# SPEC-043: 평가 프레임워크 → 개발·개선 지원 프레임워크 (Draft)

- **Phase**: P12
- **상태**: ✅ **전 REQ 완료 (2026-09-09)** — REQ-1·3·2·6a·4·5·6b·7. SPEC-042와 같은 원칙 유지: **새 Gate 채점 공식 없음, 전 REQ 옵트인, 기본값에서 결과 JSON 바이트 동일성 유지.** 커밋 안 함(SPEC-042·043 둘 다 미릴리스).
  - **REQ-7 ✅ (2026-09-09)**: `agent-eval improve apply-verify <baseline_result.json> --proposal <gate|gate:kind> --eval-cmd "<sh>" [--new-result PATH] [--repo .] [--prompt-file PATH] [--persist] [--keep-worktree]`. `cli/improve.py`에 `_cmd_apply_verify` + `_select_proposal` + `_locate_new_result` + `_git` 추가. 흐름: (1) 선택한 proposal을 `register_experiment`로 등록, (2) `git worktree add --detach <tmp> HEAD`로 격리 worktree 생성, (3) `_patch_prompt_edit`/`_patch_config_change`(기존 P61 헬퍼 재사용)로 diff 생성 → `git -C <wt> apply`, (4) `--eval-cmd`를 `subprocess.run(shell=True, cwd=<wt>)`, (5) `--new-result`(worktree 상대/절대) 또는 `<wt>/results/*.json` 중 실행 후 생성된 최신 파일로 결과 위치 파악, (6) `score_experiments([exp], new_result, baseline)` → verdict 출력. `--persist`면 `resolve_experiment` + `_record_outcome`(→ `recommendation_outcomes.jsonl`). **머지/커밋 절대 안 함** — 성공 시 worktree는 사람이 보라고 남김(제거 명령 출력), 실패 시 정리(`--keep-worktree`면 유지). data_fix proposal은 코드 diff가 아니라 거부. `data_fix`/비-git-repo/미존재 파일/미선택 proposal은 exit 1. 테스트 `test_spec043_improve_apply_verify.py` 16건, 0 new ruff/mypy(1038/204).
  - **REQ-6b ✅ (2026-09-09)**: 선호 신호 export. `datasets/preference_export.py` 신설 — `iter_preference_rows(result_data)`(한 결과 JSON에서 `{question, response_a, response_b, preferred: a|b|tie, source, annotator?}` 행 yield) + `export_preferences(path, out_path)`(파일/디렉토리 스캔 → JSONL, dedupe, malformed 파일 skip, `{n_written, by_source, n_files_scanned, n_files_skipped, out_path}`). 소스 3개: (1) `extra_metrics.llm_judge_pairwise` — `LLMJudge.judge_pairwise()` 이력을 `monitor.generate_report()`가 `skipped` 제외하고 자동 직렬화(입력 `question`/`response_a`/`response_b`도 `pairwise_results` 항목에 실음, 반환값은 back-compat 유지), `winner`→`preferred`. (2) `extra_metrics.preference_annotations` + task `extra.preference`(dict 또는 list) — 사람 A/B 라벨. (3) `insights.contrast_pairs`를 `tasks[]`에 task_id로 join — 실패 응답=a, 최유사 통과 응답=b, `preferred: "b"`, `source: "contrast_pair"`. `agent-eval feedback export-preferences <path> --out <jsonl>`(신규 서브커맨드 `cli/feedback.py` + `build_feedback_subparser`). **export만** — 리워드 모델/파인튜닝 없음. 테스트 `test_spec043_preference_export.py` 16건, 0 new ruff/mypy(1038/204).
  - **REQ-5 ✅ (2026-09-09)**: 얇은 결함 주입 하네스. `gates/fault_injection.py` 신설 — `FaultInjectionConfig(tool_failure_rate, added_latency_ms, latency_jitter_ms, fail_tools, seed)` · `FaultInjectionError(RuntimeError)` · `_FaultInjector`(시드 고정 `random.Random` 1개 = 데코레이터 인스턴스당 결정적 시퀀스) · `fault_injection_session()` contextmanager + `enter_/exit_fault_injection()` 토큰 API(contextvar). `tool_guard(fault_injection=)` — 데코레이터 인자 있으면 그걸로, 없으면(또는 no-op이면) 주변 `fault_injection_session`(= `@agent_eval(fault_injection=)`가 설치) 상속. 주입 지점은 `_check()`(차단 검사) **통과 후** `func()` 호출 직전 → `before_call(tool_name)`: 지연 sleep 후 `fail_tools` 포함 or `rng.random() < rate`면 `FaultInjectionError` raise(기존 `except BaseException: _record_failure` 경로가 실패로 기록). **차단 로직 무수정** — 차단이 항상 우선(`GuardrailBlockedError`가 먼저). `@agent_eval(fault_injection=)` — sync/async wrapper에서 `_enter_/_exit_fault_injection`으로 contextvar 설치, `_build_and_record`가 config를 `extra.fault_injection`에 echo → `monitor._build_lineage()`가 dedupe해 `lineage.fault_injection`(1건이면 dict, 여러 건이면 list). `FaultInjectionConfig`/`Error`/`session`은 `gates/live_guardrail`에서도 re-export(`tool_guard` 옆). 미설정이면 데코레이터 동작 100% 불변. 테스트 `test_spec043_fault_injection.py` 15건, 0 new ruff/mypy(1038/204).
  - **REQ-4 ✅ (2026-09-09)**: 프로덕션 이상/저확신 → 골든 후보 자동 편입. `datasets/golden_candidates.py` 신설 — `append_candidate` · `record_candidate_review(accept|reject|defer)` · `load_candidates` · `pending_candidates` · `summarize_candidates`(append-only JSONL, `decision_ledger.py` 패턴). `StreamingEvaluator(golden_candidate_sink=, candidate_confidence_threshold=)` — `record()`에 optional `question`/`response`/`confidence` 추가; 태스크가 에러거나 confidence < threshold면 `{question,response,trigger,task_id,reviewed:false}` append, 주기적 `AnomalyDetector` 스캔 결과도 event_id로 dedupe해 `trigger="anomaly:<metric>"`로 편입. 미설정이면 스트리밍 동작 100% 불변(모든 실패는 fail-safe로 삼킴). `agent-eval dataset review-candidates <jsonl>` — 인자 없으면 pending 목록/`--json`, `--accept <id> --to <golden.json>`는 `GoldenSetBuilder.merge_to_golden`으로 편입(전부 `needs_human_review` 플래그, 라벨은 사람), `--reject`/`--defer`는 review 행만 기록. `datasets/golden_health.assess_golden_health`가 골든셋/`history_dir` 옆의 `golden_candidates.jsonl`을 찾아 `pending_production_candidates: N` + note 한 줄 추가(`insights.golden_health` 경유 스키마 + 리포트 `_build_golden_health`). 새 판정 로직 없음. 테스트 `test_spec043_golden_candidates.py` 20건, 0 new ruff/mypy(1038/204).
  - **REQ-6a ✅ (2026-09-09)**: `agent-eval {claude,opencode} test-config <cases.yaml>`. 공유 헬퍼 `cli/_integration_health.py`에 `load_config_cases`(YAML/JSON, `{cases:[{tool,args?,expect:allow|deny,gate?,name?}]}` 또는 최상위 리스트; PyYAML 없으면 JSON fallback; 빈 목록 허용) · `run_config_tests(resolved_cfg, cases) -> (rows, all_ok, skipped)`(해석된 config로 `build_guardrail` 한 번 → 케이스마다 `check_before_tool_call`("test-config", tool, args), `.block`/`.gate` 대조; `build_guardrail`이 오타 블록을 SKIP하면 그 경고를 `skipped`로 반환 = 부분 config 경고) · `render_config_test_table` · `cmd_test_config_common`(exit 1 = 불일치/잘못된 파일/config 빌드 실패, exit 0 = 전부 통과) 추가. claude는 `claude_code_hook.load_config(<config dir>)`로 해석, opencode는 sibling `agent-evaluator.config.json`을 그대로(없으면 `{}` = LiveGuardrail 기본값). `--global`·`--json`. 순수 조회라 guardrail 인스턴스 재사용해도 케이스 간 상태 안 샘. `check_before_tool_call` 무수정 — 차단/채점 로직 불변. 테스트 `test_spec043_guardrail_config_test.py` 24건, 0 new ruff/mypy(1038/204).
  - **REQ-2 ✅ (2026-09-09)**: 평가셋 버전 정합. `monitor._build_lineage()`가 `lineage.eval_set_hash`(정렬된 `(question, ground_truth)` 쌍의 SHA1[:16], 순서 무관·콘텐츠 안정) + `eval_set_size`를 자동 기록(git 실패 시처럼 예외는 조용히 빈 dict). `insights._eval_set_delta_section(current, baseline)` — baseline 있고 양쪽 `eval_set_hash`가 다를 때만: 공통 task_id에 대한 Oaxaca 스타일 분해로 TCR 이동을 `attributable_to_agent_pp`(공통셋에서 baseline→current 이동) + `attributable_to_eval_set_change_pp`(나머지 = added/removed 케이스 효과)로 쪼갬. 재실행 없음 — baseline 결과 JSON의 per-task pass/fail(`_effective_fail`)만 재집계. 공통 task_id 0건이면 `attributable=false` + 케이스 수 diff만. `build_insights` full 모드에만 배선(baseline 필요). `regression_attribution`가 `eval_set_delta`를 받아 `eval_set_changed` 플래그 + note 한 줄(±1pp 이상일 때) 추가. schema `eval_set_delta` 객체 + `regression_attribution.eval_set_changed`. 리포트 `_build_eval_set_delta`("Eval-Set Change Attribution") + `_TOC_LABELS`. 테스트 `test_spec043_eval_set_delta.py` 13건, 0 new ruff/mypy(1038/204).
  - **REQ-3 ✅ (2026-09-09)**: 배포 결정 원장. `agent_evaluator/rca/decision_ledger.py` 신설 — `record_gate_decision()`(gate 실행 항목: exit_code/verdict_level/decision_ready/gate_scores) · `record_decision_outcome(outcome, decided_by, rationale, gate_run_id=)`(사람 판정, 미결 gate_run 중 최신에 링크; `VALID_OUTCOMES = accepted|held|overridden|rejected`) · `load_decisions` · `summarize_decisions`(`{n_gate_runs, n_pending, pending[], by_outcome, last{gate_run, outcome|None}}`). append-only JSONL, `recommendation_tracking.py` 패턴. `agent-eval gate --decision-log PATH`가 실행마다 append(exit code 무관). `agent-eval decisions {list [--pending] [--json], record --outcome --by --rationale --gate-run-id}`(신규 서브커맨드 `cli/decisions.py`). `insights.deploy_decision`(`build_insights(decision_log_path=)`) — 마지막 gate run + 사람 outcome + `n_pending`. schema + 리포트 `_build_deploy_decision`("Deploy Decisions") + `_TOC_LABELS`. 테스트 `test_spec043_decision_ledger.py` 18건, ruff 1038(−1)·mypy 204.
  - **REQ-1 ✅ (2026-09-09)**: `insights.spec_coverage` — `insights._spec_coverage_section(tasks, requirements=None)`. 골든 케이스가 `extra.covers: [req_id]`로 자기가 재는 요구사항 선언. universe = `--requirements PATH`(평문 `ID: desc`) 있으면 그 목록(→ `uncovered` 계산), 없으면 `covers` 합집합(covers_only 모드, `uncovered=[]`). `{source, requirements, covered, uncovered, n_*, by_requirement, note}`. `build_insights(requirements=)` kwarg, full+partial 모드 배선. `create_taskresult(covers=[...])` → `extra["covers"]`. `agent-eval gate --requirements PATH --require-spec-coverage` → uncovered 있으면 **exit 4**(케이스 회귀와 같은 코드). `insights.schema.json` + 리포트 `_build_spec_coverage`("Requirement Coverage") + `_TOC_LABELS`. **게이트 점수 아님** — `verdict.level` 불변(테스트). 테스트 `test_spec043_spec_coverage.py` 13건 · 0 new ruff/mypy. (구현 중 `git stash` 실험으로 4개 파일 변경이 stash에 갇혔다가 `git checkout stash@{i} -- <file>`로 복구 — SPEC-042 변경 포함 전부 무손실.)
- **의존성**: SPEC-041 완료(`build_insights()` / `insights.*`) · SPEC-042 완료(`acceptance_criteria` · `decision_ready` · `improve` 폐루프) · SPEC-019/028(LiveGuardrail · AC/AOO 훅) · P15(`dataset promote`) · P43(`target set`)
- **검증 기준일**: 2026-09-09. 아래 Context의 `파일:라인`·"없음" 판정은 이 날짜에 코드를 직접 대조해 확인했다.

---

## 0. 선행 갭 분석의 재검증 (정확성 · 효과성 · 방법론 정합)

이 스펙에 앞서 제시한 "빠진 요소 7선"을 코드와 재대조하고, Harness 6원칙 및 "AI Agent 평가툴" 관점과의 정합을 확인했다. REQ는 **재검증된 사실**과 **정합 판정**을 기준으로 좁혔다.

| # | 선행 분석 주장 | 재검증 | 정합 판정 → 이번 스펙에서의 처리 |
|---|---|---|---|
| A-1 | 요구사항 산출물 원시타입 없음, 요구사항↔골든 커버리지 없음, `acceptance_criteria`는 표시 전용 | **정확.** `_capability_coverage`(`insights.py:2546`)는 `task_type × difficulty × tool-use × question-length` 셀 커버리지이지 *선언된 요구사항* 대비가 아님. `acceptance_criteria`(SPEC-042 REQ-1)는 `_acceptance_coverage_section`에서 키워드 매칭 표시만, 골든 케이스 링크 없음 | 원칙 1과 **부분 정합**. 방법론은 "스펙은 사람의 결정"이라 도구가 스펙을 *소유·생성*하면 misaligned. → **REQ-1: 링크 + 커버리지 flag/gate만**(요구사항 레지스트리·EARS 파서·케이스 생성은 Non-Goal) |
| A-2 | 프롬프트/Config가 lineage 태그일 뿐 관리 객체 아님 | **부분 과장.** `compare_results(group_by="prompt_version")`·`gate --baseline-version <prompt-tag>`·`improve patch`(프롬프트 파일 anchor-diff)가 이미 존재. 진짜 갭은 "프롬프트 변경 ↔ Gate 이동 귀속"뿐 | 독립 REQ 부적절 → **REQ-2(평가셋 버전관리)에 흡수** — 같은 "측정 기반의 버전 정합" 문제 |
| A-3 | 평가셋이 자체 changelog·영향 분석을 가진 1급 객체가 아님, 케이스 추가 시 baseline 조용히 이동 | **정확.** `dataset.version`(`monitor.py:2498`)은 "최근 로드된 골든셋 이름" OTEL 속성뿐. 평가셋 해시·변경↔점수 귀속 없음 | 원칙 2("증명"은 안정된 측정 기반 필요)와 **정합** → **REQ-2** |
| B-1 | 추천→적용→재검증을 에이전트가 구동하는 `improve run` 없음 | **부분 과장.** `improve patch`(diff 방출, `cli/improve.py:517` "never applies") + `improve verify`(before/after 채점) 사이가 수동. 하지만 이건 *새 능력*이 아니라 apply-patch + eval + verify를 잇는 **편의 래퍼**. 완전 자율 apply-and-deploy는 원칙 6과 misaligned | 축소 → **REQ-7(편의 래퍼, 격리 worktree, 절대 머지 안 함)**, 낮은 우선순위 |
| B-2 | 프로덕션 실패/저확신 → 평가셋 자동 편입 파이프라인 없음 | **정확(자동 트리거 한정).** 프리미티브는 있음(`dataset build --source`·`dataset promote`·스트리밍·`review_queue`). 없는 건 "이상/저확신 이벤트가 골든 후보 + 리뷰 태스크를 자동 생성" | 원칙 2/4와 **정합**, 사람 리뷰 게이트 유지 시 원칙 6도 유지 → **REQ-4** |
| B-3 | Gate C를 채점만 하고 결함을 *유발*하지 않음, 샌드박스 없음 | **정확.** `fault_injection`/`FaultInjection` 0건. `FaultToleranceConfig`/`GracefulDegradationConfig`는 데이터에 있으면 채점만 | 원칙 3과 **정합**(채점 enrichment, 차단 무관). 전면 샌드박스(E2B/Firecracker)·계약 테스트(Pact)는 도서 F.6이 그은 경계 → **REQ-5: 얇은 확률적 데코레이터만** |
| C-1 | 배포 결정 원장 없음(누가·무슨 근거로 hold/deploy/override 했는지) | **정확.** `decision_log`/`deploy_decision`/`gate_decision` 0건. `recommendation_outcomes.jsonl`는 *조치* 판정만. SPEC-042 REQ-2가 `hold` 상태는 만들었으나 *결정 기록*은 없음 | 원칙 6(거버넌스) + 도서 §13(규제)와 **강하게 정합** → **REQ-3** |
| C-2 | `improvement_priors`가 프로젝트 격리, org 레벨 교차 에이전트 뷰 없음, 리뷰어 불일치가 선호 데이터셋 아님 | **정확.** 단 (a) org 레지스트리는 큰 아키텍처(멀티 프로젝트) — 이번 스펙 밖. (b) 리뷰어 불일치 export는 작은 *출력* (`n_disagreements`·`judge_disagreement` 필터가 이미 신호를 가짐, `insights.py:1220`) | (a) → **Non-Goal(별도 후속)**. (b) → **REQ-6(신호 방출만, 학습은 팀 몫)** |
| (신규) | guardrail_config를 케이스 파일로 assert하는 TDD가 없음 | `{claude,opencode} doctor`는 *고정* 시나리오(무해→allow, `rm -rf`→deny, WebFetch→deny)만. 프로젝트가 자기 금지 명령·정상 명령 목록으로 config 판정을 assert하는 수단 없음 | 원칙 2(TDD-AI)·3(가드레일 자체의 red-green)과 **정합** → **REQ-6b → REQ-6 승격, "guardrail_config_test"** |

**요약:** 7선 중 **정확·정합 5건**(A-1축소·A-3·B-2·B-3·C-1), **축소 2건**(B-1→래퍼·A-2→REQ-2 흡수), **분할 1건**(C-2 → 소출력 채택·org는 Non-Goal), **신규 1건**(guardrail_config_test). SPEC-042 때와 같은 패턴 — 방향은 맞았으나 B-1·A-2가 과대평가됐다.

### 방법론·평가툴 관점 정합 종합

| 원칙 / 관점 | 이번 스펙이 강화 | 반대로 이 원칙이 *제약*하는 것 |
|---|---|---|
| 1. 코드보다 결정이 먼저 | REQ-1(요구사항 커버리지 gate) | 도구가 스펙을 소유·생성 금지 → REQ-1은 링크·flag만 |
| 2. 통과보다 증명 | REQ-2(평가셋 버전 정합), REQ-4(회귀 코퍼스 성장), REQ-6(가드레일 TDD) | — |
| 3. 차단과 채점 분리 | REQ-5(Gate C 채점 enrichment), REQ-6(가드레일 config를 별도로 검증) | REQ-5는 *차단* 로직 무수정 |
| 4. 이미 있는 걸 다시 만들지 않는다 | REQ-4(기존 `dataset` 프리미티브에 배선), REQ-7(새 능력 대신 래퍼) | B-1을 독립 능력으로 만들지 않는 이유 |
| 5. 모델 크기 ↔ 작업 성격 | (SPEC-042 REQ-8이 커버 — 이번 스펙은 원칙 5 직접 대상 아님) | — |
| 6. 사람의 최종 책임 | REQ-3(결정 원장), REQ-4(리뷰 게이트 유지), REQ-7(절대 머지 안 함) | 자율 apply-and-deploy 금지 |
| 평가툴: 구성 타당도 | REQ-1(요구사항 대비 측정) | — |
| 평가툴: 재현성 | REQ-2(어느 평가셋 버전으로 낸 점수인가) | — |
| 평가툴: 폐루프 학습 | REQ-4, REQ-6(disagreement 신호) | 학습/RLHF 플랫폼화 금지 → REQ-6은 export만 |

---

## 1. Goals

인사이트 계층(SPEC-041, ~63키)이 "리포트가 무엇을 말하는가"를 완성했다면, 이번 스펙은 그 말이 **① 올바른 입력(요구사항·평가셋)에 근거하는가**, **② 사람 개입을 최소화하며 코드·평가셋으로 되먹여지는가**, **③ 결정이 기록으로 남는가**를 채운다. 전부 **기존 프리미티브에 배선**하고 **새 채점 공식은 도입하지 않는다**.

## 2. Non-Goals

- **도구가 스펙을 소유·생성** — 요구사항 레지스트리, EARS/Gherkin 파서, 요구사항→케이스 자동 생성. (원칙 1: 스펙은 사람의 결정.)
- **자율 apply-and-deploy** — REQ-7은 격리 worktree에서 apply→eval→verify까지만, **절대 머지하지 않는다**. (원칙 6.)
- **학습·라벨링·RLHF 플랫폼** — REQ-6은 선호 신호를 JSONL로 *방출*만 한다. 리워드 모델·파인튜닝은 팀 몫.
- **전면 샌드박스 / 계약 테스트** — E2B·Firecracker·Pact는 도서 부록 F.6이 그은 경계. REQ-5는 얇은 확률적 도구 래퍼만.
- **org 레벨 교차 에이전트 지식 레지스트리** (선행 분석 C-2a) — 멀티 프로젝트 아키텍처라 별도 후속 스펙.
- **새 Gate 채점 공식** — 전 REQ가 기존 verdict/insight를 재구성하거나 새 산출물(로그·JSONL)을 낼 뿐.

## 3. Requirements

### REQ-1 — `spec_coverage`: 선언된 요구사항 ↔ 골든 케이스 커버리지 (원칙 1)

- **Context**: `acceptance_criteria`(SPEC-042 REQ-1)는 태스크에 붙는 표시 전용 문자열. `_capability_coverage`는 요구사항이 아니라 셀(타입·난이도) 커버리지. "각 요구사항을 실제로 재는 골든 케이스가 있는가"를 아무것도 확인하지 않는다.
- **변경**:
  - 골든 케이스에 optional `covers: list[str]`(요구사항 ID) 필드. `docs/GATE_MAP.md`류를 파싱하지 않고, **케이스가 자기가 어느 요구사항을 재는지** 선언한다.
  - `insights.spec_coverage` 신설 — `{requirements[], covered[], uncovered[], by_requirement{req_id: [case_ids]}}`. 요구사항 목록의 소스: (a) 태스크들의 `extra.acceptance_criteria` 합집합, 또는 (b) optional `--requirements PATH`(한 줄당 `REQ-ID: 서술`인 평문).
  - `agent-eval gate --require-spec-coverage` → 커버되지 않은 요구사항이 있으면 **exit 4**(케이스 회귀와 같은 코드 — 둘 다 "평가셋 결함"). `--require-spec-coverage-strict`면 전용 exit.
- **Acceptance**: `covers` 없는 골든셋은 `spec_coverage == null`, 게이트 동작 불변. 요구사항 3개 중 1개만 커버하는 골든셋에서 `uncovered == [REQ-X]`, `--require-spec-coverage` → exit 4.
- **Non-Goal 재확인**: EARS 문법 검증·요구사항에서 케이스 *생성*은 하지 않는다.
- **규모**: 중.

### REQ-2 ✅ — 평가셋 버전 정합: 해시 lineage + 변경↔점수 귀속 (원칙 2)

- **Context**: `dataset.version`은 OTEL 속성(골든셋 이름)뿐. baseline과 현재의 평가셋이 다른데 점수가 움직이면 "에이전트가 나빠진 것"과 "평가셋이 어려워진 것"이 구분되지 않는다.
- **변경**:
  - `PerformanceMonitor(dataset_ref=)`(이미 존재, P28)에 더해 lineage에 `eval_set_hash`(태스크 `question`+`ground_truth` 정렬 SHA1)와 `eval_set_size`를 자동 기록.
  - `insights.eval_set_delta`(baseline 있고 `eval_set_hash`가 다를 때만) — `{added_cases, removed_cases, tcr_movement_pp, attributable_to_eval_set_change_pp, attributable_to_agent_pp}`. 귀속 방식: baseline 에이전트를 **공통 케이스에만** 재채점한 값과 전체 값의 차 = 평가셋 기여분. (재실행 불필요 — baseline 결과 JSON의 per-task 점수에서 공통 케이스만 골라 재집계.)
  - HTML 리포트 회귀 섹션 + `regression_attribution`에 "이 회귀의 Xpp는 평가셋 변경분" 한 줄.
- **Acceptance**: 같은 평가셋(해시 동일)이면 `eval_set_delta == null`. baseline 대비 케이스 5건 추가·그게 더 어려운 경우 `attributable_to_eval_set_change_pp`가 음수로 잡히고 `attributable_to_agent_pp`가 회귀의 나머지.
- **규모**: 중.

### REQ-3 — 배포 결정 원장 (원칙 6, 도서 §13)

- **Context**: `gate`가 exit 0/75/1~4를 내면 그걸로 끝. 사람이 exit 75를 수용/오버라이드/보류한 *결정*, 그 근거, 결정자, 시점을 남기는 곳이 없다. `recommendation_outcomes.jsonl`은 조치 판정만.
- **변경**:
  - `agent-eval gate --decision-log PATH` — 게이트 실행마다 `{ts, result_file, agent_version, exit_code, verdict_level, decision_ready, undecided_reason?, gate_scores}`를 append-only JSONL로.
  - `agent-eval decisions record <log> --outcome {accepted|held|overridden|rejected} --by <name> --rationale "..."` — 사람의 판정을 같은 로그에 후속 append(직전 미결 항목에 링크).
  - `agent-eval decisions list <log> [--pending]` — 원장 조회. `--pending`은 exit 75인데 아직 `outcome`이 없는 항목.
  - `insights.deploy_decision`(로그 경로 주어지면) — 이 결과에 대한 마지막 결정 + "미결" 여부.
- **Acceptance**: `--decision-log` 없으면 동작·출력 불변. exit 75 실행 → 로그에 `outcome` 없는 항목 → `decisions list --pending`에 등장 → `decisions record --outcome overridden` 후 사라짐.
- **규모**: 중. `rca/recommendation_tracking.py`의 append-only JSONL 패턴 재사용.

### REQ-4 ✅ — 프로덕션 이상/저확신 → 골든 후보 자동 편입 (원칙 2·4)

- **Context**: 프리미티브(`dataset build --source`·`dataset promote`·스트리밍·`AnomalyDetector`·`review_queue`)는 다 있으나 자동 트리거가 없다. 사람이 주기적으로 `dataset build`를 돌려야 프로덕션 실패가 골든셋에 들어간다.
- **변경**:
  - `StreamingEvaluator`/`AgentEvalMiddleware`에 optional `golden_candidate_sink=` — `AnomalyEvent` 발생 또는 `extra.confidence < threshold`(옵트인)인 태스크를 `golden_candidates.jsonl`에 후보로 append(`{question, response, timestamp, trigger, reviewed: false}`).
  - `agent-eval dataset review-candidates <jsonl>` — 미검토 후보를 하나씩 accept(→ 골든셋 편입, 라벨은 사람이) / reject(→ `reviewed: true, kept: false`) / defer.
  - `insights.golden_health`(P58)에 "검토 대기 프로덕션 후보 N건" 한 줄.
- **Acceptance**: `golden_candidate_sink` 미설정 시 스트리밍 동작 불변. 이상 이벤트 1건 → `golden_candidates.jsonl`에 `reviewed: false` 1행 → `review-candidates`에서 accept → 골든셋에 케이스 추가, 후보는 `reviewed: true`.
- **규모**: 중. 새 판정 로직 없음 — 기존 `dataset promote`가 종착.

### REQ-5 ✅ — 얇은 결함 주입 하네스 (원칙 3 — Gate C 채점 enrichment)

- **Context**: Gate C(`FaultToleranceConfig`/`GracefulDegradationConfig`)는 데이터에 결함 상황이 있으면 채점한다. 그 상황을 *만드는* 수단이 없다. 전면 샌드박스는 도서 경계 밖.
- **변경**:
  - `FaultInjectionConfig(tool_failure_rate=0.0, added_latency_ms=0, latency_jitter_ms=0, fail_tools=None, seed=None)` — `@agent_eval(fault_injection=...)` 또는 `tool_guard(fault_injection=...)`에 전달.
  - 데코레이터가 도구 호출을 감싸 `seed` 고정 RNG로 확률적으로 (a) 예외 주입(`fail_tools`에 있거나 무작위) 또는 (b) `time.sleep(added_latency_ms ± jitter)`. **차단(`check_before_tool_call`) 로직은 건드리지 않는다.**
  - 결과는 기존 경로 그대로 흘러 Gate C·D 채점에 반영. `lineage.fault_injection`에 설정을 기록(재현).
- **Acceptance**: `fault_injection=None`(기본)이면 데코레이터 동작 100% 불변. `tool_failure_rate=0.3, seed=1`이면 같은 시드로 두 번 돌린 실패 패턴이 동일. 주입된 실패가 `RetryCorrectionTracker`·Gate C에 나타난다.
- **Non-Goal**: 네트워크/파일시스템/프로세스 격리, syscall 후킹 — 전부 별도 도구.
- **규모**: 중.

### REQ-6 — `guardrail_config` 케이스 기반 검증 (원칙 2·3 — 가드레일의 TDD) + 선호 신호 export

**6a. guardrail_config test** ✅ (2026-09-09)
- **Context**: `{claude,opencode} doctor`의 라이브 검사는 *고정* 시나리오(`rm -rf`→deny 등)뿐. 프로젝트가 자기 `runtime.json`이 "환불 명령은 막고, 정상 셸은 통과"하는지 assert할 수단이 없다.
- **변경**: `agent-eval {claude,opencode} test-config <cases.yaml>` — `cases: [{tool, args, expect: allow|deny, gate?}]`를 해석된 config로 `check_before_tool_call`에 태워 기대와 대조. 불일치 시 exit 1 + 표. CI 스텝으로 둔다.
- **Acceptance**: 빈 케이스 파일 → exit 0. `{tool: Bash, args: {command: "refund --user 42"}, expect: deny}`가 config의 `forbidden_tools`와 맞으면 pass, config에서 그 항목을 빼면 fail.

**6b. 선호 신호 export** ✅ (2026-09-09)
- **Context**: `judge_pairwise`·`ImplicitFeedbackTracker`·transparency annotation·`review_queue`가 "사람 A vs 에이전트" 또는 "리뷰어 A vs B" 선호를 이미 담지만, 이를 데이터셋으로 꺼내는 출구가 없다.
- **변경**: `agent-eval feedback export-preferences <results_dir> --out prefs.jsonl` — `{question, response_a, response_b, preferred: "a"|"b"|"tie", source: pairwise_judge|annotation|review_queue, annotator?}` JSONL. **export만** — 학습은 하지 않는다.
- **Acceptance**: pairwise judge 결과 3건 + annotation 2건이 있는 디렉토리 → 5행 JSONL. 소스별 `source` 태그.

- **규모**: 6a 소, 6b 소.

### REQ-7 ✅ — `improve apply-verify`: 편의 래퍼 (DX; 원칙 4·6)

- **Context**: `improve patch`(diff 방출) → 사람이 `git apply` → 평가 재실행 → `improve verify`. 3~4단계가 수동. 새 능력이 아니라 배선.
- **변경**: `agent-eval improve apply-verify <baseline_result.json> --proposal <id> --eval-cmd "<셸>" [--worktree]` —
  1. `improve patch`의 해당 diff를 **격리 git worktree**(`--worktree`, 기본 임시)에 apply.
  2. `--eval-cmd`를 그 worktree에서 실행(결과 JSON을 뱉는다고 가정).
  3. `improve verify <새 결과> --baseline <baseline> --persist`.
  4. `{confirmed|refuted|inconclusive}` + worktree 경로를 출력. **머지·커밋은 절대 안 한다** — 사람이 worktree를 보고 결정.
- **Acceptance**: proposal이 없으면 즉시 exit 1. worktree는 항상 별도 경로(원본 트리 무수정). `--persist` 없이는 `recommendation_outcomes.jsonl` 미변경.
- **규모**: 소~중.

## 4. Interface 변경 요약 (전부 하위호환)

| 대상 | 추가 | 기본값에서의 동작 |
|---|---|---|
| 골든 케이스 스키마 | `covers: list[str]` (optional) | 없으면 `spec_coverage == null` |
| `insights` | `spec_coverage` · `eval_set_delta` · `deploy_decision` | 조건부 — 입력 없으면 `null` |
| `agent-eval gate` | `--require-spec-coverage` · `--decision-log PATH` | 미지정 → exit code·출력 불변 |
| `agent-eval decisions` | 신규 서브커맨드 (`record` · `list`) | — |
| `agent-eval dataset` | `review-candidates` 서브커맨드 | — |
| `agent-eval {claude,opencode}` | `test-config <cases.yaml>` 서브커맨드 | — |
| `agent-eval feedback` | `export-preferences` 서브커맨드 | — |
| `agent-eval improve` | `apply-verify` 서브커맨드 | — |
| `PerformanceMonitor` lineage | `eval_set_hash` · `eval_set_size` 자동 | 추가 필드만 |
| `@agent_eval` / `tool_guard` | `fault_injection: FaultInjectionConfig \| None = None` | `None` → 완전 불변 |
| `StreamingEvaluator` / `AgentEvalMiddleware` | `golden_candidate_sink` | `None` → 불변 |
| `insights.schema.json` | `spec_coverage` · `eval_set_delta` · `deploy_decision` 정의 | `additionalProperties:true`라 non-breaking, 그래도 명시 |

## 5. Compatibility

- 전 REQ 옵트인. 기본값에서 기존 테스트 스위트(5039)·공개 API·결과 JSON 바이트 동일성 유지가 각 REQ Acceptance.
- `schema_version`은 필드 *추가*만 → minor로 충분(현재 `"1.1"`).
- REQ-5(`fault_injection`)는 `@agent_eval` 시그니처에 kwarg 1개 추가 — SPEC-039의 `_UNSET` sentinel 병합 규약과 충돌 없음(신규 kwarg는 항상 명시 전달).

## 6. Rollout (권장 순서)

방법론 정합·레버리지 기준: **REQ-1 → REQ-3 → REQ-2 → REQ-6a → REQ-4 → REQ-5 → REQ-6b → REQ-7**

1. **묶음 1 (원칙 1·6 직결, 저~중비용):** REQ-1(spec coverage), REQ-3(decision ledger). 각각 `gate` exit code 1개 + insight 섹션 1개 + append-only JSONL. SPEC-041 §"Adding an insight section" 5단계 준수.
2. **묶음 2 (증명의 측정 기반):** REQ-2(eval-set delta) — 재실행 없이 baseline per-task 점수 재집계로 귀속. 회귀 리포트·`regression_attribution`에 배선.
3. **묶음 3 (자동화·wiring):** REQ-6a(guardrail test — `doctor` 인프라 재사용), REQ-4(prod→golden — `dataset promote` 종착 재사용).
4. **묶음 4 (채점 enrichment):** REQ-5(fault injection) — `tool_guard` 래핑 지점에 결정적 RNG.
5. **묶음 5 (소출력·DX):** REQ-6b(preference export), REQ-7(apply-verify 래퍼).

각 묶음: `pytest` 전체 통과 + `ruff`/`mypy` 신규 0(SPEC-021 래칫) + 결과 JSON 바이트 동일성(옵트인 미사용 시).

## 7. Risks

| 시나리오 | 완화 |
|---|---|
| REQ-1이 "요구사항 산출물을 도구가 강제"로 확대 해석 | Non-Goal에 명시 + `covers`는 케이스가 *선언*, 파서 없음 |
| REQ-2 귀속이 baseline 결과 JSON에 per-task 점수가 없으면 계산 불가 | 그 경우 `eval_set_delta.attribution == null`, 케이스 수 diff만 보고 |
| REQ-3 원장이 방치돼 exit 75 항목이 영원히 pending | `decisions list --pending`을 CI 리포트에 노출, `--decision-log` 자체가 옵트인 |
| REQ-4 자동 후보가 노이즈로 골든셋 오염 | `golden_candidates.jsonl`은 `reviewed:false` 대기열일 뿐, 골든셋 편입은 `review-candidates` accept(사람) |
| REQ-5 결함 주입이 프로덕션 코드 경로에 샘 | 데코레이터 레벨, `fault_injection=None` 기본, `lineage`에 기록돼 "이 결과는 주입된 것"이 명시 |
| REQ-7 worktree가 정리 안 됨 / 원본 트리 오염 | 항상 임시 별도 경로, 머지·커밋 금지, 종료 시 worktree 경로만 출력(사람이 정리) |

---

## 부록: 원칙 ↔ REQ 매핑

| Harness 원칙 | 강화하는 REQ | 평가툴 관점 속성 |
|---|---|---|
| 1. 코드보다 결정이 먼저 | REQ-1 | 구성 타당도 — 선언된 요구사항 대비 측정 |
| 2. 통과보다 증명 | REQ-2, REQ-4, REQ-6a | 재현성(어느 평가셋 버전) + 폐루프 학습(회귀 코퍼스 성장) + 가드레일 자체의 TDD |
| 3. 차단과 채점 분리 | REQ-5, REQ-6a | 채점 enrichment(결함 유발) — 차단 로직 무수정 |
| 4. 이미 있는 걸 다시 만들지 않는다 | REQ-4, REQ-7 | 기존 `dataset`/`improve` 프리미티브에 배선 |
| 6. 사람의 최종 책임 | REQ-3, REQ-4, REQ-7 | 결정 준비도 — 결정을 기록으로; 자율 배포 금지 |
| 평가툴: 폐루프 학습 | REQ-6b | 선호 신호 방출(학습은 팀 몫) |
