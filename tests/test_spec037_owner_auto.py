"""
tests/test_spec037_owner_auto.py
====================================
SPEC-037: TeamConcurrencyConfig.owner="auto" — git config user.name 자동 주입.

발견 경위: SPEC-036이 owner 필드로 "자기 자신의 클레임" 오탐을 고칠 수 있게
했지만, owner를 빼먹으면 다시 같은 함정(SPEC-036 Context가 기록한 실제
버그)에 빠진다. "auto" 센티널은 agent_version="auto"(SPEC-027)와 동일한
패턴으로 git config user.name을 1회 조회해 이 함정 자체를 제거한다.

REQ-1: resolve_owner("auto")는 git config user.name을 조회해 반환한다.
REQ-2: resolve_owner("auto")는 조회 실패 시 예외 없이 None을 반환한다
       (git 미설치·비-git 환경·user.name 미설정 등 어떤 이유로든).
REQ-3: resolve_owner(None)/resolve_owner("명시적 이름")은 그대로 반환한다
       ("auto"만 특수 처리하는 순수 변환).
REQ-4: LiveGuardrail(team_concurrency=TeamConcurrencyConfig(owner="auto"))는
       생성자 시점에 1회만 조회해 캐싱한다 — SPEC-036의 owner 필터 로직과
       동일하게 동작하되, 값의 출처만 "auto" 센티널로 자동화된다.
REQ-5: 원본 TeamConcurrencyConfig 객체는 변경되지 않는다(owner="auto" 그대로
       보존) — LiveGuardrail 내부에만 해석된 값을 캐싱한다.
"""
from __future__ import annotations

from unittest.mock import patch

from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.gates.team_concurrency import (
    TeamConcurrencyConfig,
    append_claim,
    resolve_owner,
)


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


class TestResolveOwnerAutoSentinel:
    def test_auto_resolves_via_git_config(self):
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ) as mock_run:
            result = resolve_owner("auto")
        assert result == "Sungwoo Kim"
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["git", "config", "user.name"]

    def test_auto_falls_back_to_none_on_nonzero_exit(self):
        """git config user.name이 미설정이면 returncode != 0."""
        with patch("subprocess.run", return_value=_FakeCompletedProcess("", 1)):
            assert resolve_owner("auto") is None

    def test_auto_falls_back_to_none_on_empty_stdout(self):
        with patch("subprocess.run", return_value=_FakeCompletedProcess("\n", 0)):
            assert resolve_owner("auto") is None

    def test_auto_falls_back_to_none_on_exception(self):
        """git 미설치·비-git 환경 등 어떤 예외든 전파하지 않고 None."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            assert resolve_owner("auto") is None

    def test_auto_falls_back_to_none_on_timeout(self):
        import subprocess as _subprocess

        with patch("subprocess.run", side_effect=_subprocess.TimeoutExpired("git", 2)):
            assert resolve_owner("auto") is None


class TestResolveOwnerPassthrough:
    def test_none_returned_unchanged(self):
        assert resolve_owner(None) is None

    def test_explicit_name_returned_unchanged(self):
        assert resolve_owner("수아") == "수아"

    def test_explicit_name_does_not_call_subprocess(self):
        with patch("subprocess.run") as mock_run:
            resolve_owner("수아")
        mock_run.assert_not_called()


class TestLiveGuardrailOwnerAutoIntegration:
    def test_own_claim_excluded_when_auto_resolves(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="Sungwoo Kim", scope=["configs.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ):
            guardrail = LiveGuardrail(
                team_concurrency=TeamConcurrencyConfig(
                    claims_path=str(claims_path), owner="auto",
                ),
            )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "configs.py"})
        assert verdict.block is False

    def test_other_developer_claim_still_blocks_when_auto_resolves(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="태호", scope=["evaluators.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ):
            guardrail = LiveGuardrail(
                team_concurrency=TeamConcurrencyConfig(
                    claims_path=str(claims_path), owner="auto",
                ),
            )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "evaluators.py"})
        assert verdict.block is True

    def test_auto_resolution_failure_preserves_legacy_block_behavior(self, tmp_path):
        """git config 조회가 실패하면 owner는 None으로 떨어지고, SPEC-036 이전의
        기존 동작(자기 클레임도 차단)이 그대로 보존돼야 한다 — 새 기능이 조용히
        실패해도 "차단 안 해야 할 걸 차단"하는 방향으로만 안전하게 무너진다."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="Sungwoo Kim", scope=["configs.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            guardrail = LiveGuardrail(
                team_concurrency=TeamConcurrencyConfig(
                    claims_path=str(claims_path), owner="auto",
                ),
            )
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "configs.py"})
        assert verdict.block is True

    def test_original_config_object_not_mutated(self, tmp_path):
        claims_path = tmp_path / "claims.jsonl"
        config = TeamConcurrencyConfig(claims_path=str(claims_path), owner="auto")
        with patch(
            "subprocess.run",
            return_value=_FakeCompletedProcess("Sungwoo Kim\n", 0),
        ):
            LiveGuardrail(team_concurrency=config)
        assert config.owner == "auto"

    def test_owner_none_default_unaffected_by_auto_logic(self, tmp_path):
        """owner 미지정(기본값 None)은 "auto" 경로를 전혀 타지 않는다 —
        subprocess가 호출되지 않아야 한다."""
        claims_path = tmp_path / "claims.jsonl"
        append_claim(
            claims_path, claim_id="c1", developer="Sungwoo Kim", scope=["configs.py"],
            started_at="2026-07-08T09:00:00+09:00", status="active",
        )
        with patch("subprocess.run") as mock_run:
            guardrail = LiveGuardrail(
                team_concurrency=TeamConcurrencyConfig(claims_path=str(claims_path)),
            )
        mock_run.assert_not_called()
        verdict = guardrail.check_before_tool_call("t1", "edit", {"file": "configs.py"})
        assert verdict.block is True
