# Microduck

An open reproduction of the [Microduck](https://github.com/pollen-robotics/microduck)
biped duck robot (Hugging Face / Pollen Robotics, 2026) as a software stack:
a parametric MJCF model, two MuJoCo tasks, and a distributed PPO trainer that
takes a policy from scratch to an ONNX file the robot can run.

The headline task is **fetch**: the duck walks to a ball, bends down and picks
it up with its beak, carries it back to where it started, and puts it down.

```
microduck/
  src/microduck/
    model/      spec.py is the single source of truth; builder.py emits the MJCF
    sim/        kinematics, reference gait, walking task, fetch task
    rl/         actor-critic, PPO, distributed trainer, ONNX export, benchmarks
  configs/      ready-to-run configs for a 4x V100 box
  scripts/      two-stage launcher
  docs/         training guide and task reference
  tests/        39 tests, including a real 4-rank distributed check
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[train,export,dev]'
```

Simulation needs only `mujoco` and `numpy`. Training adds `torch`; export adds
`onnx`/`onnxruntime`.

## Try it without training anything

```bash
microduck spec                  # the robot: 15 DoF, 0.78 kg, 25 cm
microduck walk --seconds 10     # scripted gait baseline
microduck bench --ranks 4       # throughput on this machine
```

`microduck walk` runs a hand-tuned open-loop gait, so a fresh clone does
something visible immediately. It walks forward at about 0.08 m/s and stands
indefinitely. It is a smoke test for the model and the IK, not a controller:
backward walking and in-place turning are not reliable, and it will not survive
a shove. That is what the learned policy is for.

## Train the fetch task

```bash
scripts/train_fetch_4xv100.sh
```

Two stages: locomotion first, then the fetch task warm-started from it. The
fetch observation is the walking observation with task channels appended, so a
walking checkpoint transfers exactly -- the fetch run starts from a duck that
can already walk. See [docs/training.md](docs/training.md).

```bash
microduck evaluate runs/fetch_v100x4/best.pt -n 100
microduck export   runs/fetch_v100x4/best.pt -o policy.onnx
```

Export writes a JSON sidecar beside the `.onnx` pinning the observation layout,
scales, joint order and action decoding, so the runtime cannot feed the network
a vector it was not trained on, and verifies the graph against PyTorch
numerically before writing it.

## The robot

15 servos: 5 per leg (hip yaw/roll/pitch, knee, ankle pitch), 3 for the neck
and head, a beak and a tail. The beak has two jaws -- a fixed lower mandible
and a servo-driven upper one -- so it works as a gripper. Two IMUs, a
wide-angle camera and an 8x8 ToF sensor are modelled at their mounting points.
Control runs at 50 Hz over 500 Hz physics, matching the real runtime.

`model/spec.py` holds all of it as plain data, and `model/builder.py` generates
the MJCF. **The XML is generated -- never edit it by hand**; run
`microduck build-model` after changing the spec. A test asserts the committed
XML matches what the generator produces, so a stale commit cannot silently
change the robot.

The spec is internally consistent in a way worth preserving: the standing pose
is an exact fixed point of the leg IK, so a zero action means "stand".

## Scope

What this is: a faithful software reproduction -- kinematics, dynamics, sensing,
tasks and the full sim2real-oriented training stack, with domain randomisation
over masses, friction, gearboxes, latency, sensor noise and pushes.

What it is not: the real robot's firmware or service architecture. The upstream
project runs a set of Rust services talking JSON-RPC 2.0 over Unix sockets; this
repo stops at the ONNX policy and the metadata needed to drive it. Link lengths
and masses are plausible reconstructions from the published figures, not the
manufacturer's CAD, so a policy trained here is a starting point for hardware
transfer, not a drop-in.

## Tests

```bash
pytest                       # 39 tests
pytest -m "not slow"         # skip the 4-rank distributed check
```

The suite covers more than shapes: the committed XML matching its generator,
the IK fixed point, the duck actually standing under its own PD control, the
scripted gait walking forward without falling, the grasp latching and
releasing, the fetch reward budget being winnable, and -- as a real 4-process
`torchrun` job -- that all ranks end a PPO update with identical weights.

That last one exists because the bug it catches is invisible on one GPU:
`DistributedDataParallel` only all-reduces gradients for work done inside
`forward`, so calling the module's `evaluate` directly trains four independent
policies on four GPUs and silently wastes the cluster.
