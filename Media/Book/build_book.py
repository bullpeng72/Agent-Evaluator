#!/usr/bin/env python3
"""Book markdown → single HTML converter with Mermaid diagram injection."""

import importlib.util
import platform
import re
import sys
import unicodedata
from html import escape as _html_escape
from pathlib import Path

# ── 의존성 확인 ────────────────────────────────────────────────────────────────

def _check_dependencies() -> None:
    missing = []
    if importlib.util.find_spec("markdown") is None:
        missing.append("markdown")

    if missing:
        os_name = platform.system()
        print(f"❌ 필수 패키지 누락: {', '.join(missing)}")
        print("\n설치 방법:")
        print(f"  pip install {' '.join(missing)}")

        if os_name == "Darwin":  # macOS
            print("  brew install pandoc pango")
        elif os_name == "Linux":  # Ubuntu/Debian
            print("  sudo apt install pandoc libpango-1.0-0")
        sys.exit(1)


_check_dependencies()

import markdown as md_lib

BOOK_DIR = Path(__file__).parent
OUTPUT_FILE = BOOK_DIR / "agent-evaluator-book.html"

# ── SDK 버전 자동 읽기 (pyproject.toml → 변경 없이 항상 최신 버전 반영) ──────────
def _read_sdk_version() -> str:
    """pyproject.toml에서 version을 읽는다. 실패 시 regex fallback."""
    toml_path = BOOK_DIR.parent.parent / "pyproject.toml"
    try:
        if sys.version_info >= (3, 11):
            import tomllib
            with open(toml_path, "rb") as _f:
                return tomllib.load(_f)["project"]["version"]
    except Exception:
        pass
    try:
        import re as _re
        _raw = toml_path.read_text(encoding="utf-8")
        _m = _re.search(r'^version\s*=\s*"([^"]+)"', _raw, _re.MULTILINE)
        if _m:
            return _m.group(1)
    except Exception:
        pass
    return "0.9.3"  # hardcoded fallback

SDK_VERSION = _read_sdk_version()


def robust_path(fpath: Path) -> Path:
    """NFC/NFD 정규화 차이로 인한 파일 미인식 문제 해결."""
    if fpath.exists():
        return fpath

    try:
        rel_parts = fpath.relative_to(BOOK_DIR).parts
    except ValueError:
        return fpath

    current = BOOK_DIR
    for part in rel_parts:
        nfc_part = unicodedata.normalize("NFC", part)
        found = False
        if not current.exists():
            break
        for entry in current.iterdir():
            if unicodedata.normalize("NFC", entry.name) == nfc_part:
                current = entry
                found = True
                break
        if not found:
            current = current / part
    return current


# ── 변환 순서 ──────────────────────────────────────────────────────────────────
ORDERED_FILES = [
    robust_path(BOOK_DIR / "README.md"),
    robust_path(BOOK_DIR / "00_서문.md"),
    robust_path(BOOK_DIR / "Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md"),
    robust_path(BOOK_DIR / "Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_04_GroupA_목표달성.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_05_GroupB_행동무결성.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_06_GroupC_신뢰성.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_07_GroupD_성능계약.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_08_GroupE_보안경계.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_09_GroupF_다중에이전트.md"),
    robust_path(BOOK_DIR / "Part_II_지표시스템/Chapter_10_GroupG_운영관측성.md"),
    robust_path(BOOK_DIR / "Part_III_개발자가이드/Chapter_11_평가데이터_설계.md"),
    robust_path(BOOK_DIR / "Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md"),
    robust_path(BOOK_DIR / "Part_III_개발자가이드/Chapter_13_프레임워크_통합.md"),
    robust_path(BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md"),
    robust_path(BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_15_대시보드_시각화.md"),
    robust_path(BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_16_알림시스템_운영.md"),
    robust_path(BOOK_DIR / "Part_IV_QA관리자가이드/Chapter_17_주간월간_품질리뷰.md"),
    robust_path(BOOK_DIR / "Part_V_프로덕션운영/Chapter_18_CICD_품질게이팅.md"),
    robust_path(BOOK_DIR / "Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md"),
    robust_path(BOOK_DIR / "Part_V_프로덕션운영/Chapter_20_프로덕션_배포전략.md"),
    robust_path(BOOK_DIR / "Part_V_프로덕션운영/Chapter_21_종합_실무파이프라인.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/00_파트_서문.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/Chapter_22_기존_프로젝트_해부.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/Chapter_23_Gate_매핑_전략.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/Chapter_24_첫번째_이식.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/Chapter_25_전체_통합.md"),
    robust_path(BOOK_DIR / "Part_VI_실전이식가이드/Chapter_26_CICD_완성.md"),
    robust_path(BOOK_DIR / "Part_VII_실시간가드레일/Chapter_27_LiveGuardrail_OpenCode_연동.md"),
    robust_path(BOOK_DIR / "Part_VII_실시간가드레일/Chapter_28_로컬_ADE_구축.md"),
    robust_path(BOOK_DIR / "Appendix/A_58개지표_레퍼런스.md"),
    robust_path(BOOK_DIR / "Appendix/B_CLI_명령어_레퍼런스.md"),
    robust_path(BOOK_DIR / "Appendix/C_환경변수_설정_레퍼런스.md"),
    robust_path(BOOK_DIR / "Appendix/D_프레임워크_호환성_매트릭스.md"),
    robust_path(BOOK_DIR / "Appendix/E_에러코드_트러블슈팅.md"),
    robust_path(BOOK_DIR / "Appendix/F_용어사전.md"),
    robust_path(BOOK_DIR / "Appendix/G_AI평가_이론적기초.md"),
    robust_path(BOOK_DIR / "Appendix/H_알고리즘_수학적_레퍼런스.md"),
    robust_path(BOOK_DIR / "Appendix/I_지표_비교분석_선택가이드.md"),
    robust_path(BOOK_DIR / "Appendix/J_프로덕션_실패패턴_카탈로그.md"),
    robust_path(BOOK_DIR / "Appendix/K_적대적_강건성과_레드팀_평가.md"),
    robust_path(BOOK_DIR / "Appendix/L_예산최적화_평가설계.md"),
    robust_path(BOOK_DIR / "Appendix/M_프로덕션_운영_체크리스트.md"),
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
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#37474f">
      <div class="bm-part-title">Part VI<span>실전 이식 가이드</span></div>
      <a href="#ch22" class="bm-ch">Ch22<small>기존 프로젝트 해부</small></a>
      <a href="#ch23" class="bm-ch">Ch23<small>Gate 매핑 전략</small></a>
      <a href="#ch24" class="bm-ch">Ch24<small>첫 번째 이식</small></a>
      <a href="#ch25" class="bm-ch">Ch25<small>전체 통합</small></a>
      <a href="#ch26" class="bm-ch">Ch26<small>CI/CD 완성</small></a>
    </div>
    <div class="bm-arrow">▶</div>
    <div class="bm-part" style="--part-color:#6a1b9a">
      <div class="bm-part-title">Part VII<span>실시간 가드레일</span></div>
      <a href="#ch27" class="bm-ch">Ch27<small>LiveGuardrail & OpenCode</small></a>
      <a href="#ch28" class="bm-ch">Ch28<small>로컬 자가교정 ADE 구축</small></a>
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
    REC --> L1["Layer 1 집계\\nTCR · Accuracy · Hallucination\\nQuality · Latency · Token"]
    REC --> L2["Layer 2 집계\\nToolCall · Retry · Security\\nCoordination · Workflow"]
    L1 --> HC["Harness Config 평가\\n33개 Config 임계값 대조"]
    L2 --> HC
    HC --> GA["Gate A\\n목표달성"]
    HC --> GB["Gate B\\n행동무결성"]
    HC --> GC["Gate C\\n신뢰성"]
    HC --> GD["Gate D\\n성능계약"]
    HC --> GE["Gate E\\n보안경계"]
    HC --> GF["Gate F\\n다중에이전트"]
    HC --> GG["Gate G\\n운영관측성"]
    
    GA --> RPT["generate_report()\\nsave_to_file()"]
    GB --> RPT
    GC --> RPT
    GD --> RPT
    GE --> RPT
    GF --> RPT
    GG --> RPT
    
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
        RUN["평가 실행\nch18_cicd_gate.py\n7개 Gate 최소 검증"]
        GATE["Harness Gate 종합 판정\nmonitor.generate_report()\nPASS / WARN / FAIL → exit 0 / 1"]
        TREND["agent-eval trend\n--fail-on-regression"]
    end
    RUN --> GATE
    RUN --> RESULT["results/\nch18_cicd_gate.json"]
    RESULT --> TREND
    GATE --> |"exit 0 (PASS)"| DEPLOY["배포 단계"]
    GATE --> |"exit 1 (FAIL)"| HALT["파이프라인 중단\nexit 1"]
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
    "Chapter_21_종합_실무파이프라인": [],
    "00_파트_서문": [],
    "Chapter_22_기존_프로젝트_해부": [],
    "Chapter_23_Gate_매핑_전략": [],
    "Chapter_24_첫번째_이식": [],
    "Chapter_25_전체_통합": [],
    "Chapter_26_CICD_완성": [],
    "A_58개지표_레퍼런스": [
        (
            "## A.1",
            """@@HTML_START@@
<style>
.gate-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0;}
.gate-card{border-radius:10px;padding:14px;font-size:12px;}
.gate-title{font-weight:700;font-size:13px;margin-bottom:8px;border-bottom-width:1px;border-bottom-style:solid;padding-bottom:6px;}
.gate-sub{font-weight:400;font-size:11px;}
.section-label{font-size:10px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin:8px 0 4px;opacity:.7;}
.chip{border-radius:4px;padding:4px 8px;margin-bottom:4px;display:flex;align-items:center;gap:5px;font-size:12px;}
.chip-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.summary-card{border-radius:10px;padding:14px;display:flex;align-items:center;justify-content:center;background:#f5f5f5;border:2px solid #bdbdbd;}
.legend{display:flex;gap:16px;margin:0 0 12px;font-size:11px;align-items:center;}
.legend-item{display:flex;align-items:center;gap:5px;}
</style>
<div class="legend">
  <span style="font-weight:700;font-size:12px;color:#424242;">범례:</span>
  <span class="legend-item"><span style="width:10px;height:10px;border-radius:50%;background:#37474f;display:inline-block;"></span> Tracker (자동 측정)</span>
  <span class="legend-item"><span style="width:10px;height:10px;border-radius:2px;background:#90a4ae;display:inline-block;"></span> Config (기준 선언)</span>
</div>
<div class="gate-grid">

  <div class="gate-card" style="background:#e8f5e9;border:2px solid #66bb6a;">
    <div class="gate-title" style="color:#1b5e20;border-bottom-color:#a5d6a7;">
      Gate A &mdash; 목표달성<br><span class="gate-sub" style="color:#388e3c;">Goal Achievement</span>
    </div>
    <div class="section-label" style="color:#1b5e20;">Tracker</div>
    <div class="chip" style="background:#1b5e20;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>TaskCompletionTracker</div>
    <div class="chip" style="background:#1b5e20;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>AccuracyEvaluator</div>
    <div class="chip" style="background:#1b5e20;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ResponseQualityEvaluator</div>
    <div class="section-label" style="color:#1b5e20;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>InstructionConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>GoalAlignmentConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>PlanConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>SubtaskConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>ContextRetentionConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #a5d6a7;color:#1b5e20;"><span class="chip-dot" style="background:#a5d6a7;"></span>KnowledgeRetentionConfig</div>
  </div>

  <div class="gate-card" style="background:#e3f2fd;border:2px solid #42a5f5;">
    <div class="gate-title" style="color:#0d47a1;border-bottom-color:#90caf9;">
      Gate B &mdash; 행동무결성<br><span class="gate-sub" style="color:#1565c0;">Behavioral Integrity</span>
    </div>
    <div class="section-label" style="color:#0d47a1;">Tracker</div>
    <div class="chip" style="background:#0d47a1;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ToolCallAnalyzer</div>
    <div class="chip" style="background:#0d47a1;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>WorkflowExecutionTracker</div>
    <div class="section-label" style="color:#0d47a1;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>LoopDetectionConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>ScopeConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>ToolParameterSafetyConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>ContextWindowConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>StateConsistencyConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #90caf9;color:#0d47a1;"><span class="chip-dot" style="background:#90caf9;"></span>DeadlockConfig</div>
  </div>

  <div class="gate-card" style="background:#fff3e0;border:2px solid #ffa726;">
    <div class="gate-title" style="color:#e65100;border-bottom-color:#ffcc80;">
      Gate C &mdash; 신뢰성<br><span class="gate-sub" style="color:#ef6c00;">Reliability</span>
    </div>
    <div class="section-label" style="color:#e65100;">Tracker</div>
    <div class="chip" style="background:#e65100;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>HallucinationDetector</div>
    <div class="chip" style="background:#e65100;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>RetryCorrectionTracker</div>
    <div class="section-label" style="color:#e65100;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #ffcc80;color:#e65100;"><span class="chip-dot" style="background:#ffcc80;"></span>ReproducibilityConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ffcc80;color:#e65100;"><span class="chip-dot" style="background:#ffcc80;"></span>FaultToleranceConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ffcc80;color:#e65100;"><span class="chip-dot" style="background:#ffcc80;"></span>GracefulDegradationConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ffcc80;color:#e65100;"><span class="chip-dot" style="background:#ffcc80;"></span>RetryConsistencyConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ffcc80;color:#e65100;"><span class="chip-dot" style="background:#ffcc80;"></span>IdempotencyConfig</div>
  </div>

  <div class="gate-card" style="background:#fce4ec;border:2px solid #ec407a;">
    <div class="gate-title" style="color:#880e4f;border-bottom-color:#f48fb1;">
      Gate D &mdash; 성능계약<br><span class="gate-sub" style="color:#ad1457;">Performance Contract</span>
    </div>
    <div class="section-label" style="color:#880e4f;">Tracker</div>
    <div class="chip" style="background:#880e4f;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>LatencyTracker</div>
    <div class="chip" style="background:#880e4f;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>TokenEconomyTracker</div>
    <div class="section-label" style="color:#880e4f;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #f48fb1;color:#880e4f;"><span class="chip-dot" style="background:#f48fb1;"></span>SLAConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #f48fb1;color:#880e4f;"><span class="chip-dot" style="background:#f48fb1;"></span>EfficiencyConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #f48fb1;color:#880e4f;"><span class="chip-dot" style="background:#f48fb1;"></span>ResourceBudgetConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #f48fb1;color:#880e4f;"><span class="chip-dot" style="background:#f48fb1;"></span>TTFTVariabilityConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #f48fb1;color:#880e4f;"><span class="chip-dot" style="background:#f48fb1;"></span>CostPredictabilityConfig</div>
  </div>

  <div class="gate-card" style="background:#f3e5f5;border:2px solid #ab47bc;">
    <div class="gate-title" style="color:#4a148c;border-bottom-color:#ce93d8;">
      Gate E &mdash; 보안경계<br><span class="gate-sub" style="color:#6a1b9a;">Security Boundary</span>
    </div>
    <div class="section-label" style="color:#4a148c;">Tracker</div>
    <div class="chip" style="background:#4a148c;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>InputSanitizationTracker</div>
    <div class="chip" style="background:#4a148c;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>OutputLeakageDetector</div>
    <div class="chip" style="background:#4a148c;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ToolAuthorizationTracker</div>
    <div class="chip" style="background:#4a148c;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>PrivilegeEscalationDetector</div>
    <div class="chip" style="background:#4a148c;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ToolChainAttackDetector</div>
    <div class="section-label" style="color:#4a148c;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #ce93d8;color:#4a148c;"><span class="chip-dot" style="background:#ce93d8;"></span>ThreatSeverityConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ce93d8;color:#4a148c;"><span class="chip-dot" style="background:#ce93d8;"></span>ComplianceConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #ce93d8;color:#4a148c;"><span class="chip-dot" style="background:#ce93d8;"></span>ThreatResponseConfig</div>
  </div>

  <div class="gate-card" style="background:#e8eaf6;border:2px solid #5c6bc0;">
    <div class="gate-title" style="color:#1a237e;border-bottom-color:#9fa8da;">
      Gate F &mdash; 다중에이전트<br><span class="gate-sub" style="color:#283593;">Multi-Agent</span>
    </div>
    <div class="section-label" style="color:#1a237e;">Tracker</div>
    <div class="chip" style="background:#1a237e;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>AgentCoordinationTracker</div>
    <div class="chip" style="background:#1a237e;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ToolSelectionTracker</div>
    <div class="section-label" style="color:#1a237e;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #9fa8da;color:#1a237e;"><span class="chip-dot" style="background:#9fa8da;"></span>ConsensusConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #9fa8da;color:#1a237e;"><span class="chip-dot" style="background:#9fa8da;"></span>PropagationConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #9fa8da;color:#1a237e;"><span class="chip-dot" style="background:#9fa8da;"></span>AgentRoleConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #9fa8da;color:#1a237e;"><span class="chip-dot" style="background:#9fa8da;"></span>ConflictResolutionConfig</div>
  </div>

  <div class="gate-card" style="background:#e0f7fa;border:2px solid #26c6da;">
    <div class="gate-title" style="color:#006064;border-bottom-color:#80deea;">
      Gate G &mdash; 운영관측성<br><span class="gate-sub" style="color:#00838f;">Observability</span>
    </div>
    <div class="section-label" style="color:#006064;">Tracker</div>
    <div style="font-size:11px;color:#00838f;font-style:italic;padding:4px 6px;background:#b2ebf2;border-radius:4px;margin-bottom:4px;">Native Tracker 없음<br>LLMJudge(Hybrid, opt-in)</div>
    <div class="section-label" style="color:#006064;">Config</div>
    <div class="chip" style="background:#fff;border:1px solid #80deea;color:#006064;"><span class="chip-dot" style="background:#80deea;"></span>ExplainabilityConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #80deea;color:#006064;"><span class="chip-dot" style="background:#80deea;"></span>ObservabilityConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #80deea;color:#006064;"><span class="chip-dot" style="background:#80deea;"></span>ErrorDiagnosisConfig</div>
    <div class="chip" style="background:#fff;border:1px solid #80deea;color:#006064;"><span class="chip-dot" style="background:#80deea;"></span>LatencyAttributionConfig</div>
  </div>

  <div class="summary-card">
    <div style="text-align:center;color:#424242;">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px;">합계</div>
      <div style="display:flex;gap:12px;justify-content:center;align-items:center;">
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:700;color:#37474f;">16</div>
          <div style="font-size:10px;color:#546e7a;">Gate 매핑<br>Tracker</div>
        </div>
        <div style="font-size:18px;font-weight:300;color:#bdbdbd;">+</div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:700;color:#78909c;">9</div>
          <div style="font-size:10px;color:#546e7a;">운영 지원<br>Tracker</div>
        </div>
        <div style="font-size:18px;font-weight:300;color:#bdbdbd;">+</div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:700;color:#90a4ae;">33</div>
          <div style="font-size:10px;color:#546e7a;">Harness<br>Config</div>
        </div>
      </div>
      <div style="margin-top:10px;font-size:16px;font-weight:700;color:#1a237e;border-top:1px solid #e0e0e0;padding-top:8px;">= 58개 지표</div>
    </div>
  </div>

</div>

<!-- 운영 지원 Tracker 9종 -->
<div style="margin-top:8px;background:#f5f5f5;border:2px solid #bdbdbd;border-radius:10px;padding:14px;">
  <div style="font-weight:700;font-size:13px;color:#37474f;margin-bottom:10px;border-bottom:1px solid #e0e0e0;padding-bottom:6px;">
    운영 지원 Tracker (9종) &mdash; Harness Gate 직접 판정 외 운영 인프라
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;">
    <div class="chip" style="background:#37474f;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ConversationSession</div>
    <div class="chip" style="background:#37474f;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ConversationMetrics</div>
    <div class="chip" style="background:#37474f;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ConversationTurn</div>
    <div class="chip" style="background:#546e7a;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>ImplicitFeedbackTracker</div>
    <div class="chip" style="background:#546e7a;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>AnomalyDetector</div>
    <div class="chip" style="background:#546e7a;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>CostTracker</div>
    <div class="chip" style="background:#607d8b;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>AdaptivePolicy</div>
    <div class="chip" style="background:#607d8b;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>SamplingStage</div>
    <div class="chip" style="background:#607d8b;color:#fff;"><span class="chip-dot" style="background:#fff;"></span>StreamingEvaluator</div>
  </div>
</div>
@@HTML_END@@
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
<title>실전 AI 에이전트 하네스 엔지니어링 — Agent-Evaluator를 활용한 품질 평가와 배포 자동화</title>
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
#sidebar-header .subtitle {
  display: block;
  font-size: 0.72rem;
  font-weight: 400;
  font-style: italic;
  opacity: 0.82;
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px solid rgba(255,255,255,0.18);
  line-height: 1.55;
  letter-spacing: 0.01em;
}
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

/* ── lecture-forge editor 호환: chapter-section 내 헤딩 재정의 ── */
/* demote_headings()로 h1→h2, h2→h3, h3→h4, h4→h5 강등 후 시각 보정 */
.chapter-section h2 { font-size: 2.2rem; color: var(--primary); margin: 40px 0 20px; padding-bottom: 12px; border-bottom: 2px solid var(--primary); }
.chapter-section h3 { font-size: 1.55rem; color: var(--primary-light); margin: 36px 0 14px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.chapter-section h4 { font-size: 1.2rem; color: var(--text); margin: 28px 0 10px; }
.chapter-section h5 { font-size: 1.05rem; color: var(--text); margin: 20px 0 8px; }

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

/* ── Harness 연결 카드 (hc-card) ── */
.hc-card {
  border-radius: 12px; overflow: hidden;
  margin: 20px 0 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.09);
  border: 2px solid var(--hc-border, #e0e0e0);
}
.hc-a { --hc-border:#90caf9; --hc-bg:#e3f2fd; --hc-hbg:#1565c0; --hc-label-t:#0d47a1; }
.hc-b { --hc-border:#a5d6a7; --hc-bg:#e8f5e9; --hc-hbg:#2e7d32; --hc-label-t:#1b5e20; }
.hc-c { --hc-border:#ffcc80; --hc-bg:#fff3e0; --hc-hbg:#e65100; --hc-label-t:#bf360c; }
.hc-d { --hc-border:#f48fb1; --hc-bg:#fce4ec; --hc-hbg:#880e4f; --hc-label-t:#880e4f; }
.hc-e { --hc-border:#ce93d8; --hc-bg:#f3e5f5; --hc-hbg:#6a1b9a; --hc-label-t:#4a148c; }
.hc-f { --hc-border:#9fa8da; --hc-bg:#e8eaf6; --hc-hbg:#283593; --hc-label-t:#1a237e; }
.hc-g { --hc-border:#80deea; --hc-bg:#e0f7fa; --hc-hbg:#00695c; --hc-label-t:#006064; }
.hc-header {
  display: flex; align-items: center; gap: 12px;
  background: var(--hc-hbg, #333); padding: 10px 16px;
}
.hc-gate-badge {
  font-size: 0.78rem; font-weight: 700; padding: 3px 12px;
  border-radius: 14px; flex-shrink: 0; white-space: nowrap;
}
.hc-title {
  color: #fff; font-size: 0.88rem; font-weight: 600;
  letter-spacing: 0.01em;
}
.hc-body { background: var(--hc-bg, #fafafa); padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; }
.hc-row { display: flex; align-items: flex-start; gap: 10px; }
.hc-label {
  flex-shrink: 0; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.04em; text-transform: uppercase;
  padding: 3px 8px; border-radius: 4px; margin-top: 2px;
  white-space: nowrap;
}
.hc-tracker-label { background: #e3f2fd; color: #0d47a1; border: 1px solid #90caf9; }
.hc-config-label  { background: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; }
.hc-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.hc-chip {
  font-family: var(--font-mono); font-size: 0.73rem;
  padding: 2px 9px; border-radius: 6px;
}
.hc-t-chip { background: #bbdefb; color: #0d47a1; border: 1px solid #90caf9; }
.hc-c-chip { background: #c8e6c9; color: #1b5e20; border: 1px solid #a5d6a7; }
.hc-t-note { background: #e3f2fd; color: #546e7a; font-style: italic; border: 1px dashed #90caf9; }
.hc-footer {
  background: rgba(0,0,0,0.04); padding: 8px 18px;
  font-size: 0.78rem; color: #555;
  border-top: 1px solid rgba(0,0,0,0.07);
}
.hc-footer code { font-size: 0.78rem; }

/* ── Gate 경고 박스 (gw-box) ── */
.gw-box {
  border-left: 4px solid #f59e0b; border-radius: 0 10px 10px 0;
  background: #fffbeb; margin: 20px 0 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.gw-header {
  padding: 10px 18px 8px; font-weight: 700; font-size: 0.9rem;
  color: #92400e; border-bottom: 1px solid #fde68a;
}
.gw-body { padding: 12px 18px 14px; font-size: 0.9rem; color: #44403c; }
.gw-body p { margin: 0 0 10px; line-height: 1.7; }
.gw-body p:last-child { margin-bottom: 0; }
.gw-case {
  background: #fff8e1; border-radius: 6px; padding: 9px 13px;
  font-size: 0.85rem; color: #555; margin-top: 8px; line-height: 1.65;
  border: 1px solid #fde68a;
}
.gw-case strong { color: #b45309; }
.gw-note {
  margin-top: 8px; padding: 7px 12px; background: #f0f9ff;
  border-radius: 6px; font-size: 0.82rem; color: #555;
  border: 1px solid #bae6fd;
}
.gw-note strong { color: #0369a1; }

/* ── Dual-view (개발자 ↔ QA 관리자) ── */
.dual-view {
  display: flex; align-items: stretch; gap: 0;
  margin: 20px 0 28px; border-radius: 12px; overflow: hidden;
  box-shadow: 0 2px 10px rgba(0,0,0,0.10);
}
.dv-col {
  flex: 1; display: flex; flex-direction: column;
}
.dv-dev { background: #1e2433; }
.dv-qa  { background: #f0f4ff; border: 2px solid #c5cae9; border-left: none; }
.dv-header {
  padding: 10px 18px; font-size: 0.82rem; font-weight: 700;
  letter-spacing: 0.03em;
}
.dv-dev .dv-header { background: #12151f; color: #7ec8e3; }
.dv-qa  .dv-header { background: #3949ab; color: #fff; }
.dv-body { flex: 1; padding: 16px 18px; }
.dv-code {
  background: transparent; border: none; box-shadow: none;
  padding: 0; margin: 0; font-size: 0.82rem; line-height: 1.7;
  color: #abb2bf; white-space: pre;
}
.dv-dec  { color: #61afef; }
.dv-cfg  { color: #98c379; }
.dv-footer {
  padding: 8px 18px; font-size: 0.72rem; text-align: center;
  border-top: 1px solid rgba(255,255,255,0.08);
}
.dv-dev .dv-footer { color: #5c6370; background: #12151f; }
.dv-qa  .dv-footer { color: #7986cb; background: #e8eaf6; border-color: #c5cae9; }
.dv-arrow {
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem; color: #9e9e9e; padding: 0 6px;
  background: #f5f5f5; flex-shrink: 0;
}
.dv-result-label {
  font-size: 0.72rem; font-weight: 700; color: #3949ab;
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 12px;
}
.dv-results { display: flex; flex-direction: column; gap: 8px; }
.dv-gate-row {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-radius: 7px; padding: 7px 12px;
  border: 1px solid #dde2f5;
}
.dv-gate-name { font-size: 0.8rem; color: #283593; font-weight: 500; }
.dv-badge {
  font-size: 0.74rem; font-weight: 700; padding: 2px 10px;
  border-radius: 10px;
}
.dv-pass { background: #c8e6c9; color: #1b5e20; }
.dv-warn { background: #fff9c4; color: #f57f17; }
.dv-fail { background: #ffcdd2; color: #b71c1c; }

/* ── HarnessEvaluationGate flow diagram (Ch18) ── */
.heg-flow {
  background: #1a1f2e; border-radius: 14px; padding: 28px 32px;
  margin: 20px 0 24px; box-shadow: 0 3px 12px rgba(0,0,0,0.18);
  display: flex; align-items: center; gap: 0;
}
.heg-left {
  flex: 1; display: flex; flex-direction: column; gap: 10px;
}
.heg-left-title {
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #546e7a; margin-bottom: 4px;
}
.heg-config-row {
  display: flex; align-items: center; gap: 10px;
}
.heg-cfg-name {
  font-family: 'SFMono-Regular', monospace; font-size: 0.78rem;
  color: #90caf9; background: rgba(255,255,255,0.05);
  border: 1px solid rgba(144,202,249,0.25); border-radius: 5px;
  padding: 4px 10px; min-width: 200px;
}
.heg-arrow-right {
  color: #546e7a; font-size: 0.9rem; flex-shrink: 0;
}
.heg-pass {
  font-size: 0.72rem; font-weight: 700; padding: 2px 8px;
  border-radius: 8px; background: rgba(105,240,174,0.12);
  color: #69f0ae; border: 1px solid rgba(105,240,174,0.25);
  white-space: nowrap;
}
.heg-connector {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 0 20px; color: #3949ab;
  flex-shrink: 0;
}
.heg-connector-line {
  width: 2px; flex: 1; background: linear-gradient(to bottom, transparent, #3949ab, transparent);
  min-height: 80px;
}
.heg-connector-arrow {
  font-size: 1.4rem; color: #5c6bc0; margin: 4px 0;
}
.heg-right {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  flex-shrink: 0;
}
.heg-right-title {
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #546e7a; margin-bottom: 4px;
  text-align: center;
}
.heg-gate-box {
  background: linear-gradient(135deg, #283593, #1565c0);
  border-radius: 10px; padding: 14px 22px; text-align: center;
  border: 1px solid rgba(100,181,246,0.3);
  box-shadow: 0 0 18px rgba(40,53,147,0.4);
}
.heg-gate-name {
  font-size: 0.88rem; font-weight: 700; color: #fff; white-space: nowrap;
}
.heg-gate-sub {
  font-size: 0.68rem; color: #90caf9; margin-top: 3px;
}
.heg-outcomes {
  display: flex; gap: 10px;
}
.heg-deploy {
  background: rgba(105,240,174,0.12); border: 1px solid rgba(105,240,174,0.35);
  border-radius: 8px; padding: 7px 16px; text-align: center;
  font-size: 0.78rem; font-weight: 700; color: #69f0ae;
}
.heg-hold {
  background: rgba(255,82,82,0.1); border: 1px solid rgba(255,82,82,0.3);
  border-radius: 8px; padding: 7px 16px; text-align: center;
  font-size: 0.78rem; font-weight: 700; color: #ff5252;
}
.heg-outcome-note {
  font-size: 0.66rem; color: #455a64; text-align: center; margin-top: -4px;
}

/* ── Impact matrix table (Ch18) ── */
.impact-table {
  width: 100%; border-collapse: collapse; font-size: 0.82rem;
  margin: 16px 0 20px; border-radius: 10px; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.impact-table thead th {
  background: #1e2433; color: #90caf9;
  padding: 10px 14px; text-align: left; font-weight: 700;
  font-size: 0.78rem; letter-spacing: 0.04em; white-space: nowrap;
}
.impact-table tbody tr { border-bottom: 1px solid #e8eaf6; }
.impact-table tbody tr:last-child { border-bottom: none; }
.impact-table tbody tr:nth-child(even) { background: #f7f8ff; }
.impact-table tbody tr:hover { background: #eef0ff; }
.impact-table td { padding: 10px 14px; vertical-align: top; color: #333; }
.impact-table td:first-child { font-weight: 600; white-space: nowrap; }
.im-source {
  display: inline-block; padding: 2px 9px; border-radius: 10px;
  font-size: 0.74rem; font-weight: 700; margin-bottom: 3px;
}
.im-code   { background: #e3f2fd; color: #1565c0; }
.im-model  { background: #f3e5f5; color: #6a1b9a; }
.im-prompt { background: #e8f5e9; color: #1b5e20; }
.im-data   { background: #fff3e0; color: #e65100; }
.im-gate   { font-size: 0.78rem; font-weight: 600; }
.im-gate-b { color: #1565c0; }
.im-gate-a { color: #2e7d32; }
.im-gate-c { color: #6a1b9a; }
.im-gate-e { color: #b71c1c; }
.im-gate-g { color: #37474f; }
.im-configs { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.im-cfg {
  background: #f0f2ff; border: 1px solid #c5cae9; border-radius: 4px;
  padding: 1px 7px; font-size: 0.72rem; font-family: 'SFMono-Regular', monospace;
  color: #3949ab; white-space: nowrap;
}
.im-trackers { font-size: 0.77rem; color: #555; line-height: 1.7; }
.im-trackers code {
  font-size: 0.74rem; background: #f5f5f5; padding: 1px 5px;
  border-radius: 3px; color: #455a64;
}

/* ── Tradeoff spectrum (Ch13) ── */
.tradeoff-wrap {
  background: #1a1f2e; border-radius: 14px; padding: 28px 32px 24px;
  margin: 20px 0 24px; box-shadow: 0 3px 12px rgba(0,0,0,0.18);
}
.tradeoff-title {
  text-align: center; font-size: 0.75rem; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 18px;
  display: flex; justify-content: space-between; align-items: center;
}
.tradeoff-title .t-left  { color: #69f0ae; }
.tradeoff-title .t-right { color: #ff8a65; }
.tradeoff-title .t-mid   { color: #90a4ae; font-weight: 400; font-size: 0.68rem; }
.tradeoff-bar {
  position: relative; height: 8px; border-radius: 4px;
  background: linear-gradient(to right, #69f0ae 0%, #29b6f6 35%, #ffd54f 65%, #ff8a65 100%);
  margin-bottom: 0;
}
.tradeoff-axis {
  display: flex; justify-content: space-between;
  margin-top: 2px; margin-bottom: 20px;
}
.tradeoff-axis span { font-size: 0.65rem; color: #546e7a; }
.tradeoff-pins {
  position: relative; height: 90px; margin-bottom: 0;
}
.t-pin {
  position: absolute; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center; gap: 4px;
}
.t-pin-dot {
  width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.2);
}
.t-pin-label {
  background: rgba(255,255,255,0.07); border-radius: 6px;
  padding: 3px 9px; font-size: 0.75rem; font-weight: 700;
  white-space: nowrap; border: 1px solid rgba(255,255,255,0.1);
}
.t-pin-desc {
  font-size: 0.62rem; color: #78909c; text-align: center;
  white-space: nowrap; line-height: 1.4;
}
.t-green  { color: #69f0ae; }
.t-teal   { color: #4dd0e1; }
.t-blue   { color: #29b6f6; }
.t-yellow { color: #ffd54f; }
.t-orange { color: #ff8a65; }
.t-pin-dot.c-green  { background: #69f0ae; border-color: #69f0ae; }
.t-pin-dot.c-teal   { background: #4dd0e1; border-color: #4dd0e1; }
.t-pin-dot.c-blue   { background: #29b6f6; border-color: #29b6f6; }
.t-pin-dot.c-yellow { background: #ffd54f; border-color: #ffd54f; }
.t-pin-dot.c-orange { background: #ff8a65; border-color: #ff8a65; }

/* ── SLA document template (Ch14) ── */
.sla-doc {
  background: #fafafa; border: 1px solid #dde2f5; border-radius: 12px;
  overflow: hidden; margin: 20px 0 24px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.07);
  font-size: 0.85rem;
}
.sla-doc-header {
  background: linear-gradient(135deg, #1e2433 0%, #283593 100%);
  padding: 16px 24px; color: #fff;
}
.sla-doc-header h3 {
  margin: 0 0 4px; font-size: 1rem; font-weight: 700; color: #fff;
  border: none; padding: 0;
}
.sla-doc-meta {
  font-size: 0.72rem; color: #9fa8da; display: flex; gap: 16px;
}
.sla-doc-meta span::before { content: '• '; }
.sla-section {
  padding: 14px 24px; border-bottom: 1px solid #e8eaf6;
}
.sla-section:last-child { border-bottom: none; }
.sla-section-title {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.07em;
  text-transform: uppercase; color: #3949ab; margin: 0 0 10px;
  display: flex; align-items: center; gap: 6px;
}
.sla-section-title::before {
  content: ''; display: inline-block; width: 3px; height: 14px;
  background: #3949ab; border-radius: 2px;
}
.sla-meta-list {
  display: flex; gap: 20px; flex-wrap: wrap;
  list-style: none; margin: 0; padding: 0;
}
.sla-meta-list li {
  font-size: 0.8rem; color: #424242;
}
.sla-meta-list li strong { color: #1a237e; }
.sla-table {
  width: 100%; border-collapse: collapse; font-size: 0.8rem;
}
.sla-table th {
  background: #e8eaf6; color: #1a237e; font-weight: 700;
  padding: 7px 12px; text-align: left; white-space: nowrap;
  border-bottom: 2px solid #c5cae9;
}
.sla-table td {
  padding: 7px 12px; border-bottom: 1px solid #eeeeee; color: #333;
  vertical-align: middle;
}
.sla-table tr:last-child td { border-bottom: none; }
.sla-table tr:hover td { background: #f0f2ff; }
.sla-badge {
  display: inline-block; padding: 2px 8px; border-radius: 8px;
  font-size: 0.7rem; font-weight: 700;
}
.sla-warn     { background: #fff9c4; color: #f57f17; }
.sla-error    { background: #ffe0b2; color: #e65100; }
.sla-critical { background: #ffcdd2; color: #b71c1c; }
.sla-code     { font-family: 'SFMono-Regular', monospace; font-size: 0.78rem; color: #5c6bc0; background: #f0f2ff; padding: 1px 5px; border-radius: 3px; }

/* ── Metric-matrix table (Ch12) ── */
.mm-table {
  width: 100%; border-collapse: collapse; margin: 20px 0 24px;
  font-size: 0.83rem; border-radius: 10px; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.mm-table thead th {
  background: #1e2433; color: #7ec8e3;
  padding: 10px 14px; text-align: center; font-weight: 700;
  letter-spacing: 0.04em; font-size: 0.82rem; white-space: nowrap;
}
.mm-table thead th:first-child { text-align: left; padding-left: 16px; min-width: 220px; }
.mm-table .mm-gate-row td {
  background: #2a3150; color: #9fa8da;
  padding: 6px 14px; font-size: 0.76rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; border: none;
  border-top: 2px solid #3949ab;
}
.mm-table tbody tr:not(.mm-gate-row) { border-bottom: 1px solid #e8eaf6; }
.mm-table tbody tr:not(.mm-gate-row):nth-child(even) { background: #f5f7ff; }
.mm-table tbody tr:not(.mm-gate-row):hover { background: #eef0ff; }
.mm-table td { padding: 8px 14px; color: #333; vertical-align: middle; }
.mm-table td:not(:first-child) { text-align: center; white-space: nowrap; }
.mm-ok  { color: #1b5e20; font-weight: 700; }
.mm-opt { color: #e65100; font-size: 0.78rem; font-weight: 600; }
.mm-rag { color: #1565c0; font-size: 0.78rem; font-weight: 600; }
.mm-na  { color: #bdbdbd; font-size: 0.78rem; }

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
@media (max-width: 768px) {
  :root { --sidebar-w: 0px; }
  #sidebar { display: none; }
  #main { margin-left: 0; padding: 20px; }
}

/* ── lecture-forge editor figure 호환 (Tailwind 유틸리티 대체) ── */
.my-6    { margin-top: 1.5rem; margin-bottom: 1.5rem; }
.text-center { text-align: center; }
.max-w-full  { max-width: 100%; height: auto; }
.rounded     { border-radius: 0.375rem; }
.shadow      { box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08); }
.mx-auto     { margin-left: auto; margin-right: auto; display: block; }

/* ── 외부 이미지 (터미널·대시보드 스크린샷 등) ── */
img:not(.mermaid img) {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 12px auto;
  border-radius: 6px;
}
figure {
  margin: 24px 0;
  text-align: center;
}
figcaption {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-top: 8px;
  font-style: italic;
  line-height: 1.5;
}

/* ── Search ── */
#search-wrap {
  padding: 8px 12px 10px;
  background: rgba(0,0,0,0.18);
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
#search-box {
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(255,255,255,0.1);
  color: #fff;
  font-size: 0.8rem;
  font-family: var(--font-body);
  outline: none;
  box-sizing: border-box;
  transition: background 0.15s, border-color 0.15s;
}
#search-box::placeholder { color: rgba(255,255,255,0.38); }
#search-box:focus {
  background: rgba(255,255,255,0.17);
  border-color: rgba(255,255,255,0.3);
}
#search-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 5px;
  min-height: 18px;
}
#search-count { font-size: 0.7rem; color: rgba(255,255,255,0.5); }
#search-nav { display: flex; gap: 3px; }
#search-nav button {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  color: rgba(255,255,255,0.65);
  border-radius: 4px;
  padding: 1px 7px;
  font-size: 0.73rem;
  cursor: pointer;
  line-height: 1.5;
  transition: background 0.12s;
}
#search-nav button:hover:not(:disabled) { background: rgba(255,255,255,0.18); color: #fff; }
#search-nav button:disabled { opacity: 0.28; cursor: default; }
mark.search-hit {
  background: #ffeb3b;
  color: #212121;
  border-radius: 2px;
  padding: 0 1px;
  font-style: inherit;
  font-weight: inherit;
}
mark.search-hit.current {
  background: #ff9800;
  color: #fff;
  outline: 2px solid #ff9800;
}
@media print { #search-wrap { display: none; } mark.search-hit { background: none; } }
</style>
</head>
<body>
"""

HTML_SIDEBAR_START = (
    '<nav id="sidebar"><div id="sidebar-header">실전 AI 에이전트<br>하네스 엔지니어링'
    '<span class="subtitle">Agent-Evaluator를 활용한<br>품질 평가와 배포 자동화</span>'
    f'<small>Agent-Evaluator v{SDK_VERSION}</small></div>'
    '<div id="search-wrap">'
    '<input id="search-box" type="search" placeholder="\U0001f50d 본문 검색…" autocomplete="off" spellcheck="false">'
    '<div id="search-meta">'
    '<span id="search-count"></span>'
    '<div id="search-nav">'
    '<button id="search-prev" disabled title="이전 결과">▲</button>'
    '<button id="search-next" disabled title="다음 결과">▼</button>'
    '</div>'
    '</div>'
    '</div>'
    '<div id="toc">'
)
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
<script>
/* ── In-page Search ── */
(function () {
  var box   = document.getElementById('search-box');
  var count = document.getElementById('search-count');
  var bPrev = document.getElementById('search-prev');
  var bNext = document.getElementById('search-next');
  var main  = document.getElementById('main');
  if (!box || !main) return;

  var hits = [], cur = -1, timer;

  function clearMarks() {
    main.querySelectorAll('mark.search-hit').forEach(function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    main.normalize();
    hits = []; cur = -1;
  }

  function applySearch(term) {
    clearMarks();
    if (!term) { count.textContent = ''; bPrev.disabled = bNext.disabled = true; return; }
    var lterm = term.toLowerCase();
    var tlen  = term.length;
    var walker = document.createTreeWalker(
      main, NodeFilter.SHOW_TEXT,
      { acceptNode: function (node) {
          var el = node.parentElement;
          if (!el) return NodeFilter.FILTER_REJECT;
          if (el.closest('pre, code, .mermaid, script, style, mark'))
            return NodeFilter.FILTER_REJECT;
          return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }
      }
    );
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      var val  = node.nodeValue;
      var lval = val.toLowerCase();
      if (lval.indexOf(lterm) === -1) return;
      var frag = document.createDocumentFragment();
      var last = 0, idx;
      while ((idx = lval.indexOf(lterm, last)) !== -1) {
        if (idx > last) frag.appendChild(document.createTextNode(val.slice(last, idx)));
        var mark = document.createElement('mark');
        mark.className = 'search-hit';
        mark.textContent = val.slice(idx, idx + tlen);
        frag.appendChild(mark);
        hits.push(mark);
        last = idx + tlen;
      }
      if (last < val.length) frag.appendChild(document.createTextNode(val.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    if (hits.length) {
      cur = 0; setCurrent(); count.textContent = hits.length + '건 발견';
    } else {
      count.textContent = '일치 없음';
    }
    bPrev.disabled = bNext.disabled = hits.length < 2;
  }

  function setCurrent() {
    hits.forEach(function (m, i) { m.classList.toggle('current', i === cur); });
    if (hits[cur]) hits[cur].scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (hits.length > 1) count.textContent = (cur + 1) + ' / ' + hits.length + '건';
  }

  box.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { applySearch(box.value.trim()); }, 250);
  });
  box.addEventListener('keydown', function (e) {
    if (e.key === 'Enter')  { e.preventDefault(); if (hits.length) { cur = (cur + 1) % hits.length; setCurrent(); } }
    if (e.key === 'Escape') { box.value = ''; clearMarks(); count.textContent = ''; bPrev.disabled = bNext.disabled = true; box.blur(); }
  });
  bNext.addEventListener('click', function () {
    if (!hits.length) return; cur = (cur + 1) % hits.length; setCurrent();
  });
  bPrev.addEventListener('click', function () {
    if (!hits.length) return; cur = (cur - 1 + hits.length) % hits.length; setCurrent();
  });
  /* '/' 키로 검색창 포커스 */
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault(); box.focus(); box.select();
    }
  });
})();
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
    ("chapter", "Chapter_01", "ch01", "01. AI 에이전트 평가란?"),
    ("chapter", "Chapter_02", "ch02", "02. Agent-Evaluator 첫 시작"),
    ("part", "Part II — 지표 시스템"),
    ("chapter", "Chapter_03", "ch03", "03. Harness Engineering 기초"),
    ("chapter", "Chapter_04", "ch04", "04. Gate A — 목표달성"),
    ("chapter", "Chapter_05", "ch05", "05. Gate B — 행동무결성"),
    ("chapter", "Chapter_06", "ch06", "06. Gate C — 신뢰성"),
    ("chapter", "Chapter_07", "ch07", "07. Gate D — 성능계약"),
    ("chapter", "Chapter_08", "ch08", "08. Gate E — 보안경계"),
    ("chapter", "Chapter_09", "ch09", "09. Gate F — 다중에이전트"),
    ("chapter", "Chapter_10", "ch10", "10. Gate G — 운영관측성"),
    ("part", "Part III — 개발자 가이드"),
    ("chapter", "Chapter_11", "ch11", "11. 평가데이터 설계"),
    ("chapter", "Chapter_12", "ch12", "12. 데코레이터 완전정복"),
    ("chapter", "Chapter_13", "ch13", "13. 프레임워크 통합"),
    ("part", "Part IV — QA 관리자 가이드"),
    ("chapter", "Chapter_14", "ch14", "14. 임계값 & 품질기준"),
    ("chapter", "Chapter_15", "ch15", "15. 대시보드 시각화"),
    ("chapter", "Chapter_16", "ch16", "16. 알림시스템 운영"),
    ("chapter", "Chapter_17", "ch17", "17. 주간·월간 품질리뷰"),
    ("part", "Part V — 프로덕션 운영"),
    ("chapter", "Chapter_18", "ch18", "18. CI/CD 품질게이팅"),
    ("chapter", "Chapter_19", "ch19", "19. Phoenix OTEL 모니터링"),
    ("chapter", "Chapter_20", "ch20", "20. 프로덕션 배포전략"),
    ("chapter", "Chapter_21", "ch21", "21. 종합 실무파이프라인"),
    ("part", "Part VI — 실전 이식 가이드"),
    ("chapter", "Chapter_22", "ch22", "22. 기존 프로젝트 해부"),
    ("chapter", "Chapter_23", "ch23", "23. Gate 매핑 전략"),
    ("chapter", "Chapter_24", "ch24", "24. 첫 번째 이식"),
    ("chapter", "Chapter_25", "ch25", "25. 전체 통합"),
    ("chapter", "Chapter_26", "ch26", "26. CI/CD 완성"),
    ("part", "Part VII — 실시간 가드레일"),
    ("chapter", "Chapter_27", "ch27", "27. LiveGuardrail과 OpenCode"),
    ("chapter", "Chapter_28", "ch28", "28. 로컬 자가교정 ADE 구축"),
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
    ("appendix", "M_프로덕션", "appM", "App M. 프로덕션 운영 체크리스트"),
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
    stem = unicodedata.normalize("NFC", stem)
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
        saved_blocks.append(("custom_html", m.group(1).strip()))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"@@HTML_START@@\s*\n(.*?)@@HTML_END@@", extract_html_block, text, flags=re.DOTALL)

    # ② mermaid 블록 추출
    def extract_mermaid(m: re.Match) -> str:
        saved_blocks.append(("mermaid", m.group(1)))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    text = re.sub(r"```mermaid\s*\n(.*?)```", extract_mermaid, text, flags=re.DOTALL)

    # ③ blockquote 내부 fenced code block 추출
    # Python markdown의 fenced_code 확장은 blockquote 안의 코드 블록을 파싱하지 못하므로
    # markdown 변환 전에 raw HTML로 미리 변환해 saved_blocks에 보관한다.
    def extract_bq_code(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        body = m.group(2)
        lines: list[str] = []
        for line in body.split("\n"):
            if line.startswith("> "):
                lines.append(line[2:])
            elif line.rstrip() == ">":
                lines.append("")
        code = "\n".join(lines).rstrip("\n")
        escaped = _html_escape(code)
        cls_attr = f' class="language-{lang}"' if lang else ""
        raw_html = f"<pre><code{cls_attr}>{escaped}</code></pre>"
        saved_blocks.append(("html", raw_html))
        return f"@@BLOCK_{len(saved_blocks) - 1}@@"

    # ^> ```lang  ~  ^> ``` (end-of-line) を非貪欲 DOTALL で一括抽出
    # ※ 닫는 ``` 뒤에 \s*$ 를 붙여 `> ```python` 같은 열기 마커와 혼동하지 않도록 함
    text = re.sub(
        r"^> ```(\w*)\n(.*?)^> ```\s*$",
        extract_bq_code,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )

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
            return f'<div class="mermaid" data-lf-preserve="mermaid">{content}</div>'
        if kind == "custom_html":
            # <style> 블록은 div 래핑 시 브라우저 경고 발생 — 그대로 반환
            if content.strip().startswith("<style"):
                return content
            return f'<div class="lf-html-block" data-lf-preserve="html">{content}</div>'
        return content  # blockquote 내 코드 블록 등 — 그대로 반환

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


def demote_headings(html: str) -> str:
    """섹션 body 헤딩을 1레벨 강등 (lecture-forge editor 호환).

    build_book() 전용 — build_pdf_chapters.py 는 미적용.
    역순 치환(h4→h5 먼저)으로 이중 치환 방지.
    h1→h2, h2→h3, h3→h4, h4→h5 (h5, h6 는 그대로).
    """
    for level in range(4, 0, -1):
        html = re.sub(
            rf'(</?h){level}(\s|>)',
            lambda m, lv=level: f'{m.group(1)}{lv + 1}{m.group(2)}',
            html,
        )
    return html


def build_toc_html() -> str:
    lines: list[str] = []
    for item in TOC_STRUCTURE:
        if item[0] == "part":
            lines.append(f'<a class="part-heading">{item[1]}</a>')
        elif item[0] == "chapter":
            lines.append(f'<a class="chapter toc-link" href="#{item[2]}">{item[3]}</a>')
        elif item[0] == "appendix":
            lines.append(f'<a class="appendix toc-link" href="#{item[2]}">{item[3]}</a>')
    return "\n".join(lines)


def _rewrite_img_paths_for_book(html_str: str, md_dir: Path) -> str:
    """img src 의 상대 경로를 OUTPUT_FILE(BOOK_DIR) 기준 상대 경로로 재작성한다.

    마크다운 파일은 하위 디렉토리(Part_I_기초/ 등)에 있으므로
    md 파일 기준 상대 경로를 그대로 쓰면 BOOK_DIR 에 저장된 단일 HTML 에서 깨진다.
    http(s)://, data:, file:// 로 시작하는 src 는 그대로 유지한다.
    """
    def _to_rel(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:", "file://", "#")):
            return m.group(0)
        abs_path = (md_dir / src).resolve()
        try:
            rel_path = abs_path.relative_to(BOOK_DIR)
            return f'src="{rel_path}"'
        except ValueError:
            return f'src="{abs_path}"'
    return re.sub(r'src="([^"]+)"', _to_rel, html_str)


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
        html_body = _rewrite_img_paths_for_book(html_body, fpath.parent)

        sid = stem_id(fpath)

        # title 추출 — demote_headings() 적용 전 h1이 존재할 때 수행
        _h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html_body, re.DOTALL)
        _title_text = re.sub(r'<[^>]+>', '', _h1.group(1)).strip() if _h1 else sid

        # lecture-forge editor 호환: h1→h2, h2→h3, h3→h4, h4→h5
        html_body = demote_headings(html_body)

        parts.append(
            f'<section class="chapter-section" id="{sid}" data-section-title="{_html_escape(_title_text)}">'
            f'\n{html_body}\n</section>'
        )

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
