"""Edge-NPU design study — reproducible driver for docs/NPU-Design-Study.md.

An 18-layer transformer encoder (d=256, 8 heads, seq=128, FFN=1024, int8)
compared across three datapath designs on physically-grounded PPA (SPEC-013).

Run from the repo root:  python examples/design_study_encoder.py

We evaluate ONE encoder layer (the repeating unit) and scale ×N_LAYERS.
Per-op compute cost + dynamic energy come from the RuleBasedMapper
(matmul→MAC, softmax/gelu/layernorm→AVP); area/leakage from the physical
models. This attributes each op to its correct engine and avoids the
wired-pipeline streaming quirk.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

import npu_sim.modules  # noqa: F401  (registers modules)
from npu_sim.evaluation import chip_fidelity, elaborate
from npu_sim.evaluation.trace_ops import ops_from_list
from npu_sim.mapping import RuleBasedMapper

D, H, S, F, N_LAYERS = 256, 8, 128, 1024, 18
PERIOD_PS = 1000  # 1 GHz
BASE = os.path.abspath(
    "tests/fixtures/architectures/usecase_chip_trace_driven.yaml"
)

DESIGNS = {
    "A: MAC-heavy": {"mac": {"array_rows": 64, "array_cols": 64},
                     "avp": {"vector_width": 16}, "vau": {"lanes": 16},
                     "dsb": {"buffer_kb": 64}},
    "B: Balanced":  {"mac": {"array_rows": 32, "array_cols": 32},
                     "avp": {"vector_width": 32}, "vau": {"lanes": 32},
                     "dsb": {"buffer_kb": 128}},
    "C: Compact":   {"mac": {"array_rows": 16, "array_cols": 16},
                     "avp": {"vector_width": 16}, "vau": {"lanes": 16},
                     "dsb": {"buffer_kb": 32}},
}


def encoder_layer_ops() -> list[dict]:
    """One transformer-encoder layer as a SPEC-012 op list."""
    return [
        {"op_type": "matmul", "m": S, "k": D, "n": D, "precision": "int8"},  # q_proj
        {"op_type": "matmul", "m": S, "k": D, "n": D, "precision": "int8"},  # k_proj
        {"op_type": "matmul", "m": S, "k": D, "n": D, "precision": "int8"},  # v_proj
        {"op_type": "matmul", "m": S, "k": D, "n": S, "precision": "int8"},  # scores
        {"op_type": "softmax", "n_elements": H * S * S},                     # softmax
        {"op_type": "matmul", "m": S, "k": S, "n": D, "precision": "int8"},  # attn
        {"op_type": "matmul", "m": S, "k": D, "n": D, "precision": "int8"},  # out_proj
        {"op_type": "layernorm", "n_elements": S * D},                       # ln1
        {"op_type": "matmul", "m": S, "k": D, "n": F, "precision": "int8"},  # ffn1
        {"op_type": "gelu", "n_elements": S * F},                            # gelu
        {"op_type": "matmul", "m": S, "k": F, "n": D, "precision": "int8"},  # ffn2
        {"op_type": "layernorm", "n_elements": S * D},                       # ln2
    ]


def _build(overrides: dict):
    mods = {mid: {"config": cfg} for mid, cfg in overrides.items()}
    ov = {"schema_version": "1.0", "name": "design", "base": BASE,
          "overrides": {"modules": mods}}
    p = Path(tempfile.mkdtemp()) / "design.yaml"
    p.write_text(yaml.safe_dump(ov), encoding="utf-8")
    return elaborate(str(p))


def main() -> None:
    ops_dicts = encoder_layer_ops()
    ops = ops_from_list(ops_dicts)
    macs = sum(o["m"] * o["k"] * o["n"] for o in ops_dicts if o["op_type"] == "matmul")
    print(f"# Encoder layer: {len(ops)} ops | model = ×{N_LAYERS} layers")
    print(f"# matmul MACs/layer = {macs:,}  → model {macs*N_LAYERS/1e9:.2f} G-MAC\n")

    hdr = (f"{'design':14} | {'area mm²':>9} | {'cyc/layer':>10} | {'model ms':>9} "
           f"| {'dyn nJ/L':>10} | {'stat nJ/L':>9} | {'model mJ':>9}")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for name, ov in DESIGNS.items():
        arch = _build(ov)
        plan = RuleBasedMapper(strict=False).map(ops, arch)
        cyc = plan.total_typical_cycles
        dyn_pj = plan.total_dynamic_pj
        area_mm2 = chip_fidelity(arch).total_area_um2 / 1e6
        power_uw = sum(m.static_power_uw() for m in arch.modules.values())
        stat_pj = power_uw * (cyc * PERIOD_PS) * 1e-6
        model_ms = cyc * PERIOD_PS * 1e-12 * N_LAYERS * 1e3
        model_mj = (dyn_pj + stat_pj) / 1000 * N_LAYERS / 1e6
        rows.append((name, area_mm2, cyc, model_ms, model_mj))
        print(f"{name:14} | {area_mm2:9.2f} | {cyc:10,} | {model_ms:9.2f} "
              f"| {dyn_pj/1000:10.1f} | {stat_pj/1000:9.1f} | {model_mj:9.3f}")

    print("\n# best latency:", min(rows, key=lambda r: r[2])[0])
    print("# best area   :", min(rows, key=lambda r: r[1])[0])
    print("# best EDP    :", min(rows, key=lambda r: r[3] * r[4])[0])


if __name__ == "__main__":
    main()
