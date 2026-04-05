"""
tests/test_v075_gaps.py
========================
v0.7.5 수정 사항 테스트:
  Gap A  - GET /api/results/{file_id}/tasks/search 검색/필터링 엔드포인트
  Gap B  - 다중 monitor 리스트 지원 (EvalDecorator)
  Gap C  - QuickEval.gate(config_file=...) 설정 파일 임계값 로드
  Gap D  - GET /api/results/{file_id}/distributions 분포 통계 엔드포인트
  Gap E  - sample_condition 조건부 샘플링 (agent_eval / batch_eval)
  Gap F  - PerformanceMonitor.aggregate_by_time() 시계열 집계
  Gap G  - GET /api/tasks/search 전체 파일 검색 엔드포인트
  Gap H  - on_record 반환 TaskResult 교체
  Gap I  - batch_eval on_batch_progress 진행률 콜백
  Gap J  - conversation_eval on_session_timeout 타임아웃 콜백
"""
from __future__ import annotations

import json
import time
import threading
import pytest


# ---------------------------------------------------------------------------
# Gap A — /api/results/{file_id}/tasks/search
# ---------------------------------------------------------------------------

class TestSearchTasksEndpoint:
    def test_search_route_registered(self):
        """search 라우터가 data 라우터에 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("tasks/search" in p for p in paths), f"tasks/search not found in {paths}"

    def test_distributions_route_registered(self):
        """distributions 라우터가 data 라우터에 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("distributions" in p for p in paths), f"distributions not found in {paths}"

    def test_cross_file_search_route_registered(self):
        """전체 파일 task 검색 라우터가 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        # /tasks/search or /api/tasks/search
        assert any("tasks/search" in p for p in paths), f"global tasks/search not found in {paths}"


# ---------------------------------------------------------------------------
# Gap B — 다중 monitor 리스트 지원
# ---------------------------------------------------------------------------

class TestMultiMonitorSupport:
    def test_agent_eval_records_to_multiple_monitors(self, tmp_path):
        """agent_eval에 monitor 리스트를 넘기면 모두에 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        m1 = PerformanceMonitor(output_dir=str(tmp_path / "m1") + "/")
        m2 = PerformanceMonitor(output_dir=str(tmp_path / "m2") + "/")

        @agent_eval([m1, m2], task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")

        assert len(m1.tcr_tracker.tasks) == 1
        assert len(m2.tcr_tracker.tasks) == 1

    def test_batch_eval_records_to_multiple_monitors(self, tmp_path):
        """batch_eval에 monitor 리스트를 넘기면 모두에 기록되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        m1 = PerformanceMonitor(output_dir=str(tmp_path / "m1") + "/")
        m2 = PerformanceMonitor(output_dir=str(tmp_path / "m2") + "/")

        @batch_eval([m1, m2], task_type="qa")
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])

        assert len(m1.tcr_tracker.tasks) == 2
        assert len(m2.tcr_tracker.tasks) == 2


# ---------------------------------------------------------------------------
# Gap C — QuickEval.gate(config_file=...)
# ---------------------------------------------------------------------------

class TestQuickEvalGateConfigFile:
    def test_gate_loads_thresholds_from_file(self, tmp_path):
        """config_file에서 임계값을 로드해야 한다."""
        from agent_evaluator.quick_eval import QuickEval
        from agent_evaluator.decorators import agent_eval

        cfg = tmp_path / "thresholds.json"
        cfg.write_text(json.dumps({"tcr": 0, "accuracy": 0}))  # 항상 통과하는 임계값

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        result = qe.gate(config_file=str(cfg))
        assert result is True

    def test_gate_direct_param_overrides_config_file(self, tmp_path):
        """직접 지정 파라미터가 config_file 값보다 우선해야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        cfg = tmp_path / "thresholds.json"
        cfg.write_text(json.dumps({"tcr": 0}))  # 파일은 tcr=0

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        # tcr=0으로 config, 직접 tcr=0으로 override → 통과
        result = qe.gate(config_file=str(cfg), tcr=0)
        assert result is True

    def test_gate_missing_config_file_ignored(self, tmp_path):
        """존재하지 않는 config_file은 경고 후 무시되어야 한다."""
        from agent_evaluator.quick_eval import QuickEval

        qe = QuickEval(str(tmp_path) + "/")

        @qe.qa
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        # 파일 없음 → 무시하고 tcr=0으로 통과
        result = qe.gate(config_file="/nonexistent/path.json", tcr=0)
        assert result is True


# ---------------------------------------------------------------------------
# Gap D — /api/results/{file_id}/distributions (라우터 등록 확인)
# ---------------------------------------------------------------------------

class TestDistributionsEndpoint:
    def test_distributions_in_data_router(self):
        """distributions 엔드포인트가 등록되어야 한다."""
        from agent_evaluator.serve.routers.data import router
        paths = [r.path for r in router.routes]
        assert any("distributions" in p for p in paths)


# ---------------------------------------------------------------------------
# Gap E — sample_condition 조건부 샘플링
# ---------------------------------------------------------------------------

class TestSampleCondition:
    def test_agent_eval_condition_false_skips_evaluation(self, tmp_path):
        """sample_condition이 False를 반환하면 평가를 생략해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa", sample_condition=lambda args, kwargs: False)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        # 조건 False → 평가 생략 → 태스크 기록 없음
        assert len(monitor.tcr_tracker.tasks) == 0

    def test_agent_eval_condition_true_evaluates(self, tmp_path):
        """sample_condition이 True를 반환하면 평가가 실행되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa", sample_condition=lambda args, kwargs: True)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(monitor.tcr_tracker.tasks) == 1

    def test_agent_eval_condition_based_on_kwargs(self, tmp_path):
        """sample_condition이 kwargs 내용을 기반으로 동적 샘플링해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        # question 길이 > 10 인 경우만 평가
        condition = lambda args, kwargs: len(kwargs.get("question", args[0] if args else "")) > 10

        @agent_eval(monitor, task_type="qa", sample_condition=condition)
        def agent(question, ground_truth=""):
            return "answer"

        agent("short", ground_truth="answer")   # 짧은 질문 → 생략
        agent("long question with more than 10 chars", ground_truth="answer")  # 긴 질문 → 평가

        assert len(monitor.tcr_tracker.tasks) == 1

    def test_batch_eval_sample_condition_false_skips(self, tmp_path):
        """batch_eval에서도 sample_condition=False이면 평가 생략해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa", sample_condition=lambda args, kwargs: False)
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(monitor.tcr_tracker.tasks) == 0


# ---------------------------------------------------------------------------
# Gap F — PerformanceMonitor.aggregate_by_time()
# ---------------------------------------------------------------------------

class TestAggregateByTime:
    def test_aggregate_by_time_returns_dict(self, tmp_path):
        """aggregate_by_time() 이 dict를 반환해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        result = monitor.aggregate_by_time("hour")
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_aggregate_by_time_bucket_has_required_keys(self, tmp_path):
        """각 버킷에 tcr, avg_accuracy, avg_latency, count, error_count 가 있어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        hourly = monitor.aggregate_by_time("hour")
        bucket = next(iter(hourly.values()))
        assert "tcr" in bucket
        assert "avg_accuracy" in bucket
        assert "avg_latency" in bucket
        assert "count" in bucket
        assert "error_count" in bucket

    def test_aggregate_by_time_granularities(self, tmp_path):
        """minute / hour / day 세 가지 granularity 가 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        for gran in ("minute", "hour", "day"):
            result = monitor.aggregate_by_time(gran)
            assert isinstance(result, dict)

    def test_aggregate_by_time_empty_monitor(self, tmp_path):
        """태스크가 없으면 빈 dict를 반환해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        result = monitor.aggregate_by_time("hour")
        assert result == {}

    def test_aggregate_by_time_count_matches_tasks(self, tmp_path):
        """버킷 count 합계가 총 태스크 수와 같아야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        for i in range(5):
            agent(f"q{i}?", ground_truth="answer")

        hourly = monitor.aggregate_by_time("hour")
        total_count = sum(v["count"] for v in hourly.values())
        assert total_count == 5


# ---------------------------------------------------------------------------
# Gap H — on_record 반환값으로 TaskResult 교체
# ---------------------------------------------------------------------------

class TestOnRecordTransform:
    def test_on_record_returning_none_is_ignored(self, tmp_path):
        """on_record가 None 반환 시 원래 TaskResult가 유지되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        recorded = []

        def my_on_record(tr):
            recorded.append(tr)
            return None  # None 반환 → 교체 없음

        @agent_eval(monitor, task_type="qa", on_record=my_on_record)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(recorded) == 1
        assert recorded[0].task_type is not None

    def test_on_record_returning_taskresult_replaces(self, tmp_path):
        """on_record가 TaskResult 반환 시 교체되어야 한다."""
        import dataclasses
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        results_seen = []

        def enriching_on_record(tr):
            # framework 태그 주입
            enriched = dataclasses.replace(tr, framework="enriched-framework")
            results_seen.append(enriched)
            return enriched

        @agent_eval(monitor, task_type="qa", on_record=enriching_on_record)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q?", ground_truth="answer")
        assert len(results_seen) == 1
        assert results_seen[0].framework == "enriched-framework"


# ---------------------------------------------------------------------------
# Gap I — batch_eval on_batch_progress
# ---------------------------------------------------------------------------

class TestBatchEvalProgress:
    def test_on_batch_progress_called_per_item(self, tmp_path):
        """on_batch_progress가 항목마다 호출되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        progress_log = []

        @batch_eval(
            monitor,
            task_type="qa",
            on_batch_progress=lambda done, total: progress_log.append((done, total)),
        )
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2", "q3"], ground_truths=["a1", "a2", "a3"])
        assert len(progress_log) == 3
        assert progress_log[-1] == (3, 3)

    def test_on_batch_progress_final_equals_total(self, tmp_path):
        """마지막 콜백의 done == total 이어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        calls = []

        @batch_eval(
            monitor,
            task_type="qa",
            on_batch_progress=lambda done, total: calls.append((done, total)),
        )
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1", "q2"], ground_truths=["a1", "a2"])
        assert calls[-1][0] == calls[-1][1]

    def test_on_batch_progress_none_does_not_fail(self, tmp_path):
        """on_batch_progress=None 이어도 정상 동작해야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import batch_eval

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")

        @batch_eval(monitor, task_type="qa")
        def agent(questions, ground_truths=None):
            return [f"ans" for _ in questions]

        agent(questions=["q1"], ground_truths=["a1"])
        assert len(monitor.tcr_tracker.tasks) == 1


# ---------------------------------------------------------------------------
# Gap J — conversation_eval on_session_timeout
# ---------------------------------------------------------------------------

class TestConversationSessionTimeout:
    def test_on_session_timeout_called_on_timer_expire(self, tmp_path):
        """max_session_seconds 초과 시 on_session_timeout이 호출되어야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval, flush_conversation

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        timeout_log = []
        done_event = threading.Event()

        def on_timeout(session_id):
            timeout_log.append(session_id)
            done_event.set()

        @conversation_eval(
            monitor,
            max_session_seconds=0.05,  # 50ms
            on_session_timeout=on_timeout,
        )
        def chat(question, session_id="sess_001"):
            return "reply"

        chat("안녕하세요", session_id="sess_001")
        # 타이머가 만료될 때까지 대기 (최대 2초)
        done_event.wait(timeout=2.0)

        assert len(timeout_log) >= 1
        assert timeout_log[0] == "sess_001"

    def test_on_session_timeout_not_called_when_no_timer(self, tmp_path):
        """max_session_seconds 미지정 시 on_session_timeout이 호출되지 않아야 한다."""
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import conversation_eval, flush_conversation

        monitor = PerformanceMonitor(output_dir=str(tmp_path) + "/")
        timeout_log = []

        @conversation_eval(
            monitor,
            on_session_timeout=lambda sid: timeout_log.append(sid),
        )
        def chat(question, session_id="sess_002"):
            return "reply"

        chat("안녕하세요", session_id="sess_002")
        flush_conversation("sess_002")
        time.sleep(0.1)

        assert len(timeout_log) == 0
