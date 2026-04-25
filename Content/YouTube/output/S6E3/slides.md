---
marp: true
theme: default
paginate: true
style: |
  section {{
    font-family: 'Noto Sans KR', sans-serif;
    font-size: 28px;
  }}
  section.lead h1 {{
    font-size: 52px;
  }}
  code {{
    font-size: 22px;
  }}
  .highlight {{
    color: #e63946;
    font-weight: bold;
  }}
---

<!-- _class: lead -->

# 30분 안에 첫 측정값 얻기 — 실전 이식 실습

### Season 6 · S6E3

---

## 이 영상에서 다루는 것



---

## ⏱️ 타이머 시작 — 지금 이 순간부터 30분



---

## 이 영상에서 다루는 것

- 지금 이 순간, 타이머를 30분으로 맞춰놓겠습니다
- 여러분의 기존 AI 에이전트 코드에 평가 시스템을 붙이고, 실제 숫자를 화면에 찍어내는 것
- 리팩터링도 없고, 아키텍처 개편도 없습니다
- 기존 코드를 최대한 건드리지 않고, 딱 6줄만 추가해서 첫 측정값을 얻는 방법, 지금 바로 시작합니다

---

## 이식 제1원칙 — 아무것도 깨지 않는다



---

## 이식의 제1원칙: 측정과 수정은 분리한다

- 자, 먼저 질문 하나 드릴게요
- 기존 프로젝트에 뭔가 새로운 코드를 붙이다가, 오히려 기존 기능을 망가뜨린 경험이 있으신 분
- 아마 다들 한 번씩은 있으실 겁니다
- 평가 코드를 이식할 때 제일 흔하게 일어나는 실수가 바로 이겁니다
- "어, 평가하는 김에 이 부분도 리팩터링해볼까?" 라는 생각이 드는 거예요
- 함수 인터페이스를 슬쩍 바꿔보거나, 로그를 남기려고 기존 흐름에 분기를 하나 추가하거나

---

## 침습도 레벨 0–3 — 1단계는 0과 1만 허용



---

## 침습도 레벨 4단계 — 지금은 0과 1만

- 기존 프로젝트에 평가를 붙이는 방법을 침습도 기준으로 4단계로 나눠볼게요
- 이 분류를 머릿속에 넣어두면, 나중에 "지금 내가 무리하고 있는 건 아닌가"를 스스로 체크할 수 있습니다
- **레벨 0** — 반환값 래핑만 합니다
- 기존 함수를 호출하는 얇은 래퍼 함수를 새로 작성하는 거예요
- 기존 코드 파일을 아예 열지 않습니다
- 오늘 주로 다룰 방식이고, 1단계의 권장 방식입니다

---

## 핵심 도구 3종 — 뭘 언제 쓰는가



---

## 오늘 쓸 핵심 도구 — QuickEval, PerformanceMonitor, create_taskresult

- 코드로 넘어가기 전에, 오늘 실제로 쓸 도구들을 빠르게 짚고 넘어갈게요
- Python 개발자 여러분이면 API 이름만 봐도 금방 감이 오실 겁니다
- 첫 번째는 **QuickEval**입니다
- 평가 세션을 가장 간단하게 시작하는 Facade예요
- `QuickEval("results/")` 한 줄이 전부입니다
- 그 다음에 `@eval_session.qa` 같은 데코레이터를 함수에 붙이면, 그 함수가 호출될 때마다 자동으로 결과가 기록됩니다

---

## 첫 측정점 선택 — 세 가지 기준과 흔한 실수



---

## 첫 측정점을 고르는 세 가지 기준

- 자, 도구는 알았고, 이제 "어디에 측정점을 붙이느냐"가 문제입니다
- 실제 프로젝트에 가보면 평가 대상이 될 수 있는 함수가 수십 개입니다
- 그중에서 **첫 번째** 측정점을 잘못 고르면 1단계가 복잡해집니다
- 세 가지 기준을 전부 만족하는 함수를 찾아야 합니다
- **기준 1: 입출력이 명확하다**

파라미터가 3개 이하고, 반환값이 단일 타입이면 이상적입니다
- `question: str`을 받아서 답변 텍스트를 돌려주는 함수라면 완벽합니다

---

## 레벨 0 래핑 — 기존 파일을 열지 않는다



---

## 범용 패턴: 레벨 0 래핑

- 이제 코드로 넘어갑니다
- 어떤 프로젝트든 기존 LLM 호출 함수를 감싸는 범용 레벨 0 래핑 패턴입니다.

---

## 💻 코드 실습

> level0_pattern.py — QuickEval 세션 생성 + 기존 함수를 호출하는 래퍼 함수 작성 패턴

---

## 범용 패턴: 레벨 0 래핑

- 패턴을 보시면 딱 세 가지 요소로 구성돼 있습니다
- 첫째, `QuickEval("eval_results/")` 한 줄로 평가 세션을 시작합니다
- 결과 파일이 저장될 경로를 인자로 넘겨줍니다
- 폴더가 없어도 자동으로 만들어줍니다
- 둘째, 기존 함수는 **전혀 건드리지 않습니다**
- 소스 파일도 열지 않습니다

---

## QAAgent 이식 — 세 가지 기준 적용 + 6줄 추가



---

## Lecture_forge QAAgent 이식 — 6줄 추가로 측정 시작

- 자, 이제 실제 프로젝트 코드로 들어갑니다
- 예제 프로젝트 이름은 **Lecture_forge**입니다
- 강의 자료를 자동으로 생성하는 AI 에이전트 시스템인데, 이 시리즈 전체를 통해서 계속 다루는 사례 프로젝트예요
- 본인의 프로젝트 함수명으로 치환하면 그대로 쓸 수 있습니다
- 세 가지 기준을 Lecture_forge에 적용하면 첫 번째 측정점으로 **`QAAgent.answer()`**가 선택됩니다
- 왜 이 함수인지 이유를 보면요

---

## 💻 코드 실습

> ch24_quickeval_entry.py — cli/chat.py 수정 전/후 비교: QAAgent.answer()에 레벨 0 이식 6줄 추가

---

## Lecture_forge QAAgent 이식 — 6줄 추가로 측정 시작

- 코드 화면을 보시면서 설명드릴게요
- 수정 전과 후를 비교하면, 추가된 코드가 딱 6줄입니다
- 1번: `from agent_evaluator import QuickEval` 임포트 한 줄
- 2번: `eval_session = QuickEval("lecture_eval_results/", auto_save=True)` 세션 생성 한 줄
- `auto_save=True`를 쓴 이유는 잠시 후에 설명드릴게요
- 3번: `_ctx = {}` 클로저 변수 선언 한 줄

---

## ContentWriter 이식 — Delegation Adapter 패턴



---

## ContentWriter 이식 — 위임 어댑터 패턴

- QAAgent는 `str`을 반환하니까 데코레이터를 바로 붙일 수 있었습니다
- 그런데 현실에서는 이런 행운이 항상 따라오지 않습니다
- Lecture_forge의 **ContentWriter**가 바로 그 경우입니다
- `write_section()` 메서드가 `SectionContent`라는 Pydantic 모델을 반환합니다
- `@eval_session.qa` 데코레이터는 `str` 반환을 요구하기 때문에 직접 붙일 수 없습니다
- 물론 `agent.py`를 열어서 레벨 1 방식으로 `return` 직전에 `monitor.record_task()`를 추가할 수도 있어요

---

## 💻 코드 실습

> ch24_quickeval_entry.py — eval/adapters.py: ContentWriterAdapter 클래스 — 위임 어댑터 패턴, try/finally 오류 기록 포함

---

## ContentWriter 이식 — 위임 어댑터 패턴

- 어댑터 구조를 보시면요
- 생성자에서 기존 `ContentWriterAgent` 인스턴스, `PerformanceMonitor` 인스턴스, 그리고 학습 목표 리스트를 받습니다
- `write_section()` 메서드는 `try/finally` 구조로 구성됩니다
- `try` 블록에서 원본 `self._agent.write_section()`을 호출하고, `finally` 블록에서 `create_taskresult()`로 결과를 기록합니다
- 여기서 핵심은 `finally` 블록입니다
- 예외가 발생하더라도 `finally`는 반드시 실행되기 때문에, `write_section()`이 에러를 던지는 경우도 `has_error=True`인 TaskResult로 기록됩니다

---

## 💻 코드 실습

> ch24_quickeval_entry.py — cli/commands/create.py: generate_lecture() 안에서 ContentWriterAdapter 적용 — 2줄 추가

---

## ContentWriter 이식 — 위임 어댑터 패턴

- 진입점 코드는 더 간단합니다
- 기존에 `writer = ContentWriterAgent(vector_store=vs)`로 생성하던 코드 바로 아래에, `if _eval_monitor:` 조건으로 어댑터로 교체합니다
- 모니터가 없는 경우엔 기존 에이전트가 그대로 동작합니다
- 완전한 opt-in 설계가 됩니다
- 이 패턴의 장점을 정리해볼게요
- 첫째, `ContentWriterAgent`의 소스 파일을 열지 않습니다

---

## 첫 번째 측정 결과 — 숫자들이 말해주는 것



---

## 첫 실행 — 어떤 숫자가 보이는가

- 두 개의 측정점을 삽입했습니다
- 이제 Lecture_forge를 실제로 돌려볼 차례입니다.

---

## 💻 코드 실습

> ch24_quickeval_entry.py — CLI 실행 명령 + lecture_eval_results/ 폴더에 JSON·HTML 파일 생성 확인

---

## 첫 실행 — 어떤 숫자가 보이는가

- 실행하고 나면 `lecture_eval_results/` 폴더에 JSON 파일과 HTML 파일이 생성됩니다
- 이 두 파일이 보이면 1단계 이식에 성공한 겁니다
- 그럼 이 첫 번째 결과에서 어떤 숫자들이 보이는지 살펴볼게요
- **TCR, Task Completion Rate**
- 가장 먼저 봐야 할 숫자입니다
- 예외 없이 완료된 태스크의 비율이에요

---

## 베이스라인 — 판단이 아니라 기준점 설정



---

## 베이스라인 설정 — 첫 숫자 이후 할 일

- 첫 번째 숫자를 얻었습니다
- 여기서 한 가지 꼭 기억해야 할 게 있습니다
- **첫 번째 측정값은 "좋다/나쁘다"를 판단하는 게 목적이 아닙니다
- 베이스라인을 설정하는 것이 목적입니다.**

지금 이 숫자가 앞으로 모든 개선의 기준점이 됩니다
- 첫 번째 TCR이 70%라고 실망할 필요 없어요
- "지금 30%가 에러로 죽는구나

---

## QnA — 이식 중 자주 막히는 순간들



---

## 자주 막히는 지점과 함정 피하기

- 실제로 이 패턴을 적용해보신 분들이 자주 막히는 지점들을 짚어드릴게요
- **Q: 비동기 에이전트, 즉 `async def`에는 어떻게 적용하나요?**

`@eval_session.qa`는 동기 함수용입니다
- `async def`로 선언된 함수에는 `async_evaluation_session` 컨텍스트 매니저를 사용하거나, `create_taskresult()`를 직접 호출하는 방식이 더 안전합니다
- `async with async_evaluation_session("파일명") as monitor:` 블록 안에서 `await`로 에이전트를 호출하고, `monitor.record_task()`로 수동 기록하는 패턴이 깔끔합니다
- **Q: 같은 함수가 여러 스레드에서 동시에 호출되면 데이터가 뒤섞이지 않나요?**

`QuickEval`과 `PerformanceMonitor` 내부는 `threading.Lock`으로 보호되어 있습니다
- 동시 호출에서도 결과 누락이나 중복 기록이 발생하지 않습니다

---

## ⏱️ 30분 체크포인트 — 단계별 타임라인



---

## 30분 체크포인트 — 지금 당장 해야 할 것들

- 타이머를 다시 보겠습니다
- 오늘 배운 내용을 기반으로 실제로 30분 안에 해야 할 것들을 체크리스트로 정리해드릴게요
- 이 영상을 다시 틀어놓고 같이 따라 하셔도 됩니다
- **0분 ~ 5분: 설치 및 임포트 확인**

`pip install agent-evaluator`로 설치하고, `from agent_evaluator import QuickEval`이 에러 없이 임포트 되는지 확인합니다
- 이미 설치된 분들은 버전을 확인해보세요
- `agent-eval --version`으로 0.8.5 이상인지 체크합니다

---

## 핵심 정리 + 다음 편 예고



---

<!-- _class: lead -->

## 핵심 정리

- 오늘 영상을 정리하겠습니다
- 첫째, 기존 코드를 수정하지 않는 레벨 0 침습 원칙을 지키면 단 6줄 추가만으로 첫 측정을 시작할 수 있습니다
- 둘째, `str`을 반환하는 함수는 `@eval_session.qa` 데코레이터로, Pydantic 모델 등 다른 타입을 반환하는 함수는 위임 어댑터 패턴으로 각각 대응합니다

---

