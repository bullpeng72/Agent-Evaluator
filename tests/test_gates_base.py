"""
tests/test_gates_base.py
==========================
SPEC-000 Commit 0: agent_evaluator.gates.base 공유 인프라 단위 테스트.

_status/_g/_min_sample_warning는 monitor.py의 nested closure/모듈 레벨 정의에서
순수 함수로 그대로 승격된 것이므로, 여기서는 동작이 기존과 동일한지만 검증한다.
"""
import pytest

from agent_evaluator.gates.base import (
    _DEFAULT_MIN_SAMPLES,
    _g,
    _gate_pass_verdict,
    _measured,
    _min_sample_warning,
    _status,
    assemble_overall,
)


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


class TestGatePassVerdict:
    """이전에는 이 판정이 HarnessEvaluationGate.evaluate() · QuickEval.gate() ·
    cli/gate.py 세 곳에 독립적으로 복제돼 있었다 — 하나를 고쳐도 나머지 둘은
    안 고쳐지는 구조였다. 이제 세 곳 모두 _gate_pass_verdict()를 호출하므로,
    이 클래스의 테스트가 곧 세 경로 전체의 회귀 테스트다."""

    def test_score_above_threshold_passes(self):
        assert _gate_pass_verdict(0.8, 0.7, "pass") is True

    def test_score_below_threshold_fails(self):
        assert _gate_pass_verdict(0.6, 0.7, "warn") is False

    def test_score_equal_threshold_passes(self):
        assert _gate_pass_verdict(0.7, 0.7, "pass") is True

    def test_fail_on_warn_false_ignores_warn_status(self):
        # fail_on_warn 기본값(False) — 커스텀 임계값만 통과하면 status와 무관하게 pass
        assert _gate_pass_verdict(0.6, 0.5, "warn", fail_on_warn=False) is True

    def test_fail_on_warn_true_escalates_warn_status(self):
        assert _gate_pass_verdict(0.6, 0.5, "warn", fail_on_warn=True) is False

    def test_fail_on_warn_true_ignores_pass_status(self):
        assert _gate_pass_verdict(0.8, 0.7, "pass", fail_on_warn=True) is True

    def test_fail_on_warn_escalation_independent_of_custom_threshold(self):
        # 의도된 동작: status(고정 warn=0.7/fail=0.5 기준)의 "warn" escalation은
        # threshold를 얼마나 느슨하게 재정의해도 무시되지 않는다 — 두 기준(커스텀
        # 임계값 통과 여부·Gate의 보편적 위험 분류)이 동시에 강제된다.
        assert _gate_pass_verdict(0.55, 0.4, "warn", fail_on_warn=True) is False


class TestMeasured:
    """측정 상태 3분류 계약 — Gate E가 어겼던 것과 같은 클래스의 버그(count=0인데
    value가 이미 "안전"으로 계산돼 있는 경우)를 새 Gate/지표에서 구조적으로 막는다."""

    def test_zero_count_is_none_even_if_value_looks_safe(self):
        assert _measured(0, 1.0) is None

    def test_negative_count_is_none(self):
        assert _measured(-1, 1.0) is None

    def test_positive_count_returns_value_unchanged(self):
        assert _measured(5, 0.73) == 0.73

    def test_positive_count_with_none_value_stays_none(self):
        assert _measured(3, None) is None


class TestAssembleOverall:
    """Phase 2 — Gate가 몇 개든(내장 7개 + register_gate()로 추가된 것 포함)
    overall을 하드코딩 없이 조립하는지 검증."""

    def test_all_seven_scored(self):
        groups = {g: {"score": 0.8} for g in "ABCDEFG"}
        overall = assemble_overall(groups)
        assert overall["scored_groups"] == 7
        assert overall["scored_group_ids"] == list("ABCDEFG")
        assert overall["score"] == 0.8

    def test_some_none_excluded_from_average_and_ids(self):
        groups = {"A": {"score": 1.0}, "B": {"score": None}, "C": {"score": 0.5}}
        overall = assemble_overall(groups)
        assert overall["scored_groups"] == 2
        assert overall["scored_group_ids"] == ["A", "C"]
        assert overall["score"] == pytest.approx(0.75)

    def test_all_none_yields_zero_score_and_empty_ids(self):
        # 기존 동작 그대로 보존: 채점된 Gate가 하나도 없으면 score=0.0(None 아님) —
        # 이건 이 함수가 새로 만든 동작이 아니라 리팩터 이전 _compute_harness_groups의
        # 동일한 기존 동작을 그대로 승격한 것이다(구조적 투자 검토에서 별도 개선 과제로 남김).
        groups = {"A": {"score": None}, "B": {"score": None}}
        overall = assemble_overall(groups)
        assert overall["scored_groups"] == 0
        assert overall["scored_group_ids"] == []
        assert overall["score"] == 0.0
        assert overall["status"] == "fail"  # _status(0.0) == "fail" — 기존 동작 그대로

    def test_custom_gate_included_alongside_builtin(self):
        """register_gate()로 추가된 8번째 Gate("H")도 A-G와 동일하게 집계돼야 한다."""
        groups = {**{g: {"score": 0.9} for g in "ABCDEFG"}, "H": {"score": 0.1}}
        overall = assemble_overall(groups)
        assert overall["scored_groups"] == 8
        assert "H" in overall["scored_group_ids"]
        assert overall["score"] == pytest.approx((0.9 * 7 + 0.1) / 8)

    def test_insertion_order_preserved_in_scored_group_ids(self):
        groups = {"G": {"score": 1.0}, "A": {"score": 1.0}, "H": {"score": 1.0}}
        overall = assemble_overall(groups)
        assert overall["scored_group_ids"] == ["G", "A", "H"]
