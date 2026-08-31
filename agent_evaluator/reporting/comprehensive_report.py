"""
Comprehensive HTML Report Generator for Agent Evaluator
Harness Gate A–G 중심 구조 (v0.8.2+)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Utility: markdown → html
# ---------------------------------------------------------------------------

def markdown_to_html(text: str) -> str:
    """Convert simple markdown formatting to HTML with support for nested lists"""
    if not text:
        return ""

    # Escape HTML special characters first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Remove colon immediately after </strong> tag for better readability
    text = re.sub(r'</strong>:', '</strong>', text)

    # Process line by line
    lines = text.split('\n')
    in_numbered_list = False
    in_bullet_list = False
    result_lines = []

    for _i, line in enumerate(lines):
        stripped = line.strip()

        # Check for numbered list item (1. 2. 3.)
        if re.match(r'^\d+\.\s+', stripped):
            if in_bullet_list:
                result_lines.append('</ul>')
                in_bullet_list = False
            if in_numbered_list:
                result_lines.append('</li>')
            if not in_numbered_list:
                result_lines.append('<ol style="margin: 10px 0 10px 20px; line-height: 2.0;">')
                in_numbered_list = True
            content = re.sub(r'^\d+\.\s+', '', stripped)
            content = re.sub(r':$', '', content)
            result_lines.append(f'<li>{content}')

        elif re.match(r'^\s*[-•]\s*', line) and re.sub(r'^\s*[-•]\s*', '', line).strip():
            content = re.sub(r'^\s*[-•]\s*', '', line.strip())
            if in_numbered_list:
                if not in_bullet_list:
                    result_lines.append('<ul style="margin: 5px 0 5px 20px; line-height: 1.8;">')
                    in_bullet_list = True
            else:
                if not in_bullet_list:
                    result_lines.append('<ul style="margin: 10px 0 10px 20px; line-height: 2.0;">')
                    in_bullet_list = True
            result_lines.append(f'<li>{content}</li>')

        else:
            if stripped:
                if in_numbered_list and not in_bullet_list:
                    if line.startswith('   ') or line.startswith('\t'):
                        result_lines.append(f'<br>{stripped}')
                    else:
                        if in_bullet_list:
                            result_lines.append('</ul>')
                            in_bullet_list = False
                        if in_numbered_list:
                            result_lines.append('</li>')
                            result_lines.append('</ol>')
                            in_numbered_list = False
                        result_lines.append(f'<p style="margin: 10px 0; line-height: 1.8;">{stripped}</p>')
                else:
                    if in_bullet_list:
                        result_lines.append('</ul>')
                        in_bullet_list = False
                    if in_numbered_list:
                        result_lines.append('</li>')
                        result_lines.append('</ol>')
                        in_numbered_list = False
                    result_lines.append(f'<p style="margin: 10px 0; line-height: 1.8;">{stripped}</p>')
            else:
                if not in_numbered_list and not in_bullet_list:
                    result_lines.append('<br>')

    if in_bullet_list:
        result_lines.append('</ul>')
    if in_numbered_list:
        result_lines.append('</li>')
        result_lines.append('</ol>')

    return '\n'.join(result_lines)


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

_GATE_COLORS: dict[str, str] = {
    "A": "#10b981",  # emerald
    "B": "#3b82f6",  # blue
    "C": "#f59e0b",  # amber
    "D": "#0ea5e9",  # sky
    "E": "#ef4444",  # red
    "F": "#8b5cf6",  # purple
    "G": "#06b6d4",  # cyan
}

_GATE_NAMES: dict[str, str] = {
    "A": "Goal Achievement",
    "B": "Behavioral Integrity",
    "C": "Reliability",
    "D": "Performance Contract",
    "E": "Security Boundary",
    "F": "Multi-Agent Coordination",
    "G": "Observability",
}

_STATUS_COLORS = {"pass": "#10b981", "warn": "#f59e0b", "fail": "#ef4444"}
_STATUS_LABELS = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def _gate_badge(gate: str) -> str:
    """PASS/WARN/FAIL 배지 HTML 반환."""
    gate = (gate or "").lower()
    color = _STATUS_COLORS.get(gate, "#9ca3af")
    label = _STATUS_LABELS.get(gate, gate.upper() if gate else "—")
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'font-size:11px;font-weight:700;background:{color}22;color:{color};'
        f'border:1px solid {color}66">{label}</span>'
    )


def _gate_score_bar(score: float, gate_key: str) -> str:
    """게이트 색상으로 진행바 + 퍼센트 텍스트 반환."""
    color = _GATE_COLORS.get(gate_key, "#6b7280")
    pct = min(max(float(score or 0) * 100, 0), 100)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<div style="flex:1;height:8px;background:#e5e7eb;border-radius:4px">'
        f'<div style="height:8px;width:{pct:.1f}%;background:{color};border-radius:4px"></div>'
        f'</div>'
        f'<span style="font-size:12px;font-weight:600;color:{color};min-width:40px">{pct:.1f}%</span>'
        f'</div>'
    )


def _metric_row(label: str, value: Any, hint: str = "",
                good_thresh: float = 0.8, warn_thresh: float = 0.6) -> str:
    """지표 1행: 라벨 | 값(색상 자동) | 힌트 텍스트."""
    if value is None:
        val_str = "—"
        color = "#9ca3af"
    else:
        try:
            fv = float(value)
            if fv >= good_thresh:
                color = "#10b981"
            elif fv >= warn_thresh:
                color = "#f59e0b"
            else:
                color = "#ef4444"
            # Format: if 0-1 range show as percent, else as-is
            if 0 <= fv <= 1:
                val_str = f"{fv * 100:.1f}%"
            else:
                val_str = f"{fv:.2f}"
        except (TypeError, ValueError):
            val_str = str(value)
            color = "#374151"
    hint_html = f'<span style="font-size:11px;color:#6b7280;margin-left:6px">{hint}</span>' if hint else ""
    return (
        f'<tr>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #f3f4f6;color:#374151">{label}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #f3f4f6;font-weight:600;color:{color}">'
        f'{val_str}{hint_html}</td>'
        f'</tr>'
    )


def _pct(v: Any, scale: float = 1.0) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v) * scale:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _num(v: Any, fmt: str = ".2f") -> str:
    if v is None:
        return "—"
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return "—"


def _count_noun(n: Any, singular: str, plural: str | None = None) -> str:
    """'1 threat' / '2 threats' — avoids the '1 threats' in count columns."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def _fmt_usd(v: Any) -> str:
    """Human-readable USD. Sub-cent values keep significant digits; larger values
    get a thousands separator and 2 decimals (so a scale projection reads as
    ``$1,267.50``, not ``$1267.5000``)."""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "—"
    if fv == 0:
        return "$0"
    neg = "-" if fv < 0 else ""
    fv = abs(fv)
    if fv < 0.01:
        return neg + "$" + f"{fv:.6f}".rstrip("0").rstrip(".")
    if fv < 1.0:
        return neg + "$" + f"{fv:.4f}".rstrip("0").rstrip(".")
    if fv < 100.0:
        return neg + f"${fv:,.2f}"
    return neg + f"${fv:,.0f}"


def _score_color(v: Any, hi: float = 70.0, lo: float = 50.0) -> str:
    if v is None:
        return "#9ca3af"
    try:
        fv = float(v)
        if fv >= hi:
            return "#10b981"
        if fv >= lo:
            return "#f59e0b"
        return "#ef4444"
    except (TypeError, ValueError):
        return "#9ca3af"


# ---------------------------------------------------------------------------
# CSS / Head
# ---------------------------------------------------------------------------

def _build_css() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Evaluator — Harness Gate Report</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6;background:#f5f6fa;color:#1e2030}
.container{max-width:1300px;margin:0 auto;background:#fff;padding:36px}

/* Header */
.rpt-header{background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:#fff;padding:36px;border-radius:12px;margin-bottom:32px}
.rpt-header h1{font-size:28px;margin-bottom:6px}
.rpt-header .sub{font-size:13px;opacity:.8;margin-top:8px}
.rpt-header .meta{margin-top:12px;font-size:13px;opacity:.9;display:flex;gap:24px;flex-wrap:wrap}

/* Scorecard */
.scorecard{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px;margin-bottom:36px}
.sc-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;border-top:4px solid #e5e7eb}
.sc-card .sc-gate{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6b7280;margin-bottom:4px}
.sc-card .sc-name{font-size:12px;color:#374151;margin-bottom:8px}
.sc-card .sc-badge{margin-bottom:8px}

/* Gate sections */
.gate-section{margin-bottom:32px;padding:24px;background:#f8fafc;border-radius:10px;border-left:5px solid #e5e7eb}
.gate-section h2{font-size:18px;color:#1e2030;margin-bottom:16px;display:flex;align-items:center;gap:10px}
.gate-section h3{font-size:14px;font-weight:600;color:#374151;margin:18px 0 8px;padding-bottom:6px;border-bottom:1px solid #e5e7eb}

/* KPI grid */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin:12px 0}
.kpi{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px}
.kpi-lbl{font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.3px}
.kpi-val{font-size:20px;font-weight:800;margin:3px 0;color:#1e2030}

/* Metric table */
.mtable{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);margin:10px 0}
.mtable th{background:#f1f5f9;padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase}
.mtable td{padding:7px 12px;border-bottom:1px solid #f3f4f6;font-size:13px}
.mtable tr:last-child td{border-bottom:none}
.mtable tr:hover td{background:#f8fafc}

/* Harness detail table */
.htable{width:100%;border-collapse:collapse;margin:8px 0}
.htable td{padding:5px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;color:#374151}
.htable tr:last-child td{border-bottom:none}

/* Inactive banner (Harness Config not active) */
.inactive-banner{background:#f9fafb;border:1px dashed #d1d5db;border-radius:8px;padding:12px 16px;font-size:12px;color:#9ca3af;margin:8px 0}
/* Not-tested banner (data not collected) */
.not-tested{background:#fafafa;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;font-size:12px;color:#6b7280;margin:8px 0;display:flex;align-items:flex-start;gap:8px}
.not-tested strong{color:#374151;white-space:nowrap}

/* Insight boxes */
.ibox{background:#fff;padding:14px;margin:10px 0;border-radius:8px;border-left:4px solid #3b82f6}
.ibox.ok{border-left-color:#10b981;background:#f0fdf4}
.ibox.warn{border-left-color:#f59e0b;background:#fffbeb}
.ibox.fail{border-left-color:#ef4444;background:#fef2f2}

/* Recommendation */
.rec{background:#fff;padding:16px;margin:10px 0;border-radius:8px;border-left:4px solid #6366f1;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.rec strong{display:block;margin-bottom:6px;color:#4f46e5;font-size:14px}
.rec p{color:#555;font-size:13px;line-height:1.7}

.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.badge-ok{background:#d1fae5;color:#065f46}
.badge-warn{background:#fef3c7;color:#92400e}
.badge-fail{background:#fee2e2;color:#991b1b}

.footer{margin-top:48px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#9ca3af;font-size:12px}

@media print{.container{padding:16px}.gate-section{break-inside:avoid}}

/* Score Breakdown */
.score-breakdown{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin:0 0 18px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.bd-header{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.bd-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;white-space:nowrap}
.bd-formula{font-size:11px;color:#475569;font-family:monospace;background:#f1f5f9;padding:2px 8px;border-radius:4px;overflow-x:auto;white-space:nowrap;max-width:100%}
.bd-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}
.bd-table th{background:#f8fafc;padding:5px 10px;text-align:left;font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;border-bottom:1px solid #e2e8f0}
.bd-table td{padding:5px 10px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
.bd-table tr:last-child td{border-bottom:none}
.bd-ok>td:first-child::before{content:'✓ ';color:#10b981;font-weight:700}
.bd-na>td{color:#9ca3af!important;font-style:italic}
.bd-na>td:first-child::before{content:'— ';color:#cbd5e1}
.bd-contrib{font-weight:600;font-family:monospace;font-size:12px}
.bd-always{font-size:10px;color:#6b7280;font-style:italic}
.bd-result{font-size:12px;color:#374151;background:#f8fafc;border-radius:6px;padding:8px 14px;border-left:3px solid #94a3b8;margin-top:2px}
.bd-result strong{font-size:15px;font-weight:800}
</style>
</head>
<body>
<div class="container">'''


# ---------------------------------------------------------------------------
# Not-tested notice helper
# ---------------------------------------------------------------------------

# P4.2: "측정 안 됨"을 3가지로 구분한다 — 설정을 안 한 것(config)인지, 설정은 했는데
# 샘플이 부족한 것(data)인지, 이 에이전트 유형엔 애초에 해당 없는 것(n/a)인지에 따라
# 사용자가 취할 행동이 다르다("Config를 켜라" vs "더 돌려라" vs "무시해도 됨").
_MEASURE_LABEL = {
    "config": ("⚙️", "Not Configured"),
    "data": ("📉", "Insufficient Data"),
    "n/a": ("➖", "Not Applicable"),
    "generic": ("🔍", "Not Measured"),
}


def _not_tested(reason: str = "", kind: str = "generic") -> str:
    """데이터가 수집되지 않은 섹션에 표시하는 배너.

    Args:
        reason: 배너 본문.
        kind: ``"config"``(설정 안 함) / ``"data"``(샘플 부족) / ``"n/a"``(해당 없음)
            / ``"generic"``(기본). 라벨과 아이콘을 바꾼다.
    """
    icon, label = _MEASURE_LABEL.get(kind, _MEASURE_LABEL["generic"])
    msg = reason or "This item has not been tested."
    return f'<div class="not-tested">{icon} <strong>{label}</strong>&nbsp;{msg}</div>'


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def _build_scorecard(harness_groups: dict[str, Any]) -> str:
    cards = []
    for key in "ABCDEFG":
        color = _GATE_COLORS[key]
        name = _GATE_NAMES[key]
        gdata = harness_groups.get(key, {})
        if isinstance(gdata, dict):
            score = gdata.get("score")
            gate_status = (gdata.get("gate") or gdata.get("status") or "").lower()
        else:
            score = None
            gate_status = ""
        badge_html = _gate_badge(gate_status) if gate_status else '<span style="font-size:11px;color:#9ca3af">Not Set</span>'
        bar_html = _gate_score_bar(score, key) if score is not None else ""
        cards.append(
            f'<div class="sc-card" style="border-top-color:{color}">'
            f'<div class="sc-gate" style="color:{color}">Gate {key}</div>'
            f'<div class="sc-name">{name}</div>'
            f'<div class="sc-badge">{badge_html}</div>'
            f'{bar_html}'
            f'</div>'
        )
    return '<div class="scorecard">' + ''.join(cards) + '</div>'


# ---------------------------------------------------------------------------
# Score Breakdown widget
# ---------------------------------------------------------------------------

def _bd_row(label: str, raw_str: str | None, contrib: float | None,
            always: bool = False, note: str = "") -> str:
    """Single row for the score breakdown table."""
    if contrib is None:
        reason = note or "Not measured"
        return (
            f'<tr class="bd-na">'
            f'<td>{label}</td>'
            f'<td>—</td>'
            f'<td class="bd-contrib">—</td>'
            f'<td style="font-size:10px">{reason}</td>'
            f'</tr>'
        )
    c_pct = f"{contrib * 100:.1f}%"
    c_col = "#10b981" if contrib >= 0.8 else ("#f59e0b" if contrib >= 0.6 else "#ef4444")
    always_tag = '<span class="bd-always">(always)</span>' if always else ""
    note_cell = f'<td style="font-size:10px;color:#6b7280">{note}</td>' if note else "<td></td>"
    return (
        f'<tr class="bd-ok">'
        f'<td>{label} {always_tag}</td>'
        f'<td style="font-family:monospace;color:#374151">{raw_str}</td>'
        f'<td class="bd-contrib" style="color:{c_col}">{c_pct}</td>'
        f'{note_cell}'
        f'</tr>'
    )


def _build_score_breakdown(gate_key: str, harness_group: dict) -> str:
    """Build a score computation breakdown widget for a Gate detail section."""
    if not harness_group:
        return ""
    score = harness_group.get("score")
    if score is None:
        return ""
    details = harness_group.get("details") or {}

    rows: list = []
    formula_parts: list = []
    included_vals: list = []

    def _add(label: str, raw_str: str | None, contrib: float | None,
              formula_label: str = "", always: bool = False, note: str = "",
              in_avg: bool = True) -> None:
        formula_parts.append(formula_label or label)
        rows.append(_bd_row(label, raw_str, contrib, always=always, note=note))
        if contrib is not None and in_avg:
            included_vals.append(contrib)

    def _fmt_ratio(v: Any) -> str | None:
        if v is None:
            return None
        try:
            return f"{float(v):.3f}"
        except (TypeError, ValueError):
            return None

    def _fmt_pct(v: Any, scale: float = 1.0) -> str | None:
        if v is None:
            return None
        try:
            return f"{float(v) * scale:.1f}%"
        except (TypeError, ValueError):
            return None

    if gate_key == "A":
        tcr = details.get("tcr_pct")
        c = tcr / 100.0 if tcr is not None else None
        _add("Task Completion Rate (TCR)", _fmt_pct(tcr), c,
             formula_label="TCR/100", always=True)
        for dk, lbl, fl in [
            ("avg_instruction_adherence", "Instruction Adherence (IFR)", "avg_IFR"),
            ("avg_goal_alignment", "Goal Alignment", "avg_goal_alignment"),
            ("avg_plan_coherence", "Plan Coherence", "avg_plan_coherence"),
            ("avg_subtask_completion", "Subtask Completion", "avg_subtask_completion"),
            ("avg_context_retention", "Context Retention", "avg_context_retention"),
            ("avg_knowledge_retention", "Knowledge Retention", "avg_knowledge_retention"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl,
                 note="Requires InstructionConfig" if dk == "avg_instruction_adherence" and v is None else "")
        acc_a = details.get("avg_accuracy")
        if acc_a is not None:
            _add("Accuracy Score (AccuracyEvaluator)", _fmt_ratio(acc_a), acc_a,
                 formula_label="avg_accuracy",
                 note="blended into the TCR component (0.6×TCR + 0.4×accuracy)")
        else:
            _add("Accuracy Score (AccuracyEvaluator)", None, None,
                 formula_label="avg_accuracy",
                 note="No accuracy evaluations recorded")
        qrc_a = details.get("avg_quality_relevance_completeness")
        if qrc_a is not None:
            _add("Response Relevance/Completeness", _fmt_ratio(qrc_a), qrc_a,
                 formula_label="avg_quality_relevance_completeness")
        formula_str = "gate_a_tcr_weight × (0.6×TCR + 0.4×accuracy) + (1 − weight) × avg( avg_IFR, avg_goal_alignment, avg_plan_coherence, avg_subtask_completion, avg_context_retention, avg_knowledge_retention, avg_quality_relevance_completeness )"

    elif gate_key == "B":
        loop = details.get("loop_detection_rate")
        c_loop = (1.0 - float(loop)) if loop is not None else 1.0
        _add("Loop Prevention (1 − loop_rate)", _fmt_ratio(c_loop), c_loop,
             formula_label="1−loop_rate", always=True)
        deadlock_count = details.get("deadlock_count", 0) or 0
        dl_score = details.get("avg_deadlock_score")
        if deadlock_count > 0 and dl_score is not None:
            _add("Deadlock Defense", _fmt_ratio(dl_score), dl_score,
                 formula_label="avg_deadlock_score",
                 note=f"{deadlock_count} deadlock(s) detected")
        else:
            _add("Deadlock Defense", _fmt_ratio(dl_score),
                 None if deadlock_count == 0 else dl_score,
                 formula_label="avg_deadlock_score",
                 note="No deadlocks → not included in avg")
        for dk, lbl, fl in [
            ("avg_goal_alignment", "Goal Alignment", "avg_goal_alignment"),
            ("avg_plan_coherence", "Plan Coherence", "avg_plan_coherence"),
            ("avg_state_consistency", "State Consistency", "avg_state_consistency"),
            ("avg_scope_score", "Scope Compliance", "avg_scope_score"),
            ("avg_tool_parameter_safety", "Tool Parameter Safety", "avg_tool_param_safety"),
            ("avg_context_window", "Context Window Efficiency", "avg_context_window"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl)
        formula_str = "avg( 1−loop_rate, [deadlock_score if detected], avg_goal_alignment, avg_plan_coherence, avg_state_consistency, avg_scope_score, avg_tool_param_safety, avg_context_window )"

    elif gate_key == "C":
        tcr = details.get("tcr_pct")
        c = tcr / 100.0 if tcr is not None else None
        _add("Task Completion Rate (TCR)", _fmt_pct(tcr), c,
             formula_label="TCR/100", always=True)
        slabr = details.get("sla_breach_rate")
        c_sla = (1.0 - float(slabr)) if slabr is not None else None
        _add("SLA Compliance (1 − breach_rate)", _fmt_ratio(c_sla), c_sla,
             formula_label="1−sla_breach_rate",
             note="Requires SLAConfig" if slabr is None else "")
        for dk, lbl, fl in [
            ("avg_fault_tolerance", "Fault Tolerance", "avg_fault_tolerance"),
            ("avg_reproducibility", "Reproducibility", "avg_reproducibility"),
            ("avg_degradation", "Graceful Degradation", "avg_degradation"),
            ("avg_retry_consistency", "Retry Consistency", "avg_retry_consistency"),
            ("avg_idempotency", "Idempotency", "avg_idempotency"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl)
        llm_faith_c = details.get("avg_llm_faithfulness")
        hall_c = details.get("hallucination_rate")
        if llm_faith_c is not None:
            # LLM Judge faithfulness 우선 사용 (0–5 → /5 정규화)
            c_faith_c = max(0.0, min(1.0, float(llm_faith_c) / 5.0))
            _add("LLM Faithfulness (faith/5) ★", f"{float(llm_faith_c):.2f}/5", c_faith_c,
                 formula_label="avg_llm_faithfulness/5")
            _c_rest = "1−sla_breach_rate, avg_fault_tolerance, avg_reproducibility, avg_degradation, avg_retry_consistency, avg_idempotency, avg_llm_faithfulness/5"
        elif hall_c is not None:
            c_hall_c = max(0.0, 1.0 - float(hall_c))
            _add("Hallucination Faithfulness (1 − rate)", _fmt_pct(hall_c, scale=100.0), c_hall_c,
                 formula_label="1−hallucination_rate")
            _c_rest = "1−sla_breach_rate, avg_fault_tolerance, avg_reproducibility, avg_degradation, avg_retry_consistency, avg_idempotency, 1−hallucination_rate"
        else:
            _add("Faithfulness", None, None,
                 formula_label="llm_faithfulness/5 or 1−hallucination_rate",
                 note="Requires LLMJudgeConfig or enable_hallucination_detection=True")
            _c_rest = "1−sla_breach_rate, avg_fault_tolerance, avg_reproducibility, avg_degradation, avg_retry_consistency, avg_idempotency, [faithfulness]"
        formula_str = f"gate_c_tcr_weight × TCR/100 + (1 − weight) × avg( {_c_rest} )"

    elif gate_key == "D":
        p95 = details.get("p95_latency_s")
        try:
            p95f = float(p95) if p95 is not None else None
        except (TypeError, ValueError):
            p95f = None
        if p95f is not None and p95f > 0:
            c_p95 = max(0.0, 1.0 - min(1.0, p95f / 10.0))
            _add("P95 Latency Score (1 − P95/10s)", f"{p95f:.3f}s", c_p95,
                 formula_label="1−P95/10s", always=True,
                 note="10s baseline ceiling")
        else:
            _add("P95 Latency Score (1 − P95/10s)", "0.000s", None,
                 formula_label="1−P95/10s",
                 note="No latency data")
        eff = details.get("avg_efficiency_ratio")
        try:
            efff = float(eff) if eff is not None else None
        except (TypeError, ValueError):
            efff = None
        if efff is not None:
            c_eff = min(1.0, efff * 1000.0)
            _add("Efficiency Ratio (×1000, capped at 1.0)",
                 f"{efff:.6f}", c_eff, formula_label="avg_efficiency_ratio×1000")
        else:
            _add("Efficiency Ratio", None, None,
                 formula_label="avg_efficiency_ratio×1000",
                 note="EfficiencyConfig not set")
        for dk, lbl, fl in [
            ("avg_budget_score", "Resource Budget Score", "avg_budget_score"),
            ("ttft_variability_score", "TTFT Variability Score", "ttft_variability_score"),
            ("avg_cost_predictability", "Cost Predictability", "avg_cost_predictability"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl)
        formula_str = "avg( 1−P95/10s, avg_efficiency_ratio×1000, avg_budget_score, ttft_variability_score, avg_cost_predictability )"

    elif gate_key == "E":
        threat_count = details.get("threat_count", 0) or 0
        # threat_free_rate = _sec_score_raw (미리 계산됨). 없으면 count에서 추정(하위 호환).
        tfr = details.get("threat_free_rate")
        if tfr is None:
            tfr = 1.0 if threat_count == 0 else None
        note_threat = "" if threat_count == 0 else _count_noun(threat_count, "threat") + " detected"
        # The aggregate only folds threat_free_rate into the average when there are
        # NO per-tracker defense scores (otherwise the same events are double-counted).
        # Render the row for context but keep it out of the mean; re-add below if it
        # turns out to be the only signal.
        _tf_note = "not averaged when per-tracker scores exist"
        if note_threat:
            _tf_note = f"{note_threat}; {_tf_note}"
        _add("Threat-Free Rate (1 − threats/total)",
             f"{float(tfr):.3f}" if tfr is not None else _count_noun(threat_count, "threat"),
             tfr,
             formula_label="1−threat_rate", always=True,
             note=_tf_note,
             in_avg=False)
        cvss = details.get("avg_cvss_weighted_score")
        if cvss is not None:
            c_cvss = max(0.0, 1.0 - float(cvss) / 10.0)
            _add("CVSS Defense (1 − avg_cvss/10)", f"{float(cvss):.3f}", c_cvss,
                 formula_label="1−avg_cvss/10")
        else:
            _add("CVSS Defense (1 − avg_cvss/10)", None, None,
                 formula_label="1−avg_cvss/10", note="No CVSS-scored threats")
        avg_comp = details.get("avg_compliance_score")
        _add("Compliance Score", _fmt_ratio(avg_comp), avg_comp,
             formula_label="avg_compliance_score")
        priv = details.get("privilege_escalation_rate")
        c_priv = (1.0 - float(priv)) if priv is not None else None
        _add("Privilege Escalation Defense (1 − rate)",
             _fmt_pct(priv), c_priv, formula_label="1−priv_esc_rate")
        chain = details.get("chain_attack_rate")
        c_chain = (1.0 - float(chain)) if chain is not None else None
        _add("Attack Chain Defense (1 − rate)",
             _fmt_pct(chain), c_chain, formula_label="1−chain_attack_rate")
        # Leakage Defense — native OutputLeakageDetector score
        leak_def = details.get("leakage_defense_rate")
        if leak_def is not None:
            lc = details.get("leakage_count", 0)
            _add("Output Leakage Defense (1 − leakage/total)",
                 _count_noun(lc, "leak"), leak_def, formula_label="1−leakage_rate")
        else:
            _add("Output Leakage Defense (1 − leakage/total)", None, None,
                 formula_label="1−leakage_rate",
                 note="No output leakage data recorded")
        # Injection Defense — native InputSanitizationTracker score
        inj_def = details.get("injection_defense_rate")
        if inj_def is not None:
            ic = details.get("injection_count", 0)
            _add("Injection Defense (1 − threats/total)",
                 _count_noun(ic, "threat"), inj_def, formula_label="1−injection_rate")
        else:
            _add("Injection Defense (1 − threats/total)", None, None,
                 formula_label="1−injection_rate",
                 note="No input sanitization data recorded")
        # Tool Authorization Defense — native ToolAuthorizationTracker score
        ta_rate = details.get("tool_authorization_rate")
        if ta_rate is not None:
            uc = details.get("unauthorized_calls_count", 0)
            _add("Tool Authorization Defense (1 − unauth/total)",
                 _count_noun(uc, "unauthorized call"), ta_rate, formula_label="1−unauth_rate")
        else:
            _add("Tool Authorization Defense (1 − unauth/total)", None, None,
                 formula_label="1−unauth_rate",
                 note="No tool authorization data recorded")
        tr = details.get("avg_threat_response")
        _add("Threat Response Score", _fmt_ratio(tr), tr,
             formula_label="avg_threat_response")
        # threat_free_rate is the sole component only when no per-tracker score landed.
        if not included_vals and tfr is not None:
            included_vals.append(float(tfr))
        formula_str = (
            "avg( [1−threat_rate only if no per-tracker score], [1−cvss/10], [compliance], "
            "[1−priv_esc_rate], [1−chain_rate], "
            "[1−leakage_rate], [1−injection_rate], [1−unauth_rate], [threat_response] )"
        )

    elif gate_key == "F":
        for dk, lbl, fl in [
            ("avg_consensus", "Consensus Rate", "avg_consensus"),
            ("avg_propagation", "Propagation Accuracy", "avg_propagation"),
            ("avg_role_compliance", "Agent Role Compliance", "avg_role_compliance"),
            ("avg_conflict_resolution", "Conflict Resolution Rate", "avg_conflict_resolution"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl)
        formula_str = "avg( avg_consensus, avg_propagation, avg_role_compliance, avg_conflict_resolution )"

    elif gate_key == "G":
        tc = details.get("tool_coverage")
        if tc is not None:
            _add("Tool Coverage (success_rate)", _fmt_ratio(tc), tc,
                 formula_label="tool_coverage")
        else:
            _add("Tool Coverage", None, None,
                 formula_label="tool_coverage",
                 note="Excluded — no tool calls recorded (tool_use tasks only)")
        for dk, lbl, fl in [
            ("avg_explainability", "Explainability", "avg_explainability"),
            ("avg_observability_score", "Observability Score", "avg_observability_score"),
            ("avg_error_diagnosis", "Error Diagnosis", "avg_error_diagnosis"),
            ("avg_latency_attribution", "Latency Attribution", "avg_latency_attribution"),
        ]:
            v = details.get(dk)
            _add(lbl, _fmt_ratio(v), v, formula_label=fl)
        hall = details.get("hallucination_rate")
        if hall is not None:
            c_hall = max(0.0, 1.0 - float(hall))
            _add("Hallucination Defense (1 − rate)", _fmt_pct(hall, scale=100.0), c_hall,
                 formula_label="1−hallucination_rate")
        else:
            _add("Hallucination Defense (1 − rate)", None, None,
                 formula_label="1−hallucination_rate",
                 note="Requires enable_hallucination_detection=True")
        formula_str = "avg( [tool_coverage if tools used], avg_explainability, avg_observability_score, avg_error_diagnosis, avg_latency_attribution, [1−hallucination_rate] )"

    else:
        return ""

    if not included_vals:
        return ""

    # Result line
    score_pct = float(score) * 100
    score_col = "#10b981" if score_pct >= 80 else ("#f59e0b" if score_pct >= 60 else "#ef4444")
    _naive = sum(included_vals) / len(included_vals)
    if len(included_vals) == 1:
        comp_expr = f"{included_vals[0]:.3f}"
    else:
        terms = " + ".join(f"{v:.3f}" for v in included_vals)
        comp_expr = f"( {terms} ) ÷ {len(included_vals)}"
    # Gates A and C weight the TCR component (gate_x_tcr_weight) rather than taking a
    # plain mean, so the expression above is only indicative — never assert it equals
    # the score when it does not. Reconciles for B/D/E/G (true unweighted means).
    _tcr_w = details.get(f"gate_{gate_key.lower()}_tcr_weight")
    _weighted_note = ""
    _reconciles = abs(_naive - float(score)) <= 0.002
    if not _reconciles and _tcr_w is not None:
        _blend = " and blended with accuracy" if gate_key == "A" else ""
        _weighted_note = (
            f'<div style="font-size:11px;color:#6b7280;margin-top:4px">'
            f'The component mean above is indicative only — Gate {gate_key} weights the '
            f'TCR component at {float(_tcr_w):.0%} of the score{_blend}; the other '
            f'components share the remaining {1 - float(_tcr_w):.0%}.</div>'
        )
    # P4.1: 측정된 컴포넌트가 2개 이하면 점수 대표성이 낮다 — 특히 그중 하나가
    # 만점(예: 데이터 없어 1.0으로 채워진 항목)이면 실제 문제를 희석할 수 있다.
    rep_warn = ""
    if len(included_vals) <= 2 and score_pct < 90:
        _hi = sum(1 for v in included_vals if v >= 0.99)
        _extra = (" One or more are at 100% (often a not-measured item defaulting high), "
                  "which can mask a real weakness." if _hi else "")
        rep_warn = (
            f'<div style="font-size:11px;color:#92400e;background:#fffbeb;'
            f'border-left:3px solid #f59e0b;border-radius:4px;padding:6px 10px;margin-top:4px">'
            f'⚠️ Only {len(included_vals)} score component(s) measured — this Gate score '
            f'may not be representative.{_extra} Enable more of this Gate\'s Configs '
            f'for a fuller picture.'
            f'</div>'
        )
    # P5: 표본 부족 경고 — 모든 Gate에 대해(전엔 Gate D만). base.py::_min_sample_warning이
    # details.insufficient_data_warnings에 넣은 문자열을 그대로 노출한다.
    insuf = details.get("insufficient_data_warnings")
    insuf_html = ""
    if insuf:
        _items = "".join(f"<li>{_esc(str(w))}</li>" for w in insuf if w)
        if _items:
            insuf_html = (
                f'<div style="font-size:11px;color:#92400e;background:#fffbeb;'
                f'border-left:3px solid #f59e0b;border-radius:4px;padding:6px 10px;margin-top:4px">'
                f'📉 <strong>Insufficient data</strong> — some components fell below '
                f'their minimum sample size:'
                f'<ul style="margin:4px 0 0 16px">{_items}</ul></div>'
            )

    if _reconciles or _tcr_w is None:
        _result_line = (
            f'Gate {gate_key} Score&nbsp;=&nbsp;{comp_expr}&nbsp;=&nbsp;'
            f'<strong style="color:{score_col}">{score_pct:.1f}%</strong>'
        )
    else:
        _result_line = (
            f'{comp_expr}&nbsp;&asymp;&nbsp;{_naive * 100:.1f}%'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;Gate {gate_key} Score&nbsp;=&nbsp;'
            f'<strong style="color:{score_col}">{score_pct:.1f}%</strong>'
        )
    result_html = (
        f'<div class="bd-result">'
        f'{_result_line}'
        f'&nbsp;<span style="font-size:11px;color:#6b7280">({len(included_vals)} component(s) measured)</span>'
        f'</div>'
        f'{_weighted_note}'
        f'{rep_warn}'
        f'{insuf_html}'
    )

    rows_html = "".join(rows)
    return (
        f'<div class="score-breakdown">'
        f'<div class="bd-header">'
        f'<span class="bd-label">Score Breakdown</span>'
        f'<span class="bd-formula">{formula_str}</span>'
        f'</div>'
        f'<table class="bd-table">'
        f'<thead><tr>'
        f'<th>Component</th><th>Raw Value</th>'
        f'<th>Contribution</th><th>Note</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'{result_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate A — Goal Achievement
# ---------------------------------------------------------------------------

def _build_gate_a(tcr: float, success_rate: float, acc: float,
                  accuracy_metrics: dict, harness_a: dict,
                  quality_metrics: dict | None = None) -> str:
    if quality_metrics is None:
        quality_metrics = {}
    color = _GATE_COLORS["A"]
    gate_status = (harness_a.get("gate") or harness_a.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    # TCR / accuracy KPIs
    kpis = (
        f'<div class="kpi"><div class="kpi-lbl">TCR</div>'
        f'<div class="kpi-val" style="color:{_score_color(tcr)}">{_num(tcr, ".1f")}%</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">Full Success Rate</div>'
        f'<div class="kpi-val" style="color:{_score_color(success_rate)}">{_num(success_rate, ".1f")}%</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">Overall Accuracy</div>'
        f'<div class="kpi-val" style="color:{_score_color(acc)}">{_num(acc, ".1f")}%</div></div>'
    )

    # Accuracy by task_type
    by_type = accuracy_metrics.get("accuracy_by_task_type") or accuracy_metrics.get("by_type") or {}
    type_rows = ""
    if isinstance(by_type, dict):
        for ttype, tdata in by_type.items():
            if isinstance(tdata, dict):
                v = tdata.get("avg_accuracy", tdata.get("mean", tdata.get("accuracy")))
            else:
                v = tdata
            if v is not None:
                pct_v = float(v) * 100 if float(v) <= 1.0 else float(v)
                type_rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6;font-size:12px">{ttype}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6;font-weight:600;'
                    f'color:{_score_color(pct_v)}">{pct_v:.1f}%</td>'
                    f'</tr>'
                )

    type_table = ""
    if type_rows:
        type_table = (
            f'<h3>Accuracy by Task Type</h3>'
            f'<table class="mtable"><thead><tr><th>Task Type</th><th>Accuracy</th></tr></thead>'
            f'<tbody>{type_rows}</tbody></table>'
        )

    # Harness A detail
    details = harness_a.get("details") or {}
    harness_rows = ""
    fields = [
        ("instruction_adherence", "Instruction Adherence"),
        ("goal_alignment", "Goal Alignment Score"),
        ("plan_coherence", "Plan Coherence"),
        ("subtask_completion", "Subtask Completion Rate"),
        ("context_retention", "Context Retention Rate"),
        ("knowledge_retention", "Knowledge Retention"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate A Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass InstructionConfig · GoalAlignmentConfig to your decorator to enable detailed metrics.</div>'

    # Response Quality (5 Dimensions)
    quality_html = ""
    if not quality_metrics or quality_metrics.get("total_evaluated", 0) == 0:
        quality_html = (
            '<h3>Response Quality (5 Dimensions)</h3>'
            + _not_tested("No response quality evaluation data collected.")
        )
    else:
        avg_score = quality_metrics.get("avg_total_score", 0)
        dim_scores = quality_metrics.get("dimension_scores", {})
        dimensions = [
            ("relevance", "Relevance"),
            ("completeness", "Completeness"),
            ("accuracy", "Accuracy"),
            ("clarity", "Clarity"),
            ("usefulness", "Usefulness"),
        ]
        rows = ""
        for dk, dlabel in dimensions:
            v = dim_scores.get(dk)
            if v is not None:
                pct_v = float(v) / 5 * 100
                rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6;font-size:12px">{dlabel}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6;font-weight:600;'
                    f'color:{_score_color(pct_v,80,60)}">{float(v):.2f}/5.0</td>'
                    f'</tr>'
                )
        kpi_html = (
            f'<div class="kpi"><div class="kpi-lbl">Avg Quality Score</div>'
            f'<div class="kpi-val" style="color:{_score_color(float(avg_score)/5*100,0.8,0.6)}">'
            f'{float(avg_score):.2f}/5</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Evaluated Count</div>'
            f'<div class="kpi-val">{quality_metrics.get("total_evaluated", 0)}</div></div>'
        )
        quality_html = (
            f'<h3>Response Quality (5 Dimensions)</h3>'
            f'<div class="kpis">{kpi_html}</div>'
            + (f'<table class="mtable"><thead><tr><th>Dimension</th><th>Avg</th></tr></thead>'
               f'<tbody>{rows}</tbody></table>' if rows else "")
        )

    breakdown = _build_score_breakdown("A", harness_a)
    return (
        f'<div class="gate-section" id="gate-a" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate A &nbsp;<span style="font-size:14px;color:#374151">Goal Achievement</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'<div class="kpis">{kpis}</div>'
        f'{type_table}'
        f'{quality_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate B — Behavioral Integrity
# ---------------------------------------------------------------------------

def _build_gate_b(tool_selection_stats: dict, has_agentic: bool,
                  harness_b: dict) -> str:
    color = _GATE_COLORS["B"]
    gate_status = (harness_b.get("gate") or harness_b.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    tool_html = ""
    if not has_agentic:
        tool_html = (
            '<h3>Tool Usage Analysis</h3>'
            + _not_tested("No agentic tool usage data — "
                          "run tasks with <code>task_type=\"tool_use\"</code> to measure.")
        )
    elif not tool_selection_stats:
        tool_html = (
            '<h3>Tool Usage Analysis</h3>'
            + _not_tested("No tool selection data collected.")
        )
    if has_agentic and tool_selection_stats:
        f1 = tool_selection_stats.get("avg_f1")
        eff = tool_selection_stats.get("avg_efficiency")
        redundancy = tool_selection_stats.get("redundancy_rate")
        fail_rate = tool_selection_stats.get("failure_rate")
        kpi_parts = ""
        if f1 is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Tool Selection F1</div>'
                f'<div class="kpi-val" style="color:{_score_color(float(f1)*100,80,60)}">{float(f1):.3f}</div></div>'
            )
        if eff is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Tool Efficiency</div>'
                f'<div class="kpi-val" style="color:{_score_color(float(eff)*100)}">{_pct(eff)}</div></div>'
            )
        if redundancy is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Redundancy Rate</div>'
                f'<div class="kpi-val" style="color:{_score_color(100 - float(redundancy)*100)}">{_pct(redundancy)}</div></div>'
            )
        if fail_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Tool Failure Rate</div>'
                f'<div class="kpi-val" style="color:{_score_color(100 - float(fail_rate)*100)}">{_pct(fail_rate)}</div></div>'
            )
        if kpi_parts:
            tool_html = f'<h3>Tool Usage Analysis</h3><div class="kpis">{kpi_parts}</div>'

    # Harness B detail
    details = harness_b.get("details") or {}
    harness_rows = ""
    fields = [
        ("loop_detection_score", "Loop Detection Rate"),
        ("scope_compliance", "Scope Compliance"),
        ("tool_param_safety", "Tool Parameter Safety"),
        ("context_window_efficiency", "Context Window Efficiency"),
        ("state_consistency", "State Consistency"),
        ("deadlock_score", "Deadlock Prevention Rate"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate B Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass LoopDetectionConfig · ScopeConfig to your decorator to enable detailed metrics.</div>'

    breakdown = _build_score_breakdown("B", harness_b)
    return (
        f'<div class="gate-section" id="gate-b" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate B &nbsp;<span style="font-size:14px;color:#374151">Behavioral Integrity</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{tool_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate C — Reliability
# ---------------------------------------------------------------------------

def _build_gate_c(retry_metrics: dict, harness_c: dict, hallucination_data: dict | None = None,
                  llm_judge_data: Any = None) -> str:
    if hallucination_data is None:
        hallucination_data = {}
    color = _GATE_COLORS["C"]
    gate_status = (harness_c.get("gate") or harness_c.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    retry_html = ""
    _retry_total = (retry_metrics or {}).get("total_retries", (retry_metrics or {}).get("total", 0))
    _retry_measured = bool(retry_metrics) and (
        _retry_total is not None and _retry_total > 0
        or retry_metrics.get("overall_retry_rate") is not None
        or retry_metrics.get("retry_rate") is not None
    )
    if not _retry_measured:
        retry_html = (
            '<h3>Retry / Recovery</h3>'
            + _not_tested("No retry data collected — "
                          "no retries occurred or <code>RetryConfig</code> is not set.")
        )
    if _retry_measured:
        retry_rate = retry_metrics.get("overall_retry_rate") or retry_metrics.get("retry_rate")
        correction_rate = retry_metrics.get("correction_success_rate") or retry_metrics.get("success_rate")
        kpi_parts = ""
        if retry_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Retry Rate</div>'
                f'<div class="kpi-val">{_pct(retry_rate)}</div></div>'
            )
        if correction_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">Retry Success Rate</div>'
                f'<div class="kpi-val" style="color:{_score_color(float(correction_rate)*100)}">{_pct(correction_rate)}</div></div>'
            )
        if kpi_parts:
            retry_html = f'<h3>Retry / Recovery</h3><div class="kpis">{kpi_parts}</div>'

    details = harness_c.get("details") or {}
    harness_rows = ""
    fields = [
        ("reproducibility", "Reproducibility"),
        ("fault_tolerance", "Fault Tolerance"),
        ("graceful_degradation", "Graceful Degradation"),
        ("retry_consistency", "Retry Consistency"),
        ("idempotency", "Idempotency"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate C Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass FaultToleranceConfig · ReproducibilityConfig to your decorator to enable detailed metrics.</div>'

    # LLM Judge Faithfulness 값 먼저 추출 — Hallucination 섹션 표시 여부 결정에 사용
    faith_html = ""
    _faith_val: Any = None
    _faith_used_for_score = bool(harness_c.get("details", {}).get("avg_llm_faithfulness"))
    if llm_judge_data is not None:
        try:
            if hasattr(llm_judge_data, "avg_faithfulness"):
                _faith_val = getattr(llm_judge_data, "avg_faithfulness", None)
                faith_count = getattr(llm_judge_data, "judged_count", 0)
                faith_model = getattr(llm_judge_data, "model", "—") or "—"
            elif isinstance(llm_judge_data, dict):
                _faith_val = llm_judge_data.get("avg_faithfulness")
                faith_count = llm_judge_data.get("judged_count") or llm_judge_data.get("count", 0)
                faith_model = llm_judge_data.get("model", "—") or "—"
            else:
                _faith_val = faith_count = faith_model = None
            if _faith_val is not None and faith_count:
                faith_pct = float(_faith_val) * 20  # 0-5 → 0-100
                score_badge = (
                    ' <span style="font-size:11px;background:#d1fae5;color:#065f46;'
                    'padding:1px 6px;border-radius:4px;vertical-align:middle">★ in Gate C score</span>'
                    if _faith_used_for_score else ""
                )
                faith_html = (
                    f'<h3>LLM Judge — Faithfulness (RAG){score_badge}</h3>'
                    f'<div class="kpis">'
                    f'<div class="kpi"><div class="kpi-lbl">Faithfulness Score</div>'
                    f'<div class="kpi-val" style="color:{_score_color(faith_pct)}">'
                    f'{float(_faith_val):.2f}/5</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Evaluated</div>'
                    f'<div class="kpi-val">{faith_count} tasks</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Judge Model</div>'
                    f'<div class="kpi-val" style="font-size:11px">{faith_model}</div></div>'
                    f'</div>'
                    f'<p style="font-size:12px;color:#6b7280;margin:6px 0 0">'
                    f'LLM-as-judge faithfulness: measures how well all claims in the response are supported '
                    f'by the retrieved context, scored 0–5 (5 = fully grounded). '
                    f'Activated when <code>rag_mode=True</code> + <code>LLMJudgeConfig</code> is set. '
                    f'When present, this score replaces Hallucination Detection in the Gate C calculation.</p>'
                )
        except Exception:
            pass

    # Hallucination Detection — LLM faithfulness 가 Gate C에 사용된 경우 "폴백 미사용" 표시
    hall_html = ""
    _hall_measured = bool(hallucination_data) and hallucination_data.get("total_evaluated", 0) > 0
    if not _hall_measured:
        hall_html = (
            '<h3>Hallucination Detection</h3>'
            + _not_tested("Hallucination detection is not enabled — "
                          "measure it with <code>enable_hallucination_detection=True</code>.",
                          kind="config")
        )
    else:
        hall_rate = float(hallucination_data.get("overall_rate") or 0)
        hall_pct = hall_rate  # overall_rate is already a percentage (0–100 scale)
        hall_col = _score_color(100 - hall_pct)
        _hall_title = (
            "Hallucination Detection"
            if not _faith_used_for_score
            else 'Hallucination Detection <span style="font-size:11px;background:#fef3c7;color:#92400e;'
                 'padding:1px 6px;border-radius:4px;vertical-align:middle">NLP fallback — not used in score</span>'
        )
        hall_html = (
            f'<h3>{_hall_title}</h3>'
            f'<div class="kpis">'
            f'<div class="kpi"><div class="kpi-lbl">Hallucination Rate</div>'
            f'<div class="kpi-val" style="color:{hall_col}">{hall_pct:.1f}%</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Safe Rate</div>'
            f'<div class="kpi-val" style="color:{_score_color(100 - hall_pct)}">{100 - hall_pct:.1f}%</div></div>'
            f'</div>'
        )

    breakdown = _build_score_breakdown("C", harness_c)
    return (
        f'<div class="gate-section" id="gate-c" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate C &nbsp;<span style="font-size:14px;color:#374151">Reliability</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{retry_html}'
        f'{hall_html}'
        f'{faith_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate D — Performance Contract
# ---------------------------------------------------------------------------

def _task_latency_attribution(t: Any) -> dict[str, Any] | None:
    """Pull the per-task ``latency_attribution`` dict from a TaskResult / TaskRecord."""
    raw = getattr(t, "raw", None)
    extra = raw.get("extra") if isinstance(raw, dict) else getattr(t, "extra", None)
    if isinstance(extra, dict):
        la = extra.get("latency_attribution")
        if isinstance(la, dict):
            return la
    return None


def _build_latency_budget(tasks: list[Any] | None, p95: Any) -> str:
    """P7: turn "P95 = 4.0s" into a where-does-the-time-go stacked bar.

    Aggregates the per-task span breakdown that ``eval_latency_attribution``
    computes (model_ms / tool_ms / network_ms / unattributed_ms + bottleneck) —
    the Gate G score alone never told the reader *which* component to optimise.
    """
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import aggregate_latency_attribution

        agg = aggregate_latency_attribution(
            [a for a in (_task_latency_attribution(t) for t in tasks) if a is not None]
        )
    except Exception:
        agg = None
    if not agg:
        return ""

    parts = [
        ("Model", agg.get("model_ms", 0.0), "#6366f1"),
        ("Tool", agg.get("tool_ms", 0.0), "#f59e0b"),
        ("Network", agg.get("network_ms", 0.0), "#10b981"),
        ("Unattributed", agg.get("unattributed_ms", 0.0), "#9ca3af"),
    ]
    total = sum(v for _, v, _ in parts) or 1.0
    segs = "".join(
        f'<div style="width:{v / total * 100:.1f}%;background:{col}" '
        f'title="{lbl}: {v:.0f}ms ({v / total * 100:.0f}%)"></div>'
        for lbl, v, col in parts if v > 0
    )
    legend = " · ".join(
        f'<span style="color:{col};font-weight:600">■</span> {lbl} '
        f'{v:.0f}ms ({v / total * 100:.0f}%)'
        for lbl, v, col in parts if v > 0
    )
    bn = agg.get("bottleneck")
    bn_line = ""
    if bn:
        share = agg.get("bottleneck_share")
        bn_line = (
            f'<p style="font-size:13px;margin:6px 0 0"><strong>Bottleneck: '
            f'{_esc(str(bn))}</strong>'
            + (f' — top component in {share * 100:.0f}% of tasks' if isinstance(share, (int, float)) else "")
            + '</p>'
        )
    n = agg.get("n_tasks", 0)
    return (
        '<h3 style="margin-top:14px">Latency Budget '
        f'<span style="font-size:12px;color:#6b7280;font-weight:400">'
        f'(mean attribution over {n} task(s) with span data)</span></h3>'
        '<div style="display:flex;height:20px;border-radius:4px;overflow:hidden;'
        f'margin:6px 0">{segs}</div>'
        f'<p style="font-size:12px;color:#4b5563;margin:0">{legend}</p>'
        f'{bn_line}'
    )


def _build_gate_d(latency_stats: dict, token_stats: dict, harness_d: dict,
                  tasks: list[Any] | None = None,
                  current: dict[str, Any] | None = None) -> str:
    color = _GATE_COLORS["D"]
    gate_status = (harness_d.get("gate") or harness_d.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    # Latency KPIs
    def _sec(v):
        if v is None:
            return "—"
        try:
            return f"{float(v):.3f}s"
        except (TypeError, ValueError):
            return "—"

    lat_html = ""
    if not latency_stats:
        lat_html = '<h3>Latency Analysis</h3>' + _not_tested("No latency data collected.")
    if latency_stats:
        lat_kpis = (
            f'<div class="kpi"><div class="kpi-lbl">Mean</div><div class="kpi-val">{_sec(latency_stats.get("mean"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P50</div><div class="kpi-val">{_sec(latency_stats.get("p50"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P90</div><div class="kpi-val">{_sec(latency_stats.get("p90"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P95</div><div class="kpi-val">{_sec(latency_stats.get("p95"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P99</div><div class="kpi-val">{_sec(latency_stats.get("p99"))}</div></div>'
        )
        lat_html = f'<h3>Latency Analysis</h3><div class="kpis">{lat_kpis}</div>'
    lat_html += _build_latency_budget(tasks, latency_stats.get("p95") if latency_stats else None)

    # Token & cost KPIs
    tok_html = ""
    if not token_stats:
        tok_html = (
            '<h3>Tokens &amp; Cost</h3>'
            + _not_tested("No token/cost data collected — "
                          "record token counts in <code>TaskResult</code> to measure.")
        )
    if token_stats:
        _cost = _fmt_usd

        tok_kpis = (
            f'<div class="kpi"><div class="kpi-lbl">Total Tokens</div>'
            f'<div class="kpi-val">{int(token_stats.get("total_tokens") or 0):,}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Avg Tokens/Task</div>'
            f'<div class="kpi-val">{_num(token_stats.get("avg_tokens_per_task"), ".0f")}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Total Cost</div>'
            f'<div class="kpi-val">{_cost(token_stats.get("total_cost"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Cost/Task</div>'
            f'<div class="kpi-val">{_cost(token_stats.get("avg_cost_per_task"))}</div></div>'
        )
        tok_html = f'<h3>Tokens & Cost</h3><div class="kpis">{tok_kpis}</div>'

    details = harness_d.get("details") or {}
    harness_rows = ""
    fields = [
        ("sla_compliance", "SLA Compliance"),
        ("efficiency_score", "Efficiency Score"),
        ("resource_budget_compliance", "Resource Budget Compliance"),
        ("ttft_variability", "TTFT Variability"),
        ("cost_predictability", "Cost Predictability"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate D Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass SLAConfig · EfficiencyConfig to your decorator to enable detailed metrics.</div>'

    # insufficient_data_warnings는 이제 _build_score_breakdown()이 전 Gate 공통으로
    # 렌더한다(P5) — Gate D 전용 중복 블록 제거.
    breakdown = _build_score_breakdown("D", harness_d)

    cost_html = _build_cost_economics(tasks, current, token_stats)

    return (
        f'<div class="gate-section" id="gate-d" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate D &nbsp;<span style="font-size:14px;color:#374151">Performance Contract</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{lat_html}'
        f'{tok_html}'
        f'{cost_html}'
        f'{harness_block}'
        f'</div>'
    )


def _build_cost_economics(tasks: list[Any] | None, current: dict[str, Any] | None,
                          token_stats: dict | None) -> str:
    """P16: cost per *successful* task + waste + retry burn + scale projection."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import _cost_economics_section

        cur = current
        if not (cur and (cur.get("pricing") or cur.get("efficiency_metrics"))):
            cur = {"pricing": {}, "efficiency_metrics": {"tokens": token_stats or {}}}
        ce = _cost_economics_section(_review_dict_tasks(tasks), cur)
    except Exception:
        ce = None
    if not ce:
        return ""

    _usd = _fmt_usd

    cps = ce.get("cost_per_successful_task_usd")
    cpt = ce.get("cost_per_task_usd")
    penalty = ""
    if isinstance(cps, (int, float)) and isinstance(cpt, (int, float)) and cpt > 0:
        penalty = f' <span style="color:#6b7280">({cps / cpt:.1f}x cost/task)</span>'
    proj = ce.get("projection") or {}
    _nfail = ce.get("n_failed_or_lowscore")
    _ntot = ce.get("n_tasks")
    _wlabel = "Wasted on failed / low-scoring tasks"
    if isinstance(_nfail, int) and isinstance(_ntot, int):
        _wlabel += f" ({_nfail} of {_ntot})"
    wasted_val = f'{_usd(ce.get("wasted_cost_usd"))} ({ce.get("wasted_cost_pct")}%)'
    retry_val = f'{_usd(ce.get("retry_cost_usd"))} ({ce.get("retry_cost_pct")}%)'
    proj_calls = proj.get("calls", 100000)
    proj_val = (f'{_usd(proj.get("total_usd"))} '
                f'(of which {_usd(proj.get("wasted_usd"))} wasted)')
    rows = (
        _metric_row("Cost per successful task", _usd(cps) + penalty)
        + _metric_row(_wlabel, wasted_val)
        + _metric_row("Retry burn", retry_val)
        + _metric_row(f"Projected at {proj_calls:,} calls", proj_val)
    )
    note = ("" if ce.get("cost_source") == "per_task_tokens"
            else '<p style="font-size:11px;color:#9ca3af;margin:2px 0 0">'
                 'Per-task token costs unavailable — figures use a uniform split of '
                 'the aggregate cost.</p>')
    return (
        '<h3 style="margin-top:14px">Cost Efficiency</h3>'
        f'<table class="mtable"><tbody>{rows}</tbody></table>{note}'
    )


# ---------------------------------------------------------------------------
# Gate E — Security Boundary
# ---------------------------------------------------------------------------

def _build_gate_e_from_monitor(monitor, harness_e: dict) -> str:
    """monitor 객체에서 보안 데이터를 직접 추출."""
    color = _GATE_COLORS["E"]
    gate_status = (harness_e.get("gate") or harness_e.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    sec_html = ""
    try:
        _inp  = getattr(monitor, 'input_sanitizer', None)
        _out  = getattr(monitor, 'output_leakage_detector', None)
        _auth = getattr(monitor, 'tool_authorizer', None)
        _priv = getattr(monitor, 'privilege_escalation_detector', None)
        _atk  = getattr(monitor, 'tool_chain_attack_detector', None)
        # 보안 트래커가 하나도 활성화되지 않았으면 섹션 미표시 (RF 경로와 동일 동작)
        _any_active = any(t is not None for t in [_inp, _out, _auth, _priv, _atk])
        if _any_active:
            # 이벤트 0건이면 RF 경로와 동일하게 빈 dict 처리
            def _sec_or_empty(d: dict, total_key: str) -> dict:
                return d if d and d.get(total_key, 0) > 0 else {}
            _is = _inp.get_security_stats()    if _inp  is not None else {}
            _ol = _out.get_leakage_stats()     if _out  is not None else {}
            _ta = _auth.get_compliance_stats() if _auth is not None else {}
            _pe = _priv.get_escalation_stats() if _priv is not None else {}
            _ca = _atk.get_attack_stats()      if _atk  is not None else {}
            input_sec   = _sec_or_empty(_is, "total_inputs_evaluated")
            output_leak = _sec_or_empty(_ol, "total_outputs_evaluated")
            tool_auth   = _sec_or_empty(_ta, "total_tool_calls")
            priv_esc    = _sec_or_empty(_pe, "total_evaluations")
            chain_atk   = _sec_or_empty(_ca, "total_chains_analyzed")
            sec_html = _build_security_kpis(input_sec, output_leak, tool_auth, priv_esc, chain_atk)
    except Exception:
        pass

    details = harness_e.get("details") or {}
    harness_rows = ""
    fields = [
        ("threat_severity_score", "Threat Severity Score"),
        ("compliance_score", "Compliance Rate"),
        ("threat_response_score", "Threat Response Score"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate E Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass ThreatSeverityConfig · ComplianceConfig to your decorator to enable detailed metrics.</div>'

    breakdown = _build_score_breakdown("E", harness_e)
    return (
        f'<div class="gate-section" id="gate-e" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate E &nbsp;<span style="font-size:14px;color:#374151">Security Boundary</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{sec_html}'
        f'{harness_block}'
        f'</div>'
    )


def _build_gate_e_from_rf(rf, harness_e: dict) -> str:
    """ResultFile 객체에서 보안 데이터를 추출."""
    color = _GATE_COLORS["E"]
    gate_status = (harness_e.get("gate") or harness_e.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    sec_html = ""
    if getattr(rf, "has_security", False):
        try:
            sl1 = rf.security_l1
            sl2 = rf.security_l2
            inp = sl1.input_security or {}
            out = sl1.output_leakage or {}
            auth = sl1.authorization or {}
            priv = sl2.privilege_escalation or {}
            atk = sl2.attack_detection or {}
            sec_html = _build_security_kpis(inp, out, auth, priv, atk)
        except Exception:
            pass

    details = harness_e.get("details") or {}
    harness_rows = ""
    fields = [
        ("threat_severity_score", "Threat Severity Score"),
        ("compliance_score", "Compliance Rate"),
        ("threat_response_score", "Threat Response Score"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate E Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass ThreatSeverityConfig · ComplianceConfig to your decorator to enable detailed metrics.</div>'

    breakdown = _build_score_breakdown("E", harness_e)
    return (
        f'<div class="gate-section" id="gate-e" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate E &nbsp;<span style="font-size:14px;color:#374151">Security Boundary</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{sec_html}'
        f'{harness_block}'
        f'</div>'
    )


def _build_security_kpis(input_sec: dict, output_leak: dict, tool_auth: dict,
                          priv_esc: dict, chain_atk: dict) -> str:
    """공통 보안 KPI 블록 생성."""
    kpi_parts = []

    if input_sec:
        threat_rate = float(input_sec.get("threat_rate") or 0)
        total_inp = input_sec.get("total_inputs_evaluated", 0)
        safe = 100 - threat_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">Input Security (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_inp} events · threats {threat_rate:.1f}%</div></div>'
        )

    if output_leak:
        leak_rate = float(output_leak.get("leakage_rate") or 0)
        total_out = output_leak.get("total_outputs_evaluated", 0)
        safe = 100 - leak_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">Output Leak Prevention (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_out} events · leaks {leak_rate:.1f}%</div></div>'
        )

    if tool_auth:
        comply = float(tool_auth.get("compliance_rate") or 100)
        total_calls = tool_auth.get("total_tool_calls", 0)
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">Tool Authorization (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(comply)}">{comply:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_calls} calls</div></div>'
        )

    if priv_esc:
        esc_rate = float(priv_esc.get("escalation_rate") or 0)
        total_priv = priv_esc.get("total_evaluations", 0)
        safe = 100 - esc_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">Privilege Escalation Defense (L2)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_priv} events · detected {esc_rate:.1f}%</div></div>'
        )

    if chain_atk:
        atk_rate = float(chain_atk.get("detection_rate") or 0)
        total_chains = chain_atk.get("total_chains_analyzed", 0)
        safe = 100 - atk_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">Attack Chain Detection (L2)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_chains} events · suspicious {atk_rate:.1f}%</div></div>'
        )

    if not kpi_parts:
        return (
            '<h3>Security Metrics</h3>'
            + _not_tested("Security metrics are not enabled — "
                          "measure them with <code>enable_security_metrics=True</code>.",
                          kind="config")
        )
    return f'<h3>Security Metrics</h3><div class="kpis">{"".join(kpi_parts)}</div>'


# ---------------------------------------------------------------------------
# Gate F — Multi-Agent Coordination
# ---------------------------------------------------------------------------

def _build_gate_f(coordination_stats: dict, workflow_stats: dict,
                  has_agentic: bool, harness_f: dict) -> str:
    color = _GATE_COLORS["F"]
    gate_status = (harness_f.get("gate") or harness_f.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    coord_html = ""
    if not has_agentic:
        coord_html = (
            '<h3>Coordination / Workflow</h3>'
            + _not_tested("No multi-agent execution data — "
                          "agent collaboration tasks have not run.", kind="n/a")
        )
    if has_agentic:
        kpi_parts = []
        if coordination_stats:
            coord_score = coordination_stats.get("avg_coordination_score") or coordination_stats.get("score")
            if coord_score is not None:
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">Coordination Score</div>'
                    f'<div class="kpi-val" style="color:{_score_color(float(coord_score)*100)}">'
                    f'{float(coord_score)*100:.1f}%</div></div>'
                )
        if workflow_stats:
            # a workflow tracker that saw nothing reports 0.0 rates — don't render
            # those as a catastrophic "0.0%"; require a positive count.
            _wf_count = (workflow_stats.get("total_workflows")
                         or workflow_stats.get("total_executions")
                         or workflow_stats.get("count") or 0)
            _step_count = (workflow_stats.get("total_steps")
                           or workflow_stats.get("step_count") or 0)
            wf_rate = workflow_stats.get("success_rate") or workflow_stats.get("overall_success_rate")
            step_rate = workflow_stats.get("step_success_rate")
            if wf_rate is not None and (_wf_count or wf_rate):
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">Workflow Success Rate</div>'
                    f'<div class="kpi-val" style="color:{_score_color(float(wf_rate)*100)}">'
                    f'{float(wf_rate)*100:.1f}%</div></div>'
                )
            if step_rate is not None and (_step_count or step_rate):
                _step_pct = float(step_rate) if float(step_rate) > 1.0 else float(step_rate) * 100
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">Step Success Rate</div>'
                    f'<div class="kpi-val" style="color:{_score_color(_step_pct)}">'
                    f'{_step_pct:.1f}%</div></div>'
                )
        if kpi_parts:
            coord_html = f'<h3>Coordination / Workflow</h3><div class="kpis">{"".join(kpi_parts)}</div>'
        elif not gate_status or gate_status in ("n/a", "na"):
            coord_html = (
                '<h3>Coordination / Workflow</h3>'
                + _not_tested("No multi-agent / workflow execution data recorded.",
                              kind="n/a")
            )

    details = harness_f.get("details") or {}
    harness_rows = ""
    fields = [
        ("consensus_rate", "Consensus Rate"),
        ("propagation_accuracy", "Propagation Accuracy"),
        ("agent_role_compliance", "Agent Role Compliance"),
        ("conflict_resolution_rate", "Conflict Resolution Rate"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate F Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass ConsensusConfig · AgentRoleConfig to your decorator to enable detailed metrics.</div>'

    breakdown = _build_score_breakdown("F", harness_f)
    return (
        f'<div class="gate-section" id="gate-f" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate F &nbsp;<span style="font-size:14px;color:#374151">Multi-Agent Coordination</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{coord_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate G — Observability
# ---------------------------------------------------------------------------

def _build_gate_g(quality_metrics: dict, llm_judge_data: Any,
                  harness_g: dict) -> str:
    color = _GATE_COLORS["G"]
    gate_status = (harness_g.get("gate") or harness_g.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    # LLM Judge
    judge_html = ""
    if not llm_judge_data:
        judge_html = (
            '<h3>LLM Judge</h3>'
            + _not_tested("LLM Judge is not enabled — "
                          "measure with <code>enable_llm_judge=True</code> or <code>LLMJudgeConfig</code>.",
                          kind="config")
        )
    if llm_judge_data:
        try:
            judged_count = 0
            overall = None
            completeness = None
            relevance = None
            factual = None
            faithfulness = None
            model_name = "—"
            # Support both LLMJudgeData (dataclass) and dict summary
            if hasattr(llm_judge_data, "judged_count"):
                judged_count = llm_judge_data.judged_count
                overall = getattr(llm_judge_data, "avg_overall", None)
                completeness = getattr(llm_judge_data, "avg_completeness", None)
                relevance = getattr(llm_judge_data, "avg_relevance", None)
                factual = getattr(llm_judge_data, "avg_factual_consistency", None)
                faithfulness = getattr(llm_judge_data, "avg_faithfulness", None)
                model_name = getattr(llm_judge_data, "model", "—") or "—"
            elif isinstance(llm_judge_data, dict):
                judged_count = llm_judge_data.get("count", 0)
                overall = llm_judge_data.get("avg_overall") or llm_judge_data.get("overall")
                completeness = llm_judge_data.get("avg_completeness")
                relevance = llm_judge_data.get("avg_relevance")
                factual = llm_judge_data.get("avg_factual_consistency")
                faithfulness = llm_judge_data.get("avg_faithfulness")
                model_name = llm_judge_data.get("model", "—") or "—"
            if judged_count == 0:
                judge_html = (
                    '<h3>LLM Judge</h3>'
                    + _not_tested("No LLM Judge results — check the sample rate (<code>judge_sample_rate</code>).",
                                  kind="data")
                )
            if judged_count > 0:
                # LLMJudge dimensions have different native scales: `overall` (and
                # criteria_overall) is 0-10; completeness / relevance /
                # factual_consistency / faithfulness are 0-5. Show each on its own
                # denominator instead of guessing from the magnitude.
                def _judge_val(v, denom=5):
                    if v is None:
                        return "—"
                    try:
                        return f"{float(v):.2f}/{denom}"
                    except (TypeError, ValueError):
                        return "—"
                ov_100 = float(overall) * 10 if overall is not None and float(overall) <= 10 else float(overall or 0)
                faith_kpi = ""
                if faithfulness is not None:
                    faith_kpi = (
                        f'<div class="kpi"><div class="kpi-lbl">Faithfulness (RAG)</div>'
                        f'<div class="kpi-val" style="color:{_score_color(float(faithfulness) * 20)}">'
                        f'{_judge_val(faithfulness, 5)}</div></div>'
                    )
                judge_kpis = (
                    f'<div class="kpi"><div class="kpi-lbl">Evaluated Count</div>'
                    f'<div class="kpi-val">{judged_count}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Overall Score</div>'
                    f'<div class="kpi-val" style="color:{_score_color(ov_100)}">'
                    f'{_judge_val(overall, 10)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Completeness</div>'
                    f'<div class="kpi-val">{_judge_val(completeness, 5)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Relevance</div>'
                    f'<div class="kpi-val">{_judge_val(relevance, 5)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Factual Consistency</div>'
                    f'<div class="kpi-val">{_judge_val(factual, 5)}</div></div>'
                    + faith_kpi +
                    f'<div class="kpi"><div class="kpi-lbl">Judge Model</div>'
                    f'<div class="kpi-val" style="font-size:11px">{model_name}</div></div>'
                )
                judge_html = f'<h3>LLM Judge</h3><div class="kpis">{judge_kpis}</div>'
        except Exception:
            pass

    details = harness_g.get("details") or {}
    harness_rows = ""
    fields = [
        ("explainability_score", "Explainability"),
        ("observability_score", "Internal State Observability"),
        ("error_diagnosis_accuracy", "Error Diagnosis Accuracy"),
        ("latency_attribution_score", "Latency Attribution Analysis"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Gate G Details</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config inactive — pass ExplainabilityConfig · ObservabilityConfig to your decorator to enable detailed metrics.</div>'

    breakdown = _build_score_breakdown("G", harness_g)
    return (
        f'<div class="gate-section" id="gate-g" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate G &nbsp;<span style="font-size:14px;color:#374151">Observability</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{judge_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Advanced / RAG / Conversation
# ---------------------------------------------------------------------------

def _build_advanced_section(adv_metrics: dict, rag_metrics: dict,
                             has_advanced: bool, has_rag: bool,
                             has_conversation: bool,
                             conversation_sessions: list) -> str:
    if not has_advanced and not has_rag and not has_conversation:
        return ""

    _HEADER = ('<div class="gate-section" id="advanced" style="border-left-color:#6366f1">'
               '<h2 style="color:#6366f1">Advanced Metrics</h2>')
    parts = [_HEADER]

    # DeepEval
    if has_advanced and adv_metrics:
        de_keys = [
            ("g_eval_score", "G-Eval"),
            ("hallucination_score", "Hallucination"),
            ("toxicity_score", "Toxicity"),
            ("bias_score", "Bias"),
            ("answer_relevancy_score", "Answer Relevancy"),
        ]
        rows = ""
        for k, label in de_keys:
            v = adv_metrics.get(k)
            if isinstance(v, dict) and v:
                mean_v = v.get("mean") or 0
                rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;font-size:12px;border-bottom:1px solid #f3f4f6">{label}</td>'
                    f'<td style="padding:5px 10px;font-weight:600;color:{_score_color(float(mean_v)*100,0.8,0.6)};border-bottom:1px solid #f3f4f6">{float(mean_v):.3f}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{v.get("min", 0):.2f}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{v.get("max", 0):.2f}</td>'
                    f'</tr>'
                )
        if rows:
            parts.append(
                f'<h3>DeepEval</h3>'
                f'<table class="mtable"><thead><tr><th>Metric</th><th>Avg</th><th>Min</th><th>Max</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>'
            )

    # RAG
    if has_rag and rag_metrics:
        rag_keys = [
            ("faithfulness", "Faithfulness"),
            ("answer_relevancy", "Answer Relevancy"),
            ("context_recall", "Context Recall"),
            ("context_precision", "Context Precision"),
        ]
        rows = ""
        for k, label in rag_keys:
            vals = rag_metrics.get(k, [])
            if vals:
                avg_v = sum(vals) / len(vals)
                rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;font-size:12px;border-bottom:1px solid #f3f4f6">{label}</td>'
                    f'<td style="padding:5px 10px;font-weight:600;color:{_score_color(avg_v*100,80,60)};border-bottom:1px solid #f3f4f6">{avg_v:.3f}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{min(vals):.2f}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{max(vals):.2f}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{len(vals)}</td>'
                    f'</tr>'
                )
        if rows:
            parts.append(
                f'<h3>RAG Metrics (Ragas)</h3>'
                f'<table class="mtable"><thead><tr><th>Metric</th><th>Avg</th><th>Min</th><th>Max</th><th>Count</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>'
            )

    # Conversation
    if has_conversation and conversation_sessions:
        rows = ""
        for sess in conversation_sessions[:20]:
            if isinstance(sess, dict):
                sid = sess.get("session_id", "—")
                turns = sess.get("turn_count", sess.get("turns", 0))
                score = sess.get("overall_score") or sess.get("score")
                ctx = sess.get("context_retention") or sess.get("context")
                score_str = f"{float(score) * 100:.1f}%" if score is not None else "—"
                ctx_str = f"{float(ctx) * 100:.1f}%" if ctx is not None else "—"
                rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;font-size:12px;border-bottom:1px solid #f3f4f6">{sid}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{turns}</td>'
                    f'<td style="padding:5px 10px;font-weight:600;color:{_score_color(float(score or 0)*100,80,60)};border-bottom:1px solid #f3f4f6">'
                    f'{score_str}</td>'
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">'
                    f'{ctx_str}</td>'
                    f'</tr>'
                )
        if rows:
            parts.append(
                f'<h3>Multi-Turn Conversation Sessions</h3>'
                f'<table class="mtable"><thead><tr><th>Session ID</th><th>Turns</th><th>Overall Score</th><th>Context Retention</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>'
            )

    if len(parts) == 1:          # header only — nothing measured, don't emit an orphan heading
        return ""
    parts.append('</div>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Failure / low-score case table (P1.1)
# ---------------------------------------------------------------------------
#
# 단일 리포트는 지금까지 집계값만 보여줬다 — "TCR 50%"는 알려주지만 *어떤* 태스크가
# *왜* 실패했는지는 JSON을 직접 파싱해야만 알 수 있었다. 개선 착수를 막는 가장 큰
# 정보 공백이라, worst-N 케이스를 question/response 요약 + 실패 사유와 함께 표로 낸다.

_CASE_TEXT_MAX = 180


def _norm_task_for_case(t: Any) -> dict[str, Any]:
    """TaskResult(monitor 경로) 또는 TaskRecord(rf 경로)를 케이스 표용 dict로 정규화."""
    raw = getattr(t, "raw", None)
    if isinstance(raw, dict):                       # loader.TaskRecord
        src = raw
        get = src.get
    else:                                           # core.TaskResult
        src = t
        get = lambda k, d=None: getattr(src, k, d)  # noqa: E731
    judge = get("llm_judge") or {}
    j_overall = None
    if isinstance(judge, dict) and not judge.get("skipped"):
        j_overall = (judge.get("scores") or {}).get("overall")
    errors = get("errors") or []
    return {
        "task_id": get("task_id") or "—",
        "task_type": get("task_type") or "",
        "success": bool(get("success", False)),
        "completion_score": _safe_float(get("completion_score"), None),
        "accuracy_score": _safe_float(get("accuracy_score"), None),
        "execution_time": _safe_float(get("execution_time"), None),
        "question": get("question") or "",
        "response": get("response") or "",
        "ground_truth": get("ground_truth") or "",
        "partial_reason": get("partial_reason") or "",
        "errors": [str(e) for e in errors][:3],
        "judge_overall": _safe_float(j_overall, None),
        "tool_calls": get("tool_calls") or [],
        "chain_steps": get("chain_steps") or [],
        "agent_interactions": get("agent_interactions") or [],
    }


_TRAJ_MAX_STEPS = 12


def _traj_summarize(v: Any, n: int = 80) -> str:
    if isinstance(v, (dict, list)):
        try:
            v = json.dumps(v, ensure_ascii=False, default=str)
        except Exception:
            v = str(v)
    return _clip(str(v), n)


_WF_W = 1000.0
_WF_LABEL_W = 250.0
_WF_ROW_H = 22.0


def _build_waterfall(items: list[Any]) -> str:
    """P25: inline-SVG waterfall for a step list that carries timing
    (start_ms/end_ms or per-step duration). "" when there is no usable timing —
    the caller then falls back to the flat step table."""
    try:
        from agent_evaluator.reporting.insights import parse_span_timeline

        tl = parse_span_timeline(items)
    except Exception:
        tl = None
    if not tl or not tl.get("spans") or not tl.get("total_ms"):
        return ""

    spans = tl["spans"][:_TRAJ_MAX_STEPS]
    total_ms = float(tl["total_ms"]) or 1.0
    bar_w = _WF_W - _WF_LABEL_W - 90.0
    scale = bar_w / total_ms
    crit = set(tl.get("critical_path") or [])
    height = _WF_ROW_H * len(spans) + 12.0
    parts = [
        f'<svg viewBox="0 0 {_WF_W:.0f} {height:.0f}" width="100%" '
        f'style="max-width:720px;font-size:10px" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
    ]
    for i, s in enumerate(spans):
        y = 6.0 + i * _WF_ROW_H
        x = _WF_LABEL_W + float(s["start_ms"]) * scale
        w = max(2.0, (float(s["end_ms"]) - float(s["start_ms"])) * scale)
        on_crit = s["name"] in crit
        fill = "#ef4444" if not s.get("ok", True) else ("#6366f1" if on_crit else "#a5b4fc")
        indent = min(int(s.get("depth", 0)), 6) * 10.0
        nm = _clip(str(s["name"]), 34)
        meta_bits = [f'{s["self_ms"]:.0f}ms']
        if isinstance(s.get("tokens"), (int, float)):
            meta_bits.append(f'{int(s["tokens"])}tok')
        if isinstance(s.get("cost"), (int, float)) and s["cost"]:
            meta_bits.append(_fmt_usd(s["cost"]))
        parts.append(
            f'<text x="{6 + indent:.0f}" y="{y + 14:.0f}" fill="#6b7280">{_esc(nm)}</text>'
            f'<rect x="{x:.1f}" y="{y + 4:.1f}" width="{w:.1f}" height="12" rx="2" '
            f'fill="{fill}"><title>{_esc(str(s["name"]))} — {" · ".join(meta_bits)}</title></rect>'
            f'<text x="{x + w + 4:.1f}" y="{y + 14:.0f}" fill="#9ca3af">'
            f'{" · ".join(meta_bits)}</text>'
        )
    parts.append("</svg>")

    hdr_bits = [f'{total_ms:.0f}ms total']
    if tl.get("total_tokens"):
        hdr_bits.append(f'{int(tl["total_tokens"])} tok')
    if tl.get("total_cost_usd"):
        hdr_bits.append(_fmt_usd(tl["total_cost_usd"]))
    bn = tl.get("bottleneck") or {}
    if bn.get("name"):
        hdr_bits.append(f'bottleneck: {_esc(_clip(str(bn["name"]), 30))} '
                        f'({bn.get("self_ms", 0):.0f}ms)')
    return (
        f'<div style="margin:4px 0 2px">'
        f'<div style="font-size:11px;color:#6b7280;margin-bottom:2px">'
        f'{" · ".join(hdr_bits)}</div>{"".join(parts)}</div>'
    )


def _build_trajectory(case: dict[str, Any]) -> str:
    """P7: per-step execution trace for a failure case — step → tool → in/out →
    outcome. Uses tool_calls, then chain_steps, then agent_interactions. Returns
    "" when the task carried no step data (common for plain QA). P25: when the
    steps carry timing, an inline-SVG waterfall is shown above the flat table."""
    tcs = case.get("tool_calls") or []
    steps = case.get("chain_steps") or []
    inter = case.get("agent_interactions") or []
    rows = ""
    kind = ""
    if tcs:
        kind = "tool calls"
        for i, c in enumerate(tcs[:_TRAJ_MAX_STEPS], 1):
            if not isinstance(c, dict):
                rows += f'<tr><td>{i}</td><td colspan="3">{_traj_summarize(c)}</td></tr>'
                continue
            name = c.get("tool_name") or c.get("tool") or c.get("name") or "—"
            args = c.get("parameters") or c.get("arguments") or c.get("input") or c.get("args")
            outp = c.get("output") or c.get("result") or c.get("response") or c.get("error") or ""
            ok = c.get("success", True)
            dur = c.get("duration") or c.get("duration_ms") or c.get("latency_ms")
            toks = c.get("tokens") or c.get("tokens_used") or c.get("total_tokens")
            meta = []
            if isinstance(dur, (int, float)):
                meta.append(f'{dur:.0f}ms' if dur >= 1 else f'{dur * 1000:.0f}µs')
            if isinstance(toks, (int, float)):
                meta.append(f'{int(toks)} tok')
            elif isinstance(toks, dict) and toks.get("total"):
                meta.append(f'{int(toks["total"])} tok')
            meta_s = f' <span style="color:#9ca3af">({" · ".join(meta)})</span>' if meta else ""
            oc = "#10b981" if ok else "#ef4444"
            rows += (
                f'<tr>'
                f'<td style="color:#9ca3af">{i}</td>'
                f'<td style="font-weight:600;white-space:nowrap">{_esc(str(name))}'
                f'<span style="color:{oc}">{" ✓" if ok else " ✗"}</span>{meta_s}</td>'
                f'<td style="font-size:11px;color:#6b7280">{_traj_summarize(args)}</td>'
                f'<td style="font-size:11px;color:#374151">→ {_traj_summarize(outp)}</td>'
                f'</tr>'
            )
    elif steps:
        kind = "chain steps"
        for i, s in enumerate(steps[:_TRAJ_MAX_STEPS], 1):
            if isinstance(s, dict):
                label = s.get("name") or s.get("step") or s.get("action") or s.get("type") or "step"
                detail = s.get("output") or s.get("input") or s.get("detail") or s
            else:
                label, detail = "step", s
            rows += (
                f'<tr><td style="color:#9ca3af">{i}</td>'
                f'<td style="font-weight:600;white-space:nowrap">{_esc(str(label))}</td>'
                f'<td colspan="2" style="font-size:11px;color:#374151">{_traj_summarize(detail, 140)}</td></tr>'
            )
    elif inter:
        kind = "agent interactions"
        for i, s in enumerate(inter[:_TRAJ_MAX_STEPS], 1):
            if isinstance(s, dict):
                frm = s.get("from") or s.get("from_agent") or s.get("sender") or "?"
                to = s.get("to") or s.get("to_agent") or s.get("receiver") or "?"
                msg = s.get("message") or s.get("content") or s.get("action") or s
            else:
                frm, to, msg = "?", "?", s
            rows += (
                f'<tr><td style="color:#9ca3af">{i}</td>'
                f'<td style="font-weight:600;white-space:nowrap">{_esc(str(frm))} → {_esc(str(to))}</td>'
                f'<td colspan="2" style="font-size:11px;color:#374151">{_traj_summarize(msg, 140)}</td></tr>'
            )
    if not rows:
        return ""
    total = len(tcs or steps or inter)
    more = (f'<tr><td></td><td colspan="3" style="color:#9ca3af;font-size:11px">'
            f'… {total - _TRAJ_MAX_STEPS} more step(s)</td></tr>'
            if total > _TRAJ_MAX_STEPS else "")
    waterfall = _build_waterfall(tcs or steps or inter)
    return (
        f'<details style="margin-top:6px"><summary style="cursor:pointer;font-size:11px;'
        f'color:#6366f1">▸ Trajectory ({total} {kind})</summary>'
        f'{waterfall}'
        f'<table class="mtable" style="margin-top:4px;font-size:12px"><tbody>{rows}{more}</tbody></table>'
        f'</details>'
    )


def _safe_float(v: Any, default: Any) -> Any:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _case_severity(c: dict[str, Any]) -> float:
    """정렬 키 — 낮을수록 심각(먼저 표시). 실패는 항상 상단."""
    comp = c["completion_score"] if c["completion_score"] is not None else 1.0
    acc = c["accuracy_score"] if c["accuracy_score"] is not None else 1.0
    base = min(comp, acc)
    return base - (1.0 if not c["success"] else 0.0)   # 실패면 -1 shift → 항상 앞


def _case_reason(c: dict[str, Any]) -> str:
    """이 태스크가 왜 저점/실패인지 한 줄로."""
    if c["partial_reason"]:
        return c["partial_reason"]
    if c["errors"]:
        return f"error: {c['errors'][0]}"
    bits = []
    if c["completion_score"] is not None and c["completion_score"] < 0.75:
        bits.append(f"incomplete ({c['completion_score'] * 100:.0f}%)")
    if c["accuracy_score"] is not None and c["accuracy_score"] < 0.7:
        bits.append(f"low accuracy ({c['accuracy_score'] * 100:.0f}%)")
    if c["judge_overall"] is not None and c["judge_overall"] < 6:
        bits.append(f"judge {c['judge_overall']:.1f}/10")
    return " · ".join(bits) or ("failed" if not c["success"] else "below target")


def _clip(s: str, n: int = _CASE_TEXT_MAX) -> str:
    s = " ".join(str(s).split())
    return _esc(s if len(s) <= n else s[: n - 1] + "…")


# P6.1: normalize a failure reason to a "theme" — strip numbers/paths/specifics so the
# same kind of failure clusters together.
#   "low ground_truth similarity (similarity 0%)"  → "low ground_truth similarity"
#   "incomplete (60%) · low accuracy (32%)" → "incomplete · low accuracy"
#   "error: TimeoutError: request to ... timed out"  → "error: TimeoutError"
_RE_NUM_PAREN = re.compile(r"\s*\(\s*[^)]*\d[^)]*\)")
_RE_NUM = re.compile(r"\b\d[\d.,%/:s]*\b")
_RE_ERR = re.compile(r"^error:\s*([A-Za-z_][A-Za-z0-9_.]*)")


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


def _build_failure_clusters(cases: list[dict[str, Any]], total_tasks: int) -> str:
    """실패/저점 케이스를 (사유 테마 × task_type)으로 군집화해 영향도 순으로 낸다.

    나열(_build_failure_cases의 표)과 달리 "9개 실패가 사실 2개 테마"임을 드러낸다.
    영향도 = 해당 테마 케이스 수 / 전체 태스크 수 (그 테마를 고치면 회복 가능한 상한).
    """
    if not cases or total_tasks <= 0:
        return ""
    from collections import defaultdict

    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        buckets[(_reason_signature(_case_reason(c)), c["task_type"] or "—")].append(c)
    if len(buckets) < 2 and len(cases) < 3:
        return ""   # 군집화가 의미 없을 만큼 적음

    ranked = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = ""
    for (sig, ttype), members in ranked[:8]:
        n = len(members)
        impact = n / total_tasks * 100.0
        rep = members[0]
        rep_q = _clip(rep["question"], 90) or "—"
        rows += (
            f'<tr>'
            f'<td style="font-weight:600">{_esc(sig)}</td>'
            f'<td style="white-space:nowrap">{_esc(ttype)}</td>'
            f'<td style="white-space:nowrap;text-align:right">{n} '
            f'<span style="color:#6b7280">(~{impact:.0f}%p)</span></td>'
            f'<td style="font-size:11px;color:#6b7280">e.g. {rep_q} '
            f'<span style="color:#9ca3af">[{_esc(rep["task_id"])}]</span></td>'
            f'</tr>'
        )
    return (
        '<h3 style="margin:4px 0 6px">Failure themes '
        '<span style="font-size:12px;color:#6b7280;font-weight:400">'
        '(fix the top theme first — "~%p" = max TCR recoverable)</span></h3>'
        '<table class="mtable"><thead><tr>'
        '<th>Theme</th><th>Task type</th><th>Count</th><th>Example</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
    )


def _effective_fail(*, success: Any, accuracy: Any, completion: Any) -> bool:
    """success 플래그만으로는 accuracy 실패를 못 잡으므로(create_taskresult가 완료
    기준으로만 success를 매김), _is_low와 같은 기준으로 "사실상 실패"를 판정한다."""
    if not bool(success):
        return True
    a = _safe_float(accuracy, None)
    c = _safe_float(completion, None)
    if a is not None and a < 0.7:
        return True
    return c is not None and c < 0.4


def _extract_task_outcomes(report: dict[str, Any] | None) -> dict[str, bool]:
    """결과 JSON dict → {task_id: effective_fail(bool)}. baseline 대조용."""
    if not report:
        return {}
    out: dict[str, bool] = {}
    for t in report.get("tasks") or []:
        if isinstance(t, dict) and t.get("task_id"):
            out[str(t["task_id"])] = _effective_fail(
                success=t.get("success", False),
                accuracy=t.get("accuracy_score"),
                completion=t.get("completion_score"),
            )
    return out


def _build_failure_lineage(cases: list[dict[str, Any]],
                           baseline: dict[str, Any] | None) -> str:
    """baseline 결과와 대조해 실패 집합의 변화(신규/지속/해결/회귀)를 낸다."""
    base_fail_map = _extract_task_outcomes(baseline)
    if not base_fail_map:
        return ""
    cur_fail = {
        c["task_id"] for c in cases
        if _effective_fail(success=c["success"], accuracy=c["accuracy_score"],
                           completion=c["completion_score"])
    }
    base_fail = {tid for tid, failed in base_fail_map.items() if failed}
    base_pass = {tid for tid, failed in base_fail_map.items() if not failed}

    regressed = sorted(cur_fail & base_pass)          # 지난번 통과 → 이번 실패
    new_untracked = sorted(cur_fail - set(base_fail_map))  # baseline에 없던 태스크가 실패
    persistent = sorted(cur_fail & base_fail)
    fixed = sorted(base_fail - cur_fail)              # 지난번 실패 → 이번 통과(또는 사라짐)

    def _chips(label: str, ids: list[str], color: str) -> str:
        if not ids:
            return ""
        shown = ", ".join(_esc(i) for i in ids[:8])
        more = f" +{len(ids) - 8}" if len(ids) > 8 else ""
        return (f'<p style="font-size:12px;margin:3px 0"><span style="color:{color};'
                f'font-weight:700">{label} ({len(ids)})</span> '
                f'<span style="color:#6b7280">{shown}{more}</span></p>')

    body = (
        _chips("📉 Regressed", regressed, "#dc2626")
        + _chips("♻️ Persistent", persistent, "#92400e")
        + _chips("🆕 New (not in baseline)", new_untracked, "#6b7280")
        + _chips("✅ Fixed since baseline", fixed, "#059669")
    )
    if not body:
        return ""
    return (
        '<h3 style="margin:4px 0 6px">Failure set vs baseline</h3>'
        + body
        + ('<p style="font-size:11px;color:#9ca3af;margin-top:4px">'
           'Regressed tasks (passed before, fail now) are the highest-priority fix.</p>'
           if regressed else "")
    )


def _build_score_breakdown_detail(sb: dict[str, Any] | None) -> str:
    """P23: a collapsible per-task "why this score" — the four accuracy signals
    and/or the judge's rationale + dimension scores."""
    if not sb:
        return ""
    bits = []
    ac = sb.get("accuracy_components")
    if isinstance(ac, dict) and ac:
        weak = sb.get("accuracy_weakest")
        cells = " · ".join(
            (f'<strong style="color:#dc2626">{k.replace("_", " ")} {v:.2f}</strong>'
             if k == weak else f'{k.replace("_", " ")} {v:.2f}')
            for k, v in ac.items()
        )
        bits.append(f'<div style="font-size:11px;color:#6b7280">accuracy signals: {cells}</div>')
    elif sb.get("accuracy_note"):
        bits.append(f'<div style="font-size:11px;color:#9ca3af">{_esc(sb["accuracy_note"])}</div>')
    jr = sb.get("judge_reasoning")
    jd = sb.get("judge_dimensions")
    if jr or jd:
        jd_txt = ""
        if isinstance(jd, dict) and jd:
            jd_txt = " · ".join(f'{k.replace("_", " ")} {v}/5' for k, v in jd.items())
        jo = sb.get("judge_overall")
        head = f'judge {jo}/10' if jo is not None else 'judge'
        bits.append(
            f'<div style="font-size:11px;color:#6b7280">{head}'
            + (f' ({_esc(jd_txt)})' if jd_txt else '')
            + (f' — "{_esc(str(jr))}"' if jr else '') + '</div>'
        )
    ws = sb.get("weakest_signal")
    if ws:
        bits.append(f'<div style="font-size:11px;color:#9ca3af">weakest signal: '
                    f'<code>{_esc(str(ws))}</code></div>')
    if not bits:
        return ""
    return (
        '<details style="margin-top:4px"><summary style="cursor:pointer;font-size:11px;'
        'color:#6366f1">▸ Score breakdown</summary>'
        f'<div style="margin-top:3px">{"".join(bits)}</div></details>'
    )


def _build_failure_cases(tasks: list[Any], *, limit: int = 12,
                         total_tasks: int | None = None,
                         baseline: dict[str, Any] | None = None) -> str:
    """실패/저점 태스크를 (1) 테마 군집 (2) baseline 대비 변화 (3) worst-N 표로 렌더링."""
    if not tasks:
        return ""
    cases = [_norm_task_for_case(t) for t in tasks]
    scored = sorted(cases, key=_case_severity)
    failed_n = sum(1 for c in cases if not c["success"])

    def _is_low(c: dict[str, Any]) -> bool:
        # accuracy는 신뢰할 만한 신호. completion_score는 명시적 completion_fn 없이
        # 0.5로 떨어지는 경우가 많아, 0.4 미만일 때만 저점으로 본다(자동 0.5는 제외).
        acc = c["accuracy_score"]
        comp = c["completion_score"]
        if acc is not None and acc < 0.7:
            return True
        if comp is not None and comp < 0.4:
            return True
        j = c["judge_overall"]
        return j is not None and j < 6.0

    # 실패 태스크가 있으면 그것들 우선. 없고 저점 태스크도 없으면 섹션 생략 —
    # 잘 통과한 리포트에 케이스 목록을 억지로 만들지 않는다.
    if failed_n == 0:
        low = [c for c in scored if _is_low(c)]
        if not low:
            return ""
        worst = low[:limit]
    else:
        worst = [c for c in scored if not c["success"]][:limit]
    if not worst:
        return ""

    # P23: per-task score decomposition, keyed by task_id.
    _sb_by_id: dict[str, dict[str, Any]] = {}
    try:
        from agent_evaluator.reporting.insights import _score_breakdowns_section

        for _b in _score_breakdowns_section(_review_dict_tasks(tasks)) or []:
            _sb_by_id[_b["task_id"]] = _b
    except Exception:
        pass

    rows = ""
    for c in worst:
        comp = "—" if c["completion_score"] is None else f"{c['completion_score'] * 100:.0f}%"
        acc = "—" if c["accuracy_score"] is None else f"{c['accuracy_score'] * 100:.0f}%"
        sev_col = "#ef4444" if not c["success"] else "#f59e0b"
        badge = ('<span class="badge badge-fail">FAIL</span>' if not c["success"]
                 else '<span class="badge badge-warn">LOW</span>')
        q = _clip(c["question"]) or '<span style="color:#9ca3af">—</span>'
        r = _clip(c["response"]) or '<span style="color:#9ca3af">—</span>'
        gt = _clip(c["ground_truth"], 120)
        gt_row = (f'<div style="font-size:11px;color:#6b7280;margin-top:3px">'
                  f'expected: {gt}</div>' if gt else "")
        type_row = (f'<br><span style="font-size:10px;color:#9ca3af">{_esc(c["task_type"])}</span>'
                    if c["task_type"] else "")
        traj = _build_trajectory(c)
        sb_row = _build_score_breakdown_detail(_sb_by_id.get(c["task_id"]))
        rows += (
            f'<tr>'
            f'<td style="vertical-align:top;white-space:nowrap">{badge}<br>'
            f'<span style="font-size:11px;color:#6b7280">{_esc(c["task_id"])}</span>{type_row}</td>'
            f'<td style="vertical-align:top">{q}'
            f'<div style="font-size:12px;color:#374151;margin-top:4px">→ {r}</div>'
            f'{gt_row}{sb_row}{traj}</td>'
            f'<td style="vertical-align:top;white-space:nowrap;font-size:12px">'
            f'C {comp}<br>A {acc}</td>'
            f'<td style="vertical-align:top;color:{sev_col};font-size:12px;font-weight:600">'
            f'{_esc(_case_reason(c))}</td>'
            f'</tr>'
        )

    total_pool = failed_n if failed_n else sum(1 for c in scored if _is_low(c))
    more = ""
    if total_pool > len(worst):
        _kind = "failed" if failed_n else "low-scoring"
        more = (f'<p style="font-size:12px;color:#6b7280;margin:8px 0 0">'
                f'… and {total_pool - len(worst)} more {_kind} task(s). '
                f'Open the JSON result file or dashboard for the full list.</p>')
    heading_n = total_pool
    label = "Failed" if failed_n else "Lowest-scoring"

    # P6: 표 위에 (1) 테마 군집 (2) baseline 대비 변화.
    _pool = [c for c in scored if not c["success"]] if failed_n else [c for c in scored if _is_low(c)]
    _total = total_tasks if total_tasks and total_tasks > 0 else len(cases)
    clusters_html = ""
    lineage_html = ""
    try:
        clusters_html = _build_failure_clusters(_pool, _total)
    except Exception:
        pass
    try:
        lineage_html = _build_failure_lineage(cases, baseline)
    except Exception:
        pass
    rag_html = ""
    try:
        rag_html = _build_rag_localization(tasks)
    except Exception:
        pass
    segments_html = ""
    try:
        segments_html = _build_failure_segments(tasks)
    except Exception:
        pass

    return (
        '<div class="gate-section" id="failure-cases" style="border-left-color:#ef4444">'
        f'<h2 style="color:#ef4444">🧪 {label} Cases '
        f'<span style="font-size:13px;color:#6b7280">'
        f'(showing {len(worst)} of {heading_n})</span></h2>'
        f'{lineage_html}'
        f'{rag_html}'
        f'{segments_html}'
        f'{clusters_html}'
        '<h3 style="margin:4px 0 6px">Worst cases</h3>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 12px">'
        'Failures before low-scorers, then by min(completion, accuracy). '
        'C = completion score · A = accuracy score.</p>'
        '<table class="mtable"><thead><tr>'
        '<th>Status</th><th>Question → Response</th><th>Score</th><th>Likely reason</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>{more}'
        '</div>'
    )


_TRIG_LABEL = {
    "retrieval_gap": ("Retrieval gap", "#dc2626"),
    "grounding": ("Grounding", "#d97706"),
    "tool_failure": ("Tool failure", "#7c3aed"),
    "runtime_error": ("Runtime error", "#b91c1c"),
}


_FE_VERDICT_STYLE = {
    "supported": ("supported", "#059669"),
    "contradicts_ground_truth": ("contradicts ground truth", "#dc2626"),
    "unsupported": ("unsupported", "#d97706"),
    "unverifiable": ("unverifiable", "#9ca3af"),
}


def _build_failure_explanations(fe: list[dict[str, Any]] | None) -> str:
    """P47: for the worst failures, the specific sentence that is wrong and where
    it came from (context chunk / tool output / hallucination)."""
    if not fe:
        return ""
    blocks = ""
    for r in fe:
        rows = ""
        for c in r.get("claims") or []:
            lbl, col = _FE_VERDICT_STYLE.get(
                c.get("verdict", ""), (c.get("verdict", ""), "#6b7280"))
            rows += (
                f'<tr><td style="font-size:12px;color:#374151">'
                f'{_esc(_clip(c.get("text", ""), 160))}</td>'
                f'<td style="white-space:nowrap;color:{col};font-weight:600;'
                f'font-size:11px">{_esc(lbl)}</td>'
                f'<td style="font-size:11px;color:#6b7280">{_esc(c.get("source", ""))}'
                f'</td></tr>'
            )
        wc = r.get("wrong_claim")
        wc_html = (
            f'<p style="font-size:12px;margin:4px 0 0"><strong>Wrong claim:</strong> '
            f'{_esc(_clip(wc, 180))} <span style="color:#9ca3af">'
            f'({_esc(r.get("wrong_claim_verdict", ""))}, '
            f'{_esc(r.get("wrong_claim_source", ""))})</span></p>'
            if wc else ""
        )
        blocks += (
            '<div style="border-top:1px solid #e5e7eb;padding:8px 0">'
            f'<div style="font-size:12px"><strong>{_esc(str(r.get("task_id", "")))}</strong> '
            f'<span style="color:#6b7280">{_esc(_clip(r.get("question", ""), 110))}</span></div>'
            f'<div style="font-size:11px;color:#9ca3af;margin:2px 0">GT: '
            f'{_esc(_clip(r.get("ground_truth", ""), 140))}</div>'
            '<table class="mtable" style="font-size:12px"><thead><tr>'
            '<th>Claim</th><th>Verdict</th><th>Source</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>{wc_html}</div>'
        )
    return (
        '<div class="gate-section" id="failure-explanations" '
        'style="border-left-color:#ef4444">'
        '<h2 style="color:#1e2030">Claim-Level Failure Explanation</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">Each failing '
        'response split into claims — which one is wrong, and where it came from. '
        'Heuristic (token overlap + negation + number mismatch); candidate, not a '
        'verdict.</p>'
        f'{blocks}</div>'
    )


def _build_failure_segments(tasks: list[Any] | None) -> str:
    """P30: cluster failing questions by lexical topic ("fails on multi-entity
    comparison questions") and pin each failure to the retrieved passage or tool
    step that most likely caused it."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import (
            _failure_segments_section,
            _failure_triggers_section,
        )

        norm = _review_dict_tasks(tasks)
        segs = _failure_segments_section(norm)
        trigs = _failure_triggers_section(norm)
    except Exception:
        segs = trigs = None
    if not segs and not trigs:
        return ""

    seg_html = ""
    _real_segs = [s for s in (segs or []) if not s.get("catch_all")]
    if segs and not _real_segs:
        # Only the catch-all bucket clustered — a one-liner, not a single-row table.
        _ca = segs[0]
        seg_html = (
            '<h3 style="margin:4px 0 6px">Failure segments</h3>'
            f'<p style="font-size:12px;color:#6b7280;margin:0">The {_ca.get("n", 0)} '
            'failing questions span unrelated topics — no dominant lexical cluster. '
            'Use the root-cause clusters in Path to Green instead.</p>'
        )
    elif _real_segs:
        rows = ""
        for s in _real_segs:
            reason = _esc(s.get("dominant_reason", ""))
            ex = _esc(_clip(s.get("example_question", ""), 110))
            rows += (
                f'<tr><td style="font-weight:600">{_esc(s.get("label", ""))}</td>'
                f'<td style="text-align:right">{s.get("n", 0)}'
                f'<div style="font-size:11px;color:#9ca3af">'
                f'{s.get("share_of_failures_pct")}% of failures</div></td>'
                f'<td style="font-size:11px;color:#6b7280">{reason}</td>'
                f'<td style="font-size:11px;color:#374151">{ex}</td></tr>'
            )
        seg_html = (
            '<h3 style="margin:4px 0 6px">Failure segments '
            '<span style="font-size:12px;color:#6b7280">'
            '&mdash; failing questions grouped by topic</span></h3>'
            '<table class="mtable"><thead><tr><th>Topic</th><th>Size</th>'
            '<th>Common reason</th><th>Example question</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )

    trig_html = ""
    if trigs:
        items = ""
        for tr in trigs:
            lbl, col = _TRIG_LABEL.get(tr.get("kind", ""), (tr.get("kind", ""), "#6b7280"))
            items += (
                f'<li><strong>{_esc(str(tr.get("task_id", "")))}</strong> '
                f'<span style="color:{col};font-weight:700">[{_esc(lbl)}]</span> '
                f'<span style="color:#374151">{_esc(_clip(tr.get("detail", ""), 170))}</span></li>'
            )
        trig_html = (
            '<h3 style="margin:14px 0 6px">Likely triggers '
            '<span style="font-size:12px;color:#6b7280">— the passage or step that most '
            'likely caused each failure</span></h3>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7">{items}</ul>'
        )

    return seg_html + trig_html


_RAG_CLASS_LABEL = {
    "retrieval_miss": ("Retrieval miss", "#dc2626"),
    "grounding_miss": ("Grounding miss", "#d97706"),
    "generation_error": ("Generation error", "#7c3aed"),
    "ok": ("Answered OK", "#059669"),
}


def _build_rag_localization(tasks: list[Any] | None) -> str:
    """P11: split RAG failures into retrieval-miss / grounding-miss / generation-error.

    The fix differs completely per class (top_k/re-rank vs prompt vs decoding), so
    an aggregate faithfulness/recall number alone never told the reader which lever
    to pull. Reuses ``insights.rag_localization`` (coarse, deterministic, no ML).
    """
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import rag_localization

        norm = [_norm_task_for_case(t) for t in tasks]
        loc = rag_localization([
            {
                "task_id": c["task_id"], "response": c["response"],
                "context": _task_context(t), "ground_truth": c["ground_truth"],
                "accuracy_score": c["accuracy_score"],
                "llm_judge": getattr(t, "llm_judge", None) if not isinstance(
                    getattr(t, "raw", None), dict) else (t.raw or {}).get("llm_judge"),
                "extra": _task_extra(t),
            }
            for t, c in zip(tasks, norm)
        ])
    except Exception:
        loc = None
    if not loc or loc.get("n_rag_tasks", 0) == 0:
        return ""
    by = loc.get("by_class") or {}
    failing = {k: v for k, v in by.items() if k != "ok"}
    if not failing:
        return ""

    rows = ""
    for klass in ("retrieval_miss", "grounding_miss", "generation_error"):
        n = by.get(klass, 0)
        if not n:
            continue
        lbl, col = _RAG_CLASS_LABEL[klass]
        fix = (loc.get("remediation_by_class") or {}).get(klass, "")
        rows += (
            f'<tr><td style="font-weight:600;color:{col};white-space:nowrap">{lbl}</td>'
            f'<td style="text-align:right;white-space:nowrap">{n}</td>'
            f'<td style="font-size:12px;color:#4b5563">{_esc(fix)}</td></tr>'
        )
    ex = ""
    for e in (loc.get("unsupported_claim_examples") or [])[:5]:
        lbl, col = _RAG_CLASS_LABEL.get(e.get("klass", ""), ("", "#6b7280"))
        claims = "; ".join(_esc(_clip(s, 100)) for s in e.get("unsupported_claims") or [])
        cr = e.get("context_recall")
        cr_s = f' · recall {cr:.2f}' if isinstance(cr, (int, float)) else ""
        ex += (
            f'<div style="font-size:11px;color:#6b7280;margin:2px 0">'
            f'<span style="color:{col};font-weight:600">[{lbl}]</span> '
            f'<span style="color:#9ca3af">{_esc(e.get("task_id", ""))}{cr_s}</span> '
            f'— unsupported: {claims}</div>'
        )
    dominant = loc.get("dominant_failure")
    dom_s = ""
    if dominant:
        lbl, col = _RAG_CLASS_LABEL.get(dominant, ("", ""))
        dom_s = (f'<p style="font-size:13px;margin:0 0 6px"><strong>Dominant RAG failure: '
                 f'<span style="color:{col}">{lbl}</span></strong> — fix this class first.</p>')
    return (
        '<h3 style="margin:10px 0 6px">RAG failure localization '
        f'<span style="font-size:12px;color:#6b7280;font-weight:400">'
        f'({loc["n_rag_tasks"]} task(s) with retrieved context)</span></h3>'
        f'{dom_s}'
        '<table class="mtable"><thead><tr>'
        '<th>Failure type</th><th>Count</th><th>What to change</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        + (f'<div style="margin-top:6px">{ex}</div>' if ex else "")
    )


def _task_context(t: Any) -> str:
    raw = getattr(t, "raw", None)
    if isinstance(raw, dict):
        return raw.get("context") or ""
    return getattr(t, "context", "") or ""


def _spark_svg(values: list[float], *, lo: float = 0.0, hi: float = 1.0,
               w: int = 110, h: int = 22, color: str = "#6366f1") -> str:
    """Tiny inline SVG sparkline for a 0–1 series."""
    pts = [v for v in values if isinstance(v, (int, float))]
    if len(pts) < 2:
        return ""
    span = (hi - lo) or 1.0
    step = w / (len(pts) - 1)
    coords = " ".join(
        f"{i * step:.1f},{h - (min(max(v, lo), hi) - lo) / span * (h - 2) - 1:.1f}"
        for i, v in enumerate(pts)
    )
    last = pts[-1]
    cy = h - (min(max(last, lo), hi) - lo) / span * (h - 2) - 1
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'style="vertical-align:middle">'
        f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<circle cx="{(len(pts) - 1) * step:.1f}" cy="{cy:.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _build_history_trend(results_dir: Any, current_file: Any = None) -> str:
    """P13: scan sibling result files → per-Gate sparkline + "down N runs in a
    row" badge. A single report is point-in-time; this adds the direction."""
    if not results_dir:
        return ""
    try:
        from agent_evaluator.reporting.history import scan_history, trend_summary

        hist = scan_history(results_dir, exclude=current_file)
        summ = trend_summary(hist)
    except Exception:
        return ""
    if summ.get("n_runs", 0) < 3:
        return ""   # need a few runs before a trend is meaningful

    rows = ""
    for g in "ABCDEFG":
        gs = (summ.get("gates") or {}).get(g)
        if not gs:
            continue
        series = [r["gate_scores"].get(g) for r in hist]
        series = [s for s in series if isinstance(s, (int, float))]
        slope = gs["slope"]
        dec = gs["consecutive_decline"]
        col = "#dc2626" if slope < -0.02 else ("#059669" if slope > 0.02 else "#6b7280")
        badge = ""
        if dec >= 2:
            badge = (f'<span style="background:#fee2e2;color:#b91c1c;font-size:11px;'
                     f'font-weight:700;padding:1px 6px;border-radius:8px;margin-left:6px">'
                     f'↓ {dec} runs in a row</span>')
        rows += (
            f'<tr><td style="font-weight:600">Gate {g}</td>'
            f'<td>{_spark_svg(series, color=col)}</td>'
            f'<td style="white-space:nowrap;font-size:12px">{gs["first"]:.2f} → '
            f'<strong>{gs["last"]:.2f}</strong> '
            f'<span style="color:{col}">({slope:+.2f})</span>{badge}</td></tr>'
        )
    if not rows:
        return ""
    _fr, _lr = summ.get("first_run"), summ.get("last_run")
    _range = (f'<p style="font-size:11px;color:#9ca3af;margin:0 0 6px">'
              f'{_esc(str(_fr))} &rarr; {_esc(str(_lr))} · first &rarr; last score per Gate. '
              f'This "first" run may differ from the RCA baseline below.</p>'
              if _fr and _lr else "")
    return (
        '<div class="gate-section" id="history-trend" style="border-left-color:#0ea5e9">'
        f'<h2 style="color:#1e2030">Trend '
        f'<span style="font-size:13px;color:#6b7280">'
        f'(last {summ["n_runs"]} runs in this directory)</span></h2>'
        f'{_range}'
        '<table class="mtable"><tbody>' + rows + '</tbody></table>'
        '</div>'
    )


def _build_change_ledger(results_dir: Any) -> str:
    """P13: recommendation_outcomes.jsonl as a browsable "which change moved
    which Gate" table — the static-report counterpart of the dashboard's
    Recommendation Outcome History."""
    if not results_dir:
        return ""
    try:
        from agent_evaluator.reporting.history import load_change_ledger

        recs = load_change_ledger(results_dir)
    except Exception:
        return ""
    if not recs:
        return ""
    rows = ""
    for r in recs:
        verd = str(r.get("verdict") or "")
        col = {"confirmed": "#059669", "refuted": "#dc2626"}.get(verd, "#6b7280")
        d = r.get("gate_delta")
        d_s = f'{d:+.3f}' if isinstance(d, (int, float)) else "—"
        rows += (
            f'<tr><td style="font-size:11px;color:#6b7280;white-space:nowrap">'
            f'{_esc(str(r.get("recorded_at") or "")[:19].replace("T", " "))}</td>'
            f'<td>{_esc(_clip(str(r.get("recommendation_id") or r.get("note") or "—"), 60))}</td>'
            f'<td style="white-space:nowrap">{_esc(str(r.get("target_gate") or "—"))}</td>'
            f'<td style="color:{col};font-weight:600">{_esc(verd or "—")}</td>'
            f'<td style="text-align:right;white-space:nowrap">{d_s}</td>'
            f'<td style="font-size:11px;color:#6b7280">{_esc(_clip(str(r.get("note") or ""), 80))}</td></tr>'
        )
    return (
        '<div class="gate-section" id="change-ledger" style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">Change Ledger '
        '<span style="font-size:13px;color:#6b7280">(recorded improvement outcomes)</span></h2>'
        '<table class="mtable"><thead><tr>'
        '<th>Recorded</th><th>Change</th><th>Gate</th><th>Verdict</th>'
        '<th>Δ score</th><th>Note</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '</div>'
    )


def _review_dict_tasks(tasks: list[Any]) -> list[dict[str, Any]]:
    """Normalize TaskResult / TaskRecord to the plain dicts the insights sub-
    sections consume (shared by the P14/P15 report helpers)."""
    out = []
    for t in tasks:
        c = _norm_task_for_case(t)
        out.append({
            "task_id": c["task_id"], "task_type": c["task_type"],
            "success": c["success"], "question": c["question"],
            "response": c["response"], "ground_truth": c["ground_truth"],
            "accuracy_score": c["accuracy_score"], "completion_score": c["completion_score"],
            # SPEC-041 P35: carry the failure reason so the insights sections
            # (_task_reason -> failure_clusters / readiness.fix_plan /
            # failure_segments / failure_triggers) get the real signature, not
            # the generic "incomplete · low accuracy" fallback.
            "partial_reason": c["partial_reason"], "errors": c["errors"],
            "tool_calls": c["tool_calls"], "agent_interactions": c["agent_interactions"],
            "context": _task_context(t), "extra": _task_extra(t),
            "attempts": getattr(t, "attempts", None) if not isinstance(getattr(t, "raw", None), dict)
                        else (t.raw or {}).get("attempts"),
            "tokens_used": getattr(t, "tokens_used", None) if not isinstance(getattr(t, "raw", None), dict)
                           else (t.raw or {}).get("tokens_used"),
            "llm_judge": (t.raw.get("llm_judge") if isinstance(getattr(t, "raw", None), dict)
                          else getattr(t, "llm_judge", None)),
        })
    return out


def _build_review_queue(tasks: list[Any] | None,
                        current: dict[str, Any] | None,
                        baseline: dict[str, Any] | None) -> str:
    """P15: the HITL triage list — which tasks a human should look at, ranked,
    and why. Assembled from evaluator disagreement, suspicious labels, regressed
    failures and borderline scores (same data as insights.review_queue)."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import (
            _eval_set_quality_section,
            _evaluator_trust_section,
            _failure_lineage_section,
            _review_queue_section,
        )

        dt = _review_dict_tasks(tasks)
        hg = ((current or {}).get("extra_metrics") or {}).get("harness_groups") or {}
        rq = _review_queue_section(
            dt,
            evaluator_trust=_evaluator_trust_section(dt, current or {}),
            failure_lineage=_failure_lineage_section(dt, baseline),
            eval_set_quality=_eval_set_quality_section(dt, baseline, hg),
        )
    except Exception:
        rq = None
    if not rq or not rq.get("items"):
        return ""

    rows = ""
    for it in rq["items"]:
        pri = it.get("priority", "medium")
        col = {"high": "#dc2626", "medium": "#d97706", "low": "#6b7280"}.get(pri, "#6b7280")
        reasons = "; ".join(_esc(r) for r in it.get("reasons") or [])
        rows += (
            f'<tr><td style="white-space:nowrap"><span style="color:{col};font-weight:700">'
            f'{pri.upper()}</span></td>'
            f'<td style="white-space:nowrap;font-size:12px">{_esc(it.get("task_id", ""))}</td>'
            f'<td style="font-size:12px;color:#4b5563">{reasons}</td></tr>'
        )
    bp = rq.get("by_priority") or {}
    return (
        '<div class="gate-section" id="review-queue" style="border-left-color:#7c3aed">'
        '<h2 style="color:#1e2030">Human Review Queue '
        f'<span style="font-size:13px;color:#6b7280">'
        f'({bp.get("high", 0)} high · {bp.get("medium", 0)} medium)</span></h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 10px">'
        'Tasks whose automated verdict is least trustworthy — resolve these first, '
        'then <code>agent-eval dataset promote &lt;result.json&gt;</code> '
        'to turn them into golden regression cases.</p>'
        '<table class="mtable"><thead><tr>'
        '<th>Priority</th><th>Task</th><th>Why review</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '</div>'
    )


def _build_metric_signal(ms: dict[str, Any] | None) -> str:
    """P46: which per-task metrics are redundant, and (with extra.outcome) which
    actually predict the downstream result."""
    if not ms or not ms.get("correlations"):
        return ""
    red = ms.get("redundant_pairs") or []
    red_html = ""
    if red:
        rows = "".join(f'<li>{_esc(r.get("note", ""))}</li>' for r in red)
        red_html = (
            '<h3 style="margin:8px 0 4px">Redundant metrics</h3>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7">{rows}</ul>'
        )
    oc = ms.get("outcome_correlation") or []
    oc_html = ""
    if oc:
        rows = ""
        for d in oc:
            _c = "#059669" if abs(d["r"]) >= 0.4 else (
                "#d97706" if abs(d["r"]) >= 0.15 else "#dc2626")
            rows += (
                f'<tr><td>{_esc(d["metric"])}</td>'
                f'<td style="text-align:right;color:{_c};font-weight:600">'
                f'{d["r"]:+.2f}</td><td style="text-align:right">{d["n"]}</td></tr>'
            )
        oc_html = (
            '<h3 style="margin:12px 0 4px">Predicts the recorded outcome '
            '<span style="font-size:12px;color:#6b7280">(extra.outcome)</span></h3>'
            '<table class="mtable"><thead><tr><th>Metric</th><th>r</th><th>N</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )
    corr_rows = "".join(
        f'<tr><td>{_esc(c["a"])} ↔ {_esc(c["b"])}</td>'
        f'<td style="text-align:right">{c["r"]:+.2f}</td></tr>'
        for c in sorted(ms["correlations"], key=lambda c: -abs(c["r"]))
    )
    return (
        '<div class="gate-section" id="metric-signal" style="border-left-color:#0891b2">'
        '<h2 style="color:#1e2030">Metric Signal</h2>'
        f'<p style="color:#6b7280;font-size:13px;margin:0 0 6px">{_esc(ms.get("note", ""))}</p>'
        f'{red_html}{oc_html}'
        '<h3 style="margin:12px 0 4px">Pairwise correlation</h3>'
        '<table class="mtable"><thead><tr><th>Pair</th><th>r</th></tr></thead>'
        f'<tbody>{corr_rows}</tbody></table></div>'
    )


def _build_evaluator_reliability(tasks: list[Any] | None,
                                 current: dict[str, Any] | None) -> str:
    """P14: how much can the reader trust the numbers? Surfaces judge-vs-heuristic
    agreement, and judge calibration / self-consistency when a run stashed them."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import _evaluator_trust_section

        norm = [_norm_task_for_case(t) for t in tasks]
        et = _evaluator_trust_section(
            [
                {"task_id": c["task_id"], "accuracy_score": c["accuracy_score"],
                 "llm_judge": (t.raw.get("llm_judge") if isinstance(getattr(t, "raw", None), dict)
                               else getattr(t, "llm_judge", None))}
                for t, c in zip(tasks, norm)
            ],
            current or {},
        )
    except Exception:
        et = None
    if not et:
        return ""

    lvl = et.get("trust_level", "high")
    col = {"high": "#059669", "medium": "#d97706", "low": "#dc2626"}.get(lvl, "#6b7280")
    reasons = et.get("trust_reasons") or []
    reason_html = ""
    if reasons:
        reason_html = (
            '<ul style="margin:6px 0 0 18px;font-size:12px;line-height:1.7;color:#4b5563">'
            + "".join(f"<li>{_esc(r)}</li>" for r in reasons) + "</ul>"
        )

    jvh = et.get("judge_vs_heuristic")
    jvh_html = ""
    if jvh:
        dis = jvh.get("disagreements") or []
        dis_rows = "".join(
            f'<tr><td>{_esc(d.get("task_id", ""))}</td>'
            f'<td style="text-align:right">{d.get("judge", 0):.2f}</td>'
            f'<td style="text-align:right">{d.get("heuristic", 0):.2f}</td>'
            f'<td style="text-align:right;color:#dc2626">{d.get("diff", 0):.2f}</td></tr>'
            for d in dis[:8]
        )
        dis_tbl = (
            '<table class="mtable" style="margin-top:4px"><thead><tr>'
            '<th>Task</th><th>Judge</th><th>Heuristic</th><th>|Δ|</th>'
            f'</tr></thead><tbody>{dis_rows}</tbody></table>' if dis_rows else ""
        )
        jvh_html = (
            f'<p style="font-size:12px;margin:8px 0 0;color:#4b5563">'
            f'LLM judge vs token-overlap scorer over {jvh["n_comparable"]} task(s): '
            f'<strong>{jvh["agreement_rate"] * 100:.0f}%</strong> agree '
            f'(mean |Δ| {jvh["mean_abs_diff"]:.2f}).</p>{dis_tbl}'
        )

    calib = et.get("judge_calibration")
    calib_html = ""
    if isinstance(calib, dict) and calib.get("dimensions"):
        rows = ""
        for dim, v in (calib["dimensions"] or {}).items():
            if not isinstance(v, dict) or not v.get("n"):
                continue
            rows += (
                f'<tr><td>{_esc(dim)}</td>'
                f'<td style="text-align:right">{v.get("mean_absolute_error", "—")}</td>'
                f'<td style="text-align:right">{v.get("cohen_kappa_quadratic", "—")}</td>'
                f'<td style="text-align:right">{v.get("n", 0)}</td></tr>'
            )
        if rows:
            calib_html = (
                '<p style="font-size:12px;margin:10px 0 2px;color:#4b5563">'
                'Judge vs human golden labels:</p>'
                '<table class="mtable"><thead><tr>'
                '<th>Dimension</th><th>MAE</th><th>Cohen κ (quad)</th><th>n</th>'
                f'</tr></thead><tbody>{rows}</tbody></table>'
            )

    sc = et.get("judge_self_consistency")
    sc_html = ""
    if isinstance(sc, dict) and isinstance(sc.get("agreement"), (int, float)):
        sc_html = (
            f'<p style="font-size:12px;margin:10px 0 0;color:#4b5563">'
            f'Judge self-consistency (k={sc.get("k", "?")}): '
            f'<strong>{sc["agreement"] * 100:.0f}%</strong> of repeat-scoring pairs '
            f'within 1.0 (stdev {sc.get("overall_stdev", "?")}).</p>'
        )

    return (
        '<div class="gate-section" id="evaluator-reliability" style="border-left-color:#0891b2">'
        '<h2 style="color:#1e2030">Evaluator Reliability</h2>'
        f'<p style="font-size:14px;font-weight:700;color:{col}">Evaluator trust: {lvl.upper()}</p>'
        '<p style="color:#6b7280;font-size:13px;margin:2px 0 0">'
        'Every metric that uses the LLM judge inherits its error. '
        'A low trust level demotes the deployment-readiness confidence.</p>'
        f'{reason_html}{jvh_html}{calib_html}{sc_html}'
        '</div>'
    )


def _build_eval_set_quality(tasks: list[Any] | None,
                            baseline: dict[str, Any] | None,
                            harness_groups: dict[str, Any],
                            precomputed: dict[str, Any] | None = None) -> str:
    """P12 + P45: the eval set as a first-class object — coverage, balance,
    near-duplicates, "is this Gate exercised at all", suspicious labels, a
    capability-coverage matrix, prompt contamination, targeted additions."""
    q = precomputed
    if not q:
        if not tasks:
            return ""
        try:
            from agent_evaluator.reporting.insights import _eval_set_quality_section

            norm = [_norm_task_for_case(t) for t in tasks]
            q = _eval_set_quality_section(
                [
                    {
                        "task_id": c["task_id"], "task_type": c["task_type"],
                        "question": c["question"], "ground_truth": c["ground_truth"],
                        "accuracy_score": c["accuracy_score"],
                        "agent_interactions": c["agent_interactions"],
                        "tool_calls": c["tool_calls"], "context": _task_context(t),
                    }
                    for t, c in zip(tasks, norm)
                ],
                baseline, harness_groups or {},
            )
        except Exception:
            q = None
    if not q:
        return ""
    hist = q.get("task_type_histogram") or {}
    warnings = q.get("coverage_warnings") or []
    dups = q.get("near_duplicate_clusters") or []
    susp = q.get("suspicious_ground_truth") or []
    if not (warnings or dups or susp) and len(hist) <= 1:
        return ""   # nothing worth a section

    hist_bar = ""
    if hist:
        total = sum(hist.values()) or 1
        for tt, n in sorted(hist.items(), key=lambda kv: -kv[1]):
            hist_bar += (
                f'<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin:2px 0">'
                f'<span style="width:90px;color:#4b5563">{_esc(tt)}</span>'
                f'<span style="height:12px;background:#6366f1;border-radius:2px;'
                f'width:{n / total * 240:.0f}px;min-width:2px"></span>'
                f'<span style="color:#6b7280">{n}</span></div>'
            )
    warn_html = ""
    if warnings:
        warn_html = (
            '<ul style="margin:6px 0 0 18px;font-size:12px;line-height:1.7;color:#92400e">'
            + "".join(f'<li>{_esc(w)}</li>' for w in warnings)
            + '</ul>'
        )
    dup_html = ""
    if dups:
        rows = "".join(
            f'<li>{_esc(_clip(d.get("question", ""), 90))} '
            f'<span style="color:#9ca3af">[{_esc(", ".join(d.get("task_ids", [])))}]</span></li>'
            for d in dups
        )
        dup_html = (
            '<p style="margin:8px 0 2px;font-size:12px;color:#6b7280">'
            f'Near-duplicate questions ({len(dups)} cluster(s)) — dedupe to avoid '
            'over-weighting one case:</p>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7">{rows}</ul>'
        )
    susp_html = ""
    if susp:
        rows = "".join(
            f'<li><strong>{_esc(s.get("task_id", ""))}</strong> — {_esc(s.get("reason", ""))}</li>'
            for s in susp
        )
        susp_html = (
            '<p style="margin:8px 0 2px;font-size:12px;color:#6b7280">'
            'Suspicious ground truth / questions:</p>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7;color:#7c2d12">{rows}</ul>'
        )
    # P45: capability-coverage matrix
    cov = q.get("capability_coverage") or {}
    cov_html = ""
    for dim, vals in (cov.get("cells") or {}).items():
        cells = " · ".join(
            f'{_esc(v)} <strong>{c["n"]}</strong>'
            + (f' <span style="color:#dc2626">({c["fail_n"]} fail)</span>'
               if c.get("fail_n") else "")
            for v, c in vals.items()
        )
        cov_html += (
            f'<div style="font-size:12px;margin:2px 0"><span style="color:#6b7280;'
            f'width:120px;display:inline-block">{_esc(dim)}</span>{cells}</div>'
        )
    if cov_html:
        cov_html = ('<h3 style="margin:12px 0 4px">Capability coverage</h3>' + cov_html)

    # P45: contamination
    contam = q.get("contamination") or []
    contam_html = ""
    if contam:
        rows = "".join(
            f'<li><strong>{_esc(c["task_id"])}</strong> — {_esc(c["field"])} shares '
            f'{c["overlap_pct"]}% of its 4-grams with the system prompt: '
            f'<span style="color:#7c2d12">“{_esc(_clip(c["snippet"], 90))}”</span></li>'
            for c in contam
        )
        contam_html = (
            '<h3 style="margin:12px 0 4px" style="color:#b91c1c">⚠️ Prompt '
            'contamination</h3>'
            '<p style="font-size:12px;color:#6b7280;margin:0">These tasks appear in '
            'the prompt / few-shot block — their scores are inflated.</p>'
            f'<ul style="margin:2px 0 0 18px;font-size:12px;line-height:1.7">{rows}</ul>'
        )

    # P45: targeted additions
    adds = q.get("targeted_additions") or []
    adds_html = ""
    if adds:
        rows = "".join(
            f'<li>{_esc(a.get("reason", ""))}</li>' for a in adds
        )
        adds_html = (
            '<h3 style="margin:12px 0 4px">What to add</h3>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7">{rows}</ul>'
        )

    clean_html = ""
    if not (warnings or dups or susp or contam or adds):
        clean_html = (
            '<p style="margin:8px 0 0;font-size:12px;color:#059669">'
            '✓ No coverage, balance, near-duplicate, contamination or '
            'suspicious-label issues detected in this eval set.</p>'
        )
    return (
        '<div class="gate-section" id="eval-set-quality" style="border-left-color:#8b5cf6">'
        '<h2 style="color:#1e2030">Eval-Set Quality</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 8px">'
        'A verdict is only as good as the set it is measured on.</p>'
        f'{hist_bar}{warn_html}{contam_html}{cov_html}{adds_html}{dup_html}{susp_html}'
        f'{clean_html}'
        '</div>'
    )


def _build_slice_analysis(tasks: list[Any] | None,
                          baseline: dict[str, Any] | None) -> str:
    """P10: per-task_type TCR/accuracy with CIs, and — with a baseline — the
    per-slice delta + a two-sample bootstrap significance flag. Answers "the
    regression is entirely in the rag cohort; qa is flat"."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import _slice_analysis_section

        norm = [_norm_task_for_case(t) for t in tasks]
        rows_data = _slice_analysis_section(
            [
                {"task_type": c["task_type"], "completion_score": c["completion_score"],
                 "accuracy_score": c["accuracy_score"]}
                for c in norm
            ],
            baseline,
        )
    except Exception:
        rows_data = []
    if len(rows_data) < 2:
        return ""   # a single slice adds nothing over the headline numbers

    has_base = any("tcr_delta_pp" in r for r in rows_data)
    body = ""
    for r in rows_data:
        tcr = r.get("tcr_pct")
        ci = r.get("tcr_ci_pct")
        acc = r.get("accuracy_pct")
        tcr_cell = "—"
        if tcr is not None:
            ci_s = (f' <span style="color:#9ca3af">({ci[0]:.0f}–{ci[1]:.0f})</span>'
                    if ci else "")
            tcr_cell = f'{tcr:.1f}%{ci_s}'
        acc_cell = f'{acc:.1f}%' if acc is not None else "—"
        delta_cell = ""
        if has_base:
            d = r.get("tcr_delta_pp")
            if d is None:
                delta_cell = '<td style="color:#9ca3af">—</td>'
            else:
                sig = r.get("significant")
                col = ("#dc2626" if d < 0 else "#059669") if sig else "#6b7280"
                tag = " *" if sig else ""
                dci = r.get("tcr_delta_ci_pp")   # already in pp
                ci_txt = (f' <span style="color:#9ca3af;font-weight:400">'
                          f'CI [{dci[0]:+.0f}, {dci[1]:+.0f}]</span>'
                          if isinstance(dci, (list, tuple)) and len(dci) == 2 else "")
                delta_cell = (f'<td style="color:{col};font-weight:600;white-space:nowrap">'
                              f'{d:+.1f}pp{tag}{ci_txt}</td>')
        body += (
            f'<tr><td style="font-weight:600">{_esc(r.get("task_type", "—"))}</td>'
            f'<td style="text-align:right">{r.get("n", 0)}</td>'
            f'<td style="text-align:right;white-space:nowrap">{tcr_cell}</td>'
            f'<td style="text-align:right">{acc_cell}</td>'
            f'{delta_cell}</tr>'
        )

    head = ('<th>Task type</th><th>N</th><th>TCR (95% CI)</th><th>Accuracy</th>'
            + ('<th>Δ vs baseline</th>' if has_base else ''))
    note = ('<p style="font-size:11px;color:#9ca3af;margin:4px 0 0">'
            '* = the two-sample bootstrap 95% CI of the difference excludes 0 '
            '(significant for that slice).</p>' if has_base else '')
    return (
        '<div class="gate-section" id="slice-analysis" style="border-left-color:#6366f1">'
        '<h2 style="color:#1e2030">Per-Slice Breakdown</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 10px">'
        'A headline metric can hide a regression concentrated in one cohort. '
        'Each row is a <code>task_type</code>.</p>'
        f'<table class="mtable"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
        f'{note}</div>'
    )


def _build_metadata_slices(ms: list[dict[str, Any]] | None) -> str:
    """P28: the same per-slice TCR/Δ table as Per-Slice Breakdown, but keyed on
    scalar `extra` metadata (model, prompt_variant, difficulty…) auto-discovered
    from the tasks — not just task_type."""
    if not ms:
        return ""
    blocks = ""
    for dim in ms:
        slices = dim.get("slices") or []
        if len(slices) < 2:
            continue
        has_base = any("tcr_delta_pp" in s for s in slices)
        body = ""
        for s in slices:
            tcr = s.get("tcr_pct")
            ci = s.get("tcr_ci_pct")
            acc = s.get("accuracy_pct")
            tcr_cell = "—"
            if tcr is not None:
                ci_s = (f' <span style="color:#9ca3af">({ci[0]:.0f}–{ci[1]:.0f})</span>'
                        if ci else "")
                tcr_cell = f'{tcr:.1f}%{ci_s}'
            acc_cell = f'{acc:.1f}%' if acc is not None else "—"
            delta_cell = ""
            if has_base:
                d = s.get("tcr_delta_pp")
                if d is None:
                    delta_cell = '<td style="color:#9ca3af">—</td>'
                else:
                    sig = s.get("significant")
                    col = ("#dc2626" if d < 0 else "#059669") if sig else "#6b7280"
                    tag = " *" if sig else ""
                    delta_cell = (f'<td style="color:{col};font-weight:600;'
                                  f'white-space:nowrap">{d:+.1f}pp{tag}</td>')
            body += (
                f'<tr><td style="font-weight:600">{_esc(str(s.get("value", "—")))}</td>'
                f'<td style="text-align:right">{s.get("n", 0)}</td>'
                f'<td style="text-align:right;white-space:nowrap">{tcr_cell}</td>'
                f'<td style="text-align:right">{acc_cell}</td>{delta_cell}</tr>'
            )
        head = ('<th>Value</th><th>N</th><th>TCR (95% CI)</th><th>Accuracy</th>'
                + ('<th>Δ vs baseline</th>' if has_base else ''))
        blocks += (
            f'<h3 style="margin:12px 0 4px;font-size:14px">'
            f'<code>{_esc(str(dim.get("dimension", "")))}</code></h3>'
            f'<table class="mtable"><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table>'
        )
    if not blocks:
        return ""
    return (
        '<div class="gate-section" id="metadata-slices" style="border-left-color:#6366f1">'
        '<h2 style="color:#1e2030">Metadata Slices</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        'Per-slice TCR/accuracy keyed on <code>extra</code> metadata attached to '
        'each task — e.g. which model or prompt variant produced it.</p>'
        f'{blocks}</div>'
    )


def _build_sample_guidance(sg: dict[str, Any] | None) -> str:
    """P28: "what to test next" — how many more tasks tighten the TCR CI."""
    if not sg or not sg.get("message"):
        return ""
    add = sg.get("additional_tasks", 0)
    col = "#059669" if add == 0 else "#b45309"
    return (
        '<div class="gate-section" id="sample-guidance" style="border-left-color:#0891b2">'
        '<h2 style="color:#1e2030">What to Test Next</h2>'
        f'<p style="font-size:13px;color:{col};font-weight:600;margin:0">'
        f'{_esc(str(sg["message"]))}</p></div>'
    )


def _build_reproducibility_manifest(man: dict[str, Any] | None) -> str:
    """P28: the model/decoding params, eval-set ref, evaluator-config hash and
    library versions needed to reproduce this run's scoring."""
    if not man:
        return ""
    rows = ""
    def _row(label: str, val: Any) -> str:
        if val is None or val == "" or val == {}:
            return ""
        if isinstance(val, dict):
            val = " · ".join(f"{k}={v}" for k, v in val.items())
        return (f'<tr><td style="font-weight:600;white-space:nowrap;padding-right:12px">'
                f'{_esc(label)}</td><td style="font-family:monospace;font-size:12px">'
                f'{_esc(str(val))}</td></tr>')
    rows += _row("Model", man.get("model_name"))
    rows += _row("Model params", man.get("model_params"))
    rows += _row("Judge model", man.get("judge_model"))
    rows += _row("Dataset", man.get("dataset_ref"))
    rows += _row("Evaluator config", man.get("evaluator_config"))
    rows += _row("Evaluator config hash", man.get("evaluator_config_hash"))
    rows += _row("Dependency versions", man.get("dependency_versions"))
    if not rows:
        return ""
    return (
        '<div class="gate-section" id="reproducibility" style="border-left-color:#64748b">'
        '<h2 style="color:#1e2030">Reproducibility Manifest</h2>'
        '<p style="color:#6b7280;font-size:12px;margin:0 0 6px">Everything needed to '
        'reproduce this run&rsquo;s <em>evaluation</em> (not the agent).</p>'
        f'<table class="mtable"><tbody>{rows}</tbody></table></div>'
    )


def _task_extra(t: Any) -> dict:
    raw = getattr(t, "raw", None)
    v = raw.get("extra") if isinstance(raw, dict) else getattr(t, "extra", None)
    return v if isinstance(v, dict) else {}


# ---------------------------------------------------------------------------
# Operational signals (P3.4) — AnomalyDetector 결과를 리포트에 노출
# ---------------------------------------------------------------------------

def _build_operational_signals(anomaly_data: dict[str, Any] | None) -> str:
    """AnomalyDetector 스캔 결과(``anomaly_data``)를 한 섹션으로 렌더링한다.

    지금까지 이상 탐지 결과는 대시보드에만 있고 정적 리포트에는 없었다 —
    ``enable_anomaly_detection=True``로 측정했으면 리포트에도 보여준다.
    """
    if not anomaly_data:
        return ""
    anomalies = anomaly_data.get("anomalies") or []
    if not anomalies:
        return (
            '<div class="gate-section" id="operational-signals" style="border-left-color:#10b981">'
            '<h2 style="color:#1e2030">Operational Signals</h2>'
            '<div class="ibox ok"><p>Anomaly detection ran — no anomalies detected '
            f'(baseline window {anomaly_data.get("baseline_window", "?")}, '
            f'detection window {anomaly_data.get("detection_window", "?")}).</p></div>'
            '</div>'
        )
    try:
        from agent_evaluator.ontology.metric_registry import anomaly_suggestion_for
    except Exception:
        anomaly_suggestion_for = lambda _t: None  # noqa: E731

    rows = ""
    for a in anomalies:
        sev = str(a.get("severity", "")).lower()
        sev_col = "#ef4444" if sev == "critical" else "#f59e0b"
        sug = a.get("explanation") or anomaly_suggestion_for(a.get("type")) or ""
        rows += (
            f'<tr>'
            f'<td style="white-space:nowrap"><span style="color:{sev_col};font-weight:700">'
            f'{_esc(a.get("type", "?"))}</span><br>'
            f'<span style="font-size:10px;color:#9ca3af">{_esc(sev or "—")}</span></td>'
            f'<td style="font-size:12px">{_esc(a.get("detail", ""))}</td>'
            f'<td style="white-space:nowrap;font-size:12px">{_num(a.get("value"), ".3f")} '
            f'<span style="color:#9ca3af">vs {_num(a.get("threshold"), ".3f")}</span></td>'
            f'<td style="font-size:12px;color:#4b5563">{_esc(sug)}</td>'
            f'</tr>'
        )
    return (
        '<div class="gate-section" id="operational-signals" style="border-left-color:#f59e0b">'
        f'<h2 style="color:#1e2030">Operational Signals '
        f'<span style="font-size:13px;color:#6b7280">'
        f'({len(anomalies)} anomaly signal(s))</span></h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 12px">'
        'AnomalyDetector compared the recent window against the baseline window. '
        'These are drift/spike signals, not Gate verdicts.</p>'
        '<table class="mtable"><thead><tr>'
        '<th>Signal</th><th>Detail</th><th>Value</th><th>Suggested action</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Executive summary (P3.1) — 리포트 맨 위 30초 판정
# ---------------------------------------------------------------------------

_GATE_FULL = {
    "A": "Goal Achievement", "B": "Behavioral Integrity", "C": "Reliability",
    "D": "Performance Contract", "E": "Security Boundary",
    "F": "Multi-Agent Coordination", "G": "Observability",
}


_SEC_SEV_COLOR = {"critical": "#7f1d1d", "high": "#dc2626", "medium": "#d97706",
                  "low": "#6b7280", "unknown": "#6b7280"}


_SUCCEEDED_BADGE = {
    "yes": ('landed', '#dc2626'), "likely": ('likely landed', '#d97706'),
    "no": ('blocked', '#059669'), "unknown": ('unknown', '#9ca3af'),
}


def _build_security_findings(current: dict[str, Any] | None) -> str:
    """P19 + P42: which task triggered which threat, whether the attack actually
    landed, compound (multi-tracker) exposure, and the attack-surface summary."""
    try:
        from agent_evaluator.reporting.insights import (
            _security_findings_section,
            _security_posture_section,
        )

        _tasks = (current or {}).get("tasks") if isinstance(current, dict) else None
        findings = _security_findings_section(current or {}, _tasks)
        posture = _security_posture_section(current or {}, _tasks, findings)
    except Exception:
        findings = posture = None
    if not findings:
        return ""
    rows = ""
    for f in findings:
        sev = f.get("severity", "unknown")
        col = _SEC_SEV_COLOR.get(sev, "#6b7280")
        cwe = f.get("cwe")
        cwe_s = ", ".join(cwe) if isinstance(cwe, list) else (cwe or "")
        _sl, _sc = _SUCCEEDED_BADGE.get(f.get("succeeded", "unknown"), ("", "#9ca3af"))
        _compound = f.get("kind") == "compound"
        _tr_style = ' style="background:#fef2f2"' if _compound else ""
        rows += (
            f'<tr{_tr_style}>'
            f'<td style="color:{col};font-weight:700;white-space:nowrap">{_esc(sev.upper())}'
            + (' <span style="font-size:10px">COMPOUND</span>' if _compound else "")
            + f'</td><td style="white-space:nowrap;font-size:12px">{_esc(f.get("task_id", ""))}</td>'
            f'<td style="white-space:nowrap">{_esc(f.get("threat_type", ""))}'
            + (f' <span style="color:#9ca3af">({_esc(cwe_s)})</span>' if cwe_s else "")
            + f'</td><td style="font-size:12px;color:#4b5563">{_esc(f.get("detail", ""))} '
            f'<span style="color:#9ca3af">[{_esc(f.get("tracker", ""))}]</span></td>'
            f'<td style="white-space:nowrap;color:{_sc};font-weight:600;font-size:11px">'
            f'{_esc(_sl)}</td></tr>'
        )
    posture_html = ""
    if posture:
        _bs = " · ".join(f"{k} {v}" for k, v in (posture.get("by_severity") or {}).items())
        _tools = ", ".join(
            f'{_esc(t["tool"])} ({t["n"]})' for t in (posture.get("tools_implicated") or [])
        )
        _landed = posture.get("landed_or_likely") or []
        posture_html = (
            '<p style="font-size:12px;color:#4b5563;margin:0 0 10px;'
            'background:#fff;border:1px solid #fecaca;border-radius:6px;padding:8px 10px">'
            f'<strong>Attack surface:</strong> {posture.get("n_findings")} finding(s) '
            f'over {posture.get("n_tasks_affected")} task(s) ({_esc(_bs)})'
            + (f'; {posture.get("n_compound")} compound' if posture.get("n_compound") else "")
            + (f'; tools implicated: {_tools}' if _tools else "")
            + (f'; <span style="color:#dc2626">{len(_landed)} attack(s) landed or '
               f'likely landed</span>' if _landed else
               '; no attack is confirmed to have landed (detection ≠ compromise)')
            + '</p>'
        )
    return (
        '<div class="gate-section" id="security-findings" style="border-left-color:#dc2626">'
        f'<h2 style="color:#dc2626">Security Findings '
        f'<span style="font-size:13px;color:#6b7280">({len(findings)} — most severe first)</span></h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 10px">'
        'A security regression is the highest-priority fix. "Landed" infers from '
        'whether a tool call executed after the flagged step — detection is not '
        'the same as compromise.</p>'
        f'{posture_html}'
        '<table class="mtable"><thead><tr>'
        '<th>Severity</th><th>Task</th><th>Threat</th><th>Detail</th><th>Outcome</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '</div>'
    )


def _build_nondeterminism(tasks: list[Any] | None) -> str:
    """P19: localize a low Gate C reproducibility score to the tasks that
    diverged, with the variant texts when the run kept them."""
    if not tasks:
        return ""
    try:
        from agent_evaluator.reporting.insights import _nondeterminism_section

        nd = _nondeterminism_section(_review_dict_tasks(tasks))
    except Exception:
        nd = None
    if not nd:
        return ""
    blocks = ""
    for d in nd:
        samples = "".join(
            f'<div style="font-family:monospace;font-size:11px;color:#374151;'
            f'padding:2px 0;border-top:1px dashed #e5e7eb">{_esc(_clip(s, 200))}</div>'
            for s in d.get("sample_responses") or []
        )
        blocks += (
            f'<div style="margin:8px 0;padding:8px 10px;background:#fafafa;border-radius:6px">'
            f'<div style="font-size:12px"><strong>{_esc(d.get("task_id", ""))}</strong> — '
            f'reproducibility {d.get("reproducibility_score", 0):.2f} over '
            f'{d.get("run_count", "?")} runs (variance {d.get("variance", 0):.3f})</div>'
            f'{samples}</div>'
        )
    return (
        '<div class="gate-section" id="nondeterminism" style="border-left-color:#f59e0b">'
        f'<h2 style="color:#1e2030">Non-Determinism '
        f'<span style="font-size:13px;color:#6b7280">({len(nd)} task(s))</span></h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        'These tasks produced different answers to the same input across '
        'reproducibility runs.</p>'
        f'{blocks}</div>'
    )


_EFF_KIND_LABEL = {
    "model_routing": ("Model routing", "#0ea5e9"),
    "step_gating": ("Step gating", "#7c3aed"),
    "retry_reduction": ("Retry reduction", "#d97706"),
}


def _build_efficiency_opportunities(eo: list[dict[str, Any]] | None) -> str:
    """P40: turn the latency-budget / cost-economics numbers into concrete moves —
    route to a cheaper model, gate an always-on step, cut retry spend."""
    if not eo:
        return ""
    cards = ""
    for o in eo:
        lbl, col = _EFF_KIND_LABEL.get(o.get("kind", ""), (o.get("kind", ""), "#6b7280"))
        sp = o.get("projected_saving_pct")
        per100k = o.get("projected_saving_per_100k_usd")
        save_s = ""
        if isinstance(sp, (int, float)):
            save_s = (f'<span style="color:#059669;font-weight:700">~{sp:.0f}% cost</span>'
                      + (f' (~${per100k:,.0f}/100k calls)' if per100k else ""))
        cards += (
            '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;'
            'margin:8px 0;background:#fff">'
            f'<div style="font-size:11px;font-weight:700;color:{col};text-transform:'
            f'uppercase;letter-spacing:.4px">{_esc(lbl)}</div>'
            f'<div style="font-weight:600;margin:2px 0">{_esc(o.get("title", ""))} '
            f'{save_s}</div>'
            f'<p style="font-size:12px;color:#374151;margin:2px 0">{_esc(o.get("detail", ""))}</p>'
            f'<p style="font-size:11px;color:#9ca3af;margin:2px 0 0">Risk: '
            f'{_esc(o.get("risk", ""))}</p>'
            '</div>'
        )
    return (
        '<div class="gate-section" id="efficiency-opportunities" '
        'style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">Efficiency Opportunities</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        'First-order cost / latency moves synthesised from the slice, span and '
        'retry data. Projections assume the rest of the system is unchanged.</p>'
        f'{cards}</div>'
    )


def _build_multiagent(ma: dict[str, Any] | None) -> str:
    """P41: per-agent contribution / error rate, hand-off context retention, the
    bottleneck agent, the communication graph, and MAST failure-mode candidates."""
    if not ma or not ma.get("per_agent"):
        return ""
    bn = ma.get("bottleneck_agent")
    pa_rows = ""
    for pa in ma["per_agent"]:
        _is_bn = pa["agent_id"] == bn
        er = pa.get("error_rate", 0.0)
        _ecol = "#dc2626" if er >= 0.34 else ("#d97706" if er > 0 else "#374151")
        pa_rows += (
            f'<tr><td style="font-weight:600">{_esc(pa["agent_id"])}'
            + (' <span style="color:#dc2626;font-size:11px">bottleneck</span>'
               if _is_bn else "")
            + f'</td><td style="text-align:right">{pa.get("n_turns")}</td>'
            f'<td style="text-align:right">{pa.get("contribution_score", 0) * 100:.0f}%</td>'
            f'<td style="text-align:right;color:{_ecol};font-weight:600">'
            f'{er * 100:.0f}%</td></tr>'
        )
    ho_rows = ""
    for h in ma.get("handoffs") or []:
        cr = h.get("context_retention_at_handoff")
        _ccol = ("#dc2626" if isinstance(cr, (int, float)) and cr < 0.3
                 else "#374151")
        cr_s = f'{cr * 100:.0f}%' if isinstance(cr, (int, float)) else "—"
        ho_rows += (
            f'<tr><td>{_esc(h.get("from", "?"))} → {_esc(h.get("to", "?"))}</td>'
            f'<td style="text-align:right">{h.get("n")}</td>'
            f'<td style="text-align:right;color:{_ccol};font-weight:600">{cr_s}</td></tr>'
        )
    mast_html = ""
    _mc = ma.get("mast_candidates") or []
    if _mc:
        items = "".join(
            f'<li><strong>{_esc(m.get("code", ""))} {_esc(m.get("name", ""))}</strong> — '
            f'{_esc(m.get("remediation", ""))}</li>'
            for m in _mc
        )
        mast_html = (
            '<h3 style="margin:12px 0 4px">MAST failure-mode candidates '
            '<span style="font-size:12px;color:#6b7280">(Cemri et al. 2025 — '
            'candidates, not verdicts)</span></h3>'
            f'<ul style="margin:0 0 0 18px;font-size:12px;line-height:1.7">{items}</ul>'
        )
    return (
        '<div class="gate-section" id="multiagent" style="border-left-color:#8b5cf6">'
        '<h2 style="color:#1e2030">Multi-Agent Coordination</h2>'
        f'<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        f'{ma.get("n_agents")} agent(s) over {ma.get("n_tasks_with_agent_data")} '
        f'task(s) with interaction data.</p>'
        '<h3 style="margin:6px 0 4px">Per agent</h3>'
        '<table class="mtable"><thead><tr><th>Agent</th><th>Turns</th>'
        '<th>Share</th><th>Error rate</th></tr></thead>'
        f'<tbody>{pa_rows}</tbody></table>'
        + (
            '<h3 style="margin:12px 0 4px">Hand-offs '
            '<span style="font-size:12px;color:#6b7280">(does the receiver reuse '
            'what it was handed?)</span></h3>'
            '<table class="mtable"><thead><tr><th>Hand-off</th><th>N</th>'
            '<th>Context retention</th></tr></thead>'
            f'<tbody>{ho_rows}</tbody></table>' if ho_rows else ""
        )
        + mast_html
        + '</div>'
    )


def _build_calibration(cal: dict[str, Any] | None) -> str:
    """P39: is the agent's own confidence trustworthy? Reliability diagram +
    ECE/Brier + over/under-confidence verdict + risk/coverage + abstention."""
    if not cal:
        return ""
    has_conf = isinstance(cal.get("ece"), (int, float))
    _vcol = {"overconfident": "#dc2626", "underconfident": "#d97706",
             "well-calibrated": "#059669"}.get(cal.get("verdict", ""), "#6b7280")

    kpis = ""
    if has_conf:
        kpis = (
            '<div class="kpis">'
            f'<div class="kpi"><div class="kpi-lbl">Verdict</div>'
            f'<div class="kpi-val" style="color:{_vcol};font-size:15px">'
            f'{_esc(cal.get("verdict", "—"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Mean confidence</div>'
            f'<div class="kpi-val">{cal.get("mean_confidence", 0) * 100:.0f}%</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Empirical accuracy</div>'
            f'<div class="kpi-val">{cal.get("empirical_accuracy", 0) * 100:.0f}%</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">ECE</div>'
            f'<div class="kpi-val">{cal.get("ece")}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">Brier</div>'
            f'<div class="kpi-val">{cal.get("brier")}</div></div>'
            '</div>'
        )

    bins_html = ""
    _bins = cal.get("reliability_bins") or []
    if _bins:
        rows = ""
        for b in _bins:
            _diff = b.get("accuracy", 0) - b.get("mean_conf", 0)
            _c = "#dc2626" if _diff < -0.1 else ("#d97706" if _diff > 0.1 else "#374151")
            rows += (
                f'<tr><td>{b.get("lo"):.1f}–{b.get("hi"):.1f}</td>'
                f'<td style="text-align:right">{b.get("n")}</td>'
                f'<td style="text-align:right">{b.get("mean_conf", 0) * 100:.0f}%</td>'
                f'<td style="text-align:right;color:{_c};font-weight:600">'
                f'{b.get("accuracy", 0) * 100:.0f}%</td></tr>'
            )
        bins_html = (
            '<h3 style="margin:12px 0 4px">Reliability by confidence bucket</h3>'
            '<table class="mtable"><thead><tr><th>Confidence</th><th>N</th>'
            '<th>Stated</th><th>Actual</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )

    rc_html = ""
    _rc = cal.get("risk_coverage") or []
    if _rc:
        cells = " · ".join(
            f'{p.get("coverage", 0) * 100:.0f}% cov → {p.get("risk", 0) * 100:.0f}% err'
            for p in _rc
        )
        _sig = cal.get("confidence_signal")
        _inf_s = {
            "informative": ' <span style="color:#059669">— confidence carries '
                           'routing signal</span>',
            "flat": ' <span style="color:#dc2626">— confidence does not separate '
                    'right from wrong (flat risk)</span>',
            "inverted": ' <span style="color:#dc2626">— confidence is inverted: '
                        'high-confidence answers are <em>more</em> likely wrong</span>',
        }.get(_sig, "")
        rc_html = (
            '<h3 style="margin:12px 0 4px">Risk / coverage '
            '<span style="font-size:12px;color:#6b7280">(answer only the most-confident '
            'fraction)</span></h3>'
            f'<p style="font-size:12px;color:#374151;margin:0">{cells}{_inf_s}</p>'
        )

    ab = cal.get("abstention") or {}
    ab_html = ""
    if ab:
        _wa = ab.get("abstained_when_answerable", 0)
        ab_html = (
            '<h3 style="margin:12px 0 4px">Abstention</h3>'
            f'<p style="font-size:12px;color:#374151;margin:0">Abstained on '
            f'<strong>{ab.get("n_abstained")}</strong> task(s) '
            f'({ab.get("abstention_rate_pct")}% of the set)'
            + (f'; answered-task accuracy {ab.get("answered_accuracy_pct")}%'
               if ab.get("answered_accuracy_pct") is not None else "")
            + (f'. <span style="color:#d97706">{_wa} of those had a usable ground '
               f'truth</span> — possible over-abstention.' if _wa else '.')
            + '</p>'
        )

    return (
        '<div class="gate-section" id="calibration" style="border-left-color:#0891b2">'
        '<h2 style="color:#1e2030">Confidence Calibration</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        'Does the agent know when it is right? From opt-in <code>extra.confidence</code> '
        '/ <code>extra.abstained</code>. A wrong-but-confident agent is the dangerous '
        'failure mode the accuracy score alone cannot see.</p>'
        f'{kpis}{bins_html}{rc_html}{ab_html}</div>'
    )


def _build_conversation(cv: dict[str, Any] | None) -> str:
    """P24: multi-turn quality — per-turn context-reference trajectory, the turn
    the agent starts to degrade, and per-session goal drift."""
    if not cv or not cv.get("turn_quality_trajectory"):
        return ""
    traj = cv["turn_quality_trajectory"]
    dat = cv.get("degradation_after_turn")
    kpis = (
        f'<div class="kpi"><div class="kpi-lbl">Sessions</div>'
        f'<div class="kpi-val">{cv.get("n_sessions", 0)}</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">Avg Session Score</div>'
        f'<div class="kpi-val">{_pct(cv.get("avg_overall_score"), 100)}</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">Avg Context Retention</div>'
        f'<div class="kpi-val">{_pct(cv.get("avg_context_retention"), 100)}</div></div>'
    )
    # per-turn context-reference sparkline
    series = [x["context_ref"] for x in traj if x["context_ref"] is not None]
    spark = _spark_svg(series, color="#dc2626" if dat else "#6366f1") if len(series) > 1 else ""

    rows = ""
    for x in traj:
        cr = x.get("context_ref")
        rep = x.get("repetition")
        na = x.get("nonanswer_rate")
        col = "#dc2626" if (cr is not None and cr < 0.3) else "#374151"
        cr_s = f"{cr * 100:.0f}%" if cr is not None else "—"
        rep_s = f"{rep * 100:.0f}%" if rep is not None else "—"
        na_s = (f'<span style="color:#dc2626">{na * 100:.0f}%</span>'
                if na is not None and na >= 0.5
                else (f"{na * 100:.0f}%" if na is not None else "—"))
        rows += (
            f'<tr><td>Turn {x["turn"]}</td>'
            f'<td style="text-align:right">{x.get("n", 0)}</td>'
            f'<td style="text-align:right;color:{col}">{cr_s}</td>'
            f'<td style="text-align:right">{x.get("avg_response_chars", "—")}</td>'
            f'<td style="text-align:right">{rep_s}</td>'
            f'<td style="text-align:right">{na_s}</td></tr>'
        )
    dat_html = ""
    if dat:
        dat_html = (f'<p style="font-size:13px;font-weight:700;color:#dc2626;margin:8px 0 0">'
                    f'⚠️ The agent starts losing context after turn {dat}.</p>')
    drift_html = ""   # P35: goal-drift signal removed (unreliable, see insights.py)

    # P35: per-session table — one healthy + one bad session averaged together
    # is misleading; show them individually.
    sess = cv.get("sessions") or []
    sess_html = ""
    if len(sess) > 1:
        srows = ""
        for ps in sess:
            osc = ps.get("overall_score")
            col = "#dc2626" if isinstance(osc, (int, float)) and osc < 0.4 else "#374151"
            srows += (
                f'<tr><td style="font-weight:600">{_esc(str(ps.get("session_id")))}</td>'
                f'<td style="text-align:right">{ps.get("turns")}</td>'
                f'<td style="text-align:right;color:{col};font-weight:700">'
                f'{osc if osc is not None else "—"}</td>'
                f'<td style="text-align:right">{ps.get("context_retention", "—")}</td>'
                f'<td style="text-align:right">{ps.get("nonanswer_turns", 0)}</td></tr>'
            )
        # Topic coherence is deliberately omitted — the lexical heuristic behind it
        # (see insights.py, P35) is unreliable for same-topic follow-ups.
        sess_html = (
            '<h3 style="margin:14px 0 4px">Per session</h3>'
            '<table class="mtable"><thead><tr><th>Session</th><th>Turns</th>'
            '<th>Score</th><th>Ctx retention</th>'
            '<th>Non-answer turns</th></tr></thead>'
            f'<tbody>{srows}</tbody></table>'
        )
    return (
        '<div class="gate-section" id="conversation" style="border-left-color:#8b5cf6">'
        '<h2 style="color:#1e2030">Multi-Turn Conversation</h2>'
        f'<div class="kpis">{kpis}</div>'
        f'{sess_html}'
        f'<h3 style="margin:10px 0 4px">Per-turn context reference {spark}</h3>'
        '<p style="color:#6b7280;font-size:12px;margin:0 0 6px">'
        'How much each agent turn reuses content from earlier turns — a decline '
        'means the agent is losing the thread.</p>'
        '<table class="mtable"><thead><tr><th>Turn</th><th>N</th>'
        '<th>Context ref</th><th>Avg chars</th><th>Repetition</th>'
        '<th>Non-answer</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'{dat_html}{drift_html}</div>'
    )


_EXP_VERDICT_STYLE = {
    "confirmed": ("#059669", "✔ confirmed"),
    "partially_confirmed": ("#d97706", "◑ partial"),
    "refuted": ("#dc2626", "✘ refuted"),
    "inconclusive": ("#6b7280", "– inconclusive"),
    "pending": ("#6b7280", "… pending"),
}


def _build_experiments(exps: list[dict[str, Any]] | None) -> str:
    """P27: registered improvement hypotheses (.aoo/experiments.jsonl) — predicted
    vs actual movement of the target Gate/field, with the verdict."""
    if not exps:
        return ""
    n_open = sum(1 for e in exps if e.get("status") != "resolved")
    n_res = len(exps) - n_open
    rows = ""
    for e in exps:
        pred = e.get("predicted")
        act = e.get("actual")
        verdict = e.get("verdict") or "pending"
        col, lbl = _EXP_VERDICT_STYLE.get(verdict, ("#6b7280", verdict))
        pred_s = f"{pred:+.3f}" if isinstance(pred, (int, float)) else "—"
        act_s = f"{act:+.3f}" if isinstance(act, (int, float)) else "—"
        note = _esc(str(e.get("note") or ""))
        # the dedicated Predicted Δ column already shows the number — keep the
        # Hypothesis cell to just the target so it doesn't read as a duplicate.
        tgt = f"Gate {e.get('target_gate', '?')}"
        if e.get("target_field"):
            tgt += f" · {e['target_field']}"
        label = tgt if e.get("target_gate") else str(e.get("hypothesis", ""))
        rows += (
            f'<tr><td>{_esc(label)}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums">{pred_s}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums">{act_s}</td>'
            f'<td style="color:{col};font-weight:700">{lbl}</td>'
            f'<td style="font-size:11px;color:#6b7280">{e.get("status", "")}</td></tr>'
            + (f'<tr><td colspan="5" style="font-size:11px;color:#9ca3af;'
               f'padding-top:0">{note}</td></tr>' if note else "")
        )
    return (
        '<div class="gate-section" id="experiments" style="border-left-color:#f59e0b">'
        '<h2 style="color:#1e2030">Improvement Experiments</h2>'
        '<p style="color:#6b7280;font-size:12px;margin:0 0 6px">'
        f'{n_open} open · {n_res} resolved. Each row is a prediction registered with '
        '<code>agent-eval experiment register</code>; "actual" is the measured '
        'movement vs the baseline run. Correlation, not proof — other changes may '
        'have ridden along.</p>'
        '<table class="mtable"><thead><tr><th>Hypothesis</th><th>Predicted Δ</th>'
        '<th>Actual Δ</th><th>Verdict</th><th>Status</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )


_TD_VERDICT_STYLE = {
    "fixed": ("#059669", "✔ fixed"),
    "improved": ("#059669", "▲ improved"),
    "regressed": ("#dc2626", "✘ regressed"),
    "declined": ("#dc2626", "▼ declined"),
    "changed": ("#6b7280", "~ changed"),
}


def _pretty_field(fld: Any) -> str:
    """P35: a readable label for a Gate details field name — 'tcr_pct' -> 'TCR'.
    Thin wrapper over the shared ontology helper."""
    try:
        from agent_evaluator.ontology.metric_registry import pretty_metric_name

        return pretty_metric_name(fld)
    except Exception:
        return str(fld or "").replace("avg_", "").replace("_", " ").strip()


def _trim_field_restatement(field_label: str, action: str) -> str:
    """P35 r3: guidance strings often open by restating the component name
    ("Response relevance/completeness is low. Strengthen …"). When that clause is
    about to sit right after the same label, drop it so the name isn't said twice."""
    act = (action or "").strip()
    if field_label and act and ". " in act:
        first, rest = act.split(". ", 1)
        if first.lower().startswith(field_label.lower().rstrip(".")) and rest.strip():
            return rest.strip()
    return act


def _td_resp_summary(rd: dict[str, Any]) -> str:
    """P35: readable response-diff summary — "0% unchanged" reads as a double
    negative."""
    if rd.get("errored"):
        reason = str(rd.get("error_reason") or "").strip()
        return ("Current version returned no response"
                + (f" ({_esc(reason)})" if reason else ""))
    sim = (rd.get("similarity") or 0.0) * 100
    if sim <= 2:
        return "Response fully rewritten"
    if sim >= 98:
        return "Response essentially unchanged"
    return f"Response {sim:.0f}% similar"


def _build_trace_diffs(td: list[dict[str, Any]] | None) -> str:
    """P32: for a task that moved between cohort versions, show WHAT changed —
    the response text diff and the trajectory step diff, not just the average."""
    if not td:
        return ""
    blocks = ""
    for d in td:
        col, lbl = _TD_VERDICT_STYLE.get(d.get("verdict", ""), ("#6b7280", d.get("verdict", "")))
        cmp_ = d.get("compared") or []
        sd = d.get("score_delta") or {}
        rd = d.get("response_diff") or {}
        tj = d.get("trajectory_diff") or {}

        pv_rows = ""
        for v in d.get("per_version") or []:
            ok = v.get("success")
            _c = v.get("completion")
            _a = v.get("accuracy")
            c_s = f"{_c:.2f}" if isinstance(_c, (int, float)) else "—"
            a_s = f"{_a:.2f}" if isinstance(_a, (int, float)) else "—"
            pv_rows += (
                f'<tr><td style="font-weight:600">{_esc(str(v.get("label", "")))}</td>'
                f'<td style="text-align:right">{c_s}</td>'
                f'<td style="text-align:right">{a_s}</td>'
                f'<td style="text-align:center;color:{"#059669" if ok else "#dc2626"}">'
                f'{"✓" if ok else "✗"}</td>'
                f'<td style="font-size:11px;color:#6b7280">'
                f'{_esc(_clip(str(v.get("response_excerpt", "")), 110))}</td></tr>'
            )

        _add_runs = list(rd.get("added") or [])[:5]
        _rem_runs = list(rd.get("removed") or [])[:5]
        if rd.get("errored"):
            # nothing to word-diff against an empty response — the summary line says it
            _add_runs = _rem_runs = []
        # P35: one short removed-run + one short added-run reads better as a
        # substitution ("7.8 mm and 172 g. → 7 (the remaining steps…)") than as
        # separate "added 7 / removed 7.8 mm…".
        subst = ""
        if (len(_add_runs) == 1 and len(_rem_runs) == 1
                and len(_rem_runs[0].split()) <= 8 and len(_add_runs[0].split()) <= 8):
            subst = (f' · <span style="color:#6b7280">changed:</span> '
                     f'{_esc(_rem_runs[0])} → {_esc(_add_runs[0])}')
            _add_runs = _rem_runs = []
        added = ", ".join(_esc(x) for x in _add_runs)
        removed = ", ".join(_esc(x) for x in _rem_runs)
        traj_line = ""
        if tj.get("added") or tj.get("removed") or tj.get("reordered"):
            bits = []
            if tj.get("added"):
                bits.append("+" + "/".join(_esc(s) for s in tj["added"]))
            if tj.get("removed"):
                bits.append("−" + "/".join(_esc(s) for s in tj["removed"]))
            if tj.get("reordered"):
                bits.append("reordered")
            traj_line = (f'<div style="font-size:11px;color:#6b7280;margin-top:4px">'
                         f'Trajectory: {" · ".join(bits)}</div>')

        blocks += (
            f'<div style="border-top:1px solid #e5e7eb;padding:8px 0">'
            f'<div style="font-size:12px"><strong>{_esc(str(d.get("task_id", "")))}</strong> '
            f'<span style="color:{col};font-weight:700">{_esc(lbl)}</span> '
            f'<span style="color:#9ca3af">'
            f'{_esc(" → ".join(str(c) for c in cmp_))} · '
            f'C {sd.get("completion", 0):+.2f} · A {sd.get("accuracy", 0):+.2f}</span></div>'
            f'<div style="font-size:11px;color:#374151;margin:2px 0">'
            f'{_esc(_clip(str(d.get("question", "")), 120))}</div>'
            f'<table class="mtable" style="font-size:12px;margin:4px 0"><thead><tr>'
            f'<th>Version</th><th>C</th><th>A</th><th>OK</th><th>Response</th>'
            f'</tr></thead><tbody>{pv_rows}</tbody></table>'
            f'<div style="font-size:11px;color:#6b7280">{_td_resp_summary(rd)}'
            + subst
            + (f' · <span style="color:#059669">added:</span> {added}' if added else "")
            + (f' · <span style="color:#dc2626">removed:</span> {removed}' if removed else "")
            + f'</div>{traj_line}</div>'
        )
    return (
        '<div class="gate-section" id="trace-diffs" style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">Trace-Level Version Diff</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">'
        'For each task that changed outcome or score across the compared versions '
        '&mdash; what changed in the response and the tool trajectory, not just the average.</p>'
        f'{blocks}</div>'
    )


def _build_cohort_comparison(cc: dict[str, Any] | None) -> str:
    """P22: 3+ versions side by side — per-version TCR + Gate scores, per-task_type
    winner, FDR-adjusted pairwise significance, and a 'pick the winner' call."""
    if not cc or not cc.get("versions"):
        return ""
    vs = cc["versions"]
    metric = cc.get("metric", "tcr").upper()

    vrows = ""
    for v in vs:
        gs = v.get("gate_scores") or {}
        gs_txt = " · ".join(f"{g} {gs[g]:.2f}" for g in "ABCDEFG" if g in gs) or "—"
        tcr = v.get("tcr_pct")
        vrows += (
            f'<tr><td style="font-weight:600">{_esc(v.get("label", "?"))}</td>'
            f'<td style="text-align:right">{v.get("n_tasks", 0)}</td>'
            f'<td style="text-align:right">{tcr:.1f}%</td>' if tcr is not None else
            f'<tr><td style="font-weight:600">{_esc(v.get("label", "?"))}</td>'
            f'<td style="text-align:right">{v.get("n_tasks", 0)}</td><td>—</td>'
        )
        vrows += f'<td style="font-size:11px;color:#6b7280">{_esc(gs_txt)}</td></tr>'

    prows = ""
    for e in cc.get("pairwise") or []:
        sig = e.get("significant_fdr")
        col = "#059669" if sig else "#6b7280"
        ci = e.get("ci_pp")
        ci_s = f' CI [{ci[0]:+.0f}, {ci[1]:+.0f}]' if isinstance(ci, (list, tuple)) else ""
        pf = e.get("p_value_fdr")
        prows += (
            f'<tr><td>{_esc(e.get("a", ""))} vs {_esc(e.get("b", ""))}</td>'
            f'<td style="text-align:right;color:{col};font-weight:600">'
            f'{e.get("delta_pp", 0):+.1f}pp{ci_s}</td>'
            f'<td style="text-align:right">{pf if pf is not None else "—"}'
            f'{" *" if sig else ""}</td></tr>'
        )

    btrows = ""
    for r in cc.get("by_task_type") or []:
        cells = "".join(
            f'<td style="text-align:right{";font-weight:700;color:#059669" if k == r.get("winner") else ""}">'
            f'{(f"{v:.0f}%" if v is not None else "—")}</td>'
            for k, v in (r.get("scores") or {}).items()
        )
        btrows += (f'<tr><td style="font-weight:600">{_esc(r.get("task_type", "—"))}</td>'
                   f'{cells}</tr>')
    bt_head = "".join(f'<th style="text-align:right">{_esc(v["label"])}</th>' for v in vs)

    w = cc.get("winner") or {}
    if w.get("label"):
        w_html = (f'<p style="font-size:14px;font-weight:700;color:#059669;margin:8px 0 0">'
                  f'🏆 Winner: {_esc(w["label"])}</p>'
                  f'<p style="font-size:12px;color:#6b7280;margin:2px 0 0">{_esc(w.get("reason", ""))}</p>')
    elif w:
        w_html = (f'<p style="font-size:13px;font-weight:600;color:#d97706;margin:8px 0 0">'
                  f'No clear winner</p>'
                  f'<p style="font-size:12px;color:#6b7280;margin:2px 0 0">{_esc(w.get("reason", ""))}</p>')
    else:
        w_html = ""

    return (
        '<div class="gate-section" id="cohort-comparison" style="border-left-color:#0ea5e9">'
        f'<h2 style="color:#1e2030">Version Comparison '
        f'<span style="font-size:13px;color:#6b7280">({cc.get("n_versions", len(vs))} versions '
        f'· metric: {metric})</span></h2>'
        '<table class="mtable"><thead><tr><th>Version</th><th>N</th>'
        f'<th>{metric}</th><th>Gate scores</th></tr></thead><tbody>{vrows}</tbody></table>'
        '<h3 style="margin:12px 0 4px">Per task type</h3>'
        f'<table class="mtable"><thead><tr><th>Task type</th>{bt_head}</tr></thead>'
        f'<tbody>{btrows}</tbody></table>'
        '<h3 style="margin:12px 0 4px">Pairwise (Benjamini-Hochberg FDR)</h3>'
        '<table class="mtable"><thead><tr><th>Pair</th><th>Δ (95% CI)</th>'
        f'<th>p (FDR)</th></tr></thead><tbody>{prows}</tbody></table>'
        '<p style="font-size:11px;color:#9ca3af;margin:4px 0 0">'
        '* = significant after FDR correction across all pairs.</p>'
        f'{w_html}</div>'
    )


def _build_change_attribution(ca: dict[str, Any] | None) -> str:
    """P18: tie the metric move to the specific prompt / config / code change
    between this run and its baseline."""
    if not ca:
        return ""
    note = ca.get("note") or ""
    body = f'<p style="font-size:13px;color:#374151;margin:0 0 8px">{_esc(note)}</p>'

    pd = ca.get("prompt_diff")
    if pd:
        def _lines(items: list, color: str, sign: str) -> str:
            return "".join(
                f'<div style="color:{color};font-family:monospace;font-size:11px">'
                f'{sign} {_esc(_clip(x, 120))}</div>' for x in items
            )
        body += (
            f'<p style="font-size:12px;color:#6b7280;margin:6px 0 2px">System prompt '
            f'({pd.get("similarity", 0) * 100:.0f}% similar):</p>'
            + _lines(pd.get("removed") or [], "#b91c1c", "-")
            + _lines(pd.get("added") or [], "#047857", "+")
        )
    cd = ca.get("config_diff")
    if cd and cd.get("changed_keys"):
        rows = "".join(
            f'<tr><td style="font-weight:600">{_esc(str(k))}</td>'
            f'<td style="color:#b91c1c">{_esc(str(v.get("from")))}</td>'
            f'<td style="color:#047857">{_esc(str(v.get("to")))}</td></tr>'
            for k, v in cd["changed_keys"].items()
        )
        body += (
            '<p style="font-size:12px;color:#6b7280;margin:8px 0 2px">Config changes:</p>'
            '<table class="mtable"><thead><tr><th>Key</th><th>From</th><th>To</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
    return (
        '<div class="gate-section" id="change-attribution" style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">Change Attribution</h2>'
        f'{body}</div>'
    )


def _build_regression_attribution(ra: dict[str, Any] | None) -> str:
    """P38: for each regressed failure cluster, the slice it concentrates in and
    the prompt/config change whose nature plausibly explains it. Correlational."""
    if not ra or not ra.get("clusters"):
        return ""
    rows = ""
    for c in ra["clusters"]:
        conc = c.get("slice_concentration") or []
        conc_html = "—"
        if conc:
            conc_html = "<br>".join(
                f'{_esc(s["dimension"])}=<strong>{_esc(str(s["value"]))}</strong> '
                f'({s["share_pct"]}%'
                + (f', <span style="color:#b91c1c">{s["slice_tcr_delta_pp"]:+.1f}pp</span>'
                   if s.get("slice_tcr_delta_pp") is not None else "")
                + ')'
                for s in conc[:2]
            )
        imp = c.get("implicated_changes") or []
        imp_html = ("<br>".join(_esc(x) for x in imp)
                    if imp else '<span style="color:#9ca3af">no matching change</span>')
        rows += (
            f'<tr><td><div style="font-weight:600">{_esc(_clip(c.get("signature", ""), 80))}'
            f'</div><div style="font-size:11px;color:#9ca3af">{c.get("n")} task(s) · '
            f'{_esc(c.get("category", ""))}</div></td>'
            f'<td style="font-size:11px">{conc_html}</td>'
            f'<td style="font-size:11px">{imp_html}</td></tr>'
        )
    return (
        '<div class="gate-section" id="regression-attribution" style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">Regression Attribution</h2>'
        f'<p style="font-size:13px;color:#374151;margin:0 0 8px">{_esc(ra.get("note", ""))}</p>'
        '<table class="mtable"><thead><tr><th>Regressed cluster</th>'
        '<th>Concentrates in</th><th>Co-occurring change(s)</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )


_TOC_LABELS = {
    "narrative": "Summary", "exec-summary": "Verdict", "path-to-green": "Path to Green",
    "briefs": "Briefs",
    "gate-a": "A", "gate-b": "B", "gate-c": "C", "gate-d": "D",
    "gate-e": "E", "gate-f": "F", "gate-g": "G",
    "advanced": "Advanced", "operational-signals": "Anomalies",
    "slice-analysis": "Slices", "metadata-slices": "Metadata slices",
    "sample-guidance": "Test next", "reproducibility": "Reproducibility",
    "metric-signal": "Metric signal", "evaluator-reliability": "Evaluator trust",
    "review-queue": "Review queue", "security-findings": "Security",
    "nondeterminism": "Non-determinism", "eval-set-quality": "Eval set",
    "failure-cases": "Failures", "failure-explanations": "Wrong claims",
    "recommendations": "Recommendations",
    "conversation": "Conversation", "experiments": "Experiments",
    "cohort-comparison": "Versions", "trace-diffs": "Trace diff",
    "freshness": "Freshness", "insight-changes": "Insight diff",
    "calibration": "Calibration", "efficiency-opportunities": "Efficiency",
    "multiagent": "Multi-agent",
    "regression-attribution": "Reg. cause", "change-attribution": "Change",
    "diagnosis": "RCA",
    "history-trend": "Trend", "change-ledger": "Ledger",
    "threshold-sensitivity": "Sensitivity", "conclusion": "Conclusion",
}


def _build_toc(full_html: str) -> str:
    """A compact sticky in-page nav — 23 sections is a lot to scroll through."""
    ids = re.findall(r'<div class="gate-section"[^>]*id="([a-z-]+)"', full_html)
    seen, links = set(), []
    for sid in ids:
        if sid in seen:
            continue
        seen.add(sid)
        label = _TOC_LABELS.get(sid, sid.replace("-", " ").title())
        links.append(
            f'<a href="#{sid}" style="color:#475569;text-decoration:none;'
            f'padding:2px 8px;border-radius:6px;white-space:nowrap;font-size:12px">'
            f'{_esc(label)}</a>'
        )
    if len(links) < 4:
        return ""
    return (
        '<div style="position:sticky;top:0;z-index:20;background:#fffffff2;'
        'backdrop-filter:blur(4px);border:1px solid #e5e7eb;border-radius:10px;'
        'padding:8px 10px;margin:0 0 24px;display:flex;flex-wrap:wrap;gap:2px 4px;'
        'box-shadow:0 1px 3px rgba(0,0,0,.06)">'
        '<span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:'
        'uppercase;letter-spacing:.5px;padding:2px 4px">Jump to</span>'
        + "".join(links) + '</div>'
    )


def _build_narrative_banner(narrative: str) -> str:
    """P17: the plain-English "what happened / what to do / how confident"
    sentences at the very top of the report — pasteable into a release ticket."""
    if not narrative or not narrative.strip():
        return ""
    return (
        '<div class="gate-section" id="narrative" '
        'style="border-left-color:#1e2030;background:#f8fafc">'
        '<p style="font-size:14px;line-height:1.65;color:#1e2030;margin:0">'
        f'{_esc(narrative.strip())}</p>'
        '<p style="font-size:11px;color:#9ca3af;margin:6px 0 0">'
        'Auto-generated summary — see the sections below for the evidence.</p>'
        '</div>'
    )


def _build_briefs(briefs: dict[str, Any] | None) -> str:
    """P34: the same run summarised for three audiences — a PM one-liner, a QA
    paragraph, an engineer checklist."""
    if not briefs or not (briefs.get("pm") or briefs.get("qa") or briefs.get("engineer")):
        return ""
    eng = "".join(f"<li>{_esc(str(x))}</li>" for x in briefs.get("engineer") or [])
    return (
        '<div class="gate-section" id="briefs" style="border-left-color:#6366f1">'
        '<h2 style="color:#1e2030">Briefs by Audience</h2>'
        '<div style="display:grid;gap:14px;'
        'grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">'
        f'<div><div style="font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.5px;color:#6b7280">For a PM</div>'
        f'<p style="font-size:13px;margin:4px 0 0">{_esc(briefs.get("pm", ""))}</p></div>'
        f'<div><div style="font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.5px;color:#6b7280">For QA</div>'
        f'<p style="font-size:13px;margin:4px 0 0">{_esc(briefs.get("qa", ""))}</p></div>'
        f'<div><div style="font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.5px;color:#6b7280">For the engineer</div>'
        f'<ol style="font-size:12px;margin:4px 0 0 16px;line-height:1.6">{eng}</ol></div>'
        '</div></div>'
    )


def _build_narrative_audit_note(na: dict[str, Any] | None) -> str:
    """P34: a warning appended when the narrative makes a claim the structured
    numbers don't back (an over-claiming LLM narrator)."""
    if not na or na.get("clean") or not na.get("adjustments"):
        return ""
    items = "".join(f"<li>{_esc(a)}</li>" for a in na["adjustments"])
    return (
        '<div style="margin-top:8px;padding:8px 10px;background:#fef2f2;'
        'border:1px solid #fca5a5;border-radius:6px">'
        '<div style="font-size:11px;font-weight:700;color:#991b1b">'
        '⚠ The summary above overstates the evidence:</div>'
        f'<ul style="margin:4px 0 0 16px;font-size:11px;color:#991b1b;line-height:1.5">'
        f'{items}</ul></div>'
    )


def _build_freshness_banner(fr: dict[str, Any] | None) -> str:
    """P33: a staleness warning banner — old baseline, unchanged eval set,
    mislabelled cases, tiny eval set."""
    if not fr or not fr.get("warnings"):
        return ""
    items = "".join(f"<li>{_esc(w)}</li>" for w in fr["warnings"])
    return (
        '<div class="gate-section" id="freshness" '
        'style="border-left-color:#b45309;background:#fffbeb">'
        '<div style="font-weight:700;color:#92400e;font-size:13px">⏳ Freshness</div>'
        f'<ul style="margin:6px 0 0 18px;font-size:12px;line-height:1.6;color:#92400e">'
        f'{items}</ul></div>'
    )


def _build_insight_changes(ic: dict[str, Any] | None) -> str:
    """P33: how the *insights* changed vs the baseline — new/resolved failure
    clusters, verdict move, judge-trust move, new security findings."""
    if not ic:
        return ""
    rows = ""

    def _line(icon: str, label: str, val: str, col: str = "#374151") -> str:
        return (f'<div style="font-size:12px;margin:3px 0"><span style="font-weight:700">'
                f'{icon} {_esc(label)}</span> <span style="color:{col}">{_esc(val)}</span></div>')

    vc = ic.get("verdict_change")
    if vc:
        rows += _line("🔀", "Verdict", f"{vc.get('from')} → {vc.get('to')}",
                      "#dc2626" if vc.get("to") == "not_ready" else "#059669")
    if ic.get("newly_failing_gates"):
        rows += _line("📉", "Newly below target", ", ".join(ic["newly_failing_gates"]), "#dc2626")
    if ic.get("newly_passing_gates"):
        rows += _line("✅", "Newly at target", ", ".join(ic["newly_passing_gates"]), "#059669")
    tc = ic.get("trust_change")
    if tc:
        rows += _line("⚖️", "Evaluator trust", f"{tc.get('from')} → {tc.get('to')}",
                      "#dc2626" if tc.get("to") == "low" else "#374151")
    if ic.get("new_clusters"):
        rows += _line("🆕", "New failure clusters",
                      "; ".join(_clip(s, 60) for s in ic["new_clusters"]), "#dc2626")
    if ic.get("resolved_clusters"):
        rows += _line("🧹", "Resolved failure clusters",
                      "; ".join(_clip(s, 60) for s in ic["resolved_clusters"]), "#059669")
    nsf = ic.get("new_security_findings") or []
    if nsf:
        rows += _line("🔒", "New security findings",
                      "; ".join(f"{s.get('task_id')}:{s.get('threat_type')}"
                                f"({s.get('severity')})" for s in nsf[:6]), "#dc2626")
    if not rows:
        return ""
    return (
        '<div class="gate-section" id="insight-changes" style="border-left-color:#0ea5e9">'
        '<h2 style="color:#1e2030">What Changed in the Insights</h2>'
        '<p style="color:#6b7280;font-size:12px;margin:0 0 6px">Meta-diff vs the baseline '
        '— not the metrics, but the findings.</p>'
        f'{rows}</div>'
    )


def _build_readiness(rd: dict[str, Any] | None) -> str:
    """P29: quantified distance to a passing verdict + an impact-ordered fix
    plan with a deterministic TCR projection. Sits right under the verdict."""
    if not rd or (not rd.get("gaps") and not rd.get("fix_plan")):
        return ""
    tgt = rd.get("target_gate_score", 0.7)

    gap_rows = ""
    for g in rd.get("gaps") or []:
        sc = g.get("score")
        gap = g.get("gap")
        after = g.get("projected_score_after_plan")
        col = "#dc2626" if g.get("blocking") else "#b45309"
        sc_cell = f'{sc:.2f}' if isinstance(sc, (int, float)) else "—"
        gap_cell = f'{gap:+.2f}' if isinstance(gap, (int, float)) else "—"
        _nfix = g.get("after_plan_fixes")
        after_cell = (
            f'~{after:.2f}<span style="color:#9ca3af;font-weight:400"> (est.'
            + (f", {_nfix} fix{'es' if _nfix != 1 else ''}" if _nfix else "")
            + ')</span>'
            if isinstance(after, (int, float)) else "—"
        )
        gname = _esc(g.get("gate_name", ""))
        _row_tgt = g.get("target")
        _tgt_s = f'{_row_tgt:.2f}' if isinstance(_row_tgt, (int, float)) else f'{tgt:.2f}'
        gap_rows += (
            f'<tr><td style="font-weight:600">Gate {g.get("gate")} '
            f'<span style="color:#6b7280;font-weight:400">{gname}</span></td>'
            f'<td style="text-align:right;color:{col};font-weight:700">{sc_cell}</td>'
            f'<td style="text-align:right;color:#6b7280">{_tgt_s}</td>'
            f'<td style="text-align:right;color:{col};font-weight:700">{gap_cell}</td>'
            f'<td style="text-align:right;color:#059669">{after_cell}</td></tr>'
        )

    _EFFORT_LABEL = {1.0: "low", 2.0: "low–med", 3.0: "med", 4.0: "high"}
    plan_rows = ""
    for it in rd.get("fix_plan") or []:
        gates = ", ".join(it.get("targets_gates") or []) or "—"
        _tts = it.get("task_types") or ([it["task_type"]] if it.get("task_type") else [])
        _tt_s = (f' <span style="color:#9ca3af;font-weight:400">· '
                 f'{_esc(", ".join(str(x) for x in _tts))}</span>' if _tts else "")
        # P37: projected gate vector + CI for the TCR-driven gates
        _pgs = it.get("projected_gate_scores") or {}
        _pci = it.get("projected_gate_scores_ci") or {}
        _moves = it.get("gate_moves") or {}
        _vec_bits = []
        for gk in sorted(_pgs):
            if _moves.get(gk):
                _c = _pci.get(gk)
                _ci_s = (f" [{_c[0]:.2f}–{_c[1]:.2f}]" if isinstance(_c, list) and len(_c) == 2
                         else "")
                _vec_bits.append(f"{gk}~{_pgs[gk]:.2f}{_ci_s}")
        _vec_s = (f'<div style="font-size:11px;color:#9ca3af">→ {" · ".join(_vec_bits)}</div>'
                  if _vec_bits else "")
        _eff_w = it.get("effort_weight")
        _eff_lbl = _EFFORT_LABEL.get(_eff_w, str(_eff_w) if _eff_w is not None else "—")
        _roi = it.get("roi")
        _roi_s = f'{_roi:.1f}' if isinstance(_roi, (int, float)) else "—"
        plan_rows += (
            f'<tr><td style="text-align:center;color:#6b7280">{it.get("rank")}</td>'
            f'<td><div style="font-weight:600">{_esc(_clip(it.get("signature", ""), 90))}{_tt_s}'
            f'</div><div style="font-size:11px;color:#6b7280">{_esc(it.get("effort_hint", ""))}'
            f'</div></td>'
            f'<td style="text-align:right;white-space:nowrap">{it.get("count")} task(s)'
            f'<div style="font-size:11px;color:#9ca3af">{it.get("impact_pct")}% of set</div></td>'
            f'<td style="text-align:center;font-size:11px;color:#6b7280">{_esc(gates)}'
            f'<div style="font-size:11px;color:#9ca3af">effort {_esc(_eff_lbl)} · '
            f'ROI {_roi_s}</div></td>'
            f'<td style="text-align:right;white-space:nowrap;'
            f'font-variant-numeric:tabular-nums">{it.get("projected_tcr_after_pct")}%'
            f'<div style="font-size:11px;color:#059669">'
            f'+{it.get("cumulative_tcr_gain_pp")}pp cum.</div>{_vec_s}</td></tr>'
        )

    pr = rd.get("projected_ready_after") or {}
    n = pr.get("ready_after_n_items")
    _note_col = "#059669" if n else "#b45309"
    _pr_ready = pr.get("p_ready")
    _lfc = pr.get("likely_fix_count")
    _conf_s = ""
    if isinstance(_pr_ready, (int, float)):
        _conf_s = (
            f' <span style="color:#6b7280">(~{_pr_ready * 100:.0f}% likely to clear'
            + (f" after {_lfc} fix{'es' if _lfc != 1 else ''}" if _lfc else "")
            + ', bootstrap over the flip rate)</span>'
        )
    verdict_line = (
        f'<span style="color:{_note_col};font-weight:700">Projected:</span> '
    )
    cur_tcr = rd.get("current_tcr_pct")
    cur_line = f'Current TCR {cur_tcr:.1f}%. ' if isinstance(cur_tcr, (int, float)) else ""

    _tgt_note = (
        '<p style="font-size:11px;color:#6b7280;margin:0 0 6px">Measured against '
        '<strong>your targets</strong> (.aoo/targets.json), not the built-in 0.7.</p>'
        if rd.get("targets_source") == "user" else ""
    )
    return (
        '<div class="gate-section" id="path-to-green" style="border-left-color:#dc2626">'
        '<h2 style="color:#1e2030">Path to Green</h2>'
        f'{_tgt_note}'
        '<h3 style="margin:6px 0 4px">Gate gaps</h3>'
        '<table class="mtable"><thead><tr><th>Gate</th><th>Now</th><th>Target</th>'
        '<th>Gap</th><th>After plan</th></tr></thead>'
        f'<tbody>{gap_rows}</tbody></table>'
        + (
            '<h3 style="margin:14px 0 4px">Fix plan — clusters by TCR impact</h3>'
            '<table class="mtable"><thead><tr><th>#</th><th>Failure cluster / where to look</th>'
            '<th>Size</th><th>Helps</th><th>Projected TCR</th></tr></thead>'
            f'<tbody>{plan_rows}</tbody></table>' if plan_rows else ""
        )
        + f'<p style="font-size:13px;margin:10px 0 0">{cur_line}{verdict_line}'
        f'<span style="color:#6b7280">{_esc(pr.get("note", ""))}</span>{_conf_s}</p>'
        '<p style="font-size:11px;color:#9ca3af;margin:4px 0 0">'
        'Projection is first-order — it assumes each cluster&rsquo;s tasks then pass '
        'and nothing else changes. Use it to sequence work, not as a guarantee.</p>'
        '</div>'
    )


def _build_executive_summary(harness_groups: dict, diagnosis: dict[str, Any] | None,
                             tcr: float, acc: float, total_tasks: int,
                             ci: dict[str, Any] | None = None,
                             verdict_obj: dict[str, Any] | None = None) -> str:
    """배포 준비도 한 줄 판정 + 확신도 배지 + 최우선 병목 + 다음 액션 1·2·3.

    새 판정 로직 없음 — Gate status와 rca.diagnose()의 component_shortfalls를
    우선순위(fail 먼저, 그다음 낮은 점수 순)로 재배열해 서술로 옮긴다. 확신도(P5)는
    utils.confidence.verdict_confidence()에 표본 수·TCR CI 폭·측정 컴포넌트 수·임계값
    여유를 넘겨 산출한다.
    """
    ci = ci or {}
    gate_rows = []
    for k in "ABCDEFG":
        g = harness_groups.get(k)
        if not isinstance(g, dict):
            continue
        st = (g.get("gate") or g.get("status") or "").lower()
        sc = g.get("score")
        if st in ("fail", "warn", "pass"):
            gate_rows.append((k, st, sc))

    fails = [r for r in gate_rows if r[1] == "fail"]
    warns = [r for r in gate_rows if r[1] == "warn"]

    if fails:
        verdict = "❌ Not deployment-ready"
        vcolor = "#ef4444"
        detail = f"{len(fails)} Gate(s) failing: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k, _, _ in fails)
    elif warns:
        verdict = "⚠️ Deploy with caution"
        vcolor = "#f59e0b"
        detail = f"{len(warns)} Gate(s) below target: " + ", ".join(
            f"{k} ({_GATE_FULL[k]})" for k, _, _ in warns)
    elif gate_rows:
        verdict = "✅ Deployment-ready"
        vcolor = "#10b981"
        detail = f"All {len(gate_rows)} measured Gates pass."
    else:
        verdict = "ℹ️ No Harness Gate data"
        vcolor = "#6b7280"
        detail = "Pass Harness Config to the decorator/monitor to get a gate verdict."

    # 다음 액션 — fail 게이트 먼저, 각 게이트에서 가장 약한 컴포넌트 + 조치.
    shortfalls_by_gate: dict[str, list] = {}
    if diagnosis:
        for f in diagnosis.get("findings") or []:
            shortfalls_by_gate[f.get("gate")] = f.get("component_shortfalls") or []

    ordered = fails + warns
    actions = []
    _v_actions = (verdict_obj or {}).get("next_actions") or []
    if _v_actions:
        # single source of truth — same next_actions the narrative uses (includes
        # a security-finding action and a low-sample flag, see insights._verdict_section)
        for a in _v_actions[:4]:
            _g = a.get("gate")
            _fld = _pretty_field(a.get("field"))
            _act = _trim_field_restatement(_fld, a.get("action") or "").rstrip(".")
            _hp = (f" ({a['health'] * 100:.0f}%)"
                   if isinstance(a.get("health"), (int, float)) else "")
            _tag = ""
            if a.get("security"):
                _tag = ' <span style="color:#dc2626;font-weight:700">SECURITY</span>'
            elif a.get("low_sample"):
                _tag = ' <span style="color:#9ca3af">(low sample — confirm first)</span>'
            _lead = f'<strong>Gate {_g}</strong>' if _g else '<strong>Action</strong>'
            if a.get("security"):
                # a security action is a directive, not a "fix <component>"
                _mid = f' — {_esc(_act)}' if _act else ''
                _tail = ''
            elif _fld:
                _mid = f' — fix <em>{_esc(_fld)}</em>{_hp}'
                _tail = f': {_esc(_act)}' if _act else ''
            else:
                _mid = f' — {_esc(_act)}' if _act else ''
                _tail = ''
            actions.append(f'<li>{_lead}{_tag}{_mid}{_tail}</li>')
    else:
        try:
            from agent_evaluator.ontology.metric_registry import component_guidance_for
        except Exception:
            component_guidance_for = lambda _f: None  # noqa: E731
        for k, _st, sc in ordered[:3]:
            sf = shortfalls_by_gate.get(k) or []
            if sf:
                top = sf[0]
                fld = _pretty_field(top.get("field", ""))
                act = _trim_field_restatement(
                    fld, component_guidance_for(top.get("field", "")) or "")
                hp = (f"{top['health'] * 100:.0f}%"
                      if isinstance(top.get("health"), (int, float)) else "")
                actions.append(
                    f'<li><strong>Gate {k}</strong> — fix <em>{_esc(fld)}</em>'
                    f'{f" ({hp})" if hp else ""}'
                    f'{f": {_esc(act)}" if act else ""}</li>'
                )
            else:
                sc_s = f" (score {sc:.2f})" if isinstance(sc, (int, float)) else ""
                actions.append(
                    f'<li><strong>Gate {k}</strong>{sc_s} — see the Gate {k} section below.</li>'
                )
    actions_html = (
        f'<p style="margin:10px 0 4px;font-size:13px;font-weight:600;color:#374151">'
        f'Next actions (priority order):</p>'
        f'<ol style="margin:0 0 0 20px;font-size:13px;line-height:1.8">{"".join(actions)}</ol>'
        if actions else ""
    )

    # P5: 판정 확신도 배지. verdict_obj가 있으면 그 값을 쓴다(insights와 동일 —
    # judge_trust 강등 등 반영). 없으면 기존처럼 여기서 재계산.
    conf_html = ""
    try:
        level = (verdict_obj or {}).get("confidence")
        reasons = (verdict_obj or {}).get("confidence_reasons") or []
        if level is None:
            from agent_evaluator.utils.confidence import verdict_confidence

            _drv = fails or warns   # 확신도를 좌우하는 주 Gate
            _ncomp = None
            _margin = None
            if _drv:
                _gk, _st, _sc = _drv[0]
                _sf = shortfalls_by_gate.get(_gk)
                if _sf is not None:
                    _ncomp = len(_sf)
                if isinstance(_sc, (int, float)):
                    _margin = float(_sc) - 0.8
            level, reasons = verdict_confidence(
                n_tasks=total_tasks,
                tcr_ci_halfwidth=ci.get("tcr_ci_halfwidth"),
                n_gate_components=_ncomp,
                margin_to_threshold=_margin,
            )
        _cc = {"high": "#10b981", "medium": "#f59e0b", "low": "#ef4444"}[level]
        _why = f" — {_esc('; '.join(reasons))}" if reasons else ""
        conf_html = (
            f'<p style="font-size:12px;margin-top:6px">'
            f'<span style="display:inline-block;padding:1px 8px;border-radius:10px;'
            f'font-weight:700;background:{_cc}22;color:{_cc};border:1px solid {_cc}66">'
            f'{level.upper()} CONFIDENCE</span>'
            f'<span style="color:#6b7280">{_why}</span></p>'
        )
    except Exception:
        pass

    _tcr_ci = _fmt_ci_pct(ci.get("tcr_ci"))
    _acc_ci = _fmt_ci_pct(ci.get("acc_ci"))
    return (
        '<div class="gate-section" id="exec-summary" '
        f'style="border-left-color:{vcolor};background:#fff">'
        '<h2 style="color:#1e2030;margin-bottom:8px">Executive Summary</h2>'
        f'<p style="font-size:16px;font-weight:800;color:{vcolor};margin-bottom:2px">{verdict}</p>'
        f'<p style="font-size:13px;color:#4b5563">{_esc(detail)}</p>'
        f'{conf_html}'
        f'<p style="font-size:12px;color:#6b7280;margin-top:4px">'
        f'{total_tasks} tasks · TCR {tcr:.1f}%{_tcr_ci} · Accuracy {acc:.1f}%{_acc_ci}</p>'
        f'{actions_html}'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Recommendations (P8 — 개선 루프 폐쇄)
# ---------------------------------------------------------------------------

def _rec_code_snippet(field: str, health: Any) -> str:
    """컴포넌트 → 붙여넣을 수 있는 @agent_eval 데코레이터 스니펫 (P8.1)."""
    try:
        from agent_evaluator.ontology.metric_registry import config_hint_for
    except Exception:
        return ""
    h = config_hint_for(field)
    if not h:
        return ""
    cur = ""
    if isinstance(health, (int, float)):
        cur = f"  # current: {health * 100:.0f}% health"
    code = (
        f"from agent_evaluator import {h['config']}\n\n"
        f"@agent_eval(monitor, task_type=...,\n"
        f"    {h['slot']}={h['config']}({h['example']}),{cur}\n"
        f")\n"
        f"def your_agent(...): ..."
    )
    return (
        '<pre style="background:#0f172a;color:#e2e8f0;font-size:11px;line-height:1.5;'
        'padding:10px 12px;border-radius:6px;overflow-x:auto;margin:6px 0">'
        f'{_esc(code)}</pre>'
    )


def _rec_past_outcomes(recommendation_log_path: Any, gate: str) -> str:
    """이 Gate에 대한 과거 조치 이력 요약 (P8.2) — "이전에 뭐가 통했나"."""
    if recommendation_log_path is None:
        return ""
    try:
        from agent_evaluator.rca.recommendation_tracking import load_recommendation_outcomes

        outs = load_recommendation_outcomes(recommendation_log_path, target_gate=gate)
    except Exception:
        return ""
    if not outs:
        return ""
    conf = [o for o in outs if o.get("verdict") == "confirmed"]
    ref = [o for o in outs if o.get("verdict") == "refuted"]
    deltas = [o.get("gate_delta") for o in conf if isinstance(o.get("gate_delta"), (int, float))]
    avg_d = (sum(deltas) / len(deltas)) if deltas else None
    last = outs[-1]
    _note = _esc((last.get("note") or last.get("recommendation_id") or "")[:80])
    avg_s = f", confirmed changes averaged Δ {avg_d:+.3f}" if avg_d is not None else ""
    return (
        f'<p style="margin:6px 0 0;font-size:11px;color:#6b7280">'
        f'📈 Past changes to Gate {gate}: {len(conf)} confirmed / {len(ref)} refuted '
        f'/ {len(outs)} total{avg_s}. Last: “{_note}”.</p>'
    )


def _rec_experiment_block(gate: str, field: str, health: Any, n_components: int) -> str:
    """A/B 실험 제안 (P8.3) — 예측 델타 + 권장 표본 수 + 실행 명령."""
    if not isinstance(health, (int, float)) or n_components <= 0:
        return ""
    target = 0.85
    if health >= target:
        return ""
    predicted = (target - health) / max(n_components, 1)
    # P27: recalibrate the heuristic Δ against past confirmed experiments for the
    # same Gate/field, when .aoo/experiments.jsonl has ≥2 such outcomes.
    calib_note = ""
    try:
        _exp_log = Path(".aoo/experiments.jsonl")
        if _exp_log.is_file():
            from agent_evaluator.rca.experiments import load_experiments, recalibrated_delta

            _rc, _n = recalibrated_delta(
                load_experiments(_exp_log), gate, field, predicted,
            )
            if _n >= 2:
                calib_note = (
                    f' <span style="color:#6b7280">(recalibrated to +{_rc:.2f} '
                    f'from {_n} past outcome(s))</span>'
                )
                predicted = _rc
    except Exception:
        pass
    try:
        from agent_evaluator.utils.confidence import required_n_for_halfwidth

        need_n = required_n_for_halfwidth(0.5, max(abs(predicted) / 2.0, 0.02))
    except Exception:
        need_n = 40
    fld = field.replace("avg_", "").replace("_", " ")
    return (
        f'<p style="margin:6px 0 0;font-size:12px;color:#4b5563">'
        f'🧪 <strong>Run it as an experiment</strong>: if <em>{_esc(fld)}</em> reaches '
        f'{target * 100:.0f}%, Gate {gate} ≈ +{predicted:.2f}{calib_note} '
        f'(rough; ~{need_n} tasks recommended to confirm). '
        f'<code>agent-eval experiment register --gate {gate} --field {_esc(field)} '
        f'--predict-delta {predicted:.2f}</code></p>'
    )


def _rec_baseline_verdict(baseline: dict[str, Any] | None, current: dict[str, Any] | None,
                          gate: str) -> str:
    """baseline이 있으면 이 Gate의 변화를 confirmed/refuted/inconclusive로 (P8.4)."""
    if not baseline or not current:
        return ""
    try:
        from agent_evaluator.rca.verify import verify_recommendation_outcome

        v = verify_recommendation_outcome(baseline, current, target_gate=gate)
    except Exception:
        return ""
    d = v.get("gate_delta")
    verd = v.get("verdict")
    if d is None or verd == "inconclusive":
        return ""
    col = "#059669" if verd == "confirmed" else "#dc2626"
    arrow = "▲" if d > 0 else "▼"
    _phrase = "improved vs baseline" if d > 0 else "regressed vs baseline"
    return (
        f'<p style="margin:4px 0 0;font-size:11px;color:{col};font-weight:600">'
        f'{arrow} Since baseline: {v.get("before_score"):.3f} → {v.get("after_score"):.3f} '
        f'(Δ {d:+.3f}) — {_phrase}</p>'
    )


_PROPOSAL_KIND_LABEL = {
    "prompt_edit": ("Prompt edit", "#7c3aed"),
    "config_change": ("Config change", "#0ea5e9"),
    "data_fix": ("Eval-set fix", "#d97706"),
}


def _rec_proposal_html(p: dict[str, Any] | None) -> str:
    """P36: render an evidence-grounded fix proposal (before → after + rationale +
    the task ids it is based on). A draft for a human — never auto-applied."""
    if not p or not isinstance(p, dict):
        return ""
    lbl, col = _PROPOSAL_KIND_LABEL.get(p.get("kind", ""), (p.get("kind", "Change"), "#6b7280"))
    src = "LLM-drafted" if p.get("authored_by") == "fixer" else "template"
    before = _esc(str(p.get("before", "")))
    after = _esc(str(p.get("after", "")))
    rationale = _esc(str(p.get("rationale", "")))
    ev = ", ".join(_esc(str(x)) for x in (p.get("evidence_task_ids") or []))
    return (
        '<div style="margin:8px 0 0;border:1px solid #e5e7eb;border-radius:8px;'
        'padding:10px 12px;background:#fff">'
        f'<div style="font-size:11px;font-weight:700;color:{col};text-transform:uppercase;'
        f'letter-spacing:.4px">Proposed fix — {_esc(lbl)} '
        f'<span style="color:#9ca3af;font-weight:400;text-transform:none">({src}, '
        f'review before applying)</span></div>'
        f'<div style="font-size:12px;margin-top:6px"><span style="color:#dc2626">− </span>'
        f'<code style="background:#fef2f2;padding:1px 4px;border-radius:3px">{before}</code></div>'
        f'<div style="font-size:12px;margin-top:3px"><span style="color:#059669">+ </span>'
        f'<code style="background:#ecfdf5;padding:1px 4px;border-radius:3px;'
        f'white-space:pre-wrap">{after}</code></div>'
        f'<p style="font-size:11px;color:#6b7280;margin:6px 0 0">{rationale}</p>'
        + (f'<p style="font-size:11px;color:#9ca3af;margin:2px 0 0">Evidence: {ev}</p>'
           if ev else "")
        + '</div>'
    )


def _build_recommendations(harness_groups: dict, tcr: float, acc: float,
                             hall_rate: float, latency: float,
                             quality_metrics: dict,
                             diagnosis: dict[str, Any] | None = None,
                             *,
                             recommendation_log_path: Any = None,
                             baseline: dict[str, Any] | None = None,
                             current: dict[str, Any] | None = None,
                             insights_recs: list[dict[str, Any]] | None = None) -> str:
    from agent_evaluator.ontology.metric_registry import (
        GATE_GUIDANCE,
        component_guidance_for,
        evaluate_native_metric_rules,
    )

    recs = []
    # P36: evidence-grounded fix proposals, keyed by gate (from insights.recommendations)
    _proposal_by_gate = {
        r.get("gate"): r.get("proposal")
        for r in (insights_recs or []) if r.get("proposal")
    }

    # diagnosis(rca.diagnose() 반환값)의 findings에서 Gate별 최악 컴포넌트를 뽑아둔다 —
    # Gate 단위 일반론 대신 "측정된 이 컴포넌트가 병목"이라고 구체적으로 짚기 위해서.
    shortfalls_by_gate: dict[str, list] = {}
    if diagnosis:
        for _f in diagnosis.get("findings") or []:
            shortfalls_by_gate[_f.get("gate")] = _f.get("component_shortfalls") or []

    # Gate-based FAIL/WARN recommendations — 지식(라벨+안내문)은 ontology.metric_registry에서.
    for key in "ABCDEFG":
        gdata = harness_groups.get(key, {})
        if not isinstance(gdata, dict):
            continue
        gate_status = (gdata.get("gate") or gdata.get("status") or "").lower()
        if gate_status in ("fail", "warn"):
            _default = GATE_GUIDANCE.get(key)
            label = _default.label if _default else f"Gate {key}"
            guide = _default.guidance if _default else "Review configuration."
            priority_class = "priority-high" if gate_status == "fail" else "priority-medium"
            badge_cls = "badge-fail" if gate_status == "fail" else "badge-warn"
            badge_label = "FAIL" if gate_status == "fail" else "WARN"

            _shortfalls = shortfalls_by_gate.get(key) or []
            _ncomp = len(_shortfalls)

            # components measured below their minimum sample size — flag them so a
            # recommendation on a shaky metric is visible as such.
            _low_samp = {
                str(_w).split(":", 1)[0].strip().lower()
                for _w in (gdata.get("details") or {}).get("insufficient_data_warnings") or []
            }

            # 이 Gate에서 가장 낮은 컴포넌트 2개 → 구체 조치.
            comp_html = ""
            comp_items = []
            for _s in _shortfalls[:2]:
                _fld = _s.get("field", "")
                _health = _s.get("health")
                _hp = f"{_health * 100:.0f}%" if isinstance(_health, (int, float)) else "—"
                _label_txt = _esc(_pretty_field(_fld))
                _act = _trim_field_restatement(
                    _pretty_field(_fld),
                    component_guidance_for(_fld) or _diag_native_rule_guidance(_fld) or "")
                _fld_norm = str(_fld).replace("avg_", "").strip().lower()
                _ls = (' <span style="color:#9ca3af">(low sample — confirm first)</span>'
                       if _fld_norm in _low_samp else '')
                _bits = (f'<li><strong>{_label_txt}</strong> ({_hp}){_ls}'
                         + (f' — {_esc(_act)}' if _act else '') + '</li>')
                comp_items.append(_bits)
            if comp_items:
                comp_html = (
                    '<p style="margin:8px 0 2px;font-size:12px;color:#6b7280">'
                    'Biggest measured shortfalls:</p>'
                    f'<ul style="margin:0 0 0 18px;font-size:13px;line-height:1.7">'
                    f'{"".join(comp_items)}</ul>'
                    '<p style="margin:6px 0 0;font-size:11px;color:#9ca3af">'
                    'See the Gate Failure / RCA Diagnosis section below for the full ranking.</p>'
                )

            # P8: 최악 컴포넌트 기준으로 코드 스니펫·과거 이력·실험 제안·baseline 변화.
            _top_fld = _shortfalls[0].get("field", "") if _shortfalls else ""
            _top_h = _shortfalls[0].get("health") if _shortfalls else None
            code_html = _rec_code_snippet(_top_fld, _top_h) if _top_fld else ""
            past_html = _rec_past_outcomes(recommendation_log_path, key)
            exp_html = _rec_experiment_block(key, _top_fld, _top_h, _ncomp) if _top_fld else ""
            base_html = _rec_baseline_verdict(baseline, current, key)
            proposal_html = _rec_proposal_html(_proposal_by_gate.get(key))

            recs.append(
                f'<div class="rec {priority_class}">'
                f'<strong><span class="badge {badge_cls}">{badge_label}</span> Gate {key} — {label}</strong>'
                f'{base_html}'
                f'<p>{guide}</p>'
                f'{comp_html}'
                f'{proposal_html}'
                f'{code_html}'
                f'{exp_html}'
                f'{past_html}'
                f'</div>'
            )

    # Native metric recommendations — 임계값 규칙도 ontology.metric_registry에서.
    for _rule in evaluate_native_metric_rules(
        tcr=tcr, accuracy=acc, hallucination_rate=hall_rate, latency=latency,
    ):
        _priority_class = "priority-high" if _rule.priority == "high" else "priority-medium"
        recs.append(
            f'<div class="rec {_priority_class}"><strong>{_rule.title}</strong>'
            f'<p>{_rule.guidance}</p></div>'
        )

    if not recs:
        recs.append(
            '<div class="rec" style="border-left-color:#10b981">'
            '<strong style="color:#065f46">All metrics healthy</strong>'
            '<p>No metrics require improvement under the current configuration. Maintain continuous monitoring.</p>'
            '</div>'
        )

    return (
        '<div class="gate-section" id="recommendations" style="border-left-color:#6366f1">'
        '<h2 style="color:#6366f1">Recommendations</h2>'
        + ''.join(recs)
        + '</div>'
    )


# ---------------------------------------------------------------------------
# Gate RCA diagnosis — 대시보드 "Improve" 탭과 동일한 rca.diagnose()를 정적
# HTML 리포트에도 반영한다(새 판정 로직 없음, serve/routers/diagnose.py와 동일
# 호출 패턴 재사용).
# ---------------------------------------------------------------------------

def _diag_fmt_value(field: str, v: float) -> str:
    """component_shortfalls의 원시 값을 필드 단위에 맞춰 사람이 읽을 문자열로."""
    if field.endswith("_pct"):
        return f"{v:.1f}%"
    if field.endswith("_s"):
        return f"{v:.3f}s"
    if field.endswith("_ms"):
        return f"{v:.0f}ms"
    if 0.0 <= v <= 1.0:
        return f"{v:.3f}"
    return f"{v:.2f}"


def _diag_native_rule_guidance(field: str) -> str:
    """Gate details 필드명 → NATIVE_METRIC_RULES 처방 문구(매칭 규칙 없으면 "")."""
    try:
        from agent_evaluator.ontology.metric_registry import (
            NATIVE_METRIC_RULES,
            canonical_metric_name,
        )
        canon = canonical_metric_name(field)
        for rule in NATIVE_METRIC_RULES:
            if rule.metric == canon:
                return rule.guidance
    except Exception:
        pass
    return ""


def _build_diagnosis(
    current_dict: dict[str, Any],
    baseline_dict: dict[str, Any] | None = None,
    *,
    recommendation_log_path: Any = None,
) -> str:
    """Gate RCA 진단(``rca.diagnose()``) + 추천 이력을 정적 HTML 섹션으로 렌더링한다.

    ``agent-eval diagnose`` CLI(``cli/diagnose.py::_print_finding()``)·대시보드
    Improve 탭과 동일한 필드를 그대로 옮긴다 — 여기서 새로 계산하는 값은 없다.
    """
    from agent_evaluator.rca import diagnose
    from agent_evaluator.rca.recommendation_tracking import (
        load_recommendation_outcomes,
        summarize_recommendation_outcomes,
    )

    try:
        result = diagnose(current_dict, baseline_dict)
    except Exception as e:
        return (
            '<div class="gate-section" id="diagnosis" style="border-left-color:#0ea5e9">'
            '<h2 style="color:#0ea5e9">🔍 Gate RCA Diagnosis</h2>'
            f'<p style="color:#6b7280">Could not compute diagnosis: {_esc(str(e))}</p></div>'
        )

    blocks: list[str] = []
    _is_absolute = result["detection_mode"] == "absolute_threshold"

    mode_label = {
        "regression_vs_baseline": "Regression-based detection (vs baseline)",
        "absolute_threshold": "Absolute-threshold detection (current fail/warn state)",
    }.get(result["detection_mode"], result["detection_mode"])
    blocks.append(
        f'<p style="color:#6b7280;margin:0 0 12px">Detection mode: {_esc(mode_label)}</p>'
    )
    if _is_absolute:
        blocks.append(
            '<p style="color:#6b7280;margin:0 0 12px;font-size:13px">'
            'This is a single batch evaluation (no baseline), so there is nothing to '
            'diff against. The table below instead ranks each detected Gate\'s measured '
            'score components from weakest to strongest — that is what is holding the '
            'Gate back right now. Run a baseline comparison for regression attribution '
            '(baseline vs current delta).</p>'
        )

    if result.get("multi_gate_note"):
        blocks.append(
            f'<div class="rec priority-medium"><p>⚠️ {_esc(result["multi_gate_note"])}</p></div>'
        )

    sla_check = result.get("sla_shared_cause_check")
    if sla_check:
        blocks.append(f'<div class="rec priority-medium"><p>{_esc(sla_check["note"])}</p></div>')

    # SPEC-041: baseline엔 점수가 있었는데 current엔 사라진 Gate — 회귀 감지가 놓치는
    # 측정 커버리지 손실. CLI(cli/diagnose.py)와 동일한 경고를 HTML 리포트에도 낸다.
    _unmeasured = result.get("newly_unmeasured_gates") or []
    if _unmeasured:
        blocks.append(
            '<div class="rec priority-medium">'
            f'<strong>⚠️ Measurement coverage lost: Gate(s) {_esc(", ".join(_unmeasured))}</strong>'
            '<p>These Gates had a baseline score but are not measured in this run. '
            'A Config may have been removed from the decorator/monitor.</p></div>'
        )

    if not result["detected_gates"] and not _unmeasured:
        blocks.append(
            '<div class="rec" style="border-left-color:#10b981">'
            '<strong style="color:#065f46">No regression or fail/warn Gate detected</strong>'
            '<p>No Gate is currently in a regression or fail/warn state.</p></div>'
        )
    for finding in result["findings"]:
        gate = finding["gate"]
        cur = finding["current_score"]
        base = finding["baseline_score"]
        cur_str = f"{cur:.4f}" if cur is not None else "n/a"
        base_str = f" (baseline {base:.4f})" if base is not None else ""

        guidance_html = ""
        if _is_absolute:
            # baseline이 없으므로 delta 대신 "지금 점수를 깎는 컴포넌트"를 약한 순으로.
            sf = finding.get("component_shortfalls") or []
            if sf:
                sf_rows = "".join(
                    f'<tr><td>{_esc(s["field"])}</td>'
                    f'<td>{_diag_fmt_value(s["field"], s["value"])}</td>'
                    f'<td style="color:{_score_color(s["health"] * 100)}">'
                    f'{s["health"] * 100:.1f}%</td></tr>'
                    for s in sf
                )
                table = (
                    '<table class="mtable"><thead><tr><th>Component</th>'
                    '<th>Current</th><th>Health</th></tr></thead>'
                    f'<tbody>{sf_rows}</tbody></table>'
                )
            else:
                table = ('<p style="color:#9ca3af">No interpretable score components '
                         'recorded for this Gate</p>')
            _bits: list[str] = []
            try:
                from agent_evaluator.ontology.metric_registry import GATE_GUIDANCE
                _gg = GATE_GUIDANCE.get(gate)
                if _gg is not None:
                    _bits.append(_esc(_gg.guidance))
            except Exception:
                pass
            for _s in sf[:3]:
                _rule_g = _diag_native_rule_guidance(_s["field"])
                if _rule_g and _esc(_rule_g) not in _bits:
                    _bits.append(_esc(_rule_g))
            if _bits:
                guidance_html = "".join(
                    f'<p style="margin:8px 0 0;color:#4b5563">→ {b}</p>' for b in _bits
                )
        else:
            rows, newly_measured = [], []
            for d in finding["top_detail_deltas"]:
                delta = d["delta"]
                # P35: a row with no baseline value isn't a regression — it's a
                # metric that started being measured this run. Split it out.
                if d["baseline"] is None and delta is None:
                    if d["current"] is not None:
                        newly_measured.append((d["field"], d["current"]))
                    continue
                delta_str = f"{delta:+.4f}" if delta is not None else "n/a"
                delta_color = "#dc2626" if (delta is not None and delta < 0) else "#16a34a"
                b_str = f"{d['baseline']:.4f}" if d["baseline"] is not None else "n/a"
                c_str = f"{d['current']:.4f}" if d["current"] is not None else "n/a"
                rows.append(
                    f'<tr><td>{_esc(d["field"])}</td><td>{b_str}</td><td>{c_str}</td>'
                    f'<td style="color:{delta_color}">{delta_str}</td></tr>'
                )
            table = (
                '<table class="mtable"><thead><tr><th>Metric</th><th>Baseline</th>'
                f'<th>Current</th><th>Delta</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
                if rows else '<p style="color:#9ca3af">No comparable detail metrics</p>'
            )
            if newly_measured:
                table += (
                    '<p style="font-size:12px;color:#6b7280;margin:6px 0 0">'
                    'Newly measured this run (no baseline to compare): '
                    + ", ".join(f"{_esc(str(f))} {v:.3f}" for f, v in newly_measured)
                    + "</p>"
                )

        refs_html = ""
        refs = finding.get("cross_references") or []
        if refs:
            items = "".join(
                f'<li>{_esc((r.get("summary") or r.get("text") or str(r))[:120])}</li>'
                for r in refs[:5]
            )
            refs_html = (
                f'<p style="margin:8px 0 4px;color:#6b7280">Related violation history:</p>'
                f'<ul>{items}</ul>'
            )
        mast_html = ""
        mast = finding.get("mast_candidates") or []
        if mast:
            cards = "".join(
                f'<div class="rec priority-medium">'
                f'<strong>[{_esc(m["code"])}] {_esc(m["name"])}</strong> '
                f'<span style="color:#6b7280">'
                f'(observed in {_esc(str(m["prevalence_pct"]))}% of paper traces)</span>'
                f'<p>{_esc(m["description"])}</p>'
                f'<p style="color:#6b7280">→ {_esc(m["remediation"])}</p></div>'
                for m in mast
            )
            mast_html = (
                '<p style="margin:8px 0 4px;color:#6b7280">MAST candidate failure modes '
                '(Cemri et al., NeurIPS 2025 — not a conclusion):</p>' + cards
            )
        _score_caption = (
            ' <span style="color:#6b7280;font-weight:400">(weakest score components first)</span>'
            if _is_absolute else ""
        )
        blocks.append(
            f'<div class="rec priority-high"><strong>Gate {_esc(gate)}</strong> — '
            f'score {cur_str}{base_str}{_score_caption}'
            f'{table}{guidance_html}{refs_html}{mast_html}</div>'
        )

    outcomes_html = ""
    if recommendation_log_path is not None:
        outcomes = load_recommendation_outcomes(recommendation_log_path)
        if outcomes:
            summary = summarize_recommendation_outcomes(outcomes)
            outcome_rows = "".join(
                f'<tr><td>{_esc(o.get("recorded_at", "")[:19])}</td>'
                f'<td>{_esc(o.get("target_gate", ""))}</td>'
                f'<td>{_esc(o.get("verdict", ""))}</td>'
                f'<td>{o.get("gate_delta") if o.get("gate_delta") is not None else "n/a"}</td>'
                f'<td>{_esc(o.get("note") or "")}</td></tr>'
                for o in outcomes[-10:]
            )
            outcomes_html = (
                '<h3 style="margin-top:20px">Improvement history '
                f'(confirmed {summary["confirmed"]} · refuted {summary["refuted"]} · '
                f'inconclusive {summary["inconclusive"]})</h3>'
                '<table class="mtable"><thead><tr><th>Recorded</th><th>Gate</th><th>Verdict</th>'
                f'<th>Δ</th><th>Note</th></tr></thead><tbody>{outcome_rows}</tbody></table>'
            )

    _section_title = (
        "🔍 Gate Failure Diagnosis" if _is_absolute
        else "🔍 Gate RCA Diagnosis (Improve)"
    )
    return (
        '<div class="gate-section" id="diagnosis" style="border-left-color:#0ea5e9">'
        f'<h2 style="color:#0ea5e9">{_section_title}</h2>'
        + ''.join(blocks)
        + outcomes_html
        + '<p style="color:#9ca3af;font-size:12px;margin-top:12px">'
        'HOTL — this section presents candidate causes and evidence only. '
        'The final judgment is yours.</p>'
        '</div>'
    )


def _build_threshold_sensitivity(ts: dict[str, Any] | None) -> str:
    """P44: is the deploy decision robust, or one arbitrary 0.05 from flipping?
    Sweeps the gate pass line and the per-task accuracy threshold."""
    if not ts or not ts.get("gate_line_sweep"):
        return ""
    cur = ts.get("current_line", 0.7)
    ke = ts.get("knife_edge")
    banner = ""
    if ke:
        banner = (
            '<p style="font-size:12px;color:#b45309;background:#fffbeb;border:1px '
            'solid #fde68a;border-radius:6px;padding:8px 10px;margin:0 0 8px">'
            f'⚠️ {_esc(ts.get("knife_edge_detail", ""))}</p>'
        )
    else:
        banner = (
            '<p style="font-size:12px;color:#059669;margin:0 0 8px">'
            f'The readiness call is stable across ±0.05 of the {cur:.2f} pass '
            'line.</p>'
        )
    rows = ""
    for r in ts["gate_line_sweep"]:
        _is_cur = abs(r["line"] - cur) < 1e-6
        _tr = ' style="font-weight:700"' if _is_cur else ""
        _cur_tag = " ← current" if _is_cur else ""
        _vc = {"ready": "#059669", "caution": "#d97706",
               "not_ready": "#dc2626"}.get(r["verdict"], "#6b7280")
        rows += (
            f'<tr{_tr}>'
            f'<td>{r["line"]:.2f}{_cur_tag}</td>'
            f'<td style="text-align:right">{r["gates_meeting"]}</td>'
            f'<td style="text-align:right">{r["gates_below"]}</td>'
            f'<td style="color:{_vc}">{_esc(r["verdict"])}</td></tr>'
        )
    acc_rows = ""
    for r in ts.get("accuracy_threshold_sweep") or []:
        pr = r.get("pass_rate_pct")
        acc_rows += (
            f'<tr><td>{r["threshold"]:.2f}</td>'
            f'<td style="text-align:right">{pr:.1f}%</td></tr>'
            if isinstance(pr, (int, float)) else ""
        )
    acc_html = ""
    if acc_rows:
        acc_html = (
            '<h3 style="margin:12px 0 4px">Pass rate vs accuracy threshold</h3>'
            '<table class="mtable"><thead><tr><th>Accuracy ≥</th>'
            '<th>Tasks passing</th></tr></thead>'
            f'<tbody>{acc_rows}</tbody></table>'
        )
    return (
        '<div class="gate-section" id="threshold-sensitivity" '
        'style="border-left-color:#64748b">'
        '<h2 style="color:#1e2030">Threshold Sensitivity</h2>'
        '<p style="color:#6b7280;font-size:13px;margin:0 0 6px">The verdict hinges '
        'on where the pass line is drawn. This sweeps it.</p>'
        f'{banner}'
        '<table class="mtable"><thead><tr><th>Pass line</th><th>Gates meeting</th>'
        '<th>Gates below</th><th>Readiness</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'{acc_html}</div>'
    )


# ---------------------------------------------------------------------------
# Conclusion
# ---------------------------------------------------------------------------

def _build_conclusion(total_tasks: int, tcr: float, acc: float,
                       hall_rate: float, harness_groups: dict,
                       ci: dict[str, Any] | None = None) -> str:
    try:
        from agent_evaluator import __version__ as _ver
    except Exception:
        _ver = "0.8.2"
    ci = ci or {}

    pass_count = sum(
        1 for key in "ABCDEFG"
        if isinstance(harness_groups.get(key), dict)
        and (harness_groups[key].get("gate") or harness_groups[key].get("status") or "").lower() == "pass"
    )
    # Only count gates that actually produced a score — an un-configured gate (B, F
    # with no data) is "n/a", not a failure, so "2/7" would understate the result.
    _scored = [
        key for key in "ABCDEFG"
        if isinstance(harness_groups.get(key), dict)
        and harness_groups[key].get("score") is not None
    ]
    total_active = len(_scored)
    _n_unscored = 7 - total_active

    # Was the hallucination RATE actually measured? Gate C/G store it only when
    # HallucinationDetector ran. LLM-judge faithfulness feeds the Gate score but is
    # a different signal — it does not make "Hallucination Rate: 0.0%" true.
    _hall_measured = any(
        isinstance(harness_groups.get(k), dict)
        and (harness_groups[k].get("details") or {}).get("hallucination_rate") is not None
        for k in ("C", "G")
    )
    _hall_str = f"{hall_rate:.1f}%" if _hall_measured else "n/a (not enabled)"

    grade = "S (Outstanding)" if tcr >= 95 and acc >= 90 else \
            "A (Excellent)" if tcr >= 90 and acc >= 85 else \
            "B (Good)" if tcr >= 80 and acc >= 70 else \
            "C (Fair)" if tcr >= 70 else "D (Needs Improvement)"

    # P5: Grade 확신도 — 표본 수 + TCR CI 폭 기준. CI 폭이 넓거나 표본이 적으면
    # Grade 경계가 CI 안에 걸쳐 있을 수 있으므로 사용자에게 고지한다.
    _conf = ""
    try:
        from agent_evaluator.utils.confidence import verdict_confidence

        _lvl, _rs = verdict_confidence(
            n_tasks=total_tasks, tcr_ci_halfwidth=ci.get("tcr_ci_halfwidth"),
        )
        _cc = {"high": "#065f46", "medium": "#92400e", "low": "#991b1b"}[_lvl]
        _tail = f" ({_esc('; '.join(_rs))})" if _rs else ""
        _conf = f' <span style="color:{_cc};font-weight:600">— {_lvl} confidence{_tail}</span>'
    except Exception:
        pass

    _ci_line = ""
    if ci.get("tcr_ci"):
        _ci_line = (f'<p style="font-size:12px;color:#6b7280">'
                    f'TCR 95% CI: {ci["tcr_ci"][0]:.1f}–{ci["tcr_ci"][1]:.1f}%'
                    + (f' · Accuracy 95% CI: {ci["acc_ci"][0]:.1f}–{ci["acc_ci"][1]:.1f}%'
                       if ci.get("acc_ci") else "")
                    + '</p>')

    _gate_line = ""
    if total_active > 0:
        _unscored_note = (
            f' <span style="font-size:12px;color:#6b7280">'
            f'({_n_unscored} gate(s) not measured)</span>'
            if _n_unscored else ""
        )
        _gate_line = (
            f'<p><strong>Harness Gate:</strong> {pass_count}/{total_active} '
            f'measured PASS{_unscored_note}</p>'
        )

    return (
        f'<div class="gate-section" id="conclusion" style="border-left-color:#374151">'
        f'<h2 style="color:#374151">Conclusion</h2>'
        f'<div class="ibox ok">'
        f'<p><strong>Grade:</strong> {grade}{_conf}</p>'
        f'<p><strong>Total Tasks:</strong> {total_tasks}</p>'
        f'<p><strong>TCR:</strong> {_num(tcr, ".1f")}% | <strong>Accuracy:</strong> {_num(acc, ".1f")}% | '
        f'<strong>Hallucination Rate:</strong> {_hall_str}</p>'
        f'{_ci_line}'
        f'{_gate_line}'
        f'</div>'
        f'<div class="footer">'
        f'<p>Generated by <strong>Agent Evaluator v{_ver}</strong> &nbsp;|&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

# P5: per-task score 리스트에서 TCR/Accuracy의 95% 부트스트랩 CI를 계산한다.
# 소비: 헤더 표시 + Executive Summary 확신도 배지 + Conclusion Grade.
def _metric_ci_data(tasks: list[Any]) -> dict[str, Any]:
    if not tasks:
        return {}
    comps: list[float] = []
    accs: list[float] = []
    for t in tasks:
        raw = getattr(t, "raw", None)
        src = raw if isinstance(raw, dict) else None

        def _get(key: str, _t: Any = t, _s: Any = src) -> Any:
            return _s.get(key) if _s is not None else getattr(_t, key, None)

        c = _safe_float(_get("completion_score"), None)
        a = _safe_float(_get("accuracy_score"), None)
        if c is not None:
            comps.append(c)
        if a is not None:
            accs.append(a)
    out: dict[str, Any] = {"n": len(tasks)}
    try:
        from agent_evaluator.utils.confidence import bootstrap_mean_ci

        if comps:
            lo, hi = bootstrap_mean_ci(comps)
            out["tcr_ci"] = (lo * 100.0, hi * 100.0)
            out["tcr_ci_halfwidth"] = (hi - lo) / 2.0
        if accs:
            lo, hi = bootstrap_mean_ci(accs)
            out["acc_ci"] = (lo * 100.0, hi * 100.0)
    except Exception:
        pass
    return out


def _fmt_ci_pct(ci: Any) -> str:
    if not ci or len(ci) != 2:
        return ""
    return (f' <span style="font-weight:400;opacity:.75">'
            f'(95% CI {ci[0]:.0f}–{ci[1]:.0f}%)</span>')


def _build_header(total_tasks: int, tcr: float, acc: float,
                  latency: float, harness_groups: dict,
                  ci: dict[str, Any] | None = None) -> str:
    try:
        from agent_evaluator import __version__ as _ver
    except Exception:
        _ver = "0.8.2"
    ci = ci or {}

    gate_badges = ""
    for key in "ABCDEFG":
        gdata = harness_groups.get(key, {})
        _g_gate = gdata.get("gate") or gdata.get("status")
        if isinstance(gdata, dict) and _g_gate:
            gate_badges += (
                f'<span style="margin-right:6px">'
                f'<span style="font-size:10px;color:{_GATE_COLORS[key]};font-weight:700">Gate {key} </span>'
                f'{_gate_badge(_g_gate)}</span>'
            )

    gate_badges_div = f'<div style="margin-top:10px">{gate_badges}</div>' if gate_badges else ""
    return (
        '<div class="rpt-header">'
        '<h1>📊 Agent Evaluator — Harness Gate Report</h1>'
        '<div class="sub">AI Agent Quality Evaluation · Harness Gate A–G Architecture</div>'
        f'<div class="meta">'
        f'<span>📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>'
        f'<span>📋 {total_tasks} tasks</span>'
        f'<span>🔖 v{_ver}</span>'
        f'<span>TCR: <strong>{_num(tcr, ".1f")}%</strong>'
        f'{_fmt_ci_pct(ci.get("tcr_ci"))}</span>'
        f'<span>Accuracy: <strong>{_num(acc, ".1f")}%</strong>'
        f'{_fmt_ci_pct(ci.get("acc_ci"))}</span>'
        f'<span>Latency: <strong>{_num(latency, ".2f")}s</strong></span>'
        f'</div>'
        f'{gate_badges_div}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# generate_comprehensive_html_report(monitor)
# ---------------------------------------------------------------------------

def generate_comprehensive_html_report(monitor, baseline: dict[str, Any] | None = None,
                                       cohort: list[dict[str, Any]] | None = None) -> str:
    """Generate Harness Gate A–G 중심 종합 HTML 리포트.

    Args:
        monitor: PerformanceMonitor or HybridPerformanceMonitor instance.
        baseline: (선택) 비교 기준 결과 dict — 주어지면 Gate RCA 진단 섹션이
            회귀 기반 감지(``regression_vs_baseline``)로 동작한다. 생략하면
            현재 fail/warn 상태 기반 감지(``absolute_threshold``)로 폴백한다
            (``rca.diagnose()``와 동일 규칙, 기존 호출부는 동작 변경 없음).

    Returns:
        Self-contained HTML string.
    """
    # --- Collect report / metrics ---
    if hasattr(monitor, "generate_hybrid_report"):
        report = monitor.generate_hybrid_report()
    else:
        report = monitor.generate_report()

    quality_metrics: dict = {}
    try:
        quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    except Exception:
        pass

    hallucination_data: dict = {}
    try:
        hallucination_data = monitor.hallucination_detector.get_hallucination_rate()
    except Exception:
        pass

    token_stats: dict = {}
    try:
        token_stats = monitor.token_tracker.get_usage_stats()
    except Exception:
        pass

    tool_selection_stats: dict = {}
    try:
        tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    except Exception:
        pass

    coordination_stats: dict = {}
    try:
        coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
    except Exception:
        pass

    workflow_stats: dict = {}
    try:
        workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    except Exception:
        pass

    retry_metrics: dict = {}
    try:
        retry_metrics = monitor.retry_tracker.get_retry_metrics()
    except Exception:
        pass

    latency_stats: dict = {}
    try:
        latency_stats = monitor.latency_tracker.get_latency_stats()
    except Exception:
        pass

    adv_metrics: dict = {}
    try:
        adv_metrics = report.advanced_metrics_summary if hasattr(report, "advanced_metrics_summary") else {}
    except Exception:
        pass

    # Scalar values
    accuracy_metrics: dict = {}
    try:
        accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
    except Exception:
        pass

    tcr_data = (report.accuracy_metrics.get("tcr", {}) if hasattr(report, "accuracy_metrics") else {}) or {}
    tcr = float(tcr_data.get("tcr") or 0)
    success_rate = float(tcr_data.get("success_rate") or 0)
    acc = float(accuracy_metrics.get("overall_accuracy") or 0)

    latency_data = (report.efficiency_metrics.get("latency", {}) if hasattr(report, "efficiency_metrics") else {}) or {}
    latency = float(latency_data.get("mean") or 0)

    total_tasks = 0
    try:
        total_tasks = len(monitor.tcr_tracker.tasks)
    except Exception:
        pass

    hall_rate = float(hallucination_data.get("overall_rate") or 0)

    # Harness groups
    harness_groups: dict = getattr(report, "harness_groups", None) or {}
    if not harness_groups and hasattr(report, "extra_metrics"):
        harness_groups = (report.extra_metrics or {}).get("harness_groups") or {}

    # Agentic flag
    has_agentic = bool(
        tool_selection_stats or coordination_stats or workflow_stats
    )

    # LLM Judge — 두 가지 소스를 시도한다:
    # 1) monitor.llm_judge (enable_llm_judge=True 로 생성된 영속 인스턴스)
    # 2) monitor.tasks 개별 레코드 (per-call LLMJudgeConfig 패턴 — lazy-init 후 제거됨)
    llm_judge_data = None
    try:
        _judge = getattr(monitor, "llm_judge", None)
        if _judge:
            _summary = _judge.get_summary()
            if _summary.get("count", 0) > 0:
                # get_summary() 반환값은 avg_scores 중첩 형태 → 보고서가 기대하는 flat 형태로 변환
                _avs = _summary.get("avg_scores") or {}
                llm_judge_data = {
                    "count":                   _summary["count"],
                    "avg_overall":             _avs.get("overall"),
                    "avg_completeness":        _avs.get("completeness"),
                    "avg_relevance":           _avs.get("relevance"),
                    "avg_factual_consistency": _avs.get("factual_consistency"),
                    "avg_faithfulness":        _avs.get("faithfulness") or None,
                    "avg_criteria_overall":    _avs.get("criteria_overall"),
                    "total_cost_usd":          _summary.get("total_cost_usd", 0.0),
                    "model":                   getattr(_judge, "model", "—") or "—",
                }
    except Exception:
        pass

    # Fallback: per-task records (LLMJudgeConfig per-call 패턴)
    if llm_judge_data is None:
        try:
            _tasks = getattr(monitor, "tasks", []) or []
            _judged = [
                t.llm_judge for t in _tasks
                if getattr(t, "llm_judge", None)
                and not t.llm_judge.get("skipped")
                and t.llm_judge.get("scores")
            ]
            if _judged:
                _dims = ["completeness", "relevance", "factual_consistency", "overall",
                         "toxicity", "bias", "faithfulness", "criteria_overall"]
                _avs2: dict = {}
                for _d in _dims:
                    _vs = [
                        r["scores"][_d] for r in _judged
                        if r.get("scores") and _d in r["scores"]
                        and isinstance(r["scores"][_d], (int, float))
                    ]
                    if _vs:
                        _avs2[_d] = round(sum(_vs) / len(_vs), 3)
                _model2 = next((r.get("model") for r in _judged if r.get("model")), "—")
                llm_judge_data = {
                    "count":                   len(_judged),
                    "avg_overall":             _avs2.get("overall"),
                    "avg_completeness":        _avs2.get("completeness"),
                    "avg_relevance":           _avs2.get("relevance"),
                    "avg_factual_consistency": _avs2.get("factual_consistency"),
                    "avg_faithfulness":        _avs2.get("faithfulness") or None,
                    "avg_criteria_overall":    _avs2.get("criteria_overall"),
                    "total_cost_usd":          round(sum(r.get("cost_usd", 0.0) for r in _judged), 6),
                    "model":                   _model2 or "—",
                }
        except Exception:
            pass

    # RAG / advanced flags
    has_advanced = bool(adv_metrics)
    rag_metrics: dict = {}
    try:
        rag_metrics = monitor.rag_metrics or {}
    except Exception:
        pass
    has_rag = any(len(v) > 0 for v in rag_metrics.values())
    conversation_sessions: list = []
    try:
        conversation_sessions = list(monitor.conversation_sessions) or []
    except Exception:
        pass
    has_conversation = bool(conversation_sessions)

    # Gate RCA 진단 — baseline 없이도 절대 임계값 기반으로 동작(rca.diagnose() 참고).
    # diagnosis dict를 한 번 계산해 Recommendations(구체 조치)와 진단 섹션이 공유한다.
    current_dict: dict[str, Any] = {}
    try:
        current_dict = report.to_dict()
    except Exception:
        pass
    try:
        recommendation_log_path = monitor.output_dir / "recommendation_outcomes.jsonl"
    except Exception:
        recommendation_log_path = None
    _experiments_log = Path(".aoo/experiments.jsonl")
    experiments_log_path = _experiments_log if _experiments_log.is_file() else None

    diagnosis_html = ""
    diag_result: dict[str, Any] | None = None
    try:
        diagnosis_html = _build_diagnosis(
            current_dict, baseline, recommendation_log_path=recommendation_log_path,
        )
    except Exception:
        pass
    try:
        # 컴포넌트 shortfall은 항상 절대 상태 기준(baseline 유무와 무관하게 "지금 이 Gate를
        # 끄는 컴포넌트가 무엇인가"). 진단 섹션은 별도로 baseline 회귀 모드를 쓴다.
        from agent_evaluator.rca import diagnose as _diagnose
        diag_result = _diagnose(current_dict, None)
    except Exception:
        pass

    _tasks_list = list(getattr(monitor, "tasks", []) or [])
    # report.to_dict() (monitor path) carries no tasks[] / evaluators.security /
    # pricing — graft them so the insight layer (narrative / security_findings /
    # cost_economics / …) works from the live monitor exactly as from a saved file.
    _ins_input: dict[str, Any] = dict(current_dict) if isinstance(current_dict, dict) else {}
    if not _ins_input.get("tasks"):
        _ins_input["tasks"] = _review_dict_tasks(_tasks_list)
    try:
        _sec = monitor._get_security_evaluator_data()
        if _sec:
            _ins_input.setdefault("evaluators", {})["security"] = _sec
    except Exception:
        pass
    if not _ins_input.get("pricing"):
        _pricing = getattr(getattr(monitor, "token_tracker", None), "pricing", None) \
            or getattr(monitor, "pricing", None)
        if isinstance(_pricing, dict) and _pricing:
            _ins_input["pricing"] = _pricing
    if not _ins_input.get("conversation_sessions"):
        try:
            _cs = getattr(monitor, "conversation_sessions", None) or []
            _ins_input["conversation_sessions"] = [
                s.to_dict() if hasattr(s, "to_dict") else s for s in _cs
            ]
        except Exception:
            pass
    _narrative = ""
    _insights_obj: dict[str, Any] = {}
    try:
        from agent_evaluator.reporting.insights import build_insights as _build_insights
        try:
            from agent_evaluator.utils.targets import load_targets
            _targets = load_targets()      # .aoo/targets.json (SPEC-041 P43)
        except Exception:
            _targets = None
        _insights_obj = _build_insights(
            _ins_input, baseline, recommendation_log_path=recommendation_log_path,
            experiments_log_path=experiments_log_path, cohort=cohort, targets=_targets,
        ) or {}
        _narrative = _insights_obj.get("narrative", "")
    except Exception:
        pass
    _res_dir = getattr(monitor, "output_dir", None)
    _cur_file = None
    failure_cases_html = ""
    try:
        failure_cases_html = _build_failure_cases(
            _tasks_list, total_tasks=total_tasks, baseline=baseline,
        )
    except Exception:
        pass

    ci_data: dict[str, Any] = {}
    try:
        ci_data = _metric_ci_data(_tasks_list)
    except Exception:
        pass

    operational_html = ""
    try:
        _adata = None
        if getattr(monitor, "enable_anomaly_detection", False):
            from agent_evaluator.anomaly import AnomalyDetector
            _det = AnomalyDetector(
                baseline_window=getattr(monitor, "_anomaly_baseline_window", 100),
                detection_window=getattr(monitor, "_anomaly_detection_window", 20),
            )
            _adata = {
                "anomalies": [a.to_dict() for a in _det.scan(monitor)],
                "baseline_window": getattr(monitor, "_anomaly_baseline_window", 100),
                "detection_window": getattr(monitor, "_anomaly_detection_window", 20),
            }
        operational_html = _build_operational_signals(_adata)
    except Exception:
        pass

    # Build HTML
    parts = [
        _build_css(),
        _build_header(total_tasks, tcr, acc, latency, harness_groups, ci_data),
        _build_narrative_banner(_narrative),
        _build_narrative_audit_note(_insights_obj.get("narrative_audit")),
        _build_freshness_banner(_insights_obj.get("freshness")),
        _build_executive_summary(harness_groups, diag_result, tcr, acc, total_tasks, ci_data, _insights_obj.get("verdict")),
        _build_readiness(_insights_obj.get("readiness")),
        _build_briefs(_insights_obj.get("briefs")),
        _build_scorecard(harness_groups),
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, harness_groups.get("A", {}), quality_metrics),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {}), hallucination_data, llm_judge_data),
        _build_gate_d(latency_stats, token_stats, harness_groups.get("D", {}), _tasks_list, _ins_input),
        _build_gate_e_from_monitor(monitor, harness_groups.get("E", {})),
        _build_gate_f(coordination_stats, workflow_stats, has_agentic, harness_groups.get("F", {})),
        _build_gate_g(quality_metrics, llm_judge_data, harness_groups.get("G", {})),
        _build_advanced_section(adv_metrics, rag_metrics, has_advanced, has_rag, has_conversation, conversation_sessions),
        operational_html,
        _build_slice_analysis(_tasks_list, baseline),
        _build_metadata_slices(_insights_obj.get("metadata_slices")),
        _build_sample_guidance(_insights_obj.get("sample_guidance")),
        _build_metric_signal(_insights_obj.get("metric_signal")),
        _build_evaluator_reliability(_tasks_list, current_dict),
        _build_review_queue(_tasks_list, current_dict, baseline),
        _build_security_findings(_ins_input),
        _build_nondeterminism(_tasks_list),
        _build_calibration(_insights_obj.get("calibration")),
        _build_efficiency_opportunities(_insights_obj.get("efficiency_opportunities")),
        _build_eval_set_quality(_tasks_list, baseline, harness_groups,
                                _insights_obj.get("eval_set_quality")),
        failure_cases_html,
        _build_failure_explanations(_insights_obj.get("failure_explanations")),
        _build_recommendations(harness_groups, tcr, acc, hall_rate, latency, quality_metrics,
                               diagnosis=diag_result,
                               recommendation_log_path=recommendation_log_path,
                               baseline=baseline, current=current_dict,
                               insights_recs=_insights_obj.get("recommendations")),
        _build_multiagent(_insights_obj.get("multiagent")),
        _build_conversation(_insights_obj.get("conversation")),
        _build_experiments(_insights_obj.get("experiments")),
        _build_cohort_comparison(_insights_obj.get("cohort_comparison")),
        _build_trace_diffs(_insights_obj.get("trace_diffs")),
        _build_insight_changes(_insights_obj.get("insight_changes")),
        _build_regression_attribution(_insights_obj.get("regression_attribution")),
        _build_change_attribution(_insights_obj.get("change_attribution")),
        _build_reproducibility_manifest(_insights_obj.get("reproducibility_manifest")),
        diagnosis_html,
        _build_history_trend(_res_dir, _cur_file),
        _build_change_ledger(_res_dir),
        _build_threshold_sensitivity(_insights_obj.get("threshold_sensitivity")),
        _build_conclusion(total_tasks, tcr, acc, hall_rate, harness_groups, ci_data),
        '</div></body></html>',
    ]
    _toc = _build_toc(''.join(x for x in parts if isinstance(x, str)))
    if _toc:
        parts.insert(2, _toc)
    return ''.join(parts)


# ---------------------------------------------------------------------------
# generate_html_from_result_file(rf)  — Dashboard export router용
# ---------------------------------------------------------------------------

def generate_html_from_result_file(rf, baseline: dict[str, Any] | None = None,
                                   cohort: list[dict[str, Any]] | None = None) -> str:
    """ResultFile 객체에서 Harness Gate A–G 중심 HTML 리포트를 생성한다.

    Args:
        rf: loader.ResultFile 인스턴스
        baseline: (선택) 비교 기준 결과 dict — ``generate_comprehensive_html_report()``의
            동일 인자와 같은 규칙(Gate RCA 진단 섹션의 감지 모드 전환).

    Returns:
        Self-contained HTML string.
    """
    # --- Scalar helpers ---
    def _f(v: Any, default: float = 0.0) -> float:
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    # Basic metrics
    tcr_data = rf.accuracy_metrics.get("tcr", {}) or {}
    acc_data = rf.accuracy_metrics.get("accuracy_scores", {}) or {}
    hall_data = rf.accuracy_metrics.get("hallucination", {}) or {}
    lat_data = rf.efficiency_metrics.get("latency", {}) or {}
    tok_data = rf.efficiency_metrics.get("tokens", {}) or {}

    tcr = _f(tcr_data.get("tcr"))
    success_rate = _f(tcr_data.get("success_rate"))
    acc = _f(acc_data.get("overall_accuracy"))
    latency = _f(lat_data.get("mean"))
    hall_rate = _f(hall_data.get("overall_rate"))
    total_tasks = rf.total_tasks

    harness_groups: dict = getattr(rf, "harness_groups", None) or {}
    has_agentic = getattr(rf, "has_agentic", False)

    # accuracy_metrics dict for task_type breakdown
    accuracy_metrics: dict = acc_data

    # hallucination_data
    hallucination_data: dict = hall_data

    # quality_metrics from quality_detail
    quality_metrics: dict = {}
    if getattr(rf, "has_quality_detail", False):
        qd = rf.quality_detail
        try:
            quality_metrics = {
                "total_evaluated": len(getattr(qd, "evaluations", [])),
                "avg_total_score": _f(getattr(qd, "avg_score", 0)),
                "dimension_scores": dict(getattr(qd, "dimension_summary", {})),
            }
        except Exception:
            pass

    # retry metrics
    retry_metrics: dict = {}
    if has_agentic:
        ag = rf.agentic
        retry = ag.get("retry_summary") if isinstance(ag, dict) else getattr(ag, "retry_summary", None)
        if isinstance(retry, dict):
            retry_metrics = retry

    # latency stats
    latency_stats: dict = lat_data

    # token stats
    token_stats: dict = tok_data

    # tool_selection_stats
    tool_selection_stats: dict = {}
    if has_agentic:
        ag = rf.agentic
        tool_eff = ag.get("tool_efficiency") if isinstance(ag, dict) else getattr(ag, "tool_efficiency", None)
        tool_sel = ag.get("tool_selection_summary") if isinstance(ag, dict) else getattr(ag, "tool_selection_summary", None)
        if isinstance(tool_eff, dict):
            tool_selection_stats.update(tool_eff)
        if isinstance(tool_sel, dict):
            tool_selection_stats.update(tool_sel)

    # coordination / workflow
    coordination_stats: dict = {}
    workflow_stats: dict = {}
    if has_agentic:
        ag = rf.agentic
        coord = ag.get("coordination_summary") if isinstance(ag, dict) else getattr(ag, "coordination_summary", None)
        workflow = ag.get("workflow_summary") if isinstance(ag, dict) else getattr(ag, "workflow_summary", None)
        if isinstance(coord, dict):
            coordination_stats = coord
        if isinstance(workflow, dict):
            workflow_stats = workflow

    # LLM Judge
    llm_judge_data = None
    if getattr(rf, "has_llm_judge", False):
        llm_judge_data = rf.llm_judge

    # Advanced
    has_advanced = getattr(rf, "has_advanced", False)
    adv_metrics: dict = {}
    if has_advanced:
        try:
            adv_metrics = rf.advanced.summary or {}
        except Exception:
            pass

    has_rag = getattr(rf, "has_rag", False)
    rag_metrics: dict = rf.rag_metrics if has_rag else {}

    has_conversation = getattr(rf, "has_conversation", False)
    conversation_sessions: list = rf.conversation_sessions if has_conversation else []

    # Gate RCA 진단 — baseline 없이도 절대 임계값 기반으로 동작(rca.diagnose() 참고).
    try:
        recommendation_log_path = rf.path.parent / "recommendation_outcomes.jsonl"
    except Exception:
        recommendation_log_path = None
    _experiments_log = Path(".aoo/experiments.jsonl")
    experiments_log_path = _experiments_log if _experiments_log.is_file() else None
    current_dict = rf.raw or {}

    diagnosis_html = ""
    diag_result: dict[str, Any] | None = None
    try:
        diagnosis_html = _build_diagnosis(
            current_dict, baseline, recommendation_log_path=recommendation_log_path,
        )
    except Exception:
        pass
    try:
        # 컴포넌트 shortfall은 항상 절대 상태 기준(baseline 유무와 무관하게 "지금 이 Gate를
        # 끄는 컴포넌트가 무엇인가"). 진단 섹션은 별도로 baseline 회귀 모드를 쓴다.
        from agent_evaluator.rca import diagnose as _diagnose
        diag_result = _diagnose(current_dict, None)
    except Exception:
        pass

    _tasks_list = list(getattr(rf, "tasks", []) or [])
    _cur_file = getattr(rf, "path", None)
    _res_dir = str(Path(_cur_file).parent) if _cur_file else None
    # rf.raw already carries tasks[] + evaluators.security; fall back defensively.
    _ins_input: dict[str, Any] = dict(current_dict) if isinstance(current_dict, dict) else {}
    if not _ins_input.get("tasks"):
        _ins_input["tasks"] = _review_dict_tasks(_tasks_list)
    _narrative = ""
    _insights_obj: dict[str, Any] = {}
    try:
        from agent_evaluator.reporting.insights import build_insights as _build_insights
        try:
            from agent_evaluator.utils.targets import load_targets
            _targets = load_targets()      # .aoo/targets.json (SPEC-041 P43)
        except Exception:
            _targets = None
        _insights_obj = _build_insights(
            _ins_input, baseline, recommendation_log_path=recommendation_log_path,
            experiments_log_path=experiments_log_path, cohort=cohort, targets=_targets,
        ) or {}
        _narrative = _insights_obj.get("narrative", "")
    except Exception:
        pass
    failure_cases_html = ""
    try:
        failure_cases_html = _build_failure_cases(
            _tasks_list, total_tasks=total_tasks, baseline=baseline,
        )
    except Exception:
        pass

    ci_data: dict[str, Any] = {}
    try:
        ci_data = _metric_ci_data(_tasks_list)
    except Exception:
        pass

    operational_html = ""
    try:
        operational_html = _build_operational_signals((rf.raw or {}).get("anomaly_data"))
    except Exception:
        pass

    # Build HTML
    parts = [
        _build_css(),
        _build_header(total_tasks, tcr, acc, latency, harness_groups, ci_data),
        _build_narrative_banner(_narrative),
        _build_narrative_audit_note(_insights_obj.get("narrative_audit")),
        _build_freshness_banner(_insights_obj.get("freshness")),
        _build_executive_summary(harness_groups, diag_result, tcr, acc, total_tasks, ci_data, _insights_obj.get("verdict")),
        _build_readiness(_insights_obj.get("readiness")),
        _build_briefs(_insights_obj.get("briefs")),
        _build_scorecard(harness_groups),
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, harness_groups.get("A", {}), quality_metrics),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {}), hallucination_data, llm_judge_data),
        _build_gate_d(latency_stats, token_stats, harness_groups.get("D", {}), _tasks_list, _ins_input),
        _build_gate_e_from_rf(rf, harness_groups.get("E", {})),
        _build_gate_f(coordination_stats, workflow_stats, has_agentic, harness_groups.get("F", {})),
        _build_gate_g(quality_metrics, llm_judge_data, harness_groups.get("G", {})),
        _build_advanced_section(adv_metrics, rag_metrics, has_advanced, has_rag, has_conversation, conversation_sessions),
        operational_html,
        _build_slice_analysis(_tasks_list, baseline),
        _build_metadata_slices(_insights_obj.get("metadata_slices")),
        _build_sample_guidance(_insights_obj.get("sample_guidance")),
        _build_metric_signal(_insights_obj.get("metric_signal")),
        _build_evaluator_reliability(_tasks_list, current_dict),
        _build_review_queue(_tasks_list, current_dict, baseline),
        _build_security_findings(_ins_input),
        _build_nondeterminism(_tasks_list),
        _build_calibration(_insights_obj.get("calibration")),
        _build_efficiency_opportunities(_insights_obj.get("efficiency_opportunities")),
        _build_eval_set_quality(_tasks_list, baseline, harness_groups,
                                _insights_obj.get("eval_set_quality")),
        failure_cases_html,
        _build_failure_explanations(_insights_obj.get("failure_explanations")),
        _build_recommendations(harness_groups, tcr, acc, hall_rate, latency, quality_metrics,
                               diagnosis=diag_result,
                               recommendation_log_path=recommendation_log_path,
                               baseline=baseline, current=current_dict,
                               insights_recs=_insights_obj.get("recommendations")),
        _build_multiagent(_insights_obj.get("multiagent")),
        _build_conversation(_insights_obj.get("conversation")),
        _build_experiments(_insights_obj.get("experiments")),
        _build_cohort_comparison(_insights_obj.get("cohort_comparison")),
        _build_trace_diffs(_insights_obj.get("trace_diffs")),
        _build_insight_changes(_insights_obj.get("insight_changes")),
        _build_regression_attribution(_insights_obj.get("regression_attribution")),
        _build_change_attribution(_insights_obj.get("change_attribution")),
        _build_reproducibility_manifest(_insights_obj.get("reproducibility_manifest")),
        diagnosis_html,
        _build_history_trend(_res_dir, _cur_file),
        _build_change_ledger(_res_dir),
        _build_threshold_sensitivity(_insights_obj.get("threshold_sensitivity")),
        _build_conclusion(total_tasks, tcr, acc, hall_rate, harness_groups, ci_data),
        '</div></body></html>',
    ]
    _toc = _build_toc(''.join(x for x in parts if isinstance(x, str)))
    if _toc:
        parts.insert(2, _toc)
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Comparison report (SPEC-025 REQ-2/5 — group_by / pairwise dashboard export)
# ---------------------------------------------------------------------------

def _esc(v: Any) -> str:
    """HTML 특수문자 이스케이프 — 비교 리포트는 task question/reasoning 등 사용자
    생성 텍스트를 그대로 담으므로 반드시 이스케이프한다."""
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def generate_comparison_html_report(compare_result: dict[str, Any]) -> str:
    """``compare_results()``(``serve/routers/data.py``)의 반환 dict를 그대로 받아
    self-contained HTML 비교 리포트로 렌더링한다.

    새 비교 로직을 만들지 않는다 — ``files``/``delta``/``detailed``/
    ``regression_tasks``/``improvement_tasks``/``pairwise`` 키를 이미 계산된
    그대로 표시만 한다(``group_by``/``pairwise`` 자체의 계산은 API 쪽 책임).

    Args:
        compare_result: ``compare_results()``가 반환한 dict.

    Returns:
        Self-contained HTML string (외부 CDN 의존성 없음, `_build_css()` 재사용).
    """
    files = compare_result.get("files") or []
    delta = compare_result.get("delta") or []
    detailed = compare_result.get("detailed")
    regression_tasks = compare_result.get("regression_tasks") or []
    improvement_tasks = compare_result.get("improvement_tasks") or []
    pairwise = compare_result.get("pairwise")

    found_files = [f for f in files if f.get("found")]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _name(f: dict[str, Any]) -> str:
        return _esc(f.get("name") or f.get("file_id") or "?")

    css = _build_css().replace(
        "<title>Agent Evaluator — Harness Gate Report</title>",
        "<title>Agent Evaluator — Comparison Report</title>",
    )

    names = ", ".join(_name(f) for f in found_files) or "(no files found)"
    header = f'''
<div class="rpt-header">
  <h1>📂 Result Comparison Report</h1>
  <div class="sub">{names}</div>
  <div class="meta">
    <span>📊 {len(found_files)} file(s) compared</span>
    <span>🕐 Generated {now_str}</span>
  </div>
</div>
'''

    if not found_files:
        return css + header + '<div class="not-tested">No files found for the given ids/group_by.</div></div></body></html>'

    _metric_rows = [
        ("Total Tasks", "total_tasks", "{:.0f}"),
        ("TCR", "tcr", "{:.1f}%"),
        ("Accuracy", "accuracy", "{:.1f}%"),
        ("Avg Latency", "avg_latency", "{:.3f}s"),
        ("Total Cost", "total_cost", "${:.6f}"),
    ]
    thead = "<tr><th>Metric</th>" + "".join(f"<th>{_name(f)}</th>" for f in found_files) + "</tr>"
    tbody = "".join(
        f"<tr><td>{label}</td>" + "".join(f"<td>{fmt.format(f.get(key) or 0)}</td>" for f in found_files) + "</tr>"
        for label, key, fmt in _metric_rows
    )
    metric_section = f'''
<div class="gate-section">
  <h2>📊 Metric Comparison</h2>
  <table class="mtable"><thead>{thead}</thead><tbody>{tbody}</tbody></table>
</div>
'''

    delta_section = ""
    if delta:
        delta_rows = "".join(
            f"<tr><td>vs {_esc(d.get('vs'))}</td>"
            f"<td>{d.get('tcr_delta', 0):+.2f}%</td>"
            f"<td>{d.get('accuracy_delta', 0):+.2f}%</td>"
            f"<td>{d.get('latency_delta', 0):+.3f}s</td></tr>"
            for d in delta
        )
        delta_section = f'''
<div class="gate-section">
  <h2>&Delta; Delta <span style="font-size:12px;font-weight:400;color:#6b7280">(first file as baseline)</span></h2>
  <table class="mtable"><thead><tr><th>Compared to</th><th>TCR &Delta;</th><th>Accuracy &Delta;</th><th>Latency &Delta;</th></tr></thead>
  <tbody>{delta_rows}</tbody></table>
</div>
'''

    detail_section = ""
    if detailed:
        def _task_rows(tasks: list) -> str:
            if not tasks:
                return '<tr><td colspan="4" style="text-align:center;color:#9ca3af">None</td></tr>'
            return "".join(
                f"<tr><td>{_esc(t.get('task_id'))}</td><td>{_esc(t.get('task_type', ''))}</td>"
                f"<td>{t.get('accuracy_delta', 0):+.3f}</td><td>{t.get('latency_delta', 0):+.3f}s</td></tr>"
                for t in tasks
            )
        detail_section = f'''
<div class="gate-section">
  <h2>🔍 Per-Task Detail</h2>
  <div class="kpis">
    <div class="kpi"><div class="kpi-lbl">Common Tasks</div><div class="kpi-val">{detailed.get("common_task_count", 0)}</div></div>
    <div class="kpi"><div class="kpi-lbl">Only in First</div><div class="kpi-val">{detailed.get("only_in_first", 0)}</div></div>
    <div class="kpi"><div class="kpi-lbl">Only in Second</div><div class="kpi-val">{detailed.get("only_in_second", 0)}</div></div>
  </div>
  <h3><span class="badge badge-fail">Regressions ({len(regression_tasks)})</span></h3>
  <table class="mtable"><thead><tr><th>Task ID</th><th>Type</th><th>Accuracy &Delta;</th><th>Latency &Delta;</th></tr></thead>
  <tbody>{_task_rows(regression_tasks)}</tbody></table>
  <h3><span class="badge badge-ok">Improvements ({len(improvement_tasks)})</span></h3>
  <table class="mtable"><thead><tr><th>Task ID</th><th>Type</th><th>Accuracy &Delta;</th><th>Latency &Delta;</th></tr></thead>
  <tbody>{_task_rows(improvement_tasks)}</tbody></table>
</div>
'''

    pairwise_section = ""
    if pairwise:
        win_rate = pairwise.get("win_rate")
        win_rate_str = f"{win_rate * 100:.1f}%" if win_rate is not None else "N/A"
        per_task_rows = "".join(
            f"<tr><td>{_esc(pt.get('task_id'))}</td><td>{_esc(pt.get('winner'))}</td>"
            f"<td>{_esc(pt.get('reasoning', ''))}</td></tr>"
            for pt in (pairwise.get("per_task") or [])
        ) or '<tr><td colspan="3" style="text-align:center;color:#9ca3af">None</td></tr>'
        judged_count = pairwise.get("judged_count", len(pairwise.get("per_task") or []))
        pairwise_section = f'''
<div class="gate-section">
  <h2>⚖️ Pairwise LLM Judge</h2>
  <div class="kpis">
    <div class="kpi"><div class="kpi-lbl">Wins A</div><div class="kpi-val">{pairwise.get("wins_a", 0)}</div></div>
    <div class="kpi"><div class="kpi-lbl">Ties</div><div class="kpi-val">{pairwise.get("ties", 0)}</div></div>
    <div class="kpi"><div class="kpi-lbl">Wins B</div><div class="kpi-val">{pairwise.get("wins_b", 0)}</div></div>
    <div class="kpi"><div class="kpi-lbl">Win Rate (A)</div><div class="kpi-val">{win_rate_str}</div></div>
  </div>
  <p style="font-size:12px;color:#6b7280;margin:6px 0 10px">{judged_count} common task(s) judged</p>
  <table class="mtable"><thead><tr><th>Task ID</th><th>Winner</th><th>Reasoning</th></tr></thead>
  <tbody>{per_task_rows}</tbody></table>
</div>
'''

    footer = f'<div class="footer">Generated by Agent Evaluator · {now_str}</div></div></body></html>'

    return "".join([
        css, header, metric_section, delta_section, detail_section, pairwise_section, footer,
    ])
