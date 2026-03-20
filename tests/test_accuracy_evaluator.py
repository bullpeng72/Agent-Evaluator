"""Tests for AccuracyEvaluator._qa_accuracy()"""
import pytest

from agent_evaluator.core.agent_evaluator import AccuracyEvaluator


@pytest.fixture
def evaluator():
    return AccuracyEvaluator()


class TestQaAccuracy:
    def test_exact_match_returns_high_score(self, evaluator):
        score = evaluator._qa_accuracy("서울", "서울")
        assert score >= 0.95

    def test_empty_ground_truth_returns_zero(self, evaluator):
        assert evaluator._qa_accuracy("", "any answer") == 0.0

    def test_empty_prediction_returns_low_score(self, evaluator):
        score = evaluator._qa_accuracy("서울", "")
        assert score < 0.1

    def test_partial_overlap_returns_intermediate_score(self, evaluator):
        score = evaluator._qa_accuracy("한국의 수도는 서울이다", "서울이 수도")
        assert 0.0 < score < 0.9

    def test_completely_different_returns_low_score(self, evaluator):
        score = evaluator._qa_accuracy("사과", "자동차")
        assert score < 0.2

    def test_case_insensitive(self, evaluator):
        score_lower = evaluator._qa_accuracy("Seoul", "seoul")
        assert score_lower >= 0.9

    def test_score_bounded_between_zero_and_one(self, evaluator):
        score = evaluator._qa_accuracy("hello world test", "hello world test extra words here")
        assert 0.0 <= score <= 1.0

    def test_whitespace_normalized(self, evaluator):
        score = evaluator._qa_accuracy("한국  수도", "한국 수도")
        assert score >= 0.9

    def test_punctuation_ignored(self, evaluator):
        score = evaluator._qa_accuracy("서울!", "서울")
        assert score >= 0.9
