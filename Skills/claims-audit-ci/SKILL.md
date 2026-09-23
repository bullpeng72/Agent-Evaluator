---
name: claims-audit-ci
description: CI에 `agent-eval claims audit`를 등록해 TTL 초과·겹치는 active 클레임을 병합 전에 자동으로 잡는다. `.aoo/claims.jsonl` 팀 동시성 제어를 새로 도입하는 시점, 또는 기존 CI 파이프라인에 이 감사 단계가 빠져 있는지 점검할 때 사용한다.
aoo_dependency: full
---

# 클레임 CI 감사 도입 절차

《하니스 메서드》 §11.2·§11.6·§12.2가 다루는 `.aoo/claims.jsonl` 팀 동시성 제어를 CI의 마지막 안전망으로 굳히는 절차다. 새 판정 로직이 아니다 — `agent_evaluator/gates/team_concurrency.py`의 `audit_claims()`(CLI 래퍼: `agent-eval claims audit`)를 CI 단계 하나로 등록할 뿐이다.

## 왜 필요한가

`.aoo/claims.jsonl`은 세션 시작 시점에만 겹침을 확인한다(§11.2) — 세션 도중 새로 걸린 클레임과의 충돌은 `refresh_team_claims()`로 수동 재조회하지 않는 한 놓칠 수 있고, 클레임을 걸어놓고 세션이 비정상 종료돼(크래시, 강제 종료) `agent-eval claims release`를 못 부른 경우 그 클레임은 영원히 active로 남는다. 로컬 계층(LiveGuardrail·pre-commit)이 어떤 이유로든 뚫리거나 건너뛰어졌을 때, PR이 실제로 병합되기 전 원격에서 한 번 더 확인하는 것이 이 CI 단계의 역할이다(《하니스 메서드》 §12.2의 "네 계층" 방어선 중 마지막 계층과 같은 위치).

## 절차

### 1. TTL 기본값을 정한다

`audit_claims()`가 "초과됐다"고 판정하는 기준은 `started_at`으로부터 흐른 시간(`ttl_hours`)이다. 팀의 업무시간 리듬에 맞춰 정한다 — 하루 안에 끝나는 세션이 대부분이면 8시간이 합리적인 출발점이다.

### 2. CI 워크플로우에 감사 단계를 추가한다

```yaml
# .github/workflows 예시 — PR 병합 전 마지막 확인
- name: 클레임 감사
  run: agent-eval claims audit --ttl-hours 8
```

`agent-eval claims audit`은 `audit_claims()`를 그대로 호출하고, 위반이 하나라도 있으면 종료 코드 1을 반환한다 — 별도 파싱 로직 없이 CI 스텝 실패로 바로 이어진다.

### 3. 위반 두 유형을 팀에 공유한다

`audit_claims()`가 반환하는 위반은 정확히 두 타입이다(《하니스 메서드》 §12.2 참고).

- **`ttl_exceeded`** — `started_at`으로부터 지정한 시간이 지나도록 `released` 이벤트가 없는 클레임. 세션이 비정상 종료됐거나, 개발자가 `agent-eval claims release`를 잊은 경우다.
- **`overlapping_claims`** — 클레임 로그에 스코프가 겹치는 두 개의 active 항목이 동시에 존재하는 경우. `"gates/gate_d/"`와 `"gates/gate_d/aggregate.py"`처럼 한쪽이 다른 쪽의 하위 경로여도 겹침으로 잡힌다.

CI가 실패했을 때 팀이 해야 할 일은 다르다 — `ttl_exceeded`는 해당 개발자가 클레임을 확인 후 수동으로 `agent-eval claims release`하면 되고, `overlapping_claims`는 두 세션의 작성자가 직접 대화해 어느 변경을 채택할지 결정해야 한다(자동 병합 로직으로 풀 문제가 아니다 — §11.6이 강조하듯 이런 판단은 사람의 몫이다).

### 4. `started_at`의 타임존을 통일한다

`audit_claims()`는 타임존 오프셋이 없는(naive) 타임스탬프도 UTC로 간주해 처리하지만, 팀원마다 다른 로컬 시간대로 기록하면 TTL 판정이 실제 경과 시간과 어긋날 수 있다. `append_claim()` 호출 시 `datetime.now(timezone.utc).isoformat()`처럼 항상 타임존을 명시하도록 팀 규칙에 넣는다.

## 적용 체크리스트

- [ ] 팀의 세션 리듬에 맞는 `--ttl-hours` 값을 정했다(하루짜리 세션이 흔하면 8시간부터 시작).
- [ ] CI 워크플로우에 `agent-eval claims audit --ttl-hours <N>` 단계를 추가했다.
- [ ] `ttl_exceeded`/`overlapping_claims` 두 위반 타입의 대응 절차(누가, 무엇을 확인하는지)를 팀 문서에 남겼다.
- [ ] 클레임을 기록하는 모든 곳(`agent-eval claims add` 또는 직접 `append_claim()` 호출)이 타임존 명시 타임스탬프를 쓰는지 확인했다.
- [ ] 이 CI 단계는 §12.2가 정의한 "네 계층 방어선" 중 마지막 계층이지 유일한 계층이 아니다 — `BranchGuardConfig`(LiveGuardrail)·pre-commit·CODEOWNERS 나머지 세 계층도 함께 갖췄는지 점검했다.
