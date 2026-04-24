# Chapter 24. 첫 번째 이식: 30분 안에 첫 측정값 얻기

> **이 챕터에서 배우는 것**
> - 기존 코드를 최소한 수정하면서 평가를 이식하는 **침습도 최소화 원칙**
> - 기존 함수를 수정하지 않고 QuickEval 데코레이터로 감싸는 **레벨 0 이식 패턴**
> - "첫 측정점"을 고르는 세 가지 기준과 흔한 선택 실수
> - Lecture_forge QAAgent와 ContentWriter에 각각 측정점 삽입하기
> - 1단계 이식이 끝난 후 어떤 숫자가 보이는가

> **독자별 읽기 가이드**
> - **👨‍💻 개발자**: §24.2(침습도 레벨)와 §24.3(첫 측정점 기준)을 먼저 읽고, §24.4–24.5의 코드를 자신의 프로젝트에 맞게 변형하면 됩니다.
> - **📋 QA 관리자**: §24.6(1단계에서 얻는 것)를 먼저 읽으면 "30분 투자로 무엇을 얻는가"를 팀에 설득할 수 있습니다.
> - **이 챕터의 코드는 복사-붙여넣기로 바로 쓸 수 있게 설계됐습니다.** 자신의 프로젝트 함수명으로 치환하면 됩니다.

---

## 24.1 이식의 제1원칙: 아무것도 깨지 않는다

기존 프로젝트에 평가 코드를 붙일 때 가장 흔한 실수는 **내부 로직을 함께 수정하는 것**이다.

"평가하는 김에 이 부분도 리팩터링하면 어떨까?" 라는 생각이 든다. 측정 코드를 삽입하면서 함수 인터페이스를 바꾼다. 평가 결과를 로그로 남기기 위해 기존 흐름에 분기를 추가한다.

이것은 측정과 수정을 동시에 하는 것이다. 나중에 버그가 생겼을 때 "평가 코드 때문인가, 리팩터링 때문인가"를 구분할 수 없어진다. 측정이 오히려 시스템을 불안정하게 만든다.

1단계의 원칙은 명확하다.

> **기존 코드의 입력과 출력을 바꾸지 않는다. 반환값만 관찰한다.**

이것을 "레벨 0 침습"이라 부른다. 함수가 무엇을 반환하는지만 보고, 내부를 바꾸지 않는다.

---

## 24.1b 핵심 도구 안내 (처음 읽는 분을 위해)

이 챕터에서 처음 등장하는 agent-evaluator 도구들을 미리 정리한다.

| 도구 | 역할 | 기본 사용법 |
|------|------|------------|
| `QuickEval` | 평가 세션을 가장 간단하게 시작하는 Facade | `eval_session = QuickEval("results/")` 한 줄 |
| `@eval_session.qa` | 에이전트 함수에 붙이는 데코레이터. 호출할 때마다 자동으로 결과를 기록 | 함수가 `str`을 반환해야 함 |
| `PerformanceMonitor` | 더 세밀한 설정(보안 스캔, Harness Gate Config)이 필요할 때 직접 사용 | Ch25에서 본격 사용 |
| `create_taskresult()` | 데코레이터 적용이 불가능할 때 수동으로 결과 1건을 기록 | `monitor.record_task(create_taskresult(...))` |

### 데코레이터 적용 가능 vs 불가능

| 상황 | 권장 방법 | 이유 |
|------|-----------|------|
| 함수가 `str` 반환 | `@eval_session.qa` 직접 적용 (Level 0) | 데코레이터 요구 충족 |
| 함수가 `dict/객체` 반환 | `@eval_session.qa` + 래퍼 함수 작성 | `str` 변환이 필요 |
| 클래스 메서드, 복잡한 반환 | `create_taskresult()` 직접 사용 (Level 1) | 데코레이터 우회 |
| 기존 로직 내부에서 기록 | `monitor.record_task(create_taskresult(...))` | 호출 흐름 유지 |

이 표를 기준으로 자신의 프로젝트 함수 유형을 확인하고 §24.4 이후의 패턴을 선택하면 된다.

---

## 24.2 침습도 레벨

기존 프로젝트에 평가를 이식하는 방법은 침습도에 따라 4단계로 나뉜다.

@@HTML_START@@
<style>
.invasion-table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;}
.invasion-table th{background:#37474f;color:#fff;padding:10px 14px;}
.invasion-table td{padding:9px 14px;border-bottom:1px solid #eceff1;vertical-align:top;}
.level-badge{display:inline-block;padding:4px 12px;border-radius:12px;font-weight:700;font-size:12px;color:#fff;}
.recommend-tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:600;background:#c8e6c9;color:#1b5e20;}
.caution-tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:600;background:#fff3e0;color:#e65100;}
.danger-tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:600;background:#ffebee;color:#c62828;}
</style>

<table class="invasion-table">
<thead>
<tr>
  <th>레벨</th>
  <th>설명</th>
  <th>기존 코드 수정</th>
  <th>사용 단계</th>
</tr>
</thead>
<tbody>
<tr>
  <td><span class="level-badge" style="background:#2e7d32;">레벨 0</span></td>
  <td><strong>반환값 래핑만</strong><br>기존 함수를 호출하는 얇은 래퍼를 새로 작성한다. 기존 코드 파일을 열지 않는다.</td>
  <td><span class="recommend-tag">수정 없음</span></td>
  <td>1단계 (권장)</td>
</tr>
<tr>
  <td><span class="level-badge" style="background:#1565c0;">레벨 1</span></td>
  <td><strong>반환 직후 기록 추가</strong><br>기존 함수의 마지막 return 직전에 <code>monitor.record_task()</code>를 추가한다.</td>
  <td><span class="recommend-tag">최소 수정</span><br>(1–3줄 추가)</td>
  <td>1단계 허용</td>
</tr>
<tr>
  <td><span class="level-badge" style="background:#e65100;">레벨 2</span></td>
  <td><strong>내부 흐름에 훅 추가</strong><br>기존 함수의 중간 단계에 측정 코드를 삽입한다. 로직 변경 없이 추적만.</td>
  <td><span class="caution-tag">구조적 수정</span></td>
  <td>2단계 (Ch25)</td>
</tr>
<tr>
  <td><span class="level-badge" style="background:#c62828;">레벨 3</span></td>
  <td><strong>아키텍처 변경</strong><br>에이전트 클래스를 상속하거나, 함수 인터페이스를 바꾸거나, 미들웨어를 삽입한다.</td>
  <td><span class="danger-tag">대규모 수정</span></td>
  <td>1단계 금지</td>
</tr>
</tbody>
</table>
@@HTML_END@@

1단계에서는 레벨 0과 레벨 1만 사용한다. 레벨 2 이상은 2단계(Ch25)에서 시스템 전체를 이해한 후에 적용한다.

---

## 24.3 첫 측정점을 고르는 세 가지 기준

프로젝트에 측정점이 될 수 있는 함수가 수십 개 있다. 그중에서 **첫 번째** 측정점을 어떻게 고르는가가 1단계의 성공을 좌우한다.

세 가지 기준을 모두 만족하는 함수를 찾는다.

**기준 1: 입출력이 명확하다**

함수가 무엇을 받고 무엇을 반환하는지 한눈에 보인다. 파라미터가 3개 이하고, 반환값이 단일 타입이면 이상적이다.

```python
# 좋은 예: 명확한 입출력
def answer(question: str) -> dict:
    return {"answer": str, "confidence": float, "sources": list}

# 나쁜 예: 복잡한 상태 의존
def process(self, context, state, config, **kwargs) -> Optional[Response]:
    ...  # 내부 상태를 여러 곳에서 읽고 씀
```

**기준 2: 이미 성공 기준이 있다**

기존 코드에 검증 로직이 있거나, "이 함수가 이것을 반환하면 성공"이라는 기준이 암묵적으로라도 존재한다. 이 기준이 `ground_truth`와 `accuracy` 측정의 출발점이 된다.

```python
# 성공 기준이 코드에 있는 경우
if len(answer["answer"].split()) < MIN_ANSWER_WORDS:
    raise InsufficientAnswerError(...)

# → ground_truth를 비워도 단어 수 기반 TCR 측정 가능
```

**기준 3: 독립적으로 호출 가능하다**

다른 에이전트의 상태나 전역 변수에 의존하지 않고, 입력만 주면 단독으로 실행할 수 있다. 이것이 재현 가능한 평가의 기초다.

---

## 24.4 범용 패턴: 레벨 0 래핑

어떤 프로젝트든 기존 LLM 호출 함수를 감싸는 패턴은 동일하다.

```python
# ── 범용 레벨 0 래핑 패턴 ────────────────────────────────────────────

from agent_evaluator import QuickEval

eval_session = QuickEval("eval_results/")   # ← 평가 결과 저장 경로

# 기존 함수 (수정하지 않음)
# def existing_function(input_data): ...

# 평가 래퍼 (새로 작성 — 기존 파일 수정 없음)
@eval_session.qa
def measured_function(question: str, ground_truth: str = "") -> str:
    result = existing_function(question)
    # 반환값이 객체라면 텍스트만 추출
    return result.text if hasattr(result, "text") else str(result)

# 기존 호출 코드에서 함수명만 변경
# before: response = existing_function(user_input)
# after:  response = measured_function(user_input)
```

핵심은 두 가지다. `existing_function`을 전혀 건드리지 않는다. `measured_function`은 기존 함수와 동일한 결과를 반환한다. 기존 코드를 쓰는 모든 곳에서 함수명만 바꾸면 된다.

---

## 24.5 Lecture_forge 1단계 이식: QAAgent

세 가지 기준을 Lecture_forge에 적용하면 첫 번째 측정점으로 `QAAgent.answer()`가 선택된다.

- **입출력 명확**: `question: str` → `{"answer": str, "sources": list, "confidence": float}`
- **성공 기준 존재**: `≥ 300단어`, `≥ 2개 출처`, `신뢰도 0–1` 이 코드에 명시됨
- **독립 호출 가능**: 특정 `lecture_dir`만 있으면 단독으로 실행됨

```python
# cli/chat.py — 수정 전 (기존 코드)
def chat_command(lecture_dir: str):
    qa_agent = QAAgent(lecture_dir)
    while True:
        question = input("질문: ")
        result = qa_agent.answer(question)
        print(result["answer"])
        print(f"\n출처: {', '.join(result['sources'])}")
```

```python
# cli/chat.py — 수정 후 (레벨 0 이식, 추가된 코드: 6줄)
from agent_evaluator import QuickEval           # 추가 1

eval_session = QuickEval("lecture_eval_results/", auto_save=True)  # 추가 2 — auto_save=True 필수

def chat_command(lecture_dir: str):
    qa_agent = QAAgent(lecture_dir)
    _ctx = {}                                   # 추가 3 — sources 노출용 클로저 변수

    @eval_session.qa                            # 추가 4
    def measured_answer(question: str, ground_truth: str = "") -> str:  # 추가 5
        result = qa_agent.answer(question)
        _ctx["sources"] = result["sources"]     # 추가 6 — while 루프에서 접근 가능하게
        return result["answer"]                 # 데코레이터가 str 반환값을 response로 캡처

    while True:
        question = input("질문: ")
        answer = measured_answer(question)      # ← 평가 기록 + _ctx 갱신, str 반환
        print(answer)                           # ← 기존 print(result["answer"])와 동일
        print(f"\n출처: {', '.join(_ctx['sources'])}")  # ← 기존 코드와 동일
    # auto_save=True 덕분에 10건마다 자동 저장된다.
    # save()를 명시 호출하지 않아도 된다 (while True 이후는 도달 불가).
```

> **왜 `return result`가 아니라 `return result["answer"]`인가?**
>
> `@eval_session.qa`는 내부적으로 `@agent_eval(monitor, task_type="qa")`와 동일하게 동작한다. 이 데코레이터는 함수의 반환값을 **`TaskResult.response` (str)** 로 캡처해서 정확도 점수(Token F1·Jaccard·LCS)를 계산한다.
>
> `result`(dict)를 반환하면 `str({"answer": ..., "sources": [...], "confidence": 0.9})`가 response에 저장된다. accuracy scoring이 이 문자열과 ground_truth를 비교하게 되어 **모든 점수가 무의미**해진다.
>
> 따라서 평가에 쓸 텍스트인 `result["answer"]`만 반환하고, 나머지 데이터(`sources`, `confidence`)는 클로저 변수(`_ctx`)를 통해 while 루프에 노출시킨다.

> **왜 `auto_save=True`가 필요한가?**
>
> `while True` 루프는 종료되지 않으므로 루프 뒤의 `save()`는 절대 실행되지 않는다. `QuickEval("경로/", auto_save=True)`로 생성하면 10건마다 자동으로 `save_to_file()`이 호출된다. 채팅 세션 중간에 프로세스가 종료되더라도 결과가 보존된다. 서버 재시작·강제 종료 등을 고려하는 모든 long-running 세션에 `auto_save=True`를 사용할 것을 권장한다.

**수정한 것**: 함수 임포트 1줄 + `eval_session` 생성 1줄 + `_ctx` 1줄 + 래퍼 함수 3줄 = **총 6줄 추가**  
**기존 로직 수정**: 0줄

---

## 24.6 Lecture_forge 1단계 이식: ContentWriter — 위임 어댑터 패턴

ContentWriter는 `SectionContent`라는 Pydantic 모델을 반환한다. `@eval_session.qa` 데코레이터는 `str` 반환을 요구하므로 직접 적용할 수 없다.

레벨 1 방식으로 `agent.py`를 직접 수정하는 방법도 있지만, **기존 파일을 전혀 건드리지 않으면서도** 모든 측정이 가능한 패턴이 있다. **위임 어댑터(Delegation Adapter) 패턴**이다.

### 위임 어댑터 패턴의 구조

핵심 아이디어는 간단하다. 기존 에이전트 인스턴스를 감싸는 **어댑터 클래스**를 별도 파일에 작성한다. 어댑터가 원본 메서드를 호출하고, 결과를 `monitor`에 기록한 뒤, 원래 반환값을 그대로 돌려준다. `__getattr__`로 계측하지 않는 나머지 메서드와 속성은 원본으로 **투명하게 위임**된다.

```python
# src/lecture_forge/eval/adapters.py  (새 파일 — 기존 파일 수정 없음)

import time
from typing import List, Optional
from agent_evaluator import PerformanceMonitor, create_taskresult


class ContentWriterAdapter:
    """ContentWriterAgent를 감싸 각 섹션 생성을 계측한다."""

    def __init__(
        self,
        agent,                              # 기존 ContentWriterAgent 인스턴스
        monitor: PerformanceMonitor,
        learning_objectives: List[str],
    ) -> None:
        self._agent = agent
        self._monitor = monitor
        self._learning_objectives = learning_objectives

    def write_section(self, section, curriculum, available_images=None):
        """원본 write_section()을 호출하고 결과를 monitor에 기록한다."""
        task_id = f"section_{getattr(section, 'id', 'unknown')}"
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

            # Gate A: 학습목표 키워드 → 본문 오버랩 측정
            content_text = getattr(result, "markdown_content", "") if result else ""
            section_objectives = getattr(section, "learning_outcomes", []) or []
            ground_truth = " ".join(section_objectives)

            extra = {
                "phase": "content_writing",      # Gate G 단계별 지연 분석
                "section_id": getattr(section, "id", ""),
                "word_count": getattr(result, "word_count", 0) if result else 0,
            }

            task = create_taskresult(
                task_id=task_id,
                question=f"섹션 '{getattr(section, 'title', '')}' 콘텐츠 작성",
                response=content_text,
                ground_truth=ground_truth,
                execution_time=elapsed,
                task_type="document_creation",
                has_error=has_error,
                error_message=error_msg,
                extra=extra,
            )
            self._monitor.record_task(task)

        return result    # 기존과 완전히 동일한 반환값

    def __getattr__(self, name: str):
        """계측하지 않는 메서드/속성은 원본으로 투명하게 위임."""
        return getattr(self._agent, name)
```

### 진입점에서 어댑터 적용

```python
# cli/commands/create.py — generate_lecture() 안에서 에이전트 생성 직후 적용

# 기존 코드 (수정 없음):
writer = ContentWriterAgent(vector_store=vs)

# 어댑터로 교체 (이 한 줄 추가):
if _eval_monitor:
    writer = ContentWriterAdapter(writer, _eval_monitor, curriculum.learning_objectives)

# 이후 writer.write_section() 호출은 기존과 완전히 동일
# — 어댑터가 투명하게 중간에서 계측만 한다
```

이 방식의 장점은 명확하다. `ContentWriterAgent`의 소스 파일을 열지 않는다. 어댑터를 씌운 후에도 `writer.write_section()`의 인터페이스와 반환값은 완전히 동일하다. 모니터가 없는 경우(`_eval_monitor is None`) 한 줄로 우회할 수 있어 **opt-in** 설계가 자연스럽게 된다.

### try/finally로 오류 케이스도 기록

`try/except/finally` 구조 덕분에 `write_section()`이 예외를 던져도 `finally` 블록이 실행된다. `has_error=True`인 TaskResult가 monitor에 기록되고, Gate C(FaultTolerance)의 복구율 측정에 포함된다.

**수정한 것**: `eval/adapters.py` 새 파일 작성 + `create.py`에 어댑터 적용 2줄  
**기존 파일 수정**: 0줄 (`content_writer/agent.py`는 열지도 않는다)  
**`write_section()` 반환값**: 기존과 완전히 동일

---

## 24.7 첫 실행: 무엇이 보이는가

두 개의 측정점을 삽입한 후 Lecture_forge를 실행하면 다음 숫자들이 생긴다.

```bash
python -m lecture_forge.cli create \
    --topic "FastAPI 기초" \
    --duration 60 \
    --audience-level intermediate
```

실행 후 생성된 `lecture_eval_results/` 디렉토리를 대시보드로 확인한다.

```bash
agent-eval dashboard --results lecture_eval_results/
```

@@HTML_START@@
<style>
.metrics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0;}
.metric-card{padding:16px;border-radius:10px;text-align:center;}
.metric-value{font-size:28px;font-weight:900;margin:6px 0;}
.metric-label{font-size:12px;opacity:.8;}
.metric-note{font-size:11px;margin-top:6px;padding:4px 8px;border-radius:6px;}
</style>

<div class="metrics-grid">
  <div class="metric-card" style="background:#e8f5e9;border:2px solid #66bb6a;">
    <div class="metric-label" style="color:#1b5e20;">TCR (섹션 완성률)</div>
    <div class="metric-value" style="color:#2e7d32;">100%</div>
    <div class="metric-note" style="background:#c8e6c9;color:#1b5e20;">5/5 섹션 완성</div>
  </div>
  <div class="metric-card" style="background:#e3f2fd;border:2px solid #42a5f5;">
    <div class="metric-label" style="color:#0d47a1;">Accuracy (키워드 오버랩)</div>
    <div class="metric-value" style="color:#1565c0;">62%</div>
    <div class="metric-note" style="background:#bbdefb;color:#0d47a1;">학습목표 ↔ 본문 오버랩</div>
  </div>
  <div class="metric-card" style="background:#fff3e0;border:2px solid #ffa726;">
    <div class="metric-label" style="color:#e65100;">P95 레이턴시</div>
    <div class="metric-value" style="color:#ef6c00;">94초</div>
    <div class="metric-note" style="background:#ffe0b2;color:#e65100;">섹션당 최대 응답시간</div>
  </div>
  <div class="metric-card" style="background:#f3e5f5;border:2px solid #ab47bc;">
    <div class="metric-label" style="color:#4a148c;">평균 섹션 품질</div>
    <div class="metric-value" style="color:#6a1b9a;">81.4</div>
    <div class="metric-note" style="background:#e1bee7;color:#4a148c;">기존 QualityEvaluator 점수</div>
  </div>
</div>
@@HTML_END@@

이 숫자들을 어떻게 읽는가.

**TCR 100%**: 5개 섹션이 모두 완성됐다. 오류 없이 파이프라인이 종료됐다는 의미다.

**Accuracy 62%**: 학습 목표 키워드와 생성된 본문 사이의 토큰 오버랩이 62%다. "FastAPI의 의존성 주입"을 학습 목표로 지정했는데, 본문에 관련 내용이 얼마나 포함됐는지를 나타낸다. 62%가 낮은 건지 높은 건지는 다음 실행과 비교해서 판단한다.

**P95 94초**: 섹션 생성의 95퍼센타일 레이턴시다. 한 섹션이 최대 94초 걸렸다. SLA 120초에는 여유가 있다.

**평균 품질 81.4**: 기존 `QualityEvaluator`가 계산한 점수를 `metadata`에 담았으므로, 이제 이 점수도 agent-evaluator 대시보드에서 추적된다.

---

## 24.8 1단계 이식의 진짜 목적

30분의 작업으로 얻은 숫자들이 완전하지 않다는 것은 알고 있다. Gate A–G 전체를 측정하지도 않았고, 보안 스캔도 없고, 에이전트 간 정보 전파도 추적하지 않는다.

그래도 된다.

1단계의 목적은 완전한 측정이 아니다. **측정이 가능하다는 것을 확인하는 것**이다.

기존 코드를 18줄 추가해서 TCR, Accuracy, P95, 품질 점수가 숫자로 나왔다. 이것은 "이 프로젝트는 평가할 수 있다"는 증명이다. 처음으로 시스템의 건강 상태가 숫자로 표현됐다.

이 첫 숫자가 나오는 순간, 팀에서 두 가지 반응이 생긴다. "Accuracy 62%가 충분한가?"라는 질문과 "지난 주엔 몇이었지?"라는 질문이다. 이 두 질문이 2단계(전체 통합)로 자연스럽게 이어진다.

---

## 24.8b 이식 비용의 본질: 처음부터 설계한 프로젝트와의 차이

1단계 이식을 마친 지금, 한 가지 사실을 직시해야 한다. "기존 로직 수정: 0줄"이라고 표시했지만, QAAgent 이식에는 클로저 변수(`_ctx`)와 래퍼 함수가 필요했다. ContentWriter 이식에는 반환값 재구성이 필요했다. 이것은 "0줄 수정"이 아니다. **추가 비용이 있다.**

이 비용의 근본 원인은 하나다. `@agent_eval` 데코레이터는 에이전트 함수가 **`str`을 반환한다**고 가정한다. Lecture_forge의 함수들은 `dict`를 반환한다. 이 불일치가 모든 이식 마찰의 원천이다.

### 처음부터 설계한 경우 vs 이식하는 경우

처음부터 agent-evaluator와 함께 개발했다면, 에이전트 함수는 자연스럽게 `str`을 반환하는 형태로 설계된다.

```python
# 처음부터 agent-evaluator를 염두에 두고 설계한 경우
# → @eval_session.qa를 씌우면 그대로 동작, 추가 비용 없음

@eval_session.qa
def qa_agent(question: str, ground_truth: str = "") -> str:
    result = _internal_rag(question)            # 내부에서 dict를 만들어도
    return result["answer"]                     # 밖으로는 str만 노출

# 출처·신뢰도는 외부에서 직접 필요하지 않음 — 평가에는 answer만 쓰임
```

Lecture_forge처럼 `dict` 반환 함수를 이식하면, 데코레이터가 요구하는 `str`과 기존 코드가 기대하는 `dict` 사이의 간극을 코드로 메워야 한다.

```python
# 이식 경우 — 불가피한 비용 3가지

# 비용 1: 래퍼 함수 작성 (기존 함수를 직접 데코레이팅할 수 없음)
#   이유: qa_agent.answer()는 dict 반환 → 데코레이터가 str 요구
@eval_session.qa
def measured_answer(question: str, ground_truth: str = "") -> str:
    result = qa_agent.answer(question)          # 기존 함수 호출
    _ctx["sources"] = result["sources"]         # 비용 2: 클로저 변수로 데이터 노출
    return result["answer"]                     # str만 반환

# 비용 3: 호출부 변경
# 기존: result = qa_agent.answer(question)
# 이식: answer = measured_answer(question)  ← 함수명 교체 + result 접근 방식 변경
```

### 이식 비용 비교표

| 상황 | 추가 코드 | 호출부 변경 | 비용 |
|------|-----------|------------|------|
| 처음부터 `-> str` 반환으로 설계 | 데코레이터 1줄 | 없음 | 최소 |
| `dict` 반환 함수 이식 (Level 0) | 래퍼 3줄 + 클로저 1줄 | 함수명 교체 | 중간 |
| 복잡한 객체 반환 함수 이식 (Level 1) | `create_taskresult` 직접 작성 | 로직 추가 | 높음 |

### "Level 0 이식"이 진짜로 0비용인 경우

기존 함수가 이미 `str`을 반환한다면, 데코레이터 한 줄만 추가하면 끝난다. 비용이 정말 0이다.

```python
# ── 이식 전 (기존 코드) ──────────────────────────────────
def summarize_document(text: str) -> str:
    return llm.invoke(f"Summarize: {text}")
    # 이미 str 반환 → 데코레이터 요구 조건 충족

# ── 이식 후 (변경 1줄: 데코레이터 추가) ─────────────────
@eval_session.qa                                 # ← 이 줄만 추가
def summarize_document(text: str, ground_truth: str = "") -> str:
    return llm.invoke(f"Summarize: {text}")
    # 함수 본문은 한 글자도 바뀌지 않았다
```

`ground_truth=""` 파라미터만 추가하고 데코레이터 한 줄을 붙이는 것이 전부다. 기존 로직은 그대로다.

Lecture_forge의 QAAgent는 `str`을 반환하지 않기 때문에 이 케이스에 해당하지 않았다.

### 이것이 의미하는 것

"레벨 0 이식 = 기존 코드 0줄 수정"은 **최선의 경우**다. `str` 반환 함수가 이미 설계되어 있는 프로젝트에서만 완전히 성립한다. 대부분의 기존 프로젝트는 에이전트 함수가 `dict`, 객체, 또는 복잡한 타입을 반환하기 때문에, 이식 비용이 어느 수준으로든 발생한다.

이 비용은 나쁜 것이 아니다. 처음으로 측정이 가능해지는 데 지불하는 최소한의 비용이다. 그리고 새 프로젝트를 시작할 때 이 비용을 설계 단계에서 없앨 수 있다. **그 방법은 Chapter 12.12에서 다룬다.**

---

## 24.9 일반화: 어떤 프로젝트에도 이 방법을 쓸 수 있다

### 입출력이 복잡한 함수를 만났을 때

반환값이 중첩된 객체이거나 여러 타입이 섞여 있을 때, 무리하게 파싱하려 하지 말고 핵심 텍스트만 추출한다.

```python
# 반환값이 복잡한 경우
@eval_session.qa
def measured_complex_function(question: str, ground_truth: str = "") -> str:
    result = existing_complex_agent(question)
    # 핵심 텍스트만 추출 — 나머지는 metadata로
    return (
        result.output.text              # 텍스트 출력이 있는 경우
        or result.content               # 또는 다른 필드
        or str(result)                  # 최후 수단: 전체를 문자열로
    )
```

### ground_truth가 없는 경우

ground_truth 없이 시작해도 된다. `ground_truth=""`로 두면 TCR(완료 여부)만 측정되고 Accuracy는 측정되지 않는다. TCR만으로도 처음 몇 주간 충분한 인사이트를 얻을 수 있다.

```python
# ground_truth 없이 TCR만 측정하는 경우
@eval_session.qa
def measured_function(question: str, ground_truth: str = "") -> str:
    return existing_function(question)
    # ground_truth=""이면 TCR만 측정됨 — 완전히 유효한 시작점
```

### 실패 케이스도 기록하라

기존 코드에 오류 처리가 있다면, 성공 경로와 실패 경로 모두에서 `record_task()`를 호출한다.

```python
def write_section(self, section, curriculum, available_images):
    try:
        content = self._generate_content(section, curriculum, contexts)
        _eval_monitor.record_task(create_taskresult(
            task_id=f"section_{section.id}",
            response=content.markdown_content,
            ...
        ))
        return content
    except Exception as e:
        _eval_monitor.record_task(create_taskresult(
            task_id=f"section_{section.id}_error",
            response="",
            has_error=True,
            error_message=str(e),
            execution_time=time.time() - _start,
            ...
        ))
        raise   # 기존 예외 처리 유지
```

실패 케이스를 기록하면 Gate C(FaultTolerance)의 복구율 측정이 자동으로 된다.

---

## 24.10 1단계 완료 체크리스트

```
1단계 이식 완료 체크리스트

□ 첫 측정점을 선택했다 (입출력 명확 + 성공 기준 존재 + 독립 호출 가능)
□ 레벨 0 또는 레벨 1 방식으로 이식했다 (기존 반환값 변경 없음)
□ eval_results/ 디렉토리에 JSON 파일이 생성됐다
□ agent-eval dashboard에서 TCR, Accuracy, P95가 보인다
□ 기존 테스트가 모두 통과한다 (이식이 기존 동작을 깨지 않았음을 확인)
```

마지막 항목이 중요하다. 1단계 이식 후 반드시 기존 테스트를 실행해서 아무것도 깨지지 않았음을 확인한다. 테스트가 모두 통과하면, 1단계는 완성이다.

---

> **이 챕터에서 배운 것**
>
> 첫 번째 이식의 핵심은 아무것도 깨지 않는 것이다. 레벨 0 래핑 패턴은 기존 코드를 전혀 수정하지 않고 평가 데코레이터를 씌운다. 클래스 기반 에이전트가 Pydantic 모델을 반환하는 경우에는 **위임 어댑터 패턴**이 더 깔끔하다 — 기존 에이전트 파일을 전혀 건드리지 않고, 진입점에서 어댑터 인스턴스로 교체하는 것만으로 계측이 완성된다.
>
> Lecture_forge에서 QAAgent는 QuickEval 래퍼로, ContentWriter는 `ContentWriterAdapter`로 계측했다. 두 경우 모두 기존 파일 수정: 0줄. 결과: TCR, Accuracy, P95가 처음으로 숫자로 나왔다.
>
> 이 숫자들이 완전하지 않아도 된다. 처음으로 "측정 가능하다"는 것을 확인한 것 자체가 1단계의 성과다.
>
> **다음 챕터**에서는 이 기반 위에 Gate A–G 전체를 연결한다. 중앙 모니터를 설계하고, 4개 에이전트를 각각 위임 어댑터로 감싸고, 보안 스캔을 `enable_security_metrics=True` 한 줄로 활성화한다.

```
# 출처: Evaluator_Examples/ch24_quickeval_entry.py
```
