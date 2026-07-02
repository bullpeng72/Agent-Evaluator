"""
tests/test_gate_f_structured_signals.py
========================================
SPEC-009: 구조화 신호(agent_interactions/tool_calls) 우선 평가 전환 회귀·기능 테스트.

대상 함수: eval_consensus(REQ-1) · eval_role_adherence(REQ-2) · eval_propagation(REQ-3)

검증 축:
1. 구조화 데이터 부재 시(agent_interactions/tool_calls 미제공) — 기존 텍스트 매칭과
   100% 동일한 결과 + signal_source == "text_fallback" (회귀 방지, 핵심 계약).
2. 구조화 데이터 존재 시 — signal_source == "structured" + 타당한 점수.
3. 워딩만 다르고 의미가 같은 두 응답 세트에서, 구조화 모드가 텍스트 매칭 모드보다
   합의도 판정의 분산이 낮은지(더 안정적인지) 비교(Acceptance 3번째 항목).
"""
import pytest

from agent_evaluator.gates.gate_f_multiagent.evaluators import (
    eval_consensus,
    eval_propagation,
    eval_role_adherence,
)
from agent_evaluator.gates.gate_f_multiagent.configs import (
    AgentRoleConfig,
    ConsensusConfig,
    PropagationConfig,
)


# ============================================================================
# REQ-1: eval_consensus — 구조화 intent/action 필드 우선 사용
# ============================================================================

class TestEvalConsensusStructuredSignal:
    def test_text_fallback_identical_to_legacy_call(self):
        """agent_interactions 미제공 시 signal_source=text_fallback + 기존 로직과 동일 점수."""
        responses = ["The weather is sunny today.", "It is completely different and unrelated."]
        config = ConsensusConfig()

        # 기존 방식(4-positional 호출, agent_interactions 없음)
        legacy = eval_consensus(responses, None, config)
        # 신규 파라미터를 명시적으로 생략(=None)해도 동일해야 함
        explicit_none = eval_consensus(responses, None, config, agent_interactions=None)

        assert legacy["signal_source"] == "text_fallback"
        assert explicit_none["signal_source"] == "text_fallback"
        assert legacy["consensus_score"] == explicit_none["consensus_score"]
        assert legacy["agreement_pairs"] == explicit_none["agreement_pairs"]
        assert legacy["dissenting_agents"] == explicit_none["dissenting_agents"]

    def test_structured_signal_used_when_agent_interactions_complete(self):
        """전 에이전트에 intent/action 구조화 필드가 있으면 structured 모드로 판정."""
        responses = [
            "I think we should launch the product now.",
            "Totally different wording, unrelated meaning here.",
        ]
        names = ["agent_a", "agent_b"]
        interactions = [
            {"agent": "agent_a", "intent": "approve", "action": "launch"},
            {"agent": "agent_b", "intent": "approve", "action": "launch"},
        ]
        config = ConsensusConfig()
        result = eval_consensus(responses, names, config, agent_interactions=interactions)

        assert result["signal_source"] == "structured"
        # 동일 intent/action → 완전 합의 → consensus_score == 1.0
        assert result["consensus_score"] == 1.0
        assert result["agreement_pairs"][0]["agreed"] is True

    def test_structured_signal_disagreement_detected(self):
        """구조화 필드가 다르면(의도 불일치) 텍스트가 비슷해도 불일치로 판정."""
        responses = [
            "We should proceed with the plan.",
            "We should proceed with the plan.",  # 텍스트는 동일
        ]
        names = ["agent_a", "agent_b"]
        interactions = [
            {"agent": "agent_a", "intent": "approve", "action": "proceed"},
            {"agent": "agent_b", "intent": "reject", "action": "halt"},
        ]
        config = ConsensusConfig()
        result = eval_consensus(responses, names, config, agent_interactions=interactions)

        assert result["signal_source"] == "structured"
        assert result["consensus_score"] == 0.0
        assert set(result["dissenting_agents"]) == {"agent_a", "agent_b"}

    def test_partial_structured_data_falls_back_to_text(self):
        """일부 에이전트만 구조화 필드를 제공하면 안전하게 text_fallback으로 전환."""
        responses = ["The launch is approved.", "The launch is approved."]
        names = ["agent_a", "agent_b"]
        interactions = [
            {"agent": "agent_a", "intent": "approve", "action": "launch"},
            # agent_b는 구조화 신호 없음
        ]
        config = ConsensusConfig()
        result = eval_consensus(responses, names, config, agent_interactions=interactions)

        assert result["signal_source"] == "text_fallback"

    def test_wording_sensitivity_lower_variance_under_structured_mode(self):
        """Acceptance: 같은 의미·다른 표현의 두 응답 세트를 비교했을 때, 구조화 모드의
        합의도 판정이 텍스트 매칭 모드보다 표현 차이에 덜 민감(분산이 낮음)해야 한다."""
        config = ConsensusConfig()
        names = ["agent_a", "agent_b"]

        # 의미는 완전히 동일하지만 표현(어휘)이 크게 다른 두 가지 응답 쌍
        wording_variants = [
            ("We approve launching the product immediately.",
             "Green light — ship it right away."),
            ("I agree, let's release it now.",
             "Consensus reached: proceed with the rollout at once."),
            ("Yes, launch now.",
             "Affirmative, we should deploy this without delay."),
        ]

        text_scores = []
        structured_scores = []
        interactions = [
            {"agent": "agent_a", "intent": "approve", "action": "launch"},
            {"agent": "agent_b", "intent": "approve", "action": "launch"},
        ]
        for r_a, r_b in wording_variants:
            text_result = eval_consensus([r_a, r_b], names, config)
            structured_result = eval_consensus([r_a, r_b], names, config, agent_interactions=interactions)
            text_scores.append(text_result["consensus_score"])
            structured_scores.append(structured_result["consensus_score"])

        def _variance(vals):
            mean = sum(vals) / len(vals)
            return sum((v - mean) ** 2 for v in vals) / len(vals)

        # 구조화 모드는 매 케이스 동일 intent/action이므로 분산 0 — 텍스트 모드보다 안정적(<=)
        assert _variance(structured_scores) <= _variance(text_scores)
        # 구조화 모드는 항상 완전 합의(표현과 무관)
        assert all(s == 1.0 for s in structured_scores)


# ============================================================================
# REQ-2: eval_role_adherence — tool_calls 도구명 직접 비교 우선 사용
# ============================================================================

class TestEvalRoleAdherenceStructuredSignal:
    def test_text_fallback_identical_to_legacy_behavior_empty_tool_calls(self):
        """tool_calls=[] (도구 식별자 없음) → signal_source=text_fallback + 기존 키워드 판정 유지."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["delete"],
        )
        result = eval_role_adherence([], "I will delete the file.", config)
        assert result is not None
        assert result["signal_source"] == "text_fallback"
        assert any("forbidden_keyword:delete" in v for v in result["role_violations"])

    def test_structured_signal_used_when_tool_calls_present(self):
        """tool_calls에 도구명이 있으면 signal_source=structured + 식별자 직접 비교로 판정."""
        config = AgentRoleConfig(
            role_name="researcher",
            allowed_tools=["search", "read"],
            forbidden_tools=["delete_file"],
        )
        result = eval_role_adherence(
            [{"name": "delete_file"}], "I searched and deleted the file.", config
        )
        assert result is not None
        assert result["signal_source"] == "structured"
        assert any("forbidden_tool:delete_file" in v for v in result["role_violations"])

    def test_structured_mode_skips_keyword_false_positive(self):
        """tool_calls가 있으면(구조화 모드) 응답 텍스트의 키워드는 무시되어
        거짓 양성(false positive) 위험이 없어야 한다 — REQ-2 핵심 목적."""
        config = AgentRoleConfig(
            role_name="researcher",
            allowed_tools=["search"],
            forbidden_action_keywords=["delete"],  # 텍스트에 "deleted"가 있지만 구조화 모드라 무시되어야 함
        )
        result = eval_role_adherence(
            [{"name": "search"}],
            "I searched and the outdated cache was deleted automatically.",
            config,
        )
        assert result is not None
        assert result["signal_source"] == "structured"
        # 구조화 모드에서는 forbidden_action_keywords 검사를 건너뛰므로 위반 없음
        assert not any("forbidden_keyword" in v for v in result["role_violations"])

    def test_none_tool_calls_treated_as_text_fallback(self):
        """tool_calls=None도 text_fallback으로 정상 폴백해야 한다."""
        config = AgentRoleConfig(role_name="reader", forbidden_action_keywords=["delete"])
        result = eval_role_adherence(None, "I will delete the file.", config)
        assert result is not None
        assert result["signal_source"] == "text_fallback"


# ============================================================================
# REQ-3: eval_propagation — agent_interactions 홉의 구조화 fact 필드 우선 사용
# ============================================================================

class TestEvalPropagationStructuredSignal:
    def test_text_fallback_identical_to_legacy_behavior(self):
        """agent_interactions에 구조화 필드가 없으면 signal_source=text_fallback +
        기존 텍스트 매칭/부정어 탐지 결과와 동일."""
        config = PropagationConfig(key_facts=["deadline 2026-04-30"])
        legacy = eval_propagation("The deadline 2026-04-30 was not confirmed.", [], config)
        with_plain_interactions = eval_propagation(
            "The deadline 2026-04-30 was not confirmed.",
            [{"content": "unrelated chatter"}],
            config,
        )

        assert legacy["signal_source"] == "text_fallback"
        assert with_plain_interactions["signal_source"] == "text_fallback"
        assert legacy["distortion_detected"] is True
        assert legacy["fidelity_score"] == with_plain_interactions["fidelity_score"]
        assert legacy["facts_propagated"] == with_plain_interactions["facts_propagated"]

    def test_structured_signal_used_when_hop_reports_relayed_facts(self):
        """홉이 facts_relayed로 명시하면 signal_source=structured + 그 신호를 직접 채택."""
        config = PropagationConfig(key_facts=["budget: 10M", "deadline: 2026-04-30"])
        interactions = [
            {"agent": "planner", "facts_relayed": ["budget: 10M", "deadline: 2026-04-30"]},
        ]
        result = eval_propagation("irrelevant response text with no facts mentioned", interactions, config)

        assert result["signal_source"] == "structured"
        assert set(result["facts_propagated"]) == {"budget: 10M", "deadline: 2026-04-30"}
        assert result["facts_lost"] == []
        assert result["propagation_rate"] == 1.0

    def test_structured_signal_detects_distortion_via_distorted_facts(self):
        """홉이 distorted_facts를 명시하면 부정어 탐지 없이도 왜곡으로 판정된다."""
        config = PropagationConfig(key_facts=["budget: 10M"])
        interactions = [
            {"agent": "relay", "facts_relayed": ["budget: 10M"], "distorted_facts": ["budget: 10M"]},
        ]
        result = eval_propagation("some unrelated confirmation text", interactions, config)

        assert result["signal_source"] == "structured"
        assert result["distortion_detected"] is True
        assert result["fidelity_score"] < 1.0

    def test_structured_signal_reports_lost_fact_not_relayed(self):
        """홉이 일부 fact만 relay했다고 명시하면 나머지는 facts_lost로 분류된다."""
        config = PropagationConfig(key_facts=["fact_a", "fact_b"])
        interactions = [
            {"agent": "relay", "facts_relayed": ["fact_a"]},
        ]
        result = eval_propagation("response text irrelevant to facts", interactions, config)

        assert result["signal_source"] == "structured"
        assert result["facts_propagated"] == ["fact_a"]
        assert result["facts_lost"] == ["fact_b"]
        assert result["propagation_rate"] == 0.5
