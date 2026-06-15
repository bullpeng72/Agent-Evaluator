"""
tests/test_gate_f_bugs.py
=========================
Gate F (Multi-Agent Coordination) 버그 수정 검증 테스트.

F-J: eval_role_adherence — forbidden/allowed_action_keywords substring 거짓 양성 수정
F-P: eval_conflict_resolution — conflict_markers에 _cr_marker_match 적용 (resolution_markers와 일관성)
F-Q: AgentRoleConfig.__post_init__ — allowed_tools/forbidden_tools 교집합 경고 누락
F-R: eval_propagation — fuzzy match 발견 fact의 distortion 체크 skip (false negative)
"""
import warnings
import pytest

from agent_evaluator.helpers.taskresult_helpers import (
    eval_role_adherence,
    eval_conflict_resolution,
    eval_propagation,
)
from agent_evaluator.decorators import AgentRoleConfig, ConflictResolutionConfig, PropagationConfig


# ============================================================================
# F-J: eval_role_adherence — forbidden/allowed_action_keywords 단어 경계 매칭
# ============================================================================

class TestEvalRoleAdherenceKeywordBoundary:
    """F-J: keyword 검사가 단어 경계를 사용하는지 검증."""

    # ── forbidden_action_keywords ──────────────────────────────────────────

    def test_forbidden_keyword_exact_match_triggers_violation(self):
        """forbidden 키워드가 응답에 정확히 있으면 위반으로 판정해야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["delete"],
        )
        result = eval_role_adherence([], "I will delete the file.", config)
        assert result is not None
        assert any("forbidden_keyword:delete" in v for v in result["role_violations"])

    def test_forbidden_keyword_substring_does_not_trigger_violation(self):
        """F-J: 'delete'가 forbidden인데 응답이 'deleted_at' 또는 'model'처럼 substring 포함만 하면
        위반이 아니어야 한다 (수정 전: substring 비교로 거짓 양성 발생)."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["del"],
        )
        # "del" 키워드가 "model", "delivered" 등 다른 단어 내에 포함된 경우
        result = eval_role_adherence([], "The model delivered the result successfully.", config)
        assert result is not None
        violations = [v for v in result["role_violations"] if "forbidden_keyword" in v]
        assert len(violations) == 0, (
            f"F-J 버그: 'del'이 'model'/'delivered' 내 substring임에도 거짓 양성 위반 감지: {violations}"
        )

    def test_forbidden_keyword_word_boundary_triggers(self):
        """단어 경계가 있는 경우 forbidden 키워드가 정상 감지되어야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["write"],
        )
        result = eval_role_adherence([], "I will write the report to disk.", config)
        assert result is not None
        assert any("forbidden_keyword:write" in v for v in result["role_violations"])

    def test_forbidden_keyword_no_false_positive_writer(self):
        """'write'가 forbidden인데 'writer'만 언급하면 위반이 아니어야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["write"],
        )
        result = eval_role_adherence([], "The technical writer reviewed the document.", config)
        assert result is not None
        violations = [v for v in result["role_violations"] if "forbidden_keyword" in v]
        assert len(violations) == 0, (
            f"F-J 버그: 'write'가 'writer' 내 substring임에도 거짓 양성: {violations}"
        )

    def test_forbidden_keyword_korean_uses_substring(self):
        """한글 키워드는 단어 경계 개념이 없으므로 substring으로 탐지해야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["삭제"],
        )
        result = eval_role_adherence([], "파일을 삭제했습니다.", config)
        assert result is not None
        assert any("forbidden_keyword:삭제" in v for v in result["role_violations"])

    # ── allowed_action_keywords ────────────────────────────────────────────

    def test_allowed_keyword_exact_match_passes(self):
        """allowed 키워드가 응답에 정확히 있으면 required 키워드 충족으로 통과해야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            allowed_action_keywords=["search"],
        )
        result = eval_role_adherence([], "I will search the database for results.", config)
        assert result is not None
        assert "missing_required_keyword" not in result["role_violations"]

    def test_allowed_keyword_no_false_positive_substring(self):
        """F-J: 'search'가 allowed인데 응답에 'research'만 있으면 required 키워드 미충족이어야 한다.
        (수정 전: 'search' in 'research' = True로 거짓 통과)."""
        config = AgentRoleConfig(
            role_name="reader",
            allowed_action_keywords=["search"],
        )
        result = eval_role_adherence([], "The research team analyzed the data carefully.", config)
        assert result is not None
        # 'research'에서 'search'가 substring으로 감지되면 거짓 양성 통과 → 버그
        assert "missing_required_keyword" in result["role_violations"], (
            "F-J 버그: 'search'가 'research' 내 substring임에도 allowed 키워드 충족으로 거짓 통과"
        )

    def test_allowed_keyword_boundary_match_passes(self):
        """'search'가 독립 단어로 있으면 allowed 키워드 충족이어야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            allowed_action_keywords=["search"],
        )
        result = eval_role_adherence([], "I search for the relevant documents.", config)
        assert result is not None
        assert "missing_required_keyword" not in result["role_violations"]

    def test_forbidden_keyword_multiple_english(self):
        """여러 forbidden 키워드 — 경계 있는 것만 위반 감지."""
        config = AgentRoleConfig(
            role_name="reader",
            forbidden_action_keywords=["exec", "drop"],
        )
        # "exec" → "executing"(substring), "drop" → "drop"(독립 단어)
        result = eval_role_adherence(
            [], "I am executing the plan and will drop the constraint.", config
        )
        assert result is not None
        violations = [v for v in result["role_violations"] if "forbidden_keyword" in v]
        # "drop"은 독립 단어 → 위반 1건
        # "exec"는 "executing" 내 substring → 거짓 양성 없어야 함
        assert any("forbidden_keyword:drop" in v for v in violations), "drop은 위반이어야 함"
        assert not any("forbidden_keyword:exec" in v for v in violations), (
            "exec가 'executing' 내 substring임에도 거짓 양성 위반"
        )


# ============================================================================
# F-P: eval_conflict_resolution — conflict_markers 단어 경계 매칭
# ============================================================================

class TestEvalConflictResolutionConflictMarkerBoundary:
    """F-P: conflict_markers가 resolution_markers와 일관되게 단어 경계를 사용하는지 검증."""

    def test_conflict_marker_exact_match_in_interaction(self):
        """conflict 마커가 interaction content에 정확히 있으면 충돌로 감지되어야 한다."""
        config = ConflictResolutionConfig()
        interactions = [{"content": "There is a conflict between the two agents."}]
        result = eval_conflict_resolution("resolved the issue", interactions, config)
        assert result["conflicts_detected"] >= 1

    def test_conflict_marker_no_false_positive_nonconflict(self):
        """F-P: 'conflict' 마커가 있는데 'nonconflict'만 포함된 interaction은 충돌로 감지되면 안 된다.
        (수정 전: 'conflict' in 'nonconflict' = True로 거짓 양성 발생)."""
        config = ConflictResolutionConfig()
        interactions = [{"content": "This is a nonconflict zone for peaceful resolution."}]
        result = eval_conflict_resolution("All is well, agreed.", interactions, config)
        assert result["conflicts_detected"] == 0, (
            f"F-P 버그: 'conflict'가 'nonconflict' 내 substring임에도 충돌 감지: {result}"
        )

    def test_conflict_marker_no_false_positive_disagree_substring(self):
        """'disagree' 마커 — 'disagreeable'만 있는 경우 충돌 아님."""
        config = ConflictResolutionConfig(conflict_markers=["disagree"])
        interactions = [{"content": "The task was disagreeable but completed."}]
        result = eval_conflict_resolution("Task completed and agreed.", interactions, config)
        assert result["conflicts_detected"] == 0, (
            f"F-P 버그: 'disagree'가 'disagreeable' 내 substring임에도 충돌 감지: {result}"
        )

    def test_conflict_marker_no_false_positive_in_response_fallback(self):
        """interactions가 없을 때 response 텍스트 fallback에서도 단어 경계가 적용되어야 한다."""
        config = ConflictResolutionConfig(conflict_markers=["conflict"])
        # interactions 없음 → response 텍스트 fallback
        result = eval_conflict_resolution(
            "The preconflict analysis showed no issues. Agreed on the decision.",
            [],
            config,
        )
        assert result["conflicts_detected"] == 0, (
            f"F-P 버그: 'conflict'가 'preconflict' 내 substring임에도 response fallback에서 충돌 감지: {result}"
        )

    def test_conflict_marker_detects_standalone_word_in_response_fallback(self):
        """interactions 없을 때 response에서 standalone conflict 마커는 정상 감지되어야 한다."""
        config = ConflictResolutionConfig(
            conflict_markers=["conflict"],
            resolution_markers=["resolved"],
        )
        result = eval_conflict_resolution(
            "A conflict occurred but was resolved between agents.",
            [],
            config,
        )
        assert result["conflicts_detected"] >= 1
        assert result["conflicts_resolved"] >= 1

    def test_korean_conflict_marker_still_uses_substring(self):
        """한글 충돌 마커는 단어 경계 없이 substring으로 탐지해야 한다."""
        config = ConflictResolutionConfig(conflict_markers=["충돌"])
        interactions = [{"content": "에이전트 간 충돌이 발생했습니다."}]
        result = eval_conflict_resolution("합의에 도달했습니다.", interactions, config)
        assert result["conflicts_detected"] >= 1

    def test_inconsistent_marker_substring_f_p_regression(self):
        """F-P 회귀 방지: resolution_markers와 conflict_markers 모두 동일한 단어 경계 정책 사용."""
        config = ConflictResolutionConfig(
            conflict_markers=["disagree"],
            resolution_markers=["resolved"],
        )
        interactions = [{"content": "The two teams disagreed on priorities."}]
        result_with_interaction = eval_conflict_resolution(
            "We resolved the issue together.", interactions, config
        )
        # "disagreed" 내 "disagree" substring → 경계 있으면 탐지됨 (disagree가 단어 앞에 위치)
        # 실제로 "disagreed"는 "disagree"로 시작하므로 \bdisagree\b는 match 안 됨
        # → conflicts_detected = 0
        assert result_with_interaction["conflicts_detected"] == 0, (
            f"F-P: 'disagree'가 'disagreed'의 시작부분 — 단어 경계 미적용 시 거짓 양성: {result_with_interaction}"
        )

    def test_conflict_resolution_score_with_no_false_conflict(self):
        """거짓 충돌이 제거되면 score=1.0이 되어야 한다."""
        config = ConflictResolutionConfig(conflict_markers=["conflict"])
        interactions = [{"content": "All processes completed without nonconflict issues."}]
        result = eval_conflict_resolution("agreed and decided.", interactions, config)
        # 충돌 없으므로 score=1.0
        assert result["resolution_score"] == 1.0


# ============================================================================
# 통합: 두 버그 동시 시나리오
# ============================================================================

# ============================================================================
# F-Q: AgentRoleConfig — allowed_tools/forbidden_tools 교집합 경고
# ============================================================================

class TestAgentRoleConfigOverlapWarning:
    """F-Q: allowed_tools와 forbidden_tools 교집합 시 UserWarning 발생 확인."""

    def test_overlap_tools_raises_warning(self):
        """같은 도구가 allowed_tools와 forbidden_tools 모두에 있으면 UserWarning이 발생해야 한다."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            AgentRoleConfig(
                role_name="reader",
                allowed_tools=["search", "read"],
                forbidden_tools=["write", "search"],  # "search" 교집합
            )
        overlap_warns = [w for w in caught if "allowed_tools and forbidden_tools" in str(w.message)]
        assert len(overlap_warns) >= 1, "F-Q 버그: 교집합 도구에 대한 UserWarning이 발생하지 않음"
        assert "search" in str(overlap_warns[0].message)

    def test_no_overlap_no_warning(self):
        """교집합이 없으면 경고가 발생하지 않아야 한다."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            AgentRoleConfig(
                role_name="reader",
                allowed_tools=["search", "read"],
                forbidden_tools=["write", "delete"],
            )
        overlap_warns = [w for w in caught if "allowed_tools and forbidden_tools" in str(w.message)]
        assert len(overlap_warns) == 0, "교집합 없는데 경고 발생"

    def test_none_allowed_tools_normalized(self):
        """allowed_tools=None이 []로 정규화되어 TypeError 없이 처리되어야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            allowed_tools=None,  # type: ignore[arg-type]
            forbidden_tools=["write"],
        )
        assert config.allowed_tools == []

    def test_none_forbidden_tools_normalized(self):
        """forbidden_tools=None이 []로 정규화되어 TypeError 없이 처리되어야 한다."""
        config = AgentRoleConfig(
            role_name="reader",
            allowed_tools=["read"],
            forbidden_tools=None,  # type: ignore[arg-type]
        )
        assert config.forbidden_tools == []

    def test_overlap_tool_treated_as_forbidden(self):
        """교집합 도구는 eval_role_adherence에서 forbidden으로 처리되어야 한다."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            config = AgentRoleConfig(
                role_name="reader",
                allowed_tools=["search", "write"],
                forbidden_tools=["write"],  # "write" 교집합
            )
        # "write" 도구를 사용한 에이전트 → forbidden 위반
        result = eval_role_adherence(
            [{"name": "write"}], "I will write the file.", config
        )
        assert result is not None
        assert any("forbidden_tool:write" in v for v in result["role_violations"])


# ============================================================================
# F-R: eval_propagation — fuzzy match fact의 distortion 체크 false negative
# ============================================================================

class TestEvalPropagationFuzzyDistortion:
    """F-R: fuzzy match로 발견된 fact에도 distortion이 탐지되어야 한다."""

    def test_exact_match_fact_distortion_detected(self):
        """exact match로 발견된 fact + negation → distortion 감지 (기본 동작 확인)."""
        config = PropagationConfig(key_facts=["deadline 2026-04-30"])
        result = eval_propagation(
            "The deadline 2026-04-30 was not confirmed.", [], config
        )
        assert result is not None
        assert result["distortion_detected"] is True, "exact match + negation → distortion 미감지"

    def test_fuzzy_match_fact_distortion_detected(self):
        """F-R: fuzzy match로만 발견된 fact + negation → distortion이 감지되어야 한다.
        (수정 전: find(fact_lower)=-1 → distortion window 미구성 → distortion_detected=False)."""
        # "deadline april thirty" → 토큰 fuzzy match로 발견되지만 exact find는 실패
        config = PropagationConfig(
            key_facts=["deadline april thirty"],
            similarity_threshold=0.6,
        )
        # "deadline" 앞에 "not" → distortion이어야 함
        result = eval_propagation(
            "The deadline is not in april, thirty days remain.", [], config
        )
        assert result is not None
        # fact가 fuzzy로 발견됨
        assert "deadline april thirty" in result["facts_propagated"], (
            "fuzzy match로 fact가 발견되지 않음 — 전제 조건 실패"
        )
        assert result["distortion_detected"] is True, (
            "F-R 버그: fuzzy match fact + negation인데 distortion이 감지되지 않음"
        )

    def test_fuzzy_match_fact_no_distortion(self):
        """fuzzy match로 발견된 fact에 negation 없음 → distortion 미감지 (정상 동작)."""
        config = PropagationConfig(
            key_facts=["deadline april thirty"],
            similarity_threshold=0.6,
        )
        result = eval_propagation(
            "The deadline in april is thirty days from now. Confirmed.", [], config
        )
        assert result is not None
        if "deadline april thirty" in result["facts_propagated"]:
            assert result["distortion_detected"] is False, (
                "negation 없는 fuzzy match fact인데 distortion이 잘못 감지됨"
            )

    def test_fidelity_score_reduced_on_fuzzy_distortion(self):
        """F-R: distortion이 감지되면 fidelity_score=0.8×propagation_rate (< 1.0)이어야 한다."""
        config = PropagationConfig(
            key_facts=["budget ten million"],
            similarity_threshold=0.6,
        )
        # "budget" 주변에 "not" → fuzzy match + distortion
        result = eval_propagation(
            "The budget is not ten million anymore.", [], config
        )
        assert result is not None
        if result.get("distortion_detected"):
            assert result["fidelity_score"] < 1.0, (
                "distortion 감지됐는데 fidelity_score가 1.0 — penalty 미적용"
            )


# ============================================================================
# 통합: 두 버그 동시 시나리오
# ============================================================================

class TestGateFBugIntegration:
    """F-J + F-P + F-Q + F-R 통합 시나리오."""

    def test_role_and_conflict_no_false_positives_combined(self):
        """역할 키워드와 충돌 마커 모두 단어 경계 정책으로 거짓 양성 없음."""
        role_config = AgentRoleConfig(
            role_name="researcher",
            forbidden_action_keywords=["write"],
        )
        conflict_config = ConflictResolutionConfig(conflict_markers=["conflict"])

        # "writer"는 "write" substring이지만 독립 단어가 아님 → 역할 위반 아님
        role_result = eval_role_adherence(
            [], "The technical writer analyzed the data.", role_config
        )
        assert role_result is not None
        assert all("forbidden_keyword" not in v for v in role_result["role_violations"])

        # "preconflict"는 "conflict" substring이지만 독립 단어가 아님 → 충돌 감지 아님
        conflict_result = eval_conflict_resolution(
            "Preconflict mitigation succeeded. Agreed on next steps.",
            [],
            conflict_config,
        )
        assert conflict_result["conflicts_detected"] == 0
        assert conflict_result["resolution_score"] == 1.0
