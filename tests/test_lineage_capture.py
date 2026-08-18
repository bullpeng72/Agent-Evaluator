"""
tests/test_lineage_capture.py
===============================
SPEC-007: 감사/재현성 Lineage 캡처 검증.
"""
from unittest.mock import MagicMock, patch

from agent_evaluator import PerformanceMonitor, create_taskresult


class TestLineageAlwaysPresent:
    def test_lineage_present_even_with_no_tasks(self):
        m = PerformanceMonitor()
        report = m.generate_report()
        assert report.extra_metrics is not None
        lineage = report.extra_metrics["lineage"]
        assert lineage["sdk_version"] is not None
        assert "git_commit" in lineage
        assert lineage["prompt_version"] is None
        assert lineage["agent_version"] is None
        assert lineage["iteration_note"] is None
        assert lineage["judge_model_snapshot"] is None

    def test_lineage_present_alongside_harness_groups(self):
        m = PerformanceMonitor()
        m.record_task(create_taskresult(task_id="t1", question="q", response="r", execution_time=1.0))
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert "harness_groups" in report.extra_metrics
        assert "lineage" in report.extra_metrics


class TestPromptAndAgentVersionPassthrough:
    def test_custom_tags_stored_verbatim(self):
        m = PerformanceMonitor(prompt_version="v3.2", agent_version="agent-2026-07")
        report = m.generate_report()
        assert report.extra_metrics is not None
        lineage = report.extra_metrics["lineage"]
        assert lineage["prompt_version"] == "v3.2"
        assert lineage["agent_version"] == "agent-2026-07"


class TestIterationNotePassthrough:
    """SPEC-029: iteration_note는 새 계산 없이 그대로 lineage에 실린다."""

    def test_note_stored_verbatim(self):
        m = PerformanceMonitor(iteration_note="플랜 단계를 먼저 세우게 지시문 추가")
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["lineage"]["iteration_note"] == "플랜 단계를 먼저 세우게 지시문 추가"

    def test_note_alongside_agent_version(self):
        m = PerformanceMonitor(agent_version="v2-cot", iteration_note="루프 탐지 threshold 완화")
        report = m.generate_report()
        assert report.extra_metrics is not None
        lineage = report.extra_metrics["lineage"]
        assert lineage["agent_version"] == "v2-cot"
        assert lineage["iteration_note"] == "루프 탐지 threshold 완화"

    def test_default_is_none(self):
        m = PerformanceMonitor()
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["lineage"]["iteration_note"] is None


class TestGitCommitFailureSafety:
    def test_git_missing_returns_none_not_exception(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            m = PerformanceMonitor()  # 예외 전파 없이 생성돼야 함 (REQ-2)
        assert m._git_commit is None

    def test_git_nonzero_returncode_returns_none(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=128, stdout="")):
            m = PerformanceMonitor()
        assert m._git_commit is None

    def test_git_commit_cached_once_not_per_report_call(self):
        call_count = {"n": 0}

        def fake_run(*args, **kwargs):
            call_count["n"] += 1
            return MagicMock(returncode=0, stdout="abc123def\n")

        with patch("subprocess.run", side_effect=fake_run):
            m = PerformanceMonitor()
            m.generate_report()
            m.generate_report()
            m.generate_report()

        assert call_count["n"] == 1  # REQ-3: 인스턴스 생성 시 1회만
        assert m._git_commit == "abc123def"


class TestJudgeModelSnapshot:
    def test_snapshot_from_most_recent_judged_task(self):
        m = PerformanceMonitor()
        m.llm_judge = MagicMock(model="claude-haiku-4-5")
        m.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0,
            llm_judge={"model": "claude-haiku-4-5", "model_snapshot": "claude-haiku-4-5-20251001", "scores": {}},
        ))
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["lineage"]["judge_model_snapshot"] == "claude-haiku-4-5-20251001"

    def test_snapshot_falls_back_to_configured_model_when_missing(self):
        m = PerformanceMonitor()
        m.llm_judge = MagicMock(model="claude-haiku-4-5")
        m.record_task(create_taskresult(task_id="t1", question="q", response="r", execution_time=1.0))
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["lineage"]["judge_model_snapshot"] == "claude-haiku-4-5"

    def test_snapshot_none_when_judge_disabled(self):
        m = PerformanceMonitor()
        m.record_task(create_taskresult(task_id="t1", question="q", response="r", execution_time=1.0))
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics["lineage"]["judge_model_snapshot"] is None


class TestLLMJudgeParseResponseModelSnapshot:
    def test_model_snapshot_uses_provider_value_when_given(self):
        from agent_evaluator.integrations.llm_judge import LLMJudge
        judge = LLMJudge(model="claude-haiku-4-5")
        result = judge._parse_judge_response(
            "t1",
            '{"completeness":4,"relevance":4,"factual_consistency":4,"toxicity":0,"bias":0,"reasoning":"ok"}',
            cost=0.001,
            model="claude-haiku-4-5",
            model_snapshot="claude-haiku-4-5-20251001",
        )
        assert result["model_snapshot"] == "claude-haiku-4-5-20251001"

    def test_model_snapshot_falls_back_to_model_when_absent(self):
        from agent_evaluator.integrations.llm_judge import LLMJudge
        judge = LLMJudge(model="claude-haiku-4-5")
        result = judge._parse_judge_response(
            "t1",
            '{"completeness":4,"relevance":4,"factual_consistency":4,"toxicity":0,"bias":0,"reasoning":"ok"}',
            cost=0.001,
            model="claude-haiku-4-5",
        )
        assert result["model_snapshot"] == "claude-haiku-4-5"
