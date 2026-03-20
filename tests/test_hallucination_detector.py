"""Tests for HallucinationDetector.detect_hallucination()"""
import pytest

from agent_evaluator.core.agent_evaluator import HallucinationDetector


@pytest.fixture
def detector():
    return HallucinationDetector()


class TestDetectHallucination:
    def test_returns_dict_with_required_keys(self, detector):
        result = detector.detect_hallucination(
            task_id="t1",
            response="서울은 한국의 수도입니다.",
            context="한국의 수도는 서울입니다.",
        )
        assert "task_id" in result
        assert "hallucination_rate" in result
        assert "indicators" in result

    def test_task_id_preserved(self, detector):
        result = detector.detect_hallucination("my_task", "text", "context")
        assert result["task_id"] == "my_task"

    def test_rate_bounded(self, detector):
        result = detector.detect_hallucination(
            "t2", "완전히 다른 내용의 응답입니다.", "전혀 관련 없는 컨텍스트."
        )
        rate = result["hallucination_rate"]
        assert 0.0 <= rate <= 1.0

    def test_grounded_response_zero_hallucination(self, detector):
        context = "파이썬은 프로그래밍 언어입니다. Guido van Rossum이 만들었습니다."
        response = "파이썬은 Guido van Rossum이 만든 프로그래밍 언어입니다."
        result = detector.detect_hallucination("t3", response, context)
        assert result["hallucination_rate"] == 0.0

    def test_empty_response_handled(self, detector):
        result = detector.detect_hallucination("t4", "", "some context")
        assert isinstance(result, dict)

    def test_records_stored(self, detector):
        detector.detect_hallucination("t5", "response text", "context text")
        rate = detector.get_hallucination_rate()
        assert rate.get("total_evaluated", 0) >= 1

    def test_indicators_is_list(self, detector):
        result = detector.detect_hallucination("t6", "response", "context")
        assert isinstance(result["indicators"], list)
