# SPEC-044: HTML 리포트를 품질 평가 + 하네스 방법론 구동 도구로 (Draft)

- **Phase**: P13
- **상태**: ✅ **전 REQ 완전 구현 + 예시 리포트 감사 1라운드 (2026-09-09)** — REQ-8·1·2·3·4·5·6·7 전부(REQ-6 잔여분 다크 테마·diff 모드·실패표 필터 포함). 원칙: **리포트에 새 Gate 채점 공식·새 verdict 없음(원칙 3), 전 추가 기능 옵트인, 결과 JSON 바이트 동일성 유지, self-contained·외부 의존 0.** 커밋 안 함.
  - **감사 라운드 1 (2026-09-09)**: rich(baseline+회귀+실험+targets+decision-log+history)·thin(첫 실행)·ready(전 pass) 3 시나리오를 생성해 섹션 간 모순·카운트 버그 점검. **수정 2건**: ① `_wrap_evidence_group`의 `<summary>` 배지가 "⚠5 · ✗4" 같은 **숫자**였는데 — 실패 게이트가 섹션헤더 `badge-fail`와 h2 `>FAIL</span>`로 이중 계상되고, 우선순위 라벨 `badge-warn">LOW`가 경고로 오계상 — **presence 마커("⚠ needs review" / "✗ needs review")**로 교체(숫자 제거). 신호 감지는 `>FAIL</span>`·`ibox fail"`·`rc-verdict fail`(fail), `>WARN</span>`·`ibox warn"`(warn)만 — `badge-fail/warn`(라벨용) 제외. `evgrp-failure`는 존재만으로 auto-open("이건 실패들"). ② `_build_history_chart` 라벨이 bare index("0/1/2")였음 → `scan_history`의 `file`(basename)/`timestamp`로 교체("run0/run1/run2"). **확인 clean(수정 후 0 finding)**: 판정층이 모든 증거 그룹 앞 · `next-action` not_ready→apply-verify + user targets 인용 · `regression-check` FAIL + `--fail-on-case-regression` · `lifecycle-spine` primary=development(baseline+실험) & missing[]=[] · `proof-panel` 등록 실험을 예측 vs 실측(refuted)로 표시 · `design-contract` "3 of 7 measured" + 미측정 Gate Config 힌트 · evgrp 카운트=본문 top-level 섹션 수 일치 · TOC 앵커 전부 해결 · 중복 렌더 0. 감사 회귀 테스트 4건(`TestAuditRegressions`).
  - **REQ-8 ✅**: `comprehensive_report._assemble_report_body(ctx)` 신설 — 두 진입점(`generate_comprehensive_html_report` / `generate_html_from_result_file`)이 공유하던 ~65줄 near-duplicate `parts` 리스트를 하나로. 두 곳은 `ctx` dict(사전 계산값) + `gate_e_html`(monitor/rf 분기)만 만들어 넘김. `_TOC_LABELS`에 신규 id. `Docs/09_OUTPUTS.md` §4에 3계층 구조 설명 + "정본은 `_assemble_report_body`" 명시.
  - **REQ-1 ✅**: 3계층 — 판정층(header+fault badge → narrative/audit/freshness → exec-summary → `next-action` → `spec-frontmatter` → `regression-check` → readiness → scorecard → briefs) · 이터레이션층(`lifecycle-spine` → `proof-panel`) · 증거층(6 `<details class="evidence-group">` = `evgrp-{gates,failure,evalset,stats,version,governance}`; Gate fail/warn 신호(또는 `evgrp-failure`) 있으면 auto-`open` + `<summary>`에 "N section(s)" + presence 마커("⚠/✗ needs review" — 감사 라운드 1에서 숫자 배지→마커; 이중·오계상 방지); 빈 그룹 미렌더). `@media print`가 전 `<details>` 강제 펼침. RCA `diagnosis`를 governance 그룹의 recommendations 바로 뒤로(회귀 원인이 아니라 "무엇을 할지" 재료).
  - **REQ-2 ✅**: `insights._lifecycle_phase_section` → `insights.lifecycle_phase{primary ∈ analysis·design·development·verification·operations, order, signals[], missing[], note}`. baseline+열린실험→development / baseline(+≥3 형제run)→verification / targets만→design / decision-log→operations / 그외→analysis. partial 모드는 analysis 고정. schema + `test_insights_schema.py` 시나리오. `_build_lifecycle_spine`가 스트립 + signals + "Not in this report"(nested `<details>`) 렌더.
  - **REQ-3 ✅**: `_build_next_action(insights, harness_groups)` — `verdict.level`+`decision_ready`에서 단 하나의 다음 행동 + 복붙 CLI: ready→`agent-eval decisions record --outcome accepted ...` / decision_ready=false→`run_repeated(eval_fn, 5)` + "exit 75" 안내 / not_ready→`agent-eval improve apply-verify <result>.json --proposal <failing gate> --eval-cmd '...'`. targets 출처(user `.aoo/targets.json` vs builtin 0.7) 한 줄. 임계값 재계산 없음.
  - **REQ-5 ✅ (부분)**: `_build_proof_panel`(열린/채점된 experiment의 예측 vs 실측 표 + `improvement_priors` 트랙레코드 한 줄, 없으면 `improve start` 넛지) · `_build_regression_check`(case-regression + `eval_set_delta` ±1pp를 한 블록 + 단일 PASS/FAIL + 정확한 `--fail-on-case-regression` 플래그; baseline 없으면 회색) · `_build_fault_injection_banner`(`lineage.fault_injection` → 헤더 아래 "Gate C/D는 주입 조건 하 점수" 배지). 이터레이션 표식은 별도 헤더 대신 `lifecycle_phase.missing`로 흡수.
  - **REQ-6 ✅ (전체)**: `_build_report_js(*, has_baseline)` — 라이브러리 0, 인라인 `<script>` 1개. **핵심**: `pre.cmd[data-cmd]` 복사 버튼(`navigator.clipboard`→`execCommand` 폴백→숨김) · 증거 그룹 "Expand all / Collapse all" · hash/TOC 클릭 시 포함 `<details>` 자동 open + `scrollIntoView` · `IntersectionObserver`로 exec-summary 벗어나면 하단 고정 미니 판정바 · `prefers-reduced-motion` 존중. **잔여분**: ① 라이트/다크 토글 — JS-주입 `.report-controls` 버튼이 `<html>`에 `data-theme="dark"` 스탬프(세션 DOM만·저장X), CSS는 `prefers-color-scheme` 의존 없이 **명시적 `:root[data-theme="dark"]` 오버라이드**(구조 표면 ~38룰). `_build_toc` 인라인 스타일 → `.report-toc` 클래스로 이관. ② diff 모드 토글(baseline 있을 때만) — `_wrap_evidence_group(has_change=)`가 `evgrp-version`·`evgrp-failure`에 `data-has-change="1"`, `body.diff-mode ...:not([data-has-change]){display:none}`. ③ 실패표 텍스트 필터 — `#failure-cases` 표 위 JS-주입 `<input>`, `tr.textContent` 부분일치(colspan expando 행 동반). 스크립트 제거해도 전문 판독 가능.
  - **REQ-4 ✅**: `_build_spec_frontmatter`(판정층 — 요구사항 미커버 ID + `--require-spec-coverage` 안내 + acceptance "N of M met") + `_build_design_contract(harness_groups, insights, lineage)`(증거층 evgrp-evalset 상단 — 측정된 Gate(score≠None)/status/`_GATE_CONFIGS`에서 `lineage.config_snapshot` 키와 매칭한 Config vs 미측정 Gate + "set one of: …" Config 힌트; `insights.newly_unmeasured_gates`는 "⚠ was measured in the baseline"으로 표기; config_snapshot 없으면 "config not recorded" + `PerformanceMonitor(config_snapshot=...)` 안내). `ctx["lineage"]` = `_ins_input.extra_metrics.lineage` 배선.
  - **REQ-7 ✅**: `report_markdown_summary(insights, *, result_file=, exit_code=)` 신설(`comprehensive_report.py`) — `verdict`+`readiness`+`_next_action`(REQ-3 로직을 공유 헬퍼로 추출)에서 `## Gate verdict` / Decision / Bottleneck / Confidence / `### Next`(코드펜스 명령) / `### Path to green`(fix_plan top4) 마크다운. `agent-eval gate <result>.json --html-out PATH`(gate 로직 후 `generate_html_from_result_file`로 그 경로에 씀; baseline은 `tasks` 있는 결과 JSON만 전달) · `--html-summary`(마크다운을 stdout에). 둘 다 `getattr` 기본값이라 미지정 시 gate 출력·exit code 바이트 동일. `_build_history_chart(results_dir, current_file)` — `scan_history`로 형제 run per-Gate score 시계열을 `<script type="application/json" id="ae-history-data">` + `<canvas id="ae-history-canvas">`에 임베드(`< 3 runs`면 미렌더), `_build_report_js`의 `drawHistory()`가 라이브러리 0으로 멀티라인 차트 렌더. `_build_history_trend`(sparkline) 안에 이어 붙임.
  - 전체 5217 passed(신규 `test_spec044_report_instrument.py` 48건), ruff 1037·mypy 204(0 new). `_build_next_action`을 `_next_action(insights) -> dict|None` 순수 헬퍼 + HTML 래퍼로 분리(REQ-3/7 공유).
- **의존성**: SPEC-041 완료(`build_insights()` / `reporting/comprehensive_report.py`의 `_build_*` 헬퍼 ~70개) · SPEC-042 완료(`acceptance_criteria` · `decision_ready` · exit 75 · `run_repeated`) · SPEC-043 완료(`spec_coverage` · `deploy_decision` · `eval_set_delta` · `fault_injection` · `improve apply-verify`)
- **검증 기준일**: 2026-09-09. 아래 Context의 "없음"·`파일:라인` 판정은 이 날짜에 코드를 직접 대조해 확인했다.

---

## 0. 문제 정의

`reporting/comprehensive_report.py`는 `_build_*` 헬퍼 ~70개를 **선형으로 이어 붙인 ~65섹션 정적 HTML**이다(`<script>` 0개, `<details>` 2곳). `Docs/09_OUTPUTS.md` §1이 이미 "Every Agent-Evaluator output exists to **deliver the evaluation result and drive improvement**"라고 의도를 못 박았지만, 리포트 자체는 그 의도를 구조로 구현하지 못했다:

- **품질 평가 도구로서**: 폴드 위 8섹션(narrative→verdict→freshness→insight-changes→briefs→narrative-audit→path-to-green→scorecard)이 이미 L4–L6 판정을 담아 강하다. 문제는 그 뒤로 **50+섹션이 등급·그룹·목적 구분 없이 쏟아진다**. 90%는 상단만 읽는다.
- **방법론 구동 도구로서**: recommendations에 복붙 스니펫·`experiment register` 명령이 있고 `improve`/`experiments`/`change-ledger` 섹션도 있지만 — ① 이 실행이 분석/설계/개발/검증/운영 중 어디인지 프레이밍이 없고 ② exit code(0/1/2/4/75)와 "다음 명령"이 연결돼 있지 않으며 ③ 복사 버튼·필터·접기가 없어(정적) 스캔·조작이 안 되고 ④ `spec_coverage`(분석①), `deploy_decision`(운영), TDD-AI "증명" 재료가 뒷부분에 흩어져 있다.
- **v1.0.0 이후 추가분**(SPEC-042/043)이 전부 선형 리스트 **중간**에 삽입돼 묻혔다: `spec_coverage`(security 뒤), `deploy_decision`·`eval_set_delta`·verdict-stability(중간), `lineage.fault_injection` 배지 없음(결과 오독 위험).

리포트는 **내용은 완비, 도구화가 미완**이다. 이 스펙은 새 판단을 추가하지 않고 — **재배치 · 3계층 그룹화 · 라이프사이클 프레이밍 · 인라인 상호작용**으로 도구화한다.

---

## 1. Goals

1. **품질 평가**: 폴드 위 한 화면에서 "지금 배포 가능한가 · 얼마나 확신 · 다음 결정"이 끝난다.
2. **방법론 구동**: 리포트가 exit code·insights를 근거로 **하나의 다음 행동(복붙 CLI 포함)**을 제시하고, 이 실행이 하네스 라이프사이클의 어느 단계인지 명시한다.
3. **스캔·조작 가능**: 정적 HTML을 유지하되 접이식 그룹·복사 버튼·실패표 필터·diff 모드를 인라인 vanilla JS로 얹는다.
4. **v1.0.0 이후 추가분을 제자리에**: 분석①/설계/증명/거버넌스 재료를 목적 그룹으로 옮긴다.
5. **정합**: `Docs/09_OUTPUTS.md`를 코드와 재동기화하고, 섹션 순서·그룹을 상수화한다.

## 2. Non-Goals

- **리포트에 새 verdict/채점 로직** — 판단은 전부 `build_insights` / `harness_groups`에 유지. 리포트는 재배치·그룹화·프레이밍·복사 버튼만. (원칙 3: 리포트는 채점 채널.)
- **외부 의존 / CDN / 빌드 스텝** — JS는 전부 인라인 vanilla(라이브러리 0), 리포트는 단일 self-contained `.html` 유지.
- **서버 렌더링 · 백엔드 상태 · 저장** — 리포트는 여전히 열면 끝나는 정적 파일. 클라이언트 상태(펼침/필터)는 세션 내 DOM만, 저장 안 함.
- **대시보드 완전 대체** — 대시보드 존폐는 별도 결정. 이 스펙은 "대시보드가 축소돼도 리포트가 그 자리를 감당"할 수 있게 종단 히스토리·스트리밍 스냅샷 흡수분만 다룬다.
- **`schema_version` bump** — `insights`에 추가되는 것은 파생·nullable 키 하나(`lifecycle_phase`)뿐, `additionalProperties:true`라 minor.

## 3. Requirements

### REQ-8 — 섹션 순서·그룹 상수화 + 문서 재동기화 (기반 리팩터)

- **Context**: `comprehensive_report.py`의 `parts = [...]` 리스트(라인 ~6874, ~7204)가 섹션 순서를 하드코딩하고, `_TOC_LABELS` dict가 라벨을 따로 든다. `Docs/09_OUTPUTS.md` §4의 섹션 순서표는 SPEC-042/043 추가분(`spec_coverage`·`deploy_decision`·`eval_set_delta`·verdict-stability) 반영 전이라 코드와 어긋난다.
- **변경**:
  - `comprehensive_report.py`에 `_REPORT_LAYOUT` 상수 하나 — `[(group_id, group_label, [(_build_fn_ref, section_id), ...]), ...]` 형태로 계층/그룹/순서를 한곳에 선언. `parts` 조립을 이 상수 순회로 대체. `generate_comprehensive_html_report`와 `generate_html_from_result_file` 두 경로가 같은 상수를 쓴다(현재 두 곳에 순서가 중복).
  - `_TOC_LABELS`를 `_REPORT_LAYOUT`에서 파생(라벨 중복 제거).
  - `Docs/09_OUTPUTS.md` §4를 `_REPORT_LAYOUT`과 일치하게 재작성. doc 상단에 "이 표는 `comprehensive_report._REPORT_LAYOUT`이 정본" 명시.
- **Acceptance**: 리팩터 전후 생성 HTML의 섹션 `id` 집합·순서 동일(순수 리팩터). `Docs/09_OUTPUTS.md` §4의 모든 섹션이 코드에 존재하고 그 역도 성립.
- **규모**: 소.

### REQ-1 — 3계층 정보구조 + 접이식 증거 그룹 (IA)

- **Context**: 65섹션 선형. 판정·진단·증거가 섞여 있고 등급별 접기가 없다.
- **변경** — `_REPORT_LAYOUT`(REQ-8)을 3계층으로 재편:
  - **판정층** (항상 펼침, 폴드 위): `narrative` → `narrative_audit` → `freshness` → `executive_summary`(+exit code·`decision_ready`) → **`_build_next_action`(REQ-3)** → **`_build_spec_frontmatter`(REQ-4)** → **`_build_regression_check`(REQ-5)** → `deploy_decision` 상태 한 줄 → `readiness`(path-to-green) → `scorecard` → `briefs`.
  - **이번 이터레이션층** (펼침): **`_build_lifecycle_spine`(REQ-2)** → **`_build_proof_panel`(REQ-5)** → `failure_clusters`(top 1) → `contrast_pairs`(1) → `ablation_hints`(바꿀 한 줄) → `recommendations`(top 1) → `insight_changes`(있으면 "이터레이션 N" 헤더, REQ-5).
  - **증거층** (`<details>` 6그룹, 기본 접힘, 그룹 안에 fail/warn 신호 있으면 자동 펼침 + `<summary>`에 "N개 섹션 · ⚠ 2 · ✗ 1" 배지):
    - **Gate 상세**: `scorecard` breakdown, `gate-a`…`gate-g`, `advanced`, `multiagent`, `conversation`
    - **실패 분석**: `failure-cases`(전체), `failure-taxonomy`, `failure-segments`, `failure-explanations`, `rag-localization`, `contrast-pairs`(전체), `ablation-hints`(전체)
    - **평가셋 품질**: `spec-coverage`(전체), `acceptance-coverage`, `eval-set-quality`, `golden-health`, `eval-representativeness`, `slice-analysis`, `metadata-slices`
    - **통계 엄밀성**: `metric-ci`, `sample-guidance`, `multiplicity-audit`, `uncertainty-budget`, `calibration`, `threshold-sensitivity`, `metric-signal`, `judge-robustness`, `evaluator-reliability`, `nondeterminism`, `verdict-stability`, `reference-frame`
    - **버전·종단**: `cohort-comparison`, `trace-diffs`, `change-attribution`, `regression-attribution`, `eval-set-delta`, `history-trend`, `longitudinal`, `diagnosis`
    - **거버넌스·트랙레코드**: `deploy-decision`(전체), `experiments`, `improvement-priors`, `change-ledger`, `reproducibility`, `recommendations`(전체), `operational-signals`, `security-findings`, `efficiency-opportunities`, `latency-budget`, `cost-economics`
  - 빈 섹션(`""`)이 든 그룹은 그 섹션만 빠지고, 그룹 전체가 비면 그룹 `<details>` 자체를 렌더 안 함.
  - `@media print { details { display:block } details > summary { list-style:none } details:not([open]) > *:not(summary) { display:block } }` — 인쇄 시 전부 펼침.
- **Acceptance**: 폴드 위(판정층)에 등장하는 섹션 수 ≤ 12. 증거층 그룹은 기본 접힘, fail/warn 신호가 있는 그룹만 `open`. baseline·experiments·decision-log가 모두 없는 얇은 결과 JSON에서도 판정층은 정상 렌더되고 "이 리포트에 없는 것" 안내(REQ-2 note)가 뜬다.
- **규모**: 중.

### REQ-3 — "다음 결정 / 다음 명령" 카드 (원칙 6·2)

- **Context**: exec-summary가 "Not deployment-ready / Deploy with caution / Deployment-ready"를 말하고 Next actions 1·2·3을 주지만, exit code(특히 SPEC-042 exit 75)와 **지금 실행할 정확한 명령**이 연결돼 있지 않다.
- **변경** — `_build_next_action(insights, harness_groups, exit_code_hint)` 신설(판정층):
  - `insights.verdict.level` + `decision_ready` + (있으면) `deploy_decision`에서 상태를 도출해 **단 하나**의 다음 행동 + 복붙 CLI 블록:
    - ready + `decision_ready` → `agent-eval decisions record --outcome accepted --by <name> --decision-log .aoo/decisions.jsonl` ("결정을 원장에 남기세요")
    - `decision_ready == false` (borderline / knife-edge) → "사람 보류. Wilson CI가 TCR 목표를 걸침. 반복 안정성 확인: `run_repeated(eval_fn, k=5)` 또는 태스크 +N개(sample_guidance의 N)."
    - not_ready → 차단 Gate X + "격리 worktree에서 자동 검증: `agent-eval improve apply-verify <result>.json --proposal <X> --eval-cmd '<your eval>'`" (proposal이 `recommendations`에 있으면 그 gate/kind를, 없으면 최저 Gate를).
  - `exit_code_hint`는 호출자(있으면)가 전달, 없으면 `verdict.level`에서 추정. `_build_executive_summary`가 이미 계산하는 verdict을 재사용 — 새 판단 없음.
  - 카드에 "이 판정은 `.aoo/targets.json` 기준(TCR ≥ 90, Gate A ≥ 0.85)" 같은 targets 출처를 한 줄로(있을 때).
- **Acceptance**: 세 verdict 상태 각각에서 정확히 하나의 카드가, 해당 상태에 맞는 CLI 한 줄과 함께 렌더. targets 미설정 시 "기본 임계값 0.7" 표기.
- **규모**: 소.

### REQ-4 — Spec-Driven 프론트매터 + 설계 계약 패널 (원칙 1)

- **Context**: `spec_coverage`(SPEC-043 R1)는 분석①(요구사항) 신호인데 리포트 중간(security 뒤)에 있다. "스펙이 요구하는 Gate를 이 평가가 실제로 측정했는가"(설계 갭)를 보여주는 곳이 없다.
- **변경**:
  - `_build_spec_frontmatter(insights)` 신설(판정층): `spec_coverage`가 있으면 "요구사항 M건 중 K건은 재는 골든 케이스 없음: REQ-004, REQ-008" + `acceptance_coverage` "N of M met" 롤업 한 줄. covers_only 모드(요구사항 목록 없음)면 "선언된 요구사항 커버 P건 (전체 목록 미제공 — `--requirements`로 갭 확인)". `--require-spec-coverage`가 이걸 exit 4로 잡는다는 안내.
  - `_build_design_contract(harness_groups, lineage)` 신설(증거층 "평가셋 품질" 그룹 상단): 측정된 Gate(score≠None) vs 미측정 Gate 표 + 각 Gate에 붙은 Config(`lineage.config_snapshot`의 키에서 유추, 없으면 "config 미기록"). "Gate D 미측정 — SLAConfig/EfficiencyConfig 미설정" 같은 갭을 명시. `newly_unmeasured_gates`(baseline엔 있었는데 사라진 Gate)를 여기로 합침.
- **Acceptance**: `spec_coverage == null`이면 프론트매터 미렌더. 미측정 Gate가 있으면 design-contract 표에 그 Gate가 "⚙️ Not configured"로, baseline에서 측정됐다 사라졌으면 "⚠️ was measured in baseline"으로.
- **규모**: 중.

### REQ-5 — TDD-AI 증명 패널 · 회귀 체크 단일 판정 · 이터레이션 표식 · 결함주입 배지 (원칙 2)

- **Context**: "통과보다 증명"의 재료(`experiments` 예측/실측, `improvement_priors` 트랙레코드, `eval_set_delta`·case/golden regression, `insight_changes`, `lineage.fault_injection`)가 흩어져 있거나 배지가 없다.
- **변경**:
  - `_build_proof_panel(insights)` 신설(이터레이션층): `.aoo/experiments.jsonl`에 이 프로젝트 열린/방금 채점된 실험이 있으면 "가설: Gate A `avg_subtask_completion` +0.08 예측(SubtaskConfig 추가) → 이번 실행 실측 +0.06 → **부분 확인**" + `improvement_priors` 한 줄("config change on Gate A: 3/4 confirmed, mean Δ+0.05"). 실험이 없으면 "가설을 먼저 등록: `agent-eval improve start <result>.json --yes`" 넛지. `experiments`·`improvement_priors` 섹션 자체는 증거층에 그대로 남김(패널은 요약+링크).
  - `_build_regression_check(insights)` 신설(판정층): `failure_lineage.regressed`(case regression), golden regression(있으면), `eval_set_delta`, `cohort_comparison`를 하나의 블록 + **단일 PASS/FAIL** + "CI에서 잡으려면: `agent-eval gate <result>.json --baseline-result <prev>.json --fail-on-case-regression`"(해당 신호에 맞는 정확한 플래그). baseline 없으면 "회귀 체크: baseline 미제공" 회색 표기.
  - `_build_iteration_marker(insights)` — `insight_changes`가 있으면 이터레이션층 헤더에 "이 fix의 이터레이션 N — 이전 리포트 대비 인사이트 diff ↓"(N은 `longitudinal`/history의 형제 run 수에서 유추, 불가하면 "이전 대비"). `insight_changes` 섹션은 증거층에 유지.
  - 헤더(`_build_header`)에 `lineage.fault_injection` 있으면 배지: "⚠ FAULT-INJECTED — seed=1, fail_tools=[api]. Gate C/D는 주입 조건 하 점수".
- **Acceptance**: 열린 실험이 있으면 proof panel이 예측·실측·verdict을 표시하고, 없으면 넛지만. `eval_set_delta`/case regression 중 하나라도 있으면 regression-check가 FAIL + 정확한 `--fail-on-*` 플래그. `lineage.fault_injection` 없으면 배지 미표시(바이트 동일).
- **규모**: 중.

### REQ-6 — 인라인 vanilla JS 상호작용 레이어

- **Context**: 리포트에 `<script>`가 0개. 스캔·조작(접기·복사·필터)이 불가능하다.
- **변경** — `_build_report_js()` 신설(라이브러리 0, ~180줄 이하, 리포트 끝 `<script>`에 인라인):
  - 접이식 그룹 토글 + "전체 펼침 / 접힘" 버튼(판정층 상단).
  - 스크롤 시 상단 고정 미니 판정바 — Gate A–G 배지 + "다음 명령" 축약. `IntersectionObserver`로 판정층이 뷰포트를 벗어나면 표시(뷰 진입 시 숨김 — 첫 프레임엔 안 보임).
  - 모든 제안 CLI 줄(`<pre data-copy>` 또는 `.cmd`)에 복사 버튼. `navigator.clipboard` 실패 시 `execCommand` 폴백, 둘 다 실패면 버튼 숨김.
  - 실패 표(`failure-cases`) 클라이언트 필터 — 클러스터 / taxonomy 코드 / slice / Gate 드롭다운(값은 렌더 시 표의 `data-*`에서 수집).
  - 라이트/다크 토글(현재 `prefers-color-scheme`만) — `data-theme` 스탬프, 세션 내 DOM만(저장 안 함).
  - diff 모드 토글(baseline 있을 때만) — `insight_changes`가 "변경 없음"으로 분류한 섹션 `id`를 `data-unchanged`로 표시해 두고 숨김.
  - `@media (prefers-reduced-motion: reduce)` 존중 — 애니메이션 없음, 미니바는 즉시 표시.
  - JS 없이도(스크립트 차단 환경) 리포트는 전부 읽힌다 — `<details>`는 기본 `open` 아니면 접힘이지만 인쇄 CSS로 펼쳐지고, 필터/복사만 비활성.
- **Acceptance**: JS 삽입 후에도 리포트는 단일 파일·외부 요청 0. 스크립트를 지워도 모든 텍스트가 읽힌다. 복사 버튼이 실제 CLI 문자열을 클립보드에 넣는다(수동 확인 1회).
- **규모**: 중.

### REQ-2 — 라이프사이클 스파인 배지 + `insights.lifecycle_phase` (방법론 전체)

- **Context**: 리포트가 모든 실행을 동일하게 취급한다. "이 리포트를 지금 왜 보는가"(개발 이터레이션? 회귀 체크포인트? 운영 기준선?)가 없다.
- **변경**:
  - `insights.py`에 `_lifecycle_phase_section(current, baseline, experiments_log_path, recommendation_log_path, targets, decision_log_path)` — 입력 신호로 `{primary: "analysis"|"design"|"development"|"verification"|"operations", signals: [...], missing: [...], note: str}` 도출:
    - baseline 있음 + 열린 실험 → `development`
    - baseline 있음 + (regression 신호 or history ≥ 3 runs) → `verification`
    - baseline 없음 + targets 설정 → `design`
    - decision_log 존재 + outcome 기록 → `operations`
    - 그 외(첫 실행) → `analysis`
    - `missing`: 이 리포트에 없는 재료와 이유("baseline 미제공 → 회귀 섹션 없음", "experiments.jsonl 없음 → 증명 패널 넛지만", "targets 미설정 → 임계값 0.7").
  - `build_insights`에 `experiments_log_path`/`recommendation_log_path`/`decision_log_path`는 이미 kwarg. `_lifecycle_phase_section`을 `out["lifecycle_phase"]`로 배선(never raises, 실패 시 omit). partial 모드는 `analysis` 고정.
  - `_build_lifecycle_spine(insights)` — 상단에 분석①→분석②→설계→개발→검증→운영 스트립, `primary` 하이라이트, 각 단계가 관련 그룹 `id`로 점프. `missing` 목록을 그 아래 회색 note로("이 리포트에 없는 것: …").
  - `insights.schema.json`에 `lifecycle_phase` 객체 추가(`["object","null"]`, `additionalProperties:true`). `tests/test_insights_schema.py` 시나리오 1건.
- **Acceptance**: 첫 실행(baseline·targets·log 전무) → `primary == "analysis"`, `missing`에 3항목. baseline + 열린 실험 → `development`. `lifecycle_phase == null`이면 스파인 미렌더(리포트는 정상).
- **규모**: 소~중.

### REQ-7 — 배포: `--html-summary` · `--html-out` · 종단 흡수분

- **Context**: HTML은 `save_to_file()` 시점에만 생성. `agent-eval gate`는 결과 JSON만 받아 터미널 표를 낸다 — PR·Slack에 붙일 짧은 형태가 없다. 대시보드가 축소되면 종단 히스토리 브라우징이 사라진다.
- **변경**:
  - `agent-eval gate <result>.json --html-out report.html` — gate가 `generate_html_from_result_file`로 리포트를 그 경로에 쓴다(baseline·cohort 인자 재사용). 미지정 시 동작 불변.
  - `agent-eval gate --html-summary` — 판정 + path-to-green 헤드라인 + "다음 명령"(REQ-3)을 **짧은 마크다운 블록**으로 stdout에. `--notify` payload에도 포함(현재 서술+회귀+코호트 승자에 이어). PR 설명에 붙여넣기용. HTML 전문 경로가 있으면 링크 한 줄.
  - `_build_history_chart(results_dir, current_file)` — `_build_history_trend`(인라인 sparkline) 옆에, 형제 run들의 per-Gate 시계열을 작은 **클라이언트 사이드 Canvas 차트**로(라이브러리 0, `_build_report_js`가 그림). 대시보드 "history" 탭의 최소 대체. 데이터는 렌더 시 `<script type="application/json">`에 임베드.
- **Acceptance**: `--html-out` 지정 → 그 경로에 유효한 self-contained HTML. `--html-summary` → 파싱 가능한 마크다운(제목·불릿·코드펜스). 둘 다 미지정 → `gate` 출력 바이트 동일.
- **규모**: 소~중.

## 4. Interface 변경 요약 (전부 하위호환)

| 대상 | 추가 | 기본값에서의 동작 |
|---|---|---|
| `reporting/comprehensive_report.py` | `_REPORT_LAYOUT` 상수 · 3계층 조립 · `_build_report_js` · `_build_next_action` · `_build_spec_frontmatter` · `_build_design_contract` · `_build_proof_panel` · `_build_regression_check` · `_build_iteration_marker` · `_build_lifecycle_spine` · `_build_history_chart` | HTML 구조·JS가 바뀜(리포트는 `schema_version` 대상 아님). 콘텐츠 판단은 불변 |
| `insights` | `lifecycle_phase` (파생, nullable) | 입력 신호 없으면 `analysis` / partial은 `analysis` 고정 |
| `insights.schema.json` | `lifecycle_phase` 정의 | `additionalProperties:true`라 non-breaking |
| `agent-eval gate` | `--html-out PATH` · `--html-summary` | 미지정 → stdout·exit code 바이트 동일 |
| `Docs/09_OUTPUTS.md` §4 | `_REPORT_LAYOUT`과 일치하게 재작성 | 문서만 |

## 5. Compatibility

- 리포트에 새 verdict·채점 없음 — `build_insights` / `harness_groups` 판단 그대로. **리포트 HTML은 `schema_version` 대상이 아니므로** 구조 재편이 호환성 계약을 깨지 않는다. 단 **예시 리포트 감사**(P35 스타일 — 섹션 재배치는 섹션 간 모순·카운트 버그 이력)를 각 REQ 후 1라운드.
- `insights.lifecycle_phase`는 파생·nullable·`additionalProperties:true` → `schema_version "1.1"` 유지. SPEC-041 §"Adding an insight section" 5단계 준수(섹션 함수 순수·never raises·스키마·테스트·리포트 렌더).
- 결과 JSON 바이트 동일성: `lifecycle_phase`가 `extra_metrics.insights`에 추가되지만 이는 SPEC-041 이래 매 스펙이 하는 것과 동일(옵트인 입력 없으면 `analysis` + `missing`만). 옵트인 미사용 시 그 외 필드 불변.
- `--html-out`/`--html-summary` 미지정 시 `gate` 동작 100% 불변.

## 6. Rollout (권장 순서)

**REQ-8 → REQ-1 → REQ-3 → REQ-4 → REQ-5 → REQ-6 → REQ-2 → REQ-7**

1. **기반**: REQ-8(상수화·doc 동기화) — 순수 리팩터, 생성 HTML 불변이 acceptance.
2. **구조**: REQ-1(3계층 + 접이식 그룹) — `_REPORT_LAYOUT`을 3계층으로 재편.
3. **판정층 콘텐츠**: REQ-3(다음 명령), REQ-4(spec 프론트매터·설계 계약).
4. **증명**: REQ-5(proof panel·회귀 체크·이터레이션 표식·결함 배지).
5. **상호작용**: REQ-6(vanilla JS — 접기·복사·필터·미니바·diff·테마).
6. **프레이밍**: REQ-2(라이프사이클 스파인 + `insights.lifecycle_phase`).
7. **배포**: REQ-7(`--html-out`·`--html-summary`·종단 차트).

각 REQ: `pytest` 전체 통과 + `ruff`/`mypy` 신규 0(SPEC-021 래칫) + (콘텐츠 판단 미변경이므로) 옵트인 미사용 시 결과 JSON 바이트 동일 + 예시 리포트 감사 1라운드.

## 7. Risks

| 시나리오 | 완화 |
|---|---|
| 섹션 재배치가 섹션 간 카운트·모순 버그 유발(P35에서 반복 관측) | REQ-8로 순서를 상수 1곳에 모으고, 각 REQ 후 예시 리포트 감사. 콘텐츠 함수(`_build_gate_*` 등) 자체는 안 건드림 |
| 접이식 기본 접힘 → "리포트가 비어 보인다" | fail/warn 신호 있는 그룹만 자동 `open` + `<summary>`에 "N개 섹션 · ⚠k · ✗m" 배지 + 인쇄 CSS로 전부 펼침 + REQ-2 `missing` note |
| 인라인 JS가 self-contained·CSP 규약을 깬다 | 라이브러리 0, `<script>` 인라인만, 외부 요청 0. 스크립트 제거해도 전문 판독 가능이 acceptance |
| `lifecycle_phase` 추론이 틀림 | `signals` 배열로 근거 노출, `primary`는 조언. 틀려도 섹션 내용은 불변(프레이밍만) |
| `--html-out`이 대용량 결과에서 느림 | gate는 이미 `build_insights`를 부름(P26). HTML 생성은 그 위 얇은 렌더. 옵트인이므로 기본 경로 영향 0 |
| 리포트가 "새 판단"을 하는 것처럼 보임(원칙 3 위반 인상) | 모든 신규 `_build_*`가 `insights`/`harness_groups` 값을 **재표시**만. "다음 명령"도 `verdict.level`에서 파생, 임계값 재계산 없음 |

---

## 부록: 원칙 ↔ REQ 매핑

| Harness 원칙 | 강화하는 REQ | 리포트에서의 발현 |
|---|---|---|
| 1. 코드보다 결정이 먼저 | REQ-4 | spec-coverage 프론트매터 · 설계 계약(측정 Gate ↔ Config 갭) |
| 2. 통과보다 증명 | REQ-5, REQ-3 | proof panel(예측 vs 실측) · 회귀 체크 단일 판정 · 결함 주입 배지 |
| 3. 차단과 채점 분리 | (전체) | 리포트는 채점 채널 — 새 verdict 없음이 설계 제약 |
| 4. 이미 있는 걸 다시 만들지 않는다 | REQ-8, REQ-1 | `_build_*` 콘텐츠 함수 재사용, 순서·그룹만 상수화 |
| 6. 사람의 최종 책임 | REQ-3, REQ-7 | 다음 결정 카드(원장 기록 명령) · `--html-summary`로 결정 가시성 |
| 방법론 전체 | REQ-2 | 라이프사이클 스파인 — 이 실행이 분석/설계/개발/검증/운영 중 어디인지 |
| 사용성(전제) | REQ-6 | 접기·복사·필터·미니바 — 65섹션을 조작 가능하게 |
