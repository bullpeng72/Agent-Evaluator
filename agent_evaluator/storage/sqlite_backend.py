"""
agent_evaluator.storage.sqlite_backend
=========================================
SPEC-016: SQLite 영속성 백엔드 구현.

- REQ-2: task_id 기준 upsert 쓰기 — 매 저장마다 전체 히스토리를 재직렬화하는 JSON 파일
  방식과 달리, 신규/변경된 태스크만 기록한다.
- REQ-3: ``PRAGMA journal_mode=WAL``로 다중 프로세스 동시쓰기를 SQLite 자체의 파일 락으로
  안전하게 직렬화한다.
- REQ-4: ``schema_version`` 테이블로 스키마 버전을 추적 — 버전 불일치 시 조용한 데이터
  손상 대신 명확한 에러를 낸다.
- REQ-5: ``load_tasks_from_db()`` 읽기 헬퍼.
- REQ-6: 추가 pip 의존성 없이 stdlib ``sqlite3``만 사용한다.

스키마 설계: ``TaskResult.to_dict()``/``TaskResult.from_dict()``(``core/trackers/base.py``)가
이미 전체 필드를 JSON-safe dict로 왕복 직렬화하므로, 필드마다 개별 컬럼을 만드는 대신
쿼리 가능성을 위한 최소 스칼라 컬럼(task_id, task_type, success, timestamp)과 전체 상태를
담는 단일 ``data_json`` 컬럼으로 구성한다 — ``TaskResult``에 향후 필드가 추가돼도 이
스키마 자체는 변경할 필요가 없다(스키마 마이그레이션 부담 최소화).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Union

from agent_evaluator.core.trackers.base import TaskResult

SCHEMA_VERSION = 1

_CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    success INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    data_json TEXT NOT NULL
)
"""

_CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
)
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """(REQ-4) 스키마를 초기화하거나, 기존 DB의 버전이 다르면 명확한 에러를 낸다."""
    conn.execute(_CREATE_SCHEMA_VERSION_TABLE)
    conn.execute(_CREATE_TASKS_TABLE)
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif row[0] != SCHEMA_VERSION:
        raise RuntimeError(
            f"agent_evaluator SQLite storage: schema_version mismatch — "
            f"DB has version {row[0]}, this SDK expects version {SCHEMA_VERSION}. "
            "자동 마이그레이션은 지원되지 않는다(SPEC-016 Non-Goals) — 새 파일로 저장하거나 "
            "호환되는 SDK 버전을 사용할 것."
        )


def _connect(path: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    # REQ-3: WAL 모드 — 다중 프로세스가 동시에 같은 .db 파일에 쓸 때 SQLite 자체의
    # 파일 락으로 안전하게 직렬화되도록 한다.
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def save_tasks_to_db(path: Union[str, Path], tasks: List[TaskResult]) -> None:
    """(REQ-2) 태스크 리스트를 ``task_id`` 기준 upsert로 SQLite에 기록한다.

    이미 저장된 ``task_id``는 최신 값으로 갱신되고, 신규 ``task_id``는 추가된다 —
    JSON 파일 방식처럼 매번 전체를 재직렬화하지 않는다.

    Args:
        path: SQLite DB 파일 경로.
        tasks: 저장할 ``TaskResult`` 리스트.
    """
    conn = _connect(path)
    try:
        for t in tasks:
            data = t.to_dict()
            conn.execute(
                """
                INSERT INTO tasks (task_id, task_type, success, timestamp, data_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type=excluded.task_type,
                    success=excluded.success,
                    timestamp=excluded.timestamp,
                    data_json=excluded.data_json
                """,
                (
                    t.task_id,
                    t.task_type,
                    int(t.success),
                    data.get("timestamp"),
                    json.dumps(data, ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def load_tasks_from_db(path: Union[str, Path]) -> List[TaskResult]:
    """(REQ-5) SQLite DB 파일에서 저장된 ``TaskResult`` 리스트를 재구성한다.

    Args:
        path: SQLite DB 파일 경로.

    Returns:
        ``timestamp`` 오름차순으로 정렬된 ``TaskResult`` 리스트.
    """
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT data_json FROM tasks ORDER BY timestamp"
        ).fetchall()
    finally:
        conn.close()
    return [TaskResult.from_dict(json.loads(r[0])) for r in rows]
