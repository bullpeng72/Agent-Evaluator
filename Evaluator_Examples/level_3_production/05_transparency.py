#!/usr/bin/env python3
"""
Level 3 Production - Example 05: 투명성 관리
=============================================

FILE_PREFIX: [L3-05]_

🎯 주제: AI 시스템 투명성 및 디버깅

📚 학습 내용:
1. Trace 기록 및 분석
2. Annotation (주석) 관리
3. 디버깅 패턴 및 Best Practices
4. 설명 가능성 (Explainability)

🔍 핵심 개념:
- Trace: 실행 경로 추적
- Annotation: 추가 설명 및 메타데이터
- Debugging: 오류 진단 및 수정
- Explainability: 결정 과정 설명

실행 방법:
    python level_3_production/05_transparency.py
"""

FILE_PREFIX = "[L3-05]_"

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.utils.test_transparency_manager import (
    TestTransparencyManager,
    AnnotationType,
    TestStepStatus
)
import time
import json

def main():
    print("=" * 80)
    print("🔍 Level 3 Production - 투명성 관리")
    print("=" * 80)

    monitor = PerformanceMonitor(enable_hallucination_detection=True)

    # Initialize TestTransparencyManager for dashboard integration
    transparency = TestTransparencyManager()
    print(f"\n🔍 TestTransparencyManager 초기화 완료")
    print(f"  - Output Directory: {transparency.output_dir}")
    print(f"  - Dashboard Integration: Enabled")

    print("""
🔍 Transparency & Debugging:
- Trace: 실행 경로 기록
- Annotation: 설명 및 메타데이터
- Error Tracking: 오류 추적 및 분석
- Explainability: 의사결정 과정 설명

📊 측정 메트릭:
- Layer 1: Hallucination Detection, Error Rate
- Transparency: Trace Depth, Annotation Coverage
- Debugging: Error Recovery Time, Debug Session Count
    """)

    # ========================================================================
    # Part 1: Basic Trace Recording
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Basic Trace Recording - 실행 추적")
    print("=" * 80)

    print("""
시나리오: 단순 질문 응답
→ 각 단계의 실행 흐름을 상세히 기록

Trace Levels:
- Level 0: Entry/Exit만 기록
- Level 1: 주요 단계 기록
- Level 2: 상세 단계 기록 (디버깅)
    """)

    trace_execution = {
        "task_id": "trace_001",
        "question": "Python에서 리스트와 튜플의 차이는?",
        "trace_level": 2,
        "trace_steps": [
            {
                "timestamp": "2024-01-01T10:00:00.000",
                "level": 0,
                "event": "ENTRY",
                "function": "process_question",
                "args": {"question": "Python에서 리스트와 튜플의 차이는?"}
            },
            {
                "timestamp": "2024-01-01T10:00:00.100",
                "level": 1,
                "event": "STEP",
                "function": "parse_question",
                "result": {"intent": "comparison", "entities": ["list", "tuple"]}
            },
            {
                "timestamp": "2024-01-01T10:00:00.500",
                "level": 1,
                "event": "STEP",
                "function": "retrieve_knowledge",
                "result": {"docs_retrieved": 3, "relevance": 0.92}
            },
            {
                "timestamp": "2024-01-01T10:00:01.200",
                "level": 1,
                "event": "STEP",
                "function": "generate_response",
                "result": {"tokens": 85, "confidence": 0.95}
            },
            {
                "timestamp": "2024-01-01T10:00:01.300",
                "level": 0,
                "event": "EXIT",
                "function": "process_question",
                "return_value": "리스트는 변경 가능(mutable)하고 튜플은 변경 불가능(immutable)합니다."
            }
        ],
        "response": "리스트는 변경 가능(mutable)하고 튜플은 변경 불가능(immutable)합니다.",
        "ground_truth": "리스트는 mutable, 튜플은 immutable",
        "context": "Python에서 리스트는 [ ]로 표현되며 변경 가능하고, 튜플은 ( )로 표현되며 변경 불가능합니다.",
        "execution_time": 1.3
    }

    task = create_taskresult(
        task_id=trace_execution["task_id"],
        task_type="transparency_trace",
        question=trace_execution["question"],
        response=trace_execution["response"],
        ground_truth=trace_execution["ground_truth"],
        execution_time=trace_execution["execution_time"]
    )
    monitor.record_task(
        task,
        context=trace_execution["context"],
        response=trace_execution["response"]
    )

    print(f"\n✅ Trace Recording (Level {trace_execution['trace_level']}):")
    for i, step in enumerate(trace_execution["trace_steps"], 1):
        indent = "  " * step["level"]
        print(f"  {i}. {indent}[{step['event']}] {step['function']}")
        if "result" in step:
            print(f"     {indent}Result: {step['result']}")
    print(f"\n  총 Trace Step: {len(trace_execution['trace_steps'])}개")
    print(f"  Trace Depth: {max(s['level'] for s in trace_execution['trace_steps'])} levels")

    # Record trace to dashboard
    trace_id = transparency.start_metric_calculation(
        metric_name="trace_recording",
        metric_type="basic",
        task_id=trace_execution["task_id"]
    )

    for i, step in enumerate(trace_execution["trace_steps"]):
        transparency.add_calculation_step(
            trace_id=trace_id,
            step_name=step["function"],
            description=f"[{step['event']}] Level {step['level']}",
            input_data={"timestamp": step["timestamp"]},
            output_data=step.get("result", None),
            status=TestStepStatus.SUCCESS
        )

    transparency.complete_metric_calculation(
        trace_id=trace_id,
        final_value=max(s['level'] for s in trace_execution['trace_steps']) / 3.0,  # Normalized depth score
        metadata={
            "total_steps": len(trace_execution['trace_steps']),
            "trace_depth": max(s['level'] for s in trace_execution['trace_steps']),
            "execution_time": trace_execution["execution_time"]
        }
    )
    print(f"  📊 Dashboard Trace 저장: {trace_id}")

    # ========================================================================
    # Part 2: Annotation & Metadata
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: Annotation & Metadata - 설명 추가")
    print("=" * 80)

    print("""
시나리오: 복잡한 추론 과정에 주석 추가
→ 각 단계의 의도와 근거를 명확히 기록

Annotation Types:
- Rationale: 왜 이 단계를 실행했는가?
- Confidence: 이 결과에 대한 확신도
- Alternative: 고려했지만 선택하지 않은 대안
    """)

    annotated_execution = {
        "task_id": "annotation_001",
        "question": "기후 변화를 막기 위한 가장 효과적인 방법은?",
        "reasoning_steps": [
            {
                "step": "문제 분석",
                "action": "질문 분해",
                "annotation": {
                    "rationale": "복잡한 질문이므로 하위 질문으로 분해 필요",
                    "confidence": 0.9,
                    "alternatives": ["직접 답변", "유사 사례 검색"]
                },
                "result": ["재생에너지?", "탄소 감축?", "정책?"],
                "duration": 0.3
            },
            {
                "step": "정보 수집",
                "action": "각 측면의 효과 분석",
                "annotation": {
                    "rationale": "과학적 근거 기반 답변을 위해 데이터 필요",
                    "confidence": 0.85,
                    "alternatives": ["전문가 의견", "일반적 답변"]
                },
                "result": {
                    "renewable": "30% 감축 가능",
                    "carbon_tax": "20% 감축 가능",
                    "policy": "50% 감축 가능 (종합)"
                },
                "duration": 1.5
            },
            {
                "step": "결론 도출",
                "action": "종합 정책이 가장 효과적",
                "annotation": {
                    "rationale": "단일 방법보다 통합 접근이 효과적",
                    "confidence": 0.92,
                    "alternatives": ["재생에너지만 강조", "탄소세만 제안"]
                },
                "result": "종합적 정책 접근 (재생에너지 + 탄소 감축 + 규제)",
                "duration": 0.8
            }
        ],
        "response": "기후 변화를 막기 위해서는 재생에너지 확대, 탄소 감축, 정책 규제를 결합한 종합적 접근이 가장 효과적입니다.",
        "ground_truth": "종합적 정책 접근",
        "context": "기후 변화는 복합적 문제로 다각도의 해결책이 필요합니다.",
        "execution_time": 2.6
    }

    task = create_taskresult(
        task_id=annotated_execution["task_id"],
        task_type="transparency_annotation",
        question=annotated_execution["question"],
        response=annotated_execution["response"],
        ground_truth=annotated_execution["ground_truth"],
        execution_time=annotated_execution["execution_time"]
    )
    monitor.record_task(
        task,
        context=annotated_execution["context"],
        response=annotated_execution["response"]
    )

    print(f"\n✅ Annotated Reasoning:")
    for i, step in enumerate(annotated_execution["reasoning_steps"], 1):
        print(f"\n  Step {i}: {step['step']}")
        print(f"    Action: {step['action']}")
        print(f"    📝 Annotations:")
        ann = step["annotation"]
        print(f"      - Rationale: {ann['rationale']}")
        print(f"      - Confidence: {ann['confidence']:.0%}")
        print(f"      - Alternatives: {', '.join(ann['alternatives'])}")
        print(f"    Result: {step['result']}")
    print(f"\n  총 Reasoning Steps: {len(annotated_execution['reasoning_steps'])}개")
    print(f"  평균 Confidence: {sum(s['annotation']['confidence'] for s in annotated_execution['reasoning_steps']) / len(annotated_execution['reasoning_steps']):.0%}")

    # Add annotations to dashboard
    for i, step in enumerate(annotated_execution["reasoning_steps"], 1):
        annotation_id = transparency.add_annotation(
            target_type="metric",
            target_id=f"reasoning_step_{i}",
            annotation_type=AnnotationType.NOTE,
            priority="medium",
            title=f"{step['step']}: {step['action']}",
            content=f"Rationale: {step['annotation']['rationale']}. Confidence: {step['annotation']['confidence']:.0%}. Alternatives: {', '.join(step['annotation']['alternatives'])}",
            author="transparency_manager"
        )
        if i == 1:
            print(f"  📊 Dashboard Annotation 저장: {annotation_id} (+ {len(annotated_execution['reasoning_steps'])-1} more)")

    # ========================================================================
    # Part 3: Error Tracking & Debugging
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Error Tracking & Debugging - 오류 추적")
    print("=" * 80)

    print("""
시나리오: 오류 발생 및 복구 과정
→ 오류 발생 지점, 원인, 복구 과정을 상세히 기록

Error Types:
- Tool Error: Tool 실행 실패
- Validation Error: 입력/출력 검증 실패
- Timeout Error: 시간 초과
    """)

    error_tracking = {
        "task_id": "error_001",
        "question": "최신 뉴스에서 AI 관련 기사 3개 요약",
        "execution_attempts": [
            {
                "attempt": 1,
                "steps": [
                    {"name": "validate_input", "success": True, "duration": 0.1},
                    {"name": "fetch_news", "success": False, "duration": 2.0,
                     "error": {
                         "type": "ToolError",
                         "message": "API rate limit exceeded",
                         "stack_trace": "NewsAPI.fetch() line 45",
                         "timestamp": "2024-01-01T10:00:02.000"
                     }}
                ]
            },
            {
                "attempt": 2,
                "recovery_action": "retry_with_backoff",
                "backoff_time": 5.0,
                "steps": [
                    {"name": "validate_input", "success": True, "duration": 0.1},
                    {"name": "fetch_news", "success": False, "duration": 2.0,
                     "error": {
                         "type": "ToolError",
                         "message": "API rate limit still active",
                         "timestamp": "2024-01-01T10:00:09.000"
                     }}
                ]
            },
            {
                "attempt": 3,
                "recovery_action": "use_alternative_source",
                "steps": [
                    {"name": "validate_input", "success": True, "duration": 0.1},
                    {"name": "fetch_news_alternative", "success": True, "duration": 1.5,
                     "result": "3 articles retrieved"},
                    {"name": "summarize", "success": True, "duration": 1.2,
                     "result": "3 summaries generated"}
                ]
            }
        ],
        "response": "1. AI 반도체 발전 2. 자율주행 규제 3. ChatGPT 업데이트",
        "ground_truth": "",
        "execution_time": 12.0
    }

    task = create_taskresult(
        task_id=error_tracking["task_id"],
        task_type="transparency_error",
        question=error_tracking["question"],
        response=error_tracking["response"],
        ground_truth=error_tracking["ground_truth"],
        execution_time=error_tracking["execution_time"]
    )
    monitor.record_task(task)

    # Workflow tracking with errors
    for attempt in error_tracking["execution_attempts"]:
        for step in attempt["steps"]:
            monitor.workflow_tracker.track_step(
                task_id=error_tracking["task_id"],
                step_name=f"{step['name']}_attempt{attempt['attempt']}",
                step_type="tool_call" if "fetch" in step["name"] else "agent_task",
                success=step["success"],
                execution_time=step["duration"]
            )

    print(f"\n✅ Error Tracking & Recovery:")
    for attempt in error_tracking["execution_attempts"]:
        print(f"\n  Attempt {attempt['attempt']}:")
        if "recovery_action" in attempt:
            print(f"    Recovery: {attempt['recovery_action']}")
        for step in attempt["steps"]:
            status = "✓" if step["success"] else "❌"
            print(f"    {status} {step['name']}: {step['duration']:.1f}s")
            if "error" in step:
                err = step["error"]
                print(f"       Error: {err['type']} - {err['message']}")
                if "stack_trace" in err:
                    print(f"       Stack: {err['stack_trace']}")

    successful_attempts = sum(1 for a in error_tracking["execution_attempts"] if all(s["success"] for s in a["steps"]))
    print(f"\n  총 시도: {len(error_tracking['execution_attempts'])}회")
    print(f"  성공: {successful_attempts}회")
    print(f"  최종 복구 시간: {error_tracking['execution_time']:.1f}s")

    # Log errors to dashboard audit log
    audit_count = 0
    for attempt in error_tracking["execution_attempts"]:
        for step in attempt["steps"]:
            if not step["success"] and "error" in step:
                transparency.log_event(
                    event_type="error",
                    user="transparency_manager",
                    action=f"{step['name']} 실패",
                    target_type="task",
                    target_id=error_tracking["task_id"],
                    details={
                        "attempt": attempt['attempt'],
                        "error_type": step["error"]["type"],
                        "error_message": step["error"]["message"],
                        "stack_trace": step["error"].get("stack_trace", ""),
                        "timestamp": step["error"]["timestamp"],
                        "duration": step["duration"],
                        "recovery_action": attempt.get("recovery_action", "none")
                    }
                )
                audit_count += 1
            elif step["success"] and attempt["attempt"] == 3:
                transparency.log_event(
                    event_type="evaluation",
                    user="transparency_manager",
                    action=f"{step['name']} 복구 성공",
                    target_type="task",
                    target_id=error_tracking["task_id"],
                    details={
                        "attempts": attempt['attempt'],
                        "duration": step["duration"],
                        "result": step.get("result", "")
                    }
                )
                audit_count += 1

    print(f"  📊 Dashboard Audit Log: {audit_count} events 저장")

    # ========================================================================
    # Part 4: Decision Explainability
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Decision Explainability - 의사결정 설명")
    print("=" * 80)

    print("""
시나리오: Tool 선택 과정 설명
→ Agent가 왜 특정 Tool을 선택했는지 설명

Explanation Components:
- Context: 현재 상황
- Options: 가능한 선택지
- Decision: 선택한 옵션
- Reasoning: 선택 이유
    """)

    explainability_case = {
        "task_id": "explain_001",
        "question": "서울에서 부산까지 가장 빠른 이동 방법은?",
        "decision_points": [
            {
                "point": "정보 수집 방법 선택",
                "context": "실시간 교통 정보 필요",
                "options": {
                    "search": {"speed": "medium", "accuracy": "high", "cost": "low"},
                    "database": {"speed": "fast", "accuracy": "medium", "cost": "none"},
                    "api": {"speed": "slow", "accuracy": "very_high", "cost": "high"}
                },
                "decision": "search",
                "reasoning": "정확도와 비용의 균형을 고려하여 search 선택",
                "confidence": 0.85,
                "expected_tools": ["search", "calculator"],
                "actual_tools": ["search"]
            },
            {
                "point": "이동 시간 계산",
                "context": "KTX, 비행기, 자동차 옵션 존재",
                "options": {
                    "calculator": {"precision": "high", "speed": "fast"},
                    "llm": {"precision": "medium", "speed": "slow", "explanation": "good"}
                },
                "decision": "calculator",
                "reasoning": "정확한 수치 계산이 필요하므로 calculator 선택",
                "confidence": 0.95,
                "expected_tools": ["search", "calculator"],
                "actual_tools": ["search", "calculator"]
            }
        ],
        "response": "KTX가 가장 빠른 방법으로, 약 2시간 30분 소요됩니다.",
        "ground_truth": "KTX (2시간 30분)",
        "execution_time": 1.8
    }

    task = create_taskresult(
        task_id=explainability_case["task_id"],
        task_type="transparency_explainability",
        question=explainability_case["question"],
        response=explainability_case["response"],
        ground_truth=explainability_case["ground_truth"],
        execution_time=explainability_case["execution_time"]
    )

    # Tool calls
    all_tools = []
    for dp in explainability_case["decision_points"]:
        all_tools.extend([{"tool": t, "success": True, "duration": 0.5} for t in dp["actual_tools"]])
    task.tool_calls = all_tools
    task.expected_tools = explainability_case["decision_points"][0]["expected_tools"]
    monitor.record_task(task)

    # Tool selection evaluation
    actual_tools_set = list(set(dp["decision"] for dp in explainability_case["decision_points"]))
    monitor.tool_selection_tracker.evaluate_selection(
        task_id=explainability_case["task_id"],
        expected_tools=explainability_case["decision_points"][0]["expected_tools"],
        actual_tools=actual_tools_set
    )

    print(f"\n✅ Decision Explainability:")
    for i, dp in enumerate(explainability_case["decision_points"], 1):
        print(f"\n  Decision Point {i}: {dp['point']}")
        print(f"    Context: {dp['context']}")
        print(f"    Options Considered:")
        for opt_name, opt_details in dp["options"].items():
            print(f"      - {opt_name}: {opt_details}")
        print(f"    ➜ Selected: {dp['decision']}")
        print(f"    Reasoning: {dp['reasoning']}")
        print(f"    Confidence: {dp['confidence']:.0%}")

    print(f"\n  Tool Selection:")
    print(f"    Expected: {explainability_case['decision_points'][0]['expected_tools']}")
    print(f"    Actual: {actual_tools_set}")
    selection_result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=explainability_case["task_id"],
        expected_tools=explainability_case["decision_points"][0]["expected_tools"],
        actual_tools=actual_tools_set
    )
    print(f"    F1 Score: {selection_result['f1_score']:.1f}%")

    # Record explainability trace to dashboard
    explainability_trace_id = transparency.start_metric_calculation(
        metric_name="decision_explainability",
        metric_type="advanced",
        task_id=explainability_case["task_id"]
    )

    for i, dp in enumerate(explainability_case["decision_points"], 1):
        transparency.add_calculation_step(
            trace_id=explainability_trace_id,
            step_name=dp["point"],
            description=f"{dp['context']} → Selected: {dp['decision']}",
            input_data={"context": dp["context"], "options": dp["options"]},
            output_data={
                "decision": dp["decision"],
                "reasoning": dp["reasoning"],
                "confidence": dp["confidence"],
                "options": list(dp["options"].keys())
            },
            status=TestStepStatus.SUCCESS
        )

    transparency.complete_metric_calculation(
        trace_id=explainability_trace_id,
        final_value=sum(dp["confidence"] for dp in explainability_case["decision_points"]) / len(explainability_case["decision_points"]),
        metadata={
            "decision_points": len(explainability_case["decision_points"]),
            "avg_confidence": sum(dp["confidence"] for dp in explainability_case["decision_points"]) / len(explainability_case["decision_points"]),
            "f1_score": selection_result['f1_score']
        }
    )
    print(f"  📊 Dashboard Explainability Trace 저장: {explainability_trace_id}")

    # ========================================================================
    # Part 5: Hallucination Detection
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Hallucination Detection - 환각 탐지")
    print("=" * 80)

    print("""
시나리오: 사실 기반 질문에 대한 응답 검증
→ Context와 일치하지 않는 내용 탐지

Hallucination Types:
- Factual Error: 사실 오류
- Contradiction: Context와 모순
- Fabrication: 근거 없는 정보 추가
    """)

    hallucination_cases = [
        {
            "task_id": "halluc_001",
            "question": "에펠탑의 높이는?",
            "response": "에펠탑은 324미터입니다.",
            "ground_truth": "324미터",
            "context": "에펠탑은 프랑스 파리에 있는 철탑으로 높이는 324미터입니다.",
            "is_hallucination": False,
            "execution_time": 0.8
        },
        {
            "task_id": "halluc_002",
            "question": "한국의 수도는?",
            "response": "한국의 수도는 부산입니다.",  # 잘못된 정보!
            "ground_truth": "서울",
            "context": "대한민국의 수도는 서울특별시입니다.",
            "is_hallucination": True,
            "hallucination_type": "factual_error",
            "execution_time": 0.7
        },
        {
            "task_id": "halluc_003",
            "question": "태양계의 행성 개수는?",
            "response": "태양계에는 9개의 행성이 있습니다. 명왕성을 포함하면 10개입니다.",  # 과거 정보 + 추가 오류
            "ground_truth": "8개",
            "context": "태양계에는 8개의 행성이 있습니다. 명왕성은 2006년 왜소행성으로 재분류되었습니다.",
            "is_hallucination": True,
            "hallucination_type": "fabrication",
            "execution_time": 0.9
        }
    ]

    for case in hallucination_cases:
        task = create_taskresult(
            task_id=case["task_id"],
            task_type="transparency_hallucination",
            question=case["question"],
            response=case["response"],
            ground_truth=case["ground_truth"],
            execution_time=case["execution_time"]
        )
        monitor.record_task(
            task,
            context=case["context"],
            response=case["response"]
        )

    print(f"\n✅ Hallucination Detection Results:")
    for case in hallucination_cases:
        status = "❌ HALLUCINATION" if case["is_hallucination"] else "✓ VALID"
        print(f"\n  {status} - {case['task_id']}")
        print(f"    Question: {case['question']}")
        print(f"    Response: {case['response']}")
        print(f"    Ground Truth: {case['ground_truth']}")
        if case["is_hallucination"]:
            print(f"    Type: {case['hallucination_type']}")

    hallucination_rate = sum(1 for c in hallucination_cases if c["is_hallucination"]) / len(hallucination_cases)
    print(f"\n  Hallucination Rate: {hallucination_rate:.0%} ({sum(1 for c in hallucination_cases if c['is_hallucination'])}/{len(hallucination_cases)})")

    # Record hallucination detection trace to dashboard
    hallucination_trace_id = transparency.start_metric_calculation(
        metric_name="hallucination_detection",
        metric_type="validation",
        task_id="halluc_validation"
    )

    for case in hallucination_cases:
        status = TestStepStatus.FAILED if case["is_hallucination"] else TestStepStatus.SUCCESS
        transparency.add_calculation_step(
            trace_id=hallucination_trace_id,
            step_name=f"validate_{case['task_id']}",
            description=f"Checking: {case['question']}",
            input_data={"question": case["question"], "context": case["context"], "response": case["response"]},
            output_data={
                "is_hallucination": case["is_hallucination"],
                "hallucination_type": case.get("hallucination_type", "none"),
                "ground_truth": case["ground_truth"]
            },
            status=status
        )

    transparency.complete_metric_calculation(
        trace_id=hallucination_trace_id,
        final_value=1.0 - hallucination_rate,  # Higher is better (accuracy)
        metadata={
            "hallucination_rate": hallucination_rate,
            "detected": sum(1 for c in hallucination_cases if c["is_hallucination"]),
            "total": len(hallucination_cases)
        }
    )
    print(f"  📊 Dashboard Hallucination Trace 저장: {hallucination_trace_id}")

    # ========================================================================
    # Part 6: 전체 통계 및 투명성 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 투명성 통계")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n🔍 Transparency 측정 항목:")
    print(f"  - Trace Recording: {len(trace_execution['trace_steps'])} steps")
    print(f"  - Annotation Coverage: {len(annotated_execution['reasoning_steps'])} steps")
    print(f"  - Error Tracking: {len(error_tracking['execution_attempts'])} attempts")
    print(f"  - Decision Points Explained: {len(explainability_case['decision_points'])}")
    print(f"  - Hallucination Cases: {len(hallucination_cases)}")

    print(f"\n📊 투명성 메트릭:")
    print(f"  - Trace Depth: {max(s['level'] for s in trace_execution['trace_steps'])} levels")
    print(f"  - Avg Confidence: {sum(s['annotation']['confidence'] for s in annotated_execution['reasoning_steps']) / len(annotated_execution['reasoning_steps']):.0%}")
    print(f"  - Error Recovery Rate: {successful_attempts}/{len(error_tracking['execution_attempts'])} ({successful_attempts/len(error_tracking['execution_attempts']):.0%})")
    print(f"  - Hallucination Rate: {hallucination_rate:.0%}")

    # Hallucination stats
    try:
        halluc_rate = monitor.hallucination_detector.get_hallucination_rate()
        print(f"\n🎯 Hallucination Detection:")
        print(f"  - Detection Rate: {halluc_rate:.1f}%")
    except:
        pass

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    print(f"\n✅ Transparency Management Report:")
    print(f"  - Trace Steps: {len(trace_execution['trace_steps'])}")
    print(f"  - Annotated Decisions: {len(annotated_execution['reasoning_steps'])}")
    print(f"  - Error Recovery Attempts: {len(error_tracking['execution_attempts'])}")
    print(f"  - Explained Decisions: {len(explainability_case['decision_points'])}")
    print(f"  - Hallucination Detection: {hallucination_rate:.0%} detected")

    # 결과 저장
    filename = f"{FILE_PREFIX}transparency_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    # ========================================================================
    # Part 7: 투명성 종합 리포트 생성 (Dashboard "상세 리포트" 용)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📋 투명성 종합 리포트 생성")
    print("=" * 80)

    # Generate comprehensive transparency report
    transparency_report = transparency.generate_transparent_report(
        task_id="transparency_evaluation_001",
        task_type="transparency_analysis",
        success=True,
        metadata={
            "environment": "production",
            "framework": "agent_evaluator",
            "model_name": "transparency_module",
            "evaluator": "transparency_manager",
            "description": "Level 3 Production - 투명성 관리 평가",
            "test_configuration": {
                "environment": "production",
                "framework": "agent_evaluator",
                "model_name": "transparency_module",
                "evaluator": "transparency_manager"
            }
        },
        monitor=monitor,
        auto_save=True
    )

    print(f"\n✅ 투명성 종합 리포트 생성 완료!")
    print(f"  - Report ID: {transparency_report['report_id']}")
    print(f"  - Task ID: {transparency_report['task_id']}")
    print(f"  - Success: {transparency_report['success']}")
    print(f"  - Generated At: {transparency_report['generated_at']}")

    # Report summary
    summary = transparency_report.get('summary', {})
    print(f"\n📊 리포트 요약:")
    print(f"  - Total Tasks: {summary.get('total_tasks', 0)}")
    print(f"  - Anomalies Detected: {summary.get('anomalies_detected', 0)}")
    print(f"  - Warnings: {summary.get('warnings', 0)}")
    print(f"  - Data Quality Score: {summary.get('data_quality_score', 0):.1f}/100")

    # Reliability analysis
    reliability = transparency_report.get('reliability_analysis', {})
    if reliability:
        print(f"\n🔬 신뢰성 분석:")
        print(f"  - Sample Size: {reliability.get('sample_size', 0)}")
        print(f"  - Sufficient: {'✅' if reliability.get('sufficient', False) else '⚠️'}")
        print(f"  - Confidence Level: {reliability.get('confidence_level', 0):.0f}%")
        print(f"  - Variance: {reliability.get('variance', 0):.4f}")

        if reliability.get('warnings'):
            print(f"\n  ⚠️ Warnings:")
            for warning in reliability['warnings']:
                print(f"    - {warning}")

    # Actionable insights
    insights = transparency_report.get('actionable_insights', [])
    if insights:
        print(f"\n💡 실행 가능한 인사이트: {len(insights)}개")
        for i, insight in enumerate(insights[:3], 1):  # Show first 3
            print(f"\n  {i}. [{insight['priority'].upper()}] {insight['title']}")
            print(f"     Category: {insight['category']}")
            print(f"     Current: {insight['current_state']}")
            print(f"     Action: {insight['action']}")

    reports_dir = transparency.output_dir / "transparent_reports"
    print(f"\n💾 리포트 저장 위치:")
    print(f"  {reports_dir}/{transparency_report['report_id']}.json")

    # Dashboard 투명성 데이터 요약
    print(f"\n🔍 Dashboard 투명성 데이터:")
    print(f"  - Traces: 4개 (trace_recording, decision_explainability, hallucination_detection + more)")
    print(f"  - Annotations: {len(annotated_execution['reasoning_steps'])}개")
    print(f"  - Audit Logs: {audit_count}개 (errors + recovery events)")
    print(f"  - 투명성 리포트: 1개 (종합 분석)")
    print(f"  - 위치: {transparency.output_dir}/")
    print(f"    └─ traces/trace_*.json")
    print(f"    └─ annotations/annotation_*.json")
    print(f"    └─ audit_logs/audit_*.json")
    print(f"    └─ transparent_reports/report_*.json  ⭐ NEW!")

    print("\n" + "=" * 80)
    print("🎉 투명성 관리 평가 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ Trace Recording (실행 추적)
2. ✅ Annotation & Metadata (설명 추가)
3. ✅ Error Tracking & Debugging (오류 추적)
4. ✅ Decision Explainability (의사결정 설명)
5. ✅ Hallucination Detection (환각 탐지)

🔍 투명성의 중요성:
- Debugging: 문제 진단 및 수정 용이
- Trust: 사용자 신뢰 확보
- Compliance: 규제 준수 (AI Act, GDPR)
- Improvement: 시스템 개선 근거

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py

  1. Performance 탭: {filename} 선택
     → Hallucination Detection, Error Rate 확인

  2. 🔍 Test 투명성 탭:
     → 메트릭 계산 과정 (4개 Traces)
     → 주석 관리 (3개 Annotations)
     → Audit Log ({audit_count}개 events)
     → 📋 상세 리포트 (종합 투명성 분석) ⭐
        • Phase 1: 평가 메타데이터
        • Phase 2: 메트릭 계산 추적
        • Phase 3: 신뢰성 분석
        • Phase 4: 주석 및 Audit Log 타임라인
        • Phase 5: 이전 평가와 비교
        • Actionable Insights (실행 가능한 개선 제안)
        • Excel/Markdown 내보내기 가능

🎓 Level 3 (Production) 완료:
  ✅ 01_framework_crewai.py: CrewAI 프레임워크
  ✅ 02_cost_optimization.py: 비용 최적화
  ✅ 03_framework_langchain.py: LangChain 통합
  ✅ 04_framework_langgraph.py: LangGraph 통합
  ✅ 05_transparency.py: 투명성 관리
    """)

if __name__ == "__main__":
    main()
