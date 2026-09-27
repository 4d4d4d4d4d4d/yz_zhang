"""Load an operator trace (SPEC-012 `ops` format) into IOperations.

The same inline op-list that drives TraceProducer (dynamic stimulus) is
turned here into StaticOperations for the RuleBasedMapper (static
estimate). This connects trace-driven simulation and Mapper estimation:
one trace file feeds both.

Op-type → required-capability convention matches the SPEC-005/006 module
capability names (matmul→int8_matmul, relu→relu, softmax→softmax, ...).
"""

from __future__ import annotations

from typing import Any

import yaml

from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation


# op_type → required capability. Precision-sensitive ops (matmul) are
# resolved dynamically below.
_OP_CAP = {
    "relu": "relu",
    "gelu": "gelu",
    "softmax": "softmax",
    "layernorm": "layernorm",
    "bfp8_unpack": "bfp8_unpack",
    "bfp16_unpack": "bfp16_unpack",
    "exp": "exp",
    "rsqrt": "rsqrt",
    "div": "div",
}

_PRECISION_KIND = {
    "int8": PrecisionKind.INT8,
    "int16": PrecisionKind.INT16,
    "int32": PrecisionKind.INT32,
    "fp16": PrecisionKind.FP16,
    "bf16": PrecisionKind.BF16,
    "fp32": PrecisionKind.FP32,
    "bfp8": PrecisionKind.BFP8,
    "bfp16": PrecisionKind.BFP16,
}


def _matmul_capability(prec: str) -> str:
    if prec in ("bf16", "bfp16"):
        return "bfp16_matmul"
    if prec == "fp16":
        return "fp16_matmul"
    return "int8_matmul"


def _op_to_static(op: dict[str, Any], index: int) -> StaticOperation:
    op_type = op.get("op_type", "unknown")
    prec_name = op.get("precision", "fp32")
    prec = Precision(kind=_PRECISION_KIND.get(prec_name, PrecisionKind.FP32))

    if op_type == "matmul":
        cap = _matmul_capability(prec_name)
    else:
        cap = _OP_CAP.get(op_type, op_type)

    shape = tuple(
        (k, int(v))
        for k, v in op.items()
        if k not in ("op_type", "precision") and isinstance(v, (int, float))
    )
    return StaticOperation(
        _op_type=op_type,
        _required_capabilities=(cap,),
        _shape_info=shape,
        _precision=prec,
    )


def ops_from_list(ops: list[dict]) -> list[StaticOperation]:
    """Convert an inline SPEC-012 ops list into StaticOperations."""
    return [_op_to_static(op, i) for i, op in enumerate(ops)]


def load_ops(path: str) -> list[StaticOperation]:
    """Load ops from a YAML file.

    Accepts either a top-level ``ops:`` list, or a full architecture YAML
    whose ``modules`` contains a TraceProducer with ``config.ops`` (so an
    existing trace fixture can be reused directly).
    """
    with open(path) as f:
        doc = yaml.safe_load(f)
    if isinstance(doc, dict) and "ops" in doc:
        return ops_from_list(doc["ops"])
    if isinstance(doc, dict) and "modules" in doc:
        for m in doc["modules"]:
            if m.get("type") == "TraceProducer":
                return ops_from_list(m.get("config", {}).get("ops", []))
    raise ValueError(
        f"{path}: no top-level `ops:` and no TraceProducer with config.ops found"
    )
