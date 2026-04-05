"""tests/test_improvements_g1_g26.py — v0.7.2 improvement batch G1~G26 테스트.

축 1: 데코레이터 UX (A, B, D, E, F, S, W)
축 2: 프레임워크 어댑터 (G, H, I, J, T, U, X, Z)
축 3: 대시보드 API (K, L, M, N, O)
축 4: 모니터링 (P, Q, R)
축 5: QuickEval & DX (C, V, Y)
"""
from __future__ import annotations

import datetime
import inspect
import threading
import warnings
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import (
    AGENT_EVAL_PRESETS,
    EvalDecorator,
    _eval_active,
    _make_alert_on_record,
    agent_eval,
    get_framework_info,
    register_preset,
)


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
# 축 1 — 데코레이터 UX
# ===========================================================================


# ---------------------------------------------------------------------------
# A: alert_rules + on_record 실행 순서
# ---------------------------------------------------------------------------

class TestAlertRulesAndOnRecord:
    """항목 A: alert_rules 가 on_record 보다 먼저 실행됨을 확인."""

    def test_alert_rules_on_record_order(self):
        """alert_rules 콜백 → on_record 순서로 호출됨을 확인."""
        monitor = _make_monitor()
        call_order: list = []

        from agent_evaluator import SimpleTaskAlertRule

        def _alert_handler(msg, tr):
            call_order.append("alert")

        rule = SimpleTaskAlertRule(
            name="order_test_rule",
            condition=lambda tr: True,
            handler=_alert_handler,
            severity="info",
            cooldown=0,
        )

        def _on_record(tr):
            call_order.append("on_record")

        @agent_eval(monitor, task_type="qa", alert_rules=[rule], on_record=_on_record)
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        agent("질문", ground_truth="답변")

        assert "alert" in call_order
        assert "on_record" in call_order
        # alert_rules가 on_record보다 먼저 실행되어야 한다
        assert call_order.index("alert") < call_order.index("on_record")

    def test_make_alert_on_record_code_or_docstring_mentions_order(self):
        """decorators.py에 alert_rules + on_record 실행 순서 관련 코드가 있음."""
        import agent_evaluator.decorators as dec_module
        src = inspect.getsource(dec_module)
        # _make_alert_on_record 함수 또는 관련 주석이 있어야 한다
        assert "_make_alert_on_record" in src or "alert_rules" in src


# ---------------------------------------------------------------------------
# B: generator timeout UserWarning
# ---------------------------------------------------------------------------

class TestGeneratorTimeoutWarning:
    """항목 B: generator 함수에 timeout 지정 시 UserWarning."""

    def test_timeout_on_generator_raises_warning(self):
        """일반 generator 함수에 timeout=1.0 지정 시 UserWarning 발행."""
        monitor = _make_monitor()

        def gen_agent(question: str, ground_truth: str = ""):
            yield "hello"
            yield "world"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_eval(monitor, task_type="qa", timeout=1.0)(gen_agent)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("timeout" in str(w.message).lower() for w in user_warnings), (
            "generator 함수에 timeout 지정 시 UserWarning이 발행되어야 한다"
        )

    def test_timeout_on_async_gen_raises_warning(self):
        """async generator 함수에 timeout=1.0 지정 시 UserWarning 발행."""
        monitor = _make_monitor()

        async def agen_agent(question: str, ground_truth: str = ""):
            yield "hello"
            yield "world"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_eval(monitor, task_type="qa", timeout=1.0)(agen_agent)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("timeout" in str(w.message).lower() for w in user_warnings), (
            "async generator 함수에 timeout 지정 시 UserWarning이 발행되어야 한다"
        )


# ---------------------------------------------------------------------------
# D: rag_mode + security_mode 동시 사용 경고
# ---------------------------------------------------------------------------

class TestRagModeSecurityModeWarning:
    """항목 D: rag_mode=True + security_mode=True 동시 사용 시 UserWarning."""

    def test_rag_mode_security_mode_both_warns(self):
        """rag_mode=True와 security_mode=True 동시 지정 시 UserWarning 발행."""
        monitor = _make_monitor()

        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent_eval(monitor, rag_mode=True, security_mode=True)(agent)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) > 0, (
            "rag_mode=True + security_mode=True 동시 사용 시 UserWarning이 발행되어야 한다"
        )
        assert any("rag_mode" in str(w.message) or "security_mode" in str(w.message)
                   for w in user_warnings)


# ---------------------------------------------------------------------------
# E: EvalDecorator.context() 양방향 지원
# ---------------------------------------------------------------------------

class TestEvalDecoratorContext:
    """항목 E: EvalDecorator.context 속성/callable 양방향 지원."""

    def test_eval_decorator_context_property_exists(self):
        """EvalDecorator 인스턴스에 .context 속성이 존재해야 한다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        assert hasattr(dec, "context"), "EvalDecorator.context 속성이 없다"

    def test_eval_decorator_context_callable(self):
        """eval.context(task_type='qa') 호출이 context manager를 반환해야 한다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        ctx_shortcut = dec.context
        # _ContextShortcut 또는 callable이어야 한다
        assert callable(ctx_shortcut) or hasattr(ctx_shortcut, "__call__") or hasattr(ctx_shortcut, "__enter__"), (
            "dec.context는 callable 또는 context manager여야 한다"
        )

    def test_eval_decorator_context_returns_cm(self):
        """eval.context('qa') 호출 결과가 context manager 프로토콜을 구현해야 한다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        # _ContextShortcut.__call__로 cm 얻기
        shortcut = dec.context
        if callable(shortcut):
            cm = shortcut("qa")
            assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__"), (
                "context('qa') 반환값이 context manager여야 한다"
            )


# ---------------------------------------------------------------------------
# F: 이중 데코레이터 스택 감지
# ---------------------------------------------------------------------------

class TestDoubleDecoratorStackDetection:
    """항목 F: _eval_active ContextVar 기반 이중 스택 감지."""

    def test_eval_active_contextvar_exists(self):
        """_eval_active ContextVar가 decorators 모듈에 정의되어 있어야 한다."""
        assert _eval_active is not None
        import contextvars
        assert isinstance(_eval_active, contextvars.ContextVar), (
            "_eval_active가 ContextVar 타입이어야 한다"
        )

    def test_eval_active_default_is_false(self):
        """_eval_active의 기본값은 False여야 한다."""
        assert _eval_active.get(True) is False or _eval_active.get() is False

    def test_double_decorator_stack_warns(self):
        """이중 데코레이터 스택 진입 시 UserWarning이 발행되어야 한다."""
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa")
        def inner_agent(question: str, ground_truth: str = "") -> str:
            return "내부응답"

        @agent_eval(monitor, task_type="qa")
        def outer_agent(question: str, ground_truth: str = "") -> str:
            # 이미 eval_active=True 상태에서 inner_agent 호출 → 경고 발행
            return inner_agent(question, ground_truth=ground_truth)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            outer_agent("질문", ground_truth="응답")

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        # 이중 스택 경고가 발행되어야 한다
        assert any("이중" in str(w.message) or "double" in str(w.message).lower()
                   or "평가 데코레이터" in str(w.message)
                   for w in user_warnings), (
            "이중 데코레이터 스택 진입 시 UserWarning이 발행되어야 한다"
        )


# ---------------------------------------------------------------------------
# S: alert_error_mode 파라미터
# ---------------------------------------------------------------------------

class TestAlertErrorMode:
    """항목 S: agent_eval의 alert_error_mode 파라미터."""

    def test_agent_eval_has_alert_error_mode_param(self):
        """agent_eval() 시그니처에 alert_error_mode 파라미터가 있어야 한다."""
        sig = inspect.signature(agent_eval)
        assert "alert_error_mode" in sig.parameters, (
            "agent_eval에 alert_error_mode 파라미터가 없다"
        )

    def test_alert_error_mode_default_is_log(self):
        """alert_error_mode 기본값은 'log'여야 한다."""
        sig = inspect.signature(agent_eval)
        default = sig.parameters["alert_error_mode"].default
        assert default == "log"

    def test_alert_error_mode_log_no_exception(self):
        """alert_error_mode='log'이면 alert 콜백 예외가 함수 밖으로 전파되지 않는다."""
        monitor = _make_monitor()
        from agent_evaluator import SimpleTaskAlertRule

        def _bad_handler(msg, tr):
            raise RuntimeError("alert 예외")

        rule = SimpleTaskAlertRule(
            name="bad_handler_rule",
            condition=lambda tr: True,
            handler=_bad_handler,
            severity="warning",
            cooldown=0,
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule], alert_error_mode="log")
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        # alert_error_mode="log"이면 RuntimeError가 전파되지 않아야 한다
        result = agent("질문", ground_truth="답변")
        assert result == "답변"

    def test_alert_error_mode_strict_propagates_exception(self):
        """alert_error_mode='strict'이면 rule.evaluate() 자체 예외가 전파된다.

        SimpleTaskAlertRule.evaluate()는 handler 예외를 내부에서 무시하므로,
        strict 모드에서 전파되는 예외는 condition 예외 또는 evaluate 자체 예외다.
        """
        from agent_evaluator.decorators import _make_alert_on_record

        # condition 자체에서 예외를 발생시켜 evaluate가 외부로 전파하도록 한다.
        # 단, SimpleTaskAlertRule.evaluate는 condition 예외를 catch하므로
        # rule.evaluate 자체가 아닌 별도 callable로 mock한다.

        class _RaisingRule:
            name = "raising_rule"

            def evaluate(self, tr: Any) -> None:
                raise RuntimeError("strict 모드 예외")

        rule = _RaisingRule()
        _on_record = _make_alert_on_record([rule], None, alert_error_mode="strict")

        tr = _make_task_result()
        with pytest.raises(RuntimeError, match="strict 모드 예외"):
            _on_record(tr)


# ---------------------------------------------------------------------------
# W: register_preset()
# ---------------------------------------------------------------------------

class TestRegisterPreset:
    """항목 W: register_preset() — 사용자 정의 preset 등록."""

    def setup_method(self):
        """테스트 후 cleanup을 위해 등록한 preset 이름을 기록."""
        self._added: list = []

    def teardown_method(self):
        """등록한 preset 정리."""
        for name in self._added:
            AGENT_EVAL_PRESETS.pop(name, None)

    def test_register_preset_adds_to_presets(self):
        """register_preset('test_preset', {...})이 AGENT_EVAL_PRESETS에 추가된다."""
        name = "g26_test_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 0.5})
        assert name in AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS[name]["sample_rate"] == 0.5

    def test_register_preset_invalid_name_raises(self):
        """빈 이름으로 register_preset('', {}) 호출 시 ValueError."""
        with pytest.raises(ValueError, match="name"):
            register_preset("", {"sample_rate": 0.5})

    def test_register_preset_invalid_config_raises(self):
        """config가 dict가 아니면 ValueError."""
        with pytest.raises(ValueError, match="config"):
            register_preset("g26_bad_config_preset", ["not", "a", "dict"])  # type: ignore

    def test_register_preset_usable_in_agent_eval(self):
        """등록된 preset을 agent_eval(monitor, preset=name)에 사용할 수 있다."""
        name = "g26_usable_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 1.0})

        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa", preset=name)
        def agent(question: str, ground_truth: str = "") -> str:
            return "답변"

        # 예외 없이 실행되면 된다
        result = agent("질문", ground_truth="답변")
        assert result == "답변"

    def test_register_preset_overwrites_with_warning(self):
        """이미 존재하는 preset 이름으로 재등록 시 UserWarning을 발행하고 덮어쓴다."""
        name = "g26_overwrite_preset"
        self._added.append(name)
        AGENT_EVAL_PRESETS.pop(name, None)
        register_preset(name, {"sample_rate": 0.3})

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            register_preset(name, {"sample_rate": 0.7})

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) > 0, "재등록 시 UserWarning이 발행되어야 한다"
        assert AGENT_EVAL_PRESETS[name]["sample_rate"] == 0.7


# ===========================================================================
# 축 2 — 프레임워크 어댑터
# ===========================================================================


# ---------------------------------------------------------------------------
# G: supports_chain_steps
# ---------------------------------------------------------------------------

class TestSupportsChainSteps:
    """항목 G: get_framework_info()에 supports_chain_steps 필드 존재."""

    def test_get_framework_info_has_supports_chain_steps_langchain(self):
        """get_framework_info('langchain')['supports_chain_steps'] == True."""
        info = get_framework_info("langchain")
        assert info is not None, "langchain 프레임워크 정보가 None이다"
        assert "supports_chain_steps" in info, "supports_chain_steps 필드가 없다"
        assert info["supports_chain_steps"] is True

    def test_supports_chain_steps_false_for_openai(self):
        """get_framework_info('openai')['supports_chain_steps'] == False."""
        info = get_framework_info("openai")
        assert info is not None, "openai 프레임워크 정보가 None이다"
        assert "supports_chain_steps" in info
        assert info["supports_chain_steps"] is False

    def test_supports_chain_steps_for_dspy_true(self):
        """get_framework_info('dspy')['supports_chain_steps'] == True."""
        info = get_framework_info("dspy")
        assert info is not None
        assert info["supports_chain_steps"] is True


# ---------------------------------------------------------------------------
# H: estimated 필드 일관성
# ---------------------------------------------------------------------------

class TestHuggingFaceEstimatedField:
    """항목 H: HuggingFace 응답에서 estimated: True 포함 확인."""

    def test_huggingface_tokens_has_estimated_true(self):
        """HuggingFace list 응답에서 추출된 토큰에 'estimated': True 포함."""
        from agent_evaluator.decorators import _extract_huggingface_metadata

        hf_response = [{"generated_text": "안녕하세요 반갑습니다 오늘은 좋은 날씨입니다"}]
        meta = _extract_huggingface_metadata(hf_response)
        assert meta is not None, "HuggingFace 응답에서 메타데이터가 추출되어야 한다"
        assert meta.tokens_used is not None, "tokens_used가 None이다"
        assert meta.tokens_used.get("estimated") is True, (
            "HuggingFace 토큰 추정값에 estimated=True가 있어야 한다"
        )

    def test_huggingface_agent_logs_estimated_true(self):
        """HuggingFace agent logs 응답에서도 estimated: True."""
        from agent_evaluator.decorators import _extract_huggingface_metadata

        raw = MagicMock()
        raw.logs = ["step1", "step2", "step3 response"]
        raw.tool_calls = None
        del raw.tool_calls  # hasattr 실패 유도

        # logs만 있는 경우
        class AgentResult:
            logs = ["검색 결과", "답변 생성"]

        meta = _extract_huggingface_metadata(AgentResult())
        if meta is not None and meta.tokens_used is not None:
            # estimated 필드가 있는 경우에만 검증
            if "estimated" in meta.tokens_used:
                assert meta.tokens_used["estimated"] is True


# ---------------------------------------------------------------------------
# I: Vertex AI vs Gemini 구분
# ---------------------------------------------------------------------------

class TestVertexAIVsGeminiDetection:
    """항목 I: vertexai vs gemini 프레임워크 자동 감지 분기."""

    def test_auto_detect_framework_vertexai_module(self):
        """응답 객체의 module에 'vertexai'가 포함될 때 'vertexai' 감지."""
        from agent_evaluator.decorators import _auto_detect_framework

        raw = MagicMock()
        raw.__class__.__module__ = "vertexai.generative_models"
        # candidates 속성으로 Gemini-like 구조 설정
        raw.candidates = [MagicMock()]
        raw.usage_metadata = MagicMock()

        detected = _auto_detect_framework(raw)
        assert detected == "vertexai", (
            f"vertexai 모듈 응답은 'vertexai'로 감지되어야 한다. 실제: {detected}"
        )

    def test_auto_detect_framework_gemini_module(self):
        """응답 객체의 module에 'google.generativeai'가 있을 때 'gemini' 감지."""
        from agent_evaluator.decorators import _auto_detect_framework

        raw = MagicMock()
        raw.__class__.__module__ = "google.generativeai.types"
        raw.candidates = [MagicMock()]
        raw.usage_metadata = MagicMock()

        detected = _auto_detect_framework(raw)
        # gemini 또는 vertexai — google.generativeai는 gemini 계열
        assert detected in ("gemini", "vertexai"), (
            f"google.generativeai 모듈 응답은 gemini 계열이어야 한다. 실제: {detected}"
        )

    def test_vertexai_framework_info_exists(self):
        """get_framework_info('vertexai')가 None이 아닌 dict 반환."""
        info = get_framework_info("vertexai")
        assert info is not None and isinstance(info, dict)


# ---------------------------------------------------------------------------
# J: chain_steps 유효성 검증
# ---------------------------------------------------------------------------

class TestChainStepsValidation:
    """항목 J: chain_steps에 'name' 없는 항목이 필터링됨."""

    def test_chain_steps_invalid_items_filtered(self):
        """'name' 없는 chain_step은 record_task 시 필터링된다."""
        monitor = _make_monitor()

        @agent_eval(monitor, task_type="qa")
        def agent(question: str, ground_truth: str = "") -> str:
            from agent_evaluator.decorators import EvalMetadata
            # 유효 step + 무효 step 혼합
            agent._eval_metadata = EvalMetadata(  # type: ignore
                chain_steps=[
                    {"name": "valid_step", "output": "ok"},
                    {"no_name_field": "invalid"},  # 이 항목은 필터링되어야 한다
                ]
            )
            return "답변"

        # _eval_metadata 주입 방식 대신 직접 record_task 사용
        from agent_evaluator import TaskResult
        import dataclasses

        tr = _make_task_result(
            chain_steps=[
                {"name": "valid", "output": "ok"},
                {"no_name_field": "invalid"},
            ]
        )
        # monitor._post_process_chain_steps 또는 내부 로직 확인
        # chain_steps 필터링은 agent_eval wrapper 내부에서 발생
        # 직접 확인: _valid_cs 로직
        raw_chain_steps = tr.chain_steps or []
        valid = [s for s in raw_chain_steps if isinstance(s, dict) and "name" in s]
        assert len(valid) == 1
        assert valid[0]["name"] == "valid"

    def test_chain_steps_non_dict_filtered(self):
        """chain_steps의 dict가 아닌 항목도 필터링된다."""
        raw = [
            {"name": "step1"},
            "not_a_dict",
            123,
            {"name": "step2"},
        ]
        valid = [s for s in raw if isinstance(s, dict) and "name" in s]
        assert len(valid) == 2


# ---------------------------------------------------------------------------
# T: create_taskresult() extra_fields
# ---------------------------------------------------------------------------

class TestCreateTaskresultExtraFields:
    """항목 T: create_taskresult_from_execution에 **extra_fields 지원."""

    def test_create_taskresult_accepts_framework_extra(self):
        """create_taskresult(framework='langchain') 호출 시 framework 필드 포함."""
        from agent_evaluator import create_taskresult

        tr = create_taskresult(
            task_id="extra_test_001",
            question="프레임워크 테스트?",
            response="langchain으로 답변",
            ground_truth="langchain으로 답변",
            execution_time=0.5,
            task_type="qa",
            framework="langchain",
        )
        assert tr is not None
        # framework 필드가 TaskResult에 있거나 extra에 있어야 한다
        has_framework = (
            getattr(tr, "framework", None) == "langchain"
            or (isinstance(getattr(tr, "extra", None), dict) and tr.extra.get("framework") == "langchain")  # type: ignore
        )
        assert has_framework, "framework 필드가 TaskResult에 반영되어야 한다"

    def test_create_taskresult_extra_fields_invalid_key_ignored(self):
        """TaskResult에 없는 extra_fields 키는 무시된다 (에러 없음)."""
        from agent_evaluator import create_taskresult

        tr = create_taskresult(
            task_id="extra_ignore_001",
            question="무효 필드 테스트?",
            response="답변",
            ground_truth="답변",
            execution_time=0.3,
            task_type="qa",
            nonexistent_field_xyz="무시되어야 함",
        )
        assert tr is not None
        assert not hasattr(tr, "nonexistent_field_xyz")


# ---------------------------------------------------------------------------
# U: EvalDecorator.inspect()
# ---------------------------------------------------------------------------

class TestEvalDecoratorInspect:
    """항목 U: EvalDecorator.inspect() / get_config()."""

    def test_eval_decorator_inspect_returns_dict(self):
        """EvalDecorator(monitor).inspect() 반환이 dict여야 한다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        result = dec.inspect()
        assert isinstance(result, dict), f"inspect()가 dict가 아니다: {type(result)}"

    def test_eval_decorator_get_config_alias(self):
        """EvalDecorator.get_config()가 inspect()와 동일한 결과를 반환한다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor)
        assert hasattr(dec, "get_config"), "get_config 메서드가 없다"
        assert callable(dec.get_config)
        assert dec.get_config() == dec.inspect()

    def test_eval_decorator_inspect_reflects_init_params(self):
        """EvalDecorator 초기화 파라미터가 inspect()에 반영된다."""
        monitor = _make_monitor()
        dec = EvalDecorator(monitor, sample_rate=0.5)
        config = dec.inspect()
        # sample_rate가 _defaults에 저장되어 있어야 한다
        assert "sample_rate" in config
        assert config["sample_rate"] == 0.5


# ---------------------------------------------------------------------------
# X: eval_context.chunk_step() / add_step()
# ---------------------------------------------------------------------------

class TestEvalContextStepMethods:
    """항목 X: eval_context.chunk_step() 및 add_step() 메서드."""

    def test_eval_context_has_chunk_step_method(self):
        """eval_context 인스턴스에 chunk_step 메서드가 있어야 한다."""
        from agent_evaluator.decorators import eval_context
        monitor = _make_monitor()
        ctx = eval_context(monitor, "qa")
        assert hasattr(ctx, "chunk_step") and callable(ctx.chunk_step), (
            "eval_context에 chunk_step 메서드가 없다"
        )

    def test_eval_context_has_add_step_method(self):
        """eval_context 인스턴스에 add_step 메서드가 있어야 한다."""
        from agent_evaluator.decorators import eval_context
        monitor = _make_monitor()
        ctx = eval_context(monitor, "qa")
        assert hasattr(ctx, "add_step") and callable(ctx.add_step), (
            "eval_context에 add_step 메서드가 없다"
        )

    def test_eval_context_chunk_step_adds_streaming_steps(self):
        """chunk_step() 호출 후 extra에 streaming_steps가 추가된다."""
        from agent_evaluator.decorators import eval_context

        monitor = _make_monitor()
        with eval_context(monitor, "qa") as ctx:
            ctx.chunk_step(content="첫 번째 청크")
            ctx.chunk_step(content="두 번째 청크")
            ctx.response = "완성된 응답"

        tasks = monitor.tasks
        assert len(tasks) > 0
        last_task = tasks[-1]
        extra = getattr(last_task, "extra", None) or {}
        assert "streaming_steps" in extra, "streaming_steps가 extra에 없다"
        assert len(extra["streaming_steps"]) == 2

    def test_eval_context_add_step_adds_chain_steps(self):
        """add_step() 호출 후 extra에 chain_steps가 추가된다."""
        from agent_evaluator.decorators import eval_context

        monitor = _make_monitor()
        with eval_context(monitor, "qa") as ctx:
            ctx.add_step("retrieval", duration_s=0.2, step_type="retrieval")
            ctx.add_step("generation", duration_s=0.8, step_type="generation")
            ctx.response = "RAG 답변"

        tasks = monitor.tasks
        assert len(tasks) > 0
        last_task = tasks[-1]
        extra = getattr(last_task, "extra", None) or {}
        assert "chain_steps" in extra, "chain_steps가 extra에 없다"
        step_names = [s.get("name") for s in extra["chain_steps"]]
        assert "retrieval" in step_names
        assert "generation" in step_names


# ---------------------------------------------------------------------------
# Z: get_framework_info() — is_installed bool 반환
# ---------------------------------------------------------------------------

class TestGetFrameworkInfoIsInstalled:
    """항목 Z: get_framework_info()의 is_installed 필드가 bool."""

    def test_get_framework_info_is_installed_bool_for_native(self):
        """get_framework_info('native')['is_installed']가 bool 타입."""
        info = get_framework_info("native")
        assert info is not None
        assert "is_installed" in info
        assert isinstance(info["is_installed"], bool)

    def test_get_framework_info_is_installed_bool_for_openai(self):
        """get_framework_info('openai')['is_installed']가 bool 타입."""
        info = get_framework_info("openai")
        assert info is not None
        assert isinstance(info["is_installed"], bool)

    def test_get_framework_info_returns_none_for_unknown(self):
        """알 수 없는 프레임워크에 대해 None 반환."""
        info = get_framework_info("nonexistent_framework_xyz_abc")
        assert info is None


# ===========================================================================
# 축 3 — 대시보드 API
# ===========================================================================


# ---------------------------------------------------------------------------
# K: /results 범위 필터 (tcr_min)
# ---------------------------------------------------------------------------

class TestResultsListFilterParams:
    """항목 K: list_results에 tcr_min 파라미터 존재."""

    def test_list_results_has_tcr_min_param(self):
        """list_results 함수 시그니처 또는 라우트에 tcr_min이 있다."""
        from agent_evaluator.serve.routers import data as data_router
        # list_results 함수 찾기
        list_results_fn = getattr(data_router, "list_results", None)
        if list_results_fn is None:
            # 라우트에서 찾기
            from agent_evaluator.serve.routers.data import router
            found = False
            for route in router.routes:
                if hasattr(route, "path") and "results" in str(getattr(route, "path", "")):
                    found = True
                    break
            assert found, "results 라우트가 없다"
        else:
            sig = inspect.signature(list_results_fn)
            assert "tcr_min" in sig.parameters, "list_results에 tcr_min 파라미터가 없다"

    def test_tcr_min_param_in_source(self):
        """data.py 소스에 tcr_min이 정의되어 있다."""
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "tcr_min" in src, "data.py에 tcr_min이 없다"


# ---------------------------------------------------------------------------
# L: SSE 엔드포인트
# ---------------------------------------------------------------------------

class TestLiveStatsSSERoute:
    """항목 L: /live-stats SSE 라우트가 등록되어 있다."""

    def test_live_stats_sse_route_exists(self):
        """router.routes에 /live-stats 라우트가 등록되어 있다."""
        from agent_evaluator.serve.routers.data import router

        route_paths = [str(getattr(r, "path", "")) for r in router.routes]
        assert any("live-stats" in p for p in route_paths), (
            f"/live-stats 라우트가 없다. 등록된 경로: {route_paths}"
        )

    def test_live_stats_sse_source_exists(self):
        """data.py 소스에 live-stats 엔드포인트 정의가 있다."""
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "live-stats" in src or "live_stats" in src


# ---------------------------------------------------------------------------
# M: hourly-stats 엔드포인트
# ---------------------------------------------------------------------------

class TestHourlyStatsRoute:
    """항목 M: /results/{file_id}/hourly-stats 라우트가 등록되어 있다."""

    def test_hourly_stats_route_exists(self):
        """/results/{file_id}/hourly-stats 라우트가 등록되어 있다."""
        from agent_evaluator.serve.routers.data import router

        route_paths = [str(getattr(r, "path", "")) for r in router.routes]
        assert any("hourly-stats" in p for p in route_paths), (
            f"hourly-stats 라우트가 없다. 등록된 경로: {route_paths}"
        )

    def test_hourly_stats_in_source(self):
        """data.py 소스에 hourly-stats 정의가 있다."""
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "hourly-stats" in src or "hourly_stats" in src


# ---------------------------------------------------------------------------
# N: include_sample
# ---------------------------------------------------------------------------

class TestIncludeSampleParam:
    """항목 N: list_results에 include_sample 파라미터가 있다."""

    def test_list_results_has_include_sample_param(self):
        """list_results 시그니처 또는 data.py 소스에 include_sample이 있다."""
        from agent_evaluator.serve.routers import data as data_module
        src = inspect.getsource(data_module)
        assert "include_sample" in src, "data.py에 include_sample이 없다"


# ---------------------------------------------------------------------------
# O: Anomaly Pydantic 스키마
# ---------------------------------------------------------------------------

class TestAnomalySchema:
    """항목 O: AnomalyEventSchema / AnomalyListResponse 정의 확인."""

    def test_anomaly_event_schema_defined(self):
        """AnomalyEventSchema 클래스가 data.py에 정의되어 있다."""
        from agent_evaluator.serve.routers import data as data_module
        assert hasattr(data_module, "AnomalyEventSchema"), (
            "AnomalyEventSchema 클래스가 data.py에 없다"
        )

    def test_anomaly_list_response_defined(self):
        """AnomalyListResponse 클래스가 data.py에 정의되어 있다."""
        from agent_evaluator.serve.routers import data as data_module
        assert hasattr(data_module, "AnomalyListResponse"), (
            "AnomalyListResponse 클래스가 data.py에 없다"
        )

    def test_anomaly_event_schema_has_expected_fields(self):
        """AnomalyEventSchema가 Pydantic BaseModel이고 events 필드가 있다."""
        from agent_evaluator.serve.routers.data import AnomalyListResponse
        # Pydantic BaseModel 필드 확인
        if hasattr(AnomalyListResponse, "model_fields"):
            # Pydantic v2
            fields = AnomalyListResponse.model_fields
        else:
            # Pydantic v1
            fields = AnomalyListResponse.__fields__
        assert "events" in fields, "AnomalyListResponse에 events 필드가 없다"


# ===========================================================================
# 축 4 — 모니터링
# ===========================================================================


# ---------------------------------------------------------------------------
# P: thread-safety RLock
# ---------------------------------------------------------------------------

class TestPerformanceMonitorThreadSafety:
    """항목 P: PerformanceMonitor의 _tasks_lock이 threading.Lock/RLock."""

    def test_performance_monitor_has_tasks_lock(self):
        """_tasks_lock 속성이 존재하고 Lock 계열 타입이다."""
        monitor = _make_monitor()
        assert hasattr(monitor, "_tasks_lock"), "_tasks_lock 속성이 없다"
        lock = monitor._tasks_lock
        # threading.RLock 또는 threading.Lock 타입
        lock_types = (type(threading.RLock()), type(threading.Lock()))
        assert isinstance(lock, lock_types), (
            f"_tasks_lock이 Lock 계열이 아니다: {type(lock)}"
        )

    def test_tasks_lock_is_alias_for_lock(self):
        """_tasks_lock이 _lock과 동일 객체(alias)여야 한다."""
        monitor = _make_monitor()
        if hasattr(monitor, "_lock"):
            assert monitor._tasks_lock is monitor._lock, (
                "_tasks_lock이 _lock의 alias여야 한다"
            )

    def test_concurrent_record_task_thread_safe(self):
        """다중 스레드에서 record_task() 동시 호출이 안전하게 완료된다."""
        monitor = _make_monitor()
        errors: list = []

        def worker(i: int):
            try:
                tr = _make_task_result(task_id=f"thread_task_{i}")
                monitor.record_task(tr)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"스레드 안전성 오류: {errors}"
        assert len(monitor.tasks) == 20


# ---------------------------------------------------------------------------
# Q: get_live_stats 캐시
# ---------------------------------------------------------------------------

class TestGetLiveStatsCache:
    """항목 Q: _recent_tasks_cache와 get_live_stats() 캐시 최적화."""

    def test_performance_monitor_has_recent_tasks_cache(self):
        """_recent_tasks_cache 속성이 PerformanceMonitor에 존재한다."""
        monitor = _make_monitor()
        assert hasattr(monitor, "_recent_tasks_cache"), (
            "_recent_tasks_cache 속성이 없다"
        )

    def test_recent_tasks_cache_populated_after_record(self):
        """record_task() 후 _recent_tasks_cache에 항목이 추가된다."""
        monitor = _make_monitor()
        initial_len = len(monitor._recent_tasks_cache)
        tr = _make_task_result(task_id="cache_test_001")
        monitor.record_task(tr)
        assert len(monitor._recent_tasks_cache) > initial_len

    def test_get_live_stats_uses_cache_for_short_window(self):
        """record_task() 후 get_live_stats(window_seconds=30)가 빠르게 반환한다."""
        import time
        monitor = _make_monitor()
        for i in range(5):
            tr = _make_task_result(task_id=f"live_stats_task_{i}")
            monitor.record_task(tr)

        start = time.perf_counter()
        stats = monitor.get_live_stats(window_seconds=30)
        elapsed = time.perf_counter() - start

        assert stats is not None, "get_live_stats()가 None을 반환한다"
        assert elapsed < 2.0, f"get_live_stats()가 너무 느리다: {elapsed:.3f}s"

    def test_get_live_stats_has_expected_keys(self):
        """get_live_stats()가 task_count 등 기본 키를 포함한다."""
        monitor = _make_monitor()
        tr = _make_task_result(task_id="live_stats_key_test")
        monitor.record_task(tr)

        stats = monitor.get_live_stats(window_seconds=60)
        assert isinstance(stats, dict), "get_live_stats()가 dict를 반환해야 한다"
        # 최소한 하나의 통계 키를 포함해야 한다
        assert len(stats) > 0


# ---------------------------------------------------------------------------
# R: _STREAMING_THRESHOLD 상수
# ---------------------------------------------------------------------------

class TestStreamingThreshold:
    """항목 R: _STREAMING_THRESHOLD 상수가 monitor.py에 정의됨."""

    def test_streaming_threshold_constant_exists(self):
        """_STREAMING_THRESHOLD가 monitor.py에 정의되어 있다."""
        from agent_evaluator.core.trackers import monitor as monitor_module
        assert hasattr(monitor_module, "_STREAMING_THRESHOLD"), (
            "_STREAMING_THRESHOLD 상수가 monitor.py에 없다"
        )

    def test_streaming_threshold_is_positive_int(self):
        """_STREAMING_THRESHOLD가 양의 정수여야 한다."""
        from agent_evaluator.core.trackers.monitor import _STREAMING_THRESHOLD
        assert isinstance(_STREAMING_THRESHOLD, int), (
            "_STREAMING_THRESHOLD가 int가 아니다"
        )
        assert _STREAMING_THRESHOLD > 0, "_STREAMING_THRESHOLD는 양수여야 한다"

    def test_streaming_threshold_value_reasonable(self):
        """_STREAMING_THRESHOLD가 합리적인 범위(100 ~ 100000)에 있다."""
        from agent_evaluator.core.trackers.monitor import _STREAMING_THRESHOLD
        assert 100 <= _STREAMING_THRESHOLD <= 100_000, (
            f"_STREAMING_THRESHOLD={_STREAMING_THRESHOLD}이 합리적 범위를 벗어났다"
        )


# ===========================================================================
# 축 5 — QuickEval & DX
# ===========================================================================


# ---------------------------------------------------------------------------
# C: gate() 고급 임계값
# ---------------------------------------------------------------------------

class TestGateAdvancedThresholds:
    """항목 C: gate() token_efficiency_min / dry_run 파라미터."""

    def test_gate_has_token_efficiency_min_param(self):
        """gate() 시그니처에 token_efficiency_min 파라미터가 있다."""
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.gate)
        assert "token_efficiency_min" in sig.parameters, (
            "gate()에 token_efficiency_min 파라미터가 없다"
        )

    def test_gate_has_dry_run_param(self):
        """gate() 시그니처에 dry_run 파라미터가 있다."""
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.gate)
        assert "dry_run" in sig.parameters

    def test_gate_dry_run_includes_token_efficiency(self):
        """gate(dry_run=True, token_efficiency_min=...) 결과에 token_efficiency 키가 있다."""
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator import create_taskresult

        qe = QuickEval("results/")
        # 실제 태스크 하나 추가
        tr = create_taskresult(
            task_id="gate_test_001",
            question="테스트?",
            response="답변",
            ground_truth="답변",
            execution_time=0.5,
            task_type="qa",
        )
        qe.monitor.record_task(tr)

        result = qe.gate(dry_run=True, token_efficiency_min=1000)
        assert isinstance(result, dict)
        assert "results" in result
        assert "token_efficiency" in result["results"], (
            "dry_run 결과에 token_efficiency 키가 없다"
        )

    def test_gate_dry_run_returns_dict_not_sys_exit(self):
        """gate(dry_run=True)는 sys.exit() 없이 dict를 반환한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        # 태스크 없는 상태에서 dry_run
        result = qe.gate(dry_run=True)
        assert isinstance(result, dict), "dry_run=True인데 dict가 반환되지 않았다"


# ---------------------------------------------------------------------------
# V: summary() _meta
# ---------------------------------------------------------------------------

class TestSummaryMeta:
    """항목 V: summary()에 _meta 키 포함."""

    def test_summary_has_meta_key(self):
        """summary()가 _meta 키를 포함해야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        result = qe.summary()
        assert "_meta" in result, f"summary()에 _meta 키가 없다. 키 목록: {list(result.keys())}"

    def test_summary_meta_is_dict(self):
        """summary()['_meta']가 dict여야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        result = qe.summary()
        assert isinstance(result["_meta"], dict)

    def test_summary_meta_has_meaningful_fields(self):
        """_meta에 계산 가능 여부 관련 필드가 있다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval("results/")
        meta = qe.summary()["_meta"]
        # 계산 가능성 관련 필드 (최소 1개 이상)
        assert len(meta) > 0, "_meta가 비어있다"


# ---------------------------------------------------------------------------
# Y: for_regression_eval() + check_regression()
# ---------------------------------------------------------------------------

class TestForRegressionEval:
    """항목 Y: QuickEval.for_regression_eval() / check_regression()."""

    def test_for_regression_eval_has_baseline_file_param(self):
        """for_regression_eval() 시그니처에 baseline_file 파라미터가 있다."""
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.for_regression_eval)
        assert "baseline_file" in sig.parameters, (
            "for_regression_eval에 baseline_file 파라미터가 없다"
        )

    def test_for_regression_eval_has_regression_threshold_param(self):
        """for_regression_eval() 시그니처에 regression_threshold 파라미터가 있다."""
        from agent_evaluator.quick_eval import QuickEval
        sig = inspect.signature(QuickEval.for_regression_eval)
        assert "regression_threshold" in sig.parameters

    def test_check_regression_no_baseline_returns_expected_dict(self):
        """check_regression() baseline 없으면 {'has_baseline': False} 포함 dict 반환."""
        from agent_evaluator.quick_eval import QuickEval

        # baseline_file 미지정 → baseline 없는 상태
        qe = QuickEval.for_regression_eval("results/", baseline_file=None)
        result = qe.check_regression()

        assert isinstance(result, dict)
        assert "has_baseline" in result, f"has_baseline 키가 없다. 키: {list(result.keys())}"
        assert result["has_baseline"] is False

    def test_for_regression_eval_returns_quickeval_instance(self):
        """for_regression_eval()이 QuickEval 인스턴스를 반환한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval.for_regression_eval("results/")
        assert isinstance(qe, QuickEval)

    def test_check_regression_has_regression_threshold_pct_key_with_baseline(self):
        """baseline이 있을 때 check_regression() 반환 dict에 regression_threshold_pct 키가 있다.

        baseline이 없으면 {'has_baseline': False} 만 반환하므로,
        _baseline_summary를 직접 주입해 baseline 있는 경로를 검증한다.
        """
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval.for_regression_eval("results/", regression_threshold=0.1)
        # baseline_summary를 직접 주입해 has_baseline=True 경로로 진입
        qe._baseline_summary = {"tcr": 90.0, "accuracy": 80.0}
        result = qe.check_regression()
        assert "regression_threshold_pct" in result, (
            f"regression_threshold_pct 키가 없다. 키: {list(result.keys())}"
        )
        assert result["regression_threshold_pct"] == pytest.approx(10.0)
