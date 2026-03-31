"""알림 시스템 API — Phase 2-B."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

def _alert_dir(request: Request) -> Path:
    results_dir = request.app.state.results_dir
    return Path(results_dir) / "alerts"

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
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

@router.get("")
def list_alerts(request: Request, days: int = 7) -> List[Dict[str, Any]]:
    """최근 N일 알림 히스토리."""
    alert_dir = _alert_dir(request)
    result = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        result.extend(_read_jsonl(alert_dir / f"{d}.jsonl"))
    return sorted(result, key=lambda x: x.get("triggered_at", ""), reverse=True)

@router.get("/today")
def today_alerts(request: Request) -> Dict[str, Any]:
    """오늘 발화된 알림 요약."""
    alert_dir = _alert_dir(request)
    today = date.today().isoformat()
    records = _read_jsonl(alert_dir / f"{today}.jsonl")

    by_severity: Dict[str, int] = {}
    by_rule: Dict[str, int] = {}
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

@router.get("/file/{file_id}")
def file_alerts(file_id: str, request: Request) -> Dict[str, Any]:
    """선택된 결과 파일 날짜에 해당하는 알림 히스토리 반환.

    파일의 timestamp에서 날짜(YYYY-MM-DD)를 추출하여 해당 날짜의
    alerts/*.jsonl 파일을 읽는다. 대시보드에서 특정 결과 파일을 선택하면
    그 파일이 생성된 날의 알림 이력을 표시하는 데 사용된다.
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

    by_severity: Dict[str, int] = {}
    by_rule: Dict[str, int] = {}
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


@router.get("/summary")
def alert_summary(request: Request) -> Dict[str, Any]:
    """7일 알림 통계 요약."""
    alert_dir = _alert_dir(request)
    daily_counts: Dict[str, int] = {}
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
