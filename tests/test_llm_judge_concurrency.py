"""
tests/test_llm_judge_concurrency.py
====================================
SPEC-006 (LLM Judge 동시성 및 백오프) 검증 테스트.

대상:
  - REQ-1: ``asyncio.Semaphore(max_concurrent_judge_calls)`` — ``ajudge()`` 를 통한
    동시 judge 호출 수 상한.
  - REQ-2: provider rate-limit(429) 예외 시 지수 백오프(1s, 2s, 4s) 재시도, 최대
    ``max_retries`` 회. 소진 시 기존과 동일하게 예외 전파.
  - REQ-3: ``@agent_eval`` 의 ``is_async=True`` 경로에서 동기 ``judge()`` 대신
    ``ajudge()`` 를 사용하도록 배선(``decorators.py``)했는지 — sync/async 양쪽에서
    동일한 채점 로직(동일 입력 → 동일 출력)을 거치는지 회귀 검증.
  - REQ-4: ``batch_eval`` 의 옵트인 동시 judge 처리(``concurrent_judge=True``) —
    기본값(``False``)은 기존과 동일하게 순차 처리.

Provider(anthropic/openai) 네트워크 호출은 전부 mock 처리하며, 실제 API 키를
요구하지 않는다.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, Optional
from unittest.mock import patch

import httpx
import pytest

from agent_evaluator import PerformanceMonitor, agent_eval, batch_eval
from agent_evaluator.integrations.llm_judge import LLMJudge, _is_rate_limit_error


def _make_scores(overall: float = 4.0) -> Dict[str, Any]:
    return {
        "completeness": int(overall),
        "relevance": int(overall),
        "factual_consistency": int(overall),
        "toxicity": 0,
        "bias": 0,
        "safety_score": 1.0,
        "overall": overall,
        "confidence": 0.9,
    }


def _fake_judge_result(task_id: str, model: str, overall: float = 4.0) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "skipped": False,
        "scores": _make_scores(overall),
        "reasoning": "ok",
        "model": model,
        "model_snapshot": model,
        "cost_usd": 0.0001,
    }


# ---------------------------------------------------------------------------
# REQ-2: rate-limit 예외 판별
# ---------------------------------------------------------------------------

class TestIsRateLimitError:
    def test_anthropic_rate_limit_error_detected(self):
        resp = httpx.Response(
            status_code=429,
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        )
        import anthropic
        exc = anthropic.RateLimitError("rate limited", response=resp, body=None)
        assert _is_rate_limit_error(exc) is True

    def test_openai_rate_limit_error_detected(self):
        resp = httpx.Response(
            status_code=429,
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )
        import openai
        exc = openai.RateLimitError("rate limited", response=resp, body=None)
        assert _is_rate_limit_error(exc) is True

    def test_generic_status_code_429_fallback(self):
        class FakeProviderError(Exception):
            status_code = 429

        assert _is_rate_limit_error(FakeProviderError("too many requests")) is True

    def test_classname_fallback(self):
        class SomeVendorRateLimitError(Exception):
            pass

        assert _is_rate_limit_error(SomeVendorRateLimitError("slow down")) is True

    def test_non_rate_limit_exception_not_detected(self):
        assert _is_rate_limit_error(ValueError("bad input")) is False
        assert _is_rate_limit_error(ConnectionError("network down")) is False


# ---------------------------------------------------------------------------
# REQ-2: _call_with_retry — 지수 백오프
# ---------------------------------------------------------------------------

class TestCallWithRetryBackoff:
    def test_succeeds_after_retries_within_limit(self, monkeypatch):
        """429가 max_retries 이내로 몇 차례 발생한 뒤 성공하면 결과를 반환한다."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_retries=3)
        monkeypatch.setattr(time, "sleep", lambda _s: None)  # 테스트 시간 단축

        calls = {"n": 0}

        class FakeRateLimit(Exception):
            status_code = 429

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise FakeRateLimit("429")
            return "success"

        result = judge._call_with_retry(flaky)
        assert result == "success"
        assert calls["n"] == 3

    def test_exhausts_retries_then_propagates(self, monkeypatch):
        """max_retries를 초과해 계속 429가 발생하면 기존과 동일하게 예외가 전파된다."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_retries=3)
        monkeypatch.setattr(time, "sleep", lambda _s: None)

        calls = {"n": 0}

        class FakeRateLimit(Exception):
            status_code = 429

        def always_fails():
            calls["n"] += 1
            raise FakeRateLimit("429")

        with pytest.raises(FakeRateLimit):
            judge._call_with_retry(always_fails)
        # 최초 시도 1회 + 재시도 3회 = 총 4회 호출
        assert calls["n"] == 4

    def test_non_rate_limit_exception_raised_immediately_without_retry(self, monkeypatch):
        """rate-limit이 아닌 예외는 재시도 없이 즉시 전파된다 (기존 동작과 동일)."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_retries=3)
        monkeypatch.setattr(time, "sleep", lambda _s: None)

        calls = {"n": 0}

        def raises_value_error():
            calls["n"] += 1
            raise ValueError("not a rate limit")

        with pytest.raises(ValueError):
            judge._call_with_retry(raises_value_error)
        assert calls["n"] == 1  # 재시도 없음

    def test_backoff_delays_are_exponential(self, monkeypatch):
        """1s, 2s, 4s 간격으로 재시도되는지 실제 sleep 인자를 기록해 검증한다."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_retries=3)
        recorded_delays = []
        monkeypatch.setattr(time, "sleep", lambda s: recorded_delays.append(s))

        class FakeRateLimit(Exception):
            status_code = 429

        calls = {"n": 0}

        def always_fails():
            calls["n"] += 1
            raise FakeRateLimit("429")

        with pytest.raises(FakeRateLimit):
            judge._call_with_retry(always_fails)

        assert recorded_delays == [1, 2, 4]

    def test_call_judge_claude_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        """통합 시나리오: _call_claude가 429를 반환하다 성공하면 정상 결과를 반환한다."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_retries=3)
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        class FakeRateLimit(Exception):
            status_code = 429

        call_count = {"n": 0}

        class FakeMessage:
            def __init__(self):
                self.content = [type("C", (), {"text": '{"completeness":5,"relevance":5,"factual_consistency":5,"toxicity":0,"bias":0,"reasoning":"ok"}'})()]
                self.usage = type("U", (), {"input_tokens": 100, "output_tokens": 50})()
                self.model = "claude-haiku-4-5-20251001"

        class FakeMessages:
            def create(self, **kwargs):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    raise FakeRateLimit("429 rate limited — 5연속 시나리오 중 앞 2회")
                return FakeMessage()

        class FakeAnthropicClient:
            def __init__(self, api_key=None):
                self.messages = FakeMessages()

        import anthropic as anthropic_module
        monkeypatch.setattr(anthropic_module, "Anthropic", FakeAnthropicClient)

        result = judge._call_claude("t1", "질문", "응답", None)
        assert result.get("error") is None
        assert result["scores"]["overall"] == 5.0
        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# REQ-1: asyncio.Semaphore 동시성 제한
# ---------------------------------------------------------------------------

class TestSemaphoreConcurrencyLimit:
    @pytest.mark.asyncio
    async def test_ajudge_bounds_concurrency_to_max_concurrent_judge_calls(self):
        """max_concurrent_judge_calls=N 이면 동시에 진행 중인 judge 호출 수가 N을 넘지 않는다."""
        max_concurrent = 2
        judge = LLMJudge(
            model="claude-haiku-4-5-20251001",
            sample_rate=1.0,
            max_concurrent_judge_calls=max_concurrent,
        )

        state = {"current": 0, "max_seen": 0}
        lock = threading.Lock()

        def sync_judge(task_id, question, response, context=None):
            with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            time.sleep(0.08)
            with lock:
                state["current"] -= 1
            return _fake_judge_result(task_id, judge.model)

        judge.judge = sync_judge  # type: ignore[method-assign]

        results = await asyncio.gather(
            *(judge.ajudge(f"t{i}", "q", "r") for i in range(8))
        )

        assert state["max_seen"] <= max_concurrent
        assert state["max_seen"] > 1, "동시 실행이 전혀 없었다면 세마포어 테스트가 의미가 없음"
        assert len(results) == 8
        for r in results:
            assert r["scores"]["overall"] == 4.0

    @pytest.mark.asyncio
    async def test_default_max_concurrent_judge_calls_is_5(self):
        """LLMJudge() 기본값은 5여야 한다 (하위호환 — 인터페이스 명시값)."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        assert judge.max_concurrent_judge_calls == 5
        assert judge.max_retries == 3

    @pytest.mark.asyncio
    async def test_unbounded_calls_do_not_exceed_higher_limit(self):
        """max_concurrent_judge_calls=4로 설정하면 5개 동시 호출도 4를 넘지 않는다."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0, max_concurrent_judge_calls=4)

        state = {"current": 0, "max_seen": 0}
        lock = threading.Lock()

        def sync_judge(task_id, question, response, context=None):
            with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            time.sleep(0.05)
            with lock:
                state["current"] -= 1
            return _fake_judge_result(task_id, judge.model)

        judge.judge = sync_judge  # type: ignore[method-assign]

        await asyncio.gather(*(judge.ajudge(f"t{i}", "q", "r") for i in range(5)))
        assert state["max_seen"] <= 4


# ---------------------------------------------------------------------------
# REQ-3: agent_eval 비동기 경로 — ajudge() 배선
# ---------------------------------------------------------------------------

class TestAsyncAgentEvalUsesAjudge(object):
    def _install_fake_call_judge(self, monkeypatch, call_log):
        def fake_call_judge(self, task_id, question, response, context, *, _model=None):
            call_log.append(threading.current_thread().name)
            return _fake_judge_result(task_id, self.model)

        monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)

    def test_sync_agent_eval_judges_on_calling_thread(self, monkeypatch, tmp_path):
        """회귀 방지: sync 경로는 변경 없이 호출 스레드에서 그대로 judge()가 실행된다."""
        call_log: list = []
        self._install_fake_call_judge(monkeypatch, call_log)

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "sync_out"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )

        @agent_eval(monitor, task_type="qa")
        def sync_agent(question: str, ground_truth: str = "") -> str:
            return "Seoul"

        sync_agent("What is the capital of Korea?", ground_truth="Seoul")

        assert len(call_log) == 1
        assert call_log[0] == threading.current_thread().name
        task = monitor.tasks[-1]
        assert task.llm_judge is not None
        assert task.llm_judge["scores"]["overall"] == 4.0

    @pytest.mark.asyncio
    async def test_async_agent_eval_uses_ajudge_off_main_thread(self, monkeypatch, tmp_path):
        """REQ-3: async 에이전트 경로는 ajudge()를 통해 별도 스레드에서 judge를 수행한다."""
        call_log: list = []
        self._install_fake_call_judge(monkeypatch, call_log)

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "async_out"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )

        @agent_eval(monitor, task_type="qa")
        async def async_agent(question: str, ground_truth: str = "") -> str:
            await asyncio.sleep(0.01)
            return "Seoul"

        await async_agent("What is the capital of Korea?", ground_truth="Seoul")

        assert len(call_log) == 1
        # ajudge()는 run_in_executor를 통해 별도 워커 스레드에서 judge를 실행하므로
        # 메인(테스트) 스레드와 다른 스레드 이름이 기록되어야 한다.
        assert call_log[0] != threading.current_thread().name
        task = monitor.tasks[-1]
        assert task.llm_judge is not None
        assert task.llm_judge["scores"]["overall"] == 4.0

    @pytest.mark.asyncio
    async def test_sync_and_async_paths_produce_equivalent_scoring(self, monkeypatch, tmp_path):
        """REQ-3 Acceptance: 동일 입력 → 동일 출력 (동기/비동기 채점 로직 동등성)."""
        call_log: list = []
        self._install_fake_call_judge(monkeypatch, call_log)

        sync_monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "equiv_sync"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )
        async_monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "equiv_async"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )

        @agent_eval(sync_monitor, task_type="qa")
        def sync_agent(question: str, ground_truth: str = "") -> str:
            return "Seoul"

        @agent_eval(async_monitor, task_type="qa")
        async def async_agent(question: str, ground_truth: str = "") -> str:
            return "Seoul"

        sync_agent("What is the capital of Korea?", ground_truth="Seoul")
        await async_agent("What is the capital of Korea?", ground_truth="Seoul")

        sync_task = sync_monitor.tasks[-1]
        async_task = async_monitor.tasks[-1]
        assert sync_task.llm_judge["scores"] == async_task.llm_judge["scores"]
        assert sync_task.response == async_task.response == "Seoul"

    @pytest.mark.asyncio
    async def test_async_agent_eval_without_judge_enabled_unaffected(self, tmp_path):
        """judge 비활성 monitor에서는 REQ-3 배선이 아무 영향을 주지 않는다 (회귀 방지)."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path / "no_judge"))

        @agent_eval(monitor, task_type="qa")
        async def async_agent(question: str, ground_truth: str = "") -> str:
            return "Seoul"

        await async_agent("What is the capital of Korea?", ground_truth="Seoul")
        task = monitor.tasks[-1]
        assert task.llm_judge is None
        assert task.response == "Seoul"


# ---------------------------------------------------------------------------
# REQ-4: batch_eval 옵트인 동시 judge 처리
# ---------------------------------------------------------------------------

class TestBatchEvalConcurrentJudge:
    def _install_fake_call_judge(self, monkeypatch, state, lock, delay=0.05):
        def fake_call_judge(self, task_id, question, response, context, *, _model=None):
            with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            time.sleep(delay)
            with lock:
                state["current"] -= 1
            return _fake_judge_result(task_id, self.model)

        monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)

    @pytest.mark.asyncio
    async def test_default_sequential_behavior_unchanged(self, monkeypatch, tmp_path):
        """concurrent_judge 미지정(기본 False) 시 기존과 동일하게 순차 처리된다."""
        state = {"current": 0, "max_seen": 0}
        lock = threading.Lock()
        self._install_fake_call_judge(monkeypatch, state, lock, delay=0.03)

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "batch_default"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )

        @batch_eval(monitor, task_type="qa")
        async def async_batch(questions, ground_truths=None):
            await asyncio.sleep(0.005)
            return ["Seoul"] * len(questions)

        await async_batch(
            questions=[f"Q{i}" for i in range(5)],
            ground_truths=["Seoul"] * 5,
        )

        assert state["max_seen"] == 1  # 순차 처리 — 동시 진행 없음
        assert len(monitor.tasks) == 5
        for t in monitor.tasks:
            assert t.llm_judge is not None

    @pytest.mark.asyncio
    async def test_concurrent_judge_opt_in_bounds_by_semaphore(self, monkeypatch, tmp_path):
        """concurrent_judge=True이면 REQ-1 세마포어 한도 내에서 동시 judge 처리가 일어난다."""
        state = {"current": 0, "max_seen": 0}
        lock = threading.Lock()
        self._install_fake_call_judge(monkeypatch, state, lock, delay=0.05)

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "batch_concurrent"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )
        monitor.llm_judge.max_concurrent_judge_calls = 3

        @batch_eval(monitor, task_type="qa", concurrent_judge=True)
        async def async_batch(questions, ground_truths=None):
            await asyncio.sleep(0.005)
            return ["Seoul"] * len(questions)

        await async_batch(
            questions=[f"Q{i}" for i in range(9)],
            ground_truths=["Seoul"] * 9,
        )

        assert state["max_seen"] > 1, "동시 처리가 전혀 일어나지 않음"
        assert state["max_seen"] <= 3
        assert len(monitor.tasks) == 9
        for t in monitor.tasks:
            assert t.llm_judge is not None
            assert t.llm_judge["scores"]["overall"] == 4.0

    def test_concurrent_judge_opt_in_sync_batch_function(self, monkeypatch, tmp_path):
        """concurrent_judge=True는 동기(sync) 배치 함수에도 적용된다 (asyncio.run 경유)."""
        state = {"current": 0, "max_seen": 0}
        lock = threading.Lock()
        self._install_fake_call_judge(monkeypatch, state, lock, delay=0.05)

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path / "batch_concurrent_sync"),
            enable_llm_judge=True,
            judge_sample_rate=1.0,
            judge_model="claude-haiku-4-5-20251001",
        )
        monitor.llm_judge.max_concurrent_judge_calls = 3

        @batch_eval(monitor, task_type="qa", concurrent_judge=True)
        def sync_batch(questions, ground_truths=None):
            return ["Seoul"] * len(questions)

        sync_batch(
            questions=[f"Q{i}" for i in range(6)],
            ground_truths=["Seoul"] * 6,
        )

        assert state["max_seen"] > 1
        assert state["max_seen"] <= 3
        assert len(monitor.tasks) == 6
        for t in monitor.tasks:
            assert t.llm_judge is not None
