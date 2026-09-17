---
name: sync-drift-check
description: GitHub PR 라벨(Phase 상태)과 오토파일럿의 .aoo/tasks/<id>.json이 서로 어긋나지 않았는지 주기적으로 대조한다. "대시보드 상태를 믿어도 되는지 확인해줘", "GitHub이랑 과제 상태가 안 맞는 것 같아" 같은 요청에 사용.
aoo_dependency: full
---

# sync-drift-check

Harness Autopilot 설계서 §3.3(Phase 상태머신)은 GitHub PR 라벨과
`.aoo/tasks/<task_id>.json`을 **서로 다른 두 저장소**로 둔다 — 하나는
플랫폼(GitHub)이, 하나는 로컬 파일이 갖는다. 웹훅이 유실되거나 GitHub
Actions 잡이 실패하면 이 둘이 어긋날 수 있는데, §9 마찰 #6이 지적했듯
지금까지는 그걸 알려주는 장치가 없었다. `claims-audit-ci`(본편 절차
스킬)와 같은 패턴(주기 대조 + CI 실패로 드러냄, 원칙4 — 새로 안 만들고
기존 audit 방식을 재사용)을 그대로 가져온다.

## 대조 절차

1. `.aoo/tasks/*.json`의 `current_phase`를 전부 읽는다
   (`agent-eval autopilot doctor`가 이미 이 목록을 출력한다).
2. 같은 과제에 연결된 GitHub PR의 `phase:N-*` 라벨을 읽는다(M1 이후,
   PR 라벨 상태머신이 실제로 존재해야 이 단계가 의미를 갖는다 — 지금
   이 스킬은 M2 완료조건 중 하나로 설계서 §6에 배치돼 있다).
3. 둘의 Phase 숫자가 다르면 **어느 쪽이 최신인지 자동으로 판단하지
   않는다** — 두 저장소 다 append-only 이력을 갖고 있으니(`phase_
   history`, PR 이벤트 로그) 사람이 마지막 이벤트 시각을 비교해서
   판단한다.

## CI 편입

`claims-audit-ci`가 `agent-eval claims audit`을 CI에 거는 것과 같은
자리에, 이 점검을 함께 건다 — 어긋남이 발견되면 CI를 실패시키는 게
아니라(과제 상태 불일치가 빌드를 막을 이유는 없다) 대시보드 상단바에
"마지막 동기화: N시간 전, 불일치 감지" 배지를 띄운다(§9 UI 개선안,
설계서 §6 M2).

## 이 스킬이 하지 않는 것

- 자동으로 한쪽을 다른 쪽에 맞춰 덮어쓰지 않는다 — 어느 쪽이 진실인지
  기계가 판단할 근거가 없다.
- GitHub Actions 상태머신 자체를 구현하지 않는다 — 그건 M2의 별도
  산출물이고, 이 스킬은 그 위에서 도는 감사(audit) 절차일 뿐이다.

> 절차 정본: 설계서(SPEC-AP-001) §9.2 마찰 #6·§6 M2. 같은 패턴의 선례는
> 본편 `claims-audit-ci` 스킬과 `agent_evaluator/gates/team_concurrency.
> py::audit_claims()`.
