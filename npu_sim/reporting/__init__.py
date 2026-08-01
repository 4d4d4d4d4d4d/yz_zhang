"""Render simulation / comparison results as Markdown."""

from npu_sim.reporting.markdown import (
    render_comparison_report,
    render_mapping_report,
    render_pipeline_bottleneck,
    render_reconcile_report,
    render_simulation_report,
    render_snapshot_diff,
    render_state_snapshot,
)

__all__ = [
    "render_comparison_report",
    "render_mapping_report",
    "render_pipeline_bottleneck",
    "render_reconcile_report",
    "render_simulation_report",
    "render_snapshot_diff",
    "render_state_snapshot",
]
