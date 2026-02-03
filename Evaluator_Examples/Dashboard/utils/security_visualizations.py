"""
Security Visualization Components
==================================

Provides Plotly-based visualization components for security metrics
"""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Dict, Any, List


# ============================================================================
# Security Risk Gauge
# ============================================================================

def create_security_risk_gauge(risk_score: float, risk_label: str) -> go.Figure:
    """
    Create security risk gauge chart

    Args:
        risk_score: Risk score (0-100, lower is better)
        risk_label: Risk level label (e.g., "🟢 낮음 (안전)")

    Returns:
        Plotly gauge figure
    """
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=risk_score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"보안 리스크 점수<br><sub>{risk_label}</sub>", 'font': {'size': 20}},
        number={'suffix': "", 'font': {'size': 40}},
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 20], 'color': 'lightgreen'},
                {'range': [20, 50], 'color': 'lightyellow'},
                {'range': [50, 100], 'color': 'lightcoral'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 50
            }
        }
    ))

    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=80, b=20),
        font={'family': "Arial"}
    )

    return fig


# ============================================================================
# Risk Breakdown Pie Chart
# ============================================================================

def create_risk_breakdown_chart(breakdown: Dict[str, float]) -> go.Figure:
    """
    Create pie chart showing risk breakdown by category

    Args:
        breakdown: Dict of risk categories and their scores

    Returns:
        Plotly pie chart figure
    """
    if not breakdown:
        return go.Figure()

    labels = []
    values = []
    colors = []

    label_map = {
        'input_security': '입력 보안',
        'output_leakage': '출력 유출',
        'authorization': '권한 관리',
        'privilege_escalation': '권한 상승',
        'attack_detection': '공격 탐지'
    }

    color_map = {
        'input_security': '#FF6B6B',
        'output_leakage': '#FF8E53',
        'authorization': '#FFD93D',
        'privilege_escalation': '#6BCB77',
        'attack_detection': '#4D96FF'
    }

    for key, value in breakdown.items():
        if value > 0:
            labels.append(label_map.get(key, key))
            values.append(value)
            colors.append(color_map.get(key, '#999999'))

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        hovertemplate='<b>%{label}</b><br>리스크: %{value:.2f}<br>비율: %{percent}<extra></extra>'
    )])

    fig.update_layout(
        title="보안 리스크 분포",
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
    )

    return fig


# ============================================================================
# Input Security Bar Chart
# ============================================================================

def create_input_security_chart(input_security: Dict[str, Any]) -> go.Figure:
    """
    Create bar chart for input security threats

    Args:
        input_security: Input security metrics

    Returns:
        Plotly bar chart figure
    """
    threats = {
        'SQL Injection': input_security.get('sql_injection', 0),
        'Prompt Injection': input_security.get('prompt_injection', 0),
        'XSS': input_security.get('xss', 0),
        'Path Traversal': input_security.get('path_traversal', 0)
    }

    fig = go.Figure(data=[
        go.Bar(
            x=list(threats.keys()),
            y=list(threats.values()),
            marker_color=['#FF6B6B', '#FF8E53', '#FFD93D', '#6BCB77'],
            text=list(threats.values()),
            textposition='auto',
        )
    ])

    fig.update_layout(
        title="입력 보안 위협 탐지 현황",
        xaxis_title="위협 유형",
        yaxis_title="탐지 횟수",
        height=350,
        margin=dict(l=20, r=20, t=60, b=20)
    )

    return fig


# ============================================================================
# Output Leakage Bar Chart
# ============================================================================

def create_output_leakage_chart(output_leakage: Dict[str, Any]) -> go.Figure:
    """
    Create bar chart for output leakage detection

    Args:
        output_leakage: Output leakage metrics

    Returns:
        Plotly bar chart figure
    """
    leakages = {
        'API Keys': output_leakage.get('api_keys', 0),
        'Passwords': output_leakage.get('passwords', 0),
        'Emails': output_leakage.get('emails', 0),
        'Phone Numbers': output_leakage.get('phones', 0),
        'Private IPs': output_leakage.get('private_ips', 0)
    }

    fig = go.Figure(data=[
        go.Bar(
            x=list(leakages.keys()),
            y=list(leakages.values()),
            marker_color=['#FF3838', '#FF6B6B', '#FF8E53', '#FFD93D', '#6BCB77'],
            text=list(leakages.values()),
            textposition='auto',
        )
    ])

    fig.update_layout(
        title="출력 유출 탐지 현황",
        xaxis_title="유출 유형",
        yaxis_title="탐지 횟수",
        height=350,
        margin=dict(l=20, r=20, t=60, b=20)
    )

    return fig


# ============================================================================
# Attack Detection Chart
# ============================================================================

def create_attack_detection_chart(attack_detection: Dict[str, Any]) -> go.Figure:
    """
    Create bar chart for attack pattern detection

    Args:
        attack_detection: Attack detection metrics

    Returns:
        Plotly bar chart figure
    """
    attacks = {
        'Data Exfiltration': attack_detection.get('data_exfiltration', 0),
        'Lateral Movement': attack_detection.get('lateral_movement', 0),
        'Defense Evasion': attack_detection.get('defense_evasion', 0),
        'Persistence': attack_detection.get('persistence', 0)
    }

    fig = go.Figure(data=[
        go.Bar(
            x=list(attacks.keys()),
            y=list(attacks.values()),
            marker_color=['#FF3838', '#FF6B6B', '#FF8E53', '#FFD93D'],
            text=list(attacks.values()),
            textposition='auto',
        )
    ])

    fig.update_layout(
        title="공격 패턴 탐지 현황 (Layer 2)",
        xaxis_title="공격 유형",
        yaxis_title="탐지 횟수",
        height=350,
        margin=dict(l=20, r=20, t=60, b=20)
    )

    return fig


# ============================================================================
# Security Metrics Comparison Chart
# ============================================================================

def create_security_comparison_chart(layer1_sec: Dict, layer2_sec: Dict) -> go.Figure:
    """
    Create comparison chart for Layer 1 vs Layer 2 security metrics

    Args:
        layer1_sec: Layer 1 security metrics
        layer2_sec: Layer 2 security metrics

    Returns:
        Plotly grouped bar chart figure
    """
    categories = ['입력 위협율', '출력 유출율', '권한 위반율', '권한 상승율', '공격 탐지율']

    layer1_values = [
        layer1_sec.get('input_security', {}).get('threat_rate', 0),
        layer1_sec.get('output_leakage', {}).get('leakage_rate', 0),
        layer1_sec.get('authorization', {}).get('violation_rate', 0),
        0,  # No Layer 1 equivalent
        0   # No Layer 1 equivalent
    ]

    layer2_values = [
        0,  # No Layer 2 equivalent
        0,  # No Layer 2 equivalent
        0,  # No Layer 2 equivalent
        layer2_sec.get('privilege_escalation', {}).get('escalation_rate', 0),
        layer2_sec.get('attack_detection', {}).get('detection_rate', 0)
    ]

    fig = go.Figure(data=[
        go.Bar(name='Layer 1 (Native)', x=categories, y=layer1_values, marker_color='#4D96FF'),
        go.Bar(name='Layer 2 (Agentic)', x=categories, y=layer2_values, marker_color='#6BCB77')
    ])

    fig.update_layout(
        title="보안 지표 비교: Layer 1 vs Layer 2",
        xaxis_title="지표",
        yaxis_title="탐지율 (%)",
        barmode='group',
        height=400,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig


# ============================================================================
# Security Timeline Chart
# ============================================================================

def create_security_timeline(monitor, max_events: int = 50) -> go.Figure:
    """
    Create timeline of security events

    Args:
        monitor: HybridPerformanceMonitor instance
        max_events: Maximum number of events to show

    Returns:
        Plotly scatter plot figure
    """
    events = []

    # Collect security events from various trackers
    # Input security events
    if hasattr(monitor, 'input_sanitizer') and hasattr(monitor.input_sanitizer, 'evaluations'):
        for eval_data in monitor.input_sanitizer.evaluations[-max_events:]:
            if eval_data.get('threat_count', 0) > 0:
                events.append({
                    'timestamp': eval_data.get('timestamp'),
                    'type': 'Input Threat',
                    'severity': eval_data.get('risk_level', 'low'),
                    'details': f"Threats: {eval_data.get('threat_count', 0)}"
                })

    # Output leakage events
    if hasattr(monitor, 'output_leakage_detector') and hasattr(monitor.output_leakage_detector, 'detections'):
        for detection in monitor.output_leakage_detector.detections[-max_events:]:
            if detection.get('leakage_count', 0) > 0:
                events.append({
                    'timestamp': detection.get('timestamp'),
                    'type': 'Output Leakage',
                    'severity': detection.get('severity', 'low'),
                    'details': f"Leaks: {detection.get('leakage_count', 0)}"
                })

    if not events:
        # Return empty figure with message
        fig = go.Figure()
        fig.add_annotation(
            text="보안 이벤트 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(height=300)
        return fig

    # Convert to DataFrame
    df = pd.DataFrame(events)

    # Sort by timestamp
    df = df.sort_values('timestamp')

    # Create scatter plot
    severity_colors = {'low': 'green', 'medium': 'orange', 'high': 'red', 'critical': 'darkred'}
    df['color'] = df['severity'].map(severity_colors)

    fig = px.scatter(
        df,
        x='timestamp',
        y='type',
        color='severity',
        color_discrete_map=severity_colors,
        hover_data=['details'],
        title="보안 이벤트 타임라인"
    )

    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=60, b=20),
        xaxis_title="시간",
        yaxis_title="이벤트 유형"
    )

    return fig


# ============================================================================
# Layer Metrics Radar Chart
# ============================================================================

def create_layer_metrics_radar(layer1_basic: Dict, layer2_agentic: Dict) -> go.Figure:
    """
    Create radar chart comparing Layer 1 and Layer 2 metrics

    Args:
        layer1_basic: Layer 1 basic metrics
        layer2_agentic: Layer 2 agentic metrics

    Returns:
        Plotly radar chart figure
    """
    categories = ['TCR', 'Accuracy', 'Quality', 'Tool Selection', 'Efficiency']

    layer1_values = [
        layer1_basic.get('tcr', {}).get('rate', 0),
        layer1_basic.get('accuracy', {}).get('overall', 0),
        layer1_basic.get('quality', {}).get('average_score', 0) * 20,  # Scale to 0-100
        0,  # No Layer 1 equivalent
        0   # No Layer 1 equivalent
    ]

    layer2_values = [
        0,  # Use Layer 1 value
        0,  # Use Layer 1 value
        0,  # Use Layer 1 value
        layer2_agentic.get('tool_selection', {}).get('accuracy', 0),
        layer2_agentic.get('tool_efficiency', {}).get('efficiency_score', 0)
    ]

    # Combine for display
    combined_values = [max(l1, l2) for l1, l2 in zip(layer1_values, layer2_values)]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=combined_values,
        theta=categories,
        fill='toself',
        name='Performance Metrics',
        line_color='#4D96FF'
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )
        ),
        showlegend=False,
        title="Layer 1 & 2 성능 지표",
        height=400,
        margin=dict(l=80, r=80, t=80, b=80)
    )

    return fig
