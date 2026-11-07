"""Environment contracts: shapes, determinism, termination, reward sanity."""

import numpy as np
import pytest

from microduck.model import spec
from microduck.sim.env import OBS_DIM, EnvConfig, MicroduckEnv, assemble_observation
from microduck.sim.fetch_env import (FETCH_OBS_DIM, FetchConfig, MicroduckFetchEnv,
                                     Phase)
from microduck.sim.gait import ScriptedGait
from microduck.sim.randomization import RandomizationConfig


def nominal(config_cls):
    cfg = config_cls()
    cfg.randomization = RandomizationConfig(enabled=False)
    return cfg


@pytest.mark.parametrize("env_cls,config_cls,dim",
                         [(MicroduckEnv, EnvConfig, OBS_DIM),
                          (MicroduckFetchEnv, FetchConfig, FETCH_OBS_DIM)])
def test_observation_shape_and_finiteness(env_cls, config_cls, dim):
    env = env_cls(config_cls(), seed=0)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (dim,)
    assert obs.dtype == np.float32
    for _ in range(60):
        obs, reward, terminated, truncated, info = env.step(
            np.random.uniform(-0.5, 0.5, env.action_dim))
        assert np.all(np.isfinite(obs))
        assert np.isfinite(reward)
        if terminated or truncated:
            break


def test_fetch_observation_extends_walk_observation():
    """The fetch layout must keep the walking channels first, in order.

    Warm-starting a fetch policy from a walking checkpoint depends on it.
    """
    from microduck.sim.env import OBS_LAYOUT
    from microduck.sim.fetch_env import FETCH_OBS_LAYOUT

    assert FETCH_OBS_LAYOUT[:len(OBS_LAYOUT)] == OBS_LAYOUT
    assert FETCH_OBS_DIM > OBS_DIM


def test_assemble_observation_rejects_wrong_sizes():
    from microduck.sim.env import OBS_LAYOUT

    channels = {name: np.zeros(size) for name, size in OBS_LAYOUT}
    channels["command"] = np.zeros(2)
    with pytest.raises(ValueError, match="command"):
        assemble_observation(channels)


@pytest.mark.parametrize("env_cls,config_cls",
                         [(MicroduckEnv, EnvConfig), (MicroduckFetchEnv, FetchConfig)])
def test_same_seed_gives_same_trajectory(env_cls, config_cls):
    def rollout():
        env = env_cls(config_cls(), seed=7)
        obs, _ = env.reset(seed=7)
        trace = [obs]
        rng = np.random.default_rng(0)
        for _ in range(40):
            obs, *_ = env.step(rng.uniform(-0.2, 0.2, env.action_dim))
            trace.append(obs)
        return np.stack(trace)

    np.testing.assert_allclose(rollout(), rollout())


def test_zero_action_holds_the_standing_pose():
    env = MicroduckEnv(nominal(EnvConfig), seed=0)
    env.reset(seed=0)
    env.data.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
    for _ in range(200):
        _obs, _r, terminated, _t, info = env.step(np.zeros(env.action_dim))
        assert not terminated
    assert info["height"] > 0.13


def test_termination_on_a_fall():
    env = MicroduckEnv(nominal(EnvConfig), seed=0)
    env.reset(seed=0)
    # Tip the duck right over; it must terminate rather than carry on upside down.
    env.data.qpos[3:7] = (0.0, 0.0, 1.0, 0.0)
    _obs, _r, terminated, _t, _i = env.step(np.zeros(env.action_dim))
    assert terminated


def test_scripted_gait_walks_forward():
    cfg = nominal(EnvConfig)
    cfg.episode_length = 9.0
    env = MicroduckEnv(cfg, seed=1)
    env.reset(seed=1)
    env.data.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
    env.data.qvel[:] = 0.0
    gait = ScriptedGait(cfg.gait)
    default = np.array(spec.default_pose())
    command = (0.15, 0.0, 0.0)
    start = env.data.qpos[:3].copy()
    for _ in range(int(8.0 / env.dt)):
        env.command[:] = command
        targets = np.array(gait.step(command, env.dt))
        _o, _r, terminated, _t, _i = env.step((targets - default) / cfg.action_scale)
        assert not terminated, "the scripted gait fell over"
    assert (env.data.qpos[:3] - start)[0] > 0.3


def test_scripted_gait_standing_reproduces_default_pose():
    gait = ScriptedGait()
    np.testing.assert_allclose(gait.targets((0.0, 0.0, 0.0)), spec.default_pose(),
                               atol=1e-9)


def test_fetch_resets_place_ball_within_configured_range():
    cfg = nominal(FetchConfig)
    env = MicroduckFetchEnv(cfg, seed=3)
    for episode in range(10):
        env.reset(seed=episode)
        distance = np.linalg.norm(env.ball_pos[:2] - env.home_xy)
        assert cfg.ball_distance[0] - 1e-6 <= distance <= cfg.ball_distance[1] + 1e-6
        assert env.phase == Phase.APPROACH
        assert not env.grasped


def test_fetch_curriculum_difficulty_limits_spawn_distance():
    cfg = nominal(FetchConfig)
    cfg.difficulty = 0.0
    env = MicroduckFetchEnv(cfg, seed=0)
    for episode in range(5):
        env.reset(seed=episode)
        distance = np.linalg.norm(env.ball_pos[:2] - env.home_xy)
        assert distance == pytest.approx(cfg.ball_distance[0], abs=1e-6)


def test_fetch_grasp_latches_and_releases():
    """Drive the phase machine directly: closing on the ball must latch a grasp."""
    cfg = nominal(FetchConfig)
    env = MicroduckFetchEnv(cfg, seed=0)
    env.reset(seed=0)

    # Teleport the ball into the beak and close the jaws.
    env.data.qpos[env._ball_qpos:env._ball_qpos + 3] = env.beak_pos
    env.data.qpos[7 + spec.BEAK_INDEX] = 0.0
    import mujoco
    mujoco.mj_forward(env.model, env.data)
    env._post_physics()
    assert env.grasped, "beak closed on the ball but no grasp latched"

    env.data.qpos[7 + spec.BEAK_INDEX] = cfg.beak_open + 0.1
    mujoco.mj_forward(env.model, env.data)
    env._post_physics()
    assert not env.grasped, "beak opened but the grasp did not release"


def test_fetch_rejects_unknown_grasp_mode():
    cfg = FetchConfig()
    cfg.grasp_mode = "magnet"
    with pytest.raises(ValueError, match="grasp_mode"):
        MicroduckFetchEnv(cfg)


def test_doing_nothing_scores_far_below_a_completed_fetch():
    """The task bonuses must dominate the always-on survival reward.

    With the walking task's own weights they do not, and the optimal policy is
    to stand still for the whole episode. This test is the guard on that.
    """
    cfg = nominal(FetchConfig)
    env = MicroduckFetchEnv(cfg, seed=0)
    env.reset(seed=0)
    total = 0.0
    while True:
        _o, reward, terminated, truncated, _i = env.step(np.zeros(env.action_dim))
        total += reward
        if terminated or truncated:
            break
    fetch = cfg.fetch_rewards
    one_time = (fetch.in_range_bonus + fetch.grasp_bonus + fetch.lift_bonus
                + fetch.home_bonus + fetch.success_bonus)
    assert one_time > total, (
        f"a do-nothing episode scores {total:.0f}, but completing the task only "
        f"adds {one_time:.0f} in bonuses")
