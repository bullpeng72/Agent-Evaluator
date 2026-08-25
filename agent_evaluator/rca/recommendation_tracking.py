"""
agent_evaluator.rca.recommendation_tracking
===============================================
Phase 4(개선 엔진, 폐루프 학습) — 추천 적용 이력의 append-only 감사 로그.

``rca/verify.py``는 의도적으로 "추천 적용 이력을 자동으로 추적하는 저장소(성공률
누적·랭킹)는 만들지 않는다"고 범위를 좁혔다 — 검증할 실사용 데이터가 없는 상태에서
랭킹/우선순위 알고리즘부터 만들면 정확성을 검증할 방법이 없는 통계를 SDK에 넣게
된다는 이유였다. 이 모듈은 그 경계를 넘지 않는다: 여기 있는 건
``verify_recommendation_outcome()``의 판정을 ``gates/team_concurrency.py``의
``.aoo/claims.jsonl``과 같은 append-only JSON Lines 패턴으로 기록·조회하는 순수
로깅 계층뿐이다. ``summarize_recommendation_outcomes()``가 내는 것도 평범한 개수
집계(confirmed/refuted/inconclusive 카운트)이지, "이 추천이 더 낫다"는 순위나
예측이 아니다 — 그 선을 넘는 순간 ``verify.py``가 경계했던 문제로 되돌아간다.

HOTL 원칙(Chapter 2): 이 모듈은 "무슨 일이 있었는지"만 보여준다 — "다음에 뭘
추천할지"는 사람이 이 개수를 보고 판단한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from agent_evaluator.rca.verify import verify_recommendation_outcome


def record_recommendation_outcome(
    log_path: Union[str, Path],
    *,
    recommendation_id: str,
    target_gate: str,
    before: dict[str, Any],
    after: dict[str, Any],
    target_field: str | None = None,
    improvement_threshold: float = 0.05,
    note: str | None = None,
) -> dict[str, Any]:
    """추천 적용 전/후 리포트를 ``verify_recommendation_outcome()``으로 판정하고,
    그 결과를 ``log_path``에 한 줄(JSON Lines) append한다 — ``.aoo/claims.jsonl``과
    같은 append-only 형식을 차용한다(스키마는 다르다 — 이 로그는 클레임이 아니라
    판정 이력이다).

    Args:
        log_path: 기록할 JSONL 파일 경로. 상위 디렉터리가 없으면 생성한다.
        recommendation_id: 이 추천을 식별하는 문자열(예: ontology remediation 코드,
            또는 사람이 붙인 임의 id) — 같은 추천이 여러 번 적용된 이력을 나중에
            모아 보는 키로 쓰인다.
        target_gate / before / after / target_field / improvement_threshold:
            ``verify_recommendation_outcome()``과 동일 — 그대로 위임한다.
        note: 사람이 남기는 자유 형식 메모(선택, 예: 실제로 적용한 코드 변경 요약).

    Returns:
        기록된 한 줄의 dict 전체(``verify_recommendation_outcome()`` 결과 +
        ``recommendation_id``/``recorded_at``/``note``) — 파일을 다시 읽지 않아도
        호출자가 즉시 확인할 수 있게 그대로 반환한다.
    """
    verdict_result = verify_recommendation_outcome(
        before, after, target_gate=target_gate, target_field=target_field,
        improvement_threshold=improvement_threshold,
    )
    entry: dict[str, Any] = {
        "recommendation_id": recommendation_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        **verdict_result,
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_recommendation_outcomes(
    log_path: Union[str, Path],
    *,
    recommendation_id: str | None = None,
    target_gate: str | None = None,
) -> list[dict[str, Any]]:
    """``log_path``의 모든 기록 줄을 읽는다. append-only라 "최신만 유효" 같은 상태
    접기가 없다 — ``claims.jsonl``의 active/released 상태 기계와 달리, 판정 이력은
    매 기록이 독립적인 과거 사실이라 전부가 그대로 유효하다. 파일이 없으면 빈 리스트.

    Args:
        log_path: ``record_recommendation_outcome()``이 기록한 JSONL 파일 경로.
        recommendation_id / target_gate: 지정하면 그 값과 일치하는 줄만 반환.

    Returns:
        기록된 dict 리스트, 기록 순서(파일에 쓰인 순서) 그대로.
    """
    path = Path(log_path)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # 손상된 줄은 조용히 건너뜀 — 감사 로그 전체를 무효화하지 않음
            if (
                recommendation_id is not None
                and entry.get("recommendation_id") != recommendation_id
            ):
                continue
            if target_gate is not None and entry.get("target_gate") != target_gate:
                continue
            entries.append(entry)
    return entries


def summarize_recommendation_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """판정 이력의 단순 개수 집계 — confirmed/refuted/inconclusive 카운트만 낸다.

    의도적으로 랭킹·우선순위·성공"률"을 계산하지 않는다 — 비율은 표본이 적을 때
    오도하기 쉽고, 이 모듈의 목적은 "무슨 일이 있었는지 보여주는 것"이지 "다음에 뭘
    추천할지 판단하는 것"이 아니다(HOTL — 그 판단은 사람이 이 개수를 보고 내린다).

    Args:
        outcomes: ``load_recommendation_outcomes()``의 반환값(또는 그 부분집합).

    Returns:
        ``{"total", "confirmed", "refuted", "inconclusive", "by_gate": {gate:
        {"total", "confirmed", "refuted", "inconclusive"}}}``.
    """
    def _empty_counts() -> dict[str, int]:
        return {"total": 0, "confirmed": 0, "refuted": 0, "inconclusive": 0}

    overall = _empty_counts()
    by_gate: dict[str, dict[str, int]] = {}
    for entry in outcomes:
        verdict = entry.get("verdict")
        gate = entry.get("target_gate")
        overall["total"] += 1
        if verdict in overall:
            overall[verdict] += 1
        if gate is not None:
            bucket = by_gate.setdefault(gate, _empty_counts())
            bucket["total"] += 1
            if verdict in bucket:
                bucket[verdict] += 1

    return {**overall, "by_gate": by_gate}
