#!/usr/bin/env python3
"""
Level 2 Advanced - Example 06: Workflow Execution 평가
======================================================

FILE_PREFIX: [L2-06]_

🎯 주제: Workflow Execution 패턴 및 평가

📚 학습 내용:
1. WorkflowExecutionTracker 활용
2. 복잡한 워크플로우 실행 추적
3. 병렬 실행 및 에러 처리
4. Step-by-step 성공률 분석

🔍 핵심 개념:
- Workflow Step Types: agent_task, tool_call, decision, parallel_group
- Execution Success Rate: 단계별 성공률
- Critical Path: 주요 실행 경로
- Error Recovery: 오류 복구 패턴

실행 방법:
    python level_2_advanced/06_workflow.py
"""

FILE_PREFIX = "[L2-06]_"

from agent_evaluator import PerformanceMonitor, create_taskresult
import time

def main():
    print("=" * 80)
    print("🔄 Level 2 Advanced - Workflow Execution 평가")
    print("=" * 80)

    monitor = PerformanceMonitor()

    print("""
🔄 Workflow Execution Metrics:
- Execution Success Rate: 전체 Step 성공률
- Avg Steps per Task: Task당 평균 Step 수
- Critical Path Duration: 주요 경로 실행 시간
- Error Recovery Rate: 오류 복구율

📊 Step Types:
- agent_task: Agent가 수행하는 작업
- tool_call: 도구 호출
- decision: 조건부 분기
- parallel_group: 병렬 실행 그룹
    """)

    # ========================================================================
    # Part 1: Linear Workflow (선형 워크플로우)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Linear Workflow - 순차적 실행")
    print("=" * 80)

    print("""
시나리오: 간단한 데이터 처리 파이프라인
1. Data Ingestion (데이터 수집)
2. Data Validation (검증)
3. Data Transformation (변환)
4. Data Storage (저장)
→ 각 단계가 순차적으로 실행
    """)

    linear_steps = [
        {
            "name": "Data Ingestion",
            "type": "agent_task",
            "success": True,
            "duration": 1.0,
            "output": "1000 records collected"
        },
        {
            "name": "Data Validation",
            "type": "agent_task",
            "success": True,
            "duration": 0.8,
            "output": "All records valid"
        },
        {
            "name": "Data Transformation",
            "type": "tool_call",
            "success": True,
            "duration": 1.5,
            "output": "Transformed to JSON format"
        },
        {
            "name": "Data Storage",
            "type": "tool_call",
            "success": True,
            "duration": 0.7,
            "output": "Stored in database"
        }
    ]

    task_id = "linear_workflow_001"
    total_time = 0

    for i, step in enumerate(linear_steps, 1):
        monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step["name"],
            step_type=step["type"],
            success=step["success"],
            execution_time=step["duration"],
            metadata={"step_number": i, "output": step["output"]}
        )
        total_time += step["duration"]
        status = "✓" if step["success"] else "❌"
        print(f"  {status} Step {i}: {step['name']} ({step['type']})")
        print(f"    Duration: {step['duration']:.1f}s, Output: {step['output']}")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="workflow",
        question="데이터 처리 파이프라인 실행",
        response="파이프라인 완료",
        ground_truth="",
        execution_time=total_time
    )
    monitor.record_task(task)

    # Calculate statistics manually
    total_steps = len(linear_steps)
    successful = sum(1 for s in linear_steps if s["success"])
    success_rate = (successful / total_steps * 100) if total_steps > 0 else 0
    total_duration = sum(s["duration"] for s in linear_steps)
    avg_duration = total_duration / total_steps if total_steps > 0 else 0

    print(f"\n📊 Linear Workflow Statistics:")
    print(f"  - Total Steps: {total_steps}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Total Duration: {total_duration:.1f}s")
    print(f"  - Avg Step Duration: {avg_duration:.2f}s")
    print(f"  ✓ 분석: 모든 단계 순차 실행 성공")

    # ========================================================================
    # Part 2: Branching Workflow (분기 워크플로우)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: Branching Workflow - 조건부 분기")
    print("=" * 80)

    print("""
시나리오: 사용자 등록 처리
1. Validate Input (입력 검증)
2. Decision: 신규 vs 기존 사용자
   A. 신규 → Create Account → Send Welcome Email
   B. 기존 → Update Profile → Send Notification
3. Log Activity (활동 기록)
    """)

    # 신규 사용자 경로
    branching_steps = [
        {
            "name": "Validate Input",
            "type": "agent_task",
            "success": True,
            "duration": 0.5
        },
        {
            "name": "User Type Decision",
            "type": "decision",
            "success": True,
            "duration": 0.1,
            "metadata": {"decision": "new_user"}
        },
        {
            "name": "Create Account",
            "type": "agent_task",
            "success": True,
            "duration": 1.2
        },
        {
            "name": "Send Welcome Email",
            "type": "tool_call",
            "success": True,
            "duration": 0.8
        },
        {
            "name": "Log Activity",
            "type": "tool_call",
            "success": True,
            "duration": 0.3
        }
    ]

    task_id = "branching_001"
    total_time = 0

    for i, step in enumerate(branching_steps, 1):
        monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step["name"],
            step_type=step["type"],
            success=step["success"],
            execution_time=step["duration"],
            metadata=step.get("metadata", {})
        )
        total_time += step["duration"]
        status = "✓" if step["success"] else "❌"
        print(f"  {status} Step {i}: {step['name']} ({step['type']})")
        if step.get("metadata"):
            print(f"    Metadata: {step['metadata']}")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="workflow",
        question="사용자 등록 처리",
        response="등록 완료",
        ground_truth="",
        execution_time=total_time
    )
    monitor.record_task(task)

    # Calculate statistics
    total_steps = len(branching_steps)
    successful = sum(1 for s in branching_steps if s["success"])
    success_rate = (successful / total_steps * 100) if total_steps > 0 else 0

    print(f"\n📊 Branching Workflow Statistics:")
    print(f"  - Total Steps: {total_steps}")
    print(f"  - Decision Points: 1")
    print(f"  - Path Taken: New User Path")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  ✓ 분석: 조건부 분기 성공적으로 처리")

    # ========================================================================
    # Part 3: Parallel Workflow (병렬 워크플로우)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Parallel Workflow - 병렬 실행")
    print("=" * 80)

    print("""
시나리오: 미디어 처리 파이프라인
1. Upload File (파일 업로드)
2. Parallel Processing:
   - Generate Thumbnail (썸네일 생성)
   - Extract Metadata (메타데이터 추출)
   - Virus Scan (바이러스 검사)
   - Compress File (압축)
3. Save Results (결과 저장)
→ 2단계는 병렬 실행으로 시간 단축
    """)

    parallel_steps = [
        {
            "name": "Upload File",
            "type": "tool_call",
            "success": True,
            "duration": 2.0
        },
        # 병렬 실행 시작
        {
            "name": "Generate Thumbnail",
            "type": "parallel_group",
            "success": True,
            "duration": 1.5
        },
        {
            "name": "Extract Metadata",
            "type": "parallel_group",
            "success": True,
            "duration": 1.2
        },
        {
            "name": "Virus Scan",
            "type": "parallel_group",
            "success": True,
            "duration": 2.5  # 가장 오래 걸림
        },
        {
            "name": "Compress File",
            "type": "parallel_group",
            "success": True,
            "duration": 1.8
        },
        # 병렬 실행 종료
        {
            "name": "Save Results",
            "type": "tool_call",
            "success": True,
            "duration": 0.5
        }
    ]

    task_id = "parallel_001"

    # 순차 실행 시간 vs 병렬 실행 시간
    sequential_time = sum(step["duration"] for step in parallel_steps)
    parallel_time = (
        parallel_steps[0]["duration"] +  # Upload
        max(parallel_steps[1:5], key=lambda x: x["duration"])["duration"] +  # Parallel (최대값)
        parallel_steps[5]["duration"]  # Save
    )

    for i, step in enumerate(parallel_steps, 1):
        monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step["name"],
            step_type=step["type"],
            success=step["success"],
            execution_time=step["duration"],
            metadata={"parallel": step["type"] == "parallel_group"}
        )
        parallel_marker = "⚡" if step["type"] == "parallel_group" else "→"
        print(f"  {parallel_marker} Step {i}: {step['name']} ({step['duration']:.1f}s)")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="workflow",
        question="미디어 처리 파이프라인",
        response="처리 완료",
        ground_truth="",
        execution_time=parallel_time  # 병렬 실행 시간
    )
    monitor.record_task(task)

    print(f"\n📊 Parallel Workflow Statistics:")
    print(f"  - Total Steps: {len(parallel_steps)}")
    print(f"  - Parallel Steps: 4")
    print(f"  - Sequential Time: {sequential_time:.1f}s")
    print(f"  - Parallel Time: {parallel_time:.1f}s")
    print(f"  - Time Saved: {sequential_time - parallel_time:.1f}s ({(1 - parallel_time/sequential_time) * 100:.1f}% faster)")
    print(f"  ✓ 분석: 병렬 처리로 {(1 - parallel_time/sequential_time) * 100:.0f}% 성능 향상")

    # ========================================================================
    # Part 4: Error Recovery Workflow (에러 복구)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Error Recovery Workflow - 오류 처리 및 복구")
    print("=" * 80)

    print("""
시나리오: API 호출 with Retry
1. Prepare Request (요청 준비)
2. Call API (API 호출) → 실패
3. Retry Logic (재시도) → 성공
4. Parse Response (응답 파싱)
5. Validate Data (데이터 검증) → 실패
6. Error Handler (에러 처리)
7. Fallback Strategy (대체 전략)
    """)

    error_recovery_steps = [
        {
            "name": "Prepare Request",
            "type": "agent_task",
            "success": True,
            "duration": 0.3
        },
        {
            "name": "Call API",
            "type": "tool_call",
            "success": False,  # ❌ 실패
            "duration": 1.0,
            "error": "Connection timeout"
        },
        {
            "name": "Retry Logic - Attempt 1",
            "type": "tool_call",
            "success": False,  # ❌ 실패
            "duration": 1.2,
            "error": "Still timeout"
        },
        {
            "name": "Retry Logic - Attempt 2",
            "type": "tool_call",
            "success": True,  # ✓ 성공
            "duration": 1.5
        },
        {
            "name": "Parse Response",
            "type": "agent_task",
            "success": True,
            "duration": 0.5
        },
        {
            "name": "Validate Data",
            "type": "agent_task",
            "success": False,  # ❌ 실패
            "duration": 0.4,
            "error": "Invalid format"
        },
        {
            "name": "Error Handler",
            "type": "decision",
            "success": True,
            "duration": 0.2
        },
        {
            "name": "Fallback Strategy",
            "type": "agent_task",
            "success": True,
            "duration": 0.8,
            "output": "Used cached data"
        }
    ]

    task_id = "error_recovery_001"
    total_time = 0

    for i, step in enumerate(error_recovery_steps, 1):
        monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step["name"],
            step_type=step["type"],
            success=step["success"],
            execution_time=step["duration"],
            metadata={
                "error": step.get("error", ""),
                "output": step.get("output", "")
            }
        )
        total_time += step["duration"]
        status = "✓" if step["success"] else "❌"
        print(f"  {status} Step {i}: {step['name']}")
        if not step["success"]:
            print(f"    Error: {step.get('error', 'Unknown')}")
        elif step.get("output"):
            print(f"    Output: {step['output']}")

    # Task 기록
    task = create_taskresult(
        task_id=task_id,
        task_type="workflow",
        question="API 호출 및 데이터 처리",
        response="Fallback으로 완료",
        ground_truth="",
        execution_time=total_time
    )
    monitor.record_task(task)

    # Calculate statistics
    total_steps = len(error_recovery_steps)
    successful = sum(1 for s in error_recovery_steps if s["success"])
    success_rate = (successful / total_steps * 100) if total_steps > 0 else 0
    failed_steps = total_steps - successful
    recovery_steps = 2  # Retry + Fallback

    print(f"\n📊 Error Recovery Workflow Statistics:")
    print(f"  - Total Steps: {total_steps}")
    print(f"  - Failed Steps: {failed_steps}")
    print(f"  - Recovery Steps: {recovery_steps}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Recovery Rate: {recovery_steps / failed_steps * 100:.1f}% ({recovery_steps}/{failed_steps})" if failed_steps > 0 else "")
    print(f"  ✓ 분석: 오류 발생 후 성공적으로 복구")

    # ========================================================================
    # Part 5: Complex Multi-Stage Workflow (복합 워크플로우)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Complex Multi-Stage Workflow - 복합 실행")
    print("=" * 80)

    print("""
시나리오: E-commerce 주문 처리 시스템
1. Order Received (주문 접수)
2. Inventory Check (재고 확인)
   - Decision: 재고 있음/없음
3. Payment Processing (결제 처리)
   - Parallel: Card Validation + Fraud Check
4. Shipping Preparation (배송 준비)
   - Parallel: Label Generation + Notification
5. Order Completion (주문 완료)
    """)

    complex_workflow = [
        # Stage 1: Order Reception
        {
            "name": "Order Received",
            "type": "agent_task",
            "success": True,
            "duration": 0.3,
            "stage": "Reception"
        },
        {
            "name": "Parse Order Details",
            "type": "tool_call",
            "success": True,
            "duration": 0.2,
            "stage": "Reception"
        },
        # Stage 2: Inventory Check
        {
            "name": "Check Inventory",
            "type": "tool_call",
            "success": True,
            "duration": 0.5,
            "stage": "Inventory"
        },
        {
            "name": "Inventory Decision",
            "type": "decision",
            "success": True,
            "duration": 0.1,
            "stage": "Inventory",
            "metadata": {"decision": "in_stock"}
        },
        # Stage 3: Payment (Parallel)
        {
            "name": "Card Validation",
            "type": "parallel_group",
            "success": True,
            "duration": 1.0,
            "stage": "Payment"
        },
        {
            "name": "Fraud Check",
            "type": "parallel_group",
            "success": True,
            "duration": 1.5,
            "stage": "Payment"
        },
        {
            "name": "Process Payment",
            "type": "tool_call",
            "success": True,
            "duration": 0.8,
            "stage": "Payment"
        },
        # Stage 4: Shipping (Parallel)
        {
            "name": "Generate Shipping Label",
            "type": "parallel_group",
            "success": True,
            "duration": 0.7,
            "stage": "Shipping"
        },
        {
            "name": "Send Customer Notification",
            "type": "parallel_group",
            "success": True,
            "duration": 0.5,
            "stage": "Shipping"
        },
        {
            "name": "Update Inventory",
            "type": "tool_call",
            "success": True,
            "duration": 0.4,
            "stage": "Shipping"
        },
        # Stage 5: Completion
        {
            "name": "Order Completion",
            "type": "agent_task",
            "success": True,
            "duration": 0.3,
            "stage": "Completion"
        },
        {
            "name": "Log Transaction",
            "type": "tool_call",
            "success": True,
            "duration": 0.2,
            "stage": "Completion"
        }
    ]

    task_id = "complex_001"

    # Stage별 그룹화
    stages = {}
    for step in complex_workflow:
        stage = step["stage"]
        if stage not in stages:
            stages[stage] = []
        stages[stage].append(step)

    print("\nWorkflow Stages:")
    for stage_name, steps in stages.items():
        print(f"\n  📁 {stage_name} Stage ({len(steps)} steps):")
        for step in steps:
            monitor.workflow_tracker.track_step(
                task_id=task_id,
                step_name=step["name"],
                step_type=step["type"],
                success=step["success"],
                execution_time=step["duration"],
                metadata=step.get("metadata", {"stage": stage_name}),
                framework="custom"
            )
            parallel_marker = "⚡" if step["type"] == "parallel_group" else "→"
            print(f"    {parallel_marker} {step['name']} ({step['duration']:.1f}s)")

    # Task 기록
    total_time = sum(step["duration"] for step in complex_workflow)
    task = create_taskresult(
        task_id=task_id,
        task_type="workflow",
        question="E-commerce 주문 처리",
        response="주문 완료",
        ground_truth="",
        execution_time=total_time
    )
    monitor.record_task(task)

    # Calculate statistics
    total_steps = len(complex_workflow)
    successful = sum(1 for s in complex_workflow if s["success"])
    success_rate = (successful / total_steps * 100) if total_steps > 0 else 0
    total_duration = sum(s["duration"] for s in complex_workflow)

    print(f"\n📊 Complex Workflow Statistics:")
    print(f"  - Total Stages: {len(stages)}")
    print(f"  - Total Steps: {total_steps}")
    print(f"  - Success Rate: {success_rate:.1f}%")
    print(f"  - Total Duration: {total_duration:.1f}s")
    print(f"  - Parallel Steps: 4 (2 groups)")
    print(f"  ✓ 분석: 복합 워크플로우 성공적으로 실행")

    # ========================================================================
    # Part 6: 전체 통계 및 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 Workflow 통계")
    print("=" * 80)

    overall_rate_data = monitor.workflow_tracker.calculate_execution_success_rate()
    overall_rate = overall_rate_data.get('execution_success_rate', 0) if isinstance(overall_rate_data, dict) else overall_rate_data

    print(f"\n🔄 Overall Workflow Execution Metrics:")
    print(f"  - Execution Success Rate: {overall_rate:.1f}%")

    # Step Type 분포 (샘플에서 계산)
    print(f"\n📊 Step Type Distribution (샘플 기준):")
    all_steps = linear_steps + branching_steps + parallel_steps + error_recovery_steps + complex_workflow
    type_counts = {}
    for step in all_steps:
        stype = step.get("type", step.get("step_type", "unknown"))
        type_counts[stype] = type_counts.get(stype, 0) + 1

    total_count = len(all_steps)
    for stype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_count * 100) if total_count > 0 else 0
        print(f"  - {stype}: {count}회 ({percentage:.1f}%)")

    # 성공률 평가
    print(f"\n🎯 Workflow Quality Assessment:")
    if overall_rate >= 90:
        print(f"  ✅ 우수 (Success Rate: {overall_rate:.1f}%)")
        print(f"     - 매우 안정적인 워크플로우 실행")
    elif overall_rate >= 70:
        print(f"  ⚠️ 양호 (Success Rate: {overall_rate:.1f}%)")
        print(f"     - 일부 개선 필요")
    else:
        print(f"  ❌ 개선 필요 (Success Rate: {overall_rate:.1f}%)")
        print(f"     - 높은 실패율, 에러 처리 강화 필요")

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n✅ Workflow Execution Report:")
    print(f"  - Execution Success Rate: {overall_rate:.1f}%")

    # 결과 저장
    filename = f"{FILE_PREFIX}workflow_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    print("\n" + "=" * 80)
    print("🎉 Workflow Execution 평가 학습 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ Workflow Step Types (agent_task, tool_call, decision, parallel_group)
2. ✅ 실행 패턴 (선형, 분기, 병렬, 에러 복구)
3. ✅ 성능 최적화 (병렬 처리로 시간 단축)
4. ✅ 에러 처리 및 Fallback 전략

🔍 실제 활용:
- LangGraph: State machine workflow
- CrewAI: Sequential/Parallel task execution
- Temporal: Workflow orchestration

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py
  → {filename} 선택
  → Layer 2 Metrics 탭에서 Workflow Execution 상세 확인

🎓 Layer 2 (Agentic AI) 완료:
  ✅ 04_tool_selection.py: Tool 선택 패턴
  ✅ 05_multi_agent.py: Multi-Agent 협업
  ✅ 06_workflow.py: Workflow 실행

🚀 다음 단계:
  level_3_production/: 프로덕션 레벨 평가 (CrewAI, Cost Optimization)
    """)

if __name__ == "__main__":
    main()
