#!/usr/bin/env python3
"""Book markdown → single HTML converter with Mermaid diagram injection."""

import re
from pathlib import Path

import markdown as md_lib

BOOK_DIR = Path(__file__).parent
OUTPUT_FILE = BOOK_DIR / "agent-evaluator-book.html"

# ── 변환 순서 ──────────────────────────────────────────────────────────────────
ORDERED_FILES = [
    BOOK_DIR / "README.md",
    BOOK_DIR / "00_서문.md",
    BOOK_DIR / "Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md",
    BOOK_DIR / "Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_04_GroupA_목표달성.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_05_GroupB_행동무결성.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_06_GroupC_신뢰성.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_07_GroupD_성능계약.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_08_GroupE_보안경계.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_09_GroupF_다중에이전트.md",
    BOOK_DIR / "Part_II_지표시스템/Chapter_10_GroupG_운영관측성.md",
    BOOK_DIR / "Part_III_개발자가이드/Chapter_11_평가데이터_설계.md",
    BOOK_DIR / "Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md",
    BOOK_DIR / "Part_III_개발자가이드/Chapter_13_프레임워크_통합.md",
    BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md",
    BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_15_대시보드_시각화.md",
    BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_16_알림시스템_운영.md",
    BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_17_주간월간_품질리뷰.md",
    BOOK_DIR / "Part_V_프로덕션운영/Chapter_18_CICD_품질게이팅.md",
    BOOK_DIR / "Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md",
    BOOK_DIR / "Part_V_프로덕션운영/Chapter_20_프로덕션_배포전략.md",
    BOOK_DIR / "Part_V_프로덕션운영/Chapter_21_종합_실무파이프라인.md",
    BOOK_DIR / "Appendix/A_58개지표_레퍼런스.md",
    BOOK_DIR / "Appendix/B_CLI_명령어_레퍼런스.md",
    BOOK_DIR / "Appendix/C_환경변수_설정_레퍼런스.md",
    BOOK_DIR / "Appendix/D_프레임워크_호환성_매트릭스.md",
    BOOK_DIR / "Appendix/E_에러코드_트러블슈팅.md",
    BOOK_DIR / "Appendix/F_용어사전.md",
    BOOK_DIR / "Appendix/G_AI평가_이론적기초.md",
    BOOK_DIR / "Appendix/H_알고리즘_수학적_레퍼런스.md",
    BOOK_DIR / "Appendix/I_지표_비교분석_선택가이드.md",
    BOOK_DIR / "Appendix/J_프로덕션_실패패턴_카탈로그.md",
    BOOK_DIR / "Appendix/K_적대적_강건성과_레드팀_평가.md",
    BOOK_DIR / "Appendix/L_예산최적화_평가설계.md",
]

# ── 섹션별 Mermaid 다이어그램 주입 ──────────────────────────────────────────────
# key: 파일명 stem, value: (앵커 문자열, mermaid 블록) — 앵커 다음 줄에 삽입
MERMAID_INJECTIONS: dict[str, list[tuple[str, str]]] = {
    "README": [
        (
            "## 책 구성",
            """@@HTML_START@@
<div class="book-map">
  <div class="bm-arrow-row">
    <div class="bm-part" style="--part-color:#1a237e">
      <div class="bm-part-title">Part I<span>기초</span></div>
      <a href="#ch01" class="bm-ch">Ch01<small>AI 에이전트 평가란?</small></a>
      <a href="#ch02" class="bm-ch">Ch02<small>Agent-Evaluator 첫 시작</small></a>
    </div>
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#00695c">
      <div class="bm-part-title">Part II<span>지표 시스템</span></div>
      <a href="#ch03" class="bm-ch">Ch03<small>Harness Engineering 기초</small></a>
      <a href="#ch04" class="bm-ch">Ch04<small>Gate A — 목표달성</small></a>
      <a href="#ch05" class="bm-ch">Ch05<small>Gate B — 행동무결성</small></a>
      <a href="#ch06" class="bm-ch">Ch06<small>Gate C — 신뢰성</small></a>
      <a href="#ch07" class="bm-ch">Ch07<small>Gate D — 성능계약</small></a>
      <a href="#ch08" class="bm-ch">Ch08<small>Gate E — 보안경계</small></a>
      <a href="#ch09" class="bm-ch">Ch09<small>Gate F — 다중에이전트</small></a>
      <a href="#ch10" class="bm-ch">Ch10<small>Gate G — 운영관측성</small></a>
    </div>
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#4527a0">
      <div class="bm-part-title">Part III<span>개발자 가이드</span></div>
      <a href="#ch11" class="bm-ch">Ch11<small>평가데이터 설계</small></a>
      <a href="#ch12" class="bm-ch">Ch12<small>데코레이터 완전정복</small></a>
      <a href="#ch13" class="bm-ch">Ch13<small>프레임워크 통합</small></a>
    </div>
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#e65100">
      <div class="bm-part-title">Part IV<span>QA 관리자</span></div>
      <a href="#ch14" class="bm-ch">Ch14<small>임계값 & 품질기준</small></a>
      <a href="#ch15" class="bm-ch">Ch15<small>대시보드 시각화</small></a>
      <a href="#ch16" class="bm-ch">Ch16<small>알림시스템 운영</small></a>
      <a href="#ch17" class="bm-ch">Ch17<small>주간·월간 품질리뷰</small></a>
    </div>
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#b71c1c">
      <div class="bm-part-title">Part V<span>프로덕션 운영</span></div>
      <a href="#ch18" class="bm-ch">Ch18<small>CI/CD 품질게이팅</small></a>
      <a href="#ch19" class="bm-ch">Ch19<small>Phoenix OTEL 모니터링</small></a>
      <a href="#ch20" class="bm-ch">Ch20<small>프로덕션 배포전략</small></a>
      <a href="#ch21" class="bm-ch">Ch21<small>종합 실무파이프라인</small></a>
    </div>
  </div>
</div>
@@HTML_END@@
""",
        )
    ],
    "Chapter_03_Harness_Engineering_기초": [
        (
            "## 3.1",
            """@@HTML_START@@
<div class="he-flow">
  <div class="he-box">
    <div class="he-box-title">Harness Engineering</div>
    <div class="he-elements">
      <div class="he-elem"><span class="he-icon">🔍</span><strong>Tracker</strong><small>(관찰·측정)</small></div>
      <span class="he-arr">→</span>
      <div class="he-elem"><span class="he-icon">📋</span><strong>Config</strong><small>(기준 선언)</small></div>
      <span class="he-arr">→</span>
      <div class="he-elem"><span class="he-icon">🚦</span><strong>Gate</strong><small>(배포 판정)</small></div>
    </div>
  </div>
  <span class="he-main-arr">⟶</span>
  <div class="he-gates">
    <div class="he-gates-title">7개 Harness Gate</div>
    <div class="he-gate-list">
      <div class="he-gate ga">Gate A<small>목표달성</small></div>
      <div class="he-gate gb">Gate B<small>행동무결성</small></div>
      <div class="he-gate gc">Gate C<small>신뢰성</small></div>
      <div class="he-gate gd">Gate D<small>성능계약</small></div>
      <div class="he-gate ge">Gate E<small>보안경계</small></div>
      <div class="he-gate gf">Gate F<small>다중에이전트</small></div>
      <div class="he-gate gg">Gate G<small>운영관측성</small></div>
    </div>
  </div>
  <span class="he-main-arr">⟶</span>
  <div class="he-outcomes">
    <div class="he-pass">✅ PASS<small>배포 승인</small></div>
    <div class="he-fail">❌ FAIL<small>배포 차단</small></div>
  </div>
</div>
@@HTML_END@@
""",
        ),
        (
            "### 3.1.2",
            """@@HTML_START@@
<div class="gs-wrap">
  <div class="gs-agent">
    <div class="gs-agent-box">AI 에이전트 실행</div>
  </div>
  <div class="gs-mid">
    <!-- Guides 열 -->
    <div class="gs-col">
      <div class="gs-panel gs-guide-panel">
        <div class="gs-panel-title">Guides</div>
        <div class="gs-panel-sub">사전 제어 (Feedforward) — 실행 전 제약 선언</div>
        <div class="gs-items">
          <div class="gs-item">InstructionConfig</div>
          <div class="gs-item">SLAConfig</div>
          <div class="gs-item">ComplianceConfig</div>
          <div class="gs-item">LoopDetectionConfig</div>
          <div class="gs-item">ThreatSeverityConfig</div>
          <div class="gs-item">ScopeConfig</div>
        </div>
      </div>
    </div>
    <!-- 중앙 실행 화살표 -->
    <div class="gs-center-col">
      <div class="gs-arrow-v">↓</div>
      <div class="gs-exe-label">실행</div>
      <div class="gs-arrow-v">↓</div>
    </div>
    <!-- Sensors 열 -->
    <div class="gs-col">
      <div class="gs-panel gs-sensor-panel">
        <div class="gs-panel-title">Sensors</div>
        <div class="gs-panel-sub">사후 제어 (Feedback) — 실행 후 측정·검증</div>
        <div class="gs-items">
          <div class="gs-item">AccuracyEvaluator</div>
          <div class="gs-item">LatencyTracker</div>
          <div class="gs-item">HallucinationDetector</div>
          <div class="gs-item">InputSanitizationTracker</div>
          <div class="gs-item">OutputLeakageDetector</div>
          <div class="gs-item">TokenEconomyTracker</div>
        </div>
      </div>
    </div>
  </div>
  <!-- Gate 판정 -->
  <div class="gs-gate-row">
    <div class="gs-gate-box">
      <div class="gs-gate-title">Gate 판정 (A–G) — Guides × Sensors 통합 검증</div>
      <div class="gs-verdicts">
        <span class="gs-pass">✅ PASS</span>
        <span class="gs-warn">⚠️ WARNING</span>
        <span class="gs-fail">❌ FAIL</span>
      </div>
    </div>
  </div>
</div>
@@HTML_END@@
""",
        ),
        (
            "세 요소가 결합하면",
            """@@HTML_START@@
<div class="pip-wrap">
  <div class="pip-title">배포 검증 파이프라인</div>
  <div class="pip-body">
    <div class="pip-left">
      <div class="pip-box pip-config">
        <span class="pip-icon">📋</span>
        <strong>Config</strong>
        <span class="pip-sub">기준 선언</span>
      </div>
      <div class="pip-down-arr">↓</div>
      <div class="pip-box pip-tracker">
        <span class="pip-icon">🔍</span>
        <strong>Tracker</strong>
        <span class="pip-sub">측정</span>
      </div>
    </div>
    <div class="pip-right-arr">→</div>
    <div class="pip-box pip-gate">
      <span class="pip-icon">🚦</span>
      <strong>Gate</strong>
      <span class="pip-sub">판정</span>
    </div>
    <div class="pip-right-arr">→</div>
    <div class="pip-verdicts">
      <div class="pip-pass">✅ PASS</div>
      <div class="pip-warn">⚠️ WARNING</div>
      <div class="pip-fail">❌ FAIL</div>
    </div>
  </div>
</div>
@@HTML_END@@
""",
        ),
        (
            "## 3.2",
            """@@HTML_START@@
<div class="te-outer">
  <div class="te-title">Harness Engineering</div>
  <div class="te-inner">
    <div class="te-card te-tracker">
      <div class="te-icon">🔍</div>
      <div class="te-name">Tracker</div>
      <div class="te-sub">(관찰/측정)</div>
      <div class="te-q">"무슨 일이 일어났나?"</div>
    </div>
    <div class="te-arrow">→</div>
    <div class="te-card te-config">
      <div class="te-icon">📋</div>
      <div class="te-name">Config</div>
      <div class="te-sub">(기준 선언)</div>
      <div class="te-q">"어떤 수치면 배포 가능한가?"</div>
    </div>
    <div class="te-arrow">→</div>
    <div class="te-card te-gate">
      <div class="te-icon">🚦</div>
      <div class="te-name">Gate</div>
      <div class="te-sub">(배포 판정)</div>
      <div class="te-q">"지금 배포해도 되는가?"</div>
    </div>
  </div>
</div>
@@HTML_END@@
""",
        ),
        (
            "## 3.3",
            """```mermaid
flowchart TD
    REC["record_task(TaskResult)"]
    REC --> L1["Layer 1 집계\nTCR · Accuracy · Hallucination\nQuality · Latency · Token"]
    REC --> L2["Layer 2 집계\nToolCall · Retry · Security\nCoordination · Workflow"]
    L1 --> HC["Harness Config 평가\n33개 Config 임계값 대조"]
    L2 --> HC
    HC --> GA["Gate A\n목표달성"]
    HC --> GB["Gate B\n행동무결성"]
    HC --> GC["Gate C\n신뢰성"]
    HC --> GD["Gate D\n성능계약"]
    HC --> GE["Gate E\n보안경계"]
    HC --> GF["Gate F\n다중에이전트"]
    HC --> GG["Gate G\n운영관측성"]
    GA & GB & GC & GD & GE & GF & GG --> RPT["generate_report()\nsave_to_file()"]
    RPT --> JSON["result.json"]
    RPT --> HTML["result.html"]
```
""",
        ),
    ],
    "Chapter_09_GroupF_다중에이전트": [
        (
            "## 9.1",
            """```mermaid
sequenceDiagram
    participant U as User
    participant O as Orchestrator
    participant R as Researcher
    participant A as Analyst
    participant W as Writer
    U->>O: 요청
    O->>R: 정보 수집 위임
    R-->>O: 수집 결과 (127억, +34.2%)
    O->>A: 분석 위임
    Note over O,A: PropagationConfig 감시: 수치 왜곡?
    A-->>O: 분석 결과
    O->>W: 보고서 작성 위임
    Note over O,W: AgentRoleConfig 감시: 역할 준수?
    W-->>O: 초안
    O-->>U: 최종 결과
    Note over O: ConsensusConfig: 합의율 측정
```
""",
        )
    ],
    "Chapter_18_CICD_품질게이팅": [
        (
            "## 18.1",
            """```mermaid
flowchart LR
    PR["PR / Push"] --> BUILD["빌드"]
    BUILD --> EVAL["python ch18_cicd_gate.py\n평가 실행"]
    EVAL --> GATE["agent-eval gate\nresult.json --tcr 85"]
    GATE --> PASS{"Gate\n판정"}
    PASS -->|"PASS\nexit 0"| MERGE["✅ 머지 / 배포 허용"]
    PASS -->|"FAIL\nexit 1"| BLOCK["❌ 배포 차단\n알림 발송"]
    BLOCK --> FIX["수정 후 재시도"]
    FIX --> EVAL
    style MERGE fill:#c8e6c9
    style BLOCK fill:#ffcdd2
```
""",
        ),
        (
            "## 18.4",
            """```mermaid
flowchart TD
    subgraph CI["CI 파이프라인"]
        RUN["평가 실행\nch18_cicd_gate.py"]
        GATE["HarnessEvaluationGate.enforce()"]
        TREND["agent-eval trend\n--fail-on-regression"]
    end
    RUN --> GATE
    RUN --> RESULT["result.json"]
    RESULT --> TREND
    GATE --> |"PASS"| DEPLOY["배포 단계"]
    GATE --> |"FAIL"| HALT["파이프라인 중단\nexit 1"]
    TREND --> |"회귀 없음"| DEPLOY
    TREND --> |"회귀 감지"| HALT
    DEPLOY --> CANARY["카나리 배포\n10% 트래픽"]
    CANARY --> FULL["전체 배포\n100% 트래픽"]
    style HALT fill:#ffcdd2
    style FULL fill:#c8e6c9
```
""",
        ),
    ],
    "Chapter_19_Phoenix_OTEL_모니터링": [
        (
            "## 19.1",
            """```mermaid
flowchart LR
    subgraph SDK["Agent-Evaluator SDK"]
        AE["@agent_eval\n데코레이터"]
        PM["PerformanceMonitor"]
        OTEL["setup_otel()\nOTELProvider"]
    end
    subgraph Transport["OTLP/HTTP"]
        SPAN["Span\nae.* 속성 25개"]
    end
    subgraph Phoenix["Arize Phoenix"]
        TRACE["Traces 뷰"]
        DS["Datasets 뷰"]
        PG["Playground\nPrompt 실험"]
        GQL["GraphQL API"]
    end
    AE --> PM --> OTEL --> SPAN --> Phoenix
    TRACE --> DS
    GQL --> DS
    style Phoenix fill:#e8eaf6
    style SDK fill:#e8f5e9
```
""",
        )
    ],
    "Chapter_20_프로덕션_배포전략": [
        (
            "## 20.1",
            """```mermaid
flowchart TD
    subgraph V1["v1 레거시 에이전트"]
        V1A["Gate D FAIL\nSLA 초과"]
        V1B["Gate F FAIL\n합의율 낮음"]
        V1C["Gate G FAIL\n추론 설명 부족"]
    end
    subgraph V2["v2 개선 에이전트"]
        V2A["Gate D PASS\n+23.9%"]
        V2B["Gate F PASS\n+67%"]
        V2C["Gate G PASS\n+50%"]
    end
    COMPARE["ch20_deployment.py\nGate 점수 비교"]
    V1 --> COMPARE
    V2 --> COMPARE
    COMPARE --> DECISION{"종합 점수\n비교"}
    DECISION --> |"v2 우위"| DEPLOY["✅ v2 배포 승인"]
    DECISION --> |"차이 미미"| HOLD["⏸ 추가 검증"]
    style DEPLOY fill:#c8e6c9
    style HOLD fill:#fff9c4
    style V1 fill:#ffebee
    style V2 fill:#e8f5e9
```
""",
        )
    ],
    "Chapter_21_종합_실무파이프라인": [
        (
            "## 21.1",
            """```mermaid
flowchart TD
    subgraph DEV["🛠️ 개발 단계"]
        direction LR
        E01["ch01\nLayer 1 기초"]
        E12["ch12\n데코레이터"]
        E13["ch13\n프레임워크"]
    end
    subgraph QA["🔍 QA 단계"]
        direction LR
        E04["ch04\nGate A~G FAIL 검증"]
        E16["ch16\n알림 연동"]
        E17["ch17\n주간 리뷰"]
    end
    subgraph PROD["🚀 프로덕션 단계"]
        direction LR
        E18["ch18\nCI/CD Gate"]
        E19["ch19\nPhoenix OTEL"]
        E20["ch20\n버전 비교"]
    end
    DEV --> QA --> PROD
    PROD --> GATE{"Gate\n판정"}
    GATE --> |"exit 0 ✅"| LIVE["Live 배포"]
    GATE --> |"exit 1 ❌"| FIX["수정 후 재시도"]
    FIX --> DEV
    style LIVE fill:#c8e6c9,color:#1b5e20
    style FIX fill:#ffcdd2,color:#b71c1c
    style DEV fill:#e8f5e9
    style QA fill:#e3f2fd
    style PROD fill:#fff3e0
```
""",
        )
    ],
    "A_58개지표_레퍼런스": [
        (
            "## A.1",
            """```mermaid
graph TB
    subgraph A["Gate A — Goal Achievement"]
        A1["InstructionConfig"]
        A2["GoalAlignmentConfig"]
        A3["PlanConfig"]
        A4["SubtaskConfig"]
        A5["ContextRetentionConfig"]
        A6["KnowledgeRetentionConfig"]
    end
    subgraph B["Gate B — Behavioral Integrity"]
        B1["LoopDetectionConfig"]
        B2["ScopeConfig"]
        B3["ToolParameterSafetyConfig"]
        B4["ContextWindowConfig"]
        B5["StateConsistencyConfig"]
        B6["DeadlockConfig"]
    end
    subgraph C["Gate C — Reliability"]
        C1["ReproducibilityConfig"]
        C2["FaultToleranceConfig"]
        C3["GracefulDegradationConfig"]
        C4["RetryConsistencyConfig"]
        C5["IdempotencyConfig"]
    end
    subgraph D["Gate D — Performance Contract"]
        D1["SLAConfig"]
        D2["EfficiencyConfig"]
        D3["ResourceBudgetConfig"]
        D4["TTFTVariabilityConfig"]
        D5["CostPredictabilityConfig"]
    end
    subgraph E["Gate E — Security Boundary"]
        E1["ThreatSeverityConfig"]
        E2["ComplianceConfig"]
        E3["ThreatResponseConfig"]
    end
    subgraph F["Gate F — Multi-Agent"]
        F1["ConsensusConfig"]
        F2["PropagationConfig"]
        F3["AgentRoleConfig"]
        F4["ConflictResolutionConfig"]
    end
    subgraph G["Gate G — Observability"]
        G1["ExplainabilityConfig"]
        G2["ObservabilityConfig"]
        G3["ErrorDiagnosisConfig"]
        G4["LatencyAttributionConfig"]
    end
    style A fill:#e8f5e9
    style B fill:#e3f2fd
    style C fill:#fff3e0
    style D fill:#fce4ec
    style E fill:#f3e5f5
    style F fill:#e8eaf6
    style G fill:#e0f7fa
```
""",
        )
    ],
}

# ── HTML 템플릿 ──────────────────────────────────────────────────────────────────
HTML_HEAD = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 에이전트 Harness Engineering 실무 가이드 — Agent-Evaluator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Noto+Serif+KR:wght@400;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/bash.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/yaml.min.js"></script>
<style>
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --primary: #1a237e;
  --primary-light: #3949ab;
  --accent: #00897b;
  --accent-light: #4db6ac;
  --warn: #f57f17;
  --danger: #c62828;
  --success: #2e7d32;
  --bg: #fafafa;
  --surface: #ffffff;
  --border: #e0e0e0;
  --text: #212121;
  --text-secondary: #616161;
  --code-bg: #f5f5f5;
  --sidebar-w: 280px;
  --font-body: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
  --font-serif: 'Noto Serif KR', serif;
  /* JetBrains Mono: 코드, Noto Sans Mono: CJK 혼용 폴백 */
  --font-mono: 'JetBrains Mono', 'Noto Sans Mono', 'Menlo', monospace;
}

html { scroll-behavior: smooth; font-size: 16px; }
body {
  font-family: var(--font-body);
  color: var(--text);
  background: var(--bg);
  line-height: 1.8;
  display: flex;
}

/* ── Sidebar TOC ── */
#sidebar {
  position: fixed;
  top: 0; left: 0;
  width: var(--sidebar-w);
  height: 100vh;
  overflow-y: auto;
  background: var(--primary);
  color: #fff;
  padding: 0;
  z-index: 100;
  font-size: 0.8rem;
}
#sidebar-header {
  padding: 20px 16px 12px;
  background: rgba(0,0,0,0.25);
  font-family: var(--font-serif);
  font-size: 0.85rem;
  font-weight: 700;
  line-height: 1.4;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
#sidebar-header small { display: block; font-size: 0.7rem; font-weight: 300; opacity: 0.75; margin-top: 4px; }
#toc { padding: 8px 0 40px; }
#toc a {
  display: block;
  padding: 4px 16px;
  color: rgba(255,255,255,0.8);
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  line-height: 1.4;
}
#toc a:hover { background: rgba(255,255,255,0.1); color: #fff; }
#toc a.part-heading {
  padding: 10px 16px 4px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.45);
  cursor: default;
}
#toc a.chapter { padding-left: 24px; font-size: 0.78rem; }
#toc a.appendix { padding-left: 24px; font-size: 0.75rem; color: rgba(255,255,255,0.65); }
#toc a.active { background: rgba(255,255,255,0.15); color: #fff; font-weight: 500; }

/* ── Main content ── */
#main {
  margin-left: var(--sidebar-w);
  min-height: 100vh;
  width: calc(100% - var(--sidebar-w));
  max-width: 900px;
  padding: 0 48px 80px 48px;
}

/* ── Chapter sections ── */
.chapter-section {
  border-top: 3px solid var(--primary);
  margin-top: 64px;
  padding-top: 48px;
}
.chapter-section:first-of-type { border-top: none; margin-top: 0; padding-top: 40px; }
.part-divider {
  margin: 80px 0 0;
  padding: 20px 0 10px;
  border-top: 1px solid var(--border);
}
.part-divider h2 {
  font-family: var(--font-serif);
  font-size: 1.4rem;
  color: var(--primary);
  letter-spacing: 0.02em;
}

/* ── Typography ── */
h1, h2, h3, h4, h5, h6 { font-family: var(--font-serif); line-height: 1.35; }
h1 { font-size: 2.2rem; color: var(--primary); margin: 40px 0 20px; padding-bottom: 12px; border-bottom: 2px solid var(--primary); }
h2 { font-size: 1.55rem; color: var(--primary-light); margin: 36px 0 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.2rem; color: var(--text); margin: 28px 0 10px; }
h4 { font-size: 1.05rem; color: var(--text); margin: 20px 0 8px; }
h5, h6 { font-size: 0.95rem; color: var(--text-secondary); margin: 16px 0 6px; }

p { margin: 0 0 14px; }
ul, ol { margin: 0 0 14px 24px; }
li { margin: 4px 0; }
ul li ul { margin-top: 4px; }

strong { color: var(--primary); font-weight: 700; }
em { font-style: italic; }

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }

/* ── Code ── */
code {
  font-family: var(--font-mono);
  font-size: 0.84em;
  background: #fff0f0;
  color: #c0392b;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid #ffd5d5;
}
pre {
  background: #282c34;  /* atom-one-dark base */
  border-radius: 10px;
  padding: 20px 22px;
  overflow-x: auto;
  margin: 16px 0 22px;
  position: relative;
  font-size: 0.84rem;
  line-height: 1.65;
  border: 1px solid #3a3f4b;
  box-shadow: 0 2px 8px rgba(0,0,0,0.18);
}
pre code {
  background: transparent !important;
  color: #abb2bf !important;  /* atom-one-dark default text */
  padding: 0;
  font-size: inherit;
  border-radius: 0;
  border: none;
}
/* hljs 오버라이드 — 배경 투명, 텍스트 선명 */
.hljs {
  background: transparent !important;
  color: #abb2bf !important;
  padding: 0 !important;
}
/* 주석: 선명한 회록색 */
.hljs-comment, .hljs-quote { color: #7c8899 !important; font-style: italic; }
/* 키워드: 보라 */
.hljs-keyword, .hljs-selector-tag, .hljs-built_in { color: #c678dd !important; font-weight: 500; }
/* 문자열: 초록 */
.hljs-string, .hljs-attr { color: #98c379 !important; }
/* 숫자: 주황 */
.hljs-number, .hljs-literal { color: #d19a66 !important; }
/* 함수명: 하늘 */
.hljs-title, .hljs-title.function_, .hljs-function .hljs-title { color: #61afef !important; }
/* 클래스명: 노란 */
.hljs-class .hljs-title, .hljs-title.class_ { color: #e5c07b !important; }
/* 변수·파라미터: 연한 빨강 */
.hljs-variable, .hljs-params { color: #e06c75 !important; }
/* 데코레이터·메타 */
.hljs-meta { color: #61afef !important; }
/* 연산자·구두점 */
.hljs-operator, .hljs-punctuation { color: #abb2bf !important; }
/* 인라인 코드 안의 strong 색 복원 */
pre strong { color: #e5c07b; }

/* ── Tables ── */
.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 16px 0 22px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0;
  font-size: 0.88rem;
  overflow: hidden;
  border-radius: 8px;
}
th {
  background: var(--primary);
  color: #fff;
  padding: 10px 14px;
  text-align: left;
  font-weight: 500;
  font-size: 0.83rem;
  white-space: nowrap;
}
td { padding: 9px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; white-space: nowrap; }
tr:last-child td { border-bottom: none; }
tr:nth-child(even) td { background: #f8f9ff; }
tr:hover td { background: #eef0fb; }

/* ── Blockquote (callouts) ── */
blockquote {
  border-left: 4px solid var(--accent);
  background: #e0f2f1;
  padding: 12px 18px;
  margin: 16px 0;
  border-radius: 0 8px 8px 0;
  font-size: 0.93rem;
}
blockquote p { margin-bottom: 6px; }
blockquote p:last-child { margin-bottom: 0; }
blockquote strong { color: var(--accent); }
blockquote code { background: rgba(0,0,0,0.06); }

/* ── TIP box (개발자·QA·DevOps TIP callout) ── */
.tip-box {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 12px 18px;
  margin: 16px 0;
  border-radius: 0 8px 8px 0;
  font-size: 0.93rem;
}
.tip-box p { margin-bottom: 6px; }
.tip-box p:last-child { margin-bottom: 0; }
.tip-box strong { color: #b45309; }
.tip-box code { background: rgba(0,0,0,0.06); }

/* ── Mermaid diagrams ── */
.mermaid {
  background: #f8f9ff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  margin: 20px 0 24px;
  text-align: center;
  overflow-x: auto;
}

/* ── Badge / pill ── */
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.73rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.badge-pass { background: #c8e6c9; color: #1b5e20; }
.badge-fail { background: #ffcdd2; color: #b71c1c; }
.badge-warn { background: #fff9c4; color: #f57f17; }

/* ── Preformatted box (ASCII art) ── */
.box-art pre, pre.box {
  background: #263238;
  border-left: 4px solid var(--accent);
  font-size: 0.8rem;
}

/* ── Plain code (언어 미지정 / text 블록) — 모든 토큰 색상 제거 ── */
pre code.plain-code,
pre code.plain-code * {
  color: #abb2bf !important;   /* 단색 — hljs 토큰 오착색 차단 */
  font-style: normal !important;
  font-weight: normal !important;
}
/* CJK 혼용 모노스페이스 정렬 보조
   한글(2칸)과 ASCII(1칸)가 섞인 pre 블록에서 컬럼이 어긋나지 않도록
   unicode-range 기반 font-feature 활성화 */
pre {
  font-feature-settings: "liga" 0, "calt" 0;
  text-rendering: optimizeLegibility;
}
/* CJK 문자에 Noto Sans Mono 폴백 — 폰트 메트릭을 고르게 */
@font-face {
  font-family: 'JetBrains Mono';
  src: local('Noto Sans Mono');
  unicode-range: U+AC00-D7AF, U+1100-11FF, U+3130-318F, U+A960-A97F, U+D7B0-D7FF;
}

/* ── Layer architecture (Ch02 §2.4) ── */
.la-wrap { margin: 20px 0 28px; }
.la-header {
  background: #1a237e;
  color: #fff;
  text-align: center;
  padding: 10px 16px;
  border-radius: 8px 8px 0 0;
  font-family: var(--font-mono);
  font-size: 0.88rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.la-header span { display: block; font-size: 0.75rem; font-weight: 400; opacity: 0.82; margin-top: 2px; }
.la-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 2px solid #1a237e;
  border-top: none;
  border-radius: 0 0 8px 8px;
  overflow: hidden;
}
.la-layer {
  border-right: 1px solid #e0e0e0;
  padding: 14px 14px 16px;
  background: var(--lb, #fff);
}
.la-layer:last-child { border-right: none; }
.la-ltitle {
  font-weight: 700;
  font-size: 0.82rem;
  color: var(--lc, #333);
  margin-bottom: 3px;
  letter-spacing: 0.01em;
}
.la-ldesc {
  font-size: 0.72rem;
  color: #757575;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0,0,0,0.08);
}
.la-list { list-style: none; padding: 0; margin: 0; }
.la-list li {
  font-size: 0.75rem;
  padding: 3px 0;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.la-list li:last-child { border-bottom: none; }
.la-list code {
  font-family: var(--font-mono);
  font-size: 0.73rem;
  background: rgba(0,0,0,0.05);
  padding: 1px 4px;
  border-radius: 3px;
  color: #333;
  display: inline-block;
}
.la-list .la-meta { font-size: 0.68rem; color: #757575; }

/* ── Book map (README 책 구성) ── */
.book-map {
  margin: 24px 0 32px;
  overflow-x: auto;
}
.bm-arrow-row {
  display: flex;
  align-items: flex-start;
  gap: 0;
  min-width: 600px;
}
.bm-part {
  flex: 1;
  border: 2px solid var(--part-color, #1a237e);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}
.bm-part-title {
  background: var(--part-color, #1a237e);
  color: #fff;
  font-family: var(--font-serif);
  font-size: 0.8rem;
  font-weight: 700;
  padding: 8px 10px 6px;
  text-align: center;
  line-height: 1.3;
}
.bm-part-title span {
  display: block;
  font-size: 0.72rem;
  font-weight: 400;
  opacity: 0.88;
}
.bm-ch {
  display: block;
  padding: 6px 10px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--part-color, #1a237e);
  text-decoration: none;
  border-bottom: 1px solid #f0f0f0;
  line-height: 1.3;
  transition: background 0.1s;
}
.bm-ch:last-child { border-bottom: none; }
.bm-ch:hover { background: #f5f5ff; text-decoration: none; }
.bm-ch small {
  display: block;
  font-size: 0.67rem;
  font-weight: 400;
  color: #666;
  margin-top: 1px;
}
.bm-arrow {
  align-self: center;
  font-size: 1.2rem;
  color: #9e9e9e;
  padding: 0 4px;
  flex-shrink: 0;
  line-height: 1;
}

/* ── Harness Engineering flow diagram (Ch03 §3.1) ── */
.he-flow {
  display: flex; align-items: center; gap: 14px;
  background: #fafbff; border: 1px solid var(--border);
  border-radius: 10px; padding: 20px 24px; margin: 20px 0 24px;
  overflow-x: auto;
}
.he-box {
  border: 2px solid #f9a825; border-radius: 8px;
  background: #fffde7; padding: 12px 16px; flex-shrink: 0;
}
.he-box-title {
  font-size: 0.72rem; font-weight: 700; text-align: center;
  color: #e65100; margin-bottom: 10px; letter-spacing: 0.03em;
}
.he-elements { display: flex; align-items: center; gap: 8px; }
.he-elem {
  display: flex; flex-direction: column; align-items: center;
  background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
  padding: 8px 10px; min-width: 76px; gap: 2px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.he-elem .he-icon { font-size: 1.1rem; }
.he-elem strong { font-size: 0.8rem; color: var(--primary); }
.he-elem small { font-size: 0.64rem; color: #888; }
.he-arr { color: #bdbdbd; font-size: 1rem; flex-shrink: 0; }
.he-main-arr { color: var(--primary); font-size: 1.6rem; flex-shrink: 0; padding: 0 2px; }
.he-gates {
  border: 2px solid #66bb6a; border-radius: 8px;
  background: #f1f8e9; padding: 12px 14px; flex-shrink: 0;
}
.he-gates-title {
  font-size: 0.72rem; font-weight: 700; text-align: center;
  color: #33691e; margin-bottom: 10px; letter-spacing: 0.02em;
}
.he-gate-list { display: flex; gap: 5px; justify-content: center; }
.he-gate {
  display: flex; flex-direction: column; align-items: center;
  background: #fff; border-radius: 5px; border: 1px solid #c5e1a5;
  padding: 6px 8px; font-size: 0.75rem; font-weight: 600;
  min-width: 60px; gap: 2px;
}
.he-gate small { font-size: 0.6rem; color: #555; font-weight: 400; }
.he-gate.ga { border-color: #90caf9; background: #e3f2fd; color: #0d47a1; }
.he-gate.gb { border-color: #a5d6a7; background: #e8f5e9; color: #1b5e20; }
.he-gate.gc { border-color: #ffcc80; background: #fff3e0; color: #e65100; }
.he-gate.gd { border-color: #f48fb1; background: #fce4ec; color: #880e4f; }
.he-gate.ge { border-color: #ce93d8; background: #f3e5f5; color: #4a148c; }
.he-gate.gf { border-color: #9fa8da; background: #e8eaf6; color: #1a237e; }
.he-gate.gg { border-color: #80deea; background: #e0f7fa; color: #006064; }
.he-outcomes { display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }
.he-pass, .he-fail {
  display: flex; flex-direction: column; align-items: center;
  border-radius: 6px; padding: 9px 14px; font-size: 0.8rem;
  font-weight: 700; min-width: 76px; text-align: center; gap: 2px;
}
.he-pass { background: #c8e6c9; color: #1b5e20; border: 1px solid #a5d6a7; }
.he-fail { background: #ffcdd2; color: #b71c1c; border: 1px solid #ef9a9a; }
.he-pass small, .he-fail small { font-size: 0.63rem; font-weight: 400; display: block; }

/* ── 3요소 다이어그램 (Ch03 §3.2) ── */
.te-outer {
  border: 2px dashed #bdbdbd; border-radius: 10px;
  padding: 20px 24px; margin: 20px 0 24px; background: #fafafa;
}
.te-title {
  text-align: center; font-size: 0.82rem; font-weight: 700;
  color: #757575; margin-bottom: 16px; letter-spacing: 0.06em;
  text-transform: uppercase;
}
.te-inner {
  display: flex; align-items: flex-start; gap: 12px;
  justify-content: center; flex-wrap: wrap;
}
.te-card {
  display: flex; flex-direction: column; align-items: center;
  background: #fff; border: 1.5px solid #e0e0e0; border-radius: 10px;
  padding: 16px 18px; min-width: 140px; text-align: center; gap: 4px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}
.te-tracker { border-color: #90caf9; background: #e3f2fd; }
.te-config  { border-color: #a5d6a7; background: #e8f5e9; }
.te-gate    { border-color: #ce93d8; background: #f3e5f5; }
.te-icon { font-size: 1.5rem; }
.te-name { font-size: 0.95rem; font-weight: 700; color: var(--primary); margin-top: 2px; }
.te-sub { font-size: 0.72rem; color: #888; }
.te-q {
  font-size: 0.73rem; color: #444; margin-top: 10px;
  font-style: italic; line-height: 1.45;
  border-top: 1px solid rgba(0,0,0,0.08); padding-top: 10px; width: 100%;
}
.te-arrow {
  align-self: center; font-size: 1.6rem; color: #9e9e9e; flex-shrink: 0;
  margin-top: 0;
}

/* ── Guides + Sensors 아키텍처 다이어그램 (Ch03 §3.1.2) ── */
.gs-wrap {
  background: #fafbff; border: 1px solid var(--border);
  border-radius: 12px; padding: 24px 20px 20px;
  margin: 20px 0 24px; font-family: var(--font-body);
}
.gs-agent {
  text-align: center; margin-bottom: 12px;
}
.gs-agent-box {
  display: inline-block; background: #fff8e1; border: 2px solid #f9a825;
  border-radius: 10px; padding: 8px 28px; font-size: 0.9rem;
  font-weight: 700; color: #e65100; letter-spacing: 0.02em;
}
.gs-mid {
  display: flex; align-items: stretch; gap: 0;
  justify-content: center;
}
.gs-col {
  flex: 1; max-width: 300px;
}
.gs-panel {
  border-radius: 10px; padding: 14px 16px 16px;
  height: 100%; box-sizing: border-box;
}
.gs-guide-panel {
  background: #e8f0fe; border: 2px solid #90caf9;
  border-right: none; border-radius: 10px 0 0 10px;
}
.gs-sensor-panel {
  background: #e8f5e9; border: 2px solid #81c784;
  border-left: none; border-radius: 0 10px 10px 0;
}
.gs-panel-title {
  font-size: 0.78rem; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase; margin-bottom: 4px;
}
.gs-guide-panel .gs-panel-title { color: #1565c0; }
.gs-sensor-panel .gs-panel-title { color: #2e7d32; }
.gs-panel-sub {
  font-size: 0.68rem; color: #757575; margin-bottom: 10px;
  font-style: italic;
}
.gs-items { display: flex; flex-direction: column; gap: 5px; }
.gs-item {
  background: #fff; border-radius: 6px;
  padding: 5px 10px; font-size: 0.73rem; font-family: var(--font-mono);
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
}
.gs-guide-panel .gs-item { border-left: 3px solid #90caf9; color: #0d47a1; }
.gs-sensor-panel .gs-item { border-left: 3px solid #81c784; color: #1b5e20; }
.gs-center-col {
  display: flex; flex-direction: column; align-items: center;
  justify-content: space-between; padding: 0 2px; min-width: 56px;
}
.gs-exe-label {
  writing-mode: vertical-rl; font-size: 0.68rem; color: #9e9e9e;
  letter-spacing: 0.12em; text-transform: uppercase;
  background: #f5f5f5; border: 1px solid #e0e0e0;
  padding: 6px 4px; border-radius: 4px; flex: 1;
  display: flex; align-items: center; justify-content: center;
}
.gs-arrow-v { font-size: 1.4rem; color: #9e9e9e; line-height: 1; }
.gs-gate-row {
  display: flex; justify-content: center; margin-top: 12px;
}
.gs-gate-box {
  background: #f3e5f5; border: 2px solid #ce93d8;
  border-radius: 10px; padding: 12px 28px; text-align: center;
}
.gs-gate-title {
  font-size: 0.82rem; font-weight: 700; color: #6a1b9a;
  margin-bottom: 6px; letter-spacing: 0.02em;
}
.gs-verdicts { display: flex; gap: 10px; justify-content: center; }
.gs-pass { background: #c8e6c9; color: #1b5e20; border: 1px solid #a5d6a7; border-radius: 5px; padding: 3px 12px; font-size: 0.75rem; font-weight: 700; }
.gs-warn { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; border-radius: 5px; padding: 3px 12px; font-size: 0.75rem; font-weight: 700; }
.gs-fail { background: #ffcdd2; color: #b71c1c; border: 1px solid #ef9a9a; border-radius: 5px; padding: 3px 12px; font-size: 0.75rem; font-weight: 700; }

/* ── 3요소 배포 검증 파이프라인 다이어그램 (Ch03 §3.1.3) ── */
.pip-wrap {
  background: #fafbff; border: 1px solid var(--border);
  border-radius: 12px; padding: 8px 20px 20px;
  margin: 16px 0 24px; font-family: var(--font-body);
}
.pip-title {
  font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: #6b7080; margin-bottom: 14px;
}
.pip-body {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.pip-left { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.pip-down-arr { font-size: 1.4rem; color: #888; line-height: 1; }
.pip-right-arr { font-size: 1.8rem; color: #9aa0b0; line-height: 1; }
.pip-box {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 12px 18px; border-radius: 10px; min-width: 90px; text-align: center;
}
.pip-config { background: #e3f2fd; border: 2px solid #1976d2; }
.pip-tracker { background: #e8f5e9; border: 2px solid #388e3c; }
.pip-gate { background: #f3e5f5; border: 2px solid #7b1fa2; }
.pip-box strong { font-size: 0.95rem; }
.pip-icon { font-size: 1.4rem; }
.pip-sub { font-size: 0.72rem; color: #555; }
.pip-verdicts { display: flex; flex-direction: column; gap: 6px; }
.pip-pass { background: #c8e6c9; color: #1b5e20; border-radius: 6px; padding: 4px 14px; font-size: 0.82rem; font-weight: 700; }
.pip-warn { background: #fff9c4; color: #f57f17; border-radius: 6px; padding: 4px 14px; font-size: 0.82rem; font-weight: 700; }
.pip-fail { background: #ffcdd2; color: #b71c1c; border-radius: 6px; padding: 4px 14px; font-size: 0.82rem; font-weight: 700; }

/* ── Tracker / Config 행 색상 구분 ── */
tr.row-tracker { background: #e8f5e9; }
tr.row-tracker td:first-child { font-weight: 700; color: #1b5e20; }
tr.row-tracker td:first-child::before {
  content: ''; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: #43a047; margin-right: 6px; vertical-align: middle;
}
tr.row-config { background: #e8eaf6; }
tr.row-config td:first-child { font-weight: 700; color: #283593; }
tr.row-config td:first-child::before {
  content: ''; display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: #5c6bc0; margin-right: 6px; vertical-align: middle;
}
/* 코드 뱃지 색상도 유형에 따라 구분 */
tr.row-tracker code { background: #c8e6c9; color: #1b5e20; border-color: #a5d6a7; }
tr.row-config code { background: #c5cae9; color: #1a237e; border-color: #9fa8da; }

/* ── Print ── */
@media print {
  #sidebar { display: none; }
  #main { margin-left: 0; max-width: 100%; padding: 0 20mm; }
  .chapter-section { page-break-before: always; }
  .chapter-section:first-of-type { page-break-before: avoid; }
  a { color: var(--text); }
  pre { background: #f5f5f5; color: var(--text); border: 1px solid #ccc; }
  pre code { color: var(--text); }
}

/* ── Responsive ── */
@media (max-width: 900px) {
  :root { --sidebar-w: 0px; }
  #sidebar { display: none; }
  #main { margin-left: 0; padding: 20px; max-width: 100%; }
}
</style>
</head>
<body>
"""

HTML_SIDEBAR_START = '<nav id="sidebar"><div id="sidebar-header">AI 에이전트<br>Harness Engineering<br>실무 가이드<small>Agent-Evaluator v0.8.4</small></div><div id="toc">'
HTML_SIDEBAR_END = "</div></nav>"

HTML_MAIN_START = '<main id="main">'
HTML_MAIN_END = "</main>"

HTML_FOOT = """\
<script>
mermaid.initialize({ startOnLoad: true, theme: 'default', securityLevel: 'loose', fontFamily: 'Noto Sans KR, sans-serif' });
document.addEventListener('DOMContentLoaded', function() {
  // 언어가 명시된 블록(class="language-python" 등)만 하이라이팅
  // 언어 미지정 블록은 highlight.js 자동 감지를 차단해 오착색 방지
  const ALLOWED = new Set(['python','bash','shell','sh','yaml','json','javascript','js','text','plaintext','html','css','sql','dockerfile']);
  document.querySelectorAll('pre code').forEach(block => {
    const cls = block.className || '';
    const langMatch = cls.match(/language-([a-z0-9_+-]+)/);
    if (langMatch && ALLOWED.has(langMatch[1]) && langMatch[1] !== 'text' && langMatch[1] !== 'plaintext') {
      hljs.highlightElement(block);
    }
    // language-text / 미지정 블록: 색상 없이 그대로 (plain-code 클래스 부여)
    if (!langMatch || langMatch[1] === 'text' || langMatch[1] === 'plaintext') {
      block.classList.add('plain-code');
    }
  });
  // Active TOC tracking
  const sections = document.querySelectorAll('.chapter-section[id]');
  const tocLinks = document.querySelectorAll('#toc a[href^="#"]');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        tocLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id));
      }
    });
  }, { rootMargin: '-10% 0px -80% 0px' });
  sections.forEach(s => observer.observe(s));

  // Tracker / Config 행 색상 구분
  document.querySelectorAll('table tbody tr').forEach(row => {
    const firstCell = row.querySelector('td:first-child');
    if (!firstCell) return;
    const text = firstCell.textContent.trim();
    if (text === 'Tracker') row.classList.add('row-tracker');
    else if (text === 'Config') row.classList.add('row-config');
  });
});
</script>
</body>
</html>
"""

# ── TOC 구조 정의 ──────────────────────────────────────────────────────────────
TOC_STRUCTURE = [
    ("part", "📖 표지 & 서문"),
    ("chapter", "README", "readme", "표지"),
    ("chapter", "00_서문", "preface", "서문"),
    ("part", "Part I — 기초"),
    ("chapter", "Chapter_01", "ch01", "Ch01. AI 에이전트 평가란?"),
    ("chapter", "Chapter_02", "ch02", "Ch02. Agent-Evaluator 첫 시작"),
    ("part", "Part II — 지표 시스템"),
    ("chapter", "Chapter_03", "ch03", "Ch03. Harness Engineering 기초"),
    ("chapter", "Chapter_04", "ch04", "Ch04. Gate A — 목표달성"),
    ("chapter", "Chapter_05", "ch05", "Ch05. Gate B — 행동무결성"),
    ("chapter", "Chapter_06", "ch06", "Ch06. Gate C — 신뢰성"),
    ("chapter", "Chapter_07", "ch07", "Ch07. Gate D — 성능계약"),
    ("chapter", "Chapter_08", "ch08", "Ch08. Gate E — 보안경계"),
    ("chapter", "Chapter_09", "ch09", "Ch09. Gate F — 다중에이전트"),
    ("chapter", "Chapter_10", "ch10", "Ch10. Gate G — 운영관측성"),
    ("part", "Part III — 개발자 가이드"),
    ("chapter", "Chapter_11", "ch11", "Ch11. 평가데이터 설계"),
    ("chapter", "Chapter_12", "ch12", "Ch12. 데코레이터 완전정복"),
    ("chapter", "Chapter_13", "ch13", "Ch13. 프레임워크 통합"),
    ("part", "Part IV — QA 관리자 가이드"),
    ("chapter", "Chapter_14", "ch14", "Ch14. 임계값 & 품질기준"),
    ("chapter", "Chapter_15", "ch15", "Ch15. 대시보드 시각화"),
    ("chapter", "Chapter_16", "ch16", "Ch16. 알림시스템 운영"),
    ("chapter", "Chapter_17", "ch17", "Ch17. 주간·월간 품질리뷰"),
    ("part", "Part V — 프로덕션 운영"),
    ("chapter", "Chapter_18", "ch18", "Ch18. CI/CD 품질게이팅"),
    ("chapter", "Chapter_19", "ch19", "Ch19. Phoenix OTEL 모니터링"),
    ("chapter", "Chapter_20", "ch20", "Ch20. 프로덕션 배포전략"),
    ("chapter", "Chapter_21", "ch21", "Ch21. 종합 실무파이프라인"),
    ("part", "Appendix"),
    ("appendix", "A_58", "appA", "App A. 58개 지표 레퍼런스"),
    ("appendix", "B_CLI", "appB", "App B. CLI 명령어 레퍼런스"),
    ("appendix", "C_환경", "appC", "App C. 환경변수 설정"),
    ("appendix", "D_프레임워크", "appD", "App D. 프레임워크 호환성"),
    ("appendix", "E_에러", "appE", "App E. 에러코드 트러블슈팅"),
    ("appendix", "F_용어", "appF", "App F. 용어사전"),
    ("appendix", "G_AI평가", "appG", "App G. AI 평가 이론적 기초"),
    ("appendix", "H_알고리즘", "appH", "App H. 알고리즘 수학적 레퍼런스"),
    ("appendix", "I_지표", "appI", "App I. 지표 비교분석 선택가이드"),
    ("appendix", "J_프로덕션", "appJ", "App J. 실패패턴 카탈로그"),
    ("appendix", "K_적대적", "appK", "App K. 적대적 강건성 & 레드팀"),
    ("appendix", "L_예산", "appL", "App L. 예산최적화 평가설계"),
]

# stem → section_id 매핑 (파일명 일부 → anchor ID)
STEM_TO_ID: dict[str, str] = {}
for item in TOC_STRUCTURE:
    if item[0] in ("chapter", "appendix"):
        STEM_TO_ID[item[1]] = item[2]


def stem_id(path: Path) -> str:
    stem = path.stem
    for key, sid in STEM_TO_ID.items():
        if key in stem:
            return sid
    return re.sub(r"[^a-zA-Z0-9_-]", "_", stem)


def inject_mermaid(stem: str, text: str) -> str:
    """주요 섹션 제목 다음에 mermaid / HTML 블록을 삽입한다.
    @@HTML@@ 접두사로 시작하는 블록은 raw HTML로 처리된다.
    """
    for file_key, injections in MERMAID_INJECTIONS.items():
        if file_key not in stem:
            continue
        for anchor, block in injections:
            lines = text.split("\n")
            inserted = False
            for i, line in enumerate(lines):
                if anchor in line:
                    lines.insert(i + 1, "\n" + block)
                    inserted = True
                    break
            text = "\n".join(lines)
            if not inserted:
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("# "):
                        lines.insert(i + 1, "\n" + block)
                        break
                text = "\n".join(lines)
    return text


def md_to_html(text: str) -> str:
    """mermaid / raw-HTML 블록을 보존하면서 markdown → HTML 변환."""
    saved_blocks: list[str] = []  # (type, content)

    # ① @@HTML_START@@ ... @@HTML_END@@ raw HTML 블록 추출
    def extract_html_block(m: re.Match) -> str:
        saved_blocks.append(("html", m.group(1).strip()))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"@@HTML_START@@\s*\n(.*?)@@HTML_END@@", extract_html_block, text, flags=re.DOTALL)

    # ② mermaid 블록 추출
    def extract_mermaid(m: re.Match) -> str:
        saved_blocks.append(("mermaid", m.group(1)))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"```mermaid\s*\n(.*?)```", extract_mermaid, text, flags=re.DOTALL)

    # markdown 변환
    converter = md_lib.Markdown(
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "attr_list",
            "def_list",
            "nl2br",
            "sane_lists",
        ],
        extension_configs={"toc": {"permalink": False}},
    )
    html = converter.convert(text)

    # ③ 블록 복원 (mermaid / raw HTML)
    def restore_block(m: re.Match) -> str:
        idx = int(m.group(1))
        kind, content = saved_blocks[idx]
        if kind == "mermaid":
            return f'<div class="mermaid">{content}</div>'
        return content  # raw HTML 그대로

    # <p> 감싸기 먼저 처리 (더 구체적인 패턴 우선), 그 다음 bare 플레이스홀더
    html = re.sub(r"<p>\s*@@BLOCK_(\d+)@@\s*</p>", restore_block, html)
    # nl2br 확장으로 <br> 가 추가된 경우도 처리
    html = re.sub(r"<p>\s*@@BLOCK_(\d+)@@\s*<br\s*/?>\s*</p>", restore_block, html)
    html = re.sub(r"@@BLOCK_(\d+)@@", restore_block, html)

    # blockquote 내부를 단락 단위로 분리:
    # - TIP 이모지(👨‍💻 📊 🔧 🚨 💡)로 시작하는 단락 → <div class="tip-box">
    # - 나머지(참고: 등) → <blockquote> 유지
    _TIP_START_PAT = re.compile(r"^[\s]*(?:👨‍💻|📊|🔧|🚨|💡)")

    def _split_blockquote(m: re.Match) -> str:
        inner = m.group(1)
        # <p>...</p> 단락 단위로 분리
        segs = re.split(r"(?=<p[\s>])", inner)
        bq_buf: list[str] = []
        tip_buf: list[str] = []
        result: list[str] = []

        def _flush_bq() -> None:
            if bq_buf:
                result.append(f"<blockquote>{''.join(bq_buf)}</blockquote>")
                bq_buf.clear()

        def _flush_tip() -> None:
            if tip_buf:
                result.append(f'<div class="tip-box">{"".join(tip_buf)}</div>')
                tip_buf.clear()

        for seg in segs:
            if not seg.strip():
                continue
            plain = re.sub(r"<[^>]+>", "", seg).strip()
            if _TIP_START_PAT.match(plain):
                _flush_bq()
                tip_buf.append(seg)
            else:
                _flush_tip()
                bq_buf.append(seg)

        _flush_bq()
        _flush_tip()
        return "\n".join(result) if result else m.group(0)

    html = re.sub(r"<blockquote>(.*?)</blockquote>", _split_blockquote, html, flags=re.DOTALL)

    # 테이블 가로 스크롤: <table>...</table> → <div class="table-wrap"><table>...</table></div>
    html = re.sub(r"(<table\b)", r'<div class="table-wrap">\1', html)
    html = re.sub(r"(</table>)", r"\1</div>", html)

    return html


def build_toc_html() -> str:
    lines: list[str] = []
    for item in TOC_STRUCTURE:
        if item[0] == "part":
            lines.append(f'<a class="part-heading">{item[1]}</a>')
        elif item[0] == "chapter":
            lines.append(f'<a class="chapter" href="#{item[2]}">{item[3]}</a>')
        elif item[0] == "appendix":
            lines.append(f'<a class="appendix" href="#{item[2]}">{item[3]}</a>')
    return "\n".join(lines)


def build_book() -> None:
    print("📚 Building HTML book...")
    parts: list[str] = []

    for fpath in ORDERED_FILES:
        if not fpath.exists():
            print(f"  ⚠️  Missing: {fpath.name}")
            continue

        print(f"  📄 {fpath.name}")
        raw = fpath.read_text(encoding="utf-8")

        # mermaid 삽입
        raw = inject_mermaid(fpath.stem, raw)

        # HTML 변환
        html_body = md_to_html(raw)

        sid = stem_id(fpath)
        parts.append(f'<section class="chapter-section" id="{sid}">\n{html_body}\n</section>')

    # 조합
    toc_html = build_toc_html()
    output = (
        HTML_HEAD
        + HTML_SIDEBAR_START
        + toc_html
        + HTML_SIDEBAR_END
        + HTML_MAIN_START
        + "\n".join(parts)
        + HTML_MAIN_END
        + HTML_FOOT
    )

    OUTPUT_FILE.write_text(output, encoding="utf-8")
    size_kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"\n✅ Done: {OUTPUT_FILE}  ({size_kb} KB)")


if __name__ == "__main__":
    build_book()
