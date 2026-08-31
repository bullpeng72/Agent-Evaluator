"""
tests/test_regression_attribution_p38.py
========================================
SPEC-041 P38 — insights.regression_attribution: joins failure_lineage.regressed
with change_attribution (what changed) and metadata_slices (where it dropped).
"""
from __future__ import annotations

from agent_evaluator.reporting.insights import (
    _change_implicates,
    _regression_attribution_section,
    build_insights,
)


def _t(tid, comp, acc, ok, reason=None, extra=None):
    d = {"task_id": tid, "task_type": "qa", "completion_score": comp,
         "accuracy_score": acc, "success": ok, "question": f"q {tid}"}
    if reason:
        d["partial_reason"] = reason
    if extra:
        d["extra"] = extra
    return d


def test_change_implicates_mapping():
    assert _change_implicates("config: model (a -> b)", "runtime") is True   # model = all
    assert _change_implicates("config: temperature (0.2 -> 0.7)", "grounding") is True
    assert _change_implicates("config: retry_timeout", "runtime") is True
    assert _change_implicates("config: temperature", "runtime") is False
    assert _change_implicates("prompt reworded (50% similar)", "decomposition") is False


def test_none_without_regressions():
    assert _regression_attribution_section([], None, None, None) is None
    assert _regression_attribution_section(
        [_t("a", 1.0, 0.9, True)], {"regressed": []}, {}, None,
    ) is None


def test_links_slice_and_change():
    tasks = [
        _t("r1", 0.3, 0.2, False, "only part of a multi-step answer completed",
           {"difficulty": "hard"}),
        _t("r2", 0.3, 0.2, False, "only part of a multi-step answer completed",
           {"difficulty": "hard"}),
        _t("r3", 0.3, 0.2, False, "only part of a multi-step answer completed",
           {"difficulty": "hard"}),
    ]
    fl = {"regressed": ["r1", "r2", "r3"], "persistent": [], "new": [], "fixed": []}
    ca = {
        "prompt_changed": True,
        "prompt_diff": {"similarity": 0.6,
                        "removed": ["Break the task into numbered steps."], "added": []},
        "config_diff": {"changed_keys": {"temperature": {"from": 0.2, "to": 0.7}}},
    }
    ms = [{"dimension": "extra.difficulty",
           "slices": [{"value": "hard", "n": 3, "tcr_pct": 30.0, "tcr_delta_pp": -25.0}]}]
    ra = _regression_attribution_section(tasks, fl, ca, ms)
    assert ra is not None
    assert ra["n_regressed_tasks"] == 3
    c0 = ra["clusters"][0]
    assert c0["category"] == "decomposition"
    conc = c0["slice_concentration"][0]
    assert conc["dimension"] == "extra.difficulty" and conc["value"] == "hard"
    assert conc["slice_tcr_delta_pp"] == -25.0
    assert "prompt: removed a step-decomposition instruction" in c0["implicated_changes"]
    assert "temporal isolation" in ra["note"]


def test_non_scalar_extra_keys_ignored():
    tasks = [
        _t(f"r{i}", 0.3, 0.2, False, "error: TimeoutError",
           {"trace": {"steps": [1, 2, 3]}, "note": "x" * 200, "region": "eu"})
        for i in range(3)
    ]
    fl = {"regressed": ["r0", "r1", "r2"]}
    ra = _regression_attribution_section(tasks, fl, {}, None)
    assert ra is not None
    dims = {s["dimension"] for c in ra["clusters"] for s in c["slice_concentration"]}
    assert "extra.trace" not in dims and "extra.note" not in dims
    assert "extra.region" in dims          # short scalar survives


def test_end_to_end_via_build_insights():
    base_tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(8)]
    cur_tasks = [_t(f"p{i}", 1.0, 0.9, True) for i in range(5)]
    cur_tasks += [_t(f"p{i}", 0.2, 0.1, False, "answer not grounded in the retrieved context",
                     {"model_variant": "mini"}) for i in range(5, 8)]
    cur = {"extra_metrics": {"harness_groups": {
               "A": {"score": 0.6, "status": "warn", "gate": "warn", "details": {}}},
               "lineage": {"config_snapshot": {"temperature": 0.7}}},
           "tasks": cur_tasks}
    base = {"extra_metrics": {"harness_groups": {
                "A": {"score": 0.8, "status": "pass", "gate": "pass", "details": {}}},
                "lineage": {"config_snapshot": {"temperature": 0.2}}},
            "tasks": base_tasks}
    ra = build_insights(cur, base)["regression_attribution"]
    assert ra and ra["n_regressed_tasks"] == 3
    assert "temperature" in ra["changed_config_keys"]
