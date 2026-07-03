# SPEC-023: LLM Judge/실행 모델 이종화 경고 + Lineage 기록

**Phase:** P6 (SDK 전반 성숙도 — 엔터프라이즈 신뢰성) · **상태:** Implemented (2026-07-04) · **의존성:** SPEC-007(완료, `_build_lineage()`에 필드 1개 추가)

> **구현 노트 (2026-07-04)**: `PerformanceMonitor.__init__`의 LLM Judge 생성 블록 직후
> `self._judge_same_as_execution_model`을 한 번 계산해(REQ-4) `UserWarning`(REQ-1~2)과
> `_build_lineage()`의 `judge_same_as_execution_model` 필드(REQ-3)가 동일한 값을
> 공유하도록 구현. `tests/test_judge_execution_model_heterogeneity.py`(8건)로 검증 —
> 동일 모델 경고 발생, 다른 모델/빈 model_name/judge 비활성/judge 생성 실패 시 경고
> 미발생, lineage 필드 True/False 양쪽. 전체 스위트 **3,226 passed, 1 skipped, 회귀
> 0건**(기존 3,218 + 신규 8).

## Context

- `LLMJudge`가 에이전트 자신의 출력을 채점할 때, judge 모델과 실행(응답 생성) 모델이 **동일**하면 독립적인 검증이 아니라 자기평가(self-evaluation) 편향이 생긴다 — 특히 로컬 소형 모델(예: Ollama qwen 계열)에서 이 문제가 두드러진다. 지금 SDK엔 이걸 감지·경고하는 코드가 전혀 없다.
- `PerformanceMonitor.__init__`에서 `self.model_name`은 딱 한 번, 생성자 진입 시점에 결정된다(`monitor.py:403-421`) — 명시 인자가 없으면 `.env`의 실제(placeholder 아닌) API 키 유무에 따라 `anthropic_model`/`openai_model`로 자동 채워지고, 둘 다 없으면 `""`로 남는다(직접 확인). 이후 이 값을 바꾸는 setter/재할당은 파일 전체에 없다(`grep -n "model_name\b"` 전수 확인) — 즉 생성자 완료 시점 이후로는 불변.
- `self.llm_judge`는 `enable_llm_judge=True`일 때 `monitor.py:586-608`에서 `LLMJudge(model=judge_model, ...)`로 즉시 생성된다. **`judge_model=None`이면 `PerformanceMonitor`가 직접 해석하지 않고 그대로 `LLMJudge.__init__`에 넘긴다** — 실제 해석은 `LLMJudge.__init__`(`llm_judge.py:322`)의 `self.model = model if model is not None else _resolve_default_model()`가 담당하며, `_resolve_default_model()`(`llm_judge.py:190-226`)은 API 키 유무에 따라 `anthropic_model`/`openai_model`을 고르고, 그마저 없으면 하드코딩된 리터럴 `"gpt-5-nano"`로 폴백한다 — **`LLMJudge.model`은 어떤 환경에서도 항상 구체적인 비어있지 않은 문자열**이다(직접 확인, `None`/`""`로 남는 경로 없음).
- `LLMJudge` 생성이 실패하면(`ImportError`/기타 예외) `self.llm_judge`는 `None`으로 남고 `self.enable_llm_judge`도 `False`로 강제 리셋된다(`monitor.py:604,608`) — 따라서 비교 로직은 `self.llm_judge is not None`을 반드시 가드해야 한다.
- **비대칭 주의점**: `self.model_name` 해석(`monitor.py:411-413`)은 `"your-"`로 시작하는 placeholder API 키를 명시적으로 걸러내지만, `LLMJudge._resolve_default_model()`이 쓰는 `Settings.has_anthropic()`/`has_openai()`(`config.py:208-212`)는 `bool(api_key)`만 확인해 placeholder 키도 "있음"으로 친다 — 반쯤 설정된 환경(placeholder 키만 있는 경우)에서 `self.model_name=""`이지만 `self.llm_judge.model`은 실제 모델 문자열일 수 있다. 이 경우 문자열이 다르므로 경고가 발동하지 않는데(`""` != `"claude-..."`), 이건 올바른 동작이다 — "실행 모델이 없다"는 별개 문제이지 "judge와 실행 모델이 같다"는 문제가 아니기 때문이다.
- 기존 Config `__post_init__` 경고 스타일(`gates/gate_b_behavioral/configs.py`의 `LoopDetectionConfig`/`ToolParameterSafetyConfig` 등, 직접 확인)은 `warnings.warn(f"<ClassName>: <값> <위험>. <조치>.", UserWarning, stacklevel=2)` 형식을 일관되게 쓴다 — `monitor.py`도 이미 LLM Judge 초기화 실패 시 같은 자리(`:603,607`)에서 `warnings.warn(..., RuntimeWarning, stacklevel=2)`를 쓰고 있어, 같은 위치에 `UserWarning`을 추가하는 게 기존 관례와 자연스럽게 맞아떨어진다.
- SPEC-007이 이미 `_build_lineage()`(`monitor.py:2931-2954`)에서 `judge_model_snapshot`을 감사 목적으로 `extra_metrics.lineage`에 기록해 두고 있다 — judge와 실행 모델이 같았는지 여부도 "일회성 경고"로만 끝내지 않고 이 기존 lineage 딕셔너리에 필드 하나로 같이 남기면, 저장된 리포트만 보고도 사후에(경고 로그를 못 봤어도) "이 실행은 judge가 독립적이었는가"를 확인할 수 있다.

## Goals

- `enable_llm_judge=True`이고 실행 모델(`model_name`)과 judge 모델이 완전히 동일한 문자열이면, `PerformanceMonitor.__init__` 시점에 `UserWarning`으로 즉시 경고한다.
- 같은 판정을 `extra_metrics.lineage`에도 `judge_same_as_execution_model: bool` 필드로 남겨, 저장된 리포트만으로도 사후 감사가 가능하게 한다(SPEC-007 lineage의 자연스러운 확장).
- 두 identifier 모두 기존에 이미 해석되는 값을 그대로 재사용한다 — 새 모델 비교 로직(예: "같은 계열인지" 퍼지 매칭)을 만들지 않는다.

## Non-Goals

- 모델 패밀리 수준의 정교한 유사도 판정(예: "gpt-4"와 "gpt-4-turbo"를 "사실상 같은 계열"로 간주) — 정확한 문자열 일치만 검사한다. 오탐/누락 여지가 있음을 Risks에 명시.
- 이 경고를 개별적으로 끄는 새 생성자 파라미터 추가 — 표준 Python `warnings.filterwarnings()`로 이미 억제 가능하므로 새 옵션 표면을 늘리지 않는다.
- `judge_model`/`model_name` 해석 로직 자체(placeholder 키 필터링 등)의 변경 — 기존 로직을 그대로 소비만 한다.
- 실행 시점에 강제로 judge 호출을 막는 hard-block — 이건 "경고 + 감사 기록"이지 "차단"이 아니다(사용자가 의도적으로 같은 모델로 자기 일관성을 테스트하고 싶을 수도 있음).

## Requirements

- **REQ-1**: `PerformanceMonitor.__init__`의 LLM Judge 생성 블록(`monitor.py:586-608`) 직후, 다음 조건이 전부 참이면 `UserWarning`을 발행한다: `self.model_name`이 truthy(빈 문자열 아님) AND `self.llm_judge is not None` AND `self.model_name == self.llm_judge.model`(대소문자 구분 정확 일치).
- **REQ-2**: 경고 메시지는 기존 Config 경고 스타일을 따른다 — 클래스명, 실제 값, 위험 설명, 권고 조치를 포함: `"PerformanceMonitor: judge_model({self.llm_judge.model!r})이 실행 model_name과 동일합니다. 같은 모델이 자신의 출력을 채점하면 독립적인 검증이 아니라 자기평가(self-evaluation) 편향이 생길 수 있습니다 — 특히 로컬 소형 모델에서 두드러집니다. 가능하면 judge_model에 다른 모델을 지정하세요."`
- **REQ-3**: `_build_lineage()`(`monitor.py:2931-2954`)가 반환하는 딕셔너리에 `"judge_same_as_execution_model": bool` 필드를 추가한다 — `self.llm_judge is None`이면 판정 자체가 무의미하므로 `False`(judge 없음 = "같지 않음"으로 규약).
- **REQ-4**: REQ-1의 경고 조건과 REQ-3의 lineage 필드 판정 조건은 완전히 동일한 불리언 표현식을 공유해야 한다(중복 로직 방지 — 헬퍼 메서드 또는 인스턴스 속성으로 한 번만 계산).

## Interface

```python
# 변경 전 — 아무 경고 없이 조용히 자기평가
monitor = PerformanceMonitor(
    model_name="qwen3-coder:latest",
    enable_llm_judge=True, judge_model="qwen3-coder:latest",
)

# 변경 후 — 생성 시점에 UserWarning 발행
monitor = PerformanceMonitor(
    model_name="qwen3-coder:latest",
    enable_llm_judge=True, judge_model="qwen3-coder:latest",
)
# UserWarning: PerformanceMonitor: judge_model('qwen3-coder:latest')이 실행 model_name과
# 동일합니다. ...

report = monitor.generate_report()
report.to_dict()["extra_metrics"]["lineage"]["judge_same_as_execution_model"]  # True
```

## Acceptance

- **REQ-1/2**: `model_name`과 `judge_model`을 동일한 문자열로 준 `PerformanceMonitor` 생성 시 `pytest.warns(UserWarning, match="judge_model")`로 경고 발생 확인.
- **다른 모델이면 경고 없음**: `model_name="claude-sonnet-5"`, `judge_model="claude-haiku-4-5-20251001"`(또는 judge_model 생략, 자동 해석된 값이 다른 경우) → 경고 없음.
- **`model_name` 미설정(빈 문자열)이면 경고 없음**: `model_name` 인자를 생략(placeholder API 키만 있는 등)해 `self.model_name==""`인 상태에서 `enable_llm_judge=True` → 경고 없음(REQ-1의 truthy 가드 확인).
- **judge 생성 실패 시 경고 없음**: `LLMJudge` 생성자가 예외를 던지도록 몽키패치 → `self.llm_judge is None`이 되어 REQ-1 경고도, REQ-3 lineage 필드도 안전하게 `False`/미발동으로 처리되는지 확인.
- **REQ-3**: `judge_model`이 `model_name`과 같은 모니터로 태스크를 기록하고 `generate_report().to_dict()["extra_metrics"]["lineage"]["judge_same_as_execution_model"]`가 `True`인지, 다른 경우 `False`인지 확인.
- **회귀**: `enable_llm_judge=False`(기본값)인 기존 테스트 전체가 무변화로 통과하는지 확인(경고 코드 경로 자체가 `enable_llm_judge=True`일 때만 도달).

## Compatibility

- 완전히 옵트인 경고/필드 추가 — `enable_llm_judge=False`(기본값)이거나 두 모델이 다르면 어떤 동작도 바뀌지 않는다.
- `extra_metrics.lineage`에 필드 1개가 추가되는 것은 SPEC-007이 이미 확립한 "always present, additive" 계약과 일치한다 — 기존 lineage 소비 코드가 알 수 없는 키를 무시하는 관용적 JSON 소비 패턴이라면 영향 없음.

## Rollout

1. `PerformanceMonitor`에 판정 결과를 한 번만 계산해 재사용하는 private 헬퍼(또는 인스턴스 속성) 추가(REQ-4).
2. LLM Judge 생성 블록 직후 경고 발행(REQ-1~2).
3. `_build_lineage()`에 필드 추가(REQ-3).
4. 단위 테스트(경고 발생/미발생 각 시나리오, lineage 필드 값) + 회귀(기존 LLM Judge 테스트 스위트 무변화).
5. 전체 스위트 통과 확인 후 상태를 Draft → Implemented로 갱신, `Docs/specs/README.md` 인덱스 등록.

## Risks

- **정확한 문자열 일치만 검사**: `"claude-sonnet-5"`와 `"claude-sonnet-5-20260315"`처럼 사실상 같은 모델의 다른 별칭/스냅샷 표기는 서로 다른 문자열로 취급돼 경고가 안 뜬다(false negative) — 모델 패밀리 퍼지 매칭은 Non-Goals로 명시적으로 제외했으므로 이 한계는 의도된 것이다.
- **`judge_model`을 명시하지 않고 자동 해석에 의존하는 흔한 구성에서, 실행 모델도 같은 자동 해석 규칙(Anthropic 우선)을 타면 우연히 같은 문자열이 될 수 있음**: 이건 실제로 감지해야 할 정확한 케이스이므로 리스크라기보다 이 스펙의 존재 이유에 가깝다 — 다만 사용자가 "당연히 같겠거니" 하고 지나치던 경고가 갑자기 뜨기 시작하면 놀랄 수 있다(회귀 아님, 의도된 신규 신호).
- **경고가 `stacklevel=2`로 발행되므로, `PerformanceMonitor(...)`를 감싸는 팩토리 함수(`QuickEval.for_llm_judge()` 등)를 통해 생성하면 경고의 지목 위치가 사용자 코드가 아니라 팩토리 내부를 가리킬 수 있음** — 기존 LLM Judge 초기화 실패 경고(`monitor.py:603,607`)도 동일한 한계를 이미 갖고 있으므로 새로운 문제는 아니다.
