#!/usr/bin/env python3
"""
Merge Evaluation Results Utility

여러 평가 결과 JSON 파일을 하나의 통합 파일로 병합합니다.
주로 월간/주간 리포트 생성 시 사용됩니다.

Usage:
    # Dashboard 디렉토리에서 실행 (독립적으로 사용 가능)
    cd Dashboard
    python utils/merge_evaluation_results.py --month 2024-12
    python utils/merge_evaluation_results.py --week 2024-W48
    python utils/merge_evaluation_results.py --files file1.json file2.json
    python utils/merge_evaluation_results.py --all
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import sys

# Import zero configuration helpers
from agent_evaluator.utils.path_helpers import (
    find_project_root,
    get_evaluation_results_dir,
    get_dashboard_dir
)

# Import HybridPerformanceMonitor for complete merge
from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor


def find_evaluation_files(results_dir: Path, month: str = None, week: str = None) -> List[Path]:
    """
    평가 결과 파일 찾기

    Args:
        results_dir: evaluation_results 디렉토리 경로
        month: 'YYYY-MM' 형식의 월 (예: '2024-12')
        week: 'YYYY-WNN' 형식의 주 (예: '2024-W48')

    Returns:
        JSON 파일 경로 리스트
    """
    if not results_dir.exists():
        print(f"❌ Error: Directory not found: {results_dir}")
        return []

    # 모든 JSON 파일 찾기
    all_files = list(results_dir.glob("*.json"))

    if not month and not week:
        return all_files

    # 월별 필터링
    if month:
        filtered_files = []
        for file in all_files:
            try:
                # 파일의 메타데이터에서 월 확인
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'metadata' in data and 'created_at' in data['metadata']:
                        created_at = data['metadata']['created_at']
                        # ISO 8601 형식에서 월 추출 (YYYY-MM)
                        file_month = created_at[:7]  # '2024-12-08T...' -> '2024-12'
                        if file_month == month:
                            filtered_files.append(file)
                    elif 'timestamp' in data:
                        # 'timestamp' 필드도 확인
                        timestamp = data['timestamp']
                        file_month = timestamp[:7]
                        if file_month == month:
                            filtered_files.append(file)
            except Exception as e:
                print(f"⚠️  Warning: Could not read {file.name}: {e}")

        return filtered_files

    # 주별 필터링
    if week:
        # TODO: ISO week 기반 필터링 구현
        print(f"⚠️  Warning: Week filtering not yet implemented. Using all files.")
        return all_files

    return all_files


def merge_monitors_complete(monitor_list: List[HybridPerformanceMonitor]) -> HybridPerformanceMonitor:
    """
    여러 HybridPerformanceMonitor 인스턴스를 하나로 완전히 병합
    (Dashboard UI의 merge_monitors()와 동일한 방식)

    Args:
        monitor_list: 병합할 Monitor 객체 리스트

    Returns:
        병합된 HybridPerformanceMonitor 객체
    """
    if not monitor_list:
        return None

    if len(monitor_list) == 1:
        return monitor_list[0]

    # Use the first monitor as base
    merged_monitor = monitor_list[0]

    # Merge tasks from other monitors
    for monitor in monitor_list[1:]:
        # Merge TCR tracker tasks
        merged_monitor.tcr_tracker.tasks.extend(monitor.tcr_tracker.tasks)

        # Merge extended tasks
        if hasattr(merged_monitor, 'extended_tasks') and hasattr(monitor, 'extended_tasks'):
            merged_monitor.extended_tasks.extend(monitor.extended_tasks)

        # Merge latency data
        merged_monitor.latency_tracker.latencies.extend(monitor.latency_tracker.latencies)

        # Merge token usage data
        merged_monitor.token_tracker.usage_log.extend(monitor.token_tracker.usage_log)

        # Merge tool analyzer calls
        if hasattr(merged_monitor, 'tool_analyzer') and hasattr(monitor, 'tool_analyzer'):
            merged_monitor.tool_analyzer.executions.extend(monitor.tool_analyzer.executions)

        # Merge retry tracker data
        if hasattr(merged_monitor, 'retry_tracker') and hasattr(monitor, 'retry_tracker'):
            merged_monitor.retry_tracker.attempts.extend(monitor.retry_tracker.attempts)

        # Merge tool selection data
        if hasattr(merged_monitor, 'tool_selection_tracker') and hasattr(monitor, 'tool_selection_tracker'):
            merged_monitor.tool_selection_tracker.selections.extend(monitor.tool_selection_tracker.selections)

        # Merge agent coordination data
        if hasattr(merged_monitor, 'agent_coordination_tracker') and hasattr(monitor, 'agent_coordination_tracker'):
            merged_monitor.agent_coordination_tracker.interactions.extend(monitor.agent_coordination_tracker.interactions)

        # Merge workflow execution data
        if hasattr(merged_monitor, 'workflow_tracker') and hasattr(monitor, 'workflow_tracker'):
            merged_monitor.workflow_tracker.executions.extend(monitor.workflow_tracker.executions)

    return merged_monitor


def merge_evaluation_data_complete(files: List[Path]) -> HybridPerformanceMonitor:
    """
    여러 평가 결과 파일을 하나로 완전히 병합 (모든 Tracker 데이터 포함)

    ⭐ NEW: 이전에는 tasks만 병합했지만, 이제 모든 Tracker 데이터를 병합합니다.
    - TCR Tracker: tasks
    - Latency Tracker: latencies
    - Token Tracker: usage_log
    - Tool Selection: selections
    - Agent Coordination: interactions
    - Workflow Execution: executions
    - Retry Tracker: attempts
    - Tool Analyzer: executions

    Args:
        files: 병합할 JSON 파일 경로 리스트

    Returns:
        병합된 HybridPerformanceMonitor 객체
    """
    if not files:
        return None

    print(f"\n🔄 Loading monitors from {len(files)} files...")
    monitors = []
    merge_metadata = {
        'created_at': datetime.now().isoformat(),
        'merged_from': [],
        'total_files': len(files),
        'merge_type': 'complete'
    }

    for file_path in files:
        try:
            # Load as HybridPerformanceMonitor object
            monitor = HybridPerformanceMonitor.load_from_file(str(file_path))
            monitors.append(monitor)

            # Collect metadata
            task_count = len(monitor.tcr_tracker.tasks)
            merge_metadata['merged_from'].append({
                'filename': file_path.name,
                'task_count': task_count,
                'created_at': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            })

            print(f"✅ Loaded: {file_path.name} ({task_count} tasks)")

        except Exception as e:
            print(f"❌ Error loading {file_path.name}: {e}")

    if not monitors:
        print("❌ No monitors loaded successfully")
        return None

    print(f"\n🔧 Merging {len(monitors)} monitors...")

    # Merge all monitors
    merged_monitor = merge_monitors_complete(monitors)

    # Update merge metadata
    merge_metadata['total_tasks'] = len(merged_monitor.tcr_tracker.tasks)
    merge_metadata['total_latencies'] = len(merged_monitor.latency_tracker.latencies)
    merge_metadata['total_tokens'] = len(merged_monitor.token_tracker.usage_log)

    # Store merge metadata in the monitor (for reference)
    if not hasattr(merged_monitor, 'merge_info'):
        merged_monitor.merge_info = merge_metadata

    print(f"✅ Merge complete!")
    print(f"   📊 Total tasks: {merge_metadata['total_tasks']}")
    print(f"   ⏱️  Total latencies: {merge_metadata['total_latencies']}")
    print(f"   🪙 Total token logs: {merge_metadata['total_tokens']}")

    return merged_monitor


def merge_evaluation_data(files: List[Path]) -> Dict[str, Any]:
    """
    [LEGACY] 여러 평가 결과 파일을 하나로 병합 (tasks만)

    ⚠️ WARNING: 이 함수는 tasks만 병합합니다.
    완전한 병합을 위해서는 merge_evaluation_data_complete()를 사용하세요.

    Args:
        files: 병합할 JSON 파일 경로 리스트

    Returns:
        병합된 데이터 딕셔너리
    """
    if not files:
        return {}

    merged_data = {
        'metadata': {
            'created_at': datetime.now().isoformat(),
            'merged_from': [],
            'total_tasks': 0,
            'total_files': len(files),
            'providers_used': [],
            'merge_type': 'legacy_tasks_only'
        },
        'tasks': [],
        'providers_used': []
    }

    all_providers = set()

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 파일 정보 기록
            file_metadata = data.get('metadata', {})
            merged_data['metadata']['merged_from'].append({
                'filename': file_path.name,
                'created_at': file_metadata.get('created_at') or data.get('timestamp', 'unknown'),
                'task_count': len(data.get('tasks', []))
            })

            # Tasks 병합
            if 'tasks' in data:
                merged_data['tasks'].extend(data['tasks'])

            # Providers 수집
            if 'metadata' in data and 'providers_used' in data['metadata']:
                all_providers.update(data['metadata']['providers_used'])
            elif 'providers_used' in data:
                all_providers.update(data['providers_used'])

            print(f"✅ Merged: {file_path.name} ({len(data.get('tasks', []))} tasks)")

        except Exception as e:
            print(f"❌ Error merging {file_path.name}: {e}")

    # 메타데이터 업데이트
    merged_data['metadata']['total_tasks'] = len(merged_data['tasks'])
    merged_data['metadata']['providers_used'] = sorted(list(all_providers))
    merged_data['providers_used'] = sorted(list(all_providers))

    return merged_data


def save_merged_monitor(monitor: HybridPerformanceMonitor, output_path: Path):
    """
    병합된 Monitor를 파일로 저장

    Args:
        monitor: 병합된 HybridPerformanceMonitor 객체
        output_path: 출력 파일 경로
    """
    try:
        # 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Monitor를 JSON 파일로 저장
        monitor.save_to_file(str(output_path))

        print(f"\n✅ Successfully saved merged monitor to: {output_path}")

        # 저장된 데이터 요약
        print(f"📊 Total tasks: {len(monitor.tcr_tracker.tasks)}")
        print(f"⏱️  Total latencies: {len(monitor.latency_tracker.latencies)}")
        print(f"🪙 Total token logs: {len(monitor.token_tracker.usage_log)}")

        if hasattr(monitor, 'merge_info'):
            print(f"📁 Merged from {monitor.merge_info['total_files']} files")

    except Exception as e:
        print(f"❌ Error saving merged monitor: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def save_merged_data(data: Dict[str, Any], output_path: Path):
    """
    [LEGACY] 병합된 데이터를 파일로 저장 (tasks만)

    ⚠️ WARNING: 이 함수는 tasks만 저장합니다.
    완전한 저장을 위해서는 save_merged_monitor()를 사용하세요.

    Args:
        data: 병합된 데이터
        output_path: 출력 파일 경로
    """
    try:
        # 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # JSON 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Successfully saved merged data to: {output_path}")
        print(f"📊 Total tasks: {data['metadata']['total_tasks']}")
        print(f"📁 Merged from {data['metadata']['total_files']} files")

    except Exception as e:
        print(f"❌ Error saving merged data: {e}")
        sys.exit(1)


def print_merge_summary_complete(monitor: HybridPerformanceMonitor):
    """병합 결과 요약 출력 (완전 병합)"""
    print("\n" + "=" * 70)
    print("📊 COMPLETE MERGE SUMMARY")
    print("=" * 70)

    if hasattr(monitor, 'merge_info'):
        metadata = monitor.merge_info

        print(f"\n📅 Created: {metadata.get('created_at', 'N/A')}")
        print(f"📁 Files merged: {metadata.get('total_files', 0)}")
        print(f"🔧 Merge type: {metadata.get('merge_type', 'N/A')}")

        print(f"\n📊 Merged Data Summary:")
        print(f"   ✅ Tasks: {metadata.get('total_tasks', 0)}")
        print(f"   ⏱️  Latencies: {metadata.get('total_latencies', 0)}")
        print(f"   🪙 Token logs: {metadata.get('total_tokens', 0)}")

        # Calculate additional stats
        report = monitor.generate_hybrid_report()
        tcr_data = report.accuracy_metrics.get('tcr', {})
        tcr = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0

        print(f"\n📈 Quick Stats:")
        print(f"   TCR: {tcr:.1f}%")

        latency_stats = monitor.latency_tracker.get_latency_stats()
        if latency_stats:
            print(f"   Avg Latency: {latency_stats.get('mean', 0):.2f}s")

        token_stats = monitor.token_tracker.get_usage_stats()
        if token_stats:
            print(f"   Total Cost: ${token_stats.get('total_cost', 0):.4f}")

        print(f"\n📋 Source files:")
        for i, file_info in enumerate(metadata.get('merged_from', []), 1):
            print(f"   {i}. {file_info['filename']} - {file_info['task_count']} tasks - {file_info['created_at']}")
    else:
        print("\n⚠️  No merge metadata available")
        print(f"📊 Total tasks: {len(monitor.tcr_tracker.tasks)}")

    print("\n" + "=" * 70)


def print_merge_summary(data: Dict[str, Any]):
    """[LEGACY] 병합 결과 요약 출력 (tasks만)"""
    print("\n" + "=" * 70)
    print("📊 MERGE SUMMARY (LEGACY - Tasks Only)")
    print("=" * 70)

    metadata = data.get('metadata', {})

    print(f"\n📅 Created: {metadata.get('created_at', 'N/A')}")
    print(f"📁 Files merged: {metadata.get('total_files', 0)}")
    print(f"📊 Total tasks: {metadata.get('total_tasks', 0)}")

    print(f"\n⚠️  WARNING: This is a legacy merge (tasks only)")
    print(f"   Missing: latencies, tokens, tool selection, agent coordination, workflows")
    print(f"   Use complete merge for full analysis in Dashboard")

    providers = metadata.get('providers_used', [])
    if providers:
        print(f"\n🔧 Providers: {', '.join(providers)}")

    print(f"\n📋 Source files:")
    for i, file_info in enumerate(metadata.get('merged_from', []), 1):
        print(f"   {i}. {file_info['filename']} - {file_info['task_count']} tasks - {file_info['created_at']}")

    print("\n" + "=" * 70)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='Merge multiple evaluation result JSON files into one',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Dashboard 디렉토리에서 실행 (독립적으로 사용 가능)
  cd Dashboard

  # 2024년 12월의 모든 결과 병합
  python utils/merge_evaluation_results.py --month 2024-12

  # 2024년 48주차의 모든 결과 병합
  python utils/merge_evaluation_results.py --week 2024-W48

  # 특정 파일들만 병합
  python utils/merge_evaluation_results.py --files example1.json example2.json

  # 디렉토리의 모든 파일 병합
  python utils/merge_evaluation_results.py --all

  # 커스텀 출력 파일명 지정
  python utils/merge_evaluation_results.py --month 2024-12 --output monthly_report_dec.json
        '''
    )

    parser.add_argument('--month', type=str, help='Month to merge (YYYY-MM format, e.g., 2024-12)')
    parser.add_argument('--week', type=str, help='Week to merge (YYYY-WNN format, e.g., 2024-W48)')
    parser.add_argument('--files', nargs='+', help='Specific files to merge')
    parser.add_argument('--all', action='store_true', help='Merge all files in the directory')
    parser.add_argument('--output', type=str, help='Output filename (default: auto-generated based on filter)')
    parser.add_argument('--legacy', action='store_true', help='Use legacy merge (tasks only). Default is complete merge.')

    args = parser.parse_args()

    # Use zero configuration to find evaluation_results directory
    results_dir = get_evaluation_results_dir()

    print("=" * 70)
    print("🔧 EVALUATION RESULTS MERGER")
    print("=" * 70)
    print(f"\n📂 Results directory: {results_dir}")

    # 병합할 파일 결정
    files_to_merge = []
    output_filename = None

    if args.files:
        # 특정 파일들 병합
        files_to_merge = [results_dir / filename for filename in args.files]
        output_filename = args.output or 'merged_custom.json'
        print(f"📋 Mode: Merge specific files ({len(args.files)} files)")

    elif args.month:
        # 월별 병합
        files_to_merge = find_evaluation_files(results_dir, month=args.month)
        output_filename = args.output or f"monthly_{args.month.replace('-', '_')}.json"
        print(f"📅 Mode: Merge by month ({args.month})")

    elif args.week:
        # 주별 병합
        files_to_merge = find_evaluation_files(results_dir, week=args.week)
        output_filename = args.output or f"weekly_{args.week.replace('-', '_')}.json"
        print(f"📅 Mode: Merge by week ({args.week})")

    elif args.all:
        # 전체 병합
        files_to_merge = find_evaluation_files(results_dir)
        output_filename = args.output or f"merged_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        print(f"📋 Mode: Merge all files")

    else:
        print("❌ Error: Please specify --month, --week, --files, or --all")
        parser.print_help()
        sys.exit(1)

    # 파일 존재 확인
    if not files_to_merge:
        print(f"\n❌ Error: No files found to merge")
        sys.exit(1)

    print(f"📁 Found {len(files_to_merge)} file(s) to merge\n")

    # 출력 경로
    output_path = results_dir / output_filename

    # 파일 병합 (기본: 완전 병합, --legacy 플래그 시 tasks만)
    if args.legacy:
        print("⚠️  Using LEGACY merge mode (tasks only)\n")
        print("🔄 Merging files...")
        merged_data = merge_evaluation_data(files_to_merge)

        if not merged_data or not merged_data.get('tasks'):
            print("❌ Error: No data to merge")
            sys.exit(1)

        # 저장
        save_merged_data(merged_data, output_path)

        # 요약 출력
        print_merge_summary(merged_data)
    else:
        print("✅ Using COMPLETE merge mode (all tracker data)\n")

        # 완전 병합
        merged_monitor = merge_evaluation_data_complete(files_to_merge)

        if not merged_monitor:
            print("❌ Error: No monitor to merge")
            sys.exit(1)

        # 저장
        save_merged_monitor(merged_monitor, output_path)

        # 요약 출력
        print_merge_summary_complete(merged_monitor)

    print(f"\n💡 Next steps:")
    print(f"   1. Open Dashboard:")
    print(f"      streamlit run streamlit_dashboard.py")
    print(f"   2. Select '{output_filename}' from the sidebar dropdown")
    print(f"   3. Analyze the merged data across all tabs")
    if not args.legacy:
        print(f"   ✅ All metrics available: TCR, Latency, Tokens, Tool Selection, Agent Coordination, Workflows")
    else:
        print(f"   ⚠️  Limited metrics: Only TCR and basic task data")
    print()


if __name__ == '__main__':
    main()
