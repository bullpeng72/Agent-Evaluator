"""알림 시스템 API — Phase 2-B."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# ---------------------------------------------------------------------------
# B8: 알림 규칙 CRUD — 인메모리 저장소 (프로세스 재시작 시 초기화)
# ---------------------------------------------------------------------------

class AlertRuleCreate(BaseModel):
    name: str
    condition_expr: str = ""   # 예: "accuracy_score < 0.7"
    severity: str = "warning"
    cooldown: float = 60.0
    enabled: bool = True
    description: Optional[str] = None  # noqa: UP045
    compound_conditions: Optional[List[Dict[str, Any]]] = None  # noqa: UP006,UP045  # B8: 복합 조건

# ---------------------------------------------------------------------------
# B7: 알림 규칙 저장소 — 메모리 캐시 + 파일 동기화
# ---------------------------------------------------------------------------
_ALERT_RULES_STORE: dict[str, dict[str, Any]] = {}


def _get_rules_file(request: Request) -> Path:
    """알림 규칙 파일 경로 반환."""
    results_dir = getattr(request.app.state, "results_dir", None)
    if results_dir is None:
        return Path("/tmp") / "agent_eval_alerts" / "rules.json"
    return Path(results_dir) / "alerts" / "rules.json"


def _load_rules(path: Path) -> dict[str, Any]:
    """파일에서 알림 규칙 로드. 파일이 없으면 {} 반환."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_rules(path: Path, rules: dict[str, Any]) -> None:
    """알림 규칙을 파일에 저장."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _alert_dir(request: Request) -> Path:
    results_dir = request.app.state.results_dir
    return Path(results_dir) / "alerts"

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return records

@router.get("", summary="Alert history list")
def list_alerts(request: Request, days: int = 7) -> List[Dict[str, Any]]:  # noqa: UP006
    """Recent N-day alert history."""
    alert_dir = _alert_dir(request)
    result = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        result.extend(_read_jsonl(alert_dir / f"{d}.jsonl"))
    return sorted(result, key=lambda x: x.get("triggered_at", ""), reverse=True)

@router.get("/today", summary="Today's alerts")
def today_alerts(request: Request) -> Dict[str, Any]:  # noqa: UP006
    """Summary of alerts fired today."""
    alert_dir = _alert_dir(request)
    today = date.today().isoformat()
    records = _read_jsonl(alert_dir / f"{today}.jsonl")

    by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for r in records:
        sev = r.get("severity", "unknown")
        rule = r.get("rule_name", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_rule[rule] = by_rule.get(rule, 0) + 1

    return {
        "date": today,
        "total": len(records),
        "critical": by_severity.get("critical", 0),
        "warning": by_severity.get("warning", 0),
        "by_rule": by_rule,
        "events": records,
    }

@router.get("/file/{file_id}", summary="Alerts for a result file")
def file_alerts(file_id: str, request: Request) -> Dict[str, Any]:  # noqa: UP006
    """Return alert history for the date corresponding to the selected result file.

    Extracts the date (YYYY-MM-DD) from the file's timestamp and reads the
    alerts/*.jsonl file for that date. Used to show the alert history for
    the day a specific result file was created.
    """
    rs = getattr(request.app.state, "result_set", None)
    if rs is None:
        return {"date": "", "total": 0, "critical": 0, "warning": 0, "by_rule": {}, "events": {},
                "summary": {"total_7d": 0, "critical_7d": 0, "warning_7d": 0}}

    rf = rs.by_id(file_id)
    if rf is None:
        return {"date": "", "total": 0, "critical": 0, "warning": 0, "by_rule": {}, "events": {},
                "summary": {"total_7d": 0, "critical_7d": 0, "warning_7d": 0}}

    # 파일 timestamp에서 날짜 추출 (ISO-8601: "2026-03-30T14:23:11" or "2026-03-30")
    date_str = (rf.timestamp or date.today().isoformat())[:10]

    alert_dir = _alert_dir(request)
    records = _read_jsonl(alert_dir / f"{date_str}.jsonl")

    by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for r in records:
        sev = r.get("severity", "unknown")
        rule = r.get("rule_name", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_rule[rule] = by_rule.get(rule, 0) + 1

    critical = by_severity.get("critical", 0)
    warning = by_severity.get("warning", 0)
    return {
        "date": date_str,
        "total": len(records),
        "critical": critical,
        "warning": warning,
        "by_rule": by_rule,
        "events": records,
        "summary": {"total_7d": len(records), "critical_7d": critical, "warning_7d": warning},
    }


@router.get("/patterns", summary="Alert pattern analysis")
def alert_patterns(request: Request, days: int = 7) -> Dict[str, Any]:  # noqa: UP006
    """Detect recurring patterns in the last N days of alerts by hour, weekday, and rule."""
    alert_dir = _alert_dir(request)
    all_records: list[dict[str, Any]] = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        all_records.extend(_read_jsonl(alert_dir / f"{d}.jsonl"))

    hourly: dict[int, int] = {h: 0 for h in range(24)}
    dow: dict[str, int] = {"Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0}
    _DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rule_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}

    for r in all_records:
        ts = r.get("triggered_at", "")
        try:
            dt = datetime.fromisoformat(ts)
            hourly[dt.hour] = hourly.get(dt.hour, 0) + 1
            dow[_DOW[dt.weekday()]] = dow.get(_DOW[dt.weekday()], 0) + 1
        except Exception:
            pass
        rule = r.get("rule_name", "unknown")
        rule_counts[rule] = rule_counts.get(rule, 0) + 1
        sev = r.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # 피크 시간대
    peak_hour = max(hourly, key=hourly.get) if hourly else 0
    top_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "period_days": days,
        "total_alerts": len(all_records),
        "hourly_distribution": hourly,
        "dow_distribution": dow,
        "severity_distribution": severity_counts,
        "rule_counts": rule_counts,
        "top_rules": [{"rule": r, "count": c} for r, c in top_rules],
        "peak_hour": peak_hour,
        "peak_dow": max(dow, key=dow.get) if any(dow.values()) else None,
    }


@router.get("/rules", summary="Alert rules list")
def list_alert_rules(request: Request) -> Dict[str, Any]:  # noqa: UP006
    """List alert rules (B7/B8) — file-based persistent storage."""
    rules_file = _get_rules_file(request)
    rules = _load_rules(rules_file)
    # 메모리 캐시 동기화
    _ALERT_RULES_STORE.clear()
    _ALERT_RULES_STORE.update(rules)
    return {"total": len(rules), "rules": list(rules.values())}


@router.post("/rules", summary="Create alert rule")
def create_alert_rule(body: AlertRuleCreate, request: Request) -> Dict[str, Any]:  # noqa: UP006
    """Create alert rule (B7/B8) — file-based persistent storage + compound_conditions support.

    Example body::

        {
            "name": "slow_response",
            "condition_expr": "execution_time > 5.0",
            "severity": "warning",
            "cooldown": 60.0,
            "compound_conditions": [
                {"field": "accuracy_score", "op": "lt", "value": 0.7},
                {"field": "execution_time", "op": "gt", "value": 5.0}
            ]
        }
    """
    import uuid as _uuid
    rules_file = _get_rules_file(request)
    rules = _load_rules(rules_file)
    _ALERT_RULES_STORE.update(rules)

    rule_id = _uuid.uuid4().hex[:8]
    rule: dict[str, Any] = {
        "rule_id":        rule_id,
        "name":           body.name,
        "condition_expr": body.condition_expr,
        "severity":       body.severity,
        "cooldown":       body.cooldown,
        "enabled":        body.enabled,
        "description":    body.description,
        "created_at":     datetime.now().isoformat(),
    }
    # B8: compound 조건
    if body.compound_conditions is not None:
        rule["compound_conditions"] = body.compound_conditions

    rules[rule_id] = rule
    _ALERT_RULES_STORE[rule_id] = rule
    _save_rules(rules_file, rules)
    return rule


@router.get("/rules/{rule_id}", summary="Alert rule detail")
def get_alert_rule(rule_id: str, request: Request) -> Dict[str, Any]:  # noqa: UP006
    """Get a single alert rule (B7/B8) — retrieved from file."""
    rules_file = _get_rules_file(request)
    rules = _load_rules(rules_file)
    rule = rules.get(rule_id) or _ALERT_RULES_STORE.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return rule


@router.delete("/rules/{rule_id}", summary="Delete alert rule")
def delete_alert_rule(rule_id: str, request: Request) -> Dict[str, Any]:  # noqa: UP006
    """Delete an alert rule (B7/B8) — removed from file as well."""
    rules_file = _get_rules_file(request)
    rules = _load_rules(rules_file)
    rule = rules.pop(rule_id, None) or _ALERT_RULES_STORE.pop(rule_id, None)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    # 파일 업데이트
    if rule_id in rules:
        rules.pop(rule_id, None)
    _save_rules(rules_file, rules)
    _ALERT_RULES_STORE.pop(rule_id, None)
    return {"deleted": True, "rule_id": rule_id, "name": rule.get("name")}


@router.get("/summary", summary="Alert summary")
def alert_summary(request: Request) -> Dict[str, Any]:  # noqa: UP006
    """7-day alert statistics summary."""
    alert_dir = _alert_dir(request)
    daily_counts: dict[str, int] = {}
    total_critical = total_warning = 0

    for i in range(7):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        records = _read_jsonl(alert_dir / f"{d}.jsonl")
        daily_counts[d] = len(records)
        total_critical += sum(1 for r in records if r.get("severity") == "critical")
        total_warning += sum(1 for r in records if r.get("severity") == "warning")

    return {
        "total_7d": sum(daily_counts.values()),
        "critical_7d": total_critical,
        "warning_7d": total_warning,
        "daily_counts": daily_counts,
    }
