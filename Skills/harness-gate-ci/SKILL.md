---
name: harness-gate-ci
description: agent-eval gate를 CI에 연결한다 — 절대 임계값(exit 1) · baseline 회귀(exit 2) · 골든셋 회귀(exit 3) · 케이스 회귀/리뷰 큐(exit 4) · 판정 보류(exit 75)를 별개의 CI 스텝으로 나누고, 종료 코드별로 다른 알림으로 라우팅한다. 팀 회귀 게이트를 새로 도입하거나, 기존 CI 파이프라인에 Gate 게이팅이 빠져 있는지 점검할 때 사용한다.
aoo_dependency: full
---

# Harness Gate CI 연결 절차

《하니스 메서드》 §13(브랜치 보호와 CI 감사)·§30(PR 검증과 팀 기준 재확인)이 다루는 "회귀를 병합 전에 자동으로 막는다"를 CI 스텝으로 굳히는 절차다. 새 판정 로직이 아니다 — `agent-eval gate`(내부적으로 `gates/base.py::evaluate_gate_scores()` + `_compute_gate_regressions()`)를 CI 잡으로 등록할 뿐이다. `claims-audit-ci`가 `agent-eval claims audit`를 CI의 마지막 안전망으로 굳히는 것과 같은 위치이며, 보통 같은 워크플로우에 나란히 둔다.

## 실패 유형별로 스텝을 나눈다

`agent-eval gate`는 무엇으로 실패했는지에 따라 종료 코드가 다르다(1~4, 그리고 옵트인 `--hold-on-undecided`의 75). 한 스텝에 다 넣으면 CI 로그만 보고는 "임계값 미달"인지 "기준선 대비 후퇴"인지 구분이 안 되고, 알림도 뭉뚱그려진다.

| 종료 코드 | 무엇이 실패했나 | 필요한 플래그 | 이 실패가 뜻하는 것 |
|---|---|---|---|
| **1** | 절대 임계값 미달 | `--tcr` · `--accuracy` · `--gate-thresholds` | 이 버전은 팀이 정한 최소선 자체를 못 넘겼다 — 병합 불가 |
| **2** | baseline 대비 회귀 | `--baseline-version <태그>` `--fail-on-regression <허용폭%>` | 임계값은 통과했지만 직전 확정 버전보다 나빠졌다 — "통과"와 "회귀 없음"은 다른 질문(§20.4) |
| **3** | 골든셋 회귀 | `--golden-set <파일>` `--fail-on-golden-regression` | 인수 기준(§15.4)으로 삼은 케이스에서 후퇴했다 — 지표 평균은 괜찮아도 핵심 케이스가 깨졌을 수 있다 |
| **4** | 케이스 단위 회귀 / 리뷰 큐 초과 | `--baseline-result <이전 result.json>` `--fail-on-case-regression`, 또는 `--max-review-high <N>` | 이전 실행에서 통과한 태스크가 이번에 실패했다(골든셋에 없어도), 또는 자동 판정을 못 믿을 태스크(`insights.review_queue` HIGH)가 N개를 넘었다 |
| **75** | 판정 보류 (통과처럼 보이지만 통계적으로 애매) | `--hold-on-undecided` | 절대 게이트는 통과했지만 합격률 신뢰구간이 목표선을 걸치거나 판정이 임계선 ±0.05에서 뒤집힌다 — 자동 통과 대신 사람이 확인해야 한다(원칙 6). 명백한 실패(1~4)는 이 플래그로 덮이지 않는다 |

## 절차

### 1. baseline을 산출물로 커밋한다

`--baseline-version`이 읽는 기준선(`results/baselines/<태그>.json`)은 자동 파생물이 아니라 **명시적으로 저장·버전관리하는 산출물**이어야 한다(《하니스 메서드》 §20.4.3). `.gitignore`가 `results/`를 무시하더라도 `!results/baselines/` 예외를 둔다.

- [ ] 현재 메인 브랜치의 확정 리포트를 `results/baselines/main-latest.json`으로 커밋했다.
- [ ] 골든셋(`data/golden_datasets/*.json`)도 커밋돼 있고, `IRREVERSIBLE` 목록(또는 동급 문서)이 이 파일들을 정답 소스로 지목한다.

### 2. 스텝을 워크플로우에 추가한다 (필수 3 + 선택 1)

```yaml
# .github/workflows 예시 — 평가 리포트 생성 뒤에 이어서
- name: Gate — 절대 임계값
  run: agent-eval gate results/ci_run.json --tcr 85 --accuracy 70
  # exit 1 → 최소선 미달

- name: Gate — baseline 회귀
  run: agent-eval gate results/ci_run.json --baseline-version main-latest --fail-on-regression 10
  # exit 2 → 직전 확정 버전 대비 10%p 넘게 후퇴

- name: Gate — 골든셋 회귀
  run: agent-eval gate results/ci_run.json --golden-set data/golden_datasets/golden_core.json --fail-on-golden-regression
  # exit 3 → 인수 기준 케이스 후퇴

- name: Gate — 케이스 회귀 / 리뷰 큐   # 선택 — 골든셋에 없는 태스크까지 잡고 싶을 때
  run: agent-eval gate results/ci_run.json --baseline-result results/baselines/main-latest.json --fail-on-case-regression --max-review-high 0
  # exit 4 → 이전 통과 태스크가 실패, 또는 리뷰 큐 HIGH 초과

- name: Gate — 판정 보류   # 선택 — "통계적으로 애매한 통과"를 사람 확인으로 돌린다
  run: agent-eval gate results/ci_run.json --tcr 85 --hold-on-undecided
  # exit 75 → 절대 게이트는 통과했지만 통계적으로 borderline. 파이프라인이 75를 별도 처리해야 의미가 있다
```

각 스텝을 독립 실행하려면 `continue-on-error`로 앞 스텝이 실패해도 나머지가 돌게 하고, 마지막에 하나라도 실패했으면 잡을 실패시키는 집계 스텝을 둔다.

### 3. 종료 코드별로 알림을 라우팅한다

- **exit 1** → PR 작성자에게 "최소 품질선 미달, 병합 불가". 리뷰어 소환하지 않는다(아직 볼 게 없다).
- **exit 2** → PR 작성자 + 직전 baseline을 만든 사람. "무엇이 회귀했는가"를 `agent-eval diagnose`(§31)로 좁히도록 안내. 의도된 트레이드오프라면 사람이 baseline을 갱신하고 재실행한다(자동 갱신 금지 — §20.4.3).
- **exit 3** → PR 작성자 + 골든셋 라벨러. 어느 케이스가 깨졌는지 함께 확인. 케이스 자체가 나쁜 것으로 판명되면 골든셋에서 제외하는 것도 유효한 결정이다(§15.4).
- **exit 4** → PR 작성자 + QA. `insights.review_queue`가 지목한 태스크를 사람이 읽고, 회귀가 진짜면 `agent-eval dataset promote`로 골든셋에 편입(다음부터 exit 3에서 잡힘)한다.
- **exit 75** → PR 작성자 + QA. 병합을 막되 "실패"로 표시하지 않는다 — 리포트의 `insights.verdict.undecided_reason`을 읽고, 표본을 늘리거나(케이스 추가) 릴리스 후보라면 같은 평가를 K회 재실행해(`nondeterminism_repeat`) 판정이 안정적인지 확인한 뒤 사람이 병합 여부를 정한다.

- [ ] 스텝이 분리돼 있고, CI 로그·알림에서 exit 1/2/3(/4)(/75)이 구분된다.
- [ ] exit 2에서 baseline을 CI가 자동 갱신하지 않는다 — 갱신은 사람의 명시적 커밋으로만.
- [ ] `--hold-on-undecided`를 쓴다면, CI 파이프라인이 종료 코드 75를 "일반 실패"가 아니라 "사람 확인 대기"로 별도 처리한다.

### 4. `agent-eval gate`는 막고, `abtest`·`diagnose`는 막지 않는다

병합 차단은 `agent-eval gate`의 몫이다. `agent-eval abtest`(어느 버전이 더 나은가 — `abtest-decision-workflow`)와 `agent-eval diagnose`(왜 떨어졌나 — §31, 항상 exit 0)는 **CI 병합 조건으로 연결하지 않는다.** 이 셋을 섞으면 "왜"를 좁히는 도구가 "막는" 역할을 떠맡아 원칙③(차단과 채점의 분리)이 무너진다.

## 체크리스트

- [ ] baseline 리포트와 골든셋이 커밋된 산출물로 존재한다(`!results/baselines/` 예외 포함).
- [ ] 절대 임계값 · baseline 회귀 · 골든셋 회귀가 **분리된 CI 스텝**이다(선택으로 케이스 회귀/리뷰 큐 스텝 추가).
- [ ] 종료 코드 1/2/3(/4)이 각각 다른 대상에게 다른 안내로 알림된다.
- [ ] exit 2에서 baseline은 사람이 명시적으로 갱신한다 — CI 자동 갱신 없음.
- [ ] `abtest`·`diagnose`는 CI 병합 차단 조건에 연결하지 않았다.
- [ ] (같은 워크플로우라면) `claims-audit-ci`의 클레임 감사 스텝도 함께 있다.
