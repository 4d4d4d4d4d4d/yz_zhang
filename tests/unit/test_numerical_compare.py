"""Conformance tests for the functional comparator. Reference: SPEC-004 §5."""

from __future__ import annotations

import numpy as np

from npu_sim.evaluation import compare_tensors
from npu_sim.interfaces.numerical import NumericDType, Tensor, Tolerance


def _t(data: np.ndarray) -> Tensor:
    return Tensor(data=data, dtype=NumericDType.FP32, shape=data.shape)


class TestExactMatch:
    """SPEC-004 §5.1 metrics on identical tensors."""

    def test_identical_tensors_pass(self):
        x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        result = compare_tensors(_t(x), _t(x.copy()), Tolerance())
        assert result.passed
        assert result.metrics["max_abs_error"] == 0.0
        assert result.metrics["max_rel_error"] == 0.0
        assert result.metrics["outliers_pct"] == 0.0
        assert result.metrics["cosine_similarity"] == 1.0
        assert result.violations == []


class TestTolerance:
    """SPEC-004 §5.2 Tolerance violations."""

    def test_within_rtol_atol_passes(self):
        exp = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        act = exp + 1e-7
        result = compare_tensors(_t(exp), _t(act), Tolerance(rtol=1e-5, atol=1e-6))
        assert result.passed
        assert result.metrics["outliers_pct"] == 0.0

    def test_exceeds_atol_flags_outliers(self):
        exp = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        act = np.array([1.0, 2.0, 3.0, 99.0], dtype=np.float32)
        result = compare_tensors(_t(exp), _t(act), Tolerance(rtol=1e-5, atol=1e-6))
        assert not result.passed
        # one element out of four → 25% outliers
        assert result.metrics["outliers_pct"] == 25.0
        # and the outlier-tolerance default is 0 -> violation reported
        assert any(v.metric == "outliers_pct" for v in result.violations)

    def test_max_abs_error_threshold(self):
        exp = np.array([0.0, 0.0], dtype=np.float32)
        act = np.array([0.0, 0.5], dtype=np.float32)
        result = compare_tensors(
            _t(exp), _t(act), Tolerance(max_abs_error=0.1, max_outliers_pct=100.0)
        )
        assert not result.passed
        assert any(v.metric == "max_abs_error" for v in result.violations)

    def test_min_cosine_sim_threshold(self):
        # Anti-parallel vectors: cosine = -1.
        exp = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        act = -exp
        result = compare_tensors(
            _t(exp), _t(act),
            Tolerance(min_cosine_sim=0.9, max_outliers_pct=100.0,
                      max_abs_error=1e9, max_rel_error=1e9),
        )
        assert not result.passed
        assert any(v.metric == "cosine_similarity" for v in result.violations)


class TestShapeMismatch:

    def test_different_shape_fails_immediately(self):
        exp = Tensor(np.arange(6, dtype=np.float32).reshape(2, 3),
                     NumericDType.FP32, (2, 3))
        act = Tensor(np.arange(6, dtype=np.float32).reshape(3, 2),
                     NumericDType.FP32, (3, 2))
        result = compare_tensors(exp, act, Tolerance())
        assert not result.passed
        assert any(v.metric == "shape" for v in result.violations)


class TestPurity:
    """SPEC-004 §3.1 / §5.1 — compare_tensors must not mutate inputs."""

    def test_inputs_unchanged_after_compare(self):
        exp_arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        act_arr = np.array([1.0, 2.0, 3.5], dtype=np.float32)
        before_exp = exp_arr.copy()
        before_act = act_arr.copy()
        compare_tensors(_t(exp_arr), _t(act_arr), Tolerance())
        np.testing.assert_array_equal(exp_arr, before_exp)
        np.testing.assert_array_equal(act_arr, before_act)

    def test_repeated_call_same_result(self):
        exp = _t(np.array([1.0, 2.0, 3.0], dtype=np.float32))
        act = _t(np.array([1.0, 2.0, 3.5], dtype=np.float32))
        r1 = compare_tensors(exp, act, Tolerance())
        r2 = compare_tensors(exp, act, Tolerance())
        assert r1.metrics == r2.metrics
        assert [v.metric for v in r1.violations] == [v.metric for v in r2.violations]


class TestSampleDiff:

    def test_sample_diff_points_to_largest_error(self):
        exp = np.array([1.0, 2.0, 10.0, 4.0], dtype=np.float32)
        act = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        result = compare_tensors(_t(exp), _t(act), Tolerance())
        assert result.sample_diff is not None
        # (exp, act, abs_diff) for the index of largest error -> index 2.
        np.testing.assert_array_equal(result.sample_diff, np.array([10.0, 3.0, 7.0]))


class TestFidelityRegressionUseCase:
    """End-to-end SPEC-004 §5 use case: baseline (golden) vs noisy variant."""

    def test_detects_quantization_noise_regression(self):
        rng = np.random.default_rng(42)
        ref = rng.normal(size=(32,)).astype(np.float32)
        # Small variant noise that the spec'd default Tolerance should
        # tolerate, vs large noise that it should not.
        tight = ref + rng.normal(scale=1e-7, size=(32,)).astype(np.float32)
        loose = ref + rng.normal(scale=0.5, size=(32,)).astype(np.float32)

        tight_result = compare_tensors(
            _t(ref), _t(tight),
            Tolerance(rtol=1e-3, atol=1e-3, max_outliers_pct=0.0),
        )
        loose_result = compare_tensors(
            _t(ref), _t(loose),
            Tolerance(rtol=1e-3, atol=1e-3, max_outliers_pct=0.0),
        )
        assert tight_result.passed
        assert not loose_result.passed
        assert loose_result.metrics["max_abs_error"] > tight_result.metrics["max_abs_error"]
