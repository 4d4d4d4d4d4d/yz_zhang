"""Phase-driven reference gait.

Two jobs:

* it supplies the clock (``sin``/``cos`` of the gait phase) the RL policy sees,
  which is what keeps a learned walk from degenerating into a shuffle; and
* it doubles as a scripted open-loop controller, so a fresh clone can make the
  duck walk before anything has been trained.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..model import spec
from . import kinematics


@dataclass
class GaitParams:
    frequency: float = 2.98           # cycles per second
    #: Hip-to-sole distance when standing still.  Taken from the spec's pose so
    #: a zero command reproduces that pose exactly.
    stand_depth: float = kinematics.default_stand_depth()
    #: Hip-to-sole distance while walking.  A slightly deeper crouch than
    #: standing: it lowers the centre of mass and buys swing clearance.
    walk_depth: float = 0.092
    #: Fore/aft sole offset when standing, taken from the spec's pose.
    stand_offset_x: float = kinematics.default_stand_sole()[0]
    step_height: float = 0.026        # peak swing lift, m
    stride_gain: float = 0.41         # m of stride per (m/s) commanded
    lateral_gain: float = 0.10
    sway: float = 0.16                # hip roll amplitude, rad
    #: Where in the cycle the weight shift peaks.  Both hips roll *together*:
    #: rolling them the same way translates the pelvis sideways, whereas
    #: mirroring them only splays the feet and shifts no weight at all.
    sway_phase: float = 0.08
    yaw_gain: float = 0.22            # hip yaw per (rad/s) commanded
    duty: float = 0.65                # fraction of the cycle a leg is grounded
    crouch: float = 0.0               # vertical bob amplitude, m


DEFAULT_PARAMS = GaitParams()


def phase_signal(phase: float) -> tuple[float, float]:
    """The two-element clock the policy observes."""
    return math.sin(2 * math.pi * phase), math.cos(2 * math.pi * phase)


def leg_phase(phase: float, side: str) -> float:
    """Per-leg phase; the right leg is half a cycle behind the left."""
    return (phase + (0.0 if side == "left" else 0.5)) % 1.0


def swing_state(value: float, duty: float) -> tuple[bool, float]:
    """``(in_swing, s)`` with ``s`` running 0->1 across the current sub-phase."""
    if value < duty:
        return False, value / duty
    return True, (value - duty) / (1.0 - duty)


class ScriptedGait:
    """Open-loop walking controller.

    Returns a full 15-joint target vector for a velocity command.  It is not a
    learned policy and will not survive a shove, but on flat ground it walks,
    turns and stands -- a useful baseline and a smoke test for the whole stack.
    """

    def __init__(self, params: GaitParams | None = None) -> None:
        self.params = params or GaitParams()
        self.phase = 0.0
        self._default = spec.default_pose()
        self._index = {name: i for i, name in enumerate(spec.JOINT_NAMES)}

    def reset(self) -> None:
        self.phase = 0.0

    def step(self, command: tuple[float, float, float], dt: float) -> list[float]:
        if abs(command[0]) + abs(command[1]) + abs(command[2]) > 1e-3:
            self.phase = (self.phase + self.params.frequency * dt) % 1.0
        else:
            self.phase = 0.0
        return self.targets(command)

    def targets(self, command: tuple[float, float, float]) -> list[float]:
        vx, vy, wz = command
        p = self.params
        targets = list(self._default)
        moving = abs(vx) + abs(vy) + abs(wz) > 1e-3

        for side, mirror in (("left", 1.0), ("right", -1.0)):   # mirror: yaw only
            in_swing, s = swing_state(leg_phase(self.phase, side), p.duty)
            if moving:
                # The foot travels forward through swing and back through
                # stance, so the body advances at the commanded speed.
                travel = (s - 0.5) if in_swing else (0.5 - s)
                x = p.stand_offset_x + vx * p.stride_gain * travel
                y_shift = vy * p.lateral_gain * travel
                lift = p.step_height * math.sin(math.pi * s) if in_swing else 0.0
                depth = p.walk_depth - lift + p.crouch * math.cos(4 * math.pi * self.phase)
                roll = p.sway * math.sin(2 * math.pi * (self.phase + p.sway_phase))
                yaw = mirror * wz * p.yaw_gain * travel
            else:
                x, y_shift, depth, roll, yaw = p.stand_offset_x, 0.0, p.stand_depth, 0.0, 0.0

            hip_pitch, knee, ankle = kinematics.inverse(x, -depth)
            self._set(targets, f"{side}_hip_pitch", hip_pitch)
            self._set(targets, f"{side}_knee", knee)
            self._set(targets, f"{side}_ankle_pitch", ankle)
            self._set(targets, f"{side}_hip_roll", roll + y_shift * 2.0)
            self._set(targets, f"{side}_hip_yaw", yaw)

        if moving:   # a little head bob and tail wag; also exercises the aux servos
            self._set(targets, "neck_pitch", self._default[self._index["neck_pitch"]]
                      + 0.05 * math.sin(2 * math.pi * self.phase))
            self._set(targets, "tail", self._default[self._index["tail"]]
                      + 0.12 * math.sin(2 * math.pi * self.phase))
        return targets

    def _set(self, targets: list[float], name: str, value: float) -> None:
        low, high = spec.JOINT_BY_NAME[name].range
        targets[self._index[name]] = min(high, max(low, value))
