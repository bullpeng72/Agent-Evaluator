# SPEC-007: 감사/재현성 Lineage 캡처

**Phase:** P0 · **상태:** Implemented (2026-07-02) · **의존성:** 없음 (독립 착수 가능)

> **구현 노트**: `PerformanceMonitor.__init__`에서 `sdk_version`(`importlib.metadata`)·`git_commit`(`subprocess.run(["git","rev-parse","HEAD"])`, 실패 시 예외 없이 `None`)을 1회 캐싱하고, `generate_report()`에서 태스크 유무와 무관하게 `extra_metrics.lineage`에 병합한다. `judge_model_snapshot`은 `llm_judge.py`의 `_call_claude`/`_call_openai`가 실제 API 응답 객체(`msg.model`/`completion.model`)에서 추출해 `_parse_judge_response()` 반환 dict의 `model_snapshot` 키로 흘려보내고, `_build_lineage()`가 가장 최근 판정된 태스크의 값을 채택(없으면 `judge.model` 설정값 폴백)한다. 테스트: `tests/test_lineage_capture.py`(신규 11건).

## Context

- `agent_evaluator/core/trackers/base.py`의 `EvaluationReport` 필드(`period, total_tasks, accuracy_metrics, efficiency_metrics, quality_metrics, security_metrics, alerts, recommendations, timestamp, extra_metrics`)와 `monitor.py`의 `save_to_file` 경로(`:5483` 이하) 어디에도 `sdk_version`/`git_commit`/`prompt_version`/`agent_version` 저장 지점이 없다 (2026-07-02 세션에서 `core/`, `decorators.py` 전체 grep으로 재확인, 0건).
- `ReproducibilityConfig`(`decorators.py:334-374`)는 반복 실행 간 **응답 유사도**만 측정할 뿐, "이 점수가 어떤 코드/모델/프롬프트 조합에서 나왔는가"를 재구성할 lineage 정보는 별개다.
- LLM Judge 결과 딕셔너리에는 `"model"` 키(`llm_judge.py:682` 등 다수)로 모델 문자열은 기록되지만, provider가 반환하는 실제 스냅샷 ID(예: Anthropic 응답의 세부 모델 리비전)는 캡처되지 않는다.

## Goals

- 평가 결과 파일만으로 "어떤 SDK 버전·어떤 코드 커밋·어떤 프롬프트 버전에서 이 점수가 나왔는지" 감사·재현할 수 있는 최소한의 메타데이터를 자동 캡처한다.

## Non-Goals

- 완전한 실험 추적 시스템(MLflow류) 구축 — 이번 스펙은 저장 파일에 필드를 추가하는 수준.
- Judge provider의 모델 스냅샷 고정/검증(SPEC-006 이후 별도 스펙 후보).

## Requirements

- **REQ-1**: `save_to_file` 호출 시 `extra_metrics.lineage`에 아래 필드를 자동 포함한다.
  - `sdk_version`: `importlib.metadata.version("agent-evaluator")` (실패 시 `None`)
  - `git_commit`: 현재 작업 디렉토리 기준 `git rev-parse HEAD` 결과 (git 리포지토리가 아니거나 명령 실패 시 `None`, 예외 전파 금지)
  - `prompt_version`: 사용자가 `PerformanceMonitor` 또는 `@agent_eval`에 명시적으로 지정한 태그 문자열(선택, 기본값 `None`)
  - `agent_version`: 사용자가 명시적으로 지정한 태그 문자열(선택, 기본값 `None`)
- **REQ-2**: `git_commit` 조회 실패(비-git 환경, `git` 미설치 등)가 `save_to_file` 전체를 실패시키지 않아야 한다 — 반드시 예외를 잡아 `None`으로 대체.
- **REQ-3**: `git_commit` 조회는 매 `save_to_file` 호출마다 서브프로세스를 띄우지 않고, `PerformanceMonitor` 인스턴스 생성 시 1회만 조회해 캐싱한다(성능 고려).
- **REQ-4**: LLM Judge를 사용한 태스크의 경우, `lineage`에 `judge_model_snapshot` 필드를 추가한다 — provider 응답에 모델 리비전/스냅샷 식별자가 포함되어 있으면(예: 응답 헤더/바디의 실제 모델 문자열) 이를 그대로 기록하고, 없으면 설정값(`judge.model`)을 그대로 기록한다. 이는 provider가 별칭(`"gpt-4o"` 등)을 무중단으로 새 스냅샷으로 교체해도 SDK가 "어떤 시점에 어떤 모델로 평가됐는지"를 최소한 사후 대조할 수 있게 하기 위함이다(2026-07-02 세션의 LLM Judge 거버넌스 분석 근거, `llm_judge.py:682` 등에서 이미 `"model": model` 키가 결과 dict에 존재함을 재사용).

## Interface

```python
# 변경 전
monitor = PerformanceMonitor(output_dir="results/")

# 변경 후 (하위호환 — 신규 파라미터는 선택)
monitor = PerformanceMonitor(
    output_dir="results/",
    prompt_version="v3.2",   # 신규, 선택
    agent_version="agent-2026-07",  # 신규, 선택
)
```

저장되는 JSON:
```json
{
  "extra_metrics": {
    "harness_groups": { ... },
    "lineage": {
      "sdk_version": "0.9.5",
      "git_commit": "a1b2c3d...",
      "prompt_version": "v3.2",
      "agent_version": "agent-2026-07"
    }
  }
}
```

## Acceptance

- git 리포지토리 내부/외부 양쪽 환경에서 `save_to_file` 정상 동작 확인(외부에서는 `git_commit: None`).
- git 리포지토리 내부에서 저장된 `git_commit`이 실제 `git rev-parse HEAD` 결과와 일치.
- `prompt_version`/`agent_version` 미지정 시 `None`으로 저장되고 기존 테스트에 영향 없음(additive).
- `PerformanceMonitor` 인스턴스 생성 100회에 대해 git 서브프로세스가 100회가 아니라 1회만 호출되는지 검증(REQ-3).

## Compatibility

- `extra_metrics`에 `lineage` 키만 추가 — 완전 additive, 기존 스키마 소비자에 영향 없음.

## Rollout

1. `PerformanceMonitor.__init__`에 git commit 캐싱 로직 추가.
2. `save_to_file`에 `lineage` 필드 조립 로직 추가.
3. 대시보드(선택) — 결과 상세 뷰에 lineage 정보를 표시하는 UI 추가는 후속 과제로 분리 가능.

## Risks

- 서브프로세스로 `git rev-parse` 호출 시 샌드박스/권한 제한 환경에서 실패할 수 있음 → REQ-2로 이미 완화(예외를 삼키고 `None`).
