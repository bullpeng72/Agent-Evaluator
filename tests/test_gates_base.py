"""
tests/test_gates_base.py
==========================
SPEC-000 Commit 0: agent_evaluator.gates.base 공유 인프라 단위 테스트.

_status/_g/_min_sample_warning는 monitor.py의 nested closure/모듈 레벨 정의에서
순수 함수로 그대로 승격된 것이므로, 여기서는 동작이 기존과 동일한지만 검증한다.
"""
from agent_evaluator.gates.base import _DEFAULT_MIN_SAMPLES, _min_sample_warning, _status, _g


class TestStatus:
    def test_none_is_na(self):
        assert _status(None) == "n/a"

    def test_exact_warn_boundary_is_pass(self):
        assert _status(0.7) == "pass"

    def test_exact_fail_boundary_is_warn(self):
        assert _status(0.5) == "warn"

    def test_below_fail_is_fail(self):
        assert _status(0.49) == "fail"

    def test_custom_thresholds(self):
        assert _status(0.85, warn=0.9, fail=0.8) == "warn"


class TestG:
    def test_builds_expected_keys(self):
        result = _g(0.8, "Test Gate", {"foo": 1})
        assert result == {
            "name": "Test Gate", "score": 0.8, "status": "pass", "gate": "pass",
            "details": {"foo": 1},
        }

    def test_f_score_none_is_na_not_fail(self):
        # f_score=True + score=None → "n/a" (Gate F/G 처럼 데이터 없음과 실패를 구분)
        result = _g(None, "Gate F", {}, f_score=True)
        assert result["status"] == "n/a"
        assert result["gate"] == "n/a"


class TestMinSampleWarning:
    def test_zero_count_no_warning(self):
        assert _min_sample_warning("metric", 0, 3) is None

    def test_below_min_samples_warns(self):
        assert _min_sample_warning("metric", 2, 3) == "metric: 2 samples < min_samples=3"

    def test_at_or_above_min_samples_no_warning(self):
        assert _min_sample_warning("metric", 3, 3) is None
        assert _min_sample_warning("metric", 5, 3) is None

    def test_default_constant_value(self):
        assert _DEFAULT_MIN_SAMPLES == 3
