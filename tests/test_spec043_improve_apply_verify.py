"""
tests/test_spec043_improve_apply_verify.py
==========================================
SPEC-043 REQ-7 — ``agent-eval improve apply-verify``: apply one proposal's diff
in an isolated git worktree, run the caller's eval command there, and score
predicted-vs-actual. Never merges or commits.
"""
from __future__ import annotations

import argparse
import json
import subprocess

import pytest

from agent_evaluator.cli.improve import _cmd_apply_verify, _locate_new_result, _select_proposal


# --------------------------------------------------------------------------- #
# unit helpers
# --------------------------------------------------------------------------- #
class TestSelectProposal:
    _rows = [
        {"gate": "A", "kind": "prompt_edit"},
        {"gate": "E", "kind": "config_change"},
    ]

    def test_match_by_gate(self):
        p = _select_proposal(self._rows, "A")
        assert p is not None and p["kind"] == "prompt_edit"

    def test_match_by_gate_colon_kind(self):
        p = _select_proposal(self._rows, "E:config_change")
        assert p is not None and p["gate"] == "E"

    def test_match_by_gate_underscore_kind(self):
        p = _select_proposal(self._rows, "e_config_change")
        assert p is not None and p["gate"] == "E"

    def test_no_match(self):
        assert _select_proposal(self._rows, "Z") is None


class TestLocateNewResult:
    def test_explicit_relative_hint(self, tmp_path):
        (tmp_path / "results").mkdir()
        f = tmp_path / "results" / "r.json"
        f.write_text("{}")
        assert _locate_new_result(tmp_path, "results/r.json", 0.0) == f

    def test_explicit_missing_hint_returns_none(self, tmp_path):
        assert _locate_new_result(tmp_path, "nope.json", 0.0) is None

    def test_newest_in_results_dir(self, tmp_path):
        import time

        (tmp_path / "results").mkdir()
        old = tmp_path / "results" / "old.json"
        old.write_text("{}")
        time.sleep(0.01)
        started = time.time()
        time.sleep(0.01)
        new = tmp_path / "results" / "new.json"
        new.write_text("{}")
        assert _locate_new_result(tmp_path, None, started) == new


# --------------------------------------------------------------------------- #
# full flow in a real git repo
# --------------------------------------------------------------------------- #
_EVAL_PY = """import json, pathlib
pathlib.Path("results").mkdir(exist_ok=True)
data = {
  "summary": {"tcr": 90.0, "total_tasks": 2},
  "extra_metrics": {"harness_groups": {"A": {"score": 0.88, "status": "pass",
    "threshold": 0.7}}},
  "tasks": [
    {"task_id": "t1", "question": "q1", "response": "a1", "success": True,
     "accuracy_score": 0.9, "completion_score": 1.0, "ground_truth": "a1"},
    {"task_id": "t2", "question": "q2", "response": "a2", "success": True,
     "accuracy_score": 0.9, "completion_score": 1.0, "ground_truth": "a2"}
  ]
}
pathlib.Path("results/new.json").write_text(json.dumps(data))
"""

_BASELINE = {
    "summary": {"tcr": 50.0, "total_tasks": 2},
    "extra_metrics": {
        "harness_groups": {"A": {"score": 0.55, "status": "fail", "threshold": 0.7}},
        "lineage": {"prompt_source_path": "prompt.txt",
                    "prompt_text": "You are a helpful assistant."},
    },
    "tasks": [
        {"task_id": "t1", "question": "q1", "response": "wrong", "ground_truth": "a1",
         "success": False, "accuracy_score": 0.2, "completion_score": 0.2,
         "task_type": "qa"},
        {"task_id": "t2", "question": "q2", "response": "wrong2", "ground_truth": "a2",
         "success": False, "accuracy_score": 0.3, "completion_score": 0.3,
         "task_type": "qa"},
    ],
}


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


@pytest.fixture
def gitrepo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "prompt.txt").write_text("You are a helpful assistant.\n")
    (tmp_path / "eval.py").write_text(_EVAL_PY)
    (tmp_path / "baseline.json").write_text(json.dumps(_BASELINE))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _ns(repo, **over):
    base = dict(
        improve_command="apply-verify",
        result_file=str(repo / "baseline.json"),
        proposal="A", eval_cmd="python eval.py",
        new_result="results/new.json", repo=str(repo), baseline=None,
        prompt_file=None, persist=False, min_effect=0.02, keep_worktree=False,
        log=str(repo / ".aoo" / "experiments.jsonl"),
    )
    base.update(over)
    return argparse.Namespace(**base)


class TestApplyVerifyFlow:
    def test_happy_path_scores_and_keeps_worktree(self, gitrepo, capsys):
        rc = _cmd_apply_verify(_ns(gitrepo, persist=True))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Registered experiment" in out
        assert "confirmed" in out
        assert "Nothing was merged or committed" in out
        # experiment resolved
        lines = [json.loads(x) for x in
                 (gitrepo / ".aoo" / "experiments.jsonl").read_text().splitlines()]
        assert any(e.get("status") == "resolved" for e in lines)
        # recommendation outcome appended next to the baseline
        assert (gitrepo / "recommendation_outcomes.jsonl").is_file()
        # original working tree untouched
        assert (gitrepo / "prompt.txt").read_text() == "You are a helpful assistant.\n"
        # a worktree was left behind
        wl = _git(gitrepo, "worktree", "list").stdout
        assert "ae-improve-" in wl

    def test_unknown_proposal_exits_1(self, gitrepo, capsys):
        rc = _cmd_apply_verify(_ns(gitrepo, proposal="ZZZ"))
        assert rc == 1
        assert "No proposal matches" in capsys.readouterr().out

    def test_not_a_git_repo_exits_1(self, tmp_path, capsys):
        (tmp_path / "baseline.json").write_text(json.dumps(_BASELINE))
        rc = _cmd_apply_verify(_ns(tmp_path))
        assert rc == 1
        assert "not a git repository" in capsys.readouterr().out

    def test_missing_result_file_exits_1(self, gitrepo):
        rc = _cmd_apply_verify(_ns(gitrepo, result_file=str(gitrepo / "nope.json")))
        assert rc == 1

    def test_no_persist_leaves_experiment_open(self, gitrepo, capsys):
        rc = _cmd_apply_verify(_ns(gitrepo, persist=False))
        assert rc == 0
        assert "left open" in capsys.readouterr().out
        lines = [json.loads(x) for x in
                 (gitrepo / ".aoo" / "experiments.jsonl").read_text().splitlines()]
        assert all(e.get("status") != "resolved" for e in lines)

    def test_eval_cmd_that_writes_nothing_exits_1(self, gitrepo, capsys):
        rc = _cmd_apply_verify(_ns(gitrepo, eval_cmd="true", new_result=None))
        assert rc == 1
        assert "Could not find a result JSON" in capsys.readouterr().out
