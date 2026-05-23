"""Tests for the DSL YAML loader. Reference: SPEC-003 §5 Phase 1, §6.3."""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.architecture.loader import load_dsl
from npu_sim.core.errors import OverrideError


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestBasicLoading:

    def test_baseline_loads(self):
        merged, warnings = load_dsl(str(FIXTURES / "baseline_dummy.yaml"))
        assert merged["name"] == "Dummy baseline"
        assert len(merged["modules"]) == 2
        assert warnings == []

    def test_variant_inherits_baseline(self):
        merged, _ = load_dsl(str(FIXTURES / "variant_throughput_half.yaml"))
        producer = next(m for m in merged["modules"] if m["id"] == "producer")
        assert producer["config"]["throughput_elems_per_cycle"] == 1
        # other producer fields preserved
        assert producer["config"]["support_extra"] is True

    def test_variant_name_overrides_baseline(self):
        merged, _ = load_dsl(str(FIXTURES / "variant_throughput_half.yaml"))
        # Identity belongs to the variant, not the base.
        assert merged["name"] == "Dummy - half throughput"

    def test_variant_brings_baseline_connections_along(self):
        merged, _ = load_dsl(str(FIXTURES / "variant_throughput_half.yaml"))
        assert len(merged["connections"]) == 1


class TestChainInheritanceBan:
    """SPEC-003 §6.3 / ADR-001.2 v0.2 constraint."""

    def test_intermediate_alone_still_works(self):
        # The intermediate file by itself is fine — it bases on the real baseline.
        merged, _ = load_dsl(str(FIXTURES / "variant_intermediate.yaml"))
        producer = next(m for m in merged["modules"] if m["id"] == "producer")
        assert producer["config"]["throughput_elems_per_cycle"] == 4

    def test_chain_rejected(self):
        # variant_chain_final.yaml bases on variant_intermediate.yaml (which itself
        # has a base) — must be rejected.
        with pytest.raises(OverrideError, match="Chain inheritance"):
            load_dsl(str(FIXTURES / "variant_chain_final.yaml"))


class TestBaseFileResolution:

    def test_missing_file_raises_override_error(self):
        # A YAML referencing a nonexistent base.
        target = FIXTURES / "_missing_base_tmp.yaml"
        target.write_text(
            'schema_version: "1.0"\n'
            'name: "Missing"\n'
            'base: does_not_exist.yaml\n'
            'overrides: {}\n'
        )
        try:
            with pytest.raises(OverrideError, match="not found"):
                load_dsl(str(target))
        finally:
            target.unlink()
