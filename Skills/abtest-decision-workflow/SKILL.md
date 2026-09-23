---
name: abtest-decision-workflow
description: "`agent-eval abtest`로 두 버전(또는 세 버전 이상)을 비교하기 전에 주 지표(guardrail metric)를 미리 정하고, 결과를 책임 있게 해석한다. 버전 비교 결과를 놓고 \"어느 쪽을 채택할지\" 의사결정하는 시점에 사용한다."
aoo_dependency: full
---

# A/B 테스트 의사결정 절차

《하니스 메서드》 §20.5(`agent-eval abtest`)가 제공하는 통계 검정(Welch's t-test / N-way + Benjamini-Hochberg FDR / mSPRT sequential)을 실제 버전 채택 의사결정에 책임 있게 연결하는 절차다. `agent-eval abtest`는 CI 게이트가 아니다 — 사람이 두 버전 중 하나를 고르는 걸 돕는 의사결정 지원 도구이지, `agent-eval gate`처럼 자동으로 병합을 막는 장치가 아니다. 이 스킬은 그 사람의 판단을 구조화한다.

## 절차

### 1. 결과를 보기 전에 주 지표를 미리 정한다

`--metric`으로 넘길 지표(예: `accuracy_score`, `completion_score`, 특정 Gate의 `details` 키)를 **결과 파일을 열어보기 전에** 정해 팀 채널이나 PR 설명에 남긴다. 결과를 먼저 보고 나서 "가장 좋게 나온 지표"를 주 지표로 고르면, 그 순간부터 이 통계 검정은 의미를 잃는다 — `human-approval-loop` 스킬이 HITL 개입 지점을 세션 *전에* 정의하는 것과 같은 사전 등록(pre-registration) 원칙이다.

```bash
# 예: PR 설명에 먼저 기록 — "이번 비교의 주 지표는 accuracy_score다"
agent-eval abtest results/v1.json results/v2.json --metric accuracy_score
```

### 2. 비교 횟수에 맞는 모드를 고른다

| 상황 | 쓸 모드 | 이유 |
|---|---|---|
| 두 버전을 **딱 한 번**만 비교하고, 결과가 나올 때까지 기다릴 수 있다 | 기본 Welch's t-test | 사전에 정한 표본 크기까지 실행한 뒤 한 번만 확인한다는 전제가 있어야 유의성이 정확하다 |
| 결과가 쌓이는 대로 **여러 번 들여다보고** 싶다("피킹") | `--sequential --tau <값>`(mSPRT) | 고전 t-test를 반복 관찰하면 그 자체로 거짓양성률이 치솟는다 — mSPRT는 매 관찰이 항상 유효하도록 설계된 always-valid 방법이다(§20.5) |
| 버전이 **3개 이상** | 파일 3개 이상을 그대로 넘긴다 → N-way 자동 전환 | 쌍마다 개별 t-test를 반복하면 다중비교 문제로 거짓양성이 누적된다 |

- [ ] 아직 표본이 다 안 모였는데 중간 결과가 궁금해서 기본 모드를 여러 번 돌리고 있지는 않은가 — 그렇다면 지금 `--sequential`로 바꿔야 한다.

### 3. N-way 결과는 FDR 보정값을 본다

버전이 3개 이상이면 원시 쌍별 p-value가 아니라 Benjamini-Hochberg로 보정된 유의성 판정을 따른다. 원시 p-value로 "이 쌍은 유의미해 보인다"고 판단하면, 비교 쌍이 늘어날수록 우연히 유의미해 보이는 결과가 누적된다는 걸 §20.5의 다중비교 경고가 이미 설명한다.

### 4. 출력은 의사결정 입력이지, 자동 게이트가 아니다

`agent-eval abtest`의 종료 코드나 출력을 CI 파이프라인의 병합 차단 조건으로 직접 연결하지 않는다. 병합을 막아야 하는 절대적 품질 기준(TCR·Gate 점수 임계값·골든셋 회귀)은 `agent-eval gate`의 몫이고(CI 게이트), `abtest`는 "이미 둘 다 품질 기준은 통과했는데, 어느 쪽이 더 나은가"를 사람이 판단하도록 돕는 몫이다. 대시보드 File Compare 탭의 ⚖️ Pairwise Judge 서브탭(§20.5의 개발자 TIP 참고)처럼 숫자 하나로 요약 안 되는 정성적 판단이 필요하면 그쪽을 함께 참고한다.

## 체크리스트

- [ ] 주 지표(`--metric`)를 결과를 보기 전에 정해 기록해뒀다.
- [ ] 비교 횟수(1회 vs 반복 관찰 vs 3버전 이상)에 맞는 모드를 선택했다.
- [ ] N-way라면 원시 p-value가 아니라 FDR 보정 결과를 기준으로 판단했다.
- [ ] `abtest` 결과를 CI 병합 차단 조건으로 직접 연결하지 않았다 — 최종 채택 여부는 사람이 결정한다.
- [ ] 채택 근거(주 지표 값, 통계 모드, 최종 판단)를 PR 설명이나 ADR에 남겼다.
