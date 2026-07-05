"""
tests/test_spec016_sqlite_storage_backend.py
================================================
SPEC-016: 영속성 저장소 옵션 — SQLite 백엔드 검증.

REQ-1: PerformanceMonitor(storage_backend="json"|"sqlite"), 잘못된 값은 ValueError.
REQ-2: task_id 기준 upsert 쓰기 — 신규/변경만 반영, 전체 재직렬화 없음.
REQ-3: PRAGMA journal_mode=WAL — 다중 writer 동시쓰기 안전성.
REQ-4: schema_version 테이블 — 버전 불일치 시 명확한 에러.
REQ-5: load_tasks_from_db() 읽기 헬퍼 — 왕복 직렬화 정합성.
REQ-6: 추가 pip 의존성 없음(stdlib sqlite3만 사용) — import 자체로 간접 검증.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.storage import (
    SCHEMA_VERSION,
    load_tasks_from_db,
    save_tasks_to_db,
    search_violations,
)
from agent_evaluator.storage.sqlite_backend import _connect


def _make_task(task_id: str, question: str = "q", response: str = "r"):
    return create_taskresult(
        task_id=task_id, question=question, response=response,
        ground_truth="r", execution_time=0.5, task_type="qa",
        extra={"source": "test"},
    )


class TestSaveAndLoadRoundtrip:
    def test_round_trip_preserves_fields(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = _make_task("t1", question="what is 2+2", response="4")
        save_tasks_to_db(db_path, [t1])

        loaded = load_tasks_from_db(db_path)
        assert len(loaded) == 1
        assert loaded[0].task_id == t1.task_id
        assert loaded[0].question == t1.question
        assert loaded[0].response == t1.response
        assert loaded[0].ground_truth == t1.ground_truth
        assert loaded[0].execution_time == t1.execution_time
        assert loaded[0].task_type == t1.task_type
        assert loaded[0].extra == t1.extra

    def test_multiple_tasks_preserve_order_by_timestamp(self, tmp_path):
        db_path = tmp_path / "test.db"
        tasks = [_make_task(f"t{i}") for i in range(5)]
        save_tasks_to_db(db_path, tasks)

        loaded = load_tasks_from_db(db_path)
        assert [t.task_id for t in loaded] == [f"t{i}" for i in range(5)]

    def test_empty_db_returns_empty_list(self, tmp_path):
        db_path = tmp_path / "empty.db"
        save_tasks_to_db(db_path, [])
        assert load_tasks_from_db(db_path) == []


class TestUpsertBehavior:
    def test_same_task_id_updates_not_duplicates(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = _make_task("t1", response="original")
        save_tasks_to_db(db_path, [t1])

        t1_updated = _make_task("t1", response="updated")
        save_tasks_to_db(db_path, [t1_updated])

        loaded = load_tasks_from_db(db_path)
        assert len(loaded) == 1
        assert loaded[0].response == "updated"

    def test_new_task_id_adds_without_touching_existing(self, tmp_path):
        db_path = tmp_path / "test.db"
        save_tasks_to_db(db_path, [_make_task("t1")])
        save_tasks_to_db(db_path, [_make_task("t2")])

        loaded = load_tasks_from_db(db_path)
        assert {t.task_id for t in loaded} == {"t1", "t2"}

    def test_second_save_only_reparses_incremental_set(self, tmp_path):
        """REQ-2: 두 번째 저장 호출이 첫 번째 저장분을 다시 쓰지 않고도 최종 상태가
        정확한지 확인 — 호출 인자로 넘긴 태스크 집합만 upsert된다."""
        db_path = tmp_path / "test.db"
        batch1 = [_make_task(f"t{i}") for i in range(50)]
        save_tasks_to_db(db_path, batch1)

        batch2 = [_make_task("t_new")]
        save_tasks_to_db(db_path, batch2)

        loaded = load_tasks_from_db(db_path)
        assert len(loaded) == 51


class TestSchemaVersion:
    def test_schema_version_table_populated(self, tmp_path):
        db_path = tmp_path / "test.db"
        save_tasks_to_db(db_path, [_make_task("t1")])

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        conn.close()
        assert row == (SCHEMA_VERSION,)

    def test_version_mismatch_raises_runtime_error(self, tmp_path):
        db_path = tmp_path / "test.db"
        save_tasks_to_db(db_path, [_make_task("t1")])

        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 999,))
        conn.commit()
        conn.close()

        with pytest.raises(RuntimeError, match="schema_version mismatch"):
            load_tasks_from_db(db_path)
        with pytest.raises(RuntimeError, match="schema_version mismatch"):
            save_tasks_to_db(db_path, [_make_task("t2")])


class TestWalModeConcurrency:
    def test_wal_mode_enabled(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = _connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"

    def test_concurrent_writers_both_persist(self, tmp_path):
        """REQ-3: 두 writer가 서로 다른 task_id로 동시에 써도 둘 다 유실 없이 저장된다."""
        db_path = tmp_path / "test.db"
        save_tasks_to_db(db_path, [])  # DB/스키마 미리 생성

        errors = []

        def _writer(prefix: str, count: int) -> None:
            try:
                save_tasks_to_db(db_path, [_make_task(f"{prefix}{i}") for i in range(count)])
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_writer, args=("a", 20))
        t2 = threading.Thread(target=_writer, args=("b", 20))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert errors == []
        loaded = load_tasks_from_db(db_path)
        task_ids = {t.task_id for t in loaded}
        assert len(task_ids) == 40
        assert all(f"a{i}" in task_ids for i in range(20))
        assert all(f"b{i}" in task_ids for i in range(20))


class TestPerformanceMonitorIntegration:
    def test_invalid_storage_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="storage_backend"):
            PerformanceMonitor(storage_backend="postgres")

    def test_default_storage_backend_is_json_unchanged(self, tmp_path):
        """REQ-1: storage_backend 기본값(json)은 기존 save_to_file() 동작과 100% 동일."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(_make_task("t1"))
        path = monitor.save_to_file("run1")
        assert path.endswith(".json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["tasks"]) == 1

    def test_sqlite_backend_save_to_file_produces_db(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path), storage_backend="sqlite")
        monitor.record_task(_make_task("t1"))
        monitor.record_task(_make_task("t2"))
        path = monitor.save_to_file("run1")

        assert path.endswith(".db")
        loaded = load_tasks_from_db(path)
        assert {t.task_id for t in loaded} == {"t1", "t2"}

    def test_sqlite_backend_incremental_save_upserts(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path), storage_backend="sqlite")
        monitor.record_task(_make_task("t1"))
        path1 = monitor.save_to_file("run1")

        monitor.record_task(_make_task("t2"))
        path2 = monitor.save_to_file("run1")

        assert path1 == path2
        loaded = load_tasks_from_db(path2)
        assert {t.task_id for t in loaded} == {"t1", "t2"}


class TestViolationSearchIndexing:
    """SPEC-024 REQ-2: violation_search(FTS5) additive 확장."""

    def _task_with_extra(self, task_id: str, extra: dict):
        return create_taskresult(
            task_id=task_id, question="q", response="r",
            ground_truth="r", execution_time=0.5, task_type="qa",
            extra=extra,
        )

    def test_pre_existing_db_without_fts5_table_migrates_cleanly(self, tmp_path):
        """violation_search 테이블 없이 만들어진(REQ-2 이전) DB를 새 코드로 열어도 에러 없다."""
        from agent_evaluator.storage.sqlite_backend import (
            _CREATE_SCHEMA_VERSION_TABLE,
            _CREATE_TASKS_TABLE,
        )

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(_CREATE_SCHEMA_VERSION_TABLE)
        conn.execute(_CREATE_TASKS_TABLE)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.commit()
        conn.close()

        loaded = load_tasks_from_db(db_path)  # 에러 없이 열려야 한다
        assert loaded == []

        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "violation_search" in tables

    def test_task_with_violation_is_indexed_and_searchable(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-1", {
            "tool_parameter_safety": {
                "safety_score": 0.75, "dangerous_calls": ["bash"],
                "violations": ["dangerous_pattern:bash:rm_shell_command"],
                "checked_calls": 1, "violation_count": 1,
            },
        })
        save_tasks_to_db(db_path, [t1])

        conn = sqlite3.connect(str(db_path))
        hits = conn.execute(
            "SELECT task_id FROM violation_search WHERE violation_search MATCH ?", ("bash",)
        ).fetchall()
        conn.close()
        assert hits == [("session-1",)]

    def test_task_without_violation_is_not_indexed(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-clean", {
            "scope": {"in_scope": True, "violations": [], "violation_tools": [],
                      "excess_calls": 0, "unique_tools": [], "scope_score": 1.0},
        })
        save_tasks_to_db(db_path, [t1])

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT task_id FROM violation_search").fetchall()
        conn.close()
        assert rows == []

    def test_task_without_extra_is_not_indexed(self, tmp_path):
        """extra=None(기본값)인 일반 태스크는 violation_search에 아무것도 남기지 않는다."""
        db_path = tmp_path / "test.db"
        save_tasks_to_db(db_path, [_make_task("t1")])

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT task_id FROM violation_search").fetchall()
        conn.close()
        assert rows == []

    def test_re_saving_resolved_violation_removes_search_entry(self, tmp_path):
        """위반이 있던 task_id를 위반 없는 상태로 재저장하면 검색 색인에서도 빠진다(upsert)."""
        db_path = tmp_path / "test.db"
        violating = self._task_with_extra("session-1", {
            "scope": {"in_scope": False, "violations": ["forbidden:webfetch"],
                      "violation_tools": ["webfetch"], "excess_calls": 0,
                      "unique_tools": ["webfetch"], "scope_score": 0.8},
        })
        save_tasks_to_db(db_path, [violating])

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("SELECT task_id FROM violation_search").fetchall() == [("session-1",)]
        conn.close()

        resolved = self._task_with_extra("session-1", {
            "scope": {"in_scope": True, "violations": [], "violation_tools": [],
                      "excess_calls": 0, "unique_tools": [], "scope_score": 1.0},
        })
        save_tasks_to_db(db_path, [resolved])

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT task_id FROM violation_search").fetchall()
        conn.close()
        assert rows == []

    def test_multiple_violation_categories_all_appear_in_summary(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-multi", {
            "loop_detection": {
                "detected": True,
                "detected_loops": [
                    {"loop_type": "consecutive_repeat", "loop_at_step": 2, "loop_tool": "bash"},
                ],
            },
            "tool_authorization": {
                "unauthorized_calls": 1, "restricted_calls": 1, "dangerous_param_calls": 0,
                "total_violations": 2, "total_calls": 3, "compliance_rate": 0.3333,
            },
        })
        save_tasks_to_db(db_path, [t1])

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT summary FROM violation_search WHERE task_id = ?", ("session-multi",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert "loop_detection" in row[0]
        assert "tool_authorization" in row[0]


class TestSearchViolations:
    """SPEC-024 REQ-3: search_violations() 조회 API."""

    def _task_with_extra(self, task_id: str, extra: dict):
        return create_taskresult(
            task_id=task_id, question="q", response="r",
            ground_truth="r", execution_time=0.5, task_type="tool_use",
            extra=extra,
        )

    def test_matching_keyword_returns_result(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-1", {
            "tool_parameter_safety": {
                "safety_score": 0.75, "dangerous_calls": ["bash"],
                "violations": ["dangerous_pattern:bash:rm_shell_command"],
                "checked_calls": 1, "violation_count": 1,
            },
        })
        save_tasks_to_db(db_path, [t1])

        results = search_violations(db_path, "bash")
        assert len(results) == 1
        assert results[0]["task_id"] == "session-1"
        assert "bash" in results[0]["summary"]
        assert results[0]["task_type"] == "tool_use"
        assert "timestamp" in results[0]
        assert "success" in results[0]

    def test_unrelated_keyword_returns_empty(self, tmp_path):
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-1", {
            "tool_parameter_safety": {
                "safety_score": 0.75, "dangerous_calls": ["bash"],
                "violations": ["dangerous_pattern:bash:rm_shell_command"],
                "checked_calls": 1, "violation_count": 1,
            },
        })
        save_tasks_to_db(db_path, [t1])

        assert search_violations(db_path, "kubernetes") == []

    def test_clean_task_never_appears_in_results(self, tmp_path):
        db_path = tmp_path / "test.db"
        clean = self._task_with_extra("session-clean", {
            "scope": {"in_scope": True, "violations": [], "violation_tools": [],
                      "excess_calls": 0, "unique_tools": [], "scope_score": 1.0},
        })
        save_tasks_to_db(db_path, [clean])

        assert search_violations(db_path, "scope") == []

    def test_limit_caps_result_count(self, tmp_path):
        db_path = tmp_path / "test.db"
        tasks = [
            self._task_with_extra(f"session-{i}", {
                "tool_parameter_safety": {
                    "safety_score": 0.75, "dangerous_calls": ["bash"],
                    "violations": [f"dangerous_pattern:bash:pattern{i}"],
                    "checked_calls": 1, "violation_count": 1,
                },
            })
            for i in range(5)
        ]
        save_tasks_to_db(db_path, tasks)

        assert len(search_violations(db_path, "bash", limit=2)) == 2
        assert len(search_violations(db_path, "bash", limit=10)) == 5

    def test_malformed_fts5_query_falls_back_to_phrase_search(self, tmp_path):
        """따옴표·괄호 등 FTS5 문법에 어긋나는 자유 형식 입력도 에러 없이 처리된다."""
        db_path = tmp_path / "test.db"
        t1 = self._task_with_extra("session-1", {
            "tool_parameter_safety": {
                "safety_score": 0.75, "dangerous_calls": ["bash"],
                "violations": ["dangerous_pattern:bash:rm_shell_command"],
                "checked_calls": 1, "violation_count": 1,
            },
        })
        save_tasks_to_db(db_path, [t1])

        # 괄호는 FTS5 MATCH 문법에서 특수 문자 — 에러 없이 처리돼야 한다.
        results = search_violations(db_path, "rm (blocked)")
        assert results == []  # 구 전체가 요약과 일치하지 않으므로 결과 없음, 에러가 아님이 핵심

    def test_empty_db_returns_empty_list(self, tmp_path):
        db_path = tmp_path / "empty.db"
        save_tasks_to_db(db_path, [])
        assert search_violations(db_path, "anything") == []
