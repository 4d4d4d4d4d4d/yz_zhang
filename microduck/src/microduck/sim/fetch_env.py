"""Fetch task: walk to the ball, pick it up with the beak, carry it home, drop it.

The episode runs through four phases, advanced by the environment and shown to
the policy as a one-hot:

===========  ==========================================================
APPROACH     walk until the beak is within grasping range of the ball
GRASP        bend down, close the beak on the ball and lift it
RETURN       carry the ball back to the home pad
RELEASE      open the beak over the pad and leave the ball there
===========  ==========================================================

The phases only shape the reward and the observation -- there is one policy and
one network, and it has to produce the whole sequence.  Every locomotion term
from the walking task still applies throughout, so the policy cannot buy task
reward by flailing or by dragging itself along on its chest.

Two design decisions worth knowing about before you train:

**Grasping.**  ``grasp_mode="weld"`` (the default) latches a MuJoCo weld
constraint when the beak closes on the ball, and releases it when the beak
opens.  Frictional grasping with a 1-DoF beak and a smooth sphere is genuinely
hard to make stable at this scale, and a policy spending its whole sample
budget rediscovering contact mechanics learns the task much more slowly.
``grasp_mode="contact"`` uses real friction instead and is the honest setting
for sim2real work on the gripper itself -- expect it to need far more samples.

**Navigation.**  With ``heading_command=True`` (the default) the environment
puts a desired base velocity towards the active target into the same command
channel the walking task uses, which makes this a waypoint-conditioned
locomotion-and-manipulation policy: the environment navigates, the policy walks
and grasps.  This also lets a walking checkpoint warm-start the task exactly,
since the observation is the walking one with channels appended.  With
``heading_command=False`` the command channel is zeroed and the policy must
learn navigation from the relative-position channels as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import mujoco
import numpy as np

from ..model import spec
from ..model.builder import BALL_RADIUS, FETCH_MODEL_PATH, HOME_RADIUS
from .env import OBS_LAYOUT, EnvConfig, MicroduckEnv
from .rewards import RewardConfig, locomotion_terms


class Phase(IntEnum):
    APPROACH = 0
    GRASP = 1
    RETURN = 2
    RELEASE = 3


NUM_PHASES = len(Phase)

#: The walking layout plus the task channels.  The walking channels come first
#: and keep their order, so a walking policy's weights transfer directly.
FETCH_OBS_LAYOUT: tuple[tuple[str, int], ...] = OBS_LAYOUT + (
    ("ball_rel", 3),
    ("home_rel", 3),
    ("task_phase", NUM_PHASES),
    ("grasp_state", 1),
)
FETCH_OBS_DIM = sum(size for _n, size in FETCH_OBS_LAYOUT)


@dataclass
class FetchRewardConfig:
    """Task rewards.  Locomotion terms come from :class:`RewardConfig`."""

    # The weights below are balanced against a full-length episode (25 s at
    # 50 Hz, so ~1250 steps).  Per-step terms are multiplied by that, one-time
    # bonuses are not, and getting that ratio wrong is the single easiest way
    # to make this task unlearnable: with the walking task's own `alive` and
    # `upright` weights, simply standing upright for 25 s outscores a complete
    # fetch, and the policy correctly learns to stand still and do nothing.
    # `FetchConfig.rewards` therefore also lowers those shared weights.

    #: Reward per metre of progress towards the active target.  Progress-based
    #: rather than distance-based, so it cannot be farmed by standing still in
    #: a good spot.
    approach_progress: float = 60.0
    carry_progress: float = 80.0
    #: Face the target while approaching; a duck walking at the ball sideways
    #: cannot get its beak onto it.  Small, because it is paid every step.
    facing: float = 0.05
    #: Shaped beak-to-ball distance once in range, which is what drives the
    #: bend-down motion.
    beak_reach: float = 0.5
    beak_reach_sigma: float = 0.0045
    #: Keep the beak open while reaching and closed while carrying.
    beak_posture: float = 0.05

    # One-time event bonuses.  Large relative to the dense terms, because the
    # dense terms only have to get the policy close enough to trip them.
    in_range_bonus: float = 8.0
    grasp_bonus: float = 40.0
    lift_bonus: float = 15.0
    home_bonus: float = 25.0
    success_bonus: float = 120.0

    #: Dropping the ball once it is held: the single most common failure.
    drop_penalty: float = -25.0
    #: Kicking the ball away instead of picking it up.
    ball_disturb: float = -3.0
    #: Mild per-step cost, so finishing sooner is better.
    time_penalty: float = -0.03


DEFAULT_FETCH_REWARDS = FetchRewardConfig()


def _fetch_locomotion_rewards() -> RewardConfig:
    """Walking rewards, rescaled for a task episode.

    Same shaping as the walking task -- it is what keeps the gait clean -- but
    the always-on terms are cut hard so the task terms can dominate the return.
    Velocity tracking stays off: in this task the environment supplies the
    heading command and the task terms say where to go.
    """
    cfg = RewardConfig()
    cfg.alive = 0.05
    cfg.upright = 0.10
    cfg.base_height = 0.10
    cfg.stand_still = 0.0
    cfg.lin_vel_tracking = 0.0
    cfg.ang_vel_tracking = 0.0
    cfg.feet_air_time = 0.3
    return cfg


@dataclass
class FetchConfig(EnvConfig):
    episode_length: float = 25.0

    rewards: RewardConfig = field(default_factory=_fetch_locomotion_rewards)
    fetch_rewards: FetchRewardConfig = field(default_factory=lambda: DEFAULT_FETCH_REWARDS)

    #: Where the ball is spawned, in polar coordinates around the start pose.
    ball_distance: tuple[float, float] = (0.30, 0.60)
    ball_bearing: float = 0.9            # rad, +/- off the duck's heading
    #: Curriculum knob: 0 spawns the ball at the near edge, 1 uses the full
    #: range and the full bearing spread.
    difficulty: float = 1.0

    #: Beak-to-ball distance that counts as in range.
    grasp_radius: float = 0.055
    #: Beak joint angle below which the beak counts as closed.
    beak_closed: float = 0.18
    #: ...and above which it counts as open.
    beak_open: float = 0.45
    #: Ball must come this far off the floor to count as lifted.
    lift_height: float = 0.012
    #: Ball within this distance of the pad centre counts as delivered.
    home_radius: float = HOME_RADIUS
    grasp_mode: str = "weld"             # "weld" | "contact"
    heading_command: bool = True
    #: Desired approach speed fed into the command channel.
    approach_speed: float = 0.22
    #: Stop commanding forward motion this close to the target, so the duck
    #: settles instead of walking over the ball.
    command_deadband: float = 0.10
    #: Give up on the episode if the ball is knocked outside this radius.
    ball_escape_radius: float = 1.2


class MicroduckFetchEnv(MicroduckEnv):
    """Walk to the ball, pick it up, bring it back."""

    observation_layout = FETCH_OBS_LAYOUT

    def __init__(self, config: FetchConfig | None = None, seed: int | None = None,
                 model_path=None) -> None:
        cfg = config or FetchConfig()
        if cfg.grasp_mode not in ("weld", "contact"):
            raise ValueError(f"grasp_mode must be 'weld' or 'contact', got {cfg.grasp_mode!r}")
        super().__init__(cfg, seed=seed, model_path=model_path or FETCH_MODEL_PATH)
        self.cfg: FetchConfig = cfg

        mj = mujoco
        self._ball_body = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_BODY, "ball")
        self._ball_geom = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_GEOM, "ball")
        self._beak_site = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_SITE, "beak_grip")
        self._upper_beak_geom = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_GEOM, "upper_beak")
        self._lower_beak_geom = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_GEOM, "lower_beak")
        self._grasp_eq = mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_EQUALITY, "beak_grasp")
        if self._grasp_eq < 0 and self.cfg.grasp_mode == "weld":
            raise RuntimeError("model has no 'beak_grasp' constraint; rebuild with "
                               "`microduck build-model`")
        #: Index of the ball's free joint in qpos.
        self._ball_qpos = self.model.jnt_qposadr[
            mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_JOINT, "ball_free")]
        self._ball_qvel = self.model.jnt_dofadr[
            mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_JOINT, "ball_free")]

        self.phase = Phase.APPROACH
        self.grasped = False
        self.home_xy = np.zeros(2)
        self.ball_spawn_xy = np.zeros(2)
        self._prev_target_dist = 0.0
        self._events: dict[str, bool] = {}
        self._reached_phase = Phase.APPROACH
        self.success = False

    # ------------------------------------------------------------------
    # Episode lifecycle
    # ------------------------------------------------------------------
    def _reset_task(self) -> None:
        cfg = self.cfg
        # Home is wherever the duck starts; it has to come back to its own spot.
        self.home_xy = self.data.qpos[0:2].copy()

        near, far = cfg.ball_distance
        reach = near + (far - near) * np.clip(cfg.difficulty, 0.0, 1.0) * self.rng.random()
        bearing = cfg.ball_bearing * np.clip(cfg.difficulty, 0.0, 1.0) * self.rng.uniform(-1, 1)
        heading = self._base_yaw() + bearing
        self.ball_spawn_xy = self.home_xy + reach * np.array([np.cos(heading), np.sin(heading)])

        self.data.qpos[self._ball_qpos:self._ball_qpos + 3] = (
            self.ball_spawn_xy[0], self.ball_spawn_xy[1], BALL_RADIUS)
        self.data.qpos[self._ball_qpos + 3:self._ball_qpos + 7] = (1.0, 0.0, 0.0, 0.0)
        self.data.qvel[self._ball_qvel:self._ball_qvel + 6] = 0.0

        self.phase = Phase.APPROACH
        self._reached_phase = Phase.APPROACH
        self.grasped = False
        self.success = False
        self._events = {}
        self._set_grasp_constraint(False)
        mujoco.mj_forward(self.model, self.data)
        self._prev_target_dist = self._target_distance()
        self._update_command()

    # ------------------------------------------------------------------
    # Task state
    # ------------------------------------------------------------------
    def _base_yaw(self) -> float:
        q = self.data.qpos[3:7]
        return float(np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]),
                                1 - 2 * (q[2] ** 2 + q[3] ** 2)))

    @property
    def ball_pos(self) -> np.ndarray:
        return self.data.xpos[self._ball_body].copy()

    @property
    def beak_pos(self) -> np.ndarray:
        return self.data.site_xpos[self._beak_site].copy()

    def _beak_angle(self) -> float:
        return float(self.data.qpos[7 + spec.BEAK_INDEX])

    def _beak_to_ball(self) -> float:
        return float(np.linalg.norm(self.beak_pos - self.ball_pos))

    def _ball_height(self) -> float:
        return float(self.ball_pos[2] - BALL_RADIUS)

    def _target_xy(self) -> np.ndarray:
        """The point the duck should be heading for in the current phase."""
        if self.phase in (Phase.APPROACH, Phase.GRASP):
            return self.ball_pos[:2]
        return self.home_xy

    def _target_distance(self) -> float:
        """Distance that the phase's progress reward is measured on.

        While approaching, that is the duck's own distance to the ball; while
        carrying, it is the *ball's* distance to the pad, because delivering
        the ball is the actual goal.
        """
        if self.phase in (Phase.APPROACH, Phase.GRASP):
            return float(np.linalg.norm(self.data.qpos[0:2] - self.ball_pos[:2]))
        return float(np.linalg.norm(self.ball_pos[:2] - self.home_xy))

    def _jaws_on_ball(self) -> bool:
        """True when both jaws are touching the ball."""
        upper = lower = False
        for i in range(self.data.ncon):
            con = self.data.contact[i]
            pair = (con.geom1, con.geom2)
            if self._ball_geom not in pair:
                continue
            if self._upper_beak_geom in pair:
                upper = True
            if self._lower_beak_geom in pair:
                lower = True
        return upper and lower

    def _set_grasp_constraint(self, active: bool) -> None:
        if self._grasp_eq >= 0:
            self.data.eq_active[self._grasp_eq] = 1 if active else 0

    def _post_physics(self) -> None:
        """Latch or release the grasp, before anything reads task state."""
        if self.cfg.grasp_mode == "weld":
            closed = self._beak_angle() < self.cfg.beak_closed
            if not self.grasped:
                if closed and self._beak_to_ball() < self.cfg.grasp_radius:
                    self.grasped = True
                    self._set_grasp_constraint(True)
            elif self._beak_angle() > self.cfg.beak_open:
                self.grasped = False
                self._set_grasp_constraint(False)
        else:
            self.grasped = self._jaws_on_ball()

    # ------------------------------------------------------------------
    # Phase machine
    # ------------------------------------------------------------------
    def _advance_task(self) -> None:
        cfg = self.cfg
        self._events = {}
        beak_dist = self._beak_to_ball()

        if self.phase == Phase.APPROACH:
            if beak_dist < cfg.grasp_radius:
                self.phase = Phase.GRASP
                self._events["in_range"] = True
        elif self.phase == Phase.GRASP:
            if self.grasped and self._ball_height() > cfg.lift_height:
                self.phase = Phase.RETURN
                self._events["lifted"] = True
            elif beak_dist > cfg.grasp_radius * 2.2 and not self.grasped:
                # Lost it again: go back to walking at the ball.
                self.phase = Phase.APPROACH
        elif self.phase == Phase.RETURN:
            if not self.grasped:
                self._events["dropped"] = True
                self.phase = (Phase.RELEASE if self._ball_at_home() else Phase.APPROACH)
            elif self._ball_at_home():
                self.phase = Phase.RELEASE
                self._events["home"] = True
        elif self.phase == Phase.RELEASE:
            if not self.grasped and self._ball_at_home() and self._ball_settled():
                self.success = True
            elif self.grasped and not self._ball_at_home():
                self.phase = Phase.RETURN

        if self.phase > self._reached_phase:
            self._reached_phase = self.phase
        self._update_command()

    def _ball_at_home(self) -> bool:
        return bool(np.linalg.norm(self.ball_pos[:2] - self.home_xy) < self.cfg.home_radius)

    def _ball_settled(self) -> bool:
        """Ball on the ground and nearly still, i.e. actually delivered."""
        return (self._ball_height() < 0.006
                and float(np.linalg.norm(self.data.qvel[
                    self._ball_qvel:self._ball_qvel + 3])) < 0.08)

    def _update_command(self) -> None:
        """Waypoint heading, written into the walking task's command channel."""
        if not self.cfg.heading_command:
            self.command[:] = 0.0
            return
        delta = self._target_xy() - self.data.qpos[0:2]
        distance = float(np.linalg.norm(delta))
        yaw = self._base_yaw()
        bearing = float(np.arctan2(delta[1], delta[0]) - yaw)
        bearing = (bearing + np.pi) % (2 * np.pi) - np.pi

        # Turn to face the target first, then walk at it.  Commanding forward
        # speed while badly misaligned just makes the duck walk past.
        self.command[2] = float(np.clip(2.0 * bearing, -1.0, 1.0))
        if distance < self.cfg.command_deadband or abs(bearing) > 0.6:
            self.command[0] = 0.0
        else:
            self.command[0] = self.cfg.approach_speed * float(np.clip(distance / 0.3, 0.2, 1.0))
        self.command[1] = 0.0

    # ------------------------------------------------------------------
    # Rewards
    # ------------------------------------------------------------------
    def _reward_terms(self, reward_obs: dict) -> dict[str, float]:
        cfg = self.cfg.fetch_rewards
        terms = locomotion_terms(self.cfg.rewards, reward_obs)

        # Progress on the active target, clipped so a physics glitch or a
        # bounced ball cannot hand out a huge one-step reward.
        distance = self._target_distance()
        progress = float(np.clip(self._prev_target_dist - distance, -0.05, 0.05))
        self._prev_target_dist = distance
        weight = cfg.carry_progress if self.phase >= Phase.RETURN else cfg.approach_progress
        terms["progress"] = weight * progress

        # Facing the target matters while walking at it, not while carrying.
        delta = self._target_xy() - self.data.qpos[0:2]
        if np.linalg.norm(delta) > 1e-6:
            heading = np.array([np.cos(self._base_yaw()), np.sin(self._base_yaw())])
            cosine = float(np.dot(heading, delta / np.linalg.norm(delta)))
            terms["facing"] = cfg.facing * cosine
        else:
            terms["facing"] = 0.0

        beak_dist = self._beak_to_ball()
        if self.phase == Phase.GRASP:
            terms["beak_reach"] = cfg.beak_reach * float(
                np.exp(-(beak_dist ** 2) / cfg.beak_reach_sigma))
            # Open beak while reaching in, closed once the ball is held.
            want_open = not self.grasped
            angle = self._beak_angle()
            opened = angle > self.cfg.beak_open
            terms["beak_posture"] = cfg.beak_posture * (1.0 if opened == want_open else -1.0)
        else:
            terms["beak_reach"] = 0.0
            terms["beak_posture"] = cfg.beak_posture * (1.0 if self.grasped else 0.0)

        # Kicking the ball around instead of picking it up.
        ball_speed = float(np.linalg.norm(self.data.qvel[self._ball_qvel:self._ball_qvel + 2]))
        terms["ball_disturb"] = cfg.ball_disturb * (0.0 if self.grasped else ball_speed ** 2)
        terms["time_penalty"] = cfg.time_penalty

        events = self._events
        terms["in_range_bonus"] = cfg.in_range_bonus if events.get("in_range") else 0.0
        terms["lift_bonus"] = cfg.lift_bonus if events.get("lifted") else 0.0
        terms["home_bonus"] = cfg.home_bonus if events.get("home") else 0.0
        terms["drop_penalty"] = cfg.drop_penalty if events.get("dropped") else 0.0
        # Credited once, on the step the grasp first latches.
        if self.grasped and not getattr(self, "_grasp_credited", False):
            terms["grasp_bonus"] = cfg.grasp_bonus
            self._grasp_credited = True
        else:
            terms["grasp_bonus"] = 0.0
        terms["success_bonus"] = cfg.success_bonus if self.success else 0.0
        return terms

    # ------------------------------------------------------------------
    # Termination
    # ------------------------------------------------------------------
    def _terminated(self) -> bool:
        if super()._terminated():
            return True
        if self.success:
            return True
        # Ball punted out of the arena: nothing left to learn this episode.
        return bool(np.linalg.norm(self.ball_pos[:2] - self.home_xy)
                    > self.cfg.ball_escape_radius)

    def reset(self, seed: int | None = None):
        self._grasp_credited = False
        return super().reset(seed=seed)

    # ------------------------------------------------------------------
    # Observations and logging
    # ------------------------------------------------------------------
    def raw_observation(self) -> dict[str, np.ndarray]:
        channels = super().raw_observation()
        rot = self._base_rotation()
        base = self.data.qpos[0:3]
        home = np.array([self.home_xy[0], self.home_xy[1], 0.0])
        channels["ball_rel"] = rot.T @ (self.ball_pos - base)
        channels["home_rel"] = rot.T @ (home - base)
        phase = np.zeros(NUM_PHASES)
        phase[int(self.phase)] = 1.0
        channels["task_phase"] = phase
        channels["grasp_state"] = np.array([1.0 if self.grasped else 0.0])
        return channels

    def _apply_sensor_noise(self, raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        raw = super()._apply_sensor_noise(raw)
        # On the real robot the ball and the pad are found by the camera and the
        # ToF sensor, so the policy trains against estimates, not ground truth.
        raw["ball_rel"] = raw["ball_rel"] + self.randomizer.observation_noise("object_pos", 3)
        raw["home_rel"] = raw["home_rel"] + self.randomizer.observation_noise("object_pos", 3)
        return raw

    def _task_info(self) -> dict:
        return {
            "command": self.command.copy(),
            "phase": int(self.phase),
            "reached_phase": int(self._reached_phase),
            "grasped": bool(self.grasped),
            "success": bool(self.success),
            "ball_to_home": float(np.linalg.norm(self.ball_pos[:2] - self.home_xy)),
            "beak_to_ball": self._beak_to_ball(),
        }
