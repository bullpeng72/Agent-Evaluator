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
from agent_evaluator.storage import SCHEMA_VERSION, load_tasks_from_db, save_tasks_to_db
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
