"""
ch22_project_analysis.py — 기존 프로젝트 해부: 평가 가능한 단위 찾기
====================================================================
Book Chapter 22 — 기존 프로젝트 해부

분석 4단계 방법론을 3가지 가상 프로젝트 토폴로지에 적용한다.
Lecture_forge 실제 사례와 비교하며 "측정 가능한 단위"를 추출하는
원칙을 체득한다.

  섹션 1: 에이전트 토폴로지 3패턴 — 순차 / 루프 포함 / 병렬+집계
  섹션 2: LLM 호출 지점 열거 — 입력 타입·출력 형식·성공 기준 기록
  섹션 3: 기존 품질 지표 발굴 — 측정됨 vs 측정 안 됨 시각화
  섹션 4: 위험 지점 우선순위화 — 외부 입력·루프·비용 기준
  섹션 5: 측정 단위 추출 — 원자성·대표성·집계가능성 3원칙

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch22_project_analysis.py

결과:
    results/ch22_project_analysis.json  (+ .html)
"""

import random
import time
from pathlib import Path

from agent_evaluator import (
    PerformanceMonitor,
    QuickEval,
    create_taskresult,
    setup_otel,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")


def _tcr(report):
    return report.to_dict()['accuracy_metrics']['tcr']['tcr']

def _acc(report):
    return float(report.to_dict()['accuracy_metrics']['accuracy_scores']['overall_accuracy'])

def _p95(report):
    return float(report.to_dict()['efficiency_metrics']['latency']['p95'])

try:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006",
                       service_name="ch22-project-analysis")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

print("=" * 60)
print("  Ch22: 기존 프로젝트 해부 방법론 실습")
print("=" * 60)

# ===========================================================================
# 섹션 1: 에이전트 토폴로지 3패턴
# ===========================================================================
print("\n=== 섹션 1: 에이전트 토폴로지 3패턴 ===")

print("""
  패턴 A: 순차 파이프라인
  ─────────────────────────────────────────────────────
  [수집] → [분석] → [생성] → [검증] → [출력]

  특징: 각 에이전트가 이전 결과를 받아 처리
  주요 위험: 정보 전파 왜곡 (Gate F)
  핵심 측정 단위: 에이전트별 TaskResult

  패턴 B: 루프 포함 파이프라인 (Lecture_forge 형태)
  ─────────────────────────────────────────────────────
  [수집] → [설계] → [생성] (×N) → [평가]
                                  pass↓   fail↓
                                       [수정] (최대 3회)
                                          ↓
                                       [출력]

  특징: 품질 기준 미달 시 재시도
  주요 위험: 무한 루프 + 비용 폭발 (Gate B, D)
  핵심 측정 단위: 반복 단위(섹션) + 루프 카운트

  패턴 C: 병렬 + 집계
  ─────────────────────────────────────────────────────
  [입력] → [에이전트1] ─┐
          → [에이전트2] ─┼→ [집계] → [출력]
          → [에이전트3] ─┘

  특징: 여러 에이전트가 동시 실행 후 합의
  주요 위험: 합의 실패 + 충돌 해결 (Gate F)
  핵심 측정 단위: 각 에이전트 + 집계 결과
""")

# ===========================================================================
# 섹션 2: LLM 호출 지점 열거 실습
# ===========================================================================
print("\n=== 섹션 2: LLM 호출 지점 열거 ===")

# 가상 에이전트들 — 각각 다른 입출력 패턴
class MockLLMCall:
    """실제 LLM 호출을 시뮬레이션하는 목(mock)."""

    @staticmethod
    def call_with_clear_io(question: str) -> str:
        """입출력 명확 + 성공 기준 있음 → 1순위 측정 후보."""
        time.sleep(0.01)
        return f"답변: {question}에 대한 구체적 설명"

    @staticmethod
    def call_with_complex_state(context: dict, history: list) -> dict:
        """입출력 복잡 + 상태 의존 → 2단계에서 처리."""
        time.sleep(0.01)
        return {"result": "복잡한 결과", "state": context}

    @staticmethod
    def call_without_success_criteria(raw_text: str) -> str:
        """성공 기준 없음 → 최우선 측정 대상."""
        time.sleep(0.01)
        return f"처리됨: {raw_text[:50]}"


llm = MockLLMCall()

# 열거 결과 시뮬레이션
CALL_INVENTORY = [
    {
        "agent": "QAAgent.answer()",
        "input_type": "str (사용자 질문)",
        "output_format": "dict {'answer': str, 'confidence': float}",
        "success_criteria": "≥300단어 + 신뢰도>0.6",
        "risk_level": "medium",
        "first_target": True,
    },
    {
        "agent": "ContentWriter.write_section()",
        "input_type": "Section + RAG contexts (list[str])",
        "output_format": "SectionContent (Markdown)",
        "success_criteria": "단어수 범위 + 품질점수≥80",
        "risk_level": "high",
        "first_target": True,
    },
    {
        "agent": "PDFTranslator._translate_chunk()",
        "input_type": "영문 텍스트 청크",
        "output_format": "한국어 텍스트",
        "success_criteria": "없음 ← 위험!",
        "risk_level": "critical",
        "first_target": True,
    },
    {
        "agent": "CurriculumDesigner._generate_objectives()",
        "input_type": "주제 + 분석결과",
        "output_format": "JSON 배열 (학습목표 3-5개)",
        "success_criteria": "JSON 파싱 성공",
        "risk_level": "medium",
        "first_target": False,
    },
]

print(f"\n  LLM 호출 지점 전수 목록 ({len(CALL_INVENTORY)}개 발견):\n")
for i, item in enumerate(CALL_INVENTORY, 1):
    risk_icon = "🔴" if item["risk_level"] == "critical" else \
                "🟡" if item["risk_level"] == "high" else "🟢"
    target_str = " ← 1순위 측정 후보" if item["first_target"] else ""
    print(f"  [{i}] {risk_icon} {item['agent']}")
    print(f"       입력: {item['input_type']}")
    print(f"       출력: {item['output_format']}")
    print(f"       성공: {item['success_criteria']}{target_str}")
    print()

print("  핵심 발견: PDFTranslator에 성공 기준 없음 → 평가 도입 최우선 지점")

# ===========================================================================
# 섹션 3: 기존 품질 지표 발굴
# ===========================================================================
print("\n=== 섹션 3: 기존 품질 지표 발굴 ===")

EXISTING_METRICS = {
    "측정됨": [
        "QualityEvaluator.overall_score (0–100, 6차원 가중 평균)",
        "TokenTracker.total_cost (USD, phase별 분해)",
        "ContentWriter.word_count (섹션별 단어 수)",
        "QAAgent.confidence (0–1, RAG 검색 신뢰도)",
        "@make_api_retry 재시도 횟수 (로그)",
    ],
    "측정 안 됨": [
        "에이전트 간 정보 왜곡 (audience_level 전파 여부)",
        "외부 PDF 프롬프트 인젝션 탐지",
        "동일 주제 재실행 시 결과 일관성 (재현성)",
        "지난 8주간 품질 점수 추세",
        "어느 에이전트가 전체 시간의 몇 %를 사용하는가",
    ],
}

print(f"\n  이미 측정됨 ({len(EXISTING_METRICS['측정됨'])}개):")
for m in EXISTING_METRICS["측정됨"]:
    print(f"    ✅ {m}")

print(f"\n  측정 안 됨 — agent-evaluator가 채우는 공백 ({len(EXISTING_METRICS['측정 안 됨'])}개):")
for m in EXISTING_METRICS["측정 안 됨"]:
    print(f"    ❌ {m}")

print(f"\n  → 기존 지표({len(EXISTING_METRICS['측정됨'])}개)를 재활용하고,")
print(f"     공백({len(EXISTING_METRICS['측정 안 됨'])}개)을 Gate A–G로 채운다.")

# ===========================================================================
# 섹션 4: 위험 지점 우선순위화
# ===========================================================================
print("\n=== 섹션 4: 위험 지점 우선순위화 ===")

RISK_ANALYSIS = [
    {
        "기준": "외부 입력 경로",
        "발견": "ContentCollector가 PDF·URL 텍스트를 LLM 프롬프트에 직접 삽입",
        "위험도": "CRITICAL",
        "gate": "E",
        "우선순위": 1,
    },
    {
        "기준": "루프·반복 구조",
        "발견": "ContentWriter 확장 루프(max 3회) + RevisionAgent 루프(max 3회)",
        "위험도": "HIGH",
        "gate": "B, D",
        "우선순위": 2,
    },
    {
        "기준": "비용 폭발 가능",
        "발견": "섹션 수 × 루프 횟수 = 가변적 LLM 호출 (최악: N×3×3)",
        "위험도": "HIGH",
        "gate": "D",
        "우선순위": 3,
    },
    {
        "기준": "성공 기준 없는 호출",
        "발견": "PDFTranslator._translate_chunk() — 번역 품질 검증 없음",
        "위험도": "MEDIUM",
        "gate": "A",
        "우선순위": 4,
    },
]

print(f"\n  위험 지점 우선순위 목록:\n")
for item in RISK_ANALYSIS:
    risk_icon = "🔴" if item["위험도"] == "CRITICAL" else \
                "🟡" if item["위험도"] == "HIGH" else "🟢"
    print(f"  [{item['우선순위']}순위] {risk_icon} {item['위험도']} — {item['기준']}")
    print(f"         발견: {item['발견']}")
    print(f"         → Gate {item['gate']} 우선 적용")
    print()

# ===========================================================================
# 섹션 5: 측정 단위 추출 — 원자성·대표성·집계가능성
# ===========================================================================
print("\n=== 섹션 5: 측정 단위 추출 3원칙 ===")

monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

# 원칙 1: 원자성 — 섹션별 vs 강의 전체
print("\n  [원칙 1: 원자성] 하나의 TaskResult = 하나의 의미 있는 동작")
print("  잘못된 예: 강의 전체를 1개 TaskResult → TCR이 0% 또는 100%만 나옴")
print("  올바른 예: 섹션별 TaskResult → 어느 섹션이 문제인지 파악 가능\n")

SECTION_NAMES = [
    "FastAPI 기초 개요",
    "라우터와 엔드포인트",
    "의존성 주입 패턴",
    "데이터 모델링 (Pydantic)",
    "비동기 처리 및 성능",
]
LEARNING_OUTCOMES = [
    "FastAPI의 핵심 개념 이해",
    "REST API 엔드포인트 설계",
    "의존성 주입으로 코드 재사용",
    "Pydantic으로 데이터 검증",
    "async/await 패턴 활용",
]

for i, (section_name, outcome) in enumerate(zip(SECTION_NAMES, LEARNING_OUTCOMES)):
    quality_score = 75 + random.uniform(0, 20)
    word_count = 800 + random.randint(-200, 400)
    is_complete = quality_score >= 80 and word_count >= 600

    result = create_taskresult(
        task_id=f"section_{i+1:02d}",
        question=section_name,
        response=f"## {section_name}\n\n{outcome}에 대한 상세 설명..." * 10,
        ground_truth=outcome,
        execution_time=1.5 + random.uniform(0, 2.5),
        task_type="qa",
        metadata={
            "word_count":    word_count,
            "quality_score": round(quality_score, 1),
            "agent":         "content_writer",
            "section_index": i + 1,
        },
    
        use_korean_tokenizer=True,
    )
    monitor.record_task(result)

    status = "✅" if is_complete else "⚠️"
    print(f"  {status} 섹션 {i+1}: {section_name[:20]:<20}"
          f"  품질={quality_score:.0f}  단어={word_count}")

# 원칙 2: 대표성
print("\n  [원칙 2: 대표성] ground_truth가 완벽하지 않아도 된다")
print("  학습 목표 키워드를 ground_truth로 사용 → 의미 있는 Accuracy 측정 가능")

# 원칙 3: 집계 가능성
report = monitor.generate_report()
print(f"\n  [원칙 3: 집계가능성] {len(SECTION_NAMES)}개 섹션의 통계가 의미 있는 값을 만든다")
print(f"  TCR:      {_tcr(report):.1f}%  (완성 섹션 / 전체 섹션)")
print(f"  Accuracy: {_acc(report):.1f}%  (학습목표 키워드 오버랩 평균)")
print(f"  P95:      {_p95(report):.2f}초  (섹션 생성 P95 레이턴시)")
print(f"  총 태스크: {report.total_tasks}건")

# ===========================================================================
# 최종 저장
# ===========================================================================
monitor.save_to_file("ch22_project_analysis")
print("\n결과 저장 완료: results/ch22_project_analysis.json")
print("확인: agent-eval dashboard --results results/")

print("""
=== Ch22 분석 4단계 완료 요약 ===

  Step 1 토폴로지:  순차(A) + 루프(B) 복합 패턴 확인
                   외부 입력 경로 3개 (PDF·URL·사용자 질문) 식별

  Step 2 LLM 열거: 4개 호출 지점 발견
                   PDFTranslator — 성공 기준 없음 → 즉시 측정 필요

  Step 3 지표 발굴: 기존 5개 지표 재활용 가능
                   5개 측정 공백 → Gate A/B/D/E/F/G 매핑 예정

  Step 4 우선순위: E(보안) > B+D(루프+비용) > A(목표달성) 순
                   → Ch23에서 Gate Config로 번역 시작

  다음 단계: Ch23 Gate 매핑 — 실패 모드 카탈로그 작성
""")
