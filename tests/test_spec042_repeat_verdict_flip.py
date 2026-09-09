"""
tests/test_spec042_repeat_verdict_flip.py
==========================================
SPEC-042 REQ-4 — whole-eval verdict stability
(``agent_evaluator.repeat`` + ``insights.nondeterminism_repeat``).
"""
from __future__ import annotations

from agent_evaluator.repeat import run_repeated, summarize_repeated
from agent_evaluator.reporting.insights import build_insights


def _run(gate_a=0.9, tcr=90.0, task_pass=(True, True)):
    return {
        "summary": {"tcr": tcr, "total_tasks": len(task_pass)},
        "extra_metrics": {"harness_groups": {"A": {"score": gate_a}}},
        "tasks": [
            {
                "task_id": f"t{i}",
                "success": ok,
                "accuracy_score": 0.9 if ok else 0.1,
                "completion_score": 1.0 if ok else 0.0,
            }
            for i, ok in enumerate(task_pass)
        ],
    }


class TestSummarizeRepeated:
    def test_fewer_than_two_runs_is_none(self):
        assert summarize_repeated([]) is None
        assert summarize_repeated([_run()]) is None

    def test_identical_passing_runs_are_deterministic(self):
        s = summarize_repeated([_run(), _run(), _run()])
        assert s is not None
        assert s["runs"] == 3
        assert s["flip_rate"] == 0.0
        assert s["gate_pass_count"] == 3
        assert s["deterministic"] is True
        assert s["n_unstable_tasks"] == 0

    def test_gate_verdict_flip_is_measured(self):
        s = summarize_repeated([_run(gate_a=0.9), _run(gate_a=0.9), _run(gate_a=0.3)])
        assert s is not None
        assert s["gate_verdicts"] == ["pass", "pass", "fail"]
        assert s["majority_verdict"] == "pass"
        assert s["flip_rate"] == 0.3333
        assert s["deterministic"] is False

    def test_unstable_task_is_flagged(self):
        s = summarize_repeated([
            _run(task_pass=(True, True)),
            _run(task_pass=(True, False)),
            _run(task_pass=(True, False)),
        ])
        assert s is not None
        ids = {u["task_id"]: u for u in s["unstable_tasks"]}
        assert "t1" in ids and ids["t1"]["pass_count"] == 1 and ids["t1"]["runs"] == 3
        assert "t0" not in ids  # t0 passed in every run
        assert s["deterministic"] is False

    def test_tcr_stddev(self):
        s = summarize_repeated([_run(tcr=80.0), _run(tcr=90.0), _run(tcr=100.0)])
        assert s is not None
        assert s["tcr_mean"] == 90.0
        assert s["tcr_stddev"] == 10.0

    def test_unknown_when_no_gate_measured(self):
        r = {"summary": {"tcr": 90.0}, "tasks": []}
        s = summarize_repeated([r, r])
        assert s is not None
        assert s["gate_verdicts"] == ["unknown", "unknown"]


class TestRunRepeated:
    def test_k_le_1_returns_none_without_calling(self):
        calls = []
        assert run_repeated(lambda: calls.append(1) or _run(), k=1) is None
        assert calls == []

    def test_calls_eval_fn_k_times(self):
        calls = []

        def fn():
            calls.append(1)
            return _run()

        s = run_repeated(fn, k=4)
        assert len(calls) == 4
        assert s is not None
        assert s["runs"] == 4


class TestInsightsWiring:
    def test_summary_dict_is_passed_through(self):
        summary = summarize_repeated([_run(gate_a=0.9), _run(gate_a=0.3)])
        cur = _run()
        cur["extra_metrics"]["repeat_runs"] = summary
        ins = build_insights(cur)
        assert ins["nondeterminism_repeat"]["runs"] == 2
        assert ins["nondeterminism_repeat"]["majority_verdict"] == "fail"  # tie -> conservative

    def test_raw_list_is_summarised(self):
        cur = _run()
        cur["extra_metrics"]["repeat_runs"] = [_run(), _run(), _run()]
        ins = build_insights(cur)
        nr = ins["nondeterminism_repeat"]
        assert nr["runs"] == 3 and nr["deterministic"] is True

    def test_absent_repeat_runs_is_none(self):
        ins = build_insights(_run())
        assert ins["nondeterminism_repeat"] is None
