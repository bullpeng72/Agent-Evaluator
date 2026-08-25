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
from typing import Any, Union

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

# SPEC-030 REQ-3: 완전히 차단돼(record_tool_call()이 호출되지 않아) tasks/violation_search
# 어디에도 남지 않는 시도의 감사 이력. reason만 MATCH 전문 검색 대상 — 나머지는 UNINDEXED.
_CREATE_BLOCKED_VIOLATIONS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS blocked_violations USING fts5(
    task_id UNINDEXED, tool_name UNINDEXED, gate UNINDEXED, reason
)
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """(REQ-4) 스키마를 초기화하거나, 기존 DB의 버전이 다르면 명확한 에러를 낸다."""
    conn.execute(_CREATE_SCHEMA_VERSION_TABLE)
    conn.execute(_CREATE_TASKS_TABLE)
    conn.execute(_CREATE_VIOLATION_SEARCH_TABLE)  # SPEC-024 REQ-2: additive, 버전 증가 없음
    conn.execute(_CREATE_BLOCKED_VIOLATIONS_TABLE)  # SPEC-030 REQ-3: additive, 버전 증가 없음
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


def _fmt_loop_detection(data: dict[str, Any]) -> str | None:
    if not data.get("detected"):
        return None
    _loops = data.get("detected_loops") or []
    _tools = ", ".join(
        f"{d.get('loop_type')}:{d.get('loop_tool')}" for d in _loops if isinstance(d, dict)
    )
    return f"loop_detection: {_tools}" if _tools else "loop_detection: detected"


def _fmt_deadlock(data: dict[str, Any]) -> str | None:
    if not data.get("detected"):
        return None
    return f"deadlock: {data.get('deadlock_type') or 'unknown'}"


def _fmt_scope(data: dict[str, Any]) -> str | None:
    if not data.get("violations"):
        return None
    return f"scope: {', '.join(data['violations'])}"


def _fmt_tool_parameter_safety(data: dict[str, Any]) -> str | None:
    if not data.get("violations"):
        return None
    return f"tool_parameter_safety: {', '.join(data['violations'])}"


def _fmt_tool_authorization(data: dict[str, Any]) -> str | None:
    if not data.get("total_violations"):
        return None
    return (
        f"tool_authorization: {data['total_violations']} violations "
        f"(unauthorized={data.get('unauthorized_calls', 0)}, "
        f"restricted={data.get('restricted_calls', 0)}, "
        f"dangerous_params={data.get('dangerous_param_calls', 0)})"
    )


def _fmt_privilege_escalation(data: dict[str, Any]) -> str | None:
    if not data.get("escalation_detected"):
        return None
    return f"privilege_escalation: {data.get('initial_privilege')} -> {data.get('max_privilege')}"


def _fmt_tool_chain_attack(data: dict[str, Any]) -> str | None:
    if not data.get("is_suspicious_chain"):
        return None
    _patterns = data.get("attack_patterns_detected") or []
    if _patterns:
        return f"tool_chain_attack: {'; '.join(_patterns)}"
    return "tool_chain_attack: suspicious"


# VIOLATION_TYPES(ontology/metric_registry.py)의 각 유형에 대응하는 포맷터. 두 목록의
# 키 집합이 어긋나면(새 유형 추가를 한쪽에서만 하면) get_summary_for_type()에서 즉시
# KeyError로 드러난다 — 이전에는 이 함수 안에 정적으로만 존재해 빠뜨려도 예외 없이
# 조용히 색인이 누락됐다.
_VIOLATION_FORMATTERS: dict[str, Any] = {
    "loop_detection": _fmt_loop_detection,
    "deadlock": _fmt_deadlock,
    "scope": _fmt_scope,
    "tool_parameter_safety": _fmt_tool_parameter_safety,
    "tool_authorization": _fmt_tool_authorization,
    "privilege_escalation": _fmt_privilege_escalation,
    "tool_chain_attack": _fmt_tool_chain_attack,
}


def _summarize_violations(extra: dict[str, Any]) -> str | None:
    """(SPEC-024 REQ-2) Gate B/E 판정 상세를 검색 가능한 한 줄 요약으로 변환한다.

    점수가 아니라 "무엇이 왜 위반됐는지"를 담는다 — SPEC-019가 확립한 TypeScript
    ``summarizeGuardrailResult()``와 동일한 원칙(점수만으로는 다음 세션이 "무엇을
    피해야 하는지" 알 수 없다). 실제 위반이 하나도 없으면 ``None``을 반환한다 —
    ``violation_search``는 위반 이력 검색용이므로, "위반 없음" 태스크까지 색인하면
    검색 신호 대비 잡음만 늘어난다.

    검사 대상 유형 목록은 ``ontology.metric_registry.VIOLATION_TYPES``(Phase 2)에서
    가져온다 — 새 Gate B/E 체크가 추가되면 그 레지스트리를 갱신하는 게 첫 단계가 되도록,
    이 함수가 직접 유형을 하드코딩하지 않는다.

    Args:
        extra: ``TaskResult.extra``(또는 ``LiveGuardrail.to_task_extra()`` 반환값).

    Returns:
        위반이 있으면 " | "로 구분된 한 줄 요약, 없으면 ``None``.
    """
    from agent_evaluator.ontology.metric_registry import VIOLATION_TYPES

    parts: list[str] = []
    for _vtype in VIOLATION_TYPES:
        _data = extra.get(_vtype)
        if isinstance(_data, dict):
            _formatted = _VIOLATION_FORMATTERS[_vtype](_data)
            if _formatted:
                parts.append(_formatted)
    return " | ".join(parts) if parts else None


def save_tasks_to_db(path: Union[str, Path], tasks: list[TaskResult]) -> None:
    """(REQ-2) 태스크 리스트를 ``task_id`` 기준 upsert로 SQLite에 기록한다.

    이미 저장된 ``task_id``는 최신 값으로 갱신되고, 신규 ``task_id``는 추가된다 —
    JSON 파일 방식처럼 매번 전체를 재직렬화하지 않는다.

    SPEC-024 REQ-2: ``task.extra``에 Gate B/E 위반이 있으면 ``violation_search``
    (FTS5)에도 함께 upsert한다. FTS5 가상 테이블은 ``ON CONFLICT`` upsert를
    지원하지 않으므로, 기존 ``task_id`` 행을 먼저 지우고 위반이 있을 때만
    다시 삽입한다(위반이 해소된 태스크는 재저장 시 검색 색인에서 자동으로 빠진다).

    SPEC-030 REQ-3: ``task.extra["blocked_attempts"]``(``LiveGuardrail.snapshot()``이
    항상 채우는 키, SPEC-030 REQ-2)를 같은 delete-then-insert 패턴으로
    ``blocked_violations``에 반영한다 — 완전히 차단돼 ``tasks``/``violation_search``
    어디에도 원본 시도가 남지 않는 이력을 별도로 감사 가능하게 한다. 항목당
    1행(여러 건을 하나로 합치지 않음 — 검색 관련도를 항목별로 유지하기 위함).

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
            conn.execute("DELETE FROM blocked_violations WHERE task_id = ?", (t.task_id,))
            for _attempt in (t.extra or {}).get("blocked_attempts") or []:
                conn.execute(
                    "INSERT INTO blocked_violations (task_id, tool_name, gate, reason) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        t.task_id,
                        _attempt.get("tool_name"),
                        _attempt.get("gate"),
                        _attempt.get("reason") or "",
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def load_tasks_from_db(path: Union[str, Path]) -> list[TaskResult]:
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


def _match_with_phrase_fallback(
    conn: sqlite3.Connection, sql: str, query: str, limit: int
) -> list[Any]:
    """FTS5 MATCH 쿼리를 실행하고, 쿼리 문법 오류 시 통째로 구(phrase)로 감싸 재시도한다.

    ``search_violations()``의 두 하위 쿼리(관찰 모드/차단 이력)가 공유하는 재시도 로직 —
    자유 형식 자연어 질의를 그대로 받아야 하는 요구(REQ-3 원 설계)를 두 테이블 모두에
    동일하게 적용하기 위해 분리했다.
    """
    try:
        return conn.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        _phrase = '"' + query.replace('"', '""') + '"'
        return conn.execute(sql, (_phrase, limit)).fetchall()


def search_violations(
    path: Union[str, Path], query: str, limit: int = 10, include_blocked: bool = False,
) -> list[dict[str, Any]]:
    """(SPEC-024 REQ-3) ``violation_search``(FTS5)에서 Gate B/E 위반 이력을 검색한다.

    ``save_tasks_to_db()``가 위반이 있는 태스크에 한해 채워둔 요약(REQ-2)을
    전문 검색한다. 자유 형식 자연어 질의를 그대로 받는다 — FTS5 쿼리 문법(따옴표·
    괄호 등)에 어긋나는 입력은 통째로 하나의 구(phrase)로 취급해 재시도한다(REQ-4의
    MCP 서버가 LLM이 생성한 임의의 질의 문자열을 그대로 전달하기 때문에, 호출자가
    FTS5 문법을 알아야 한다는 요구를 두지 않기 위함).

    SPEC-030 REQ-4: ``include_blocked=True``면 ``blocked_violations``(완전히 차단돼
    ``violation_search``에는 전혀 남지 않는 이력, SPEC-030 REQ-3)도 함께 검색해
    이어붙인다. 두 FTS5 가상 테이블의 bm25 점수는 서로 비교 가능하지 않으므로
    통합 랭킹을 만들지 않는다 — 관찰 모드 결과가 먼저, 차단 이력이 뒤에 오는
    순서로 이어붙이고, 각 결과에 ``blocked`` 키로 구분한다. ``limit``은 두
    하위 쿼리에 각각 독립 적용된다(합쳐서 최대 ``2 * limit``건).

    Args:
        path: SQLite DB 파일 경로(``save_tasks_to_db()``로 이미 기록된 파일).
        query: 검색 질의(자연어 키워드).
        limit: 하위 쿼리 1개당 최대 반환 건수.
        include_blocked: ``True``면 완전 차단 이력도 함께 반환(REQ-4). 기본값
            ``False``는 기존 반환 스키마와 100% 동일(``blocked`` 키 자체가 없음).

    Returns:
        관련도(BM25) 순으로 정렬된
        ``{"task_id", "summary", "timestamp", "task_type", "success"}`` 리스트
        (``include_blocked=True``면 각 항목에 ``"blocked": bool``도 포함).
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
        rows = _match_with_phrase_fallback(conn, _sql, query, limit)
        results = [
            {
                "task_id": r[0],
                "summary": r[1],
                "timestamp": r[2],
                "task_type": r[3],
                "success": bool(r[4]),
            }
            for r in rows
        ]
        if include_blocked:
            for r in results:
                r["blocked"] = False
            _blocked_sql = """
                SELECT b.task_id, b.tool_name, b.gate, b.reason, t.timestamp, t.task_type, t.success
                FROM blocked_violations AS b
                JOIN tasks AS t ON t.task_id = b.task_id
                WHERE blocked_violations MATCH ?
                ORDER BY bm25(blocked_violations)
                LIMIT ?
            """
            _blocked_rows = _match_with_phrase_fallback(conn, _blocked_sql, query, limit)
            for r in _blocked_rows:
                results.append({
                    "task_id": r[0],
                    "summary": f"{r[1]}: {r[3]}" if r[1] else r[3],
                    "gate": r[2],
                    "timestamp": r[4],
                    "task_type": r[5],
                    "success": bool(r[6]),
                    "blocked": True,
                })
    finally:
        conn.close()
    return results
