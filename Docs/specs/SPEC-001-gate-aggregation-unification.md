# SPEC-001: Gate 집계 단일 소스화

**Phase:** P1 · **상태:** Draft — [SPEC-000](SPEC-000-gate-package-decomposition.md)의 REQ-1로 흡수됨 · **의존성:** SPEC-003(단일 패스 정리)을 먼저 끝내는 것을 권장

> **2026-07-02 재검토 노트**: 이 스펙의 요구사항(REQ-1~4)은 별도로 구현하지 않고, SPEC-000의 Gate별 이관 작업(`gates/gate_x/aggregate.py` 작성 시) 안에서 함께 처리한다. 이 문서는 REQ 상세 근거 자료로 유지한다.

## Context

- `agent_evaluator/core/trackers/monitor.py:2779-4064` `_compute_harness_groups` — SDK가 태스크를 직접 기록해 리포트를 생성할 때 쓰는 **정식** Gate A~G 계산 로직 (~1,285줄, 단일 메서드).
- `agent_evaluator/serve/loader.py:744-812` `_compute_harness_groups_fallback` — 대시보드가 `extra_metrics.harness_groups`가 없는 (레거시) JSON을 읽을 때 쓰는 **별도 재구현**. 두 로직은 수식 자체가 다르다:
  - Gate A: 정식은 `0.4×TCR + 0.6×(accuracy/quality/...)` 가중 블렌딩, fallback은 `(tcr_pct/100 + overall_acc)/2` 단순 평균.
  - Gate B: 정식은 loop/scope/deadlock/state-consistency/tool-param-safety/context-window 6개 지표, fallback은 `tcr_pct/100 × 0.95` 단일 프록시로 실제 지표를 전혀 사용하지 않음.
  - Gate D: 정식은 Efficiency/ResourceBudget/TTFT/CostPredictability 종합, fallback은 p95 레이턴시 하나만으로 `<5→1.0, <10→0.7, else 0.3` 하드코딩 임계값.
  - Gate F: 정식은 Consensus/Propagation/RoleAdherence/ConflictResolution 종합, fallback은 `coordination_success_rate` 하나만 사용.
- `loader.py:323` `ResultFile.has_harness` 플래그가 존재하지만, `_parse_harness_data`(`loader.py:827` 이하)는 `has_harness` 여부와 무관하게 **항상** `harness_groups` 딕셔너리를 채워 반환한다. `has_harness`는 대시보드 메인 Harness 섹션의 노출 여부(`dashboard.html.j2:729,736`, `x-show="data.has_harness"`)만 제어하므로, 다른 소비처(CLI `gate`/`trend`, export 등)가 `has_harness`를 확인하지 않고 `harness_groups` 값을 그대로 사용하면 근사값을 정식 값처럼 노출할 위험이 있다.
- Gate D/E/F에서 이미 수정된 17건 이상의 로직 버그(falsy-trap, substring-vs-word-boundary 등)는 `monitor.py`에만 반영되어 있고, `loader.py`의 fallback 수식 자체가 다르므로 애초에 적용될 여지가 없다.

## Goals

- Gate A~G 계산 로직을 **하나의 라이브러리**로 통합해 `monitor.py`와 `serve/loader.py`가 동일한 함수를 호출하도록 만든다.
- 원본 tracker 데이터가 없는 개별 지표만 결측(`None`) 처리하고, 있는 지표는 정식 공식을 그대로 적용한다 (Gate 전체를 다른 수식으로 대체하지 않는다).

## Non-Goals

- Gate 가중치 자체의 재설계(`gate_a_tcr_weight` 등 기본값 변경) — 별도 스펙.
- 대시보드 UI/템플릿 리디자인.

## Requirements

- **REQ-1**: `agent_evaluator/gates/` 패키지의 각 `gate_x.compute(...)` 함수는 `List[TaskResult]`(모니터 경로)와 이미 직렬화된 `report: dict`(사후 로딩 경로) 두 입력 형태를 모두 받아들일 수 있어야 한다.
- **REQ-2**: 특정 지표의 원본 tracker 데이터가 없으면 해당 지표만 `None` 처리하고, 나머지 사용 가능한 지표는 정식 가중치/정규화 공식으로 계산한다.
- **REQ-3**: 근사 계산(원본 tracker 배열이 없어 일부 지표가 결측된 경우)이 하나라도 발생한 Gate의 출력에는 `"approximated": true`를 명시적으로 포함한다. 모든 지표가 정상 계산되면 `"approximated": false`.
- **REQ-4**: `serve/loader.py::_compute_harness_groups_fallback`을 제거하고, `gates/` 패키지의 REQ-1 함수를 직접 호출하도록 전환한다.

## Interface

**변경 전:**
```python
# monitor.py
class PerformanceMonitor:
    def _compute_harness_groups(self, tasks: List[TaskResult]) -> Dict[str, Any]: ...

# serve/loader.py
def _compute_harness_groups_fallback(report: dict) -> Dict[str, Any]: ...  # 별도 수식
```

**변경 후:**
```python
# agent_evaluator/gates/__init__.py
def compute_all_gates(
    tasks: Optional[List[TaskResult]] = None,
    report: Optional[dict] = None,
    config: Optional[GateConfig] = None,
) -> Dict[str, Any]:
    """tasks 또는 report 중 하나를 받아 A~G 딕셔너리를 반환.
    개별 지표 결측 시 None 처리, Gate 단위 approximated 플래그 포함."""
```

`monitor.py._compute_harness_groups`와 `loader.py._compute_harness_groups_fallback`는 이 함수의 얇은 래퍼로 축소되거나 제거된다.

## Acceptance

- 정식 tracker 데이터가 모두 있는 `report.json` 픽스처를 `monitor.py` 경로와 `gates.compute_all_gates(report=...)` 경로 양쪽에 태워 Gate 점수가 **소수점 4자리까지 완전 일치**하는 회귀 테스트.
- 일부 지표만 결측된 픽스처에서 해당 지표만 `None`, 나머지는 정식 공식 값이 나오는지 검증.
- `approximated` 플래그가 결측 지표 유무와 정확히 일치하는지 검증.

## Compatibility

- `harness_groups` JSON 스키마는 기존 키를 유지하고 `"approximated"` 키만 추가 (additive, non-breaking).
- 기존 2,795개 테스트 전량 통과 필수.

## Rollout

1. `gates/` 패키지에 `compute_all_gates` 구현 (SPEC-003 완료 후 착수 권장 — 계산 순서 보존이 더 쉬움).
2. `monitor.py`가 내부적으로 이 함수를 호출하도록 전환, 기존 공개 메서드 시그니처 유지.
3. `serve/loader.py`가 동일 함수를 호출하도록 전환, `_compute_harness_groups_fallback` 삭제.
4. CHANGELOG에 "과거 파일(레거시 fallback 대상)의 근사 점수가 정식 공식으로 갱신됨"을 명시.

## Risks

- 레거시 결과 파일(Phase 1 이전 생성, `harness_groups` 키 없음)을 다시 열람할 때 기존에 보이던 근사 점수와 다른 값이 나올 수 있다 → 릴리스 노트에 명시하고, 필요 시 `"recomputed_from_legacy": true` 플래그 추가 고려.
- `gates/` 패키지가 `report: dict` 입력을 처리하려면 직렬화된 JSON 구조에서 원본 tracker 배열을 역으로 복원해야 하는 지표가 있을 수 있음 — 구현 착수 전 어떤 지표가 report dict만으로 복원 불가능한지 먼저 목록화할 것.
