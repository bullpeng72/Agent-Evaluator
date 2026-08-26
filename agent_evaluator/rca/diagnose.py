"""
agent_evaluator.rca.diagnose
===============================
Media/Harness_Method Chapter 31(Gate 하락 원인진단 — RCA 프레임워크)의 3단계
절차(§31.0~31.2)를 그대로 자동화한다.

1단계(감지) — baseline이 있으면 Gate 점수 회귀(``_compute_gate_regressions()``,
   Phase 0에서 3개 게이트 경로가 이미 공유하는 정본 함수)를, 없으면 현재 상태가
   fail/warn인 Gate를 감지 대상으로 삼는다.
2단계(원인귀속) — 감지된 Gate의 ``details``를 baseline과 비교해 가장 크게 움직인
   세부 지표를 순서대로 뽑는다(§31.4가 강조하듯 top-line 점수만 보면 놓치는
   세부값의 반대 방향 이동도 그대로 드러난다).
3단계(교차확인) — SQLite 위반 이력(``search_violations()``)이 있으면 가장 크게
   움직인 지표 이름으로 검색해 같은 시기 위반 이력을 찾는다.

여러 Gate가 동시에 감지되면 §31.2의 교훈("하나의 원인이라 성급히 가정하지 마라")을
그대로 반영한다 — Gate C·D가 함께 감지된 경우에만 SLA 공유원인 여부를 가장 싼
체크(details 필드 대조)로 먼저 확인하고, 그 외에는 각 Gate를 독립적으로 보고한다.

HOTL 원칙(Chapter 2): 이 함수는 후보 원인과 근거만 반환한다 — "이게 원인이다"를
단정하지 않는다. 최종 판단은 사람(QA·거버넌스 담당자)의 몫이다.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from agent_evaluator.quick_eval import _compute_gate_regressions, _normalize_gate_score_dict

_NON_NUMERIC_DETAIL_KEYS = frozenset({"insufficient_data_warnings"})


def _extract_harness_groups(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {}
    return (report.get("extra_metrics") or {}).get("harness_groups", {}) or {}


def _as_number(v: Any) -> float | None:
    """bool은 int의 서브클래스라 isinstance(v, (int, float))에 True로 걸리는 함정을
    피하려고 별도 헬퍼로 뽑았다 — True/False가 1.0/0.0으로 잘못 집계되는 걸 방지."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _ranking_scale(field: str) -> float:
    """정렬용 스케일 보정 — Gate details는 필드마다 자연 단위가 다르다(``tcr_pct``는
    0-100, 대부분의 ``avg_*``/``*_rate``는 0-1). 원시 delta를 그대로 비교하면
    0-100 스케일 필드가 항상 "가장 크게 움직인 지표"로 오판되는데, 이건 이미
    Phase 2(``get_comparison`` accuracy_dropped)에서 확인한 것과 같은 클래스의
    스케일 오판이다 — 여기서도 같은 실수를 반복하지 않는다.
    """
    return 100.0 if field.endswith("_pct") else 1.0


def _numeric_detail_deltas(
    current_details: dict[str, Any], baseline_details: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Gate details의 숫자 필드만 골라 baseline 대비 변화량 순으로 정렬한다.

    ``deadlock_by_type``(dict)·``insufficient_data_warnings``(list)처럼 숫자가
    아닌 필드는 제외한다 — "가장 크게 움직인 세부 지표"라는 질문에 답이 안 되기
    때문이다. 정렬은 ``_ranking_scale()``로 0-100/0-1 스케일을 맞춘 뒤 비교한다 —
    반환하는 ``delta``/``current``/``baseline`` 값 자체는 원래 단위 그대로 보존한다
    (표시용 값을 조작하지 않는다, 정렬 기준에만 정규화를 적용).
    """
    keys = set(current_details.keys())
    if baseline_details:
        keys |= set(baseline_details.keys())
    keys -= _NON_NUMERIC_DETAIL_KEYS

    deltas: list[dict[str, Any]] = []
    for key in keys:
        cur_v = current_details.get(key)
        base_v = (baseline_details or {}).get(key)
        cur_f = _as_number(cur_v)
        base_f = _as_number(base_v)
        if cur_f is None and base_f is None:
            continue  # 둘 다 숫자가 아니면(예: deadlock_by_type dict) 제외
        delta = (cur_f - base_f) if (cur_f is not None and base_f is not None) else None
        deltas.append({"field": key, "current": cur_f, "baseline": base_f, "delta": delta})

    # delta가 있는 항목을 스케일 보정된 절대값 큰 순으로 먼저, baseline이 없어 delta를
    # 못 낸 항목은 뒤로.
    def _sort_key(d: dict[str, Any]) -> float:
        if d["delta"] is None:
            return -1.0
        return abs(d["delta"]) / _ranking_scale(d["field"])

    deltas.sort(key=_sort_key, reverse=True)
    return deltas


def _check_sla_shared_cause(
    current_hg: dict[str, Any], baseline_hg: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Gate C·D가 동시에 감지됐을 때 SLA가 공유 원인인지 가장 싼 체크(details 필드
    대조)로 먼저 확인한다 — Chapter 31 §31.2·CLAUDE.md의 RCA 상호참조와 동일 절차."""
    c_details = (current_hg.get("C") or {}).get("details") or {}
    d_details = (current_hg.get("D") or {}).get("details") or {}
    sla_breach_rate = c_details.get("sla_breach_rate")
    sla_window_penalty = d_details.get("sla_window_penalty")
    sla_budget_penalty = d_details.get("sla_budget_penalty")
    if sla_breach_rate is None and sla_window_penalty is None and sla_budget_penalty is None:
        return None

    _breach = sla_breach_rate or 0.0
    _penalty = (sla_window_penalty or 0.0) + (sla_budget_penalty or 0.0)
    likely_shared_cause = _breach > 0.1 or _penalty > 0.05
    return {
        "sla_breach_rate": sla_breach_rate,
        "sla_window_penalty": sla_window_penalty,
        "sla_budget_penalty": sla_budget_penalty,
        "likely_shared_cause": likely_shared_cause,
        "note": (
            "SLA breach/penalty detected — this may be a shared cause behind the "
            "simultaneous drop in Gate C and D. Investigate SLA-related changes first "
            "(threshold adjustments, external API latency, etc)."
            if likely_shared_cause else
            "SLA breach/penalty is low — SLA is unlikely to be a shared cause. "
            "Investigate Gate C and Gate D independently."
        ),
    }


@dataclasses.dataclass(frozen=True)
class SharedCauseCheck:
    """"여러 Gate가 동시에 감지됐을 때 공유 원인인지 싸게 먼저 확인하는" 절차 하나를
    등록 가능한 형태로 표현한다(폐루프 학습 — reverse-diagnosis 일반화).

    지금은 ``SHARED_CAUSE_CHECKS``에 SLA 체크 하나만 있다 — 검증된 교차참조가 그것
    하나뿐이기 때문이다(CLAUDE.md의 RCA 상호참조 문서화 항목과 일치). 새 교차참조가
    실제로 검증되면(예: 다른 Gate 쌍의 공유 원인 패턴이 발견되면) 여기 하나 더 등록하면
    된다 — 아래 ``_select_shared_cause_explanations()``의 최소 설명집합 선택 로직은
    체크 개수와 무관하게 그대로 동작한다.
    """
    name: str
    applies_to_gates: frozenset[str]
    check_fn: Any  # Callable[[dict, dict|None], dict|None]


SHARED_CAUSE_CHECKS: tuple[SharedCauseCheck, ...] = (
    SharedCauseCheck("sla", frozenset({"C", "D"}), _check_sla_shared_cause),
)


def _select_shared_cause_explanations(
    detected_gate_ids: list[str],
    current_hg: dict[str, Any],
    baseline_hg: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """감지된 Gate 집합을 "공유 원인으로 설명되는 그룹"과 "독립적으로 봐야 하는 나머지"로
    가른다 — minimal hitting set의 그리디 근사(Reiter 1987류 최소 진단 이론과 같은
    구조: 가장 많은 관측을 설명하는 원인부터 채택하고, 이미 설명된 것과 안 겹치는
    나머지 체크만 계속 본다). 체크가 1개뿐인 지금은 사실상 "적용 가능하면 적용"과
    동일하지만, 이 알고리즘 자체는 체크가 늘어나도 그대로 확장된다.

    Returns:
        ``(explanations, independent_gates)`` — ``explanations``는 채택된
        ``SharedCauseCheck``의 결과 목록(``explains_gates`` 키로 어느 Gate를
        설명하는지 포함), ``independent_gates``는 어떤 체크로도 설명 안 된 나머지
        Gate 목록(정렬됨) — 이 Gate들은 기존처럼 각자 독립 finding으로 보고된다.
    """
    detected_set = set(detected_gate_ids)
    explanations: list[dict[str, Any]] = []
    explained_gates: set[str] = set()

    applicable = [c for c in SHARED_CAUSE_CHECKS if c.applies_to_gates <= detected_set]
    # 그리디: 가장 많은 Gate를 설명하는 체크부터 — 표준 set-cover 그리디 근사.
    applicable.sort(key=lambda c: len(c.applies_to_gates), reverse=True)

    for check in applicable:
        if check.applies_to_gates <= explained_gates:
            continue  # 이미 다른(먼저 채택된) 체크로 전부 설명됨 — 중복 적용 안 함
        result = check.check_fn(current_hg, baseline_hg)
        if result and result.get("likely_shared_cause"):
            explanations.append({
                "check": check.name,
                "explains_gates": sorted(check.applies_to_gates),
                **result,
            })
            explained_gates |= check.applies_to_gates

    independent_gates = sorted(detected_set - explained_gates)
    return explanations, independent_gates


# Gate F의 details 필드명 → ontology.mast_taxonomy.MASTFailureMode.related_gate_f_metric.
# 두 이름 체계가 자연스럽게 안 맞는 지점(avg_role_compliance → role_adherence)이 있어
# _search_query_for_field()의 범용 접두/접미사 제거만으로는 못 맞춘다 — Gate F 전용으로
# 명시 매핑한다.
_GATE_F_FIELD_TO_MAST_METRIC: dict[str, str] = {
    "avg_consensus": "consensus",
    "avg_propagation": "propagation",
    "avg_role_compliance": "role_adherence",
    "avg_conflict_resolution": "conflict_resolution",
}


def _mast_candidates_for_gate_f(top_field: str | None) -> list[dict[str, Any]]:
    """Gate F가 감지됐을 때, 가장 크게 움직인 세부 지표와 관련된 MAST 후보 실패모드를
    참고용으로 붙인다(HOTL — 이게 원인이라고 단정하지 않는다, mast_taxonomy.py 모듈
    docstring 참고)."""
    from agent_evaluator.ontology.mast_taxonomy import mast_failure_modes_for_gate_f_metric

    if top_field is None:
        return []
    mast_metric = _GATE_F_FIELD_TO_MAST_METRIC.get(top_field)
    if mast_metric is None:
        return []
    modes = mast_failure_modes_for_gate_f_metric(mast_metric)
    return [
        {
            "code": m.code, "name": m.name, "category": m.category,
            "description": m.description, "remediation": m.remediation,
            # 논문 Figure 1 관측 빈도(%, 1642개 트레이스 기준) — 참고용, 이 세션에서 실제로
            # 그 정도 비율로 발생했다는 뜻이 아니다(HOTL 원칙, mast_taxonomy.py 참고).
            "prevalence_pct": m.prevalence_pct,
        }
        for m in modes
    ]


def _search_query_for_field(field: str) -> str:
    """detail 필드명에서 검색어를 뽑는다 — 접두/접미사(avg_/_rate/_score 등)를 벗겨
    ``search_violations()``의 FTS5 토큰 검색에 맞는 핵심어만 남긴다."""
    q = field
    for prefix in ("avg_", "gate_a_ref__"):
        if q.startswith(prefix):
            q = q[len(prefix):]
    for suffix in ("_rate", "_score", "_count", "_pct"):
        if q.endswith(suffix):
            q = q[: -len(suffix)]
    return q or field


def diagnose(
    current: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    regression_threshold: float = 0.1,
    violation_db_path: str | Path | None = None,
    violation_search_limit: int = 5,
    with_experiment_metadata: bool = False,
    repo_path: str | Path = ".",
) -> dict[str, Any]:
    """Chapter 31의 3단계 RCA 절차를 자동화한다.

    Args:
        current: 평가 결과 JSON을 로드한 dict(``report.to_dict()`` 또는
            ``json.load()``의 반환값 그대로).
        baseline: 비교 대상 baseline 결과 JSON(선택). 있으면 회귀 기반 감지
            (§31.0의 1단계와 동일), 없으면 현재 fail/warn 상태 기반 감지로 폴백한다.
        regression_threshold: baseline 대비 허용 회귀 비율(``_compute_gate_regressions``와
            동일 정의 — 3개 게이트 경로가 이미 공유하는 정본 공식).
        violation_db_path: ``save_tasks_to_db()``로 만든 SQLite DB 경로(선택).
            주어지면 3단계(교차확인)에서 ``search_violations()``를 호출한다 —
            없으면(JSON 백엔드만 쓴 경우) 3단계는 조용히 건너뛴다.
        violation_search_limit: ``search_violations()`` 호출당 최대 반환 건수.
        with_experiment_metadata: ``True``면 ``rca.derive_experiment_metadata()``로
            baseline→current 사이에 실제 어떤 커밋이 있었는지 git에서 조회해 붙인다
            (폐루프 학습 — metric-space 발견을 code-space 원인과 연결). 기본값 False —
            git 서브프로세스 호출이라 순수 함수 기본 경로를 느리게 하지 않기 위해 옵트인.
        repo_path: ``with_experiment_metadata=True``일 때 조회할 git 저장소 경로.

    Returns:
        ``{detection_mode, regression_threshold, detected_gates, regressions,
        findings, multi_gate_note, sla_shared_cause_check, shared_cause_explanations,
        independently_investigate_gates, experiment_metadata}``. ``findings``의 각
        항목은 ``{gate, current_score, baseline_score, top_detail_deltas,
        cross_references, [F만] mast_candidates}`` — "이게 원인이다"를 단정하지 않고
        후보와 근거만 담는다. ``shared_cause_explanations``는
        ``SHARED_CAUSE_CHECKS``(reverse-diagnosis — 폐루프 학습)에서 채택된 공유
        원인 목록, ``independently_investigate_gates``는 어떤 체크로도 설명 안 돼
        각자 독립 조사가 필요한 Gate 목록이다. ``experiment_metadata``는
        ``with_experiment_metadata=True``이고 두 리포트 모두 git commit 정보가
        있을 때만 채워진다(그 외엔 ``None``).
    """
    current_hg = _extract_harness_groups(current)
    baseline_hg = _extract_harness_groups(baseline) if baseline is not None else None

    current_scores = {g: (current_hg.get(g) or {}).get("score") for g in "ABCDEFG"}

    regressions: list[dict[str, Any]] | None = None
    baseline_scores: dict[str, float | None] = {}
    if baseline_hg is not None:
        baseline_scores = _normalize_gate_score_dict(baseline_hg)
        regressions = _compute_gate_regressions(
            current_scores, baseline_scores, regression_threshold,
        )
        detected_gate_ids = [r["gate"] for r in regressions]
        detection_mode = "regression_vs_baseline"
    else:
        detected_gate_ids = [
            g for g in "ABCDEFG" if (current_hg.get(g) or {}).get("status") in ("fail", "warn")
        ]
        detection_mode = "absolute_threshold"

    findings: list[dict[str, Any]] = []
    for gate_id in detected_gate_ids:
        cur_details = (current_hg.get(gate_id) or {}).get("details") or {}
        base_details = (baseline_hg.get(gate_id) or {}).get("details") if baseline_hg else None
        detail_deltas = _numeric_detail_deltas(cur_details, base_details)

        cross_refs: list[dict[str, Any]] = []
        if violation_db_path is not None and detail_deltas:
            from agent_evaluator.storage.sqlite_backend import search_violations

            query = _search_query_for_field(detail_deltas[0]["field"])
            try:
                cross_refs = search_violations(
                    violation_db_path, query, limit=violation_search_limit,
                )
            except Exception:
                cross_refs = []  # DB 없음/손상 등 — 3단계만 건너뛰고 1·2단계 결과는 그대로 반환

        finding: dict[str, Any] = {
            "gate": gate_id,
            "current_score": current_scores.get(gate_id),
            "baseline_score": baseline_scores.get(gate_id) if baseline_hg is not None else None,
            "top_detail_deltas": detail_deltas[:5],
            "cross_references": cross_refs,
        }
        if gate_id == "F":
            _top_field = detail_deltas[0]["field"] if detail_deltas else None
            finding["mast_candidates"] = _mast_candidates_for_gate_f(_top_field)
        findings.append(finding)

    multi_gate_note = None
    sla_shared_cause = None
    shared_cause_explanations: list[dict[str, Any]] = []
    independent_gates: list[str] = []
    if len(detected_gate_ids) > 1:
        multi_gate_note = (
            f"{len(detected_gate_ids)} Gates ({', '.join(detected_gate_ids)}) detected "
            "simultaneously — don't assume a single cause too quickly. It's more common "
            "for several unrelated changes to coincide in the same deployment "
            "(Chapter 31 §31.2)."
        )
        if {"C", "D"} <= set(detected_gate_ids):
            sla_shared_cause = _check_sla_shared_cause(current_hg, baseline_hg)
        # reverse-diagnosis(폐루프 학습) — 일반화된 최소 설명집합 선택. 위 sla_shared_cause는
        # 하위호환 필드로 그대로 두고(기존 소비 코드/테스트가 이 정확한 shape을 기대함),
        # 이 결과는 같은 SLA 체크를 포함해 "몇 개 Gate가 공유 원인으로 설명됐고 몇 개가
        # 독립적으로 남았는지"를 일반화된 형태로 추가 제공한다.
        shared_cause_explanations, independent_gates = _select_shared_cause_explanations(
            detected_gate_ids, current_hg, baseline_hg,
        )
    else:
        independent_gates = list(detected_gate_ids)

    experiment_metadata = None
    if with_experiment_metadata and baseline is not None:
        from agent_evaluator.rca.experiment_metadata import derive_experiment_metadata

        _exp = derive_experiment_metadata(baseline, current, repo_path=repo_path)
        # JSON 직렬화 가능한 순수 dict로 변환 — dataclass 그대로 반환하면 CLI --json
        # 경로(json.dumps)와 API 소비자 모두가 dataclass를 알아야 하는 부담이 생긴다.
        experiment_metadata = dataclasses.asdict(_exp) if _exp is not None else None

    return {
        "detection_mode": detection_mode,
        "regression_threshold": regression_threshold if baseline_hg is not None else None,
        "detected_gates": detected_gate_ids,
        "regressions": regressions,
        "findings": findings,
        "multi_gate_note": multi_gate_note,
        "sla_shared_cause_check": sla_shared_cause,
        "shared_cause_explanations": shared_cause_explanations,
        "independently_investigate_gates": independent_gates,
        "experiment_metadata": experiment_metadata,
    }
