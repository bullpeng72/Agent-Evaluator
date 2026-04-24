# Chapter 25. 전체 통합: Harness Gate를 파이프라인에 연결하기

> **이 챕터에서 배우는 것**
> - 분산된 측정점을 하나로 합치는 **중앙 모니터 패턴**
> - 기존 추적기(비용, 품질 점수 등)의 데이터를 TaskResult로 변환하는 **어댑터 패턴**
> - Gate E 보안 스캔을 외부 입력 경로에 삽입하는 방법
> - Lecture_forge `build_lecture_monitor()` 전체 구현
> - Gate 리포트가 실제로 코드 버그를 찾아낸 사례

> **독자별 읽기 가이드**
> - **👨‍💻 개발자**: §25.1(중앙 모니터 패턴) → §25.3(어댑터 패턴) → §25.5(실제 구현) 순으로 읽으면 패턴을 먼저 이해하고 코드를 볼 수 있습니다.
> - **📋 QA 관리자**: §25.6(Gate 리포트 출력)과 §25.7(Gate가 찾아낸 버그) 를 먼저 읽으면 "왜 이 작업을 해야 하는가"의 실질적 근거를 얻을 수 있습니다.
> - **이 챕터는 Ch24(1단계)의 측정 코드를 확장합니다.** Ch24를 먼저 완료한 후 이 챕터를 시작하세요.

---

## 25.1 왜 중앙 모니터가 필요한가

Ch24에서 측정 코드를 삽입한 후 프로젝트는 다음 상태가 됐다.

```
chat.py         → eval_session (QuickEval)
content_writer.py → _eval_monitor (PerformanceMonitor)
```

두 개의 독립된 평가 세션이 존재한다. QAAgent의 측정 결과와 ContentWriter의 측정 결과가 서로 다른 파일에 저장된다. 강의 1건의 전체 품질을 한 리포트로 볼 수 없다.

에이전트가 12개인 Lecture_forge에서 이 패턴이 계속되면 12개의 독립된 평가 파일이 생긴다. 이것은 1단계에서는 허용했지만, 2단계에서는 반드시 통합해야 한다.

**중앙 모니터 패턴**은 이 문제를 해결한다. 파이프라인 진입점에서 단일 `PerformanceMonitor`를 만들고, 모든 에이전트가 이것을 공유한다.

@@HTML_START@@
<style>
.arch-compare{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0;}
.arch-card{padding:16px;border-radius:10px;}
.arch-title{font-weight:700;font-size:14px;margin-bottom:12px;}
.arch-diagram{font-family:monospace;font-size:12px;padding:12px;border-radius:8px;white-space:pre;line-height:1.6;}
</style>

<div class="arch-compare">
  <div class="arch-card" style="background:#ffebee;border:2px solid #ef9a9a;">
    <div class="arch-title" style="color:#c62828;">❌ 1단계: 분산된 모니터</div>
    <div class="arch-diagram" style="background:#ffcdd2;color:#b71c1c;">chat.py
  eval_session_A ← QAAgent 결과
  → chat_results.json

content_writer.py
  eval_monitor_B ← ContentWriter 결과
  → writer_results.json

(강의 1건의 전체 뷰 없음)</div>
  </div>
  <div class="arch-card" style="background:#e8f5e9;border:2px solid #a5d6a7;">
    <div class="arch-title" style="color:#1b5e20;">✅ 2단계: 중앙 모니터</div>
    <div class="arch-diagram" style="background:#c8e6c9;color:#1b5e20;">cli/create.py (진입점)
  monitor ← 단일 PerformanceMonitor
     │
     ├── ContentWriter.write_section()
     ├── QualityEvaluator.evaluate()
     ├── RevisionAgent.revise()
     └── QAAgent.answer()

→ lecture_001.json (전체 뷰)</div>
  </div>
</div>
@@HTML_END@@

---

## 25.2 중앙 모니터 설계: 빌더 함수 패턴

어떤 프로젝트든 중앙 모니터를 구성하는 방법은 동일하다. **"모니터를 만드는 함수"를 별도 파일에 작성한다.**

> **⚠️ PerformanceMonitor 역할 범위**
>
> `PerformanceMonitor.__init__()`은 **기록 설정 전용**이다. `output_dir`, `enable_*` 플래그, `auto_save` 같은 인자만 받는다.
>
> Harness Gate Config(InstructionConfig 등 33개)는 **`@agent_eval` 데코레이터**에 전달하는 것이 원칙이다.
>
> 단, 위임 어댑터 패턴처럼 `@agent_eval` 대신 `create_taskresult() + record_task()`로 수동 기록하는 경우에는 Gate Config를 데코레이터에 전달할 수 없다. 이때 Gate 측정은 `extra` 필드, `task_type`, `has_error`, `execution_time` 같은 기본 필드를 통해 이루어진다.

```python
# your_project/eval/monitor.py  (새 파일 — 기존 코드 수정 없음)

from pathlib import Path
from typing import Optional
from agent_evaluator import PerformanceMonitor


def build_project_monitor(
    output_dir: str = "eval_results/",
    *,
    enable_llm_judge: bool = False,
    judge_model: Optional[str] = None,
) -> PerformanceMonitor:
    """
    프로젝트 파이프라인용 PerformanceMonitor를 생성한다.
    기록 설정만 담당 — Gate Config는 어댑터의 create_taskresult() extra 필드로 전달된다.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    return PerformanceMonitor(
        output_dir=output_dir,
        enable_security_metrics=True,       # 외부 입력(PDF 등) 존재 → Gate E 자동 활성화
        enable_hallucination_detection=False,
        enable_llm_judge=enable_llm_judge,
        judge_model=judge_model,
        judge_sample_rate=0.2,
        auto_save=True,
        auto_save_interval=5,
    )
```

빌더 함수가 하는 일은 두 가지다. `output_dir` 디렉토리를 만들고 `PerformanceMonitor`를 반환한다. `enable_security_metrics=True` 한 줄이 Gate E(보안 스캔)를 활성화한다. LLM 채점이 필요한 경우 `enable_llm_judge=True`로 opt-in한다.

**Gate 커버리지는 어댑터에서 완성된다.** 각 어댑터가 `create_taskresult()`를 호출할 때 전달하는 `task_type`, `ground_truth`, `extra`, `has_error`, `execution_time` 필드가 Gate A–G 지표의 원천 데이터가 된다.

---

## 25.3 위임 어댑터 패턴: 에이전트를 감싸서 계측하기

Ch24의 `ContentWriterAdapter`에서 소개한 위임 어댑터 패턴을 일반화한다.

이 패턴이 필요한 상황은 명확하다. 에이전트 메서드가 `str`이 아닌 Pydantic 모델이나 복잡한 객체를 반환해 `@agent_eval` 데코레이터를 직접 적용할 수 없을 때, 그리고 기존 파일을 전혀 수정하지 않으면서 계측하고 싶을 때다.

### 위임 어댑터의 범용 구조

```python
import time
from typing import Optional
from agent_evaluator import PerformanceMonitor, create_taskresult


class SomeAgentAdapter:
    """SomeAgent를 감싸 target_method()를 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor) -> None:
        self._agent = agent
        self._monitor = monitor

    def target_method(self, input_data):
        """원본 메서드를 호출하고 결과를 monitor에 기록한다."""
        task_id = f"task_{getattr(input_data, 'id', 'unknown')}"
        start = time.perf_counter()
        has_error = False
        error_msg: Optional[str] = None
        result = None

        try:
            result = self._agent.target_method(input_data)   # 원본 호출
        except Exception as exc:
            has_error = True
            error_msg = str(exc)
            raise
        finally:
            elapsed = time.perf_counter() - start

            # 결과에서 평가에 쓸 텍스트 추출
            response_text = _extract_text(result)
            ground_truth = _extract_ground_truth(input_data)

            extra = {
                "phase": "phase_name",   # Gate G: 단계별 지연 분석
                # 기타 Gate 측정에 필요한 필드
            }

            task = create_taskresult(
                task_id=task_id,
                question=str(input_data),
                response=response_text,
                ground_truth=ground_truth,
                execution_time=elapsed,
                task_type="qa",          # 에이전트 역할에 맞는 task_type
                has_error=has_error,     # Gate C: 오류 발생 여부
                error_message=error_msg,
                extra=extra,
            )
            self._monitor.record_task(task)

        return result   # 원본과 동일한 반환값 — 호출부 변경 없음

    def __getattr__(self, name: str):
        """계측하지 않는 메서드/속성은 원본으로 투명하게 위임."""
        return getattr(self._agent, name)
```

### 핵심 설계 원칙

**`try/except/finally` 구조**: `finally` 블록은 성공·실패 어느 경우에도 실행된다. 예외가 발생해도 TaskResult가 monitor에 기록된다. `has_error=True`인 태스크가 Gate C(FaultTolerance) 복구율 측정에 포함된다.

**`__getattr__` 위임**: 어댑터가 계측하는 메서드 외의 모든 속성과 메서드는 원본 에이전트로 투명하게 전달된다. 호출부에서 어댑터와 원본을 구분할 필요가 없다.

**gate 측정 필드 매핑**: `create_taskresult()`에 전달하는 필드가 Gate 지표의 원천이다.

| 필드 | Gate 기여 |
|------|-----------|
| `task_type` | TCR 분류, Gate A 정렬 |
| `ground_truth` | Gate A: 키워드 오버랩(AccuracyEvaluator) |
| `execution_time` | Gate D: SLA P95 계산 |
| `has_error=True` | Gate C: TCR에서 실패 태스크로 집계 |
| `extra["phase"]` | Gate G: 단계별 지연 기여도 분석 |
| `enable_security_metrics=True` (모니터 설정) | Gate E: response 보안 스캔 자동 실행 |

---

## 25.4 Lecture_forge 어댑터 4종

Lecture_forge에는 계측 대상 에이전트가 4개 있다. 각각 별도 어댑터 클래스를 작성한다. 모든 어댑터는 동일한 `monitor` 인스턴스를 공유하므로, 4개 에이전트의 결과가 하나의 JSON 파일에 통합된다.

```python
# src/lecture_forge/eval/adapters.py  (새 파일 — 기존 파일 수정 없음)

import time
from typing import List, Optional
from agent_evaluator import PerformanceMonitor, create_taskresult


class ContentWriterAdapter:
    """ContentWriterAgent.write_section()을 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor,
                 learning_objectives: List[str]) -> None:
        self._agent = agent
        self._monitor = monitor
        self._learning_objectives = learning_objectives

    def write_section(self, section, curriculum, available_images=None):
        task_id = f"section_{getattr(section, 'id', 'unknown')}"
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
                task_id=task_id,
                question=f"섹션 '{getattr(section, 'title', '')}' 콘텐츠 작성",
                response=content_text,
                ground_truth=ground_truth,        # Gate A: 학습목표 키워드 오버랩
                execution_time=elapsed,           # Gate D: SLA P95
                task_type="document_creation",
                has_error=has_error,              # Gate C: 오류 시 TCR 실패 집계
                error_message=error_msg,
                extra={
                    "phase": "content_writing",   # Gate G: 단계별 지연 기여도
                    "section_id": getattr(section, "id", ""),
                    "word_count": getattr(result, "word_count", 0) if result else 0,
                },
            ))
        return result

    def __getattr__(self, name: str):
        return getattr(self._agent, name)


class CurriculumDesignerAdapter:
    """CurriculumDesignerAgent.design()을 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor) -> None:
        self._agent = agent; self._monitor = monitor

    def design(self, analysis_result, topic: str, duration: int, audience_level: str):
        task_id = f"curriculum_{topic[:40].replace(' ', '_')}"
        start = time.perf_counter()
        has_error = False; error_msg = None; result = None
        try:
            result = self._agent.design(analysis_result, topic, duration, audience_level)
        except Exception as exc:
            has_error = True; error_msg = str(exc); raise
        finally:
            elapsed = time.perf_counter() - start
            sections = getattr(result, "sections", []) if result else []
            objectives = getattr(result, "learning_objectives", []) if result else []
            total_time = getattr(result, "total_estimated_time", 0) if result else 0
            response_text = (
                f"커리큘럼 설계 완료. 섹션 {len(sections)}개, 총 {total_time}분. "
                f"학습목표: {'; '.join(objectives[:3])}"
            ) if result else ""
            self._monitor.record_task(create_taskresult(
                task_id=task_id,
                question=f"주제 '{topic}', {duration}분, {audience_level} 커리큘럼 설계",
                response=response_text,
                ground_truth=f"{topic} {duration}분 {audience_level}",  # Gate A
                execution_time=elapsed,
                task_type="planning",
                has_error=has_error, error_message=error_msg,
                extra={"phase": "curriculum_design", "topic": topic,
                       "duration_requested": duration, "duration_actual": total_time},
            ))
        return result

    def __getattr__(self, name: str):
        return getattr(self._agent, name)


class ContentAnalyzerAdapter:
    """ContentAnalyzerAgent.analyze()를 계측한다."""

    def __init__(self, agent, monitor: PerformanceMonitor) -> None:
        self._agent = agent; self._monitor = monitor

    def analyze(self, collection_result, image_result, topic: str):
        task_id = f"analysis_{topic[:40].replace(' ', '_')}"
        start = time.perf_counter()
        has_error = False; error_msg = None; result = None
        try:
            result = self._agent.analyze(collection_result, image_result, topic)
        except Exception as exc:
            has_error = True; error_msg = str(exc); raise
        finally:
            elapsed = time.perf_counter() - start
            key_topics = getattr(result, "key_topics", []) if result else []
            entities = getattr(result, "entities", []) if result else []
            response_text = (
                f"분석 완료. 핵심 주제 {len(key_topics)}개: "
                f"{', '.join(str(t) for t in key_topics[:10])}. "
                f"엔티티 {len(entities)}개 추출."
            ) if result else ""
            self._monitor.record_task(create_taskresult(
                task_id=task_id,
                question=f"'{topic}' 관련 핵심 주제·엔티티 분석",
                response=response_text,
                ground_truth=topic,   # Gate A: topic 키워드 포함 여부
                execution_time=elapsed,
                task_type="information_retrieval",
                has_error=has_error, error_message=error_msg,
                extra={"phase": "content_analysis", "topic": topic,
                       "key_topics_count": len(key_topics)},
            ))
        return result

    def __getattr__(self, name: str):
        return getattr(self._agent, name)


class QualityEvaluatorAdapter:
    """QualityEvaluator.evaluate()를 계측한다."""

    def __init__(self, evaluator, monitor: PerformanceMonitor) -> None:
        self._evaluator = evaluator; self._monitor = monitor

    def evaluate(self, lecture, threshold: int = 80):
        task_id = f"quality_{getattr(lecture, 'topic', 'unknown')[:30].replace(' ', '_')}"
        start = time.perf_counter()
        result = self._evaluator.evaluate(lecture, threshold)
        elapsed = time.perf_counter() - start
        overall = getattr(result, "overall_score", 0.0)
        passed = getattr(result, "passed", False)
        dim_scores = getattr(result, "dimension_scores", {})
        # Gate C: 품질 미달 = 태스크 실패 → TCR에 반영
        quality_failed = not passed
        self._monitor.record_task(create_taskresult(
            task_id=task_id,
            question=f"강의 품질 평가 (임계값 {threshold}점)",
            response=f"품질 점수 {overall:.1f}/100. {'통과' if passed else '미통과'}.",
            ground_truth=f"품질 점수 {threshold} 이상",
            execution_time=elapsed,
            task_type="qa",
            has_error=quality_failed,    # Gate C: 미달 = 실패
            error_message=(f"품질 {overall:.1f} < {threshold}" if quality_failed else None),
            extra={"phase": "quality_evaluation", "overall_score": overall,
                   "passed": passed, "threshold": threshold, **{f"dim_{k}": v
                   for k, v in dim_scores.items()}},
        ))
        return result

    def __getattr__(self, name: str):
        return getattr(self._evaluator, name)
```

4개 어댑터 모두 동일한 패턴을 따른다. `__init__`에서 원본 에이전트와 `monitor`를 받는다. 타깃 메서드에서 `try/except/finally`로 측정하고 기록한다. `__getattr__`로 나머지는 원본으로 위임한다. `return result`로 원본 반환값을 그대로 돌려준다.

---

## 25.5 Lecture_forge 전체 통합 구현

실제 파일 구조와 코드다. `eval/` 패키지 두 파일과 `create.py` 수정 한 곳이 전부다.

### 파일 구조

```
src/lecture_forge/
├── eval/                          ← 새 패키지 (기존 코드 수정 없음)
│   ├── __init__.py
│   ├── monitor.py                 ← build_lecture_monitor()
│   └── adapters.py                ← 4개 어댑터 클래스
└── cli/
    └── commands/
        └── create.py              ← --eval 플래그 추가 (~56줄)
```

### `eval/monitor.py`

```python
# src/lecture_forge/eval/monitor.py

from pathlib import Path
from typing import Optional
from agent_evaluator import PerformanceMonitor


def build_lecture_monitor(
    output_dir: str = "eval_results/",
    *,
    enable_llm_judge: bool = False,
    judge_model: Optional[str] = None,
) -> PerformanceMonitor:
    """
    LectureForge 파이프라인용 PerformanceMonitor를 생성한다.

    Gate E(보안 스캔)는 enable_security_metrics=True로 자동 활성화된다.
    Gate A–G의 나머지 측정은 어댑터가 record_task() 호출 시 extra 필드로 제공한다.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    return PerformanceMonitor(
        output_dir=output_dir,
        enable_security_metrics=True,       # Gate E: 생성 콘텐츠 보안 스캔
        enable_hallucination_detection=False,
        enable_llm_judge=enable_llm_judge,
        judge_model=judge_model,
        judge_sample_rate=0.2,
        auto_save=True,
        auto_save_interval=5,
    )
```

### `cli/commands/create.py` 변경 사항

```python
# cli/commands/create.py — 추가된 부분 (기존 코드 생략)

# ① generate_lecture() 시그니처에 eval_output_dir 추가
def generate_lecture(
    inputs: LectureInputs,
    ...
    eval_output_dir: Optional[str] = None,   # ← 추가
) -> Lecture:

    # ② eval 모니터 초기화 (opt-in)
    _eval_monitor = None
    if eval_output_dir:
        try:
            from lecture_forge.eval import (
                build_lecture_monitor,
                ContentWriterAdapter,
                CurriculumDesignerAdapter,
                ContentAnalyzerAdapter,
                QualityEvaluatorAdapter,
            )
            _eval_monitor = build_lecture_monitor(eval_output_dir)
        except ImportError:
            console.print("[yellow]⚠️  agent-evaluator 미설치 — eval 계측 건너뜀[/yellow]")

    # ③ 에이전트 생성 후 어댑터로 교체
    analyzer = ContentAnalyzerAgent(...)
    if _eval_monitor:
        analyzer = ContentAnalyzerAdapter(analyzer, _eval_monitor)

    designer = CurriculumDesignerAgent(...)
    if _eval_monitor:
        designer = CurriculumDesignerAdapter(designer, _eval_monitor)

    writer = ContentWriterAgent(vector_store=vs)
    if _eval_monitor:
        writer = ContentWriterAdapter(
            writer, _eval_monitor,
            curriculum.learning_objectives,   # Gate A 키워드 오버랩 기준
        )

    quality_evaluator = QualityEvaluator(...)
    if _eval_monitor:
        quality_evaluator = QualityEvaluatorAdapter(quality_evaluator, _eval_monitor)

    # ── 기존 파이프라인 로직 (수정 없음) ──────────────────────────────
    analysis = analyzer.analyze(collection_result, image_result, inputs.topic)
    curriculum = designer.design(analysis, inputs.topic, inputs.duration, inputs.audience_level)
    for section in curriculum.sections:
        content = writer.write_section(section, curriculum, available_images)
        ...
    quality_result = quality_evaluator.evaluate(lecture, threshold=80)
    ...
    # ─────────────────────────────────────────────────────────────────

    # ④ 최종 저장 — try/finally 패턴 (이미 만든 monitor 재사용)
    if _eval_monitor:
        topic_slug = inputs.topic[:30].replace(" ", "_")
        _eval_monitor.save_to_file(f"lecture_eval_{topic_slug}")

    return lecture


# ⑤ create 커맨드에 --eval 옵션 추가
@click.command()
@click.option("--topic",         required=True)
@click.option("--duration",      default=60, type=int)
@click.option("--audience-level",default="intermediate")
@click.option("--eval",          "eval_output_dir", default=None,
              help="agent-evaluator 결과 저장 디렉토리 (미지정 시 계측 비활성화)")
def create(topic, duration, audience_level, eval_output_dir):
    inputs = LectureInputs(topic=topic, duration=duration, audience_level=audience_level)
    generate_lecture(inputs, eval_output_dir=eval_output_dir)
```

> **💡 `evaluation_session` vs `try/finally`**
>
> `evaluation_session`은 내부에서 `PerformanceMonitor`를 새로 만들어 반환하는 컨텍스트 매니저다. `with` 블록 종료 시 `save_to_file()`이 자동 호출된다.
>
> `build_lecture_monitor()`처럼 **이미 만든 모니터를 재사용**하는 경우에는 `try/finally`를 사용한다. `evaluation_session(monitor=monitor)` 형태로 기존 모니터를 주입하는 방식은 지원되지 않는다.

### 실행

```bash
# eval 계측 없이 (기존과 동일)
lf create --topic "FastAPI 기초" --duration 60

# eval 계측 활성화
lf create --topic "FastAPI 기초" --duration 60 --eval eval_results/

# 결과 확인
agent-eval dashboard --results eval_results/
```

어댑터를 씌운 후에도 파이프라인 로직은 한 글자도 바뀌지 않는다. `analyzer.analyze()`, `designer.design()`, `writer.write_section()`, `quality_evaluator.evaluate()` 호출부는 기존과 완전히 동일하다. 어댑터가 중간에서 투명하게 계측만 한다.

---

## 25.6 Gate 리포트 실제 출력

이 모든 것을 연결한 후 `lf create --topic "FastAPI 기초" --duration 60`을 실행하면 다음 리포트가 생성된다.

```
════════════════════════════════════════════════════════════════
  HARNESS GATE REPORT — FastAPI 기초 (60분)
  실행: 2026-04-24 14:23  |  섹션: 5개  |  총 시간: 7분 12초
════════════════════════════════════════════════════════════════

  ✅ Gate A  Goal Achievement              0.875  PASS
             ├─ 학습목표 키워드: 7/8 충족
             ├─ 섹션 완성: 5/5 (100%)
             └─ 컨텍스트 유지: 0.81 (임계값 0.80)

  ✅ Gate B  Behavioral Integrity          1.000  PASS
             ├─ 확장 루프 최대 2회 (임계값 3회)
             ├─ 금지 도구 파라미터: 없음
             └─ 상태 불변성: curriculum.topic, audience_level 유지

  ✅ Gate C  Reliability                   0.933  PASS
             ├─ API 오류 3건 → 3건 복구 (100%)
             ├─ Pexels 이미지 서버 장애 → 텍스트만으로 완성
             └─ 재시도 품질 분산: ±8.2점 (임계값 15점)

  ✅ Gate D  Performance Contract          0.820  PASS
             ├─ P95: 98초 ✅ (SLA 120초)
             ├─ 비용: $0.038 ⚠ (목표 $0.035 소폭 초과)
             └─ RAG 쿼리: 평균 4.2회/섹션 (임계값 5회)

  ✅ Gate E  Security Boundary             1.000  PASS
             ├─ 위협 청크 2건 차단 (PDF 내 인젝션 패턴)
             ├─ 개인정보 패턴: 없음
             └─ 위협 대응: sanitize → skip_chunk (1초 이내)

  ⚠  Gate F  Multi-Agent Coordination      0.720  WARN
             ├─ PropagationConfig: audience_level 왜곡 감지 ⚠
             │    curriculum_designer → content_writer 구간
             │    expected: "intermediate", received: None
             └─ AgentRole: 역할 위반 없음

  ✅ Gate G  Observability                 0.833  PASS
             ├─ content_writing: 65% (4분 41초) ← 병목
             ├─ rag_indexing: 12% (52초)
             ├─ curriculum_design: 11% (47초)
             └─ html_assembly: 7% (30초)

────────────────────────────────────────────────────────────────
  종합 점수 (가중: A×2.0 E×3.0 F×1.5 D×1.2)
  → 0.861  PASS  (기준 0.75)

  저장: lecture_eval_results/lecture_FastAPI기초.json/.html
════════════════════════════════════════════════════════════════
```

7개 Gate 중 6개가 PASS고, Gate F 하나가 WARN이다. 종합 가중 점수 0.861로 PASS다.

하지만 Gate F의 WARN은 중요하다. `audience_level`이 CurriculumDesigner에서 ContentWriter로 전달되는 과정에서 `None`이 되고 있다는 것을 리포트가 알려주고 있다.

---

## 25.7 Gate가 찾아낸 버그: 실제 수정 사례

Gate F가 발견한 `audience_level` 전파 실패를 추적한다.

### 버그 탐색

PropagationConfig의 리포트에 "curriculum_designer → content_writer 구간, expected: intermediate, received: None"이라는 정보가 있다. ContentWriter의 프롬프트 구성 코드를 확인한다.

```python
# agents/content_writer/agent.py — 버그 위치 (line 87)

def _build_prompt(self, section: Section, curriculum: Curriculum,
                  contexts: list[str]) -> str:
    context_text = "\n\n".join(contexts[:5])
    return f"""당신은 강의 콘텐츠 작성 전문가입니다.

주제: {section.title}
학습 주제: {', '.join(section.topics)}
학습 목표: {chr(10).join(section.learning_outcomes)}

참고 자료:
{context_text}

위 내용을 바탕으로 {section.estimated_time}분 분량의 강의 섹션을 작성해 주세요."""
# ← curriculum.audience_level이 프롬프트에 없다!
```

`audience_level`이 프롬프트에서 빠져 있었다. CurriculumDesigner가 `audience_level=intermediate`로 커리큘럼을 설계했지만, ContentWriter의 프롬프트에는 이 정보가 전달되지 않고 있었다. LLM은 수강생 수준을 모른 채 콘텐츠를 생성하고 있었다.

### 수정

```python
# agents/content_writer/agent.py — 수정 후

def _build_prompt(self, section: Section, curriculum: Curriculum,
                  contexts: list[str]) -> str:
    context_text = "\n\n".join(contexts[:5])
    return f"""당신은 강의 콘텐츠 작성 전문가입니다.

주제: {section.title}
수강생 수준: {curriculum.audience_level}   # ← 이 한 줄 추가
학습 주제: {', '.join(section.topics)}
학습 목표: {chr(10).join(section.learning_outcomes)}

참고 자료:
{context_text}

위 내용을 바탕으로 {curriculum.audience_level} 수준의 수강생을 위한
{section.estimated_time}분 분량의 강의 섹션을 작성해 주세요."""
```

### 수정 후 결과

```
  ✅ Gate F  Multi-Agent Coordination      0.950  PASS  ← 0.720 → 0.950
             ├─ PropagationConfig: 모든 필드 전파 확인
             └─ audience_level: intermediate 정상 전달
```

이것이 2단계 통합의 핵심 가치다. "어딘가 이상한 것 같은데"가 아니라, "Gate F PropagationConfig: curriculum_designer → content_writer 구간, audience_level None"이라는 정확한 진단이 나왔다. 코드 한 줄을 수정하고, Gate F가 0.720에서 0.950으로 올라갔다.

---

## 25.8 일반화: 어떤 프로젝트에도 이 방법을 쓸 수 있다

### 어댑터 작성의 실용적 가이드

어댑터 작성에서 가장 많이 막히는 경우는 두 가지다.

**기존 추적기가 task_id를 지원하지 않는 경우**: 추적기의 전체 집계 데이터를 가져와서 이전 섹션의 누적값을 빼면 된다.

```python
# before 값을 기억해뒀다가 차분을 구한다
before = token_tracker.get_total_summary()
content = writer.generate(section)   # 생성
after = token_tracker.get_total_summary()

tokens_for_this_section = {
    "input":  after["prompt_tokens"] - before["prompt_tokens"],
    "output": after["completion_tokens"] - before["completion_tokens"],
    "total":  after["total_tokens"] - before["total_tokens"],
}
```

**기존 품질 점수의 단위가 다른 경우**: 어떤 단위든 0–100으로 정규화해서 `accuracy` 필드에 넣는다. 원래 값은 `metadata`에 보존한다.

```python
# 5점 만점 → 100점 척도로 정규화
accuracy_normalized = (existing_5pt_score / 5.0) * 100

result = create_taskresult(
    accuracy=accuracy_normalized,   # 0–100 정규화
    metadata={
        "original_score_5pt": existing_5pt_score,  # 원래 값 보존
    },
)
```

### Gate 리포트 WARN/FAIL 처리 우선순위

처음 Gate 리포트를 받으면 여러 WARN이 나오는 것이 일반적이다. 모든 WARN을 즉시 수정하려 하지 말고, 다음 순서로 처리한다.

첫째, Gate E FAIL은 즉시 수정한다. 보안 문제는 기다릴 수 없다.

둘째, Gate A FAIL은 1주일 내 수정한다. 제품의 핵심 기능 실패다.

셋째, Gate B WARN 중 루프 관련은 2주 내 수정한다. 비용 폭발로 이어질 수 있다.

넷째, 나머지 Gate WARN은 다음 스프린트에 포함한다.

처음 달에는 모든 Gate를 PASS로 만들려 하지 않는다. Gate 리포트가 지속적으로 나오는 환경을 만드는 것이 먼저다.

---

> **이 챕터에서 배운 것**
>
> 2단계 통합의 핵심은 세 가지다. 단일 `build_lecture_monitor()`로 공유 모니터를 만든다. 4개 에이전트를 각각 위임 어댑터로 감싼다. `enable_security_metrics=True` 한 줄로 Gate E 보안 스캔을 활성화한다.
>
> 새 파일: `eval/monitor.py` + `eval/adapters.py`. 기존 파일 수정: `create.py`에 `--eval` 옵션과 어댑터 적용 코드 ~56줄 추가. 기존 파이프라인 로직: 0줄 변경.
>
> Gate F WARN이 `audience_level` 전파 버그를 찾아냈다. 코드 한 줄을 수정하고 Gate F가 0.720에서 0.950으로 올라갔다. "어딘가 이상한 것 같은데"에서 "정확히 어느 에이전트에서 어떤 필드가 왜곡됐는가"로 진단의 수준이 달라진 것이다.
>
> **다음 챕터**에서는 이 모든 것을 CI/CD에 연결하고, 주간 자동화 루틴을 구축해 파트 VI를 완성한다.

```
# 출처: Evaluator_Examples/ch25_harness_full.py
```
