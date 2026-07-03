"""
tests/test_judge_execution_model_heterogeneity.py
=====================================================
SPEC-023 검증: judge_model이 실행 model_name과 동일할 때 PerformanceMonitor가
UserWarning을 발행하고, extra_metrics.lineage.judge_same_as_execution_model에
그 판정을 남기는지.
"""
import warnings

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.llm_judge import LLMJudge


class TestSameModelWarns:
    def test_warns_when_judge_model_equals_execution_model(self):
        with pytest.warns(UserWarning, match="judge_model"):
            monitor = PerformanceMonitor(
                model_name="qwen3-coder:latest",
                enable_llm_judge=True, judge_model="qwen3-coder:latest",
            )
        assert monitor._judge_same_as_execution_model is True

    def test_different_models_no_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            monitor = PerformanceMonitor(
                model_name="claude-sonnet-5",
                enable_llm_judge=True, judge_model="claude-haiku-4-5-20251001",
            )
        assert monitor._judge_same_as_execution_model is False

    def test_empty_model_name_no_warning(self):
        """model_name 미설정(빈 문자열)이면 비교 대상이 없으므로 경고하지 않는다."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            monitor = PerformanceMonitor(
                model_name="", enable_llm_judge=True, judge_model="claude-haiku-4-5-20251001",
            )
        assert monitor._judge_same_as_execution_model is False

    def test_judge_disabled_no_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            monitor = PerformanceMonitor(model_name="qwen3-coder:latest")  # enable_llm_judge 기본값 False
        assert monitor._judge_same_as_execution_model is False

    def test_judge_init_failure_no_warning(self, monkeypatch):
        """LLMJudge 생성 자체가 실패하면 self.llm_judge가 None으로 남으므로 비교 자체가 스킵된다."""
        def _boom(self, *args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(LLMJudge, "__init__", _boom)
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            monitor = PerformanceMonitor(
                model_name="qwen3-coder:latest",
                enable_llm_judge=True, judge_model="qwen3-coder:latest",
            )
        assert monitor.llm_judge is None
        assert monitor.enable_llm_judge is False
        assert monitor._judge_same_as_execution_model is False


class TestLineageField:
    def test_lineage_true_when_same_model(self):
        monitor = PerformanceMonitor(
            output_dir="/tmp",
            model_name="qwen3-coder:latest",
            enable_llm_judge=True, judge_model="qwen3-coder:latest",
        )
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0,
        ))
        lineage = monitor.generate_report().to_dict()["extra_metrics"]["lineage"]
        assert lineage["judge_same_as_execution_model"] is True

    def test_lineage_false_when_different_model(self):
        monitor = PerformanceMonitor(
            output_dir="/tmp",
            model_name="claude-sonnet-5",
            enable_llm_judge=True, judge_model="claude-haiku-4-5-20251001",
        )
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0,
        ))
        lineage = monitor.generate_report().to_dict()["extra_metrics"]["lineage"]
        assert lineage["judge_same_as_execution_model"] is False

    def test_lineage_false_when_judge_disabled(self):
        monitor = PerformanceMonitor(output_dir="/tmp", model_name="qwen3-coder:latest")
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0,
        ))
        lineage = monitor.generate_report().to_dict()["extra_metrics"]["lineage"]
        assert lineage["judge_same_as_execution_model"] is False
