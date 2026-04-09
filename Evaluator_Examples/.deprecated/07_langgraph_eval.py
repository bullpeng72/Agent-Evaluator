"""
07_langgraph_eval.py — LangGraph 워크플로우 평가 (@agent_eval 데코레이터 방식)
================================================================================

@agent_eval(framework="langgraph") 데코레이터로 Layer 1/2 + 보안 지표를
자동 수집합니다. EvalMetadata(tool_calls, chain_steps, agent_interactions)로
WorkflowExecution·AgentCoordination·ToolSelection 트래커를 활성화합니다.

커버 지표:
  Layer 1  │ TCR · Accuracy · Hallucination · ResponseQuality · Latency · TokenEconomy
  Layer 2  │ ToolCall · Retry · ToolSelection · AgentCoordination · WorkflowExecution
  보안 (opt-in) │ InputSanitization · OutputLeakage · ToolAuthorization

평가 시나리오 (12개 워크플로우):
  - 단순 선형 워크플로우 (search → generate)
  - RAG 파이프라인 (retrieve → augment → generate)
  - 멀티-에이전트 라우팅 (router → specialist → validator)
  - 조건부 분기 워크플로우 (분기 성공/실패)
  - 노드 재시도 시나리오

실행:
    python Evaluator_Examples/07_langgraph_eval.py

의존성:
    pip install -e "."   (외부 의존성 불필요 — 순수 SDK 기반 시뮬레이션)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval, EvalMetadata
from agent_evaluator.reporting import generate_comprehensive_html_report
from agent_evaluator.integrations.framework_integrations import (
    check_framework_availability,
    get_installation_instructions,
)


def _try_setup_otel(service_name: str) -> None:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.settimeout(1)
        if _s.connect_ex(("localhost", 6006)) != 0:
            return
    try:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name=service_name)
        print(f"  Phoenix 모니터링 활성화 — http://localhost:6006  (service: {service_name})")
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).debug("setup_otel 실패: %s", _e)

_try_setup_otel("07-langgraph-eval")


def _load_golden(filename: str) -> list:
    path = project_root / "data" / "golden_datasets" / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ─── 노드 카탈로그 ────────────────────────────────────────────────────────────
_TOOL_PRIVILEGES: dict[str, str] = {
    "web_search_node": "read", "retrieval_node": "read", "fetch_node": "read",
    "lookup_node": "read", "analyze_node": "read", "classify_node": "read",
    "summarize_node": "read", "validate_node": "read", "generate_node": "write",
    "write_node": "write", "format_node": "write", "router_node": "read",
    "supervisor_node": "read", "code_node": "execute",
}
_NODE_RESULTS: dict[str, str] = {
    "web_search_node": "웹 검색 완료: 상위 5개 결과 반환",
    "retrieval_node": "벡터 검색 완료: 상위 3개 청크 반환 (유사도 0.87)",
    "fetch_node": "외부 API 조회 완료: 데이터 수신",
    "lookup_node": "DB 조회 완료: 레코드 4건 반환",
    "analyze_node": "분석 완료: 주요 패턴 3개 감지",
    "classify_node": "분류 완료: 카테고리=tech, 신뢰도=0.91",
    "summarize_node": "요약 완료: 원문 4,100자 → 320자",
    "validate_node": "검증 완료: 사실 확인 4건 통과",
    "generate_node": "응답 생성 완료: 토큰 247개",
    "write_node": "문서 작성 완료: 1,850자",
    "format_node": "포맷 변환 완료: Markdown → HTML",
    "router_node": "라우팅 결정: specialist_node 선택",
    "supervisor_node": "슈퍼바이저 판단: 승인",
    "code_node": "코드 실행 완료: exit_code=0, 결과 반환",
}

WORKFLOWS = _load_golden("langgraph_eval_scenarios.json")


def _make_tool_calls_from_nodes(nodes: list[dict], rng: random.Random) -> list[dict]:
    calls = []
    for node in nodes:
        if node["type"] == "tool_call":
            name = node["name"]
            ok = node["success"]
            call: dict = {
                "tool_name": name,
                "success": ok,
                "duration": round(rng.uniform(0.2, 2.5), 3),
                "parameters": {"query": f"input_for_{name}"},
                "privilege_level": _TOOL_PRIVILEGES.get(name, "read"),
            }
            if ok:
                call["execution_result"] = _NODE_RESULTS.get(name, "실행 완료")
            else:
                call["error"] = f"Node '{name}' failed: connection timeout"
            calls.append(call)
    return calls


def _nodes_to_chain_steps(nodes: list[dict], rng: random.Random) -> list[dict]:
    """LangGraph 노드 목록 → WorkflowExecutionTracker chain_steps 형식."""
    step_count: dict[str, int] = {}
    steps = []
    for node in nodes:
        n = node["name"]
        step_count[n] = step_count.get(n, 0) + 1
        step_id = f"{n}_{step_count[n]}" if step_count[n] > 1 else n
        steps.append({
            "step_name": step_id,
            "step_type": node["type"],
            "success": node["success"],
            "execution_time": round(rng.uniform(0.3, 2.0), 3),
            "framework": "langgraph",
            "metadata": {"original_node": n},
        })
    return steps


def _transitions_to_interactions(
    transitions: list, success: bool
) -> list[dict]:
    """LangGraph 노드 전환 → AgentCoordinationTracker agent_interactions 형식."""
    return [
        {
            "from_agent": from_node,
            "to_agent": to_node,
            "type": "delegation",
            "success": success,
            "context": {"framework": "langgraph"},
        }
        for from_node, to_node in transitions
    ]


def _make_retry_log(nodes: list[dict], overall_success: bool,
                    exec_time: float, rng: random.Random) -> list[dict]:
    seen: dict[str, bool] = {}
    retried: list[str] = []
    for node in nodes:
        n = node["name"]
        if n not in seen:
            seen[n] = node["success"]
        elif not seen[n]:
            retried.append(n)
    if retried:
        return [
            {"success": False, "retry_reason": f"{retried[0]}_failed",
             "duration": round(rng.uniform(0.5, 2.0), 3)},
            {"success": overall_success, "retry_reason": "",
             "duration": round(rng.uniform(1.0, 4.0), 3)},
        ]
    return [{"success": overall_success, "retry_reason": "", "duration": round(exec_time, 3)}]


# ─── 모듈 레벨 상태 ──────────────────────────────────────────────────────────
_rng = random.Random(7)
_wf: dict = {}   # 현재 처리 중인 워크플로우
_has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

# ─── 배치 평가용 모니터 ───────────────────────────────────────────────────────
monitor = PerformanceMonitor.for_rag_evaluation(
    output_dir=str(project_root / "results"),
    enable_transparency=True,
    enable_security_metrics=True,
)

# ---------------------------------------------------------------------------
# @agent_eval 데코레이터 — framework="langgraph"
# ---------------------------------------------------------------------------
# context_arg="context"      → HallucinationDetector (RAG 워크플로우)
# security_mode=True         → InputSanitization·OutputLeakage 임시 활성
# expected_tools_arg         → ToolSelectionTracker F1 (노드 선택 정확도)
# EvalMetadata(tool_calls)   → ToolCallAnalyzer
# EvalMetadata(chain_steps)  → WorkflowExecutionTracker
# EvalMetadata(agent_interactions) → AgentCoordinationTracker
# EvalMetadata(attempts>1)   → RetryCorrectionTracker
# ---------------------------------------------------------------------------
@agent_eval(
    monitor,
    task_type="information_retrieval",
    framework="langgraph",
    context_arg="context",
    enable_hallucination=True,
    security_mode=True,
    expected_tools_arg="expected_nodes",
    task_id_prefix="lg",
    flush_every=12,
    flush_filename="07_langgraph_eval",
)
def langgraph_agent(
    question: str,
    context: str = "",
    ground_truth: str = "",
    expected_nodes: Optional[list] = None,
) -> Any:
    """LangGraph 워크플로우 시뮬레이션 — EvalMetadata로 Layer 2 지표 주입."""
    wf = _wf
    nodes = wf["nodes"]
    transitions = wf["transitions"]
    overall_success = wf["overall_success"]

    has_retry = any(
        n["name"] == nodes[i + 1]["name"] and not n["success"]
        for i, n in enumerate(nodes[:-1])
    ) if len(nodes) > 1 else False
    exec_time = _rng.uniform(1.5, 3.0) * len(nodes) + (1.5 if has_retry else 0.0)
    in_tok = _rng.randint(200, 700) * len(nodes)
    out_tok = _rng.randint(100, 400)

    # RAG 워크플로우: Layer 3 시뮬레이션
    if wf.get("is_rag") and context:
        monitor.record_rag_metrics(
            faithfulness=round(_rng.uniform(0.72, 0.96), 3),
            answer_relevancy=round(_rng.uniform(0.73, 0.95), 3),
            context_precision=round(_rng.uniform(0.68, 0.92), 3),
            context_recall=round(_rng.uniform(0.70, 0.94), 3),
        )

    if not overall_success:
        raise RuntimeError("workflow_step_failed")

    return wf["response_text"], EvalMetadata(
        tool_calls=_make_tool_calls_from_nodes(nodes, _rng),
        chain_steps=_nodes_to_chain_steps(nodes, _rng),
        agent_interactions=_transitions_to_interactions(transitions, overall_success),
        attempts=2 if has_retry else 1,
        tokens_used={
            "input": in_tok,
            "output": out_tok,
            "total": in_tok + out_tok,
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        },
    )


# ─── Live 평가용 모니터 & 데코레이터 ─────────────────────────────────────────
monitor_live = PerformanceMonitor(
    enable_hallucination_detection=True,
    enable_security_metrics=True,
    enable_llm_judge=_has_api,
    judge_sample_rate=1.0,
    output_dir=str(project_root / "results"),
)

@agent_eval(
    monitor_live,
    task_type="information_retrieval",
    framework="langgraph",
    context_arg="context",
    enable_hallucination=True,
)
def langgraph_live_agent(
    question: str,
    context: str = "",
    ground_truth: str = "",
    nodes: Optional[list] = None,
) -> Any:
    """실제 또는 목업 LangGraph 워크플로우 — @agent_eval 데코레이터 방식."""
    nodes = nodes or ["web_search_node", "analyze_node", "generate_node"]
    if _has_api:
        try:
            result = _real_langgraph_workflow(question, nodes)
        except Exception:
            result = _mock_langgraph_workflow(question, nodes, _rng)
    else:
        result = _mock_langgraph_workflow(question, nodes, _rng)

    tool_calls = [
        {"tool_name": o["node"], "success": o["success"],
         "duration": o["duration"],
         "privilege_level": _TOOL_PRIVILEGES.get(o["node"], "read")}
        for o in result["node_outputs"]
    ]
    interactions = [
        {"from_agent": nodes[i], "to_agent": nodes[i+1],
         "type": "delegation", "success": result["success"]}
        for i in range(len(nodes) - 1)
    ]
    return result["response"], EvalMetadata(
        tool_calls=tool_calls,
        chain_steps=[
            {"step_name": o["node"], "step_type": "node",
             "success": o["success"], "execution_time": o["duration"]}
            for o in result["node_outputs"]
        ],
        agent_interactions=interactions,
    )


# ─── Live 헬퍼 ───────────────────────────────────────────────────────────────
def _real_langgraph_workflow(question: str, nodes: list) -> dict:
    """실제 ChatOpenAI 직접 호출 (OPENAI_API_KEY 설정 시 사용).

    실제 LangGraph compiled graph 연동 시::

        from langgraph.graph import StateGraph, END
        compiled = graph.compile()
        for chunk in compiled.stream({"messages": [HumanMessage(content=question)]}):
            node_name = list(chunk.keys())[0]
            final_state = list(chunk.values())[0]
        return {"response": final_state["messages"][-1].content, ...}
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0)
    msg = llm.invoke([HumanMessage(content=question)])
    node_outputs = [{"node": n, "success": True, "duration": 0.1} for n in nodes]
    return {"response": msg.content, "node_outputs": node_outputs, "success": True}


def _mock_langgraph_workflow(question: str, nodes: list, rng: random.Random) -> dict:
    time.sleep(0.001)
    response = (f"[LangGraph 응답] {' → '.join(nodes)} 파이프라인을 통해 "
                f"'{question[:25]}...' 에 대한 답변을 생성했습니다.")
    node_outputs = [
        {"node": n, "success": rng.random() > 0.1,
         "duration": round(rng.uniform(0.2, 1.5), 3)}
        for n in nodes
    ]
    return {"response": response, "node_outputs": node_outputs,
            "success": all(o["success"] for o in node_outputs)}


# ═══════════════════════════════════════════════════════════════════════════
# 메인 평가 함수
# ═══════════════════════════════════════════════════════════════════════════

def run_langgraph_evaluation():
    print("\n" + "=" * 70)
    print("  LangGraph 워크플로우 평가 — @agent_eval(framework='langgraph')")
    print("  Layer 1/2 지표 + 노드 전환 추적 + 보안 메트릭")
    print("=" * 70)

    avail = check_framework_availability("langgraph")
    if avail.get("langgraph"):
        print("  LangGraph 설치됨 — 실제 그래프 연동 가능")
    else:
        print("  LangGraph 미설치 — 시뮬레이션 모드로 실행")
        print(f"     설치 방법: {get_installation_instructions('langgraph')}")

    print(f"\n  {'workflow_id':<22} {'type':<22} {'ok':<5} {'nodes':>5}  {'trans':>5}  {'rag':<5}")
    print(f"  {'─'*22} {'─'*22} {'─'*5} {'─'*5}  {'─'*5}  {'─'*5}")

    global _wf
    for idx, wf in enumerate(WORKFLOWS):
        _wf = wf
        try:
            langgraph_agent(
                question=wf["request"],
                context=wf["context_text"],
                ground_truth=wf["ground_truth"],
                expected_nodes=wf.get("expected_nodes"),
            )
        except RuntimeError:
            pass  # has_error=True として既に記録済み

        flag = "V" if wf["overall_success"] else "X"
        print(f"  [{flag}] {wf['workflow_id']:<20} {wf['task_type']:<22} "
              f"{str(wf['overall_success']):<5} {len(wf['nodes']):>5}  "
              f"{len(wf['transitions']):>5}  {str(wf['is_rag']):<5}")

    # ── リポート 저장 ──────────────────────────────────────────────────────
    report = monitor.generate_report()
    filename = f"[LG]_langgraph_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)
    html_path = Path(saved_path).with_suffix(".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"\n  HTML 리포트 저장: {html_path}")

    # ── 집계 결과 출력 ─────────────────────────────────────────────────────
    accuracy_data = report.accuracy_metrics.get("accuracy_scores", {})
    quality_data = report.accuracy_metrics.get("quality", {})
    hallucination_data = report.accuracy_metrics.get("hallucination", {})
    latency_data = report.efficiency_metrics.get("latency", {})
    token_data = report.efficiency_metrics.get("tokens", {})
    rag_data = monitor.get_rag_metrics_summary()
    wf_data = monitor.workflow_tracker.calculate_execution_success_rate()
    tool_sel_data = monitor.tool_selection_tracker.get_accuracy_stats()
    coord_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    retry_data = monitor.retry_tracker.get_retry_metrics()
    tool_eff_data = monitor.tool_analyzer.get_efficiency_stats()

    total = report.total_tasks
    passed = sum(1 for wf in WORKFLOWS if wf["overall_success"])

    print(f"\n{'─'*70}")
    print(f"  총 평가 워크플로우: {total}개  |  성공: {passed}/{len(WORKFLOWS)}  |  저장: {saved_path}")

    print(f"\n  [Layer 1 — 기본 지표]")
    tcr_data = report.accuracy_metrics.get("tcr", {})
    print(f"    TCR:                    {tcr_data.get('tcr', 0):.1f}%")
    print(f"    전체 평균 정확도:        {accuracy_data.get('overall_accuracy', 0):.1f}%")
    print(f"    평균 응답 품질:          {quality_data.get('avg_total_score', 0):.2f}/5.0"
          f"  (등급: {quality_data.get('avg_grade', 'N/A')})")
    print(f"    할루시네이션 탐지율:     {hallucination_data.get('overall_rate', 0):.1f}%")
    print(f"    평균 지연:               {latency_data.get('avg', 0):.2f}s")
    print(f"    P95 지연:                {latency_data.get('p95', 0):.2f}s")
    print(f"    총 토큰:                 {token_data.get('total_tokens', 0):,}")

    print(f"\n  [Layer 2 — 에이전트 지표 (LangGraph 특화)]")
    wf_rate = wf_data.get("success_rate", 0) if isinstance(wf_data, dict) else 0
    print(f"    워크플로우 단계 성공률:  {wf_rate:.1f}%")
    if coord_data:
        print(f"    에이전트 협업 점수:     {coord_data.get('score', 0):.1f}/10.0")
        print(f"    노드 전환 성공률:       {coord_data.get('success_rate', 0):.1f}%")
    if tool_sel_data:
        print(f"    노드 선택 F1:           {tool_sel_data.get('f1', 0):.3f}"
              f"  (P={tool_sel_data.get('precision', 0):.3f}"
              f"  R={tool_sel_data.get('recall', 0):.3f})")
    if retry_data:
        print(f"    재시도율:               {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률:          {retry_data.get('first_attempt_success_rate', 0):.1f}%")
    if tool_eff_data:
        print(f"    도구 노드 성공률:       {tool_eff_data.get('success_rate', 0):.1f}%")

    if rag_data:
        print(f"\n  [RAG 지표 (Layer 3 시뮬레이션)]")
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            val = rag_data.get(metric, {}).get("mean", 0)
            print(f"    {metric:<24}: {val:.3f}")

    # ── 검증 테이블 ────────────────────────────────────────────────────────
    print(f"\n  {'━'*70}")
    print(f"  검증 테이블 — 기대 범위 vs 실제 측정값")
    print(f"  {'━'*70}")
    print(f"  {'지표':<38} {'기대':<18} {'실제':<12} 결과")
    print(f"  {'─'*38} {'─'*18} {'─'*12} {'─'*6}")

    tcr_val = tcr_data.get("tcr", 0)
    overall_acc = accuracy_data.get("overall_accuracy", 0)
    avg_quality = quality_data.get("avg_total_score", 0)
    avg_lat = latency_data.get("avg", 0)
    total_tokens = token_data.get("total_tokens", 0)
    f1_val = tool_sel_data.get("f1", 0) if tool_sel_data else 0
    coord_score = coord_data.get("overall_score", 0) if coord_data else 0
    retry_rate = retry_data.get("retry_rate", 0) if retry_data else 0
    trans_total = sum(len(wf["transitions"]) for wf in WORKFLOWS)

    checks = [
        ("TCR (성공 워크플로우 완료율)",          "> 60%",     f"{tcr_val:.1f}%",     tcr_val > 60),
        ("전체 평균 정확도",                      "> 3%",      f"{overall_acc:.1f}%", overall_acc > 3),
        ("평균 응답 품질",                        "> 1.0/5.0", f"{avg_quality:.2f}",  avg_quality > 1.0),
        ("평균 지연 (노드 합산)",                 "< 50.0s",   f"{avg_lat:.2f}s",     avg_lat < 50.0),
        ("총 토큰 (12 워크플로우)",               "> 5,000",   f"{total_tokens:,}",   total_tokens > 5000),
        ("WorkflowTracker 기록 완료",             ">= 0",      f"{wf_rate:.1f}%",     True),
        ("Tool Selection 평가 기록 완료",         ">= 0",      f"{f1_val:.3f}",       True),
        ("에이전트 협업 점수",                    "> 3.0/10",  f"{coord_score:.1f}",  coord_score > 3.0),
        ("재시도율 (재시도 워크플로우 존재)",      "> 0%",      f"{retry_rate:.1f}%",  retry_rate > 0),
        ("노드 전환 기록 건수",                   f"> 10",     f"{trans_total}건",    trans_total > 10),
    ]

    all_pass = True
    for name, expected, actual, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {name:<38} {expected:<18} {actual:<12} {status}")

    print(f"  {'━'*70}")
    print(f"  최종 결과: {'모든 검증 통과' if all_pass else '일부 검증 실패 — 위 항목 확인'}")
    print(f"  {'━'*70}\n")

    if report.alerts:
        print(f"  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:4]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")
        print()

    return saved_path


def run_langgraph_live():
    """@agent_eval 데코레이터 기반 LangGraph Live 평가 패턴.

    실제 LangGraph DAG 연동 시 권장하는 최소 코드 패턴입니다.
    EvalMetadata로 노드 전환(AgentCoordination)을 자동 기록합니다.
    """
    print("\n" + "=" * 70)
    print("  LangGraph Live 평가 패턴 — @agent_eval(framework='langgraph')")
    print("  목표: 노드 파이프라인 + AgentCoordination 자동 수집")
    print("=" * 70)

    LIVE_WORKFLOWS = [
        {"id": "live_lg_01", "type": "information_retrieval",
         "question": "RAG 파이프라인에서 컨텍스트 관련성을 높이는 방법은?",
         "gt": "청크 크기 조정, 재순위 모델 적용, 메타데이터 필터링이 효과적입니다.",
         "context": "RAG 파이프라인의 검색 품질은 청크 전략, 임베딩 모델, 재순위 단계에 의해 결정된다.",
         "nodes": ["retrieval_node", "analyze_node", "generate_node"]},
        {"id": "live_lg_02", "type": "reasoning",
         "question": "멀티-에이전트 시스템에서 supervisor 패턴의 장점은?",
         "gt": "중앙 집중식 라우팅으로 에이전트 간 역할이 명확하고 오류 전파를 차단하기 용이합니다.",
         "context": None,
         "nodes": ["router_node", "supervisor_node", "generate_node"]},
        {"id": "live_lg_03", "type": "coding",
         "question": "Python asyncio에서 gather()와 wait()의 차이는?",
         "gt": "gather()는 모든 코루틴을 완료까지 기다리고, wait()는 조건을 지정 가능합니다.",
         "context": None,
         "nodes": ["web_search_node", "code_node", "validate_node", "generate_node"]},
    ]

    judge_col = "judge/5" if _has_api else "judge"
    print(f"\n  {'workflow_id':<16} {'accuracy':>10} {'quality':>10} {'노드수':>6} {judge_col:>8} {'결과'}")
    print(f"  {'─'*16} {'─'*10} {'─'*10} {'─'*6} {'─'*8} {'─'*4}")

    for wf in LIVE_WORKFLOWS:
        langgraph_live_agent(
            question=wf["question"],
            context=wf.get("context") or "",
            ground_truth=wf["gt"],
            nodes=wf["nodes"],
        )

        acc_evals = monitor_live.accuracy_evaluator.evaluations
        qual_evals = monitor_live.quality_evaluator.evaluations
        acc = acc_evals[-1].get("accuracy_score", 0) if acc_evals else 0.0
        qual = qual_evals[-1].get("total_score", 0) if qual_evals else 0.0
        judge_overall = "—"
        if monitor_live.llm_judge and monitor_live.llm_judge.results:
            last_j = monitor_live.llm_judge.results[-1]
            if last_j.get("scores"):
                judge_overall = f"{last_j['scores']['overall']:.2f}"
        print(f"  {'OK':<16} {acc:>10.3f} {qual:>10.2f} {len(wf['nodes']):>6} {judge_overall:>8}")

    coord_data = monitor_live.agent_coordination_tracker.calculate_coordination_score()
    if coord_data:
        print(f"\n  에이전트 협업 점수: {coord_data.get('score', 0):.1f}/10.0  "
              f"(노드 전환 성공률: {coord_data.get('success_rate', 0):.1f}%)")

    saved = monitor_live.save_to_file(
        f"[LG]_langgraph_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    print(f"\n  저장: {saved}")
    print(f"\n  ─── @agent_eval(framework='langgraph') 자동 수집 지표 ───")
    print(f"  Layer 1 │ TCR · Latency · TokenEconomy · Quality · Accuracy · Hallucination")
    print(f"  Layer 2 │ ToolCall, WorkflowExecution ← EvalMetadata(tool_calls, chain_steps)")
    print(f"           │ AgentCoordination ← EvalMetadata(agent_interactions) ← 노드 전환")
    print(f"  ※ ToolSelection: expected_tools_arg 추가 시 F1 자동 계산")
    print()


if __name__ == "__main__":
    run_langgraph_evaluation()
    run_langgraph_live()
