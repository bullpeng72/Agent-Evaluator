# 데코레이터 가이드

에이전트 코드에 평가를 적용하는 실전 개발자 레퍼런스

**Version**: 0.7.4  
**최종 업데이트**: 2026-04-08

---

## 목차

1. [3가지 데코레이터 방식 한눈에 보기](#1-3가지-데코레이터-방식-한눈에-보기)
2. [데코레이터 내부 동작 원리](#2-데코레이터-내부-동작-원리)
3. [방식 1 — `agent_eval`](#3-방식-1--agent_eval)
4. [방식 2 — `QuickEval` / `EvalDecorator`](#4-방식-2--quickeval--evaldecorator)
5. [방식 3 — `conversation_eval`](#5-방식-3--conversation_eval)
6. [메타데이터 주입 — `EvalMetadata` & `get_eval_ctx()`](#6-메타데이터-주입--evalmetadata--get_eval_ctx)
7. [지표별 커버리지](#7-지표별-커버리지)
8. [프레임워크별 커버리지](#8-프레임워크별-커버리지)
9. [Dashboard / Phoenix UI 커버리지](#9-dashboard--phoenix-ui-커버리지)
10. [프로덕션 설정](#10-프로덕션-설정)
11. [전체 파라미터 레퍼런스](#11-전체-파라미터-레퍼런스)

---

## 1. 3가지 핵심 데코레이터 방식 한눈에 보기

SDK의 표준 인터페이스는 용도에 따라 통합된 3개의 데코레이터입니다.

```
┌──────────────────┬──────────────────────────────────┬─────────────────────────────┐
│ 데코레이터        │ 용도                              │ 코드 한 줄                   │
├──────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ @agent_eval      │ 단일 호출 (Single-turn)            │ @agent_eval(monitor)         │
│ @batch_eval      │ 리스트 기반 대량 처리 (Batch)       │ @batch_eval(monitor)         │
│ @conversation_eval│ 멀티턴 대화 세션 (Multi-turn)      │ @conversation_eval(monitor)  │
└──────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

> **Note**: `QuickEval`(`eval = QuickEval()`)은 위 데코레이터들을 더 짧게 설정하기 위한 **팩토리(Factory) 도구**입니다.

---

## 2. 방식 1 — `@agent_eval` (표준)

가장 범용적인 방식입니다. 동기(`def`) 및 비동기(`async def`) 함수를 모두 자동으로 감지하여 처리합니다.

### 기본 사용법

```python
from agent_evaluator import agent_eval, PerformanceMonitor

monitor = PerformanceMonitor(output_dir="results/")

@agent_eval(monitor, task_type="qa", framework="openai")
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)
```

### RAG + 할루시네이션 모드

```python
@agent_eval(monitor, task_type="information_retrieval", rag_mode=True)
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return rag_chain.invoke({"input": question, "context": context})
```

---

## 3. 방식 2 — `@batch_eval` (Batch 처리)

대량의 데이터를 한 번에 평가할 때 사용하며, 병렬 실행(`concurrent=True`)을 지원합니다.

```python
from agent_evaluator import batch_eval

@batch_eval(monitor, task_type="qa", concurrent=True, max_concurrent=5)
def batch_agent(questions: list, ground_truths: list = None) -> list:
    return [llm.invoke(q) for q in questions]
```

---

## 4. 방식 3 — `@conversation_eval` (멀티턴 대화)

v0.7.3부터 수동 세션 관리를 대체하는 표준 방식입니다. `session_id`를 기반으로 대화 맥락을 누적합니다.

```python
from agent_evaluator import conversation_eval, flush_conversation

@conversation_eval(monitor, session_id_arg="sid", max_turns=10)
def chat_agent(question: str, sid: str = "default") -> str:
    return chatbot.chat(question)

# 동일 sid 호출 시 턴 자동 누적
chat_agent("안녕하세요", sid="user_1")
chat_agent("날씨 알려줘", sid="user_1")

# 명시적 종료
flush_conversation("user_1")
```

---

## 5. QuickEval — 편의용 팩토리

데코레이터 설정을 더 간결하게 하고 싶을 때 사용합니다.

```python
from agent_evaluator import QuickEval
eval = QuickEval("results/")

@eval.qa  # 내부적으로 @agent_eval(monitor, task_type="qa") 호출
def my_agent(q): ...
```
