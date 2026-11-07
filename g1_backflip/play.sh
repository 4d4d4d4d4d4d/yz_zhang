#!/usr/bin/env bash
# ============================================================
#  可视化回放 + 导出策略（JIT / ONNX）
#  ./play.sh                       # 自动加载最新 checkpoint
#  ./play.sh --checkpoint /path/model_5000.pt
#  ./play.sh --video --headless    # 录制视频到 logs/.../videos/play
# ============================================================
set -eo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
activate_env || die "请先运行 ./install.sh"
cd "$PROJECT_ROOT"
python scripts/play.py --task "${TASK%-v0}-Play-v0" --num_envs "${PLAY_ENVS:-16}" "$@"
