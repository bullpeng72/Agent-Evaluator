"""Gate G (Observability) — 버그 회귀 테스트 (BUG-G1 ~ BUG-G8)

BUG-G1  monitor.py:3930        — Gate G details hallucination_rate 미반올림
BUG-G2  taskresult_helpers.py  — required_span_attributes=[] falsy trap
BUG-G3  taskresult_helpers.py  — min_coverage=0.0 falsy trap (slo_met 오염)
BUG-G4  decorators.py          — LatencyAttributionConfig 범위 검증 없음
BUG-G5  decorators.py          — ErrorDiagnosisConfig 음수 가중치 허용
BUG-G6  taskresult_helpers.py  — only_on_failure=False + 성공 태스크 → score=0.0
BUG-G7  decorators.py          — ExplainabilityConfig min_reasoning_length < 0
BUG-G8  taskresult_helpers.py  — eval_observability otel_spans=0 falsy trap
"""

import warnings
import pytest

from agent_evaluator.helpers.taskresult_helpers import (
    eval_observability,
    eval_explainability,
    eval_error_diagnosis,
    eval_latency_attribution,
)
from agent_evaluator.decorators import (
    ExplainabilityConfig,
    ErrorDiagnosisConfig,
    LatencyAttributionConfig,
    ObservabilityConfig,
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G1: Gate G details hallucination_rate 미반올림
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG1HallucinationRateRounding:
    """monitor.py Gate G details에서 hallucination_rate가 round(rate, 4)로 처리됨을 검증.

    실제 monitor._compute_harness_groups() 코드 경로를 통해 검증하는 대신,
    비수치 검증으로 해당 라인의 패턴을 단위 테스트한다.
    """

    def test_hallucination_rate_rounded_in_gate_g_details(self):
        """Gate G details에 저장되는 hallucination_rate는 round(4)가 적용된 값이어야 한다."""
        from agent_evaluator import PerformanceMonitor, create_taskresult

        monitor = PerformanceMonitor(
            output_dir="results/",
            enable_hallucination_detection=True,
        )
        t = create_taskresult(
            task_id="g1_t1",
            question="What is 2+2?",
            response="The answer is 4.",
            ground_truth="4",
            execution_time=0.1,
        )
        monitor.record_task(t)
        monitor.hallucination_detector.detect_hallucination(
            "g1_t1", "The answer is 4.", "Math context", "4"
        )
        report = monitor.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics.get("harness_groups", {})
        if "G" in hg and hg["G"]["details"].get("hallucination_rate") is not None:
            rate = hg["G"]["details"]["hallucination_rate"]
            # 소수점 4자리를 초과하지 않아야 한다
            assert rate == round(rate, 4)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G2: required_span_attributes=[] falsy trap
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG2RequiredSpanAttributesEmptyList:
    """required_span_attributes=[] 전달 시 '속성 검사 없음' 으로 처리되어야 한다.

    수정 전: [] → or 연산 → 기본 리스트 ["task_id", "task_type", "execution_time"]로 치환
    수정 후: [] → None 체크 → [] 그대로 유지 → attr_completeness=1.0 (검사 없음)
    """

    def _cfg(self, required_span_attributes):
        cfg = ObservabilityConfig(required_span_attributes=required_span_attributes)
        return cfg

    def test_empty_list_means_no_required_attrs(self):
        cfg = self._cfg([])
        result = eval_observability(
            tool_calls=[],
            task_result_extra={},
            task_id="g2_t1",
            task_type="qa",
            execution_time_s=1.0,
            config=cfg,
        )
        # 필수 속성이 없으므로 누락 없음 → attr_completeness=1.0
        assert result["attr_completeness"] == 1.0
        assert result["missing_attributes"] == []

    def test_empty_list_does_not_fall_back_to_defaults(self):
        """required_span_attributes=[] 지정 시 기본값 3개 속성이 누락으로 잡히지 않아야 한다."""
        cfg = self._cfg([])
        # 의도적으로 extra에 task_id/task_type/execution_time 누락
        result = eval_observability(
            tool_calls=[],
            task_result_extra={"custom_key": "value"},
            task_id="",
            task_type="",
            execution_time_s=0.0,
            config=cfg,
        )
        # required_attrs=[] → missing_attributes=[] → completeness=1.0
        assert result["missing_attributes"] == []
        assert result["attr_completeness"] == 1.0

    def test_nonempty_list_still_enforces(self):
        cfg = self._cfg(["custom_attr"])
        result = eval_observability(
            tool_calls=[],
            task_result_extra={},
            task_id="g2_t3",
            task_type="qa",
            execution_time_s=1.0,
            config=cfg,
        )
        assert "custom_attr" in result["missing_attributes"]
        assert result["attr_completeness"] < 1.0


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G3: min_coverage=0.0 falsy trap (slo_met 오염)
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG3MinCoverageZero:
    """min_coverage=0.0 전달 시 실제로 0.0이 사용되어야 한다.

    수정 전: 0.0 or 0.95 = 0.95 → slo_met 계산에서 0.95 임계값 사용 (오탐)
    수정 후: 0.0 → 명시적 None 체크 → 0.0 그대로 사용 → trace_coverage >= 0.0 항상 True
    """

    def test_min_coverage_zero_slo_always_met(self):
        """min_coverage=0.0이면 trace_coverage=0.0 인 경우에도 slo_met=True여야 한다."""
        cfg = ObservabilityConfig(
            min_coverage=0.0,
            check_trace_continuity=True,
        )
        # tool_calls 있고 otel_spans=0 → trace_coverage=0.0
        result = eval_observability(
            tool_calls=[{"name": "search"}],
            task_result_extra={"otel_spans": 0},
            task_id="g3_t1",
            task_type="qa",
            execution_time_s=1.0,
            config=cfg,
        )
        assert result["trace_coverage"] == 0.0
        # min_coverage=0.0 → 0.0 >= 0.0 → slo_met=True
        assert result["slo_met"] is True

    def test_default_min_coverage_still_works(self):
        """min_coverage 미지정 시 기본값 0.95가 사용됨을 확인한다."""
        cfg = ObservabilityConfig()
        result = eval_observability(
            tool_calls=[{"name": "search"}],
            task_result_extra={"otel_spans": 0},
            task_id="g3_t2",
            task_type="qa",
            execution_time_s=1.0,
            config=cfg,
        )
        # trace_coverage=0.0 < 0.95 → slo_met=False
        assert result["slo_met"] is False


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G4: LatencyAttributionConfig 범위 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG4LatencyAttributionConfigValidation:
    """max_tool_time_ratio / max_unattributed_ratio 가 [0,1] 범위 밖이면 경고 + 보정."""

    def test_max_tool_time_ratio_over_1_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = LatencyAttributionConfig(max_tool_time_ratio=1.5)
            assert cfg.max_tool_time_ratio == 0.6  # 기본값으로 보정
            assert any("max_tool_time_ratio" in str(warning.message) for warning in w)

    def test_max_tool_time_ratio_negative_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = LatencyAttributionConfig(max_tool_time_ratio=-0.1)
            assert cfg.max_tool_time_ratio == 0.6
            assert any("max_tool_time_ratio" in str(warning.message) for warning in w)

    def test_max_unattributed_ratio_over_1_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = LatencyAttributionConfig(max_unattributed_ratio=2.0)
            assert cfg.max_unattributed_ratio == 0.3
            assert any("max_unattributed_ratio" in str(warning.message) for warning in w)

    def test_valid_ratios_pass_unchanged(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = LatencyAttributionConfig(max_tool_time_ratio=0.5, max_unattributed_ratio=0.2)
            assert cfg.max_tool_time_ratio == 0.5
            assert cfg.max_unattributed_ratio == 0.2
            # 유효 범위 내에서 경고 없음
            assert not any(
                "LatencyAttributionConfig" in str(warning.message) for warning in w
            )

    def test_over_1_no_longer_inflates_score(self):
        """수정 전: max_tool_time_ratio=2.0 → 도구 시간이 아무리 많아도 tool_penalty=0 → score=1.0."""
        cfg = LatencyAttributionConfig(max_tool_time_ratio=2.0)
        # 보정 후 max_tool_time_ratio=0.6이므로 100% 도구 시간은 페널티를 받는다
        result = eval_latency_attribution(
            execution_time_ms=1000.0,
            extra={"tool_latencies": {"search": 1000.0}},
            config=cfg,
        )
        # tool_ratio=1.0, max=0.6(보정됨) → tool_penalty=0.4 → score < 1.0
        assert result["attribution_score"] < 1.0


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G5: ErrorDiagnosisConfig 음수 가중치
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG5ErrorDiagnosisNegativeWeights:
    """음수 가중치 지정 시 경고 + 기본값 보정으로 Gate G 음수 방지."""

    def test_negative_acknowledgment_weight_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ErrorDiagnosisConfig(acknowledgment_weight=-1.0)
            assert cfg.acknowledgment_weight == 0.3
            assert any("acknowledgment_weight" in str(warning.message) for warning in w)

    def test_negative_root_cause_weight_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ErrorDiagnosisConfig(root_cause_weight=-5.0)
            assert cfg.root_cause_weight == 0.5
            assert any("root_cause_weight" in str(warning.message) for warning in w)

    def test_negative_suggestion_weight_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ErrorDiagnosisConfig(suggestion_weight=-0.1)
            assert cfg.suggestion_weight == 0.2
            assert any("suggestion_weight" in str(warning.message) for warning in w)

    def test_zero_total_weight_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ErrorDiagnosisConfig(
                acknowledgment_weight=0.0,
                root_cause_weight=0.0,
                suggestion_weight=0.0,
            )
            assert any("sum to 0.0" in str(warning.message) for warning in w)

    def test_valid_weights_produce_nonnegative_score(self):
        cfg = ErrorDiagnosisConfig(
            acknowledgment_weight=0.3,
            root_cause_weight=0.5,
            suggestion_weight=0.2,
        )
        result = eval_error_diagnosis(
            response="Error occurred because the API failed. Try again.",
            has_error=True,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert result["diagnosis_score"] >= 0.0

    def test_score_never_negative_after_fix(self):
        """음수 가중치가 보정되면 diagnosis_score는 항상 0 이상이다."""
        cfg = ErrorDiagnosisConfig(
            acknowledgment_weight=-10.0,   # 보정 → 0.3
            root_cause_weight=-5.0,        # 보정 → 0.5
            suggestion_weight=-2.0,        # 보정 → 0.2
        )
        result = eval_error_diagnosis(
            response="could not complete due to network error",
            has_error=True,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert result["diagnosis_score"] >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G6: only_on_failure=False + 성공 태스크 → score=0.0 부당 Gate G 하락
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG6OnlyOnFailureFalseSuccessTask:
    """성공 태스크는 only_on_failure 값과 무관하게 None을 반환해야 한다.

    수정 전: only_on_failure=False이면 성공 태스크도 평가 → 실패 마커 없음 → score=0.0 → Gate G 하락
    수정 후: task_success=True AND has_error=False → 항상 None (Gate G 집계 제외)
    """

    def test_success_task_no_error_returns_none_when_only_on_failure_true(self):
        cfg = ErrorDiagnosisConfig(only_on_failure=True)
        result = eval_error_diagnosis(
            response="The answer is 42.",
            has_error=False,
            task_success=True,
            config=cfg,
        )
        assert result is None

    def test_success_task_no_error_returns_none_when_only_on_failure_false(self):
        """핵심 수정: only_on_failure=False이더라도 성공 태스크 → None 반환."""
        cfg = ErrorDiagnosisConfig(only_on_failure=False)
        result = eval_error_diagnosis(
            response="The answer is 42.",
            has_error=False,
            task_success=True,
            config=cfg,
        )
        # 수정 전: 결과가 {"diagnosis_score": 0.0, ...} 으로 Gate G를 낮췄음
        assert result is None

    def test_failure_task_always_evaluated(self):
        cfg = ErrorDiagnosisConfig(only_on_failure=False)
        result = eval_error_diagnosis(
            response="Error: could not complete because the API failed. Try again.",
            has_error=False,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert result["diagnosis_score"] >= 0.0

    def test_error_but_success_still_evaluated(self):
        """has_error=True이지만 task_success=True인 부분 성공 케이스는 평가를 실행한다."""
        cfg = ErrorDiagnosisConfig(only_on_failure=False)
        result = eval_error_diagnosis(
            response="failed due to timeout. Try again.",
            has_error=True,
            task_success=True,
            config=cfg,
        )
        # has_error=True이면 task_success=True여도 평가 대상
        assert result is not None

    def test_all_success_tasks_dont_deflate_gate_g(self):
        """only_on_failure=False 상태에서 10개 성공 태스크가 Gate G를 낮추지 않는다."""
        from agent_evaluator import PerformanceMonitor, agent_eval
        monitor = PerformanceMonitor(output_dir="results/")
        cfg = ErrorDiagnosisConfig(only_on_failure=False)

        @agent_eval(monitor, task_type="qa", error_diagnosis=cfg)
        def agent(question, ground_truth=""):
            return f"Answer: {question}"

        for i in range(10):
            agent(f"What is {i}?", ground_truth=str(i))

        report = monitor.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics.get("harness_groups", {})
        g_details = hg.get("G", {}).get("details", {})
        # error_diagnosis가 None만 반환했다면 avg_error_diagnosis도 None
        assert g_details.get("avg_error_diagnosis") is None


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G7: ExplainabilityConfig min_reasoning_length < 0
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG7ExplainabilityMinReasoningLengthNegative:
    """min_reasoning_length < 0 시 경고 + 20으로 보정."""

    def test_negative_length_corrected(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ExplainabilityConfig(min_reasoning_length=-5)
            assert cfg.min_reasoning_length == 20
            assert any("min_reasoning_length" in str(warning.message) for warning in w)

    def test_zero_length_is_valid(self):
        """min_reasoning_length=0은 유효한 설정이다 (길이 제한 없음)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ExplainabilityConfig(min_reasoning_length=0)
            assert cfg.min_reasoning_length == 0
            assert not any(
                "min_reasoning_length" in str(warning.message) for warning in w
            )

    def test_negative_length_no_longer_passes_empty_response(self):
        """수정 전: min_reasoning_length=-1 → len('') >= -1 = True → 빈 응답도 reasoning 통과."""
        cfg = ExplainabilityConfig(
            require_reasoning=True,
            min_reasoning_length=-1,  # 보정 → 20
            reasoning_markers=["because"],
        )
        # 보정 후 min_reasoning_length=20 이므로 빈 응답은 길이 검사 실패
        result = eval_explainability("", [], cfg)
        # 짧거나 빈 응답 + 마커 없음 → reasoning=False
        assert result["checks"].get("reasoning") is False

    def test_valid_positive_length_unchanged(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ExplainabilityConfig(min_reasoning_length=50)
            assert cfg.min_reasoning_length == 50
            assert not any(
                "ExplainabilityConfig" in str(warning.message) for warning in w
            )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-G8: eval_observability otel_spans=0 falsy trap
# ─────────────────────────────────────────────────────────────────────────────

class TestBugG8OtelSpansZeroFalsyTrap:
    """otel_spans=0 (명시적 0 스팬)이 span_count로 폴백되지 않아야 한다.

    수정 전: extra.get("otel_spans") or extra.get("span_count")
             → otel_spans=0이 falsy라서 span_count=5로 폴백 → trace_coverage 오탐
    수정 후: _raw_otel = extra.get("otel_spans")
             → _raw_otel if _raw_otel is not None else extra.get("span_count")
             → otel_spans=0 → None이 아님 → 0 사용 → trace_coverage=0.0
    """

    def _cfg(self):
        return ObservabilityConfig(check_trace_continuity=True)

    def test_otel_spans_zero_gives_zero_coverage(self):
        """otel_spans=0 이고 span_count=5가 있어도 otel_spans=0이 우선되어야 한다."""
        result = eval_observability(
            tool_calls=[{"name": "search"}, {"name": "retrieve"}],
            task_result_extra={"otel_spans": 0, "span_count": 5},
            task_id="g8_t1",
            task_type="qa",
            execution_time_s=1.0,
            config=self._cfg(),
        )
        # otel_spans=0 → span_count=0 → coverage=0.0
        # 수정 전: span_count=5로 폴백 → coverage=min(1.0, 5/2)=1.0 (잘못된 값)
        assert result["trace_coverage"] == 0.0

    def test_otel_spans_zero_no_span_count_fallback(self):
        """otel_spans=0이고 span_count가 없을 때도 0으로 처리된다."""
        result = eval_observability(
            tool_calls=[{"name": "tool_a"}],
            task_result_extra={"otel_spans": 0},
            task_id="g8_t2",
            task_type="qa",
            execution_time_s=1.0,
            config=self._cfg(),
        )
        assert result["trace_coverage"] == 0.0

    def test_otel_spans_none_falls_back_to_span_count(self):
        """otel_spans가 없을 때는 span_count 폴백이 정상 동작해야 한다."""
        result = eval_observability(
            tool_calls=[{"name": "search"}, {"name": "retrieve"}],
            task_result_extra={"span_count": 2},
            task_id="g8_t3",
            task_type="qa",
            execution_time_s=1.0,
            config=self._cfg(),
        )
        # otel_spans=None → span_count=2 사용 → coverage=2/2=1.0
        assert result["trace_coverage"] == 1.0

    def test_otel_spans_positive_not_affected(self):
        """otel_spans>0 (truthy)인 경우 수정 전후 동일 동작."""
        result = eval_observability(
            tool_calls=[{"name": "s1"}, {"name": "s2"}, {"name": "s3"}],
            task_result_extra={"otel_spans": 2, "span_count": 99},
            task_id="g8_t4",
            task_type="qa",
            execution_time_s=1.0,
            config=self._cfg(),
        )
        # otel_spans=2 (positive truthy) → span_count 무시 → coverage=2/3
        assert abs(result["trace_coverage"] - 2 / 3) < 0.001

    def test_both_none_gives_zero_coverage_with_warning(self):
        """otel_spans 없고 span_count도 없으면 coverage=0.0 (경고는 허용)."""
        import logging
        result = eval_observability(
            tool_calls=[{"name": "tool"}],
            task_result_extra={},
            task_id="g8_t5",
            task_type="qa",
            execution_time_s=1.0,
            config=self._cfg(),
        )
        assert result["trace_coverage"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 통합 검증: eval_observability / eval_explainability / eval_latency_attribution
# ─────────────────────────────────────────────────────────────────────────────

class TestGateGEvalFunctionsIntegration:
    """개별 eval 함수의 정상 동작 확인 (경계값, 반환 구조)."""

    # eval_observability

    def test_observability_no_tool_calls_full_coverage(self):
        cfg = ObservabilityConfig()
        result = eval_observability([], {}, "t1", "qa", 1.0, cfg)
        assert result["trace_coverage"] == 1.0
        assert result["observability_score"] >= 0.0

    def test_observability_all_attrs_present_full_completeness(self):
        cfg = ObservabilityConfig(required_span_attributes=["task_id", "model"])
        result = eval_observability(
            [], {"model": "gpt-5-nano"}, "t1", "qa", 1.0, cfg
        )
        assert result["attr_completeness"] == 1.0
        assert result["missing_attributes"] == []

    def test_observability_missing_attr_partial_completeness(self):
        cfg = ObservabilityConfig(required_span_attributes=["task_id", "model", "version"])
        result = eval_observability([], {}, "t1", "qa", 1.0, cfg)
        # task_id는 function arg에서 주입되므로 존재, model/version은 없음
        assert "model" in result["missing_attributes"] or "version" in result["missing_attributes"]
        assert result["attr_completeness"] < 1.0

    def test_observability_audit_events_partial(self):
        cfg = ObservabilityConfig(audit_events=["login", "query", "logout"])
        result = eval_observability(
            [], {"audit_events": ["login", "query"]}, "t1", "qa", 1.0, cfg
        )
        assert "logout" in result["missing_audit_events"]
        assert result["audit_completeness"] < 1.0

    def test_observability_score_in_zero_one(self):
        cfg = ObservabilityConfig()
        result = eval_observability(
            [{"name": "s"}], {"otel_spans": 0}, "t1", "qa", 1.0, cfg
        )
        assert 0.0 <= result["observability_score"] <= 1.0

    # eval_explainability

    def test_explainability_all_checks_pass(self):
        cfg = ExplainabilityConfig(
            require_reasoning=True,
            require_citations=True,
            reasoning_markers=["because"],
            citation_markers=["source:"],
            min_reasoning_length=10,
        )
        result = eval_explainability(
            "This is correct because the data shows it. source: Wikipedia",
            [],
            cfg,
        )
        assert result["score"] == 1.0

    def test_explainability_no_checks_returns_none_score(self):
        """모든 require_* False → checks 없음 → score=None → Gate G 미기여."""
        cfg = ExplainabilityConfig(
            require_reasoning=False,
            require_uncertainty_expression=False,
            require_citations=False,
            check_action_explanation_alignment=False,
        )
        result = eval_explainability("any response", [], cfg)
        assert result["score"] is None

    def test_explainability_partial_score(self):
        cfg = ExplainabilityConfig(
            require_reasoning=True,
            require_citations=True,
            reasoning_markers=["because"],
            citation_markers=["source:"],
            min_reasoning_length=5,
        )
        result = eval_explainability("because it works", [], cfg)
        # reasoning 통과, citations 실패 → 0.5
        assert result["score"] == pytest.approx(0.5)

    def test_explainability_empty_response_reasoning_fails(self):
        cfg = ExplainabilityConfig(require_reasoning=True, min_reasoning_length=10)
        result = eval_explainability("", [], cfg)
        assert result["checks"]["reasoning"] is False

    def test_explainability_action_alignment_with_no_tools(self):
        """tool_calls=[] → alignment check 스킵 → checks에 해당 키 없음."""
        cfg = ExplainabilityConfig(
            require_reasoning=False,
            check_action_explanation_alignment=True,
        )
        result = eval_explainability("any response", [], cfg)
        assert "action_explanation_alignment" not in result["checks"]

    # eval_error_diagnosis

    def test_error_diagnosis_full_score(self):
        cfg = ErrorDiagnosisConfig(only_on_failure=True)
        result = eval_error_diagnosis(
            "failed to process because the API is down. Try the backup endpoint instead.",
            has_error=True,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert result["diagnosis_score"] == pytest.approx(1.0)

    def test_error_diagnosis_partial_score(self):
        cfg = ErrorDiagnosisConfig(only_on_failure=True)
        result = eval_error_diagnosis(
            "error occurred",  # 인정만 있고 원인/제안 없음
            has_error=True,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert 0.0 < result["diagnosis_score"] < 1.0

    def test_error_diagnosis_score_in_zero_one(self):
        cfg = ErrorDiagnosisConfig()
        result = eval_error_diagnosis(
            "could not complete due to error. Try again.",
            has_error=True,
            task_success=False,
            config=cfg,
        )
        assert result is not None
        assert 0.0 <= result["diagnosis_score"] <= 1.0

    # eval_latency_attribution

    def test_latency_attribution_full_attribution(self):
        cfg = LatencyAttributionConfig(max_tool_time_ratio=0.6, max_unattributed_ratio=0.3)
        result = eval_latency_attribution(
            execution_time_ms=1000.0,
            extra={"tool_latencies": {"search": 300.0}, "model_latency_ms": 700.0},
            config=cfg,
        )
        assert result["attribution_score"] is not None
        assert result["unattributed_ratio"] == pytest.approx(0.0)
        assert result["attribution_score"] == pytest.approx(1.0)

    def test_latency_attribution_high_tool_ratio_penalized(self):
        cfg = LatencyAttributionConfig(max_tool_time_ratio=0.3, max_unattributed_ratio=0.3)
        result = eval_latency_attribution(
            execution_time_ms=1000.0,
            extra={"tool_latencies": {"search": 900.0}},
            config=cfg,
        )
        # tool_ratio=0.9, max=0.3 → penalty=0.6 → score=max(0, 1-0.6-...)
        assert result["attribution_score"] < 0.7

    def test_latency_attribution_fast_no_data_returns_none_score(self):
        """실행 시간 < 10ms AND 컴포넌트 데이터 없음 → attribution_score=None (Gate G 제외)."""
        cfg = LatencyAttributionConfig()
        result = eval_latency_attribution(
            execution_time_ms=5.0,
            extra={},
            config=cfg,
        )
        assert result["attribution_score"] is None

    def test_latency_attribution_score_in_zero_one(self):
        cfg = LatencyAttributionConfig()
        result = eval_latency_attribution(
            execution_time_ms=500.0,
            extra={"tool_latencies": {"t1": 200.0}, "model_latency_ms": 100.0},
            config=cfg,
        )
        assert result["attribution_score"] is not None
        assert 0.0 <= result["attribution_score"] <= 1.0

    def test_latency_attribution_bottleneck_identified(self):
        cfg = LatencyAttributionConfig()
        result = eval_latency_attribution(
            execution_time_ms=1000.0,
            extra={"tool_latencies": {"t": 800.0}, "model_latency_ms": 100.0},
            config=cfg,
        )
        assert result["bottleneck"] == "tool"
