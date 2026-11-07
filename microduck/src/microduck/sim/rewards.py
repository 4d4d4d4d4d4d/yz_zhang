"""Reward terms for the walking task.

Each term is computed separately and returned in a dict so training logs show
which one is driving behaviour -- when a gait comes out wrong it is almost
always visible as one term dominating the sum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..model import spec


@dataclass
class RewardConfig:
    # Task.
    lin_vel_tracking: float = 2.0
    ang_vel_tracking: float = 1.0
    lin_vel_sigma: float = 0.16
    ang_vel_sigma: float = 0.5

    # Posture.
    upright: float = 0.6
    base_height: float = 0.6
    target_height: float = 0.145
    orientation: float = -1.0

    # Regularisation.  This is what keeps the policy deployable: a gait that
    # scores well but chatters the servos will not survive on hardware.
    action_rate: float = -0.012
    torque: float = -0.0004
    joint_vel: float = -2.0e-4
    joint_acc: float = -2.5e-7
    joint_limit: float = -1.0
    vertical_vel: float = -0.6
    head_stability: float = -0.15

    # Gait shaping.
    feet_air_time: float = 1.2
    target_air_time: float = 0.28
    feet_slip: float = -0.20
    stand_still: float = -0.5

    alive: float = 0.5
    termination: float = -6.0


DEFAULT_REWARDS = RewardConfig()

_LEG_IDX = np.array([spec.JOINT_NAMES.index(n) for n in spec.LEG_JOINT_NAMES])
_LOWER, _UPPER = (np.array(a) for a in spec.joint_limits())
_LIMIT_MARGIN = 0.05
_SOFT_LOWER = _LOWER + _LIMIT_MARGIN * (_UPPER - _LOWER)
_SOFT_UPPER = _UPPER - _LIMIT_MARGIN * (_UPPER - _LOWER)


def locomotion_terms(cfg: RewardConfig, obs: dict) -> dict[str, float]:
    """Posture, regularisation and gait terms shared by every task.

    The fetch task reuses these unchanged and adds its own task terms on top,
    so a policy that learns to fetch cannot do it by flailing.
    """
    terms = {
        "upright": cfg.upright * float(-obs["projected_gravity"][2]),
        "orientation": cfg.orientation * float(np.sum(obs["projected_gravity"][:2] ** 2)),
        "vertical_vel": cfg.vertical_vel * float(obs["base_lin_vel"][2] ** 2),
        "action_rate": cfg.action_rate * float(np.sum((obs["action"] - obs["prev_action"]) ** 2)),
        "torque": cfg.torque * float(np.sum(obs["torques"] ** 2)),
        "joint_vel": cfg.joint_vel * float(np.sum(obs["joint_vel"] ** 2)),
        "joint_acc": cfg.joint_acc * float(np.sum(obs["joint_acc"] ** 2)),
        # The head carries the camera; a policy that whips it around is useless
        # for any downstream vision task even if it walks well.
        "head_stability": cfg.head_stability * float(np.sum(obs["head_ang_vel"] ** 2)),
        "alive": cfg.alive,
    }
    over = np.clip(obs["joint_pos"] - _SOFT_UPPER, 0.0, None)
    under = np.clip(_SOFT_LOWER - obs["joint_pos"], 0.0, None)
    terms["joint_limit"] = cfg.joint_limit * float(np.sum(over + under))
    terms["feet_slip"] = cfg.feet_slip * float(np.sum(obs["feet_contact"] * obs["feet_speed"] ** 2))
    if obs["terminated"]:
        terms["termination"] = cfg.termination
    return terms


def compute(cfg: RewardConfig, obs: dict, dt: float) -> dict[str, float]:
    """Full walking reward: velocity tracking plus the shared terms."""
    cmd = obs["command"]
    lin_err = np.sum((cmd[:2] - obs["base_lin_vel"][:2]) ** 2)
    ang_err = (cmd[2] - obs["base_ang_vel"][2]) ** 2

    terms = locomotion_terms(cfg, obs)
    terms["lin_vel_tracking"] = cfg.lin_vel_tracking * float(np.exp(-lin_err / cfg.lin_vel_sigma))
    terms["ang_vel_tracking"] = cfg.ang_vel_tracking * float(np.exp(-ang_err / cfg.ang_vel_sigma))
    terms["base_height"] = cfg.base_height * float(
        np.exp(-((obs["base_height"] - cfg.target_height) ** 2) / 0.0008))

    if float(np.linalg.norm(cmd)) > 0.05:
        # Credit each footfall by how close its swing was to the target; this
        # is what produces steps rather than a shuffle.
        credit = np.sum(obs["feet_just_landed"]
                        * (cfg.target_air_time - np.abs(obs["feet_air_time"] - cfg.target_air_time)))
        terms["feet_air_time"] = cfg.feet_air_time * float(credit)
        terms["stand_still"] = 0.0
    else:
        terms["feet_air_time"] = 0.0
        # Told to hold still, holding still is the task.
        terms["stand_still"] = cfg.stand_still * float(
            np.sum(np.abs(obs["joint_pos"][_LEG_IDX] - obs["default_pos"][_LEG_IDX])))
    return terms
