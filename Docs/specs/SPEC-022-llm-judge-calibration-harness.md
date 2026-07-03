# SPEC-022: LLM Judge 검증 하네스 (사람 라벨 합의도 리포트)

**Phase:** P6 (SDK 전반 성숙도 — 엔터프라이즈 신뢰성) · **상태:** Implemented (2026-07-04) · **의존성:** 없음 (기존 `LLMJudge.judge()`를 그대로 호출만 함, 새 외부 의존성 없음)

> **구현 노트 (2026-07-04)**: `agent_evaluator/integrations/llm_judge_calibration.py` 신설 —
> `compute_agreement()`/`_weighted_kappa()`(REQ-3~4), `CalibrationCase`/`LLMJudgeCalibration`
> (REQ-2,5~6), `load_cases_from_json()`(REQ-7) 전부 구현. `tests/test_llm_judge_calibration.py`
> (10건)로 검증 — 순수 함수(완전 일치/상수 배열/길이 불일치), `LLMJudge._call_judge`를
> 스텁한 통합 테스트(스킵 처리·`None` faithfulness 제외 확인), `load_cases_from_json` 왕복.
> **`_weighted_kappa`를 scikit-learn의 `cohen_kappa_score`와 교차검증하는 과정에서 실제로
> 잡은 테스트 설계 결함 1건**: 이 개발 환경에 우연히 설치된 sklearn으로 무작위 정수
> 시퀀스를 비교했더니 처음엔 값이 갈렸다(-0.5625 vs -0.5) — 원인은 sklearn의
> `cohen_kappa_score`가 `labels` 인자를 생략하면 "이 표본에서 실제 관측된 값들"만으로
> 카테고리를 잡는데, 무작위 소표본(5~30개)은 0-5 전체를 다 포함하지 않을 때가 많아 더
> 좁은 범위로 계산되기 때문이었다 — 반면 이 스펙의 `_weighted_kappa`는 의도적으로
> "이론적 전체 스케일(0-5)"을 고정 사용한다(LLMJudge 점수는 항상 0-5 스케일이므로 이게
> 맞는 설계). 버그는 구현이 아니라 테스트 쪽에 있었다 — sklearn 호출에
> `labels=list(range(6))`을 명시하자 20세트×2가중치 전부 부동소수 오차 이내로 일치했다.
> 이 스펙의 신규 테스트는 10건이며, 이번 세션에서 추가된 SPEC-020/022 전체 테스트를
> 포함한 전체 스위트가 **3,218 passed, 1 skipped, 회귀 0건**으로 통과함을 확인했다.

## Context

- `LLMJudge`(`agent_evaluator/integrations/llm_judge.py`)는 응답을 최대 7개 이상 차원에서 채점하는데, 모듈 docstring(`llm_judge.py:6`)이 명시하듯 **"ground_truth 없이" 채점하도록 설계**됐다 — 즉 이 judge 자체가 실제로 사람 판단과 얼마나 일치하는지 검증하는 장치가 SDK 어디에도 없다. `grep -in "human|calibrat|kappa|agreement|ground_truth"`를 `llm_judge.py` 전체에 돌려도 이 docstring 한 줄 외엔 아무것도 없다(직접 확인).
- `judge()`(`llm_judge.py:374-380`)/`ajudge()`(`:514-520`)가 반환하는 `result["scores"]`의 정확한 스케일(직접 확인, `llm_judge.py:803-862`):
  - `completeness`/`relevance`/`factual_consistency`/`toxicity`/`bias`/`faithfulness`(context 있을 때만)/`criteria_scores`의 각 항목 — **정수 0-5**(`faithfulness`는 모델이 필드를 누락하면 0이 아니라 `None`으로 기록돼 평균을 오염시키지 않음, `:830-844`).
  - `overall`(`completeness+relevance+factual_consistency`의 평균, `:809`)/`criteria_overall`/`safety_score`/`confidence` — **실수**(정수가 아닐 수 있음).
  - `sample_rate` 게이트(`:408-410`)로 인해 `judge()`가 `{"skipped": True}`만 반환할 수 있다 — `gates/shared_metrics.py:616-617`이 쓰는 것과 같은 `(_lj or {}).get("skipped")` 관용구가 이미 SDK 컨벤션으로 자리잡고 있다.
- `datasets/builder.py`의 `GoldenSetBuilder`(골든셋 큐레이션 도구)에는 사람이 매긴 **점수**를 저장하는 필드가 전혀 없다 — `extract()`가 붙이는 건 `_requires_review`(bool, `:114`)뿐이고, `serve/routers/golden.py`의 승인 플로우도 `_approved`/`_rejected`(bool, `:426-427,448-449`) 같은 이진 플래그만 다룬다(직접 확인). 즉 "사람이 0-5 점수를 매긴 값"을 저장/비교하는 자리 자체가 없다.
- `TaskResult`(`core/trackers/base.py:41-70`)에도 사람 라벨 전용 필드가 없다 — 새 필드를 추가하려면 frozen dataclass 스키마·`to_dict()`/`from_dict()`·SQLite 저장 전부에 영향이 번진다. 이번 스펙은 그 경로를 건드리지 않고, **`TaskResult`와 완전히 분리된 오프라인 검증 도구**로 설계한다(Goals 참조) — 골든셋 검증은 애초에 라이브 파이프라인에 얹을 필요가 없는 별도 작업 흐름이기 때문이다.
- 통계 의존성 확인 결과(`pyproject.toml` 직접 확인): `scikit-learn`은 코어·extras 어디에도 선언돼 있지 않다(0건). `scipy`도 선언된 의존성은 아니지만, `quick_eval.py:1538-1548`의 `QuickEval.ab_test()`가 이미 `try: from scipy import stats ... except ImportError: pass` 형태의 **소프트 임포트 관용구**를 쓰고 있다 — 이번 스펙은 Cohen's kappa(scikit-learn 없이) 자체를 직접 구현해 이 소프트 의존성 문제를 아예 피한다(코어 의존성인 numpy만 사용).
- 기존 `LLMJudge` 테스트(`tests/test_llm_judge_concurrency.py`)는 `monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)`로 실제 API 호출을 스텁하는 패턴을 확립해 뒀다(`:296` 등, 직접 확인) — 이번 스펙의 테스트도 동일 패턴을 따른다.

## Goals

- 사람이 소규모 골든셋(수십 건 규모를 전제)에 `question`/`response`(+선택 `context`)와 각 차원별 점수(`human_scores`, 예: `{"overall": 4, "faithfulness": 5}`)를 매겨두면, 기존 `LLMJudge.judge()`를 그대로 호출해 얻은 자동 점수와 비교해 차원별 합의도 지표(평균절대오차, Pearson 상관, Cohen's kappa)를 리포트한다.
- `LLMJudge`의 채점 로직 자체는 한 줄도 바꾸지 않는다 — 이미 있는 `judge()`를 호출해 얻은 결과를 소비만 하는 별도 레이어.
- scikit-learn/scipy 없이(코어 의존성 numpy만으로) Cohen's kappa(linear/quadratic weighted)를 직접 구현해, 이 기능이 옵셔널 의존성 유무에 따라 조용히 빠지는 일이 없게 한다.

## Non-Goals

- `TaskResult`에 사람 라벨 필드를 추가하는 것 — 완전히 분리된 오프라인 도구로 설계한다(Context 참조).
- `GoldenSetBuilder`/`serve/routers/golden.py`의 승인(`_approved`/`_rejected`) 플로우를 사람 점수 라벨링 UI로 확장하는 것 — 이번 스펙은 라벨을 이미 갖고 있다고 가정하고 비교 리포트만 만든다. UI/워크플로우는 별도 스펙.
- CLI 서브커맨드 추가(`agent-eval judge-calibrate` 같은) — 이번 스펙은 Python API로 한정한다. 필요해지면 후속 스펙으로 분리.
- 비동기(`ajudge()`) 경로 지원 — 검증 골든셋은 통상 수십 건 규모라 순차 동기 호출로 충분하다고 보고, 동시성은 범위 밖으로 둔다.
- `confidence`/`safety_score`처럼 사람이 직접 채점하기보다 다른 차원에서 파생되는 값에 대한 특별 처리 — 사용자가 그 차원에 대해 `human_scores`를 제공하면 그대로 비교하되(같은 로직 재사용), 의미 있는 해석은 사용자 책임으로 문서에만 명시한다.

## Requirements

- **REQ-1**: 신규 모듈 `agent_evaluator/integrations/llm_judge_calibration.py`.
- **REQ-2**: `CalibrationCase` 데이터클래스 — `task_id: str`, `question: str`, `response: str`, `human_scores: Dict[str, float]`, `context: Optional[str] = None`.
- **REQ-3**: `compute_agreement(judge_scores: Sequence[float], human_scores: Sequence[float], category_range: Tuple[int, int] = (0, 5)) -> Dict[str, Any]` — 두 점수 시퀀스(길이 같아야 함, 다르면 `ValueError`)에서:
  - `n`(개수), `mean_absolute_error`(원점수 기준), `pearson_r`(원점수 기준, 둘 중 하나라도 표준편차 0이면 `None`, `n<2`면 `None`),
  - `exact_match_rate`, `cohen_kappa_linear`, `cohen_kappa_quadratic` — 이 3개는 `category_range`로 반올림·클램프한 정수 카테고리 기준.
  - `n=0`이면 `{"n": 0}`만 반환.
- **REQ-4**: Cohen's weighted kappa를 scikit-learn 없이 numpy만으로 직접 구현(`kappa = 1 - sum(W*O)/sum(W*E)`, `O`=혼동행렬, `E`=주변분포 외적, `W`=linear(`|i-j|/(k-1)`) 또는 quadratic(`(i-j)^2/(k-1)^2`) 가중치 행렬 — 표준 공식, scikit-learn의 `cohen_kappa_score(weights=...)`와 동일한 결과를 내야 한다).
- **REQ-5**: `LLMJudgeCalibration` 클래스 — 생성자는 기존 `LLMJudge` 인스턴스를 받는다(`__init__(self, judge: LLMJudge)`, 새 judge 로직을 만들지 않음). `run(self, cases: List[CalibrationCase]) -> Dict[str, Any]` 메서드가:
  1. 각 `case`에 대해 `self._judge.judge(case.task_id, case.question, case.response, context=case.context)` 호출.
  2. 스킵된(`skipped=True`) 케이스는 비교 대상에서 제외하되, 리포트에 `skipped_count`로 몇 건이 빠졌는지 노출한다(REQ-6) — `sample_rate<1.0`인 judge를 실수로 넘겨 조용히 적은 표본으로 리포트되는 걸 방지.
  3. `case.human_scores`에 등장하는 모든 차원 이름을 모아, 각 차원에 대해 judge 점수와 사람 점수가 **둘 다 존재하는**(judge 쪽이 `None`이 아닌) 페어만 모아 `compute_agreement()`를 호출.
- **REQ-6**: `run()`의 반환 형식:
  ```python
  {
      "n_cases": int,
      "skipped_count": int,
      "dimensions": {
          "<dim_name>": {...compute_agreement() 결과...} | {"n": 0, "note": "no comparable (judge, human) pairs"},
          ...
      },
  }
  ```
- **REQ-7**: 편의 함수 `load_cases_from_json(path: str) -> List[CalibrationCase]` — `[{"task_id", "question", "response", "human_scores", "context"?}, ...]` 형식의 JSON 파일을 읽어 `CalibrationCase` 리스트로 변환.

## Interface

```python
from agent_evaluator import LLMJudge
from agent_evaluator.integrations.llm_judge_calibration import (
    CalibrationCase, LLMJudgeCalibration, compute_agreement, load_cases_from_json,
)

# 골든셋 검증 시에는 sample_rate=1.0 권장(전수 채점) — run()이 skipped_count로 누락을 알려주지만
# 애초에 전부 채점되게 구성하는 게 자연스럽다.
judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0)

cases = [
    CalibrationCase(
        task_id="g1", question="...", response="...",
        human_scores={"overall": 4, "faithfulness": 5},
    ),
    # 또는: cases = load_cases_from_json("golden_calibration_set.json")
]

report = LLMJudgeCalibration(judge).run(cases)
# {
#   "n_cases": 1, "skipped_count": 0,
#   "dimensions": {
#     "overall": {"n": 1, "mean_absolute_error": 0.33, "pearson_r": None, ...},
#     "faithfulness": {"n": 1, ...},
#   },
# }
```

## Acceptance

- **REQ-3/4 (완전 일치)**: judge/human 점수가 완전히 동일한 리스트 → `mean_absolute_error=0`, `exact_match_rate=1.0`, `cohen_kappa_quadratic`/`cohen_kappa_linear` 둘 다 `1.0`(카테고리가 2개 이상 다양할 때).
- **REQ-3 (상수 배열)**: `judge_scores`가 전부 같은 값이면 `pearson_r=None`(표준편차 0으로 상관계수 미정의).
- **REQ-3 (길이 불일치)**: `ValueError` 발생 확인.
- **REQ-4 (scikit-learn 대조)**: 이 개발 환경에 우연히 설치된 `sklearn.metrics.cohen_kappa_score(y1, y2, weights="quadratic"/"linear")`와 직접 구현한 `_weighted_kappa()`가 무작위 정수 시퀀스 여러 세트에서 동일한 값(부동소수 오차 이내)을 내는지 교차검증(`pytest.importorskip("sklearn")`로 감싸 sklearn 없는 환경에서는 스킵).
- **REQ-5/6**: `monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)`로 고정된 점수를 반환하는 가짜 judge를 꽂고, 여러 `CalibrationCase`에 대해 `run()`을 호출 — `dimensions`에 사람 라벨을 매긴 차원만 나타나고, 라벨 없는 차원은 나타나지 않는지 확인.
- **REQ-5 (스킵 처리)**: `sample_rate=0.0`인 judge로 `run()` 호출 → 모든 케이스가 스킵되어 `skipped_count == n_cases`이고 각 차원이 `{"n": 0, "note": ...}`인지 확인.
- **REQ-5 (None 필드 제외)**: `context`를 안 준 케이스의 `faithfulness`가 `None`인 상황에서, 그 차원에 사람 라벨이 있어도 해당 케이스가 페어에서 제외되는지 확인(judge 쪽 `None` 필터링).
- **REQ-7**: 임시 JSON 파일을 만들어 `load_cases_from_json()`으로 읽고 `CalibrationCase` 필드가 정확히 매핑되는지 확인.

## Compatibility

- 완전히 새로운 모듈 — 기존 `LLMJudge`/`gates/*`/`monitor.py`의 어떤 코드 경로도 수정하지 않는다(순수 additive).
- 새 하드 의존성 없음(numpy는 이미 코어 의존성).

## Rollout

1. `agent_evaluator/integrations/llm_judge_calibration.py` 신설(REQ-1~4: `compute_agreement`/`_weighted_kappa`).
2. `CalibrationCase`/`LLMJudgeCalibration`/`load_cases_from_json` 구현(REQ-2,5-7).
3. 단위 테스트(순수 함수 `compute_agreement`/`_weighted_kappa`, scikit-learn 교차검증) + 통합 테스트(`_call_judge` 스텁 + `LLMJudgeCalibration.run()`).
4. 전체 스위트 통과 확인 후 상태를 Draft → Implemented로 갱신, `Docs/specs/README.md` 인덱스 등록.

## Risks

- **소규모 표본에서 kappa/상관계수의 통계적 불안정성**: 골든셋이 수십 건 이하로 작으면 이 지표들 자체의 신뢰구간이 넓다 — 이 스펙은 "지표를 계산해 보여준다"까지만 하고, "표본이 몇 건 이상이어야 신뢰할 수 있다" 같은 통계적 유의성 가드는 범위 밖으로 둔다(SPEC-002의 min-sample 가드와는 별개 문제 — 필요하면 후속 스펙에서 다룰 것).
- **`overall`처럼 원래 연속값인 차원에 kappa를 적용하는 것의 해석 한계**: 정수 반올림 후 카테고리화해서 계산하므로, 소수점 차이(예: judge 3.67 vs human 4)가 카테고리상 "일치"로 뭉개질 수 있다 — `mean_absolute_error`/`pearson_r`(반올림하지 않은 원점수 기준)를 함께 보고해 이 손실을 보완한다.
- **사람 라벨 자체의 신뢰도(inter-rater reliability)는 이 스펙 범위 밖**: 여러 사람이 라벨링해 사람들 사이의 합의도까지 검증하는 건 다루지 않는다 — 이 스펙은 "이미 확정된 사람 라벨 1세트" 대 "judge 점수"의 비교만 다룬다.
