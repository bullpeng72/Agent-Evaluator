"""
tests/test_llm_judge_calibration.py
======================================
SPEC-022 검증: agent_evaluator.integrations.llm_judge_calibration.

- compute_agreement/_weighted_kappa 순수 함수 동작(완전 일치, 상수 배열, 길이 불일치)
- _weighted_kappa가 scikit-learn의 cohen_kappa_score와 동일한 값을 내는지 교차검증
  (이 개발 환경에 우연히 설치돼 있을 뿐 선언된 의존성은 아니므로 importorskip으로 감쌈)
- LLMJudgeCalibration.run()이 기존 LLMJudge._call_judge를 스텁해 실제 API 호출 없이
  동작하는지(tests/test_llm_judge_concurrency.py와 동일한 모킹 패턴)
- load_cases_from_json 왕복 확인
"""
import json
import random
from typing import Any, Dict

import pytest

from agent_evaluator.integrations.llm_judge import LLMJudge
from agent_evaluator.integrations.llm_judge_calibration import (
    CalibrationCase,
    LLMJudgeCalibration,
    _weighted_kappa,
    compute_agreement,
    load_cases_from_json,
)


def _scores(overall=4, faithfulness=None) -> Dict[str, Any]:
    return {
        "completeness": overall, "relevance": overall, "factual_consistency": overall,
        "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": float(overall),
        "confidence": 0.9, "faithfulness": faithfulness,
    }


def _fake_judge_result(task_id: str, model: str, overall=4, faithfulness=None, skipped=False) -> Dict[str, Any]:
    if skipped:
        return {"task_id": task_id, "skipped": True}
    return {
        "task_id": task_id, "skipped": False, "scores": _scores(overall, faithfulness),
        "reasoning": "ok", "model": model, "model_snapshot": model, "cost_usd": 0.0001,
    }


class TestComputeAgreement:
    def test_perfect_agreement(self):
        result = compute_agreement([0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5])
        assert result["mean_absolute_error"] == 0
        assert result["exact_match_rate"] == 1.0
        assert result["cohen_kappa_linear"] == 1.0
        assert result["cohen_kappa_quadratic"] == 1.0
        assert result["pearson_r"] == 1.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_agreement([1, 2, 3], [1, 2])

    def test_empty_returns_n_zero(self):
        assert compute_agreement([], []) == {"n": 0}

    def test_constant_judge_scores_pearson_is_none(self):
        result = compute_agreement([3, 3, 3], [1, 3, 5])
        assert result["pearson_r"] is None

    def test_partial_disagreement(self):
        result = compute_agreement([3, 4, 5], [4, 4, 4])
        assert result["mean_absolute_error"] == pytest.approx(2 / 3, abs=1e-4)
        assert result["exact_match_rate"] == pytest.approx(1 / 3, abs=1e-4)


class TestWeightedKappaVsSklearn:
    def test_matches_sklearn_cohen_kappa_score(self):
        sklearn_metrics = pytest.importorskip("sklearn.metrics")
        rng = random.Random(42)
        for _ in range(20):
            n = rng.randint(5, 30)
            rater1 = [rng.randint(0, 5) for _ in range(n)]
            rater2 = [rng.randint(0, 5) for _ in range(n)]
            for weights in ("linear", "quadratic"):
                # labels=range(6)을 명시해야 sklearn도 우리 구현과 동일하게 "이 표본에서
                # 관측된 값"이 아니라 "이론적 전체 범위(0-5)"를 카테고리로 쓴다 — 그래야
                # 두 구현이 같은 가정으로 비교된다(작은 무작위 표본은 0-5를 전부 포함하지
                # 않을 수 있어, labels 생략 시 sklearn이 더 좁은 범위로 계산해 값이 갈린다).
                expected = sklearn_metrics.cohen_kappa_score(
                    rater1, rater2, labels=list(range(6)), weights=weights,
                )
                actual = _weighted_kappa(rater1, rater2, n_categories=6, weights=weights)
                assert actual == pytest.approx(expected, abs=1e-9)


class TestLLMJudgeCalibrationRun:
    def test_dimensions_only_include_labeled_ones(self, monkeypatch):
        def fake_call_judge(self, task_id, question, response, context, *, _model=None):
            return _fake_judge_result(task_id, self.model, overall=4, faithfulness=5)

        monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0)

        cases = [
            CalibrationCase(task_id="g1", question="q1", response="r1",
                             human_scores={"overall": 4, "faithfulness": 5}),
            CalibrationCase(task_id="g2", question="q2", response="r2",
                             human_scores={"overall": 3, "faithfulness": 4}),
        ]
        report = LLMJudgeCalibration(judge).run(cases)

        assert report["n_cases"] == 2
        assert report["skipped_count"] == 0
        assert set(report["dimensions"].keys()) == {"overall", "faithfulness"}
        assert report["dimensions"]["overall"]["n"] == 2
        assert report["dimensions"]["faithfulness"]["n"] == 2

    def test_all_skipped_when_sample_rate_zero(self, monkeypatch):
        def fake_call_judge(self, task_id, question, response, context, *, _model=None):
            return _fake_judge_result(task_id, self.model, overall=4)

        monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.0)

        cases = [
            CalibrationCase(task_id="g1", question="q1", response="r1",
                             human_scores={"overall": 4}),
        ]
        report = LLMJudgeCalibration(judge).run(cases)

        assert report["skipped_count"] == 1
        assert report["dimensions"]["overall"] == {"n": 0, "note": "no comparable (judge, human) pairs"}

    def test_none_faithfulness_excluded_from_pairs(self, monkeypatch):
        """context 없는 케이스는 judge의 faithfulness가 None — 사람 라벨이 있어도 페어에서 제외."""
        def fake_call_judge(self, task_id, question, response, context, *, _model=None):
            return _fake_judge_result(task_id, self.model, overall=4, faithfulness=None)

        monkeypatch.setattr(LLMJudge, "_call_judge", fake_call_judge)
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0)

        cases = [
            CalibrationCase(task_id="g1", question="q1", response="r1",
                             human_scores={"faithfulness": 5}),
        ]
        report = LLMJudgeCalibration(judge).run(cases)
        assert report["dimensions"]["faithfulness"]["n"] == 0


class TestLoadCasesFromJson:
    def test_round_trip(self, tmp_path):
        payload = [
            {"task_id": "g1", "question": "q", "response": "r",
             "human_scores": {"overall": 4}, "context": "ctx"},
            {"task_id": "g2", "question": "q2", "response": "r2",
             "human_scores": {"overall": 3}},
        ]
        path = tmp_path / "cases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        cases = load_cases_from_json(path)
        assert len(cases) == 2
        assert cases[0].task_id == "g1"
        assert cases[0].context == "ctx"
        assert cases[1].context is None
        assert cases[1].human_scores == {"overall": 3}
