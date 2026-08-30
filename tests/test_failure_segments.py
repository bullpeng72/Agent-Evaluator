"""
tests/test_failure_segments.py
=================================
SPEC-041 P30 — semantic failure segmentation + trigger localization.

`_failure_segments_section` clusters the failing *questions* by lexical topic
(binary TF-IDF + greedy cosine, stdlib); `_failure_triggers_section` pins each
failure to the retrieved passage or tool step that most likely caused it.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_evaluator.reporting.comprehensive_report import _build_failure_segments
from agent_evaluator.reporting.insights import (
    _failure_segments_section,
    _failure_triggers_section,
    build_insights,
)


def _t(tid, q, comp, acc, ok, **kw):
    d = {"task_id": tid, "task_type": "qa", "question": q,
         "completion_score": comp, "accuracy_score": acc, "success": ok}
    d.update(kw)
    return d


def _dataset():
    ts = [_t(f"ok{i}", f"generic passing question number {i}", 1.0, 0.9, True) for i in range(8)]
    ts += [
        _t("f1", "How do I get a refund for a returned item shipped back to you?", 0.4, 0.3, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="full refund within 14 days of return",
           context="Our loyalty program grants points on every purchase.\n\nGold tier "
                   "requires $300 spend.",
           response="You earn points on returns."),
        _t("f2", "What is the return shipping cost for a refund?", 0.4, 0.25, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="return shipping is free with a prepaid label",
           context="Loyalty points expire after 12 months.",
           response="Points never expire."),
        _t("f3", "Can I return an opened item and still get a refund?", 0.5, 0.2, False,
           partial_reason="answer not grounded in the retrieved context",
           ground_truth="opened items get store credit only",
           context="Delivery takes 2-3 business days.",
           response="Delivery is fast."),
        _t("g1", "How do I update the device firmware over the air?", 0.3, 0.2, False,
           partial_reason="only part of a multi-step answer completed",
           ground_truth="use the companion app Settings > Software update"),
        _t("g2", "Why does the firmware update fail on low battery?", 0.3, 0.2, False,
           partial_reason="only part of a multi-step answer completed",
           ground_truth="the update needs 50% battery"),
        _t("h1", "Check delivery status of order 10293", 0.0, 0.0, False,
           partial_reason="error: TimeoutError",
           tool_calls=[
               {"tool_name": "retrieve", "success": True, "output": "ok"},
               {"tool_name": "order_api", "success": False, "error": "503 upstream unavailable"},
           ]),
    ]
    return ts


class TestFailureSegments:
    def test_separates_topics(self):
        segs = _failure_segments_section(_dataset())
        assert segs is not None
        labels = " ".join(s["label"] for s in segs)
        assert any(w in labels for w in ("return", "refund", "shipping"))
        assert any(w in labels for w in ("firmware", "update", "battery"))

    def test_segment_fields(self):
        segs = _failure_segments_section(_dataset())
        s = segs[0]
        assert s["n"] >= 2
        assert 0 < s["share_of_failures_pct"] <= 100
        assert s["dominant_reason"]
        assert s["keywords"] and isinstance(s["keywords"], list)

    def test_none_when_too_few_failures(self):
        assert _failure_segments_section([_t("a", "one question", 0.3, 0.2, False)]) is None

    def test_none_when_questions_have_no_content_words(self):
        ts = [_t(f"f{i}", "the a an of to", 0.3, 0.2, False) for i in range(6)]
        assert _failure_segments_section(ts) is None

    def test_deterministic(self):
        a = _failure_segments_section(_dataset())
        b = _failure_segments_section(_dataset())
        assert [s["task_ids"] for s in a] == [s["task_ids"] for s in b]


class TestFailureTriggers:
    def test_tool_failure_pinned_to_step(self):
        trigs = {t["task_id"]: t for t in _failure_triggers_section(_dataset())}
        assert trigs["h1"]["kind"] == "tool_failure"
        assert "order_api" in trigs["h1"]["detail"] and "Step 2" in trigs["h1"]["detail"]

    def test_retrieval_gap_detected(self):
        trigs = {t["task_id"]: t for t in _failure_triggers_section(_dataset())}
        assert trigs["f1"]["kind"] in ("retrieval_gap", "grounding")
        assert trigs["f1"]["detail"]

    def test_none_when_no_localizable_trigger(self):
        ts = [_t(f"x{i}", "plain question", 0.3, 0.2, False) for i in range(4)]
        assert _failure_triggers_section(ts) is None


class TestBuildInsightsWiring:
    def test_keys_and_schema(self):
        ins = build_insights({
            "extra_metrics": {"harness_groups": {
                "A": {"score": 0.5, "status": "fail", "gate": "fail", "details": {}}}},
            "tasks": _dataset(),
        })
        assert ins["failure_segments"] and ins["failure_triggers"]
        json.dumps(ins)
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "agent_evaluator" / "schemas"
             / "insights.schema.json").read_text()
        )
        jsonschema.validate(ins, schema)

    def test_null_for_healthy_run(self):
        ins = build_insights({
            "extra_metrics": {"harness_groups": {}},
            "tasks": [_t(f"ok{i}", "fine", 1.0, 0.95, True) for i in range(10)],
        })
        assert ins["failure_segments"] is None
        assert ins["failure_triggers"] is None


class TestReportSection:
    def test_renders(self):
        from agent_evaluator import create_taskresult

        objs = []
        for d in _dataset():
            tr = create_taskresult(task_id=d["task_id"], task_type="qa",
                                   question=d["question"], response=d.get("response", ""),
                                   ground_truth=d.get("ground_truth", ""), execution_time=1.0)
            object.__setattr__(tr, "completion_score", d["completion_score"])
            object.__setattr__(tr, "accuracy_score", d["accuracy_score"])
            object.__setattr__(tr, "success", d["success"])
            for k in ("partial_reason", "context", "tool_calls"):
                if d.get(k):
                    object.__setattr__(tr, k, d[k])
            objs.append(tr)
        h = _build_failure_segments(objs)
        assert "Failure segments" in h and "Likely triggers" in h

    def test_empty_without_data(self):
        assert _build_failure_segments(None) == ""
