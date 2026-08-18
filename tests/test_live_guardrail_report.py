"""
tests/test_live_guardrail_report.py
======================================
SPEC-019 REQ-6 배치 편입 검증: agent_evaluator.integrations.live_guardrail_report.

핵심 확인 대상: 여러 OpenCode 세션(각각 독립 프로세스를 흉내낸 별도 record_and_save()
호출)이 같은 output_dir/파일에 누적될 때, sqlite 백엔드(기본값)는 이전 세션 기록을
잃지 않는지(SPEC-016 upsert), JSON 백엔드는 단일 세션 전제하에서만 안전하다는 걸
실제로 보여주는지.
"""
import io
import json
from unittest.mock import MagicMock, patch

from agent_evaluator.integrations.live_guardrail_report import record_and_save, run
from agent_evaluator.storage.sqlite_backend import load_tasks_from_db


class TestRecordAndSaveValidation:
    def test_missing_task_id_or_extra_returns_error(self, tmp_path):
        outstream = io.StringIO()
        run(io.StringIO(json.dumps({"extra": {}})), outstream)
        result = json.loads(outstream.getvalue())
        assert result["ok"] is False
        assert "error" in result

    def test_empty_stdin_returns_error(self):
        outstream = io.StringIO()
        run(io.StringIO(""), outstream)
        result = json.loads(outstream.getvalue())
        assert result["ok"] is False


class TestSqliteAccumulationAcrossProcesses:
    """sqlite(기본값)는 서로 다른 프로세스 호출이 같은 파일에 upsert되어 누적돼야 한다."""

    def test_two_sessions_both_persist(self, tmp_path):
        output_dir = str(tmp_path / "opencode_results")

        result1 = record_and_save({
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": output_dir,
            "save_filename": "opencode_sessions",
        })
        assert result1["ok"] is True
        db_path = result1["saved_to"]
        assert db_path.endswith(".db")

        result2 = record_and_save({
            "task_id": "session-2",
            "extra": {"scope": {"in_scope": False, "scope_score": 0.5, "violations": ["forbidden:x"]}},
            "output_dir": output_dir,
            "save_filename": "opencode_sessions",
        })
        assert result2["ok"] is True
        assert result2["saved_to"] == db_path

        tasks = load_tasks_from_db(db_path)
        task_ids = {t.task_id for t in tasks}
        assert task_ids == {"session-1", "session-2"}

    def test_gate_b_score_reflects_extra(self, tmp_path):
        result = record_and_save({
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": str(tmp_path / "out"),
        })
        assert result["ok"] is True
        assert result["gate_b_score"] == 1.0
        assert result["gate_e_score"] is None  # extra에 Gate E 키가 없으므로


class TestExecutionTimePassthrough:
    """SPEC-028 REQ-2: OpenCode 플러그인이 실측 세션 경과 시간을 execution_time으로
    보내면 TaskResult.execution_time에 그대로 반영돼야 한다(Gate D 성능 지표용)."""

    def test_explicit_execution_time_reflected(self, tmp_path):
        result = record_and_save({
            "task_id": "session-1",
            "extra": {},
            "execution_time": 42.5,
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["tasks"][0]["execution_time"] == 42.5

    def test_missing_execution_time_defaults_to_zero(self, tmp_path):
        """execution_time 미지정(구형 플러그인 등) — 하위 호환으로 기존처럼 0.0."""
        result = record_and_save({
            "task_id": "session-1",
            "extra": {},
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["tasks"][0]["execution_time"] == 0.0


class TestJsonBackendSingleSession:
    def test_json_backend_writes_file(self, tmp_path):
        result = record_and_save({
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
            "save_filename": "opencode_sessions",
        })
        assert result["ok"] is True
        assert result["saved_to"].endswith(".json")
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["task_id"] == "session-1"


class TestStdioProtocol:
    def test_run_reads_stdin_writes_stdout(self, tmp_path):
        payload = {
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": str(tmp_path / "out"),
        }
        outstream = io.StringIO()
        run(io.StringIO(json.dumps(payload)), outstream)
        result = json.loads(outstream.getvalue())
        assert result["ok"] is True
        assert result["gate_b_score"] == 1.0


class TestToolCallsExtraction:
    """SPEC-028 REQ-1: extra 안의 tool_calls를 꺼내 TaskResult.tool_calls로 옮기고,
    나머지 Gate B/E 파생 지표는 그대로 extra에 남긴다 — Gate G(ToolCallAnalyzer)가
    실제 도구 사용 데이터를 읽을 수 있게 하기 위함."""

    def test_tool_calls_moved_to_top_level_field(self, tmp_path):
        tool_calls = [
            {"name": "bash", "arguments": {"command": "ls"}},
            {"name": "edit", "arguments": {"file": "a.py"}},
        ]
        result = record_and_save({
            "task_id": "session-1",
            "extra": {
                "scope": {"in_scope": True, "scope_score": 1.0},
                "tool_calls": tool_calls,
            },
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        saved_task = data["tasks"][0]
        assert saved_task["tool_calls"] == tool_calls
        assert "tool_calls" not in saved_task["extra"]
        assert saved_task["extra"]["scope"] == {"in_scope": True, "scope_score": 1.0}

    def test_gate_g_tool_coverage_populated_when_tool_calls_present(self, tmp_path):
        """이전에는 tool_calls가 TaskResult에 전혀 전달되지 않아 Gate G의
        tool_coverage가 항상 None(not tested)이었다 — 이제 실제 값이 나오는지 확인."""
        result = record_and_save({
            "task_id": "session-1",
            "extra": {
                "tool_calls": [
                    {"name": "bash", "arguments": {}},
                    {"name": "edit", "arguments": {}},
                ],
            },
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        gate_g = data["extra_metrics"]["harness_groups"].get("G") or {}
        assert gate_g.get("score") is not None

    def test_missing_tool_calls_key_backward_compatible(self, tmp_path):
        """tool_calls 키가 없는(SPEC-028 이전 형식) 페이로드도 에러 없이 그대로 동작."""
        result = record_and_save({
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": str(tmp_path / "out"),
            "storage_backend": "json",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["tasks"][0]["tool_calls"] == []

    def test_original_payload_extra_not_mutated(self, tmp_path):
        """extra를 복사해서 쓰므로, 호출자가 넘긴 원본 payload["extra"]는 변형되지 않는다."""
        original_extra = {
            "scope": {"in_scope": True}, "tool_calls": [{"name": "bash", "arguments": {}}],
        }
        payload = {
            "task_id": "session-1", "extra": original_extra, "output_dir": str(tmp_path / "out"),
        }
        record_and_save(payload)
        assert "tool_calls" in original_extra  # pop이 원본을 변형하지 않았어야 함
        assert payload["extra"] is original_extra

    def test_broken_pipe_on_final_write_does_not_raise(self, tmp_path):
        """실제 OpenCode 라이브 세션(2026-07-03)에서 재현된 시나리오: 호출자가 응답을
        기다리지 않고 먼저 종료해 stdout 파이프가 닫힌다. record_and_save()는 이미
        끝난 뒤이므로(배치 리포트는 저장됨), 응답 write/flush의 BrokenPipeError는
        조용히 삼켜야 한다 — run()이 예외를 전파하면 안 된다."""

        class _BrokenPipeStream(io.StringIO):
            def write(self, *_args, **_kwargs):
                raise BrokenPipeError(32, "Broken pipe")

        payload = {
            "task_id": "session-1",
            "extra": {"scope": {"in_scope": True, "scope_score": 1.0}},
            "output_dir": str(tmp_path / "out"),
        }
        run(io.StringIO(json.dumps(payload)), _BrokenPipeStream())  # raise 없이 반환돼야 함


class TestSuccessOptInSignal:
    """SPEC-028 REQ-3: success가 주어지면 실제 완료 판정을 반영하고, 미지정 시
    completion_score를 중립값(0.5)으로 둬 placeholder 텍스트 기반 오도를 막는다.

    *설계안 대비 수정*: 원 설계는 미지정 시 completion_score/accuracy_score를 None으로
    override할 계획이었으나, TaskResult.__post_init__이 0.0<=completion_score<=1.0을
    강제해 None을 주면 TypeError로 즉시 크래시한다(직접 실행해 확인, Non-Goals/
    구현 노트 참고). completion_score는 Gate A TCR 컴포넌트에 무조건 반영되므로
    "not tested"로 만드는 것 자체가 아키텍처적으로 불가능하다."""

    def _save_and_load(self, tmp_path, payload_extra, save_filename="s"):
        payload = {"task_id": "t1", "storage_backend": "json", "save_filename": save_filename,
                   "output_dir": str(tmp_path / "out"), **payload_extra}
        result = record_and_save(payload)
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            return json.load(f)["tasks"][0]

    def test_success_true_sets_perfect_scores(self, tmp_path):
        task = self._save_and_load(tmp_path, {"extra": {}, "success": True})
        assert task["completion_score"] == 1.0
        assert task["accuracy_score"] == 1.0
        assert task["success"] is True

    def test_success_false_sets_zero_scores(self, tmp_path):
        task = self._save_and_load(tmp_path, {"extra": {}, "success": False}, save_filename="s2")
        assert task["completion_score"] == 0.0
        assert task["accuracy_score"] == 0.0
        assert task["success"] is False

    def test_missing_success_uses_neutral_completion_score(self, tmp_path):
        """success 미지정(기존 호출부 전부 포함, 하위 호환) — 크래시 없이 중립값 0.5."""
        task = self._save_and_load(tmp_path, {"extra": {}}, save_filename="s3")
        assert task["completion_score"] == 0.5
        assert task["accuracy_score"] == 0.0  # ground_truth 없음 — 기존 자연 계산값 그대로
        assert task["success"] is True  # has_error 없음 — 기존 기본값 그대로(변경 없음)

    def test_neutral_score_independent_of_placeholder_text(self, tmp_path):
        """핵심 회귀 확인 — success 없이는 completion_score가 question/response
        placeholder 텍스트 내용과 무관하게 항상 동일해야 한다(더 이상 텍스트
        길이 휴리스티에 좌우되지 않는다는 증거)."""
        task_a = self._save_and_load(
            tmp_path,
            {"extra": {}, "question": "<opencode session>", "response": "<opencode session>"},
            save_filename="sa",
        )
        task_b = self._save_and_load(
            tmp_path,
            {
                "extra": {},
                "question": "a much longer completely different placeholder text here",
                "response": "another very different long placeholder response text indeed",
            },
            save_filename="sb",
        )
        assert task_a["completion_score"] == task_b["completion_score"] == 0.5

    def test_gate_a_score_does_not_crash_and_reflects_neutral_tcr(self, tmp_path):
        """Gate A는 completion_score>=1.0 여부로 TCR을 집계하므로(0.5는 미달),
        success 미지정 세션은 "완료" 아닌 "부분 완료"로 집계돼야 한다(크래시 없음)."""
        result = record_and_save({
            "task_id": "t1", "extra": {}, "output_dir": str(tmp_path / "out"),
            "storage_backend": "json", "save_filename": "gatea",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        gate_a = data["extra_metrics"]["harness_groups"].get("A") or {}
        assert gate_a.get("score") is not None  # 크래시 없이 계산됨


class TestAgentVersionAutoTagging:
    """SPEC-028 REQ-5: agent_version 기본값 "auto"(SPEC-027)를 PerformanceMonitor에
    연결 — 커밋 없이 반복 실행되는 로컬 세션도 group_by/pairwise 비교에서 자동으로
    구분되게 한다."""

    def _fake_run(self, clean_diff: bool = True):
        def _run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n")
            if "diff" in cmd:
                stdout = "" if clean_diff else "diff --git a/f.py b/f.py\n+changed\n"
                return MagicMock(returncode=0, stdout=stdout)
            raise AssertionError(f"unexpected git subprocess call: {cmd}")
        return _run

    def test_default_resolves_via_spec027_auto_tagging(self, tmp_path):
        with patch("subprocess.run", side_effect=self._fake_run(clean_diff=True)):
            result = record_and_save({
                "task_id": "t1", "extra": {}, "output_dir": str(tmp_path / "out"),
                "storage_backend": "json", "save_filename": "s1",
            })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["extra_metrics"]["lineage"]["agent_version"] == "abc123de"

    def test_explicit_override_used_verbatim(self, tmp_path):
        with patch("subprocess.run", side_effect=self._fake_run(clean_diff=True)):
            result = record_and_save({
                "task_id": "t1", "extra": {}, "agent_version": "my-custom-tag",
                "output_dir": str(tmp_path / "out"),
                "storage_backend": "json", "save_filename": "s2",
            })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["extra_metrics"]["lineage"]["agent_version"] == "my-custom-tag"

    def test_dirty_state_produces_dirty_suffixed_tag(self, tmp_path):
        with patch("subprocess.run", side_effect=self._fake_run(clean_diff=False)):
            result = record_and_save({
                "task_id": "t1", "extra": {}, "output_dir": str(tmp_path / "out"),
                "storage_backend": "json", "save_filename": "s3",
            })
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["extra_metrics"]["lineage"]["agent_version"].startswith("abc123de-dirty-")


class TestIterationNotePassthrough:
    """SPEC-029: 페이로드의 iteration_note를 PerformanceMonitor에 그대로 전달한다."""

    def test_note_stored_in_lineage(self, tmp_path):
        result = record_and_save({
            "task_id": "t1", "extra": {}, "iteration_note": "루프 탐지 threshold를 6으로 완화",
            "output_dir": str(tmp_path / "out"), "storage_backend": "json", "save_filename": "n1",
        })
        assert result["ok"] is True
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["extra_metrics"]["lineage"]["iteration_note"] == "루프 탐지 threshold를 6으로 완화"

    def test_omitted_defaults_to_none(self, tmp_path):
        result = record_and_save({
            "task_id": "t1", "extra": {},
            "output_dir": str(tmp_path / "out"), "storage_backend": "json", "save_filename": "n2",
        })
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["extra_metrics"]["lineage"]["iteration_note"] is None


class TestBlockedAttemptAlert:
    """Harness Method Ch13 §13.2 HITL 대응 — AGENT_EVALUATOR_ALERT_WEBHOOK_URL이
    설정돼 있고 blocked_attempts가 있으면 세션당 Slack 알림 1건을 보낸다."""

    _BLOCKED = [{"tool_name": "bash", "gate": "B", "reason": "dangerous tool parameters"}]

    def test_no_webhook_env_no_dispatch_attempted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENT_EVALUATOR_ALERT_WEBHOOK_URL", raising=False)
        with patch("agent_evaluator.alerts.handlers.SlackHandler.send") as mock_send:
            result = record_and_save({
                "task_id": "t1", "extra": {"blocked_attempts": self._BLOCKED},
                "output_dir": str(tmp_path / "out"), "storage_backend": "json",
                "save_filename": "n3",
            })
        assert result["ok"] is True
        mock_send.assert_not_called()

    def test_webhook_env_but_no_blocked_attempts_no_dispatch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVALUATOR_ALERT_WEBHOOK_URL", "https://hooks.slack.test/x")
        with patch("agent_evaluator.alerts.handlers.SlackHandler.send") as mock_send:
            result = record_and_save({
                "task_id": "t1", "extra": {},
                "output_dir": str(tmp_path / "out"), "storage_backend": "json",
                "save_filename": "n4",
            })
        assert result["ok"] is True
        mock_send.assert_not_called()

    def test_webhook_env_and_blocked_attempts_dispatches_one_alert(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVALUATOR_ALERT_WEBHOOK_URL", "https://hooks.slack.test/x")
        with patch("agent_evaluator.alerts.handlers.SlackHandler.send") as mock_send:
            result = record_and_save({
                "task_id": "sess-42", "extra": {"blocked_attempts": self._BLOCKED},
                "output_dir": str(tmp_path / "out"), "storage_backend": "json",
                "save_filename": "n5",
            })
        assert result["ok"] is True
        mock_send.assert_called_once()
        event = mock_send.call_args[0][0]
        assert event.severity == "critical"
        assert "sess-42" in event.message
        assert "bash" in event.message
        assert event.value == 1

    def test_dispatch_failure_does_not_break_record_and_save(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_EVALUATOR_ALERT_WEBHOOK_URL", "https://hooks.slack.test/x")
        with patch(
            "agent_evaluator.alerts.handlers.SlackHandler.send",
            side_effect=OSError("network unreachable"),
        ):
            result = record_and_save({
                "task_id": "t1", "extra": {"blocked_attempts": self._BLOCKED},
                "output_dir": str(tmp_path / "out"), "storage_backend": "json",
                "save_filename": "n6",
            })
        assert result["ok"] is True  # 알림 발송 실패가 세션 리포트 저장을 막지 않는다

    def test_blocked_attempts_stays_in_extra_metrics(self, tmp_path, monkeypatch):
        """blocked_attempts는 pop되지 않고 tool_calls처럼 그대로 extra에 남아야 한다
        (sqlite_backend.save_tasks_to_db()가 blocked_violations 테이블에 반영, SPEC-030)."""
        monkeypatch.delenv("AGENT_EVALUATOR_ALERT_WEBHOOK_URL", raising=False)
        result = record_and_save({
            "task_id": "t1", "extra": {"blocked_attempts": self._BLOCKED},
            "output_dir": str(tmp_path / "out"), "storage_backend": "json", "save_filename": "n7",
        })
        with open(result["saved_to"]) as f:
            data = json.load(f)
        assert data["tasks"][0]["extra"]["blocked_attempts"] == self._BLOCKED
