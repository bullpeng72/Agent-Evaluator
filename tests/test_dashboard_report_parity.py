"""
tests/test_dashboard_report_parity.py
========================================
The dashboard (serve/routers/data.py) and the static HTML report
(reporting/comprehensive_report.py) read the same ResultFile — a metric shown
on both surfaces must be the *same number*.

Two mismatches this pins down:
  1. "Hallucination Rate" — the report / ResultFile.hallucination_rate / the
     Gate C-G score use ``overall_rate`` = mean(per-task rate) x 100. ``_to_meta``
     used flagged / evaluated x 100 (task incidence) under the same label.
  2. "Total Tasks" — the report keys its headline off the parsed task list;
     ``_to_meta`` / the detail endpoint used the file's declared ``total_tasks``,
     which can disagree (sampled export, partial write, dropped non-dict rows).
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from agent_evaluator.reporting.comprehensive_report import generate_html_from_result_file
from agent_evaluator.serve.loader import parse_file
from agent_evaluator.serve.routers.data import _to_meta


def _rf(raw: dict):
    p = Path(tempfile.mktemp(suffix=".json"))
    p.write_text(json.dumps(raw), encoding="utf-8")
    return parse_file(p)


class TestHallucinationRateParity:
    # 3 of 7 tasks flagged, but the flagged ones are only partially hallucinated,
    # so mean-severity (overall_rate) != incidence (flagged/evaluated).
    RAW = {
        "accuracy_metrics": {
            "tcr": {"tcr": 55.0},
            "hallucination": {
                "overall_rate": 21.5,          # mean(per-task rate) x 100
                "total_evaluated": 7,
                "total_flagged": 3,            # 3/7 x 100 = 42.86 incidence
            },
        },
        "tasks": [
            {"task_id": f"t{i}", "success": True, "completion_score": 0.6,
             "accuracy_score": 0.6, "execution_time": 1.0}
            for i in range(7)
        ],
    }

    def test_to_meta_uses_overall_rate_not_incidence(self):
        meta = _to_meta(_rf(self.RAW))
        assert meta["hallucination"] == pytest.approx(21.5)
        # incidence is still available, just under its own key
        assert meta["hallucination_incidence"] == pytest.approx(42.86, abs=0.01)
        assert meta["hallucination_flagged"] == 3
        assert meta["hallucination_evaluated"] == 7

    def test_dashboard_matches_report_headline(self):
        rf = _rf(self.RAW)
        meta = _to_meta(rf)
        html = generate_html_from_result_file(rf)
        # the "Hallucination Detection" section KPI renders the rate the user sees
        seg = html[html.find("Hallucination Detection"):]
        m = re.search(r'Hallucination Rate</div><div class="kpi-val"[^>]*>([\d.]+)%', seg)
        assert m, "report should render a Hallucination Rate KPI"
        assert float(m.group(1)) == pytest.approx(meta["hallucination"], abs=0.1)
        # and it must NOT be the flagged/evaluated incidence (42.86)
        assert float(m.group(1)) != pytest.approx(meta["hallucination_incidence"], abs=0.1)

    def test_resultfile_property_is_the_canonical_one(self):
        rf = _rf(self.RAW)
        assert rf.hallucination_rate == pytest.approx(21.5)
        assert _to_meta(rf)["hallucination"] == pytest.approx(rf.hallucination_rate)


class TestTaskCountParity:
    DECLARED_GT_ACTUAL = {
        "total_tasks": 10,
        "accuracy_metrics": {"tcr": {"tcr": 66.6}},
        "tasks": [
            {"task_id": f"t{i}", "success": i < 2, "completion_score": 0.7,
             "accuracy_score": 0.6, "execution_time": 1.0}
            for i in range(3)
        ],
    }
    SUMMARY_ONLY = {"total_tasks": 42, "accuracy_metrics": {"tcr": {"tcr": 80.0}}}

    def test_task_count_property_prefers_parsed(self):
        rf = _rf(self.DECLARED_GT_ACTUAL)
        assert rf.total_tasks == 10        # declared, untouched
        assert rf.task_count == 3          # parsed

    def test_task_count_falls_back_to_declared_when_no_tasks(self):
        rf = _rf(self.SUMMARY_ONLY)
        assert rf.task_count == 42

    def test_to_meta_matches_report_headline(self):
        rf = _rf(self.DECLARED_GT_ACTUAL)
        meta = _to_meta(rf)
        assert meta["total_tasks"] == 3
        assert meta["total_tasks_declared"] == 10
        html = generate_html_from_result_file(rf)
        # the report's headline "N tasks" must be the same 3
        assert re.search(r"\b3\s+tasks\b", html)
        assert not re.search(r"\b10\s+tasks\b", html)

    def test_summary_only_file_agrees_on_declared(self):
        rf = _rf(self.SUMMARY_ONLY)
        assert _to_meta(rf)["total_tasks"] == 42
        html = generate_html_from_result_file(rf)
        assert re.search(r"\b42\s+tasks\b", html)


class TestStoredAggregateFallbackParity:
    """When a partial / older-SDK / externally-produced file has tasks but no
    stored ``accuracy_metrics`` / ``efficiency_metrics`` aggregate, the dashboard
    detail view recomputes from the per-task list (``_tcr()`` / ``_latPct()``)
    while the list card and the static report used to read a flat 0.0.
    ResultFile.tcr / .accuracy / .avg_latency / .p95_latency / .total_tokens now
    carry the same fallback so every surface shows one number."""

    PARTIAL = {
        "tasks": [
            {"task_id": f"t{i}", "success": i % 4 != 0,
             "completion_score": 0.8 if i % 4 != 0 else 0.2,
             "accuracy_score": 0.7 if i % 4 != 0 else 0.1,
             "execution_time": 1.0 + i * 0.5,
             "tokens_used": {"input": 100, "output": 50}}
            for i in range(8)
        ],
    }

    def test_resultfile_properties_fall_back_to_per_task(self):
        rf = _rf(self.PARTIAL)
        comps = [t.completion_score for t in rf.tasks]
        accs = [t.accuracy_score for t in rf.tasks]
        xs = sorted(t.execution_time for t in rf.tasks)
        assert rf.tcr == pytest.approx(sum(comps) / len(comps) * 100)
        assert rf.accuracy == pytest.approx(sum(accs) / len(accs) * 100)
        assert rf.avg_latency == pytest.approx(sum(xs) / len(xs))
        assert rf.p95_latency == pytest.approx(xs[min(len(xs) - 1, int(len(xs) * 0.95))])
        assert rf.total_tokens == 8 * 150

    def test_cost_per_task_falls_back_to_total_over_task_count(self):
        # file has total_cost but no avg_cost_per_task, and declared != actual
        rf = _rf({
            "total_tasks": 10,
            "efficiency_metrics": {"tokens": {"total_cost": 0.5}},
            "accuracy_metrics": {"tcr": {"tcr": 80}},
            "tasks": [{"task_id": f"t{i}", "success": True, "completion_score": 0.9,
                       "accuracy_score": 0.8, "execution_time": 1.0}
                      for i in range(4)],
        })
        # dashboard shows "per task: $" = cTotal / task_count = 0.5 / 4
        assert rf.avg_cost_per_task == pytest.approx(0.125)
        html = generate_html_from_result_file(rf)
        m = re.search(r'Cost/Task</div><div class="kpi-val">\$?([0-9.]+)', html)
        assert m and float(m.group(1)) == pytest.approx(0.125, abs=0.001)

    def test_stored_cost_per_task_still_wins(self):
        rf = _rf({
            "efficiency_metrics": {"tokens": {"total_cost": 9.9,
                                              "avg_cost_per_task": 0.033}},
            "accuracy_metrics": {"tcr": {"tcr": 80}},
            "tasks": [{"task_id": "a", "success": True, "completion_score": 1.0,
                       "accuracy_score": 1.0, "execution_time": 1.0}],
        })
        assert rf.avg_cost_per_task == pytest.approx(0.033)

    def test_dashboard_list_card_matches_report_headline(self):
        rf = _rf(self.PARTIAL)
        meta = _to_meta(rf)
        html = generate_html_from_result_file(rf)

        def num(pat):
            m = re.search(pat, html)
            return float(m.group(1)) if m else None

        assert num(r"TCR[:\s</strongp>]{1,25}([0-9.]+)%") == pytest.approx(meta["tcr"], abs=0.1)
        assert num(r"Accuracy:</strong>\s*([0-9.]+)%") == pytest.approx(meta["accuracy"], abs=0.1)
        assert num(r'Mean</div><div class="kpi-val">([0-9.]+)s') == pytest.approx(
            meta["avg_latency"], abs=0.05)
        assert num(r'P95</div><div class="kpi-val">([0-9.]+)s') == pytest.approx(
            rf.p95_latency, abs=0.05)

    def test_well_formed_file_still_uses_stored_values(self):
        rf = _rf({
            "accuracy_metrics": {
                "tcr": {"tcr": 91.5},
                "accuracy_scores": {"overall_accuracy": 88.0},
            },
            "efficiency_metrics": {"latency": {"mean": 3.3, "p95": 7.1},
                                   "tokens": {"total_tokens": 999}},
            # per-task scores are deliberately far off the stored aggregates
            "tasks": [{"task_id": "a", "success": True, "completion_score": 0.1,
                       "accuracy_score": 0.1, "execution_time": 99.0,
                       "tokens_used": {"input": 1, "output": 1}}],
        })
        assert rf.tcr == 91.5
        assert rf.accuracy == 88.0
        assert rf.avg_latency == 3.3
        assert rf.p95_latency == 7.1
        assert rf.total_tokens == 999


class TestImproveTabInsightsParity:
    """The dashboard "Improve" tab renders ``/api/diagnose/{id}``'s
    ``result["insights"]`` (built by serve/routers/diagnose.py); the static
    report renders its own ``build_insights`` call. They must pass the same
    optional inputs or the two disagree — most visibly the verdict, which
    measures against ``.aoo/targets.json`` in the report but used to measure
    against the built-in 0.7 on the dashboard."""

    def test_verdict_matches_when_targets_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        aoo = tmp_path / ".aoo"
        aoo.mkdir()
        (aoo / "targets.json").write_text(
            json.dumps({"gate_default": 0.7, "gates": {"E": 0.95}, "tcr_pct": 90}),
            encoding="utf-8",
        )
        raw = {
            "accuracy_metrics": {"tcr": {"tcr": 72}},
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.8, "status": "pass"},
                "E": {"score": 0.85, "status": "pass"},
            }},
            "tasks": [
                {"task_id": f"t{i}", "success": i % 3 != 0, "completion_score": 0.7,
                 "accuracy_score": 0.6, "execution_time": 1.0}
                for i in range(12)
            ],
        }
        rf_path = tmp_path / "v3.json"
        rf_path.write_text(json.dumps(raw), encoding="utf-8")
        rf = parse_file(rf_path)

        from agent_evaluator.reporting.insights import build_insights
        from agent_evaluator.utils.targets import load_targets

        tg = load_targets()
        assert tg and tg.get("tcr_pct") == 90  # sanity: the file is picked up

        # how the static report calls it
        report_ins = build_insights(
            rf.raw, None, targets=tg,
            history_dir=str(tmp_path), current_file=str(rf_path),
        )
        # how serve/routers/diagnose.py now calls it (targets + history_dir + current_file)
        dash_ins = build_insights(
            rf.raw, None, targets=tg,
            history_dir=str(tmp_path), current_file=str(rf_path),
        )
        # and how it USED to call it — no targets → different verdict
        old_dash_ins = build_insights(rf.raw, None)

        assert report_ins["verdict"] == dash_ins["verdict"]
        assert report_ins["verdict"]["level"] == "caution"       # TCR 72 < target 90
        assert old_dash_ins["verdict"]["level"] == "ready"       # the bug: ignored SLO


class TestFallbackGateScoreParity:
    """A file with no stored ``extra_metrics.harness_groups`` gets its A-G scores
    from ``loader._compute_harness_groups_fallback``. Gate A/D read the stored
    ``accuracy_metrics`` / ``latency`` aggregates — when those are absent too they
    used a flat 0, so the Scorecard showed Gate A 0% while the report header
    (ResultFile.tcr) showed the real 65%. Both now use the per-task fallback."""

    PARTIAL = {
        "tasks": [
            {"task_id": f"t{i}", "success": i % 4 != 0,
             "completion_score": 0.8 if i % 4 != 0 else 0.2,
             "accuracy_score": 0.7 if i % 4 != 0 else 0.1,
             "execution_time": 2.0}
            for i in range(8)
        ],
    }

    def test_gate_a_score_tracks_the_headline_numbers(self):
        rf = _rf(self.PARTIAL)
        a = (rf.harness_groups or {}).get("A", {}).get("score")
        assert a == pytest.approx((rf.tcr / 100 + rf.accuracy / 100) / 2, abs=0.001)
        assert a == pytest.approx(0.60, abs=0.01)          # not 0.0

    def test_gate_d_score_uses_per_task_p95_when_no_latency_block(self):
        rf = _rf(self.PARTIAL)
        # exec_time 2.0s -> p95 < 5s -> score 1.0 (was 0.5 "unknown" before)
        assert (rf.harness_groups or {}).get("D", {}).get("score") == pytest.approx(1.0)

    def test_stored_aggregates_still_win_over_per_task(self):
        rf = _rf({
            "accuracy_metrics": {"tcr": {"tcr": 90},
                                 "accuracy_scores": {"overall_accuracy": 80}},
            "tasks": [{"task_id": "a", "success": True, "completion_score": 0.1,
                       "accuracy_score": 0.1, "execution_time": 1.0}],
        })
        assert (rf.harness_groups or {}).get("A", {}).get("score") == pytest.approx(0.85)

    def test_report_scorecard_not_internally_contradictory(self):
        rf = _rf(self.PARTIAL)
        html = generate_html_from_result_file(rf)
        # headline TCR ~65%; the Gate A scorecard badge must not be 0%
        assert re.search(r"\b6[0-9](?:\.[0-9])?%", html)   # a ~60-69% number is present
        seg = html[html.find("sc-card"):]
        # crude: the Gate A card's percent should be in the 55-65 band, never 0
        m = re.search(r"Gate A.*?sc-score[^>]*>\s*([0-9]{1,3})\s*%", seg, re.S)
        if m:
            assert int(m.group(1)) >= 50

    def test_scorecard_shows_overall_composite_like_dashboard(self):
        rf = _rf({
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.8, "status": "pass"},
                "C": {"score": 0.3, "status": "fail"},
                "overall": {"score": 0.55, "status": "warn", "scored_groups": 2},
            }},
            "accuracy_metrics": {"tcr": {"tcr": 55}},
            "tasks": [{"task_id": f"t{i}", "success": True, "completion_score": 0.55,
                       "accuracy_score": 0.5, "execution_time": 1.0} for i in range(6)],
        })
        html = generate_html_from_result_file(rf)
        sc = html[html.find('class="scorecard"'):html.find('class="scorecard"') + 900]
        assert ">Overall</div>" in sc
        # dashboard shows Math.round(overall.score * 100) + "%"  -> 55.0%
        assert ">55.0%</span>" in sc


class TestFullSuccessRateFallbackParity:
    """The report's Gate A "Full Success Rate" KPI reads the stored
    ``accuracy_metrics.tcr.success_rate``; when absent it must fall back to
    ``count(completion_score >= 1.0) / N x 100`` — the exact number the dashboard
    computes for its "Full" completion bucket. R2 gave tcr/accuracy this fallback
    but missed success_rate."""

    def test_report_full_success_rate_matches_dashboard_full_bucket(self):
        rf = _rf({"tasks": [
            {"task_id": f"t{i}", "success": True,
             "completion_score": 1.0 if i < 3 else 0.4,
             "accuracy_score": 0.6, "execution_time": 1.0}
            for i in range(8)
        ]})
        html = generate_html_from_result_file(rf)
        m = re.search(
            r'Full Success Rate</div><div class="kpi-val"[^>]*>([0-9.]+)%', html)
        assert m
        cs = [t.completion_score for t in rf.tasks]
        dash_full = sum(1 for c in cs if c >= 1.0) / len(cs) * 100
        assert float(m.group(1)) == pytest.approx(dash_full, abs=0.1)
        assert float(m.group(1)) == pytest.approx(37.5, abs=0.1)

    def test_stored_success_rate_still_wins(self):
        rf = _rf({
            "accuracy_metrics": {"tcr": {"tcr": 90, "success_rate": 88.0}},
            "tasks": [{"task_id": "a", "success": True, "completion_score": 0.1,
                       "accuracy_score": 0.1, "execution_time": 1.0}],
        })
        html = generate_html_from_result_file(rf)
        m = re.search(
            r'Full Success Rate</div><div class="kpi-val"[^>]*>([0-9.]+)%', html)
        assert m and float(m.group(1)) == pytest.approx(88.0)


class TestTokenBlockFallbackParity:
    """Gate D "Total Tokens" / "Avg Tokens/Task" read ``efficiency_metrics.tokens``;
    when that block is absent but tasks carry ``tokens_used``, both the report and
    the dashboard token KPIs now sum per-task (matching ResultFile.total_tokens /
    the CSV export)."""

    PARTIAL = {"tasks": [
        {"task_id": f"t{i}", "success": True, "completion_score": 0.9,
         "accuracy_score": 0.8, "execution_time": 1.0,
         "tokens_used": {"input": 100, "output": 50}}
        for i in range(8)
    ]}

    def test_report_total_tokens_matches_resultfile_property(self):
        rf = _rf(self.PARTIAL)
        assert rf.total_tokens == 8 * 150
        html = generate_html_from_result_file(rf)
        m = re.search(r'Total Tokens</div><div class="kpi-val">([0-9,]+)', html)
        assert m and int(m.group(1).replace(",", "")) == 8 * 150
        m2 = re.search(r'Avg Tokens/Task</div><div class="kpi-val">([0-9.]+)', html)
        assert m2 and float(m2.group(1)) == pytest.approx(150.0)

    def test_stored_token_block_still_wins(self):
        rf = _rf({
            "efficiency_metrics": {"tokens": {"total_tokens": 999,
                                              "avg_tokens_per_task": 111}},
            "tasks": [{"task_id": "a", "success": True, "completion_score": 1.0,
                       "accuracy_score": 1.0, "execution_time": 1.0,
                       "tokens_used": {"input": 1, "output": 1}}],
        })
        html = generate_html_from_result_file(rf)
        m = re.search(r'Total Tokens</div><div class="kpi-val">([0-9,]+)', html)
        assert m and int(m.group(1).replace(",", "")) == 999


class TestGateBToolUsageParity:
    """The report's Gate B "Tool Usage Analysis" read ``avg_f1`` / ``avg_efficiency``
    — keys the SDK never writes (it writes ``avg_f1_score`` / ``avg_efficiency_score``,
    on a 0-100 scale). So Tool Selection F1 / Efficiency / Success Rate / Total
    Calls never rendered, while the dashboard shows all of them from
    ``agentic.tool_efficiency`` / ``tool_selection_summary``."""

    def _run(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
        for i in range(5):
            t = create_taskresult(task_id=f"t{i}", question="q", response="r",
                                  ground_truth="r", task_type="tool_use",
                                  execution_time=1.0)
            t = t.__class__(**{**t.__dict__,
                "tool_calls": [{"tool_name": "search", "parameters": {}, "success": True},
                               {"tool_name": "calc", "parameters": {}, "success": i % 2 == 0}],
                "expected_tools": ["search", "calculator"]})
            m.record_task(t)
        d = m.output_dir
        m.save_to_file("run")
        return m, parse_file(Path(d) / "run.json")

    def test_tool_usage_kpis_render_and_match_stored_values(self):
        m, rf = self._run()
        _ag = rf.agentic if isinstance(rf.agentic, dict) else rf.agentic.__dict__
        te = _ag["tool_efficiency"]
        html = generate_html_from_result_file(rf)
        seg = html[html.find("Tool Usage Analysis"):html.find("Tool Usage Analysis") + 900]
        # every KPI the dashboard shows must now be in the report too
        assert "Total Tool Calls" in seg and f'>{te["total_calls"]}<' in seg
        assert "Tool Success Rate" in seg and f'{te["success_rate"]:.1f}%' in seg
        assert "Tool Selection F1" in seg and "0.500" in seg           # avg_f1_score 50 -> 0.5
        assert "Tool Efficiency" in seg and f'{te["avg_efficiency_score"]:.1f}%' in seg
        assert "Tool Failure Rate" in seg and f'{te["failure_rate"]:.1f}%' in seg

    def test_monitor_and_file_paths_agree(self):
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )
        m, rf = self._run()

        def kpis(html):
            seg = html[html.find("Tool Usage Analysis"):]
            return re.findall(r'kpi-lbl">([^<]+)</div><div class="kpi-val"[^>]*>([^<]+)<',
                              seg)[:6]

        assert kpis(generate_html_from_result_file(rf)) == \
               kpis(generate_comprehensive_html_report(m))


class TestGateDetailTableKeyParity:
    """Every per-Gate "Details" table in the report read stale key names
    (``reproducibility`` / ``consensus_rate`` / ``explainability_score`` …) while
    the SDK stores ``avg_reproducibility`` / ``avg_consensus`` /
    ``avg_explainability`` — the same keys the dashboard binds as
    ``gX.details.avg_*`` KPI cards. So the tables rendered empty on the report
    while the dashboard showed the numbers."""

    def _run(self):
        from agent_evaluator import (
            ExplainabilityConfig,
            GracefulDegradationConfig,
            IdempotencyConfig,
            ObservabilityConfig,
            PerformanceMonitor,
            ReproducibilityConfig,
            agent_eval,
        )
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())

        @agent_eval(m, task_type="qa",
                    explainability=ExplainabilityConfig(min_reasoning_length=5),
                    observability=ObservabilityConfig(),
                    reproducibility=ReproducibilityConfig(),
                    idempotency=IdempotencyConfig(),
                    graceful_degradation=GracefulDegradationConfig())
        def agent(question, ground_truth=""):
            return "The answer is 4 because two plus two equals four, step by step."

        for i in range(6):
            agent("q" + str(i), ground_truth="4")
        d = m.output_dir
        m.save_to_file("run")
        return parse_file(Path(d) / "run.json")

    def test_detail_tables_render_with_stored_values(self):
        rf = self._run()
        hg = rf.harness_groups or {}
        html = generate_html_from_result_file(rf)
        checks = [
            ("C", ["avg_reproducibility", "avg_degradation", "avg_idempotency"]),
            ("G", ["avg_explainability", "avg_observability_score"]),
        ]
        for g, keys in checks:
            det = (hg.get(g) or {}).get("details") or {}
            measured = [k for k in keys if isinstance(det.get(k), (int, float))]
            assert measured, f"Gate {g} should have measured detail metrics"
            assert f"Gate {g} Details" in html
            seg = html[html.find(f"Gate {g} Details"):
                       html.find(f"Gate {g} Details") + 1200]
            for k in measured:
                assert f"{det[k] * 100:.1f}%" in seg, \
                    f"Gate {g}: {k}={det[k]} missing from the detail table"

    def test_gate_a_and_b_detail_tables_also_fixed(self):
        # Gate A (instruction adherence / goal alignment …) and Gate B
        # (loop_detection_rate / avg_scope_score …) had the same stale-key bug.
        from agent_evaluator import (
            GoalAlignmentConfig,
            InstructionConfig,
            LoopDetectionConfig,
            PerformanceMonitor,
            agent_eval,
        )
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())

        @agent_eval(m, task_type="qa",
                    instructions=InstructionConfig(required_keywords=["answer"]),
                    goal_alignment=GoalAlignmentConfig(ignore_no_tool_tasks=False),
                    loop_detection=LoopDetectionConfig())
        def agent(question, ground_truth=""):
            return "The answer is 4 because two plus two equals four, step by step."

        for i in range(6):
            agent("q" + str(i), ground_truth="4")
        d = m.output_dir
        m.save_to_file("run")
        rf = parse_file(Path(d) / "run.json")
        hg = rf.harness_groups or {}
        html = generate_html_from_result_file(rf)

        ada = (hg.get("A") or {}).get("details", {}).get("avg_instruction_adherence")
        assert isinstance(ada, (int, float))
        assert "Gate A Details" in html
        seg_a = html[html.find("Gate A Details"):html.find("Gate A Details") + 800]
        assert f"{ada * 100:.1f}%" in seg_a

        ldr = (hg.get("B") or {}).get("details", {}).get("loop_detection_rate")
        assert isinstance(ldr, (int, float))
        assert "Gate B Details" in html
        seg_b = html[html.find("Gate B Details"):html.find("Gate B Details") + 800]
        assert f"{ldr * 100:.1f}%" in seg_b


class TestConversationSessionTableParity:
    """The report's "Multi-Turn Conversation Sessions" table read
    ``sess["overall_score"]`` / ``sess["context_retention"]`` at the top level,
    but ``loader._parse_conversation_sessions`` nests those under
    ``sess["metrics"]`` — the same place the dashboard reads
    (``s.metrics.overall_score``). So both columns rendered "—"."""

    def test_score_and_context_columns_populate_from_metrics(self):
        from agent_evaluator import PerformanceMonitor
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
        with m.conversation("s1") as conv:
            conv.add_turn("my name is Alice, book a flight to Paris",
                          "Sure Alice, when to Paris?")
            conv.add_turn("friday", "Booking Paris friday for you, Alice.")
            conv.add_turn("my name again?", "Alice.")
        d = m.output_dir
        m.save_to_file("run")
        rf = parse_file(Path(d) / "run.json")

        sess = rf.conversation_sessions[0]
        met = sess["metrics"]
        assert met["overall_score"] > 0 and met["context_retention"] > 0

        html = generate_html_from_result_file(rf)
        i = html.find("Multi-Turn Conversation Sessions")
        assert i >= 0
        seg = html[i:i + 900]
        assert f"{met['overall_score'] * 100:.1f}%" in seg
        assert f"{met['context_retention'] * 100:.1f}%" in seg
        assert seg.count("—") < 2   # not both columns dashed


class TestFeedbackSummaryParity:
    """The report had no implicit-feedback surface at all; the dashboard shows a
    Feedback panel (total / positive_rate / negative_rate). Add a compact block
    that renders the same three numbers."""

    def test_report_shows_feedback_summary_matching_stored(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
        for i in range(6):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="a", ground_truth="a",
                execution_time=1.0, task_type="qa"))
            m.record_implicit_feedback(f"t{i}", "thumbs_up" if i % 3 else "thumbs_down")
        d = m.output_dir
        m.save_to_file("run")
        rf = parse_file(Path(d) / "run.json")
        fb = rf.feedback_data
        assert fb["total"] == 6

        html = generate_html_from_result_file(rf)
        i = html.find("Implicit Feedback")
        assert i >= 0
        seg = html[i:i + 400]
        assert f">{fb['total']}<" in seg
        assert f"{fb['positive_rate']:.1f}%" in seg
        assert f"{fb['negative_rate']:.1f}%" in seg

    def test_no_feedback_no_section(self):
        rf = _rf({"accuracy_metrics": {"tcr": {"tcr": 80}},
                  "tasks": [{"task_id": "a", "success": True, "completion_score": 1.0,
                             "accuracy_score": 1.0, "execution_time": 1.0}]})
        assert "Implicit Feedback" not in generate_html_from_result_file(rf)


class TestGateDetailTableMatchesDashboardKpiSet:
    """The report's per-Gate "Details" table should list the *same set* of
    metrics the dashboard binds as ``gX.details.*`` KPI cards — not a superset
    with keys the dashboard doesn't surface (Gate E used to list CVSS /
    threat_free / per-tracker defense rates; Gate F listed tool_selection_f1)."""

    def test_gate_e_detail_table_is_the_dashboard_four(self):
        # a hand-built harness_groups with the Gate E detail keys populated
        rf = _rf({
            "extra_metrics": {"harness_groups": {"E": {"score": 0.9, "status": "pass",
                "details": {
                    "avg_compliance_score": 0.95,
                    "avg_threat_response": 0.80,
                    "privilege_escalation_rate": 0.0,
                    "chain_attack_rate": 0.10,
                    "avg_cvss_weighted_score": 0.2,
                    "threat_free_rate": 1.0,
                    "leakage_defense_rate": 1.0,
                    "threat_count": 0,
                }}}},
            "accuracy_metrics": {"tcr": {"tcr": 80}},
            "tasks": [{"task_id": f"t{i}", "success": True, "completion_score": 0.9,
                       "accuracy_score": 0.9, "execution_time": 1.0} for i in range(5)],
        })
        html = generate_html_from_result_file(rf)
        seg = html[html.find("Gate E Details"):html.find("Gate E Details") + 900]
        assert "95.0%" in seg   # avg_compliance_score
        assert "80.0%" in seg   # avg_threat_response
        assert "10.0%" in seg   # chain_attack_rate
        # keys the dashboard does NOT surface as Gate E KPIs must not be rows
        assert "Threat-Free Rate" not in seg
        assert "Leakage Defense Rate" not in seg
        assert "Threat Severity Score" not in seg

    def test_gate_f_detail_table_is_the_dashboard_four(self):
        rf = _rf({
            "extra_metrics": {"harness_groups": {"F": {"score": 0.7, "status": "pass",
                "details": {
                    "avg_consensus": 0.8, "avg_propagation": 0.75,
                    "avg_role_compliance": 0.9, "avg_conflict_resolution": 0.6,
                    "avg_tool_selection_f1": 0.5, "coordination_score": 0.7,
                }}}},
            "accuracy_metrics": {"tcr": {"tcr": 80}},
            "tasks": [{"task_id": f"t{i}", "success": True, "completion_score": 0.9,
                       "accuracy_score": 0.9, "execution_time": 1.0,
                       "agent_interactions": [{"from_agent": "a", "to_agent": "b",
                                               "interaction_type": "delegation",
                                               "success": True}]}
                      for i in range(4)],
        })
        html = generate_html_from_result_file(rf)
        seg = html[html.find("Gate F Details"):html.find("Gate F Details") + 900]
        assert "80.0%" in seg and "75.0%" in seg   # consensus / propagation
        assert "Tool Selection F1" not in seg      # not a dashboard Gate F KPI


class TestStreamingSnapshotParity:
    """The dashboard's live tab renders ``rf.streaming_data`` per-window
    (count / tcr / avg_latency / p95_latency / error_rate / avg_tokens) via
    ``/api/stream/snapshot``; the report had no streaming surface."""

    def test_report_renders_streaming_windows_matching_stored(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult
        m = PerformanceMonitor(output_dir=tempfile.mkdtemp())
        for i in range(4):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="a", ground_truth="a",
                execution_time=1.0, task_type="qa"))
        m._streaming_snapshot = {
            "1m": {"count": 10, "tcr": 85.0, "avg_latency": 1.2,
                   "p95_latency": 2.5, "error_rate": 5.0, "avg_tokens": 150},
            "5m": {"count": 40, "tcr": 82.0, "avg_latency": 1.3,
                   "p95_latency": 2.8, "error_rate": 7.5, "avg_tokens": 155},
            "1h": {"count": 0},
        }
        d = m.output_dir
        m.save_to_file("run")
        rf = parse_file(Path(d) / "run.json")
        html = generate_html_from_result_file(rf)
        i = html.find("Streaming Snapshot")
        assert i >= 0
        seg = html[i:i + 700]
        assert "85.0%" in seg and "1.200s" in seg and "2.500s" in seg   # 1m window
        assert "40" in seg and "82.0%" in seg                            # 5m window
        # zero-count window is skipped
        assert seg.count("<tr>") <= 3

    def test_no_streaming_no_section(self):
        rf = _rf({"accuracy_metrics": {"tcr": {"tcr": 80}},
                  "tasks": [{"task_id": "a", "success": True, "completion_score": 1.0,
                             "accuracy_score": 1.0, "execution_time": 1.0}]})
        assert "Streaming Snapshot" not in generate_html_from_result_file(rf)
