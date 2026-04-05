"""
21_layer2_agentic_eval.py
==========================
Layer 2 Agentic Metrics 활성화 가이드.

Layer 2 트래커는 TaskResult 에 특정 필드가 채워져 있을 때만 자동 활성화된다.
이 예제는 각 트래커를 활성화하는 방법을 3가지 방식으로 설명한다.

  A. agent_eval + get_eval_ctx()  — 실행 중에 컨텍스트에서 직접 채움
  B. agent_eval + EvalMetadata    — 응답 객체에서 메타데이터 수동 주입
  C. framework= 파라미터           — 프레임워크 응답에서 자동 추출

Layer 2 트래커별 활성화 필드:
  ┌────────────────────────────┬──────────────────────────────────────────────┐
  │ 트래커                     │ 활성화 필드 (TaskResult)                      │
  ├────────────────────────────┼──────────────────────────────────────────────┤
  │ ToolCallAnalyzer           │ tool_calls (list, len > 0)                   │
  │ ToolSelectionTracker       │ tool_calls + expected_tools                  │
  │ RetryCorrectionTracker     │ attempts > 1                                 │
  │ WorkflowExecutionTracker   │ chain_steps (list, len > 0)                  │
  │ AgentCoordinationTracker   │ agent_interactions (list, len > 0)           │
  └────────────────────────────┴──────────────────────────────────────────────┘

실행 방법:
    pip install "agent-evaluator[dev]"
    python 21_layer2_agentic_eval.py
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.decorators import agent_eval, get_eval_ctx, EvalMetadata

# ---------------------------------------------------------------------------
# 공통 모니터 설정
# ---------------------------------------------------------------------------

monitor = PerformanceMonitor(output_dir="results/layer2/")


# ===========================================================================
# A. get_eval_ctx() 로 실행 중에 직접 채우기
# ---------------------------------------------------------------------------
# agent_eval 래퍼가 실행되는 동안 get_eval_ctx() 로 현재 태스크 컨텍스트를
# 가져와서 tool_calls, chain_steps, agent_interactions 를 추가한다.
# ===========================================================================

print("=" * 60)
print("A. get_eval_ctx() 직접 주입 방식")
print("=" * 60)


@agent_eval(monitor, task_type="tool_use")
def tool_agent_with_ctx(question: str, ground_truth: str = "") -> str:
    """tool_calls, chain_steps 를 get_eval_ctx() 로 주입."""
    ctx = get_eval_ctx()

    # 도구 호출 시뮬레이션
    ctx.add_tool_call("web_search", {"query": question}, "검색 결과 반환")
    ctx.add_tool_call("calculator", {"expr": "42+1"}, "43")

    # 추론 단계 (chain_steps → WorkflowExecutionTracker 활성)
    ctx.add_chain_step("질문 파싱", "입력에서 핵심 쿼리 추출 완료")
    ctx.add_chain_step("검색 실행", "상위 3개 문서 검색")
    ctx.add_chain_step("답변 합성", "검색 결과 기반 최종 답변 생성")

    # 에이전트 간 상호작용 (agent_interactions → AgentCoordinationTracker 활성)
    ctx.add_agent_interaction(
        from_agent="orchestrator",
        to_agent="search_agent",
        message_type="task_delegation",
        content={"task": question},
    )

    time.sleep(0.05)
    return "43"


result = tool_agent_with_ctx("42+1은?", ground_truth="43")
print(f"  결과: {result}")
print()


# ===========================================================================
# B. EvalMetadata 반환 방식
# ---------------------------------------------------------------------------
# 함수가 (answer, EvalMetadata) 튜플을 반환하면 agent_eval이 자동으로
# 메타데이터를 TaskResult 에 적용한다. 외부 호출자가 응답 객체를 직접 조작할
# 수 없는 경우에 유용하다.
# ===========================================================================

print("=" * 60)
print("B. EvalMetadata 튜플 반환 방식")
print("=" * 60)


@agent_eval(monitor, task_type="planning")
def multi_agent_planner(question: str, ground_truth: str = "") -> Any:
    """(answer, EvalMetadata) 튜플로 에이전트 상호작용 메타데이터 주입."""
    time.sleep(0.08)

    meta = EvalMetadata(
        tool_calls=[
            {"tool_name": "web_search", "arguments": {"q": question}, "result": "result1"},
            {"tool_name": "summarizer", "arguments": {"text": "..."}, "result": "summary"},
        ],
        chain_steps=[
            {"step": "planning", "description": "하위 태스크 분해"},
            {"step": "execution", "description": "각 에이전트에 태스크 위임"},
            {"step": "aggregation", "description": "결과 수집 및 합성"},
        ],
        agent_interactions=[
            {
                "from_agent": "planner",
                "to_agent": "researcher",
                "message_type": "task_assignment",
                "content": question,
            },
            {
                "from_agent": "researcher",
                "to_agent": "planner",
                "message_type": "result_report",
                "content": "research_done",
            },
        ],
        tokens_used={"input": 210, "output": 85, "total": 295},
    )
    return "계획 완료", meta


result = multi_agent_planner("AI 에이전트 시스템 설계 방법은?", ground_truth="계획 완료")
print(f"  결과: {result}")
print()


# ===========================================================================
# C. expected_tools 로 ToolSelectionTracker 활성화
# ---------------------------------------------------------------------------
# expected_tools_arg 를 지정하면 ToolSelectionTracker 가 F1 기반 도구
# 선택 정확도를 계산한다. 함수 인자로 expected_tools 를 받아야 한다.
# ===========================================================================

print("=" * 60)
print("C. expected_tools 로 ToolSelectionTracker 활성화")
print("=" * 60)


@agent_eval(
    monitor,
    task_type="tool_use",
    expected_tools_arg="expected_tools",
)
def tool_selector(
    question: str,
    expected_tools: Optional[List[str]] = None,
    ground_truth: str = "",
) -> Any:
    """expected_tools 를 받아 ToolSelectionTracker F1 계산을 활성화."""
    ctx = get_eval_ctx()

    # 실제로 사용한 도구 기록
    ctx.add_tool_call("web_search", {"q": question}, "OK")
    ctx.add_tool_call("calculator", {}, "OK")
    # "summarizer" 는 expected 에 있지만 사용하지 않음 → recall 감소
    # "calculator" 는 expected 에 없지만 사용함 → precision 감소

    time.sleep(0.03)
    return "answered"


result = tool_selector(
    "검색 후 요약해줘",
    expected_tools=["web_search", "summarizer"],
    ground_truth="answered",
)
print(f"  결과: {result}")
print()


# ===========================================================================
# D. attempts > 1 로 RetryCorrectionTracker 활성화
# ---------------------------------------------------------------------------
# create_taskresult() 로 직접 TaskResult 를 생성하여 record_task() 에 넘기면
# attempts 필드로 재시도 동작을 기록할 수 있다.
# ===========================================================================

print("=" * 60)
print("D. attempts > 1 로 RetryCorrectionTracker 활성화")
print("=" * 60)

retry_task = create_taskresult(
    task_id="retry_demo_001",
    question="분산 시스템의 CAP 정리를 설명해줘",
    response="CAP 정리: Consistency, Availability, Partition tolerance 중 두 가지만 보장 가능",
    ground_truth="CAP",
    execution_time=1.5,
    task_type="qa",
    attempts=3,                # 3회 시도 → RetryCorrectionTracker 활성
    errors=["timeout", "invalid_response"],  # 에러 기록
)

monitor.record_task(retry_task)
print(f"  TaskResult(attempts=3) 기록 완료: {retry_task.task_id}")
print()


# ===========================================================================
# E. Framework 어댑터를 통한 자동 추출
# ---------------------------------------------------------------------------
# framework="langchain" / "langgraph" / "openai" / "anthropic" 등으로 지정하면
# 해당 프레임워크의 응답 객체에서 자동으로 메타데이터를 추출한다.
# 실제 SDK 없이 mock 객체로 동작을 확인한다.
# ===========================================================================

print("=" * 60)
print("E. Framework 어댑터 자동 추출 (mock)")
print("=" * 60)


@agent_eval(monitor, task_type="tool_use", framework="openai")
def openai_style_agent(question: str, ground_truth: str = "") -> Any:
    """OpenAI ChatCompletion 형태의 mock 응답으로 tool_calls 자동 추출."""

    # openai ChatCompletion mock
    class _ToolCall:
        def __init__(self, name, args):
            self.id = f"call_{name}"
            self.type = "function"

            class _Fn:
                def __init__(self, n, a):
                    self.name = n
                    self.arguments = a
            self.function = _Fn(name, args)

    class _Message:
        role = "assistant"
        content = "tool_result_answer"
        tool_calls = [
            _ToolCall("web_search", '{"query": "' + question + '"}'),
            _ToolCall("calculator", '{"expr": "1+1"}'),
        ]

    class _Choice:
        message = _Message()
        finish_reason = "tool_calls"

    class _Usage:
        prompt_tokens = 150
        completion_tokens = 40
        total_tokens = 190

    class _ChatCompletion:
        choices = [_Choice()]
        usage = _Usage()
        model = "gpt-4o-mini"

    time.sleep(0.04)
    return _ChatCompletion()


result = openai_style_agent("최신 AI 뉴스 검색해줘", ground_truth="tool_result_answer")
print(f"  결과 타입: {type(result).__name__} (EvalMetadata 자동 추출됨)")
print()


# ===========================================================================
# 결과 요약
# ===========================================================================

print("=" * 60)
print("Layer 2 Agentic Metrics 요약")
print("=" * 60)

report = monitor.generate_report()
print(f"  전체 태스크 수: {report.total_tasks}")

agentic = report.agentic_metrics or {}
if agentic:
    tool_call_data = agentic.get("tool_call_analysis", {})
    if tool_call_data:
        print(f"  도구 호출 분석:")
        print(f"    총 도구 호출: {tool_call_data.get('total_calls', 0)}")
        print(f"    평균 호출/태스크: {tool_call_data.get('avg_calls_per_task', 0):.1f}")

    workflow_data = agentic.get("workflow_execution", {})
    if workflow_data:
        print(f"  워크플로우 실행:")
        print(f"    총 단계: {workflow_data.get('total_steps', 0)}")

    retry_data = agentic.get("retry_correction", {})
    if retry_data:
        total = retry_data.get("total_attempts", 0)
        print(f"  재시도 분석: 총 시도 횟수 = {total}")
else:
    print("  (agentic 지표가 없으면 모니터에 Layer2 활성화 태스크가 부족할 수 있습니다)")

print()
print("Layer 2 트래커 활성화 요약:")
print("  ToolCallAnalyzer        → get_eval_ctx().add_tool_call() 또는 EvalMetadata(tool_calls=[...])")
print("  ToolSelectionTracker    → expected_tools_arg + add_tool_call()")
print("  RetryCorrectionTracker  → TaskResult(attempts > 1)")
print("  WorkflowExecutionTracker→ get_eval_ctx().add_chain_step() 또는 EvalMetadata(chain_steps=[...])")
print("  AgentCoordinationTracker→ get_eval_ctx().add_agent_interaction() 또는 EvalMetadata(agent_interactions=[...])")
