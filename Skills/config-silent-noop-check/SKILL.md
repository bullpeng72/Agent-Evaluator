---
name: config-silent-noop-check
description: Harness Config(예 SubtaskConfig·ComplianceConfig·ExplainabilityConfig·BranchGuardConfig)를 배선했는데 Gate 점수나 가드레일이 기대와 다르게(또는 전혀) 반응하지 않을 때, 그 Config가 실제로 채점/차단 경로에 연결돼 있는지 SDK 소스 레벨에서 확인하는 절차. "이 Config를 켰는데 점수가 그대로다", "설정했는데 왜 안 잡히지", "이 옵션이 진짜 작동하는지 모르겠다" 같은 요청에 사용.
aoo_dependency: full
---

# config-silent-noop-check

Archivist 실습서(워크북) Ch 27·30·31·33·36에서 다섯 번 독립적으로 같은
모양의 함정에 걸렸다: **Config를 배선했다는 것과, 그 Config가 실제로
채점/차단 로직에 연결됐다는 것은 다른 일이다.**

- Ch 27: `SubtaskConfig`를 배선했지만 실제로는 파이프라인 단계 추적이
  아니라 응답 텍스트의 리터럴 단어 매칭이었다 — 기대한 신호를 전혀
  안 냈다.
- Ch 30: `CostPredictabilityConfig`가 `PerformanceMonitor` 기본값만으로도
  이미 자동 실행되고 있었고, 통과/실패가 아니라 `1 − CV/max_cv` 선형
  공식이라 임계값을 조금 올려선 점수가 거의 안 움직였다.
- Ch 31: `ComplianceConfig(pii_categories=["card", ...])` — 존재하지
  않는 카테고리 이름(`"card"`, 정확히는 `"credit_card"`) 오타가
  Ch 16부터 조용히 아무 것도 안 하고 있었다.
- Ch 33: `ExplainabilityConfig`의 `require_reasoning` 기본값이 `True`
  라는 것을 몰라 응답에 사유가 없다는 이유로 계속 감점되고 있었다.
- Ch 36: `BranchGuardConfig`가 설정 파일엔 있었지만, `LiveGuardrail`을
  거치는 경로(OpenCode 플러그인/Claude Code 훅) 밖에서 셸을 직접 쓰는
  워크플로에는 애초에 적용되지 않고 있었다.

다섯 건 전부 원인이 달랐다(필드 의미 오해·숨은 기본값·오타·실행 경로
불일치) — 그런데 증상은 똑같았다: **"설정했는데 반응이 없다."** 이
스킬은 그 증상을 만났을 때 원인 종류를 좁혀나가는 절차다.

## 언제 발동하는가

- Config를 새로 켜거나 값을 바꿨는데 관련 Gate 점수/가드레일 판정이
  기대만큼(또는 전혀) 움직이지 않을 때
- "이 옵션이 진짜 작동하는지 모르겠다"는 의심이 들 때 — 증상이 나기
  전에 선제적으로 확인하고 싶을 때도 쓸 수 있다

## 절차 (4단계 — 원인 종류별로 좁혀간다)

1. **필드 의미부터 SDK 소스로 재확인한다.** `gates/gate_x/configs.py`의
   dataclass 정의와 `evaluators.py`의 실제 계산 로직을 직접 읽는다 —
   이름만 보고 동작을 추측하지 않는다(Ch 27의 `SubtaskConfig`가
   "파이프라인 추적"처럼 들리지만 실제로는 텍스트 매칭이었던 사례).
2. **숨은 기본값이 있는지 확인한다.** dataclass 필드의 기본값이
   `True`/`0`/특정 임계값으로 이미 정해져 있어, 아무것도 안 켰다고
   생각한 상태에서도 실제로는 감점/통과가 이미 일어나고 있을 수 있다
   (Ch 30의 `CostPredictabilityConfig`, Ch 33의 `require_reasoning`).
3. **문자열 값(카테고리 이름·패턴 등)이 SDK가 인식하는 정확한 철자와
   일치하는지 확인한다.** 오타는 예외를 던지지 않고 그냥 매칭 실패로
   조용히 넘어가는 경우가 많다(Ch 31의 `"card"` vs `"credit_card"`).
4. **실행 경로 자체가 맞는지 확인한다.** LiveGuardrail 계열 Config는
   그 Config를 넘긴 `LiveGuardrail`/`tool_guard`/훅 경로를 실제로
   타야만 작동한다 — 그 경로 밖(예: 셸 직접 실행, 별도 스크립트)에서는
   설정이 있어도 절대 발동하지 않는다(Ch 36의 `BranchGuardConfig`).
   가능하면 `agent-eval {claude,opencode} test-config`로 라이브 세션
   없이 그 경로 자체를 실측한다.

## 이 스킬이 하지 않는 것

- SDK 코드를 고치지 않는다 — 이 절차는 진단 전용이다. 원인이 SDK
  버그(예: 잘못된 타입 처리)로 판명되면 그건 별도의 수정 작업이다.
- Config가 "왜 이런 필드 설계를 택했는지"까지는 판단하지 않는다 —
  실제로 연결됐는지 여부만 좁혀낸다.

> 절차 정본: 이 워크북 Ch 27(SubtaskConfig)·Ch 30(CostPredictabilityConfig)·
> Ch 31(PII 카테고리 오타)·Ch 33(require_reasoning 기본값)·
> Ch 36(BranchGuardConfig 실행 경로) — 다섯 건 모두 실측으로 확인된
> 독립 사례. `docs/DESIGN_T-5E1FD6.md`에 각 사례의 사후 정정 기록이 있다.
