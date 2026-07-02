# 검증 원장 (Verification Ledger)

2026-07-02 세션에서 Agent-Evaluator 엔터프라이즈 개선 분석 중 제기된 모든 사실 주장을 코드베이스와 직접 대조한 기록. 서브에이전트 조사 결과와 이전 대화 요약을 그대로 인용하지 않고, 이 세션에서 직접 확인한 것만 "확인"으로 표시한다.

## 파일 규모 / 구조

| 주장 | 근거 | 상태 |
|---|---|---|
| `decorators.py` 9,632줄, top-level 정의 102개 | `wc -l`, `grep -c "^class \|^def "` 직접 실행 | 확인 |
| `monitor.py` 7,779줄, top-level 정의 5개 (God Object) | 동일 | 확인 |
| `taskresult_helpers.py` 4,632줄, `eval_*` 함수 55개 평면 나열 | 동일 | 확인 |
| decorators.py의 33개 Config가 Gate별로 정렬되지 않고 무작위 인터리빙 | `grep -n "^@dataclasses.dataclass" -A1` 전체 목록 확인 (예: Instruction(A)→Loop(B)→GoalAlignment(A)→Reproducibility(C)→Plan(A)→SLA(D)...) | 확인 |

## Gate 집계 로직

| 주장 | 근거 | 상태 |
|---|---|---|
| `_compute_harness_groups`가 단일 메서드로 ~1,285줄(`monitor.py:2779-4064`) | 메서드 경계 grep으로 확인 | 확인 |
| Gate B가 Gate A의 `avg_goal_alignment`/`avg_plan_coherence`를 진단용으로 재참조 (스코어링 제외) | `monitor.py:3854-3866` 직접 읽음, 주석 확인 | 확인 |
| SLA 데이터가 Gate C(`_rel_vals`)와 Gate D 양쪽에 스코어링 반영 | `monitor.py:3072-3082`(C), `:3878`(D) 직접 확인 | 확인 |
| SLA 표본 부족 경고(`len<5`)가 Gate D에만 노출, 같은 데이터를 쓰는 Gate C에는 미노출 | `monitor.py:3509-3510`(D 전용 `_d_insufficient`), Gate C details에 동등 키 없음 | 확인 |
| `_compute_harness_groups` 내 `for t in tasks`류 순회 46회 | grep 카운트 | 확인 (정확한 개수는 리팩터 시 재확인 필요) |
| `monitor.py::_compute_harness_groups`(정식)와 `serve/loader.py::_compute_harness_groups_fallback`(근사)이 서로 다른 수식 사용 | `loader.py:744-812` 전체 읽음 — Gate B는 `tcr×0.95` 단일 프록시, 6개 실제 지표 미반영 | 확인 |
| Gate D만 `insufficient_data_warnings` 보유, A/B/C/E/F/G는 표본 가드 없음 | `monitor.py` 전체에서 `insufficient`/`min_samples` grep | 확인 |

## 순환 임포트 / 의존 방향

| 주장 | 근거 | 상태 |
|---|---|---|
| `decorators.py`는 top-level에서 `taskresult_helpers.py`/`monitor.py`를 import하지 않고 함수 내부 lazy import만 사용 | `decorators.py:5264` 등 30여 곳 지역 import 확인 | 확인 |
| `monitor.py`는 `decorators.py`를 참조하지 않음 (역방향 순환 없음) | grep 결과 0건 | 확인 |

## 메모리/성능

| 주장 | 근거 | 상태 |
|---|---|---|
| `self.tasks`는 무상한 리스트(append만, maxlen 없음) | `monitor.py:6285,6291` | 확인 |
| `_recent_tasks_cache`는 별도 `deque(maxlen=10000)`이며 윈도우 조회 전용, `self.tasks` 자체는 여전히 무제한 | `monitor.py:516-518` | 확인 |
| `self.tasks`가 `_compute_harness_groups` 외 12곳 이상에서 전체 참조됨 (get_report_by_type/framework, export_by_framework, register_aggregator 등) | `monitor.py:3986,4084,4127,6212,6472,6528,6747,6822,6914,6944` | 확인 |
| `register_aggregator`로 등록한 사용자 함수가 `self.tasks` 전체를 인자로 받음 | `monitor.py:6914` | 확인 |
| `save_to_file`은 원자적 쓰기(`tempfile.mkstemp` + `os.replace`), `_STREAMING_THRESHOLD=5000` 존재 | `monitor.py:5618-5628`, `:87` | 확인 |
| `serve/loader.py::load_results`가 `rglob("*.json")`으로 전량 재스캔, 인덱싱/페이지네이션 없음 | `loader.py:1295` | 확인 |

## LLM Judge

| 주장 | 근거 | 상태 |
|---|---|---|
| `ajudge()`는 자기 docstring 예시(`llm_judge.py:443`) 외 repo 전체에서 호출되는 곳이 없음 (완전한 dead code) | repo-wide grep | 확인 |
| Judge 호출은 `temperature=0.0` 고정 | `llm_judge.py:532` | 확인 |
| `self.seed`/`self._rng`는 샘플링 여부 결정(`sample_rate` 비교)에만 사용, 생성 결정성과 무관 | `llm_judge.py:304-305,361` | 확인 |
| `batch_eval`의 `ThreadPoolExecutor`는 에이전트 함수 호출(`func`)만 감싸고, judge/record_task는 그 바깥에서 순차 처리 | `decorators.py:8388-8401` 직접 읽음 | 확인 |

## 엔터프라이즈 운영

| 주장 | 근거 | 상태 |
|---|---|---|
| `serve/server.py`는 CORS + No-cache 미들웨어만 있고 인증/인가 전무 (103 라우트) | `server.py:120-142` 전체 읽음 | 확인 |
| 알림 핸들러(Slack/Webhook/Email) 3종 모두 예외 처리·재시도·백오프 없음 | `alerts/handlers.py` 전체 읽음 | 확인 |
| Compliance는 HIPAA/GDPR 키워드 매칭만 존재, SOC2/PCI-DSS 룰셋 없음 | `taskresult_helpers.py:3672-3679` (PCI 언급은 `:2073`의 CVSS 가중치 주석뿐, 실제 분기 아님) | 확인 |
| `sdk_version`/`git_commit`/`prompt_version` 등 lineage 캡처 지점 0건 | `core/`, `decorators.py` 전체 grep | 확인 |
| CI 게이트(`HarnessEvaluationGate`)는 정적 임계값만, 베이스라인 비교는 `QuickEval.for_regression_eval`로 별도 분리 | `quick_eval.py:553-629` | 확인 |
| `.github/workflows` 디렉토리 없음, SBOM/취약점 스캔 도구 설정 없음 | `find`, repo 전체 확인 | 확인 |
| `pyproject.toml` 의존성이 범위 핀(`>=x,<y`) 방식 | `pyproject.toml` 직접 확인 | 확인 |

## 정정된 항목 (이전 세션에서 오류로 지적되고 수정됨)

| 원래 주장 | 오류 내용 | 정정 |
|---|---|---|
| "Gate는 서로 완전 독립된 모듈로 분리 가능" | A→B, SLA→C/D 교차 참조가 실제로 존재해 완전 독립 슬라이스는 불가능 | `gates/shared_metrics.py` 공유 계층 도입으로 정정 (SPEC-001) |
| "P0에서 self.tasks에 상한을 걸어 무제한 증식 방지" | `register_aggregator` 등 12곳 이상이 전체 태스크 리스트에 의존 — 기본값 변경 시 하위호환 붕괴 | 옵트인 `retention_mode="windowed"`로 정정, 기본값은 `"full"` 유지 (SPEC-004) |
