---
name: checklist-confidence-audit
description: 승인 큐의 체크리스트 자동채점(§3.4)이 실제로 얼마나 정확한지 주기적으로 점검한다. "체크리스트 자동채점이 믿을 만한지 확인해줘", "이번 분기 승인 오탐률 점검" 같은 요청에 사용.
aoo_dependency: full
---

# checklist-confidence-audit

`agent-eval autopilot approvals open`의 자동채점(`score_checklist()` +
`extract_needs_clarification()`)은 규칙 기반이다 — 체크리스트 항목의
`status` 필드와 `[NEEDS CLARIFICATION: ...]` 정규식 매칭만 본다. 사람이
"이 정도면 검토해도 된다"고 판단하는 것과 자동채점의 판정이 계속
어긋나면, 그 오탐률 자체를 추적해야 한다 — 이게 Harness Autopilot 설계서
§9 마찰 #4("요약만 보고 승인하는 고무도장 위험")의 반대편 위험, 즉
"자동채점을 못 믿어서 전부 사람이 다시 봐야 하는" 상태를 막는 장치다.

## 점검 절차

1. **최근 N개 승인 항목을 훑는다.** `agent-eval autopilot approvals list
   --all`로 `approved`/`rejected`/`changes_requested`로 끝난 항목을
   모은다.
2. **자동채점이 "ready"라고 했는데 사람이 반려한 경우를 센다.**
   `status`가 `pending`(자동채점 통과)으로 열렸다가 `rejected` 또는
   `changes_requested`로 끝난 비율 — 이게 **오탐(false ready)** 이다.
3. **자동채점이 "draft"로 묶어뒀는데 사람이 그대로 승인한 경우는
   해당 없음** — draft 상태는 애초에 사람 큐에 올라가지 않으므로 이
   경로 자체가 존재하지 않는다(설계상 보수적으로 치우친 쪽).
4. **오탐률이 임계치(팀이 정함, 기본 제안 20%)를 넘으면** 체크리스트
   항목 정의나 `[NEEDS CLARIFICATION: ...]` 태그 관행 자체를 재검토한다
   — 이건 `threshold-realism-review` 스킬과 같은 종류의 조정이지만
   대상이 Gate 임계값이 아니라 체크리스트 항목이라는 점이 다르다.

## 출력

한 줄 요약을 남긴다: `"최근 N건 중 오탐 M건(비율%) — 임계치 이하/초과"`.
이 수치 자체를 Gate 점수로 쓰지 않는다(원칙4 — 이미 있는 Gate A–G 채점
엔진을 다시 만들지 않는다, 새 판정 로직 아님) — 사람이 체크리스트 정의를
고칠지 말지 판단하는 참고 자료일 뿐이다.

> 절차 정본: 설계서(SPEC-AP-001) §9.2 마찰 #4, §9.3. `score_checklist()`
> 자체 구현은 `agent_evaluator/gates/autopilot_state.py`.
