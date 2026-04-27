---
marp: true
theme: default
size: 16:9
paginate: true
style: |
  section {
    font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
    font-size: 30px;
    padding: 44px 72px;
    background-color: #0f1117;
    color: #e2e8f0;
    line-height: 1.65;
  }
  h1 {
    font-size: 56px;
    color: #60a5fa;
    line-height: 1.2;
    margin-bottom: 8px;
  }
  h2 {
    font-size: 38px;
    color: #93c5fd;
    border-bottom: 3px solid #1d4ed8;
    padding-bottom: 10px;
    margin-bottom: 24px;
  }
  h3 {
    font-size: 28px;
    color: #94a3b8;
    font-weight: 400;
  }
  ul { padding-left: 36px; margin: 0; }
  li { margin: 10px 0; line-height: 1.5; }
  strong { color: #fbbf24; }
  em { color: #a78bfa; font-style: normal; }
  code {
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 23px;
    background: #1e293b;
    padding: 2px 8px;
    border-radius: 4px;
    color: #86efac;
  }
  pre {
    background: #0d1117;
    border-radius: 10px;
    padding: 22px 28px;
    border-left: 4px solid #1d4ed8;
    margin: 4px 0 0 0;
  }
  pre code {
    font-size: 19px;
    background: transparent;
    padding: 0;
    color: #cdd6f4;
    line-height: 1.6;
  }
  blockquote {
    border-left: 4px solid #60a5fa;
    padding: 12px 24px;
    background: #1e293b;
    border-radius: 0 8px 8px 0;
    color: #94a3b8;
    margin: 16px 0;
  }
  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
  }
  section.lead h1 { font-size: 60px; }
  section.lead h2 { border: none; font-size: 44px; color: #60a5fa; }
  section.lead h3 { font-size: 30px; margin-top: 16px; }
  section.concept {
    background: linear-gradient(135deg, #0f1117 0%, #1e1b4b 100%);
  }
  section.concept h2 {
    font-size: 46px;
    color: #a78bfa;
    border-color: #7c3aed;
    text-align: center;
    margin-top: 40px;
  }
  section.code h2 { font-size: 30px; color: #86efac; border-color: #15803d; }
  footer { display: none; }
---

<!-- _class: lead -->

# 30분 안에 첫 측정값 얻기 — 실전 이식 실습

### Season 6 · S6E3

---

<!-- _class: concept -->

## ⏱️ 타이머 ON — 지금 이 순간부터 30분

---

<!-- _class: concept -->

## 제1원칙 — 측정과 수정은 절대 동시에 하지 않는다

---

## 이식의 제1원칙 — 아무것도 깨지 않는다 (1/2)

- 자, 경험 있으신 분들은 공감하실 거예요. 기존 프로젝트에 뭔가 새 기능을 붙이려고…
- 평가 코드 이식할 때 이게 제일 흔한 실수입니다. 측정 코드 삽입하면서 함수 인터페이스도…
- 측정과 수정을 동시에 하면 나중에 버그가 났을 때 어디서 문제가 생겼는지 구분이 안…
- 1단계의 원칙은 딱 하나입니다. 기존 코드의 입력과 출력을 바꾸지 않는다. 반환값만…
- 이 원칙 위에서 오늘 사용할 도구들을 빠르게 정리해볼게요. 처음 보시는 분들을 위해 세…

---

## 이식의 제1원칙 — 아무것도 깨지 않는다 (2/2)

- 첫 번째, `QuickEval`입니다. 평가 세션을 가장 간단하게 시작하는 파사드예요.…
- 두 번째, `@eval_session.qa`입니다. 에이전트 함수에 붙이는…
- 세 번째, `create_taskresult()`입니다. 데코레이터 적용이 불가능한 상황…
- 정리하자면, `str` 반환하는 함수엔 `@eval_session.qa` 바로 붙이면…

---

<!-- _class: concept -->

## 침습도 0~3 — 1단계는 0과 1만 허용

---

## 침습도 레벨 — 얼마나 건드릴 것인가 (1/2)

- 기존 프로젝트에 평가를 이식하는 방법은 침습도에 따라 4단계로 나뉩니다. 이 분류가…
- 레벨 0 — 반환값 래핑만 하기. 기존 함수를 호출하는 얇은 래퍼 함수를 새로 작성하는…
- 레벨 1 — 반환 직후 기록 추가. 기존 함수의 마지막 `return` 바로 앞에…
- 레벨 2 — 내부 흐름에 훅 추가. 함수 중간 단계에 측정 코드를 삽입하는 거예요.…
- 레벨 3 — 아키텍처 변경. 에이전트 클래스를 상속하거나, 함수 인터페이스를 바꾸거나,…

---

## 침습도 레벨 — 얼마나 건드릴 것인가 (2/2)

- 오늘은 레벨 0과 레벨 1만 씁니다. 결론은 간단해요.
- 한 가지 더 짚고 넘어갈 게 있어요. 데코레이터 적용 가능한 상황과 불가능한 상황을 미리…

---

<!-- _class: concept -->

## 측정점 선택 체크리스트 — 3가지 모두 만족해야

---

## 첫 측정점을 고르는 세 가지 기준 (1/2)

- 지금 여러분 프로젝트에 함수가 수십 개 있을 거예요. 그중에서 첫 번째 측정점을 어떻게…
- 세 가지 기준이 있는데, 세 가지 다 만족하는 함수를 찾는 게 이상적이에요.
- 기준 1: 입출력이 명확하다. 파라미터 3개 이하, 반환값이 단일 타입이면 이상적입니다.…
- 기준 2: 이미 성공 기준이 있다. 기존 코드에 검증 로직이 있거나, "이 함수가 이걸…
- 기준 3: 독립적으로 호출 가능하다. 다른 에이전트의 상태나 전역 변수에 의존하지 않고,…

---

## 첫 측정점을 고르는 세 가지 기준 (2/2)

- 흔한 선택 실수도 말씀드릴게요. "메인 오케스트레이터 함수를 측정하면 전체를 한 방에 볼…
- 세 가지 다 만족하는 함수가 없다면요? 기준 1번, 입출력 명확한 함수만 만족해도 일단…

---

<!-- _class: concept -->

## 범용 래핑 패턴 — QuickEval + @eval_session.qa

---

## 범용 레벨 0 패턴 — 어떤 프로젝트든 이 틀 안에 들어온다

- 자, 이론은 충분히 했으니 실제 코드 패턴 보겠습니다.

---

<!-- _class: code -->

## 💻 `generic_wrapper.py`

```python
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
    ...
```

---

## 범용 레벨 0 패턴 — 어떤 프로젝트든 이 틀 안에 들어온다

- 화면에 코드 보이시죠? 핵심만 짚겠습니다.
- `QuickEval("eval_results/")` — 이 한 줄이 평가 세션을…
- `@eval_session.qa` — 이 데코레이터가 붙은 함수는 호출될 때마다 자동으로…
- 래퍼 함수 내부를 보시면, 기존 `existing_function`을 그냥 호출하고,…
- 그러고 나서 기존 호출부에서 함수명만 바꿔주면 끝. `existing_function`이…
- 복잡하게 만들면 이식 자체가 또 하나의 프로젝트가 되어버려요. 그러면 30분이 아니라…

---

<!-- _class: concept -->

## ⏱️ 타이머 START — QAAgent 레벨 0 이식 실습

---

## 실전 이식 1 — QAAgent, 타이머 시작

- 자, 여기서부터 실제 프로젝트에 적용합니다. 오늘 예제 프로젝트는…
- 먼저 QAAgent의 `answer()` 메서드에 세 가지 기준을 대입해볼게요.
- 입출력 명확한가요? `question: str` 받아서 `dict` 반환합니다. 딕셔너리…
- 성공 기준이 있나요? 네, 코드 안에 이미 검증 로직이 있어요. 300단어 이상, 출처…
- 독립 호출 가능한가요? 네, `lecture_dir`만 있으면 단독으로 실행됩니다.
- 완벽한 첫 측정점이에요. 바로 이식 들어갑니다.

---

<!-- _class: code -->

## 💻 `cli/chat.py`

```python
print("\n=== 섹션 8: QuickEval Facade ===")

eval_qe = QuickEval(
    output_dir=_OUTPUT_DIR,
    auto_save=True,
    auto_save_interval=5,
    auto_save_filename="ch12_quickeval_auto",
)

@eval_qe.qa
def qe_qa_agent(question: str, ground_truth: str = "") -> str:
    return f"QE 답변: {question}"
    ...
```

---

## 실전 이식 1 — QAAgent, 타이머 시작 (1/2)

- 수정한 거 보이시죠? 총 6줄 추가입니다. 기존 로직 수정은 0줄이에요.
- 여기서 두 가지 포인트가 특히 중요합니다. 꼭 이해하고 넘어가세요.
- 첫 번째, 왜 `result` 통째로 반환하지 않고 `result["answer"]`만…
- `@eval_session.qa` 데코레이터는 내부적으로…
- 만약 `result` 딕셔너리를 통째로 반환하면 어떻게 되냐고요?…

---

## 실전 이식 1 — QAAgent, 타이머 시작 (2/2)

- 그래서 평가에 쓸 텍스트인 `answer`만 반환하고, 나머지 데이터인…
- 두 번째, 왜 `auto_save=True`가 필수냐고요?
- `while True` 루프를 생각해보세요. 이 루프는 끝나지 않잖아요. 루프 밖에…
- `QuickEval("경로/", auto_save=True)`로 생성하면 10건마다…
- 타이머 확인해보면 — 여러분이 직접 해보시면 실제로 10분이면 충분합니다.

---

<!-- _class: concept -->

## 위임 어댑터 패턴 — Pydantic 모델 반환 시의 해법

---

## 실전 이식 2 — ContentWriter, 위임 어댑터 패턴

- 두 번째 측정점, ContentWriter입니다. 얘는 상황이 조금 달라요.
- ContentWriter의 `write_section()` 메서드는…
- 선택지가 두 가지 있어요. 레벨 1 방식으로 `agent.py`를 직접 수정하거나,…
- 아이디어는 정말 간단합니다. 기존 에이전트 인스턴스를 감싸는 어댑터 클래스를 별도 파일에…

---

<!-- _class: code -->

## 💻 `src/lecture_forge/eval/adapters.py`

```python
    def write_section(self, section: MockSection, curriculum: MockCurriculum,
                      available_images=None) -> MockSectionContent:
        task_id = f"section_{section.id}"
        start = time.perf_counter()
        has_error = False; error_msg = None; result = None
        try:
            result = self._agent.write_section(section, curriculum, available_images)
        except Exception as exc:
            has_error = True; error_msg = str(exc); raise
        finally:
            elapsed = time.perf_counter() - start
            content_text = result.markdown_content if result else ""
    ...
```

---

## 실전 이식 2 — ContentWriter, 위임 어댑터 패턴

- 코드에서 특히 주목하실 부분 세 가지를 짚겠습니다.
- 첫째, try/finally 구조입니다. `write_section()`이 예외를 던져도…
- 둘째, extra 딕셔너리입니다. `phase`, `section_id`,…
- 셋째, `__getattr__` 투명 위임입니다. 이게 위임 어댑터 패턴의 핵심이에요.…

---

<!-- _class: code -->

## 💻 `cli/commands/create.py`

```python
curriculum = designer.design(analysis, TOPIC, DURATION, AUDIENCE)

# ContentWriterAdapter는 learning_objectives도 받는다
writer = ContentWriterAdapter(base_writer, monitor, curriculum.learning_objectives)

for section in curriculum.sections:
    content: MockSectionContent = writer.write_section(section, curriculum)
    print(f"  ✅ {section.title:<25}  단어수={content.word_count}"
          f"  (SectionContent 반환값 그대로)")

# __getattr__ 위임 확인
stats = writer.get_vector_store_stats()
    ...
```

---

## 실전 이식 2 — ContentWriter, 위임 어댑터 패턴

- 진입점 코드를 보시면, `_eval_monitor`가 있을 때만 어댑터로 교체합니다.…
- 이 방식의 장점을 정리해볼게요.
- `ContentWriterAgent`의 소스 파일을 열지 않습니다. 어댑터를 씌운 후에도…
- 수정한 것: `eval/adapters.py` 새 파일 하나 + `create.py`에…

---

<!-- _class: concept -->

## 첫 측정값 해석 — 기준선이 생겼다는 것의 의미

---

## 첫 실행 — 어떤 숫자가 보이는가

- 자, 두 개의 측정점을 삽입했습니다. 이제 Lecture_forge를 실행하고 나서…

---

<!-- _class: code -->

## 💻 `터미널 실행`

```bash
$ python -m lecture_forge chat ./lectures

# 결과 확인
$ ls lecture_eval_results/
quickeval.json
```

---

## 첫 실행 — 어떤 숫자가 보이는가 (1/2)

- `lecture_eval_results/` 디렉토리를 열어보면 JSON 파일이 생겼을…
- Task Completion Rate, TCR. "에이전트가 요청받은 작업을…
- accuracy. Token F1, Jaccard Similarity, LCS…
- execution_time. 각 호출마다 몇 초 걸렸는지가 다 찍혀 있어요. 10건 정도…
- ContentWriter 쪽에선 `word_count` 같은 extra 데이터도 함께…

---

## 첫 실행 — 어떤 숫자가 보이는가 (2/2)

- 대시보드로도 확인해볼 수 있어요. `agent-eval dashboard` 명령 하나면…
- 이 시점에서 중요한 마음가짐을 하나 말씀드릴게요. 1단계의 숫자들이 지금 당장 완벽한…
- 이전에는 "느낌상 나아진 것 같은데요" 였다면, 이제는 "TCR이 72%에서 81%로…

---

<!-- _class: concept -->

## 이식 실수 TOP 3 — 반드시 피해야 할 것들

---

## 이식하면서 자주 하는 실수 — 그리고 해결책

- 마지막으로, 이 과정에서 자주 하는 실수 세 가지만 짚겠습니다. 저도 처음에 다 겪어봤던…
- 실수 1: dict 통째로 반환하기. 방금 QAAgent에서 설명드렸죠.…
- 실수 2: long-running 세션에서 `auto_save` 빼먹기. `while…
- 실수 3: 첫 이식에 측정 대상을 너무 많이 잡기. "어차피 하는 김에 다 하자" — 이…
- 그리고 하나 더 — 이식 후에 기존 테스트를 반드시 돌려보세요. 레벨 0 이식이라 기존…
- 이 세 가지 실수만 피해도 30분 안에 첫 측정값 뽑는 거 충분히 됩니다.

---

<!-- _class: concept -->

## 핵심 정리 + 다음 편 예고

---

<!-- _class: lead -->

## 핵심 정리

- 자, 오늘 내용 세 줄로 정리합니다.
- 첫째, 1단계 이식의 원칙은 레벨 0과 레벨 1만 — 기존 코드 파일을 여지 말고,…
- 둘째, 첫 측정점은 입출력 명확 + 성공 기준 존재 + 독립 호출 가능 — 이 세 가지…
- 셋째, `auto_save=True`는 long-running 세션에서 필수고, 첫…
- 다음 편에서는 이 기준선을 바탕으로 Gate A부터 G까지 Harness Config를…

---

