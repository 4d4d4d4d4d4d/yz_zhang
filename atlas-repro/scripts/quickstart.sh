#!/usr/bin/env bash
# End-to-end: test, train, evaluate, sample. ~40 minutes on 4 CPU cores.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== tests =="
python3 -m pytest tests -q

echo "== train =="
python3 -m atlas.train --config configs/tiny.json

echo "== evaluate =="
python3 -m atlas.eval --ckpt runs/atlas-tiny/checkpoint.pt --scenes 32 \
    --out runs/atlas-tiny/metrics.json

echo "== sample =="
python3 -m atlas.sample --ckpt runs/atlas-tiny/checkpoint.pt \
    --prompt "a scene with two red spheres and one blue cube on the floor" \
    --views 8 --out samples/text2world

python3 -m atlas.sample --ckpt runs/atlas-tiny/checkpoint.pt \
    --scene 7 --observed 1 --views 6 --out samples/image2world

echo "done -- see runs/atlas-tiny and samples/"
