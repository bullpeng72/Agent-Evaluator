"""
tests/test_spec044_report_instrument.py
=======================================
SPEC-044 — the HTML report as a quality-evaluation + methodology-driving
instrument: `insights.lifecycle_phase`, the 3-tier structure, the new judgment
cards (next-action / spec-frontmatter / regression-check), the iteration tier
(lifecycle-spine / proof-panel), the collapsible evidence groups, and the
inline JS layer.
"""
from __future__ import annotations

import json
import re

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.comprehensive_report import (
    _build_design_contract,
    _build_history_chart,
    _build_next_action,
    generate_comprehensive_html_report,
    generate_html_from_result_file,
    report_markdown_summary,
)
from agent_evaluator.reporting.insights import build_insights


def _mon(tmp_path, n_pass, n_total, *, covers=None):
    m = PerformanceMonitor(output_dir=str(tmp_path))
    for i in range(n_total):
        ok = i < n_pass
        m.record_task(create_taskresult(
            task_id=f"t{i}", question=f"q{i}",
            response="good" if ok else "bad", ground_truth="good",
            execution_time=0.3, task_type="qa",
            covers=(covers if i == 0 else None),
        ))
    return m


# --------------------------------------------------------------------------- #
# insights.lifecycle_phase
# --------------------------------------------------------------------------- #
class TestLifecyclePhase:
    def _r(self, **over):
        base = {
            "tasks": [{"task_id": "t1", "success": True, "accuracy_score": 0.9,
                       "completion_score": 1.0, "question": "q", "response": "r",
                       "ground_truth": "r"}],
            "extra_metrics": {"harness_groups": {"A": {"score": 0.8, "status": "pass"}}},
        }
        base.update(over)
        return base

    def test_first_run_is_analysis(self):
        lp = build_insights(self._r())["lifecycle_phase"]
        assert lp["primary"] == "analysis"
        assert any("baseline" in m for m in lp["missing"])

    def test_baseline_is_verification(self):
        cur = self._r()
        base = self._r()
        lp = build_insights(cur, base)["lifecycle_phase"]
        assert lp["primary"] == "verification"

    def test_targets_without_baseline_is_design(self):
        lp = build_insights(
            self._r(), targets={"gates": {"A": 0.85}, "tcr_pct": 90},
        )["lifecycle_phase"]
        assert lp["primary"] == "design"

    def test_partial_mode_is_analysis(self):
        lp = build_insights(self._r(), partial=True)["lifecycle_phase"]
        assert lp["primary"] == "analysis"

    def test_order_always_present(self):
        lp = build_insights(self._r())["lifecycle_phase"]
        assert lp["order"] == [
            "analysis", "design", "development", "verification", "operations",
        ]


# --------------------------------------------------------------------------- #
# 3-tier structure
# --------------------------------------------------------------------------- #
class TestThreeTier:
    def test_judgment_tier_before_evidence_groups(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 6, 10))
        i_na = html.find('id="next-action"')
        i_sc = html.find('class="scorecard"')
        i_ev = html.find('class="evidence-group"')
        assert 0 < i_na < i_sc < i_ev

    def test_evidence_groups_render(self, tmp_path):
        # an empty group (nothing to show) drops out entirely — so 4..6, and the
        # always-populated groups (gates, governance) are always there.
        html = generate_comprehensive_html_report(_mon(tmp_path, 8, 10))
        n = html.count('<details class="evidence-group"')
        assert 4 <= n <= 6
        assert 'id="evgrp-gates"' in html
        assert 'id="evgrp-governance"' in html
        # every rendered group id is one of the six known ids
        rendered = set(re.findall(r'<details class="evidence-group" id="([a-z-]+)"', html))
        assert rendered <= {
            "evgrp-gates", "evgrp-failure", "evgrp-evalset",
            "evgrp-stats", "evgrp-version", "evgrp-governance",
        }

    def test_evidence_group_with_signal_auto_opens(self, tmp_path):
        # a failing run -> the gate-detail group carries fail badges -> open
        html = generate_comprehensive_html_report(_mon(tmp_path, 3, 10))
        m = re.search(r'<details class="evidence-group" id="evgrp-gates"( open)?>', html)
        assert m and m.group(1) == " open"

    def test_no_section_dropped_vs_flat_list(self, tmp_path):
        """Every gate-section id from before still renders (restructure, not removal)."""
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        for sid in ("gate-a", "gate-b", "gate-c", "gate-d", "gate-e", "gate-f",
                    "gate-g", "recommendations", "conclusion", "exec-summary"):
            assert f'id="{sid}"' in html


# --------------------------------------------------------------------------- #
# judgment-tier cards
# --------------------------------------------------------------------------- #
class TestNextAction:
    def test_not_ready_offers_apply_verify(self):
        ins = {"verdict": {"level": "not_ready", "failing_gates": ["C"],
                           "targets_source": "builtin"}}
        html = _build_next_action(ins, {})
        assert "improve apply-verify" in html
        assert "--proposal C" in html

    def test_ready_offers_decisions_record(self):
        ins = {"verdict": {"level": "ready", "decision_ready": True,
                           "targets_source": "builtin"}}
        html = _build_next_action(ins, {})
        assert "decisions record" in html

    def test_borderline_offers_repeat(self):
        ins = {"verdict": {"level": "ready", "decision_ready": False,
                           "undecided_reason": "the CI straddles the target",
                           "targets_source": "builtin"}}
        html = _build_next_action(ins, {})
        assert "run_repeated" in html
        assert "exit 75" in html

    def test_targets_provenance_shown(self):
        ins = {"verdict": {"level": "ready", "decision_ready": True,
                           "targets_source": "user",
                           "targets": {"gates": {"A": 0.85}}}}
        html = _build_next_action(ins, {})
        assert "targets.json" in html

    def test_empty_when_no_verdict(self):
        assert _build_next_action({}, {}) == ""

    def test_copy_blocks_are_marked(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 4, 10))
        assert 'pre class="cmd" data-cmd' in html


class TestRegressionCheck:
    def test_fail_with_flag_when_a_case_regresses(self, tmp_path):
        base = _mon(tmp_path, 9, 10)
        bpath = base.save_to_file("baseline")
        baseline = json.loads(open(bpath).read())
        cur = _mon(tmp_path, 6, 10)
        html = generate_comprehensive_html_report(cur, baseline=baseline)
        seg = html[html.find('id="regression-check"'):][:900]
        assert "FAIL" in seg
        assert "--fail-on-case-regression" in seg

    def test_none_without_baseline(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 8, 10))
        seg = html[html.find('id="regression-check"'):][:400]
        assert "No baseline provided" in seg


class TestSpecFrontmatter:
    def test_absent_without_coverage(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 8, 10))
        assert 'id="spec-frontmatter"' not in html

    def test_present_with_covers(self, tmp_path):
        html = generate_comprehensive_html_report(
            _mon(tmp_path, 8, 10, covers=["REQ-001"]),
        )
        assert 'id="spec-frontmatter"' in html


class TestLifecycleSpine:
    def test_renders_strip_and_missing(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        assert 'id="lifecycle-spine"' in html
        seg = html[html.find('id="lifecycle-spine"'):][:1200]
        assert "ls-step on" in seg
        assert "Not in this report" in seg


class TestProofPanel:
    def test_nudges_when_no_experiments(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 6, 10))
        seg = html[html.find('id="proof-panel"'):][:800]
        assert "improve start" in seg


# --------------------------------------------------------------------------- #
# inline JS layer
# --------------------------------------------------------------------------- #
class TestReportJs:
    def test_script_present_and_self_contained(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        assert "<script>" in html
        # no external requests
        assert "src=" not in html.split("<script>")[-1]
        assert "cdn" not in html.lower().split("<script>")[-1]

    def test_readable_with_script_removed(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        stripped = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
        # the verdict + a gate detail + a command are all still in the DOM text
        assert "Deployment" in stripped or "deployment" in stripped
        assert 'id="gate-a"' in stripped
        assert "apply-verify" in stripped or "decisions record" in stripped

    def test_has_expand_collapse_and_copy_wiring(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 5, 10))
        js = html.split("<script>")[-1]
        assert "copy-btn" in js
        assert "Expand all evidence" in js
        assert "mini-verdict" in js
        assert "revealHash" in js


# --------------------------------------------------------------------------- #
# from-result-file path parity
# --------------------------------------------------------------------------- #
class TestFileEntryPointParity:
    def test_same_structure_from_saved_file(self, tmp_path):
        from pathlib import Path

        m = _mon(tmp_path, 6, 10)
        path = m.save_to_file("run")
        # save_to_file already wrote the .html via the monitor path; re-render
        # from the file to exercise generate_html_from_result_file
        from agent_evaluator.serve.loader import parse_file

        rf = parse_file(Path(str(path)))
        html = generate_html_from_result_file(rf)
        for gid in ("next-action", "lifecycle-spine", "proof-panel",
                    "evgrp-gates", "evgrp-governance"):
            assert f'id="{gid}"' in html
        assert 4 <= html.count('<details class="evidence-group"') <= 6


# --------------------------------------------------------------------------- #
# REQ-4 — design contract panel
# --------------------------------------------------------------------------- #
class TestDesignContract:
    def test_lists_measured_and_unmeasured_gates(self):
        hg = {
            "A": {"score": 0.75, "status": "warn"},
            "B": {"score": None},
            "D": {"score": None},
        }
        html = _build_design_contract(hg, {}, None)
        assert 'id="design-contract"' in html
        assert "Gate A" in html and "0.75" in html
        assert "Not configured" in html               # B / D unmeasured
        assert "SLAConfig" in html                    # Gate D's Config hint

    def test_flags_gate_that_regressed_to_unmeasured(self):
        hg = {"A": {"score": 0.8, "status": "pass"}, "F": {"score": None}}
        html = _build_design_contract(hg, {"newly_unmeasured_gates": ["F"]}, None)
        assert "was measured in the baseline" in html

    def test_config_snapshot_attribution(self):
        hg = {"D": {"score": 0.9, "status": "pass"}}
        lineage = {"config_snapshot": {"SLAConfig": {"p95_ms": 3000}}}
        html = _build_design_contract(hg, {}, lineage)
        assert "SLAConfig" in html
        assert "config not recorded" not in html

    def test_empty_without_harness_groups(self):
        assert _build_design_contract({}, {}, None) == ""

    def test_renders_in_full_report_evalset_group(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        assert 'id="design-contract"' in html


# --------------------------------------------------------------------------- #
# REQ-7 — markdown summary + history chart + gate flags
# --------------------------------------------------------------------------- #
class TestMarkdownSummary:
    def test_not_ready_summary_has_verdict_and_command(self):
        ins = {"verdict": {"level": "not_ready", "headline": "Not ready",
                           "failing_gates": ["C"], "confidence": "MEDIUM",
                           "targets_source": "builtin"}}
        md = report_markdown_summary(ins, result_file="v3.json", exit_code=1)
        assert md.startswith("## Gate verdict")
        assert "Hold (exit 1)" in md
        assert "```" in md and "improve apply-verify" in md
        assert "`v3.json`" in md

    def test_ready_summary(self):
        ins = {"verdict": {"level": "ready", "decision_ready": True,
                           "headline": "Ready", "targets_source": "builtin"}}
        md = report_markdown_summary(ins, exit_code=0)
        assert "Ship (exit 0)" in md
        assert "decisions record" in md

    def test_no_verdict_still_returns_a_block(self):
        md = report_markdown_summary({})
        assert md.startswith("## Gate verdict")


class TestHistoryChart:
    def test_absent_under_three_runs(self, tmp_path):
        m = _mon(tmp_path, 6, 10)
        m.save_to_file("only")
        assert _build_history_chart(str(tmp_path), None) == ""

    def test_canvas_and_data_with_enough_runs(self, tmp_path):
        for k in range(4):
            m = _mon(tmp_path, 5 + k, 10)
            m.save_to_file(f"run{k}")
        html = _build_history_chart(str(tmp_path), None)
        assert "ae-history-canvas" in html
        assert '<script type="application/json" id="ae-history-data">' in html
        # payload parses and carries per-gate series
        import json as _j
        import re as _re
        m2 = _re.search(r'id="ae-history-data">(.*?)</script>', html, _re.S)
        assert m2 is not None
        payload = _j.loads(m2.group(1))
        assert "labels" in payload and "series" in payload
        assert len(payload["labels"]) >= 3

    def test_js_draws_the_chart(self, tmp_path):
        for k in range(4):
            _mon(tmp_path, 5 + k, 10).save_to_file(f"run{k}")
        # generate_html_from_result_file scans the sibling dir for history
        from pathlib import Path

        from agent_evaluator.serve.loader import parse_file

        newest = sorted(Path(tmp_path).glob("run*.json"))[-1]
        html = generate_html_from_result_file(parse_file(newest))
        assert "drawHistory" in html
        assert "ae-history-canvas" in html


class TestGateHtmlFlags:
    def _ns(self, **kw):
        base = dict(
            result_file="", tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, fail_on_regression=None,
            baseline=None, baseline_version=None, save_baseline=False,
            junit_xml=None, golden_set=None, fail_on_golden_regression=False,
            explain=False, min_gate_score=None, gate_weights=None,
            gate_thresholds=None, required_gates=None, fail_on_gate_warn=False,
            baseline_result=None, fail_on_case_regression=False,
            max_review_high=None, notify=None, hold_on_undecided=False,
            requirements=None, require_spec_coverage=False, decision_log=None,
            digest=False, max_cost_per_task=None, html_out=None,
            html_summary=False,
        )
        base.update(kw)
        import argparse

        return argparse.Namespace(**base)

    def test_html_out_writes_file(self, tmp_path, capsys):
        from agent_evaluator.cli.gate import cmd_gate

        m = _mon(tmp_path, 7, 10)
        p = m.save_to_file("run")
        out = tmp_path / "report.html"
        cmd_gate(self._ns(result_file=str(p), html_out=str(out)))
        assert out.is_file() and out.stat().st_size > 1000
        assert "evidence-group" in out.read_text()

    def test_html_summary_prints_markdown(self, tmp_path, capsys):
        from agent_evaluator.cli.gate import cmd_gate

        m = _mon(tmp_path, 4, 10)
        p = m.save_to_file("run")
        cmd_gate(self._ns(result_file=str(p), html_summary=True))
        out = capsys.readouterr().out
        assert "## Gate verdict" in out
        assert "### Next" in out

    def test_neither_flag_no_extra_output(self, tmp_path, capsys):
        from agent_evaluator.cli.gate import cmd_gate

        m = _mon(tmp_path, 7, 10)
        p = m.save_to_file("run")
        cmd_gate(self._ns(result_file=str(p)))
        out = capsys.readouterr().out
        assert "## Gate verdict" not in out
        assert "HTML report:" not in out


# --------------------------------------------------------------------------- #
# example-report audit regressions (SPEC-044 audit round)
# --------------------------------------------------------------------------- #
class TestAuditRegressions:
    def test_evidence_group_marker_is_presence_not_count(self, tmp_path):
        # a failing run: the group marker must not print a misleading number
        # (priority labels like badge-warn">LOW over-count; a failing gate
        # double-counts as badge-fail + >FAIL</span>)
        from agent_evaluator.reporting.comprehensive_report import _wrap_evidence_group

        body = [
            '<div class="gate-section" id="x"><span class="badge badge-warn">LOW</span>'
            '<span class="badge badge-warn">LOW</span></div>',
            # a real gate h2 renders the status as bare text in a span
            '<div class="gate-section" id="y"><h2>Gate A <span style="...">FAIL</span>'
            '</h2><span class="badge-fail">FAIL Gate A</span></div>',
        ]
        # not the failure group -> the LOW priority labels must NOT drive a marker,
        # but the real >FAIL</span> h2 badge opens the group
        html = _wrap_evidence_group("evgrp-governance", "Governance", body)
        assert "needs review" in html          # presence marker, not a digit
        assert not re.search(r"evgrp-tag \w+\">&#\d+; \d+</span>", html)  # no "⚠ 5"
        assert " open>" in html
        # a group with only LOW priority labels (no real status marker) stays shut
        low_only = _wrap_evidence_group(
            "evgrp-stats", "Stats",
            ['<div class="gate-section" id="z"><span class="badge badge-warn">LOW</span></div>'],
        )
        assert " open>" not in low_only and "needs review" not in low_only

    def test_evgrp_section_count_matches_body(self, tmp_path):
        from agent_evaluator.reporting.comprehensive_report import _wrap_evidence_group

        secs = ['<div class="gate-section" id="a">A</div>',
                '', '   ',
                '<div class="gate-section" id="b">B</div>']
        html = _wrap_evidence_group("evgrp-stats", "Stats", secs)
        m = re.search(r'evgrp-meta">(\d+) section', html)
        assert m and m.group(1) == "2"         # empties dropped

    def test_history_chart_labels_use_filenames(self, tmp_path):
        for k in range(4):
            _mon(tmp_path, 5 + k, 10).save_to_file(f"iter{k}")
        html = _build_history_chart(str(tmp_path), None)
        m = re.search(r'id="ae-history-data">(.*?)</script>', html, re.S)
        assert m is not None
        labels = json.loads(m.group(1))["labels"]
        assert any("iter" in x for x in labels)   # not bare indices

    def test_lifecycle_missing_empty_when_all_material_present(self, tmp_path):
        # baseline + targets + experiments + decision-log -> nothing "missing"
        import os

        d = tmp_path / "full"
        d.mkdir()
        aoo = d / ".aoo"
        aoo.mkdir()
        (aoo / "targets.json").write_text('{"gates":{"A":0.8}}')
        from agent_evaluator.rca.decision_ledger import record_gate_decision
        from agent_evaluator.rca.experiments import register_experiment

        register_experiment(str(aoo / "experiments.jsonl"), target_gate="A",
                            predicted_delta=0.05, note="[improve] x", baseline_ref="b")
        record_gate_decision(str(aoo / "decisions.jsonl"), result_file="b",
                             agent_version="v1", exit_code=1, verdict_level="not_ready",
                             decision_ready=True)
        cwd = os.getcwd()
        os.chdir(d)
        try:
            base = _mon(d, 9, 12)
            bpath = base.save_to_file("baseline")
            baseline = json.loads(open(bpath).read())
            cur = _mon(d, 7, 12)
            ins = build_insights(
                json.loads(open(cur.save_to_file("cur")).read()), baseline,
                experiments_log_path=str(aoo / "experiments.jsonl"),
                decision_log_path=str(aoo / "decisions.jsonl"),
                targets={"gates": {"A": 0.8}},
            )
        finally:
            os.chdir(cwd)
        lp = ins["lifecycle_phase"]
        assert lp["primary"] == "development"
        assert lp["missing"] == []


# --------------------------------------------------------------------------- #
# REQ-6 remaining — theme toggle / diff mode / failure filter
# --------------------------------------------------------------------------- #
class TestReq6Remaining:
    def test_dark_theme_css_and_toggle_wiring(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        # explicit-toggle dark palette (no prefers-color-scheme dependency)
        assert ':root[data-theme="dark"] .container' in html
        assert ':root[data-theme="dark"] details.evidence-group' in html
        js = html.split("<script>")[-1]
        assert 'setAttribute("data-theme", "dark")' in js
        assert 'removeAttribute("data-theme")' in js          # toggles back
        # the toggle is JS-injected, not a dead button in the static DOM
        assert 'class="report-controls"' not in html.split("<script>")[0]

    def test_toc_uses_class_not_inline_style(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 8, 10))
        assert '<div class="report-toc">' in html
        assert 'background:#fffffff2' not in html.split('<div class="report-toc">')[1][:200]
        assert '.report-toc{' in html                          # styled via CSS

    def test_diff_mode_only_with_baseline(self, tmp_path):
        # no baseline -> HAS_BASELINE false, no data-has-change attrs, no diff btn
        solo = generate_comprehensive_html_report(_mon(tmp_path, 7, 10))
        assert "HAS_BASELINE = false" in solo
        assert not re.search(
            r'<details class="evidence-group"[^>]*data-has-change', solo)

        base = _mon(tmp_path, 9, 10)
        bp = base.save_to_file("baseline")
        baseline = json.loads(open(bp).read())
        cur = generate_comprehensive_html_report(_mon(tmp_path, 6, 10), baseline=baseline)
        assert "HAS_BASELINE = true" in cur
        # the version + failure groups carry the diff marker
        assert re.search(
            r'<details class="evidence-group" id="evgrp-version"[^>]*data-has-change="1"', cur)
        assert re.search(
            r'<details class="evidence-group" id="evgrp-failure"[^>]*data-has-change="1"', cur)
        # the other groups do NOT
        assert not re.search(
            r'<details class="evidence-group" id="evgrp-stats"[^>]*data-has-change', cur)
        assert "body.diff-mode details.evidence-group:not([data-has-change])" in cur
        assert 'diffBtn' in cur.split("<script>")[-1]

    def test_failure_filter_js_present(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 3, 10))
        js = html.split("<script>")[-1]
        assert "failureFilter" in js
        assert 'getElementById("failure-cases")' in js
        assert "ff-filter" in html                             # CSS class

    def test_script_still_single_and_self_contained(self, tmp_path):
        html = generate_comprehensive_html_report(_mon(tmp_path, 5, 10))
        assert html.count("<script>") == 1 and html.count("</script>") == 1
        tail = html.split("<script>")[-1]
        assert "src=" not in tail and "http" not in tail
        # readable with the script gone
        stripped = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
        assert 'id="gate-a"' in stripped and 'id="next-action"' in stripped
