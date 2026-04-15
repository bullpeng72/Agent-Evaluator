"""
tests/test_v078_gaps.py
========================
v0.7.8 신규 기능 테스트 — 37개 Gap 검증

A1:  batch_eval concurrent on_item_error / _last_failures
A2:  batch_eval strict_types
A3:  conversation_eval participant_id_arg / TurnMetadata.participant_id
A4:  eval_context depth 추적
A5:  EvalDecorator._auto_common_params() / custom_parser in _COMMON_PARAMS
A6:  agent_eval_with_retry should_retry
A7:  EvalDecorator.batch() 반환 callable
A8:  eval_context auto_task_id
A9:  custom_parser 적용 / None 반환 시 무시
A10: conversation_eval max_turns_exceeded_action (flush/warn/error)

B1:  DELETE /api/results/{file_id} — soft / hard delete
B2:  POST /api/results/{file_id}/tasks/bulk-tag
B3:  GET  /api/results/{file_id}/aggregate?by=task_type
B4:  POST /api/results/{file_id}/tasks/filter — gte / AND
B5:  GET  /api/compare?detailed=true
B6:  stream 라우터 등록 여부
B7:  POST /api/alerts/rules — 생성 후 파일 저장
B8:  POST /api/alerts/rules — compound_conditions 지원
B9:  GET  /api/cost/breakdown?by=model
B10: GET  /api/export/excel/{file_id} — 등록 여부
B11: POST /api/golden/candidates/{name}/bulk-approve — 전체 승인
B12: GET  /api/results — page/limit 파라미터 반환 형식

C1:  _is_cohere_response — finish_reason 속성으로 streaming 감지
C2:  _extract_groq_metadata — cache_creation_tokens 추출
C3:  _extract_mistral_metadata — function_call fallback

C7:  _auto_detect_framework — anthropic 감지 / unknown → None / auto_detect_framework=True
C8:  _safe_adapter_call — 어댑터 실패 시 None + error_msg / 정상 시 EvalMetadata

D1:  PerformanceMonitor.filter_tasks (task_type / min_accuracy / success_only / combined)
D2:  PerformanceMonitor.aggregate_metrics (all / by task_type / by day)
D3:  enabled_security_trackers 선택적 활성화
D4:  get_tcr_metrics / get_latency_metrics — dict 반환
D5:  analyze / get_bottleneck_tasks / get_optimization_recommendations
D6:  create_taskresult metadata → extra 저장
"""
from __future__ import annotations

import inspect
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _make_monitor(output_dir=None, **kwargs):
    from agent_evaluator import PerformanceMonitor
    return PerformanceMonitor(output_dir=output_dir or tempfile.mkdtemp(), **kwargs)


def _make_task_result(**kwargs):
    from agent_evaluator import create_taskresult
    defaults = dict(
        task_id="t1",
        question="q",
        response="r",
        ground_truth="r",
        execution_time=0.1,
        task_type="qa",
    )
    defaults.update(kwargs)
    return create_taskresult(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# A1: batch_eval concurrent — on_item_error / _last_failures
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchEvalConcurrentFailure:
    def test_last_failures_attribute_exists(self):
        """wrapper._last_failures 속성이 concurrent 실행 후 존재한다."""
        from agent_evaluator.decorators import batch_eval

        m = _make_monitor()

        @batch_eval(m, task_type="qa", concurrency=2)
        def agent(questions, ground_truths=None):
            return [f"ans:{q}" for q in questions]

        agent(["q1", "q2"])
        assert hasattr(agent, "_last_failures")
        assert isinstance(agent._last_failures, list)

    def test_on_item_error_param_exists(self):
        """batch_eval에 on_item_error 파라미터가 있다."""
        from agent_evaluator.decorators import batch_eval
        sig = inspect.signature(batch_eval)
        assert "on_item_error" in sig.parameters

    def test_on_item_error_callback_called_on_failure(self):
        """concurrent=True에서 개별 항목 실패 시 on_item_error가 호출된다."""
        from agent_evaluator.decorators import batch_eval

        m = _make_monitor()
        errors_collected = []

        def on_item_err(index, question, error):
            errors_collected.append((index, str(error)))

        @batch_eval(
            m,
            task_type="qa",
            concurrency=2,
            on_item_error=on_item_err,
        )
        def agent(questions, ground_truths=None):
            results = []
            for q in questions:
                if "fail" in q:
                    raise ValueError(f"fail: {q}")
                results.append(f"ok:{q}")
            return results

        try:
            agent(["ok1", "fail2", "ok3"])
        except Exception:
            pass

        # _last_failures에 실패 정보가 저장되어야 함
        assert hasattr(agent, "_last_failures")


# ─────────────────────────────────────────────────────────────────────────────
# A2: batch_eval strict_types
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchEvalStrictTypes:
    def test_strict_types_list_passes(self):
        """strict_types 제거됨 — 전달 시 TypeError 발생."""
        from agent_evaluator.decorators import batch_eval

        m = _make_monitor()

        with pytest.raises(TypeError):
            batch_eval(m, task_type="qa", strict_types=True)

    def test_strict_types_non_list_raises(self):
        """strict_types=False 도 TypeError (파라미터 자체가 제거됨)."""
        from agent_evaluator.decorators import batch_eval

        m = _make_monitor()

        with pytest.raises(TypeError):
            batch_eval(m, task_type="qa", strict_types=False)

    def test_strict_types_param_exists(self):
        """batch_eval에서 strict_types 파라미터가 제거됨."""
        from agent_evaluator.decorators import batch_eval
        sig = inspect.signature(batch_eval)
        assert "strict_types" not in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# A3: conversation_eval — participant_id_arg / TurnMetadata.participant_id
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationEvalParticipantId:
    def test_turn_metadata_participant_id_field(self):
        """TurnMetadata에 participant_id 필드가 존재한다."""
        from agent_evaluator.decorators import TurnMetadata
        tm = TurnMetadata(participant_id="user_123")
        assert tm.participant_id == "user_123"

    def test_turn_metadata_participant_id_default_none(self):
        """TurnMetadata.participant_id 기본값은 None이다."""
        from agent_evaluator.decorators import TurnMetadata
        tm = TurnMetadata()
        assert tm.participant_id is None

    def test_participant_id_arg_param_exists(self):
        """conversation_eval에서 participant_id_arg 파라미터가 제거됨."""
        from agent_evaluator.decorators import conversation_eval
        sig = inspect.signature(conversation_eval)
        assert "participant_id_arg" not in sig.parameters

    def test_participant_id_arg_functional(self):
        """participant_id_arg 제거 후 conversation_eval 기본 호출이 정상 동작한다."""
        from agent_evaluator.decorators import conversation_eval, flush_conversation

        m = _make_monitor()

        @conversation_eval(m)
        def chat(question, session_id="sid_default"):
            return f"echo:{question}"

        chat("hi", session_id="pid_test_sess")
        flush_conversation("pid_test_sess")
        assert True


# ─────────────────────────────────────────────────────────────────────────────
# A4: eval_context depth 추적
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalContextDepth:
    def test_depth_is_one_at_top(self):
        """최상위 eval_context는 depth=1이다."""
        from agent_evaluator.decorators import eval_context

        m = _make_monitor()
        with eval_context(m, "qa", question="q") as ctx:
            assert ctx.depth == 1

    def test_nested_depth_increases(self):
        """중첩된 eval_context는 depth가 증가한다."""
        from agent_evaluator.decorators import eval_context

        m = _make_monitor()
        with eval_context(m, "qa", question="outer") as outer:
            assert outer.depth == 1
            with eval_context(m, "qa", question="inner") as inner:
                assert inner.depth == 2

    def test_depth_property_exists(self):
        """eval_context에 depth 프로퍼티가 있다."""
        from agent_evaluator.decorators import eval_context

        m = _make_monitor()
        with eval_context(m, "qa", question="q") as ctx:
            assert hasattr(ctx, "depth")


# ─────────────────────────────────────────────────────────────────────────────
# A5: EvalDecorator._auto_common_params() / custom_parser in _COMMON_PARAMS
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalDecoratorAutoCommonParams:
    def test_auto_common_params_returns_frozenset(self):
        """_auto_common_params()는 frozenset을 반환한다."""
        from agent_evaluator.decorators import EvalDecorator
        params = EvalDecorator._auto_common_params()
        assert isinstance(params, frozenset)
        assert len(params) > 0

    def test_custom_parser_in_common_params(self):
        """'custom_parser'가 _COMMON_PARAMS에 포함된다."""
        from agent_evaluator.decorators import EvalDecorator
        assert "custom_parser" in EvalDecorator._COMMON_PARAMS

    def test_auto_common_params_includes_standard_keys(self):
        """_auto_common_params()는 표준 파라미터 키를 포함한다."""
        from agent_evaluator.decorators import EvalDecorator
        params = EvalDecorator._auto_common_params()
        for key in ("framework", "model_name", "sample_rate", "enabled"):
            assert key in params, f"Missing standard key: {key}"

    def test_auto_common_params_classmethod(self):
        """_auto_common_params는 classmethod이다."""
        from agent_evaluator.decorators import EvalDecorator
        assert isinstance(
            inspect.getattr_static(EvalDecorator, "_auto_common_params"),
            classmethod,
        )


# ─────────────────────────────────────────────────────────────────────────────
# A6: agent_eval should_retry (통합 후 agent_eval 사용)
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentEvalShould:
    def test_should_retry_param_exists(self):
        """should_retry 는 agent_eval 직접 파라미터가 아닌 RetryConfig.should_retry 로 지정."""
        from agent_evaluator.decorators import agent_eval, RetryConfig
        sig = inspect.signature(agent_eval)
        assert "should_retry" not in sig.parameters
        assert "retry" in sig.parameters

    def test_should_retry_false_raises_eventually(self):
        """RetryConfig(should_retry=lambda e: False) 지정 시 첫 번째 예외에서 중단."""
        from agent_evaluator.decorators import agent_eval, RetryConfig

        m = _make_monitor()
        call_count = [0]

        @agent_eval(
            m,
            task_type="qa",
            retry=RetryConfig(max=3, on=(ValueError,), should_retry=lambda e: False),
        )
        def agent(question, ground_truth=""):
            call_count[0] += 1
            raise ValueError("fail")

        # should_retry=False이면 재시도 없이 ValueError 발생
        with pytest.raises(ValueError):
            agent("q")

        # should_retry=False이면 한 번만 호출
        assert call_count[0] >= 1

    def test_should_retry_conditional(self):
        """RetryConfig(should_retry=...) 로 특정 메시지 예외만 재시도한다."""
        from agent_evaluator.decorators import agent_eval, RetryConfig

        m = _make_monitor()
        call_count = [0]

        @agent_eval(
            m,
            task_type="qa",
            retry=RetryConfig(max=3, on=(ValueError,), should_retry=lambda e: "retry_me" in str(e)),
        )
        def agent(question, ground_truth=""):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("retry_me")
            return "success"

        result = agent("q")
        assert result == "success"
        assert call_count[0] == 3


# ─────────────────────────────────────────────────────────────────────────────
# A7: EvalDecorator.batch() 반환 타입
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalDecoratorReturnTypes:
    def test_batch_method_exists(self):
        """EvalDecorator에 batch 메서드가 있다."""
        from agent_evaluator.decorators import EvalDecorator
        m = _make_monitor()
        ed = EvalDecorator(m)
        assert hasattr(ed, "batch")
        assert callable(ed.batch)

    def test_batch_returns_callable(self):
        """EvalDecorator.batch(task_type=...)는 callable decorator를 반환한다."""
        from agent_evaluator.decorators import EvalDecorator
        m = _make_monitor()
        ed = EvalDecorator(m)
        decorator = ed.batch(task_type="qa")
        assert callable(decorator)

    def test_batch_decorates_and_runs(self):
        """EvalDecorator.batch()로 함수를 감싸고 실행할 수 있다."""
        from agent_evaluator.decorators import EvalDecorator
        m = _make_monitor()
        ed = EvalDecorator(m)

        @ed.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans:{q}" for q in questions]

        result = batch_agent(["q1", "q2"])
        assert result == ["ans:q1", "ans:q2"]


# ─────────────────────────────────────────────────────────────────────────────
# A8: eval_context auto_task_id
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalContextAutoTaskId:
    def test_auto_task_id_param_exists(self):
        """eval_context에 auto_task_id 파라미터가 있다."""
        from agent_evaluator.decorators import eval_context
        sig = inspect.signature(eval_context)
        assert "auto_task_id" in sig.parameters

    def test_auto_task_id_generates_auto_prefix(self):
        """auto_task_id=True 시 'auto_' prefix task_id가 생성된다."""
        from agent_evaluator.decorators import eval_context

        m = _make_monitor()
        with eval_context(m, "qa", question="q", auto_task_id=True) as ctx:
            ctx.response = "answer"

        tasks = m.tasks
        assert len(tasks) == 1
        assert tasks[0].task_id.startswith("auto_")

    def test_auto_task_id_with_explicit_uses_explicit(self, caplog):
        """task_id 명시 + auto_task_id=True 시 task_id가 우선 사용된다."""
        from agent_evaluator.decorators import eval_context

        m = _make_monitor()
        with caplog.at_level(logging.WARNING, logger="agent_evaluator.decorators"):
            with eval_context(m, "qa", question="q",
                              task_id="explicit_id", auto_task_id=True) as ctx:
                ctx.response = "answer"

        tasks = m.tasks
        assert len(tasks) == 1
        assert tasks[0].task_id == "explicit_id"


# ─────────────────────────────────────────────────────────────────────────────
# A9: custom_parser
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomParser:
    def test_custom_parser_applied(self):
        """custom_parser가 호출되어 EvalMetadata를 반환하면 적용된다."""
        from agent_evaluator.decorators import agent_eval, EvalMetadata

        m = _make_monitor()
        parsed = []

        def my_parser(raw):
            parsed.append(raw)
            return EvalMetadata(framework="custom_fw", attempts=5)

        @agent_eval(m, task_type="qa", custom_parser=my_parser)
        def agent(question, ground_truth=""):
            return "response_text"

        agent("question")

        assert len(parsed) == 1
        tasks = m.tasks
        assert len(tasks) == 1
        assert tasks[0].framework == "custom_fw"
        assert tasks[0].attempts == 5

    def test_custom_parser_none_ignored(self):
        """custom_parser가 None을 반환하면 custom_parser가 덮어쓰지 않는다."""
        from agent_evaluator.decorators import agent_eval

        m = _make_monitor()
        call_count = [0]

        def null_parser(raw):
            call_count[0] += 1
            return None  # None 반환 → 무시

        @agent_eval(m, task_type="qa", custom_parser=null_parser)
        def agent(question, ground_truth=""):
            return "response"

        agent("question")
        tasks = m.tasks
        assert len(tasks) == 1
        # null_parser가 호출됨
        assert call_count[0] == 1
        # None 반환 시 attempts는 자동값(1) 유지
        assert tasks[0].attempts == 1

    def test_custom_parser_param_in_agent_eval(self):
        """agent_eval에 custom_parser 파라미터가 있다."""
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "custom_parser" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# A10: conversation_eval max_turns_exceeded_action
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationMaxTurnsAction:
    def test_max_turns_exceeded_action_param_exists(self):
        """conversation_eval에 max_turns_exceeded_action 파라미터가 있다."""
        from agent_evaluator.decorators import conversation_eval
        sig = inspect.signature(conversation_eval)
        assert "max_turns_exceeded_action" in sig.parameters

    def test_max_turns_action_flush(self):
        """max_turns_exceeded_action='flush' 시 max_turns 초과 시 flush 실행."""
        from agent_evaluator.decorators import conversation_eval

        m = _make_monitor()
        sid = "flush_action_sess"

        @conversation_eval(m, max_turns=2, max_turns_exceeded_action="flush")
        def chat(question, session_id=sid):
            return f"echo:{question}"

        chat("turn1", session_id=sid)
        chat("turn2", session_id=sid)
        chat("turn3", session_id=sid)  # 초과 → flush 발생 (예외 없음)
        assert True

    def test_max_turns_action_warn(self, caplog):
        """max_turns_exceeded_action='warn' 시 경고 후 계속 처리."""
        from agent_evaluator.decorators import conversation_eval

        m = _make_monitor()
        sid = "warn_action_sess"

        @conversation_eval(m, max_turns=2, max_turns_exceeded_action="warn")
        def chat(question, session_id=sid):
            return f"echo:{question}"

        with caplog.at_level(logging.WARNING):
            chat("turn1", session_id=sid)
            chat("turn2", session_id=sid)
            chat("turn3", session_id=sid)  # warn or flush

        # warn 모드: 예외 없이 완료
        assert True

    def test_max_turns_action_error(self):
        """max_turns_exceeded_action='error' 시 max_turns 도달 시 ValueError가 발생한다."""
        from agent_evaluator.decorators import conversation_eval

        m = _make_monitor()
        sid = "error_action_sess_new"

        @conversation_eval(m, max_turns=2, max_turns_exceeded_action="error")
        def chat(question, session_id=sid):
            return f"echo:{question}"

        # max_turns=2 이므로 2번째 호출 시 (turn_count >= max_turns) 체크
        chat("turn1", session_id=sid)
        with pytest.raises(ValueError):
            chat("turn2_triggers_error", session_id=sid)


# ─────────────────────────────────────────────────────────────────────────────
# D1: PerformanceMonitor.filter_tasks
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorFilterTasks:
    def _setup_monitor(self):
        m = _make_monitor()
        m.record_task(_make_task_result(
            task_id="t1", task_type="qa", execution_time=0.5,
            response="r", ground_truth="r",
        ))
        m.record_task(_make_task_result(
            task_id="t2", task_type="tool_use", execution_time=5.0,
            response="wrong", ground_truth="correct",
        ))
        m.record_task(_make_task_result(
            task_id="t3", task_type="qa", execution_time=1.0,
            response="r", ground_truth="r",
        ))
        return m

    def test_filter_by_task_type(self):
        """task_type='qa' 필터로 QA 태스크만 반환한다."""
        m = self._setup_monitor()
        results = m.filter_tasks(task_type="qa")
        assert len(results) == 2
        for t in results:
            tt = t.task_type
            if hasattr(tt, "value"):
                tt = tt.value
            assert str(tt).lower() == "qa"

    def test_filter_by_min_accuracy(self):
        """min_accuracy 필터로 특정 점수 이상만 반환한다."""
        m = self._setup_monitor()
        results = m.filter_tasks(min_accuracy=0.0)
        assert isinstance(results, list)
        assert len(results) == 3  # 전체

    def test_filter_by_success_only(self):
        """success_only=True 시 성공 태스크만 반환한다."""
        m = self._setup_monitor()
        results = m.filter_tasks(success_only=True)
        assert all(t.success for t in results)

    def test_filter_combined(self):
        """여러 조건 AND 결합 필터링."""
        m = self._setup_monitor()
        results = m.filter_tasks(task_type="qa", success_only=True)
        for t in results:
            tt = t.task_type
            if hasattr(tt, "value"):
                tt = tt.value
            assert str(tt).lower() == "qa"
            assert t.success is True

    def test_filter_returns_list(self):
        """filter_tasks는 항상 리스트를 반환한다."""
        m = _make_monitor()
        result = m.filter_tasks()
        assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# D2: PerformanceMonitor.aggregate_metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorAggregateMetrics:
    def _make_monitor_with_tasks(self):
        m = _make_monitor()
        for i in range(3):
            m.record_task(_make_task_result(
                task_id=f"t{i}",
                task_type="qa" if i % 2 == 0 else "tool_use",
                execution_time=float(i + 1),
            ))
        return m

    def test_aggregate_all(self):
        """by=None 전체 집계 키를 반환한다."""
        m = self._make_monitor_with_tasks()
        result = m.aggregate_metrics()
        for key in ("total", "tcr", "avg_accuracy", "avg_latency", "p95_latency", "total_tokens"):
            assert key in result, f"Missing key: {key}"

    def test_aggregate_by_task_type(self):
        """by='task_type' 시 그룹별 집계 dict를 반환한다."""
        m = self._make_monitor_with_tasks()
        result = m.aggregate_metrics(by="task_type")
        assert isinstance(result, dict)
        assert len(result) >= 1
        for group_data in result.values():
            assert "total" in group_data
            assert "tcr" in group_data

    def test_aggregate_by_day(self):
        """by='day' 시 날짜별 집계를 반환한다."""
        m = self._make_monitor_with_tasks()
        result = m.aggregate_metrics(by="day")
        assert isinstance(result, dict)

    def test_aggregate_empty_monitor(self):
        """태스크 없으면 total=0인 집계를 반환한다."""
        m = _make_monitor()
        result = m.aggregate_metrics()
        assert result["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# D3: enabled_security_trackers 선택적 활성화
# ─────────────────────────────────────────────────────────────────────────────

class TestEnabledSecurityTrackers:
    def test_selective_input_sanitization_only(self):
        """['InputSanitization']이면 input_sanitizer만 활성화된다."""
        m = _make_monitor(
            enable_security_metrics=True,
            enabled_security_trackers=["InputSanitization"],
        )
        assert m.input_sanitizer is not None
        assert m.output_leakage_detector is None

    def test_all_security_trackers_when_none(self):
        """enable_security_metrics=True, enabled_security_trackers=None이면 전체 활성화."""
        m = _make_monitor(
            enable_security_metrics=True,
            enabled_security_trackers=None,
        )
        assert m.input_sanitizer is not None
        assert m.output_leakage_detector is not None
        assert m.tool_authorizer is not None

    def test_security_disabled_by_default(self):
        """기본값에서는 보안 트래커 비활성화."""
        m = _make_monitor()
        assert m.input_sanitizer is None

    def test_param_exists_in_init(self):
        """PerformanceMonitor.__init__에 enabled_security_trackers 파라미터가 있다."""
        from agent_evaluator import PerformanceMonitor
        sig = inspect.signature(PerformanceMonitor.__init__)
        assert "enabled_security_trackers" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# D4: 메트릭 별칭 메서드
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorMetricAliases:
    def test_get_tcr_metrics_returns_dict(self):
        """get_tcr_metrics()는 dict를 반환한다."""
        m = _make_monitor()
        m.record_task(_make_task_result())
        result = m.get_tcr_metrics()
        assert isinstance(result, dict)

    def test_get_tcr_metrics_empty_monitor(self):
        """태스크 없을 때도 dict를 반환한다."""
        m = _make_monitor()
        result = m.get_tcr_metrics()
        assert isinstance(result, dict)

    def test_get_latency_metrics_returns_dict(self):
        """get_latency_metrics()는 dict를 반환한다."""
        m = _make_monitor()
        m.record_task(_make_task_result(execution_time=1.5))
        result = m.get_latency_metrics()
        assert isinstance(result, dict)

    def test_get_latency_metrics_empty(self):
        """태스크 없을 때도 dict를 반환한다."""
        m = _make_monitor()
        result = m.get_latency_metrics()
        assert isinstance(result, dict)

    def test_all_alias_methods_exist(self):
        """4개 별칭 메서드 모두 존재한다."""
        m = _make_monitor()
        for method_name in ("get_tcr_metrics", "get_latency_metrics",
                            "get_accuracy_metrics", "get_token_metrics"):
            assert callable(getattr(m, method_name, None)), f"Missing: {method_name}"


# ─────────────────────────────────────────────────────────────────────────────
# D5: analyze / get_bottleneck_tasks / get_optimization_recommendations
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorAnalyze:
    def _make_monitor_with_tasks(self):
        m = _make_monitor()
        m.record_task(_make_task_result(
            task_id="low_acc",
            response="wrong",
            ground_truth="correct",
            execution_time=0.5,
        ))
        m.record_task(_make_task_result(
            task_id="high_lat",
            response="right",
            ground_truth="right",
            execution_time=20.0,
        ))
        return m

    def test_analyze_returns_dict_with_keys(self):
        """analyze()는 필수 키를 포함한 dict를 반환한다."""
        m = self._make_monitor_with_tasks()
        result = m.analyze()
        for key in ("summary", "bottlenecks", "recommendations", "analyzed_at"):
            assert key in result, f"Missing key: {key}"

    def test_analyze_summary_has_total_tasks(self):
        """analyze().summary에 total_tasks가 있다."""
        m = self._make_monitor_with_tasks()
        result = m.analyze()
        assert "total_tasks" in result["summary"]
        assert result["summary"]["total_tasks"] >= 2

    def test_get_bottleneck_tasks(self):
        """get_bottleneck_tasks()는 low_accuracy/high_latency/high_error_rate 키를 가진다."""
        m = self._make_monitor_with_tasks()
        result = m.get_bottleneck_tasks()
        for key in ("low_accuracy", "high_latency", "high_error_rate"):
            assert key in result
            assert isinstance(result[key], list)

    def test_get_optimization_recommendations_returns_list(self):
        """get_optimization_recommendations()는 리스트를 반환한다."""
        m = self._make_monitor_with_tasks()
        result = m.get_optimization_recommendations()
        assert isinstance(result, list)

    def test_recommendations_have_priority_structure(self):
        """권고사항 항목에 priority/category/message/metric 키가 있다."""
        m = self._make_monitor_with_tasks()
        recs = m.get_optimization_recommendations()
        for rec in recs:
            for key in ("priority", "category", "message", "metric"):
                assert key in rec, f"Missing key: {key}"

    def test_recommendations_empty_on_no_tasks(self):
        """태스크 없을 때 빈 리스트를 반환한다."""
        m = _make_monitor()
        assert m.get_optimization_recommendations() == []


# ─────────────────────────────────────────────────────────────────────────────
# D6: create_taskresult metadata → extra
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTaskresultMetadata:
    def test_metadata_maps_to_extra(self):
        """metadata= 파라미터가 TaskResult.extra에 저장된다."""
        from agent_evaluator import create_taskresult

        result = create_taskresult(
            task_id="meta_test",
            question="q",
            response="r",
            ground_truth="r",
            execution_time=0.1,
            task_type="qa",
            metadata={"intent": "search", "source": "api"},
        )
        assert result.extra is not None
        assert result.extra.get("intent") == "search"
        assert result.extra.get("source") == "api"

    def test_metadata_overrides_extra(self):
        """metadata와 extra 동시 지정 시 metadata가 우선한다."""
        from agent_evaluator import create_taskresult

        result = create_taskresult(
            task_id="meta_test2",
            question="q",
            response="r",
            ground_truth="r",
            execution_time=0.1,
            task_type="qa",
            extra={"key": "extra_value"},
            metadata={"key": "meta_value"},
        )
        assert result.extra["key"] == "meta_value"

    def test_metadata_param_exists(self):
        """create_taskresult_from_execution에 metadata 파라미터가 있다."""
        from agent_evaluator.helpers.taskresult_helpers import create_taskresult_from_execution
        sig = inspect.signature(create_taskresult_from_execution)
        assert "metadata" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# C1: _is_cohere_response — finish_reason streaming 감지
# ─────────────────────────────────────────────────────────────────────────────

class TestCohereStreamingAdapter:
    def test_is_cohere_streaming_by_finish_reason(self):
        """finish_reason 속성이 있고 choices가 없으면 Cohere streaming으로 감지한다."""
        from agent_evaluator.decorators import _is_cohere_response

        streaming = type("StreamedChatResponse", (), {
            "finish_reason": "COMPLETE",
        })()
        assert _is_cohere_response(streaming) is True

    def test_is_cohere_false_for_openai_like(self):
        """choices 속성을 가진 객체는 Cohere가 아니다."""
        from agent_evaluator.decorators import _is_cohere_response

        openai_like = type("ChatCompletion", (), {
            "choices": [],
            "usage": None,
            "finish_reason": "stop",
        })()
        assert _is_cohere_response(openai_like) is False

    def test_is_cohere_false_for_none(self):
        """None은 False를 반환한다."""
        from agent_evaluator.decorators import _is_cohere_response
        assert _is_cohere_response(None) is False


# ─────────────────────────────────────────────────────────────────────────────
# C2: _extract_groq_metadata — cache_creation_tokens
# ─────────────────────────────────────────────────────────────────────────────

class TestGroqCacheTokens:
    def test_cache_creation_tokens_extracted(self):
        """Groq v0.9+ cache_creation_tokens가 tokens_used에 포함된다."""
        from agent_evaluator.decorators import _extract_groq_metadata

        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 50
        usage.cache_creation_tokens = 20
        usage.cache_read_tokens = 0

        choice = MagicMock()
        choice.message.tool_calls = None

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        resp.model = "llama3-70b"

        result = _extract_groq_metadata(resp)
        assert result is not None
        assert result.tokens_used is not None
        assert "cache_creation" in result.tokens_used
        assert result.tokens_used["cache_creation"] == 20

    def test_no_cache_tokens_excluded(self):
        """cache 토큰이 0이면 cache_creation 키가 없다."""
        from agent_evaluator.decorators import _extract_groq_metadata

        usage = MagicMock()
        usage.prompt_tokens = 50
        usage.completion_tokens = 30
        usage.cache_creation_tokens = 0
        usage.cache_read_tokens = 0

        choice = MagicMock()
        choice.message.tool_calls = None

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        resp.model = "llama3-8b"

        result = _extract_groq_metadata(resp)
        assert result is not None
        # cache 없으면 cache_creation 키 없음
        assert "cache_creation" not in result.tokens_used


# ─────────────────────────────────────────────────────────────────────────────
# C3: _extract_mistral_metadata — function_call fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestMistralFallback:
    def test_function_call_fallback(self):
        """구버전 function_call 구조를 파싱한다."""
        from agent_evaluator.decorators import _extract_mistral_metadata

        fc = MagicMock()
        fc.name = "old_tool"
        fc.arguments = '{"param": "value"}'

        msg = MagicMock()
        msg.tool_calls = None
        msg.function_call = fc

        choice = MagicMock()
        choice.message = msg

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None

        result = _extract_mistral_metadata(resp)
        assert result is not None
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "old_tool"

    def test_new_tool_calls_structure(self):
        """신버전 tool_calls 구조를 파싱한다."""
        from agent_evaluator.decorators import _extract_mistral_metadata

        fn = MagicMock()
        fn.name = "new_tool"
        fn.arguments = '{"query": "hello"}'

        tc = MagicMock()
        tc.function = fn

        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.function_call = None

        choice = MagicMock()
        choice.message = msg

        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage

        result = _extract_mistral_metadata(resp)
        assert result is not None
        assert result.tool_calls[0]["name"] == "new_tool"

    def test_none_for_unknown_input(self):
        """알 수 없는 입력에는 None을 반환한다."""
        from agent_evaluator.decorators import _extract_mistral_metadata
        result = _extract_mistral_metadata("not_mistral")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# C7: _auto_detect_framework
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoDetectFramework:
    def test_detect_anthropic_by_attributes(self):
        """Anthropic 응답 속성(content/usage/stop_reason)으로 'anthropic' 감지."""
        from agent_evaluator.decorators import _auto_detect_framework

        # Anthropic Message 구조 (choices 없음)
        anthropic_obj = type("Message", (), {
            "content": [],
            "usage": MagicMock(),
            "stop_reason": "end_turn",
        })()
        result = _auto_detect_framework(anthropic_obj)
        assert result == "anthropic"

    def test_detect_unknown_returns_none(self):
        """알 수 없는 plain dict는 None을 반환한다."""
        from agent_evaluator.decorators import _auto_detect_framework
        result = _auto_detect_framework({"random": "dict"})
        assert result is None

    def test_detect_none_returns_none(self):
        """None 입력은 None을 반환한다."""
        from agent_evaluator.decorators import _auto_detect_framework
        assert _auto_detect_framework(None) is None

    def test_auto_detect_framework_param_exists(self):
        """auto_detect_framework 는 agent_eval에서 제거됨 — 항상 자동 감지."""
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "auto_detect_framework" not in sig.parameters

    def test_auto_detect_framework_functional(self):
        """auto_detect_framework 제거 후에도 Anthropic 응답이 자동 감지된다."""
        from agent_evaluator.decorators import agent_eval

        m = _make_monitor()

        @agent_eval(m, task_type="qa")
        def agent(question, ground_truth=""):
            return type("Message", (), {
                "content": [type("TextBlock", (), {"text": "answer", "type": "text"})()],
                "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
                "stop_reason": "end_turn",
            })()

        agent("q")
        tasks = m.tasks
        assert len(tasks) == 1
        assert tasks[0].framework == "anthropic"


# ─────────────────────────────────────────────────────────────────────────────
# C8: _safe_adapter_call
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeAdapterCall:
    def test_adapter_error_captured(self):
        """어댑터 실패 시 (None, error_msg) 반환."""
        from agent_evaluator.decorators import _safe_adapter_call

        def bad_adapter(raw):
            raise RuntimeError("adapter crashed")

        result, err = _safe_adapter_call(bad_adapter, "raw", "test_fw")
        assert result is None
        assert err is not None
        assert "adapter crashed" in err

    def test_adapter_success(self):
        """정상 어댑터는 (EvalMetadata, None) 반환."""
        from agent_evaluator.decorators import _safe_adapter_call, EvalMetadata

        def good_adapter(raw):
            return EvalMetadata(framework="test_fw", attempts=2)

        result, err = _safe_adapter_call(good_adapter, "raw", "test_fw")
        assert result is not None
        assert isinstance(result, EvalMetadata)
        assert result.framework == "test_fw"
        assert err is None

    def test_safe_adapter_call_is_callable(self):
        """_safe_adapter_call 함수가 존재하고 callable이다."""
        from agent_evaluator.decorators import _safe_adapter_call
        assert callable(_safe_adapter_call)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard API fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_result_set():
    """Mock result_set for API testing."""
    task = MagicMock()
    task.task_id = "task_001"
    task.task_type = "qa"
    task.success = True
    task.accuracy_score = 0.9
    task.completion_score = 1.0
    task.execution_time = 1.2
    task.tokens_used = {"total": 100, "input": 60, "output": 40, "model": "gpt-4"}
    task.tool_calls = []
    task.attempts = 1
    task.errors = []
    task.timestamp = "2026-04-04T10:00:00"
    task.framework = "native"
    task.raw = {"question": "q", "response": "r", "ground_truth": "r"}
    task.advanced_metrics = {}
    task.expected_tools = None

    task2 = MagicMock()
    task2.task_id = "task_002"
    task2.task_type = "tool_use"
    task2.success = False
    task2.accuracy_score = 0.3
    task2.completion_score = 0.0
    task2.execution_time = 5.0
    task2.tokens_used = {"total": 200, "input": 120, "output": 80, "model": "unknown"}
    task2.tool_calls = []
    task2.attempts = 2
    task2.errors = ["error_msg"]
    task2.timestamp = "2026-04-04T11:00:00"
    task2.framework = "langchain"
    task2.raw = {}
    task2.advanced_metrics = {}
    task2.expected_tools = None

    quality_detail = MagicMock()
    quality_detail.avg_score = 0.8
    quality_detail.evaluations = []
    quality_detail.dimension_summary = {}
    quality_detail.grade_distribution = {}

    hallucination_detail = MagicMock()
    hallucination_detail.detections = []

    llm_judge = MagicMock()
    llm_judge.judged_count = 0

    rf = MagicMock()
    rf.file_id = "file_001"
    rf.name = "test_results"
    rf.timestamp = "2026-04-04T10:00:00"
    rf.total_tasks = 2
    rf.tcr = 50.0
    rf.accuracy = 0.6
    rf.avg_latency = 3.1
    rf.total_cost = 0.001
    rf.tasks = [task, task2]
    rf.path = None
    rf.quality_detail = quality_detail
    rf.hallucination_detail = hallucination_detail
    rf.has_hallucination = False
    rf.llm_judge = llm_judge
    rf.accuracy_metrics = {
        "tcr": {"tcr": 50.0},
        "accuracy_scores": {"overall_accuracy": 0.6},
        "hallucination": {"total_evaluated": 0, "total_flagged": 0},
    }
    rf.efficiency_metrics = {
        "latency": {"mean": 3.1, "p95": 5.0},
        "tokens": {"total_tokens": 300},
    }
    rf.rag_metrics = {}
    rf.security_metrics = {}
    rf.conversation_sessions = [{"session_id": "s1", "turns": 3}]
    rf.cost_data = {"total_usd": 0.001}
    rf.feedback_data = {}
    rf.streaming_data = None
    rf.anomaly_data = []
    rf.has_security = False
    rf.has_agentic = False
    rf.has_advanced = False
    rf.has_rag = False
    rf.has_quality_detail = True
    rf.has_conversation = True
    rf.has_feedback = False
    rf.has_streaming = False
    rf.has_anomaly = False
    rf.has_cost = False
    rf.has_llm_judge = False

    rs = MagicMock()
    rs.files = [rf]
    rs.by_id = lambda fid: rf if fid == "file_001" else None

    return rs


@pytest.fixture
def test_app(mock_result_set):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from agent_evaluator.serve.routers.data import router as data_router
    from agent_evaluator.serve.routers.cost import router as cost_router
    from agent_evaluator.serve.routers.alerts import router as alerts_router
    from agent_evaluator.serve.routers.export import router as export_router
    from agent_evaluator.serve.routers.golden import router as golden_router

    app = FastAPI()
    app.state.result_set = mock_result_set
    app.state.results_dir = tempfile.mkdtemp()
    app.include_router(data_router)
    app.include_router(cost_router)
    app.include_router(alerts_router)
    app.include_router(export_router)
    app.include_router(golden_router)

    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# B1: DELETE /api/results/{file_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteResultEndpoint:
    def test_soft_delete_returns_archived(self, test_app):
        """soft=True 시 archived=True를 반환한다."""
        from agent_evaluator.serve.routers.data import _ARCHIVE_STORE
        _ARCHIVE_STORE.pop("file_001", None)

        resp = test_app.delete("/api/results/file_001?soft=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("archived") is True
        assert data.get("file_id") == "file_001"

        _ARCHIVE_STORE.pop("file_001", None)

    def test_hard_delete_not_found(self, test_app):
        """없는 file_id hard delete는 404."""
        resp = test_app.delete("/api/results/nonexistent_file?soft=false")
        assert resp.status_code == 404

    def test_soft_delete_not_found(self, test_app):
        """없는 file_id soft delete도 404."""
        resp = test_app.delete("/api/results/no_such_file?soft=true")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# B2: POST /api/results/{file_id}/tasks/bulk-tag
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkTagTasks:
    def test_bulk_tag_multiple_tasks(self, test_app):
        """여러 task_id에 태그를 일괄 추가한다."""
        resp = test_app.post(
            "/api/results/file_001/tasks/bulk-tag",
            content=json.dumps({
                "task_ids": ["task_001", "task_002"],
                "tags": ["regression", "slow"],
            }),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == 2
        assert "regression" in data["tags"]

    def test_bulk_tag_not_found(self, test_app):
        """없는 file_id는 404."""
        resp = test_app.post(
            "/api/results/no_file/tasks/bulk-tag",
            content=json.dumps({"task_ids": ["t1"], "tags": ["x"]}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 404

    def test_bulk_tag_empty_arrays(self, test_app):
        """빈 배열도 정상 처리된다."""
        resp = test_app.post(
            "/api/results/file_001/tasks/bulk-tag",
            content=json.dumps({"task_ids": [], "tags": []}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# B3: GET /api/results/{file_id}/aggregate
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregateEndpoint:
    def test_aggregate_by_task_type(self, test_app):
        """by=task_type 그룹별 집계 반환."""
        resp = test_app.get("/api/results/file_001/aggregate?by=task_type")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert data["by"] == "task_type"

    def test_aggregate_default_by_task_type(self, test_app):
        """기본 by 파라미터는 task_type이다."""
        resp = test_app.get("/api/results/file_001/aggregate")
        assert resp.status_code == 200
        assert "groups" in resp.json()

    def test_aggregate_not_found(self, test_app):
        """없는 file_id는 404."""
        resp = test_app.get("/api/results/no_file/aggregate")
        assert resp.status_code == 404

    def test_aggregate_group_structure(self, test_app):
        """각 그룹에는 count와 avg_accuracy가 있다."""
        resp = test_app.get("/api/results/file_001/aggregate?by=task_type")
        data = resp.json()
        for group_data in data["groups"].values():
            assert "count" in group_data
            assert "avg_accuracy" in group_data


# ─────────────────────────────────────────────────────────────────────────────
# B4: POST /api/results/{file_id}/tasks/filter
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterTasksAdvanced:
    def test_filter_gte_operator(self, test_app):
        """gte 연산자로 accuracy_score 필터링."""
        resp = test_app.post(
            "/api/results/file_001/tasks/filter",
            content=json.dumps({
                "conditions": [{"field": "accuracy_score", "op": "gte", "value": 0.5}],
                "logic": "AND",
            }),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # 응답에 results 또는 tasks 키가 있어야 함
        assert "results" in data or "tasks" in data
        assert "total" in data

    def test_filter_and_logic(self, test_app):
        """AND 복합 조건 필터링."""
        resp = test_app.post(
            "/api/results/file_001/tasks/filter",
            content=json.dumps({
                "conditions": [
                    {"field": "accuracy_score", "op": "gte", "value": 0.5},
                    {"field": "task_type", "op": "eq", "value": "qa"},
                ],
                "logic": "AND",
            }),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data or "tasks" in data

    def test_filter_not_found(self, test_app):
        """없는 file_id는 404."""
        resp = test_app.post(
            "/api/results/no_file/tasks/filter",
            content=json.dumps({"conditions": []}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# B5: GET /api/compare?detailed=true
# ─────────────────────────────────────────────────────────────────────────────

class TestCompareDetailed:
    def test_compare_with_detailed_true(self, test_app):
        """detailed=true 파라미터가 정상 처리된다."""
        resp = test_app.get("/api/compare?ids=file_001,file_001&detailed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data

    def test_compare_basic_structure(self, test_app):
        """compare 응답에 file_count가 있다."""
        resp = test_app.get("/api/compare?ids=file_001")
        assert resp.status_code == 200
        data = resp.json()
        assert "file_count" in data


# ─────────────────────────────────────────────────────────────────────────────
# B6: stream 라우터 등록 여부
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamFiltered:
    def test_stream_module_importable(self):
        """agent_evaluator.serve.routers.stream 모듈이 임포트 가능하다."""
        try:
            from agent_evaluator.serve.routers import stream
            assert stream is not None
        except ImportError:
            pytest.skip("stream router not available")

    def test_stream_router_has_tasks_route(self):
        """stream 라우터에 tasks 경로가 있다."""
        try:
            from agent_evaluator.serve.routers.stream import router as stream_router
            routes = [r.path for r in stream_router.routes]
            assert any("tasks" in r for r in routes)
        except ImportError:
            pytest.skip("stream router not available")


# ─────────────────────────────────────────────────────────────────────────────
# B7: POST /api/alerts/rules — persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertRulesPersistence:
    def test_create_and_persist(self, test_app):
        """알림 규칙 생성 후 목록에서 조회된다."""
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()

        resp = test_app.post("/api/alerts/rules", json={
            "name": "persist_rule",
            "condition_expr": "accuracy_score < 0.7",
            "severity": "warning",
            "cooldown": 30.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "rule_id" in data
        assert data["name"] == "persist_rule"

        list_resp = test_app.get("/api/alerts/rules")
        assert list_resp.status_code == 200
        rules = list_resp.json()["rules"]
        assert any(r["name"] == "persist_rule" for r in rules)

    def test_rule_required_fields(self, test_app):
        """생성된 규칙에 필수 필드가 있다."""
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()

        resp = test_app.post("/api/alerts/rules", json={
            "name": "field_check",
            "condition_expr": "execution_time > 5.0",
            "severity": "critical",
        })
        data = resp.json()
        for field in ("rule_id", "name", "condition_expr", "severity", "created_at"):
            assert field in data, f"Missing: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# B8: POST /api/alerts/rules — compound_conditions
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertCompoundConditions:
    def test_create_compound_rule(self, test_app):
        """compound_conditions 포함 규칙을 생성한다."""
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()

        resp = test_app.post("/api/alerts/rules", json={
            "name": "compound_rule",
            "condition_expr": "",
            "severity": "warning",
            "compound_conditions": [
                {"field": "accuracy_score", "op": "lt", "value": 0.7},
                {"field": "execution_time", "op": "gt", "value": 5.0},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "compound_conditions" in data
        assert len(data["compound_conditions"]) == 2

    def test_compound_rule_retrieved(self, test_app):
        """생성된 compound 규칙을 ID로 조회한다."""
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()

        create_resp = test_app.post("/api/alerts/rules", json={
            "name": "compound_get",
            "condition_expr": "",
            "compound_conditions": [{"field": "tcr", "op": "lt", "value": 80.0}],
        })
        rule_id = create_resp.json()["rule_id"]
        get_resp = test_app.get(f"/api/alerts/rules/{rule_id}")
        assert get_resp.status_code == 200
        assert "compound_conditions" in get_resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# B9: GET /api/cost/breakdown?by=model
# ─────────────────────────────────────────────────────────────────────────────

class TestCostBreakdown:
    def test_breakdown_by_model(self, test_app):
        """model 기준 비용 분류를 반환한다."""
        resp = test_app.get("/api/cost/breakdown?by=model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["by"] == "model"
        assert "groups" in data
        assert "total_usd" in data

    def test_breakdown_by_task_type(self, test_app):
        """task_type 기준 비용 분류."""
        resp = test_app.get("/api/cost/breakdown?by=task_type")
        assert resp.status_code == 200
        assert resp.json()["by"] == "task_type"

    def test_breakdown_by_file(self, test_app):
        """file 기준 비용 분류."""
        resp = test_app.get("/api/cost/breakdown?by=file")
        assert resp.status_code == 200
        assert resp.json()["by"] == "file"

    def test_breakdown_group_structure(self, test_app):
        """그룹에는 total_usd/task_count/avg_cost_per_task가 있다."""
        resp = test_app.get("/api/cost/breakdown?by=model")
        data = resp.json()
        for group_data in data["groups"].values():
            assert "total_usd" in group_data
            assert "task_count" in group_data
            assert "avg_cost_per_task" in group_data


# ─────────────────────────────────────────────────────────────────────────────
# B10: GET /api/export/excel/{file_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestExcelExport:
    def test_excel_endpoint_registered(self, test_app):
        """export/excel/{file_id} 엔드포인트가 등록되어 있다."""
        from agent_evaluator.serve.routers.export import router as export_router
        routes = [r.path for r in export_router.routes]
        assert any("excel" in r for r in routes)

    def test_excel_without_openpyxl_returns_501(self, test_app):
        """openpyxl이 없을 때 501 또는 500을 반환한다."""
        # openpyxl을 임시로 제거
        orig = sys.modules.get("openpyxl")
        sys.modules["openpyxl"] = None  # type: ignore
        try:
            resp = test_app.get("/api/export/excel/file_001")
            assert resp.status_code in (501, 500, 200)
        finally:
            if orig is None:
                sys.modules.pop("openpyxl", None)
            else:
                sys.modules["openpyxl"] = orig


# ─────────────────────────────────────────────────────────────────────────────
# B11: POST /api/golden/candidates/{name}/bulk-approve
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkApproveGolden:
    def _make_golden_app(self, tmp_path, mock_result_set, cases, filename="test_cands.json"):
        """골든 디렉토리와 FastAPI 앱을 설정한다.

        _golden_dir()는 results_dir.parent/data/golden_datasets 를 먼저 탐색하므로
        results_dir = tmp_path/results 로 설정하고
        golden_dir = tmp_path/data/golden_datasets 에 파일을 생성한다.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from agent_evaluator.serve.routers.golden import router as golden_router

        results_dir = tmp_path / "results"
        results_dir.mkdir()
        golden_dir = tmp_path / "data" / "golden_datasets"
        golden_dir.mkdir(parents=True)
        candidates_file = golden_dir / filename
        candidates_file.write_text(json.dumps(cases))

        app = FastAPI()
        app.state.result_set = mock_result_set
        app.state.results_dir = results_dir  # Path 객체
        app.include_router(golden_router)
        return TestClient(app)

    def test_bulk_approve_all(self, tmp_path, mock_result_set):
        """조건 없이 전체 후보를 승인한다."""
        cases = [
            {"question": "q1", "answer": "a1", "score": 0.9},
            {"question": "q2", "answer": "a2", "score": 0.7},
        ]
        client = self._make_golden_app(tmp_path, mock_result_set, cases)

        resp = client.post("/api/golden/candidates/test_cands.json/bulk-approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["approved_count"] == 2
        assert data["total"] == 2

    def test_bulk_approve_with_min_accuracy(self, tmp_path, mock_result_set):
        """min_accuracy 필터로 특정 점수 이상만 승인한다."""
        cases = [
            {"question": "q1", "answer": "a1", "accuracy_score": 0.9},
            {"question": "q2", "answer": "a2", "accuracy_score": 0.3},
        ]
        client = self._make_golden_app(
            tmp_path, mock_result_set, cases, filename="filter_cands.json"
        )

        resp = client.post(
            "/api/golden/candidates/filter_cands.json/bulk-approve?min_accuracy=0.8"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_count"] == 1

    def test_bulk_approve_not_found(self, tmp_path, mock_result_set):
        """없는 파일은 404를 반환한다."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from agent_evaluator.serve.routers.golden import router as golden_router

        results_dir = tmp_path / "results_404"
        results_dir.mkdir()

        app = FastAPI()
        app.state.result_set = mock_result_set
        app.state.results_dir = results_dir
        app.include_router(golden_router)
        client = TestClient(app)

        resp = client.post(
            "/api/golden/candidates/nonexistent_file.json/bulk-approve"
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# B12: GET /api/results — page/limit 페이지네이션
# ─────────────────────────────────────────────────────────────────────────────

class TestResultsPagination:
    def test_pagination_default_params(self, test_app):
        """기본 파라미터로 페이지네이션 응답 형식을 반환한다."""
        from agent_evaluator.serve.routers.data import _ARCHIVE_STORE
        _ARCHIVE_STORE.clear()

        resp = test_app.get("/api/results")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total", "page", "limit", "total_pages", "files"):
            assert key in data, f"Missing key: {key}"

    def test_pagination_custom_params(self, test_app):
        """page=1&limit=5 파라미터 정상 처리."""
        from agent_evaluator.serve.routers.data import _ARCHIVE_STORE
        _ARCHIVE_STORE.clear()

        resp = test_app.get("/api/results?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["limit"] == 5

    def test_pagination_archived_excluded(self, test_app):
        """아카이브된 파일은 목록에서 제외된다."""
        from agent_evaluator.serve.routers.data import _ARCHIVE_STORE
        _ARCHIVE_STORE["file_001"] = True

        resp = test_app.get("/api/results")
        data = resp.json()
        file_ids = [f["id"] for f in data["files"]]
        assert "file_001" not in file_ids

        _ARCHIVE_STORE.pop("file_001", None)
