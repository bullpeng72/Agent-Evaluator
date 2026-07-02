# SPEC-010: CI/CD 게이트 베이스라인 통합

**Phase:** P3 · **상태:** Draft · **의존성:** 없음

## Context

- `agent_evaluator/quick_eval.py::HarnessEvaluationGate.evaluate()`는 정적 임계값 비교만 수행한다(`gate.evaluate()`는 인자 없이 현재 리포트만 보고 판정).
- 베이스라인 비교(회귀 탐지)는 `QuickEval.for_regression_eval(baseline_file=..., regression_threshold=0.05)` + `check_regression()`(`quick_eval.py:553-629`)이라는 **완전히 별도의 옵트인 팩토리**로만 존재한다.
- CLI `agent-eval gate` 커맨드는 `--tcr`/`--accuracy` 등 정적 임계값 플래그만 받고, `--baseline`류 옵션이 기본 워크플로우에 통합되어 있지 않다(`cli/main.py`의 `gate` 서브커맨드는 `trend` 서브커맨드의 `--save-baseline`/`--fail-on-regression`과 분리된 별개 경로).
- 결과적으로 "이번 배포가 정적 임계값은 통과했지만 이전 배포보다 확실히 나빠졌다"는 상황을 기본 `gate` 워크플로우가 놓칠 수 있다.

## Goals

- `agent-eval gate` 기본 워크플로우에 베이스라인 비교를 1급 옵션으로 통합해, 정적 임계값 통과와 회귀 없음을 함께 확인하는 것을 기본 관행으로 만든다.

## Non-Goals

- `for_regression_eval`/`trend` 커맨드의 기존 동작 변경 — 그대로 유지, `gate` 커맨드에 동등 기능을 추가 통합하는 것이 목표.
- 베이스라인 저장 포맷 변경.

## Requirements

- **REQ-1**: `HarnessEvaluationGate.evaluate(baseline: Optional[dict] = None, regression_threshold: float = 0.05)`로 확장 — `baseline`이 주어지면 정적 임계값 판정에 더해 각 Gate 점수가 베이스라인 대비 `regression_threshold`를 초과해 하락했는지 함께 판정하고, 하나라도 회귀가 있으면 `result["passed"] = False`, `result["regressions"]`에 상세 목록을 포함한다.
- **REQ-2**: CLI `agent-eval gate result.json --baseline baseline.json [--regression-threshold 0.05]` 옵션 추가.
- **REQ-3**: `baseline` 미지정 시 기존 동작(정적 임계값만)과 100% 동일 — 하위호환.
- **REQ-4**: `agent-eval gate --save-baseline`로 현재 결과를 다음 베이스라인으로 저장하는 옵션 추가(수동으로 `for_regression_eval` 워크플로우를 거치지 않아도 되도록).

## Interface

```python
# 변경 전
gate = HarnessEvaluationGate(report)
result = gate.evaluate()

# 변경 후 (하위호환 — baseline 생략 시 기존과 동일)
gate = HarnessEvaluationGate(report)
result = gate.evaluate(baseline=baseline_report_dict, regression_threshold=0.05)
# result: {..., "regressions": [{"gate": "A", "baseline_score": 0.82, "current_score": 0.74, "delta": -0.08}]}
```

```bash
# 변경 후 CLI
agent-eval gate result.json --tcr 85 --accuracy 70 --baseline results/baseline.json --regression-threshold 0.05
agent-eval gate result.json --save-baseline  # 현재 결과를 다음 비교 기준으로 저장
```

## Acceptance

- `baseline` 미지정 시 기존 `gate` 관련 테스트 전량 통과(회귀 없음).
- 베이스라인 대비 5% 초과 하락 픽스처에서 `passed=False` + `regressions` 목록에 해당 Gate 포함 검증.
- 베이스라인 대비 하락이 임계값 이내인 픽스처에서 `passed` 판정이 정적 임계값 결과만으로 결정되는지(회귀 없음으로 처리) 검증.

## Compatibility

- 완전 하위호환 — `baseline` 파라미터/CLI 옵션 모두 선택.

## Rollout

1. `HarnessEvaluationGate.evaluate()`에 `baseline`/`regression_threshold` 파라미터 추가.
2. CLI `gate` 서브커맨드에 `--baseline`/`--regression-threshold`/`--save-baseline` 옵션 추가.
3. 문서(`Docs/05_QUALITY_GATE.md`)에 "정적 임계값 + 베이스라인 비교를 함께 쓰는 것을 기본 권장 워크플로우"로 갱신.

## Risks

- 베이스라인 파일 포맷이 `for_regression_eval`의 것과 동일해야 재사용 가능 — 포맷 불일치 시 별도 변환 로직 필요 여부 확인.
