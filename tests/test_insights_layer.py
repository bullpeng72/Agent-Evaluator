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
