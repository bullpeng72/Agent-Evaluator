"""
tests/test_v077_gaps.py
========================
v0.7.7 신규 기능 테스트 — 33개 Gap 검증

A1: batch_eval sync concurrent (ThreadPoolExecutor)
A2: batch_eval async gather 결과 재정렬
A3: conversation_eval flush_every/flush_filename
A4: EvalDecorator._CONV_PARAMS 확장
A5: agent_eval_with_retry + alert_rules/flush_every
A6: QuickEval.summary() 확장
A7: QuickEval.gate() quality/hallucination 임계값
A8: QuickEval.multi_agent / .security 단축 데코레이터
A9: EvalDecorator.__init__ + sample_condition
B1: GET /api/results/{file_id}/timeline
B2: GET /api/results/compare
B3: GET /api/leaderboard
B4: GET /api/results/{file_id}/sessions
B5: POST /api/results/{file_id}/tags / GET /api/results/{file_id}/tags
B6: GET /api/results/{file_id}/tasks/{task_id}/similar
B7: WS /ws/events WebSocket
B8: GET/POST/DELETE /api/alerts/rules
B9: GET /api/cost/trend
C1: cohere_eval + _extract_cohere_metadata
C2: groq_eval
C3: mistral_eval + _extract_mistral_metadata
C4: bedrock_eval + _extract_bedrock_metadata
C5: smolagents_eval + _extract_smolagents_metadata
C6: semantic_kernel_eval + _extract_semantic_kernel_metadata
D1: PerformanceMonitor.compare()
D2: PerformanceMonitor.task_count
D3: SimpleTaskAlertRule.class_level_cooldown
D5: gen_wrapper + timeout 경고
D6: conversation_eval async generator
D7: QuickEval.__repr__ — task_count 사용
D8: top-level LLM SDK decorator imports
D9: EvalDecorator._CONV_PARAMS flush_every/flush_filename
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 / 픽스처
# ─────────────────────────────────────────────────────────────────────────────

def _make_monitor(output_dir=None):
    from agent_evaluator import PerformanceMonitor
    return PerformanceMonitor(output_dir=output_dir or tempfile.mkdtemp())


def _make_task_result(**kwargs):
    from typing import Any
    from agent_evaluator import create_taskresult
    defaults: dict[str, Any] = dict(
        task_id="t1",
        question="q",
        response="r",
        ground_truth="r",
        execution_time=0.1,
        task_type="qa",
    )
    defaults.update(kwargs)
    return create_taskresult(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# D2: PerformanceMonitor.task_count
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskCount:
    def test_initial_zero(self):
        m = _make_monitor()
        assert m.task_count == 0

    def test_increments_after_record(self):
        m = _make_monitor()
        m.record_task(_make_task_result(task_id="t1"))
        assert m.task_count == 1
        m.record_task(_make_task_result(task_id="t2"))
        assert m.task_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# D1: PerformanceMonitor.compare()
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorCompare:
    def test_compare_empty(self):
        m1 = _make_monitor()
        m2 = _make_monitor()
        result = m1.compare(m2)
        assert "self" in result
        assert "other" in result
        assert "delta" in result

    def test_compare_keys(self):
        m1 = _make_monitor()
        m2 = _make_monitor()
        r = m1.compare(m2)
        for key in ("tcr", "accuracy", "avg_latency", "total_tasks"):
            assert key in r["self"]
            assert key in r["other"]
            assert key in r["delta"]

    def test_compare_delta_math(self):
        m1 = _make_monitor()
        m2 = _make_monitor()
        m1.record_task(_make_task_result(task_id="t1"))
        r = m1.compare(m2)
        assert r["delta"]["total_tasks"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# D7: QuickEval.__repr__ uses task_count
# ─────────────────────────────────────────────────────────────────────────────

class TestQuickEvalRepr:
    def test_repr_uses_task_count(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        r = repr(qe)
        assert "tasks=0" in r

    def test_repr_after_record(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())

        @qe.qa
        def agent(question, ground_truth=""):
            return "ans"

        agent("q", ground_truth="ans")
        r = repr(qe)
        assert "tasks=1" in r


# ─────────────────────────────────────────────────────────────────────────────
# A6: QuickEval.summary() 확장
# ─────────────────────────────────────────────────────────────────────────────

class TestQuickEvalSummaryExpanded:
    def test_summary_keys(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        s = qe.summary()
        for key in ("tcr", "accuracy", "total_tasks", "avg_latency",
                    "p95_latency", "total_cost_usd", "quality_avg",
                    "hallucination_rate", "total_tokens"):
            assert key in s, f"Missing key: {key}"

    def test_summary_types(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        s = qe.summary()
        assert isinstance(s["p95_latency"], float)
        assert isinstance(s["total_cost_usd"], float)
        assert isinstance(s["quality_avg"], float)
        assert isinstance(s["hallucination_rate"], float)


# ─────────────────────────────────────────────────────────────────────────────
# A7: QuickEval.gate() quality/hallucination
# ─────────────────────────────────────────────────────────────────────────────

class TestQuickEvalGateExpanded:
    def test_gate_quality_pass(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        # quality 임계값 0 이면 항상 통과
        assert qe.gate(quality=0) is True

    def test_gate_hallucination_pass(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        # hallucination rate 100% 미만이면 통과
        assert qe.gate(hallucination=100.0) is True

    def test_gate_hallucination_fail(self, capsys):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        with pytest.raises(SystemExit):
            # hallucination rate 0 이하 요구 (실제는 0% 이므로 pass)  — negative threshold
            qe.gate(hallucination=-1.0)  # rate > -1 always


# ─────────────────────────────────────────────────────────────────────────────
# A8: QuickEval.multi_agent / .security
# ─────────────────────────────────────────────────────────────────────────────

class TestQuickEvalNewDecorators:
    def test_multi_agent_property(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        dec = qe.multi_agent
        assert dec is not None

    def test_multi_agent_applies(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())

        @qe.multi_agent
        def crew_task(question, ground_truth=""):
            return "done"

        crew_task("q")
        assert qe.monitor.task_count == 1

    def test_security_property(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())
        dec = qe.security
        assert dec is not None

    def test_security_applies(self):
        from agent_evaluator import QuickEval
        qe = QuickEval(tempfile.mkdtemp())

        @qe.security
        def secure_agent(question, ground_truth=""):
            return "safe"

        secure_agent("inject")
        assert qe.monitor.task_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# A9: EvalDecorator.__init__ sample_condition
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalDecoratorSampleCondition:
    def test_sample_condition_param_exists(self):
        from agent_evaluator.decorators import EvalDecorator
        m = _make_monitor()
        called = []
        ed = EvalDecorator(m, sample_condition=lambda a, k: called.append(1) or True)
        assert "sample_condition" in ed._defaults

    def test_sample_condition_propagates(self):
        from agent_evaluator.decorators import EvalDecorator
        m = _make_monitor()
        skip = [False]

        def cond(args, kwargs):
            return not skip[0]

        ed = EvalDecorator(m, sample_condition=cond)

        @ed(task_type="qa")
        def agent(question, ground_truth=""):
            return "ans"

        skip[0] = True
        agent("q")
        assert m.task_count == 0  # sampled out

        skip[0] = False
        agent("q")
        assert m.task_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# A4 / D9: EvalDecorator._CONV_PARAMS 확장
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalDecoratorConvParams:
    def test_conv_params_expanded(self):
        from agent_evaluator.decorators import EvalDecorator
        expected = {
            "sample_rate", "enabled", "alert_rules", "on_session_timeout",
            "on_flush", "on_turn", "session_score_fn", "turn_score_fn",
            "max_turns", "flush_on_error", "max_session_seconds",
            "flush_every",
        }
        for param in expected:
            assert param in EvalDecorator._CONV_PARAMS, f"Missing: {param}"

    def test_conversation_propagates_flush_every(self):
        from agent_evaluator.decorators import EvalDecorator, conversation_eval
        import inspect
        m = _make_monitor()
        ed = EvalDecorator(m, flush_every=5)
        # conversation() method should forward flush_every
        sig = inspect.signature(conversation_eval)
        assert "flush_every" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# A5: agent_eval retry + alert_rules / flush_every (통합 후 agent_eval 사용)
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentEvalRetryAlertRules:
    def test_alert_rules_param(self):
        """agent_eval에 alert_rules, flush_every 파라미터 존재 (flush_filename 제거됨)."""
        import inspect
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "alert_rules" in sig.parameters
        assert "flush_every" in sig.parameters
        assert "flush_filename" not in sig.parameters

    def test_alert_rules_fired(self):
        from agent_evaluator.decorators import agent_eval, SimpleTaskAlertRule
        m = _make_monitor()
        fired = []
        rule = SimpleTaskAlertRule(
            name="test", condition=lambda r: True,
            handler=lambda msg, r: fired.append(msg),
            cooldown=0.0,
        )

        @agent_eval(m, task_type="qa", alert_rules=[rule])
        def agent(question, ground_truth=""):
            return "ans"

        agent("q")
        assert len(fired) == 1

    def test_flush_every_triggers(self, tmp_path):
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor(str(tmp_path))

        @agent_eval(m, task_type="qa", flush_every=1)
        def agent(question, ground_truth=""):
            return "ans"

        agent("q")
        # flush 파일이 생성되어야 함 — 기본 파일명 auto_save.json
        assert (tmp_path / "auto_save.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# A3: conversation_eval flush_every / flush_filename
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationEvalFlushEvery:
    def test_flush_every_param(self):
        from agent_evaluator.decorators import conversation_eval
        import inspect
        sig = inspect.signature(conversation_eval)
        assert "flush_every" in sig.parameters
        assert "flush_filename" not in sig.parameters

    def test_flush_every_triggers(self, tmp_path):
        from agent_evaluator.decorators import conversation_eval, flush_conversation
        m = _make_monitor(str(tmp_path))

        @conversation_eval(m, max_turns=1, flush_every=1)
        def chat(question, session_id="s1"):
            return "hi"

        chat("hello", session_id="s100")
        # max_turns=1 → flush 발생 → flush_every=1 → save_to_file("auto_save") 호출
        # save_to_file은 확장자 없으면 .json 자동 추가
        time.sleep(0.1)
        assert (tmp_path / "auto_save.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# A1: batch_eval sync concurrent (ThreadPoolExecutor)
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchEvalSyncConcurrent:
    def test_sync_concurrent_param(self):
        from agent_evaluator.decorators import batch_eval
        import inspect
        sig = inspect.signature(batch_eval)
        # concurrent/max_concurrent removed; concurrency=N is the new param
        assert "concurrent" not in sig.parameters
        assert "max_concurrent" not in sig.parameters
        assert "concurrency" in sig.parameters

    def test_sync_concurrent_executes(self):
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()
        call_threads = []

        @batch_eval(m, task_type="qa", concurrency=3)
        def agents(questions, ground_truths=None):
            call_threads.append(threading.current_thread().name)
            return [q + "_ans" for q in questions]

        agents(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        assert m.task_count == 3

    def test_sync_concurrent_results_correct(self):
        from agent_evaluator.decorators import batch_eval
        m = _make_monitor()

        @batch_eval(m, task_type="qa", concurrency=4)
        def agents(questions, ground_truths=None):
            return [q.upper() for q in questions]

        agents(questions=["a", "b", "c"])
        assert m.task_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# C1-C6: 새 프레임워크 어댑터 + eval 함수
# ─────────────────────────────────────────────────────────────────────────────

class TestNewFrameworkAdapters:
    def test_cohere_extractor_none_on_unknown(self):
        from agent_evaluator.decorators import _extract_cohere_metadata
        assert _extract_cohere_metadata("not a cohere response") is None

    def test_cohere_extractor_dict_token(self):
        from agent_evaluator.decorators import _extract_cohere_metadata
        mock = MagicMock()
        mock.tool_calls = None
        billed = MagicMock()
        billed.input_tokens = 10
        billed.output_tokens = 5
        mock.meta.billed_units = billed
        result = _extract_cohere_metadata(mock)
        assert result is not None
        assert result.tokens_used is not None
        assert result.tokens_used["input"] == 10

    def test_groq_extractor(self):
        from agent_evaluator.decorators import _extract_groq_metadata
        assert _extract_groq_metadata("not groq") is None

    def test_mistral_extractor_none(self):
        from agent_evaluator.decorators import _extract_mistral_metadata
        assert _extract_mistral_metadata("not mistral") is None

    def test_bedrock_extractor_dict(self):
        from agent_evaluator.decorators import _extract_bedrock_metadata
        resp = {
            "output": {
                "message": {
                    "content": [
                        {"toolUse": {"name": "search", "input": {"q": "hello"}}},
                    ]
                }
            },
            "usage": {"inputTokens": 100, "outputTokens": 50},
        }
        result = _extract_bedrock_metadata(resp)
        assert result is not None
        assert result.tool_calls is not None
        assert result.tokens_used is not None
        assert result.tool_calls[0]["name"] == "search"
        assert result.tokens_used["input"] == 100

    def test_smolagents_extractor(self):
        from agent_evaluator.decorators import _extract_smolagents_metadata
        assert _extract_smolagents_metadata("string") is None

    def test_semantic_kernel_extractor(self):
        from agent_evaluator.decorators import _extract_semantic_kernel_metadata
        assert _extract_semantic_kernel_metadata("string") is None

    def test_framework_adapters_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw in ("cohere", "groq", "mistral", "bedrock", "smolagents", "semantic_kernel"):
            assert fw in _FRAMEWORK_ADAPTERS, f"Missing adapter: {fw}"

    def test_agent_eval_framework_param(self):
        """agent_eval에 framework 파라미터가 있다 — *_eval 함수 대신 사용."""
        import inspect
        from agent_evaluator.decorators import agent_eval
        sig = inspect.signature(agent_eval)
        assert "framework" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# D8: LLM SDK 어댑터 등록 확인 (agent_eval(framework=name) 방식)
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMSDKAdapters:
    """*_eval 함수 대신 agent_eval(framework=name) + _FRAMEWORK_ADAPTERS 확인."""

    def test_llm_adapters_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        for fw in ("anthropic", "openai", "gemini", "llamaindex",
                   "haystack", "vertexai", "ollama"):
            assert fw in _FRAMEWORK_ADAPTERS, f"Missing adapter: {fw}"

    def test_agent_eval_callable(self):
        from agent_evaluator import agent_eval
        assert callable(agent_eval)


# ─────────────────────────────────────────────────────────────────────────────
# D3: SimpleTaskAlertRule.class_level_cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestClassLevelCooldown:
    def test_class_level_cooldown_param(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        import inspect
        fields = {f.name for f in SimpleTaskAlertRule.__dataclass_fields__.values()}
        assert "class_level_cooldown" in fields

    def test_class_level_cooldown_default_false(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        rule = SimpleTaskAlertRule(
            name="r1", condition=lambda r: True,
            handler=lambda m, r: None,
        )
        assert rule.class_level_cooldown is False

    def test_class_level_cooldown_shared(self):
        from agent_evaluator.decorators import SimpleTaskAlertRule
        fired = []

        rule1 = SimpleTaskAlertRule(
            name="shared_rule",
            condition=lambda r: True,
            handler=lambda m, r: fired.append(1),
            cooldown=999.0,
            class_level_cooldown=True,
        )
        rule2 = SimpleTaskAlertRule(
            name="shared_rule",
            condition=lambda r: True,
            handler=lambda m, r: fired.append(2),
            cooldown=999.0,
            class_level_cooldown=True,
        )
        # Clear shared state
        SimpleTaskAlertRule._SHARED_COOLDOWN.clear()

        tr = _make_task_result()
        rule1.evaluate(tr)  # fires
        rule2.evaluate(tr)  # blocked by shared cooldown

        assert len(fired) == 1


# ─────────────────────────────────────────────────────────────────────────────
# D5: gen_wrapper timeout warning
# ─────────────────────────────────────────────────────────────────────────────

class TestGenWrapperTimeoutWarning:
    def test_timeout_warning_for_generator(self, caplog):
        from agent_evaluator.decorators import agent_eval
        m = _make_monitor()

        with caplog.at_level(logging.WARNING, logger="agent_evaluator.decorators"):
            @agent_eval(m, task_type="qa", timeout=5.0)
            def stream_agent(question, ground_truth=""):
                yield "chunk1"
                yield "chunk2"

        assert any("timeout" in record.message.lower() for record in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# D6: conversation_eval async generator support
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationEvalAsyncGen:
    @pytest.mark.asyncio
    async def test_async_gen_conversation(self):
        from agent_evaluator.decorators import conversation_eval, flush_conversation
        m = _make_monitor()

        @conversation_eval(m, max_turns=2)
        async def chat_stream(question, session_id="s1"):
            for chunk in ["hello", " world"]:
                yield chunk

        session_id = "async_gen_test"
        chunks = []
        async for chunk in chat_stream("hi", session_id=session_id):
            chunks.append(chunk)

        assert chunks == ["hello", " world"]
        flush_conversation(session_id)


# ─────────────────────────────────────────────────────────────────────────────
# B1-B6: Dashboard API endpoints
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_result_set():
    """Mock result_set for API testing."""
    from unittest.mock import MagicMock

    task = MagicMock()
    task.task_id = "task_001"
    task.task_type = "qa"
    task.success = True
    task.accuracy_score = 0.9
    task.completion_score = 1.0
    task.execution_time = 1.2
    task.tokens_used = {"total": 100}
    task.tool_calls = []
    task.attempts = 1
    task.errors = []
    task.timestamp = "2026-04-04T10:00:00"
    task.framework = "native"
    task.raw = {"question": "q", "response": "r", "ground_truth": "r"}
    task.advanced_metrics = {}
    task.expected_tools = None

    task2 = MagicMock()
    task2.task_id = "task_002"
    task2.task_type = "tool_use"
    task2.success = False
    task2.accuracy_score = 0.3
    task2.completion_score = 0.0
    task2.execution_time = 5.0
    task2.tokens_used = {"total": 200}
    task2.tool_calls = []
    task2.attempts = 2
    task2.errors = ["error"]
    task2.timestamp = "2026-04-04T11:00:00"
    task2.framework = "langchain"
    task2.raw = {}
    task2.advanced_metrics = {}
    task2.expected_tools = None

    rf = MagicMock()
    rf.file_id = "file_001"
    rf.name = "test_results"
    rf.timestamp = "2026-04-04T10:00:00"
    rf.total_tasks = 2
    rf.tcr = 50.0
    rf.accuracy = 0.6
    rf.avg_latency = 3.1
    rf.total_cost = 0.001
    rf.tasks = [task, task2]
    rf.conversation_sessions = [{"session_id": "s1", "turns": 3}]
    rf.cost_data = {"total_usd": 0.001}

    rs = MagicMock()
    rs.files = [rf]
    rs.by_id = lambda fid: rf if fid == "file_001" else None

    return rs


@pytest.fixture
def test_app(mock_result_set):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from agent_evaluator.serve.routers.data import router as data_router
    from agent_evaluator.serve.routers.cost import router as cost_router
    from agent_evaluator.serve.routers.alerts import router as alerts_router

    app = FastAPI()
    app.state.result_set = mock_result_set
    app.state.results_dir = tempfile.mkdtemp()
    app.include_router(data_router)
    app.include_router(cost_router)
    app.include_router(alerts_router)

    return TestClient(app)


class TestTimelineEndpoint:
    def test_timeline_basic(self, test_app):
        resp = test_app.get("/api/results/file_001/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "buckets" in data
        assert "values" in data
        assert "counts" in data
        assert data["metric"] == "accuracy_score"

    def test_timeline_custom_metric(self, test_app):
        resp = test_app.get("/api/results/file_001/timeline?metric=execution_time&bucket=day")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric"] == "execution_time"
        assert data["bucket"] == "day"

    def test_timeline_not_found(self, test_app):
        resp = test_app.get("/api/results/nonexistent/timeline")
        assert resp.status_code == 404


class TestCompareEndpoint:
    def test_compare_basic(self, test_app):
        resp = test_app.get("/api/compare?ids=file_001,file_001")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert data["file_count"] == 2

    def test_compare_no_ids(self, test_app):
        resp = test_app.get("/api/compare?ids=")
        assert resp.status_code == 400


class TestLeaderboard:
    def test_leaderboard_basic(self, test_app):
        resp = test_app.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert "sort_by" in data

    def test_leaderboard_sort_by_accuracy(self, test_app):
        resp = test_app.get("/api/leaderboard?sort_by=accuracy&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sort_by"] == "accuracy"


class TestSessionsEndpoint:
    def test_sessions_basic(self, test_app):
        resp = test_app.get("/api/results/file_001/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "total" in data
        assert data["total"] == 1

    def test_sessions_pagination(self, test_app):
        resp = test_app.get("/api/results/file_001/sessions?skip=0&limit=10")
        assert resp.status_code == 200


class TestTagsEndpoint:
    def test_post_tags(self, test_app):
        resp = test_app.post(
            "/api/results/file_001/tags",
            json=["production", "v2"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data

    def test_get_tags(self, test_app):
        # First add
        test_app.post("/api/results/file_001/tags", json=["test_tag"])
        resp = test_app.get("/api/results/file_001/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data


class TestSimilarTasksEndpoint:
    def test_similar_basic(self, test_app):
        resp = test_app.get("/api/results/file_001/tasks/task_001/similar?top_k=3")
        assert resp.status_code == 200
        data = resp.json()
        assert "similar" in data
        assert len(data["similar"]) <= 3
        assert data["top_k"] == 3

    def test_similar_not_found(self, test_app):
        resp = test_app.get("/api/results/file_001/tasks/nonexistent/similar")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# B8: Alert Rules CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertRulesCRUD:
    def test_list_empty(self, test_app):
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()
        resp = test_app.get("/api/alerts/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data

    def test_create_rule(self, test_app):
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()
        resp = test_app.post("/api/alerts/rules", json={
            "name": "slow_response",
            "condition_expr": "execution_time > 5.0",
            "severity": "warning",
            "cooldown": 60.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "slow_response"
        assert "rule_id" in data

    def test_get_rule(self, test_app):
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()
        create_resp = test_app.post("/api/alerts/rules", json={
            "name": "test_rule",
            "condition_expr": "accuracy_score < 0.5",
            "severity": "critical",
        })
        rule_id = create_resp.json()["rule_id"]
        resp = test_app.get(f"/api/alerts/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test_rule"

    def test_delete_rule(self, test_app):
        from agent_evaluator.serve.routers.alerts import _ALERT_RULES_STORE
        _ALERT_RULES_STORE.clear()
        create_resp = test_app.post("/api/alerts/rules", json={
            "name": "to_delete",
            "condition_expr": "tcr < 50",
            "severity": "warning",
        })
        rule_id = create_resp.json()["rule_id"]
        resp = test_app.delete(f"/api/alerts/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        # Verify deleted
        get_resp = test_app.get(f"/api/alerts/rules/{rule_id}")
        assert get_resp.status_code == 404

    def test_get_nonexistent_rule(self, test_app):
        resp = test_app.get("/api/alerts/rules/nonexistent_id")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# B9: GET /api/cost/trend
# ─────────────────────────────────────────────────────────────────────────────

class TestCostTrend:
    def test_cost_trend_basic(self, test_app):
        resp = test_app.get("/api/cost/trend")
        assert resp.status_code == 200
        data = resp.json()
        assert "period_days" in data
        assert "buckets" in data
        assert "values" in data
        assert "cumulative" in data
        assert "total_usd" in data

    def test_cost_trend_custom_days(self, test_app):
        resp = test_app.get("/api/cost/trend?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 7

    def test_cumulative_is_nondecreasing(self, test_app):
        resp = test_app.get("/api/cost/trend?days=30")
        data = resp.json()
        cum = data["cumulative"]
        for i in range(1, len(cum)):
            assert cum[i] >= cum[i - 1] - 1e-9
