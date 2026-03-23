"""
Hybrid Performance Monitor
===========================
Extends native Agent Evaluator with external library metrics
(DeepEval, Ragas, LangSmith)
"""

import atexit
import json
import os
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import metric adapters
from ..integrations.metric_adapters import (
    DeepEvalAdapter,
    EvaluationContext,
    LangSmithAdapter,
    MetricAdapter,
    MetricProvider,
    RagasAdapter,
)

# Import native Agent Evaluator
from .agent_evaluator import EvaluationReport, PerformanceMonitor, TaskResult

# Suppress async event loop warnings from httpx/DeepEval/Ragas
# These occur when async clients clean up after the event loop closes
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*Event loop is closed.*')
warnings.filterwarnings('ignore', message='.*coroutine.*was never awaited.*')


# ============================================================================
# Extended Data Classes
# ============================================================================

@dataclass
class ExtendedTaskResult(TaskResult):
    """TaskResult with advanced metrics from external libraries"""
    advanced_metrics: Dict[str, Any] = field(default_factory=dict)
    evaluation_context: Optional[Dict[str, Any]] = None
    metric_providers_used: List[str] = field(default_factory=list)


@dataclass
class HybridEvaluationReport(EvaluationReport):
    """Evaluation report with advanced metrics"""
    advanced_metrics_summary: Dict[str, Any] = field(default_factory=dict)
    providers_used: List[str] = field(default_factory=list)


# ============================================================================
# Hybrid Performance Monitor
# ============================================================================

class HybridPerformanceMonitor(PerformanceMonitor):
    """
    Extended PerformanceMonitor with external library integration

    Features:
    - Native Agent Evaluator metrics (fast, always available)
    - DeepEval metrics (G-Eval, Hallucination, Toxicity, Bias)
    - Ragas metrics (RAG-specific: Faithfulness, Context Recall, etc.)
    - LangSmith metrics (optional: tracing data)
    """

    def __init__(
        self,
        use_deepeval: bool = True,
        use_ragas: bool = True,
        use_langsmith: bool = False,
        deepeval_model: str = "gpt-4o-mini",
        ragas_model: str = "gpt-4o-mini",
        langsmith_api_key: Optional[str] = None,
        enable_hallucination_detection: bool = True,
        enable_security_metrics: bool = False,
        security_config: Optional[Dict[str, Any]] = None,
        enable_transparency: bool = False,
        output_dir: Optional[str] = None
    ):
        """
        Initialize Hybrid Performance Monitor

        Args:
            use_deepeval: Enable DeepEval metrics
            use_ragas: Enable Ragas metrics
            use_langsmith: Enable LangSmith integration
            deepeval_model: Model for DeepEval (default: gpt-4o-mini for cost)
            ragas_model: Model for Ragas (default: gpt-4o-mini)
            langsmith_api_key: LangSmith API key (optional)
            enable_hallucination_detection: Enable Layer1 hallucination detection (default: True for Hybrid)
            enable_security_metrics: Enable security metrics (Layer 1 & 2 security trackers)
            security_config: Security configuration (allowed_tools, restricted_tools, etc.)
            enable_transparency: Enable transparency logging (traces, audit logs)
            output_dir: Output directory (None이면 자동 감지)
        """
        # Initialize native monitor with Zero Configuration and hallucination detection enabled
        super().__init__(
            output_dir=output_dir,
            enable_security_metrics=enable_security_metrics,
            security_config=security_config,
            enable_hallucination_detection=enable_hallucination_detection,
            enable_transparency=enable_transparency,
        )

        # Initialize metric adapters
        self.metric_adapters: Dict[MetricProvider, MetricAdapter] = {}
        self.enabled_providers: List[str] = ["native"]

        print("\n" + "="*60)
        print("Initializing Hybrid Performance Monitor")
        print("="*60)

        # DeepEval adapter
        if use_deepeval:
            adapter = DeepEvalAdapter(model=deepeval_model)
            if adapter.is_available():
                self.metric_adapters[MetricProvider.DEEPEVAL] = adapter
                self.enabled_providers.append("deepeval")
                print(f"✅ DeepEval enabled (model: {deepeval_model})")
            else:
                print("⚠️  DeepEval not available - install with: pip install deepeval")

        # Ragas adapter
        if use_ragas:
            adapter = RagasAdapter(llm_model=ragas_model)
            if adapter.is_available():
                self.metric_adapters[MetricProvider.RAGAS] = adapter
                self.enabled_providers.append("ragas")
                print(f"✅ Ragas enabled (model: {ragas_model})")
            else:
                print("⚠️  Ragas not available - install with: pip install ragas langchain-openai")

        # LangSmith adapter
        if use_langsmith:
            adapter = LangSmithAdapter(api_key=langsmith_api_key)
            if adapter.is_available():
                self.metric_adapters[MetricProvider.LANGSMITH] = adapter
                self.enabled_providers.append("langsmith")
                print("✅ LangSmith enabled")
            else:
                print("⚠️  LangSmith not available - set LANGSMITH_API_KEY")

        print(f"\n📊 Active providers: {', '.join(self.enabled_providers)}")
        print("="*60 + "\n")

        # Storage for extended results
        self.extended_tasks: List[ExtendedTaskResult] = []

        # Register cleanup handler
        atexit.register(self._cleanup)

    def record_task(
        self,
        task: TaskResult,
        enable_advanced_metrics: bool = True,
        input_text: str = "",
        output_text: str = "",
        expected_output: Optional[str] = None,
        retrieved_context: Optional[List[str]] = None,
        quality_criteria: Optional[str] = None
    ):
        """
        Record task with both native and advanced metrics

        Args:
            task: TaskResult from agent execution
            enable_advanced_metrics: Enable external library metrics (slower)
            input_text: Input text for evaluation
            output_text: Output text for evaluation
            expected_output: Expected/ground truth output
            retrieved_context: Retrieved documents (for RAG)
            quality_criteria: Custom quality criteria for G-Eval
        """
        # 1. Record with native Agent Evaluator (fast) + automatic hallucination detection
        # Build context for hallucination detection
        context_for_hallucination = None
        if retrieved_context:
            # RAG context: join retrieved documents
            context_for_hallucination = '\n\n'.join(retrieved_context)
        elif input_text:
            # Non-RAG context: use input as context
            context_for_hallucination = input_text

        super().record_task(
            task,
            context=context_for_hallucination,
            response=output_text if output_text else None,
            ground_truth=expected_output,
            request=input_text if input_text else None
        )

        # 2. Evaluate with external libraries (optional, slower)
        advanced_metrics = {}
        providers_used = ["native"]

        if enable_advanced_metrics and (input_text or output_text):
            context = EvaluationContext(
                input_text=input_text,
                output_text=output_text,
                expected_output=expected_output,
                retrieved_context=retrieved_context,
                quality_criteria=quality_criteria,
                task_type=task.task_type
            )

            # DeepEval metrics
            if MetricProvider.DEEPEVAL in self.metric_adapters:
                try:
                    deepeval_metrics = self.metric_adapters[MetricProvider.DEEPEVAL].evaluate(context)
                    advanced_metrics.update(deepeval_metrics)
                    providers_used.append("deepeval")
                except Exception as e:
                    print(f"⚠️  DeepEval evaluation error: {e}")

            # Ragas metrics (only for RAG tasks)
            if MetricProvider.RAGAS in self.metric_adapters and retrieved_context:
                try:
                    ragas_metrics = self.metric_adapters[MetricProvider.RAGAS].evaluate(context)
                    advanced_metrics.update(ragas_metrics)
                    providers_used.append("ragas")
                except Exception as e:
                    print(f"⚠️  Ragas evaluation error: {e}")

            # LangSmith metrics
            if MetricProvider.LANGSMITH in self.metric_adapters:
                try:
                    langsmith_metrics = self.metric_adapters[MetricProvider.LANGSMITH].evaluate(context)
                    advanced_metrics.update(langsmith_metrics)
                    providers_used.append("langsmith")
                except Exception as e:
                    print(f"⚠️  LangSmith evaluation error: {e}")

        # Create extended task result
        extended_task = ExtendedTaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            success=task.success,
            completion_score=task.completion_score,
            accuracy_score=task.accuracy_score,
            execution_time=task.execution_time,
            tokens_used=task.tokens_used,
            tool_calls=task.tool_calls,
            attempts=task.attempts,
            errors=task.errors,
            timestamp=task.timestamp,
            framework=getattr(task, 'framework', None),
            advanced_metrics=advanced_metrics,
            evaluation_context={
                'input_text': input_text,
                'output_text': output_text,
                'expected_output': expected_output,
                'retrieved_context': retrieved_context,
                'quality_criteria': quality_criteria
            } if enable_advanced_metrics else None,
            metric_providers_used=providers_used
        )

        self.extended_tasks.append(extended_task)

        # Auto-populate quality_evaluator and hallucination_detector from DeepEval results
        if advanced_metrics:
            # 1. Populate quality_evaluator from G-Eval results
            if 'g_eval_score' in advanced_metrics and advanced_metrics.get('g_eval_score') is not None:
                # G-Eval score is 0-1, convert to 5-point scale for quality_evaluator
                g_eval_score_5pt = advanced_metrics['g_eval_score'] * 5

                # Create quality evaluation entry compatible with quality_evaluator
                quality_evaluation = {
                    "task_id": task.task_id,
                    "dimension_scores": {
                        "completeness": g_eval_score_5pt,
                        "relevance": g_eval_score_5pt,
                        "clarity": g_eval_score_5pt,
                        "accuracy": g_eval_score_5pt,
                        "usefulness": g_eval_score_5pt
                    },
                    "total_score": g_eval_score_5pt,
                    "grade": self.quality_evaluator._assign_grade(g_eval_score_5pt),
                    "timestamp": task.timestamp or datetime.now()
                }
                self.quality_evaluator.evaluations.append(quality_evaluation)

            # 2. Populate hallucination_detector from DeepEval hallucination results
            if 'hallucination_score' in advanced_metrics and advanced_metrics.get('hallucination_score') is not None:
                # DeepEval hallucination_score: 1.0 = no hallucination (good), 0.0 = full hallucination (bad)
                # Convert to hallucination_rate: 0.0 = no hallucination, 1.0 = full hallucination
                hallucination_rate = 1.0 - advanced_metrics['hallucination_score']

                # Create hallucination detection entry
                hallucination_detection = {
                    "task_id": task.task_id,
                    "hallucination_rate": hallucination_rate,
                    "indicators": [],  # DeepEval doesn't provide detailed indicators
                    "timestamp": task.timestamp or datetime.now(),
                    "source": "deepeval",  # Mark as coming from DeepEval
                    "score": advanced_metrics['hallucination_score'],  # Keep original score for reference
                    "detected": advanced_metrics.get('hallucination_detected', hallucination_rate > 0.5)
                }
                self.hallucination_detector.detections.append(hallucination_detection)

    def _cleanup(self):
        """
        Cleanup async resources before program exit

        This method suppresses async event loop warnings that occur when
        DeepEval/Ragas/LangChain use httpx AsyncClient internally.
        """
        # Suppress the specific async warnings
        warnings.filterwarnings('ignore', message='.*Event loop is closed.*')
        warnings.filterwarnings('ignore', message='.*Task exception was never retrieved.*')

        # Note: We don't need to explicitly close DeepEval/Ragas clients
        # as they manage their own lifecycle. The warning suppression
        # is sufficient to handle the cleanup race condition.

    def generate_hybrid_report(self) -> HybridEvaluationReport:
        """Generate comprehensive report with advanced metrics"""
        # Get native report
        native_report = super().generate_report()

        # Aggregate advanced metrics
        advanced_summary = self._aggregate_advanced_metrics()

        # Combine native and advanced recommendations
        combined_recommendations = list(native_report.recommendations)
        advanced_recommendations = self._generate_advanced_recommendations(advanced_summary)
        combined_recommendations.extend(advanced_recommendations)

        # Create hybrid report
        hybrid_report = HybridEvaluationReport(
            period=native_report.period,
            total_tasks=native_report.total_tasks,
            accuracy_metrics=native_report.accuracy_metrics,
            efficiency_metrics=native_report.efficiency_metrics,
            quality_metrics=native_report.quality_metrics,
            security_metrics=native_report.security_metrics,  # Include security metrics
            alerts=native_report.alerts,
            recommendations=combined_recommendations,
            timestamp=native_report.timestamp,
            advanced_metrics_summary=advanced_summary,
            providers_used=self.enabled_providers
        )

        return hybrid_report

    def _aggregate_advanced_metrics(self, debug: bool = False) -> Dict[str, Any]:
        """
        Aggregate advanced metrics across all tasks

        Args:
            debug: Enable debug output to see metric collection process
        """
        # If advanced metrics were loaded from file, use those
        if hasattr(self, '_advanced_metrics_summary') and self._advanced_metrics_summary:
            return self._advanced_metrics_summary

        if not self.extended_tasks:
            return {}

        summary = {}

        # Collect all metric values
        metric_values = {}
        metric_counts = {}  # Track how many tasks have each metric

        for task in self.extended_tasks:
            if debug:
                print(f"  Task {task.task_id} metrics: {list(task.advanced_metrics.keys())}")

            for metric_name, value in task.advanced_metrics.items():
                # Skip error entries
                if metric_name.endswith('_error'):
                    continue

                # Track metric occurrence
                metric_counts[metric_name] = metric_counts.get(metric_name, 0) + 1

                # Collect numeric values for statistics
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(float(value))

        if debug:
            print("\n📊 Metrics collected:")
            for metric_name, count in sorted(metric_counts.items()):
                print(f"  • {metric_name}: {count} tasks")

        # Calculate statistics for numeric metrics
        for metric_name, values in metric_values.items():
            if values:
                import statistics

                mean_val = statistics.mean(values)
                median_val = statistics.median(values)

                # Use sample standard deviation (n-1) instead of population (n)
                std_val = statistics.stdev(values) if len(values) > 1 else 0.0

                summary[metric_name] = {
                    'mean': mean_val,
                    'median': median_val,
                    'min': min(values),
                    'max': max(values),
                    'count': len(values),
                    'std': std_val
                }

                if debug:
                    print(f"\n  {metric_name} statistics:")
                    print(f"    Mean: {summary[metric_name]['mean']:.3f}")
                    print(f"    Min: {summary[metric_name]['min']:.3f}")
                    print(f"    Max: {summary[metric_name]['max']:.3f}")

        # Add categorical summaries for detection metrics
        summary['hallucination_detection'] = self._summarize_detections('hallucination_detected')
        summary['toxicity_detection'] = self._summarize_detections('toxicity_detected')
        summary['bias_detection'] = self._summarize_detections('bias_detected')

        # Add pass/fail summaries
        for metric_base in ['g_eval', 'hallucination', 'toxicity', 'bias', 'answer_relevancy']:
            passed_key = f'{metric_base}_passed'
            if any(passed_key in task.advanced_metrics for task in self.extended_tasks):
                summary[f'{metric_base}_pass_rate'] = self._calculate_pass_rate(passed_key)

        return summary

    def _calculate_pass_rate(self, passed_key: str) -> Dict[str, Any]:
        """Calculate pass rate for a given metric"""
        passed = 0
        total = 0

        for task in self.extended_tasks:
            if passed_key in task.advanced_metrics:
                total += 1
                if task.advanced_metrics[passed_key]:
                    passed += 1

        return {
            'passed': passed,
            'total': total,
            'rate': passed / total if total > 0 else 0
        }

    def _summarize_detections(self, metric_name: str) -> Dict[str, int]:
        """Summarize boolean detection metrics"""
        detected = 0
        total = 0

        for task in self.extended_tasks:
            if metric_name in task.advanced_metrics:
                total += 1
                if task.advanced_metrics[metric_name]:
                    detected += 1

        return {
            'detected': detected,
            'total': total,
            'rate': detected / total if total > 0 else 0
        }

    def save_to_file(self, filename: str = "hybrid_evaluation_results.json"):
        """Save results with advanced metrics to JSON file in results/"""
        # results/ 디렉토리에 저장 (절대 경로가 아닌 경우)
        if not os.path.isabs(filename):
            from ..utils.path_helpers import get_evaluation_results_dir
            results_dir = get_evaluation_results_dir(create=True)
            filename = os.path.join(results_dir, filename)

        _now = datetime.now().isoformat()
        data = {
            'total_tasks': len(self.extended_tasks),
            'timestamp': _now,
            'metadata': {
                'created_at': _now,
                'total_tasks': len(self.extended_tasks),
                'providers_used': self.enabled_providers
            },
            'pricing': self.token_tracker.pricing,
            'tasks': [
                {
                    'task_id': task.task_id,
                    'task_type': task.task_type,
                    'success': task.success,
                    'completion_score': task.completion_score,
                    'accuracy_score': task.accuracy_score,
                    'execution_time': task.execution_time,
                    'tokens_used': task.tokens_used,
                    'tool_calls': task.tool_calls,
                    'attempts': task.attempts,
                    'errors': task.errors,
                    'timestamp': task.timestamp.isoformat() if hasattr(task.timestamp, 'isoformat') else str(task.timestamp),
                    'advanced_metrics': task.advanced_metrics,
                    'providers_used': task.metric_providers_used,
                    # Add Agentic AI fields
                    'framework': getattr(task, 'framework', None),
                    'expected_tools': getattr(task, 'expected_tools', None),
                    'agent_interactions': getattr(task, 'agent_interactions', None),
                    'chain_steps': getattr(task, 'chain_steps', None),
                    'graph_traversal': getattr(task, 'graph_traversal', None),
                    'conversation_turns': getattr(task, 'conversation_turns', None)
                }
                for task in self.extended_tasks
            ],
            'report': asdict(self.generate_hybrid_report()),
            # Add evaluator data for compatibility with dashboard
            'evaluators': {
                'quality': {
                    'evaluations': self.quality_evaluator.evaluations
                },
                'hallucination': {
                    'detections': self.hallucination_detector.detections
                },
                'retry': {
                    'attempts': self.retry_tracker.attempts
                },
                'tool_selection': {
                    'selections': self.tool_selection_tracker.selections
                },
                'agent_coordination': {
                    'interactions': self.agent_coordination_tracker.interactions
                },
                'workflow': {
                    'executions': self.workflow_tracker.executions
                },
                'tool_calls': {
                    'executions': self.tool_analyzer.executions
                }
            }
        }

        # RAG metrics
        data['rag_metrics'] = self.rag_metrics

        # 보안 트래커 데이터 (enable_security=True 로 생성된 경우)
        if getattr(self, 'input_sanitizer', None) is not None:
            security_data = self._get_security_evaluator_data()
            if security_data:
                data['evaluators']['security'] = security_data

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        print(f"✅ Hybrid evaluation results saved to: {filename}")

    @classmethod
    def load_from_file(cls, filename: str) -> 'HybridPerformanceMonitor':
        """Load results from JSON file"""
        # results/ 디렉토리에서 탐색 (현재 디렉토리에 없는 경우)
        if not os.path.exists(filename):
            from ..utils.path_helpers import get_evaluation_results_dir
            results_dir_file = os.path.join(get_evaluation_results_dir(), filename)
            if os.path.exists(results_dir_file):
                filename = results_dir_file

        with open(filename, encoding='utf-8') as f:
            data = json.load(f)

        # Check if security metrics are present in the data
        has_security_metrics = "security" in data.get("evaluators", {})

        # Create monitor instance
        monitor = cls(
            use_deepeval=False,
            use_ragas=False,
            use_langsmith=False,
            enable_security_metrics=has_security_metrics
        )

        # Restore tasks
        for task_data in data['tasks']:
            task = TaskResult(
                task_id=task_data['task_id'],
                task_type=task_data['task_type'],
                success=task_data['success'],
                completion_score=task_data['completion_score'],
                accuracy_score=task_data['accuracy_score'],
                execution_time=task_data['execution_time'],
                tokens_used=task_data['tokens_used'],
                tool_calls=task_data['tool_calls'],
                attempts=task_data['attempts'],
                errors=task_data['errors'],
                timestamp=datetime.fromisoformat(task_data['timestamp'])
            )

            # Record with native monitor using the parent class method
            super(HybridPerformanceMonitor, monitor).record_task(task)

            # Add extended task with only valid fields
            extended_task = ExtendedTaskResult(
                task_id=task_data['task_id'],
                task_type=task_data['task_type'],
                success=task_data['success'],
                completion_score=task_data['completion_score'],
                accuracy_score=task_data['accuracy_score'],
                execution_time=task_data['execution_time'],
                tokens_used=task_data['tokens_used'],
                tool_calls=task_data['tool_calls'],
                attempts=task_data['attempts'],
                errors=task_data['errors'],
                timestamp=datetime.fromisoformat(task_data['timestamp']),
                advanced_metrics=task_data.get('advanced_metrics', {}),
                evaluation_context=task_data.get('evaluation_context'),
                metric_providers_used=task_data.get('providers_used', task_data.get('metric_providers_used', []))
            )
            monitor.extended_tasks.append(extended_task)

        # Restore evaluator data (if available)
        evaluators = data.get("evaluators", {})

        if evaluators:
            # Quality evaluations
            if "quality" in evaluators:
                monitor.quality_evaluator.evaluations = evaluators["quality"].get("evaluations", [])

            # Hallucination detections
            if "hallucination" in evaluators:
                monitor.hallucination_detector.detections = evaluators["hallucination"].get("detections", [])

            # Retry attempts
            if "retry" in evaluators:
                monitor.retry_tracker.attempts = evaluators["retry"].get("attempts", [])

            # Tool selections
            if "tool_selection" in evaluators:
                monitor.tool_selection_tracker.selections = evaluators["tool_selection"].get("selections", [])

            # Agent interactions
            if "agent_coordination" in evaluators:
                monitor.agent_coordination_tracker.interactions = evaluators["agent_coordination"].get("interactions", [])

            # Workflow executions
            if "workflow" in evaluators:
                monitor.workflow_tracker.executions = evaluators["workflow"].get("executions", [])

            # Tool call executions
            if "tool_calls" in evaluators:
                monitor.tool_analyzer.executions = evaluators["tool_calls"].get("executions", [])

            # Security evaluators (Layer 1 & 2)
            if "security" in evaluators:
                security_data = evaluators["security"]

                # Input Sanitizer
                if "input_sanitizer" in security_data:
                    monitor.input_sanitizer.evaluations = security_data["input_sanitizer"].get("evaluations", [])

                # Output Leakage Detector
                if "output_leakage_detector" in security_data:
                    monitor.output_leakage_detector.detections = security_data["output_leakage_detector"].get("detections", [])

                # Tool Authorizer
                if "tool_authorizer" in security_data:
                    monitor.tool_authorizer.tool_calls = security_data["tool_authorizer"].get("tool_calls", [])

                # Privilege Escalation Detector
                if "privilege_escalation_detector" in security_data:
                    monitor.privilege_escalation_detector.escalation_events = security_data["privilege_escalation_detector"].get("escalation_events", [])

                # Tool Chain Attack Detector
                if "tool_chain_attack_detector" in security_data:
                    monitor.tool_chain_attack_detector.detections = security_data["tool_chain_attack_detector"].get("detections", [])

                print("   🔒 Restored security evaluators:")
                print(f"      - Input Sanitizer: {len(monitor.input_sanitizer.evaluations)} evaluations")
                print(f"      - Output Leakage: {len(monitor.output_leakage_detector.detections)} detections")
                print(f"      - Tool Authorizer: {len(monitor.tool_authorizer.tool_calls)} calls")
                print(f"      - Privilege Escalation: {len(monitor.privilege_escalation_detector.escalation_events)} events")
                print(f"      - Attack Detector: {len(monitor.tool_chain_attack_detector.detections)} detections")

        # Restore advanced_metrics_summary (DeepEval, Ragas 등)
        # Saved at top-level by save_to_file() and also inside report dict
        _ams = data.get("advanced_metrics_summary") or data.get("report", {}).get("advanced_metrics_summary")
        if _ams:
            monitor._advanced_metrics_summary = _ams
            print(f"   📊 Restored advanced metrics summary with {len(_ams)} metrics")

        # Restore rag_metrics
        if "rag_metrics" in data:
            monitor.rag_metrics = data["rag_metrics"]

        # Store evaluators data for Dashboard compatibility
        if "evaluators" in data:
            monitor.evaluators = data["evaluators"]

        print(f"✅ Loaded {len(monitor.extended_tasks)} tasks from {filename}")
        return monitor

    def print_summary(self):
        """Print comprehensive evaluation summary"""
        report = self.generate_hybrid_report()

        print("\n" + "="*70)
        print("HYBRID EVALUATION SUMMARY")
        print("="*70)

        # Native metrics
        print("\n📊 NATIVE METRICS")
        print(f"   Total Tasks: {report.total_tasks}")

        # CRITICAL FIX: Use correct keys from generate_report()
        # TCR is stored as accuracy_metrics['tcr']['tcr'], not 'overall_tcr'
        tcr_data = report.accuracy_metrics.get('tcr', {})
        tcr_value = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
        print(f"   Task Completion Rate: {tcr_value:.1f}%")

        # Accuracy is stored as accuracy_metrics['accuracy_scores']['overall_accuracy'], not 'average_accuracy'
        accuracy_data = report.accuracy_metrics.get('accuracy_scores', {})
        accuracy_value = accuracy_data.get('overall_accuracy', 0) if isinstance(accuracy_data, dict) else 0
        print(f"   Average Accuracy: {accuracy_value:.2f}%")

        print(f"   Average Latency: {report.efficiency_metrics.get('latency', {}).get('mean', 0):.2f}s")

        # CRITICAL FIX: Cost is in tokens metrics, not top-level efficiency_metrics
        tokens_data = report.efficiency_metrics.get('tokens', {})
        total_cost = tokens_data.get('total_cost', 0) if isinstance(tokens_data, dict) else 0
        print(f"   Total Cost: ${total_cost:.4f}")

        # Advanced metrics
        if report.advanced_metrics_summary:
            print(f"\n🔬 ADVANCED METRICS (Providers: {', '.join(report.providers_used)})")

            # G-Eval
            if 'g_eval_score' in report.advanced_metrics_summary:
                g_eval = report.advanced_metrics_summary['g_eval_score']
                mean_score = g_eval.get('mean', 0)
                count = g_eval.get('count', 0)
                print(f"   G-Eval Quality Score: {mean_score:.3f}/1.0 (n={count})")
                if 'g_eval_pass_rate' in report.advanced_metrics_summary:
                    pass_rate = report.advanced_metrics_summary['g_eval_pass_rate']
                    print(f"      Pass Rate: {pass_rate['passed']}/{pass_rate['total']} ({pass_rate['rate']*100:.1f}%)")
            else:
                if 'deepeval' in report.providers_used:
                    print("   ℹ️  G-Eval: Not evaluated (requires quality_criteria parameter)")

            # Hallucination
            if 'hallucination_score' in report.advanced_metrics_summary:
                hal_score = report.advanced_metrics_summary['hallucination_score']
                print(f"   Hallucination Score: {hal_score.get('mean', 0):.3f} (n={hal_score.get('count', 0)})")

            if 'hallucination_detection' in report.advanced_metrics_summary:
                hal = report.advanced_metrics_summary['hallucination_detection']
                print(f"   Hallucination Detection: {hal['detected']}/{hal['total']} ({hal['rate']*100:.1f}%)")

            # Toxicity
            if 'toxicity_score' in report.advanced_metrics_summary:
                tox_score = report.advanced_metrics_summary['toxicity_score']
                print(f"   Toxicity Score: {tox_score.get('mean', 0):.3f} (n={tox_score.get('count', 0)})")

            if 'toxicity_detection' in report.advanced_metrics_summary:
                tox = report.advanced_metrics_summary['toxicity_detection']
                print(f"   Toxicity Detection: {tox['detected']}/{tox['total']} ({tox['rate']*100:.1f}%)")

            # Bias
            if 'bias_score' in report.advanced_metrics_summary:
                bias_score = report.advanced_metrics_summary['bias_score']
                print(f"   Bias Score: {bias_score.get('mean', 0):.3f} (n={bias_score.get('count', 0)})")

            if 'bias_detection' in report.advanced_metrics_summary:
                bias = report.advanced_metrics_summary['bias_detection']
                print(f"   Bias Detection: {bias['detected']}/{bias['total']} ({bias['rate']*100:.1f}%)")

            # Answer Relevancy
            if 'answer_relevancy_score' in report.advanced_metrics_summary:
                rel_score = report.advanced_metrics_summary['answer_relevancy_score']
                print(f"   Answer Relevancy: {rel_score.get('mean', 0):.3f}/1.0 (n={rel_score.get('count', 0)})")

            # Ragas
            if 'ragas_overall_score' in report.advanced_metrics_summary:
                ragas = report.advanced_metrics_summary['ragas_overall_score']
                print(f"   Ragas RAG Quality: {ragas.get('mean', 0):.3f}/1.0 (n={ragas.get('count', 0)})")

            # Ragas sub-metrics (corrected to match actual metric names)
            ragas_metrics = ['ragas_faithfulness', 'ragas_context_precision', 'ragas_context_recall', 'ragas_answer_relevancy']
            for metric in ragas_metrics:
                if metric in report.advanced_metrics_summary:
                    data = report.advanced_metrics_summary[metric]
                    # Remove 'ragas_' prefix for display
                    metric_name = metric.replace('ragas_', '').replace('_', ' ').title()
                    print(f"      {metric_name}: {data.get('mean', 0):.3f}")
        else:
            print("\n📊 No advanced metrics (Enable with enable_advanced_metrics=True)")

        # Alerts
        if report.alerts:
            print(f"\n⚠️  ALERTS ({len(report.alerts)})")
            for alert in report.alerts[:5]:  # Show top 5
                print(f"   [{alert['severity']}] {alert['message']}")

        print("\n" + "="*70 + "\n")

    def _generate_advanced_recommendations(self, advanced_summary: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate recommendations based on advanced metrics"""
        recommendations = []

        if not advanced_summary:
            return recommendations

        # DeepEval G-Eval 권장사항
        if 'g_eval_score' in advanced_summary and isinstance(advanced_summary['g_eval_score'], dict):
            g_eval = advanced_summary['g_eval_score']['mean']
            if g_eval < 0.7:
                recommendations.append({
                    "area": "G-Eval 품질 개선",
                    "issue": f"G-Eval 평균 점수: {g_eval:.2f} (권장: 0.7 이상)",
                    "suggestion": "품질 기준 명확화, 프롬프트 개선, 출력 구조화",
                    "impact": "전반적인 응답 품질 향상"
                })

        # Hallucination Score 권장사항 (높을수록 좋음 - 환각이 없음을 의미)
        if 'hallucination_score' in advanced_summary and isinstance(advanced_summary['hallucination_score'], dict):
            hall_score = advanced_summary['hallucination_score']['mean']
            if hall_score < 0.7:
                recommendations.append({
                    "area": "환각 감소 (컨텍스트 일치도 향상)",
                    "issue": f"평균 환각 없음 점수: {hall_score:.2f} (권장: 0.7 이상)",
                    "suggestion": "Temperature 낮추기, 컨텍스트 강화, 사실 확인 단계 추가, RAG 검색 품질 개선",
                    "impact": "컨텍스트에 충실한 응답으로 신뢰도 향상"
                })

        # Toxicity Score 권장사항 (낮을수록 좋음)
        if 'toxicity_score' in advanced_summary and isinstance(advanced_summary['toxicity_score'], dict):
            tox_score = advanced_summary['toxicity_score']['mean']
            if tox_score > 0.3:
                recommendations.append({
                    "area": "독성 콘텐츠 감소",
                    "issue": f"평균 독성 점수: {tox_score:.2f} (권장: 0.3 이하)",
                    "suggestion": "Safety System Message 추가, 출력 필터링, 콘텐츠 검수 강화",
                    "impact": "안전하고 적절한 응답 생성"
                })

        # Bias Score 권장사항 (낮을수록 좋음)
        if 'bias_score' in advanced_summary and isinstance(advanced_summary['bias_score'], dict):
            bias_score = advanced_summary['bias_score']['mean']
            if bias_score > 0.3:
                recommendations.append({
                    "area": "편향 감소",
                    "issue": f"평균 편향 점수: {bias_score:.2f} (권장: 0.3 이하)",
                    "suggestion": "공정성 가이드라인 적용, 다양한 예제 사용, 편향 제거 프롬프트",
                    "impact": "공정하고 균형 잡힌 응답 생성"
                })

        # Answer Relevancy 권장사항 (높을수록 좋음)
        if 'answer_relevancy_score' in advanced_summary and isinstance(advanced_summary['answer_relevancy_score'], dict):
            relevancy = advanced_summary['answer_relevancy_score']['mean']
            if relevancy < 0.7:
                recommendations.append({
                    "area": "답변 관련성 개선",
                    "issue": f"평균 답변 관련성: {relevancy:.2f} (권장: 0.7 이상)",
                    "suggestion": "질문 분석 강화, 불필요한 정보 제거, 답변 포커스 개선",
                    "impact": "질문에 정확히 대응하는 답변 생성"
                })

        # RAGAS Faithfulness 권장사항
        if 'ragas_faithfulness' in advanced_summary and isinstance(advanced_summary['ragas_faithfulness'], dict):
            faithfulness = advanced_summary['ragas_faithfulness']['mean']
            if faithfulness < 0.7:
                recommendations.append({
                    "area": "RAG 충실도 개선",
                    "issue": f"평균 충실도: {faithfulness:.2f} (권장: 0.7 이상)",
                    "suggestion": "검색된 컨텍스트만 사용하도록 강제, 인용 추가, 주장 검증",
                    "impact": "컨텍스트 기반의 정확한 RAG 응답"
                })

        # RAGAS Context Precision 권장사항
        if 'ragas_context_precision' in advanced_summary and isinstance(advanced_summary['ragas_context_precision'], dict):
            precision = advanced_summary['ragas_context_precision']['mean']
            if precision < 0.7:
                recommendations.append({
                    "area": "RAG 컨텍스트 정밀도 개선",
                    "issue": f"평균 컨텍스트 정밀도: {precision:.2f} (권장: 0.7 이상)",
                    "suggestion": "검색 쿼리 최적화, Re-ranking 추가, 메타데이터 필터링",
                    "impact": "관련 정보만 검색하여 노이즈 감소"
                })

        # RAGAS Context Recall 권장사항
        if 'ragas_context_recall' in advanced_summary and isinstance(advanced_summary['ragas_context_recall'], dict):
            recall = advanced_summary['ragas_context_recall']['mean']
            if recall < 0.7:
                recommendations.append({
                    "area": "RAG 컨텍스트 재현율 개선",
                    "issue": f"평균 컨텍스트 재현율: {recall:.2f} (권장: 0.7 이상)",
                    "suggestion": "Top-K 증가, 하이브리드 검색(키워드+의미), 쿼리 확장",
                    "impact": "필요한 정보를 모두 검색하여 완전한 답변"
                })

        # RAGAS Answer Relevancy 권장사항 (높을수록 좋음)
        if 'ragas_answer_relevancy' in advanced_summary and isinstance(advanced_summary['ragas_answer_relevancy'], dict):
            ragas_relevancy = advanced_summary['ragas_answer_relevancy']['mean']
            if ragas_relevancy < 0.7:
                recommendations.append({
                    "area": "RAG 답변 관련성 개선",
                    "issue": f"평균 RAGAS 답변 관련성: {ragas_relevancy:.2f} (권장: 0.7 이상)",
                    "suggestion": "질문 이해 개선, 검색-생성 정렬 강화, 프롬프트에 질문 재강조",
                    "impact": "RAG 시스템에서 질문에 직접 관련된 답변 생성"
                })

        # RAGAS Overall Score 권장사항
        if 'ragas_overall_score' in advanced_summary and isinstance(advanced_summary['ragas_overall_score'], dict):
            overall = advanced_summary['ragas_overall_score']['mean']
            if overall < 0.6:
                recommendations.append({
                    "area": "RAG 시스템 전반 개선",
                    "issue": f"RAGAS 종합 점수: {overall:.2f} (권장: 0.6 이상)",
                    "suggestion": "RAG 파이프라인 전체 재검토, 임베딩 모델 업그레이드, 청킹 전략 개선",
                    "impact": "RAG 시스템의 전반적인 성능 향상"
                })

        return recommendations


# ============================================================================
# Convenience Functions
# ============================================================================

def create_monitor(
    profile: str = "balanced",
    output_dir: Optional[str] = None,
    **kwargs
) -> HybridPerformanceMonitor:
    """
    Create monitor with preset profiles

    Profiles:
    - "minimal": Native metrics only (fastest, free)
    - "balanced": Native + DeepEval (recommended)
    - "rag": Native + DeepEval + Ragas (for RAG systems)
    - "full": All providers (requires LangSmith)
    - "secure": Balanced + Security Metrics (for production)
    - "secure-full": Full + Security Metrics (comprehensive monitoring)

    Args:
        profile: Preset profile name
        output_dir: Output directory (None이면 자동 감지)
        **kwargs: Override profile settings (e.g., enable_security_metrics=True, security_config={...})

    Returns:
        Configured HybridPerformanceMonitor

    Examples:
        >>> # Basic balanced profile
        >>> monitor = create_monitor(profile="balanced")

        >>> # Secure profile with custom security config
        >>> monitor = create_monitor(
        ...     profile="secure",
        ...     security_config={
        ...         'allowed_tools': ['search', 'read'],
        ...         'restricted_tools': ['delete', 'execute']
        ...     }
        ... )

        >>> # Override security for any profile
        >>> monitor = create_monitor(
        ...     profile="balanced",
        ...     enable_security_metrics=True
        ... )
    """
    profiles = {
        "minimal": {
            "use_deepeval": False,
            "use_ragas": False,
            "use_langsmith": False,
            "enable_security_metrics": False
        },
        "balanced": {
            "use_deepeval": True,
            "use_ragas": False,
            "use_langsmith": False,
            "deepeval_model": "gpt-4o-mini",
            "enable_security_metrics": False
        },
        "rag": {
            "use_deepeval": True,
            "use_ragas": True,
            "use_langsmith": False,
            "deepeval_model": "gpt-4o-mini",
            "ragas_model": "gpt-4o-mini",
            "enable_security_metrics": False
        },
        "full": {
            "use_deepeval": True,
            "use_ragas": True,
            "use_langsmith": True,
            "deepeval_model": "gpt-4o",
            "ragas_model": "gpt-4o",
            "enable_security_metrics": False
        },
        "secure": {
            "use_deepeval": True,
            "use_ragas": False,
            "use_langsmith": False,
            "deepeval_model": "gpt-4o-mini",
            "enable_security_metrics": True,
            "security_config": {
                "allowed_tools": None,  # Allow all by default
                "restricted_tools": ["execute_command", "delete_file", "drop_table"]
            }
        },
        "secure-full": {
            "use_deepeval": True,
            "use_ragas": True,
            "use_langsmith": True,
            "deepeval_model": "gpt-4o",
            "ragas_model": "gpt-4o",
            "enable_security_metrics": True,
            "security_config": {
                "allowed_tools": None,
                "restricted_tools": ["execute_command", "delete_file", "drop_table"]
            }
        }
    }

    if profile not in profiles:
        raise ValueError(f"Unknown profile: {profile}. Choose from: {list(profiles.keys())}")

    # Create a copy of the profile config to avoid modifying the original
    config = profiles[profile].copy()
    config['output_dir'] = output_dir  # Add output_dir to config
    config.update(kwargs)  # Override with user settings

    return HybridPerformanceMonitor(**config)


if __name__ == "__main__":
    # Test initialization
    print("\nTesting Hybrid Monitor Initialization...")

    monitor = create_monitor(profile="balanced")
    monitor.print_summary()
