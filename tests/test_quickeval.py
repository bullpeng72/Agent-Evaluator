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
