"""
Test Transparency Manager
==========================
평가 프로세스의 투명성을 관리하는 모듈

주요 기능:
1. 투명성 리포트 생성
2. 메트릭 계산 추적 (Traces)
3. 주석 및 코멘트 추가 (Annotations)
4. 감사 로그 기록 (Audit Logs)
5. 투명성 요약 생성
"""

import json
import statistics
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AnnotationType(Enum):
    """Annotation types"""
    NOTE = "note"
    WARNING = "warning"
    REVIEW = "review"
    IMPROVEMENT = "improvement"
    BUG = "bug"
    QUESTION = "question"


class TestStepStatus(Enum):
    """Test step status"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


class TestTransparencyManager:
    """
    Enhanced transparency manager for dashboard with insights and analysis
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Args:
            output_dir: Base output directory (None이면 자동 감지)
        """
        # Zero Configuration: 자동 경로 감지
        if output_dir is None:
            from .path_helpers import get_evaluation_results_dir
            self.output_dir = get_evaluation_results_dir(create=False)
        else:
            self.output_dir = Path(output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        self.traces_dir = self.output_dir / "traces"
        self.annotations_dir = self.output_dir / "annotations"
        self.audit_logs_dir = self.output_dir / "audit_logs"

        for dir_path in [self.traces_dir, self.annotations_dir, self.audit_logs_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Data storage
        self.traces: Dict[str, Dict[str, Any]] = {}
        self.annotations: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: List[Dict[str, Any]] = []
        self.reports: List[Dict[str, Any]] = []  # Track generated reports

    # -------------------------------------------------------------------------
    # Metric Calculation Traces
    # -------------------------------------------------------------------------

    def start_metric_calculation(
        self,
        metric_name: str,
        metric_type: str,
        task_id: Optional[str] = None
    ) -> str:
        """
        Start tracking a metric calculation

        Args:
            metric_name: Name of the metric (tcr, accuracy, etc.)
            metric_type: Type (basic, quality, detection, performance)
            task_id: Optional task ID

        Returns:
            trace_id: Unique trace identifier
        """
        trace_id = f"trace_{metric_name}_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now()

        self.traces[trace_id] = {
            "trace_id": trace_id,
            "metric_name": metric_name,
            "metric_type": metric_type,
            "task_id": task_id,
            "start_time": timestamp.isoformat(),
            "steps": [],
            "status": "in_progress",
            "final_value": None,
            "metadata": {}
        }

        return trace_id

    def add_calculation_step(
        self,
        trace_id: str,
        step_name: str,
        description: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        status: TestStepStatus
    ):
        """
        Add a calculation step to a trace

        Args:
            trace_id: Trace identifier
            step_name: Name of the step
            description: Step description
            input_data: Input data for this step
            output_data: Output data from this step
            status: Step status
        """
        if trace_id not in self.traces:
            raise ValueError(f"Trace {trace_id} not found")

        step = {
            "step_name": step_name,
            "description": description,
            "input_data": input_data,
            "output_data": output_data,
            "status": status.value if isinstance(status, TestStepStatus) else status,
            "timestamp": datetime.now().isoformat()
        }

        self.traces[trace_id]["steps"].append(step)

    def complete_metric_calculation(
        self,
        trace_id: str,
        final_value: Any,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Complete a metric calculation trace

        Args:
            trace_id: Trace identifier
            final_value: Final calculated value
            metadata: Additional metadata
        """
        if trace_id not in self.traces:
            raise ValueError(f"Trace {trace_id} not found")

        self.traces[trace_id].update({
            "status": "completed",
            "end_time": datetime.now().isoformat(),
            "final_value": final_value,
            "metadata": metadata or {}
        })

        # Save trace to file
        self._save_trace(trace_id)

    def _save_trace(self, trace_id: str):
        """Save trace to JSON file"""
        if trace_id not in self.traces:
            return

        filepath = self.traces_dir / f"{trace_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.traces[trace_id], f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Annotations
    # -------------------------------------------------------------------------

    def add_annotation(
        self,
        target_type: str,
        target_id: str,
        annotation_type: AnnotationType,
        priority: str,
        title: str,
        content: str,
        author: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add an annotation

        Args:
            target_type: Type of target (metric, task, dataset, etc.)
            target_id: ID of the target
            annotation_type: Type of annotation
            priority: Priority level (low, medium, high, critical)
            title: Annotation title
            content: Annotation content
            author: Author name
            metadata: Additional metadata

        Returns:
            annotation_id: Unique annotation identifier
        """
        annotation_id = f"annotation_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now()

        annotation = {
            "annotation_id": annotation_id,
            "target_type": target_type,
            "target_id": target_id,
            "annotation_type": annotation_type.value if isinstance(annotation_type, AnnotationType) else annotation_type,
            "priority": priority,
            "title": title,
            "content": content,
            "author": author,
            "timestamp": timestamp.isoformat(),
            "created_at": timestamp.isoformat(),  # For dashboard compatibility
            "status": "open",  # Default status
            "replies": [],
            "tags": [],  # Default empty tags
            "related_metric": None,  # Optional related metric
            "related_value": None,  # Optional related value
            "metadata": metadata or {}
        }

        self.annotations[annotation_id] = annotation

        # Save annotation to file
        self._save_annotation(annotation_id)

        return annotation_id

    def add_reply_to_annotation(
        self,
        annotation_id: str,
        author: str,
        content: str
    ):
        """
        Add a reply to an annotation

        Args:
            annotation_id: Annotation identifier
            author: Reply author
            content: Reply content
        """
        if annotation_id not in self.annotations:
            raise ValueError(f"Annotation {annotation_id} not found")

        timestamp = datetime.now()
        reply = {
            "reply_id": f"reply_{uuid.uuid4().hex[:8]}",
            "author": author,
            "content": content,
            "timestamp": timestamp.isoformat(),
            "created_at": timestamp.isoformat()  # For dashboard compatibility
        }

        self.annotations[annotation_id]["replies"].append(reply)

        # Update saved file
        self._save_annotation(annotation_id)

    def _save_annotation(self, annotation_id: str):
        """Save annotation to JSON file"""
        if annotation_id not in self.annotations:
            return

        filepath = self.annotations_dir / f"{annotation_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.annotations[annotation_id], f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Audit Logs
    # -------------------------------------------------------------------------

    def log_event(
        self,
        event_type: str,
        user: str,
        action: str,
        target_type: str,
        target_id: str,
        details: Dict[str, Any],
        success: bool = True
    ):
        """
        Log an audit event

        Args:
            event_type: Type of event
            user: User who performed the action
            action: Action description
            target_type: Type of target
            target_id: ID of target
            details: Additional details
            success: Whether the action was successful
        """
        log_entry = {
            "log_id": f"audit_{uuid.uuid4().hex[:8]}",
            "event_type": event_type,
            "user": user,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }

        self.audit_logs.append(log_entry)

        # Save audit log to file
        self._save_audit_log(log_entry)

        return log_entry

    def _save_audit_log(self, log_entry: Dict[str, Any]):
        """Save audit log entry to JSON file"""
        filepath = self.audit_logs_dir / f"{log_entry['log_id']}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------

    def generate_transparent_report(
        self,
        task_id: str,
        task_type: str,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
        monitor: Optional[Any] = None,
        auto_save: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive transparency report with enhanced features

        New Features:
        - Phase 1: Auto-extract test configuration from metadata/monitor
        - Phase 2: Already supported (metric calculation traces)
        - Phase 3: Auto-calculate reliability analysis (if monitor provided)
        - Phase 4: Already supported (annotations + audit_logs timeline)
        - Phase 5: Auto-compare with previous report

        Args:
            task_id: Task ID
            task_type: Task type
            success: Success status
            metadata: Additional metadata
            monitor: Optional PerformanceMonitor for enhanced analysis
            auto_save: Auto-save report to file (default: True)

        Returns:
            Report dictionary with enhanced transparency data
        """
        report = {
            "report_id": f"report_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "task_id": task_id,
            "task_type": task_type,
            "success": success,
            "generated_at": datetime.now().isoformat(),
            "traces": list(self.traces.values()),
            "annotations": list(self.annotations.values()),
            "audit_logs": self.audit_logs,
            "metadata": metadata or {}
        }

        # Phase 1: Extract test configuration
        if not report["metadata"].get("test_configuration"):
            report["metadata"]["test_configuration"] = self._extract_test_configuration(metadata, monitor)

        # Add summary metrics
        report["summary"] = {
            "total_tasks": len(report["traces"]) if report["traces"] else 0,
            "anomalies_detected": 0,  # Will be calculated if monitor provided
            "warnings": 0,
            "data_quality_score": 100.0
        }

        # Phase 3: Calculate reliability analysis
        if monitor:
            report["reliability_analysis"] = self._calculate_reliability(monitor)

            # Add anomalies and quality report
            anomalies = self.analyze_metric_anomalies(monitor)
            report["anomalies"] = anomalies
            report["summary"]["anomalies_detected"] = len(anomalies.get("anomalies", []))
            report["summary"]["warnings"] = len(anomalies.get("warnings", []))

            quality_report = self.generate_data_quality_report(monitor)
            report["quality_report"] = quality_report
            report["summary"]["data_quality_score"] = quality_report.get("overall_score", 100.0)

            # Add actionable insights
            report["actionable_insights"] = self.generate_actionable_insights(monitor)

        # Phase 5: Compare with previous report
        report["comparison"] = self._compare_with_previous(task_id, report, monitor)

        self.reports.append(report)

        # Auto-save to transparent_reports directory
        if auto_save:
            self.save_report(report)

        return report

    # -------------------------------------------------------------------------
    # Phase 1-5 Helper Methods
    # -------------------------------------------------------------------------

    def _extract_test_configuration(
        self,
        metadata: Optional[Dict[str, Any]],
        monitor: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Phase 1: Extract test configuration from metadata or monitor

        Args:
            metadata: Report metadata
            monitor: Optional PerformanceMonitor

        Returns:
            Test configuration dictionary
        """
        config = {}

        # Extract from metadata
        if metadata:
            config.update({
                "environment": metadata.get("environment", "unknown"),
                "framework": metadata.get("framework", "unknown"),
                "model_name": metadata.get("model_name", "unknown"),
                "dataset_path": metadata.get("dataset_path", "N/A"),
                "evaluator": metadata.get("evaluator", "System"),
                "description": metadata.get("description", "")
            })

        # Extract thresholds from monitor
        if monitor and hasattr(monitor, "thresholds"):
            config["thresholds"] = monitor.thresholds

        # Ensure required fields
        if "environment" not in config:
            config["environment"] = "production"
        if "framework" not in config:
            config["framework"] = "custom"
        if "model_name" not in config:
            config["model_name"] = "unknown"

        return config

    def _calculate_reliability(self, monitor) -> Dict[str, Any]:
        """
        Phase 3: Calculate reliability analysis

        Args:
            monitor: PerformanceMonitor

        Returns:
            Reliability analysis dictionary
        """

        # Get tasks
        tasks = getattr(monitor, 'tasks', None) or getattr(monitor.tcr_tracker, 'tasks', [])
        sample_size = len(tasks)

        # Minimum required samples
        min_required = 30
        sufficient = sample_size >= min_required

        # Calculate variance and standard error for accuracy
        accuracy_scores = [
            t.accuracy_score for t in tasks
            if hasattr(t, 'accuracy_score') and t.accuracy_score is not None
        ]

        variance = 0.0
        std_error = 0.0
        confidence = 0.0

        if len(accuracy_scores) >= 2:
            variance = statistics.variance(accuracy_scores)
            std_error = statistics.stdev(accuracy_scores) / (len(accuracy_scores) ** 0.5)
            # Simplified confidence level (95% confidence interval)
            confidence = 95.0 if sufficient else 80.0

        # Generate warnings
        warnings = []
        if not sufficient:
            warnings.append(f"샘플 크기가 부족합니다 ({sample_size}/{min_required}). 최소 {min_required}개 이상 권장")

        if variance > 0.1:
            warnings.append(f"정확도 분산이 높습니다 ({variance:.4f}). 결과의 일관성이 낮을 수 있습니다")

        # Generate recommendations
        recommendations = []
        if not sufficient:
            recommendations.append(f"최소 {min_required - sample_size}개 이상의 추가 평가를 수행하세요")

        if variance > 0.1:
            recommendations.append("평가 데이터셋의 난이도 분포를 균일하게 조정하세요")
            recommendations.append("프롬프트 템플릿을 표준화하여 일관성을 높이세요")

        return {
            "sample_size": sample_size,
            "min_required_samples": min_required,
            "sufficient": sufficient,
            "confidence_level": confidence,
            "variance": variance,
            "standard_error": std_error,
            "warnings": warnings,
            "recommendations": recommendations
        }

    def _compare_with_previous(
        self,
        task_id: str,
        current_report: Dict[str, Any],
        monitor: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Phase 5: Compare with previous report

        Args:
            task_id: Current task ID
            current_report: Current report data
            monitor: Optional PerformanceMonitor

        Returns:
            Comparison dictionary
        """
        # Find previous reports for the same task_id pattern
        task_prefix = task_id.rsplit('_', 1)[0] if '_' in task_id else task_id
        previous_reports = [
            r for r in self.reports
            if r.get('task_id', '').startswith(task_prefix) and r != current_report
        ]

        if not previous_reports:
            return {}

        # Get most recent previous report
        previous_report = sorted(
            previous_reports,
            key=lambda x: x.get('generated_at', ''),
            reverse=True
        )[0]

        comparison = {
            "previous_report_id": previous_report.get('report_id'),
            "previous_generated_at": previous_report.get('generated_at'),
            "metric_changes": {}
        }

        # Compare metrics if monitor provided
        if monitor:
            current_metrics = {}
            previous_quality = previous_report.get('quality_report', {})

            # Get current metrics
            tasks = getattr(monitor, 'tasks', None) or getattr(monitor.tcr_tracker, 'tasks', [])
            if tasks:
                # TCR
                tcr_data = monitor.tcr_tracker.calculate_tcr() if hasattr(monitor, 'tcr_tracker') else {}
                current_metrics['tcr'] = tcr_data.get('tcr', 0)

                # Accuracy
                accuracy_scores = [t.accuracy_score for t in tasks if hasattr(t, 'accuracy_score') and t.accuracy_score is not None]
                if accuracy_scores:
                    current_metrics['accuracy'] = sum(accuracy_scores) / len(accuracy_scores) * 100

            # Compare with previous
            prev_quality_data = previous_quality.get('data_completeness', {})

            for metric_name, current_value in current_metrics.items():
                # Try to extract previous value from quality report
                previous_value = None

                if metric_name == 'tcr':
                    # Estimate from previous data
                    prev_total = prev_quality_data.get('total_tasks', 0)
                    prev_with_scores = prev_quality_data.get('tasks_with_scores', 0)
                    if prev_total > 0:
                        previous_value = (prev_with_scores / prev_total) * 100
                elif metric_name == 'accuracy':
                    # Would need to be stored in previous report
                    previous_value = None  # Not available in current structure

                if previous_value is not None:
                    change = current_value - previous_value
                    change_percent = (change / previous_value * 100) if previous_value != 0 else 0

                    comparison["metric_changes"][metric_name] = {
                        "previous": previous_value,
                        "current": current_value,
                        "change": change,
                        "change_percent": change_percent
                    }

        # Generate summary
        if comparison["metric_changes"]:
            improved = sum(1 for m in comparison["metric_changes"].values() if m['change'] > 0)
            degraded = sum(1 for m in comparison["metric_changes"].values() if m['change'] < 0)

            if improved > degraded:
                comparison["summary"] = f"{improved}개 메트릭 개선, {degraded}개 메트릭 저하"
            elif degraded > improved:
                comparison["summary"] = f"{degraded}개 메트릭 저하, {improved}개 메트릭 개선"
            else:
                comparison["summary"] = "메트릭 변화 없음"

        return comparison

    # -------------------------------------------------------------------------
    # Analysis & Insights
    # -------------------------------------------------------------------------

    def analyze_metric_anomalies(self, monitor) -> Dict[str, Any]:
        """Analyze metrics for anomalies and inconsistencies"""
        anomalies = []
        warnings = []
        insights = []

        try:
            # Get TCR if available
            # CRITICAL FIX: Use get_tcr_by_type() instead of non-existent get_tcr()
            if hasattr(monitor, 'tcr_tracker'):
                tcr_data = monitor.tcr_tracker.get_tcr_by_type()
                # Extract overall TCR from the returned dictionary
                tcr = tcr_data.get('overall', {}).get('tcr', None) if tcr_data else None
            else:
                tcr = None

            if tcr is not None:
                if tcr < 50:
                    anomalies.append({
                        "severity": "high",
                        "title": "매우 낮은 작업 완료율",
                        "description": f"TCR이 {tcr:.1f}%로 매우 낮습니다. 절반 이상의 작업이 실패하고 있습니다.",
                        "recommendation": "실패 원인을 즉시 조사하고, 입력 데이터 품질과 모델 설정을 재검토하세요."
                    })
                elif tcr < 70:
                    warnings.append({
                        "severity": "medium",
                        "title": "낮은 작업 완료율",
                        "description": f"TCR이 {tcr:.1f}%입니다. 30% 이상의 작업이 실패하고 있습니다.",
                        "recommendation": "에러 로그를 확인하고 실패 패턴을 분석하세요."
                    })
                elif tcr >= 95:
                    insights.append({
                        "title": "우수한 작업 완료율",
                        "description": f"TCR이 {tcr:.1f}%로 매우 높습니다!",
                        "action": "현재 설정을 유지하고 다른 프로젝트에도 적용을 고려하세요."
                    })

        except Exception:
            pass

        return {
            "anomalies": anomalies,
            "warnings": warnings,
            "insights": insights
        }

    def analyze_metric_correlations(self, monitor) -> Dict[str, Any]:
        """Analyze correlations between metrics"""
        correlations = []

        # Placeholder implementation
        return {
            "correlations": correlations,
            "strong_positive": [],
            "strong_negative": [],
            "insights": []
        }

    def identify_performance_bottlenecks(self, monitor) -> Dict[str, Any]:
        """Identify performance bottlenecks"""
        bottlenecks = []

        # Placeholder implementation
        return {
            "bottlenecks": bottlenecks,
            "critical": [],
            "moderate": [],
            "recommendations": []
        }

    def generate_data_quality_report(self, monitor) -> Dict[str, Any]:
        """Generate data quality report"""
        quality_issues = []
        passed_checks = []

        # Get basic statistics
        tasks = getattr(monitor, 'tasks', None) or getattr(monitor.tcr_tracker, 'tasks', [])
        total_tasks = len(tasks)
        tasks_with_scores = sum(1 for t in tasks if hasattr(t, 'accuracy_score') and t.accuracy_score is not None)

        # Check if quality evaluator has data
        quality_evaluated = 0
        if hasattr(monitor, 'quality_evaluator'):
            quality_metrics = monitor.quality_evaluator.get_quality_metrics()
            if quality_metrics and 'evaluations' in quality_metrics:
                quality_evaluated = len(quality_metrics['evaluations'])

        # Data completeness checks
        completeness_score = 100.0

        if total_tasks == 0:
            quality_issues.append({
                "severity": "critical",
                "type": "No Data",
                "description": "No tasks have been evaluated",
                "recommendation": "Run evaluation to collect data"
            })
            completeness_score = 0.0
        else:
            # Check for tasks without scores
            if tasks_with_scores < total_tasks:
                missing_ratio = (total_tasks - tasks_with_scores) / total_tasks
                if missing_ratio > 0.5:
                    quality_issues.append({
                        "severity": "high",
                        "type": "Incomplete Scoring",
                        "description": f"{total_tasks - tasks_with_scores} tasks missing accuracy scores ({missing_ratio*100:.1f}%)",
                        "recommendation": "Ensure all tasks have accuracy evaluation"
                    })
                    completeness_score -= 30
                elif missing_ratio > 0.2:
                    quality_issues.append({
                        "severity": "medium",
                        "type": "Partial Scoring",
                        "description": f"{total_tasks - tasks_with_scores} tasks missing accuracy scores ({missing_ratio*100:.1f}%)",
                        "recommendation": "Review scoring coverage"
                    })
                    completeness_score -= 15
                else:
                    passed_checks.append({
                        "check": "Scoring Coverage",
                        "result": f"{tasks_with_scores}/{total_tasks} tasks scored ({tasks_with_scores/total_tasks*100:.1f}%)"
                    })
            else:
                passed_checks.append({
                    "check": "Scoring Coverage",
                    "result": "100% - All tasks have scores"
                })

            # Check for quality evaluation
            if quality_evaluated == 0:
                quality_issues.append({
                    "severity": "low",
                    "type": "No Quality Evaluation",
                    "description": "No quality evaluations performed",
                    "recommendation": "Use quality_evaluator.evaluate_response() for detailed quality metrics"
                })
                completeness_score -= 10
            else:
                passed_checks.append({
                    "check": "Quality Evaluation",
                    "result": f"{quality_evaluated} tasks evaluated"
                })

        # Calculate overall score
        overall_score = max(0.0, min(100.0, completeness_score))

        return {
            "overall_score": overall_score,
            "data_completeness": {
                "total_tasks": total_tasks,
                "tasks_with_scores": tasks_with_scores,
                "quality_evaluated": quality_evaluated
            },
            "quality_issues": quality_issues,
            "passed_checks": passed_checks
        }

    def generate_actionable_insights(self, monitor) -> List[Dict[str, Any]]:
        """Generate actionable insights from metrics"""
        insights = []

        # Get metrics
        tasks = getattr(monitor, 'tasks', None) or getattr(monitor.tcr_tracker, 'tasks', [])
        total_tasks = len(tasks)
        if total_tasks == 0:
            return insights

        # Get TCR
        tcr = None
        if hasattr(monitor, 'tcr_tracker'):
            tcr_data = monitor.tcr_tracker.calculate_tcr()
            tcr = tcr_data.get('tcr', 0)

        # Get average accuracy
        avg_accuracy = 0
        tasks_with_accuracy = [t for t in tasks if hasattr(t, 'accuracy_score') and t.accuracy_score is not None]
        if tasks_with_accuracy:
            avg_accuracy = sum(t.accuracy_score for t in tasks_with_accuracy) / len(tasks_with_accuracy) * 100

        # Get quality metrics
        quality_evaluated = 0
        if hasattr(monitor, 'quality_evaluator'):
            quality_metrics = monitor.quality_evaluator.get_quality_metrics()
            if quality_metrics and 'evaluations' in quality_metrics:
                quality_evaluated = len(quality_metrics['evaluations'])

        # Insight 1: Low TCR
        if tcr is not None and tcr < 80:
            insights.append({
                "priority": "high",
                "title": "작업 완료율 개선 필요",
                "category": "Performance",
                "current_state": f"현재 TCR은 {tcr:.1f}%로 목표치(80%) 미달",
                "action": "실패 원인을 분석하고 입력 데이터 품질 개선",
                "expected_impact": "TCR을 80% 이상으로 향상",
                "implementation": [
                    "실패한 작업의 에러 로그 수집 및 분석",
                    "입력 프롬프트 품질 검토",
                    "모델 파라미터 조정 (temperature, max_tokens 등)"
                ]
            })

        # Insight 2: Low Accuracy
        if avg_accuracy > 0 and avg_accuracy < 80:
            insights.append({
                "priority": "high",
                "title": "정확도 개선 필요",
                "category": "Quality",
                "current_state": f"평균 정확도 {avg_accuracy:.1f}%로 목표치(80%) 미달",
                "action": "Golden Dataset 품질 개선 및 모델 평가 재검토",
                "expected_impact": "정확도를 80% 이상으로 향상",
                "implementation": [
                    "Golden Dataset의 기대 답변 품질 검토",
                    "모호한 QA 쌍 수정 또는 제거",
                    "평가 메트릭 조정 (semantic similarity threshold 등)"
                ]
            })

        # Insight 3: No quality evaluation
        if quality_evaluated == 0 and total_tasks > 0:
            insights.append({
                "priority": "medium",
                "title": "품질 평가 활성화 권장",
                "category": "Data Quality",
                "current_state": "현재 품질 평가가 수행되지 않음",
                "action": "quality_evaluator를 사용하여 응답 품질 평가",
                "expected_impact": "더 상세한 품질 인사이트 확보",
                "implementation": [
                    "monitor.quality_evaluator.evaluate_response() 호출 추가",
                    "각 응답에 대해 completeness, relevance, clarity 평가",
                    "품질 메트릭을 대시보드에서 모니터링"
                ]
            })

        # Insight 4: Good performance
        if tcr is not None and tcr >= 90 and avg_accuracy >= 85:
            insights.append({
                "priority": "low",
                "title": "우수한 성능 유지 중",
                "category": "Success",
                "current_state": f"TCR {tcr:.1f}%, 정확도 {avg_accuracy:.1f}%로 목표 초과 달성",
                "action": "현재 설정 및 프로세스를 문서화하고 다른 프로젝트에 적용",
                "expected_impact": "모범 사례 확산 및 전체 품질 향상",
                "implementation": [
                    "현재 설정 및 프롬프트를 문서화",
                    "Golden Dataset을 템플릿으로 공유",
                    "정기적인 모니터링으로 품질 유지"
                ]
            })

        return insights

    # -------------------------------------------------------------------------
    # Load Methods for Dashboard
    # -------------------------------------------------------------------------

    def load_annotations(
        self,
        annotation_type: Optional[str] = None,
        status: Optional[str] = None,
        target_type: Optional[str] = None,
        priority: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Load annotations from files

        Args:
            annotation_type: Filter by annotation type
            status: Filter by status
            target_type: Filter by target type
            priority: Filter by priority

        Returns:
            List of annotation dictionaries
        """
        annotations = []

        # Load from files
        if self.annotations_dir.exists():
            # Try both individual files and batch files
            for filepath in self.annotations_dir.glob("annotation*.json"):
                try:
                    with open(filepath, encoding='utf-8') as f:
                        data = json.load(f)
                        # Check if it's a batch file with "annotations" key
                        if isinstance(data, dict) and 'annotations' in data:
                            annotations.extend(data['annotations'])
                        # Or individual annotation file
                        elif isinstance(data, dict):
                            annotations.append(data)
                except Exception as e:
                    print(f"Error loading annotation {filepath}: {e}")

        # Also include in-memory annotations
        for ann_id, annotation in self.annotations.items():
            if not any(a.get('annotation_id') == ann_id for a in annotations):
                annotations.append(annotation)

        # Apply filters
        filtered = annotations

        if annotation_type:
            filtered = [a for a in filtered if a.get('annotation_type') == annotation_type]

        if status:
            filtered = [a for a in filtered if a.get('status') == status]

        if target_type:
            filtered = [a for a in filtered if a.get('target_type') == target_type]

        if priority:
            filtered = [a for a in filtered if a.get('priority') == priority]

        return filtered

    def load_audit_logs(
        self,
        event_type: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Load audit logs from files

        Args:
            event_type: Filter by event type
            user: Filter by user
            limit: Maximum number of logs to return

        Returns:
            List of audit log dictionaries
        """
        logs = []

        # Load from files
        if self.audit_logs_dir.exists():
            for filepath in sorted(
                self.audit_logs_dir.glob("audit*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            ):
                try:
                    with open(filepath, encoding='utf-8') as f:
                        data = json.load(f)
                        # Check if it's a batch file with "audit_logs" key
                        if isinstance(data, dict) and 'audit_logs' in data:
                            logs.extend(data['audit_logs'])
                        # Or individual log file
                        elif isinstance(data, dict):
                            logs.append(data)
                except Exception as e:
                    print(f"Error loading audit log {filepath}: {e}")

        # Also include in-memory logs
        for log in self.audit_logs:
            if not any(l.get('log_id') == log.get('log_id') for l in logs):
                logs.append(log)

        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Apply filters
        filtered = logs

        if event_type:
            filtered = [l for l in filtered if l.get('event_type') == event_type]

        if user:
            filtered = [l for l in filtered if user.lower() in l.get('user', '').lower()]

        # Apply limit
        return filtered[:limit]

    def load_traces(
        self,
        metric_name: Optional[str] = None,
        metric_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Load metric calculation traces from files

        Args:
            metric_name: Filter by metric name
            metric_type: Filter by metric type
            status: Filter by status (in_progress, completed, failed)

        Returns:
            List of trace dictionaries
        """
        traces = []

        # Load from files
        if self.traces_dir.exists():
            for filepath in self.traces_dir.glob("trace_*.json"):
                try:
                    with open(filepath, encoding='utf-8') as f:
                        trace = json.load(f)
                        traces.append(trace)
                except Exception as e:
                    print(f"Error loading trace {filepath}: {e}")

        # Also include in-memory traces
        for trace_id, trace in self.traces.items():
            if not any(t.get('trace_id') == trace_id for t in traces):
                traces.append(trace)

        # Apply filters
        filtered = traces

        if metric_name:
            filtered = [t for t in filtered if t.get('metric_name') == metric_name]

        if metric_type:
            filtered = [t for t in filtered if t.get('metric_type') == metric_type]

        if status:
            filtered = [t for t in filtered if t.get('status') == status]

        return filtered

    # -------------------------------------------------------------------------
    # Report Management
    # -------------------------------------------------------------------------

    def save_report(
        self,
        report: Dict[str, Any],
        filename: Optional[str] = None
    ) -> Path:
        """
        Save a report to transparent_reports directory

        Args:
            report: Report dictionary to save
            filename: Optional filename (defaults to report_id)

        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"{report.get('report_id', 'report')}.json"

        # Save to transparent_reports subdirectory for dashboard compatibility
        reports_dir = self.output_dir / "transparent_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        filepath = reports_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return filepath

    def save_all_reports(self) -> List[Path]:
        """
        Save all generated reports to files

        Returns:
            List of saved file paths
        """
        saved_files = []
        for report in self.reports:
            filepath = self.save_report(report)
            saved_files.append(filepath)

        return saved_files

    def get_transparency_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of transparency data

        Returns:
            Summary dictionary with counts and report info
        """
        return {
            "total_reports": len(self.reports),
            "total_traces": len(self.traces),
            "total_annotations": len(self.annotations),
            "total_audit_logs": len(self.audit_logs),
            "reports": [
                {
                    "report_id": report.get("report_id"),
                    "task_id": report.get("task_id"),
                    "task_type": report.get("task_type"),
                    "success": report.get("success"),
                    "generated_at": report.get("generated_at"),
                    "traces_count": len(report.get("traces", [])),
                    "annotations_count": len(report.get("annotations", [])),
                    "audit_logs_count": len(report.get("audit_logs", []))
                }
                for report in self.reports
            ]
        }

    # -------------------------------------------------------------------------
    # Report Version Management
    # -------------------------------------------------------------------------

    def list_report_versions(self, task_id_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all report versions, optionally filtered by task_id prefix

        Args:
            task_id_prefix: Optional prefix to filter reports

        Returns:
            List of report metadata sorted by date (newest first)
        """
        import json

        reports_dir = self.output_dir / "transparent_reports"

        if not reports_dir.exists():
            return []

        report_files = list(reports_dir.glob("*.json"))
        report_list = []

        for report_file in report_files:
            try:
                with open(report_file, encoding='utf-8') as f:
                    report_data = json.load(f)

                task_id = report_data.get('task_id', '')

                # Filter by prefix if provided
                if task_id_prefix and not task_id.startswith(task_id_prefix):
                    continue

                report_list.append({
                    "report_id": report_data.get('report_id'),
                    "task_id": task_id,
                    "task_type": report_data.get('task_type'),
                    "success": report_data.get('success'),
                    "generated_at": report_data.get('generated_at'),
                    "file_path": str(report_file),
                    "data_quality_score": report_data.get('quality_report', {}).get('overall_score', 0),
                    "has_comparison": bool(report_data.get('comparison', {}).get('metric_changes'))
                })
            except Exception:
                continue

        # Sort by date (newest first)
        report_list.sort(key=lambda x: x['generated_at'], reverse=True)

        return report_list

    def get_report_version_history(self, task_id_prefix: str) -> List[Dict[str, Any]]:
        """
        Get version history for a specific task

        Args:
            task_id_prefix: Task ID prefix to search for

        Returns:
            List of reports for this task, sorted by date
        """
        return self.list_report_versions(task_id_prefix=task_id_prefix)

    def load_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a specific report by ID

        Args:
            report_id: Report ID to load

        Returns:
            Report dictionary or None if not found
        """
        import json

        reports_dir = self.output_dir / "transparent_reports"

        if not reports_dir.exists():
            return None

        report_file = reports_dir / f"{report_id}.json"

        if not report_file.exists():
            return None

        try:
            with open(report_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def compare_report_versions(
        self,
        report_id_1: str,
        report_id_2: str
    ) -> Dict[str, Any]:
        """
        Compare two report versions

        Args:
            report_id_1: First report ID (typically newer)
            report_id_2: Second report ID (typically older)

        Returns:
            Comparison dictionary
        """
        report1 = self.load_report_by_id(report_id_1)
        report2 = self.load_report_by_id(report_id_2)

        if not report1 or not report2:
            return {"error": "One or both reports not found"}

        comparison = {
            "report_1": {
                "report_id": report_id_1,
                "generated_at": report1.get('generated_at'),
                "data_quality_score": report1.get('quality_report', {}).get('overall_score', 0)
            },
            "report_2": {
                "report_id": report_id_2,
                "generated_at": report2.get('generated_at'),
                "data_quality_score": report2.get('quality_report', {}).get('overall_score', 0)
            },
            "differences": {}
        }

        # Compare data quality scores
        quality1 = report1.get('quality_report', {})
        quality2 = report2.get('quality_report', {})

        if quality1 and quality2:
            comparison["differences"]["data_quality"] = {
                "report_1": quality1.get('overall_score', 0),
                "report_2": quality2.get('overall_score', 0),
                "change": quality1.get('overall_score', 0) - quality2.get('overall_score', 0)
            }

        # Compare reliability
        reliability1 = report1.get('reliability_analysis', {})
        reliability2 = report2.get('reliability_analysis', {})

        if reliability1 and reliability2:
            comparison["differences"]["sample_size"] = {
                "report_1": reliability1.get('sample_size', 0),
                "report_2": reliability2.get('sample_size', 0),
                "change": reliability1.get('sample_size', 0) - reliability2.get('sample_size', 0)
            }

        # Compare counts
        comparison["differences"]["traces"] = {
            "report_1": len(report1.get('traces', [])),
            "report_2": len(report2.get('traces', [])),
            "change": len(report1.get('traces', [])) - len(report2.get('traces', []))
        }

        comparison["differences"]["annotations"] = {
            "report_1": len(report1.get('annotations', [])),
            "report_2": len(report2.get('annotations', [])),
            "change": len(report1.get('annotations', [])) - len(report2.get('annotations', []))
        }

        return comparison

    def delete_old_reports(self, keep_last_n: int = 10, task_id_prefix: Optional[str] = None) -> int:
        """
        Delete old reports, keeping only the most recent N

        Args:
            keep_last_n: Number of recent reports to keep
            task_id_prefix: Optional filter by task ID prefix

        Returns:
            Number of reports deleted
        """
        import os

        versions = self.list_report_versions(task_id_prefix=task_id_prefix)

        if len(versions) <= keep_last_n:
            return 0

        # Delete older reports
        to_delete = versions[keep_last_n:]
        deleted_count = 0

        for report in to_delete:
            try:
                os.remove(report['file_path'])
                deleted_count += 1
            except Exception:
                continue

        return deleted_count

    # -------------------------------------------------------------------------
    # Export Functions
    # -------------------------------------------------------------------------

    def export_report_to_excel(self, report_id: str, output_path: Optional[str] = None) -> Optional[Path]:
        """
        Export a transparency report to Excel format

        Args:
            report_id: Report ID to export
            output_path: Optional output file path

        Returns:
            Path to exported file or None if error
        """
        try:
            import pandas as pd
        except ImportError:
            print("⚠️ pandas is required for Excel export. Install with: pip install pandas openpyxl")
            return None

        report = self.load_report_by_id(report_id)
        if not report:
            return None

        if output_path is None:
            output_path = self.output_dir / f"{report_id}.xlsx"
        else:
            output_path = Path(output_path)

        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Sheet 1: Summary
            summary_data = {
                "Property": ["Report ID", "Task ID", "Task Type", "Success", "Generated At", "Data Quality Score"],
                "Value": [
                    report.get('report_id', 'N/A'),
                    report.get('task_id', 'N/A'),
                    report.get('task_type', 'N/A'),
                    report.get('success', False),
                    report.get('generated_at', 'N/A'),
                    report.get('quality_report', {}).get('overall_score', 0)
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

            # Sheet 2: Metric Traces
            if report.get('traces'):
                traces_data = []
                for trace in report['traces']:
                    traces_data.append({
                        "Metric Name": trace.get('metric_name'),
                        "Metric Type": trace.get('metric_type'),
                        "Final Value": trace.get('final_value'),
                        "Status": trace.get('status'),
                        "Steps Count": len(trace.get('steps', []))
                    })
                pd.DataFrame(traces_data).to_excel(writer, sheet_name='Metric Traces', index=False)

            # Sheet 3: Annotations
            if report.get('annotations'):
                annotations_data = []
                for ann in report['annotations']:
                    annotations_data.append({
                        "Title": ann.get('title'),
                        "Priority": ann.get('priority'),
                        "Type": ann.get('annotation_type'),
                        "Content": ann.get('content'),
                        "Author": ann.get('author'),
                        "Timestamp": ann.get('timestamp')
                    })
                pd.DataFrame(annotations_data).to_excel(writer, sheet_name='Annotations', index=False)

            # Sheet 4: Data Quality
            quality_report = report.get('quality_report', {})
            if quality_report:
                quality_data = {
                    "Metric": ["Overall Score", "Total Tasks", "Tasks with Scores", "Quality Evaluated"],
                    "Value": [
                        quality_report.get('overall_score', 0),
                        quality_report.get('data_completeness', {}).get('total_tasks', 0),
                        quality_report.get('data_completeness', {}).get('tasks_with_scores', 0),
                        quality_report.get('data_completeness', {}).get('quality_evaluated', 0)
                    ]
                }
                pd.DataFrame(quality_data).to_excel(writer, sheet_name='Data Quality', index=False)

            # Sheet 5: Actionable Insights
            if report.get('actionable_insights'):
                insights_data = []
                for insight in report['actionable_insights']:
                    insights_data.append({
                        "Priority": insight.get('priority'),
                        "Title": insight.get('title'),
                        "Category": insight.get('category'),
                        "Current State": insight.get('current_state'),
                        "Action": insight.get('action'),
                        "Expected Impact": insight.get('expected_impact')
                    })
                pd.DataFrame(insights_data).to_excel(writer, sheet_name='Actionable Insights', index=False)

            # Sheet 6: Comparison
            comparison = report.get('comparison', {})
            if comparison and comparison.get('metric_changes'):
                comparison_data = []
                for metric, data in comparison['metric_changes'].items():
                    comparison_data.append({
                        "Metric": metric,
                        "Previous": data['previous'],
                        "Current": data['current'],
                        "Change": data['change'],
                        "Change %": data['change_percent']
                    })
                pd.DataFrame(comparison_data).to_excel(writer, sheet_name='Comparison', index=False)

        return output_path

    def export_report_to_markdown(self, report_id: str, output_path: Optional[str] = None) -> Optional[Path]:
        """
        Export a transparency report to Markdown format (useful for PDF conversion)

        Args:
            report_id: Report ID to export
            output_path: Optional output file path

        Returns:
            Path to exported file or None if error
        """
        report = self.load_report_by_id(report_id)
        if not report:
            return None

        if output_path is None:
            output_path = self.output_dir / f"{report_id}.md"
        else:
            output_path = Path(output_path)

        md_content = []

        # Title
        md_content.append(f"# Transparency Report: {report.get('report_id')}\n")

        # Summary
        md_content.append("## Summary\n")
        md_content.append(f"- **Task ID**: {report.get('task_id')}")
        md_content.append(f"- **Task Type**: {report.get('task_type')}")
        md_content.append(f"- **Success**: {report.get('success')}")
        md_content.append(f"- **Generated At**: {report.get('generated_at')}")
        md_content.append(f"- **Data Quality Score**: {report.get('quality_report', {}).get('overall_score', 0)}/100\n")

        # Test Configuration
        test_config = report.get('metadata', {}).get('test_configuration', {})
        if test_config:
            md_content.append("## Test Configuration\n")
            md_content.append(f"- **Environment**: {test_config.get('environment')}")
            md_content.append(f"- **Framework**: {test_config.get('framework')}")
            md_content.append(f"- **Model**: {test_config.get('model_name')}")
            md_content.append(f"- **Evaluator**: {test_config.get('evaluator')}\n")

        # Reliability Analysis
        reliability = report.get('reliability_analysis', {})
        if reliability:
            md_content.append("## Reliability Analysis\n")
            md_content.append(f"- **Sample Size**: {reliability.get('sample_size')}")
            md_content.append(f"- **Sufficient**: {'✅' if reliability.get('sufficient') else '⚠️'}")
            md_content.append(f"- **Confidence Level**: {reliability.get('confidence_level')}%")
            md_content.append(f"- **Variance**: {reliability.get('variance'):.4f}\n")

        # Metric Traces
        if report.get('traces'):
            md_content.append("## Metric Calculation Traces\n")
            for trace in report['traces']:
                md_content.append(f"### {trace.get('metric_name')}")
                md_content.append(f"- **Type**: {trace.get('metric_type')}")
                md_content.append(f"- **Final Value**: {trace.get('final_value')}")
                md_content.append(f"- **Status**: {trace.get('status')}")
                md_content.append(f"- **Steps**: {len(trace.get('steps', []))}\n")

        # Actionable Insights
        if report.get('actionable_insights'):
            md_content.append("## Actionable Insights\n")
            for idx, insight in enumerate(report['actionable_insights'], 1):
                md_content.append(f"### {idx}. [{insight.get('priority').upper()}] {insight.get('title')}")
                md_content.append(f"**Category**: {insight.get('category')}")
                md_content.append(f"**Current State**: {insight.get('current_state')}")
                md_content.append(f"**Action**: {insight.get('action')}")
                md_content.append(f"**Expected Impact**: {insight.get('expected_impact')}\n")

        # Comparison
        comparison = report.get('comparison', {})
        if comparison and comparison.get('metric_changes'):
            md_content.append("## Comparison with Previous Evaluation\n")
            md_content.append(f"**Previous Report**: {comparison.get('previous_report_id')}\n")
            md_content.append("| Metric | Previous | Current | Change | Change % |")
            md_content.append("|--------|----------|---------|--------|----------|")
            for metric, data in comparison['metric_changes'].items():
                md_content.append(
                    f"| {metric} | {data['previous']:.2f} | {data['current']:.2f} | "
                    f"{data['change']:+.2f} | {data['change_percent']:+.1f}% |"
                )
            md_content.append("")

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))

        return output_path

    def clear_session(self):
        """
        Clear all current session data

        This clears traces, annotations, audit_logs, and reports from memory
        but does not delete saved files.
        """
        self.traces.clear()
        self.annotations.clear()
        self.audit_logs.clear()
        self.reports.clear()
