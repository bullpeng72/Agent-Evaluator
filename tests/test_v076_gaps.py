"""
tests/test_v076_gaps.py
=======================
v0.7.6 신규 기능 회귀 테스트 (17 gaps).

Gaps covered:
  A1  – GET /api/results/{file_id}/metrics/{metric_name}
  A2  – GET /api/export/parquet/{file_id}  (alerts.py 에서 구현)
  A3  – GET /api/alerts/patterns
  H1  – GET /api/results/{file_id}/heatmap/{metric}
  B1  – agent_eval auto_retry params (→ agent_eval_with_retry 위임)
  B3  – batch_eval shuffle/shuffle_seed
  C1  – monitor.estimate_token_cost_per_request()
  C2  – monitor.compare_models()
  C3  – monitor.export_to_wandb() / export_to_mlflow()
  D1  – QuickEval.compare()
  D2  – QuickEval.for_regression_eval()
  E1  – CrewAI 2.0+ output_pydantic 지원
  E2  – vertexai_eval 어댑터
  E3  – ollama_eval 어댑터
  F1  – monitor.configure_suspicious_patterns() / evaluate_suspicious_patterns()
  F2  – SimpleTaskAlertRule.dry_run()
  G2  – monitor.enable_compression()
"""
from __future__ import annotations

import dataclasses
import datetime
import os
import sys
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    task_id: str = "t1",
    task_type: str = "qa",
    success: bool = True,
    accuracy_score: float = 0.9,
    execution_time: float = 1.0,
    tokens_used: Dict = None,
    framework: str = "native",
    errors: List = None,
):
    from agent_evaluator.core.trackers.base import TaskResult
    return TaskResult(
        task_id=task_id,
        task_type=task_type,
        success=success,
        completion_score=1.0,
        accuracy_score=accuracy_score,
        execution_time=execution_time,
        tokens_used=tokens_used or {},
        tool_calls=[],
        attempts=1,
        errors=errors or [],
        timestamp=datetime.datetime.now(),
        framework=framework,
    )


def _make_monitor():
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor
    return PerformanceMonitor()


# ---------------------------------------------------------------------------
# A1: GET /api/results/{file_id}/metrics/{metric_name}
# ---------------------------------------------------------------------------

class TestMetricDetailEndpoint:
    def test_route_registered(self):
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("/results/{file_id}/metrics/{metric_name}" in p for p in paths)

    def test_invalid_metric_raises_404(self):
        """존재하지 않는 metric_name 은 HTTPException 404 반환."""
        from agent_evaluator.serve.routers import data as data_mod
        from fastapi import HTTPException

        class FakeRF:
            file_id = "f1"
            accuracy_metrics = {}
            efficiency_metrics = {}
            hallucination_detail = SimpleNamespace(detections=[], indicator_types={})
            has_hallucination = False
            quality_detail = SimpleNamespace(avg_score=0, evaluations=[], dimension_summary={}, grade_distribution={})
            security_l1 = SimpleNamespace(input_security=0, output_leakage=0, authorization=0)
            security_l2 = SimpleNamespace(privilege_escalation=0, attack_detection=0)
            agentic = SimpleNamespace(tool_efficiency=0, retry_summary={}, coordination_summary={}, workflow_summary={})
            cost_data = {}
            llm_judge = SimpleNamespace(judged_count=0, avg_overall=0, avg_completeness=0, avg_relevance=0, avg_factual_consistency=0, avg_toxicity=0, avg_bias=0, avg_faithfulness=0, avg_criteria_overall=0, results=[])

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        with pytest.raises(HTTPException) as exc_info:
            data_mod.get_metric_detail("f1", "nonexistent_metric", FakeRequest())
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# H1: GET /api/results/{file_id}/heatmap/{metric}
# ---------------------------------------------------------------------------

class TestHeatmapEndpoint:
    def test_route_registered(self):
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("/results/{file_id}/heatmap/{metric}" in p for p in paths)

    def test_invalid_metric_raises_404(self):
        from agent_evaluator.serve.routers import data as data_mod
        from fastapi import HTTPException

        class FakeRF:
            file_id = "f1"
            tasks = []

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        with pytest.raises(HTTPException):
            data_mod.get_metric_heatmap("f1", "invalid_metric", FakeRequest())

    def test_valid_metric_returns_structure(self):
        from agent_evaluator.serve.routers import data as data_mod

        fake_task = SimpleNamespace(
            task_type="qa",
            accuracy_score=0.9,
            execution_time=1.2,
            completion_score=1.0,
            timestamp="2026-04-04T10:00:00",
        )

        class FakeRF:
            file_id = "f1"
            tasks = [fake_task]

        class FakeRS:
            def by_id(self, fid):
                return FakeRF()

        class FakeApp:
            class state:
                result_set = FakeRS()

        class FakeRequest:
            app = FakeApp()

        result = data_mod.get_metric_heatmap("f1", "accuracy_score", FakeRequest())
        assert "x_labels" in result
        assert "y_labels" in result
        assert "matrix" in result
        assert result["metric"] == "accuracy_score"


# ---------------------------------------------------------------------------
# B1: agent_eval auto_retry
# ---------------------------------------------------------------------------

class TestAgentEvalAutoRetry:
    def test_auto_retry_succeeds(self):
        """max_retries=2 — 첫 시도 성공 시 1회만 실행."""
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa", max_retries=2)
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?", ground_truth="answer")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1

    def test_auto_retry_retries_on_failure(self):
        """max_retries=3 — 3회 시도 후 성공."""
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor()
        call_count = [0]

        @agent_eval(m, task_type="qa", max_retries=3, retry_on=(ValueError,))
        def fn(question, ground_truth=""):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("simulated error")
            return "ok"

        result = fn("q?")
        assert result == "ok"
        assert call_count[0] == 3
        assert m.tasks[-1].attempts == 3

    def test_no_auto_retry_by_default(self):
        """max_retries 기본값 1 — 재시도 없음."""
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# B3: batch_eval shuffle
# ---------------------------------------------------------------------------

class TestBatchEvalShuffle:
    def test_shuffle_changes_order(self):
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()
        questions = [f"q{i}" for i in range(10)]

        @batch_eval(m, shuffle=True, shuffle_seed=42)
        def fn(questions, ground_truths=None):
            return [f"a_{q}" for q in questions]

        fn(questions=questions, ground_truths=[f"gt{i}" for i in range(10)])

        recorded_qs = [t.question for t in m.tcr_tracker.tasks]
        # 셔플 결과는 원본 순서와 달라야 한다 (seed=42 기준)
        assert recorded_qs != questions

    def test_shuffle_seed_is_deterministic(self):
        from agent_evaluator.decorators import batch_eval
        questions = ["q1", "q2", "q3", "q4", "q5"]

        m1 = _make_monitor()
        m2 = _make_monitor()

        @batch_eval(m1, shuffle=True, shuffle_seed=99)
        def fn1(questions, ground_truths=None):
            return questions

        @batch_eval(m2, shuffle=True, shuffle_seed=99)
        def fn2(questions, ground_truths=None):
            return questions

        fn1(questions=questions)
        fn2(questions=questions)

        qs1 = [t.question for t in m1.tcr_tracker.tasks]
        qs2 = [t.question for t in m2.tcr_tracker.tasks]
        assert qs1 == qs2

    def test_no_shuffle_preserves_order(self):
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()
        questions = ["q0", "q1", "q2"]

        @batch_eval(m, shuffle=False)
        def fn(questions, ground_truths=None):
            return questions

        fn(questions=questions)
        recorded = [t.question for t in m.tcr_tracker.tasks]
        assert recorded == questions


# ---------------------------------------------------------------------------
# C1: estimate_token_cost_per_request
# ---------------------------------------------------------------------------

class TestEstimateTokenCost:
    def test_empty_returns_zeros(self):
        m = _make_monitor()
        result = m.estimate_token_cost_per_request()
        assert result["count"] == 0
        assert result["avg_cost_usd"] == 0.0

    def test_with_tasks(self):
        m = _make_monitor()
        for i in range(3):
            m.record_task(_make_result(
                task_id=f"t{i}",
                tokens_used={"input": 100, "output": 50, "total": 150},
            ))
        result = m.estimate_token_cost_per_request()
        assert result["count"] == 3
        assert result["avg_input_tokens"] == 100.0
        assert result["avg_output_tokens"] == 50.0
        assert result["avg_cost_usd"] > 0.0

    def test_filter_by_task_type(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", task_type="qa", tokens_used={"input": 100, "output": 50}))
        m.record_task(_make_result("t2", task_type="code_generation", tokens_used={"input": 200, "output": 100}))

        qa_result = m.estimate_token_cost_per_request("qa")
        assert qa_result["count"] == 1
        assert qa_result["avg_input_tokens"] == 100.0


# ---------------------------------------------------------------------------
# C2: compare_models
# ---------------------------------------------------------------------------

class TestCompareModels:
    def test_empty_returns_empty(self):
        m = _make_monitor()
        result = m.compare_models()
        assert isinstance(result, dict)

    def test_groups_by_model_field(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", tokens_used={"input": 100, "output": 50, "model": "gpt-4o"}))
        m.record_task(_make_result("t2", tokens_used={"input": 200, "output": 100, "model": "gpt-4o"}))
        m.record_task(_make_result("t3", tokens_used={"input": 50, "output": 25, "model": "claude-sonnet-4-6"}))

        result = m.compare_models()
        assert "gpt-4o" in result
        assert "claude-sonnet-4-6" in result
        assert result["gpt-4o"]["count"] == 2
        assert result["claude-sonnet-4-6"]["count"] == 1

    def test_filter_by_model_names(self):
        m = _make_monitor()
        m.record_task(_make_result("t1", tokens_used={"model": "gpt-4o"}))
        m.record_task(_make_result("t2", tokens_used={"model": "claude-haiku"}))

        result = m.compare_models(model_names=["gpt-4o"])
        assert "gpt-4o" in result
        assert "claude-haiku" not in result


# ---------------------------------------------------------------------------
# C3: export_to_wandb / export_to_mlflow (ImportError path)
# ---------------------------------------------------------------------------

class TestExportToExternalServices:
    def test_wandb_raises_import_error_if_not_installed(self):
        import importlib, sys
        m = _make_monitor()
        orig = sys.modules.get("wandb")
        sys.modules["wandb"] = None  # simulate missing package
        try:
            with pytest.raises((ImportError, TypeError)):
                m.export_to_wandb("test-project")
        finally:
            if orig is None:
                sys.modules.pop("wandb", None)
            else:
                sys.modules["wandb"] = orig

    def test_mlflow_raises_import_error_if_not_installed(self):
        import sys
        m = _make_monitor()
        orig = sys.modules.get("mlflow")
        sys.modules["mlflow"] = None
        try:
            with pytest.raises((ImportError, TypeError)):
                m.export_to_mlflow("test-experiment")
        finally:
            if orig is None:
                sys.modules.pop("mlflow", None)
            else:
                sys.modules["mlflow"] = orig


# ---------------------------------------------------------------------------
# D1: QuickEval.compare()
# ---------------------------------------------------------------------------

class TestQuickEvalCompare:
    def test_compare_returns_three_keys(self):
        from agent_evaluator.quick_eval import QuickEval
        q1 = QuickEval()
        q2 = QuickEval()
        result = q1.compare(q2)
        assert "self" in result
        assert "other" in result
        assert "delta" in result

    def test_delta_is_self_minus_other(self):
        from agent_evaluator.quick_eval import QuickEval
        q1 = QuickEval()
        q2 = QuickEval()
        q1.monitor.record_task(_make_result("t1", accuracy_score=0.9, success=True))
        q2.monitor.record_task(_make_result("t2", accuracy_score=0.7, success=True))

        result = q1.compare(q2)
        # tcr 는 둘 다 100% → delta 0
        assert result["delta"]["tcr"] == 0.0


# ---------------------------------------------------------------------------
# D2: QuickEval.for_regression_eval()
# ---------------------------------------------------------------------------

class TestQuickEvalForRegressionEval:
    def test_factory_returns_quickeval(self):
        from agent_evaluator.quick_eval import QuickEval
        qr = QuickEval.for_regression_eval()
        assert isinstance(qr, QuickEval)

    def test_auto_save_enabled(self):
        from agent_evaluator.quick_eval import QuickEval
        qr = QuickEval.for_regression_eval()
        assert qr.monitor.auto_save is True


# ---------------------------------------------------------------------------
# E1: CrewAI 2.0+ output_pydantic 지원
# ---------------------------------------------------------------------------

class TestCrewAIOutputPydantic:
    def test_output_pydantic_extracted(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakePydantic:
            def model_dump_json(self):
                return '{"result": "ok"}'

        class FakeCrewOutput:
            tasks_output = None
            output_pydantic = FakePydantic()

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert len(meta.agent_interactions) == 1
        assert meta.agent_interactions[0]["type"] == "task_completion"
        assert "output_pydantic" in meta.agent_interactions[0]["context"]

    def test_tasks_output_with_pydantic_merged(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakePydantic:
            def model_dump_json(self):
                return '{"result": "ok"}'

        class FakeTaskOut:
            agent = "researcher"
            description = "Research task"
            raw = "Research result"

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = FakePydantic()

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        # tasks_output + output_pydantic = 2 interactions
        assert len(meta.agent_interactions) == 2

    def test_no_output_pydantic_unchanged(self):
        from agent_evaluator.decorators import _extract_crewai_metadata

        class FakeTaskOut:
            agent = "researcher"
            description = "Task"
            raw = "Result"

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert len(meta.agent_interactions) == 1


# ---------------------------------------------------------------------------
# E2: vertexai_eval 어댑터
# ---------------------------------------------------------------------------

class TestVertexAIAdapter:
    def test_vertexai_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "vertexai" in _FRAMEWORK_ADAPTERS

    def test_vertexai_extract_tool_calls(self):
        from agent_evaluator.decorators import _extract_vertexai_metadata

        class FakeFunctionCall:
            name = "get_weather"
            args = {"location": "Seoul"}

        class FakePart:
            function_call = FakeFunctionCall()

        class FakeContent:
            parts = [FakePart()]

        class FakeCandidate:
            content = FakeContent()

        class FakeUsage:
            prompt_token_count = 100
            candidates_token_count = 50
            total_token_count = 150

        class FakeResponse:
            candidates = [FakeCandidate()]
            usage_metadata = FakeUsage()

        meta = _extract_vertexai_metadata(FakeResponse())
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["name"] == "get_weather"
        assert meta.tokens_used["input"] == 100
        assert meta.framework == "vertexai"

    def test_vertexai_eval_via_agent_eval(self):
        from agent_evaluator import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa", framework="vertexai")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# E3: ollama_eval 어댑터
# ---------------------------------------------------------------------------

class TestOllamaAdapter:
    def test_ollama_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "ollama" in _FRAMEWORK_ADAPTERS

    def test_ollama_extract_tokens_from_dict(self):
        from agent_evaluator.decorators import _extract_ollama_metadata

        resp = {
            "message": {"role": "assistant", "content": "Hello"},
            "prompt_eval_count": 80,
            "eval_count": 40,
        }
        meta = _extract_ollama_metadata(resp)
        assert meta is not None
        assert meta.tokens_used["input"] == 80
        assert meta.tokens_used["output"] == 40
        assert meta.framework == "ollama"

    def test_ollama_extract_tool_calls_from_dict(self):
        from agent_evaluator.decorators import _extract_ollama_metadata

        resp = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_time", "arguments": {}}}
                ],
            },
            "prompt_eval_count": 50,
            "eval_count": 20,
        }
        meta = _extract_ollama_metadata(resp)
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["name"] == "get_time"

    def test_ollama_eval_via_agent_eval(self):
        from agent_evaluator import agent_eval
        m = _make_monitor()

        @agent_eval(m, task_type="qa", framework="ollama")
        def fn(question, ground_truth=""):
            return "answer"

        result = fn("q?")
        assert result == "answer"
        assert len(m.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# F1: configure_suspicious_patterns / evaluate_suspicious_patterns
# ---------------------------------------------------------------------------

class TestSuspiciousPatterns:
    def test_no_patterns_returns_no_match(self):
        m = _make_monitor()
        result = m.evaluate_suspicious_patterns("sensitive text")
        assert result["matched"] is False
        assert result["match_count"] == 0

    def test_configure_and_match(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bpassword\b", "DROP TABLE"])
        result = m.evaluate_suspicious_patterns("my password is 123")
        assert result["matched"] is True
        assert r"\bpassword\b" in result["patterns_matched"]

    def test_no_match(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bsecret\b"])
        result = m.evaluate_suspicious_patterns("normal text here")
        assert result["matched"] is False

    def test_case_insensitive(self):
        m = _make_monitor()
        m.configure_suspicious_patterns(["DROP TABLE"])
        result = m.evaluate_suspicious_patterns("drop table users")
        assert result["matched"] is True

    def test_multiple_patterns_matched(self):
        m = _make_monitor()
        m.configure_suspicious_patterns([r"\bpassword\b", r"\bsecret\b"])
        result = m.evaluate_suspicious_patterns("password and secret here")
        assert result["match_count"] == 2


# ---------------------------------------------------------------------------
# F2: SimpleTaskAlertRule.dry_run()
# ---------------------------------------------------------------------------

class TestSimpleTaskAlertRuleDryRun:
    def _task(self, execution_time=1.0, accuracy_score=0.9):
        return _make_result("t1", execution_time=execution_time, accuracy_score=accuracy_score)

    def test_dry_run_fires(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="slow", condition=lambda r: r.execution_time > 5.0,
            handler=lambda m, r: None, severity="warning"
        )
        result = rule.dry_run(self._task(execution_time=10.0))
        assert result["would_fire"] is True
        assert result["message"] is not None
        assert "[WARNING]" in result["message"]
        assert result["error"] is None

    def test_dry_run_does_not_fire(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="slow", condition=lambda r: r.execution_time > 5.0,
            handler=lambda m, r: None
        )
        result = rule.dry_run(self._task(execution_time=1.0))
        assert result["would_fire"] is False
        assert result["message"] is None

    def test_dry_run_error_in_condition(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="broken", condition=lambda r: 1 / 0,
            handler=lambda m, r: None
        )
        result = rule.dry_run(self._task())
        assert result["would_fire"] is False
        assert result["error"] is not None

    def test_dry_run_does_not_call_handler(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        called = [False]

        def bad_handler(m, r):
            called[0] = True

        rule = SimpleTaskAlertRule(
            name="test", condition=lambda r: True,
            handler=bad_handler
        )
        rule.dry_run(self._task())
        assert called[0] is False  # handler should NOT be called


# ---------------------------------------------------------------------------
# G2: enable_compression
# ---------------------------------------------------------------------------

class TestEnableCompression:
    def test_enable_gzip_sets_algorithm(self):
        m = _make_monitor()
        m.enable_compression("gzip")
        assert getattr(m, "_compression_algorithm", None) == "gzip"

    def test_enable_bz2_sets_algorithm(self):
        m = _make_monitor()
        m.enable_compression("bz2")
        assert getattr(m, "_compression_algorithm", None) == "bz2"

    def test_unsupported_algorithm_defaults_to_gzip(self):
        m = _make_monitor()
        m.enable_compression("xz")  # unsupported
        assert getattr(m, "_compression_algorithm", None) == "gzip"

    def test_save_creates_compressed_file(self):
        m = _make_monitor()
        m.enable_compression("gzip")
        m.record_task(_make_result())

        with tempfile.TemporaryDirectory() as tmpdir:
            m.output_dir = Path(tmpdir)
            # Use explicit .json extension so the compressed file is test_comp.json.gz
            json_path = m.save_to_file("test_comp.json")
            gz_path = Path(json_path + ".gz")
            assert gz_path.exists(), f"Expected compressed file at {gz_path}"
            # Verify it's valid gzip
            import gzip
            with gzip.open(gz_path) as f:
                content = json.loads(f.read())
            assert isinstance(content, dict)
