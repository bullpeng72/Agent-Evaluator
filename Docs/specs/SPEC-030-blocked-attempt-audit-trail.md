# SPEC-030: `blocked_violations` — 완전 차단된 시도의 감사(Audit) 이력 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~6 전체 완료(2026-07-07)** · **의존성:** SPEC-019(완료, `LiveGuardrail`/`check_before_tool_call()`/`record_tool_call()`/`snapshot()`) · SPEC-024(완료, `violation_search` FTS5 테이블 + `search_violations()` + `violation_search_mcp.py` — 이번 스펙이 그대로 확장하는 기반) · SPEC-028(완료, `snapshot()`의 `tool_calls` 무조건 노출 패턴을 `blocked_attempts`에도 재사용)

> **구현 노트 (2026-07-07)**: 설계안 그대로 6개 REQ 전부 구현, 편차 없음.
> REQ-1: `LiveGuardrail.record_blocked_attempt(task_id, tool_name, verdict)` 추가 —
> `verdict.block=False`면 `ValueError`, `self._blocked_attempts`(신규 내부 상태,
> `self._tool_calls`와 완전히 분리)에 `{"tool_name", "gate", "reason"}` 딕셔너리를
> append. `check_before_tool_call()`은 무수정 — 이 메서드를 내부적으로 호출하지
> 않아 순수 조회 계약 그대로 유지. REQ-2: `snapshot()`/`to_task_extra()`가
> `"blocked_attempts": list(self._blocked_attempts)`를 `tool_calls`와 동일하게
> 항상(빈 리스트라도) 포함 — `tool_calls`와 달리 `TaskResult.extra`에 그대로
> 남고 최상위로 승격되지 않는다(`live_guardrail_report.py` 무수정으로 확인).
> REQ-3: `storage/sqlite_backend.py`에 `blocked_violations` FTS5 가상 테이블
> (`task_id UNINDEXED, tool_name UNINDEXED, gate UNINDEXED, reason`) 추가,
> `save_tasks_to_db()`가 `violation_search`와 동일한 delete-then-insert 패턴으로
> `task.extra["blocked_attempts"]`를 항목당 1행씩 반영(`SCHEMA_VERSION` 증가 없음).
> REQ-4: `search_violations(path, query, limit=10, include_blocked=False)` —
> 기본값 `False`는 기존과 100% 동일(반환 dict에 `blocked` 키 자체가 없음).
> `True`면 두 FTS5 테이블을 각각 독립 bm25 정렬한 뒤 `[*non_blocked, *blocked]`
> 순으로 이어붙이고 각 항목에 `"blocked": bool` 부여(재시도 로직은
> `_match_with_phrase_fallback()` 헬퍼로 양쪽 쿼리가 공유). REQ-5:
> `violation_search_mcp.py`가 `include_blocked=True`로 호출하도록 갱신(도구
> docstring이 원래 약속한 "차단된 이력" 검색을 실제로 이행), `format_results()`가
> `blocked` 필드에 따라 `[차단됨]`/`[관찰됨]` 접두어 렌더링. REQ-6:
> `live_guardrail_stdio.py`에 `{"op": "record_blocked", ...}` 연산 추가(수신
> gate/reason으로 `LiveVerdict(block=True, ...)`을 재구성해 호출) + TS 플러그인
> `GuardrailSession.recordBlocked()` 메서드 신설 + `tool.execute.before`에서
> 차단 에러를 던지기 직전에 호출하도록 배선(OpenCode 실사용 세션에서도 감사
> 이력이 실제로 쌓이도록 하는 마지막 조각).
>
> 기존 테스트 3건이 `snapshot()`/`to_task_extra()`의 정확한 key set/dict를
> assert하고 있어 `blocked_attempts` 키 추가로 실패 — `test_live_guardrail.py`의
> `test_snapshot_only_includes_configured_metrics`(예상 key set에
> `"blocked_attempts"` 추가)와 `test_gate_b_score_matches_direct_extra`/
> `test_gate_e_score_matches_direct_extra`(`direct_extra`에 `"blocked_attempts": []`
> 추가)를 수정 — 설계 시점에 이미 알고 있던 영향 범위였고 실제로도 딱 그
> 3건뿐이었음을 확인.
>
> 테스트 27건 추가(`test_live_guardrail.py` 5건, `test_spec016_sqlite_storage_backend.py`
> 16건, `test_violation_search_mcp.py` 4건, `test_live_guardrail_stdio.py` 2건).
> 전체 스위트 **3,462 passed, 1 skipped, 회귀 0건**(기존 3,440 + 신규 22 — 기존
> 3건 수정은 실패→통과로 전환됐을 뿐 신규 테스트 카운트에는 포함 안 됨).
>
> 품질 래칫: `live_guardrail.py`(UP006 8→10)·`sqlite_backend.py`(UP006 6→7)
> 증가분 전부 `git show HEAD:<file>`로 받은 원본과 직접 대조해 확인한 결과,
> **이 두 파일에 이미 지배적으로 존재하던 동일 규칙(Dict/List 타입힌트)**의
> 추가 인스턴스일 뿐 새로운 종류의 위반이 아님(SPEC-027 REQ-3의 UP045 +1과
> 동일한 선례). `violation_search_mcp.py`/`live_guardrail_stdio.py`는 변화 없음.
> mypy 신규 findings 없음(기존 2건은 내가 건드리지 않은 `analyze_privilege_chain`
> 호출부, 라인 번호만 밀렸을 뿐).

## Context (설계 시점 — 위 구현 노트가 최신 상태)

## Context

- `LiveGuardrail.check_before_tool_call()`이 `block=True`를 반환하면(§27.2, Ch27) 그 호출은 실행되지 않으므로 `record_tool_call()`도 호출되지 않는다 — 즉 **완전히 차단된 시도는 `self._tool_calls`에도, 그로부터 파생되는 `violation_search`(SPEC-024)에도 전혀 남지 않는다.** 이는 SPEC-019/024가 의도적으로 선택한 설계다 — Gate B/E 점수는 "확정 실행된 호출"만 반영해야 하므로, 애초에 실행되지 않은 후보를 이력에 섞으면 안 된다.
- 이 트레이드오프의 대가로, "이 세션에서 정확히 무엇이 왜 차단됐는가"를 나중에 검색할 방법이 없다 — `Evaluator_Examples/ch28_local_ade_loop.py` 섹션 2가 실제로 `search_violations(db, 'git')` 결과 0건을 보여주며 이 한계를 라이브로 검증해 뒀다("완전 차단된 시도는 검색되지 않는다"). 현재 권장 우회책은 `fail_on_*=False`(관찰 모드)로 낮춰 차단 대신 관찰만 하는 것뿐인데, 이러면 위험한 호출이 실제로 **실행**돼 버린다 — "완전 차단 + 감사 가능"을 동시에 満족시킬 방법이 없다.
- `violation_search`(SPEC-024 REQ-2, `storage/sqlite_backend.py`)는 이미 `save_tasks_to_db()` 안에서 `task.extra`로부터 자동으로 채워지는 FTS5 가상 테이블이다 — 같은 delete-then-insert 패턴을 그대로 복제하면 새 쓰기 경로를 발명할 필요가 없다.
- `violation_search_mcp.py`(SPEC-024 REQ-4)의 MCP 도구 docstring은 이미 "**차단된** 이력을 검색한다"고 적혀 있다 — 그러나 실제 구현은 `violation_search`만 조회하므로, 정확히는 "관찰 모드에서 기록된 위반"만 검색될 뿐 진짜 차단 이력은 찾지 못한다. 이번 스펙이 이 docstring과 실제 동작의 간극을 메운다.
- `check_before_tool_call()`은 "순수 조회 — 호출해도 내부 이력이 바뀌지 않는다"는 계약(§27.2)을 갖고 있다. 이 계약을 지키려면, 차단된 시도를 감사 이력에 남기는 새 동작은 `check_before_tool_call()` 내부에 자동으로 넣지 않고, 호출자가 명시적으로 트리거하는 별도 API여야 한다 — 그래야 "후보를 여러 개 미리 찔러보는" 호출까지 전부 감사 로그에 남는 노이즈를 피한다.

## Goals

- 완전히 차단된(`block=True`) 도구 호출 시도를, **Gate B/E 점수 계산에 전혀 영향을 주지 않으면서** 별도의 감사 가능한 이력으로 남긴다.
- 이 이력을 기존 `search_violations()`/`violation_search_mcp.py` 파이프라인에서 옵트인으로(`include_blocked=True`) 검색 가능하게 해, 다음 세션이 "이 시도는 과거에 완전히 차단됐었다"를 확인할 수 있게 한다.
- `check_before_tool_call()`의 "순수 조회" 계약을 그대로 유지한다 — 새 기록 동작은 호출자가 명시적으로 트리거하는 별도 메서드로 분리한다.
- 기존 `violation_search` 인프라(FTS5 delete-then-insert 패턴, `search_violations()` 반환 스키마)를 최대한 재사용한다 — 새 저장 메커니즘을 발명하지 않는다.

## Non-Goals

- `check_before_tool_call()`을 호출할 때마다 자동으로 차단 시도를 기록하는 것 — "순수 조회" 계약을 깨므로 명시적으로 배제한다. 기록은 반드시 호출자가 `record_blocked_attempt()`를 별도로 호출해야 일어난다.
- 차단된 시도의 원본 도구 파라미터(예: 실제 셸 명령 전체 텍스트)를 저장하는 것 — `LiveVerdict.reason`은 이미 도구 이름/패턴 이름 수준의 요약이지 원본 인자 전체가 아니다(기존 `_summarize_violations()`와 동일한 신뢰 수준). 원본 파라미터 캡처는 이번 스펙 범위 밖(민감 정보 노출 위험이 더 커 별도 검토 필요).
- 두 FTS5 테이블(`violation_search`/`blocked_violations`)에 걸친 단일 통합 관련도(bm25) 랭킹 — 서로 다른 가상 테이블의 bm25 점수는 직접 비교할 수 없다. 이번 스펙은 각 테이블에서 독립적으로 정렬한 뒤 이어붙이는 것으로 충분하다고 본다.
- PII 마스킹 확장 — `reason` 필드는 기존 `violation_search`의 `summary`와 동일한 신뢰 수준(도구 이름/패턴 기반, 원본 인자 아님)이라 이번 스펙에서 새 마스킹을 추가하지 않는다.

## Requirements

- **REQ-1**: `LiveGuardrail`에 `self._blocked_attempts: List[Dict[str, Any]] = []` 내부 상태와 `record_blocked_attempt(task_id: str, tool_name: str, verdict: LiveVerdict) -> None` 메서드를 추가한다. `verdict.block`이 `False`면 `ValueError`(차단되지 않은 시도를 차단 이력에 넣는 호출자 오류를 조용히 넘기지 않는다). `{"tool_name": ..., "gate": verdict.gate, "reason": verdict.reason}`을 `self._blocked_attempts`에 append한다. `check_before_tool_call()`은 이 메서드를 내부적으로 호출하지 않는다 — 순수 조회 계약 유지.
- **REQ-2**: `snapshot()`/`to_task_extra()`가 반환하는 dict에 `"blocked_attempts": list(self._blocked_attempts)`를 **항상** 포함한다(`tool_calls`와 동일하게 조건부가 아님 — SPEC-028 REQ-1과 동일한 원칙). 다른 Gate B/E 파생 키(`loop_detection` 등)와 달리 새 계산을 하지 않고 누적된 리스트를 그대로 실어 보낸다.
- **REQ-3**: `storage/sqlite_backend.py`에 `blocked_violations` FTS5 가상 테이블(`task_id UNINDEXED, tool_name UNINDEXED, gate UNINDEXED, reason`)을 추가한다. `save_tasks_to_db()`가 각 태스크 저장 시 기존 `violation_search`와 동일한 delete-then-insert 패턴으로 `task.extra.get("blocked_attempts", [])`를 이 테이블에 반영한다(`live_guardrail_report.py`는 무수정 — `blocked_attempts`는 `tool_calls`와 달리 `TaskResult.extra`에서 꺼내 올리지 않고 그대로 둔다). `SCHEMA_VERSION`은 올리지 않는다(순수 additive, SPEC-024 REQ-2와 동일한 원칙).
- **REQ-4**: `search_violations(path, query, limit=10, include_blocked=False)` — 기본값 `False`면 기존 동작·반환 스키마와 100% 동일(회귀 없음). `True`면 `violation_search`와 `blocked_violations`를 각각 독립적으로 bm25 검색한 뒤, 각 결과 dict에 `"blocked": bool`을 추가해 `[*non_blocked_results, *blocked_results]` 순서로 이어붙여 반환한다. `limit`은 두 하위 쿼리에 각각 독립 적용(합쳐서 최대 `2×limit`건).
- **REQ-5**: `violation_search_mcp.py`의 `search_violations` MCP 도구가 `include_blocked=True`로 하위 함수를 호출하도록 갱신한다(도구 docstring이 이미 약속한 "차단된 이력" 검색을 실제로 이행). `format_results()`가 각 결과의 `blocked` 필드에 따라 `[차단됨]`/`[관찰됨]` 접두어를 붙여 렌더링한다.
- **REQ-6**: `live_guardrail_stdio.py`에 새 연산 `{"op": "record_blocked", "task_id": ..., "tool_name": ..., "gate": ..., "reason": ...}` → `{"ok": true}`를 추가한다(수신한 필드로 `LiveVerdict(block=True, gate=..., reason=...)`을 재구성해 `record_blocked_attempt()` 호출). OpenCode TS 플러그인(`agent-evaluator.ts`)의 `GuardrailSession`에 `recordBlocked(taskId, toolName, verdict)` 메서드를 추가하고, `tool.execute.before`에서 `verdict.block`이 참이라 에러를 던지기 **직전**에 호출한다 — 이래야 OpenCode 실사용 세션에서도 이번 스펙의 감사 이력이 실제로 쌓인다(REQ-1~5가 Python SDK 단독으로 완결되는 것과 달리, 이 REQ만 TS 변경을 동반).

## Interface

```python
# REQ-1 — 호출자가 명시적으로 트리거 (check_before_tool_call()은 그대로 순수 조회)
verdict = guardrail.check_before_tool_call(task_id, "bash", {"command": "rm -rf /"})
if verdict.block:
    guardrail.record_blocked_attempt(task_id, "bash", verdict)  # 감사 이력에 기록
    # 도구를 실행하지 않는다
else:
    # 도구 실행
    guardrail.record_tool_call(task_id, "bash", {"command": "..."})
```

```python
# REQ-2 — snapshot()에 항상 포함
guardrail.snapshot()
# -> {"tool_calls": [...], "blocked_attempts": [
#        {"tool_name": "bash", "gate": "B", "reason": "dangerous tool parameters: ['bash'] (task_id=t1)"}
#    ], ...}
```

```python
# REQ-4 — 옵트인 검색
from agent_evaluator.storage.sqlite_backend import search_violations

search_violations(db_path, "rm -rf")                        # 기존과 동일(관찰 모드 위반만)
search_violations(db_path, "rm -rf", include_blocked=True)   # + 완전 차단 이력도 함께
# -> [{"task_id": ..., "summary": ..., "blocked": False, ...},
#     {"task_id": ..., "summary": "bash: dangerous tool parameters...", "blocked": True, ...}]
```

## Acceptance

- **REQ-1**: `verdict.block=False`인 `LiveVerdict`로 `record_blocked_attempt()`를 호출하면 `ValueError`. `block=True`인 verdict로 호출하면 `self._blocked_attempts`에 1건 추가되고, `check_before_tool_call()`을 여러 번 호출해도(record를 호출하지 않는 한) `self._blocked_attempts`가 변하지 않는지(순수 조회 계약 유지 확인).
- **REQ-2**: `record_blocked_attempt()`를 한 번도 호출하지 않은 세션의 `snapshot()`이 `"blocked_attempts": []`(빈 리스트, 키 자체는 항상 존재)를 반환하는지. 2건 기록 후 `snapshot()`이 그 2건을 그대로 반환하는지.
- **REQ-3**: `blocked_attempts`가 있는 태스크를 `save_tasks_to_db()`로 저장한 뒤, `blocked_violations` 테이블에 해당 행이 존재하는지. 같은 `task_id`로 재저장(블록 내용이 바뀜)했을 때 이전 행이 아니라 최신 행만 남는지(delete-then-insert 확인). `blocked_attempts`가 없는(빈 리스트) 태스크는 `blocked_violations`에 아무 행도 추가되지 않는지.
- **REQ-4**: `include_blocked=False`(기본값)일 때 반환 dict에 `"blocked"` 키 자체가 없는지(기존 스키마와 완전 동일 — 회귀 없음). `include_blocked=True`일 때 관찰 모드 위반과 차단 이력이 모두 반환되고 각각 정확한 `blocked` 값을 갖는지. 둘 다 없는 DB에서 `include_blocked=True`로 검색해도 빈 리스트(에러 아님).
- **REQ-5**: MCP `search_violations` 도구를 통해 검색했을 때 차단 이력이 결과에 포함되고, `format_results()` 출력에 `[차단됨]` 접두어가 붙는지.
- **REQ-6**: stdio 브리지에 `{"op": "record_blocked", ...}`를 보내면 `{"ok": true}`가 오고, 이어지는 `{"op": "snapshot"}` 응답의 `extra.blocked_attempts`에 반영되는지.
- **회귀 없음**: `record_blocked_attempt()`를 전혀 쓰지 않는 기존 `LiveGuardrail`/`search_violations()`/MCP 도구 사용 코드가 이전과 완전히 동일하게 동작하는지 — 기존 SPEC-019/024/028 테스트 스위트 전체가 무수정으로 통과하는지 확인.

## Compatibility

- 100% additive — `record_blocked_attempt()`는 새 옵트인 메서드, `include_blocked`는 기본값 `False`인 새 옵트인 파라미터. 기존 `check_before_tool_call()`/`record_tool_call()`/`snapshot()`/`search_violations()`의 기본 동작·반환 스키마는 전혀 바뀌지 않는다.
- `save_tasks_to_db()`에 `blocked_attempts`가 없는(이번 스펙 이전에 만들어진) `TaskResult`를 저장해도 `extra.get("blocked_attempts", [])`가 빈 리스트로 안전하게 떨어져 `blocked_violations`에 아무것도 추가되지 않는다 — 하위 호환 100%.
- `SCHEMA_VERSION` 증가 없음 — 구버전 DB 파일을 다시 열어도 `blocked_violations` 테이블이 없으면 `CREATE TABLE IF NOT EXISTS`로 조용히 생성된다(SPEC-024 REQ-2와 동일한 패턴).

## Rollout

1. REQ-1(`record_blocked_attempt()` + 내부 상태) — 가장 작고 독립적, 다른 REQ의 전제.
2. REQ-2(`snapshot()` 노출) — REQ-1에 의존, 즉시 병행 가능.
3. REQ-3(`blocked_violations` 테이블 + `save_tasks_to_db()` 연결) — REQ-2가 만드는 `extra.blocked_attempts`를 소비.
4. REQ-4(`search_violations(include_blocked=...)`) — REQ-3이 채운 테이블을 조회.
5. REQ-5(MCP 도구 연결) — REQ-4에 의존, 실제 사용자(다음 세션의 모델)에게 가치가 드러나는 지점.
6. REQ-6(stdio 브리지 + TS 플러그인) — REQ-1에 의존, OpenCode 실사용 세션에서 실제로 이 감사 이력이 쌓이게 하는 마지막 조각(Python 단독 스펙 완결성과는 별개로, 실사용을 위해 필요).

## Risks

- **호출자가 `record_blocked_attempt()`를 잊고 호출하지 않을 위험**: `check_before_tool_call()`이 자동으로 기록하지 않기로 한 설계상 트레이드오프다 — 호출자(OpenCode 플러그인, 또는 직접 Python 통합)가 `block=True`를 받고도 이 메서드를 호출하지 않으면 감사 이력에 남지 않는다. 완화책: REQ-6에서 TS 플러그인의 유일한 차단 처리 지점(`tool.execute.before`)에 직접 배선해 두면, OpenCode 경유 사용자는 이 위험에서 자동으로 벗어난다. 직접 Python 통합 사용자는 Interface 섹션의 표준 패턴(check → block이면 record_blocked, 아니면 record)을 문서로 안내한다.
- **`blocked_attempts`가 많이 쌓인 세션의 `extra` 크기 증가**: 반복적으로 같은 위험한 호출을 여러 번 시도하는 세션이면 리스트가 길어질 수 있다 — 완화책: 각 항목이 이름/게이트/한 줄 이유만 담아(원본 파라미터 없음) 항목당 크기가 작고, 이미 `tool_calls`도 같은 패턴으로 무제한 누적되고 있어 기존 리스크 수준과 동일하다(새로운 종류의 위험이 아님).
- **두 FTS5 테이블 간 랭킹 비교 불가**: Non-Goals에 명시한 대로 통합 랭킹을 만들지 않기로 했으므로, `include_blocked=True` 결과의 순서가 "관련도"를 완벽히 반영하지 않을 수 있다 — 완화책: 각 하위 그룹 내에서는 정확한 bm25 순서를 유지하고, `blocked` 필드로 두 그룹을 명확히 구분할 수 있게 해 사용자(모델)가 직접 판단할 수 있게 한다.
