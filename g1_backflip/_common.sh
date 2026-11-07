#!/usr/bin/env bash
# 公共函数：定位工程目录、激活 Python 环境
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_ROOT/config.sh"
THIRD_PARTY="$PROJECT_ROOT/third_party"
ISAACLAB_DIR="$THIRD_PARTY/IsaacLab"
VENV_DIR="$PROJECT_ROOT/.venv_$ENV_NAME"
INSTALL_STAMP="$PROJECT_ROOT/.installed"

info()  { echo -e "\033[1;32m[G1-Flip]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[G1-Flip][WARN]\033[0m $*"; }
die()   { echo -e "\033[1;31m[G1-Flip][ERROR]\033[0m $*" >&2; exit 1; }

has_conda() { command -v conda >/dev/null 2>&1; }

activate_env() {
    if has_conda && conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
        eval "$(conda shell.bash hook)"
        conda activate "$ENV_NAME"
    elif [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    else
        return 1
    fi
}
