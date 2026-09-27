"""YAML loader for the architecture DSL.

Implements SPEC-003 §5 Phase 1 (load + merge) and §6.3 chain-inheritance ban.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from npu_sim.architecture.overrides import apply_overrides
from npu_sim.core.errors import OverrideError


def _read_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return yaml.safe_load(fp) or {}
    except FileNotFoundError as e:
        raise OverrideError(f"DSL file not found: {path}") from e


def _resolve_base(parent_path: str, base_ref: str) -> str:
    """Resolve `base` relative to the parent file's directory."""
    if os.path.isabs(base_ref):
        return base_ref
    return str(Path(parent_path).parent / base_ref)


def load_dsl(path: str) -> tuple[dict, list[str]]:
    """Load a DSL file. If it has a `base`, load that and apply `overrides`.

    Enforces SPEC-003 §6.3 chain inheritance ban: the base file must not
    itself have a `base` field.

    Returns (merged_dict, warnings).
    """

    raw = _read_yaml(path)

    if "base" not in raw:
        return raw, []

    base_path = _resolve_base(path, raw["base"])
    base_raw = _read_yaml(base_path)

    if "base" in base_raw:
        raise OverrideError(
            f"Chain inheritance not allowed: {path} → {raw['base']} → "
            f"{base_raw['base']}. Promote intermediate variant to a new "
            f"baseline first, or flatten into a single override layer. "
            f"See SPEC-003 §6.3 / ADR-001.2."
        )

    merged, warnings = apply_overrides(base_raw, raw.get("overrides", {}))

    # Variant-level fields override the base file's identity / metadata so
    # reports reflect the variant rather than the base.
    for key in ("schema_version", "name", "description", "metadata"):
        if key in raw:
            merged[key] = raw[key]

    return merged, warnings
