"""
tests/test_phase4_rca_diagnose.py
====================================
Phase 4(개선 엔진) — agent_evaluator.rca.diagnose()의 회귀 테스트.

Media/Harness_Method Chapter 31의 두 워크드 예제를 그대로 재현해서 검증한다:
- §31.0/§31.4: Gate A 하락 — avg_plan_coherence가 급락한 게 실제 원인귀속 1순위로
  나와야 한다(§31.4는 tcr_pct가 오히려 오른 사례로 "세부값을 반드시 보라"를 강조).
- §31.2: Gate C·D 동시 하락 — SLA가 원인이 아닌 경우(각자 독립 원인)와 원인인 경우
  둘 다 검증한다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from agent_evaluator.rca import diagnose


def _report(harness_groups: dict) -> dict:
    return {"extra_metrics": {"harness_groups": harness_groups}}


def _gate(score, **details):
    return {"score": score, "status": "pass", "gate": "pass", "details": details}


class TestDetectionMode:
    def test_no_baseline_uses_absolute_threshold(self):
        current = _report({
            "A": {"score": 0.9, "status": "pass", "details": {}},
            "B": {"score": 0.4, "status": "fail", "details": {}},
        })
        result = diagnose(current)
        assert result["detection_mode"] == "absolute_threshold"
        assert result["detected_gates"] == ["B"]
        assert result["regressions"] is None

    def test_with_baseline_uses_regression_detection(self):
        current = _report({"A": _gate(0.5)})
        baseline = _report({"A": _gate(0.85)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["detection_mode"] == "regression_vs_baseline"
        assert result["detected_gates"] == ["A"]
        assert result["regressions"][0]["gate"] == "A"

    def test_no_regression_when_within_threshold(self):
        current = _report({"A": _gate(0.80)})
        baseline = _report({"A": _gate(0.85)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["detected_gates"] == []


class TestChapter31Section0GateAWorkedExample:
    """§31.0/§31.4 워크드 예제 — Gate A 0.85→0.60, avg_plan_coherence가 원인 1순위여야 함."""

    def test_plan_coherence_ranks_first_by_magnitude(self):
        current = _report({
            "A": _gate(0.60, tcr_pct=60.0, avg_goal_alignment=0.88, avg_plan_coherence=0.4),
        })
        baseline = _report({
            "A": _gate(0.85, tcr_pct=55.0, avg_goal_alignment=0.90, avg_plan_coherence=0.9),
        })
        result = diagnose(current, baseline, regression_threshold=0.1)
        finding = result["findings"][0]
        assert finding["gate"] == "A"
        top = finding["top_detail_deltas"][0]
        assert top["field"] == "avg_plan_coherence"
        assert top["delta"] < 0

    def test_tcr_rising_while_gate_falls_is_visible_not_hidden(self):
        """§31.4의 핵심 교훈 — top-line 점수는 떨어졌는데 tcr_pct는 올랐다. 이 반대
        방향 이동이 top_detail_deltas에 그대로 드러나야 한다(감춰지면 안 됨)."""
        current = _report({"A": _gate(0.1452, tcr_pct=60.0, avg_accuracy=0.0)})
        baseline = _report({"A": _gate(0.2962, tcr_pct=55.0, avg_accuracy=0.0815)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        deltas_by_field = {d["field"]: d for d in result["findings"][0]["top_detail_deltas"]}
        assert deltas_by_field["tcr_pct"]["delta"] > 0  # 오히려 상승
        assert deltas_by_field["avg_accuracy"]["delta"] < 0  # 진짜 원인


class TestChapter31Section2MultiGateSlaCheck:
    """§31.2 워크드 예제 — Gate C·D 동시 하락 시 SLA 공유원인 여부를 먼저 체크."""

    def test_multi_gate_note_present_when_two_or_more_detected(self):
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.0),
            "D": _gate(0.68, sla_window_penalty=0.0, sla_budget_penalty=0.0),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        assert result["multi_gate_note"] is not None
        assert "C" in result["multi_gate_note"] and "D" in result["multi_gate_note"]

    def test_sla_ruled_out_when_breach_and_penalty_near_zero(self):
        """§31.2 사례 그대로 — sla_breach_rate/penalty가 낮으면 SLA는 원인이 아니라고
        판단하고 각 Gate를 독립적으로 조사하라고 안내해야 한다."""
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.02),
            "D": _gate(0.68, sla_window_penalty=0.0, sla_budget_penalty=0.0),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        check = result["sla_shared_cause_check"]
        assert check["likely_shared_cause"] is False
        assert "independently" in check["note"]

    def test_sla_flagged_as_likely_shared_cause_when_breach_high(self):
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.4),
            "D": _gate(0.68, sla_window_penalty=0.1, sla_budget_penalty=0.05),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        check = result["sla_shared_cause_check"]
        assert check["likely_shared_cause"] is True

    def test_no_sla_check_when_only_one_of_c_d_detected(self):
        current = _report({"C": _gate(0.55, sla_breach_rate=0.4), "D": _gate(0.9)})
        baseline = _report({"C": _gate(0.80), "D": _gate(0.9)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        assert result["detected_gates"] == ["C"]
        assert result["sla_shared_cause_check"] is None
        assert result["multi_gate_note"] is None

    def test_no_multi_gate_note_for_single_gate(self):
        current = _report({"A": _gate(0.5)})
        baseline = _report({"A": _gate(0.9)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["multi_gate_note"] is None


class TestDetailDeltaRankingIsScaleAware:
    """회귀 테스트 — 0-100 스케일 필드(_pct)와 0-1 스케일 필드를 원시 delta로만
    비교하면 _pct 필드가 항상 1순위로 오판된다(Phase 2의 get_comparison
    accuracy_dropped와 같은 클래스의 스케일 버그). 정렬이 스케일을 보정하는지 확인."""

    def test_pct_field_does_not_dominate_ranking_by_raw_magnitude_alone(self):
        # tcr_pct: 55.0→60.0 (raw delta=5.0), avg_plan_coherence: 0.9→0.4 (raw delta=-0.5)
        # 스케일 보정 없이 raw만 비교하면 tcr_pct(5.0)가 avg_plan_coherence(0.5)를 이긴다.
        current = _report({"A": _gate(0.5, tcr_pct=60.0, avg_plan_coherence=0.4)})
        baseline = _report({"A": _gate(0.9, tcr_pct=55.0, avg_plan_coherence=0.9)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        top_field = result["findings"][0]["top_detail_deltas"][0]["field"]
        assert top_field == "avg_plan_coherence"

    def test_reported_delta_values_stay_in_original_units(self):
        """정렬 기준만 스케일 보정하고, 실제 반환값(current/baseline/delta)은 원래
        단위(0-100)를 그대로 보존해야 한다 — 표시용 값을 조작하면 안 된다."""
        current = _report({"A": _gate(0.5, tcr_pct=60.0)})
        baseline = _report({"A": _gate(0.9, tcr_pct=55.0)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        tcr_entry = next(
            d for d in result["findings"][0]["top_detail_deltas"] if d["field"] == "tcr_pct"
        )
        assert tcr_entry["current"] == 60.0
        assert tcr_entry["baseline"] == 55.0
        assert tcr_entry["delta"] == 5.0


class TestReverseDiagnosisSharedCauseGeneralization:
    """폐루프 학습 — SHARED_CAUSE_CHECKS 레지스트리 + 최소 설명집합 선택
    (_select_shared_cause_explanations)의 회귀 테스트. sla_shared_cause_check
    (하위호환 필드)와 shared_cause_explanations(일반화된 신규 필드)가 일관돼야 한다."""

    def test_explained_gates_excluded_from_independent_list(self):
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.4),
            "D": _gate(0.68, sla_window_penalty=0.1, sla_budget_penalty=0.05),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        assert result["independently_investigate_gates"] == []
        assert len(result["shared_cause_explanations"]) == 1
        assert result["shared_cause_explanations"][0]["check"] == "sla"
        assert result["shared_cause_explanations"][0]["explains_gates"] == ["C", "D"]

    def test_unexplained_gates_remain_independent(self):
        """SLA가 원인이 아니면(낮은 breach/penalty) C·D 둘 다 독립 조사 대상으로 남는다."""
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.01),
            "D": _gate(0.68, sla_window_penalty=0.0, sla_budget_penalty=0.0),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        assert result["independently_investigate_gates"] == ["C", "D"]
        assert result["shared_cause_explanations"] == []

    def test_gates_outside_any_check_stay_independent(self):
        """C·D는 SLA로 설명돼도, 같이 감지된 A는 어떤 체크 대상도 아니므로 항상 독립."""
        current = _report({
            "A": _gate(0.5),
            "C": _gate(0.55, sla_breach_rate=0.4),
            "D": _gate(0.68, sla_window_penalty=0.1, sla_budget_penalty=0.05),
        })
        baseline = _report({"A": _gate(0.9), "C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        assert result["independently_investigate_gates"] == ["A"]
        assert result["shared_cause_explanations"][0]["explains_gates"] == ["C", "D"]

    def test_backward_compat_sla_field_matches_generalized_result(self):
        """sla_shared_cause_check(구 필드)와 shared_cause_explanations(신 필드)가
        같은 내용을 가리켜야 한다 — 하나만 고치고 다른 하나를 깜빡하면 이 테스트가 잡는다."""
        current = _report({
            "C": _gate(0.55, sla_breach_rate=0.4),
            "D": _gate(0.68, sla_window_penalty=0.1, sla_budget_penalty=0.05),
        })
        baseline = _report({"C": _gate(0.80), "D": _gate(0.75)})
        result = diagnose(current, baseline, regression_threshold=0.05)
        old_field = result["sla_shared_cause_check"]
        new_field = result["shared_cause_explanations"][0]
        assert old_field["likely_shared_cause"] == new_field["likely_shared_cause"]
        assert old_field["sla_breach_rate"] == new_field["sla_breach_rate"]

    def test_single_gate_detected_is_independent_by_definition(self):
        current = _report({"A": _gate(0.5)})
        baseline = _report({"A": _gate(0.9)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["independently_investigate_gates"] == ["A"]
        assert result["shared_cause_explanations"] == []


class TestDetailDeltasExcludeNonNumeric:
    def test_insufficient_data_warnings_excluded(self):
        current = _report({
            "B": _gate(0.5, loop_detection_rate=0.3, insufficient_data_warnings=["x: 1 < 3"]),
        })
        baseline = _report({"B": _gate(0.9, loop_detection_rate=0.0)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        fields = {d["field"] for d in result["findings"][0]["top_detail_deltas"]}
        assert "insufficient_data_warnings" not in fields

    def test_dict_valued_field_excluded(self):
        current = _report({
            "B": _gate(0.5, deadlock_by_type={"circular": 1}, avg_deadlock_score=0.3),
        })
        baseline = _report({"B": _gate(0.9, deadlock_by_type=None, avg_deadlock_score=1.0)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        fields = {d["field"] for d in result["findings"][0]["top_detail_deltas"]}
        assert "deadlock_by_type" not in fields
        assert "avg_deadlock_score" in fields


class TestCrossReferenceSkippedWithoutDb:
    def test_no_violation_db_path_yields_empty_cross_references(self):
        current = _report({"B": _gate(0.4, loop_detection_rate=0.5)})
        baseline = _report({"B": _gate(0.9, loop_detection_rate=0.0)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["findings"][0]["cross_references"] == []

    def test_broken_db_path_fails_gracefully(self, tmp_path):
        current = _report({"B": _gate(0.4, loop_detection_rate=0.5)})
        baseline = _report({"B": _gate(0.9, loop_detection_rate=0.0)})
        result = diagnose(
            current, baseline, regression_threshold=0.1,
            violation_db_path=tmp_path / "nonexistent.db",
        )
        # 3단계만 조용히 건너뛰고 1·2단계 결과는 그대로 반환돼야 함
        assert result["findings"][0]["cross_references"] == []
        assert result["findings"][0]["top_detail_deltas"][0]["field"] == "loop_detection_rate"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


class TestExperimentMetadataIntegration:
    """ExperimentMetadata는 기본적으로 꺼져 있고(with_experiment_metadata=False),
    켜졌을 때만(옵트인) 그리고 baseline이 있을 때만 채워져야 한다."""

    def test_absent_by_default(self):
        current = _report({"A": _gate(0.5)})
        baseline = _report({"A": _gate(0.9)})
        result = diagnose(current, baseline, regression_threshold=0.1)
        assert result["experiment_metadata"] is None

    def test_absent_when_no_baseline_even_if_requested(self):
        current = _report({"B": {"score": 0.4, "status": "fail", "details": {}}})
        result = diagnose(current, with_experiment_metadata=True)
        assert result["experiment_metadata"] is None

    def test_absent_when_lineage_missing_even_if_requested(self):
        current = _report({"A": _gate(0.5)})
        baseline = _report({"A": _gate(0.9)})
        result = diagnose(
            current, baseline, regression_threshold=0.1, with_experiment_metadata=True,
        )
        assert result["experiment_metadata"] is None

    def test_populated_as_plain_dict_when_git_commits_resolvable(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test User")
        (repo / "a.py").write_text("v1\n")
        _git(repo, "add", "a.py")
        _git(repo, "commit", "-q", "-m", "first")
        first_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        (repo / "a.py").write_text("v2\n")
        _git(repo, "commit", "-q", "-am", "second")
        second_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

        baseline = {
            "extra_metrics": {
                "harness_groups": {"A": _gate(0.9)},
                "lineage": {"git_commit": first_sha},
            }
        }
        current = {
            "extra_metrics": {
                "harness_groups": {"A": _gate(0.5)},
                "lineage": {"git_commit": second_sha},
            }
        }
        result = diagnose(
            current, baseline, regression_threshold=0.1,
            with_experiment_metadata=True, repo_path=repo,
        )
        exp = result["experiment_metadata"]
        assert isinstance(exp, dict)  # dataclass가 아니라 JSON 직렬화 가능한 순수 dict여야 함
        assert exp["from_commit"] == first_sha[:8]
        assert exp["to_commit"] == second_sha[:8]
        assert "a.py" in exp["changed_files"]
        assert exp["commits_between"][0]["subject"] == "second"

        import json

        json.dumps(result, ensure_ascii=False)  # CLI --json 경로 조건 — 예외 없이 직렬화돼야 함
