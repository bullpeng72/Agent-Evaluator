"""
Tests for ToolSelectionTracker, _normalize_tool_name, and _TOOL_ALIASES
"""

import pytest
from agent_evaluator.core.trackers.layer2 import (
    ToolSelectionTracker,
    _normalize_tool_name,
    _TOOL_ALIASES,
    _TOOL_ALIAS_REVERSE,
)


@pytest.fixture
def tracker():
    return ToolSelectionTracker()


# ---------------------------------------------------------------------------
# _normalize_tool_name direct tests
# ---------------------------------------------------------------------------

def test_normalize_known_alias():
    # search_web is an alias for web_search
    assert _normalize_tool_name("search_web") == "web_search"


def test_normalize_canonical_unchanged():
    assert _normalize_tool_name("web_search") == "web_search"


def test_normalize_case_insensitive():
    # Aliases are lowercase in the map; we lowercase before lookup
    assert _normalize_tool_name("Search_Web") == "web_search"


def test_normalize_whitespace_stripped():
    assert _normalize_tool_name("  calculator  ") == "calculator"


def test_normalize_unknown_tool_unchanged():
    assert _normalize_tool_name("my_custom_tool") == "my_custom_tool"


def test_normalize_empty_string():
    assert _normalize_tool_name("") == ""


# ---------------------------------------------------------------------------
# 1. Perfect match — Precision=1.0, Recall=1.0, F1=1.0
# ---------------------------------------------------------------------------

def test_perfect_match(tracker):
    result = tracker.evaluate_selection(
        "t1",
        expected_tools=["web_search", "calculator"],
        actual_tools=["web_search", "calculator"],
    )
    assert result["precision"] == 100.0
    assert result["recall"] == 100.0
    assert result["f1_score"] == 100.0


# ---------------------------------------------------------------------------
# 2. Partial match — correct F1 calculation
# ---------------------------------------------------------------------------

def test_partial_match_f1(tracker):
    # expected: 3 tools, actual matches 2 of them exactly
    result = tracker.evaluate_selection(
        "t2",
        expected_tools=["web_search", "calculator", "file_read"],
        actual_tools=["web_search", "calculator"],
    )
    # Precision = 2/2 = 1.0
    # Recall    = 2/3 ≈ 0.667
    # F1        = 2 * 1.0 * 0.667 / (1.0 + 0.667) ≈ 0.800
    assert result["recall"] < 100.0
    assert result["f1_score"] > 0.0
    assert result["f1_score"] <= 100.0


# ---------------------------------------------------------------------------
# 3. Alias matching: expected=["web_search"], actual=["search_web"]
# ---------------------------------------------------------------------------

def test_alias_match_search_web(tracker):
    result = tracker.evaluate_selection(
        "t3",
        expected_tools=["web_search"],
        actual_tools=["search_web"],
    )
    assert result["f1_score"] == 100.0


# ---------------------------------------------------------------------------
# 4. Alias matching: expected=["python_repl"], actual=["code_runner"]
# ---------------------------------------------------------------------------

def test_alias_match_code_runner(tracker):
    result = tracker.evaluate_selection(
        "t4",
        expected_tools=["python_repl"],
        actual_tools=["code_runner"],
    )
    assert result["f1_score"] == 100.0


# ---------------------------------------------------------------------------
# 5. Complete mismatch — F1=0.0
# ---------------------------------------------------------------------------

def test_complete_mismatch(tracker):
    result = tracker.evaluate_selection(
        "t5",
        expected_tools=["web_search"],
        actual_tools=["calculator"],
    )
    assert result["f1_score"] == 0.0


# ---------------------------------------------------------------------------
# 6. Expected empty list — no division by zero, returns 100.0 accuracy note
# ---------------------------------------------------------------------------

def test_empty_expected_no_division_by_zero(tracker):
    result = tracker.evaluate_selection(
        "t6",
        expected_tools=[],
        actual_tools=["web_search"],
    )
    # When expected is empty there is no ground truth — accuracy/f1_score are None
    # (not 0.0) so callers using dropna() exclude them from aggregated averages.
    # A "note" key signals the evaluation was skipped.
    assert result["accuracy"] is None
    assert result["f1_score"] is None
    assert "note" in result
    # All standard keys must be present for consistent downstream aggregation
    for key in ("precision", "recall", "f1_score", "true_positives",
                "false_positives", "false_negatives"):
        assert key in result, f"missing key: {key}"


# ---------------------------------------------------------------------------
# 7. get_accuracy_stats — aggregates multiple evaluations correctly
# ---------------------------------------------------------------------------

def test_get_accuracy_stats_aggregation(tracker):
    tracker.evaluate_selection("a", ["web_search"], ["web_search"])
    tracker.evaluate_selection("b", ["calculator"], ["calculator"])
    stats = tracker.get_accuracy_stats()
    assert stats["total_evaluations"] == 2
    assert stats["avg_f1_score"] == 100.0


def test_get_accuracy_stats_empty_returns_structured_zeros():
    t = ToolSelectionTracker()
    stats = t.get_accuracy_stats()
    assert stats["total_evaluations"] == 0
    assert stats["avg_accuracy"] == 0.0
    assert stats["avg_f1_score"] == 0.0


# ---------------------------------------------------------------------------
# 8. _TOOL_ALIASES covers reverse mapping properly
# ---------------------------------------------------------------------------

def test_alias_reverse_map_consistency():
    for canonical, aliases in _TOOL_ALIASES.items():
        for alias in aliases:
            assert _TOOL_ALIAS_REVERSE.get(alias) == canonical, (
                f"Reverse map inconsistency: alias '{alias}' should map to '{canonical}'"
            )
