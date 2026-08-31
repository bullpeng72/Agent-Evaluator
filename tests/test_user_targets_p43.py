"""
tests/test_user_targets_p43.py
==============================
SPEC-041 P43 — user-defined targets/SLOs (.aoo/targets.json) flow through
verdict / readiness / narrative / agent-eval gate.
"""
from __future__ import annotations

import json

from agent_evaluator.reporting.insights import build_insights
from agent_evaluator.utils.targets import (
    gate_target,
    is_user_defined,
    load_targets,
    save_targets,
)

# ---- utils.targets ------------------------------------------------------------

def test_load_save_roundtrip_and_coerce(tmp_path):
    p = tmp_path / "targets.json"
    save_targets({"gates": {"a": 0.85, "Z": 0.9, "E": 2.0}, "tcr_pct": 90,
                  "junk": "x"}, p)
    t = load_targets(p)
    assert t is not None
    assert t["gates"] == {"A": 0.85}          # 'Z' dropped, E=2.0 out of range
    assert t["tcr_pct"] == 90.0
    assert "junk" not in t


def test_save_deep_merges_gates(tmp_path):
    p = tmp_path / "t.json"
    save_targets({"gates": {"A": 0.8}}, p)
    save_targets({"gates": {"C": 0.75}, "tcr_pct": 88}, p)
    t = load_targets(p)
    assert t is not None
    assert t["gates"] == {"A": 0.8, "C": 0.75} and t["tcr_pct"] == 88.0


def test_gate_target_precedence():
    t = {"gates": {"A": 0.9}, "gate_default": 0.8}
    assert gate_target(t, "A") == 0.9          # explicit
    assert gate_target(t, "C") == 0.8          # gate_default
    assert gate_target(None, "A") == 0.7       # SDK default
    assert gate_target({}, "A", 0.7) == 0.7
    assert is_user_defined(t) and not is_user_defined(None) and not is_user_defined({})


def test_load_missing_or_bad(tmp_path):
    assert load_targets(tmp_path / "nope.json") is None
    (tmp_path / "bad.json").write_text("{not json")
    assert load_targets(tmp_path / "bad.json") is None


# ---- build_insights threading ----------------------------------------------

def _result(scores):
    hg = {}
    for k, s in scores.items():
        st = "fail" if s < 0.5 else "warn" if s < 0.7 else "pass"
        hg[k] = {"score": s, "status": st, "gate": st, "details": {}}
    tasks = [{"task_id": f"p{i}", "task_type": "qa", "completion_score": 0.9,
              "accuracy_score": 0.8, "success": True, "question": "q"}
             for i in range(8)]
    tasks += [{"task_id": f"f{i}", "task_type": "qa", "completion_score": 0.2,
               "accuracy_score": 0.2, "success": False, "question": "q",
               "partial_reason": "only part of a multi-step answer completed"}
              for i in range(4)]
    return {"extra_metrics": {"harness_groups": hg}, "tasks": tasks}


def test_builtin_when_no_targets():
    ins = build_insights(_result({"A": 0.75, "C": 0.75}))
    assert ins["verdict"]["targets_source"] == "builtin"
    assert ins["verdict"]["targets"] is None
    assert ins["verdict"]["level"] == "ready"


def test_user_target_flags_a_builtin_pass_gate():
    # A=0.75 clears the SDK line but not a user bar of 0.85
    ins = build_insights(_result({"A": 0.75, "C": 0.9}),
                         targets={"gates": {"A": 0.85}})
    v = ins["verdict"]
    assert v["targets_source"] == "user"
    assert v["below_user_target_gates"] == ["A"]
    assert v["level"] == "caution"
    assert "below your target" in v["headline"]
    # readiness measures against the user bar
    rd = ins["readiness"]
    assert rd["targets_source"] == "user"
    a_gap = next(g for g in rd["gaps"] if g["gate"] == "A")
    assert a_gap["target"] == 0.85
    assert abs(a_gap["gap"] - (0.85 - 0.75)) < 1e-6
    assert "your target" in rd["projected_ready_after"]["note"]


def test_narrative_uses_your_target_phrase():
    ins = build_insights(_result({"A": 0.72}), targets={"gate_default": 0.8})
    assert "below your target" in ins["narrative"]


def test_schema_still_valid_with_targets():
    import jsonschema

    schema = json.loads(
        (
            __import__("pathlib").Path(__file__).parents[1]
            / "agent_evaluator/schemas/insights.schema.json"
        ).read_text()
    )
    ins = build_insights(_result({"A": 0.6, "C": 0.55}),
                         targets={"gates": {"A": 0.9}, "gate_default": 0.8})
    jsonschema.validate(ins, schema)


# ---- CLI ------------------------------------------------------------------

def test_target_cli_set_show_clear(tmp_path, capsys):
    import argparse

    from agent_evaluator.cli.targets import cmd_target

    f = str(tmp_path / "targets.json")
    rc = cmd_target(argparse.Namespace(
        target_command="set", gate=["A=0.85", "E=0.95"], gate_default=None,
        tcr=90.0, accuracy=None, max_cost_per_task=0.03, note="slo", path=f,
    ))
    assert rc == 0
    loaded = load_targets(f)
    assert loaded is not None
    assert loaded["gates"] == {"A": 0.85, "E": 0.95}
    cmd_target(argparse.Namespace(target_command="show", as_json=True, path=f))
    assert '"A": 0.85' in capsys.readouterr().out
    cmd_target(argparse.Namespace(target_command="clear", path=f))
    assert load_targets(f) is None


def test_gate_cli_auto_loads_targets(tmp_path, monkeypatch):
    import argparse

    from agent_evaluator.cli.gate import cmd_gate

    res = tmp_path / "r.json"
    res.write_text(json.dumps({
        "accuracy_metrics": {"tcr": {"tcr": 0.71}},
        "extra_metrics": {"harness_groups": {
            "A": {"score": 0.64, "status": "warn", "gate": "warn", "details": {}}}},
        "tasks": [{"task_id": "t", "question": "q", "completion_score": 0.7,
                   "accuracy_score": 0.6, "success": True}],
    }))
    save_targets({"gates": {"A": 0.9}, "tcr_pct": 95}, tmp_path / ".aoo/targets.json")
    monkeypatch.chdir(tmp_path)
    ns = argparse.Namespace(result_file=str(res), tcr=None, accuracy=None,
                            p95_latency=None, hallucination=None, llm_judge=None,
                            max_cost_per_task=None, gate_thresholds=None,
                            min_gate_score=None, save_baseline=False, baseline=None,
                            baseline_version=None, fail_on_regression=None,
                            golden_set=None, digest=False, explain=False, notify=[])
    rc = cmd_gate(ns)
    assert rc == 1          # TCR 71% < 95% target and Gate A 0.64 < 0.9
