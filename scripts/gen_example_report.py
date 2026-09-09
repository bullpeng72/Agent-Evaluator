"""Generate one feature-rich example HTML report (SPEC-044 structure).

Writes results/example_report/ with 4 sibling runs + baseline + the current
report at results/example_report/report.html. Run: python scripts/gen_example_report.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.rca.decision_ledger import record_gate_decision
from agent_evaluator.rca.experiments import register_experiment

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "results" / "example_report"
OUT.mkdir(parents=True, exist_ok=True)
AOO = OUT / ".aoo"
AOO.mkdir(exist_ok=True)

# --- project state: SLOs, an open improvement experiment, a pending decision ---
(AOO / "targets.json").write_text(json.dumps(
    {"gates": {"A": 0.85, "C": 0.80, "E": 0.95}, "tcr_pct": 90, "accuracy_pct": 75},
    indent=2,
))
register_experiment(
    str(AOO / "experiments.jsonl"),
    target_gate="A", predicted_delta=0.08, target_field="avg_subtask_completion",
    note="[improve] Gate A prompt_edit: add two worked examples to the system prompt",
    baseline_ref="baseline.json",
)
record_gate_decision(
    str(AOO / "decisions.jsonl"), result_file="baseline.json", agent_version="v2",
    exit_code=1, verdict_level="not_ready", decision_ready=True,
    gate_scores={"A": 0.61, "C": 0.72},
)

REQUIREMENTS = ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005"]
(OUT / "requirements.txt").write_text(
    "REQ-001: answers cite the retrieved passage\n"
    "REQ-002: refuses out-of-scope questions\n"
    "REQ-003: response is at most 3 sentences\n"
    "REQ-004: no PII in the response\n"
    "REQ-005: latency p95 under 3s\n"
)

DIFFICULTY = ["easy", "easy", "medium", "medium", "medium", "hard", "hard", "hard"]


def _task(i: int, ok: bool, *, covers=None, extra_fail_reason=None):
    q = f"What does section {i} of the policy say about refunds and eligibility?"
    resp = ("Per the retrieved passage, refunds are issued within 14 days for "
            "eligible orders." if ok else
            "I'm not sure — the policy is unclear on that.")
    ex: dict = {"difficulty": DIFFICULTY[i % len(DIFFICULTY)]}
    if not ok and extra_fail_reason:
        ex["partial_reason"] = extra_fail_reason
    return create_taskresult(
        task_id=f"t{i}", question=q, response=resp,
        ground_truth="Refunds are issued within 14 days for eligible orders.",
        execution_time=0.4 + (0.9 if DIFFICULTY[i % 8] == "hard" else 0.1),
        task_type="rag" if i % 3 == 0 else "qa",
        context="Section: refunds. Eligible orders may be refunded within 14 days."
        if ok else "Section: shipping. Orders ship in 2 business days.",
        covers=covers,
        acceptance_criteria=["cites the retrieved passage", "answer in <= 3 sentences"],
    )


def _run(name: str, n_pass: int, n: int = 18, *, baseline_path=None):
    m = PerformanceMonitor(
        output_dir=str(OUT),
        config_snapshot={
            "SLAConfig": {"p95_ms": 3000},
            "EfficiencyConfig": {"fallback_reference_cost_per_completion": 0.002},
            "InstructionConfig": {"required_keywords": ["refund"]},
        },
        agent_version="auto",
    )
    for i in range(n):
        ok = i < n_pass
        reason = None
        if not ok:
            reason = ("answer not grounded in the retrieved context"
                      if i % 2 else "error: TimeoutError after 3 retries")
        m.record_task(_task(
            i, ok,
            covers=[REQUIREMENTS[i % len(REQUIREMENTS)]] if i < 4 else None,
            extra_fail_reason=reason,
        ))
    return m.save_to_file(name, baseline_path=baseline_path)


# --- 3 sibling history runs (improving, then this run dips) ---
for k, npass in enumerate((11, 13, 15)):
    _run(f"run_{k}", npass)

# --- baseline: 15/18 pass ---
bpath = _run("baseline", 15)
baseline = json.loads(Path(bpath).read_text())

# --- current: 10/18 pass — t10..t14 regressed (passed in baseline, fail now) ---
os.chdir(OUT)  # so .aoo/ + requirements.txt resolve from the report's dir
cur_mon = PerformanceMonitor(
    output_dir=".",
    config_snapshot={
        "SLAConfig": {"p95_ms": 3000},
        "EfficiencyConfig": {"fallback_reference_cost_per_completion": 0.002},
        "InstructionConfig": {"required_keywords": ["refund"]},
    },
    agent_version="auto",
)
for i in range(18):
    ok = i < 10
    reason = None
    if not ok:
        reason = ("answer not grounded in the retrieved context" if i % 2
                  else "error: TimeoutError after 3 retries")
    cur_mon.record_task(_task(
        i, ok,
        covers=[REQUIREMENTS[i % len(REQUIREMENTS)]] if i < 4 else None,
        extra_fail_reason=reason,
    ))
cur_path = cur_mon.save_to_file("current", baseline_path="baseline.json")

from agent_evaluator.reporting.comprehensive_report import (  # noqa: E402
    generate_comprehensive_html_report,
)

html = generate_comprehensive_html_report(cur_mon, baseline=baseline)
Path("report.html").write_text(html, encoding="utf-8")
report_path = Path("report.html").resolve()
os.chdir(REPO_ROOT)

print(f"\n  example report: {report_path}")
print(f"  {len(html):,} bytes · open it in a browser")
print(f"  result JSON:    {report_path.parent / 'current.json'}")
