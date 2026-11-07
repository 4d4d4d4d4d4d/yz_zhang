"""The Microduck walking environment.

A plain ``reset()`` / ``step()`` environment over MuJoCo -- no gym dependency,
because the only consumers are this repo's trainer and playback tools, and a
hard gym/gymnasium pin is the fastest way to make a robotics repo
un-installable a year later.  The signatures follow the gymnasium 5-tuple
convention (``obs, reward, terminated, truncated, info``) so wrapping it is
trivial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import mujoco
import numpy as np

from ..model import spec
from ..model.builder import MODEL_PATH
from . import gait
from .randomization import DEFAULT_RANDOMIZATION, DomainRandomizer, RandomizationConfig
from .rewards import DEFAULT_REWARDS, RewardConfig, compute as compute_rewards

#: Observation layout.  Exported so the runtime and the ONNX exporter build the
#: input vector in exactly the order the policy was trained on.
OBS_LAYOUT: tuple[tuple[str, int], ...] = (
    ("projected_gravity", 3),
    ("base_ang_vel", 3),
    ("joint_pos", spec.NUM_JOINTS),
    ("joint_vel", spec.NUM_JOINTS),
    ("prev_action", spec.NUM_JOINTS),
    ("command", 3),
    ("gait_phase", 2),
)
OBS_DIM = sum(size for _n, size in OBS_LAYOUT)
ACTION_DIM = spec.NUM_JOINTS

#: Per-channel scaling, applied before the network sees anything, so no running
#: normaliser is needed on-robot.
OBS_SCALES: dict[str, float] = {
    "projected_gravity": 1.0, "base_ang_vel": 0.25, "joint_pos": 1.0,
    "joint_vel": 0.05, "prev_action": 1.0, "command": 1.0, "gait_phase": 1.0,
    # Fetch-task channels.
    "ball_rel": 2.0, "home_rel": 1.0, "task_phase": 1.0, "grasp_state": 1.0,
}


def assemble_observation(channels: dict[str, np.ndarray],
                         layout: tuple[tuple[str, int], ...] = OBS_LAYOUT) -> np.ndarray:
    """Flatten named channels into the policy input vector.

    Shared by the simulator and the on-robot runtime, so a policy can never be
    fed its inputs in a different order than it was trained with.
    """
    parts = []
    for name, size in layout:
        value = np.asarray(channels[name], dtype=np.float32).ravel()
        if value.size != size:
            raise ValueError(f"channel {name!r} has size {value.size}, expected {size}")
        parts.append(value * OBS_SCALES[name])
    return np.concatenate(parts).astype(np.float32)


@dataclass
class CommandRanges:
    """The velocity commands the policy is trained to follow."""

    lin_vel_x: tuple[float, float] = (-0.15, 0.35)
    lin_vel_y: tuple[float, float] = (-0.12, 0.12)
    ang_vel_z: tuple[float, float] = (-1.0, 1.0)
    stand_probability: float = 0.15
    resample_interval: float = 4.0    # s


@dataclass
class EnvConfig:
    episode_length: float = 12.0      # s
    commands: CommandRanges = field(default_factory=CommandRanges)
    rewards: RewardConfig = field(default_factory=lambda: DEFAULT_REWARDS)
    randomization: RandomizationConfig = field(default_factory=lambda: DEFAULT_RANDOMIZATION)
    gait: gait.GaitParams = field(default_factory=gait.GaitParams)
    min_height: float = 0.075         # terminate below this torso height
    max_tilt: float = 0.55            # ...or tilted past ~56 degrees
    action_scale: float = spec.ACTUATION.action_scale


class MicroduckEnv:
    """Velocity-tracking walking task."""

    observation_layout = OBS_LAYOUT

    def __init__(self, config: EnvConfig | None = None, seed: int | None = None,
                 model_path=None) -> None:
        self.cfg = config or EnvConfig()
        self.rng = np.random.default_rng(seed)
        self.model = mujoco.MjModel.from_xml_path(str(model_path or MODEL_PATH))
        self.model.opt.timestep = spec.SIM_TIMESTEP
        self.data = mujoco.MjData(self.model)

        self.dt = spec.CONTROL_DT
        self.decimation = spec.CONTROL_DECIMATION
        self.max_steps = int(self.cfg.episode_length / self.dt)

        self.default_pos = np.array(spec.default_pose())
        self.lower, self.upper = (np.array(a) for a in spec.joint_limits())

        name2id = lambda kind, n: mujoco.mj_name2id(self.model, kind, n)  # noqa: E731
        self._foot_geoms = [name2id(mujoco.mjtObj.mjOBJ_GEOM, n)
                            for n in ("left_foot", "right_foot")]
        self._foot_bodies = [name2id(mujoco.mjtObj.mjOBJ_BODY, n)
                             for n in ("left_foot", "right_foot")]
        self._head_body = name2id(mujoco.mjtObj.mjOBJ_BODY, "head")

        self.randomizer = DomainRandomizer(self.model, self.cfg.randomization, self.rng)
        self.observation_dim = sum(s for _n, s in self.observation_layout)
        self.action_dim = ACTION_DIM

        self.command = np.zeros(3)
        self.action = np.zeros(ACTION_DIM)
        self.prev_action = np.zeros(ACTION_DIM)
        self.applied_target = self.default_pos.copy()
        self.gait_phase = 0.0
        self.step_count = 0
        self.feet_air_time = np.zeros(2)
        self.feet_contact = np.zeros(2)

    # ------------------------------------------------------------------
    # Episode lifecycle
    # ------------------------------------------------------------------
    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self.randomizer.rng = self.rng

        mujoco.mj_resetData(self.model, self.data)
        self.randomizer.resample(0.0)
        self._reset_state()
        self._reset_task()
        mujoco.mj_forward(self.model, self.data)

        self.action[:] = 0.0
        self.prev_action[:] = 0.0
        self.applied_target = self.data.qpos[7:7 + ACTION_DIM].copy()
        self.gait_phase = float(self.rng.uniform(0.0, 1.0))
        self.step_count = 0
        self.feet_air_time[:] = 0.0
        self.feet_contact[:] = 0.0
        return self._observation(), {}

    def _reset_state(self) -> None:
        cfg_rand = self.cfg.randomization
        jitter = cfg_rand.initial_joint_jitter if cfg_rand.enabled else 0.0
        yaw = self.rng.uniform(-cfg_rand.initial_yaw, cfg_rand.initial_yaw) if cfg_rand.enabled else 0.0
        self.data.qpos[0:3] = (0.0, 0.0, spec.NOMINAL_STANDING_HEIGHT)
        self.data.qpos[3:7] = (np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2))
        self.data.qpos[7:7 + ACTION_DIM] = np.clip(
            self.default_pos + self.rng.uniform(-jitter, jitter, ACTION_DIM),
            self.lower, self.upper)
        self.data.qvel[:] = 0.0
        self.data.ctrl[:] = self.data.qpos[7:7 + ACTION_DIM]

    def _reset_task(self) -> None:
        """Hook for subclasses; the walking task only needs a velocity command."""
        self._resample_command()

    def _resample_command(self) -> None:
        c = self.cfg.commands
        if self.rng.random() < c.stand_probability:
            self.command[:] = 0.0
            return
        self.command[0] = self.rng.uniform(*c.lin_vel_x)
        self.command[1] = self.rng.uniform(*c.lin_vel_y)
        self.command[2] = self.rng.uniform(*c.ang_vel_z)
        # Snap tiny commands to a stop, so the policy gets a clean "hold still"
        # signal rather than an unfollowable crawl.
        if np.linalg.norm(self.command) < 0.06:
            self.command[:] = 0.0

    # ------------------------------------------------------------------
    # Stepping
    # ------------------------------------------------------------------
    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        action = np.clip(np.asarray(action, dtype=np.float64),
                         -spec.ACTUATION.action_clip, spec.ACTUATION.action_clip)
        self.prev_action[:] = self.action
        self.action[:] = action

        target = np.clip(self.default_pos + self.cfg.action_scale * action,
                         self.lower, self.upper)
        # First-order lag standing in for the servo-bus round trip.
        alpha = 1.0 if self.randomizer.action_latency <= 0 else min(
            1.0, self.dt / max(self.randomizer.action_latency, 1e-6))
        self.applied_target += alpha * (target - self.applied_target)

        prev_joint_vel = self.data.qvel[6:6 + ACTION_DIM].copy()
        for _ in range(self.decimation):
            self.data.ctrl[:] = self.applied_target
            mujoco.mj_step(self.model, self.data)
        self._post_physics()

        self.randomizer.maybe_push(self.data, self.data.time)
        self.gait_phase = (self.gait_phase + self.cfg.gait.frequency * self.dt) % 1.0
        self.step_count += 1
        self._advance_task()

        just_landed = self._update_feet()
        terminated = self._terminated()
        truncated = self.step_count >= self.max_steps

        joint_vel = self.data.qvel[6:6 + ACTION_DIM].copy()
        reward_obs = {
            "command": self.command,
            "base_lin_vel": self._base_lin_vel(),
            "base_ang_vel": self._base_ang_vel(),
            "head_ang_vel": self.data.cvel[self._head_body][:3].copy(),
            "projected_gravity": self._projected_gravity(),
            "base_height": float(self.data.qpos[2]),
            "joint_pos": self.data.qpos[7:7 + ACTION_DIM].copy(),
            "joint_vel": joint_vel,
            "joint_acc": (joint_vel - prev_joint_vel) / self.dt,
            "default_pos": self.default_pos,
            "torques": self.data.actuator_force.copy(),
            "action": self.action,
            "prev_action": self.prev_action,
            "feet_air_time": self.feet_air_time.copy(),
            "feet_just_landed": just_landed,
            "feet_contact": self.feet_contact.copy(),
            "feet_speed": self._feet_speed(),
            "terminated": terminated,
        }
        terms = self._reward_terms(reward_obs)
        reward = float(sum(terms.values()))
        self.feet_air_time[just_landed > 0] = 0.0

        info = {"reward_terms": terms, "height": reward_obs["base_height"],
                "episode_length": self.step_count}
        info.update(self._task_info())
        return self._observation(), reward, terminated, truncated, info

    def _reward_terms(self, reward_obs: dict) -> dict[str, float]:
        return compute_rewards(self.cfg.rewards, reward_obs, self.dt)

    def _post_physics(self) -> None:
        """Hook run right after the physics substeps, before anything reads state."""

    def _advance_task(self) -> None:
        if self.step_count % max(1, int(self.cfg.commands.resample_interval / self.dt)) == 0:
            self._resample_command()

    def _task_info(self) -> dict:
        return {"command": self.command.copy()}

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _base_rotation(self) -> np.ndarray:
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, self.data.qpos[3:7])
        return rot.reshape(3, 3)

    def _projected_gravity(self) -> np.ndarray:
        """Gravity in the base frame -- what an accelerometer reads at rest."""
        return self._base_rotation().T @ np.array([0.0, 0.0, -1.0])

    def _base_lin_vel(self) -> np.ndarray:
        return self._base_rotation().T @ self.data.qvel[0:3]

    def _base_ang_vel(self) -> np.ndarray:
        return self.data.qvel[3:6].copy()

    def _contacts(self) -> np.ndarray:
        contact = np.zeros(2)
        for i in range(self.data.ncon):
            con = self.data.contact[i]
            for k, geom in enumerate(self._foot_geoms):
                if geom in (con.geom1, con.geom2):
                    contact[k] = 1.0
        return contact

    def _feet_speed(self) -> np.ndarray:
        """Horizontal foot speed; non-zero while in contact means slip."""
        return np.array([float(np.linalg.norm(self.data.cvel[b][3:5]))
                         for b in self._foot_bodies])

    def _update_feet(self) -> np.ndarray:
        contact = self._contacts()
        just_landed = ((contact > 0) & (self.feet_contact == 0)).astype(np.float64)
        self.feet_air_time += self.dt * (contact == 0)
        self.feet_contact = contact
        return just_landed

    def _terminated(self) -> bool:
        if self.data.qpos[2] < self.cfg.min_height:
            return True
        if -self._projected_gravity()[2] < self.cfg.max_tilt:
            return True
        return not np.all(np.isfinite(self.data.qpos))

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------
    def raw_observation(self) -> dict[str, np.ndarray]:
        """The unscaled, noise-free channels -- handy for debugging."""
        return {
            "projected_gravity": self._projected_gravity(),
            "base_ang_vel": self._base_ang_vel(),
            "joint_pos": self.data.qpos[7:7 + ACTION_DIM] - self.default_pos,
            "joint_vel": self.data.qvel[6:6 + ACTION_DIM].copy(),
            "prev_action": self.action.copy(),
            "command": self.command.copy(),
            "gait_phase": np.array(gait.phase_signal(self.gait_phase)),
        }

    def _apply_sensor_noise(self, raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Corrupt the channels the way the real sensors do.

        Subclasses extend this for the channels they add rather than
        reassembling the observation themselves.
        """
        noise = self.randomizer
        raw["joint_pos"] = raw["joint_pos"] + noise.joint_bias + noise.observation_noise(
            "joint_pos", ACTION_DIM)
        raw["joint_vel"] = raw["joint_vel"] + noise.observation_noise("joint_vel", ACTION_DIM)
        raw["base_ang_vel"] = raw["base_ang_vel"] + noise.observation_noise("gyro", 3)
        raw["projected_gravity"] = raw["projected_gravity"] + noise.observation_noise("gravity", 3)
        return raw

    def _observation(self) -> np.ndarray:
        raw = self._apply_sensor_noise(self.raw_observation())
        return assemble_observation(raw, self.observation_layout)
