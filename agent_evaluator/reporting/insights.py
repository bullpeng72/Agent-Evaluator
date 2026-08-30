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

import re
from collections import defaultdict
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
    return {
        "klass": klass,
        "context_recall": round(recall, 3) if recall is not None else None,
        "unsupported_ratio": round(unsupported_ratio, 3),
        "unsupported_claims": [s[:160] for s in unsupported[:3]],
    }


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
        if res["klass"] != "ok" and res["unsupported_claims"] and len(examples) < 10:
            examples.append({
                "task_id": str(t.get("task_id") or "—"),
                "klass": res["klass"],
                "context_recall": res["context_recall"],
                "unsupported_claims": res["unsupported_claims"],
            })
    if n_rag == 0:
        return None
    failing = {k: v for k, v in by_class.items() if k != "ok"}
    return {
        "n_rag_tasks": n_rag,
        "by_class": dict(by_class),
        "dominant_failure": (max(failing, key=failing.get) if failing else None),
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

    if fails:
        level = "not_ready"
        headline = f"{len(fails)} Gate(s) failing: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k in fails
        )
    elif warns:
        level = "caution"
        headline = f"{len(warns)} Gate(s) below target: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k in warns
        )
    elif passes:
        level = "ready"
        headline = f"All {len(passes)} measured Gates pass."
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

    next_actions: list[dict[str, Any]] = []
    for k in (fails + warns)[:3]:
        sf = shortfalls_by_gate.get(k) or []
        if sf:
            top = sf[0]
            fld = str(top.get("field", ""))
            next_actions.append({
                "gate": k,
                "field": fld,
                "health": top.get("health"),
                "action": component_guidance_for(fld) or "",
            })
        else:
            g = harness_groups.get(k) or {}
            next_actions.append({
                "gate": k,
                "field": None,
                "health": None,
                "action": f"See the Gate {k} section (score "
                          f"{g.get('score')}).",
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
        )
    except Exception:  # pragma: no cover - defensive
        pass

    return {
        "level": level,
        "headline": headline,
        "failing_gates": fails,
        "warning_gates": warns,
        "passing_gates": passes,
        "confidence": conf_level,
        "confidence_reasons": conf_reasons,
        "next_actions": next_actions,
    }


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
    try:
        from agent_evaluator.utils.confidence import bootstrap_diff_ci, bootstrap_mean_ci
    except Exception:  # pragma: no cover - defensive
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
        comps = [
            c for c in (_safe_float(m.get("completion_score")) for m in members)
            if c is not None
        ]
        accs = [
            a for a in (_safe_float(m.get("accuracy_score")) for m in members)
            if a is not None
        ]
        row: dict[str, Any] = {"task_type": ttype, "n": len(members)}
        if comps:
            row["tcr_pct"] = round(sum(comps) / len(comps) * 100.0, 2)
            lo, hi = bootstrap_mean_ci(comps)
            row["tcr_ci_pct"] = [round(lo * 100, 2), round(hi * 100, 2)]
        if accs:
            row["accuracy_pct"] = round(sum(accs) / len(accs) * 100.0, 2)
        base_members = base_by.get(ttype) or []
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
        rows.append(row)
    return rows


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
        o.get("gate_delta") for o in conf
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
# Entry point
# ---------------------------------------------------------------------------

def build_insights(
    current: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recommendation_log_path: str | Path | None = None,
    with_experiment_metadata: bool = False,
    repo_path: str | Path = ".",
) -> dict[str, Any]:
    """Compute the machine-readable insight object for a result JSON.

    Args:
        current: loaded result JSON dict (``report.to_dict()`` / ``json.load()``).
        baseline: optional prior result JSON for regression-mode findings and
            failure-set lineage.
        recommendation_log_path: path to ``recommendation_outcomes.jsonl`` — when
            present, per-Gate "past changes" summaries are included.
        with_experiment_metadata: pass through to ``rca.diagnose()`` (git diff).
        repo_path: git repo path for ``with_experiment_metadata``.

    Returns:
        A JSON-serializable dict — see ``INSIGHTS_SCHEMA_VERSION``. Never raises;
        any section that fails to compute is omitted or empty.
    """
    hg = _harness_groups(current)
    tasks = [t for t in (current.get("tasks") or []) if isinstance(t, dict)]
    total_tasks = len(tasks)

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

    out: dict[str, Any] = {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "detection_mode": (diagnosis or {}).get("detection_mode", "absolute_threshold"),
        "verdict": _safe(_verdict_section, hg, diagnosis, ci, total_tasks, default={}),
        "metric_confidence": ci,
        "gate_findings": _safe(_gate_findings_section, diagnosis, default=[]),
        "failure_clusters": _safe(
            _failure_clusters_section, tasks, total_tasks, default=[],
        ),
        "failure_lineage": _safe(
            _failure_lineage_section, tasks, baseline, default=None,
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
        "rag_localization": _safe(rag_localization, tasks, default=None),
        "slice_analysis": _safe(_slice_analysis_section, tasks, baseline, default=[]),
        "shared_cause_explanations": (diagnosis or {}).get("shared_cause_explanations", []),
        "newly_unmeasured_gates": (diagnosis or {}).get("newly_unmeasured_gates", []),
        "experiment_metadata": (diagnosis or {}).get("experiment_metadata"),
    }
    return out


def _safe(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:  # pragma: no cover - defensive
        return default
