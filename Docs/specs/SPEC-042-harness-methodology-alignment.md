# SPEC-042: Harness Methodology 정합 개선 (Draft)

- **Phase**: P11
- **상태**: ✅ **완료 (2026-09-08)** — REQ-1~8 전부 구현. (REQ-4·5·7은 아래 설명대로 설계를 수정해 구현.) 커밋 대기 — 사용자 지시 시 직접 main에 커밋/푸시.
  - **REQ-6 ✅ (2026-09-08)**: `circuit_breaker_recover_after` — 트립된 뒤 연속 M회(기본 `circuit_breaker_after × 2 = 10`) 실제 실행되면 관찰 전용 자동 해제. Claude 훅(`claude_code_hook.py` `_read/_write_circuit_state`에 `clean_since_trip` 필드 · `handle_post_tool_use` 복구 로직 · `_resolve_circuit_recover_after()`) + OpenCode 플러그인(`agent-evaluator.ts` `CIRCUIT_BREAKER_RECOVER_AFTER` · `session.cleanSinceTrip`) 대칭. 관찰 전용 중 재차단 시 `clean_since_trip=0` 리셋. `0`/음수면 SPEC-041의 세션 내내 sticky 유지. `DEFAULT_GUARDRAIL_CONFIG`에 키 추가(`claude upgrade`가 기존 설정에 deep-merge). `_integration_health.validate_guardrail_config`/`probe_blocked_capture`의 bridge-only pop 목록에 추가. 테스트 5건(`TestCircuitBreaker`), 전체 `test_claude_code_hook.py` 59 passed · `tsc --noEmit` 0.
  - **REQ-2 ✅ (2026-09-08)**: `insights.verdict.decision_ready`(bool) + `verdict.undecided_reason`(str|null) — `_attach_decision_ready()`가 post-dict 블록에서 계산. `false` 조건: (a) 이진 pass-rate Wilson 95% CI가 TCR 타깃을 걸침(`_running_verdict_section` 재사용, `decisive==False`), 또는 (b) `threshold_sensitivity.knife_edge`. `level in (not_ready, unknown)`이면 항상 `true`(결정적). partial 모드에도 부착(threshold_sensitivity 없이 CI 검사만). `agent-eval gate --hold-on-undecided` → would-be PASS(exit 0)만 exit 75로 승격(1~4는 불변), stderr에 사유. `insights.schema.json` verdict에 두 필드 명시 추가. HTML 리포트 exec-summary에 "HOLD FOR REVIEW" 배너. `Docs/05` exit code 표 + `main.py` gate epilog(4·75 행 보강). 테스트 `test_spec042_hold_on_undecided.py` 8건, 관련 스위트 1320+8 passed · 0 new ruff/mypy.
  - **REQ-3 ✅ (2026-09-08)**: `recommend_fix` MCP가 `.aoo` 로그의 improvement track record 한 줄을 덧붙임. `recommend_fix_mcp.py`에 `_load_priors()`(experiments.jsonl + recommendation_outcomes.jsonl → `synthesize_priors`) · `_prior_note()` · `_fmt_bucket()`. `format_recommendation(..., category=, aoo_dir=)`, `recommend_fix(gate, metric, value, category)` 툴에 `category` 파라미터 추가(prompt_edit/config_change/data_fix — 있으면 그 버킷만, 없으면 Gate별 상위 3버킷, 없으면 overall 폴백). `n<3`이면 "thin sample" 라벨. 로그 없으면 이전과 동일(정적 지식만). `python -m …recommend_fix_mcp <aoo_dir>`(기본 `.aoo`). `cli/claude.py` `_resolve_aoo_arg(is_global)` — 로컬 설치는 `<project_root>/.aoo` 절대경로를 등록에 append(글로벌은 상대 기본값), `claude doctor`가 stale 등록에 info. OpenCode는 상주 프로세스라 cwd 기준 `.aoo` 기본값 사용(코드 변경 없음, docstring만). 테스트 `TestPriorNoteReq3` 6건, `test_recommend_fix_mcp.py` 33 passed · 0 new ruff/mypy.
  - **REQ-7 ✅ (2026-09-08)**: `LiveGuardrail(human_only_patterns=[...])` — 직렬화된 인자에 대소문자 무시 substring 매치 시 `gate="B"`, reason `"human_only: …"`, remediation "사람이 직접 수행"으로 차단(되돌림, 대기 없음). `check_before_tool_call`에서 protected_write 직후(내용 아닌 범주 검사). None/[] = 꺼짐. 브랭크 패턴 필터링, 직렬화 실패해도 안 죽음. `record_blocked_attempt`는 무수정으로 새 유형 수용, `_blocked_detail._BLOCK_REASON_PREFIXES`에 `"human_only:"` 추가. `live_guardrail_stdio.build_guardrail`가 `human_only_patterns` 리스트 전달, OpenCode `GuardrailInitConfig` 타입 + 설정 passthrough(TS 로직 무변경), Claude 훅은 `guardrail_config.json` 통과. 테스트 `TestHumanOnlyPatternsReq7` 7건 · tsc 0 · 0 new ruff/mypy.
  - **REQ-1 ✅ (2026-09-08)**: `acceptance_criteria` optional 필드. `create_taskresult(acceptance_criteria=[...])` → `TaskResult.extra["acceptance_criteria"]`(시그니처 kwarg 1개 추가, 없으면 불변). `EvalMetadata(extra={...})` 경로는 이미 동작. `insights._acceptance_coverage_section(tasks)` — criterion별 (a) 전체 문구 substring 또는 (b) content-word 토큰 60%+ 겹침이면 satisfied. `{method, n_tasks_with_criteria, total_criteria, satisfied_criteria, fully_satisfied_tasks, coverage_pct, by_task[{task_id,total,satisfied,unmet}], note}`. **게이트 점수 아님** — `verdict.level` 불변(테스트로 고정). partial 모드에도 포함. `insights.schema.json` + HTML 리포트 `_build_acceptance_coverage()`("Acceptance Criteria" 섹션) + `_TOC_LABELS`. 테스트 `test_spec042_acceptance_coverage.py` 10건 · 0 new ruff/mypy.
  - **REQ-8 ✅ (2026-09-08)**: `insights.efficiency_opportunities`에 `tier_downshift` opportunity 추가((d)번째 kind). task_type별 `{n, mean_accuracy, cost_per_task_usd}` 집계 → 최고비용 타입이 아니고 `mean_accuracy ≥ 0.85`(n ≥ 3)이고 `cost_per_task ≥ 0.8 × dearest`면 "이 타입을 더 작은 모델로" 제안(정량 투영 없음, `risk`에 "measure the drop" 명시). `_task_token_cost` 재사용. schema `kind` enum + `_EFF_KIND_LABEL`("Tier downshift"). `Docs/AOO_STACK.md`에 "Task nature ↔ model tier (Harness principle 5)" 절 신설(judge tier + agent tier per task type + "SDK는 tier를 강제하지 않음"). 테스트 `test_spec042_tier_downshift.py` 6건 · 0 new ruff/mypy.
  - **REQ-4 ✅ (2026-09-08)**: **설계 변경** — `PerformanceMonitor(repeat_runs=K)`는 채택하지 않음(PM은 수동 레코더라 평가를 재실행할 수 없음). 대신 `agent_evaluator/repeat.py` 신설: `run_repeated(eval_fn, k)` — 호출자가 준 zero-arg `eval_fn`(전체 평가 1회 → 결과 dict)을 K회 호출, `summarize_repeated(runs)`가 `{runs, gate_pass_count, gate_verdicts, flip_rate, majority_verdict, tcr_values/mean/stddev, unstable_tasks, n_unstable_tasks, deterministic}`로 접음. "pass" = 측정된 Gate A–G 전부 ≥ 0.7(새 공식 없음). 결과를 `result["extra_metrics"]["repeat_runs"]`(summary dict 또는 raw K-run list)에 넣으면 `insights.nondeterminism_repeat`(신규 top-level 키, `nondeterminism`이 list라 하위키 불가)로 표면화 — `_verdict_flip_section()`. `__init__.py` export(`run_repeated`/`summarize_repeated`). `insights.schema.json` + HTML 리포트 `_build_verdict_stability()`("Verdict Stability" 섹션, `_build_nondeterminism`가 prepend) + `_TOC_LABELS`. 릴리스 후보/nightly 전용(K× 비용), 멱등 에이전트만. 테스트 `test_spec042_repeat_verdict_flip.py` 13건, 관련 스위트 586+ passed · 0 new ruff/mypy.
  - **REQ-5 ✅ (2026-09-08)**: **설계 변경** — 스펙의 `last_replayed_index`(증분 인덱스)는 채택하지 않음. Claude Code 훅은 매 호출이 별도 프로세스라 인덱스로 재구성된 guardrail 상태를 프로세스 간에 이어갈 수 없어 인덱스 방식은 오히려 이력 손실. 대신 **bounded-tail replay**: `check_before_tool_call()`에서 과거 이력에 의존하는 실시간 검사는 윈도우 루프 감지 하나뿐이므로(deadlock/privilege_escalation/tool_chain_attack/누적 scope 상한은 AC 기본 설정에서 OFF), PreToolUse는 마지막 `live_loop_window + 5`개만 재생 → O(n²)→O(n). `_replay_tail_records(config, records)`가 이력 전체 필요 검사가 켜져 있으면 전량 반환(등가). SessionEnd는 여전히 전량 재생(Gate G 배치 리포트). 테스트 `TestReplayTailReq5` 8건(200-call 등가성 + tail 슬라이스 + full 폴백), `test_claude_code_hook.py` 67 passed · 0 new ruff/mypy.
- **의존성**: SPEC-041 완료(`build_insights()` / `insights.*` 소비 경로 재사용) · SPEC-019/028 완료(LiveGuardrail·AC 훅) · SPEC-049(P49 `agent-eval improve` 폐루프) · P43 `agent-eval target`
- **검증 기준일**: 2026-09-08. 아래 Context의 모든 `파일:라인`은 이 날짜에 코드를 직접 대조해 확인했다.

---

## 0. 분석 재검증 결과 (선행 분석의 오류·과장 정정)

이 스펙에 앞서 제시한 "Top-5 개선안" 분석을 코드베이스와 재대조해 아래 오류/과장을 확인했다. REQ 정의는 **정정된 사실**을 기준으로 한다.

| # | 선행 분석의 서술 | 판정 | 근거 (2026-09-08 확인) | 정정 |
|---|---|---|---|---|
| E1 | "서킷 브레이커가 일방향 — 성공해도 연속 차단 카운터가 안 줄어든다" | **오류** | `integrations/claude_code_hook.py:476-480` — `handle_post_tool_use`가 도구가 실제 실행되면 `_write_circuit_state(circuit_path, 0, ...["tripped"])`로 `consecutive_blocks`를 **0으로 리셋**한다. 주석: "도구가 실제로 실행됐으므로 연속 차단 스트릭을 리셋한다 … 단 이미 트립된 상태(tripped)는 유지한다." | 카운터 감쇠는 **이미 구현됨**. 남는 갭은 **`tripped`(관찰 전용 전환)가 세션 내내 sticky** — 이후 N회 정상 호출해도 해제 안 됨. → REQ-6 (범위 축소) |
| E2 | "게이트가 pass/fail 이진이다" | **과단순화** | `cli/gate.py` + `Docs/05_QUALITY_GATE.md:144-155` — exit **0/1/2/3/4** (통과 / 임계미달 / baseline 회귀 / 골든셋 회귀 / 케이스 회귀·`--max-review-high`)가 이미 존재. | "이진"이 아니라 **5단계**. 단 **비-0 코드는 전부 "무언가 실패"** — "판단 보류, 사람에게 라우팅"에 해당하는 코드가 없음. → REQ-2는 "이진 → 5단계 인지 + 6번째 '보류' 상태 신설"로 재정의 |
| E3 | "`insights.verdict`에 이미 `undecided`가 있다" | **부정확** | `reporting/insights.py:2230` `_running_verdict_section` 만 `"undecided"`를 냄(`:2282`). 이는 `running_verdict`(P50 partial 경로, `:6432`에서 배선)에만 있고, 전체 실행 `verdict` 섹션에는 없음. | "보류" 재료는 **mid-run partial 경로에만** 존재. 전체 실행 게이트에는 없음 → REQ-2가 이 재료를 full 경로·CI exit code까지 승격 |
| E4 | "`recommend_fix`가 정적 온톨로지 조회만 한다" | **정확 (도구 한정)** | `integrations/recommend_fix_mcp.py`·`ontology/metric_registry.py`에 `prior_for`/`recommendation_outcome` 참조 0건. **단** `reporting/insights.py:6320-6335`는 `prior_for(priors, rec["gate"], cat)`로 `insights.recommendations[].prior`를 이미 채운다. | "능력(P57 `synthesize_priors`/`prior_for`)은 있고 **`recommend_fix` MCP 도구에만 안 붙었다**"로 정정 → REQ-3 |
| E5 | "이미 `.aoo/recommendation_outcomes.jsonl`에 데이터가 쌓인다" | **과장** | `cli/improve.py:314-316` — `record_recommendation_outcome()`는 **`improve verify --persist`에서만** append. 자동 채움 경로 없음. | "쌓을 구조는 있으나 팀이 `improve verify --persist`를 실제로 돌려야 채워짐"으로 정정 |
| E6 | "판정 뒤집힘률(verdict-flip)을 재는 모드가 없다" | **정확 (전체 평가 한정)** | `reporting/insights.py:909/917` `extra_metrics.judge_runs`(≥2 run, 옵트인), `:1081` `judge_self_consistency`, `:952` `_judge_robustness_section` — 전부 **판정기(judge)** 안정성. `LLMJudge.self_consistency(task, k=3)`도 judge 자기일치. 에이전트 출력을 K회 재실행해 verdict-flip을 내는 `PerformanceMonitor`/`QuickEval` 모드는 없음. | "인접하지만 judge에 한정된 기능이 있다"는 각주 필요 → REQ-4 |
| E7 | "세계적 수준 프레임워크가 공통으로 '신뢰구간이 임계선을 걸치면 자동으로 사람에게' 한다" | **근거 없는 일반화** | 출처 없음. 타 프레임워크 조사 없이 단정. | 삭제. REQ-2의 근거는 "타사 관행"이 아니라 **이 프로젝트의 설계 목표(knife-edge를 뭉개지 않는다)** 로만 서술 |
| E8 | "며칠 작업" 등 소요 기간 단정 | **근거 없음** | 추정 근거 없음. | "기존 구조 재사용, 소규모 변경" 수준의 상대 규모만 표기. 절대 기간은 명시하지 않음 |
| E9 | "인사이트 계층 62키" | **경미** | `CLAUDE.md`는 "~62". | "약 62키"로 표기 |
| E10 | "AC 리플레이 지연이 선형→2차로 누적" (§3 표현) | **경미한 혼동** | `integrations/claude_code_hook.py:329` `_replay`는 세션 파일 전체를 순회하는 단순 `for` 루프, `:382`(pre-tool 매 호출)·`:555`(session end)에서 무메모이제이션 호출. | **호출당** 재생 비용이 이력 길이에 비례해 선형 증가하고, **세션 누적**이 O(n²) — 로 구분해 서술 → REQ-5 |

**방향이 틀린 제안은 없었다.** E1이 유일한 명백한 오류(원칙 4 "이미 있는 걸 다시 만들지 않는다"를 스스로 어긴 셈)로, REQ-6에서 `tripped` 해제로 범위를 좁힌다.

---

## 1. Goals

Agent-Evaluator / AOO 조합 / AC 조합이 Harness Methodology 6원칙에 더 잘 정합하도록, **이미 있는 재료를 개발자가 실제로 만나는 진입점(CI exit code · MCP 응답 · 훅 상태 · PR 코멘트)에 배선**한다. 새 판정 공식은 도입하지 않는다(SPEC-041과 동일 원칙).

## 2. Non-Goals

- **완전 자율 판정 기계화** — REQ-2는 "보류" 상태를 *추가*할 뿐, 기존 pass/fail 의미를 바꾸지 않는다.
- **라이브 루프의 동기 "사람 승인 대기"** (선행 분석 제안 I 원안) — tool 실행 전 동기 경로에서 사람을 기다리는 것은 DX를 심하게 해친다. 채택하지 않는다. 대신 REQ-7은 `branch_guard`식 **범주적 되돌림**("이건 사람이 직접 하라")만 확장한다.
- **서킷 브레이커 카운터 감쇠 신규 구현** (선행 분석 제안 F 원안, E1으로 오류 확인) — 이미 구현돼 있다. REQ-6은 `tripped` 해제만 다룬다.
- **AOO tier 강제** — 모델 tier 배분은 OpenCode/Ollama 설정 영역으로 SDK 통제 밖. REQ-8은 `cost_economics` 인사이트에 **조언**만 얹는다.
- Spec/EARS 작성 **강제** — REQ-1은 optional 필드로만 도입한다.

## 3. Requirements

### REQ-1 — Acceptance Criteria를 태스크·골든셋의 optional 1급 필드로 (원칙 1: 코드보다 결정이 먼저)

- **Context**: `agent_evaluator/` 전체에 `spec`/`EARS`/`acceptance_criteria` 기능 없음(grep 0건; `SPEC-002` 주석과 `utils/targets.py`(SLO pin)만 존재). 게이트 임계값(0.7, TCR 85 등)은 팀이 합의한 요구사항이 아니라 도구 기본값. `agent-eval target set`(P43)이 프로젝트 단위 SLO는 pin하지만 **태스크 단위 "하기로 한 일"** 은 없음.
- **변경**:
  - `create_taskresult(...)` / `@agent_eval(...)` / 골든 케이스 스키마에 `acceptance_criteria: list[str] | None` optional 필드 추가. 없으면 동작 100% 불변.
  - 값이 있으면 `reporting/insights.py`에 `acceptance_coverage` 섹션 신설 — 각 criterion을 (a) `required_keywords`/`InstructionConfig` 매칭 또는 (b) LLMJudge claim 검증(옵트인)으로 충족/미충족 판정, "AC N개 중 M개 충족"으로 렌더. **새 게이트 점수 아님** — 리포트/insights 표시 전용.
  - 정적 HTML 리포트 `_build_*` + `_TOC_LABELS` + 스키마 + `test_insights_schema.py` 시나리오 반영(SPEC-041 §"Adding an insight section" 절차).
- **Acceptance**: AC 필드 미지정 결과 JSON은 `insights` 키 집합·게이트 점수가 바이트 단위로 이전과 동일. AC 3개 중 2개 충족인 케이스가 `acceptance_coverage.satisfied == 2, total == 3`로 나온다.
- **Risks**: criterion 매칭이 부정확하면 오해 유발 → 판정 방식(keyword/judge)과 신뢰도를 섹션에 함께 기재. LLMJudge 경로는 옵트인.
- **규모**: 중 (스키마 + 1개 insight 섹션 + 렌더). 복리형 — 팀이 AC를 쓰기 시작하면 가치 증가.

### REQ-2 — `agent-eval gate`에 "보류(undecided)" 종료 코드 (원칙 6: 사람의 최종 책임)

- **Context**: `cli/gate.py` exit 0/1/2/3/4 존재(§0 E2). 그러나 비-0은 전부 "실패" 의미. knife-edge(`insights.threshold_sensitivity.knife_edge`)·비결정 판정도 pass/fail로 뭉개짐. `undecided` 판정 재료는 `_running_verdict_section`(`reporting/insights.py:2230`, Wilson CI on binary pass-rate vs TCR target)에 있으나 **P50 partial 경로 전용**(§0 E3).
- **변경**:
  - `_running_verdict_section`의 Wilson-CI 로직을 full-run 경로에서도 계산하는 `verdict.decision_ready: bool` + `verdict.undecided_reason: str | None` 필드 추가(pass-rate CI가 TCR target을 걸치거나, `knife_edge`가 참이고 CI half-width가 임계 초과일 때 `decision_ready=False`).
  - `agent-eval gate ... --hold-on-undecided` 플래그: `decision_ready=False`면 **exit 75**(BSD `sysexits.h` `EX_TEMPFAIL` 관례 차용 — 이 목적의 표준은 아님, 프로젝트 규약으로 문서화) + stderr에 "판정 보류: 사람 확인 필요 (사유)". 플래그 없으면 기존 동작 100% 불변(보수적 default).
  - `--notify` 대상에 "held for review" 상태 전달(`alerts/` `dispatch_gate_result` `held` 케이스).
- **Acceptance**: `--hold-on-undecided` 없이는 exit code 분포가 이전과 동일. pass-rate 12/17, TCR target 70%인 결과에서 Wilson 95% CI가 70%를 포함하면 `--hold-on-undecided`가 exit 75. CI가 target을 완전히 상회/하회하면 각각 0/1.
- **Risks**: exit 75가 기존 CI 스크립트에서 "일반 실패"로 처리될 수 있음 → 문서에 "75는 옵트인, 파이프라인이 명시적으로 처리해야 의미가 있다" 명기. `Docs/05_QUALITY_GATE.md` exit code 표에 행 추가.
- **규모**: 소 (exit code 1개 + verdict 필드 2개 + partial 로직 재사용).

### REQ-3 — `recommend_fix` MCP가 팀 이력 prior를 반영 (원칙 2: 통과보다 증명)

- **Context**: `recommend_fix_mcp.py`는 정적 온톨로지만 반환(§0 E4). `rca/improvement_priors.py::synthesize_priors()`/`prior_for()`가 `.aoo/experiments.jsonl` + `.aoo/recommendation_outcomes.jsonl`을 (gate, change-category)별 confirm-rate/mean-Δ로 접는 순수 계산 계층으로 이미 존재하고, `reporting/insights.py:6320-6335`가 `insights.recommendations[].prior`에 이를 쓴다. `recommend_fix`만 안 봄.
- **변경**:
  - `recommend_fix(gate, metric=, value=)` 응답에, 로그 파일이 있으면 `prior_for(priors, gate, category)` 결과를 "이 유형의 변경은 이 게이트에서 과거 3/4 확인됨(평균 Δ+0.06, n=4)" 한 줄로 덧붙임. 로그 없거나 매칭 없으면 문구 생략(현행 동작).
  - 로그 경로 탐색: `recommend_fix_mcp.py`에 `--priors-log`/`--experiments-log` 옵션(기본 `.aoo/` 상대). `agent-eval claude|opencode install --with-recommend-fix`가 로컬 설치 시 절대경로를 append(SPEC-024 `--with-violation-search` DB 경로 패턴과 동일).
- **Acceptance**: 로그 없는 환경에서 `recommend_fix` 출력이 이전과 동일. `outcomes.jsonl`에 Gate E "config" 변경 3건 중 2건 confirmed가 있으면 응답에 "2/3 confirmed" 문구 포함.
- **Risks**: 표본이 작을 때(n≤2) 과신 유발 → n<3이면 "표본 부족" 라벨. `pretty` 문구는 SPEC-041 `pretty_metric_name` 공유.
- **규모**: 소 (기존 `prior_for` 호출 + 문자열 조립).

### REQ-4 — 전체 평가 재실행 비결정성 모드 (원칙 2)

- **Context**: judge 안정성(`judge_runs`/`judge_self_consistency`/`_judge_robustness_section`, `LLMJudge.self_consistency`)은 있으나 에이전트 출력을 K회 재실행해 verdict-flip rate를 내는 것은 없음(§0 E6). `insights.nondeterminism`은 단일 실행 내 신호만.
- **변경**:
  - (구현: `PerformanceMonitor`는 수동 레코더라 평가를 재실행 못 함 → `agent_evaluator/repeat.py`의 `run_repeated(eval_fn, k)` / `summarize_repeated(runs)`로 이관.) 호출자가 준 전체-평가-1회 함수를 K회 실행, 각 실행의 게이트 pass/fail·TCR·태스크별 pass를 모아 `insights.nondeterminism_repeat`(신규 top-level 키)에 `{runs, gate_pass_count, gate_verdicts, flip_rate, majority_verdict, tcr_mean/stddev, unstable_tasks, deterministic}` 기록.
  - 비용·시간이 K배이므로 문서에서 **릴리스 후보 / nightly 전용**으로 안내. 매 PR 사용은 비권장.
  - 조기 종료 없음 — 단순 집계.
- **Acceptance**: `repeat_runs=1`(기본)에서 `insights` 키 집합·값이 이전과 동일. 결정적 에이전트를 `repeat_runs=3`으로 돌리면 `flip_rate == 0.0`. 5회 중 2회 Gate A fail인 에이전트에서 `flip_rate ≈ 0.4`, `unstable_tasks`에 해당 케이스.
- **Risks**: 재실행이 부작용(외부 상태 변경)을 일으키는 에이전트에는 부적합 → 문서에 "멱등 에이전트에만" 명기. `idempotency` Config와 상호 참조.
- **규모**: 중 (실행 루프 + 1개 insight 서브필드).

### REQ-5 — AC(Claude Code) 훅 리플레이 증분화 (원칙: 최소 부작용 / 재현성 인프라)

- **Context**: `integrations/claude_code_hook.py:329` `_replay()`는 세션 파일 전체를 매번 순회. `:382`(매 PreToolUse), `:555`(SessionEnd)에서 무메모이제이션 호출. 호출당 비용은 이력 길이에 선형 비례, 세션 누적 O(n²)(§0 E10). OpenCode(상주 프로세스, 브리지가 세션 내내 살아있어 재생 불필요)와 비대칭.
- **변경 (구현 시 설계 수정 — §상태 참고)**: `last_replayed_index`(증분 인덱스)는 프로세스 간 guardrail 상태를 이어갈 수 없어 폐기. 대신 **bounded-tail replay** — `check_before_tool_call()`의 유일한 이력 의존 실시간 검사인 윈도우 루프 감지에 필요한 만큼(`live_loop_window + margin`)만 PreToolUse에서 재생.
  - `_replay_tail_records(config, records)` — deadlock / privilege_escalation / tool_chain_attack / 누적 scope 상한(`max_tool_calls`·`max_unique_tools`)이 설정되면 전량 반환(등가), 아니면 마지막 `live_loop_window + 5`개.
  - `handle_pre_tool_use`만 tail 적용. `handle_session_end`(배치 리포트 snapshot)는 전량 재생 유지.
- **Acceptance**: 200개 tool call 세션에서 tail/full 재생의 PreToolUse verdict가 동일(세션 끝 루프는 차단, tail 이전 옛 반복은 latch 안 됨). PreToolUse 재생 레코드 수 O(1).
- **Risks**: 이력 전체 필요 검사가 켜졌는데 tail만 재생 → `_replay_tail_records`의 needs_full 분기로 방지. fail-open 계약 유지.
- **규모**: 소~중 (헬퍼 1개 + PreToolUse 1줄 + 등가성 테스트). 사용자 비가시(긴 세션 팀이 조용히 수혜).

### REQ-6 — 서킷 브레이커 `tripped` 자동 해제 (원칙 3: 차단과 채점 분리 / 안전장치 가시성)

- **Context**: §0 E1 — `consecutive_blocks`는 성공 시 리셋되나(`claude_code_hook.py:476-480`), `tripped`(관찰 전용 전환)는 세션 내내 sticky. 한 번 트립되면 이후 수십 번 정상 호출해도 가드레일이 안 돌아옴. `circuit_breaker_after` 기본 5(`:95`).
- **변경**:
  - `_write_circuit_state`가 `tripped=True`인 상태에서 clean 호출 스트릭을 별도 카운트(`clean_since_trip`). `clean_since_trip >= recover_after`(신규 config, 기본 `circuit_breaker_after * 2 = 10`)면 `tripped=False`로 복귀 + stderr에 "circuit breaker recovered after N clean calls".
  - `guardrail_config.json`에 `circuit_breaker_recover_after` 키(옵트인; 미설정 시 위 기본). OpenCode 브리지 쪽 `GuardrailSession` 서킷 로직에도 대칭 반영(`opencode_plugin/agent-evaluator.ts`).
  - `circuit_breaker_recover_after: 0`이면 현행 동작(영구 sticky) 보존.
- **Acceptance**: 5회 연속 차단 → `tripped`. 이후 10회 clean 호출 → `tripped=False`, 다음 위험 호출이 다시 차단됨. `recover_after=0`이면 10회 clean 후에도 관찰 전용 유지.
- **Risks**: 공격이 "N회 clean → 1회 위험" 패턴으로 복구를 악용 → `recover_after` 기본을 임계의 2배로 크게 잡고, 복구 후 첫 차단은 즉시 재트립(카운터가 아니라 1회로). 문서에 트레이드오프 명기.
- **규모**: 소 (상태 필드 1개 + 복구 조건). 양 호스트 대칭.

### REQ-7 — 라이브 루프 "범주적 되돌림" 확장 (원칙 6) — 선택적, 낮은 우선순위

- **Context**: 라이브 루프의 정책성 차단은 `branch_guard`(SPEC-035) + `team_concurrency`(SPEC-032/036/037) 둘. 둘 다 자율 차단이며 "사람 승인 대기"는 없음(그리고 Non-Goals에 따라 추가하지 않음). "프로덕션 배포·DB 마이그레이션은 에이전트가 아니라 사람이" 같은 **범주**를 되돌리는 일반 메커니즘은 없음.
- **변경**:
  - `LiveGuardrail`에 `human_only_patterns: list[str] | None`(옵트인) — 매칭 시 `branch_guard`와 동일하게 차단 + "이 작업은 사람이 직접 수행하도록 지정됨" 메시지. 실행을 되돌릴 뿐 대기하지 않음.
  - `record_blocked_attempt()`는 코드 변경 없이 새 차단 유형 수용(SPEC-032/035에서 확인된 패턴).
- **Acceptance**: `human_only_patterns=["terraform apply", "alembic upgrade"]`에서 해당 명령이 차단되고 `blocked_violations`에 `gate="human_only"` 기록. 미설정 시 동작 불변.
- **Risks**: 자유 형식 bash 파싱 오탐 → `branch_guard`와 같은 보수적 substring 매칭 + fail-open. 범위를 좁게 유지.
- **규모**: 소. **우선순위 최저** — REQ-1~6 이후.

### REQ-8 — AOO 모델 tier 조언 (원칙 5: 모델 크기는 작업 성격에 맞춘다) — 선택적

- **Context**: `Docs/AOO_STACK.md`에 tier·모델 크기 매칭이 방법론으로 문서화돼 있지 않음. `judge_escalation_model`(작은 판정기→큰 판정기)만 존재. `insights.cost_economics`(P16)/`efficiency_opportunities`(P40)가 비용/효율 제안을 이미 냄.
- **변경**:
  - `insights.efficiency_opportunities`에 tier 다운시프트 후보를 추가 — 태스크 유형별(예: 단순 도구 실행 vs 분석) 평균 토큰·지연·정확도를 보고, "실행류 태스크는 더 작은 모델로 옮겨 $X/월 절감 가능(정확도 영향 추정 Δ)" 제안. 순수 관찰 기반, 강제 없음.
  - `Docs/AOO_STACK.md`에 "작업 성격 ↔ tier" 절 신설(방법론 문서화).
- **Acceptance**: 실행류 태스크의 정확도가 임계 이상이고 비용이 분석류와 비슷하면 다운시프트 후보로 나옴. 근거 수치(토큰/지연/정확도) 동반.
- **Risks**: 정확도 영향 추정이 빗나갈 수 있음 → "추정", 근거 표본 수 동반. 제안일 뿐 자동 적용 없음.
- **규모**: 소~중. **우선순위 낮음**.

## 4. Interface 변경 요약 (전부 하위호환)

| 대상 | 추가 | 기본값에서의 동작 |
|---|---|---|
| `create_taskresult` / `@agent_eval` / 골든 스키마 | `acceptance_criteria: list[str] \| None` | `None` → 완전 불변 |
| `agent-eval gate` | `--hold-on-undecided` (flag) | 미지정 → exit code 분포 불변 |
| `insights.verdict` | `decision_ready: bool`, `undecided_reason: str \| None` | 추가 키 (SPEC-041 `additionalProperties:true`) |
| `insights` | `acceptance_coverage`, `nondeterminism.verdict_flip` | 조건부 — 입력 없으면 `null`/생략 |
| `recommend_fix_mcp.py` | `--priors-log` / `--experiments-log` | 로그 없으면 문구 생략 (현행) |
| `agent_evaluator.repeat` (신규 모듈) | `run_repeated(eval_fn, k)` · `summarize_repeated(runs)` | 옵트인 헬퍼 — 호출 안 하면 무영향 |
| `insights` | `nondeterminism_repeat` | `extra_metrics.repeat_runs` 없으면 `null` |
| `claude_code_hook.py` | `_replay_tail_records()` (PreToolUse tail replay) | 이력 전체 필요 검사가 켜지면 전량 반환(동작 불변) |
| `guardrail_config.json` | `circuit_breaker_recover_after` (기본 `circuit_breaker_after*2`) | `0` → 현행 영구 sticky |
| `LiveGuardrail` | `human_only_patterns: list[str] \| None` | `None` → 불변 |

## 5. Compatibility

- 전 REQ가 옵트인. 기본값에서 기존 테스트 스위트(4,795+)·공개 API·결과 JSON 바이트 동일성 유지가 각 REQ의 Acceptance 조건.
- `insights.schema.json`은 SPEC-041에서 모든 object가 `additionalProperties:true`, nullable 섹션은 `["object"|"array","null"]`이므로 신규 키 추가는 스키마 breaking 아님. 그래도 REQ-1·REQ-2·REQ-4는 스키마에 명시적 정의 + `test_insights_schema.py` 시나리오 추가.
- `schema_version`은 필드 *추가*만 하므로 minor로 충분(현재 `"1.1"`). breaking 없음.

## 6. Rollout (권장 순서)

효과/비용 기준 우선순위: **REQ-6 → REQ-2 → REQ-3 → REQ-5 → REQ-4 → REQ-1 → REQ-7 → REQ-8**

1. **묶음 1 (저비용·안전 개선, 기존 구조 재사용):** REQ-6(`tripped` 해제), REQ-2(보류 exit code), REQ-3(prior 배선). 각각 독립 커밋, 각 REQ Acceptance를 테스트로 고정.
2. **묶음 2 (인프라):** REQ-5(증분 리플레이) — 등가성 테스트가 게이트. 단독 배포, 롤백 조건 = 200-call 등가성 실패 시 즉시 전체 재생으로 되돌림.
3. **묶음 3 (복리형):** REQ-1(AC 필드) + REQ-4(repeat_runs). 스키마·리포트·대시보드까지 SPEC-041 §"Adding an insight section" 5단계 절차 준수.
4. **묶음 4 (선택):** REQ-7, REQ-8 — 수요 확인 후.

각 묶음마다 `pytest` 전체 통과 + `ruff` 신규 위반 0 + `mypy` 신규 오류 0을 릴리스 조건으로 한다(SPEC-021 래칫).

## 7. Risks (전체)

| 시나리오 | 완화 |
|---|---|
| exit 75가 기존 CI에서 일반 실패로 처리됨 | 옵트인 플래그 + 문서 명시 + `Docs/05` exit code 표 갱신 |
| 증분 리플레이가 판정 상태를 미묘하게 다르게 재구성 | 200-call 등가성 테스트를 CI 게이트로; 파싱 실패 시 전체 재생 폴백 |
| `tripped` 자동 해제를 공격이 악용 | `recover_after` 기본을 임계 2배로; 복구 후 첫 차단은 즉시 재트립 |
| prior 표본 부족 시 과신 | n<3이면 "표본 부족" 라벨; 문구는 항상 confirm-rate + n 동반 |
| `repeat_runs`가 부작용 있는 에이전트에서 상태 오염 | 문서에 "멱등 에이전트 전용", `idempotency` Config 상호 참조 |
| AC criterion 매칭 부정확 | 판정 방식·신뢰도를 섹션에 동반; LLMJudge 경로는 옵트인 |

---

## 부록: Harness 6원칙 ↔ REQ 매핑

| 원칙 | 강화하는 REQ | 평가 프레임워크 관점의 속성 |
|---|---|---|
| 1. 코드보다 결정이 먼저 | REQ-1 | 구성 타당도 — 판정 기준이 도구 기본값이 아닌 선언된 계약 대비가 됨 |
| 2. 통과보다 증명 | REQ-3, REQ-4 | 폐루프 학습(팀별 자기교정) + 판정 안정성 측정 |
| 3. 차단과 채점 분리 | REQ-6 | 안전장치 가시성 — 관찰 전용 상태가 조용히 죽지 않음 |
| 4. 이미 있는 걸 다시 만들지 않는다 | (E1 정정으로 준수) | — |
| 5. 모델 크기 ↔ 작업 성격 | REQ-8 | 비용 효율 — 관찰 기반 tier 조언 |
| 6. 사람의 최종 책임 | REQ-2, REQ-7 | 결정 준비도 — "모르겠음"을 1급 결과로; 위험 범주의 범주적 되돌림 |
