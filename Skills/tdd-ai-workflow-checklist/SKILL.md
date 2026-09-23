---
name: tdd-ai-workflow-checklist
description: TDD-AI(Test-Driven Agent Iteration)의 red-green-refactor 순환을 실행 세션(Tier 2)에서 체크리스트로 따라간다. 설계 문서가 이미 있고 실제 구현을 시작할 때 사용한다.
aoo_dependency: full
---

# TDD-AI 워크플로우 체크리스트

《하니스 메서드》 §21이 정의한 TDD-AI 순환을 세션 진행 중 그대로 따라가는 체크리스트다. TDD-AI는 SDK 기능이 아니라 팀 방법론이라 SDK 가이드에는 대응하는 챕터가 없다 — 이 책 §21이 유일한 정의처다. `agent_version="auto"` + `iteration_note` 같은 버전 비교 API 자체의 레퍼런스는 SDK 가이드에서 확인할 수 있다.

## Red — 실패하는 골든셋 케이스 확인

- [ ] 이번 세션이 통과시켜야 할 골든셋 케이스를 명시했다(설계 문서·§15 산출물에서 가져온다).
- [ ] 현재 코드가 이 케이스를 통과하지 못한다는 것을 먼저 확인했다(없던 걸 만드는 경우는 생략 가능).

## Green — 통과시키는 최소 코드

- [ ] 설계 문서(§17)가 지정한 스코프 밖 파일은 건드리지 않았다.
- [ ] 골든셋 케이스가 전부 통과한다.
- [ ] 기존 테스트 스위트가 수정 전과 동일하게 통과한다(리팩토링이라면 이 항목이 가장 중요하다).

## Refactor — 버전 비교로 "나아졌다" 증명

- [ ] `agent_version="auto"` + `iteration_note`로 이번 iteration을 태깅했다.
- [ ] 이전 iteration과 Gate 점수를 비교했다(대시보드 File Compare, 필요시 Pairwise Judge).
- [ ] 점수가 예상과 다르게 하락했다면, 다음 세션을 시작하기 전에 원인을 확인했다.

## 세션 종료 시

- [ ] 무엇을 시도했고 무엇이 실패했는지 세션 리포트에 남겼다 — 다음 세션이 `search_violations()`로 회수할 수 있도록.
