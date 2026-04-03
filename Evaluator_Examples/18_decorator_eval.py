"""
18_decorator_eval.py — @agent_eval 데코레이터 방식 평가
=========================================================
Opik의 ``@track`` 데코레이터처럼 한 줄만 추가하면 자동으로
agent-evaluator 평가가 적용됩니다.

실행:
    python Evaluator_Examples/18_decorator_eval.py

필요 패키지:
    pip install agent-evaluator          # 기본
    pip install "agent-evaluator[llm]"   # 실제 LLM 사용 시
"""

import asyncio
import os

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import agent_eval, agent_eval_async

# ---------------------------------------------------------------------------
# 모니터 설정
# ---------------------------------------------------------------------------
monitor = PerformanceMonitor(output_dir="results/")

# Phoenix OTEL 연결 (선택 — pip install "agent-evaluator[otel]" 필요)
try:
    from agent_evaluator import setup_otel
    setup_otel()
    print("[OTEL] Phoenix 연결됨 → http://localhost:6006")
except Exception:
    pass


# ---------------------------------------------------------------------------
# 예제 1: 기본 QA — 파라미터 이름 자동 탐지
# ---------------------------------------------------------------------------
@agent_eval(monitor, task_type="qa")
def qa_agent(question: str, ground_truth: str = "") -> str:
    """가장 단순한 형태 — question / ground_truth 이름 그대로 사용."""
    # 실제 프로젝트에서는 여기에 LLM 호출 코드가 들어갑니다
    MOCK_ANSWERS = {
        "한국의 수도는?": "서울입니다.",
        "Python 창시자는?": "귀도 반 로섬(Guido van Rossum)입니다.",
        "1 + 1 = ?": "2입니다.",
    }
    return MOCK_ANSWERS.get(question, "모르겠습니다.")


# ---------------------------------------------------------------------------
# 예제 2: 파라미터 이름이 다른 경우 — question_arg / ground_truth_arg 명시
# ---------------------------------------------------------------------------
@agent_eval(
    monitor,
    task_type="information_retrieval",
    question_arg="query",
    ground_truth_arg="expected",
    task_id_prefix="search",
)
def search_agent(query: str, expected: str = "") -> str:
    """검색 에이전트 — 파라미터 이름이 question 이 아닌 경우."""
    return f"'{query}'에 대한 검색 결과입니다."


# ---------------------------------------------------------------------------
# 예제 3: RAG 에이전트 — context_arg 로 할루시네이션 감지 활성화
# ---------------------------------------------------------------------------
@agent_eval(
    monitor,
    task_type="information_retrieval",
    question_arg="query",
    context_arg="context",
    task_id_prefix="rag",
    model_name="gpt-4o-mini",
)
def rag_agent(query: str, context: str = "", ground_truth: str = "") -> str:
    """RAG 에이전트 — context 제공 시 할루시네이션 감지 자동 적용."""
    return f"컨텍스트 기반 답변: {context[:50]}... → {query}에 대한 답변입니다."


# ---------------------------------------------------------------------------
# 예제 4: 에러 케이스 — 예외 발생 시에도 has_error=True 로 자동 기록
# ---------------------------------------------------------------------------
@agent_eval(monitor, task_type="qa", task_id_prefix="error_test")
def flaky_agent(question: str, ground_truth: str = "") -> str:
    """일부러 오류를 발생시키는 에이전트 — 실패 케이스도 기록됨."""
    if "오류" in question:
        raise ValueError("의도적 오류 발생!")
    return "정상 응답"


# ---------------------------------------------------------------------------
# 예제 5: 실제 OpenAI 사용 (API 키 있을 때만)
# ---------------------------------------------------------------------------
if os.getenv("OPENAI_API_KEY"):
    @agent_eval(
        monitor,
        task_type="qa",
        task_id_prefix="openai",
        model_name="gpt-4o-mini",
    )
    def openai_agent(question: str, ground_truth: str = "") -> str:
        import openai
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": question}],
        )
        # @agent_eval 이 OpenAI 응답 객체를 자동 인식 → 토큰 수 자동 추출
        # 여기서는 문자열로 반환하지만, 응답 객체 자체를 반환해도 동작함
        return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# 예제 6: 비동기 에이전트
# ---------------------------------------------------------------------------
@agent_eval_async(monitor, task_type="qa", task_id_prefix="async")
async def async_agent(question: str, ground_truth: str = "") -> str:
    """비동기 에이전트 예시."""
    await asyncio.sleep(0.05)  # 네트워크 지연 시뮬레이션
    return f"비동기 응답: {question}"


# ---------------------------------------------------------------------------
# 예제 7: enabled 플래그 — 환경변수로 평가 On/Off
# ---------------------------------------------------------------------------
EVAL_ENABLED = os.getenv("AGENT_EVAL_ENABLED", "true").lower() == "true"

@agent_eval(monitor, task_type="qa", enabled=EVAL_ENABLED)
def conditional_agent(question: str, ground_truth: str = "") -> str:
    """AGENT_EVAL_ENABLED=false 설정 시 데코레이터 무력화."""
    return "조건부 평가 응답"


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
async def main():
    print("\n=== @agent_eval 데코레이터 예제 ===\n")

    # 예제 1: 기본 QA
    print("--- 예제 1: 기본 QA ---")
    qa_dataset = [
        ("한국의 수도는?", "서울"),
        ("Python 창시자는?", "귀도 반 로섬"),
        ("1 + 1 = ?", "2"),
    ]
    for question, gt in qa_dataset:
        answer = qa_agent(question, ground_truth=gt)
        print(f"  Q: {question}")
        print(f"  A: {answer}\n")

    # 예제 2: 파라미터 이름 변경
    print("--- 예제 2: 파라미터 이름 변경 ---")
    result = search_agent(query="agent-evaluator 사용법", expected="데코레이터 방식으로 사용")
    print(f"  검색 결과: {result}\n")

    # 예제 3: RAG
    print("--- 예제 3: RAG (할루시네이션 감지) ---")
    rag_result = rag_agent(
        query="서울의 인구는?",
        context="서울특별시의 인구는 약 950만 명이다. 수도권 전체 인구는 약 2,500만 명이다.",
        ground_truth="약 950만 명",
    )
    print(f"  RAG 응답: {rag_result}\n")

    # 예제 4: 에러 케이스
    print("--- 예제 4: 에러 케이스 (실패도 자동 기록) ---")
    try:
        flaky_agent("오류를 일으켜줘", ground_truth="")
    except ValueError as e:
        print(f"  예상된 오류 발생 (기록됨): {e}\n")

    flaky_agent("정상 질문입니다", ground_truth="정상 응답")
    print("  정상 케이스 완료\n")

    # 예제 5: 실제 OpenAI
    if os.getenv("OPENAI_API_KEY"):
        print("--- 예제 5: 실제 OpenAI 호출 ---")
        try:
            answer = openai_agent("대한민국의 수도는?", ground_truth="서울")
            print(f"  OpenAI 응답: {answer}\n")
        except Exception as e:
            print(f"  OpenAI 호출 실패: {e}\n")
    else:
        print("--- 예제 5: OpenAI 건너뜀 (OPENAI_API_KEY 미설정) ---\n")

    # 예제 6: 비동기
    print("--- 예제 6: 비동기 에이전트 ---")
    async_result = await async_agent("비동기로 답해줘", ground_truth="비동기 응답")
    print(f"  비동기 응답: {async_result}\n")

    # 예제 7: 조건부
    print(f"--- 예제 7: 조건부 평가 (AGENT_EVAL_ENABLED={EVAL_ENABLED}) ---")
    conditional_agent("조건부 질문", ground_truth="조건부 응답")
    print("  조건부 에이전트 완료\n")

    # 결과 저장
    print("--- 결과 저장 ---")
    monitor.save_to_file("18_decorator_eval")
    print("  results/18_decorator_eval.json 저장 완료")
    print("\n=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
