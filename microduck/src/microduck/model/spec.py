"""Physical specification of the Microduck.

Single source of truth for the robot: every link, joint, actuator and sensor is
plain data here, and ``builder.py`` turns it into MJCF.  Keeping the numbers in
Python rather than hand-edited XML means the simulation, the runtime joint
tables and the exported policy can never drift apart.

Figures follow the published Microduck: a ~25 cm biped weighing just under
800 g, 15 serial-bus servos, a wide-angle camera, an 8x8 ToF sensor and two
IMUs.  It walks, picks objects up with its beak, and gets back up when it falls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Axis = tuple[float, float, float]
Vec3 = tuple[float, float, float]

TOTAL_HEIGHT = 0.25           # m, standing, beak tip excluded
TOTAL_MASS = 0.78             # kg, battery included
NOMINAL_STANDING_HEIGHT = 0.155   # m, torso origin above ground when standing

SIM_TIMESTEP = 0.002          # 500 Hz physics
CONTROL_DECIMATION = 10       # -> 50 Hz policy, matching the on-robot runtime
CONTROL_DT = SIM_TIMESTEP * CONTROL_DECIMATION


@dataclass(frozen=True)
class Servo:
    """A serial-bus servo.  Its gearbox limits are what the PD loop must respect."""

    name: str
    kp: float
    kd: float
    max_torque: float      # N.m
    max_velocity: float    # rad/s
    armature: float        # rotor inertia through the gearbox, kg.m^2
    frictionloss: float = 0.01


#: Legs carry the body weight and use the larger gearbox; head, beak and tail
#: use the small one.
LEG_SERVO = Servo("sts3215", kp=12.0, kd=0.45, max_torque=1.6,
                  max_velocity=12.0, armature=6.0e-4, frictionloss=0.012)
AUX_SERVO = Servo("sts3032", kp=6.0, kd=0.22, max_torque=0.5,
                  max_velocity=14.0, armature=2.0e-4, frictionloss=0.006)


@dataclass(frozen=True)
class Joint:
    """One actuated degree of freedom.  ``parent -> child`` is one tree edge."""

    name: str
    parent: str
    child: str
    axis: Axis
    origin: Vec3                      # in the parent body frame
    range: tuple[float, float]
    default: float                    # standing pose; also the action-space zero
    servo: Servo
    group: Literal["leg", "head", "face"]


@dataclass(frozen=True)
class Link:
    """A rigid body.  Geometry is one capsule or box primitive."""

    name: str
    mass: float
    shape: tuple                      # ("capsule", from, to, r) | ("box", half_size)
    rgba: tuple[float, float, float, float] = (0.98, 0.78, 0.15, 1.0)
    #: Only the feet and the beak jaws collide with anything.
    contype: int = 0
    conaffinity: int = 0
    #: Offset of the geometry from the body origin.
    offset: Vec3 = (0.0, 0.0, 0.0)


HIP_SEPARATION = 0.035        # half-distance between the hip yaw axes
THIGH_LENGTH = 0.052
SHIN_LENGTH = 0.055
FOOT_LENGTH = 0.052
FOOT_WIDTH = 0.030
FOOT_HEIGHT = 0.010

#: Gap between the jaws when the beak joint is fully open, m.  Sized so the
#: 35 mm task ball fits between them.
BEAK_OPEN_GAP = 0.042
BEAK_LENGTH = 0.024

BODY_LINKS: tuple[Link, ...] = (
    Link("torso", 0.240, ("capsule", (0.0, 0.0, -0.030), (0.0, 0.0, 0.034), 0.043)),
    Link("neck", 0.028, ("capsule", (0.0, 0.0, 0.0), (0.0, 0.0, 0.030), 0.012),
         rgba=(0.95, 0.72, 0.12, 1.0)),
    Link("head_gimbal", 0.018, ("capsule", (0.0, -0.010, 0.0), (0.0, 0.010, 0.0), 0.011),
         rgba=(0.95, 0.72, 0.12, 1.0)),
    Link("head", 0.064, ("capsule", (0.0, -0.008, 0.010), (0.0, 0.012, 0.010), 0.028)),
    # Two jaws, so the beak is a real gripper.  The lower jaw is rigid with the
    # head (as in a bird); the upper jaw is the one the servo drives.
    Link("lower_beak", 0.008, ("box", (BEAK_LENGTH / 2, 0.011, 0.0035)),
         rgba=(0.95, 0.45, 0.10, 1.0), contype=1, conaffinity=1),
    Link("upper_beak", 0.010, ("box", (BEAK_LENGTH / 2, 0.012, 0.0035)),
         rgba=(0.95, 0.45, 0.10, 1.0), contype=1, conaffinity=1,
         offset=(BEAK_LENGTH / 2, 0.0, 0.0)),
    Link("tail", 0.014, ("box", (0.022, 0.016, 0.005)), rgba=(0.95, 0.72, 0.12, 1.0)),
)


def _leg_links(side: str) -> tuple[Link, ...]:
    return (
        Link(f"{side}_hip_yoke", 0.030,
             ("capsule", (0.0, 0.0, 0.0), (0.0, 0.0, -0.014), 0.015)),
        Link(f"{side}_hip_bracket", 0.026,
             ("capsule", (0.0, -0.012, 0.0), (0.0, 0.012, 0.0), 0.014)),
        Link(f"{side}_thigh", 0.058,
             ("capsule", (0.0, 0.0, 0.0), (0.0, 0.0, -THIGH_LENGTH), 0.013)),
        Link(f"{side}_shin", 0.046,
             ("capsule", (0.0, 0.0, 0.0), (0.0, 0.0, -SHIN_LENGTH), 0.011)),
        Link(f"{side}_foot", 0.040,
             ("box", (FOOT_LENGTH / 2, FOOT_WIDTH / 2, FOOT_HEIGHT / 2)),
             rgba=(0.95, 0.45, 0.10, 1.0), contype=1, conaffinity=1),
    )


LINKS: tuple[Link, ...] = BODY_LINKS + _leg_links("left") + _leg_links("right")


def _leg_joints(side: str, sign: float) -> tuple[Joint, ...]:
    """Five DoF per leg: hip yaw/roll/pitch, knee, ankle pitch.

    ``sign`` is +1 for the left leg and -1 for the right and mirrors the
    lateral offsets.  All sagittal joints turn about +y, and with every angle
    at zero the leg points straight down.
    """
    return (
        Joint(f"{side}_hip_yaw", "torso", f"{side}_hip_yoke", (0, 0, 1),
              (0.0, sign * HIP_SEPARATION, -0.030), (-0.7, 0.7), 0.0, LEG_SERVO, "leg"),
        Joint(f"{side}_hip_roll", f"{side}_hip_yoke", f"{side}_hip_bracket", (1, 0, 0),
              (0.0, 0.0, -0.014), (-0.5, 0.5), 0.0, LEG_SERVO, "leg"),
        Joint(f"{side}_hip_pitch", f"{side}_hip_bracket", f"{side}_thigh", (0, 1, 0),
              (0.0, 0.0, 0.0), (-1.4, 1.4), -0.32, LEG_SERVO, "leg"),
        Joint(f"{side}_knee", f"{side}_thigh", f"{side}_shin", (0, 1, 0),
              (0.0, 0.0, -THIGH_LENGTH), (0.0, 2.2), 0.72, LEG_SERVO, "leg"),
        Joint(f"{side}_ankle_pitch", f"{side}_shin", f"{side}_foot", (0, 1, 0),
              (0.0, 0.0, -SHIN_LENGTH), (-1.2, 1.0), -0.40, LEG_SERVO, "leg"),
    )


HEAD_JOINTS: tuple[Joint, ...] = (
    Joint("neck_yaw", "torso", "neck", (0, 0, 1), (0.006, 0.0, 0.034),
          (-1.6, 1.6), 0.0, AUX_SERVO, "head"),
    # The neck must pitch far enough down for the beak to reach the floor.
    Joint("neck_pitch", "neck", "head_gimbal", (0, 1, 0), (0.0, 0.0, 0.030),
          (-0.9, 1.7), -0.10, AUX_SERVO, "head"),
    Joint("head_roll", "head_gimbal", "head", (1, 0, 0), (0.0, 0.0, 0.0),
          (-0.6, 0.6), 0.0, AUX_SERVO, "head"),
)

FACE_JOINTS: tuple[Joint, ...] = (
    #: 0 = jaws closed, positive = open.  The gripper that picks the ball up.
    Joint("beak", "head", "upper_beak", (0, 1, 0), (0.022, 0.0, 0.004),
          (0.0, 1.0), 0.0, AUX_SERVO, "face"),
    Joint("tail", "torso", "tail", (0, 1, 0), (-0.040, 0.0, 0.012),
          (-0.5, 0.5), 0.10, AUX_SERVO, "face"),
)

JOINTS: tuple[Joint, ...] = (
    _leg_joints("left", 1.0) + _leg_joints("right", -1.0) + HEAD_JOINTS + FACE_JOINTS
)

#: Canonical ordering.  The runtime, the exported policy and the servo bus all
#: index joints with this list, so it must never be reordered casually.
JOINT_NAMES: tuple[str, ...] = tuple(j.name for j in JOINTS)
NUM_JOINTS = len(JOINT_NAMES)
LEG_JOINT_NAMES: tuple[str, ...] = tuple(j.name for j in JOINTS if j.group == "leg")
HEAD_JOINT_NAMES: tuple[str, ...] = tuple(j.name for j in JOINTS if j.group != "leg")
JOINT_BY_NAME: dict[str, Joint] = {j.name: j for j in JOINTS}
LINK_BY_NAME: dict[str, Link] = {ln.name: ln for ln in LINKS}
BEAK_INDEX = JOINT_NAMES.index("beak")
NECK_PITCH_INDEX = JOINT_NAMES.index("neck_pitch")


def default_pose() -> list[float]:
    return [j.default for j in JOINTS]


def joint_limits() -> tuple[list[float], list[float]]:
    return [j.range[0] for j in JOINTS], [j.range[1] for j in JOINTS]


@dataclass(frozen=True)
class SensorSpec:
    """Onboard sensing, mirroring the real bill of materials."""

    imu_sites: tuple[str, ...] = ("torso_imu", "head_imu")
    camera_site: str = "head_camera"
    camera_fovy: float = 110.0                 # wide-angle
    lidar_site: str = "head_lidar"
    lidar_resolution: tuple[int, int] = (8, 8)
    lidar_fov: float = 63.0                    # VL53L5CX-class ToF
    lidar_max_range: float = 4.0               # m


SENSORS = SensorSpec()


@dataclass(frozen=True)
class ActuationConfig:
    """How policy actions become joint targets."""

    action_scale: float = 0.35      # radians of residual per unit action
    action_clip: float = 3.0        # one bad inference cannot command a full swing
    command_latency: float = 0.010  # s, servo-bus round trip


ACTUATION = ActuationConfig()


def describe() -> str:
    lines = [
        f"Microduck  |  {NUM_JOINTS} DoF  |  {TOTAL_MASS:.2f} kg  |  {TOTAL_HEIGHT * 100:.0f} cm",
        f"control {1 / CONTROL_DT:.0f} Hz over physics {1 / SIM_TIMESTEP:.0f} Hz",
        "",
        f"{'joint':<18}{'group':<7}{'range (rad)':<22}{'default':>8}",
    ]
    for j in JOINTS:
        lines.append(f"{j.name:<18}{j.group:<7}"
                     f"{f'[{j.range[0]:+.2f}, {j.range[1]:+.2f}]':<22}{j.default:>+8.2f}")
    lines += ["", f"sum of link masses: {sum(ln.mass for ln in LINKS):.3f} kg"]
    return "\n".join(lines)
