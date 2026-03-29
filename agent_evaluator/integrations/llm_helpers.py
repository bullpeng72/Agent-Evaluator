"""
LLM Integration Helpers
Simplify real LLM API calls with automatic evaluation and recording
"""

import time
from datetime import datetime
from typing import Optional, Dict, Any, List


class LLMEvaluationHelper:
    """
    Helper for evaluating real LLM API calls
    Automatically records metrics in PerformanceMonitor

    Example:
        ```python
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.integrations.llm_helpers import LLMEvaluationHelper

        monitor = PerformanceMonitor()
        llm_helper = LLMEvaluationHelper(monitor)

        # Real OpenAI call with auto-evaluation!
        task = llm_helper.evaluate_openai_call(
            task_id="qa_001",
            prompt="What is the capital of France?",
            ground_truth="Paris",
            model="gpt-4o-mini"
        )

        print(f"Answer: {task.response}")
        print(f"Accuracy: {task.accuracy_score:.2f}")
        # Already recorded in monitor!
        ```
    """

    def __init__(self, monitor):
        """
        Initialize LLMEvaluationHelper

        Args:
            monitor: PerformanceMonitor or HybridPerformanceMonitor instance
        """
        self.monitor = monitor

    def evaluate_openai_call(
        self,
        task_id: str,
        prompt: str,
        ground_truth: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        context: Optional[str] = None,
        **openai_kwargs
    ):
        """
        Evaluate an OpenAI API call and automatically record metrics

        Args:
            task_id: Task identifier
            prompt: User prompt
            ground_truth: Expected answer (for accuracy calculation)
            model: OpenAI model name (default: gpt-4o-mini)
            temperature: Model temperature
            context: Additional context for RAG scenarios
            **openai_kwargs: Additional OpenAI API parameters

        Returns:
            TaskResult with auto-calculated metrics

        Raises:
            ImportError: If openai library is not installed
            Exception: Any OpenAI API error
        """
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. Install with: pip install openai"
            )

        from ..helpers.taskresult_helpers import create_taskresult_from_execution
        from ..core.agent_evaluator import TaskResult

        start_time = time.time()

        try:
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            if context:
                messages.insert(0, {
                    "role": "system",
                    "content": f"Use the following context to answer:\n\n{context}"
                })

            # Real OpenAI API call
            response = openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **openai_kwargs
            )

            execution_time = time.time() - start_time
            answer = response.choices[0].message.content
            tokens = {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
                "total": response.usage.total_tokens
            }

            # Auto-create TaskResult with accuracy calculation
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type="qa",
                question=prompt,
                response=answer,
                ground_truth=ground_truth or "",
                execution_time=execution_time,
                openai_response=response,
                context=context
            )

            # Auto-record in monitor
            self.monitor.record_task(task)

            return task

        except Exception as e:
            execution_time = time.time() - start_time

            # Create failure task
            task = TaskResult(
                task_id=task_id,
                task_type="qa",
                success=False,
                completion_score=0.0,
                accuracy_score=0.0,
                execution_time=execution_time,
                tokens_used={"input": 0, "output": 0, "total": 0},
                tool_calls=[],
                attempts=1,
                errors=[str(e)],
                timestamp=datetime.now()
            )

            # Record failure
            self.monitor.record_task(task)

            # Re-raise exception
            raise

    def evaluate_batch_openai_calls(
        self,
        tasks: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        show_progress: bool = True
    ) -> List:
        """
        Evaluate multiple OpenAI calls in batch

        Args:
            tasks: List of task dictionaries with keys:
                   - task_id: str
                   - prompt: str
                   - ground_truth: Optional[str]
                   - context: Optional[str]
            model: OpenAI model name
            show_progress: Show progress bar

        Returns:
            List of TaskResult objects
        """
        results = []

        for i, task_config in enumerate(tasks):
            if show_progress:
                print(f"Processing {i+1}/{len(tasks)}: {task_config['task_id']}")

            try:
                result = self.evaluate_openai_call(
                    task_id=task_config['task_id'],
                    prompt=task_config['prompt'],
                    ground_truth=task_config.get('ground_truth'),
                    context=task_config.get('context'),
                    model=model
                )
                results.append(result)

            except Exception as e:
                print(f"  ❌ Error: {e}")
                # Error task already recorded in evaluate_openai_call

        if show_progress:
            success_count = sum(1 for r in results if r.success)
            print(f"\n✅ Batch completed: {success_count}/{len(tasks)} successful")

        return results


class AnthropicEvaluationHelper:
    """
    Helper for evaluating Anthropic (Claude) API calls
    Similar to LLMEvaluationHelper but for Claude models

    Example:
        ```python
        from agent_evaluator import PerformanceMonitor
        from agent_evaluator.integrations.llm_helpers import AnthropicEvaluationHelper

        monitor = PerformanceMonitor()
        claude_helper = AnthropicEvaluationHelper(monitor)

        task = claude_helper.evaluate_claude_call(
            task_id="qa_001",
            prompt="Explain quantum computing",
            model="claude-3-sonnet-20240229"
        )
        ```
    """

    def __init__(self, monitor):
        """
        Initialize AnthropicEvaluationHelper

        Args:
            monitor: PerformanceMonitor or HybridPerformanceMonitor instance
        """
        self.monitor = monitor

    def evaluate_claude_call(
        self,
        task_id: str,
        prompt: str,
        ground_truth: Optional[str] = None,
        model: str = "claude-3-sonnet-20240229",
        max_tokens: int = 1024,
        **anthropic_kwargs
    ):
        """
        Evaluate an Anthropic Claude API call

        Args:
            task_id: Task identifier
            prompt: User prompt
            ground_truth: Expected answer
            model: Claude model name
            max_tokens: Maximum tokens to generate
            **anthropic_kwargs: Additional Anthropic API parameters

        Returns:
            TaskResult with auto-calculated metrics
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )

        from ..helpers.taskresult_helpers import create_taskresult_from_execution
        from ..core.agent_evaluator import TaskResult

        start_time = time.time()

        try:
            # Real Anthropic API call
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **anthropic_kwargs
            )

            execution_time = time.time() - start_time
            answer = response.content[0].text
            tokens = {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "total": response.usage.input_tokens + response.usage.output_tokens
            }

            # Auto-create TaskResult
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type="qa",
                question=prompt,
                response=answer,
                ground_truth=ground_truth or "",
                execution_time=execution_time,
            )

            # Auto-record
            self.monitor.record_task(task)

            return task

        except Exception as e:
            execution_time = time.time() - start_time

            # Create failure task
            task = TaskResult(
                task_id=task_id,
                task_type="qa",
                success=False,
                completion_score=0.0,
                accuracy_score=0.0,
                execution_time=execution_time,
                tokens_used={"input": 0, "output": 0, "total": 0},
                tool_calls=[],
                attempts=1,
                errors=[str(e)],
                timestamp=datetime.now()
            )

            self.monitor.record_task(task)
            raise
