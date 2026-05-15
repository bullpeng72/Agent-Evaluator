"""
Metric Adapters for Hybrid Evaluation Architecture
===================================================
Integrates external evaluation libraries (DeepEval, Ragas)
with Agent Evaluator's native metrics system.
"""

import logging
import math
import os
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass

# DeepEval / Ragas 의 비동기 이벤트 루프 정리 관련
# DeprecationWarning 만 타겟 억제 (전역 억제 금지 — CLAUDE.md 참조)
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"deepeval|ragas")
warnings.filterwarnings("ignore", message=r".*Event loop.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=r".*coroutine.*was never awaited.*")


class _EventLoopClosedFilter(logging.Filter):
    """Python 3.13 + httpx: 이벤트 루프 종료 후 deepeval 내부 cleanup 태스크 에러 억제."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "Event loop is closed" not in msg and "Task exception was never retrieved" not in msg


logging.getLogger("asyncio").addFilter(_EventLoopClosedFilter())


# ============================================================================
# Core Interfaces
# ============================================================================

class MetricProvider(Enum):
    """Available metric provider backends"""
    NATIVE = "native"           # Agent Evaluator native metrics
    DEEPEVAL = "deepeval"       # DeepEval metrics (G-Eval, Hallucination, etc.)
    RAGAS = "ragas"             # Ragas metrics (RAG-specific)
    CUSTOM = "custom"           # User-defined custom metrics


@dataclass
class EvaluationContext:
    """Context information for advanced evaluation"""
    input_text: str
    output_text: str
    expected_output: Optional[str] = None
    retrieved_context: Optional[List[str]] = None
    quality_criteria: Optional[str] = None
    task_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MetricAdapter(ABC):
    """Abstract base class for metric provider adapters"""

    @abstractmethod
    def evaluate(self, context: EvaluationContext) -> Dict[str, Any]:
        """
        Evaluate using the provider's metrics

        Args:
            context: Evaluation context with input/output/ground truth

        Returns:
            Dictionary of metric name -> value pairs
        """
        pass

    @abstractmethod
    def get_metric_names(self) -> List[str]:
        """Get list of metric names this adapter provides"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (library installed)"""
        pass


# ============================================================================
# DeepEval Adapter
# ============================================================================

class DeepEvalAdapter(MetricAdapter):
    """
    Adapter for DeepEval metrics

    Provides:
    - G-Eval: Custom criteria evaluation
    - HallucinationMetric: Semantic hallucination detection
    - ToxicityMetric: Toxic content detection
    - BiasMetric: Bias detection
    - AnswerRelevancyMetric: Answer quality for QA
    """

    def __init__(self, model: str = "gpt-5-nano", threshold: float = 0.5, timeout: int = 60):
        """
        Initialize DeepEval adapter

        Args:
            model: LLM model to use for evaluation (default: gpt-5-nano for cost)
            threshold: Threshold for binary metrics (default: 0.5)
            timeout: Timeout per metric API call in seconds (default: 60).
                     Enforced via ThreadPoolExecutor.submit().result(timeout=...).
                     The underlying thread is not killed on timeout (Python limitation),
                     but the calling code proceeds immediately after TimeoutError.
        """
        self.model = model
        self.threshold = threshold
        self.timeout = timeout
        self._available = False
        self._metrics_cache = {}

        try:
            from deepeval.metrics import (
                GEval,
                HallucinationMetric,
                ToxicityMetric,
                BiasMetric,
                AnswerRelevancyMetric
            )
            from deepeval.test_case import LLMTestCase, LLMTestCaseParams

            self._available = True
            self.GEval = GEval
            self.HallucinationMetric = HallucinationMetric
            self.ToxicityMetric = ToxicityMetric
            self.BiasMetric = BiasMetric
            self.AnswerRelevancyMetric = AnswerRelevancyMetric
            self.LLMTestCase = LLMTestCase
            self.LLMTestCaseParams = LLMTestCaseParams

            logger.info("DeepEval adapter initialized (model: %s)", model)

        except ImportError as e:
            logger.info("DeepEval not available: %s. Install with: pip install deepeval", e)

    def is_available(self) -> bool:
        return self._available

    def _run_with_timeout(self, fn, *args) -> Any:
        """metric.measure() 등 블로킹 호출을 self.timeout 초 내에 실행.

        TimeoutError 발생 시 빈 dict를 반환하고 경고 로그를 출력한다.
        Python 스레드는 강제 종료할 수 없으므로 백그라운드 스레드는 계속 실행될 수 있다.
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeoutError:
                logger.warning(
                    "DeepEval metric timed out after %ds — skipping", self.timeout
                )
                return {}

    def evaluate(self, context: EvaluationContext) -> Dict[str, Any]:
        """Evaluate using DeepEval metrics.

        Each individual metric call is bounded by ``self.timeout`` seconds.
        """
        if not self._available:
            return None  # M7: None signals "adapter unavailable"; {} means "available but no results"

        results = {}

        try:
            # Create test case
            test_case = self.LLMTestCase(
                input=context.input_text,
                actual_output=context.output_text,
                expected_output=context.expected_output,
                context=context.retrieved_context or []
            )

            # 1. G-Eval for custom quality criteria
            if context.quality_criteria:
                results.update(self._evaluate_geval(test_case, context.quality_criteria))

            # 2. Hallucination detection (semantic)
            if context.retrieved_context:
                results.update(self._evaluate_hallucination(test_case))

            # 3. Toxicity detection
            results.update(self._evaluate_toxicity(test_case))

            # 4. Bias detection
            results.update(self._evaluate_bias(test_case))

            # 5. Answer relevancy (for QA tasks)
            if context.task_type in ['qa', 'information_retrieval']:
                results.update(self._evaluate_answer_relevancy(test_case))

        except (ImportError, AttributeError) as e:
            # Module or class not found — return {} so advanced_metrics.update() is a no-op
            logger.warning("DeepEval module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            # Invalid parameters or type mismatch
            logger.warning("DeepEval parameter error: %s", e)
            return {}
        except Exception as e:
            # Unexpected errors (API, network, etc.)
            logger.warning("DeepEval unexpected error: %s\n%s", e, traceback.format_exc())
            return {}

        return results

    def _evaluate_geval(self, test_case, criteria: str) -> Dict[str, Any]:
        """
        Evaluate using G-Eval with custom criteria

        G-Eval evaluates based on the test case parameters you specify.
        Uses INPUT, ACTUAL_OUTPUT, and EXPECTED_OUTPUT by default.
        """
        try:
            # Define evaluation parameters (what parts of test case to evaluate)
            eval_params = [
                self.LLMTestCaseParams.INPUT,
                self.LLMTestCaseParams.ACTUAL_OUTPUT
            ]

            # Add expected output if available
            if test_case.expected_output:
                eval_params.append(self.LLMTestCaseParams.EXPECTED_OUTPUT)

            # Add context if available
            if test_case.context and len(test_case.context) > 0:
                eval_params.append(self.LLMTestCaseParams.CONTEXT)

            metric = self.GEval(
                name="quality_assessment",
                criteria=criteria,
                evaluation_params=eval_params,
                model=self.model,
                threshold=self.threshold,
                async_mode=False  # Synchronous for simpler error handling
            )
            timed_out = self._run_with_timeout(metric.measure, test_case)
            if timed_out == {}:
                return {}

            return {
                'g_eval_score': metric.score,
                'g_eval_reason': metric.reason if hasattr(metric, 'reason') else None,
                'g_eval_passed': metric.score >= self.threshold
            }
        except (AttributeError, ImportError) as e:
            logger.warning("G-Eval module/attribute error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("G-Eval parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("G-Eval unexpected error: %s", e)
            logger.debug("G-Eval traceback: %s", traceback.format_exc())
            return {}

    def _evaluate_hallucination(self, test_case) -> Dict[str, Any]:
        """Evaluate hallucination (contextual consistency)"""
        try:
            metric = self.HallucinationMetric(
                threshold=self.threshold,
                model=self.model
            )
            if self._run_with_timeout(metric.measure, test_case) == {}:
                return {}

            return {
                'hallucination_score': metric.score,
                'hallucination_detected': metric.score < self.threshold,  # Higher score = less hallucination (no hallucination is good)
                'hallucination_passed': metric.score >= self.threshold
            }
        except (AttributeError, ImportError) as e:
            logger.warning("Hallucination metric module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("Hallucination metric parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("Hallucination metric unexpected error: %s", e)
            return {}

    def _evaluate_toxicity(self, test_case) -> Dict[str, Any]:
        """Evaluate toxicity"""
        try:
            metric = self.ToxicityMetric(
                threshold=self.threshold,
                model=self.model
            )
            if self._run_with_timeout(metric.measure, test_case) == {}:
                return {}

            return {
                'toxicity_score': metric.score,
                'toxicity_detected': metric.score > self.threshold,
                'toxicity_passed': metric.score <= self.threshold
            }
        except (AttributeError, ImportError) as e:
            logger.warning("Toxicity metric module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("Toxicity metric parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("Toxicity metric unexpected error: %s", e)
            return {}

    def _evaluate_bias(self, test_case) -> Dict[str, Any]:
        """Evaluate bias"""
        try:
            metric = self.BiasMetric(
                threshold=self.threshold,
                model=self.model
            )
            if self._run_with_timeout(metric.measure, test_case) == {}:
                return {}

            return {
                'bias_score': metric.score,
                'bias_detected': metric.score > self.threshold,
                'bias_passed': metric.score <= self.threshold
            }
        except (AttributeError, ImportError) as e:
            logger.warning("Bias metric module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("Bias metric parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("Bias metric unexpected error: %s", e)
            return {}

    def _evaluate_answer_relevancy(self, test_case) -> Dict[str, Any]:
        """Evaluate answer relevancy"""
        try:
            metric = self.AnswerRelevancyMetric(
                threshold=self.threshold,
                model=self.model
            )
            if self._run_with_timeout(metric.measure, test_case) == {}:
                return {}

            return {
                'answer_relevancy_score': metric.score,
                'answer_relevancy_passed': metric.score >= self.threshold
            }
        except (AttributeError, ImportError) as e:
            logger.warning("Answer relevancy metric module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("Answer relevancy metric parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("Answer relevancy metric unexpected error: %s", e)
            return {}

    def get_metric_names(self) -> List[str]:
        return [
            'g_eval_score',
            'g_eval_reason',
            'hallucination_score',
            'hallucination_detected',
            'toxicity_score',
            'toxicity_detected',
            'bias_score',
            'bias_detected',
            'answer_relevancy_score'
        ]


# ============================================================================
# Ragas Adapter
# ============================================================================

class RagasAdapter(MetricAdapter):
    """
    Adapter for Ragas RAG evaluation metrics (ragas >= 0.4.0)

    Provides:
    - Faithfulness: Factual consistency with context
    - AnswerRelevancy: Answer quality for question (requires embeddings)
    - ContextPrecision: Retrieved context relevance
    - ContextRecall: Context completeness (requires reference/ground_truth)
    """

    def __init__(self, llm_model: str = "gpt-5-nano", timeout: int = 60):
        """
        Initialize Ragas adapter

        Args:
            llm_model: LLM model for evaluation
            timeout: Timeout for API calls in seconds (default: 60)
                     Note: Currently informational - actual timeout enforcement
                     depends on LangChain/OpenAI client configuration.
        """
        self.llm_model = llm_model
        self.timeout = timeout
        self._available = False
        self._embeddings_wrapper = None

        try:
            # ragas 0.4.x API: EvaluationDataset + SingleTurnSample
            from ragas import evaluate, EvaluationDataset
            from ragas.dataset_schema import SingleTurnSample
            from ragas.metrics import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision
            from ragas.llms import LangchainLLMWrapper

            # Use OpenAI if available, otherwise fall back to Anthropic
            openai_key = os.getenv("OPENAI_API_KEY")
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")

            if openai_key:
                from langchain_openai import ChatOpenAI
                llm_instance = ChatOpenAI(model=llm_model)
                active_model = llm_model
            elif anthropic_key:
                from langchain_anthropic import ChatAnthropic
                llm_instance = ChatAnthropic(
                    model="claude-3-haiku-20240307",
                    anthropic_api_key=anthropic_key,
                    temperature=0
                )
                active_model = "claude-3-haiku-20240307 (Anthropic)"
            else:
                raise ImportError("Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set")

            self._available = True
            self.evaluate_fn = evaluate
            self.EvaluationDataset = EvaluationDataset
            self.SingleTurnSample = SingleTurnSample
            self.Faithfulness = Faithfulness
            self.AnswerRelevancy = AnswerRelevancy
            self.ContextRecall = ContextRecall
            self.ContextPrecision = ContextPrecision
            self.llm_wrapper = LangchainLLMWrapper(llm_instance)

            # AnswerRelevancy requires embeddings — only auto-configured for OpenAI
            if openai_key:
                try:
                    from langchain_openai import OpenAIEmbeddings
                    from ragas.embeddings import LangchainEmbeddingsWrapper
                    self._embeddings_wrapper = LangchainEmbeddingsWrapper(OpenAIEmbeddings())
                except ImportError:
                    pass

            logger.info("Ragas adapter initialized (model: %s)", active_model)
            if not self._embeddings_wrapper:
                logger.info("Ragas: no embeddings configured — AnswerRelevancy will be skipped")

        except ImportError as e:
            logger.info(
                "Ragas not available: %s. Install with: pip install 'agent-evaluator[eval]'", e
            )

    def is_available(self) -> bool:
        return self._available

    def evaluate(self, context: EvaluationContext) -> Optional[Dict[str, Any]]:
        """Evaluate using Ragas RAG metrics (ragas 0.4.x API)"""
        if not self._available:
            return None  # M7: None signals "adapter unavailable"; {} means "available but no results"

        # Only evaluate RAG tasks with retrieved context
        if not context.retrieved_context:
            return {}

        results = {}

        try:
            # ragas 0.4.x: SingleTurnSample replaces the old dict-based Dataset
            # Field mapping: question→user_input, answer→response,
            #                contexts→retrieved_contexts, ground_truth→reference
            sample = self.SingleTurnSample(
                user_input=context.input_text,
                response=context.output_text,
                retrieved_contexts=context.retrieved_context,
                reference=context.expected_output if context.expected_output else None,
            )
            dataset = self.EvaluationDataset(samples=[sample])

            # Build metric instances with LLM — ragas 0.4.x requires class instantiation
            faithfulness = self.Faithfulness(llm=self.llm_wrapper)
            context_precision = self.ContextPrecision(llm=self.llm_wrapper)
            metrics = [faithfulness, context_precision]

            # AnswerRelevancy needs embeddings in ragas 0.4.x
            if self._embeddings_wrapper:
                answer_relevancy = self.AnswerRelevancy(
                    llm=self.llm_wrapper,
                    embeddings=self._embeddings_wrapper,
                )
                metrics.append(answer_relevancy)

            # ContextRecall requires a reference (ground_truth)
            if context.expected_output:
                context_recall = self.ContextRecall(llm=self.llm_wrapper)
                metrics.append(context_recall)

            eval_result = self.evaluate_fn(dataset, metrics=metrics)

            # Extract scores — EvaluationResult[metric.name] returns a list (one value per sample)
            for metric_obj in metrics:
                metric_name = metric_obj.name
                try:
                    value_list = eval_result[metric_name]
                    value = value_list[0] if isinstance(value_list, (list, tuple)) and value_list else value_list
                    if value is not None and isinstance(value, (int, float)) and not (
                        isinstance(value, float) and math.isnan(value)
                    ):
                        results[f'ragas_{metric_name}'] = float(value)
                except (KeyError, IndexError, TypeError, AttributeError, ValueError):
                    continue

            # Overall score from numeric metrics only
            numeric_metrics = {
                k: v for k, v in results.items()
                if isinstance(v, (int, float))
                and not isinstance(v, bool)
                and not k.endswith(('_error', '_passed', '_detected'))
            }
            if numeric_metrics:
                results['ragas_overall_score'] = sum(numeric_metrics.values()) / len(numeric_metrics)

            if 'ragas_overall_score' in results:
                overall = results['ragas_overall_score']
                if overall >= 0.8:
                    results['ragas_quality'] = 'excellent'
                elif overall >= 0.6:
                    results['ragas_quality'] = 'good'
                elif overall >= 0.4:
                    results['ragas_quality'] = 'acceptable'
                else:
                    results['ragas_quality'] = 'poor'

        except (ImportError, AttributeError) as e:
            # Module or class not found — return {} so advanced_metrics.update() is a no-op
            logger.warning("Ragas module error: %s", e)
            return {}
        except (ValueError, TypeError) as e:
            logger.warning("Ragas parameter error: %s", e)
            return {}
        except Exception as e:
            logger.warning("Ragas unexpected error: %s\n%s", e, traceback.format_exc())
            return {}

        return results

    def get_metric_names(self) -> List[str]:
        return [
            'ragas_faithfulness',
            'ragas_answer_relevancy',
            'ragas_context_recall',
            'ragas_context_precision',
            'ragas_overall_score',
            'ragas_quality'
        ]


# ============================================================================
# Adapter Factory
# ============================================================================

class MetricAdapterFactory:
    """Factory for creating metric adapters"""

    @staticmethod
    def create_adapter(provider: MetricProvider, **kwargs) -> Optional[MetricAdapter]:
        """
        Create a metric adapter for the specified provider

        Args:
            provider: Metric provider type
            **kwargs: Provider-specific configuration

        Returns:
            MetricAdapter instance or None if unavailable
        """
        if provider == MetricProvider.DEEPEVAL:
            adapter = DeepEvalAdapter(**kwargs)
            return adapter if adapter.is_available() else None

        elif provider == MetricProvider.RAGAS:
            adapter = RagasAdapter(**kwargs)
            return adapter if adapter.is_available() else None

        else:
            raise ValueError(f"Unknown provider: {provider}")

    @staticmethod
    def get_available_providers() -> List[MetricProvider]:
        """Get list of available providers"""
        available = [MetricProvider.NATIVE]  # Always available

        # Check DeepEval
        try:
            import deepeval
            available.append(MetricProvider.DEEPEVAL)
        except ImportError:
            pass

        # Check Ragas
        try:
            import ragas
            available.append(MetricProvider.RAGAS)
        except ImportError:
            pass

        return available


# ============================================================================
# Utility Functions
# ============================================================================

def print_available_metrics():
    """Print available metric providers and their metrics"""
    print("\n" + "="*60)
    print("Available Metric Providers")
    print("="*60 + "\n")

    providers = MetricAdapterFactory.get_available_providers()

    for provider in providers:
        print(f"✅ {provider.value.upper()}")

        if provider == MetricProvider.DEEPEVAL:
            adapter = DeepEvalAdapter()
            if adapter.is_available():
                print(f"   Metrics: {', '.join(adapter.get_metric_names())}")

        elif provider == MetricProvider.RAGAS:
            adapter = RagasAdapter()
            if adapter.is_available():
                print(f"   Metrics: {', '.join(adapter.get_metric_names())}")

        print()


if __name__ == "__main__":
    # Test availability
    print_available_metrics()
