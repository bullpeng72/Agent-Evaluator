"""
agent_evaluator.integrations.recommend_fix_mcp
===================================================
``search_violations`` MCP 서버와 나란히 등록하는 최소 stdio MCP 서버.

노출 도구는 정확히 하나 — ``recommend_fix(gate, metric=None, value=None) -> str``.
"이 Gate/지표가 나쁠 때 뭘 해야 하는가"라는 정적 지식 조회다 — 새 판정 로직이나
새 추천 지식을 만들지 않는다. 지금까지 세 곳에 흩어져 있던 지식을 하나로 모은
``agent_evaluator.ontology.metric_registry``(``GATE_GUIDANCE``/``NATIVE_METRIC_RULES``/
``ANOMALY_METRIC_SUGGESTIONS``)와 ``agent_evaluator.ontology.mast_taxonomy``(Gate F
전용 MAST 실패모드)를 그대로 읽기만 한다.

``agent_evaluator.rca.diagnose()``와의 차이: ``diagnose()``는 결과 JSON 파일을 읽고
baseline과 대조해 "무엇이 움직였는가"까지 답하는 진단 도구이고, Gate F에 한해서만
MAST 처방을 붙인다. 이 도구는 결과 파일이 없어도(개발 중인 에이전트를 아직 평가하지
않았어도) 호출할 수 있는 더 가벼운 정적 지식 조회이며, Gate A-G 전체에 대해 답한다 —
"무엇이 움직였는가"가 아니라 "이 Gate/지표가 나쁠 때 보통 뭘 하는가"만 답한다.

``search_violations``와 마찬가지로 세션 내내 살아있는 stdio MCP 서버다. OpenCode
등록은 ``agent-eval opencode install --with-recommend-fix``가 자동으로 수행하거나,
아래처럼 수동으로도 가능하다::

    opencode mcp add agent-evaluator-recommend-fix -- \\
        python -m agent_evaluator.integrations.recommend_fix_mcp

의존성(옵트인, ``pip install "agent-evaluator[mcp]"``)::

    mcp>=1.0.0
"""
from __future__ import annotations

from typing import Any

_GATE_NAMES = (
    "A=Goal Achievement, B=Behavioral Integrity, C=Reliability, D=Performance Contract, "
    "E=Security Boundary, F=Multi-Agent Coordination, G=Observability"
)


def format_recommendation(
    gate: str, metric: str | None = None, value: float | None = None,
) -> str:
    """Gate/지표 하나에 대한 조치 후보 텍스트를 만든다.

    Args:
        gate: ``"A"``~``"G"`` 중 하나(대소문자 무관). 유효하지 않으면 그 사실을
            명시적으로 알린다(모델이 없는 Gate를 지어내지 않도록).
        metric: 세부 지표명(선택). ``NATIVE_METRIC_RULES``/``ANOMALY_METRIC_SUGGESTIONS``의
            키이거나, Gate F라면 ``MASTFailureMode.related_gate_f_metric`` 값(예:
            ``"conflict_resolution"``).
        value: ``metric``의 현재 측정값(선택). 주어지면 ``NATIVE_METRIC_RULES``
            임계값 위반 여부까지 함께 알려준다.

    Returns:
        사람이 읽을 수 있는 조치 후보 텍스트. 항상 HOTL 고지문으로 끝난다 — 이
        도구는 확정 진단이 아니라 후보만 제시한다.
    """
    from agent_evaluator.ontology.mast_taxonomy import mast_failure_modes_for_gate_f_metric
    from agent_evaluator.ontology.metric_registry import (
        GATE_GUIDANCE,
        NATIVE_METRIC_RULES,
        anomaly_suggestion_for,
        canonical_metric_name,
    )

    gate_key = (gate or "").strip().upper()
    guidance = GATE_GUIDANCE.get(gate_key)
    if guidance is None:
        return (
            f"'{gate}' is not a valid Gate. Specify one of Gate A-G ({_GATE_NAMES})."
        )

    lines = [f"[Gate {gate_key} — {guidance.label}] {guidance.guidance}"]

    if metric:
        # SPEC-041: rca.diagnose()가 주는 필드명(hall_rate, avg_role_compliance,
        # p95_latency_ms …)을 규칙/제안/MAST 조회용 canonical 키로 정규화한다. 두 MCP
        # 도구(diagnose ↔ recommend_fix)가 같은 어휘를 쓰게 해, "규칙이 있는데 없다"고
        # 답하던 문제를 없앤다. 정규화로 이름이 바뀌면 사용자에게 그 사실을 알린다.
        canonical = canonical_metric_name(metric)
        if canonical and canonical != metric:
            lines.append(f"\n(interpreting '{metric}' as '{canonical}')")
        metric = canonical or metric
        matched_rule = next((r for r in NATIVE_METRIC_RULES if r.metric == metric), None)
        if matched_rule is not None:
            lines.append(f"\n[{matched_rule.title}] {matched_rule.guidance}")
            if value is not None:
                _status = "violated" if matched_rule.is_violated(value) else "within range"
                lines.append(
                    f"  current value {value} — threshold {matched_rule.threshold}"
                    f" ({matched_rule.direction}): {_status}"
                )

        # canonical 지표명(latency/accuracy/error_rate)이나 AnomalyEvent.type
        # (latency_trend 등) 둘 다 받아 이상탐지 조치 제안을 붙인다.
        anomaly_suggestion = anomaly_suggestion_for(metric)
        if anomaly_suggestion:
            lines.append(f"\n[anomaly note] {anomaly_suggestion}")

        mast_candidates: tuple[Any, ...] = ()
        if gate_key == "F":
            mast_candidates = mast_failure_modes_for_gate_f_metric(metric)
            if mast_candidates:
                lines.append(
                    "\n[MAST failure-mode candidates — Cemri et al., NeurIPS 2025, "
                    "not a verdict]"
                )
                for m in mast_candidates:
                    lines.append(
                        f"  [{m.code}] {m.name} "
                        f"(observed in {m.prevalence_pct}% of paper traces): {m.description}"
                    )
                    lines.append(f"    → {m.remediation}")

        if matched_rule is None and not anomaly_suggestion and not mast_candidates:
            _no_rule_note = (
                f"No detailed rule for '{metric}' — refer to the Gate-level guidance only."
            )
            lines.append(f"\n({_no_rule_note})")

    lines.append(
        "\nThis is candidate guidance only — confirming the actual cause and the final "
        "judgment are up to you."
    )
    return "\n".join(lines)


def build_server() -> Any:
    """``recommend_fix`` 도구 1개를 노출하는 ``FastMCP`` 인스턴스를 만든다.

    Returns:
        ``mcp.server.fastmcp.FastMCP`` 인스턴스(아직 ``run()``은 호출하지 않음).
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("agent-evaluator-recommend-fix")

    @server.tool()
    def recommend_fix(gate: str, metric: str | None = None, value: float | None = None) -> str:
        """Gate A-G 중 하나가 나쁠 때(fail/warn) 참고할 조치 후보를 반환한다.

        결과 파일이 없어도 호출할 수 있는 정적 지식 조회다 — 개발 중인 에이전트를
        아직 평가하지 않았어도, "Gate E가 나쁘면 보통 뭘 하는가" 같은 질문에 즉시
        답한다. gate는 필수(A~G, 대소문자 무관). metric을 함께 주면(예: "latency",
        "hallucination_rate", Gate F는 "conflict_resolution" 등) 더 구체적인 규칙과
        (Gate F는) MAST 실패모드 후보까지 덧붙는다. value를 주면 그 값이 실제로
        임계값을 위반하는지도 알려준다. 확정 진단이 아니라 후보 조치만 제시한다 —
        최종 판단은 항상 사람의 몫이다.
        """
        return format_recommendation(gate, metric, value)

    return server


def main() -> None:
    try:
        server = build_server()
    except ImportError as exc:
        # SPEC-041: [mcp] extra 미설치 시 bare ImportError 대신 명확한 안내(stderr) —
        # 이 프로세스는 OpenCode/Claude가 스폰하므로 사용자는 클라이언트 로그에서만 본다.
        import sys

        sys.stderr.write(
            f"[agent-evaluator] recommend_fix MCP server needs the optional 'mcp' "
            f"dependency — install it with:  pip install \"agent-evaluator[mcp]\"\n"
            f"  (original error: {exc})\n"
        )
        raise SystemExit(1) from exc
    server.run()


if __name__ == "__main__":
    main()
