"""
agent_evaluator.gates.gate_f_multiagent.evaluators
=====================================================
Gate F(Multi-Agent Coordination) 평가 함수 4종.

SPEC-000 Commit 1: agent_evaluator/helpers/taskresult_helpers.py에서 그대로 이관
(로직 변경 없음). taskresult_helpers.py는 이 모듈을 re-export하여 하위호환을 유지한다.

_token_overlap_ratio/normalize_text는 Gate B(eval_loop_detection)·Gate C
(compute_reproducibility_score)도 공유하는 인프라이므로 taskresult_helpers.py에
그대로 두고 여기서는 import만 한다.

SPEC-009: 구조화 신호(agent_interactions/tool_calls) 우선 평가 전환.
eval_consensus/eval_role_adherence/eval_propagation 3종에 "구조화 데이터가 있으면
우선 사용, 없으면 텍스트 휴리스틱으로 폴백" 패턴을 도입했다. 각 함수의 반환 dict에는
진단용 "signal_source"("structured" | "text_fallback") 키가 추가된다(Gate 점수에는
영향 없음). 폴백 경로(구조화 데이터 미제공 시)는 기존 로직과 100% 동일하게 유지된다
— 회귀 테스트는 tests/test_gate_f_structured_signals.py 참고.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from agent_evaluator.helpers.taskresult_helpers import _token_overlap_ratio, normalize_text

logger = logging.getLogger(__name__)


def _consensus_structured_signals(
    agent_interactions: Optional[List[Any]],
    names: List[str],
) -> Optional[Dict[str, Tuple[Optional[str], Optional[str]]]]:
    """agent_interactions에서 에이전트별 구조화 의도/액션 신호를 추출한다(REQ-1).

    각 interaction dict가 에이전트 식별자("agent"/"agent_name"/"name")와 구조화 필드
    ("intent" 또는 "action")를 모두 담고 있으면 그 에이전트의 신호로 채택한다(동일
    에이전트의 항목이 여러 개면 마지막 항목이 최종 신호로 우선한다).

    ``names``의 모든 에이전트에 대해 신호를 찾지 못하면(일부 데이터 누락) 부분적으로
    구조화 모드를 적용하지 않고 None을 반환해 안전하게 텍스트 폴백으로 전환한다 —
    프레임워크(LangGraph/CrewAI 등)마다 agent_interactions 스키마가 달라 부분 데이터를
    섞어 판정하면 오히려 신뢰도가 떨어지기 때문이다.

    Args:
        agent_interactions: 에이전트 상호작용 리스트 (스키마는 프레임워크마다 상이할 수 있음).
        names: 합의 판정 대상 에이전트 이름 목록.

    Returns:
        {agent_name: (intent, action)} 또는 구조화 신호가 불완전/부재하면 None.
    """
    if not agent_interactions:
        return None

    by_name: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for interaction in agent_interactions:
        if not isinstance(interaction, dict):
            continue
        agent_id = (
            interaction.get("agent")
            or interaction.get("agent_name")
            or interaction.get("name")
        )
        if not agent_id:
            continue
        intent = interaction.get("intent")
        action = interaction.get("action")
        if intent is None and action is None:
            continue  # 구조화 필드 없음 — 이 항목은 신호로 사용 불가

        def _norm(v: Any) -> Optional[str]:
            return str(v).strip().lower() if v is not None else None

        by_name[str(agent_id)] = (_norm(intent), _norm(action))

    if not by_name:
        return None
    # names 전원의 신호가 확보되어야 구조화 모드로 전환(부분 데이터는 폴백)
    if not all(n in by_name for n in names):
        return None
    return by_name


def eval_consensus(
    responses: List[str],
    agent_names: Optional[List[str]],
    config: Any,
    agent_interactions: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """다중 에이전트 응답의 합의 품질을 측정한다.

    SPEC-009 REQ-1: ``agent_interactions``에 에이전트별 구조화 의도/액션 필드
    (``intent``/``action``)가 모두 채워져 있으면 어휘 유사도(``_token_overlap_ratio``)
    대신 구조화 필드 일치 여부로 합의를 판정한다(``signal_source="structured"``).
    ``agent_interactions``가 없거나 일부 에이전트의 구조화 필드를 찾을 수 없으면
    기존 텍스트 매칭으로 폴백한다(``signal_source="text_fallback"`` — 하위호환,
    ``agent_interactions`` 생략 시 기존 동작과 100% 동일).

    Args:
        responses: 에이전트별 응답 문자열 목록 (len >= 2).
        agent_names: 각 응답에 대응하는 에이전트 이름 목록 (None이면 0,1,2,... 인덱스 사용).
        config: ConsensusConfig 인스턴스.
        agent_interactions: (신규, 선택) 에이전트별 구조화 상호작용 목록. 각 항목은
            {"agent"|"agent_name"|"name": str, "intent": ..., "action": ...} 형식을 지원한다.

    Returns:
        {consensus_score, agreement_pairs, dissenting_agents, selected_response, method,
         signal_source}
    """
    if not responses or len(responses) < 2:
        return {
            "consensus_score": 1.0,
            "agreement_pairs": [],
            "dissenting_agents": [],
            "selected_response": responses[0] if responses else None,
            "method": "single",
            "signal_source": "text_fallback",
        }

    method: str = getattr(config, "consensus_method", "majority") or "majority"
    agent_weights: Dict[str, float] = getattr(config, "agent_weights", {}) or {}
    # F-6: `or 0.7` falsy 패턴 — similarity_threshold=0.0 입력 시 0.7로 강제 override되는 버그
    # ConsensusConfig.__post_init__이 0.0을 차단하지만 방어 코드로 명시적 None 체크로 수정
    _raw_thresh = getattr(config, "similarity_threshold", None)
    sim_threshold: float = float(_raw_thresh) if _raw_thresh is not None else 0.7
    select_best: bool = getattr(config, "select_consensus_response", False)

    names = agent_names or [str(i) for i in range(len(responses))]

    # SPEC-009 REQ-1: 구조화 신호가 전 에이전트에 대해 확보되면 구조화 모드로 전환
    _structured_signals = _consensus_structured_signals(agent_interactions, names)
    signal_source = "structured" if _structured_signals is not None else "text_fallback"

    # pairwise similarity matrix
    sim_matrix: List[List[float]] = []
    for i in range(len(responses)):
        row = []
        for j in range(len(responses)):
            if i == j:
                row.append(1.0)
            elif _structured_signals is not None:
                # 구조화 필드(intent/action) 완전 일치 여부로 판정 — 어휘 표현 차이에 영향받지 않음
                row.append(
                    1.0 if _structured_signals[names[i]] == _structured_signals[names[j]] else 0.0
                )
            else:
                row.append(_token_overlap_ratio(
                    normalize_text(responses[i]),
                    normalize_text(responses[j]),
                ))
        sim_matrix.append(row)

    # 동의 쌍 (threshold 이상이면 동의)
    agreement_pairs: List[Dict[str, Any]] = []
    agree_count = 0
    total_pairs = 0
    for i in range(len(responses)):
        for j in range(i + 1, len(responses)):
            total_pairs += 1
            sim = sim_matrix[i][j]
            agreed = sim >= sim_threshold
            agreement_pairs.append({
                "agent_a": names[i],
                "agent_b": names[j],
                "similarity": round(sim, 4),
                "agreed": agreed,
            })
            if agreed:
                agree_count += 1

    # Fix3: 양방향 sim_matrix로 판단 — i+1 범위 제약에 의한 마지막 에이전트 오판 방지
    dissenting_set: set = set()
    for i in range(len(responses)):
        if not any(sim_matrix[i][j] >= sim_threshold for j in range(len(responses)) if j != i):
            dissenting_set.add(names[i])

    # Fix6: consensus_method가 실제 점수에 반영되도록 수정
    if method == "unanimity":
        # 만장일치: 모든 쌍이 동의해야만 1.0, 하나라도 불일치 시 0.0
        consensus_score = 1.0 if (total_pairs > 0 and agree_count == total_pairs) else 0.0
    elif method == "weighted" and agent_weights:
        # 가중 합의: 쌍의 두 에이전트 가중치 평균으로 weighted ratio 계산
        # agent_weights 키가 실제 names와 하나도 일치하지 않으면 경고 (사실상 majority 동작)
        if not any(n in agent_weights for n in names):
            logger.warning(
                "eval_consensus: method='weighted'이지만 agent_weights 키 %s가 "
                "agent_names %s와 일치하지 않아 모든 가중치가 1.0으로 폴백됩니다. "
                "ConsensusConfig(agent_weights={'<name>': weight}) 에서 키를 "
                "agent_names와 동일하게 설정하세요.",
                list(agent_weights.keys()), names,
            )
        _w_agree = 0.0
        _w_total = 0.0
        for _pair in agreement_pairs:
            _w = (
                agent_weights.get(_pair["agent_a"], 1.0)
                + agent_weights.get(_pair["agent_b"], 1.0)
            ) / 2.0
            _w_total += _w
            if _pair["agreed"]:
                _w_agree += _w
        consensus_score = (
            _w_agree / _w_total if _w_total > 0
            else (agree_count / total_pairs if total_pairs > 0 else 1.0)
        )
    else:
        # majority: 동의 쌍 비율
        consensus_score = agree_count / total_pairs if total_pairs > 0 else 1.0

    # 대표 응답 선택
    selected_response: Optional[str] = None
    if select_best:
        if method == "weighted" and agent_weights:
            # 가중치가 높은 에이전트의 응답 선택
            best_idx = max(
                range(len(names)),
                key=lambda i: agent_weights.get(names[i], 1.0),
            )
            selected_response = responses[best_idx]
        else:
            # majority: 평균 유사도가 가장 높은 응답
            avg_sims = [
                sum(sim_matrix[i][j] for j in range(len(responses)) if j != i) / max(len(responses) - 1, 1)
                for i in range(len(responses))
            ]
            selected_response = responses[avg_sims.index(max(avg_sims))]

    return {
        "consensus_score": round(consensus_score, 4),
        "agreement_pairs": agreement_pairs,
        "dissenting_agents": list(dissenting_set),
        "selected_response": selected_response,
        "method": method,
        "signal_source": signal_source,
    }


def _propagation_structured_signal(
    agent_interactions: Optional[List[Any]],
    key_facts: List[str],
) -> Optional[Dict[str, set]]:
    """agent_interactions의 각 홉에서 구조화된 fact 전파 신호를 추출한다(SPEC-009 REQ-3).

    interaction dict가 "facts_relayed"(또는 "relayed_facts") 키로 해당 홉이 실제로
    전달한 fact 목록을 구조화된 형태로 제공하면, 텍스트 윈도우 기반 부정어 탐지 대신
    이 신호를 직접 사용한다. "distorted_facts" 키가 있으면 해당 fact가 이 홉에서
    왜곡(부정/오전달 등)되었음을 프레임워크가 직접 표명한 것으로 간주한다.

    Args:
        agent_interactions: 에이전트 상호작용(홉) 리스트.
        key_facts: PropagationConfig.key_facts (대조 대상 fact 목록).

    Returns:
        {"relayed": set[str], "distorted": set[str]} 또는 구조화 필드가 전혀 없으면 None.
    """
    if not agent_interactions:
        return None

    relayed: set = set()
    distorted: set = set()
    has_structured = False
    for interaction in agent_interactions:
        if not isinstance(interaction, dict):
            continue
        _relayed = interaction.get("facts_relayed")
        if _relayed is None:
            _relayed = interaction.get("relayed_facts")
        if _relayed is None:
            continue  # 이 홉은 구조화 신호를 제공하지 않음
        has_structured = True
        for f in _relayed:
            if f in key_facts:
                relayed.add(f)
        for f in (interaction.get("distorted_facts") or []):
            if f in key_facts:
                distorted.add(f)

    if not has_structured:
        return None
    return {"relayed": relayed, "distorted": distorted}


def eval_propagation(
    response: str, agent_interactions: List[Any], config: Any
) -> Dict[str, Any]:
    """멀티에이전트 조율에서 정보 전파 충실도를 평가한다.

    SPEC-009 REQ-3: ``agent_interactions``의 각 홉이 "facts_relayed"/"distorted_facts"
    같은 구조화 필드로 원본 fact 전파 여부를 직접 표명하면 이를 우선 대조한다
    (``signal_source="structured"``). 구조화 필드가 없으면 기존 텍스트 매칭
    (``_fact_in_text``) + 부정어 탐지 윈도우 방식으로 폴백한다(``signal_source="text_fallback"``
    — 하위호환, agent_interactions에 구조화 필드가 없으면 기존 동작과 100% 동일).

    Args:
        response: 에이전트 응답 문자열.
        agent_interactions: 에이전트 상호작용 리스트. 구조화 모드를 쓰려면 각 항목에
            "facts_relayed"(List[str])·선택적으로 "distorted_facts"(List[str])를 담는다.
        config: PropagationConfig 인스턴스.

    Returns:
        {fidelity_score, facts_propagated, facts_lost, propagation_rate, distortion_detected,
         signal_source}
    """
    key_facts = getattr(config, "key_facts", []) or []
    check_in_response = bool(getattr(config, "check_in_response", True))
    check_in_tool_calls = getattr(config, "check_in_tool_calls", False)
    penalize_distortion = getattr(config, "penalize_distortion", True)
    similarity_threshold = float(getattr(config, "similarity_threshold", 0.7))
    source_agent = str(getattr(config, "source_agent", "") or "")

    if not key_facts:
        # key_facts 미설정 → 측정 불가, None 반환으로 Gate F 집계에서 제외
        # (빈 key_facts로 fidelity_score=1.0이 Gate F를 무상으로 상향하던 문제 방지)
        return None  # type: ignore[return-value]

    # SPEC-009 REQ-3: 구조화 신호 우선 판정
    _structured_prop = _propagation_structured_signal(agent_interactions, key_facts)
    signal_source = "structured" if _structured_prop is not None else "text_fallback"

    response_lower = response.lower() if response else ""

    def _fact_in_text(fact: str, text: str) -> bool:
        fl = fact.lower()
        if fl in text:
            return True
        if similarity_threshold < 1.0:
            tokens = fl.split()
            # F-I: 분모를 len(tokens) 전체로 쓰면 len < 2 단어("I", "a")가 분자에서는 제외되고
            # 분모에는 포함되어 match ratio가 과소 계산됨. 예: "I went" → "went" in text면
            # matched = 1/2 = 0.5 < 0.7 → 미발견 판정 (오류).
            # 분모도 len >= 2 토큰만 기준으로 계산.
            valid_tokens = [t for t in tokens if len(t) >= 2]
            if valid_tokens:
                matched = sum(1 for t in valid_tokens if t in text) / len(valid_tokens)
                return matched >= similarity_threshold
        return False

    facts_propagated: List[str] = []
    facts_lost: List[str] = []

    if _structured_prop is not None:
        # SPEC-009 REQ-3: 홉이 명시한 구조화 relay 신호를 그대로 채택 — 텍스트 매칭 생략
        for fact in key_facts:
            if fact in _structured_prop["relayed"]:
                facts_propagated.append(fact)
            else:
                facts_lost.append(fact)
    else:
        for fact in key_facts:
            found = check_in_response and _fact_in_text(fact, response_lower)

            if not found and check_in_tool_calls:
                for interaction in (agent_interactions or []):
                    if isinstance(interaction, dict):
                        content = str(interaction.get("content", "")).lower()
                        if _fact_in_text(fact, content):
                            found = True
                            break

            if found:
                facts_propagated.append(fact)
            else:
                facts_lost.append(fact)

    propagation_rate = len(facts_propagated) / len(key_facts) if key_facts else 1.0

    distortion_detected = False
    if _structured_prop is not None:
        # SPEC-009 REQ-3: 홉이 명시한 distorted_facts로 직접 판정 — 부정어 탐지 윈도우 생략
        if penalize_distortion:
            distortion_detected = any(f in _structured_prop["distorted"] for f in facts_propagated)
    else:
        # Distortion: if fact appears but with negation nearby
        # F-B: 단어 경계 regex 적용 — 기존 substring `in` 검사는 "not" in "note", "no" in "another" 등
        # 거짓 양성을 유발해 정상 문장도 왜곡으로 판정하는 버그가 있었음
        import re as _re_distortion
        _NEGATION_PAT = _re_distortion.compile(
            r'\b(?:not|no|never|false|incorrect|wrong)\b|(?:아니|없)'
        )
        if penalize_distortion:
            for fact in facts_propagated:
                fact_lower = fact.lower()
                pos = response_lower.find(fact_lower)
                if pos < 0:
                    # F-R: fuzzy match로 발견된 fact는 exact find가 실패(pos=-1)하므로
                    # distortion window를 구성할 위치를 찾지 못해 negation 탐지가 스킵되었음.
                    # fact의 대표 토큰(len≥2) 첫 번째 위치로 window를 근사 계산해 false negative 방지.
                    _ftokens = [t for t in fact_lower.split() if len(t) >= 2]
                    if _ftokens:
                        pos = response_lower.find(_ftokens[0])
                if pos >= 0:  # Fix4: pos > 0 → pos >= 0 (응답 첫 위치 왜곡 감지 누락 수정)
                    window = response_lower[max(0, pos - 30):pos + len(fact_lower) + 30]
                    if _NEGATION_PAT.search(window):
                        distortion_detected = True
                        break

    fidelity_score = propagation_rate * (0.8 if distortion_detected else 1.0)

    return {
        "fidelity_score": round(fidelity_score, 4),
        "facts_propagated": facts_propagated,
        "facts_lost": facts_lost,
        "propagation_rate": round(propagation_rate, 4),
        "distortion_detected": distortion_detected,
        "source_agent": source_agent,
        "signal_source": signal_source,
    }


def eval_role_adherence(
    tool_calls: List[Any], response: str, config: Any
) -> Dict[str, Any]:
    """에이전트 행동이 선언된 역할에 부합하는지 평가한다.

    SPEC-009 REQ-2: ``tool_calls``에서 도구 식별자를 추출할 수 있으면(``tool_names``
    비어있지 않음) ``allowed_tools``/``forbidden_tools``와의 직접 문자열 비교(식별자
    비교이므로 키워드 오탐 위험 없음)만으로 판정하고, 텍스트 기반 액션 키워드
    (``forbidden_action_keywords``/``allowed_action_keywords``) 매칭은 건너뛴다
    (``signal_source="structured"``). ``tool_calls``에서 도구 식별자를 전혀 추출하지
    못하면 기존과 동일하게 키워드 매칭으로 폴백한다(``signal_source="text_fallback"``
    — 하위호환, tool_calls가 비어있으면 기존 동작과 100% 동일).

    Args:
        tool_calls: 도구 호출 리스트.
        response: 에이전트 응답 문자열.
        config: AgentRoleConfig 인스턴스.

    Returns:
        {role_compliance_score, role_violations, misused_tools, role_name, violation_count,
         signal_source}
    """
    tool_names: List[str] = []
    for tc in (tool_calls or []):
        if isinstance(tc, dict):
            name = tc.get("name") or tc.get("tool") or tc.get("function", {}).get("name", "")
        elif hasattr(tc, "name"):
            name = getattr(tc, "name", "")
        else:
            name = str(tc)
        if name:
            tool_names.append(name)

    # SPEC-009 REQ-2: tool_calls에서 도구 식별자를 얻었으면 구조화 모드(직접 식별자 비교),
    # 얻지 못했으면(도구 미사용/이름 없음) 텍스트 키워드 매칭으로 폴백
    signal_source = "structured" if tool_names else "text_fallback"

    role_violations: List[str] = []
    misused_tools: List[str] = []

    # Check forbidden tools
    for t in tool_names:
        if config.forbidden_tools and t in config.forbidden_tools:
            role_violations.append(f"forbidden_tool:{t}")
            misused_tools.append(t)

    # Check allowed tools (if specified, only these are permitted)
    if config.allowed_tools and config.check_tool_role_alignment:
        for t in tool_names:
            if t not in config.allowed_tools and t not in misused_tools:
                role_violations.append(f"out_of_role_tool:{t}")
                misused_tools.append(t)

    # F-J: substring 비교 → 단어 경계 regex.
    # ASCII 키워드는 \b 경계 적용 — "del" in "model", "write" in "writer" 등 거짓 양성 방지.
    # 한글/CJK 키워드는 단어 경계 개념이 없으므로 substring 유지 (_cr_marker_match와 동일 패턴).
    def _kw_match(kw: str, text: str) -> bool:
        kl = kw.lower()
        if any(ord(c) > 127 for c in kl):
            return kl in text
        try:
            return bool(re.search(r'\b' + re.escape(kl) + r'\b', text))
        except Exception:
            return kl in text

    # SPEC-009 REQ-2: 텍스트 기반 액션 키워드 매칭은 tool_calls에서 도구 식별자를
    # 얻지 못했을 때(text_fallback)만 수행 — 도구명이 있으면 그 식별자 비교로 충분하고
    # 키워드 오탐(false positive) 위험을 감수할 필요가 없다.
    missing_required: List[str] = []
    if signal_source == "text_fallback":
        # Check forbidden action keywords in response
        response_lower = (response or "").lower()
        for kw in (config.forbidden_action_keywords or []):
            if _kw_match(kw, response_lower):
                role_violations.append(f"forbidden_keyword:{kw}")

        # Check required action keywords (at least one must appear in response)
        allowed_kws = list(config.allowed_action_keywords or [])
        if allowed_kws:
            found_required = any(_kw_match(kw, response_lower) for kw in allowed_kws)
            if not found_required:
                role_violations.append("missing_required_keyword")
                missing_required = allowed_kws

    # 실질적인 검사 항목이 하나도 없으면 None 반환 → Gate F 집계 제외
    # eval_propagation(key_facts=[]), eval_explainability(checks={})와 동일 패턴:
    # allowed_tools/forbidden_tools/keywords 모두 비어있으면 위반 탐지 불가 → score=1.0이 무의미
    _has_checks = bool(
        config.forbidden_tools
        or (config.allowed_tools and config.check_tool_role_alignment)
        or (signal_source == "text_fallback"
            and (config.forbidden_action_keywords or config.allowed_action_keywords))
    )
    if not _has_checks:
        return None  # type: ignore[return-value]

    penalty = len(role_violations) * config.role_violation_penalty
    role_compliance_score = max(0.0, 1.0 - penalty)

    return {
        "role_compliance_score": round(role_compliance_score, 4),
        "role_violations": role_violations,
        "misused_tools": misused_tools,
        "role_name": config.role_name,
        "violation_count": len(role_violations),
        "missing_required_keywords": missing_required,
        "signal_source": signal_source,
    }


def eval_conflict_resolution(
    response: str, agent_interactions: List[Any], config: Any
) -> Dict[str, Any]:
    """멀티에이전트 충돌 감지 및 해결 품질을 평가한다.

    Args:
        response: 에이전트 응답 문자열.
        agent_interactions: 에이전트 상호작용 리스트.
        config: ConflictResolutionConfig 인스턴스.

    Returns:
        {resolution_score, conflicts_detected, conflicts_resolved, unresolved_conflicts,
         escalation_present, resolution_method}
    """
    import re as _re_cr

    def _cr_marker_match(marker: str, text: str) -> bool:
        """단어 경계를 고려한 마커 탐지.
        ASCII 마커는 \\b 경계를 적용해 "resolved" in "unresolved",
        "agreed" in "disagreed", "human" in "humanitarian" 등 거짓 양성을 방지한다.
        한글/CJK 마커는 단어 경계 개념이 없으므로 substring 매칭을 유지한다.
        """
        m_low = marker.lower()
        if any(ord(c) > 127 for c in m_low):
            return m_low in text
        try:
            return bool(_re_cr.search(r'\b' + _re_cr.escape(m_low) + r'\b', text))
        except Exception:
            return m_low in text

    response_lower = (response or "").lower()

    # Detect conflicts in agent interactions
    conflicts_detected = 0
    for interaction in (agent_interactions or []):
        _ic = ""
        if isinstance(interaction, dict):
            _ic = str(interaction.get("content", "")).lower()
        elif hasattr(interaction, "content"):
            _ic = str(getattr(interaction, "content", "")).lower()
        # F-P: conflict_markers에도 _cr_marker_match 적용.
        # resolution_markers는 이미 _cr_marker_match를 쓰는데 conflict_markers만 substring 비교를
        # 사용해 "conflict" in "nonconflict", "disagree" in "disagreeable" 등 거짓 양성이 발생했음.
        if any(_cr_marker_match(m, _ic) for m in config.conflict_markers):
            conflicts_detected += 1

    # Fix5: response 충돌 마커는 interactions가 없을 때만 fallback으로 사용
    # (이전: interactions + response 합산 → 해결 응답이 충돌 언급 시 이중 카운팅)
    response_conflicts = sum(
        1 for m in config.conflict_markers if _cr_marker_match(m, response_lower)
    )
    if agent_interactions:
        total_conflicts = conflicts_detected
    else:
        # interactions 없음 — 응답 텍스트 스캔으로 폴백
        total_conflicts = response_conflicts

    # Detect resolutions in response
    # F-D: substring 비교로 "resolved" in "unresolved", "agreed" in "disagreed",
    # "decided" in "undecided" 등이 거짓 양성 → 단어 경계 매칭으로 수정
    conflicts_resolved = sum(
        1 for m in config.resolution_markers if _cr_marker_match(m, response_lower)
    )
    conflicts_resolved = min(conflicts_resolved, total_conflicts)

    unresolved = max(0, total_conflicts - conflicts_resolved)
    check_quality = bool(getattr(config, "check_resolution_quality", True))
    require_explanation = bool(getattr(config, "require_explanation", False))

    penalty = unresolved * config.unresolved_penalty
    resolution_score = max(0.0, 1.0 - penalty)

    # Escalation check (only when quality checking is enabled)
    _check_penalty = getattr(config, "check_penalty", 0.1)
    escalation_present = False
    if check_quality and config.expect_escalation_on_fail and unresolved > 0:
        # F-E: "human" in "humanitarian"/"inhuman"/"subhuman" 거짓 양성 방지 → 단어 경계 적용
        esc_markers = ["escalate", "escalation", "human", "supervisor", "에스컬레이션", "상위"]
        escalation_present = any(_cr_marker_match(m, response_lower) for m in esc_markers)
        if not escalation_present:
            resolution_score = max(0.0, resolution_score - _check_penalty)

    # Explanation check: resolution should include reasoning
    has_explanation = False
    if require_explanation and conflicts_resolved > 0:
        # F-F: "since" in "sincerely", "reason" in "reasoning" 거짓 양성 방지 → 단어 경계 적용
        explanation_markers = [
            "because", "since", "due to", "reason", "therefore", "as a result",
            "왜냐하면", "때문에", "따라서", "결과로",
        ]
        has_explanation = any(_cr_marker_match(m, response_lower) for m in explanation_markers)
        if not has_explanation:
            resolution_score = max(0.0, resolution_score - _check_penalty)

    return {
        "resolution_score": round(resolution_score, 4),
        "conflicts_detected": total_conflicts,
        "conflicts_resolved": conflicts_resolved,
        "unresolved_conflicts": unresolved,
        "escalation_present": escalation_present,
        "resolution_method": "marker_based",
        "has_explanation": has_explanation,
    }
