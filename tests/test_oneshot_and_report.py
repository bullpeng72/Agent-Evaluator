"""One-shot API, Batch API, EvaluationReport 메서드 테스트."""
import json
import pytest
from agent_evaluator import PerformanceMonitor, create_taskresult


class TestEvaluateQA:
    """monitor.evaluate_qa() 테스트"""

    def test_evaluate_qa_returns_dict(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa("Q", "A", "A")
        assert isinstance(result, dict)
        assert "accuracy_score" in result
        assert "task_id" in result

    def test_evaluate_qa_accuracy_exact_match(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa("Q", "Seoul", "Seoul")
        assert result["accuracy_score"] > 0.8

    def test_evaluate_qa_records_task(self):
        monitor = PerformanceMonitor()
        monitor.evaluate_qa("Q", "A", "A")
        report = monitor.generate_report()
        assert report.total_tasks == 1

    def test_evaluate_qa_custom_task_id(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa("Q", "A", "A", task_id="custom_001")
        assert result["task_id"] == "custom_001"

    def test_evaluate_qa_auto_task_id(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa("Q", "A", "A")
        assert result["task_id"].startswith("qa_")

    def test_evaluate_qa_score_range(self):
        monitor = PerformanceMonitor()
        result = monitor.evaluate_qa("Q", "completely wrong answer", "correct answer")
        assert 0.0 <= result["accuracy_score"] <= 1.0
        assert 0.0 <= result["completion_score"] <= 1.0


class TestEvaluateBatch:
    """monitor.evaluate_batch() 테스트"""

    def test_evaluate_batch_returns_list(self):
        monitor = PerformanceMonitor()
        items = [
            {"question": "Q1", "response": "A1", "ground_truth": "A1"},
            {"question": "Q2", "response": "A2", "ground_truth": "A2"},
        ]
        results = monitor.evaluate_batch(items)
        assert len(results) == 2

    def test_evaluate_batch_records_all_tasks(self):
        monitor = PerformanceMonitor()
        items = [{"question": f"Q{i}", "response": f"A{i}", "ground_truth": f"A{i}"} for i in range(5)]
        monitor.evaluate_batch(items)
        assert monitor.generate_report().total_tasks == 5

    def test_evaluate_batch_custom_prefix(self):
        monitor = PerformanceMonitor()
        items = [{"question": "Q", "response": "A", "ground_truth": "A"}]
        results = monitor.evaluate_batch(items, task_id_prefix="test")
        assert results[0]["task_id"].startswith("test_")

    def test_evaluate_batch_each_has_scores(self):
        monitor = PerformanceMonitor()
        items = [{"question": "Q", "response": "A", "ground_truth": "G"}]
        results = monitor.evaluate_batch(items)
        assert "accuracy_score" in results[0]

    def test_evaluate_batch_empty_list(self):
        monitor = PerformanceMonitor()
        results = monitor.evaluate_batch([])
        assert results == []


class TestEvaluationReportMethods:
    """EvaluationReport.to_dict(), to_json(), summary() 테스트"""

    @pytest.fixture
    def report(self):
        monitor = PerformanceMonitor()
        for i in range(3):
            task = create_taskresult(
                task_id=f"t{i}",
                question=f"Q{i}",
                response=f"A{i}",
                ground_truth=f"A{i}",
                execution_time=1.0,
            )
            monitor.record_task(task)
        return monitor.generate_report()

    def test_to_dict_returns_dict(self, report):
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "total_tasks" in d

    def test_to_dict_total_tasks(self, report):
        d = report.to_dict()
        assert d["total_tasks"] == 3

    def test_to_json_returns_string(self, report):
        j = report.to_json()
        assert isinstance(j, str)

    def test_to_json_is_valid_json(self, report):
        j = report.to_json()
        parsed = json.loads(j)
        assert isinstance(parsed, dict)

    def test_to_json_contains_total_tasks(self, report):
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["total_tasks"] == 3

    def test_summary_returns_dict(self, report):
        s = report.summary()
        assert isinstance(s, dict)

    def test_summary_has_required_keys(self, report):
        s = report.summary()
        assert "total_tasks" in s
        assert "success_rate" in s

    def test_summary_total_tasks(self, report):
        assert report.summary()["total_tasks"] == 3
