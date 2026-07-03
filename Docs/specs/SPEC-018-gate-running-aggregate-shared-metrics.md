# SPEC-018: Gate 러닝 집계 공유 인프라 (shared_metrics 계층)

**Phase:** P2 · **상태:** Implemented (2026-07-03, Phase 0-7 전체 완료) · **의존성:** 없음

> **구현 노트**: Phase 0-7 전체(A-G 7개 Gate 모두)를 구현했다. 신규
> `agent_evaluator/gates/shared_metrics.py`에 범용 러닝 집계 프리미티브(`RunningAverage`/
> `RunningSum`/`RunningWindow`/`RunningLastValue`/`MonotonicFlag`/`RunningCount`/
> `RunningCategoryCounter`)와 8개 Gate 전용 클래스(`GateESharedAgg`/`GateFSharedAgg`/
> `GateGSharedAgg`/`GateBSharedAgg`/`GateASharedAgg`/`GateCSharedAgg`/
> `GateCRetryConsistencyAgg`/`GateDSharedAgg`)를 추가했다. 각 Gate의
> `gates/gate_x/aggregate.py::compute()`가 `shared_running: Optional[dict] = None` 인자를
> 받아 windowed 모드에서는 러닝 집계 스냅숏을, "full" 모드(기본값)에서는 기존 `tasks`
> 재계산 경로를 그대로 사용한다. `monitor.py`의 3개 지점(`__init__`/`record_task()`/
> `_compute_harness_groups()`)에 매 Gate당 각 2-3줄씩 배선했다 — 기존 `_running_tcr_agg`/
> `_RunningTCRView`(SPEC-004) 패턴을 그대로 일반화했다.
>
> **Phase 7(2026-07-03 후속 승인)**: 애초 별도 승인이 필요하다고 명시했던 Gate C
> `retry_consistency`와 Gate D 근사 지표를 사용자 승인 후 구현했다. 두 항목 모두
> "정확한 전체 이력 재현"이 불가능한 지표라 **의도적으로 승인된 근사**를 도입했다:
> - **Gate C `retry_consistency`**: `GateCRetryConsistencyAgg`가 task_id 프리픽스별
>   상태(점수 합/개수 + 문자열 최소/최대 task_id 엔트리의 accuracy·config)를
>   `OrderedDict` LRU로 관리하고, 서로 다른 프리픽스 수가 `_MAX_PREFIXES`(기본
>   5,000)를 넘으면 가장 오래전에 갱신된 프리픽스를 제거한다 — 그 프리픽스의 기여분은
>   최종 평균에서 빠진다. `evicted_count`로 근사 발동 여부를 진단할 수 있다. 캡 이내인
>   일반적인 세션에서는 windowed 모드가 "full" 모드와 완전히 일치한다(테스트로 확인).
> - **Gate D**: `GateDSharedAgg`가 efficiency/resource_budget는 단순 평균·누적합·최근
>   config 덮어쓰기만으로 **정확히** 재현하고(다른 Gate와 동일한 패턴), ttft_variability/
>   cost_predictability만 `_RESERVOIR_SIZE`(기본 2,000, `window_size`와 완전히 독립)개의
>   최근 원시값 슬라이딩 샘플에서 stddev/percentile/CV를 계산한다 — 이력이 샘플 크기를
>   초과하면 가장 오래된 원시값부터 밀려나 전체 이력과 정확히 같지 않을 수 있다(승인된
>   트레이드오프, 전용 회귀 테스트로 근사가 실제 발동함을 확인). p95 latency는
>   `latency_tracker`가 `retention_mode`와 무관하게 이미 무제한 증식하는 트래커라서
>   (`_latencies`/`_ttft_records`가 plain list, `deque(maxlen=...)` 아님) 애초부터
>   전체 이력을 반영해 왔다 — `hall_rate`와 동일한 사례, 수정 불필요.
>
> **구현 중 실제로 발견·수정한 버그 2건**:
> 1. **순서 버그(Phase 1, Gate E)**: `record_task()`의 보안 트래커 enrichment(`input_
>    sanitization`/`output_leakage`/`privilege_escalation`/`tool_chain_attack`/
>    `tool_authorization`을 `task_result.extra`에 채우는 블록)가 TCR 러닝 집계 갱신보다
>    **나중에** 실행되는데, Gate E 러닝 집계 갱신을 그 이전에 호출하면 아직 enrichment
>    안 된 task_result를 집계해 windowed 모드의 Gate E 점수가 "full" 모드와 달라지는
>    버그가 있었다 — full-vs-windowed 교차검증 테스트로 실제로 잡아서 갱신 호출 위치를
>    enrichment 블록 이후로 옮겨 수정했다.
> 2. **표시 게이팅 버그(Phase 6, Gate C)**: 기존 코드의 `"sla_breach_count": _sla_breach_count
>    if _sla_results else None`가 **windowed 부분집합**(`_sla_results`)의 존재 여부로
>    `None` 여부를 결정했다 — 윈도우가 SLA 태그 태스크를 전부 밀어내면, 전체 이력에
>    breach가 있었어도 `sla_breach_count`가 `None`으로 잘못 표시되는 버그. `sla_n`(전체
>    이력 기준 SLA 태그 태스크 수, `compute_sla_shared_data()`가 신규로 반환)으로
>    게이팅 조건을 교체해 수정 — "full" 모드에서는 `sla_n == len(windowed_subset)`이므로
>    동작 변화 없음(byte-diff 동일), windowed 모드에서만 정확해짐.
>
> **여전히 스코프 밖(별도 승인 필요, Phase 7에도 포함 안 됨)**:
> - 7개 트래커(`accuracy_evaluator`/`quality_evaluator`/`hallucination_detector`/
>   `latency_tracker`/`tool_analyzer`/`agent_coordination_tracker`/`tool_selection_tracker`)
>   자체의 무제한 증식 — 이들은 SPEC-004 때부터 이미 windowed 모드에서도 캡핑되지 않음
>   (별도 스코프, `latency_tracker`/`hallucination_detector`는 오히려 이 때문에 이미
>   전체 이력을 반영하는 유리한 부작용이 있음).
> - `register_aggregator`/`run_aggregator`(`self.tasks` 전체를 사용자 콜백에 그대로
>   넘김) — 구조적으로 이 리팩터로 고칠 수 없는 대상, 기존 `UserWarning`이 유일한 완화책.
>
> **알려진 한계**: Gate A(goal_alignment/plan_coherence)와 Gate C(llm_faithfulness)는
> `task_result.llm_judge`에 의존한다. SPEC-006의 비동기 judge 경로(`ajudge()`)가
> `record_task()` 반환 이후 별도 코루틴에서 `llm_judge`를 patch하는 경우, 그 patch는
> 이미 계산된 러닝 집계에 반영되지 않는다("full" 모드는 매번 `tasks`를 재스캔하므로
> 항상 최신값 반영 — 이 지점만 windowed 모드와 다를 수 있음). 동기 judge 경로(`record_
> task()` 내부, lock 진입 전 `dataclasses.replace()`로 이미 반영됨)는 영향받지 않는다.
>
> 신규 테스트: `tests/test_shared_metrics_primitives.py`(20건, Phase 0 프리미티브 단위
> 테스트) + `tests/test_streaming_retention_mode.py`에 Gate별 클래스 8개 추가(계 63건 —
> 이력 반영, 세부 지표 일치, full-vs-windowed 교차검증, full 모드 불변 확인의 4종 패턴
> 반복 + Gate 고유 검증: Gate F의 `method="single"` 제외, Gate A의 LLM-judge 블렌딩
> 후 스칼라 누적, Gate B의 공유 분모/카테고리 카운터, Gate C의 SLA 링버퍼 독립성·
> sla_breach_count 버그 수정 확인, Gate C `retry_consistency`의 LRU 캡 이내 exact-match와
> 캡 초과 시 실제 eviction 발동 확인, Gate D efficiency/resource_budget의 exact-match와
> ttft/cost_predictability의 reservoir 이내 exact-match·초과 시 근사 실제 발동 확인·
> p95가 이미 전체 이력임을 별도 확인). 기존 관련 테스트(`test_gates_gate_{a,b,c,d,e,f,g}
> _migration.py`, `test_gate_{e,f,g}_*.py`, `test_min_sample_guard.py`,
> `test_report_harness_groups.py` 등) 전량 무수정 통과. 전체 스위트
> **3,156 passed, 1 skipped, 회귀 0건**.

## Context

- SPEC-004(옵트인 스트리밍 리텐션 모드)는 `retention_mode="windowed"`에서
  `self.tasks`(`tcr_tracker._tasks`)를 `deque(maxlen=window_size)`로 캡핑했지만, Gate
  A/C의 TCR 컴포넌트(`_running_tcr_agg`/`_RunningTCRView`, `monitor.py:187-221,375-381,
  1726-1739`)만 전체 이력 기준 러닝 집계로 보정되고, 나머지 모든 Gate 지표(A의 나머지
  6개, B/D/E/F/G 전체, C의 SLA 외 나머지)는 윈도우 밖으로 밀려난 태스크의 기여분을
  잃은 채 windowed 부분집합만으로 재계산됐다.
- SPEC-004 문서는 이 확장 작업이 "SPEC-001이 제안한 shared_metrics 계층" 완성 후
  가능하다고 명시했으나, 직접 코드 대조 재검토 결과 `SPEC-001-gate-aggregation-
  unification.md`은 실제로는 **다른 문제**(`monitor.py`의 실시간 계산 경로 vs
  `serve/loader.py`의 legacy-JSON fallback 경로가 서로 다른 근사 공식을 쓰는 중복
  문제, `compute_all_gates(tasks=None, report=None)` 통합안)를 다루며, SPEC-000에
  흡수되어 별도 구현되지 않았다. 이 러닝 집계 일반화 작업과는 무관한 스펙이므로,
  새 스펙 번호(본 문서, SPEC-018)로 추적하고 SPEC-004의 잘못된 교차 참조를 정정한다.
- 7개 Gate의 `aggregate.py::compute()`를 전수 조사한 결과(직접 파일 읽기), 각 Gate의
  지표는 난이도가 크게 갈린다:
  - **단순 누적 가능**(합/카운트/평균, 그대로 running-average로 전환 가능): Gate A의
    6개 지표(instruction_adherence/goal_alignment/plan_coherence/subtask_completion/
    context_retention/knowledge_retention), Gate B의 6개 지표 전부, Gate C의
    reproducibility/fault_tolerance/graceful_degradation/idempotency/
    llm_faithfulness/sla_breach_rate/sla_budget_penalty, Gate E 전부, Gate F/G의
    task 기반 지표 전부.
  - **약간의 추가 상태가 필요하지만 유계(bounded)**: Gate C의 sla_window_penalty(최근
    N개 SLA 결과의 순서 보존 링버퍼, `breach_window` config 값, 기본 10).
  - **사실상 무한 증식 위험(별도 승인 필요)**: Gate C의 retry_consistency(task_id
    프리픽스별 그룹 dict — 프리픽스 카디널리티가 세션 길이에 비례해 증가할 수 있음).
  - **근사 알고리즘 필요, 정확한 재계산과 동일하지 않음(별도 승인 필요)**: Gate D의
    p95 latency, TTFT variability(stddev+percentile+IQR 이상치 제거), cost
    predictability(CV, 그룹별 이상치 필터).

## Goals

- `_RunningTCRView` 패턴(record_task() 시점에 갱신되는 O(1) 누적기, "full" 모드에서는
  전혀 개입하지 않음)을 일반화해 Gate A/B/C(일부)/E/F/G의 단순 누적 가능한 지표들도
  windowed 모드에서 전체 이력을 반영하게 한다.
- 각 단계(Gate)를 독립적으로 검증 가능한 작은 단위로 나눠, 매 단계마다 전체 테스트
  스위트 100% green을 유지한다.

## Non-Goals

- 7개 트래커(accuracy_evaluator 등) 자체를 캡핑하는 것 — SPEC-004가 이미 별도
  스코프로 분리해 둔 기존 한계, 이번 스펙에서 확장하지 않는다.
- `serve/loader.py`/SPEC-001의 monitor.py-loader.py 공식 통합 문제 — 완전히 별개의
  스펙(진짜 SPEC-001)이며 이 작업과 무관하다.
- `register_aggregator`/`run_aggregator` — 구조적으로 이 리팩터로 고칠 수 없는 대상.

> Phase 7(2026-07-03) 승인 이전에는 Gate C `retry_consistency`와 Gate D 근사 지표도
> 이 섹션에 있었으나, 사용자가 별도 승인해 REQ-10/REQ-11로 구현했다(아래 참조).

## Requirements

- **REQ-1**: `agent_evaluator/gates/shared_metrics.py` 신설 — `RunningAverage`(단순
  평균)/`RunningSum`(누적합)/`RunningWindow`(순서 보존 링버퍼, `retention_mode`의
  `window_size`와 독립)/`RunningLastValue`(최근 관측값 덮어쓰기)/`MonotonicFlag`(단조
  증가 불리언)/`RunningCount`(단순 카운터)/`RunningCategoryCounter`(카테고리별 카운트,
  카디널리티 유한한 지표 전용) 7개 범용 프리미티브.
- **REQ-2**: Gate E(Security) — `GateESharedAgg`. 트래커 의존성 0, 다른 Gate 참조
  0인 가장 단순한 Gate를 파일럿으로 삼는다. 공유 분모(`n = max(len(tasks), 1)`)와
  "전체 이력에 한 번이라도 데이터가 존재했는가" 게이팅(`_native_e_scores` 포함 여부)을
  정확히 재현한다.
- **REQ-3**: Gate F(Multi-Agent Coordination) — `GateFSharedAgg`. task 기반 4개 평균만
  (consensus/propagation/agent_role/conflict_resolution, `method != "single"` 필터
  유지). 트래커 기반 2개 지표는 무변경.
- **REQ-4**: Gate G(Observability) — `GateGSharedAgg`. task 기반 4개 평균만
  (observability/explainability/error_diagnosis/latency_attribution). `hall_rate`/
  `avg_llm_faithfulness`(Gate C passthrough)는 Gate C(REQ-6) 완료 전까지 windowed-only.
- **REQ-5**: Gate B(Behavioral Integrity) — `GateBSharedAgg`. 6개 지표 전부. 공유
  분모 패턴(loop/deadlock — 분모가 전체 n이 아니라 "해당 Config가 설정된 태스크
  수")과 `RunningCategoryCounter`(deadlock_by_type)를 처음 실전 검증.
- **REQ-6**: Gate A(Goal Achievement) — `GateASharedAgg`. 6개 Config 기반 지표.
  goal_alignment/plan_coherence는 LLM-judge relevance 블렌딩 **이후의 최종 스칼라**를
  누적해야 한다(원점수 누적 금지). TCR 컴포넌트·accuracy/quality 트래커 기반 부분은
  무변경.
- **REQ-7**: Gate C(Reliability), `retry_consistency` 제외 — `GateCSharedAgg`.
  reproducibility/fault_tolerance/graceful_degradation/idempotency/llm_faithfulness
  (단순 평균) + SLA breach_rate/window_penalty(`RunningWindow` 링버퍼)/budget_penalty
  (`RunningSum` + `RunningLastValue`). `compute_sla_shared_data()`가 Gate D에도 값을
  공급하므로, **`sla_results`(원본 리스트)는 `shared_running` 유무와 무관하게 항상
  `tasks`에서 계산**(Gate D의 p95 threshold 평균 계산이 계속 원본 리스트를 필요로 함) —
  breach_count/rate/window_penalty/budget_penalty "값"만 러닝 집계로 대체된다.
- **REQ-8**: 각 Gate의 `compute()`는 새 선택 인자 `shared_running: Optional[dict] =
  None`을 받는다. `None`(기본값, "full" 모드 및 windowed 모드에서 아직 마이그레이션
  안 된 Gate)이면 기존과 100% 동일하게 `tasks`에서 매번 재계산한다.
- **REQ-9**: `monitor.py`는 매 Gate마다 3개 지점(`__init__`에서 windowed일 때만 인스턴스화,
  `record_task()`의 기존 lock 블록 내에서 `.update()` 호출, `_compute_harness_groups()`
  에서 `.snapshot()`을 만들어 `compute()`에 전달)에 배선한다 — `_running_tcr_agg` 패턴과
  동일한 구조.
- **REQ-10** (Phase 7, 2026-07-03 별도 승인): Gate C `retry_consistency` —
  `GateCRetryConsistencyAgg`. task_id 프리픽스별(`rsplit("_", 1)`) 점수 평균 + 문자열
  최소/최대 task_id 엔트리의 accuracy 델타 기반 개선/저하 보너스·페널티를 그대로
  재현하되, 프리픽스 카디널리티를 `_MAX_PREFIXES`(기본 5,000)로 캡핑한 `OrderedDict`
  LRU로 관리한다 — 캡 초과 시 가장 오래전에 갱신된 프리픽스가 제거되고 그 기여분이
  최종 평균에서 빠진다(승인된 의도적 근사). `compute()`에는 `shared_running`과 별도인
  `retry_consistency_shared: Optional[dict] = None` 파라미터로 분리해 "이 지표만 근사"
  임을 diff에서 명확히 드러낸다. `use_prefix=False`(비-프리픽스 평탄 평균) 모드는 이
  캡과 무관해 항상 정확하다.
- **REQ-11** (Phase 7, 2026-07-03 별도 승인): Gate D — `GateDSharedAgg`.
  efficiency(calibrated_score/efficiency_ratio, 단위별)와 resource_budget(rollover
  모드의 누적 소비/한도 합, non-rollover 모드의 budget_score 평균, 최근 `_config`
  덮어쓰기)는 단순 평균·누적합만으로 **정확히** 재현 가능해 다른 Gate와 동일한 패턴을
  따른다. ttft_variability(stddev+percentile+IQR 이상치 제거)와 cost_predictability
  (task_type별 CV, mean±k·std 이상치 필터)만 `_RESERVOIR_SIZE`(기본 2,000, `window_size`
  와 완전히 독립)개의 최근 원시값 슬라이딩 샘플에서 계산하는 **의도적으로 승인된
  근사**다 — 원본과 동일한 sorted/IQR/stddev/percentile 계산 로직을 샘플에 적용하므로,
  이력이 샘플 크기 이내이면 "full" 모드와 완전히 일치하고, 초과하면 근사가 발동한다.
  p95 latency는 `latency_tracker`(retention_mode와 무관하게 이미 무제한 증식)에서 오므로
  이 REQ의 범위 밖 — 애초부터 전체 이력 반영, 수정 불필요.

## Interface

```python
# 변경 전 (예: Gate E)
def compute(tasks: list, enable_security_metrics: bool, min_samples_default: int) -> Dict[str, Any]: ...

# 변경 후 (하위호환 — shared_running 기본값 None이면 기존과 100% 동일)
def compute(
    tasks: list, enable_security_metrics: bool, min_samples_default: int,
    shared_running: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]: ...
```

```python
# monitor.py — 매 Gate당 반복되는 3-지점 패턴 (Gate E 예시)
# __init__:
if self._retention_mode == "windowed":
    self._running_gate_e_agg = GateESharedAgg()

# record_task() 내부, 기존 lock 블록:
if self._retention_mode == "windowed":
    self._running_gate_e_agg.update(task_result)

# _compute_harness_groups():
_e_shared = self._running_gate_e_agg.snapshot() if self._retention_mode == "windowed" else None
_e_group = gate_e_aggregate.compute(tasks, self.enable_security_metrics, self._min_samples_default, shared_running=_e_shared)
```

## Acceptance

각 Gate 단계마다 4종 테스트(모두 통과 확인됨):
1. **이력 반영 검증**: `window_size`보다 많은 태스크 기록 → 러닝 집계 스냅숏이 밀려난
   태스크의 기여분을 반영.
2. **세부 지표 단위 일치**: `details`의 각 마이그레이션된 키가 전체 이력 기대값과 일치.
3. **full vs windowed 교차검증**: 동일 태스크 시퀀스를 `retention_mode="full"`/
   `"windowed"`(작은 window_size)로 각각 실행 → `details` 전체가 `pytest.approx`로 동일.
4. **full 모드 불변 확인**: `retention_mode="full"`에서 `_running_gate_x_agg` 속성 자체가
   생성되지 않음(`not hasattr`).

Gate 고유 추가 테스트: Gate F의 `method="single"` 배제, Gate A의 LLM-judge 블렌딩,
Gate C의 SLA 링버퍼 독립성(`window_size`와 무관), `sla_breach_count` 버그 수정 확인
(윈도우가 SLA 태스크를 전부 밀어내도 전체 이력 카운트가 표시됨).

**근사 지표(REQ-10/REQ-11) 전용 추가 검증**(4종 패턴을 대체 — "동일" 대신 "캡/샘플
이내에서는 동일, 초과하면 근사가 실제로 발동"을 확인):
1. **캡/샘플 이내 exact-match**: LRU 캡(5,000)·reservoir(2,000)보다 훨씬 작은 픽스처로
   windowed와 full 모드가 완전히 일치함을 확인(Gate C retry_consistency, Gate D
   ttft_variability/cost_predictability 각각).
2. **캡/샘플 초과 시 근사 발동 확인**: 테스트에서 `_MAX_PREFIXES`/`_RESERVOIR_SIZE`를
   작게 조정해 캡/샘플을 의도적으로 초과시키고, eviction이 실제로 일어나며
   (`evicted_count > 0`) 결과가 "밀려난 원시값을 반영하지 못함"을 보여주는지 확인 —
   근사가 문서상의 주장으로만 존재하는 게 아니라 실제로 그렇게 동작함을 증명.
3. **정확 재현 구간의 exact-match**: Gate D의 efficiency/resource_budget(근사가 아닌
   부분)은 다른 Gate와 동일하게 4종 패턴으로 검증(위 목록 그대로).
4. **p95의 선행 완전성 확인**: `latency_tracker`가 애초부터 무제한이라는 근거로 Gate D
   마이그레이션과 무관하게 windowed 모드에서도 이미 전체 이력과 일치함을 별도 확인.

## Compatibility

- `retention_mode="full"`(기본값)은 이번 작업으로 어떤 코드 경로도 추가 실행되지
  않는다 — 모든 신규 상태는 `if self._retention_mode == "windowed":` 가드 안에서만
  생성/갱신된다.
- 각 `compute()`의 새 `shared_running` 인자는 기본값이 있는 선택 인자이므로 기존
  호출부(있다면 외부 코드) 수정 불필요.
- `register_aggregator`/`run_aggregator`(`self.tasks`를 통째로 사용자 콜백에 넘김)는
  이 리팩터로 고칠 수 없는 대상 — 기존 `UserWarning`(SPEC-004 REQ-3)이 유일한 완화책,
  변경하지 않았다.

## Rollout

1. Phase 0: `shared_metrics.py` 기반 프리미티브만 추가(사용처 없음, 위험 없음). ✅
2. Phase 1: Gate E(파일럿). ✅ — 순서 버그 발견·수정.
3. Phase 2: Gate F. ✅
4. Phase 3: Gate G. ✅
5. Phase 4: Gate B. ✅ — `RunningCategoryCounter` 첫 실전 검증.
6. Phase 5: Gate A. ✅ — LLM-judge 블렌딩, 비동기 judge 패치 한계 문서화.
7. Phase 6: Gate C(`retry_consistency` 제외). ✅ — `sla_breach_count` 표시 게이팅
   버그 발견·수정.
8. Phase 7(2026-07-03, 별도 승인 후 착수): Gate C `retry_consistency`(LRU 캡) + Gate D
   (efficiency/resource_budget 정확 재현 + ttft_variability/cost_predictability
   reservoir 근사, p95는 이미 완전). ✅ — A-G 7개 Gate 전체 완료.

각 Phase 완료 시 `Docs/specs/SPEC-004-streaming-retention-mode.md`의 구현 노트를
갱신해 해당 Gate를 "windowed-only" 목록에서 "전체 이력 반영" 목록으로 이동했다.

## Risks

- **비동기 judge patch 한계**(위 구현 노트 참조) — Gate A/C의 llm_judge 의존 지표는
  SPEC-006 비동기 judge 경로의 patch 타이밍에 따라 러닝 집계가 아직 반영 안 된 값을
  스냅숏할 수 있다. 완화책: 문서화된 알려진 한계로 명시, 필요 시 SPEC-014의
  `invalidate_report_cache()`와 유사한 메커니즘을 러닝 집계에도 적용하는 후속 작업으로
  분리.
- **`compute()` 내부에 두 코드 경로 공존**(TCR 사례와 달리 트래커 스왑만으로 해결
  안 됨, 지표별 `if shared_running is not None: ... else: ...` 분기 필요) — "현재
  로직을 있는 그대로 옮겨적기(transliteration), 재해석 금지" 원칙과 4종 교차검증
  테스트로 상쇄. 실제로 Gate E에서 순서 버그를, Gate C에서 표시 게이팅 버그를 이
  테스트들이 잡아냈다 — 설계가 유효함을 실증.
- Gate C의 `sla_results`(원본 리스트)는 REQ-7에 따라 여전히 windowed 부분집합에서
  계산된다 — Gate D의 p95 threshold 평균 계산은 windowed 모드에서 계속 부분집합
  기준(Gate D의 다른 지표들이 Phase 7에서 정확/근사 재현으로 마이그레이션된 것과
  무관하게, `sla_results`만은 의도적으로 그대로 둔 설계 — REQ-7에 문서화됨).
- **근사 지표의 캡/샘플 크기 선택**(Gate C `_MAX_PREFIXES=5000`, Gate D
  `_RESERVOIR_SIZE=2000`)은 하드코딩된 상수이며 `PerformanceMonitor` 공개 API로
  노출되지 않는다 — 극단적으로 높은 프리픽스 카디널리티나 매우 긴 세션에서 근사
  강도가 사용자 조정 불가. 필요해지면 별도 요청으로 파라미터화할 수 있다(현재는
  일반적인 사용 사례를 커버하는 합리적 기본값으로 판단해 범위 밖으로 유지).
