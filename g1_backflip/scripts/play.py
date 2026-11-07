"""Play a trained G1 backflip policy and export it to TorchScript / ONNX.

Usage (normally via ../play.sh):
    python scripts/play.py --task Isaac-G1-Backflip-Direct-Play-v0 --num_envs 16
"""

import argparse
import os
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Play G1 backflip policy.")
parser.add_argument("--task", type=str, default="Isaac-G1-Backflip-Direct-Play-v0")
parser.add_argument("--num_envs", type=int, default=16)
parser.add_argument("--load_run", type=str, default=".*", help="Run folder (regex), default: latest.")
parser.add_argument("--checkpoint", type=str, default=None, help="Path to a .pt file, or regex of file name.")
parser.add_argument("--video", action="store_true")
parser.add_argument("--video_length", type=int, default=500)
parser.add_argument("--steps", type=int, default=0, help="Stop after N steps (0 = run until window closed).")
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
if args_cli.video:
    args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402
from rsl_rl.runners import OnPolicyRunner  # noqa: E402

from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper, export_policy_as_jit, export_policy_as_onnx  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path, parse_env_cfg  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import load_cfg_from_registry  # noqa: E402

import g1_backflip  # noqa: E402,F401

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=args_cli.num_envs)
    agent_cfg = load_cfg_from_registry(args_cli.task, "rsl_rl_cfg_entry_point")
    if args_cli.device is not None:
        agent_cfg.device = args_cli.device

    log_root_path = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", agent_cfg.experiment_name)
    if args_cli.checkpoint and os.path.isfile(args_cli.checkpoint):
        resume_path = os.path.abspath(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(log_root_path, args_cli.load_run, args_cli.checkpoint or "model_.*.pt")
    log_dir = os.path.dirname(resume_path)
    print(f"[INFO] Loading model checkpoint from: {resume_path}")

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)
    if args_cli.video:
        env = gym.wrappers.RecordVideo(
            env,
            video_folder=os.path.join(log_dir, "videos", "play"),
            step_trigger=lambda step: step == 0,
            video_length=args_cli.video_length,
            disable_logger=True,
        )
    env = RslRlVecEnvWrapper(env)

    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path)
    policy = runner.get_inference_policy(device=env.unwrapped.device)

    # ---- export (for sim2sim / deployment)
    policy_nn = getattr(runner.alg, "policy", None) or getattr(runner.alg, "actor_critic")
    normalizer = getattr(runner, "obs_normalizer", None)
    export_dir = os.path.join(log_dir, "exported")
    export_policy_as_jit(policy_nn, normalizer, path=export_dir, filename="policy.pt")
    export_policy_as_onnx(policy_nn, normalizer=normalizer, path=export_dir, filename="policy.onnx")
    print(f"[INFO] Exported policy to: {export_dir}")

    obs, _ = env.get_observations()
    step = 0
    while simulation_app.is_running():
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, _, _ = env.step(actions)
        step += 1
        if args_cli.video and step >= args_cli.video_length:
            break
        if args_cli.steps and step >= args_cli.steps:
            break
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
