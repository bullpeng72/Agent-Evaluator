"""
tests/test_gates_autopilot_state.py
====================================
Harness Autopilot M0 — .aoo/tasks/<task_id>.json · .aoo/team.json 읽기/쓰기
(agent_evaluator.gates.autopilot_state).

새 채점 로직은 없으므로, 여기서는 ① 스키마가 설계서(§4.1·§4.5·§4.6) 그대로
쓰이는지, ② 다중 과제/다중 팀원이 서로 안 섞이는지, ③ 잘못된 입력을 올바르게
거부하는지만 확인한다.
"""
from __future__ import annotations

import json

import pytest

from agent_evaluator.gates.autopilot_state import (
    PHASE_LABELS,
    add_team_member,
    create_task,
    find_member,
    load_all_tasks,
    load_task,
    load_team,
    members_by_role,
    save_task,
    save_team,
    task_path,
    transition_phase,
)


class TestTaskCreateLoad:
    def test_create_task_starts_at_phase_0(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        task = create_task(tasks_dir, task_id="ST-001", title="테스트 과제", platform="ac")
        assert task["current_phase"] == 0
        assert task["phase_label"] == PHASE_LABELS[0]
        assert task["platform"] == "AC"
        assert task["blocking_on"] == []
        assert len(task["phase_history"]) == 1
        assert task["phase_history"][0]["exited_at"] is None

    def test_create_task_persists_to_disk(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t", platform="aoo")
        path = task_path(tasks_dir, "ST-001")
        assert path.is_file()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["platform"] == "AOO"

    def test_create_task_rejects_invalid_platform(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        with pytest.raises(ValueError, match="platform"):
            create_task(tasks_dir, task_id="ST-001", title="t", platform="gcp")

    def test_create_task_rejects_duplicate_id(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="t1", platform="ac")
        with pytest.raises(ValueError, match="already exists"):
            create_task(tasks_dir, task_id="ST-001", title="t2", platform="ac")

    def test_load_task_missing_returns_none(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        assert load_task(tasks_dir, "nope") is None

    def test_load_task_corrupt_json_returns_none(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "bad.json").write_text("{not json", encoding="utf-8")
        assert load_task(tasks_dir, "bad") is None


class TestLoadAllTasks:
    def test_multiple_tasks_do_not_mix(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        create_task(tasks_dir, task_id="ST-002", title="b", platform="aoo")
        create_task(tasks_dir, task_id="ST-003", title="c", platform="ac")

        tasks = load_all_tasks(tasks_dir)
        assert len(tasks) == 3
        ids = {t["task_id"] for t in tasks}
        assert ids == {"ST-001", "ST-002", "ST-003"}
        platforms = {t["task_id"]: t["platform"] for t in tasks}
        assert platforms["ST-002"] == "AOO"

    def test_missing_dir_returns_empty_list(self, tmp_path):
        assert load_all_tasks(tmp_path / "nope") == []

    def test_skips_corrupt_files_without_raising(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        (tasks_dir / "corrupt.json").write_text("{{{", encoding="utf-8")
        tasks = load_all_tasks(tasks_dir)
        assert len(tasks) == 1


class TestTransitionPhase:
    def test_transition_closes_previous_and_opens_new(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        updated = transition_phase(
            tasks_dir, "ST-001", new_phase=1, mode="hitl", approved_by="pm-park"
        )

        assert updated["current_phase"] == 1
        assert updated["phase_label"] == PHASE_LABELS[1]
        history = updated["phase_history"]
        assert len(history) == 2
        assert history[0]["exited_at"] is not None
        assert history[1]["phase"] == 1
        assert history[1]["approved_by"] == "pm-park"
        assert history[1]["exited_at"] is None

    def test_transition_missing_task_raises(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        with pytest.raises(ValueError, match="not found"):
            transition_phase(tasks_dir, "nope", new_phase=1)

    def test_save_task_requires_task_id(self, tmp_path):
        with pytest.raises(ValueError, match="task_id"):
            save_task(tmp_path / ".aoo" / "tasks", {"title": "no id"})


class TestTeamRegistry:
    def test_add_member_defaults_unsynced(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        member = add_team_member(team_path, member_id="yj", name="유진", roles=["설계"])
        assert member["synced"] is False
        assert member["id"] == "yj"

    def test_add_member_rejects_unknown_role(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        with pytest.raises(ValueError, match="unknown role"):
            add_team_member(team_path, member_id="x", name="X", roles=["해커"])

    def test_add_member_rejects_duplicate_id(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="yj", name="유진", roles=["설계"])
        with pytest.raises(ValueError, match="already exists"):
            add_team_member(team_path, member_id="yj", name="유진2", roles=["개발"])

    def test_multiple_members_persist_independently(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="sa", name="수아", roles=["개발"])
        add_team_member(team_path, member_id="th", name="태호", roles=["개발"])
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])

        members = load_team(team_path)
        assert len(members) == 3
        assert {m["id"] for m in members} == {"sa", "th", "jm"}

    def test_members_by_role_filters_correctly(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="sa", name="수아", roles=["개발"])
        add_team_member(team_path, member_id="th", name="태호", roles=["개발"])
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])

        devs = members_by_role(team_path, "개발")
        assert {m["id"] for m in devs} == {"sa", "th"}
        analysts = members_by_role(team_path, "분석")
        assert {m["id"] for m in analysts} == {"jm"}

    def test_find_member_by_id_or_name(self, tmp_path):
        team_path = tmp_path / ".aoo" / "team.json"
        add_team_member(team_path, member_id="jm", name="정민", roles=["분석"])
        assert find_member(team_path, "jm") is not None
        assert find_member(team_path, "정민") is not None
        assert find_member(team_path, "없음") is None

    def test_load_team_missing_file_returns_empty(self, tmp_path):
        assert load_team(tmp_path / "nope.json") == []

    def test_load_team_corrupt_json_returns_empty(self, tmp_path):
        team_path = tmp_path / "team.json"
        team_path.write_text("{not json", encoding="utf-8")
        assert load_team(team_path) == []

    def test_save_team_round_trips(self, tmp_path):
        team_path = tmp_path / "team.json"
        save_team(team_path, [{"id": "a", "name": "A", "roles": ["개발"]}])
        assert load_team(team_path)[0]["name"] == "A"
