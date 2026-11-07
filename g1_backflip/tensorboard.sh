#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
activate_env || die "请先运行 ./install.sh"
tensorboard --logdir "$PROJECT_ROOT/logs/rsl_rl" --port "${PORT:-6006}" --bind_all
