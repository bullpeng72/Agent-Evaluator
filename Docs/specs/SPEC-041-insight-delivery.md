# SPEC-041: World-Class Insight & Information Delivery

> **Status:** Implemented (P1–P42 + P35 audit rounds 1–3), 2026-08.
> **Scope:** the machine-readable `extra_metrics.insights` layer (`reporting/insights.py::build_insights()`),
> its report / dashboard / CLI / MCP surfaces, and the phase-by-phase implementation history.
> Split out of `CLAUDE.md`, which keeps only the working contract (see the
> *"`extra_metrics.insights` — working contract"* subsection there).

**Guiding principle:** every phase *re-shapes* existing verdicts (`rca.diagnose()`, `utils.confidence`,
`ontology.metric_registry`, the `gates/*` aggregates, `rca.recommendation_tracking`/`verify`) into a
JSON-serializable object. No new scoring formulas. `build_insights()` never raises — a section that
fails to compute is omitted or `null`. New/changed sections must stay valid against
`agent_evaluator/schemas/insights.schema.json` (Draft 2020-12; every object `additionalProperties:true`;
nullable sections typed `["object"|"array","null"]`) and `tests/test_insights_schema.py`.

**Consumers:** `monitor.save_to_file()` attaches it as `extra_metrics.insights`;
`serve/routers/diagnose.py` returns it as `result["insights"]` (dashboard Improve tab);
`cli/gate.py` (`--digest` / `--fail-on-case-regression` / `--max-review-high` / `--notify`);
the static HTML report renders the same content with its own `_build_*` helpers (content parity).

Hooks: `build_insights(narrator=Callable[[dict], str])` swaps the deterministic `narrative` for
LLM text (template fallback); `build_insights(fixer=Callable[[payload], dict|None])` swaps the
deterministic `recommendations[].proposal` (P36). Neither is auto-applied.

---

## `build_insights()` output — key-by-key

**`extra_metrics.insights`** (SPEC-041 P9) — 머신 판독 인사이트 계층(L5/L6). `reporting/insights.py::build_insights()`가
`rca.diagnose()`·`utils.confidence`·`ontology.metric_registry`·`rca.recommendation_tracking`/`verify`의 출력을
JSON 직렬화 가능한 한 객체로 재구성한다(새 판정 로직 없음, 절대 raise 안 함 — 실패 섹션은 비거나 생략).
`monitor.save_to_file()`가 저장 시 자동 첨부(baseline 없는 absolute 모드, output_dir의
`recommendation_outcomes.jsonl` 자동 픽업), `serve/routers/diagnose.py`의 `/api/diagnose/{id}`도
`result["insights"]`로 반환(대시보드 Improve 탭이 소비). 스키마:
`{schema_version, detection_mode, verdict{level: not_ready|caution|ready|unknown, headline, failing_gates,
warning_gates, confidence, confidence_reasons, next_actions[]},
readiness{target_gate_score(=0.7), current_tcr_pct, current_accuracy_pct, gaps[]{gate, gate_name, score,
target, gap, blocking, projected_score_after_plan?, estimate?}, fix_plan[]{rank, signature, task_type, count,
impact_pct, example_task_ids, effort_hint, targets_gates[], projected_tcr_after_pct, projected_accuracy_after_pct,
cumulative_tcr_gain_pp}, projected_ready_after{ready_after_n_items, remaining_structural_blockers[], note}}|null
(SPEC-041 P29 — "green까지의 경로": 게이트별 pass 라인(0.7)까지의 정량 갭 + 실패군집을 TCR 영향 순으로
정렬한 수정 계획 + 결정적 투영. 실패/경고 게이트도 실패군집도 없으면 null),
metric_confidence{n_tasks, tcr_pct, tcr_ci_pct,
accuracy_pct, accuracy_ci_pct}, gate_findings[]{gate, score, component_shortfalls[]{field, value, health,
guidance, config_hint}, top_detail_deltas[]}, failure_clusters[]{signature, task_type, count, impact_pct,
example_task_ids},
failure_segments[]{label, keywords[], task_ids[], n, share_of_failures_pct, impact_pct, dominant_reason,
example_question}|null (SPEC-041 P30 — 실패 *질문*을 어휘 토픽으로 군집화, binary TF-IDF + greedy cosine,
stdlib. `(reason×type)` 군집이 못 잡는 "특정 입력 패턴"),
failure_triggers[]{task_id, kind(retrieval_gap|grounding|tool_failure|runtime_error), detail}|null
(SPEC-041 P30 — worst-N 실패를 유발한 검색 청크/도구 스텝에 국소화),
failure_lineage{regressed, persistent, new, fixed}|null, recommendations[]{gate, status,
label, guidance, shortfalls[], code_snippet, experiment{predicted_gate_delta, recommended_tasks, command}|null,
past_outcomes{confirmed, refuted, avg_delta}|null, baseline_verdict{verdict, delta}|null},
latency_budget{n_tasks, tool_ms, model_ms, network_ms, unattributed_ms, *_ratio, bottleneck, bottleneck_share}|null
(SPEC-041 P7 — eval_latency_attribution의 per-task span 분해를 평균낸 것, 모달 bottleneck),
rag_localization{n_rag_tasks, by_class, dominant_failure, remediation_by_class, unsupported_claim_examples}|null
(SPEC-041 P11 — RAG 실패를 retrieval/grounding/generation으로 분류),
slice_analysis[]{task_type, n, tcr_pct, tcr_ci_pct, accuracy_pct, baseline_tcr_pct?, tcr_delta_pp?,
tcr_delta_ci_pp?, significant?} (SPEC-041 P10 — per-task_type CI, baseline 있으면 두-표본 부트스트랩 유의성),
eval_set_quality{n_tasks, task_type_histogram, near_duplicate_clusters[]{question, task_ids, count},
coverage_warnings[], suspicious_ground_truth[]{task_id, reason}}|null (SPEC-041 P12 — 평가셋 커버리지·균형·
근접중복·Gate 미실행 경고·baseline 대비 동일 실패 라벨 의심),
evaluator_trust{judge_vs_heuristic{n_comparable, agreement_rate, mean_abs_diff, disagreements[]},
judge_calibration|null, judge_self_consistency|null, trust_level: high|medium|low, trust_reasons[]}|null
(SPEC-041 P14 — 평가기 신뢰도. trust_level=low/medium면 verdict.confidence를 같은 등급으로 강등),
review_queue{n_items, by_priority{high, medium, low}, items[]{task_id, priority, reasons[]}}|null
(SPEC-041 P15 — HITL 트리아지: judge↔휴리스틱 불일치·suspicious 라벨·회귀 실패·경계선 점수를 우선순위로),
cost_economics{total_cost_usd, cost_source, cost_per_task_usd, cost_per_successful_task_usd, wasted_cost_usd,
wasted_cost_pct, retry_cost_usd, retry_cost_pct, projection{calls, total_usd, wasted_usd}}|null
(SPEC-041 P16 — 성공 태스크당 비용·실패/재시도 낭비·10만 콜 투사. per-task 토큰×pricing, 없으면 집계 균등분할),
narrative: str (SPEC-041 P17 — 배포 준비도 판정 + 최약 병목 + 리뷰/신뢰도 + 비용 투사를 2~4문장 영어로.
`build_insights(narrator=<callable>)`로 LLM 작성 대체 가능, 실패 시 결정적 템플릿 폴백),
narrative_audit{claims_checked, clean, adjustments[]}|null (SPEC-041 P34 — narrative의 정량 주장을
구조화 숫자와 대조: verdict≠ready인데 "is deployment-ready" · TCR/accuracy와 >3pp 다른 % 인용 ·
baseline 없는데 "improvement/regression" · confidence=low인데 미언급. 결정적 템플릿은 항상 clean),
briefs{pm: str, qa: str, engineer: [str]}|null (SPEC-041 P34 — 같은 run을 3개 청중용으로 결정적 합성:
PM 한 줄(ship/hold + 노력 + 리스크 + confidence), QA 문단(review_queue + evaluator_trust + 최대
failure_segment + freshness 경고), engineer 체크리스트(critical 보안 먼저 + readiness.fix_plan 항목별
effort_hint + 코드 스니펫 안내). verdict unknown이고 failure_clusters도 없으면 null),
change_attribution{prompt_changed, prompt_diff{similarity, added[], removed[]}, config_changed,
config_diff{changed_keys}, git{from_commit, to_commit}, largest_gate_move{gate, delta}, note}|null
(SPEC-041 P18 — baseline 필요. 두 run의 lineage.prompt_text/config_snapshot diff + 최대 Gate 이동),
cohort_comparison{metric, n_versions, versions[]{label, n_tasks, tcr_pct, gate_scores, overall},
pairwise[]{a, b, delta_pp, p_value, p_value_fdr, significant_fdr, ci_pp}, by_task_type[]{task_type,
winner, scores}, winner{label, reason}|null}|null (SPEC-041 P22 — `build_insights(cohort=[dict,…])` 시.
N-버전 비교 + Benjamini-Hochberg FDR + 슬라이스별 승자 + "승자 지목"),
trace_diffs[]{task_id, question, compared[from,to], verdict(fixed|improved|regressed|declined|changed),
score_delta{completion, accuracy}, response_diff{similarity, added[], removed[]},
trajectory_diff{before[], after[], added[], removed[], reordered}, per_version[]{label, completion,
accuracy, success, response_excerpt}}|null (SPEC-041 P32 — cohort에 ≥2회 등장하고 결과/점수가 움직인
태스크의 응답 텍스트 diff(difflib) + 궤적 스텝 시퀀스 diff. current vs 첫 cohort 항목. cohort 없으면 null),
security_findings[]{task_id, tracker, threat_type, severity, cwe, detail}|null (SPEC-041 P19 — 5개 보안
트래커의 per-task 위협 상세, severity 순, CWE 매핑),
nondeterminism[]{task_id, reproducibility_score, run_count, variance, sample_responses[]}|null
(SPEC-041 P19 — Gate C 재현성 score<0.85 태스크 + 변형 응답 텍스트),
trajectories[]{task_id, source, n_spans, total_ms, critical_path[], bottleneck{name, self_ms},
total_cost_usd, total_tokens}|null (SPEC-041 P25 — worst-N 실패 태스크의 스텝 타임라인.
`parse_span_timeline()`이 타이밍 있는 스텝만 중첩 파싱, 없으면 null),
experiments[]{experiment_id, hypothesis, target_gate, target_field, predicted, actual, verdict, status,
note}|null (SPEC-041 P27 — `build_insights(experiments_log_path=)` 시 `.aoo/experiments.jsonl`의
등록 가설. baseline 있으면 open 가설을 score(predicted vs actual → confirmed/partially_confirmed/
refuted/inconclusive), 없으면 pending. resolved 가설은 저장된 verdict 그대로. 로그 없으면 null),
metadata_slices[]{dimension: "extra.<key>", slices[]{value, n, tcr_pct, tcr_ci_pct, accuracy_pct,
baseline_tcr_pct?, tcr_delta_pp?, significant?}}|null (SPEC-041 P28 — task의 스칼라 `extra` 메타데이터
(model/prompt_variant/difficulty…)로 자동 슬라이스. task_type과 1:1인 키는 제외. 태스크 <4개면 null),
sample_guidance{n_tasks, tcr_ci_halfwidth_pp, target_halfwidth_pp, recommended_n?, additional_tasks,
message}|null (SPEC-041 P28 — "TCR CI를 ±5pp로 좁히려면 태스크 몇 개 더". `required_n_for_halfwidth` 재사용),
reproducibility_manifest{model_name, model_params, judge_model, dataset_ref, evaluator_config,
evaluator_config_hash, dependency_versions}|null (SPEC-041 P28 — `lineage.reproducibility_manifest` 패스스루),
insight_changes{new_clusters[], resolved_clusters[], trust_change{from,to}|null, new_security_findings[],
verdict_change{from,to}|null, newly_failing_gates[], newly_passing_gates[]}|null (SPEC-041 P33 — baseline
필요. *인사이트*의 메타 diff: current vs baseline의 failure_clusters 시그니처·evaluator_trust.trust_level·
security_findings(task_id,threat_type)·verdict.level·fail 게이트 집합을 대조. 아무것도 안 움직였으면 null.
baseline 인사이트는 full build_insights 재실행 대신 필요한 하위섹션만 baseline로 직접 호출),
freshness{baseline_age_days, eval_set_identical_to_baseline, n_tasks, warnings[]}|null (SPEC-041 P33 —
신선도 신호: baseline timestamp 나이 >30일 · 질문셋 fingerprint가 baseline과 동일한데 새 실패모드 존재 ·
suspicious_ground_truth 있음 · n_tasks<20. warnings는 사람 읽는 문장 리스트),
longitudinal{n_runs, run_files[], recurring_failures[]{signature, in_n_runs, of_runs, flap_transitions,
currently_failing, kind(chronic|flapping|recurring), note}, eval_set_stability{n_runs_same_eval_set,
tcr_mean_pct, tcr_stdev_pp, detectable_change_pp, note}|null, cadence{n_intervals,
median_days_between_runs, last_gap_days}|null}|null (SPEC-041 P48 — history_dir의 형제 결과 JSON
≥4개를 가로질러: 계속 실패하는 시그니처 + 변하지 않은 평가셋의 run-to-run TCR 노이즈 밴드 + 실행 주기.
history_dir 없거나 <4 run이면 null),
shared_cause_explanations, newly_unmeasured_gates, experiment_metadata}`.
스키마 정본: **`agent_evaluator/schemas/insights.schema.json`**(Draft 2020-12, SPEC-041 P20) —
`build_insights()` 출력이 이 스키마를 위반하면 안 된다(전 object `additionalProperties:true`로 전방 호환,
nullable 섹션은 신호 없으면 null). `tests/test_insights_schema.py`가 여러 시나리오로 검증.
`harness_groups.schema.json`과 동일 계약 원칙. P20: `classify_rag_failure`가 임계값 근처면
`borderline:True` → `rag_localization.n_borderline`/`borderline_task_ids` + review_queue medium 항목. 정적 HTML 리포트는 여전히 자체
`_build_*` 헬퍼로 같은 내용을 렌더한다(콘텐츠 동등, `insights`는 머신 판독 채널).

---

## Phase history (P7–P42)

> Phases are listed in the order they were written to `CLAUDE.md` (roughly reverse-chronological
> for P22–P42, then the P35 audit rounds, then P36–P42). Each paragraph is the authoritative
> description of that phase's behaviour; the code is the ground truth.

**SPEC-041 P7 (궤적 가시성)** — `reporting/comprehensive_report.py`:
`_build_latency_budget(tasks, p95)`(Gate D 섹션) — "P95 4.0s"를 model/tool/network/unattributed 스택바 +
"Bottleneck: model" 한 줄로 분해. `insights.aggregate_latency_attribution()` 재사용.
`_build_trajectory(case)`(실패 케이스 표의 각 행에 `<details>`) — `tool_calls`→`chain_steps`→`agent_interactions`
순으로 step→tool→인자/출력 요약→✓/✗ + 스텝별 duration/토큰. 스텝 데이터 없는 태스크(순수 QA)는 "".
`_norm_task_for_case`가 tool_calls/chain_steps/agent_interactions도 담는다. `_build_gate_d`가 `tasks` 인자 추가.
P25: 스텝에 타이밍이 있으면 이 평면 표 위에 `_build_waterfall(items)`이 인라인 SVG 워터폴을 얹는다
(`parse_span_timeline` 재사용, critical-path 스팬 강조 + bottleneck 헤더). 타이밍 없으면 평면 표만.

**SPEC-041 P11 (RAG 국소화)** — `reporting/insights.py`: `classify_rag_failure(response, context, ground_truth,
accuracy, faithfulness)` — retrieved context 있는 태스크를 `retrieval_miss`(정답 정보가 애초에 검색 안 됨:
gt↔context 토큰 오버랩<0.40) / `grounding_miss`(검색됐는데 응답이 무시: unsupported 문장 비율>0.50 또는
faithfulness<0.6) / `generation_error`(검색·근거 OK인데 여전히 오답) / `ok`로 분류. 결정적, 의존성 없음
(공백 토큰화 + 소형 영어 stopword, ML 재실행 아님 — HOTL "후보 지침"). `rag_localization(tasks)`가 집계 →
`insights.rag_localization{n_rag_tasks, by_class, dominant_failure, remediation_by_class{retrieval→top_k/re-rank,
grounding→프롬프트/temperature, generation→few-shot/검증}, unsupported_claim_examples[]}`. 리포트:
`_build_rag_localization(tasks)`(실패 케이스 섹션 안), 대시보드 Improve 탭 패널.

**SPEC-041 P10 (통계 심도)** — `utils/confidence.py`: `mde_two_proportions(n_a, n_b, p_pooled)` — 주어진
표본에서 80% 검정력·α=0.05로 탐지 가능한 최소 효과 크기(정규근사). `bootstrap_diff_ci(a, b)` — 두 슬라이스
평균차의 백분위 부트스트랩 CI(0 포함 안 하면 유의). `cli/abtest.py::_print_mde()` — proportion형 지표
(양쪽 mean∈[0,1])에 "min detectable effect @ 80% power ±X — observed |delta| Y" 한 줄 + not significant인데
|delta|<MDE면 "underpowered, 동등성 증거 아님" 경고. `reporting/insights.py::_slice_analysis_section` +
`comprehensive_report.py::_build_slice_analysis` — task_type별 TCR/accuracy(+CI), baseline 있으면 per-slice
Δ + 유의성(*) 표. "헤더 지표는 한 코호트에 몰린 회귀를 숨긴다".

**SPEC-041 P12 (평가셋 품질)** — `reporting/insights.py::_eval_set_quality_section` +
`comprehensive_report.py::_build_eval_set_quality`: task_type 히스토그램 · 근접중복 질문(질문 토큰 Jaccard≥0.85
클러스터) · 커버리지 경고(Gate F가 점수 있는데 agent_interactions 태스크 0개 / Gate G tool_calls 0개 /
task_type 5:1 이상 불균형 / <20 태스크) · suspicious_ground_truth(baseline 필요 — 같은 task가 두 run 모두
acc<0.35에 |Δ|<0.05로 실패 → 라벨/질문 의심, gt 토큰<3이면 "very short" 힌트). 리포트 섹션
`eval-set-quality`, 대시보드 Improve 탭 패널.

**SPEC-041 P13 (종단 뷰)** — `reporting/history.py` + `comprehensive_report.py::_build_history_trend` /
`_build_change_ledger`: 단일 정적 리포트는 point-in-time이라 "Gate D가 3 run 연속 하락"을 못 말한다.
같은 디렉터리의 형제 결과 JSON을 훑어 per-Gate 인라인 SVG 스파크라인(`_spark_svg`) + first→last(slope) +
"↓ N runs in a row" 배지(consecutive_decline≥2), 그리고 recommendation_outcomes.jsonl을 "어느 변경이 어느
Gate를 움직였나" 표로. 리포트 섹션 `history-trend`·`change-ledger`(≥3 run일 때만). monitor 경로는
`monitor.output_dir`, rf 경로는 `Path(rf.path).parent`에서 디렉터리 도출.

**SPEC-041 P14 (평가기 신뢰도)** — `reporting/insights.py::_evaluator_trust_section` +
`comprehensive_report.py::_build_evaluator_reliability`: (a) **judge_vs_heuristic** — 태스크별
LLM judge `scores.overall`(/10 정규화)와 `AccuracyEvaluator` `accuracy_score`의 일치율·mean |Δ|·
불일치 태스크 목록 (|Δ|>0.40). (b) **judge_calibration** — `extra_metrics.judge_calibration`
(파이프라인이 `LLMJudgeCalibration.run()` 결과를 넣었을 때)의 MAE/Cohen κ. (c) **judge_self_consistency**
— `extra_metrics.judge_self_consistency`(`LLMJudge.self_consistency()` 결과)의 agreement.
셋을 종합해 `trust_level` high/medium/low(최저 등급 승) → `verdict_confidence(judge_trust=...)`로
배포 준비도 확신도 강등. judge 데이터 자체가 없으면 `evaluator_trust=None`. 리포트 섹션
`evaluator-reliability`, 대시보드 Improve 탭 패널.

**SPEC-041 P15 (HITL 트리아지 + 골든셋 승격)** — `reporting/insights.py::_review_queue_section` +
`comprehensive_report.py::_build_review_queue`: 기존 신호를 우선순위 리스트로 조립 —
judge↔휴리스틱 불일치(high) · suspicious ground_truth(high) · baseline 대비 회귀 실패(high) · baseline에
없던 신규 실패(medium) · 경계선 점수(acc 0.55–0.75 / comp 0.35–0.55, medium). task_id로 dedupe,
사유 병합, 25개 캡. 리포트 섹션 `review-queue`, 대시보드 패널.
**`agent-eval dataset promote <result.json> [--baseline F] [--min-priority high|medium|low] [--out DIR]
[--name F] [--tag TAG]`** (`cli/dataset.py::_cmd_promote`) — `build_insights().review_queue`의 플래그된
태스크를 `tasks[]`에서 찾아 `{question, ground_truth, context, source_task_id, review_reasons,
needs_human_review:True}` 골든 케이스로 `GoldenSetBuilder.merge_to_golden()`. 실패→회귀테스트 루프를 닫는다.
(주의: `--tag`이 golden version — top-level `--version`(store_true)과 충돌 피하려 `dest="promote_version"`.)

**SPEC-041 P16 (비용 경제성)** — `reporting/insights.py::_cost_economics_section` +
`comprehensive_report.py::_build_cost_economics`(Gate D 섹션 "Cost Efficiency"): per-task 비용 =
`tokens_used.input/1000×pricing.input + output/1000×pricing.output`(또는 `extra.cost_usd`), 없으면
`efficiency_metrics.tokens.total_cost` 균등분할(`cost_source`로 구분). **cost_per_successful_task**
(= total / _effective_fail 아닌 태스크 수) · **wasted_cost**(실패 태스크 비용 합) · **retry_cost**
(attempts>1 태스크의 `cost×(attempts-1)/attempts`) · **projection**(10만 콜 total/wasted USD). 대시보드
Improve 탭 패널. `_build_gate_d`에 `current` 인자 추가.

**SPEC-041 P17 (자연어 내러티브)** — `reporting/insights.py::_narrative_section` — 조립된 `insights`
dict에서 verdict 문구·confidence·next_actions[0](최약 컴포넌트+조치)·review_queue·evaluator_trust·
cost_economics.projection을 2~4문장 영어로 합성(`_narrative_from_template`, 결정적). `build_insights(...,
narrator=Callable[[insights_dict], str])`로 LLM 작성 대체 — narrator가 raise/non-str이면 템플릿 폴백.
`out["narrative"]`. `comprehensive_report.py::_build_narrative_banner`(리포트 최상단 `narrative` 섹션,
헤더 다음), `cli/gate.py::_print_narrative`(`agent-eval gate` 표 다음 "Summary"). monitor 경로는
`report.to_dict()`에 tasks[]가 없어 `_review_dict_tasks(_tasks_list)`를 graft해서 넘긴다.

**SPEC-041 P18 (변경 귀속)** — `PerformanceMonitor(prompt_text=..., config_snapshot={...})`(opt-in, 점수
무관) → `_build_lineage()`가 `lineage.prompt_text`/`prompt_hash`(sha1[:16])/`config_snapshot`으로 실음.
`reporting/insights.py::_change_attribution_section`(baseline 필요) — 두 run의 프롬프트 본문 line diff
(difflib SequenceMatcher, added/removed/similarity) + config_snapshot 키 diff + git commit + diagnosis의
최대 회귀 Gate(`largest_gate_move`). `insights.change_attribution`. `comprehensive_report.py::
_build_change_attribution`(리포트 `change-attribution` 섹션, diagnosis 앞), 대시보드 Improve 탭 패널.
report 두 진입점이 `build_insights`를 1회 호출해 `_insights_obj`로 narrative(P17)와 공유.
monitor 경로는 `_ins_input`에 tasks + `monitor._get_security_evaluator_data()`도 graft한다.

**SPEC-041 P19 (재현성·보안 국소화)** — `reporting/insights.py`: `_security_findings_section(current)` —
`evaluators.security`의 5개 트래커(input_sanitizer/output_leakage_detector/tool_authorizer/
privilege_escalation_detector/tool_chain_attack_detector) 레코드를 훑어 실제 탐지된 것만 per-task
`{task_id, tracker, threat_type, severity, cwe(_THREAT_CWE 매핑), detail}`로, severity 순 25개.
`_nondeterminism_section(tasks)` — `extra.reproducibility.score<0.85 & run_count>=2` 태스크 + `variance`
+ `sample_responses`(decorators.py가 score<1.0일 때 변형 응답 3개 truncate 저장, SPEC-041 P19). 리포트
섹션 `security-findings`(가장 심각 먼저)·`nondeterminism`, 대시보드 Improve 탭 패널.
`_review_dict_tasks`가 `extra`/`attempts`/`tokens_used`도 담도록 확장.

**SPEC-041 P21 (리포트 QA 수정 — 예시 리포트 감사에서 발견)**:
- **`create_taskresult(task_type="rag")`가 조용히 `"qa"`로 강등**되던 버그 — `taskresult_helpers.py::
  _resolve_task_type()` 신설: `_TASK_TYPE_ALIASES`(rag→information_retrieval, summarization→
  document_creation 등) + 알 수 없는 값은 QA 강등 대신 **원본 보존 + `UserWarning`**. per-slice/
  eval-set-quality가 RAG 코호트를 통째로 잃던 것 해소.
- **`_fmt_usd()`**(`comprehensive_report.py`) — 공용 통화 포맷 헬퍼. ≥$100은 `,.0f`, ≥$1은 `,.2f`,
  소수는 유효숫자. Cost Efficiency의 `$1267.5000`·`_build_gate_d._cost`의 4자리 고정 제거. 내러티브와
  Gate D 표의 금액이 이제 일치.
- **`_ins_input`에 `pricing` graft**(monitor 경로) — `report.to_dict()`엔 pricing이 없어 cost_economics가
  균등분할 폴백만 하던 것 → per-task 토큰 비용 정상 계산. `_build_gate_d`도 `_ins_input`을 받는다.
- **cost_economics.n_failed_or_lowscore** 추가 + 리포트 라벨 "Wasted on failed / low-scoring tasks
  (N of M)" — `_effective_fail`(12) vs Failed Cases의 `success` 플래그(10) 불일치를 명시.
- **`rca/diagnose.py::_is_excluded_detail_key()`** — regression 모드 `top_detail_deltas`에서
  `gate_*_tcr_weight`·`*_weight`·`*_penalty`·config 상수 제외(`_SHORTFALL_EXCLUDE_*`와 동일 취지,
  이전엔 `component_shortfalls`에만 적용).
- **Gate G LLM Judge**: dimension별 native scale 명시(`_judge_val(v, denom)`) — faithfulness/relevance는
  `/5`, overall만 `/10`(Gate C의 `/5`와 불일치 해소). 헤더 "7 Dimensions"→"LLM Judge".
- **Gate F**: workflow 카운트가 0이면 `step_success_rate=0.0`을 "0.0%"로 렌더하지 않음(N/A 배너).
- **Gate E**: `_count_noun(n, "threat")` — "1 threats"→"1 threat".
- **`insights._verdict_section(security_findings=)`** — critical/high 보안 findings를 `next_actions[0]`
  (`security:True`)로 넣고, 내러티브/exec-summary가 Gate 점수와 무관하게 최상단 노출(C1). 저표본
  컴포넌트(`insufficient_data_warnings`)는 `next_actions`에서 뒤로 밀고 `low_sample:True` 표식(C2).
- **`_build_executive_summary(verdict_obj=)`** — 이제 `insights.verdict.next_actions`를 그대로 렌더
  (내러티브와 단일 소스). confidence도 `verdict_obj`에서(judge_trust 강등 반영).
- **`_build_toc()`** — 23개 섹션용 스티키 in-page 네비(C3). `_build_history_trend`에 first/last run
  라벨(C5), `_build_slice_analysis`에 delta CI(C6), review_queue 2차 정렬 `-len(reasons)`(C4).

**SPEC-041 P24 (대화/멀티턴 인사이트)** — `reporting/insights.py::_conversation_section(current)` —
결과 JSON `conversation_sessions[]`를 훑어 `insights.conversation{n_sessions, avg_overall_score,
avg_context_retention, turn_quality_trajectory[]{turn, n, context_ref(에이전트 턴이 이전 턴 토큰을
재사용하는 비율), avg_response_chars, repetition(직전 에이전트 턴과의 유사도), nonanswer_rate},
degradation_after_turn(turn k부터 nonanswer_rate≥0.5가 지속되고 이전엔 아니었던 첫 지점 —
`_is_nonanswer`: <15자 또는 "i can't"/"could you clarify" 등 deflection 구문), worst_session}`.
(P35: `goal_drift_sessions`는 제거됨 — 첫↔마지막 user 턴 어휘 오버랩 휴리스틱이 같은 주제의
후속 질문을 주제 이탈로 오탐. `degradation_after_turn`이 "세션이 나빠지는 지점"을 이미 커버.)
리포트 `_build_conversation` 섹션 `conversation`(턴별 표 + context_ref 스파크라인 + degradation 경고),
대시보드 Improve 탭 패널. monitor 경로는 `_ins_input`에 `conversation_sessions`도 graft.

**SPEC-041 P35 (round-5 예시 리포트 감사 수정)** — 8건.
- **B1**: `comprehensive_report._review_dict_tasks`가 `partial_reason`/`errors`를 안 실어
  monitor 경로의 `insights.failure_clusters`/`readiness.fix_plan`/`failure_segments.dominant_reason`/
  `failure_triggers`가 전부 generic "incomplete · low accuracy" 시그니처로 퇴화(HTML의
  `_build_failure_clusters`는 `_norm_task_for_case` 직통이라 정상이었음 — 두 채널 불일치). 두 키 추가.
- **B2**: `_narrative_audit_section`의 `_RE_PCT`가 컴포넌트 health % ("relevance completeness (40%)")를
  TCR/accuracy 주장으로 오탐 → 항상-clean이어야 할 템플릿에 빨간 박스. 이제 % 앞뒤 40자에
  "tcr"/"accuracy"/"completion rate" 등이 있을 때만 검사.
- **B3**: `_conversation_section`의 `goal_drift_sessions` **제거**. 첫↔마지막 user 턴 어휘 오버랩
  휴리스틱이 같은 주제의 후속 질문("돈 언제 들어와요?")을 주제 이탈로 오탐 — 실측: healthy 4-턴
  반품 대화의 topic_coherence가 0.098로 나와 어떤 임계값 조합으로도 분리 불가. semantic 없이는
  신뢰 불가라 폐기. `degradation_after_turn`(비답변율)이 "세션이 나빠지는 지점"을 이미 커버.
  schema/09_OUTPUTS/대시보드에서도 제거.
- **B4**: `_trace_diffs_section`이 `hits[0]`(가장 오래된 cohort)와 diff → `hits[-1]`(가장 가까운 이전
  버전). `compared`/`first_lbl`→`prior_lbl`.
- **B5**: trace-diff "Response 0% unchanged"(이중부정) → `_td_resp_summary()`: ≤2% "fully rewritten",
  ≥98% "essentially unchanged", 그 외 "X% similar".
- **B6**: `_readiness_section`이 fail 게이트만 blocker로 봐서, 전부 warn인 run에서
  `_build_readiness`가 "does not clear every failing gate"라는 모순 문구 출력. 이제 `below = fails +
  warns`를 A/C(TCR-driven) vs 나머지로 나누고 `_only_warn` 분기, note를 "bring every warning gate to
  target"류로. verdict_line은 note 중복 제거하고 색만.
- **B7**: exec-summary next-action 폴백이 `(score 0.6372)` 미반올림 → `.2f`. 필드명 `tcr pct` →
  `_pretty_field()`(`_PRETTY_FIELD` 맵) → "TCR".
- **I1**: `_build_readiness` fix-plan 행에 `task_type` 표시, `_briefs_section` engineer 리스트는
  같은 시그니처 행을 count 합산 + task_type 병합.
- **I2**: `_build_diagnosis` regression 델타 표에서 baseline=None & delta=None 행(= 이번 run에 새로
  측정 시작된 지표)을 표 밖 "Newly measured this run" 문장으로 분리.

**P35 round 2 (다시 감사) — 4건 더:**
- **B2b**: `_insight_changes_section`이 *잘린 top-8* `failure_clusters` 리스트로 diff → 순위 밖으로
  밀린(여전히 발생 중인) 클러스터가 "resolved"로 표시. 이제 모든 `_effective_fail` 태스크의
  `_reason_signature(_task_reason(t))` **전체 집합**을 current vs baseline 대조. `failure_clusters`
  파라미터 제거.
- **I1b (fix-plan 병합)**: `_readiness_section` 버킷을 `(sig, ttype)` → **`sig`만**으로 변경.
  "error: TimeoutError"가 task_type별 3행으로 쪼개지던 것 → 1행, `task_types`(list) + `task_type`
  (단일이면 값, 아니면 None) 병기. 엔지니어 브리프는 upstream 병합을 신뢰(자체 병합 제거).
- **B3b (투영 일관성)**: Path-to-Green "After plan" 열이 항상 *전체 8클러스터* 투영이었는데 note는
  "top 3면 충분"이라 숫자 불일치. `ready_after`를 gaps 계산 전에 구하고, `plan_gain`을
  `ready_after`(없으면 전체) 시점 gain으로. gap 행에 `after_plan_fixes`, `projected_ready_after`에
  `plan_fixes_projected`/`projected_gate_scores` 추가. note에 "(Gate A ~0.71, Gate C ~0.70)" 병기.
- **B4b (필드명)**: `ontology.metric_registry.pretty_metric_name()` 신설(공유 `_PRETTY_FIELD` 맵) —
  `comprehensive_report._pretty_field`가 위임, `_build_recommendations`의 "Biggest measured
  shortfalls"와 `_narrative_from_template`의 "biggest measured shortfall" 문장도 사용. exec-summary만
  고쳐졌던 것을 세 곳 모두로.
- **개선**: `_conversation_section`에 `sessions[]`(per-session score/turns/ctx/coherence/nonanswer)
  + `best_session` 추가 — healthy 세션 1개 + 나쁜 세션 1개가 평균 21%로 뭉개지던 것 → 리포트에
  "Per session" 표. trace-diff에서 짧은 removed-run 1개 + added-run 1개는 "changed: X → Y"로.
전체 4534 통과. `test_p35_report_qa_fixes.py`(15).

**P35 round 3 (세 번째 감사) — 12건:**
- **B1 (게이트 점수 산출식 정합)**: `_build_score_breakdown`이 `( a+b+c ) ÷ N = <score>`를
  출력해 독자 검산을 유도하는데, TCR-가중(A·C) 또는 컴포넌트 누락(A) / 초과(E) 게이트에선
  이 산술이 배지 점수와 안 맞았다(A 69.2%≠63.9%, C 62.2%≠63.1%, E 96.5%≠97.5%). 이제
  `_naive`와 `score`가 0.2pp 넘게 벌어지면 `( a+b+c ) ÷ N ≈ M% · Gate X Score = SCORE%` +
  "TCR 컴포넌트를 {w:.0%}로 가중" 주석. D·G는 진짜 단순평균이라 기존 형식 유지. "component(s)
  averaged"→"measured".
- **B2**: Gate A 분해표에 `avg_quality_relevance_completeness` 행 추가(점수엔 들어가는데
  표엔 없었다). Accuracy 행 note에 "TCR 컴포넌트에 블렌딩(0.6×TCR + 0.4×accuracy)" 명시.
  formula_str도 실제 가중식으로 교체.
- **B3 (E threat-free 제외)**: aggregate의 `_include_sec_raw`(per-tracker 점수 있으면
  `_sec_score_raw` 제외)를 리포트도 미러 — threat-free 행은 `in_avg=False`(정보용), 다른
  컴포넌트가 하나도 없을 때만 재편입. `_add(..., in_avg=)` 파라미터 신설.
- **B3′ (fix-plan 정렬)**: `_readiness_section`의 `ranked`가 count 내림차순이라 "clusters by
  TCR impact" 라벨과 불일치(정확도 실패 클러스터가 TCR 회복 큰 timeout 클러스터보다 위).
  이제 `_standalone_tcr_gain`(멤버들의 1−completion 합 / total) 내림차순으로 정렬.
- **B4 (catch-all 세그먼트)**: `_failure_segments_section` 항목에 `catch_all` 플래그(실제
  토픽 클러스터 False, "other (no shared topic)" True). `_briefs_section` QA 문장은 catch_all이
  유일하면 `readiness.fix_plan[0]`(없으면 `failure_clusters[0]`) 시그니처를 인용. 리포트
  `_build_failure_segments`는 catch_all만이면 1행 표 대신 한 줄 안내.
- **B5**: `_rec_past_outcomes` "avg Δ +0.160"이 confirmed-only 평균인데 "N total" 뒤에 붙어
  오해 → "confirmed changes averaged Δ {:+.3f}"로 명시(음수 부호도 정상 처리).
- **C1**: Gate D efficiency note "No tool calls / EfficiencyConfig not set" → 툴 호출이
  있는데도 뜨던 오해 제거, "EfficiencyConfig not set"만.
- **C3**: `_rec_baseline_verdict`의 "Since baseline … (Δ -0.207) — refuted"가 델타 자체가
  반증된 것처럼 읽힘 → "improved/regressed vs baseline".
- **C4**: 리포트 per-session 표에서 "Topic coherence" 열 제거(P35 r1이 신뢰 불가로 판정한
  지표 — bare 컬럼으로 재노출하던 것). `sessions[].topic_coherence` 데이터는 유지.
- **C5**: `_insight_changes_section`의 `newly_failing_gates`가 hard-fail(<0.5)만 잡아 pass→warn
  전이를 놓침 → "below target"(fail OR warn, <0.7)으로 확장. 라벨도 "Newly below target".
- **N1**: Conclusion "Hallucination Rate: 0.0%"가 미측정(`summary.hallucination_rate` null)일 때도
  0.0%로 렌더 → Gate C/G details에 실제 `hallucination_rate`가 있을 때만 수치, 아니면
  "n/a (not enabled)". faithfulness는 대체 신호라 측정 근거로 안 침.
- **N2**: `_build_advanced_section`이 본문 0줄이어도 "Advanced Metrics" 헤더 + 좌측 레일 +
  TOC 항목을 남기던 것 → 본문 없으면 "" 반환.
- **N3**: Conclusion "Harness Gate: 2/7 PASS"가 미측정 B·F를 실패로 카운트 → "2/5 measured
  PASS (2 gate(s) not measured)".
- **N4**: Exec Summary가 TCR CI만 보이고 Accuracy CI는 Conclusion에만 → Exec Summary에도 병기.
- **P2**: eval-set-quality가 경고 없으면 히스토그램 3줄만 떠서 렌더 글리치처럼 보임 →
  "✓ No coverage/balance/near-duplicate/suspicious-label issues detected" 한 줄 추가.
- **P4**: trace-diff에서 회귀 버전이 무응답(timeout/error)이면 `response_diff.errored`/
  `error_reason` 플래그 → "removed: <옛 답>" bare 워드 diff 대신 "Current version returned
  no response (error: …)".
- **P5**: narrative/exec-summary/recommendations의 "shortfall is X — X is low. …"에서 필드명이
  대시 양옆에 두 번 나오던 것 → `_trim_field_restatement()`가 guidance 첫 문장이 필드명 재진술이면
  잘라냄.
전체 4542 통과. `test_p35_report_qa_fixes.py`(+8 = 23).

**SPEC-041 P36 (증거 기반 처방)** — `reporting/insights.py`: `recommendations[]`에 `proposal`
객체 추가. `_attach_proposals(out, tasks, current, fixer)`가 각 fail/warn 게이트의 최상위 실패
클러스터(`readiness.fix_plan`의 `targets_gates` 매칭 → 없으면 `failure_clusters` + `_fix_effort_hint`)
멤버 태스크와 시스템 프롬프트(`lineage.prompt_text`, 있을 때)를 보고 `{kind:
prompt_edit|config_change|data_fix, before, after, rationale, evidence_task_ids, authored_by}`를
합성한다. `_proposal_category()`(runtime/grounding/decomposition/guardrail/data/generic) →
`_deterministic_proposal()` 템플릿. `build_insights(fixer=Callable[[payload], dict|None])` —
`{gate, cluster_signature, prompt_text, evidence[], template_proposal}`를 받아 LLM 작성 proposal을
돌려주면 `_validate_proposal()`(kind 화이트리스트) 통과 시 교체, 아니면/raise면 템플릿 폴백
(`narrator`와 동일 패턴). **자동 적용 절대 안 함 — 사람이 검토할 초안.** 리포트
`_rec_proposal_html()`가 recommendations 카드에 before(−)/after(+) + rationale + Evidence 태스크
id 블록 렌더(`_build_recommendations(insights_recs=)`, 두 진입점 모두 `_insights_obj["recommendations"]`
전달). 스키마 `recommendations[].proposal` 추가. `test_fix_proposals.py`(9). 전체 4551 통과.

**SPEC-041 P37 (불확실성 있는 전(全)게이트 투영)** — `reporting/insights.py::_readiness_section`:
`fix_plan[]` 각 행에 `projected_gate_scores{모든 below-target 게이트}` + `projected_gate_scores_ci`
(A·C만, Beta-Binomial 부트스트랩) + `gate_moves{게이트→bool}`(A·C=True는 TCR 이동, B/D/E/F/G=False는
현재값 고정 — 태스크 결과가 지연/비용/보안을 안 바꿈) + `effort_weight`(`_effort_weight_for_sig`:
data 1·runtime/guardrail 2·grounding/decomposition 3·generic 4) + `roi`(= 닫힌 gap pp ÷ effort_weight).
부트스트랩: 전체 pass율 Beta(passes+1, fails+1)에서 p 추출 → 누적 fixed 태스크가 각각 Bernoulli(p)로
flip → 게이트 점수 재계산, 400회, seed `_PROJ_SEED+rank`로 결정적. `projected_ready_after`에 `p_ready`
(TCR 블로커 전부 target 도달 확률) + `likely_fix_count`(부트스트랩 modal rank) 추가. 리포트
`_build_readiness`: fix-plan 표 Helps 열에 "effort <label> · ROI <n>", Projected TCR 열 아래
"→ A~0.76 [0.64–0.76] · C~..." 벡터, Projected 문장에 "~100% likely to clear after 1 fix" 꼬리말.
스키마 `readiness.fix_plan[].{effort_weight,projected_gate_scores,projected_gate_scores_ci,gate_moves,roi}`
+ `projected_ready_after.{p_ready,likely_fix_count}`. `test_readiness_projection_p37.py`(6). 전체 4557 통과.

**SPEC-041 P38 (회귀 → 원인 연결)** — `reporting/insights.py::_regression_attribution_section`:
`failure_lineage.regressed`(baseline pass→current fail 태스크) × `change_attribution`(무엇이 바뀜:
config_diff.changed_keys / prompt_diff.removed) × `metadata_slices`(어디에 몰림: model_variant/
difficulty별 tcr_delta_pp)를 조인. 회귀 태스크를 `_reason_signature`로 군집화 → 각 군집에
`slice_concentration[]`(≥60%가 한 슬라이스 값에 몰리고 그 슬라이스가 baseline 대비 음수 Δ면
`{dimension, value, share_pct, slice_tcr_delta_pp}`) + `implicated_changes[]`(`_change_implicates`:
config 키/프롬프트 제거 라인의 성격이 그 군집의 실패 카테고리와 매칭 — model→전부, temp/top_k/
context→grounding, retry/timeout/tool→runtime, step/numbered→decomposition, scope/guard→guardrail).
비-스칼라 `extra` 키(dict/60자 초과 문자열)는 제외, `metadata_slices`가 이미 검증한 dimension만
우선. **단일 run엔 change-set이 하나뿐이라 시간적 격리가 아닌 상관** — note에 명시. `build_insights`
`out` 딕셔너리 조립 후 `_attach_proposals` 옆에서 계산(`out.regression_attribution`, baseline
없으면 None). 리포트 `_build_regression_attribution()` 섹션 `regression-attribution`
(change-attribution 앞), TOC "Reg. cause". 스키마 `regression_attribution` 추가.
`test_regression_attribution_p38.py`(5). 전체 4562 통과.

**SPEC-041 P39 (에이전트 확신도 calibration + 기권 품질)** — opt-in. `utils/confidence.py`:
`expected_calibration_error(pairs, n_bins=10)`(ECE = Σ nᵦ/N·|accᵦ−confᵦ|, MCE, 버킷별 상세) ·
`brier_score(pairs)`(Σ(conf−correct)²/N) · `risk_coverage_points(pairs)`(confidence 내림차순 정렬 →
상위 커버리지별 error rate — 잘 보정됐으면 커버리지 줄일수록 risk 하락). `reporting/insights.py::
_calibration_section(tasks)` — 태스크 `extra.confidence`(0-1)/`extra.abstained`(bool)를 읽어
`{n_with_confidence, ece, mce, brier, mean_confidence, empirical_accuracy, confidence_gap(+면
overconfident), verdict(overconfident>0.10/underconfident<−0.10/well-calibrated), reliability_bins[],
risk_coverage[], confidence_is_informative, confidence_signal(informative/flat/inverted),
abstention{n_abstained, abstention_rate_pct, answered_accuracy_pct, abstained_when_answerable(=
usable ground_truth 있는데 기권), example_task_ids}}`. `_is_correct`: accuracy≥0.6 우선, 없으면
not `_effective_fail`. 확신 태스크 <5개이고 기권도 없으면 None. `build_insights` out 딕셔너리에
`calibration` 추가. `_narrative_from_template`이 overconfident면 "reports X% confidence but only
Y% accurate (ECE …); wrong answers delivered as if certain" 문장 + 기권 answerable 있으면 별도
문장. 리포트 `_build_calibration()` 섹션 `calibration`(non-determinism 다음): verdict/mean_conf/
accuracy/ECE/Brier KPI + confidence 버킷별 stated vs actual 표(gap>0.1 빨강) + risk/coverage 한 줄
(+signal 판정) + abstention. TOC "Calibration". 스키마 `calibration`. gen_example_v2.py: rich run에
`extra.confidence`(실패 태스크는 0.82-0.97로 overconfident) + `t_qa_7`/`t_rag_8` `abstained`.
`test_calibration_p39.py`(9). 전체 4571 통과.

**SPEC-041 P40 (비용/지연 최적화 제안)** — `reporting/insights.py::_efficiency_opportunities_section`:
P7 지연 예산·P16 비용 경제성이 *보고만* 하던 것을 구체적 조치로. `insights.efficiency_opportunities[]`
`{kind, title, detail, projected_saving_pct, projected_saving_per_100k_usd, risk, evidence}`:
(a) **model_routing** — `metadata_slices`의 model/variant/engine dimension에서 값별 per-task 토큰비용
(`_task_token_cost`) + TCR 계산 → 가장 싼 값이 가장 비싼 값의 85% 미만 비용이고 TCR 손실 ≤5pp이며
현재 cost/task보다 싸면 "consolidate on '<cheap>'" + 절감률/10만콜 절감액. (b) **step_gating** —
`parse_span_timeline`으로 태스크별 스텝 타이밍 파싱, ≥5개 timed 태스크에서 ≥90% 태스크에 등장 &
mean self_ms ≥80ms & 최대 지속시간 스텝(=핵심 작업)이 아닌 스텝 1개를 "gate the '<step>' step"
(비용 절감 정량화 불가라 None). (c) **retry_reduction** — `cost_economics.retry_cost_pct ≥5%`면
runtime 카테고리 `failure_clusters` 이름과 함께 "N% of spend is retries". 전부 상관·1차 근사.
`build_insights` out 딕셔너리 조립 후(`_attach_proposals` 옆) 계산. 리포트
`_build_efficiency_opportunities()` 섹션 `efficiency-opportunities`(calibration 다음), TOC "Efficiency".
스키마 `efficiency_opportunities`. gen_example_v2.py: rich RAG 태스크에 timed `retrieve→rerank→
synthesize` tool_calls 추가(step_gating 데모). `test_efficiency_opportunities_p40.py`(6). 전체 4577 통과.

**SPEC-041 P41 (멀티에이전트 인사이트 섹션)** — `reporting/insights.py::_multiagent_section`:
`conversation`(P24)에 대응하는 Gate F용 분석. 태스크 `agent_interactions`(list of
`{from/from_agent/sender, to/to_agent/receiver, message/content, success}`) 있을 때
`insights.multiagent{n_agents, per_agent[]{agent_id, n_turns, error_rate(성공=False 비율),
contribution_score(전체 발신 대비 점유)}, handoffs[]{from, to, n, context_retention_at_handoff
(수신자의 다음 메시지가 받은 메시지 토큰을 재사용하는 `_overlap`)}, communication_graph[],
bottleneck_agent(≥2턴 중 error_rate 최고, 없으면 저-retention 핸드오프를 가장 많이 받는 에이전트),
repeated_agents(연속 동일 메시지 발신), mast_candidates[]{code, name, category, remediation}}.
MAST(Cemri et al. 2025) 매핑: 평균 핸드오프 retention<0.3→1.4(Loss of Conversation History),
repeated→1.3(Step Repetition), 한 에이전트 error_rate≥0.34→1.2(Disobey Role Spec), A→B·B→A
핑퐁 사이클→1.5(Unaware of Termination). `mast_failure_mode_by_code` 재사용. 결정적, stdlib.
`build_insights` out 딕셔너리에 `multiagent` 추가. 리포트 `_build_multiagent()` 섹션 `multiagent`
(conversation 앞): per-agent 표(bottleneck 표시, error_rate≥0.34 빨강) + 핸드오프 표(retention<0.3
빨강) + MAST 후보 리스트. TOC "Multi-agent". 스키마 `multiagent`. gen_example_v2.py: rich tool_use
태스크에 planner→retriever→responder crew `agent_interactions`(thin context 핸드오프).
`test_multiagent_insight_p41.py`(6). 전체 4583 통과.

**SPEC-041 P42 (복합 보안 finding + 공격 결과 연결)** — `reporting/insights.py`:
`_security_findings_section(current, tasks=None)` 각 finding에 `succeeded`(yes/likely/no/unknown)
추가 — 레코드에 `blocked/prevented/enforced` 또는 `acted_on/executed/bypassed`가 있으면 그대로,
없으면 태스크 `tool_calls`에 성공 실행이 있으면 "likely", 아니면 "unknown"(탐지 ≠ 침해). 같은
태스크에 서로 다른 트래커 2개 이상이 flag하면 단일 `kind:"compound"` finding 합성 —
`severity`를 최악 컴포넌트에서 한 단계 상향(`_bump_severity`, critical cap), `components[]`·
`cwe[]`(리스트)·`succeeded`(컴포넌트 중 하나라도 landed면 승계). 정렬은 compound 먼저.
새 `_security_posture_section(current, tasks, security_findings)` → `insights.security_posture
{n_findings, n_tasks_affected, n_compound, by_severity, tools_implicated[]{tool, n}(detail의
"tool <name>" 파싱), landed_or_likely[], any_landed}`. `build_insights` out 딕셔너리에
`security_posture` 추가, `security_findings` 호출에 `tasks` 전달. 리포트
`_build_security_findings`: 상단에 attack-surface 요약 박스 + 표에 "Outcome" 열(landed 빨강/
likely 주황/blocked 초록) + compound 행 하이라이트(CRITICAL COMPOUND 태그). 스키마
`security_findings[].{succeeded,kind,components}` + `cwe` array 허용 + `security_posture`.
`test_security_compound_p42.py`(7). 전체 4590 통과.

**SPEC-041 P43 (사용자 정의 목표/SLO)** — `.aoo/targets.json`(`{gate_default?, gates?{A:0.85,…},
tcr_pct?, accuracy_pct?, cost_per_task_usd?, note?}`, 모든 키 optional). 신규 `utils/targets.py`:
`load_targets(path)`(누락/손상 시 None) · `save_targets`(shallow merge, `gates`는 deep) ·
`gate_target(targets, gate, default=0.7)`(per-gate > gate_default > SDK 기본) · `is_user_defined()`.
신규 `agent-eval target {set,show,clear}`(`cli/targets.py`). `build_insights(current, *,
targets=None)` → `_verdict_section`·`_readiness_section`에 전달. verdict: SDK pass 라인은 넘지만
사용자 바(bar)엔 못 미치는 게이트를 `below_user_target_gates`로, headline은 "below your target",
`targets_source`("user"/"builtin")·`targets` 노출. readiness: `_gt(k)`(=per-gate 목표)로 gaps의
`target`/`gap`, fix_plan 투영, `ready_after`·`p_ready` 부트스트랩, note 문구("your target") 전부
재계산; `targets_source`·`per_gate_targets` 노출. `_narrative_from_template`은 verdict.headline을
그대로 써서 자동 반영. `monitor.save_to_file()`·리포트 두 진입점·`agent-eval gate`가 CWD의
`.aoo/targets.json`을 자동 로드. `agent-eval gate`: `--gate-thresholds` 미지정 시 targets의
`gates`로 임계값 구성, `--tcr`/`--accuracy`/`--max-cost-per-task`/`--min-gate-score` 미지정 시
targets에서 채움(명시 인수가 이김), "Using targets from .aoo/targets.json" 출력. 리포트
`_build_readiness`: targets_source=user면 "Measured against your targets" 배너 + Target 열은
per-row 값. 스키마 `verdict.{below_user_target_gates,targets_source,targets}` +
`readiness.{targets_source,per_gate_targets}`. `test_user_targets_p43.py`(10). 전체 4600 통과.

**SPEC-041 P44 (임계값 민감도)** — `reporting/insights.py::_threshold_sensitivity_section(harness_groups,
tasks, targets=None)` → `insights.threshold_sensitivity`. 배포 판정이 두 임의 상수(게이트 pass 라인
0.7, per-task accuracy 임계값)에 얼마나 민감한지 스윕. `gate_line_sweep[]` = 라인
{0.50…0.85} 각각에 `{line, gates_meeting(score≥line), gates_below, verdict}` — verdict는 `_ts_verdict`
스윕 모델(라인 미달 게이트 있으면 caution, `line−0.15` 미달 있으면 not_ready). `accuracy_threshold_sweep[]`
= 임계값 {0.50…0.80}별 `pass_rate_pct`(=accuracy≥thr 태스크 비율). `knife_edge` = 현재 라인(user
target 있으면 그 값, 없으면 0.7)의 스윕 verdict가 ±0.05에서 달라지면 True + `knife_edge_detail`
("at 0.65 it would be 'caution' — the decision is sensitive to where the line is drawn"). 순수
계산(per-task 점수만, 새 판정 없음). `build_insights` out 딕셔너리에 추가. 리포트
`_build_threshold_sensitivity()` 섹션 `threshold-sensitivity`(Conclusion 앞): knife-edge면 앰버 배너,
안정이면 초록 한 줄 + pass-line 스윕 표(현재 행 볼드 "← current") + accuracy 스윕 표. TOC "Sensitivity".
스키마 `threshold_sensitivity`. `test_threshold_sensitivity_p44.py`(7). 전체 4607 통과.

**SPEC-041 P47 (claim 레벨 실패 설명)** — `reporting/insights.py::_failure_explanations_section(tasks,
*, explainer=None)` → `insights.failure_explanations[]`. worst-N 실패(응답 있는 것)마다 응답을
`_sentences`로 문장 분할 → 각 claim에 `{text, verdict, source}`:
- **verdict** (`_claim_verdict`, NLI 없음): `contradicts_ground_truth`(공유 내용어 있고 —
  `_has_neg`(정규식) 부정어 플립 또는 `_nums` 숫자 불일치 또는 gt 오버랩 0.18–0.55) >
  `supported`(오버랩 ≥0.55) > `unsupported` > `unverifiable`(gt 없음).
- **source** (`_claim_source`): claim↔`_ctx_chunks` 중 오버랩 최고 청크가 ≥0.30이면
  `context_chunk[i]`, 아니면 tool_call 출력에 있으면 `tool_output`, 아니면 `none — hallucinated
  or from reasoning`.
행에 `wrong_claim`/`wrong_claim_verdict`/`wrong_claim_source`(첫 contradicts/unsupported claim) +
`explained_by`("template"/"explainer"). `build_insights(explainer=Callable[[payload], dict|None])` —
payload `{task_id, question, response, ground_truth, context_chunks[], template_explanation}` →
`{claims:[…]}` 반환 시 교체(narrator/fixer 동일 패턴, 실패 시 템플릿). `out` 딕셔너리
`failure_explanations` 추가. 리포트 `_build_failure_explanations()` 섹션 `failure-explanations`
(failure-cases 다음): 태스크별 Claim/Verdict/Source 표(verdict 색상) + "Wrong claim" 한 줄.
TOC "Wrong claims". 스키마 `failure_explanations`. gen_example_v2: `t_rag_3`을 `wrong_fact` 모드로
고정(숫자 플립 → context_chunk[0] 추적 데모). `test_failure_explanations_p47.py`(10). 전체 4617 통과.

**SPEC-041 P45 (eval-set 갭 분석 + contamination)** — `_eval_set_quality_section(tasks, baseline,
harness_groups, current=None)`(신규 `current` 인자)에 3개 추가:
- `capability_coverage` — `_capability_coverage()`가 `task_type × difficulty(extra) × uses_tools
  (bool) × question_length(short≤8w/long≥25w/medium)` 셀별 `{n, fail_n}` + `thin_cells`(0<n<3).
- `contamination[]` — `_contamination()`가 태스크 `question`/`ground_truth`의 4-gram(`_q_ngrams`)이
  `lineage.prompt_text`의 4-gram과 ≥40% 겹치면 `{task_id, field, overlap_pct, snippet}`(few-shot
  누출 → 점수 부풀림). prompt_text 없으면 [].
- `targeted_additions[]` — `_targeted_additions()`가 실패가 몰린 task_type(≥2건)이 히스토그램
  중앙값·8 미만이면 `{task_type, current_n, failing_n, suggested_add, reason}`.
contamination 있으면 / thin_cell 상위 3개도 `coverage_warnings`에 문장 추가. 리포트
`_build_eval_set_quality(..., precomputed=)` — 이제 `_insights_obj["eval_set_quality"]`를 그대로
받아(재계산 안 함) capability-coverage 표 + ⚠️ Prompt contamination 리스트 + "What to add" 리스트를
렌더. 스키마 `eval_set_quality.{capability_coverage,contamination,targeted_additions}`. gen_example_v2:
PROMPT_V3에 `t_qa_2` 질문+정답을 few-shot으로 넣어 contamination 데모. `test_eval_set_gap_p45.py`(7).
전체 4624 통과.

**SPEC-041 P46 (지표 신호/중복 분석)** — `utils/confidence.py::pearson_r(xs, ys)`(stdlib, <3쌍 또는
분산 0이면 None). `reporting/insights.py::_metric_signal_section(tasks)` → `insights.metric_signal`.
per-task 지표 벡터 추출(`completion`·`accuracy`·`judge_overall`(/10)·`faithfulness`(/5)·
`latency`(execution_time)·`tokens`(tokens_used.total), 각각 ≥5개 있어야 포함) → 모든 쌍 Pearson
`correlations[]{a,b,r,n}` + `redundant_pairs[]`(|r|≥0.9 → "둘 중 하나만 추적해도 정보 손실 ≈0") +
(opt-in `extra.outcome` 스칼라 ≥5개면) `outcome_correlation[]{metric,r,n}` |r| 내림차순 — "가장 잘
예측하는 지표" + |r|<0.15인 지표는 "deprioritise". `note` 합성. 리포트 `_build_metric_signal()` 섹션
`metric-signal`(evaluator-reliability 앞): Redundant metrics 리스트 + outcome 예측 표(|r|≥0.4 초록/
0.15–0.4 주황/<0.15 빨강) + pairwise 상관 표. TOC "Metric signal". 스키마 `metric_signal`.
gen_example_v2: rich 태스크에 `extra.outcome`(1–5 CSAT, accuracy 추종·latency 무관) 추가.
`test_metric_signal_p46.py`(7). 전체 4631 통과.

**SPEC-041 P48 (종단 인텔리전스 — 여러 run 가로지르기)** — `reporting/insights.py::
_longitudinal_section(history_dir, current_file=None)` → `insights.longitudinal`. `history_dir`의
형제 결과 JSON(`baseline.json`·`current_file` 제외, `_LONG_MAX_RUNS=20` 최신본, `_LONG_MIN_RUNS=4`
미만이면 None)을 timestamp 순으로 읽어 각 run의 `{tcr, fail_sigs(=실패 태스크의
`_reason_signature(_task_reason(t))` 집합), fingerprint(`_question_fingerprint`)}`을 만든다. 반환:
`recurring_failures[]{signature, in_n_runs, of_runs, flap_transitions(0↔1 전이 수), currently_failing,
kind(chronic=전 run 실패 / flapping=전이≥2 / recurring), note}` — 3개 이상 run에 등장한 시그니처만,
`(-in_n_runs, -flap_transitions)` 정렬(가장 만성적인 것 먼저), 상위 10 · `eval_set_stability`
{같은 fingerprint를 가진 최대 그룹(≥3 run)의 `n_runs_same_eval_set, tcr_mean_pct, tcr_stdev_pp,
detectable_change_pp(=2·sd)`, "변하지 않은 평가셋에서 TCR이 ±Npp 움직였으니 ~2Npp보다 작은 실제
변화는 노이즈와 구분 불가"} · `cadence{n_intervals, median_days_between_runs, last_gap_days}`
(`_days_between` 재사용). P13(per-Gate 스파크라인/slope)의 보완 — 이쪽은 "무엇이 계속 실패하나 /
재실행에 얼마나 노이즈가 끼나 / 얼마나 자주 도나". `build_insights(history_dir=, current_file=)` 파라미터
추가, out dict에 `"insight_changes"` 앞으로 배선. 리포트 `_build_longitudinal()` 섹션 `longitudinal`
(trace-diffs 뒤, insight-changes 앞): CHRONIC/FLAPPING/RECURRING 뱃지 + `runs`(N/M) + `flips` + "latest
run" 상태 표 + 안정성 한 줄 + cadence 한 줄. TOC "Across runs". monitor 경로는 `current_file=None`이라
현재 run도 포함(디스크에 있으면), 리포트 경로는 `rf.path`를 제외. 스키마 `longitudinal`.
gen_example_v2: `h1/h2/h3` 이전 run 3개 추가 + 7개 run의 timestamp를 7일 간격으로 재작성.
`test_longitudinal_p48.py`(7). 전체 4638 통과.

**SPEC-041 P34 (대상별 브리프 + 내러티브 주장 감사)** — `reporting/insights.py`:
`_briefs_section(ins)` → `insights.briefs{pm, qa, engineer}` — 조립된 out dict(verdict/readiness/
review_queue/evaluator_trust/failure_segments/freshness/security_findings/recommendations)에서 결정적
합성. `_narrative_audit_section(narrative, ins)` → `insights.narrative_audit{claims_checked, clean,
adjustments[]}` — `_READY_PHRASES`(affirmative만, "not deployment-ready" 미매치)·`_RE_PCT`(±3pp)·
baseline 유무·confidence=low 미언급 체크. narrator가 준 텍스트를 재작성하진 않고 flag만. `out["narrative"]`
계산 직후 `out["narrative_audit"]`·`out["briefs"]` 추가(narrator 반영). 리포트 `_build_briefs()` 섹션
`briefs`(readiness 다음, 3열 그리드) + `_build_narrative_audit_note()`(narrative 배너 다음, dirty일 때만
빨간 박스). 대시보드 Improve 탭 패널 2개. `agent-eval gate --digest` → `_print_digest(data)`가 PM/QA/
engineer 브리프를 표 다음 출력.

**SPEC-041 P33 (인사이트 메타-diff + 신선도)** — `reporting/insights.py`:
`_insight_changes_section(current, baseline, security_findings, evaluator_trust, failure_clusters,
harness_groups)` → `insights.insight_changes` (baseline 필요). `change_attribution`이 프롬프트/config/
지표 delta를 보는 것과 달리 *인사이트 자체*를 diff — new/resolved failure cluster(시그니처 집합 차),
trust_change(trust_level), new_security_findings((task_id,threat_type) 신규), verdict_change(level),
newly_failing/passing_gates. baseline 인사이트는 full 재실행 대신 `_failure_clusters_section`/
`_evaluator_trust_section`/`_security_findings_section`/`_verdict_section`을 baseline로 직접 호출(경량).
아무것도 안 움직였으면 None. `_freshness_section(current, baseline, eval_set_quality, failure_clusters,
failure_segments, ci)` → `insights.freshness{baseline_age_days(_days_between+_report_timestamp),
eval_set_identical_to_baseline(_question_fingerprint 동일성), n_tasks, warnings[]}`. 경고: baseline
>30일 · 질문셋 그대로인데 새 실패모드 · suspicious_ground_truth · n_tasks<20. baseline 없어도
n_tasks 경고는 가능(그땐 baseline_age_days=None). 리포트 `_build_freshness_banner()`(narrative 배너
다음, 앰버) + `_build_insight_changes()` 섹션 `insight-changes`(change-attribution 앞). 대시보드
Improve 탭 상단 패널 2개. build_insights가 `fclusters`/`fsegments`를 1회 계산해 out dict과 양 섹션이 공유.

**SPEC-041 P32 (트레이스 레벨 버전 간 diff)** — `reporting/insights.py::_trace_diffs_section(current,
cohort)` → `insights.trace_diffs` (cohort 지정 시만). `_labelled_cohort`(P22 재사용)로 [(label, report)…],
[0]=current. current에 있고 cohort 버전 ≥1개에도 있으며 결과가 뒤집혔거나 |Δacc|≥0.15/|Δcomp|≥0.20인
태스크만. current vs *첫* cohort 항목을 diff: `response_diff`(difflib SequenceMatcher — similarity +
added/removed 단어런, `_word_runs`) · `trajectory_diff`(`_trace_step_names`로 tool_calls→chain_steps→
agent_interactions 스텝명 시퀀스 추출 → added/removed/reordered) · `score_delta` · `per_version[]`
(태스크를 담은 모든 버전, current 먼저). verdict fixed/improved/regressed/declined/changed. 정렬:
regressed 먼저, |Δacc| 큰 순. 최대 8개. 리포트 `_build_trace_diffs()` 섹션 `trace-diffs`
(cohort-comparison 바로 뒤), 대시보드 cohort 패널 하위 리스트.

**SPEC-041 P31 (`ask_insights` MCP)** — `integrations/ask_insights_mcp.py` — 결과 JSON을 로드해
`build_insights()`를 1회 계산하고 4개 구조화 질문에 답하는 stdio MCP 서버(옵트인 `[mcp]`,
`violation_search_mcp`/`recommend_fix_mcp`와 나란히). 도구: `insights_summary(result_file,
baseline_file="")` · `insights_readiness(result_file)` · `insights_why_failed(result_file, task_id)` ·
`insights_list(result_file, filter, baseline_file="")`. 순수 함수(`summary_text`/`readiness_text`/
`why_failed_text`/`list_task_ids`)는 별도 import·테스트 가능. filter: failing/judge_disagreement/
borderline/nondeterministic/security/regressed(baseline 필요)/review/`segment:<text>`. 새 판정
로직 없음, 결과 파일 미변경. `agent-eval {opencode,claude} install --with-ask-insights`로 등록
(constants·register fn·install/upgrade hook·uninstall deregister·claude doctor mcp_targets 전부 배선,
`_MCP_NAMES`에 `agent-evaluator-ask-insights` 추가). opencode doctor는 MCP 미검사라 변경 없음.

**SPEC-041 P30 (의미 기반 실패 세그먼트 + 트리거 국소화)** — `reporting/insights.py`:
`_failure_segments_section(tasks)` — 실패 태스크의 *질문*을 어휘 토픽으로 군집화. `_tfidf_vectors`
(binary TF-IDF, df==N 항 제외, L2 정규화) + `_cosine` + greedy 그룹화(가장 distinctive 질문부터
seed, cosine≥`_SEG_SIM`=0.22). `_wtok`/`_RAG_STOPWORDS` 재사용. 각 세그먼트: label(상위 3 키워드)·
keywords·task_ids·n·share_of_failures_pct·impact_pct·dominant_reason(`_reason_signature` 최빈)·
example_question. 결정적(seed 순서 고정). 실패 <4개 또는 내용어 부족이면 None. `_failure_triggers_section`
— worst-N 실패마다 `_ctx_chunks`(context를 문단/문장 분할)로 gt-오버랩 최저 청크 확인 → `retrieval_gap`
(best<`_RAG_RECALL_MISS`) / `grounding`(reason에 ground/context/contradict + 응답이 다른 청크 추종) /
`tool_failure`(첫 success=False 스텝) / `runtime_error`(reason이 `error:`). 리포트
`_build_failure_segments()` — failure-cases 섹션 안에 "Failure segments" 표 + "Likely triggers" 리스트.
대시보드 Improve 탭 패널. `_review_dict_tasks`는 TaskResult 속성 접근이라 리포트 경로는 실제 객체 필요
(plain dict은 insights 섹션에서만 동작).

**SPEC-041 P29 (green까지의 경로)** — `reporting/insights.py::_readiness_section(tasks, harness_groups)` →
`insights.readiness`. `gaps[]` = fail/warn 게이트별 `{score, target(0.7=gates/base.py `_status` warn 라인),
gap, blocking, projected_score_after_plan(A/C만, estimate)}`. `fix_plan[]` = 실패군집(전체 멤버십으로
재계산, `_failure_clusters_section`의 잘린 example_task_ids 대신)을 크기순 정렬, 각 항목에 결정적 투영
`projected_tcr_after_pct`(해당 군집까지 fix 시 완료율 정확 재계산)·`cumulative_tcr_gain_pp`·
`effort_hint`+`targets_gates`(`_fix_effort_hint`: reason 시그니처 키워드→처방/게이트 매핑).
`projected_ready_after` = TCR-driven 블로커(A/C)가 몇 개 fix 후 target을 넘는지 + B/D/E/F/G는
`remaining_structural_blockers`로 분리("task 결과로 안 움직임"). 투영은 1차 근사(군집 태스크가 pass로
바뀌고 나머지 불변 가정) — 순서 잡기용이지 보장 아님. 리포트 `_build_readiness()` 섹션 `path-to-green`
(verdict 바로 아래), 대시보드 Improve 탭 패널. fail/warn 게이트도 실패군집도 없으면 None.

**SPEC-041 P28 (인사이트 전달 로드맵 마무리)** — 4개 독립 추가.
(1) **메타데이터 슬라이싱** — `reporting/insights.py::_metadata_slices_section(tasks, baseline)` —
`slice_analysis`(task_type 전용)를 task의 스칼라 `extra` 키(model/prompt_variant/difficulty…)로
확장. `_slice_stats()`(TCR/accuracy/CI + baseline Δ + 부트스트랩 유의성)를 두 섹션이 공유하도록
`_slice_analysis_section` 리팩터. 자동 발견: 스칼라 값·≥60% 커버리지·2~8개 distinct·task_type과
bijection 아님(`_one_to_one` 양방향 검사). `insights.metadata_slices`. 리포트 `_build_metadata_slices`
섹션 `metadata-slices`.
(2) **"다음에 뭘 테스트" 가이드** — `_sample_guidance_section(ci)` — `metric_confidence`의 TCR CI
half-width가 ±5pp보다 크면 `required_n_for_halfwidth`로 권장 표본 수 + 추가 태스크 수 계산.
`insights.sample_guidance`. 리포트 `_build_sample_guidance` 섹션 `sample-guidance`.
(3) **재현성 매니페스트** — `PerformanceMonitor(model_params=, dataset_ref=)` 신설 + `monitor.py::
_build_reproducibility_manifest()` — model_name·model_params(temperature/top_p/seed)·judge_model·
dataset_ref·evaluator_config(점수 계산 플래그/가중치)+그 sha1 해시·dependency_versions(importlib.
metadata로 anthropic/openai/deepeval/ragas/numpy/pandas). `lineage.reproducibility_manifest`에 실림,
`insights.reproducibility_manifest`로 패스스루. 리포트 `_build_reproducibility_manifest` 섹션
`reproducibility`.
(4) **비용 SLO 게이트** — `agent-eval gate --max-cost-per-task USD` — `_load_metrics`가
`cost_per_task = total_cost / task 수` 계산, `_GATE_DEFS`에 `cost_per_task`(direction "max") 추가 →
기존 `_check_gates`/exit-code 경로로 자동 흐름(초과 시 exit 1).

**SPEC-041 P27 (개선 실험 레지스트리)** — `agent-eval experiment {register,list,score}`
(`cli/experiment.py`, `cli/main.py` 위임) + `rca/experiments.py`(§rca/ 참고). "Gate A의
avg_subtask_completion이 +0.08 오를 것" 같은 반증 가능한 예측을 `.aoo/experiments.jsonl`에
append-only 등록 → 다음 run이 baseline을 주면 `score` 서브커맨드가 `verify_recommendation_outcome`로
predicted vs actual을 대조해 confirmed/partially_confirmed/refuted/inconclusive 판정,
`--persist`면 resolution 줄을 write back. `build_insights(current, baseline, *,
experiments_log_path=)` — open 가설을 in-memory로 score(쓰기 없음), resolved는 저장 verdict 그대로
→ `insights.experiments[]`. 리포트 `_build_experiments()` 섹션 `experiments`(hypothesis/predicted/
actual/verdict 표), `_rec_experiment_block`이 `.aoo/experiments.jsonl`에 같은 gate/field의
confirmed 과거 outcome ≥2개면 heuristic 예측 Δ를 `recalibrated_delta()`로 재보정 + 명령을
`agent-eval experiment register`로 변경. 소비처(모두 파일 존재 시에만 경로 전달): `monitor.save_to_file`
(baseline 없음 → pending), `comprehensive_report` 두 진입점, `serve/routers/diagnose.py`.

**SPEC-041 P26 (케이스 회귀 게이트 + 알림)** — `agent-eval gate`에 옵트인 exit 4 체크 2개 +
`--notify` 추가. `cli/gate.py::_compute_gate_insights(data, args, baseline_path)` — full baseline
*result* JSON(`--baseline-result`, 없으면 `tasks[]`를 담은 `--baseline`/해석된 baseline 경로)으로
`build_insights(current, baseline_result)` 1회 계산(총 실패 시 None, baseline result 없으면 dict
안 `failure_lineage`만 None). `--fail-on-case-regression` → `failure_lineage.regressed`(baseline에선
통과했는데 지금 실패하는 task_id)가 비어있지 않으면 exit 4(baseline result 없으면 경고 후 스킵).
`--max-review-high N` → `review_queue.by_priority.high > N`이면 exit 4. 종료 코드 우선순위:
golden(3) > case/review(4) > regression(2) > gate fail/composite/threshold(1) > 0. `--notify TARGET`
(반복 가능) — 종료 코드 확정 후 `alerts.dispatch_gate_result(targets, insights, passed=, result_file=,
exit_code=)` 호출: `build_gate_result_message()`가 narrative + regressed + cohort winner를 조립,
`slack://`·`webhook://`(→`https://`, 빈 본문은 `$SLACK_WEBHOOK`/`$ALERT_WEBHOOK_URL`)·raw
http(s):// 를 핸들러로. 전송 실패는 stderr 보고만, 종료 코드 불변. `alerts/__init__.py`가
`dispatch_gate_result`/`build_gate_result_message` export.

**SPEC-041 P25 (스팬 타임라인·워터폴 트레이스)** — `reporting/insights.py::parse_span_timeline(items)`
신설(순수 함수) — 평면 스텝 리스트(`tool_calls`/`chain_steps`/`agent_interactions`)에 타이밍이 있으면
(`start_ms`/`end_ms` 절대값 **또는** 스텝별 `duration`/`duration_ms`/`latency_ms`) 중첩 타임라인으로 파싱:
`{n_spans, total_ms, spans[{idx,name,depth,start_ms,end_ms,self_ms,tokens,cost,ok}], critical_path,
bottleneck{name,self_ms}, total_cost_usd, total_tokens}`. `duration_ms`/`latency_ms`/`elapsed_ms`는
밀리초로 신뢰, bare `duration`/`latency`/`elapsed`만 초로 보고 ×1000. `depth`는 `id`/`parent` 체인,
없으면 전부 0(평면). `self_ms` = 자기 구간 − 자식 구간 합. `critical_path` = self_ms 내림차순으로 total의
80%를 채우는 스팬들. 타이밍이 하나도 없으면 `None`. `_trajectories_section(tasks, limit=8)` — worst-N
실패 태스크(없으면 전체)에서 `tool_calls`→`chain_steps`→`agent_interactions` 순으로 첫 타임라인만
`{task_id, source, n_spans, total_ms, critical_path, bottleneck, total_cost_usd, total_tokens}`.
`insights.trajectories`(타이밍 없으면 None). 리포트 `_build_waterfall(items)` — `_build_trajectory`의
`<details>` 안 평면 표 **위에** 인라인 SVG 워터폴(start_ms로 배치, duration으로 너비, critical-path
스팬은 진한 남색, 실패는 빨강, depth 들여쓰기, 스팬별 self_ms/tok/$ 라벨 + 헤더에 total·bottleneck).
타이밍 없으면 워터폴 생략하고 기존 평면 표만(회귀 없음). 대시보드는 트레이스가 리포트 전용이라 스킵.

**SPEC-041 P23 (태스크별 점수 분해)** — `core/trackers/layer1.py::AccuracyEvaluator.decompose_qa(gt, pred)`
신설 — QA 정확도 뒤의 4개 신호 `{token_overlap_f1, jaccard, lcs_ratio, char_sim, weighted, weakest}`
(새 채점 없음, `_qa_accuracy`가 이제 이걸 호출). `reporting/insights.py::_score_breakdowns_section(tasks)` —
worst-N 실패 태스크별 `{accuracy, accuracy_components, accuracy_weakest / accuracy_note(code/tool_use),
judge_overall, judge_reasoning, judge_dimensions, weakest_signal(accuracy 신호 + judge dim÷5 통합 최저)}`.
`insights.score_breakdowns`. 리포트 `_build_score_breakdown_detail` — Worst-cases 표 각 행에 `▸ Score
breakdown` `<details>`(4개 신호 + judge rationale, 최저 신호 빨강). 대시보드 Improve 탭 패널.

**SPEC-041 P22 (N-버전 코호트 비교)** — `utils/confidence.py::welch_t_p(a, b)` — stdlib Welch t-검정
정규근사 p-value(scipy 무의존). `reporting/insights.py::_cohort_comparison_section(labelled, metric)` —
`quick_eval._benjamini_hochberg` + `bootstrap_diff_ci` 재사용: per-version {label(lineage.agent_version/
prompt_version), n, tcr_pct, gate_scores} · 모든 unordered 쌍의 delta/p/FDR-보정 p/CI · task_type별 승자 ·
overall winner(최고 TCR이고 2위 대비 리드가 FDR 유의하면 지목, 아니면 "not significant — collect more
tasks"). `build_insights(current, *, cohort=[dict,…], cohort_metric="tcr")` — 비교 집합 = `[current]+cohort`,
라벨 중복은 `#2` 접미. `insights.cohort_comparison`(cohort 미지정 시 None). 리포트 `_build_cohort_comparison`
섹션 `cohort-comparison`(version 표 + task_type 표 + pairwise FDR 표 + 승자), `generate_*` 두 진입점에
`cohort` 인자. serve `/api/diagnose/{id}?cohort_ids=a,b,c`, 대시보드 Improve 탭 multi-select + 패널.
