"""Chip-level fidelity report — how much of the PPA is physically grounded.

Answers "is this real?" for any elaborated chip: it classifies each module's
area model as physically grounded (SPEC-013 literature-derived), hybrid
(part physical + part placeholder), or a `[calibration knob]` placeholder,
and reports what fraction of total chip area rests on grounded models.

Classification is read from each module's ``estimate_area().notes`` — the
same provenance string the modules already carry — so it stays correct
automatically as more modules migrate. No fabrication: a module is only
called "physical" if its own note says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from npu_sim.architecture.architecture import IArchitecture


@dataclass(frozen=True)
class ModuleFidelity:
    module_id: str
    module_type: str
    area_um2: float
    status: str          # "physical" | "hybrid" | "placeholder"
    note: str


@dataclass(frozen=True)
class ChipFidelityReport:
    modules: tuple[ModuleFidelity, ...]
    total_area_um2: float
    grounded_area_um2: float          # physical + hybrid
    grounded_pct: float
    summary_text: str = ""


def _classify(note: str) -> str:
    has_physical = "SPEC-013" in note
    has_placeholder = "calibration knob" in note
    if has_physical and has_placeholder:
        return "hybrid"
    if has_physical:
        return "physical"
    return "placeholder"


def chip_fidelity(architecture: IArchitecture) -> ChipFidelityReport:
    """Per-module area + physical/placeholder status for an elaborated chip."""
    mods: list[ModuleFidelity] = []
    total = 0.0
    grounded = 0.0
    for mid, m in architecture.modules.items():
        area_model = m.estimate_area()
        area = area_model.um2
        status = _classify(area_model.notes or "")
        total += area
        if status in ("physical", "hybrid"):
            grounded += area
        mods.append(ModuleFidelity(
            module_id=mid,
            module_type=m.module_type(),
            area_um2=area,
            status=status,
            note=area_model.notes or "",
        ))

    mods.sort(key=lambda x: (-x.area_um2, x.module_id))
    pct = (grounded / total * 100.0) if total > 0 else 0.0

    n_phys = sum(1 for x in mods if x.status == "physical")
    n_hy = sum(1 for x in mods if x.status == "hybrid")
    n_ph = sum(1 for x in mods if x.status == "placeholder")
    lines = [
        f"Chip fidelity: {pct:.0f}% of area on physically-grounded models",
        f"  modules: {n_phys} physical, {n_hy} hybrid, {n_ph} placeholder",
        f"  total area: {total:,.0f} µm²  (grounded: {grounded:,.0f} µm²)",
    ]
    return ChipFidelityReport(
        modules=tuple(mods),
        total_area_um2=total,
        grounded_area_um2=grounded,
        grounded_pct=pct,
        summary_text="\n".join(lines),
    )
