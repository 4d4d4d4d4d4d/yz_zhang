"""The model has to stay consistent with the spec, and the duck has to stand."""

import mujoco
import numpy as np
import pytest

from microduck.model import spec
from microduck.model.builder import FETCH_MODEL_PATH, MODEL_PATH, to_xml
from microduck.sim import kinematics


def test_spec_is_self_consistent():
    assert spec.NUM_JOINTS == 15
    assert len(spec.JOINT_NAMES) == len(set(spec.JOINT_NAMES))
    # Every joint's parent and child must be a real link, and every joint must
    # drive a distinct body, or the MJCF tree is malformed.
    children = [j.child for j in spec.JOINTS]
    assert len(children) == len(set(children))
    for joint in spec.JOINTS:
        assert joint.parent in spec.LINK_BY_NAME, joint.name
        assert joint.child in spec.LINK_BY_NAME, joint.name
        low, high = joint.range
        assert low < high
        assert low <= joint.default <= high, joint.name


def test_committed_xml_matches_generator():
    """The XML is generated; a stale commit would silently change the robot."""
    assert MODEL_PATH.read_text() == to_xml(False)
    assert FETCH_MODEL_PATH.read_text() == to_xml(True)


@pytest.mark.parametrize("path", [MODEL_PATH, FETCH_MODEL_PATH])
def test_model_loads_with_expected_shape(path):
    model = mujoco.MjModel.from_xml_path(str(path))
    assert model.nu == spec.NUM_JOINTS
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
             for i in range(model.nu)]
    # Actuator order is the contract between the policy, the runtime and the
    # servo bus; it must match the canonical list exactly.
    assert names == list(spec.JOINT_NAMES)
    assert 0.6 < model.body_subtreemass[1] < 0.95


def test_total_mass_near_spec():
    assert abs(sum(link.mass for link in spec.LINKS) - spec.TOTAL_MASS) < 0.05


def test_default_pose_is_fixed_point_of_ik():
    """The standing pose must be exactly what the IK produces for it.

    If these drift apart, a zero action no longer means "stand", and every
    policy's action space is quietly offset.
    """
    j = spec.JOINT_BY_NAME
    hip, knee, ankle = kinematics.inverse(
        *kinematics.forward(j["left_hip_pitch"].default, j["left_knee"].default))
    assert hip == pytest.approx(j["left_hip_pitch"].default, abs=1e-6)
    assert knee == pytest.approx(j["left_knee"].default, abs=1e-6)
    assert ankle == pytest.approx(j["left_ankle_pitch"].default, abs=1e-6)


def test_ik_round_trips_across_workspace():
    for x in (-0.03, 0.0, 0.02):
        for depth in (0.07, 0.09, 0.10):
            hip, knee, _ankle = kinematics.inverse(x, -depth)
            fx, fz = kinematics.forward(hip, knee)
            assert fx == pytest.approx(x, abs=1e-6)
            assert fz == pytest.approx(-depth, abs=1e-6)


def test_ik_clamps_unreachable_targets_without_nan():
    for target in ((0.0, -0.5), (0.4, -0.01), (0.0, 0.0)):
        angles = kinematics.inverse(*target)
        assert all(np.isfinite(a) for a in angles)


def test_duck_stands_at_default_pose():
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    pose = spec.default_pose()
    data.qpos[2] = spec.NOMINAL_STANDING_HEIGHT
    data.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
    data.qpos[7:] = pose
    data.ctrl[:] = pose
    for _ in range(1500):      # 3 seconds
        data.ctrl[:] = pose
        mujoco.mj_step(model, data)
    assert data.qpos[2] > 0.13, "the duck sagged or fell while holding its pose"
    assert np.linalg.norm(data.qvel[:3]) < 0.02


def test_beak_default_is_off_its_hard_stop():
    """A closed beak must not sit inside the joint-limit penalty band.

    It did once, and it charged every policy a per-step penalty for keeping its
    beak shut -- which is the beak's resting state.
    """
    from microduck.sim.rewards import _SOFT_LOWER, _SOFT_UPPER

    defaults = np.array(spec.default_pose())
    inside = (defaults >= _SOFT_LOWER) & (defaults <= _SOFT_UPPER)
    offenders = [n for n, ok in zip(spec.JOINT_NAMES, inside) if not ok]
    assert not offenders, f"default pose is inside the limit penalty band: {offenders}"
