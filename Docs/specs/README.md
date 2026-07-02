# Agent-Evaluator 개선 Spec 인덱스

Spec-Driven 방식으로 진행하는 아키텍처/확장성/거버넌스 개선 작업의 규격 모음.
모든 사실 관계(Context)는 2026-07-02 세션에서 코드를 직접 대조해 검증했다(`Docs/specs/VERIFICATION_LEDGER.md` 참조).

## 스펙 템플릿

새 스펙 작성 시 아래 형식을 따른다.

```
SPEC-XXX: <제목>
- Context        : 현재 코드 상태 (파일:라인 근거 — 반드시 직접 확인한 것만 기재)
- Goals          : 무엇을 달성하는가
- Non-Goals      : 이번 스펙에서 다루지 않는 것 (스코프 누수 방지)
- Requirements   : REQ-1, REQ-2 ... 고유 ID, 검증 가능한 문장
- Interface      : 변경 전/후 시그니처 (하위호환 여부 명시)
- Acceptance     : REQ ID별 테스트 케이스/판정 기준
- Compatibility  : 기존 테스트 스위트 + 공개 API에 대한 영향
- Rollout        : 배포 순서, 롤백 조건
- Risks          : 실패 시나리오와 완화책
```

## 스펙 목록

| ID | 제목 | Phase | 상태 | 의존성 |
|---|---|---|---|---|
| [SPEC-000](SPEC-000-gate-package-decomposition.md) | **Gate 패키지 전면 분해** (decorators.py/taskresult_helpers.py/monitor.py → gates/) | P1 | **✅ Done — Gate A–G 전체 7개 Gate 이관 완료** | 없음 — 다른 구조 스펙의 상위 스펙 |
| [SPEC-001](SPEC-001-gate-aggregation-unification.md) | Gate 집계 단일 소스화 (monitor.py ↔ serve/loader.py) | P1 | Draft — **SPEC-000 REQ-1로 흡수** | SPEC-000 이관 작업 내 처리 |
| [SPEC-002](SPEC-002-universal-min-sample-guard.md) | 전 Gate 공통 최소 표본 가드 | P0 | **Implemented (2026-07-02)** | 없음 — SPEC-000과 독립적으로 지금 착수 가능 |
| [SPEC-003](SPEC-003-single-pass-aggregation.md) | 단일 패스 집계 (46회 순회 → 1회) | P1 | Draft — **SPEC-000 REQ-2로 흡수** | SPEC-000 이관 작업 내 처리 |
| [SPEC-004](SPEC-004-streaming-retention-mode.md) | 옵트인 스트리밍 모니터 모드 | P2 | **Partially Implemented (2026-07-02)** — REQ-1/3/4 완료, REQ-2는 Gate A/C TCR 컴포넌트만 러닝 집계(축소 범위) | SPEC-000 완료 |
| [SPEC-005](SPEC-005-dashboard-auth-middleware.md) | 대시보드 인증 미들웨어 (옵트인) | P0 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-006](SPEC-006-llm-judge-concurrency.md) | LLM Judge 동시성 및 백오프 | P2 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-007](SPEC-007-lineage-capture.md) | 감사/재현성 Lineage 캡처 | P0 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-008](SPEC-008-compliance-framework-expansion.md) | Compliance 프레임워크 확장 (SOC2/PCI-DSS) | P3 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-009](SPEC-009-structured-signal-evaluation.md) | 구조화 신호 우선 평가 전환 (Gate F/B) | P2 | **Implemented (2026-07-02)** | SPEC-000 완료 |
| [SPEC-010](SPEC-010-cicd-baseline-gate.md) | CI/CD 게이트 베이스라인 통합 — Harness Gate A–G 회귀 탐지 확장 | P3 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-011](SPEC-011-tool-coverage-attribute-fix.md) | **Gate G `tool_coverage` 속성명 결함 수정** (`self.tool_call_analyzer` → `self.tool_analyzer`) | P1 | **Implemented (2026-07-02)** | SPEC-000 완료 — Gate G 이관 중 발견 |
| [SPEC-012](SPEC-012-event-based-min-sample-guard.md) | **이벤트 기반 지표 최소 표본 가드** (Gate F coordination/tool_selection, Gate G tool_coverage) | P1 | **Implemented (2026-07-02)** | SPEC-002(Non-Goals에서 제외)·SPEC-011(tool_coverage 실효성 확보) 완료 |
| [SPEC-013](SPEC-013-dashboard-loader-incremental-cache.md) | **대시보드 로더 증분 캐싱** (watch 모드 요청당 전량 재파싱 제거) | P2 | **Implemented (2026-07-02)** | 없음 |
| [SPEC-014](SPEC-014-generate-report-caching.md) | **`generate_report()` 재계산 방지 캐싱** (풀 리텐션 모드) | P2 | **Implemented (2026-07-03)** | 없음 |

## 백로그 (상세 스펙 미작성 — 2026-07-02 감사에서 누락 확인, 착수 전 스펙화 필요)

아래 항목은 턴 1~3의 엔터프라이즈/성능 분석에서 지적됐으나 아직 SPEC 문서로 구체화되지 않았다. Definition of Done에 포함되지 않은 항목들이며, 착수 전 반드시 정식 스펙(Context/REQ/Acceptance)을 먼저 작성할 것 — 이 목록에만 남겨두고 스펙 없이 바로 구현에 들어가지 않는다.

| 항목 | 근거 (원 분석 위치) | 예상 Phase |
|---|---|---|
| 알림 핸들러 재시도/백오프/알림 폭풍 방지 | `alerts/handlers.py` 예외처리 전무 확인(턴 1) | P3 |
| 영속성 DB 백엔드 옵션(JSON 파일 전용의 동시쓰기/규모 한계) | `monitor.py::save_to_file`, `serve/loader.py` 분석(턴 1, 3) | P4 |
| 공급망 위생 (SBOM, `pip-audit`/dependabot, `.github/workflows` 부재) | `pyproject.toml` 범위 핀, CI 워크플로우 0건 확인(턴 1) | P4 |

## 로드맵 (2026-07-02 재정렬)

| Phase | 스펙 | 근거 |
|---|---|---|
| **P0** (즉시, 리스크 최저) | SPEC-002, SPEC-005, SPEC-007 | 독립적·additive, SPEC-000의 구조 변경과 무관하게 지금 착수 가능 |
| **P1** (구조 기반) | **SPEC-000** ✅ 완료(Gate별 이관: F→E→D→A→B→C→G, 각 단계에 SPEC-001/003 요구사항 흡수) | decorators.py(9,632→8,025줄)/taskresult_helpers.py(4,632→1,262줄)/monitor.py God Method(~1,165줄→위임 호출)를 전면 분해하는 프로그램의 핵심 구조 변경 |
| **P2** | SPEC-004(부분 완료)·SPEC-006·SPEC-009·SPEC-013·SPEC-014 ✅ (2026-07-02~03) | SPEC-000 완료로 착수 가능했음 — shared_metrics 계층 통합(선택적 후속 정리)은 SPEC-000 문서의 "완료 후 후속 작업" 참조 |
| **P3** | SPEC-008 ✅·SPEC-010 ✅(2026-07-02) (+ 백로그: 알림 재시도) | 이후 |
| **P4** | 백로그: DB 백엔드, 공급망 위생 | 장기 |

## Definition of Done (프로그램 최종 목표)

1. **구조**: Gate 관련 코드가 `gates/gate_x/{configs.py, evaluators.py, aggregate.py}` 7세트로 전면 이관, 파일당 1,500줄 이하. Gate 집계 알고리즘 단일 소스화(monitor.py ↔ serve/loader.py 중복 제거). — **SPEC-000 ✅ 완료(2026-07-02)**
2. **통계적 신뢰**: 전 Gate 표본 부족 경고, CI 게이트가 통계적으로 무의미한 점수로 배포를 승인하지 않음. — **SPEC-002**
3. **AI-Native**: Gate F/B가 텍스트 휴리스틱보다 구조화된 `tool_calls`/`agent_interactions`를 우선 사용. — **SPEC-009 ✅ 완료(2026-07-02)**
4. **엔터프라이즈 운영**: 대시보드 인증 옵션·결과 파일 lineage 캡처(judge 모델 스냅샷 포함)·judge 호출 비병목화·CI/CD 베이스라인 통합. — **SPEC-005 ✅·SPEC-007 ✅·SPEC-006 ✅·SPEC-010 ✅(2026-07-02)**
5. **성능/확장성**: 옵트인 스트리밍 리텐션 모드, 리포트 생성 비용이 태스크 수에 선형 비례하되 상수 배수가 46이 아니라 1, 대시보드 로더가 watch 모드에서 매 요청 전량 재파싱하지 않음, `generate_report()`가 직전 호출 이후 데이터가 바뀌지 않았으면 재계산을 건너뜀. — **SPEC-004(부분 완료, 2026-07-02 — TCR 컴포넌트만 러닝 집계), SPEC-000(REQ-2) ✅, SPEC-013 ✅(2026-07-02), SPEC-014 ✅(2026-07-03)**

각 목표가 어느 스펙으로 달성되는지 1:1로 명시했다 — 스펙 없는 목표(이전 두 차례 감사에서 발견된 패턴)가 더 없는지는 이 표와 백로그 섹션을 함께 봐야 확인된다.

## 작업 원칙 (반복 오류 재발 방지)

1. 스펙의 Context 항목은 **같은 세션에서 직접 확인한 파일:라인**만 인용한다. 이전 대화나 서브에이전트 요약을 그대로 옮기지 않는다.
2. 해결책(Requirements)을 쓰기 전에, 그 변경이 영향을 미치는 **모든 소비처**를 먼저 grep으로 찾는다 (예: SPEC-004는 `self.tasks`의 12+ 소비처를 먼저 확인한 뒤에야 안전한 설계가 나왔다).
3. "결과값 동일 유지"가 목표인 리팩터(SPEC-003 등)는 Acceptance에 byte-diff 검증을 포함한다.
4. 각 스펙 구현 후 이 README의 상태(Draft → In Progress → Done)를 갱신한다.
