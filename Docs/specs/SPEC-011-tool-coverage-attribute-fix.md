# SPEC-011: Gate G `tool_coverage` 속성명 결함 수정

**Phase:** P1 (버그 수정, SPEC-000 후속) · **상태:** Implemented (2026-07-02) · **의존성:** SPEC-000(완료) — Gate G가 `gates/gate_g_observability/`로 이관된 상태에서 발견됨

> **구현 노트**: `monitor.py:2927`의 Gate G 위임 호출에서 `getattr(self, "tool_call_analyzer", None)`을 `self.tool_analyzer`(실제 속성)로 교체(REQ-1). `tests/test_gates_gate_g_migration.py`에 신규 `TestToolCoverageAttributeFix` 클래스(3건: 속성 존재 확인, 실제 도구 호출 시 `tool_coverage` 계산 검증, byte-diff 동등성) 추가, 기존 "latent bug preserved" 테스트는 "도구 호출 없을 때 여전히 None"으로 재의미화(REQ-3, REQ-4). 전체 스위트 2,943 passed, 1 skipped, 회귀 0건(순수 추가 3건 반영).

## Context

- `agent_evaluator/core/trackers/monitor.py:417` — `PerformanceMonitor.__init__`에서 도구 호출 트래커는 `self.tool_analyzer = ToolCallAnalyzer()`로 생성된다. 속성명은 `tool_analyzer`이며 `tool_call_analyzer`가 아니다.
- `agent_evaluator/core/trackers/monitor.py:1648-1652` — `record_task()`가 `task_result.tool_calls`가 있을 때마다 `self.tool_analyzer.analyze_execution(...)`을 호출해 이 트래커를 채운다. 즉 트래커 자체는 정상적으로 데이터를 축적한다.
- `agent_evaluator/core/trackers/monitor.py:2928` (SPEC-000 Gate G 이관 커밋에서 발견) — Gate G 집계 위임 호출이 `getattr(self, "tool_call_analyzer", None)`을 `gate_g_aggregate.compute()`에 전달한다. `tool_call_analyzer`라는 속성은 `PerformanceMonitor`에 존재한 적이 없다.
- SPEC-000 이전 원래 코드(`git show HEAD~1:agent_evaluator/core/trackers/monitor.py` 기준, 이관 전 인라인 버전)도 `self.tool_call_analyzer.get_efficiency_stats()`를 **동일한 오탈자로** 호출했고, 이 호출은 Gate G 블록 내부의 지역 `try: ... except Exception: pass`에 감싸여 있었다. 따라서 `AttributeError`가 항상 발생했지만 조용히 삼켜졌고, `_tool_coverage`는 **단 한 번도 계산되지 않고 항상 `None`** 이었다 — SPEC-000 감사에서 처음 발견된, SPEC-000 이전부터 존재하던 잠재 결함이다.
- SPEC-000의 Gate G 이관 과정에서 이 속성 접근이 `compute()` 호출부(즉 `try/except` 경계 밖)로 노출되면서 `AttributeError`가 `_compute_harness_groups()` 전체를 실패시켰다. 이를 즉시 막기 위해 임시로 `getattr(self, "tool_call_analyzer", None)`을 사용해 **기존의 침묵 실패("tool_coverage=None") 동작을 그대로 보존**했다(SPEC-000의 "완전한 동작 무변경" 계약을 지키기 위한 임시 조치). 이 스펙은 그 임시 조치를 실제 수정으로 교체한다.
- 결과적으로 `report.extra_metrics["harness_groups"]["G"]["details"]["tool_coverage"]`는 이 SDK가 출시된 이래(v0.9.x 전체) 도구를 호출하는 에이전트를 평가하더라도 항상 `None`이었다 — Gate G 점수에 `tool_coverage`가 기여한 적이 한 번도 없다.

## Goals

- `gate_g_aggregate.compute()`가 실제로 채워진 `ToolCallAnalyzer` 인스턴스(`self.tool_analyzer`)를 받아 `tool_coverage`를 정상적으로 계산하도록 수정한다.
- 이 수정이 Gate G 점수·`overall` 점수에 미치는 영향을 명시적으로 문서화하고 테스트로 고정한다(값이 처음으로 `None`이 아니게 되는 변화이므로 "버그 수정"이지만 관찰 가능한 출력이 바뀌는 변경이다).

## Non-Goals

- Gate F의 `coordination_score`/`avg_tool_selection_f1`, Gate G의 `tool_coverage` 자체에 대한 min-sample 가드 설계(SPEC-002 Non-Goals에서 이미 백로그로 분리됨) — 이 스펙은 속성명 결함만 다룬다.
- `ToolCallAnalyzer.get_efficiency_stats()`의 `success_rate` 계산 로직 자체의 재검토(이 스펙 범위 밖).
- `gates/shared_metrics.py` 통합 리팩터(SPEC-000 후속 작업으로 별도 분리됨, 이 스펙과 독립).

## Requirements

- **REQ-1**: `agent_evaluator/core/trackers/monitor.py`의 Gate G 위임 호출에서 `getattr(self, "tool_call_analyzer", None)`을 `self.tool_analyzer`로 교체한다.
- **REQ-2**: `tool_calls`가 기록된 태스크가 하나 이상 있는 세션에서 `harness_groups["G"]["details"]["tool_coverage"]`가 `None`이 아닌 실제 값(0.0–1.0)을 반환하는지 검증하는 테스트를 추가한다.
- **REQ-3**: `tool_calls`가 전혀 없는 세션(도구 미사용 에이전트, 예: 순수 QA)에서는 `ToolCallAnalyzer._executions`가 비어 있으므로 `get_efficiency_stats()["total_calls"] == 0`이 되어 기존과 동일하게 `tool_coverage=None`을 유지하는지 확인한다(회귀 없음 — 이 케이스는 이미 대부분의 기존 테스트 픽스처가 해당).
- **REQ-4**: `tests/test_gates_gate_g_migration.py::TestGateGMigrationEquivalence::test_tool_call_analyzer_latent_bug_preserved`를 이 수정에 맞게 갱신한다 — "크래시 없이 None 유지"를 검증하던 기존 목적에서 "정상적으로 실제 값을 계산"함을 검증하는 목적으로 전환한다.

## Interface

`PerformanceMonitor.generate_report()`의 반환값 스키마는 변경되지 않는다 — `tool_coverage` 키는 이미 존재했고 타입(`Optional[float]`)도 동일하다. 다만 **값 자체**가 도구 호출 태스크가 있는 세션에서 처음으로 `None`이 아니게 된다.

```python
# 수정 전 (도구 호출 태스크가 있어도 항상):
report.extra_metrics["harness_groups"]["G"]["details"]["tool_coverage"]  # None

# 수정 후 (도구 호출 태스크가 있으면):
report.extra_metrics["harness_groups"]["G"]["details"]["tool_coverage"]  # 예: 0.92
```

Gate G의 `_obs_vals`에 `tool_coverage`가 처음으로 실제 기여하게 되므로, 도구를 사용하는 에이전트의 **Gate G 점수와 `overall` 점수가 변할 수 있다**(다른 Gate G 하위 지표가 없는 경우 특히 영향이 크다).

## Acceptance

- `tool_calls`가 있는 태스크 픽스처에서 `tool_coverage`가 `ToolCallAnalyzer.get_efficiency_stats()["success_rate"] / 100.0`과 정확히 일치하는지 검증.
- `tool_calls`가 없는 기존 픽스처(대다수의 기존 테스트)에서 `tool_coverage`가 여전히 `None`인지 회귀 검증 — 전체 스위트 재실행으로 확인.
- `test_tool_call_analyzer_latent_bug_preserved`를 대체하는 신규 테스트가 실제 값 계산을 검증하는지 확인.

## Compatibility

- **하위호환 영향 있음(의도된 동작 변경)**: 도구 호출 에이전트를 평가하는 기존 사용자는 다음 `generate_report()` 호출부터 `tool_coverage`가 `None`에서 실제 값으로 바뀌고, 이에 따라 Gate G·overall 점수가 소폭 변동할 수 있다. CHANGELOG에 "버그 수정: Gate G tool_coverage가 이제 실제로 계산됩니다(이전에는 속성명 오류로 항상 None)"로 명시한다.
- CI/CD 게이트(`agent-eval gate`)를 사용하는 프로젝트가 Gate G 임계값을 설정해 두었다면, 이 수정 이후 처음으로 통과/실패 여부가 바뀔 수 있음을 릴리스 노트에 강조한다.

## Rollout

1. `monitor.py` REQ-1 수정 (1줄 변경).
2. `tests/test_gates_gate_g_migration.py`의 관련 테스트 갱신(REQ-4) + 신규 회귀 테스트 추가(REQ-2, REQ-3).
3. 전체 스위트 실행 후 SPEC-011 상태를 `Implemented`로 갱신.
4. CHANGELOG/릴리스 노트에 이 변경을 "버그 수정"으로 명시(마이너 버전 범프 권장 — 관찰 가능한 점수 변화를 동반하는 수정이므로).

## Risks

- Gate G·overall 점수가 실제로 바뀌므로, 이 SDK를 CI 게이트로 사용 중인 하류 프로젝트가 예기치 않게 임계값을 넘거나 못 넘을 수 있다 — 완화책: 릴리스 노트에 명시적 경고, 필요 시 `--tool-coverage-legacy-none` 같은 옵트아웃은 이번 스펙 범위에서는 추가하지 않는다(과도한 엔지니어링으로 판단, 버그 수정은 정확한 값을 제공하는 것이 옳다).
