"""
ch25_quickeval_entry.py — 첫 번째 이식: 30분 안에 첫 숫자 얻기
===============================================================
Book Chapter 25 — 첫 번째 이식

침습도(Invasiveness) 최소화 원칙으로 기존 코드를 건드리지 않고
첫 번째 측정값을 얻는 방법을 실습한다.

  섹션 1: 침습도 레벨 정의 — Level 0 ~ Level 3
  섹션 2: Level 0 — 반환값 래핑 (str 반환 함수, @eval_session.qa)
  섹션 3: 위임 어댑터 패턴 — Pydantic 반환 클래스 계측 (기존 파일 수정 0줄)
  섹션 4: 첫 번째 측정 결과 해석
  섹션 5: 다음 단계 결정 기준

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch25_quickeval_entry.py

결과:
    results/ch25_quickeval_entry.json  (+ .html)
"""

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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
                       service_name="ch24-quickeval-entry")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

print("=" * 60)
print("  Ch25: 첫 번째 이식 — 30분 안에 첫 숫자 얻기")
print("=" * 60)

# ===========================================================================
# 섹션 1: 침습도 레벨 정의
# ===========================================================================
print("\n=== 섹션 1: 침습도(Invasiveness) 레벨 정의 ===")

print("""
  ┌─────────┬─────────────────────┬────────────────────────────────┬──────────┐
  │ 레벨    │ 방법                │ 기존 코드 수정                 │ 소요시간 │
  ├─────────┼─────────────────────┼────────────────────────────────┼──────────┤
  │ Level 0 │ 반환값 래핑         │ 0줄 (str 반환 함수에 적용)     │ 5분      │
  │ Level 0 │ 위임 어댑터 클래스  │ 0줄 (Pydantic 반환 클래스)     │ 10~20분  │
  │ Level 1 │ record_task 삽입    │ 2–5줄 추가                    │ 15분     │
  │ Level 2 │ 내부 훅 추가        │ 10–20줄 수정                  │ 1–2시간  │
  │ Level 3 │ 아키텍처 변경       │ 광범위한 리팩터                │ 1–3일    │
  └─────────┴─────────────────────┴────────────────────────────────┴──────────┘

  1단계 이식 = Level 0만 사용 (위임 어댑터 포함)
  목표: 기존 코드 동작을 바꾸지 않고 측정만 추가한다.
""")

# ===========================================================================
# 섹션 2: Level 0 — 반환값 래핑 (str 반환 함수)
# ===========================================================================
print("\n=== 섹션 2: Level 0 — 반환값 래핑 (@eval_session.qa) ===")

print("""
  str을 반환하는 함수는 @eval_session.qa 데코레이터를 씌우는 것만으로 계측 완료.

  [기존 코드 — 수정 전]
  ─────────────────────────────────────────────────────────
  class QAAgent:
      def answer(self, question: str) -> dict:
          result = self.llm.invoke(self.qa_prompt | question)
          return {"answer": result.content, "confidence": 0.85}

  [Level 0 래핑 — 기존 코드 0줄 수정, 새 래퍼 함수만 추가]
  ─────────────────────────────────────────────────────────
  eval_session = QuickEval("lecture_eval_results/")

  @eval_session.qa
  def measured_answer(question: str, ground_truth: str = "") -> str:
      result = qa_agent.answer(question)     # 기존 호출 그대로
      return result["answer"]               # str로 반환 (데코레이터 요구사항)
""")

eval_session = QuickEval(_OUTPUT_DIR)


class MockQAAgent:
    """기존 QA 에이전트를 흉내내는 mock — 수정 금지."""

    KNOWLEDGE_BASE = {
        "FastAPI 라우터 정의 방법":   "APIRouter()를 사용해 라우터를 정의하고 app.include_router()로 등록합니다.",
        "Pydantic 모델 정의":         "BaseModel을 상속받아 필드를 타입 힌트로 선언합니다.",
        "의존성 주입 방법":           "Depends()를 파라미터 기본값으로 사용합니다.",
        "비동기 엔드포인트 작성법":   "async def와 await를 사용합니다.",
        "미들웨어 추가 방법":         "app.add_middleware()로 미들웨어 클래스를 등록합니다.",
    }

    def answer(self, question: str) -> dict:
        """기존 에이전트 인터페이스 — 수정 금지."""
        # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
        #   예) result = self.llm.invoke(self.qa_prompt | question)
        #       return {"answer": result.content, "confidence": 0.85}
        time.sleep(0.3 + random.uniform(0, 0.5))
        answer = self.KNOWLEDGE_BASE.get(question, f"{question}에 대한 답변을 찾을 수 없습니다.")
        return {"answer": answer, "confidence": random.uniform(0.6, 0.95)}


qa_agent = MockQAAgent()

@eval_session.qa
def measured_answer(question: str, ground_truth: str = "") -> str:
    result = qa_agent.answer(question)
    return result["answer"]


print("  Level 0 래핑 적용 — QAAgent.answer() 5개 호출:")
QA_PAIRS = [
    ("FastAPI 라우터 정의 방법",   "APIRouter"),
    ("Pydantic 모델 정의",         "BaseModel"),
    ("의존성 주입 방법",           "Depends"),
    ("비동기 엔드포인트 작성법",   "async def"),
    ("미들웨어 추가 방법",         "add_middleware"),
]
for question, expected_keyword in QA_PAIRS:
    answer = measured_answer(question, ground_truth=expected_keyword)
    hit = "✅" if expected_keyword in answer else "⚠️"
    print(f"  {hit} Q: {question[:22]:<22}  → '{answer[:40]}...'")

# ===========================================================================
# 섹션 3: 위임 어댑터 패턴 — Pydantic 반환 클래스 계측
# ===========================================================================
print("\n\n=== 섹션 3: 위임 어댑터 패턴 — Pydantic 반환 에이전트 계측 ===")

print("""
  @eval_session.qa 데코레이터는 함수가 str을 반환해야 동작한다.
  Lecture_forge의 ContentWriterAgent.write_section()은
  SectionContent(Pydantic 모델)를 반환하므로 직접 적용할 수 없다.

  해결책: 위임 어댑터(Delegation Adapter) 패턴
    1. 기존 에이전트 파일을 전혀 건드리지 않는다.
    2. 새 파일(eval/adapters.py)에 어댑터 클래스를 작성한다.
    3. 진입점(create.py)에서 에이전트 인스턴스를 어댑터로 교체한다.

  [기존 에이전트 — 수정 금지]
  ─────────────────────────────────────────────────────────
  class ContentWriterAgent:
      def write_section(self, section, curriculum) -> SectionContent:
          contexts = self._query_knowledge(section, curriculum)
          content = self._generate_content(section, curriculum, contexts)
          return content   # Pydantic 모델 반환

  [위임 어댑터 — 새 파일 eval/adapters.py]
  ─────────────────────────────────────────────────────────
  class ContentWriterAdapter:
      def __init__(self, agent, monitor, learning_objectives):
          self._agent = agent
          self._monitor = monitor

      def write_section(self, section, curriculum, available_images=None):
          start = time.perf_counter()
          has_error = False; error_msg = None; result = None
          try:
              result = self._agent.write_section(section, curriculum, available_images)
          except Exception as exc:
              has_error = True; error_msg = str(exc); raise
          finally:
              elapsed = time.perf_counter() - start
              content_text = getattr(result, "markdown_content", "") if result else ""
              ground_truth = " ".join(getattr(section, "learning_outcomes", []) or [])
              self._monitor.record_task(create_taskresult(
                  task_id=f"section_{getattr(section, 'id', '?')}",
                  question=f"섹션 '{getattr(section, 'title', '')}' 콘텐츠 작성",
                  response=content_text, ground_truth=ground_truth,
                  execution_time=elapsed, task_type="document_creation",
                  has_error=has_error, error_message=error_msg,
                  extra={"phase": "content_writing",
                         "word_count": getattr(result, "word_count", 0) if result else 0},
              
                  use_korean_tokenizer=True,
              ))
          return result   # 원본 반환값 그대로

      def __getattr__(self, name):          # 나머지는 원본으로 투명 위임
          return getattr(self._agent, name)

  [create.py 에서 교체 — 3줄]
  ─────────────────────────────────────────────────────────
  writer = ContentWriterAgent(vector_store=vs)
  if _eval_monitor:
      writer = ContentWriterAdapter(writer, _eval_monitor, objectives)
  # 이후 writer.write_section() 호출은 기존과 완전히 동일
""")


# ── mock Pydantic-like 반환 객체 ─────────────────────────────────────────────
@dataclass
class MockSection:
    id: str
    title: str
    learning_outcomes: List[str]


@dataclass
class MockSectionContent:
    markdown_content: str
    word_count: int


class MockContentWriterAgent:
    """기존 ContentWriterAgent mock — 이 파일을 수정하지 않는 것이 핵심."""

    def write_section(self, section: MockSection, curriculum, available_images=None) -> MockSectionContent:
        """Pydantic 모델(SectionContent)을 반환하는 기존 에이전트 메서드."""
        # TODO(현업 적용): 아래 Mock 구현을 실제 ContentWriter LLM 호출로 교체하세요.
        #   예) return self._generate_content(section, curriculum, available_images)
        time.sleep(0.4 + random.uniform(0, 0.6))
        outcomes_text = " ".join(section.learning_outcomes)
        word_count = random.randint(600, 1200)
        content = f"## {section.title}\n\n{outcomes_text}에 대한 내용입니다.\n\n" + ("본문 " * (word_count // 5))
        return MockSectionContent(markdown_content=content, word_count=word_count)

    def get_stats(self):
        return {"total_sections_written": 99}   # __getattr__ 위임 테스트용


# ── 위임 어댑터 구현 ──────────────────────────────────────────────────────────
class ContentWriterAdapterDemo:
    """ContentWriterAgent를 감싸 write_section()을 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor,
                 learning_objectives: List[str]) -> None:
        self._agent = agent
        self._monitor = monitor
        self._learning_objectives = learning_objectives

    def write_section(self, section: MockSection, curriculum,
                      available_images=None) -> MockSectionContent:
        task_id = f"section_{section.id}"
        start = time.perf_counter()
        has_error = False
        error_msg: Optional[str] = None
        result = None
        try:
            result = self._agent.write_section(section, curriculum, available_images)
        except Exception as exc:
            has_error = True
            error_msg = str(exc)
            raise
        finally:
            elapsed = time.perf_counter() - start
            content_text = result.markdown_content if result else ""
            ground_truth = " ".join(section.learning_outcomes)
            self._monitor.record_task(create_taskresult(
                task_id=task_id,
                question=f"섹션 '{section.title}' 콘텐츠 작성",
                response=content_text,
                ground_truth=ground_truth,        # Gate A: 학습목표 키워드 오버랩
                execution_time=elapsed,           # Gate D: SLA P95
                task_type="document_creation",
                has_error=has_error,              # Gate C: TCR 실패 집계
                error_message=error_msg,
                extra={
                    "phase": "content_writing",   # Gate G: 단계별 지연 분석
                    "section_id": section.id,
                    "word_count": result.word_count if result else 0,
                },
            
                use_korean_tokenizer=True,
            ))
        return result   # 원본과 완전히 동일한 반환값

    def __getattr__(self, name: str):
        """계측하지 않는 속성/메서드는 원본으로 투명하게 위임."""
        return getattr(self._agent, name)


# ── 위임 어댑터 실습 ──────────────────────────────────────────────────────────
monitor_adapter = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

base_agent = MockContentWriterAgent()
writer = ContentWriterAdapterDemo(
    agent=base_agent,
    monitor=monitor_adapter,
    learning_objectives=["FastAPI 핵심 개념 이해", "REST API 설계", "의존성 주입"],
)

SECTIONS = [
    MockSection("s01", "FastAPI 기초 개요",         ["FastAPI 핵심 개념 이해"]),
    MockSection("s02", "라우터와 엔드포인트",        ["REST API 엔드포인트 설계"]),
    MockSection("s03", "의존성 주입 패턴",           ["의존성 주입으로 재사용"]),
    MockSection("s04", "데이터 모델링 (Pydantic)",   ["Pydantic으로 데이터 검증"]),
    MockSection("s05", "비동기 처리 및 성능",        ["async/await 패턴 활용"]),
]

print("  위임 어댑터 적용 — write_section() 5개 호출:")
for section in SECTIONS:
    content: MockSectionContent = writer.write_section(section, curriculum=None)
    print(f"  ✅ {section.title[:22]:<22}  단어수={content.word_count}  "
          f"(SectionContent 반환값 그대로)")

# __getattr__ 위임 확인
stats = writer.get_stats()
print(f"\n  __getattr__ 위임 확인: writer.get_stats() → {stats}")
print("  → 어댑터가 없는 메서드는 원본 에이전트로 투명하게 전달됨")

# ===========================================================================
# 섹션 4: 첫 번째 측정 결과 해석
# ===========================================================================
print("\n\n=== 섹션 4: 첫 번째 측정 결과 해석 ===")

report_adapter = monitor_adapter.generate_report()

print("""
  첫 번째 숫자를 얻었다. 이제 해석이 필요하다.

  ┌─────────────────────────────────────────────────────────┐
  │  해석 체크리스트                                        │
  ├─────────────────────────────────────────────────────────┤
  │  TCR < 80%    → 태스크 완료 기준 재검토 (너무 엄격?)    │
  │  Accuracy<50% → ground_truth 설계 개선 필요             │
  │  P95 > SLA    → 즉시 Gate D 추가                        │
  │  모두 100%    → ground_truth가 너무 쉬움                │
  └─────────────────────────────────────────────────────────┘
""")

print(f"  [위임 어댑터 — ContentWriter 5개 섹션 결과]")
print(f"  TCR:       {_tcr(report_adapter):.1f}%")
print(f"  Accuracy:  {_acc(report_adapter):.1f}%  (학습목표 키워드 → 본문 오버랩)")
print(f"  P95:       {_p95(report_adapter):.2f}초  (실제 LLM은 수십 초 예상)")
print(f"  총 태스크: {report_adapter.total_tasks}건")

print("""
  해석:
  · Accuracy 50–80% → ground_truth 키워드가 생성 본문에 얼마나 포함됐는지 측정
    (학습목표가 실제 콘텐츠에 반영되는지 — Gate A의 시작점)
  · P95 > 0.5초  → 실제 LLM 환경에서는 수십 초 예상
    → SLAConfig(p95_ms=45_000) 설정으로 모니터링 시작 (Ch26)
  · 기존 에이전트 파일 수정: 0줄
    → 어댑터를 제거하면 원래 코드로 즉시 복구 가능
""")

# ===========================================================================
# 섹션 5: 다음 단계 결정 기준
# ===========================================================================
print("\n=== 섹션 5: 다음 단계 결정 기준 ===")

print("""
  첫 번째 측정 후 다음을 결정한다:

  ① str 반환 함수 → Level 0 래핑 (@eval_session.qa)
    기준: 함수가 이미 str을 반환한다
    행동: 데코레이터 1줄 추가로 완료

  ② Pydantic/dict 반환 클래스 → 위임 어댑터 패턴
    기준: 에이전트 메서드가 복잡한 객체를 반환한다
    행동: eval/adapters.py 에 어댑터 클래스 작성

  ③ 중앙 모니터로 통합 (Level 2 진입)
    기준: 여러 에이전트의 측정값을 한 리포트로 보고 싶다
    행동: Ch26 전체 통합으로 이동

  Lecture_forge 권장 순서:
    1단계: QAAgent Level 0 래핑 (5분)               ← 섹션 2에서 완료
    2단계: ContentWriterAdapter 위임 어댑터 (20분)   ← 섹션 3에서 완료
    3단계: 4개 에이전트 어댑터 + 중앙 모니터 (1시간)  ← Ch26
    4단계: CI/CD 통합 (Ch27)
""")

monitor_adapter.save_to_file("ch25_quickeval_entry")
print("결과 저장 완료: results/ch25_quickeval_entry.json")
print("확인: agent-eval dashboard --results results/")

print("""
=== Ch25 첫 번째 이식 완료 요약 ===

  Level 0 래핑:       QAAgent — @eval_session.qa 래퍼 함수 (str 반환)
  위임 어댑터 패턴:   ContentWriterAdapter — Pydantic 반환 에이전트 계측

  두 경우 모두:
    · 기존 에이전트 파일 수정: 0줄
    · 기존 반환값: 완전히 동일
    · 첫 측정 결과: TCR / Accuracy / P95 확보

  핵심 원칙: 완벽한 측정이 아니라 빠른 첫 측정
    → 데이터가 있어야 Gate를 설계할 수 있다

  다음 단계: Ch26 전체 통합 — 4개 에이전트 어댑터 + 중앙 모니터 연결
""")
