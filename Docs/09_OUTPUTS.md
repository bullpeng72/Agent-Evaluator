# 출력 & 리포트 가이드

결과 JSON · HTML 리포트 · CLI · 대시보드 · AI 런타임 출력의 체계적 정리

**v1.0.0-rc4 | Python 3.8+**

---

## 목차

1. [출력의 3가지 대상과 6가지 정보 계층](#1-출력의-3가지-대상과-6가지-정보-계층)
2. [출력 표면 전체 지도](#2-출력-표면-전체-지도)
3. [결과 JSON (`save_to_file()`)](#3-결과-json-save_to_file)
4. [정적 HTML 리포트 — 단일 결과](#4-정적-html-리포트--단일-결과)
5. [비교 HTML 리포트](#5-비교-html-리포트)
6. [CLI 터미널 출력](#6-cli-터미널-출력)
7. [대시보드](#7-대시보드)
8. [AI 런타임 출력 (Claude 훅 · OpenCode 플러그인 · MCP)](#8-ai-런타임-출력-claude-훅--opencode-플러그인--mcp)
9. [정보 계층 × 표면 매트릭스](#9-정보-계층--표면-매트릭스)
10. [역할별 출력 워크플로우](#10-역할별-출력-워크플로우)

---

## 1. 출력의 3가지 대상과 6가지 정보 계층

Agent-Evaluator의 모든 출력은 **평가 결과를 전달하고 개선을 유도**하기 위해 존재한다. 출력을 볼 주체는 셋이다.

| 대상 | 무엇을 원하나 | 주 표면 |
|------|--------------|---------|
| **개발자** | "어느 태스크가 왜 실패했나 · 뭘 고치면 되나" | HTML 리포트 · `agent-eval diagnose` · 대시보드 |
| **품질관리자(QM)** | "배포해도 되나 · 지난 버전 대비 어떤가 · 리스크는" | HTML 리포트 상단 · `agent-eval gate` · 대시보드 · 비교 리포트 |
| **AI 런타임** (Claude Code · OpenCode 에이전트) | "지금 이 행동이 막혔다 · 대신 뭘 해야 하나" | LiveGuardrail 차단 메시지 · SessionEnd 요약 · MCP 도구 |

모든 표면은 아래 **6개 정보 계층** 중 일부를 노출한다. 계층이 높을수록 "판단"에 가깝고, 낮을수록 "원천 데이터"다.

| # | 계층 | 내용 | 정본 위치 |
|---|------|------|-----------|
| L1 | **원천 기록** | 태스크별 question/response/score/tool_calls/errors | 결과 JSON `tasks[]` |
| L2 | **집계 지표** | TCR · Accuracy · P95 · 토큰/비용 · 25 Native Tracker 통계. **95% 신뢰구간**(TCR/Accuracy) + 표본 적정성 | 결과 JSON `accuracy_metrics`/`efficiency_metrics` · `utils.confidence` |
| L3 | **Gate 점수** | Harness Gate A–G score(0–1) + status(pass/warn/fail) + 산식 컴포넌트. **점수 대표성 경고** + 표본 부족 경고 | 결과 JSON `extra_metrics.harness_groups` |
| L4 | **판정** | 임계값 통과/실패 · baseline 회귀 · 골든셋 회귀. **판정 확신도**(HIGH/MEDIUM/LOW) | `agent-eval gate` (exit code) · 리포트 Executive Summary |
| L5 | **진단(RCA)** | 어느 컴포넌트가 점수를 깎았나 · **실패 테마 군집화** · **baseline 대비 실패 집합 변화** · 과거 위반 이력 교차참조 · MAST 후보 | `rca.diagnose()` → `agent-eval diagnose` / 리포트 진단·실패 케이스 섹션 |
| L6 | **처방 & 인사이트** | 배포 준비도 한 줄 판정 · Next actions 1·2·3 · 컴포넌트별 구체 조치 · **붙여넣을 수 있는 코드 스니펫** · **실험 제안(예측 Δ + 표본)** · **과거에 통한 조치** | 리포트 Executive Summary / Recommendations · `recommend_fix` MCP |

> **원칙 (HOTL, Human on the Loop)**: L5·L6은 후보 원인과 조치만 제시한다. "이게 원인이다"·"이렇게 하면 통과한다"를 단정하지 않는다 — 최종 판단은 사람의 몫이다.

---

## 2. 출력 표면 전체 지도

| 표면 | 형식 | 생성 시점 | 대상 | 노출 계층 |
|------|------|-----------|------|-----------|
| **결과 JSON** | `.json` 파일 | `monitor.save_to_file()` / `QuickEval.save()` | 도구·CI·로더 | L1–L6 (전부, 기계 판독 — `extra_metrics.insights`) |
| **단일 HTML 리포트** | self-contained `.html` | `save_to_file()`가 `.json`과 함께 자동 생성 / 대시보드 Export | 개발자·QM | L2–L6 |
| **비교 HTML 리포트** | self-contained `.html` | 대시보드 File Compare → Export / `/html/compare` | 개발자·QM | L2–L3 델타 + per-task 회귀/개선 |
| **`agent-eval gate`** | 터미널 표 + exit code + JUnit XML | CI 파이프라인 / 수동 | CI·QM | L3–L4 (+`--explain` 시 L5·L6 요약) |
| **`agent-eval diagnose`** | 터미널 (RCA 3단계) | 수동 (실패 원인 파고들 때) | 개발자 | L5 (+baseline 시 L5 회귀 귀속) |
| **`agent-eval abtest`** | 터미널 (통계 유의성) | 수동 (v1 vs v2 비교) | 개발자·QM | L2 통계 (Welch/mSPRT/FDR) |
| **`agent-eval trend`** | 터미널 (slope 추세) | CI / 수동 (여러 run 시계열) | QM·CI | L2 추세 (+회귀 시 git diff) |
| **대시보드** | FastAPI 웹 UI (23 탭 / 111 route) | `agent-eval dashboard` (port 8765) | 개발자·QM·거버넌스 | L1–L6 (인터랙티브) |
| **`agent-eval monitor`** | Arize Phoenix 웹 UI | `setup_otel()` opt-in | MLOps·운영 | 실시간 트레이스/스팬 (별도 파이프라인, [06_OBSERVABILITY](06_OBSERVABILITY.md)) |
| **LiveGuardrail 차단 메시지** | 훅 JSON / Error 문자열 | tool 실행 직전 (Gate B/E 위반) | AI 런타임 | 차단 사유 + `remediation`(조치) |
| **SessionEnd 요약** | Claude `systemMessage` / OpenCode synthetic transcript | 세션 종료 / 매 턴 | AI 런타임·사용자 | Gate B/E 점수 + 위반 요약 |
| **`search_violations` MCP** | 자연어 문자열 | 에이전트가 도구 호출 | AI 런타임 | 과거 차단 이력 + `recommend_fix` 힌트 |
| **`recommend_fix` MCP** | 자연어 문자열 | 에이전트가 도구 호출 | AI 런타임 | Gate/지표별 정적 조치 지식 (L6) |

---

## 3. 결과 JSON (`save_to_file()`)

**모든 출력의 원천.** `monitor.save_to_file("name")` → `results/name.json` + `results/name.html`.
`storage_backend="sqlite"`면 `.db` (스키마는 [04_DATA_GUIDE](04_DATA_GUIDE.md)).

### 최상위 키

| 키 | 계층 | 내용 |
|----|------|------|
| `schema_version` | — | 결과 스키마 버전 (현재 `"1.1"`). 소비자가 필드 형태 변화에 대응하기 위한 것 — breaking change 시 major 증가 |
| `tasks[]` | L1 | 태스크별 원천 레코드. 각 항목: `task_id · task_type · success · completion_score · accuracy_score · execution_time · tokens_used · tool_calls · attempts · errors · question · response · ground_truth · context · partial_reason · llm_judge · extra` |
| `total_tasks` | L2 | 태스크 수 |
| `accuracy_metrics` | L2 | `tcr · accuracy_scores · hallucination · quality · rag_metrics` |
| `efficiency_metrics` | L2 | `latency · tokens · tool_efficiency · retries · coordination · latency_analysis · workflow_analysis` |
| `quality_metrics` | L2 | ResponseQualityEvaluator 5차원 |
| `security_metrics` | L2 | 5개 보안 트래커 (opt-in) |
| `evaluators` | L1 | 각 evaluator의 원본 평가 배열 (재현/재로드용) |
| `extra_metrics.harness_groups` | **L3** | Gate A–G + `overall`. 각 Gate: `{name, score, status, gate, details}` — `details`에 산식 컴포넌트 (`tcr_pct`, `avg_subtask_completion`, `sla_breach_rate`, …) |
| `extra_metrics.lineage` | — | `git_commit · agent_version · prompt_version · iteration_note` (버전 추적, `agent_version="auto"` 시 자동) |
| `extra_metrics.insights` | **L5–L6** | 머신 판독 인사이트 계층 (SPEC-041 P9~) — `reporting/insights.py::build_insights()`가 `rca.diagnose()`·`utils.confidence`·`ontology.metric_registry` 출력을 한 객체로. `{schema_version, verdict{level, headline, confidence, next_actions[]}, metric_confidence{tcr_ci_pct, …}, evaluator_trust{trust_level, judge_vs_heuristic, judge_calibration, judge_self_consistency}, gate_findings[]{component_shortfalls[]{field, health, guidance, config_hint}}, failure_clusters[]{signature, task_type, count, impact_pct}, failure_lineage{regressed, persistent, new, fixed}, recommendations[]{code_snippet, experiment{…}, past_outcomes, baseline_verdict}, latency_budget, rag_localization, slice_analysis[], eval_set_quality}`. 대시보드 Improve 탭·`/api/diagnose/{id}`가 소비. 정적 HTML 리포트는 자체 헬퍼로 같은 내용 렌더 (콘텐츠 동등) |
| `recommendations` / `alerts` | L6 / — | 리포트 생성용 힌트 · 발화된 알림 |
| `anomaly_data` | L6 | `enable_anomaly_detection=True`일 때만. `{anomalies[], baseline_window, detection_window}` |
| `conversation_sessions` / `feedback` / `pricing` / `model_name` / `timestamp` | L1–L2 | 멀티턴 · 암묵 피드백 · 가격표 · 메타 |

### `harness_groups[X].details` 필드명 규약

- 대부분 `avg_*` / `*_rate` / `*_score` = 0–1
- `tcr_pct` 등 `*_pct` = 0–100
- `p95_latency_s` = 초, `ttft_p95_ms` = 밀리초
- `*_count` / `tasks_with_ifr` = 정수 카운터 (점수 아님)
- 소비 도구가 서로 다른 이름을 쓸 수 있음 → `ontology.metric_registry.canonical_metric_name()`으로 정규화

### 소비자

`serve/loader.py` (대시보드) · `cli/gate.py` · `cli/diagnose.py` · `cli/trend.py` · `cli/abtest.py` · `reporting/comprehensive_report.py` · `search_violations` (sqlite 백엔드) · 외부 CI 스크립트.

---

## 4. 정적 HTML 리포트 — 단일 결과

`generate_comprehensive_html_report(monitor)` / `generate_html_from_result_file(rf)` — 외부 CDN 의존성 없는 self-contained HTML. **개발자·QM의 1차 리포트.**

### 섹션 순서 (위 → 아래)

| # | 섹션 (`id`) | 계층 | 내용 | 조건 |
|---|-------------|------|------|------|
| 0 | 헤더 | L2 | 날짜 · 태스크 수 · 버전 · TCR/Accuracy `(95% CI …)` · Latency · Gate A–G 배지 | 항상 |
| 1 | **Executive Summary** (`exec-summary`) | **L6** | 배포 준비도 한 줄 판정 (`❌ Not deployment-ready` / `⚠️ Deploy with caution` / `✅ Deployment-ready`) + **`HIGH/MEDIUM/LOW CONFIDENCE` 배지**(표본 수·CI 폭·측정 컴포넌트 수·임계값 여유) + 병목 Gate + **Next actions 1·2·3** (fail 먼저, 각 Gate 최약 컴포넌트 + 조치) | 항상 |
| 2 | Scorecard | L3 | Gate A–G 카드 (score bar + status 배지) | 항상 |
| 3 | Gate A–G 상세 (`gate-a`…`gate-g`) | L3 | **Score Breakdown** (산식 + 컴포넌트별 raw value/기여도/note) + KPI + 상세 표. 측정 컴포넌트 ≤2 & score<90이면 "대표성 낮음" 경고. **전 Gate `insufficient_data_warnings`**(표본 부족 컴포넌트) 노출. **Gate D**: **Latency Budget** (SPEC-041 P7) — model/tool/network/unattributed 스택바 + `Bottleneck: <component>`; **Cost Efficiency** (SPEC-041 P16) — 성공 태스크당 비용(× cost/task) · 실패 낭비 · 재시도 burn · 10만 콜 투사 | 항상 (미측정 항목은 `⚙️ Not Configured` / `📉 Insufficient Data` / `➖ Not Applicable` 배너) |
| 4 | Advanced Metrics (`advanced`) | L2 | DeepEval · Ragas · 멀티턴 대화 세션 | 데이터 있을 때 |
| 5 | **Operational Signals** (`operational-signals`) | L6 | AnomalyDetector 결과 — type/severity/detail/value + `anomaly_suggestion_for()` 조치 | `enable_anomaly_detection=True` |
| 5b | **Per-Slice Breakdown** (`slice-analysis`) | **L4** | task_type별 N · TCR(95% CI) · Accuracy. baseline 있으면 `Δ vs baseline` + 두-표본 부트스트랩 유의성(*) (SPEC-041 P10 — "회귀가 한 코호트에 몰렸는지") | task_type ≥ 2종일 때 |
| 5c | **Eval-Set Quality** (`eval-set-quality`) | **L4** | task_type 히스토그램 · 근접중복 질문 클러스터 · 커버리지 경고(Gate 미실행 / 불균형 / 표본 부족) · suspicious ground truth(baseline 대비 동일 실패) (SPEC-041 P12) | 경고/중복/의심 항목 있을 때 |
| 5d | **Evaluator Reliability** (`evaluator-reliability`) | **L4** | `Evaluator trust: HIGH/MEDIUM/LOW` + 근거 · LLM judge ↔ 휴리스틱 채점기 일치율 + 불일치 태스크 · (있으면) judge-vs-human 보정(MAE/κ) · judge self-consistency. LOW면 배포 준비도 확신도 강등 (SPEC-041 P14) | `llm_judge` 데이터 있을 때 |
| 5e | **Human Review Queue** (`review-queue`) | **L5** | 자동 판정을 가장 못 믿을 태스크를 우선순위(HIGH/MEDIUM)로 — judge↔휴리스틱 불일치 · suspicious 라벨 · 회귀 실패 · 경계선 점수. `agent-eval dataset promote`로 골든 회귀 케이스 승격 (SPEC-041 P15) | 리뷰 대상 있을 때 |
| 6 | **실패/저점 케이스** (`failure-cases`) | **L1** | ① **Failure set vs baseline** — 📉Regressed/♻️Persistent/🆕New/✅Fixed (baseline 시) ② **RAG failure localization** (SPEC-041 P11) — retrieved context 있는 태스크를 retrieval-miss / grounding-miss / generation-error로 분류, 클래스별 count + 조치 + unsupported claim 예시 ③ **Failure themes** — `(사유 테마 × task_type)` 군집을 count·영향도(~%p) 순 ④ **Worst cases** 표 (`Status · Question→Response · Score(C/A) · Likely reason`) — 각 행에 **▸ Trajectory** `<details>` (SPEC-041 P7): `tool_calls`→`chain_steps`→`agent_interactions` 순으로 step→tool→인자/출력 요약→✓/✗ + 스텝별 duration/토큰 | 실패·저점 태스크 있을 때 |
| 7 | **Recommendations** (`recommendations`) | **L6** | fail/warn Gate마다 (a) `▲/▼ Since baseline` confirmed/refuted (b) GATE_GUIDANCE (c) **Biggest measured shortfalls** (d) **붙여넣을 수 있는 `@agent_eval` 코드 스니펫** (e) **🧪 실험 제안** — 예측 Δ + 권장 표본 + `agent-eval abtest` (f) **📈 과거 이력** — 이 Gate 조치 confirmed/refuted/avg Δ | 항상 |
| 8 | **Gate Failure / RCA Diagnosis** (`diagnosis`) | **L5** | baseline 없으면 "🔍 Gate Failure Diagnosis" — `component_shortfalls`(Component/Current/Health 약한 순) + 처방. baseline 있으면 "🔍 Gate RCA Diagnosis (Improve)" — Baseline/Current/Δ 표 + MAST 후보 + 추천 이력 | 항상 |
| 8b | **Trend** (`history-trend`) | **L4** | 같은 디렉터리의 형제 결과 JSON을 훑어 per-Gate 인라인 스파크라인 + `first→last (slope)` + `↓ N runs in a row` 배지 (SPEC-041 P13) | 디렉터리에 ≥3 run 있을 때 |
| 8c | **Change Ledger** (`change-ledger`) | **L6** | `recommendation_outcomes.jsonl` — recorded_at · 변경 · Gate · verdict · Δ score · note (SPEC-041 P13) | 그 파일에 항목 있을 때 |
| 9 | Conclusion (`conclusion`) | L2 | **Grade + 확신도** · 총 태스크 · TCR/Acc/Hall + **TCR/Accuracy 95% CI** · N/7 PASS · 생성 정보 | 항상 |

### baseline 전달 시 (`save_to_file(baseline_path=...)` / `QuickEval.save(baseline_path=...)`)

- 진단 섹션이 **회귀 기반**(`regression_vs_baseline`)으로 전환 — Baseline/Delta 열이 의미를 가짐
- `newly_unmeasured_gates` 경고 (baseline엔 있었는데 사라진 Gate = Config 실수 가능)

---

## 5. 비교 HTML 리포트

`generate_comparison_html_report(compare_result)` — 대시보드 File Compare 탭 Export 또는 `GET /html/compare?ids=…` / `?group_by=…`.

| 섹션 | 내용 |
|------|------|
| Metric Comparison | 파일별 Total Tasks · TCR · Accuracy · Avg Latency · Total Cost + `agent_version`/`iteration_note` 메타 행 |
| Δ Delta | 첫 파일 기준 TCR/Accuracy/Latency 델타 |
| Per-Task Detail | 공통 태스크 수 · **Regressions**(태스크별 accuracy/latency 하락) · **Improvements** |
| Pairwise LLM Judge | `judge_pairwise()` 맞대결 — Wins A/Ties/Wins B · Win Rate · 태스크별 승자+근거 (opt-in) |

3개 이상 파일 → N-way + Benjamini-Hochberg FDR 보정.

---

## 6. CLI 터미널 출력

모든 CLI는 색상 지원(TTY) + `--json` 옵션(파이프용, 해당 명령).

### `agent-eval gate` — 품질 게이팅 (CI)

```
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Agent Evaluator — Quality Gate
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [Harness Gate Composite Score 표]  (--min-gate-score 시)
  Metric      Current   Threshold   Delta   Result
  TCR         50.0%     ≥ 85%       -35.0%  ❌ FAIL
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Regressions detected:  (--fail-on-regression 시)
  ❌ Quality gate failed (0/1 passed)
  → Fail this step in your CI pipeline

  Why it failed — RCA summary   (실패 시 자동, --no-explain으로 억제)
  Gate A (score 0.600) — weakest components:
    • avg_subtask_completion (25%)
      → 여러 하위 작업 중 일부만 끝냈습니다. SubtaskConfig로 각 단계를 검증하세요.
```

| exit code | 의미 |
|-----------|------|
| 0 | 모든 기준 통과 |
| 1 | 임계값 미달 / 복합 점수 미달 / Gate 임계값 위반 |
| 2 | baseline 대비 회귀 (`--fail-on-regression`) |
| 3 | 골든셋 회귀 (`--golden-set --fail-on-golden-regression`) |

`--junit-xml PATH` → CI 시스템 통합용 XML. 상세: [05_QUALITY_GATE](05_QUALITY_GATE.md).

### `agent-eval diagnose` — Gate 회귀 원인진단 (RCA)

CI 게이트 **아님** — 항상 exit 0 (파일 못 읽을 때만 1). 3단계 절차(감지 → 원인귀속 → 교차확인)를 출력.

- **baseline 없이**: `absolute_threshold` 모드 — fail/warn Gate마다 "Weakest score components"(health 오름차순) + `NATIVE_METRIC_RULES` 처방
- **baseline 있으면** (`--baseline`): `regression_vs_baseline` — 세부 지표 변화량(largest absolute first) + `--show-diff`로 git commit 범위 diff까지
- Gate F 감지 시 MAST 실패모드 후보 (Cemri et al., NeurIPS 2025)
- `--violation-db PATH` → sqlite 위반 이력 교차검색

### `agent-eval abtest` — 통계 A/B

CI 게이트 아님. 파일 2개 → Welch's t-test (`--sequential` 시 mSPRT always-valid), 3개+ → N-way + FDR. 유의성 · 효과크기 · 표본 경고만 출력, pass/fail 없음. **SPEC-041 P10**: proportion형 지표(양쪽 mean∈[0,1])에 `min detectable effect @ 80% power (α=0.05): ±X — observed |delta| Y` 한 줄. not significant인데 관측 차이가 MDE보다 작으면 "underpowered — 동등성 증거가 아님, 태스크를 더 모으거나 `--sequential`" 경고.

### `agent-eval trend` — 시계열 추세

여러 결과 파일을 시간순으로 읽어 지표별 linear slope 계산 → `improving ↑` / `degrading ↓` / `stable →`.

| exit code | 의미 |
|-----------|------|
| 0 | 회귀 없음 (또는 `--fail-on-regression` 미지정) |
| 1 | 회귀 감지 (`--fail-on-regression` 지정 시) |

회귀 감지 + 첫/마지막 run에 `lineage.git_commit`이 있으면 **그 사이 실제 코드 변경**(변경 파일 · 커밋 목록)을 자동 첨부 (`--repo-path`로 저장소 지정).

---

## 7. 대시보드

`agent-eval dashboard` → FastAPI 서버 (port 8765, 23 탭 / 111 route). `results/` 의 `.json`을 폴링(15초 / `--watch`).

| 탭 그룹 | 주요 탭 | 계층 |
|---------|---------|------|
| **개요** | Overview · Harness Gates · Scorecard | L2–L3 |
| **상세** | Tasks (태스크 테이블) · Accuracy · Latency · Tokens & Cost · Quality | L1–L2 |
| **에이전틱** | Tool Calls · Coordination · Workflow · Retry | L2 |
| **보안** | Security (L1/L2 트래커) · Violations 검색(FTS5) | L2 |
| **비교** | File Compare (group_by · Pairwise Judge · 📄 Export HTML) | L2–L3 델타 |
| **🔧 Improve** | Gate RCA (`rca.diagnose()`) · baseline 없으면 `component_shortfalls`(Component/Current/Health) 표 · **배포 준비도 판정 + 확신도** · **실패 테마 군집 / baseline 대비 실패 집합** · **처방 카드**(붙여넣을 코드 스니펫 · 실험 제안 · 과거 이력 · baseline 대비 confirmed/refuted) · 추천 적용 이력 | **L5–L6** (`insights` 객체) |
| **운영** | Anomaly · Alerts · Cost · Config · Transparency | L2·L6 |

탭별 상세 + 활성화 조건: [06_OBSERVABILITY](06_OBSERVABILITY.md) §3–4.

프로덕션 실시간 트레이싱은 대시보드가 아니라 `agent-eval monitor` (Arize Phoenix, `setup_otel()` opt-in) — 별도 파이프라인.

---

## 8. AI 런타임 출력 (Claude 훅 · OpenCode 플러그인 · MCP)

LiveGuardrail(`gates/live_guardrail.py`)이 tool 실행 **직전** Gate B/E를 동기 판정한다. 목적은 리포트가 아니라 **에이전트의 자가 교정** — "무엇이 막혔나 + 그래서 뭘 하라"를 다음 턴 컨텍스트에 노출.

### 8.1 차단 시 — `LiveVerdict`

| 필드 | 내용 |
|------|------|
| `block` | `True`면 이 tool 호출을 막음 |
| `gate` | `"B"` (행동 무결성) / `"E"` (보안 경계) |
| `reason` | 기계 판독 사유 — 예: `loop_detection: ['consecutive_repeat'] (tool='Bash' repeated with identical arguments)` |
| `detail` | 구조화 판정 (dict) |
| `remediation` | **조치 지침** — `block=True`이고 미지정이면 `reason`에서 자동 도출: `COMPONENT_GUIDANCE` 문구 + "동일 호출 반복 말고 접근 바꿔라 + `recommend_fix` / `search_violations` MCP 도구로 확인하라" |

### 8.2 Claude Code CLI 훅 (`agent-eval claude install`)

| 이벤트 | 출력 |
|--------|------|
| **PreToolUse** (허용) | `{"hookSpecificOutput": {"permissionDecision": "allow"}}` |
| **PreToolUse** (차단) | `permissionDecisionReason` = `reason` + `\n→ ` + `remediation` · exit 2 · stderr 사유 |
| **PreToolUse** (circuit breaker tripped) | 연속 5회 차단 → `allow` + `systemMessage`("config가 잘못됐을 가능성이 높다, 파일을 고치고 새 세션") · 이후 관찰 전용(감사만) |
| **PostToolUse** | 확정 tool 호출을 세션 상태 파일에 기록 (판정 상태 복원용, Claude 훅은 호출마다 별도 프로세스) |
| **SessionEnd** | 배치 리포트 디스크 저장(`results/claude_code_live_guardrail/`) + `systemMessage` **세션 요약**: `Gate B/E 점수 + 위반 종류 + 차단 건수 + 리포트 경로` |

### 8.3 OpenCode 플러그인 (`agent-eval opencode install`)

| 이벤트 | 출력 |
|--------|------|
| **tool.execute.before** (차단) | `throw new Error("[agent-evaluator] blocked by Gate B: <reason>\n→ <remediation>")` — 이 문자열이 다음 턴 컨텍스트에 노출 |
| **tool.execute.before** (circuit breaker) | 연속 5회 차단 → 관찰 전용 전환 + stderr 경고 (Claude 훅과 대칭) |
| **tool.execute.after** | 실행 결과(success/exit_code/stdout) 기록. 성공 시 연속 차단 카운터 리셋 |
| **session.idle** (매 턴) | 위반 총계가 늘었을 때만 **synthetic transcript 파트** 추가 — `Gate B/E score · 위반 종류·대상 도구 · "search_violations로 과거 이력, recommend_fix로 조치 확인하라"`. ctx가 이걸 색인 → 다음 세션 자가 교정 |

Claude vs OpenCode 차이: [OPENCODE_VS_CLAUDE_CODE](OPENCODE_VS_CLAUDE_CODE.md).

### 8.4 MCP 도구 (opt-in: `pip install "agent-evaluator[mcp]"` + `--with-violation-search` / `--with-recommend-fix`)

| 도구 | 입력 | 출력 |
|------|------|------|
| `search_violations(query)` | 자연어 질의 | 관련도순 과거 차단 이력 (`[차단됨]`/`[관찰됨]` 접두) + 위반 유형 감지 시 **`recommend_fix(gate=…, metric=…)` 호출 힌트** |
| `recommend_fix(gate, metric=None, value=None)` | Gate A–G + 선택적 지표/값 | 정적 조치 지식 — `GATE_GUIDANCE` + `NATIVE_METRIC_RULES`(value 주면 임계값 위반 여부) + `ANOMALY_METRIC_SUGGESTIONS` + Gate F는 MAST 후보. 결과 파일 불필요, 항상 HOTL 고지로 끝 |

---

## 9. 정보 계층 × 표면 매트릭스

`●` = 완전 노출 · `◐` = 부분/요약 · `○` = 없음

| 표면 | L1 원천 | L2 집계 | L3 Gate | L4 판정 | L5 진단 | L6 처방 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| 결과 JSON | ● | ● | ● | ◐¹ | ● | ● |
| 단일 HTML 리포트 | ◐³ | ● | ● | ◐⁴ | ● | ● |
| 비교 HTML 리포트 | ◐ | ● | ◐ | ○ | ○ | ○ |
| `agent-eval gate` | ○ | ◐ | ● | ● | ◐⁵ | ◐⁵ |
| `agent-eval diagnose` | ○ | ○ | ◐ | ○ | ● | ◐ |
| `agent-eval abtest` | ○ | ● | ○ | ○ | ○ | ○ |
| `agent-eval trend` | ○ | ● | ◐ | ◐ | ◐⁶ | ○ |
| 대시보드 | ● | ● | ● | ◐ | ● | ● |
| LiveGuardrail 차단 | ◐ | ○ | ◐ | ● | ◐ | ● |
| SessionEnd 요약 | ○ | ○ | ◐ | ○ | ◐ | ◐ |
| `search_violations` | ◐ | ○ | ○ | ○ | ◐ | ◐⁷ |
| `recommend_fix` | ○ | ○ | ○ | ○ | ○ | ● |

1. `extra_metrics.insights.verdict` (배포 준비도 한 줄 판정 + 확신도) · 2·3. `extra_metrics.insights` (verdict·gate_findings·failure_clusters·recommendations — L5/L6 전체가 SPEC-041 P9부터 기계 판독 가능) · 4. baseline 전달 시 회귀 표시 · 5. `--explain` 또는 실패 시 자동 · 6. 회귀 시 git diff · 7. `recommend_fix` 호출 힌트

---

## 10. 역할별 출력 워크플로우

### 개발자 — "실패를 고친다"

```
save_to_file()  →  results/eval.html 열기
    ├─ Executive Summary: 어느 Gate가 병목인가, Next actions 1·2·3
    ├─ 실패 케이스 테이블: 어느 태스크가 왜 (question→response + likely reason)
    ├─ Gate 상세 Score Breakdown: 어느 컴포넌트가 점수를 깎았나
    └─ Recommendations / Diagnosis: 그 컴포넌트에 대한 구체 조치
         │
         └─(더 파고들 때)→  agent-eval diagnose results/eval.json
                              └─(코드 원인)→  agent-eval diagnose ... --baseline prev.json --show-diff
```

### 품질관리자 — "배포 판단 + 회귀 감시"

```
CI:  agent-eval gate results/ci.json --tcr 85 --accuracy 70 \
         --fail-on-regression 10 --junit-xml out.xml
     └─ exit 0/1/2/3  +  실패 시 RCA 요약 3줄
버전 비교:  대시보드 File Compare  또는  agent-eval abtest v1.json v2.json --sequential
릴리스 승인:  results/release.html  Executive Summary 한 줄 판정 + N/7 PASS
시계열:  agent-eval trend results/ --fail-on-regression   (회귀 시 원인 커밋까지)
```

### AI 런타임 — "행동 자가 교정"

```
tool 실행 시도
    ├─(Gate B/E 위반)→  차단 + remediation ("접근 바꿔라 + MCP 도구 써라")
    │      └─ 에이전트: search_violations("rm -rf")  →  과거 이력 + recommend_fix 힌트
    │                    recommend_fix("B", "loop_detection")  →  조치 지식
    ├─(연속 5회 차단)→  circuit breaker: 관찰 전용 전환 + "config 재검토" 경고
    └─ 세션 종료 →  SessionEnd 요약 (Gate B/E 점수 + 위반) → 다음 세션 컨텍스트
```

---

## 관련 문서

| 목적 | 문서 |
|------|------|
| 58개 지표 상세 (25 Native + 33 Harness Config) | [02_METRICS_GUIDE.md](02_METRICS_GUIDE.md) |
| 결과 JSON / SQLite 스키마 · 골든셋 | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| 임계값 설정 · CI/CD · trend · diagnose | [05_QUALITY_GATE.md](05_QUALITY_GATE.md) |
| 대시보드 23 탭 · Phoenix 실시간 모니터링 | [06_OBSERVABILITY.md](06_OBSERVABILITY.md) |
| Claude Code 훅 설치·설정 | [CLAUDE_CODE_HOOKS.md](CLAUDE_CODE_HOOKS.md) |
| OpenCode vs Claude Code 차이 | [OPENCODE_VS_CLAUDE_CODE.md](OPENCODE_VS_CLAUDE_CODE.md) |
