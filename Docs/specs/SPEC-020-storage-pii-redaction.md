# SPEC-020: 저장 계층 PII Redaction (옵트인)

**Phase:** P6 (SDK 전반 성숙도 — 엔터프라이즈 신뢰성) · **상태:** Implemented (2026-07-04) · **의존성:** 없음 (기존 `gates/gate_e_security/evaluators.py::_PII_PATTERNS`를 재사용만 함)

> **구현 노트 (2026-07-04)**: `agent_evaluator/utils/pii_redaction.py` 신설(REQ-1~4) —
> `redact_pii_text()`/`redact_task_pii()`/`DEFAULT_REDACTION_CATEGORIES`(name/address
> 제외 8개 카테고리). `PerformanceMonitor.__init__`에 `enable_pii_redaction`/
> `pii_redaction_categories` 추가(REQ-5), `save_to_file()`의 SQLite·JSON 두 분기 모두
> 스냅숏 직후 조건부 redaction 적용(REQ-6~7, `monitor.py`의 두 `_tasks_snapshot` 지점).
> `tests/test_pii_redaction.py`(12건) — 순수 함수 단위 테스트, name/address 기본 제외
> 확인, JSON/SQLite 양쪽 백엔드에서 저장본은 redact되고 인메모리 `monitor.tasks`는
> 원문을 그대로 유지하는지(REQ-7 핵심 불변식) 검증, `enable_pii_redaction` 기본값
> `False`에서 무변화 회귀 확인. 전체 12건 1회 통과.

## Context

- Gate E는 `ComplianceConfig`로 응답 텍스트 안의 PII를 탐지해 컴플라이언스 점수를 매긴다(`_PII_PATTERNS`, `gates/gate_e_security/evaluators.py:15-29` — email/phone/ssn/credit_card/passport/ip_address/korean_phone/korean_rrn/name/address 10개 카테고리). 하지만 이 탐지는 **점수 계산용**일 뿐, 탐지 대상이 된 원문 자체를 저장 시점에 지우거나 마스킹하는 로직은 어디에도 없다 — 이 프로젝트가 PII를 채점하면서 정작 자기 저장소에는 그 PII를 평문 그대로 영구 보존한다는 모순이 있다.
- `TaskResult`(`core/trackers/base.py:24`, `@dataclass(frozen=True)`)의 `question`/`response`/`ground_truth`/`context`(`base.py:63-66`, 주석: "persisted to JSON for dashboard display") 4개 필드가 실제 PII 노출 표면이다. 이 필드들은 생성 시점 그대로 어떤 가공도 거치지 않고 저장된다.
- `task_result.extra`(Gate 판정 결과가 담기는 곳)는 이미 redaction-safe하다 — 직접 확인 결과, `eval_compliance()`(`gate_e_security/evaluators.py:203-333`)는 `pii_detected` 리스트에 카테고리 이름만(`"email"`, `"ssn"` 등, `:266`) 담고, `violations`도 태그 문자열(`f"pii:{category}"` 등, `:267`)만 담을 뿐 매칭된 원문 조각(`match.group()`)은 어디에도 저장하지 않는다. `OutputLeakageDetector.detect_leakage()`(`core/trackers/security.py:549-660`)도 불리언/개수/점수만 반환한다(`:621-657`). `InputSanitizationTracker`(`core/trackers/security.py:293-303`)는 `match.group(0)`을 길이 계산에만 쓰고 버린다(`:300`). 즉 **레닥션이 필요한 곳은 `TaskResult`의 원문 4개 필드뿐**이다.
- `PerformanceMonitor.save_to_file()`(`monitor.py:4766`)이 실제 디스크 쓰기 지점이다 — JSON 경로는 `_tasks_snapshot`(`:4812`)을 `asdict(task)`(`:4815`)로 직렬화하고, `storage_backend="sqlite"` 경로(`:4794`)는 별도로 스냅숏(`:4798`)을 떠서 `save_tasks_to_db()`(`storage/sqlite_backend.py:75`)에 넘기며, 그 안에서 `t.to_dict()`(`:88`, 내부적으로 `dataclasses.asdict` 호출, `base.py:207`)로 직렬화한다. 두 경로 모두 `TaskResult`를 가공 없이 그대로 직렬화한다.
- `record_task()`(`monitor.py:1600`)는 이미 frozen dataclass를 안전하게 갱신하는 패턴을 4곳에서 쓰고 있다 — `dataclasses.replace(task_result, ...)`(`:1681,1701,1730,1951`). 보안 트래커 enrichment 블록(`:1951`)은 `add_task()`(`:1736`)가 이미 실행된 뒤 `_tcr_list[-1] = task_result`(`:1955`)로 이미 저장된 항목을 수동으로 교체하는 패턴까지 확립돼 있다 — 이번 스펙이 저장 시점 이후(즉 `record_task()`가 아니라 `save_to_file()` 시점)에만 개입하면 이 패턴을 그대로 따를 필요조차 없다(아래 Goals 참조).
- `PerformanceMonitor.__init__`(`monitor.py:225-288`)의 옵트인 플래그 컨벤션은 `enable_<feature>: bool = False`이고, 저장소 형태를 바꾸는 파라미터는 `storage_backend: Literal["json","sqlite"] = "json"`(`:287`, 주석: "기본값 'json'은 기존 save_to_file() 동작과 100% 동일") 스타일이다 — 이번 스펙의 새 파라미터도 동일한 "기본값 불변" 원칙을 따른다.

## Goals

- `PerformanceMonitor(enable_pii_redaction=True)`로 옵트인하면, `save_to_file()`이 실제로 디스크(JSON 파일 또는 SQLite DB)에 쓰기 **직전**에만 `question`/`response`/`ground_truth`/`context` 필드에서 PII 패턴을 찾아 `[REDACTED:<category>]`로 치환한다.
- Gate E의 PII 탐지(스코어링)는 원문이 있어야 의미가 있으므로, redaction은 **인메모리 `self.tasks`/`self.tcr_tracker._tasks`에는 절대 적용하지 않는다** — `record_task()`/`generate_report()`/대시보드 실시간 뷰는 기존과 동일하게 원문을 본다. redaction은 오직 `save_to_file()`이 만드는 저장용 스냅숏 사본에만 적용된다.
- 기존 `_PII_PATTERNS`(Gate E)를 그대로 재사용한다 — 새 탐지 로직을 만들지 않는다.

## Non-Goals

- `task_result.extra` redaction — Context에서 확인했듯 이미 원문을 담지 않으므로 대상이 아니다.
- `record_task()`/`generate_report()`/대시보드 실시간 API의 응답 redaction — 이 스펙은 "저장(at-rest)" 경로만 다룬다. 프로세스 메모리 내부에서 원문에 접근 가능한 것 자체는 위협 모델 밖(신뢰된 프로세스 경계 내부).
- 완전한 PII 삭제 보장 — `_PII_PATTERNS`는 정규식 기반 휴리스틱이며(Gate E 스코어링과 동일한 한계), 모든 PII를 잡아낸다고 보장하지 않는다. "이미 있는 탐지 능력만큼만 가려준다"는 범위.
- `name`/`address` 카테고리의 정규식 정확도 개선 — 기존 Gate E 패턴을 그대로 쓴다(아래 Risks 참조, 대신 기본 카테고리 집합에서 제외).
- SQLite/JSON 파일에 이미 저장된 과거 데이터의 소급 redaction(마이그레이션 도구) — 이번 스펙은 신규 저장분에만 적용한다.

## Requirements

- **REQ-1**: 신규 모듈 `agent_evaluator/utils/pii_redaction.py`. `gates/gate_e_security/evaluators.py::_PII_PATTERNS`를 import해 재사용한다(값 복제 금지 — 카테고리 정규식이 한 곳에서만 유지되도록).
- **REQ-2**: `DEFAULT_REDACTION_CATEGORIES: List[str]` — `_PII_PATTERNS`의 키 중 `"name"`/`"address"`를 제외한 나머지(email/phone/ssn/credit_card/passport/ip_address/korean_phone/korean_rrn) 8개. `"name"`(아무 한글 3-4글자 연속 매칭)과 `"address"`는 매칭 범위가 넓어 일반 텍스트를 과도하게 가릴 수 있으므로 기본값에서 제외하고, 필요한 사용자만 명시적으로 포함하도록 한다(Risks 참조).
- **REQ-3**: `redact_pii_text(text: Optional[str], categories: List[str]) -> Optional[str]` — `text`가 `None`/빈 문자열이면 그대로 반환. 아니면 `categories`에 해당하는 `_PII_PATTERNS`의 각 정규식을 `re.sub(pattern, f"[REDACTED:{category}]", text)`로 순차 치환해 반환.
- **REQ-4**: `redact_task_pii(task: TaskResult, categories: Optional[List[str]] = None) -> TaskResult` — `categories=None`이면 `DEFAULT_REDACTION_CATEGORIES` 사용. `question`/`response`/`ground_truth`/`context` 4개 필드에 `redact_pii_text()`를 적용한 **새** `TaskResult`를 `dataclasses.replace()`로 만들어 반환한다(frozen dataclass이므로 원본은 변경되지 않는다 — 호출자가 반환값만 저장용으로 써야 함).
- **REQ-5**: `PerformanceMonitor.__init__`에 `enable_pii_redaction: bool = False`, `pii_redaction_categories: Optional[List[str]] = None` 2개 파라미터 추가. 각각 `self.enable_pii_redaction`, `self.pii_redaction_categories`로 저장한다(기존 `enable_hallucination_detection`/`enable_security_metrics` 저장 패턴과 동일, `monitor.py:419-420` 참조).
- **REQ-6**: `save_to_file()`의 두 스냅숏 지점(SQLite 분기 `:4798`, JSON 분기 `:4812`) 각각에서, `self.enable_pii_redaction`이 `True`면 스냅숏 리스트를 `[redact_task_pii(t, self.pii_redaction_categories) for t in _tasks_snapshot]`로 치환한 뒤 이어지는 직렬화(`asdict`/`save_tasks_to_db`)를 그대로 수행한다. `False`(기본값)면 기존과 100% 동일한 코드 경로.
- **REQ-7**: redaction된 스냅숏은 `save_to_file()` 호출 내부의 지역 변수로만 존재해야 한다 — `self.tasks`/`self.tcr_tracker._tasks` 자체를 교체하거나 변경하지 않는다(Goals의 "인메모리는 원문 유지" 보장).

## Interface

```python
# 변경 전
monitor = PerformanceMonitor(output_dir="results/")

# 변경 후 (하위호환 — enable_pii_redaction 기본값 False는 기존과 100% 동일)
monitor = PerformanceMonitor(
    output_dir="results/",
    enable_pii_redaction=True,
    pii_redaction_categories=["email", "ssn", "credit_card"],  # 생략 시 DEFAULT_REDACTION_CATEGORIES
)
monitor.record_task(task)          # Gate E는 원문으로 정상 채점됨 — 영향 없음
monitor.save_to_file("eval.json")  # 저장된 파일의 question/response/ground_truth/context만 마스킹됨
```

```python
# agent_evaluator/utils/pii_redaction.py
def redact_pii_text(text: Optional[str], categories: List[str]) -> Optional[str]: ...
def redact_task_pii(task: TaskResult, categories: Optional[List[str]] = None) -> TaskResult: ...
DEFAULT_REDACTION_CATEGORIES: List[str]
```

## Acceptance

- **REQ-3**: `redact_pii_text("contact me at a@b.com", ["email"])` → `"contact me at [REDACTED:email]"`. `redact_pii_text(None, [...])`/`redact_pii_text("", [...])` → 그대로 반환.
- **REQ-4**: `redact_task_pii(task)`가 반환한 객체는 `question`/`response`/`ground_truth`/`context`만 바뀌고 나머지 필드(특히 `task_id`/`extra`/`tool_calls`)는 원본과 동일한지 검증. 원본 `task` 객체 자체는 변경되지 않았는지(`is` 비교 아닌 필드값 비교) 검증.
- **REQ-6 (JSON 백엔드)**: `enable_pii_redaction=True`로 이메일이 포함된 질문을 기록 → `save_to_file()` → 저장된 JSON 파일을 열어 `tasks[0]["question"]`에 `[REDACTED:email]`이 있고 원본 이메일 문자열이 파일 어디에도 없는지 확인.
- **REQ-6 (SQLite 백엔드)**: 동일 시나리오를 `storage_backend="sqlite"`로 반복 — `load_tasks_from_db()`로 다시 읽었을 때도 redaction된 텍스트만 나오는지 확인.
- **REQ-7**: `enable_pii_redaction=True`로 기록 후 `monitor.generate_report()`/`monitor.tasks[0].question`으로 인메모리 값을 직접 확인 — 원본 이메일이 그대로 남아있는지(redaction이 저장 시점에만 적용됐는지) 검증.
- **회귀**: `enable_pii_redaction`을 지정하지 않은 기존 테스트 전체가 byte-diff 수준으로 그대로 통과하는지 확인(기본값 `False` 무변화 보장).
- **기본 카테고리 제외 확인**: `pii_redaction_categories`를 지정하지 않은 기본 상태에서, `"김철수"`(한글 3글자, `"name"` 카테고리에 해당) 같은 텍스트가 redaction되지 **않는지**(REQ-2의 기본 제외 확인) 검증.

## Compatibility

- 완전히 옵트인 — `enable_pii_redaction` 기본값 `False`는 기존 `save_to_file()` 동작과 100% 동일(코드 경로 자체가 조건부 분기 밖).
- 신규 모듈(`utils/pii_redaction.py`) 추가 외에 기존 파일 수정은 `monitor.py`의 `__init__`(파라미터 2개 추가)과 `save_to_file()`(스냅숏 후 조건부 치환 1줄씩 추가) 뿐 — 기존 시그니처는 전부 하위호환.

## Rollout

1. `agent_evaluator/utils/pii_redaction.py` 신설(REQ-1~4).
2. `PerformanceMonitor.__init__` 파라미터 추가(REQ-5).
3. `save_to_file()` 두 분기에 조건부 redaction 적용(REQ-6~7).
4. 단위 테스트(`redact_pii_text`/`redact_task_pii` 순수 함수) + 통합 테스트(JSON/SQLite 양쪽 백엔드로 실제 저장 후 파일 내용 확인 + 인메모리 원문 보존 확인) + 회귀(기본값 무변화).
5. 전체 스위트 통과 확인 후 상태를 Draft → Implemented로 갱신, `Docs/specs/README.md` 인덱스에 등록.

## Risks

- **`name`/`address` 카테고리의 과잉 매칭**: `"name"` 정규식(`[가-힣]{3,4}`)은 사실상 아무 한글 3-4글자 연속에 매칭되므로, 전체 카테고리를 기본으로 켜면 일반적인 한국어 응답 텍스트 상당 부분이 `[REDACTED:name]`으로 뒤덮여 저장 데이터가 사실상 못 쓰게 될 위험이 크다 — REQ-2에서 기본 제외로 완화했다. 사용자가 명시적으로 `pii_redaction_categories`에 `"name"`을 추가하면 이 위험을 감수하는 것으로 간주한다.
- **redaction이 Gate E 스코어링에 영향을 주지 않는다는 보장의 취약점**: `save_to_file()`을 여러 번 호출하는 사용 패턴(예: 중간 저장 후 계속 `record_task()` 진행)에서, redaction이 매번 새 스냅숏 사본에만 적용되고 원본 `self.tasks`를 절대 건드리지 않는다는 REQ-7 불변식이 깨지면 이후 채점이 조용히 오염된다 — Acceptance의 "인메모리 원문 보존 확인" 테스트가 이 불변식을 직접 검증한다.
- **정규식 기반 탐지의 근본 한계**: Gate E 스코어링과 동일하게, 이 redaction도 `_PII_PATTERNS`가 못 잡는 형태의 PII(예: 문맥 의존적 개인식별정보, 패턴에 없는 국가별 주민번호 형식)는 그대로 저장된다 — "탐지되면 가려진다"이지 "PII가 절대 없다"가 아니다. 규제 준수를 위한 유일한 보호장치로 쓰면 안 된다는 걸 문서에 명시한다.
