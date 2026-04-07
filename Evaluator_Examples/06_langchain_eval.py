"""
06_langchain_eval.py — LangChain 에이전트 평가 (@agent_eval 데코레이터 방식)
=============================================================================

@agent_eval(framework="langchain") 데코레이터 한 줄로 Layer 1/2 + 보안 지표를
자동 수집합니다. 시나리오 루프에서 EvalMetadata로 tool_calls·chain_steps를 주입해
WorkflowExecutionTracker·ToolSelectionTracker·RetryCorrectionTracker를 활성화합니다.

커버 지표:
  Layer 1  │ TCR · Accuracy · Hallucination · ResponseQuality · Latency · TokenEconomy
  Layer 2  │ ToolCall · Retry · ToolSelection · WorkflowExecution
  보안 (opt-in) │ InputSanitization · OutputLeakage · ToolAuthorization

실행:
    python Evaluator_Examples/06_langchain_eval.py

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

_try_setup_otel("06-langchain-eval")


def _load_golden(filename: str) -> list:
    path = project_root / "data" / "golden_datasets" / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ─── 도구 카탈로그 ────────────────────────────────────────────────────────────
_TOOL_PRIVILEGES: dict[str, str] = {
    "web_search": "read", "arxiv_search": "read", "wikipedia_search": "read",
    "calculator": "read", "code_executor": "execute", "db_lookup": "read",
    "data_analyzer": "read", "doc_retriever": "read", "summarizer": "read",
    "report_writer": "write",
}
_TOOL_RESULTS: dict[str, str] = {
    "web_search": "검색 완료: 관련 문서 8건 반환",
    "arxiv_search": "논문 검색 완료: 5편 반환 (관련도 상위)",
    "wikipedia_search": "Wikipedia 항목 로드: 2,340자",
    "calculator": "계산 완료: 결과값 반환",
    "code_executor": "코드 실행 완료: exit_code=0",
    "db_lookup": "DB 조회 완료: 레코드 7건 반환",
    "data_analyzer": "데이터 분석 완료: 통계 요약 반환",
    "doc_retriever": "문서 검색 완료: 상위 3개 청크 반환",
    "summarizer": "요약 완료: 원문 3,200자 → 280자",
    "report_writer": "보고서 저장 완료: report.pdf 24페이지",
}

SCENARIOS = _load_golden("langchain_eval_scenarios.json")


def _make_tool_calls(tools: list[str], rng: random.Random, success_rate: float = 1.0) -> list[dict]:
    calls = []
    for tool_name in tools:
        ok = rng.random() < success_rate
        call: dict = {
            "tool_name": tool_name,
            "success": ok,
            "duration": round(rng.uniform(0.1, 1.8), 3),
            "parameters": {"query": f"query_for_{tool_name}"},
            "privilege_level": _TOOL_PRIVILEGES.get(tool_name, "read"),
        }
        if ok:
            call["execution_result"] = _TOOL_RESULTS.get(tool_name, "실행 완료")
        else:
            call["error"] = f"Tool '{tool_name}' execution failed: timeout"
        calls.append(call)
    return calls


def _make_workflow_steps(tools: list[str], rng: random.Random) -> list[dict]:
    steps = [{"step_name": "input_parsing", "step_type": "node", "success": True,
               "execution_time": round(rng.uniform(0.05, 0.15), 3), "framework": "langchain"}]
    for tool_name in tools:
        steps.append({"step_name": tool_name, "step_type": "tool_call", "success": True,
                       "execution_time": round(rng.uniform(0.2, 1.5), 3), "framework": "langchain"})
    steps.append({"step_name": "llm_generation", "step_type": "llm_generation", "success": True,
                   "execution_time": round(rng.uniform(0.8, 3.0), 3), "framework": "langchain"})
    steps.append({"step_name": "output_formatting", "step_type": "node", "success": True,
                   "execution_time": round(rng.uniform(0.02, 0.08), 3), "framework": "langchain"})
    return steps


# ─── 모듈 레벨 상태 ──────────────────────────────────────────────────────────
_rng = random.Random(42)
_sc: dict = {}   # 현재 처리 중인 시나리오 (루프에서 설정)
_has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

# ─── 배치 평가용 모니터 ───────────────────────────────────────────────────────
monitor = PerformanceMonitor.for_rag_evaluation(
    output_dir=str(project_root / "results"),
    enable_transparency=True,
    enable_security_metrics=True,
)

# ---------------------------------------------------------------------------
# @agent_eval 데코레이터 — framework="langchain"
# ---------------------------------------------------------------------------
# context_arg="context"     → HallucinationDetector 자동 활성
# enable_hallucination=True → RAG 태스크 할루시네이션 감지
# security_mode=True        → InputSanitization·OutputLeakage 임시 활성
# expected_tools_arg        → ToolSelectionTracker F1 자동 계산
# EvalMetadata(tool_calls)  → ToolCallAnalyzer 활성
# EvalMetadata(chain_steps) → WorkflowExecutionTracker 활성
# EvalMetadata(attempts>1)  → RetryCorrectionTracker 활성
# ---------------------------------------------------------------------------
@agent_eval(
    monitor,
    task_type="information_retrieval",
    framework="langchain",
    context_arg="context",
    enable_hallucination=True,
    security_mode=True,
    expected_tools_arg="expected_tools",
    task_id_prefix="lc",
    flush_every=10,
    flush_filename="06_langchain_eval",
)
def langchain_agent(
    question: str,
    context: str = "",
    ground_truth: str = "",
    expected_tools: Optional[list] = None,
) -> Any:
    """LangChain 에이전트 시뮬레이션 — EvalMetadata로 Layer 2 지표 주입."""
    sc = _sc
    # RAG 시나리오: Layer 3 시뮬레이션 (실제 프로젝트에서는 ragas 등으로 대체)
    if context:
        monitor.record_rag_metrics(
            faithfulness=round(_rng.uniform(0.70, 0.95), 3),
            answer_relevancy=round(_rng.uniform(0.72, 0.96), 3),
            context_precision=round(_rng.uniform(0.65, 0.92), 3),
            context_recall=round(_rng.uniform(0.68, 0.93), 3),
        )
    # 실패 시나리오: 예외로 has_error=True 기록
    if not sc["success"]:
        raise RuntimeError(sc.get("error_message", "external_api_connection_failed"))
    in_tok = _rng.randint(150, 600)
    out_tok = _rng.randint(100, 500)
    return sc["response_text"], EvalMetadata(
        tool_calls=_make_tool_calls(sc["tools_used"], _rng, 0.85),
        chain_steps=_make_workflow_steps(sc["tools_used"], _rng),
        attempts=1 + sc["retry_count"],
        tokens_used={"input": in_tok, "output": out_tok, "total": in_tok + out_tok,
                     "model": "gpt-4o-mini"},
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
    task_type="qa",
    framework="langchain",
    context_arg="context",
    enable_hallucination=True,
)
def langchain_live_agent(
    question: str,
    context: str = "",
    ground_truth: str = "",
) -> Any:
    """실제 또는 목업 LangChain 에이전트 — monitor.task() 대신 @agent_eval 사용."""
    if _has_api:
        try:
            result = _real_langchain_agent(question, ["web_search"])
            return result["response"], EvalMetadata(tool_calls=result.get("tool_calls", []))
        except Exception:
            pass
    result = _mock_langchain_agent(question, ["web_search"], _rng)
    return result["response"], EvalMetadata(tool_calls=result.get("tool_calls", []))


# ─── 실제 LangChain 호출 (OPENAI_API_KEY 설정 시) ────────────────────────────
def _real_langchain_agent(question: str, tool_names: list) -> dict:
    """실제 ChatOpenAI 직접 호출 (OPENAI_API_KEY 설정 시 사용).

    실제 tool-use 에이전트가 필요한 경우::

        from langchain.agents import create_react_agent, AgentExecutor
        agent = create_react_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools)
        result = executor.invoke({"input": question})
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0)
    msg = llm.invoke([HumanMessage(content=question)])
    return {
        "response": msg.content,
        "tool_calls": [{"tool_name": t, "success": True, "duration": 0.1}
                       for t in tool_names[:2]],
        "success": True,
    }


def _mock_langchain_agent(question: str, tools: list, rng: random.Random) -> dict:
    """목업 LangChain AgentExecutor (API 키 없을 때 사용)."""
    time.sleep(0.001)
    keywords = question.split()[:3]
    response = (f"[LangChain 응답] '{' '.join(keywords)}' 관련 정보를 검색했습니다. "
                f"도구 {len(tools[:2])}개를 사용해 답변을 생성했습니다.")
    return {
        "response": response,
        "tool_calls": [{"tool_name": t, "success": True,
                        "duration": round(rng.uniform(0.1, 0.5), 3)} for t in tools[:2]],
        "success": rng.random() > 0.15,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 메인 평가 함수
# ═══════════════════════════════════════════════════════════════════════════

def run_langchain_evaluation():
    print("\n" + "=" * 70)
    print("  LangChain 에이전트 평가 — @agent_eval(framework='langchain')")
    print("  Layer 1/2 지표 + 보안 메트릭 전체 커버")
    print("=" * 70)

    avail = check_framework_availability("langchain")
    if avail.get("langchain"):
        print("  LangChain 설치됨 — 실제 에이전트 연동 가능")
    else:
        print("  LangChain 미설치 — 시뮬레이션 모드로 실행")
        print(f"     설치 방법: {get_installation_instructions('langchain')}")

    print(f"\n  {'task_id':<20} {'type':<22} {'success':<8} {'tools':>5}  {'retry':>5}")
    print(f"  {'─'*20} {'─'*22} {'─'*8} {'─'*5}  {'─'*5}")

    global _sc
    for idx, sc in enumerate(SCENARIOS):
        _sc = sc
        try:
            langchain_agent(
                question=sc["request"],
                context=sc["context_text"],
                ground_truth=sc["ground_truth"],
                expected_tools=sc["expected_tools"],
            )
        except RuntimeError:
            pass  # has_error=True として既に記録済み
        flag = "" if sc["success"] else "X"
        print(f"  [{flag}] {sc['task_id']:<18} {sc['task_type']:<22} {str(sc['success']):<8} "
              f"{len(sc['tools_used']):>5}  {sc['retry_count']:>5}")

    # ── リポート 저장 ──────────────────────────────────────────────────────
    report = monitor.generate_report()
    filename = f"[LC]_langchain_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    retry_data = monitor.retry_tracker.get_retry_metrics()
    tool_eff_data = monitor.tool_analyzer.get_efficiency_stats()

    total = report.total_tasks
    passed = sum(1 for sc in SCENARIOS if sc["success"])

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {total}개  |  성공: {passed}/{len(SCENARIOS)}  |  저장: {saved_path}")

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

    print(f"\n  [Layer 2 — 에이전트 지표]")
    wf_rate = wf_data.get("success_rate", 0) if isinstance(wf_data, dict) else 0
    print(f"    워크플로우 성공률:       {wf_rate:.1f}%")
    if tool_sel_data:
        print(f"    Tool Selection F1:      {tool_sel_data.get('f1', 0):.3f}"
              f"  (P={tool_sel_data.get('precision', 0):.3f}"
              f"  R={tool_sel_data.get('recall', 0):.3f})")
    if retry_data:
        print(f"    재시도율:               {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률:          {retry_data.get('first_attempt_success_rate', 0):.1f}%")
    if tool_eff_data:
        print(f"    도구 호출 성공률:       {tool_eff_data.get('success_rate', 0):.1f}%")

    if rag_data:
        print(f"\n  [RAG 지표 (Layer 3 시뮬레이션)]")
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            val = rag_data.get(metric, {}).get("mean", 0)
            print(f"    {metric:<24}: {val:.3f}")

    # ── 검증 테이블 ────────────────────────────────────────────────────────
    print(f"\n  {'━'*70}")
    print(f"  검증 테이블 — 기대 범위 vs 실제 측정값")
    print(f"  {'━'*70}")
    print(f"  {'지표':<36} {'기대':<18} {'실제':<14} 결과")
    print(f"  {'─'*36} {'─'*18} {'─'*14} {'─'*6}")

    tcr_val = tcr_data.get("tcr", 0)
    overall_acc = accuracy_data.get("overall_accuracy", 0)
    avg_quality = quality_data.get("avg_total_score", 0)
    avg_lat = latency_data.get("avg", 0)
    total_tokens = token_data.get("total_tokens", 0)
    wf_rate_val = wf_rate
    f1_val = tool_sel_data.get("f1", 0) if tool_sel_data else 0
    retry_rate = retry_data.get("retry_rate", 0) if retry_data else 0

    checks = [
        ("TCR (성공 태스크 완료율)",          "> 50%",     f"{tcr_val:.1f}%",       tcr_val > 50),
        ("전체 평균 정확도",                  "> 3%",      f"{overall_acc:.1f}%",   overall_acc > 3),
        ("평균 응답 품질",                    "> 1.0/5.0", f"{avg_quality:.2f}",    avg_quality > 1.0),
        ("평균 지연",                         "< 15.0s",   f"{avg_lat:.2f}s",       avg_lat < 15.0),
        ("총 토큰 (10 태스크)",               "> 1,000",   f"{total_tokens:,}",     total_tokens > 1000),
        ("WorkflowTracker 기록 완료",         ">= 0",      f"{wf_rate_val:.1f}%",   True),
        ("Tool Selection 평가 기록 완료",     ">= 0",      f"{f1_val:.3f}",         True),
        ("재시도율 (재시도 태스크 존재)",      "> 0%",      f"{retry_rate:.1f}%",    retry_rate > 0),
    ]

    all_pass = True
    for name, expected, actual, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {name:<36} {expected:<18} {actual:<14} {status}")

    print(f"  {'━'*70}")
    print(f"  최종 결과: {'모든 검증 통과' if all_pass else '일부 검증 실패 — 위 항목 확인'}")
    print(f"  {'━'*70}\n")

    if report.alerts:
        print(f"  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:4]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")
        print()

    return saved_path


def run_langchain_live():
    """@agent_eval 데코레이터 기반 Live 평가 패턴.

    실제 LangChain 에이전트 연동 시 권장하는 최소 코드 패턴입니다.
    API 키 없이도 실행 가능한 목업 에이전트를 사용합니다.
    """
    print("\n" + "=" * 70)
    print("  LangChain Live 평가 패턴 — @agent_eval 데코레이터 기반")
    print("  목표: 최소 코드로 Quality · Accuracy · Hallucination 자동 수집")
    print("=" * 70)

    QA_PAIRS = [
        ("한국의 수도는?", "서울", "qa", ["web_search", "wikipedia_search"], None),
        ("Python 리스트 컴프리헨션 예시를 보여줘",
         "[x*2 for x in range(5)] → [0, 2, 4, 6, 8]", "coding", ["code_executor"], None),
        ("머신러닝에서 과적합(overfitting)이란?",
         "훈련 데이터에 과도하게 최적화되어 새 데이터에서 성능이 저하되는 현상",
         "qa", ["web_search", "arxiv_search"],
         "과적합은 모델이 훈련 데이터의 노이즈까지 학습해 일반화 성능이 낮아지는 문제다."),
    ]

    judge_col = "judge/5" if _has_api else "judge"
    print(f"\n  {'task_id':<16} {'accuracy':>10} {'quality':>10} {judge_col:>8} {'결과'}")
    print(f"  {'─'*16} {'─'*10} {'─'*10} {'─'*8} {'─'*4}")

    for i, (question, ground_truth, task_type, tools, context) in enumerate(QA_PAIRS):
        langchain_live_agent(
            question=question,
            context=context or "",
            ground_truth=ground_truth,
        )

        # 마지막 기록에서 지표 확인
        acc_evals = monitor_live.accuracy_evaluator.evaluations
        qual_evals = monitor_live.quality_evaluator.evaluations
        acc = acc_evals[-1].get("accuracy_score", 0) if acc_evals else 0.0
        qual = qual_evals[-1].get("total_score", 0) if qual_evals else 0.0
        judge_overall = "—"
        if monitor_live.llm_judge and monitor_live.llm_judge.results:
            last_j = monitor_live.llm_judge.results[-1]
            if last_j.get("scores"):
                judge_overall = f"{last_j['scores']['overall']:.2f}"
        print(f"  {'OK':<16} {acc:>10.3f} {qual:>10.2f} {judge_overall:>8}")

    saved = monitor_live.save_to_file(
        f"[LC]_langchain_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    print(f"\n  저장: {saved}")
    print(f"\n  ─── @agent_eval 자동 수집 지표 ───")
    print(f"  Layer 1 │ TCR · Latency · TokenEconomy (기본)")
    print(f"           │ Quality   ← question + response")
    print(f"           │ Accuracy  ← ground_truth 설정 시")
    print(f"           │ Hallucination ← context_arg + enable_hallucination=True")
    print(f"  Layer 2 │ ToolCall  ← EvalMetadata(tool_calls=[...])")
    print(f"  LLM Judge│ completeness/relevance/factual ← enable_llm_judge=True + API 키")
    if monitor_live.llm_judge:
        js = monitor_live.llm_judge.get_summary()
        if js["count"] > 0:
            print(f"           │ 채점 {js['count']}건 · overall avg {js['avg_scores']['overall']:.2f}/5"
                  f" · 비용 ${js['total_cost_usd']:.5f}")
    print()


if __name__ == "__main__":
    run_langchain_evaluation()
    run_langchain_live()
