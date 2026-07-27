"""IMapper + RuleBasedMapper. Reference: SPEC-006.

Maps a flat ordered list of IOperations onto modules of an elaborated
IArchitecture using only the pure Mapper-facing API of SPEC-001 §3.2
(`can_execute` / `estimate_latency` / `estimate_energy`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.core.errors import NoMappingError
from npu_sim.interfaces.module import EnergyEstimate, IModule, LatencyEstimate
from npu_sim.interfaces.operation import IOperation


# ============================================================
# Dataclasses (SPEC-006 §2.1)
# ============================================================


@dataclass(frozen=True)
class MappingDecision:
    """One op → one module assignment. Reference: SPEC-006 §2.1."""

    op_index: int
    op_type: str
    module_id: str
    latency: LatencyEstimate
    energy: EnergyEstimate
    alternatives: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class MappingPlan:
    """Aggregate result of an IMapper.map() call. Reference: SPEC-006 §2.1."""

    decisions: tuple[MappingDecision, ...]
    total_typical_cycles: int
    total_dynamic_pj: float
    unmapped: tuple[int, ...] = ()
    summary_text: str = ""


# ============================================================
# Abstract interface (SPEC-006 §2)
# ============================================================


class IMapper(ABC):
    """Mapper contract. Reference: SPEC-006 §2."""

    @abstractmethod
    def map(
        self,
        operations: Sequence[IOperation],
        architecture: IArchitecture,
    ) -> MappingPlan:
        """Pure function: produce a MappingPlan from ops + architecture."""


# ============================================================
# RuleBasedMapper (SPEC-006 §3)
# ============================================================


class RuleBasedMapper(IMapper):
    """Single-op greedy rule-based mapper.

    Reference: SPEC-006 §3. For each IOperation, picks the module whose
    ``estimate_latency.typical_cycles`` is lowest, breaking ties by
    ``estimate_energy.dynamic_pj`` and then by ``module_id`` lexicographically
    so the result is deterministic regardless of dict insertion order.
    """

    def __init__(self, strict: bool = True) -> None:
        self._strict = strict

    def map(
        self,
        operations: Sequence[IOperation],
        architecture: IArchitecture,
    ) -> MappingPlan:
        decisions: list[MappingDecision] = []
        unmapped: list[int] = []

        for idx, op in enumerate(operations):
            ranked = self._rank_candidates(op, architecture.modules)
            if not ranked:
                if self._strict:
                    raise NoMappingError(
                        f"No module can execute op#{idx} ({op.op_type!r}); "
                        f"required={list(op.required_capabilities)}; "
                        f"available="
                        f"{ {mid: m.active_capabilities() for mid, m in architecture.modules.items()} }"
                    )
                unmapped.append(idx)
                continue

            chosen_id, chosen_mod = ranked[0]
            latency = chosen_mod.estimate_latency(op)
            energy = chosen_mod.estimate_energy(op)
            alts = tuple(mid for mid, _ in ranked[1:])
            decisions.append(
                MappingDecision(
                    op_index=idx,
                    op_type=op.op_type,
                    module_id=chosen_id,
                    latency=latency,
                    energy=energy,
                    alternatives=alts,
                    rationale=(
                        f"chose {chosen_id}: typical {latency.typical_cycles} cyc, "
                        f"{energy.dynamic_pj:.2f} pJ"
                        + (f" (vs {list(alts)})" if alts else "")
                    ),
                )
            )

        total_cycles = sum(d.latency.typical_cycles for d in decisions)
        total_pj = sum(d.energy.dynamic_pj for d in decisions)

        return MappingPlan(
            decisions=tuple(decisions),
            total_typical_cycles=total_cycles,
            total_dynamic_pj=total_pj,
            unmapped=tuple(unmapped),
            summary_text=_format_summary(decisions, total_cycles, total_pj, unmapped),
        )

    # ============== helpers ==============

    @staticmethod
    def _rank_candidates(
        op: IOperation,
        modules: dict[str, IModule],
    ) -> list[tuple[str, IModule]]:
        """Return (module_id, module) pairs sorted by SPEC-006 §3.2 keys.

        A module is a candidate iff every required capability of the op is in
        the module's active_capabilities (SPEC-001 §3.1 / SPEC-006 §3.2 — the
        authoritative Mapper↔Module contract). This is checked directly
        rather than via can_execute() because stimulus / infrastructure
        modules (TraceProducer, Producer, NoC, PMU, ...) implement
        can_execute() loosely (return True), which would wrongly make them
        compute targets.
        """
        required = set(op.required_capabilities)
        candidates = [
            (mid, mod)
            for mid, mod in modules.items()
            if required.issubset(set(mod.active_capabilities()))
        ]
        return sorted(
            candidates,
            key=lambda pair: (
                pair[1].estimate_latency(op).typical_cycles,
                pair[1].estimate_energy(op).dynamic_pj,
                pair[0],
            ),
        )


# ============================================================
# Summary rendering (SPEC-006 §5)
# ============================================================


def _format_summary(
    decisions: Sequence[MappingDecision],
    total_cycles: int,
    total_pj: float,
    unmapped: Sequence[int],
) -> str:
    lines = ["MappingPlan:"]
    for d in decisions:
        lines.append(
            f"  op#{d.op_index} {d.op_type!r:>14} → {d.module_id:<10} "
            f"{d.latency.typical_cycles:>6d} cyc  {d.energy.dynamic_pj:>9.2f} pJ"
        )
    lines.append(
        f"  total: {total_cycles} typical cycles, "
        f"{total_pj:.2f} pJ dynamic, {len(unmapped)} unmapped"
    )
    return "\n".join(lines)
