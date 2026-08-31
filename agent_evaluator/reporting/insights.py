"""
agent_evaluator.reporting.insights
======================================
Machine-readable **insight layer** (L5/L6 of ``Docs/09_OUTPUTS.md``) as a single
JSON-serializable object.

Until now the deploy verdict, confidence, failure clusters, component shortfalls,
prescriptive recommendations and experiment suggestions lived only in the HTML
report and the ``agent-eval`` CLI text output. That means CI jobs, the dashboard
and any automation could read raw Gate scores (L1-L4) but not the *interpretation*
of them (L5-L6).

``build_insights()`` computes that interpretation once, as plain data, so it can
be embedded in the result JSON (``extra_metrics.insights``) and served verbatim to
the dashboard. It introduces **no new judgement logic** — it reuses
``rca.diagnose()``, ``utils.confidence``, ``ontology.metric_registry`` and
``rca.recommendation_tracking`` / ``rca.verify``, and re-shapes their output.

HOTL principle (Chapter 2): every field here is a *candidate* explanation with its
evidence — nothing asserts "this is the cause".
"""
from __future__ import annotations

import difflib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Schema version for the ``insights`` object itself. Bump the major on any
# breaking field-shape change so consumers (dashboard/CI/external tools) can adapt.
INSIGHTS_SCHEMA_VERSION = "1.0"

_GATE_FULL = {
    "A": "Goal Achievement", "B": "Behavioral Integrity", "C": "Reliability",
    "D": "Performance Contract", "E": "Security Boundary",
    "F": "Multi-Agent Coordination", "G": "Observability",
}

# ---------------------------------------------------------------------------
# Failure-clustering primitives — kept in sync with the HTML report's
# _reason_signature / _effective_fail (reporting/comprehensive_report.py). They
# are duplicated here (a dozen lines) rather than imported to avoid pulling the
# heavy report module into the monitor save path.
# ---------------------------------------------------------------------------
_RE_NUM_PAREN = re.compile(r"\s*\(\s*[^)]*\d[^)]*\)")
_RE_NUM = re.compile(r"\b\d[\d.,%/:s]*\b")
_RE_ERR = re.compile(r"^error:\s*([A-Za-z_][A-Za-z0-9_.]*)")


def _safe_float(v: Any, default: Any = None) -> Any:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _reason_signature(reason: str) -> str:
    r = (reason or "").strip()
    if not r:
        return "unspecified"
    m = _RE_ERR.match(r)
    if m:
        return f"error: {m.group(1)}"
    r = _RE_NUM_PAREN.sub("", r)
    r = _RE_NUM.sub("", r).strip()
    r = re.sub(r"\s{2,}", " ", r).strip(" ·-–—")
    return r or "unspecified"


def _effective_fail(*, success: Any, accuracy: Any, completion: Any) -> bool:
    if not bool(success):
        return True
    a = _safe_float(accuracy)
    c = _safe_float(completion)
    if a is not None and a < 0.7:
        return True
    return c is not None and c < 0.4


def _task_reason(t: dict[str, Any]) -> str:
    """One-line "why did this task fail / score low" — mirrors the report's
    _case_reason but for a plain result-JSON task dict."""
    pr = t.get("partial_reason")
    if pr:
        return str(pr)
    errs = t.get("errors") or []
    if errs:
        return f"error: {errs[0]}"
    bits = []
    comp = _safe_float(t.get("completion_score"))
    acc = _safe_float(t.get("accuracy_score"))
    if comp is not None and comp < 0.75:
        bits.append(f"incomplete ({comp * 100:.0f}%)")
    if acc is not None and acc < 0.7:
        bits.append(f"low accuracy ({acc * 100:.0f}%)")
    return " · ".join(bits) or ("failed" if not t.get("success") else "below target")


# ---------------------------------------------------------------------------
# Latency attribution (P7) — aggregate the per-task span breakdown that
# gate_g_observability.eval_latency_attribution() computes but only exposes as a
# single 0-1 score. This turns "P95 = 4.0s" into "2.1s model + 1.3s tool + 0.6s
# unattributed; bottleneck = model".
# ---------------------------------------------------------------------------

_ATTR_COMPONENTS = ("tool", "model", "network", "unattributed")


def aggregate_latency_attribution(
    attr_dicts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Mean the per-task ``latency_attribution`` dicts and pick the modal bottleneck.

    Each input dict is the output of ``eval_latency_attribution`` (keys
    ``tool_ms``, ``model_ms``, ``tool_ratio`` … ``bottleneck``). Returns ``None``
    when no task carried attribution data.
    """
    rows = [d for d in attr_dicts if isinstance(d, dict)]
    if not rows:
        return None
    n = len(rows)
    out: dict[str, Any] = {"n_tasks": n}
    for comp in _ATTR_COMPONENTS:
        ms_vals = [_safe_float(d.get(f"{comp}_ms"), 0.0) or 0.0 for d in rows]
        ratio_vals = [_safe_float(d.get(f"{comp}_ratio"), None) for d in rows]
        ratio_vals = [r for r in ratio_vals if r is not None]
        out[f"{comp}_ms"] = round(sum(ms_vals) / n, 2)
        if ratio_vals:
            out[f"{comp}_ratio"] = round(sum(ratio_vals) / len(ratio_vals), 4)
    counts: dict[str, int] = defaultdict(int)
    for d in rows:
        b = str(d.get("bottleneck") or "").strip()
        if b:
            counts[b] += 1
    if counts:
        bottleneck, hits = max(counts.items(), key=lambda kv: kv[1])
        out["bottleneck"] = bottleneck
        out["bottleneck_share"] = round(hits / n, 4)
    return out


def _extract_task_attr(t: dict[str, Any]) -> dict[str, Any] | None:
    extra = t.get("extra")
    if isinstance(extra, dict):
        la = extra.get("latency_attribution")
        if isinstance(la, dict):
            return la
    return None


# ---------------------------------------------------------------------------
# Security findings (P19) — per-task threat detail from the 5 security trackers.
# Gate E has its own aggregate section but never said *which task* triggered
# *which threat*; a security regression is the highest-priority improve item.
# ---------------------------------------------------------------------------
_THREAT_CWE = {
    "sql_injection": "CWE-89", "command_injection": "CWE-78",
    "path_traversal": "CWE-22", "xss": "CWE-79", "prompt_injection": "LLM01",
    "template_injection": "CWE-1336", "ldap_injection": "CWE-90", "xxe": "CWE-611",
    "ssrf": "CWE-918", "jwt_manipulation": "CWE-347",
    "api_key": "CWE-312", "password": "CWE-256", "credit_card": "CWE-311",
    "ssn": "CWE-359", "private_ip": "CWE-200", "db_connection": "CWE-522",
    "jwt_token": "CWE-522", "crypto_address": "CWE-200",
    "privilege_escalation": "CWE-269", "dangerous_params": "CWE-77",
    "unauthorized_tool": "CWE-862", "restricted_tool": "CWE-863",
    "tool_chain_attack": "CWE-506",
}


def _sec_records(current: dict[str, Any], name: str) -> list[dict[str, Any]]:
    sec = ((current.get("evaluators") or {}).get("security") or {}) if isinstance(current, dict) else {}
    block = sec.get(name)
    if not isinstance(block, dict):
        return []
    for v in block.values():           # {"evaluations": [...]} / {"detections": [...]} / ...
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
    return []


_SEV_ORDER = ["low", "medium", "high", "critical"]


def _bump_severity(sev: str) -> str:
    try:
        i = _SEV_ORDER.index(sev)
    except ValueError:
        return "high"
    return _SEV_ORDER[min(i + 1, len(_SEV_ORDER) - 1)]


def _attack_succeeded(rec: dict[str, Any], task: dict[str, Any] | None) -> str:
    """Did the detected threat actually land? Trust an explicit outcome field on
    the record; otherwise infer from whether a tool call executed. 'unknown' when
    neither is available (detection != compromise)."""
    for k in ("blocked", "prevented", "enforced"):
        if k in rec:
            return "no" if bool(rec[k]) else "yes"
    for k in ("acted_on", "executed", "bypassed", "succeeded"):
        if k in rec:
            return "yes" if bool(rec[k]) else "no"
    if task is not None:
        calls = task.get("tool_calls")
        if isinstance(calls, list) and any(
            isinstance(c, dict) and c.get("success", True) is not False
            for c in calls
        ):
            return "likely"          # something ran after the flagged step
    return "unknown"


def _security_findings_section(
    current: dict[str, Any], tasks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    if not isinstance(current, dict) or not (current.get("evaluators") or {}).get("security"):
        return None
    by_id = {str(t.get("task_id")): t for t in (tasks or []) if t.get("task_id")}
    out: list[dict[str, Any]] = []

    def _emit(tid: Any, tracker: str, threat: str, severity: str, detail: str,
              rec: dict[str, Any] | None = None) -> None:
        out.append({
            "task_id": str(tid or "—"), "tracker": tracker,
            "threat_type": threat, "severity": severity or "unknown",
            "cwe": _THREAT_CWE.get(threat), "detail": detail[:200],
            "succeeded": _attack_succeeded(rec or {}, by_id.get(str(tid or ""))),
        })

    for r in _sec_records(current, "input_sanitizer"):
        if r.get("threat_count", 0) or r.get("sanitization_needed"):
            hits = [k[4:] for k in r if k.startswith("has_") and r.get(k)]
            _emit(r.get("task_id"), "input_sanitizer",
                  hits[0] if hits else "input_threat", r.get("risk_level", ""),
                  f"input threats: {', '.join(hits) or 'unspecified'}", r)
    for r in _sec_records(current, "output_leakage_detector"):
        if r.get("leakage_count", 0):
            hits = [k[9:] for k in r if k.startswith("contains_") and r.get(k)]
            _emit(r.get("task_id"), "output_leakage_detector",
                  hits[0] if hits else "output_leak", r.get("severity", ""),
                  f"response leaked: {', '.join(hits) or 'unspecified'}", r)
    for r in _sec_records(current, "tool_authorizer"):
        if r.get("has_dangerous_params") or not r.get("is_authorized", True) or r.get("is_restricted"):
            vt = r.get("violation_type") or (
                "unauthorized_tool" if not r.get("is_authorized", True) else "dangerous_params"
            )
            sev = "high" if not r.get("is_authorized", True) else "medium"
            _emit(r.get("task_id"), "tool_authorizer", vt, sev,
                  f"tool {r.get('tool_name', '?')} — {vt}", r)
    for r in _sec_records(current, "privilege_escalation_detector"):
        if r.get("escalation_detected"):
            rs = r.get("risk_score", 0)
            sev = "critical" if rs >= 8 else "high" if rs >= 5 else "medium"
            _emit(r.get("task_id"), "privilege_escalation_detector",
                  "privilege_escalation", sev,
                  f"{r.get('initial_privilege')} → {r.get('max_privilege')} "
                  f"(risk {rs})", r)
    for r in _sec_records(current, "tool_chain_attack_detector"):
        if r.get("is_suspicious_chain"):
            pats = r.get("attack_patterns_detected") or [
                k for k, v in (r.get("attack_types") or {}).items() if v
            ]
            conf = r.get("confidence", 0.0)
            sev = "critical" if conf >= 0.8 else "high" if conf >= 0.5 else "medium"
            _emit(r.get("task_id"), "tool_chain_attack_detector",
                  "tool_chain_attack", sev,
                  f"patterns: {', '.join(str(p) for p in pats) or 'unspecified'}", r)

    if not out:
        return None

    # P42: compound findings — 2+ trackers flagging the SAME task is worse than
    # the sum: an injection alongside a tool-authorization gap means the injection
    # had a path to execution. Escalate one severity level and list the parts.
    _sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    per_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in out:
        per_task[f["task_id"]].append(f)
    for tid, fs in per_task.items():
        trackers = {f["tracker"] for f in fs}
        if len(trackers) < 2:
            continue
        worst = min(fs, key=lambda f: _sev_rank.get(f["severity"], 4))
        succ = ("yes" if any(f["succeeded"] == "yes" for f in fs)
                else "likely" if any(f["succeeded"] == "likely" for f in fs)
                else "unknown")
        out.append({
            "task_id": tid, "tracker": "compound", "kind": "compound",
            "threat_type": " + ".join(sorted({f["threat_type"] for f in fs})),
            "severity": _bump_severity(worst["severity"]),
            "cwe": sorted({f["cwe"] for f in fs if f.get("cwe")}),
            "detail": (f"{len(fs)} findings from {len(trackers)} trackers on one "
                       f"task — combined exposure, not independent issues"),
            "succeeded": succ,
            "components": sorted({f["threat_type"] for f in fs}),
        })

    out.sort(key=lambda f: (
        0 if f.get("kind") == "compound" else 1,
        _sev_rank.get(f["severity"], 4), f["task_id"],
    ))
    return out[:30]


def _security_posture_section(
    current: dict[str, Any], tasks: list[dict[str, Any]] | None,
    security_findings: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """P42: attack-surface summary — which tools are implicated, how many tasks
    are affected, did anything actually land."""
    sf = security_findings or []
    if not sf:
        return None
    _sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    real = [f for f in sf if f.get("kind") != "compound"]
    by_sev: Counter = Counter(f["severity"] for f in real)
    tools: Counter = Counter()
    for f in real:
        d = str(f.get("detail") or "")
        m = re.search(r"tool ([A-Za-z0-9_.\-]+)", d)
        if m:
            tools[m.group(1)] += 1
    landed = [
        {"task_id": f["task_id"], "threat_type": f["threat_type"],
         "severity": f["severity"], "succeeded": f["succeeded"]}
        for f in real if f["succeeded"] in ("yes", "likely")
    ]
    return {
        "n_findings": len(real),
        "n_tasks_affected": len({f["task_id"] for f in real}),
        "n_compound": sum(1 for f in sf if f.get("kind") == "compound"),
        "by_severity": {k: by_sev[k] for k in _SEV_ORDER[::-1] if by_sev[k]},
        "tools_implicated": [
            {"tool": t, "n": n} for t, n in tools.most_common(10)
        ],
        "landed_or_likely": sorted(
            landed, key=lambda x: _sev_rank.get(x["severity"], 4),
        )[:10],
        "any_landed": any(x["succeeded"] == "yes" for x in landed),
    }


# ---------------------------------------------------------------------------
# Non-determinism (P19) — localize a low Gate C reproducibility score to the
# tasks that actually diverged (with the variant texts when the run kept them).
# ---------------------------------------------------------------------------

def _nondeterminism_section(tasks: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    out: list[dict[str, Any]] = []
    for t in tasks:
        extra = t.get("extra")
        rep = extra.get("reproducibility") if isinstance(extra, dict) else None
        if not isinstance(rep, dict):
            continue
        score = _safe_float(rep.get("score"))
        rc = rep.get("run_count")
        if score is None or not isinstance(rc, int) or rc < 2 or score >= 0.85:
            continue
        out.append({
            "task_id": str(t.get("task_id") or "—"),
            "reproducibility_score": round(score, 3),
            "run_count": rc,
            "variance": round(_safe_float(rep.get("variance"), 0.0) or 0.0, 4),
            "sample_responses": [
                str(s)[:300] for s in (rep.get("sample_responses") or [])
            ][:3],
        })
    if not out:
        return None
    out.sort(key=lambda d: d["reproducibility_score"])
    return out[:15]


# ---------------------------------------------------------------------------
# Agent calibration & abstention quality (P39) — opt-in.
#
# When a task records `extra.confidence` (0–1, the agent's own probability that
# its answer is right) and/or `extra.abstained` (bool), we can say things the
# accuracy score alone can't: is the agent WRONG-BUT-CONFIDENT (the dangerous
# failure), does its confidence carry enough signal to route on (risk/coverage),
# and when it says "I don't know" is it right to? No opt-in data -> section is
# None (zero cost, zero noise).
# ---------------------------------------------------------------------------
def _is_correct(t: dict[str, Any]) -> bool:
    acc = _safe_float(t.get("accuracy_score"))
    if acc is not None:
        return acc >= 0.6
    return not _effective_fail(
        success=t.get("success", False),
        accuracy=t.get("accuracy_score"),
        completion=t.get("completion_score"),
    )


def _calibration_section(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    conf_pairs: list[tuple[float, float]] = []
    abstained: list[dict[str, Any]] = []
    answered_correct = answered_total = 0
    for t in tasks:
        ex = _task_extra(t) or {}
        abst = bool(ex.get("abstained"))
        conf = ex.get("confidence")
        if abst:
            gt = str(t.get("ground_truth") or "").strip()
            abstained.append({
                "task_id": str(t.get("task_id") or "—"),
                # "answerable" heuristic: a real, non-trivial ground truth exists
                "answerable": len(gt.split()) >= 3,
                "question": str(t.get("question") or "")[:160],
            })
            continue
        if isinstance(conf, (int, float)):
            conf_pairs.append((float(conf), 1.0 if _is_correct(t) else 0.0))
        answered_total += 1
        if _is_correct(t):
            answered_correct += 1

    if len(conf_pairs) < 5 and not abstained:
        return None

    out: dict[str, Any] = {"n_with_confidence": len(conf_pairs)}

    if len(conf_pairs) >= 5:
        try:
            from agent_evaluator.utils.confidence import (
                brier_score,
                expected_calibration_error,
                risk_coverage_points,
            )
        except Exception:  # pragma: no cover - defensive
            return out if abstained else None
        ece = expected_calibration_error(conf_pairs)
        mean_conf = sum(c for c, _ in conf_pairs) / len(conf_pairs)
        acc = sum(y for _, y in conf_pairs) / len(conf_pairs)
        gap = mean_conf - acc          # +ve = overconfident
        out.update({
            "ece": (ece or {}).get("ece"),
            "mce": (ece or {}).get("mce"),
            "brier": brier_score(conf_pairs),
            "mean_confidence": round(mean_conf, 4),
            "empirical_accuracy": round(acc, 4),
            "confidence_gap": round(gap, 4),
            "verdict": (
                "overconfident" if gap > 0.10
                else "underconfident" if gap < -0.10
                else "well-calibrated"
            ),
            "reliability_bins": (ece or {}).get("bins") or [],
            "risk_coverage": risk_coverage_points(conf_pairs) or [],
        })
        # does the confidence carry routing signal? risk should FALL as coverage
        # drops (abstain on the least-sure first). Flat = no signal; rising = the
        # confidence is inverted (high-confidence answers are worse).
        rc = out["risk_coverage"]
        if len(rc) >= 2:
            _d = rc[-1]["risk"] - rc[0]["risk"]
            out["confidence_is_informative"] = bool(_d < -0.03)
            out["confidence_signal"] = (
                "informative" if _d < -0.03
                else "inverted" if _d > 0.03
                else "flat"
            )

    if abstained:
        n_ab = len(abstained)
        n_answerable = sum(1 for a in abstained if a["answerable"])
        out["abstention"] = {
            "n_abstained": n_ab,
            "abstention_rate_pct": round(
                n_ab / max(1, n_ab + answered_total) * 100.0, 1,
            ),
            "answered_accuracy_pct": (
                round(answered_correct / answered_total * 100.0, 1)
                if answered_total else None
            ),
            "abstained_when_answerable": n_answerable,
            "example_task_ids": [a["task_id"] for a in abstained[:10]],
        }

    return out


# ---------------------------------------------------------------------------
# Cost economics (P16) — the number that actually matters is cost per *successful*
# task, plus how much is being burned on failures and retries, plus what that
# projects to at scale. Gate D only ever showed total / per-task cost.
# ---------------------------------------------------------------------------
_PROJECTION_CALLS = 100_000


def _task_token_cost(t: dict[str, Any], p_in: float | None, p_out: float | None) -> float | None:
    """Per-task USD cost from token counts + pricing (per-1k-token rates), or the
    task's own ``extra.cost_usd`` / ``llm_judge.cost_usd`` if present."""
    extra = t.get("extra")
    if isinstance(extra, dict) and isinstance(extra.get("cost_usd"), (int, float)):
        return float(extra["cost_usd"])
    tu = t.get("tokens_used")
    if isinstance(tu, dict) and p_in is not None:
        i = _safe_float(tu.get("input"), 0.0) or 0.0
        o = _safe_float(tu.get("output"), 0.0) or 0.0
        if i or o:
            return i / 1000.0 * p_in + o / 1000.0 * (p_out if p_out is not None else p_in)
    return None


def _cost_economics_section(
    tasks: list[dict[str, Any]], current: dict[str, Any],
) -> dict[str, Any] | None:
    if not tasks:
        return None
    pricing = (current.get("pricing") or {}) if isinstance(current, dict) else {}
    p_in = _safe_float(pricing.get("input"))
    p_out = _safe_float(pricing.get("output"))

    per_task = [_task_token_cost(t, p_in, p_out) for t in tasks]
    have_per_task = any(c is not None for c in per_task)

    agg_total = None
    em = (current.get("efficiency_metrics") or {}) if isinstance(current, dict) else {}
    _tok = em.get("tokens")
    tok = _tok if isinstance(_tok, dict) else {}
    if isinstance(tok.get("total_cost"), (int, float)):
        agg_total = float(tok["total_cost"])

    n = len(tasks)
    if have_per_task:
        costs = [c if c is not None else 0.0 for c in per_task]
        total_cost = sum(costs)
    elif agg_total and agg_total > 0:
        total_cost = agg_total
        costs = [agg_total / n] * n           # uniform fallback
    else:
        return None
    if total_cost <= 0:
        return None

    # A task that fails OR scores below target is (at least partly) wasted spend —
    # this is intentionally the wider `_effective_fail` set, not just success=False.
    failed = [
        i for i, t in enumerate(tasks)
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    n_success = n - len(failed)
    wasted = sum(costs[i] for i in failed)

    retry_cost = 0.0
    for i, t in enumerate(tasks):
        a = t.get("attempts")
        if isinstance(a, int) and a > 1:
            retry_cost += costs[i] * (a - 1) / a   # fraction attributable to retries

    cost_per_task = total_cost / n
    return {
        "total_cost_usd": round(total_cost, 6),
        "cost_source": "per_task_tokens" if have_per_task else "aggregate_uniform_split",
        "n_tasks": n,
        "n_successful": n_success,
        "n_failed_or_lowscore": len(failed),
        "cost_per_task_usd": round(cost_per_task, 6),
        "cost_per_successful_task_usd": (
            round(total_cost / n_success, 6) if n_success else None
        ),
        "wasted_cost_usd": round(wasted, 6),
        "wasted_cost_pct": round(wasted / total_cost * 100.0, 1),
        "retry_cost_usd": round(retry_cost, 6),
        "retry_cost_pct": round(retry_cost / total_cost * 100.0, 1),
        "projection": {
            "calls": _PROJECTION_CALLS,
            "total_usd": round(cost_per_task * _PROJECTION_CALLS, 2),
            "wasted_usd": round(wasted / n * _PROJECTION_CALLS, 2),
        },
    }


# ---------------------------------------------------------------------------
# Efficiency opportunities (P40) — cost/latency reporting -> concrete proposals.
#
# P7 (latency budget) and P16 (cost economics) only *report*. The data to act on
# is already here: per-variant cost + TCR from metadata slices, per-step timing
# from span data, retry spend from cost economics. This section synthesises the
# obvious moves — route to a cheaper model, gate an always-on step, cut retries.
# Correlational and first-order; a human decides.
# ---------------------------------------------------------------------------
_ROUTE_TCR_TOL_PP = 5.0
_STEP_UBIQUITY = 0.9
_RETRY_PCT_FLOOR = 5.0


def _efficiency_opportunities_section(
    tasks: list[dict[str, Any]],
    current: dict[str, Any],
    cost_economics: dict[str, Any] | None,
    metadata_slices: list[dict[str, Any]] | None,
    failure_clusters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tasks:
        return None
    ce = cost_economics or {}
    cur_cpt = _safe_float(ce.get("cost_per_task_usd"))
    out: list[dict[str, Any]] = []

    pricing = (current.get("pricing") or {}) if isinstance(current, dict) else {}
    p_in, p_out = _safe_float(pricing.get("input")), _safe_float(pricing.get("output"))

    # (a) model routing — a variant/model metadata dimension with a cheaper value
    #     whose TCR is within tolerance of the expensive one.
    for dim in metadata_slices or []:
        key = str(dim.get("dimension", ""))
        short = key[6:] if key.startswith("extra.") else key
        if not any(w in short.lower() for w in ("model", "variant", "engine")):
            continue
        rows: list[dict[str, Any]] = []
        for s in dim.get("slices") or []:
            val = str(s.get("value"))
            members = [
                t for t in tasks
                if str((_task_extra(t) or {}).get(short)) == val
            ]
            costs = [
                c for c in (_task_token_cost(t, p_in, p_out) for t in members)
                if c is not None
            ]
            if len(members) < 3 or not costs or s.get("tcr_pct") is None:
                continue
            rows.append({
                "value": val, "n": len(members),
                "tcr_pct": float(s["tcr_pct"]),
                "cost_per_task_usd": round(sum(costs) / len(costs), 6),
            })
        if len(rows) < 2:
            continue
        cheap = min(rows, key=lambda r: r["cost_per_task_usd"])
        dear = max(rows, key=lambda r: r["cost_per_task_usd"])
        tcr_loss = dear["tcr_pct"] - cheap["tcr_pct"]
        if (cheap["value"] != dear["value"]
                and cheap["cost_per_task_usd"] < dear["cost_per_task_usd"] * 0.85
                and tcr_loss <= _ROUTE_TCR_TOL_PP
                and cur_cpt and cheap["cost_per_task_usd"] < cur_cpt):
            saved_pct = (cur_cpt - cheap["cost_per_task_usd"]) / cur_cpt * 100.0
            out.append({
                "kind": "model_routing",
                "title": f"Consolidate on the '{cheap['value']}' {short}",
                "detail": (
                    f"'{cheap['value']}' costs ${cheap['cost_per_task_usd']:.4f}/task "
                    f"vs ${dear['cost_per_task_usd']:.4f} for '{dear['value']}', and "
                    f"its TCR is {cheap['tcr_pct']:.0f}% vs {dear['tcr_pct']:.0f}% "
                    f"({-tcr_loss:+.1f}pp). Routing all traffic to '{cheap['value']}' "
                    f"is projected to cut cost/task by {saved_pct:.0f}%."
                ),
                "projected_saving_pct": round(saved_pct, 1),
                "projected_saving_per_100k_usd": round(
                    (cur_cpt - cheap["cost_per_task_usd"]) * 100_000, 0,
                ),
                "risk": (
                    f"up to ~{max(0.0, tcr_loss):.1f}pp TCR on the share that "
                    f"currently uses '{dear['value']}'"
                    if tcr_loss > 0 else "none measured on this eval set"
                ),
                "evidence": {"by_value": rows},
            })

    # (b) always-on step with meaningful cost — a candidate to gate behind a
    #     confidence / necessity check.
    span_count: Counter = Counter()
    span_ms: dict[str, list[float]] = defaultdict(list)
    n_timed = 0
    for t in tasks:
        for src in ("tool_calls", "chain_steps", "agent_interactions"):
            tl = parse_span_timeline(t.get(src) or [])
            if tl and tl.get("spans"):
                n_timed += 1
                for sp in tl["spans"]:
                    span_count[sp["name"]] += 1
                    span_ms[sp["name"]].append(float(sp.get("self_ms") or 0.0))
                break
    if n_timed >= 5:
        _means = {
            nm: (sum(v) / len(v) if v else 0.0) for nm, v in span_ms.items()
        }
        # never suggest gating the single most expensive step — that's the core work
        _core = max(_means, key=lambda nm: _means[nm]) if _means else None
        _ubiq = sorted(
            (nm for nm, c in span_count.items()
             if c / n_timed >= _STEP_UBIQUITY and c >= 5 and nm != _core),
            key=lambda nm: -_means.get(nm, 0.0),
        )
        for name in _ubiq:
            share = span_count[name] / n_timed
            mean_ms = _means.get(name, 0.0)
            if mean_ms >= 80.0:
                out.append({
                    "kind": "step_gating",
                    "title": f"Gate the '{name}' step",
                    "detail": (
                        f"The '{name}' step runs on {share * 100:.0f}% of traced "
                        f"tasks and adds ~{mean_ms:.0f}ms each. If it only changes "
                        f"the answer on a minority, gate it behind a "
                        f"retrieval-confidence / necessity check."
                    ),
                    "projected_saving_pct": None,
                    "projected_saving_per_100k_usd": None,
                    "risk": "quality drop on the tasks that genuinely need this step",
                    "evidence": {"share_pct": round(share * 100.0, 1),
                                 "mean_self_ms": round(mean_ms, 1),
                                 "n": span_count[name]},
                })
                break          # one is enough — the costliest ubiquitous non-core step

    # (c) retry spend
    rpct = _safe_float(ce.get("retry_cost_pct"))
    if rpct is not None and rpct >= _RETRY_PCT_FLOOR:
        rt_clusters = list(dict.fromkeys(
            str(c.get("signature") or c.get("label"))
            for c in (failure_clusters or [])
            if _proposal_category(str(c.get("signature") or c.get("label") or "")) == "runtime"
        ))
        out.append({
            "kind": "retry_reduction",
            "title": f"{rpct:.0f}% of spend is retries",
            "detail": (
                f"${ce.get('retry_cost_usd', 0):.4f} ({rpct:.0f}% of total) is spent "
                f"re-running tasks that failed the first time"
                + (f", concentrated in: {', '.join(str(x) for x in rt_clusters[:3])}"
                   if rt_clusters else "")
                + ". Fix the root cause (timeout / tool errors) rather than "
                  "widening the retry budget."
            ),
            "projected_saving_pct": round(rpct, 1),
            "projected_saving_per_100k_usd": round(
                (_safe_float(ce.get("retry_cost_usd"), 0.0) or 0.0)
                / max(1, len(tasks)) * 100_000, 0,
            ),
            "risk": "fewer automatic recoveries — pair with a real reliability fix",
            "evidence": {"retry_cost_usd": ce.get("retry_cost_usd"),
                         "clusters": [str(x) for x in rt_clusters[:5]]},
        })

    return out or None


# ---------------------------------------------------------------------------
# Evaluator trust (P14) — "how much can I trust the numbers?"
#
# Every L2-L6 figure that involves the LLM judge inherits the judge's error. This
# surfaces three signals so the reader (and verdict_confidence) can react:
#   judge_vs_heuristic     : do the LLM judge and the token-overlap AccuracyEvaluator
#                            agree per task? systematic disagreement => one of them
#                            is wrong for this task type.
#   judge_calibration      : judge-vs-human agreement (MAE / Cohen's kappa) — only
#                            when a calibration run stashed it in extra_metrics.
#   judge_self_consistency : judge-vs-itself on identical input — only when a
#                            self-consistency run stashed it in extra_metrics.
# ---------------------------------------------------------------------------
_TRUST_DISAGREE_THRESHOLD = 0.40   # |judge_norm - accuracy| above this = a disagreement
_TRUST_AGREE_BAND = 0.25           # within this = the pair "agrees"


# ---------------------------------------------------------------------------
# Metric signal / redundancy (P46) — not every metric is load-bearing for a
# given agent. Correlate the per-task metrics: near-1 correlation means two
# metrics measure the same thing (tracking both adds ~0 information). When a
# task carries `extra.outcome` (a downstream signal — CSAT, thumbs, revenue),
# report which metrics actually predict it so effort goes to the ones that move
# the needle.
# ---------------------------------------------------------------------------
_MS_MIN_N = 5
_MS_REDUNDANT = 0.90


def _metric_signal_section(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    cols: dict[str, list[float | None]] = {
        "completion": [], "accuracy": [], "judge_overall": [],
        "faithfulness": [], "latency": [], "tokens": [],
    }
    outcomes: list[float | None] = []
    for t in tasks:
        cols["completion"].append(_safe_float(t.get("completion_score")))
        cols["accuracy"].append(_safe_float(t.get("accuracy_score")))
        j = t.get("llm_judge")
        sc = j.get("scores") if isinstance(j, dict) else None
        cols["judge_overall"].append(
            (_safe_float((sc or {}).get("overall")) or 0.0) / 10.0
            if isinstance(sc, dict) and sc.get("overall") is not None else None
        )
        cols["faithfulness"].append(
            (_safe_float((sc or {}).get("faithfulness")) or 0.0) / 5.0
            if isinstance(sc, dict) and sc.get("faithfulness") is not None else None
        )
        cols["latency"].append(_safe_float(t.get("execution_time")))
        tu = t.get("tokens_used")
        cols["tokens"].append(
            _safe_float(tu.get("total")) if isinstance(tu, dict) else None
        )
        ex = _task_extra(t) or {}
        ov = ex.get("outcome")
        outcomes.append(float(ov) if isinstance(ov, (int, float)) and not isinstance(ov, bool)
                        else None)

    live = {
        k: v for k, v in cols.items()
        if sum(1 for x in v if x is not None) >= _MS_MIN_N
    }
    if len(live) < 2:
        return None

    try:
        from agent_evaluator.utils.confidence import pearson_r
    except Exception:  # pragma: no cover - defensive
        return None

    names = sorted(live)
    correlations: list[dict[str, Any]] = []
    redundant: list[dict[str, Any]] = []
    for i in range(len(names)):
        for k in range(i + 1, len(names)):
            a, b = names[i], names[k]
            pairs = [
                (x, y) for x, y in zip(live[a], live[b])
                if x is not None and y is not None
            ]
            r = pearson_r([p[0] for p in pairs], [p[1] for p in pairs])
            if r is None:
                continue
            correlations.append({"a": a, "b": b, "r": r, "n": len(pairs)})
            if abs(r) >= _MS_REDUNDANT:
                redundant.append({
                    "pair": [a, b], "r": r,
                    "note": (f"'{a}' and '{b}' correlate {r:+.2f} — tracking both "
                             f"adds almost no information; keep one."),
                })

    outcome_corr: list[dict[str, Any]] = []
    n_out = sum(1 for o in outcomes if o is not None)
    if n_out >= _MS_MIN_N:
        for k in names:
            pairs = [
                (x, o) for x, o in zip(live[k], outcomes)
                if x is not None and o is not None
            ]
            r = pearson_r([p[0] for p in pairs], [p[1] for p in pairs])
            if r is not None:
                outcome_corr.append({"metric": k, "r": r, "n": len(pairs)})
        outcome_corr.sort(key=lambda d: -abs(d["r"]))

    note_bits = []
    if redundant:
        note_bits.append(
            f"{len(redundant)} metric pair(s) are redundant (|r| ≥ 0.9)"
        )
    if outcome_corr:
        top = outcome_corr[0]
        weak = [d for d in outcome_corr if abs(d["r"]) < 0.15]
        note_bits.append(
            f"'{top['metric']}' best predicts the recorded outcome (r={top['r']:+.2f})"
            + (f"; {', '.join(d['metric'] for d in weak)} barely move it — "
               "deprioritise work on those" if weak else "")
        )
    return {
        "metrics_analysed": names,
        "n_tasks": len(tasks),
        "correlations": correlations,
        "redundant_pairs": redundant,
        "outcome_correlation": outcome_corr or None,
        "note": ". ".join(note_bits) or "No redundant metric pairs; no outcome "
                                       "signal recorded (add extra.outcome to rank "
                                       "metrics by what they predict).",
    }


_JUDGE_SWING = 0.20          # normalised (/1) overall-score range that flags a task
_JUDGE_BUCKET_LINE = 0.60    # pass/fail bucket line on the normalised judge score
_JUDGE_MODEL_DRIFT = 0.10    # per-model mean gap above which models "disagree"


def _jr_runs(current: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the opt-in ``extra_metrics.judge_runs`` — either a bare list of run
    dicts or ``{"runs": [...]}``. Each run: ``{model?, cost_usd?, scores:
    {task_id: {overall, ...}}}`` (``scores`` may also be a list of
    ``{task_id, overall}``)."""
    em = (current.get("extra_metrics") or {}) if isinstance(current, dict) else {}
    jr = em.get("judge_runs")
    if isinstance(jr, dict):
        jr = jr.get("runs")
    return [r for r in jr if isinstance(r, dict)] if isinstance(jr, list) else []


def _jr_score_map(run: dict[str, Any]) -> dict[str, float]:
    """task_id -> normalised (/1) overall score for one run."""
    sc = run.get("scores")
    out: dict[str, float] = {}
    items: list[tuple[Any, Any]] = []
    if isinstance(sc, dict):
        items = list(sc.items())
    elif isinstance(sc, list):
        items = [(d.get("task_id"), d) for d in sc if isinstance(d, dict)]
    for tid, val in items:
        if tid is None:
            continue
        ov = val.get("overall") if isinstance(val, dict) else val
        ov = _safe_float(ov)
        if ov is None:
            continue
        out[str(tid)] = ov / 10.0 if ov > 1.0 else ov
    return out


def _judge_robustness_section(
    current: dict[str, Any], tasks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """P52: how much the deploy picture depends on *which* judge scored it.
    Needs ``extra_metrics.judge_runs`` with >= 2 runs (typically the same tasks
    scored by two judge models). No re-scoring — pure aggregation of what the
    pipeline recorded."""
    runs = _jr_runs(current)
    if len(runs) < 2:
        return None
    maps = [_jr_score_map(r) for r in runs]
    models = [str(r.get("model") or f"run{i + 1}") for i, r in enumerate(runs)]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    if not common:
        return None

    sensitive: list[dict[str, Any]] = []
    same_bucket = 0
    for tid in sorted(common):
        vals = [m[tid] for m in maps]
        spread = max(vals) - min(vals)
        buckets = {v >= _JUDGE_BUCKET_LINE for v in vals}
        flips = len(buckets) > 1
        if not flips:
            same_bucket += 1
        if flips or spread >= _JUDGE_SWING:
            sensitive.append({
                "task_id": tid,
                "models": models,
                "scores": [round(v, 3) for v in vals],
                "spread": round(spread, 3),
                "bucket_flip": flips,
            })
    sensitive.sort(key=lambda d: (-int(d["bucket_flip"]), -d["spread"]))

    per_model_mean = {
        models[i]: round(sum(maps[i][t] for t in common) / len(common), 4)
        for i in range(len(runs))
    }
    means = list(per_model_mean.values())
    drift = round(max(means) - min(means), 4)
    agreement = round(same_bucket / len(common), 3)

    judge_cost = sum(
        c for c in (_safe_float(r.get("cost_usd")) for r in runs) if c is not None
    )
    total_cost = None
    try:
        eff = (current.get("efficiency_metrics") or {}).get("tokens") or {}
        tc = _safe_float(eff.get("total_cost"))
        if tc is not None:
            total_cost = tc + judge_cost
    except Exception:  # pragma: no cover - defensive
        total_cost = None
    cost_share = (
        round(judge_cost / total_cost * 100.0, 1)
        if total_cost and total_cost > 0 else None
    )

    stable = drift < _JUDGE_MODEL_DRIFT and agreement >= 0.9
    note = (
        f"{len(models)} judge runs ({', '.join(models)}); "
        f"pass/fail agreement {agreement * 100:.0f}% over {len(common)} tasks, "
        f"per-model mean spread {drift:+.2f}. "
        + ("Verdict is stable across judges."
           if stable else
           f"{len(sensitive)} task(s) move enough to change their pass/fail call "
           f"depending on the judge — confirm those by hand.")
    )
    return {
        "n_runs": len(runs),
        "models": models,
        "n_comparable_tasks": len(common),
        "verdict_stability_across_models": {
            "stable": stable,
            "per_model_overall_mean": per_model_mean,
            "max_mean_gap": drift,
            "bucket_agreement_rate": agreement,
        },
        "judge_sensitive_tasks": sensitive[:20],
        "n_sensitive": len(sensitive),
        "judge_cost_usd": round(judge_cost, 4) if judge_cost else 0.0,
        "judge_cost_share_pct": cost_share,
        "note": note,
    }


def _evaluator_trust_section(
    tasks: list[dict[str, Any]], current: dict[str, Any],
) -> dict[str, Any] | None:
    em = (current.get("extra_metrics") or {}) if isinstance(current, dict) else {}

    pairs: list[tuple[str, float, float]] = []
    for t in tasks:
        j = t.get("llm_judge")
        if not isinstance(j, dict) or j.get("skipped"):
            continue
        ov = (j.get("scores") or {}).get("overall")
        acc = _safe_float(t.get("accuracy_score"))
        if not isinstance(ov, (int, float)) or acc is None:
            continue
        pairs.append((str(t.get("task_id") or "—"), float(ov) / 10.0, acc))

    jvh: dict[str, Any] | None = None
    if pairs:
        diffs = [abs(jn - ac) for _, jn, ac in pairs]
        disagreements = sorted(
            (
                {"task_id": tid, "judge": round(jn, 3), "heuristic": round(ac, 3),
                 "diff": round(abs(jn - ac), 3)}
                for tid, jn, ac in pairs
                if abs(jn - ac) > _TRUST_DISAGREE_THRESHOLD
            ),
            key=lambda d: -d["diff"],
        )
        jvh = {
            "n_comparable": len(pairs),
            "agreement_rate": round(sum(1 for d in diffs if d <= _TRUST_AGREE_BAND) / len(diffs), 3),
            "mean_abs_diff": round(sum(diffs) / len(diffs), 3),
            "disagreements": disagreements[:10],
        }

    calib = em.get("judge_calibration") if isinstance(em.get("judge_calibration"), dict) else None
    sc = em.get("judge_self_consistency")
    sc = sc if isinstance(sc, dict) else None

    if jvh is None and calib is None and sc is None:
        return None

    # roll up to a trust level (lowest wins), with reasons
    level = "high"
    reasons: list[str] = []

    def _demote(to: str, why: str) -> None:
        nonlocal level
        order = {"high": 2, "medium": 1, "low": 0}
        if order[to] < order[level]:
            level = to
        reasons.append(why)

    if jvh is not None:
        if jvh["agreement_rate"] < 0.5:
            _demote("low", f"LLM judge and heuristic scorer agree on only "
                           f"{jvh['agreement_rate'] * 100:.0f}% of tasks")
        elif jvh["agreement_rate"] < 0.7:
            _demote("medium", f"judge/heuristic agreement is "
                              f"{jvh['agreement_rate'] * 100:.0f}%")
    if calib is not None:
        kappas = [
            float(v["cohen_kappa_quadratic"])
            for v in (calib.get("dimensions") or {}).values()
            if isinstance(v, dict) and isinstance(v.get("cohen_kappa_quadratic"), (int, float))
        ]
        if kappas:
            worst = min(kappas)
            if worst < 0.4:
                _demote("low", f"judge-vs-human Cohen's kappa as low as {worst:.2f}")
            elif worst < 0.6:
                _demote("medium", f"judge-vs-human Cohen's kappa {worst:.2f}")
    if sc is not None and isinstance(sc.get("agreement"), (int, float)):
        if sc["agreement"] < 0.6:
            _demote("low", f"judge self-consistency only {sc['agreement'] * 100:.0f}%")
        elif sc["agreement"] < 0.8:
            _demote("medium", f"judge self-consistency {sc['agreement'] * 100:.0f}%")

    return {
        "judge_vs_heuristic": jvh,
        "judge_calibration": calib,
        "judge_self_consistency": sc,
        "trust_level": level,
        "trust_reasons": reasons,
    }


# ---------------------------------------------------------------------------
# RAG failure localization (P11) — split a RAG failure into
#   retrieval_miss   : the info needed to answer was never retrieved
#   grounding_miss    : it WAS retrieved, but the answer ignores / contradicts it
#   generation_error  : retrieved + grounded, but still wrong (reasoning / format)
# because the fix is completely different per class (top_k/re-rank vs prompt vs
# decoding). Coarse, deterministic, dependency-free — whitespace tokenization,
# not a re-run of the ML detector.
# ---------------------------------------------------------------------------
_RE_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_RAG_SUPPORT_THRESHOLD = 0.30      # sentence-in-context overlap below this = unsupported
_RAG_RECALL_MISS = 0.40           # gt-in-context overlap below this = retrieval miss
_RAG_UNSUPPORTED_MAX = 0.50       # unsupported-sentence ratio above this = not grounded
_RAG_MIN_SENTENCE_WORDS = 5

# Function words carry no grounding signal — a short vague sentence would otherwise
# score as "supported" just from "the / was / for" overlapping the context. Small
# English-leaning list (this is a coarse overlap heuristic, not the ML detector).
_RAG_STOPWORDS = frozenset(
    "a an the of to in on at by for and or but is are was were be been being it its "
    "this that these those i we you he she they them his her their our your as with "
    "from into about over under out up down off than then so no not do does did "
    "have has had will would can could should may might must if else when while "
    "which who whom whose what where why how all any both each few more most other "
    "some such only own same too very can just".split()
)

_RAG_REMEDIATION = {
    "retrieval_miss": (
        "The passage needed to answer was not in the retrieved context. Raise top_k, "
        "add a re-ranker, improve chunking/embeddings, or widen the query."
    ),
    "grounding_miss": (
        "The context contained the answer but the response ignored or contradicted it. "
        "Tighten the prompt ('answer only from the context, cite the passage'), lower "
        "temperature, or add a self-check / citation step."
    ),
    "generation_error": (
        "Context was retrieved and the answer stayed on it, but the result is still "
        "wrong — a reasoning or formatting error. Add few-shot examples, a verification "
        "step, or a stronger model for this task type."
    ),
}


def _wtok(text: Any) -> set[str]:
    """Content-word token set — lowercased, stopwords dropped, keeps digits."""
    return {
        w.lower() for w in _RE_WORD.findall(str(text or ""))
        if w.lower() not in _RAG_STOPWORDS
    }


def _raw_wordcount(text: Any) -> int:
    return len(_RE_WORD.findall(str(text or "")))


def _overlap(a: set[str], b: set[str]) -> float:
    return (len(a & b) / len(a)) if a else 0.0


def classify_rag_failure(
    *,
    response: str,
    context: str,
    ground_truth: str = "",
    accuracy: float | None = None,
    faithfulness: float | None = None,
) -> dict[str, Any] | None:
    """Classify one (RAG) task. Returns ``None`` when there is no retrieved
    context (not a RAG task). ``klass`` is ``ok`` when the task looks correct."""
    if not context or not str(context).strip():
        return None
    ctx_tok = _wtok(context)
    gt_tok = _wtok(ground_truth)
    recall = _overlap(gt_tok, ctx_tok) if gt_tok else None

    sentences = [s.strip() for s in re.split(r"[.\n]", str(response or "")) if s.strip()]
    long_sents = [s for s in sentences if _raw_wordcount(s) >= _RAG_MIN_SENTENCE_WORDS]
    unsupported = [
        s for s in long_sents
        if _wtok(s) and _overlap(_wtok(s), ctx_tok) < _RAG_SUPPORT_THRESHOLD
    ]
    unsupported_ratio = (len(unsupported) / len(long_sents)) if long_sents else 0.0

    grounded = unsupported_ratio <= _RAG_UNSUPPORTED_MAX
    if faithfulness is not None:
        grounded = grounded and faithfulness >= 0.6

    correct = accuracy is None or accuracy >= 0.7
    if correct:
        klass = "ok"
    elif recall is not None and recall < _RAG_RECALL_MISS:
        klass = "retrieval_miss"
    elif not grounded:
        klass = "grounding_miss"
    else:
        klass = "generation_error"

    # SPEC-041 P20: flag a classification that sits close to a threshold — the
    # coarse heuristic is least reliable there, so a human should confirm it.
    borderline = klass != "ok" and (
        (recall is not None and abs(recall - _RAG_RECALL_MISS) < 0.08)
        or abs(unsupported_ratio - _RAG_UNSUPPORTED_MAX) < 0.12
        or (accuracy is not None and abs(accuracy - 0.7) < 0.06)
    )
    return {
        "klass": klass,
        "borderline": bool(borderline),
        "context_recall": round(recall, 3) if recall is not None else None,
        "unsupported_ratio": round(unsupported_ratio, 3),
        "unsupported_claims": [s[:160] for s in unsupported[:3]],
    }


# ---------------------------------------------------------------------------
# Per-example score decomposition (P23) — "why did THIS task get THIS score".
# The blended accuracy number and the judge's verdict alone don't say which
# signal dragged a task down; this surfaces the breakdown that AccuracyEvaluator
# and the LLM judge already computed.
# ---------------------------------------------------------------------------
_QA_TYPES = frozenset({"qa", "information_retrieval", "reasoning", "chat"})


def _score_breakdowns_section(
    tasks: list[dict[str, Any]], *, limit: int = 12,
) -> list[dict[str, Any]] | None:
    failing = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    if not failing:
        return None
    try:
        from agent_evaluator.core.trackers.layer1 import AccuracyEvaluator

        _ae = AccuracyEvaluator()
    except Exception:  # pragma: no cover - defensive
        _ae = None

    failing.sort(key=lambda t: _safe_float(t.get("accuracy_score"), 1.0) or 1.0)
    out: list[dict[str, Any]] = []
    for t in failing[:limit]:
        acc = _safe_float(t.get("accuracy_score"))
        row: dict[str, Any] = {
            "task_id": str(t.get("task_id") or "—"),
            "task_type": str(t.get("task_type") or ""),
            "accuracy": round(acc, 3) if acc is not None else None,
            "completion": _safe_float(t.get("completion_score")),
        }
        signals: dict[str, float] = {}

        tt = str(t.get("task_type") or "").lower()
        gt = str(t.get("ground_truth") or "")
        resp = str(t.get("response") or "")
        if _ae is not None and gt and resp and (tt in _QA_TYPES or not tt):
            try:
                comps = _ae.decompose_qa(gt, resp)
                row["accuracy_components"] = {
                    k: comps[k] for k in
                    ("token_overlap_f1", "jaccard", "lcs_ratio", "char_sim")
                }
                row["accuracy_weakest"] = comps.get("weakest")
                signals.update(row["accuracy_components"])
            except Exception:  # pragma: no cover - defensive
                pass
        elif tt in ("coding", "code_generation"):
            row["accuracy_note"] = "1.0 iff the response is AST-parseable code, else 0.0"
        elif tt == "tool_use":
            row["accuracy_note"] = "0.6 floor when no tool_calls were recorded"

        j = t.get("llm_judge")
        if isinstance(j, dict) and not j.get("skipped"):
            sc = j.get("scores") or {}
            row["judge_overall"] = sc.get("overall")
            row["judge_reasoning"] = str(j.get("reasoning") or "")[:300] or None
            dims = {
                k: float(sc[k]) for k in
                ("completeness", "relevance", "factual_consistency", "faithfulness")
                if isinstance(sc.get(k), (int, float))
            }
            if dims:
                row["judge_dimensions"] = dims
                # judge dims are 0-5; normalise to 0-1 for the "weakest overall"
                signals.update({f"judge.{k}": v / 5.0 for k, v in dims.items()})

        if signals:
            row["weakest_signal"] = min(signals, key=lambda k: signals[k])
        out.append(row)
    return out or None


def _task_faithfulness(t: dict[str, Any]) -> float | None:
    j = t.get("llm_judge")
    if isinstance(j, dict) and not j.get("skipped"):
        f = (j.get("scores") or {}).get("faithfulness")
        if isinstance(f, (int, float)):
            return float(f) / 5.0 if f > 1.0 else float(f)
    extra = t.get("extra")
    if isinstance(extra, dict):
        for k in ("faithfulness", "ragas_faithfulness"):
            v = extra.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    return None


def rag_localization(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate ``classify_rag_failure`` over every task that has retrieved
    context. ``None`` when no task is a RAG task."""
    by_class: dict[str, int] = defaultdict(int)
    examples: list[dict[str, Any]] = []
    n_rag = 0
    n_borderline = 0
    borderline_task_ids: list[str] = []
    for t in tasks:
        res = classify_rag_failure(
            response=t.get("response") or "",
            context=t.get("context") or "",
            ground_truth=t.get("ground_truth") or "",
            accuracy=_safe_float(t.get("accuracy_score")),
            faithfulness=_task_faithfulness(t),
        )
        if res is None:
            continue
        n_rag += 1
        by_class[res["klass"]] += 1
        if res.get("borderline"):
            n_borderline += 1
            if t.get("task_id"):
                borderline_task_ids.append(str(t["task_id"]))
        if res["klass"] != "ok" and res["unsupported_claims"] and len(examples) < 10:
            examples.append({
                "task_id": str(t.get("task_id") or "—"),
                "klass": res["klass"],
                "context_recall": res["context_recall"],
                "borderline": bool(res.get("borderline")),
                "unsupported_claims": res["unsupported_claims"],
            })
    if n_rag == 0:
        return None
    failing = {k: v for k, v in by_class.items() if k != "ok"}
    return {
        "n_rag_tasks": n_rag,
        "n_borderline": n_borderline,
        "borderline_task_ids": borderline_task_ids[:15],
        "by_class": dict(by_class),
        "dominant_failure": (max(failing, key=lambda k: failing[k]) if failing else None),
        "remediation_by_class": {
            k: _RAG_REMEDIATION[k] for k in failing if k in _RAG_REMEDIATION
        },
        "unsupported_claim_examples": examples,
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _harness_groups(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {}
    return (report.get("extra_metrics") or {}).get("harness_groups", {}) or {}


def _gate_status(g: Any) -> str:
    if not isinstance(g, dict):
        return ""
    return str(g.get("gate") or g.get("status") or "").lower()


def _verdict_section(
    harness_groups: dict[str, Any],
    diagnosis: dict[str, Any] | None,
    ci: dict[str, Any],
    n_tasks: int,
    evaluator_trust: dict[str, Any] | None = None,
    security_findings: list[dict[str, Any]] | None = None,
    targets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fails, warns, passes = [], [], []
    for k in "ABCDEFG":
        g = harness_groups.get(k)
        st = _gate_status(g)
        if st == "fail":
            fails.append(k)
        elif st == "warn":
            warns.append(k)
        elif st == "pass":
            passes.append(k)

    # P43: gates that clear the built-in line but fall short of a stricter *user*
    # target — a "caution", not an SDK fail.
    _user = False
    below_user_target: list[str] = []
    try:
        from agent_evaluator.utils.targets import gate_target, is_user_defined

        _user = is_user_defined(targets)
        if _user:
            for k in "ABCDEFG":
                if k in fails or k in warns:
                    continue
                sc = _safe_float((harness_groups.get(k) or {}).get("score"))
                if sc is not None and sc < gate_target(targets, k) - 1e-9:
                    below_user_target.append(k)
    except Exception:  # pragma: no cover - defensive
        pass

    _bar = " your target" if _user else " target"
    if fails:
        level = "not_ready"
        headline = f"{len(fails)} Gate(s) failing: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k in fails
        )
    elif warns or below_user_target:
        level = "caution"
        _lo = warns + below_user_target
        headline = f"{len(_lo)} Gate(s) below{_bar}: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k in _lo
        )
    elif passes:
        level = "ready"
        headline = (f"All {len(passes)} measured Gates meet{_bar}."
                    if _user else f"All {len(passes)} measured Gates pass.")
    else:
        level = "unknown"
        headline = "No Harness Gate data — pass Harness Config to get a verdict."

    shortfalls_by_gate: dict[str, list] = {}
    if diagnosis:
        for f in diagnosis.get("findings") or []:
            shortfalls_by_gate[f.get("gate")] = f.get("component_shortfalls") or []

    try:
        from agent_evaluator.ontology.metric_registry import component_guidance_for
    except Exception:  # pragma: no cover - defensive
        component_guidance_for = lambda _f: None  # noqa: E731

    # fields whose Gate score component fell below its minimum sample size — an
    # action recommended on one of these is shaky, so mark it and don't let it be
    # the headline when a better-supported shortfall exists.
    low_sample_fields: set[str] = set()
    for _g in harness_groups.values():
        if not isinstance(_g, dict):
            continue
        for _w in (_g.get("details") or {}).get("insufficient_data_warnings") or []:
            _name = str(_w).split(":", 1)[0].strip().lower()
            if _name:
                low_sample_fields.add(_name)

    def _is_low_sample(field: str) -> bool:
        f = str(field or "").replace("avg_", "").strip().lower()
        return f in low_sample_fields or any(f == w or f.endswith("_" + w) for w in low_sample_fields)

    next_actions: list[dict[str, Any]] = []

    # C1: a critical/high security finding is the top action, above any Gate.
    for _sf in security_findings or []:
        if _sf.get("severity") in ("critical", "high"):
            next_actions.append({
                "gate": "E", "field": _sf.get("threat_type"), "health": None,
                "action": (f"Investigate the {_sf.get('severity')} "
                           f"{_sf.get('threat_type')} on task {_sf.get('task_id')} "
                           f"before shipping — the Gate E score is rate-based and can "
                           f"still pass with a severe finding."),
                "security": True,
                "derived_from": {
                    "source": "security_finding",
                    "tracker": _sf.get("tracker"),
                    "task_id": _sf.get("task_id"),
                    "threat_type": _sf.get("threat_type"),
                    "severity": _sf.get("severity"),
                },
            })
            break

    for k in (fails + warns + below_user_target)[:3]:
        sf = list(shortfalls_by_gate.get(k) or [])
        # push low-sample components to the back so a solidly-measured shortfall wins
        sf.sort(key=lambda s: _is_low_sample(s.get("field", "")))
        if sf:
            top = sf[0]
            fld = str(top.get("field", ""))
            next_actions.append({
                "gate": k,
                "field": fld,
                "health": top.get("health"),
                "action": component_guidance_for(fld) or "",
                "low_sample": _is_low_sample(fld),
                "derived_from": {
                    "source": "gate_component_shortfall",
                    "gate": k,
                    "field": fld,
                    "health": top.get("health"),
                    "low_sample": _is_low_sample(fld),
                },
            })
        else:
            g = harness_groups.get(k) or {}
            _sc = _safe_float(g.get("score"))
            _sc_s = f"{_sc:.2f}" if _sc is not None else "n/a"
            next_actions.append({
                "gate": k,
                "field": None,
                "health": None,
                "action": f"See the Gate {k} section (score {_sc_s}).",
                "derived_from": {
                    "source": "gate_score", "gate": k, "score": _sc,
                },
            })

    conf_level: str | None = None
    conf_reasons: list[str] = []
    try:
        from agent_evaluator.utils.confidence import verdict_confidence

        drv = fails or warns
        ncomp = margin = None
        if drv:
            gk = drv[0]
            sf = shortfalls_by_gate.get(gk)
            if sf is not None:
                ncomp = len(sf)
            sc = (harness_groups.get(gk) or {}).get("score")
            if isinstance(sc, (int, float)):
                margin = float(sc) - 0.8
        conf_level, conf_reasons = verdict_confidence(
            n_tasks=n_tasks,
            tcr_ci_halfwidth=ci.get("tcr_ci_halfwidth"),
            n_gate_components=ncomp,
            margin_to_threshold=margin,
            judge_trust=(evaluator_trust or {}).get("trust_level"),
        )
    except Exception:  # pragma: no cover - defensive
        pass

    return {
        "level": level,
        "headline": headline,
        "failing_gates": fails,
        "warning_gates": warns,
        "passing_gates": passes,
        "below_user_target_gates": below_user_target,
        "targets_source": "user" if _user else "builtin",
        "targets": targets if _user else None,
        "confidence": conf_level,
        "confidence_reasons": conf_reasons,
        "next_actions": next_actions,
    }


# ---------------------------------------------------------------------------
# Threshold sensitivity (P44) — the verdict hinges on two arbitrary constants:
# the gate pass line (0.7) and the per-task accuracy threshold (0.7). Sweep both
# and show whether the deploy decision is robust or one 0.05 from flipping.
# ---------------------------------------------------------------------------
_TS_GATE_LINES = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)
_TS_ACC_THR = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)


def _ts_verdict(scores: list[float], line: float) -> str:
    if not scores:
        return "unknown"
    if any(s < line - 0.15 for s in scores):
        return "not_ready"
    if any(s < line for s in scores):
        return "caution"
    return "ready"


def _threshold_sensitivity_section(
    harness_groups: dict[str, Any],
    tasks: list[dict[str, Any]],
    targets: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    scores = [
        _safe_float((harness_groups.get(k) or {}).get("score"))
        for k in "ABCDEFG"
    ]
    scores = [s for s in scores if s is not None]
    accs = [a for a in (_safe_float(t.get("accuracy_score")) for t in tasks) if a is not None]
    if not scores and not accs:
        return None

    try:
        from agent_evaluator.utils.targets import gate_target, is_user_defined

        cur_line = gate_target(targets, "A", _READINESS_TARGET) if is_user_defined(targets) \
            else _READINESS_TARGET
    except Exception:  # pragma: no cover - defensive
        cur_line = _READINESS_TARGET

    gate_sweep = [
        {
            "line": ln,
            "gates_meeting": sum(1 for s in scores if s >= ln - 1e-9),
            "gates_below": sum(1 for s in scores if s < ln - 1e-9),
            "verdict": _ts_verdict(scores, ln),
        }
        for ln in _TS_GATE_LINES
    ]
    acc_sweep = [
        {
            "threshold": thr,
            "pass_rate_pct": round(
                sum(1 for a in accs if a >= thr - 1e-9) / len(accs) * 100.0, 1,
            ) if accs else None,
        }
        for thr in _TS_ACC_THR
    ]

    # knife-edge: does the verdict at the current line differ from ±0.05?
    cur_v = _ts_verdict(scores, cur_line)
    lo_v = _ts_verdict(scores, max(0.0, cur_line - 0.05))
    hi_v = _ts_verdict(scores, cur_line + 0.05)
    knife = bool(scores) and (lo_v != cur_v or hi_v != cur_v)
    detail = ""
    if knife:
        bits = []
        if lo_v != cur_v:
            bits.append(f"at {cur_line - 0.05:.2f} it would be '{lo_v}'")
        if hi_v != cur_v:
            bits.append(f"at {cur_line + 0.05:.2f} it would be '{hi_v}'")
        detail = (f"The readiness call is '{cur_v}' at the {cur_line:.2f} pass line; "
                  + "; ".join(bits) + " — the decision is sensitive to where the "
                  "line is drawn.")

    return {
        "current_line": round(cur_line, 3),
        "swept_verdict_at_current_line": cur_v,
        "knife_edge": knife,
        "knife_edge_detail": detail,
        "gate_line_sweep": gate_sweep,
        "accuracy_threshold_sweep": acc_sweep,
        "n_gates_measured": len(scores),
        "n_tasks_with_accuracy": len(accs),
    }


# ---------------------------------------------------------------------------
# Path to green (P29) — the verdict says "not ready"; this quantifies the gap
# to each gate's pass line and orders the failure clusters into a fix plan with
# a deterministic projection of "close these N and Gate A reaches ~0.74".
# ---------------------------------------------------------------------------

# score >= 0.7 is the built-in gate "pass" line (gates/base.py::_status warn=0.7).
# A CI run may set a stricter custom threshold; this is the SDK default target.
_READINESS_TARGET = 0.7
_TCR_DRIVEN_GATES = ("A", "C")


def _fix_effort_hint(sig: str) -> tuple[str, list[str]]:
    """(effort hint, gates the fix most likely moves) from a reason signature."""
    s = (sig or "").lower()
    if s.startswith("error:") or "timeout" in s or "exceeded" in s:
        return ("Reliability / infra — review retry and timeout handling "
                "(FaultToleranceConfig, RetryConfig).", ["C", "D"])
    if ("not grounded" in s or "contradict" in s or "retrieved context" in s
            or "hallucin" in s or "unsupported" in s):
        return ("Retrieval or grounding — re-rank or raise top_k, and tighten "
                "the 'answer only from context' instruction.", ["A", "C", "G"])
    if ("part of" in s or "multi-step" in s or "incomplete" in s
            or "remaining steps" in s or "steps" in s):
        return ("Task decomposition — add SubtaskConfig so each step is "
                "verified before the next.", ["A"])
    if ("loop" in s or "repeat" in s or "scope" in s or "unauthorized" in s
            or "injection" in s or "ignore previous" in s):
        return ("Guardrail config — LoopDetectionConfig / ScopeConfig / "
                "ToolParameterSafetyConfig.", ["B", "E"])
    return ("Review the worst-case examples in this cluster to find the shared "
            "root cause.", ["A"])


# P37: rough relative effort of each fix category (higher = more work). Used only
# to rank clusters by ROI (readiness gain per unit effort) — not a time estimate.
_EFFORT_WEIGHT = {
    "data": 1.0, "runtime": 2.0, "guardrail": 2.0,
    "grounding": 3.0, "decomposition": 3.0, "generic": 4.0,
}


def _effort_weight_for_sig(sig: str) -> float:
    s = (sig or "").lower()
    if s.startswith("error:") or "timeout" in s or "exceeded" in s:
        return _EFFORT_WEIGHT["runtime"]
    if ("not grounded" in s or "contradict" in s or "retrieved context" in s
            or "hallucin" in s or "unsupported" in s):
        return _EFFORT_WEIGHT["grounding"]
    if "part of" in s or "multi-step" in s or "remaining steps" in s:
        return _EFFORT_WEIGHT["decomposition"]
    if ("loop" in s or "repeat" in s or "scope" in s or "unauthorized" in s
            or "injection" in s or "ignore previous" in s):
        return _EFFORT_WEIGHT["guardrail"]
    if "ground_truth similarity" in s or "label" in s or "suspicious" in s:
        return _EFFORT_WEIGHT["data"]
    return _EFFORT_WEIGHT["generic"]


_PROJ_BOOT_N = 400
_PROJ_SEED = 12345


def _readiness_section(
    tasks: list[dict[str, Any]],
    harness_groups: dict[str, Any],
    targets: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """P29: quantified distance to a passing verdict + an impact-ordered fix
    plan with a deterministic projection. ``None`` when there is nothing to
    plan (no failing/warning gate and no failure cluster). P43: measures against
    the user's per-gate target when ``targets`` is given, else the built-in 0.7."""
    try:
        from agent_evaluator.utils.targets import gate_target, is_user_defined
    except Exception:  # pragma: no cover - defensive
        gate_target = lambda _t, _k, default=_READINESS_TARGET: default  # noqa: E731
        is_user_defined = lambda _t: False  # noqa: E731
    _user_targets = is_user_defined(targets)

    def _gt(k: str) -> float:
        return gate_target(targets, k, _READINESS_TARGET)

    fails, warns = [], []
    for k in "ABCDEFG":
        st = _gate_status(harness_groups.get(k))
        sc = _safe_float((harness_groups.get(k) or {}).get("score"))
        if st == "fail":
            fails.append(k)
        elif st == "warn":
            warns.append(k)
        elif _user_targets and sc is not None and sc < _gt(k) - 1e-9:
            warns.append(k)          # clears the SDK line but not the user's bar
    if not tasks:
        return None

    # --- current outcome rates (exact per-task means) ----------------------
    comps = [c for c in (_safe_float(t.get("completion_score")) for t in tasks) if c is not None]
    accs = [a for a in (_safe_float(t.get("accuracy_score")) for t in tasks) if a is not None]
    cur_tcr = (sum(comps) / len(comps)) if comps else None
    cur_acc = (sum(accs) / len(accs)) if accs else None
    pass_accs = [
        _safe_float(t.get("accuracy_score"))
        for t in tasks
        if not _effective_fail(success=t.get("success", False),
                               accuracy=t.get("accuracy_score"),
                               completion=t.get("completion_score"))
    ]
    pass_accs = [a for a in pass_accs if a is not None]
    passing_acc = (sum(pass_accs) / len(pass_accs)) if pass_accs else 0.85

    # --- failure clusters by signature (P35: one row per root cause; the
    # per-task_type split was noise — the effort hint and target gates are
    # identical per signature, so task_type is just a sub-label).
    pool = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in pool:
        buckets[_reason_signature(_task_reason(t))].append(t)
    # Order by *projected TCR recovery* if that cluster's tasks flipped to passing —
    # not by raw size. A 3-task cluster of accuracy-only failures (completion already
    # ~1.0) recovers almost no TCR and must not outrank a 3-task cluster of timeouts.
    _tot = max(1, len(tasks))

    def _standalone_tcr_gain(members: list[dict[str, Any]]) -> float:
        return sum(
            max(0.0, 1.0 - (_safe_float(m.get("completion_score")) or 0.0))
            for m in members
        ) / _tot

    ranked = sorted(
        buckets.items(),
        key=lambda kv: (-_standalone_tcr_gain(kv[1]), -len(kv[1]), kv[0]),
    )

    if not fails and not warns and not ranked:
        return None

    total = len(tasks)
    # P37: base pass-rate prior for the flip bootstrap — Beta(passes+1, fails+1).
    _n_pass_set = sum(
        0 if _effective_fail(success=t.get("success", False),
                             accuracy=t.get("accuracy_score"),
                             completion=t.get("completion_score")) else 1
        for t in tasks
    )
    _beta_a, _beta_b = _n_pass_set + 1.0, (total - _n_pass_set) + 1.0
    below_all = fails + warns
    _cur_scores = {
        k: (_safe_float((harness_groups.get(k) or {}).get("score")) or 0.0)
        for k in below_all
    }

    fixed_ids: set[str] = set()
    fixed_lift: list[float] = []          # (1 − completion) of every task fixed so far
    lift_by_rank: dict[int, list[float]] = {}
    fix_plan: list[dict[str, Any]] = []
    for rank, (sig, members) in enumerate(ranked[:8], 1):
        for m in members:
            if m.get("task_id"):
                fixed_ids.add(str(m["task_id"]))
                fixed_lift.append(
                    max(0.0, 1.0 - (_safe_float(m.get("completion_score")) or 0.0))
                )
        lift_by_rank[rank] = list(fixed_lift)
        proj_tcr = sum(
            1.0 if str(t.get("task_id")) in fixed_ids
            else (_safe_float(t.get("completion_score")) or 0.0)
            for t in tasks
        ) / total
        proj_acc = sum(
            passing_acc if str(t.get("task_id")) in fixed_ids
            else (_safe_float(t.get("accuracy_score")) or 0.0)
            for t in tasks
        ) / total
        hint, tgt_gates = _fix_effort_hint(sig)
        ttypes = sorted({str(m.get("task_type") or "—") for m in members} - {"—"})
        _cum_gain = proj_tcr - (cur_tcr or 0.0)

        # P37: project every below-target gate at this rank, with a bootstrap CI on
        # the TCR-driven ones (A/C move with completion; B/D/E/F/G are held — task
        # outcomes don't change latency/cost/security). `moves` says which is which.
        proj_gate_scores: dict[str, float] = {}
        proj_gate_ci: dict[str, list[float]] = {}
        gate_moves: dict[str, bool] = {}
        _rng = random.Random(_PROJ_SEED + rank)
        _samples: dict[str, list[float]] = {k: [] for k in below_all if k in _TCR_DRIVEN_GATES}
        for _ in range(_PROJ_BOOT_N if _samples else 0):
            _p = _rng.betavariate(_beta_a, _beta_b)
            _gain_b = sum(lf for lf in fixed_lift if _rng.random() < _p) / total
            for k in _samples:
                _samples[k].append(min(1.0, _cur_scores[k] + _gain_b))
        for k in below_all:
            if k in _TCR_DRIVEN_GATES:
                proj_gate_scores[k] = round(min(1.0, _cur_scores[k] + _cum_gain), 3)
                gate_moves[k] = True
                if _samples.get(k):
                    ss = sorted(_samples[k])
                    lo = ss[int(0.025 * (len(ss) - 1))]
                    hi = ss[int(0.975 * (len(ss) - 1))]
                    proj_gate_ci[k] = [round(lo, 3), round(hi, 3)]
            else:
                proj_gate_scores[k] = round(_cur_scores[k], 3)
                gate_moves[k] = False

        _gap_closed_pp = sum(
            max(0.0, min(_gt(k), proj_gate_scores[k])
                - min(_gt(k), _cur_scores[k])) * 100.0
            for k in below_all if k in _TCR_DRIVEN_GATES
        )
        _eff = _effort_weight_for_sig(sig)

        fix_plan.append({
            "rank": rank,
            "signature": sig,
            "task_types": ttypes,
            "task_type": ttypes[0] if len(ttypes) == 1 else None,  # back-compat
            "count": len(members),
            "impact_pct": round(len(members) / total * 100.0, 1),
            "example_task_ids": [str(m.get("task_id")) for m in members[:5] if m.get("task_id")],
            "effort_hint": hint,
            "effort_weight": _eff,
            "targets_gates": tgt_gates,
            "projected_tcr_after_pct": round(proj_tcr * 100.0, 1),
            "projected_accuracy_after_pct": round(proj_acc * 100.0, 1),
            "cumulative_tcr_gain_pp": round(_cum_gain * 100.0, 1),
            "projected_gate_scores": proj_gate_scores,
            "projected_gate_scores_ci": proj_gate_ci,
            "gate_moves": gate_moves,
            "roi": round(_gap_closed_pp / _eff, 2),
            "derived_from": {
                "source": "failure_cluster",
                "signature": sig,
                "n": len(members),
                "impact_pct": round(len(members) / total * 100.0, 1),
                "example_task_ids": [
                    str(m.get("task_id")) for m in members[:5] if m.get("task_id")
                ],
            },
        })

    # Every below-target gate is a candidate for the plan to lift. Split into the
    # ones task outcomes actually move (A/C) and the rest (latency/cost/safety).
    below = fails + warns
    tcr_blockers = [k for k in below if k in _TCR_DRIVEN_GATES]
    other_blockers = [k for k in below if k not in _TCR_DRIVEN_GATES]
    _only_warn = not fails

    def _gain_at(rank: int) -> float:
        if not fix_plan:
            return 0.0
        rank = max(1, min(rank, len(fix_plan)))
        return fix_plan[rank - 1]["projected_tcr_after_pct"] / 100.0 - (cur_tcr or 0.0)

    # smallest N fixes after which every TCR-driven below-target gate reaches target
    ready_after: int | None = None
    if tcr_blockers and fix_plan:
        for item in fix_plan:
            gain = item["projected_tcr_after_pct"] / 100.0 - (cur_tcr or 0.0)
            if all(
                (_safe_float((harness_groups.get(k) or {}).get("score")) or 0.0) + gain
                >= _gt(k)
                for k in tcr_blockers
            ):
                ready_after = item["rank"]
                break

    # P35: project each gate at the *recommended* number of fixes (ready_after),
    # or the full plan when the plan can't clear it — not always the full plan.
    _plan_rank = ready_after if ready_after is not None else len(fix_plan)
    plan_gain = _gain_at(_plan_rank)

    gaps: list[dict[str, Any]] = []
    for k in fails + warns:
        g = harness_groups.get(k) or {}
        score = _safe_float(g.get("score"))
        row: dict[str, Any] = {
            "gate": k,
            "gate_name": _GATE_FULL.get(k, k),
            "score": None if score is None else round(score, 3),
            "target": round(_gt(k), 3),
            "gap": None if score is None else round(_gt(k) - score, 3),
            "blocking": k in fails,
        }
        if score is not None and k in _TCR_DRIVEN_GATES:
            row["projected_score_after_plan"] = round(min(1.0, score + plan_gain), 3)
            row["after_plan_fixes"] = _plan_rank
            row["estimate"] = True
        gaps.append(row)

    # projected TCR-driven gate scores at _plan_rank, for the note
    proj_scores = {
        k: round(min(1.0, (_safe_float((harness_groups.get(k) or {}).get("score")) or 0.0)
                     + plan_gain), 2)
        for k in tcr_blockers
    }
    _proj_str = ", ".join(f"Gate {k} ~{v:.2f}" for k, v in proj_scores.items())

    # P37: bootstrap "how likely is the plan to actually clear the TCR blockers,
    # and after how many fixes" — draws a pass-rate, flips each fixed task, and
    # finds the first rank where every TCR blocker clears target.
    p_ready: float | None = None
    likely_fix_count: int | None = None
    if tcr_blockers and fix_plan:
        _rng2 = random.Random(_PROJ_SEED + 999)
        _clear_ranks: list[int | None] = []
        for _ in range(_PROJ_BOOT_N):
            _p = _rng2.betavariate(_beta_a, _beta_b)
            _hit: int | None = None
            for r in range(1, len(fix_plan) + 1):
                _g = sum(lf for lf in lift_by_rank[r] if _rng2.random() < _p) / total
                if all(_cur_scores[k] + _g >= _gt(k) for k in tcr_blockers):
                    _hit = r
                    break
            _clear_ranks.append(_hit)
        _hits = [r for r in _clear_ranks if r is not None]
        p_ready = round(len(_hits) / len(_clear_ranks), 3)
        if _hits:
            likely_fix_count = Counter(_hits).most_common(1)[0][0]

    _word = "warning" if _only_warn else "failing"
    _tgt = "your target" if _user_targets else "target"
    if not tcr_blockers and not other_blockers:
        note = (f"No gate is below {_tgt}; the fix plan is ordered by how much TCR "
                "each cluster is costing you.")
    elif ready_after is not None and not other_blockers:
        note = (f"Closing the top {ready_after} cluster(s) is projected to bring "
                f"every {_word} gate to {_tgt} ({_proj_str}; estimate — assumes "
                f"those tasks then pass and nothing else moves).")
    elif other_blockers:
        _head = (
            f"Closing the top {ready_after} cluster(s) is projected to bring the "
            f"TCR-driven gate(s) to {_tgt} ({_proj_str}). "
            if (ready_after is not None and tcr_blockers) else
            (f"The full fix plan lifts the TCR-driven gate(s) to about "
             f"{_proj_str}, still short of {_tgt}. " if tcr_blockers else "")
        )
        note = (_head + "Gate(s) "
                + ", ".join(f"{k} ({_GATE_FULL.get(k, k)})" for k in other_blockers)
                + " are not driven by task outcomes — the fix plan will not move "
                "them; address them from their own Gate section.")
    else:
        note = (f"The full fix plan lifts the {_word} TCR-driven gate(s) to about "
                f"{_proj_str} — still short of {_tgt}, more or deeper fixes needed.")

    return {
        "target_gate_score": _READINESS_TARGET,
        "targets_source": "user" if _user_targets else "builtin",
        "per_gate_targets": (
            {k: round(_gt(k), 3) for k in (fails + warns)} if _user_targets else None
        ),
        "current_tcr_pct": None if cur_tcr is None else round(cur_tcr * 100.0, 1),
        "current_accuracy_pct": None if cur_acc is None else round(cur_acc * 100.0, 1),
        "gaps": gaps,
        "fix_plan": fix_plan,
        "projected_ready_after": {
            "ready_after_n_items": ready_after,
            "plan_fixes_projected": _plan_rank,
            "projected_gate_scores": proj_scores,
            "remaining_structural_blockers": other_blockers,
            "p_ready": p_ready,
            "likely_fix_count": likely_fix_count,
            "note": note,
        },
    }


def _reference_frame_section(
    current: dict[str, Any],
    harness_groups: dict[str, Any],
    tasks: list[dict[str, Any]],
    reference: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """P53: where this run sits against an external reference distribution
    (``.aoo/reference.json``) — percentile + gap to the frontier. Pure lookup,
    no new scoring. ``None`` when no reference is configured."""
    try:
        from agent_evaluator.utils.reference import (
            is_defined,
            percentile_of,
            reference_frontier,
            reference_median,
        )
    except Exception:  # pragma: no cover - defensive
        return None
    if not is_defined(reference):
        return None

    comps = [_safe_float(t.get("completion_score")) for t in tasks]
    comps = [c for c in comps if c is not None]
    cur_tcr = (sum(comps) / len(comps) * 100.0) if comps else None

    def _one(label: str, value: Any, entry: Any, *, pct_scale: bool) -> dict[str, Any] | None:
        if not isinstance(value, (int, float)) or entry is None:
            return None
        med = reference_median(entry)
        front = reference_frontier(entry)
        pctile = percentile_of(value, entry)
        gap = None if med is None else round(value - med, 3 if not pct_scale else 1)
        vd = "at reference"
        if med is not None:
            tol = 1.0 if pct_scale else 0.01
            vd = ("above reference" if value > med + tol
                  else "below reference" if value < med - tol else "at reference")
        return {
            "metric": label,
            "value": round(value, 3 if not pct_scale else 1),
            "reference_median": med,
            "reference_frontier": front,
            "percentile": pctile,
            "gap": gap,
            "gap_to_frontier": None if front is None else round(value - front,
                                                               3 if not pct_scale else 1),
            "verdict": vd,
        }

    rows: list[dict[str, Any]] = []
    tcr_row = _one("tcr", cur_tcr, reference.get("tcr_pct"), pct_scale=True)
    if tcr_row:
        rows.append(tcr_row)
    for k in "ABCDEFG":
        sc = _safe_float((harness_groups.get(k) or {}).get("score"))
        ent = (reference.get("gate_scores") or {}).get(k)
        r = _one(f"gate_{k.lower()}", sc, ent, pct_scale=False)
        if r:
            rows.append(r)
    if not rows:
        return None

    below = [r["metric"] for r in rows if r["verdict"] == "below reference"]

    # weakest metric relative to the reference: lowest percentile among those that
    # have one, else the largest *relative* shortfall vs the frontier (pp and
    # score scales are not comparable, so normalise by the frontier value).
    def _rel_short(r: dict[str, Any]) -> float:
        f = r.get("reference_frontier")
        g = r.get("gap_to_frontier")
        if not isinstance(f, (int, float)) or not isinstance(g, (int, float)) or f == 0:
            return 0.0
        return g / abs(f)

    with_pct = [r for r in rows if isinstance(r.get("percentile"), int)]
    weakest = None
    if with_pct:
        weakest = min(with_pct, key=lambda r: r["percentile"])
    else:
        cand = [r for r in rows if _rel_short(r) < 0]
        weakest = min(cand, key=_rel_short) if cand else None

    tcr_pctile = tcr_row.get("percentile") if tcr_row else None
    bits = []
    if tcr_pctile is not None:
        bits.append(f"TCR is p{tcr_pctile} vs the "
                    f"'{reference.get('label', 'reference')}' reference")
    elif tcr_row and tcr_row.get("gap") is not None:
        bits.append(f"TCR is {tcr_row['gap']:+.1f}pp vs the reference point")
    if weakest is not None and weakest["verdict"] == "below reference":
        wp = weakest.get("percentile")
        wtxt = (f"{_pretty_metric_name(weakest['metric'])} is the weakest at "
                + (f"p{wp}" if isinstance(wp, int)
                   else f"{_rel_short(weakest) * 100:.0f}% below the frontier"))
        bits.append(wtxt)
    elif not below:
        bits.append("every measured metric is at or above the reference")

    return {
        "label": reference.get("label"),
        "source": reference.get("source"),
        "metrics": rows,
        "below_reference": below,
        "furthest_from_frontier": (
            {"metric": weakest["metric"], "percentile": weakest.get("percentile"),
             "gap": weakest.get("gap_to_frontier"),
             "frontier": weakest.get("reference_frontier")}
            if weakest is not None and weakest["verdict"] == "below reference" else None
        ),
        "summary": "; ".join(bits) or "reference comparison unavailable",
    }


def _pretty_metric_name(m: str) -> str:
    if m == "tcr":
        return "TCR"
    if m.startswith("gate_"):
        return "Gate " + m.split("_", 1)[1].upper()
    return m


def _metric_confidence_section(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n_tasks": len(tasks)}
    comps = [_safe_float(t.get("completion_score")) for t in tasks]
    accs = [_safe_float(t.get("accuracy_score")) for t in tasks]
    comps = [c for c in comps if c is not None]
    accs = [a for a in accs if a is not None]
    if comps:
        out["tcr_pct"] = round(sum(comps) / len(comps) * 100.0, 2)
    if accs:
        out["accuracy_pct"] = round(sum(accs) / len(accs) * 100.0, 2)
    try:
        from agent_evaluator.utils.confidence import bootstrap_mean_ci

        if comps:
            lo, hi = bootstrap_mean_ci(comps)
            out["tcr_ci_pct"] = [round(lo * 100.0, 2), round(hi * 100.0, 2)]
            out["tcr_ci_halfwidth"] = round((hi - lo) / 2.0, 4)
        if accs:
            lo, hi = bootstrap_mean_ci(accs)
            out["accuracy_ci_pct"] = [round(lo * 100.0, 2), round(hi * 100.0, 2)]
    except Exception:  # pragma: no cover - defensive
        pass
    return out


_RUNNING_MIN_TASKS = 10


def _running_verdict_section(
    tasks: list[dict[str, Any]],
    harness_groups: dict[str, Any],
    *,
    targets: dict[str, Any] | None = None,
    min_tasks: int = _RUNNING_MIN_TASKS,
) -> dict[str, Any]:
    """P50: a mid-run readiness call for early-stop. Binary task pass-rate
    (``not _effective_fail``) + Wilson CI vs the TCR target, plus a check that
    every *measured* gate is at its bar. ``decisive`` means: keep sampling
    cannot flip the call.

      - CI upper bound already below target        -> decisive, not_ready
      - CI lower bound at/above target AND every
        measured gate >= its target                -> decisive, ready
      - otherwise                                  -> undecided (keep going)
    """
    n = len(tasks)
    passes = sum(
        1 for t in tasks
        if not _effective_fail(
            success=t.get("success", False),
            accuracy=t.get("accuracy_score"),
            completion=t.get("completion_score"),
        )
    )
    accs = [_safe_float(t.get("accuracy_score")) for t in tasks]
    accs = [a for a in accs if a is not None]
    try:
        from agent_evaluator.utils.targets import gate_target
    except Exception:  # pragma: no cover - defensive
        def gate_target(targets: Any, gate: str, default: float = 0.7) -> float:
            return default

    target_tcr = 70.0
    if isinstance(targets, dict) and isinstance(targets.get("tcr_pct"), (int, float)):
        target_tcr = float(targets["tcr_pct"])

    gates_below: list[str] = []
    for k in "ABCDEFG":
        gd = harness_groups.get(k) or {}
        sc = gd.get("score")
        if isinstance(sc, (int, float)) and sc < gate_target(targets, k, _READINESS_TARGET) - 1e-9:
            gates_below.append(k)

    out: dict[str, Any] = {
        "n_tasks": n,
        "pass_rate_pct": round(passes / n * 100.0, 2) if n else None,
        "accuracy_pct": round(sum(accs) / len(accs) * 100.0, 2) if accs else None,
        "target_tcr_pct": round(target_tcr, 2),
        "gates_below_target": gates_below,
        "decisive": False,
        "verdict": "undecided",
        "reason": "",
    }
    if n < min_tasks:
        out["reason"] = f"only {n} task(s) so far — need >= {min_tasks} for a call"
        return out
    try:
        from agent_evaluator.utils.confidence import wilson_interval

        lo, hi = wilson_interval(passes, n)
    except Exception:  # pragma: no cover - defensive
        return out
    lo_pp, hi_pp = round(lo * 100.0, 2), round(hi * 100.0, 2)
    out["pass_rate_ci_pct"] = [lo_pp, hi_pp]

    if hi_pp < target_tcr:
        out.update(
            decisive=True, verdict="not_ready",
            reason=(f"pass-rate 95% CI upper bound {hi_pp:.1f}% is still below the "
                    f"{target_tcr:.0f}% target after {n} tasks — more tasks will "
                    f"not clear it"),
        )
    elif lo_pp >= target_tcr and not gates_below:
        out.update(
            decisive=True, verdict="ready",
            reason=(f"pass-rate 95% CI lower bound {lo_pp:.1f}% is at/above the "
                    f"{target_tcr:.0f}% target and all measured gates are at their "
                    f"bar — safe to stop"),
        )
    else:
        bits = [f"pass-rate CI [{lo_pp:.1f}%, {hi_pp:.1f}%] straddles the "
                f"{target_tcr:.0f}% target"]
        if gates_below:
            bits.append(f"gates below target: {', '.join(gates_below)}")
        out["reason"] = "; ".join(bits) + " — keep sampling"
    return out


def _sample_guidance_section(
    ci: dict[str, Any], *, target_halfwidth_pp: float = 5.0,
) -> dict[str, Any] | None:
    """P28: "what to test next" — how many more tasks would tighten the TCR
    confidence interval to ``±target_halfwidth_pp``. Uses the same
    ``required_n_for_halfwidth`` the experiment blocks use, surfaced for the run
    as a whole. ``None`` when the CI is already at/below target or unmeasurable."""
    n = int(ci.get("n_tasks") or 0)
    hw = ci.get("tcr_ci_halfwidth")
    tcr_pct = ci.get("tcr_pct")
    if not n or hw is None or tcr_pct is None:
        return None
    hw_pp = round(float(hw) * 100.0, 2)
    if hw_pp <= target_halfwidth_pp:
        return {
            "n_tasks": n, "tcr_ci_halfwidth_pp": hw_pp,
            "target_halfwidth_pp": target_halfwidth_pp,
            "additional_tasks": 0,
            "message": (
                f"TCR CI is ±{hw_pp:.1f}pp on {n} tasks — already within "
                f"±{target_halfwidth_pp:.0f}pp. No more tasks needed for precision."
            ),
        }
    try:
        from agent_evaluator.utils.confidence import required_n_for_halfwidth

        rec_n = required_n_for_halfwidth(
            max(0.01, min(0.99, float(tcr_pct) / 100.0)),
            target_halfwidth_pp / 100.0,
        )
    except Exception:  # pragma: no cover - defensive
        return None
    add = max(0, rec_n - n)
    return {
        "n_tasks": n,
        "tcr_ci_halfwidth_pp": hw_pp,
        "target_halfwidth_pp": target_halfwidth_pp,
        "recommended_n": rec_n,
        "additional_tasks": add,
        "message": (
            f"TCR CI is ±{hw_pp:.1f}pp on {n} tasks; about {rec_n} tasks "
            f"(+{add}) would tighten it to ±{target_halfwidth_pp:.0f}pp."
        ),
    }


def _q_ngrams(text: Any, n: int = 4) -> set[str]:
    words = [w.lower() for w in _RE_WORD.findall(str(text or ""))]
    if len(words) < n:
        return set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _len_bucket(text: Any) -> str:
    w = len(_RE_WORD.findall(str(text or "")))
    return "short" if w <= 8 else "long" if w >= 25 else "medium"


def _capability_coverage(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """task_type × difficulty × tool-use × question-length cells, with the empty
    / thin ones named. Answers "you have 0 tasks testing hard multi-hop"."""
    dims: dict[str, dict[str, dict[str, Any]]] = {}

    def _bump(dim: str, val: str, failed: bool) -> None:
        cell = dims.setdefault(dim, {}).setdefault(val, {"n": 0, "fail_n": 0})
        cell["n"] += 1
        if failed:
            cell["fail_n"] += 1

    for t in tasks:
        failed = _effective_fail(success=t.get("success", False),
                                 accuracy=t.get("accuracy_score"),
                                 completion=t.get("completion_score"))
        _bump("task_type", str(t.get("task_type") or "—"), failed)
        ex = _task_extra(t) or {}
        if isinstance(ex.get("difficulty"), (str, int, float)):
            _bump("difficulty", str(ex["difficulty"]), failed)
        _bump("uses_tools", "yes" if t.get("tool_calls") else "no", failed)
        _bump("question_length", _len_bucket(t.get("question")), failed)

    thin = [
        {"dimension": d, "value": v, "n": c["n"], "fail_n": c["fail_n"]}
        for d, vals in dims.items() for v, c in vals.items()
        if 0 < c["n"] < 3
    ]
    return {"cells": dims, "thin_cells": sorted(thin, key=lambda x: x["n"])}


def _contamination(tasks: list[dict[str, Any]], prompt_text: str) -> list[dict[str, Any]]:
    """A task whose question / ground_truth appears near-verbatim in the system
    prompt (or few-shot block) — its score is inflated. 4-gram overlap."""
    pg = _q_ngrams(prompt_text)
    if not pg:
        return []
    out: list[dict[str, Any]] = []
    for t in tasks:
        for field in ("question", "ground_truth"):
            tg = _q_ngrams(t.get(field))
            if not tg:
                continue
            share = len(tg & pg) / len(tg)
            if share >= 0.40:
                out.append({
                    "task_id": str(t.get("task_id") or "—"),
                    "field": field,
                    "overlap_pct": round(share * 100.0, 1),
                    "snippet": str(t.get(field) or "")[:120],
                })
    return sorted(out, key=lambda x: -x["overlap_pct"])[:15]


def _targeted_additions(
    tasks: list[dict[str, Any]], hist: dict[str, int],
) -> list[dict[str, Any]]:
    """Where do failures concentrate, and is that cohort under-sampled? -> "add N
    tasks of type X"."""
    fail_by_type: Counter = Counter()
    for t in tasks:
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score")):
            fail_by_type[str(t.get("task_type") or "—")] += 1
    if not fail_by_type:
        return []
    med = sorted(hist.values())[len(hist) // 2] if hist else 0
    out: list[dict[str, Any]] = []
    for tt, fn in fail_by_type.most_common(3):
        n = hist.get(tt, 0)
        if n < max(8, med) and fn >= 2:
            out.append({
                "task_type": tt,
                "current_n": n,
                "failing_n": fn,
                "suggested_add": max(8, med) - n,
                "reason": (f"{fn} of the failures are '{tt}' but the set only has "
                           f"{n} '{tt}' task(s) — add ~{max(8, med) - n} more to "
                           f"localise the problem."),
            })
    return out


def _eval_set_quality_section(
    tasks: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
    harness_groups: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Treat the eval set as a first-class object (P12): coverage / balance /
    near-duplicates / "is this Gate even being exercised" / suspicious labels.

    A verdict computed from an unbalanced or mislabelled eval set is not
    trustworthy no matter how clean the stats are.
    """
    if not tasks:
        return None
    hist: dict[str, int] = defaultdict(int)
    for t in tasks:
        hist[str(t.get("task_type") or "—")] += 1

    # near-duplicate questions — token Jaccard >= 0.85 (small n, O(n^2) is fine)
    def _qtok(t: dict[str, Any]) -> set[str]:
        return {w.lower() for w in _RE_WORD.findall(str(t.get("question") or ""))}

    toks = [(str(t.get("task_id") or f"#{i}"), _qtok(t)) for i, t in enumerate(tasks)]
    seen: set[int] = set()
    dup_clusters: list[dict[str, Any]] = []
    for i in range(len(toks)):
        if i in seen or not toks[i][1]:
            continue
        group = [toks[i][0]]
        for j in range(i + 1, len(toks)):
            if j in seen or not toks[j][1]:
                continue
            a, b = toks[i][1], toks[j][1]
            jac = len(a & b) / len(a | b) if (a | b) else 0.0
            if jac >= 0.85:
                group.append(toks[j][0])
                seen.add(j)
        if len(group) > 1:
            seen.add(i)
            q = next((str(t.get("question") or "") for t in tasks
                      if str(t.get("task_id") or "") == group[0]), "")
            dup_clusters.append({"question": q[:120], "task_ids": group, "count": len(group)})

    # coverage cross-check — is a scored Gate actually exercised by any task?
    warnings: list[str] = []
    n_multi = sum(1 for t in tasks if t.get("agent_interactions"))
    n_tools = sum(1 for t in tasks if t.get("tool_calls"))
    if isinstance((harness_groups.get("F") or {}).get("score"), (int, float)) and n_multi == 0:
        warnings.append(
            "Gate F (Multi-Agent Coordination) is scored but no task carries "
            "agent_interactions — the score reflects defaults, not this agent."
        )
    if isinstance((harness_groups.get("G") or {}).get("score"), (int, float)) and n_tools == 0:
        warnings.append(
            "Gate G tool coverage is scored but no task carries tool_calls."
        )
    least = min(hist.values()) if hist else 0
    most = max(hist.values()) if hist else 0
    if len(hist) > 1 and least > 0 and most / least >= 5:
        warnings.append(
            f"Task-type mix is unbalanced ({dict(hist)}) — per-slice verdicts for "
            "the smallest cohorts are low-confidence."
        )
    if len(tasks) < 20:
        warnings.append(f"Only {len(tasks)} tasks — most verdicts will be LOW confidence.")

    # suspicious ground truth — needs a baseline: same task fails ~identically in
    # both runs => the label / question is the more likely culprit than the agent.
    suspicious: list[dict[str, Any]] = []
    if baseline:
        base_acc = {
            str(t.get("task_id")): _safe_float(t.get("accuracy_score"))
            for t in (baseline.get("tasks") or []) if isinstance(t, dict) and t.get("task_id")
        }
        for t in tasks:
            tid = str(t.get("task_id") or "")
            ca = _safe_float(t.get("accuracy_score"))
            ba = base_acc.get(tid)
            if ca is None or ba is None:
                continue
            if ca < 0.35 and ba < 0.35 and abs(ca - ba) < 0.05:
                gt = str(t.get("ground_truth") or "")
                hint = " (ground truth is very short)" if len(_RE_WORD.findall(gt)) < 3 else ""
                suspicious.append({
                    "task_id": tid,
                    "reason": f"fails near-identically in baseline and current "
                              f"(acc {ba:.2f} → {ca:.2f}){hint} — verify the label / question",
                })

    # P45: capability-coverage matrix, prompt contamination, targeted additions
    _prompt = ""
    try:
        _prompt = str(
            ((current or {}).get("extra_metrics") or {}).get("lineage", {})
            .get("prompt_text") or ""
        )
    except Exception:  # pragma: no cover - defensive
        _prompt = ""
    coverage = _capability_coverage(tasks)
    contamination = _contamination(tasks, _prompt)
    additions = _targeted_additions(tasks, dict(hist))
    if contamination:
        warnings.append(
            f"{len(contamination)} task(s) overlap the system prompt heavily "
            "(4-gram ≥ 40%) — those scores are inflated."
        )
    for _tc in coverage["thin_cells"][:3]:
        warnings.append(
            f"Only {_tc['n']} task(s) at {_tc['dimension']}={_tc['value']} — "
            "that cohort is effectively untested."
        )

    return {
        "n_tasks": len(tasks),
        "task_type_histogram": dict(hist),
        "near_duplicate_clusters": dup_clusters[:10],
        "coverage_warnings": warnings,
        "suspicious_ground_truth": suspicious[:10],
        "capability_coverage": coverage,
        "contamination": contamination,
        "targeted_additions": additions,
    }


def _slice_analysis_section(
    tasks: list[dict[str, Any]], baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Per-``task_type`` TCR/accuracy with CIs, and — when a baseline is given —
    the per-slice delta plus whether a two-sample bootstrap CI of the difference
    excludes 0. Answers "the 12pp TCR regression is entirely in the rag cohort;
    qa is flat (significant)". (P10)
    """
    if not tasks:
        return []

    def _by_type(ts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in ts:
            out[str(t.get("task_type") or "—")].append(t)
        return out

    cur_by = _by_type(tasks)
    base_by = _by_type(
        [t for t in (baseline.get("tasks") or []) if isinstance(t, dict)]
    ) if baseline else {}

    rows: list[dict[str, Any]] = []
    for ttype, members in sorted(cur_by.items(), key=lambda kv: -len(kv[1])):
        row = _slice_stats(members, base_by.get(ttype) or [])
        row = {"task_type": ttype, **row}
        rows.append(row)
    return rows


def _slice_stats(
    members: list[dict[str, Any]], base_members: list[dict[str, Any]],
) -> dict[str, Any]:
    """TCR/accuracy + CI for one slice, plus the vs-baseline delta + two-sample
    bootstrap significance when ``base_members`` is non-empty. Shared by
    ``_slice_analysis_section`` (by task_type) and ``_metadata_slices_section``
    (by an ``extra`` key)."""
    from agent_evaluator.utils.confidence import bootstrap_diff_ci, bootstrap_mean_ci

    comps = [
        c for c in (_safe_float(m.get("completion_score")) for m in members)
        if c is not None
    ]
    accs = [
        a for a in (_safe_float(m.get("accuracy_score")) for m in members)
        if a is not None
    ]
    row: dict[str, Any] = {"n": len(members)}
    if comps:
        row["tcr_pct"] = round(sum(comps) / len(comps) * 100.0, 2)
        lo, hi = bootstrap_mean_ci(comps)
        row["tcr_ci_pct"] = [round(lo * 100, 2), round(hi * 100, 2)]
    if accs:
        row["accuracy_pct"] = round(sum(accs) / len(accs) * 100.0, 2)
    if base_members:
        b_comps = [
            c for c in (_safe_float(m.get("completion_score")) for m in base_members)
            if c is not None
        ]
        if b_comps and comps:
            row["baseline_tcr_pct"] = round(sum(b_comps) / len(b_comps) * 100.0, 2)
            row["tcr_delta_pp"] = round(row["tcr_pct"] - row["baseline_tcr_pct"], 2)
            dci = bootstrap_diff_ci(comps, b_comps)
            if dci is not None:
                row["tcr_delta_ci_pp"] = [round(dci[0] * 100, 2), round(dci[1] * 100, 2)]
                row["significant"] = dci[0] > 0 or dci[1] < 0
    return row


def _task_extra(t: dict[str, Any]) -> dict[str, Any]:
    e = t.get("extra")
    return e if isinstance(e, dict) else {}


def _metadata_slices_section(
    tasks: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
    *,
    max_dims: int = 4,
    max_values: int = 8,
    min_coverage: float = 0.6,
) -> list[dict[str, Any]] | None:
    """P28: the same per-slice TCR/accuracy/Δ analysis as ``slice_analysis`` but
    keyed on scalar ``extra`` metadata (model, prompt_variant, difficulty, …),
    not just ``task_type``. Auto-discovers usable keys: scalar values, present on
    ≥ ``min_coverage`` of tasks, 2..``max_values`` distinct values, and not a
    1:1 restatement of ``task_type``."""
    if not tasks or len(tasks) < 4:
        return None
    n = len(tasks)
    key_values: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in tasks:
        for k, v in _task_extra(t).items():
            if isinstance(v, (str, bool, int)):   # scalar, not float/dict/list
                sv = str(v)
                if len(sv) <= 40:
                    key_values[k][sv] += 1

    candidates: list[tuple[str, int]] = []
    for k, counts in key_values.items():
        covered = sum(counts.values())
        if covered < min_coverage * n or not (2 <= len(counts) <= max_values):
            continue
        if _one_to_one(tasks, k):   # would just restate slice_analysis
            continue
        candidates.append((k, covered))

    candidates.sort(key=lambda kv: -kv[1])
    if not candidates:
        return None

    base_tasks = (
        [t for t in (baseline.get("tasks") or []) if isinstance(t, dict)]
        if baseline else []
    )
    out: list[dict[str, Any]] = []
    for key, _cov in candidates[:max_dims]:
        cur_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in tasks:
            ex = _task_extra(t)
            if key in ex:
                cur_by[str(ex[key])].append(t)
        base_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in base_tasks:
            ex = _task_extra(t)
            if key in ex:
                base_by[str(ex[key])].append(t)
        slices = []
        for val, members in sorted(cur_by.items(), key=lambda kv: -len(kv[1])):
            slices.append({"value": val, **_slice_stats(members, base_by.get(val) or [])})
        if len(slices) >= 2:
            out.append({"dimension": f"extra.{key}", "slices": slices})
    return out or None


def _one_to_one(tasks: list[dict[str, Any]], key: str) -> bool:
    """True when ``extra[key]`` and ``task_type`` partition the tasks identically
    (a bijection) — slicing by such a key would just reproduce ``slice_analysis``.
    Requires the mapping to be one-to-one in *both* directions."""
    fwd: dict[str, set] = defaultdict(set)   # key value -> task_types
    rev: dict[str, set] = defaultdict(set)   # task_type -> key values
    for t in tasks:
        ex = _task_extra(t)
        if key in ex:
            kv = str(ex[key])
            tt = str(t.get("task_type") or "—")
            fwd[kv].add(tt)
            rev[tt].add(kv)
    if len(fwd) < 2:
        return False
    return (
        all(len(v) == 1 for v in fwd.values())
        and all(len(v) == 1 for v in rev.values())
    )


def _gate_findings_section(diagnosis: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not diagnosis:
        return []
    try:
        from agent_evaluator.ontology.metric_registry import (
            component_guidance_for,
            config_hint_for,
        )
    except Exception:  # pragma: no cover - defensive
        component_guidance_for = lambda _f: None  # noqa: E731
        config_hint_for = lambda _f: None  # noqa: E731

    findings: list[dict[str, Any]] = []
    for f in diagnosis.get("findings") or []:
        gate = f.get("gate")
        shortfalls = []
        for s in f.get("component_shortfalls") or []:
            fld = s.get("field", "")
            shortfalls.append({
                "field": fld,
                "value": s.get("value"),
                "health": s.get("health"),
                "guidance": component_guidance_for(fld) or "",
                "config_hint": config_hint_for(fld),
            })
        item = {
            "gate": gate,
            "gate_name": _GATE_FULL.get(gate, gate),
            "score": f.get("current_score"),
            "baseline_score": f.get("baseline_score"),
            "component_shortfalls": shortfalls,
            "top_detail_deltas": f.get("top_detail_deltas") or [],
            "cross_references": f.get("cross_references") or [],
        }
        if gate == "F" and f.get("mast_candidates"):
            item["mast_candidates"] = f["mast_candidates"]
        findings.append(item)
    return findings


def _failure_clusters_section(
    tasks: list[dict[str, Any]], total_tasks: int,
) -> list[dict[str, Any]]:
    if not tasks or total_tasks <= 0:
        return []
    pool = [
        t for t in tasks
        if _effective_fail(
            success=t.get("success", False),
            accuracy=t.get("accuracy_score"),
            completion=t.get("completion_score"),
        )
    ]
    if not pool:
        return []
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for t in pool:
        sig = _reason_signature(_task_reason(t))
        buckets[(sig, t.get("task_type") or "—")].append(t)
    if len(buckets) < 2 and len(pool) < 3:
        return []
    ranked = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for (sig, ttype), members in ranked[:8]:
        out.append({
            "signature": sig,
            "task_type": ttype,
            "count": len(members),
            "impact_pct": round(len(members) / total_tasks * 100.0, 1),
            "example_task_ids": [
                str(m.get("task_id")) for m in members[:5] if m.get("task_id")
            ],
        })
    return out


# ---------------------------------------------------------------------------
# Semantic failure segmentation + trigger localization (P30).
# `_failure_clusters_section` groups by (reason signature x task_type) — surface
# level. This clusters the failing *questions* by lexical topic so the report can
# say "the agent fails on multi-entity comparison questions", and pins each
# failure to the retrieved passage or tool step that most likely caused it.
# Pure stdlib: binary TF-IDF + greedy cosine grouping (small N, deterministic).
# ---------------------------------------------------------------------------

_SEG_MIN_FAILURES = 4
_SEG_SIM = 0.22             # cosine >= this -> same topic segment
_SEG_MIN_MEMBERS = 2
_SEG_MAX = 6


def _tfidf_vectors(
    docs: list[tuple[str, set[str]]],
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    n = len(docs)
    df: Counter = Counter()
    for _tid, toks in docs:
        df.update(toks)
    idf = {
        term: math.log((1.0 + n) / (1.0 + c)) + 1.0
        for term, c in df.items()
        if c < n  # a term in every failing question does not discriminate
    }
    vecs: dict[str, dict[str, float]] = {}
    for tid, toks in docs:
        v = {t: idf[t] for t in toks if t in idf}
        norm = math.sqrt(sum(w * w for w in v.values())) or 1.0
        vecs[tid] = {t: w / norm for t, w in v.items()}
    return vecs, idf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def _failure_segments_section(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    fails = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    if len(fails) < _SEG_MIN_FAILURES:
        return None
    docs = [
        (str(t.get("task_id") or f"#{i}"), _wtok(t.get("question")))
        for i, t in enumerate(fails)
    ]
    docs = [(tid, toks) for tid, toks in docs if len(toks) >= 2]
    if len(docs) < _SEG_MIN_FAILURES:
        return None
    by_id = {str(t.get("task_id") or f"#{i}"): t for i, t in enumerate(fails)}
    vecs, idf = _tfidf_vectors(docs)

    # greedy grouping seeded by the most distinctive question first
    order = sorted(docs, key=lambda d: -sum(vecs[d[0]].values()))
    assigned: set[str] = set()
    groups: list[list[str]] = []
    for tid, _toks in order:
        if tid in assigned:
            continue
        grp = [tid]
        assigned.add(tid)
        for other, _ot in order:
            if other in assigned:
                continue
            if _cosine(vecs[tid], vecs[other]) >= _SEG_SIM:
                grp.append(other)
                assigned.add(other)
        groups.append(grp)

    total = len(tasks)
    n_fail = len(fails)
    segments: list[dict[str, Any]] = []
    leftovers: list[str] = []
    for grp in groups:
        if len(grp) < _SEG_MIN_MEMBERS:
            leftovers.extend(grp)
            continue
        term_mass: dict[str, float] = defaultdict(float)
        for tid in grp:
            for term, w in vecs[tid].items():
                term_mass[term] += w
        kw = [t for t, _ in sorted(term_mass.items(), key=lambda kv: -kv[1])[:5]]
        members = [by_id[tid] for tid in grp if tid in by_id]
        reasons = Counter(_reason_signature(_task_reason(m)) for m in members)
        example = min(
            (str(m.get("question") or "") for m in members if m.get("question")),
            key=len, default="",
        )
        segments.append({
            "label": " · ".join(kw[:3]) or "misc",
            "keywords": kw,
            "task_ids": grp,
            "n": len(grp),
            "share_of_failures_pct": round(len(grp) / n_fail * 100.0, 1),
            "impact_pct": round(len(grp) / total * 100.0, 1),
            "dominant_reason": reasons.most_common(1)[0][0] if reasons else "unspecified",
            "example_question": example[:160],
            "catch_all": False,
        })
    segments.sort(key=lambda s: -s["n"])
    segments = segments[:_SEG_MAX]
    # An "other" bucket is worth showing even when nothing clustered — "12
    # failures, no shared topic" is itself a finding (spread across capabilities).
    if len(leftovers) >= _SEG_MIN_MEMBERS:
        lo_members = [by_id[tid] for tid in leftovers if tid in by_id]
        by_reason = Counter(_reason_signature(_task_reason(m)) for m in lo_members)
        lo_example = min(
            (str(m.get("question") or "") for m in lo_members if m.get("question")),
            key=len, default="",
        )
        segments.append({
            "label": "other (no shared topic)",
            "keywords": [],
            "task_ids": leftovers,
            "n": len(leftovers),
            "share_of_failures_pct": round(len(leftovers) / n_fail * 100.0, 1),
            "impact_pct": round(len(leftovers) / total * 100.0, 1),
            "dominant_reason": by_reason.most_common(1)[0][0] if by_reason else "mixed",
            "example_question": lo_example[:160],
            "catch_all": True,
        })
    return segments or None


_TRIG_LIMIT = 12


def _ctx_chunks(context: Any) -> list[str]:
    if isinstance(context, list):
        return [str(c) for c in context if str(c).strip()]
    text = str(context or "")
    parts = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) >= 15]


def _failure_triggers_section(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    fails = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    fails.sort(key=lambda t: _safe_float(t.get("accuracy_score"), 1.0) or 1.0)
    out: list[dict[str, Any]] = []
    for t in fails[:_TRIG_LIMIT]:
        tid = str(t.get("task_id") or "—")
        reason = _reason_signature(_task_reason(t))
        tcs = [s for s in (t.get("tool_calls") or []) if isinstance(s, dict)]
        bad_step = next(
            ((k, s) for k, s in enumerate(tcs, 1) if s.get("success") is False), None
        )
        chunks = _ctx_chunks(t.get("context"))
        gt_tok = _wtok(t.get("ground_truth"))
        kind = detail = ""
        if chunks and gt_tok:
            best = max((_overlap(gt_tok, _wtok(c)) for c in chunks), default=0.0)
            if best < _RAG_RECALL_MISS:
                kind = "retrieval_gap"
                detail = (f"No retrieved passage covers the expected answer well "
                          f"(best ground-truth overlap {best * 100:.0f}%).")
            elif any(w in reason for w in ("ground", "context", "contradict", "hallucin")):
                resp_tok = _wtok(t.get("response"))
                misleading = max(chunks, key=lambda c: _overlap(_wtok(c), resp_tok))
                kind = "grounding"
                detail = (f"The response tracks a passage that does not answer the "
                          f"question: “{misleading[:120]}”")
        if not kind and bad_step:
            k, s = bad_step
            name = s.get("tool_name") or s.get("tool") or s.get("name") or "?"
            o = s.get("error") or s.get("output") or s.get("result") or ""
            kind = "tool_failure"
            detail = f"Step {k} ({name}) failed: {str(o)[:120]}"
        if not kind and reason.startswith("error:"):
            kind = "runtime_error"
            detail = reason
        if kind:
            out.append({"task_id": tid, "kind": kind, "detail": detail})
    return out or None


# ---------------------------------------------------------------------------
# Claim-level failure explanation (P47) — "grounding failure" is a category;
# this pins the *specific sentence* that is wrong and where it came from. Split
# the response into claims, mark each supported / contradicted / unsupported vs
# the ground truth, and trace it to a context chunk / tool output / nothing.
# Deterministic, NLI-free (token overlap + negation + number mismatch). An
# `explainer=` hook can substitute an LLM-backed version (like `narrator`).
# ---------------------------------------------------------------------------
_FE_LIMIT = 8
_FE_SUPPORTED = 0.55        # claim↔gt overlap at/above this = supported
_FE_SRC_MIN = 0.30         # claim↔chunk overlap at/above this = that chunk is the source


def _sentences(text: Any) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", str(text or "").strip())
    return [p.strip() for p in parts if len(p.strip().split()) >= 3][:12]


_NEG_RE = re.compile(
    r"\b(not|no|never|cannot|none|nothing|without|unable|n't)\b|n['’]t\b", re.I,
)


def _has_neg(text: Any) -> bool:
    return bool(_NEG_RE.search(str(text or "")))


def _nums(text: Any) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", str(text or "")))


def _claim_verdict(claim: str, gt: str) -> str:
    ct, gtt = _wtok(claim), _wtok(gt)
    if not gtt:
        return "unverifiable"
    ov = _overlap(ct, gtt)
    shared = (ct & gtt) - _RAG_STOPWORDS
    # Contradiction signals win even when the token overlap is high — "we do NOT
    # ship" vs "we ship", or "5 years" vs "2 years", share most content words.
    if shared:
        neg_flip = _has_neg(claim) != _has_neg(gt)
        num_flip = bool(_nums(claim)) and bool(_nums(gt)) and not (_nums(claim) & _nums(gt))
        if neg_flip or num_flip:
            return "contradicts_ground_truth"
    if ov >= _FE_SUPPORTED:
        return "supported"
    if shared and 0.18 <= ov < _FE_SUPPORTED:
        return "contradicts_ground_truth"
    return "unsupported"


def _claim_source(claim: str, chunks: list[str], tool_outputs: list[str]) -> str:
    ct = _wtok(claim)
    if chunks:
        best_i, best_ov = -1, 0.0
        for i, c in enumerate(chunks):
            ov = _overlap(ct, _wtok(c))
            if ov > best_ov:
                best_i, best_ov = i, ov
        if best_ov >= _FE_SRC_MIN:
            return f"context_chunk[{best_i}]"
    for o in tool_outputs:
        if _overlap(ct, _wtok(o)) >= _FE_SRC_MIN:
            return "tool_output"
    return "none — hallucinated or from reasoning"


def _failure_explanations_section(
    tasks: list[dict[str, Any]], *, explainer: Any = None,
) -> list[dict[str, Any]] | None:
    fails = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
        and str(t.get("response") or "").strip()
    ]
    fails.sort(key=lambda t: _safe_float(t.get("accuracy_score"), 1.0) or 1.0)
    out: list[dict[str, Any]] = []
    for t in fails[:_FE_LIMIT]:
        resp = str(t.get("response") or "")
        gt = str(t.get("ground_truth") or "")
        chunks = _ctx_chunks(t.get("context"))
        tool_outputs = [
            str(s.get("output") or s.get("result") or s.get("stdout") or "")
            for s in (t.get("tool_calls") or []) if isinstance(s, dict)
        ]
        tool_outputs = [o for o in tool_outputs if o.strip()]
        claims = []
        for sent in _sentences(resp):
            v = _claim_verdict(sent, gt)
            claims.append({
                "text": sent[:200],
                "verdict": v,
                "source": (_claim_source(sent, chunks, tool_outputs)
                           if v != "supported" else "ground truth"),
            })
        if not claims:
            continue
        wrong = next(
            (c for c in claims if c["verdict"] in
             ("contradicts_ground_truth", "unsupported")), None,
        )
        row = {
            "task_id": str(t.get("task_id") or "—"),
            "question": str(t.get("question") or "")[:200],
            "ground_truth": gt[:200],
            "claims": claims,
            "wrong_claim": wrong["text"] if wrong else None,
            "wrong_claim_verdict": wrong["verdict"] if wrong else None,
            "wrong_claim_source": wrong["source"] if wrong else None,
            "explained_by": "template",
        }
        if explainer is not None:
            try:
                authored = explainer({
                    "task_id": row["task_id"], "question": row["question"],
                    "response": resp[:1500], "ground_truth": gt[:600],
                    "context_chunks": [c[:400] for c in chunks[:8]],
                    "template_explanation": dict(row),
                })
                if isinstance(authored, dict) and isinstance(authored.get("claims"), list):
                    row["claims"] = authored["claims"][:20]
                    row["wrong_claim"] = authored.get("wrong_claim", row["wrong_claim"])
                    row["explained_by"] = "explainer"
            except Exception:  # pragma: no cover - explainer is user code
                pass
        out.append(row)
    return out or None


def _failure_lineage_section(
    tasks: list[dict[str, Any]], baseline: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not baseline:
        return None
    base_map: dict[str, bool] = {}
    for t in baseline.get("tasks") or []:
        if isinstance(t, dict) and t.get("task_id"):
            base_map[str(t["task_id"])] = _effective_fail(
                success=t.get("success", False),
                accuracy=t.get("accuracy_score"),
                completion=t.get("completion_score"),
            )
    if not base_map:
        return None
    cur_fail = {
        str(t.get("task_id")) for t in tasks
        if t.get("task_id") and _effective_fail(
            success=t.get("success", False),
            accuracy=t.get("accuracy_score"),
            completion=t.get("completion_score"),
        )
    }
    base_fail = {tid for tid, f in base_map.items() if f}
    base_pass = {tid for tid, f in base_map.items() if not f}
    return {
        "regressed": sorted(cur_fail & base_pass),
        "persistent": sorted(cur_fail & base_fail),
        "new": sorted(cur_fail - set(base_map)),
        "fixed": sorted(base_fail - cur_fail),
    }


# ---------------------------------------------------------------------------
# Regression -> cause linkage (P38)
#
# `failure_lineage.regressed` says WHICH tasks passed before and fail now.
# `change_attribution` says WHAT changed between the two runs (prompt / config).
# `metadata_slices` says WHERE the drop concentrated (model_variant / difficulty).
# This section joins the three — for each regressed cluster it reports the slice
# it concentrates in and the config/prompt changes whose nature plausibly
# explains that failure category. One run has exactly one change-set, so this is
# correlational ("the regression is all in the haiku-mini slice and the config
# diff changed the model"), never a temporal isolation. Labelled as such.
# ---------------------------------------------------------------------------
def _change_implicates(change_label: str, category: str) -> bool:
    c = change_label.lower()
    if "model" in c:
        return True                                  # a model swap affects everything
    if category == "grounding":
        return any(k in c for k in ("temp", "top_p", "top_k", "sample", "context",
                                    "grounded", "only from", "retriev"))
    if category == "runtime":
        return any(k in c for k in ("retry", "timeout", "tool", "concurren", "budget"))
    if category == "decomposition":
        return any(k in c for k in ("step", "numbered", "plan", "decompos", "subtask"))
    if category == "guardrail":
        return any(k in c for k in ("scope", "guard", "loop", "safety", "allow", "forbid"))
    return False


def _regression_attribution_section(
    tasks: list[dict[str, Any]],
    failure_lineage: dict[str, Any] | None,
    change_attribution: dict[str, Any] | None,
    metadata_slices: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    regressed = list((failure_lineage or {}).get("regressed") or [])
    if not regressed:
        return None
    by_id = {str(t.get("task_id")): t for t in tasks if t.get("task_id")}
    reg_tasks = [by_id[i] for i in regressed if i in by_id]
    if not reg_tasks:
        return None

    # candidate changes, as human labels
    ca = change_attribution or {}
    changes: list[str] = []
    ck = ((ca.get("config_diff") or {}).get("changed_keys") or {})
    for k, mv in (ck.items() if isinstance(ck, dict) else []):
        if isinstance(mv, dict):
            changes.append(f"config: {k} ({mv.get('from')} → {mv.get('to')})")
        else:
            changes.append(f"config: {k}")
    pd = ca.get("prompt_diff") or {}
    prompt_changed = bool(ca.get("prompt_changed"))
    if prompt_changed:
        sim = pd.get("similarity")
        changes.append(
            f"prompt reworded ({sim * 100:.0f}% similar)" if isinstance(sim, (int, float))
            else "prompt reworded"
        )
    removed_lines = [str(x).lower() for x in (pd.get("removed") or [])]

    # slice concentration lookup: {dimension: {value: tcr_delta_pp}} — only the
    # `extra` keys the metadata slicer already vetted as real dimensions.
    slice_delta: dict[str, dict[str, float]] = {}
    for dim in metadata_slices or []:
        d = dim.get("dimension", "")
        slice_delta[d] = {}
        for s in dim.get("slices") or []:
            dv = s.get("tcr_delta_pp")
            if dv is not None:
                slice_delta[d][str(s.get("value"))] = float(dv)
    vetted_keys = {d[6:] for d in slice_delta if d.startswith("extra.")}

    def _scalar_extra_keys(m: dict[str, Any]) -> set[str]:
        ex = _task_extra(m) or {}
        if vetted_keys:
            return {k for k in ex if k in vetted_keys}
        return {
            k for k, v in ex.items()
            if isinstance(v, (str, int, float, bool))
            and not (isinstance(v, str) and len(v) > 60)
        }

    clusters_out: list[dict[str, Any]] = []
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in reg_tasks:
        buckets[_reason_signature(_task_reason(t))].append(t)

    for sig, members in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        cat = _proposal_category(sig)
        n = len(members)

        # where does this cluster concentrate?
        concentration: list[dict[str, Any]] = []
        for key in {k for m in members for k in _scalar_extra_keys(m)}:
            vals = Counter(
                str((_task_extra(m) or {}).get(key)) for m in members
                if (_task_extra(m) or {}).get(key) is not None
            )
            if not vals:
                continue
            top_val, top_n = vals.most_common(1)[0]
            share = top_n / n
            if share >= 0.6 and top_n >= 2:
                dd = slice_delta.get(f"extra.{key}", {}).get(top_val)
                concentration.append({
                    "dimension": f"extra.{key}",
                    "value": top_val,
                    "share_pct": round(share * 100.0, 1),
                    "slice_tcr_delta_pp": None if dd is None else round(dd, 1),
                })
        concentration.sort(key=lambda c: (c["slice_tcr_delta_pp"] is None,
                                          c["slice_tcr_delta_pp"] or 0.0))

        implicated = [c for c in changes if _change_implicates(c, cat)]
        # a removed grounding/step line in the prompt is directly implicated
        if cat == "grounding" and any(
            any(w in ln for w in ("context", "only", "grounded", "cite"))
            for ln in removed_lines
        ):
            implicated.append("prompt: removed a grounding instruction")
        if cat == "decomposition" and any(
            any(w in ln for w in ("step", "numbered", "break")) for ln in removed_lines
        ):
            implicated.append("prompt: removed a step-decomposition instruction")

        clusters_out.append({
            "signature": sig,
            "n": n,
            "task_ids": [str(m.get("task_id")) for m in members[:10] if m.get("task_id")],
            "category": cat,
            "slice_concentration": concentration,
            "implicated_changes": sorted(set(implicated)),
        })

    # overall note
    _n = len(reg_tasks)
    _top = clusters_out[0] if clusters_out else None
    parts = [f"{_n} task(s) that passed in the baseline now fail"]
    if _top and _top["slice_concentration"]:
        c0 = _top["slice_concentration"][0]
        parts.append(
            f"the largest regressed cluster (\"{_top['signature']}\") concentrates "
            f"in {c0['dimension']}={c0['value']} ({c0['share_pct']}%"
            + (f", that slice is {c0['slice_tcr_delta_pp']:+.1f}pp vs baseline"
               if c0.get("slice_tcr_delta_pp") is not None else "") + ")"
        )
    if _top and _top["implicated_changes"]:
        parts.append("co-occurring change(s): " + "; ".join(_top["implicated_changes"]))
    note = ". ".join(parts) + ". One run has a single change-set — this is a " \
                              "correlation, not a temporal isolation."

    return {
        "n_regressed_tasks": _n,
        "clusters": clusters_out,
        "changed_config_keys": [
            k for k in (ck.keys() if isinstance(ck, dict) else [])
        ],
        "prompt_changed": prompt_changed,
        "note": note,
    }


def _recommendations_section(
    harness_groups: dict[str, Any],
    diagnosis: dict[str, Any] | None,
    *,
    recommendation_log_path: str | Path | None,
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    try:
        from agent_evaluator.ontology.metric_registry import (
            GATE_GUIDANCE,
            component_guidance_for,
            config_hint_for,
        )
    except Exception:  # pragma: no cover - defensive
        return []

    shortfalls_by_gate: dict[str, list] = {}
    if diagnosis:
        for f in diagnosis.get("findings") or []:
            shortfalls_by_gate[f.get("gate")] = f.get("component_shortfalls") or []

    past_by_gate: dict[str, list] = {}
    if recommendation_log_path is not None:
        try:
            from agent_evaluator.rca.recommendation_tracking import (
                load_recommendation_outcomes,
            )

            for k in "ABCDEFG":
                past_by_gate[k] = load_recommendation_outcomes(
                    recommendation_log_path, target_gate=k,
                ) or []
        except Exception:  # pragma: no cover - defensive
            past_by_gate = {}

    out: list[dict[str, Any]] = []
    for key in "ABCDEFG":
        gdata = harness_groups.get(key)
        st = _gate_status(gdata)
        if st not in ("fail", "warn"):
            continue
        gg = GATE_GUIDANCE.get(key)
        shortfalls = shortfalls_by_gate.get(key) or []
        ncomp = len(shortfalls)
        top = shortfalls[0] if shortfalls else {}
        top_fld = str(top.get("field", "")) if top else ""
        top_health = top.get("health") if top else None

        rec: dict[str, Any] = {
            "gate": key,
            "gate_name": _GATE_FULL.get(key, key),
            "status": st,
            "label": gg.label if gg else f"Gate {key}",
            "guidance": gg.guidance if gg else "Review configuration.",
            "shortfalls": [
                {
                    "field": s.get("field"),
                    "health": s.get("health"),
                    "guidance": component_guidance_for(s.get("field", "")) or "",
                }
                for s in shortfalls[:2]
            ],
            "code_snippet": _code_snippet(top_fld, top_health, config_hint_for),
            "experiment": _experiment(key, top_fld, top_health, ncomp),
            "past_outcomes": _past_outcomes(past_by_gate.get(key) or []),
            "baseline_verdict": _baseline_verdict(baseline, current, key),
            "derived_from": {
                "source": "gate_status" if not shortfalls else "gate_component_shortfall",
                "gate": key,
                "status": st,
                "gate_score": _safe_float((gdata or {}).get("score")),
                "shortfall_fields": [
                    s.get("field") for s in shortfalls[:2] if s.get("field")
                ],
                "from_diagnosis": bool(diagnosis),
            },
        }
        out.append(rec)
    return out


def _code_snippet(field: str, health: Any, config_hint_for: Any) -> str | None:
    if not field:
        return None
    h = config_hint_for(field)
    if not h:
        return None
    cur = ""
    if isinstance(health, (int, float)):
        cur = f"  # current: {health * 100:.0f}% health"
    return (
        f"from agent_evaluator import {h['config']}\n\n"
        f"@agent_eval(monitor, task_type=...,\n"
        f"    {h['slot']}={h['config']}({h['example']}),{cur}\n"
        f")\n"
        f"def your_agent(...): ..."
    )


def _experiment(gate: str, field: str, health: Any, n_components: int) -> dict[str, Any] | None:
    if not field or not isinstance(health, (int, float)) or n_components <= 0:
        return None
    target = 0.85
    if health >= target:
        return None
    predicted = (target - health) / max(n_components, 1)
    try:
        from agent_evaluator.utils.confidence import required_n_for_halfwidth

        need_n = required_n_for_halfwidth(0.5, max(predicted / 2.0, 0.02))
    except Exception:  # pragma: no cover - defensive
        need_n = 40
    return {
        "field": field,
        "target_health": target,
        "predicted_gate_delta": round(predicted, 3),
        "recommended_tasks": need_n,
        "command": "agent-eval abtest before.json after.json --sequential",
    }


def _past_outcomes(outs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not outs:
        return None
    conf = [o for o in outs if o.get("verdict") == "confirmed"]
    ref = [o for o in outs if o.get("verdict") == "refuted"]
    deltas = [
        float(o["gate_delta"]) for o in conf
        if isinstance(o.get("gate_delta"), (int, float))
    ]
    avg_d = round(sum(deltas) / len(deltas), 4) if deltas else None
    last = outs[-1]
    return {
        "confirmed": len(conf),
        "refuted": len(ref),
        "total": len(outs),
        "avg_delta": avg_d,
        "last_note": str(last.get("note") or last.get("recommendation_id") or "")[:120],
    }


def _baseline_verdict(
    baseline: dict[str, Any] | None, current: dict[str, Any] | None, gate: str,
) -> dict[str, Any] | None:
    if not baseline or not current:
        return None
    try:
        from agent_evaluator.rca.verify import verify_recommendation_outcome

        v = verify_recommendation_outcome(baseline, current, target_gate=gate)
    except Exception:  # pragma: no cover - defensive
        return None
    if v.get("gate_delta") is None or v.get("verdict") == "inconclusive":
        return None
    return {
        "verdict": v.get("verdict"),
        "before_score": v.get("before_score"),
        "after_score": v.get("after_score"),
        "delta": v.get("gate_delta"),
    }


# ---------------------------------------------------------------------------
# Evidence-grounded fix proposals (P36)
#
# `_recommendations_section` gives a per-Gate *component* + static guidance
# ("strengthen the response-format instructions"). This layer looks at the actual
# failing tasks in that Gate's top cluster (+ the system prompt, when the run
# recorded one) and turns the guidance into a concrete, paste-able change proposal
# with `before`/`after` text and the evidence task ids. Deterministic by default;
# `build_insights(fixer=Callable)` swaps in an LLM-authored proposal (same pattern
# as `narrator`), never auto-applied — HOTL, the proposal is a draft for a human.
# ---------------------------------------------------------------------------
_PROPOSAL_KINDS = ("prompt_edit", "config_change", "data_fix")


def _proposal_category(sig: str) -> str:
    s = (sig or "").lower()
    if s.startswith("error:") or "timeout" in s or "exceeded" in s:
        return "runtime"
    if ("not grounded" in s or "contradict" in s or "retrieved context" in s
            or "hallucin" in s or "unsupported" in s):
        return "grounding"
    if ("part of" in s or "multi-step" in s or "remaining steps" in s):
        return "decomposition"
    if ("loop" in s or "repeat" in s or "scope" in s or "unauthorized" in s
            or "injection" in s or "ignore previous" in s):
        return "guardrail"
    if ("ground_truth similarity" in s or "label" in s or "suspicious" in s):
        return "data"
    return "generic"


def _first_prompt_line(prompt_text: str, *keywords: str) -> str:
    """First line of the system prompt that mentions one of `keywords` (used as
    the `before` text for a prompt_edit proposal). Empty string when absent."""
    for ln in str(prompt_text or "").splitlines():
        low = ln.lower()
        if ln.strip() and any(k in low for k in keywords):
            return ln.strip()
    return ""


def _evidence_rows(members: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in members[:limit]:
        rows.append({
            "task_id": str(m.get("task_id") or ""),
            "question": str(m.get("question") or "")[:200],
            "response": str(m.get("response") or "")[:200],
            "reason": _task_reason(m),
        })
    return rows


def _deterministic_proposal(
    gate: str, sig: str, members: list[dict[str, Any]], prompt_text: str,
) -> dict[str, Any]:
    cat = _proposal_category(sig)
    n = len(members)
    ex = next((str(m.get("task_id")) for m in members if m.get("task_id")), "")
    ev = [str(m.get("task_id")) for m in members[:5] if m.get("task_id")]
    has_prompt = bool(str(prompt_text or "").strip())

    if cat == "grounding":
        before = _first_prompt_line(prompt_text, "context", "answer", "help", "grounded")
        add = ("Only state facts that appear in the retrieved context. If the "
               "context does not contain the answer, say you don't know rather "
               "than guessing.")
        return {
            "kind": "prompt_edit",
            "before": before or "(no grounding instruction in the system prompt)",
            "after": (before + " " + add) if before else add,
            "rationale": (f"{n} failing task(s) in Gate {gate} added claims not "
                          f"supported by the retrieved context (e.g. {ex}). A "
                          f"stricter grounding instruction + a re-ranker / higher "
                          f"top_k is the usual fix."),
            "evidence_task_ids": ev,
        }
    if cat == "runtime":
        top_err = _reason_signature(_task_reason(members[0])) if members else "error"
        return {
            "kind": "config_change",
            "before": "(no retry / fault-tolerance config on the decorator)",
            "after": ("fault_tolerance=FaultToleranceConfig(max_retries=2, "
                      "backoff_s=1.0),\n    retry=RetryConfig(retry_on_timeout=True)"),
            "rationale": (f"{n} task(s) failed with runtime errors / timeouts "
                          f"({top_err}). Bounded retries with backoff recover the "
                          f"transient ones; a lighter model or a tighter tool "
                          f"timeout fixes the rest."),
            "evidence_task_ids": ev,
        }
    if cat == "decomposition":
        before = _first_prompt_line(prompt_text, "step", "break", "numbered")
        add = ("Break the task into numbered sub-steps, complete every step, and "
               "verify each step's output before writing the final answer.")
        return {
            "kind": "prompt_edit",
            "before": before or "(no step-decomposition instruction)",
            "after": (before + " " + add) if before else add,
            "rationale": (f"{n} task(s) only partially completed a multi-step "
                          f"answer (e.g. {ex}). Add SubtaskConfig(min_subtasks=…) "
                          f"so each step is checked, and make the instruction "
                          f"explicit."),
            "evidence_task_ids": ev,
        }
    if cat == "guardrail":
        return {
            "kind": "config_change",
            "before": "(no behavioural / security guardrail config)",
            "after": ("loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),\n"
                      "    scope=ScopeConfig(forbidden_tools=[...]),\n"
                      "    tool_parameter_safety=ToolParameterSafetyConfig()"),
            "rationale": (f"{n} task(s) tripped a loop / scope / injection signal "
                          f"(e.g. {ex}). Tighten the guardrail configs and, for "
                          f"live runs, enable the LiveGuardrail plugin."),
            "evidence_task_ids": ev,
        }
    if cat == "data":
        return {
            "kind": "data_fix",
            "before": "(ground_truth / question as written in the eval set)",
            "after": f"Re-check the ground_truth and wording for: {', '.join(ev) or '—'}",
            "rationale": (f"{n} task(s) fail near-identically across runs with very "
                          f"low accuracy — this pattern points at a label / "
                          f"question problem, not the agent. Fix the eval set, "
                          f"then `agent-eval dataset promote`."),
            "evidence_task_ids": ev,
        }
    # generic
    return {
        "kind": "prompt_edit" if has_prompt else "config_change",
        "before": "(review the worst-case tasks in this cluster)",
        "after": (f"Inspect tasks {', '.join(ev) or '—'} for the shared root cause, "
                  f"then adjust the prompt or the relevant Gate {gate} config."),
        "rationale": (f"{n} task(s) share the failure signature \"{sig}\" but it "
                      f"does not map to a known fix template — needs a human look."),
        "evidence_task_ids": ev,
    }


def _validate_proposal(p: Any) -> dict[str, Any] | None:
    if not isinstance(p, dict):
        return None
    if p.get("kind") not in _PROPOSAL_KINDS:
        return None
    return {
        "kind": p["kind"],
        "before": str(p.get("before") or ""),
        "after": str(p.get("after") or ""),
        "rationale": str(p.get("rationale") or ""),
        "evidence_task_ids": [str(x) for x in (p.get("evidence_task_ids") or [])][:5],
        "authored_by": "fixer" if p.get("_from_fixer") else "template",
    }


def _attach_proposals(
    out: dict[str, Any], tasks: list[dict[str, Any]],
    current: dict[str, Any], fixer: Any = None,
) -> None:
    """Mutate ``out['recommendations']`` — add a ``proposal`` to each rec whose
    Gate has an identifiable top failure cluster."""
    recs = out.get("recommendations") or []
    if not recs:
        return
    by_id = {str(t.get("task_id")): t for t in tasks if t.get("task_id")}
    fix_plan = (out.get("readiness") or {}).get("fix_plan") or []
    fclusters = out.get("failure_clusters") or []
    prompt_text = (
        ((current.get("extra_metrics") or {}).get("lineage") or {}).get("prompt_text") or ""
    )

    def _cluster_for_gate(gate: str) -> tuple[str, list[dict[str, Any]]] | None:
        for row in fix_plan:
            if gate in (row.get("targets_gates") or []):
                ids = row.get("example_task_ids") or []
                members = [by_id[i] for i in ids if i in by_id]
                if not members:
                    sig = row.get("signature") or ""
                    members = [
                        t for t in tasks
                        if _effective_fail(
                            success=t.get("success", False),
                            accuracy=t.get("accuracy_score"),
                            completion=t.get("completion_score"),
                        ) and _reason_signature(_task_reason(t)) == sig
                    ]
                return (row.get("signature") or "", members)
        for c in fclusters:
            sig = c.get("signature") or c.get("label") or ""
            _, gates = _fix_effort_hint(sig)
            if gate in gates:
                members = [
                    t for t in tasks
                    if _effective_fail(
                        success=t.get("success", False),
                        accuracy=t.get("accuracy_score"),
                        completion=t.get("completion_score"),
                    ) and _reason_signature(_task_reason(t)) == sig
                ]
                return (sig, members)
        return None

    for rec in recs:
        gate = rec.get("gate")
        hit = _cluster_for_gate(gate)
        if not hit or not hit[1]:
            continue
        sig, members = hit
        template = _deterministic_proposal(gate, sig, members, prompt_text)
        proposal = template
        if fixer is not None:
            try:
                payload = {
                    "gate": gate,
                    "cluster_signature": sig,
                    "prompt_text": prompt_text,
                    "evidence": _evidence_rows(members),
                    "template_proposal": dict(template),
                }
                authored = fixer(payload)
                if authored is not None:
                    authored = dict(authored)
                    authored["_from_fixer"] = True
                    validated = _validate_proposal(authored)
                    if validated is not None:
                        proposal = validated
            except Exception:  # pragma: no cover - fixer is user code
                proposal = template
        if "authored_by" not in proposal:
            proposal = {**proposal, "authored_by": "template"}
        rec["proposal"] = proposal


# ---------------------------------------------------------------------------
# Review queue (P15) — the HITL triage list
#
# Every signal needed to say "a human should look at these" already exists in the
# other sections; this assembles them into one prioritized list and dedupes by
# task. `agent-eval dataset promote <result.json>` turns this list into golden
# cases (closing the failure -> regression-test loop).
# ---------------------------------------------------------------------------
_REVIEW_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _review_queue_section(
    tasks: list[dict[str, Any]],
    *,
    evaluator_trust: dict[str, Any] | None = None,
    failure_lineage: dict[str, Any] | None = None,
    eval_set_quality: dict[str, Any] | None = None,
    rag_localization: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    by_task: dict[str, dict[str, Any]] = {}

    def _add(tid: str, priority: str, reason: str) -> None:
        tid = str(tid)
        cur = by_task.get(tid)
        if cur is None:
            by_task[tid] = {"task_id": tid, "priority": priority, "reasons": [reason]}
            return
        if reason not in cur["reasons"]:
            cur["reasons"].append(reason)
        if _REVIEW_PRIORITY_ORDER[priority] < _REVIEW_PRIORITY_ORDER[cur["priority"]]:
            cur["priority"] = priority

    # 1. judge <-> heuristic disagreement (the two scorers can't both be right)
    for d in ((evaluator_trust or {}).get("judge_vs_heuristic") or {}).get("disagreements") or []:
        _add(d.get("task_id", ""), "high",
             f"LLM judge ({d.get('judge')}) and heuristic scorer ({d.get('heuristic')}) "
             f"disagree by {d.get('diff')}")

    # 2. suspicious ground truth / question (label is the likelier culprit)
    for s in (eval_set_quality or {}).get("suspicious_ground_truth") or []:
        _add(s.get("task_id", ""), "high", s.get("reason", "suspicious ground truth"))

    # 3. regressed vs baseline (passed before, fails now)
    for tid in (failure_lineage or {}).get("regressed") or []:
        _add(tid, "high", "passed in the baseline run, fails now")
    for tid in (failure_lineage or {}).get("new") or []:
        _add(tid, "medium", "new failure not present in the baseline run")

    # 4. borderline RCA classification — the coarse heuristic is least reliable here
    for tid in (rag_localization or {}).get("borderline_task_ids") or []:
        _add(tid, "medium", "RAG failure classification is borderline (heuristic uncertain)")

    # 5. borderline scores — near a pass/fail boundary, a human tie-breaks best
    for t in tasks:
        tid = str(t.get("task_id") or "")
        if not tid:
            continue
        acc = _safe_float(t.get("accuracy_score"))
        comp = _safe_float(t.get("completion_score"))
        if acc is not None and 0.55 <= acc < 0.75:
            _add(tid, "medium", f"borderline accuracy ({acc:.2f})")
        elif comp is not None and 0.35 <= comp < 0.55:
            _add(tid, "medium", f"borderline completion ({comp:.2f})")

    if not by_task:
        return None
    # within a priority band, more independent reasons = more urgent (breaks the
    # "everything is HIGH" tie so the top of the list is still meaningful)
    items = sorted(
        by_task.values(),
        key=lambda it: (_REVIEW_PRIORITY_ORDER[it["priority"]],
                        -len(it.get("reasons") or []), it["task_id"]),
    )[:25]
    return {
        "n_items": len(items),
        "by_priority": {
            "high": sum(1 for i in items if i["priority"] == "high"),
            "medium": sum(1 for i in items if i["priority"] == "medium"),
            "low": sum(1 for i in items if i["priority"] == "low"),
        },
        "items": items,
    }


# ---------------------------------------------------------------------------
# Multi-agent coordination insight (P41)
#
# Gate F scores multi-agent runs but `insights` had nothing analogous to the
# `conversation` section for them. When tasks carry `agent_interactions`, this
# breaks the run down by agent (turns / error rate / share of the work), by
# hand-off (does the receiver actually use what it was handed?), names the
# bottleneck agent, emits the communication graph, and attaches MAST failure-mode
# candidates. Deterministic, stdlib. `None` when no agent-interaction data.
# ---------------------------------------------------------------------------
def _mi_field(item: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _mi_ok(item: dict[str, Any]) -> bool:
    for k in ("success", "ok"):
        if k in item:
            return bool(item[k])
    return True


def _multiagent_section(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    inter: list[dict[str, Any]] = []
    n_tasks_with = 0
    for t in tasks:
        ai = t.get("agent_interactions")
        if isinstance(ai, list) and ai:
            rows = [x for x in ai if isinstance(x, dict)]
            if rows:
                n_tasks_with += 1
                inter.extend(rows)
    if not inter:
        return None

    def _frm(x: dict[str, Any]) -> str:
        return _mi_field(x, "from", "from_agent", "sender", "agent", "agent_id", "role")

    def _to(x: dict[str, Any]) -> str:
        return _mi_field(x, "to", "to_agent", "receiver", "recipient", "target")

    def _msg(x: dict[str, Any]) -> str:
        return _mi_field(x, "message", "content", "text", "response", "output")

    agents: set[str] = set()
    sends: Counter = Counter()
    errs: Counter = Counter()
    for x in inter:
        f, to = _frm(x), _to(x)
        if f:
            agents.add(f)
            sends[f] += 1
            if not _mi_ok(x):
                errs[f] += 1
        if to:
            agents.add(to)
    if not agents:
        return None

    total_sends = sum(sends.values()) or 1
    per_agent = [
        {
            "agent_id": a,
            "n_turns": sends.get(a, 0),
            "error_rate": round(errs.get(a, 0) / sends[a], 3) if sends.get(a) else 0.0,
            "contribution_score": round(sends.get(a, 0) / total_sends, 3),
        }
        for a in sorted(agents)
    ]

    # hand-offs + context retention: consecutive interactions where the receiver
    # of one is the sender of the next.
    handoff_ct: Counter = Counter()
    retention: dict[tuple[str, str], list[float]] = defaultdict(list)
    for i in range(len(inter) - 1):
        a_to = _to(inter[i])
        b_from = _frm(inter[i + 1])
        if a_to and b_from and a_to == b_from:
            key = (_frm(inter[i]) or "?", a_to)
            handoff_ct[key] += 1
            m1, m2 = _wtok(_msg(inter[i])), _wtok(_msg(inter[i + 1]))
            if m1 and m2:
                retention[key].append(_overlap(m1, m2))
    handoffs = [
        {
            "from": k[0], "to": k[1], "n": n,
            "context_retention_at_handoff": (
                round(sum(retention[k]) / len(retention[k]), 3)
                if retention.get(k) else None
            ),
        }
        for k, n in handoff_ct.most_common()
    ]

    # step repetition: an agent sending near-identical consecutive messages
    repeated_agents: set[str] = set()
    for i in range(len(inter) - 1):
        if _frm(inter[i]) and _frm(inter[i]) == _frm(inter[i + 1]):
            m1, m2 = _wtok(_msg(inter[i])), _wtok(_msg(inter[i + 1]))
            if m1 and m2 and _overlap(m1, m2) >= 0.8:
                repeated_agents.add(_frm(inter[i]))

    # bottleneck: highest error rate among agents with >=2 turns, else the one
    # that receives the most low-retention hand-offs.
    _cand = [pa for pa in per_agent if pa["n_turns"] >= 2]
    bottleneck = None
    if _cand:
        worst = max(_cand, key=lambda pa: (pa["error_rate"], pa["n_turns"]))
        if worst["error_rate"] > 0.0:
            bottleneck = worst["agent_id"]
    if bottleneck is None and handoffs:
        low = [h for h in handoffs
               if (h["context_retention_at_handoff"] or 1.0) < 0.3]
        if low:
            bottleneck = max(low, key=lambda h: h["n"])["to"]

    # MAST candidates (Cemri et al.) — heuristic mapping
    avg_ret = [
        h["context_retention_at_handoff"] for h in handoffs
        if h["context_retention_at_handoff"] is not None
    ]
    mast_codes: list[str] = []
    if avg_ret and sum(avg_ret) / len(avg_ret) < 0.3:
        mast_codes.append("1.4")           # Loss of Conversation History
    if repeated_agents:
        mast_codes.append("1.3")           # Step Repetition
    if any(pa["error_rate"] >= 0.34 and pa["n_turns"] >= 2 for pa in per_agent):
        mast_codes.append("1.2")           # Disobey Role Specification
    # a ping-pong hand-off cycle (A->B and B->A both frequent)
    _pairs = {(h["from"], h["to"]) for h in handoffs if h["n"] >= 2}
    if any((b, a) in _pairs for (a, b) in _pairs):
        mast_codes.append("1.5")           # Unaware of Termination Conditions

    mast_candidates: list[dict[str, Any]] = []
    try:
        from agent_evaluator.ontology.mast_taxonomy import mast_failure_mode_by_code

        for code in dict.fromkeys(mast_codes):
            m = mast_failure_mode_by_code(code)
            if m:
                mast_candidates.append({
                    "code": m.code, "name": m.name, "category": m.category,
                    "remediation": m.remediation,
                })
    except Exception:  # pragma: no cover - defensive
        mast_candidates = []

    return {
        "n_tasks_with_agent_data": n_tasks_with,
        "n_agents": len(agents),
        "per_agent": sorted(per_agent, key=lambda pa: -pa["contribution_score"]),
        "handoffs": handoffs,
        "communication_graph": [
            {"from": h["from"], "to": h["to"], "n": h["n"]} for h in handoffs
        ],
        "bottleneck_agent": bottleneck,
        "repeated_agents": sorted(repeated_agents),
        "mast_candidates": mast_candidates,
    }


# ---------------------------------------------------------------------------
# Span timeline (P25) — the P7 trajectory is a flat list. When the steps carry
# timing (start_ms/end_ms or per-step duration) this parses them into a nested
# timeline with per-span self-time and cost, so a report can show a waterfall
# and name the critical path instead of just listing steps.
# ---------------------------------------------------------------------------

def _span_name(item: dict[str, Any]) -> str:
    for k in ("name", "tool_name", "tool", "step", "action", "type", "operation"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    frm = item.get("from") or item.get("from_agent") or item.get("sender")
    to = item.get("to") or item.get("to_agent") or item.get("receiver")
    if frm or to:
        return f"{frm or '?'} → {to or '?'}"
    return "step"


def _span_num(item: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = _safe_float(item.get(k))
        if v is not None:
            return v
    return None


def _span_tokens(item: dict[str, Any]) -> int | None:
    v = item.get("tokens") or item.get("tokens_used") or item.get("total_tokens")
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict) and isinstance(v.get("total"), (int, float)):
        return int(v["total"])
    return None


def parse_span_timeline(items: list[Any]) -> dict[str, Any] | None:
    """Nested timeline from a list of step dicts. ``None`` when no step carries
    usable timing (start_ms/end_ms or a duration)."""
    steps = [s for s in (items or []) if isinstance(s, dict)]
    if not steps:
        return None

    # --- 1. absolute or relative timing --------------------------------------
    have_abs = any(
        _span_num(s, "start_ms", "start", "t_start") is not None for s in steps
    )

    def _dur_ms(s: dict[str, Any]) -> float | None:
        # explicit-millisecond keys are trusted as-is; bare `duration` /
        # `latency` are seconds by convention -> scale to ms.
        v = _span_num(s, "duration_ms", "latency_ms", "elapsed_ms", "self_ms")
        if v is not None:
            return v
        v = _span_num(s, "duration", "latency", "elapsed")
        return v * 1000.0 if v is not None else None

    durs = [_dur_ms(s) for s in steps]
    if not have_abs and not any(d is not None for d in durs):
        return None

    raw: list[dict[str, Any]] = []
    cursor = 0.0
    for i, s in enumerate(steps):
        st = _span_num(s, "start_ms", "start", "t_start")
        en = _span_num(s, "end_ms", "end", "t_end")
        d = durs[i]
        if st is None:
            st = cursor
        if en is None:
            en = st + (d if d is not None else 0.0)
        cursor = max(cursor, en)
        raw.append({
            "idx": i, "name": _span_name(s),
            "id": s.get("id") or s.get("span_id"),
            "parent": s.get("parent") or s.get("parent_id") or s.get("parent_span"),
            "start_ms": round(float(st), 1), "end_ms": round(float(en), 1),
            "tokens": _span_tokens(s),
            "cost": _span_num(s, "cost", "cost_usd"),
            "ok": s.get("success", True),
        })

    t0 = min(r["start_ms"] for r in raw)
    total_ms = round(max(r["end_ms"] for r in raw) - t0, 1)
    for r in raw:
        r["start_ms"] = round(r["start_ms"] - t0, 1)
        r["end_ms"] = round(r["end_ms"] - t0, 1)

    # --- 2. depth from id/parent (else flat) -------------------------------
    by_id = {r["id"]: r for r in raw if r["id"] is not None}
    for r in raw:
        depth, p, guard = 0, r["parent"], 0
        while p is not None and p in by_id and guard < 20:
            depth += 1
            p = by_id[p]["parent"]
            guard += 1
        r["depth"] = depth

    # --- 3. self-time (interval minus child intervals) --------------------
    children: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in raw:
        if r["parent"] in by_id:
            children[r["parent"]].append(r)
    for r in raw:
        span = r["end_ms"] - r["start_ms"]
        covered = sum(c["end_ms"] - c["start_ms"] for c in children.get(r["id"], []))
        r["self_ms"] = round(max(0.0, span - covered), 1)

    spans = [
        {"idx": r["idx"], "name": r["name"], "depth": r["depth"],
         "start_ms": r["start_ms"], "end_ms": r["end_ms"], "self_ms": r["self_ms"],
         "tokens": r["tokens"], "cost": r["cost"], "ok": bool(r["ok"])}
        for r in raw
    ]

    ranked = sorted(spans, key=lambda s: -s["self_ms"])
    crit, acc = [], 0.0
    for s in ranked:
        crit.append(s["name"])
        acc += s["self_ms"]
        if total_ms and acc >= 0.8 * total_ms:
            break
    costs = [s["cost"] for s in spans if isinstance(s["cost"], (int, float))]
    toks = [s["tokens"] for s in spans if isinstance(s["tokens"], (int, float))]
    return {
        "n_spans": len(spans),
        "total_ms": total_ms,
        "spans": spans,
        "critical_path": crit,
        "bottleneck": ({"name": ranked[0]["name"], "self_ms": ranked[0]["self_ms"]}
                       if ranked else None),
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "total_tokens": sum(toks) if toks else None,
    }


def _trajectories_section(
    tasks: list[dict[str, Any]], *, limit: int = 8,
) -> list[dict[str, Any]] | None:
    failing = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ] or tasks
    out: list[dict[str, Any]] = []
    for t in failing:
        for key in ("tool_calls", "chain_steps", "agent_interactions"):
            tl = _safe(parse_span_timeline, t.get(key) or [], default=None)
            if tl:
                out.append({
                    "task_id": str(t.get("task_id") or "—"),
                    "source": key, **{
                        k: tl[k] for k in
                        ("n_spans", "total_ms", "critical_path", "bottleneck",
                         "total_cost_usd", "total_tokens")
                    },
                })
                break
        if len(out) >= limit:
            break
    return out or None


# ---------------------------------------------------------------------------
# Conversation / multi-turn (P24) — `insights` had zero coverage for a whole
# product category. Session-level scores were in the JSON; this adds the
# per-turn quality trajectory, the turn where the agent starts to degrade, and
# Coarse text heuristics, stdlib only.
# ---------------------------------------------------------------------------
_CONV_NONANSWER_MIN_CHARS = 15
_CONV_NONANSWER_PHRASES = (
    "i can't", "i cannot", "i can not", "not able to", "unable to",
    "could you clarify", "please clarify", "i don't have", "i do not have",
    "i'm not sure", "i am not sure", "contact support", "contact our support",
    "i don't know", "i do not know", "cannot help with", "can't help with",
    "not something i can", "reach out to",
)


def _is_nonanswer(agent_text: str) -> bool:
    """A turn where the agent effectively didn't answer — very short, or a
    deflection phrase. Used to find where a multi-turn agent gives up."""
    t = str(agent_text or "").strip().lower()
    if len(t) < _CONV_NONANSWER_MIN_CHARS:
        return True
    return any(p in t for p in _CONV_NONANSWER_PHRASES)


def _conversation_section(current: dict[str, Any]) -> dict[str, Any] | None:
    sessions = (current or {}).get("conversation_sessions") or []
    sessions = [s for s in sessions if isinstance(s, dict) and s.get("turns")]
    if not sessions:
        return None

    overalls, ctx_rets = [], []
    per_turn: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"ctx": [], "len": [], "rep": [], "nonans": []}
    )
    worst = None
    per_session: list[dict[str, Any]] = []

    for s in sessions:
        turns = [t for t in s["turns"] if isinstance(t, dict)]
        m = s.get("metrics") or {}
        ov = _safe_float(m.get("overall_score"))
        if ov is not None:
            overalls.append(ov)
            if worst is None or ov < worst[1]:
                worst = (s.get("session_id"), ov)
        cr = _safe_float(m.get("context_retention"))
        if cr is not None:
            ctx_rets.append(cr)
        # P35: per-session summary so the reader can see one session is fine and
        # another isn't, instead of only the average (ConversationMetrics runs
        # pessimistic on short Q&A).
        _na = sum(1 for t in turns if _is_nonanswer(str(t.get("agent") or "")))
        _tc = _safe_float(m.get("topic_coherence"))
        per_session.append({
            "session_id": s.get("session_id"),
            "turns": len(turns),
            "overall_score": None if ov is None else round(ov, 3),
            "context_retention": None if cr is None else round(cr, 3),
            "topic_coherence": None if _tc is None else round(_tc, 3),
            "nonanswer_turns": _na,
        })

        prior_tokens: set[str] = set()
        prev_agent = ""
        for t in turns:
            i = t.get("turn_index", 0)
            agent = str(t.get("agent") or "")
            user = str(t.get("user") or "")
            a_tok = _wtok(agent)
            ref = _overlap(a_tok, prior_tokens) if prior_tokens else 1.0
            rep = _overlap(a_tok, _wtok(prev_agent)) if prev_agent else 0.0
            per_turn[i]["ctx"].append(ref)
            per_turn[i]["len"].append(float(len(agent)))
            per_turn[i]["rep"].append(rep)
            per_turn[i]["nonans"].append(1.0 if _is_nonanswer(agent) else 0.0)
            prior_tokens |= _wtok(user) | a_tok
            prev_agent = agent

        # P35: a lexical "goal drift" flag (last user turn shares no content words
        # with the earlier turns) can't tell a distinct follow-up ("how long
        # until the money arrives?") from a real topic change — it false-positives
        # on healthy multi-turn Q&A. `degradation_after_turn` + the per-turn
        # trajectory already surface a session that goes bad; goal-drift is
        # dropped rather than shipped unreliable.

    traj = []
    for i in sorted(per_turn):
        d = per_turn[i]
        traj.append({
            "turn": i + 1,
            "n": len(d["ctx"]),
            "context_ref": round(sum(d["ctx"]) / len(d["ctx"]), 3) if d["ctx"] else None,
            "avg_response_chars": round(sum(d["len"]) / len(d["len"])) if d["len"] else None,
            "repetition": round(sum(d["rep"]) / len(d["rep"]), 3) if d["rep"] else None,
            "nonanswer_rate": round(sum(d["nonans"]) / len(d["nonans"]), 3) if d["nonans"] else None,
        })

    # degradation: the first turn from which the agent mostly stops answering
    # (short / deflecting responses) and never recovers. This keys off actual
    # non-answers, not token reuse — a healthy follow-up naturally introduces new
    # tokens and must not be flagged.
    degradation_after = None
    if len(traj) >= 3:
        na = [x["nonanswer_rate"] or 0.0 for x in traj]
        for k in range(1, len(na)):
            if na[k] >= 0.5 and all(v >= 0.5 for v in na[k:]) and any(v < 0.5 for v in na[:k]):
                degradation_after = traj[k]["turn"] - 1
                break

    best = None
    for ps in per_session:
        if ps["overall_score"] is not None and (best is None or ps["overall_score"] > best[1]):
            best = (ps["session_id"], ps["overall_score"])

    return {
        "n_sessions": len(sessions),
        "avg_overall_score": round(sum(overalls) / len(overalls), 3) if overalls else None,
        "avg_context_retention": round(sum(ctx_rets) / len(ctx_rets), 3) if ctx_rets else None,
        "sessions": sorted(per_session, key=lambda p: (p["overall_score"] is None,
                                                       p["overall_score"] or 0.0)),
        "turn_quality_trajectory": traj,
        "degradation_after_turn": degradation_after,
        "best_session": ({"session_id": best[0], "overall_score": best[1]} if best else None),
        "worst_session": ({"session_id": worst[0], "overall_score": round(worst[1], 3)}
                          if worst else None),
    }


# ---------------------------------------------------------------------------
# Cohort comparison (P22) — the report / insights only ever compared one result
# to one optional baseline. World-class tooling puts 3+ versions side by side,
# per task_type, with multiple-comparison-safe significance and a "pick the
# winner" call. Reuses quick_eval._benjamini_hochberg + utils.confidence.
# ---------------------------------------------------------------------------

def _version_label(report: dict[str, Any] | None, fallback: str) -> str:
    lin = _lineage(report)
    for k in ("agent_version", "prompt_version"):
        v = lin.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def _per_task_metric(report: dict[str, Any] | None, metric: str) -> list[float]:
    key = "completion_score" if metric == "tcr" else "accuracy_score"
    out = []
    for t in ((report or {}).get("tasks") or []):
        if isinstance(t, dict):
            v = _safe_float(t.get(key))
            if v is not None:
                out.append(v)
    return out


def _by_type_metric(report: dict[str, Any] | None, metric: str) -> dict[str, list[float]]:
    key = "completion_score" if metric == "tcr" else "accuracy_score"
    out: dict[str, list[float]] = defaultdict(list)
    for t in ((report or {}).get("tasks") or []):
        if isinstance(t, dict):
            v = _safe_float(t.get(key))
            if v is not None:
                out[str(t.get("task_type") or "—")].append(v)
    return out


def _labelled_cohort(
    current: dict[str, Any], cohort: list[dict[str, Any]] | None,
) -> list[tuple[str, dict[str, Any]]]:
    """[(label, report), …] for [current] + cohort — de-dupes labels."""
    out: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()
    reps: list[dict[str, Any]] = [current, *(cohort or [])]
    for idx, rep in enumerate(reps):
        base = _version_label(rep, "current" if idx == 0 else f"v{idx + 1}")
        lbl, n = base, 2
        while lbl in used:
            lbl = f"{base}#{n}"
            n += 1
        used.add(lbl)
        out.append((lbl, rep))
    return out


def _cohort_comparison_section(
    labelled: list[tuple[str, dict[str, Any]]],
    metric: str = "tcr",
) -> dict[str, Any] | None:
    """``labelled`` = [(label, result_dict), …] with >= 2 entries."""
    if len(labelled) < 2:
        return None
    try:
        from agent_evaluator.quick_eval import _benjamini_hochberg
        from agent_evaluator.utils.confidence import bootstrap_diff_ci, welch_t_p
    except Exception:  # pragma: no cover - defensive
        return None

    versions: list[dict[str, Any]] = []
    arrays: dict[str, list[float]] = {}
    by_type: dict[str, dict[str, list[float]]] = {}
    for label, rep in labelled:
        hg = _harness_groups(rep)
        vals = _per_task_metric(rep, metric)
        arrays[label] = vals
        by_type[label] = _by_type_metric(rep, metric)
        versions.append({
            "label": label,
            "n_tasks": len([t for t in (rep.get("tasks") or []) if isinstance(t, dict)]),
            "tcr_pct": round(sum(vals) / len(vals) * 100.0, 2) if vals else None,
            "gate_scores": {
                g: (hg.get(g) or {}).get("score") for g in "ABCDEFG"
                if isinstance((hg.get(g) or {}).get("score"), (int, float))
            },
            "overall": (hg.get("overall") or {}).get("score"),
        })

    # pairwise (all unordered pairs), FDR-adjusted
    pairs = [(i, j) for i in range(len(labelled)) for j in range(i + 1, len(labelled))]
    raw_p: list[float | None] = []
    pw: list[dict[str, Any]] = []
    for i, j in pairs:
        la, lb = labelled[i][0], labelled[j][0]
        a, b = arrays[la], arrays[lb]
        p = welch_t_p(a, b)
        raw_p.append(p)
        ma = (sum(a) / len(a)) if a else 0.0
        mb = (sum(b) / len(b)) if b else 0.0
        dci = bootstrap_diff_ci(a, b)
        pw.append({
            "a": la, "b": lb,
            "delta_pp": round((ma - mb) * 100.0, 2),
            "p_value": round(p, 5) if p is not None else None,
            "ci_pp": [round(dci[0] * 100, 1), round(dci[1] * 100, 1)] if dci else None,
        })
    adj = _benjamini_hochberg(raw_p)
    for entry, q in zip(pw, adj):
        entry["p_value_fdr"] = round(q, 5) if q is not None else None
        entry["significant_fdr"] = (q is not None and q < 0.05)

    # per-task_type winner
    all_types = sorted({tt for bt in by_type.values() for tt in bt})
    by_task_type = []
    for tt in all_types:
        scores = {
            lbl: (round(sum(bt[tt]) / len(bt[tt]) * 100.0, 1) if bt.get(tt) else None)
            for lbl, bt in by_type.items()
        }
        ranked = [(k, v) for k, v in scores.items() if v is not None]
        winner = max(ranked, key=lambda kv: kv[1])[0] if ranked else None
        by_task_type.append({"task_type": tt, "winner": winner, "scores": scores})

    # overall winner: highest TCR whose lead over the runner-up is FDR-significant
    ranked = sorted(
        [(v["label"], v["tcr_pct"]) for v in versions if v["tcr_pct"] is not None],
        key=lambda kv: -kv[1],
    )
    winner = None
    if len(ranked) >= 2:
        top, second = ranked[0], ranked[1]
        sig = any(
            e["significant_fdr"] and {e["a"], e["b"]} == {top[0], second[0]}
            for e in pw
        )
        if sig:
            winner = {"label": top[0],
                      "reason": f"highest {metric.upper()} ({top[1]:.1f}%) and the lead "
                                f"over {second[0]} is significant after FDR correction"}
        else:
            winner = {"label": None,
                      "reason": f"{top[0]} has the highest {metric.upper()} but its lead "
                                f"over {second[0]} is not significant — collect more tasks"}

    return {
        "metric": metric,
        "n_versions": len(labelled),
        "versions": versions,
        "pairwise": pw,
        "by_task_type": by_task_type,
        "winner": winner,
    }


# ---------------------------------------------------------------------------
# Trace-level cross-version diff (P32) — cohort_comparison is aggregate. For a
# task that appears in >=2 cohort versions and whose outcome/score moved, this
# diffs the response text and the trajectory step sequence so the reader sees
# *what actually changed* for that task, not just that the average moved.
# ---------------------------------------------------------------------------

_TD_ACC_DELTA = 0.15
_TD_COMP_DELTA = 0.20
_TD_LIMIT = 8


def _trace_step_names(t: dict[str, Any]) -> list[str]:
    for key in ("tool_calls", "chain_steps", "agent_interactions"):
        steps = [s for s in (t.get(key) or []) if isinstance(s, dict)]
        if not steps:
            continue
        names = []
        for s in steps:
            nm = (s.get("tool_name") or s.get("tool") or s.get("name")
                  or s.get("step") or s.get("action") or s.get("type"))
            if not nm and (s.get("from") or s.get("to")):
                nm = f"{s.get('from', '?')}→{s.get('to', '?')}"
            names.append(str(nm or "step"))
        return names
    return []


def _word_runs(
    sm: difflib.SequenceMatcher, side: str, words: list[str], *, cap: int = 6,
) -> list[str]:
    tag = "delete" if side == "a" else "insert"
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == tag or (op == "replace" and side == "b"):
            run = words[j1:j2] if side == "b" else words[i1:i2]
            if run:
                out.append(" ".join(run)[:80])
        elif op == "replace" and side == "a":
            run = words[i1:i2]
            if run:
                out.append(" ".join(run)[:80])
    return out[:cap]


def _trace_diffs_section(
    current: dict[str, Any], cohort: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    labelled = _labelled_cohort(current, cohort)
    if len(labelled) < 2:
        return None
    cur_label, cur_rep = labelled[0]
    priors = labelled[1:]

    def _index(rep: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(t.get("task_id")): t
            for t in (rep.get("tasks") or [])
            if isinstance(t, dict) and t.get("task_id")
        }

    cur_idx = _index(cur_rep)
    prior_idxs = [(lbl, _index(rep)) for lbl, rep in priors]
    if not cur_idx or not any(idx for _lbl, idx in prior_idxs):
        return None

    def _ok(t: dict[str, Any]) -> bool:
        return not _effective_fail(
            success=t.get("success", False), accuracy=t.get("accuracy_score"),
            completion=t.get("completion_score"),
        )

    out: list[dict[str, Any]] = []
    for tid, ct in cur_idx.items():
        hits = [(lbl, idx[tid]) for lbl, idx in prior_idxs if tid in idx]
        if not hits:
            continue
        # P35: diff against the *nearest* prior version (last cohort entry),
        # not the oldest — "what changed" means the most recent step.
        prior_lbl, pt = hits[-1]
        c_acc = _safe_float(ct.get("accuracy_score"), 0.0) or 0.0
        p_acc = _safe_float(pt.get("accuracy_score"), 0.0) or 0.0
        c_comp = _safe_float(ct.get("completion_score"), 0.0) or 0.0
        p_comp = _safe_float(pt.get("completion_score"), 0.0) or 0.0
        acc_d, comp_d = c_acc - p_acc, c_comp - p_comp
        c_ok, p_ok = _ok(ct), _ok(pt)
        if not (c_ok != p_ok or abs(acc_d) >= _TD_ACC_DELTA or abs(comp_d) >= _TD_COMP_DELTA):
            continue

        rp = str(pt.get("response") or "")
        rc = str(ct.get("response") or "")
        w_p, w_c = rp.split(), rc.split()
        sm = difflib.SequenceMatcher(None, w_p, w_c)
        # A regressed version that returned nothing (timeout / runtime error) — a bare
        # "removed: <old answer>" word-diff is misleading; flag it so the renderer can
        # say "no response" instead.
        _cur_reason = _task_reason(ct)
        _cur_errored = (not rc.strip()) and (
            bool(ct.get("errors")) or str(_cur_reason).lower().startswith("error:")
        )

        steps_p, steps_c = _trace_step_names(pt), _trace_step_names(ct)
        traj = {
            "before": steps_p[:12],
            "after": steps_c[:12],
            "added": [s for s in steps_c if s not in steps_p][:8],
            "removed": [s for s in steps_p if s not in steps_c][:8],
            "reordered": bool(
                steps_p and steps_c and steps_p != steps_c
                and sorted(steps_p) == sorted(steps_c)
            ),
        }
        if c_ok and not p_ok:
            verdict = "fixed"
        elif p_ok and not c_ok:
            verdict = "regressed"
        elif acc_d > 0:
            verdict = "improved"
        elif acc_d < 0:
            verdict = "declined"
        else:
            verdict = "changed"

        per_version = []
        for lbl, idx in [(cur_label, cur_idx)] + prior_idxs:
            if tid in idx:
                vt = idx[tid]
                per_version.append({
                    "label": lbl,
                    "completion": _safe_float(vt.get("completion_score")),
                    "accuracy": _safe_float(vt.get("accuracy_score")),
                    "success": bool(vt.get("success", False)),
                    "response_excerpt": str(vt.get("response") or "")[:160],
                })

        out.append({
            "task_id": tid,
            "question": str(ct.get("question") or "")[:160],
            "compared": [prior_lbl, cur_label],
            "verdict": verdict,
            "score_delta": {"completion": round(comp_d, 3), "accuracy": round(acc_d, 3)},
            "response_diff": {
                "similarity": round(sm.ratio(), 3),
                "added": _word_runs(sm, "b", w_c),
                "removed": _word_runs(sm, "a", w_p),
                "errored": _cur_errored,
                "error_reason": str(_cur_reason) if _cur_errored else None,
            },
            "trajectory_diff": traj,
            "per_version": per_version,
        })

    out.sort(key=lambda d: (
        0 if d["verdict"] == "regressed" else 1,
        -abs(d["score_delta"]["accuracy"]),
    ))
    return out[:_TD_LIMIT] or None


# ---------------------------------------------------------------------------
# Insight meta-diff + staleness (P33). change_attribution diffs prompts/config/
# metrics. This diffs the *insights* themselves ("a new failure cluster
# appeared", "judge trust dropped", "a new CWE finding") and flags when the
# baseline / eval set is stale enough that the comparison is shaky.
# ---------------------------------------------------------------------------

def _report_timestamp(report: dict[str, Any] | None) -> Any:
    if not report:
        return None
    for k in ("timestamp", "created_at", "generated_at"):
        v = report.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    lin = _lineage(report)
    for k in ("timestamp", "created_at"):
        v = lin.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _days_between(a: Any, b: Any) -> int | None:
    from datetime import datetime

    def _parse(s: Any) -> Any:
        if not isinstance(s, str):
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    # one side may be tz-aware and the other naive — compare on the wall clock.
    da = da.replace(tzinfo=None)
    db = db.replace(tzinfo=None)
    return abs((da - db).days)


def _question_fingerprint(report: dict[str, Any] | None) -> frozenset:
    return frozenset(
        str(t.get("question") or "").strip().lower()
        for t in ((report or {}).get("tasks") or [])
        if isinstance(t, dict) and str(t.get("question") or "").strip()
    )


# ---------------------------------------------------------------------------
# Longitudinal intelligence (P48) — history.py gives per-gate sparklines;
# insight_changes diffs current vs ONE baseline. This reads *all* sibling result
# JSONs and answers "which failure keeps coming back (flapping)", "how much can
# run-to-run TCR move on an unchanged eval set (the noise floor)", and "how
# often are we even running this". Needs >= 4 usable sibling runs.
# ---------------------------------------------------------------------------
_LONG_MIN_RUNS = 4
_LONG_MAX_RUNS = 20


def _longitudinal_section(
    history_dir: str | Path | None, current_file: str | Path | None = None,
) -> dict[str, Any] | None:
    if not history_dir:
        return None
    d = Path(history_dir)
    if not d.is_dir():
        return None
    excl = Path(current_file).resolve() if current_file else None
    runs: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        if p.name in ("baseline.json",) or (excl and p.resolve() == excl):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or not (data.get("tasks")):
            continue
        tasks = [t for t in data["tasks"] if isinstance(t, dict)]
        if not tasks:
            continue
        comps = [_safe_float(t.get("completion_score")) for t in tasks]
        comps = [c for c in comps if c is not None]
        runs.append({
            "file": p.name,
            "timestamp": data.get("timestamp") or "",
            "tcr": (sum(comps) / len(comps) * 100.0) if comps else None,
            "fail_sigs": {
                _reason_signature(_task_reason(t)) for t in tasks
                if _effective_fail(success=t.get("success", False),
                                   accuracy=t.get("accuracy_score"),
                                   completion=t.get("completion_score"))
            },
            "fingerprint": _question_fingerprint(data),
        })
    runs.sort(key=lambda r: (str(r["timestamp"]), r["file"]))
    runs = runs[-_LONG_MAX_RUNS:]
    if len(runs) < _LONG_MIN_RUNS:
        return None

    # recurring / flapping failure signatures
    recurring: list[dict[str, Any]] = []
    all_sigs = {s for r in runs for s in r["fail_sigs"] if s and s != "unspecified"}
    for sig in sorted(all_sigs):
        present = [sig in r["fail_sigs"] for r in runs]
        n_runs = sum(present)
        if n_runs < 3:
            continue
        transitions = sum(1 for a, b in zip(present, present[1:]) if a != b)
        chronic = n_runs == len(runs)
        recurring.append({
            "signature": sig,
            "in_n_runs": n_runs,
            "of_runs": len(runs),
            "flap_transitions": transitions,
            "currently_failing": present[-1],
            "kind": "chronic" if chronic else ("flapping" if transitions >= 2
                                               else "recurring"),
            "note": (f"fails in every one of the last {n_runs} runs"
                     if chronic else
                     f"recurs in {n_runs}/{len(runs)} runs"
                     + (f", flapped {transitions}×" if transitions >= 2 else "")),
        })
    # most chronic first, then most unstable, then most frequent
    recurring.sort(key=lambda x: (-x["in_n_runs"], -x["flap_transitions"]))

    # eval-set stability — TCR spread across runs with the SAME question set
    stability = None
    fp_groups: dict[frozenset, list[float]] = defaultdict(list)
    for r in runs:
        if r["fingerprint"] and r["tcr"] is not None:
            fp_groups[r["fingerprint"]].append(r["tcr"])
    same = max(fp_groups.values(), key=len, default=[])
    if len(same) >= 3:
        m = sum(same) / len(same)
        sd = (sum((x - m) ** 2 for x in same) / len(same)) ** 0.5
        stability = {
            "n_runs_same_eval_set": len(same),
            "tcr_mean_pct": round(m, 1),
            "tcr_stdev_pp": round(sd, 2),
            "detectable_change_pp": round(2.0 * sd, 1),
            "note": (f"On the unchanged eval set, TCR has moved ±{sd:.1f}pp "
                     f"run-to-run — a real change smaller than ~{2 * sd:.1f}pp "
                     f"can't be told from noise."),
        }

    # cadence
    gaps = [
        _days_between(runs[i]["timestamp"], runs[i - 1]["timestamp"])
        for i in range(1, len(runs))
    ]
    gaps = [g for g in gaps if g is not None]
    cadence = None
    if gaps:
        cadence = {
            "n_intervals": len(gaps),
            "median_days_between_runs": sorted(gaps)[len(gaps) // 2],
            "last_gap_days": gaps[-1],
        }

    return {
        "n_runs": len(runs),
        "run_files": [r["file"] for r in runs],
        "recurring_failures": recurring[:10],
        "eval_set_stability": stability,
        "cadence": cadence,
    }


def _insight_changes_section(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    security_findings: list[dict[str, Any]] | None,
    evaluator_trust: dict[str, Any] | None,
    harness_groups: dict[str, Any],
) -> dict[str, Any] | None:
    if not baseline:
        return None
    base_tasks = [t for t in (baseline.get("tasks") or []) if isinstance(t, dict)]
    cur_tasks = [t for t in (current.get("tasks") or []) if isinstance(t, dict)]
    base_hg = _harness_groups(baseline)

    # P35: compare the *full* set of failure signatures over every failing task,
    # not the truncated top-8 failure_clusters list — a cluster that merely drops
    # in rank was reading as "resolved".
    def _fail_sigs(tasks: list[dict[str, Any]]) -> set[str]:
        return {
            _reason_signature(_task_reason(t))
            for t in tasks
            if _effective_fail(success=t.get("success", False),
                               accuracy=t.get("accuracy_score"),
                               completion=t.get("completion_score"))
        }

    cur_sigs = _fail_sigs(cur_tasks)
    base_sigs = _fail_sigs(base_tasks)
    new_clusters = sorted(s for s in cur_sigs - base_sigs if s and s != "unspecified")
    resolved_clusters = sorted(s for s in base_sigs - cur_sigs if s and s != "unspecified")

    b_trust = _safe(_evaluator_trust_section, base_tasks, baseline, default=None) or {}
    trust_change = None
    ct, bt = (evaluator_trust or {}).get("trust_level"), b_trust.get("trust_level")
    if ct and bt and ct != bt:
        trust_change = {"from": bt, "to": ct}

    b_sec = _safe(_security_findings_section, baseline, default=None) or []
    base_sec_keys = {(s.get("task_id"), s.get("threat_type")) for s in b_sec}
    new_security_findings = [
        {"task_id": s.get("task_id"), "threat_type": s.get("threat_type"),
         "severity": s.get("severity")}
        for s in (security_findings or [])
        if (s.get("task_id"), s.get("threat_type")) not in base_sec_keys
    ]

    def _lvl(hg: dict[str, Any]) -> str:
        v = _safe(
            _verdict_section, hg, None, {"n_tasks": 0}, 0, default={},
        )
        return (v or {}).get("level", "unknown")

    cur_lvl, base_lvl = _lvl(harness_groups), _lvl(base_hg)
    verdict_change = {"from": base_lvl, "to": cur_lvl} if cur_lvl != base_lvl else None

    # "below target" = the report's fail-OR-warn framing (score < 0.7), not just the
    # hard-fail line (< 0.5) — otherwise a gate sliding from pass to warn is silent.
    _below = {"fail", "warn"}
    cur_fail = {k for k in "ABCDEFG" if _gate_status(harness_groups.get(k)) in _below}
    base_fail = {k for k in "ABCDEFG" if _gate_status(base_hg.get(k)) in _below}
    newly_failing_gates = sorted(cur_fail - base_fail)
    newly_passing_gates = sorted(base_fail - cur_fail)

    if not any([new_clusters, resolved_clusters, trust_change, new_security_findings,
                verdict_change, newly_failing_gates, newly_passing_gates]):
        return None
    return {
        "new_clusters": new_clusters,
        "resolved_clusters": resolved_clusters,
        "trust_change": trust_change,
        "new_security_findings": new_security_findings,
        "verdict_change": verdict_change,
        "newly_failing_gates": newly_failing_gates,
        "newly_passing_gates": newly_passing_gates,
    }


_FRESH_BASELINE_MAX_DAYS = 30
_FRESH_MIN_TASKS = 20


def _freshness_section(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    eval_set_quality: dict[str, Any] | None,
    failure_clusters: list[dict[str, Any]] | None,
    failure_segments: list[dict[str, Any]] | None,
    ci: dict[str, Any],
) -> dict[str, Any] | None:
    warnings: list[str] = []
    baseline_age_days = None
    eval_set_identical = None

    if baseline:
        baseline_age_days = _days_between(
            _report_timestamp(current), _report_timestamp(baseline)
        )
        if baseline_age_days is not None and baseline_age_days > _FRESH_BASELINE_MAX_DAYS:
            warnings.append(
                f"The baseline run is {baseline_age_days} days old — the "
                f"regression comparison may be stale; re-baseline against a "
                f"recent run."
            )
        cur_fp = _question_fingerprint(current)
        base_fp = _question_fingerprint(baseline)
        if cur_fp and base_fp:
            eval_set_identical = cur_fp == base_fp
            if eval_set_identical and (failure_clusters or failure_segments):
                warnings.append(
                    "The eval set has not changed since the baseline, yet new "
                    "failure modes are present — add cases that cover them so "
                    "the next run can track them."
                )

    sgt = (eval_set_quality or {}).get("suspicious_ground_truth") or []
    if sgt:
        warnings.append(
            f"{len(sgt)} eval case(s) look mislabelled (they fail near-identically "
            f"in both runs) — refresh their ground truth before trusting the scores."
        )
    n_tasks = int((ci or {}).get("n_tasks") or 0)
    if 0 < n_tasks < _FRESH_MIN_TASKS:
        warnings.append(
            f"Only {n_tasks} task(s) in the eval set — widen it toward "
            f"{_FRESH_MIN_TASKS}+ for a stable verdict."
        )

    if baseline_age_days is None and eval_set_identical is None and not warnings:
        return None
    return {
        "baseline_age_days": baseline_age_days,
        "eval_set_identical_to_baseline": eval_set_identical,
        "n_tasks": n_tasks,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Change attribution (P18) — tie a metric move to the specific thing that
# changed. experiment_metadata already gives the git file/commit diff; this adds
# the system-prompt / config text diff (when the run stashed it in lineage) and
# points at the largest Gate move between the two runs.
# ---------------------------------------------------------------------------

def _lineage(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    return (report.get("extra_metrics") or {}).get("lineage") or {}


def _prompt_line_diff(old: str, new: str) -> dict[str, Any]:
    import difflib

    a = (old or "").splitlines()
    b = (new or "").splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    added = [ln for i, ln in enumerate(b) if i in _changed_indices(sm, "b")]
    removed = [ln for i, ln in enumerate(a) if i in _changed_indices(sm, "a")]
    return {
        "similarity": round(sm.ratio(), 3),
        "added": [ln.strip() for ln in added if ln.strip()][:15],
        "removed": [ln.strip() for ln in removed if ln.strip()][:15],
    }


def _changed_indices(sm: Any, side: str) -> set[int]:
    out: set[int] = set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rng = range(i1, i2) if side == "a" else range(j1, j2)
        out.update(rng)
    return out


def _change_attribution_section(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not baseline:
        return None
    cur_l, base_l = _lineage(current), _lineage(baseline)

    prompt_changed = False
    prompt_diff: dict[str, Any] | None = None
    cp, bp = cur_l.get("prompt_text"), base_l.get("prompt_text")
    if isinstance(cp, str) and isinstance(bp, str):
        prompt_changed = cur_l.get("prompt_hash") != base_l.get("prompt_hash") or cp != bp
        if prompt_changed:
            prompt_diff = _prompt_line_diff(bp, cp)

    config_changed = False
    config_diff: dict[str, Any] | None = None
    cc, bc = cur_l.get("config_snapshot"), base_l.get("config_snapshot")
    if isinstance(cc, dict) and isinstance(bc, dict):
        changed_keys = {
            k: {"from": bc.get(k), "to": cc.get(k)}
            for k in set(cc) | set(bc)
            if cc.get(k) != bc.get(k)
        }
        if changed_keys:
            config_changed = True
            config_diff = {"changed_keys": changed_keys}

    git = None
    fc, tc = base_l.get("git_commit"), cur_l.get("git_commit")
    if fc and tc and fc != tc:
        git = {"from_commit": fc, "to_commit": tc}

    largest_move = None
    regs = (diagnosis or {}).get("regressions") or []
    if regs:
        r = max(regs, key=lambda x: abs(_safe_float(x.get("delta"), 0.0) or 0.0))
        largest_move = {
            "gate": r.get("gate"),
            "delta": round(_safe_float(r.get("delta"), 0.0) or 0.0, 4),
        }

    if not (prompt_changed or config_changed or git or largest_move):
        return None

    bits: list[str] = []
    if prompt_changed and prompt_diff:
        bits.append(f"the system prompt changed ({prompt_diff['similarity'] * 100:.0f}% similar)")
    if config_changed and config_diff:
        bits.append(f"{len(config_diff['changed_keys'])} config key(s) changed")
    if git and isinstance(fc, str) and isinstance(tc, str) and not (
        prompt_changed or config_changed
    ):
        bits.append(f"code changed ({fc[:8]}..{tc[:8]})")
    move_txt = ""
    if largest_move and largest_move["gate"]:
        move_txt = (f", and Gate {largest_move['gate']} moved "
                    f"{largest_move['delta']:+.2f}")
    note = ("Between these two runs " + " and ".join(bits) + move_txt +
            ". Correlation, not proof — other changes may coincide." if bits
            else "No prompt/config/code change recorded between the two runs.")

    return {
        "prompt_changed": prompt_changed,
        "prompt_diff": prompt_diff,
        "config_changed": config_changed,
        "config_diff": config_diff,
        "git": git,
        "largest_gate_move": largest_move,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Narrative (P17) — the 2-4 plain-English sentences a QA lead pastes into a
# release ticket. Deterministic template by default; a `narrator` callable can
# replace it with an LLM-written version (falls back to the template on error).
# ---------------------------------------------------------------------------
_NARRATIVE_VERDICT_PHRASE = {
    "not_ready": "Not deployment-ready",
    "caution": "Deploy with caution",
    "ready": "Deployment-ready",
    "unknown": "No deployment verdict (no Harness Gate data)",
}


def _narrative_from_template(ins: dict[str, Any]) -> str:
    v = ins.get("verdict") or {}
    parts: list[str] = []

    phrase = _NARRATIVE_VERDICT_PHRASE.get(str(v.get("level") or ""), "Evaluation complete")
    head = v.get("headline") or ""
    conf = v.get("confidence")
    s1 = f"{phrase}"
    if head and v.get("level") in ("not_ready", "caution"):
        s1 += f": {head[0].lower() + head[1:]}"
    if conf:
        why = (v.get("confidence_reasons") or [])
        s1 += f". Confidence is {conf.upper()}"
        if why:
            s1 += f" ({why[0]})"
    parts.append(s1 + ".")

    # A critical / high security finding outranks everything else — surface it
    # even when Gate E's rate-based score reads as a pass.
    sec = ins.get("security_findings") or []
    sev_sec = [f for f in sec if f.get("severity") in ("critical", "high")]
    if sev_sec:
        kinds = sorted({f.get("threat_type", "threat") for f in sev_sec})
        parts.append(
            f"A {sev_sec[0]['severity']}-severity security finding was detected "
            f"({', '.join(kinds)} on task {sev_sec[0].get('task_id')}) — treat this "
            f"as the top priority regardless of the Gate E score."
        )

    # the security finding already has its own sentence above — the "biggest
    # measured shortfall" line describes a *scored* Gate component.
    acts = [a for a in (v.get("next_actions") or []) if not a.get("security")]
    if acts:
        a = acts[0]
        try:
            from agent_evaluator.ontology.metric_registry import pretty_metric_name

            fld = pretty_metric_name(a.get("field")) if a.get("field") else ""
        except Exception:
            fld = str(a.get("field") or "").replace("avg_", "").replace("_", " ").strip()
        act_txt = (a.get("action") or "").rstrip(".")
        # Guidance strings often open by restating the field ("Response
        # relevance/completeness is low. Strengthen …") — drop that clause so the
        # sentence doesn't say the field name twice back-to-back.
        if act_txt and fld and ". " in act_txt:
            _first, _rest = act_txt.split(". ", 1)
            if _first.lower().startswith(fld.lower()) and _rest.strip():
                act_txt = _rest.strip()
        if fld:
            hp = ""
            if isinstance(a.get("health"), (int, float)):
                hp = f" ({a['health'] * 100:.0f}%)"
            low_n = " (low sample — confirm before acting)" if a.get("low_sample") else ""
            s2 = f"The biggest measured shortfall is {fld}{hp} in Gate {a.get('gate')}{low_n}"
            if act_txt:
                s2 += f" — {act_txt[0].lower() + act_txt[1:]}"
            parts.append(s2 + ".")

    rq = ins.get("review_queue") or {}
    et = ins.get("evaluator_trust") or {}
    extras: list[str] = []
    if rq.get("n_items"):
        hi = (rq.get("by_priority") or {}).get("high", 0)
        extras.append(
            f"{rq['n_items']} task(s) are flagged for human review"
            + (f" ({hi} high-priority)" if hi else "")
        )
    if et.get("trust_level") in ("low", "medium"):
        extras.append(
            f"the LLM judge has {et['trust_level']} reliability for this run"
        )
    if extras:
        parts.append(extras[0][0].upper() + extras[0][1:] + (
            f"; {extras[1]}." if len(extras) > 1 else "."
        ))

    rfr = ins.get("reference_frame") or {}
    rf_tcr = next((m for m in (rfr.get("metrics") or []) if m.get("metric") == "tcr"), None)
    if rf_tcr and isinstance(rf_tcr.get("percentile"), int):
        s = (f"Against the '{rfr.get('label', 'reference')}' reference, TCR sits at "
             f"p{rf_tcr['percentile']}")
        ff = rfr.get("furthest_from_frontier")
        if ff and isinstance(ff.get("percentile"), int):
            s += (f"; {_pretty_metric_name(ff['metric'])} is the weakest at "
                  f"p{ff['percentile']}")
        parts.append(s + ".")

    cal = ins.get("calibration") or {}
    if (cal.get("verdict") == "overconfident"
            and isinstance(cal.get("confidence_gap"), (int, float))):
        parts.append(
            f"The agent is overconfident — it reports "
            f"{cal.get('mean_confidence', 0) * 100:.0f}% confidence but is only "
            f"{cal.get('empirical_accuracy', 0) * 100:.0f}% accurate "
            f"(ECE {cal.get('ece')}); wrong answers are being delivered as if certain."
        )
    ab = cal.get("abstention") or {}
    if ab.get("abstained_when_answerable"):
        parts.append(
            f"The agent abstained on {ab['n_abstained']} task(s), "
            f"{ab['abstained_when_answerable']} of which had a usable ground truth."
        )

    ce = ins.get("cost_economics") or {}
    proj = ce.get("projection") or {}
    if proj.get("total_usd"):
        s = f"At {proj.get('calls', 100000):,} calls this configuration costs " \
            f"about ${proj['total_usd']:,.0f}"
        if proj.get("wasted_usd"):
            s += (f", of which about ${proj['wasted_usd']:,.0f} is spent on failed "
                  f"or low-scoring tasks")
        parts.append(s + ".")

    return " ".join(parts)


def _narrative_section(ins: dict[str, Any], narrator: Any = None) -> str:
    template = ""
    try:
        template = _narrative_from_template(ins)
    except Exception:  # pragma: no cover - defensive
        template = ""
    if narrator is None:
        return template
    try:
        written = narrator({k: v for k, v in ins.items() if k != "narrative"})
        if isinstance(written, str) and written.strip():
            return written.strip()
    except Exception:  # pragma: no cover - narrator is user code
        pass
    return template


# ---------------------------------------------------------------------------
# Audience-targeted briefs + narrative claim audit (P34). One `narrative` string
# serves everyone badly; `briefs` gives a PM one-liner, a QA paragraph and an
# engineer checklist, all synthesised deterministically from the assembled
# insights. `narrative_audit` checks that the narrative's quantitative claims
# are backed by the structured numbers (catches an over-claiming LLM narrator).
# ---------------------------------------------------------------------------

# affirmative ship claims — phrased so a negation ("not deployment-ready",
# "is not ready to ship") does not match.
_READY_PHRASES = ("is deployment-ready", "is ready to ship", "is ready to deploy",
                  "ready to ship it", "safe to deploy", "good to ship",
                  "clear to ship", "cleared for deployment")
_RE_PCT = re.compile(r"(\d{1,3}(?:\.\d)?)\s?%")


def _narrative_audit_section(
    narrative: str, ins: dict[str, Any],
) -> dict[str, Any] | None:
    text = str(narrative or "")
    if not text.strip():
        return None
    adjustments: list[str] = []
    low = text.lower()

    verdict = (ins.get("verdict") or {}).get("level")
    if verdict and verdict != "ready" and any(p in low for p in _READY_PHRASES):
        adjustments.append(
            f"claims the agent is ready to ship, but the verdict is '{verdict}'"
        )

    mc = ins.get("metric_confidence") or {}
    backed = {
        round(v) for v in (mc.get("tcr_pct"), mc.get("accuracy_pct"))
        if isinstance(v, (int, float))
    }
    # Only a % that the narrative *attributes to* TCR / accuracy / completion is
    # a checkable claim — component-health scores, "% of failures", cost shares
    # etc. are legitimately different numbers, so a bare "40%" is not evidence
    # of over-claiming (P35: this check used to false-positive on the always-
    # clean template).
    for m in _RE_PCT.finditer(text):
        try:
            val = round(float(m.group(1)))
        except ValueError:
            continue
        window = low[max(0, m.start() - 40):m.end() + 12]
        about_headline = any(
            w in window for w in ("tcr", "accuracy", "accurate",
                                  "completion rate", "task completion", "pass rate")
        )
        if about_headline and 0 <= val <= 100 and backed \
                and all(abs(val - b) > 3 for b in backed):
            adjustments.append(
                f"cites {m.group(0)} as a headline metric, but the measured "
                f"TCR/accuracy is {', '.join(f'{b}%' for b in sorted(backed))}"
            )
            break

    if ("improv" in low or "regress" in low or "since the baseline" in low) \
            and ins.get("failure_lineage") is None and not ins.get("insight_changes"):
        adjustments.append(
            "talks about change vs a baseline, but no baseline was provided"
        )

    conf = (ins.get("verdict") or {}).get("confidence")
    hedged = any(w in low for w in ("confidence", "wide ci", "few task", "only",
                                    "preliminary", "small sample"))
    if conf == "low" and not hedged:
        adjustments.append(
            "does not mention that confidence is LOW for this run"
        )

    return {
        "claims_checked": True,
        "clean": not adjustments,
        "adjustments": adjustments,
    }


def _brief_effort(fix_plan: list[dict[str, Any]] | None) -> str:
    n = len(fix_plan or [])
    if not n:
        return "small"
    if n <= 2:
        return "roughly 1 focused change"
    if n <= 4:
        return "a few changes"
    return "several changes"


def _briefs_section(ins: dict[str, Any]) -> dict[str, Any] | None:
    v = ins.get("verdict") or {}
    level = v.get("level", "unknown")
    if level == "unknown" and not ins.get("failure_clusters"):
        return None
    rd = ins.get("readiness") or {}
    fp = rd.get("fix_plan") or []
    rq = ins.get("review_queue") or {}
    et = ins.get("evaluator_trust") or {}
    fr = ins.get("freshness") or {}
    segs = ins.get("failure_segments") or []
    conf = v.get("confidence")

    # ---- PM: ship / hold + effort + one risk ----------------------------
    verb = {"ready": "Ship", "caution": "Ship with caution", "not_ready": "Hold"}.get(
        level, "Unclear"
    )
    pm_bits = [f"{verb}."]
    if level != "ready" and v.get("failing_gates"):
        gate = v["failing_gates"][0]
        g = next((x for x in rd.get("gaps") or [] if x.get("gate") == gate), None)
        if g and g.get("score") is not None:
            pm_bits.append(
                f"Gate {gate} is failing ({g['score']:.2f} vs {g.get('target', 0.7)})."
            )
        else:
            pm_bits.append(f"Gate {gate} is failing.")
    pr = rd.get("projected_ready_after") or {}
    if pr.get("ready_after_n_items"):
        pm_bits.append(
            f"Closing the top {pr['ready_after_n_items']} failure cluster(s) is "
            f"projected to clear it — {_brief_effort(fp)}."
        )
    elif pr.get("remaining_structural_blockers"):
        pm_bits.append(
            f"Blocked on Gate(s) {', '.join(pr['remaining_structural_blockers'])} "
            f"that task fixes won't move."
        )
    if conf:
        pm_bits.append(f"Verdict confidence: {conf.upper()}.")
    pm = " ".join(pm_bits)

    # ---- QA: what to review -------------------------------------------------
    qa_bits: list[str] = []
    bp = rq.get("by_priority") or {}
    if rq.get("n_items"):
        qa_bits.append(
            f"Review the {rq['n_items']} queued task(s) "
            f"({bp.get('high', 0)} high-priority) first — "
            f"`agent-eval dataset promote` turns the confirmed ones into golden cases."
        )
    if et.get("trust_level") in ("low", "medium"):
        jvh = et.get("judge_vs_heuristic") or {}
        n_dis = len(jvh.get("disagreements") or [])
        qa_bits.append(
            f"The LLM judge has {et['trust_level']} reliability here"
            + (f" — it disagrees with the heuristic on {n_dis} task(s); spot-check them"
               if n_dis else "")
            + "."
        )
    _real_seg = next((s for s in segs if not s.get("catch_all")), None)
    if _real_seg:
        qa_bits.append(
            f"The biggest failure topic is \"{_real_seg.get('label')}\" "
            f"({_real_seg.get('n')} task(s), "
            f"{_real_seg.get('share_of_failures_pct')}% of failures)."
        )
    else:
        # No shared question topic — fall back to the prioritised root-cause cluster.
        # Prefer readiness.fix_plan[0] so this matches the Path-to-Green ordering.
        _fp = (ins.get("readiness") or {}).get("fix_plan") or []
        _fc = ins.get("failure_clusters") or []
        if _fp:
            c0 = _fp[0]
            qa_bits.append(
                f"Failures don't share a topic — the top root-cause cluster is "
                f"\"{c0.get('signature')}\" ({c0.get('count')} task(s))."
            )
        elif _fc:
            c0 = _fc[0]
            qa_bits.append(
                f"Failures don't share a topic — the largest root-cause cluster is "
                f"\"{c0.get('signature') or c0.get('label')}\" "
                f"({c0.get('count') or c0.get('n')} task(s))."
            )
        elif segs:
            qa_bits.append(
                "The failing tasks span unrelated topics — no dominant cluster."
            )
    for w in (fr.get("warnings") or [])[:2]:
        qa_bits.append(w)
    if not qa_bits:
        qa_bits.append("Nothing stands out for manual review — the automated "
                       "signals agree and the eval set looks healthy.")
    qa = " ".join(qa_bits)

    # ---- Engineer: ordered checklist -------------------------------------
    eng: list[str] = []
    for sf in (ins.get("security_findings") or [])[:1]:
        if sf.get("severity") in ("critical", "high"):
            eng.append(
                f"Investigate the {sf['severity']} {sf.get('threat_type')} on "
                f"task {sf.get('task_id')} before anything else."
            )
    # merge fix-plan rows that share a signature (they only differ by task_type)
    # fix_plan is already one row per signature (P35); just format it.
    for it in fp[:4]:
        _tts = it.get("task_types") or ([it["task_type"]] if it.get("task_type") else [])
        _tt = f" ({', '.join(str(x) for x in _tts)})" if _tts else ""
        eng.append(
            f"{it.get('signature')}{_tt} — {it.get('count')} task(s) — "
            f"{it.get('effort_hint')} "
            f"[projected TCR → {it.get('projected_tcr_after_pct')}%]"
        )
    for rec in (ins.get("recommendations") or []):
        snip = rec.get("code_snippet")
        if snip:
            eng.append(
                f"Gate {rec.get('gate')}: paste the @agent_eval snippet from the "
                f"Recommendations section."
            )
            break
    if not eng:
        eng.append("No blocking fixes — see the Recommendations section for "
                   "incremental improvements.")

    return {"pm": pm, "qa": qa, "engineer": eng}


# ---------------------------------------------------------------------------
# Registered experiments (P27) — falsifiable "I expect Gate X's <field> to move
# +N" hypotheses from `.aoo/experiments.jsonl`. When a baseline is available the
# open ones are scored (predicted vs actual); resolved ones carry their stored
# verdict. Read-only here — `agent-eval experiment score` persists resolutions.
# ---------------------------------------------------------------------------

def _experiment_hypothesis(gate: str, field: Any, predicted: Any) -> str:
    tgt = f"Gate {gate}" + (f" {field}" if field else " score")
    try:
        return f"{tgt} {float(predicted):+.3f}"
    except (TypeError, ValueError):
        return tgt


def _experiments_section(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    experiments_log_path: Any,
) -> list[dict[str, Any]] | None:
    if not experiments_log_path:
        return None
    try:
        from agent_evaluator.rca.experiments import load_experiments, score_experiments
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        registry = load_experiments(experiments_log_path)
    except Exception:  # pragma: no cover - defensive
        return None
    if not registry:
        return None

    open_exps = [e for e in registry if e.get("status") != "resolved"]
    resolved = [e for e in registry if e.get("status") == "resolved"]
    scored = _safe(score_experiments, open_exps, current, baseline, default=[]) or []

    items: list[dict[str, Any]] = []
    for row in scored:
        items.append({
            "experiment_id": row.get("experiment_id"),
            "hypothesis": _experiment_hypothesis(
                row.get("target_gate", ""), row.get("target_field"),
                row.get("predicted_delta"),
            ),
            "target_gate": row.get("target_gate"),
            "target_field": row.get("target_field"),
            "predicted": row.get("predicted_delta"),
            "actual": row.get("actual_delta"),
            "verdict": row.get("verdict"),
            "status": "open",
            "note": row.get("note"),
        })
    for e in resolved:
        items.append({
            "experiment_id": e.get("experiment_id"),
            "hypothesis": _experiment_hypothesis(
                e.get("target_gate", ""), e.get("target_field"),
                e.get("predicted_delta"),
            ),
            "target_gate": e.get("target_gate"),
            "target_field": e.get("target_field"),
            "predicted": e.get("predicted_delta"),
            "actual": e.get("actual_delta"),
            "verdict": e.get("verdict"),
            "status": "resolved",
            "note": e.get("note"),
        })
    return items or None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _build_partial_insights(
    current: dict[str, Any],
    hg: dict[str, Any],
    tasks: list[dict[str, Any]],
    total_tasks: int,
    targets: dict[str, Any] | None,
    narrator: Any,
) -> dict[str, Any]:
    """P50: the cheap, baseline-free subset of ``build_insights`` for a run in
    progress — a running readiness call + early-stop decision, plus the few
    sections that need no baseline / history / cohort / git. Every regression,
    lineage, cohort, trace-diff, longitudinal and experiment section is skipped
    (they all require a second run or a log). Same "never raises" contract."""
    ci = _safe(_metric_confidence_section, tasks, default={"n_tasks": total_tasks})
    diagnosis = _safe(
        lambda: __import__(
            "agent_evaluator.rca.diagnose", fromlist=["diagnose"],
        ).diagnose(current, None),
        default=None,
    )
    evaluator_trust = _safe(_evaluator_trust_section, tasks, current, default=None)
    security_findings = _safe(_security_findings_section, current, tasks, default=None)
    fclusters = _safe(_failure_clusters_section, tasks, total_tasks, default=[])
    out: dict[str, Any] = {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "detection_mode": "partial",
        "partial": True,
        "n_tasks": total_tasks,
        "running_verdict": _safe(
            _running_verdict_section, tasks, hg, targets=targets, default={},
        ),
        "verdict": _safe(
            _verdict_section, hg, diagnosis, ci, total_tasks, evaluator_trust,
            security_findings, targets, default={},
        ),
        "readiness": _safe(_readiness_section, tasks, hg, targets, default=None),
        "metric_confidence": ci,
        "gate_findings": _safe(_gate_findings_section, diagnosis, default=[]),
        "failure_clusters": fclusters,
        "failure_segments": _safe(_failure_segments_section, tasks, default=None),
        "security_findings": security_findings,
        "security_posture": _safe(
            _security_posture_section, current, tasks, security_findings, default=None,
        ),
        "calibration": _safe(_calibration_section, tasks, default=None),
        "sample_guidance": _safe(_sample_guidance_section, ci, default=None),
    }
    out["narrative"] = _safe(_narrative_section, out, narrator, default="")
    return out


def build_insights(
    current: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recommendation_log_path: str | Path | None = None,
    experiments_log_path: str | Path | None = None,
    with_experiment_metadata: bool = False,
    repo_path: str | Path = ".",
    narrator: Any = None,
    fixer: Any = None,
    explainer: Any = None,
    targets: dict[str, Any] | None = None,
    reference: dict[str, Any] | None = None,
    history_dir: str | Path | None = None,
    current_file: str | Path | None = None,
    cohort: list[dict[str, Any]] | None = None,
    cohort_metric: str = "tcr",
    partial: bool = False,
) -> dict[str, Any]:
    """Compute the machine-readable insight object for a result JSON.

    Args:
        current: loaded result JSON dict (``report.to_dict()`` / ``json.load()``).
        baseline: optional prior result JSON for regression-mode findings and
            failure-set lineage.
        recommendation_log_path: path to ``recommendation_outcomes.jsonl`` — when
            present, per-Gate "past changes" summaries are included.
        experiments_log_path: path to ``.aoo/experiments.jsonl`` (SPEC-041 P27) —
            when present, registered hypotheses are surfaced in ``experiments``;
            open ones are scored (predicted vs actual) if ``baseline`` is given.
        with_experiment_metadata: pass through to ``rca.diagnose()`` (git diff).
        repo_path: git repo path for ``with_experiment_metadata``.
        narrator: optional ``Callable[[insights_dict], str]`` — swaps the
            deterministic ``narrative`` for LLM-authored text (template fallback).
        explainer: optional ``Callable[[payload], dict|None]`` (SPEC-041 P47) —
            swaps the deterministic claim-level breakdown on
            ``failure_explanations`` for an LLM/NLI-backed one. Template fallback.
        fixer: optional ``Callable[[payload], dict|None]`` (SPEC-041 P36) — given
            ``{gate, cluster_signature, prompt_text, evidence[], template_proposal}``
            it may return a concrete ``{kind, before, after, rationale,
            evidence_task_ids}`` fix proposal that replaces the deterministic one
            on ``recommendations[].proposal``. Never auto-applied.
        targets: optional user targets/SLOs (SPEC-041 P43) —
            ``{gate_default?, gates?{A:0.85,…}, tcr_pct?, accuracy_pct?,
            cost_per_task_usd?}`` (typically ``utils.targets.load_targets()``).
            When set, ``verdict`` and ``readiness`` measure against this bar
            instead of the built-in 0.7.
        reference: optional external reference distribution (SPEC-041 P53) —
            ``utils.reference.load_reference()`` shape (``.aoo/reference.json``).
            When set, ``reference_frame`` reports the run's percentile + gap to
            the frontier against it.
        partial: SPEC-041 P50 — when ``True``, return only the cheap,
            baseline-free subset for a run *in progress*: a ``running_verdict``
            (Wilson-CI pass-rate vs target + a ``decisive`` early-stop flag),
            plus ``verdict`` / ``readiness`` / ``gate_findings`` /
            ``failure_clusters`` / ``security_*`` / ``calibration`` /
            ``narrative``. Every regression / lineage / cohort / longitudinal /
            experiment section is skipped.

    Returns:
        A JSON-serializable dict — see ``INSIGHTS_SCHEMA_VERSION``. Never raises;
        any section that fails to compute is omitted or empty.
    """
    hg = _harness_groups(current)
    tasks = [t for t in (current.get("tasks") or []) if isinstance(t, dict)]
    total_tasks = len(tasks)

    if partial:
        return _build_partial_insights(current, hg, tasks, total_tasks, targets, narrator)

    diagnosis: dict[str, Any] | None = None
    try:
        from agent_evaluator.rca.diagnose import diagnose

        diagnosis = diagnose(
            current, baseline,
            with_experiment_metadata=with_experiment_metadata,
            repo_path=repo_path,
        )
    except Exception:  # pragma: no cover - defensive
        diagnosis = None

    ci = {}
    try:
        ci = _metric_confidence_section(tasks)
    except Exception:  # pragma: no cover - defensive
        ci = {"n_tasks": total_tasks}

    evaluator_trust = _safe(_evaluator_trust_section, tasks, current, default=None)
    failure_lineage = _safe(_failure_lineage_section, tasks, baseline, default=None)
    eval_set_quality = _safe(
        _eval_set_quality_section, tasks, baseline, hg, current, default=None,
    )
    rag_loc = _safe(rag_localization, tasks, default=None)
    security_findings = _safe(_security_findings_section, current, tasks, default=None)
    fclusters = _safe(_failure_clusters_section, tasks, total_tasks, default=[])
    fsegments = _safe(_failure_segments_section, tasks, default=None)

    out: dict[str, Any] = {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "detection_mode": (diagnosis or {}).get("detection_mode", "absolute_threshold"),
        "verdict": _safe(
            _verdict_section, hg, diagnosis, ci, total_tasks, evaluator_trust,
            security_findings, targets, default={},
        ),
        "readiness": _safe(_readiness_section, tasks, hg, targets, default=None),
        "threshold_sensitivity": _safe(
            _threshold_sensitivity_section, hg, tasks, targets, default=None,
        ),
        "reference_frame": _safe(
            _reference_frame_section, current, hg, tasks, reference, default=None,
        ),
        "metric_confidence": ci,
        "evaluator_trust": evaluator_trust,
        "metric_signal": _safe(_metric_signal_section, tasks, default=None),
        "judge_robustness": _safe(_judge_robustness_section, current, tasks, default=None),
        "review_queue": _safe(
            _review_queue_section, tasks,
            evaluator_trust=evaluator_trust, failure_lineage=failure_lineage,
            eval_set_quality=eval_set_quality, rag_localization=rag_loc, default=None,
        ),
        "gate_findings": _safe(_gate_findings_section, diagnosis, default=[]),
        "failure_clusters": fclusters,
        "failure_segments": fsegments,
        "failure_triggers": _safe(_failure_triggers_section, tasks, default=None),
        "failure_explanations": _safe(
            _failure_explanations_section, tasks, explainer=explainer, default=None,
        ),
        "failure_lineage": failure_lineage,
        "insight_changes": _safe(
            _insight_changes_section, current, baseline, security_findings,
            evaluator_trust, hg, default=None,
        ),
        "longitudinal": _safe(
            _longitudinal_section, history_dir, current_file, default=None,
        ),
        "freshness": _safe(
            _freshness_section, current, baseline, eval_set_quality,
            fclusters, fsegments, ci, default=None,
        ),
        "recommendations": _safe(
            _recommendations_section, hg, diagnosis,
            recommendation_log_path=recommendation_log_path,
            baseline=baseline, current=current, default=[],
        ),
        "latency_budget": _safe(
            lambda: aggregate_latency_attribution(
                [a for a in (_extract_task_attr(t) for t in tasks) if a is not None]
            ),
            default=None,
        ),
        "rag_localization": rag_loc,
        "slice_analysis": _safe(_slice_analysis_section, tasks, baseline, default=[]),
        "metadata_slices": _safe(_metadata_slices_section, tasks, baseline, default=None),
        "sample_guidance": _safe(_sample_guidance_section, ci, default=None),
        "cost_economics": _safe(_cost_economics_section, tasks, current, default=None),
        "security_findings": security_findings,
        "security_posture": _safe(
            _security_posture_section, current, tasks, security_findings, default=None,
        ),
        "nondeterminism": _safe(_nondeterminism_section, tasks, default=None),
        "calibration": _safe(_calibration_section, tasks, default=None),
        "multiagent": _safe(_multiagent_section, tasks, default=None),
        "score_breakdowns": _safe(_score_breakdowns_section, tasks, default=None),
        "trajectories": _safe(_trajectories_section, tasks, default=None),
        "experiments": _safe(
            _experiments_section, current, baseline, experiments_log_path, default=None,
        ),
        "conversation": _safe(_conversation_section, current, default=None),
        "eval_set_quality": eval_set_quality,
        "change_attribution": _safe(
            _change_attribution_section, current, baseline, diagnosis, default=None,
        ),
        "cohort_comparison": _safe(
            _cohort_comparison_section,
            _labelled_cohort(current, cohort), cohort_metric, default=None,
        ) if cohort else None,
        "trace_diffs": _safe(
            _trace_diffs_section, current, cohort, default=None,
        ) if cohort else None,
        "reproducibility_manifest": _safe(
            lambda: ((current.get("extra_metrics") or {}).get("lineage") or {})
            .get("reproducibility_manifest"),
            default=None,
        ),
        "shared_cause_explanations": (diagnosis or {}).get("shared_cause_explanations", []),
        "newly_unmeasured_gates": (diagnosis or {}).get("newly_unmeasured_gates", []),
        "experiment_metadata": (diagnosis or {}).get("experiment_metadata"),
    }
    _safe(_attach_proposals, out, tasks, current, fixer, default=None)
    out["efficiency_opportunities"] = _safe(
        _efficiency_opportunities_section, tasks, current,
        out.get("cost_economics"), out.get("metadata_slices"),
        out.get("failure_clusters"), default=None,
    )
    out["regression_attribution"] = _safe(
        _regression_attribution_section, tasks, out.get("failure_lineage"),
        out.get("change_attribution"), out.get("metadata_slices"), default=None,
    )
    out["narrative"] = _safe(_narrative_section, out, narrator, default="")
    out["narrative_audit"] = _safe(
        _narrative_audit_section, out.get("narrative", ""), out,
        default=None,
    )
    out["briefs"] = _safe(_briefs_section, out, default=None)
    return out


def _safe(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:  # pragma: no cover - defensive
        return default
