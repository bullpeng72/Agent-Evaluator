#LangChain프로젝트평가 #AI평가이식 #30분가이드

# 기존 LangChain 프로젝트에 평가 붙이기 — 30분 실전 가이드

> **TL;DR**
> - 기존 코드를 한 줄도 수정하지 않고 `@eval_session.qa` 데코레이터 하나로 LangChain 에이전트 측정을 시작할 수 있다.
> - 반환값이 `dict` 또는 Pydantic 모델인 함수는 **위임 어댑터 패턴**으로 감싸면 원본 파일을 열지 않아도 된다.
> - 30분 안에 TCR·정확도·레이턴시 첫 측정값을 얻고, Harness Gate A–G 전체 분석의 기초를 세울 수 있다.

---

## 왜 "나중에 붙이자"가 계속 미뤄지는가

LangChain으로 에이전트를 만들다 보면 평가는 항상 뒷전이 된다. 일단 돌아가게 만들고, 다음에 붙이려는데 막상 보면 코드가 이미 얽혀 있다. 함수가 `dict`를 반환하고, 클래스 메서드는 내부 상태에 의존하고, 어디서부터 손대야 할지 모르겠다.

그래서 "측정하는 김에 리팩터링도 같이"라는 생각이 든다. 그리고 그 순간부터 30분 작업이 3일 작업이 된다.

이 글에서는 다른 접근을 택한다. **기존 코드의 입출력을 바꾸지 않고, 반환값만 관찰한다.** 이 원칙만 지키면 30분 안에 첫 측정값을 얻을 수 있다.

---

## 침습도 레벨 — 지금 당장은 레벨 0만 쓴다

기존 프로젝트에 평가를 이식하는 방법은 **침습도(invasion level)** 에 따라 4단계로 나뉜다.

| 레벨 | 방법 | 기존 코드 수정 | 사용 시점 |
|------|------|----------------|-----------|
| **0** | 반환값 래핑만 (새 래퍼 함수 작성) | **0줄** | **지금 (권장)** |
| **1** | 기존 함수 마지막 줄에 `record_task()` 추가 | 1–3줄 | 지금 허용 |
| **2** | 내부 흐름에 훅 삽입 | 구조적 수정 | 다음 단계 |
| **3** | 클래스 상속·인터페이스 변경 | 대규모 수정 | 전면 이식 시 |

첫 번째 이식에서는 **레벨 0과 1만** 쓴다. 레벨 2 이상은 시스템 전체를 파악한 이후에 적용한다.

**첫 번째 이식에서는 레벨 0만으로도 TCR·정확도·레이턴시를 전부 측정할 수 있다.**

---

## 첫 측정점 고르는 세 가지 기준

프로젝트 안에 측정 가능한 함수가 수십 개라도, **첫 번째** 측정점은 아래 기준으로 고른다.

1. **입출력이 명확하다** — 파라미터 3개 이하, 반환값 단일 타입이면 이상적이다.
2. **성공 기준이 이미 있다** — 코드에 검증 로직이 있거나, "이걸 반환하면 성공"이 암묵적으로라도 정의된 함수.
3. **독립적으로 호출 가능하다** — 다른 에이전트 상태나 전역 변수 없이, 입력만 주면 단독 실행된다.

세 가지를 모두 만족하는 함수부터 시작한다. 셋 중 하나라도 빠지면 첫 측정이 어렵다.

---

## LangChain 프로젝트 평가 시작: 레벨 0 래핑 패턴

```bash
pip install agent-evaluator
```

설치 후 어떤 LLM 에이전트 함수든 다음 패턴으로 감쌀 수 있다.

```python
# evaluation/wrappers.py  ← 새 파일 (기존 파일 수정 없음)

from agent_evaluator import QuickEval

# 평가 세션 생성 — 결과는 eval_results/ 디렉토리에 저장
eval_session = QuickEval("eval_results/", auto_save=True)

# 기존 함수는 건드리지 않는다
# from my_agent import existing_qa_agent

@eval_session.qa
def measured_qa(question: str, ground_truth: str = "") -> str:
    result = existing_qa_agent.invoke({"input": question})
    # dict·객체라면 텍스트 부분만 추출
    return result["output"] if isinstance(result, dict) else str(result)
```

```python
# 기존 호출 코드에서 함수명만 교체
# before: response = existing_qa_agent.invoke({"input": question})
# after:  response = measured_qa(question)
```

**왜 `return result` 전체가 아니라 `result["output"]`인가?** `@eval_session.qa`는 반환된 `str`을 `TaskResult.response`로 캡처해 Token F1·Jaccard·LCS 정확도를 계산한다. `dict`를 통째로 반환하면 `str({"output": ..., "metadata": ...})`가 response에 저장되어 모든 점수가 무의미해진다. **평가에 쓸 텍스트만 반환**하는 게 핵심이다.

**왜 `auto_save=True`인가?** CLI 서비스나 `while True` 루프처럼 종료 시점이 불명확한 경우, 루프 뒤의 `save()`는 실행되지 않는다. `auto_save=True`로 생성하면 10건마다 자동 저장된다.

*핵심: 기존 함수를 전혀 수정하지 않고 6줄 추가만으로 QA 측정이 시작된다.*

---

## 반환값이 객체일 때 — 위임 어댑터 패턴

LangChain 에이전트가 Pydantic 모델(`SectionContent`, `AgentOutput` 등)을 반환한다면 `@eval_session.qa`를 직접 달 수 없다. 이때는 **위임 어댑터** 패턴을 쓴다.

기존 에이전트 인스턴스를 감싸는 어댑터 클래스를 **별도 파일에** 작성한다. `__getattr__`로 계측하지 않는 모든 메서드와 속성은 원본으로 투명하게 위임한다.

```python
# evaluation/adapters.py  ← 새 파일 (agent.py 수정 없음)

import time
from typing import Optional
from agent_evaluator import PerformanceMonitor, create_taskresult


class ContentWriterAdapter:
    """ContentWriterAgent를 감싸 섹션 생성을 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor) -> None:
        self._agent = agent
        self._monitor = monitor

    def write_section(self, section, curriculum, available_images=None):
        """원본 write_section()을 호출하고 결과를 monitor에 기록."""
        task_id = f"section_{getattr(section, 'id', 'unknown')}"
        start = time.perf_counter()
        result = None
        has_error = False
        error_msg: Optional[str] = None

        try:
            result = self._agent.write_section(section, curriculum, available_images)
        except Exception as exc:
            has_error = True
            error_msg = str(exc)
            raise                          # 예외는 그대로 전파 — 기존 동작 유지
        finally:
            elapsed = time.perf_counter() - start

            content_text = getattr(result, "markdown_content", "") if result else ""
            section_objectives = getattr(section, "learning_outcomes", []) or []

            task = create_taskresult(
                task_id=task_id,
                question=f"섹션 '{getattr(section, 'title', '')}' 콘텐츠 작성",
                response=content_text,
                ground_truth=" ".join(section_objectives),  # 학습목표 키워드 오버랩 측정
                execution_time=elapsed,
                task_type="document_creation",
                has_error=has_error,
                error_message=error_msg,
            )
            self._monitor.record_task(task)

        return result    # 기존과 완전히 동일한 반환값

    def __getattr__(self, name: str):
        """계측하지 않는 메서드·속성은 원본으로 투명하게 위임."""
        return getattr(self._agent, name)
```

```python
# cli/commands/create.py — generate() 함수 안, 에이전트 생성 직후에만 추가

from agent_evaluator import PerformanceMonitor

_monitor = PerformanceMonitor("eval_results/")

# 기존 코드 (수정 없음)
writer = ContentWriterAgent(vector_store=vs)

# 어댑터 교체 — 이 한 줄만 추가
writer = ContentWriterAdapter(writer, _monitor)

# 이후 writer.write_section() 호출은 기존과 완전히 동일
```

`try/finally` 구조 덕분에 `write_section()`이 예외를 던져도 `finally` 블록은 반드시 실행된다. `has_error=True`인 TaskResult가 기록되어 **Gate C(FaultTolerance)** 복구율 측정에 자동으로 포함된다.

*핵심: 원본 `agent.py`를 열지 않고도 Pydantic 모델 반환 함수의 모든 지표를 측정할 수 있다.*

---

## 첫 실행 후 대시보드 확인

이식이 끝났으면 평소처럼 에이전트를 실행한다. 별도 테스트 스크립트가 필요 없다.

```bash
# 평소대로 실행 — 평가가 자동으로 기록된다
python -m my_project.cli run --topic "FastAPI 기초"

# 결과 확인
agent-eval dashboard --results eval_results/
```

처음 측정에서 보게 될 숫자들:

| 지표 | 예시 | 읽는 방법 |
|------|------|-----------|
| **TCR** | 100% | 전체 태스크가 오류 없이 완료됐는지 |
| **Accuracy** | 62% | 학습목표 키워드가 본문에 얼마나 반영됐는지 |
| **P95 레이턴시** | 94초 | 상위 5% 최악 응답시간 — SLA 설계의 기준점 |
| **평균 품질** | 81.4 | 5차원 응답 품질 종합 점수 |

**Accuracy 62%** 숫자를 보고 "낮다"고 느낄 수 있다. 하지만 **이것이 바로 첫 측정의 가치**다. 기존에는 이 숫자가 존재하지 않았다. 지금부터 이 숫자를 개선의 기준선으로 쓸 수 있다. 다음 배포에서 62%가 71%가 됐는지, 반대로 55%로 떨어졌는지 알 수 있다.

---

## 마무리 — 30분 체크리스트

지금까지 한 작업을 정리하면 다음과 같다.

- ✅ `pip install agent-evaluator`
- ✅ `QuickEval("eval_results/", auto_save=True)` 생성
- ✅ `str`을 반환하는 함수 → `@eval_session.qa` 데코레이터 적용 (레벨 0)
- ✅ 객체/dict를 반환하는 함수 → 위임 어댑터로 래핑 (레벨 0)
- ✅ 평소대로 실행 후 `agent-eval dashboard`로 첫 숫자 확인

기존 로직은 단 한 줄도 바뀌지 않았다. 새로 작성한 코드는 `wrappers.py`와 `adapters.py` 두 파일뿐이다.

다음 단계(15편)에서는 이 측정값을 바탕으로 **Gate A–G 전체 Harness Config를 연결**하고, 보안 스캔과 멀티에이전트 합의율까지 한 번에 연결하는 방법을 다룬다.

---

## 👇 더 알아보기

**GitHub**: [https://github.com/bullpeng72/Agent-Evaluator](https://github.com/bullpeng72/Agent-Evaluator)
— 이 글의 전체 예제 코드는 `Evaluator_Examples/ch24_quickeval_entry.py`에 있습니다.

**PyPI**: [https://pypi.org/project/agent-evaluator/](https://pypi.org/project/agent-evaluator/)
— `pip install agent-evaluator` 로 바로 설치 가능합니다.

**이 시리즈의 다른 글**
- [13편] LangChain·CrewAI·AutoGen 프레임워크 통합 어댑터 완전 가이드
- **[14편] 기존 LangChain 프로젝트에 평가 붙이기 — 30분 실전 가이드** ← 지금 여기
- [15편] Gate A–G 전체 Harness 연결 — 보안 스캔부터 멀티에이전트 합의율까지

> 질문이나 이식 과정에서 막히는 부분이 있다면 [GitHub Issues](https://github.com/bullpeng72/Agent-Evaluator/issues)에 남겨주세요.