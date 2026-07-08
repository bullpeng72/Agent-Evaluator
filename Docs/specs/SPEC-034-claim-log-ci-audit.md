# SPEC-034: `audit_claims()` — 클레임 로그 CI 감사 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~4 전체 완료(2026-07-08)** · **의존성:** SPEC-032(완료, `load_active_claims()`/`_scopes_overlap()` 재사용 — 새 파싱 로직 없음)

> **구현 노트 (2026-07-08)**: 설계 그대로 편차 없이 구현했다. `gates/team_concurrency.py`에
> `audit_claims(claims_path=".aoo/claims.jsonl", ttl_hours=8.0)` 추가 — 내부에서
> `load_active_claims()`(REQ-1)와 `_scopes_overlap()`(REQ-3)를 그대로 재사용해 새
> 파싱·겹침 규칙을 만들지 않았다. `started_at` 타임존 처리는 offset-aware/naive
> 둘 다 처리(naive는 UTC로 간주 후 비교)하도록 구현, 파싱 실패는 조용히 건너뜀(REQ-2).
> 반환값은 `sys.exit()` 없는 순수 위반 리스트(REQ-4).
>
> 외부 검토안의 두 버그를 직접 재현해 이 구현이 실제로 피하는지 확인했다: (1)
> 개설→해제 순으로 클레임을 넣었을 때 이 구현은 위반 0건(해제된 클레임 재사용
> 안 함), 외부 검토안은 "여전히 active"로 오탐. (2) `+09:00` 오프셋 타임스탬프로
> `datetime.now()`(naive)와 그대로 빼면 외부 검토안은 `TypeError`로 크래시하는
> 것을 재현했고, 이 구현은 정상 처리됨을 확인. (3) prefix만 겹치는 스코프
> (`"gates/gate_d/"` vs `"gates/gate_d/aggregate.py"`)가 외부 검토안의 `set & set`
> 방식(완전 일치만 확인)으로는 놓치지만 이 구현(`_scopes_overlap()` 재사용)은
> 정확히 잡는 것도 확인.
>
> Ch29 §29.2의 의사코드(`...`)를 실제 함수 호출 + CI 종료 코드 스니펫으로 교체,
> 스니펫을 직접 실행해(오래된 활성 클레임 시나리오) `sys.exit(1)`이 정확히
> 발동하는 것도 확인했다.
>
> 테스트 14건 추가(`tests/test_spec034_claim_audit.py`) — 해제된 클레임 재발 방지
> 회귀 2건, TTL 판정(tz-aware/naive/누락/파싱불가) 6건, 겹침 판정(정확 일치/prefix/
> 비겹침/3개 이상 중복방지) 4건, 빈 상태 2건. 전체 스위트 **회귀 0건**.
>
> 품질 래칫: `team_concurrency.py` UP006 +4(신규 `List[...]`/`Dict[...]` 타입힌트 —
> 이 파일에 이미 지배적인 컨벤션과 일치). 초안에서 새 E501 1건(주석이 길어 100자
> 초과)이 나와 주석을 별도 줄로 분리해 해결 — 최종 E501 순증가 0건. mypy 신규
> findings 없음.

---

## Context

- Ch29 §29.2는 "CI에서 클레임 로그의 정합성을 주기적으로 점검한다"며 `audit_claims(claims_path=".aoo/claims.jsonl", ttl_hours=8)`를 예시로 들지만, 본문은 의사코드(`...`)로만 남아 있고 실제 구현이 없다 — "TTL 초과 클레임"과 "겹치는 active 클레임"을 찾는다고 설명만 하고 실행 가능한 코드는 제공하지 않는다.
- 외부 검토에서 이 함수의 "즉석 구현안"이 제시됐으나, 직접 실행해 두 가지 실질적 버그를 확인했다: (1) claims.jsonl의 "같은 `claim_id`는 최신 상태만 유효하다"는 핵심 규칙(§28.5)을 구현하지 않아 **이미 해제된 클레임을 영원히 active로 오탐**한다, (2) 책이 실제로 쓰는 타임스탬프 포맷(`+09:00` 같은 오프셋)에 `datetime.now()`(naive)를 그대로 빼서 `TypeError`로 즉시 크래시한다. 두 버그 모두 재현 스크립트로 직접 확인했다.
- SPEC-032가 이미 이 정확한 "최신 병합" 로직을 `load_active_claims()`(`gates/team_concurrency.py`)로 구현·테스트해 뒀다 — `audit_claims()`는 이 함수를 그대로 재사용하면 첫 번째 버그를 원천적으로 피할 수 있다. 두 번째 버그(타임존 처리)만 새로 신경 쓰면 된다.
- 스코프 겹침 판정도 기존 `_scopes_overlap()`(prefix 매칭 — `check_scope_claim()`이 이미 쓰는 것과 동일한 기준)을 재사용해야 한다 — 외부 검토안의 `set(a) & set(b)`(완전 일치만 확인) 방식은 `"gates/gate_d/"` vs `"gates/gate_d/aggregate.py"`처럼 실제로 겹치는 경로를 놓친다.

## Goals

- Ch29 §29.2의 의사코드를 실제 동작하는 함수로 교체한다 — TTL 초과 클레임과 겹치는 active 클레임을 찾아 CI가 소비할 수 있는 구조화된 목록으로 반환한다.
- SPEC-032의 기존 파싱·겹침 판정 로직을 그대로 재사용한다 — 새 클레임 로그 해석 규칙을 만들지 않는다.
- `started_at`에 타임존 오프셋이 있든 없든 예외 없이 동작한다.

## Non-Goals

- 클레임 로그 자체의 쓰기 동시성 보장(여러 프로세스가 동시에 append할 때의 원자성) — OS/파일시스템의 append 원자성에 의존하는 기존 전제를 그대로 따른다(SPEC-032 Risks에 이미 문서화).
- Slack/이메일 등 실제 알림 발송 — `audit_claims()`는 위반 목록만 반환한다. 발송은 호출자(CI 스크립트)의 몫이다.
- 새 CLI 서브커맨드(`agent-eval claims audit` 등) — 이번 스펙은 라이브러리 함수와 CI 스니펫 수준까지만 다룬다. 필요성이 확인되면 별도 후속 스펙.

## Requirements

- **REQ-1**: `gates/team_concurrency.py`에 `audit_claims(claims_path: Union[str, Path] = ".aoo/claims.jsonl", ttl_hours: float = 8.0) -> List[Dict[str, Any]]`를 추가한다. 내부적으로 `load_active_claims(claims_path)`를 호출해 활성 클레임 목록을 얻는다(SPEC-032 로직 재사용, 새 파싱 없음).
- **REQ-2**: 각 활성 클레임의 `started_at`을 파싱해 현재 시각과의 경과 시간을 계산한다. 파싱된 시각에 타임존 정보가 있으면 그대로, 없으면 UTC로 간주해 비교한다(naive/aware 혼합으로 인한 `TypeError` 방지). 경과 시간이 `ttl_hours`를 넘으면 `{"type": "ttl_exceeded", "claim_id", "developer", "scope", "age_hours"}` 형태로 위반 목록에 추가한다. `started_at`이 없거나 파싱 불가능하면(방어적) 조용히 건너뛴다 — TTL 판정 불가로 인한 예외 전파를 막는다.
- **REQ-3**: 활성 클레임 전체에 대해 쌍별(pairwise)로 스코프 겹침을 확인한다 — 기존 `_scopes_overlap()`(prefix 매칭)을 재사용해, `c1.scope`의 각 경로가 `c2.scope`와 겹치는지 확인한다(완전 일치만 보는 `set & set` 방식 아님). 겹치면 `{"type": "overlapping_claims", "claim_id_a", "developer_a", "claim_id_b", "developer_b", "scope"}`로 위반 목록에 추가한다. 같은 쌍을 두 번 보고하지 않는다(`i < j` 순회).
- **REQ-4**: 반환값이 빈 리스트면 위반 없음. `audit_claims()` 자체는 `sys.exit()`을 호출하지 않는다 — CI 종료 코드 결정은 호출자의 몫(Ch29 §29.2 예제가 이 패턴을 보여준다).

## Interface

```python
from agent_evaluator.gates.team_concurrency import audit_claims

violations = audit_claims(".aoo/claims.jsonl", ttl_hours=8)
# -> [{"type": "ttl_exceeded", "claim_id": "c1", "developer": "sungwoo",
#      "scope": ["agent_evaluator/gates/gate_d_performance/"], "age_hours": 9.2},
#     {"type": "overlapping_claims", "claim_id_a": "c1", "developer_a": "sungwoo",
#      "claim_id_b": "c2", "developer_b": "alice",
#      "scope": ["agent_evaluator/gates/gate_d_performance/"]}]
```

```bash
# CI 스니펫 — GitHub Actions 등에서 그대로 쓸 수 있는 종료 코드 패턴
python -c "
import sys
from agent_evaluator.gates.team_concurrency import audit_claims

violations = audit_claims('.aoo/claims.jsonl', ttl_hours=8)
if violations:
    for v in violations:
        print(f'CLAIM AUDIT FAIL: {v}')
    sys.exit(1)
print('CLAIM AUDIT PASS')
"
```

## Acceptance

- **REQ-1**: `load_active_claims()`가 이미 검증한 "최신 상태만 유효" 시나리오(개설→해제)를 `audit_claims()`에 넣었을 때 해제된 클레임이 TTL/겹침 판정 대상에서 제외되는지(SPEC-032 버그 재발 방지 회귀 테스트).
- **REQ-2**: `started_at`이 8시간 전인 활성 클레임이 `ttl_hours=8`에서 위반으로 잡히는지. 타임존 오프셋 포맷(`+09:00`)과 오프셋 없는 포맷(naive) 둘 다 예외 없이 처리되는지(각각 직접 테스트). `started_at` 필드 자체가 없는 클레임이 예외 없이 건너뛰어지는지.
- **REQ-3**: 완전히 동일한 스코프의 두 active 클레임이 겹침으로 잡히는지. prefix만 겹치는 경우(`"a/"` vs `"a/b.py"`)도 잡히는지(`set & set` 방식이면 놓치는 케이스). 겹치지 않는 두 클레임이 위반으로 잡히지 않는지. 클레임이 3개 이상일 때 같은 쌍이 중복 보고되지 않는지.
- **REQ-4**: 위반이 전혀 없을 때 빈 리스트를 반환하는지(예외 아님).
- **회귀 없음**: 기존 SPEC-032 테스트 스위트 전체가 무수정으로 통과하는지.

## Compatibility

- 100% additive — 신규 함수, 기존 `team_concurrency.py`의 다른 함수·시그니처를 변경하지 않는다.

## Rollout

1. REQ-1(`audit_claims()` 골격 + `load_active_claims()` 재사용) — 가장 작고 독립적.
2. REQ-2(TTL 판정, 타임존 안전 처리) — REQ-1에 의존.
3. REQ-3(겹침 판정, `_scopes_overlap()` 재사용) — REQ-1에 의존, REQ-2와 병행 가능.
4. REQ-4는 REQ-1~3 구현에 자연히 포함(별도 롤아웃 단계 아님).

## Risks

- **TTL 기준값(8시간)은 팀마다 다를 수 있다.** 기본값일 뿐이며 팀 업무 시간·세션 길이 관행에 맞춰 조정해야 한다 — Ch28 §28.2 원칙 4("세션은 짧다")를 따르는 팀이라면 훨씬 짧은 값(예: 2~3시간)이 더 적합할 수 있다.
- **클레임 로그 자체가 없거나 빈 경우**: `load_active_claims()`가 이미 안전하게 빈 리스트를 반환하므로(SPEC-032), `audit_claims()`도 예외 없이 빈 위반 목록을 반환한다 — 새로운 리스크가 아니다.
