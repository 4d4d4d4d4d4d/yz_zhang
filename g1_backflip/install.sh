#!/usr/bin/env bash
# ============================================================
#  一键安装：Isaac Sim (pip) + Isaac Lab + RSL-RL + 本工程
#  系统要求：Ubuntu 20.04/22.04，NVIDIA 驱动 >= 535，GLIBC >= 2.34
# ============================================================
set -eo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

# ---------- 1. 环境检查 ----------
info "检查 GPU / 驱动 ..."
command -v nvidia-smi >/dev/null 2>&1 || die "未找到 nvidia-smi，请先安装 NVIDIA 驱动 (>=535)。"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
command -v git >/dev/null 2>&1 || die "需要 git：sudo apt install git"

# ---------- 2. 创建 Python 环境 ----------
if activate_env 2>/dev/null; then
    info "已存在 Python 环境，直接复用：$(which python)"
else
    if has_conda; then
        info "创建 conda 环境 $ENV_NAME (python=$PYTHON_VERSION) ..."
        conda create -y -n "$ENV_NAME" "python=$PYTHON_VERSION"
    else
        PY_BIN="python$PYTHON_VERSION"
        command -v "$PY_BIN" >/dev/null 2>&1 || die "未找到 conda，也未找到 $PY_BIN。请安装 Miniconda 或 sudo apt install python$PYTHON_VERSION-venv"
        info "未检测到 conda，使用 venv：$VENV_DIR"
        "$PY_BIN" -m venv "$VENV_DIR"
    fi
    activate_env || die "Python 环境激活失败"
fi

PY_VER_NOW="$(python -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
[ "$PY_VER_NOW" = "$PYTHON_VERSION" ] || die "当前 Python 为 $PY_VER_NOW，Isaac Sim $ISAACSIM_VERSION 需要 $PYTHON_VERSION"

python -m pip install --upgrade pip wheel setuptools

# ---------- 3. PyTorch ----------
info "安装 PyTorch $TORCH_VERSION ($TORCH_INDEX_URL) ..."
python -m pip install "torch==$TORCH_VERSION" "torchvision==$TORCHVISION_VERSION" --index-url "$TORCH_INDEX_URL"

# ---------- 4. Isaac Sim ----------
info "安装 Isaac Sim $ISAACSIM_VERSION（约 10+GB，耐心等待）..."
python -m pip install "isaacsim[all,extscache]==$ISAACSIM_VERSION" --extra-index-url https://pypi.nvidia.com

# ---------- 5. Isaac Lab ----------
mkdir -p "$THIRD_PARTY"
if [ ! -d "$ISAACLAB_DIR/.git" ]; then
    info "克隆 Isaac Lab $ISAACLAB_TAG ..."
    git clone --depth 1 --branch "$ISAACLAB_TAG" https://github.com/isaac-sim/IsaacLab.git "$ISAACLAB_DIR"
else
    info "Isaac Lab 已存在：$ISAACLAB_DIR"
fi
info "安装 Isaac Lab 扩展 (isaaclab / assets / tasks / rl[rsl_rl]) ..."
python -m pip install -e "$ISAACLAB_DIR/source/isaaclab"
python -m pip install -e "$ISAACLAB_DIR/source/isaaclab_assets"
python -m pip install -e "$ISAACLAB_DIR/source/isaaclab_tasks"
python -m pip install -e "$ISAACLAB_DIR/source/isaaclab_rl[rsl_rl]"

# ---------- 6. 本工程 ----------
info "安装 g1_backflip 任务包 ..."
python -m pip install -e "$PROJECT_ROOT/source/g1_backflip"
python -m pip install tensorboard

# ---------- 7. 自检 ----------
python - <<'PY'
import importlib, torch
print("torch", torch.__version__, "cuda:", torch.cuda.is_available(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
for m in ["isaacsim", "rsl_rl", "g1_backflip"]:
    importlib.import_module(m); print("ok:", m)
PY

date > "$INSTALL_STAMP"
info "安装完成！运行  ./train.sh  开始训练。"
