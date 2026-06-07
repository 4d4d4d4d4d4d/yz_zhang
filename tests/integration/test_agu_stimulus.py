"""SPEC-007 §7 — MAC/DSB/AGU algorithm-stimulus use case.

The "MAC/DSB/AGU 算法激励" item in the 2026-06-04 evaluation list:
sweep AGU pipeline_depth against client (MAC/DSB) array size and observe
how the stall to the client behaves. The §7.3.1 contract is "1 addr/cycle
steady-state"; pipeline_depth drives the fill-stage stall.
"""

from __future__ import annotations

import pytest

from npu_sim.core.errors import ConfigurationError
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
from npu_sim.architecture.clock import SimpleClock
from npu_sim.modules.control.agu_module import AGU


def _bind(client_id: str = "mac_0", pipeline_depth: int = 3) -> AGU:
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    clock = SimpleClock("global", period_ps=1000)
    a = AGU()
    a.bind_services(event_bus=bus, stat_sink=sink, clock=clock)
    a.configure({"client_module_id": client_id, "agu_pipeline_depth": pipeline_depth})
    return a


def _op(n_addresses: int = 256):
    return StaticOperation(
        _op_type="addr_loop",
        _required_capabilities=("inner_loop_address_gen",),
        _shape_info=(("n_addresses", n_addresses),),
        _precision=Precision(kind=PrecisionKind.INT8),
    )


class TestAGUStimulus:
    """§7.3 pipeline_depth sweep."""

    @pytest.mark.parametrize("depth", [1, 2, 3, 4, 8])
    def test_fill_stall_equals_depth_minus_one(self, depth):
        """§7.3.1: fill stalls client by (pipeline_depth - 1) cycles."""
        agu = _bind(pipeline_depth=depth)
        assert agu.estimate_stall_to_client() == depth - 1

    def test_steady_state_throughput_is_one_addr_per_cycle(self):
        """§7.3.1: amortised over many addresses, fill stall vanishes."""
        agu = _bind(pipeline_depth=3)
        n = 1024
        cycles = agu.estimate_latency(_op(n_addresses=n)).typical_cycles
        # fill (3) + steady (n) = 3 + 1024.
        # Throughput → 1.0 addrs/cycle as n grows.
        throughput = n / cycles
        assert throughput > 0.99, (
            f"§7.3.1: AGU throughput {throughput:.3f} addrs/cycle below 0.99"
        )

    def test_deeper_pipeline_costs_more_fill(self):
        """Stimulus: depth=8 should fill-stall 7 cycles, depth=1 stalls 0."""
        shallow = _bind(pipeline_depth=1)
        deep = _bind(pipeline_depth=8)
        c_shallow = shallow.estimate_latency(_op(n_addresses=32)).typical_cycles
        c_deep = deep.estimate_latency(_op(n_addresses=32)).typical_cycles
        assert c_deep - c_shallow == 7

    def test_agu_rejects_missing_client(self):
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
        from npu_sim.architecture.clock import SimpleClock

        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        clock = SimpleClock("global", period_ps=1000)
        a = AGU()
        a.bind_services(event_bus=bus, stat_sink=sink, clock=clock)
        with pytest.raises(ConfigurationError, match="§7.1.2"):
            a.configure({"agu_pipeline_depth": 3})


class TestControlModuleRegistration:
    def test_all_six_spec007_modules_registered(self):
        from npu_sim.core.module_registry import ModuleRegistry
        registered = set(ModuleRegistry.list_modules())
        for required in ["MCU", "OGU", "TAU", "DMA", "MTU", "AGU"]:
            assert required in registered, f"{required} not registered"
