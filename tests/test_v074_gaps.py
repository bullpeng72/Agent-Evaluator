"""
tests/test_v074_gaps.py
========================
v0.7.4 수정 사항 테스트:
  - eval_context timeout 파라미터
  - EvalDecorator.batch() 파라미터 전파 (_BATCH_PARAMS)
  - EvalDecorator.context() timeout 전파
"""
from __future__ import annotations

import time
import pytest


# ---------------------------------------------------------------------------
# eval_context timeout
# ---------------------------------------------------------------------------

class TestEvalContextTimeout:
    def test_timeout_param_accepted(self, tmp_path):
        """timeout 파라미터가 오류 없이 수용되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=10.0) as ctx:
            ctx.response = "answer"

    def test_no_timeout_normal_execution(self, tmp_path):
        """timeout 미지정 시 정상 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", ground_truth="ans") as ctx:
            ctx.response = "ans"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is True

    def test_timeout_exceeded_marks_error(self, tmp_path):
        """timeout 초과 시 has_error=True 로 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=0.01) as ctx:
            time.sleep(0.05)   # 0.05s > 0.01s timeout
            ctx.response = "too slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        # timeout 초과는 has_error=True 로 기록
        assert tasks[0].success is False

    def test_timeout_not_exceeded_no_error(self, tmp_path):
        """timeout 내 완료 시 정상 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=5.0) as ctx:
            ctx.response = "fast answer"

        tcr = getattr(monitor, "tcr_tracker", None)
        assert tcr is not None
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is True

    def test_timeout_error_message_contains_timeout_info(self, tmp_path):
        """timeout 초과 오류 메시지에 timeout 정보가 포함되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with eval_context(monitor, "qa", question="q", timeout=0.01) as ctx:
            time.sleep(0.05)
            ctx.response = "slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        errors = tasks[0].errors or []
        assert any("timeout" in str(e).lower() or "exceeded" in str(e).lower() for e in errors)

    def test_timeout_does_not_suppress_real_exceptions(self, tmp_path):
        """timeout 설정이 있어도 실제 예외는 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        with pytest.raises(ValueError):
            with eval_context(monitor, "qa", question="q", timeout=5.0) as ctx:
                raise ValueError("real error")


# ---------------------------------------------------------------------------
# EvalDecorator.batch() 파라미터 전파
# ---------------------------------------------------------------------------

class TestEvalDecoratorBatchParams:
    def test_on_error_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 on_error 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        error_log = []

        eval_dec = EvalDecorator(monitor, on_error=lambda tr: error_log.append(tr.task_id))

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            raise RuntimeError("batch fail")

        with pytest.raises(RuntimeError):
            batch_agent(questions=["q1"], ground_truths=["a1"])

        # on_error 콜백이 호출되어야 함
        assert len(error_log) >= 1

    def test_score_fn_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 score_fn 이 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        score_calls = []

        def my_score(response: str, gt: str) -> float:
            score_calls.append((response, gt))
            return 0.95

        eval_dec = EvalDecorator(monitor, score_fn=my_score)

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans_{i}" for i in range(len(questions))]

        batch_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(score_calls) == 2

    def test_alert_rules_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 alert_rules 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
            cooldown=0,
        )
        eval_dec = EvalDecorator(monitor, alert_rules=[rule])

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        batch_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(fired) == 2

    def test_timeout_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 timeout 이 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.001)  # 1ms timeout

        @eval_dec.batch(task_type="qa")
        def slow_batch(questions, ground_truths=None):
            time.sleep(0.5)  # 500ms — timeout 초과
            return [f"ans" for _ in questions]

        with pytest.raises((TimeoutError, Exception)):
            slow_batch(questions=["q1"], ground_truths=["a1"])

    def test_framework_propagated_to_batch(self, tmp_path):
        """EvalDecorator의 framework 가 batch()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, framework="openai")

        @eval_dec.batch(task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        batch_agent(questions=["q1"], ground_truths=["a1"])

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        assert tasks[0].framework == "openai"

    def test_batch_params_frozenset_exists(self):
        """EvalDecorator._BATCH_PARAMS 가 존재하고 필요한 파라미터를 포함해야 한다."""
        from agent_evaluator.decorators import EvalDecorator

        assert hasattr(EvalDecorator, "_BATCH_PARAMS")
        bp = EvalDecorator._BATCH_PARAMS
        assert "on_error" in bp
        assert "task_id_fn" in bp
        assert "timeout" in bp
        assert "context_arg" in bp
        assert "expected_tools_arg" in bp


# ---------------------------------------------------------------------------
# EvalDecorator.context() timeout 전파
# ---------------------------------------------------------------------------

class TestEvalDecoratorContextTimeout:
    def test_timeout_propagated_to_context(self, tmp_path):
        """EvalDecorator의 timeout 이 context()에 전파되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.01)

        with eval_dec.context("qa", question="q") as ctx:
            time.sleep(0.05)   # timeout 초과
            ctx.response = "slow"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        assert len(tasks) == 1
        assert tasks[0].success is False  # timeout 초과 → has_error=True

    def test_context_timeout_override(self, tmp_path):
        """context() 호출 시 timeout 직접 지정이 _defaults보다 우선해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        eval_dec = EvalDecorator(monitor, timeout=0.001)  # 극히 짧은 기본값

        # context() 호출 시 더 넉넉한 timeout 지정
        with eval_dec.context("qa", question="q", timeout=60.0) as ctx:
            ctx.response = "fast"

        tcr = getattr(monitor, "tcr_tracker", None)
        tasks = list(tcr.tasks)
        # 60초 timeout이 적용되어 정상 처리
        assert tasks[0].success is True
