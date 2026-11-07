"""Training-stack contracts, including the ones that only bite on 4 GPUs."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from microduck.model import spec
from microduck.rl.networks import ActorCritic, load_transferred_weights
from microduck.rl.ppo import PPO, PPOConfig, RolloutBuffer
from microduck.rl.train import (SHARED_STAT_KEYS, EpisodeStats, TrainConfig,
                                default_num_workers, load_config, make_env_config)
from microduck.sim.env import OBS_DIM
from microduck.sim.fetch_env import FETCH_OBS_DIM

REPO_ROOT = Path(__file__).resolve().parents[1]


def filled_buffer(cfg, obs_dim, action_dim, device, policy):
    buffer = RolloutBuffer(cfg.rollout_steps, cfg.num_envs, obs_dim, action_dim, device)
    for _ in range(cfg.rollout_steps):
        obs = torch.randn(cfg.num_envs, obs_dim)
        action, log_prob, value = policy.act(obs)
        buffer.add(obs, action, log_prob, torch.randn(cfg.num_envs),
                   torch.zeros(cfg.num_envs), value)
    buffer.compute_returns(torch.zeros(cfg.num_envs), cfg.gamma, cfg.gae_lambda)
    return buffer


def test_ppo_update_runs_and_reports_finite_stats():
    cfg = PPOConfig(num_envs=4, rollout_steps=8, num_minibatches=2, update_epochs=2,
                    target_kl=0.0)
    policy = ActorCritic(OBS_DIM, spec.NUM_JOINTS)
    device = torch.device("cpu")
    algo = PPO(policy, cfg, device, total_updates=10)
    stats = algo.update(filled_buffer(cfg, OBS_DIM, spec.NUM_JOINTS, device, policy), 0)
    assert all(np.isfinite(v) for v in stats.values())
    assert stats["learning_rate"] == pytest.approx(cfg.learning_rate)


def test_training_path_goes_through_forward_not_evaluate():
    """DDP only all-reduces gradients for work done inside ``forward``.

    If the PPO update ever calls ``module.evaluate`` directly again, a 4-GPU run
    trains four independent policies and silently wastes the cluster. This
    pins the two-argument ``forward`` signature the update relies on.
    """
    policy = ActorCritic(OBS_DIM, spec.NUM_JOINTS)
    obs = torch.randn(3, OBS_DIM)
    actions = torch.randn(3, spec.NUM_JOINTS)

    assert policy(obs).shape == (3, spec.NUM_JOINTS)
    log_probs, entropy, values = policy(obs, actions)
    assert log_probs.shape == entropy.shape == values.shape == (3,)

    source = (REPO_ROOT / "src/microduck/rl/ppo.py").read_text()
    assert "self.wrapped(" in source
    assert "self.module.evaluate(" not in source


def test_learning_rate_anneals_to_the_configured_floor():
    cfg = PPOConfig(final_lr_fraction=0.1)
    algo = PPO(ActorCritic(OBS_DIM, spec.NUM_JOINTS), cfg, torch.device("cpu"),
               total_updates=100)
    assert algo.learning_rate_at(0) == pytest.approx(cfg.learning_rate)
    assert algo.learning_rate_at(100) == pytest.approx(cfg.learning_rate * 0.1)
    assert algo.learning_rate_at(1000) == pytest.approx(cfg.learning_rate * 0.1)


def test_minibatch_size_rejects_indivisible_shapes():
    cfg = PPOConfig(num_envs=5, rollout_steps=7, num_minibatches=4)
    with pytest.raises(ValueError, match="divisible"):
        cfg.minibatch_size(1)


def test_gae_discounts_and_cuts_at_episode_boundaries():
    buffer = RolloutBuffer(3, 1, 2, 1, torch.device("cpu"))
    for reward, done in ((1.0, 0.0), (1.0, 1.0), (1.0, 0.0)):
        buffer.add(torch.zeros(1, 2), torch.zeros(1, 1), torch.zeros(1),
                   torch.tensor([reward]), torch.tensor([done]), torch.zeros(1))
    buffer.compute_returns(torch.zeros(1), gamma=0.5, lam=1.0)
    # Step 1 ends the episode, so step 0 must not see step 2's reward.
    assert buffer.advantages[0].item() == pytest.approx(1.5)
    assert buffer.advantages[1].item() == pytest.approx(1.0)


def test_walk_checkpoint_warm_starts_fetch_policy_exactly():
    torch.manual_seed(0)
    walk = ActorCritic(OBS_DIM, spec.NUM_JOINTS)
    fetch = ActorCritic(FETCH_OBS_DIM, spec.NUM_JOINTS)
    report = load_transferred_weights(fetch, walk.state_dict())
    assert not any("skipped" in note or "missing" in note for note in report.values()), report

    walk_obs = torch.randn(4, OBS_DIM)
    fetch_obs = torch.zeros(4, FETCH_OBS_DIM)
    fetch_obs[:, :OBS_DIM] = walk_obs
    # Zeros on the appended task channels, so the warm-started policy starts out
    # behaving exactly like the walking policy it came from.
    torch.testing.assert_close(walk(walk_obs), fetch(fetch_obs))


def test_transfer_reports_incompatible_tensors_instead_of_dropping_them():
    small = ActorCritic(OBS_DIM, spec.NUM_JOINTS, actor_hidden=(32, 32))
    big = ActorCritic(OBS_DIM, spec.NUM_JOINTS, actor_hidden=(64, 64))
    report = load_transferred_weights(big, small.state_dict())
    assert any("mismatch" in note for note in report.values())
    with pytest.raises(ValueError):
        load_transferred_weights(big, small.state_dict(), strict_tail=True)


def test_episode_stats_expose_every_reduced_key():
    """Each reduced key must map to a real series.

    The ranks reduce a fixed-layout tensor built from these keys; a missing one
    would raise inside a collective, which is a miserable failure to debug.
    """
    stats = EpisodeStats()
    stats.start(2)
    for key in SHARED_STAT_KEYS:
        assert isinstance(stats.values_for(key), list)

    stats.update(np.array([1.0, 2.0]), np.array([True, False]),
                 [{"success": True, "reached_phase": 3}, {}])
    assert stats.values_for("ep_return") == [1.0]
    assert stats.values_for("success_rate") == [1.0]
    summary = stats.summary()
    assert summary["ep_return"] == pytest.approx(1.0)


def test_config_round_trips_through_json(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({
        "task": "fetch", "total_steps": 1234,
        "ppo": {"num_envs": 8, "rollout_steps": 16},
        "curriculum": {"enabled": False},
        "env_overrides": {"grasp_mode": "contact"},
    }))
    cfg = load_config(str(path))
    assert cfg.task == "fetch" and cfg.total_steps == 1234
    assert cfg.ppo.num_envs == 8 and cfg.ppo.rollout_steps == 16
    assert cfg.curriculum.enabled is False
    assert make_env_config(cfg).grasp_mode == "contact"


@pytest.mark.parametrize("name", ["walk_v100x4.json", "fetch_v100x4.json"])
def test_shipped_configs_are_valid(name):
    cfg = load_config(str(REPO_ROOT / "configs" / name))
    assert cfg.task in ("walk", "fetch")
    # Must divide cleanly on the 4-GPU box these configs are written for.
    assert cfg.ppo.minibatch_size(4) > 0
    make_env_config(cfg)


def test_env_overrides_reject_unknown_fields():
    cfg = TrainConfig(task="fetch", env_overrides={"not_a_field": 1})
    with pytest.raises(ValueError, match="not_a_field"):
        make_env_config(cfg)


def test_default_worker_count_splits_cores_between_ranks():
    assert default_num_workers(64, 4) >= 1
    assert default_num_workers(1, 4) == 1
    # Four ranks must never each claim the whole machine.
    assert default_num_workers(1024, 4) <= default_num_workers(1024, 1)


@pytest.mark.slow
def test_four_rank_distributed_run_keeps_policies_identical(tmp_path):
    """End-to-end: 4 ranks, different data, must end with identical weights.

    This is the integration guard on DDP gradient averaging and on every
    collective in the update being issued the same number of times per rank.
    """
    script = tmp_path / "ddp_job.py"
    script.write_text(f'''
import hashlib, sys
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
import torch, torch.distributed as dist
from torch import nn
from microduck.rl.networks import ActorCritic
from microduck.rl.ppo import PPO, PPOConfig, RolloutBuffer

dist.init_process_group("gloo")
rank, world = dist.get_rank(), dist.get_world_size()
torch.manual_seed(0)
net = ActorCritic(32, 4)
wrapped = nn.parallel.DistributedDataParallel(net)
cfg = PPOConfig(num_envs=4, rollout_steps=8, num_minibatches=1, update_epochs=2,
                target_kl=0.02)
algo = PPO(wrapped, cfg, torch.device("cpu"), total_updates=5, world_size=world)
torch.manual_seed(100 + rank)
buf = RolloutBuffer(8, 4, 32, 4, torch.device("cpu"))
for _ in range(8):
    obs = torch.randn(4, 32)
    action, log_prob, value = net.act(obs)
    buf.add(obs, action, log_prob, torch.randn(4) * (rank + 1), torch.zeros(4), value)
buf.compute_returns(torch.zeros(4), cfg.gamma, cfg.gae_lambda)
algo.update(buf, 0)
flat = torch.cat([p.detach().flatten() for p in net.parameters()])
digest = hashlib.sha256(flat.numpy().tobytes()).hexdigest()
gathered = [None] * world
dist.all_gather_object(gathered, digest)
if rank == 0:
    print("UNIQUE_HASHES", len(set(gathered)))
dist.destroy_process_group()
''')
    env = dict(os.environ, OMP_NUM_THREADS="1")
    result = subprocess.run(
        [sys.executable, "-m", "torch.distributed.run", "--standalone",
         "--nproc_per_node=4", str(script)],
        capture_output=True, text=True, timeout=600, env=env)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "UNIQUE_HASHES 1" in result.stdout, (
        "ranks ended with different weights: gradients were not all-reduced\n"
        + result.stdout[-2000:])
