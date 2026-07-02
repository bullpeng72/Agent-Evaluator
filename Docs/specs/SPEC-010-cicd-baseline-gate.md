# SPEC-010: CI/CD 게이트 베이스라인 통합 — Harness Gate A–G 회귀 탐지 확장

**Phase:** P3 · **상태:** Implemented (2026-07-02) · **의존성:** 없음

> **구현 노트**: `agent_evaluator/quick_eval.py`에 공유 헬퍼 `_compute_gate_regressions()`(회귀
> 판정 공식 — `cli/gate.py::_check_regression()`과 동일한 `direction="min"` 방식)와
> `_normalize_gate_score_dict()`(평면 dict·리포트 형식 dict 양쪽 지원)를 추가해 CLI와 Python API가
> 판정 로직을 공유하도록 했다(REQ-2/REQ-3 "로직 공유" 목표 달성). **CLI**: `cli/gate.py`의
> `_save_baseline()`이 `harness_scores` 파라미터를 받아 `baseline.json`에 `"gate_scores"` 키로
> A–G 점수를 함께 저장(REQ-1, 실제 값이 하나도 없으면 키 자체를 생략해 무의미한 all-None 저장 방지).
> `cmd_gate()`의 `--fail-on-regression` 블록이 `_compute_gate_regressions()`로 Gate A–G 회귀도
> 함께 검사해 CLI의 `regressions` 리스트에 병합(REQ-2) — 구버전 `baseline.json`(`gate_scores` 키
> 없음)을 읽어도 크래시 없이 해당 검사만 건너뛴다(하위호환, Acceptance에 명시된 케이스 검증 완료).
> **Python API**: `HarnessEvaluationGate.evaluate(baseline=None, regression_threshold=0.05)`로
> 확장(REQ-3) — `baseline`은 평면 dict(`{"A": 0.82, ...}`)와 리포트 형식 dict(`{"A": {"score": 0.82}}`)
> 모두 지원. `enforce()`도 `baseline`/`regression_threshold`를 받아 그대로 전달하도록 확장해 CI
> 엔트리포인트에서 베이스라인 회귀 시에도 `sys.exit(1)`이 발동하게 했다(스펙에 명시되지 않았지만
> REQ-3의 "CI 게이트가... 확인" 목표를 실제로 달성하려면 필요한 자연스러운 확장). `baseline` 미지정
> 시(기본값) 결과 dict에 `"regressions"` 키 자체가 생기지 않아 REQ-4 하위호환을 만족한다.
> 신규 테스트 `tests/test_spec010_gate_regression.py`(24건 — 공유 헬퍼 단위 테스트, Python API
> baseline 회귀/무회귀/enforce 검증, CLI save-baseline/fail-on-regression 통합 검증, 구버전
> baseline.json 하위호환 검증 포함), 기존 `tests/test_coverage_cli_gate.py`(38건)·
> `tests/test_improvements_decorators.py`(207건) 무수정 통과. 전체 스위트 3,046 passed, 1 skipped,
> 회귀 0건.
>
> **의도적으로 다루지 않은 것**: Risks에서 지적한 "3개의 독립적인 베이스라인 비교 구현" 문제 중
> `QuickEval.for_regression_eval`과의 통합은 이번 스펙 범위 밖으로 그대로 남겨뒀다 — CLI↔Python API
> 사이의 중복만 제거했을 뿐, `for_regression_eval`은 여전히 완전히 별개의 세 번째 경로다.

> **재검증 노트(2026-07-02)**: 최초 작성 시점의 Context는 부정확했다 — 직접 코드를 다시 대조한 결과
> `agent_evaluator/cli/gate.py`(873줄)에 이미 상당히 성숙한 베이스라인/회귀 비교 시스템이 **구현되어
> 있음**을 확인했다(`--baseline`/`--save-baseline`/`--fail-on-regression`, 2026-07-02 기준 존재).
> 다만 이 시스템은 TCR/accuracy/p95_latency/hallucination/llm_judge_overall **5개 평면 지표에만**
> 적용되고, Harness Gate A–G 복합/개별 점수(`--min-gate-score`/`--gate-thresholds`)는 **정적 임계값
> 검사만 있고 회귀 비교 대상이 아니다** — 이것이 실제로 남아있는 갭이다. 아래 Context/Goals/
> Requirements를 이 재조사 결과에 맞춰 전면 재작성했다.

## Context

- `agent_evaluator/cli/gate.py::_check_regression()`(`:378-427`)와 `_load_metrics()`(`:46-`)는
  `_GATE_DEFS`(`:305-311`, `tcr`/`accuracy`/`p95_latency`/`hallucination`/`llm_judge_overall` 5개
  키)에 대해서만 베이스라인 대비 회귀를 판정한다. `cmd_gate()`(`:708-`)가
  `--baseline`(`cli/main.py:918-921`)/`--save-baseline`(`:922-925`)/`--fail-on-regression`
  (`:914-917`) 3개 CLI 옵션을 이미 완전히 배선해 두었고, `_save_baseline()`(`:290-296`)로
  `<result_dir>/baseline.json`(`_default_baseline_path`, `:274-276`)에 저장한다 — **최초 작성 시
  "베이스라인류 옵션이 통합되어 있지 않다"고 기재했던 것은 오류였다.**
- 반면 `--min-gate-score`/`--gate-thresholds`/`--group-weights`/`--required-gates`/
  `--fail-on-gate-warn`(`cli/main.py:930-961`)로 구현된 Harness Gate A–G 복합/개별 점수 검사
  (`_load_harness_groups()` `:154-173`, `_compute_composite_gate()` `:244-`, `cmd_gate()` 내부
  `:771-827`)는 **정적 임계값 비교만** 수행한다 — `_check_regression()`은 `_GATE_DEFS`만 순회하므로
  `harness_groups`(A–G)의 어떤 점수도 베이스라인과 비교되지 않는다(직접 코드 대조로 확인). 즉
  "이번 배포가 Gate D(성능) 정적 임계값은 통과했지만 이전 배포보다 확실히 나빠졌다"는 상황을
  여전히 놓칠 수 있다 — **이것이 이번 스펙의 실제 남은 목표다.**
- `_save_baseline()`이 저장하는 `payload`는 `metrics`(5개 평면 지표 + `total_cost`)만 담고
  `harness_groups` 점수는 포함하지 않는다(`:290-296` 직접 확인) — REQ-2가 확장해야 할 지점.
- `agent_evaluator/quick_eval.py::HarnessEvaluationGate.evaluate()`(Python API, CLI의
  `cli/gate.py`와는 **완전히 독립된 별개 구현** — `cli/gate.py`는 `HarnessEvaluationGate`를
  import하지 않음, grep으로 확인)는 여전히 인자 없이 정적 임계값만 판정한다 — 이 부분은
  최초 작성 내용 그대로 정확하다.
- `QuickEval.for_regression_eval(baseline_file=..., regression_threshold=0.05)` +
  `check_regression()`(`quick_eval.py:553-629`, 라인 번호 재확인 완료·변동 없음)은 여전히
  세 번째의, 또 다른 독립적인 베이스라인 비교 경로다 — `cli/gate.py`·`HarnessEvaluationGate`
  어느 쪽과도 코드를 공유하지 않는다. 이 코드베이스에 "베이스라인 비교"가 **서로 겹치지 않는
  3개의 독립 구현**(`for_regression_eval`, `cli/gate.py`, 그리고 `HarnessEvaluationGate`가
  이번 스펙으로 4번째가 될 위험)으로 존재한다는 것 자체가 구조적 리스크다(Risks 참고).

## Goals

- **Harness Gate A–G 점수를 베이스라인 회귀 비교 대상에 포함**시켜, 5개 평면 지표뿐 아니라
  Gate 단위 점수 하락도 CI에서 탐지되게 한다(현재 가장 실질적인 갭).
- `HarnessEvaluationGate`(Python API)에도 동등한 베이스라인 비교 기능을 추가해, CLI 전용이 아닌
  프로그래밍 방식 사용자도 회귀 탐지를 쓸 수 있게 한다.
- 위 두 목표를 구현할 때 **가능하면 로직을 공유**해 4번째 독립 구현이 되지 않도록 한다.

## Non-Goals

- `QuickEval.for_regression_eval`/`trend` 커맨드의 기존 동작 변경 — 그대로 유지한다.
- `cli/gate.py`의 5개 평면 지표(`tcr`/`accuracy`/`p95_latency`/`hallucination`/`llm_judge_overall`)
  회귀 비교 로직 자체 변경 — 이미 완전히 동작하므로 건드리지 않는다. 이번 스펙은 여기에
  Harness Gate A–G를 **추가**하는 것이지, 기존 것을 고치는 것이 아니다.
- 베이스라인 파일 포맷의 하위호환 파괴 — 기존 `baseline.json`에 필드를 추가하는 것은 허용하되,
  기존 필드 제거/이름 변경은 하지 않는다.
- 3개의 독립 구현을 하나로 통합하는 대규모 리팩터(Risks에서 언급하되, 이번 스펙 범위는 아님 —
  통합은 그 자체로 별도 스펙이 필요한 규모).

## Requirements

- **REQ-1**: `cli/gate.py::_load_metrics()`/`_save_baseline()`가 `harness_groups`의 A–G 점수도
  함께 로드/저장하도록 확장한다(예: `metrics["gate_A"]`~`metrics["gate_G"]` 또는 별도
  `harness_scores` 하위 dict — 기존 `baseline.json`에 필드 추가, 기존 5개 지표 필드는 그대로 둔다).
- **REQ-2**: `_check_regression()`(또는 이를 감싸는 새 함수)이 `--fail-on-regression` 사용 시
  A–G 점수의 베이스라인 대비 하락도 함께 판정하도록 확장한다. 판정 기준은 기존 5개 지표와
  동일한 `direction="min"` 방식(현재값이 `baseline × (1 - tolerance)` 미만이면 회귀)을 그대로
  적용한다 — 새 판정 방식을 발명하지 않는다.
- **REQ-3**: `HarnessEvaluationGate.evaluate(baseline: Optional[dict] = None, regression_threshold: float = 0.05)`로
  확장한다 — `baseline`이 주어지면 정적 임계값 판정에 더해 각 Gate 점수의 베이스라인 대비 하락을
  REQ-2와 **동일한 판정 공식**으로 검사하고, 하나라도 회귀가 있으면 `result["passed"] = False`,
  `result["regressions"]`에 상세 목록을 포함한다. 가능하면 REQ-2에서 만든 회귀 판정 헬퍼를
  `cli/gate.py`와 `quick_eval.py` 양쪽에서 import해 공유한다(Goals의 "로직 공유" 목표).
- **REQ-4**: `baseline`/`--baseline`(A–G 확장분) 미지정 시 두 경로(Python API·CLI) 모두 기존
  동작과 100% 동일 — 하위호환. CLI의 기존 5개 평면 지표 회귀 비교는 이번 스펙과 무관하게 계속
  그대로 동작해야 한다(회귀 테스트 대상).

## Interface

```python
# 변경 전 (HarnessEvaluationGate, Python API — 여전히 베이스라인 미지원)
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

# 변경 후 (하위호환 — baseline 생략 시 기존과 동일)
gate = HarnessEvaluationGate(report)
result = gate.evaluate(baseline=baseline_report_dict, regression_threshold=0.05)
# result: {..., "regressions": [{"gate": "A", "baseline_score": 0.82, "current_score": 0.74, "delta": -0.08}]}
```

```bash
# 변경 전 CLI (이미 동작함 — 5개 평면 지표만 회귀 비교 대상)
agent-eval gate result.json --tcr 85 --fail-on-regression 10 --baseline results/baseline.json
agent-eval gate result.json --save-baseline

# 변경 후 CLI (REQ-1/2 — Harness Gate A–G도 baseline.json에 저장되고 회귀 비교 대상에 포함됨)
agent-eval gate result.json --min-gate-score 0.7 --fail-on-regression 10 --baseline results/baseline.json
# → baseline.json에 저장된 과거 Gate D 점수 대비 현재 Gate D 점수가 10% 초과 하락하면
#   exit code 2(회귀 감지)
```

## Acceptance

- **REQ-1/2(CLI)**: `--save-baseline`로 저장한 `baseline.json`에 A–G 점수가 포함되는지 확인.
  이후 Gate 점수가 하락한 결과 파일로 `--fail-on-regression`을 실행하면 exit code 2와 함께
  회귀 목록에 해당 Gate가 포함되는지 검증. 기존 5개 평면 지표만 있던 시절의 `baseline.json`
  (A–G 필드 없음)을 읽어도 크래시 없이 동작하는지(구버전 베이스라인 파일 하위호환) 검증.
- **REQ-3(Python API)**: 베이스라인 대비 5% 초과 하락 픽스처에서 `passed=False` + `regressions`
  목록에 해당 Gate 포함 검증. 베이스라인 대비 하락이 임계값 이내인 픽스처에서 `passed` 판정이
  정적 임계값 결과만으로 결정되는지(회귀 없음으로 처리) 검증.
- **REQ-4**: `baseline` 미지정 시 `cli/gate.py`·`HarnessEvaluationGate` 관련 기존 테스트 전량
  무수정 통과(회귀 없음).

## Compatibility

- CLI: 기존 `baseline.json` 포맷에 필드를 **추가**하므로 완전 하위호환 — 구버전 파일에 A–G
  필드가 없어도 신버전 코드가 정상 동작해야 한다(REQ-1 Acceptance에 명시).
- Python API: `baseline`/`regression_threshold` 파라미터 모두 선택값 — 기존 `HarnessEvaluationGate(...)`
  생성·`evaluate()` 호출 코드는 수정 없이 그대로 동작.

## Rollout

1. REQ-1: `cli/gate.py::_load_metrics()`/`_save_baseline()`에 harness_groups A–G 필드 추가.
2. REQ-2: `_check_regression()`을 A–G 포함하도록 확장(또는 병행 헬퍼 추가) — 기존 5개 지표
   판정 결과가 달라지지 않는지 회귀 테스트로 고정.
3. REQ-3: 위에서 만든 판정 헬퍼를 재사용해 `HarnessEvaluationGate.evaluate()`에 `baseline`/
   `regression_threshold` 파라미터 추가.
4. 문서(`Docs/05_QUALITY_GATE.md`)에 "Harness Gate A–G도 이제 베이스라인 회귀 비교 대상"임을
   명시하고, 이 코드베이스에 존재하는 3(+1)개의 베이스라인 비교 경로(`for_regression_eval`/
   `cli gate`/`HarnessEvaluationGate`) 각각의 용도 차이를 표로 정리해 사용자 혼동을 줄인다.

## Risks

- **구조적 리스크(신규 발견)**: 이 코드베이스에는 이미 서로 코드를 공유하지 않는 3개의 독립적인
  "베이스라인 비교" 구현(`QuickEval.for_regression_eval`, `cli/gate.py`, 그리고 이번 스펙으로
  베이스라인을 갖게 될 `HarnessEvaluationGate`)이 존재하게 된다 — 유지보수 시 판정 로직을 한 곳만
  고치고 나머지를 놓칠 위험이 실재한다. 완화책: REQ-2/REQ-3가 동일한 회귀 판정 헬퍼를 공유하도록
  구현해 최소한 CLI↔Python API 사이의 중복은 만들지 않는다. `for_regression_eval`과의 통합은
  이번 스펙 범위 밖(별도 스펙 후보로 백로그에 남긴다).
- 베이스라인 파일 포맷에 A–G 필드를 추가하는 시점에 이미 저장된 구버전 `baseline.json`을 읽는
  경로가 있다면(REQ-1 Acceptance의 하위호환 케이스), `None`/누락 필드 처리를 빠뜨리면 회귀 비교가
  조용히 스킵되거나 예외가 발생할 수 있음 — `.get()` 기반 안전한 접근으로 방어.
