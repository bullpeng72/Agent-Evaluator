"""
agent_evaluator.ontology.mast_taxonomy
=========================================
Phase 4(개선 엔진) — Gate F(Multi-Agent Coordination) RemediationOntology 시드 데이터.

출처: Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein,
Ramchandran, Zaharia, Gonzalez, Stoica. "Why Do Multi-Agent LLM Systems Fail?"
NeurIPS 2025 (Datasets and Benchmarks Track), arXiv:2503.13657v3. MAST(Multi-Agent
System Failure Taxonomy) — 7개 MAS 프레임워크·1642개 실행 트레이스 분석(κ=0.88),
14개 실패모드/3범주. 논문 Figure 1을 원문 그대로 옮겼다(코드·이름·prevalence % 전부
검증됨, 지어내지 않음) — https://arxiv.org/abs/2503.13657.

**이 모듈이 하지 않는 것**: MAST는 사람/LLM 판정자가 트레이스를 사후 분류하기 위한
분류 체계(taxonomy)이지, 자동 탐지기가 아니다. Gate F는 이 14개 모드 중 "지금 이게
발생했다"를 자동으로 판정하지 않는다 — RCA(``agent_evaluator.rca``)가 Gate F를
감지했을 때, 어느 하위 지표가 가장 크게 움직였는지에 따라 "참고할 만한 후보 실패모드
목록"을 사람에게 제시할 뿐이다(HOTL 원칙 — Chapter 2). ``related_gate_f_metric``은
MAST 논문이 정의한 매핑이 아니라 이 SDK가 각 실패모드의 정의를 읽고 붙인 해석적
힌트다 — 참고용이지 근거로 단정하면 안 된다.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class MASTFailureMode:
    code: str                    # 논문의 "1.1" 형식 코드
    category: str                # 3범주 중 하나(MAST_FAILURE_MODES 정의부 참고)
    name: str                    # 논문 원문 명칭
    prevalence_pct: float        # 논문 Figure 1 관측 빈도(%), 1642개 트레이스 기준, 참고용
    description: str
    remediation: str
    # consensus|propagation|role_adherence|conflict_resolution|None — SDK 해석(MAST 원문 매핑 아님)
    related_gate_f_metric: str | None


MAST_FAILURE_MODES: tuple[MASTFailureMode, ...] = (
    # ── 1. System Design Issues (44.2% of observed failures) ──
    MASTFailureMode(
        "1.1", "system_design_issues", "Disobey Task Specification", 11.8,
        "Agent does not follow the requirements or constraints specified in the task.",
        "Restate task constraints more explicitly and repeatedly in each role's system "
        "prompt, and provide completion criteria as a checklist.",
        "role_adherence",
    ),
    MASTFailureMode(
        "1.2", "system_design_issues", "Disobey Role Specification", 1.5,
        "Agent acts outside the role or authority scope assigned to it.",
        "Set AgentRoleConfig's allowed_tools/forbidden_action_keywords more strictly, "
        "and repeatedly emphasize role boundaries in the system prompt.",
        "role_adherence",
    ),
    MASTFailureMode(
        "1.3", "system_design_issues", "Step Repetition", 15.7,
        "Unnecessarily repeats a step that has already been completed (one of the most "
        "frequent failure modes).",
        "Investigate together with Gate B's LoopDetectionConfig — the multi-agent "
        "orchestration layer is likely failing to share 'already completed step' state.",
        None,  # Better investigated cross-referenced with Gate B (loop_detection)
    ),
    MASTFailureMode(
        "1.4", "system_design_issues", "Loss of Conversation History", 2.8,
        "Prior conversation/context information is lost in subsequent steps.",
        "Measure whether key facts actually propagate using PropagationConfig(key_facts), "
        "and review how the orchestration layer passes context.",
        "propagation",
    ),
    MASTFailureMode(
        "1.5", "system_design_issues", "Unaware of Termination Conditions", 12.4,
        "Lacks awareness of when to stop working, so it unnecessarily continues.",
        "Include explicit termination conditions in each agent's prompt, and separately "
        "detect infinite delegation with Gate B's DeadlockConfig (max_delegation_depth, etc).",
        None,  # Better investigated cross-referenced with Gate B (deadlock)
    ),
    # ── 2. Inter-Agent Misalignment (32.3%) ──
    MASTFailureMode(
        "2.1", "inter_agent_misalignment", "Conversation Reset", 2.2,
        "Conversation context is unexpectedly reset, losing prior progress.",
        "Externalize session state (e.g. shared memory) so progress is preserved even "
        "across a conversation reset.",
        "propagation",
    ),
    MASTFailureMode(
        "2.2", "inter_agent_misalignment", "Fail to Ask for Clarification", 6.8,
        "Proceeds arbitrarily in ambiguous situations instead of asking another agent "
        "or the user for clarification.",
        "Lower ConsensusConfig's agreement threshold, or add explicit prompt instructions "
        "to request clarification when ambiguity is detected.",
        "consensus",
    ),
    MASTFailureMode(
        "2.3", "inter_agent_misalignment", "Task Derailment", 7.4,
        "Conversation/work drifts away from the original task toward unrelated directions.",
        "Specify each agent's task scope with AgentRoleConfig, and insert periodic "
        "checkpoints into the orchestration that re-confirm the original goal.",
        "role_adherence",
    ),
    MASTFailureMode(
        "2.4", "inter_agent_misalignment", "Information Withholding", 0.8,
        "Does not share information that another agent needs.",
        "Explicitly measure whether required information propagates using "
        "PropagationConfig(key_facts), and include information sharing in the task "
        "completion criteria.",
        "propagation",
    ),
    MASTFailureMode(
        "2.5", "inter_agent_misalignment", "Ignored Other Agent's Input", 1.9,
        "Ignores another agent's suggestions or correction requests and proceeds solely "
        "on its own judgment.",
        "Measure whether ignored input escalates using "
        "ConflictResolutionConfig(expect_escalation_on_fail), and enforce the consensus "
        "protocol as an explicit step.",
        "conflict_resolution",
    ),
    MASTFailureMode(
        "2.6", "inter_agent_misalignment", "Reasoning-Action Mismatch", 13.2,
        "The conclusion reached during reasoning does not match the action actually taken.",
        "Use ExplainabilityConfig(require_reasoning) to explicitly record reasoning right "
        "before acting, and separately score reasoning-action alignment (cross-investigate "
        "with Gate G).",
        None,  # A single-agent reasoning-action alignment issue — closer to Gate G
               # (explainability) than Gate F
    ),
    # ── 3. Task Verification (23.5%) ──
    MASTFailureMode(
        "3.1", "task_verification", "Premature Termination", 6.2,
        "Terminates early even though the work is not actually complete.",
        "Specify completion criteria with ConflictResolutionConfig/"
        "SubtaskConfig(min_completion_rate), and enforce a checklist verification step "
        "before termination in the orchestration.",
        "conflict_resolution",
    ),
    MASTFailureMode(
        "3.2", "task_verification", "No or Incomplete Verification", 8.2,
        "Verification of the output is either absent or only partially performed.",
        "Explicitly assign a separate agent/step responsible for verifying results "
        "(e.g. a reviewer role), and track verification attempts themselves with "
        "ErrorDiagnosisConfig.",
        "conflict_resolution",
    ),
    MASTFailureMode(
        "3.3", "task_verification", "Incorrect Verification", 9.1,
        "Verification was attempted, but the verification logic/criteria themselves were "
        "wrong, letting an incorrect result pass.",
        "Make verification criteria explicit based on a golden set (§15.4 Spec-Driven), "
        "and have a human periodically sample-audit the verifying agent's judgments "
        "(same principle as LLM Judge calibration).",
        "conflict_resolution",
    ),
)


def mast_failure_modes_for_gate_f_metric(metric: str) -> tuple[MASTFailureMode, ...]:
    """``related_gate_f_metric``이 주어진 지표와 일치하는 MAST 실패모드만 골라 반환한다.

    RCA(``agent_evaluator.rca.diagnose``)가 Gate F를 감지하고 가장 크게 움직인 세부
    지표(예: ``avg_consensus``)를 찾았을 때, 그 지표명에서 접두/접미사를 벗긴 값
    (``consensus``)으로 이 함수를 호출하면 참고할 만한 후보 실패모드 목록을 얻는다.
    """
    return tuple(m for m in MAST_FAILURE_MODES if m.related_gate_f_metric == metric)


def mast_failure_mode_by_code(code: str) -> MASTFailureMode | None:
    for m in MAST_FAILURE_MODES:
        if m.code == code:
            return m
    return None
