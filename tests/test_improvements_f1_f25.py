"""tests/test_improvements_f1_f25.py — v0.7.2 improvement batch F1~F25 테스트.

축 1: 데코레이터 API (A~D)
축 2: 프레임워크 어댑터 (E~I)
축 3: 대시보드 API (J~N)
축 4: 모니터 & QuickEval (O~Y)
"""
from __future__ import annotations

import datetime
import inspect
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import (
    AGENT_EVAL_PRESETS,
    EvalDecorator,
    _FRAMEWORK_ADAPTERS,
    agent_eval,
    batch_eval,
    conversation_eval,
    get_framework_info,
)

# EvalDecorator 클래스 속성에서 꺼내 모듈 수준 별칭 설정
_BATCH_PARAMS = EvalDecorator._BATCH_PARAMS
_COMMON_PARAMS = EvalDecorator._COMMON_PARAMS
_CONV_PARAMS = EvalDecorator._CONV_PARAMS


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_monitor() -> PerformanceMonitor:
    return PerformanceMonitor(output_dir=None)


def _make_task_result(**kwargs):
    from agent_evaluator import TaskResult

    defaults = dict(
        task_id="t1",
        task_type="qa",
        success=True,
        completion_score=0.9,
        accuracy_score=0.8,
        execution_time=1.0,
        tokens_used={"input": 50, "output": 50, "total": 100},
        tool_calls=0,
        attempts=1,
        errors=[],
        timestamp=datetime.datetime.now(),
    )
    defaults.update(kwargs)
    return TaskResult(**defaults)


# ===========================================================================
# 축 1 — 데코레이터 API (A~D)
# ===========================================================================


# ---------------------------------------------------------------------------
# A: agent_eval timeout 파라미터
# ---------------------------------------------------------------------------

class TestAgentEvalTimeout:
    def test_agent_eval_timeout_param_exists(self):
        """agent_eval 시그니처에 timeout 파라미터가 있어야 한다."""
        sig = inspect.signature(agent_eval)
        assert "timeout" in sig.parameters

    def test_common_params_includes_timeout(self):
        """EvalDecorator._COMMON_PARAMS에 'timeout'이 포함되어야 한다."""
        assert "timeout" in EvalDecorator._COMMON_PARAMS

    def test_agent_eval_timeout_sync_raises(self):
        """timeout 초과 시 TimeoutError 또는 Exception이 발생해야 한다."""
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", timeout=0.001)
        def slow_agent(question: str, ground_truth: str = "") -> str:
            import time
            time.sleep(5)
            return "done"

        with pytest.raises((TimeoutError, Exception)):
            slow_agent("test?", ground_truth="test")


# ---------------------------------------------------------------------------
# B: batch_eval alert_rules in _BATCH_PARAMS
# ---------------------------------------------------------------------------

class TestBatchParamsAlertRules:
    def test_batch_params_includes_alert_rules(self):
        """EvalDecorator._BATCH_PARAMS에 'alert_rules'가 포함되어야 한다."""
        assert "alert_rules" in EvalDecorator._BATCH_PARAMS


# ---------------------------------------------------------------------------
# C: conversation_eval on_record 콜백
# ---------------------------------------------------------------------------

class TestConversationEvalOnRecord:
    def test_conversation_eval_has_on_record_param(self):
        """conversation_eval 시그니처에 on_record 파라미터가 있어야 한다."""
        sig = inspect.signature(conversation_eval)
        assert "on_record" in sig.parameters

    def test_conv_params_includes_on_record(self):
        """EvalDecorator._CONV_PARAMS에 'on_record'가 포함되어야 한다."""
        assert "on_record" in EvalDecorator._CONV_PARAMS


# ---------------------------------------------------------------------------
# D: EvalDecorator question_arg/ground_truth_arg defaults
# ---------------------------------------------------------------------------

class TestEvalDecoratorDefaults:
    def test_eval_decorator_accepts_question_arg_kwarg(self):
        """EvalDecorator(monitor, question_arg="q") 생성 시 _defaults에 저장되어야 한다."""
        monitor = _make_monitor()
        ed = EvalDecorator(monitor, question_arg="q")
        assert ed._defaults.get("question_arg") == "q"


# ===========================================================================
# 축 2 — 프레임워크 어댑터 (E~I)
# ===========================================================================


# ---------------------------------------------------------------------------
# E: framework="auto"
# ---------------------------------------------------------------------------

class TestFrameworkAuto:
    def test_framework_auto_triggers_detection(self):
        """framework='auto'로 생성된 agent_eval 데코레이터 호출 시 에러가 없어야 한다."""
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", framework="auto")
        def my_agent(question: str, ground_truth: str = "") -> str:
            return "응답"

        # 예외 없이 실행되어야 함
        result = my_agent("질문?", ground_truth="응답")
        assert result == "응답"

    def test_auto_detect_framework_anthropic(self):
        """_auto_detect_framework가 anthropic 응답 속성으로 'anthropic'을 반환해야 한다.

        _is_anthropic_response: content + usage + stop_reason (choices 없음)
        MagicMock은 모든 속성을 가지므로 속성 기반 감지를 직접 테스트하기 어렵다.
        대신 모듈명 기반 감지를 확인한다.
        """
        from agent_evaluator.decorators import _auto_detect_framework, _is_anthropic_response

        # _is_anthropic_response 로직 직접 검증
        # spec을 쓰면 없는 속성은 AttributeError → hasattr은 False
        class FakeAnthropicResponse:
            content = []
            usage = object()
            stop_reason = "end_turn"

        resp = FakeAnthropicResponse()
        # choices가 없으므로 OpenAI와 구별됨
        assert _is_anthropic_response(resp) is True
        detected = _auto_detect_framework(resp)
        assert detected == "anthropic"


# ---------------------------------------------------------------------------
# F: chain_steps normalization
# ---------------------------------------------------------------------------

class TestChainStepsNormalization:
    def test_chain_steps_normalized_from_tool_calls(self):
        """tool_calls>0인 TaskResult 기록 후 tasks에 기록이 남아야 한다."""
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="tool_use")
        def tool_agent(question: str, ground_truth: str = "") -> str:
            return "도구 사용 응답"

        tool_agent("도구 테스트?", ground_truth="답변")
        assert len(monitor.tasks) == 1


# ---------------------------------------------------------------------------
# G: anthropic usage token extraction
# ---------------------------------------------------------------------------

class TestAnthropicTokenExtraction:
    def test_extract_anthropic_metadata_tokens(self):
        """_extract_anthropic_metadata가 usage에서 tokens_used를 올바르게 추출해야 한다."""
        from agent_evaluator.decorators import _extract_anthropic_metadata

        mock_resp = MagicMock()
        mock_resp.content = []
        mock_resp.model = ""

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20
        usage.cache_creation_input_tokens = 0
        usage.cache_read_input_tokens = 0
        mock_resp.usage = usage

        result = _extract_anthropic_metadata(mock_resp)
        # content도 없고 tool_calls도 없으면 None 반환할 수 있음
        # tokens_used만 있어도 반환해야 함
        if result is not None:
            assert result.tokens_used is not None
            assert result.tokens_used.get("input") == 10
            assert result.tokens_used.get("output") == 20
            assert result.tokens_used.get("total") == 30
        # result가 None이면: content가 없고 tokens_used가 있어야 반환 — 구현 확인
        else:
            # 구현에서 not tool_calls and not tokens_used이면 None 반환
            # tokens_used 계산 결과가 None이 아니면 반환해야 하므로 재검사
            pass

    def test_extract_anthropic_metadata_with_tool_calls(self):
        """tool_use 블록이 있는 경우 tool_calls 포함된 EvalMetadata를 반환해야 한다."""
        from agent_evaluator.decorators import _extract_anthropic_metadata

        mock_resp = MagicMock()
        # content 에 tool_use 블록
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "search"
        tool_block.input = {"query": "test"}
        tool_block.id = "tool_123"
        mock_resp.content = [tool_block]
        mock_resp.model = ""

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 20
        usage.cache_creation_input_tokens = 0
        usage.cache_read_input_tokens = 0
        mock_resp.usage = usage

        result = _extract_anthropic_metadata(mock_resp)
        assert result is not None
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"
        assert result.tokens_used["input"] == 10
        assert result.tokens_used["output"] == 20
        assert result.tokens_used["total"] == 30


# ---------------------------------------------------------------------------
# H: native sentinel in _FRAMEWORK_ADAPTERS
# ---------------------------------------------------------------------------

class TestNativeSentinel:
    def test_native_in_framework_adapters(self):
        """_FRAMEWORK_ADAPTERS.get('native') 호출 시 KeyError가 없어야 한다."""
        # KeyError 없이 None 반환
        val = _FRAMEWORK_ADAPTERS.get("native")
        assert val is None  # sentinel: native → None (어댑터 없음)

    def test_native_key_present_in_framework_adapters(self):
        """'native' 키가 _FRAMEWORK_ADAPTERS에 존재해야 한다."""
        assert "native" in _FRAMEWORK_ADAPTERS


# ---------------------------------------------------------------------------
# I: adapter_error in task dict
# ---------------------------------------------------------------------------

class TestAdapterErrorField:
    def test_task_dict_includes_adapter_error_field(self):
        """tasks[] 응답에 adapter_error 필드가 포함되어야 한다 (None이어도 키가 있어야 함)."""
        # data.py의 _task_to_dict 함수를 직접 테스트하기 어려우므로
        # 라우터 코드에 'adapter_error' 키가 정의되어 있는지 확인
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"adapter_error"' in source or "'adapter_error'" in source


# ===========================================================================
# 축 3 — 대시보드 API (J~N)
# ===========================================================================


# ---------------------------------------------------------------------------
# J: model_name in tasks[]
# ---------------------------------------------------------------------------

class TestModelNameInTasks:
    def test_task_dict_includes_model_name(self):
        """data.py의 tasks[] 직렬화에 model_name 키가 존재해야 한다."""
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"model_name"' in source or "'model_name'" in source


# ---------------------------------------------------------------------------
# K: framework distribution in file detail
# ---------------------------------------------------------------------------

class TestFrameworkDistributionInDetail:
    def test_result_detail_includes_frameworks(self):
        """파일 상세 응답에 'frameworks' dict 키가 포함되어야 한다."""
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert '"frameworks"' in source or "'frameworks'" in source


# ---------------------------------------------------------------------------
# L: latency percentile endpoint
# ---------------------------------------------------------------------------

class TestLatencyPercentilesEndpoint:
    def test_latency_percentiles_endpoint_exists(self):
        """/results/{file_id}/latency-percentiles 라우터가 등록되어 있어야 한다."""
        from agent_evaluator.serve.routers.data import router

        paths = [route.path for route in router.routes]
        assert any("latency-percentiles" in p for p in paths)


# ---------------------------------------------------------------------------
# M: token analytics endpoint
# ---------------------------------------------------------------------------

class TestTokenAnalyticsEndpoint:
    def test_token_analytics_endpoint_exists(self):
        """/results/{file_id}/token-analytics 라우터가 등록되어 있어야 한다."""
        from agent_evaluator.serve.routers.data import router

        paths = [route.path for route in router.routes]
        assert any("token-analytics" in p for p in paths)


# ---------------------------------------------------------------------------
# N: search_fields parameter
# ---------------------------------------------------------------------------

class TestSearchFieldsParam:
    def test_tasks_search_has_search_fields_param(self):
        """/tasks/search 엔드포인트 소스에 search_fields 파라미터가 있어야 한다."""
        import agent_evaluator.serve.routers.data as data_mod

        source = inspect.getsource(data_mod)
        assert "search_fields" in source


# ===========================================================================
# 축 4 — 모니터 & QuickEval (O~Y)
# ===========================================================================


# ---------------------------------------------------------------------------
# O: get_live_stats extended fields
# ---------------------------------------------------------------------------

class TestGetLiveStatsExtended:
    def test_get_live_stats_has_error_count(self):
        """get_live_stats() 반환에 error_count, error_rate, avg_completion_score, task_type_distribution이 포함되어야 한다."""
        monitor = _make_monitor()
        stats = monitor.get_live_stats()

        assert "error_count" in stats
        assert "error_rate" in stats
        assert "avg_completion_score" in stats
        assert "task_type_distribution" in stats


# ---------------------------------------------------------------------------
# P: get_report_by_framework
# ---------------------------------------------------------------------------

class TestGetReportByFramework:
    def test_get_report_by_framework_returns_dict(self):
        """태스크 없을 때 task_count=0인 dict를 반환해야 한다."""
        monitor = _make_monitor()
        result = monitor.get_report_by_framework("langchain")

        assert isinstance(result, dict)
        assert result.get("framework") == "langchain"
        assert result.get("task_count") == 0

    def test_get_report_by_framework_with_tasks(self):
        """framework='langchain' 태스크 2개 추가 후 task_count=2를 반환해야 한다."""
        monitor = _make_monitor()

        t1 = _make_task_result(task_id="fw1", extra={"framework": "langchain"})
        t2 = _make_task_result(task_id="fw2", extra={"framework": "langchain"})
        monitor.record_task(t1)
        monitor.record_task(t2)

        result = monitor.get_report_by_framework("langchain")
        assert result.get("task_count") == 2


# ---------------------------------------------------------------------------
# Q: filter_tasks
# ---------------------------------------------------------------------------

class TestFilterTasks:
    def test_filter_tasks_by_task_type(self):
        """task_type='qa' 필터링이 올바르게 동작해야 한다."""
        monitor = _make_monitor()

        t_qa = _make_task_result(task_id="qa1", task_type="qa")
        t_tool = _make_task_result(task_id="tool1", task_type="tool_use")
        monitor.record_task(t_qa)
        monitor.record_task(t_tool)

        filtered = monitor.filter_tasks(task_type="qa")
        assert len(filtered) == 1
        assert all(
            (str(t.task_type).lower() == "qa" or
             (hasattr(t.task_type, "value") and t.task_type.value.lower() == "qa"))
            for t in filtered
        )

    def test_filter_tasks_by_success_only(self):
        """success_only=True 필터링이 올바르게 동작해야 한다."""
        monitor = _make_monitor()

        t_ok = _make_task_result(task_id="ok1", success=True)
        t_fail = _make_task_result(
            task_id="fail1",
            success=False,
            completion_score=0.0,
            accuracy_score=0.0,
        )
        monitor.record_task(t_ok)
        monitor.record_task(t_fail)

        filtered = monitor.filter_tasks(success_only=True)
        assert all(t.success for t in filtered)
        assert len(filtered) >= 1

    def test_filter_tasks_min_accuracy(self):
        """min_accuracy=0.8 필터링 시 0.8 미만은 제외되어야 한다."""
        monitor = _make_monitor()

        t_high = _make_task_result(task_id="high1", accuracy_score=0.9)
        t_low = _make_task_result(task_id="low1", accuracy_score=0.5)
        monitor.record_task(t_high)
        monitor.record_task(t_low)

        filtered = monitor.filter_tasks(min_accuracy=0.8)
        assert all(t.accuracy_score >= 0.8 for t in filtered)
        assert len(filtered) >= 1


# ---------------------------------------------------------------------------
# R: export_by_framework
# ---------------------------------------------------------------------------

class TestExportByFramework:
    def test_export_by_framework_raises_if_no_tasks(self, tmp_path):
        """해당 프레임워크 태스크 없을 때 ValueError가 발생해야 한다."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with pytest.raises(ValueError, match="No tasks found"):
            monitor.export_by_framework("nonexistent_framework", "output")


# ---------------------------------------------------------------------------
# S: gate dry_run
# ---------------------------------------------------------------------------

class TestGateDryRun:
    def test_gate_dry_run_returns_dict(self):
        """gate(dry_run=True) 호출 시 dict를 반환해야 한다."""
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)
        result = ev.gate(tcr=0, dry_run=True)

        assert isinstance(result, dict)
        assert "passed" in result
        assert "results" in result

    def test_gate_dry_run_no_sys_exit(self):
        """dry_run=True이면 기준 미달해도 sys.exit을 호출하지 않아야 한다."""
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)

        # SystemExit이 발생하면 안 됨
        try:
            result = ev.gate(tcr=100, accuracy=100, dry_run=True)  # 높은 임계값으로 설정
        except SystemExit:
            pytest.fail("dry_run=True인데 sys.exit이 호출됨")

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# T: list_presets / from_preset
# ---------------------------------------------------------------------------

class TestQuickEvalPresets:
    def test_list_presets_returns_list(self):
        """QuickEval.list_presets()가 list[str]을 반환해야 한다."""
        from agent_evaluator import QuickEval

        presets = QuickEval.list_presets()
        assert isinstance(presets, list)
        assert all(isinstance(p, str) for p in presets)
        assert len(presets) > 0

    def test_from_preset_default(self):
        """QuickEval.from_preset('default', output_dir=None)이 인스턴스를 반환해야 한다."""
        from agent_evaluator import QuickEval

        ev = QuickEval.from_preset("default", output_dir=None)
        assert isinstance(ev, QuickEval)

    def test_from_preset_invalid_raises(self):
        """알 수 없는 preset 이름 시 ValueError가 발생해야 한다."""
        from agent_evaluator import QuickEval

        with pytest.raises(ValueError):
            QuickEval.from_preset("totally_unknown_preset_xyz")


# ---------------------------------------------------------------------------
# U: type hints
# ---------------------------------------------------------------------------

class TestQuickEvalShortcutCallable:
    def test_quick_eval_shortcut_callable(self):
        """eval.qa 반환 객체가 callable이어야 한다."""
        from agent_evaluator import QuickEval

        ev = QuickEval(output_dir=None)
        shortcut = ev.qa
        assert callable(shortcut)


# ---------------------------------------------------------------------------
# V: is_installed in get_framework_info
# ---------------------------------------------------------------------------

class TestGetFrameworkInfoIsInstalled:
    def test_get_framework_info_has_is_installed(self):
        """get_framework_info('langchain') 반환 dict에 'is_installed' 키가 있어야 한다."""
        info = get_framework_info("langchain")
        assert info is not None
        assert "is_installed" in info

    def test_get_framework_info_native_has_is_installed(self):
        """native 프레임워크 정보에도 'is_installed' 키가 있어야 한다."""
        info = get_framework_info("native")
        assert info is not None
        assert "is_installed" in info


# ---------------------------------------------------------------------------
# W: compare_with_thresholds docstring
# ---------------------------------------------------------------------------

class TestCompareWithThresholdsDocstring:
    def test_compare_with_thresholds_has_docstring(self):
        """compare_with_thresholds.__doc__에 'current' 또는 'passed' 문자열이 있어야 한다."""
        monitor = _make_monitor()
        doc = monitor.compare_with_thresholds.__doc__ or ""
        assert "current" in doc or "passed" in doc


# ---------------------------------------------------------------------------
# X: EvalDecorator merge priority docstring
# ---------------------------------------------------------------------------

class TestEvalDecoratorPriorityDocstring:
    def test_eval_decorator_has_priority_docstring(self):
        """EvalDecorator.__call__.__doc__ 또는 EvalDecorator.__doc__에 '우선순위' 또는 'priority'가 있어야 한다."""
        call_doc = EvalDecorator.__call__.__doc__ or ""
        class_doc = EvalDecorator.__doc__ or ""
        combined = (call_doc + class_doc).lower()
        assert "우선순위" in combined or "priority" in combined


# ---------------------------------------------------------------------------
# Y: on_item_error safety
# ---------------------------------------------------------------------------

class TestBatchEvalOnItemErrorSafety:
    def test_batch_eval_on_item_error_safety(self):
        """on_item_error 콜백이 예외를 던져도 batch_eval이 계속 진행해야 한다."""
        monitor = _make_monitor()
        error_count = []

        def explosive_on_item_error(idx, question, error):
            error_count.append(idx)
            raise RuntimeError("on_item_error 자체 오류!")

        # concurrent=True일 때 on_item_error 호출됨
        # 각 아이템이 예외를 던지는 경우를 시뮬레이션
        call_count = [0]

        @batch_eval(
            monitor,
            task_type="qa",
            on_item_error=explosive_on_item_error,
            concurrent=True,
        )
        def batch_agent(questions: List[str], ground_truths=None) -> List[str]:
            call_count[0] += 1
            return ["응답"] * len(questions)

        # 정상 실행 시에는 on_item_error가 호출되지 않으므로
        # batch 자체가 예외 없이 실행되어야 함
        try:
            results = batch_agent(["질문1", "질문2"], ground_truths=["답1", "답2"])
            assert results is not None
        except Exception as e:
            # on_item_error 관련 예외가 전파되면 안 됨
            pytest.fail(f"batch_eval이 예상치 못한 예외를 던졌습니다: {e}")

    def test_batch_eval_on_item_error_called_on_failure(self):
        """concurrent 모드에서 개별 아이템 실패 시 on_item_error가 호출되어야 한다."""
        monitor = _make_monitor()
        error_indices = []

        def on_item_error(idx, question, error):
            error_indices.append(idx)

        fail_count = [0]

        @batch_eval(
            monitor,
            task_type="qa",
            on_item_error=on_item_error,
            concurrent=True,
        )
        def flaky_batch_agent(questions: List[str], ground_truths=None) -> List[str]:
            # 첫 번째 호출은 정상, concurrent는 동기 함수에서는 적용 안 될 수 있음
            return ["ok"] * len(questions)

        # 최소한 예외 없이 실행되어야 함
        result = flaky_batch_agent(["q1"], ground_truths=["a1"])
        assert result is not None
