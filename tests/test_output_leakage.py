"""
Tests for OutputLeakageDetector
"""

import pytest
from agent_evaluator.core.trackers.security import OutputLeakageDetector


@pytest.fixture
def detector():
    return OutputLeakageDetector()


# ---------------------------------------------------------------------------
# 1. OpenAI API key detection
# ---------------------------------------------------------------------------

def test_detect_openai_api_key(detector):
    text = "Here is the key: sk-abcdefghijklmnopqrstuvwxyz123456789012345678"
    result = detector.detect_leakage("t1", text)
    assert result["contains_api_key"] is True


# ---------------------------------------------------------------------------
# 2. Anthropic API key detection
# ---------------------------------------------------------------------------

def test_detect_anthropic_api_key(detector):
    text = "key: sk-ant-api03-" + "A" * 90
    result = detector.detect_leakage("t2", text)
    assert result["contains_api_key"] is True


# ---------------------------------------------------------------------------
# 3. GitHub PAT detection
# ---------------------------------------------------------------------------

def test_detect_github_pat(detector):
    text = "token ghp_" + "A" * 36
    result = detector.detect_leakage("t3", text)
    assert result["contains_api_key"] is True


# ---------------------------------------------------------------------------
# 4. Email detection
# ---------------------------------------------------------------------------

def test_detect_email(detector):
    text = "Please contact support@example.com for help."
    result = detector.detect_leakage("t4", text)
    assert result["contains_email"] is True


# ---------------------------------------------------------------------------
# 5. Phone number detection
# ---------------------------------------------------------------------------

def test_detect_phone(detector):
    text = "Call us at 010-1234-5678 anytime."
    result = detector.detect_leakage("t5", text)
    assert result["contains_phone"] is True


# ---------------------------------------------------------------------------
# 6. File path detection
# ---------------------------------------------------------------------------

def test_detect_file_path(detector):
    text = "The config is at /etc/passwd on the server."
    result = detector.detect_leakage("t6", text)
    assert result["contains_file_path"] is True


# ---------------------------------------------------------------------------
# 7. Credit card number detection
# ---------------------------------------------------------------------------

def test_detect_credit_card(detector):
    text = "Payment card: 4111 1111 1111 1111"
    result = detector.detect_leakage("t7", text)
    assert result["contains_credit_card"] is True


# ---------------------------------------------------------------------------
# 8. Clean output — all flags False
# ---------------------------------------------------------------------------

def test_no_leakage_in_clean_text(detector):
    text = "The weather today is sunny with a high of 25 degrees Celsius."
    result = detector.detect_leakage("t8", text)
    assert result["contains_api_key"] is False
    assert result["contains_email"] is False
    assert result["contains_phone"] is False
    assert result["contains_file_path"] is False
    assert result["contains_credit_card"] is False
    assert result["contains_password"] is False
    assert result["leakage_count"] == 0
    assert result["severity"] == "none"


# ---------------------------------------------------------------------------
# 9. leakage_score > 0 when leakage is present
# ---------------------------------------------------------------------------

def test_leakage_count_positive_when_leakage_present(detector):
    text = "Contact admin@corp.io and use password=SuperSecret99!"
    result = detector.detect_leakage("t9", text)
    assert result["leakage_count"] > 0


# ---------------------------------------------------------------------------
# 10. Full return structure validation
# ---------------------------------------------------------------------------

def test_detect_leakage_return_structure(detector):
    text = "No sensitive info here."
    result = detector.detect_leakage("t10", text)
    expected_keys = {
        "task_id",
        "contains_api_key",
        "contains_password",
        "contains_credit_card",
        "contains_email",
        "contains_phone",
        "contains_ssn",
        "contains_private_ip",
        "contains_file_path",
        "leakage_count",
        "severity",
    }
    for key in expected_keys:
        assert key in result, f"Missing key in detect_leakage result: {key}"

    assert result["task_id"] == "t10"
    assert isinstance(result["leakage_count"], int)
    assert result["severity"] in {"none", "low", "medium", "high", "critical"}


# ---------------------------------------------------------------------------
# 11. get_leakage_stats returns correct aggregates after multiple detections
# ---------------------------------------------------------------------------

def test_get_leakage_stats_aggregation():
    d = OutputLeakageDetector()
    d.detect_leakage("a", "safe text")
    d.detect_leakage("b", "email: foo@bar.com")
    stats = d.get_leakage_stats()
    assert stats["total_outputs_evaluated"] == 2
    assert stats["outputs_with_leakage"] == 1
    assert stats["email_leaks"] == 1


def test_get_leakage_stats_empty_returns_structured_zeros():
    d = OutputLeakageDetector()
    stats = d.get_leakage_stats()
    assert stats["total_outputs_evaluated"] == 0
    assert stats["outputs_with_leakage"] == 0
    assert stats["leakage_rate"] == 0.0
    for key in ("api_key_leaks", "password_leaks", "credit_card_leaks",
                "email_leaks", "ssn_leaks", "phone_leaks", "private_ip_leaks", "file_path_leaks"):
        assert stats[key] == 0
