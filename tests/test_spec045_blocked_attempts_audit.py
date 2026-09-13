"""
tests/test_spec045_blocked_attempts_audit.py
================================================
SPEC-045 REQ-7 — LiveGuardrail's ``extra.blocked_attempts`` surfaced as
``insights.blocked_attempts_audit`` (display only — never a Gate score, mirrors
SPEC-042's ``acceptance_coverage`` pattern). Generic over origin: identical whether
tasks came from a live-guardrail host bridge or a batch ``@agent_eval`` run.
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import build_insights


def _task(tid, timestamp="2026-09-11T00:00:00", blocked_attempts=None):
    t = {
        "task_id": tid,
        "timestamp": timestamp,
        "success": True,
        "accuracy_score": 0.9,
        "completion_score": 1.0,
        "question": "q",
        "response": "r",
        "ground_truth": "gt",
        "task_type": "qa",
    }
    if blocked_attempts is not None:
        t["extra"] = {"blocked_attempts": blocked_attempts}
    return t


def _result(tasks):
    return {
        "summary": {"tcr": 90.0, "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {"A": {"score": 0.9, "status": "pass"}}},
        "tasks": tasks,
    }


class TestBlockedAttemptsAuditSection:
    def test_none_when_no_task_carries_blocked_attempts(self):
        ins = build_insights(_result([_task("t1")]))
        assert ins["blocked_attempts_audit"] is None

    def test_none_when_blocked_attempts_is_empty_list(self):
        """SPEC-030 REQ-2: snapshot() always includes the key, empty or not — an empty
        list must not be treated as "there was an audit finding"."""
        ins = build_insights(_result([_task("t1", blocked_attempts=[])]))
        assert ins["blocked_attempts_audit"] is None

    def test_single_blocked_attempt_is_surfaced(self):
        ins = build_insights(_result([_task("t1", blocked_attempts=[
            {"tool_name": "Bash", "gate": "B", "reason": "dangerous tool parameters",
             "arg_excerpt": "some captured command"},
        ])]))
        audit = ins["blocked_attempts_audit"]
        assert audit is not None
        assert audit["total"] == 1
        assert audit["sessions_affected"] == 1
        assert audit["by_gate"] == {"B": 1}
        assert audit["by_tool"] == {"Bash": 1}
        assert audit["items"][0]["task_id"] == "t1"
        assert audit["items"][0]["arg_excerpt"] == "some captured command"

    def test_counts_aggregate_across_sessions_and_gates(self):
        ins = build_insights(_result([
            _task("t1", timestamp="2026-09-10T00:00:00", blocked_attempts=[
                {"tool_name": "Bash", "gate": "B", "reason": "r1"},
                {"tool_name": "Bash", "gate": "B", "reason": "r2"},
            ]),
            _task("t2", timestamp="2026-09-11T00:00:00", blocked_attempts=[
                {"tool_name": "Write", "gate": "E", "reason": "r3"},
            ]),
        ]))
        audit = ins["blocked_attempts_audit"]
        assert audit["total"] == 3
        assert audit["sessions_affected"] == 2
        assert audit["by_gate"] == {"B": 2, "E": 1}
        assert audit["by_tool"] == {"Bash": 2, "Write": 1}

    def test_items_sorted_most_recent_first(self):
        ins = build_insights(_result([
            _task("older", timestamp="2026-09-01T00:00:00",
                  blocked_attempts=[{"tool_name": "Bash", "gate": "B", "reason": "r"}]),
            _task("newer", timestamp="2026-09-10T00:00:00",
                  blocked_attempts=[{"tool_name": "Bash", "gate": "B", "reason": "r"}]),
        ]))
        items = ins["blocked_attempts_audit"]["items"]
        assert [i["task_id"] for i in items] == ["newer", "older"]

    def test_generic_over_origin_batch_agent_eval_task_also_surfaces(self):
        """A plain batch @agent_eval task (no live-guardrail host bridge involved) that
        merged guardrail.to_task_extra() into EvalMetadata(extra=...) must be surfaced
        identically — this section never special-cases where the task came from."""
        ins = build_insights(_result([_task("batch-t1", blocked_attempts=[
            {"tool_name": "shell_exec", "gate": "B", "reason": "dangerous tool parameters"},
        ])]))
        assert ins["blocked_attempts_audit"]["total"] == 1

    def test_never_a_gate_score_note_present(self):
        ins = build_insights(_result([_task("t1", blocked_attempts=[
            {"tool_name": "Bash", "gate": "B", "reason": "r"},
        ])]))
        assert "never scored against Gate B/E" in ins["blocked_attempts_audit"]["note"]

    def test_malformed_blocked_attempts_entries_are_skipped_not_raising(self):
        ins = build_insights(_result([_task("t1", blocked_attempts=["not-a-dict", 42, None])]))
        assert ins["blocked_attempts_audit"] is None

    def test_partial_mode_also_carries_the_section(self):
        """SPEC-050-style partial/mid-run insights should carry the same signal."""
        ins = build_insights(_result([_task("t1", blocked_attempts=[
            {"tool_name": "Bash", "gate": "B", "reason": "r"},
        ])]), partial=True)
        assert ins["blocked_attempts_audit"] is not None
        assert ins["blocked_attempts_audit"]["total"] == 1
