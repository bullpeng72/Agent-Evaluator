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
