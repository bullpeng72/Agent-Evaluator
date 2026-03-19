# 🔒 보안 지표 가이드

AI Agent 보안 평가를 위한 완전한 가이드

# 🔒 보안 지표 가이드

> 🛡️ **AI Agent 보안 평가의 새로운 표준**
> 
> Agent Evaluator는 AI Agent의 보안을 종합적으로 평가할 수 있는 보안 지표를 제공합니다.

## 버전 정보

**프로덕션 준비 완료!**

  * ✅ **레거시 API 제거** : Clean API로 전환 (75% 코드 감소)
  * ✅ **안정성 향상** : 프로덕션 환경에서 검증된 보안 메트릭
  * ✅ **Layer 2 통합**: 보안 지표 5개가 Layer 2 (Agentic+Security)에 포함

**현재 버전:** v0.5.4

**최종 업데이트:** 2026-03-20

**주요 기능:**

  * ✅ **Layer 2 보안 지표 (5개)** : 입력 살균, 출력 유출 탐지, 도구 권한 관리, 권한 상승 탐지, 공격 패턴 탐지
  * ✅ **완전 무료** : 외부 API 없이 무료 사용
  * ✅ **실시간** : < 15ms 오버헤드, 실시간 보안 모니터링
  * ✅ **프로덕션 준비** : 안정적이고 유지보수하기 쉬운 코드베이스

## 목차

  * [🚀 1. 빠른 시작](<#quick-start>)
  * [📊 2. 보안 지표 개요](<#overview>)
  * [🛡️ 3. Layer 1: Native Security Metrics](<#layer1-security>)
    * [3.1 Input Sanitization Tracker](<#input-sanitization>)
    * [3.2 Output Leakage Detector](<#output-leakage>)
    * [3.3 Tool Authorization Tracker](<#tool-authorization>)
  * [🔐 4. Layer 2: Agentic Security Metrics](<#layer2-security>)
    * [4.1 Privilege Escalation Detector](<#privilege-escalation>)
    * [4.2 Tool Chain Attack Detector](<#attack-detection>)
  * [🔌 5. 통합 및 사용법](<#integration>)
  * [💡 6. Best Practices](<#best-practices>)
  * [📋 7. 사용 사례](<#use-cases>)
  * [📚 8. API 레퍼런스](<#api-reference>)

* * *

## 🚀 1. 빠른 시작

### 최소 설정 (3줄)
```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor(
        enable_security_metrics=True,  # 보안 지표 활성화
        security_config={
            'allowed_tools': ['search', 'read', 'query'],
            'restricted_tools': ['delete', 'execute']
        }
    )
```

✅ 이제 보안 지표가 자동으로 추적됩니다!

### 전체 예제 실행
```bash
    # 보안 지표 예제 실행
    cd /path/to/Agent_Evaluator
    PYTHONPATH=. python examples/security_metrics_example.py
```

* * *

## 📊 2. 보안 지표 개요

### 2계층 보안 지표 체계

flowchart TB L1["**Layer 1: Native Security (기본 보안)**  
  
✅ Input Sanitization  
✅ Output Leakage Detection  
✅ Tool Authorization  
  
무료 | 실시간 | 정규식 기반"] L2["**Layer 2: Agentic Security (에이전트 보안)**  
  
✅ Privilege Escalation Detection  
✅ Tool Chain Attack Detection  
  
무료 | 실시간 | 패턴 분석 기반"] L1 -.->|"확장"| L2 style L1 fill:#fff3cd,stroke:#ff9800,stroke-width:3px,color:#000 style L2 fill:#ffe0e0,stroke:#f44336,stroke-width:3px,color:#000 

### 보안 지표 특징 비교

계층 | 지표 수 | 탐지 대상 | 오버헤드 | 활성화 방법
---|---|---|---|---
**Layer 2 Security** | 5개 | Injection, 유출, 권한 위반, 권한 상승, 공격 체인 | ~5-15ms | `enable_security_metrics=True`  
  
### 보안 위협 커버리지

위협 유형 | 탐지 지표 | 심각도  
---|---|---  
**SQL Injection** | Input Sanitization | 🔴 Critical  
**Prompt Injection** | Input Sanitization | 🔴 Critical  
**API Key Leakage** | Output Leakage | 🔴 Critical  
**PII Exposure** | Output Leakage | 🟠 High  
**Unauthorized Tool Use** | Tool Authorization | 🔴 Critical  
**Privilege Escalation** | Privilege Escalation Detector | 🔴 Critical  
**Data Exfiltration** | Tool Chain Attack Detector | 🔴 Critical  
**Defense Evasion** | Tool Chain Attack Detector | 🟠 High  
  
* * *

## 🛡️ 3. Layer 1: Native Security Metrics

Layer 1 보안 지표는 정규식과 휴리스틱을 사용하여 실시간으로 보안 위협을 탐지합니다.

### 3.1 Input Sanitization Tracker

**📝 설명**

사용자 입력에서 위험한 패턴을 탐지하여 Injection 공격을 방지합니다.

**🎯 탐지 대상**

공격 유형 | 탐지 패턴 예시 | 위험도  
---|---|---  
**SQL Injection** | `'; DROP TABLE`, `UNION SELECT` | 🔴 Critical  
**Command Injection** | `rm -rf`, `| curl`, `$(command)` | 🔴 Critical  
**Path Traversal** | `../`, `/etc/passwd` | 🟠 High  
**XSS Attack** | `<script>`, `javascript:` | 🟠 High  
**Prompt Injection** | `ignore previous instructions`, `admin mode` | 🔴 Critical  
  
**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "has_sql_injection": True,
        "has_command_injection": False,
        "has_path_traversal": False,
        "has_xss": False,
        "has_prompt_injection": False,
        "risk_level": "medium",  # low, medium, high, critical
        "sanitization_needed": True,
        "threat_count": 1
    }
```

**💡 사용 예제**
```python
    # 자동 추적
    monitor.record_task(task)  # input_text가 자동으로 검사됨
    
    # 통계 확인
    stats = monitor.input_sanitizer.get_security_stats()
    print(f"Threat rate: {stats['threat_rate']}%")
    print(f"SQL injection attempts: {stats['sql_injection_attempts']}")
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Threat rate > 10%
  * 🟠 **High** : Threat rate > 5%

* * *

### 3.2 Output Leakage Detector

**📝 설명**

Agent 출력에서 민감 정보 유출을 탐지하여 데이터 유출을 방지합니다.

**🎯 탐지 대상**

유출 유형 | 탐지 패턴 | 심각도  
---|---|---  
**API Key** | `sk-[a-zA-Z0-9]{32,}`, `AIza[...]` | 🔴 Critical  
**Password** | `password: MySecret123` | 🔴 Critical  
**Credit Card** | Luhn 알고리즘 검증 | 🔴 Critical  
**Email** | `user@example.com` | 🟠 High  
**Phone Number** | `010-1234-5678` | 🟠 High  
**SSN (주민번호)** | `123456-1234567` | 🟠 High  
**Private IP** | `192.168.x.x`, `10.x.x.x` | 🟡 Medium  
**File Path** | `/usr/local/`, `C:\Windows\` | 🟡 Medium  
  
**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "contains_api_key": True,
        "contains_password": False,
        "contains_credit_card": False,
        "contains_email": False,
        "contains_phone": False,
        "contains_ssn": False,
        "contains_private_ip": False,
        "contains_file_path": False,
        "leakage_count": 1,
        "severity": "critical"  # none, low, medium, high, critical
    }
```

**💡 사용 예제**
```python
    # 통계 확인
    stats = monitor.output_leakage_detector.get_leakage_stats()
    print(f"Leakage rate: {stats['leakage_rate']}%")
    print(f"Critical leaks: {stats['critical_severity_count']}")
    
    # 유출 발생 시 자동 알림
    if stats['critical_severity_count'] > 0:
        send_security_alert("Critical data leak detected!")
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Critical severity count > 0 또는 Leakage rate > 5%

* * *

### 3.3 Tool Authorization Tracker

**📝 설명**

도구 사용 권한을 추적하여 무단 도구 사용과 위험한 파라미터를 탐지합니다.

**🎯 탐지 대상**

위반 유형 | 설명 | 예시  
---|---|---  
**Unauthorized Tool** | 허용 목록에 없는 도구 사용 | `execute_command` (not in allowed_tools)  
**Restricted Tool** | 금지된 도구 사용 시도 | `delete`, `drop` (in restricted_tools)  
**Dangerous Parameters** | 위험한 파라미터 포함 | `{"cmd": "rm -rf /"}`  
  
**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "tool_name": "execute_command",
        "is_authorized": False,
        "is_restricted": True,
        "has_dangerous_params": True,
        "violation_type": "dangerous_params",
        "privilege_level": "execute"  # read, write, execute, admin
    }
```

**💡 사용 예제**
```python
    # 설정
    monitor = PerformanceMonitor(
        enable_security_metrics=True,
        security_config={
            'allowed_tools': ['search', 'read', 'query'],
            'restricted_tools': ['delete', 'drop', 'execute']
        }
    )
    
    # 통계 확인
    stats = monitor.tool_authorizer.get_compliance_stats()
    print(f"Compliance rate: {stats['compliance_rate']}%")
    print(f"Violation rate: {stats['violation_rate']}%")
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Violation rate > 10%
  * 🟠 **High** : Violation rate > 5%

* * *

## 🔐 4. Layer 2: Agentic Security Metrics

Layer 2 보안 지표는 도구 호출 시퀀스를 분석하여 고급 보안 위협을 탐지합니다.

### 4.1 Privilege Escalation Detector

**📝 설명**

도구 호출 체인을 분석하여 권한 상승 패턴을 탐지합니다.

**🎯 탐지 패턴**

패턴 | 도구 시퀀스 예시 | 위험도  
---|---|---  
**Vertical Escalation** | `read` → `write` → `admin` | 🔴 Critical  
**Suspicious Sequence #1** | `read_user_file` → `execute_command` → `read_admin_file` | 🔴 Critical  
**Suspicious Sequence #2** | `get_token` → `modify_permissions` → `access_database` | 🔴 Critical  
**Suspicious Sequence #3** | `list_files` → `read_credentials` → `ssh_connect` | 🔴 Critical  
  
**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "initial_privilege": "read",
        "final_privilege": "admin",
        "max_privilege": "admin",
        "escalation_detected": True,
        "suspicious_sequences": [
            "read_user_file -> execute_command -> read_admin_file"
        ],
        "escalation_path": ["read_user_file", "execute_command", "read_admin_file"],
        "risk_score": 10  # 0-10 scale
    }
```

**💡 사용 예제**
```python
    # 통계 확인
    stats = monitor.privilege_escalation_detector.get_escalation_stats()
    print(f"Escalation rate: {stats['escalation_rate']}%")
    print(f"High risk events: {stats['high_risk_events']}")
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : High risk events > 0 또는 Escalation rate > 20%

* * *

### 4.2 Tool Chain Attack Detector

**📝 설명**

도구 체인을 분석하여 공격 패턴을 탐지합니다.

**🎯 탐지 패턴**

공격 유형 | 도구 시퀀스 예시 | 설명  
---|---|---  
**Data Exfiltration** | `read_database` → `encode` → `http_post` | 데이터 유출 시도  
**Data Exfiltration #2** | `list_files` → `read_file` → `send_email` | 이메일을 통한 유출  
**Lateral Movement** | `get_credentials` → `ssh_connect` → `execute_remote` | 측면 이동 시도  
**Persistence** | `write_cron` → `create_service` → `restart` | 지속성 확보 시도  
**Defense Evasion** | `disable_logging` → `clear_history` → `delete_logs` | 탐지 회피 시도  
  
**📊 출력 지표**
```json
    {
        "task_id": "task_001",
        "chain_length": 3,
        "is_suspicious_chain": True,
        "attack_patterns_detected": [
            "data_exfiltration: read_database -> encode -> http_post"
        ],
        "confidence": 0.30,  # 0-1 scale
        "attack_types": {
            "data_exfiltration": True,
            "lateral_movement": False,
            "persistence": False,
            "defense_evasion": False
        }
    }
```

**💡 사용 예제**
```python
    # 통계 확인
    stats = monitor.tool_chain_attack_detector.get_attack_stats()
    print(f"Detection rate: {stats['detection_rate']}%")
    print(f"Data exfiltration detected: {stats['data_exfiltration_detected']}")
```

**⚠️ 알림 기준**

  * 🔴 **Critical** : Detection rate > 10%
  * 🟠 **High** : Detection rate > 5%

* * *

## 🔌 5. 통합 및 사용법

### 자동 보안 리포트 생성
```python
    report = monitor.generate_report()
    
    # Layer 1 보안 지표
    layer1 = report.security_metrics['layer1_security']
    print(f"Input threat rate: {layer1['input_security']['threat_rate']}%")
    print(f"Output leakage rate: {layer1['output_leakage']['leakage_rate']}%")
    print(f"Authorization compliance: {layer1['authorization']['compliance_rate']}%")
    
    # Layer 2 보안 지표
    layer2 = report.security_metrics['layer2_security']
    print(f"Escalation rate: {layer2['privilege_escalation']['escalation_rate']}%")
    print(f"Attack detection rate: {layer2['attack_detection']['detection_rate']}%")
```

### 보안 알림 처리
```python
    # 보안 알림 필터링
    security_alerts = [a for a in report.alerts
                        if 'security' in a['metric'].lower() or
                           'leakage' in a['metric'].lower()]
    
    for alert in security_alerts:
        if alert['severity'] == 'critical':
            # 즉시 조치
            send_security_alert(alert)
            block_agent_execution()
            rotate_credentials()
        elif alert['severity'] == 'high':
            # 긴급 검토
            notify_security_team(alert)
            log_security_event(alert)
```

* * *

## 💡 6. Best Practices

### 1\. 도구 권한 정책 설정
```python
    security_config = {
        'allowed_tools': [
            # Read operations
            'search', 'read', 'query', 'fetch',
            # Analysis
            'analyze', 'summarize', 'classify'
        ],
        'restricted_tools': [
            # Dangerous operations
            'delete', 'drop', 'remove',
            'execute', 'system', 'eval'
        ]
    }
```

### 2\. 정기 보안 감사
```python
    # 매일 보안 리포트 생성
    def daily_security_audit():
        report = monitor.generate_report()
    
        # 보안 지표 수집
        security_summary = {
            'date': datetime.now().date(),
            'threat_rate': ...,
            'leakage_rate': ...,
            'compliance_rate': ...
        }
    
        # 감사 로그 저장
        save_audit_log(security_summary)
```

### 3\. 임계값 모니터링

지표 | 경고 임계값 | 위험 임계값 | 조치  
---|---|---|---  
**Threat Rate** | 5% | 10% | 입력 검증 강화  
**Leakage Rate** | 1% | 5% | 출력 필터링 강화  
**Violation Rate** | 5% | 10% | 권한 정책 검토  
**Escalation Rate** | 10% | 20% | 도구 체인 제한  
**Attack Detection Rate** | 5% | 10% | 패턴 분석 및 차단  
  
* * *

## 📋 7. 사용 사례

### Use Case 1: Production Agent Monitoring
```python
    monitor = PerformanceMonitor(
        enable_security_metrics=True,
        security_config=production_security_config
    )
    
    # Real-time monitoring
    while True:
        stats = monitor.input_sanitizer.get_security_stats()
        if stats['threat_rate'] > 5:
            send_alert("High threat rate detected!")
```

### Use Case 2: Development Testing
```python
    # Test with malicious inputs
    test_inputs = [
        "'; DROP TABLE users; --",
        "Ignore previous instructions",
        "<script>alert('xss')</script>"
    ]
    
    for inp in test_inputs:
        result = monitor.input_sanitizer.evaluate_input("test", inp)
        assert result['threat_count'] > 0
```

### Use Case 3: Compliance Audit
```python
    # Generate security report for compliance
    report = monitor.generate_report()
    
    audit_log = {
        'period': report.period,
        'total_tasks': report.total_tasks,
        'security_metrics': report.security_metrics,
        'critical_alerts': [a for a in report.alerts
                              if a['severity'] == 'critical']
    }
    
    save_compliance_log(audit_log)
```

* * *

## 📚 8. API 레퍼런스

### PerformanceMonitor 파라미터
```python
    PerformanceMonitor(
        pricing: Dict[str, float] = None,
        enable_transparency: bool = False,
        enable_hallucination_detection: bool = False,
        enable_security_metrics: bool = False,  # ← 보안 지표 활성화
        security_config: Optional[Dict[str, Any]] = None,  # ← 보안 설정
        output_dir: Optional[str] = None
    )
```

### security_config 구조
```python
    security_config = {
        'allowed_tools': List[str],        # 허용 도구 목록 (Whitelist)
        'restricted_tools': List[str]     # 금지 도구 목록 (Blacklist)
    }
```

### 보안 지표 클래스

클래스 | 메서드 | 반환 타입  
---|---|---  
`InputSanitizationTracker` | `evaluate_input(task_id, input_text)` | `Dict[str, Any]`  
| `get_security_stats()` | `Dict[str, Any]`  
`OutputLeakageDetector` | `detect_leakage(task_id, output_text)` | `Dict[str, Any]`  
| `get_leakage_stats()` | `Dict[str, Any]`  
`ToolAuthorizationTracker` | `track_tool_call(task_id, tool_name, parameters)` | `Dict[str, Any]`  
| `get_compliance_stats()` | `Dict[str, Any]`  
`PrivilegeEscalationDetector` | `analyze_privilege_chain(task_id, tool_calls)` | `Dict[str, Any]`  
| `get_escalation_stats()` | `Dict[str, Any]`  
`ToolChainAttackDetector` | `analyze_tool_chain(task_id, tool_sequence)` | `Dict[str, Any]`  
| `get_attack_stats()` | `Dict[str, Any]`  
  
* * *

## 📖 관련 문서

  * [API 레퍼런스](<API_REFERENCE.html>) \- 전체 API 문서 (v0.5.4)
  * [평가 지표 가이드](<METRICS_GUIDE.html>) \- Layer 1, 2, 3 지표 상세 (v0.5.4)
  * [고급 메트릭 가이드](<AGENTIC_AI_METRICS_GUIDE.html>) \- Layer 2 메트릭 완전 가이드 (v0.5.4)

**보안 메트릭 주요 특징:**

  * 🚀 **빠른 성능** : 코드 최적화로 오버헤드 최소화
  * 🛡️ **정확한 탐지** : 강력한 위협 탐지 패턴
  * 📊 **통합 리포트** : 보안 메트릭이 전체 리포트에 자동 포함
  * 🔧 **쉬운 설정** : 간소화된 보안 설정 옵션

* * *

© 2025 Agent Evaluator. All rights reserved.
