"""
tests/test_improve_p49.py
=========================
SPEC-041 P49 — `agent-eval improve {plan,start,verify}`: the closed loop that
turns insights.recommendations[].proposal into tracked experiments + change
stubs, then scores the prediction on the next run.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.cli.improve import (
    _cmd_plan,
    _cmd_start,
    _cmd_verify,
    _exp_note,
    _proposals,
    _stub_text,
)
from agent_evaluator.reporting.insights import build_insights


def _t(tid, comp, acc, ok, reason, ttype="qa"):
    return {"task_id": tid, "task_type": ttype, "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q?", "response": "r"}


def _result(gate_scores, tasks, *, prompt_text=None):
    hg = {k: {"score": s, "status": "warn" if s < 0.7 else "pass",
              "gate": "warn" if s < 0.7 else "pass", "details": {}}
          for k, s in gate_scores.items()}
    em = {"harness_groups": hg}
    if prompt_text is not None:
        em["lineage"] = {"prompt_text": prompt_text}
    return {"extra_metrics": em, "tasks": tasks}


def _run(a=0.6, c=0.62):
    tasks = [_t(f"p{i}", 1.0, 0.9, True, None) for i in range(10)]
    tasks += [_t(f"m{i}", 0.3, 0.2, False,
                 "only part of a multi-step answer completed") for i in range(4)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    return _result({"A": a, "C": c}, tasks,
                   prompt_text="Answer the question using the context.")


def _ns(**kw):
    base = {"gate": None, "baseline": None, "log": None, "out": None,
            "yes": False, "persist": False, "min_effect": 0.02}
    base.update(kw)
    return argparse.Namespace(**base)


def _write(p, obj):
    Pth = p
    Pth.write_text(json.dumps(obj), encoding="utf-8")
    return str(Pth)


# ---- pure helpers ----------------------------------------------------------

def test_proposals_extracted_and_ordered():
    ins = build_insights(_run(a=0.55, c=0.68))
    rows = _proposals(ins, None)
    assert rows, "expected at least one proposal"
    gates = [r["gate"] for r in rows]
    assert "A" in gates and "C" in gates
    # fail-status gates sort before warn-status ones
    statuses = [r["status"] for r in rows]
    assert statuses == sorted(statuses, key=lambda s: {"fail": 0, "warn": 1}.get(s, 9))
    a = next(r for r in rows if r["gate"] == "A")
    assert a["kind"] in ("prompt_edit", "config_change", "data_fix")
    assert a["evidence_task_ids"]


def test_gate_filter():
    ins = build_insights(_run())
    assert {r["gate"] for r in _proposals(ins, "C")} == {"C"}
    assert _proposals(ins, "Z") == []


def test_exp_note_and_stub_text():
    ins = build_insights(_run())
    row = _proposals(ins, "C")[0]
    note = _exp_note(row)
    assert note.startswith("[improve] Gate C") and len(note) <= 200
    stub = _stub_text(row, "exp-abc123")
    assert "exp-abc123" in stub and "## After (apply this)" in stub
    assert "improve verify" in stub


# ---- plan ----------------------------------------------------------------

def test_cmd_plan_smoke(tmp_path, capsys):
    rf = _write(tmp_path / "v.json", _run())
    rc = _cmd_plan(_ns(result_file=rf, log=str(tmp_path / "e.jsonl")))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Improvement plan" in out and "Gate A" in out


# ---- start -------------------------------------------------------------------

def test_start_dry_run_writes_nothing(tmp_path, capsys):
    rf = _write(tmp_path / "v.json", _run())
    log = tmp_path / "e.jsonl"
    rc = _cmd_start(_ns(result_file=rf, log=str(log), out=str(tmp_path / "imp"),
                        yes=False))
    assert rc == 0
    assert not log.exists()
    assert "Re-run with --yes" in capsys.readouterr().out


def test_start_registers_and_writes_stubs_then_dedupes(tmp_path, capsys):
    rf = _write(tmp_path / "v.json", _run())
    log = tmp_path / "e.jsonl"
    out = tmp_path / "imp"
    rc = _cmd_start(_ns(result_file=rf, log=str(log), out=str(out), yes=True))
    assert rc == 0
    exps = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    assert len(exps) >= 2
    assert all(e["status"] == "open" for e in exps)
    assert all(e["note"].startswith("[improve]") for e in exps)
    stubs = list(out.glob("*.md"))
    assert len(stubs) == len(exps)

    # second run: every proposal already has an open experiment -> all skipped
    capsys.readouterr()
    _cmd_start(_ns(result_file=rf, log=str(log), out=str(out), yes=True))
    o = capsys.readouterr().out
    assert "0 registered" in o
    exps2 = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    assert len(exps2) == len(exps)


# ---- verify ----------------------------------------------------------------

def test_verify_scores_and_persists(tmp_path, capsys):
    v_old = _write(tmp_path / "v_old.json", _run(a=0.6, c=0.62))
    log = tmp_path / "e.jsonl"
    _cmd_start(_ns(result_file=v_old, log=str(log), out=str(tmp_path / "imp"),
                   yes=True))
    capsys.readouterr()

    # a "new run" where Gate A/C recovered -> predicted +delta should confirm
    v_new = _write(tmp_path / "v_new.json", _run(a=0.9, c=0.9))
    rc = _cmd_verify(_ns(result_file=v_new, baseline=v_old, log=str(log),
                         persist=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "VERDICT" in out
    assert "Resolved" in out

    folded = {}
    for line in log.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            folded[r["experiment_id"]] = {**folded.get(r["experiment_id"], {}), **r}
    assert any(e.get("status") == "resolved" for e in folded.values())
    assert (tmp_path / "recommendation_outcomes.jsonl").is_file()


def test_verify_dry_run_does_not_resolve(tmp_path, capsys):
    v_old = _write(tmp_path / "v_old.json", _run())
    log = tmp_path / "e.jsonl"
    _cmd_start(_ns(result_file=v_old, log=str(log), out=str(tmp_path / "imp"),
                   yes=True))
    capsys.readouterr()
    v_new = _write(tmp_path / "v_new.json", _run(a=0.9, c=0.9))
    _cmd_verify(_ns(result_file=v_new, baseline=v_old, log=str(log), persist=False))
    assert "Dry run" in capsys.readouterr().out
    assert not (tmp_path / "recommendation_outcomes.jsonl").exists()
    rows = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    assert all(r["status"] == "open" for r in rows)


def test_verify_missing_files(tmp_path, capsys):
    assert _cmd_verify(_ns(result_file=str(tmp_path / "nope.json"),
                           baseline=str(tmp_path / "no2.json"),
                           log=str(tmp_path / "e.jsonl"))) == 1
