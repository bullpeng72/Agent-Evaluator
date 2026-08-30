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
import math
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


def _security_findings_section(current: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(current, dict) or not (current.get("evaluators") or {}).get("security"):
        return None
    out: list[dict[str, Any]] = []

    def _emit(tid: Any, tracker: str, threat: str, severity: str, detail: str) -> None:
        out.append({
            "task_id": str(tid or "—"), "tracker": tracker,
            "threat_type": threat, "severity": severity or "unknown",
            "cwe": _THREAT_CWE.get(threat), "detail": detail[:200],
        })

    for r in _sec_records(current, "input_sanitizer"):
        if r.get("threat_count", 0) or r.get("sanitization_needed"):
            hits = [k[4:] for k in r if k.startswith("has_") and r.get(k)]
            _emit(r.get("task_id"), "input_sanitizer",
                  hits[0] if hits else "input_threat", r.get("risk_level", ""),
                  f"input threats: {', '.join(hits) or 'unspecified'}")
    for r in _sec_records(current, "output_leakage_detector"):
        if r.get("leakage_count", 0):
            hits = [k[9:] for k in r if k.startswith("contains_") and r.get(k)]
            _emit(r.get("task_id"), "output_leakage_detector",
                  hits[0] if hits else "output_leak", r.get("severity", ""),
                  f"response leaked: {', '.join(hits) or 'unspecified'}")
    for r in _sec_records(current, "tool_authorizer"):
        if r.get("has_dangerous_params") or not r.get("is_authorized", True) or r.get("is_restricted"):
            vt = r.get("violation_type") or (
                "unauthorized_tool" if not r.get("is_authorized", True) else "dangerous_params"
            )
            sev = "high" if not r.get("is_authorized", True) else "medium"
            _emit(r.get("task_id"), "tool_authorizer", vt, sev,
                  f"tool {r.get('tool_name', '?')} — {vt}")
    for r in _sec_records(current, "privilege_escalation_detector"):
        if r.get("escalation_detected"):
            rs = r.get("risk_score", 0)
            sev = "critical" if rs >= 8 else "high" if rs >= 5 else "medium"
            _emit(r.get("task_id"), "privilege_escalation_detector",
                  "privilege_escalation", sev,
                  f"{r.get('initial_privilege')} -> {r.get('max_privilege')} "
                  f"(risk {rs})")
    for r in _sec_records(current, "tool_chain_attack_detector"):
        if r.get("is_suspicious_chain"):
            pats = r.get("attack_patterns_detected") or [
                k for k, v in (r.get("attack_types") or {}).items() if v
            ]
            conf = r.get("confidence", 0.0)
            sev = "critical" if conf >= 0.8 else "high" if conf >= 0.5 else "medium"
            _emit(r.get("task_id"), "tool_chain_attack_detector",
                  "tool_chain_attack", sev,
                  f"patterns: {', '.join(str(p) for p in pats) or 'unspecified'}")

    if not out:
        return None
    _sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    out.sort(key=lambda f: (_sev_rank.get(f["severity"], 4), f["task_id"]))
    return out[:25]


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
    tok = em.get("tokens") if isinstance(em.get("tokens"), dict) else {}
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
            v.get("cohen_kappa_quadratic")
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
                k: sc.get(k) for k in
                ("completeness", "relevance", "factual_consistency", "faithfulness")
                if isinstance(sc.get(k), (int, float))
            }
            if dims:
                row["judge_dimensions"] = dims
                # judge dims are 0-5; normalise to 0-1 for the "weakest overall"
                signals.update({f"judge.{k}": v / 5.0 for k, v in dims.items()})

        if signals:
            row["weakest_signal"] = min(signals, key=signals.get)
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
    evaluator_trust: dict[str, Any] | None = None,
    security_findings: list[dict[str, Any]] | None = None,
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
            })
            break

    for k in (fails + warns)[:3]:
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
        "confidence": conf_level,
        "confidence_reasons": conf_reasons,
        "next_actions": next_actions,
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


def _readiness_section(
    tasks: list[dict[str, Any]],
    harness_groups: dict[str, Any],
) -> dict[str, Any] | None:
    """P29: quantified distance to a passing verdict + an impact-ordered fix
    plan with a deterministic projection. ``None`` when there is nothing to
    plan (no failing/warning gate and no failure cluster)."""
    fails, warns = [], []
    for k in "ABCDEFG":
        st = _gate_status(harness_groups.get(k))
        if st == "fail":
            fails.append(k)
        elif st == "warn":
            warns.append(k)
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

    # --- failure clusters, full membership (not the truncated public list) -
    pool = [
        t for t in tasks
        if _effective_fail(success=t.get("success", False),
                           accuracy=t.get("accuracy_score"),
                           completion=t.get("completion_score"))
    ]
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for t in pool:
        buckets[(_reason_signature(_task_reason(t)), t.get("task_type") or "—")].append(t)
    ranked = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    if not fails and not warns and not ranked:
        return None

    total = len(tasks)
    fixed_ids: set[str] = set()
    fix_plan: list[dict[str, Any]] = []
    for rank, ((sig, ttype), members) in enumerate(ranked[:8], 1):
        for m in members:
            if m.get("task_id"):
                fixed_ids.add(str(m["task_id"]))
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
        fix_plan.append({
            "rank": rank,
            "signature": sig,
            "task_type": ttype,
            "count": len(members),
            "impact_pct": round(len(members) / total * 100.0, 1),
            "example_task_ids": [str(m.get("task_id")) for m in members[:5] if m.get("task_id")],
            "effort_hint": hint,
            "targets_gates": tgt_gates,
            "projected_tcr_after_pct": round(proj_tcr * 100.0, 1),
            "projected_accuracy_after_pct": round(proj_acc * 100.0, 1),
            "cumulative_tcr_gain_pp": round((proj_tcr - (cur_tcr or 0.0)) * 100.0, 1),
        })

    final_gain = (
        (fix_plan[-1]["projected_tcr_after_pct"] / 100.0 - (cur_tcr or 0.0))
        if fix_plan else 0.0
    )

    gaps: list[dict[str, Any]] = []
    for k in fails + warns:
        g = harness_groups.get(k) or {}
        score = _safe_float(g.get("score"))
        row: dict[str, Any] = {
            "gate": k,
            "gate_name": _GATE_FULL.get(k, k),
            "score": None if score is None else round(score, 3),
            "target": _READINESS_TARGET,
            "gap": None if score is None else round(_READINESS_TARGET - score, 3),
            "blocking": k in fails,
        }
        if score is not None and k in _TCR_DRIVEN_GATES:
            row["projected_score_after_plan"] = round(min(1.0, score + final_gain), 3)
            row["estimate"] = True
        gaps.append(row)

    # smallest N fixes after which every TCR-driven blocking gate clears target
    tcr_blockers = [k for k in fails if k in _TCR_DRIVEN_GATES]
    other_blockers = [k for k in fails if k not in _TCR_DRIVEN_GATES]
    ready_after: int | None = None
    if tcr_blockers and fix_plan:
        for item in fix_plan:
            gain = item["projected_tcr_after_pct"] / 100.0 - (cur_tcr or 0.0)
            if all(
                (_safe_float((harness_groups.get(k) or {}).get("score")) or 0.0) + gain
                >= _READINESS_TARGET
                for k in tcr_blockers
            ):
                ready_after = item["rank"]
                break

    if not tcr_blockers and not other_blockers:
        note = ("No gate is failing outright; the fix plan is ordered by how much "
                "TCR each cluster is costing you.")
    elif ready_after is not None and not other_blockers:
        note = (f"Closing the top {ready_after} cluster(s) is projected to clear "
                f"every failing gate (estimate — assumes those tasks then pass and "
                f"nothing else moves).")
    elif other_blockers:
        note = ("Gate(s) " + ", ".join(f"{k} ({_GATE_FULL.get(k, k)})" for k in other_blockers)
                + " are not driven by task outcomes — the fix plan will not close "
                "them. Address them from their own Gate section.")
    else:
        note = ("The fix plan does not fully close the failing TCR-driven gate(s) "
                "on its own — more or deeper fixes are needed.")

    return {
        "target_gate_score": _READINESS_TARGET,
        "current_tcr_pct": None if cur_tcr is None else round(cur_tcr * 100.0, 1),
        "current_accuracy_pct": None if cur_acc is None else round(cur_acc * 100.0, 1),
        "gaps": gaps,
        "fix_plan": fix_plan,
        "projected_ready_after": {
            "ready_after_n_items": ready_after,
            "remaining_structural_blockers": other_blockers,
            "note": note,
        },
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


def _eval_set_quality_section(
    tasks: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
    harness_groups: dict[str, Any],
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

    return {
        "n_tasks": len(tasks),
        "task_type_histogram": dict(hist),
        "near_duplicate_clusters": dup_clusters[:10],
        "coverage_warnings": warnings,
        "suspicious_ground_truth": suspicious[:10],
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
        term_mass: Counter = Counter()
        for tid in grp:
            for term, w in vecs[tid].items():
                term_mass[term] += w
        kw = [t for t, _ in term_mass.most_common(5)]
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
        })
    segments.sort(key=lambda s: -s["n"])
    segments = segments[:_SEG_MAX]
    if not segments:
        return None
    if len(leftovers) >= _SEG_MIN_MEMBERS:
        segments.append({
            "label": "other (no shared topic)",
            "keywords": [],
            "task_ids": leftovers,
            "n": len(leftovers),
            "share_of_failures_pct": round(len(leftovers) / n_fail * 100.0, 1),
            "impact_pct": round(len(leftovers) / total * 100.0, 1),
            "dominant_reason": "mixed",
            "example_question": "",
        })
    return segments


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
# per-session goal drift. Coarse text heuristics, stdlib only.
# ---------------------------------------------------------------------------
_CONV_DRIFT_OVERLAP = 0.15     # first<->last user-turn content overlap below this = goal drift
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
    drift: list[dict[str, Any]] = []
    worst = None

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

        if len(turns) >= 2:
            first_u = _wtok(turns[0].get("user") or "")
            last_u = _wtok(turns[-1].get("user") or "")
            ov_fl = _overlap(last_u, first_u) if first_u else 1.0
            tc = _safe_float((s.get("metrics") or {}).get("topic_coherence"))
            # ignore a trailing "ok thanks / bye" — only a substantive last turn
            # counts as drift.
            substantive_last = len(last_u) >= 4
            if (substantive_last and ov_fl < _CONV_DRIFT_OVERLAP) or (tc is not None and tc < 0.4):
                drift.append({
                    "session_id": s.get("session_id"),
                    "first_last_topic_overlap": round(ov_fl, 3),
                    "reason": ("the last user turn barely overlaps the first "
                               "(topic drifted) " if ov_fl < _CONV_DRIFT_OVERLAP
                               else "low topic_coherence"),
                })

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

    return {
        "n_sessions": len(sessions),
        "avg_overall_score": round(sum(overalls) / len(overalls), 3) if overalls else None,
        "avg_context_retention": round(sum(ctx_rets) / len(ctx_rets), 3) if ctx_rets else None,
        "turn_quality_trajectory": traj,
        "degradation_after_turn": degradation_after,
        "goal_drift_sessions": drift[:10],
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
    for idx, rep in enumerate([current, *(cohort or [])]):
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
        first_lbl, pt = hits[0]
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
            "compared": [first_lbl, cur_label],
            "verdict": verdict,
            "score_delta": {"completion": round(comp_d, 3), "accuracy": round(acc_d, 3)},
            "response_diff": {
                "similarity": round(sm.ratio(), 3),
                "added": _word_runs(sm, "b", w_c),
                "removed": _word_runs(sm, "a", w_p),
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
    return abs((da - db).days)


def _question_fingerprint(report: dict[str, Any] | None) -> frozenset:
    return frozenset(
        str(t.get("question") or "").strip().lower()
        for t in ((report or {}).get("tasks") or [])
        if isinstance(t, dict) and str(t.get("question") or "").strip()
    )


def _insight_changes_section(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    security_findings: list[dict[str, Any]] | None,
    evaluator_trust: dict[str, Any] | None,
    failure_clusters: list[dict[str, Any]] | None,
    harness_groups: dict[str, Any],
) -> dict[str, Any] | None:
    if not baseline:
        return None
    base_tasks = [t for t in (baseline.get("tasks") or []) if isinstance(t, dict)]
    base_hg = _harness_groups(baseline)

    b_clusters = _safe(_failure_clusters_section, base_tasks, len(base_tasks), default=[]) or []
    cur_sigs = {c.get("signature") for c in (failure_clusters or [])}
    base_sigs = {c.get("signature") for c in b_clusters}
    new_clusters = sorted(s for s in cur_sigs - base_sigs if s)
    resolved_clusters = sorted(s for s in base_sigs - cur_sigs if s)

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

    cur_fail = {k for k in "ABCDEFG" if _gate_status(harness_groups.get(k)) == "fail"}
    base_fail = {k for k in "ABCDEFG" if _gate_status(base_hg.get(k)) == "fail"}
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
    prompt_diff = None
    cp, bp = cur_l.get("prompt_text"), base_l.get("prompt_text")
    if isinstance(cp, str) and isinstance(bp, str):
        prompt_changed = cur_l.get("prompt_hash") != base_l.get("prompt_hash") or cp != bp
        if prompt_changed:
            prompt_diff = _prompt_line_diff(bp, cp)

    config_changed = False
    config_diff = None
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
    if config_changed:
        bits.append(f"{len(config_diff['changed_keys'])} config key(s) changed")
    if git and not (prompt_changed or config_changed):
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

    phrase = _NARRATIVE_VERDICT_PHRASE.get(v.get("level"), "Evaluation complete")
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
        fld = str(a.get("field") or "").replace("avg_", "").replace("_", " ").strip()
        act_txt = (a.get("action") or "").rstrip(".")
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
    for m in _RE_PCT.finditer(text):
        try:
            val = round(float(m.group(1)))
        except ValueError:
            continue
        if 0 <= val <= 100 and backed and all(abs(val - b) > 3 for b in backed):
            adjustments.append(
                f"cites {m.group(0)} which does not match the measured "
                f"TCR/accuracy ({', '.join(f'{b}%' for b in sorted(backed))})"
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
    if segs:
        s0 = segs[0]
        qa_bits.append(
            f"The biggest failure cluster is \"{s0.get('label')}\" "
            f"({s0.get('n')} task(s), {s0.get('share_of_failures_pct')}% of failures)."
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
    for it in fp[:4]:
        eng.append(
            f"{it.get('signature')} ({it.get('count')} task(s)) — "
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

def build_insights(
    current: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recommendation_log_path: str | Path | None = None,
    experiments_log_path: str | Path | None = None,
    with_experiment_metadata: bool = False,
    repo_path: str | Path = ".",
    narrator: Any = None,
    cohort: list[dict[str, Any]] | None = None,
    cohort_metric: str = "tcr",
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

    evaluator_trust = _safe(_evaluator_trust_section, tasks, current, default=None)
    failure_lineage = _safe(_failure_lineage_section, tasks, baseline, default=None)
    eval_set_quality = _safe(
        _eval_set_quality_section, tasks, baseline, hg, default=None,
    )
    rag_loc = _safe(rag_localization, tasks, default=None)
    security_findings = _safe(_security_findings_section, current, default=None)
    fclusters = _safe(_failure_clusters_section, tasks, total_tasks, default=[])
    fsegments = _safe(_failure_segments_section, tasks, default=None)

    out: dict[str, Any] = {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "detection_mode": (diagnosis or {}).get("detection_mode", "absolute_threshold"),
        "verdict": _safe(
            _verdict_section, hg, diagnosis, ci, total_tasks, evaluator_trust,
            security_findings, default={},
        ),
        "readiness": _safe(_readiness_section, tasks, hg, default=None),
        "metric_confidence": ci,
        "evaluator_trust": evaluator_trust,
        "review_queue": _safe(
            _review_queue_section, tasks,
            evaluator_trust=evaluator_trust, failure_lineage=failure_lineage,
            eval_set_quality=eval_set_quality, rag_localization=rag_loc, default=None,
        ),
        "gate_findings": _safe(_gate_findings_section, diagnosis, default=[]),
        "failure_clusters": fclusters,
        "failure_segments": fsegments,
        "failure_triggers": _safe(_failure_triggers_section, tasks, default=None),
        "failure_lineage": failure_lineage,
        "insight_changes": _safe(
            _insight_changes_section, current, baseline, security_findings,
            evaluator_trust, fclusters, hg, default=None,
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
        "nondeterminism": _safe(_nondeterminism_section, tasks, default=None),
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
