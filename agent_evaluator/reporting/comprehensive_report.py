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
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Evaluator — Harness Gate 리포트</title>
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
</style>
</head>
<body>
<div class="container">'''


# ---------------------------------------------------------------------------
# Not-tested notice helper
# ---------------------------------------------------------------------------

def _not_tested(reason: str = "") -> str:
    """데이터가 수집되지 않은 섹션에 표시하는 '테스트되지 않음' 배너."""
    msg = reason or "해당 항목이 테스트되지 않았습니다."
    return f'<div class="not-tested">🔍 <strong>미측정</strong>&nbsp;{msg}</div>'


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
        badge_html = _gate_badge(gate_status) if gate_status else '<span style="font-size:11px;color:#9ca3af">미설정</span>'
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
# Gate A — Goal Achievement
# ---------------------------------------------------------------------------

def _build_gate_a(tcr: float, success_rate: float, acc: float,
                  accuracy_metrics: Dict, hallucination_data: Dict,
                  harness_a: Dict) -> str:
    color = _GATE_COLORS["A"]
    gate_status = (harness_a.get("gate") or harness_a.get("status") or "").lower()
    badge = _gate_badge(gate_status) if gate_status else ""

    # TCR / accuracy KPIs
    kpis = (
        f'<div class="kpi"><div class="kpi-lbl">TCR</div>'
        f'<div class="kpi-val" style="color:{_score_color(tcr)}">{_num(tcr, ".1f")}%</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">완전 성공률</div>'
        f'<div class="kpi-val" style="color:{_score_color(success_rate)}">{_num(success_rate, ".1f")}%</div></div>'
        f'<div class="kpi"><div class="kpi-lbl">전체 정확도</div>'
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
            f'<h3>task_type별 정확도</h3>'
            f'<table class="mtable"><thead><tr><th>Task Type</th><th>정확도</th></tr></thead>'
            f'<tbody>{type_rows}</tbody></table>'
        )

    # Hallucination
    hall_html = ""
    hall_rate = 0.0
    _hall_measured = bool(hallucination_data) and hallucination_data.get("total_evaluated", 0) > 0
    if not _hall_measured:
        hall_html = (
            f'<h3>환각 탐지</h3>'
            + _not_tested("환각 탐지가 활성화되지 않았습니다 — "
                          "<code>enable_hallucination_detection=True</code> 로 측정할 수 있습니다.")
        )
    if _hall_measured:
        hall_rate = float(hallucination_data.get("overall_rate") or 0)
        hall_pct = hall_rate  # overall_rate is already a percentage (0–100 scale)
        hall_col = _score_color(100 - hall_pct)
        hall_html = (
            f'<h3>환각 탐지</h3>'
            f'<div class="kpis">'
            f'<div class="kpi"><div class="kpi-lbl">환각율</div>'
            f'<div class="kpi-val" style="color:{hall_col}">{hall_pct:.1f}%</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">안전율</div>'
            f'<div class="kpi-val" style="color:{_score_color(100 - hall_pct)}">{100 - hall_pct:.1f}%</div></div>'
            f'</div>'
        )

    # Harness A detail
    details = harness_a.get("details") or {}
    harness_rows = ""
    fields = [
        ("instruction_adherence", "지시 이행률"),
        ("goal_alignment", "목표 정렬 점수"),
        ("plan_coherence", "계획 일관성"),
        ("subtask_completion", "하위 태스크 완료율"),
        ("context_retention", "컨텍스트 유지율"),
        ("knowledge_retention", "지식 보존·활용"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness A 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — InstructionConfig · GoalAlignmentConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-a" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate A &nbsp;<span style="font-size:14px;color:#374151">목표 달성 (Goal Achievement)</span>&nbsp;{badge}</h2>'
        f'<div class="kpis">{kpis}</div>'
        f'{type_table}'
        f'{hall_html}'
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
            f'<h3>도구 사용 분석</h3>'
            + _not_tested("에이전틱 도구 사용 데이터가 없습니다 — "
                          "<code>task_type=\"tool_use\"</code> 태스크를 실행하면 측정됩니다.")
        )
    elif not tool_selection_stats:
        tool_html = (
            f'<h3>도구 사용 분석</h3>'
            + _not_tested("도구 선택 데이터가 수집되지 않았습니다.")
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
                f'<div class="kpi"><div class="kpi-lbl">도구 효율성</div>'
                f'<div class="kpi-val" style="color:{_score_color(float(eff)*100)}">{_pct(eff)}</div></div>'
            )
        if redundancy is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">중복 호출률</div>'
                f'<div class="kpi-val" style="color:{_score_color(100 - float(redundancy)*100)}">{_pct(redundancy)}</div></div>'
            )
        if fail_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">도구 실패율</div>'
                f'<div class="kpi-val" style="color:{_score_color(100 - float(fail_rate)*100)}">{_pct(fail_rate)}</div></div>'
            )
        if kpi_parts:
            tool_html = f'<h3>도구 사용 분석</h3><div class="kpis">{kpi_parts}</div>'

    # Harness B detail
    details = harness_b.get("details") or {}
    harness_rows = ""
    fields = [
        ("loop_detection_score", "루프 탐지율"),
        ("scope_compliance", "범위 준수율"),
        ("tool_param_safety", "도구 파라미터 안전성"),
        ("context_window_efficiency", "컨텍스트 창 효율"),
        ("state_consistency", "상태 일관성"),
        ("deadlock_score", "교착 방지율"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness B 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — LoopDetectionConfig · ScopeConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-b" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate B &nbsp;<span style="font-size:14px;color:#374151">행동 무결성 (Behavioral Integrity)</span>&nbsp;{badge}</h2>'
        f'{tool_html}'
        f'{harness_block}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Gate C — Reliability
# ---------------------------------------------------------------------------

def _build_gate_c(retry_metrics: Dict, harness_c: Dict) -> str:
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
            f'<h3>재시도 / 복구</h3>'
            + _not_tested("재시도 데이터가 수집되지 않았습니다 — "
                          "재시도가 발생하지 않았거나 <code>RetryConfig</code> 가 설정되지 않았습니다.")
        )
    if _retry_measured:
        retry_rate = retry_metrics.get("overall_retry_rate") or retry_metrics.get("retry_rate")
        correction_rate = retry_metrics.get("correction_success_rate") or retry_metrics.get("success_rate")
        kpi_parts = ""
        if retry_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">재시도율</div>'
                f'<div class="kpi-val">{_pct(retry_rate)}</div></div>'
            )
        if correction_rate is not None:
            kpi_parts += (
                f'<div class="kpi"><div class="kpi-lbl">재시도 성공률</div>'
                f'<div class="kpi-val" style="color:{_score_color(float(correction_rate)*100)}">{_pct(correction_rate)}</div></div>'
            )
        if kpi_parts:
            retry_html = f'<h3>재시도 / 복구</h3><div class="kpis">{kpi_parts}</div>'

    details = harness_c.get("details") or {}
    harness_rows = ""
    fields = [
        ("reproducibility", "재현성"),
        ("fault_tolerance", "장애 허용률"),
        ("graceful_degradation", "점진적 품질 하강"),
        ("retry_consistency", "재시도 일관성"),
        ("idempotency", "멱등성"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness C 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — FaultToleranceConfig · ReproducibilityConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-c" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate C &nbsp;<span style="font-size:14px;color:#374151">신뢰성 (Reliability)</span>&nbsp;{badge}</h2>'
        f'{retry_html}'
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
        lat_html = f'<h3>지연 분석</h3>' + _not_tested("지연 데이터가 수집되지 않았습니다.")
    if latency_stats:
        lat_kpis = (
            f'<div class="kpi"><div class="kpi-lbl">Mean</div><div class="kpi-val">{_sec(latency_stats.get("mean"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P50</div><div class="kpi-val">{_sec(latency_stats.get("p50"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P90</div><div class="kpi-val">{_sec(latency_stats.get("p90"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P95</div><div class="kpi-val">{_sec(latency_stats.get("p95"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">P99</div><div class="kpi-val">{_sec(latency_stats.get("p99"))}</div></div>'
        )
        lat_html = f'<h3>지연 분석</h3><div class="kpis">{lat_kpis}</div>'

    # Token & cost KPIs
    tok_html = ""
    if not token_stats:
        tok_html = (
            f'<h3>토큰 &amp; 비용</h3>'
            + _not_tested("토큰·비용 데이터가 수집되지 않았습니다 — "
                          "토큰 수를 <code>TaskResult</code> 에 기록하면 측정됩니다.")
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
            f'<div class="kpi"><div class="kpi-lbl">총 토큰</div>'
            f'<div class="kpi-val">{int(token_stats.get("total_tokens") or 0):,}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">평균 토큰/Task</div>'
            f'<div class="kpi-val">{_num(token_stats.get("avg_tokens_per_task"), ".0f")}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">총 비용</div>'
            f'<div class="kpi-val">{_cost(token_stats.get("total_cost"))}</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">비용/Task</div>'
            f'<div class="kpi-val">{_cost(token_stats.get("avg_cost_per_task"))}</div></div>'
        )
        tok_html = f'<h3>토큰 & 비용</h3><div class="kpis">{tok_kpis}</div>'

    details = harness_d.get("details") or {}
    harness_rows = ""
    fields = [
        ("sla_compliance", "SLA 준수율"),
        ("efficiency_score", "효율 점수"),
        ("resource_budget_compliance", "리소스 예산 준수"),
        ("ttft_variability", "TTFT 변동성"),
        ("cost_predictability", "비용 예측가능성"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness D 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — SLAConfig · EfficiencyConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-d" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate D &nbsp;<span style="font-size:14px;color:#374151">성능 계약 (Performance Contract)</span>&nbsp;{badge}</h2>'
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
        input_sec = monitor.input_sanitizer.get_sanitization_metrics() if hasattr(monitor, 'input_sanitizer') else {}
        output_leak = monitor.output_leakage_detector.get_leakage_metrics() if hasattr(monitor, 'output_leakage_detector') else {}
        tool_auth = monitor.tool_auth_tracker.get_authorization_metrics() if hasattr(monitor, 'tool_auth_tracker') else {}
        priv_esc = monitor.privilege_escalation_detector.get_escalation_metrics() if hasattr(monitor, 'privilege_escalation_detector') else {}
        chain_atk = monitor.tool_chain_attack_detector.get_attack_metrics() if hasattr(monitor, 'tool_chain_attack_detector') else {}
        sec_html = _build_security_kpis(input_sec, output_leak, tool_auth, priv_esc, chain_atk)
    except Exception:
        pass

    details = harness_e.get("details") or {}
    harness_rows = ""
    fields = [
        ("threat_severity_score", "위협 심각도 점수"),
        ("compliance_score", "규정 준수율"),
        ("threat_response_score", "위협 대응 점수"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness E 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — ThreatSeverityConfig · ComplianceConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-e" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate E &nbsp;<span style="font-size:14px;color:#374151">보안 경계 (Security Boundary)</span>&nbsp;{badge}</h2>'
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
        ("threat_severity_score", "위협 심각도 점수"),
        ("compliance_score", "규정 준수율"),
        ("threat_response_score", "위협 대응 점수"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness E 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — ThreatSeverityConfig · ComplianceConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-e" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate E &nbsp;<span style="font-size:14px;color:#374151">보안 경계 (Security Boundary)</span>&nbsp;{badge}</h2>'
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
            f'<div class="kpi"><div class="kpi-lbl">입력 보안 (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_inp}건 · 위협 {threat_rate:.1f}%</div></div>'
        )

    if output_leak:
        leak_rate = float(output_leak.get("leakage_rate") or 0)
        total_out = output_leak.get("total_outputs_evaluated", 0)
        safe = 100 - leak_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">출력 유출 방지 (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_out}건 · 유출 {leak_rate:.1f}%</div></div>'
        )

    if tool_auth:
        comply = float(tool_auth.get("compliance_rate") or 100)
        total_calls = tool_auth.get("total_tool_calls", 0)
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">도구 권한 준수 (L1)</div>'
            f'<div class="kpi-val" style="color:{_score_color(comply)}">{comply:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_calls}건 호출</div></div>'
        )

    if priv_esc:
        esc_rate = float(priv_esc.get("escalation_rate") or 0)
        total_priv = priv_esc.get("total_evaluations", 0)
        safe = 100 - esc_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">권한 상승 방어 (L2)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_priv}건 · 탐지 {esc_rate:.1f}%</div></div>'
        )

    if chain_atk:
        atk_rate = float(chain_atk.get("detection_rate") or 0)
        total_chains = chain_atk.get("total_chains_analyzed", 0)
        safe = 100 - atk_rate
        kpi_parts.append(
            f'<div class="kpi"><div class="kpi-lbl">공격 체인 탐지 (L2)</div>'
            f'<div class="kpi-val" style="color:{_score_color(safe)}">{safe:.1f}%</div>'
            f'<div style="font-size:10px;color:#6b7280">{total_chains}건 · 의심 {atk_rate:.1f}%</div></div>'
        )

    if not kpi_parts:
        return (
            f'<h3>보안 지표</h3>'
            + _not_tested("보안 지표가 활성화되지 않았습니다 — "
                          "<code>enable_security_metrics=True</code> 로 측정할 수 있습니다.")
        )
    return f'<h3>보안 지표</h3><div class="kpis">{"".join(kpi_parts)}</div>'


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
            f'<h3>협업 / 워크플로우</h3>'
            + _not_tested("멀티에이전트 실행 데이터가 없습니다 — "
                          "에이전트 협업 태스크가 실행되지 않았습니다.")
        )
    if has_agentic:
        kpi_parts = []
        if coordination_stats:
            coord_score = coordination_stats.get("avg_coordination_score") or coordination_stats.get("score")
            if coord_score is not None:
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">협업 점수</div>'
                    f'<div class="kpi-val" style="color:{_score_color(float(coord_score)*100)}">'
                    f'{float(coord_score)*100:.1f}%</div></div>'
                )
        if workflow_stats:
            wf_rate = workflow_stats.get("success_rate") or workflow_stats.get("overall_success_rate")
            step_rate = workflow_stats.get("step_success_rate")
            if wf_rate is not None:
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">워크플로우 성공률</div>'
                    f'<div class="kpi-val" style="color:{_score_color(float(wf_rate)*100)}">'
                    f'{float(wf_rate)*100:.1f}%</div></div>'
                )
            if step_rate is not None:
                _step_pct = float(step_rate) if float(step_rate) > 1.0 else float(step_rate) * 100
                kpi_parts.append(
                    f'<div class="kpi"><div class="kpi-lbl">단계 성공률</div>'
                    f'<div class="kpi-val" style="color:{_score_color(_step_pct)}">'
                    f'{_step_pct:.1f}%</div></div>'
                )
        if kpi_parts:
            coord_html = f'<h3>협업 / 워크플로우</h3><div class="kpis">{"".join(kpi_parts)}</div>'

    details = harness_f.get("details") or {}
    harness_rows = ""
    fields = [
        ("consensus_rate", "합의율"),
        ("propagation_accuracy", "정보 전파 정확도"),
        ("agent_role_compliance", "역할 준수율"),
        ("conflict_resolution_rate", "충돌 해결률"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness F 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — ConsensusConfig · AgentRoleConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-f" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate F &nbsp;<span style="font-size:14px;color:#374151">멀티에이전트 협업 (Multi-Agent Coordination)</span>&nbsp;{badge}</h2>'
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

    quality_html = ""
    if not quality_metrics or quality_metrics.get("total_evaluated", 0) == 0:
        quality_html = (
            f'<h3>응답 품질 (5차원)</h3>'
            + _not_tested("응답 품질 평가 데이터가 수집되지 않았습니다.")
        )
    if quality_metrics and quality_metrics.get("total_evaluated", 0) > 0:
        avg_score = quality_metrics.get("avg_total_score", 0)
        dim_scores = quality_metrics.get("dimension_scores", {})
        dimensions = [
            ("relevance", "관련성"),
            ("completeness", "완전성"),
            ("accuracy", "정확성"),
            ("clarity", "명확성"),
            ("usefulness", "유용성"),
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
            f'<div class="kpi"><div class="kpi-lbl">평균 품질 점수</div>'
            f'<div class="kpi-val" style="color:{_score_color(float(avg_score)/5*100,0.8,0.6)}">'
            f'{float(avg_score):.2f}/5</div></div>'
            f'<div class="kpi"><div class="kpi-lbl">평가 건수</div>'
            f'<div class="kpi-val">{quality_metrics.get("total_evaluated", 0)}</div></div>'
        )
        quality_html = (
            f'<h3>응답 품질 (5차원)</h3>'
            f'<div class="kpis">{kpi_html}</div>'
            f'<table class="mtable"><thead><tr><th>차원</th><th>평균</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )

    # LLM Judge
    judge_html = ""
    if not llm_judge_data:
        judge_html = (
            f'<h3>LLM Judge</h3>'
            + _not_tested("LLM Judge가 활성화되지 않았습니다 — "
                          "<code>enable_llm_judge=True</code> 또는 <code>LLMJudgeConfig</code> 로 측정할 수 있습니다.")
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
                    + _not_tested("LLM Judge 채점 결과가 없습니다 — 샘플 비율(<code>judge_sample_rate</code>) 을 확인하세요.")
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
                    f'<div class="kpi"><div class="kpi-lbl">평가 건수</div>'
                    f'<div class="kpi-val">{judged_count}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">종합 점수</div>'
                    f'<div class="kpi-val" style="color:{_score_color(ov_100)}">'
                    f'{_judge_val(overall)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">완전성</div>'
                    f'<div class="kpi-val">{_judge_val(completeness)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">관련성</div>'
                    f'<div class="kpi-val">{_judge_val(relevance)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">사실 일관성</div>'
                    f'<div class="kpi-val">{_judge_val(factual)}</div></div>'
                    f'<div class="kpi"><div class="kpi-lbl">Judge 모델</div>'
                    f'<div class="kpi-val" style="font-size:11px">{model_name}</div></div>'
                )
                judge_html = f'<h3>LLM Judge (7차원)</h3><div class="kpis">{judge_kpis}</div>'
        except Exception:
            pass

    details = harness_g.get("details") or {}
    harness_rows = ""
    fields = [
        ("explainability_score", "설명가능성"),
        ("observability_score", "내부 상태 관측가능성"),
        ("error_diagnosis_accuracy", "오류 진단 정확도"),
        ("latency_attribution_score", "지연 원인 분석"),
    ]
    for fk, flabel in fields:
        v = details.get(fk)
        if v is not None:
            harness_rows += _metric_row(flabel, v)
    harness_block = ""
    if harness_rows:
        harness_block = (
            f'<h3>Harness G 세부 지표</h3>'
            f'<table class="mtable"><tbody>{harness_rows}</tbody></table>'
        )
    elif not details:
        harness_block = '<div class="inactive-banner">⚙️ Harness Config 미활성 — ExplainabilityConfig · ObservabilityConfig 등을 데코레이터에 전달하면 세부 지표가 표시됩니다.</div>'

    return (
        f'<div class="gate-section" id="gate-g" style="border-left-color:{color}">'
        f'<h2 style="color:{color}">Gate G &nbsp;<span style="font-size:14px;color:#374151">관측가능성 (Observability)</span>&nbsp;{badge}</h2>'
        f'{quality_html}'
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
             '<h2 style="color:#6366f1">고급 평가 (Advanced Metrics)</h2>']

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
                f'<table class="mtable"><thead><tr><th>지표</th><th>평균</th><th>최솟값</th><th>최댓값</th></tr></thead>'
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
                    f'<td style="padding:5px 10px;border-bottom:1px solid #f3f4f6">{len(vals)}건</td>'
                    f'</tr>'
                )
        if rows:
            parts.append(
                f'<h3>RAG 지표 (Ragas)</h3>'
                f'<table class="mtable"><thead><tr><th>지표</th><th>평균</th><th>최솟값</th><th>최댓값</th><th>건수</th></tr></thead>'
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
                f'<h3>멀티턴 대화 세션</h3>'
                f'<table class="mtable"><thead><tr><th>Session ID</th><th>턴 수</th><th>종합 점수</th><th>컨텍스트 유지율</th></tr></thead>'
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
        "A": ("목표 달성", "TCR·정확도·환각 지표를 개선하세요. InstructionConfig / GoalAlignmentConfig를 데코레이터에 추가하여 세부 추적을 활성화하세요."),
        "B": ("행동 무결성", "루프 탐지·범위 준수 설정을 강화하세요. LoopDetectionConfig / ScopeConfig 파라미터를 조정하세요."),
        "C": ("신뢰성", "재시도 정책과 장애 허용 메커니즘을 검토하세요. FaultToleranceConfig를 활성화하여 복구율을 측정하세요."),
        "D": ("성능 계약", "SLA 임계값을 초과했습니다. SLAConfig로 응답시간 상한을 정의하고 P95 지연을 모니터링하세요."),
        "E": ("보안 경계", "보안 위협이 탐지되었습니다. enable_security_metrics=True와 ThreatSeverityConfig를 활성화하세요."),
        "F": ("멀티에이전트 협업", "에이전트 간 협업 점수가 낮습니다. ConsensusConfig / ConflictResolutionConfig를 추가하세요."),
        "G": ("관측가능성", "설명가능성·관측가능성 지표를 강화하세요. ExplainabilityConfig / ObservabilityConfig를 활성화하세요."),
    }
    for key in "ABCDEFG":
        gdata = harness_groups.get(key, {})
        if not isinstance(gdata, dict):
            continue
        gate_status = (gdata.get("gate") or gdata.get("status") or "").lower()
        if gate_status in ("fail", "warn"):
            label, guide = gate_labels.get(key, (f"Gate {key}", "설정을 검토하세요."))
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
            '<div class="rec priority-high"><strong>TCR 개선 필요</strong>'
            '<p>작업 완료율이 75% 미만입니다. 에이전트 프롬프트를 개선하고 실패 케이스를 분석하세요.</p></div>'
        )
    if acc < 70:
        recs.append(
            '<div class="rec priority-high"><strong>정확도 개선 필요</strong>'
            '<p>정확도가 70% 미만입니다. RAG 컨텍스트 품질 또는 ground_truth 설정을 검토하세요.</p></div>'
        )
    if hall_rate > 0.2:
        recs.append(
            '<div class="rec priority-high"><strong>환각 위험 높음</strong>'
            '<p>환각율이 20%를 초과합니다. 사실 검증 로직을 강화하세요.</p></div>'
        )
    if latency > 5.0:
        recs.append(
            '<div class="rec priority-medium"><strong>응답 지연 개선 필요</strong>'
            '<p>평균 응답시간이 5초를 초과합니다. 병렬 처리 또는 캐싱을 검토하세요.</p></div>'
        )

    if not recs:
        recs.append(
            '<div class="rec" style="border-left-color:#10b981">'
            '<strong style="color:#065f46">모든 지표 양호</strong>'
            '<p>현재 설정에서 개선이 필요한 지표가 없습니다. 지속적인 모니터링을 유지하세요.</p>'
            '</div>'
        )

    return (
        '<div class="gate-section" id="recommendations" style="border-left-color:#6366f1">'
        '<h2 style="color:#6366f1">개선 권장사항 (Recommendations)</h2>'
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
        f'<h2 style="color:#374151">결론 및 다음 단계 (Conclusion)</h2>'
        f'<div class="ibox ok">'
        f'<p><strong>평가 등급:</strong> {grade}</p>'
        f'<p><strong>총 태스크:</strong> {total_tasks}개</p>'
        f'<p><strong>TCR:</strong> {_num(tcr, ".1f")}% | <strong>정확도:</strong> {_num(acc, ".1f")}% | '
        f'<strong>환각율:</strong> {hall_rate:.1f}%</p>'
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
        '<h1>📊 Agent Evaluator — Harness Gate 리포트</h1>'
        '<div class="sub">AI Agent 품질 평가 · Harness Gate A–G 중심 구조</div>'
        f'<div class="meta">'
        f'<span>📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>'
        f'<span>📋 {total_tasks}개 태스크</span>'
        f'<span>🔖 v{_ver}</span>'
        f'<span>TCR: <strong>{_num(tcr, ".1f")}%</strong></span>'
        f'<span>정확도: <strong>{_num(acc, ".1f")}%</strong></span>'
        f'<span>지연: <strong>{_num(latency, ".2f")}s</strong></span>'
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
    has_rag = False
    rag_metrics: Dict = {}
    has_conversation = False
    conversation_sessions: list = []

    # Build HTML
    parts = [
        _build_css(),
        _build_header(total_tasks, tcr, acc, latency, harness_groups),
        _build_scorecard(harness_groups),
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, hallucination_data, harness_groups.get("A", {})),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {})),
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
        _build_gate_a(tcr, success_rate, acc, accuracy_metrics, hallucination_data, harness_groups.get("A", {})),
        _build_gate_b(tool_selection_stats, has_agentic, harness_groups.get("B", {})),
        _build_gate_c(retry_metrics, harness_groups.get("C", {})),
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
