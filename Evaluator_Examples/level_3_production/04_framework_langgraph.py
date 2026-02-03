#!/usr/bin/env python3
"""
Level 3 Production - Example 04: LangGraph 통합
================================================

FILE_PREFIX: [L3-04]_

🎯 주제: LangGraph State Machine 통합 평가

📚 학습 내용:
1. State Graph 구조 평가
2. Conditional Edge 분기 추적
3. Node 간 상태 전달
4. Cycle Detection 및 최적화

🔍 핵심 개념:
- State Graph: 상태 기반 워크플로우
- Node: 작업 단위 (함수)
- Edge: Node 간 연결
- Conditional Edge: 조건부 분기
- State: Node 간 공유 데이터

실행 방법:
    python level_3_production/04_framework_langgraph.py
"""

FILE_PREFIX = "[L3-04]_"

from agent_evaluator import PerformanceMonitor, create_taskresult
import time

def main():
    print("=" * 80)
    print("🔀 Level 3 Production - LangGraph 통합")
    print("=" * 80)

    monitor = PerformanceMonitor()

    print("""
🔀 LangGraph State Machine:
- State Graph: 상태 기반 워크플로우
- Conditional Edge: 동적 분기
- State Persistence: 상태 저장 및 복원
- Cycle Control: 무한 루프 방지

📊 측정 메트릭:
- Layer 1: Latency, Workflow Efficiency
- Layer 2: Workflow Execution, Agent Coordination
- LangGraph 특화: Graph 구조, State 전이
    """)

    # ========================================================================
    # Part 1: Simple Linear Graph
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Simple Linear Graph - 순차 실행")
    print("=" * 80)

    print("""
Graph 구조:
START → node_a → node_b → node_c → END

→ 각 Node가 순차적으로 실행
    """)

    linear_graph = {
        "task_id": "linear_graph_001",
        "question": "선형 워크플로우 실행",
        "nodes": [
            {
                "name": "node_a",
                "state_in": {"input": "start"},
                "state_out": {"result_a": "processed_a"},
                "duration": 0.3
            },
            {
                "name": "node_b",
                "state_in": {"result_a": "processed_a"},
                "state_out": {"result_b": "processed_b"},
                "duration": 0.5
            },
            {
                "name": "node_c",
                "state_in": {"result_b": "processed_b"},
                "state_out": {"final": "complete"},
                "duration": 0.4
            }
        ],
        "response": "complete",
        "ground_truth": ""
    }

    total_time = sum(node["duration"] for node in linear_graph["nodes"])

    task = create_taskresult(
        task_id=linear_graph["task_id"],
        task_type="langgraph_linear",
        question=linear_graph["question"],
        response=linear_graph["response"],
        ground_truth=linear_graph["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for node in linear_graph["nodes"]:
        monitor.workflow_tracker.track_step(
            task_id=linear_graph["task_id"],
            step_name=node["name"],
            step_type="agent_task",
            success=True,
            execution_time=node["duration"],
            framework="langgraph"
        )

    print(f"\n✅ Linear Graph 실행:")
    for i, node in enumerate(linear_graph["nodes"], 1):
        print(f"  {i}. {node['name']}")
        print(f"     State In: {node['state_in']}")
        print(f"     State Out: {node['state_out']}")
        print(f"     Duration: {node['duration']:.2f}s")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 2: Conditional Graph (Branching)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: Conditional Graph - 조건부 분기")
    print("=" * 80)

    print("""
Graph 구조:
START → analyze → [condition]
                    ├─ (if positive) → process_positive → END
                    └─ (if negative) → process_negative → END

→ analyze 결과에 따라 다른 경로 실행
    """)

    conditional_graph = {
        "task_id": "conditional_001",
        "question": "감정 분석 및 처리",
        "nodes": [
            {
                "name": "analyze",
                "function": "sentiment_analysis",
                "state_in": {"text": "오늘 날씨가 좋네요!"},
                "state_out": {"sentiment": "positive", "score": 0.92},
                "duration": 0.6
            },
            {
                "name": "conditional_edge",
                "condition": "sentiment == 'positive'",
                "result": True,
                "duration": 0.01
            },
            {
                "name": "process_positive",
                "state_in": {"sentiment": "positive", "score": 0.92},
                "state_out": {"response": "긍정적인 반응 처리 완료"},
                "duration": 0.4
            }
        ],
        "skipped_nodes": ["process_negative"],
        "response": "긍정적인 반응 처리 완료",
        "ground_truth": ""
    }

    total_time = sum(node["duration"] for node in conditional_graph["nodes"])

    task = create_taskresult(
        task_id=conditional_graph["task_id"],
        task_type="langgraph_conditional",
        question=conditional_graph["question"],
        response=conditional_graph["response"],
        ground_truth=conditional_graph["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for node in conditional_graph["nodes"]:
        step_type = "decision" if node["name"] == "conditional_edge" else "agent_task"
        monitor.workflow_tracker.track_step(
            task_id=conditional_graph["task_id"],
            step_name=node["name"],
            step_type=step_type,
            success=True,
            execution_time=node["duration"],
            framework="langgraph"
        )

    print(f"\n✅ Conditional Graph 실행:")
    for i, node in enumerate(conditional_graph["nodes"], 1):
        print(f"  {i}. {node['name']}")
        if node["name"] == "conditional_edge":
            print(f"     Condition: {node['condition']}")
            print(f"     Result: {node['result']}")
        else:
            print(f"     State: {node['state_out']}")
        print(f"     Duration: {node['duration']:.2f}s")
    print(f"  Skip된 Node: {conditional_graph['skipped_nodes']}")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 3: Parallel Execution Graph
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Parallel Execution Graph")
    print("=" * 80)

    print("""
Graph 구조:
START → split → [parallel]
                  ├─ process_a ─┐
                  ├─ process_b ─┼→ merge → END
                  └─ process_c ─┘

→ 병렬 처리로 성능 최적화
    """)

    parallel_graph = {
        "task_id": "parallel_graph_001",
        "question": "데이터 병렬 처리",
        "nodes": [
            {
                "name": "split",
                "state_in": {"data": "large_dataset"},
                "state_out": {"chunk_a": "...", "chunk_b": "...", "chunk_c": "..."},
                "duration": 0.2
            }
        ],
        "parallel_nodes": [
            {"name": "process_a", "state_out": {"result_a": "processed"}, "duration": 1.2},
            {"name": "process_b", "state_out": {"result_b": "processed"}, "duration": 0.9},
            {"name": "process_c", "state_out": {"result_c": "processed"}, "duration": 1.5}
        ],
        "merge_node": {
            "name": "merge",
            "state_in": {"result_a": "...", "result_b": "...", "result_c": "..."},
            "state_out": {"final_result": "combined"},
            "duration": 0.3
        },
        "response": "combined",
        "ground_truth": ""
    }

    # 병렬 실행 시간 = split + max(parallel) + merge
    parallel_time = (
        parallel_graph["nodes"][0]["duration"] +
        max(node["duration"] for node in parallel_graph["parallel_nodes"]) +
        parallel_graph["merge_node"]["duration"]
    )
    # 순차 실행 시간 = split + sum(parallel) + merge
    sequential_time = (
        parallel_graph["nodes"][0]["duration"] +
        sum(node["duration"] for node in parallel_graph["parallel_nodes"]) +
        parallel_graph["merge_node"]["duration"]
    )

    task = create_taskresult(
        task_id=parallel_graph["task_id"],
        task_type="langgraph_parallel",
        question=parallel_graph["question"],
        response=parallel_graph["response"],
        ground_truth=parallel_graph["ground_truth"],
        execution_time=parallel_time
    )
    monitor.record_task(task)

    # Workflow tracking
    monitor.workflow_tracker.track_step(
        task_id=parallel_graph["task_id"],
        step_name=parallel_graph["nodes"][0]["name"],
        step_type="agent_task",
        success=True,
        execution_time=parallel_graph["nodes"][0]["duration"],
        framework="langgraph"
    )

    for node in parallel_graph["parallel_nodes"]:
        monitor.workflow_tracker.track_step(
            task_id=parallel_graph["task_id"],
            step_name=node["name"],
            step_type="parallel_group",
            success=True,
            execution_time=node["duration"],
            framework="langgraph"
        )

    monitor.workflow_tracker.track_step(
        task_id=parallel_graph["task_id"],
        step_name=parallel_graph["merge_node"]["name"],
        step_type="agent_task",
        success=True,
        execution_time=parallel_graph["merge_node"]["duration"],
        framework="langgraph"
    )

    print(f"\n✅ Parallel Graph 실행:")
    print(f"  1. split: {parallel_graph['nodes'][0]['duration']:.2f}s")
    print(f"  2. Parallel Processing:")
    for node in parallel_graph["parallel_nodes"]:
        print(f"     ⚡ {node['name']}: {node['duration']:.2f}s")
    print(f"  3. merge: {parallel_graph['merge_node']['duration']:.2f}s")
    print(f"\n  순차 실행 시: {sequential_time:.2f}s")
    print(f"  병렬 실행 시: {parallel_time:.2f}s")
    print(f"  시간 절약: {sequential_time - parallel_time:.2f}s ({(1 - parallel_time/sequential_time)*100:.0f}% faster)")

    # ========================================================================
    # Part 4: Cycle Graph (Loop with Condition)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Cycle Graph - 반복 실행")
    print("=" * 80)

    print("""
Graph 구조:
START → process → check → [condition]
          ↑                  ├─ (if not done) → improve ─┘
          |                  └─ (if done) → END
          └──────────────────────────────────┘

→ 조건 만족까지 반복 실행
    """)

    cycle_graph = {
        "task_id": "cycle_001",
        "question": "반복 개선 프로세스",
        "iterations": [
            {
                "iteration": 1,
                "nodes": [
                    {"name": "process", "state": {"quality": 0.6}, "duration": 0.4},
                    {"name": "check", "condition": "quality >= 0.9", "result": False, "duration": 0.1},
                    {"name": "improve", "state": {"quality": 0.75}, "duration": 0.5}
                ]
            },
            {
                "iteration": 2,
                "nodes": [
                    {"name": "process", "state": {"quality": 0.75}, "duration": 0.4},
                    {"name": "check", "condition": "quality >= 0.9", "result": False, "duration": 0.1},
                    {"name": "improve", "state": {"quality": 0.88}, "duration": 0.5}
                ]
            },
            {
                "iteration": 3,
                "nodes": [
                    {"name": "process", "state": {"quality": 0.88}, "duration": 0.4},
                    {"name": "check", "condition": "quality >= 0.9", "result": False, "duration": 0.1},
                    {"name": "improve", "state": {"quality": 0.95}, "duration": 0.5}
                ]
            },
            {
                "iteration": 4,
                "nodes": [
                    {"name": "process", "state": {"quality": 0.95}, "duration": 0.4},
                    {"name": "check", "condition": "quality >= 0.9", "result": True, "duration": 0.1}
                ]
            }
        ],
        "response": "품질 목표 달성 (0.95)",
        "ground_truth": ""
    }

    total_time = sum(
        sum(node["duration"] for node in iteration["nodes"])
        for iteration in cycle_graph["iterations"]
    )

    task = create_taskresult(
        task_id=cycle_graph["task_id"],
        task_type="langgraph_cycle",
        question=cycle_graph["question"],
        response=cycle_graph["response"],
        ground_truth=cycle_graph["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for iteration in cycle_graph["iterations"]:
        for node in iteration["nodes"]:
            step_type = "decision" if node["name"] == "check" else "agent_task"
            monitor.workflow_tracker.track_step(
                task_id=cycle_graph["task_id"],
                step_name=f"{node['name']}_iter{iteration['iteration']}",
                step_type=step_type,
                success=True,
                execution_time=node["duration"],
                framework="langgraph"
            )

    print(f"\n✅ Cycle Graph 실행:")
    for iteration in cycle_graph["iterations"]:
        print(f"\n  Iteration {iteration['iteration']}:")
        for node in iteration["nodes"]:
            if node["name"] == "check":
                print(f"    - check: condition={node.get('condition')}, result={node.get('result')}")
            else:
                quality = node.get("state", {}).get("quality", 0)
                print(f"    - {node['name']}: quality={quality:.2f}")
    print(f"\n  총 반복: {len(cycle_graph['iterations'])}회")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 5: Multi-Agent Graph (Agent Communication)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Multi-Agent Graph - Agent 간 협업")
    print("=" * 80)

    print("""
Graph 구조:
START → coordinator
          ├─ researcher → analyst ─┐
          └─ writer → reviewer ────┼→ coordinator → END

→ 여러 Agent가 협업하여 작업 수행
    """)

    multi_agent_graph = {
        "task_id": "multi_agent_001",
        "question": "연구 보고서 작성",
        "nodes": [
            {
                "name": "coordinator",
                "agent": "Coordinator",
                "action": "작업 분배",
                "state_out": {"tasks": ["research", "write"]},
                "duration": 0.2
            },
            {
                "name": "researcher",
                "agent": "Researcher",
                "action": "데이터 수집",
                "state_out": {"data": "research_results"},
                "duration": 1.5
            },
            {
                "name": "analyst",
                "agent": "Analyst",
                "action": "데이터 분석",
                "state_out": {"insights": "analysis_results"},
                "duration": 1.2
            },
            {
                "name": "writer",
                "agent": "Writer",
                "action": "초안 작성",
                "state_out": {"draft": "initial_draft"},
                "duration": 2.0
            },
            {
                "name": "reviewer",
                "agent": "Reviewer",
                "action": "검토 및 피드백",
                "state_out": {"feedback": "review_comments"},
                "duration": 0.8
            },
            {
                "name": "coordinator_final",
                "agent": "Coordinator",
                "action": "최종 통합",
                "state_out": {"final_report": "complete"},
                "duration": 0.5
            }
        ],
        "agent_interactions": [
            {"from": "coordinator", "to": "researcher", "type": "delegation"},
            {"from": "coordinator", "to": "writer", "type": "delegation"},
            {"from": "researcher", "to": "analyst", "type": "communication"},
            {"from": "writer", "to": "reviewer", "type": "communication"},
            {"from": "analyst", "to": "coordinator_final", "type": "communication"},
            {"from": "reviewer", "to": "coordinator_final", "type": "communication"}
        ],
        "response": "complete",
        "ground_truth": ""
    }

    total_time = sum(node["duration"] for node in multi_agent_graph["nodes"])

    task = create_taskresult(
        task_id=multi_agent_graph["task_id"],
        task_type="langgraph_multi_agent",
        question=multi_agent_graph["question"],
        response=multi_agent_graph["response"],
        ground_truth=multi_agent_graph["ground_truth"],
        execution_time=total_time
    )
    monitor.record_task(task)

    # Workflow tracking
    for node in multi_agent_graph["nodes"]:
        monitor.workflow_tracker.track_step(
            task_id=multi_agent_graph["task_id"],
            step_name=node["name"],
            step_type="agent_task",
            success=True,
            execution_time=node["duration"],
            framework="langgraph"
        )

    # Agent coordination tracking
    for interaction in multi_agent_graph["agent_interactions"]:
        monitor.agent_coordination_tracker.track_interaction(
            task_id=multi_agent_graph["task_id"],
            from_agent=interaction["from"],
            to_agent=interaction["to"],
            interaction_type=interaction["type"],
            success=True,
            context={"framework": "langgraph"}
        )

    print(f"\n✅ Multi-Agent Graph 실행:")
    for i, node in enumerate(multi_agent_graph["nodes"], 1):
        print(f"  {i}. {node['name']} ({node['agent']})")
        print(f"     Action: {node['action']}")
        print(f"     Duration: {node['duration']:.2f}s")
    print(f"\n  Agent Interactions: {len(multi_agent_graph['agent_interactions'])}개")
    print(f"  총 실행 시간: {total_time:.2f}s")

    # ========================================================================
    # Part 6: 전체 통계 및 LangGraph 특화 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 통계 및 LangGraph 분석")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n🔀 LangGraph Framework 통계:")
    print(f"  - Graph 유형:")
    print(f"    • Linear Graph: 1")
    print(f"    • Conditional Graph: 1 (분기)")
    print(f"    • Parallel Graph: 1 (병렬 처리)")
    print(f"    • Cycle Graph: 1 (반복 4회)")
    print(f"    • Multi-Agent Graph: 1 (6개 Agent)")

    print(f"\n📊 성능 메트릭:")
    latency_metrics = report.efficiency_metrics.get('latency', {})
    print(f"  - 평균 지연시간: {latency_metrics.get('mean', 0):.3f}s")
    print(f"  - P95 지연시간: {latency_metrics.get('p95', 0):.3f}s")

    # Workflow execution
    workflow_rate_data = monitor.workflow_tracker.calculate_execution_success_rate()
    workflow_rate = workflow_rate_data.get('execution_success_rate', 0) if isinstance(workflow_rate_data, dict) else workflow_rate_data

    print(f"\n🔄 Workflow 실행:")
    print(f"  - 성공률: {workflow_rate:.1f}%")
    print(f"  - 병렬 처리: {(1 - parallel_time/sequential_time)*100:.0f}% 시간 절약")
    print(f"  - Cycle 반복: {len(cycle_graph['iterations'])}회")

    # Agent coordination
    coord_score_data = monitor.agent_coordination_tracker.calculate_coordination_score()
    coord_score = coord_score_data.get('coordination_score', 0)

    print(f"\n🤝 Agent Coordination (Multi-Agent Graph):")
    print(f"  - Coordination Score: {coord_score:.1f}/100")
    print(f"  - Interactions: {len(multi_agent_graph['agent_interactions'])}개")

    print(f"\n💡 LangGraph 특징:")
    print(f"  - State Management: 5개 Graph에서 상태 전달 성공")
    print(f"  - Conditional Edge: 조건부 분기 처리")
    print(f"  - Parallel Execution: {(1 - parallel_time/sequential_time)*100:.0f}% 성능 향상")
    print(f"  - Cycle Control: 안전한 반복 실행 ({len(cycle_graph['iterations'])}회)")

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    print(f"\n✅ LangGraph Integration Report:")
    print(f"  - Framework: LangGraph")
    print(f"  - Graph Types: 5")
    print(f"  - Workflow Success Rate: {workflow_rate:.1f}%")
    print(f"  - Agent Coordination Score: {coord_score:.1f}/100")

    # 결과 저장
    filename = f"{FILE_PREFIX}langgraph_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    print("\n" + "=" * 80)
    print("🎉 LangGraph 통합 평가 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ Linear Graph (순차 실행)
2. ✅ Conditional Graph (조건부 분기)
3. ✅ Parallel Graph (병렬 처리)
4. ✅ Cycle Graph (반복 실행)
5. ✅ Multi-Agent Graph (Agent 협업)

🔍 LangGraph 특징:
- State-based Workflow: 상태 중심 설계
- Conditional Edge: 동적 분기
- Parallel Execution: 성능 최적화
- Cycle Detection: 무한 루프 방지
- Agent Orchestration: Multi-Agent 조율

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py
  → {filename} 선택
  → Workflow, Agent Coordination 확인

🚀 다음 단계:
  level_3_production/05_transparency.py: 투명성 및 디버깅
    """)

if __name__ == "__main__":
    main()
