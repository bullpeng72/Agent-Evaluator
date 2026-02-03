#!/usr/bin/env python3
"""
Level 3 Production - Example 03: LangChain 통합
================================================

FILE_PREFIX: [L3-03]_

🎯 주제: LangChain 프레임워크 통합 평가

📚 학습 내용:
1. LCEL (LangChain Expression Language) 평가
2. LangChain Agent 성능 측정
3. Chain 실행 추적
4. LangChain 특화 메트릭

🔍 핵심 개념:
- LCEL: Runnable 인터페이스 기반 체인 구성
- Agent: Tool 자동 선택 및 실행
- Chain: 순차적 처리 파이프라인
- Callback: 실행 추적 및 모니터링

실행 방법:
    python level_3_production/03_framework_langchain.py
"""

FILE_PREFIX = "[L3-03]_"

from agent_evaluator import PerformanceMonitor, create_taskresult
import time
import json

def main():
    print("=" * 80)
    print("🔗 Level 3 Production - LangChain 통합")
    print("=" * 80)

    monitor = PerformanceMonitor()

    print("""
🔗 LangChain Integration:
- LCEL (LangChain Expression Language)
- Agent with Tool Selection
- Chain Pipeline Execution
- Callback-based Monitoring

📊 측정 메트릭:
- Layer 1: Latency, Tokens, Tool Efficiency
- Layer 2: Tool Selection, Workflow Execution
- LangChain 특화: Chain 구조, Runnable 성능
    """)

    # ========================================================================
    # Part 1: Simple LCEL Chain
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Simple LCEL Chain - Prompt | LLM | Parser")
    print("=" * 80)

    print("""
시나리오: 간단한 LCEL 체인
chain = prompt | llm | output_parser

→ 순차적 Runnable 실행
    """)

    # 시뮬레이션: LCEL Chain 실행
    lcel_execution = {
        "task_id": "lcel_001",
        "question": "Python의 주요 특징 3가지를 설명하세요",
        "chain_steps": [
            {"name": "prompt_template", "type": "runnable", "duration": 0.01},
            {"name": "llm_invoke", "type": "runnable", "duration": 1.2},
            {"name": "output_parser", "type": "runnable", "duration": 0.02}
        ],
        "response": "1. 간결한 문법 2. 다양한 라이브러리 3. 높은 생산성",
        "ground_truth": "간결한 문법, 풍부한 라이브러리, 높은 생산성",
        "tokens": {"prompt": 25, "completion": 30, "total": 55}
    }

    start_time = time.time()
    time.sleep(sum(step["duration"] for step in lcel_execution["chain_steps"]))
    execution_time = time.time() - start_time

    task = create_taskresult(
        task_id=lcel_execution["task_id"],
        task_type="lcel_chain",
        question=lcel_execution["question"],
        response=lcel_execution["response"],
        ground_truth=lcel_execution["ground_truth"],
        execution_time=execution_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for step in lcel_execution["chain_steps"]:
        monitor.workflow_tracker.track_step(
            task_id=lcel_execution["task_id"],
            step_name=step["name"],
            step_type=step["type"],
            success=True,
            execution_time=step["duration"],
            framework="langchain"
        )

    print(f"\n✅ LCEL Chain 실행:")
    print(f"  Chain 구조: prompt → llm → parser")
    for i, step in enumerate(lcel_execution["chain_steps"], 1):
        print(f"  {i}. {step['name']}: {step['duration']:.3f}s")
    print(f"  총 실행 시간: {execution_time:.3f}s")
    print(f"  토큰 사용: {lcel_execution['tokens']['total']}")

    # ========================================================================
    # Part 2: LangChain Agent with Tools
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: LangChain Agent with Tools")
    print("=" * 80)

    print("""
시나리오: ReAct Agent with Tools
- Agent가 질문 분석
- 필요한 Tool 선택
- Tool 실행 및 결과 종합

Tools: [search, calculator, wikipedia]
    """)

    agent_execution = {
        "task_id": "agent_001",
        "question": "2024년 파리 올림픽 금메달 수와 2020년 도쿄 올림픽 금메달 수의 차이는?",
        "expected_tools": ["search", "calculator"],
        "agent_steps": [
            {
                "step": "think",
                "thought": "파리 올림픽 정보를 검색해야 함",
                "duration": 0.5
            },
            {
                "step": "tool_use",
                "tool": "search",
                "query": "2024 파리 올림픽 금메달",
                "result": "50개",
                "duration": 0.8,
                "success": True
            },
            {
                "step": "think",
                "thought": "도쿄 올림픽 정보도 필요",
                "duration": 0.3
            },
            {
                "step": "tool_use",
                "tool": "search",
                "query": "2020 도쿄 올림픽 금메달",
                "result": "45개",
                "duration": 0.7,
                "success": True
            },
            {
                "step": "think",
                "thought": "차이를 계산",
                "duration": 0.2
            },
            {
                "step": "tool_use",
                "tool": "calculator",
                "query": "50 - 45",
                "result": "5",
                "duration": 0.1,
                "success": True
            },
            {
                "step": "final_answer",
                "answer": "5개 차이",
                "duration": 0.4
            }
        ],
        "response": "파리 올림픽(50개)과 도쿄 올림픽(45개)의 차이는 5개입니다.",
        "ground_truth": "5개"
    }

    total_time = sum(step["duration"] for step in agent_execution["agent_steps"])

    task = create_taskresult(
        task_id=agent_execution["task_id"],
        task_type="langchain_agent",
        question=agent_execution["question"],
        response=agent_execution["response"],
        ground_truth=agent_execution["ground_truth"],
        execution_time=total_time
    )

    # Tool calls 추가
    tool_calls = [
        {"tool": step["tool"], "success": step["success"], "duration": step["duration"]}
        for step in agent_execution["agent_steps"]
        if step["step"] == "tool_use"
    ]
    task.tool_calls = tool_calls
    task.expected_tools = agent_execution["expected_tools"]
    monitor.record_task(task)

    # Tool Selection 평가
    actual_tools = list(set(tc["tool"] for tc in tool_calls))
    monitor.tool_selection_tracker.evaluate_selection(
        task_id=agent_execution["task_id"],
        expected_tools=agent_execution["expected_tools"],
        actual_tools=actual_tools
    )

    # Workflow tracking
    for step in agent_execution["agent_steps"]:
        step_type = "agent_task" if step["step"] in ["think", "final_answer"] else "tool_call"
        monitor.workflow_tracker.track_step(
            task_id=agent_execution["task_id"],
            step_name=step["step"],
            step_type=step_type,
            success=step.get("success", True),
            execution_time=step["duration"],
            framework="langchain"
        )

    print(f"\n✅ Agent 실행:")
    print(f"  총 Step: {len(agent_execution['agent_steps'])}개")
    print(f"  Tool 호출: {len(tool_calls)}회")
    print(f"  선택된 Tools: {actual_tools}")
    print(f"  예상 Tools: {agent_execution['expected_tools']}")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # Tool selection 결과
    selection_result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=agent_execution["task_id"],
        expected_tools=agent_execution["expected_tools"],
        actual_tools=actual_tools
    )
    print(f"\n  Tool Selection Metrics:")
    print(f"    - Precision: {selection_result['precision']:.1f}%")
    print(f"    - Recall: {selection_result['recall']:.1f}%")
    print(f"    - F1 Score: {selection_result['f1_score']:.1f}%")

    # ========================================================================
    # Part 3: Sequential Chain (Legacy)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Sequential Chain (Legacy Style)")
    print("=" * 80)

    print("""
시나리오: Multi-step Sequential Chain
1. Chain 1: 주제 추출
2. Chain 2: 내용 생성
3. Chain 3: 요약

→ 각 Chain의 출력이 다음 Chain의 입력
    """)

    sequential_chain = {
        "task_id": "seq_chain_001",
        "question": "AI의 미래에 대한 블로그 포스트 작성",
        "chains": [
            {
                "name": "topic_extraction",
                "input": "AI의 미래",
                "output": "주요 토픽: 머신러닝, 자동화, 윤리",
                "duration": 0.6
            },
            {
                "name": "content_generation",
                "input": "머신러닝, 자동화, 윤리",
                "output": "AI는 미래 산업의 핵심이며...(500 words)",
                "duration": 2.5
            },
            {
                "name": "summarization",
                "input": "(500 words content)",
                "output": "AI는 머신러닝과 자동화를 통해 발전하며 윤리적 고려가 필요합니다.",
                "duration": 0.8
            }
        ],
        "response": "AI는 머신러닝과 자동화를 통해 발전하며 윤리적 고려가 필요합니다.",
        "ground_truth": ""
    }

    total_time = sum(chain["duration"] for chain in sequential_chain["chains"])

    task = create_taskresult(
        task_id=sequential_chain["task_id"],
        task_type="sequential_chain",
        question=sequential_chain["question"],
        response=sequential_chain["response"],
        ground_truth=sequential_chain["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for chain in sequential_chain["chains"]:
        monitor.workflow_tracker.track_step(
            task_id=sequential_chain["task_id"],
            step_name=chain["name"],
            step_type="agent_task",
            success=True,
            execution_time=chain["duration"],
            framework="langchain"
        )

    print(f"\n✅ Sequential Chain 실행:")
    for i, chain in enumerate(sequential_chain["chains"], 1):
        print(f"  {i}. {chain['name']}")
        print(f"     Input: {chain['input'][:50]}...")
        print(f"     Duration: {chain['duration']:.2f}s")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 4: Retrieval Chain (RAG Pattern)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Retrieval Chain (RAG Pattern)")
    print("=" * 80)

    print("""
시나리오: RAG (Retrieval-Augmented Generation)
1. Retriever: 관련 문서 검색
2. LLM: 검색된 문서 기반 답변 생성

→ Context-aware 답변
    """)

    rag_execution = {
        "task_id": "rag_001",
        "question": "LangChain의 주요 구성 요소는?",
        "retrieval": {
            "query": "LangChain components",
            "retrieved_docs": [
                "LangChain은 Models, Prompts, Chains으로 구성됩니다.",
                "LangChain의 핵심은 LCEL입니다.",
                "Agent는 LangChain의 고급 기능입니다."
            ],
            "relevance_scores": [0.95, 0.88, 0.82],
            "duration": 0.3
        },
        "generation": {
            "context": "3개 문서",
            "response": "LangChain의 주요 구성 요소는 Models, Prompts, Chains, LCEL, Agent입니다.",
            "duration": 1.2
        },
        "ground_truth": "Models, Prompts, Chains, LCEL, Agent"
    }

    total_time = rag_execution["retrieval"]["duration"] + rag_execution["generation"]["duration"]

    task = create_taskresult(
        task_id=rag_execution["task_id"],
        task_type="rag_chain",
        question=rag_execution["question"],
        response=rag_execution["generation"]["response"],
        ground_truth=rag_execution["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    monitor.workflow_tracker.track_step(
        task_id=rag_execution["task_id"],
        step_name="retrieval",
        step_type="tool_call",
        success=True,
        execution_time=rag_execution["retrieval"]["duration"],
        framework="langchain"
    )
    monitor.workflow_tracker.track_step(
        task_id=rag_execution["task_id"],
        step_name="generation",
        step_type="agent_task",
        success=True,
        execution_time=rag_execution["generation"]["duration"],
        framework="langchain"
    )

    print(f"\n✅ RAG Chain 실행:")
    print(f"  Retrieval:")
    print(f"    - 검색된 문서: {len(rag_execution['retrieval']['retrieved_docs'])}개")
    print(f"    - 평균 관련성: {sum(rag_execution['retrieval']['relevance_scores']) / len(rag_execution['retrieval']['relevance_scores']):.2f}")
    print(f"    - Duration: {rag_execution['retrieval']['duration']:.2f}s")
    print(f"  Generation:")
    print(f"    - Context: {rag_execution['generation']['context']}")
    print(f"    - Duration: {rag_execution['generation']['duration']:.2f}s")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 5: Parallel Chain (RunnableParallel)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Parallel Chain (RunnableParallel)")
    print("=" * 80)

    print("""
시나리오: 병렬 실행으로 성능 최적화
- Chain A: 영어 번역
- Chain B: 감정 분석
- Chain C: 키워드 추출

→ 동시 실행으로 시간 단축
    """)

    parallel_execution = {
        "task_id": "parallel_001",
        "question": "이 텍스트를 분석하세요: '오늘 날씨가 정말 좋네요!'",
        "parallel_chains": [
            {"name": "translation", "result": "The weather is really nice today!", "duration": 0.8},
            {"name": "sentiment", "result": "긍정 (0.95)", "duration": 0.6},
            {"name": "keywords", "result": ["날씨", "좋다"], "duration": 0.5}
        ],
        "response": "번역: 'The weather is really nice today!', 감정: 긍정(0.95), 키워드: 날씨, 좋다",
        "ground_truth": ""
    }

    # 병렬 실행 시간 = max duration
    parallel_time = max(chain["duration"] for chain in parallel_execution["parallel_chains"])
    # 순차 실행 시간 = sum duration
    sequential_time = sum(chain["duration"] for chain in parallel_execution["parallel_chains"])

    task = create_taskresult(
        task_id=parallel_execution["task_id"],
        task_type="parallel_chain",
        question=parallel_execution["question"],
        response=parallel_execution["response"],
        ground_truth=parallel_execution["ground_truth"],
        execution_time=parallel_time
    )
    monitor.record_task(task)

    # Workflow tracking (parallel)
    for chain in parallel_execution["parallel_chains"]:
        monitor.workflow_tracker.track_step(
            task_id=parallel_execution["task_id"],
            step_name=chain["name"],
            step_type="parallel_group",
            success=True,
            execution_time=chain["duration"],
            framework="langchain"
        )

    print(f"\n✅ Parallel Chain 실행:")
    for chain in parallel_execution["parallel_chains"]:
        print(f"  ⚡ {chain['name']}: {chain['duration']:.2f}s")
    print(f"\n  순차 실행 시: {sequential_time:.2f}s")
    print(f"  병렬 실행 시: {parallel_time:.2f}s")
    print(f"  시간 절약: {sequential_time - parallel_time:.2f}s ({(1 - parallel_time/sequential_time)*100:.0f}% faster)")

    # ========================================================================
    # Part 6: 전체 통계 및 LangChain 특화 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 통계 및 LangChain 분석")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n🔗 LangChain Framework 통계:")
    print(f"  - 실행된 Task: 5개")
    print(f"  - Chain 유형:")
    print(f"    • LCEL Chain: 1")
    print(f"    • Agent: 1")
    print(f"    • Sequential Chain: 1")
    print(f"    • RAG Chain: 1")
    print(f"    • Parallel Chain: 1")

    print(f"\n📊 성능 메트릭:")
    latency_metrics = report.efficiency_metrics.get('latency', {})
    print(f"  - 평균 지연시간: {latency_metrics.get('mean', 0):.3f}s")
    print(f"  - P95 지연시간: {latency_metrics.get('p95', 0):.3f}s")

    tool_metrics = report.efficiency_metrics.get('tool_efficiency', {})
    if tool_metrics:
        print(f"\n🔧 Tool 효율성:")
        print(f"  - 총 Tool 호출: {tool_metrics.get('total_calls', 0)}회")
        print(f"  - 성공률: {tool_metrics.get('success_rate', 0):.1f}%")

    # Workflow execution rate
    workflow_rate_data = monitor.workflow_tracker.calculate_execution_success_rate()
    workflow_rate = workflow_rate_data.get('execution_success_rate', 0) if isinstance(workflow_rate_data, dict) else workflow_rate_data

    print(f"\n🔄 Workflow 실행:")
    print(f"  - 성공률: {workflow_rate:.1f}%")
    print(f"  - 병렬 처리: 1개 (시간 절약: {(1 - parallel_time/sequential_time)*100:.0f}%)")

    # Tool selection (Agent만 해당)
    tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    if tool_selection_stats.get('total_evaluations', 0) > 0:
        print(f"\n🎯 Tool Selection (Agent):")
        print(f"  - Precision: {tool_selection_stats.get('avg_precision', 0):.1f}%")
        print(f"  - Recall: {tool_selection_stats.get('avg_recall', 0):.1f}%")
        print(f"  - F1 Score: {tool_selection_stats.get('avg_f1_score', 0):.1f}%")

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    print(f"\n✅ LangChain Integration Report:")
    print(f"  - Framework: LangChain")
    print(f"  - Chain Types: 5")
    print(f"  - Workflow Success Rate: {workflow_rate:.1f}%")

    # 결과 저장
    filename = f"{FILE_PREFIX}langchain_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    print("\n" + "=" * 80)
    print("🎉 LangChain 통합 평가 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ LCEL (LangChain Expression Language)
2. ✅ LangChain Agent with Tool Selection
3. ✅ Sequential Chain (Legacy)
4. ✅ RAG Pattern (Retrieval + Generation)
5. ✅ Parallel Chain (RunnableParallel)

🔍 LangChain 특징:
- Runnable 인터페이스: 통일된 실행 방식
- LCEL: 체인 구성의 표준
- Agent: 자동 Tool 선택
- Callback: 실행 추적 및 모니터링

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py
  → {filename} 선택
  → Layer 1-2 Metrics, Workflow 확인

🚀 다음 단계:
  level_3_production/04_framework_langgraph.py: LangGraph State Machine
    """)

if __name__ == "__main__":
    main()
