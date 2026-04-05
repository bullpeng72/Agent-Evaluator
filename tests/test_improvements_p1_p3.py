"""Tests for P1/P2/P3 improvements (v0.7.2 enhancement batch).

P1-A: EvalDecorator._BATCH_PARAMS includes on_batch_complete
P1-C: get_result() tasks[] includes chain_steps, quality_dimensions, streaming_metadata
P2-A: AGENT_EVAL_PRESETS updated values
P2-B: agent_eval enable_quality_evaluation parameter
P2-C: /quality-heatmap endpoint + /frameworks enhanced fields
P3-A: Haystack component type detection + token extraction; HuggingFace token estimation
P3-B: LLMJudge confidence field in scores
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# P3-B: LLMJudge confidence field
# ---------------------------------------------------------------------------
class TestLLMJudgeConfidence:
    def _get_judge(self):
        from agent_evaluator.integrations.llm_judge import LLMJudge
        return LLMJudge(model="claude-sonnet-4-6")

    def test_parse_judge_response_includes_confidence(self):
        judge = self._get_judge()
        raw = json.dumps({"completeness": 5, "relevance": 5, "factual_consistency": 5, "reasoning": "perfect"})
        result = judge._parse_judge_response("t1", raw, 0.001)
        assert "confidence" in result["scores"]
        assert 0.0 <= result["scores"]["confidence"] <= 1.0

    def test_perfect_agreement_high_confidence(self):
        judge = self._get_judge()
        raw = json.dumps({"completeness": 5, "relevance": 5, "factual_consistency": 5, "reasoning": ""})
        result = judge._parse_judge_response("t1", raw, 0.001)
        # std=0 → confidence=1.0
        assert result["scores"]["confidence"] == 1.0

    def test_high_disagreement_low_confidence(self):
        judge = self._get_judge()
        # completeness=1, relevance=3, factual=5 → big spread
        raw = json.dumps({"completeness": 1, "relevance": 3, "factual_consistency": 5, "reasoning": ""})
        result = judge._parse_judge_response("t1", raw, 0.001)
        conf = result["scores"]["confidence"]
        assert 0.0 <= conf < 1.0  # should be below 1.0

    def test_moderate_agreement_mid_confidence(self):
        judge = self._get_judge()
        raw = json.dumps({"completeness": 3, "relevance": 4, "factual_consistency": 4, "reasoning": ""})
        result = judge._parse_judge_response("t1", raw, 0.001)
        conf = result["scores"]["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_get_summary_includes_confidence_avg(self):
        judge = self._get_judge()
        # Manually inject results
        judge.results = [
            {
                "task_id": "t1",
                "skipped": False,
                "scores": {
                    "completeness": 4,
                    "relevance": 4,
                    "factual_consistency": 4,
                    "overall": 4.0,
                    "confidence": 0.9,
                },
                "cost_usd": 0.001,
            }
        ]
        summary = judge.get_summary()
        assert "confidence" in summary["avg_scores"]
        assert summary["avg_scores"]["confidence"] == 0.9

    def test_confidence_bounded_zero_to_one(self):
        judge = self._get_judge()
        for c, r, f in [(0, 0, 0), (5, 5, 5), (0, 5, 0), (1, 1, 5)]:
            raw = json.dumps({"completeness": c, "relevance": r, "factual_consistency": f, "reasoning": ""})
            result = judge._parse_judge_response("t1", raw, 0.001)
            conf = result["scores"]["confidence"]
            assert 0.0 <= conf <= 1.0, f"confidence {conf} out of range for ({c},{r},{f})"


# ---------------------------------------------------------------------------
# P1-A: EvalDecorator._BATCH_PARAMS includes on_batch_complete
# ---------------------------------------------------------------------------
class TestBatchParamsOnBatchComplete:
    def test_on_batch_complete_in_batch_params(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "on_batch_complete" in EvalDecorator._BATCH_PARAMS

    def test_on_batch_complete_propagated_via_batch(self):
        """EvalDecorator.batch() should pass on_batch_complete to batch_eval()."""
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        collected: List[Any] = []

        def on_complete(results):
            collected.extend(results)

        eval_dec = EvalDecorator(monitor, framework="native")

        @eval_dec.batch(task_type="qa", on_batch_complete=on_complete)
        def agent(questions, ground_truths=None):
            return ["ok"] * len(questions)

        agent(questions=["Q1"], ground_truths=["A1"])
        # on_batch_complete should have been called with the task results
        assert len(collected) >= 1


# ---------------------------------------------------------------------------
# P2-A: AGENT_EVAL_PRESETS updated values
# ---------------------------------------------------------------------------
class TestAgentEvalPresetsUpdated:
    def test_production_has_llm_judge(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["production"].get("enable_llm_judge") is True

    def test_production_has_anomaly_detection(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["production"].get("enable_anomaly_detection") is True

    def test_testing_preset_sample_rate_01(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["testing"].get("sample_rate") == 0.1

    def test_testing_preset_flush_every_5(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["testing"].get("flush_every") == 5

    def test_canary_preset_sample_rate_005(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["canary"].get("sample_rate") == 0.05

    def test_canary_preset_has_anomaly_detection(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        assert AGENT_EVAL_PRESETS["canary"].get("enable_anomaly_detection") is True

    def test_all_presets_present(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        for key in ("production", "development", "testing", "canary"):
            assert key in AGENT_EVAL_PRESETS


# ---------------------------------------------------------------------------
# P2-B: agent_eval enable_quality_evaluation
# ---------------------------------------------------------------------------
class TestEnableQualityEvaluation:
    def test_agent_eval_accepts_enable_quality_evaluation(self):
        """agent_eval() should accept enable_quality_evaluation without error."""
        import inspect
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "enable_quality_evaluation" in sig.parameters

    def test_build_and_record_accepts_enable_quality_evaluation(self):
        """_build_and_record() should accept enable_quality_evaluation."""
        import inspect
        from agent_evaluator.decorators import _build_and_record
        sig = inspect.signature(_build_and_record)
        assert "enable_quality_evaluation" in sig.parameters

    def test_eval_decorator_accepts_enable_quality_evaluation(self):
        import inspect
        from agent_evaluator.decorators import EvalDecorator
        sig = inspect.signature(EvalDecorator.__init__)
        assert "enable_quality_evaluation" in sig.parameters

    def test_common_params_includes_enable_quality_evaluation(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "enable_quality_evaluation" in EvalDecorator._COMMON_PARAMS

    def test_agent_eval_with_quality_flag_runs(self):
        """Decorator with enable_quality_evaluation=True should run without error."""
        from agent_evaluator import PerformanceMonitor, agent_eval

        monitor = PerformanceMonitor(output_dir=None)

        @agent_eval(monitor, task_type="qa", enable_quality_evaluation=True)
        def fn(question, ground_truth=""):
            return "answer"

        result = fn(question="Q?", ground_truth="A")
        assert result is not None

    def test_eval_decorator_propagates_quality_flag(self):
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        monitor = PerformanceMonitor(output_dir=None)
        dec = EvalDecorator(monitor, enable_quality_evaluation=True)
        assert dec._defaults.get("enable_quality_evaluation") is True


# ---------------------------------------------------------------------------
# P3-A: Haystack component type detection + token extraction
# ---------------------------------------------------------------------------
class TestHaystackAdapterEnhanced:
    def _get_extractor(self):
        from agent_evaluator.decorators import _extract_haystack_metadata
        return _extract_haystack_metadata

    def test_retriever_component_type_detected(self):
        extractor = self._get_extractor()
        raw = {"retriever": {"documents": [{"content": "text"}]}}
        result = extractor(raw)
        assert result is not None
        assert result.chain_steps[0]["type"] == "retriever"

    def test_generator_component_type_detected(self):
        extractor = self._get_extractor()
        raw = {"llm_generator": {"replies": ["answer text"]}}
        result = extractor(raw)
        assert result is not None
        assert result.chain_steps[0]["type"] == "generator"

    def test_unknown_component_type_fallback(self):
        extractor = self._get_extractor()
        raw = {"mystery_component": {"data": "value"}}
        result = extractor(raw)
        assert result is not None
        assert result.chain_steps[0]["type"] == "component"

    def test_type_field_in_chain_step(self):
        extractor = self._get_extractor()
        raw = {"my_retriever": {"documents": []}, "my_generator": {"replies": ["hi"]}}
        result = extractor(raw)
        assert result is not None
        types = {step["name"]: step["type"] for step in result.chain_steps}
        assert types["my_retriever"] == "retriever"
        assert types["my_generator"] == "generator"

    def test_token_extraction_from_meta_usage(self):
        extractor = self._get_extractor()

        class FakeDoc:
            def __init__(self):
                self.meta = {"usage": {"total_tokens": 100, "prompt_tokens": 60, "completion_tokens": 40}}

        raw = {"generator": {"replies": [FakeDoc()]}}
        result = extractor(raw)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["total"] == 100

    def test_no_token_extraction_without_usage(self):
        extractor = self._get_extractor()
        raw = {"retriever": {"documents": [{"content": "text"}]}}
        result = extractor(raw)
        assert result is not None
        assert result.tokens_used is None

    def test_embedder_type_detected(self):
        extractor = self._get_extractor()
        raw = {"text_embedder": {"embedding": [0.1, 0.2]}}
        result = extractor(raw)
        assert result is not None
        assert result.chain_steps[0]["type"] == "embedder"


# ---------------------------------------------------------------------------
# P3-A: HuggingFace token estimation
# ---------------------------------------------------------------------------
class TestHuggingFaceAdapterTokenEstimation:
    def _get_extractor(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata
        return _extract_huggingface_metadata

    def test_pipeline_output_token_estimation(self):
        extractor = self._get_extractor()
        # Single-item pipeline output with text
        text = "A" * 400  # 400 chars → ~100 tokens
        raw = [{"generated_text": text}]
        result = extractor(raw)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used.get("estimated") is True
        assert result.tokens_used.get("total", 0) > 0

    def test_pipeline_output_creates_chain_steps(self):
        extractor = self._get_extractor()
        raw = [{"generated_text": "Hello world"}, {"generated_text": "Bye world"}]
        result = extractor(raw)
        assert result is not None
        assert len(result.chain_steps) == 2

    def test_generate_dict_with_input_ids_token_count(self):
        extractor = self._get_extractor()
        # Simulate generate() dict with input_ids and sequences
        raw = {
            "input_ids": [[1, 2, 3, 4, 5]],  # 5 input tokens
            "sequences": [[1, 2, 3, 4, 5, 6, 7, 8]],  # 8 total → 3 output tokens
        }
        result = extractor(raw)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 5
        assert result.tokens_used["output"] == 3
        assert result.tokens_used["total"] == 8

    def test_agents_logs_token_estimation(self):
        extractor = self._get_extractor()

        class FakeAgent:
            logs = ["Step 1: " + "x" * 200, "Step 2: " + "y" * 200]
            tool_calls = []

        result = extractor(FakeAgent())
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used.get("estimated") is True
        assert result.tokens_used.get("total", 0) > 0


# ---------------------------------------------------------------------------
# P1-C: get_result() tasks[] includes new fields
# ---------------------------------------------------------------------------
class TestGetResultTaskFields:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        payload = {
            "report": {
                "total_tasks": 1,
                "successful_tasks": 1,
                "task_completion_rate": 1.0,
                "accuracy_metrics": {},
                "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                "token_metrics": {"total_tokens": 100, "total_cost": 0.001},
                "quality_metrics": {},
                "agentic_metrics": {},
                "security_metrics": {},
            },
            "tasks": [{
                "task_id": "t1",
                "task_type": "qa",
                "success": True,
                "completion_score": 1.0,
                "accuracy_score": 0.9,
                "execution_time": 1.0,
                "tokens_used": 50,
                "tool_calls": [],
                "attempts": 1,
                "errors": [],
                "timestamp": "2026-01-01T00:00:00",
                "advanced_metrics": {"quality_dimensions": {"clarity": 4}},
            }],
            "metadata": {"version": "0.7.2", "name": "test_eval"},
        }
        (tmp_path / "test_eval.json").write_text(json.dumps(payload))
        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_tasks_include_chain_steps_field(self, client):
        resp_list = client.get("/api/results").json()
        files = resp_list.get("files", resp_list) if isinstance(resp_list, dict) else resp_list
        if not files:
            pytest.skip("no files")
        file_id = files[0]["id"]
        resp = client.get(f"/api/results/{file_id}")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) >= 1
        # chain_steps key should be present (may be None)
        assert "chain_steps" in tasks[0]

    def test_tasks_include_quality_dimensions_field(self, client):
        resp_list = client.get("/api/results").json()
        files = resp_list.get("files", resp_list) if isinstance(resp_list, dict) else resp_list
        if not files:
            pytest.skip("no files")
        file_id = files[0]["id"]
        resp = client.get(f"/api/results/{file_id}")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert "quality_dimensions" in tasks[0]
        # We stored quality_dimensions in advanced_metrics
        assert tasks[0]["quality_dimensions"] == {"clarity": 4}

    def test_tasks_include_streaming_metadata_field(self, client):
        resp_list = client.get("/api/results").json()
        files = resp_list.get("files", resp_list) if isinstance(resp_list, dict) else resp_list
        if not files:
            pytest.skip("no files")
        file_id = files[0]["id"]
        resp = client.get(f"/api/results/{file_id}")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        # streaming_metadata should be present (None if no ttft/chunk_count)
        assert "streaming_metadata" in tasks[0]


# ---------------------------------------------------------------------------
# P2-C: /quality-heatmap endpoint
# ---------------------------------------------------------------------------
class TestQualityHeatmapEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        payload = {
            "report": {
                "total_tasks": 4,
                "successful_tasks": 3,
                "task_completion_rate": 0.75,
                "accuracy_metrics": {},
                "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                "token_metrics": {"total_tokens": 200, "total_cost": 0.002},
                "quality_metrics": {},
                "agentic_metrics": {},
                "security_metrics": {},
            },
            "tasks": [
                {"task_id": f"t{i}", "task_type": ["qa", "code", "qa", "code"][i],
                 "success": True, "completion_score": 0.8, "accuracy_score": [0.9, 0.5, 0.7, 0.3][i],
                 "execution_time": 1.0, "tokens_used": 50, "tool_calls": [], "attempts": 1,
                 "errors": [], "timestamp": "2026-01-01T00:00:00", "framework": "native",
                 "advanced_metrics": {}}
                for i in range(4)
            ],
            "metadata": {"version": "0.7.2", "name": "heatmap_test"},
        }
        (tmp_path / "heatmap_test.json").write_text(json.dumps(payload))
        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_quality_heatmap_200(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/quality-heatmap")
        assert r.status_code == 200

    def test_quality_heatmap_structure(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/quality-heatmap").json()
        assert "groups" in data
        assert "bucket_labels" in data
        assert "matrix" in data
        assert len(data["bucket_labels"]) == 5

    def test_quality_heatmap_group_by_task_type(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/quality-heatmap?group_by=task_type").json()
        assert "qa" in data["groups"] or "code" in data["groups"]

    def test_quality_heatmap_group_by_framework(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/quality-heatmap?group_by=framework").json()
        assert data["group_by"] == "framework"

    def test_quality_heatmap_invalid_metric_422(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/quality-heatmap?metric=invalid_metric")
        assert r.status_code == 422

    def test_quality_heatmap_invalid_group_by_422(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        r = client.get(f"/api/results/{fid}/quality-heatmap?group_by=invalid_group")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# P2-C: /frameworks endpoint enhanced fields
# ---------------------------------------------------------------------------
class TestFrameworksEndpointEnhanced:
    @pytest.fixture
    def client(self, tmp_path):
        from agent_evaluator.serve.server import create_app
        from starlette.testclient import TestClient

        payload = {
            "report": {
                "total_tasks": 2,
                "successful_tasks": 2,
                "task_completion_rate": 1.0,
                "accuracy_metrics": {},
                "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
                "token_metrics": {"total_tokens": 200, "total_cost": 0.002},
                "quality_metrics": {},
                "agentic_metrics": {},
                "security_metrics": {},
            },
            "tasks": [
                {"task_id": "t1", "task_type": "qa", "success": True, "completion_score": 0.9,
                 "accuracy_score": 0.85, "execution_time": 1.0, "tokens_used": {"total": 50},
                 "tool_calls": ["tool1"], "attempts": 1, "errors": [],
                 "timestamp": "2026-01-01T00:00:00", "framework": "langchain", "advanced_metrics": {}},
                {"task_id": "t2", "task_type": "qa", "success": True, "completion_score": 0.8,
                 "accuracy_score": 0.75, "execution_time": 2.0, "tokens_used": {"total": 80},
                 "tool_calls": [], "attempts": 1, "errors": [],
                 "timestamp": "2026-01-01T00:00:00", "framework": "langchain", "advanced_metrics": {}},
            ],
            "metadata": {"version": "0.7.2", "name": "fw_test"},
        }
        (tmp_path / "fw_test.json").write_text(json.dumps(payload))
        app = create_app(results_dir=tmp_path, watch=False, offline=False)
        return TestClient(app, raise_server_exceptions=False)

    def test_frameworks_has_avg_completion(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/frameworks").json()
        fw = data["frameworks"]
        assert "langchain" in fw
        assert "avg_completion" in fw["langchain"]

    def test_frameworks_has_error_rate(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/frameworks").json()
        fw = data["frameworks"]
        assert "langchain" in fw
        assert "error_rate" in fw["langchain"]

    def test_frameworks_has_avg_tool_calls(self, client):
        files = client.get("/api/results").json().get("files", [])
        if not files:
            pytest.skip("no files")
        fid = files[0]["id"]
        data = client.get(f"/api/results/{fid}/frameworks").json()
        fw = data["frameworks"]
        assert "langchain" in fw
        assert "avg_tool_calls" in fw["langchain"]
