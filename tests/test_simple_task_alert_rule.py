"""
tests/test_simple_task_alert_rule.py
=====================================
SimpleTaskAlertRule 및 alert_rules 통합 테스트.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call


# ---------------------------------------------------------------------------
# SimpleTaskAlertRule 기본 동작
# ---------------------------------------------------------------------------

class TestSimpleTaskAlertRule:
    def _make_task(self, response="r", ground_truth="r", latency=1.0):
        from agent_evaluator import create_taskresult
        return create_taskresult(
            task_id="t1",
            question="q",
            response=response,
            ground_truth=ground_truth,
            execution_time=latency,
        )

    def test_fires_when_condition_met(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule

        fired = []
        rule = SimpleTaskAlertRule(
            name="slow_latency",
            condition=lambda tr: tr.execution_time > 0.5,  # latency > 0.5s
            handler=lambda msg, tr: fired.append(tr.task_id),
        )
        task = self._make_task(latency=1.0)  # 1s → 조건 충족
        rule.evaluate(task)
        assert len(fired) == 1

    def test_does_not_fire_when_condition_false(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule

        fired = []
        rule = SimpleTaskAlertRule(
            name="slow_latency",
            condition=lambda tr: tr.execution_time > 5.0,  # > 5s
            handler=lambda msg, tr: fired.append(tr.task_id),
        )
        task = self._make_task(latency=0.1)  # 0.1s → 조건 미충족
        rule.evaluate(task)
        assert len(fired) == 0

    def test_handler_is_called_with_name_in_message(self, caplog):
        import logging
        from agent_evaluator.decorators import SimpleTaskAlertRule

        captured = []
        rule = SimpleTaskAlertRule(
            name="test_rule",
            condition=lambda tr: True,
            handler=lambda msg, tr: captured.append(msg),
        )
        task = self._make_task()
        rule.evaluate(task)
        assert len(captured) == 1
        assert "test_rule" in captured[0]

    def test_handler_exception_is_suppressed(self):
        """handler 예외가 발생해도 evaluate()가 raise 하지 않아야 한다."""
        from agent_evaluator.decorators import SimpleTaskAlertRule

        rule = SimpleTaskAlertRule(
            name="bad_handler",
            condition=lambda tr: True,
            handler=lambda msg, tr: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        task = self._make_task()
        rule.evaluate(task)  # 예외 없이 통과


# ---------------------------------------------------------------------------
# alert_rules + agent_eval 통합
# ---------------------------------------------------------------------------

class TestAlertRulesWithAgentEval:
    def test_alert_fires_on_agent_eval(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir="/tmp/")
        fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
        )

        @agent_eval(monitor, task_type="qa", alert_rules=[rule])
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(fired) == 1

    def test_alert_combined_with_on_record(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir="/tmp/")
        alert_fired = []
        record_fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: alert_fired.append(1),
        )

        @agent_eval(
            monitor, task_type="qa",
            alert_rules=[rule],
            on_record=lambda tr: record_fired.append(1),
        )
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(alert_fired) == 1
        assert len(record_fired) == 1


# ---------------------------------------------------------------------------
# alert_rules + batch_eval 통합
# ---------------------------------------------------------------------------

class TestAlertRulesWithBatchEval:
    def test_alert_fires_per_item(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir="/tmp/")
        fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
            cooldown=0,  # cooldown 없이 매 항목마다 발동
        )

        @batch_eval(monitor, task_type="qa", alert_rules=[rule])
        def batch_agent(questions, ground_truths=None):
            return [f"answer_{i}" for i in range(len(questions))]

        batch_agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(fired) == 2  # 2개 항목 각각에 발동


# ---------------------------------------------------------------------------
# alert_rules + eval_context 통합
# ---------------------------------------------------------------------------

class TestAlertRulesWithEvalContext:
    def test_alert_fires_on_exit(self):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import eval_context, SimpleTaskAlertRule

        monitor = PerformanceMonitor(output_dir="/tmp/")
        fired = []

        rule = SimpleTaskAlertRule(
            name="any",
            condition=lambda tr: True,
            handler=lambda msg, tr: fired.append(tr.task_id),
        )

        with eval_context(
            monitor, "qa",
            question="q?", ground_truth="answer",
            alert_rules=[rule],
        ) as ctx:
            ctx.response = "answer"

        assert len(fired) == 1
