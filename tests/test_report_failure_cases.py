"""
tests/test_report_failure_cases.py
=====================================
P1.1 / P1.2 — 단일 HTML 리포트의 두 개선:

1. 실패/저점 per-task 케이스 테이블(``_build_failure_cases``) — 집계값만 보던
   리포트에 "어떤 태스크가 왜 실패했는지"를 노출한다.
2. Recommendations를 ``rca.diagnose()``의 ``component_shortfalls`` 기반으로
   구체화(``_build_recommendations(..., diagnosis=...)``) + ontology의
   ``COMPONENT_GUIDANCE`` 조치 문구 첨부.
"""
from __future__ import annotations

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.ontology.metric_registry import (
    COMPONENT_GUIDANCE,
    component_guidance_for,
)
from agent_evaluator.reporting.comprehensive_report import (
    _build_executive_summary,
    _build_failure_cases,
    _build_failure_clusters,
    _build_failure_lineage,
    _build_operational_signals,
    _build_recommendations,
    _norm_task_for_case,
    _reason_signature,
    generate_comprehensive_html_report,
)


class _T:
    """가벼운 TaskResult 스텁 — _norm_task_for_case가 getattr로 읽는 필드만."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _mk(task_id, *, success, comp, acc, q="q", r="r", gt="", reason="", errors=None):
    return _T(
        task_id=task_id, task_type="qa", success=success,
        completion_score=comp, accuracy_score=acc,
        question=q, response=r, ground_truth=gt,
        partial_reason=reason, errors=errors or [], llm_judge=None,
        execution_time=1.0,
    )


class TestFailureCasesSection:
    def test_empty_when_no_tasks(self):
        assert _build_failure_cases([]) == ""

    def test_hidden_when_all_healthy(self):
        tasks = [_mk(f"t{i}", success=True, comp=0.95, acc=0.95) for i in range(5)]
        assert _build_failure_cases(tasks) == ""

    def test_failed_tasks_rendered_worst_first(self):
        tasks = [
            _mk("ok", success=True, comp=0.9, acc=0.9),
            _mk("bad", success=False, comp=0.1, acc=0.0, q="서울 인구?", r="모름",
                gt="940만", reason="ground_truth 유사도 낮음"),
            _mk("mid", success=False, comp=0.5, acc=0.4),
        ]
        html = _build_failure_cases(tasks)
        assert 'id="failure-cases"' in html
        assert "Failed Cases" in html
        assert "서울 인구?" in html and "모름" in html
        assert "940만" in html
        assert "ground_truth 유사도 낮음" in html
        # worst first: bad(0.0) 행이 mid(0.4) 행보다 앞
        assert html.index(">bad<") < html.index(">mid<")
        # 통과 태스크는 표에 없음
        assert ">ok<" not in html

    def test_low_scorers_shown_when_no_failures(self):
        tasks = [
            _mk("lo", success=True, comp=0.6, acc=0.55),
            _mk("hi", success=True, comp=0.95, acc=0.95),
        ]
        html = _build_failure_cases(tasks)
        assert "Lowest-scoring Cases" in html
        assert ">lo<" in html
        assert ">hi<" not in html

    def test_limit_and_more_line(self):
        tasks = [_mk(f"f{i}", success=False, comp=0.1, acc=0.1) for i in range(20)]
        html = _build_failure_cases(tasks, limit=5)
        assert "showing 5 of 20" in html
        assert "15 more failed task(s)" in html

    def test_html_escaped(self):
        tasks = [_mk("x", success=False, comp=0.0, acc=0.0, q="<script>alert(1)</script>")]
        html = _build_failure_cases(tasks)
        assert "<script>alert(1)" not in html
        assert "&lt;script&gt;" in html

    def test_included_in_full_report_when_failures(self):
        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(4):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="서울 인구는?",
                response="모르겠습니다" if i < 3 else "약 940만명",
                ground_truth="약 940만명", execution_time=1.0, task_type="qa",
            ))
        html = generate_comprehensive_html_report(m)
        assert 'id="failure-cases"' in html


class TestComponentGuidance:
    def test_direct_key(self):
        assert (component_guidance_for("subtask_completion")
                == COMPONENT_GUIDANCE["subtask_completion"])

    def test_avg_prefix_stripped(self):
        assert component_guidance_for("avg_budget_score") == COMPONENT_GUIDANCE["budget_score"]

    def test_suffix_stripped(self):
        assert component_guidance_for("sla_breach_rate") == COMPONENT_GUIDANCE["sla_breach"]
        assert component_guidance_for("p95_latency_s") == COMPONENT_GUIDANCE["p95_latency"]

    def test_unknown_returns_none(self):
        assert component_guidance_for("totally_made_up_field") is None
        assert component_guidance_for(None) is None


class TestRecommendationsUseDiagnosis:
    def _hg(self, status="warn"):
        return {
            "A": {"score": 0.6, "status": status, "gate": status, "details": {
                "avg_subtask_completion": 0.25, "tcr_pct": 50.0, "avg_accuracy": 0.83,
            }},
        }

    def test_shortfall_component_and_action_rendered(self):
        from agent_evaluator.rca import diagnose
        hg = self._hg()
        diag = diagnose({"extra_metrics": {"harness_groups": hg}})
        html = _build_recommendations(hg, tcr=50.0, acc=83.0, hall_rate=0.0,
                                      latency=1.0, quality_metrics={}, diagnosis=diag)
        assert "Biggest measured shortfalls" in html
        assert "subtask completion" in html
        assert "SubtaskConfig" in html  # COMPONENT_GUIDANCE["subtask_completion"] 문구
        assert "RCA Diagnosis" in html or "Failure / RCA Diagnosis" in html

    def test_no_diagnosis_still_renders_gate_level(self):
        hg = self._hg()
        html = _build_recommendations(hg, tcr=50.0, acc=83.0, hall_rate=0.0,
                                      latency=1.0, quality_metrics={}, diagnosis=None)
        assert "Gate A" in html
        assert "Biggest measured shortfalls" not in html


class TestExecutiveSummary:
    def _hg(self, **gates):
        return gates

    def test_fail_gate_verdict(self):
        hg = {"A": {"status": "fail", "gate": "fail", "score": 0.3, "details": {}}}
        html = _build_executive_summary(hg, None, 40.0, 30.0, 10)
        assert "Not deployment-ready" in html
        assert "A (Goal Achievement)" in html

    def test_warn_gate_verdict(self):
        hg = {"D": {"status": "warn", "gate": "warn", "score": 0.6, "details": {}}}
        html = _build_executive_summary(hg, None, 80.0, 80.0, 10)
        assert "Deploy with caution" in html

    def test_all_pass_verdict(self):
        hg = {k: {"status": "pass", "gate": "pass", "score": 0.95, "details": {}}
              for k in "ABC"}
        html = _build_executive_summary(hg, None, 95.0, 92.0, 10)
        assert "Deployment-ready" in html

    def test_next_actions_use_component_shortfalls(self):
        from agent_evaluator.rca import diagnose
        hg = {"A": {"status": "warn", "gate": "warn", "score": 0.6,
                    "details": {"avg_subtask_completion": 0.25, "tcr_pct": 50.0}}}
        diag = diagnose({"extra_metrics": {"harness_groups": hg}})
        html = _build_executive_summary(hg, diag, 50.0, 80.0, 10)
        assert "Next actions" in html
        assert "subtask completion" in html
        assert "SubtaskConfig" in html

    def test_no_gate_data(self):
        html = _build_executive_summary({}, None, 0.0, 0.0, 0)
        assert "No Harness Gate data" in html


class TestOperationalSignals:
    def test_empty_when_no_anomaly_data(self):
        assert _build_operational_signals(None) == ""
        assert _build_operational_signals({}) == ""

    def test_no_anomalies_shows_clean_banner(self):
        html = _build_operational_signals(
            {"anomalies": [], "baseline_window": 100, "detection_window": 20}
        )
        assert "no anomalies detected" in html

    def test_anomaly_rows_with_suggestion(self):
        html = _build_operational_signals({"anomalies": [{
            "type": "latency_trend", "severity": "critical",
            "detail": "P95 up 3x", "value": 6.1, "threshold": 2.0,
        }]})
        assert "latency_trend" in html
        assert "P95 up 3x" in html
        assert "trending up" in html  # ANOMALY_METRIC_SUGGESTIONS["latency_trend"]


class TestScoreRepresentativenessWarning:
    """P4.1: 측정 컴포넌트가 2개 이하이고 점수가 90 미만이면 대표성 경고."""

    def test_warns_on_few_components(self):
        from agent_evaluator.reporting.comprehensive_report import _build_score_breakdown
        hg = {"score": 0.6, "status": "warn", "gate": "warn",
              "details": {"tcr_pct": 50.0, "avg_instruction_adherence": 1.0}}
        html = _build_score_breakdown("A", hg)
        assert "may not be representative" in html
        assert "at 100%" in html  # IFR=1.0 masking

    def test_no_warn_when_many_components(self):
        from agent_evaluator.reporting.comprehensive_report import _build_score_breakdown
        hg = {"score": 0.6, "status": "warn", "gate": "warn", "details": {
            "tcr_pct": 50.0, "avg_instruction_adherence": 0.8, "avg_subtask_completion": 0.5,
            "avg_accuracy": 0.6,
        }}
        html = _build_score_breakdown("A", hg)
        assert "may not be representative" not in html

    def test_no_warn_when_score_high(self):
        from agent_evaluator.reporting.comprehensive_report import _build_score_breakdown
        hg = {"score": 0.95, "status": "pass", "gate": "pass",
              "details": {"tcr_pct": 95.0, "avg_accuracy": 0.95}}
        html = _build_score_breakdown("A", hg)
        assert "may not be representative" not in html


class TestSchemaVersion:
    def test_saved_json_has_schema_version(self, tmp_path):
        import json as _json

        from agent_evaluator import PerformanceMonitor, create_taskresult
        m = PerformanceMonitor(output_dir=str(tmp_path))
        m.record_task(create_taskresult(
            task_id="t1", question="q", response="a", ground_truth="a",
            execution_time=1.0, task_type="qa",
        ))
        m.save_to_file("r")
        data = _json.loads((tmp_path / "r.json").read_text())
        assert data.get("schema_version") == "1.1"


class TestFailureClusters:
    """P6 — 실패 인텔리전스: 사유 테마 군집화 + baseline 대비 실패 집합 변화."""

    def test_reason_signature_strips_specifics(self):
        assert _reason_signature("incomplete (60%)") == "incomplete"
        assert (_reason_signature("ground_truth 유사도 낮음 (유사도 0%)")
                == "ground_truth 유사도 낮음")
        assert (_reason_signature("error: TimeoutError: connect ETIMEDOUT")
                == "error: TimeoutError")
        assert _reason_signature("") == "unspecified"

    def test_clusters_ranked_by_count_with_impact(self):
        cases = [
            _mk(f"a{i}", success=False, comp=0.1, acc=0.0,
                reason="ground_truth 유사도 낮음 (유사도 0%)")
            for i in range(4)
        ] + [
            _mk(f"b{i}", success=False, comp=0.1, acc=0.0, reason="error: TimeoutError: x")
            for i in range(2)
        ]
        norm = [_norm_task_for_case(c) for c in cases]
        html = _build_failure_clusters(norm, total_tasks=10)
        assert "Failure themes" in html
        assert html.index("ground_truth 유사도 낮음") < html.index("error: TimeoutError")
        assert "~40%p" in html  # 4/10

    def test_lineage_classifies_regressed_persistent_new(self):
        baseline = {"tasks": [
            {"task_id": "t1", "success": True, "accuracy_score": 0.9},
            {"task_id": "t2", "success": True, "accuracy_score": 0.9},
            {"task_id": "t3", "success": False, "accuracy_score": 0.1},
        ]}
        cur = [_norm_task_for_case(c) for c in [
            _mk("t1", success=False, comp=0.1, acc=0.0),
            _mk("t2", success=True, comp=0.9, acc=0.9),
            _mk("t3", success=False, comp=0.1, acc=0.0),
            _mk("t4", success=False, comp=0.1, acc=0.0),
        ]]
        html = _build_failure_lineage(cur, baseline)
        assert "Regressed (1)" in html and "t1" in html
        assert "Persistent (1)" in html
        assert "New (not in baseline) (1)" in html and "t4" in html

    def test_lineage_empty_without_baseline(self):
        assert _build_failure_lineage([], None) == ""

    def test_full_report_shows_themes_and_lineage(self):
        d = "/tmp"
        mb = PerformanceMonitor(output_dir=d)
        for i in range(8):
            mb.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}",
                response="정답 서울 940만" if i < 4 else "모름",
                ground_truth="정답 서울 940만", execution_time=1.0, task_type="qa",
            ))
        baseline = mb.generate_report().to_dict()
        baseline["tasks"] = [
            {"task_id": f"t{i}", "success": i < 4,
             "accuracy_score": 0.9 if i < 4 else 0.1, "completion_score": 0.9 if i < 4 else 0.1}
            for i in range(8)
        ]
        mc = PerformanceMonitor(output_dir=d)
        for i in range(8):
            mc.record_task(create_taskresult(
                task_id=f"t{i}", question=f"q{i}: 서울 인구",
                response="정답 서울 940만" if i < 2 else "모르겠습니다",
                ground_truth="정답 서울 940만", execution_time=1.0, task_type="qa",
            ))
        html = generate_comprehensive_html_report(mc, baseline=baseline)
        assert "Failure themes" in html
        assert "Failure set vs baseline" in html
        assert "Regressed" in html


class TestImprovementLoopClosure:
    """P8 — 코드 레벨 처방 · 과거 이력 · 실험 제안 · baseline 변화 판정."""

    def test_code_snippet_for_known_component(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_code_snippet
        html = _rec_code_snippet("avg_subtask_completion", 0.25)
        assert "SubtaskConfig" in html
        assert "subtask_tracking=SubtaskConfig(" in html
        assert "current: 25% health" in html

    def test_code_snippet_empty_for_unmapped_component(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_code_snippet
        assert _rec_code_snippet("avg_quality_relevance_completeness", 0.2) == ""

    def test_config_hint_normalizes_avg_prefix(self):
        from agent_evaluator.ontology.metric_registry import config_hint_for
        assert config_hint_for("avg_loop_detection")["config"] == "LoopDetectionConfig"
        assert config_hint_for("sla_breach_rate")["config"] == "SLAConfig"
        assert config_hint_for("nonexistent") is None

    def test_experiment_block_predicts_delta_and_n(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_experiment_block
        html = _rec_experiment_block("A", "avg_subtask_completion", 0.25, n_components=4)
        assert "Run it as an experiment" in html
        assert "Gate A ≈ +0.15" in html          # (0.85-0.25)/4
        assert "tasks recommended" in html
        assert "agent-eval abtest" in html

    def test_experiment_block_empty_when_already_healthy(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_experiment_block
        assert _rec_experiment_block("A", "avg_x", 0.9, 4) == ""

    def test_past_outcomes_summary(self, tmp_path):
        import json as _json

        from agent_evaluator.reporting.comprehensive_report import _rec_past_outcomes
        p = tmp_path / "recommendation_outcomes.jsonl"
        p.write_text(
            _json.dumps({"target_gate": "A", "verdict": "confirmed",
                         "gate_delta": 0.15, "note": "added SubtaskConfig"}) + "\n"
            + _json.dumps({"target_gate": "A", "verdict": "refuted",
                           "gate_delta": -0.02, "note": "x"}) + "\n"
        )
        html = _rec_past_outcomes(p, "A")
        assert "1 confirmed / 1 refuted / 2 total" in html
        assert "avg Δ +0.150" in html

    def test_past_outcomes_empty_without_log(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_past_outcomes
        assert _rec_past_outcomes(None, "A") == ""

    def test_baseline_verdict_confirmed_and_refuted(self):
        from agent_evaluator.reporting.comprehensive_report import _rec_baseline_verdict
        base = {"extra_metrics": {"harness_groups": {"A": {"score": 0.5}}}}
        up = {"extra_metrics": {"harness_groups": {"A": {"score": 0.72}}}}
        down = {"extra_metrics": {"harness_groups": {"A": {"score": 0.3}}}}
        assert "confirmed" in _rec_baseline_verdict(base, up, "A")
        assert "refuted" in _rec_baseline_verdict(base, down, "A")
        assert _rec_baseline_verdict(None, up, "A") == ""

    def test_full_report_recommendations_carry_p8(self):
        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(10):
            m.record_task(create_taskresult(
                task_id=f"t{i}", question="q", response="모름" if i < 7 else "약 940만명",
                ground_truth="약 940만명", execution_time=1.0, task_type="qa",
            ))
        html = generate_comprehensive_html_report(m)
        seg = html[html.find('id="recommendations"'):html.find('id="diagnosis"')]
        assert "Run it as an experiment" in seg


class TestTrajectoryAndLatencyBudget:
    """P7 — per-step trajectory in failure cases + latency-budget breakdown."""

    def test_trajectory_renders_tool_calls_for_failure(self):
        from agent_evaluator.reporting.comprehensive_report import _build_trajectory
        case = {
            "tool_calls": [
                {"tool_name": "retrieve", "parameters": {"q": "x"}, "output": "3 docs",
                 "success": True, "duration": 320},
                {"tool_name": "generate", "parameters": {}, "output": "wrong",
                 "success": False, "duration": 1400, "tokens": {"total": 110}},
            ],
            "chain_steps": [], "agent_interactions": [],
        }
        html = _build_trajectory(case)
        assert "Trajectory (2 tool calls)" in html
        assert "retrieve" in html and "generate" in html
        assert "320ms" in html and "110 tok" in html
        assert " ✗" in html  # failed step marked

    def test_trajectory_empty_without_step_data(self):
        from agent_evaluator.reporting.comprehensive_report import _build_trajectory
        empty = {"tool_calls": [], "chain_steps": [], "agent_interactions": []}
        assert _build_trajectory(empty) == ""

    def test_latency_budget_section_in_report(self):
        from agent_evaluator.core.trackers.base import TaskResult
        from agent_evaluator.reporting.comprehensive_report import (
            generate_comprehensive_html_report,
        )

        m = PerformanceMonitor(output_dir="/tmp")
        for i in range(8):
            m.record_task(TaskResult(
                task_id=f"t{i}", task_type="rag", success=True,
                completion_score=1.0, accuracy_score=0.9, execution_time=1.7,
                tokens_used={"total": 150}, tool_calls=[], attempts=1, errors=[],
                question="q", response="a", ground_truth="a",
                extra={"latency_attribution": {
                    "tool_ms": 300.0, "model_ms": 1400.0, "network_ms": 20.0,
                    "unattributed_ms": 0.0, "tool_ratio": 0.17, "model_ratio": 0.82,
                    "network_ratio": 0.01, "unattributed_ratio": 0.0,
                    "bottleneck": "model"},
                },
            ))
        html = generate_comprehensive_html_report(m)
        assert "Latency Budget" in html
        assert "Bottleneck: model" in html
