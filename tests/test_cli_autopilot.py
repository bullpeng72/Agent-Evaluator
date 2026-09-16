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

from agent_evaluator.cli.autopilot import (
    _cmd_autopilot_add_member,
    _cmd_autopilot_dashboard,
    _cmd_autopilot_doctor,
    _cmd_autopilot_install,
    _cmd_autopilot_new_task,
    cmd_autopilot,
)
from agent_evaluator.gates.autopilot_state import (
    add_team_member,
    load_all_tasks,
    load_team,
)


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


class TestAutopilotAppRealData:
    """create_autopilot_app()이 실제 .aoo/ 파일을 읽는지(M0 완료조건) 확인한다."""

    def test_dashboard_app_serves_real_tasks_and_team(self, tmp_path):
        fastapi_testclient = None
        try:
            from fastapi.testclient import TestClient
            fastapi_testclient = TestClient
        except ImportError:
            import pytest
            pytest.skip("fastapi[serve] extra not installed")

        from agent_evaluator.cli.autopilot import _cmd_autopilot_install
        from agent_evaluator.gates.autopilot_state import add_team_member, create_task
        from agent_evaluator.serve.autopilot_app import create_autopilot_app

        _cmd_autopilot_install(_ns(platform="ac", root=str(tmp_path)))
        create_task(
            tmp_path / ".aoo" / "tasks", task_id="ST-014", title="반품정책", platform="ac"
        )
        add_team_member(
            tmp_path / ".aoo" / "team.json", member_id="jm", name="정민", roles=["분석"]
        )

        app = create_autopilot_app(root=tmp_path)
        client = fastapi_testclient(app)

        r = client.get("/api/tasks")
        assert r.status_code == 200
        assert r.json()[0]["task_id"] == "ST-014"

        r = client.get("/api/team")
        assert r.json()[0]["name"] == "정민"

        r = client.get("/")
        assert r.status_code == 200
        assert "ST-014" in r.text
        assert "정민" in r.text
