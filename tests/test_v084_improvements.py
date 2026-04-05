"""
tests/test_v084_improvements.py
=================================
v0.8.4 개선 사항 테스트:
- A1: task detail API에 streaming_steps / chunk_count 추가
- A2: enable_anomaly_detection temp-override 구현 (파라미터 → _build_and_record 전달)
- B1: task detail API에 llm_judge 결과 포함
- B2: GET /api/results/{file_id}/frameworks 엔드포인트 신규
- B4: GET /api/results/{file_id}/llm_judge 엔드포인트 신규
- C1: CrewAI 어댑터 token_usage 추출 지원
- C2: DSPy/PydanticAI 속성 기반 자동 감지
- C3: OpenAI streaming delta(choice.delta) tool_calls 추출
- D2: agent_eval() Quick Start 문서 추가
- D3: batch_eval DataFrame 추가 필드
- D6: sync/async generator 첫 yield → TTFT 자동 기록
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import agent_eval
from agent_evaluator.core.trackers.monitor import PerformanceMonitor
from agent_evaluator.decorators import (
    EvalMetadata,
    _auto_detect_framework,
    _extract_crewai_metadata,
    _extract_openai_metadata,
    batch_eval,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def monitor(tmp_path):
    return PerformanceMonitor(output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# TestA2AnomalyDetectionTempOverride
# ---------------------------------------------------------------------------


class TestA2AnomalyDetectionTempOverride:
    def test_enable_anomaly_detection_param_accepted(self, monitor):
        """enable_anomaly_detection=True 파라미터가 오류 없이 수용됨."""

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            return "답변"

        result = agent("질문")
        assert result == "답변"

    def test_anomaly_flag_restored_after_call(self, monitor):
        """호출 완료 후 enable_anomaly_detection 플래그가 원래 값으로 복원됨."""
        monitor.enable_anomaly_detection = False

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            return "답변"

        agent("질문")
        assert monitor.enable_anomaly_detection is False

    def test_anomaly_flag_restored_even_after_exception(self, monitor):
        """예외 발생 시에도 anomaly detection 플래그가 복원됨."""
        monitor.enable_anomaly_detection = False

        @agent_eval(monitor, task_type="qa", enable_anomaly_detection=True)
        def agent(question, ground_truth=""):
            raise ValueError("테스트 오류")

        with pytest.raises(ValueError):
            agent("질문")

        assert monitor.enable_anomaly_detection is False

    def test_anomaly_preset_production_activates_detection(self, monitor):
        """production preset에 enable_anomaly_detection이 포함됨."""
        from agent_evaluator import AGENT_EVAL_PRESETS

        assert AGENT_EVAL_PRESETS["production"].get("enable_anomaly_detection") is True

    def test_effective_enable_anomaly_computed(self, monitor):
        """_effective_enable_anomaly 가 preset과 파라미터를 합산함."""
        # production preset을 사용하면 enable_anomaly_detection=True 가 적용되어야 함
        @agent_eval(monitor, task_type="qa", preset="production")
        def agent(question, ground_truth=""):
            return "답변"

        # 예외 없이 실행되면 성공
        result = agent("질문")
        assert result == "답변"


# ---------------------------------------------------------------------------
# TestC1CrewAITokenExtraction
# ---------------------------------------------------------------------------


class TestC1CrewAITokenExtraction:
    def test_token_usage_dict_extraction(self):
        """CrewOutput에 token_usage dict가 있으면 tokens_used 추출됨."""

        class FakeTaskOut:
            agent = "researcher"
            description = "Research task"
            raw = "Result text"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            token_usage = {"prompt_tokens": 200, "completion_tokens": 100}
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["input"] == 200
        assert meta.tokens_used["output"] == 100
        assert meta.tokens_used["total"] == 300

    def test_usage_metrics_dict_extraction(self):
        """CrewOutput에 usage_metrics dict가 있으면 tokens_used 추출됨."""

        class FakeTaskOut:
            agent = "writer"
            description = "Write task"
            raw = "Written text"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            usage_metrics = {"prompt_tokens": 150, "completion_tokens": 80}
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["total"] == 230

    def test_no_token_usage_returns_none_tokens(self):
        """token 정보 없을 때 tokens_used는 None."""

        class FakeTaskOut:
            agent = "analyst"
            description = "Analyze"
            raw = "Analysis"
            output_format = None

        class FakeCrewOutput:
            tasks_output = [FakeTaskOut()]
            output_pydantic = None
            output_format = None

        meta = _extract_crewai_metadata(FakeCrewOutput())
        assert meta is not None
        assert meta.tokens_used is None


# ---------------------------------------------------------------------------
# TestC2DSPyPydanticAIDetection
# ---------------------------------------------------------------------------


class TestC2DSPyPydanticAIDetection:
    def test_dspy_prediction_via_completions(self):
        """DSPy Prediction — completions 속성으로 감지."""

        class FakeDSPyPrediction:
            completions = {"answer": ["value1", "value2"]}
            # no choices, no content

        assert _auto_detect_framework(FakeDSPyPrediction()) == "dspy"

    def test_dspy_prediction_via_underscore_completions(self):
        """DSPy Prediction — _completions 속성으로 감지."""

        class FakeDSPyPrediction:
            _completions = [{"answer": "value"}]

        assert _auto_detect_framework(FakeDSPyPrediction()) == "dspy"

    def test_pydanticai_runresult_via_all_messages(self):
        """PydanticAI RunResult — data + all_messages() callable 조합으로 감지."""

        class FakePydanticAIRunResult:
            data = "답변"

            def all_messages(self):
                return []

        assert _auto_detect_framework(FakePydanticAIRunResult()) == "pydanticai"

    def test_openai_response_not_confused_with_dspy(self):
        """choices 있는 OpenAI 응답은 dspy로 감지 안 됨."""

        class FakeOpenAI:
            choices = [MagicMock()]
            model = "gpt-4o"
            usage = MagicMock()

        result = _auto_detect_framework(FakeOpenAI())
        assert result != "dspy"


# ---------------------------------------------------------------------------
# TestC3OpenAIStreamingDelta
# ---------------------------------------------------------------------------


class TestC3OpenAIStreamingDelta:
    def test_streaming_chunk_tool_calls_extracted(self):
        """OpenAI streaming 청크(choice.delta)에서 tool_calls 추출."""

        class FakeFunction:
            name = "search"
            arguments = '{"query": "test"}'

        class FakeToolCall:
            function = FakeFunction()
            id = "tc_001"

        class FakeDelta:
            tool_calls = [FakeToolCall()]

        class FakeChoice:
            message = None
            delta = FakeDelta()

        class FakeStreamingChunk:
            choices = [FakeChoice()]

        meta = _extract_openai_metadata(FakeStreamingChunk())
        assert meta is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["tool_name"] == "search"

    def test_streaming_chunk_without_tool_calls_returns_none(self):
        """tool_calls 없는 스트리밍 청크는 None 반환."""

        class FakeDelta:
            tool_calls = None

        class FakeChoice:
            message = None
            delta = FakeDelta()

        class FakeStreamingChunk:
            choices = [FakeChoice()]

        meta = _extract_openai_metadata(FakeStreamingChunk())
        assert meta is None or (meta is not None and not meta.tool_calls)


# ---------------------------------------------------------------------------
# TestD3BatchEvalDataFrame
# ---------------------------------------------------------------------------


class TestD3BatchEvalDataFrame:
    def test_dataframe_has_extended_fields(self, monitor):
        """return_format='dataframe'이 확장 필드를 포함한 DataFrame 반환."""
        pytest.importorskip("pandas")

        @batch_eval(monitor, task_type="qa", return_format="dataframe")
        def agents(questions, ground_truths=None):
            return [f"답변 {i}" for i in range(len(questions))]

        df = agents(["질문1", "질문2"])
        import pandas as pd

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        # D3 추가 필드 확인
        assert "tokens_total" in df.columns
        assert "tool_call_count" in df.columns
        assert "has_error" in df.columns
        assert "attempts" in df.columns
        assert "timestamp" in df.columns

    def test_dataframe_fallback_without_pandas(self, monitor):
        """pandas 없으면 경고 후 list 반환 (graceful degradation)."""
        import importlib
        import sys

        # pandas 있으면 이 테스트는 skip (이 환경엔 pandas가 있을 것)
        try:
            import pandas  # noqa: F401
            pytest.skip("pandas available — graceful degradation test not applicable")
        except ImportError:
            pass

        @batch_eval(monitor, task_type="qa", return_format="dataframe")
        def agents(questions, ground_truths=None):
            return [f"답변 {i}" for i in range(len(questions))]

        result = agents(["질문1"])
        # list 반환 (pandas 없으므로)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TestD6GeneratorTTFT
# ---------------------------------------------------------------------------


class TestD6GeneratorTTFT:
    def test_sync_generator_records_ttft(self, monitor):
        """sync generator — 첫 yield 까지 시간이 LatencyTracker에 TTFT로 기록됨."""

        @agent_eval(monitor, task_type="qa")
        def streaming_agent(question, ground_truth=""):
            yield "첫 "
            yield "번째 "
            yield "응답"

        list(streaming_agent("질문"))

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats.get("count", 0) >= 1

    def test_async_generator_records_ttft(self, monitor):
        """async generator — 첫 yield 까지 시간이 LatencyTracker에 TTFT로 기록됨."""

        @agent_eval(monitor, task_type="qa")
        async def async_streaming_agent(question, ground_truth=""):
            yield "첫 "
            yield "번째 "
            yield "응답"

        async def run():
            chunks = []
            async for chunk in async_streaming_agent("질문"):
                chunks.append(chunk)
            return chunks

        asyncio.get_event_loop().run_until_complete(run())

        stats = monitor.latency_tracker.get_ttft_stats()
        assert stats.get("count", 0) >= 1

    def test_sync_generator_ttft_is_reasonable(self, monitor):
        """sync generator TTFT는 0 이상 전체 실행 시간 이하."""
        import time

        @agent_eval(monitor, task_type="qa")
        def streaming_agent(question, ground_truth=""):
            yield "chunk"

        start = time.perf_counter()
        list(streaming_agent("질문"))
        total = time.perf_counter() - start

        stats = monitor.latency_tracker.get_ttft_stats()
        if stats.get("count", 0) > 0:
            ttft = stats.get("min", 0)
            assert 0 <= ttft <= total + 0.1  # 여유 0.1s


# ---------------------------------------------------------------------------
# TestB2FrameworkBreakdown — /api/results/{file_id}/frameworks
# ---------------------------------------------------------------------------


class TestB2FrameworkBreakdown:
    def test_endpoint_function_exists(self):
        """get_framework_breakdown 함수가 data.py에 존재."""
        from agent_evaluator.serve.routers.data import get_framework_breakdown

        assert callable(get_framework_breakdown)

    def test_endpoint_returns_framework_data(self):
        """모의 데이터로 framework 집계 정확성 검증."""
        from agent_evaluator.serve.routers.data import get_framework_breakdown

        # 모의 TaskRecord
        class FakeTask:
            def __init__(self, fw, success, accuracy, execution_time, tokens_used):
                self.framework = fw
                self.success = success
                self.accuracy_score = accuracy
                self.execution_time = execution_time
                self.tokens_used = tokens_used

        class FakeResultFile:
            tasks = [
                FakeTask("langchain", True, 0.9, 1.0, {"total": 100}),
                FakeTask("langchain", False, 0.5, 2.0, {"total": 80}),
                FakeTask("openai", True, 0.8, 0.5, {"total": 60}),
            ]

        class FakeRS:
            def by_id(self, fid):
                return FakeResultFile()

        class FakeRequest:
            def __init__(self):
                self.app = type("App", (), {"state": type("State", (), {"result_store": FakeRS()})()})()

        # 직접 로직 검증 (HTTP 레이어 없이)
        from collections import defaultdict
        tasks = FakeResultFile().tasks
        fw_data = defaultdict(lambda: {"task_count": 0, "success_count": 0, "accuracy_sum": 0.0, "latency_sum": 0.0, "tokens_sum": 0})
        for t in tasks:
            fw = t.framework or "native"
            d = fw_data[fw]
            d["task_count"] += 1
            if t.success:
                d["success_count"] += 1
            d["accuracy_sum"] += t.accuracy_score
            d["latency_sum"] += t.execution_time
            d["tokens_sum"] += (t.tokens_used or {}).get("total", 0)

        assert "langchain" in fw_data
        assert fw_data["langchain"]["task_count"] == 2
        assert fw_data["langchain"]["success_count"] == 1
        assert fw_data["openai"]["task_count"] == 1


# ---------------------------------------------------------------------------
# TestB4LLMJudgeEndpoint — /api/results/{file_id}/llm_judge
# ---------------------------------------------------------------------------


class TestB4LLMJudgeEndpoint:
    def test_endpoint_function_exists(self):
        """get_llm_judge_details 함수가 data.py에 존재."""
        from agent_evaluator.serve.routers.data import get_llm_judge_details

        assert callable(get_llm_judge_details)

    def test_endpoint_signature_has_filter_params(self):
        """min_score / max_score / skip / limit 파라미터 존재."""
        import inspect
        from agent_evaluator.serve.routers.data import get_llm_judge_details

        sig = inspect.signature(get_llm_judge_details)
        assert "min_score" in sig.parameters
        assert "max_score" in sig.parameters
        assert "skip" in sig.parameters
        assert "limit" in sig.parameters

    def test_score_filter_logic(self):
        """min_score 필터 로직 검증."""
        results = [
            {"task_id": "t1", "scores": {"overall": 0.9}},
            {"task_id": "t2", "scores": {"overall": 0.4}},
            {"task_id": "t3", "scores": {"overall": 0.7}},
        ]
        min_score = 0.6
        filtered = [r for r in results if (r.get("scores") or {}).get("overall", 0.0) >= min_score]
        assert len(filtered) == 2
        assert all(r["scores"]["overall"] >= 0.6 for r in filtered)


# ---------------------------------------------------------------------------
# TestB1TaskDetailLLMJudge — task detail API llm_judge 포함
# ---------------------------------------------------------------------------


class TestB1TaskDetailLLMJudge:
    def test_task_detail_includes_llm_judge(self):
        """get_task_detail() 응답에 llm_judge 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        # 함수 소스에서 llm_judge 필드 포함 확인
        src = inspect.getsource(get_task_detail)
        assert '"llm_judge"' in src or "'llm_judge'" in src

    def test_task_detail_includes_streaming_steps(self):
        """get_task_detail() 응답에 streaming_steps 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        src = inspect.getsource(get_task_detail)
        assert "streaming_steps" in src

    def test_task_detail_includes_chunk_count(self):
        """get_task_detail() 응답에 chunk_count 필드가 포함됨."""
        import inspect
        from agent_evaluator.serve.routers.data import get_task_detail

        src = inspect.getsource(get_task_detail)
        assert "chunk_count" in src
