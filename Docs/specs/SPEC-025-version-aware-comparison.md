# SPEC-025: 버전 인식 비교 — prompt_version/agent_version 그룹 비교 + Pairwise LLM Judge + 골든셋 회귀 게이트

**Phase:** P8 (신규 기능 확장 — 개발 루프 "품질이 개선되고 있는가" 확인 격차 해소) · **상태:** **Implemented — REQ-1~6 전체 완료(2026-07-06)** · **의존성:** SPEC-010(완료, `cli/gate.py`의 baseline/회귀 판정 로직·`_compute_gate_regressions`를 그대로 재사용) · SPEC-006(완료, `LLMJudge`의 동시성/백오프 인프라를 `judge_pairwise`에도 재사용) · SPEC-013(완료, `serve/loader.py`의 증분 캐싱 구조를 `ResultFile` 신규 프로퍼티 추가에 그대로 적용)

> **구현 노트 (추가 개선, 2026-07-06)**: SPEC-025 완료 직후 진행한 자체 갭 분석에서
> "대시보드 UI가 `group_by`/`pairwise`를 노출하지 않는다"는 격차를 발견했고, 사용자
> 요청으로 곧바로 해소했다. `dashboard2.html.j2`(`/dashboard` 라우트 — 마이그레이션
> 완료 후 유지될 대시보드; 레거시 `dashboard.html.j2`는 건드리지 않음)의 File Compare
> 탭에 (1) `Group by: prompt_version|agent_version` 드롭다운 — `/api/compare?group_by=`로
> file_id를 해석해 기존 `compareIds`/`loadCompareData()` 흐름에 그대로 태운다(새 렌더링
> 로직 없음, 파일 선택 방식만 하나 추가), (2) 정확히 2개 파일 선택 시에만 노출되는
> "⚖️ Pairwise Judge" 서브탭 — `/api/compare?detailed=true&pairwise=true`를 호출해
> win/tie/lose 카운트 + win_rate + task별 winner/reasoning 표를 렌더링, (3) "📄 Export
> HTML" 다운로드 버튼을 추가했다. 백엔드에는 이 다운로드를 위한
> `generate_comparison_html_report()`(`reporting/comprehensive_report.py`)와
> `GET /api/export/html/compare`(`serve/routers/export.py`, ids 또는 group_by 입력 + 선택적
> pairwise) — **정적 경로(`/html/compare`)를 파라미터 경로(`/html/{file_id}`)보다 먼저
> 등록**해야 FastAPI가 `file_id="compare"`로 삼키지 않는다(라우트 등록 순서 테스트로
> 실제 검증). 새 비교 계산 로직은 만들지 않았다 — 이미 존재하는 `compare_results()`의
> 반환 dict(`files`/`delta`/`detailed`/`regression_tasks`/`improvement_tasks`/`pairwise`)를
> 그대로 표로 렌더링만 한다. `tests/test_compare_html_export.py`(12건: HTML 이스케이프
> 방어 포함) 추가, 전체 스위트 3,400 passed(회귀 0), 품질 래칫 순증가 E501 +15/UP006
> +2/UP045 +2(전부 파일 기존 컨벤션과 일치 — `comprehensive_report.py`는 이미 `Dict`/
> 100자 초과 HTML 템플릿 라인이 표준인 파일, `export.py`의 `Optional[str]`은 같은 파일의
> `export_html`이 아니라 `data.py`의 `compare_results` 파라미터 시그니처를 그대로 미러링).

> **구현 노트 (추가 개선 갭 후속 조치, 2026-07-06)**: 위 대시보드 추가분에 대한 자체
> 갭 분석에서 발견한 항목 중 2건을 곧바로 고쳤다 — (1) `GET /html/compare?...&pairwise=true`
> 전체 경로를 실제로 검증하는 테스트가 없었다(기존 테스트는 pairwise 로직과 HTML
> 렌더러를 각각 따로만 검증). 동일 `task_id`를 공유하는 전용 fixture +
> `judge_pairwise()` mock으로 엔드투엔드 테스트 1건 추가. (2) HTML 리포트에는
> "N common task(s) judged" 문구가 없어 대시보드 UI와 표현이 달랐다 — 리포트에도 동일
> 문구를 추가해 통일. (3) **`group_by`가 5개 초과 태그를 찾으면 무경고로 처음 5개만
> 보여주는 문제** — `_latest_file_ids_by_group()`가 태그값 알파벳 오름차순으로 정렬해
> 반환하는데, UI가 `.slice(0,5)`로 잘라 쓰면서 나머지가 아무 표시 없이 사라졌다.
> `applyCompareGroupBy()`가 절삭 전 전체 개수를 `compareGroupTotal`에 저장하고, 5 초과 시
> `⚠️ Found N distinct <field> values — showing only the first 5(alphabetical)` 배너를
> File Compare 탭에 노출하도록 수정(수동 선택으로 전환 시 `compareGroupTotal`도 함께
> 리셋). 백엔드 변경 없음 — 순수 UI 가시성 개선. 테스트: `/api/compare?group_by=`가
> 7개 태그 중 7개 전부를 반환하는지(절삭은 프런트엔드에서만 일어남을 확인) 직접 호출로
> 검증. 전체 스위트 3,401 passed(회귀 0).

> **구현 노트 (REQ-6, 2026-07-06)**: `cli/gate.py`에 `_load_golden_set(path)`(골든셋
> JSON 로드, 리스트 아니면 빈 리스트)와 `_check_golden_regressions(golden_cases,
> result_tasks)`(매칭 + 판정)를 추가했다. **설계안 대비 수정 1건**: 원 설계는 "매칭된
> 태스크가 없거나 accuracy_score가 낮으면(config.py의 기존 accuracy 임계값 재사용)"이라고
> 썼으나, 실제로 `config.py`에 그런 기존 accuracy 임계값 상수가 존재하지 않았다(직접
> grep으로 확인). 대신 각 태스크에 이미 계산돼 있는 `success`(bool) 필드를 판정 기준으로
> 썼다 — 새로운 임계값을 발명하지 않고 "이 케이스가 실행에 성공했는가"라는 이미 존재하는
> 신호를 그대로 신뢰하는 편이 이 CLI의 "사후 분석만 한다"는 기존 경계에 더 충실하다고
> 판단했다. 매칭은 `task_id` 우선, 없으면 `question` 텍스트 완전 일치 폴백. `success` 키
> 자체가 없는 비정상 데이터는 안전하게 회귀(실패)로 처리한다(관대하게 통과시키지 않음).
>
> `cmd_gate()`에 `--golden-set`/`--fail-on-golden-regression`을 배선했다 — 골든셋 파일이
> 없거나 파싱 실패하면 (오탈자를 "그냥 통과"로 오인하지 않도록) 즉시 exit 1로 실패시킨다.
> `--fail-on-golden-regression` 없이 `--golden-set`만 주면 회귀를 stderr에 보고만 하고
> 종료 코드에는 반영하지 않는다(다른 옵트인 체크들과 동일한 관례) — 지정 시에만 신규
> 전용 종료 코드 `3`을 반환한다(기존 0/1/2와 겹치지 않음, 다른 게이팅 실패(`--tcr` 등)와
> 독립적으로 병행 동작 확인). `cli/main.py`의 `gate` 서브파서에 두 플래그와 사용 예시를
> 추가했다.
>
> `tests/test_spec025_version_aware_comparison.py`에 `TestCheckGoldenRegressions`(7건)·
> `TestLoadGoldenSet`(4건)·`TestCmdGateGoldenSet`(8건) 추가 — 순수 매칭 로직(성공/실패/누락/
> question 폴백/success 키 부재/빈 골든셋/비-dict 원소 방어), 로더(리스트 아닌 JSON·
> 파일 없음·JSON 파싱 실패), CLI 통합(파일 없음→1, 파싱 실패→1, 통과→0, 플래그 없이
> 회귀만 보고→0, 플래그 있고 회귀→3, `--golden-set` 미지정 시 하위호환, 일반 지표
> 게이팅과 병행 동작). 전체 스위트 **3,348 passed, 1 skipped, 회귀 0건**(기존 3,329 +
> 신규 19). 품질 래칫 순변화 **0**(`gate.py`/`main.py` 모두 FastAPI에 노출되지 않는
> 순수 CLI 모듈임을 확인하고 신규 코드를 `dict`/`list` 최신 문법으로 작성).
>
> **SPEC-025 전체 완료.** REQ-1(버전 메타데이터 노출)→REQ-2(그룹 비교)→REQ-3(버전별
> baseline)→REQ-4(pairwise judge)→REQ-5(pairwise 통합)→REQ-6(골든셋 게이트)까지 6개
> 요구사항 모두 실제 테스트 통과와 품질 래칫 순증가 0(REQ-1의 불가피한 최소 예외 2건
> 제외)을 확인하며 구현했다.

> **구현 노트 (REQ-5, 2026-07-06)**: `compare_results`(`serve/routers/data.py`)에
> `pairwise: bool = Query(default=False, ...)`를 추가했다. `detailed=True`와
> 함께 지정하면(단독으로는 무시 — REQ-4의 기존 `if detailed and len(file_ids) >= 2:`
> 블록 안에서만 동작), 이미 계산된 `common_ids`에 대해 신규 모듈 함수
> `_run_pairwise_comparison(tasks_a, tasks_b, common_ids)`이 각 task마다
> `LLMJudge().judge_pairwise(question, response_a, response_b)`(REQ-4, 그대로 재사용)를
> 호출해 `wins_a`/`wins_b`/`ties`/`judged_count`/`win_rate`(tie는 0.5승 처리 — LLM 평가
> 문헌의 통상적 win-rate 정의)를 `result["pairwise"]`에 담는다. `question`/`response`는
> `TaskRecord.raw`(`serve/loader.py:1206`가 원본 태스크 dict를 그대로 보존)에서 읽는다.
> `judge_pairwise()`가 예산 초과·연속 오류·파싱 실패로 `skipped`/`error`를 반환한 task는
> 집계에서 제외한다(새 판정 로직을 만들지 않고 REQ-4의 안전장치를 그대로 신뢰).
> 기존 `accuracy_delta` 기반 `regression_tasks`/`improvement_tasks`는 **대체하지 않고
> 병행 제공**한다(설계 그대로) — `pairwise`는 추가 신호일 뿐이다.
> `LLMJudge` import는 이 파일의 다른 무거운 통합체와 동일하게 함수 내부 지연 임포트로
> 두었다(모듈 상단에 신규 top-level 의존성을 추가하지 않음).
> `tests/test_spec025_version_aware_comparison.py`에 `TestComparePairwise`(7건) 추가 —
> `pairwise=False`/`detailed=False` 시 키 부재, 전승/동점(0.5승) 집계, 스킵/오류 task 제외,
> 공통 task 없을 때 `win_rate=None`, 기존 regression/improvement 목록과 병행 제공 확인.
> `unittest.mock.patch.object(LLMJudge, "judge_pairwise", ...)`로 실제 API 호출 없이
> 검증했다. 전체 스위트 **3,329 passed, 1 skipped, 회귀 0건**(기존 3,322 + 신규 7).
> 품질 래칫 순변화 **0**(`_run_pairwise_comparison`이 FastAPI가 처리하지 않는 순수
> 헬퍼임을 확인하고 `dict`/`list` 최신 문법으로 작성, mypy 순변화 0).

> **구현 노트 (REQ-4, 2026-07-06)**: `integrations/llm_judge.py`에 `LLMJudge.judge_pairwise(
> question, response_a, response_b, context=None, swap_check=True) -> dict`를 추가했다.
> 기존 `judge()`/`_call_judge()`/`_call_claude()`/`_call_openai()`의 예산 체크
> (`_check_budget()`)·연속 오류 자동 비활성화(`_disabled_reason`)·재시도/백오프
> (`_call_with_retry()`, SPEC-006)·비용 추정(`_estimate_cost()`)을 그대로 재사용하되,
> 5차원 절대 스코어링 파서(`_parse_judge_response`)는 건드리지 않고 별도의
> `_call_claude_pairwise`/`_call_openai_pairwise`/`_parse_pairwise_response`를
> 병렬로 추가했다(기존 검증된 절대 스코어링 경로에 회귀 위험을 주지 않기 위해 — 두
> 경로는 프롬프트만 다르고 구조는 동일). `sample_rate` 샘플링은 의도적으로 적용하지
> 않는다 — pairwise 비교는 호출자가 명시적으로 요청하는 단발성 호출이라 대량 태스크
> 샘플링과 성격이 다르다는 판단(설계 문서에 없던 세부 결정, docstring에 근거 명시).
>
> **swap-check 설계**: `_resolve_pairwise_result()`가 1차 호출(A, B 원래 순서)과, 필요시
> A/B를 뒤집은 2차 호출을 받아 `_flip = {"a":"b","b":"a","tie":"tie"}`로 2차 결과를
> 원래 프레임으로 되돌린 뒤 일치 여부로 최종 승자를 정한다. 2차 호출이 실패하면(네트워크
> 문제 등) 무작위로 `"tie"` 처리해 유효한 1차 결과를 버리지 않고, `swap_check=False` +
> `swap_check_error`로 "swap-check 미완료"만 표시한다 — 설계안에는 없던 방어적 결정.
> `winner` 파싱 값이 `"a"/"b"/"tie"` 중 하나가 아니면 임의로 승자를 선언하지 않고
> `"tie"`로 처리한다(같은 원칙).
>
> pairwise 이력은 `self.pairwise_results`(신규, `self.results`와 분리)에 쌓여
> `get_summary()`의 절대 스코어 집계를 오염시키지 않는다. `tests/test_spec025_version_aware_comparison.py`에
> `TestPairwiseJudgeDispatch`·`TestParsePairwiseResponse`·`TestCallPairwiseNoKey`·
> `TestJudgePairwise`(19건) 추가 — dispatch 분기, 파싱(대소문자·알 수 없는 값·마크다운
> 펜스·파싱 오류), API 키 없음, swap-check 합의/불일치/비활성화/2차 실패, 예산 초과,
> 연속 오류 자동 비활성화, `pairwise_results`와 `results`의 분리 확인. 관련 LLMJudge
> 스위트(`test_coverage_llm_judge.py`·`test_llm_judge_concurrency.py`·
> `test_judge_execution_model_heterogeneity.py`·`test_llm_judge_calibration.py`) +
> 전체 스위트 **3,322 passed, 1 skipped, 회귀 0건**(기존 3,303 + 신규 19).
> 품질 래칫 순변화 **0**(초안 구현에서 ruff +23·mypy +1 발생 → 이 파일이 FastAPI/pydantic에
> 노출되지 않는 순수 클래스임을 확인하고 신규 코드만 `dict`/`str | None` 최신 문법으로
> 전환, mypy 오류는 `_flip.get()` 호출에 `isinstance` 가드를 추가해 해소 — 최종 순증가 0).

> **구현 노트 (REQ-3, 2026-07-06)**: `cli/gate.py`에 `_baseline_version_path(result_file,
> tag) -> Path`(`result_file.parent / "baselines" / f"{tag}.json"`)를 추가하고,
> `cmd_gate()`의 기준선 경로 결정을 `--baseline`(명시적 경로) > `--baseline-version`
> (버전별 `baselines/<tag>.json`) > 기본 `baseline.json` 순으로 확장했다. `_save_baseline`/
> `_load_baseline`/`_check_regression`은 경로 하나만 받는 기존 시그니처 그대로 재사용 —
> 저장/조회/회귀비교 로직 자체는 한 줄도 바꾸지 않았다(설계 그대로, 새 알고리즘 없음).
> `cli/main.py`의 `gate` 서브파서에 `--baseline-version TAG`(dest=`baseline_version`)를
> 추가하고 epilog에 사용 예시 2줄을 추가했다. `--baseline-version` 미지정 시
> `getattr(args, "baseline_version", None)`이 `None`을 반환해 기존 `baseline.json` 단일
> 경로 동작과 100% 동일(SPEC-010 기존 테스트 스위트 그대로 통과로 확인).
> `tests/test_spec025_version_aware_comparison.py`에 `TestGateBaselineVersion`(6건) 추가 —
> 경로 헬퍼, `baselines/<tag>.json` 저장, 두 버전 독립성, 버전별 회귀 탐지(exit 2),
> `--baseline`이 `--baseline-version`보다 우선, 미지정 시 기존 경로 하위호환. 품질 래칫
> 순변화 0(ruff/mypy 모두 pre-existing 위반과 정확히 동일한 개수 — 신규 코드가 추가한
> debt 없음). 전체 스위트 **3,303 passed, 1 skipped, 회귀 0건**(기존 3,297 + 신규 6).

> **구현 노트 (REQ-2, 2026-07-06)**: `compare_results`(`serve/routers/data.py`)의 `ids`를
> 필수(`Query(...)`)에서 옵트인(`Optional[str] = Query(default=None, ...)`)으로 바꾸고,
> `group_by: Optional[str] = Query(default=None, ...)`를 추가했다. `group_by`가 주어지면
> 신규 헬퍼 `_latest_file_ids_by_group(rs, group_by)`가 `rs.files`(이미 로드된 전체
> `ResultSet`, 디스크 재스캔 없음)를 `group_by` 값별로 묶고 그룹마다 `ResultFile.mtime`
> (SPEC-013 필드) 기준 최신 파일 1개의 `file_id`만 뽑아 `sorted()`로 결정적 순서를 만든다
> — 이후 로직(`rf_map`/`files_data`/`delta`/`detailed` 계산)은 REQ-1 이전부터 있던 기존
> 코드를 그대로 재사용한다(새 비교 알고리즘 없음, 설계 그대로). `group_by` 값이 없는
> (`None`) 파일은 그룹 대상에서 제외 — Acceptance에서 예고한 "둘 중 택1"을 "제외"로
> 확정해 문서화했다. `ids`가 주어지면 `group_by`는 무시된다(우선순위 명시). `group_by`가
> `{"prompt_version", "agent_version"}` 밖의 값이면 400.
> SPEC-021 품질 래칫 순변화: ruff +2(UP045, `ids`/`group_by` 두 FastAPI `Query` 파라미터 —
> REQ-1과 동일한 이유로 `Optional[str]` 유지, `str | None`은 Python 3.8/3.9에서 FastAPI가
> 의존성 주입 시 깨질 위험), mypy +0, E501 +0(신규 헬퍼 함수는 FastAPI가 처리하지 않아
> `dict`/`list` 최신 문법으로 작성해 그쪽에서는 debt 미발생). `tests/test_spec025_version_aware_comparison.py`에
> `TestCompareResultsGroupBy`(7건) 추가 — 그룹당 최신 파일 선택(`os.utime`로 mtime 결정적
> 조정), 미태그 파일 그룹 제외, delta 계산 재사용 확인, 잘못된 `group_by` 값 400, `ids`
> 우선순위, `ids`/`group_by` 둘 다 없으면 400, `agent_version` 그룹핑. 전체 스위트
> **3,297 passed, 1 skipped, 회귀 0건**(기존 3,290 + 신규 7).

> **구현 노트 (REQ-1, 2026-07-06)**: `ResultFile`(`serve/loader.py:203-214`)에 `prompt_version`/
> `agent_version` 프로퍼티를 추가했다 — 설계안의 `self.raw.get("prompt_version")`은 실제
> 구조와 달라 구현 중 바로잡았다: 실제 값은 `report["prompt_version"]`이 아니라
> `report["extra_metrics"]["lineage"]["prompt_version"]`(SPEC-007 `_build_lineage()`,
> `monitor.py:2969-2973`)에 있으므로, `(self.raw.get("extra_metrics") or {}).get("lineage",
> {}).get("prompt_version")`으로 읽는다(`tests/test_lineage_capture.py`가 이미 이 경로를
> 검증하고 있어 재확인 후 반영). `list_results`(`serve/routers/data.py`)에 `prompt_version`/
> `agent_version` 쿼리 파라미터(`Optional[str]`, exact match)를 추가하고, `_to_meta()` 응답에도
> 두 필드를 노출했다. FastAPI `Query()` 파라미터는 `Optional[str]`로 유지했다 — 이 저장소가
> `Python 3.8+`를 타깃으로 명시하므로, `str | None` PEP 604 문법은 `from __future__ import
> annotations`가 있어도 FastAPI가 의존성 주입 시 `typing.get_type_hints()`로 문자열 annotation을
> 실제로 평가하기 때문에 3.8/3.9에서 깨질 수 있다는 것을 확인하고 되돌렸다(순수 `@property`
> 반환 타입인 `ResultFile.prompt_version`/`agent_version`은 FastAPI가 평가하지 않으므로 `str |
> None`으로 유지 — 이 파일에 그런 문법이 없었던 이유가 실제로 이 리스크 때문인지는 불명확하나,
> 안전한 쪽을 택했다). SPEC-021 품질 래칫 기준 순변화: ruff +2(UP045, `data.py`의 신규
> 파라미터 2개 — 바로 위 `tcr_min`/`accuracy_min` 등 기존 파라미터 4개와 동일한 스타일이라
> 일관성을 위해 감수), mypy +2(`no-any-return`, 신규 프로퍼티 2개 — 같은 파일의 기존
> `tcr`/`accuracy`/`hallucination_rate` 등 8개 프로퍼티가 이미 동일한 패턴으로 위반하고
> 있어 그대로 따름). `tests/test_spec025_version_aware_comparison.py`(8건) 신규 —
> 버전 필드 노출·구버전 파일에서 `None`·`list_results` 정확 일치 필터·필터 미지정 시 전체
> 반환·`_to_meta` 노출까지 확인. 관련 테스트 스위트(`test_loader_parsers.py`·
> `test_spec013_loader_incremental_cache.py`·`test_lineage_capture.py`·
> `test_version_features.py`) + 전체 스위트 **3,290 passed, 1 skipped, 회귀 0건**(기존
> 3,282 + 신규 8).

## Context

- `PerformanceMonitor.__init__`은 `prompt_version`/`agent_version` 파라미터를 받아(`agent_evaluator/core/trackers/monitor.py:280-281`) `self._prompt_version`/`self._agent_version`에 저장하고(`:484-485`), `generate_report()`가 만드는 리포트 dict에 그대로 직렬화한다(`:2972-2973`). 즉 **버전 메타데이터는 이미 모든 결과 JSON 파일 안에 존재**한다.
- 그런데 이 두 필드를 소비하는 코드가 저장소 전체에 없다 — `grep -rn "prompt_version\|agent_version" agent_evaluator/serve/ agent_evaluator/cli/`가 0건을 반환한다. 대시보드가 결과 파일을 파싱해 만드는 `ResultFile` 데이터클래스(`agent_evaluator/serve/loader.py:137-168`)에도 이 두 필드에 대응하는 속성이 없다 — 원본 JSON은 `raw: Dict[str, Any]`(`:155`)에 전체 보존되므로 값 자체는 `raw.get("prompt_version")`으로 언제든 꺼낼 수 있지만, `tcr`/`accuracy`(`:171-177`)처럼 1급 프로퍼티로 노출된 적이 없다.
- 대시보드의 다중 결과 비교 API `compare_results`(`agent_evaluator/serve/routers/data.py:1442-1534`)는 `ids: str = Query(...)`로 **사람이 직접 골라야 하는 콤마 구분 file_id 목록**만 입력받는다. `detailed=True`일 때 공통 `task_id` 기준 accuracy_delta/latency_delta와 회귀/개선 태스크 목록까지 뽑아주는(`:1495-1532`) 잘 만들어진 기능이 이미 있지만, "어떤 파일이 어떤 프롬프트 버전인지"는 이 함수도, 그 앞단의 `list_results`(`:177-`)도 전혀 모른다.
- `agent-eval gate`(`cli/gate.py`)의 기준선은 `_default_baseline_path()`(`:276-278`)가 반환하는 **디렉토리당 정확히 1개**의 `baseline.json`이다. 여러 프롬프트 버전을 동시에 실험 중이면(예: `v1-few-shot` vs `v2-cot`), 버전마다 별도 기준선을 두고 비교할 방법이 없다 — 최신 저장이 항상 유일한 기준선을 덮어쓰는 구조.
- `LLMJudge`(`agent_evaluator/integrations/llm_judge.py:273-`)의 `judge()`(`:374`)/`ajudge()`(`:514`)는 응답 하나에 대한 절대 스코어(0-5)만 반환한다. `grep -rln "pairwise\|win_rate\|elo" agent_evaluator/`에 이 클래스나 어떤 코드도 걸리지 않는다 — 응답 A/B를 직접 맞대결시켜 상대적으로 판정하는 경로가 아예 없다. 절대 스코어는 judge 모델의 그날그날 기준 이동(scale drift)에 민감해, "A가 B보다 나은가"를 판정하는 용도로는 pairwise가 더 안정적이라는 것이 이 SDK가 이미 채택한 G-Eval 계열 관행(`llm_judge.py:14` 주석)과도 맥이 닿는다.
- `GoldenSetBuilder.extract()`(`agent_evaluator/datasets/builder.py:77-`)는 운영 실패 케이스를 후보로 뽑고, 대시보드의 `approve_case`/`merge_approved`(`serve/routers/golden.py:415-434`, `:511-534`)가 사람 승인을 거쳐 `data/golden_datasets/golden_<timestamp>.json`으로 병합한다(내부 `_` 접두 메타 필드는 제거하되 원본 `task_id`/`question`/`ground_truth`는 그대로 보존, `golden.py:527`). 이렇게 승인된 골든셋이 `agent-eval gate`/`agent-eval trend` 어느 쪽과도 연결되지 않는다 — "이번 변경이 과거에 실패했던 케이스들을 여전히 통과하는가"를 확인하려면 사람이 수동으로 두 파일을 열어 대조해야 한다.

## Goals

- `prompt_version`/`agent_version`을 `ResultFile`의 1급 속성으로 노출하고, 이 값으로 결과 파일을 필터링/그룹핑해 "버전 A vs 버전 B"를 자동으로 비교할 수 있게 한다.
- `agent-eval gate`가 버전별로 분리된 기준선을 저장·조회할 수 있게 해, 여러 프롬프트 실험을 동시에 진행하며 각자의 회귀 여부를 독립적으로 추적할 수 있게 한다.
- 절대 스코어보다 변동성이 낮은 pairwise(승/패/무) LLM Judge 비교를 추가해, `compare_results(detailed=True)`가 이미 만드는 공통 task_id 목록 위에서 "어느 응답이 더 나은가"를 판정할 수 있게 한다.
- 사람이 승인한 골든셋을 CI 게이트에 연결해, 실행 결과가 과거 실패 케이스를 커버·통과하는지 자동으로 검증한다.

## Non-Goals

- Elo/TrueSkill 등 다표본 랭킹 알고리즘 — 이번 스펙은 두 응답 간 단순 승/패/무 집계(win rate)까지만 다룬다. 3개 이상 버전의 상대적 순위가 필요하면 별도 후속 스펙.
- `prompt_version`/`agent_version` 값 자체의 자동 생성(git commit SHA, 프롬프트 파일 해시 등) — 이번 스펙은 **사용자가 이미 존재하는 이 두 파라미터에 값을 넘긴다는 전제** 위에서 그 값을 소비하는 쪽만 다룬다. 로컬 ADE(OpenCode) 세션에서 git 정보를 자동으로 태깅하는 것은 별도 후속 스펙(AOO ADE 연동 트랙) 범위.
- 골든셋 케이스를 현재 에이전트로 **재실행**하는 기능 — `cli/gate.py`는 이미 생성된 결과 JSON을 분석하는 사후 분석 도구이지 에이전트를 호출하는 실행기가 아니다(기존 아키텍처 경계 유지). REQ-5는 "최신 결과 파일에 골든셋 케이스가 커버·통과됐는가"만 검증하며, 에이전트 실행 자체는 사용자의 기존 파이프라인 책임으로 남긴다.
- 기존 `compare_results(ids=...)` file_id 직접 비교 경로의 제거 또는 시그니처 변경 — 신규 groupby 경로는 추가 옵션이며 기존 호출은 100% 그대로 동작해야 한다.

## Requirements

- **REQ-1**: `ResultFile`(`serve/loader.py:137-`)에 `prompt_version: Optional[str]`/`agent_version: Optional[str]` 프로퍼티를 추가한다(`self.raw.get("prompt_version")`/`self.raw.get("agent_version")`을 반환 — 신규 파싱 로직 없이 이미 보존된 `raw`에서 읽기만 한다). `list_results`(`serve/routers/data.py:177-`)에 `prompt_version`/`agent_version` 쿼리 파라미터를 추가해 정확히 일치하는 파일만 반환하도록 필터링한다.
- **REQ-2**: `compare_results`(`data.py:1442-`)에 `group_by: Optional[str] = Query(default=None, description="prompt_version|agent_version")` 파라미터를 추가한다. 지정되면 `ids` 대신 `results_dir` 전체를 스캔해 해당 필드 값별로 파일을 그룹핑하고, 그룹별 최신 파일 1개씩을 뽑아 기존 `delta` 계산(`:1481-1491`) 로직을 그대로 적용한다 — 새 비교 알고리즘을 만들지 않고 기존 델타 계산을 그룹 선택 단계 앞에 끼워 넣는다.
- **REQ-3**: `cli/gate.py`의 baseline 경로 함수를 확장한다 — `--baseline-version <tag>` 인자가 주어지면 `_default_baseline_path()`(`:276-278`) 대신 `result_file.parent / "baselines" / f"{tag}.json"`을 사용한다(미지정 시 기존 `baseline.json` 단일 경로로 100% 하위 호환). `--save-baseline --baseline-version <tag>` 조합으로 버전별 기준선을 독립적으로 저장할 수 있다.
- **REQ-4**: `LLMJudge`(`integrations/llm_judge.py`)에 `judge_pairwise(question: str, response_a: str, response_b: str, context: str = "") -> Dict[str, Any]` 메서드를 추가한다. 기존 `judge()`가 쓰는 것과 동일한 client/재시도/백오프 인프라(SPEC-006)를 재사용하되, 프롬프트는 "A와 B 중 어느 응답이 더 나은가, 혹은 동등한가"를 판정하도록 구성한다. 반환값은 `{"winner": "a"|"b"|"tie", "reasoning": str}`. 포지션 편향(A/B 순서 자체가 판정에 영향)을 완화하기 위해 내부적으로 A/B 순서를 뒤집어 2회 호출한 뒤, 두 호출의 승자가 일치하면 그 결과를, 불일치하면 `"tie"`를 반환한다(옵트인 `swap_check: bool = True` 파라미터로 비활성화 가능 — 호출 비용을 2배로 만들지 않으려는 사용자를 위한 탈출구).
- **REQ-5**: `compare_results(detailed=True)`(`data.py:1495-1532`)에 `pairwise: bool = Query(default=False)` 파라미터를 추가한다. `True`면 이미 계산된 공통 `task_id`마다(`:1506`) REQ-4의 `judge_pairwise()`를 호출해 `win_rate`(첫 번째 파일 기준 승률)를 `result["detailed"]`에 추가한다 — 기존 accuracy_delta 기반 regression_tasks/improvement_tasks는 그대로 유지하고 병행 제공한다(대체가 아니라 추가 신호).
- **REQ-6**: `cli/gate.py`에 `--golden-set <path>` 인자를 추가한다. 지정 시 골든셋 파일(`data/golden_datasets/golden_*.json`, `golden.py:524`가 만드는 형식 — `task_id`/`question`/`ground_truth` 보존)의 각 케이스에 대해, 분석 대상 결과 파일의 `tasks` 목록에서 동일 `task_id`(있으면) 또는 `question` 텍스트 일치(없으면 폴백)로 매칭을 시도한다. 매칭된 태스크가 없거나(커버리지 누락) `success=False`/`accuracy_score`가 낮으면(`config.py`의 기존 accuracy 임계값 재사용) 이를 "golden regression"으로 별도 집계해 출력하고, `--fail-on-golden-regression` 지정 시 전용 종료 코드(기존 0/1/2와 겹치지 않는 `3`)를 반환한다.

## Interface

```python
# REQ-1 — ResultFile 신규 프로퍼티 (신규 파싱 없이 raw에서 읽기만 함)
rf.prompt_version  # -> "v2-cot" | None
rf.agent_version    # -> "0.9.7" | None
```

```
GET /api/results?prompt_version=v2-cot
GET /api/compare?group_by=prompt_version&pairwise=true
```

```bash
# REQ-3 — 버전별 독립 기준선
agent-eval gate results/run_v2.json --save-baseline --baseline-version v2-cot
agent-eval gate results/run_v2_latest.json --baseline-version v2-cot --fail-on-regression

# REQ-6 — 골든셋 회귀 게이트
agent-eval gate results/run_latest.json \
  --golden-set data/golden_datasets/golden_20260705_120000.json \
  --fail-on-golden-regression
# exit 3: golden regression — 2 case(s) missing or failing (task_id=t042, t108)
```

```python
# REQ-4 — pairwise judge
judge = LLMJudge(model="claude-haiku-4-5-20251001")
result = judge.judge_pairwise(
    question="...", response_a="(v1 응답)", response_b="(v2 응답)", context="...",
)
# {"winner": "b", "reasoning": "..."}
```

## Acceptance

- **REQ-1**: `prompt_version="v2"`로 저장된 결과 파일을 로드했을 때 `ResultFile.prompt_version == "v2"`; 필드가 없는 구버전 결과 파일에서는 `None`(에러 아님) — 하위 호환 확인.
- **REQ-2**: 동일 `prompt_version` 값을 가진 파일이 3개 있을 때 `group_by=prompt_version`이 그중 최신 파일만 그룹 대표로 선택하는지, 값이 없는 파일(`None`)은 별도 그룹으로 묶이거나 제외되는지(둘 중 택1, 명시적으로 문서화) 검증.
- **REQ-3**: `--baseline-version v1`로 저장 후 `--baseline-version v2`로 별도 저장 — 두 파일이 독립적으로 존재하고 서로의 회귀 판정에 영향을 주지 않는지 확인. `--baseline-version` 미지정 시 기존 `baseline.json` 단일 경로 동작이 회귀 없이 그대로인지(기존 SPEC-010 테스트 스위트 통과) 확인.
- **REQ-4**: 명백히 더 나은 응답 A(정확·완결)와 더 나쁜 응답 B(오류 포함)를 pairwise 판정했을 때 `winner == "a"`가 A/B 순서를 바꿔도 안정적으로 나오는지(position bias 완화 확인). 두 응답이 사실상 동일할 때 `swap_check=True`에서 두 호출 결과가 불일치하면 `"tie"`로 수렴하는지 확인.
- **REQ-5**: `pairwise=true`로 호출한 `compare_results(detailed=True)` 결과에 `win_rate` 키가 존재하고, `pairwise=false`(기본값)에서는 기존 응답 스키마와 완전히 동일한지(회귀 없음) 확인.
- **REQ-6**: 골든셋의 특정 `task_id`가 최신 결과 파일에서 빠져 있을 때(커버리지 누락)와, 존재하지만 `success=False`일 때(품질 회귀) 각각 "golden regression"으로 잡히는지, 두 사례 모두 없을 때는 exit code 0으로 통과하는지 확인.

## Compatibility

- REQ-1/2/5는 `serve/loader.py`/`serve/routers/data.py`에 대한 순수 additive 변경 — 기존 `ResultFile` 필드·`compare_results(ids=...)` 기본 호출 방식·응답 스키마는 그대로 유지된다.
- REQ-3/6은 `cli/gate.py`에 신규 옵트인 플래그만 추가 — 미지정 시 기존 baseline.json 단일 경로 동작, 기존 종료 코드(0/1/2) 의미는 변경되지 않는다(`3`은 신규 전용 코드).
- REQ-4는 `LLMJudge`에 신규 메서드 추가 — 기존 `judge()`/`ajudge()` 시그니처·반환값 무변경.

## Rollout

1. REQ-1(`ResultFile` 프로퍼티 + `list_results` 필터) — 가장 리스크 낮음, 다른 REQ의 전제.
2. REQ-2(`compare_results` group_by) — REQ-1에 의존.
3. REQ-3(`gate.py` 버전별 baseline) — REQ-1/2와 독립적으로 병행 가능.
4. REQ-4(`judge_pairwise`) — 독립적, SPEC-006 인프라 재사용.
5. REQ-5(`compare_results` pairwise 통합) — REQ-2와 REQ-4 완료 후.
6. REQ-6(골든셋 회귀 게이트) — 나머지와 독립적, 마지막에 배치(가장 새로운 개념이라 별도 검증 시간 필요).

## Risks

- **`group_by`가 그룹당 여러 파일 중 "최신"을 임의로 고르는 것의 함정**: 같은 프롬프트 버전으로 여러 번 실행한 결과가 섞여 있으면 최신 파일이 반드시 대표값은 아닐 수 있다 — 완화책: 문서에 "그룹당 여러 실행이 있으면 `agent-eval trend --pattern`으로 해당 버전 파일만 필터링해 추세를 먼저 확인하라"고 명시, 이 스펙에서 평균/집계 로직을 새로 만들지 않는다(Non-Goals 성격).
- **pairwise judge의 비용 2배(REQ-4 `swap_check=True` 기본값)**: 절대 스코어 대비 API 호출이 늘어난다 — 완화책: `swap_check=False` 탈출구 제공, `compare_results(pairwise=True)`도 옵트인(기본 `False`)으로 기존 호출 비용에 영향 없음.
- **골든셋 `question` 텍스트 매칭 폴백의 취약성(REQ-6)**: `task_id`가 없는 골든셋 항목은 텍스트 완전 일치로 매칭하므로, 질문이 약간이라도 다르게 재구성되면 거짓 커버리지 누락으로 잡힐 수 있다 — 완화책: 문서에 "골든셋은 가능하면 원본 `task_id`를 보존한 채 병합하라"고 명시(`golden.py:527`이 이미 이를 보존하므로 정상 경로에서는 발생하지 않음), 텍스트 매칭은 어디까지나 폴백.
- **버전별 baseline 파일이 무한정 누적됨(REQ-3)**: `baselines/` 디렉토리에 실험이 늘어날수록 파일이 쌓인다 — 완화책: 이 스펙에서 자동 정리 로직을 추가하지 않고, 정리는 사람이 판단할 몫으로 남긴다(SPEC-021의 "자동 하향 없음" 원칙과 동일한 성격).
