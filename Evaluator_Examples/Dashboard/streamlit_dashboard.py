"""
Streamlit Dashboard for Agent Evaluator Results
==============================================

Main evaluation results dashboard with 12 tabs:
1. 📊 Overview - Summary of all metrics
2. 📈 Layer 1: Basic - TCR, Accuracy, Quality, Hallucination, Performance
3. 🔒 Layer 1: Security - Input Sanitization, Output Leakage, Authorization
4. 🤖 Layer 2: Agentic - Tool Selection, Tool Efficiency, Multi-Agent, Workflow
5. 🛡️ Layer 2: Security - Privilege Escalation, Attack Detection
6. 🔬 Layer 3: Advanced - DeepEval and Ragas metrics
7. 🚨 Integrated Security - Comprehensive security dashboard
8. 💡 Insights - Alerts, Recommendations, Task Explorer
9. 🔍 Test 투명성 - Traces, Annotations, Audit Log
10. 📚 지표 설명 - Detailed explanation of all metrics (Layer 1, 2, 3)
11. 📦 Export - Reports and Evaluation Info

✨ v2.2 Improvements (Security Integration):
- Layer 1 Security metrics: Input Sanitization, Output Leakage, Authorization
- Layer 2 Security metrics: Privilege Escalation, Attack Detection
- Integrated Security Dashboard with risk scoring and alerts
- Security visualization components (gauges, charts, timelines)
- Comprehensive security recommendations

✨ v2.1 Improvements:
- RAG metrics (faithfulness, answer_relevancy, context_recall, context_precision)
  now tracked directly in PerformanceMonitor
- compare_with_thresholds() calculates real values (not 'pending')
- get_rag_metrics_summary() provides detailed RAG statistics
- CSV export includes 13+ metrics (basic + RAG)

Usage:
    streamlit run streamlit_dashboard.py
"""

import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Import evaluator classes from agent_evaluator package
from agent_evaluator import PerformanceMonitor, TaskType, HybridPerformanceMonitor
from agent_evaluator.reporting.comprehensive_report import generate_comprehensive_html_report
from agent_evaluator.utils.path_helpers import (
    find_project_root,
    get_evaluation_results_dir,
    get_dashboard_dir
)

# Import security dashboard utilities
from utils.dashboard_utils import (
    get_layer1_basic_metrics,
    get_layer1_security_metrics,
    get_layer2_agentic_metrics,
    get_layer2_security_metrics,
    get_layer3_advanced_metrics,
    calculate_security_risk_score,
    generate_security_alerts,
    has_security_metrics,
    get_all_layer_metrics
)
from utils.security_tabs import (
    render_layer1_security_tab,
    render_layer2_security_tab,
    render_integrated_security_tab
)

# Helper functions for zero configuration
def get_data_dir():
    """Get the data directory using zero configuration"""
    project_root = find_project_root()
    dashboard_dir = get_dashboard_dir(project_root)
    return dashboard_dir / "data"

def get_dashboard_directory():
    """Get the dashboard directory using zero configuration"""
    project_root = find_project_root()
    return get_dashboard_dir(project_root)

# Page configuration
st.set_page_config(
    page_title="Agent Evaluator Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper function for validation (moved to module level to avoid duplication)
def is_valid_result_file(file_path: Path) -> bool:
    """Check if file is a valid evaluation result (not a config file)"""
    # Skip known config files
    config_files = ['thresholds.json', 'config.json', 'advanced_eval_config.json']
    if file_path.name in config_files:
        return False

    # Try to load and check if it has 'tasks' key
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # Valid result files should have 'tasks' or 'completion_tracker' keys
            return 'tasks' in data or 'completion_tracker' in data
    except:
        return False


# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .status-pass {
        color: #00cc00;
        font-weight: bold;
    }
    .status-fail {
        color: #ff4444;
        font-weight: bold;
    }
    .status-warning {
        color: #ffaa00;
        font-weight: bold;
    }
    .stMetric {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def load_evaluation_results() -> Optional[HybridPerformanceMonitor]:
    """Load the most recent evaluation results (includes registry data)"""
    all_files = get_available_result_files()

    if all_files:
        # Get most recent file
        latest_file = all_files[0]  # Already sorted by modification time
        try:
            monitor = HybridPerformanceMonitor.load_from_file(str(latest_file))
            # Show source in sidebar
            if latest_file.parent.name == "evaluation_results" and latest_file.parent.parent.name == "data":
                st.sidebar.success(f"✅ 로드: {latest_file.name}")
            else:
                st.sidebar.success(f"✅ 로드: {latest_file.name}\n📁 위치: {latest_file.parent.name}")
            return monitor
        except Exception as e:
            st.sidebar.error(f"Error loading {latest_file.name}: {e}")
            # Try next file
            if len(all_files) > 1:
                try:
                    monitor = HybridPerformanceMonitor.load_from_file(str(all_files[1]))
                    st.sidebar.success(f"✅ 로드: {all_files[1].name}")
                    return monitor
                except:
                    pass

    return None


def get_available_result_files() -> List[Path]:
    """Get all available evaluation result files (includes registry)"""
    all_files = []

    # 1. Check evaluation_results directory using zero configuration
    results_dir = get_evaluation_results_dir(create=True)

    if results_dir.exists():
        json_files = [f for f in results_dir.glob("*.json") if is_valid_result_file(f)]
        all_files.extend(json_files)

    # 2. Check evaluation_results directory for example files (no longer checking current directory)
    example_files = [f for f in results_dir.glob("example*.json") if is_valid_result_file(f)]
    all_files.extend(example_files)

    # Remove duplicates and sort by modification time (newest first)
    all_files = list(set(all_files))
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return all_files


def merge_monitors(monitor_list: List[HybridPerformanceMonitor]) -> HybridPerformanceMonitor:
    """Merge multiple HybridPerformanceMonitor instances into one"""
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


def get_status_icon(value: float, threshold: float, reverse: bool = False) -> str:
    """Get status icon based on threshold comparison"""
    if reverse:  # For metrics where lower is better (hallucination, cost, latency)
        if value <= threshold:
            return "✅"
        elif value <= threshold * 1.2:
            return "⚠️"
        else:
            return "❌"
    else:  # For metrics where higher is better
        if value >= threshold:
            return "✅"
        elif value >= threshold * 0.8:
            return "⚠️"
        else:
            return "❌"


def get_efficiency_stats(monitor) -> Dict[str, Any]:
    """Get combined efficiency statistics from latency and token trackers"""
    latency_stats = monitor.latency_tracker.get_latency_stats()
    token_stats = monitor.token_tracker.get_usage_stats()

    return {
        'average_latency': latency_stats.get('average', 0),
        'total_cost': token_stats.get('total_cost', 0),
        'cost_per_task': token_stats.get('avg_cost_per_task', 0),  # Fixed: cost_per_task → avg_cost_per_task
        'total_tokens': token_stats.get('total_tokens', 0),
        'average_tokens_per_task': token_stats.get('avg_tokens_per_task', 0)  # Fixed: average_tokens_per_task → avg_tokens_per_task
    }


def extract_report_value(report, path: str, default=0):
    """Safely extract nested values from report

    Args:
        report: HybridEvaluationReport object
        path: Dot-separated path like 'accuracy_metrics.tcr.tcr' or 'efficiency_metrics.latency.average'
        default: Default value if path not found

    Returns:
        Extracted value or default
    """
    parts = path.split('.')
    current = report

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)

        if current is None:
            return default

    return current if current is not None else default


def render_overview_tab(monitor: HybridPerformanceMonitor):
    """Tab 1: Overview - Summary of all metrics aligned with tab structure"""

    st.header("📊 평가 결과 개요")
    st.caption("모든 평가 지표의 핵심 정보를 한눈에 확인하세요")

    # Generate hybrid report
    report = monitor.generate_hybrid_report()

    # ========================================================================
    # 전체 요약 - Top-level KPIs
    # ========================================================================
    st.markdown("### 📋 전체 요약")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "총 Task 수",
            f"{report.total_tasks}",
            help="평가된 전체 작업 수"
        )

    with col2:
        tcr_data = report.accuracy_metrics.get('tcr', {})
        success_rate = tcr_data.get('success_rate', 0) if isinstance(tcr_data, dict) else 0
        st.metric(
            "성공률",
            f"{success_rate:.1f}%",
            delta=f"{success_rate - 85:.1f}%" if success_rate >= 85 else f"{success_rate - 85:.1f}%",
            delta_color="normal",
            help="전체 작업 중 성공한 비율"
        )

    with col3:
        tcr_value = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
        st.metric(
            "작업 완료율 (TCR)",
            f"{tcr_value:.1f}%",
            delta="목표 90%" if tcr_value >= 90 else f"{tcr_value - 90:.1f}%",
            delta_color="normal" if tcr_value >= 90 else "inverse",
            help="Task Completion Rate - 작업 완료 점수"
        )

    with col4:
        latency_data = report.efficiency_metrics.get('latency', {})
        avg_time = latency_data.get('mean', 0) if isinstance(latency_data, dict) else 0
        st.metric(
            "평균 실행 시간",
            f"{avg_time:.2f}s",
            delta="최적" if avg_time <= 3.0 else "개선 필요",
            delta_color="normal" if avg_time <= 3.0 else "inverse",
            help="작업당 평균 실행 시간"
        )

    st.markdown("---")

    # ========================================================================
    # 🎯 Core Metrics Section
    # ========================================================================
    with st.container():
        st.markdown("### 🎯 Core Metrics")
        st.caption("**작업 완료도 및 정확성 지표** (What was achieved) - 상세 내용은 'Core Metrics' 탭에서 확인")

        accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
        quality_metrics = monitor.quality_evaluator.get_quality_metrics()
        hallucination_data = monitor.hallucination_detector.get_hallucination_rate()

        core_metrics = []

        # TCR
        core_metrics.append({
            'name': 'TCR',
            'value': f"{tcr_value:.1f}%",
            'help': 'Task Completion Rate'
        })

        # Accuracy
        accuracy_value = accuracy_metrics.get('overall_accuracy', 0)
        if accuracy_value > 0:
            core_metrics.append({
                'name': '정확도',
                'value': f"{accuracy_value:.1f}%",
                'help': '전체 정확도 점수'
            })

        # Quality
        total_evaluated = quality_metrics.get('total_evaluated', 0)
        if total_evaluated > 0:
            avg_score = quality_metrics.get('avg_total_score', 0)
            core_metrics.append({
                'name': '응답 품질',
                'value': f"{avg_score:.2f}/10",
                'help': '평균 응답 품질 점수'
            })

        # Hallucination
        hall_rate = hallucination_data.get('hallucination_rate', 0) * 100
        total_checked = hallucination_data.get('total_checked', 0)
        if total_checked > 0:
            core_metrics.append({
                'name': '환각 발생률',
                'value': f"{hall_rate:.2f}%",
                'help': '환각(Hallucination) 탐지율 (낮을수록 좋음)'
            })

        if core_metrics:
            cols = st.columns(len(core_metrics))
            for col, metric in zip(cols, core_metrics):
                with col:
                    st.metric(metric['name'], metric['value'], help=metric['help'])
        else:
            st.info("Core Metrics 데이터가 없습니다.")

    st.markdown("---")

    # ========================================================================
    # ⚡ Performance Section
    # ========================================================================
    with st.container():
        st.markdown("### ⚡ Performance")
        st.caption("**실행 효율성 및 리소스 사용 지표** (How efficiently it was achieved) - 상세 내용은 'Performance' 탭에서 확인")

        token_stats = monitor.token_tracker.get_usage_stats()

        perf_metrics = []

        # Latency
        perf_metrics.append({
            'name': '평균 응답 시간',
            'value': f"{avg_time:.2f}s",
            'help': '작업당 평균 실행 시간'
        })

        # Tokens
        total_tokens = token_stats.get('total_tokens', 0)
        if total_tokens > 0:
            avg_tokens = token_stats.get('avg_tokens_per_task', 0)
            perf_metrics.append({
                'name': '평균 토큰',
                'value': f"{avg_tokens:,.0f}",
                'help': 'Task당 평균 토큰 사용량'
            })

            # Cost
            total_cost = token_stats.get('total_cost', 0)
            perf_metrics.append({
                'name': '총 비용',
                'value': f"${total_cost:.4f}",
                'help': '전체 API 비용'
            })

            cost_per_task = token_stats.get('avg_cost_per_task', 0)
            perf_metrics.append({
                'name': 'Task당 비용',
                'value': f"${cost_per_task:.4f}",
                'help': '작업당 평균 비용'
            })

        # Retry Success Rate (Layer 1 metric)
        retry_metrics = monitor.retry_tracker.get_retry_metrics()
        if retry_metrics:
            # Calculate retry success rate: tasks that eventually succeeded after retry
            eventual_success = retry_metrics.get('eventual_success_rate', 0)
            if eventual_success > 0:
                perf_metrics.append({
                    'name': '재시도 성공률',
                    'value': f"{eventual_success:.1f}%",
                    'help': 'Layer 1: 재시도 후 최종 성공 비율'
                })

        if perf_metrics:
            cols = st.columns(len(perf_metrics))
            for col, metric in zip(cols, perf_metrics):
                with col:
                    st.metric(metric['name'], metric['value'], help=metric['help'])
        else:
            st.info("Performance 데이터가 없습니다.")

    st.markdown("---")

    # ========================================================================
    # 🤖 Agentic AI Section
    # ========================================================================
    with st.container():
        st.markdown("### 🤖 Agentic AI")
        st.caption("에이전트 특화 지표 (도구 사용 포함) - 상세 내용은 'Agentic AI' 탭에서 확인")

        agentic_metrics = []

        # Tool Selection
        tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
        if tool_selection_stats and tool_selection_stats.get('total_selections', 0) > 0:
            tool_accuracy = tool_selection_stats.get('overall_accuracy', 0)
            agentic_metrics.append({
                'name': '도구 선택 정확도',
                'value': f"{tool_accuracy:.1f}%",
                'help': '올바른 도구를 선택한 비율'
            })

        # Tool Efficiency (moved from Performance)
        tool_stats = monitor.tool_analyzer.get_efficiency_stats()
        if tool_stats and tool_stats.get('total_calls', 0) > 0:
            efficiency = tool_stats.get('avg_efficiency_score', 0)
            agentic_metrics.append({
                'name': '도구 효율성',
                'value': f"{efficiency:.1f}%",
                'help': '선택한 도구의 실행 효율성 (성공률, 중복 제거)'
            })

        # Multi-Agent Coordination
        coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
        if coordination_stats.get('total_interactions', 0) > 0:
            coord_score = coordination_stats.get('score', 0)
            agentic_metrics.append({
                'name': '에이전트 협업',
                'value': f"{coord_score:.2f}/10",
                'help': 'Multi-agent coordination quality'
            })

        # Workflow Execution
        workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
        if workflow_stats.get('total_steps', 0) > 0:
            workflow_success = workflow_stats.get('step_success_rate', 0)
            agentic_metrics.append({
                'name': '워크플로우 성공률',
                'value': f"{workflow_success:.1f}%",
                'help': 'Chain/Graph 실행 성공률'
            })

        # Retry & Correction
        retry_metrics = monitor.retry_tracker.get_retry_metrics()
        if retry_metrics.get('total_tasks_with_retries', 0) > 0:
            final_success = retry_metrics.get('final_success_rate', 0)
            agentic_metrics.append({
                'name': '재시도 후 성공률',
                'value': f"{final_success:.1f}%",
                'help': '재시도 후 최종 성공률'
            })

        if agentic_metrics:
            cols = st.columns(len(agentic_metrics))
            for col, metric in zip(cols, agentic_metrics):
                with col:
                    st.metric(metric['name'], metric['value'], help=metric['help'])
        else:
            st.info("Agentic AI 데이터가 없습니다. TaskResult에 framework, expected_tools 등을 설정하세요.")

    st.markdown("---")

    # ========================================================================
    # 🔬 Advanced Metrics Section
    # ========================================================================
    with st.container():
        st.markdown("### 🔬 Advanced Metrics")
        st.caption("고급 평가 지표 - 상세 내용은 'Advanced' 탭에서 확인")

        adv_metrics = report.advanced_metrics_summary if hasattr(report, 'advanced_metrics_summary') else {}

        # Check if external metrics are available
        has_external_metrics = any(
            key in adv_metrics and adv_metrics[key]
            for key in ['g_eval_score', 'hallucination_score', 'answer_relevancy_score',
                        'ragas_faithfulness', 'ragas_context_precision', 'ragas_context_recall',
                        'ragas_answer_relevancy', 'ragas_overall_score']
        )

        if has_external_metrics:
            advanced_display = []

            # DeepEval highlights
            g_eval = adv_metrics.get('g_eval_score', {}).get('mean', 0)
            if g_eval > 0:
                advanced_display.append({
                    'name': 'G-Eval (DeepEval)',
                    'value': f"{g_eval:.2f}",
                    'help': 'LLM 기반 종합 품질 평가'
                })

            hall_score = adv_metrics.get('hallucination_score', {}).get('mean', 0)
            if hall_score > 0:
                advanced_display.append({
                    'name': 'Hallucination (DeepEval)',
                    'value': f"{hall_score:.2f}",
                    'help': 'AI 기반 환각 탐지'
                })

            # Ragas highlights
            faithfulness = adv_metrics.get('ragas_faithfulness', {}).get('mean', 0)
            if faithfulness > 0:
                advanced_display.append({
                    'name': 'Faithfulness (Ragas)',
                    'value': f"{faithfulness:.2f}",
                    'help': '답변이 컨텍스트에 충실한 정도 (환각 방지)'
                })

            overall = adv_metrics.get('ragas_overall_score', {}).get('mean', 0)
            if overall > 0:
                advanced_display.append({
                    'name': 'Ragas Overall',
                    'value': f"{overall:.2f}",
                    'help': 'Ragas 종합 점수'
                })

            if advanced_display:
                cols = st.columns(len(advanced_display))
                for col, metric in zip(cols, advanced_display):
                    with col:
                        st.metric(metric['name'], metric['value'], help=metric['help'])
        else:
            st.info("고급 지표 데이터가 없습니다. HybridPerformanceMonitor에서 DeepEval 또는 Ragas를 활성화하세요.")

    st.markdown("---")

    # ========================================================================
    # 🔒 Security Section
    # ========================================================================
    with st.container():
        st.markdown("### 🔒 Security")
        st.caption("보안 지표 (Layer 1 & Layer 2) - 상세 내용은 'Layer 1: Security' 및 'Layer 2: Security' 탭에서 확인")

        # Get security metrics
        from utils.dashboard_utils import (
            get_layer1_security_metrics,
            get_layer2_security_metrics,
            has_security_metrics
        )

        if has_security_metrics(monitor):
            layer1_sec = get_layer1_security_metrics(monitor)
            layer2_sec = get_layer2_security_metrics(monitor)

            security_display = []

            # Layer 1 metrics
            if layer1_sec:
                input_sec = layer1_sec.get('input_security', {})
                if input_sec.get('total_inputs', 0) > 0:
                    threat_rate = input_sec.get('threat_rate', 0)
                    security_display.append({
                        'name': '입력 위협 탐지율',
                        'value': f"{threat_rate:.1f}%",
                        'help': 'Layer 1: 입력에서 탐지된 보안 위협 비율',
                        'alert': threat_rate > 20
                    })

                output_leak = layer1_sec.get('output_leakage', {})
                if output_leak.get('total_outputs', 0) > 0:
                    leakage_rate = output_leak.get('leakage_rate', 0)
                    security_display.append({
                        'name': '출력 유출 탐지율',
                        'value': f"{leakage_rate:.1f}%",
                        'help': 'Layer 1: 출력에서 탐지된 민감정보 유출 비율',
                        'alert': leakage_rate > 10
                    })

                auth = layer1_sec.get('authorization', {})
                if auth.get('total_calls', 0) > 0:
                    compliance_rate = auth.get('compliance_rate', 100)
                    security_display.append({
                        'name': '권한 준수율',
                        'value': f"{compliance_rate:.1f}%",
                        'help': 'Layer 1: 도구 권한 정책 준수 비율',
                        'alert': compliance_rate < 90
                    })

            # Layer 2 metrics
            if layer2_sec:
                priv_esc = layer2_sec.get('privilege_escalation', {})
                if priv_esc.get('total_evaluations', 0) > 0:
                    esc_rate = priv_esc.get('escalation_rate', 0)
                    security_display.append({
                        'name': '권한 상승 탐지율',
                        'value': f"{esc_rate:.1f}%",
                        'help': 'Layer 2: 권한 상승 시도가 탐지된 비율',
                        'alert': esc_rate > 20
                    })

                attack = layer2_sec.get('attack_detection', {})
                if attack.get('total_chains_analyzed', 0) > 0:
                    attack_rate = attack.get('detection_rate', 0)
                    security_display.append({
                        'name': '공격 패턴 탐지율',
                        'value': f"{attack_rate:.1f}%",
                        'help': 'Layer 2: 의심스러운 공격 패턴 탐지 비율',
                        'alert': attack_rate > 20
                    })

                    # Show data exfiltration if any detected
                    exfil = attack.get('data_exfiltration_detected', 0)
                    if exfil > 0:
                        security_display.append({
                            'name': '데이터 유출 시도',
                            'value': f"{exfil}건",
                            'help': 'Layer 2: 데이터 유출 공격 탐지 횟수',
                            'alert': True
                        })

            if security_display:
                # Display metrics
                cols = st.columns(min(len(security_display), 4))
                for idx, metric in enumerate(security_display[:4]):
                    with cols[idx]:
                        if metric.get('alert', False):
                            st.metric(
                                f"🔴 {metric['name']}",
                                metric['value'],
                                help=metric['help']
                            )
                        else:
                            st.metric(
                                metric['name'],
                                metric['value'],
                                help=metric['help']
                            )

                # Show additional metrics if more than 4
                if len(security_display) > 4:
                    st.caption("추가 보안 지표:")
                    cols2 = st.columns(len(security_display) - 4)
                    for idx, metric in enumerate(security_display[4:]):
                        with cols2[idx]:
                            if metric.get('alert', False):
                                st.metric(
                                    f"🔴 {metric['name']}",
                                    metric['value'],
                                    help=metric['help']
                                )
                            else:
                                st.metric(
                                    metric['name'],
                                    metric['value'],
                                    help=metric['help']
                                )
            else:
                st.info("보안 지표 데이터가 아직 수집되지 않았습니다.")
        else:
            st.info("보안 메트릭이 비활성화되어 있습니다. `enable_security_metrics=True`로 활성화하세요.")

    st.markdown("---")

    # ========================================================================
    # 💡 Insights Section
    # ========================================================================
    with st.container():
        st.markdown("### 💡 Insights")
        st.caption("알림 및 권장사항 - 상세 내용은 'Insights' 탭에서 확인")

        # Get alerts and recommendations
        alerts = report.alerts if hasattr(report, 'alerts') else []
        recommendations = report.recommendations if hasattr(report, 'recommendations') else []

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🚨 주요 알림")
            if alerts:
                # Show top 3 critical/high alerts
                critical_alerts = [a for a in alerts if a.get('severity') in ['critical', 'high']][:3]
                if critical_alerts:
                    for alert in critical_alerts:
                        severity_icon = "🔴" if alert['severity'] == 'critical' else "🟡"
                        st.warning(f"{severity_icon} **{alert.get('metric', 'Unknown')}**: {alert.get('message', '')}")
                else:
                    st.success("✅ 주요 알림 없음")
            else:
                st.info("알림 데이터 없음")

        with col2:
            st.markdown("#### 💡 주요 권장사항")
            if recommendations:
                # Show top 3 recommendations
                for rec in recommendations[:3]:
                    st.info(f"**{rec.get('area', '')}**: {rec.get('suggestion', '')}")
            else:
                st.info("권장사항 데이터 없음")

    st.markdown("---")

    # ========================================================================
    # 🎯 Threshold Comparison (if configured)
    # ========================================================================
    if hasattr(monitor, 'thresholds') and monitor.thresholds:
        with st.container():
            st.markdown("### 🎯 임계값 비교")
            st.caption("설정된 임계값과의 비교")

            threshold_comparison = monitor.compare_with_thresholds()
            basic_metrics = threshold_comparison.get('basic_metrics', {})

            if basic_metrics:
                # Pass/Fail Summary
                pass_count = sum(1 for v in basic_metrics.values() if v.get('status') == 'pass')
                fail_count = sum(1 for v in basic_metrics.values() if v.get('status') == 'fail')
                warn_count = sum(1 for v in basic_metrics.values() if v.get('status') == 'warning')

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("✅ 통과", pass_count)
                with col2:
                    st.metric("⚠️ 경고", warn_count)
                with col3:
                    st.metric("❌ 미달", fail_count)
def render_accuracy_quality_tab(monitor: HybridPerformanceMonitor):
    """Tab 2: Accuracy & Quality - Detailed metric views"""

    st.header("🎯 정확도 & 품질 지표")

    # Get all metrics
    tcr_metrics = monitor.tcr_tracker.calculate_tcr()
    accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
    quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    hallucination_data = monitor.hallucination_detector.get_hallucination_rate()

    # Create subtabs for each metric
    subtab1, subtab2, subtab3, subtab4, subtab5, subtab6, subtab7, subtab8 = st.tabs([
        "TCR (작업 완료율)",
        "Accuracy (정확도)",
        "Hallucination (환각)",
        "Quality (품질)",
        "Faithfulness (충실도)",
        "Answer Relevancy",
        "Context Recall",
        "Context Precision"
    ])

    # Subtab 1: TCR
    with subtab1:
        st.subheader("📊 작업 완료율 (Task Completion Rate)")

        col1, col2, col3, col4, col5 = st.columns(5)

        overall_tcr = tcr_metrics.get('tcr', 0)
        full_success = tcr_metrics.get('full_success', 0)
        partial_success = tcr_metrics.get('partial_success', 0)
        failures = tcr_metrics.get('failures', 0)
        total_tasks = tcr_metrics.get('total_tasks', 0)

        with col1:
            st.metric("전체 TCR", f"{overall_tcr:.1f}%", help="Task Completion Rate: 모든 작업의 Completion Score 평균")
        with col2:
            st.metric("완전 성공", f"{full_success}", help="Completion Score = 100%")
        with col3:
            st.metric("부분 성공", f"{partial_success}", help="70% ≤ Completion Score < 100%")
        with col4:
            st.metric("실패", f"{failures}", help="Completion Score < 70%")
        with col5:
            benchmark = monitor.tcr_tracker.get_benchmark_status(overall_tcr)
            st.metric("벤치마크 등급", benchmark, help="TCR 기반 성능 등급")

        # Task completion breakdown
        st.markdown("---")
        completed_tasks = full_success + partial_success
        completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Calculate sum of completion scores for accurate display
        tasks_data = monitor.tcr_tracker.tasks
        weighted_sum = sum(t.completion_score for t in tasks_data)

        st.markdown(f"""
        **작업 완료 현황**: {completed_tasks}/{total_tasks} 작업 완료 ({completion_percentage:.1f}%)
        - ✅ **완전 성공**: {full_success}개 (Completion Score = 100%)
        - ⚠️ **부분 성공**: {partial_success}개 (70% ≤ Completion Score < 100%)
        - ❌ **실패**: {failures}개 (Completion Score < 70%)

        💡 **TCR 계산**: (모든 작업의 Completion Score 합) / 전체 작업 × 100 = {weighted_sum:.2f} / {total_tasks} × 100 = **{overall_tcr:.1f}%**
        """)

        # TCR by task type
        st.markdown("#### TaskType별 완료율")
        tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()

        if tcr_by_type:
            df_tcr = pd.DataFrame([
                {
                    'TaskType': task_type,
                    'TCR (%)': data.get('tcr', 0),
                    '완전 성공': data.get('full_success', 0),
                    '부분 성공': data.get('partial_success', 0),
                    '실패': data.get('failures', 0),
                    '전체': data.get('total_tasks', 0)
                }
                for task_type, data in tcr_by_type.items()
            ])

            # Bar chart
            fig = px.bar(
                df_tcr,
                x='TaskType',
                y='TCR (%)',
                title='TaskType별 작업 완료율',
                color='TCR (%)',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width='stretch')

            # Data table
            st.dataframe(df_tcr, width='stretch')

    # Subtab 2: Accuracy
    with subtab2:
        st.subheader("🎯 정확도 (Accuracy)")

        col1, col2, col3, col4 = st.columns(4)

        overall_acc = accuracy_metrics.get('overall_accuracy', 0)
        high_acc_count = accuracy_metrics.get('high_accuracy_count', 0)
        low_acc_count = accuracy_metrics.get('low_accuracy_count', 0)
        avg_acc = accuracy_metrics.get('average_accuracy', 0) * 100

        with col1:
            st.metric("전체 정확도", f"{overall_acc:.1f}%")
        with col2:
            st.metric("높은 정확도 (≥90%)", f"{high_acc_count}")
        with col3:
            st.metric("낮은 정확도 (<70%)", f"{low_acc_count}")
        with col4:
            st.metric("평균 정확도", f"{avg_acc:.1f}%")

        # Accuracy by task type
        st.markdown("#### TaskType별 정확도")
        acc_by_type = monitor.accuracy_evaluator.get_accuracy_by_type()

        if acc_by_type:
            df_acc = pd.DataFrame([
                {
                    'TaskType': task_type,
                    'Accuracy (%)': acc * 100
                }
                for task_type, acc in acc_by_type.items()
            ])

            fig = px.bar(
                df_acc,
                x='TaskType',
                y='Accuracy (%)',
                title='TaskType별 정확도',
                color='Accuracy (%)',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, width='stretch')

            st.dataframe(df_acc, width='stretch')

    # Subtab 3: Hallucination
    with subtab3:
        st.subheader("🚨 환각 탐지 (Hallucination Detection)")

        col1, col2, col3, col4 = st.columns(4)

        hall_rate = hallucination_data.get('hallucination_rate', 0) * 100
        total_checked = hallucination_data.get('total_checked', 0)
        total_flagged = hallucination_data.get('total_flagged', 0)

        with col1:
            st.metric("환각 발생률", f"{hall_rate:.2f}%", delta="낮을수록 좋음", delta_color="inverse")
        with col2:
            st.metric("검사한 응답", f"{total_checked}")
        with col3:
            st.metric("플래그된 응답", f"{total_flagged}")
        with col4:
            safety_status = "안전" if hall_rate < 5 else "경고" if hall_rate < 10 else "위험"
            st.metric("안전 등급", safety_status)

        st.markdown("#### 환각 탐지 설명")
        st.info("""
        **환각(Hallucination)**은 AI가 사실이 아니거나 제공되지 않은 정보를 생성하는 현상입니다.

        - **낮음 (<5%)**: 매우 안전한 수준
        - **보통 (5-10%)**: 주의 필요
        - **높음 (>10%)**: 개선 필요

        환각률이 높다면 프롬프트 개선이나 검증 메커니즘 추가를 권장합니다.
        """)

    # Subtab 4: Quality
    with subtab4:
        st.subheader("⭐ 응답 품질 (Response Quality)")

        col1, col2, col3, col4 = st.columns(4)

        avg_quality = quality_metrics.get('average_quality', 0)
        max_quality = quality_metrics.get('max_quality', 0)
        min_quality = quality_metrics.get('min_quality', 0)
        high_quality_count = quality_metrics.get('high_quality_count', 0)

        with col1:
            st.metric("평균 품질", f"{avg_quality:.1f}/10")
        with col2:
            st.metric("최고 품질", f"{max_quality:.1f}/10")
        with col3:
            st.metric("최저 품질", f"{min_quality:.1f}/10")
        with col4:
            st.metric("고품질 응답 (≥8)", f"{high_quality_count}")

        # Quality distribution
        st.markdown("#### 품질 점수 분포")

        quality_ranges = quality_metrics.get('quality_distribution', {})
        if quality_ranges:
            df_quality = pd.DataFrame([
                {'범위': k, '개수': v}
                for k, v in quality_ranges.items()
            ])

            fig = px.pie(
                df_quality,
                values='개수',
                names='범위',
                title='품질 점수 분포',
                hole=0.3
            )
            st.plotly_chart(fig, width='stretch')

    # Subtabs 5-8: RAG Metrics (Ragas)
    for subtab_idx, (subtab, metric_name, metric_key, description) in enumerate([
        (subtab5, "Faithfulness", "ragas_faithfulness", "답변이 제공된 컨텍스트에 얼마나 충실한지 측정 (환각 방지)"),
        (subtab6, "Answer Relevancy", "ragas_answer_relevancy", "답변이 질문과 얼마나 관련있는지 측정"),
        (subtab7, "Context Recall", "ragas_context_recall", "필요한 정보를 컨텍스트에서 얼마나 잘 검색했는지 측정 (완전성)"),
        (subtab8, "Context Precision", "ragas_context_precision", "검색된 컨텍스트가 얼마나 정확한지 측정 (노이즈 최소화)")
    ], start=5):
        with subtab:
            st.subheader(f"🔍 {metric_name}")
            st.info(f"📝 {description}")

            # Check if advanced metrics are available
            if hasattr(monitor, 'advanced_metrics') and monitor.advanced_metrics:
                # Get metric values
                metric_values = [
                    m.get(metric_key, 0)
                    for m in monitor.advanced_metrics.values()
                    if metric_key in m
                ]

                if metric_values:
                    avg_value = sum(metric_values) / len(metric_values)
                    max_value = max(metric_values)
                    min_value = min(metric_values)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("평균", f"{avg_value:.2f}")
                    with col2:
                        st.metric("최대", f"{max_value:.2f}")
                    with col3:
                        st.metric("최소", f"{min_value:.2f}")

                    # Distribution chart
                    fig = go.Figure()
                    fig.add_trace(go.Histogram(
                        x=metric_values,
                        nbinsx=20,
                        name=metric_name,
                        marker_color='lightblue'
                    ))
                    fig.update_layout(
                        title=f'{metric_name} 분포',
                        xaxis_title=metric_name,
                        yaxis_title='빈도',
                        showlegend=False
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.warning(f"{metric_name} 데이터가 없습니다.")
            else:
                st.warning(f"""
                {metric_name} 메트릭을 사용하려면 평가 시 다음을 활성화하세요:

                ```python
                monitor.record_task(
                    task,
                    enable_advanced_metrics=True,
                    input_text=question,
                    output_text=answer,
                    retrieved_context=context  # RAG 메트릭에 필요
                )
                ```
                """)


def render_efficiency_tab(monitor: HybridPerformanceMonitor):
    """Tab 3: Efficiency - Latency and cost metrics"""

    st.header("⚡ 효율성 지표")

    efficiency_stats = get_efficiency_stats(monitor)
    latency_stats = monitor.latency_tracker.get_latency_stats()
    usage_stats = monitor.token_tracker.get_usage_stats()

    # Create subtabs
    subtab1, subtab2, subtab3 = st.tabs([
        "⏱️ 응답 시간 (Latency)",
        "💰 비용 (Cost)",
        "🔧 도구 효율성 (Tool Efficiency)"
    ])

    # Subtab 1: Latency
    with subtab1:
        st.subheader("⏱️ 응답 시간 분석")

        col1, col2, col3, col4 = st.columns(4)

        avg_latency = latency_stats.get('average', 0)
        p50_latency = latency_stats.get('p50', 0)
        p95_latency = latency_stats.get('p95', 0)
        max_latency = latency_stats.get('max', 0)

        with col1:
            st.metric("평균 응답 시간", f"{avg_latency:.2f}s")
        with col2:
            st.metric("P50 (중앙값)", f"{p50_latency:.2f}s")
        with col3:
            st.metric("P95", f"{p95_latency:.2f}s")
        with col4:
            st.metric("최대", f"{max_latency:.2f}s")

        # Latency by task type
        st.markdown("#### TaskType별 응답 시간")

        # Get tasks and create DataFrame
        if monitor.tcr_tracker.tasks:
            task_data = []
            for task in monitor.tcr_tracker.tasks:
                task_data.append({
                    'TaskType': task.task_type,
                    'Execution Time (s)': task.execution_time
                })

            df_latency = pd.DataFrame(task_data)

            # Box plot
            fig = px.box(
                df_latency,
                x='TaskType',
                y='Execution Time (s)',
                title='TaskType별 응답 시간 분포',
                points='all'
            )
            st.plotly_chart(fig, width='stretch')

            # Summary by type
            latency_by_type_df = df_latency.groupby('TaskType')['Execution Time (s)'].agg([
                ('평균', 'mean'),
                ('중앙값', 'median'),
                ('최소', 'min'),
                ('최대', 'max')
            ]).reset_index()

            st.dataframe(latency_by_type_df, width='stretch')

    # Subtab 2: Cost
    with subtab2:
        st.subheader("💰 비용 분석")

        col1, col2, col3, col4 = st.columns(4)

        total_cost = efficiency_stats.get('total_cost', 0)
        cost_per_task = efficiency_stats.get('cost_per_task', 0)
        total_tokens = usage_stats.get('total_tokens', 0)
        avg_tokens = usage_stats.get('avg_tokens_per_task', 0)  # Fixed: average_tokens_per_task → avg_tokens_per_task

        with col1:
            st.metric("총 비용", f"${total_cost:.4f}")
        with col2:
            st.metric("Task당 비용", f"${cost_per_task:.4f}")
        with col3:
            st.metric("총 토큰 사용", f"{total_tokens:,}")
        with col4:
            st.metric("Task당 평균 토큰", f"{avg_tokens:.0f}")

        # Token usage breakdown
        st.markdown("#### 토큰 사용 상세")

        col1, col2, col3 = st.columns(3)

        with col1:
            input_tokens = usage_stats.get('total_input_tokens', 0)
            st.metric("Input 토큰", f"{input_tokens:,}")

        with col2:
            output_tokens = usage_stats.get('total_output_tokens', 0)
            st.metric("Output 토큰", f"{output_tokens:,}")

        with col3:
            if total_tokens > 0:
                input_ratio = (input_tokens / total_tokens) * 100
                st.metric("Input 비율", f"{input_ratio:.1f}%")

        # Cost trend (if multiple evaluations)
        st.markdown("#### 비용 최적화 제안")

        if cost_per_task > 0.05:
            st.warning(f"""
            ⚠️ Task당 평균 비용이 ${cost_per_task:.4f}로 높습니다.

            **최적화 방안:**
            - 프롬프트 길이 최적화
            - 불필요한 컨텍스트 제거
            - 더 작은 모델 사용 검토
            - 캐싱 활용
            """)
        elif cost_per_task > 0.02:
            st.info(f"""
            💡 Task당 비용: ${cost_per_task:.4f}

            적정 수준이지만 추가 최적화 가능합니다.
            """)
        else:
            st.success(f"""
            ✅ Task당 비용: ${cost_per_task:.4f}

            매우 효율적인 비용 수준입니다!
            """)

    # Subtab 3: Tool Efficiency
    with subtab3:
        st.subheader("🔧 도구 효율성 분석")

        # Get tool efficiency stats
        tool_stats = monitor.tool_analyzer.get_efficiency_stats()

        if not tool_stats or tool_stats.get('total_calls', 0) == 0:
            st.info("""
            📊 도구 호출 데이터가 없습니다.

            Agent가 도구를 사용하는 경우, 여기에서 도구 효율성 지표를 확인할 수 있습니다.
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            total_calls = tool_stats.get('total_calls', 0)
            success_rate = tool_stats.get('success_rate', 0)
            efficiency_score = tool_stats.get('avg_efficiency_score', 0)
            redundancy_rate = tool_stats.get('redundancy_rate', 0)

            with col1:
                st.metric("총 도구 호출", f"{total_calls:,}")
            with col2:
                st.metric("성공률", f"{success_rate:.1f}%", delta=f"{success_rate - 95:.1f}%" if success_rate < 95 else None)
            with col3:
                st.metric("효율성 점수", f"{efficiency_score:.1f}%", delta=f"{efficiency_score - 80:.1f}%" if efficiency_score < 80 else None)
            with col4:
                st.metric("중복률", f"{redundancy_rate:.1f}%", delta=f"{10 - redundancy_rate:.1f}%" if redundancy_rate > 10 else None)

            # Additional metrics
            st.markdown("#### 상세 지표")

            col1, col2, col3 = st.columns(3)

            with col1:
                avg_calls = tool_stats.get('avg_calls_per_task', 0)
                st.metric("Task당 평균 호출", f"{avg_calls:.1f}")

            with col2:
                avg_duration = tool_stats.get('avg_duration', 0)
                st.metric("평균 실행 시간", f"{avg_duration:.3f}s")

            with col3:
                failure_rate = tool_stats.get('failure_rate', 0)
                st.metric("실패율", f"{failure_rate:.1f}%")

            # Tool efficiency breakdown
            st.markdown("#### 도구 효율성 분석")

            # Create summary table
            summary_data = {
                "지표": [
                    "총 도구 호출",
                    "성공한 호출",
                    "실패한 호출",
                    "중복 호출",
                    "Task당 평균 호출"
                ],
                "값": [
                    f"{total_calls:,}",
                    f"{int(total_calls * success_rate / 100):,}",
                    f"{tool_stats.get('total_failed_calls', 0):,}",
                    f"{tool_stats.get('total_redundant_calls', 0):,}",
                    f"{avg_calls:.2f}"
                ]
            }

            df_summary = pd.DataFrame(summary_data)
            st.dataframe(df_summary, width='stretch', hide_index=True)

            # Efficiency recommendations
            st.markdown("#### 최적화 제안")

            issues = []

            if success_rate < 95:
                issues.append({
                    "severity": "🔴 높음",
                    "issue": f"도구 성공률이 {success_rate:.1f}%로 낮습니다 (목표: 95%)",
                    "suggestion": "도구 파라미터 검증, 에러 핸들링 개선, 도구 설정 확인"
                })

            if efficiency_score < 80:
                issues.append({
                    "severity": "🟡 중간",
                    "issue": f"효율성 점수가 {efficiency_score:.1f}%로 낮습니다 (목표: 80%)",
                    "suggestion": "중복 호출 제거, 실패한 호출 원인 분석, 도구 선택 로직 개선"
                })

            if redundancy_rate > 10:
                issues.append({
                    "severity": "🟡 중간",
                    "issue": f"중복 호출률이 {redundancy_rate:.1f}%로 높습니다 (목표: <10%)",
                    "suggestion": "도구 호출 전 결과 캐싱, 동일 파라미터 호출 방지 로직 추가"
                })

            if avg_duration > 2.0:
                issues.append({
                    "severity": "🟢 낮음",
                    "issue": f"평균 실행 시간이 {avg_duration:.3f}초입니다 (목표: <2초)",
                    "suggestion": "비동기 호출 고려, 도구 최적화, 타임아웃 설정 조정"
                })

            if issues:
                for issue in issues:
                    with st.expander(f"{issue['severity']} - {issue['issue']}"):
                        st.write(f"**문제:** {issue['issue']}")
                        st.write(f"**제안:** {issue['suggestion']}")
            else:
                st.success("""
                ✅ 모든 도구 효율성 지표가 목표치를 달성했습니다!

                현재 도구 사용 패턴이 매우 효율적입니다.
                """)


def render_advanced_metrics_tab(monitor: HybridPerformanceMonitor):
    """Tab 4: Advanced Metrics - DeepEval and Ragas"""

    st.header("🔬 고급 평가 지표")

    # Generate report first to check advanced metrics
    report = monitor.generate_hybrid_report()
    adv_metrics = report.advanced_metrics_summary if hasattr(report, 'advanced_metrics_summary') else {}

    # Check if there are any advanced metrics in the report
    has_external_metrics = any(
        key in adv_metrics and adv_metrics[key]
        for key in ['g_eval_score', 'hallucination_score', 'answer_relevancy_score',
                    'ragas_faithfulness', 'ragas_context_recall', 'ragas_context_precision',
                    'ragas_answer_relevancy']
    )

    if not has_external_metrics:
        st.info("""
        📊 기본 평가 지표만 사용 중입니다.

        **외부 라이브러리 기반 고급 지표를 사용하려면:**

        ```python
        from agent_evaluator.core.hybrid_monitor import create_monitor

        # 프로필 선택: 'minimal', 'balanced', 'comprehensive', 'rag'
        monitor = create_monitor(profile="balanced")

        # 평가 시 고급 메트릭 활성화
        monitor.record_task(
            task,
            enable_advanced_metrics=True,
            input_text=question,
            output_text=answer,
            expected_output=expected,
            quality_criteria="평가 기준"
        )
        ```

        **프로필별 지원 메트릭:**
        - **minimal**: 기본 메트릭만 (무료)
        - **balanced**: DeepEval 주요 메트릭
        - **comprehensive**: DeepEval 전체 메트릭
        - **rag**: RAG 시스템용 Ragas 메트릭

        **현재 제공 중인 기본 지표:**
        - Hallucination Detection (Rule-based)
        - Quality Evaluation
        - Token Usage & Cost
        """)
        # Don't return - still show available metrics below

    # Create subtabs
    subtab1, subtab2 = st.tabs([
        "🤖 DeepEval 지표",
        "📚 Ragas 지표 (RAG 평가)"
    ])

    # Subtab 1: DeepEval
    with subtab1:
        st.subheader("🤖 DeepEval 지표")

        st.markdown("""
        **DeepEval**은 LLM을 사용하여 AI 응답의 품질을 평가하는 프레임워크입니다.
        """)

        # G-Eval
        st.markdown("#### 🌟 G-Eval (품질 평가)")
        g_eval_data = adv_metrics.get('g_eval_score', {})

        if g_eval_data:
            col1, col2, col3 = st.columns(3)

            g_eval_mean = g_eval_data.get('mean', 0)
            g_eval_max = g_eval_data.get('max', 0)
            g_eval_min = g_eval_data.get('min', 0)

            with col1:
                st.metric("평균 G-Eval", f"{g_eval_mean:.3f}")
                if g_eval_mean >= 0.9:
                    st.success("✅ 우수")
                elif g_eval_mean >= 0.7:
                    st.warning("⚠️ 보통")
                else:
                    st.error("❌ 개선 필요")

            with col2:
                st.metric("최대", f"{g_eval_max:.3f}")

            with col3:
                st.metric("최소", f"{g_eval_min:.3f}")

            st.info("""
            **G-Eval**: LLM 기반 종합 품질 평가
            - ≥0.9: 매우 우수
            - 0.7-0.9: 양호
            - <0.7: 개선 필요
            """)
        else:
            st.info("G-Eval 데이터 없음")

        st.markdown("---")

        # Hallucination Detection (AI-based)
        st.markdown("#### 🚨 Hallucination Detection (AI 기반)")
        hall_data = adv_metrics.get('hallucination_score', {})

        if hall_data:
            col1, col2, col3 = st.columns(3)

            hall_mean = hall_data.get('mean', 0)
            hall_max = hall_data.get('max', 0)
            hall_min = hall_data.get('min', 0)

            with col1:
                st.metric("평균 환각 점수", f"{hall_mean:.3f}")
                if hall_mean <= 0.3:
                    st.success("✅ 안전")
                elif hall_mean <= 0.5:
                    st.warning("⚠️ 주의")
                else:
                    st.error("❌ 위험")

            with col2:
                st.metric("최대", f"{hall_max:.3f}")

            with col3:
                st.metric("최소", f"{hall_min:.3f}")

            st.info("""
            **AI 환각 탐지**: LLM으로 환각 탐지
            - ≤0.3: 안전
            - 0.3-0.5: 주의 필요
            - >0.5: 위험 (낮을수록 좋음)
            """)
        else:
            st.info("Hallucination Detection 데이터 없음")

        st.markdown("---")

        # Toxicity
        st.markdown("#### ☢️ Toxicity (유해성)")
        toxicity_data = adv_metrics.get('toxicity_score', {})

        if toxicity_data:
            col1, col2, col3 = st.columns(3)

            tox_mean = toxicity_data.get('mean', 0)
            tox_max = toxicity_data.get('max', 0)
            tox_min = toxicity_data.get('min', 0)

            with col1:
                st.metric("평균 유해성 점수", f"{tox_mean:.3f}")
                if tox_mean <= 0.3:
                    st.success("✅ 안전")
                elif tox_mean <= 0.5:
                    st.warning("⚠️ 주의")
                else:
                    st.error("❌ 위험")

            with col2:
                st.metric("최대", f"{tox_max:.3f}")

            with col3:
                st.metric("최소", f"{tox_min:.3f}")

            st.info("""
            **유해성 점수**: 공격적이거나 부적절한 콘텐츠 탐지
            - ≤0.3: 안전
            - 0.3-0.5: 주의
            - >0.5: 위험 (낮을수록 좋음)
            """)
        else:
            st.info("Toxicity 데이터 없음")

        st.markdown("---")

        # Bias
        st.markdown("#### ⚖️ Bias (편향성)")
        bias_data = adv_metrics.get('bias_score', {})

        if bias_data:
            col1, col2, col3 = st.columns(3)

            bias_mean = bias_data.get('mean', 0)
            bias_max = bias_data.get('max', 0)
            bias_min = bias_data.get('min', 0)

            with col1:
                st.metric("평균 편향성 점수", f"{bias_mean:.3f}")
                if bias_mean <= 0.3:
                    st.success("✅ 공정")
                elif bias_mean <= 0.5:
                    st.warning("⚠️ 주의")
                else:
                    st.error("❌ 편향됨")

            with col2:
                st.metric("최대", f"{bias_max:.3f}")

            with col3:
                st.metric("최소", f"{bias_min:.3f}")

            st.info("""
            **편향성 점수**: 성별, 인종 등의 편향 탐지
            - ≤0.3: 공정
            - 0.3-0.5: 주의
            - >0.5: 편향됨 (낮을수록 좋음)
            """)
        else:
            st.info("Bias 데이터 없음")

        st.markdown("---")

        # Answer Relevancy (DeepEval)
        st.markdown("#### 🎯 Answer Relevancy (답변 관련성)")
        answer_rel_data = adv_metrics.get('answer_relevancy_score', {})

        if answer_rel_data:
            col1, col2, col3 = st.columns(3)

            rel_mean = answer_rel_data.get('mean', 0)
            rel_max = answer_rel_data.get('max', 0)
            rel_min = answer_rel_data.get('min', 0)

            with col1:
                st.metric("평균 관련성 점수", f"{rel_mean:.3f}")
                if rel_mean >= 0.8:
                    st.success("✅ 우수")
                elif rel_mean >= 0.6:
                    st.warning("⚠️ 보통")
                else:
                    st.error("❌ 개선 필요")

            with col2:
                st.metric("최대", f"{rel_max:.3f}")

            with col3:
                st.metric("최소", f"{rel_min:.3f}")

            st.info("""
            **Answer Relevancy**: 답변이 질문과 얼마나 관련있는지 측정 (DeepEval)
            - ≥0.8: 매우 관련성 높음
            - 0.6-0.8: 적절한 관련성
            - <0.6: 관련성 부족 (높을수록 좋음)
            """)
        else:
            st.info("Answer Relevancy 데이터 없음")

    # Subtab 2: Ragas
    with subtab2:
        st.subheader("📚 Ragas 지표 (RAG 시스템 평가)")

        st.markdown("""
        **Ragas**는 RAG (Retrieval-Augmented Generation) 시스템을 평가하기 위한 프레임워크입니다.
        """)

        # Check for Ragas metrics (corrected metric names to match actual implementation)
        ragas_metrics_found = any(key in adv_metrics for key in [
            'ragas_faithfulness', 'ragas_context_precision', 'ragas_context_recall',
            'ragas_answer_relevancy', 'ragas_overall_score'
        ])

        if not ragas_metrics_found:
            st.info("""
            Ragas 메트릭을 사용하려면 RAG 프로필로 모니터를 생성하고 컨텍스트를 제공하세요:

            ```python
            monitor = create_monitor(profile="rag")

            monitor.record_task(
                task,
                enable_advanced_metrics=True,
                input_text=question,
                output_text=answer,
                expected_output=expected,
                retrieved_context=context_list  # 필수!
            )
            ```
            """)
            return

        # Faithfulness (컨텍스트 충실도)
        st.markdown("#### 🎯 Faithfulness (컨텍스트 충실도)")
        faithfulness_data = adv_metrics.get('ragas_faithfulness', {})

        if faithfulness_data:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("평균", f"{faithfulness_data.get('mean', 0):.3f}")
            with col2:
                st.metric("최대", f"{faithfulness_data.get('max', 0):.3f}")
            with col3:
                st.metric("최소", f"{faithfulness_data.get('min', 0):.3f}")

            st.info("생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정 (환각 방지)")
        else:
            st.warning("Faithfulness 데이터 없음")

        st.markdown("---")

        # Context Precision (검색 정밀도)
        st.markdown("#### 📝 Context Precision (검색 정밀도)")
        context_precision_data = adv_metrics.get('ragas_context_precision', {})

        if context_precision_data:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("평균", f"{context_precision_data.get('mean', 0):.3f}")
            with col2:
                st.metric("최대", f"{context_precision_data.get('max', 0):.3f}")
            with col3:
                st.metric("최소", f"{context_precision_data.get('min', 0):.3f}")

            st.info("검색된 컨텍스트 중 관련 있는 정보의 비율 (노이즈 최소화)")
        else:
            st.warning("Context Precision 데이터 없음")

        st.markdown("---")

        # Context Recall (검색 재현율)
        st.markdown("#### ✅ Context Recall (검색 재현율)")
        context_recall_data = adv_metrics.get('ragas_context_recall', {})

        if context_recall_data:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("평균", f"{context_recall_data.get('mean', 0):.3f}")
            with col2:
                st.metric("최대", f"{context_recall_data.get('max', 0):.3f}")
            with col3:
                st.metric("최소", f"{context_recall_data.get('min', 0):.3f}")

            st.info("필요한 정보를 모두 검색했는지 측정 (완전성)")
        else:
            st.warning("Context Recall 데이터 없음")

        st.markdown("---")

        # Answer Relevancy (답변 관련성)
        st.markdown("#### 🔍 Answer Relevancy (답변 관련성)")
        answer_relevancy_data = adv_metrics.get('ragas_answer_relevancy', {})

        if answer_relevancy_data:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("평균", f"{answer_relevancy_data.get('mean', 0):.3f}")
            with col2:
                st.metric("최대", f"{answer_relevancy_data.get('max', 0):.3f}")
            with col3:
                st.metric("최소", f"{answer_relevancy_data.get('min', 0):.3f}")

            st.info("생성된 답변이 질문과 얼마나 관련있는지 측정")
        else:
            st.warning("Answer Relevancy 데이터 없음")

        st.markdown("---")

        # Overall Score
        st.markdown("#### 🏆 Ragas Overall Score")
        overall_data = adv_metrics.get('ragas_overall_score', {})

        if overall_data:
            overall_mean = overall_data.get('mean', 0)

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("평균 종합 점수", f"{overall_mean:.3f}")
                if overall_mean >= 0.8:
                    st.success("✅ 우수")
                elif overall_mean >= 0.6:
                    st.warning("⚠️ 보통")
                else:
                    st.error("❌ 개선 필요")

            with col2:
                st.metric("최대", f"{overall_data.get('max', 0):.3f}")

            with col3:
                st.metric("최소", f"{overall_data.get('min', 0):.3f}")

            st.info("""
            **Ragas 종합 점수**: 모든 Ragas 메트릭의 가중 평균
            - ≥0.8: RAG 시스템 우수
            - 0.6-0.8: 양호
            - <0.6: 개선 필요
            """)


def render_alerts_tab(monitor: HybridPerformanceMonitor):
    """Tab 5: Alerts - Threshold violations and warnings"""

    st.header("🚨 알림 및 경고")

    # Check if thresholds are configured
    if not hasattr(monitor, 'thresholds') or not monitor.thresholds:
        st.warning("""
        임계값이 설정되지 않았습니다.

        **임계값 설정하기:**

        ```python
        monitor = PerformanceMonitor()
        monitor.load_thresholds_from_config('config.json')
        ```

        또는 데이터 편집 대시보드에서 설정할 수 있습니다:
        `streamlit run dashboard_data_editor.py`
        """)
        return

    # Get threshold comparison
    threshold_comparison = monitor.compare_with_thresholds()

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)

    basic_metrics = threshold_comparison.get('basic_metrics', {})
    advanced_metrics = threshold_comparison.get('advanced_metrics', {})

    all_statuses = [m.get('status') for m in list(basic_metrics.values()) + list(advanced_metrics.values())]

    pass_count = all_statuses.count('pass')
    fail_count = all_statuses.count('fail')
    warn_count = all_statuses.count('warning')
    total_count = len(all_statuses)

    with col1:
        st.metric("✅ 통과", f"{pass_count}/{total_count}")

    with col2:
        st.metric("⚠️ 경고", f"{warn_count}/{total_count}")

    with col3:
        st.metric("❌ 미달", f"{fail_count}/{total_count}")

    with col4:
        pass_rate = (pass_count / total_count * 100) if total_count > 0 else 0
        st.metric("통과율", f"{pass_rate:.1f}%")

    st.markdown("---")

    # Failed metrics (critical alerts)
    st.subheader("❌ 임계값 미달 (즉시 조치 필요)")

    failed_metrics = [
        (name, data) for name, data in {**basic_metrics, **advanced_metrics}.items()
        if data.get('status') == 'fail'
    ]

    if failed_metrics:
        for metric_key, metric_data in failed_metrics:
            with st.expander(f"❌ {metric_data.get('name', metric_key)}", expanded=True):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("현재 값", f"{metric_data.get('current_value', 0)}")

                with col2:
                    st.metric("임계값", f"{metric_data.get('threshold', 0)}")

                with col3:
                    deviation = metric_data.get('deviation', 0)
                    st.metric("편차", f"{deviation:+.1f}%")

                st.error(f"""
                **조치 필요**: {metric_data.get('name')}가 임계값을 미달했습니다.

                - 현재 값: {metric_data.get('current_value')}
                - 목표 임계값: {metric_data.get('threshold')}
                - 편차: {deviation:.1f}%

                **권장 조치:**
                1. 해당 메트릭의 원인 분석
                2. 프롬프트 또는 시스템 개선
                3. 재평가 후 결과 확인
                """)
    else:
        st.success("✅ 임계값 미달 항목이 없습니다!")

    st.markdown("---")

    # Warning metrics
    st.subheader("⚠️ 경고 (주의 필요)")

    warning_metrics = [
        (name, data) for name, data in {**basic_metrics, **advanced_metrics}.items()
        if data.get('status') == 'warning'
    ]

    if warning_metrics:
        for metric_key, metric_data in warning_metrics:
            with st.expander(f"⚠️ {metric_data.get('name', metric_key)}"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("현재 값", f"{metric_data.get('current_value', 0)}")

                with col2:
                    st.metric("임계값", f"{metric_data.get('threshold', 0)}")

                with col3:
                    deviation = metric_data.get('deviation', 0)
                    st.metric("편차", f"{deviation:+.1f}%")

                st.warning(f"""
                **주의**: {metric_data.get('name')}가 임계값에 근접했습니다.

                현재는 허용 범위 내이지만 모니터링이 필요합니다.
                """)
    else:
        st.info("경고 항목이 없습니다.")

    st.markdown("---")

    # Passed metrics
    st.subheader("✅ 통과")

    passed_metrics = [
        (name, data) for name, data in {**basic_metrics, **advanced_metrics}.items()
        if data.get('status') == 'pass'
    ]

    if passed_metrics:
        with st.expander(f"✅ 통과한 메트릭 ({len(passed_metrics)}개)", expanded=False):
            for metric_key, metric_data in passed_metrics:
                st.markdown(f"**{metric_data.get('name')}**: {metric_data.get('current_value')} (임계값: {metric_data.get('threshold')})")


def render_detailed_analysis_tab(monitor: HybridPerformanceMonitor):
    """Tab 6: Detailed Analysis - Deep dive into results"""

    st.header("📈 상세 분석")

    st.info("개별 태스크 결과 및 심층 분석")

    # Task list
    if not monitor.tcr_tracker.tasks:
        st.warning("평가된 태스크가 없습니다.")
        return

    st.subheader(f"📋 전체 태스크 목록 ({len(monitor.tcr_tracker.tasks)}개)")

    # Create DataFrame
    task_data = []
    for task in monitor.tcr_tracker.tasks:
        task_data.append({
            'Task ID': task.task_id,
            'Type': task.task_type,
            'Success': '✅' if task.success else '❌',
            'TCR': f"{task.completion_score * 100:.1f}%",
            'Accuracy': f"{task.accuracy_score * 100:.1f}%",
            'Time (s)': f"{task.execution_time:.2f}",
            'Attempts': task.attempts,
            'Errors': len(task.errors)
        })

    df_tasks = pd.DataFrame(task_data)

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        task_types = ['All'] + list(df_tasks['Type'].unique())
        selected_type = st.selectbox("TaskType 필터", task_types)

    with col2:
        success_filter = st.selectbox("성공/실패 필터", ['All', 'Success', 'Failure'])

    with col3:
        sort_by = st.selectbox("정렬 기준", ['Task ID', 'Time (s)', 'TCR', 'Accuracy'])

    # Apply filters
    filtered_df = df_tasks.copy()

    if selected_type != 'All':
        filtered_df = filtered_df[filtered_df['Type'] == selected_type]

    if success_filter == 'Success':
        filtered_df = filtered_df[filtered_df['Success'] == '✅']
    elif success_filter == 'Failure':
        filtered_df = filtered_df[filtered_df['Success'] == '❌']

    # Display table
    st.dataframe(filtered_df, width='stretch')

    # Task details
    st.markdown("---")
    st.subheader("🔍 개별 태스크 상세 정보")

    selected_task_id = st.selectbox(
        "태스크 선택",
        [task.task_id for task in monitor.tcr_tracker.tasks]
    )

    if selected_task_id:
        task = next((t for t in monitor.tcr_tracker.tasks if t.task_id == selected_task_id), None)

        if task:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**기본 정보**")
                st.write(f"- **Task ID**: {task.task_id}")
                st.write(f"- **Type**: {task.task_type}")
                st.write(f"- **Success**: {'✅ Yes' if task.success else '❌ No'}")
                st.write(f"- **Timestamp**: {task.timestamp}")
                st.write(f"- **Attempts**: {task.attempts}")

            with col2:
                st.markdown("**성능 지표**")
                st.write(f"- **Completion Score**: {task.completion_score * 100:.1f}%")
                st.write(f"- **Accuracy Score**: {task.accuracy_score * 100:.1f}%")
                st.write(f"- **Execution Time**: {task.execution_time:.2f}s")
                st.write(f"- **Tokens Used**: {task.tokens_used.get('total', 0)}")

            if task.errors:
                st.markdown("**오류 정보**")
                for error in task.errors:
                    st.error(error)

            if task.tool_calls:
                st.markdown("**도구 호출**")
                for tool_call in task.tool_calls:
                    st.write(f"- {tool_call}")


def render_report_tab(monitor: HybridPerformanceMonitor):
    """Tab 7: Report - Comprehensive evaluation report"""

    st.header("📝 종합 평가 리포트")

    report = monitor.generate_hybrid_report()

    # Executive Summary
    st.subheader("📊 요약")

    summary_col1, summary_col2, summary_col3 = st.columns(3)

    with summary_col1:
        st.markdown("### 전체 평가")
        st.metric("총 Task 수", report.total_tasks)

        tcr_data = extract_report_value(report, 'accuracy_metrics.tcr', {})
        success_rate = tcr_data.get('success_rate', 0) if isinstance(tcr_data, dict) else 0
        tcr_value = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0

        st.metric("성공률", f"{success_rate:.1f}%")
        st.metric("TCR", f"{tcr_value:.1f}%")

    with summary_col2:
        st.markdown("### 품질")
        st.metric("정확도", f"{extract_report_value(report, 'accuracy_metrics.accuracy_scores', {}).get('overall_accuracy', 0):.1f}%")
        st.metric("응답 품질", f"{extract_report_value(report, 'accuracy_metrics.quality', {}).get('average_quality', 0):.1f}/10")
        st.metric("환각률", f"{extract_report_value(report, 'accuracy_metrics.hallucination', {}).get('hallucination_rate', 0) * 100:.2f}%")

    with summary_col3:
        st.markdown("### 효율성")
        st.metric("평균 시간", f"{extract_report_value(report, 'efficiency_metrics.latency', {}).get('mean', 0):.2f}s")
        st.metric("총 비용", f"${extract_report_value(report, 'efficiency_metrics.tokens', {}).get('total_cost', 0):.4f}")
        st.metric("Task당 비용", f"${extract_report_value(report, 'efficiency_metrics.tokens', {}).get('cost_per_task', 0):.4f}")

    st.markdown("---")

    # Detailed sections
    st.subheader("📋 상세 분석")

    # Performance by TaskType
    st.markdown("### TaskType별 성능")

    if monitor.tcr_tracker.tasks:
        # Group by task type
        task_type_summary = {}
        for task in monitor.tcr_tracker.tasks:
            task_type = task.task_type
            if task_type not in task_type_summary:
                task_type_summary[task_type] = {
                    'count': 0,
                    'success': 0,
                    'total_time': 0,
                    'total_tcr': 0
                }

            task_type_summary[task_type]['count'] += 1
            if task.success:
                task_type_summary[task_type]['success'] += 1
            task_type_summary[task_type]['total_time'] += task.execution_time
            task_type_summary[task_type]['total_tcr'] += task.completion_score

        # Create DataFrame
        type_summary_data = []
        for task_type, data in task_type_summary.items():
            type_summary_data.append({
                'TaskType': task_type,
                'Count': data['count'],
                'Success Rate': f"{(data['success'] / data['count'] * 100):.1f}%",
                'Avg TCR': f"{(data['total_tcr'] / data['count'] * 100):.1f}%",
                'Avg Time': f"{(data['total_time'] / data['count']):.2f}s"
            })

        df_type_summary = pd.DataFrame(type_summary_data)
        st.dataframe(df_type_summary, width='stretch')

    st.markdown("---")

    # Recommendations
    st.subheader("💡 권장사항")

    # Generate recommendations based on metrics
    recommendations = []

    tcr = extract_report_value(report, 'accuracy_metrics.tcr', {}).get('tcr', 0)
    if tcr < 90:
        recommendations.append({
            'priority': 'High',
            'area': 'TCR',
            'issue': f'TCR이 {tcr:.1f}%로 목표(90%) 미달',
            'action': '작업 완료 로직 개선, 에러 처리 강화 필요'
        })

    accuracy = extract_report_value(report, 'accuracy_metrics.accuracy_scores', {}).get('overall_accuracy', 0)
    if accuracy < 0.85:
        recommendations.append({
            'priority': 'High',
            'area': 'Accuracy',
            'issue': f'정확도가 {accuracy * 100:.1f}%로 목표(85%) 미달',
            'action': '프롬프트 개선, 더 강력한 모델 사용 검토'
        })

    hall_rate = extract_report_value(report, 'accuracy_metrics.hallucination', {}).get('hallucination_rate', 0)
    if hall_rate > 0.05:
        recommendations.append({
            'priority': 'High',
            'area': 'Hallucination',
            'issue': f'환각률이 {hall_rate * 100:.2f}%로 높음',
            'action': '사실 검증 메커니즘 추가, 컨텍스트 강화'
        })

    avg_time = extract_report_value(report, 'efficiency_metrics.latency', {}).get('mean', 0)
    if avg_time > 3.0:
        recommendations.append({
            'priority': 'Medium',
            'area': 'Latency',
            'issue': f'평균 응답 시간이 {avg_time:.2f}s로 느림',
            'action': '프롬프트 최적화, 캐싱 활용, 더 빠른 모델 검토'
        })

    cost_per_task = extract_report_value(report, 'efficiency_metrics.tokens', {}).get('cost_per_task', 0)
    if cost_per_task > 0.05:
        recommendations.append({
            'priority': 'Medium',
            'area': 'Cost',
            'issue': f'Task당 비용이 ${cost_per_task:.4f}로 높음',
            'action': '토큰 사용 최적화, 더 저렴한 모델 검토'
        })

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            priority_color = "🔴" if rec['priority'] == 'High' else "🟡"
            with st.expander(f"{priority_color} {rec['area']}: {rec['issue']}", expanded=(rec['priority'] == 'High')):
                st.markdown(f"**우선순위**: {rec['priority']}")
                st.markdown(f"**문제**: {rec['issue']}")
                st.markdown(f"**조치사항**: {rec['action']}")
    else:
        st.success("✅ 모든 메트릭이 목표를 달성했습니다!")

    st.markdown("---")

    # Export report
    st.subheader("📥 리포트 내보내기")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("JSON으로 내보내기"):
            report_dict = {
                'summary': {
                    'total_tasks': report.total_tasks,
                    'success_rate': (extract_report_value(report, 'accuracy_metrics.tcr', {}).get('success_rate', 0) / 100.0),
                    'tcr': extract_report_value(report, 'accuracy_metrics.tcr', {}).get('tcr', 0),
                },
                'accuracy': report.accuracy_metrics,
                'quality': report.quality_metrics,
                'performance': report.efficiency_metrics,
                'recommendations': recommendations
            }

            st.download_button(
                label="다운로드 JSON",
                data=json.dumps(report_dict, indent=2, ensure_ascii=False),
                file_name=f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

    with col2:
        if st.button("HTML로 내보내기"):
            # Get metrics for HTML
            tcr_data = extract_report_value(report, 'accuracy_metrics.tcr', {})
            success_rate = tcr_data.get('success_rate', 0) if isinstance(tcr_data, dict) else 0
            tcr_value = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
            acc_data = extract_report_value(report, 'accuracy_metrics.accuracy_scores', {})
            accuracy = acc_data.get('overall_accuracy', 0) if isinstance(acc_data, dict) else 0
            latency_data = extract_report_value(report, 'efficiency_metrics.latency', {})
            avg_time = latency_data.get('mean', 0) if isinstance(latency_data, dict) else 0

            # Generate HTML
            html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Evaluator - 평가 리포트</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .container {{ background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }}
        h3 {{ color: #7f8c8d; margin-top: 20px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #ecf0f1; padding: 20px; border-radius: 8px; text-align: center; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #3498db; margin: 10px 0; }}
        .metric-label {{ color: #7f8c8d; font-size: 14px; text-transform: uppercase; }}
        .recommendation {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; border-radius: 4px; }}
        .recommendation.high {{ background: #f8d7da; border-left-color: #dc3545; }}
        .priority {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 10px; }}
        .priority.high {{ background: #dc3545; color: white; }}
        .priority.medium {{ background: #ffc107; color: #333; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #7f8c8d; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Agent Evaluator 평가 리포트</h1>
        <p><strong>생성 시간:</strong> {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}</p>
        <h2>📈 요약</h2>
        <div class="summary">
            <div class="metric-card"><div class="metric-label">총 Task 수</div><div class="metric-value">{report.total_tasks}</div></div>
            <div class="metric-card"><div class="metric-label">성공률</div><div class="metric-value">{success_rate:.1f}%</div></div>
            <div class="metric-card"><div class="metric-label">TCR</div><div class="metric-value">{tcr_value:.1f}%</div></div>
            <div class="metric-card"><div class="metric-label">정확도</div><div class="metric-value">{accuracy:.1f}%</div></div>
            <div class="metric-card"><div class="metric-label">평균 실행 시간</div><div class="metric-value">{avg_time:.2f}s</div></div>
        </div>
        <h2>💡 권장사항</h2>
"""
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    priority_class = rec['priority'].lower()
                    html_content += f"""        <div class="recommendation {priority_class}">
            <h3>{i}. {rec['area']} <span class="priority {priority_class}">{rec['priority']}</span></h3>
            <p><strong>문제:</strong> {rec['issue']}</p>
            <p><strong>조치:</strong> {rec['action']}</p>
        </div>
"""
            else:
                html_content += "        <p>✅ 모든 메트릭이 목표를 달성했습니다!</p>\n"

            html_content += """        <div class="footer">
            <p>🤖 Generated with <strong>Agent Evaluator</strong></p>
            <p>AI 에이전트 성능 평가 및 분석 도구</p>
        </div>
    </div>
</body>
</html>"""

            st.download_button(
                label="다운로드 HTML",
                data=html_content,
                file_name=f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html"
            )


def render_agent_analysis_tab(monitor: HybridPerformanceMonitor):
    """Tab 5: Agent Analysis - Agentic AI specific metrics"""

    st.header("🤖 Agent 분석")

    st.markdown("""
    Agentic AI 시스템의 특화된 성능 지표를 분석합니다.

    **도구(Tool) 사용 지표 (순서대로):**
    - **Tool Selection**: 올바른 도구 선택 정확도 - 무엇을 선택했는가
    - **Tool Efficiency**: 선택한 도구의 실행 효율성 - 얼마나 효율적으로 실행했는가

    **협업 & 워크플로우 지표:**
    - **Multi-Agent Coordination**: 에이전트 간 협업 품질 (CrewAI)
    - **Workflow Execution**: 체인/그래프 실행 성능 (LangChain/LangGraph)
    """)

    # Create subtabs for Agentic AI metrics (순서: Selection → Efficiency → Coordination → Workflow)
    subtab1, subtab2, subtab3, subtab4 = st.tabs([
        "🔧 Tool Selection",
        "⚡ Tool Efficiency",
        "🤝 Multi-Agent (CrewAI)",
        "🔀 Workflow (LangChain/LangGraph)"
    ])

    # Subtab 1: Tool Selection
    with subtab1:
        st.subheader("🔧 도구 선택 정확도")

        tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()

        if not tool_selection_stats:
            st.info("""
            📊 도구 선택 데이터가 없습니다.

            **Golden Dataset에 expected_tools를 정의하면 도구 선택 정확도를 측정할 수 있습니다:**

            ```python
            task = TaskResult(
                ...,
                expected_tools=["search", "calculator"],  # 예상 도구
                tool_calls=[...],  # 실제 호출된 도구
                ...
            )
            ```
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            avg_accuracy = tool_selection_stats.get('avg_accuracy', 0)
            avg_precision = tool_selection_stats.get('avg_precision', 0)
            avg_recall = tool_selection_stats.get('avg_recall', 0)
            avg_f1 = tool_selection_stats.get('avg_f1_score', 0)

            with col1:
                st.metric("평균 정확도 (F1)", f"{avg_accuracy:.1f}%",
                         delta=f"{avg_accuracy - 90:.1f}%" if avg_accuracy < 90 else None)
            with col2:
                st.metric("정밀도 (Precision)", f"{avg_precision:.1f}%")
            with col3:
                st.metric("재현율 (Recall)", f"{avg_recall:.1f}%")
            with col4:
                st.metric("F1 Score", f"{avg_f1:.1f}%")

            # Detailed metrics
            st.markdown("#### 상세 분석")

            col1, col2, col3 = st.columns(3)

            with col1:
                total_evals = tool_selection_stats.get('total_evaluations', 0)
                st.metric("평가된 Task 수", f"{total_evals}")

            with col2:
                true_positives = tool_selection_stats.get('total_true_positives', 0)
                st.metric("정확한 선택", f"{true_positives}")

            with col3:
                false_positives = tool_selection_stats.get('total_false_positives', 0)
                st.metric("불필요한 도구", f"{false_positives}")

            # Recommendations
            st.markdown("#### 개선 제안")

            if avg_accuracy < 90:
                st.error(f"""
                🔴 **도구 선택 정확도가 {avg_accuracy:.1f}%로 낮습니다** (목표: 90%)

                **개선 방안:**
                - Agent에게 사용 가능한 도구 목록과 설명을 명확히 제공
                - Few-shot 예시로 올바른 도구 선택 패턴 학습
                - 도구 선택 로직을 별도 단계로 분리하여 검증
                - Function calling 프롬프트 최적화
                """)
            elif avg_precision < avg_recall:
                st.warning(f"""
                🟡 **불필요한 도구 호출이 많습니다** (Precision: {avg_precision:.1f}%)

                **제안:** 도구 호출 전 필요성 검증 단계 추가
                """)
            elif avg_recall < avg_precision:
                st.warning(f"""
                🟡 **필요한 도구가 누락되고 있습니다** (Recall: {avg_recall:.1f}%)

                **제안:** Agent가 모든 도구 옵션을 고려하도록 프롬프트 개선
                """)
            else:
                st.success("""
                ✅ 도구 선택 정확도가 우수합니다!

                Agent가 올바른 도구를 효과적으로 선택하고 있습니다.
                """)

    # Subtab 2: Tool Efficiency
    with subtab2:
        st.subheader("⚡ 도구 실행 효율성")

        # Get tool efficiency stats
        tool_stats = monitor.tool_analyzer.get_efficiency_stats()

        if not tool_stats or tool_stats.get('total_calls', 0) == 0:
            st.info("""
            📊 도구 호출 데이터가 없습니다.

            Agent가 도구를 사용하는 경우, 여기에서 도구 효율성 지표를 확인할 수 있습니다.

            **Tool Efficiency는 선택된 도구의 실행 품질을 측정합니다:**
            - 성공률: 도구 호출이 성공적으로 완료되었는가
            - 효율성: 중복 호출과 실패를 최소화했는가
            - 실행 시간: 도구가 얼마나 빠르게 실행되었는가
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            total_calls = tool_stats.get('total_calls', 0)
            success_rate = tool_stats.get('success_rate', 0)
            efficiency_score = tool_stats.get('avg_efficiency_score', 0)
            redundancy_rate = tool_stats.get('redundancy_rate', 0)

            with col1:
                st.metric("총 도구 호출", f"{total_calls:,}")
            with col2:
                st.metric("성공률", f"{success_rate:.1f}%", delta=f"{success_rate - 95:.1f}%" if success_rate < 95 else None)
            with col3:
                st.metric("효율성 점수", f"{efficiency_score:.1f}%", delta=f"{efficiency_score - 80:.1f}%" if efficiency_score < 80 else None)
            with col4:
                st.metric("중복률", f"{redundancy_rate:.1f}%", delta=f"{10 - redundancy_rate:.1f}%" if redundancy_rate > 10 else None)

            # Additional metrics
            st.markdown("#### 상세 지표")

            col1, col2, col3 = st.columns(3)

            with col1:
                avg_calls = tool_stats.get('avg_calls_per_task', 0)
                st.metric("Task당 평균 호출", f"{avg_calls:.1f}")

            with col2:
                avg_duration = tool_stats.get('avg_duration', 0)
                st.metric("평균 실행 시간", f"{avg_duration:.3f}s")

            with col3:
                failure_rate = tool_stats.get('failure_rate', 0)
                st.metric("실패율", f"{failure_rate:.1f}%")

            # Per-tool breakdown
            st.markdown("#### 도구별 효율성 분석")

            # Get per-tool statistics
            if hasattr(monitor.tool_analyzer, 'executions') and monitor.tool_analyzer.executions:
                tool_breakdown = {}
                for execution in monitor.tool_analyzer.executions:
                    for call in execution.get('tool_calls', []):
                        tool_name = call.get('tool_name', 'Unknown')
                        if tool_name not in tool_breakdown:
                            tool_breakdown[tool_name] = {
                                'total': 0,
                                'success': 0,
                                'failed': 0,
                                'durations': []
                            }

                        tool_breakdown[tool_name]['total'] += 1
                        if call.get('success', False):
                            tool_breakdown[tool_name]['success'] += 1
                        else:
                            tool_breakdown[tool_name]['failed'] += 1

                        if 'duration' in call:
                            tool_breakdown[tool_name]['durations'].append(call['duration'])

                if tool_breakdown:
                    # Create DataFrame for per-tool stats
                    tool_data = []
                    for tool_name, stats in tool_breakdown.items():
                        success_rate_tool = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
                        avg_duration_tool = (sum(stats['durations']) / len(stats['durations'])) if stats['durations'] else 0
                        tool_data.append({
                            '도구명': tool_name,
                            '총 호출': stats['total'],
                            '성공': stats['success'],
                            '실패': stats['failed'],
                            '성공률': f"{success_rate_tool:.1f}%",
                            '평균 실행시간': f"{avg_duration_tool:.3f}s"
                        })

                    df_tools = pd.DataFrame(tool_data)
                    df_tools = df_tools.sort_values('총 호출', ascending=False)
                    st.dataframe(df_tools, width='stretch', hide_index=True)

                    # Visualization: Success rate by tool
                    st.markdown("#### 도구별 성공률 분포")
                    fig = px.bar(
                        df_tools,
                        x='도구명',
                        y=[col for col in df_tools.columns if col in ['성공', '실패']],
                        title='도구별 성공/실패 분포',
                        barmode='stack'
                    )
                    st.plotly_chart(fig, width="stretch")

            # Tool efficiency summary table
            st.markdown("#### 도구 효율성 요약")

            summary_data = {
                "지표": [
                    "총 도구 호출",
                    "성공한 호출",
                    "실패한 호출",
                    "중복 호출",
                    "Task당 평균 호출"
                ],
                "값": [
                    f"{total_calls:,}",
                    f"{int(total_calls * success_rate / 100):,}",
                    f"{tool_stats.get('total_failed_calls', 0):,}",
                    f"{tool_stats.get('total_redundant_calls', 0):,}",
                    f"{avg_calls:.2f}"
                ]
            }

            df_summary = pd.DataFrame(summary_data)
            st.dataframe(df_summary, width='stretch', hide_index=True)

            # Efficiency recommendations
            st.markdown("#### 최적화 제안")

            issues = []

            if success_rate < 95:
                issues.append({
                    "severity": "🔴 높음",
                    "issue": f"도구 성공률이 {success_rate:.1f}%로 낮습니다 (목표: 95%)",
                    "suggestion": "도구 파라미터 검증, 에러 핸들링 개선, 도구 설정 확인"
                })

            if efficiency_score < 80:
                issues.append({
                    "severity": "🟡 중간",
                    "issue": f"효율성 점수가 {efficiency_score:.1f}%로 낮습니다 (목표: 80%)",
                    "suggestion": "중복 호출 제거, 실패한 호출 원인 분석, 도구 선택 로직 개선"
                })

            if redundancy_rate > 10:
                issues.append({
                    "severity": "🟡 중간",
                    "issue": f"중복 호출률이 {redundancy_rate:.1f}%로 높습니다 (목표: <10%)",
                    "suggestion": "도구 호출 전 결과 캐싱, 동일 파라미터 호출 방지 로직 추가"
                })

            if avg_duration > 2.0:
                issues.append({
                    "severity": "🟢 낮음",
                    "issue": f"평균 실행 시간이 {avg_duration:.3f}초입니다 (목표: <2초)",
                    "suggestion": "비동기 호출 고려, 도구 최적화, 타임아웃 설정 조정"
                })

            if issues:
                for issue in issues:
                    with st.expander(f"{issue['severity']} - {issue['issue']}"):
                        st.write(f"**문제:** {issue['issue']}")
                        st.write(f"**제안:** {issue['suggestion']}")
            else:
                st.success("""
                ✅ 모든 도구 효율성 지표가 목표치를 달성했습니다!

                현재 도구 사용 패턴이 매우 효율적입니다.
                """)

    # Subtab 3: Multi-Agent Coordination (CrewAI)
    with subtab3:
        st.subheader("🤝 멀티 에이전트 협업 (CrewAI)")

        coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()

        if not coordination_stats or coordination_stats.get('total_interactions', 0) == 0:
            st.info("""
            📊 에이전트 협업 데이터가 없습니다.

            **CrewAI를 사용하는 경우, TaskResult에 agent_interactions를 기록하세요:**

            ```python
            task = TaskResult(
                ...,
                agent_interactions=[
                    {
                        "from_agent": "researcher",
                        "to_agent": "writer",
                        "type": "delegation",
                        "success": True,
                        "context": {...}
                    }
                ],
                framework="crewai",
                ...
            )
            ```
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            coord_score = coordination_stats.get('score', 0)
            success_rate = coordination_stats.get('success_rate', 0)
            total_interactions = coordination_stats.get('total_interactions', 0)
            unique_agents = coordination_stats.get('unique_agents', 0)

            with col1:
                st.metric("협업 점수", f"{coord_score:.1f}/10",
                         delta=f"{coord_score - 8:.1f}" if coord_score < 8 else None)
            with col2:
                st.metric("성공률", f"{success_rate:.1f}%")
            with col3:
                st.metric("총 상호작용", f"{total_interactions}")
            with col4:
                st.metric("참여 에이전트", f"{unique_agents}")

            # Interaction types
            st.markdown("#### 상호작용 유형 분포")

            interaction_types = coordination_stats.get('interaction_types', {})

            if interaction_types:
                df_types = pd.DataFrame([
                    {"유형": k, "횟수": v}
                    for k, v in interaction_types.items()
                ])

                fig = px.pie(df_types, names='유형', values='횟수', title='상호작용 유형 분포')
                st.plotly_chart(fig, width='stretch')

            # Delegation success rate
            delegation_rate = monitor.agent_coordination_tracker.get_delegation_success_rate()

            if delegation_rate > 0:
                st.markdown("#### 작업 위임 성공률")
                col1, col2 = st.columns([1, 3])

                with col1:
                    st.metric("위임 성공률", f"{delegation_rate:.1f}%")

                with col2:
                    if delegation_rate < 90:
                        st.warning("작업 위임 성공률을 높이기 위해 에이전트 역할 정의를 명확히 하세요.")
                    else:
                        st.success("작업 위임이 효과적으로 이루어지고 있습니다.")

            # Recommendations
            st.markdown("#### 개선 제안")

            if coord_score < 8:
                st.error(f"""
                🔴 **에이전트 협업 품질이 낮습니다** (점수: {coord_score:.1f}/10, 목표: 8.0)

                **개선 방안:**
                - 에이전트 간 역할과 책임을 명확히 정의
                - 효과적인 통신 프로토콜 수립
                - 작업 위임 규칙 최적화
                - 에이전트 간 정보 공유 메커니즘 강화
                """)
            elif success_rate < 90:
                st.warning(f"""
                🟡 **에이전트 간 상호작용 실패가 많습니다** (성공률: {success_rate:.1f}%)

                **제안:** 에러 핸들링 및 재시도 로직 개선
                """)
            else:
                st.success("""
                ✅ 멀티 에이전트 협업이 우수합니다!

                에이전트들이 효과적으로 협력하여 작업을 수행하고 있습니다.
                """)

    # Subtab 4: Workflow Execution (LangChain/LangGraph)
    with subtab4:
        st.subheader("🔀 워크플로우 실행 (LangChain/LangGraph)")

        workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()

        if not workflow_stats or workflow_stats.get('total_steps', 0) == 0:
            st.info("""
            📊 워크플로우 실행 데이터가 없습니다.

            **LangChain 또는 LangGraph를 사용하는 경우, TaskResult에 chain_steps를 기록하세요:**

            ```python
            task = TaskResult(
                ...,
                chain_steps=[
                    {
                        "name": "retrieval",
                        "type": "chain_step",
                        "success": True,
                        "execution_time": 0.5
                    },
                    {
                        "name": "generation",
                        "type": "chain_step",
                        "success": True,
                        "execution_time": 1.2
                    }
                ],
                framework="langchain",  # or "langgraph"
                ...
            )
            ```
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            step_success_rate = workflow_stats.get('step_success_rate', 0)
            task_success_rate = workflow_stats.get('task_success_rate', 0)
            total_steps = workflow_stats.get('total_steps', 0)
            avg_steps = workflow_stats.get('avg_steps_per_task', 0)

            with col1:
                st.metric("단계 성공률", f"{step_success_rate:.1f}%",
                         delta=f"{step_success_rate - 95:.1f}%" if step_success_rate < 95 else None)
            with col2:
                st.metric("Task 성공률", f"{task_success_rate:.1f}%",
                         delta=f"{task_success_rate - 92:.1f}%" if task_success_rate < 92 else None)
            with col3:
                st.metric("총 실행 단계", f"{total_steps}")
            with col4:
                st.metric("Task당 평균 단계", f"{avg_steps:.1f}")

            # Detailed breakdown
            st.markdown("#### 상세 분석")

            col1, col2, col3 = st.columns(3)

            with col1:
                successful_steps = workflow_stats.get('successful_steps', 0)
                st.metric("성공한 단계", f"{successful_steps}")

            with col2:
                failed_steps = workflow_stats.get('failed_steps', 0)
                st.metric("실패한 단계", f"{failed_steps}")

            with col3:
                fully_successful = workflow_stats.get('fully_successful_tasks', 0)
                total_tasks = workflow_stats.get('total_tasks', 0)
                st.metric("완전 성공 Task", f"{fully_successful}/{total_tasks}")

            # Framework-specific stats
            st.markdown("#### Framework별 통계")

            # LangChain
            langchain_stats = monitor.workflow_tracker.calculate_execution_success_rate(framework="langchain")
            # LangGraph
            langgraph_stats = monitor.workflow_tracker.calculate_execution_success_rate(framework="langgraph")

            if langchain_stats.get('total_steps', 0) > 0 or langgraph_stats.get('total_steps', 0) > 0:
                col1, col2 = st.columns(2)

                with col1:
                    if langchain_stats.get('total_steps', 0) > 0:
                        st.markdown("**LangChain**")
                        st.metric("단계 성공률", f"{langchain_stats['step_success_rate']:.1f}%")
                        st.metric("총 단계", f"{langchain_stats['total_steps']}")
                    else:
                        st.info("LangChain 데이터 없음")

                with col2:
                    if langgraph_stats.get('total_steps', 0) > 0:
                        st.markdown("**LangGraph**")
                        st.metric("단계 성공률", f"{langgraph_stats['step_success_rate']:.1f}%")
                        st.metric("총 단계", f"{langgraph_stats['total_steps']}")
                    else:
                        st.info("LangGraph 데이터 없음")

            # Recommendations
            st.markdown("#### 개선 제안")

            if step_success_rate < 95:
                st.error(f"""
                🔴 **워크플로우 단계 성공률이 낮습니다** ({step_success_rate:.1f}%, 목표: 95%)

                **개선 방안:**
                - 각 단계별 에러 핸들링 강화
                - 실패한 단계 로그 분석 및 원인 파악
                - 체인 구조 단순화 검토
                - 각 단계의 입출력 검증 추가
                """)
            elif task_success_rate < 92:
                st.warning(f"""
                🟡 **일부 단계 실패로 전체 Task 성공률이 낮습니다** ({task_success_rate:.1f}%)

                **제안:**
                - 중요하지 않은 단계는 선택적으로 만들기
                - 부분 실패 허용 정책 검토
                - 재시도 메커니즘 추가
                """)
            elif avg_steps > 10:
                st.info(f"""
                💡 **워크플로우가 복잡합니다** (평균 {avg_steps:.1f} 단계)

                **제안:**
                - 불필요한 단계 병합 검토
                - 워크플로우 최적화로 실행 시간 단축
                """)
            else:
                st.success("""
                ✅ 워크플로우 실행이 우수합니다!

                체인/그래프 기반 워크플로우가 안정적으로 실행되고 있습니다.
                """)


def render_transparency_tab(monitor: HybridPerformanceMonitor):
    """Tab 9: Test Transparency - Enhanced with actionable insights and analysis"""

    st.header("🔬 Test 투명성 & 인사이트")

    st.info("""
    **실효성 있는 평가 분석**: AI Agent 개발자와 품질 관리자를 위한 실행 가능한 인사이트를 제공합니다.

    - 🚨 이상치 탐지 및 경고
    - 🔗 메트릭 간 상관관계
    - 🎯 성능 병목 지점
    - 📊 데이터 품질 검증
    - 💡 실행 가능한 개선 방안
    """)

    # Import TestTransparencyManager
    from agent_evaluator.utils.test_transparency_manager import TestTransparencyManager

    # Create transparency manager
    transparency_mgr = TestTransparencyManager()

    # Create tabs for different analysis types
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🚨 이상치 탐지",
        "🔗 상관관계 분석",
        "🎯 성능 병목",
        "📊 데이터 품질",
        "💡 개선 방안",
        "📐 계산 방법"
    ])

    # Tab 1: Anomaly Detection
    with tab1:
        st.subheader("🚨 메트릭 이상치 탐지")
        st.markdown("메트릭 간 불일치, 예상치 못한 패턴, 잠재적 문제를 자동으로 탐지합니다.")

        try:
            anomaly_data = transparency_mgr.analyze_metric_anomalies(monitor)

            # Display anomalies
            if anomaly_data['anomalies']:
                st.error("### ⚠️ 감지된 이상치")
                for anomaly in anomaly_data['anomalies']:
                    severity_icon = "🔴" if anomaly['severity'] == 'high' else "🟡"
                    with st.expander(f"{severity_icon} {anomaly['title']}", expanded=True):
                        st.markdown(f"**설명**: {anomaly['description']}")
                        st.markdown(f"**권장 조치**: {anomaly['recommendation']}")
            else:
                st.success("✅ 이상치가 감지되지 않았습니다.")

            # Display warnings
            if anomaly_data['warnings']:
                st.warning("### ⚡ 경고")
                for warning in anomaly_data['warnings']:
                    severity_icon = "🔴" if warning['severity'] == 'high' else "🟡"
                    with st.expander(f"{severity_icon} {warning['title']}"):
                        st.markdown(f"**설명**: {warning['description']}")
                        st.markdown(f"**권장 조치**: {warning['recommendation']}")

            # Display positive insights
            if anomaly_data['insights']:
                st.success("### ✨ 긍정적 인사이트")
                for insight in anomaly_data['insights']:
                    with st.expander(f"🎉 {insight['title']}"):
                        st.markdown(f"**설명**: {insight['description']}")
                        st.markdown(f"**다음 단계**: {insight['action']}")

        except Exception as e:
            st.error(f"이상치 분석 중 오류 발생: {str(e)}")

    # Tab 2: Correlation Analysis
    with tab2:
        st.subheader("🔗 메트릭 간 상관관계 분석")
        st.markdown("메트릭 간 관계를 분석하여 성능 개선 포인트를 찾습니다.")

        try:
            correlation_data = transparency_mgr.analyze_metric_correlations(monitor)

            if correlation_data['correlations']:
                for corr in correlation_data['correlations']:
                    with st.expander(f"📊 {corr['title']}", expanded=True):
                        col1, col2 = st.columns([2, 3])

                        with col1:
                            st.markdown("**관계**")
                            st.info(corr['relationship'])

                        with col2:
                            st.markdown("**인사이트**")
                            st.markdown(corr['insight'])

                        st.markdown("**권장 조치**")
                        st.success(corr['recommendation'])
            else:
                st.info("분석 가능한 메트릭 데이터가 충분하지 않습니다.")

        except Exception as e:
            st.error(f"상관관계 분석 중 오류 발생: {str(e)}")

    # Tab 3: Performance Bottlenecks
    with tab3:
        st.subheader("🎯 성능 병목 지점 식별")
        st.markdown("시스템의 성능 저하 원인을 자동으로 식별하고 해결 방안을 제시합니다.")

        try:
            bottleneck_data = transparency_mgr.identify_performance_bottlenecks(monitor)

            if bottleneck_data['bottlenecks']:
                for bottleneck in bottleneck_data['bottlenecks']:
                    severity_color = "🔴" if bottleneck['severity'] == 'high' else "🟡"

                    with st.expander(f"{severity_color} {bottleneck['title']}", expanded=True):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**문제점**")
                            st.warning(bottleneck['description'])

                        with col2:
                            st.markdown("**영향**")
                            st.error(bottleneck['impact'])

                        st.markdown("**해결 방안**")
                        st.success(bottleneck['recommendation'])
            else:
                st.success("✅ 병목 지점이 발견되지 않았습니다. 성능이 양호합니다.")

        except Exception as e:
            st.error(f"병목 분석 중 오류 발생: {str(e)}")

    # Tab 4: Data Quality
    with tab4:
        st.subheader("📊 데이터 품질 검증")
        st.markdown("평가 데이터의 완전성과 신뢰성을 검증합니다.")

        try:
            quality_report = transparency_mgr.generate_data_quality_report(monitor)

            # Overall score
            score = quality_report['overall_score']
            col1, col2, col3 = st.columns([1, 2, 1])

            with col2:
                # Color-coded score display
                if score >= 90:
                    st.success(f"### 데이터 품질 점수: {score:.1f}/100 ✅")
                elif score >= 70:
                    st.warning(f"### 데이터 품질 점수: {score:.1f}/100 ⚠️")
                else:
                    st.error(f"### 데이터 품질 점수: {score:.1f}/100 ❌")

            # Progress bar
            st.progress(score / 100)

            # Data completeness metrics
            st.markdown("### 📈 데이터 완전성")
            completeness = quality_report['data_completeness']

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("전체 작업 수", completeness['total_tasks'])

            with col2:
                st.metric("점수 있는 작업", completeness['tasks_with_scores'])

            with col3:
                st.metric("품질 평가된 작업", completeness['quality_evaluated'])

            # Quality issues
            if quality_report['quality_issues']:
                st.markdown("### 🔍 발견된 품질 이슈")
                for issue in quality_report['quality_issues']:
                    severity_map = {
                        'critical': ('🔴', 'error'),
                        'high': ('🔴', 'error'),
                        'medium': ('🟡', 'warning'),
                        'low': ('🟢', 'info')
                    }
                    icon, level = severity_map.get(issue['severity'], ('⚪', 'info'))

                    with st.expander(f"{icon} {issue['type'].replace('_', ' ').title()}"):
                        st.markdown(f"**설명**: {issue['description']}")
                        st.markdown(f"**권장 조치**: {issue['recommendation']}")
            else:
                st.success("✅ 데이터 품질 이슈가 없습니다.")

        except Exception as e:
            st.error(f"데이터 품질 검증 중 오류 발생: {str(e)}")

    # Tab 5: Actionable Insights
    with tab5:
        st.subheader("💡 실행 가능한 개선 방안")
        st.markdown("현재 메트릭을 기반으로 구체적이고 실행 가능한 개선 방안을 제시합니다.")

        try:
            insights = transparency_mgr.generate_actionable_insights(monitor)

            if insights:
                # Sort by priority
                priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
                insights.sort(key=lambda x: priority_order.get(x['priority'], 999))

                for insight in insights:
                    # Priority badge
                    priority_badge = {
                        'critical': '🔴 긴급',
                        'high': '🟠 높음',
                        'medium': '🟡 중간',
                        'low': '🟢 낮음'
                    }
                    badge = priority_badge.get(insight['priority'], '⚪ 기타')

                    # Category emoji
                    category_emoji = {
                        'cost': '💰',
                        'performance': '⚡',
                        'accuracy': '🎯',
                        'reliability': '🛡️',
                        'quality': '✨'
                    }
                    emoji = category_emoji.get(insight['category'], '📌')

                    with st.expander(f"{badge} {emoji} {insight['title']}", expanded=True):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**현재 상태**")
                            st.info(insight['current_state'])

                            st.markdown("**권장 조치**")
                            st.success(insight['action'])

                        with col2:
                            st.markdown("**예상 효과**")
                            st.warning(insight['expected_impact'])

                        st.markdown("**구현 단계**")
                        for step in insight['implementation']:
                            st.markdown(f"- {step}")

                        st.markdown("---")
            else:
                st.success("✅ 현재 성능이 모든 목표를 달성하고 있습니다. 개선 방안이 필요하지 않습니다.")

        except Exception as e:
            st.error(f"인사이트 생성 중 오류 발생: {str(e)}")

    # Tab 6: Calculation Methods (Original content, simplified)
    with tab6:
        st.subheader("📐 메트릭 계산 방법")
        st.markdown("각 메트릭이 어떻게 계산되는지 확인합니다.")

        with st.expander("TCR (Task Completion Rate)"):
            st.code("""
TCR = (완료 점수의 합) / (전체 Task 수) × 100

완료 점수 = task.completion_score (0.0 ~ 1.0)

- 각 Task의 completion_score를 평균
- 100% 완료 시 1.0, 부분 완료 시 0.0~1.0
- 목표: ≥95%
            """, language="python")

        with st.expander("Accuracy (정확도)"):
            st.code("""
Accuracy = (정확도 점수의 합) / (전체 Task 수) × 100

정확도 점수 = task.accuracy_score (0.0 ~ 1.0)

- 각 Task의 accuracy_score를 평균
- 완전 정확 시 1.0, 완전 부정확 시 0.0
- 목표: ≥85%
            """, language="python")

        with st.expander("Hallucination Rate (환각률)"):
            st.code("""
Hallucination Rate = (환각 탐지 건수) / (검사된 응답 수) × 100

탐지 방법:
- 키워드 기반 환각 탐지
- 의심스러운 표현 패턴 검사 ("아마도", "확실하지 않지만" 등)
- 목표: <5%
            """, language="python")

        with st.expander("Quality Score (품질 점수)"):
            st.code("""
Quality = (총 품질 점수) / (전체 Task 수)

품질 차원 (5가지):
- Relevance (관련성): 25%
- Completeness (완전성): 25%
- Accuracy (정확성): 20%
- Clarity (명확성): 15%
- Usefulness (유용성): 15%

총 점수 범위: 0~5.0
목표: ≥4.0
            """, language="python")

        with st.expander("Latency (지연시간)"):
            st.code("""
Latency = task.execution_time (초)

통계:
- Mean (평균)
- Median (중앙값)
- P95 (95 백분위수)
- Max (최대값)

목표: <3초 (평균)
            """, language="python")

        # System info at the bottom
        st.markdown("---")
        st.subheader("🌍 평가 환경")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Python 버전", os.sys.version.split()[0])

        with col2:
            st.metric("총 Task 수", len(monitor.tcr_tracker.tasks))

        with col3:
            st.metric("실행 시간", datetime.now().strftime('%H:%M:%S'))


# ============================================================================
# NEW TAB STRUCTURE (7-Tab): Wrapper Functions
# ============================================================================

def render_core_metrics_tab(monitor: HybridPerformanceMonitor):
    """Tab 2: Core Metrics - TCR, Accuracy, Quality, Hallucination"""
    # Reuse existing accuracy_quality_tab with adjusted header
    st.header("🎯 핵심 지표 (Core Metrics)")
    st.markdown("""
    **작업 완료도 및 정확성을 측정하는 핵심 지표** (What was achieved)

    - **Task Completion**: 작업 완료율 (TCR) - 작업의 성공 여부
    - **Accuracy**: 정확도 - 예상 결과와의 일치도
    - **Quality**: 응답 품질 - 5가지 차원의 품질 평가
    - **Hallucination**: 환각 탐지율 - 사실 왜곡 발생률

    💡 성능 효율성 지표(속도, 비용, 도구 효율, 재시도)는 ⚡ Performance 탭에서 확인하세요.
    """)

    # Get all metrics
    tcr_metrics = monitor.tcr_tracker.calculate_tcr()
    accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
    quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    hallucination_data = monitor.hallucination_detector.get_hallucination_rate()
    retry_stats = monitor.retry_tracker.get_retry_metrics()

    # Create 4 subtabs (reduced from 8)
    subtab1, subtab2, subtab3, subtab4 = st.tabs([
        "📋 Task Completion",
        "✅ Accuracy",
        "🎨 Quality",
        "🚫 Hallucination"
    ])

    # Subtab 1: Task Completion (TCR only - Retry moved to Performance tab)
    with subtab1:
        st.subheader("📋 작업 완료율 (Task Completion Rate)")

        col1, col2, col3, col4, col5 = st.columns(5)

        overall_tcr = tcr_metrics.get('tcr', 0)
        full_success = tcr_metrics.get('full_success', 0)
        partial_success = tcr_metrics.get('partial_success', 0)
        failures = tcr_metrics.get('failures', 0)
        total_tasks = tcr_metrics.get('total_tasks', 0)

        with col1:
            st.metric("전체 TCR", f"{overall_tcr:.1f}%", help="Task Completion Rate: 모든 작업의 Completion Score 평균")
        with col2:
            st.metric("완전 성공", f"{full_success}", help="Completion Score = 100%")
        with col3:
            st.metric("부분 성공", f"{partial_success}", help="70% ≤ Completion Score < 100%")
        with col4:
            st.metric("실패", f"{failures}", help="Completion Score < 70%")
        with col5:
            benchmark = monitor.tcr_tracker.get_benchmark_status(overall_tcr)
            st.metric("벤치마크 등급", benchmark, help="TCR 기반 성능 등급")

        # Task completion breakdown
        st.markdown("---")
        completed_tasks = full_success + partial_success
        completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Calculate sum of completion scores for accurate display
        tasks_data = monitor.tcr_tracker.tasks
        weighted_sum = sum(t.completion_score for t in tasks_data)

        st.markdown(f"""
        **작업 완료 현황**: {completed_tasks}/{total_tasks} 작업 완료 ({completion_percentage:.1f}%)
        - ✅ **완전 성공**: {full_success}개 (Completion Score = 100%)
        - ⚠️ **부분 성공**: {partial_success}개 (70% ≤ Completion Score < 100%)
        - ❌ **실패**: {failures}개 (Completion Score < 70%)

        💡 **TCR 계산**: (모든 작업의 Completion Score 합) / 전체 작업 × 100 = {weighted_sum:.2f} / {total_tasks} × 100 = **{overall_tcr:.1f}%**
        """)

        # TCR by task type
        st.markdown("#### TaskType별 완료율")
        tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()

        if tcr_by_type:
            df_tcr = pd.DataFrame([
                {
                    'TaskType': task_type,
                    'TCR (%)': data.get('tcr', 0),
                    '완전 성공': data.get('full_success', 0),
                    '부분 성공': data.get('partial_success', 0),
                    '실패': data.get('failures', 0),
                    '전체': data.get('total_tasks', 0)
                }
                for task_type, data in tcr_by_type.items()
            ])

            fig = px.bar(
                df_tcr,
                x='TaskType',
                y='TCR (%)',
                title='TaskType별 작업 완료율',
                color='TCR (%)',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width='stretch')

            st.dataframe(df_tcr, width='stretch')

    # Subtab 2: Accuracy
    with subtab2:
        st.subheader("✅ 정확도 (Accuracy)")

        col1, col2, col3, col4 = st.columns(4)

        overall_acc = accuracy_metrics.get('overall_accuracy', 0)
        median_acc = accuracy_metrics.get('median_accuracy', 0)

        # Calculate high/low accuracy counts from tasks
        tasks_data = monitor.accuracy_evaluator.evaluations
        high_acc_count = sum(1 for t in tasks_data if t.get('accuracy', 0) >= 0.9)
        low_acc_count = sum(1 for t in tasks_data if t.get('accuracy', 0) < 0.7)

        with col1:
            st.metric("전체 정확도", f"{overall_acc:.1f}%", help="모든 작업의 정확도 평균")
        with col2:
            st.metric("높은 정확도 (≥90%)", f"{high_acc_count}", help="정확도가 90% 이상인 작업 수")
        with col3:
            st.metric("낮은 정확도 (<70%)", f"{low_acc_count}", help="정확도가 70% 미만인 작업 수")
        with col4:
            st.metric("중앙값", f"{median_acc:.1f}%", help="정확도의 중앙값")

        # Accuracy by task type
        st.markdown("#### TaskType별 정확도")
        acc_by_type = monitor.accuracy_evaluator.get_accuracy_by_type()

        if acc_by_type:
            df_acc = pd.DataFrame([
                {
                    'TaskType': task_type,
                    'Accuracy (%)': acc  # get_accuracy_by_type() already returns percentage
                }
                for task_type, acc in acc_by_type.items()
            ])

            fig = px.bar(
                df_acc,
                x='TaskType',
                y='Accuracy (%)',
                title='TaskType별 정확도',
                color='Accuracy (%)',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, width='stretch')

            st.dataframe(df_acc, width='stretch')

    # Subtab 3: Quality
    with subtab3:
        st.subheader("🎨 응답 품질 (Quality)")

        if not quality_metrics or quality_metrics.get('total_evaluated', 0) == 0:
            st.info("품질 평가 데이터가 없습니다.")
        else:
            col1, col2, col3, col4 = st.columns(4)

            # Convert 5-point scale to 10-point scale (matching agent_evaluator.py:1560)
            avg_score = quality_metrics.get('avg_total_score', 0) * 2
            median_score = quality_metrics.get('median_total_score', 0) * 2
            high_quality = quality_metrics.get('high_quality_count', 0)
            total_eval = quality_metrics.get('total_evaluated', 0)

            with col1:
                st.metric("평균 품질 점수", f"{avg_score:.2f}/10", help="5점 척도를 10점 척도로 변환 (×2)")
            with col2:
                st.metric("중앙값", f"{median_score:.2f}/10", help="품질 점수의 중앙값")
            with col3:
                st.metric("고품질 응답", f"{high_quality}", help="등급 A 또는 B인 응답 수")
            with col4:
                st.metric("평가된 응답", f"{total_eval}", help="품질 평가가 수행된 응답 수")

            # Quality distribution
            st.markdown("#### 품질 점수 분포")
            quality_dist = quality_metrics.get('quality_distribution', {})

            if quality_dist:
                df_quality = pd.DataFrame([
                    {'범위': k, '개수': v}
                    for k, v in quality_dist.items()
                ])

                fig = px.bar(df_quality, x='범위', y='개수', title='품질 점수 분포')
                st.plotly_chart(fig, width='stretch')

            # Dimension scores
            st.markdown("#### 차원별 평균 점수 (5점 척도)")
            dimension_scores = quality_metrics.get('dimension_scores', {})

            if dimension_scores:
                # Convert to 10-point scale for consistency
                df_dim = pd.DataFrame([
                    {'차원': k, '점수 (10점)': v * 2}
                    for k, v in dimension_scores.items()
                ])

                fig = px.bar(df_dim, x='차원', y='점수 (10점)', title='차원별 평균 점수 (10점 척도)')
                fig.add_hline(y=7.0, line_dash="dash", line_color="red", annotation_text="목표: 7.0/10")
                st.plotly_chart(fig, width='stretch')

                # Show original 5-point scores in table
                st.markdown("**원본 점수 (5점 척도)**:")
                df_dim_original = pd.DataFrame([
                    {'차원': k, '점수 (5점)': v}
                    for k, v in dimension_scores.items()
                ])
                st.dataframe(df_dim_original, width='stretch')

    # Subtab 4: Hallucination
    with subtab4:
        st.subheader("🚫 환각 탐지 (Hallucination)")

        if not hallucination_data or hallucination_data.get('total_evaluated', 0) == 0:
            st.info("환각 탐지 데이터가 없습니다.")
        else:
            col1, col2, col3, col4 = st.columns(4)

            overall_rate = hallucination_data.get('overall_rate', 0)
            flagged = hallucination_data.get('total_flagged', 0)
            total_checked = hallucination_data.get('total_evaluated', 0)

            with col1:
                st.metric("전체 환각률", f"{overall_rate:.1f}%")
            with col2:
                st.metric("탐지된 환각", f"{flagged}")
            with col3:
                st.metric("검사된 응답", f"{total_checked}")
            with col4:
                if overall_rate < 5:
                    st.metric("상태", "✅ 안전")
                elif overall_rate < 10:
                    st.metric("상태", "⚠️ 주의")
                else:
                    st.metric("상태", "❌ 위험")

            # Hallucination types
            st.markdown("#### 환각 유형 분석")
            unsupported = hallucination_data.get('unsupported_claims_count', 0)
            numerical = hallucination_data.get('numerical_inconsistencies_count', 0)

            if unsupported > 0 or numerical > 0:
                df_types = pd.DataFrame([
                    {'유형': '지원되지 않는 주장', '횟수': unsupported},
                    {'유형': '숫자 불일치', '횟수': numerical}
                ])

                fig = px.pie(df_types, names='유형', values='횟수', title='환각 유형 분포')
                st.plotly_chart(fig, width='stretch')


def render_performance_tab(monitor: HybridPerformanceMonitor):
    """Tab 3: Performance - Latency, Cost, Tokens, Retry Success (Tool Efficiency moved to Agentic AI)"""

    st.header("⚡ 성능 지표 (Performance)")
    st.markdown("""
    **실행 효율성 및 리소스 사용을 측정하는 성능 지표** (How efficiently it was achieved)

    Layer 1 Performance Metrics:
    - **Latency**: 응답 시간 및 병목 지점 - 얼마나 빠른가
    - **Cost & Tokens**: 비용 및 토큰 사용량 - 얼마나 경제적인가
    - **Retry Success**: 재시도 메커니즘 효율성 - 실패 복구가 얼마나 효과적인가

    💡 작업 완료 및 정확성 지표는 🎯 Core Metrics 탭에서 확인하세요.

    💡 도구 효율성(Tool Efficiency) 지표는 🤖 Agentic AI 탭에서 확인하세요.
    """)

    efficiency_stats = get_efficiency_stats(monitor)
    latency_stats = monitor.latency_tracker.get_latency_stats()
    usage_stats = monitor.token_tracker.get_usage_stats()

    # Create 3 subtabs (Tool Efficiency moved to Agentic AI tab)
    subtab1, subtab2, subtab3 = st.tabs([
        "⏱️ Latency",
        "💰 Cost & Tokens",
        "🔄 Retry Success"
    ])

    # Subtab 1: Latency
    with subtab1:
        st.subheader("⏱️ 응답 시간 분석")

        col1, col2, col3, col4 = st.columns(4)

        avg_latency = latency_stats.get('mean', 0)
        p50_latency = latency_stats.get('p50', 0)
        p95_latency = latency_stats.get('p95', 0)
        max_latency = latency_stats.get('max', 0)

        with col1:
            st.metric("평균 응답 시간", f"{avg_latency:.2f}s")
        with col2:
            st.metric("P50 (중앙값)", f"{p50_latency:.2f}s")
        with col3:
            st.metric("P95", f"{p95_latency:.2f}s")
        with col4:
            st.metric("최대", f"{max_latency:.2f}s")

        # Latency by task type
        st.markdown("#### TaskType별 응답 시간")

        if monitor.tcr_tracker.tasks:
            task_data = []
            for task in monitor.tcr_tracker.tasks:
                task_data.append({
                    'TaskType': task.task_type,
                    'Execution Time (s)': task.execution_time
                })

            df_latency = pd.DataFrame(task_data)

            fig = px.box(
                df_latency,
                x='TaskType',
                y='Execution Time (s)',
                title='TaskType별 응답 시간 분포',
                points='all'
            )
            st.plotly_chart(fig, width='stretch')

            latency_by_type_df = df_latency.groupby('TaskType')['Execution Time (s)'].agg([
                ('평균', 'mean'),
                ('중앙값', 'median'),
                ('최소', 'min'),
                ('최대', 'max')
            ]).reset_index()

            st.dataframe(latency_by_type_df, width='stretch')

    # Subtab 2: Cost & Tokens
    with subtab2:
        st.subheader("💰 비용 & 토큰 분석")

        col1, col2, col3, col4 = st.columns(4)

        total_cost = efficiency_stats.get('total_cost', 0)
        cost_per_task = efficiency_stats.get('cost_per_task', 0)
        total_tokens = usage_stats.get('total_tokens', 0)
        avg_tokens = usage_stats.get('avg_tokens_per_task', 0)  # Fixed: average_tokens_per_task → avg_tokens_per_task

        with col1:
            st.metric("총 비용", f"${total_cost:.4f}")
        with col2:
            st.metric("Task당 비용", f"${cost_per_task:.4f}")
        with col3:
            st.metric("총 토큰 사용", f"{total_tokens:,}")
        with col4:
            st.metric("Task당 평균 토큰", f"{avg_tokens:.0f}")

        # Token usage breakdown
        st.markdown("#### 토큰 사용 상세")

        col1, col2, col3 = st.columns(3)

        with col1:
            input_tokens = usage_stats.get('total_input_tokens', 0)
            st.metric("Input 토큰", f"{input_tokens:,}")

        with col2:
            output_tokens = usage_stats.get('total_output_tokens', 0)
            st.metric("Output 토큰", f"{output_tokens:,}")

        with col3:
            if total_tokens > 0:
                input_ratio = (input_tokens / total_tokens) * 100
                st.metric("Input 비율", f"{input_ratio:.1f}%")

        # Cost optimization tips
        st.markdown("#### 비용 최적화 제안")

        if cost_per_task > 0.05:
            st.warning(f"""
            ⚠️ Task당 평균 비용이 ${cost_per_task:.4f}로 높습니다.

            **최적화 방안:**
            - 프롬프트 길이 최적화
            - 불필요한 컨텍스트 제거
            - 더 작은 모델 사용 검토
            - 캐싱 활용
            """)
        elif cost_per_task > 0.02:
            st.info(f"""
            💡 Task당 비용: ${cost_per_task:.4f}

            적정 수준이지만 추가 최적화 가능합니다.
            """)
        else:
            st.success(f"""
            ✅ Task당 비용: ${cost_per_task:.4f}

            매우 효율적인 비용 수준입니다!
            """)

    # Subtab 3: Retry Success Rate
    with subtab3:
        st.subheader("🔄 재시도 성공률 분석")

        # Get retry metrics
        retry_stats = monitor.retry_tracker.get_retry_metrics()

        if not retry_stats or retry_stats.get('total_tasks_with_retries', 0) == 0:
            st.info("""
            📊 재시도 데이터가 없습니다.

            Task 실패 시 재시도 메커니즘이 활성화되면, 여기에서 재시도 효율성 지표를 확인할 수 있습니다.
            """)
        else:
            # Key metrics
            col1, col2, col3, col4 = st.columns(4)

            total_with_retries = retry_stats.get('total_tasks_with_retries', 0)
            retry_rate = retry_stats.get('retry_rate', 0)
            eventual_success = retry_stats.get('eventual_success_rate', 0)
            correction_rate = retry_stats.get('correction_success_rate', 0)

            with col1:
                st.metric("재시도한 Task", f"{total_with_retries:,}")
            with col2:
                st.metric("재시도율", f"{retry_rate:.1f}%")
            with col3:
                st.metric("최종 성공률", f"{eventual_success:.1f}%", delta=f"{eventual_success - 80:.1f}%" if eventual_success < 80 else None)
            with col4:
                st.metric("수정 성공률", f"{correction_rate:.1f}%")

            # Additional metrics
            st.markdown("#### 상세 지표")

            col1, col2, col3 = st.columns(3)

            with col1:
                avg_attempts = retry_stats.get('avg_attempts_per_task', 0)
                st.metric("평균 시도 횟수", f"{avg_attempts:.2f}")

            with col2:
                retry_success_count = retry_stats.get('retry_success_count', 0)
                st.metric("재시도 후 성공", f"{retry_success_count:,}개")

            with col3:
                first_attempt_success = retry_stats.get('first_attempt_success_rate', 0)
                st.metric("1차 시도 성공률", f"{first_attempt_success:.1f}%")

            # Retry attempt distribution
            st.markdown("#### 재시도 횟수 분포")

            # Get retry attempts data
            if hasattr(monitor.retry_tracker, 'attempts') and monitor.retry_tracker.attempts:
                attempts_distribution = {}
                retry_reasons = {}
                total_retry_duration = 0
                retry_count = 0

                for attempt_log in monitor.retry_tracker.attempts:
                    task_id = attempt_log.get('task_id')

                    # Use total_attempts from the analysis (not attempts_log)
                    num_attempts = attempt_log.get('total_attempts', 1)
                    attempts_distribution[num_attempts] = attempts_distribution.get(num_attempts, 0) + 1

                    # Collect retry reasons from the pre-computed list
                    for reason in attempt_log.get('retry_reasons', []):
                        if reason and reason != 'unknown':
                            retry_reasons[reason] = retry_reasons.get(reason, 0) + 1
                            retry_count += 1

                    # Add retry time
                    total_retry_duration += attempt_log.get('total_retry_time', 0)

                if attempts_distribution:
                    # Create DataFrame for attempts distribution
                    dist_data = []
                    for num_attempts, count in sorted(attempts_distribution.items()):
                        dist_data.append({
                            '시도 횟수': f"{num_attempts}회",
                            'Task 수': count
                        })

                    df_dist = pd.DataFrame(dist_data)

                    col1, col2 = st.columns(2)

                    with col1:
                        st.dataframe(df_dist, width='stretch', hide_index=True)

                    with col2:
                        fig = px.pie(
                            df_dist,
                            names='시도 횟수',
                            values='Task 수',
                            title='재시도 횟수별 Task 분포'
                        )
                        st.plotly_chart(fig, width="stretch")

                # Retry reasons breakdown
                if retry_reasons:
                    st.markdown("#### 재시도 원인 분석")

                    reason_data = []
                    for reason, count in retry_reasons.items():
                        reason_display = {
                            'validation_failed': '검증 실패',
                            'timeout': '타임아웃',
                            'error': '에러 발생',
                            'quality_issue': '품질 문제',
                            'unknown': '알 수 없음'
                        }.get(reason, reason)

                        reason_data.append({
                            '재시도 원인': reason_display,
                            '발생 횟수': count,
                            '비율': f"{count / retry_count * 100:.1f}%"
                        })

                    df_reasons = pd.DataFrame(reason_data)
                    df_reasons = df_reasons.sort_values('발생 횟수', ascending=False)

                    col1, col2 = st.columns(2)

                    with col1:
                        st.dataframe(df_reasons, width='stretch', hide_index=True)

                    with col2:
                        fig = px.bar(
                            df_reasons,
                            x='재시도 원인',
                            y='발생 횟수',
                            title='재시도 원인별 발생 빈도'
                        )
                        st.plotly_chart(fig, width="stretch")

                # Retry time cost analysis
                if retry_count > 0:
                    st.markdown("#### 재시도 시간 비용")

                    avg_retry_duration = total_retry_duration / retry_count
                    total_retry_time = total_retry_duration

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("총 재시도 시간", f"{total_retry_time:.2f}s")
                    with col2:
                        st.metric("재시도당 평균 시간", f"{avg_retry_duration:.3f}s")
                    with col3:
                        # Calculate time overhead percentage
                        total_task_time = sum([task.execution_time for task in monitor.tcr_tracker.tasks])
                        if total_task_time > 0:
                            time_overhead = (total_retry_time / total_task_time) * 100
                            st.metric("시간 오버헤드", f"{time_overhead:.1f}%")

            # Comparison: First attempt vs Eventual success
            st.markdown("#### 1차 시도 vs 최종 성공 비교")

            comparison_data = {
                '구분': ['1차 시도 성공률', '재시도 후 최종 성공률'],
                '성공률': [first_attempt_success, eventual_success]
            }
            df_comparison = pd.DataFrame(comparison_data)

            fig = px.bar(
                df_comparison,
                x='구분',
                y='성공률',
                title='재시도의 효과',
                text='성공률'
            )
            fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig.update_yaxes(range=[0, 100])
            st.plotly_chart(fig, width="stretch")

            improvement = eventual_success - first_attempt_success
            if improvement > 0:
                st.info(f"""
                ✅ 재시도 메커니즘이 성공률을 **{improvement:.1f}%p** 향상시켰습니다.

                재시도를 통해 **{retry_success_count}개**의 Task가 추가로 성공했습니다.
                """)

            # Retry optimization recommendations
            st.markdown("#### 최적화 제안")

            retry_issues = []

            if eventual_success < 80:
                retry_issues.append({
                    "severity": "🔴 높음",
                    "issue": f"재시도 후에도 최종 성공률이 {eventual_success:.1f}%로 낮습니다 (목표: 80%)",
                    "suggestion": "재시도 로직 개선, 실패 원인 근본 분석, 더 나은 에러 복구 전략 필요"
                })

            if retry_rate > 30:
                retry_issues.append({
                    "severity": "🟡 중간",
                    "issue": f"재시도율이 {retry_rate:.1f}%로 높습니다 (목표: <30%)",
                    "suggestion": "1차 시도 성공률 향상, 입력 검증 강화, 프롬프트 품질 개선"
                })

            if avg_attempts > 3:
                retry_issues.append({
                    "severity": "🟡 중간",
                    "issue": f"평균 시도 횟수가 {avg_attempts:.2f}회로 많습니다 (목표: <3회)",
                    "suggestion": "재시도 한계 설정 검토, 빠른 실패(fail-fast) 전략 고려"
                })

            if correction_rate < 70:
                retry_issues.append({
                    "severity": "🟢 낮음",
                    "issue": f"수정 성공률이 {correction_rate:.1f}%입니다 (목표: >70%)",
                    "suggestion": "재시도 시 피드백 활용 개선, 에러 메시지 명확화"
                })

            if retry_issues:
                for issue in retry_issues:
                    with st.expander(f"{issue['severity']} - {issue['issue']}"):
                        st.write(f"**문제:** {issue['issue']}")
                        st.write(f"**제안:** {issue['suggestion']}")
            else:
                st.success("""
                ✅ 재시도 메커니즘이 효율적으로 작동하고 있습니다!

                적절한 재시도율과 높은 최종 성공률을 유지하고 있습니다.
                """)


def render_insights_tab(monitor: HybridPerformanceMonitor):
    """Tab 6: Insights - Alerts, Recommendations, Task Explorer"""

    st.header("💡 인사이트 & 분석")
    st.markdown("""
    평가 결과를 바탕으로 실행 가능한 인사이트를 제공합니다.
    - **Alerts**: 임계값 기반 경고 및 알림
    - **Recommendations**: AI 기반 개선 제안
    - **Task Explorer**: 개별 Task 상세 분석
    """)

    # Create 3 subtabs
    subtab1, subtab2, subtab3 = st.tabs([
        "🚨 Alerts",
        "💡 Recommendations",
        "📈 Task Explorer"
    ])

    # Subtab 1: Alerts (from render_alerts_tab)
    with subtab1:
        st.subheader("🚨 알림 및 경고")

        report = monitor.generate_hybrid_report()

        # Security Alerts Section
        from utils.dashboard_utils import (
            has_security_metrics,
            get_layer1_security_metrics,
            get_layer2_security_metrics
        )

        if has_security_metrics(monitor):
            st.markdown("### 🔒 보안 알림")

            security_alerts = [a for a in report.alerts if any(keyword in str(a).lower()
                for keyword in ['security', 'authorization', 'escalation', 'attack', 'leakage', 'threat', 'violation'])]

            if security_alerts:
                st.warning(f"⚠️ {len(security_alerts)}개의 보안 알림이 있습니다.")

                for alert in security_alerts[:5]:  # Show top 5 security alerts
                    severity = alert.get('severity', 'medium')
                    if severity == 'critical':
                        st.error(f"🔴 **{alert.get('metric', 'Security')}**: {alert.get('message', '')}")
                    elif severity == 'high':
                        st.warning(f"🟡 **{alert.get('metric', 'Security')}**: {alert.get('message', '')}")
                    else:
                        st.info(f"ℹ️ **{alert.get('metric', 'Security')}**: {alert.get('message', '')}")

                if len(security_alerts) > 5:
                    with st.expander(f"추가 보안 알림 ({len(security_alerts) - 5}개)"):
                        for alert in security_alerts[5:]:
                            st.write(f"• **{alert.get('metric', 'Security')}**: {alert.get('message', '')}")
            else:
                st.success("✅ 보안 관련 알림이 없습니다.")

            st.markdown("---")

        if not report.alerts:
            st.success("""
            ✅ 모든 지표가 정상 범위 내에 있습니다!

            현재 설정된 임계값을 기준으로 특별한 경고 사항이 없습니다.
            """)
        else:
            st.warning(f"⚠️ 총 {len(report.alerts)}개의 알림이 있습니다.")

            # Group alerts by severity
            critical_alerts = [a for a in report.alerts if a.get('severity') == 'critical']
            high_alerts = [a for a in report.alerts if a.get('severity') == 'high']
            medium_alerts = [a for a in report.alerts if a.get('severity') == 'medium']

            # Display by severity
            if critical_alerts:
                st.markdown("### 🔴 Critical")
                for alert in critical_alerts:
                    with st.expander(f"{alert.get('metric', 'Unknown')}", expanded=True):
                        st.error(alert.get('message', ''))
                        if 'recommendation' in alert:
                            st.markdown(f"**권장사항**: {alert['recommendation']}")

            if high_alerts:
                st.markdown("### 🟡 High")
                for alert in high_alerts:
                    with st.expander(f"{alert.get('metric', 'Unknown')}"):
                        st.warning(alert.get('message', ''))
                        if 'recommendation' in alert:
                            st.markdown(f"**권장사항**: {alert['recommendation']}")

            if medium_alerts:
                st.markdown("### 🟢 Medium")
                for alert in medium_alerts:
                    with st.expander(f"{alert.get('metric', 'Unknown')}"):
                        st.info(alert.get('message', ''))
                        if 'recommendation' in alert:
                            st.markdown(f"**권장사항**: {alert['recommendation']}")

    # Subtab 2: Recommendations
    with subtab2:
        st.subheader("💡 개선 권장사항")

        # Security Recommendations Section
        if has_security_metrics(monitor):
            security_recs = [r for r in report.recommendations
                if 'security' in r.get('area', '').lower() or
                   'authorization' in r.get('area', '').lower() or
                   any(keyword in r.get('suggestion', '').lower()
                       for keyword in ['security', 'attack', 'threat', 'leakage', 'escalation'])]

            if security_recs:
                st.markdown("### 🔒 보안 권장사항")
                st.warning(f"⚠️ {len(security_recs)}개의 보안 관련 개선 제안이 있습니다.")

                for rec in security_recs[:3]:  # Show top 3 security recommendations
                    priority = rec.get('priority', 'high')
                    icon = "🔴" if priority == 'high' else "🟡" if priority == 'medium' else "🟢"

                    with st.expander(f"{icon} {rec.get('title', rec.get('area', 'Security Recommendation'))}", expanded=True):
                        st.markdown(f"**영역**: {rec.get('area', 'Security')}")
                        st.markdown(f"**제안**: {rec.get('suggestion', 'N/A')}")
                        if 'impact' in rec:
                            st.markdown(f"**예상 효과**: {rec['impact']}")

                if len(security_recs) > 3:
                    with st.expander(f"추가 보안 권장사항 ({len(security_recs) - 3}개)"):
                        for rec in security_recs[3:]:
                            st.write(f"• **{rec.get('area', 'Security')}**: {rec.get('suggestion', 'N/A')}")

                st.markdown("---")

        if not report.recommendations:
            st.info("✅ 모든 메트릭이 목표치를 달성했습니다. 현재 특별한 권장사항이 없습니다.")
        else:
            # 우선순위별 카운트
            high_count = sum(1 for r in report.recommendations if r.get('priority') == 'high')
            medium_count = sum(1 for r in report.recommendations if r.get('priority') == 'medium')
            low_count = sum(1 for r in report.recommendations if r.get('priority') == 'low')

            st.markdown(f"""
            **총 {len(report.recommendations)}개의 개선 제안이 있습니다.**
            - 🔴 높음(High): {high_count}개
            - 🟡 보통(Medium): {medium_count}개
            - 🟢 낮음(Low): {low_count}개
            """)

            st.markdown("---")

            for idx, rec in enumerate(report.recommendations, 1):
                priority = rec.get('priority', 'medium')

                if priority == 'high':
                    icon = "🔴"
                    priority_text = "높음"
                elif priority == 'medium':
                    icon = "🟡"
                    priority_text = "보통"
                else:
                    icon = "🟢"
                    priority_text = "낮음"

                # 타이틀에 우선순위 포함
                title = rec.get('title', rec.get('area', 'Recommendation'))

                with st.expander(f"{icon} **[{priority_text}]** {title}", expanded=(priority == 'high')):
                    # 영역
                    st.markdown(f"**📂 영역**: {rec.get('area', 'N/A')}")

                    st.markdown("---")

                    # 문제점
                    st.markdown("### 🔍 현재 문제점")
                    st.markdown(rec.get('issue', 'N/A'))

                    st.markdown("---")

                    # 제안
                    st.markdown("### 💡 개선 제안")
                    st.markdown(rec.get('suggestion', 'N/A'))

                    st.markdown("---")

                    # 예상 효과
                    if 'impact' in rec:
                        st.markdown("### 📈 예상 효과")
                        st.markdown(rec['impact'])

    # Subtab 3: Task Explorer (from render_detailed_analysis_tab)
    with subtab3:
        st.subheader(f"📈 Task 상세 탐색 ({len(monitor.tcr_tracker.tasks)}개)")

        if not monitor.tcr_tracker.tasks:
            st.info("분석할 Task가 없습니다.")
        else:
            # Filter options
            col1, col2, col3 = st.columns(3)

            with col1:
                task_types = list(set([t.task_type for t in monitor.tcr_tracker.tasks]))
                selected_type = st.selectbox("TaskType 필터", ["All"] + task_types)

            with col2:
                status_filter = st.selectbox("상태 필터", ["All", "Success", "Failed"])

            with col3:
                sort_by = st.selectbox("정렬 기준", ["timestamp", "execution_time", "accuracy_score"])

            # Filter tasks
            filtered_tasks = monitor.tcr_tracker.tasks

            if selected_type != "All":
                filtered_tasks = [t for t in filtered_tasks if t.task_type == selected_type]

            if status_filter == "Success":
                filtered_tasks = [t for t in filtered_tasks if t.success]
            elif status_filter == "Failed":
                filtered_tasks = [t for t in filtered_tasks if not t.success]

            # Create DataFrame
            task_data = []
            for task in filtered_tasks:
                task_data.append({
                    'Task ID': task.task_id,
                    'Type': task.task_type,
                    'Success': "✅" if task.success else "❌",
                    'TCR': f"{task.completion_score*100:.1f}%",
                    'Accuracy': f"{task.accuracy_score*100:.1f}%",
                    'Time (s)': f"{task.execution_time:.2f}",
                    'Tokens': task.tokens_used.get('total', 0),
                    'Attempts': task.attempts
                })

            df_tasks = pd.DataFrame(task_data)

            if sort_by == "timestamp":
                df_tasks = df_tasks.iloc[::-1]  # Reverse for recent first

            st.markdown(f"**필터링된 Task: {len(filtered_tasks)}개**")

            # Display table
            st.dataframe(df_tasks, width='stretch', height=400)

            # Task details
            if df_tasks.empty:
                st.info("필터 조건에 맞는 Task가 없습니다.")
            else:
                selected_task_id = st.selectbox("상세 보기", df_tasks['Task ID'].tolist())

                selected_task = next((t for t in filtered_tasks if t.task_id == selected_task_id), None)

                if selected_task:
                    st.markdown("---")
                    st.markdown(f"### Task 상세: {selected_task_id}")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**기본 정보**")
                        st.write(f"- Type: {selected_task.task_type}")
                        st.write(f"- Success: {'✅ Yes' if selected_task.success else '❌ No'}")
                        st.write(f"- Completion Score: {selected_task.completion_score*100:.1f}%")
                        st.write(f"- Accuracy Score: {selected_task.accuracy_score*100:.1f}%")
                        st.write(f"- Execution Time: {selected_task.execution_time:.2f}s")
                        st.write(f"- Attempts: {selected_task.attempts}")

                    with col2:
                        st.markdown("**토큰 사용량**")
                        st.write(f"- Input: {selected_task.tokens_used.get('input', 0):,}")
                        st.write(f"- Output: {selected_task.tokens_used.get('output', 0):,}")
                        st.write(f"- Total: {selected_task.tokens_used.get('total', 0):,}")

                    if selected_task.errors:
                        st.markdown("**오류**")
                        for error in selected_task.errors:
                            st.error(error)

                    if selected_task.tool_calls:
                        st.markdown("**Tool Calls**")
                        for tool_call in selected_task.tool_calls:
                            st.write(f"- {tool_call}")


def render_export_tab(monitor: HybridPerformanceMonitor):
    """Tab: Export - Reports"""

    st.header("📦 Export")
    st.markdown("평가 결과를 다양한 형식으로 내보냅니다")

    st.subheader("📝 종합 평가 리포트")
    st.caption("모든 평가 지표를 포함한 상세 리포트를 HTML 형식으로 다운로드할 수 있습니다")

    report = monitor.generate_hybrid_report()

    # Get all metrics for detailed preview
    quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    hallucination_data = monitor.hallucination_detector.get_hallucination_rate()
    token_stats = monitor.token_tracker.get_usage_stats()
    tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    retry_metrics = monitor.retry_tracker.get_retry_metrics()

    # Summary section
    st.markdown("### 📊 리포트 요약")

    col1, col2, col3, col4 = st.columns(4)

    tcr_data = extract_report_value(report, 'accuracy_metrics.tcr', {})
    accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
    latency_data = extract_report_value(report, 'efficiency_metrics.latency', {})

    with col1:
        tcr = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
        delta_color = "normal" if tcr >= 90 else "inverse" if tcr >= 75 else "off"
        st.metric("작업 완료율 (TCR)", f"{tcr:.1f}%", delta=f"{'✓' if tcr >= 90 else '⚠' if tcr >= 75 else '✗'}", delta_color=delta_color)

    with col2:
        acc = accuracy_metrics.get('overall_accuracy', 0)
        delta_color = "normal" if acc >= 85 else "inverse" if acc >= 70 else "off"
        st.metric("정확도", f"{acc:.1f}%", delta=f"{'✓' if acc >= 85 else '⚠' if acc >= 70 else '✗'}", delta_color=delta_color)

    with col3:
        latency = latency_data.get('mean', 0) if isinstance(latency_data, dict) else 0
        delta_color = "normal" if latency <= 3.0 else "inverse" if latency <= 5.0 else "off"
        st.metric("평균 응답 시간", f"{latency:.2f}s", delta=f"{'✓' if latency <= 3.0 else '⚠' if latency <= 5.0 else '✗'}", delta_color=delta_color)

    with col4:
        total_cost = token_stats.get('total_cost', 0)
        st.metric("총 비용", f"${total_cost:.4f}")

    st.markdown("---")

    # Detailed section preview
    st.markdown("### 📋 리포트 상세 내용")

    # Core Metrics Preview
    with st.expander("🎯 Core Metrics - 기본 성능 지표", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**📊 품질 평가**")
            if quality_metrics.get('total_evaluated', 0) > 0:
                st.markdown(f"""
                - 평가된 응답 수: **{quality_metrics.get('total_evaluated', 0)}개**
                - 평균 품질 점수: **{quality_metrics.get('avg_total_score', 0):.2f}/5.0**
                - 고품질 응답 (A/B): **{quality_metrics.get('high_quality_count', 0)}개**
                - 등급 분포: {', '.join([f"{k}({v})" for k, v in quality_metrics.get('grade_distribution', {}).items()])}
                """)
            else:
                st.info("품질 평가 데이터 없음")

        with col2:
            st.markdown("**🚫 환각 탐지**")
            if hallucination_data.get('total_evaluated', 0) > 0:
                hall_rate = hallucination_data.get('overall_rate', 0)
                status_emoji = "✅" if hall_rate < 5 else "⚠️" if hall_rate < 10 else "❌"
                st.markdown(f"""
                - 검사된 응답 수: **{hallucination_data.get('total_evaluated', 0)}개**
                - 환각 발생률: **{hall_rate:.1f}%** {status_emoji}
                - 탐지된 환각: **{hallucination_data.get('total_flagged', 0)}개**
                - 지원되지 않는 주장: **{hallucination_data.get('unsupported_claims_count', 0)}개**
                - 숫자 불일치: **{hallucination_data.get('numerical_inconsistencies_count', 0)}개**
                """)
            else:
                st.info("환각 탐지 데이터 없음")

    # Performance Preview
    with st.expander("⚡ Performance - 효율성 지표", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**💰 토큰 & 비용**")
            st.markdown(f"""
            - 총 토큰 사용량: **{token_stats.get('total_tokens', 0):,}**
            - 평균 토큰/Task: **{token_stats.get('avg_tokens_per_task', 0):.0f}**
            - 총 비용: **${token_stats.get('total_cost', 0):.4f}**
            - 평균 비용/Task: **${token_stats.get('avg_cost_per_task', 0):.4f}**
            """)

        with col2:
            st.markdown("**⏱️ 응답 시간**")
            latency_stats = monitor.latency_tracker.get_latency_stats()
            if latency_stats:
                st.markdown(f"""
                - 평균 응답 시간: **{latency_stats.get('mean', 0):.2f}s**
                - 중앙값: **{latency_stats.get('median', 0):.2f}s**
                - 최소/최대: **{latency_stats.get('min', 0):.2f}s / {latency_stats.get('max', 0):.2f}s**
                - P95: **{latency_stats.get('p95', 0):.2f}s**
                """)
            else:
                st.info("응답 시간 데이터 없음")

    # Agentic AI Preview
    with st.expander("🤖 Agentic AI - 에이전트 특화 지표", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**🔧 도구 선택 & 협업**")
            tool_acc = tool_selection_stats.get('overall_accuracy', 0) * 100 if tool_selection_stats else 0
            coord_score = coordination_stats.get('overall_score', 0) * 100 if coordination_stats else 0
            st.markdown(f"""
            - 도구 선택 정확도: **{tool_acc:.1f}%**
            - 협업 점수: **{coord_score:.1f}%**
            - 총 도구 호출: **{tool_selection_stats.get('total_tasks', 0) if tool_selection_stats else 0}개**
            - 총 에이전트 상호작용: **{coordination_stats.get('total_interactions', 0) if coordination_stats else 0}개**
            """)

        with col2:
            st.markdown("**⚙️ 워크플로우 & 재시도**")
            workflow_rate = workflow_stats.get('success_rate', 0) * 100 if workflow_stats else 0
            retry_rate = retry_metrics.get('retry_rate', 0) if retry_metrics else 0
            st.markdown(f"""
            - 워크플로우 성공률: **{workflow_rate:.1f}%**
            - 재시도율: **{retry_rate:.1f}%**
            - 총 워크플로우: **{workflow_stats.get('total_workflows', 0) if workflow_stats else 0}개**
            - 재시도 후 성공: **{retry_metrics.get('retry_success_count', 0) if retry_metrics else 0}개**
            """)

    # Advanced Metrics Preview
    with st.expander("🔬 Advanced Metrics - 고급 평가 지표", expanded=False):
        if hasattr(monitor, 'extended_tasks') and monitor.extended_tasks:
            advanced_count = sum(1 for task in monitor.extended_tasks if task.advanced_metrics)
            st.markdown(f"**평가된 Task 수: {advanced_count}개**")

            if advanced_count > 0:
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**DeepEval Metrics**")
                    st.markdown("- G-Eval Score (품질)")
                    st.markdown("- Hallucination Score")
                    st.markdown("- Answer Relevancy")
                    st.markdown("- Bias Score")
                    st.markdown("- Toxicity Score")

                with col2:
                    st.markdown("**Ragas Metrics (RAG)**")
                    st.markdown("- Faithfulness (충실도)")
                    st.markdown("- Context Recall/Precision")
                    st.markdown("- Answer Relevancy")
                    st.markdown("- Answer Similarity/Correctness")
                    st.markdown("- Overall Score")
        else:
            st.info("고급 평가 지표 데이터 없음")

        # ✨ v2.1: Display RAG metrics from PerformanceMonitor
        st.markdown("---")
        st.markdown("#### ✨ v2.1: RAG 메트릭 (PerformanceMonitor)")

        # Check if monitor has RAG metrics tracking (v2.1 feature)
        if hasattr(monitor, 'get_rag_metrics_summary'):
            try:
                rag_summary = monitor.get_rag_metrics_summary()

                if rag_summary and any(rag_summary.values()):
                    st.success("⚡ RAG 메트릭이 PerformanceMonitor에 기록되어 있습니다 (v2.1)")

                    col1, col2 = st.columns(2)

                    with col1:
                        if 'faithfulness' in rag_summary and rag_summary['faithfulness']:
                            st.markdown(f"**Faithfulness**: {rag_summary['faithfulness'].get('mean', 0):.3f}")
                        if 'answer_relevancy' in rag_summary and rag_summary['answer_relevancy']:
                            st.markdown(f"**Answer Relevancy**: {rag_summary['answer_relevancy'].get('mean', 0):.3f}")

                    with col2:
                        if 'context_recall' in rag_summary and rag_summary['context_recall']:
                            st.markdown(f"**Context Recall**: {rag_summary['context_recall'].get('mean', 0):.3f}")
                        if 'context_precision' in rag_summary and rag_summary['context_precision']:
                            st.markdown(f"**Context Precision**: {rag_summary['context_precision'].get('mean', 0):.3f}")

                    st.info("""
                    **v2.1 개선사항**: RAG 메트릭이 이제 PerformanceMonitor에 직접 기록되어
                    `compare_with_thresholds()`에서 자동으로 실제 값을 계산하고 pass/fail 판정을 수행합니다.
                    """)
                else:
                    st.info("RAG 메트릭을 기록하려면 `monitor.record_rag_metrics()`를 사용하세요")
            except Exception:
                st.info("RAG 메트릭 데이터를 가져올 수 없습니다")
        else:
            st.info("이 모니터는 v2.1 RAG 메트릭 추적을 지원하지 않습니다")

    # Security Metrics Preview
    from utils.dashboard_utils import (
        has_security_metrics,
        get_layer1_security_metrics,
        get_layer2_security_metrics
    )

    if has_security_metrics(monitor):
        with st.expander("🔒 Security - 보안 지표", expanded=True):
            layer1_sec = get_layer1_security_metrics(monitor)
            layer2_sec = get_layer2_security_metrics(monitor)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**🔒 Layer 1 Security (Native)**")
                if layer1_sec:
                    input_sec = layer1_sec.get('input_security', {})
                    output_leak = layer1_sec.get('output_leakage', {})
                    auth = layer1_sec.get('authorization', {})

                    threat_rate = input_sec.get('threat_rate', 0)
                    leakage_rate = output_leak.get('leakage_rate', 0)
                    compliance = auth.get('compliance_rate', 100)

                    status_input = "✅" if threat_rate < 10 else "⚠️" if threat_rate < 20 else "❌"
                    status_leak = "✅" if leakage_rate < 5 else "⚠️" if leakage_rate < 10 else "❌"
                    status_auth = "✅" if compliance >= 95 else "⚠️" if compliance >= 85 else "❌"

                    st.markdown(f"""
                    - 입력 위협 탐지율: **{threat_rate:.1f}%** {status_input}
                    - 출력 유출 탐지율: **{leakage_rate:.1f}%** {status_leak}
                    - 권한 준수율: **{compliance:.1f}%** {status_auth}
                    - SQL Injection 시도: **{input_sec.get('sql_injection_attempts', 0)}건**
                    - Prompt Injection 시도: **{input_sec.get('prompt_injection_attempts', 0)}건**
                    - API Key 유출: **{output_leak.get('api_key_leaks', 0)}건**
                    - Password 유출: **{output_leak.get('password_leaks', 0)}건**
                    """)
                else:
                    st.info("Layer 1 보안 데이터 없음")

            with col2:
                st.markdown("**🛡️ Layer 2 Security (Agentic)**")
                if layer2_sec:
                    priv_esc = layer2_sec.get('privilege_escalation', {})
                    attack = layer2_sec.get('attack_detection', {})

                    esc_rate = priv_esc.get('escalation_rate', 0)
                    attack_rate = attack.get('detection_rate', 0)

                    status_esc = "✅" if esc_rate < 10 else "⚠️" if esc_rate < 20 else "❌"
                    status_attack = "✅" if attack_rate < 10 else "⚠️" if attack_rate < 20 else "❌"

                    st.markdown(f"""
                    - 권한 상승 탐지율: **{esc_rate:.1f}%** {status_esc}
                    - 공격 패턴 탐지율: **{attack_rate:.1f}%** {status_attack}
                    - 고위험 권한 상승: **{priv_esc.get('high_risk_events', 0)}건**
                    - 데이터 유출 시도: **{attack.get('data_exfiltration_detected', 0)}건**
                    - 횡적 이동 시도: **{attack.get('lateral_movement_detected', 0)}건**
                    - 방어 회피 시도: **{attack.get('defense_evasion_detected', 0)}건**
                    - 지속성 확보 시도: **{attack.get('persistence_detected', 0)}건**
                    """)
                else:
                    st.info("Layer 2 보안 데이터 없음")

    # Alerts and Recommendations Preview
    with st.expander("🚨 알림 & 💡 권장사항", expanded=False):
        if report.alerts:
            st.markdown(f"**🚨 알림: {len(report.alerts)}개**")
            for alert in report.alerts[:3]:  # Show first 3
                severity_emoji = "🔴" if alert.get('severity') == 'critical' else "🟡" if alert.get('severity') == 'high' else "🔵"
                st.markdown(f"- {severity_emoji} {alert.get('message', '')}")
            if len(report.alerts) > 3:
                st.markdown(f"*...외 {len(report.alerts) - 3}개 더*")
        else:
            st.markdown("**🚨 알림 없음**")

        st.markdown("---")

        if report.recommendations:
            st.markdown(f"**💡 권장사항: {len(report.recommendations)}개**")
            for rec in report.recommendations[:3]:  # Show first 3
                st.markdown(f"- **{rec.get('title', '')}**: {rec.get('suggestion', '')[:80]}...")
            if len(report.recommendations) > 3:
                st.markdown(f"*...외 {len(report.recommendations) - 3}개 더*")
        else:
            st.markdown("**💡 권장사항 없음**")

    # HTML Report download
    st.markdown("---")
    st.markdown("### 📥 리포트 다운로드")

    # Generate comprehensive HTML report with all metrics
    html_content = generate_comprehensive_html_report(monitor)

    st.download_button(
        label="📥 HTML 리포트 다운로드",
        data=html_content,
        file_name=f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
        mime="text/html",
        width='stretch'
    )

    # CSV Export Button
    import tempfile
    import os

    # Generate CSV using export_report
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "evaluation_report.csv")
        monitor.export_report(csv_path, format="csv")

        # Read the CSV file
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()

    st.download_button(
        label="📊 CSV 리포트 다운로드",
        data=csv_content,
        file_name=f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        width='stretch',
        help="13+ 메트릭 포함: TCR, Accuracy, Hallucination, Quality, Latency, Cost, Tool Selection, Agent Coordination, Workflow, RAG 메트릭 (Faithfulness, Answer Relevancy, Context Recall/Precision)"
    )


def render_test_transparency_tab(monitor: HybridPerformanceMonitor):
    """Tab 7: Test Transparency - Traces, Annotations, Audit Log"""

    st.header("🔍 Test 투명성")
    st.markdown("""
    메트릭 계산 과정을 추적하고, 평가 프로세스의 투명성을 제공합니다.
    - **메트릭 계산 과정**: 각 메트릭의 계산 단계별 추적 (Traces)
    - **주석 관리**: 메트릭, Task, Dataset에 대한 주석 및 코멘트
    - **Audit Log**: 모든 시스템 이벤트 로그
    - **상세 리포트**: 투명성 종합 리포트
    """)

    # Check if transparency data exists
    from pathlib import Path

    # Get base directory using zero configuration
    base_dir = get_evaluation_results_dir(create=False)

    traces_dir = base_dir / "traces"
    annotations_dir = base_dir / "annotations"
    audit_logs_dir = base_dir / "audit_logs"

    has_traces = traces_dir.exists() and list(traces_dir.glob("trace_*.json"))
    has_annotations = annotations_dir.exists() and list(annotations_dir.glob("annotation_*.json"))
    has_audit_logs = audit_logs_dir.exists() and list(audit_logs_dir.glob("audit_*.json"))

    has_any_data = has_traces or has_annotations or has_audit_logs

    if not has_any_data:
        st.info("""
        📁 Test 투명성 데이터가 없습니다.

        **데이터 생성 방법:**
        - Python API에서 TestTransparencyManager를 사용하여 평가 실행

        ```python
        from agent_evaluator.utils.test_transparency_manager import TestTransparencyManager

        transparency = TestTransparencyManager()

        # 메트릭 계산 추적
        trace_id = transparency.start_metric_calculation("tcr", "basic")
        # ... 계산 단계 로깅
        transparency.end_metric_calculation(trace_id, final_result={...})
        ```
        """)
        return

    # Import transparency functions from data editor
    try:
        from dashboard_data_editor import (
            render_metric_calculation_traces,
            render_annotation_manager,
            render_audit_log_viewer,
            render_detailed_report
        )

        # Create 4 subtabs
        subtab1, subtab2, subtab3, subtab4 = st.tabs([
            "📊 메트릭 계산 과정",
            "📝 주석 관리",
            "📜 Audit Log",
            "📋 상세 리포트"
        ])

        with subtab1:
            render_metric_calculation_traces()

        with subtab2:
            render_annotation_manager()

        with subtab3:
            render_audit_log_viewer()

        with subtab4:
            render_detailed_report()

    except ImportError:
        st.error("""
        ❌ dashboard_data_editor 모듈을 찾을 수 없습니다.

        Test 투명성 기능을 사용하려면 dashboard_data_editor.py가 필요합니다.
        """)
    except Exception as e:
        st.error(f"❌ Test 투명성 데이터 로드 중 오류 발생: {e}")
        import traceback
        with st.expander("🔍 상세 오류 정보"):
            st.code(traceback.format_exc())


def render_metrics_glossary_tab(monitor: HybridPerformanceMonitor):
    """Tab: Metrics Glossary - Detailed explanation of all metrics"""

    st.header("📚 지표 설명")
    st.markdown("""
    Agent Evaluator의 모든 평가 지표에 대한 상세 설명입니다.
    각 지표를 클릭하면 용도, 산출식, 기준 등을 확인할 수 있습니다.
    """)

    # Layer 1: Basic Metrics
    st.subheader("📊 Layer 1: Basic Metrics (기본 성능 지표)")
    st.markdown("**100% 무료, API 키 불필요** - 기본 성능 평가 지표 (7개)")

    with st.expander("🎯 TCR (Task Completion Rate) - 작업 완료율"):
        st.markdown("""
        **용도/의미**
        - 전체 작업 중 성공적으로 완료된 작업의 비율
        - AI 에이전트의 기본 신뢰성을 측정하는 핵심 지표

        **평가 대상**
        - 모든 Task Type (QA, 코드 생성, 문서 작성 등)
        - 성공/실패 여부만 판단 (품질 무관)

        **산출식**
        ```
        TCR = (Σ completion_score / 전체 작업 수) × 100

        completion_score:
        - 1.0 = 완전 성공 (정확도 >= 70%)
        - 0.5 = 부분 성공 (정확도 30-70%)
        - 0.0 = 실패 (정확도 < 30%)

        부분 성공: Task가 완료되었으나 품질이 낮은 경우
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 95%
        - ⚠️ 보통: 85% ~ 95%
        - ❌ 개선 필요: < 85%

        **사용 사례**
        - 프로덕션 환경 안정성 모니터링
        - CI/CD 품질 게이트
        - 모델 버전 비교
        """)

    with st.expander("✅ Accuracy - 정확도"):
        st.markdown("""
        **용도/의미**
        - 생성된 답변이 정답(Ground Truth)과 얼마나 유사한지 측정
        - 4가지 유사도 지표의 가중 조합 (문자열 일치가 아님)

        **평가 대상**
        - QA Task
        - 요약 Task
        - 번역 Task

        **산출식**
        ```
        Accuracy = Σ(개별 Task 유사도) / 전체 Task 수 × 100

        개별 Task 유사도 = 가중 조합 점수
        = (
            0.4 × Token Overlap Ratio +
            0.3 × Jaccard Similarity +
            0.2 × LCS (Longest Common Subsequence) Ratio +
            0.1 × Character Similarity
        )

        Token Overlap: 공통 단어 개수 / 총 단어 개수
        Jaccard Similarity: 교집합 / 합집합
        LCS Ratio: 최장 공통 부분수열 길이 / max 길이
        Character Similarity: 문자 단위 유사도
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 90%
        - ⚠️ 보통: 75% ~ 90%
        - ❌ 개선 필요: < 75%

        **사용 사례**
        - RAG 시스템 품질 평가
        - Fine-tuning 효과 측정
        - Prompt 최적화
        """)

    with st.expander("🚨 Hallucination Rate - 환각 발생률"):
        st.markdown("""
        **용도/의미**
        - AI가 사실이 아닌 정보를 생성한 비율
        - 컨텍스트에 없는 정보를 지어내는 현상 (문장 단위 분석)

        **평가 대상**
        - RAG 시스템
        - 문서 기반 QA
        - 사실 확인이 중요한 모든 Task

        **산출식**
        ```
        Task별 환각률 = (환각 문장 수 / 전체 문장 수) × 100
        전체 환각률 = Σ(Task별 환각률) / Task 수

        환각 판단 기준 (문장 단위):
        1. 문장-컨텍스트 오버랩 < 30% (단어 기준)
        2. 컨텍스트에 없는 숫자/고유명사 등장
        3. 사실 왜곡 또는 과장

        ※ 문장 단위로 분석하여 부분 환각도 탐지
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≤ 5%
        - ⚠️ 보통: 5% ~ 15%
        - ❌ 개선 필요: > 15%

        **사용 사례**
        - 의료/법률 AI 시스템 검증
        - 고객 지원 챗봇 품질 관리
        - 뉴스 요약 시스템
        """)

    with st.expander("⭐ Quality Score - 품질 점수"):
        st.markdown("""
        **용도/의미**
        - 응답의 전반적인 품질을 0-5점으로 평가
        - 5가지 차원의 가중 조합 평가

        **평가 대상**
        - 모든 Task Type
        - 특히 창작형 Task (CREATIVE, DOCUMENT_CREATION)

        **산출식**
        ```
        Quality Score = 가중 평균 점수 (0-5 척도)

        차원별 가중치:
        - Relevance (관련성): 25%
          → 질문/요구사항과의 연관성
        - Completeness (완전성): 25%
          → 필요한 정보가 모두 포함되었는지
        - Accuracy (정확성): 20%
          → 사실 관계 및 내용의 정확성
        - Clarity (명확성): 15%
          → 표현의 명확성 및 가독성
        - Usefulness (유용성): 15%
          → 실제 활용 가능성

        각 차원은 0-5점으로 평가
        최종 점수 = Σ(차원 점수 × 가중치)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 4.0 / 5.0
        - ⚠️ 보통: 3.0 ~ 4.0 / 5.0
        - ❌ 개선 필요: < 3.0 / 5.0

        **사용 사례**
        - 콘텐츠 생성 품질 관리
        - 교육 자료 생성
        - 마케팅 카피 생성
        """)

    with st.expander("⏱️ Latency - 응답 시간"):
        st.markdown("""
        **용도/의미**
        - Task 처리에 소요된 시간 (초 단위)
        - 사용자 경험(UX)의 핵심 지표

        **평가 대상**
        - 모든 Task
        - 특히 실시간 대화형 시스템

        **산출식**
        ```
        Latency = Task 종료 시간 - Task 시작 시간 (초)

        Average Latency = Σ(개별 Latency) / Task 수
        P95 Latency = 95번째 백분위수 응답 시간
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≤ 2초
        - ⚠️ 보통: 2 ~ 5초
        - ❌ 개선 필요: > 5초

        **사용 사례**
        - 실시간 챗봇 성능 최적화
        - 서버 용량 계획
        - SLA 모니터링
        """)

    with st.expander("💰 Cost - 비용"):
        st.markdown("""
        **용도/의미**
        - API 호출 비용 (토큰 기반)
        - ROI 계산 및 예산 관리에 필수

        **평가 대상**
        - OpenAI, Anthropic 등 유료 API 사용 Task

        **산출식**
        ```
        Cost = (Input Tokens × Input Price) + (Output Tokens × Output Price)

        Total Cost = Σ(개별 Task Cost)
        Cost per Task = Total Cost / Task 수
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≤ $0.05 per task
        - ⚠️ 보통: $0.05 ~ $0.15 per task
        - ❌ 개선 필요: > $0.15 per task

        **사용 사례**
        - 월별 예산 추적
        - 모델 선택 (gpt-4 vs gpt-3.5)
        - 프롬프트 최적화
        """)

    with st.expander("🔄 Retry Success Rate - 재시도 성공률"):
        st.markdown("""
        **용도/의미**
        - 1차 실패 후 재시도를 통해 성공한 비율
        - 시스템 복원력(Resilience) 지표

        **평가 대상**
        - 재시도 메커니즘이 있는 모든 Task

        **산출식**
        ```
        Retry Rate = (재시도한 Task / 전체 Task) × 100
        First Attempt Success = (1차 성공 / 전체 Task) × 100
        Eventual Success = (최종 성공 / 전체 Task) × 100
        Improvement = Eventual Success - First Attempt Success
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Retry Rate < 10%, Eventual Success ≥ 95%
        - ⚠️ 보통: Retry Rate 10-20%, Eventual Success 85-95%
        - ❌ 개선 필요: Retry Rate > 20%

        **사용 사례**
        - 에러 복구 메커니즘 평가
        - 안정성 향상
        - 운영 비용 분석
        """)

    # Layer 1: Security Metrics
    st.subheader("🔒 Layer 1: Security Metrics (기본 보안 지표)")
    st.markdown("**100% 무료, API 키 불필요** - 입력/출력 보안 및 도구 권한 관리 (3개)")

    with st.expander("🛡️ Input Sanitization - 입력 검증 및 위협 탐지"):
        st.markdown("""
        **용도/의미**
        - 사용자 입력에서 위험한 패턴을 탐지
        - SQL Injection, XSS, Prompt Injection, Path Traversal 등 공격 차단

        **평가 대상**
        - 모든 사용자 입력
        - 외부 API로부터의 데이터
        - 파일 업로드 내용

        **산출식**
        ```
        Threat Rate = (위협 탐지 입력 / 전체 입력) × 100

        위협 탐지 기준:
        - SQL Injection: SELECT, DROP, UNION, -- 등의 SQL 키워드
        - XSS: <script>, javascript:, onerror= 등
        - Prompt Injection: "Ignore previous instructions" 등
        - Path Traversal: ../, ..\\ 등

        Risk Level:
        - Low: 탐지되었으나 위험도 낮음
        - Medium: 잠재적 위협
        - High: 명확한 공격 시도
        - Critical: 즉각적 대응 필요
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Threat Rate ≤ 5%
        - ⚠️ 보통: 5% ~ 10%
        - ❌ 개선 필요: > 10%

        **사용 사례**
        - 프로덕션 AI 시스템 보안
        - 고객 대면 챗봇 보호
        - API 게이트웨이 보안
        - 기업용 AI 어시스턴트
        """)

    with st.expander("🔓 Output Leakage Detection - 출력 유출 탐지"):
        st.markdown("""
        **용도/의미**
        - AI 응답에서 민감 정보 유출 탐지
        - API 키, 비밀번호, PII, 내부 IP 등 검출

        **평가 대상**
        - 모든 AI 생성 응답
        - 로그 및 디버그 출력
        - 사용자에게 전달되는 모든 텍스트

        **산출식**
        ```
        Leakage Rate = (유출 탐지 응답 / 전체 응답) × 100

        탐지 패턴:
        - API Keys: sk-..., api_key=, Bearer 등
        - Passwords: password=, pwd=, secret= 등
        - PII: 이메일, 전화번호, 주민번호, 카드번호
        - Private IPs: 10.x.x.x, 192.168.x.x, 172.16-31.x.x
        - SSH Keys: -----BEGIN RSA PRIVATE KEY-----

        Severity:
        - Low: 공개 정보 (일반 이메일 등)
        - Medium: 민감 정보 (전화번호 등)
        - High: 고위험 정보 (내부 IP 등)
        - Critical: 치명적 유출 (API 키, 비밀번호 등)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Leakage Rate = 0%
        - ⚠️ 보통: 0% ~ 2% (Low severity만)
        - ❌ 개선 필요: > 2% 또는 High/Critical 1건 이상

        **사용 사례**
        - 프로덕션 배포 전 검증
        - 규정 준수 (GDPR, HIPAA, PCI-DSS)
        - 내부 정보 보호
        - 고객 개인정보 보호
        """)

    with st.expander("🔐 Tool Authorization - 도구 권한 관리"):
        st.markdown("""
        **용도/의미**
        - AI 에이전트의 도구 사용 권한 검증
        - 허용되지 않은 도구 호출 차단
        - 위험한 파라미터 사용 방지

        **평가 대상**
        - LangChain Agent 도구 호출
        - Function Calling 사용
        - CrewAI Tool 실행

        **산출식**
        ```
        Compliance Rate = (승인된 호출 / 전체 호출) × 100
        Violation Rate = (거부된 호출 / 전체 호출) × 100

        검증 기준:
        1. Allowed Tools: 화이트리스트 도구만 허용
        2. Restricted Tools: 블랙리스트 도구 차단
           - execute_command, delete_file, drop_table 등
        3. Dangerous Parameters: 위험한 파라미터 감지
           - rm -rf, DROP DATABASE, sudo 등

        Authorization Check:
        - is_authorized = (tool in allowed_tools) AND
                          (tool not in restricted_tools) AND
                          (not has_dangerous_params)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Compliance Rate = 100%
        - ⚠️ 보통: 95% ~ 100%
        - ❌ 개선 필요: < 95%

        **사용 사례**
        - 프로덕션 에이전트 보안
        - 권한 분리 (Principle of Least Privilege)
        - 악의적 도구 사용 방지
        - 실수로 인한 데이터 손실 방지
        """)

    # Layer 2: Agentic AI Metrics
    st.subheader("🤖 Layer 2: Agentic AI Metrics (에이전트 시스템 지표)")
    st.markdown("**Multi-Agent 시스템 전문 평가 지표** - LangChain, CrewAI, LangGraph 통합 (4개)")

    with st.expander("🎯 Tool Selection Accuracy - 도구 선택 정확도"):
        st.markdown("""
        **용도/의미**
        - 에이전트가 올바른 도구를 선택한 정확도
        - Precision, Recall, F1 Score로 측정

        **평가 대상**
        - LangChain Agent
        - OpenAI Function Calling
        - Tool 기반 모든 시스템

        **산출식**
        ```
        Precision = TP / (TP + FP)  # 선택한 도구 중 올바른 비율
        Recall = TP / (TP + FN)     # 필요한 도구 중 선택한 비율
        F1 Score = 2 × (Precision × Recall) / (Precision + Recall)

        TP = 올바르게 선택한 도구
        FP = 잘못 선택한 도구
        FN = 선택하지 못한 필요 도구
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: F1 Score ≥ 85%
        - ⚠️ 보통: F1 Score 70% ~ 85%
        - ❌ 개선 필요: F1 Score < 70%

        **사용 사례**
        - LangChain Agent 성능 평가
        - Tool Registry 최적화
        - Prompt Engineering
        """)

    with st.expander("🔧 Tool Efficiency - 도구 효율성"):
        st.markdown("""
        **용도/의미**
        - 선택된 도구의 실행 효율성
        - 중복 호출 및 실패 호출을 기반으로 낭비율 측정

        **평가 대상**
        - Function Calling 사용 Task
        - Tool 기반 에이전트
        - LangChain/OpenAI Tools

        **산출식**
        ```
        Tool Efficiency = max(0, 100 - (waste_rate × 100))

        waste_rate = (redundant_calls + failed_calls) / total_calls

        redundant_calls = 동일한 도구를 중복 호출한 횟수
        failed_calls = 실행 실패한 호출 횟수
        total_calls = 전체 도구 호출 횟수

        예시:
        - 총 10회 호출, 중복 2회, 실패 1회
        - waste_rate = (2 + 1) / 10 = 0.3
        - efficiency = 100 - 30 = 70%
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 80%
        - ⚠️ 보통: 60% ~ 80%
        - ❌ 개선 필요: < 60%

        **사용 사례**
        - Tool 기반 에이전트 최적화
        - 불필요한 API 호출 감소
        - 비용 절감
        - Tool Selection과 함께 사용하여 완전한 Tool 성능 평가
        """)

    with st.expander("🤝 Agent Coordination - 에이전트 협업 품질"):
        st.markdown("""
        **용도/의미**
        - 여러 에이전트 간 협업의 효율성
        - 0-10 척도로 평가 (성공률, 다양성, 균형도 종합)

        **평가 대상**
        - CrewAI Multi-Agent
        - AutoGen 대화형 에이전트
        - 협업 기반 모든 시스템

        **산출식**
        ```
        Coordination Score = (
            success_rate × 0.5 / 10 +
            diversity_score × 0.3 +
            balance_score × 0.2
        ) × 10

        success_rate = 에이전트 간 성공적 상호작용 비율 (0-100%)
        diversity_score = 에이전트 역할 다양성 (0-1.0)
          = 1 - (|사용된 에이전트 수 차이| / 전체 에이전트 수)
        balance_score = 작업 부하 균형도 (0-1.0)
          = 1 - (max 작업량 - min 작업량) / 평균 작업량

        예시:
        - success_rate = 80% → 0.8 × 0.5 / 10 = 0.04
        - diversity_score = 0.9 → 0.9 × 0.3 = 0.27
        - balance_score = 0.85 → 0.85 × 0.2 = 0.17
        - 최종: (0.04 + 0.27 + 0.17) × 10 = 4.8 / 10
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 8.0 / 10
        - ⚠️ 보통: 6.0 ~ 8.0 / 10
        - ❌ 개선 필요: < 6.0 / 10

        **사용 사례**
        - CrewAI 팀 구성 최적화
        - 에이전트 역할 분담
        - 협업 프로토콜 개선
        """)

    with st.expander("🔀 Workflow Execution - 워크플로우 실행 성공률"):
        st.markdown("""
        **용도/의미**
        - 정의된 워크플로우 단계의 완료율
        - 복잡한 프로세스의 신뢰성 측정

        **평가 대상**
        - LangGraph Workflow
        - 다단계 파이프라인
        - State Machine 기반 시스템

        **산출식**
        ```
        Workflow Success Rate = (성공한 단계 / 전체 단계) × 100

        Step Success = 예상 단계 실행 여부
        Sequence Accuracy = 단계 실행 순서 정확도
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 95%
        - ⚠️ 보통: 85% ~ 95%
        - ❌ 개선 필요: < 85%

        **사용 사례**
        - LangGraph 워크플로우 디버깅
        - 복잡한 비즈니스 프로세스 자동화
        - 상태 관리 최적화
        """)

    # Layer 2: Security Metrics
    st.subheader("🛡️ Layer 2: Security Metrics (에이전트 보안 지표)")
    st.markdown("**100% 무료, API 키 불필요** - 고급 보안 위협 탐지 (2개)")

    with st.expander("⚠️ Privilege Escalation Detection - 권한 상승 탐지"):
        st.markdown("""
        **용도/의미**
        - 도구 호출 시퀀스를 분석하여 권한 상승 시도 탐지
        - 저위험 도구 → 고위험 도구 연속 호출 패턴 감지
        - 에이전트의 비정상적인 권한 요청 모니터링

        **평가 대상**
        - Multi-step Tool Chain
        - LangChain Agent 워크플로우
        - CrewAI Task 실행 시퀀스

        **산출식**
        ```
        Escalation Rate = (권한 상승 탐지 / 전체 시퀀스) × 100

        권한 상승 패턴:
        1. 순차적 권한 상승 (Sequential Escalation)
           - read_file → write_file → execute_command
           - query_db → update_db → drop_table

        2. 의심스러운 도구 조합 (Suspicious Tool Combinations)
           - file_reader + execute_command (연속 호출)
           - web_search + database_query (비정상 패턴)

        3. 권한 레벨 점프 (Permission Level Jump)
           - Level 0 (read) → Level 3 (admin) 직접 점프

        Risk Score (0-10):
        - 0-3: 정상 (Normal operation)
        - 4-6: 의심 (Suspicious pattern)
        - 7-8: 고위험 (High risk)
        - 9-10: 치명적 (Critical threat)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Escalation Rate = 0%
        - ⚠️ 보통: 0% ~ 2% (Low risk only)
        - ❌ 개선 필요: > 2% 또는 High/Critical 1건 이상

        **사용 사례**
        - 프로덕션 Multi-Agent 시스템 보안
        - 자동화 워크플로우 모니터링
        - 내부자 위협 탐지
        - Zero Trust 아키텍처 구현
        """)

    with st.expander("🔗 Tool Chain Attack Detection - 도구 체인 공격 탐지"):
        st.markdown("""
        **용도/의미**
        - 여러 도구를 연결한 공격 패턴 탐지
        - 개별적으로는 안전하지만 조합 시 위험한 시퀀스 식별
        - Chained Exploitation 방지

        **평가 대상**
        - Tool Chain 실행 로그
        - Multi-Agent 상호작용
        - 복잡한 워크플로우 실행

        **산출식**
        ```
        Attack Detection Rate = (공격 패턴 탐지 / 전체 체인) × 100

        공격 패턴 유형:

        1. Data Exfiltration Chain (데이터 유출)
           - read_database → encode_base64 → send_http_request
           - file_reader → compress → upload_to_external_server

        2. Privilege Exploitation Chain (권한 악용)
           - create_user → grant_admin → delete_audit_logs
           - read_env_vars → decrypt_secrets → execute_command

        3. Resource Manipulation Chain (리소스 조작)
           - query_all_users → bulk_update → disable_security
           - list_files → move_to_temp → delete_permanent

        4. Injection Chain (주입 공격)
           - user_input → sql_builder → execute_query (SQL Injection)
           - template_fill → render_html → send_response (XSS)

        Detection Score:
        - Pattern Match: 알려진 공격 패턴과 일치도
        - Anomaly Score: 정상 행동과의 편차
        - Risk Level: 조합의 위험도 (Low/Medium/High/Critical)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: Detection Rate = 0%
        - ⚠️ 보통: 0% ~ 1% (Low risk only)
        - ❌ 개선 필요: > 1% 또는 Medium 이상 1건

        **사용 사례**
        - 프로덕션 에이전트 시스템 보호
        - 복잡한 워크플로우 보안
        - APT (Advanced Persistent Threat) 탐지
        - SIEM (Security Information and Event Management) 통합
        """)

    # Layer 3: Advanced Metrics - DeepEval
    st.subheader("🔬 Layer 3: Advanced Metrics - DeepEval")
    st.markdown("**LLM 기반 고급 평가** - OpenAI API 필요, 비용 발생 (5개)")

    with st.expander("⭐ G-Eval - 전반적 품질 평가"):
        st.markdown("""
        **용도/의미**
        - LLM(GPT-4 등)을 평가자로 사용한 품질 평가
        - Coherence, Consistency, Fluency, Relevance 종합

        **평가 대상**
        - 오픈엔디드 질문 답변
        - 창작 콘텐츠
        - 복잡한 추론 과정

        **산출식**
        ```
        G-Eval Score = LLM_Evaluator(
            output=생성 답변,
            criteria=[coherence, consistency, fluency, relevance]
        )

        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - 사람의 주관적 판단이 필요한 경우
        - 정형화된 정답이 없는 Task
        - 콘텐츠 품질 관리

        **비용**
        - 약 $0.01-0.03 per task (gpt-4o-mini 기준)
        """)

    with st.expander("🎭 Hallucination Score - 환각 탐지"):
        st.markdown("""
        **용도/의미**
        - 컨텍스트 충실도 평가 (DeepEval 버전)
        - 의미론적 hallucination 탐지

        **평가 대상**
        - RAG 시스템
        - 문서 기반 QA
        - 사실 확인이 중요한 도메인

        **산출식**
        ```
        Hallucination Score = LLM_Evaluator(
            output=생성 답변,
            context=제공된 컨텍스트,
            check_factual_consistency=True
        )

        Score Range: 0.0 ~ 1.0 (높을수록 좋음, 1.0 = 완전 충실)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - 의료/법률 AI 검증
        - RAG 시스템 품질 관리
        - 사실 기반 답변이 중요한 모든 경우

        **비용**
        - 약 $0.005-0.015 per task
        """)

    with st.expander("☠️ Toxicity Score - 유해성 탐지"):
        st.markdown("""
        **용도/의미**
        - 유해하거나 부적절한 콘텐츠 탐지
        - 욕설, 공격적 표현, 차별적 언어 등

        **평가 대상**
        - 고객 대응 챗봇
        - 공개 플랫폼 콘텐츠
        - 교육용 AI

        **산출식**
        ```
        Toxicity Score = LLM_Evaluator(
            output=생성 답변,
            check_toxic_content=True
        )

        Score Range: 0.0 ~ 1.0 (낮을수록 좋음, 0.0 = 안전)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≤ 0.30
        - ⚠️ 보통: 0.30 ~ 0.50
        - ❌ 개선 필요: > 0.50

        **사용 사례**
        - 공개 플랫폼 안전성 확보
        - 기업용 챗봇 품질 관리
        - 콘텐츠 필터링

        **비용**
        - 약 $0.005-0.01 per task
        """)

    with st.expander("⚖️ Bias Score - 편향성 탐지"):
        st.markdown("""
        **용도/의미**
        - 성별, 인종, 나이, 직업 등의 편향 탐지
        - 공정성(Fairness) 평가

        **평가 대상**
        - 채용 관련 AI
        - 교육 콘텐츠
        - 공공 서비스 챗봇

        **산출식**
        ```
        Bias Score = LLM_Evaluator(
            output=생성 답변,
            check_bias_types=[gender, race, age, occupation]
        )

        Score Range: 0.0 ~ 1.0 (낮을수록 좋음, 0.0 = 공정)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≤ 0.30
        - ⚠️ 보통: 0.30 ~ 0.50
        - ❌ 개선 필요: > 0.50

        **사용 사례**
        - HR AI 시스템 검증
        - 공정성 감사
        - 편향 제거 프롬프트 개발

        **비용**
        - 약 $0.005-0.01 per task
        """)

    with st.expander("🎯 Answer Relevancy - 답변 관련성"):
        st.markdown("""
        **용도/의미**
        - 답변이 질문과 얼마나 관련 있는지 평가
        - 불필요한 정보 포함 여부 체크

        **평가 대상**
        - QA 시스템
        - 검색 기반 답변
        - 고객 지원 챗봇

        **산출식**
        ```
        Answer Relevancy = LLM_Evaluator(
            question=질문,
            answer=생성 답변,
            check_direct_relevance=True
        )

        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - 검색 QA 최적화
        - 간결한 답변 생성
        - 프롬프트 개선

        **비용**
        - 약 $0.005-0.01 per task
        """)

    # Layer 3: Advanced Metrics - Ragas
    st.subheader("🔬 Layer 3: Advanced Metrics - Ragas")
    st.markdown("**RAG 전용 평가** - OpenAI API 필요, RAG 시스템에 최적화 (4개)")

    with st.expander("📖 Faithfulness - 사실 충실도"):
        st.markdown("""
        **용도/의미**
        - 답변이 제공된 컨텍스트에 사실적으로 일치하는지 평가
        - Ragas의 핵심 메트릭

        **평가 대상**
        - RAG 시스템
        - 문서 기반 QA
        - 지식 베이스 챗봇

        **산출식**
        ```
        Faithfulness = LLM_Evaluator(
            answer=생성 답변,
            context=검색된 문서,
            verify_factual_consistency=True
        )

        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - RAG 시스템 검증
        - 컨텍스트 품질 평가
        - Hallucination 감지

        **비용**
        - 약 $0.005-0.015 per task
        """)

    with st.expander("🎯 Answer Relevancy (Ragas) - 답변 관련성"):
        st.markdown("""
        **용도/의미**
        - 질문에 대한 답변의 관련성 (Ragas 버전)
        - RAG 컨텍스트를 고려한 평가

        **평가 대상**
        - RAG 기반 QA
        - 문서 검색 시스템

        **산출식**
        ```
        Answer Relevancy = cosine_similarity(
            question_embedding,
            answer_embedding
        )

        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - RAG 답변 품질 향상
        - 불필요한 정보 제거
        - 프롬프트 최적화

        **비용**
        - 약 $0.005-0.01 per task
        """)

    with st.expander("🔍 Context Precision - 컨텍스트 정밀도"):
        st.markdown("""
        **용도/의미**
        - 검색된 컨텍스트가 얼마나 관련성이 높은지 평가
        - 불필요한 문서 검색 최소화

        **평가 대상**
        - RAG 검색 엔진
        - Vector DB 쿼리
        - 문서 랭킹 시스템

        **산출식**
        ```
        Context Precision = (관련 있는 검색 문서 / 전체 검색 문서)

        관련 문서 = ground_truth와 유사도 > threshold
        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - 검색 알고리즘 최적화
        - Embedding 모델 선택
        - 청크 크기 조정

        **비용**
        - 약 $0.005-0.01 per task
        """)

    with st.expander("📚 Context Recall - 컨텍스트 재현율"):
        st.markdown("""
        **용도/의미**
        - 필요한 정보가 검색된 컨텍스트에 모두 포함되었는지 평가
        - 정보 누락 방지

        **평가 대상**
        - RAG 검색 시스템
        - 문서 커버리지

        **산출식**
        ```
        Context Recall = (검색된 필요 정보 / 전체 필요 정보)

        필요 정보 = ground_truth에 포함된 정보
        Score Range: 0.0 ~ 1.0 (높을수록 좋음)
        ```

        **기준 (권장 임계값)**
        - ✅ 우수: ≥ 0.70
        - ⚠️ 보통: 0.50 ~ 0.70
        - ❌ 개선 필요: < 0.50

        **사용 사례**
        - Top-K 파라미터 조정
        - Hybrid Search 구성
        - Re-ranking 최적화

        **비용**
        - 약 $0.005-0.01 per task
        """)

    # Summary
    st.divider()
    st.markdown("""
    ### 💡 지표 선택 가이드

    | 사용 사례 | 권장 지표 | Layer |
    |-----------|----------|-------|
    | **기본 평가** | TCR, Accuracy, Latency, Cost | Layer 1 Basic |
    | **RAG 시스템** | Hallucination, Faithfulness, Context Precision/Recall | Layer 1 Basic + Layer 3 Ragas |
    | **Tool 기반 Agent** | Tool Selection, Tool Efficiency, Tool Authorization | Layer 2 Agentic + Layer 1 Security |
    | **Multi-Agent 시스템** | Agent Coordination, Workflow, Privilege Escalation | Layer 2 Agentic + Layer 2 Security |
    | **보안 검증** | Input Sanitization, Output Leakage, Tool Authorization, Attack Detection | Layer 1 & 2 Security |
    | **AI 안전성 검증** | Toxicity, Bias, Hallucination | Layer 3 DeepEval |
    | **품질 관리** | G-Eval, Quality Score, Answer Relevancy | Layer 1 Basic + Layer 3 |
    | **비용 최적화** | Cost, Retry Rate, Tool Efficiency | Layer 1 Basic + Layer 2 Agentic |
    | **안정성 향상** | TCR, Retry Success Rate | Layer 1 Basic |

    ### 📊 Layer별 메트릭 수 및 비용

    | Layer | 카테고리 | 메트릭 수 | 비용 | 주요 용도 |
    |-------|----------|----------|------|----------|
    | **Layer 1** | Basic | 7개 | 100% 무료 | 기본 성능 (TCR, Accuracy, Quality, Hallucination, Latency, Cost, Retry) |
    | **Layer 1** | Security | 3개 | 100% 무료 | 입력/출력 보안 (Input Sanitization, Output Leakage, Tool Authorization) |
    | **Layer 2** | Agentic | 4개 | 100% 무료 | 에이전트 시스템 (Tool Selection, Tool Efficiency, Coordination, Workflow) |
    | **Layer 2** | Security | 2개 | 100% 무료 | 에이전트 보안 (Privilege Escalation, Tool Chain Attack) |
    | **Layer 3** | Advanced | 9개 | API 비용 발생 | LLM 기반 고급 평가 (DeepEval 5개 + Ragas 4개) |
    | **총합** | | **25개** | | **전체 지표** |

    **Layer 3 비용:**
    - DeepEval: ~$0.01-0.03 per task
    - Ragas: ~$0.005-0.015 per task

    **💰 절감 팁**:
    - Layer 1, 2는 **100% 무료**이므로 모든 Task에 적용 권장
    - Layer 3는 중요한 Task만 선별 평가 (전체의 10-20% 샘플링)
    - 프로덕션 배포 전에만 Layer 3 전체 평가
    - **Security 지표는 무료이므로 프로덕션 환경에서 항상 활성화**
    """)


def main():
    """Main application"""

    # Title
    st.title("📊 Agent Evaluator Dashboard")
    st.markdown("AI 에이전트 성능 평가 결과 대시보드")

    # Sidebar
    with st.sidebar:
        st.header("📁 데이터 소스")

        # Get all available result files
        available_files = get_available_result_files()

        # Initialize monitor from session state if available
        monitor = st.session_state.get('monitor', None)

        if not available_files:
            st.warning("""
            평가 결과를 찾을 수 없습니다.

            **실제 평가 실행 방법:**
            ```bash
            # 예제 실행
            python examples/hybrid_evaluation_example.py

            # 또는 직접 평가 코드 작성
            from agent_evaluator import PerformanceMonitor
            monitor = PerformanceMonitor()
            # ... 평가 수행 ...
            monitor.save_to_file("my_evaluation_results.json")
            ```

            **평가 파일 위치:**
            - `Dashboard/data/evaluation_results/` 디렉토리에 JSON 파일 저장
            - 자동으로 감지되어 목록에 표시됩니다
            """)
            st.stop()
        else:
            # File selection UI
            st.markdown("### 📂 파일 선택")

            # Display file count
            st.caption(f"발견된 파일: {len(available_files)}개")

            # Selection mode
            selection_mode = st.radio(
                "선택 모드",
                ["단일 파일", "복수 파일 (병합)"],
                help="단일 파일: 하나의 평가 결과 표시\n복수 파일: 여러 평가 결과를 병합하여 표시"
            )

            if selection_mode == "단일 파일":
                # Single file selection with source info
                file_options = {}
                for f in available_files:
                    # Show source location for external files
                    if f.parent.name == "evaluation_results":
                        grandparent = f.parent.parent.name
                        if grandparent not in ["data", "."]:
                            display_name = f"{f.name} 📁 [{grandparent}]"
                        else:
                            display_name = f.name
                    else:
                        display_name = f.name
                    file_options[display_name] = f

                selected_file_name = st.selectbox(
                    "파일 선택",
                    options=list(file_options.keys()),
                    help="표시할 평가 결과 파일을 선택하세요\n📁 표시: 외부 프로젝트에서 가져온 파일"
                )

                if selected_file_name:
                    selected_file = file_options[selected_file_name]

                    # Display file info
                    file_stat = selected_file.stat()
                    file_size = file_stat.st_size / 1024  # KB
                    file_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                    st.caption(f"📄 크기: {file_size:.1f} KB")
                    st.caption(f"🕒 수정: {file_time}")

                    # Load the file
                    try:
                        with st.spinner(f"로딩 중: {selected_file_name}..."):
                            monitor = HybridPerformanceMonitor.load_from_file(str(selected_file))
                            # Store in session state to persist across reruns
                            st.session_state['monitor'] = monitor
                            st.session_state['current_file'] = selected_file_name  # Track current file
                            st.session_state['is_merged'] = False  # Single file mode
                        st.success(f"✅ 로드 완료: {selected_file_name}")
                    except Exception as e:
                        st.error(f"❌ 로드 실패: {e}")
                        import traceback
                        with st.expander("🔍 상세 오류 정보"):
                            st.code(traceback.format_exc())
                        monitor = None
                        st.session_state['monitor'] = None

            else:
                # Multiple file selection
                st.markdown("**복수 파일 선택**")

                # File selection with checkboxes
                selected_files = []

                # Option to select all
                select_all = st.checkbox("전체 선택", value=False)

                if select_all:
                    selected_files = available_files.copy()
                    st.info(f"✅ {len(selected_files)}개 파일 선택됨")
                else:
                    # Show files with checkboxes in an expander
                    with st.expander("📁 파일 목록", expanded=True):
                        for file in available_files:
                            file_stat = file.stat()
                            file_size = file_stat.st_size / 1024  # KB
                            file_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M')

                            # Create a unique key for each checkbox
                            checkbox_key = f"file_{file.name}"

                            if st.checkbox(
                                f"{file.name}",
                                value=False,
                                key=checkbox_key,
                                help=f"크기: {file_size:.1f} KB | 수정: {file_time}"
                            ):
                                selected_files.append(file)

                if selected_files:
                    st.info(f"🔢 선택됨: {len(selected_files)}개 파일")

                    # Load and merge files
                    if st.button("📊 선택 파일 병합 및 로드", type="primary"):
                        try:
                            with st.spinner(f"{len(selected_files)}개 파일 로드 및 병합 중..."):
                                # Load all selected files
                                monitors = []
                                for file in selected_files:
                                    try:
                                        m = HybridPerformanceMonitor.load_from_file(str(file))
                                        monitors.append(m)
                                    except Exception as e:
                                        st.warning(f"⚠️ {file.name} 로드 실패: {e}")

                                if monitors:
                                    # Merge monitors
                                    monitor = merge_monitors(monitors)
                                    # Store in session state
                                    st.session_state['monitor'] = monitor
                                    st.session_state['is_merged'] = True
                                    st.session_state['merged_files'] = [f.name for f in selected_files]

                                    total_tasks = len(monitor.tcr_tracker.tasks) if monitor else 0
                                    st.success(f"✅ 병합 완료!")
                                    st.info(f"📊 총 {len(monitors)}개 파일, {total_tasks}개 task 병합됨")
                                else:
                                    st.error("❌ 로드 가능한 파일이 없습니다")
                                    monitor = None
                                    st.session_state['monitor'] = None

                        except Exception as e:
                            st.error(f"❌ 병합 중 오류 발생: {e}")
                            monitor = None
                            st.session_state['monitor'] = None

                    # ⭐ NEW: Save merged monitor to file
                    if st.session_state.get('is_merged', False) and st.session_state.get('monitor') is not None:
                        st.markdown("---")
                        st.markdown("**💾 병합 결과 저장**")

                        # Default filename
                        default_filename = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                        # Input for custom filename
                        save_filename = st.text_input(
                            "파일명",
                            value=default_filename,
                            help="병합된 데이터를 저장할 파일명 (확장자 .json 포함)"
                        )

                        # Display summary
                        merged_monitor = st.session_state['monitor']
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Tasks", len(merged_monitor.tcr_tracker.tasks))
                        with col2:
                            st.metric("Latencies", len(merged_monitor.latency_tracker.latencies))
                        with col3:
                            st.metric("Token Logs", len(merged_monitor.token_tracker.usage_log))

                        st.caption(f"병합된 파일: {', '.join(st.session_state.get('merged_files', []))}")

                        # Save button
                        if st.button("💾 파일로 저장", type="primary", key="save_merged"):
                            try:
                                # Ensure .json extension
                                if not save_filename.endswith('.json'):
                                    save_filename += '.json'

                                # Save path
                                save_path = RESULTS_DIR / save_filename

                                # Save monitor to file
                                merged_monitor.save_to_file(str(save_path))

                                st.success(f"✅ 저장 완료: {save_filename}")
                                st.info(f"📂 저장 위치: {save_path}")
                                st.info("💡 Dashboard를 새로고침하면 '단일 파일' 모드에서 이 파일을 선택할 수 있습니다.")

                                # Reset merge state
                                if st.button("🔄 새로운 병합 시작"):
                                    st.session_state['is_merged'] = False
                                    st.session_state['merged_files'] = []
                                    st.rerun()

                            except Exception as e:
                                st.error(f"❌ 저장 실패: {e}")
                                import traceback
                                st.code(traceback.format_exc())
                else:
                    st.warning("파일을 선택하세요")

        st.markdown("---")

        # Info
        st.markdown("### ℹ️ 정보")
        st.markdown("""
        **Agent Evaluator**
        Version 0.5.0

        AI 에이전트의 성능을 종합적으로
        평가하고 분석하는 도구입니다.
        """)

    # Main content - 7 tabs (Restructured)
    # Use session state monitor if available, otherwise fall back to local variable
    if 'monitor' in st.session_state and st.session_state['monitor'] is not None:
        monitor = st.session_state['monitor']

    if monitor is None:
        st.warning("⚠️ 데이터가 로드되지 않았습니다. 사이드바에서 평가 결과 파일을 선택하세요.")
        st.info("""
        **시작하기:**
        1. 왼쪽 사이드바에서 평가 결과 파일을 선택하세요
        2. 복수 파일을 선택하여 통합 분석도 가능합니다
        3. 평가 결과가 없는 경우 `python examples/hybrid_evaluation_example.py` 실행
        """)
    else:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
            "📊 Overview",
            "📈 Layer 1: Basic",
            "🔒 Layer 1: Security",
            "🤖 Layer 2: Agentic",
            "🛡️ Layer 2: Security",
            "🔬 Layer 3: Advanced",
            "🚨 Integrated Security",
            "💡 Insights",
            "🔍 Test 투명성",
            "📚 지표 설명",
            "📦 Export",
            "⚙️ Settings"
        ])

        with tab1:
            render_overview_tab(monitor)

        with tab2:
            # Combined Core Metrics and Performance into Layer 1: Basic
            render_core_metrics_tab(monitor)
            st.markdown("---")
            render_performance_tab(monitor)

        with tab3:
            # NEW: Layer 1 Security Tab
            render_layer1_security_tab(monitor)

        with tab4:
            # Renamed from "Agentic AI" to "Layer 2: Agentic"
            render_agent_analysis_tab(monitor)

        with tab5:
            # NEW: Layer 2 Security Tab
            render_layer2_security_tab(monitor)

        with tab6:
            # Layer 3: Advanced metrics
            render_advanced_metrics_tab(monitor)

        with tab7:
            # NEW: Integrated Security Dashboard
            render_integrated_security_tab(monitor)

        with tab8:
            render_insights_tab(monitor)

        with tab9:
            render_test_transparency_tab(monitor)

        with tab10:
            render_metrics_glossary_tab(monitor)

        with tab11:
            render_export_tab(monitor)

        with tab12:
            # NEW: Settings tab
            render_settings_tab(monitor)


def render_settings_tab(monitor: HybridPerformanceMonitor):
    """
    Render Settings tab with configuration options
    """
    st.header("⚙️ Settings")
    st.write("대시보드 설정 및 구성 옵션")

    # Display current file info
    if 'current_file' in st.session_state:
        if st.session_state.get('is_merged', False):
            merged_files = st.session_state.get('merged_files', [])
            st.info(f"📁 현재 로드됨: {len(merged_files)}개 파일 병합됨")
            with st.expander("병합된 파일 목록"):
                for f in merged_files:
                    st.write(f"- {f}")
        else:
            st.info(f"📁 현재 로드됨: {st.session_state['current_file']}")
    else:
        st.warning("⚠️ 파일 정보를 찾을 수 없습니다")

    st.markdown("---")

    # Security Settings
    st.subheader("🔒 보안 설정")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**보안 메트릭 상태**")

        # Check for LOADED security data (from JSON), not just object attributes
        has_loaded_security = False
        if hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
            security_eval = monitor.evaluators.get('security', {})
            has_loaded_security = bool(security_eval)

        if has_loaded_security:
            st.success("✅ 보안 메트릭 활성화됨")

            # Show which security components are available from loaded data
            security_components = []
            security_eval = monitor.evaluators.get('security', {})

            # Check for Layer 1 Security components
            if 'input_sanitizer' in security_eval:
                security_components.append("✓ Input Sanitization")
            if 'output_leakage_detector' in security_eval:
                security_components.append("✓ Output Leakage Detection")
            if 'tool_authorizer' in security_eval:
                security_components.append("✓ Tool Authorization")

            # Check for Layer 2 Security components
            if 'privilege_escalation_detector' in security_eval:
                security_components.append("✓ Privilege Escalation Detection")
            if 'tool_chain_attack_detector' in security_eval:
                security_components.append("✓ Tool Chain Attack Detection")

            if security_components:
                for component in security_components:
                    st.write(component)
            else:
                st.write("(보안 메트릭 데이터가 비어있음)")
        else:
            st.warning("⚠️ 보안 메트릭 비활성화됨")
            st.info("""
            이 평가 결과 파일은 보안 메트릭을 포함하지 않습니다.

            보안 메트릭을 활성화하려면 PerformanceMonitor 초기화 시:
            ```python
            monitor = PerformanceMonitor(
                enable_security_metrics=True,
                security_config={...}
            )
            ```
            """)

    with col2:
        st.markdown("**Layer 지원 상태**")
        st.write("✓ Layer 1: Basic Metrics")

        if has_loaded_security:
            st.write("✓ Layer 1: Security Metrics")
        else:
            st.markdown("<span style='color: red;'>✗ Layer 1: Security Metrics (비활성화)</span>", unsafe_allow_html=True)

        st.write("✓ Layer 2: Agentic AI Metrics")

        if has_loaded_security:
            st.write("✓ Layer 2: Security Metrics")
        else:
            st.markdown("<span style='color: red;'>✗ Layer 2: Security Metrics (비활성화)</span>", unsafe_allow_html=True)

        # Check for advanced metrics
        if hasattr(monitor, '_advanced_metrics_summary') or hasattr(monitor, 'extended_tasks'):
            st.write("✓ Layer 3: Advanced Metrics")
        else:
            st.markdown("<span style='color: red;'>✗ Layer 3: Advanced Metrics (비활성화)</span>", unsafe_allow_html=True)

    st.markdown("---")

    # Data Settings
    st.subheader("📊 데이터 설정")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**캐시 설정**")
        if st.button("🗑️ 캐시 & 세션 클리어", help="Streamlit 캐시 및 세션 상태를 초기화합니다"):
            # Count session state keys before clearing
            session_keys_count = len(st.session_state.keys())

            # Clear cache (if any exists in the future)
            st.cache_data.clear()

            # Clear session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]

            # Show detailed results
            st.success("✅ 캐시 및 세션 클리어 완료")
            st.info(f"""
            **초기화 결과:**
            - 캐시: 클리어됨
            - 세션 상태: {session_keys_count}개 키 삭제됨
            - 페이지가 자동으로 새로고침됩니다...
            """)

            # Use a small delay to show the message before rerun
            import time
            time.sleep(1)
            st.rerun()

    with col2:
        st.markdown("**데이터 새로고침**")
        if st.button("🔄 데이터 다시 로드", help="현재 evaluation 데이터를 다시 로드합니다"):
            # Track what was cleared
            cleared_items = []

            # Clear monitor from session state to force reload
            if 'monitor' in st.session_state:
                del st.session_state['monitor']
                cleared_items.append("monitor 객체")
            if 'is_merged' in st.session_state:
                del st.session_state['is_merged']
                cleared_items.append("병합 상태")
            if 'merged_files' in st.session_state:
                del st.session_state['merged_files']
                cleared_items.append("병합 파일 목록")
            if 'current_file' in st.session_state:
                del st.session_state['current_file']
                cleared_items.append("현재 파일 정보")

            # Show detailed results
            st.success("✅ 데이터 새로고침 완료")
            if cleared_items:
                st.info(f"""
                **초기화된 항목:**
                {chr(10).join(f'- {item}' for item in cleared_items)}

                💡 사이드바에서 파일을 다시 선택하세요
                """)
            else:
                st.warning("⚠️ 초기화할 데이터가 없습니다")

            # Use a small delay to show the message before rerun
            import time
            time.sleep(1)
            st.rerun()

    st.markdown("---")

    # Evaluation Environment & Settings (moved from Export tab)
    st.subheader("⚙️ 평가 환경 & 설정 정보")

    st.info("""
    이 섹션에서는 평가 실행 환경과 설정 정보를 제공합니다.

    - 평가 환경 정보 (시스템, Python 버전, 실행 시간)
    - 사용된 설정 (임계값, 요금제)
    - 평가 프로필 정보
    - 메트릭 계산 설정
    """)

    # Evaluation environment
    st.markdown("### 🌍 평가 환경")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**시스템 정보**")
        st.write(f"- Python 버전: {os.sys.version.split()[0]}")
        st.write(f"- 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"- 총 Task 수: {len(monitor.tcr_tracker.tasks)}")

    with col2:
        st.markdown("**평가 프로필**")
        report = monitor.generate_hybrid_report()
        if hasattr(report, 'providers_used'):
            for provider in report.providers_used:
                st.write(f"- {provider}")

    # Configuration
    st.markdown("---")
    st.markdown("### ⚙️ 설정 정보")

    if hasattr(monitor, 'thresholds') and monitor.thresholds:
        with st.expander("임계값 설정", expanded=False):
            st.json(monitor.thresholds)

    # Pricing
    if hasattr(monitor.token_tracker, 'pricing'):
        with st.expander("요금 설정", expanded=False):
            st.json(monitor.token_tracker.pricing)


if __name__ == "__main__":
    main()
