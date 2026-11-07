#!/usr/bin/env bash
# ============================================================
#  G1 后空翻工程 - 全局配置（按需修改）
# ============================================================

# Python 环境名（conda 环境名 或 venv 目录名）
ENV_NAME="${ENV_NAME:-g1flip}"

# Isaac Sim / Isaac Lab 版本（两者需配套，默认组合已验证兼容 RTX 30 系）
ISAACSIM_VERSION="${ISAACSIM_VERSION:-4.5.0}"
ISAACLAB_TAG="${ISAACLAB_TAG:-v2.1.0}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
TORCH_VERSION="${TORCH_VERSION:-2.5.1}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.20.1}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu121}"

# 训练默认参数（针对 RTX 3060 12GB 调优）
NUM_ENVS="${NUM_ENVS:-2048}"          # 12GB 显存建议 1024~2048；爆显存就调小
MAX_ITERATIONS="${MAX_ITERATIONS:-6000}"
TASK="${TASK:-Isaac-G1-Backflip-Direct-v0}"

# 自动接受 Omniverse EULA，避免首次运行卡在交互提示
export OMNI_KIT_ACCEPT_EULA=YES
