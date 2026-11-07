"""Domain randomisation.

Sim2Real for a robot this cheap stands or falls on this file.  The servos are
hobby-grade, the feet are printed plastic, and the mass changes every time a
battery is swapped -- so the policy is trained against a distribution of robots
rather than one nominal model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..model import spec


@dataclass
class RandomizationConfig:
    enabled: bool = True

    # Inertial.
    body_mass_scale: tuple[float, float] = (0.85, 1.18)
    payload_mass: tuple[float, float] = (0.0, 0.06)      # kg strapped to the torso
    com_shift: float = 0.008                             # m per axis

    # Contact.
    floor_friction: tuple[float, float] = (0.55, 1.15)

    # Actuation: gearboxes vary part to part and warm up over a session.
    kp_scale: tuple[float, float] = (0.80, 1.25)
    kd_scale: tuple[float, float] = (0.70, 1.35)
    torque_scale: tuple[float, float] = (0.80, 1.10)
    joint_friction_scale: tuple[float, float] = (0.5, 1.8)
    armature_scale: tuple[float, float] = (0.8, 1.3)

    # Signal path.
    action_latency: tuple[float, float] = (0.004, 0.022)  # s
    joint_pos_noise: float = 0.012                        # rad
    joint_vel_noise: float = 0.35                         # rad/s
    gyro_noise: float = 0.06                              # rad/s
    gravity_noise: float = 0.035
    joint_bias: float = 0.020                             # rad, constant per joint
    #: Perception noise on the task-object channels (ball/home positions),
    #: standing in for what the camera and ToF sensor actually deliver.
    object_pos_noise: float = 0.015                       # m

    # Disturbances.
    push_interval: tuple[float, float] = (2.0, 6.0)       # s
    push_velocity: float = 0.35                           # m/s applied to the base
    initial_joint_jitter: float = 0.06                    # rad
    initial_yaw: float = np.pi                            # rad, +/- around start


DEFAULT_RANDOMIZATION = RandomizationConfig()


class DomainRandomizer:
    """Draws one robot instance per episode and holds the per-episode noise."""

    def __init__(self, model, cfg: RandomizationConfig, rng: np.random.Generator) -> None:
        self.model = model
        self.cfg = cfg
        self.rng = rng
        # Nominal values, so every reset perturbs the original model rather
        # than compounding on the last episode's perturbation.
        self._nominal = {
            "mass": model.body_mass.copy(), "ipos": model.body_ipos.copy(),
            "friction": model.geom_friction.copy(), "gainprm": model.actuator_gainprm.copy(),
            "biasprm": model.actuator_biasprm.copy(),
            "forcerange": model.actuator_forcerange.copy(),
            "frictionloss": model.dof_frictionloss.copy(),
            "armature": model.dof_armature.copy(),
        }
        self.action_latency = spec.ACTUATION.command_latency
        self.joint_bias = np.zeros(spec.NUM_JOINTS)
        self.next_push_time = float("inf")

    def _uniform(self, bounds, size=None):
        return self.rng.uniform(bounds[0], bounds[1], size=size)

    def _restore_nominal(self) -> None:
        m, n = self.model, self._nominal
        m.body_mass[:] = n["mass"]
        m.body_ipos[:] = n["ipos"]
        m.geom_friction[:] = n["friction"]
        m.actuator_gainprm[:] = n["gainprm"]
        m.actuator_biasprm[:] = n["biasprm"]
        m.actuator_forcerange[:] = n["forcerange"]
        m.dof_frictionloss[:] = n["frictionloss"]
        m.dof_armature[:] = n["armature"]
        self.action_latency = spec.ACTUATION.command_latency
        self.joint_bias[:] = 0.0
        self.next_push_time = float("inf")

    def resample(self, time_now: float = 0.0) -> None:
        """Draw a fresh robot.  Call once per episode reset."""
        self._restore_nominal()
        if not self.cfg.enabled:
            return
        m, cfg, n = self.model, self.cfg, self._nominal

        m.body_mass[:] = n["mass"] * self._uniform(cfg.body_mass_scale, m.nbody)
        m.body_mass[1] += self._uniform(cfg.payload_mass)          # torso payload
        m.body_ipos[:] = n["ipos"] + self.rng.uniform(
            -cfg.com_shift, cfg.com_shift, size=n["ipos"].shape)

        friction = n["friction"].copy()
        friction[:, 0] *= self._uniform(cfg.floor_friction)
        m.geom_friction[:] = friction

        # position actuators: gainprm[0]=kp, biasprm[1]=-kp, biasprm[2]=-kv
        kp = self._uniform(cfg.kp_scale, m.nu)
        kd = self._uniform(cfg.kd_scale, m.nu)
        m.actuator_gainprm[:, 0] = n["gainprm"][:, 0] * kp
        m.actuator_biasprm[:, 1] = n["biasprm"][:, 1] * kp
        m.actuator_biasprm[:, 2] = n["biasprm"][:, 2] * kd
        m.actuator_forcerange[:] = n["forcerange"] * self._uniform(
            cfg.torque_scale, m.nu)[:, None]

        m.dof_frictionloss[:] = n["frictionloss"] * self._uniform(cfg.joint_friction_scale, m.nv)
        m.dof_armature[:] = n["armature"] * self._uniform(cfg.armature_scale, m.nv)

        self.action_latency = float(self._uniform(cfg.action_latency))
        self.joint_bias = self.rng.uniform(-cfg.joint_bias, cfg.joint_bias, spec.NUM_JOINTS)
        self.next_push_time = time_now + float(self._uniform(cfg.push_interval))

    def observation_noise(self, kind: str, size: int) -> np.ndarray:
        if not self.cfg.enabled:
            return np.zeros(size)
        scale = {
            "joint_pos": self.cfg.joint_pos_noise,
            "joint_vel": self.cfg.joint_vel_noise,
            "gyro": self.cfg.gyro_noise,
            "gravity": self.cfg.gravity_noise,
            "object_pos": self.cfg.object_pos_noise,
        }[kind]
        return self.rng.normal(0.0, scale, size)

    def maybe_push(self, data, time_now: float) -> bool:
        """Shove the base at random intervals so the policy learns to recover."""
        if not self.cfg.enabled or time_now < self.next_push_time:
            return False
        direction = self.rng.normal(size=2)
        norm = float(np.linalg.norm(direction))
        if norm > 1e-6:
            direction /= norm
        data.qvel[0:2] += direction * self.rng.uniform(0.0, self.cfg.push_velocity)
        self.next_push_time = time_now + float(self._uniform(self.cfg.push_interval))
        return True
