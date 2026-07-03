# Agent-Evaluator 개선 Spec 인덱스

Spec-Driven 방식으로 진행하는 아키텍처/확장성/거버넌스 개선 작업의 규격 모음.
모든 사실 관계(Context)는 2026-07-02~03 세션에서 코드를 직접 대조해 검증했다(`Docs/specs/VERIFICATION_LEDGER.md` 참조).

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
| [SPEC-004](SPEC-004-streaming-retention-mode.md) | 옵트인 스트리밍 모니터 모드 | P2 | **Partially Implemented (2026-07-02, Gate E-G/B/A/C/D 전체 확장 2026-07-03)** — REQ-1/3/4 완료, REQ-2는 SPEC-018로 A-G 7개 Gate 전체 확장(Gate C retry_consistency·Gate D ttft/cost_predictability는 승인된 근사, 나머지는 정확) | SPEC-000 완료 |
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
| [SPEC-015](SPEC-015-alert-handler-retry-backoff.md) | **알림 핸들러 재시도/백오프 및 알림 폭풍 방지** | P3 | **Implemented (2026-07-03)** | 없음 |
| [SPEC-016](SPEC-016-sqlite-storage-backend.md) | **영속성 저장소 옵션 — SQLite 백엔드** (JSON 파일 전용의 동시쓰기/규모 한계) | P4 | **Implemented (2026-07-03)** | 없음 |
| [SPEC-017](SPEC-017-supply-chain-hygiene.md) | **공급망 위생** (CI, 취약점 스캔, Dependabot, pre-commit, SBOM) | P4 | **Implemented (2026-07-03)** | 없음 |
| [SPEC-018](SPEC-018-gate-running-aggregate-shared-metrics.md) | **Gate 러닝 집계 공유 인프라** (shared_metrics 계층 — SPEC-004 REQ-2 확장) | P2 | **Implemented (2026-07-03, Phase 0-7 전체 완료)** — Gate C retry_consistency(LRU 캡)·Gate D ttft/cost_predictability(reservoir)는 2026-07-03 별도 승인 후 승인된 근사로 구현 | 없음 (SPEC-001과 무관, SPEC-004의 잘못된 교차 참조 정정) |
| [SPEC-019](SPEC-019-live-guardrail-api.md) | **실시간 가드레일 API** (tool-call 단위 동기 Gate B/E 판정 — 로컬 에이전트 루프(OpenCode+Ollama+ctx) 통합용) | P5 | **Implemented + 실 OpenCode 1.17.9/Ollama qwen3-coder 세션 라이브 검증 완료(2026-07-03)** — Gate B 4종 + Gate E 3종 + stdio/report 브리지 + `opencode-plugin/` 참조 구현. 라이브 세션에서 위험한 `rm -f` 삭제를 실제로 차단하고 파일 보존까지 end-to-end 확인, 그 과정에서 발견한 결함 4건(stdin 미종료 시 `opencode run` 무한대기·루프감지 오탐·`rm -f` 우회·BrokenPipeError) 모두 수정 | SPEC-000 완료 — 기존 `gates/gate_b_behavioral`·`gates/gate_e_security`·`core/trackers/security.py` 로직을 재사용만 함 |
| [SPEC-020](SPEC-020-storage-pii-redaction.md) | **저장 계층 PII Redaction** (옵트인 — Gate E가 PII를 채점하면서 저장소엔 원문을 그대로 남기는 모순 해소) | P6 | **Implemented (2026-07-04)** | 없음 — 기존 `gates/gate_e_security/evaluators.py::_PII_PATTERNS`를 재사용만 함 |
| [SPEC-021](SPEC-021-quality-debt-ratchet.md) | **코드 품질 부채 래칫** (ruff/mypy — SPEC-017의 report-only 상태를 baseline 초과 시 hard-block으로 전환) | P6 | **Implemented (2026-07-04)** | SPEC-017 완료 — report-only 2-스텝 잡을 대체 |
| [SPEC-022](SPEC-022-llm-judge-calibration-harness.md) | **LLM Judge 검증 하네스** (사람 라벨 골든셋과의 합의도 리포트 — Cohen's kappa/Pearson/MAE) | P6 | **Implemented (2026-07-04)** | 없음 — 기존 `LLMJudge.judge()`를 그대로 호출만 함 |
| [SPEC-023](SPEC-023-judge-execution-model-heterogeneity.md) | **LLM Judge/실행 모델 이종화 경고 + Lineage 기록** (자기평가 편향 감지) | P6 | **Implemented (2026-07-04)** | SPEC-007 완료 — `_build_lineage()`에 필드 1개 추가 |

## 백로그

모든 백로그 항목이 SPEC-015/016/017/019로 정식 스펙화 및 구현 완료(2026-07-03). SPEC-020/021은
SDK 전반 성숙도 개선 트랙으로 구현 완료(2026-07-04). 상세 스펙 미작성 상태의
신규 항목이 생기면 이 섹션에 먼저 등록하고, 착수 전 반드시 정식 스펙(Context/REQ/Acceptance)을 작성할 것 — 스펙
없이 바로 구현에 들어가지 않는다.

## 로드맵 (2026-07-02~03 재정렬)

| Phase | 스펙 | 근거 |
|---|---|---|
| **P0** (즉시, 리스크 최저) | SPEC-002, SPEC-005, SPEC-007 | 독립적·additive, SPEC-000의 구조 변경과 무관하게 지금 착수 가능 |
| **P1** (구조 기반) | **SPEC-000** ✅ 완료(Gate별 이관: F→E→D→A→B→C→G, 각 단계에 SPEC-001/003 요구사항 흡수) | decorators.py(9,632→8,025줄)/taskresult_helpers.py(4,632→1,262줄)/monitor.py God Method(~1,165줄→위임 호출)를 전면 분해하는 프로그램의 핵심 구조 변경 |
| **P2** | SPEC-004(부분 완료)·SPEC-006·SPEC-009·SPEC-013·SPEC-014·SPEC-018 ✅ (2026-07-02~03, Phase 0-7 전체 완료) | SPEC-000 완료로 착수 가능했음 — SPEC-018이 SPEC-004 REQ-2를 A-G 7개 Gate 전체로 확장(Gate C retry_consistency·Gate D 근사 지표 포함, 2026-07-03 별도 승인) |
| **P3** | SPEC-008 ✅·SPEC-010 ✅(2026-07-02)·SPEC-015 ✅(2026-07-03) | 이후 |
| **P4** | SPEC-016 ✅·SPEC-017 ✅(2026-07-03) | 장기 |
| **P5** | SPEC-019 ✅(2026-07-03) | 신규 기능 확장 — 배포 완결성(P0-P4) 확보 이후, 로컬 에이전트 루프(OpenCode+Ollama+ctx) 실시간 통합을 위한 별도 트랙. 기존 배치 Gate 로직은 무수정, 순수 additive |
| **P6** | SPEC-020 ✅·SPEC-021 ✅·SPEC-022 ✅·SPEC-023 ✅(2026-07-04) | SDK 전반 성숙도 — 엔터프라이즈 신뢰성(PII redaction, 코드 품질 부채 래칫, LLM Judge 검증 하네스 + 이종화 경고). ADE 파이프라인과 무관하게 SDK 자체의 세계 최고 수준 포지셔닝을 위한 별도 트랙 |

## Definition of Done (프로그램 최종 목표)

1. **구조**: Gate 관련 코드가 `gates/gate_x/{configs.py, evaluators.py, aggregate.py}` 7세트로 전면 이관, 파일당 1,500줄 이하. Gate 집계 알고리즘 단일 소스화(monitor.py ↔ serve/loader.py 중복 제거). — **SPEC-000 ✅ 완료(2026-07-02)**
2. **통계적 신뢰**: 전 Gate 표본 부족 경고, CI 게이트가 통계적으로 무의미한 점수로 배포를 승인하지 않음. — **SPEC-002**
3. **AI-Native**: Gate F/B가 텍스트 휴리스틱보다 구조화된 `tool_calls`/`agent_interactions`를 우선 사용. — **SPEC-009 ✅ 완료(2026-07-02)**
4. **엔터프라이즈 운영**: 대시보드 인증 옵션·결과 파일 lineage 캡처(judge 모델 스냅샷 포함)·judge 호출 비병목화·CI/CD 베이스라인 통합·알림 발송 안정성(재시도/백오프/알림 폭풍 방지)·대규모 세션을 위한 영속성 저장소 옵션. — **SPEC-005 ✅·SPEC-007 ✅·SPEC-006 ✅·SPEC-010 ✅·SPEC-015 ✅·SPEC-016 ✅(2026-07-03)**
5. **성능/확장성**: 옵트인 스트리밍 리텐션 모드, 리포트 생성 비용이 태스크 수에 선형 비례하되 상수 배수가 46이 아니라 1, 대시보드 로더가 watch 모드에서 매 요청 전량 재파싱하지 않음, `generate_report()`가 직전 호출 이후 데이터가 바뀌지 않았으면 재계산을 건너뜀, windowed 리텐션 모드에서도 Gate A-G 7개 전체가 전체 이력을 반영(Gate C retry_consistency·Gate D ttft/cost_predictability는 승인된 근사). — **SPEC-004(부분 완료, sla_results 원본 리스트만 windowed-only로 남음), SPEC-000(REQ-2) ✅, SPEC-013 ✅(2026-07-02), SPEC-014 ✅(2026-07-03), SPEC-018 ✅(2026-07-03, Phase 0-7 전체 완료)**
6. **엔지니어링 거버넌스**: CI(테스트/린트/타입체크 자동화)·의존성 취약점 스캔·Dependabot·pre-commit 실효화·릴리스 SBOM. — **SPEC-017 ✅(2026-07-03)**

각 목표가 어느 스펙으로 달성되는지 1:1로 명시했다 — 스펙 없는 목표(이전 두 차례 감사에서 발견된 패턴)가 더 없는지는 이 표와 백로그 섹션을 함께 봐야 확인된다.

## 작업 원칙 (반복 오류 재발 방지)

1. 스펙의 Context 항목은 **같은 세션에서 직접 확인한 파일:라인**만 인용한다. 이전 대화나 서브에이전트 요약을 그대로 옮기지 않는다.
2. 해결책(Requirements)을 쓰기 전에, 그 변경이 영향을 미치는 **모든 소비처**를 먼저 grep으로 찾는다 (예: SPEC-004는 `self.tasks`의 12+ 소비처를 먼저 확인한 뒤에야 안전한 설계가 나왔다).
3. "결과값 동일 유지"가 목표인 리팩터(SPEC-003 등)는 Acceptance에 byte-diff 검증을 포함한다.
4. 각 스펙 구현 후 이 README의 상태(Draft → In Progress → Done)를 갱신한다.
