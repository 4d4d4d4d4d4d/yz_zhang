#!/usr/bin/env bash
# ============================================================
#  一键训练：./train.sh
#  常用覆盖：NUM_ENVS=1024 ./train.sh
#            ./train.sh --max_iterations 3000
#            ./train.sh --resume                # 从最近一次 run 继续
#            ./train.sh --gui                   # 打开可视化窗口（会变慢）
# ============================================================
set -eo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

if [ ! -f "$INSTALL_STAMP" ] || ! activate_env 2>/dev/null; then
    warn "未检测到安装，先执行一键安装 ..."
    bash "$PROJECT_ROOT/install.sh"
fi
activate_env

HEADLESS="--headless"
ARGS=()
for a in "$@"; do
    if [ "$a" = "--gui" ]; then HEADLESS=""; else ARGS+=("$a"); fi
done

cd "$PROJECT_ROOT"
info "开始训练：task=$TASK num_envs=$NUM_ENVS max_iter=$MAX_ITERATIONS"
info "TensorBoard：./tensorboard.sh   日志目录：$PROJECT_ROOT/logs/rsl_rl/g1_backflip"
python scripts/train.py --task "$TASK" --num_envs "$NUM_ENVS" \
    --max_iterations "$MAX_ITERATIONS" $HEADLESS "${ARGS[@]}"
