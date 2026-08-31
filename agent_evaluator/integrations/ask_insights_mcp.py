"""
agent_evaluator.integrations.ask_insights_mcp
================================================
SPEC-041 P31 — a stdio MCP server that lets an agent (or a human, via a chat
client) *interrogate* the insight layer of an evaluation result, instead of
re-reading the whole HTML report.

It loads a result JSON, computes ``reporting.insights.build_insights()`` once,
and answers four structured questions:

  ``insights_summary(result_file, baseline_file="")``
      deploy verdict + narrative + the biggest failure themes + review counts.
  ``insights_readiness(result_file)``
      the "path to green": per-gate gap to the pass line + the impact-ordered
      fix plan + the projection of how many fixes reach a passing verdict.
  ``insights_why_failed(result_file, task_id)``
      one task: why it failed, the passage / tool step that most likely caused
      it, which failure segment it belongs to, and its score signals.
  ``insights_list(result_file, filter, baseline_file="")``
      the task ids matching a filter — ``failing`` / ``judge_disagreement`` /
      ``borderline`` / ``nondeterministic`` / ``security`` / ``regressed``
      (needs ``baseline_file``) / ``review`` / ``segment:<text>``.

Pure retrieval — no new judgement, and it never writes to the result file.
Opt-in: ``pip install "agent-evaluator[mcp]"``. Chains with ``search_violations``
(violation history) and ``recommend_fix`` (static prescriptions).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MAX_LIST = 60


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_result(path_str: str) -> dict[str, Any]:
    p = Path(path_str).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"result file not found: {p}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("result file is not a JSON object")
    return data


def _insights_for(
    result_file: str, baseline_file: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    from agent_evaluator.reporting.insights import build_insights

    data = _load_result(result_file)
    baseline = None
    if baseline_file:
        try:
            baseline = _load_result(baseline_file)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            baseline = None
    ins = build_insights(data, baseline) or {}
    return data, ins


# ---------------------------------------------------------------------------
# Answer builders (pure — importable for tests)
# ---------------------------------------------------------------------------

def summary_text(data: dict[str, Any], ins: dict[str, Any]) -> str:
    v = ins.get("verdict") or {}
    lines = [f"Verdict: {v.get('level', 'unknown').upper()} — {v.get('headline', '')}"]
    if v.get("confidence"):
        lines.append(
            f"Confidence: {v['confidence'].upper()}"
            + (f" ({'; '.join(v.get('confidence_reasons') or [])})"
               if v.get("confidence_reasons") else "")
        )
    narr = ins.get("narrative")
    if narr:
        lines.append("")
        lines.append(str(narr).strip())

    mc = ins.get("metric_confidence") or {}
    if mc.get("tcr_pct") is not None:
        ci = mc.get("tcr_ci_pct")
        ci_s = f" (95% CI {ci[0]:.0f}–{ci[1]:.0f})" if isinstance(ci, list) and len(ci) == 2 else ""
        lines.append(f"\nTCR {mc['tcr_pct']:.1f}%{ci_s} over {mc.get('n_tasks', 0)} task(s).")

    segs = ins.get("failure_segments") or []
    if segs:
        lines.append("\nBiggest failure segments:")
        for s in segs[:4]:
            lines.append(
                f"  • {s.get('label')} — {s.get('n')} task(s), "
                f"{s.get('share_of_failures_pct')}% of failures "
                f"[{s.get('dominant_reason')}]"
            )
    else:
        for c in (ins.get("failure_clusters") or [])[:4]:
            lines.append(
                f"  • {c.get('signature')} ({c.get('task_type')}) — "
                f"{c.get('count')} task(s), ~{c.get('impact_pct')}%p of TCR"
            )

    rq = ins.get("review_queue") or {}
    if rq.get("n_items"):
        bp = rq.get("by_priority") or {}
        lines.append(
            f"\nHuman review queue: {bp.get('high', 0)} high · {bp.get('medium', 0)} medium. "
            f"Use insights_list(filter='review') for the ids."
        )
    et = ins.get("evaluator_trust") or {}
    if et.get("trust_level") in ("low", "medium"):
        lines.append(
            f"Evaluator trust is {et['trust_level'].upper()} — "
            f"{'; '.join(et.get('trust_reasons') or [])}"
        )
    lines.append("\nAsk insights_readiness(...) for the fix plan, or "
                 "insights_why_failed(..., task_id=...) for a single task.")
    return "\n".join(lines)


def readiness_text(ins: dict[str, Any]) -> str:
    rd = ins.get("readiness")
    if not rd:
        return ("No path-to-green plan — no gate is below its pass line and there "
                "are no failure clusters. The run is either passing or has no "
                "Harness Gate data.")
    lines = [f"Target gate score: {rd.get('target_gate_score', 0.7)}"]
    if rd.get("current_tcr_pct") is not None:
        lines.append(f"Current TCR: {rd['current_tcr_pct']:.1f}%")

    lines.append("\nGate gaps:")
    for g in rd.get("gaps") or []:
        after = g.get("projected_score_after_plan")
        after_s = f", ~{after:.2f} after the plan (est.)" if isinstance(after, (int, float)) else ""
        lines.append(
            f"  • Gate {g.get('gate')} ({g.get('gate_name')}): {g.get('score')} "
            f"vs target {g.get('target')} — gap {g.get('gap'):+.2f}"
            f"{' [BLOCKING]' if g.get('blocking') else ''}{after_s}"
        )

    fp = rd.get("fix_plan") or []
    if fp:
        lines.append("\nFix plan (ordered by TCR impact):")
        for it in fp:
            lines.append(
                f"  {it.get('rank')}. {it.get('signature')} — {it.get('count')} task(s), "
                f"{it.get('impact_pct')}% of set → projected TCR "
                f"{it.get('projected_tcr_after_pct')}% "
                f"(+{it.get('cumulative_tcr_gain_pp')}pp cumulative). "
                f"Helps: {', '.join(it.get('targets_gates') or []) or '—'}. "
                f"{it.get('effort_hint')}"
            )
    pr = rd.get("projected_ready_after") or {}
    lines.append(f"\n{pr.get('note', '')}")
    lines.append("Projection is first-order — use it to sequence work, not as a guarantee.")
    return "\n".join(lines)


def _task_by_id(data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for t in data.get("tasks") or []:
        if isinstance(t, dict) and str(t.get("task_id")) == str(task_id):
            return t
    return None


def why_failed_text(data: dict[str, Any], ins: dict[str, Any], task_id: str) -> str:
    from agent_evaluator.reporting.insights import _task_reason

    t = _task_by_id(data, task_id)
    if t is None:
        return f"No task with id {task_id!r} in this result file."
    lines = [f"Task {task_id}  (type: {t.get('task_type', '?')})"]
    q = str(t.get("question") or "")
    if q:
        lines.append(f"Question: {q[:300]}")
    lines.append(
        f"Scores: completion={t.get('completion_score')} accuracy={t.get('accuracy_score')} "
        f"success={t.get('success')}"
    )
    lines.append(f"Reason: {_task_reason(t)}")

    for tr in ins.get("failure_triggers") or []:
        if str(tr.get("task_id")) == str(task_id):
            lines.append(f"Likely trigger [{tr.get('kind')}]: {tr.get('detail')}")
            break
    for s in ins.get("failure_segments") or []:
        if str(task_id) in (s.get("task_ids") or []):
            lines.append(f"Failure segment: {s.get('label')} "
                         f"(shared reason: {s.get('dominant_reason')})")
            break
    for sb in ins.get("score_breakdowns") or []:
        if str(sb.get("task_id")) == str(task_id):
            comps = sb.get("accuracy_components") or {}
            if comps:
                lines.append("Accuracy signals: "
                             + ", ".join(f"{k} {v:.2f}" for k, v in comps.items()))
            if sb.get("accuracy_weakest"):
                lines.append(f"Weakest accuracy signal: {sb['accuracy_weakest']}")
            if sb.get("judge_reasoning"):
                lines.append(f"Judge said: {sb['judge_reasoning']}")
            break
    for nd in ins.get("nondeterminism") or []:
        if str(nd.get("task_id")) == str(task_id):
            lines.append(
                f"Non-deterministic: reproducibility {nd.get('reproducibility_score')} "
                f"over {nd.get('run_count')} runs."
            )
            break
    rq = ins.get("review_queue") or {}
    for it in rq.get("items") or []:
        if str(it.get("task_id")) == str(task_id):
            lines.append(f"Flagged for human review ({it.get('priority')}): "
                         f"{'; '.join(it.get('reasons') or [])}")
            break
    return "\n".join(lines)


def contrast_text(data: dict[str, Any], ins: dict[str, Any], task_id: str) -> str:
    """SPEC-041 P62: the most similar *passing* task to a failing one, and the
    structured diff isolating the likely differentiator."""
    rows = ins.get("contrast_pairs") or []
    row = next((r for r in rows if str(r.get("fail_task_id")) == str(task_id)), None)
    if row is None:
        if not rows:
            return ("No contrast pairs for this result (need both failing and "
                    "similar passing tasks).")
        return (f"No contrast pair for {task_id!r}. Available: "
                + ", ".join(str(r.get("fail_task_id")) for r in rows))
    d = row.get("differences") or {}
    lines = [
        f"Failing  {row['fail_task_id']}: {row['fail_question']}",
        f"Passing  {row['pass_task_id']}: {row['pass_question']}  "
        f"(question similarity {row.get('question_similarity')})",
        f"Likely differentiator: {row.get('likely_differentiator')}",
    ]
    rt = d.get("retrieval")
    if rt:
        lines.append(
            f"  retrieval: fail {rt.get('fail_n_chunks')} chunk(s) "
            f"(best gt-overlap {rt.get('fail_best_gt_overlap')}), pass "
            f"{rt.get('pass_n_chunks')} chunk(s) (best {rt.get('pass_best_gt_overlap')})"
        )
    if d.get("tools"):
        lines.append(f"  tools: fail {d['tools'].get('fail')} · pass {d['tools'].get('pass')}")
    if d.get("response"):
        lines.append(f"  response words: fail {d['response'].get('fail_words')} · "
                     f"pass {d['response'].get('pass_words')}")
    if d.get("metadata"):
        for k, (fv, pv) in d["metadata"].items():
            lines.append(f"  metadata {k}: fail {fv} · pass {pv}")
    return "\n".join(lines)


def list_task_ids(data: dict[str, Any], ins: dict[str, Any], filt: str) -> str:
    from agent_evaluator.reporting.insights import _effective_fail

    f = (filt or "").strip().lower()
    ids: list[str] = []
    label = f

    if f in ("failing", "failed", "fail"):
        ids = [
            str(t.get("task_id")) for t in data.get("tasks") or []
            if isinstance(t, dict) and t.get("task_id") and _effective_fail(
                success=t.get("success", False), accuracy=t.get("accuracy_score"),
                completion=t.get("completion_score"))
        ]
    elif f in ("judge_disagreement", "judge", "disagreement"):
        et = ins.get("evaluator_trust") or {}
        jvh = et.get("judge_vs_heuristic") or {}
        ids = [str(d.get("task_id")) for d in jvh.get("disagreements") or [] if d.get("task_id")]
    elif f in ("borderline",):
        rq = ins.get("review_queue") or {}
        ids = [
            str(it.get("task_id")) for it in rq.get("items") or []
            if any("borderline" in str(r).lower() for r in it.get("reasons") or [])
        ]
    elif f in ("nondeterministic", "nondeterminism", "flaky"):
        ids = [str(n.get("task_id")) for n in ins.get("nondeterminism") or [] if n.get("task_id")]
    elif f in ("security",):
        ids = [
            str(s.get("task_id"))
            for s in ins.get("security_findings") or [] if s.get("task_id")
        ]
    elif f in ("regressed", "regression"):
        fl = ins.get("failure_lineage")
        if fl is None:
            return ("This filter needs a baseline — call with baseline_file set to a "
                    "prior result JSON that has tasks[].")
        ids = list(fl.get("regressed") or [])
    elif f in ("review", "review_queue", "hitl"):
        rq = ins.get("review_queue") or {}
        ids = [str(it.get("task_id")) for it in rq.get("items") or [] if it.get("task_id")]
    elif f.startswith("segment:"):
        want = f.split(":", 1)[1].strip()
        for s in ins.get("failure_segments") or []:
            if want in str(s.get("label", "")).lower():
                ids = list(s.get("task_ids") or [])
                label = f"segment {s.get('label')!r}"
                break
    else:
        return ("Unknown filter. Use one of: failing, judge_disagreement, borderline, "
                "nondeterministic, security, regressed, review, segment:<text>.")

    # dedupe preserving order
    seen: set[str] = set()
    uniq = [i for i in ids if not (i in seen or seen.add(i))]
    if not uniq:
        return f"No task ids match filter {label!r}."
    head = uniq[:_MAX_LIST]
    more = f"  (+{len(uniq) - len(head)} more)" if len(uniq) > len(head) else ""
    return f"{len(uniq)} task(s) match {label!r}:\n" + ", ".join(head) + more


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def build_server() -> Any:
    """A ``FastMCP`` server exposing the ``insights_*`` tools."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("agent-evaluator-ask-insights")

    @server.tool()
    def insights_summary(result_file: str, baseline_file: str = "") -> str:
        """Deploy verdict + plain-English narrative + the biggest failure themes +
        the human-review counts for an evaluation result JSON. Pass ``baseline_file``
        (a prior result JSON) to also get regression context."""
        data, ins = _insights_for(result_file, baseline_file)
        return summary_text(data, ins)

    @server.tool()
    def insights_readiness(result_file: str) -> str:
        """The "path to green": how far each failing/warning gate is from its pass
        line, the failure clusters ordered by projected TCR impact, and how many
        fixes are projected to reach a passing verdict."""
        _data, ins = _insights_for(result_file)
        return readiness_text(ins)

    @server.tool()
    def insights_why_failed(result_file: str, task_id: str) -> str:
        """Everything the insight layer knows about one task: why it failed, the
        retrieved passage or tool step that most likely caused it, which failure
        segment it belongs to, its accuracy signals and judge rationale, and
        whether it is flagged for human review or is non-deterministic."""
        data, ins = _insights_for(result_file)
        return why_failed_text(data, ins, task_id)

    @server.tool()
    def insights_contrast(result_file: str, task_id: str) -> str:
        """For a failing task, the most similar *passing* task and a structured
        diff (retrieved chunks, tool calls, response length, metadata) isolating
        the one thing that most likely made the difference. Call with no matching
        task_id to see which failing tasks have a contrast pair."""
        data, ins = _insights_for(result_file)
        return contrast_text(data, ins, task_id)

    @server.tool()
    def insights_list(result_file: str, filter: str, baseline_file: str = "") -> str:  # noqa: A002
        """Task ids matching a filter: 'failing', 'judge_disagreement', 'borderline',
        'nondeterministic', 'security', 'regressed' (needs baseline_file), 'review',
        or 'segment:<text>' (a failure segment whose label contains <text>)."""
        _data, ins = _insights_for(result_file, baseline_file)
        return list_task_ids(_data, ins, filter)

    return server


def main() -> None:
    try:
        server = build_server()
    except ImportError as exc:
        import sys

        sys.stderr.write(
            "[agent-evaluator] ask_insights MCP server needs the optional 'mcp' "
            'dependency — install it with:  pip install "agent-evaluator[mcp]"\n'
            f"  (original error: {exc})\n"
        )
        raise SystemExit(1) from exc
    server.run()


if __name__ == "__main__":
    main()
