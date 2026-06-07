"""SPEC-007 §6.3 — MTU 融合 TAU/DMA use case.

Formal pass criterion (§6.3.1):

    T_mtu(op) ≤ T_tau(op) + T_dma(op) - overlap_savings
    overlap_savings ≥ min(T_tau, T_dma) × 0.8

And §6.4.1 / §6.5: MTU area < TAU + DMA area (one-die saving).
"""

from __future__ import annotations

import pytest

from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
from npu_sim.architecture.clock import SimpleClock
from npu_sim.modules.control.dma_module import DMA
from npu_sim.modules.control.mtu_module import MTU
from npu_sim.modules.control.tau_module import TAU


def _bind(module):
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    clock = SimpleClock("global", period_ps=1000)
    module.bind_services(event_bus=bus, stat_sink=sink, clock=clock)
    return module


def _op(bursts=64, payload_bytes=4096):
    return StaticOperation(
        _op_type="transfer",
        _required_capabilities=("bulk_memory_transfer",),
        _shape_info=(("bursts", bursts), ("payload_bytes", payload_bytes)),
        _precision=Precision(kind=PrecisionKind.INT8),
    )


class TestMTUOverlap:
    """§6.3.1 overlap_savings ≥ 80% × min(T_tau, T_dma)."""

    def test_mtu_saves_at_least_80pct_of_min_segment(self):
        tau = _bind(TAU()); tau.configure({})
        dma = _bind(DMA()); dma.configure({})
        mtu = _bind(MTU()); mtu.configure({})
        op = _op()

        t_tau = tau.estimate_latency(op).typical_cycles
        t_dma = dma.estimate_latency(op).typical_cycles
        t_mtu = mtu.estimate_latency(op).typical_cycles

        savings = (t_tau + t_dma) - t_mtu
        min_seg = min(t_tau, t_dma)
        assert savings >= min_seg * 0.8, (
            f"§6.3.1: MTU overlap savings {savings} cycles < 80% of "
            f"min(T_tau={t_tau}, T_dma={t_dma}) = {min_seg * 0.8:.0f}"
        )

    def test_mtu_never_slower_than_max_segment(self):
        """T_mtu ≥ max(T_tau, T_dma) (overlap cannot beat the slower segment)."""
        tau = _bind(TAU()); tau.configure({})
        dma = _bind(DMA()); dma.configure({})
        mtu = _bind(MTU()); mtu.configure({})
        op = _op()
        t_tau = tau.estimate_latency(op).typical_cycles
        t_dma = dma.estimate_latency(op).typical_cycles
        t_mtu = mtu.estimate_latency(op).typical_cycles
        assert t_mtu >= max(t_tau, t_dma)


class TestMTUArea:
    """§6.4.1 / §6.5: MTU area < TAU + DMA area."""

    def test_mtu_area_less_than_sum_of_tau_dma(self):
        tau = _bind(TAU()); tau.configure({})
        dma = _bind(DMA()); dma.configure({})
        mtu = _bind(MTU()); mtu.configure({})
        a_tau = tau.estimate_area().um2
        a_dma = dma.estimate_area().um2
        a_mtu = mtu.estimate_area().um2
        assert a_mtu < a_tau + a_dma, (
            f"§6.4.1: MTU {a_mtu} ≥ TAU {a_tau} + DMA {a_dma}"
        )
        # Target: ≥10% saving vs split design.
        savings_pct = 100.0 * ((a_tau + a_dma) - a_mtu) / (a_tau + a_dma)
        assert savings_pct >= 5.0


class TestMTUCapabilitySet:
    """§6.5: MTU declares both TAU and DMA capabilities."""

    def test_mtu_has_both_capabilities(self):
        mtu = _bind(MTU()); mtu.configure({})
        active = set(mtu.active_capabilities())
        assert "tensor_address_gen" in active
        assert "bulk_memory_transfer" in active
