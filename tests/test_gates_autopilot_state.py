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
    PORTFOLIO_TASK_ID,
    add_team_member,
    compute_rejection_rate,
    create_task,
    decide_approval,
    detect_repeated_undecided,
    detect_skill_candidates,
    extract_needs_clarification,
    find_member,
    load_all_tasks,
    load_approvals,
    load_pending_approvals,
    load_task,
    load_team,
    members_by_role,
    open_approval,
    open_threshold_reviews,
    save_task,
    save_team,
    score_checklist,
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

    def test_create_task_rejects_path_traversal_id(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        with pytest.raises(ValueError, match="invalid task_id"):
            create_task(tasks_dir, task_id="../evil", title="t", platform="ac")
        # 상위 디렉토리에 파일이 생기지 않았는지 확인 — 거절만 하고 끝나야 한다.
        assert not (tmp_path / ".aoo" / "evil.json").exists()

    def test_create_task_rejects_id_with_slash(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        with pytest.raises(ValueError, match="invalid task_id"):
            create_task(tasks_dir, task_id="a/b", title="t", platform="ac")

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


class TestTransitionPhaseApprovalGate:
    """§9.5.4 순위1 — 옵트인 Phase 전이 게이트.

    ``required_approval_kind``를 안 주면 기존과 완전히 동일하게 동작한다
    (위 TestTransitionPhase가 이미 그걸 검증). 여기서는 게이트를 켰을 때의
    새 동작만 본다.
    """

    def test_no_gate_by_default(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        # approvals_path 없이, required_approval_kind 없이 — 기존과 동일
        updated = transition_phase(tasks_dir, "ST-001", new_phase=2)
        assert updated["current_phase"] == 2

    def test_gate_blocks_without_approved_approval(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        with pytest.raises(ValueError, match="no approved"):
            transition_phase(
                tasks_dir, "ST-001", new_phase=2,
                approvals_path=approvals_path, required_approval_kind="spec_review",
            )
        # 실패한 전이는 과제 상태를 바꾸지 않았어야 한다
        task = load_task(tasks_dir, "ST-001")
        assert task is not None
        assert task["current_phase"] == 0

    def test_gate_blocks_on_pending_approval(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        open_approval(
            approvals_path, task_id="ST-001", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "pending"}],
        )
        with pytest.raises(ValueError, match="no approved"):
            transition_phase(
                tasks_dir, "ST-001", new_phase=2,
                approvals_path=approvals_path, required_approval_kind="spec_review",
            )

    def test_gate_allows_after_approval(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        approval = open_approval(
            approvals_path, task_id="ST-001", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(
            approvals_path, approval["id"], decision="approved", decided_by="pm-park",
        )
        updated = transition_phase(
            tasks_dir, "ST-001", new_phase=2,
            approvals_path=approvals_path, required_approval_kind="spec_review",
        )
        assert updated["current_phase"] == 2

    def test_gate_ignores_approval_for_a_different_task(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        approval = open_approval(
            approvals_path, task_id="ST-999", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(approvals_path, approval["id"], decision="approved", decided_by="pm")
        with pytest.raises(ValueError, match="no approved"):
            transition_phase(
                tasks_dir, "ST-001", new_phase=2,
                approvals_path=approvals_path, required_approval_kind="spec_review",
            )

    def test_gate_requires_approvals_path_when_kind_given(self, tmp_path):
        tasks_dir = tmp_path / ".aoo" / "tasks"
        create_task(tasks_dir, task_id="ST-001", title="a", platform="ac")
        with pytest.raises(ValueError, match="approvals_path"):
            transition_phase(
                tasks_dir, "ST-001", new_phase=2, required_approval_kind="spec_review",
            )

    def test_missing_task_reports_task_not_found_even_with_gate_on(self, tmp_path):
        """회귀 테스트 — 실제로 있었던 버그.

        게이트를 켠 채로 존재하지 않는 task_id를 넘기면, 예전엔 승인 검사가
        먼저 돌아서 "no approved 'spec_review' approval found"라는 엉뚱한
        메시지가 나왔다(진짜 원인인 "과제 자체가 없음"을 가려버림). 과제
        존재 확인이 승인 게이트 검사보다 먼저 실행돼야 한다.
        """
        tasks_dir = tmp_path / ".aoo" / "tasks"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        with pytest.raises(ValueError, match="task not found") as exc_info:
            transition_phase(
                tasks_dir, "DOES-NOT-EXIST", new_phase=2,
                approvals_path=approvals_path, required_approval_kind="spec_review",
            )
        assert "approved" not in str(exc_info.value)


class TestComputeRejectionRate:
    """§9.5.4 순위4 — 원칙6 자가점검(부록 H.7 "반려 이력 0건" 신호)."""

    def test_no_decided_approvals_returns_none_rate(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        result = compute_rejection_rate(p)
        assert result["total"] == 0
        assert result["rejection_rate"] is None

    def test_all_approved_gives_zero_rate(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        for i in range(3):
            a = open_approval(
                p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                checklist=[{"label": "a", "status": "ok"}],
            )
            decide_approval(p, a["id"], decision="approved", decided_by="pm")
        result = compute_rejection_rate(p)
        assert result["total"] == 3
        assert result["rejection_rate"] == 0.0

    def test_mixed_decisions_computes_rate(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        a1 = open_approval(
            p, task_id="ST-1", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(p, a1["id"], decision="approved", decided_by="pm")
        a2 = open_approval(
            p, task_id="ST-2", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(p, a2["id"], decision="rejected", decided_by="pm", rationale="no")
        result = compute_rejection_rate(p)
        assert result["total"] == 2
        assert result["rejected_or_changes_requested"] == 1
        assert result["rejection_rate"] == 0.5

    def test_pending_and_draft_excluded_from_denominator(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        open_approval(
            p, task_id="ST-1", kind="spec_review", phase=1, title="still pending",
            checklist=[{"label": "a", "status": "ok"}],
        )
        result = compute_rejection_rate(p)
        assert result["total"] == 0

    def test_window_limits_to_most_recent(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        # 2건 approved, 1건 rejected(가장 최근) — window=1이면 rejected만 봐야 한다
        for i in range(2):
            a = open_approval(
                p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                checklist=[{"label": "a", "status": "ok"}],
            )
            decide_approval(p, a["id"], decision="approved", decided_by="pm")
        a_last = open_approval(
            p, task_id="ST-last", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decide_approval(p, a_last["id"], decision="rejected", decided_by="pm", rationale="no")

        result = compute_rejection_rate(p, window=1)
        assert result["total"] == 1
        assert result["rejection_rate"] == 1.0


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


class TestExtractNeedsClarification:
    def test_extracts_single_tag(self):
        text = "반품 요청은 [NEEDS CLARIFICATION: 환불 한도 초과 시 담당자] 확인 후 처리한다."
        assert extract_needs_clarification(text) == ["환불 한도 초과 시 담당자"]

    def test_extracts_multiple_tags(self):
        text = (
            "[NEEDS CLARIFICATION: 담당자 미지정] 그리고 "
            "[NEEDS CLARIFICATION: 분류 기준 미확정]"
        )
        assert extract_needs_clarification(text) == ["담당자 미지정", "분류 기준 미확정"]

    def test_no_tags_returns_empty(self):
        assert extract_needs_clarification("아무 태그도 없는 평범한 문장") == []

    def test_none_or_empty_returns_empty(self):
        assert extract_needs_clarification(None) == []
        assert extract_needs_clarification("") == []


class TestScoreChecklist:
    def test_all_ok_is_ready(self):
        score = score_checklist([{"label": "a", "status": "ok"}, {"label": "b", "status": "ok"}])
        assert score["ready_for_review"] is True
        assert score["ok_count"] == 2
        assert score["blocking"] == []

    def test_pending_item_blocks(self):
        score = score_checklist(
            [{"label": "a", "status": "ok"}, {"label": "b", "status": "pending"}]
        )
        assert score["ready_for_review"] is False
        assert len(score["blocking"]) == 1

    def test_missing_status_defaults_to_pending_and_blocks(self):
        score = score_checklist([{"label": "no status field"}])
        assert score["ready_for_review"] is False

    def test_empty_checklist_is_ready(self):
        score = score_checklist([])
        assert score["ready_for_review"] is True
        assert score["total"] == 0

    def test_none_checklist_is_ready(self):
        score = score_checklist(None)
        assert score["ready_for_review"] is True


class TestApprovalQueue:
    def test_open_approval_with_clean_checklist_is_pending(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="spec_review", phase=1, title="ST-014 SPEC 검토",
            checklist=[{"label": "EARS 표기", "status": "ok"}],
        )
        assert approval["status"] == "pending"
        assert approval["needs_clarification"] == []

    def test_open_approval_with_needs_clarification_stays_draft(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        body = "반품 요청은 [NEEDS CLARIFICATION: 환불 한도 담당자] 확인 후 처리한다."
        approval = open_approval(
            p, task_id="ST-014", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}], body_text=body,
        )
        assert approval["status"] == "draft"
        assert approval["needs_clarification"] == ["환불 한도 담당자"]

    def test_open_approval_with_blocking_checklist_stays_draft(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="adr_review", phase=2, title="t",
            checklist=[{"label": "a", "status": "pending"}],
        )
        assert approval["status"] == "draft"

    def test_gate_on_checklist_false_ignores_blocking_items(self, tmp_path):
        """체크리스트가 '밟을 절차 목록'일 땐 게이트로 안 쓴다(스캔 스모크테스트에서 발견)."""
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="threshold_review", phase=7, title="t",
            checklist=[
                {"label": "1단계", "status": "pending"}, {"label": "2단계", "status": "pending"}
            ],
            gate_on_checklist=False,
        )
        assert approval["status"] == "pending"
        assert approval["gate_on_checklist"] is False
        assert len(approval["checklist"]) == 2  # 표시용으로는 그대로 저장됨

    def test_gate_on_checklist_false_still_blocks_on_needs_clarification(self, tmp_path):
        """gate_on_checklist=False라도 NEEDS CLARIFICATION은 여전히 막는다."""
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="threshold_review", phase=7, title="t",
            checklist=[{"label": "1단계", "status": "pending"}],
            body_text="[NEEDS CLARIFICATION: 아직 불명확]",
            gate_on_checklist=False,
        )
        assert approval["status"] == "draft"

    def test_open_approval_rejects_invalid_kind(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        with pytest.raises(ValueError, match="kind"):
            open_approval(p, task_id="ST-014", kind="bogus", phase=1, title="t")

    def test_load_pending_approvals_excludes_draft(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        open_approval(p, task_id="ST-001", kind="spec_review", phase=1, title="ready",
                      checklist=[{"label": "a", "status": "ok"}])
        open_approval(p, task_id="ST-002", kind="spec_review", phase=1, title="not ready",
                      checklist=[{"label": "a", "status": "pending"}])
        pending = load_pending_approvals(p)
        assert len(pending) == 1
        assert pending[0]["task_id"] == "ST-001"

    def test_decide_approval_updates_status_and_appends_new_line(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="spec_review", phase=1, title="t",
            checklist=[{"label": "a", "status": "ok"}],
        )
        decided = decide_approval(
            p, approval["id"], decision="approved", decided_by="pm-park",
            rationale="looks good",
        )
        assert decided["status"] == "approved"
        assert decided["decided_by"] == "pm-park"

        # append-only: 두 줄이 쌓였는지 확인(이전 줄은 지우지 않음)
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        # load_approvals는 최신 상태만 반환
        latest = {a["id"]: a for a in load_approvals(p)}
        assert latest[approval["id"]]["status"] == "approved"

    def test_decide_approval_missing_id_raises(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        with pytest.raises(ValueError, match="not found"):
            decide_approval(p, "nope", decision="approved", decided_by="x")

    def test_decide_approval_invalid_decision_raises(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="spec_review", phase=1, title="t")
        with pytest.raises(ValueError, match="decision"):
            decide_approval(p, approval["id"], decision="maybe", decided_by="x")

    def test_decide_rejected_requires_rationale(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="spec_review", phase=1, title="t")
        with pytest.raises(ValueError, match="rationale"):
            decide_approval(p, approval["id"], decision="rejected", decided_by="x")

    def test_load_approvals_empty_when_file_missing(self, tmp_path):
        assert load_approvals(tmp_path / "nope.jsonl") == []


class TestMultiPersonApproval:
    """§6 M4 "리드+보안 2인 승인" — deploy/release_hold는 기본 2인 승인.

    전에는 decide_approval() 한 번 호출로 누구든 바로 approved까지 끝낼 수
    있었다 — deploy/release_hold처럼 설계서가 명시적으로 "2인 승인"을 요구하는
    kind에서도 마찬가지였다(실제 정책 구멍). required_approvals가 그 구멍을
    막는다.
    """

    def test_deploy_defaults_to_two_required_approvals(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="deploy", phase=8, title="배포 승인")
        assert approval["required_approvals"] == 2
        assert approval["approvals_recorded"] == []

    def test_release_hold_defaults_to_two_required_approvals(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="release_hold", phase=7, title="릴리스 보류 해제"
        )
        assert approval["required_approvals"] == 2

    def test_other_kinds_default_to_one_required_approval(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="spec_review", phase=1, title="t")
        assert approval["required_approvals"] == 1

    def test_single_approver_does_not_finalize_two_person_approval(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="deploy", phase=8, title="배포 승인")
        decided = decide_approval(
            p, approval["id"], decision="approved", decided_by="lead-kim"
        )
        # 아직 1/2명 — 큐에서 안 사라진다(status는 여전히 pending)
        assert decided["status"] == "pending"
        assert decided["decision"] is None
        assert [r["by"] for r in decided["approvals_recorded"]] == ["lead-kim"]
        assert decided in load_pending_approvals(p)

    def test_second_distinct_approver_finalizes(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="deploy", phase=8, title="배포 승인")
        decide_approval(p, approval["id"], decision="approved", decided_by="lead-kim")
        final = decide_approval(
            p, approval["id"], decision="approved", decided_by="sec-choi"
        )
        assert final["status"] == "approved"
        assert final["decision"] == "approved"
        assert final["decided_by"] == "sec-choi"
        assert [r["by"] for r in final["approvals_recorded"]] == ["lead-kim", "sec-choi"]
        assert final not in load_pending_approvals(p)

    def test_same_approver_twice_is_rejected(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="deploy", phase=8, title="배포 승인")
        decide_approval(p, approval["id"], decision="approved", decided_by="lead-kim")
        with pytest.raises(ValueError, match="already recorded"):
            decide_approval(p, approval["id"], decision="approved", decided_by="lead-kim")

    def test_single_rejection_finalizes_immediately_despite_required_two(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(p, task_id="ST-014", kind="deploy", phase=8, title="배포 승인")
        decide_approval(p, approval["id"], decision="approved", decided_by="lead-kim")
        rejected = decide_approval(
            p, approval["id"], decision="rejected", decided_by="sec-choi",
            rationale="보안 감사 미완료",
        )
        assert rejected["status"] == "rejected"

    def test_explicit_required_approvals_overrides_default(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        approval = open_approval(
            p, task_id="ST-014", kind="deploy", phase=8, title="긴급 배포",
            required_approvals=1,
        )
        assert approval["required_approvals"] == 1
        decided = decide_approval(p, approval["id"], decision="approved", decided_by="lead-kim")
        assert decided["status"] == "approved"

    def test_required_approvals_below_one_raises(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        with pytest.raises(ValueError, match="required_approvals"):
            open_approval(
                p, task_id="ST-014", kind="deploy", phase=8, title="t",
                required_approvals=0,
            )


class TestDetectSkillCandidates:
    def test_repeated_checklist_shape_is_a_candidate(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        checklist = [{"label": "EARS 표기", "status": "ok"}, {"label": "Gate 매핑", "status": "ok"}]
        for i in range(3):
            open_approval(
                p, task_id=f"ST-{i}", kind="spec_review", phase=1, title=f"t{i}",
                checklist=checklist,
            )
        candidates = detect_skill_candidates(p, min_occurrences=3)
        assert len(candidates) == 1
        assert candidates[0]["kind"] == "spec_review"
        assert candidates[0]["count"] == 3
        assert set(candidates[0]["labels"]) == {"EARS 표기", "Gate 매핑"}

    def test_below_threshold_is_not_a_candidate(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        checklist = [{"label": "a", "status": "ok"}]
        open_approval(
            p, task_id="ST-1", kind="spec_review", phase=1, title="t1", checklist=checklist
        )
        open_approval(
            p, task_id="ST-2", kind="spec_review", phase=1, title="t2", checklist=checklist
        )
        assert detect_skill_candidates(p, min_occurrences=3) == []

    def test_different_kinds_do_not_merge(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        checklist = [{"label": "a", "status": "ok"}]
        for i in range(3):
            open_approval(p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t",
                          checklist=checklist)
        for i in range(3):
            open_approval(p, task_id=f"AD-{i}", kind="adr_review", phase=2, title="t",
                          checklist=checklist)
        candidates = detect_skill_candidates(p, min_occurrences=3)
        assert len(candidates) == 2
        assert {c["kind"] for c in candidates} == {"spec_review", "adr_review"}

    def test_no_checklist_approvals_are_ignored(self, tmp_path):
        p = tmp_path / ".aoo" / "approvals.jsonl"
        for i in range(5):
            open_approval(p, task_id=f"ST-{i}", kind="spec_review", phase=1, title="t")
        assert detect_skill_candidates(p, min_occurrences=3) == []

    def test_empty_when_no_approvals_file(self, tmp_path):
        assert detect_skill_candidates(tmp_path / "nope.jsonl") == []


class TestDetectRepeatedUndecided:
    def _log(self, path, reason, exit_code=75):
        from agent_evaluator.rca.decision_ledger import record_gate_decision
        record_gate_decision(
            path, result_file="r.json", agent_version="v1", exit_code=exit_code,
            verdict_level="not_ready", decision_ready=(exit_code != 75),
            undecided_reason=reason if exit_code == 75 else None,
        )

    def test_five_repeats_of_same_reason_is_a_candidate(self, tmp_path):
        p = tmp_path / ".aoo" / "decisions.jsonl"
        for _ in range(5):
            self._log(p, "TCR pass-rate Wilson CI straddles the 85% target line")
        candidates = detect_repeated_undecided(p, min_occurrences=5)
        assert len(candidates) == 1
        assert candidates[0]["count"] == 5
        assert len(candidates[0]["gate_run_ids"]) == 5

    def test_four_repeats_is_not_yet_a_candidate(self, tmp_path):
        p = tmp_path / ".aoo" / "decisions.jsonl"
        for _ in range(4):
            self._log(p, "same reason")
        assert detect_repeated_undecided(p, min_occurrences=5) == []

    def test_normal_gate_runs_exit_0_are_ignored(self, tmp_path):
        p = tmp_path / ".aoo" / "decisions.jsonl"
        for _ in range(6):
            self._log(p, reason=None, exit_code=0)
        assert detect_repeated_undecided(p, min_occurrences=5) == []

    def test_different_reasons_do_not_merge(self, tmp_path):
        p = tmp_path / ".aoo" / "decisions.jsonl"
        for _ in range(5):
            self._log(p, "reason A")
        for _ in range(5):
            self._log(p, "reason B")
        candidates = detect_repeated_undecided(p, min_occurrences=5)
        assert len(candidates) == 2

    def test_empty_when_no_decisions_file(self, tmp_path):
        assert detect_repeated_undecided(tmp_path / "nope.jsonl") == []


class TestOpenThresholdReviews:
    def _log(self, decisions_path, reason):
        from agent_evaluator.rca.decision_ledger import record_gate_decision
        record_gate_decision(
            decisions_path, result_file="r.json", agent_version="v1", exit_code=75,
            verdict_level="not_ready", decision_ready=False, undecided_reason=reason,
        )

    def test_opens_one_review_per_repeated_reason(self, tmp_path):
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for _ in range(5):
            self._log(decisions_path, "임계값이 너무 타이트함")

        opened = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        assert len(opened) == 1
        assert opened[0]["kind"] == "threshold_review"
        assert opened[0]["task_id"] == PORTFOLIO_TASK_ID
        assert "임계값이 너무 타이트함" in opened[0]["title"]
        assert len(opened[0]["checklist"]) == 4  # 설계자/개발자/QA/조직 4단계
        # 4단계는 전부 "pending"으로 시작하는 할 일 목록이다 — 게이트로 쓰면 안 됨.
        # gate_on_checklist=False라 즉시 사람 큐에 뜬다(위 버그 수정 확인).
        assert opened[0]["status"] == "pending"

    def test_idempotent_does_not_duplicate_on_rerun(self, tmp_path):
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for _ in range(5):
            self._log(decisions_path, "반복 사유")

        first = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        second = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        assert len(first) == 1
        assert len(second) == 0  # 이미 pending으로 열려 있으니 또 안 만듦

        all_reviews = [
            a for a in load_approvals(approvals_path) if a.get("kind") == "threshold_review"
        ]
        assert len(all_reviews) == 1

    def test_reopens_after_previous_one_resolved(self, tmp_path):
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for _ in range(5):
            self._log(decisions_path, "반복 사유")

        first = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        decide_approval(
            approvals_path, first[0]["id"], decision="approved", decided_by="pm-park",
        )
        # 5회가 그대로 남아 있어도(로그는 append-only), 이전 건이 이미 결정됐으니 새로 하나 연다
        second = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        assert len(second) == 1

    def test_no_candidates_opens_nothing(self, tmp_path):
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        assert open_threshold_reviews(approvals_path, decisions_path) == []

    def test_idempotent_when_the_same_reason_repeats_again_while_still_open(self, tmp_path):
        """회귀 테스트 — 실제로 있었던 버그.

        제목에 반복 횟수(``{count}회 반복``)가 박혀 있어서, 카드가 열린 채로
        같은 사유가 한 번 더 쌓이면(5회→6회) count가 바뀌어 제목 전체
        문자열이 달라진다. 예전엔 그 전체 문자열로 중복을 판정해서, 이
        시나리오에서 중복 카드가 새로 열렸다(멱등성이 깨짐). 사유
        문자열이 제목에 포함돼 있는지로 바꿔 고쳤다.
        """
        decisions_path = tmp_path / ".aoo" / "decisions.jsonl"
        approvals_path = tmp_path / ".aoo" / "approvals.jsonl"
        for _ in range(5):
            self._log(decisions_path, "반복 사유")

        first = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        assert len(first) == 1
        assert "5회 반복" in first[0]["title"]

        # 카드가 아직 pending인 채로, 같은 사유가 한 번 더 발생(5회 -> 6회)
        self._log(decisions_path, "반복 사유")
        second = open_threshold_reviews(approvals_path, decisions_path, min_occurrences=5)
        assert second == []  # 새로 열리면 안 된다 — 버그가 고쳐졌다면 여기가 빈 리스트

        all_reviews = [
            a for a in load_approvals(approvals_path) if a.get("kind") == "threshold_review"
        ]
        assert len(all_reviews) == 1
