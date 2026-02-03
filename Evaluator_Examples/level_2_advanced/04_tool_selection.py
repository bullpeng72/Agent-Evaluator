#!/usr/bin/env python3
"""
Level 2 Advanced - Example 04: Tool Selection 심화
===================================================

FILE_PREFIX: [L2-04]_

🎯 주제: Tool Selection 패턴 및 정확도 분석

📚 학습 내용:
1. ToolSelectionTracker 심화 활용
2. Tool 선택 패턴 분석 (Precision, Recall, F1)
3. Tool 선택 효율성 분석
4. 잘못된 선택 패턴 탐지

🔍 핵심 개념:
- Tool Selection vs Tool Execution (Layer 1 ToolCallAnalyzer와 차이)
- Expected Tools (Golden Dataset)
- Precision: 선택한 도구 중 정확한 비율
- Recall: 필요한 도구 중 선택한 비율
- F1 Score: Precision과 Recall의 조화 평균

실행 방법:
    python level_2_advanced/04_tool_selection.py
"""

FILE_PREFIX = "[L2-04]_"

from agent_evaluator import PerformanceMonitor, create_taskresult

def main():
    print("=" * 80)
    print("🎯 Level 2 Advanced - Tool Selection 심화")
    print("=" * 80)

    monitor = PerformanceMonitor()

    print("""
📊 Tool Selection Metrics:
- Precision: 선택한 도구가 얼마나 정확한가? (False Positive 최소화)
- Recall: 필요한 도구를 얼마나 선택했는가? (False Negative 최소화)
- F1 Score: Precision과 Recall의 균형
- True Positives: 올바르게 선택한 도구
- False Positives: 불필요하게 선택한 도구
- False Negatives: 필요하지만 선택하지 않은 도구

🔑 Layer 1 ToolCallAnalyzer와의 차이:
- ToolCallAnalyzer (Layer 1): 도구 실행 효율성 (중복, 실패율)
- ToolSelectionTracker (Layer 2): 도구 선택 정확도 (올바른 선택)
    """)

    # ========================================================================
    # Part 1: Perfect Selection (이상적인 케이스)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 1: Perfect Selection - 완벽한 도구 선택")
    print("=" * 80)

    perfect_case = {
        "task_id": "perfect_001",
        "question": "서울 날씨를 조회하고 섭씨를 화씨로 변환하세요",
        "response": "서울은 현재 15°C이며, 화씨로는 59°F입니다.",
        "expected_tools": ["weather_api", "unit_converter"],
        "actual_tools": ["weather_api", "unit_converter"],
        "tool_calls": [
            {"tool": "weather_api", "success": True, "duration": 0.5},
            {"tool": "unit_converter", "success": True, "duration": 0.1}
        ]
    }

    task = create_taskresult(
        task_id=perfect_case["task_id"],
        task_type="tool_selection",
        question=perfect_case["question"],
        response=perfect_case["response"],
        ground_truth="",
        execution_time=sum(call["duration"] for call in perfect_case["tool_calls"])
    )
    # Add tool_calls and expected_tools manually
    task.tool_calls = perfect_case["tool_calls"]
    task.expected_tools = perfect_case["expected_tools"]
    monitor.record_task(task)

    # Tool Selection 평가
    result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=perfect_case["task_id"],
        expected_tools=perfect_case["expected_tools"],
        actual_tools=perfect_case["actual_tools"]
    )

    print(f"\n✅ {perfect_case['task_id']}: Perfect Selection")
    print(f"  Expected: {perfect_case['expected_tools']}")
    print(f"  Actual:   {perfect_case['actual_tools']}")
    print(f"  📊 Metrics:")
    print(f"    - True Positives:  {result['true_positives']} (정확히 선택)")
    print(f"    - False Positives: {result['false_positives']} (불필요하게 선택)")
    print(f"    - False Negatives: {result['false_negatives']} (누락)")
    print(f"    - Precision: {result['precision']:.1f}% (선택 정확도)")
    print(f"    - Recall:    {result['recall']:.1f}% (필요한 도구 커버)")
    print(f"    - F1 Score:  {result['f1_score']:.1f}% (종합 점수)")
    print(f"  ✓ 분석: 필요한 도구를 정확히 선택 (이상적)")

    # ========================================================================
    # Part 2: Over-Selection (과다 선택)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 2: Over-Selection - 불필요한 도구까지 선택")
    print("=" * 80)

    over_selection_case = {
        "task_id": "over_001",
        "question": "2 + 2를 계산하세요",
        "response": "4입니다.",
        "expected_tools": ["calculator"],
        "actual_tools": ["calculator", "search", "web_browser", "database"],  # 너무 많음!
        "tool_calls": [
            {"tool": "calculator", "success": True, "duration": 0.1},
            {"tool": "search", "success": True, "duration": 0.5},
            {"tool": "web_browser", "success": False, "duration": 0.8},
            {"tool": "database", "success": True, "duration": 0.3}
        ]
    }

    task = create_taskresult(
        task_id=over_selection_case["task_id"],
        task_type="tool_selection",
        question=over_selection_case["question"],
        response=over_selection_case["response"],
        ground_truth="4",
        execution_time=sum(call["duration"] for call in over_selection_case["tool_calls"])
    )
    task.tool_calls = over_selection_case["tool_calls"]
    task.expected_tools = over_selection_case["expected_tools"]
    monitor.record_task(task)

    result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=over_selection_case["task_id"],
        expected_tools=over_selection_case["expected_tools"],
        actual_tools=over_selection_case["actual_tools"]
    )

    print(f"\n⚠️ {over_selection_case['task_id']}: Over-Selection")
    print(f"  Expected: {over_selection_case['expected_tools']}")
    print(f"  Actual:   {over_selection_case['actual_tools']}")
    print(f"  📊 Metrics:")
    print(f"    - True Positives:  {result['true_positives']} (calculator만 필요)")
    print(f"    - False Positives: {result['false_positives']} ⚠️ (3개 불필요)")
    print(f"    - False Negatives: {result['false_negatives']}")
    print(f"    - Precision: {result['precision']:.1f}% ⚠️ (낮음 - 불필요 선택 多)")
    print(f"    - Recall:    {result['recall']:.1f}% ✓ (필요한 건 다 선택)")
    print(f"    - F1 Score:  {result['f1_score']:.1f}%")
    print(f"  ⚠️ 문제: 불필요한 도구 선택으로 비효율 발생")
    print(f"      - 실행 시간 낭비: {sum(call['duration'] for call in over_selection_case['tool_calls']):.1f}초")
    print(f"      - API 비용 증가")
    print(f"      - 복잡도 증가")

    # ========================================================================
    # Part 3: Under-Selection (누락)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 3: Under-Selection - 필요한 도구 누락")
    print("=" * 80)

    under_selection_case = {
        "task_id": "under_001",
        "question": "파리 날씨를 조회하고 한국어로 번역하여 요약하세요",
        "response": "Paris weather is sunny.",  # 번역과 요약 누락
        "expected_tools": ["weather_api", "translator", "summarizer"],
        "actual_tools": ["weather_api"],  # 2개 누락!
        "tool_calls": [
            {"tool": "weather_api", "success": True, "duration": 0.5}
        ]
    }

    task = create_taskresult(
        task_id=under_selection_case["task_id"],
        task_type="tool_selection",
        question=under_selection_case["question"],
        response=under_selection_case["response"],
        ground_truth="",
        execution_time=sum(call["duration"] for call in under_selection_case["tool_calls"])
    )
    task.tool_calls = under_selection_case["tool_calls"]
    task.expected_tools = under_selection_case["expected_tools"]
    monitor.record_task(task)

    result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=under_selection_case["task_id"],
        expected_tools=under_selection_case["expected_tools"],
        actual_tools=under_selection_case["actual_tools"]
    )

    print(f"\n❌ {under_selection_case['task_id']}: Under-Selection")
    print(f"  Expected: {under_selection_case['expected_tools']}")
    print(f"  Actual:   {under_selection_case['actual_tools']}")
    print(f"  📊 Metrics:")
    print(f"    - True Positives:  {result['true_positives']}")
    print(f"    - False Positives: {result['false_positives']}")
    print(f"    - False Negatives: {result['false_negatives']} ❌ (2개 누락)")
    print(f"    - Precision: {result['precision']:.1f}% ✓ (선택한 건 정확)")
    print(f"    - Recall:    {result['recall']:.1f}% ❌ (필요한 도구 놓침)")
    print(f"    - F1 Score:  {result['f1_score']:.1f}%")
    print(f"  ❌ 문제: 필수 도구 누락으로 작업 미완성")
    print(f"      - translator 누락 → 영어 그대로 출력")
    print(f"      - summarizer 누락 → 요약 없음")

    # ========================================================================
    # Part 4: Wrong Selection (잘못된 선택)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 4: Wrong Selection - 완전히 잘못된 선택")
    print("=" * 80)

    wrong_selection_case = {
        "task_id": "wrong_001",
        "question": "데이터베이스에서 사용자 정보를 조회하세요",
        "response": "Error: Could not find user",
        "expected_tools": ["database", "query_builder"],
        "actual_tools": ["web_scraper", "image_processor"],  # 완전 엉뚱함!
        "tool_calls": [
            {"tool": "web_scraper", "success": False, "duration": 1.0},
            {"tool": "image_processor", "success": False, "duration": 0.8}
        ]
    }

    task = create_taskresult(
        task_id=wrong_selection_case["task_id"],
        task_type="tool_selection",
        question=wrong_selection_case["question"],
        response=wrong_selection_case["response"],
        ground_truth="",
        execution_time=sum(call["duration"] for call in wrong_selection_case["tool_calls"])
    )
    task.tool_calls = wrong_selection_case["tool_calls"]
    task.expected_tools = wrong_selection_case["expected_tools"]
    monitor.record_task(task)

    result = monitor.tool_selection_tracker.evaluate_selection(
        task_id=wrong_selection_case["task_id"],
        expected_tools=wrong_selection_case["expected_tools"],
        actual_tools=wrong_selection_case["actual_tools"]
    )

    print(f"\n🚫 {wrong_selection_case['task_id']}: Wrong Selection")
    print(f"  Expected: {wrong_selection_case['expected_tools']}")
    print(f"  Actual:   {wrong_selection_case['actual_tools']}")
    print(f"  📊 Metrics:")
    print(f"    - True Positives:  {result['true_positives']} 🚫 (하나도 맞지 않음)")
    print(f"    - False Positives: {result['false_positives']} 🚫 (2개 모두 틀림)")
    print(f"    - False Negatives: {result['false_negatives']} 🚫 (2개 모두 누락)")
    print(f"    - Precision: {result['precision']:.1f}% 🚫")
    print(f"    - Recall:    {result['recall']:.1f}% 🚫")
    print(f"    - F1 Score:  {result['f1_score']:.1f}% 🚫")
    print(f"  🚫 심각: Agent가 Task를 완전히 오해함")

    # ========================================================================
    # Part 5: Partial Overlap (부분 일치)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 5: Partial Overlap - 일부는 맞고 일부는 틀림")
    print("=" * 80)

    partial_cases = [
        {
            "task_id": "partial_001",
            "question": "뉴스 검색 후 요약하고 번역하세요",
            "expected_tools": ["search", "summarizer", "translator"],
            "actual_tools": ["search", "summarizer", "sentiment_analyzer"],  # translator 누락, sentiment 추가
        },
        {
            "task_id": "partial_002",
            "question": "이미지에서 텍스트를 추출하고 저장하세요",
            "expected_tools": ["ocr", "file_writer"],
            "actual_tools": ["ocr", "database", "file_writer", "validator"],  # 2개 추가
        },
        {
            "task_id": "partial_003",
            "question": "API 호출하고 결과를 파싱하세요",
            "expected_tools": ["api_client", "json_parser"],
            "actual_tools": ["api_client"],  # parser 누락
        }
    ]

    print("\n여러 실제 케이스 평가:")
    for case in partial_cases:
        result = monitor.tool_selection_tracker.evaluate_selection(
            task_id=case["task_id"],
            expected_tools=case["expected_tools"],
            actual_tools=case["actual_tools"]
        )

        # Task 기록
        task = create_taskresult(
            task_id=case["task_id"],
            task_type="tool_selection",
            question=case["question"],
            response="Completed",
            ground_truth="",
            execution_time=1.0
        )
        task.expected_tools = case["expected_tools"]
        monitor.record_task(task)

        print(f"\n  📋 {case['task_id']}:")
        print(f"    Expected: {case['expected_tools']}")
        print(f"    Actual:   {case['actual_tools']}")
        print(f"    TP={result['true_positives']}, FP={result['false_positives']}, FN={result['false_negatives']}")
        print(f"    Precision={result['precision']:.1f}%, Recall={result['recall']:.1f}%, F1={result['f1_score']:.1f}%")

    # ========================================================================
    # Part 6: 통계 및 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 Part 6: 전체 통계 및 패턴 분석")
    print("=" * 80)

    stats = monitor.tool_selection_tracker.get_accuracy_stats()

    print(f"\n📊 Tool Selection Accuracy Statistics:")
    print(f"  - Total Evaluations: {stats['total_evaluations']}개")
    print(f"  - Average Accuracy (F1): {stats['avg_accuracy']:.1f}%")
    print(f"  - Average Precision: {stats['avg_precision']:.1f}%")
    print(f"  - Average Recall: {stats['avg_recall']:.1f}%")
    print(f"  - Total True Positives: {stats['total_true_positives']}개")
    print(f"  - Total False Positives: {stats['total_false_positives']}개 (불필요 선택)")
    print(f"  - Total False Negatives: {stats['total_false_negatives']}개 (누락)")

    print(f"\n🔍 패턴 분석:")

    # Precision vs Recall 분석
    if stats['avg_precision'] < 50:
        print(f"  ⚠️ Low Precision ({stats['avg_precision']:.1f}%): Agent가 너무 많은 도구를 선택")
        print(f"     → 해결: Tool 선택 기준 강화, 불필요한 선택 페널티")

    if stats['avg_recall'] < 50:
        print(f"  ⚠️ Low Recall ({stats['avg_recall']:.1f}%): Agent가 필요한 도구를 놓침")
        print(f"     → 해결: Task 분석 개선, 필수 도구 체크리스트")

    if stats['avg_precision'] > 80 and stats['avg_recall'] > 80:
        print(f"  ✓ 우수: Precision과 Recall 모두 높음 (균형잡힌 선택)")

    # False Positive vs False Negative 비교
    fp_rate = stats['total_false_positives'] / max(stats['total_evaluations'], 1)
    fn_rate = stats['total_false_negatives'] / max(stats['total_evaluations'], 1)

    print(f"\n📈 선택 경향:")
    print(f"  - FP Rate: {fp_rate:.2f} (평균 {fp_rate:.1f}개 불필요 선택)")
    print(f"  - FN Rate: {fn_rate:.2f} (평균 {fn_rate:.1f}개 누락)")

    if fp_rate > fn_rate * 1.5:
        print(f"  → 경향: Over-Selection (너무 많이 선택)")
    elif fn_rate > fp_rate * 1.5:
        print(f"  → 경향: Under-Selection (너무 적게 선택)")
    else:
        print(f"  → 경향: Balanced (균형)")

    # ========================================================================
    # Part 7: Layer 1 ToolCallAnalyzer와 비교
    # ========================================================================
    print("\n" + "=" * 80)
    print("🔄 Part 7: Layer 1 ToolCallAnalyzer와의 비교")
    print("=" * 80)

    tool_efficiency = monitor.tool_analyzer.get_efficiency_stats()

    print(f"\n🔧 Layer 1: ToolCallAnalyzer (Execution Efficiency)")
    print(f"  - Total Calls: {tool_efficiency.get('total_calls', 0)}개")
    print(f"  - Redundancy Rate: {tool_efficiency.get('redundancy_rate', 0):.1f}% (중복 호출)")
    print(f"  - Failure Rate: {tool_efficiency.get('failure_rate', 0):.1f}% (실패율)")
    print(f"  - Avg Calls per Task: {tool_efficiency.get('avg_calls_per_task', 0):.1f}개")
    print(f"  ➜ 측정: HOW WELL executed? (얼마나 효율적으로 실행했는가?)")

    print(f"\n🎯 Layer 2: ToolSelectionTracker (Selection Accuracy)")
    print(f"  - Average F1 Score: {stats['avg_accuracy']:.1f}%")
    print(f"  - Average Precision: {stats['avg_precision']:.1f}%")
    print(f"  - Average Recall: {stats['avg_recall']:.1f}%")
    print(f"  ➜ 측정: DID IT CHOOSE RIGHT? (올바른 도구를 선택했는가?)")

    print(f"\n💡 핵심 차이:")
    print(f"  Layer 1 (Execution):  실행 효율성 (redundancy, failures, duration)")
    print(f"  Layer 2 (Selection):  선택 정확도 (precision, recall, F1)")
    print(f"  \n  예시:")
    print(f"    - High Efficiency + Low Accuracy: 틀린 도구를 효율적으로 실행")
    print(f"    - Low Efficiency + High Accuracy: 맞는 도구를 비효율적으로 실행")
    print(f"    - 둘 다 필요!")

    # ========================================================================
    # 최종 리포트 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("📄 Final Report Generation")
    print("=" * 80)

    report = monitor.generate_report()

    print(f"\n✅ Tool Selection Report:")
    print(f"  - Selection Accuracy: {stats['avg_accuracy']:.1f}%")
    print(f"  - Precision: {stats['avg_precision']:.1f}%")
    print(f"  - Recall: {stats['avg_recall']:.1f}%")

    # 결과 저장
    filename = f"{FILE_PREFIX}tool_selection_result.json"
    monitor.save_to_file(filename)
    print(f"\n💾 결과 저장: {filename}")
    print(f"  위치: {monitor.output_dir / filename}")

    print("\n" + "=" * 80)
    print("🎉 Tool Selection 심화 학습 완료!")
    print("=" * 80)

    print(f"""
📚 학습한 내용:
1. ✅ Tool Selection Metrics (Precision, Recall, F1)
2. ✅ 선택 패턴 분석 (Perfect, Over, Under, Wrong)
3. ✅ False Positive vs False Negative
4. ✅ Layer 1 (Execution) vs Layer 2 (Selection) 차이

🔍 다음 단계:
- level_2_advanced/05_multi_agent.py: Multi-Agent 협업 패턴
- level_2_advanced/06_workflow.py: Workflow 실행 패턴

📊 Dashboard에서 확인:
  cd Dashboard
  streamlit run streamlit_dashboard.py
  → {filename} 선택
  → Layer 2 Metrics 탭에서 Tool Selection 상세 확인
    """)

if __name__ == "__main__":
    main()
