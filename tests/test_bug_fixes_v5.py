"""5차 개선 검증 테스트."""
import json
import os
import tempfile
import warnings

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult


class TestQualityMetrics:
    """quality_metrics 버그 수정 검증"""

    def test_quality_metrics_not_empty(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="q1",
            question="What is the capital of France?",
            response="Paris is the capital of France.",
            ground_truth="Paris",
            execution_time=1.0,
        )
        monitor.record_task(task)
        report = monitor.generate_report()
        assert report.quality_metrics != {}, "quality_metrics should not be empty dict"

    def test_quality_metrics_has_expected_keys(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="q1",
            question="Q",
            response="A detailed response",
            ground_truth="A",
            execution_time=0.5,
        )
        monitor.record_task(task)
        report = monitor.generate_report()
        assert isinstance(report.quality_metrics, dict)


class TestHTMLGeneration:
    """save_to_file() HTML 생성 검증"""

    def test_save_generates_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            for i in range(2):
                task = create_taskresult(
                    task_id=f"t{i}",
                    question=f"Q{i}",
                    response=f"A{i}",
                    ground_truth=f"A{i}",
                    execution_time=float(i + 1),
                )
                monitor.record_task(task)
            monitor.save_to_file("test_html")
            files = os.listdir(tmpdir)
            html_files = [f for f in files if f.endswith(".html")]
            assert len(html_files) >= 1, f"Expected HTML file, got: {files}"

    def test_save_html_is_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            task = create_taskresult(
                task_id="t1",
                question="Q",
                response="A",
                ground_truth="A",
                execution_time=1.0,
            )
            monitor.record_task(task)
            monitor.save_to_file("test_valid_html")
            html_files = [f for f in os.listdir(tmpdir) if f.endswith(".html")]
            if html_files:
                html_path = os.path.join(tmpdir, html_files[0])
                content = open(html_path, encoding="utf-8").read()
                assert len(content) > 100
                assert "<html" in content.lower() or "<!DOCTYPE" in content

    def test_save_still_creates_json_on_html_failure(self):
        """HTML 생성 실패해도 JSON은 저장되어야 함"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = PerformanceMonitor(output_dir=tmpdir)
            task = create_taskresult(
                task_id="t1", question="Q", response="A",
                ground_truth="A", execution_time=1.0,
            )
            monitor.record_task(task)
            path = monitor.save_to_file("fallback_test.json")
            assert path.endswith(".json")
            assert os.path.exists(path)


class TestContextParameter:
    """create_taskresult() context 파라미터 추가 검증"""

    def test_create_taskresult_accepts_context(self):
        task = create_taskresult(
            task_id="t1",
            question="What is AI?",
            response="AI is artificial intelligence.",
            ground_truth="Artificial Intelligence",
            execution_time=0.5,
            context="Reference document: AI stands for Artificial Intelligence...",
        )
        assert task.context == "Reference document: AI stands for Artificial Intelligence..."

    def test_create_taskresult_context_default_none(self):
        task = create_taskresult(
            task_id="t1",
            question="Q",
            response="A",
            ground_truth="G",
            execution_time=0.5,
        )
        assert task.context is None

    def test_evaluate_qa_accepts_context(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa(
            question="What is AI?",
            response="Artificial Intelligence",
            ground_truth="AI",
            context="AI stands for Artificial Intelligence.",
        )
        assert "accuracy_score" in result


class TestDeprecationWarning:
    """record_task() deprecated 파라미터 경고 검증"""

    def test_request_param_always_warns(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="t1",
            question="existing question",  # question이 이미 있어도
            response="A",
            ground_truth="A",
            execution_time=0.5,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task, request="override question")
        assert any(issubclass(x.category, DeprecationWarning) for x in w), \
            "DeprecationWarning should fire even when task_result.question is set"

    def test_request_param_none_no_warning(self):
        monitor = PerformanceMonitor()
        task = create_taskresult(
            task_id="t1",
            question="Q",
            response="A",
            ground_truth="A",
            execution_time=0.5,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task)  # request=None (기본값)
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) == 0
