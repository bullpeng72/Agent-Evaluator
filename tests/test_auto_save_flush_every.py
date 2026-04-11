"""
tests/test_auto_save_flush_every.py
=====================================
PerformanceMonitor.auto_save 및 agent_eval/batch_eval flush_every 테스트.
"""
from __future__ import annotations

import os
import threading
import pytest


# ---------------------------------------------------------------------------
# PerformanceMonitor auto_save
# ---------------------------------------------------------------------------

class TestAutoSave:
    def test_auto_save_triggers_at_interval(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path) + "/",
            auto_save=True,
            auto_save_interval=2,
            auto_save_filename="auto_test",
        )

        task1 = create_taskresult(
            task_id="t1", question="q", response="r",
            ground_truth="r", execution_time=0.1,
        )
        task2 = create_taskresult(
            task_id="t2", question="q2", response="r2",
            ground_truth="r2", execution_time=0.1,
        )

        monitor.record_task(task1)
        # 아직 저장 안 됨 (interval=2, 1개만 기록)
        # save_to_file은 확장자 없으면 .json 자동 추가
        auto_file = os.path.join(str(tmp_path), "auto_test.json")
        assert not os.path.exists(auto_file)

        monitor.record_task(task2)
        # 2번째 기록 후 auto_save 실행
        assert os.path.exists(auto_file)

    def test_auto_save_disabled_by_default(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        for i in range(10):
            task = create_taskresult(
                task_id=f"t{i}", question="q", response="r",
                ground_truth="r", execution_time=0.1,
            )
            monitor.record_task(task)

        # auto_save=False (기본값)이면 파일이 없어야 함
        assert not any(f.endswith(".json") for f in os.listdir(str(tmp_path)))

    def test_auto_save_interval_respected(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path) + "/",
            auto_save=True,
            auto_save_interval=3,
            auto_save_filename="interval_test",
        )

        auto_file = os.path.join(str(tmp_path), "interval_test.json")

        for i in range(2):
            task = create_taskresult(
                task_id=f"t{i}", question="q", response="r",
                ground_truth="r", execution_time=0.1,
            )
            monitor.record_task(task)
        # 2개 기록 후 파일 없음 (interval=3)
        assert not os.path.exists(auto_file)

        task3 = create_taskresult(
            task_id="t3", question="q", response="r",
            ground_truth="r", execution_time=0.1,
        )
        monitor.record_task(task3)
        # 3번째 기록 후 파일 있음
        assert os.path.exists(auto_file)


# ---------------------------------------------------------------------------
# agent_eval flush_every
# ---------------------------------------------------------------------------

class TestFlushEvery:
    def test_flush_every_triggers_save(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(
            monitor, task_type="qa",
            flush_every=2,
            flush_filename="flush_test",
        )
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        flush_file = os.path.join(str(tmp_path), "flush_test.json")

        agent("q1?")
        assert not os.path.exists(flush_file)

        agent("q2?")
        assert os.path.exists(flush_file)

    def test_flush_every_zero_no_save(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa", flush_every=0)
        def agent(question: str, ground_truth: str = "") -> str:
            return "answer"

        for _ in range(10):
            agent("q?")

        assert not any(f.endswith(".json") for f in os.listdir(str(tmp_path)))


# ---------------------------------------------------------------------------
# batch_eval flush_every
# ---------------------------------------------------------------------------

class TestBatchEvalFlushEvery:
    def test_batch_flush_every(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(
            monitor, task_type="qa",
            flush_every=2,
            flush_filename="batch_flush_test",
        )
        def batch_agent(questions, ground_truths=None):
            return [f"answer_{i}" for i in range(len(questions))]

        flush_file = os.path.join(str(tmp_path), "batch_flush_test.json")

        batch_agent(questions=["q1"], ground_truths=["a1"])
        assert not os.path.exists(flush_file)

        batch_agent(questions=["q2"], ground_truths=["a2"])
        assert os.path.exists(flush_file)


# ---------------------------------------------------------------------------
# thread safety (auto_save 동시 호출)
# ---------------------------------------------------------------------------

class TestAutoSaveThreadSafety:
    def test_concurrent_record_task_no_error(self, tmp_path):
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator import create_taskresult

        monitor = PerformanceMonitor(
            output_dir=str(tmp_path) + "/",
            auto_save=True,
            auto_save_interval=5,
            auto_save_filename="thread_test",
        )

        errors = []

        def record(n):
            try:
                task = create_taskresult(
                    task_id=f"t{n}", question="q", response="r",
                    ground_truth="r", execution_time=0.01,
                )
                monitor.record_task(task)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"thread errors: {errors}"
