"""
tests/test_cli_autopilot.py
=============================
Harness Autopilot M0 — `agent-eval autopilot` CLI
(install/doctor/new-task/add-member/dashboard 배선).

autopilot_state의 함수들을 감싸는 얇은 레이어이므로, 여기서는
① argparse.Namespace → 함수 호출 배선, ② CLI 특유의 종료 코드·경고 출력만
확인한다(새 판정 로직 없음).
"""
from __future__ import annotations

import argparse

import pytest

from agent_evaluator.cli.autopilot import (
    _cmd_autopilot_add_member,
    _cmd_autopilot_approvals_cancel,
    _cmd_autopilot_approvals_decide,
    _cmd_autopilot_approvals_list,
    _cmd_autopilot_approvals_open,
    _cmd_autopilot_approvals_update,
    _cmd_autopilot_dashboard,
    _cmd_autopilot_decisions,
    _cmd_autopilot_doctor,
    _cmd_autopilot_install,
    _cmd_autopilot_list_members,
    _cmd_autopilot_list_tasks,
    _cmd_autopilot_new_task,
    _cmd_autopilot_phase_check,
    _cmd_autopilot_phase_policy_set,
    _cmd_autopilot_phase_policy_show,
    _cmd_autopilot_phase_transition,
    _cmd_autopilot_remove_member,
    _cmd_autopilot_set_task_status,
    _cmd_autopilot_show_task,
    _cmd_autopilot_skills_detect,
    _cmd_autopilot_skills_scaffold,
    _cmd_autopilot_update_member,
    _cmd_autopilot_update_task,
    cmd_autopilot,
)
from agent_evaluator.gates.autopilot_state import (
    add_team_member,
    create_task,
    decide_approval,
    load_all_tasks,
    load_approvals,
    load_phase_policy,
    load_task,
    load_team,
    open_approval,
    save_task,
    set_phase_policy,
    set_task_status,
)
from agent_evaluator.gates.team_concurrency import load_active_claims
from agent_evaluator.rca.decision_ledger import load_decisions, record_gate_decision


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestInstall:
    def test_install_creates_tasks_dir_and_team_file(self, tmp_path):
        code = _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        assert code == 0
        assert (tmp_path / ".aoo" / "tasks").is_dir()
        assert (tmp_path / ".aoo" / "team.json").is_file()

    def test_install_does_not_overwrite_existing_team_file(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        team_path.parent.mkdir(parents=True)
        team_path.write_text(
            '{"members": [{"id": "x", "name": "X", "roles": []}]}\n', encoding="utf-8"
        )

        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        assert load_team(team_path)[0]["id"] == "x"

    def test_install_aoo_targets_opencode_skill_dir(self, tmp_path):
        _cmd_autopilot_install(_ns(platform="aoo", root=str(tmp_path)))
        # 스킬 소스가 없을 수도 있으니(패키징 환경에 따라) 디렉토리 자체는 안 만들어질 수 있음 —
        # install이 실패하지 않는지(exit 0)만 별도로 확인한다.
        code = _cmd_autopilot_install(_ns(platform="aoo", root=str(tmp_path)))
        assert code == 0


class TestDoctor:
    def test_doctor_fails_before_install(self, tmp_path):
        code = _cmd_autopilot_doctor(_ns(root=str(tmp_path)))
        assert code == 1

    def test_doctor_passes_after_install(self, tmp_path):
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        code = _cmd_autopilot_doctor(_ns(root=str(tmp_path)))
        assert code == 0

    def test_doctor_reports_task_count(self, tmp_path, capsys):
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        _cmd_autopilot_new_task(_ns(
            title="반품정책", platform="ac", priority="high", task_id="ST-014",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_doctor(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "ST-014" in out
        assert "1 task(s)" in out

    def test_doctor_warns_on_unsynced_member(self, tmp_path, capsys):
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jh", name="지훈", roles=["보안"]
        )
        _cmd_autopilot_doctor(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "unsynced" in out
        assert "지훈" in out

    def test_doctor_warns_on_stale_phase(self, tmp_path, capsys):
        """docs/AUTOPILOT_IMPROVEMENTS.md §3, LIMITS L4."""
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        tasks_dir = tmp_path / ".aoo" / "tasks"
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        task["phase_history"][-1]["entered_at"] = "2020-01-01T00:00:00+00:00"
        save_task(tasks_dir, task)

        capsys.readouterr()
        _cmd_autopilot_doctor(_ns(root=str(tmp_path), stale_days=7.0))
        out = capsys.readouterr().out
        assert "ST-001" in out
        assert "has been in phase 0" in out

    def test_doctor_stale_days_zero_disables_check(self, tmp_path, capsys):
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        tasks_dir = tmp_path / ".aoo" / "tasks"
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        task["phase_history"][-1]["entered_at"] = "2020-01-01T00:00:00+00:00"
        save_task(tasks_dir, task)

        capsys.readouterr()
        _cmd_autopilot_doctor(_ns(root=str(tmp_path), stale_days=0))
        out = capsys.readouterr().out
        assert "has been in phase" not in out

    def test_doctor_without_stale_days_arg_still_works(self, tmp_path):
        """하위호환 — 기존 Namespace 호출(stale_days 없음)이 안 깨짐."""
        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        assert _cmd_autopilot_doctor(_ns(root=str(tmp_path))) == 0


class TestNewTask:
    def test_new_task_creates_task_at_phase_0(self, tmp_path):
        code = _cmd_autopilot_new_task(_ns(
            title="반품정책 자동화", platform="ac", priority="high", task_id=None,
            analysis=None, design=None, root=str(tmp_path),
        ))
        assert code == 0
        tasks = load_all_tasks(tmp_path / ".aoo" / "tasks")
        assert len(tasks) == 1
        assert tasks[0]["current_phase"] == 0
        assert tasks[0]["title"] == "반품정책 자동화"

    def test_new_task_writes_problem_scaffold(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-099",
            analysis=None, design=None, root=str(tmp_path),
        ))
        assert (tmp_path / "docs" / "PROBLEM_ST-099.md").is_file()

    def test_new_task_warns_when_owner_role_mismatch(self, tmp_path, capsys):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="sa", name="수아", roles=["개발"])
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="수아", design=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert "not registered" not in out  # 수아는 등록돼 있음
        assert "not with role" in out  # 그러나 '분석' 역할은 아님

    def test_new_task_warns_when_owner_unsynced(self, tmp_path, capsys):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="정민", design=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert "not yet GitHub-synced" in out

    def test_new_task_rejects_duplicate_id(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t1", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_new_task(_ns(
            title="t2", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_new_task_accepts_all_six_role_owners(self, tmp_path):
        """docs/AUTOPILOT_IMPROVEMENTS.md §2 — owner 필드가 6역할 중
        analysis/design 2개뿐이던 공백."""
        code = _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="a", design="b", development="c", qa="d", pm="e", security="f",
            root=str(tmp_path),
        ))
        assert code == 0
        tasks = load_all_tasks(tmp_path / ".aoo" / "tasks")
        assert tasks[0]["owners"] == {
            "analysis": "a", "design": "b", "development": "c",
            "qa": "d", "pm": "e", "security": "f",
        }

    def test_new_task_still_works_without_new_owner_flags(self, tmp_path):
        """하위호환 — 새 인자를 Namespace에 안 넣어도(getattr 기본값) 안 깨짐."""
        code = _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        assert code == 0


class TestListAndShowTask:
    """SPEC-AP-001 백로그 §2 — 다중 task 조회 명령 부재."""

    def test_list_tasks_shows_all(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_new_task(_ns(
            title="b", platform="aoo", priority="normal", task_id="ST-002",
            analysis=None, design=None, root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_list_tasks(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "ST-001" in out
        assert "ST-002" in out

    def test_list_tasks_empty(self, tmp_path, capsys):
        code = _cmd_autopilot_list_tasks(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "No" in out and "tasks" in out

    def test_show_task_reports_phase_history(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_phase_transition(_ns(
            task_id="ST-001", new_phase=1, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_show_task(_ns(task_id="ST-001", root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "phase 0" in out
        assert "phase 1" in out

    def test_show_task_missing_fails(self, tmp_path):
        code = _cmd_autopilot_show_task(_ns(task_id="nope", root=str(tmp_path)))
        assert code == 1

    def test_list_tasks_excludes_archived_by_default(self, tmp_path, capsys):
        """docs/AUTOPILOT_IMPROVEMENTS.md §2 — 완료/취소된 task가 목록에 계속 쌓임."""
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_new_task(_ns(
            title="b", platform="ac", priority="normal", task_id="ST-002",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_set_task_status(_ns(
            task_id="ST-002", status="archived", reason=None, root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_list_tasks(_ns(all=False, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "ST-001" in out
        assert "ST-002" not in out

    def test_list_tasks_all_includes_archived_with_status_note(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_set_task_status(_ns(
            task_id="ST-001", status="archived", reason="done", root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_list_tasks(_ns(all=True, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "ST-001" in out
        assert "archived" in out

    def test_set_task_status_unknown_task_fails(self, tmp_path):
        code = _cmd_autopilot_set_task_status(_ns(
            task_id="nope", status="archived", reason=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_set_task_status_invalid_status_fails(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_set_task_status(_ns(
            task_id="ST-001", status="bogus", reason=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_show_task_displays_non_active_status_and_reason(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        _cmd_autopilot_set_task_status(_ns(
            task_id="ST-001", status="cancelled", reason="scope dropped", root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_show_task(_ns(task_id="ST-001", root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "cancelled" in out
        assert "scope dropped" in out

    def test_show_task_omits_status_line_when_active(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="a", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        capsys.readouterr()
        _cmd_autopilot_show_task(_ns(task_id="ST-001", root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "status:" not in out


class TestUpdateTaskCli:
    """대시보드/CLI에 과제 수정 기능이 없다는 실사용 피드백."""

    def _ns_update(self, tmp_path, **overrides):
        base = dict(
            task_id="ST-001", title=None, platform=None, priority=None,
            analysis=None, design=None, development=None, qa=None, pm=None,
            security=None, root=str(tmp_path),
        )
        base.update(overrides)
        return _ns(**base)

    def test_update_title(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="old", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_update_task(self._ns_update(tmp_path, title="new"))
        assert code == 0
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["title"] == "new"

    def test_update_single_owner_preserves_others(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="a", design="b", root=str(tmp_path),
        ))
        code = _cmd_autopilot_update_task(self._ns_update(tmp_path, design="c"))
        assert code == 0
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["owners"] == {"analysis": "a", "design": "c"}

    def test_clear_owner_with_empty_string(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="a", design="b", root=str(tmp_path),
        ))
        code = _cmd_autopilot_update_task(self._ns_update(tmp_path, analysis=""))
        assert code == 0
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["owners"] == {"design": "b"}

    def test_no_owner_flags_leaves_owners_untouched(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis="a", design="b", root=str(tmp_path),
        ))
        code = _cmd_autopilot_update_task(self._ns_update(tmp_path, title="renamed"))
        assert code == 0
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["owners"] == {"analysis": "a", "design": "b"}

    def test_missing_task_fails(self, tmp_path):
        code = _cmd_autopilot_update_task(self._ns_update(tmp_path, task_id="nope", title="x"))
        assert code == 1

    def test_dispatch_via_cmd_autopilot(self, tmp_path):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        code = cmd_autopilot(_ns(
            autopilot_command="update-task", task_id="ST-001", title="new",
            platform=None, priority=None, analysis=None, design=None,
            development=None, qa=None, pm=None, security=None, root=str(tmp_path),
        ))
        assert code == 0


class TestAddMember:
    def test_add_member_success(self, tmp_path):
        code = _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github="@yj", codeowner_scopes=None,
            root=str(tmp_path),
        ))
        assert code == 0
        members = load_team(tmp_path / ".aoo" / "team.json")
        assert members[0]["name"] == "유진"
        assert members[0]["synced"] is False

    def test_add_member_duplicate_id_fails(self, tmp_path):
        _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        code = _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진2", roles=["개발"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        assert code == 1


class TestRemoveMember:
    def test_remove_success(self, tmp_path, capsys):
        _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_remove_member(_ns(member_id="yj", root=str(tmp_path)))
        assert code == 0
        assert load_team(tmp_path / ".aoo" / "team.json") == []

    def test_remove_unknown_fails(self, tmp_path):
        code = _cmd_autopilot_remove_member(_ns(member_id="ghost", root=str(tmp_path)))
        assert code == 1


class TestUpdateMember:
    def test_update_role(self, tmp_path):
        _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        code = _cmd_autopilot_update_member(_ns(
            member_id="yj", name=None, roles=["개발"], github=None, codeowner_scopes=None,
            mark_synced=False, mark_unsynced=False, root=str(tmp_path),
        ))
        assert code == 0
        members = load_team(tmp_path / ".aoo" / "team.json")
        assert members[0]["roles"] == ["개발"]

    def test_mark_synced(self, tmp_path):
        _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        _cmd_autopilot_update_member(_ns(
            member_id="yj", name=None, roles=None, github=None, codeowner_scopes=None,
            mark_synced=True, mark_unsynced=False, root=str(tmp_path),
        ))
        members = load_team(tmp_path / ".aoo" / "team.json")
        assert members[0]["synced"] is True

    def test_update_unknown_fails(self, tmp_path):
        code = _cmd_autopilot_update_member(_ns(
            member_id="ghost", name="X", roles=None, github=None, codeowner_scopes=None,
            mark_synced=False, mark_unsynced=False, root=str(tmp_path),
        ))
        assert code == 1


class TestListMembers:
    def test_list_shows_all(self, tmp_path, capsys):
        _cmd_autopilot_add_member(_ns(
            member_id="yj", name="유진", roles=["설계"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        _cmd_autopilot_add_member(_ns(
            member_id="ms", name="민수", roles=["개발"], github=None, codeowner_scopes=None,
            root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_list_members(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "유진" in out
        assert "민수" in out
        assert "unsynced" in out

    def test_list_empty(self, tmp_path, capsys):
        code = _cmd_autopilot_list_members(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "No team members" in out


class TestApprovalsOpen:
    def test_open_clean_checklist_is_pending(self, tmp_path, capsys):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["EARS 표기:ok"], root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "ready for review" in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "pending"

    def test_open_with_needs_clarification_body_file_stays_draft(self, tmp_path, capsys):
        body = tmp_path / "spec.md"
        body.write_text("[NEEDS CLARIFICATION: 담당자 미지정]", encoding="utf-8")
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=str(body), checklist_item=["a:ok"], root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "DRAFT" in out
        assert "담당자 미지정" in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "draft"

    def test_open_missing_body_file_fails(self, tmp_path):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=str(tmp_path / "nope.md"), checklist_item=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_open_invalid_kind_fails(self, tmp_path):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="bogus", phase=1, title="t",
            body_file=None, checklist_item=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_checklist_item_without_status_defaults_to_pending(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["그냥 라벨만"], root=str(tmp_path),
        ))
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "draft"  # pending 상태 항목이 있으니 draft

    def test_adr_review_auto_adds_model_tier_checklist_item(self, tmp_path, capsys):
        """§9.5.4 순위5(원칙5 최소 기록) — adr_review는 자동으로 체크리스트가

        하나 늘어난다. 그 항목은 pending으로 시작하므로, 나머지가 전부 ok여도
        draft에 머문다 — 이게 바로 "명시하라"는 요구를 구조로 강제하는 지점이다.
        """
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="adr_review", phase=2, title="t",
            body_file=None, checklist_item=["Gate 매핑:ok"], root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "자동 추가됨" in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        labels = [c["label"] for c in approvals[0]["checklist"]]
        assert any("모델 tier" in label for label in labels)
        assert approvals[0]["status"] == "draft"  # 자동 추가 항목이 pending이라

    def test_adr_review_does_not_duplicate_existing_model_tier_item(self, tmp_path, capsys):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="adr_review", phase=2, title="t",
            body_file=None, checklist_item=["모델 tier 배정 이미 적음:ok"], root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "자동 추가됨" not in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert len(approvals[0]["checklist"]) == 1

    def test_spec_review_does_not_get_model_tier_item(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["EARS 표기:ok"], root=str(tmp_path),
        ))
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        labels = [c["label"] for c in approvals[0]["checklist"]]
        assert not any("모델 tier" in label for label in labels)

    def test_no_checklist_gate_flag_bypasses_gating(self, tmp_path):
        """Appendix M 발견 1 — scan-thresholds가 여는 threshold_review는

        gate_on_checklist=False라 pending 상태로 열리지만, 사람이 CLI로
        같은 kind를 열면 이 옵션을 켤 방법이 없어 draft에 갇혔다(Ch35).
        """
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="threshold_review", phase=7, title="t",
            body_file=None, checklist_item=["할 일:pending"],
            no_checklist_gate=True, root=str(tmp_path),
        ))
        assert code == 0
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "pending"
        assert approvals[0]["gate_on_checklist"] is False

    def test_without_no_checklist_gate_flag_still_gates_by_default(self, tmp_path):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="threshold_review", phase=7, title="t",
            body_file=None, checklist_item=["할 일:pending"],
            no_checklist_gate=False, root=str(tmp_path),
        ))
        assert code == 0
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "draft"

    def test_missing_no_checklist_gate_arg_defaults_to_gated(self, tmp_path):
        """하위호환 — 기존 Namespace 호출에 이 필드가 없어도 안 깨짐."""
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        assert code == 0
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "draft"


class TestPhaseTransition:
    """§9.5.4 순위1 — 옵트인 Phase 전이 게이트의 CLI 배선."""

    def test_transition_without_gate(self, tmp_path, capsys):
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="t", platform="ac")
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=1, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Phase 1" in out
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-014")
        assert task is not None
        assert task["current_phase"] == 1

    def test_transition_blocked_without_approval(self, tmp_path):
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="t", platform="ac")
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval="spec_review", root=str(tmp_path),
        ))
        assert code == 1

    def test_transition_allowed_after_approval(self, tmp_path, capsys):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-014", title="t", platform="ac")
        approval = open_approval(
            approvals_path, task_id="ST-014", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, approval["id"], decision="approved", decided_by="pm")

        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval="spec_review", root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Gated on an approved" in out
        task = load_task(tasks_dir, "ST-014")
        assert task is not None
        assert task["current_phase"] == 2

    def test_transition_missing_task_fails_gracefully(self, tmp_path):
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="nope", new_phase=1, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_transition_backward_warns_but_does_not_block(self, tmp_path, capsys):
        """docs/AUTOPILOT_IMPROVEMENTS.md §3 — 역행/건너뛰기가 조용히 성공함."""
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-014", title="t", platform="ac")
        _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=1, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "BEHIND" in out
        task = load_task(tasks_dir, "ST-014")
        assert task is not None
        assert task["current_phase"] == 1

    def test_transition_skip_warns_but_does_not_block(self, tmp_path, capsys):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-014", title="t", platform="ac")
        capsys.readouterr()
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=3, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "skipping" in out
        assert "2 phase(s) skipped" in out

    def test_transition_no_warning_on_normal_forward_step(self, tmp_path, capsys):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-014", title="t", platform="ac")
        capsys.readouterr()
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=1, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "BEHIND" not in out
        assert "skipping" not in out


class TestPhasePolicyCli:
    """SPEC-AP-001 백로그 §3 — 정책 파일이 --require-approval 없이도
    phase transition을 게이트한다."""

    def test_set_then_transition_is_gated_by_policy(self, tmp_path, capsys):
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="t", platform="ac")
        code = _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval="spec_review", clear=False, root=str(tmp_path),
        ))
        assert code == 0

        # --require-approval을 안 줘도 정책이 대신 게이트해야 한다
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        assert code == 1  # 아직 승인이 없으니 막힘

    def test_policy_satisfied_allows_transition(self, tmp_path, capsys):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-014", title="t", platform="ac")
        approval = open_approval(
            approvals_path, task_id="ST-014", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, approval["id"], decision="approved", decided_by="pm")
        _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval="spec_review", clear=False, root=str(tmp_path),
        ))

        capsys.readouterr()
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "phase policy" in out

    def test_explicit_flag_overrides_policy(self, tmp_path):
        """--require-approval을 직접 주면 정책이 뭐든 그걸 우선한다."""
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="t", platform="ac")
        _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval="spec_review", clear=False, root=str(tmp_path),
        ))
        # 정책은 spec_review를 요구하지만, 명시적으로 아무 게이트도 안 건다
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=3, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        assert code == 0  # phase 3엔 정책이 없으므로 안 막힘

    def test_clear_removes_policy(self, tmp_path):
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="t", platform="ac")
        _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval="spec_review", clear=False, root=str(tmp_path),
        ))
        _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval=None, clear=True, root=str(tmp_path),
        ))
        code = _cmd_autopilot_phase_transition(_ns(
            task_id="ST-014", new_phase=2, mode="auto", approved_by=None,
            require_approval=None, root=str(tmp_path),
        ))
        assert code == 0  # 정책을 지웠으니 다시 안 막힘

    def test_show_empty_policy(self, tmp_path, capsys):
        code = _cmd_autopilot_phase_policy_show(_ns(root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "No phase policy" in out

    def test_set_without_kind_or_clear_fails(self, tmp_path):
        code = _cmd_autopilot_phase_policy_set(_ns(
            new_phase=2, require_approval=None, clear=False, root=str(tmp_path),
        ))
        assert code == 1


class TestApprovalsListAndDecide:
    def test_list_pending_only_by_default(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-001", kind="spec_review", phase=1, title="ready",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-002", kind="spec_review", phase=1, title="not-ready",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "ready" in out
        assert "not-ready" not in out

    def test_list_all_includes_draft(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-002", kind="spec_review", phase=1, title="not-ready",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=True, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "not-ready" in out

    def test_decide_approve_then_disappears_from_pending(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-001", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]

        code = _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="pm-park",
            rationale="ok", root=str(tmp_path),
        ))
        assert code == 0

        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "No pending approvals" in out

    def test_decide_unknown_id_fails(self, tmp_path):
        code = _cmd_autopilot_approvals_decide(_ns(
            approval_id="nope", decision="approved", decided_by="x",
            rationale=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_list_pending_nudges_when_drafts_hidden_and_none_pending(self, tmp_path, capsys):
        """docs/AUTOPILOT_IMPROVEMENTS.md §4 — draft가 조용히 쌓여 아무도 눈치 못 챔."""
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-002", kind="spec_review", phase=1, title="not-ready",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "No pending approvals" in out
        assert "1 draft approval" in out
        assert "--all" in out

    def test_list_pending_footer_notes_hidden_drafts_when_results_exist(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-001", kind="spec_review", phase=1, title="ready",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-002", kind="spec_review", phase=1, title="not-ready",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        capsys.readouterr()
        code = _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert code == 0
        assert "ready" in out
        assert "1 draft approval(s) not shown" in out

    def test_list_all_has_no_draft_nudge(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-002", kind="spec_review", phase=1, title="not-ready",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=True, root=str(tmp_path)))
        out = capsys.readouterr().out
        assert "not shown" not in out


class TestApprovalsCancel:
    """docs/AUTOPILOT_IMPROVEMENTS.md §4 — 승인 요청을 취소할 방법이 없음."""

    def test_cancel_draft_succeeds(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:pending"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        capsys.readouterr()
        code = _cmd_autopilot_approvals_cancel(_ns(
            approval_id=approval_id, reason="no longer needed", root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "Cancelled" in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "cancelled"

    def test_cancel_pending_succeeds(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        code = _cmd_autopilot_approvals_cancel(_ns(
            approval_id=approval_id, reason=None, root=str(tmp_path),
        ))
        assert code == 0

    def test_cancel_unknown_id_fails(self, tmp_path):
        code = _cmd_autopilot_approvals_cancel(_ns(
            approval_id="nope", reason=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_cancel_already_decided_fails(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="pm",
            rationale=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_approvals_cancel(_ns(
            approval_id=approval_id, reason=None, root=str(tmp_path),
        ))
        assert code == 1

    def test_cancel_already_cancelled_fails(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        _cmd_autopilot_approvals_cancel(_ns(
            approval_id=approval_id, reason=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_approvals_cancel(_ns(
            approval_id=approval_id, reason=None, root=str(tmp_path),
        ))
        assert code == 1


class TestApprovalsUpdate:
    """SPEC-AP-001 백로그 §4 — CLI 배선(agent-eval autopilot approvals update)."""

    def test_update_promotes_draft_to_pending(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="threshold_review", phase=7, title="t",
            body_file=None, checklist_item=["항목:pending"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]

        capsys.readouterr()
        code = _cmd_autopilot_approvals_update(_ns(
            approval_id=approval_id, checklist_item=["항목:ok"], root=str(tmp_path),
        ))
        out = capsys.readouterr().out
        assert code == 0
        assert "Now ready for review" in out
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "pending"

    def test_update_unknown_label_fails(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="threshold_review", phase=7, title="t",
            body_file=None, checklist_item=["실제항목:pending"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        code = _cmd_autopilot_approvals_update(_ns(
            approval_id=approval_id, checklist_item=["없는항목:ok"], root=str(tmp_path),
        ))
        assert code == 1

    def test_update_decided_approval_fails(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t",
            body_file=None, checklist_item=["a:ok"], root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="pm",
            rationale=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_approvals_update(_ns(
            approval_id=approval_id, checklist_item=["a:flag"], root=str(tmp_path),
        ))
        assert code == 1


class TestChecklistItemParsing:
    """실제 버그(AOO 실습서 Ch 35) — LABEL:STATUS가 첫 콜론에서만 분리돼
    라벨 안에 콜론이 있으면 깨졌다."""

    def test_label_containing_its_own_colon_is_preserved(self, tmp_path):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t", body_file=None,
            checklist_item=["설계자: 통계적으로 달성 가능한 임계값인가 판단:pending"],
            root=str(tmp_path),
        ))
        assert code == 0
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        label = approvals[0]["checklist"][0]["label"]
        status = approvals[0]["checklist"][0]["status"]
        assert label == "설계자: 통계적으로 달성 가능한 임계값인가 판단"
        assert status == "pending"

    def test_label_with_no_colon_defaults_to_pending(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t", body_file=None,
            checklist_item=["콜론이 아예 없는 라벨"], root=str(tmp_path),
        ))
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["checklist"][0]["label"] == "콜론이 아예 없는 라벨"
        assert approvals[0]["checklist"][0]["status"] == "pending"

    def test_invalid_status_is_rejected(self, tmp_path):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="spec_review", phase=1, title="t", body_file=None,
            checklist_item=["항목:okk"], root=str(tmp_path),
        ))
        assert code == 1
        assert load_approvals(tmp_path / ".aoo" / "approvals.jsonl") == []


class TestMultiPersonApprovalCli:
    """§6 M4 2인 승인 — `approvals open --required-approvals` + decide 배선."""

    def test_deploy_open_reports_two_required_approvers(self, tmp_path, capsys):
        code = _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="deploy", phase=8, title="배포 승인",
            body_file=None, checklist_item=None, required_approvals=None, root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Requires 2 distinct approvers" in out

    def test_first_decide_reports_still_pending_progress(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="deploy", phase=8, title="배포 승인",
            body_file=None, checklist_item=None, required_approvals=None, root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        capsys.readouterr()

        code = _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="lead-kim",
            rationale=None, root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "1/2" in out
        assert "still needs 1 more" in out
        # 아직 확정이 아니니 pending 목록에 그대로 있어야 한다
        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        assert "배포 승인" in capsys.readouterr().out

    def test_second_distinct_approver_finalizes_via_cli(self, tmp_path, capsys):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="deploy", phase=8, title="배포 승인",
            body_file=None, checklist_item=None, required_approvals=None, root=str(tmp_path),
        ))
        approval_id = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]["id"]
        _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="lead-kim",
            rationale=None, root=str(tmp_path),
        ))
        capsys.readouterr()

        code = _cmd_autopilot_approvals_decide(_ns(
            approval_id=approval_id, decision="approved", decided_by="sec-choi",
            rationale=None, root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Recorded: approved" in out

        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        assert "No pending approvals" in capsys.readouterr().out

    def test_required_approvals_flag_overrides_default(self, tmp_path):
        _cmd_autopilot_approvals_open(_ns(
            task_id="ST-014", kind="deploy", phase=8, title="긴급 배포",
            body_file=None, checklist_item=None, required_approvals=1, root=str(tmp_path),
        ))
        approval = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")[0]
        assert approval["required_approvals"] == 1


class TestSkillsDetect:
    def test_no_candidates_when_empty(self, tmp_path, capsys):
        code = _cmd_autopilot_skills_detect(_ns(min_occurrences=3, root=str(tmp_path)))
        assert code == 0
        assert "No repeated checklist pattern" in capsys.readouterr().out

    def test_reports_repeated_pattern(self, tmp_path, capsys):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        checklist = [{"label": "EARS 표기", "status": "ok"}]
        for i in range(3):
            open_approval(p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                          checklist=checklist)
        code = _cmd_autopilot_skills_detect(_ns(min_occurrences=3, root=str(tmp_path)))
        assert code == 0
        out = capsys.readouterr().out
        assert "spec_review" in out
        assert "EARS 표기" in out
        assert "nothing was created" in out

    def test_dispatch_via_cmd_autopilot(self, tmp_path):
        code = cmd_autopilot(_ns(
            autopilot_command="skills", skills_command="detect",
            min_occurrences=3, root=str(tmp_path),
        ))
        assert code == 0

    def test_dispatch_no_skills_subcommand_fails(self):
        from agent_evaluator.cli.autopilot import _cmd_autopilot_skills
        assert _cmd_autopilot_skills(_ns(skills_command=None)) == 1


class TestSkillsScaffold:
    """docs/AUTOPILOT_IMPROVEMENTS.md §7 — 후보 발견 후 스캐폴딩 명령 부재."""

    def _seed_candidate(self, tmp_path, n=3):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        checklist = [{"label": "EARS 표기", "status": "ok"}]
        for i in range(n):
            open_approval(p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                          checklist=checklist)
        return p

    def test_no_candidate_fails(self, tmp_path):
        code = _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        assert code == 1

    def test_scaffold_writes_stub(self, tmp_path):
        self._seed_candidate(tmp_path)
        code = _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="new-skill", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        assert code == 0
        stub = tmp_path / "Skills" / "new-skill" / "SKILL.md"
        assert stub.is_file()
        text = stub.read_text(encoding="utf-8")
        assert "name: new-skill" in text
        assert "EARS 표기" in text

    def test_scaffold_refuses_to_overwrite_without_force(self, tmp_path):
        self._seed_candidate(tmp_path)
        _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        code = _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        assert code == 1

    def test_scaffold_force_overwrites(self, tmp_path):
        self._seed_candidate(tmp_path)
        _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        code = _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind=None, min_occurrences=3,
            out=str(tmp_path / "Skills"), force=True,
        ))
        assert code == 0

    def test_scaffold_filters_by_kind(self, tmp_path):
        self._seed_candidate(tmp_path)
        code = _cmd_autopilot_skills_scaffold(_ns(
            root=str(tmp_path), name="s", kind="adr_review", min_occurrences=3,
            out=str(tmp_path / "Skills"), force=False,
        ))
        assert code == 1  # only spec_review candidates exist

    def test_dispatch_via_cmd_autopilot(self, tmp_path):
        self._seed_candidate(tmp_path)
        code = cmd_autopilot(_ns(
            autopilot_command="skills", skills_command="scaffold",
            name="s", kind=None, min_occurrences=3, out=str(tmp_path / "Skills"),
            force=False, root=str(tmp_path),
        ))
        assert code == 0


class TestPhaseCheck:
    """docs/AUTOPILOT_IMPROVEMENTS.md §3, LIMITS L4."""

    def test_no_stale_tasks(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        code = _cmd_autopilot_phase_check(_ns(root=str(tmp_path), stale_days=7.0))
        assert code == 0
        assert "No task" in capsys.readouterr().out

    def test_reports_stale_task(self, tmp_path, capsys):
        _cmd_autopilot_new_task(_ns(
            title="t", platform="ac", priority="normal", task_id="ST-001",
            analysis=None, design=None, root=str(tmp_path),
        ))
        tasks_dir = tmp_path / ".aoo" / "tasks"
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        task["phase_history"][-1]["entered_at"] = "2020-01-01T00:00:00+00:00"
        save_task(tasks_dir, task)

        code = _cmd_autopilot_phase_check(_ns(root=str(tmp_path), stale_days=7.0))
        assert code == 0
        out = capsys.readouterr().out
        assert "ST-001" in out

    def test_dispatch_via_cmd_autopilot(self, tmp_path):
        code = cmd_autopilot(_ns(
            autopilot_command="phase", phase_command="check",
            stale_days=7.0, root=str(tmp_path),
        ))
        assert code == 0


class TestAutopilotDecisionsCli:
    """docs/AUTOPILOT_IMPROVEMENTS.md §6 — decisions가 autopilot 하위가

    아닌 별도 최상위 명령이었다."""

    def test_list_defaults_log_to_aoo_decisions(self, tmp_path, capsys):
        code = _cmd_autopilot_decisions(_ns(
            decisions_command="list", log=None, pending=False, as_json=False,
            root=str(tmp_path),
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert str(tmp_path / ".aoo" / "decisions.jsonl") in out

    def test_record_and_list_round_trip(self, tmp_path, capsys):
        from agent_evaluator.rca.decision_ledger import record_gate_decision

        log = tmp_path / ".aoo" / "decisions.jsonl"
        record_gate_decision(
            log, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        capsys.readouterr()
        code = _cmd_autopilot_decisions(_ns(
            decisions_command="record", log=None, outcome="overridden",
            decided_by="pm", rationale=None, gate_run_id=None, root=str(tmp_path),
        ))
        assert code == 0
        assert "Recorded" in capsys.readouterr().out

    def test_no_subcommand_fails(self, tmp_path):
        code = _cmd_autopilot_decisions(_ns(decisions_command=None, root=str(tmp_path)))
        assert code == 1

    def test_explicit_log_override(self, tmp_path, capsys):
        custom = tmp_path / "custom_decisions.jsonl"
        code = _cmd_autopilot_decisions(_ns(
            decisions_command="list", log=str(custom), pending=False, as_json=False,
            root=str(tmp_path),
        ))
        assert code == 0
        assert str(custom) in capsys.readouterr().out

    def test_dispatch_via_cmd_autopilot(self, tmp_path):
        code = cmd_autopilot(_ns(
            autopilot_command="decisions", decisions_command="list", log=None,
            pending=False, as_json=False, root=str(tmp_path),
        ))
        assert code == 0


class TestApprovalsScanThresholds:
    def _log(self, decisions_path, reason, n=5):
        from agent_evaluator.rca.decision_ledger import record_gate_decision
        for _ in range(n):
            record_gate_decision(
                decisions_path, result_file="r.json", agent_version="v1", exit_code=75,
                verdict_level="not_ready", decision_ready=False, undecided_reason=reason,
            )

    def test_no_pattern_reports_nothing(self, tmp_path, capsys):
        from agent_evaluator.cli.autopilot import _cmd_autopilot_approvals_scan_thresholds

        code = _cmd_autopilot_approvals_scan_thresholds(
            _ns(min_occurrences=5, root=str(tmp_path))
        )
        assert code == 0
        assert "No repeated exit-75 pattern" in capsys.readouterr().out

    def test_opens_review_and_shows_up_in_pending_list(self, tmp_path, capsys):
        from agent_evaluator.cli.autopilot import _cmd_autopilot_approvals_scan_thresholds

        self._log(tmp_path / ".aoo" / "decisions.jsonl", "반복되는 사유")
        code = _cmd_autopilot_approvals_scan_thresholds(
            _ns(min_occurrences=5, root=str(tmp_path))
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "Threshold review opened" in out

        # 회귀 방지: gate_on_checklist=False 버그(§ 발견분)가 고쳐졌는지 — pending 큐에 바로 뜸
        capsys.readouterr()
        _cmd_autopilot_approvals_list(_ns(all=False, root=str(tmp_path)))
        assert "반복되는 사유" in capsys.readouterr().out

    def test_dispatch_via_approvals(self, tmp_path):
        self._log(tmp_path / ".aoo" / "decisions.jsonl", "사유")
        code = cmd_autopilot(_ns(
            autopilot_command="approvals", approvals_command="scan-thresholds",
            min_occurrences=5, root=str(tmp_path),
        ))
        assert code == 0


class TestDashboardWiring:
    def test_dashboard_reports_missing_uvicorn_gracefully(self, tmp_path, monkeypatch):
        # uvicorn이 없는 환경을 흉내낸다 — ImportError를 일으키지 않고 exit 1로 처리되는지만 확인.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "uvicorn":
                raise ImportError("no uvicorn")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        code = _cmd_autopilot_dashboard(
            _ns(root=str(tmp_path), host="127.0.0.1", port=8766, open=False)
        )
        assert code == 1


class TestCmdAutopilotDispatch:
    def test_no_subcommand_returns_1(self):
        assert cmd_autopilot(_ns(autopilot_command=None)) == 1

    def test_unknown_subcommand_returns_1(self):
        assert cmd_autopilot(_ns(autopilot_command="bogus")) == 1

    def test_install_dispatches(self, tmp_path):
        code = cmd_autopilot(_ns(autopilot_command="install", platform="ac", root=str(tmp_path)))
        assert code == 0
        assert (tmp_path / ".aoo" / "tasks").is_dir()


class TestEntryPointRegistration:
    """cli/main.py가 이 모듈을 직접 import하지 않고 entry-points로만 찾을 수 있는지.

    ``pyproject.toml``의 ``[project.entry-points."agent_evaluator.cli_plugins"]``가
    ``autopilot = "agent_evaluator.cli.autopilot:register"``를 선언한다 — 이
    모듈이 언젠가 별도 배포판으로 분리돼도 ``cli/main.py``가 그대로 동작하는지
    보장하려는 계약이다. 여기서는 그 계약의 두 절반을 각각 확인한다:
    ① ``register()`` 자체가 시그니처대로 동작하는가,
    ② 실제로 설치된 패키지 메타데이터에 그 엔트리 포인트가 잡히는가.
    """

    def test_register_adds_subparser_and_returns_handler(self):
        from agent_evaluator.cli.autopilot import cmd_autopilot, register

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        handler = register(sub)

        assert handler is cmd_autopilot
        # 서브파서가 실제로 붙었는지 — "autopilot ..." 인자를 파싱할 수 있어야 한다
        args = parser.parse_args(["autopilot", "doctor", "--root", "."])
        assert args.command == "autopilot"
        assert args.autopilot_command == "doctor"

    def test_installed_entry_point_metadata_resolves_to_register(self):
        """pip install -e .로 설치된 실제 메타데이터에 잡히는지 확인.

        이 테스트가 실패한다면 ``pyproject.toml``을 고친 뒤 재설치
        (``pip install -e .``)를 안 한 것일 가능성이 크다 — entry_points는
        빌드 메타데이터(.dist-info)에 있어서 소스만 고쳐서는 반영되지 않는다.
        """
        from importlib.metadata import entry_points

        try:
            eps = list(entry_points(group="agent_evaluator.cli_plugins"))
        except TypeError:
            eps = list(entry_points().get("agent_evaluator.cli_plugins", []))

        names = [ep.name for ep in eps]
        assert "autopilot" in names, (
            "entry point not found in installed metadata — did you run "
            "'pip install -e .' after changing pyproject.toml?"
        )

        autopilot_ep = next(ep for ep in eps if ep.name == "autopilot")
        loaded = autopilot_ep.load()
        assert loaded.__name__ == "register"
        assert loaded.__module__ == "agent_evaluator.cli.autopilot"

    def test_load_cli_plugins_wires_autopilot_into_handlers(self):
        from agent_evaluator.cli.autopilot import cmd_autopilot
        from agent_evaluator.cli.main import _load_cli_plugins

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        handlers = _load_cli_plugins(sub)

        assert handlers.get("autopilot") is cmd_autopilot
        # main.py가 더 이상 하드코딩 import 없이도 서브파서를 붙였는지 확인
        args = parser.parse_args(["autopilot", "doctor", "--root", "."])
        assert args.autopilot_command == "doctor"


@pytest.fixture
def autopilot_client(tmp_path):
    """설치된 .aoo/ 위에 create_autopilot_app()을 얹은 TestClient (M0/M0.5 대시보드)."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi[serve] extra not installed")

    from agent_evaluator.serve.autopilot_app import create_autopilot_app

    _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
    app = create_autopilot_app(root=tmp_path)
    client = TestClient(app)
    client.tmp_path = tmp_path  # type: ignore[attr-defined]
    return client


class TestAutopilotAppJsonApi:
    """create_autopilot_app()이 실제 .aoo/ 파일을 읽는지(M0 완료조건) 확인한다."""

    def test_api_tasks_and_team_serve_real_data(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac")
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민", roles=["분석"]
        )

        r = autopilot_client.get("/api/tasks")
        assert r.status_code == 200
        assert r.json()[0]["task_id"] == "ST-014"

        r = autopilot_client.get("/api/team")
        assert r.json()[0]["name"] == "정민"

    def test_api_claims_reads_real_claims_jsonl(self, autopilot_client):
        from agent_evaluator.gates.team_concurrency import append_claim

        tmp_path = autopilot_client.tmp_path
        append_claim(
            tmp_path / ".aoo" / "claims.jsonl", claim_id="c-1", developer="수아",
            scope=["src/x.py"], started_at="2026-09-16T00:00:00+00:00", status="active",
        )
        r = autopilot_client.get("/api/claims")
        assert r.json()[0]["developer"] == "수아"

    def test_api_approvals_reads_real_approvals(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.get("/api/approvals")
        assert r.json()[0]["task_id"] == "ST-014"


class TestAutopilotBoardPage:
    def test_board_lists_real_tasks(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac")
        r = autopilot_client.get("/")
        assert r.status_code == 200
        assert "ST-014" in r.text
        assert "반품정책" in r.text

    def test_board_empty_state(self, autopilot_client):
        r = autopilot_client.get("/")
        assert "아직 과제가 없습니다" in r.text

    def test_board_shows_pending_badge_from_live_approvals_not_dead_field(self, autopilot_client):
        """회귀 테스트 — task['blocking_on']은 create_task()가 [] 그대로 두고 아무도

        갱신하지 않는 죽은 필드였다(승인 큐가 실제로 생겨도 배지가 절대 안 뜸).
        이제 "이 과제를 task_id로 건 pending 승인이 있는가"를 매번 직접 센다.
        """
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac")
        # 새로 만든 과제엔 blocking_on == [] — 죽은 필드로 판정했다면 배지가 안 뜬다.
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="SPEC 검토", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.get("/")
        assert 'class="badge pending">승인 대기' in r.text

    def test_board_no_badge_when_no_pending_approval(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac")
        r = autopilot_client.get("/")
        assert 'class="badge pending">승인 대기' not in r.text

    def test_post_tasks_creates_task_and_redirects(self, autopilot_client):
        r = autopilot_client.post(
            "/tasks", data={"title": "새 과제", "platform": "aoo"}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"

        tasks = load_all_tasks(autopilot_client.tmp_path / ".aoo" / "tasks")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "새 과제"
        assert tasks[0]["platform"] == "AOO"

    def test_post_tasks_with_explicit_id_and_owners(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민", roles=["분석"]
        )
        autopilot_client.post(
            "/tasks",
            data={"title": "t", "platform": "ac", "task_id": "ST-099", "analysis": "정민"},
            follow_redirects=False,
        )
        task = load_all_tasks(tmp_path / ".aoo" / "tasks")[0]
        assert task["task_id"] == "ST-099"
        assert task["owners"]["analysis"] == "정민"

    def test_post_tasks_duplicate_id_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 중복 task_id가 조용히 무시돼

        사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks", data={"title": "dup", "platform": "ac", "task_id": "ST-001"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "task_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text
        tasks = load_all_tasks(tmp_path / ".aoo" / "tasks")
        assert len(tasks) == 1  # 중복 추가되지 않음

    def test_task_detail_page_renders(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac")
        r = autopilot_client.get("/tasks/ST-014")
        assert r.status_code == 200
        assert "반품정책" in r.text

    def test_task_detail_missing_returns_404(self, autopilot_client):
        r = autopilot_client.get("/tasks/NOPE")
        assert r.status_code == 404

    def test_board_hides_archived_tasks_by_default(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md 신규(§8) — 대시보드 보드가 CLI

        list-tasks의 active-only 기본값을 따라가지 못해 완료/취소 과제가
        영원히 카드로 남아 있었다."""
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="활성", platform="ac")
        create_task(tasks_dir, task_id="ST-002", title="완료됨", platform="ac")
        set_task_status(tasks_dir, "ST-002", "archived")

        r = autopilot_client.get("/")
        assert "활성" in r.text
        assert "완료됨" not in r.text
        assert "전체 보기" in r.text

    def test_board_show_all_includes_archived(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="완료됨", platform="ac")
        set_task_status(tasks_dir, "ST-001", "archived")

        r = autopilot_client.get("/?show_all=1")
        assert "완료됨" in r.text
        assert "활성 과제만 보기" in r.text

    def test_post_tasks_accepts_all_six_owner_roles(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md 신규(§8) — new-task는 v1.1.3부터

        6역할을 받는데 대시보드 폼/핸들러는 여전히 analysis/design 2개뿐."""
        tmp_path = autopilot_client.tmp_path
        autopilot_client.post(
            "/tasks",
            data={
                "title": "t", "platform": "ac", "task_id": "ST-001",
                "analysis": "a", "design": "b", "development": "c",
                "qa": "d", "pm": "e", "security": "f",
            },
            follow_redirects=False,
        )
        task = load_all_tasks(tmp_path / ".aoo" / "tasks")[0]
        assert task["owners"] == {
            "analysis": "a", "design": "b", "development": "c",
            "qa": "d", "pm": "e", "security": "f",
        }

    def test_board_flags_stale_phase(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md 신규(§8), LIMITS L4 — phase 정체

        신호(v1.1.4)가 CLI에만 있고 대시보드엔 없었다."""
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="정체됨", platform="ac")
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        task["phase_history"][-1]["entered_at"] = "2020-01-01T00:00:00+00:00"
        save_task(tasks_dir, task)

        r = autopilot_client.get("/")
        assert 'class="badge warning">phase 정체' in r.text

    def test_task_detail_shows_stale_banner(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="정체됨", platform="ac")
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        task["phase_history"][-1]["entered_at"] = "2020-01-01T00:00:00+00:00"
        save_task(tasks_dir, task)

        r = autopilot_client.get("/tasks/ST-001")
        assert "머물러 있습니다" in r.text

    def test_task_detail_no_stale_banner_when_fresh(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="새 과제", platform="ac")
        r = autopilot_client.get("/tasks/ST-001")
        assert "머물러 있습니다" not in r.text


class TestPhaseTransitionRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §9 — phase 전이(PLANNING.md §6이

    "책의 척추"라 부르는 메커니즘)가 대시보드에 아예 없었다."""

    def test_ungated_transition_succeeds(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 1, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["current_phase"] == 1

    def test_gated_transition_without_approval_is_blocked(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "spec_review", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_error" in r.headers["location"]
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["current_phase"] == 0

    def test_error_banner_rendered_on_task_detail(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "spec_review", "approved_by": ""},
        )
        assert "cannot transition" in r.text

    def test_gated_transition_succeeds_after_approval(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-001", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(
            tmp_path / ".aoo" / "approvals.jsonl", approval["id"],
            decision="approved", decided_by="pm",
        )
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "spec_review", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_error" not in r.headers["location"]
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["current_phase"] == 2

    def test_backward_transition_warns_but_succeeds(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "", "approved_by": ""},
        )
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 1, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_warning" in r.headers["location"]
        assert "BEHIND" in r.headers["location"]
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["current_phase"] == 1

    def test_skip_transition_warns(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 3, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert "skipping" in r.headers["location"]

    def test_phase_policy_is_enforced_without_explicit_require_approval(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §10 — CLI phase transition은

        .aoo/phase_policy.json을 자동 조회하는데, 대시보드 라우트는 그걸
        전혀 안 읽어서 사람이 드롭다운에서 kind를 안 고르면 정책이 조용히
        무시됐다. 이게 바로 그 회귀 테스트다."""
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="ac")
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")

        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_error" in r.headers["location"]
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["current_phase"] == 0  # blocked, unchanged

    def test_phase_policy_satisfied_by_approval_allows_transition(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="ac")
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-001", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(
            tmp_path / ".aoo" / "approvals.jsonl", approval["id"],
            decision="approved", decided_by="pm",
        )
        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_error" not in r.headers["location"]
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["current_phase"] == 2

    def test_explicit_require_approval_overrides_policy(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="ac")
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")

        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "adr_review", "approved_by": ""},
            follow_redirects=False,
        )
        # adr_review (explicit) not spec_review (policy) is what gets checked
        assert "adr_review" in r.headers["location"]
        assert "spec_review" not in r.headers["location"]

    def test_no_policy_for_this_phase_is_ungated(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="ac")
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 5, "deploy")

        r = autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 1, "require_approval": "", "approved_by": ""},
            follow_redirects=False,
        )
        assert "phase_error" not in r.headers["location"]
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["current_phase"] == 1

    def test_task_detail_shows_policy_hint(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")
        r = autopilot_client.get("/tasks/ST-001")
        assert "spec_review" in r.text


class TestSetTaskStatusRoute:
    def test_archives_task(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/status", data={"status": "archived", "reason": "done"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["status"] == "archived"
        assert task["status_reason"] == "done"

    def test_invalid_status_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 잘못된 상태값이 조용히 무시돼

        사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/status", data={"status": "bogus", "reason": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "status_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text
        task = load_task(tmp_path / ".aoo" / "tasks", "ST-001")
        assert task is not None
        assert task["status"] == "active"


class TestUpdateTaskRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §1/§9 — 등록 후 과제 제목·플랫폼·

    우선순위·담당자를 고칠 방법이 대시보드에 없었다."""

    def test_edit_form_prefilled_with_current_values(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(
            tmp_path / ".aoo" / "tasks", task_id="ST-001", title="원래 제목", platform="ac",
            owners={"analysis": "a"},
        )
        r = autopilot_client.get("/tasks/ST-001")
        assert "/tasks/ST-001/update" in r.text
        assert 'value="원래 제목"' in r.text
        assert 'value="a"' in r.text

    def test_updates_title_platform_priority_owners(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="old", platform="ac")
        r = autopilot_client.post(
            "/tasks/ST-001/update",
            data={
                "title": "new", "platform": "AOO", "priority": "high",
                "analysis": "a", "design": "b", "development": "", "qa": "", "pm": "",
                "security": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/tasks/ST-001"
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["title"] == "new"
        assert task["platform"] == "AOO"
        assert task["priority"] == "high"
        assert task["owners"] == {"analysis": "a", "design": "b"}

    def test_blank_owner_fields_clear_owners(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(
            tasks_dir, task_id="ST-001", title="t", platform="ac",
            owners={"analysis": "a", "design": "b"},
        )
        autopilot_client.post(
            "/tasks/ST-001/update",
            data={
                "title": "t", "platform": "AC", "priority": "normal",
                "analysis": "", "design": "", "development": "", "qa": "", "pm": "",
                "security": "",
            },
        )
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["owners"] == {}

    def test_update_unknown_task_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 없는 task_id 수정이 조용히

        무시돼 사용자가 실패 여부를 알 수 없었다."""
        r = autopilot_client.post(
            "/tasks/nope/update",
            data={
                "title": "x", "platform": "", "priority": "",
                "analysis": "", "design": "", "development": "", "qa": "", "pm": "",
                "security": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "update_error" in r.headers["location"]

    def test_does_not_touch_phase_or_status(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="ac")
        autopilot_client.post(
            "/tasks/ST-001/phase",
            data={"new_phase": 2, "require_approval": "", "approved_by": ""},
        )
        autopilot_client.post(
            "/tasks/ST-001/update",
            data={
                "title": "new", "platform": "AC", "priority": "normal",
                "analysis": "", "design": "", "development": "", "qa": "", "pm": "",
                "security": "",
            },
        )
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["current_phase"] == 2


class TestAutopilotTeamPage:
    def test_team_page_lists_members(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민", roles=["분석"]
        )
        r = autopilot_client.get("/team")
        assert "정민" in r.text
        assert "GitHub 반영 필요" in r.text  # synced=False 기본값이 화면에 드러나는지

    def test_post_team_adds_member_and_redirects(self, autopilot_client):
        r = autopilot_client.post(
            "/team", data={"member_id": "yj", "name": "유진", "role": "설계"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/team"

        members = load_team(autopilot_client.tmp_path / ".aoo" / "team.json")
        assert members[0]["name"] == "유진"
        assert members[0]["roles"] == ["설계"]
        assert members[0]["synced"] is False

    def test_post_team_duplicate_id_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 중복 id가 조용히 무시돼

        사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="yj", name="유진", roles=["설계"]
        )
        r = autopilot_client.post(
            "/team", data={"member_id": "yj", "name": "유진2", "role": "개발"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "team_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text
        members = load_team(tmp_path / ".aoo" / "team.json")
        assert len(members) == 1  # 중복 추가되지 않음


class TestTeamMemberUpdateRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §1 — update-member(v1.1.2)가

    대시보드엔 없었다."""

    def test_update_renders_prefilled_edit_form(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민",
            roles=["분석"], github="@jm",
        )
        r = autopilot_client.get("/team")
        assert "/team/jm/update" in r.text
        assert 'value="정민"' in r.text
        assert 'value="@jm"' in r.text
        assert 'value="분석" checked' in r.text

    def test_update_changes_name_roles_github_synced(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])
        r = autopilot_client.post(
            "/team/jm/update",
            data={"name": "정민2", "role": ["분석", "PM"], "github": "@jm2", "synced": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/team"
        member = next(m for m in load_team(team_path) if m["id"] == "jm")
        assert member["name"] == "정민2"
        assert set(member["roles"]) == {"분석", "PM"}
        assert member["github"] == "@jm2"
        assert member["synced"] is True

    def test_unchecked_synced_checkbox_sets_false(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])
        autopilot_client.post(
            "/team/jm/update", data={"name": "정민", "role": ["분석"], "github": "", "synced": "1"},
        )
        r = autopilot_client.get("/team")
        assert 'name="synced" value="1" checked' in r.text  # 폼이 현재 값을 미리 채움

    def test_update_unknown_id_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 없는 id 수정이 조용히 무시돼

        사용자가 실패 여부를 알 수 없었다."""
        r = autopilot_client.post(
            "/team/nope/update", data={"name": "x", "role": [], "github": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "team_error" in r.headers["location"]


class TestTeamMemberRemoveRoute:
    def test_removes_member_and_redirects(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])
        r = autopilot_client.post("/team/jm/remove", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/team"
        assert load_team(team_path) == []

    def test_remove_unknown_id_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 없는 id 삭제가 조용히 무시돼

        사용자가 실패 여부를 알 수 없었다."""
        r = autopilot_client.post("/team/nope/remove", follow_redirects=False)
        assert r.status_code == 303
        assert "team_error" in r.headers["location"]

    def test_delete_button_rendered_for_each_member(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민", roles=["분석"]
        )
        r = autopilot_client.get("/team")
        assert "/team/jm/remove" in r.text
        assert "삭제" in r.text


class TestAutopilotApprovalsPage:
    def test_non_gating_checklist_items_render_without_blocking_style(self, autopilot_client):
        """gate_on_checklist=False인 pending 항목은 경고색(.blocking)을 받지 않는다."""
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="PORTFOLIO", kind="threshold_review",
            phase=7, title="임계값 재검토",
            checklist=[{"label": "1단계", "status": "pending"}],
            gate_on_checklist=False,
        )
        r = autopilot_client.get("/approvals")
        assert "임계값 재검토" in r.text
        assert 'class="blocking"' not in r.text

    def test_approvals_page_lists_pending(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="ST-014 SPEC 검토", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.get("/approvals")
        assert "ST-014 SPEC 검토" in r.text

    def test_approvals_page_separates_drafts(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="아직 초안", checklist=[{"label": "a", "status": "pending"}],
        )
        r = autopilot_client.get("/approvals")
        assert "아직 초안" in r.text
        assert "초안 — 아직 사람 큐에 안 올라옴" in r.text

    def test_post_decide_approves_and_redirects(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "pm-park", "rationale": "ok"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/approvals"

        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "approved"

    def test_decide_unknown_id_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 없는 id 결정이 조용히 큐로

        돌아가 사용자가 실패 여부를 알 수 없었다."""
        r = autopilot_client.post(
            "/approvals/nope/decide",
            data={"decision": "approved", "decided_by": "pm"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "action_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text

    def test_approved_item_disappears_from_pending_view(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="결정될 항목", checklist=[{"label": "a", "status": "ok"}],
        )
        autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "pm-park"},
        )
        r = autopilot_client.get("/approvals")
        assert "승인 대기 중인 항목이 없습니다" in r.text

    def test_decide_form_has_no_hardcoded_reviewer_field(self, autopilot_client):
        """회귀 테스트 — 예전엔 decided_by가 hidden input에 "local-reviewer"로

        고정돼 있어서, 대시보드로 누가 결정하든 전부 같은 사람으로 기록됐다
        (감사 추적이 사실상 무의미했고, 2인 승인은 이 상태로는 절대 못 채운다
        — 같은 문자열이라 서로 다른 승인자로 안 쳐준다). 이제 실제 입력칸이다.
        """
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.get("/approvals")
        assert 'value="local-reviewer"' not in r.text
        assert 'name="decided_by"' in r.text
        assert "required" in r.text

    def test_two_person_approval_stays_pending_after_one_decide(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="deploy",
            phase=8, title="배포 승인",
        )
        autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "lead-kim"},
        )
        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "pending"

        r = autopilot_client.get("/approvals")
        assert "배포 승인" in r.text
        assert "승인 1/2명" in r.text
        assert "lead-kim" in r.text

    def test_two_person_approval_finalizes_after_second_distinct_decider(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="deploy",
            phase=8, title="배포 승인",
        )
        autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "lead-kim"},
        )
        autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "sec-choi"},
        )
        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "approved"

        r = autopilot_client.get("/approvals")
        assert "승인 대기 중인 항목이 없습니다" in r.text

    def test_cancel_button_rendered_for_pending(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md 신규(§8) — approvals cancel(v1.1.3)이

        CLI에만 있고 대시보드엔 철회 버튼이 없었다."""
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.get("/approvals")
        assert "/cancel" in r.text
        assert "철회" in r.text

    def test_post_cancel_marks_cancelled_and_redirects(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        r = autopilot_client.post(
            f"/approvals/{approval['id']}/cancel",
            data={"reason": "더 이상 필요 없음"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/approvals"

        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "cancelled"
        assert updated[approval["id"]]["rationale"] == "더 이상 필요 없음"

    def test_cancelled_item_disappears_from_pending_view(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        autopilot_client.post(f"/approvals/{approval['id']}/cancel", data={})
        r = autopilot_client.get("/approvals")
        assert "승인 대기 중인 항목이 없습니다" in r.text

    def test_cancel_of_already_decided_approval_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 이미 결정된 항목 취소가 조용히

        큐로 리다이렉트돼 사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-014", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "ok"}],
        )
        autopilot_client.post(
            f"/approvals/{approval['id']}/decide",
            data={"decision": "approved", "decided_by": "pm"},
        )
        r = autopilot_client.post(
            f"/approvals/{approval['id']}/cancel", data={}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert "action_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text

        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "approved"  # 그대로 유지


class TestScanThresholdsRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §11 — `approvals scan-thresholds`가

    CLI 전용이었다."""

    def test_no_repeated_pattern_shows_note(self, autopilot_client):
        r = autopilot_client.post(
            "/approvals/scan-thresholds", data={"min_occurrences": 5},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "scan_note" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "no repeated exit-75 pattern found" in r2.text

    def test_repeated_pattern_opens_threshold_review(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        for i in range(5):
            record_gate_decision(
                decisions_path, result_file=f"r{i}.json", agent_version="v1",
                exit_code=75, verdict_level="ready", decision_ready=False,
                undecided_reason="CI straddles",
            )
        r = autopilot_client.post(
            "/approvals/scan-thresholds", data={"min_occurrences": 5},
            follow_redirects=False,
        )
        assert "opened" in r.headers["location"]
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert any(a.get("kind") == "threshold_review" for a in approvals)

    def test_scan_form_rendered_on_approvals_page(self, autopilot_client):
        r = autopilot_client.get("/approvals")
        assert "/approvals/scan-thresholds" in r.text
        assert "스캔 실행" in r.text


class TestApprovalsOpenRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §9 — 새 승인 요청을 여는 것 자체가

    대시보드엔 없었다(decide/cancel만 가능)."""

    def test_opens_approval_with_checklist_text(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "spec_review", "phase": 1,
                "title": "SPEC 검토", "checklist_text": "EARS 표기:ok\nGate 매핑:ok",
                "body_text": "",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/approvals"
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert len(approvals) == 1
        assert approvals[0]["status"] == "pending"
        assert approvals[0]["checklist"] == [
            {"label": "EARS 표기", "status": "ok"}, {"label": "Gate 매핑", "status": "ok"}
        ]

    def test_invalid_checklist_status_shows_error(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "spec_review", "phase": 1, "title": "t",
                "checklist_text": "라벨:okk", "body_text": "",
            },
            follow_redirects=False,
        )
        assert "open_error" in r.headers["location"]
        assert load_approvals(tmp_path / ".aoo" / "approvals.jsonl") == []

    def test_error_banner_rendered_on_approvals_page(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        r = autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "spec_review", "phase": 1, "title": "t",
                "checklist_text": "라벨:okk", "body_text": "",
            },
        )
        assert "invalid checklist status" in r.text

    def test_adr_review_auto_adds_model_tier_item(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "adr_review", "phase": 2, "title": "ADR",
                "checklist_text": "", "body_text": "",
            },
        )
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert any("모델 tier" in c["label"] for c in approvals[0]["checklist"])
        assert approvals[0]["status"] == "draft"  # 자동 추가 항목이 pending이라

    def test_no_checklist_gate_checkbox(self, autopilot_client):
        """Appendix M 발견 1 — scan-thresholds만 내부적으로 쓰던 옵션을

        사람도 쓸 수 있어야 한다(CLI의 --no-checklist-gate와 동등)."""
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "threshold_review", "phase": 7, "title": "t",
                "checklist_text": "할 일:pending", "body_text": "", "no_checklist_gate": "1",
            },
        )
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["status"] == "pending"
        assert approvals[0]["gate_on_checklist"] is False

    def test_missing_no_checklist_gate_defaults_to_gated(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        create_task(tmp_path / ".aoo" / "tasks", task_id="ST-001", title="t", platform="ac")
        autopilot_client.post(
            "/approvals",
            data={
                "task_id": "ST-001", "kind": "spec_review", "phase": 1, "title": "t",
                "checklist_text": "a:pending", "body_text": "",
            },
        )
        approvals = load_approvals(tmp_path / ".aoo" / "approvals.jsonl")
        assert approvals[0]["gate_on_checklist"] is True
        assert approvals[0]["status"] == "draft"


class TestApprovalsUpdateRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §9 — draft/pending 체크리스트를

    고치는 것이 대시보드엔 없었다(CLI approvals update 전용)."""

    def test_update_promotes_draft_to_pending(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-001", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "pending"}],
        )
        r = autopilot_client.post(
            f"/approvals/{approval['id']}/update",
            data={"label": ["a"], "status": ["ok"]},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/approvals"
        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "pending"
        assert updated[approval["id"]]["checklist"][0]["status"] == "ok"

    def test_update_unknown_label_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 라벨 불일치가 조용히 큐로

        돌아가 사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        approval = open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-001", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "pending"}],
        )
        r = autopilot_client.post(
            f"/approvals/{approval['id']}/update",
            data={"label": ["없는항목"], "status": ["ok"]},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "action_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text
        updated = {a["id"]: a for a in load_approvals(tmp_path / ".aoo" / "approvals.jsonl")}
        assert updated[approval["id"]]["status"] == "draft"  # 그대로 유지

    def test_update_form_rendered_for_draft_with_checklist(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        open_approval(
            tmp_path / ".aoo" / "approvals.jsonl", task_id="ST-001", kind="spec_review",
            phase=1, title="t", checklist=[{"label": "a", "status": "pending"}],
        )
        r = autopilot_client.get("/approvals")
        assert "/update" in r.text
        assert "체크리스트 반영" in r.text


class TestAutopilotOpsPage:
    def test_ops_page_renders_with_no_data(self, autopilot_client):
        r = autopilot_client.get("/ops")
        assert r.status_code == 200
        assert "활성 클레임 없음" in r.text
        assert "기록된 게이트 실행이 없음" in r.text
        assert "아직 결정된 승인이 없음" in r.text

    def test_ops_page_shows_rejection_rate(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        a = open_approval(
            approvals_path, task_id="ST-014", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, a["id"], decision="approved", decided_by="pm")

        r = autopilot_client.get("/ops")
        assert "반려율 0%" in r.text

    def test_ops_page_flags_rubber_stamp_risk_at_five_zero_rejections(self, autopilot_client):
        """5건 이상 결정됐는데 반려가 0건이면 부록 H.7 경고가 떠야 한다."""
        tmp_path = autopilot_client.tmp_path
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for i in range(5):
            a = open_approval(
                approvals_path, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                checklist=[{"label": "a", "status": "ok"}],
            )
            decide_approval(approvals_path, a["id"], decision="approved", decided_by="pm")

        r = autopilot_client.get("/ops")
        assert "반려율 0%" in r.text
        assert "고무도장" in r.text

    def test_ops_page_no_rubber_stamp_warning_below_five_decisions(self, autopilot_client):
        """4건까지는 반려 0건이어도 아직 경고를 띄우지 않는다(표본 부족)."""
        tmp_path = autopilot_client.tmp_path
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for i in range(4):
            a = open_approval(
                approvals_path, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                checklist=[{"label": "a", "status": "ok"}],
            )
            decide_approval(approvals_path, a["id"], decision="approved", decided_by="pm")

        r = autopilot_client.get("/ops")
        assert "반려율 0%" in r.text
        assert "고무도장" not in r.text

    def test_ops_page_notes_stuck_in_draft(self, autopilot_client):
        """LIMITS_T-5E1FD6.md L6 — draft에 갇힌 반려가 반려율에 안 잡히는

        사각지대를 표면화한다."""
        tmp_path = autopilot_client.tmp_path
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        a = open_approval(
            approvals_path, task_id="ST-1", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, a["id"], decision="approved", decided_by="pm")
        open_approval(
            approvals_path, task_id="ST-2", kind="spec_review", phase=1, title="stuck",
            checklist=[{"label": "a", "status": "pending"}],
        )

        r = autopilot_client.get("/ops")
        assert "draft 상태로 대기 중인 승인 1건" in r.text

    def test_ops_page_no_draft_note_when_nothing_stuck(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        a = open_approval(
            approvals_path, task_id="ST-1", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, a["id"], decision="approved", decided_by="pm")

        r = autopilot_client.get("/ops")
        assert "draft 상태로 대기 중인 승인" not in r.text


class TestPhasePolicyOpsRoutes:
    """docs/AUTOPILOT_IMPROVEMENTS.md §10 — phase policy set/show가 CLI

    전용이라 대시보드만 쓰는 사람은 정책이 걸려 있다는 사실 자체를 몰랐다."""

    def test_ops_page_shows_no_policy_by_default(self, autopilot_client):
        r = autopilot_client.get("/ops")
        assert "설정된 phase 정책 없음" in r.text

    def test_ops_page_lists_configured_policy(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")
        r = autopilot_client.get("/ops")
        assert "phase 2" in r.text
        assert "spec_review" in r.text

    def test_post_phase_policy_sets_and_redirects(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        r = autopilot_client.post(
            "/phase-policy", data={"phase": 2, "require_approval": "spec_review"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/ops"
        assert load_phase_policy(tmp_path / ".aoo" / "phase_policy.json") == {2: "spec_review"}

    def test_post_phase_policy_invalid_kind_shows_error_banner(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — 알 수 없는 kind가 조용히

        무시돼 사용자가 실패 여부를 알 수 없었다."""
        tmp_path = autopilot_client.tmp_path
        r = autopilot_client.post(
            "/phase-policy", data={"phase": 2, "require_approval": "bogus"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "policy_error" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner critical" in r2.text
        assert load_phase_policy(tmp_path / ".aoo" / "phase_policy.json") == {}

    def test_clear_route_removes_policy(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        policy_path = tmp_path / ".aoo" / "phase_policy.json"
        set_phase_policy(policy_path, 2, "spec_review")
        r = autopilot_client.post("/phase-policy/2/clear", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/ops"
        assert load_phase_policy(policy_path) == {}

    def test_clear_button_rendered_per_policy_row(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        set_phase_policy(tmp_path / ".aoo" / "phase_policy.json", 2, "spec_review")
        r = autopilot_client.get("/ops")
        assert "/phase-policy/2/clear" in r.text
        assert "해제" in r.text


class TestClaimsOpsRoutes:
    """docs/AUTOPILOT_IMPROVEMENTS.md §11 — claims add/release가 CLI 전용

    이었다(운영 현황 페이지는 조회만 가능했음)."""

    def test_post_claims_opens_claim(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        claims_path = tmp_path / ".aoo" / "claims.jsonl"
        r = autopilot_client.post(
            "/claims", data={"scope": "src/a/\nsrc/b/", "developer": "alice", "claim_id": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/ops"
        claims = load_active_claims(claims_path)
        assert len(claims) == 1
        assert claims[0]["developer"] == "alice"
        assert claims[0]["scope"] == ["src/a/", "src/b/"]

    def test_post_claims_auto_generates_id_when_blank(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        autopilot_client.post(
            "/claims", data={"scope": "src/a/", "developer": "alice", "claim_id": ""},
        )
        claims = load_active_claims(tmp_path / ".aoo" / "claims.jsonl")
        assert claims[0]["claim_id"].startswith("c-")

    def test_post_claims_overlap_warns_but_does_not_block(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        claims_path = tmp_path / ".aoo" / "claims.jsonl"
        autopilot_client.post(
            "/claims", data={"scope": "src/a/", "developer": "alice", "claim_id": ""},
        )
        r = autopilot_client.post(
            "/claims", data={"scope": "src/a/", "developer": "bob", "claim_id": ""},
            follow_redirects=False,
        )
        assert "claim_warning" in r.headers["location"]
        assert len(load_active_claims(claims_path)) == 2  # opened anyway

    def test_post_claims_release_route(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        claims_path = tmp_path / ".aoo" / "claims.jsonl"
        autopilot_client.post(
            "/claims", data={"scope": "src/a/", "developer": "alice", "claim_id": "c-fixed"},
        )
        r = autopilot_client.post("/claims/c-fixed/release", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/ops"
        assert load_active_claims(claims_path) == []

    def test_add_and_release_forms_rendered_on_ops_page(self, autopilot_client):
        r = autopilot_client.get("/ops")
        assert '/claims"' in r.text
        assert "클레임 열기" in r.text

    def test_release_unknown_claim_id_warns_but_still_releases(self, autopilot_client):
        """docs/AUTOPILOT_IMPROVEMENTS.md §12 — CLI의 `claims release`는

        claim_id가 활성 목록에 없으면 경고하는데(_cmd_claims_release), 대시보드
        버튼은 아무 검증 없이 조용히 append했다. 버튼 하나짜리 UI엔 --force에
        대응하는 자연스러운 확인 동작이 없으므로 막지 않고 경고만 한다."""
        r = autopilot_client.post("/claims/nope/release", follow_redirects=False)
        assert r.status_code == 303
        assert "claim_warning" in r.headers["location"]
        r2 = autopilot_client.get(r.headers["location"])
        assert "banner" in r2.text


class TestDecisionsRecordRoute:
    """docs/AUTOPILOT_IMPROVEMENTS.md §11 — 승인·과제·팀원은 대시보드로

    완결되는데 배포 결정 기록만 CLI(`decisions record`) 전용이었다."""

    def test_records_decision_with_sole_pending_run(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        gate_run = record_gate_decision(
            decisions_path, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        r = autopilot_client.post(
            "/decisions/record",
            data={
                "gate_run_id": "", "outcome": "overridden", "decided_by": "pm",
                "rationale": "ok",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/ops"
        entries = load_decisions(decisions_path)
        outcomes = [e for e in entries if e.get("kind") == "outcome"]
        assert len(outcomes) == 1
        assert outcomes[0]["gate_run_id"] == gate_run["id"]
        assert outcomes[0]["outcome"] == "overridden"

    def test_ambiguous_pending_runs_shows_error(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        record_gate_decision(
            decisions_path, result_file="a.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        record_gate_decision(
            decisions_path, result_file="b.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        r = autopilot_client.post(
            "/decisions/record",
            data={"gate_run_id": "", "outcome": "accepted", "decided_by": "pm"},
            follow_redirects=False,
        )
        assert "decision_error" in r.headers["location"]

    def test_explicit_gate_run_id_resolves_ambiguity(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        record_gate_decision(
            decisions_path, result_file="a.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        gate_run_b = record_gate_decision(
            decisions_path, result_file="b.json", agent_version="v1", exit_code=75,
            verdict_level="ready", decision_ready=False,
        )
        r = autopilot_client.post(
            "/decisions/record",
            data={
                "gate_run_id": gate_run_b["id"], "outcome": "accepted", "decided_by": "pm",
            },
            follow_redirects=False,
        )
        assert "decision_error" not in r.headers["location"]

    def test_no_pending_runs_shows_error(self, autopilot_client):
        r = autopilot_client.post(
            "/decisions/record",
            data={"gate_run_id": "", "outcome": "accepted", "decided_by": "pm"},
            follow_redirects=False,
        )
        assert "decision_error" in r.headers["location"]

    def test_record_form_rendered_when_pending_run_exists(self, autopilot_client):
        tmp_path = autopilot_client.tmp_path
        record_gate_decision(
            tmp_path / ".aoo" / "decisions.jsonl", result_file="r.json", agent_version="v1",
            exit_code=75, verdict_level="ready", decision_ready=False,
        )
        r = autopilot_client.get("/ops")
        assert "/decisions/record" in r.text
        assert "결정 기록" in r.text
