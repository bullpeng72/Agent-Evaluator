"""
tests/test_spec043_spec_coverage.py
====================================
SPEC-043 REQ-1 — requirement ↔ golden-case coverage
(``insights.spec_coverage`` + ``agent-eval gate --require-spec-coverage``).
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator import create_taskresult
from agent_evaluator.cli.gate import cmd_gate
from agent_evaluator.reporting.insights import build_insights


def _task(tid, covers=None):
    t = {
        "task_id": tid, "success": True, "accuracy_score": 0.9,
        "completion_score": 1.0, "question": "q", "response": "r",
        "ground_truth": "r", "task_type": "qa",
    }
    if covers is not None:
        t["extra"] = {"covers": covers}
    return t


def _result(tasks, gate_a=0.9):
    return {
        "summary": {"tcr": 100.0, "total_tasks": len(tasks)},
        "extra_metrics": {"harness_groups": {"A": {"score": gate_a, "status": "pass"}}},
        "tasks": tasks,
    }


def _ns(**kw):
    base = dict(
        result_file="", tcr=None, accuracy=None, p95_latency=None,
        hallucination=None, llm_judge=None, fail_on_regression=None,
        baseline=None, baseline_version=None, save_baseline=False, junit_xml=None,
        golden_set=None, fail_on_golden_regression=False, explain=False,
        min_gate_score=None, gate_weights=None, gate_thresholds=None,
        required_gates=None, fail_on_gate_warn=False,
        baseline_result=None, fail_on_case_regression=False,
        max_review_high=None, notify=None, hold_on_undecided=False,
        requirements=None, require_spec_coverage=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


class TestSpecCoverageSection:
    def test_none_when_no_covers_and_no_requirements(self):
        ins = build_insights(_result([_task("t1")]))
        assert ins["spec_coverage"] is None

    def test_covers_only_mode(self):
        ins = build_insights(_result([
            _task("t1", covers=["REQ-001"]),
            _task("t2", covers=["REQ-001", "REQ-002"]),
        ]))
        sc = ins["spec_coverage"]
        assert sc["source"] == "covers_only"
        assert set(sc["requirements"]) == {"REQ-001", "REQ-002"}
        assert sc["uncovered"] == []          # can't know what's missing
        assert set(sc["by_requirement"]["REQ-001"]) == {"t1", "t2"}
        assert sc["by_requirement"]["REQ-002"] == ["t2"]

    def test_requirements_list_computes_uncovered(self):
        ins = build_insights(
            _result([_task("t1", covers=["REQ-001"])]),
            requirements=["REQ-001", "REQ-002", "REQ-003"],
        )
        sc = ins["spec_coverage"]
        assert sc["source"] == "requirements_list"
        assert sc["covered"] == ["REQ-001"]
        assert sc["uncovered"] == ["REQ-002", "REQ-003"]
        assert sc["n_uncovered"] == 2

    def test_full_coverage_no_uncovered(self):
        ins = build_insights(
            _result([_task("t1", covers=["A", "B"])]),
            requirements=["A", "B"],
        )
        assert ins["spec_coverage"]["n_uncovered"] == 0

    def test_not_a_gate_score(self):
        with_c = build_insights(
            _result([_task("t1", covers=["A"])]), requirements=["A", "B"],
        )
        without = build_insights(_result([_task("t1")]))
        assert with_c["verdict"]["level"] == without["verdict"]["level"]

    def test_present_in_partial_mode_covers_only(self):
        ins = build_insights(_result([_task("t1", covers=["A"])]), partial=True)
        assert ins["spec_coverage"]["requirements"] == ["A"]


class TestCreateTaskresultCoversKwarg:
    def test_covers_lands_in_extra(self):
        tr = create_taskresult(task_id="t1", question="q", response="r",
                               covers=["REQ-1", "REQ-2"])
        assert (tr.extra or {})["covers"] == ["REQ-1", "REQ-2"]

    def test_blank_covers_filtered(self):
        tr = create_taskresult(task_id="t1", question="q", response="r",
                               covers=["  ", "", "REQ-1"])
        assert (tr.extra or {})["covers"] == ["REQ-1"]

    def test_none_leaves_extra_untouched(self):
        tr = create_taskresult(task_id="t1", question="q", response="r")
        assert "covers" not in (tr.extra or {})


class TestRequireSpecCoverageGate:
    def _files(self, tmp_path, tasks, req_lines):
        r = tmp_path / "run.json"
        r.write_text(json.dumps(_result(tasks)))
        req = tmp_path / "requirements.txt"
        req.write_text("\n".join(req_lines))
        return str(r), str(req)

    def test_exit_4_on_uncovered_requirement(self, tmp_path, capsys):
        r, req = self._files(
            tmp_path, [_task("t1", covers=["REQ-001"])],
            ["# SupportTriage requirements", "REQ-001: 카테고리 분류", "REQ-002: 우선순위"],
        )
        rc = cmd_gate(_ns(result_file=r, requirements=req, require_spec_coverage=True))
        assert rc == 4
        assert "REQ-002" in capsys.readouterr().err

    def test_pass_when_all_covered(self, tmp_path):
        r, req = self._files(
            tmp_path, [_task("t1", covers=["REQ-001", "REQ-002"])],
            ["REQ-001: a", "REQ-002: b"],
        )
        assert cmd_gate(_ns(result_file=r, requirements=req,
                            require_spec_coverage=True)) == 0

    def test_warns_and_skips_without_requirements_file(self, tmp_path, capsys):
        r = tmp_path / "run.json"
        r.write_text(json.dumps(_result([_task("t1", covers=["REQ-001"])])))
        rc = cmd_gate(_ns(result_file=str(r), require_spec_coverage=True))
        assert rc == 0
        assert "require-spec-coverage" in capsys.readouterr().err.lower()

    def test_flag_off_by_default(self, tmp_path):
        r, req = self._files(
            tmp_path, [_task("t1", covers=["REQ-001"])], ["REQ-001: a", "REQ-002: b"],
        )
        assert cmd_gate(_ns(result_file=r, requirements=req)) == 0
