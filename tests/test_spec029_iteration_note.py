"""
tests/test_spec029_iteration_note.py
======================================
SPEC-029 REQ-3: ResultFile.iteration_note — extra_metrics.lineage.iteration_note를
prompt_version/agent_version과 동일한 패턴으로 노출한다.

REQ-1/2(PerformanceMonitor -> _build_lineage())는 tests/test_lineage_capture.py,
REQ-4(record_and_save() passthrough)는 tests/test_live_guardrail_report.py에서 검증한다.
"""
from __future__ import annotations

from types import SimpleNamespace

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.serve.loader import ResultFile, load_results


def _save_run(tmp_path, filename: str, *, agent_version=None, iteration_note=None):
    monitor = PerformanceMonitor(
        output_dir=str(tmp_path), agent_version=agent_version, iteration_note=iteration_note,
    )
    monitor.record_task(
        create_taskresult(task_id="t1", question="q", response="r", execution_time=1.0)
    )
    monitor.save_to_file(filename)


class TestResultFileIterationNote:
    def test_note_exposed_alongside_agent_version(self, tmp_path):
        _save_run(
            tmp_path, "run_v2",
            agent_version="agent-2026-07", iteration_note="플랜 단계를 먼저 세우게 지시문 추가",
        )
        result_set = load_results(tmp_path)
        assert len(result_set.files) == 1
        rf = result_set.files[0]
        assert rf.agent_version == "agent-2026-07"
        assert rf.iteration_note == "플랜 단계를 먼저 세우게 지시문 추가"

    def test_none_when_absent_not_error(self, tmp_path):
        """구버전 결과 파일(iteration_note 미지정)에서는 None — 에러 아님."""
        _save_run(tmp_path, "run_legacy")
        result_set = load_results(tmp_path)
        rf = result_set.files[0]
        assert rf.iteration_note is None

    def test_missing_extra_metrics_key_entirely(self):
        """extra_metrics 자체가 없는(더 오래된) raw dict에서도 에러 없이 None."""
        rf = ResultFile(
            path=None, file_id="f1", name="f1", timestamp="", total_tasks=0, tasks=[],
            accuracy_metrics={}, efficiency_metrics={},
            security_l1=SimpleNamespace(), security_l2=SimpleNamespace(),
            agentic=SimpleNamespace(), quality_detail=SimpleNamespace(),
            hallucination_detail=SimpleNamespace(), advanced=SimpleNamespace(),
            insights=SimpleNamespace(),
            rag_metrics={}, pricing={}, raw={},
        )
        assert rf.iteration_note is None
