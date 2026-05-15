"""Evaluation cost API — Phase 3-C."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, Request

from agent_evaluator.serve.routers._utils import _rs

router = APIRouter(prefix="/api/cost", tags=["cost"])

@router.get("/summary", summary="Cost summary")
def cost_summary(request: Request) -> Dict[str, Any]:
    """Overall evaluation cost summary."""
    rs = _rs(request)
    total_usd = 0.0
    by_file: List[Dict[str, Any]] = []

    for f in rs.files:
        cost_data = getattr(f, "cost_data", {})
        file_total = cost_data.get("total_usd", 0.0)
        total_usd += file_total
        if cost_data:
            by_file.append({
                "file_id": f.file_id,
                "file_name": f.name,
                "total_usd": round(file_total, 6),
                **{k: v for k, v in cost_data.items() if k != "total_usd"},
            })

    return {
        "total_usd": round(total_usd, 6),
        "file_count": len(rs.files),
        "by_file": by_file,
    }

@router.get("/trend", summary="Cost trend by date")
def cost_trend(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    """Cost trend by date — aggregates per-file costs into daily buckets over the last N days.

    Returns:
        period_days, buckets (date list), values (total cost USD per date),
        cumulative (running total), by_file (per-file detail)
    """
    rs = _rs(request)
    since = datetime.now() - timedelta(days=days)

    # Initialize date buckets
    bucket_costs: Dict[str, float] = {}
    by_file: List[Dict[str, Any]] = []

    for f in rs.files:
        ts_raw = getattr(f, "timestamp", None) or ""
        try:
            ts = datetime.fromisoformat(str(ts_raw)[:19])
        except Exception:
            ts = None

        if ts is not None and ts < since:
            continue

        cost_data = getattr(f, "cost_data", {}) or {}
        file_cost = float(cost_data.get("total_usd", 0.0) or 0.0)
        date_key = ts.strftime("%Y-%m-%d") if ts else "unknown"
        bucket_costs[date_key] = bucket_costs.get(date_key, 0.0) + file_cost
        by_file.append({
            "file_id": f.file_id,
            "name": f.name,
            "date": date_key,
            "cost_usd": round(file_cost, 6),
        })

    # Sort by date
    buckets = sorted(bucket_costs.keys())
    values = [round(bucket_costs[b], 6) for b in buckets]
    cumulative: List[float] = []
    running = 0.0
    for v in values:
        running += v
        cumulative.append(round(running, 6))

    return {
        "period_days": days,
        "total_usd": round(sum(values), 6),
        "buckets": buckets,
        "values": values,
        "cumulative": cumulative,
        "by_file": sorted(by_file, key=lambda x: x["date"]),
    }


@router.get("/breakdown", summary="Cost breakdown")
def cost_breakdown(
    request: Request,
    by: str = Query(default="model", description="Grouping key: model|task_type|file"),
) -> Dict[str, Any]:
    """Cost breakdown — grouped by the specified key.

    Returns:
        by, groups (key → total_usd/task_count/avg_cost_per_task/total_tokens)
    """
    rs = _rs(request)
    groups: dict = {}

    for f in rs.files:
        cost_data = getattr(f, "cost_data", {}) or {}
        file_total = float(cost_data.get("total_usd", 0.0) or 0.0)

        if by == "file":
            key = f.name or f.file_id
            if key not in groups:
                groups[key] = {"total_usd": 0.0, "task_count": 0, "total_tokens": 0}
            groups[key]["total_usd"] += file_total
            groups[key]["task_count"] += f.total_tasks
            # tokens from efficiency_metrics
            tok = (f.efficiency_metrics or {}).get("tokens", {})
            groups[key]["total_tokens"] += int(tok.get("total_tokens", 0) or 0)
        else:
            # task-level grouping
            tasks = getattr(f, "tasks", []) or []
            for t in tasks:
                if by == "model":
                    tok_info = getattr(t, "tokens_used", {}) or {}
                    key = str(tok_info.get("model", "unknown") or "unknown")
                elif by == "task_type":
                    key = str(getattr(t, "task_type", "unknown") or "unknown")
                else:
                    key = str(getattr(t, by, "unknown") or "unknown")

                if key not in groups:
                    groups[key] = {"total_usd": 0.0, "task_count": 0, "total_tokens": 0}
                # Per-task cost estimation: divide file_total evenly if no per-task cost
                task_cost = 0.0
                adv = getattr(t, "advanced_metrics", {}) or {}
                if "cost_usd" in adv:
                    task_cost = float(adv["cost_usd"] or 0.0)
                elif f.total_tasks > 0:
                    task_cost = file_total / f.total_tasks

                tok_info = getattr(t, "tokens_used", {}) or {}
                total_tok = int(
                    tok_info.get("total", tok_info.get("input", 0) + tok_info.get("output", 0))
                )
                groups[key]["total_usd"] += task_cost
                groups[key]["task_count"] += 1
                groups[key]["total_tokens"] += total_tok

    # Final format: compute avg_cost_per_task + round
    result_groups = {}
    for key, g in groups.items():
        count = g["task_count"]
        result_groups[key] = {
            "total_usd": round(g["total_usd"], 6),
            "task_count": count,
            "avg_cost_per_task": round(g["total_usd"] / count, 8) if count else 0.0,
            "total_tokens": g["total_tokens"],
        }

    return {
        "by": by,
        "total_usd": round(sum(g["total_usd"] for g in result_groups.values()), 6),
        "groups": result_groups,
    }


@router.get("/{file_id}", summary="Cost detail for a file")
def get_file_cost(file_id: str, request: Request) -> Dict[str, Any]:
    """Cost detail for a specific file."""
    rs = _rs(request)
    rf = rs.by_id(file_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="File not found")
    cost_data = getattr(rf, "cost_data", {})
    return {"file_id": file_id, **cost_data}
