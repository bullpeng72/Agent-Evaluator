---
name: harness-autopilot
description: Harness Methodology 파이프라인(Phase 0~8)의 현재 위치를 판단하고, 반복되는 초안 작업(SPEC/ADR 초안, Gate 매핑)을 대신 만들고, 사람이 필요한 HITL 관문에서 정확히 멈춘다. "과제 파이프라인을 다음 단계로 진행해줘", "이 과제 지금 어느 Phase야", "SPEC 초안 만들어줘" 같은 요청에 사용.
aoo_dependency: full
---

# harness-autopilot

Harness Autopilot 설계서(SPEC-AP-001)의 오케스트레이션 스킬 스켈레톤이다.
M0 시점에는 **상태 판단만** 한다 — Phase를 자동으로 전이시키거나 Claude
Code 세션을 무인으로 재트리거하는 것은 M1 이후 범위다(설계서 §6).

## 이 스킬이 지금(M0) 하는 것

1. `.aoo/tasks/<task_id>.json`을 읽어 과제의 현재 Phase와 `blocking_on`을 보고한다.
2. `.aoo/team.json`을 대조해, 배정된 담당자가 등록돼 있는지 · 역할이 맞는지 ·
   GitHub 동기화(`synced`) 상태인지 확인하고 어긋나면 경고한다.
3. 다음에 사람이 뭘 해야 하는지(승인 대기 중인지, 다음 자동 단계가 있는지)를
   요약한다.

## 이 스킬이 아직 안 하는 것 (M1 이후)

- Phase 자동 전이(§3.3 상태머신) — 지금은 `agent-eval autopilot new-task`로
  Phase 0을 만드는 것까지만 자동이고, 이후 전이는 사람이 판단한다.
- GitHub PR 생성·라벨 전이(§3.4 HITL 승인 시퀀스).
- SPEC/ADR 초안 자동 생성 — 지금은 워크북 §6·§15의 프롬프트 패턴을 사람이
  직접 참고해야 한다.

## 사용 예

```
"ST-014 과제 지금 어디까지 왔어?"
→ .aoo/tasks/ST-014.json을 읽어 현재 Phase·담당자·blocking_on을 보고
→ .aoo/team.json과 대조해 담당자 동기화 상태 경고
```

> 절차 정본: 설계서(SPEC-AP-001) §3.1(컴포넌트 구성도)·§3.3(Phase 상태머신)·
> §4.5(과제 컬렉션)·§4.6(팀원 레지스트리). 이 파일이 그 설계의 스켈레톤
> 구현이며, M1~M4로 갈수록 이 문서도 함께 채워진다.
