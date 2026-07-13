"""
agent_evaluator.gates.gate_f_multiagent.configs
==================================================
Gate F(Multi-Agent Coordination) Harness Config 데이터클래스 4종.

SPEC-000 Commit 1: agent_evaluator/decorators.py에서 그대로 이관(로직 변경 없음).
decorators.py는 이 모듈을 re-export하여 하위호환을 유지한다
(``from agent_evaluator import ConsensusConfig`` 등 기존 import 경로 그대로 동작).
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ConsensusConfig:
    """다중 에이전트 합의 품질 측정 설정.

    ``batch_eval`` 과 함께 사용할 때 가장 효과적이다. 단일 ``agent_eval`` 에서는
    응답 하나만 평가하므로 consensus_score 는 항상 1.0 이 된다.

    Example::

        @batch_eval(monitor, task_type="multi_agent",
                    consensus=ConsensusConfig(consensus_method="weighted",
                                             agent_weights={"expert": 3.0}))
        def ensemble_agent(questions, ground_truths=None): ...
    """
    consensus_method: str = "majority"   # "majority" | "weighted" | "unanimity"
    agent_weights: dict[str, float] = dataclasses.field(default_factory=dict)
    similarity_threshold: float = 0.7
    select_consensus_response: bool = False

    def __post_init__(self) -> None:
        import warnings as _w
        # F-4: similarity_threshold <= 0 → matched >= 0.0 이 항상 True → 합의 측정 무력화
        # F-4: similarity_threshold > 1.0 → 완전 일치(sim=1.0)도 agree 불가 → 항상 0.0
        if not (0.0 < self.similarity_threshold <= 1.0):
            _w.warn(
                f"ConsensusConfig: similarity_threshold={self.similarity_threshold} 은 "
                f"(0.0, 1.0] 범위를 벗어납니다. "
                f"≤0이면 sim=0.0(완전 불일치)도 동의로 처리되어 합의 측정이 무력화되고, "
                f">1.0이면 완전 일치(sim=1.0)도 동의 불가로 처리되어 항상 0.0이 반환됩니다. "
                f"기본값 0.7로 보정됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.similarity_threshold = 0.7
        # F-4: agent_weights에 음수 값 → weighted 합산 시 _w_total이 0 이하 → majority 폴백
        _neg_weights = {k: v for k, v in (self.agent_weights or {}).items() if v < 0}
        if _neg_weights:
            _w.warn(
                f"ConsensusConfig: agent_weights에 음수 값이 있습니다: {_neg_weights}. "
                f"음수 가중치는 weighted 합산 시 _w_total이 0 이하가 되어 majority 폴백을 유발합니다. "
                f"가중치는 양수 값(예: 1.0=기본, 3.0=고신뢰)으로 설정해야 합니다.",
                UserWarning,
                stacklevel=2,
            )
        # F-G: consensus_method 유효값 검증 — 지원되지 않는 값은 majority로 폴백되지만
        # eval_consensus 반환 dict에 입력값이 그대로 노출되어 사용자가 오동작을 인지하기 어려움
        _valid_methods = {"majority", "weighted", "unanimity"}
        if self.consensus_method not in _valid_methods:
            _w.warn(
                f"ConsensusConfig: consensus_method={self.consensus_method!r}은 지원하지 않는 값입니다. "
                f"지원 값: {sorted(_valid_methods)}. "
                f"'majority'로 보정됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.consensus_method = "majority"
        # F-C: consensus_method='weighted'이지만 agent_weights가 비어 있으면
        # eval_consensus의 `elif method == "weighted" and agent_weights:` 조건이 False가 되어
        # 실제로는 majority 로직이 적용되고 반환 dict의 method 키만 'weighted'로 표시되는 불일치 발생
        if self.consensus_method == "weighted" and not self.agent_weights:
            _w.warn(
                "ConsensusConfig: consensus_method='weighted'이지만 agent_weights={}입니다. "
                "가중치가 없으면 majority 방식으로 폴백되어 가중 합의 측정이 동작하지 않습니다. "
                "agent_weights={'에이전트명': 가중치} 형식으로 설정하세요. "
                "예: agent_weights={'expert': 3.0, 'base': 1.0}",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class PropagationConfig:
    """멀티에이전트 정보 전파 충실도 측정 설정 (Harness F — Multi-Agent Coordination).

    Example::

        @agent_eval(monitor, task_type="multi_agent",
                    propagation=PropagationConfig(key_facts=["deadline: 2026-04-30", "budget: 10M"]))
        def agent(question, ground_truth=""): ...
    """
    source_agent: str = ""
    key_facts: list[str] = dataclasses.field(default_factory=list)
    check_in_response: bool = True
    check_in_tool_calls: bool = False
    similarity_threshold: float = 0.7
    penalize_distortion: bool = True

    def __post_init__(self) -> None:
        import warnings as _w
        # F-5: similarity_threshold <= 0 → _fact_in_text에서 matched >= 0.0이 항상 True
        # → 무관한 응답도 모든 key_fact가 "전파됨"으로 처리 → fidelity 항상 1.0
        # F-5: similarity_threshold > 1.0 → 퍼지 매칭 불가 (exact match만 동작)
        # → 구성 의도와 다른 동작 발생 가능
        if not (0.0 < self.similarity_threshold <= 1.0):
            _w.warn(
                f"PropagationConfig: similarity_threshold={self.similarity_threshold} 은 "
                f"(0.0, 1.0] 범위를 벗어납니다. "
                f"=0이면 matched >= 0.0이 항상 True로 모든 key_fact가 '전파됨'으로 처리되고, "
                f">1.0이면 퍼지 매칭이 비활성화되어 정확 일치만 판정됩니다. "
                f"기본값 0.7로 보정됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.similarity_threshold = 0.7


@dataclasses.dataclass
class AgentRoleConfig:
    """멀티에이전트 역할 준수 측정 설정 (Harness F — Multi-Agent Coordination).

    Example::

        @agent_eval(monitor, task_type="multi_agent",
                    agent_role=AgentRoleConfig(role_name="researcher",
                                               allowed_tools=["search", "read"],
                                               forbidden_tools=["write", "delete"]))
        def agent(question, ground_truth=""): ...
    """
    role_name: str = ""
    allowed_tools: list[str] = dataclasses.field(default_factory=list)
    forbidden_tools: list[str] = dataclasses.field(default_factory=list)
    allowed_action_keywords: list[str] = dataclasses.field(default_factory=list)
    forbidden_action_keywords: list[str] = dataclasses.field(default_factory=list)
    check_tool_role_alignment: bool = True
    role_violation_penalty: float = 0.3

    def __post_init__(self) -> None:
        import warnings as _w
        # F-1: role_violation_penalty <= 0 → penalty = count × (≤0) ≤ 0
        # → role_compliance_score = max(0, 1.0 - 음수) > 1.0 → Gate F 집계 왜곡
        # =0이면 위반이 있어도 항상 1.0 → 역할 준수 검사 비활성화
        if self.role_violation_penalty <= 0:
            _w.warn(
                f"AgentRoleConfig: role_violation_penalty={self.role_violation_penalty} ≤ 0 이므로 "
                f"기본값 0.3으로 보정됩니다. "
                f"음수 penalty는 role_compliance_score > 1.0을 만들어 Gate F 집계를 왜곡하고, "
                f"=0이면 역할 위반이 감지되어도 score가 항상 1.0이 됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.role_violation_penalty = 0.3
        # F-Q: allowed_tools/forbidden_tools 교집합 경고 — ScopeConfig와 동일 패턴.
        # 같은 도구가 양 목록에 있으면 eval_role_adherence에서 forbidden 우선 적용되지만
        # 경고가 없어 사용자가 의도와 다른 동작을 인지하지 못함.
        if self.allowed_tools is None:
            self.allowed_tools = []
        if self.forbidden_tools is None:
            self.forbidden_tools = []
        _overlap_rf = set(self.allowed_tools) & set(self.forbidden_tools)
        if _overlap_rf:
            _w.warn(
                f"AgentRoleConfig: tools appear in both allowed_tools and forbidden_tools: "
                f"{sorted(_overlap_rf)}. They will be treated as forbidden.",
                UserWarning,
                stacklevel=2,
            )


@dataclasses.dataclass
class ConflictResolutionConfig:
    """멀티에이전트 충돌 감지 및 해결 품질 측정 설정 (Harness F — Multi-Agent Coordination).

    Example::

        @agent_eval(monitor, task_type="multi_agent",
                    conflict_resolution=ConflictResolutionConfig(
                        expect_escalation_on_fail=True))
        def agent(question, ground_truth=""): ...
    """
    conflict_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "disagree", "conflict", "contradiction", "inconsistent", "반대", "충돌", "모순"
    ])
    resolution_markers: list[str] = dataclasses.field(default_factory=lambda: [
        "resolved", "consensus", "agreed", "decided", "해결", "합의", "결정"
    ])
    check_resolution_quality: bool = True
    require_explanation: bool = False
    unresolved_penalty: float = 0.5
    expect_escalation_on_fail: bool = False
    check_penalty: float = 0.1  # escalation 미존재·explanation 미제공 시 각각 적용되는 감점

    def __post_init__(self) -> None:
        import warnings as _w
        # F-2: unresolved_penalty <= 0 → penalty = count × (≤0) ≤ 0
        # → resolution_score = max(0, 1.0 - 음수) > 1.0 → Gate F 집계 왜곡
        # =0이면 미해결 충돌이 있어도 score 항상 1.0 → 충돌 해결 검사 비활성화
        if self.unresolved_penalty <= 0:
            _w.warn(
                f"ConflictResolutionConfig: unresolved_penalty={self.unresolved_penalty} ≤ 0 이므로 "
                f"기본값 0.5로 보정됩니다. "
                f"음수 penalty는 resolution_score > 1.0을 만들어 Gate F 집계를 왜곡하고, "
                f"=0이면 미해결 충돌이 있어도 score가 항상 1.0이 됩니다.",
                UserWarning,
                stacklevel=2,
            )
            self.unresolved_penalty = 0.5
        # F-3: check_penalty < 0 → escalation·explanation 부재 시 score가 오히려 올라감
        # expect_escalation_on_fail=True 또는 require_explanation=True 설정 시 의도와 정반대 동작
        if self.check_penalty < 0:
            _w.warn(
                f"ConflictResolutionConfig: check_penalty={self.check_penalty} < 0 이므로 "
                f"기본값 0.1로 보정됩니다. "
                f"음수 check_penalty는 escalation·explanation 부재 시 score를 차감하는 대신 "
                f"올려 판정을 역전시킵니다.",
                UserWarning,
                stacklevel=2,
            )
            self.check_penalty = 0.1
