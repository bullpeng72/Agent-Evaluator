from __future__ import annotations

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
    python 03_agentic_eval.py
"""

import json
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TestTransparencyManager,
    AnnotationType,
    TestStepStatus,
)
from agent_evaluator.reporting import generate_comprehensive_html_report


def _load_golden(filename: str) -> list:
    path = project_root / "results" / "golden_datasets" / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

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

# 도구별 권한 레벨 (privilege_level) — 보안 대시보드 연동
_TOOL_PRIVILEGES: dict[str, str] = {
    "web_search": "read",   "doc_reader": "read",    "data_query": "read",
    "db_lookup": "read",    "summarizer": "read",    "classifier": "read",
    "translator": "read",   "image_analyzer": "read",
    "chart_generator": "write", "report_writer": "write", "email_sender": "write",
    "code_executor": "execute",
}

# 도구별 대표 실행 결과 (execution_result) — 성공 시 표시
_TOOL_RESULTS: dict[str, str] = {
    "web_search":      "검색 완료: 관련 문서 12건 반환",
    "doc_reader":      "문서 로드 완료: 37페이지, 12,450 토큰",
    "data_query":      "쿼리 완료: 8,234건 레코드 반환",
    "code_executor":   "실행 완료: exit_code=0, 결과값 반환",
    "summarizer":      "요약 완료: 원문 4,200자 → 요약 380자",
    "classifier":      "분류 완료: 긍정 0.94 / 부정 0.04 / 중립 0.02",
    "translator":      "번역 완료: 영→한 2,100자, BLEU 0.87",
    "image_analyzer":  "이미지 분석: 객체 7개 탐지, 신뢰도 0.93",
    "chart_generator": "차트 생성: PNG 1,024×768, 3종 시각화",
    "report_writer":   "보고서 저장: report_20240315.pdf, 24페이지",
    "email_sender":    "이메일 발송 완료: 수신자 127명, 성공률 99.2%",
    "db_lookup":       "DB 조회: 사용자 레코드 3건 반환",
}

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
    """도구 호출 목록 생성. redundancy = 중복 비율(0~1)

    각 tool call dict 필드:
      tool_name        — 도구 식별자 (프레임워크 통합 표준 필드명)
      success          — 실행 성공 여부
      duration         — 실행 소요 시간(초) ← 프레임워크 통합의 실제 필드명
      parameters       — 입력 파라미터 dict ← 표준 필드명 (args/input 아님)
      privilege_level  — read/write/execute (보안 대시보드 연동)
      execution_result — 성공 시 실행 결과 텍스트
      error            — 실패 시 오류 메시지
    """
    calls = []
    for tool in tools:
        success = rng.random() > 0.1  # 90% 성공률
        dur = round(rng.uniform(0.05, 0.8), 3)
        calls.append({
            "tool_name":        tool,
            "success":          success,
            "duration":         dur,
            "parameters":       {"query": f"task_query_{tool}", "timeout": 30},
            "privilege_level":  _TOOL_PRIVILEGES.get(tool, "read"),
            "execution_result": _TOOL_RESULTS.get(tool, f"{tool} 실행 완료") if success else None,
            "error":            None if success else f"{tool} 실행 실패: 응답 타임아웃 ({dur:.2f}s 초과)",
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
# 시나리오 데이터 — 골든 데이터셋에서 로드
# (results/golden_datasets/agentic_tool_selection.json)
# ────────────────────────────────────────────────────────────────────────────────

_raw_agentic = _load_golden("agentic_tool_selection.json")
SCENARIOS = [
    (d["name"], d["expected_tools"], d["actual_tools"], d["agents"],
     d["has_workflow"], d["retry_count"], d["redundancy"])
    for d in _raw_agentic
]
_SCENARIO_CONTENT = {
    d["name"]: (d["request"], d["response_ok"], d["response_fail"],
                d["ground_truth"], d["expected_elements"])
    for d in _raw_agentic
}

def run_agentic_evaluation():
    print("\n" + "=" * 70)
    print("  에이전트 지표 평가 — Agent Evaluator")
    print("  Coverage: Tool Call · Retry · Tool Selection · Coordination · Workflow")
    print("=" * 70)

    rng = random.Random(2025)

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        enable_transparency=True,
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

        _content = _SCENARIO_CONTENT.get(name, _SCENARIO_CONTENT["simple_search"])
        request_text, resp_ok, resp_fail, ground_truth_text, expected_elems = _content
        response_text = resp_ok if success else resp_fail

        monitor.record_task(
            task,
            ground_truth=ground_truth_text,
            context=ground_truth_text,
            request=request_text,
            response=response_text,
        )

        # Response Quality — 5차원 품질 평가 (성공 시 expected_elements 기반)
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=response_text,
            request=request_text,
            expected_elements=expected_elems if success else [],
            ground_truth=ground_truth_text,
        )

        # Accuracy — ground_truth 대비 정확도 명시적 평가
        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=ground_truth_text,
            prediction=response_text,
            task_type=task.task_type,
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
        ("retry_ext_001", [
            {"success": False, "retry_reason": "ValueError: answer format mismatch", "duration": 1.2},
            {"success": False, "retry_reason": "ValueError: answer format mismatch", "duration": 1.5},
            {"success": True,  "retry_reason": "", "duration": 0.9},
        ], "qa"),
        ("retry_ext_002", [
            {"success": False, "retry_reason": "TimeoutError: LLM response exceeded 5s", "duration": 2.0},
            {"success": True,  "retry_reason": "", "duration": 1.1},
        ], "reasoning"),
        ("retry_ext_003", [
            {"success": True, "retry_reason": "", "duration": 0.7},
        ], "qa"),
        ("retry_ext_004", [
            {"success": False, "retry_reason": "ToolError: web_search rate limit exceeded", "duration": 3.0},
            {"success": False, "retry_reason": "ToolError: web_search rate limit exceeded", "duration": 2.5},
            {"success": False, "retry_reason": "ToolError: connection reset by peer", "duration": 2.0},
        ], "tool_use"),
        ("retry_ext_005", [
            {"success": False, "retry_reason": "ParseError: JSON decode failed", "duration": 1.0},
            {"success": True,  "retry_reason": "", "duration": 0.8},
        ], "reasoning"),
    ]
    for tid, log, ttype in extra_retry_cases:
        monitor.retry_tracker.track_attempts(tid, log, task_type=ttype)

    # ─── 추가: ToolCallAnalyzer 직접 호출 — 효율성 점수 케이스별 검증 ──────────
    # record_task는 tool_calls 필드가 있으면 analyze_execution()을 자동 호출하지만
    # 아래처럼 직접 호출하면 반환된 dict에서 케이스별 점수를 직접 확인할 수 있다.
    direct_tool_cases = [
        # (task_id, tool_calls, 설명)
        # 정상 단일 호출 — 효율성 100에 가까워야 함
        ("tool_direct_001",
         [{"tool_name": "web_search", "success": True, "duration": 0.3,
           "parameters": {"query": "latest AI news"}, "privilege_level": "read",
           "execution_result": "검색 완료: 관련 문서 12건", "error": None}],
         "단일 성공 호출 (효율성 최고)"),
        # 중복 없는 3-도구 체인
        ("tool_direct_002",
         [{"tool_name": "data_query",     "success": True,  "duration": 0.5,
           "parameters": {"query": "SELECT * FROM sales"}, "privilege_level": "read",
           "execution_result": "8,234건 반환", "error": None},
          {"tool_name": "classifier",     "success": True,  "duration": 0.4,
           "parameters": {"text": "sales data"}, "privilege_level": "read",
           "execution_result": "분류 완료: 긍정 0.94", "error": None},
          {"tool_name": "chart_generator","success": True,  "duration": 0.6,
           "parameters": {"data": "sales_q4"}, "privilege_level": "write",
           "execution_result": "차트 생성: 3종 PNG", "error": None}],
         "3-도구 체인, 중복 없음"),
        # 중복 호출 포함 — 효율성 낮아야 함
        ("tool_direct_003",
         [{"tool_name": "web_search", "success": True,  "duration": 0.3,
           "parameters": {"query": "AI trends"}, "privilege_level": "read",
           "execution_result": "검색 완료", "error": None},
          {"tool_name": "web_search", "success": True,  "duration": 0.3,  # 중복
           "parameters": {"query": "AI trends"}, "privilege_level": "read",
           "execution_result": "검색 완료", "error": None},
          {"tool_name": "summarizer", "success": True,  "duration": 0.4,
           "parameters": {"text": "results"}, "privilege_level": "read",
           "execution_result": "요약 완료", "error": None}],
         "web_search 중복 호출"),
        # 실패 포함 — 효율성 낮아야 함
        ("tool_direct_004",
         [{"tool_name": "code_executor", "success": False, "duration": 2.0,
           "parameters": {"code": "import heavy_lib"}, "privilege_level": "execute",
           "execution_result": None, "error": "ImportError: No module named 'heavy_lib'"},
          {"tool_name": "code_executor", "success": False, "duration": 2.5,
           "parameters": {"code": "import heavy_lib"}, "privilege_level": "execute",
           "execution_result": None, "error": "ImportError: No module named 'heavy_lib'"},
          {"tool_name": "code_executor", "success": True,  "duration": 1.2,
           "parameters": {"code": "print('hello')"}, "privilege_level": "execute",
           "execution_result": "실행 완료: exit_code=0", "error": None}],
         "2회 실패 후 성공"),
        # 완전 실패 체인
        ("tool_direct_005",
         [{"tool_name": "db_lookup",  "success": False, "duration": 1.0,
           "parameters": {"id": "user_999"}, "privilege_level": "read",
           "execution_result": None, "error": "ConnectionError: DB 연결 실패 (1.0s)"},
          {"tool_name": "data_query", "success": False, "duration": 1.5,
           "parameters": {"query": "SELECT * FROM users"}, "privilege_level": "read",
           "execution_result": None, "error": "TimeoutError: 쿼리 타임아웃 (1.5s)"}],
         "전체 실패 체인"),
        # 빈 호출 — 효율성 100 반환해야 함
        ("tool_direct_006",
         [],
         "도구 호출 없음 (효율성 100)"),
    ]

    print(f"\n  [직접 ToolCallAnalyzer 호출 — 케이스별 효율성 점수]")
    for tid, calls, desc in direct_tool_cases:
        result = monitor.tool_analyzer.analyze_execution(tid, calls)
        score       = result.get("efficiency_score", 0)
        total_calls = result.get("total_calls", 0)
        redundant   = result.get("redundant_calls", 0)
        failed      = result.get("failed_calls", 0)
        flag = "🟢" if score >= 80 else ("🟡" if score >= 50 else "🔴")
        print(f"    {flag} {tid}: score={score:.1f}/100  calls={total_calls}  "
              f"dup={redundant}  fail={failed}  ({desc})")

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[A]_agentic_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)
    html_path = Path(saved_path).with_suffix('.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"📄 HTML 리포트 저장: {html_path}")

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

    # ─── 검증 테이블 ─────────────────────────────────────────────────────────
    eff_score    = eff_data.get("avg_efficiency_score", 0) if eff_data else 0
    redundancy   = eff_data.get("redundancy_rate", 0) if eff_data else 0
    tool_f1      = tool_sel.get("avg_f1_score", tool_sel.get("avg_accuracy", 0)) if tool_sel else 0
    coord_score  = coord.get("score", 0) if coord else 0
    coord_suc    = coord.get("success_rate", 0) if coord else 0
    wf_step_suc  = workflow.get("step_success_rate", 0) if workflow else 0
    wf_task_suc  = workflow.get("task_success_rate", 0) if workflow else 0
    retry_m      = monitor.retry_tracker.get_retry_metrics()
    first_suc    = retry_m.get("first_attempt_success_rate", 0)

    # direct_tool_cases 검증: 중복 호출 케이스(003)의 효율성이 정상 케이스(001)보다 낮아야 함
    res_normal   = monitor.tool_analyzer.analyze_execution("val_normal",
        [{"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3}])
    res_dup      = monitor.tool_analyzer.analyze_execution("val_dup",
        [{"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3},
         {"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3}])
    dup_separation = res_normal.get("efficiency_score", 0) > res_dup.get("efficiency_score", 0)

    checks = [
        #  항목                               기준           실제값                     통과
        ("Tool Call 효율성 점수",             "> 50/100",  f"{eff_score:.1f}",          eff_score > 50),
        ("중복 호출률",                        "< 30%",     f"{redundancy:.1f}%",        redundancy < 30.0),
        ("Tool Selection F1",                 "> 50%",     f"{tool_f1:.1f}%",           tool_f1 > 50.0),
        ("Agent Coordination 점수",           "> 5/10",    f"{coord_score:.2f}",        coord_score > 5.0),
        ("Agent Coordination 성공률",         "> 70%",     f"{coord_suc:.1f}%",         coord_suc > 70.0),
        ("Workflow 단계 성공률",              "> 70%",     f"{wf_step_suc:.1f}%",       wf_step_suc > 70.0),
        ("Workflow 태스크 성공률",            "> 50%",     f"{wf_task_suc:.1f}%",       wf_task_suc > 50.0),
        ("첫시도 성공률 (직접 retry 포함)",   "> 5%",      f"{first_suc:.1f}%",         first_suc > 5.0),
        ("중복 호출 효율성 점수 분리",         "정상>중복", str(dup_separation),         dup_separation),
    ]

    print(f"\n  {'═'*66}")
    print(f"  {'검증 항목':<32} {'기준':<12} {'실측값':<12} {'결과'}")
    print(f"  {'─'*66}")
    pass_cnt = 0
    for name, threshold, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok: pass_cnt += 1
        print(f"  {name:<32} {threshold:<12} {actual:<12} {mark}")
    print(f"  {'═'*66}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    print(f"{'─'*70}\n")
    return saved_path


def run_tool_selection_golden_demo():
    """
    Golden Dataset 파일 기반 Tool Selection 정확도 평가 데모
    ─────────────────────────────────────────────────────────
    results/golden_datasets/agentic_tool_selection.json 을 로드하고
    ToolSelectionTracker 로 F1 기반 정확도를 측정합니다.

    각 항목의 expected_tools 와 시뮬레이션 agent 가 반환하는
    actual_tools 를 비교합니다.
    """
    import json

    print("\n" + "=" * 70)
    print("  Tool Selection Golden Dataset 평가 데모")
    print("  파일: results/golden_datasets/agentic_tool_selection.json")
    print("=" * 70)

    golden_path = project_root / "results" / "golden_datasets" / "agentic_tool_selection.json"
    if not golden_path.exists():
        print(f"\n⚠️  Golden Dataset 파일이 없습니다: {golden_path}")
        return

    with open(golden_path, encoding="utf-8") as f:
        golden_items = json.load(f)

    rng = random.Random(7777)
    monitor = PerformanceMonitor(output_dir=str(project_root / "results"))

    print(f"\n  총 {len(golden_items)}개 시나리오 평가 중...\n")

    for item in golden_items:
        task_id = f"golden_{item['name']}"
        expected = item["expected_tools"]

        # 시뮬레이션: 난이도에 따라 도구 선택 정확도 조절
        difficulty = item.get("difficulty", "medium")
        if difficulty == "easy":
            match_prob = 0.95
        elif difficulty == "medium":
            match_prob = 0.80
        else:  # hard
            match_prob = 0.65

        # 실제 도구 = expected를 기반으로 일부 추가/제거 (시뮬레이션)
        actual = list(expected)
        if rng.random() > match_prob:
            # 일부 도구를 잘못 선택
            all_available = list(ALL_TOOLS)
            wrong = rng.choice([t for t in all_available if t not in expected])
            if actual:
                actual[-1] = wrong  # 마지막 도구를 잘못된 도구로 교체

        success = set(actual) == set(expected)
        completion = 1.0 if success else rng.uniform(0.4, 0.8)

        tool_calls = [
            {"name": t, "tool_name": t, "success": True, "execution_time": rng.uniform(0.1, 0.5)}
            for t in actual
        ]

        task = TaskResult(
            task_id=task_id,
            task_type=item.get("task_type", "tool_use"),
            success=success,
            completion_score=round(completion, 3),
            accuracy_score=round(completion, 3),
            execution_time=round(rng.uniform(0.5, 5.0), 3),
            tokens_used={"input": rng.randint(100, 500), "output": rng.randint(50, 300), "total": 0},
            tool_calls=tool_calls,
            attempts=1,
            errors=[] if success else ["wrong_tool_selected"],
            timestamp=datetime.now(),
            expected_tools=expected,
            framework="crewai",
        )
        task.tokens_used["total"] = task.tokens_used["input"] + task.tokens_used["output"]

        monitor.record_task(
            task,
            ground_truth=item["ground_truth"],
            request=item["request"],
            response="작업 완료" if success else "도구 선택 오류",
        )

        # Tool Selection Tracker 에 직접 등록
        monitor.tool_selection_tracker.evaluate_selection(
            task_id=task_id,
            expected_tools=expected,
            actual_tools=actual,
        )

        match_icon = "✅" if success else "⚠️ "
        print(f"  {match_icon} {item['name']:<20} expected={expected}  actual={actual}")

    # 결과 출력
    tool_sel = monitor.tool_selection_tracker.get_accuracy_stats()
    print(f"\n{'─'*70}")
    print(f"  [Tool Selection 골든 데이터셋 평가 결과]")
    if tool_sel:
        print(f"    Precision : {tool_sel.get('avg_precision', 0):.1f}%")
        print(f"    Recall    : {tool_sel.get('avg_recall', 0):.1f}%")
        print(f"    F1 Score  : {tool_sel.get('avg_f1_score', tool_sel.get('avg_accuracy', 0)):.1f}%")
        print(f"    평가 건수 : {tool_sel.get('total_evaluations', 0)}건")
    print(f"{'─'*70}\n")


def run_transparency_demo(monitor: PerformanceMonitor, saved_path: str):
    """
    투명성 데모 — Traces / Annotations / Audit Log 생성
    ────────────────────────────────────────────────────
    TestTransparencyManager를 사용해 평가 계산 과정을 추적하고
    어노테이션·감사 로그를 남깁니다.

    생성 파일:
      results/traces/          → 지표 계산 단계별 트레이스 JSON
      results/annotations/     → 검토 메모·경고 JSON
      results/audit_logs/      → 이벤트 감사 로그 JSON
    """
    print("\n" + "=" * 70)
    print("  투명성 데모 — Traces · Annotations · Audit Log")
    print("=" * 70)

    results_dir = str(project_root / "results")
    tm = TestTransparencyManager(output_dir=results_dir)

    report = monitor.generate_report()
    tool_sel = monitor.tool_selection_tracker.get_accuracy_stats()
    coord    = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow = monitor.workflow_tracker.calculate_execution_success_rate()

    # ── 1. Traces: 주요 지표 계산 과정 기록 ──────────────────────────────────

    # (1a) Tool Selection F1 트레이스
    f1_score = tool_sel.get("avg_f1_score", tool_sel.get("avg_accuracy", 0))
    trace_id = tm.start_metric_calculation(
        metric_name="tool_selection_f1",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="collect_selections",
        description="전체 태스크의 expected/actual tool 목록 수집",
        input_data={"total_tasks": report.total_tasks},
        output_data={"evaluations": tool_sel.get("total_evaluations", 0)},
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="compute_precision_recall",
        description="각 태스크별 Precision·Recall 계산 후 평균",
        input_data={"method": "set_intersection / union"},
        output_data={
            "avg_precision": tool_sel.get("avg_precision", 0),
            "avg_recall":    tool_sel.get("avg_recall", 0),
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="compute_f1",
        description="F1 = 2 × (Precision × Recall) / (Precision + Recall)",
        input_data={
            "precision": tool_sel.get("avg_precision", 0),
            "recall":    tool_sel.get("avg_recall", 0),
        },
        output_data={"f1_score": round(f1_score, 2)},
        status=TestStepStatus.SUCCESS,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id,
        final_value=round(f1_score, 2),
        metadata={"unit": "%", "threshold": 70.0},
    )

    # (1b) Agent Coordination 트레이스
    coord_score = coord.get("score", 0) if coord else 0
    trace_id2 = tm.start_metric_calculation(
        metric_name="agent_coordination_score",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id2,
        step_name="collect_interactions",
        description="멀티 에이전트 상호작용 목록 수집",
        input_data={"agents": list(AGENTS.keys())},
        output_data={
            "total_interactions": coord.get("total_interactions", 0) if coord else 0,
            "unique_agents":      coord.get("unique_agents", 0) if coord else 0,
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id2,
        step_name="score_coordination",
        description="성공률·다양성·패턴 기반 0-10 점수 산출",
        input_data={"success_rate": coord.get("success_rate", 0) if coord else 0},
        output_data={"score": round(coord_score, 2)},
        status=TestStepStatus.SUCCESS,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id2,
        final_value=round(coord_score, 2),
        metadata={"unit": "/10", "threshold": 7.0},
    )

    # (1c) Workflow Execution 트레이스
    step_success = workflow.get("step_success_rate", 0) if workflow else 0
    trace_id3 = tm.start_metric_calculation(
        metric_name="workflow_step_success_rate",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id3,
        step_name="collect_steps",
        description="워크플로우 전체 단계 수집",
        input_data={"workflows": len(WORKFLOW_STEPS)},
        output_data={
            "total_steps":      workflow.get("total_steps", 0) if workflow else 0,
            "successful_steps": workflow.get("successful_steps", 0) if workflow else 0,
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id3,
        step_name="identify_bottlenecks",
        description="실행 시간 상위 단계 병목 탐지",
        input_data={"bottleneck_steps": ["data_retrieval", "analysis"]},
        output_data={"step_success_rate": round(step_success, 2)},
        status=TestStepStatus.SUCCESS if step_success >= 80 else TestStepStatus.FAILED,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id3,
        final_value=round(step_success, 2),
        metadata={"unit": "%", "threshold": 85.0},
    )

    # ── 2. Annotations: 주목할 점 기록 ───────────────────────────────────────

    # 낮은 F1 경고
    if f1_score < 70:
        ann_id = tm.add_annotation(
            target_type="metric",
            target_id="tool_selection_f1",
            annotation_type=AnnotationType.WARNING,
            priority="high",
            title=f"Tool Selection F1 낮음 ({f1_score:.1f}%)",
            content=(
                f"Tool Selection F1이 {f1_score:.1f}%로 임계값(70%) 미달입니다. "
                "wrong_tool_* 시나리오에서 도구 미스매치가 빈번하게 발생했습니다. "
                "에이전트 도구 선택 로직 개선이 필요합니다."
            ),
            author="evaluator",
            metadata={"threshold": 70.0, "actual": round(f1_score, 2)},
        )
        tm.add_reply_to_annotation(
            annotation_id=ann_id,
            author="reviewer",
            content="wrong_tool_1, wrong_tool_2 시나리오 우선 검토 권장.",
        )

    # 워크플로우 병목 노트
    tm.add_annotation(
        target_type="metric",
        target_id="workflow_execution",
        annotation_type=AnnotationType.NOTE,
        priority="medium",
        title="data_retrieval · analysis 단계 병목 확인됨",
        content=(
            "워크플로우에서 data_retrieval·analysis 단계의 실행 시간이 "
            "다른 단계 대비 최대 3배 높습니다. "
            "병렬 실행 또는 캐싱 전략 도입을 검토하세요."
        ),
        author="evaluator",
    )

    # 전체 개선 제안
    tm.add_annotation(
        target_type="evaluation",
        target_id="agentic_metrics_run",
        annotation_type=AnnotationType.IMPROVEMENT,
        priority="low",
        title="redundant_calls 시나리오 — 중복 호출 제거 가능",
        content=(
            "redundant_calls_1·2 시나리오에서 동일 도구를 2회 이상 호출합니다. "
            "Tool Call Analyzer의 중복 탐지 결과를 에이전트 피드백 루프에 반영하면 "
            "토큰 비용과 실행 시간을 줄일 수 있습니다."
        ),
        author="evaluator",
    )

    # ── 3. Audit Log: 에이전틱 전용 세부 지표 (자동 생성 lifecycle 이벤트와 별개) ──

    tm.log_event(
        event_type="evaluation_started",
        user="evaluator",
        action="에이전틱 지표 평가 세션 시작",
        target_type="monitor",
        target_id="agentic_metrics_run",
        details={"scenarios": len(SCENARIOS), "trackers": ["tool_call", "tool_selection", "coordination", "workflow", "retry"]},
        success=True,
    )
    tm.log_event(
        event_type="report_generated",
        user="evaluator",
        action="평가 리포트 생성",
        target_type="report",
        target_id="agentic_metrics_run",
        details={
            "total_tasks":      report.total_tasks,
            "tool_selection_f1": round(f1_score, 2),
            "coord_score":       round(coord_score, 2),
            "step_success_rate": round(step_success, 2),
        },
        success=True,
    )
    tm.log_event(
        event_type="file_saved",
        user="evaluator",
        action="결과 파일 저장",
        target_type="file",
        target_id=str(saved_path),
        details={"format": "json", "path": str(saved_path)},
        success=bool(saved_path),
    )

    # ── 결과 요약 출력 ────────────────────────────────────────────────────────
    summary = tm.get_transparency_summary()
    print(f"\n  [Transparency 생성 결과]")
    print(f"    Traces     : {summary.get('total_traces', 0)}개  → {results_dir}/traces/")
    print(f"    Annotations: {summary.get('total_annotations', 0)}개  → {results_dir}/annotations/")
    print(f"    Audit Logs : {summary.get('total_audit_logs', 0)}개  → {results_dir}/audit_logs/")
    print(f"\n  대시보드 '투명성' 탭에서 Traces · Annotations · Audit Log를 확인하세요.")
    print(f"{'─'*70}\n")


if __name__ == "__main__":
    # enable_transparency=True → save_to_file() 시 Traces·Audit Log 자동 생성
    saved_path = run_agentic_evaluation()
    run_tool_selection_golden_demo()
    # Annotations 데모 (수동 입력 예시 — dashboard UI로도 작성 가능)
    _demo_monitor = PerformanceMonitor(output_dir=str(project_root / "results"))
    run_transparency_demo(_demo_monitor, saved_path)
