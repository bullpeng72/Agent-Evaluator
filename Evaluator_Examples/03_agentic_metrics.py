"""
에이전트 지표 검증 예제 — Agent Evaluator
==========================================

커버 지표 (에이전트 카테고리):
  Layer 2  │ Tool Call Analysis     (효율성 점수 · 중복 호출 · 실패율)
           │ Retry & Correction     (재시도 패턴 · 자기수정 능력 · 첫시도 성공률)
           │ Tool Selection         (F1 기반 Precision · Recall · 선택 정확도)
           │ Agent Coordination     (협업 점수(0-10) · Hub/Chain/Mesh 패턴)
           │ Workflow Execution     (단계별 성공률 · 병목 탐지 · 병렬화 기회)

실행:
    python 03_agentic_metrics.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent_evaluator import PerformanceMonitor, TaskResult

# ────────────────────────────────────────────────────────────────────────────────
# 에이전트 역할 정의
# ────────────────────────────────────────────────────────────────────────────────
AGENTS = {
    "orchestrator": "오케스트레이터",
    "researcher":   "리서처",
    "analyst":      "분석가",
    "writer":       "작성자",
    "reviewer":     "검토자",
}

# 도구 카탈로그
ALL_TOOLS = [
    "web_search", "doc_reader", "data_query", "code_executor",
    "summarizer", "classifier", "translator", "image_analyzer",
    "chart_generator", "report_writer", "email_sender", "db_lookup",
]

# 워크플로우 단계 정의
WORKFLOW_STEPS = [
    {"name": "input_validation",   "type": "validation"},
    {"name": "data_retrieval",     "type": "retrieval"},
    {"name": "data_preprocessing", "type": "transform"},
    {"name": "analysis",           "type": "analysis"},
    {"name": "synthesis",          "type": "synthesis"},
    {"name": "quality_check",      "type": "validation"},
    {"name": "output_generation",  "type": "output"},
]


def _make_tool_calls(tools: list[str], rng: random.Random, redundancy: float = 0.0) -> list[dict]:
    """도구 호출 목록 생성. redundancy = 중복 비율(0~1)"""
    calls = []
    for tool in tools:
        success = rng.random() > 0.1  # 90% 성공률
        calls.append({
            "name": tool,
            "tool_name": tool,
            "success": success,
            "execution_time": round(rng.uniform(0.05, 0.8), 3),
            "args": {"query": f"task_query_{tool}"},
        })
    # 중복 호출 추가
    if redundancy > 0 and calls:
        n_redundant = max(1, int(len(calls) * redundancy))
        for _ in range(n_redundant):
            dup = rng.choice(calls).copy()
            dup["redundant"] = True
            calls.append(dup)
    return calls


def _make_agent_interactions(agents: list[str], rng: random.Random, n: int = 3) -> list[dict]:
    """에이전트 간 상호작용 생성"""
    interactions = []
    for _ in range(n):
        from_a, to_a = rng.sample(agents, 2)
        interactions.append({
            "from_agent": from_a,
            "to_agent":   to_a,
            "type": rng.choice(["task_delegation", "result_sharing", "feedback", "coordination"]),
            "success": rng.random() > 0.08,
            "context": f"{from_a} → {to_a} 협업",
        })
    return interactions


def _make_chain_steps(steps: list[dict], rng: random.Random, fail_step: str | None = None) -> list[dict]:
    """워크플로우 단계 생성"""
    result = []
    for s in steps:
        is_bottleneck = s["name"] in ("data_retrieval", "analysis")
        success = False if s["name"] == fail_step else rng.random() > 0.12
        result.append({
            "name": s["name"],
            "type": s["type"],
            "success": success,
            "execution_time": round(rng.uniform(0.5, 3.0) * (3 if is_bottleneck else 1), 3),
            "metadata": {"bottleneck": is_bottleneck},
        })
    return result


# ────────────────────────────────────────────────────────────────────────────────
# 시나리오 정의
# ────────────────────────────────────────────────────────────────────────────────

# (scenario_name, tools_expected, tools_actual_pool, agents, has_workflow, retry, redundancy)
SCENARIOS = [
    # ─── 단일 에이전트 — 도구 선택 완벽 ───────────────────────────────────────
    ("simple_search",      ["web_search"],                      ["web_search"],                       ["researcher"],             False, 1, 0.0),
    ("data_lookup",        ["db_lookup", "data_query"],         ["db_lookup", "data_query"],          ["analyst"],                False, 1, 0.0),
    ("code_run",           ["code_executor"],                   ["code_executor"],                    ["analyst"],                False, 1, 0.0),
    ("classify_task",      ["classifier"],                      ["classifier"],                       ["analyst"],                False, 1, 0.0),
    # ─── 단일 에이전트 — 도구 선택 부정확 (낮은 F1) ────────────────────────────
    ("wrong_tool_1",       ["web_search"],                      ["doc_reader"],                       ["researcher"],             False, 1, 0.0),
    ("wrong_tool_2",       ["data_query", "chart_generator"],   ["db_lookup"],                        ["analyst"],                False, 2, 0.0),
    ("partial_match",      ["web_search", "summarizer"],        ["web_search", "doc_reader"],         ["researcher"],             False, 1, 0.0),
    # ─── 멀티 에이전트 — Hub 패턴 ──────────────────────────────────────────────
    ("research_hub",       ["web_search", "summarizer"],        ["web_search", "summarizer"],         ["orchestrator", "researcher", "writer"],       True, 1, 0.0),
    ("analysis_hub",       ["data_query", "chart_generator"],   ["data_query", "chart_generator"],    ["orchestrator", "analyst", "writer", "reviewer"], True, 1, 0.0),
    ("document_hub",       ["doc_reader", "summarizer", "report_writer"], ["doc_reader", "summarizer", "report_writer"], ["orchestrator", "researcher", "writer"], True, 1, 0.0),
    # ─── 멀티 에이전트 — Chain 패턴 ────────────────────────────────────────────
    ("chain_research",     ["web_search", "summarizer", "report_writer"], ["web_search", "summarizer", "report_writer"], ["researcher", "analyst", "writer"], True, 1, 0.0),
    ("chain_analysis",     ["data_query", "classifier", "chart_generator"], ["data_query", "classifier", "chart_generator"], ["analyst", "writer", "reviewer"], True, 1, 0.1),
    # ─── 재시도 시나리오 ───────────────────────────────────────────────────────
    ("retry_on_fail_1",    ["web_search"],                      ["web_search"],                       ["researcher"],             False, 2, 0.0),
    ("retry_on_fail_2",    ["code_executor", "data_query"],     ["code_executor", "data_query"],      ["analyst"],                False, 3, 0.0),
    ("retry_success",      ["db_lookup"],                       ["db_lookup"],                        ["analyst"],                True,  2, 0.0),
    # ─── 중복 호출 시나리오 ────────────────────────────────────────────────────
    ("redundant_calls_1",  ["web_search", "doc_reader"],        ["web_search", "doc_reader"],         ["researcher"],             False, 1, 0.5),
    ("redundant_calls_2",  ["data_query"],                      ["data_query"],                       ["analyst"],                False, 1, 1.0),
    # ─── 복잡한 멀티 에이전트 워크플로우 ──────────────────────────────────────
    ("complex_pipeline",   ["web_search", "data_query", "chart_generator", "report_writer"],
                           ["web_search", "data_query", "chart_generator", "report_writer"],
                           ["orchestrator", "researcher", "analyst", "writer", "reviewer"], True, 1, 0.0),
    ("ml_pipeline",        ["data_query", "code_executor", "classifier", "chart_generator"],
                           ["data_query", "code_executor", "classifier", "chart_generator"],
                           ["orchestrator", "analyst", "writer"],                          True, 1, 0.1),
    ("translation_chain",  ["doc_reader", "translator", "summarizer"],
                           ["doc_reader", "translator", "summarizer"],
                           ["researcher", "writer"],                                        True, 1, 0.0),
    # ─── 실패 포함 워크플로우 ──────────────────────────────────────────────────
    ("workflow_fail_1",    ["data_query", "analysis"],          ["data_query"],                       ["analyst"],                True, 1, 0.0),
    ("workflow_fail_2",    ["web_search", "summarizer"],        ["web_search"],                       ["researcher"],             True, 2, 0.0),
    # ─── 이메일/알림 에이전트 ─────────────────────────────────────────────────
    ("notification_flow",  ["db_lookup", "email_sender"],       ["db_lookup", "email_sender"],        ["orchestrator", "analyst"], True, 1, 0.0),
    ("image_analysis",     ["image_analyzer", "classifier"],    ["image_analyzer", "classifier"],     ["analyst"],                False, 1, 0.0),
    ("full_report",        ["web_search", "data_query", "summarizer", "chart_generator", "report_writer"],
                           ["web_search", "data_query", "summarizer", "chart_generator", "report_writer"],
                           ["orchestrator", "researcher", "analyst", "writer", "reviewer"], True, 1, 0.0),
]


def run_agentic_evaluation():
    print("\n" + "=" * 70)
    print("  에이전트 지표 평가 — Agent Evaluator")
    print("  Coverage: Tool Call · Retry · Tool Selection · Coordination · Workflow")
    print("=" * 70)

    rng = random.Random(2025)

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        output_dir=str(project_root / "results"),
    )

    base_time = datetime.now() - timedelta(hours=3)

    for idx, (name, expected_tools, actual_tools, agents, has_wf, attempts, redundancy) in enumerate(SCENARIOS):
        task_id = f"agent_{idx+1:03d}_{name}"

        # 도구 호출 생성
        tool_calls = _make_tool_calls(actual_tools, rng, redundancy)

        # 성공 여부 — 도구 미스매치가 있으면 확률적 실패
        tool_match = set(expected_tools) == set(actual_tools)
        success_prob = 0.92 if tool_match else (0.65 if set(expected_tools) & set(actual_tools) else 0.30)
        success = rng.random() < success_prob
        completion = round(rng.uniform(0.8, 1.0) if success else rng.uniform(0.3, 0.6), 3)
        accuracy = round(rng.uniform(0.75, 0.95) if success else rng.uniform(0.25, 0.55), 3)

        # 에이전트 상호작용 (멀티 에이전트)
        agent_interactions = None
        if len(agents) > 1:
            n_interactions = rng.randint(len(agents) - 1, len(agents) * 2)
            agent_interactions = _make_agent_interactions(agents, rng, n_interactions)

        # 워크플로우 단계
        chain_steps = None
        if has_wf:
            # 실패 워크플로우는 한 단계 실패
            fail_step = None if success else rng.choice([s["name"] for s in WORKFLOW_STEPS[1:]])
            steps_subset = WORKFLOW_STEPS[:rng.randint(4, len(WORKFLOW_STEPS))]
            chain_steps = _make_chain_steps(steps_subset, rng, fail_step)

        exec_time = round(rng.uniform(0.5, 8.0) * (1.5 if len(agents) > 2 else 1.0), 3)
        input_tokens = rng.randint(200, 2000)
        output_tokens = rng.randint(100, 1500)

        task = TaskResult(
            task_id=task_id,
            task_type="tool_use" if not has_wf else "planning",
            success=success,
            completion_score=completion,
            accuracy_score=accuracy,
            execution_time=exec_time,
            tokens_used={"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens},
            tool_calls=tool_calls,
            attempts=attempts,
            errors=[] if success else ["tool_mismatch" if not tool_match else "execution_error"],
            timestamp=base_time + timedelta(minutes=idx * 4),
            agent_interactions=agent_interactions,
            chain_steps=chain_steps,
            expected_tools=expected_tools,
            framework="crewai" if len(agents) > 1 else "langchain",
        )

        request_text = f"{name} 작업을 수행하세요"
        response_text = "작업이 완료되었습니다." if success else "작업 수행 중 오류가 발생했습니다."
        ground_truth_text = f"expected_result_{name}"

        monitor.record_task(
            task,
            ground_truth=ground_truth_text,
            context=ground_truth_text,
            request=request_text,
            response=response_text,
        )

        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=response_text,
            request=request_text,
            expected_elements=[ground_truth_text],
            ground_truth=ground_truth_text,
        )

        if has_wf:
            monitor.record_rag_metrics(
                faithfulness=round(min(accuracy * rng.uniform(0.80, 1.05), 1.0), 3),
                answer_relevancy=round(min(accuracy * rng.uniform(0.85, 1.10), 1.0), 3),
                context_precision=round(min(completion * rng.uniform(0.75, 1.00), 1.0), 3),
                context_recall=round(min(completion * rng.uniform(0.70, 1.05), 1.0), 3),
            )

    # ─── 추가: 직접 retry tracker 에 시나리오 등록 ───────────────────────────
    # record_task는 attempts>1이면 retry_tracker에 등록
    # 더 다양한 패턴을 위해 직접 등록도 추가
    extra_retry_cases = [
        ("retry_ext_001", [{"success": False, "duration": 1.2}, {"success": False, "duration": 1.5}, {"success": True, "duration": 0.9}]),
        ("retry_ext_002", [{"success": False, "duration": 2.0}, {"success": True, "duration": 1.1}]),
        ("retry_ext_003", [{"success": True, "duration": 0.7}]),
        ("retry_ext_004", [{"success": False, "duration": 3.0}, {"success": False, "duration": 2.5}, {"success": False, "duration": 2.0}]),
        ("retry_ext_005", [{"success": False, "duration": 1.0}, {"success": True, "duration": 0.8}]),
    ]
    for tid, log in extra_retry_cases:
        monitor.retry_tracker.track_attempts(tid, log)

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[A]_agentic_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)

    # ─── 결과 출력 ────────────────────────────────────────────────────────────
    eff_data    = report.efficiency_metrics.get("tool_efficiency", {})
    retry_data  = report.efficiency_metrics.get("retries", {})

    tool_sel    = monitor.tool_selection_tracker.get_accuracy_stats()
    coord       = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow    = monitor.workflow_tracker.calculate_execution_success_rate()

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개  (+{len(extra_retry_cases)} retry 직접 등록)")
    print(f"  저장 위치: {saved_path}")

    print(f"\n  [Tool Call Analysis]")
    if eff_data:
        print(f"    효율성 점수:   {eff_data.get('avg_efficiency_score', 0):.1f}/100")
        print(f"    중복 호출률:   {eff_data.get('redundancy_rate', 0):.1f}%")
        print(f"    실패율:        {eff_data.get('failure_rate', 0):.1f}%")
        print(f"    총 호출:       {eff_data.get('total_calls', 0)}회")

    print(f"\n  [Tool Selection Accuracy — F1]")
    if tool_sel:
        print(f"    Precision:     {tool_sel.get('avg_precision', 0):.1f}%")
        print(f"    Recall:        {tool_sel.get('avg_recall', 0):.1f}%")
        print(f"    F1 Score:      {tool_sel.get('avg_f1_score', tool_sel.get('avg_accuracy', 0)):.1f}%")
        print(f"    평가 태스크:   {tool_sel.get('total_evaluations', 0)}개")

    print(f"\n  [Agent Coordination]")
    if coord:
        patterns = monitor.agent_coordination_tracker.get_interaction_patterns()
        print(f"    협업 점수:     {coord.get('score', 0):.2f}/10")
        print(f"    성공률:        {coord.get('success_rate', 0):.1f}%")
        print(f"    총 상호작용:   {coord.get('total_interactions', 0)}회")
        print(f"    에이전트 수:   {coord.get('unique_agents', 0)}개")
        print(f"    패턴:          {patterns.get('pattern_type', 'N/A')}")

    print(f"\n  [Workflow Execution]")
    if workflow:
        print(f"    단계 성공률:   {workflow.get('step_success_rate', 0):.1f}%")
        print(f"    태스크 성공률: {workflow.get('task_success_rate', 0):.1f}%")
        print(f"    총 단계:       {workflow.get('total_steps', 0)}개")
        print(f"    성공 단계:     {workflow.get('successful_steps', 0)}개")

    print(f"\n  [Retry & Correction]")
    if retry_data:
        print(f"    재시도율:      {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률: {retry_data.get('first_attempt_success_rate', 0):.1f}%")
        print(f"    수정 성공률:   {retry_data.get('correction_success_rate', 0):.1f}%")

    if report.alerts:
        print(f"\n  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:3]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")

    print(f"{'─'*70}\n")
    return saved_path


if __name__ == "__main__":
    run_agentic_evaluation()
