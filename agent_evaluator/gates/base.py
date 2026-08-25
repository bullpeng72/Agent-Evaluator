"""
agent_evaluator.gates.base
============================
전 Gate(A-G)가 공유하는 최소 인프라 — 표본 가드, 상태 판정, 그룹 딕셔너리 조립 헬퍼.

SPEC-000 Commit 0: monitor.py의 모듈 레벨 상수/함수(_DEFAULT_MIN_SAMPLES, _min_sample_warning)와
_compute_harness_groups 내부 nested closure(_status, _g)를 순수 함수로 그대로 승격했다.
동작 변경 없음 — 이관 자체가 목적인 인프라 전용 커밋.
"""
from __future__ import annotations

from typing import Any

# SPEC-002: 전 Gate 공통 최소 표본 가드 기본값 — Config에 자체 min_samples 필드가 없는
# 지표(A/B/C-비SLA/E/F/G)에 적용된다. Gate D의 TTFT/Cost는 기존 Config 필드(기본 5)를 그대로 쓴다.
_DEFAULT_MIN_SAMPLES: int = 3


def _min_sample_warning(metric_name: str, count: int, min_samples: int, unit: str = "samples") -> str | None:
    """count가 1개 이상이지만 min_samples 미만이면 표준 포맷 경고 문자열을 반환한다.

    count == 0(해당 지표가 아예 측정되지 않음)은 경고 대상이 아니다 — "데이터 없음"은
    이미 details의 avg_*=None / 키 부재로 표현되는 기존 컨벤션과 겹치므로, 여기서 또
    경고를 내면 "측정 안 함"과 "표본 부족"이 혼동된다.

    Args:
        unit: 카운트 단위 (SPEC-012) — task 기반 지표는 기본값 "samples"를 그대로 쓰고,
            이벤트 기반 지표(Gate F coordination/tool_selection, Gate G tool_coverage)는
            "interactions"/"evaluations"/"calls"처럼 실제 단위를 명시해 task 표본과
            혼동되지 않게 한다.
    """
    if 0 < count < min_samples:
        return f"{metric_name}: {count} {unit} < min_samples={min_samples}"
    return None


def _status(score: float | None, warn: float = 0.7, fail: float = 0.5) -> str:
    """Gate 점수 → pass/warn/fail/n-a 판정."""
    if score is None:
        return "n/a"
    if score >= warn:
        return "pass"
    if score >= fail:
        return "warn"
    return "fail"


def _measured(count: int, value: float | None) -> float | None:
    """"측정 상태" 3분류 계약 — Gate 점수 컴포넌트는 항상 다음 셋 중 하나여야 한다:
    ① 아예 설정 안 함(해당 Config·enable 플래그 자체가 꺼짐) ② 설정은 했지만 실제
    데이터가 0건(측정 시도는 됐으나 근거 없음) ③ 측정됨(count>0, 실제 값 존재).
    ①과 ②는 둘 다 이 함수에서 ``None``으로 합쳐진다 — Gate 점수 리스트에 포함되지
    않는다는 점에서 두 경우를 구분할 필요가 없기 때문이다(구분이 필요하면 별도
    ``enabled`` 플래그를 호출부에서 따로 확인).

    Gate C의 hallucination 처리("감지 자체가 없으면 None 유지")가 이 계약을 이미
    올바르게 지키던 참조 구현이었고, Gate E는 ``enable_security_metrics=True``인데
    실제 트래커 데이터가 0건일 때 "위협 0건"(안전)과 "측정 안 함"을 구분하지 못해
    완벽 점수(1.0)를 냈던 게 이 계약을 어긴 사례였다(수정 완료 — gate_e_security/
    aggregate.py의 ``_has_security_config_data`` 가드).

    ``count=0``인데 ``value``가 이미 계산돼 있는 흔한 실수(예: 위반 0건 → 비율 1.0)를
    막기 위해, ``count``와 ``value``를 분리해서 받는다 — 호출부가 ``value``를 계산하기
    *전에* ``count``만으로 먼저 판정할 수도 있다.

    다른 6개 Gate(A/B/C/D/F/G)를 전수 감사한 결과(2026-08) 전부 이미 이 계약을 지키고
    있었다 — 기존 코드를 강제로 이 헬퍼로 재작성하지는 않았다(이미 올바른 코드를
    건드릴 이유가 없음). 새 Gate·새 지표를 추가할 때 이 헬퍼를 쓰면 이 클래스의
    버그가 설계상 재발하지 않는다.

    Args:
        count: 이 컴포넌트에 실제로 기여한 태스크/이벤트 수. 이 함수는 "0건도 유효한
            측정"이라고 가정하지 않는다 — count<=0이면 무조건 미측정으로 본다.
        value: 이미 계산된 값(0-1 정규화됐다고 가정, 클램프는 호출부 책임).

    Returns:
        ``count <= 0``이면 ``None``, 아니면 ``value`` 그대로.

    Example::

        _hall_rate = _measured(len(detections), raw_hall_rate)
    """
    if count <= 0:
        return None
    return value


def assemble_overall(groups: dict[str, Any]) -> dict[str, Any]:
    """등록된 모든 Gate 결과에서 ``overall`` 요약을 조립한다 — 내장 7개(A-G)든
    ``PerformanceMonitor.register_gate()``로 추가된 서드파티 Gate든 구분 없이
    동일하게 처리한다(Phase 2 — 구조적 확장성).

    이전에는 ``_compute_harness_groups()``가 "A","B",...,"G" 7글자를 하드코딩한
    튜플로 overall을 계산했다 — 새 Gate를 추가할 때마다 이 계산도 같이 고쳐야
    했다. 이 함수는 ``groups``에 몇 개가 들어있든 그대로 순회하므로, 새 Gate
    등록만으로 overall 집계에 자동 반영된다.

    Args:
        groups: ``{gate_id: group_dict}``. 각 ``group_dict``는 ``_g()``가 만든
            형태(최소 ``"score"`` 키, ``None`` 가능)를 따라야 한다. 삽입 순서가
            ``scored_group_ids``의 순서로 그대로 보존된다.

    Returns:
        ``{"score", "status", "gate", "scored_groups", "scored_group_ids"}``.
    """
    _id_scores = [(gid, g.get("score")) for gid, g in groups.items()]
    _scored_ids = [gid for gid, s in _id_scores if s is not None]
    _scored = [s for _, s in _id_scores if s is not None]
    _overall_score = round(float(sum(_scored) / len(_scored)), 4) if _scored else 0.0
    return {
        "score": _overall_score,
        "status": _status(_overall_score),
        "gate": _status(_overall_score),
        "scored_groups": len(_scored),
        "scored_group_ids": _scored_ids,
    }


def _gate_pass_verdict(
    score: float,
    threshold: float,
    status: str,
    fail_on_warn: bool = False,
) -> bool:
    """Gate 점수의 pass/fail 최종 판정 — 3개 독립 게이트 경로(``HarnessEvaluationGate``·
    ``QuickEval.gate()``·``cli/gate.py``)가 각자 재구현하던 동일 판정을 공유하는 단일 정본.

    이전에는 이 판정이 세 곳에 토씨 하나 안 틀리고 복제돼 있었다 — 하나를 고쳐도
    나머지 둘은 안 고쳐지는 구조였다. 로직 자체는 기존 동작과 100% 동일하게 유지한다
    (동작 변경 없음, 통합만 목적).

    1차 기준은 ``score >= threshold``다. ``fail_on_warn=True``이면 여기에 더해 Gate의
    기본 분류(``_status()``, 고정 warn=0.7/fail=0.5)가 ``"warn"``이면 무조건 실패로
    escalate한다 — **이 escalation은 ``threshold``가 커스텀 값이어도 항상 고정 기준으로
    이뤄진다.** 즉 "이번 실행에 쓴 임계값을 통과했는가"와 "Gate의 보편적 위험 분류에서
    벗어났는가"라는 서로 다른 두 질문을 동시에 강제하는 것이 의도된 동작이다 —
    ``threshold``를 0.5 미만으로 느슨하게 재정의해도 이 경보 신호 자체는 낮아지지 않는다.

    Args:
        score: 현재 Gate 점수(0-1).
        threshold: 이번 판정에 쓸 임계값 — 커스텀(``group_thresholds``/``gate_thresholds``)
            이거나 기본값(0.7)일 수 있다.
        status: 이 Gate의 사전 계산된 상태 문자열(``_status()``가 고정 0.7/0.5로 낸 값,
            보통 ``harness_groups[gate_id]["status"]``에서 그대로 읽는다).
        fail_on_warn: ``True``면 ``status == "warn"``일 때 threshold 통과 여부와
            무관하게 실패 처리.

    Returns:
        통과하면 ``True``.
    """
    passed = score >= threshold
    if fail_on_warn and status == "warn":
        passed = False
    return passed


def evaluate_gate_scores(
    harness_groups: dict[str, Any],
    *,
    gate_ids: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
    default_threshold: float | None = None,
    strict_required: bool = False,
    fail_on_warn: bool = False,
) -> dict[str, dict[str, Any]]:
    """Gate 점수를 threshold와 대조해 판정한다 — 구조변경③(3경로 완전 통합):
    ``HarnessEvaluationGate.evaluate()``·``QuickEval.gate()``·``cli/gate.py``가 각자
    재구현해 온 "Gate별 score/threshold/status → passed" 루프의 단일 정본.

    ``_gate_pass_verdict()``가 이미 판정 공식(개별 Gate 하나의 pass/fail) 자체를
    통합했다면, 이 함수는 그 판정을 *여러 Gate에 걸쳐 어떻게 순회·필터링할지*까지
    통합한다 — required 필터링, threshold 폴백(개별 지정 → default_threshold), 미측정
    (``score=None``) Gate 처리를 포함한 전체 루프.

    Args:
        harness_groups: ``report.extra_metrics["harness_groups"]`` (또는 baseline 등
            같은 형식의 dict). ``"overall"`` 키는 자동으로 제외된다.
        gate_ids: 판정할 Gate id 목록(순서 보존 — 결과 dict/violations 순서에 그대로
            반영된다). ``None``(기본값)이면 ``harness_groups``의 원래 키 순서 그대로
            모든 dict 값 키를 자동 감지한다 — 내장 A-G뿐 아니라
            ``PerformanceMonitor.register_gate()``로 등록된 커스텀 Gate도 포함된다
            (이전엔 ``QuickEval.gate()``/``cli/gate.py``가 ``"ABCDEFG"``로 고정돼 있어
            커스텀 Gate를 판정할 수 없었다 — 통합하며 이 제약이 사라졌다).
        thresholds: Gate별 개별 임계값(``{"E": 0.95}`` 등). 없는 Gate는
            ``default_threshold``로 폴백.
        default_threshold: ``thresholds``에 없는 Gate의 기본 임계값. 이것도 ``None``이면
            (그리고 해당 Gate가 ``thresholds``에도 없으면) 그 Gate는 결과에서 제외된다
            (판정할 기준이 없으므로 — 기존 3경로 모두의 동작).
        strict_required: ``True``면 ``gate_ids``에 명시적으로 지정된(= 자동 감지가 아닌)
            Gate가 ``score=None``(미측정)일 때 실패 처리. 기본값 ``False``는 "미측정
            Gate는 조용히 통과"라는 기존 동작.
        fail_on_warn: ``_gate_pass_verdict()``에 그대로 전달 — ``status == "warn"``이면
            threshold 통과 여부와 무관하게 실패 처리.

    Returns:
        ``{gate_id: {"score": float|None, "status": str, "passed": bool,
        "threshold": float|None, "not_measured": bool (score=None일 때만 존재)}}``.
        측정된 Gate는 ``score``가 반올림(4자리)돼 있다.
    """
    _explicit_gate_ids = gate_ids is not None
    _ids_to_check = gate_ids if gate_ids is not None else [
        k for k, v in harness_groups.items() if k != "overall" and isinstance(v, dict)
    ]

    results: dict[str, dict[str, Any]] = {}
    for gate_id in _ids_to_check:
        gate_data = harness_groups.get(gate_id)
        if not isinstance(gate_data, dict):
            continue
        score = gate_data.get("score")
        status = gate_data.get("status", "n/a")

        if score is None:
            _not_measured_passed = not (strict_required and _explicit_gate_ids)
            results[gate_id] = {
                "score": None, "status": "n/a",
                "passed": _not_measured_passed, "not_measured": True,
            }
            continue

        threshold = (thresholds or {}).get(gate_id, default_threshold)
        if threshold is None:
            continue

        score_f = float(score)
        passed = _gate_pass_verdict(score_f, threshold, status, fail_on_warn=fail_on_warn)
        results[gate_id] = {
            "score": round(score_f, 4), "status": status,
            "passed": passed, "threshold": threshold,
        }

    return results


def _g(
    score: float | None,
    name: str,
    details: dict[str, Any],
    f_score: bool = False,
) -> dict[str, Any]:
    """그룹 딕셔너리 생성 헬퍼 — status와 gate 키를 동시에 출력."""
    _st = (_status(score) if not f_score else (_status(score) if score is not None else "n/a"))
    return {"name": name, "score": score, "status": _st, "gate": _st, "details": details}
