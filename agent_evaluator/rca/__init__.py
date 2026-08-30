"""
agent_evaluator.rca
======================
Phase 4(개선 엔진) — Gate 하락 원인진단(RCA) 최소기능.

Media/Harness_Method Chapter 31이 이미 문서화한 3단계 절차(감지→Gate 세부값
원인귀속→관련 이력 교차확인)를 그대로 자동화한다 — 새 RCA 방법론을 발명하지 않는다.
HOTL(사람이 사후 감독) 원칙에 따라 이 모듈은 후보 원인과 근거만 내고, "이게 원인이다"를
단정하지 않는다 — 최종 판단은 QA·거버넌스 담당자의 몫이다.
"""
from __future__ import annotations

from agent_evaluator.rca.diagnose import diagnose
from agent_evaluator.rca.experiment_metadata import ExperimentMetadata, derive_experiment_metadata
from agent_evaluator.rca.experiments import (
    load_experiments,
    recalibrated_delta,
    register_experiment,
    resolve_experiment,
    score_experiments,
)
from agent_evaluator.rca.recommendation_tracking import (
    load_recommendation_outcomes,
    record_recommendation_outcome,
    summarize_recommendation_outcomes,
)
from agent_evaluator.rca.verify import verify_recommendation_outcome

__all__ = [
    "diagnose", "verify_recommendation_outcome",
    "ExperimentMetadata", "derive_experiment_metadata",
    "record_recommendation_outcome", "load_recommendation_outcomes",
    "summarize_recommendation_outcomes",
    "register_experiment", "load_experiments", "score_experiments",
    "resolve_experiment", "recalibrated_delta",
]
