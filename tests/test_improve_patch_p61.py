"""
tests/test_improve_patch_p61.py
===============================
SPEC-041 P61 — `agent-eval improve patch`: turn recommendations[].proposal
into a unified diff (prompt file for prompt_edit, @agent_eval decorator for
config_change). Never applies.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator.cli.improve import (
    _cmd_patch,
    _find_agent_eval_decorators,
    _patch_config_change,
    _patch_prompt_edit,
)


def _t(tid, comp, acc, ok, reason=None):
    return {"task_id": tid, "task_type": "qa", "completion_score": comp,
            "accuracy_score": acc, "success": ok, "partial_reason": reason,
            "question": "q", "response": "r", "ground_truth": "x"}


def _result(prompt="Answer the question using the context.", prompt_src=None):
    tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(10)]
    tasks += [_t(f"g{i}", 0.3, 0.2, False,
                 "answer not grounded in the retrieved context") for i in range(4)]
    tasks += [_t(f"to{i}", 0.0, 0.0, False, "error: TimeoutError") for i in range(3)]
    lineage = {"prompt_text": prompt}
    if prompt_src:
        lineage["prompt_source_path"] = prompt_src
    return {"extra_metrics": {"harness_groups": {
        "A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {}},
        "C": {"score": 0.55, "status": "warn", "gate": "warn", "details": {}}},
        "lineage": lineage}, "tasks": tasks}


_AGENT_PY = (
    "from agent_evaluator import agent_eval, PerformanceMonitor\n"
    "monitor = PerformanceMonitor(output_dir='results/')\n\n\n"
    "@agent_eval(monitor, task_type='qa')\n"
    "def my_agent(question: str, ground_truth: str = '') -> str:\n"
    "    return 'answer'\n"
)


# ---- AST scan ------------------------------------------------------------------

def test_find_agent_eval_decorators(tmp_path):
    (tmp_path / "agent.py").write_text(_AGENT_PY)
    (tmp_path / "not_it.py").write_text("def f():\n    return 1\n")
    hits = _find_agent_eval_decorators(tmp_path)
    assert len(hits) == 1
    py, src, seg, lineno, fname = hits[0]
    assert fname == "my_agent" and seg.startswith("agent_eval(") and "task_type" in seg


def test_scan_skips_junk_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text(_AGENT_PY)
    assert _find_agent_eval_decorators(tmp_path) == []


# ---- prompt_edit -------------------------------------------------------------

def test_patch_prompt_edit_replaces_anchor(tmp_path):
    pf = tmp_path / "prompt.txt"
    pf.write_text("You are a support agent.\nAnswer helpfully and in detail.\n")
    row = {"gate": "A", "before": "Answer helpfully and in detail.",
           "after": "Answer helpfully and in detail. Only use the retrieved context."}
    diff, msg = _patch_prompt_edit(row, tmp_path, str(pf), {})
    assert msg == "" and diff
    assert "-Answer helpfully and in detail." in diff
    assert "+Answer helpfully and in detail. Only use the retrieved context." in diff


def test_patch_prompt_edit_appends_when_no_anchor(tmp_path):
    pf = tmp_path / "prompt.txt"
    pf.write_text("You are a support agent.\n")
    row = {"gate": "A", "before": "(no grounding instruction)",
           "after": "Only state facts from the context."}
    diff, msg = _patch_prompt_edit(row, tmp_path, str(pf), {})
    assert msg == "" and "+Only state facts from the context." in diff


def test_patch_prompt_edit_no_source():
    diff, msg = _patch_prompt_edit({"after": "X"}, None, None, {})
    assert diff == "" and "no prompt source" in msg


def test_patch_prompt_edit_uses_lineage_path(tmp_path):
    pf = tmp_path / "sys_prompt.md"
    pf.write_text("Be concise.\n")
    diff, msg = _patch_prompt_edit(
        {"before": "Be concise.", "after": "Be very concise."},
        tmp_path, None, {"prompt_source_path": "sys_prompt.md"})
    assert msg == "" and "+Be very concise." in diff


# ---- config_change ---------------------------------------------------------

def test_patch_config_change_rewrites_decorator(tmp_path):
    (tmp_path / "agent.py").write_text(_AGENT_PY)
    row = {"gate": "C", "after": "fault_tolerance=FaultToleranceConfig(max_retries=2)"}
    diff, msg = _patch_config_change(row, tmp_path)
    assert "decorator on `my_agent`" in msg
    assert "-@agent_eval(monitor, task_type='qa')" in diff
    assert "FaultToleranceConfig(max_retries=2)" in diff
    assert "\n+)\n" in diff          # the rewritten call closes on its own line


def test_patch_config_change_no_decorator(tmp_path):
    (tmp_path / "x.py").write_text("def f():\n    return 1\n")
    diff, msg = _patch_config_change({"gate": "C", "after": "retry=RetryConfig()"},
                                     tmp_path)
    assert diff == "" and "no @agent_eval" in msg


# ---- CLI -------------------------------------------------------------------

def test_cmd_patch_end_to_end(tmp_path, capsys):
    (tmp_path / "agent.py").write_text(_AGENT_PY)
    pf = tmp_path / "prompt.txt"
    pf.write_text("Answer the question using the context.\n")
    rf = tmp_path / "v3.json"
    rf.write_text(json.dumps(_result(prompt_src="prompt.txt")))
    rc = _cmd_patch(argparse.Namespace(
        result_file=str(rf), baseline=None, gate=None, repo=str(tmp_path),
        prompt_file=str(pf), out=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "diff(s) generated" in out
    assert "nothing was written to your sources" in out
    assert "--- a/" in out            # at least one unified diff


def test_cmd_patch_writes_files(tmp_path, capsys):
    (tmp_path / "agent.py").write_text(_AGENT_PY)
    rf = tmp_path / "v3.json"
    rf.write_text(json.dumps(_result()))
    outdir = tmp_path / "patches"
    rc = _cmd_patch(argparse.Namespace(
        result_file=str(rf), baseline=None, gate="C", repo=str(tmp_path),
        prompt_file=None, out=str(outdir)))
    assert rc == 0
    assert list(outdir.glob("*.patch"))
