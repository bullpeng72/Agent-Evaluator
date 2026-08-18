"""
tests/test_spec035_branch_guard.py
======================================
SPEC-035: BranchGuardConfig — 보호 브랜치 git 변경 차단.

REQ-1/2/3: BranchGuardConfig · get_current_branch() · is_branch_protected() 단위 테스트.
REQ-4/5: LiveGuardrail 통합(생성자 시점 1회 캐싱, check_before_tool_call() 체크).
"""
from __future__ import annotations

import subprocess

from agent_evaluator.gates.branch_guard import (
    BranchGuardConfig,
    get_current_branch,
    is_branch_protected,
    matches_git_mutation,
)
from agent_evaluator.gates.live_guardrail import LiveGuardrail


class TestGetCurrentBranch:
    def test_returns_branch_name_in_real_repo(self):
        # 이 저장소 자체에서 실행 — git이 있고 브랜치가 있는 정상 케이스
        branch = get_current_branch()
        assert branch is not None
        assert isinstance(branch, str)

    def test_returns_none_in_non_git_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert get_current_branch() is None

    def test_returns_none_on_subprocess_failure(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise FileNotFoundError("git not installed")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert get_current_branch() is None


class TestIsBranchProtected:
    def test_none_branch_not_protected_fail_open(self):
        assert is_branch_protected(None, BranchGuardConfig()) is False

    def test_default_protected_branches(self):
        cfg = BranchGuardConfig()
        assert is_branch_protected("main", cfg) is True
        assert is_branch_protected("master", cfg) is True
        assert is_branch_protected("feature/x", cfg) is False

    def test_require_branch_prefix_mismatch_is_protected(self):
        cfg = BranchGuardConfig(require_branch_prefix="feature/")
        assert is_branch_protected("random-branch", cfg) is True
        assert is_branch_protected("feature/x", cfg) is False

    def test_custom_protected_branches(self):
        cfg = BranchGuardConfig(protected_branches=("release",))
        assert is_branch_protected("release", cfg) is True
        assert is_branch_protected("main", cfg) is False


class TestMatchesGitMutation:
    def test_git_commit_matches(self):
        cfg = BranchGuardConfig()
        assert matches_git_mutation('{"command": "git commit -m wip"}', cfg) is True

    def test_git_push_matches(self):
        cfg = BranchGuardConfig()
        assert matches_git_mutation('{"command": "git push origin HEAD"}', cfg) is True

    def test_non_mutation_command_does_not_match(self):
        cfg = BranchGuardConfig()
        assert matches_git_mutation('{"command": "pytest tests/"}', cfg) is False


class TestLiveGuardrailBranchGuardIntegration:
    def test_default_none_no_regression(self):
        guardrail = LiveGuardrail()  # branch_guard 미설정
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m wip"})
        assert verdict.block is False

    def test_current_branch_cached_once_at_construction(self):
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig())
        cached = guardrail._current_branch
        # 여러 번 호출해도 브랜치가 재조회되지 않고 동일 값 유지(순수 조회 계약)
        guardrail.check_before_tool_call("t1", "bash", {"command": "ls"})
        guardrail.check_before_tool_call("t2", "bash", {"command": "pwd"})
        assert guardrail._current_branch == cached

    def test_protected_branch_blocks_git_commit(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig())
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m wip"})
        assert verdict.block is True
        assert verdict.gate == "B"
        assert verdict.reason is not None
        assert "main" in verdict.reason

    def test_non_protected_branch_allows_git_commit(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "feature/x",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig())
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m wip"})
        assert verdict.block is False

    def test_non_git_command_not_blocked_on_protected_branch(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig())
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "pytest tests/"})
        assert verdict.block is False

    def test_out_of_scope_tool_not_blocked(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig(scoped_tool_names=("bash",)))
        verdict = guardrail.check_before_tool_call(
            "t1", "read", {"text": "instructions mention git commit somewhere"},
        )
        assert verdict.block is False

    def test_fail_on_violation_false_does_not_block(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig(fail_on_violation=False))
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git push origin HEAD"})
        assert verdict.block is False

    def test_require_branch_prefix_blocks_mismatched_branch(self, monkeypatch):
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "random-branch",
        )
        guardrail = LiveGuardrail(
            branch_guard=BranchGuardConfig(require_branch_prefix="feature/"),
        )
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m wip"})
        assert verdict.block is True

    def test_record_blocked_attempt_works_with_branch_guard_verdict(self, monkeypatch):
        """record_blocked_attempt()는 새 코드 변경 없이 이 새 차단 유형도 받아들인다."""
        monkeypatch.setattr(
            "agent_evaluator.gates.live_guardrail.get_current_branch", lambda: "main",
        )
        guardrail = LiveGuardrail(branch_guard=BranchGuardConfig())
        verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m wip"})
        assert verdict.block is True
        guardrail.record_blocked_attempt("t1", "bash", verdict)
        snap = guardrail.snapshot()
        assert len(snap["blocked_attempts"]) == 1
        assert snap["blocked_attempts"][0]["gate"] == "B"
