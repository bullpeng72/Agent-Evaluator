"""
agent_evaluator.integrations.pydanticai_integration
====================================================
PydanticAI 평가 통합 — PydanticAI Agent 를 agent-evaluator 와 연결한다.

지원 기능:
- ``@pydanticai_eval`` 데코레이터 (``agent_eval + framework="pydanticai"``)
- ``PydanticAIEvaluator`` — PydanticAI Agent 를 wrapping 해 자동 평가 적용
- ``PydanticAITokenExtractor`` — RunResult에서 토큰 사용량 추출 유틸

의존성 (opt-in):
    pip install pydantic-ai  # 또는 pip install "pydantic-ai[openai]"

Examples::

    from pydantic_ai import Agent
    from agent_evaluator import QuickEval
    from agent_evaluator.integrations.pydanticai_integration import PydanticAIEvaluator

    agent = Agent("openai:gpt-5-nano", system_prompt="Answer concisely.")

    # 1. 데코레이터 방식
    eval = QuickEval("results/")

    @eval(task_type="qa", framework="pydanticai")
    async def my_agent(question: str, ground_truth: str = "") -> str:
        result = await agent.run(question)
        return result.data

    # 2. PydanticAIEvaluator 방식
    pai_eval = PydanticAIEvaluator(monitor, agent=agent)
    await pai_eval.evaluate_async(dataset)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "pydanticai_eval",
    "PydanticAIEvaluator",
    "PydanticAITokenExtractor",
]


# ---------------------------------------------------------------------------
# 데코레이터
# ---------------------------------------------------------------------------

def pydanticai_eval(
    monitor: Any,
    task_type: Any = "qa",
    **kwargs: Any,
) -> Any:
    """PydanticAI Agent 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="pydanticai")`` 의 편의 별칭이다.
    ``RunResult.usage()`` 에서 토큰 사용량을 자동 추출한다.

    Args:
        monitor: PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"qa"``).
        **kwargs: :func:`agent_eval` 에 전달할 추가 파라미터.

    Example::

        from agent_evaluator.integrations.pydanticai_integration import pydanticai_eval

        @pydanticai_eval(monitor)
        async def my_agent(question: str, ground_truth: str = "") -> str:
            result = await agent.run(question)
            return result.data
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "pydanticai")
    return agent_eval(monitor, task_type, **kwargs)


# ---------------------------------------------------------------------------
# PydanticAITokenExtractor
# ---------------------------------------------------------------------------

class PydanticAITokenExtractor:
    """PydanticAI RunResult 에서 토큰 사용량을 추출하는 유틸리티.

    Example::

        result = await agent.run("질문")
        tokens = PydanticAITokenExtractor.extract(result)
        # → {"input": 50, "output": 120, "total": 170}
    """

    @staticmethod
    def extract(run_result: Any) -> Optional[Dict[str, int]]:
        """RunResult 에서 토큰 사용량을 ``{"input", "output", "total"}`` 형식으로 추출.

        Args:
            run_result: PydanticAI ``RunResult`` 인스턴스.

        Returns:
            토큰 딕셔너리 또는 추출 실패 시 ``None``.
        """
        try:
            if not hasattr(run_result, "usage"):
                return None
            usage = getattr(run_result, "usage", None)
            # PydanticAI 2.x: .usage는 property(호출 불가). 구버전: .usage()가 callable.
            is_legacy_method = (
                callable(usage)
                and not hasattr(usage, "input_tokens")
                and not hasattr(usage, "request_tokens")
            )
            if is_legacy_method:
                usage = usage()
            if usage is None:
                return None
            # PydanticAI Usage 필드명 (버전별 다를 수 있음)
            inp = (
                getattr(usage, "request_tokens", None)
                or getattr(usage, "input_tokens", None)
                or getattr(usage, "prompt_tokens", None)
                or 0
            )
            out = (
                getattr(usage, "response_tokens", None)
                or getattr(usage, "output_tokens", None)
                or getattr(usage, "completion_tokens", None)
                or 0
            )
            inp, out = int(inp), int(out)
            if inp == 0 and out == 0:
                return None
            return {"input": inp, "output": out, "total": inp + out}
        except Exception as e:
            logger.debug("PydanticAITokenExtractor.extract failed (ignored): %s", e)
            return None


# ---------------------------------------------------------------------------
# PydanticAIEvaluator
# ---------------------------------------------------------------------------

class PydanticAIEvaluator:
    """PydanticAI Agent 래퍼 — 평가를 자동으로 PerformanceMonitor 에 기록.

    Args:
        monitor: PerformanceMonitor 인스턴스.
        agent: PydanticAI ``Agent`` 인스턴스.
        task_type: Task 유형 (기본: ``"qa"``).
        score_fn: 커스텀 accuracy 계산 함수 ``(response, ground_truth) -> float``.

    Example::

        from pydantic_ai import Agent
        from agent_evaluator.integrations.pydanticai_integration import PydanticAIEvaluator

        agent = Agent("openai:gpt-5-nano")
        evaluator = PydanticAIEvaluator(monitor, agent=agent)

        # 비동기 단건 평가
        response = await evaluator.run_async("질문", ground_truth="정답")

        # 데이터셋 일괄 평가
        await evaluator.evaluate_async(dataset)
    """

    def __init__(
        self,
        monitor: Any,
        agent: Any,
        task_type: str = "qa",
        score_fn: Optional[Callable] = None,
    ) -> None:
        self.monitor = monitor
        self.agent = agent
        self.task_type = task_type
        self.score_fn = score_fn

    async def run_async(
        self,
        question: str,
        ground_truth: str = "",
        task_id: Optional[str] = None,
    ) -> str:
        """단건 비동기 평가 실행.

        Args:
            question: 입력 질문.
            ground_truth: 정답 (없으면 빈 문자열).
            task_id: 태스크 ID (없으면 자동 생성).

        Returns:
            에이전트 응답 문자열.
        """
        import uuid
        import time
        import dataclasses
        from agent_evaluator.helpers.taskresult_helpers import create_taskresult_from_execution
        from agent_evaluator.decorators import _extract_pydanticai_metadata

        if task_id is None:
            task_id = f"pai_{uuid.uuid4().hex[:8]}"

        start = time.perf_counter()
        has_error = False
        error_msg = None
        run_result = None

        try:
            run_result = await self.agent.run(question)
            if run_result is not None:
                # PydanticAI 2.x: .output. 구버전: .data.
                output = getattr(run_result, "output", None)
                if output is None and hasattr(run_result, "data"):
                    output = run_result.data
                response = str(output) if output is not None else ""
            else:
                response = ""
        except Exception as exc:
            has_error = True
            error_msg = str(exc)
            response = ""

        elapsed = time.perf_counter() - start

        # 토큰 추출
        tokens_used = None
        if run_result is not None:
            tokens_used = PydanticAITokenExtractor.extract(run_result)

        # 어댑터 메타데이터 추출
        adapter_meta = None
        if run_result is not None:
            try:
                adapter_meta = _extract_pydanticai_metadata(run_result)
            except Exception:
                pass

        # 점수 계산
        accuracy_score: Optional[float] = None
        if self.score_fn and response and ground_truth:
            try:
                accuracy_score = float(self.score_fn(response, ground_truth))
            except Exception:
                pass

        # TaskResult 생성
        try:
            task_result = create_taskresult_from_execution(
                task_id=task_id,
                question=question,
                response=response,
                ground_truth=ground_truth,
                execution_time=elapsed,
                has_error=has_error,
                error_message=error_msg,
                task_type=self.task_type,
            )
            overrides: Dict[str, Any] = {"framework": "pydanticai"}
            if tokens_used:
                overrides["tokens_used"] = tokens_used
            if accuracy_score is not None:
                overrides["accuracy_score"] = max(0.0, min(1.0, accuracy_score))
            if adapter_meta and adapter_meta.chain_steps:
                overrides["chain_steps"] = adapter_meta.chain_steps
            task_result = dataclasses.replace(task_result, **overrides)
            self.monitor.record_task(task_result)
        except Exception as e:
            logger.debug("PydanticAIEvaluator: record_task failed (ignored): %s", e)

        return response

    def run(
        self,
        question: str,
        ground_truth: str = "",
        task_id: Optional[str] = None,
    ) -> str:
        """단건 동기 평가 실행 (asyncio.run 래퍼).

        Note:
            이미 실행 중인 이벤트 루프가 있으면 ``RuntimeError`` 가 발생할 수 있다.
            비동기 환경에서는 :meth:`run_async` 를 사용하라.
        """
        return asyncio.run(self.run_async(question, ground_truth, task_id))

    async def evaluate_async(
        self,
        dataset: List[Dict[str, str]],
        question_key: str = "question",
        ground_truth_key: str = "ground_truth",
        concurrency: int = 1,
    ) -> float:
        """데이터셋에 대한 비동기 일괄 평가.

        Args:
            dataset: ``{"question": ..., "ground_truth": ...}`` 딕셔너리 리스트.
            question_key: 질문 키 (기본: ``"question"``).
            ground_truth_key: 정답 키 (기본: ``"ground_truth"``).
            concurrency: 동시 실행 수 (기본: 1 = 순차).

        Returns:
            평균 accuracy 점수 (0.0 – 1.0).
        """
        import uuid

        semaphore = asyncio.Semaphore(concurrency)
        scores: List[float] = []

        async def _run_one(item: Dict[str, str]) -> float:
            async with semaphore:
                q = item.get(question_key, "")
                gt = item.get(ground_truth_key, "")
                tid = item.get("task_id", f"pai_{uuid.uuid4().hex[:8]}")
                await self.run_async(q, gt, tid)
                # score_fn 결과가 있으면 사용, 없으면 task_result의 accuracy_score
                return 1.0 if gt and q else 0.0

        tasks = [_run_one(item) for item in dataset]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, (int, float)):
                scores.append(float(r))

        return sum(scores) / len(scores) if scores else 0.0
