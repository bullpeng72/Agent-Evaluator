"""
tests/test_pii_redaction.py
==============================
SPEC-020 검증: agent_evaluator.utils.pii_redaction + PerformanceMonitor(enable_pii_redaction=True).

핵심 확인 대상:
- redact_pii_text/redact_task_pii 순수 함수 동작
- name/address가 기본 카테고리에서 제외되는지
- save_to_file()이 JSON/SQLite 양쪽 백엔드에서 저장본만 redact하고, 인메모리
  self.tasks는 원문을 그대로 유지하는지(SPEC-020 REQ-7 핵심 불변식)
- enable_pii_redaction 기본값(False)이 기존 동작과 동일한지(회귀)
"""
import json

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.storage.sqlite_backend import load_tasks_from_db
from agent_evaluator.utils.pii_redaction import (
    DEFAULT_REDACTION_CATEGORIES,
    redact_pii_text,
    redact_task_pii,
)


class TestRedactPiiText:
    def test_email_redacted(self):
        result = redact_pii_text("contact me at a@b.com please", ["email"])
        assert result == "contact me at [REDACTED:email] please"
        assert "a@b.com" not in result

    def test_none_and_empty_pass_through(self):
        assert redact_pii_text(None, ["email"]) is None
        assert redact_pii_text("", ["email"]) == ""

    def test_unmatched_category_is_noop(self):
        assert redact_pii_text("hello world", ["email"]) == "hello world"

    def test_multiple_categories_applied(self):
        text = "email a@b.com and ssn 123-45-6789"
        result = redact_pii_text(text, ["email", "ssn"])
        assert "a@b.com" not in result
        assert "123-45-6789" not in result
        assert "[REDACTED:email]" in result
        assert "[REDACTED:ssn]" in result


class TestRedactTaskPii:
    def _task(self, **overrides):
        defaults = dict(
            task_id="t1", question="my email is a@b.com",
            response="ok, noted a@b.com", execution_time=1.0,
        )
        defaults.update(overrides)
        return create_taskresult(**defaults)

    def test_redacts_text_fields_only(self):
        task = self._task(ground_truth="a@b.com is correct", context="see a@b.com")
        redacted = redact_task_pii(task)
        assert "a@b.com" not in redacted.question
        assert "a@b.com" not in redacted.response
        assert "a@b.com" not in redacted.ground_truth
        assert "a@b.com" not in redacted.context
        # 나머지 필드는 그대로
        assert redacted.task_id == task.task_id
        assert redacted.execution_time == task.execution_time

    def test_original_task_unchanged(self):
        task = self._task()
        redact_task_pii(task)
        assert "a@b.com" in task.question  # 원본은 절대 변경되지 않아야 함

    def test_default_categories_exclude_name_and_address(self):
        assert "name" not in DEFAULT_REDACTION_CATEGORIES
        assert "address" not in DEFAULT_REDACTION_CATEGORIES

    def test_name_not_redacted_by_default(self):
        task = self._task(question="김철수입니다", response="반갑습니다")
        redacted = redact_task_pii(task)
        assert redacted.question == "김철수입니다"  # 기본 카테고리엔 "name"이 없으므로 무변화

    def test_custom_categories_can_include_name(self):
        task = self._task(question="김철수입니다", response="ok")
        redacted = redact_task_pii(task, categories=["name"])
        assert "[REDACTED:name]" in redacted.question


class TestSaveToFileRedactionJson:
    def test_saved_file_is_redacted_but_memory_is_not(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path), enable_pii_redaction=True)
        task = create_taskresult(
            task_id="t1", question="my email is a@b.com", response="ok", execution_time=1.0,
        )
        monitor.record_task(task)

        saved_path = monitor.save_to_file("eval.json")
        with open(saved_path) as f:
            data = json.load(f)
        assert "a@b.com" not in json.dumps(data)
        assert "[REDACTED:email]" in data["tasks"][0]["question"]

        # 인메모리는 원문 그대로 유지돼야 한다 (SPEC-020 REQ-7 핵심 불변식)
        assert "a@b.com" in monitor.tasks[0].question

    def test_disabled_by_default(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))  # enable_pii_redaction 생략
        task = create_taskresult(
            task_id="t1", question="my email is a@b.com", response="ok", execution_time=1.0,
        )
        monitor.record_task(task)
        saved_path = monitor.save_to_file("eval.json")
        with open(saved_path) as f:
            data = json.load(f)
        assert "a@b.com" in data["tasks"][0]["question"]  # 기본값 False → 무변화


class TestSaveToFileRedactionSqlite:
    def test_saved_db_is_redacted_but_memory_is_not(self, tmp_path):
        monitor = PerformanceMonitor(
            output_dir=str(tmp_path), enable_pii_redaction=True, storage_backend="sqlite",
        )
        task = create_taskresult(
            task_id="t1", question="my email is a@b.com", response="ok", execution_time=1.0,
        )
        monitor.record_task(task)

        saved_path = monitor.save_to_file("eval")
        tasks = load_tasks_from_db(saved_path)
        assert len(tasks) == 1
        assert "a@b.com" not in tasks[0].question
        assert "[REDACTED:email]" in tasks[0].question

        # 인메모리는 원문 그대로 유지돼야 한다
        assert "a@b.com" in monitor.tasks[0].question
