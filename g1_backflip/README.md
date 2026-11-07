# G1 Backflip — 在 RTX 3060 12G 上用 Isaac Sim 训练宇树 G1 后空翻

基于 **Isaac Sim 4.5 + Isaac Lab v2.1 + RSL-RL (PPO)**，包含一键安装、一键训练、回放和导出脚本。

```
g1_backflip/
├── config.sh            # 全局配置：版本号、num_envs、迭代次数（按需修改）
├── install.sh           # 一键安装（Python 环境 + PyTorch + Isaac Sim + Isaac Lab + 本工程）
├── train.sh             # 一键训练（第一次运行会自动调用 install.sh）
├── play.sh              # 回放 + 导出 policy.pt / policy.onnx
├── tensorboard.sh       # 查看训练曲线
├── scripts/
│   ├── train.py
│   └── play.py
└── source/g1_backflip/g1_backflip/tasks/backflip/
    ├── g1_backflip_env_cfg.py   # 环境/奖励/参考轨迹配置
    ├── g1_backflip_env.py       # DirectRLEnv 环境实现
    └── agents/rsl_rl_ppo_cfg.py # PPO 超参数
```

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 系统 | Ubuntu 22.04（推荐）/ 20.04，x86_64 |
| GPU | RTX 3060 12GB（其他 ≥8GB 的 RTX 显卡也可） |
| 驱动 | NVIDIA ≥ 535（`nvidia-smi` 能正常输出） |
| 磁盘 | ≥ 50 GB 空闲（Isaac Sim 约 15GB，加上缓存） |
| 内存 | ≥ 32 GB 推荐（16GB 需把 `NUM_ENVS` 调到 1024） |
| 其他 | `git`；推荐装 Miniconda（没有 conda 会用系统 `python3.10 -m venv`） |

## 2. 一键训练

```bash
cd g1_backflip
```

```bash
./train.sh
```

第一次运行会自动安装依赖（下载 10+GB，耐心等）。之后再运行 `./train.sh` 就直接开始训练（默认 headless 模式，2048 个并行环境，6000 次迭代）。

常用参数：

```bash
NUM_ENVS=1024 ./train.sh                   # 显存不够 / 内存不够时调小
```

```bash
./train.sh --max_iterations 3000 --seed 1
```

```bash
./train.sh --resume                        # 从最近一次 run 的最新 checkpoint 继续训练
```

```bash
NUM_ENVS=64 ./train.sh --max_iterations 5  # 冒烟测试：确认整条流程能跑通
```

```bash
NUM_ENVS=32 ./train.sh --gui               # 打开窗口看训练过程（会慢很多）
```

查看曲线（另开一个终端）：

```bash
./tensorboard.sh   # 浏览器打开 http://localhost:6006
```

重点看这几项：
- `Episode/max_rotation_deg`：每个 episode 实际转过的最大角度，**接近 360 就说明翻过去了**
- `Episode_Termination/time_out` 上升、`died` 下降：说明落地后能站稳
- `Episode_Reward/pitch_track`、`orient_track`：参考轨迹的跟踪质量

## 3. 回放 / 导出

```bash
./play.sh                                   # 加载最新 run 的最新 checkpoint，16 个机器人同时后空翻
```

```bash
./play.sh --checkpoint logs/rsl_rl/g1_backflip/<run>/model_6000.pt
```

```bash
./play.sh --video --headless                # 录视频到 <run>/videos/play/
```

`play.sh` 会同时导出 `<run>/exported/policy.pt`（TorchScript）和 `policy.onnx`，可以拿去做 sim2sim（例如 MuJoCo）。

## 4. 任务设计

每个 episode（2.5 s，50 Hz 控制，200 Hz 物理）就是一次完整的后空翻尝试。策略要跟踪的参考轨迹是手工设计的，**不需要动捕数据**：

| 时间 (s) | 阶段 | 参考骨盆高度 | 参考俯仰角 |
|---|---|---|---|
| 0.00–0.35 | 下蹲 | 0.74 → 0.55 m | 0° |
| 0.35–0.55 | 蹬地起跳 | 0.55 → 0.85 m | 开始后仰 |
| 0.55–1.15 | 腾空旋转 | 最高 1.25 m | → -360°（smoothstep，峰值约 11.8 rad/s） |
| 1.15–1.45 | 落地缓冲 | → 0.72 m | -360° |
| 1.45–2.50 | 站稳 | 0.74 m | -360° |

- **观测（84 维）**：本体系线速度/角速度、重力投影、骨盆高度，23 个关节的位置/速度，上一步动作，以及相位信号（时间、参考角的 sin/cos、参考角速度、参考高度）。
- **动作（23 维）**：腿 12 + 腰 1 + 手臂 10 个关节的 PD 位置目标偏移（手指保持默认）。
- **奖励**：
  - 跟踪项：积分俯仰角（能区分 0° 和 360°）、整体姿态四元数、俯仰角速度、骨盆高度
  - 探索引导：翻转窗口内的后旋角速度奖励、起跳窗口内的竖直速度奖励
  - 落地项：双脚触地、静止、回到默认姿态
  - 正则项：侧向角速度、横向漂移、左右腿对称、动作变化率、力矩、关节加速度、关节限位
- **终止条件**：骨盆/躯干触地、骨盆高度 < 0.25 m、姿态偏离参考 > 1.8 rad、超时。
- **域随机化**：地面摩擦/恢复系数、躯干质量。

所有时间点、高度、奖励权重都在 `g1_backflip_env_cfg.py` 里，改完直接重新 `./train.sh` 即可。

## 5. 训练预期与调参

- RTX 3060 + 2048 envs 大约每次迭代 1.5–3 s，6000 次迭代约 3–5 小时（视 CPU 而定）。
- 一般几百次迭代学会下蹲起跳，1000–3000 次迭代开始转满 360°，后面主要是在学稳定落地。
- 常见问题：
  - **显存不足 (CUDA OOM / PhysX buffer overflow)**：`NUM_ENVS=1024 ./train.sh`
  - **只后仰倒地、不起跳**：调大 `takeoff_vel` / `height_track`，或者把 `max_orient_err` 调大一点（如 2.5），让早期探索别那么快被终止
  - **转不够 360°**：调大 `spin_bonus` / `pitch_track`，或把 `flip_end_t` 往后放（转得慢一点）
  - **翻过去但落地摔倒**：调大 `feet_contact_land`、`stand_still`，在已有模型上 `--resume` 继续训练
  - **侧翻 / 歪着翻**：调大 `lateral_ang_vel`、`leg_symmetry` 的惩罚
- 换 Isaac Sim 5.x：修改 `config.sh` 里的 `ISAACSIM_VERSION=5.0.0`、`ISAACLAB_TAG=v2.2.0`、`PYTHON_VERSION=3.11`、`TORCH_VERSION=2.7.0`、`TORCHVISION_VERSION=0.22.0`、`TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128`，然后删掉 `.installed` 和旧环境重新安装。

## 6. 注意

- **本工程只在仿真里训练。** 后空翻对真机冲击很大，部署到真实 G1 之前必须做 sim2sim 验证、电机力矩/速度限幅、吊架保护，风险自负。
- Windows 也能装 Isaac Sim，但这套一键脚本只支持 Linux。Windows 用户可以照着 `install.sh` 的步骤手动执行，再运行 `python scripts/train.py --headless`。
