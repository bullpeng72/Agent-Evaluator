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
| [SPEC-019](SPEC-019-live-guardrail-api.md) | **실시간 가드레일 API** (tool-call 단위 동기 Gate B/E 판정 — 로컬 에이전트 루프(OpenCode+Ollama+ctx) 통합용) | P5 | **Implemented + 실 OpenCode 1.17.9/Ollama qwen3-coder 세션 라이브 검증 완료(2026-07-03) + pip 패키지 편입(2026-07-04)** — Gate B 4종 + Gate E 3종 + stdio/report 브리지 + OpenCode 참조 구현(`agent_evaluator/integrations/opencode_plugin/`에 번들, `agent-eval opencode install`로 설치). 라이브 세션에서 위험한 `rm -f` 삭제를 실제로 차단하고 파일 보존까지 end-to-end 확인, 그 과정에서 발견한 결함 4건(stdin 미종료 시 `opencode run` 무한대기·루프감지 오탐·`rm -f` 우회·BrokenPipeError) 모두 수정 | SPEC-000 완료 — 기존 `gates/gate_b_behavioral`·`gates/gate_e_security`·`core/trackers/security.py` 로직을 재사용만 함 |
| [SPEC-020](SPEC-020-storage-pii-redaction.md) | **저장 계층 PII Redaction** (옵트인 — Gate E가 PII를 채점하면서 저장소엔 원문을 그대로 남기는 모순 해소) | P6 | **Implemented (2026-07-04)** | 없음 — 기존 `gates/gate_e_security/evaluators.py::_PII_PATTERNS`를 재사용만 함 |
| [SPEC-021](SPEC-021-quality-debt-ratchet.md) | **코드 품질 부채 래칫** (ruff/mypy — SPEC-017의 report-only 상태를 baseline 초과 시 hard-block으로 전환) | P6 | **Implemented (2026-07-04)** | SPEC-017 완료 — report-only 2-스텝 잡을 대체 |
| [SPEC-022](SPEC-022-llm-judge-calibration-harness.md) | **LLM Judge 검증 하네스** (사람 라벨 골든셋과의 합의도 리포트 — Cohen's kappa/Pearson/MAE) | P6 | **Implemented (2026-07-04)** | 없음 — 기존 `LLMJudge.judge()`를 그대로 호출만 함 |
| [SPEC-023](SPEC-023-judge-execution-model-heterogeneity.md) | **LLM Judge/실행 모델 이종화 경고 + Lineage 기록** (자기평가 편향 감지) | P6 | **Implemented (2026-07-04)** | SPEC-007 완료 — `_build_lineage()`에 필드 1개 추가 |
| [SPEC-024](SPEC-024-local-ade-memory-layer.md) | **로컬 ADE 자가교정 메모리 계층** (`ToolParameterSafetyConfig` 도구 스코프 + SQLite FTS5 검색 + MCP 노출) — ctx/mem0 라이브 검증에서 발견한 제3자 도구 한계(OpenCode 세션 미색인, Postgres 의존, 무차별 패턴 매칭)를 자체 SQLite 백엔드 확장으로 해소 | P7 | **Implemented (2026-07-05)** — REQ-1~6 전체 완료: `scope_tool_names`·FTS5 `violation_search`·`search_violations()`·`violation_search_mcp.py` stdio 서버·transcript 힌트 문구·`agent-eval opencode install --with-violation-search` 자동 등록 | SPEC-019 완료(`LiveGuardrail`/`live_guardrail_report.py` 재사용) · SPEC-016 완료(`storage/sqlite_backend.py` additive 확장) · SPEC-020 완료(PII redaction 상호작용 Risks에 명시) |
| [SPEC-025](SPEC-025-version-aware-comparison.md) | **버전 인식 비교** (`prompt_version`/`agent_version` 그룹 비교 + 버전별 baseline + Pairwise LLM Judge + 골든셋 회귀 게이트) — "코드/프롬프트 변경이 실제로 품질을 개선하는가"를 확인하는 개발 루프에서, 이미 저장만 되고 소비되지 않던 버전 메타데이터를 실제 비교 파이프라인에 연결 | P8 | **Implemented (2026-07-06)** — REQ-1~6 전체 완료: `ResultFile.prompt_version`/`agent_version` 노출 + `list_results` 정확 일치 필터·`compare_results(group_by=...)` 그룹별 최신 파일 자동 비교·`gate --baseline-version` 버전별 독립 기준선·`LLMJudge.judge_pairwise()`(swap-check)·`compare_results(pairwise=True)` win_rate 통합·`gate --golden-set --fail-on-golden-regression` 골든셋 회귀 게이트(exit 3) | SPEC-010 완료(`gate.py` baseline/회귀 로직 재사용) · SPEC-006 완료(`LLMJudge` 동시성 인프라를 pairwise에도 재사용) · SPEC-013 완료(`ResultFile` 증분 캐싱 구조에 신규 프로퍼티 추가) |
| [SPEC-026](SPEC-026-persistent-anomaly-baseline.md) | **영속 이상탐지 기준선** (SQLite 재수화로 재시작 생존 기준선 + `StreamingEvaluator` 상시 스캔 + `AlertEngine` 자동 연결 + `ImplicitFeedbackTracker` 신호 편입) — "운영 중인 에이전트의 실행 품질·드리프트·이상징후"를 확인하는 운영 루프에서, 인메모리 전용이라 프로세스 재시작에 살아남지 못하던 `AnomalyDetector` 기준선을 영속화 | P8 | **Implemented (2026-07-06)** — REQ-1~5 전체 완료: `PerformanceMonitor.rehydrate_from_storage()`·`StreamingEvaluator(anomaly_detector=..., anomaly_scan_interval=..., anomaly_alert_handler=...)` 주기적 스캔+자동 발송·`AlertEngine.dispatch_anomaly_events()`·`AnomalyDetector._check_feedback_negativity()`(6번째 체크) | SPEC-016 완료(`load_tasks_from_db` 재사용) · SPEC-015 완료(`AlertEngine` 재시도/백오프/쿨다운 재사용) |
| [SPEC-027](SPEC-027-git-based-agent-version-tagging.md) | **Git 커밋 기반 `agent_version` 자동 태깅** (`agent_version="auto"` — 커밋 SHA + 미커밋 변경(dirty) 해시 접미사) — SPEC-025가 완성한 버전 비교 파이프라인과 AOO ADE 로컬 개발 루프(커밋 없이 반복 iteration하는 게 일반적인 패턴)를 잇는 첫 조각. SPEC-025 Non-Goals가 "별도 후속 스펙(AOO ADE 연동 트랙)"으로 명시적으로 미뤄뒀던 항목 | P9 | **Implemented (2026-07-06)** — REQ-1~3 전체 완료: `agent_version="auto"` → 캐싱된 `self._git_commit` 앞 8자로 자동 해석(git 정보 없으면 `None` 폴백), 커밋되지 않은 tracked 변경이 있으면(`git diff HEAD`) 해시 접미사 부착(같은 커밋에서 다른 변경은 다른 태그, 동일 변경은 재현되는 동일 태그) + 읽기 전용 `monitor.agent_version` 프로퍼티 | SPEC-007 완료(`self._git_commit` 캐싱 재사용) · SPEC-025 완료(`agent_version` 소비 파이프라인 전체를 무수정으로 재사용) |
| [SPEC-028](SPEC-028-aoo-batch-harness-integration.md) | **AOO 배치 Gate A–G 통합** (실시간 LiveGuardrail 가드레일과 오프라인 종합평가를 하나의 파이프라인으로) — OpenCode 세션이 이미 `PerformanceMonitor.record_task()`/`generate_report()`를 거치면서도 Gate G(도구 사용 미노출)·D(execution_time 상수 0.0)·A(placeholder 텍스트로 오도하는 completion_score)를 의미 있게 채우지 못하던 것을 바로잡고, `agent_version="auto"`(SPEC-027)를 연결해 개발자 여정(실시간 차단→배치 종합평가→버전 비교)을 완성 | P9 | **Implemented (2026-07-07)** — REQ-1~5 전체 완료: `LiveGuardrail.snapshot()`이 확정 도구 호출 원본을 `tool_calls`로 노출 → `live_guardrail_report.py`가 이를 `TaskResult.tool_calls`로 옮겨 Gate G(ToolCallAnalyzer)가 실제 값을 계산(REQ-1). OpenCode 플러그인이 실제 세션 경과 시간을 `execution_time`으로 전달해 Gate D가 상수 0.0 대신 실측값 사용(REQ-2). 선택적 `success` 필드로 Gate A completion_score를 명시 반영, 미지정 시 중립값 0.5로 "항상 완벽" 오도를 제거(REQ-3, `None`은 TaskResult 검증에 막혀 불가함을 구현 중 확인). `PerformanceMonitor` 생성에 `agent_version=payload.get("agent_version", "auto")` 연결(REQ-5). `ch28_local_ade_loop.py` 섹션 5에서 전체 흐름을 직접 실행 검증 — `agent-eval gate` exit 0, Gate A/D/G가 not-tested/상수/오도값이 아닌 실제 값으로 표시됨(REQ-4) | SPEC-019 완료(`LiveGuardrail`/`live_guardrail_report.py` 재사용) · SPEC-016 완료(SQLite 다중 프로세스 upsert) · SPEC-027 ✅완료(REQ-5가 소비) |
| [SPEC-029](SPEC-029-iteration-note-tagging.md) | **`iteration_note`** (agent_version="auto"의 불투명한 dirty-hash 태그에 사람이 읽을 수 있는 한 줄 메모를 붙임) — 대시보드 File Compare 탭에서 `group_by=agent_version`으로 여러 iteration을 나열해도 어느 시도가 무엇을 바꾼 것인지 구분할 방법이 없던 것을 해소 | P9 | **Implemented (2026-07-07)** — REQ-1~5 전체 완료: `PerformanceMonitor(iteration_note=...)` → `_build_lineage()`에 그대로 실림(REQ-1/2). `ResultFile.iteration_note`가 `agent_version`과 동일 패턴으로 노출(REQ-3). `record_and_save()`가 페이로드의 `iteration_note`를 그대로 전달(REQ-4). 대시보드 Metric Comparison 표에 `agent_version`/`iteration_note` 메타데이터 행 추가, 새 API 호출 없이 기존 `compareData`에서 직접 렌더링(REQ-5). 테스트 8건 추가, 전체 스위트 3,440 passed·회귀 0건 | SPEC-007 완료(`_build_lineage()` 재사용) · SPEC-025 완료(`ResultFile`/대시보드 Group by 파이프라인 재사용) · SPEC-027 ✅완료(이 스펙이 보완하는 대상) |
| [SPEC-030](SPEC-030-blocked-attempt-audit-trail.md) | **`blocked_violations`** (완전 차단된 시도의 감사 이력) — `fail_on_*=True`로 완전 차단된 시도는 `record_tool_call()`이 호출되지 않아 `tasks`/`violation_search` 어디에도 남지 않던 것(§27.2/Ch28 섹션2가 라이브로 확인한 한계)을 Gate B/E 점수와 완전히 분리된 별도 감사 이력으로 해소 | P9 | **Implemented (2026-07-07)** — REQ-1~6 전체 완료: `LiveGuardrail.record_blocked_attempt()`(호출자가 명시적으로 트리거 — `check_before_tool_call()`은 순수 조회 계약 유지, REQ-1). `snapshot()`이 `blocked_attempts`를 `tool_calls`와 동일하게 항상 노출(REQ-2). `storage/sqlite_backend.py`의 `blocked_violations` FTS5 테이블 + `save_tasks_to_db()` 연결(REQ-3). `search_violations(include_blocked=...)`(REQ-4). `violation_search_mcp.py`가 도구 docstring이 원래 약속한 "차단된 이력" 검색을 실제로 이행(REQ-5). stdio 브리지 `record_blocked` op + TS 플러그인 `recordBlocked()` 배선으로 OpenCode 실사용 세션에서도 감사 이력이 쌓이게 함(REQ-6). 테스트 22건 추가(+기존 3건 수정), 전체 스위트 3,462 passed·회귀 0건 | SPEC-019 완료(`LiveGuardrail` 재사용) · SPEC-024 완료(`violation_search`/`search_violations()`/`violation_search_mcp.py` 확장) · SPEC-028 완료(`snapshot()`의 무조건 노출 패턴 재사용) |
| [SPEC-031](SPEC-031-tool-execution-result-capture.md) | **도구 실행 결과(exit code/output) 캡처** — `ToolCallAnalyzer`는 이미 `tool_calls`의 `"success"` 키를 읽지만(직접 확인) 그 값을 채우는 호출부(`LiveGuardrail.record_tool_call()`)에 실행 결과를 받을 자리가 없어 Gate G가 항상 낙관적 기본값(성공)으로 떨어지던 것을 해소 | P9 | **Implemented (2026-07-07)** — REQ-1~3 전체 완료: `record_tool_call(output=...)`이 allow-list 키(`success`/`exit_code`/`stdout`/`stderr`)만 병합, `stdout`/`stderr`는 `max_tool_output_chars`(기본 2000)로 truncate(REQ-1, `ToolCallAnalyzer.analyze_execution()` 직접 호출로 신규 코드 없이 반영됨을 재확인). stdio 브리지의 `record`/`init`에 선택적 `output`/`max_tool_output_chars` 필드 추가(REQ-2). TS 플러그인이 `tool.execute.after`의 그동안 버려지던 `output` 파라미터를 캡처해 `output.output`(타입 보장)을 stdout으로, `output.metadata`(any)에서 exit code 후보 키를 best-effort로 탐색(REQ-3, 실제 설치된 `@opencode-ai/plugin@1.17.9` 타입 대상 `tsc --noEmit`으로 신규 타입 에러 0건 확인 — 단 metadata의 실제 런타임 키는 라이브 미검증으로 정직하게 남김). 테스트 10건 추가, 전체 스위트 3,472 passed·회귀 0건 | SPEC-019 완료(`record_tool_call()` 확장) · SPEC-028 완료(`tool_calls`→`TaskResult.tool_calls` 승격 경로 재사용) |
| [SPEC-032](SPEC-032-team-concurrency-scope-check.md) | **`TeamConcurrencyConfig`** (축소 범위 다중 세션 스코프 충돌 감지) — `.aoo/claims.jsonl` 기반 스코프 겹침 확인이 세션 시작 *전* 사람이 수동으로 호출하는 예제 코드로만 존재해, 세션 *도중*의 위반은 `LiveGuardrail`이 전혀 잡지 못하던 갭을 해소. `bash` 자유 형식 파싱과 매 호출 재조회 문제는 범위를 좁혀(`read`/`edit`/`write`만, 세션 시작 1회 로드) 우회 | P9 | **Implemented (2026-07-07)** — REQ-1~6 전체 완료: `Evaluator_Examples/ch28_local_ade_loop.py`의 `check_scope_claim()`/`append_claim()`을 `gates/team_concurrency.py`로 로직 변경 없이 승격(REQ-1). `TeamConcurrencyConfig`(REQ-2). `LiveGuardrail.__init__`이 생성자 시점 1회만 클레임/공유파일을 로드(REQ-3, 이후 재조회 없음을 테스트로 확인). `check_before_tool_call()`의 기존 `scope` 검사 직후에 경로 겹침 검사 추가 — `bash`는 `scoped_tool_names` 기본값에서 제외돼 차단 안 됨을 확인(REQ-4). `record_blocked_attempt()`가 신규 차단 유형에도 코드 변경 없이 동작(REQ-5). `refresh_team_claims()`로 장시간 세션에서 수동 재조회 지원(REQ-6). 테스트 22건 추가, 전체 스위트 3,494 passed·회귀 0건 | SPEC-019 완료(`LiveGuardrail` 확장) · SPEC-024 완료(`.aoo/claims.jsonl` 예제 로직 승격) · SPEC-030 완료(`record_blocked_attempt()` 재사용) |

## 백로그

모든 백로그 항목이 SPEC-015/016/017/019로 정식 스펙화 및 구현 완료(2026-07-03). SPEC-020/021은
SDK 전반 성숙도 개선 트랙으로 구현 완료(2026-07-04). SPEC-025/026(둘 다 2026-07-06 완료)은
"Agent-Evaluator 자체 SDK가 목표하는 두 축(개발 중 품질 개선 확인/운영 중 실행 품질·드리프트
확인)에 대한 코드 감사"에서 나온 트랙. SPEC-027(2026-07-06 완료)/028(2026-07-07 완료)은
그 감사의 후속으로, "AOO ADE(Agent-Evaluator+Ollama+OpenCode) 로컬 개발 루프 관점에서 SDK를 어떻게
더 확장할 수 있는가"를 다시 분석한 결과 나온 P9 트랙이다 — SPEC-027은 SPEC-025가 완성한
버전 비교 파이프라인(`agent_version` 소비 측)에 커밋 SHA 기반 자동 태깅을 채워 넣고,
SPEC-028은 OpenCode 세션이 이미 거치는 배치 리포트 파이프라인에서 Gate G/D/A가 왜 의미
있게 채워지지 않는지 코드로 확인한 뒤 바로잡아 "실시간 차단(SPEC-019) → 배치 Gate A–G
종합평가 → 버전 비교(SPEC-025+027)"라는 하나의 개발자 여정을 완성한다. 상세
스펙 미작성 상태의 신규 항목이 생기면 이 섹션에 먼저 등록하고, 착수 전 반드시 정식 스펙(Context/REQ/Acceptance)을
작성할 것 — 스펙 없이 바로 구현에 들어가지 않는다.

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
| **P7** | SPEC-024 ✅(2026-07-05) | P5(SPEC-019)의 실제 라이브 검증(Media/Book Ch27/28 집필) 과정에서 ctx/mem0 두 제3자 대안이 각각 다른 이유로 실패하는 것을 확인한 뒤 나온 후속 트랙 — 제3자 도구 의존 없이 Agent-Evaluator 자신의 SQLite 백엔드를 검색 가능한 로컬 메모리로 확장 |
| **P8** | SPEC-025 ✅·SPEC-026 ✅(2026-07-06) | Agent-Evaluator SDK 자체가 목표하는 두 축 — (1) 개발 중 코드/프롬프트 변경이 품질을 개선하는지 확인, (2) 운영 중 실행 품질·드리프트·이상징후 확인 — 을 코드 대조로 감사한 뒤 나온 트랙. SPEC-025는 (1)에서 저장만 되고 소비되지 않던 `prompt_version`/`agent_version`을 실제 비교 파이프라인에 연결하고 pairwise judge·골든셋 회귀 게이트를 추가; SPEC-026은 (2)에서 인메모리 전용이라 재시작에 살아남지 못하던 `AnomalyDetector` 기준선을 SQLite로 영속화하고 `AlertEngine`/`ImplicitFeedbackTracker`와 연결. 둘 다 P7(SPEC-024)이 이미 검증한 "제3자 도구 대신 자체 SQLite 백엔드를 확장" 원칙을 그대로 계승 |
| **P9** | SPEC-027 ✅(2026-07-06)·SPEC-028 ✅(2026-07-07)·SPEC-029 ✅(2026-07-07)·SPEC-030 ✅(2026-07-07)·SPEC-031 ✅(2026-07-07)·SPEC-032 ✅(2026-07-07) | P8(SPEC-025/026) 완료 후 "AOO ADE 로컬 개발 루프 관점에서 SDK를 더 확장할 수 있는 부분"을 다시 분석한 결과 나온 트랙 — 실시간 LiveGuardrail(안전 차단)과 배치 Gate A–G 종합평가(품질 확인)를 실제로 잇는다. SPEC-025가 이미 `agent_version`을 소비하는 비교 파이프라인(group_by·pairwise·baseline-version·대시보드 UI)을 완성해 뒀지만, 그 값을 채우는 쪽은 여전히 전부 수동 입력이었다 — SPEC-027은 git 커밋 SHA + 미커밋 변경 해시로 이 값을 자동 생성해 커밋 없이 반복 iteration하는 로컬 루프도 자동으로 구분되게 한다. SPEC-028은 OpenCode 세션이 이미 거치는 `PerformanceMonitor` 파이프라인에서 Gate G(도구 사용 미노출)·D(execution_time 상수 0.0)·A(placeholder로 오도하는 completion_score)가 왜 의미 있게 채워지지 않는지 코드로 직접 확인하고 바로잡은 뒤, SPEC-027의 자동 태깅을 연결해 "실시간 차단 → 배치 종합평가 → 버전 비교"라는 하나의 개발자 여정을 완성한다(REQ-5는 SPEC-027 완료 후 착수). SPEC-029는 SPEC-027이 만든 dirty-hash 태그 자체가 불투명해 대시보드에서 여러 iteration을 구분하기 어렵던 UX 갭을 `iteration_note`로 보완한다. SPEC-030은 완전 차단된 시도가 `tasks`/`violation_search` 어디에도 남지 않아 "무엇이 왜 차단됐는가"를 나중에 검색할 수 없던 감사(audit) 갭을, Gate B/E 점수 계산과 완전히 분리된 `blocked_violations` 별도 이력으로 메운다. SPEC-031은 `ToolCallAnalyzer`가 이미 읽는 `tool_calls`의 `"success"` 키를 실제로 채워 넣는 경로(`record_tool_call(output=...)` + OpenCode 플러그인의 `tool.execute.after` 결과 캡처)를 신설해 Gate G가 "차단되지 않고 실행됨"을 넘어 "실제로 성공했는가"까지 반영하게 한다(exit code 탐지는 OpenCode 공개 타입이 `metadata: any`라 best-effort로 남김). SPEC-032는 `.aoo/claims.jsonl` 기반 팀 스코프 겹침 확인이 세션 시작 전 수동 절차로만 존재하던 것을, `bash` 자유 형식 파싱 문제(미해결)와 매 호출 재조회 문제(순수 조회 계약 위반)를 축소된 범위(`read`/`edit`/`write`만, 세션 시작 1회 로드)로 우회해 `LiveGuardrail`에 자동 연동한다 |

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
