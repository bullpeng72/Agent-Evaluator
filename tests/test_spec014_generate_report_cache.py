"""
tests/test_spec014_generate_report_cache.py
===============================================
SPEC-014: generate_report() 재계산 방지 캐싱 (풀 리텐션 모드) 검증.

REQ-1/2/3: 캐시 필드 + record_task()의 dirty=True + generate_report()의 단락 로직.
REQ-4: BUG-E6 재평가·SPEC-006 비동기 judge 패치 지점의 캐시 무효화 배선.
REQ-5: dirty-flag는 self._lock으로 보호.
REQ-6: force_recompute=True는 항상 재계산.

캐시 히트/미스는 반환된 EvaluationReport 객체의 identity(`is`/`is not`)로 판별한다 —
_generate_report_uncached()는 호출마다 항상 새 EvaluationReport 인스턴스를 만들므로,
같은 객체가 반환되면 캐시 히트, 다른 객체면 재계산이 일어난 것이다.
"""
from __future__ import annotations

import asyncio

import pytest

from agent_evaluator import (
    PerformanceMonitor,
    SecurityConfig,
    ThreatSeverityConfig,
    agent_eval,
    create_taskresult,
)


def _make_task(task_id: str):
    return create_taskresult(
        task_id=task_id, question="What is 2+2?", response="4",
        ground_truth="4", execution_time=0.5, task_type="qa",
    )


class TestCacheHitAndMiss:
    def test_no_record_task_returns_same_cached_object(self):
        """Acceptance: record_task() 없이 연속 2회 호출하면 두 번째는 캐시(동일 객체)를 반환한다."""
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        report1 = monitor.generate_report()
        report2 = monitor.generate_report()
        assert report2 is report1

    def test_record_task_between_calls_triggers_recompute(self):
        """Acceptance: 두 호출 사이에 record_task()가 있으면 재계산되어 새 리포트를 반환한다."""
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        report1 = monitor.generate_report()
        assert report1.total_tasks == 1

        monitor.record_task(_make_task("t2"))
        report2 = monitor.generate_report()
        assert report2 is not report1
        assert report2.total_tasks == 2

    def test_compute_harness_groups_not_called_on_cache_hit(self):
        """캐시 히트 시 _compute_harness_groups()가 아예 호출되지 않아야 한다(spy 검증)."""
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        monitor.generate_report()

        called = []
        original = monitor._compute_harness_groups

        def _spy(*args, **kwargs):
            called.append(1)
            return original(*args, **kwargs)

        monitor._compute_harness_groups = _spy
        monitor.generate_report()
        assert called == []

    def test_force_recompute_always_recomputes(self):
        """REQ-6: force_recompute=True는 dirty=False 상태에서도 항상 재계산한다."""
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        report1 = monitor.generate_report()
        report2 = monitor.generate_report(force_recompute=True)
        assert report2 is not report1
        # 데이터 자체는 동일해야 한다(순수 성능 최적화 — 값 변경 없음)
        assert report2.total_tasks == report1.total_tasks

    def test_fresh_monitor_no_tasks_recomputes_each_time(self):
        """태스크가 전혀 없는 상태에서도 캐시 메커니즘 자체가 에러 없이 동작해야 한다."""
        monitor = PerformanceMonitor()
        report1 = monitor.generate_report()
        report2 = monitor.generate_report()
        assert report2 is report1  # 여전히 record_task()가 없었으므로 캐시 재사용
        assert report1.total_tasks == 0


class TestCacheValueEquivalence:
    """Goals: 캐시가 있어도 결과가 캐싱 없는 경우와 완전히 동일해야 한다."""

    def test_cached_and_forced_reports_have_identical_content(self):
        monitor = PerformanceMonitor()
        for i in range(3):
            monitor.record_task(_make_task(f"t{i}"))
        cached = monitor.generate_report()
        forced = monitor.generate_report(force_recompute=True)
        assert cached.total_tasks == forced.total_tasks
        assert cached.accuracy_metrics == forced.accuracy_metrics
        assert cached.efficiency_metrics == forced.efficiency_metrics
        assert cached.extra_metrics == forced.extra_metrics


class TestInvalidateReportCacheMechanism:
    def test_invalidate_report_cache_forces_recompute(self):
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        report1 = monitor.generate_report()

        monitor.invalidate_report_cache()
        report2 = monitor.generate_report()
        assert report2 is not report1

    def test_reset_invalidates_cache(self):
        """reset()이 트래커를 초기화하므로 이후 generate_report()는 빈 상태를 반영해야 한다."""
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        report1 = monitor.generate_report()
        assert report1.total_tasks == 1

        monitor.reset()
        report2 = monitor.generate_report()
        assert report2 is not report1
        assert report2.total_tasks == 0

    def test_flush_invalidates_cache(self):
        monitor = PerformanceMonitor()
        monitor.record_task(_make_task("t1"))
        monitor.generate_report()  # 캐시 warm-up

        monitor.flush()
        report_after = monitor.generate_report()
        assert report_after.total_tasks == 0


class TestBugE6PostRecordInvalidation:
    """REQ-4: BUG-E6 threat_severity 재평가가 캐시를 무효화하는지 검증(엔드투엔드)."""

    def test_agent_eval_with_threat_severity_reflects_enriched_extra(self):
        monitor = PerformanceMonitor(enable_security_metrics=True)

        @agent_eval(
            monitor, task_type="qa",
            security=SecurityConfig(),
            threat_severity=ThreatSeverityConfig(),
        )
        def agent(question, ground_truth=""):
            return "processed"

        # SQL injection 패턴이 포함된 질문 — InputSanitizationTracker가 탐지해
        # record_task() 내부에서 task_result.extra["input_sanitization"]을 채우고,
        # BUG-E6 post-record 재평가가 이를 반영한 threat_severity로 다시 채운다.
        agent("' OR '1'='1")

        report = monitor.generate_report()
        hg = report.extra_metrics["harness_groups"]
        # Gate E가 위협을 인지했다면 threat_count > 0 또는 cvss 관련 값이 채워져야 한다.
        assert hg["E"]["details"]["threat_count"] >= 1

        # 캐시가 이 결과를 안정적으로 재사용하는지도 함께 확인(동일 객체 재반환).
        report2 = monitor.generate_report()
        assert report2 is report
        assert report2.extra_metrics["harness_groups"]["E"]["details"]["threat_count"] >= 1


class TestSpec006AsyncJudgeInvalidation:
    """REQ-4: 비동기 judge 결과 patch가 (record_task()와 분리된 시점에) 캐시를 무효화하는지 검증.

    record_task()와 별개의 await 지점에서 발생하는 in-place 수정이므로, 캐시를 미리
    warm-up해둔 뒤 patch를 적용해도 다음 generate_report() 호출이 반드시 재계산되어야
    한다 — 이 지점의 invalidate_report_cache() 호출이 빠지면 이 테스트가 실패한다.
    """

    def test_async_judge_patch_invalidates_warm_cache(self):
        from agent_evaluator.decorators import _process_async_judge_targets

        monitor = PerformanceMonitor()
        task = _make_task("t1")
        monitor.record_task(task)

        # 캐시를 미리 warm-up — judge patch가 발생하기 전에 이미 계산된 상태를 흉내낸다.
        report_before = monitor.generate_report()
        assert report_before is monitor.generate_report()  # 캐시 히트 확인

        class _FakeJudge:
            async def ajudge(self, task_id, question, response, context):
                return {"scores": {"overall": 4.5}}

        asyncio.run(_process_async_judge_targets(
            [(monitor, _FakeJudge(), "t1", "What is 2+2?", "4", None)]
        ))

        report_after = monitor.generate_report()
        assert report_after is not report_before, (
            "SPEC-006 비동기 judge patch 이후 generate_report()가 재계산 없이 "
            "stale 캐시를 반환했다 — _process_async_judge_targets()의 "
            "invalidate_report_cache() 호출이 누락됐을 가능성이 있다."
        )

        # patch가 실제로 반영됐는지도 확인
        patched_task = monitor.tcr_tracker._tasks[-1]
        assert patched_task.llm_judge == {"scores": {"overall": 4.5}}


class TestExportByFrameworkCacheSafety:
    """export_by_framework()이 self.tasks를 임시로 교체하는 동안 캐시가 잘못된
    (필터링 전/후 뒤섞인) 리포트를 반환하지 않아야 한다."""

    def test_export_by_framework_does_not_leave_stale_filtered_cache(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        t1 = create_taskresult(
            task_id="t1", question="q1", response="r1", execution_time=0.1,
            task_type="qa", extra={"framework": "langchain"},
        )
        t2 = create_taskresult(
            task_id="t2", question="q2", response="r2", execution_time=0.1,
            task_type="qa", extra={"framework": "crewai"},
        )
        monitor.record_task(t1)
        monitor.record_task(t2)

        report_before = monitor.generate_report()
        assert report_before.total_tasks == 2

        monitor.export_by_framework("langchain", "export_test")

        # 원본 태스크로 복원된 뒤에도 전체 2개를 정확히 반영해야 한다(필터링된 1개로
        # 캐시가 오염되어 있으면 안 된다).
        report_after = monitor.generate_report()
        assert report_after.total_tasks == 2
        assert report_after is not report_before
