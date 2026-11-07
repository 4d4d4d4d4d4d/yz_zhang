"""Planar leg kinematics.

Only the sagittal chain (hip pitch -> knee -> ankle pitch) needs closed-form
kinematics: it is what places the foot during a step and what lowers the body
when the duck bends down to the ball.  Hip yaw/roll are small corrections on
top.

Sign convention, matching the MJCF: all three joints turn about +y, with every
angle at zero the leg points straight down, and a positive rotation swings the
foot towards -x (backwards).
"""

from __future__ import annotations

import math

from ..model import spec

L_THIGH = spec.THIGH_LENGTH
L_SHIN = spec.SHIN_LENGTH
#: Ankle joint to sole, so targets can be given in sole coordinates.
SOLE_OFFSET = spec.FOOT_HEIGHT / 2

MIN_REACH = 0.030
#: The sole offset is part of the lower segment, so it counts towards reach.
MAX_REACH = L_THIGH + L_SHIN + SOLE_OFFSET - 0.004


def forward(hip_pitch: float, knee: float) -> tuple[float, float]:
    """Sole position (x, z) in the hip frame, metres."""
    knee_x = -L_THIGH * math.sin(hip_pitch)
    knee_z = -L_THIGH * math.cos(hip_pitch)
    shin = hip_pitch + knee
    lower = L_SHIN + SOLE_OFFSET
    return knee_x - lower * math.sin(shin), knee_z - lower * math.cos(shin)


def inverse(x: float, z: float) -> tuple[float, float, float]:
    """Hip pitch, knee and ankle pitch placing the sole at ``(x, z)``.

    ``z`` is negative (below the hip).  The ankle angle keeps the sole parallel
    to the ground, which is what the gait and the spec's default pose assume.
    """
    lower = L_SHIN + SOLE_OFFSET
    reach = min(max(math.hypot(x, z), MIN_REACH), MAX_REACH)
    cos_interior = (L_THIGH ** 2 + lower ** 2 - reach ** 2) / (2 * L_THIGH * lower)
    interior = math.acos(min(1.0, max(-1.0, cos_interior)))
    knee = math.pi - interior
    line = math.atan2(-x, -z)
    beta = math.asin(min(1.0, max(-1.0, lower * math.sin(interior) / reach)))
    hip_pitch = line - beta
    return hip_pitch, knee, -(hip_pitch + knee)


def default_stand_sole() -> tuple[float, float]:
    """Sole position implied by :func:`microduck.model.spec.default_pose`."""
    j = spec.JOINT_BY_NAME
    return forward(j["left_hip_pitch"].default, j["left_knee"].default)


def default_stand_depth() -> float:
    return -default_stand_sole()[1]
