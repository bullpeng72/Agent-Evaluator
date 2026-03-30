"""Tests for ImplicitFeedbackTracker.

Covers record(), get_stats(), get_task_feedbacks(), reset(), thread safety,
and the feedbacks property shallow-copy guarantee.
"""
from __future__ import annotations

import threading

import pytest

from agent_evaluator.core.trackers.feedback import (
    ALL_FEEDBACK_TYPES,
    NEGATIVE_TYPES,
    POSITIVE_TYPES,
    ImplicitFeedbackTracker,
)
from agent_evaluator.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker(*entries) -> ImplicitFeedbackTracker:
    """Create a tracker pre-loaded with (task_id, feedback_type) pairs."""
    t = ImplicitFeedbackTracker()
    for task_id, fb_type in entries:
        t.record(task_id, fb_type)
    return t


# ---------------------------------------------------------------------------
# record() — positive types
# ---------------------------------------------------------------------------

def test_record_all_positive_types():
    """Every POSITIVE_TYPES value must be accepted without error."""
    tracker = ImplicitFeedbackTracker()
    for fb in POSITIVE_TYPES:
        tracker.record("task_pos", fb)
    stats = tracker.get_stats()
    assert stats["positive_count"] == len(POSITIVE_TYPES)
    assert stats["negative_count"] == 0


def test_record_all_negative_types():
    """Every NEGATIVE_TYPES value must be accepted without error."""
    tracker = ImplicitFeedbackTracker()
    for fb in NEGATIVE_TYPES:
        tracker.record("task_neg", fb)
    stats = tracker.get_stats()
    assert stats["negative_count"] == len(NEGATIVE_TYPES)
    assert stats["positive_count"] == 0


def test_record_with_metadata():
    """Metadata dict must be stored in the feedback entry."""
    tracker = ImplicitFeedbackTracker()
    tracker.record("t1", "thumbs_up", metadata={"source": "web", "session": 42})
    fb = tracker.feedbacks[0]
    assert fb["metadata"]["source"] == "web"
    assert fb["metadata"]["session"] == 42


def test_record_without_metadata_defaults_to_empty_dict():
    """When metadata is omitted, the stored value must be an empty dict."""
    tracker = ImplicitFeedbackTracker()
    tracker.record("t1", "copy")
    assert tracker.feedbacks[0]["metadata"] == {}


# ---------------------------------------------------------------------------
# record() — ValidationError cases
# ---------------------------------------------------------------------------

def test_record_raises_on_empty_task_id():
    tracker = ImplicitFeedbackTracker()
    with pytest.raises(ValidationError):
        tracker.record("", "thumbs_up")


def test_record_raises_on_whitespace_only_task_id():
    tracker = ImplicitFeedbackTracker()
    with pytest.raises(ValidationError):
        tracker.record("   ", "thumbs_up")


def test_record_raises_on_unknown_feedback_type():
    tracker = ImplicitFeedbackTracker()
    with pytest.raises(ValidationError):
        tracker.record("t1", "nonexistent_type")


def test_record_raises_on_empty_feedback_type():
    tracker = ImplicitFeedbackTracker()
    with pytest.raises(ValidationError):
        tracker.record("t1", "")


# ---------------------------------------------------------------------------
# get_stats() — empty tracker
# ---------------------------------------------------------------------------

def test_get_stats_empty_tracker_returns_zeros():
    tracker = ImplicitFeedbackTracker()
    stats = tracker.get_stats()
    assert stats["total"] == 0
    assert stats["positive_count"] == 0
    assert stats["negative_count"] == 0
    assert stats["positive_rate"] == 0.0
    assert stats["negative_rate"] == 0.0
    assert stats["regenerate_rate"] == 0.0
    assert stats["abandon_rate"] == 0.0
    assert stats["type_distribution"] == {}


# ---------------------------------------------------------------------------
# get_stats() — populated tracker
# ---------------------------------------------------------------------------

def test_get_stats_total_count():
    tracker = _make_tracker(
        ("t1", "thumbs_up"),
        ("t1", "copy"),
        ("t2", "regenerate"),
    )
    assert tracker.get_stats()["total"] == 3


def test_get_stats_positive_negative_counts():
    tracker = _make_tracker(
        ("t1", "thumbs_up"),   # positive
        ("t1", "copy"),        # positive
        ("t2", "regenerate"),  # negative
        ("t2", "abandon"),     # negative
    )
    stats = tracker.get_stats()
    assert stats["positive_count"] == 2
    assert stats["negative_count"] == 2


def test_get_stats_positive_rate():
    tracker = _make_tracker(
        ("t1", "thumbs_up"),   # positive
        ("t2", "regenerate"),  # negative
        ("t3", "copy"),        # positive
        ("t4", "abandon"),     # negative
    )
    stats = tracker.get_stats()
    assert stats["positive_rate"] == 50.0
    assert stats["negative_rate"] == 50.0


def test_get_stats_regenerate_rate():
    tracker = _make_tracker(
        ("t1", "regenerate"),
        ("t2", "regenerate"),
        ("t3", "thumbs_up"),
        ("t4", "thumbs_up"),
    )
    stats = tracker.get_stats()
    assert stats["regenerate_rate"] == 50.0


def test_get_stats_abandon_rate():
    tracker = _make_tracker(
        ("t1", "abandon"),
        ("t2", "thumbs_up"),
        ("t3", "thumbs_up"),
        ("t4", "thumbs_up"),
    )
    stats = tracker.get_stats()
    assert stats["abandon_rate"] == 25.0


def test_get_stats_type_distribution():
    tracker = _make_tracker(
        ("t1", "thumbs_up"),
        ("t2", "thumbs_up"),
        ("t3", "regenerate"),
    )
    dist = tracker.get_stats()["type_distribution"]
    assert dist["thumbs_up"] == 2
    assert dist["regenerate"] == 1


# ---------------------------------------------------------------------------
# get_task_feedbacks()
# ---------------------------------------------------------------------------

def test_get_task_feedbacks_filters_by_task_id():
    tracker = _make_tracker(
        ("task_A", "thumbs_up"),
        ("task_B", "regenerate"),
        ("task_A", "copy"),
    )
    result = tracker.get_task_feedbacks("task_A")
    assert len(result) == 2
    assert all(r["task_id"] == "task_A" for r in result)


def test_get_task_feedbacks_unknown_task_returns_empty():
    tracker = _make_tracker(("t1", "thumbs_up"))
    assert tracker.get_task_feedbacks("nonexistent") == []


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

def test_reset_clears_all_feedbacks():
    tracker = _make_tracker(
        ("t1", "thumbs_up"),
        ("t2", "regenerate"),
    )
    tracker.reset()
    assert tracker.feedbacks == []
    assert tracker.get_stats()["total"] == 0


# ---------------------------------------------------------------------------
# feedbacks property — shallow copy
# ---------------------------------------------------------------------------

def test_feedbacks_property_returns_shallow_copy():
    """Mutating the returned list must not affect internal state."""
    tracker = _make_tracker(("t1", "copy"))
    copy1 = tracker.feedbacks
    copy1.append({"fake": True})
    copy2 = tracker.feedbacks
    assert len(copy2) == 1  # internal list unchanged


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_thread_safe_concurrent_records():
    """100 threads each recording once must produce exactly 100 feedbacks."""
    tracker = ImplicitFeedbackTracker()
    types = sorted(ALL_FEEDBACK_TYPES)

    def worker(idx: int) -> None:
        fb = types[idx % len(types)]
        tracker.record(f"task_{idx}", fb)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert tracker.get_stats()["total"] == 100
