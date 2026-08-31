"""
tests/test_p28_metadata_slices_manifest.py
=============================================
SPEC-041 P28 — the last insight-delivery phase:
  * metadata_slices — per-slice TCR/Δ keyed on scalar `extra` metadata
  * sample_guidance — "how many more tasks tighten the TCR CI"
  * reproducibility_manifest — model/decoding params, eval-set ref, evaluator
    config hash, dependency versions
  * `agent-eval gate --max-cost-per-task` cost SLO gate
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.insights import (
    _metadata_slices_section,
    _one_to_one,
    _sample_guidance_section,
    build_insights,
)


def _task(i, ok, *, model, difficulty="easy", acc=None):
    return {
        "task_id": f"t{i}", "task_type": "qa",
        "success": ok, "completion_score": 1.0 if ok else 0.0,
        "accuracy_score": acc if acc is not None else (0.9 if ok else 0.2),
        "extra": {"model": model, "difficulty": difficulty},
    }


class TestMetadataSlices:
    def test_discovers_extra_key_and_splits(self):
        tasks = (
            [_task(i, True, model="gpt-a") for i in range(8)]
            + [_task(i + 8, i % 4 == 0, model="gpt-b") for i in range(8)]
        )
        ms = _metadata_slices_section(tasks, None)
        assert ms is not None
        model_dim = next(d for d in ms if d["dimension"] == "extra.model")
        by_val = {s["value"]: s for s in model_dim["slices"]}
        assert by_val["gpt-a"]["tcr_pct"] > by_val["gpt-b"]["tcr_pct"]
        assert by_val["gpt-a"]["n"] == 8

    def test_skips_key_that_mirrors_task_type(self):
        tasks = [
            {"task_id": f"x{i}", "task_type": "qa" if i < 4 else "rag",
             "success": True, "completion_score": 1.0, "accuracy_score": 0.9,
             "extra": {"kind": "qa" if i < 4 else "rag"}}
            for i in range(8)
        ]
        # extra.kind is a 1:1 relabel of task_type -> not surfaced
        ms = _metadata_slices_section(tasks, None)
        assert ms is None or all(d["dimension"] != "extra.kind" for d in ms)

    def test_none_for_too_few_tasks(self):
        assert _metadata_slices_section(
            [_task(0, True, model="a"), _task(1, True, model="b")], None
        ) is None

    def test_none_when_no_scalar_extra(self):
        tasks = [
            {"task_id": f"t{i}", "task_type": "qa", "success": True,
             "completion_score": 1.0, "accuracy_score": 0.9,
             "extra": {"trace": [1, 2, 3]}}
            for i in range(6)
        ]
        assert _metadata_slices_section(tasks, None) is None

    def test_baseline_delta_computed(self):
        cur = [_task(i, i % 2 == 0, model="gpt-a" if i < 5 else "gpt-b") for i in range(10)]
        base_tasks = [_task(i, True, model="gpt-a" if i < 5 else "gpt-b") for i in range(10)]
        ms = _metadata_slices_section(cur, {"tasks": base_tasks})
        assert ms is not None
        model_dim = next(d for d in ms if d["dimension"] == "extra.model")
        assert any("tcr_delta_pp" in s and s["tcr_delta_pp"] < 0 for s in model_dim["slices"])

    def test_one_to_one_both_directions(self):
        # bijection: 2 task_types, 2 values, paired -> True
        biject = [
            {"task_type": "qa", "extra": {"m": "a"}},
            {"task_type": "qa", "extra": {"m": "a"}},
            {"task_type": "rag", "extra": {"m": "b"}},
            {"task_type": "rag", "extra": {"m": "b"}},
        ]
        assert _one_to_one(biject, "m") is True
        # one task_type, two values -> not a bijection
        split = [
            {"task_type": "qa", "extra": {"m": "a"}},
            {"task_type": "qa", "extra": {"m": "b"}},
        ]
        assert _one_to_one(split, "m") is False


class TestSampleGuidance:
    def test_recommends_more_tasks_when_ci_wide(self):
        sg = _sample_guidance_section(
            {"n_tasks": 12, "tcr_ci_halfwidth": 0.09, "tcr_pct": 60.0}
        )
        assert sg is not None
        assert sg["additional_tasks"] > 0
        assert "tighten" in sg["message"]
        assert sg["recommended_n"] > 12

    def test_satisfied_when_ci_tight(self):
        sg = _sample_guidance_section(
            {"n_tasks": 500, "tcr_ci_halfwidth": 0.02, "tcr_pct": 60.0}
        )
        assert sg is not None
        assert sg["additional_tasks"] == 0

    def test_none_without_ci(self):
        assert _sample_guidance_section({"n_tasks": 0}) is None
        assert _sample_guidance_section({"n_tasks": 10}) is None


class TestBuildInsightsWiring:
    def _report(self, tasks, manifest=None):
        r = {
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.7, "status": "pass", "gate": "pass", "details": {}},
            }},
            "tasks": tasks,
        }
        if manifest is not None:
            r["extra_metrics"]["lineage"] = {"reproducibility_manifest": manifest}
        return r

    def test_all_three_keys_and_schema(self):
        tasks = (
            [_task(i, True, model="gpt-a") for i in range(8)]
            + [_task(i + 8, i % 3 == 0, model="gpt-b") for i in range(8)]
        )
        man = {"model_name": "claude-sonnet-5", "model_params": {"temperature": 0.0},
               "evaluator_config_hash": "abc123",
               "dependency_versions": {"agent_evaluator": "1.0"}}
        ins = build_insights(self._report(tasks, man))
        assert ins["metadata_slices"] is not None
        assert ins["sample_guidance"] is not None
        assert ins["reproducibility_manifest"]["model_name"] == "claude-sonnet-5"
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_nulls_when_absent(self):
        ins = build_insights(self._report([_task(i, True, model="a") for i in range(3)]))
        assert ins["metadata_slices"] is None
        assert ins["reproducibility_manifest"] is None


class TestReproducibilityManifest:
    def test_monitor_builds_manifest(self):
        from agent_evaluator import PerformanceMonitor, create_taskresult

        m = PerformanceMonitor(
            output_dir="/tmp", model_name="claude-sonnet-5",
            model_params={"temperature": 0.0, "top_p": 1.0, "seed": 7},
            dataset_ref="golden_v3#sha256:abcd",
        )
        for i in range(3):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="a", ground_truth="a",
                execution_time=1.0, task_type="qa",
            ))
        man = m._build_lineage()["reproducibility_manifest"]
        assert man["model_name"] == "claude-sonnet-5"
        assert man["model_params"]["seed"] == 7
        assert man["dataset_ref"].startswith("golden_v3")
        assert "agent_evaluator" in man["dependency_versions"]
        assert len(man["evaluator_config_hash"]) == 16

    def test_manifest_hash_is_stable(self):
        from agent_evaluator import PerformanceMonitor

        a = PerformanceMonitor(output_dir="/tmp", model_name="m")._build_lineage()[
            "reproducibility_manifest"
        ]
        b = PerformanceMonitor(output_dir="/tmp", model_name="m")._build_lineage()[
            "reproducibility_manifest"
        ]
        assert a["evaluator_config_hash"] == b["evaluator_config_hash"]


class TestReportSections:
    def test_render_and_empty(self):
        from agent_evaluator.reporting.comprehensive_report import (
            _build_metadata_slices,
            _build_reproducibility_manifest,
            _build_sample_guidance,
        )

        ms = [{"dimension": "extra.model", "slices": [
            {"value": "a", "n": 5, "tcr_pct": 80.0},
            {"value": "b", "n": 5, "tcr_pct": 40.0},
        ]}]
        assert 'id="metadata-slices"' in _build_metadata_slices(ms)
        assert _build_metadata_slices(None) == ""
        assert 'id="sample-guidance"' in _build_sample_guidance({"message": "x", "additional_tasks": 3})
        assert _build_sample_guidance(None) == ""
        assert "claude" in _build_reproducibility_manifest({"model_name": "claude-x"})
        assert _build_reproducibility_manifest(None) == ""


class TestCostSloGate:
    def _ns(self, res, **kw):
        base = dict(
            result_file=str(res), tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, max_cost_per_task=None,
            fail_on_regression=None, baseline=None, baseline_version=None,
            save_baseline=False, junit_xml=None, golden_set=None,
            fail_on_golden_regression=False, explain=False, min_gate_score=None,
            gate_weights=None, gate_thresholds=None, required_gates=None,
            fail_on_gate_warn=False, baseline_result=None,
            fail_on_case_regression=False, max_review_high=None, notify=None,
        )
        base.update(kw)
        return argparse.Namespace(**base)

    def test_pass_and_fail(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate

        res = tmp_path / "r.json"
        res.write_text(json.dumps({
            "efficiency_metrics": {"tokens": {"total_cost": 2.0}},
            "tasks": [{"task_id": f"t{i}"} for i in range(4)],  # $0.50 / task
            "extra_metrics": {"harness_groups": {}},
        }))
        assert cmd_gate(self._ns(res, max_cost_per_task=1.0)) == 0
        assert cmd_gate(self._ns(res, max_cost_per_task=0.25)) == 1
