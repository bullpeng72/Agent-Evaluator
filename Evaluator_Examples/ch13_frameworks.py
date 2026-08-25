"""
ch13_frameworks.py — 프레임워크 어댑터 통합 예제
====================================================
Book Chapter 13 — 프레임워크 통합

LangChain, LangGraph, CrewAI, AutoGen 4개 프레임워크의 응답에서
메타데이터를 자동 추출하고, 크로스 프레임워크 파이프라인을 평가한다.

핵심 기능:
  - @agent_eval(framework="langchain")  → tool_calls·chain_steps 자동 추출
  - @agent_eval(framework="langgraph")  → graph_traversal·state_transitions 자동 추출
  - @agent_eval(framework="crewai")     → agent_interactions·task_delegation 자동 추출
  - @agent_eval(framework="autogen")    → conversation_turns·agent_interactions 자동 추출
  - _auto_detect_framework()            → 응답 객체 속성으로 자동 감지
  - 크로스 프레임워크 파이프라인       → LangGraph → LangChain → CrewAI 핸드오프

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — 없어도 실행됨)
    비고: 이 예제는 실제 LangChain/CrewAI/AutoGen 패키지 없이 동작한다.
          @agent_eval(framework=...) 데코레이터는 mock 응답 객체를 duck typing으로 처리한다.

실행:
    python Evaluator_Examples/ch13_frameworks.py

결과:
    results/ch13_frameworks.json
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from agent_evaluator import PerformanceMonitor, setup_otel
from agent_evaluator import agent_eval, batch_eval, EvalMetadata

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch13-frameworks")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

monitor = PerformanceMonitor(
    output_dir=_OUTPUT_DIR,
    enable_transparency=True,           # 투명성 탭: 메트릭 계산 Traces 자동 생성
    use_korean_tokenizer=True,
)


# ---------------------------------------------------------------------------
# 헬퍼: 각 프레임워크의 응답 객체 시뮬레이션
# ---------------------------------------------------------------------------

def _make_langchain_response(answer: str, tools: list, tokens: dict):
    """LangChain AgentExecutor 응답 구조 시뮬레이션."""
    steps = [(SimpleNamespace(tool=t, tool_input="query"), f"{t} 결과") for t in tools]
    return SimpleNamespace(
        output=answer,
        intermediate_steps=steps,
        usage_metadata={"input_tokens": tokens["input"], "output_tokens": tokens["output"]},
    )

def _make_langgraph_response(answer: str, nodes: list, tokens: dict):
    """LangGraph CompiledGraph 응답 구조 시뮬레이션."""
    messages = [
        SimpleNamespace(
            content=answer,
            type="ai",
            response_metadata={"token_usage": {"prompt_tokens": tokens["input"], "completion_tokens": tokens["output"]}},
        )
    ]
    state = {
        "messages": messages,
        "graph_traversal": {
            "nodes_visited": nodes,
            "edges": [(nodes[i], nodes[i+1]) for i in range(len(nodes)-1)],
        },
        "state_transitions": [
            {"from": nodes[i], "to": nodes[i+1], "trigger": "tool_call"}
            for i in range(len(nodes)-1)
        ],
    }
    return state

def _make_crewai_response(answer: str, agents: list, tokens: dict):
    """CrewAI Crew 응답 구조 시뮬레이션."""
    return SimpleNamespace(
        raw=answer,
        token_usage=SimpleNamespace(
            total_tokens=tokens["input"] + tokens["output"],
            prompt_tokens=tokens["input"],
            completion_tokens=tokens["output"],
        ),
        tasks_output=[
            SimpleNamespace(
                description=f"{agent} 태스크",
                agent=agent,
                raw=f"{agent} 결과물",
            )
            for agent in agents
        ],
    )

def _make_autogen_response(answer: str, agents: list, tokens: dict):
    """AutoGen ConversableAgent 응답 구조 시뮬레이션."""
    turns = []
    for i, agent in enumerate(agents):
        turns.append({"role": "assistant", "name": agent, "content": f"{agent}의 응답 {i+1}"})
    turns.append({"role": "assistant", "name": agents[0], "content": answer})
    return {
        "summary": answer,
        "conversation_turns": turns,
        "usage_summary": {"total_cost": 0.002, "total_tokens": tokens["input"] + tokens["output"]},
    }


# ===========================================================================
# [도서 보완] Mock에서 Real로: 프레임워크 자동 인식의 원리
# ===========================================================================
# agent-evaluator는 'Duck Typing' 방식을 사용합니다.
# 실제 프레임워크 패키지가 설치되어 있지 않아도, 반환된 객체가 특정 속성
# (예: choices, usage, messages)을 가지고 있으면 해당 어댑터를 자동 적용합니다.
# ===========================================================================

print("\n=== [참고] PydanticAI 실제 통합 예시 (Real-world Bridge) ===")
print("""
  # 실제 PydanticAI 에이전트 코드 (pip install pydantic-ai 필요)
  from pydantic_ai import Agent
  
  agent = Agent('openai:gpt-5-nano')
  
  @agent_eval(monitor, task_type="qa", framework="pydanticai")
  async def run_pydantic_ai(question: str):
      # result는 RunResult 객체이며, 내부적으로 .all_messages()와 .usage()를 가짐
      # agent-evaluator는 이 메서드들을 호출해 '자동으로' 지표를 추출합니다.
      result = await agent.run(question)
      return result  # 객체 그대로 반환
""")

def _simulate_pydantic_ai_run(answer: str, tokens: dict):
    """PydanticAI RunResult의 핵심 인터페이스를 흉내내는 Duck 객체"""
    class MockUsage:
        def __init__(self, t): self.t = t
        @property
        def request_tokens(self): return self.t["input"]
        @property
        def response_tokens(self): return self.t["output"]
        
    class MockRunResult:
        def __init__(self, a, t):
            self.data = a
            self._usage = MockUsage(t)
        def usage(self): return self._usage
        def all_messages(self): return [] # 간소화
        def __str__(self): return str(self.data)

    return MockRunResult(answer, tokens)

@agent_eval(monitor, task_type="qa", framework="pydanticai", task_id_prefix="pydantic")
def pydantic_ai_mock_agent(question: str, ground_truth: str = ""):
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return _simulate_pydantic_ai_run("PydanticAI가 처리한 답변입니다.", {"input": 45, "output": 25})

pydantic_ai_mock_agent("PydanticAI 통합 테스트")
print("  ✅ PydanticAI Duck Typing 어댑터 작동 확인 (usage.request_tokens 자동 추출)")


# ===========================================================================
# 섹션 1: LangChain 어댑터
# ===========================================================================
print("\n=== 섹션 1: LangChain 어댑터 ===")

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="lc")
def langchain_agent(question: str, ground_truth: str = ""):
    """LangChain AgentExecutor 시뮬레이션."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return _make_langchain_response(
        answer="LangChain 검색 결과입니다.",
        tools=["web_search", "calculator", "wikipedia"],
        tokens={"input": 350, "output": 120},
    )

LANGCHAIN_CASES = [
    ("최신 파이썬 버전은?",     "3.12"),
    ("서울 인구는 몇 명인가?",  "약 950만"),
    ("2+2는?",                  "4"),
]

for q, gt in LANGCHAIN_CASES:
    langchain_agent(q, ground_truth=gt)

print(f"  LangChain 3건 완료 (tool_calls·chain_steps 자동 추출)")

# ===========================================================================
# 섹션 2: LangGraph 어댑터 (노드 단계 + 상태 전이)
# ===========================================================================
print("\n=== 섹션 2: LangGraph 어댑터 ===")

@agent_eval(monitor, task_type="planning", framework="langgraph", task_id_prefix="lg")
def langgraph_agent(question: str, ground_truth: str = ""):
    """LangGraph 멀티노드 그래프 시뮬레이션."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return _make_langgraph_response(
        answer="LangGraph 분석 결과입니다.",
        nodes=["router", "search_node", "analysis_node", "synthesis_node"],
        tokens={"input": 420, "output": 180},
    )

LG_CASES = [
    ("시장 트렌드를 분석해줘",   "상승세"),
    ("경쟁사 보고서 작성해줘",   "보고서 완성"),
]

for q, gt in LG_CASES:
    langgraph_agent(q, ground_truth=gt)

print(f"  LangGraph 2건 완료 (graph_traversal·state_transitions 자동 추출)")

# ===========================================================================
# 섹션 3: CrewAI 어댑터 (역할 기반 멀티에이전트)
# ===========================================================================
print("\n=== 섹션 3: CrewAI 어댑터 ===")

@agent_eval(monitor, task_type="tool_use", framework="crewai", task_id_prefix="crew")
def crewai_agent(question: str, ground_truth: str = ""):
    """CrewAI Crew (Researcher + Analyst + Writer) 시뮬레이션."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    return _make_crewai_response(
        answer="CrewAI 팀 결과물입니다.",
        agents=["researcher", "analyst", "writer"],
        tokens={"input": 600, "output": 250},
    )

CREW_CASES = [
    ("AI 산업 동향 보고서를 작성해줘", "보고서"),
    ("경쟁사 분석 및 전략 수립해줘",  "전략"),
]

for q, gt in CREW_CASES:
    crewai_agent(q, ground_truth=gt)

print(f"  CrewAI 2건 완료 (agent_interactions·tasks_output 자동 추출)")

# ===========================================================================
# 섹션 4: AutoGen 어댑터 (대화형 멀티에이전트, 비동기)
# ===========================================================================
print("\n=== 섹션 4: AutoGen 어댑터 ===")

@agent_eval(monitor, task_type="tool_use", framework="autogen", task_id_prefix="ag")
async def autogen_agent(question: str, ground_truth: str = ""):
    """AutoGen ConversableAgent 시뮬레이션."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    await asyncio.sleep(0.01)  # 비동기 LLM 호출 흉내
    return _make_autogen_response(
        answer="AutoGen 협력 결과입니다.",
        agents=["user_proxy", "assistant", "code_executor"],
        tokens={"input": 500, "output": 200},
    )

async def _run_autogen():
    AG_CASES = [
        ("코드 리뷰를 수행하고 개선 방안을 제시해줘", "코드 개선"),
        ("데이터 분석 파이프라인을 설계해줘",         "파이프라인 설계"),
    ]
    for q, gt in AG_CASES:
        await autogen_agent(q, ground_truth=gt)
    print(f"  AutoGen 2건 완료 (conversation_turns·agent_interactions 자동 추출)")

asyncio.run(_run_autogen())

# ===========================================================================
# 섹션 5: 크로스 프레임워크 파이프라인
# ===========================================================================
print("\n=== 섹션 5: 크로스 프레임워크 파이프라인 ===")
print("  흐름: LangGraph(라우팅) → LangChain(검색) → CrewAI(생성)")

PIPELINE_TASKS = [
    ("경제 위기 예측 리포트 작성",   "리포트"),
    ("신제품 출시 전략 수립",         "전략 문서"),
    ("기술 트렌드 분석",             "분석 보고서"),
]

@agent_eval(monitor, task_type="planning", framework="langgraph", task_id_prefix="pipe_route")
def routing_stage(question: str, ground_truth: str = ""):
    """Stage 1: LangGraph 라우터."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LangGraph 그래프 호출로 교체하세요.
    #   예) result = compiled_graph.invoke({"messages": [HumanMessage(content=question)]})
    return _make_langgraph_response(
        answer=f"라우팅 완료: {question}",
        nodes=["router", "task_splitter", "dispatcher"],
        tokens={"input": 200, "output": 80},
    )

@agent_eval(monitor, task_type="tool_use", framework="langchain", task_id_prefix="pipe_search")
def search_stage(question: str, ground_truth: str = ""):
    """Stage 2: LangChain 검색."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LangChain agent_executor 호출로 교체하세요.
    #   예) return agent_executor.invoke({"input": question})
    return _make_langchain_response(
        answer=f"검색 결과: {question}",
        tools=["web_search", "database", "knowledge_base"],
        tokens={"input": 450, "output": 150},
    )

@agent_eval(monitor, task_type="tool_use", framework="crewai", task_id_prefix="pipe_gen")
def generation_stage(question: str, ground_truth: str = ""):
    """Stage 3: CrewAI 생성."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 CrewAI crew.kickoff() 호출로 교체하세요.
    #   예) return crew.kickoff(inputs={"topic": question})
    return _make_crewai_response(
        answer=f"최종 결과물: {question}",
        agents=["researcher", "writer", "reviewer"],
        tokens={"input": 700, "output": 350},
    )

for task, gt in PIPELINE_TASKS:
    routing_stage(task, ground_truth=gt)
    search_stage(task, ground_truth=gt)
    generation_stage(task, ground_truth=gt)
    print(f"  ✅ '{task}' 파이프라인 완료 (3단계)")

# ===========================================================================
# 섹션 6: @batch_eval — 프레임워크별 배치 비교
# ===========================================================================
print("\n=== 섹션 6: 프레임워크별 배치 비교 ===")

BENCHMARK_QA = [
    ("GDP란?",        "국내총생산"),
    ("CPU란?",        "중앙처리장치"),
    ("API란?",        "응용 프로그램 인터페이스"),
]

@batch_eval(monitor, task_type="qa", task_id_prefix="bench_lc", return_format="list")
def lc_batch(questions: list, ground_truths: Optional[list] = None) -> list:
    return [f"[LangChain] {q}에 대한 답변" for q in questions]

@batch_eval(monitor, task_type="qa", task_id_prefix="bench_crew", return_format="list")
def crew_batch(questions: list, ground_truths: Optional[list] = None) -> list:
    return [f"[CrewAI] {q}에 대한 답변" for q in questions]

lc_results   = lc_batch(
    questions=[q for q, _ in BENCHMARK_QA],
    ground_truths=[gt for _, gt in BENCHMARK_QA],
)
crew_results = crew_batch(
    questions=[q for q, _ in BENCHMARK_QA],
    ground_truths=[gt for _, gt in BENCHMARK_QA],
)
print(f"  LangChain 배치 {len(lc_results)}건 / CrewAI 배치 {len(crew_results)}건 완료")

# ===========================================================================
# 최종 리포트 & 저장
# ===========================================================================
print("\n=== 최종 리포트 ===")

report = monitor.generate_report().to_dict()
total  = report.get("total_tasks", 0)
am     = report.get("accuracy_metrics", {})
tcr    = am.get("tcr", {}).get("tcr", 0)          # 0–100 범위 그대로 사용
acc    = am.get("accuracy_scores", {}).get("overall_accuracy", 0)  # 0–100 범위 그대로 사용
print(f"  총 태스크: {total}건  TCR: {tcr:.1f}%  평균 정확도: {acc:.2f}%")
print("  ℹ  정확도가 낮게 측정되는 것은 정상입니다.")
print("     프레임워크 어댑터 예제는 실제 LLM 호출 없이 mock 응답을 사용하며,")
print("     ground_truth와 mock 응답의 토큰 오버랩이 매우 낮아 수 % 수준으로 나타납니다.")

monitor.save_to_file("ch13_frameworks")
print("\n결과 저장 완료: results/ch13_frameworks.json")
