"""
tests/test_experiments.py
============================
SPEC-041 P27 — registered improvement hypotheses (`.aoo/experiments.jsonl`).

register → score (predicted vs actual movement of the target Gate/field vs a
baseline) → resolve, plus `insights.experiments`, the CLI wrapper, and the
report section.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import jsonschema

from agent_evaluator.cli.experiment import cmd_experiment
from agent_evaluator.rca.experiments import (
    _prediction_verdict,
    load_experiments,
    recalibrated_delta,
    register_experiment,
    resolve_experiment,
    score_experiments,
)
from agent_evaluator.reporting.insights import _experiments_section, build_insights


def _report(a_score, sub=None, gate="A", field="avg_subtask_completion"):
    details = {} if sub is None else {field: sub}
    return {
        "extra_metrics": {"harness_groups": {
            gate: {"score": a_score, "status": "pass", "gate": "pass", "details": details},
        }},
        "tasks": [],
    }


class TestRegistryRoundTrip:
    def test_register_then_load_open(self, tmp_path):
        log = tmp_path / "experiments.jsonl"
        row = register_experiment(
            log, target_gate="A", predicted_delta=0.08,
            target_field="avg_subtask_completion", note="add SubtaskConfig",
        )
        assert row["experiment_id"].startswith("exp-")
        exps = load_experiments(log)
        assert len(exps) == 1
        assert exps[0]["status"] == "open"
        assert exps[0]["predicted_delta"] == 0.08

    def test_resolve_folds_by_id_and_preserves_registration_fields(self, tmp_path):
        log = tmp_path / "experiments.jsonl"
        row = register_experiment(
            log, target_gate="A", predicted_delta=0.08, target_field="avg_x",
        )
        resolve_experiment(log, row["experiment_id"], actual_delta=0.05, verdict="confirmed")
        folded = load_experiments(log)
        assert len(folded) == 1
        assert folded[0]["status"] == "resolved"
        assert folded[0]["verdict"] == "confirmed"
        assert folded[0]["target_field"] == "avg_x"          # from the register row
        assert folded[0]["actual_delta"] == 0.05

    def test_status_filter(self, tmp_path):
        log = tmp_path / "e.jsonl"
        a = register_experiment(log, target_gate="A", predicted_delta=0.1)
        register_experiment(log, target_gate="B", predicted_delta=0.1)
        resolve_experiment(log, a["experiment_id"], actual_delta=0.1, verdict="confirmed")
        assert len(load_experiments(log, status="open")) == 1
        assert len(load_experiments(log, status="resolved")) == 1

    def test_corrupt_line_skipped(self, tmp_path):
        log = tmp_path / "e.jsonl"
        register_experiment(log, target_gate="A", predicted_delta=0.1)
        with open(log, "a") as f:
            f.write("{ not json\n")
        assert len(load_experiments(log)) == 1

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_experiments(tmp_path / "nope.jsonl") == []


class TestPredictionVerdict:
    def test_confirmed_when_full_magnitude_same_direction(self):
        assert _prediction_verdict(0.08, 0.09) == "confirmed"
        assert _prediction_verdict(0.08, 0.05) == "confirmed"  # >= 50%

    def test_partial_when_small_but_right_direction(self):
        assert _prediction_verdict(0.10, 0.02) == "partially_confirmed"

    def test_refuted_on_wrong_direction_or_noise(self):
        assert _prediction_verdict(0.08, -0.05) == "refuted"
        assert _prediction_verdict(0.08, 0.001) == "refuted"

    def test_inconclusive_without_measurement(self):
        assert _prediction_verdict(0.08, None) == "inconclusive"


class TestScoreExperiments:
    def test_field_delta_drives_verdict(self, tmp_path):
        log = tmp_path / "e.jsonl"
        register_experiment(
            log, target_gate="A", predicted_delta=0.08,
            target_field="avg_subtask_completion",
        )
        scored = score_experiments(
            load_experiments(log, status="open"),
            _report(0.70, 0.58), _report(0.60, 0.50),
        )
        assert scored[0]["verdict"] == "confirmed"
        assert abs(scored[0]["actual_delta"] - 0.08) < 1e-6

    def test_pending_without_baseline(self, tmp_path):
        log = tmp_path / "e.jsonl"
        register_experiment(log, target_gate="A", predicted_delta=0.08)
        scored = score_experiments(load_experiments(log, status="open"), _report(0.7), None)
        assert scored[0]["verdict"] == "pending"
        assert scored[0]["actual_delta"] is None


class TestRecalibratedDelta:
    def test_blends_when_two_or_more_confirmed(self, tmp_path):
        log = tmp_path / "e.jsonl"
        for actual in (0.08, 0.04):
            r = register_experiment(
                log, target_gate="A", predicted_delta=0.08, target_field="avg_x",
            )
            resolve_experiment(log, r["experiment_id"], actual_delta=actual, verdict="confirmed")
        val, n = recalibrated_delta(load_experiments(log), "A", "avg_x", 0.10)
        assert n == 2
        assert abs(val - (0.5 * 0.10 + 0.5 * 0.06)) < 1e-6

    def test_passthrough_with_fewer_than_two(self, tmp_path):
        log = tmp_path / "e.jsonl"
        r = register_experiment(log, target_gate="A", predicted_delta=0.08, target_field="avg_x")
        resolve_experiment(log, r["experiment_id"], actual_delta=0.08, verdict="confirmed")
        assert recalibrated_delta(load_experiments(log), "A", "avg_x", 0.10) == (0.1, 0)


class TestBuildInsightsWiring:
    def test_experiments_key_and_schema(self, tmp_path):
        log = tmp_path / "e.jsonl"
        register_experiment(
            log, target_gate="A", predicted_delta=0.08,
            target_field="avg_subtask_completion",
        )
        ins = build_insights(
            _report(0.70, 0.58), _report(0.60, 0.50), experiments_log_path=str(log),
        )
        assert ins["experiments"] and ins["experiments"][0]["verdict"] == "confirmed"
        assert "hypothesis" in ins["experiments"][0]
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_without_log(self):
        assert build_insights(_report(0.9), None)["experiments"] is None
        assert _experiments_section(_report(0.9), None, None) is None


class TestCli:
    def test_register_list_score_persist(self, tmp_path, capsys):
        log = tmp_path / "e.jsonl"
        b = tmp_path / "b.json"
        c = tmp_path / "c.json"
        b.write_text(json.dumps(_report(0.60, 0.20, gate="B", field="loop_detection_rate")))
        c.write_text(json.dumps(_report(0.70, 0.13, gate="B", field="loop_detection_rate")))

        rc = cmd_experiment(argparse.Namespace(
            experiment_command="register", gate="B", field="loop_detection_rate",
            predict_delta=-0.05, note="tighten", baseline=None, log=str(log)))
        assert rc == 0

        rc = cmd_experiment(argparse.Namespace(
            experiment_command="list", status="open", log=str(log)))
        assert rc == 0

        rc = cmd_experiment(argparse.Namespace(
            experiment_command="score", result_file=str(c), baseline=str(b),
            persist=True, min_effect=0.02, log=str(log)))
        assert rc == 0
        assert load_experiments(log)[0]["status"] == "resolved"

    def test_score_missing_files(self, tmp_path):
        rc = cmd_experiment(argparse.Namespace(
            experiment_command="score", result_file=str(tmp_path / "no.json"),
            baseline=str(tmp_path / "no2.json"), persist=False, min_effect=0.02,
            log=str(tmp_path / "e.jsonl")))
        assert rc == 1

    def test_no_subcommand_returns_1(self):
        assert cmd_experiment(argparse.Namespace(experiment_command=None)) == 1


class TestReportSection:
    def test_renders_when_present(self):
        from agent_evaluator.reporting.comprehensive_report import _build_experiments

        html = _build_experiments([
            {"hypothesis": "Gate A avg_x +0.080", "predicted": 0.08, "actual": 0.09,
             "verdict": "confirmed", "status": "resolved", "note": "n"},
        ])
        assert 'id="experiments"' in html and "confirmed" in html

    def test_empty_when_none(self):
        from agent_evaluator.reporting.comprehensive_report import _build_experiments

        assert _build_experiments(None) == ""
