"""Unitree G1 backflip environment (Isaac Lab DirectRLEnv).

Each episode is one backflip attempt. The policy observes a phase signal
(time + reference pitch / height) and is rewarded for tracking a reference
trajectory: crouch -> jump -> rotate 2*pi backwards -> land -> stand.

Frame conventions (Isaac Sim, z-up, x-forward):
    a *backflip* is a rotation about the world +y axis with NEGATIVE angle
    (nose goes up and over backwards), i.e. root_ang_vel_w[:, 1] < 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import torch

import isaaclab.sim as sim_utils
import isaaclab.utils.math as math_utils
from isaaclab.assets import Articulation
from isaaclab.envs import DirectRLEnv
from isaaclab.sensors import ContactSensor

from .g1_backflip_env_cfg import G1BackflipEnvCfg


class G1BackflipEnv(DirectRLEnv):
    cfg: G1BackflipEnvCfg

    def __init__(self, cfg: G1BackflipEnvCfg, render_mode: str | None = None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)

        # ---------------------------------------------------------- joints
        self._ctrl_ids, ctrl_names = self.robot.find_joints(self.cfg.controlled_joints)
        if len(self._ctrl_ids) != self.cfg.action_space:
            raise RuntimeError(
                f"[G1Backflip] controlled_joints matched {len(self._ctrl_ids)} joints, but action_space="
                f"{self.cfg.action_space}. Matched: {ctrl_names}. All joints: {self.robot.joint_names}. "
                "Update `controlled_joints`, `action_space` and `observation_space` in the cfg."
            )
        self._ctrl_ids_t = torch.tensor(self._ctrl_ids, device=self.device, dtype=torch.long)
        print(f"[G1Backflip] controlling {len(ctrl_names)} joints: {ctrl_names}")

        # left/right pairs for planar-symmetry penalty (optional)
        self._sym_l, self._sym_r = None, None
        try:
            self._sym_l, _ = self.robot.find_joints(
                ["left_hip_pitch_joint", "left_knee_joint", "left_ankle_pitch_joint"], preserve_order=True
            )
            self._sym_r, _ = self.robot.find_joints(
                ["right_hip_pitch_joint", "right_knee_joint", "right_ankle_pitch_joint"], preserve_order=True
            )
        except (ValueError, RuntimeError):
            print("[G1Backflip][WARN] symmetry joints not found, leg_symmetry reward disabled.")

        # ---------------------------------------------------------- bodies
        self._term_body_ids, _ = self.contact_sensor.find_bodies(self.cfg.termination_bodies)
        self._feet_ids, feet_names = self.contact_sensor.find_bodies(self.cfg.feet_bodies)
        print(f"[G1Backflip] feet bodies: {feet_names}")

        # ---------------------------------------------------------- buffers
        n = self.num_envs
        self.actions = torch.zeros(n, self.cfg.action_space, device=self.device)
        self.prev_actions = torch.zeros_like(self.actions)
        self._joint_targets = self.robot.data.default_joint_pos.clone()
        self._pitch_integral = torch.zeros(n, device=self.device)  # unwrapped pitch (rad)
        self._start_pos = torch.zeros(n, 3, device=self.device)
        self._y_axis = torch.tensor([0.0, 1.0, 0.0], device=self.device).repeat(n, 1)

        self._h_t = torch.tensor(self.cfg.height_keyframes_t, device=self.device)
        self._h_z = torch.tensor(self.cfg.height_keyframes_z, device=self.device)

        self._episode_sums = {
            key: torch.zeros(n, dtype=torch.float, device=self.device)
            for key in vars(self.cfg.rewards).keys()
            if not key.startswith("_")
        }
        self._episode_sums["max_rotation_deg"] = torch.zeros(n, device=self.device)

    # ================================================================ scene
    def _setup_scene(self):
        self.robot = Articulation(self.cfg.robot)
        self.scene.articulations["robot"] = self.robot
        self.contact_sensor = ContactSensor(self.cfg.contact_sensor)
        self.scene.sensors["contact_sensor"] = self.contact_sensor

        self.cfg.terrain.num_envs = self.scene.cfg.num_envs
        self.cfg.terrain.env_spacing = self.scene.cfg.env_spacing
        self._terrain = self.cfg.terrain.class_type(self.cfg.terrain)

        self.scene.clone_environments(copy_from_source=False)
        self.scene.filter_collisions(global_prim_paths=[self.cfg.terrain.prim_path])

        light_cfg = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.75, 0.75, 0.75))
        light_cfg.func("/World/Light", light_cfg)

    # ============================================================ reference
    def _time(self) -> torch.Tensor:
        return self.episode_length_buf.float() * self.step_dt

    def _reference(self, t: torch.Tensor):
        """Returns (pitch_ref, pitch_rate_ref, height_ref) for time t."""
        t0, t1 = self.cfg.flip_start_t, self.cfg.flip_end_t
        s = ((t - t0) / (t1 - t0)).clamp(0.0, 1.0)
        pitch = -2.0 * math.pi * (3.0 * s**2 - 2.0 * s**3)
        rate = -2.0 * math.pi * 6.0 * s * (1.0 - s) / (t1 - t0)

        # piecewise-linear height
        xs, ys = self._h_t, self._h_z
        tc = t.clamp(xs[0], xs[-1])
        idx = torch.searchsorted(xs, tc.contiguous(), right=True).clamp(1, len(xs) - 1)
        x0, x1, y0, y1 = xs[idx - 1], xs[idx], ys[idx - 1], ys[idx]
        height = y0 + (tc - x0) / (x1 - x0) * (y1 - y0)
        return pitch, rate, height

    # ============================================================== actions
    def _pre_physics_step(self, actions: torch.Tensor):
        self.prev_actions[:] = self.actions
        self.actions = actions.clone().clamp(-self.cfg.action_clip, self.cfg.action_clip)
        default = self.robot.data.default_joint_pos[:, self._ctrl_ids_t]
        target = default + self.cfg.action_scale * self.actions
        limits = self.robot.data.soft_joint_pos_limits[:, self._ctrl_ids_t]
        target = torch.max(torch.min(target, limits[..., 1]), limits[..., 0])
        self._joint_targets[:, self._ctrl_ids_t] = target

    def _apply_action(self):
        self.robot.set_joint_position_target(self._joint_targets)
        # integrate world pitch rate at physics rate -> unwrapped rotation angle
        self._pitch_integral += self.robot.data.root_ang_vel_w[:, 1] * self.physics_dt

    # ========================================================= observations
    def _get_observations(self) -> dict:
        t = self._time()
        pitch_ref, rate_ref, h_ref = self._reference(t)
        d = self.robot.data
        q = d.joint_pos[:, self._ctrl_ids_t] - d.default_joint_pos[:, self._ctrl_ids_t]
        dq = d.joint_vel[:, self._ctrl_ids_t]
        height = d.root_pos_w[:, 2:3] - self.scene.env_origins[:, 2:3]
        phase = torch.stack(
            (
                t / self.max_episode_length_s,
                torch.sin(pitch_ref),
                torch.cos(pitch_ref),
                rate_ref / 10.0,
                h_ref,
            ),
            dim=-1,
        )
        obs = torch.cat(
            (
                d.root_lin_vel_b,
                d.root_ang_vel_b * 0.25,
                d.projected_gravity_b,
                height,
                q,
                dq * 0.05,
                self.actions,
                phase,
            ),
            dim=-1,
        )
        return {"policy": obs}

    # ============================================================== rewards
    def _get_rewards(self) -> torch.Tensor:
        cfg, w = self.cfg, self.cfg.rewards
        d = self.robot.data
        t = self._time()
        pitch_ref, rate_ref, h_ref = self._reference(t)
        dt = self.step_dt

        height = d.root_pos_w[:, 2] - self.scene.env_origins[:, 2]
        q_ref = math_utils.quat_from_angle_axis(pitch_ref, self._y_axis)
        orient_err = math_utils.quat_error_magnitude(d.root_quat_w, q_ref)
        ang_vel_w = d.root_ang_vel_w

        in_flip = ((t >= cfg.flip_start_t) & (t <= cfg.flip_end_t)).float()
        in_takeoff = ((t >= cfg.takeoff_window[0]) & (t <= cfg.takeoff_window[1])).float()
        landed = (t >= cfg.land_t).float()

        feet_force = self.contact_sensor.data.net_forces_w[:, self._feet_ids].norm(dim=-1)
        feet_contact = (feet_force > cfg.contact_force_threshold).float().mean(dim=1)

        q_dev = d.joint_pos[:, self._ctrl_ids_t] - d.default_joint_pos[:, self._ctrl_ids_t]
        limits = d.soft_joint_pos_limits[:, self._ctrl_ids_t]
        q_ctrl = d.joint_pos[:, self._ctrl_ids_t]
        out_of_limits = (-(q_ctrl - limits[..., 0]).clamp(max=0.0) + (q_ctrl - limits[..., 1]).clamp(min=0.0)).sum(1)

        if self._sym_l is not None:
            sym = torch.sum((d.joint_pos[:, self._sym_l] - d.joint_pos[:, self._sym_r]) ** 2, dim=1)
        else:
            sym = torch.zeros_like(height)

        terms = {
            "pitch_track": torch.exp(-((self._pitch_integral - pitch_ref) ** 2) / cfg.sigma_pitch**2),
            "orient_track": torch.exp(-(orient_err**2) / cfg.sigma_orient**2),
            "ang_vel_track": torch.exp(-((ang_vel_w[:, 1] - rate_ref) ** 2) / cfg.sigma_ang_vel**2),
            "height_track": torch.exp(-((height - h_ref) ** 2) / cfg.sigma_height**2),
            "spin_bonus": in_flip * (-ang_vel_w[:, 1]).clamp(0.0, 12.0),
            "takeoff_vel": in_takeoff * d.root_lin_vel_w[:, 2].clamp(0.0, 4.0),
            "feet_contact_land": landed * feet_contact,
            "stand_still": landed * torch.exp(-(d.root_lin_vel_w.norm(dim=1) ** 2 + 0.2 * ang_vel_w.norm(dim=1) ** 2)),
            "default_pose_land": landed * torch.exp(-torch.sum(q_dev**2, dim=1) / 2.0),
            "lateral_ang_vel": ang_vel_w[:, 0] ** 2 + ang_vel_w[:, 2] ** 2,
            "lateral_drift": (d.root_pos_w[:, 1] - self._start_pos[:, 1]).abs(),
            "leg_symmetry": sym,
            "action_rate": torch.sum((self.actions - self.prev_actions) ** 2, dim=1),
            "joint_torque": torch.sum(d.applied_torque**2, dim=1),
            "joint_acc": torch.sum(d.joint_acc[:, self._ctrl_ids_t] ** 2, dim=1),
            "joint_pos_limit": out_of_limits,
        }

        reward = torch.zeros(self.num_envs, device=self.device)
        for name, value in terms.items():
            scaled = value * getattr(w, name) * dt
            reward += scaled
            self._episode_sums[name] += scaled

        term = self.reset_terminated.float() * w.termination
        reward += term
        self._episode_sums["termination"] += term
        self._episode_sums["max_rotation_deg"] = torch.max(
            self._episode_sums["max_rotation_deg"], -self._pitch_integral * 180.0 / math.pi
        )
        return reward

    # ================================================================ dones
    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        time_out = self.episode_length_buf >= self.max_episode_length - 1
        d = self.robot.data
        t = self._time()
        pitch_ref, _, _ = self._reference(t)

        force_hist = self.contact_sensor.data.net_forces_w_history[:, :, self._term_body_ids]
        body_contact = torch.any(
            torch.max(torch.norm(force_hist, dim=-1), dim=1)[0] > self.cfg.contact_force_threshold, dim=1
        )
        height = d.root_pos_w[:, 2] - self.scene.env_origins[:, 2]
        too_low = height < self.cfg.min_base_height

        q_ref = math_utils.quat_from_angle_axis(pitch_ref, self._y_axis)
        orient_err = math_utils.quat_error_magnitude(d.root_quat_w, q_ref)
        off_track = orient_err > self.cfg.max_orient_err

        died = body_contact | too_low | off_track
        return died, time_out

    # ================================================================ reset
    def _reset_idx(self, env_ids: Sequence[int] | None):
        if env_ids is None or len(env_ids) == self.num_envs:
            env_ids = self.robot._ALL_INDICES

        # ---- logging (before buffers are cleared)
        extras = {}
        for key, val in self._episode_sums.items():
            if key == "max_rotation_deg":
                extras["Episode/max_rotation_deg"] = torch.mean(val[env_ids])
            else:
                extras[f"Episode_Reward/{key}"] = torch.mean(val[env_ids]) / self.max_episode_length_s
            val[env_ids] = 0.0
        extras["Episode_Termination/died"] = torch.count_nonzero(self.reset_terminated[env_ids]).item()
        extras["Episode_Termination/time_out"] = torch.count_nonzero(self.reset_time_outs[env_ids]).item()
        self.extras["log"] = extras

        self.robot.reset(env_ids)
        super()._reset_idx(env_ids)

        # ---- robot state: standing, facing +x, small joint noise
        joint_pos = self.robot.data.default_joint_pos[env_ids].clone()
        joint_pos += 0.05 * (torch.rand_like(joint_pos) - 0.5)
        limits = self.robot.data.soft_joint_pos_limits[env_ids]
        joint_pos = torch.max(torch.min(joint_pos, limits[..., 1]), limits[..., 0])
        joint_vel = torch.zeros_like(joint_pos)

        root_state = self.robot.data.default_root_state[env_ids].clone()
        root_state[:, :3] += self.scene.env_origins[env_ids]
        self.robot.write_root_pose_to_sim(root_state[:, :7], env_ids)
        self.robot.write_root_velocity_to_sim(root_state[:, 7:], env_ids)
        self.robot.write_joint_state_to_sim(joint_pos, joint_vel, None, env_ids)

        self._joint_targets[env_ids] = self.robot.data.default_joint_pos[env_ids]
        self.actions[env_ids] = 0.0
        self.prev_actions[env_ids] = 0.0
        self._pitch_integral[env_ids] = 0.0
        self._start_pos[env_ids] = root_state[:, :3]
