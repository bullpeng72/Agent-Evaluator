"""
Single-agent failure taxonomy (SPEC-041 P55).

``mast_taxonomy.py`` covers *multi-agent* failure modes (Cemri et al. 2025).
This is its single-agent counterpart: one canonical set of failure modes with a
remediation and an ``owner`` (who fixes it — the prompt, a config, the eval
data, the model, or infra), plus a deterministic ``classify_failure(task)`` that
maps one failing task to a mode.

Pure data + stdlib string logic — no external deps, no import from
``reporting.insights`` (callers pass in a normalised ``reason`` string). The
classifier is intentionally coarse and explainable; ``confidence`` reflects how
many independent signals agreed.
"""
from __future__ import annotations

import re
from typing import Any

# owner: who acts on it
PROMPT, CONFIG, DATA, MODEL, INFRA = "prompt", "config", "data", "model", "infra"


class FailureMode:
    __slots__ = ("code", "name", "owner", "description", "remediation")

    def __init__(self, code: str, name: str, owner: str, description: str,
                 remediation: str) -> None:
        self.code = code
        self.name = name
        self.owner = owner
        self.description = description
        self.remediation = remediation

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "name": self.name, "owner": self.owner,
                "description": self.description, "remediation": self.remediation}


FAILURE_MODES: dict[str, FailureMode] = {
    m.code: m for m in [
        FailureMode(
            "INSTRUCTION_IGNORED", "Instruction ignored", PROMPT,
            "A stated constraint was not honoured — a required keyword or section "
            "is missing, a forbidden tool was used, or the scope was exceeded.",
            "Restate the constraint as an explicit rule near the top of the "
            "system prompt; enforce it with InstructionConfig / ScopeConfig."),
        FailureMode(
            "FORMAT_VIOLATION", "Output format violation", PROMPT,
            "The response shape is wrong — prose where JSON / a list / a schema "
            "was asked for, or a broken structure.",
            "Give one worked example of the exact output format and validate it "
            "with a custom_parser / response schema."),
        FailureMode(
            "REFUSAL_WHEN_ANSWERABLE", "Refusal when answerable", MODEL,
            "The agent declined or deflected on a task that has a usable ground "
            "truth.",
            "Loosen an over-broad safety instruction; add a few-shot example that "
            "answers a similar question directly."),
        FailureMode(
            "RETRIEVAL_MISS", "Retrieval miss", CONFIG,
            "No retrieved passage covers the expected answer (RAG).",
            "Raise top_k, add a re-ranker, or fix chunking / the index; confirm "
            "the source document is actually ingested."),
        FailureMode(
            "GROUNDING_MISS", "Grounding miss", PROMPT,
            "The context contained the answer but the response ignored or "
            "contradicted it.",
            "Add a strict grounding instruction ('only state facts from the "
            "context; say you don't know otherwise')."),
        FailureMode(
            "HALLUCINATED_FACT", "Hallucinated fact", MODEL,
            "The response asserts a specific fact that is absent from the context "
            "and wrong.",
            "Tighten grounding, lower temperature, and enable faithfulness "
            "checking; consider a stronger model for this task type."),
        FailureMode(
            "TOOL_SELECTION_ERROR", "Wrong / missing tool", PROMPT,
            "The agent called the wrong tool or skipped a tool it needed.",
            "Sharpen tool descriptions and when-to-use rules; pass expected_tools "
            "so ToolSelectionTracker can score it."),
        FailureMode(
            "TOOL_EXECUTION_ERROR", "Tool execution error", INFRA,
            "A tool call returned an error or an unusable result.",
            "Add bounded retries with backoff (FaultToleranceConfig); check the "
            "tool's auth / rate limits / argument schema."),
        FailureMode(
            "RUNTIME_ERROR", "Runtime error / timeout", INFRA,
            "The task raised an exception, timed out, or crashed before "
            "finishing.",
            "Add retries + a tighter per-tool timeout; profile the slow step "
            "(see the latency budget)."),
        FailureMode(
            "PREMATURE_STOP", "Premature stop", PROMPT,
            "A multi-step task ended with only part of the work done.",
            "Decompose with SubtaskConfig(min_subtasks=…) and instruct the agent "
            "to verify every step before answering."),
        FailureMode(
            "LOOP_OR_REPETITION", "Loop / repetition", CONFIG,
            "The agent repeated an identical step or output segment.",
            "Tighten LoopDetectionConfig(consecutive_repeat_threshold=…); add a "
            "progress check to the loop."),
        FailureMode(
            "OVER_ELABORATION", "Over-elaboration", PROMPT,
            "The answer is far longer than needed and buries or dilutes the "
            "actual answer.",
            "Instruct a length ceiling and 'lead with the answer'; score "
            "conciseness in ResponseQuality."),
        FailureMode(
            "LABEL_OR_SPEC_ISSUE", "Label / spec problem", DATA,
            "The task fails near-identically at very low accuracy across runs — "
            "the pattern points at the eval label or question, not the agent.",
            "Re-check the ground_truth and wording; fix the eval set, then "
            "`agent-eval dataset promote`."),
        FailureMode(
            "LOW_SIMILARITY", "Low answer similarity (unclassified)", PROMPT,
            "The answer is materially off but matches none of the specific "
            "modes — needs a human read.",
            "Inspect the worst examples for a shared root cause, then adjust the "
            "prompt or the relevant Gate config."),
    ]
}

_CODES = list(FAILURE_MODES)

# --------------------------------------------------------------------------- #
# classifier signal helpers (stdlib only)
# --------------------------------------------------------------------------- #
_REFUSAL_RE = re.compile(
    r"\b(i (?:can(?:not|'t)|am (?:not able|unable))\s+(?:help|assist|answer|provide)"
    r"|i'?m sorry,? but|i don'?t have (?:access|enough)"
    r"|as an ai\b|i cannot comply)\b",
    re.I,
)
_JSON_ASK_RE = re.compile(r"\b(json|as a list|bullet(?:ed)? list|table|yaml|xml|markdown)\b", re.I)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


_STOP = frozenset(
    "the a an of to in on at for and or but is are was were be been being it its "
    "this that these those with as by from into out about not no do does did has "
    "have had you your i we they he she them his her their our can could will would "
    "should may might must if then than so such only also which who whom what when "
    "where why how".split()
)


def _words(text: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _content_words(text: Any) -> set[str]:
    return {w for w in _words(text) if w not in _STOP and len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _looks_structured(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if s[0] in "[{" or s.startswith("```"):
        return True
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    bulleted = sum(1 for ln in lines if ln[:2] in ("- ", "* ") or ln[:2].strip().isdigit())
    return len(lines) >= 2 and bulleted >= max(2, len(lines) // 2)


def classify_failure(
    task: dict[str, Any],
    *,
    reason: str | None = None,
    repeated_across_runs: bool = False,
) -> dict[str, Any]:
    """Map one failing task to a :data:`FAILURE_MODES` code.

    Args:
        task: the task dict (``response`` / ``ground_truth`` / ``question`` /
            ``context`` / ``tool_calls`` / ``partial_reason`` / ``accuracy_score``
            / ``expected_tools`` / ``extra``).
        reason: a pre-normalised failure-reason string (e.g. the caller's
            ``_reason_signature(_task_reason(task))``). Falls back to
            ``partial_reason``.
        repeated_across_runs: caller's signal that this task fails the same way
            in a baseline too (enables ``LABEL_OR_SPEC_ISSUE``).

    Returns:
        ``{code, name, owner, remediation, confidence}`` — ``confidence`` in
        ``0.3..0.95`` scales with how many signals agreed.
    """
    r = str(reason or task.get("partial_reason") or "").lower()
    resp = str(task.get("response") or "")
    q = str(task.get("question") or "")
    gt = str(task.get("ground_truth") or "")
    acc = task.get("accuracy_score")
    acc = float(acc) if isinstance(acc, (int, float)) else None
    tcs = [s for s in (task.get("tool_calls") or []) if isinstance(s, dict)]
    ctx = task.get("context")
    chunks = ([str(c) for c in ctx] if isinstance(ctx, list)
              else [str(ctx)] if ctx else [])

    hits: list[tuple[str, int]] = []  # (code, weight)

    # --- runtime / tool ---------------------------------------------------- #
    if r.startswith("error:") or any(w in r for w in ("timeout", "exception", "traceback")):
        hits.append(("RUNTIME_ERROR", 3))
    if any(s.get("success") is False for s in tcs):
        hits.append(("TOOL_EXECUTION_ERROR", 3))
    exp_tools = task.get("expected_tools") or []
    if exp_tools:
        used = {str(s.get("tool_name") or s.get("tool") or s.get("name") or "").lower()
                for s in tcs}
        want = {str(x).lower() for x in exp_tools}
        if want and not (want & used):
            hits.append(("TOOL_SELECTION_ERROR", 2))
    if any(w in r for w in ("wrong tool", "tool selection", "unexpected tool")):
        hits.append(("TOOL_SELECTION_ERROR", 2))

    # --- loop / premature stop ------------------------------------------- #
    if any(w in r for w in ("loop", "repeat", "repetition", "consecutive_repeat")):
        hits.append(("LOOP_OR_REPETITION", 3))
    if any(w in r for w in ("partial", "incomplete", "multi-step", "only part",
                            "subtask", "not all steps")):
        hits.append(("PREMATURE_STOP", 2))

    # --- refusal --------------------------------------------------------- #
    if _REFUSAL_RE.search(resp) and gt.strip():
        hits.append(("REFUSAL_WHEN_ANSWERABLE", 3))

    # --- format -------------------------------------------------------- #
    if _JSON_ASK_RE.search(q) and resp.strip() and not _looks_structured(resp):
        hits.append(("FORMAT_VIOLATION", 2))
    if any(w in r for w in ("format", "schema", "not valid json", "parse")):
        hits.append(("FORMAT_VIOLATION", 2))

    # --- instruction ignored ------------------------------------------- #
    if any(w in r for w in ("missing required", "required keyword", "forbidden tool",
                            "scope", "out of scope", "instruction", "constraint")):
        hits.append(("INSTRUCTION_IGNORED", 2))

    # --- RAG: retrieval vs grounding --------------------------------- #
    gt_w = _content_words(gt)
    if chunks and gt_w:
        best = max((_overlap(gt_w, _content_words(c)) for c in chunks), default=0.0)
        if best < 0.30:
            hits.append(("RETRIEVAL_MISS", 3))
        elif any(w in r for w in ("ground", "context", "contradict", "unsupported",
                                  "not grounded", "faithful")):
            hits.append(("GROUNDING_MISS", 3))
    elif any(w in r for w in ("hallucin", "fabricat", "made up", "not grounded",
                              "unsupported")):
        hits.append(("HALLUCINATED_FACT", 2))

    # number contradiction with the ground truth -> a concrete wrong fact
    if gt and resp:
        gn, rn = set(_NUM_RE.findall(gt)), set(_NUM_RE.findall(resp))
        if gn and rn and not (gn & rn):
            hits.append(("HALLUCINATED_FACT", 2))

    # --- over-elaboration ------------------------------------------- #
    if gt and resp and len(_words(resp)) > 6 * max(1, len(_words(gt))) and len(resp) > 400:
        hits.append(("OVER_ELABORATION", 2))

    # --- label / spec problem ------------------------------------ #
    if repeated_across_runs and acc is not None and acc < 0.35:
        hits.append(("LABEL_OR_SPEC_ISSUE", 3))
    if any(w in r for w in ("suspicious", "ground_truth similarity", "label")):
        hits.append(("LABEL_OR_SPEC_ISSUE", 2))

    if not hits:
        return {**FAILURE_MODES["LOW_SIMILARITY"].to_dict(), "confidence": 0.3}

    agg: dict[str, int] = {}
    for code, w in hits:
        agg[code] = agg.get(code, 0) + w
    best_code = max(agg, key=lambda c: (agg[c], -_CODES.index(c)))
    total = sum(agg.values())
    conf = round(min(0.95, 0.35 + 0.6 * (agg[best_code] / max(total, 1))), 2)
    return {**FAILURE_MODES[best_code].to_dict(), "confidence": conf}


def remediation_for(code: str) -> str | None:
    m = FAILURE_MODES.get(str(code))
    return m.remediation if m else None
