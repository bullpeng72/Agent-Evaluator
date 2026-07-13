"""
agent_evaluator.integrations.llm_judge_calibration
======================================================
SPEC-022: LLM Judge 검증 하네스 — 소규모 사람 라벨 골든셋에 대해 기존 ``LLMJudge.judge()``
가 낸 자동 점수와 사람 점수 간 합의도(agreement)를 차원별로 리포트한다.

``LLMJudge``의 채점 로직 자체는 전혀 바꾸지 않는다 — 이미 있는 ``judge()``를 그대로
호출해 얻은 결과를 사람 라벨과 비교하는 별도 레이어다. scikit-learn/scipy 없이(코어
의존성 numpy만으로) Cohen's weighted kappa를 직접 구현해, 이 검증 기능이 옵셔널
의존성 유무에 따라 조용히 빠지는 일이 없게 한다.

Example::

    from agent_evaluator import LLMJudge
    from agent_evaluator.integrations.llm_judge_calibration import (
        CalibrationCase, LLMJudgeCalibration,
    )

    # 골든셋 검증 시에는 sample_rate=1.0 권장(전수 채점)
    judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0)
    cases = [
        CalibrationCase(
            task_id="g1", question="...", response="...",
            human_scores={"overall": 4, "faithfulness": 5},
        ),
    ]
    report = LLMJudgeCalibration(judge).run(cases)
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Sequence, Union

import numpy as np

from agent_evaluator.integrations.llm_judge import LLMJudge


@dataclasses.dataclass
class CalibrationCase:
    """검증용 골든 케이스 1건 — question/response(+선택 context)와 사람이 매긴 차원별 점수."""

    task_id: str
    question: str
    response: str
    human_scores: dict[str, float]
    context: str | None = None


def _pearson_r(x: Sequence[float], y: Sequence[float]) -> float | None:
    """표준편차가 0이거나(상수 배열) n<2면 상관계수가 정의되지 않으므로 None."""
    if len(x) < 2:
        return None
    _x, _y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if np.std(_x) == 0 or np.std(_y) == 0:
        return None
    return float(np.corrcoef(_x, _y)[0, 1])


def _weighted_kappa(
    rater1: Sequence[int], rater2: Sequence[int], n_categories: int, weights: str = "quadratic",
) -> float | None:
    """Cohen's weighted kappa — scikit-learn 없이 numpy만으로 직접 구현.

    표준 공식 ``kappa = 1 - sum(W*O) / sum(W*E)``:
        O: 혼동행렬(관측 빈도), E: 두 rater의 주변분포 외적(기대 빈도),
        W: linear(``|i-j|/(k-1)``) 또는 quadratic(``(i-j)^2/(k-1)^2``) 가중치 행렬.

    scikit-learn의 ``cohen_kappa_score(y1, y2, weights=weights)``와 동일한 결과를
    낸다(SPEC-022 Acceptance에서 교차검증).
    """
    n = len(rater1)
    if n == 0:
        return None
    observed = np.zeros((n_categories, n_categories))
    for a, b in zip(rater1, rater2):
        observed[a, b] += 1
    hist1 = observed.sum(axis=1)
    hist2 = observed.sum(axis=0)
    expected = np.outer(hist1, hist2) / n
    idx = np.arange(n_categories)
    if weights == "quadratic":
        weight_matrix = (idx[:, None] - idx[None, :]) ** 2 / (n_categories - 1) ** 2
    else:
        weight_matrix = np.abs(idx[:, None] - idx[None, :]) / (n_categories - 1)
    denominator = np.sum(weight_matrix * expected)
    if denominator == 0:
        return None
    return float(1 - np.sum(weight_matrix * observed) / denominator)


def compute_agreement(
    judge_scores: Sequence[float],
    human_scores: Sequence[float],
    category_range: tuple[int, int] = (0, 5),
) -> dict[str, Any]:
    """judge/human 점수 쌍의 합의도 지표를 계산한다.

    Args:
        judge_scores: LLMJudge가 매긴 점수 시퀀스.
        human_scores: 사람이 매긴 점수 시퀀스(``judge_scores``와 길이가 같아야 함).
        category_range: Cohen's kappa/exact_match_rate 계산 시 반올림·클램프할
            정수 카테고리 범위(포함). 기본값 ``(0, 5)``는 ``completeness``/
            ``relevance``/``factual_consistency``/``toxicity``/``bias``/
            ``faithfulness``/``criteria_scores`` 각 항목의 실제 스케일과 일치한다.

    Returns:
        ``{"n", "mean_absolute_error", "pearson_r", "exact_match_rate",
        "cohen_kappa_linear", "cohen_kappa_quadratic"}``. ``n=0``이면 ``{"n": 0}``만.

    Raises:
        ValueError: 두 시퀀스의 길이가 다를 때.
    """
    if len(judge_scores) != len(human_scores):
        raise ValueError(
            f"judge_scores(len={len(judge_scores)})와 human_scores(len={len(human_scores)})"
            "의 길이가 다릅니다"
        )
    n = len(judge_scores)
    if n == 0:
        return {"n": 0}

    _judge = [float(s) for s in judge_scores]
    _human = [float(s) for s in human_scores]
    _mae = sum(abs(j - h) for j, h in zip(_judge, _human)) / n

    lo, hi = category_range
    n_categories = hi - lo + 1
    _judge_cat = [int(round(min(max(s, lo), hi))) - lo for s in _judge]
    _human_cat = [int(round(min(max(s, lo), hi))) - lo for s in _human]
    _exact_match = sum(1 for j, h in zip(_judge_cat, _human_cat) if j == h) / n

    def _round_or_none(value: float | None) -> float | None:
        return round(value, 4) if value is not None else None

    return {
        "n": n,
        "mean_absolute_error": round(_mae, 4),
        "pearson_r": _round_or_none(_pearson_r(_judge, _human)),
        "exact_match_rate": round(_exact_match, 4),
        "cohen_kappa_linear": _round_or_none(
            _weighted_kappa(_judge_cat, _human_cat, n_categories, "linear")
        ),
        "cohen_kappa_quadratic": _round_or_none(
            _weighted_kappa(_judge_cat, _human_cat, n_categories, "quadratic")
        ),
    }


class LLMJudgeCalibration:
    """기존 ``LLMJudge`` 인스턴스를 재사용해 골든 케이스를 채점하고, 사람 라벨과의
    합의도를 차원별로 리포트한다. 채점 로직 자체는 수정하지 않는다."""

    def __init__(self, judge: LLMJudge) -> None:
        self._judge = judge

    def run(self, cases: list[CalibrationCase]) -> dict[str, Any]:
        """각 케이스를 ``judge()``로 채점하고, 사람 라벨이 있는 차원별로
        :func:`compute_agreement`를 실행한 리포트를 반환한다.

        Args:
            cases: 검증할 골든 케이스 목록.

        Returns:
            ``{"n_cases", "skipped_count", "dimensions": {dim: agreement_dict, ...}}``.
        """
        judge_results = [
            self._judge.judge(case.task_id, case.question, case.response, context=case.context)
            for case in cases
        ]
        skipped_count = sum(1 for r in judge_results if r.get("skipped"))

        dimensions: set = set()
        for case in cases:
            dimensions.update(case.human_scores.keys())

        report: dict[str, Any] = {
            "n_cases": len(cases),
            "skipped_count": skipped_count,
            "dimensions": {},
        }
        for dim in sorted(dimensions):
            pairs = [
                (result["scores"].get(dim), case.human_scores[dim])
                for result, case in zip(judge_results, cases)
                if not result.get("skipped")
                and result.get("scores") is not None
                and dim in case.human_scores
                and result["scores"].get(dim) is not None
            ]
            if not pairs:
                report["dimensions"][dim] = {"n": 0, "note": "no comparable (judge, human) pairs"}
                continue
            judge_vals, human_vals = zip(*pairs)
            report["dimensions"][dim] = compute_agreement(list(judge_vals), list(human_vals))
        return report


def load_cases_from_json(path: Union[str, Path]) -> list[CalibrationCase]:
    """``[{"task_id", "question", "response", "human_scores", "context"?}, ...]``
    형식의 JSON 파일을 읽어 :class:`CalibrationCase` 리스트로 변환한다."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [
        CalibrationCase(
            task_id=item["task_id"],
            question=item["question"],
            response=item["response"],
            human_scores=item["human_scores"],
            context=item.get("context"),
        )
        for item in raw
    ]
