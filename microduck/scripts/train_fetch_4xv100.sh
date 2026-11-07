#!/usr/bin/env bash
# Two-stage training for the fetch task on one 4x V100 (16 GB) box.
#
#   stage 1  walk    velocity-tracking locomotion
#   stage 2  fetch   warm-started from stage 1, learns approach/grasp/carry/drop
#
# Stage 1 exists because the fetch observation is the walking observation with
# task channels appended, so a walking checkpoint transfers into the fetch
# policy exactly (see microduck.rl.networks.load_transferred_weights): the
# fetch run starts from a duck that can already walk, instead of spending its
# first tens of millions of steps rediscovering that.
#
# Usage:
#   scripts/train_fetch_4xv100.sh            # both stages
#   STAGE=fetch scripts/train_fetch_4xv100.sh  # stage 2 only
#
# Tune NUM_ENVS first: on this model the throughput ceiling is CPU physics, not
# the GPUs. Run `microduck bench --ranks 4` on this box and use the envs count
# that came out fastest.
set -euo pipefail

cd "$(dirname "$0")/.."

GPUS="${GPUS:-4}"
NUM_ENVS="${NUM_ENVS:-32}"
STAGE="${STAGE:-all}"
WALK_CONFIG="${WALK_CONFIG:-configs/walk_v100x4.json}"
FETCH_CONFIG="${FETCH_CONFIG:-configs/fetch_v100x4.json}"

# One thread per worker process. Each rank runs its environments in their own
# processes, and letting every one of them also spawn a BLAS thread pool
# oversubscribes the machine badly enough to halve throughput.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
# MuJoCo is CPU-only here; keep it off the GPUs so they are left to torch.
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"

launch() {
  echo "=== $1 ==="
  torchrun --standalone --nproc_per_node="${GPUS}" \
    -m microduck.rl.train --config "$2" --num-envs "${NUM_ENVS}" "${@:3}"
}

if [[ "${STAGE}" == "all" || "${STAGE}" == "walk" ]]; then
  launch "stage 1: walking" "${WALK_CONFIG}"
fi

if [[ "${STAGE}" == "all" || "${STAGE}" == "fetch" ]]; then
  if [[ ! -f runs/walk_v100x4/best.pt ]]; then
    echo "no walking checkpoint at runs/walk_v100x4/best.pt." >&2
    echo "Run stage 1 first, or train fetch from scratch with:" >&2
    echo "  torchrun --standalone --nproc_per_node=${GPUS} -m microduck.rl.train \\" >&2
    echo "      --config ${FETCH_CONFIG} --init-from ''" >&2
    exit 1
  fi
  launch "stage 2: fetch" "${FETCH_CONFIG}"
fi

BEST="runs/fetch_v100x4/best.pt"
if [[ -f "${BEST}" ]]; then
  echo "=== evaluating ==="
  python -m microduck.rl.evaluate "${BEST}" -n 100
  echo "=== exporting for the robot ==="
  python -m microduck.rl.export_onnx "${BEST}" -o runs/fetch_v100x4/policy.onnx
fi
