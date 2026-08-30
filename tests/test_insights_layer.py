"""
tests/test_insights_layer.py
================================
SPEC-041 P9 — machine-readable insight layer (``agent_evaluator.reporting.insights``).

The deploy verdict / confidence / failure clusters / component shortfalls /
prescriptive recommendations used to live only in the HTML report and CLI text.
``build_insights()`` re-emits that interpretation as a JSON-serializable object so
the result file, dashboard and CI can consume L5/L6 (Docs/09_OUTPUTS.md).
"""
from __future__ import annotations

import json

import pytest

from agent_evaluator.reporting.insights import INSIGHTS_SCHEMA_VERSION, build_insights


def _task(tid: str, *, ok: bool, ttype: str = "qa", reason: str = "") -> dict:
    return {
        "task_id": tid,
        "task_type": ttype,
        "success": ok,
        "completion_score": 1.0 if ok else 0.2,
        "accuracy_score": 0.95 if ok else 0.3,
        "partial_reason": reason,
        "question": f"question for {tid}",
        "response": "ok" if ok else "wrong",
    }


def _report(harness_groups: dict, tasks: list[dict] | None = None) -> dict:
    return {
        "extra_metrics": {"harness_groups": harness_groups},
        "tasks": tasks or [],
    }


class TestSchema:
    def test_is_json_serializable_and_versioned(self):
        rpt = _report(
            {"A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}}},
            [_task(f"t{i}", ok=i % 2 == 0) for i in range(10)],
        )
        ins = build_insights(rpt)
        json.dumps(ins)  # must not raise
        assert ins["schema_version"] == INSIGHTS_SCHEMA_VERSION
        for key in (
            "verdict", "metric_confidence", "gate_findings",
            "failure_clusters", "recommendations", "detection_mode",
        ):
            assert key in ins

    def test_never_raises_on_empty_report(self):
        ins = build_insights({})
        assert ins["verdict"]["level"] == "unknown"
        assert ins["gate_findings"] == []
        assert ins["failure_clusters"] == []


class TestVerdict:
    def test_failing_gate_is_not_ready(self):
        rpt = _report({
            "A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}},
            "C": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
        }, [_task(f"t{i}", ok=i % 3 != 0) for i in range(12)])
        v = build_insights(rpt)["verdict"]
        assert v["level"] == "not_ready"
        assert "A" in v["failing_gates"]
        assert v["confidence"] in ("high", "medium", "low")

    def test_all_pass_is_ready(self):
        rpt = _report({
            "A": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}},
            "B": {"score": 0.92, "status": "pass", "gate": "pass", "details": {}},
        }, [_task(f"t{i}", ok=True) for i in range(20)])
        assert build_insights(rpt)["verdict"]["level"] == "ready"

    def test_next_actions_point_at_weakest_component(self):
        rpt = _report({
            "A": {
                "score": 0.45, "status": "fail", "gate": "fail",
                "details": {"tcr_pct": 45.0, "avg_subtask_completion": 0.3},
            },
        }, [_task(f"t{i}", ok=i % 2 == 0) for i in range(10)])
        actions = build_insights(rpt)["verdict"]["next_actions"]
        assert actions and actions[0]["gate"] == "A"
        assert actions[0]["field"] is not None


class TestFailureClusters:
    def test_clusters_by_reason_and_type(self):
        tasks = (
            [_task(f"to{i}", ok=False, ttype="rag", reason="retrieval returned no context")
             for i in range(4)]
            + [_task(f"tg{i}", ok=False, ttype="qa", reason="answer not grounded in context")
               for i in range(3)]
            + [_task(f"ok{i}", ok=True) for i in range(13)]
        )
        rpt = _report(
            {"A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}}},
            tasks,
        )
        clusters = build_insights(rpt)["failure_clusters"]
        assert len(clusters) >= 2
        top = clusters[0]
        assert top["count"] == 4
        assert top["task_type"] == "rag"
        assert top["impact_pct"] == pytest.approx(20.0, abs=0.1)
        assert top["example_task_ids"]


class TestFailureLineage:
    def test_regressed_and_fixed_vs_baseline(self):
        base = _report(
            {"A": {"score": 0.8, "status": "pass", "gate": "pass", "details": {}}},
            [_task("shared_pass", ok=True), _task("was_failing", ok=False),
             _task("stable", ok=True)],
        )
        cur = _report(
            {"A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {"tcr_pct": 50.0}}},
            [_task("shared_pass", ok=False), _task("was_failing", ok=True),
             _task("stable", ok=True)],
        )
        lin = build_insights(cur, base)["failure_lineage"]
        assert lin["regressed"] == ["shared_pass"]
        assert lin["fixed"] == ["was_failing"]

    def test_none_without_baseline(self):
        rpt = _report(
            {"A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}}},
            [_task("t1", ok=False)],
        )
        assert build_insights(rpt)["failure_lineage"] is None


class TestRecommendations:
    def test_fail_gate_gets_recommendation_with_experiment(self):
        rpt = _report({
            "A": {
                "score": 0.4, "status": "fail", "gate": "fail",
                "details": {"tcr_pct": 40.0, "avg_subtask_completion": 0.25},
            },
        }, [_task(f"t{i}", ok=i % 3 == 0) for i in range(12)])
        recs = build_insights(rpt)["recommendations"]
        assert recs and recs[0]["gate"] == "A"
        assert recs[0]["status"] == "fail"
        # subtask_completion has a config hint -> snippet + experiment present
        assert recs[0]["experiment"] is not None
        assert recs[0]["experiment"]["command"].startswith("agent-eval abtest")

    def test_pass_only_report_has_no_recommendations(self):
        rpt = _report({
            "A": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}},
        }, [_task(f"t{i}", ok=True) for i in range(10)])
        assert build_insights(rpt)["recommendations"] == []


class TestLatencyBudget:
    def test_aggregates_span_attribution_and_modal_bottleneck(self):
        def _t(tid, model_ms, tool_ms):
            d = _task(tid, ok=False)
            d["extra"] = {"latency_attribution": {
                "model_ms": model_ms, "tool_ms": tool_ms, "network_ms": 10.0,
                "unattributed_ms": 0.0, "model_ratio": model_ms / (model_ms + tool_ms + 10),
                "tool_ratio": tool_ms / (model_ms + tool_ms + 10),
                "bottleneck": "model" if model_ms >= tool_ms else "tool",
            }}
            return d

        rpt = _report(
            {"D": {"score": 0.5, "status": "warn", "gate": "warn", "details": {}}},
            [_t("a", 1400, 300), _t("b", 1200, 400), _t("c", 200, 900)],
        )
        lb = build_insights(rpt)["latency_budget"]
        assert lb["n_tasks"] == 3
        assert lb["bottleneck"] == "model"          # 2 of 3
        assert lb["bottleneck_share"] == pytest.approx(2 / 3, abs=0.01)
        assert lb["model_ms"] == pytest.approx((1400 + 1200 + 200) / 3, abs=0.1)

    def test_none_when_no_attribution_data(self):
        rpt = _report(
            {"D": {"score": 0.5, "status": "warn", "gate": "warn", "details": {}}},
            [_task("t1", ok=False)],
        )
        assert build_insights(rpt)["latency_budget"] is None


class TestRagLocalization:
    _CTX = (
        "The 2023 annual report states total revenue was 4.2 billion USD across all "
        "regions and net profit was 800 million USD for the fiscal year."
    )

    def test_retrieval_miss_when_answer_not_in_context(self):
        from agent_evaluator.reporting.insights import classify_rag_failure
        res = classify_rag_failure(
            response="The headquarters moved to Berlin in 2019 according to the filing.",
            context="Weather patterns in the Pacific shift with the El Nino cycle every few years.",
            ground_truth="The company headquarters is located in Berlin, Germany since 2019.",
            accuracy=0.1,
        )
        assert res["klass"] == "retrieval_miss"

    def test_grounding_miss_when_context_ignored(self):
        from agent_evaluator.reporting.insights import classify_rag_failure
        res = classify_rag_failure(
            response="I believe the total was around fifty thousand dollars for everything.",
            context=self._CTX,
            ground_truth="Total revenue in 2023 was 4.2 billion USD across all regions.",
            accuracy=0.2,
        )
        assert res["klass"] == "grounding_miss"
        assert res["unsupported_claims"]

    def test_generation_error_when_grounded_but_wrong(self):
        from agent_evaluator.reporting.insights import classify_rag_failure
        res = classify_rag_failure(
            response=(
                "Per the 2023 annual report total revenue across all regions "
                "was 4.2 billion USD."
            ),
            context=self._CTX,
            ground_truth="Total revenue in 2023 was 4.2 billion USD across all regions.",
            accuracy=0.45,
        )
        assert res["klass"] == "generation_error"

    def test_none_when_no_context(self):
        from agent_evaluator.reporting.insights import classify_rag_failure
        assert classify_rag_failure(
            response="x", context="", ground_truth="y", accuracy=0.1,
        ) is None

    def test_aggregate_reports_dominant_and_remediation(self):
        def _rt(tid, resp, acc, ok):
            return {
                "task_id": tid, "response": resp, "context": self._CTX,
                "ground_truth": "Revenue was 4.2 billion USD.",
                "accuracy_score": acc, "success": ok,
                "completion_score": 1.0 if ok else 0.2, "task_type": "rag",
            }

        rpt = _report(
            {"C": {"score": 0.5, "status": "warn", "gate": "warn", "details": {}}},
            [
                _rt("a", "around fifty thousand dollars i think total maybe", 0.2, False),
                _rt("b", "maybe about a hundred thousand dollars overall that year", 0.2, False),
                _rt("c", "Total revenue was 4.2 billion USD across all regions.", 0.95, True),
            ],
        )
        loc = build_insights(rpt)["rag_localization"]
        assert loc["n_rag_tasks"] == 3
        assert loc["by_class"]["ok"] == 1
        assert loc["dominant_failure"] == "grounding_miss"
        assert "grounding_miss" in loc["remediation_by_class"]

    def test_none_without_rag_tasks(self):
        rpt = _report(
            {"A": {"score": 0.4, "status": "fail", "gate": "fail", "details": {"tcr_pct": 40.0}}},
            [_task("t1", ok=False)],
        )
        assert build_insights(rpt)["rag_localization"] is None


class TestSliceAnalysis:
    def test_per_type_rows_with_ci(self):
        rpt = _report(
            {"A": {"score": 0.7, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"q{i}", ok=True, ttype="qa") for i in range(12)]
            + [_task(f"r{i}", ok=i % 4 == 0, ttype="rag") for i in range(12)],
        )
        sl = build_insights(rpt)["slice_analysis"]
        by = {r["task_type"]: r for r in sl}
        assert by["qa"]["tcr_pct"] == 100.0
        assert by["rag"]["tcr_pct"] < 100.0
        assert len(by["rag"]["tcr_ci_pct"]) == 2

    def test_baseline_delta_flags_the_regressed_slice(self):
        base = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"q{i}", ok=True, ttype="qa") for i in range(16)]
            + [_task(f"r{i}", ok=True, ttype="rag") for i in range(16)],
        )
        cur = _report(
            {"A": {"score": 0.6, "status": "fail", "gate": "fail", "details": {"tcr_pct": 60.0}}},
            [_task(f"q{i}", ok=True, ttype="qa") for i in range(16)]
            + [_task(f"r{i}", ok=i < 4, ttype="rag") for i in range(16)],
        )
        sl = {r["task_type"]: r for r in build_insights(cur, base)["slice_analysis"]}
        assert sl["qa"]["tcr_delta_pp"] == 0.0
        assert sl["qa"]["significant"] is False
        assert sl["rag"]["tcr_delta_pp"] < 0
        assert sl["rag"]["significant"] is True


class TestEvalSetQuality:
    def test_histogram_duplicates_and_unbalanced_warning(self):
        tasks = (
            [_task(f"q{i}", ok=True, ttype="qa") for i in range(30)]
            + [_task("r0", ok=True, ttype="rag")]
        )
        for t in (tasks[0], tasks[1], tasks[2]):
            t["question"] = "Summarize the quarterly earnings call transcript in full"
        rpt = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}}, tasks,
        )
        q = build_insights(rpt)["eval_set_quality"]
        assert q["task_type_histogram"] == {"qa": 30, "rag": 1}
        assert any(c["count"] == 3 for c in q["near_duplicate_clusters"])
        assert any("unbalanced" in w for w in q["coverage_warnings"])

    def test_gate_f_scored_without_multiagent_tasks_warns(self):
        rpt = _report(
            {"F": {"score": 0.7, "status": "warn", "gate": "warn", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(25)],
        )
        q = build_insights(rpt)["eval_set_quality"]
        assert any("Gate F" in w and "agent_interactions" in w for w in q["coverage_warnings"])

    def test_suspicious_ground_truth_needs_baseline(self):
        base = _report(
            {"A": {"score": 0.6, "status": "fail", "gate": "fail", "details": {}}},
            [{**_task("bad", ok=False), "accuracy_score": 0.10, "ground_truth": "x"}]
            + [_task(f"t{i}", ok=True) for i in range(20)],
        )
        cur = _report(
            {"A": {"score": 0.6, "status": "fail", "gate": "fail", "details": {"tcr_pct": 60.0}}},
            [{**_task("bad", ok=False), "accuracy_score": 0.12, "ground_truth": "x"}]
            + [_task(f"t{i}", ok=True) for i in range(20)],
        )
        q = build_insights(cur, base)["eval_set_quality"]
        ids = [s["task_id"] for s in q["suspicious_ground_truth"]]
        assert "bad" in ids

    def test_none_without_tasks(self):
        assert build_insights({})["eval_set_quality"] is None


class TestEvaluatorTrust:
    def _judge_task(self, tid, judge_overall, acc):
        return {
            "task_id": tid, "accuracy_score": acc,
            "llm_judge": {"skipped": False, "scores": {"overall": judge_overall}},
        }

    def test_none_without_any_judge_data(self):
        rpt = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(10)],
        )
        assert build_insights(rpt)["evaluator_trust"] is None

    def test_judge_heuristic_disagreement_lowers_trust_and_confidence(self):
        tasks = [
            self._judge_task(f"t{i}", 9.0 if i % 2 == 0 else 2.0, 0.2 if i % 2 == 0 else 0.9)
            for i in range(12)
        ]
        rpt = _report(
            {"A": {"score": 0.55, "status": "fail", "gate": "fail",
                   "details": {"tcr_pct": 55.0, "avg_subtask_completion": 0.4}}},
            tasks,
        )
        ins = build_insights(rpt)
        et = ins["evaluator_trust"]
        assert et["trust_level"] == "low"
        assert et["judge_vs_heuristic"]["agreement_rate"] == 0.0
        assert et["judge_vs_heuristic"]["disagreements"]
        assert ins["verdict"]["confidence"] == "low"
        assert any("evaluator" in r.lower() for r in ins["verdict"]["confidence_reasons"])

    def test_agreeing_judge_keeps_trust_high(self):
        tasks = [self._judge_task(f"t{i}", 8.5, 0.85) for i in range(20)]
        rpt = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}}, tasks,
        )
        et = build_insights(rpt)["evaluator_trust"]
        assert et["trust_level"] == "high"
        assert et["judge_vs_heuristic"]["agreement_rate"] == 1.0

    def test_stashed_calibration_is_surfaced(self):
        tasks = [self._judge_task(f"t{i}", 8.0, 0.8) for i in range(15)]
        rpt = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}}, tasks,
        )
        rpt["extra_metrics"]["judge_calibration"] = {
            "dimensions": {"overall": {"n": 20, "mean_absolute_error": 2.1,
                                       "cohen_kappa_quadratic": 0.2}},
        }
        et = build_insights(rpt)["evaluator_trust"]
        assert et["judge_calibration"] is not None
        assert et["trust_level"] == "low"          # kappa 0.2 < 0.4


class TestReviewQueue:
    def _judge_task(self, tid, judge_overall, acc, ok=True, **kw):
        d = {
            "task_id": tid, "task_type": "qa", "success": ok,
            "question": f"q {tid}", "response": f"r {tid}", "ground_truth": "gt",
            "accuracy_score": acc, "completion_score": 1.0 if ok else 0.2,
            "llm_judge": {"skipped": False, "scores": {"overall": judge_overall}},
        }
        d.update(kw)
        return d

    def test_disagreement_and_borderline_populate_queue(self):
        tasks = (
            [self._judge_task(f"d{i}", 9.0, 0.2, ok=False) for i in range(4)]
            + [self._judge_task(f"b{i}", 7.0, 0.65) for i in range(3)]
            + [self._judge_task(f"ok{i}", 8.5, 0.9) for i in range(10)]
        )
        rpt = _report(
            {"A": {"score": 0.6, "status": "fail", "gate": "fail", "details": {"tcr_pct": 60.0}}},
            tasks,
        )
        rq = build_insights(rpt)["review_queue"]
        by_id = {it["task_id"]: it for it in rq["items"]}
        assert by_id["d0"]["priority"] == "high"
        assert "disagree" in by_id["d0"]["reasons"][0]
        assert by_id["b0"]["priority"] == "medium"
        assert rq["by_priority"]["high"] == 4

    def test_regressed_failures_are_high_priority(self):
        base = _report(
            {"A": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [{**_task("shared", ok=True), "task_type": "qa"}]
            + [_task(f"t{i}", ok=True) for i in range(20)],
        )
        cur = _report(
            {"A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {"tcr_pct": 50.0}}},
            [{**_task("shared", ok=False), "task_type": "qa"}]
            + [_task(f"t{i}", ok=True) for i in range(20)],
        )
        rq = build_insights(cur, base)["review_queue"]
        it = next(i for i in rq["items"] if i["task_id"] == "shared")
        assert it["priority"] == "high"
        assert "baseline" in it["reasons"][0]

    def test_none_when_nothing_to_review(self):
        rpt = _report(
            {"A": {"score": 0.95, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(20)],
        )
        assert build_insights(rpt)["review_queue"] is None


class TestCostEconomics:
    def _ct(self, tid, ok, tokens=(800, 400), attempts=1):
        return {
            "task_id": tid, "task_type": "qa", "success": ok,
            "accuracy_score": 0.9 if ok else 0.2, "completion_score": 1.0 if ok else 0.0,
            "attempts": attempts,
            "tokens_used": {"input": tokens[0], "output": tokens[1],
                            "total": sum(tokens)},
        }

    def test_cost_per_success_and_waste_and_projection(self):
        tasks = [self._ct(f"t{i}", i % 3 != 0, attempts=2 if i % 4 == 0 else 1)
                 for i in range(12)]
        rpt = _report(
            {"D": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}}, tasks,
        )
        rpt["pricing"] = {"input": 0.003, "output": 0.015}
        ce = build_insights(rpt)["cost_economics"]
        assert ce["cost_source"] == "per_task_tokens"
        assert ce["n_successful"] == 8
        # per task: 0.8*0.003 + 0.4*0.015 = 0.0084
        assert ce["cost_per_task_usd"] == pytest.approx(0.0084, abs=1e-4)
        assert ce["cost_per_successful_task_usd"] > ce["cost_per_task_usd"]
        assert ce["wasted_cost_pct"] == pytest.approx(33.3, abs=0.5)   # 4 of 12
        assert ce["retry_cost_pct"] > 0
        assert ce["projection"]["calls"] == 100000
        assert ce["projection"]["total_usd"] == pytest.approx(840.0, abs=1.0)

    def test_uniform_split_fallback_from_aggregate(self):
        tasks = [
            {"task_id": f"t{i}", "task_type": "qa", "success": i % 2 == 0,
             "accuracy_score": 0.9 if i % 2 == 0 else 0.2, "completion_score": 1.0}
            for i in range(10)
        ]
        rpt = _report(
            {"D": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}}, tasks,
        )
        rpt["efficiency_metrics"] = {"tokens": {"total_cost": 1.0}}
        ce = build_insights(rpt)["cost_economics"]
        assert ce["cost_source"] == "aggregate_uniform_split"
        assert ce["total_cost_usd"] == 1.0
        assert ce["wasted_cost_pct"] == pytest.approx(50.0, abs=0.1)

    def test_none_without_any_cost_data(self):
        rpt = _report(
            {"D": {"score": 0.9, "status": "pass", "gate": "pass", "details": {}}},
            [_task(f"t{i}", ok=True) for i in range(10)],
        )
        assert build_insights(rpt)["cost_economics"] is None


class TestSaveToFileEmbedsInsights:
    def test_monitor_save_writes_extra_metrics_insights(self, tmp_path):
        from agent_evaluator import PerformanceMonitor, create_taskresult

        m = PerformanceMonitor(output_dir=str(tmp_path))
        for i in range(12):
            ok = i % 3 != 0
            m.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}",
                response="Seoul" if ok else "wrong",
                ground_truth="Seoul", execution_time=0.5, task_type="qa",
            ))
        path = m.save_to_file("eval")
        data = json.loads(open(path).read())
        ins = data["extra_metrics"]["insights"]
        assert ins["schema_version"] == INSIGHTS_SCHEMA_VERSION
        assert ins["metric_confidence"]["n_tasks"] == 12
        assert "verdict" in ins
