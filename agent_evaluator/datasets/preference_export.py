"""
SPEC-043 REQ-6b — preference-signal export.

``judge_pairwise`` (A/B judge), human transparency annotations, and the
fail↔pass ``contrast_pairs`` already carry "this response is better than that
one" signals; there was no way to pull them out as a dataset. This does that —
**export only**. Reward models / fine-tuning are the team's job (the book's
boundary), so nothing here trains anything.

Row shape (JSON Lines)::

    {"question", "response_a", "response_b",
     "preferred": "a" | "b" | "tie",
     "source": "pairwise_judge" | "annotation" | "contrast_pair",
     "annotator"?: str, "result_file"?: str}

Sources, per result JSON:
  - ``extra_metrics.llm_judge_pairwise`` — every ``judge_pairwise()`` call
    (``winner`` → ``preferred``).
  - ``extra_metrics.preference_annotations`` / per-task ``extra.preference`` —
    human A/B labels ``{question, response_a, response_b, preferred, annotator?}``.
  - ``extra_metrics.insights.contrast_pairs`` joined to ``tasks[]`` — the failing
    response is ``a``, the nearest passing response is ``b``, ``preferred: "b"``.

Pure stdlib. Never raises on a malformed file — that file is skipped.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Union

_VALID_PREF = ("a", "b", "tie")


def _norm_pref(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if s in _VALID_PREF:
        return s
    if s in ("win_a", "a_wins", "left"):
        return "a"
    if s in ("win_b", "b_wins", "right"):
        return "b"
    if s in ("equal", "draw", "none"):
        return "tie"
    return None


def iter_preference_rows(result_data: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield preference rows from one loaded result JSON. Order:
    pairwise_judge, then annotations, then contrast_pairs."""
    if not isinstance(result_data, dict):
        return
    em = result_data.get("extra_metrics") or {}

    # 1. pairwise judge -------------------------------------------------------- #
    for r in em.get("llm_judge_pairwise") or []:
        if not isinstance(r, dict):
            continue
        pref = _norm_pref(r.get("winner") or r.get("preferred"))
        q = str(r.get("question") or "")
        ra, rb = str(r.get("response_a") or ""), str(r.get("response_b") or "")
        if pref is None or not (ra or rb):
            continue
        yield {
            "question": q, "response_a": ra, "response_b": rb,
            "preferred": pref, "source": "pairwise_judge",
        }

    # 2. human annotations --------------------------------------------------- #
    anns: list[Any] = list(em.get("preference_annotations") or [])
    for t in result_data.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        _e = t.get("extra")
        pe = _e if isinstance(_e, dict) else {}
        pr = pe.get("preference")
        if isinstance(pr, dict):
            anns.append({"question": t.get("question"), **pr})
        elif isinstance(pr, list):
            anns.extend(
                {"question": t.get("question"), **a}
                for a in pr if isinstance(a, dict)
            )
    for a in anns:
        if not isinstance(a, dict):
            continue
        pref = _norm_pref(a.get("preferred"))
        ra, rb = str(a.get("response_a") or ""), str(a.get("response_b") or "")
        if pref is None or not (ra or rb):
            continue
        row = {
            "question": str(a.get("question") or ""),
            "response_a": ra, "response_b": rb,
            "preferred": pref, "source": "annotation",
        }
        if a.get("annotator"):
            row["annotator"] = str(a["annotator"])
        yield row

    # 3. contrast pairs (fail=a, nearest pass=b) --------------------------- #
    insights = em.get("insights") or {}
    cps = insights.get("contrast_pairs") or []
    if cps:
        by_id = {
            str(t.get("task_id")): t
            for t in (result_data.get("tasks") or [])
            if isinstance(t, dict) and t.get("task_id")
        }
        for cp in cps:
            if not isinstance(cp, dict):
                continue
            f = by_id.get(str(cp.get("fail_task_id")))
            p = by_id.get(str(cp.get("pass_task_id")))
            if not f or not p:
                continue
            ra, rb = str(f.get("response") or ""), str(p.get("response") or "")
            if not (ra or rb):
                continue
            yield {
                "question": str(cp.get("fail_question")
                                or f.get("question") or ""),
                "response_a": ra, "response_b": rb,
                "preferred": "b", "source": "contrast_pair",
            }


def _iter_result_files(path: Union[str, Path]) -> Iterator[Path]:
    p = Path(path)
    if p.is_file():
        yield p
        return
    if p.is_dir():
        yield from sorted(p.glob("*.json"))


def export_preferences(
    path: Union[str, Path], out_path: Union[str, Path],
) -> dict[str, Any]:
    """Scan ``path`` (a result JSON or a directory of them), write a preference
    JSON Lines file to ``out_path``.

    Returns ``{n_written, by_source{}, n_files_scanned, out_path}``. A file that
    fails to parse is skipped (counted in ``n_files_skipped``)."""
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    by_source: dict[str, int] = {}
    n_written = 0
    n_files = 0
    n_skipped = 0
    seen: set[tuple[str, str, str, str]] = set()

    with open(out_p, "w", encoding="utf-8") as out:
        for fp in _iter_result_files(path):
            n_files += 1
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                n_skipped += 1
                continue
            for row in iter_preference_rows(data):
                key = (
                    row["question"], row["response_a"],
                    row["response_b"], row["source"],
                )
                if key in seen:
                    continue
                seen.add(key)
                row["result_file"] = fp.name
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_written += 1
                by_source[row["source"]] = by_source.get(row["source"], 0) + 1

    return {
        "n_written": n_written,
        "by_source": by_source,
        "n_files_scanned": n_files,
        "n_files_skipped": n_skipped,
        "out_path": str(out_p),
    }
