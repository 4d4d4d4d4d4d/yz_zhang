"""Functional (numerical) comparator. Reference: SPEC-004 §5.

Compares an *expected* tensor against an *actual* tensor under a per-output
``Tolerance`` and returns a ``numerical.ComparisonResult``. Pure function:
no mutation of inputs.

Metrics computed (SPEC-004 §5.1-§5.2):
- ``max_abs_error``: max(|expected - actual|)
- ``max_rel_error``: max(|expected - actual| / max(|expected|, eps))
- ``mean_abs_error``: mean(|expected - actual|)
- ``cosine_similarity``: dot(flat_expected, flat_actual) / (||·|| ||·||)
- ``outliers_pct``: 100 * fraction of elements that fail np.isclose under rtol/atol
"""

from __future__ import annotations

import numpy as np

from npu_sim.interfaces.numerical import (
    ComparisonResult,
    Tensor,
    Tolerance,
    ToleranceViolation,
)


_EPS = np.float64(1e-12)


def compare_tensors(
    expected: Tensor,
    actual: Tensor,
    tolerance: Tolerance,
) -> ComparisonResult:
    """Compare two Tensors under the given tolerance.

    Reference: SPEC-004 §5.1 (per-output metric set), §5.2 (Tolerance).
    """
    if expected.shape != actual.shape:
        return ComparisonResult(
            passed=False,
            metrics={},
            violations=[
                ToleranceViolation(
                    metric="shape",
                    actual=float(np.prod(actual.shape)),
                    threshold=float(np.prod(expected.shape)),
                )
            ],
            sample_diff=None,
        )

    exp = np.asarray(expected.data, dtype=np.float64)
    act = np.asarray(actual.data, dtype=np.float64)
    diff = exp - act
    abs_diff = np.abs(diff)

    max_abs = float(abs_diff.max()) if abs_diff.size else 0.0
    mean_abs = float(abs_diff.mean()) if abs_diff.size else 0.0
    denom = np.maximum(np.abs(exp), _EPS)
    rel = abs_diff / denom
    max_rel = float(rel.max()) if rel.size else 0.0

    flat_e = exp.ravel()
    flat_a = act.ravel()
    norm_e = float(np.linalg.norm(flat_e))
    norm_a = float(np.linalg.norm(flat_a))
    if norm_e == 0.0 or norm_a == 0.0:
        cosine = 1.0 if (norm_e == 0.0 and norm_a == 0.0) else 0.0
    else:
        cosine = float(np.dot(flat_e, flat_a) / (norm_e * norm_a))

    # Outliers: elements that fall outside np.isclose(rtol, atol).
    if abs_diff.size:
        mask = ~np.isclose(act, exp, rtol=tolerance.rtol, atol=tolerance.atol)
        outliers_pct = 100.0 * float(mask.sum()) / float(abs_diff.size)
    else:
        outliers_pct = 0.0

    metrics = {
        "max_abs_error": max_abs,
        "max_rel_error": max_rel,
        "mean_abs_error": mean_abs,
        "cosine_similarity": cosine,
        "outliers_pct": outliers_pct,
    }

    violations: list[ToleranceViolation] = []
    if tolerance.max_abs_error is not None and max_abs > tolerance.max_abs_error:
        violations.append(
            ToleranceViolation("max_abs_error", max_abs, tolerance.max_abs_error)
        )
    if tolerance.max_rel_error is not None and max_rel > tolerance.max_rel_error:
        violations.append(
            ToleranceViolation("max_rel_error", max_rel, tolerance.max_rel_error)
        )
    if (
        tolerance.min_cosine_sim is not None
        and cosine < tolerance.min_cosine_sim
    ):
        violations.append(
            ToleranceViolation("cosine_similarity", cosine, tolerance.min_cosine_sim)
        )
    if outliers_pct > tolerance.max_outliers_pct:
        violations.append(
            ToleranceViolation("outliers_pct", outliers_pct, tolerance.max_outliers_pct)
        )

    passed = not violations
    # First differing index sample (helpful for debugging); None if exact match.
    sample = None
    if abs_diff.size and max_abs > 0:
        idx_flat = int(np.argmax(abs_diff))
        idx = np.unravel_index(idx_flat, abs_diff.shape)
        sample = np.array([exp[idx], act[idx], abs_diff[idx]], dtype=np.float64)

    return ComparisonResult(
        passed=passed,
        metrics=metrics,
        violations=violations,
        sample_diff=sample,
    )
