"""Export a trained policy to ONNX for the on-robot runtime.

The robot runs the policy from ONNX, not from a PyTorch checkpoint: it keeps
torch off the robot entirely and makes the 50 Hz inference budget easy to meet.
The export deliberately traces the deterministic path (``forward`` with no
actions), because the policy is run at its mean on hardware -- sampling is a
training-time exploration device, not something you want a 25 cm biped doing
next to a table edge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ..model import spec
from ..sim.env import OBS_LAYOUT, OBS_SCALES
from ..sim.fetch_env import FETCH_OBS_LAYOUT
from .networks import ActorCritic

LAYOUTS = {"walk": OBS_LAYOUT, "fetch": FETCH_OBS_LAYOUT}


def load_policy(checkpoint: str | Path, device: str = "cpu") -> tuple[ActorCritic, dict]:
    state = torch.load(checkpoint, map_location=device, weights_only=False)
    policy_state = state.get("policy", state)
    obs_dim = int(state.get("obs_dim", policy_state["actor.0.weight"].shape[1]))
    action_dim = int(state.get("action_dim", spec.NUM_JOINTS))
    actor_hidden = tuple(
        policy_state[k].shape[0] for k in sorted(policy_state)
        if k.startswith("actor.") and k.endswith(".weight"))[:-1]
    critic_hidden = tuple(
        policy_state[k].shape[0] for k in sorted(policy_state)
        if k.startswith("critic.") and k.endswith(".weight"))[:-1]
    policy = ActorCritic(obs_dim, action_dim, actor_hidden=actor_hidden,
                         critic_hidden=critic_hidden)
    policy.load_state_dict(policy_state)
    policy.eval()
    return policy, state


def export(checkpoint: str | Path, output: str | Path, task: str = "",
           opset: int = 17) -> Path:
    policy, state = load_policy(checkpoint)
    task = task or str(state.get("task", "fetch"))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    dummy = torch.zeros(1, policy.obs_dim)
    torch.onnx.export(
        policy, (dummy,), str(output), opset_version=opset,
        input_names=["observation"], output_names=["action"],
        dynamic_axes={"observation": {0: "batch"}, "action": {0: "batch"}})

    # The sidecar is what makes the export usable six months later: it pins the
    # observation layout, the scales and the action decoding, so the runtime
    # cannot feed the network a vector it was not trained on.
    layout = LAYOUTS.get(task, FETCH_OBS_LAYOUT)
    meta = {
        "task": task,
        "observation_dim": policy.obs_dim,
        "action_dim": policy.action_dim,
        "observation_layout": [{"name": n, "size": s, "scale": OBS_SCALES[n]}
                               for n, s in layout],
        "joint_names": list(spec.JOINT_NAMES),
        "default_pose": spec.default_pose(),
        "action_scale": spec.ACTUATION.action_scale,
        "action_clip": spec.ACTUATION.action_clip,
        "joint_lower": spec.joint_limits()[0],
        "joint_upper": spec.joint_limits()[1],
        "control_hz": 1.0 / spec.CONTROL_DT,
        "decode": "target = clip(default_pose + action_scale * clip(action, "
                  "-action_clip, action_clip), joint_lower, joint_upper)",
        "source_checkpoint": str(checkpoint),
        "trained_updates": int(state.get("update", 0)),
    }
    meta_path = output.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))

    _verify(policy, output)
    return output


def _verify(policy: ActorCritic, output: Path) -> None:
    """Check the exported graph against the torch module.

    A silent numerical difference here is the worst kind of bug: the policy
    would work in simulation and misbehave only on the robot.
    """
    try:
        import onnxruntime  # type: ignore
    except ImportError:
        print("[export] onnxruntime not installed; skipping numerical check")
        return
    session = onnxruntime.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    sample = rng.normal(size=(8, policy.obs_dim)).astype(np.float32)
    onnx_out = session.run(None, {"observation": sample})[0]
    with torch.no_grad():
        torch_out = policy(torch.from_numpy(sample)).numpy()
    max_diff = float(np.abs(onnx_out - torch_out).max())
    if max_diff > 1e-4:
        raise RuntimeError(f"ONNX output differs from torch by {max_diff:.2e}")
    print(f"[export] verified against torch, max difference {max_diff:.2e}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Export a Microduck policy to ONNX.")
    p.add_argument("checkpoint")
    p.add_argument("-o", "--output", default="policy.onnx")
    p.add_argument("--task", default="", choices=("", "walk", "fetch"))
    p.add_argument("--opset", type=int, default=17)
    args = p.parse_args(argv)
    path = export(args.checkpoint, args.output, args.task, args.opset)
    print(f"[export] wrote {path} and {path.with_suffix('.json')}")


if __name__ == "__main__":
    main()
