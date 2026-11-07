# Training the fetch task on 4x V100 (16 GB)

The task: **walk to the ball, bend down and pick it up with the beak, carry it
back to the starting spot, and put it down.**

## The one thing to know first

**This workload is bound by CPU physics, not by the GPUs.**

The policy is a 3-layer MLP with ~0.4 M parameters. A forward/backward pass on
one V100 takes well under a millisecond, while one environment step costs about
0.5 ms of MuJoCo physics on one core. So four V100s are not the scarce
resource here -- cores are. Expect GPU utilisation in the low tens of percent
and do not try to "fix" it; the useful consequences are:

- `num_envs` and `num_workers` matter far more than anything GPU-side.
- fp16 (`--amp`) buys almost nothing at this network size. It is off by default.
- If you want to go meaningfully faster, the move is GPU-side physics
  (MuJoCo Warp / MJX), not a bigger batch. See *Going faster* below.

## Measured throughput

Measured on a 4-core container, fetch task, no rendering:

| configuration | env-steps/s | per env |
|---|---:|---:|
| 1 env, in-process | 1,985 | 1,985 |
| 4 envs, 4 workers | 2,309 | 577 |
| 16 envs, 4 workers | 3,632 | 227 |
| 32 envs, 4 workers | **5,119** | 160 |

Two things to take from this. One worker per core is right, but packing
*several environments into each worker* is what pays: 32 envs over 4 workers
beat 12 envs over 12 workers by ~65%, because the pipe round trip is amortised
across the group instead of paid per environment per step. That is why
`SubprocVecEnv` takes `num_workers` separately from the environment count.

That is ~1,280 env-steps/s per core. Measure your own box before you commit:

```bash
microduck bench --task fetch --ranks 4
```

It prints the best configuration it found and extrapolates wall-clock time for
100 M and 300 M steps. On a 48-core box, expect very roughly 45-60 k
env-steps/s in total and 300 M steps in ~2 hours; a 16-core box will be more
like 7 hours. NUMA effects on large servers make the extrapolation optimistic,
so trust `bench` over the formula.

## Running it

```bash
pip install -e '.[train,export,dev]'
scripts/train_fetch_4xv100.sh
```

That runs both stages. To run them by hand:

```bash
export OMP_NUM_THREADS=1            # critical: see "Threads" below

# Stage 1: locomotion.
torchrun --standalone --nproc_per_node=4 -m microduck.rl.train \
    --config configs/walk_v100x4.json

# Stage 2: the fetch task, warm-started from stage 1.
torchrun --standalone --nproc_per_node=4 -m microduck.rl.train \
    --config configs/fetch_v100x4.json
```

Then evaluate and export for the robot:

```bash
microduck evaluate runs/fetch_v100x4/best.pt -n 100
microduck export   runs/fetch_v100x4/best.pt -o runs/fetch_v100x4/policy.onnx
```

## Why two stages

The fetch observation is the walking observation **with task channels
appended**, in that order. So a walking checkpoint transfers into the fetch
policy exactly: every weight is reused, the new input columns start at zero,
and the fetch run's first rollouts behave identically to the walking policy it
came from (`tests/test_rl.py::test_walk_checkpoint_warm_starts_fetch_policy_exactly`
pins this). The fetch run therefore starts from a duck that can already walk,
instead of spending its first tens of millions of steps discovering locomotion
again under a sparser reward.

To skip stage 1 and train fetch from scratch, pass `--init-from ''`. It does
work; it is just slower.

## Configuration that matters

| knob | default | why |
|---|---|---|
| `ppo.num_envs` | 32 per rank | Set from `microduck bench`. Global batch is `4 x num_envs x rollout_steps`. |
| `num_workers` | auto | Worker processes per rank; auto = cores / ranks. Envs beyond this are packed into existing workers. |
| `ppo.rollout_steps` | 48 | 48 x 0.02 s = ~1 s of robot time per env per update. |
| `ppo.target_kl` | 0.02 | Stops the epoch loop early. The best guard against a late-run collapse. |
| `ppo.gamma` | 0.995 (fetch) | Episodes are 25 s = 1250 steps; 0.99 discounts the delivery bonus too hard. |
| `curriculum` | on | Ball starts near and straight ahead, opening up with measured success rate. |
| `ppo.amp` | off | See above. Turn on only if you scale the network up. |

### Threads

Set `OMP_NUM_THREADS=1`. Each rank runs its environments in separate
processes; if every one of those also spawns a BLAS thread pool, a 48-core box
ends up with hundreds of runnable threads and throughput roughly halves.
`torch_threads` defaults to 1 for the same reason. The launcher script exports
this for you.

### Memory

Not a constraint. The whole rollout buffer is
`4 ranks x 32 envs x 48 steps x 67 floats`, a few MB; the model is 1.6 MB of
fp32. 16 GB per GPU is many orders of magnitude more than needed, which is
another way of saying the GPUs are not the bottleneck.

## Reading the logs

`runs/<name>/progress.csv` and a console line per update:

```
[  1200] steps=  44,236,800 sps=  41,900  ep_return=412.330  success_rate=0.624  reached_phase=2.81  kl=0.0113  diff=0.85
```

- `success_rate` -- fraction of episodes that delivered the ball and let go of
  it on the pad. **This is the number the task is judged on.**
- `reached_phase` -- mean furthest phase reached (0 approach, 1 grasp,
  2 return, 3 release). Far more informative than return while the policy is
  still learning: it tells you *which* step it is stuck on.
- `diff` -- current curriculum difficulty.
- `kl` -- if this is pinned at `target_kl` every update, lower the learning rate.

Episode statistics are pooled across all four ranks as (sum, count) pairs in a
single collective, so the logged numbers describe the whole job rather than
rank 0's slice.

## What to expect, and what to do when it stalls

Rough shape of a healthy run (varies with seed):

| phase | steps | sign of life |
|---|---|---|
| locomotion holds up under the task reward | 0-20 M | `fall_rate` falling, `reached_phase` ~0 |
| reliably walks to the ball | 20-80 M | `reached_phase` approaching 1 |
| first grasps | 80-150 M | `reached_phase` > 1, `success_rate` leaves zero |
| carries and delivers | 150-300 M | `success_rate` climbing, `diff` promoting |

Diagnosis by symptom:

- **`reached_phase` stuck at 0.** The duck is not getting to the ball. Check
  it can still walk (`microduck evaluate --task walk`), and that stage 1
  actually warm-started (the run prints `[init] warm-started from ...`).
- **Stuck at 1 -- reaches the ball, never grasps.** The bend-down motion is the
  hard part. Raise `fetch_rewards.beak_reach`, or widen
  `beak_reach_sigma` so the gradient reaches further out.
- **Grasps then drops.** Raise `drop_penalty`, or `beak_posture` to hold the
  beak shut while carrying.
- **`success_rate` high but the gait looks awful.** The locomotion
  regularisers are too weak relative to the task bonuses. Raise `action_rate`
  and `torque` penalties in `FetchConfig.rewards`. A policy that scores well
  and chatters the servos will not survive contact with hardware.
- **Return rises but `success_rate` stays at 0.** Check the reward budget.
  `tests/test_envs.py::test_doing_nothing_scores_far_below_a_completed_fetch`
  guards the balance, but if you edit weights, re-run it: with the walking
  task's own `alive` and `upright` weights, standing still for 25 s outscores
  a complete fetch and the policy correctly learns to do nothing.

## Resuming

Checkpoints are written atomically (temp file, then rename), so a crash
mid-save cannot corrupt one.

```bash
torchrun --standalone --nproc_per_node=4 -m microduck.rl.train \
    --config configs/fetch_v100x4.json --resume runs/fetch_v100x4/latest.pt
```

## Going faster

If ~2 hours per 300 M steps is too slow, in order of payoff:

1. **More cores.** Throughput is close to linear in cores. The GPUs are idle.
2. **GPU physics.** MuJoCo Warp / MJX runs thousands of envs on-GPU and would
   actually use the V100s. It is a real port, not a flag: the env would need to
   be rewritten against a batched, JAX/Warp-side API, and the weld-based grasp
   and the Python phase machine both assume per-env host state.
3. **Shorter episodes with a curriculum on episode length.** 25 s episodes are
   generous; most of the learning signal is in the first few seconds of each
   phase.
4. **Fewer `update_epochs`.** 5 is conservative. 3 costs little and returns
   ~15% of wall clock, since the update is the only GPU-side work.
