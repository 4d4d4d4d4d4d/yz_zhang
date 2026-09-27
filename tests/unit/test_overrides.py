"""Tests for the override merger. Reference: SPEC-003 §6 (v0.2)."""

from __future__ import annotations

import copy

import pytest

from npu_sim.architecture.overrides import apply_overrides
from npu_sim.core.errors import OverrideError


def _baseline() -> dict:
    """A tiny baseline dict used by most override tests."""
    return {
        "schema_version": "1.0",
        "name": "base",
        "modules": [
            {
                "id": "a",
                "type": "Dummy",
                "config": {
                    "throughput_elems_per_cycle": 2,
                    "support_extra": True,
                    "precision_modes": ["INT8", "FP16"],
                },
            },
            {"id": "b", "type": "Dummy", "config": {"throughput_elems_per_cycle": 1}},
        ],
        "connections": [
            {"from": "a.out_data", "to": "b.in_data", "fifo_depth": 4, "latency_cycles": 1},
        ],
    }


class TestScalarAndDictMerge:

    def test_scalar_override_replaces_value(self):
        merged, _ = apply_overrides(
            _baseline(),
            {"modules": {"a": {"config": {"throughput_elems_per_cycle": 8}}}},
        )
        a_cfg = next(m for m in merged["modules"] if m["id"] == "a")["config"]
        assert a_cfg["throughput_elems_per_cycle"] == 8
        # Other fields untouched
        assert a_cfg["support_extra"] is True

    def test_does_not_mutate_inputs(self):
        base = _baseline()
        base_snapshot = copy.deepcopy(base)
        overrides = {"modules": {"a": {"config": {"throughput_elems_per_cycle": 8}}}}
        overrides_snapshot = copy.deepcopy(overrides)
        apply_overrides(base, overrides)
        assert base == base_snapshot
        assert overrides == overrides_snapshot

    def test_override_non_existent_module_errors(self):
        with pytest.raises(OverrideError, match="non-existent module"):
            apply_overrides(
                _baseline(),
                {"modules": {"nonexistent": {"config": {"x": 1}}}},
            )

    def test_clock_replacement(self):
        merged, _ = apply_overrides(
            _baseline(),
            {"modules": {"a": {"clock": "slow_clk"}}},
        )
        assert next(m for m in merged["modules"] if m["id"] == "a")["clock"] == "slow_clk"


class TestListMerge:
    """SPEC-003 §6 v0.2: __append__ / __remove__ markers."""

    def test_default_list_replace(self):
        merged, _ = apply_overrides(
            _baseline(),
            {"modules": {"a": {"config": {"precision_modes": ["FP8"]}}}},
        )
        a_cfg = next(m for m in merged["modules"] if m["id"] == "a")["config"]
        assert a_cfg["precision_modes"] == ["FP8"]

    def test_append_extends_list(self):
        merged, _ = apply_overrides(
            _baseline(),
            {"modules": {"a": {"config": {"precision_modes": {"__append__": ["FP8"]}}}}},
        )
        a_cfg = next(m for m in merged["modules"] if m["id"] == "a")["config"]
        assert a_cfg["precision_modes"] == ["INT8", "FP16", "FP8"]

    def test_remove_filters_list(self):
        merged, _ = apply_overrides(
            _baseline(),
            {"modules": {"a": {"config": {"precision_modes": {"__remove__": ["FP16"]}}}}},
        )
        a_cfg = next(m for m in merged["modules"] if m["id"] == "a")["config"]
        assert a_cfg["precision_modes"] == ["INT8"]

    def test_remove_then_append(self):
        merged, _ = apply_overrides(
            _baseline(),
            {
                "modules": {
                    "a": {
                        "config": {
                            "precision_modes": {
                                "__remove__": ["FP16"],
                                "__append__": ["FP8"],
                            }
                        }
                    }
                }
            },
        )
        a_cfg = next(m for m in merged["modules"] if m["id"] == "a")["config"]
        assert a_cfg["precision_modes"] == ["INT8", "FP8"]

    def test_unknown_marker_errors(self):
        with pytest.raises(OverrideError, match="Unsupported list-merge keys"):
            apply_overrides(
                _baseline(),
                {"modules": {"a": {"config": {"precision_modes": {"__insert__": ["FP8"]}}}}},
            )


class TestRemoveModules:
    """SPEC-003 §6 v0.2 D3: auto-prune dangling connections with warning."""

    def test_remove_module_drops_it(self):
        merged, _ = apply_overrides(_baseline(), {"remove_modules": ["b"]})
        ids = {m["id"] for m in merged["modules"]}
        assert "b" not in ids
        assert "a" in ids

    def test_remove_module_auto_prunes_connections(self):
        merged, warnings = apply_overrides(_baseline(), {"remove_modules": ["b"]})
        assert merged["connections"] == []
        assert any("auto-pruned" in w for w in warnings)
        assert any("'b'" in w or "b" in w for w in warnings)

    def test_remove_unknown_module_errors(self):
        with pytest.raises(OverrideError, match="non-existent"):
            apply_overrides(_baseline(), {"remove_modules": ["ghost"]})

    def test_keeps_unaffected_connections(self):
        base = _baseline()
        base["modules"].append({"id": "c", "type": "Dummy", "config": {"throughput_elems_per_cycle": 1}})
        base["connections"].append(
            {"from": "b.out_data", "to": "c.in_data", "fifo_depth": 1, "latency_cycles": 1}
        )

        merged, warnings = apply_overrides(base, {"remove_modules": ["a"]})

        # Only connection a→b should be pruned; b→c remains.
        remaining = [(c["from"], c["to"]) for c in merged["connections"]]
        assert remaining == [("b.out_data", "c.in_data")]
        assert any("auto-pruned" in w for w in warnings)


class TestAddModules:

    def test_add_module_appended(self):
        merged, _ = apply_overrides(
            _baseline(),
            {
                "add_modules": [
                    {"id": "c", "type": "Dummy", "config": {"throughput_elems_per_cycle": 1}},
                ]
            },
        )
        assert {m["id"] for m in merged["modules"]} == {"a", "b", "c"}

    def test_add_module_duplicate_id_errors(self):
        with pytest.raises(OverrideError, match="already exists"):
            apply_overrides(
                _baseline(),
                {"add_modules": [{"id": "a", "type": "Dummy", "config": {}}]},
            )


class TestAddConnections:
    """SPEC-003 §6 v0.2 D3: add_connections to removed modules errors."""

    def test_add_connection_to_unknown_module_errors(self):
        with pytest.raises(OverrideError, match="non-existent"):
            apply_overrides(
                _baseline(),
                {
                    "add_connections": [
                        {"from": "a.out_data", "to": "ghost.in_data", "fifo_depth": 1, "latency_cycles": 1},
                    ]
                },
            )

    def test_remove_then_add_to_removed_module_errors(self):
        """Common harness for module fusion typos."""
        with pytest.raises(OverrideError, match="non-existent"):
            apply_overrides(
                _baseline(),
                {
                    "remove_modules": ["b"],
                    "add_connections": [
                        {"from": "a.out_data", "to": "b.in_data", "fifo_depth": 1, "latency_cycles": 1},
                    ],
                },
            )

    def test_add_connection_ok(self):
        merged, _ = apply_overrides(
            _baseline(),
            {
                "add_modules": [{"id": "c", "type": "Dummy", "config": {"throughput_elems_per_cycle": 1}}],
                "add_connections": [
                    {"from": "b.out_data", "to": "c.in_data", "fifo_depth": 1, "latency_cycles": 1},
                ],
            },
        )
        pairs = [(c["from"], c["to"]) for c in merged["connections"]]
        assert ("b.out_data", "c.in_data") in pairs


class TestRemoveConnections:

    def test_remove_connection_by_endpoint_pair(self):
        merged, _ = apply_overrides(
            _baseline(),
            {
                "remove_connections": [
                    {"from": "a.out_data", "to": "b.in_data"},
                ]
            },
        )
        assert merged["connections"] == []

    def test_remove_nonexistent_connection_is_noop(self):
        merged, _ = apply_overrides(
            _baseline(),
            {
                "remove_connections": [
                    {"from": "a.out_data", "to": "nowhere.in_data"},
                ]
            },
        )
        assert len(merged["connections"]) == 1


class TestMappingHints:

    def test_replaces_wholesale(self):
        base = _baseline()
        base["mapping_hints"] = {"old_op": {"stage_1": "a"}}
        merged, _ = apply_overrides(
            base,
            {"mapping_hints": {"new_op": {"stage_1": "b"}}},
        )
        # Wholesale replacement, not merge.
        assert merged["mapping_hints"] == {"new_op": {"stage_1": "b"}}
