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

SPEC-024 REQ-2: ``violation_search``(FTS5 가상 테이블) — ``LiveGuardrail.to_task_extra()``
(SPEC-019)가 채운 Gate B/E 판정 상세(``loop_detection``/``deadlock``/``scope``/
``tool_parameter_safety``/``tool_authorization``/``privilege_escalation``/``tool_chain_attack``)를
사람이 읽을 수 있는 한 줄 요약으로 색인한다. ``SCHEMA_VERSION``을 올리지 않는 순수 additive
확장이다 — 기존 ``tasks`` 테이블·기존 DB 파일과 완전히 호환된다.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

# SPEC-024 REQ-2: task_id는 UNINDEXED(FTS5 전문 색인 대상 아님, 조인 키로만 사용) —
# summary만 MATCH 전문 검색 대상이 된다.
_CREATE_VIOLATION_SEARCH_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS violation_search USING fts5(task_id UNINDEXED, summary)
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """(REQ-4) 스키마를 초기화하거나, 기존 DB의 버전이 다르면 명확한 에러를 낸다."""
    conn.execute(_CREATE_SCHEMA_VERSION_TABLE)
    conn.execute(_CREATE_TASKS_TABLE)
    conn.execute(_CREATE_VIOLATION_SEARCH_TABLE)  # SPEC-024 REQ-2: additive, 버전 증가 없음
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


def _summarize_violations(extra: Dict[str, Any]) -> Optional[str]:
    """(SPEC-024 REQ-2) Gate B/E 판정 상세를 검색 가능한 한 줄 요약으로 변환한다.

    점수가 아니라 "무엇이 왜 위반됐는지"를 담는다 — SPEC-019가 확립한 TypeScript
    ``summarizeGuardrailResult()``와 동일한 원칙(점수만으로는 다음 세션이 "무엇을
    피해야 하는지" 알 수 없다). 실제 위반이 하나도 없으면 ``None``을 반환한다 —
    ``violation_search``는 위반 이력 검색용이므로, "위반 없음" 태스크까지 색인하면
    검색 신호 대비 잡음만 늘어난다.

    Args:
        extra: ``TaskResult.extra``(또는 ``LiveGuardrail.to_task_extra()`` 반환값).

    Returns:
        위반이 있으면 " | "로 구분된 한 줄 요약, 없으면 ``None``.
    """
    parts: List[str] = []

    _loop = extra.get("loop_detection")
    if isinstance(_loop, dict) and _loop.get("detected"):
        _loops = _loop.get("detected_loops") or []
        _tools = ", ".join(
            f"{d.get('loop_type')}:{d.get('loop_tool')}" for d in _loops if isinstance(d, dict)
        )
        parts.append(f"loop_detection: {_tools}" if _tools else "loop_detection: detected")

    _deadlock = extra.get("deadlock")
    if isinstance(_deadlock, dict) and _deadlock.get("detected"):
        parts.append(f"deadlock: {_deadlock.get('deadlock_type') or 'unknown'}")

    _scope = extra.get("scope")
    if isinstance(_scope, dict) and _scope.get("violations"):
        parts.append(f"scope: {', '.join(_scope['violations'])}")

    _tps = extra.get("tool_parameter_safety")
    if isinstance(_tps, dict) and _tps.get("violations"):
        parts.append(f"tool_parameter_safety: {', '.join(_tps['violations'])}")

    _ta = extra.get("tool_authorization")
    if isinstance(_ta, dict) and _ta.get("total_violations"):
        parts.append(
            f"tool_authorization: {_ta['total_violations']} violations "
            f"(unauthorized={_ta.get('unauthorized_calls', 0)}, "
            f"restricted={_ta.get('restricted_calls', 0)}, "
            f"dangerous_params={_ta.get('dangerous_param_calls', 0)})"
        )

    _pe = extra.get("privilege_escalation")
    if isinstance(_pe, dict) and _pe.get("escalation_detected"):
        parts.append(
            f"privilege_escalation: {_pe.get('initial_privilege')} -> {_pe.get('max_privilege')}"
        )

    _tc = extra.get("tool_chain_attack")
    if isinstance(_tc, dict) and _tc.get("is_suspicious_chain"):
        _patterns = _tc.get("attack_patterns_detected") or []
        parts.append(
            f"tool_chain_attack: {'; '.join(_patterns)}"
            if _patterns else "tool_chain_attack: suspicious"
        )

    return " | ".join(parts) if parts else None


def save_tasks_to_db(path: Union[str, Path], tasks: List[TaskResult]) -> None:
    """(REQ-2) 태스크 리스트를 ``task_id`` 기준 upsert로 SQLite에 기록한다.

    이미 저장된 ``task_id``는 최신 값으로 갱신되고, 신규 ``task_id``는 추가된다 —
    JSON 파일 방식처럼 매번 전체를 재직렬화하지 않는다.

    SPEC-024 REQ-2: ``task.extra``에 Gate B/E 위반이 있으면 ``violation_search``
    (FTS5)에도 함께 upsert한다. FTS5 가상 테이블은 ``ON CONFLICT`` upsert를
    지원하지 않으므로, 기존 ``task_id`` 행을 먼저 지우고 위반이 있을 때만
    다시 삽입한다(위반이 해소된 태스크는 재저장 시 검색 색인에서 자동으로 빠진다).

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
            conn.execute("DELETE FROM violation_search WHERE task_id = ?", (t.task_id,))
            _summary = _summarize_violations(t.extra or {})
            if _summary is not None:
                conn.execute(
                    "INSERT INTO violation_search (task_id, summary) VALUES (?, ?)",
                    (t.task_id, _summary),
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


def search_violations(
    path: Union[str, Path], query: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """(SPEC-024 REQ-3) ``violation_search``(FTS5)에서 Gate B/E 위반 이력을 검색한다.

    ``save_tasks_to_db()``가 위반이 있는 태스크에 한해 채워둔 요약(REQ-2)을
    전문 검색한다. 자유 형식 자연어 질의를 그대로 받는다 — FTS5 쿼리 문법(따옴표·
    괄호 등)에 어긋나는 입력은 통째로 하나의 구(phrase)로 취급해 재시도한다(REQ-4의
    MCP 서버가 LLM이 생성한 임의의 질의 문자열을 그대로 전달하기 때문에, 호출자가
    FTS5 문법을 알아야 한다는 요구를 두지 않기 위함).

    Args:
        path: SQLite DB 파일 경로(``save_tasks_to_db()``로 이미 기록된 파일).
        query: 검색 질의(자연어 키워드).
        limit: 최대 반환 건수.

    Returns:
        관련도(BM25) 순으로 정렬된
        ``{"task_id", "summary", "timestamp", "task_type", "success"}`` 리스트.
        일치하는 항목이 없으면 빈 리스트.
    """
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        _sql = """
            SELECT v.task_id, v.summary, t.timestamp, t.task_type, t.success
            FROM violation_search AS v
            JOIN tasks AS t ON t.task_id = v.task_id
            WHERE violation_search MATCH ?
            ORDER BY bm25(violation_search)
            LIMIT ?
        """
        try:
            rows = conn.execute(_sql, (query, limit)).fetchall()
        except sqlite3.OperationalError:
            # FTS5 쿼리 문법(따옴표·괄호 등)에 어긋나는 자유 형식 입력 — 통째로 하나의
            # 구(phrase)로 감싸 재시도한다. 이중 따옴표는 FTS5 규칙대로 이스케이프.
            _phrase = '"' + query.replace('"', '""') + '"'
            rows = conn.execute(_sql, (_phrase, limit)).fetchall()
    finally:
        conn.close()
    return [
        {
            "task_id": r[0],
            "summary": r[1],
            "timestamp": r[2],
            "task_type": r[3],
            "success": bool(r[4]),
        }
        for r in rows
    ]
