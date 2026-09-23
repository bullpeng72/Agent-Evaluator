---
name: recommend-fix-workflow
description: Gate A-G 중 하나가 fail/warn일 때 코드를 고치기 전에 조치 후보를 조회하고(결과 파일이 있으면 insights.recommendations[], 없으면 recommend_fix MCP), 적용 후 §31.6/§31.7의 검증(verify_recommendation_outcome 또는 agent-eval improve verify)으로 실제로 통했는지 확인하는 절차. Gate 점수가 낮게 나온 직후, 조치를 코드로 옮기기 전에 사용한다.
aoo_dependency: full
---

# recommend_fix MCP — 조치 후보 조회 → 적용 → 검증

《하니스 메서드》 §31(Gate 하락 원인 진단 RCA)이 `recommend_fix` MCP 도구와 §31.6의 폐루프 검증 함수를 각각 다루지만, 실전에서는 이 둘을 하나의 절차로 이어 써야 한다 — 이 스킬이 그 순서를 표준화한다.

## 언제 쓰는가

- `agent-eval gate`/CI에서 특정 Gate가 fail 또는 warn으로 나왔을 때
- 아직 결과 파일이 없어도(개발 중인 에이전트를 아직 평가하지 않았어도) "이 Gate가 나쁘면 보통 뭘 하는가"를 먼저 알고 싶을 때 — `rca.diagnose()`와 달리 `recommend_fix`는 결과 파일 없이도 호출할 수 있는 더 가벼운 정적 지식 조회다.

## 사전 조건

MCP 서버가 등록돼 있어야 한다(AOO는 §7.1의 ③, AC는 §7.1.2 참고). `--with-recommend-fix`는 정적 조회용, `--with-ask-insights`는 결과 JSON의 `insights` 계층 조회용:

```bash
# AOO(OpenCode)
agent-eval opencode install --with-recommend-fix --with-ask-insights

# AC(Claude Code)
agent-eval claude install --with-recommend-fix --with-ask-insights
```

둘 다 옵트인 의존성이 필요하다: `pip install "agent-evaluator[mcp]"`. (결과 파일에서 `insights.recommendations[]`를 직접 파싱한다면 MCP 없이도 가능하다.)

## 절차

### 1단계 — 조치 후보 조회

**결과 파일이 있으면 — `insights.recommendations[]`를 먼저 읽는다.** `save_to_file()`이 쓰는 결과 JSON의 `extra_metrics.insights.recommendations[]`에는 이 프로젝트를 실제로 진단한 결과가 이미 들어 있다: fail/warn Gate별 `proposal`(붙여넣을 `@agent_eval` 스니펫) + `prior`(이 Gate·변경 카테고리의 과거 confirm-rate 실적, `improvement_priors`) + `experiment`(예측 Δ + 권장 표본). `ask_insights` MCP가 등록돼 있으면 `insights_readiness` / `insights_why_failed(task_id)`로 대화 중 바로 조회한다. 정적 `recommend_fix`보다 항상 우선한다 — 이쪽은 이 결과를 실제로 본다.

**결과 파일이 아직 없으면 — `recommend_fix`(정적 폴백).** fail/warn Gate와 `harness_groups.<Gate>.details`에서 가장 많이 움직인 세부 지표를 넘긴다:

```
recommend_fix(gate="F", metric="conflict_resolution", value=0.42)
```

반환값은 Gate 레벨 안내 + (규칙이 있으면) 세부 지표 임계값 판정 + (Gate F라면) MAST 실패모드 후보로 구성된다 — 항상 "이 안내는 후보 조치일 뿐입니다"로 끝난다. `recommend_fix`는 결과 파일이 없어도 호출할 수 있는 대신, 이 프로젝트를 진단한 게 아니라 "이 Gate가 나쁘면 보통 뭘 하나"의 정적 지식이다. 단, 이 프로젝트가 `.aoo` 개선 이력을 쌓아 왔다면(3단계의 `--persist`) 정적 안내 끝에 "이 유형의 변경은 이 Gate에서 과거 N건 중 M건 확인됨" 한 줄이 붙는다(표본 3건 미만이면 "표본 부족" 라벨). 변경 유형을 알면 `recommend_fix(gate=..., category="config_change")`처럼 좁혀 그 유형의 실적만 볼 수도 있다.

> 🚨 **이 응답을 그대로 코드에 옮기지 마라.** `recommend_fix`는 정적 지식 조회이지, 이 프로젝트를 실제로 진단한 결과가 아니다 — 여러 Gate가 동시에 떨어졌다면 먼저 §31.2(복합 사례 진단)를 따라 details를 열어 원인을 좁힌 뒤에 조치 후보를 조회하라. `gate`만 주고 `metric`을 생략하면 Gate 레벨의 일반 안내만 나오므로, 가능하면 details에서 실제로 움직인 지표명을 함께 넘겨라.

### 2단계 — 조치 적용

`recommend_fix`가 제시한 방향을 참고해 실제 코드/프롬프트/Config를 수정한다. 이 단계는 사람이 판단한다(HOTL) — 도구는 후보만 제시했을 뿐, 이 코드베이스에 맞는지는 검증되지 않았다.

### 3단계 — 재평가 후 검증

조치 적용 후 재평가를 돌리고, §31.6의 세 함수로 폐루프를 닫는다:

```python
from agent_evaluator.rca.verify import verify_recommendation_outcome
from agent_evaluator.rca.recommendation_tracking import record_recommendation_outcome

verdict = verify_recommendation_outcome(
    before, after, target_gate="F", target_field="conflict_resolution",
)
record_recommendation_outcome(
    "results/recommendation_outcomes.jsonl",
    recommendation_id="REC-<임의 식별자>",
    target_gate="F", before=before, after=after, target_field="conflict_resolution",
    note="recommend_fix가 제시한 <조치 요약>",
)
```

`verdict["verdict"]`가 `"confirmed"`가 아니면(refuted/inconclusive) 1단계로 돌아가 다른 조치 후보를 찾거나, §31.1의 5 Whys로 더 깊이 파고든다. 위 두 함수를 한 번에 돌리려면 `agent-eval improve verify <after>.json --baseline <before>.json --persist`(§31.7). `--persist`가 쌓은 이력이 다음 실행의 `insights.improvement_priors`가 된다 — 순위·자동추천이 아니라 사람이 참고하는 confirm-rate 실적이다.

## 체크리스트

- [ ] 결과 파일이 있으면 `insights.recommendations[]`(proposal + prior + experiment)를 먼저 읽었고, 없을 때만 `recommend_fix(gate=..., metric=..., value=...)` 정적 조회로 폴백했다.
- [ ] 반환된 조치 후보를 그대로 적용하지 않고, 이 코드베이스 맥락에 맞는지 검토했다(HOTL).
- [ ] 조치 적용 후 `verify_recommendation_outcome()`(또는 `agent-eval improve verify --persist`)으로 실제 개선 여부를 확인했다.
- [ ] `record_recommendation_outcome()`으로 판정을 `recommendation_outcomes.jsonl`에 남겨, 다음 실행의 `insights.improvement_priors`가 track record로 쌓이게 했다.
