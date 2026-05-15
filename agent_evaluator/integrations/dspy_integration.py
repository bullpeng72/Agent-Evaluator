"""
agent_evaluator.integrations.dspy_integration
=============================================
DSPy 평가 통합 — DSPy Program / Module 을 agent-evaluator 와 연결한다.

지원 기능:
- ``@dspy_eval`` 데코레이터 (``agent_eval + framework="dspy"``)
- ``DSPyEvaluator`` — ``dspy.Evaluate`` 와 통합해 데이터셋 평가를 일괄 수행
- ``DSPyMetricAdapter`` — 기존 DSPy metric 함수를 agent-evaluator score_fn 으로 변환

의존성 (opt-in):
    pip install dspy-ai  # 또는 pip install dspy

Examples::

    import dspy
    from agent_evaluator import QuickEval
    from agent_evaluator.integrations.dspy_integration import DSPyEvaluator

    # 1. 데코레이터 방식
    eval = QuickEval("results/")

    @eval(task_type="reasoning", framework="dspy")
    def my_cot(question: str, ground_truth: str = "") -> str:
        pred = cot(question=question)
        return pred.answer

    # 2. DSPyEvaluator 방식
    dspy_eval = DSPyEvaluator(monitor, program=cot)
    dspy_eval.evaluate(devset, metric=dspy.evaluate.answer_exact_match)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "dspy_eval",
    "DSPyEvaluator",
    "DSPyMetricAdapter",
]


# ---------------------------------------------------------------------------
# 데코레이터
# ---------------------------------------------------------------------------

def dspy_eval(
    monitor: Any,
    task_type: Any = "reasoning",
    **kwargs: Any,
) -> Any:
    """DSPy Program 평가 전용 데코레이터.

    ``@agent_eval(monitor, framework="dspy")`` 의 편의 별칭이다.
    DSPy Prediction 객체에서 체인 스텝과 토큰 사용량을 자동 추출한다.

    Args:
        monitor: PerformanceMonitor 인스턴스.
        task_type: Task 유형 (기본: ``"reasoning"``).
        **kwargs: :func:`agent_eval` 에 전달할 추가 파라미터.

    Example::

        from agent_evaluator.integrations.dspy_integration import dspy_eval

        @dspy_eval(monitor)
        def cot_agent(question: str, ground_truth: str = "") -> str:
            pred = cot(question=question)
            return pred.answer
    """
    from agent_evaluator.decorators import agent_eval
    kwargs.setdefault("framework", "dspy")
    return agent_eval(monitor, task_type, **kwargs)


# ---------------------------------------------------------------------------
# DSPyEvaluator
# ---------------------------------------------------------------------------

class DSPyEvaluator:
    """DSPy 데이터셋 일괄 평가기.

    DSPy 의 ``Evaluate`` 클래스와 통합해 ``devset`` 에 대한 평가를 수행하고
    결과를 ``PerformanceMonitor`` 에 기록한다.

    Args:
        monitor: PerformanceMonitor 인스턴스.
        program: 평가할 DSPy Module / Program.
        task_type: Task 유형 (기본: ``"reasoning"``).

    Example::

        evaluator = DSPyEvaluator(monitor, program=cot_program)
        score = evaluator.evaluate(devset, metric=dspy.evaluate.answer_exact_match)
        print(f"Dataset score: {score:.2f}")
    """

    def __init__(
        self,
        monitor: Any,
        program: Any,
        task_type: str = "reasoning",
    ) -> None:
        self.monitor = monitor
        self.program = program
        self.task_type = task_type

    def evaluate(
        self,
        devset: List[Any],
        metric: Optional[Callable] = None,
        num_threads: int = 1,
        display_progress: bool = False,
    ) -> float:
        """devset 에 대해 program 을 실행하고 결과를 monitor 에 기록.

        Args:
            devset: DSPy Example 리스트.
            metric: ``(example, prediction, trace=None) -> float|bool`` 형식 함수.
            num_threads: 병렬 실행 스레드 수.
            display_progress: 진행 상황 출력 여부.

        Returns:
            평균 metric 점수 (0.0 – 1.0).
        """
        import uuid
        import time

        try:
            from agent_evaluator.helpers.taskresult_helpers import create_taskresult_from_execution
            from agent_evaluator.decorators import _extract_dspy_metadata
        except ImportError as e:
            logger.warning("DSPyEvaluator: import failed — %s", e)
            return 0.0

        scores: List[float] = []

        for i, example in enumerate(devset):
            task_id = f"dspy_{uuid.uuid4().hex[:8]}"
            question = str(getattr(example, "question", getattr(example, "input", str(example))))
            ground_truth = str(getattr(example, "answer", getattr(example, "output", "")))

            start = time.perf_counter()
            has_error = False
            error_msg = None
            raw = None

            try:
                raw = self.program(question=question)
            except Exception as exc:
                has_error = True
                error_msg = str(exc)
                logger.debug("DSPyEvaluator: program execution failed (task %d): %s", i, exc)

            elapsed = time.perf_counter() - start

            # 응답 추출
            if raw is not None:
                response = str(getattr(raw, "answer", getattr(raw, "output", str(raw))))
            else:
                response = ""

            # Metric 점수 계산
            score = 0.0
            if metric is not None and raw is not None and not has_error:
                try:
                    result = metric(example, raw)
                    score = float(result) if isinstance(result, (int, float)) else (1.0 if result else 0.0)
                except Exception as e:
                    logger.debug("DSPyEvaluator: metric failed (ignored): %s", e)
            scores.append(score)

            # DSPy 메타데이터 추출
            adapter_meta = None
            if raw is not None:
                try:
                    adapter_meta = _extract_dspy_metadata(raw)
                except Exception:
                    pass

            # TaskResult 생성 및 기록
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
                import dataclasses
                overrides: Dict[str, Any] = {
                    "accuracy_score": score,
                    "framework": "dspy",
                }
                if adapter_meta:
                    if adapter_meta.chain_steps:
                        overrides["chain_steps"] = adapter_meta.chain_steps
                    if adapter_meta.tokens_used:
                        overrides["tokens_used"] = adapter_meta.tokens_used
                task_result = dataclasses.replace(task_result, **overrides)
                self.monitor.record_task(task_result)
            except Exception as e:
                logger.debug("DSPyEvaluator: record_task failed (ignored): %s", e)

            if display_progress and (i + 1) % 10 == 0:
                avg = sum(scores) / len(scores) if scores else 0.0
                print(f"  [{i+1}/{len(devset)}] avg_score={avg:.3f}")

        return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# DSPyMetricAdapter
# ---------------------------------------------------------------------------

class DSPyMetricAdapter:
    """DSPy metric 함수를 agent-evaluator ``score_fn`` 으로 변환.

    Args:
        metric: ``(example, prediction, trace=None) -> float|bool`` 형식 DSPy metric 함수.
        example_factory: ``(response, ground_truth) -> DSPy Example`` 변환 함수.
            None 이면 기본 변환 사용.

    Example::

        import dspy
        from agent_evaluator.integrations.dspy_integration import DSPyMetricAdapter

        adapter = DSPyMetricAdapter(dspy.evaluate.answer_exact_match)

        @agent_eval(monitor, task_type="qa", score_fn=adapter.score_fn)
        def my_agent(question, ground_truth=""): ...
    """

    def __init__(
        self,
        metric: Callable,
        example_factory: Optional[Callable] = None,
    ) -> None:
        self.metric = metric
        self.example_factory = example_factory

    def score_fn(self, response: str, ground_truth: str) -> float:
        """agent-evaluator ``score_fn`` 호환 인터페이스."""
        try:
            if self.example_factory:
                example = self.example_factory(response, ground_truth)
            else:
                try:
                    import dspy
                    example = dspy.Example(answer=ground_truth).with_inputs()
                    prediction = dspy.Prediction(answer=response)
                except ImportError:
                    # DSPy 미설치 시 단순 exact_match
                    return 1.0 if response.strip() == ground_truth.strip() else 0.0

            result = self.metric(example, prediction)
            return float(result) if isinstance(result, (int, float)) else (1.0 if result else 0.0)
        except Exception as e:
            logger.debug("DSPyMetricAdapter.score_fn failed (returning 0.0): %s", e)
            return 0.0
