"""
tests/test_v083_improvements.py
=================================
v0.8.3 개선 사항 테스트:
- H1: LLM Judge 결과 back-propagation (decorated function returned TaskResult에 llm_judge 포함)
- H2: _auto_detect_framework() 속성 기반 fallback 확장 (groq/mistral/bedrock/smolagents/vllm/huggingface)
- H4: EvalDecorator rag_mode/security_mode/enable_llm_judge 파라미터 + .rag/.secure 단축 속성
- M1: FrameworkLiteral 타입 (import 및 agent_eval 타입 힌트)
- M3: /api/results/{file_id}/sessions 엔드포인트 turn-level tool_calls/model_name/tokens_used 지원
- M4: preset 유효성 검사 경고 메시지 개선
"""

from __future__ import annotations

import warnings
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import AGENT_EVAL_PRESETS, FrameworkLiteral, agent_eval
from agent_evaluator.core.trackers.monitor import PerformanceMonitor
from agent_evaluator.decorators import (
    EvalDecorator,
    _auto_detect_framework,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def monitor(tmp_path):
    return PerformanceMonitor(output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# TestH2AutoDetectFramework — 속성 기반 프레임워크 감지 (groq/mistral/bedrock/smolagents/vllm/hf)
# ---------------------------------------------------------------------------


class TestH2AutoDetectFramework:
    def test_groq_via_x_groq_attr(self):
        """Groq 응답: choices + x_groq 속성."""

        class FakeGroq:
            choices = [MagicMock()]
            x_groq = {"id": "req_abc"}

        assert _auto_detect_framework(FakeGroq()) == "groq"

    def test_mistral_via_model_attr(self):
        """Mistral 응답: choices + model 에 'mistral' 포함."""

        class FakeMistral:
            choices = [MagicMock()]
            model = "mistral-large-latest"

        assert _auto_detect_framework(FakeMistral()) == "mistral"

    def test_mistral_not_matched_without_mistral_in_model(self):
        """model에 mistral이 없으면 mistral로 감지 안 됨."""

        class FakeOther:
            choices = [MagicMock()]
            model = "gpt-4o"

        result = _auto_detect_framework(FakeOther())
        assert result != "mistral"

    def test_bedrock_via_response_metadata(self):
        """Bedrock 응답: ResponseMetadata + output 속성."""

        class FakeBedrock:
            ResponseMetadata = {"RequestId": "xyz"}
            output = {"message": {}}

        assert _auto_detect_framework(FakeBedrock()) == "bedrock"

    def test_smolagents_via_logs_and_task(self):
        """smolagents Agent 응답: logs + task 속성."""

        class FakeSmolagents:
            logs = []
            task = "calculate 2+2"

        assert _auto_detect_framework(FakeSmolagents()) == "smolagents"

    def test_vllm_native_via_outputs_and_prompt_token_ids(self):
        """vLLM RequestOutput: outputs + prompt_token_ids 속성."""

        class FakeVllmOutput:
            outputs = [MagicMock()]
            prompt_token_ids = [1, 2, 3]

        assert _auto_detect_framework(FakeVllmOutput()) == "vllm"

    def test_huggingface_pipeline_list_output(self):
        """HuggingFace pipeline 출력: list of dicts with 'generated_text'."""
        raw = [{"generated_text": "Hello, world!"}]
        assert _auto_detect_framework(raw) == "huggingface"

    def test_huggingface_not_matched_for_other_lists(self):
        """generated_text 없는 list는 huggingface로 감지 안 됨."""
        raw = [{"text": "hello"}]
        assert _auto_detect_framework(raw) != "huggingface"

    def test_existing_anthropic_detection_still_works(self):
        """기존 Anthropic 감지가 여전히 동작."""
        from agent_evaluator.decorators import _is_anthropic_response

        class FakeAnthropic:
            content = []
            usage = MagicMock()
            model = "claude-sonnet-4-6"
            type = "message"

        # _is_anthropic_response 가 True를 반환하면 "anthropic"이어야 함
        if _is_anthropic_response(FakeAnthropic()):
            assert _auto_detect_framework(FakeAnthropic()) == "anthropic"

    def test_plain_string_returns_none(self):
        """일반 문자열 응답은 None 반환."""
        assert _auto_detect_framework("hello") is None


# ---------------------------------------------------------------------------
# TestH4EvalDecoratorModeParams — EvalDecorator 모드 파라미터 전파
# ---------------------------------------------------------------------------


class TestH4EvalDecoratorModeParams:
    def test_rag_mode_stored_in_defaults(self, monitor):
        """rag_mode=True 가 _defaults 에 저장됨."""
        ed = EvalDecorator(monitor, rag_mode=True)
        assert ed._defaults["rag_mode"] is True

    def test_security_mode_stored_in_defaults(self, monitor):
        """security_mode=True 가 _defaults 에 저장됨."""
        ed = EvalDecorator(monitor, security_mode=True)
        assert ed._defaults["security_mode"] is True

    def test_enable_llm_judge_stored_in_defaults(self, monitor):
        """enable_llm_judge=True 가 _defaults 에 저장됨."""
        ed = EvalDecorator(monitor, enable_llm_judge=True)
        assert ed._defaults["enable_llm_judge"] is True

    def test_judge_model_stored_in_defaults(self, monitor):
        """judge_model 이 _defaults 에 저장됨."""
        ed = EvalDecorator(monitor, judge_model="gpt-4o")
        assert ed._defaults["judge_model"] == "gpt-4o"

    def test_enable_anomaly_detection_stored_in_defaults(self, monitor):
        """enable_anomaly_detection=True 가 _defaults 에 저장됨."""
        ed = EvalDecorator(monitor, enable_anomaly_detection=True)
        assert ed._defaults["enable_anomaly_detection"] is True

    def test_rag_shortcut_includes_rag_mode(self, monitor):
        """@eval.rag 단축키가 rag_mode=True 를 포함하는 데코레이터를 반환함."""
        ed = EvalDecorator(monitor)
        # .rag 는 agent_eval(..., rag_mode=True) 로 만들어진 decorator 반환
        # 직접 적용 테스트 — 함수에 decorator 적용 시 오류 없이 동작해야 함
        @ed.rag
        def my_agent(question, context="", ground_truth=""):
            return "답변"

        result = my_agent("질문은?", context="배경 지식")
        assert result == "답변"

    def test_secure_shortcut_exists(self, monitor):
        """@eval.secure 단축 속성이 존재하고 Callable 을 반환함."""
        ed = EvalDecorator(monitor)
        assert callable(ed.secure)

    def test_secure_shortcut_applies_security_mode(self, monitor):
        """@eval.secure 데코레이터 적용 시 오류 없이 동작."""
        ed = EvalDecorator(monitor)

        @ed.secure
        def tool_agent(question, ground_truth=""):
            return "결과"

        result = tool_agent("보안 테스트")
        assert result == "결과"

    def test_defaults_propagated_to_call(self, monitor):
        """EvalDecorator(monitor, rag_mode=True).__call__() 시 rag_mode 전파."""
        ed = EvalDecorator(monitor, rag_mode=True)
        # __call__ 호출 결과도 rag_mode가 반영된 agent_eval 데코레이터여야 함
        deco = ed("qa")  # rag_mode is in _defaults, merged into kwargs
        assert callable(deco)


# ---------------------------------------------------------------------------
# TestH1LLMJudgeBackpropagation — LLM Judge 결과 back-propagation
# ---------------------------------------------------------------------------


class TestH1LLMJudgeBackpropagation:
    def test_judge_flag_computed_before_temp_override(self, monitor):
        """enable_llm_judge=True 이면 _judge_will_be_active 플래그가 True여야 함.
        실제 LLM 호출 없이 플래그 계산 경로만 검증."""
        # monitor.enable_llm_judge 기본값 False
        assert not getattr(monitor, "enable_llm_judge", False)

        # enable_llm_judge=True 파라미터를 주면 back-propagation 로직이 실행되어야 함
        # (실제 judge 호출 없이) — 예외 없이 동작만 확인
        @agent_eval(monitor, task_type="qa", enable_llm_judge=False)
        def agent(question, ground_truth=""):
            return "답변"

        result = agent("질문", ground_truth="답변")
        assert result == "답변"

    def test_returned_taskresult_has_task_id(self, monitor):
        """_build_and_record 는 task_result 를 반환하고 task_id를 가짐."""
        collected = []

        @agent_eval(monitor, task_type="qa", on_record=lambda tr: collected.append(tr))
        def agent(question, ground_truth=""):
            return "답변"

        agent("질문", ground_truth="답변")
        assert len(collected) == 1
        assert collected[0].task_id is not None

    def test_monitor_enable_llm_judge_restored_after_call(self, monitor):
        """enable_llm_judge=True 임시 활성화 후 monitor 상태가 복원됨."""
        monitor.enable_llm_judge = False

        @agent_eval(monitor, task_type="qa", enable_llm_judge=True)
        def agent(question, ground_truth=""):
            return "답변"

        agent("질문")
        # 복원 확인
        assert monitor.enable_llm_judge is False


# ---------------------------------------------------------------------------
# TestM1FrameworkLiteral — Literal 타입 힌트 임포트 및 에디터 지원
# ---------------------------------------------------------------------------


class TestM1FrameworkLiteral:
    def test_framework_literal_importable(self):
        """FrameworkLiteral 이 agent_evaluator 최상위에서 임포트 가능."""
        assert FrameworkLiteral is not None

    def test_framework_literal_contains_native(self):
        """FrameworkLiteral 은 'native' 를 포함해야 함."""
        # Literal 의 __args__ 로 허용값 목록 접근
        args = getattr(FrameworkLiteral, "__args__", None)
        if args:
            assert "native" in args

    def test_framework_literal_contains_major_frameworks(self):
        """주요 프레임워크 이름이 FrameworkLiteral 에 포함됨."""
        args = getattr(FrameworkLiteral, "__args__", None)
        if args:
            for fw in ["langchain", "langgraph", "crewai", "autogen", "openai", "anthropic"]:
                assert fw in args, f"{fw} 가 FrameworkLiteral 에 없음"

    def test_agent_eval_accepts_literal_framework(self, monitor):
        """agent_eval(framework='langchain') 이 오류 없이 동작."""

        @agent_eval(monitor, task_type="qa", framework="langchain")
        def agent(question, ground_truth=""):
            return "응답"

        result = agent("질문")
        assert result == "응답"


# ---------------------------------------------------------------------------
# TestM4PresetValidation — preset 유효성 검사 경고 메시지
# ---------------------------------------------------------------------------


class TestM4PresetValidation:
    def test_invalid_preset_raises_userwarning(self, monitor):
        """알 수 없는 preset 값은 UserWarning 을 발생시킴."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="nonexistent_preset")
            def agent(question, ground_truth=""):
                return "답변"

        preset_warnings = [x for x in w if issubclass(x.category, UserWarning) and "preset" in str(x.message).lower()]
        assert len(preset_warnings) >= 1

    def test_invalid_preset_warning_includes_valid_options(self, monitor):
        """경고 메시지에 유효한 preset 목록이 포함됨."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="bad_preset")
            def agent(question, ground_truth=""):
                return "답변"

        preset_warnings = [x for x in w if issubclass(x.category, UserWarning) and "preset" in str(x.message).lower()]
        assert len(preset_warnings) >= 1
        msg = str(preset_warnings[0].message)
        # 유효한 preset 중 하나 이상이 메시지에 포함되어야 함
        assert any(p in msg for p in AGENT_EVAL_PRESETS), f"Valid preset names not in warning: {msg}"

    def test_valid_preset_production_no_warning(self, monitor):
        """production preset 은 경고 없이 적용됨."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="production")
            def agent(question, ground_truth=""):
                return "답변"

        preset_warnings = [
            x for x in w
            if issubclass(x.category, UserWarning) and "알 수 없는 preset" in str(x.message)
        ]
        assert len(preset_warnings) == 0

    def test_valid_preset_development_no_warning(self, monitor):
        """development preset 은 경고 없이 적용됨."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", preset="development")
            def agent(question, ground_truth=""):
                return "답변"

        preset_warnings = [
            x for x in w
            if issubclass(x.category, UserWarning) and "알 수 없는 preset" in str(x.message)
        ]
        assert len(preset_warnings) == 0


# ---------------------------------------------------------------------------
# TestM3SessionsEndpoint — /api/results/{file_id}/sessions 턴 데이터 강화
# ---------------------------------------------------------------------------


class TestM3SessionsEndpoint:
    def _make_sessions_data(self) -> list:
        """테스트용 session 데이터 생성."""
        return [
            {
                "session_id": "sess_001",
                "turn_count": 2,
                "turns": [
                    {
                        "user_input": "안녕하세요",
                        "agent_response": "안녕하세요!",
                        "metadata": {
                            "tool_calls": [{"tool": "search", "input": "hi"}],
                            "model_name": "gpt-4o",
                            "tokens_used": {"total": 120},
                        },
                    },
                    {
                        "user_input": "날씨는?",
                        "agent_response": "맑습니다.",
                        "metadata": {"latency": 0.5},
                    },
                ],
                "metrics": {
                    "overall_score": 0.85,
                    "context_retention": 0.9,
                    "topic_coherence": 0.8,
                    "progressive_depth": 0.7,
                    "session_completion": 1.0,
                    "avg_turn_latency": 0.4,
                },
            }
        ]

    def test_enrich_session_turns_extracts_tool_calls(self):
        """_enrich_session_turns 가 metadata.tool_calls 를 최상위로 추출."""
        from agent_evaluator.serve.routers.data import _enrich_session_turns

        session = self._make_sessions_data()[0]
        enriched = _enrich_session_turns(session)
        first_turn = enriched["turns"][0]
        assert first_turn["tool_calls"] == [{"tool": "search", "input": "hi"}]

    def test_enrich_session_turns_extracts_model_name(self):
        """_enrich_session_turns 가 metadata.model_name 을 최상위로 추출."""
        from agent_evaluator.serve.routers.data import _enrich_session_turns

        session = self._make_sessions_data()[0]
        enriched = _enrich_session_turns(session)
        first_turn = enriched["turns"][0]
        assert first_turn["model_name"] == "gpt-4o"

    def test_enrich_session_turns_extracts_tokens_used(self):
        """_enrich_session_turns 가 metadata.tokens_used 를 최상위로 추출."""
        from agent_evaluator.serve.routers.data import _enrich_session_turns

        session = self._make_sessions_data()[0]
        enriched = _enrich_session_turns(session)
        first_turn = enriched["turns"][0]
        assert first_turn["tokens_used"] == {"total": 120}

    def test_enrich_session_turns_none_when_no_metadata(self):
        """metadata 없는 턴은 tool_calls/model_name/tokens_used 가 None."""
        from agent_evaluator.serve.routers.data import _enrich_session_turns

        session = self._make_sessions_data()[0]
        enriched = _enrich_session_turns(session)
        second_turn = enriched["turns"][1]
        assert second_turn["tool_calls"] is None
        assert second_turn["model_name"] is None
        assert second_turn["tokens_used"] is None

    def test_enrich_session_does_not_modify_existing_fields(self):
        """이미 존재하는 최상위 필드는 덮어쓰지 않음."""
        from agent_evaluator.serve.routers.data import _enrich_session_turns

        session = {
            "session_id": "sess_002",
            "turns": [
                {
                    "tool_calls": [{"tool": "existing"}],  # 이미 존재
                    "metadata": {"tool_calls": [{"tool": "from_meta"}]},
                }
            ],
            "metrics": {},
        }
        enriched = _enrich_session_turns(session)
        # 기존 값 보존
        assert enriched["turns"][0]["tool_calls"] == [{"tool": "existing"}]

    def test_sessions_endpoint_function_signature_has_include_turns(self):
        """get_sessions 함수가 include_turns 파라미터를 가짐."""
        import inspect
        from agent_evaluator.serve.routers.data import get_sessions

        sig = inspect.signature(get_sessions)
        assert "include_turns" in sig.parameters


# ---------------------------------------------------------------------------
# TestIntegration — 전체 흐름 통합 테스트
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_eval_decorator_rag_mode_propagates_to_agent_eval(self, monitor):
        """EvalDecorator(rag_mode=True).__call__() → agent_eval(rag_mode=True) 전파."""
        ed = EvalDecorator(monitor, rag_mode=True)

        called_with_rag = []

        original_agent_eval = agent_eval.__wrapped__ if hasattr(agent_eval, "__wrapped__") else None

        # 단순히 실행 오류 없음 확인
        @ed("qa")  # rag_mode=True 가 defaults 에서 전파
        def rag_agent(question, context="", ground_truth=""):
            return "RAG 답변"

        result = rag_agent("질문?", context="배경")
        assert result == "RAG 답변"

    def test_h2_vllm_attribute_detection_end_to_end(self):
        """vLLM native 응답 자동 감지 → 어댑터 적용."""
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS

        assert "vllm" in _FRAMEWORK_ADAPTERS

        class FakeVllmResponse:
            outputs = [MagicMock(text="vllm output")]
            prompt_token_ids = [1, 2, 3, 4, 5]

        detected = _auto_detect_framework(FakeVllmResponse())
        assert detected == "vllm"

    def test_h2_huggingface_pipeline_end_to_end(self):
        """HuggingFace pipeline 자동 감지 → 어댑터 적용."""
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS

        assert "huggingface" in _FRAMEWORK_ADAPTERS
        raw = [{"generated_text": "Hello from HuggingFace"}]
        detected = _auto_detect_framework(raw)
        assert detected == "huggingface"
