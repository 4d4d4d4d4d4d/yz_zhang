"""Override merging logic.

Implements SPEC-003 §6 with v0.2 additions:
- `__remove__` / `__append__` for list-valued config fields (R6#4)
- `remove_modules` auto-prunes dangling connections, producing a warning (D3)
- `add_connections` referencing absent modules is an error (D3)
- `mapping_hints` reachability validated downstream by Elaborator (D2)
"""

from __future__ import annotations

import copy
from typing import Any

from npu_sim.core.errors import OverrideError


def _merge_config_value(base_value: Any, override_value: Any) -> Any:
    """Merge a single config entry.

    Rules per SPEC-003 §6:
    - dict on both sides: shallow merge (recursive entry-by-entry)
    - list with `__append__` / `__remove__` markers: apply in order remove-then-append
    - dict-with-unknown-`__marker__` on a list base: raise (catches typos like `__insert__`)
    - else: override wins
    """

    # Special list-merge markers carried inside a dict on the override side.
    if isinstance(override_value, dict) and isinstance(base_value, list):
        has_marker = any(
            k.startswith("__") and k.endswith("__") for k in override_value.keys()
        )
        if has_marker:
            unknown = override_value.keys() - {"__append__", "__remove__"}
            if unknown:
                raise OverrideError(
                    f"Unsupported list-merge keys {sorted(unknown)}; "
                    f"only __append__ / __remove__ are allowed."
                )
            result = list(base_value)
            # __remove__ first, then __append__ (SPEC-003 §6.1).
            for v in override_value.get("__remove__", []):
                while v in result:
                    result.remove(v)
            for v in override_value.get("__append__", []):
                result.append(v)
            return result

    if isinstance(base_value, dict) and isinstance(override_value, dict):
        merged = dict(base_value)
        for k, v in override_value.items():
            if k in merged:
                merged[k] = _merge_config_value(merged[k], v)
            else:
                merged[k] = v
        return merged

    return override_value


def _module_endpoints(connection: dict) -> tuple[str, str]:
    """Return (source_module_id, sink_module_id) from a connection dict."""
    return connection["from"].split(".")[0], connection["to"].split(".")[0]


def apply_overrides(
    base: dict,
    overrides: dict,
) -> tuple[dict, list[str]]:
    """Apply `overrides` on top of a deep copy of `base`.

    Returns (merged_dict, warnings).

    Side effects: never mutates `base` or `overrides`.
    """

    if not overrides:
        return copy.deepcopy(base), []

    result = copy.deepcopy(base)
    warnings: list[str] = []

    # ---- 1. modules.<id>.config / clock override ----

    if "modules" in overrides:
        if "modules" not in result:
            raise OverrideError(
                "Cannot override modules: base has no `modules` list."
            )
        by_id = {m["id"]: m for m in result["modules"]}
        for mod_id, mod_override in overrides["modules"].items():
            existing = by_id.get(mod_id)
            if existing is None:
                raise OverrideError(
                    f"Cannot override non-existent module: {mod_id!r}. "
                    f"Available: {sorted(by_id)}."
                )

            if "config" in mod_override:
                existing_cfg = existing.setdefault("config", {})
                for k, v in mod_override["config"].items():
                    if k in existing_cfg:
                        existing_cfg[k] = _merge_config_value(existing_cfg[k], v)
                    else:
                        existing_cfg[k] = v

            if "clock" in mod_override:
                existing["clock"] = mod_override["clock"]

    # ---- 2. remove_modules + auto-prune dangling connections (D3) ----

    if "remove_modules" in overrides:
        removed_ids = set(overrides["remove_modules"])
        if not removed_ids:
            pass
        else:
            existing_ids = {m["id"] for m in result.get("modules", [])}
            missing = removed_ids - existing_ids
            if missing:
                raise OverrideError(
                    f"remove_modules references non-existent module(s): "
                    f"{sorted(missing)}."
                )

            result["modules"] = [
                m for m in result["modules"] if m["id"] not in removed_ids
            ]

            dangling: list[dict] = []
            kept: list[dict] = []
            for c in result.get("connections", []):
                src, dst = _module_endpoints(c)
                if src in removed_ids or dst in removed_ids:
                    dangling.append(c)
                else:
                    kept.append(c)

            if dangling:
                warnings.append(
                    f"removed modules {sorted(removed_ids)} had "
                    f"{len(dangling)} dangling connections, auto-pruned: "
                    f"{[(c['from'], c['to']) for c in dangling]}. "
                    f"If intentional, add them to remove_connections explicitly."
                )
                result["connections"] = kept

            # Also prune the modules' entries from topology.dies (same D3 spirit).
            topology = result.get("topology")
            if topology and "dies" in topology:
                pruned_dies: list[str] = []
                for die in topology["dies"]:
                    original_count = len(die.get("modules", []))
                    die["modules"] = [
                        mid for mid in die.get("modules", [])
                        if mid not in removed_ids
                    ]
                    if len(die["modules"]) < original_count:
                        pruned_dies.append(die["id"])
                if pruned_dies:
                    warnings.append(
                        f"removed modules {sorted(removed_ids)} auto-pruned from "
                        f"topology dies: {pruned_dies}."
                    )

    # ---- 3. add_modules ----

    if "add_modules" in overrides:
        existing_ids = {m["id"] for m in result.get("modules", [])}
        for new_mod in overrides["add_modules"]:
            if new_mod["id"] in existing_ids:
                raise OverrideError(
                    f"add_modules id {new_mod['id']!r} already exists."
                )
            existing_ids.add(new_mod["id"])
        result.setdefault("modules", []).extend(
            copy.deepcopy(overrides["add_modules"])
        )

    # ---- 4. remove_connections ----

    if "remove_connections" in overrides:
        to_remove = {
            (c["from"], c["to"]) for c in overrides["remove_connections"]
        }
        result["connections"] = [
            c
            for c in result.get("connections", [])
            if (c["from"], c["to"]) not in to_remove
        ]

    # ---- 5. add_connections (D3: error on non-existent module refs) ----

    if "add_connections" in overrides:
        existing_ids = {m["id"] for m in result.get("modules", [])}
        for c in overrides["add_connections"]:
            src, dst = _module_endpoints(c)
            missing = [m for m in (src, dst) if m not in existing_ids]
            if missing:
                raise OverrideError(
                    f"add_connections references non-existent module(s): "
                    f"{missing}. connection: {c['from']} → {c['to']}"
                )
        result.setdefault("connections", []).extend(
            copy.deepcopy(overrides["add_connections"])
        )

    # ---- 6. mapping_hints (replace; deeper validation in Elaborator) ----

    if "mapping_hints" in overrides:
        result["mapping_hints"] = copy.deepcopy(overrides["mapping_hints"])

    return result, warnings
