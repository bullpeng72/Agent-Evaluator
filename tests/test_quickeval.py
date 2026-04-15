"""
tests/test_quickeval.py
=======================
QuickEval facade, __repr__ 버그 수정, 단축 데코레이터 속성 테스트.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def monitor():
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor
    return PerformanceMonitor(output_dir="/tmp/test_quickeval/")


@pytest.fixture()
def qe(monitor):
    from agent_evaluator.quick_eval import QuickEval
    from agent_evaluator.decorators import EvalDecorator
    qe = QuickEval.__new__(QuickEval)
    qe._monitor = monitor
    qe._eval = EvalDecorator(monitor)
    return qe


# ---------------------------------------------------------------------------
# __repr__ 버그 수정 검증 (Task 9 / B1)
# ---------------------------------------------------------------------------

class TestQuickEvalRepr:
    def test_repr_zero_tasks(self, qe):
        r = repr(qe)
        assert "tasks=0" in r

    def test_repr_no_attribute_error(self, qe):
        """tcr_tracker 없을 때 AttributeError 가 아니라 tasks=0 이어야 한다."""
        del qe._monitor.tcr_tracker
        r = repr(qe)
        assert "tasks=0" in r

    def test_repr_with_tasks(self, qe):
        from agent_evaluator import create_taskresult
        task = create_taskresult(
            task_id="t1", question="q", response="r",
            ground_truth="r", execution_time=0.1,
        )
        qe._monitor.record_task(task)
        r = repr(qe)
        assert "tasks=1" in r


# ---------------------------------------------------------------------------
# QuickEval 초기화 & 속성
# ---------------------------------------------------------------------------

class TestQuickEvalInit:
    def test_basic_init(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        qe = QuickEval(str(tmp_path) + "/")
        assert qe.monitor is not None
        assert qe.eval is not None

    def test_for_rag_factory(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        qe = QuickEval.for_rag(str(tmp_path) + "/")
        assert qe.monitor is not None

    def test_for_security_factory(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        qe = QuickEval.for_security(str(tmp_path) + "/")
        assert qe.monitor is not None

    def test_for_llm_judge_factory(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        qe = QuickEval.for_llm_judge(str(tmp_path) + "/", model="gpt-4o-mini")
        assert qe.monitor is not None


# ---------------------------------------------------------------------------
# 단축 데코레이터 속성 — @eval.qa, @eval.tool_use 등
# ---------------------------------------------------------------------------

class TestQuickEvalDecorators:
    def _apply(self, decorator, func):
        """decorator 를 func 에 적용하고 decorated 함수를 반환."""
        return decorator(func)

    def test_qa_decorator_no_parens(self, qe):
        @qe.qa
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        result = agent("q?", ground_truth="answer")
        assert result == "answer"

    def test_qa_decorator_with_kwargs(self, qe):
        @qe.qa()
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        result = agent("q?")
        assert result == "answer"

    def test_tool_use_decorator(self, qe):
        @qe.tool_use
        def agent(question: str, ground_truth: str = "") -> str:
            return "tool_result"

        assert agent("q?") == "tool_result"

    def test_code_decorator(self, qe):
        @qe.code
        def agent(question: str, ground_truth: str = "") -> str:
            return "def f(): pass"

        assert "def" in agent("write a function")

    def test_reasoning_decorator(self, qe):
        @qe.reasoning
        def agent(question: str, ground_truth: str = "") -> str:
            return "42"

        assert agent("why?") == "42"

    def test_direct_call(self, qe):
        @qe(task_type="qa")
        def agent(question: str, ground_truth: str = "") -> str:
            return "ok"

        assert agent("q?") == "ok"

    def test_rag_decorator(self, qe):
        @qe.rag
        def agent(question: str, context: str = "", ground_truth: str = "") -> str:
            return "rag_result"

        assert agent("q?", context="some context") == "rag_result"


# ---------------------------------------------------------------------------
# summary() 및 gate()
# ---------------------------------------------------------------------------

class TestQuickEvalSummaryGate:
    def test_summary_empty(self, qe):
        s = qe.summary()
        assert "tcr" in s
        assert "accuracy" in s
        assert "total_tasks" in s
        assert s["total_tasks"] == 0

    def test_summary_after_task(self, qe):
        from agent_evaluator import create_taskresult
        task = create_taskresult(
            task_id="t1", question="q", response="Seoul",
            ground_truth="Seoul", execution_time=0.5,
        )
        qe._monitor.record_task(task)
        s = qe.summary()
        assert s["total_tasks"] == 1

    def test_gate_passes_when_empty(self, qe):
        # 빈 모니터에서 gate()는 모든 지표가 0이므로 tcr/accuracy 임계값이 0이면 통과
        result = qe.gate(tcr=0, accuracy=0)
        assert result is True

    def test_gate_fails_with_high_threshold(self, qe):
        with pytest.raises(SystemExit):
            qe.gate(tcr=100)  # 빈 모니터에서는 항상 실패

    def test_save(self, tmp_path):
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator import create_taskresult
        qe = QuickEval(str(tmp_path) + "/")
        task = create_taskresult(
            task_id="t1", question="q", response="r",
            ground_truth="r", execution_time=0.1,
        )
        qe._monitor.record_task(task)
        path = qe.save("test_output")
        import os
        assert os.path.exists(path)


# ===========================================================================
# From test_refactor_dedup.py — Option B 리팩토링 검증
# ===========================================================================

import warnings as _warnings_mod


@pytest.fixture
def qe_refactor(tmp_path):
    from agent_evaluator import QuickEval
    return QuickEval(output_dir=str(tmp_path) + "/")


@pytest.fixture
def eval_dec(tmp_path):
    from agent_evaluator import PerformanceMonitor
    from agent_evaluator.decorators import EvalDecorator
    m = PerformanceMonitor(output_dir=str(tmp_path) + "/")
    return EvalDecorator(m)


class TestQuickEvalDelegation:
    """QuickEval 단축 속성이 EvalDecorator._ShortcutCallable로 위임되는지 검증."""

    TASK_TYPE_SHORTCUTS = (
        "qa", "tool_use", "rag", "code", "reasoning",
        "planning", "data_analysis", "creative", "streaming",
    )

    def test_all_shortcuts_return_shortcut_callable(self, qe_refactor):
        from agent_evaluator.decorators import _ShortcutCallable
        for attr in self.TASK_TYPE_SHORTCUTS:
            sc = getattr(qe_refactor, attr)
            assert isinstance(sc, _ShortcutCallable), (
                f"qe.{attr} should return _ShortcutCallable, got {type(sc).__name__}"
            )

    def test_shortcut_is_callable(self, qe_refactor):
        for attr in self.TASK_TYPE_SHORTCUTS:
            sc = getattr(qe_refactor, attr)
            assert callable(sc), f"qe.{attr} must be callable"

    def test_qa_no_paren_decorator(self, qe_refactor):
        @qe_refactor.qa
        def agent(question, ground_truth=""):
            return "answer"
        result = agent(question="수도는?", ground_truth="서울")
        assert result is not None

    def test_qa_with_kwargs_decorator(self, qe_refactor):
        called = []
        def my_score(response, gt):
            called.append(1)
            return 0.9
        @qe_refactor.qa(score_fn=my_score)
        def agent(question, ground_truth=""):
            return "answer"
        agent(question="수도는?", ground_truth="서울")
        assert len(called) >= 1

    def test_rag_sets_rag_mode(self, qe_refactor):
        from agent_evaluator.decorators import _ShortcutCallable
        sc = qe_refactor.rag
        assert isinstance(sc, _ShortcutCallable)
        assert sc._base_kwargs.get("rag_mode") is True

    def test_rag_sets_context_arg(self, qe_refactor):
        sc = qe_refactor.rag
        assert sc._base_kwargs.get("context_arg") == "context"

    def test_secure_sets_security_mode(self, qe_refactor):
        from agent_evaluator.decorators import _ShortcutCallable, SecurityConfig
        sc = qe_refactor.secure
        assert isinstance(sc, _ShortcutCallable)
        assert isinstance(sc._base_kwargs.get("security"), SecurityConfig)

    def test_multi_agent_shortcut_accessible(self, qe_refactor):
        from agent_evaluator.decorators import _ShortcutCallable
        sc = qe_refactor.multi_agent
        assert isinstance(sc, _ShortcutCallable)
        assert callable(sc)

    def test_update_defaults_delegated(self, qe_refactor):
        result = qe_refactor.update_defaults(sample_rate=0.5)
        from agent_evaluator.decorators import EvalDecorator
        assert isinstance(result, EvalDecorator)

    def test_inspect_delegated(self, qe_refactor):
        config = qe_refactor.inspect()
        assert isinstance(config, dict)

    def test_unknown_attribute_raises(self, qe_refactor):
        with pytest.raises(AttributeError):
            _ = qe_refactor.nonexistent_attr_xyz

    def test_private_attribute_raises(self, qe_refactor):
        with pytest.raises(AttributeError):
            _ = qe_refactor._nonexistent_private


class TestBatchChatShortcuts:
    """QuickEval.batch / .chat no-paren 동작 검증."""

    def test_batch_property_returns_shortcut(self, qe_refactor):
        from agent_evaluator.quick_eval import _QuickEvalBatchShortcut
        assert isinstance(qe_refactor.batch, _QuickEvalBatchShortcut)

    def test_chat_property_returns_shortcut(self, qe_refactor):
        from agent_evaluator.quick_eval import _QuickEvalChatShortcut
        assert isinstance(qe_refactor.chat, _QuickEvalChatShortcut)

    def test_batch_no_paren(self, qe_refactor):
        @qe_refactor.batch
        def batch_agent(questions, ground_truths=None):
            return [f"answer:{q}" for q in questions]
        results = batch_agent(questions=["Q1", "Q2"], ground_truths=["A1", "A2"])
        assert len(results) == 2

    def test_batch_with_kwargs(self, qe_refactor):
        @qe_refactor.batch(task_type="tool_use")
        def batch_agent(questions, ground_truths=None):
            return [f"answer:{q}" for q in questions]
        results = batch_agent(questions=["Q1"], ground_truths=["A1"])
        assert len(results) == 1

    def test_chat_no_paren(self, qe_refactor):
        @qe_refactor.chat
        def chatbot(question, session_id="default", ground_truth=""):
            return f"response:{question}"
        result = chatbot(question="안녕?", session_id="s1", ground_truth="")
        assert result is not None

    def test_chat_with_kwargs(self, qe_refactor):
        @qe_refactor.chat(max_turns=5)
        def chatbot(question, session_id="default", ground_truth=""):
            return f"response:{question}"
        result = chatbot(question="안녕?", session_id="s2", ground_truth="")
        assert result is not None


class TestEvalDecoratorFactoryDeprecation:
    """EvalDecorator의 deprecated 팩토리 메서드가 경고를 발생시키는지 검증."""

    def test_for_rag_emits_deprecation(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_rag(str(tmp_path) + "/")
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_for_rag_warning_message(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_rag(str(tmp_path) + "/")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert dep_warnings
        assert "QuickEval.for_rag" in str(dep_warnings[0].message)

    def test_for_rag_still_returns_evaldec(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True):
            _warnings_mod.simplefilter("always")
            result = EvalDecorator.for_rag(str(tmp_path) + "/")
        assert isinstance(result, EvalDecorator)

    def test_for_security_emits_deprecation(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_security(str(tmp_path) + "/")
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_for_security_warning_message(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_security(str(tmp_path) + "/")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert "QuickEval.for_security" in str(dep_warnings[0].message)

    def test_for_security_still_returns_evaldec(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True):
            _warnings_mod.simplefilter("always")
            result = EvalDecorator.for_security(str(tmp_path) + "/")
        assert isinstance(result, EvalDecorator)

    def test_for_llm_judge_emits_deprecation(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_llm_judge(str(tmp_path) + "/")
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_for_llm_judge_warning_message(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            EvalDecorator.for_llm_judge(str(tmp_path) + "/")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert "QuickEval.for_llm_judge" in str(dep_warnings[0].message)

    def test_for_llm_judge_still_returns_evaldec(self, tmp_path):
        from agent_evaluator.decorators import EvalDecorator
        with _warnings_mod.catch_warnings(record=True):
            _warnings_mod.simplefilter("always")
            result = EvalDecorator.for_llm_judge(str(tmp_path) + "/")
        assert isinstance(result, EvalDecorator)

    def test_quickeval_for_rag_no_deprecation(self, tmp_path):
        from agent_evaluator import QuickEval
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            QuickEval.for_rag(str(tmp_path) + "/")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert not dep_warnings

    def test_quickeval_for_security_no_deprecation(self, tmp_path):
        from agent_evaluator import QuickEval
        with _warnings_mod.catch_warnings(record=True) as w:
            _warnings_mod.simplefilter("always")
            QuickEval.for_security(str(tmp_path) + "/")
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert not dep_warnings


class TestQuickEvalDecoratorRemoved:
    """_QuickEvalDecorator 클래스가 제거됐는지 확인."""

    def test_not_importable(self):
        import agent_evaluator.quick_eval as qm
        assert not hasattr(qm, "_QuickEvalDecorator")


class TestQuickEvalRegression:
    """리팩토링 후에도 기존 공개 API가 동일하게 동작하는지 확인."""

    def test_qe_direct_call(self, qe_refactor):
        @qe_refactor(task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"
        result = agent(question="Q?", ground_truth="A")
        assert result is not None

    def test_qe_with_retry(self, qe_refactor):
        from agent_evaluator import RetryConfig
        @qe_refactor.with_retry(task_type="qa", retry=RetryConfig(max=1))
        def agent(question, ground_truth=""):
            return "answer"
        result = agent(question="Q?", ground_truth="A")
        assert result is not None

    def test_qe_save(self, qe_refactor, tmp_path):
        @qe_refactor.qa
        def agent(question, ground_truth=""):
            return "answer"
        agent(question="Q?", ground_truth="A")
        path = qe_refactor.save("test_save")
        import os
        assert os.path.exists(path)

    def test_qe_gate_passes(self, qe_refactor):
        result = qe_refactor.gate(tcr=0, dry_run=True)
        assert result is True or isinstance(result, dict)

    def test_qe_summary_returns_dict(self, qe_refactor):
        result = qe_refactor.summary()
        assert isinstance(result, dict)

    def test_qe_monitor_property(self, qe_refactor):
        from agent_evaluator import PerformanceMonitor
        assert isinstance(qe_refactor.monitor, PerformanceMonitor)

    def test_qe_eval_property(self, qe_refactor):
        from agent_evaluator.decorators import EvalDecorator
        assert isinstance(qe_refactor.eval, EvalDecorator)

    def test_qe_for_rag_factory(self, tmp_path):
        from agent_evaluator import QuickEval
        qe = QuickEval.for_rag(str(tmp_path) + "/")
        assert isinstance(qe, QuickEval)

    def test_qe_for_security_factory(self, tmp_path):
        from agent_evaluator import QuickEval
        qe = QuickEval.for_security(str(tmp_path) + "/")
        assert isinstance(qe, QuickEval)

    def test_qe_for_llm_judge_factory(self, tmp_path):
        from agent_evaluator import QuickEval
        qe = QuickEval.for_llm_judge(str(tmp_path) + "/", model="gpt-4o-mini")
        assert isinstance(qe, QuickEval)

    def test_qe_repr(self, qe_refactor):
        r = repr(qe_refactor)
        assert "QuickEval" in r

    def test_code_shortcut(self, qe_refactor):
        @qe_refactor.code
        def code_agent(question, ground_truth=""):
            return "def hello(): pass"
        result = code_agent(question="간단한 함수", ground_truth="def hello(): pass")
        assert result is not None

    def test_tool_use_shortcut(self, qe_refactor):
        @qe_refactor.tool_use
        def tool_agent(question, ground_truth=""):
            return "tool result"
        result = tool_agent(question="검색해줘", ground_truth="")
        assert result is not None

    def test_rag_shortcut_functional(self, qe_refactor):
        @qe_refactor.rag
        def rag_agent(question, context="", ground_truth=""):
            return f"answer based on {context}"
        result = rag_agent(question="Q?", context="Some context", ground_truth="A")
        assert result is not None


class TestEvalDecoratorShortcutsUnchanged:
    """EvalDecorator의 단축 속성이 리팩토링 후에도 동일하게 동작."""

    def test_all_shortcuts_still_shortcut_callable(self, eval_dec):
        from agent_evaluator.decorators import _ShortcutCallable
        for attr in ("qa", "tool_use", "rag", "code", "reasoning",
                     "planning", "data_analysis", "creative",
                     "multi_agent", "secure", "streaming"):
            val = getattr(eval_dec, attr)
            assert isinstance(val, _ShortcutCallable)

    def test_eval_dec_batch_method_still_works(self, eval_dec):
        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"a:{q}" for q in questions]
        results = batch_agent(questions=["Q1", "Q2"], ground_truths=["A1", "A2"])
        assert len(results) == 2

    def test_eval_dec_conversation_method_still_works(self, eval_dec):
        @eval_dec.conversation()
        def chatbot(question, session_id="default", ground_truth=""):
            return f"reply:{question}"
        result = chatbot(question="hi", session_id="s1", ground_truth="")
        assert result is not None
