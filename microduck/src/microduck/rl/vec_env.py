"""Vectorised environments.

MuJoCo at this model size runs on the CPU, so throughput comes from running
many copies in worker processes.  This is the part that decides how fast a
training run goes -- see ``docs/training.md`` for how to size it against the
machine.
"""

from __future__ import annotations

import multiprocessing as mp
from typing import Callable, Sequence

import numpy as np

EnvFactory = Callable[[], object]


class SyncVecEnv:
    """All environments in this process.  Simple, and best for debugging."""

    def __init__(self, factories: Sequence[EnvFactory]) -> None:
        self.envs = [f() for f in factories]
        self.num_envs = len(self.envs)
        self.observation_dim = self.envs[0].observation_dim
        self.action_dim = self.envs[0].action_dim

    def reset(self, seed: int | None = None) -> np.ndarray:
        obs = [env.reset(seed=None if seed is None else seed + i)[0]
               for i, env in enumerate(self.envs)]
        return np.stack(obs)

    def step(self, actions: np.ndarray):
        obs, rewards, dones, infos = [], [], [], []
        for env, action in zip(self.envs, actions):
            o, r, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                # Autoreset, with the final info kept so episode statistics are
                # not lost.
                info = dict(info, terminated=terminated, truncated=truncated)
                o, _ = env.reset()
            obs.append(o)
            rewards.append(r)
            dones.append(terminated or truncated)
            infos.append(info)
        return np.stack(obs), np.array(rewards, np.float32), np.array(dones, bool), infos

    def close(self) -> None:
        pass


def _worker(remote, factories_bytes, seeds) -> None:  # pragma: no cover - subprocess
    """Serve a *group* of environments over one pipe.

    One environment per pipe would mean a round trip per environment per step,
    and at ~0.5 ms of physics per step that overhead is a large fraction of the
    total.  Holding a group and stepping it in a single exchange amortises the
    pipe across the group.
    """
    import pickle

    envs = [f() for f in pickle.loads(factories_bytes)]
    for env, seed in zip(envs, seeds):
        env.reset(seed=seed)
    try:
        while True:
            cmd, data = remote.recv()
            if cmd == "step":
                obs, rewards, dones, infos = [], [], [], []
                for env, action in zip(envs, data):
                    o, reward, terminated, truncated, info = env.step(action)
                    if terminated or truncated:
                        info = dict(info, terminated=terminated, truncated=truncated)
                        o, _ = env.reset()
                    obs.append(o)
                    rewards.append(reward)
                    dones.append(terminated or truncated)
                    infos.append(info)
                remote.send((np.stack(obs), np.asarray(rewards, np.float32),
                             np.asarray(dones, bool), infos))
            elif cmd == "reset":
                obs = [env.reset(seed=None if data is None else data + i)[0]
                       for i, env in enumerate(envs)]
                remote.send(np.stack(obs))
            elif cmd == "spec":
                remote.send((envs[0].observation_dim, envs[0].action_dim))
            elif cmd == "set_attr":
                for env in envs:
                    setattr(env.cfg, data[0], data[1])
                remote.send(True)
            elif cmd == "close":
                remote.close()
                break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        remote.close()


class SubprocVecEnv:
    """Environments spread over worker processes.

    Each MuJoCo step releases the GIL for only part of its work, so threads do
    not scale here; processes do.  Size ``num_workers`` to the cores the rank
    is actually allowed to use -- oversubscribing makes every rollout slower,
    and with several ranks on one box each rank only gets a share of the
    machine.  Environments beyond that are better packed into the existing
    workers via ``envs_per_worker`` than given processes of their own.
    """

    def __init__(self, factories: Sequence[EnvFactory], start_seed: int = 0,
                 start_method: str = "spawn", num_workers: int | None = None) -> None:
        import pickle

        ctx = mp.get_context(start_method)
        self.num_envs = len(factories)
        # Set before anything can fail, so a partly built object still cleans
        # up instead of raising AttributeError out of __del__ and masking the
        # real error.
        self._closed = False

        workers = self.num_envs if num_workers is None else max(1, min(num_workers,
                                                                       self.num_envs))
        # Contiguous groups, so env ordering in the batch is stable and the
        # per-env seeds stay reproducible however the group sizes fall out.
        bounds = [round(i * self.num_envs / workers) for i in range(workers + 1)]
        self.groups = [(bounds[i], bounds[i + 1]) for i in range(workers)
                       if bounds[i + 1] > bounds[i]]
        self.num_workers = len(self.groups)

        self.remotes, self.processes = [], []
        for start, end in self.groups:
            parent, child = ctx.Pipe()
            process = ctx.Process(
                target=_worker,
                args=(child, pickle.dumps(list(factories[start:end])),
                      [start_seed + i for i in range(start, end)]),
                daemon=True)
            process.start()
            child.close()
            self.remotes.append(parent)
            self.processes.append(process)

        try:
            self.remotes[0].send(("spec", None))
            self.observation_dim, self.action_dim = self.remotes[0].recv()
        except (EOFError, ConnectionResetError) as exc:
            self.close()
            raise RuntimeError(
                "environment worker died during startup; run with "
                "--sync-envs to see the underlying error") from exc

    def reset(self, seed: int | None = None) -> np.ndarray:
        for (start, _end), remote in zip(self.groups, self.remotes):
            remote.send(("reset", None if seed is None else seed + start))
        return np.concatenate([remote.recv() for remote in self.remotes])

    def step(self, actions: np.ndarray):
        for (start, end), remote in zip(self.groups, self.remotes):
            remote.send(("step", actions[start:end]))
        results = [remote.recv() for remote in self.remotes]
        obs = np.concatenate([r[0] for r in results])
        rewards = np.concatenate([r[1] for r in results])
        dones = np.concatenate([r[2] for r in results])
        infos: list[dict] = []
        for r in results:
            infos.extend(r[3])
        return obs, rewards, dones, infos

    def set_env_attr(self, name: str, value) -> None:
        """Set a config field on every worker -- used to drive the curriculum."""
        for remote in self.remotes:
            remote.send(("set_attr", (name, value)))
        for remote in self.remotes:
            remote.recv()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for remote in self.remotes:
            try:
                remote.send(("close", None))
            except (BrokenPipeError, OSError):
                pass
        for process in self.processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()

    def __del__(self):
        self.close()
