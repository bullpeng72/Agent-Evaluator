"""
20_quickeval_demo.py — QuickEval + 신규 기능 통합 데모
=======================================================

이 예제는 v0.7.x에서 추가된 모든 개선 사항을 실증한다:

  1. QuickEval Facade         — 원스톱 설정 없이 바로 시작
  2. 프레임워크 어댑터 통합       — agent_eval(framework="langchain") 등
  3. TaskType Enum 직접 지원   — 문자열 대신 enum 사용 가능
  4. 프레임워크 어댑터 자동 추출  — tool_calls / state_transitions 자동
  5. SimpleTaskAlertRule      — TaskResult 기반 경량 알림
  6. auto_save / flush_every  — 대시보드 실시간 반영

실행:
    python Evaluator_Examples/20_quickeval_demo.py
"""

import random
import socket as _sock
import time
from pathlib import Path

_project_root = Path(__file__).parent.parent
_results_dir = str(_project_root / "results")

# Phoenix OTEL 연결
try:
    if _sock.socket().connect_ex(("localhost", 6006)) == 0:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name="20-quickeval-demo")
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 1: QuickEval — 가장 간단한 시작
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("섹션 1: QuickEval — 가장 간단한 시작")
print("=" * 60)

from agent_evaluator import QuickEval

# 1줄로 시작 (PerformanceMonitor 생성 불필요)
eval = QuickEval(_results_dir)

# @eval.qa — 괄호 없이 사용 가능
@eval.qa
def qa_agent(question: str, ground_truth: str = "") -> str:
    """기본 QA 에이전트."""
    answers = {
        "한국의 수도는?": "서울",
        "Python 창시자는?": "귀도 반 로섬",
        "지구의 반지름은?": "약 6,371km",
    }
    return answers.get(question, "모르겠습니다")

# @eval.tool_use — 도구 사용 에이전트
@eval.tool_use
def tool_agent(question: str, ground_truth: str = "") -> str:
    """도구 사용 에이전트 (시뮬레이션)."""
    return f"검색 결과: {question}에 대한 답변"

# @eval.rag — RAG 에이전트 (context_arg="context" 자동 설정)
@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    """RAG 에이전트."""
    if context:
        return f"컨텍스트 기반 답변: {context[:50]}..."
    return "컨텍스트 없음"

# @eval.code — 코드 생성 에이전트
@eval.code
def code_agent(question: str, ground_truth: str = "") -> str:
    """코드 생성 에이전트."""
    return f"def solution():\n    # {question}\n    pass"

# 실행
dataset = [
    ("한국의 수도는?", "서울"),
    ("Python 창시자는?", "귀도 반 로섬"),
    ("지구의 반지름은?", "약 6,371km"),
]

print("\n[QA 에이전트 실행]")
for q, gt in dataset:
    result = qa_agent(q, ground_truth=gt)
    print(f"  Q: {q} → A: {result}")

print("\n[도구 에이전트 실행]")
tool_agent("날씨 정보", ground_truth="맑음")

print("\n[RAG 에이전트 실행]")
rag_agent(
    "AI란 무엇인가?",
    context="인공지능(AI)은 컴퓨터 시스템이 인간의 지능을 모방하는 기술이다.",
    ground_truth="인간 지능을 모방하는 컴퓨터 기술",
)

print("\n[코드 에이전트 실행]")
code_agent("피보나치 수열을 구현하시오", ground_truth="def fib(n): ...")

# 요약 출력
summary = eval.summary()
print(f"\n[QuickEval 요약]")
print(f"  총 태스크: {summary['total_tasks']}")
print(f"  TCR: {summary['tcr']:.1f}%")
print(f"  Accuracy: {summary['accuracy']:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 2: TaskType Enum 직접 지원
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 2: TaskType Enum 직접 지원")
print("=" * 60)

from agent_evaluator import PerformanceMonitor, TaskType, agent_eval

monitor2 = PerformanceMonitor(output_dir=_results_dir)

# TaskType.QA → "qa" 자동 변환 (IDE 자동완성 + 런타임 안전)
@agent_eval(monitor2, TaskType.QA)
def enum_qa_agent(question: str, ground_truth: str = "") -> str:
    return f"답변: {question}"

@agent_eval(monitor2, TaskType.INFORMATION_RETRIEVAL)
def enum_rag_agent(question: str, ground_truth: str = "") -> str:
    return f"검색: {question}"

@agent_eval(monitor2, TaskType.CODE_GENERATION)
def enum_code_agent(question: str, ground_truth: str = "") -> str:
    return f"코드: {question}"

print("\n[TaskType Enum 데코레이터 실행]")
enum_qa_agent("한국의 수도는?", ground_truth="서울")
enum_rag_agent("AI 최신 논문", ground_truth="GPT-4 논문")
enum_code_agent("정렬 알고리즘 구현", ground_truth="def sort(arr): ...")
print("  ✅ TaskType Enum으로 task_type 지정 성공")


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 3: 프레임워크 어댑터 자동 추출
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 3: 프레임워크 어댑터 자동 추출")
print("=" * 60)

monitor3 = PerformanceMonitor(output_dir=_results_dir)

# LangChain 시뮬레이션 — intermediate_steps 포함 dict 반환
@agent_eval(monitor3, task_type="tool_use", framework="langchain")
def simulated_langchain_agent(question: str, ground_truth: str = "") -> dict:
    """LangChain AgentExecutor 응답 형식 시뮬레이션."""

    class FakeAction:
        def __init__(self, tool, tool_input):
            self.tool = tool
            self.tool_input = tool_input

    # AgentExecutor.invoke() 반환 형식
    return {
        "output": f"검색 결과: {question}",
        "intermediate_steps": [
            (FakeAction("search", {"query": question}), "관련 정보 발견"),
            (FakeAction("calculator", {"expr": "1+1"}), "2"),
        ],
    }

print("\n[LangChain 어댑터 자동 추출]")
result = simulated_langchain_agent("AI 시장 규모", ground_truth="$200B")
print(f"  응답: {result}")
print("  ✅ intermediate_steps → tool_calls 자동 변환")

# LangGraph 시뮬레이션 — messages 리스트 반환
@agent_eval(monitor3, task_type="reasoning", framework="langgraph")
def simulated_langgraph_agent(question: str, ground_truth: str = "") -> dict:
    """LangGraph invoke() 응답 형식 시뮬레이션."""

    class HumanMsg:
        def __init__(self, content):
            self.content = content
            self.tool_calls = []

    class AIMsg:
        def __init__(self, content):
            self.content = content
            self.tool_calls = [{"name": "search", "args": {"query": content}}]

    class ToolMsg:
        def __init__(self, content):
            self.content = content
            self.tool_calls = []

    return {
        "messages": [
            HumanMsg(question),
            AIMsg("검색 중..."),
            ToolMsg("검색 결과 반환"),
            AIMsg(f"최종 답변: {question}"),
        ]
    }

print("\n[LangGraph 어댑터 자동 추출]")
simulated_langgraph_agent("기후 변화의 원인", ground_truth="온실가스 배출")
print("  ✅ messages → state_transitions + graph_traversal 자동 변환")


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 4: SimpleTaskAlertRule — TaskResult 기반 경량 알림
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 4: SimpleTaskAlertRule — 경량 알림 시스템")
print("=" * 60)

from agent_evaluator import SimpleTaskAlertRule

monitor4 = PerformanceMonitor(output_dir=_results_dir)

# 알림 로그 수집 (테스트용)
alert_log = []

def mock_alert_handler(message: str, task_result) -> None:
    alert_log.append({"message": message, "task_id": task_result.task_id})
    print(f"  🔔 알림: {message[:80]}...")

@agent_eval(
    monitor4,
    task_type="qa",
    task_id_prefix="alert_demo",
    alert_rules=[
        SimpleTaskAlertRule(
            name="정확도 급락",
            condition=lambda r: r.accuracy_score < 0.5,
            handler=mock_alert_handler,
            severity="warning",
            cooldown=0.0,  # 데모를 위해 쿨다운 비활성화
        ),
        SimpleTaskAlertRule(
            name="응답 지연",
            condition=lambda r: r.execution_time > 2.0,
            handler=mock_alert_handler,
            severity="critical",
            cooldown=0.0,
        ),
    ]
)
def alert_demo_agent(question: str, ground_truth: str = "") -> str:
    """알림 데모 에이전트 — 의도적으로 낮은 정확도 응답."""
    time.sleep(0.01)
    # 틀린 답변 (낮은 accuracy_score 유발)
    return "모르겠습니다"

print("\n[SimpleTaskAlertRule 동작 테스트]")
for q, gt in [
    ("한국의 수도는?", "서울"),        # 오답 → 정확도 알림
    ("Python 창시자는?", "귀도 반 로섬"), # 오답 → 정확도 알림
]:
    alert_demo_agent(q, ground_truth=gt)

print(f"  총 알림 수: {len(alert_log)}")
for a in alert_log:
    print(f"    - [{a['task_id']}] 알림 발생")


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 5: auto_save + flush_every — 대시보드 실시간 반영
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 5: auto_save + flush_every — 대시보드 실시간 반영")
print("=" * 60)

# PerformanceMonitor.auto_save — N건마다 자동 저장
monitor5 = PerformanceMonitor(
    output_dir=_results_dir,
    auto_save=True,
    auto_save_interval=3,          # 3건마다 자동 저장
    auto_save_filename="demo_autosave",
)

@agent_eval(monitor5, task_type="qa", task_id_prefix="autosave")
def autosave_agent(question: str, ground_truth: str = "") -> str:
    return f"답변: {question}"

print("\n[auto_save 모니터 — 3건마다 자동 저장]")
for i, (q, gt) in enumerate(dataset * 2):  # 6번 실행
    autosave_agent(q, ground_truth=gt)
    print(f"  [{i+1}번째] '{q[:20]}...' 기록 완료", end="")
    if (i + 1) % 3 == 0:
        print(" ← 자동 저장 트리거")
    else:
        print()

# @agent_eval flush_every — 데코레이터 레벨 자동 저장
monitor6 = PerformanceMonitor(output_dir=_results_dir)

@agent_eval(
    monitor6,
    task_type="qa",
    task_id_prefix="flushevery",
    flush_every=2,                 # 2건마다 자동 저장
    flush_filename="demo_flush",
)
def flush_every_agent(question: str, ground_truth: str = "") -> str:
    return f"답변: {question}"

print("\n[flush_every=2 데코레이터 — 2건마다 자동 저장]")
for i, (q, gt) in enumerate(dataset):
    flush_every_agent(q, ground_truth=gt)
    print(f"  [{i+1}번째] 기록", end="")
    if (i + 1) % 2 == 0:
        print(" ← flush 트리거")
    else:
        print()


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 6: QuickEval.for_rag / for_security 팩토리
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 6: QuickEval 팩토리 메서드")
print("=" * 60)

# RAG 특화 — hallucination_detection 자동 활성화
eval_rag = QuickEval.for_rag(_results_dir)

@eval_rag.rag
def rag_with_hallucination(question: str, context: str = "", ground_truth: str = "") -> str:
    return "할루시네이션 포함 가능한 응답입니다."

print("\n[QuickEval.for_rag — hallucination 감지 활성화]")
rag_with_hallucination(
    "AI의 정의는?",
    context="AI는 인간 지능을 모방하는 기술이다.",
    ground_truth="인간 지능 모방 기술",
)
print("  ✅ hallucination_detection 자동 활성화됨")

# 보안 특화 — security_metrics 자동 활성화
eval_sec = QuickEval.for_security(_results_dir)

@eval_sec.tool_use
def secure_agent(question: str, ground_truth: str = "") -> str:
    return f"보안 처리된 응답: {question}"

print("\n[QuickEval.for_security — 보안 트래커 활성화]")
secure_agent("정상 입력", ground_truth="expected")
print("  ✅ InputSanitization, OutputLeakage 등 자동 활성화됨")


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 7: QuickEval.gate — CI/CD 품질 게이팅
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("섹션 7: QuickEval.gate — CI/CD 품질 게이팅")
print("=" * 60)

# 충분한 데이터로 기본 eval 게이팅 테스트
print("\n[eval.summary()]")
s = eval.summary()
for k, v in s.items():
    print(f"  {k}: {v:.1f}" if isinstance(v, float) else f"  {k}: {v}")

print("\n[eval.gate(tcr=0, accuracy=0) — 성공 예시]")
try:
    ok = eval.gate(tcr=0.0, accuracy=0.0)
    print(f"  ✅ 게이팅 통과: {ok}")
except SystemExit:
    print("  ❌ 게이팅 실패 (예상치 못한 실패)")


# ─────────────────────────────────────────────────────────────────────────────
# 최종 저장
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("최종 저장")
print("=" * 60)

saved_path = eval.save("20_quickeval_demo")
print(f"  📄 저장 완료: {saved_path}")

print("\n✅ 모든 섹션 완료!")
print("""
신규 기능 요약:
  1. QuickEval(_results_dir)          — 원스톱 시작
  2. @eval.qa / @eval.rag / ...      — 단축 데코레이터
  3. TaskType.QA (Enum)             — IDE 자동완성 지원
  4. agent_eval(framework=...)       — 프레임워크 어댑터 자동 추출
  5. intermediate_steps 자동 추출   — tool_calls/chain_steps 자동
  6. SimpleTaskAlertRule            — TaskResult 기반 경량 알림
  7. auto_save=True / flush_every=N — 대시보드 실시간 반영
  8. QuickEval.for_rag() / .for_security() — 특화 팩토리
""")
