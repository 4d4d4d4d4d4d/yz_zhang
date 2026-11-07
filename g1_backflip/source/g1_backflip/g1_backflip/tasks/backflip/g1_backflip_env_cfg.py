"""Configuration of the Unitree G1 backflip task.

The task is phase driven: every episode is exactly one backflip attempt.
A hand-designed reference (pelvis height + pitch angle as a function of time)
is tracked by the policy, see ``G1BackflipEnv._reference``.

Timeline (seconds since reset, all editable below):
    0.00 - 0.35  crouch
    0.35 - 0.55  push off (upward velocity reward window)
    0.45 - 1.25  rotate backwards by 2*pi (smoothstep profile)
    0.55 - 1.15  flight
    1.15 - 1.45  landing / absorbing
    1.45 - 2.50  stand still
"""

from __future__ import annotations

import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg
from isaaclab.envs import DirectRLEnvCfg, ViewerCfg
from isaaclab.envs import mdp
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.sim import PhysxCfg, SimulationCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass

from isaaclab_assets.robots.unitree import G1_MINIMAL_CFG  # isort: skip


@configclass
class EventCfg:
    """Domain randomization."""

    physics_material = EventTerm(
        func=mdp.randomize_rigid_body_material,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*"),
            "static_friction_range": (0.6, 1.2),
            "dynamic_friction_range": (0.5, 1.0),
            "restitution_range": (0.0, 0.1),
            "num_buckets": 64,
        },
    )

    torso_mass = EventTerm(
        func=mdp.randomize_rigid_body_mass,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="torso_link"),
            "mass_distribution_params": (-1.0, 2.0),
            "operation": "add",
        },
    )


@configclass
class RewardsCfg:
    """Reward weights (dense terms are multiplied by step_dt)."""

    # --- reference tracking ---
    pitch_track = 3.0  # integrated pitch angle vs reference (handles full 2*pi)
    orient_track = 2.0  # full orientation (quaternion) vs reference -> also kills roll / yaw
    ang_vel_track = 1.0  # pitch rate vs reference
    height_track = 1.0  # pelvis height vs reference
    # --- shaping for exploration ---
    spin_bonus = 0.15  # linear bonus for spinning backwards inside the flip window
    takeoff_vel = 0.5  # linear bonus for upward velocity during push off
    # --- landing / standing ---
    feet_contact_land = 1.0
    stand_still = 1.0
    default_pose_land = 0.5
    # --- regularization (negative) ---
    lateral_ang_vel = -0.05
    lateral_drift = -1.0
    leg_symmetry = -0.5
    action_rate = -0.01
    joint_torque = -1.0e-5
    joint_acc = -2.5e-7
    joint_pos_limit = -5.0
    # --- events ---
    termination = -10.0


@configclass
class G1BackflipEnvCfg(DirectRLEnvCfg):
    # ----------------------------------------------------------------- env
    episode_length_s = 2.5
    decimation = 4  # 200 Hz physics / 50 Hz policy
    action_scale = 0.5
    action_clip = 3.0
    # legs(12) + torso(1) + arms(10) = 23 ; fingers are held at default
    controlled_joints = [
        ".*_hip_pitch_joint",
        ".*_hip_roll_joint",
        ".*_hip_yaw_joint",
        ".*_knee_joint",
        ".*_ankle_pitch_joint",
        ".*_ankle_roll_joint",
        "torso_joint",
        ".*_shoulder_pitch_joint",
        ".*_shoulder_roll_joint",
        ".*_shoulder_yaw_joint",
        ".*_elbow_pitch_joint",
        ".*_elbow_roll_joint",
    ]
    action_space = 23
    # lin_vel(3)+ang_vel(3)+gravity(3)+height(1)+q(23)+dq(23)+last_a(23)+phase(5)
    observation_space = 84
    state_space = 0

    # ----------------------------------------------------------- reference
    stand_height = 0.74
    height_keyframes_t = (0.00, 0.35, 0.55, 0.85, 1.15, 1.45, 10.0)
    height_keyframes_z = (0.74, 0.55, 0.85, 1.25, 0.85, 0.72, 0.74)
    flip_start_t = 0.45
    flip_end_t = 1.25
    takeoff_window = (0.35, 0.60)
    land_t = 1.45

    # tracking kernel widths
    sigma_pitch = 1.0  # rad
    sigma_orient = 0.6  # rad
    sigma_ang_vel = 4.0  # rad/s
    sigma_height = 0.15  # m

    # ---------------------------------------------------------- terminations
    max_orient_err = 1.8  # rad, terminate if far from reference (set to 10 to disable)
    min_base_height = 0.25
    contact_force_threshold = 1.0
    termination_bodies = ["pelvis", "torso_link"]
    feet_bodies = ".*_ankle_roll_link"

    # --------------------------------------------------------------- sim
    sim: SimulationCfg = SimulationCfg(
        dt=1 / 200,
        render_interval=decimation,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
            restitution=0.0,
        ),
        physx=PhysxCfg(gpu_max_rigid_patch_count=10 * 2**15),
    )
    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="plane",
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
            restitution=0.0,
        ),
        debug_vis=False,
    )

    # ------------------------------------------------------------- scene
    # 2048 envs fit comfortably on an RTX 3060 12GB in headless mode.
    scene: InteractiveSceneCfg = InteractiveSceneCfg(num_envs=2048, env_spacing=3.0, replicate_physics=True)

    robot: ArticulationCfg = G1_MINIMAL_CFG.replace(prim_path="/World/envs/env_.*/Robot")
    contact_sensor: ContactSensorCfg = ContactSensorCfg(
        prim_path="/World/envs/env_.*/Robot/.*", history_length=3, update_period=0.0, track_air_time=True
    )

    events: EventCfg = EventCfg()
    rewards: RewardsCfg = RewardsCfg()

    # side view so the flip is visible in the GUI / videos
    viewer: ViewerCfg = ViewerCfg(eye=(0.5, 4.5, 1.4), lookat=(0.0, 0.0, 0.8), origin_type="env", env_index=0)


@configclass
class G1BackflipEnvCfg_PLAY(G1BackflipEnvCfg):
    def __post_init__(self):
        self.scene.num_envs = 16
        self.scene.env_spacing = 3.0
        self.events.torso_mass = None
