"""
tests/test_spec045_blocked_attempts_report.py
==================================================
SPEC-045 REQ-8: the HTML report surfaces LiveGuardrail's blocked_attempts —
a passive-discovery banner above the fold + a full audit section in the
Governance evidence group (auto-opened), so a session that looks clean on
Gate B/E scores still visibly shows a human that something was blocked.
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.comprehensive_report import (
    _build_blocked_attempts_audit,
    _build_blocked_attempts_banner,
    generate_comprehensive_html_report,
)


class TestBuildBlockedAttemptsAudit:
    def test_none_input_renders_empty(self):
        assert _build_blocked_attempts_audit(None) == ""

    def test_zero_total_renders_empty(self):
        assert _build_blocked_attempts_audit({"total": 0, "items": []}) == ""

    def test_populated_renders_section_with_excerpt_and_cli_hint(self):
        html = _build_blocked_attempts_audit({
            "total": 2, "sessions_affected": 1,
            "by_gate": {"B": 2}, "by_tool": {"Bash": 2},
            "items": [
                {"task_id": "s1", "gate": "B", "tool_name": "Bash",
                 "reason": "dangerous tool parameters",
                 "arg_excerpt": "some captured command text"},
            ],
            "note": "2 tool call(s) blocked...",
        })
        assert 'id="blocked-attempts-audit"' in html
        assert "some captured command text" in html
        assert "agent-eval claude blocked-detail s1" in html
        # SPEC-044 auto-open marker convention — governance group must pick this up.
        assert 'class="ibox warn"' in html
        assert "never affect Gate B/E scores" in html


class TestBuildBlockedAttemptsBanner:
    def test_none_input_renders_empty(self):
        assert _build_blocked_attempts_banner(None) == ""

    def test_zero_total_renders_empty(self):
        assert _build_blocked_attempts_banner({"total": 0}) == ""

    def test_populated_renders_banner_linking_to_audit_section(self):
        html = _build_blocked_attempts_banner({"total": 3, "sessions_affected": 2})
        assert "3 tool call(s) blocked" in html
        assert 'href="#blocked-attempts-audit"' in html


class TestEndToEndReportRendering:
    def _mon_with_blocked_task(self, tmp_path):
        m = PerformanceMonitor(output_dir=str(tmp_path))
        m.record_task(create_taskresult(
            task_id="t0", question="q", response="r", ground_truth="r",
            execution_time=0.3, task_type="qa",
            extra={"blocked_attempts": [
                {"tool_name": "Bash", "gate": "B",
                 "reason": "dangerous tool parameters: ['Bash']",
                 "arg_excerpt": "rm -rf SOMEWHERE"},
            ]},
        ))
        return m

    def test_html_report_contains_banner_and_audit_section(self, tmp_path):
        m = self._mon_with_blocked_task(tmp_path)
        html = generate_comprehensive_html_report(m)
        assert "tool call(s) blocked this run" in html
        assert 'id="blocked-attempts-audit"' in html
        assert "rm -rf SOMEWHERE" in html

    def test_governance_group_auto_opens_when_something_was_blocked(self, tmp_path):
        m = self._mon_with_blocked_task(tmp_path)
        html = generate_comprehensive_html_report(m)
        idx = html.index('id="evgrp-governance"')
        # the <details> tag for this group must carry the `open` attribute
        tag_start = html.rindex("<details", 0, idx)
        tag_end = html.index(">", idx)
        assert " open" in html[tag_start:tag_end]

    def test_clean_session_renders_no_banner_or_audit_section(self, tmp_path):
        m = PerformanceMonitor(output_dir=str(tmp_path))
        m.record_task(create_taskresult(
            task_id="t0", question="q", response="r", ground_truth="r",
            execution_time=0.3, task_type="qa",
        ))
        html = generate_comprehensive_html_report(m)
        assert "tool call(s) blocked this run" not in html
        assert 'id="blocked-attempts-audit"' not in html
