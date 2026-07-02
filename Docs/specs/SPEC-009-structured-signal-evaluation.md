# SPEC-009: 구조화 신호 우선 평가 전환

**Phase:** P2 · **상태:** Draft · **의존성:** SPEC-000(Gate F/B의 `gates/gate_f_multiagent/`, `gates/gate_b_behavioral/` 이관) 선행 권장

## Context

- `agent_evaluator/helpers/taskresult_helpers.py`의 Gate F/B 평가 함수 대부분이 응답 **문자열**에 대한 키워드/정규식/토큰 중첩 비교로 구현되어 있다:
  - `eval_consensus`(2026-06-14 기준 `taskresult_helpers.py:2724` 부근) — 다중 에이전트 합의도를 `_token_overlap_ratio` 어휘 유사도로만 계산, 의미는 같지만 표현이 다른 응답은 불일치로 오판.
  - `eval_role_adherence`, `eval_explainability`, `eval_subtask_completion`, `eval_propagation` — 전부 `response_lower`/키워드 리스트/단어 경계 regex(F/Gate 버그 수정 이력에서 substring→word-boundary로 이미 개선되었으나, 여전히 텍스트 매칭이 근간).
- `agent_evaluator/integrations/framework_integrations.py`는 `to_graph_state`/`to_crew_inputs`/`to_task_string` 등 **입력 문자열을 프레임워크 호출 형태로 감싸는 I/O 어댑터**일 뿐, LangGraph의 노드 전이·CrewAI의 태스크 위임 이벤트 등 실행 트레이스를 실제로 캡처해 평가 신호로 공급하지 않는다(파일 헤더 주석: v0.8.0에서 직접 API 래퍼가 제거되고 텍스트 I/O 방식으로 대체됨).
- 구조화 데이터(`agent_interactions`, `tool_calls`)는 `eval_deadlock`에서만 실질적으로 사용된다 — 나머지는 구조화 데이터가 있어도 활용하지 않고 텍스트 매칭에 의존.
- README `Docs/specs/README.md`의 Definition of Done 목표 #3("Gate F/B가 텍스트 휴리스틱보다 구조화된 tool_calls/agent_interactions 우선 사용")을 실제로 달성할 스펙이 이전까지 존재하지 않았다(2026-07-02 재검토에서 확인된 누락).

## Goals

- Gate F(다중 에이전트 조정)와 Gate B(행동 무결성) 평가에서, `agent_interactions`/`tool_calls` 같은 구조화 데이터가 있으면 이를 **우선 사용**하고, 텍스트 매칭은 구조화 데이터가 없을 때의 **폴백**으로 격하한다.
- 이 우선순위를 코드 레벨에서 명시적으로 선언해(각 평가 함수가 "구조화 데이터 필요 여부"를 표명), 향후 어떤 지표가 여전히 텍스트 휴리스틱에만 의존하는지 한눈에 파악 가능하게 한다.

## Non-Goals

- LangGraph/CrewAI/AutoGen 실행 트레이스를 **자동 캡처**하는 신규 통합 코드(별도 스펙 후보, 이 스펙은 "구조화 데이터가 이미 `agent_interactions`/`tool_calls`에 채워져 있을 때 그것을 우선 사용하는 평가 로직 전환"까지만 다룬다).
- 텍스트 휴리스틱 자체의 완전 제거 — 구조화 데이터가 없는 경우를 위한 폴백으로는 계속 존재한다.

## Requirements

- **REQ-1**: `eval_consensus`가 `agent_interactions`에 각 에이전트의 응답이 구조화되어 존재하면(예: 의도/액션 필드가 포함된 형태), 어휘 유사도(`_token_overlap_ratio`) 대신 구조화 필드 간 일치 여부로 합의도를 판정한다. `agent_interactions`가 없거나 구조화 필드가 없으면 기존 텍스트 매칭으로 폴백한다.
- **REQ-2**: `eval_role_adherence`가 `tool_calls`에 도구명이 기록되어 있으면, `allowed_tools`/`forbidden_tools`(AgentRoleConfig)와 **직접 문자열 비교**(도구명 자체는 텍스트가 아니라 식별자이므로 키워드 오탐 위험이 없음)로 역할 준수를 판정하고, 텍스트 기반 액션 키워드 매칭은 `tool_calls`가 비어있을 때만 폴백으로 사용한다.
- **REQ-3**: `eval_propagation`이 `agent_interactions`의 각 홉(hop)에 원본 사실(fact)이 구조화된 필드로 전달되는 경우 이를 우선 대조하고, 텍스트 윈도우 기반 부정어 탐지는 구조화 필드가 없을 때만 사용한다.
- **REQ-4**: 각 평가 함수의 반환 dict에 `"signal_source": "structured" | "text_fallback"`를 추가해, 이번 평가가 구조화 데이터로 판정됐는지 텍스트 폴백으로 판정됐는지 명시한다(디버깅/신뢰도 표시용, Gate 점수 자체에는 영향 없음).
- **REQ-5**: 구조화 데이터 사용으로 인한 판정 변화가 기존 텍스트 매칭 결과와 달라질 수 있음을 CHANGELOG에 명시(스코어링 로직 변경이므로 SPEC-001/003과 달리 **byte-diff 동일성 보장 대상이 아니다** — 이 점이 핵심 차이).

## Interface

```python
# 변경 전
def eval_consensus(responses: List[str], config: ConsensusConfig) -> dict: ...

# 변경 후 (하위호환 — agent_interactions 없으면 기존과 동일 동작)
def eval_consensus(
    responses: List[str],
    config: ConsensusConfig,
    agent_interactions: Optional[List[dict]] = None,  # 신규, 선택
) -> dict:
    ...
    # 반환 dict에 "signal_source" 키 추가
```

## Acceptance

- `agent_interactions`가 구조화 필드를 포함한 픽스처에서 `signal_source == "structured"`이고, 워딩만 다른 두 응답(의미 동일)에 대해 텍스트 매칭 방식보다 합의도 판정이 안정적인지(분산이 낮은지) 비교 테스트.
- `agent_interactions` 미제공 시 기존 텍스트 매칭 결과와 100% 동일(회귀 테스트) — 폴백 경로는 SPEC-001/003 수준의 byte-diff 보장 대상.
- 실제 LangGraph/CrewAI 골든셋(가능하면 `examples/` 기존 픽스처 재사용)에 대해 구조화 신호 사용 전/후 Gate F/B 점수의 워딩-민감도(같은 의미, 다른 표현에 대한 점수 분산)를 비교 측정.

## Compatibility

- `agent_interactions`/`tool_calls` 파라미터는 선택(Optional) — 기존 호출 코드 수정 없이 동작.
- 구조화 데이터가 제공되는 경우에 한해 점수 산출 로직이 달라지므로, 이미 구조화 데이터를 채워 사용 중인 사용자는 스코어가 변경될 수 있음(additive 파라미터이지만 동작은 조건부로 변경 — REQ-5로 명시).

## Rollout

1. SPEC-000의 Gate F 이관(`gates/gate_f_multiagent/evaluators.py`) 완료 후 착수 — 새 위치에서 바로 구조화 우선 로직을 얹는 것이 이중 작업을 피하는 길.
2. `eval_consensus`(REQ-1) → `eval_role_adherence`(REQ-2) → `eval_propagation`(REQ-3) 순으로 하나씩, 각각 회귀 테스트 통과 후 병합.
3. Gate B의 동등 함수(있다면)는 Gate F 완료 후 동일 패턴 적용.

## Risks

- 구조화 신호와 텍스트 신호가 다른 결론을 낼 때 어느 쪽이 "맞는" 판정인지 자동 검증할 골든 정답이 없음 — 실제 프레임워크 트레이스 샘플을 이용한 수동 검토가 필요.
- `agent_interactions`의 구조화 필드 스키마가 프레임워크마다 달라(LangGraph vs CrewAI) 통일된 파싱이 어려울 수 있음 — 최소한 "필드가 있으면 사용, 없으면 폴백"의 안전한 하위호환 경로는 REQ-1~3으로 보장되므로, 특정 프레임워크만 먼저 지원하고 점진 확장 가능.
