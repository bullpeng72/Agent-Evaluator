"""
Dashboard Utilities for Layer-based Metrics
===========================================

Provides utility functions to extract and process metrics from HybridPerformanceMonitor
organized by layers:
- Layer 1: Basic & Security metrics
- Layer 2: Agentic AI & Security metrics
- Layer 3: Advanced metrics (DeepEval, Ragas, LangSmith)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


# ============================================================================
# Layer Metric Mapping
# ============================================================================

LAYER_METRIC_MAPPING = {
    "layer1": {
        "basic": {
            "tcr": "tcr_tracker",
            "accuracy": "accuracy_tracker",
            "quality": "quality_evaluator",
            "hallucination": "hallucination_detector",
            "latency": "latency_tracker",
            "cost": "token_tracker"
        },
        "security": {
            "input_sanitization": "input_sanitizer",
            "output_leakage": "output_leakage_detector",
            "authorization": "tool_authorizer"
        }
    },
    "layer2": {
        "agentic": {
            "tool_selection": "tool_selection_tracker",
            "tool_efficiency": "tool_analyzer",
            "retry_success": "retry_tracker",
            "agent_coordination": "agent_coordination_tracker",
            "workflow": "workflow_tracker"
        },
        "security": {
            "privilege_escalation": "privilege_escalation_detector",
            "attack_detection": "tool_chain_attack_detector"
        }
    },
    "layer3": {
        "advanced": {
            "deepeval": "advanced_metrics.deepeval",
            "ragas": "advanced_metrics.ragas",
            "langsmith": "advanced_metrics.langsmith"
        }
    }
}


# ============================================================================
# Layer 1: Basic Metrics
# ============================================================================

def get_layer1_basic_metrics(monitor) -> Dict[str, Any]:
    """
    Extract Layer 1 basic metrics from monitor

    Returns:
        Dict with TCR, Accuracy, Quality, Hallucination, Latency, Cost metrics
    """
    metrics = {}

    # TCR (Task Completion Rate)
    if hasattr(monitor, 'tcr_tracker'):
        tcr_stats = monitor.tcr_tracker.calculate_tcr()
        metrics['tcr'] = {
            'rate': tcr_stats.get('tcr', 0),
            'completed': tcr_stats.get('completed_tasks', 0),
            'total': tcr_stats.get('total_tasks', 0)
        }

    # Accuracy
    if hasattr(monitor, 'accuracy_evaluator'):
        accuracy_stats = monitor.accuracy_evaluator.get_accuracy_scores()
        metrics['accuracy'] = {
            'overall': accuracy_stats.get('overall_accuracy', 0),
            'mean': accuracy_stats.get('overall_accuracy', 0),  # Use overall_accuracy as mean
            'median': accuracy_stats.get('median_accuracy', 0)
        }

    # Quality
    if hasattr(monitor, 'quality_evaluator'):
        quality_stats = monitor.quality_evaluator.get_quality_metrics()
        metrics['quality'] = {
            'average_score': quality_stats.get('average_total_score', 0),
            'distribution': quality_stats.get('grade_distribution', {}),
            'dimension_scores': quality_stats.get('average_dimension_scores', {})
        }

    # Hallucination
    if hasattr(monitor, 'hallucination_detector'):
        hal_stats = monitor.hallucination_detector.get_hallucination_rate()
        metrics['hallucination'] = {
            'rate': hal_stats.get('hallucination_rate', 0),
            'detected': hal_stats.get('hallucinations_detected', 0),
            'total': hal_stats.get('total_detections', 0)
        }

    # Latency
    if hasattr(monitor, 'latency_tracker'):
        latency_stats = monitor.latency_tracker.get_latency_stats()
        metrics['latency'] = {
            'mean': latency_stats.get('mean_latency', 0),
            'median': latency_stats.get('median_latency', 0),
            'p95': latency_stats.get('p95_latency', 0),
            'p99': latency_stats.get('p99_latency', 0)
        }

    # Cost & Tokens
    if hasattr(monitor, 'token_tracker'):
        token_stats = monitor.token_tracker.get_usage_stats()
        metrics['cost'] = {
            'total_cost': token_stats.get('total_cost', 0),
            'total_tokens': token_stats.get('total_tokens', 0),
            'avg_tokens_per_task': token_stats.get('avg_tokens_per_task', 0)
        }

    return metrics


# ============================================================================
# Layer 1: Security Metrics
# ============================================================================

def get_layer1_security_metrics(monitor) -> Dict[str, Any]:
    """
    Extract Layer 1 security metrics from monitor

    Returns:
        Dict with Input Sanitization, Output Leakage, Authorization metrics
    """
    security = {}

    # Input Sanitization
    if hasattr(monitor, 'input_sanitizer') and hasattr(monitor.input_sanitizer, 'get_security_stats'):
        input_stats = monitor.input_sanitizer.get_security_stats()
        security['input_security'] = {
            'total_inputs': input_stats.get('total_inputs_evaluated', 0),
            'threats_detected': input_stats.get('inputs_with_threats', 0),
            'threat_rate': input_stats.get('threat_rate', 0),
            'sql_injection': input_stats.get('sql_injection_attempts', 0),
            'prompt_injection': input_stats.get('prompt_injection_attempts', 0),
            'xss': input_stats.get('xss_attempts', 0),
            'path_traversal': input_stats.get('path_traversal_attempts', 0),
            'critical_risk': input_stats.get('critical_risk_inputs', 0)
        }
    # Fallback: Try to load from evaluators (for loaded JSON files)
    elif hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        security_eval = monitor.evaluators.get('security', {})
        input_sanitizer = security_eval.get('input_sanitizer', {})
        evaluations = input_sanitizer.get('evaluations', [])

        if evaluations:
            import pandas as pd
            df = pd.DataFrame(evaluations)
            total = len(evaluations)
            threats_detected = int(df['sanitization_needed'].sum()) if 'sanitization_needed' in df.columns else 0

            security['input_security'] = {
                'total_inputs': total,
                'threats_detected': threats_detected,
                'threat_rate': round((threats_detected / total) * 100, 2) if total > 0 else 0,
                'sql_injection': int(df['has_sql_injection'].sum()) if 'has_sql_injection' in df.columns else 0,
                'prompt_injection': int(df['has_prompt_injection'].sum()) if 'has_prompt_injection' in df.columns else 0,
                'xss': int(df['has_xss'].sum()) if 'has_xss' in df.columns else 0,
                'path_traversal': int(df['has_path_traversal'].sum()) if 'has_path_traversal' in df.columns else 0,
                'critical_risk': int((df['risk_level'] == 'critical').sum()) if 'risk_level' in df.columns else 0
            }

    # Output Leakage Detection
    if hasattr(monitor, 'output_leakage_detector') and hasattr(monitor.output_leakage_detector, 'get_leakage_stats'):
        output_stats = monitor.output_leakage_detector.get_leakage_stats()
        security['output_leakage'] = {
            'total_outputs': output_stats.get('total_outputs_evaluated', 0),
            'leakage_detected': output_stats.get('outputs_with_leakage', 0),
            'leakage_rate': output_stats.get('leakage_rate', 0),
            'api_keys': output_stats.get('api_key_leaks', 0),
            'passwords': output_stats.get('password_leaks', 0),
            'emails': output_stats.get('email_leaks', 0),
            'phones': output_stats.get('phone_leaks', 0),
            'private_ips': output_stats.get('private_ip_leaks', 0),
            'critical_leaks': output_stats.get('critical_severity_count', 0)
        }
    # Fallback: Try to load from evaluators
    elif hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        security_eval = monitor.evaluators.get('security', {})
        output_leak = security_eval.get('output_leakage_detector', {})
        detections = output_leak.get('detections', [])

        if detections:
            import pandas as pd
            df = pd.DataFrame(detections)
            total = len(detections)
            leakage_detected = int((df['leakage_count'] > 0).sum()) if 'leakage_count' in df.columns else 0

            security['output_leakage'] = {
                'total_outputs': total,
                'leakage_detected': leakage_detected,
                'leakage_rate': round((leakage_detected / total) * 100, 2) if total > 0 else 0,
                'api_keys': int(df['contains_api_key'].sum()) if 'contains_api_key' in df.columns else 0,
                'passwords': int(df['contains_password'].sum()) if 'contains_password' in df.columns else 0,
                'emails': int(df['contains_email'].sum()) if 'contains_email' in df.columns else 0,
                'phones': int(df['contains_phone'].sum()) if 'contains_phone' in df.columns else 0,
                'private_ips': int(df['contains_private_ip'].sum()) if 'contains_private_ip' in df.columns else 0,
                'critical_leaks': int((df['severity'] == 'critical').sum()) if 'severity' in df.columns else 0
            }

    # Tool Authorization Compliance
    if hasattr(monitor, 'tool_authorizer') and hasattr(monitor.tool_authorizer, 'get_compliance_stats'):
        auth_stats = monitor.tool_authorizer.get_compliance_stats()
        security['authorization'] = {
            'total_calls': auth_stats.get('total_tool_calls', 0),
            'compliance_rate': auth_stats.get('compliance_rate', 0),
            'violation_rate': auth_stats.get('violation_rate', 0),
            'violations': auth_stats.get('total_violations', 0),
            'restricted_attempts': auth_stats.get('restricted_tool_attempts', 0),
            'dangerous_params': auth_stats.get('dangerous_param_attempts', 0)
        }
    # Fallback: Try to load from evaluators
    elif hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        security_eval = monitor.evaluators.get('security', {})
        tool_auth = security_eval.get('tool_authorizer', {})
        tool_calls = tool_auth.get('tool_calls', [])

        if tool_calls:
            import pandas as pd
            df = pd.DataFrame(tool_calls)
            total = len(tool_calls)
            violations = int((~df['is_authorized']).sum()) if 'is_authorized' in df.columns else 0

            security['authorization'] = {
                'total_calls': total,
                'compliance_rate': round(((total - violations) / total) * 100, 2) if total > 0 else 100,
                'violation_rate': round((violations / total) * 100, 2) if total > 0 else 0,
                'violations': violations,
                'restricted_attempts': int(df['is_restricted'].sum()) if 'is_restricted' in df.columns else 0,
                'dangerous_params': int(df['has_dangerous_params'].sum()) if 'has_dangerous_params' in df.columns else 0
            }

    return security


# ============================================================================
# Layer 2: Agentic AI Metrics
# ============================================================================

def get_layer2_agentic_metrics(monitor) -> Dict[str, Any]:
    """
    Extract Layer 2 agentic AI metrics from monitor

    Returns:
        Dict with Tool Selection, Efficiency, Retry, Coordination, Workflow metrics
    """
    agentic = {}

    # Tool Selection
    if hasattr(monitor, 'tool_selection_tracker'):
        tool_stats = monitor.tool_selection_tracker.get_accuracy_stats()
        agentic['tool_selection'] = {
            'accuracy': tool_stats.get('overall_accuracy', 0),
            'precision': tool_stats.get('precision', 0),
            'recall': tool_stats.get('recall', 0),
            'total_selections': tool_stats.get('total_selections', 0)
        }

    # Tool Efficiency
    if hasattr(monitor, 'tool_analyzer'):
        efficiency_stats = monitor.tool_analyzer.get_efficiency_stats()
        agentic['tool_efficiency'] = {
            'efficiency_score': efficiency_stats.get('overall_efficiency', 0),
            'redundant_calls': efficiency_stats.get('redundant_calls', 0),
            'total_calls': efficiency_stats.get('total_calls', 0),
            'avg_tools_per_task': efficiency_stats.get('avg_tools_per_task', 0)
        }

    # Retry Success
    if hasattr(monitor, 'retry_tracker'):
        retry_stats = monitor.retry_tracker.get_retry_metrics()
        agentic['retry_success'] = {
            'success_rate': retry_stats.get('retry_success_rate', 0),
            'total_attempts': retry_stats.get('total_attempts', 0),
            'tasks_with_retry': retry_stats.get('tasks_requiring_retry', 0),
            'avg_retries': retry_stats.get('average_retries_per_task', 0)
        }

    # Agent Coordination
    if hasattr(monitor, 'agent_coordination_tracker'):
        coord_stats = monitor.agent_coordination_tracker.get_coordination_stats()
        agentic['agent_coordination'] = {
            'efficiency': coord_stats.get('coordination_efficiency', 0),
            'total_interactions': coord_stats.get('total_interactions', 0),
            'successful_handoffs': coord_stats.get('successful_handoffs', 0),
            'avg_agents_per_task': coord_stats.get('avg_agents_per_task', 0)
        }

    # Workflow Execution
    if hasattr(monitor, 'workflow_tracker'):
        workflow_stats = monitor.workflow_tracker.get_workflow_stats()
        agentic['workflow'] = {
            'success_rate': workflow_stats.get('workflow_success_rate', 0),
            'total_executions': workflow_stats.get('total_executions', 0),
            'avg_steps': workflow_stats.get('avg_steps_per_workflow', 0),
            'completion_time': workflow_stats.get('avg_completion_time', 0)
        }

    return agentic


# ============================================================================
# Layer 2: Security Metrics
# ============================================================================

def get_layer2_security_metrics(monitor) -> Dict[str, Any]:
    """
    Extract Layer 2 security metrics from monitor

    Returns:
        Dict with Privilege Escalation and Attack Detection metrics
    """
    security = {}

    # Privilege Escalation Detection
    if hasattr(monitor, 'privilege_escalation_detector') and hasattr(monitor.privilege_escalation_detector, 'get_escalation_stats'):
        priv_stats = monitor.privilege_escalation_detector.get_escalation_stats()
        security['privilege_escalation'] = {
            'total_evaluations': priv_stats.get('total_evaluations', 0),
            'escalations_detected': priv_stats.get('escalations_detected', 0),
            'escalation_rate': priv_stats.get('escalation_rate', 0),
            'high_risk_events': priv_stats.get('high_risk_events', 0),
            'suspicious_sequences': priv_stats.get('suspicious_sequences', 0)
        }
    elif hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        # Fallback: Read from loaded JSON
        security_eval = monitor.evaluators.get('security', {})
        escalation_events = security_eval.get('privilege_escalation_detector', {}).get('escalation_events', [])
        if escalation_events:
            df = pd.DataFrame(escalation_events)
            escalations_detected = df['escalation_detected'].sum() if 'escalation_detected' in df.columns else 0
            high_risk = df[df.get('risk_score', 0) >= 7].shape[0] if 'risk_score' in df.columns else 0
            security['privilege_escalation'] = {
                'total_evaluations': len(escalation_events),
                'escalations_detected': int(escalations_detected),
                'escalation_rate': (escalations_detected / len(escalation_events) * 100) if len(escalation_events) > 0 else 0,
                'high_risk_events': int(high_risk),
                'suspicious_sequences': df['suspicious_sequences'].apply(len).sum() if 'suspicious_sequences' in df.columns else 0
            }

    # Tool Chain Attack Detection
    if hasattr(monitor, 'tool_chain_attack_detector') and hasattr(monitor.tool_chain_attack_detector, 'get_attack_stats'):
        attack_stats = monitor.tool_chain_attack_detector.get_attack_stats()
        security['attack_detection'] = {
            'chains_analyzed': attack_stats.get('total_chains_analyzed', 0),
            'suspicious_chains': attack_stats.get('suspicious_chains', 0),
            'detection_rate': attack_stats.get('detection_rate', 0),
            'data_exfiltration': attack_stats.get('data_exfiltration_detected', 0),
            'lateral_movement': attack_stats.get('lateral_movement_detected', 0),
            'defense_evasion': attack_stats.get('defense_evasion_detected', 0),
            'persistence': attack_stats.get('persistence_detected', 0)
        }
    elif hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        # Fallback: Read from loaded JSON
        security_eval = monitor.evaluators.get('security', {})
        detections = security_eval.get('tool_chain_attack_detector', {}).get('detections', [])
        if detections:
            df = pd.DataFrame(detections)
            suspicious_chains = df['is_suspicious_chain'].sum() if 'is_suspicious_chain' in df.columns else 0

            # Count attack types
            data_exfil = 0
            lateral_move = 0
            defense_evasion = 0
            persistence = 0

            if 'attack_types' in df.columns:
                for attack_types in df['attack_types']:
                    if isinstance(attack_types, dict):
                        data_exfil += attack_types.get('data_exfiltration', False)
                        lateral_move += attack_types.get('lateral_movement', False)
                        defense_evasion += attack_types.get('defense_evasion', False)
                        persistence += attack_types.get('persistence', False)

            security['attack_detection'] = {
                'chains_analyzed': len(detections),
                'suspicious_chains': int(suspicious_chains),
                'detection_rate': (suspicious_chains / len(detections) * 100) if len(detections) > 0 else 0,
                'data_exfiltration': int(data_exfil),
                'lateral_movement': int(lateral_move),
                'defense_evasion': int(defense_evasion),
                'persistence': int(persistence)
            }

    return security


# ============================================================================
# Layer 3: Advanced Metrics
# ============================================================================

def get_layer3_advanced_metrics(monitor) -> Dict[str, Any]:
    """
    Extract Layer 3 advanced metrics from monitor

    Returns:
        Dict with DeepEval, Ragas, and LangSmith metrics
    """
    advanced = {}

    # Get advanced metrics summary from monitor
    if hasattr(monitor, '_advanced_metrics_summary'):
        summary = monitor._advanced_metrics_summary
    elif hasattr(monitor, '_aggregate_advanced_metrics'):
        summary = monitor._aggregate_advanced_metrics()
    else:
        summary = {}

    # DeepEval metrics
    deepeval_metrics = {}
    if 'g_eval_score' in summary:
        deepeval_metrics['g_eval'] = summary['g_eval_score']
    if 'hallucination_score' in summary:
        deepeval_metrics['hallucination'] = summary['hallucination_score']
    if 'toxicity_score' in summary:
        deepeval_metrics['toxicity'] = summary['toxicity_score']
    if 'bias_score' in summary:
        deepeval_metrics['bias'] = summary['bias_score']
    if 'answer_relevancy_score' in summary:
        deepeval_metrics['answer_relevancy'] = summary['answer_relevancy_score']

    if deepeval_metrics:
        advanced['deepeval'] = deepeval_metrics

    # Ragas metrics
    ragas_metrics = {}
    if 'ragas_overall_score' in summary:
        ragas_metrics['overall'] = summary['ragas_overall_score']
    if 'ragas_faithfulness' in summary:
        ragas_metrics['faithfulness'] = summary['ragas_faithfulness']
    if 'ragas_context_precision' in summary:
        ragas_metrics['context_precision'] = summary['ragas_context_precision']
    if 'ragas_context_recall' in summary:
        ragas_metrics['context_recall'] = summary['ragas_context_recall']
    if 'ragas_answer_relevancy' in summary:
        ragas_metrics['answer_relevancy'] = summary['ragas_answer_relevancy']

    if ragas_metrics:
        advanced['ragas'] = ragas_metrics

    return advanced


# ============================================================================
# Security Risk Score Calculation
# ============================================================================

def calculate_security_risk_score(layer1_sec: Dict, layer2_sec: Dict) -> Dict[str, Any]:
    """
    Calculate overall security risk score from Layer 1 & 2 security metrics

    Args:
        layer1_sec: Layer 1 security metrics
        layer2_sec: Layer 2 security metrics

    Returns:
        Dict with risk_score (0-100, lower is better), risk_level, and breakdown
    """
    risk_score = 0.0
    breakdown = {}

    # Layer 1 Input Security Risk (weight: 20%)
    if 'input_security' in layer1_sec:
        threat_rate = layer1_sec['input_security'].get('threat_rate', 0)
        input_risk = threat_rate * 0.20
        risk_score += input_risk
        breakdown['input_security'] = input_risk

    # Layer 1 Output Leakage Risk (weight: 30%)
    if 'output_leakage' in layer1_sec:
        leakage_rate = layer1_sec['output_leakage'].get('leakage_rate', 0)
        leakage_risk = leakage_rate * 0.30
        risk_score += leakage_risk
        breakdown['output_leakage'] = leakage_risk

    # Layer 1 Authorization Risk (weight: 20%)
    if 'authorization' in layer1_sec:
        violation_rate = layer1_sec['authorization'].get('violation_rate', 0)
        auth_risk = violation_rate * 0.20
        risk_score += auth_risk
        breakdown['authorization'] = auth_risk

    # Layer 2 Privilege Escalation Risk (weight: 15%)
    if 'privilege_escalation' in layer2_sec:
        escalation_rate = layer2_sec['privilege_escalation'].get('escalation_rate', 0)
        priv_risk = escalation_rate * 0.15
        risk_score += priv_risk
        breakdown['privilege_escalation'] = priv_risk

    # Layer 2 Attack Detection Risk (weight: 15%)
    if 'attack_detection' in layer2_sec:
        detection_rate = layer2_sec['attack_detection'].get('detection_rate', 0)
        attack_risk = detection_rate * 0.15
        risk_score += attack_risk
        breakdown['attack_detection'] = attack_risk

    # Cap at 100
    risk_score = min(risk_score, 100)

    # Determine risk level
    if risk_score < 20:
        risk_level = "low"
        risk_label = "🟢 낮음 (안전)"
        risk_color = "green"
    elif risk_score < 50:
        risk_level = "medium"
        risk_label = "🟡 중간 (주의)"
        risk_color = "orange"
    else:
        risk_level = "high"
        risk_label = "🔴 높음 (위험)"
        risk_color = "red"

    return {
        'score': risk_score,
        'level': risk_level,
        'label': risk_label,
        'color': risk_color,
        'breakdown': breakdown
    }


# ============================================================================
# Security Alerts Generation
# ============================================================================

def generate_security_alerts(layer1_sec: Dict, layer2_sec: Dict) -> List[Dict[str, Any]]:
    """
    Generate security alerts based on thresholds

    Args:
        layer1_sec: Layer 1 security metrics
        layer2_sec: Layer 2 security metrics

    Returns:
        List of alert dictionaries with level, message, and action
    """
    alerts = []

    # Input Security Alerts
    if 'input_security' in layer1_sec:
        threat_rate = layer1_sec['input_security'].get('threat_rate', 0)
        critical_risks = layer1_sec['input_security'].get('critical_risk', 0)

        if threat_rate > 10:
            alerts.append({
                'level': 'high',
                'category': 'Input Security',
                'message': f'입력 위협 탐지율이 {threat_rate:.1f}%로 높습니다.',
                'action': 'Input Sanitization을 강화하고 WAF 규칙을 검토하세요.',
                'metric_value': threat_rate
            })

        if critical_risks > 0:
            alerts.append({
                'level': 'critical',
                'category': 'Input Security',
                'message': f'치명적 수준의 입력 위협이 {critical_risks}건 탐지되었습니다.',
                'action': '즉시 입력 검증 로직을 강화하고 관리자에게 보고하세요.',
                'metric_value': critical_risks
            })

    # Output Leakage Alerts
    if 'output_leakage' in layer1_sec:
        leakage_rate = layer1_sec['output_leakage'].get('leakage_rate', 0)
        critical_leaks = layer1_sec['output_leakage'].get('critical_leaks', 0)
        api_keys = layer1_sec['output_leakage'].get('api_keys', 0)

        if leakage_rate > 5:
            alerts.append({
                'level': 'critical',
                'category': 'Output Leakage',
                'message': f'출력 유출 탐지율이 {leakage_rate:.1f}%입니다.',
                'action': '출력 필터링을 강화하고 민감정보 마스킹을 적용하세요.',
                'metric_value': leakage_rate
            })

        if api_keys > 0:
            alerts.append({
                'level': 'critical',
                'category': 'Output Leakage',
                'message': f'API 키가 {api_keys}건 유출되었습니다.',
                'action': '유출된 API 키를 즉시 교체하고 접근 로그를 확인하세요.',
                'metric_value': api_keys
            })

    # Authorization Alerts
    if 'authorization' in layer1_sec:
        violation_rate = layer1_sec['authorization'].get('violation_rate', 0)

        if violation_rate > 10:
            alerts.append({
                'level': 'high',
                'category': 'Authorization',
                'message': f'권한 위반율이 {violation_rate:.1f}%입니다.',
                'action': '도구 권한 정책을 검토하고 제한된 도구 접근을 차단하세요.',
                'metric_value': violation_rate
            })

    # Privilege Escalation Alerts
    if 'privilege_escalation' in layer2_sec:
        escalations = layer2_sec['privilege_escalation'].get('escalations_detected', 0)
        high_risk = layer2_sec['privilege_escalation'].get('high_risk_events', 0)

        if escalations > 0:
            alerts.append({
                'level': 'critical',
                'category': 'Privilege Escalation',
                'message': f'권한 상승 시도가 {escalations}건 탐지되었습니다.',
                'action': '도구 체인을 검토하고 권한 상승 경로를 차단하세요.',
                'metric_value': escalations
            })

        if high_risk > 0:
            alerts.append({
                'level': 'critical',
                'category': 'Privilege Escalation',
                'message': f'고위험 권한 상승 이벤트가 {high_risk}건 발생했습니다.',
                'action': '즉시 보안팀에 보고하고 관련 세션을 종료하세요.',
                'metric_value': high_risk
            })

    # Attack Detection Alerts
    if 'attack_detection' in layer2_sec:
        data_exfil = layer2_sec['attack_detection'].get('data_exfiltration', 0)
        lateral_move = layer2_sec['attack_detection'].get('lateral_movement', 0)

        if data_exfil > 0:
            alerts.append({
                'level': 'critical',
                'category': 'Attack Detection',
                'message': f'데이터 유출 시도가 {data_exfil}건 탐지되었습니다.',
                'action': '네트워크 트래픽을 모니터링하고 데이터 전송을 차단하세요.',
                'metric_value': data_exfil
            })

        if lateral_move > 0:
            alerts.append({
                'level': 'high',
                'category': 'Attack Detection',
                'message': f'횡적 이동 패턴이 {lateral_move}건 탐지되었습니다.',
                'action': '시스템 간 이동 경로를 검토하고 접근을 제한하세요.',
                'metric_value': lateral_move
            })

    # Sort by severity
    severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    alerts.sort(key=lambda x: severity_order.get(x['level'], 4))

    return alerts


# ============================================================================
# Helper Functions
# ============================================================================

def has_security_metrics(monitor) -> bool:
    """Check if monitor has security metrics enabled"""
    # Check for live security evaluators
    has_live = any([
        hasattr(monitor, 'input_sanitizer'),
        hasattr(monitor, 'output_leakage_detector'),
        hasattr(monitor, 'tool_authorizer'),
        hasattr(monitor, 'privilege_escalation_detector'),
        hasattr(monitor, 'tool_chain_attack_detector')
    ])

    # Check for loaded security evaluators (from JSON)
    has_loaded = False
    if hasattr(monitor, 'evaluators') and isinstance(monitor.evaluators, dict):
        security_eval = monitor.evaluators.get('security', {})
        has_loaded = bool(security_eval)

    return has_live or has_loaded


def get_all_layer_metrics(monitor) -> Dict[str, Any]:
    """
    Get all metrics organized by layers

    Returns:
        Dict with layer1, layer2, layer3 metrics
    """
    return {
        'layer1': {
            'basic': get_layer1_basic_metrics(monitor),
            'security': get_layer1_security_metrics(monitor)
        },
        'layer2': {
            'agentic': get_layer2_agentic_metrics(monitor),
            'security': get_layer2_security_metrics(monitor)
        },
        'layer3': {
            'advanced': get_layer3_advanced_metrics(monitor)
        }
    }
