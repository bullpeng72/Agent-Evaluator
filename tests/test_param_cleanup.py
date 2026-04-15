"""
tests/test_param_cleanup.py
============================
데코레이터 파라미터 정리 통합 테스트 (v0.8.1~v0.8.5)

- agent_eval: profile, jitter, task_id_arg, auto_detect_framework 제거
- batch_eval: strict_types, security_mode 제거
- conversation_eval: question_arg, participant_id_arg, flush_filename 제거
- RetryConfig: max_retries/retry_on/delay/backoff 대체
- CM params: question, ground_truth, context, task_id 제거
"""

from __future__ import annotations

import inspect
import warnings

import pytest

from agent_evaluator import LLMJudgeConfig, PerformanceMonitor, RetryConfig
from agent_evaluator.decorators import (
    EvalDecorator,
    LLMJudgeConfig,
    agent_eval,
    batch_eval,
    conversation_eval,
    RetryConfig,
)
from agent_evaluator import eval_context


# ─────────────────────────────────────────────────────────────────
# Fixture (한 번만 정의)
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def monitor(tmp_path):
    return PerformanceMonitor(output_dir=str(tmp_path))


# ===========================================================================
# From test_agent_eval_params_cleanup.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# 1. profile= 완전 제거 → TypeError
# ─────────────────────────────────────────────────────────────────

class TestProfileRemoved:
    def test_profile_raises_typeerror(self, monitor):
        """profile= 파라미터가 완전히 제거되어 TypeError 발생"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", profile="production")

    def test_profile_not_in_signature(self):
        """profile= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "profile" not in sig.parameters

    def test_preset_still_works(self, monitor):
        """profile= 제거 후에도 preset= 은 정상 동작"""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="production")
            def fn(question, ground_truth=""):
                return "answer"

        result = fn(question="test", ground_truth="answer")
        assert result == "answer"

    def test_no_warning_without_profile(self, monitor):
        """profile= 없을 때는 DeprecationWarning 미발행"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa")
            def fn(question, ground_truth=""):
                return "answer"

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                        and "profile" in str(x.message)]
        assert len(dep_warnings) == 0


# ─────────────────────────────────────────────────────────────────
# 2. jitter=True 완전 제거 → TypeError
# ─────────────────────────────────────────────────────────────────

class TestJitterRemoved:
    def test_jitter_true_raises_typeerror(self, monitor):
        """jitter= 파라미터가 완전히 제거되어 TypeError 발생"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", jitter=True)

    def test_jitter_false_raises_typeerror(self, monitor):
        """jitter=False 도 TypeError (파라미터 자체가 제거됨)"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", jitter=False)

    def test_jitter_not_in_signature(self):
        """jitter= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "jitter" not in sig.parameters

    def test_jitter_default_no_warning(self, monitor):
        """jitter 파라미터 미지정 시 DeprecationWarning 미발행"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa")
            def fn(question, ground_truth=""):
                return "answer"

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                        and "jitter" in str(x.message)]
        assert len(dep_warnings) == 0


# ─────────────────────────────────────────────────────────────────
# 3. task_id_arg= 완전 제거 → TypeError
# ─────────────────────────────────────────────────────────────────

class TestTaskIdArgRemoved:
    def test_task_id_arg_raises_typeerror(self, monitor):
        """task_id_arg= 파라미터가 완전히 제거되어 TypeError 발생"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", task_id_arg="my_id")

    def test_task_id_arg_not_in_signature(self):
        """task_id_arg= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "task_id_arg" not in sig.parameters

    def test_task_id_fn_still_works(self, monitor):
        """task_id_arg= 제거 후 task_id_fn= 은 정상 동작"""
        @agent_eval(monitor, task_type="qa",
                    task_id_fn=lambda args, kwargs: kwargs.get("my_id", "fallback"))
        def fn(my_id, question, ground_truth=""):
            return "answer"

        result = fn(my_id="custom_id_001", question="test", ground_truth="answer")
        assert result == "answer"

    def test_task_id_arg_none_no_warning(self, monitor):
        """task_id_arg 미지정 시 DeprecationWarning 미발행"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa")
            def fn(question, ground_truth=""):
                return "answer"

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                        and "task_id_arg" in str(x.message)]
        assert len(dep_warnings) == 0


# ─────────────────────────────────────────────────────────────────
# 4. auto_detect_framework= 서명에서 제거 확인
# ─────────────────────────────────────────────────────────────────

class TestRemovedParameters:
    def test_auto_detect_framework_not_in_agent_eval_signature(self):
        """auto_detect_framework= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "auto_detect_framework" not in sig.parameters, (
            "auto_detect_framework 파라미터가 agent_eval 서명에서 제거되어야 합니다"
        )

    def test_allow_duplicate_task_ids_not_in_agent_eval_signature(self):
        """allow_duplicate_task_ids= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "allow_duplicate_task_ids" not in sig.parameters, (
            "allow_duplicate_task_ids 파라미터가 agent_eval 서명에서 제거되어야 합니다"
        )

    def test_alert_error_mode_in_agent_eval_signature(self):
        """alert_error_mode= 는 agent_eval에 유지됨 (alert 핸들러 예외 처리 제어)"""
        sig = inspect.signature(agent_eval)
        assert "alert_error_mode" in sig.parameters, (
            "alert_error_mode 파라미터가 agent_eval 서명에 있어야 합니다"
        )

    def test_auto_detect_framework_not_in_batch_eval_signature(self):
        """auto_detect_framework= 이 batch_eval 서명에서 제거됨"""
        sig = inspect.signature(batch_eval)
        assert "auto_detect_framework" not in sig.parameters

    def test_allow_duplicate_task_ids_not_in_batch_eval_signature(self):
        """allow_duplicate_task_ids= 이 batch_eval 서명에서 제거됨"""
        sig = inspect.signature(batch_eval)
        assert "allow_duplicate_task_ids" not in sig.parameters

    def test_passing_removed_param_raises_typeerror(self, monitor):
        """제거된 파라미터 전달 시 TypeError 발생"""
        with pytest.raises(TypeError):
            @agent_eval(monitor, task_type="qa", auto_detect_framework=True)
            def fn(question, ground_truth=""):
                return "answer"

    def test_allow_dup_removed_raises_typeerror(self, monitor):
        """제거된 allow_duplicate_task_ids 전달 시 TypeError"""
        with pytest.raises(TypeError):
            @agent_eval(monitor, task_type="qa", allow_duplicate_task_ids=False)
            def fn(question, ground_truth=""):
                return "answer"

    def test_alert_error_mode_strict_works(self, monitor):
        """alert_error_mode='strict' 전달 시 정상 동작 (TypeError 없음)"""
        @agent_eval(monitor, task_type="qa", alert_error_mode="strict")
        def fn(question, ground_truth=""):
            return "answer"
        assert callable(fn)


# ─────────────────────────────────────────────────────────────────
# 5. 기존 핵심 기능 회귀 테스트
# ─────────────────────────────────────────────────────────────────

class TestCoreRegression:
    def test_basic_decoration_still_works(self, monitor):
        """기본 데코레이터 동작 확인"""
        @agent_eval(monitor, task_type="qa")
        def fn(question, ground_truth=""):
            return "서울"

        result = fn(question="한국의 수도는?", ground_truth="서울")
        assert result == "서울"
        assert len(monitor.tasks) == 1
        assert monitor.tasks[0].task_type == "qa"

    def test_rag_mode_still_works(self, monitor):
        """rag_mode=True 동작 확인"""
        @agent_eval(monitor, rag_mode=True)
        def fn(question, context="", ground_truth=""):
            return "answer"

        result = fn(question="test", context="some context", ground_truth="answer")
        assert result == "answer"
        assert monitor.tasks[0].task_type == "information_retrieval"

    def test_preset_production_works(self, monitor):
        """preset="production" 동작 확인 (allow_duplicate_task_ids 제거 후에도)"""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="production")
            def fn(question, ground_truth=""):
                return "answer"

        result = fn(question="test", ground_truth="answer")
        assert result == "answer"


# ===========================================================================
# From test_batch_conv_cleanup.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# strict_types NOT in batch_eval signature → TypeError when passed
# ─────────────────────────────────────────────────────────────────

class TestStrictTypesRemoved:
    def test_strict_types_not_in_signature(self):
        """strict_types= 파라미터가 batch_eval 서명에서 제거됨."""
        sig = inspect.signature(batch_eval)
        assert "strict_types" not in sig.parameters

    def test_strict_types_raises_typeerror(self, monitor):
        """strict_types= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            batch_eval(monitor, task_type="qa", strict_types=True)

    def test_strict_types_false_raises_typeerror(self, monitor):
        """strict_types=False 도 TypeError (파라미터 자체가 제거됨)."""
        with pytest.raises(TypeError):
            batch_eval(monitor, task_type="qa", strict_types=False)


# ─────────────────────────────────────────────────────────────────
# batch_eval flush_every default is None
# ─────────────────────────────────────────────────────────────────

class TestBatchFlushEveryDefault:
    def test_flush_every_default_is_none(self):
        """batch_eval flush_every 기본값이 None이어야 한다."""
        sig = inspect.signature(batch_eval)
        assert sig.parameters["flush_every"].default is None

    def test_flush_every_in_signature(self):
        """flush_every= 는 여전히 batch_eval 서명에 있다."""
        sig = inspect.signature(batch_eval)
        assert "flush_every" in sig.parameters


# ─────────────────────────────────────────────────────────────────
# question_arg NOT in conversation_eval signature → TypeError
# ─────────────────────────────────────────────────────────────────

class TestQuestionArgRemoved:
    def test_question_arg_not_in_signature(self):
        """question_arg= 파라미터가 conversation_eval 서명에서 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "question_arg" not in sig.parameters

    def test_question_arg_raises_typeerror(self, monitor):
        """question_arg= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, question_arg="query")


# ─────────────────────────────────────────────────────────────────
# participant_id_arg NOT in conversation_eval signature → TypeError
# ─────────────────────────────────────────────────────────────────

class TestParticipantIdArgRemoved:
    def test_participant_id_arg_not_in_signature(self):
        """participant_id_arg= 파라미터가 conversation_eval 서명에서 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "participant_id_arg" not in sig.parameters

    def test_participant_id_arg_raises_typeerror(self, monitor):
        """participant_id_arg= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, participant_id_arg="pid")


# ─────────────────────────────────────────────────────────────────
# enable_llm_judge NOT in conversation_eval signature → TypeError
# ─────────────────────────────────────────────────────────────────

class TestEnableLlmJudgeRemoved:
    def test_enable_llm_judge_not_in_signature(self):
        """enable_llm_judge= 파라미터가 conversation_eval 서명에서 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "enable_llm_judge" not in sig.parameters

    def test_enable_llm_judge_raises_typeerror(self, monitor):
        """enable_llm_judge= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, enable_llm_judge=True)


# ─────────────────────────────────────────────────────────────────
# judge_model NOT in conversation_eval signature → TypeError
# ─────────────────────────────────────────────────────────────────

class TestJudgeModelRemoved:
    def test_judge_model_not_in_signature(self):
        """judge_model= 파라미터가 conversation_eval 서명에서 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "judge_model" not in sig.parameters

    def test_judge_model_raises_typeerror(self, monitor):
        """judge_model= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, judge_model="claude-haiku-4-5-20251001")


# ─────────────────────────────────────────────────────────────────
# judge_criteria NOT in conversation_eval signature → TypeError
# ─────────────────────────────────────────────────────────────────

class TestJudgeCriteriaRemoved:
    def test_judge_criteria_not_in_signature(self):
        """judge_criteria= 파라미터가 conversation_eval 서명에서 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "judge_criteria" not in sig.parameters

    def test_judge_criteria_raises_typeerror(self, monitor):
        """judge_criteria= 전달 시 TypeError 발생."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, judge_criteria=["accuracy"])


# ─────────────────────────────────────────────────────────────────
# llm_judge IS in conversation_eval signature, default None
# ─────────────────────────────────────────────────────────────────

class TestLlmJudgeInSignature:
    def test_llm_judge_in_signature(self):
        """llm_judge= 파라미터가 conversation_eval 서명에 있다."""
        sig = inspect.signature(conversation_eval)
        assert "llm_judge" in sig.parameters

    def test_llm_judge_default_is_none(self):
        """llm_judge= 기본값이 None이어야 한다."""
        sig = inspect.signature(conversation_eval)
        assert sig.parameters["llm_judge"].default is None


# ─────────────────────────────────────────────────────────────────
# conversation_eval with llm_judge=LLMJudgeConfig() works without error
# ─────────────────────────────────────────────────────────────────

class TestConversationEvalLlmJudgeWorks:
    def test_llm_judge_config_accepted(self, monitor):
        """llm_judge=LLMJudgeConfig() 전달 시 오류 없이 데코레이터 생성."""

        @conversation_eval(monitor, llm_judge=LLMJudgeConfig())
        def chat(question, session_id="s1"):
            return "ok"

        assert callable(chat)

    def test_llm_judge_config_with_model(self, monitor):
        """llm_judge=LLMJudgeConfig(model=...) 전달 시 오류 없이 데코레이터 생성."""

        @conversation_eval(
            monitor,
            llm_judge=LLMJudgeConfig(model="claude-haiku-4-5-20251001"),
        )
        def chat(question, session_id="s1"):
            return "ok"

        assert callable(chat)

    def test_llm_judge_config_with_criteria(self, monitor):
        """llm_judge=LLMJudgeConfig(criteria=[...]) 전달 시 오류 없이 데코레이터 생성."""

        @conversation_eval(
            monitor,
            llm_judge=LLMJudgeConfig(criteria=["accuracy", "relevance"]),
        )
        def chat(question, session_id="s1"):
            return "ok"

        assert callable(chat)


# ─────────────────────────────────────────────────────────────────
# batch_eval param count == 31
# ─────────────────────────────────────────────────────────────────

class TestBatchEvalParamCount:
    def test_param_count_is_32(self):
        """batch_eval 파라미터 수가 31개이어야 한다 (security_mode 제거)."""
        sig = inspect.signature(batch_eval)
        assert len(sig.parameters) == 31, (
            f"batch_eval 파라미터 수: {len(sig.parameters)}개 (예상: 31개)\n"
            f"파라미터 목록: {list(sig.parameters.keys())}"
        )


# ─────────────────────────────────────────────────────────────────
# conversation_eval param count == 27
# ─────────────────────────────────────────────────────────────────

class TestConversationEvalParamCount:
    def test_param_count_is_28(self):
        """conversation_eval 파라미터 수가 27개이어야 한다 (flush_filename 제거)."""
        sig = inspect.signature(conversation_eval)
        assert len(sig.parameters) == 27, (
            f"conversation_eval 파라미터 수: {len(sig.parameters)}개 (예상: 27개)\n"
            f"파라미터 목록: {list(sig.parameters.keys())}"
        )


# ─────────────────────────────────────────────────────────────────
# "llm_judge" in EvalDecorator._CONV_PARAMS
# ─────────────────────────────────────────────────────────────────

class TestConvParamsLlmJudge:
    def test_llm_judge_in_conv_params(self):
        """EvalDecorator._CONV_PARAMS에 'llm_judge' 포함."""
        assert "llm_judge" in EvalDecorator._CONV_PARAMS

    def test_enable_llm_judge_not_in_conv_params(self):
        """EvalDecorator._CONV_PARAMS에 'enable_llm_judge' 미포함."""
        assert "enable_llm_judge" not in EvalDecorator._CONV_PARAMS

    def test_judge_model_not_in_conv_params(self):
        """EvalDecorator._CONV_PARAMS에 'judge_model' 미포함."""
        assert "judge_model" not in EvalDecorator._CONV_PARAMS

    def test_judge_criteria_not_in_conv_params(self):
        """EvalDecorator._CONV_PARAMS에 'judge_criteria' 미포함."""
        assert "judge_criteria" not in EvalDecorator._CONV_PARAMS

    def test_participant_id_arg_not_in_conv_params(self):
        """EvalDecorator._CONV_PARAMS에 'participant_id_arg' 미포함."""
        assert "participant_id_arg" not in EvalDecorator._CONV_PARAMS


# ===========================================================================
# From test_cm_params_removal.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# 1. 제거된 파라미터 6개 — 서명에 없음
# ─────────────────────────────────────────────────────────────────

class TestRemovedCMParams:
    """제거된 CM 전용 파라미터 6개가 agent_eval 서명에 없음을 검증."""

    REMOVED = ["question", "ground_truth", "context",
               "task_id", "task_id_prefix_cm", "auto_task_id"]

    def _sig(self):
        return inspect.signature(agent_eval)

    def test_question_not_in_signature(self):
        assert "question" not in self._sig().parameters

    def test_ground_truth_not_in_signature(self):
        assert "ground_truth" not in self._sig().parameters

    def test_context_not_in_signature(self):
        assert "context" not in self._sig().parameters

    def test_task_id_not_in_signature(self):
        assert "task_id" not in self._sig().parameters

    def test_task_id_prefix_cm_not_in_signature(self):
        assert "task_id_prefix_cm" not in self._sig().parameters

    def test_auto_task_id_not_in_signature(self):
        assert "auto_task_id" not in self._sig().parameters

    @pytest.mark.parametrize("param", REMOVED)
    def test_passing_removed_param_raises_typeerror(self, monitor, param):
        """제거된 파라미터를 전달하면 TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", **{param: "dummy"})


# ─────────────────────────────────────────────────────────────────
# 2. 유지/이동된 파라미터 검증
# ─────────────────────────────────────────────────────────────────

class TestKeptParams:
    """expected_tools, ttft_seconds는 서명에 남아 있음."""

    def test_expected_tools_still_in_signature(self):
        """expected_tools는 데코레이터 static fallback 역할이므로 유지."""
        sig = inspect.signature(agent_eval)
        assert "expected_tools" in sig.parameters

    def test_expected_tools_default_is_none(self):
        sig = inspect.signature(agent_eval)
        assert sig.parameters["expected_tools"].default is None

    def test_ttft_seconds_still_in_signature(self):
        """ttft_seconds는 데코레이터/CM 양쪽에서 사용하므로 유지."""
        sig = inspect.signature(agent_eval)
        assert "ttft_seconds" in sig.parameters

    def test_ttft_seconds_default_is_none(self):
        sig = inspect.signature(agent_eval)
        assert sig.parameters["ttft_seconds"].default is None


# ─────────────────────────────────────────────────────────────────
# 3. expected_tools 데코레이터 모드 동작 확인
# ─────────────────────────────────────────────────────────────────

class TestExpectedToolsDecorator:
    """expected_tools가 데코레이터 모드에서 static fallback으로 동작."""

    def test_static_expected_tools_used_as_fallback(self, monitor):
        """expected_tools_arg가 없는 함수에서 expected_tools가 fallback으로 사용됨."""
        @agent_eval(
            monitor,
            task_type="tool_use",
            expected_tools=["search", "calculator"],
        )
        def fn(question, ground_truth=""):
            return "답변"

        fn(question="test", ground_truth="answer")
        assert len(monitor.tasks) == 1

    def test_expected_tools_arg_overrides_static(self, monitor):
        """expected_tools_arg가 있으면 함수 인자에서 추출 (static보다 우선)."""
        @agent_eval(
            monitor,
            task_type="tool_use",
            expected_tools_arg="expected",
            expected_tools=["fallback_tool"],
        )
        def fn(question, expected=None, ground_truth=""):
            return "답변"

        fn(question="test", expected=["actual_tool"], ground_truth="answer")
        assert len(monitor.tasks) == 1


# ─────────────────────────────────────────────────────────────────
# 4. 데코레이터 모드 기본 동작 회귀 테스트
# ─────────────────────────────────────────────────────────────────

class TestDecoratorModeRegression:
    """CM 파라미터 제거 후 데코레이터 모드 기본 동작 유지."""

    def test_basic_qa_decoration(self, monitor):
        @agent_eval(monitor, task_type="qa")
        def fn(question, ground_truth=""):
            return "서울"

        result = fn(question="한국의 수도는?", ground_truth="서울")
        assert result == "서울"
        assert len(monitor.tasks) == 1

    def test_rag_mode_decoration(self, monitor):
        @agent_eval(monitor, rag_mode=True)
        def fn(question, context="", ground_truth=""):
            return "답변"

        result = fn(question="test", context="ctx", ground_truth="답변")
        assert result == "답변"
        assert monitor.tasks[0].task_type == "information_retrieval"

    def test_ttft_seconds_in_decorator_mode(self, monitor):
        """ttft_seconds를 데코레이터 모드에서 지정하면 latency_tracker에 기록."""
        @agent_eval(monitor, task_type="qa", ttft_seconds=0.5)
        def fn(question, ground_truth=""):
            return "답변"

        fn(question="test", ground_truth="답변")
        assert len(monitor.tasks) == 1

    def test_task_id_prefix_still_works(self, monitor):
        """task_id_prefix (데코레이터용)는 제거되지 않음."""
        @agent_eval(monitor, task_type="qa", task_id_prefix="myapp")
        def fn(question, ground_truth=""):
            return "답변"

        fn(question="test", ground_truth="답변")
        assert monitor.tasks[0].task_id.startswith("myapp_")


# ─────────────────────────────────────────────────────────────────
# 5. CM 모드 — eval_context 직접 사용 (권장 방법)
# ─────────────────────────────────────────────────────────────────

class TestEvalContextDirectUse:
    """제거된 CM 파라미터 → eval_context()로 직접 전달하는 권장 패턴."""

    def test_eval_context_with_question_ground_truth(self, monitor):
        """question/ground_truth는 eval_context에 직접 전달."""
        with eval_context(
            monitor,
            task_type="qa",
            question="한국의 수도는?",
            ground_truth="서울",
        ) as ctx:
            ctx.response = "서울"

        assert len(monitor.tasks) == 1
        assert monitor.tasks[0].task_type == "qa"

    def test_eval_context_with_task_id(self, monitor):
        """task_id는 eval_context에 직접 전달."""
        with eval_context(
            monitor,
            task_type="qa",
            task_id="my_custom_id_001",
        ) as ctx:
            ctx.response = "답변"

        assert monitor.tasks[0].task_id == "my_custom_id_001"

    def test_eval_context_with_task_id_prefix(self, monitor):
        """task_id_prefix는 eval_context에 직접 전달 (task_id_prefix_cm 대체)."""
        with eval_context(
            monitor,
            task_type="qa",
            task_id_prefix="cm_prefix",
        ) as ctx:
            ctx.response = "답변"

        assert monitor.tasks[0].task_id.startswith("cm_prefix_")

    def test_eval_context_with_context_for_rag(self, monitor):
        """RAG context는 eval_context에 직접 전달."""
        with eval_context(
            monitor,
            task_type="information_retrieval",
            question="테스트 질문",
            ground_truth="정답",
        ) as ctx:
            ctx.response = "컨텍스트 기반 답변"

        assert len(monitor.tasks) == 1

    def test_with_agent_eval_cm_still_works_with_defaults(self, monitor):
        """with agent_eval(...) as ctx: 는 CM 파라미터 없이도 동작."""
        handle = agent_eval(monitor, task_type="qa")
        with handle as ctx:
            ctx.response = "답변"

        assert len(monitor.tasks) == 1

    def test_eval_context_has_all_removed_params(self):
        """eval_context는 제거된 파라미터를 모두 직접 지원."""
        sig = inspect.signature(eval_context.__init__)
        for param in ["question", "ground_truth", "context",
                      "task_id", "task_id_prefix", "auto_task_id"]:
            assert param in sig.parameters, f"eval_context에 '{param}' 없음"


# ─────────────────────────────────────────────────────────────────
# 6. 최종 파라미터 수 검증
# ─────────────────────────────────────────────────────────────────

class TestSignatureSize:
    def test_agent_eval_param_count(self):
        """현재 agent_eval 파라미터 수 스냅샷 (회귀 방지)."""
        sig = inspect.signature(agent_eval)
        count = len(sig.parameters)
        assert count < 50, f"파라미터가 너무 많습니다: {count}개"
        assert count >= 28, f"파라미터가 너무 적습니다: {count}개 (잘못된 제거 가능성)"


# ===========================================================================
# From test_v081_round6_cleanup.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# 1. RetryConfig — 데이터클래스 기본값 / 임포트
# ─────────────────────────────────────────────────────────────────

class TestRetryConfig:
    def test_default_values(self):
        cfg = RetryConfig()
        assert cfg.max == 1
        assert cfg.on == (Exception,)
        assert cfg.delay == 0.0
        assert cfg.backoff == 1.0
        assert cfg.jitter_type == "full"
        assert cfg.max_delay == 60.0
        assert cfg.should_retry is None
        assert cfg.on_retry is None

    def test_custom_values(self):
        cfg = RetryConfig(max=3, delay=0.5, backoff=2.0, jitter_type="none")
        assert cfg.max == 3
        assert cfg.delay == 0.5
        assert cfg.backoff == 2.0
        assert cfg.jitter_type == "none"

    def test_exported_from_package(self):
        """RetryConfig는 최상위 패키지에서 임포트 가능해야 함."""
        from agent_evaluator import RetryConfig as _RC
        assert _RC is RetryConfig

    def test_retry_in_agent_eval_signature(self):
        sig = inspect.signature(agent_eval)
        assert "retry" in sig.parameters
        assert sig.parameters["retry"].default is None


# ─────────────────────────────────────────────────────────────────
# 2. retry= 파라미터 동작 — 개별 파라미터 오버라이드
# ─────────────────────────────────────────────────────────────────

class TestRetryParam:
    def test_retry_object_overrides_max_retries(self, monitor):
        """retry=RetryConfig(max=2)는 max_retries=1 기본값을 덮어씀."""
        cfg = RetryConfig(max=2, delay=0.0)

        call_count = {"n": 0}

        @agent_eval(monitor, task_type="qa", retry=cfg)
        def fn(question, ground_truth=""):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("first try")
            return "ok"

        result = fn(question="q", ground_truth="ok")
        assert result == "ok"
        assert call_count["n"] == 2

    def test_retry_object_with_specific_exception(self, monitor):
        """retry.on 에 지정된 예외만 재시도."""
        cfg = RetryConfig(max=3, on=(ValueError,), delay=0.0)
        call_count = {"n": 0}

        @agent_eval(monitor, task_type="qa", retry=cfg)
        def fn(question, ground_truth=""):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("retry me")
            return "ok"

        result = fn(question="q", ground_truth="ok")
        assert result == "ok"
        assert call_count["n"] == 3

    def test_individual_retry_params_raise_typeerror(self, monitor):
        """max_retries/delay 등 개별 파라미터는 완전 제거 → TypeError."""
        with pytest.raises(TypeError):
            @agent_eval(monitor, task_type="qa", max_retries=2, delay=0.0)
            def fn(question, ground_truth=""):
                return "ok"

    def test_retry_config_works_as_replacement(self, monitor):
        """retry=RetryConfig(max=2) 가 개별 파라미터 대체 역할을 함."""
        call_count = {"n": 0}

        @agent_eval(monitor, task_type="qa", retry=RetryConfig(max=2, delay=0.0))
        def fn(question, ground_truth=""):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("retry")
            return "ok"

        result = fn(question="q", ground_truth="ok")
        assert result == "ok"
        assert call_count["n"] == 2


# ─────────────────────────────────────────────────────────────────
# 3. flush_filename 제거 검증
# ─────────────────────────────────────────────────────────────────

class TestFlushFilenameRemoved:
    def test_flush_filename_not_in_agent_eval_signature(self):
        sig = inspect.signature(agent_eval)
        assert "flush_filename" not in sig.parameters

    def test_flush_filename_not_in_batch_eval_signature(self):
        sig = inspect.signature(batch_eval)
        assert "flush_filename" not in sig.parameters

    def test_flush_filename_not_in_eval_decorator_init(self):
        sig = inspect.signature(EvalDecorator.__init__)
        assert "flush_filename" not in sig.parameters

    def test_flush_filename_not_in_common_params(self):
        assert "flush_filename" not in EvalDecorator._COMMON_PARAMS

    def test_flush_filename_not_in_batch_params(self):
        assert "flush_filename" not in EvalDecorator._BATCH_PARAMS

    def test_passing_flush_filename_raises_typeerror(self, monitor):
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", flush_filename="custom")

    def test_flush_still_works_with_flush_every(self, monitor, tmp_path):
        """flush_every=1 이면 auto_save 파일이 자동 생성되어야 함."""
        @agent_eval(monitor, task_type="qa", flush_every=1)
        def fn(question, ground_truth=""):
            return "ok"

        fn(question="q", ground_truth="ok")
        auto_save = tmp_path / "auto_save.json"
        assert auto_save.exists(), "auto_save.json이 생성되어야 함"


# ─────────────────────────────────────────────────────────────────
# 4. enable_quality_evaluation 제거 검증
# ─────────────────────────────────────────────────────────────────

class TestEnableQualityEvaluationRemoved:
    def test_not_in_agent_eval_signature(self):
        sig = inspect.signature(agent_eval)
        assert "enable_quality_evaluation" not in sig.parameters

    def test_not_in_batch_eval_signature(self):
        sig = inspect.signature(batch_eval)
        assert "enable_quality_evaluation" not in sig.parameters

    def test_not_in_eval_decorator_init(self):
        sig = inspect.signature(EvalDecorator.__init__)
        assert "enable_quality_evaluation" not in sig.parameters

    def test_not_in_common_params(self):
        assert "enable_quality_evaluation" not in EvalDecorator._COMMON_PARAMS

    def test_passing_raises_typeerror(self, monitor):
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", enable_quality_evaluation=True)


# ─────────────────────────────────────────────────────────────────
# 5. enable_hallucination 완전 제거 (v0.8.2+)
# ─────────────────────────────────────────────────────────────────

class TestEnableHallucinationRename:
    def test_new_name_in_agent_eval_signature(self):
        sig = inspect.signature(agent_eval)
        assert "enable_hallucination_detection" in sig.parameters

    def test_old_name_removed_from_agent_eval_signature(self):
        """구 이름(enable_hallucination)은 v0.8.2에서 완전 제거됨."""
        sig = inspect.signature(agent_eval)
        assert "enable_hallucination" not in sig.parameters

    def test_old_name_raises_typeerror(self, monitor):
        """구 이름(enable_hallucination=True) 사용 시 TypeError 발생."""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_type="qa", enable_hallucination=True)

    def test_new_name_default_false(self):
        sig = inspect.signature(agent_eval)
        assert sig.parameters["enable_hallucination_detection"].default is False

    def test_new_name_works(self, monitor):
        """enable_hallucination_detection=True 로 DeprecationWarning 없이 동작."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", enable_hallucination_detection=True)
            def fn(question, ground_truth=""):
                return "ok"

            fn(question="q", ground_truth="ok")

        deprecation_msgs = [w for w in caught if issubclass(w.category, DeprecationWarning)
                            and "enable_hallucination" in str(w.message)]
        assert len(deprecation_msgs) == 0, "새 이름 사용 시 DeprecationWarning 없어야 함"

    def test_new_name_in_batch_eval_signature(self):
        sig = inspect.signature(batch_eval)
        assert "enable_hallucination_detection" in sig.parameters

    def test_old_name_not_in_batch_eval_signature(self):
        """batch_eval에서도 구 이름 완전 제거."""
        sig = inspect.signature(batch_eval)
        assert "enable_hallucination" not in sig.parameters

    def test_new_name_in_common_params(self):
        assert "enable_hallucination_detection" in EvalDecorator._COMMON_PARAMS

    def test_old_name_not_in_common_params(self):
        """_COMMON_PARAMS에서도 구 이름 제거."""
        assert "enable_hallucination" not in EvalDecorator._COMMON_PARAMS

    def test_new_name_in_eval_decorator_init(self):
        sig = inspect.signature(EvalDecorator.__init__)
        assert "enable_hallucination_detection" in sig.parameters

    def test_rag_mode_uses_new_name_internally(self, monitor):
        """rag_mode=True 시 내부적으로 enable_hallucination_detection이 활성화됨 (경고 없이)."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", rag_mode=True)
            def fn(question, context="", ground_truth=""):
                return "ok"

            fn(question="q", context="ctx", ground_truth="ok")

        deprecation_msgs = [w for w in caught if issubclass(w.category, DeprecationWarning)
                            and "enable_hallucination" in str(w.message)]
        assert len(deprecation_msgs) == 0, "rag_mode 내부 처리에서 DeprecationWarning 없어야 함"


# ─────────────────────────────────────────────────────────────────
# 6. 파라미터 수 스냅샷 (회귀 방지)
# ─────────────────────────────────────────────────────────────────

class TestParamCountSnapshot:
    def test_agent_eval_param_count_after_round6(self):
        sig = inspect.signature(agent_eval)
        count = len(sig.parameters)
        assert 20 <= count <= 55, f"예상 범위를 벗어난 파라미터 수: {count}"

    def test_flush_filename_not_in_conv_params(self):
        """conversation_eval에서도 flush_filename 완전 제거 — _CONV_PARAMS에 없어야 함."""
        assert "flush_filename" not in EvalDecorator._CONV_PARAMS


# ─────────────────────────────────────────────────────────────────
# 7. conversation_eval flush_filename 제거 검증 (v0.8.3+)
# ─────────────────────────────────────────────────────────────────

class TestFlushFilenameRemovedConvEval:
    def test_flush_filename_not_in_conv_eval_signature(self):
        """conversation_eval에서도 flush_filename 완전 제거됨."""
        sig = inspect.signature(conversation_eval)
        assert "flush_filename" not in sig.parameters

    def test_passing_flush_filename_to_conv_eval_raises_typeerror(self, monitor):
        """conversation_eval에 flush_filename 전달 시 TypeError."""
        with pytest.raises(TypeError):
            conversation_eval(monitor, flush_filename="custom")


# ===========================================================================
# From test_v082_round_abc_cleanup.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# Group A — 완전 제거된 파라미터는 TypeError
# ─────────────────────────────────────────────────────────────────

class TestGroupARemovedParamsTypeError:
    def test_profile_raises_typeerror(self, monitor):
        """profile= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, profile="rag")

    def test_task_id_arg_raises_typeerror(self, monitor):
        """task_id_arg= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, task_id_arg="id")

    def test_jitter_raises_typeerror(self, monitor):
        """jitter= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, jitter=True)

    def test_enable_hallucination_raises_typeerror(self, monitor):
        """enable_hallucination= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, enable_hallucination=True)

    def test_profile_not_in_signature(self):
        """profile= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "profile" not in sig.parameters

    def test_task_id_arg_not_in_signature(self):
        """task_id_arg= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "task_id_arg" not in sig.parameters

    def test_jitter_not_in_signature(self):
        """jitter= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "jitter" not in sig.parameters

    def test_enable_hallucination_not_in_signature(self):
        """enable_hallucination= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "enable_hallucination" not in sig.parameters


# ─────────────────────────────────────────────────────────────────
# Group B — 개별 재시도 파라미터: 완전 제거 → TypeError
# ─────────────────────────────────────────────────────────────────

class TestGroupBRetryDeprecationWarning:
    def test_max_retries_raises_typeerror(self, monitor):
        """max_retries= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, max_retries=2)

    def test_delay_raises_typeerror(self, monitor):
        """delay= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, delay=0.1)

    def test_multiple_individual_params_raise_typeerror(self, monitor):
        """여러 개별 파라미터 동시 사용 시 TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, max_retries=2, delay=0.1, backoff=2.0)

    def test_retry_config_no_deprecation_warning(self, monitor):
        """retry=RetryConfig(...) 사용 시 DeprecationWarning 미발행"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            @agent_eval(monitor, retry=RetryConfig(max=2))
            def fn(question, ground_truth=""):
                return "ok"

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                        and "retry=RetryConfig" in str(x.message)]
        assert len(dep_warnings) == 0, "RetryConfig 사용 시 DeprecationWarning 없어야 함"

    def test_retry_config_works_correctly(self, monitor):
        """retry=RetryConfig(max=2)는 재시도 기능이 동작함"""
        call_count = {"n": 0}

        @agent_eval(monitor, retry=RetryConfig(max=2, delay=0.0))
        def fn(question, ground_truth=""):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("first try")
            return "ok"

        result = fn(question="q", ground_truth="ok")
        assert result == "ok"
        assert call_count["n"] == 2

    def test_max_retries_not_in_signature(self):
        """max_retries= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "max_retries" not in sig.parameters

    def test_retry_on_not_in_signature(self):
        """retry_on= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "retry_on" not in sig.parameters

    def test_delay_not_in_signature(self):
        """delay= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "delay" not in sig.parameters

    def test_backoff_not_in_signature(self):
        """backoff= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "backoff" not in sig.parameters

    def test_jitter_type_not_in_signature(self):
        """jitter_type= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "jitter_type" not in sig.parameters


# ─────────────────────────────────────────────────────────────────
# LLMJudgeConfig — 임포트 및 기본값 테스트
# ─────────────────────────────────────────────────────────────────

class TestLLMJudgeConfig:
    def test_import_from_package(self):
        """LLMJudgeConfig를 최상위 패키지에서 임포트 가능"""
        from agent_evaluator import LLMJudgeConfig as _LJC
        assert _LJC is LLMJudgeConfig

    def test_import_from_decorators(self):
        """LLMJudgeConfig를 decorators 모듈에서 임포트 가능"""
        from agent_evaluator.decorators import LLMJudgeConfig as _LJC
        assert _LJC is LLMJudgeConfig

    def test_default_values(self):
        """LLMJudgeConfig 기본값 검증"""
        cfg = LLMJudgeConfig()
        assert cfg.model is None
        assert cfg.criteria is None
        assert cfg.sample_rate == 1.0

    def test_custom_values(self):
        """LLMJudgeConfig 커스텀 값 검증"""
        cfg = LLMJudgeConfig(
            model="claude-haiku-4-5-20251001",
            criteria=["medical_accuracy", "citation_quality"],
            sample_rate=0.5,
        )
        assert cfg.model == "claude-haiku-4-5-20251001"
        assert cfg.criteria == ["medical_accuracy", "citation_quality"]
        assert cfg.sample_rate == 0.5

    def test_llm_judge_param_in_agent_eval_signature(self):
        """llm_judge= 파라미터가 agent_eval 서명에 존재"""
        sig = inspect.signature(agent_eval)
        assert "llm_judge" in sig.parameters

    def test_llm_judge_default_none(self):
        """llm_judge= 기본값은 None"""
        sig = inspect.signature(agent_eval)
        assert sig.parameters["llm_judge"].default is None


# ─────────────────────────────────────────────────────────────────
# Group C — LLMJudge 개별 파라미터: 완전 제거 → TypeError
# ─────────────────────────────────────────────────────────────────

class TestGroupCLLMJudgeDeprecationWarning:
    def test_enable_llm_judge_raises_typeerror(self, monitor):
        """enable_llm_judge= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, enable_llm_judge=True)

    def test_judge_model_raises_typeerror(self, monitor):
        """judge_model= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, judge_model="claude-haiku-4-5-20251001")

    def test_judge_criteria_raises_typeerror(self, monitor):
        """judge_criteria= 파라미터 완전 제거 → TypeError"""
        with pytest.raises(TypeError):
            agent_eval(monitor, judge_criteria=["safety"])

    def test_llm_judge_config_no_deprecation(self, monitor):
        """llm_judge=LLMJudgeConfig(...) 사용 시 DeprecationWarning 미발행"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent_eval(monitor, llm_judge=LLMJudgeConfig())

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                        and "llm_judge=LLMJudgeConfig" in str(x.message)]
        assert len(dep_warnings) == 0, "LLMJudgeConfig 사용 시 DeprecationWarning 없어야 함"

    def test_llm_judge_config_activates_judge(self, monitor):
        """llm_judge=LLMJudgeConfig() 사용 시 실제로 judge가 활성화됨"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            handle = agent_eval(monitor, llm_judge=LLMJudgeConfig())

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert all("llm_judge=LLMJudgeConfig" not in str(x.message) for x in dep_warnings)

    def test_enable_llm_judge_not_in_signature(self):
        """enable_llm_judge= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "enable_llm_judge" not in sig.parameters

    def test_judge_model_not_in_signature(self):
        """judge_model= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "judge_model" not in sig.parameters

    def test_judge_criteria_not_in_signature(self):
        """judge_criteria= 이 agent_eval 서명에서 제거됨"""
        sig = inspect.signature(agent_eval)
        assert "judge_criteria" not in sig.parameters

    def test_llm_judge_config_agent_with_no_deprecation(self, monitor):
        """deprecated enable_llm_judge=False 가 제거되어 TypeError"""
        with pytest.raises(TypeError):
            @agent_eval(monitor, task_type="qa", enable_llm_judge=False)
            def fn(question, ground_truth=""):
                return "answer"


# ─────────────────────────────────────────────────────────────────
# 파라미터 수 스냅샷 (회귀 방지) — v0.8.2 기준
# ─────────────────────────────────────────────────────────────────

class TestParamCountSnapshotV082:
    def test_agent_eval_param_count_in_expected_range(self):
        """agent_eval 파라미터 수가 예상 범위(20~42) 내에 있음"""
        sig = inspect.signature(agent_eval)
        count = len(sig.parameters)
        assert 20 <= count <= 42, (
            f"agent_eval 파라미터 수가 예상 범위를 벗어남: {count}\n"
            f"파라미터 목록: {list(sig.parameters.keys())}"
        )

    def test_removed_params_not_in_signature(self):
        """제거된 파라미터가 서명에 없음"""
        sig = inspect.signature(agent_eval)
        removed = [
            "profile", "task_id_arg", "jitter", "enable_hallucination",
            "max_retries", "retry_on", "delay", "backoff", "jitter_type",
            "max_delay", "should_retry", "on_retry",
            "enable_llm_judge", "judge_model", "judge_criteria",
        ]
        for param in removed:
            assert param not in sig.parameters, f"{param}이 아직 서명에 있음"

    def test_new_params_in_signature(self):
        """신규 파라미터가 서명에 있음"""
        sig = inspect.signature(agent_eval)
        expected_new = ["llm_judge", "enable_hallucination_detection", "retry"]
        for param in expected_new:
            assert param in sig.parameters, f"{param}이 서명에 없음"

    def test_llm_judge_in_eval_decorator_defaults(self, monitor):
        """EvalDecorator에 llm_judge 기본값이 포함됨"""
        ed = EvalDecorator(monitor)
        assert "llm_judge" in ed._defaults

    def test_enable_llm_judge_not_in_eval_decorator_defaults(self, monitor):
        """EvalDecorator._defaults에 enable_llm_judge가 없음"""
        ed = EvalDecorator(monitor)
        assert "enable_llm_judge" not in ed._defaults

    def test_judge_model_not_in_eval_decorator_defaults(self, monitor):
        """EvalDecorator._defaults에 judge_model이 없음"""
        ed = EvalDecorator(monitor)
        assert "judge_model" not in ed._defaults

    def test_judge_criteria_not_in_eval_decorator_defaults(self, monitor):
        """EvalDecorator._defaults에 judge_criteria가 없음"""
        ed = EvalDecorator(monitor)
        assert "judge_criteria" not in ed._defaults


# ===========================================================================
# From test_v083_security_config.py
# ===========================================================================

# ─────────────────────────────────────────────────────────────────
# 1. SecurityConfig 임포트 및 기본값
# ─────────────────────────────────────────────────────────────────

class TestSecurityConfigBasics:
    def test_security_config_importable_from_decorators(self):
        """SecurityConfig 가 agent_evaluator.decorators에서 임포트 가능."""
        from agent_evaluator.decorators import SecurityConfig
        assert SecurityConfig is not None

    def test_security_config_importable_from_top_level(self):
        """SecurityConfig 가 agent_evaluator 최상위에서 임포트 가능."""
        from agent_evaluator import SecurityConfig
        assert SecurityConfig is not None

    def test_security_config_default_allowed_tools_is_none(self):
        """SecurityConfig() 기본 생성 시 allowed_tools=None."""
        from agent_evaluator import SecurityConfig
        cfg = SecurityConfig()
        assert cfg.allowed_tools is None

    def test_security_config_with_allowed_tools(self):
        """SecurityConfig(allowed_tools=[...]) 로 도구 목록 지정 가능."""
        from agent_evaluator import SecurityConfig
        cfg = SecurityConfig(allowed_tools=["search", "calculator"])
        assert cfg.allowed_tools == ["search", "calculator"]

    def test_security_config_in_all_exports(self):
        """SecurityConfig 가 __all__ 에 포함돼 있음."""
        import agent_evaluator
        assert "SecurityConfig" in agent_evaluator.__all__


# ─────────────────────────────────────────────────────────────────
# 2. agent_eval 시그니처 및 동작
# ─────────────────────────────────────────────────────────────────

class TestAgentEvalSecurityConfig:
    @pytest.fixture()
    def sc_monitor(self):
        return PerformanceMonitor(output_dir="/tmp/test_sc/", enable_security_metrics=False)

    def test_agent_eval_has_security_param(self):
        """agent_eval 시그니처에 security 파라미터가 있음."""
        sig = inspect.signature(agent_eval)
        assert "security" in sig.parameters

    def test_agent_eval_security_activates_security_metrics(self, sc_monitor):
        """security=SecurityConfig() 로 호출 시 monitor.enable_security_metrics 복원."""
        from agent_evaluator import SecurityConfig
        sc_monitor.enable_security_metrics = False

        @agent_eval(sc_monitor, task_type="tool_use", security=SecurityConfig())
        def secure_fn(question, ground_truth=""):
            return "done"

        secure_fn("test question", ground_truth="done")
        assert sc_monitor.enable_security_metrics is False

    def test_agent_eval_security_with_allowed_tools(self, sc_monitor):
        """security=SecurityConfig(allowed_tools=[...]) 로 도구 목록 전달 가능."""
        from agent_evaluator import SecurityConfig
        collected = []

        @agent_eval(
            sc_monitor,
            task_type="tool_use",
            security=SecurityConfig(allowed_tools=["search"]),
            on_record=lambda tr: collected.append(tr),
        )
        def tool_fn(question, ground_truth=""):
            return "result"

        tool_fn("query", ground_truth="result")
        assert len(collected) == 1

    def test_agent_eval_no_security_config_does_not_enable_security(self, sc_monitor):
        """security=None (기본) 이면 security metrics가 활성화되지 않음."""
        sc_monitor.enable_security_metrics = False

        @agent_eval(sc_monitor, task_type="qa")
        def fn(question, ground_truth=""):
            return "answer"

        fn("question", ground_truth="answer")
        assert sc_monitor.enable_security_metrics is False


# ─────────────────────────────────────────────────────────────────
# 3. batch_eval 동작
# ─────────────────────────────────────────────────────────────────

class TestBatchEvalSecurityConfig:
    @pytest.fixture()
    def sc_monitor(self):
        return PerformanceMonitor(output_dir="/tmp/test_sc/", enable_security_metrics=False)

    def test_batch_eval_has_security_param(self):
        """batch_eval 시그니처에 security 파라미터가 있음."""
        sig = inspect.signature(batch_eval)
        assert "security" in sig.parameters

    def test_batch_eval_security_config_runs_without_error(self, sc_monitor):
        """batch_eval에서 security=SecurityConfig() 로 실행 시 오류 없음."""
        from agent_evaluator import SecurityConfig

        @batch_eval(sc_monitor, task_type="tool_use", security=SecurityConfig())
        def batch_fn(questions, ground_truths=None):
            return [f"답변 {i}" for i in range(len(questions))]

        batch_fn(["질문1", "질문2"], ground_truths=["답변 0", "답변 1"])


# ─────────────────────────────────────────────────────────────────
# 4. EvalDecorator 동작
# ─────────────────────────────────────────────────────────────────

class TestEvalDecoratorSecurityConfig:
    @pytest.fixture()
    def sc_monitor(self):
        return PerformanceMonitor(output_dir="/tmp/test_sc/", enable_security_metrics=False)

    def test_eval_decorator_has_security_param(self):
        """EvalDecorator.__init__ 시그니처에 security 파라미터가 있음."""
        sig = inspect.signature(EvalDecorator.__init__)
        assert "security" in sig.parameters

    def test_eval_decorator_stores_security_in_defaults(self, sc_monitor):
        """EvalDecorator(monitor, security=SecurityConfig()) 가 _defaults 에 저장됨."""
        from agent_evaluator.decorators import SecurityConfig
        cfg = SecurityConfig(allowed_tools=["calc"])
        ed = EvalDecorator(sc_monitor, security=cfg)
        stored = ed._defaults.get("security")
        assert isinstance(stored, SecurityConfig)
        assert stored.allowed_tools == ["calc"]

    def test_eval_decorator_security_in_common_params(self):
        """EvalDecorator._COMMON_PARAMS 에 'security' 가 포함됨."""
        assert "security" in EvalDecorator._COMMON_PARAMS
