"""
Comprehensive HTML Report Generator for Agent Evaluator
Harness Gate A–G 중심 구조 (v0.8.2+)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional


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

    for i, line in enumerate(lines):
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

_GATE_COLORS: Dict[str, str] = {
    "A": "#10b981",  # emerald
    "B": "#3b82f6",  # blue
    "C": "#f59e0b",  # amber
    "D": "#0ea5e9",  # sky
    "E": "#ef4444",  # red
    "F": "#8b5cf6",  # purple
    "G": "#06b6d4",  # cyan
}

_GATE_NAMES: Dict[str, str] = {
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

/* Inactive banner (Harness Config 미활성) */
.inactive-banner{background:#f9fafb;border:1px dashed #d1d5db;border-radius:8px;padding:12px 16px;font-size:12px;color:#9ca3af;margin:8px 0}
/* Not-tested banner (데이터 미수집) */
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

def _not_tested(reason: str = "") -> str:
    """데이터가 수집되지 않은 섹션에 표시하는 '테스트되지 않음' 배너."""
    msg = reason or "This item has not been tested."
    return f'<div class="not-tested">🔍 <strong>Not Measured</strong>&nbsp;{msg}</div>'


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def _build_scorecard(harness_groups: Dict[str, Any]) -> str:
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

def _bd_row(label: str, raw_str: Optional[str], contrib: Optional[float],
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


def _build_score_breakdown(gate_key: str, harness_group: Dict) -> str:
    """Build a score computation breakdown widget for a Gate detail section."""
    if not harness_group:
        return ""
    score = harness_group.get("score")
    if score is None:
        return ""
    details = harness_group.get("details") or {}
    color = _GATE_COLORS.get(gate_key, "#6b7280")

    rows: list = []
    formula_parts: list = []
    included_vals: list = []

    def _add(label: str, raw_str: Optional[str], contrib: Optional[float],
              formula_label: str = "", always: bool = False, note: str = "") -> None:
        formula_parts.append(formula_label or label)
        rows.append(_bd_row(label, raw_str, contrib, always=always, note=note))
        if contrib is not None:
            included_vals.append(contrib)

    def _fmt_ratio(v: Any) -> Optional[str]:
        if v is None:
            return None
        try:
            return f"{float(v):.3f}"
        except (TypeError, ValueError):
            return None

    def _fmt_pct(v: Any, scale: float = 1.0) -> Optional[str]:
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
                 formula_label="avg_accuracy")
        else:
            _add("Accuracy Score (AccuracyEvaluator)", None, None,
                 formula_label="avg_accuracy",
                 note="No accuracy evaluations recorded")
        formula_str = "avg( TCR/100, avg_IFR, avg_goal_alignment, avg_plan_coherence, avg_subtask_completion, avg_context_retention, avg_knowledge_retention, avg_accuracy )"

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
        hall_c = details.get("hallucination_rate")
        if hall_c is not None:
            c_hall_c = max(0.0, 1.0 - float(hall_c))
            _add("Hallucination Faithfulness (1 − rate)", _fmt_pct(hall_c, scale=100.0), c_hall_c,
                 formula_label="1−hallucination_rate")
        else:
            _add("Hallucination Faithfulness (1 − rate)", None, None,
                 formula_label="1−hallucination_rate",
                 note="Requires enable_hallucination_detection=True")
        formula_str = "avg( TCR/100, 1−sla_breach_rate, avg_fault_tolerance, avg_reproducibility, avg_degradation, avg_retry_consistency, avg_idempotency, 1−hallucination_rate )"

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
                 note="No tool calls / EfficiencyConfig not set")
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
        # Threat-free rate: stored as threat_count but contribution = 1-count/n
        # When count=0 contribution=1.0; otherwise show note
        c_threat = 1.0 if threat_count == 0 else None
        note_threat = "" if threat_count == 0 else f"{threat_count} threats detected — contribution = 1 − threats/total"
        _add("Threat-Free Rate (1 − threats/total)",
             f"{threat_count} threats", c_threat,
             formula_label="1−threat_rate", always=True,
             note=note_threat)
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
        tr = details.get("avg_threat_response")
        _add("Threat Response Score", _fmt_ratio(tr), tr,
             formula_label="avg_threat_response")
        formula_str = "avg( 1−threat_rate, [1−cvss/10], [compliance], [1−priv_esc_rate], [1−chain_rate], [leakage_defense], [injection_defense], [threat_response] )"

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
    if len(included_vals) == 1:
        comp_expr = f"{included_vals[0]:.3f}"
    else:
        terms = " + ".join(f"{v:.3f}" for v in included_vals)
        comp_expr = f"( {terms} ) ÷ {len(included_vals)}"
    result_html = (
        f'<div class="bd-result">'
        f'Gate {gate_key} Score&nbsp;=&nbsp;{comp_expr}&nbsp;=&nbsp;'
        f'<strong style="color:{score_col}">{score_pct:.1f}%</strong>'
        f'&nbsp;<span style="font-size:11px;color:#6b7280">({len(included_vals)} component(s) averaged)</span>'
        f'</div>'
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
                  accuracy_metrics: Dict, harness_a: Dict,
                  quality_metrics: Dict = {}) -> str:
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
            f'<h3>Response Quality (5 Dimensions)</h3>'
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

def _build_gate_b(tool_selection_stats: Dict, has_agentic: bool,
                  harness_b: Dict) -> str:
    color = _GATE_COLORS["B"]
    gate_status = (harness_b.get("gate") or harness_b.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    tool_html = ""
    if not has_agentic:
        tool_html = (
            f'<h3>Tool Usage Analysis</h3>'
            + _not_tested("No agentic tool usage data — "
                          "run tasks with <code>task_type=\"tool_use\"</code> to measure.")
        )
    elif not tool_selection_stats:
        tool_html = (
            f'<h3>Tool Usage Analysis</h3>'
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

def _build_gate_c(retry_metrics: Dict, harness_c: Dict, hallucination_data: Dict = {}) -> str:
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
            f'<h3>Retry / Recovery</h3>'
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

    # Hallucination Detection
    hall_html = ""
    _hall_measured = bool(hallucination_data) and hallucination_data.get("total_evaluated", 0) > 0
    if not _hall_measured:
        hall_html = (
            f'<h3>Hallucination Detection</h3>'
            + _not_tested("Hallucination detection is not enabled — "
                          "measure it with <code>enable_hallucination_detection=True</code>.")
        )
    else:
        hall_rate = float(hallucination_data.get("overall_rate") or 0)
        hall_pct = hall_rate  # overall_rate is already a percentage (0–100 scale)
        hall_col = _score_color(100 - hall_pct)
        hall_html = (
            f'<h3>Hallucination Detection</h3>'
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
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate D — Performance Contract
# ---------------------------------------------------------------------------

def _build_gate_d(latency_stats: Dict, token_stats: Dict, harness_d: Dict) -> str:
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
        lat_html = f'<h3>Latency Analysis</h3>' + _not_tested("No latency data collected.")
    if latency_stats:
        lat_kpis = (
            f'<div class="kpi"><div class="kpi-lbl">Mean</div><div class="kpi-val">{_sec(latency_stats.get("mean"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P50</div><div class="kpi-val">{_sec(latency_stats.get("p50"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P90</div><div class="kpi-val">{_sec(latency_stats.get("p90"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P95</div><div class="kpi-val">{_sec(latency_stats.get("p95"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P99</div><div class="kpi-val">{_sec(latency_stats.get("p99"))}</div></div>'
        )
        lat_html = f'<h3>Latency Analysis</h3><div class="kpis">{lat_kpis}</div>'

    # Token & cost KPIs
    tok_html = ""
    if not token_stats:
        tok_html = (
            f'<h3>Tokens &amp; Cost</h3>'
            + _not_tested("No token/cost data collected — "
                          "record token counts in <code>TaskResult</code> to measure.")
        )
    if token_stats:
        def _cost(v):
            if v is None:
                return "—"
            try:
                fv = float(v)
                if fv == 0:
                    return "$0"
                s = f"{fv:.6f}" if fv < 0.01 else f"{fv:.4f}"
                return "$" + s.rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                return "—"

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

    breakdown = _build_score_breakdown("D", harness_d)

    # insufficient_data_warnings notice
    insuf = (harness_d.get("details") or {}).get("insufficient_data_warnings")
    insuf_html = ""
    if insuf:
        warn_items = "".join(f"<li style='margin:2px 0'>{w}</li>" for w in insuf)
        insuf_html = (
            f'<div class="ibox warn" style="font-size:12px;margin-bottom:12px">'
            f'<strong>Insufficient Data Warnings</strong>'
            f'<ul style="margin:6px 0 0 16px;line-height:1.8">{warn_items}</ul></div>'
        )

    return (
        f'<div class="gate-section" id="gate-d" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate D &nbsp;<span style="font-size:14px;color:#374151">Performance Contract</span>&nbsp;{badge}</h2>'
        f'{breakdown}'
        f'{insuf_html}'
        f'{lat_html}'
        f'{tok_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate E — Security Boundary
# ---------------------------------------------------------------------------

def _build_gate_e_from_monitor(monitor, harness_e: Dict) -> str:
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
            def _sec_or_empty(d: Dict, total_key: str) -> Dict:
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


def _build_gate_e_from_rf(rf, harness_e: Dict) -> str:
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


def _build_security_kpis(input_sec: Dict, output_leak: Dict, tool_auth: Dict,
                          priv_esc: Dict, chain_atk: Dict) -> str:
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
            f'<h3>Security Metrics</h3>'
            + _not_tested("Security metrics are not enabled — "
                          "measure them with <code>enable_security_metrics=True</code>.")
        )
    return f'<h3>Security Metrics</h3><div class="kpis">{"".join(kpi_parts)}</div>'


# ---------------------------------------------------------------------------
# Gate F — Multi-Agent Coordination
# ---------------------------------------------------------------------------

def _build_gate_f(coordination_stats: Dict, workflow_stats: Dict,
                  has_agentic: bool, harness_f: Dict) -> str:
    color = _GATE_COLORS["F"]
    gate_status = (harness_f.get("gate") or harness_f.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    coord_html = ""
    if not has_agentic:
        coord_html = (
            f'<h3>Coordination / Workflow</h3>'
            + _not_tested("No multi-agent execution data — "
                          "agent collaboration tasks have not run.")
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
            wf_rate = workflow_stats.get("success_rate") or workflow_stats.get("overall_success_rate")
            step_rate = workflow_stats.get("step_success_rate")
            if wf_rate is not None:
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">Workflow Success Rate</div>'
                    f'<div class="kpi-val" style="color:{_score_color(float(wf_rate)*100)}">'
                    f'{float(wf_rate)*100:.1f}%</div></div>'
                )
            if step_rate is not None:
                _step_pct = float(step_rate) if float(step_rate) > 1.0 else float(step_rate) * 100
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">Step Success Rate</div>'
                    f'<div class="kpi-val" style="color:{_score_color(_step_pct)}">'
                    f'{_step_pct:.1f}%</div></div>'
                )
        if kpi_parts:
            coord_html = f'<h3>Coordination / Workflow</h3><div class="kpis">{"".join(kpi_parts)}</div>'

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

def _build_gate_g(quality_metrics: Dict, llm_judge_data: Any,
                  harness_g: Dict) -> str:
    color = _GATE_COLORS["G"]
    gate_status = (harness_g.get("gate") or harness_g.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    # LLM Judge
    judge_html = ""
    if not llm_judge_data:
        judge_html = (
            f'<h3>LLM Judge</h3>'
            + _not_tested("LLM Judge is not enabled — "
                          "measure with <code>enable_llm_judge=True</code> or <code>LLMJudgeConfig</code>.")
        )
    if llm_judge_data:
        try:
            judged_count = 0
            overall = None
            completeness = None
            relevance = None
            factual = None
            model_name = "—"
            # Support both LLMJudgeData (dataclass) and dict summary
            if hasattr(llm_judge_data, "judged_count"):
                judged_count = llm_judge_data.judged_count
                overall = getattr(llm_judge_data, "avg_overall", None)
                completeness = getattr(llm_judge_data, "avg_completeness", None)
                relevance = getattr(llm_judge_data, "avg_relevance", None)
                factual = getattr(llm_judge_data, "avg_factual_consistency", None)
                model_name = getattr(llm_judge_data, "model", "—") or "—"
            elif isinstance(llm_judge_data, dict):
                judged_count = llm_judge_data.get("count", 0)
                overall = llm_judge_data.get("avg_overall") or llm_judge_data.get("overall")
                completeness = llm_judge_data.get("avg_completeness")
                relevance = llm_judge_data.get("avg_relevance")
                factual = llm_judge_data.get("avg_factual_consistency")
                model_name = llm_judge_data.get("model", "—") or "—"
            if judged_count == 0:
                judge_html = (
                    f'<h3>LLM Judge</h3>'
                    + _not_tested("No LLM Judge results — check the sample rate (<code>judge_sample_rate</code>).")
                )
            if judged_count > 0:
                def _judge_val(v):
                    if v is None:
                        return "—"
                    fv = float(v)
                    # Normalize to 0-10 scale for display
                    scale = 10 if fv <= 10 else 100
                    return f"{fv:.2f}/{scale}"
                ov_100 = float(overall) * 10 if overall is not None and float(overall) <= 10 else float(overall or 0)
                judge_kpis = (
                    f'<div class="kpi"><div class="kpi-lbl">Evaluated Count</div>'
                    f'<div class="kpi-val">{judged_count}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Overall Score</div>'
                    f'<div class="kpi-val" style="color:{_score_color(ov_100)}">'
                    f'{_judge_val(overall)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Completeness</div>'
                    f'<div class="kpi-val">{_judge_val(completeness)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Relevance</div>'
                    f'<div class="kpi-val">{_judge_val(relevance)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Factual Consistency</div>'
                    f'<div class="kpi-val">{_judge_val(factual)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Judge Model</div>'
                    f'<div class="kpi-val" style="font-size:11px">{model_name}</div></div>'
                )
                judge_html = f'<h3>LLM Judge (7 Dimensions)</h3><div class="kpis">{judge_kpis}</div>'
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

def _build_advanced_section(adv_metrics: Dict, rag_metrics: Dict,
                             has_advanced: bool, has_rag: bool,
                             has_conversation: bool,
                             conversation_sessions: list) -> str:
    if not has_advanced and not has_rag and not has_conversation:
        return ""

    parts = ['<div class="gate-section" id="advanced" style="border-left-color:#6366f1">'
             '<h2 style="color:#6366f1">Advanced Metrics</h2>']

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

    parts.append('</div>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _build_recommendations(harness_groups: Dict, tcr: float, acc: float,
                             hall_rate: float, latency: float,
                             quality_metrics: Dict) -> str:
    recs = []

    # Gate-based FAIL/WARN recommendations
    gate_labels = {
        "A": ("Goal Achievement", "Improve TCR, accuracy, and hallucination metrics. Add InstructionConfig / GoalAlignmentConfig to your decorator to enable detailed tracking."),
        "B": ("Behavioral Integrity", "Strengthen loop detection and scope compliance settings. Tune LoopDetectionConfig / ScopeConfig parameters."),
        "C": ("Reliability", "Review retry policies and fault-tolerance mechanisms. Enable FaultToleranceConfig to measure recovery rate."),
        "D": ("Performance Contract", "SLA threshold exceeded. Use SLAConfig to define response time limits and monitor P95 latency."),
        "E": ("Security Boundary", "Security threats detected. Enable enable_security_metrics=True and ThreatSeverityConfig."),
        "F": ("Multi-Agent Coordination", "Agent collaboration score is low. Add ConsensusConfig / ConflictResolutionConfig."),
        "G": ("Observability", "Strengthen explainability and observability metrics. Enable ExplainabilityConfig / ObservabilityConfig."),
    }
    for key in "ABCDEFG":
        gdata = harness_groups.get(key, {})
        if not isinstance(gdata, dict):
            continue
        gate_status = (gdata.get("gate") or gdata.get("status") or "").lower()
        if gate_status in ("fail", "warn"):
            label, guide = gate_labels.get(key, (f"Gate {key}", "Review configuration."))
            priority_class = "priority-high" if gate_status == "fail" else "priority-medium"
            badge_cls = "badge-fail" if gate_status == "fail" else "badge-warn"
            badge_label = "FAIL" if gate_status == "fail" else "WARN"
            recs.append(
                f'<div class="rec {priority_class}">'
                f'<strong><span class="badge {badge_cls}">{badge_label}</span> Gate {key} — {label}</strong>'
                f'<p>{guide}</p>'
                f'</div>'
            )

    # Native metric recommendations
    if tcr < 75:
        recs.append(
            '<div class="rec priority-high"><strong>TCR Improvement Needed</strong>'
            '<p>Task completion rate is below 75%. Improve agent prompts and analyze failure cases.</p></div>'
        )
    if acc < 70:
        recs.append(
            '<div class="rec priority-high"><strong>Accuracy Improvement Needed</strong>'
            '<p>Accuracy is below 70%. Review RAG context quality or ground_truth configuration.</p></div>'
        )
    if hall_rate > 0.2:
        recs.append(
            '<div class="rec priority-high"><strong>High Hallucination Risk</strong>'
            '<p>Hallucination rate exceeds 20%. Strengthen fact-verification logic.</p></div>'
        )
    if latency > 5.0:
        recs.append(
            '<div class="rec priority-medium"><strong>Response Latency Improvement Needed</strong>'
            '<p>Average response time exceeds 5s. Consider parallel processing or caching.</p></div>'
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
# Conclusion
# ---------------------------------------------------------------------------

def _build_conclusion(total_tasks: int, tcr: float, acc: float,
                       hall_rate: float, harness_groups: Dict) -> str:
    try:
        from agent_evaluator import __version__ as _ver
    except Exception:
        _ver = "0.8.2"

    pass_count = sum(
        1 for key in "ABCDEFG"
        if isinstance(harness_groups.get(key), dict)
        and (harness_groups[key].get("gate") or harness_groups[key].get("status") or "").lower() == "pass"
    )
    total_active = sum(
        1 for key in "ABCDEFG"
        if isinstance(harness_groups.get(key), dict)
        and (harness_groups[key].get("gate") or harness_groups[key].get("status") or "")
    )

    grade = "S (Outstanding)" if tcr >= 95 and acc >= 90 else \
            "A (Excellent)" if tcr >= 90 and acc >= 85 else \
            "B (Good)" if tcr >= 80 and acc >= 70 else \
            "C (Fair)" if tcr >= 70 else "D (Needs Improvement)"

    return (
        f'<div class="gate-section" id="conclusion" style="border-left-color:#374151">'
        f'<h2 style="color:#374151">Conclusion</h2>'
        f'<div class="ibox ok">'
        f'<p><strong>Grade:</strong> {grade}</p>'
        f'<p><strong>Total Tasks:</strong> {total_tasks}</p>'
        f'<p><strong>TCR:</strong> {_num(tcr, ".1f")}% | <strong>Accuracy:</strong> {_num(acc, ".1f")}% | '
        f'<strong>Hallucination Rate:</strong> {hall_rate:.1f}%</p>'
        f'{"<p><strong>Harness Gate:</strong> " + str(pass_count) + "/" + str(total_active) + " PASS</p>" if total_active > 0 else ""}'
        f'</div>'
        f'<div class="footer">'
        f'<p>Generated by <strong>Agent Evaluator v{_ver}</strong> &nbsp;|&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def _build_header(total_tasks: int, tcr: float, acc: float,
                  latency: float, harness_groups: Dict) -> str:
    try:
        from agent_evaluator import __version__ as _ver
    except Exception:
        _ver = "0.8.2"

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
        f'<span>TCR: <strong>{_num(tcr, ".1f")}%</strong></span>'
        f'<span>Accuracy: <strong>{_num(acc, ".1f")}%</strong></span>'
        f'<span>Latency: <strong>{_num(latency, ".2f")}s</strong></span>'
        f'</div>'
        f'{gate_badges_div}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# generate_comprehensive_html_report(monitor)
# ---------------------------------------------------------------------------

def generate_comprehensive_html_report(monitor) -> str:
    """Generate Harness Gate A–G 중심 종합 HTML 리포트.

    Args:
        monitor: PerformanceMonitor or HybridPerformanceMonitor instance.

    Returns:
        Self-contained HTML string.
    """
    # --- Collect report / metrics ---
    if hasattr(monitor, "generate_hybrid_report"):
        report = monitor.generate_hybrid_report()
    else:
        report = monitor.generate_report()

    quality_metrics: Dict = {}
    try:
        quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    except Exception:
        pass

    hallucination_data: Dict = {}
    try:
        hallucination_data = monitor.hallucination_detector.get_hallucination_rate()
    except Exception:
        pass

    token_stats: Dict = {}
    try:
        token_stats = monitor.token_tracker.get_usage_stats()
    except Exception:
        pass

    tool_selection_stats: Dict = {}
    try:
        tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    except Exception:
        pass

    coordination_stats: Dict = {}
    try:
        coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
    except Exception:
        pass

    workflow_stats: Dict = {}
    try:
        workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    except Exception:
        pass

    retry_metrics: Dict = {}
    try:
        retry_metrics = monitor.retry_tracker.get_retry_metrics()
    except Exception:
        pass

    latency_stats: Dict = {}
    try:
        latency_stats = monitor.latency_tracker.get_latency_stats()
    except Exception:
        pass

    adv_metrics: Dict = {}
    try:
        adv_metrics = report.advanced_metrics_summary if hasattr(report, "advanced_metrics_summary") else {}
    except Exception:
        pass

    # Scalar values
    accuracy_metrics: Dict = {}
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
    harness_groups: Dict = getattr(report, "harness_groups", None) or {}
    if not harness_groups and hasattr(report, "extra_metrics"):
        harness_groups = (report.extra_metrics or {}).get("harness_groups") or {}

    # Agentic flag
    has_agentic = bool(
        tool_selection_stats or coordination_stats or workflow_stats
    )

    # LLM Judge
    llm_judge_data = None
    try:
        _judge = getattr(monitor, "llm_judge", None)
        if _judge:
            summary = _judge.get_summary()
            if summary.get("count", 0) > 0:
                llm_judge_data = summary
    except Exception:
        pass

    # RAG / advanced flags
    has_advanced = bool(adv_metrics)
    rag_metrics: Dict = {}
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

    # Build HTML
    parts = [
        _build_css(),
        _build_header(total_tasks, tcr, acc, latency, harness_groups),
        _build_scorecard(harness_groups),
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, harness_groups.get("A", {}), quality_metrics),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {}), hallucination_data),
        _build_gate_d(latency_stats, token_stats, harness_groups.get("D", {})),
        _build_gate_e_from_monitor(monitor, harness_groups.get("E", {})),
        _build_gate_f(coordination_stats, workflow_stats, has_agentic, harness_groups.get("F", {})),
        _build_gate_g(quality_metrics, llm_judge_data, harness_groups.get("G", {})),
        _build_advanced_section(adv_metrics, rag_metrics, has_advanced, has_rag, has_conversation, conversation_sessions),
        _build_recommendations(harness_groups, tcr, acc, hall_rate, latency, quality_metrics),
        _build_conclusion(total_tasks, tcr, acc, hall_rate, harness_groups),
        '</div></body></html>',
    ]
    return ''.join(parts)


# ---------------------------------------------------------------------------
# generate_html_from_result_file(rf)  — Dashboard export router용
# ---------------------------------------------------------------------------

def generate_html_from_result_file(rf) -> str:
    """ResultFile 객체에서 Harness Gate A–G 중심 HTML 리포트를 생성한다.

    Args:
        rf: loader.ResultFile 인스턴스

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

    harness_groups: Dict = getattr(rf, "harness_groups", None) or {}
    has_agentic = getattr(rf, "has_agentic", False)

    # accuracy_metrics dict for task_type breakdown
    accuracy_metrics: Dict = acc_data

    # hallucination_data
    hallucination_data: Dict = hall_data

    # quality_metrics from quality_detail
    quality_metrics: Dict = {}
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
    retry_metrics: Dict = {}
    if has_agentic:
        ag = rf.agentic
        retry = ag.get("retry_summary") if isinstance(ag, dict) else getattr(ag, "retry_summary", None)
        if isinstance(retry, dict):
            retry_metrics = retry

    # latency stats
    latency_stats: Dict = lat_data

    # token stats
    token_stats: Dict = tok_data

    # tool_selection_stats
    tool_selection_stats: Dict = {}
    if has_agentic:
        ag = rf.agentic
        tool_eff = ag.get("tool_efficiency") if isinstance(ag, dict) else getattr(ag, "tool_efficiency", None)
        tool_sel = ag.get("tool_selection_summary") if isinstance(ag, dict) else getattr(ag, "tool_selection_summary", None)
        if isinstance(tool_eff, dict):
            tool_selection_stats.update(tool_eff)
        if isinstance(tool_sel, dict):
            tool_selection_stats.update(tool_sel)

    # coordination / workflow
    coordination_stats: Dict = {}
    workflow_stats: Dict = {}
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
    adv_metrics: Dict = {}
    if has_advanced:
        try:
            adv_metrics = rf.advanced.summary or {}
        except Exception:
            pass

    has_rag = getattr(rf, "has_rag", False)
    rag_metrics: Dict = rf.rag_metrics if has_rag else {}

    has_conversation = getattr(rf, "has_conversation", False)
    conversation_sessions: list = rf.conversation_sessions if has_conversation else []

    # Build HTML
    parts = [
        _build_css(),
        _build_header(total_tasks, tcr, acc, latency, harness_groups),
        _build_scorecard(harness_groups),
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, harness_groups.get("A", {}), quality_metrics),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {}), hallucination_data),
        _build_gate_d(latency_stats, token_stats, harness_groups.get("D", {})),
        _build_gate_e_from_rf(rf, harness_groups.get("E", {})),
        _build_gate_f(coordination_stats, workflow_stats, has_agentic, harness_groups.get("F", {})),
        _build_gate_g(quality_metrics, llm_judge_data, harness_groups.get("G", {})),
        _build_advanced_section(adv_metrics, rag_metrics, has_advanced, has_rag, has_conversation, conversation_sessions),
        _build_recommendations(harness_groups, tcr, acc, hall_rate, latency, quality_metrics),
        _build_conclusion(total_tasks, tcr, acc, hall_rate, harness_groups),
        '</div></body></html>',
    ]
    return ''.join(parts)
