"""
Security Dashboard Tabs
========================

Security-focused tab components for the dashboard
"""

import streamlit as st
import plotly.graph_objects as go
from typing import Dict, Any, List
from .dashboard_utils import (
    get_layer1_security_metrics,
    get_layer2_security_metrics,
    calculate_security_risk_score,
    generate_security_alerts,
    has_security_metrics
)
from .security_visualizations import (
    create_security_risk_gauge,
    create_risk_breakdown_chart,
    create_input_security_chart,
    create_output_leakage_chart,
    create_attack_detection_chart,
    create_security_comparison_chart,
    create_security_timeline
)


# ============================================================================
# Layer 1: Security Tab
# ============================================================================

def render_layer1_security_tab(monitor):
    """Render Layer 1 Security metrics tab"""
    st.header("🔒 Layer 1: 보안 기본 지표")

    # Check if security metrics are available
    if not has_security_metrics(monitor):
        st.warning("""
        ⚠️ **보안 메트릭이 활성화되지 않았습니다.**

        보안 메트릭을 사용하려면 PerformanceMonitor 초기화 시 다음과 같이 설정하세요:

        ```python
        monitor = PerformanceMonitor(
            enable_security_metrics=True,
            security_config={
                'allowed_tools': ['search', 'read', 'query'],
                'restricted_tools': ['delete', 'execute', 'drop']
            }
        )
        ```
        """)
        return

    # Get security metrics
    layer1_sec = get_layer1_security_metrics(monitor)

    if not layer1_sec:
        st.info("보안 데이터가 아직 수집되지 않았습니다.")
        return

    # Overview metrics
    st.subheader("📊 보안 현황 요약")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        threat_rate = layer1_sec.get('input_security', {}).get('threat_rate', 0)
        st.metric(
            "입력 위협 탐지율",
            f"{threat_rate:.1f}%",
            delta=None,
            help="입력에서 탐지된 보안 위협의 비율"
        )

    with col2:
        leakage_rate = layer1_sec.get('output_leakage', {}).get('leakage_rate', 0)
        st.metric(
            "출력 유출 탐지율",
            f"{leakage_rate:.1f}%",
            delta=None,
            help="출력에서 탐지된 민감정보 유출의 비율"
        )

    with col3:
        violation_rate = layer1_sec.get('authorization', {}).get('violation_rate', 0)
        st.metric(
            "권한 위반율",
            f"{violation_rate:.1f}%",
            delta=None,
            help="권한이 없는 도구 호출 시도의 비율"
        )

    with col4:
        compliance_rate = layer1_sec.get('authorization', {}).get('compliance_rate', 100)
        st.metric(
            "권한 준수율",
            f"{compliance_rate:.1f}%",
            delta=None,
            help="권한 정책을 준수한 도구 호출의 비율"
        )

    st.markdown("---")

    # Input Security Details
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🛡️ 입력 보안 (Input Sanitization)")

        if 'input_security' in layer1_sec:
            input_sec = layer1_sec['input_security']

            # Display metrics
            st.write(f"**총 입력 수:** {input_sec.get('total_inputs', 0)}")
            st.write(f"**위협 탐지 수:** {input_sec.get('threats_detected', 0)}")
            st.write(f"**위협 탐지율:** {input_sec.get('threat_rate', 0):.1f}%")

            st.markdown("**위협 유형별 탐지 현황:**")
            st.write(f"- SQL Injection: {input_sec.get('sql_injection', 0)}건")
            st.write(f"- Prompt Injection: {input_sec.get('prompt_injection', 0)}건")
            st.write(f"- XSS (Cross-Site Scripting): {input_sec.get('xss', 0)}건")
            st.write(f"- Path Traversal: {input_sec.get('path_traversal', 0)}건")

            if input_sec.get('critical_risk', 0) > 0:
                st.error(f"🔴 **치명적 위험:** {input_sec.get('critical_risk', 0)}건")

            # Visualization
            st.plotly_chart(
                create_input_security_chart(input_sec),
                width='stretch'
            )
        else:
            st.info("입력 보안 데이터가 없습니다.")

    with col2:
        st.subheader("🔓 출력 유출 탐지 (Output Leakage)")

        if 'output_leakage' in layer1_sec:
            output_leak = layer1_sec['output_leakage']

            # Display metrics
            st.write(f"**총 출력 수:** {output_leak.get('total_outputs', 0)}")
            st.write(f"**유출 탐지 수:** {output_leak.get('leakage_detected', 0)}")
            st.write(f"**유출 탐지율:** {output_leak.get('leakage_rate', 0):.1f}%")

            st.markdown("**유출 유형별 탐지 현황:**")
            st.write(f"- API Keys: {output_leak.get('api_keys', 0)}건")
            st.write(f"- Passwords: {output_leak.get('passwords', 0)}건")
            st.write(f"- Email Addresses: {output_leak.get('emails', 0)}건")
            st.write(f"- Phone Numbers: {output_leak.get('phones', 0)}건")
            st.write(f"- Private IPs: {output_leak.get('private_ips', 0)}건")

            if output_leak.get('critical_leaks', 0) > 0:
                st.error(f"🔴 **치명적 유출:** {output_leak.get('critical_leaks', 0)}건")

            # Visualization
            st.plotly_chart(
                create_output_leakage_chart(output_leak),
                width='stretch'
            )
        else:
            st.info("출력 유출 데이터가 없습니다.")

    st.markdown("---")

    # Authorization Compliance
    st.subheader("🔐 도구 권한 관리 (Authorization)")

    if 'authorization' in layer1_sec:
        auth = layer1_sec['authorization']

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("총 도구 호출", auth.get('total_calls', 0))

        with col2:
            st.metric("권한 위반", auth.get('violations', 0))

        with col3:
            st.metric("제한된 도구 시도", auth.get('restricted_attempts', 0))

        # Details
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**권한 준수 현황**")
            st.progress(auth.get('compliance_rate', 100) / 100)
            st.write(f"준수율: {auth.get('compliance_rate', 100):.1f}%")

        with col2:
            st.markdown("**위반 현황**")
            st.progress(auth.get('violation_rate', 0) / 100)
            st.write(f"위반율: {auth.get('violation_rate', 0):.1f}%")

        if auth.get('dangerous_params', 0) > 0:
            st.warning(f"⚠️ 위험한 파라미터 사용 시도: {auth.get('dangerous_params', 0)}건")
    else:
        st.info("권한 관리 데이터가 없습니다.")


# ============================================================================
# Layer 2: Security Tab
# ============================================================================

def render_layer2_security_tab(monitor):
    """Render Layer 2 Security metrics tab"""
    st.header("🛡️ Layer 2: 보안 에이전트 지표")

    # Check if security metrics are available
    if not has_security_metrics(monitor):
        st.warning("⚠️ 보안 메트릭이 활성화되지 않았습니다. Layer 1 Security 탭의 안내를 참고하세요.")
        return

    # Get security metrics
    layer2_sec = get_layer2_security_metrics(monitor)

    if not layer2_sec:
        st.info("Layer 2 보안 데이터가 아직 수집되지 않았습니다.")
        return

    # Overview metrics
    st.subheader("📊 에이전트 보안 현황")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        escalation_rate = layer2_sec.get('privilege_escalation', {}).get('escalation_rate', 0)
        st.metric(
            "권한 상승 탐지율",
            f"{escalation_rate:.1f}%",
            delta=None,
            help="권한 상승 시도가 탐지된 비율"
        )

    with col2:
        escalations = layer2_sec.get('privilege_escalation', {}).get('escalations_detected', 0)
        st.metric(
            "권한 상승 탐지",
            f"{escalations}건",
            delta=None,
            help="탐지된 권한 상승 시도 건수"
        )

    with col3:
        detection_rate = layer2_sec.get('attack_detection', {}).get('detection_rate', 0)
        st.metric(
            "공격 탐지율",
            f"{detection_rate:.1f}%",
            delta=None,
            help="의심스러운 공격 패턴 탐지 비율"
        )

    with col4:
        suspicious_chains = layer2_sec.get('attack_detection', {}).get('suspicious_chains', 0)
        st.metric(
            "의심스러운 체인",
            f"{suspicious_chains}건",
            delta=None,
            help="탐지된 의심스러운 도구 체인 건수"
        )

    st.markdown("---")

    # Privilege Escalation Details
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("⬆️ 권한 상승 탐지 (Privilege Escalation)")

        if 'privilege_escalation' in layer2_sec:
            priv_esc = layer2_sec['privilege_escalation']

            st.write(f"**총 평가 수:** {priv_esc.get('total_evaluations', 0)}")
            st.write(f"**상승 탐지:** {priv_esc.get('escalations_detected', 0)}건")
            st.write(f"**탐지율:** {priv_esc.get('escalation_rate', 0):.1f}%")
            st.write(f"**고위험 이벤트:** {priv_esc.get('high_risk_events', 0)}건")
            st.write(f"**의심스러운 시퀀스:** {priv_esc.get('suspicious_sequences', 0)}건")

            if priv_esc.get('high_risk_events', 0) > 0:
                st.error(f"🔴 **고위험 권한 상승:** {priv_esc.get('high_risk_events', 0)}건 발생!")

            # Risk explanation
            with st.expander("권한 상승이란?"):
                st.markdown("""
                **권한 상승 (Privilege Escalation)**은 에이전트가 낮은 권한의 도구에서 시작하여
                점진적으로 높은 권한의 도구로 이동하는 패턴을 말합니다.

                **예시:**
                - read_user_file (읽기) → execute_command (실행) → read_admin_file (관리자)
                - get_token (읽기) → modify_permissions (쓰기) → access_database (관리자)

                **위험성:** 공격자가 시스템의 전체 제어권을 얻을 수 있습니다.
                """)
        else:
            st.info("권한 상승 탐지 데이터가 없습니다.")

    with col2:
        st.subheader("🎯 공격 체인 탐지 (Attack Detection)")

        if 'attack_detection' in layer2_sec:
            attack = layer2_sec['attack_detection']

            st.write(f"**분석된 체인:** {attack.get('chains_analyzed', 0)}개")
            st.write(f"**의심스러운 체인:** {attack.get('suspicious_chains', 0)}개")
            st.write(f"**탐지율:** {attack.get('detection_rate', 0):.1f}%")

            st.markdown("**공격 유형별 탐지:**")
            st.write(f"- Data Exfiltration (데이터 유출): {attack.get('data_exfiltration', 0)}건")
            st.write(f"- Lateral Movement (횡적 이동): {attack.get('lateral_movement', 0)}건")
            st.write(f"- Defense Evasion (방어 회피): {attack.get('defense_evasion', 0)}건")
            st.write(f"- Persistence (지속성 확보): {attack.get('persistence', 0)}건")

            # Visualization
            st.plotly_chart(
                create_attack_detection_chart(attack),
                width='stretch'
            )

            # Attack explanation
            with st.expander("공격 체인이란?"):
                st.markdown("""
                **공격 체인 (Attack Chain)**은 여러 도구를 연속적으로 사용하여
                악의적인 목적을 달성하는 패턴입니다.

                **예시:**
                - **데이터 유출:** read_database → encode → http_post
                - **횡적 이동:** scan_network → connect_to_server → execute_remote
                - **방어 회피:** disable_logging → clear_history → delete_logs

                **위험성:** 단일 도구로는 탐지하기 어려운 복합 공격을 수행할 수 있습니다.
                """)
        else:
            st.info("공격 체인 탐지 데이터가 없습니다.")

    st.markdown("---")

    # Comparison chart
    if layer2_sec:
        st.subheader("📊 Layer 2 보안 지표 비교")

        col1, col2 = st.columns(2)

        with col1:
            # Privilege Escalation Metrics
            if layer2_sec.get('privilege_escalation'):
                priv_esc = layer2_sec['privilege_escalation']

                st.markdown("##### 🔐 권한 상승 탐지")

                # Metrics
                mcol1, mcol2, mcol3 = st.columns(3)
                with mcol1:
                    st.metric(
                        "탐지율",
                        f"{priv_esc.get('escalation_rate', 0):.1f}%",
                        help="권한 상승이 탐지된 비율"
                    )
                with mcol2:
                    st.metric(
                        "총 평가",
                        f"{priv_esc.get('total_evaluations', 0)}",
                        help="분석된 총 권한 체인 수"
                    )
                with mcol3:
                    st.metric(
                        "고위험",
                        f"{priv_esc.get('high_risk_events', 0)}",
                        help="고위험으로 분류된 이벤트 수"
                    )

                # Bar chart for privilege escalation
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=['탐지됨', '정상'],
                    y=[
                        priv_esc.get('escalations_detected', 0),
                        priv_esc.get('total_evaluations', 0) - priv_esc.get('escalations_detected', 0)
                    ],
                    marker_color=['#ff4444', '#44ff44'],
                    text=[
                        priv_esc.get('escalations_detected', 0),
                        priv_esc.get('total_evaluations', 0) - priv_esc.get('escalations_detected', 0)
                    ],
                    textposition='auto'
                ))
                fig.update_layout(
                    title="권한 상승 탐지 결과",
                    yaxis_title="체인 수",
                    height=300,
                    showlegend=False
                )
                st.plotly_chart(fig, width='stretch')

        with col2:
            # Attack Detection Metrics
            if layer2_sec.get('attack_detection'):
                attack_det = layer2_sec['attack_detection']

                st.markdown("##### 🎯 공격 패턴 탐지")

                # Metrics
                mcol1, mcol2, mcol3 = st.columns(3)
                with mcol1:
                    st.metric(
                        "탐지율",
                        f"{attack_det.get('detection_rate', 0):.1f}%",
                        help="공격 패턴이 탐지된 비율"
                    )
                with mcol2:
                    st.metric(
                        "총 분석",
                        f"{attack_det.get('total_chains_analyzed', 0)}",
                        help="분석된 총 도구 체인 수"
                    )
                with mcol3:
                    st.metric(
                        "의심스러운",
                        f"{attack_det.get('suspicious_chains', 0)}",
                        help="의심스러운 체인 수"
                    )

                # Attack types breakdown
                attack_types = {
                    '데이터 유출': attack_det.get('data_exfiltration_detected', 0),
                    '횡적 이동': attack_det.get('lateral_movement_detected', 0),
                    '방어 회피': attack_det.get('defense_evasion_detected', 0),
                    '지속성': attack_det.get('persistence_detected', 0)
                }

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=list(attack_types.keys()),
                    y=list(attack_types.values()),
                    marker_color=['#ff6b6b', '#ff9f40', '#ffcd56', '#4bc0c0'],
                    text=list(attack_types.values()),
                    textposition='auto'
                ))
                fig.update_layout(
                    title="공격 유형별 탐지 현황",
                    yaxis_title="탐지 횟수",
                    height=300,
                    showlegend=False
                )
                st.plotly_chart(fig, width='stretch')

        # Combined comparison
        st.markdown("---")
        st.markdown("##### 📈 Layer 2 보안 지표 종합")

        # Create comparison metrics
        comparison_data = {
            '지표': [],
            '값': [],
            '상태': []
        }

        if layer2_sec.get('privilege_escalation'):
            priv_esc = layer2_sec['privilege_escalation']
            esc_rate = priv_esc.get('escalation_rate', 0)
            comparison_data['지표'].append('권한 상승 탐지율')
            comparison_data['값'].append(f"{esc_rate:.1f}%")
            comparison_data['상태'].append('🔴 주의' if esc_rate > 50 else '🟡 경고' if esc_rate > 20 else '🟢 정상')

            comparison_data['지표'].append('고위험 이벤트')
            high_risk = priv_esc.get('high_risk_events', 0)
            comparison_data['값'].append(str(high_risk))
            comparison_data['상태'].append('🔴 주의' if high_risk > 3 else '🟡 경고' if high_risk > 0 else '🟢 정상')

        if layer2_sec.get('attack_detection'):
            attack_det = layer2_sec['attack_detection']
            det_rate = attack_det.get('detection_rate', 0)
            comparison_data['지표'].append('공격 패턴 탐지율')
            comparison_data['값'].append(f"{det_rate:.1f}%")
            comparison_data['상태'].append('🔴 주의' if det_rate > 30 else '🟡 경고' if det_rate > 10 else '🟢 정상')

            comparison_data['지표'].append('데이터 유출 시도')
            exfil = attack_det.get('data_exfiltration_detected', 0)
            comparison_data['값'].append(str(exfil))
            comparison_data['상태'].append('🔴 주의' if exfil > 2 else '🟡 경고' if exfil > 0 else '🟢 정상')

        if comparison_data['지표']:
            import pandas as pd
            df = pd.DataFrame(comparison_data)
            st.table(df)


# ============================================================================
# Integrated Security Dashboard Tab
# ============================================================================

def render_integrated_security_tab(monitor):
    """Render integrated security dashboard combining all security metrics"""
    st.header("🚨 통합 보안 대시보드")

    # Check if security metrics are available
    if not has_security_metrics(monitor):
        st.warning("""
        ⚠️ **보안 메트릭이 활성화되지 않았습니다.**

        통합 보안 대시보드를 사용하려면 먼저 보안 메트릭을 활성화하세요.
        Layer 1 Security 탭에서 설정 방법을 확인할 수 있습니다.
        """)
        return

    # Get all security metrics
    layer1_sec = get_layer1_security_metrics(monitor)
    layer2_sec = get_layer2_security_metrics(monitor)

    if not layer1_sec and not layer2_sec:
        st.info("보안 데이터가 아직 수집되지 않았습니다.")
        return

    # Calculate overall risk score
    risk_info = calculate_security_risk_score(layer1_sec, layer2_sec)

    # Top section: Overall risk
    st.subheader("🎯 전체 보안 상태")

    col1, col2 = st.columns([1, 2])

    with col1:
        # Risk gauge
        st.plotly_chart(
            create_security_risk_gauge(risk_info['score'], risk_info['label']),
            width='stretch'
        )

    with col2:
        # Risk breakdown
        st.plotly_chart(
            create_risk_breakdown_chart(risk_info['breakdown']),
            width='stretch'
        )

    st.markdown("---")

    # Key metrics
    st.subheader("📊 주요 보안 지표")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        threat_rate = layer1_sec.get('input_security', {}).get('threat_rate', 0)
        delta_color = "inverse" if threat_rate > 10 else "normal"
        st.metric(
            "입력 위협 탐지율",
            f"{threat_rate:.1f}%",
            help="입력에서 탐지된 보안 위협의 비율"
        )

    with col2:
        leakage_rate = layer1_sec.get('output_leakage', {}).get('leakage_rate', 0)
        st.metric(
            "출력 유출 탐지율",
            f"{leakage_rate:.1f}%",
            help="출력에서 탐지된 민감정보 유출의 비율"
        )

    with col3:
        escalation_rate = layer2_sec.get('privilege_escalation', {}).get('escalation_rate', 0)
        st.metric(
            "권한 상승 탐지율",
            f"{escalation_rate:.1f}%",
            help="권한 상승 시도가 탐지된 비율"
        )

    with col4:
        attack_rate = layer2_sec.get('attack_detection', {}).get('detection_rate', 0)
        st.metric(
            "공격 패턴 탐지율",
            f"{attack_rate:.1f}%",
            help="의심스러운 공격 패턴 탐지 비율"
        )

    st.markdown("---")

    # Security alerts
    st.subheader("🚨 보안 경고 및 권장사항")

    alerts = generate_security_alerts(layer1_sec, layer2_sec)

    if alerts:
        for alert in alerts:
            if alert['level'] == 'critical':
                with st.expander(f"🔴 **[치명적]** {alert['category']}: {alert['message']}", expanded=True):
                    st.error(f"**메시지:** {alert['message']}")
                    st.info(f"**조치 방안:** {alert['action']}")
                    st.metric("관련 지표", alert.get('metric_value', 'N/A'))

            elif alert['level'] == 'high':
                with st.expander(f"⚠️ **[높음]** {alert['category']}: {alert['message']}"):
                    st.warning(f"**메시지:** {alert['message']}")
                    st.info(f"**조치 방안:** {alert['action']}")
                    st.metric("관련 지표", alert.get('metric_value', 'N/A'))

            elif alert['level'] == 'medium':
                with st.expander(f"🟡 **[중간]** {alert['category']}: {alert['message']}"):
                    st.info(f"**메시지:** {alert['message']}")
                    st.info(f"**조치 방안:** {alert['action']}")
                    st.metric("관련 지표", alert.get('metric_value', 'N/A'))
    else:
        st.success("✅ 현재 보안 경고가 없습니다. 시스템이 안전하게 운영되고 있습니다.")

    st.markdown("---")

    # Layer comparison
    st.subheader("📈 Layer별 보안 지표 비교")
    st.plotly_chart(
        create_security_comparison_chart(layer1_sec, layer2_sec),
        width='stretch'
    )

    st.markdown("---")

    # Security timeline
    st.subheader("⏱️ 보안 이벤트 타임라인")
    st.plotly_chart(
        create_security_timeline(monitor),
        width='stretch'
    )

    st.markdown("---")

    # Recommendations
    st.subheader("💡 보안 강화 권장사항")

    recommendations = []

    # Generate recommendations based on metrics
    if threat_rate > 5:
        recommendations.append({
            'priority': 'high',
            'area': '입력 보안',
            'recommendation': 'Input Sanitization 로직을 강화하고 WAF(Web Application Firewall) 규칙을 업데이트하세요.'
        })

    if leakage_rate > 3:
        recommendations.append({
            'priority': 'critical',
            'area': '출력 보안',
            'recommendation': '민감정보 마스킹 및 DLP(Data Loss Prevention) 정책을 적용하세요.'
        })

    if escalation_rate > 5:
        recommendations.append({
            'priority': 'high',
            'area': '권한 관리',
            'recommendation': '도구 권한 체계를 재설계하고 최소 권한 원칙을 적용하세요.'
        })

    if attack_rate > 5:
        recommendations.append({
            'priority': 'high',
            'area': '공격 방어',
            'recommendation': '도구 체인 실행 정책을 검토하고 이상 행위 탐지 시스템을 강화하세요.'
        })

    # Always include general recommendations
    recommendations.extend([
        {
            'priority': 'medium',
            'area': '모니터링',
            'recommendation': '보안 로그를 정기적으로 검토하고 SIEM 시스템과 통합하세요.'
        },
        {
            'priority': 'low',
            'area': '교육',
            'recommendation': '개발팀에게 보안 코딩 가이드라인 교육을 실시하세요.'
        }
    ])

    for rec in recommendations:
        if rec['priority'] == 'critical':
            st.error(f"🔴 **[치명적]** {rec['area']}: {rec['recommendation']}")
        elif rec['priority'] == 'high':
            st.warning(f"⚠️ **[높음]** {rec['area']}: {rec['recommendation']}")
        elif rec['priority'] == 'medium':
            st.info(f"🟡 **[중간]** {rec['area']}: {rec['recommendation']}")
        else:
            st.success(f"✅ **[권장]** {rec['area']}: {rec['recommendation']}")
