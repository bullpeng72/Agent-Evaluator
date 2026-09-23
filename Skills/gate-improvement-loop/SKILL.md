---
name: gate-improvement-loop
description: 하나의 Gate 점수를 목표선 위로 올리는 반복 절차. agent-eval improve plan(또는 insights.readiness.fix_plan)으로 TCR 영향 순 제안을 받거나 harness_groups.<Gate>.details를 성분별로 열어 가장 낮은 성분의 실패 케이스를 모으고, 한 번에 한 가지만 바꿔 재측정한 뒤 이터레이션 로그에 남긴다. agent-eval gate에서 특정 Gate가 fail/warn으로 나온 직후, 한 Gate를 집중적으로 개선하는 세션에서 사용한다.
aoo_dependency: full
---

# Gate 개선 루프 — 성분 분해 → 한 가지 수정 → 재측정 → 기록

《하니스 메서드》 §21(개발 — TDD-AI 워크플로우)이 정의한 반복을, **하나의 Gate에 집중할 때**의 절차로 좁힌 것이다. `tdd-ai-workflow-checklist`가 "실패 골든셋 케이스 → 최소 구현 → 버전 비교"라는 red-green-refactor 전체 순환을 다룬다면, 이 스킬은 그 refactor 단계에서 "Gate C가 0.61인데 0.85로 올려야 한다" 같은 **한 Gate 목표**를 어떤 순서로 공략하는가를 표준화한다. `recommend-fix-workflow`는 이 루프의 2단계(원인 후보 조회)에 끼워 넣는다.

## 왜 "성분"부터 여는가

Gate 점수(예: `harness_groups.C.score = 0.61`)는 여러 세부 지표(`reproducibility` · `faithfulness` · `graceful_degradation` …)의 집계다. 총점만 보고 프롬프트를 통째로 고치면, 어느 성분이 실제로 문제였는지 모른 채 여러 변경을 한꺼번에 섞게 되고 — 점수가 올라도 무엇이 통했는지, 내려도 무엇이 원인인지 알 수 없다. `agent-eval abtest`·`--baseline-version`이 "달라졌는가"를 재려면, **한 번에 한 가지만** 바뀌어 있어야 한다(원칙②의 "증명" 요건).

## 절차

### 1. 성분을 연다 — `improve plan`, 없으면 details 직접

**우선 경로 — `agent-eval improve plan`** (baseline이 있으면):

```bash
agent-eval improve plan results/v3.json --baseline results/v2.json
# → fail/warn Gate마다 개선 제안을 TCR 영향 순으로. 결과 JSON의 insights.readiness.fix_plan과 같은 것:
#   각 항목에 impact_pct · effort_hint · targets_gates · projected_tcr_after_pct
```

`insights.readiness.fix_plan`을 직접 파싱해도 된다 — `rank`·`impact_pct`·`effort_hint`·`projected_gate_scores`가 이미 계산돼 있어, "이번 라운드가 목표선에 얼마나 근접시키는가"를 조치 전에 추정할 수 있다.

**폴백 — `details`를 손으로 연다** (baseline이 없거나, `plan`이 무엇을 보고 그렇게 정렬했는지 확인하고 싶을 때):

```python
import json
report = json.load(open("results/evaluation.json"))
details = report["extra_metrics"]["harness_groups"]["C"]["details"]
# 예: {"reproducibility": 0.55, "faithfulness": None, "graceful_degradation": 0.90, ...}
```

- [ ] `improve plan`(또는 `insights.readiness.fix_plan`)이 제시한 상위 항목, 또는 `details`에서 가장 낮은(또는 `None` = 미측정) 성분 하나를 이번 라운드의 대상으로 정했다.
- [ ] `None`이라면 "낮다"가 아니라 "안 재고 있다"이므로, 먼저 그 성분을 켜는 Config·데이터부터 붙인다(예: `faithfulness`가 `None`이면 `enable_llm_judge=True` + 채점할 응답이 실제로 생성되는지).
- [ ] `plan`의 제안은 **후보**다 — §31.2(복합 사례)를 아직 안 배제했다면 아래 2단계에서 먼저 배제한다.

### 2. 실패 케이스를 5~10건 모아 공통 패턴을 찾는다

대상 성분이 낮게 나온 개별 태스크를 골든셋에서 추려 직접 읽는다. 목표는 "이 10건이 왜 낮은가"의 **한 문장 가설**이다.

- 결과 파일 없이 "이 성분이 낮으면 보통 뭘 하나"부터 알고 싶으면 여기서 `recommend-fix-workflow`를 실행한다 — `recommend_fix(gate="C", metric="reproducibility", value=0.55)`.
- 여러 Gate가 동시에 떨어졌다면 이 스킬을 각 Gate에 따로 돌리기 전에, 《하니스 메서드》 §31.2(복합 사례)로 공유 원인부터 배제한다(예: SLA breach가 Gate C·D를 동시에 눌렀는지).

- [ ] 대상 성분의 실패 케이스 5건 이상을 실제로 읽고, 공통 원인 가설을 한 문장으로 적었다.

### 3. 한 번에 한 가지만 바꾼다

프롬프트 **또는** 코드 **또는** Config 중 하나만. 두 가지를 같이 바꿔야 할 것 같으면, 두 라운드로 나눈다.

- [ ] 이번 라운드의 변경이 "한 가지"로 요약된다(diff가 여러 파일이어도 논리적으로 하나의 결정인가).
- [ ] 설계 문서(§17)가 지정한 스코프 밖 파일은 건드리지 않았다.

### 4. 재측정하고 직전 버전과 비교한다

```bash
# 버전 태깅 — 커밋 안 해도 dirty-hash로 구분된다
# monitor = PerformanceMonitor(agent_version="auto", iteration_note="C: 온도 0으로 재현성")
<팀의 배치 채점 실행>   # 세션을 재실행해 results/evaluation.json을 새로 만든다
agent-eval gate results/evaluation.json --baseline-version <직전 버전>
```

- [ ] 대상 성분이 before→after로 올랐다.
- [ ] **다른 성분·다른 Gate가 회귀하지 않았다.** 회귀했다면, 대상 성분이 좋아졌어도 이 변경을 되돌리고 3단계로 돌아간다(§21의 "회귀는 되돌린다").
- [ ] 통계적 증명이 필요하면 `abtest-decision-workflow`로 주 지표를 사전 등록하고 `agent-eval abtest`를 돌렸다.

### 5. 이터레이션 로그에 한 줄 남긴다

이터레이션 로그 파일(예: `ITERATIONS.md`, 또는 팀 규약 파일)에 append:

```
<version> · <무엇을 바꿈> · <대상 성분> before→after · <증명: abtest p=… / 위반건수 0 / --baseline-version 통과>
```

조치가 "recommend_fix가 제시한 방향"이었다면, `recommend-fix-workflow`의 3단계대로 `verify_recommendation_outcome()` + `record_recommendation_outcome()`으로 `recommendation_outcomes.jsonl`에도 판정을 남긴다 — 또는 한 번에 `agent-eval improve verify results/v4.json --baseline results/v3.json --persist`. 이 로그가 쌓이면 다음 실행의 `insights.improvement_priors`가 (Gate, 변경 카테고리)별 confirm-rate 실적으로 보여준다(순위·자동추천이 아니라 참고용 — §31.7).

- [ ] ITERATIONS 로그에 version·변경·before→after·증명이 한 줄로 남았다.
- [ ] 목표선(예: `>= 0.85`)에 아직 못 미쳤으면 1단계로 돌아간다(다음으로 낮은 성분).

## 체크리스트

- [ ] `improve plan`(또는 `insights.readiness.fix_plan`)의 상위 항목, 없으면 `details`의 가장 낮은 성분 하나를 대상으로 정했다(총점이 아니라 성분 단위).
- [ ] 대상 성분의 실패 케이스를 실제로 읽고 원인 가설을 한 문장으로 세웠다.
- [ ] 이번 라운드에서 프롬프트·코드·Config 중 **한 가지만** 바꿨다.
- [ ] `--baseline-version`으로 재측정해 대상 성분이 올랐고 다른 성분이 회귀하지 않았음을 확인했다(회귀 시 롤백).
- [ ] 이터레이션 로그에 version·변경·before→after·증명을 한 줄로 남겼다.
- [ ] 목표선 미달이면 다음으로 낮은 성분으로 루프를 반복했다.
