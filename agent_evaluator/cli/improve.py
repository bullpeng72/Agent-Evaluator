"""
``agent-eval improve {plan,start,verify}`` (SPEC-041 P49) — the closed
improvement loop.

The insight layer already produces, for every failing / warning gate, a
concrete ``recommendations[].proposal`` (a prompt edit, a config change, or a
data fix) plus a falsifiable ``experiment`` prediction. This command turns that
into a tracked workflow:

    plan    — show the ordered improvement plan for a result file
    start   — register each proposal as an experiment in .aoo/experiments.jsonl
              and write an apply-me change stub to .aoo/improve/
    verify  — after the next run, score the open experiments predicted-vs-actual
              and (with --persist) resolve them + append to
              recommendation_outcomes.jsonl so future recommendations learn

No new logic — a thin wrapper around ``reporting.insights.build_insights`` and
``rca.experiments`` / ``rca.recommendation_tracking``. ``verify`` is
informational and never exits non-zero on a refuted prediction (HOTL: a wrong
prediction is data, not a build failure).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from agent_evaluator.cli._utils import _supports_color

_COLOR = _supports_color()
G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""

_DEFAULT_LOG = ".aoo/experiments.jsonl"
_DEFAULT_OUT = ".aoo/improve"
_KIND_LABEL = {
    "prompt_edit": "prompt edit",
    "config_change": "config change",
    "data_fix": "data / eval-set fix",
}
_VERDICT_COLOR = {
    "confirmed": G, "partially_confirmed": Y, "refuted": RD,
    "inconclusive": D, "pending": D,
}


def _err(msg: str) -> str:
    return f"{RD}❌ {msg}{R}"


def _ok(msg: str) -> str:
    return f"{G}✅ {msg}{R}"


def _load_result(path_str: str | None) -> dict | None:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_file():
        print(_err(f"File not found: {p}"))
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(_err(f"Failed to parse JSON: {exc}"))
        return None


def _insights(current: dict, baseline: dict | None) -> dict[str, Any]:
    from agent_evaluator.reporting.insights import build_insights

    try:
        return build_insights(current, baseline) or {}
    except Exception as exc:  # pragma: no cover - build_insights never raises
        print(_err(f"Could not compute insights: {exc}"))
        return {}


def _proposals(ins: dict, gate_filter: str | None) -> list[dict[str, Any]]:
    """One row per recommendation that carries a proposal, richest gate first."""
    rows: list[dict[str, Any]] = []
    for rec in ins.get("recommendations") or []:
        prop = rec.get("proposal")
        if not prop:
            continue
        gate = str(rec.get("gate") or "")
        if gate_filter and gate.upper() != gate_filter.upper():
            continue
        exp = rec.get("experiment") or {}
        field = exp.get("field") or (
            (rec.get("shortfalls") or [{}])[0].get("field") if rec.get("shortfalls") else None
        )
        rows.append({
            "gate": gate,
            "gate_name": rec.get("gate_name") or f"Gate {gate}",
            "status": rec.get("status"),
            "kind": prop.get("kind"),
            "before": prop.get("before") or "",
            "after": prop.get("after") or "",
            "rationale": prop.get("rationale") or "",
            "evidence_task_ids": prop.get("evidence_task_ids") or [],
            "authored_by": prop.get("authored_by") or "template",
            "target_field": field,
            "predicted_delta": exp.get("predicted_gate_delta"),
            "recommended_tasks": exp.get("recommended_tasks"),
            "prior": rec.get("prior"),
        })
    order = {"fail": 0, "warn": 1}
    rows.sort(key=lambda r: (order.get(str(r.get("status") or ""), 9), r.get("gate")))
    return rows


def _exp_note(row: dict[str, Any]) -> str:
    rat = " ".join((row.get("rationale") or "").split())
    return f"[improve] Gate {row['gate']} {row.get('kind')}: {rat}"[:200]


def _print_plan(rows: list[dict[str, Any]], open_notes: set[str]) -> None:
    if not rows:
        print(f"{D}No proposals — every measured gate is at target, or the "
              f"result file has no failure clusters to act on.{R}")
        return
    print(f"{B}Improvement plan — {len(rows)} proposal(s){R}\n")
    for i, r in enumerate(rows, 1):
        pd = r.get("predicted_delta")
        pd_s = f"  predicted Δ {pd:+.3f}" if isinstance(pd, (int, float)) else ""
        tracked = f"  {G}[experiment open]{R}" if _exp_note(r) in open_notes else ""
        sc = RD if r.get("status") == "fail" else Y
        print(f"{B}{i}. Gate {r['gate']} — {r['gate_name']}{R} "
              f"{sc}({r.get('status')}){R}{pd_s}{tracked}")
        print(f"   change type : {_KIND_LABEL.get(str(r.get('kind') or ''), r.get('kind'))}"
              f"  ({r.get('authored_by')})")
        if r.get("target_field"):
            print(f"   target field: {r['target_field']}")
        print(f"   before: {D}{_clip(r['before'])}{R}")
        print(f"   after : {_clip(r['after'])}")
        print(f"   why   : {D}{_clip(r['rationale'], 220)}{R}")
        if r.get("evidence_task_ids"):
            print(f"   tasks : {', '.join(r['evidence_task_ids'])}")
        pr = r.get("prior")
        if pr:
            cr = pr.get("confirm_rate")
            cr_s = f"{cr * 100:.0f}% confirmed" if isinstance(cr, (int, float)) \
                else "no decisive runs"
            pc = G if pr.get("verdict") == "works_well" else (
                RD if pr.get("verdict") == "ineffective" else Y)
            print(f"   record: {pc}{str(pr.get('category', '')).replace('_', ' ')} "
                  f"on Gate {r['gate']} — {pr.get('verdict')} ({cr_s}, "
                  f"n={pr.get('n')}){R}")
        print()
    print(f"{D}Next: agent-eval improve start <result.json>  "
          f"(registers experiments + writes change stubs){R}")


def _clip(s: str, n: int = 160) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _stub_text(row: dict[str, Any], eid: str) -> str:
    return (
        f"# Improvement stub — Gate {row['gate']} ({row['gate_name']})\n\n"
        f"- experiment_id: {eid}\n"
        f"- change type: {_KIND_LABEL.get(str(row.get('kind') or ''), row.get('kind'))}\n"
        f"- target field: {row.get('target_field') or '(gate score)'}\n"
        f"- predicted Δ: {row.get('predicted_delta')}\n"
        f"- evidence tasks: {', '.join(row.get('evidence_task_ids') or []) or '—'}\n\n"
        f"## Rationale\n\n{row.get('rationale')}\n\n"
        f"## Before\n\n```\n{row.get('before')}\n```\n\n"
        f"## After (apply this)\n\n```\n{row.get('after')}\n```\n\n"
        f"## Then\n\n"
        f"1. Apply the change above to your agent / decorator / eval set.\n"
        f"2. Re-run the evaluation to produce a new result JSON.\n"
        f"3. `agent-eval improve verify <new_result.json> --baseline "
        f"<this_result.json> --persist`\n"
    )


def _cmd_plan(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(getattr(args, "baseline", None))
    ins = _insights(current, baseline)
    rows = _proposals(ins, getattr(args, "gate", None))
    from agent_evaluator.rca.experiments import load_experiments

    open_notes = {
        str(e.get("note") or "")
        for e in load_experiments(args.log, status="open")
    }
    _print_plan(rows, open_notes)
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(getattr(args, "baseline", None))
    ins = _insights(current, baseline)
    rows = _proposals(ins, getattr(args, "gate", None))
    if not rows:
        print(f"{D}Nothing to start — no actionable proposals in {args.result_file}.{R}")
        return 0

    from agent_evaluator.rca.experiments import load_experiments, register_experiment

    existing = {
        (str(e.get("target_gate")), e.get("target_field"), str(e.get("note") or ""))
        for e in load_experiments(args.log, status="open")
    }
    out_dir = Path(args.out)
    if not args.yes:
        print(f"{B}Will register {len(rows)} experiment(s) in {args.log} "
              f"and write stubs to {out_dir}/{R}")
        print(f"{D}Re-run with --yes to proceed.{R}")
        _print_plan(rows, {n for _, _, n in existing})
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    registered = skipped = 0
    for r in rows:
        note = _exp_note(r)
        key = (r["gate"], r.get("target_field"), note)
        if key in existing:
            print(f"{D}skip  Gate {r['gate']} — matching open experiment exists{R}")
            skipped += 1
            continue
        pd = r.get("predicted_delta")
        row = register_experiment(
            args.log,
            target_gate=r["gate"],
            predicted_delta=float(pd) if isinstance(pd, (int, float)) else 0.05,
            target_field=r.get("target_field"),
            note=note,
            baseline_ref=args.result_file,
        )
        eid = row["experiment_id"]
        stub = out_dir / f"{r['gate']}_{r.get('kind', 'change')}_{eid}.md"
        stub.write_text(_stub_text(r, eid), encoding="utf-8")
        print(_ok(f"Gate {r['gate']}: {eid}  →  {stub}"))
        registered += 1

    print(f"\n{B}{registered} registered, {skipped} skipped.{R}")
    if registered:
        print(f"{D}Apply the stubs, re-run, then: agent-eval improve verify "
              f"<new_result.json> --baseline {args.result_file} --persist{R}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    baseline = _load_result(args.baseline)
    if baseline is None:
        return 1

    from agent_evaluator.rca.experiments import (
        load_experiments,
        resolve_experiment,
        score_experiments,
    )

    open_exps = load_experiments(args.log, status="open")
    improve_exps = [
        e for e in open_exps if str(e.get("note") or "").startswith("[improve]")
    ] or open_exps
    if not improve_exps:
        print(f"{D}No open experiments in {args.log}.{R}")
        return 0

    scored = score_experiments(improve_exps, current, baseline, min_effect=args.min_effect)
    print(f"{B}{'GATE/FIELD':<32} {'PRED':>8} {'ACTUAL':>8} VERDICT{R}")
    outcome_log = Path(args.result_file).parent / "recommendation_outcomes.jsonl"
    persisted = 0
    for row in scored:
        tgt = str(row.get("target_gate") or "?")
        if row.get("target_field"):
            tgt += f".{row['target_field']}"
        pred, act = row.get("predicted_delta"), row.get("actual_delta")
        verdict = row.get("verdict", "inconclusive")
        vc = _VERDICT_COLOR.get(verdict, "")
        print(f"{tgt[:32]:<32} "
              f"{(f'{pred:+.3f}' if isinstance(pred, (int, float)) else '-'):>8} "
              f"{(f'{act:+.3f}' if isinstance(act, (int, float)) else '-'):>8} "
              f"{vc}{verdict}{R}")
        if args.persist and verdict in ("confirmed", "partially_confirmed", "refuted"):
            resolve_experiment(
                args.log, row["experiment_id"], actual_delta=act, verdict=verdict,
                note=f"improve verify vs {Path(args.baseline).name}",
            )
            _record_outcome(outcome_log, row, args.baseline, baseline, current)
            persisted += 1
    if args.persist:
        print(_ok(f"Resolved {persisted} experiment(s); appended outcomes to {outcome_log}"))
    else:
        print(f"{D}Dry run — pass --persist to resolve experiments and log outcomes.{R}")
    return 0


def _record_outcome(
    outcome_log: Path, row: dict[str, Any], baseline_name: str,
    baseline: dict, current: dict,
) -> None:
    try:
        from agent_evaluator.rca.recommendation_tracking import record_recommendation_outcome

        record_recommendation_outcome(
            outcome_log,
            recommendation_id=f"improve:{row.get('experiment_id')}",
            target_gate=str(row.get("target_gate") or ""),
            before=baseline,
            after=current,
            target_field=row.get("target_field") or None,
            note=f"improve loop, predicted {row.get('predicted_delta')}, "
                 f"verdict {row.get('verdict')} (vs {baseline_name})",
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _find_agent_eval_decorators(repo: Path) -> list[tuple[Path, str, str, int, str]]:
    """AST-scan ``repo`` for functions decorated with ``@agent_eval(...)``.
    Returns ``(file, full_source, decorator_call_source, lineno, func_name)``."""
    import ast

    hits: list[tuple[Path, str, str, int, str]] = []
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"}
    for py in repo.rglob("*.py"):
        if any(part in skip for part in py.parts):
            continue
        try:
            src = py.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                fn = call.func if call else dec
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else "")
                if name == "agent_eval" and call is not None:
                    seg = ast.get_source_segment(src, call) or ""
                    if seg:
                        hits.append((py, src, seg, call.lineno, node.name))
    return hits


def _unified(before: str, after: str, path_label: str) -> str:
    import difflib

    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path_label}", tofile=f"b/{path_label}",
    ))


def _patch_prompt_edit(row: dict[str, Any], repo: Path | None, prompt_file: str | None,
                       lineage: dict[str, Any]) -> tuple[str, str]:
    src = prompt_file or lineage.get("prompt_source_path")
    if not src:
        return ("", "no prompt source — set PerformanceMonitor(prompt_source_path=…) "
                "or pass --prompt-file; suggested text:\n" + row.get("after", ""))
    if Path(src).is_absolute():
        p = Path(src)
    elif repo is None:
        return ("", "no repo root to resolve the relative prompt path against")
    else:
        p = repo / src
    if not p.is_file():
        return ("", f"prompt file not found: {p}")
    text = p.read_text(encoding="utf-8")
    before_frag = (row.get("before") or "").strip()
    after_frag = (row.get("after") or "").strip()
    if before_frag and not before_frag.startswith("(") and before_frag in text:
        new = text.replace(before_frag, after_frag, 1)
    else:  # nothing to anchor on — append the new instruction
        new = text.rstrip("\n") + "\n" + after_frag + "\n"
    if new == text:
        return ("", f"could not locate the anchor text in {p}")
    return (_unified(text, new, str(src)), "")


def _patch_config_change(row: dict[str, Any], repo: Path) -> tuple[str, str]:
    hits = _find_agent_eval_decorators(repo)
    if not hits:
        return ("", "no @agent_eval(...) decorator found in the repo; add manually:\n"
                + row.get("after", ""))
    py, src, seg, lineno, fname = hits[0]
    add = " ".join((row.get("after") or "").split())     # kwargs on one logical line
    if seg.rstrip().endswith(")"):
        head = seg.rstrip()[:-1].rstrip().rstrip(",")
        new_seg = (f"{head},\n    # agent-eval improve: proposed for Gate "
                   f"{row.get('gate')}\n    {add}\n)")
    else:  # unexpected shape — fall back to a trailing note
        new_seg = seg + f"  # agent-eval improve: {add}"
    if new_seg == seg or seg not in src:
        return ("", "could not rewrite the decorator call; add manually:\n"
                + row.get("after", ""))
    new_src = src.replace(seg, new_seg, 1)
    try:
        label = str(py.relative_to(repo))
    except ValueError:
        label = str(py)
    return (
        _unified(src, new_src, label),
        f"(decorator on `{fname}` at {py.name}:{lineno})",
    )


def _cmd_patch(args: argparse.Namespace) -> int:
    current = _load_result(args.result_file)
    if current is None:
        return 1
    ins = _insights(current, _load_result(getattr(args, "baseline", None)))
    rows = _proposals(ins, getattr(args, "gate", None))
    if not rows:
        print(f"{D}No proposals to patch.{R}")
        return 0
    repo = Path(getattr(args, "repo", ".") or ".")
    lineage = ((current.get("extra_metrics") or {}).get("lineage") or {})
    out_dir = Path(args.out) if getattr(args, "out", None) else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    n_diff = 0
    for r in rows:
        kind = r.get("kind")
        print(f"\n{B}Gate {r['gate']} — {_KIND_LABEL.get(str(kind or ''), kind)}{R}")
        if kind == "prompt_edit":
            diff, msg = _patch_prompt_edit(r, repo, getattr(args, "prompt_file", None),
                                           lineage)
        elif kind == "config_change":
            diff, msg = _patch_config_change(r, repo)
        else:
            print(f"{D}  data_fix — not patchable; re-check: "
                  f"{', '.join(r.get('evidence_task_ids') or []) or '—'}{R}")
            continue
        if msg:
            print(f"{D}  {msg}{R}")
        if diff:
            n_diff += 1
            if out_dir:
                fp = out_dir / f"{r['gate']}_{kind}.patch"
                fp.write_text(diff, encoding="utf-8")
                print(f"{G}  wrote {fp}{R}")
            else:
                print(diff)
    print(f"\n{D}{n_diff} diff(s) generated. Review and apply with "
          f"`git apply` — nothing was written to your sources.{R}")
    return 0


def _select_proposal(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """Match ``--proposal`` against ``<gate>`` or ``<gate>:<kind>`` / ``<gate>_<kind>``."""
    k = key.strip().lower()
    for r in rows:
        gate = str(r.get("gate") or "").lower()
        kind = str(r.get("kind") or "").lower()
        if k in (gate, f"{gate}:{kind}", f"{gate}_{kind}"):
            return r
    return None


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )


def _cmd_apply_verify(args: argparse.Namespace) -> int:
    """SPEC-043 REQ-7: apply one proposal's diff in an isolated git worktree, run
    the caller's eval command there, and score predicted-vs-actual. Never merges
    or commits — the human inspects the worktree and decides."""
    baseline = _load_result(args.result_file)
    if baseline is None:
        return 1
    repo = Path(getattr(args, "repo", ".") or ".").resolve()
    top = _git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        print(_err(f"{repo} is not a git repository (needed for an isolated worktree)."))
        return 1
    repo_root = Path(top.stdout.strip())

    ins = _insights(baseline, _load_result(getattr(args, "baseline", None)))
    rows = _proposals(ins, None)
    if not rows:
        print(f"{D}No proposals in {args.result_file} — nothing to apply.{R}")
        return 1
    row = _select_proposal(rows, args.proposal)
    if row is None:
        avail = ", ".join(
            f"{r['gate']}:{r.get('kind')}" for r in rows
        )
        print(_err(f"No proposal matches {args.proposal!r}. Available: {avail}"))
        return 1
    if row.get("kind") == "data_fix":
        print(_err("This proposal is a data / eval-set fix — not a code diff. "
                   "Apply it to your eval set manually, then `improve verify`."))
        return 1

    # 1. register the experiment so `score_experiments` has a prediction to check
    from agent_evaluator.rca.experiments import (
        register_experiment,
        resolve_experiment,
        score_experiments,
    )

    pd = row.get("predicted_delta")
    exp = register_experiment(
        args.log,
        target_gate=row["gate"],
        predicted_delta=float(pd) if isinstance(pd, (int, float)) else 0.05,
        target_field=row.get("target_field"),
        note=_exp_note(row),
        baseline_ref=args.result_file,
    )
    eid = exp["experiment_id"]
    print(_ok(f"Registered experiment {eid} (Gate {row['gate']})"))

    # 2. isolated worktree at HEAD
    worktree = Path(tempfile.mkdtemp(prefix="ae-improve-"))
    add = _git(repo_root, "worktree", "add", "--detach", str(worktree), "HEAD")
    if add.returncode != 0:
        print(_err(f"git worktree add failed: {add.stderr.strip()}"))
        shutil.rmtree(worktree, ignore_errors=True)
        return 1
    cleanup = not getattr(args, "keep_worktree", False)
    try:
        # 3. generate + apply the diff inside the worktree
        lineage = (baseline.get("extra_metrics") or {}).get("lineage") or {}
        if row.get("kind") == "prompt_edit":
            diff, msg = _patch_prompt_edit(
                row, worktree, getattr(args, "prompt_file", None), lineage,
            )
        else:
            diff, msg = _patch_config_change(row, worktree)
        if not diff:
            print(_err(f"Could not build a diff to apply: {msg or 'no change produced'}"))
            return 1
        patch_file = worktree / ".ae-improve.patch"
        patch_file.write_text(diff, encoding="utf-8")
        applied = _git(worktree, "apply", str(patch_file))
        if applied.returncode != 0:
            print(_err(f"git apply failed in the worktree: {applied.stderr.strip()}"))
            return 1
        patch_file.unlink(missing_ok=True)
        print(_ok(f"Applied the {row.get('kind')} diff in {worktree}"))

        # 4. run the caller's eval command there
        started = time.time()
        print(f"{D}$ {args.eval_cmd}   (cwd={worktree}){R}")
        proc = subprocess.run(
            args.eval_cmd, shell=True, cwd=str(worktree), check=False,
        )
        if proc.returncode != 0:
            print(f"{Y}⚠  eval command exited {proc.returncode} — scoring whatever "
                  f"result it produced.{R}")

        # 5. locate the new result JSON
        new_path = _locate_new_result(
            worktree, getattr(args, "new_result", None), started,
        )
        if new_path is None:
            print(_err("Could not find a result JSON produced by --eval-cmd. "
                       "Pass --new-result <path relative to the worktree>."))
            return 1
        new_result = _load_result(str(new_path))
        if new_result is None:
            return 1
        print(_ok(f"Scoring {new_path.relative_to(worktree)}"))

        # 6. score predicted vs actual
        scored = score_experiments(
            [exp], new_result, baseline, min_effect=getattr(args, "min_effect", 0.02),
        )
        srow = scored[0] if scored else {}
        verdict = srow.get("verdict", "inconclusive")
        act = srow.get("actual_delta")
        vc = _VERDICT_COLOR.get(verdict, "")
        print(f"\n{B}Gate {row['gate']}"
              + (f".{row['target_field']}" if row.get("target_field") else "")
              + f"  predicted {pd if isinstance(pd, (int, float)) else '~0.05'}  "
              + f"actual {(f'{act:+.3f}' if isinstance(act, (int, float)) else '-')}  "
              + f"{vc}{verdict}{R}")

        if getattr(args, "persist", False) and verdict in (
            "confirmed", "partially_confirmed", "refuted",
        ):
            resolve_experiment(
                args.log, eid, actual_delta=act, verdict=verdict,
                note=f"improve apply-verify vs {Path(args.result_file).name}",
            )
            _record_outcome(
                Path(args.result_file).parent / "recommendation_outcomes.jsonl",
                {**srow, "experiment_id": eid, "target_gate": row["gate"],
                 "target_field": row.get("target_field"),
                 "predicted_delta": exp.get("predicted_delta"), "verdict": verdict},
                args.result_file, baseline, new_result,
            )
            print(_ok(f"Resolved {eid}; appended a recommendation outcome"))
        else:
            print(f"{D}Experiment {eid} left open — pass --persist to resolve it.{R}")

        print(f"\n{B}Worktree:{R} {worktree}")
        print(f"{D}Nothing was merged or committed. Inspect it, then remove with{R}")
        print(f"{D}  git -C {repo_root} worktree remove --force {worktree}{R}")
        cleanup = cleanup and False  # keep it so the human can look
        return 0
    finally:
        if cleanup:
            _git(repo_root, "worktree", "remove", "--force", str(worktree))
            shutil.rmtree(worktree, ignore_errors=True)


def _locate_new_result(
    worktree: Path, hint: str | None, since: float,
) -> Path | None:
    if hint:
        p = Path(hint)
        if not p.is_absolute():
            p = worktree / hint
        return p if p.is_file() else None
    # No hint: only look under <worktree>/results/ for a JSON written during the
    # run — scanning the worktree root would pick up checked-out result files
    # (e.g. the baseline itself) that the eval command never touched.
    rdir = worktree / "results"
    if not rdir.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for fp in rdir.glob("*.json"):
        try:
            mt = fp.stat().st_mtime
        except OSError:
            continue
        if mt >= since - 1.0:
            candidates.append((mt, fp))
    if not candidates:
        return None
    return max(candidates, key=lambda t: t[0])[1]


def build_improve_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "improve",
        help="Closed improvement loop: plan / start / verify / patch proposals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Turn the insight layer's per-gate proposals into a tracked\n"
            "improvement workflow. `plan` shows them, `start` registers each as\n"
            "an experiment and writes an apply-me stub, `verify` scores the\n"
            "prediction once a new run exists, `patch` emits a unified diff,\n"
            "`apply-verify` runs the whole apply→eval→verify chain in an\n"
            "isolated git worktree (never merges).\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval improve plan results/v3.json --baseline results/v2.json\n"
            "  agent-eval improve start results/v3.json --yes\n"
            "  agent-eval improve verify results/v4.json --baseline results/v3.json "
            "--persist\n"
            "  agent-eval improve patch results/v3.json --repo .\n"
            "  agent-eval improve apply-verify results/v3.json --proposal A "
            "--eval-cmd 'python eval.py' --persist\n"
        ),
    )
    isub = p.add_subparsers(dest="improve_command",
                            metavar="{plan,start,verify,patch,apply-verify}")

    pl = isub.add_parser("plan", help="Show the ordered improvement plan")
    pl.add_argument("result_file", help="Evaluation result JSON to plan from")
    pl.add_argument("--baseline", default=None, metavar="PATH",
                    help="Prior result JSON (enables baseline-aware proposals)")
    pl.add_argument("--gate", default=None, metavar="X", help="Only this Gate (A-G)")
    pl.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")

    st = isub.add_parser("start", help="Register experiments + write change stubs")
    st.add_argument("result_file", help="Evaluation result JSON to act on")
    st.add_argument("--baseline", default=None, metavar="PATH", help="Prior result JSON")
    st.add_argument("--gate", default=None, metavar="X", help="Only this Gate (A-G)")
    st.add_argument("--out", default=_DEFAULT_OUT, metavar="DIR",
                    help=f"Where to write change stubs (default: {_DEFAULT_OUT})")
    st.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")
    st.add_argument("--yes", "-y", action="store_true", help="Actually write (no dry run)")

    vf = isub.add_parser("verify", help="Score open experiments against a new run")
    vf.add_argument("result_file", help="New evaluation result JSON")
    vf.add_argument("--baseline", required=True, metavar="PATH",
                    help="The result the change was made against")
    vf.add_argument("--persist", action="store_true",
                    help="Resolve experiments + append to recommendation_outcomes.jsonl")
    vf.add_argument("--min-effect", type=float, default=0.02, dest="min_effect",
                    metavar="D", help="|delta| below this is noise (default: 0.02)")
    vf.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")

    pt = isub.add_parser("patch", help="Emit a unified diff for each proposal (never applies)")
    pt.add_argument("result_file", help="Evaluation result JSON to patch from")
    pt.add_argument("--baseline", default=None, metavar="PATH", help="Prior result JSON")
    pt.add_argument("--gate", default=None, metavar="X", help="Only this Gate (A-G)")
    pt.add_argument("--repo", default=".", metavar="DIR",
                    help="Repo root to scan for @agent_eval decorators (default: .)")
    pt.add_argument("--prompt-file", default=None, metavar="PATH", dest="prompt_file",
                    help="System-prompt file for prompt_edit proposals "
                         "(overrides lineage.prompt_source_path)")
    pt.add_argument("--out", default=None, metavar="DIR",
                    help="Write <gate>_<kind>.patch files here instead of stdout")

    av = isub.add_parser(
        "apply-verify",
        help="Apply one proposal's diff in an isolated git worktree, run an eval, score it",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "The manual apply→re-run→verify chain in one command.\n"
            "Registers the proposal as an experiment, applies its diff to a fresh\n"
            "detached `git worktree` at HEAD, runs --eval-cmd there, finds the\n"
            "result JSON it wrote, and scores predicted-vs-actual. NEVER merges or\n"
            "commits — the worktree is left for you to inspect and remove.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval improve apply-verify results/v3.json --proposal A "
            "--eval-cmd 'python eval.py'\n"
            "  agent-eval improve apply-verify results/v3.json --proposal E:config_change "
            "--eval-cmd 'make eval' --new-result results/latest.json --persist\n"
        ),
    )
    av.add_argument("result_file", help="The result the proposal came from (= verify baseline)")
    av.add_argument("--proposal", required=True, metavar="ID",
                    help="Which proposal: <gate> or <gate>:<kind> (e.g. A, E:config_change)")
    av.add_argument("--eval-cmd", required=True, metavar="CMD", dest="eval_cmd",
                    help="Shell command to run in the worktree; it must write a result JSON")
    av.add_argument("--new-result", default=None, metavar="PATH", dest="new_result",
                    help="Where --eval-cmd writes the result JSON (rel to the worktree, "
                         "or absolute). Default: newest results/*.json it produced")
    av.add_argument("--repo", default=".", metavar="DIR", help="Repo root (default: .)")
    av.add_argument("--baseline", default=None, metavar="PATH",
                    help="Prior result JSON for baseline-aware proposal selection")
    av.add_argument("--prompt-file", default=None, metavar="PATH", dest="prompt_file",
                    help="System-prompt file for a prompt_edit proposal")
    av.add_argument("--persist", action="store_true",
                    help="Resolve the experiment + append a recommendation outcome")
    av.add_argument("--min-effect", type=float, default=0.02, dest="min_effect",
                    metavar="D", help="|delta| below this is noise (default: 0.02)")
    av.add_argument("--keep-worktree", action="store_true", dest="keep_worktree",
                    help="Also keep the worktree when an earlier step fails "
                         "(on success it is always kept)")
    av.add_argument("--log", default=_DEFAULT_LOG, metavar="PATH",
                    help=f"Experiments log (default: {_DEFAULT_LOG})")


def cmd_improve(args: argparse.Namespace) -> int:
    handlers = {"plan": _cmd_plan, "start": _cmd_start, "verify": _cmd_verify,
                "patch": _cmd_patch, "apply-verify": _cmd_apply_verify}
    cmd = getattr(args, "improve_command", None)
    handler = handlers.get(cmd) if cmd is not None else None
    if handler is None:
        print(_err("Specify: agent-eval improve {plan,start,verify,patch,apply-verify}"))
        print(f"{D}For details: agent-eval improve --help{R}")
        return 1
    return handler(args)
