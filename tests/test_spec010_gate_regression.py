"""
tests/test_spec010_gate_regression.py
========================================
SPEC-010: Harness Gate A-G 회귀 탐지 확장 검증.

REQ-1: cli/gate.py의 --save-baseline이 Gate A-G 점수도 baseline.json에 저장.
REQ-2: --fail-on-regression이 Gate A-G 점수도 회귀 비교 대상에 포함(구버전 baseline.json 하위호환).
REQ-3: HarnessEvaluationGate.evaluate(baseline=..., regression_threshold=...) Python API.
REQ-4: baseline 미지정 시 두 경로 모두 기존 동작과 100% 동일.
"""
from __future__ import annotations

import json

import pytest

from agent_evaluator.cli.gate import _load_baseline, _save_baseline, cmd_gate
from agent_evaluator.quick_eval import (
    HarnessEvaluationGate,
    _compute_gate_regressions,
    _normalize_gate_score_dict,
)

from tests.test_coverage_cli_gate import _make_args, _make_result_data


def _with_harness_groups(data, scores):
    """_make_result_data() 결과에 extra_metrics.harness_groups를 추가한다."""
    data = dict(data)
    data["extra_metrics"] = {
        "harness_groups": {
            gate_id: ({"score": score, "status": "pass"} if score is not None else {"score": None})
            for gate_id, score in scores.items()
        }
    }
    return data


class _ReportProxy:
    def __init__(self, harness_groups):
        self.extra_metrics = {"harness_groups": harness_groups}


# ---------------------------------------------------------------------------
# 공유 헬퍼 (quick_eval.py) 단위 테스트
# ---------------------------------------------------------------------------

class TestComputeGateRegressions:
    def test_regression_detected_when_below_threshold(self):
        current = {"A": 0.74, "B": 0.90}
        baseline = {"A": 0.82, "B": 0.90}
        result = _compute_gate_regressions(current, baseline, 0.05)
        assert len(result) == 1
        assert result[0]["gate"] == "A"
        assert result[0]["baseline_score"] == 0.82
        assert result[0]["current_score"] == 0.74
        assert result[0]["delta"] == pytest.approx(-0.08)

    def test_within_tolerance_not_flagged(self):
        current = {"A": 0.80}
        baseline = {"A": 0.82}
        result = _compute_gate_regressions(current, baseline, 0.05)
        assert result == []

    def test_none_current_skipped(self):
        result = _compute_gate_regressions({"A": None}, {"A": 0.82}, 0.05)
        assert result == []

    def test_none_baseline_skipped(self):
        result = _compute_gate_regressions({"A": 0.5}, {"A": None}, 0.05)
        assert result == []

    def test_zero_baseline_skipped(self):
        """분모 0 guard — baseline=0.0이면 회귀 판정에서 제외."""
        result = _compute_gate_regressions({"A": 0.0}, {"A": 0.0}, 0.05)
        assert result == []

    def test_missing_gate_in_baseline_skipped(self):
        result = _compute_gate_regressions({"A": 0.5, "B": 0.6}, {"A": 0.5}, 0.05)
        assert result == []


class TestNormalizeGateScoreDict:
    def test_flat_dict_passthrough(self):
        assert _normalize_gate_score_dict({"A": 0.8, "B": 0.6}) == {"A": 0.8, "B": 0.6}

    def test_report_shaped_dict_extracts_score(self):
        raw = {"A": {"score": 0.8, "status": "pass"}, "B": {"score": None}}
        assert _normalize_gate_score_dict(raw) == {"A": 0.8, "B": None}

    def test_none_input_returns_empty_dict(self):
        assert _normalize_gate_score_dict(None) == {}

    def test_empty_dict_returns_empty_dict(self):
        assert _normalize_gate_score_dict({}) == {}


# ---------------------------------------------------------------------------
# REQ-3: HarnessEvaluationGate.evaluate() Python API
# ---------------------------------------------------------------------------

class TestHarnessEvaluationGateBaseline:
    def test_baseline_omitted_no_regressions_key(self):
        """REQ-4: baseline 미지정 시 결과 dict에 'regressions' 키가 아예 없어야 한다(하위호환)."""
        report = _ReportProxy({"A": {"score": 0.9, "status": "pass"}})
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate()
        assert "regressions" not in result

    def test_baseline_regression_detected_flat_dict(self):
        report = _ReportProxy({"A": {"score": 0.74, "status": "pass"}})
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate(baseline={"A": 0.82}, regression_threshold=0.05)
        assert result["passed"] is False
        assert result["regressions"] == [
            {"gate": "A", "baseline_score": 0.82, "current_score": 0.74, "delta": pytest.approx(-0.08)}
        ]

    def test_baseline_regression_detected_report_shaped_dict(self):
        """baseline을 이전 report.extra_metrics['harness_groups'] 형식으로 넘겨도 동작해야 한다."""
        report = _ReportProxy({"A": {"score": 0.74, "status": "pass"}})
        gate = HarnessEvaluationGate(report)
        previous_harness_groups = {"A": {"score": 0.82, "status": "pass"}}
        result = gate.evaluate(baseline=previous_harness_groups, regression_threshold=0.05)
        assert result["passed"] is False
        assert result["regressions"][0]["gate"] == "A"

    def test_baseline_within_threshold_passes(self):
        report = _ReportProxy({"A": {"score": 0.90, "status": "pass"}})
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate(baseline={"A": 0.90}, regression_threshold=0.05)
        assert result["passed"] is True
        assert result["regressions"] == []

    def test_baseline_with_no_harness_groups_still_returns_regressions_key(self):
        """harness_groups가 비어 있는 조기 반환 경로에서도 baseline 지정 시 'regressions': []."""
        report = _ReportProxy({})
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate(baseline={"A": 0.9})
        assert result["regressions"] == []
        assert result["passed"] is True

    def test_static_threshold_and_regression_both_considered(self):
        """정적 임계값(min_group_score)과 베이스라인 회귀 둘 다 확인되어야 한다."""
        report = _ReportProxy({
            "A": {"score": 0.72, "status": "warn"},  # min_group_score=0.7 통과, 그러나 회귀 있음
        })
        gate = HarnessEvaluationGate(report, min_group_score=0.7)
        result = gate.evaluate(baseline={"A": 0.9}, regression_threshold=0.05)
        assert result["groups"]["A"]["passed"] is True  # 정적 임계값 자체는 통과
        assert result["passed"] is False  # 그러나 회귀로 인해 전체 판정은 실패
        assert len(result["regressions"]) == 1

    def test_enforce_exits_on_regression(self):
        report = _ReportProxy({"A": {"score": 0.5, "status": "warn"}})
        gate = HarnessEvaluationGate(report)
        with pytest.raises(SystemExit) as exc_info:
            gate.enforce(baseline={"A": 0.9}, regression_threshold=0.05)
        assert exc_info.value.code == 1

    def test_enforce_no_exit_when_baseline_omitted_and_static_passes(self):
        report = _ReportProxy({"A": {"score": 0.9, "status": "pass"}})
        gate = HarnessEvaluationGate(report)
        # 예외 없이 정상 반환되어야 함
        result_gate = gate.enforce(exit_on_fail=False)
        assert result_gate.result is not None
        assert result_gate.result["passed"] is True


# ---------------------------------------------------------------------------
# Harness Method 검사 5-D 개선: group_thresholds / strict_required /
# insufficient_data_warnings 노출 (QuickEval.gate()/CLI --gate-thresholds와 대칭)
# ---------------------------------------------------------------------------

class TestHarnessEvaluationGateGroupThresholds:
    def test_default_behavior_unchanged_without_group_thresholds(self):
        """group_thresholds 미지정 시 min_group_score만 쓰는 기존 동작과 100% 동일."""
        report = _ReportProxy({"A": {"score": 0.75, "status": "pass"}})
        gate = HarnessEvaluationGate(report, min_group_score=0.7)
        result = gate.evaluate()
        assert result["groups"]["A"]["passed"] is True
        assert result["groups"]["A"]["threshold"] == 0.7

    def test_per_group_threshold_overrides_min_group_score(self):
        """E처럼 리스크가 큰 Gate만 더 엄격한 임계값을 줄 수 있어야 한다."""
        report = _ReportProxy({
            "A": {"score": 0.75, "status": "pass"},
            "E": {"score": 0.90, "status": "pass"},
        })
        gate = HarnessEvaluationGate(
            report, min_group_score=0.7, group_thresholds={"E": 0.95},
        )
        result = gate.evaluate()
        assert result["groups"]["A"]["passed"] is True  # 0.75 >= 0.7 (기본값)
        assert result["groups"]["E"]["passed"] is False  # 0.90 < 0.95 (개별 임계값)
        assert result["groups"]["E"]["threshold"] == 0.95
        assert result["passed"] is False

    def test_unlisted_group_falls_back_to_min_group_score(self):
        report = _ReportProxy({"A": {"score": 0.65, "status": "warn"}})
        gate = HarnessEvaluationGate(
            report, min_group_score=0.7, group_thresholds={"E": 0.95},
        )
        result = gate.evaluate()
        assert result["groups"]["A"]["threshold"] == 0.7
        assert result["groups"]["A"]["passed"] is False


class TestHarnessEvaluationGateStrictRequired:
    def test_none_score_passes_by_default(self):
        """기존 동작(하위호환): 측정 안 된 Gate는 조용히 통과."""
        report = _ReportProxy({"E": {"score": None}})
        gate = HarnessEvaluationGate(report, required_groups=["E"])
        result = gate.evaluate()
        assert result["groups"]["E"]["passed"] is True
        assert result["groups"]["E"]["not_measured"] is True
        assert result["passed"] is True

    def test_strict_required_fails_explicit_none_score_group(self):
        """required_groups에 명시한 Gate가 score=None이면 strict_required=True일 때 실패해야 한다."""
        report = _ReportProxy({"E": {"score": None}})
        gate = HarnessEvaluationGate(
            report, required_groups=["E"], strict_required=True,
        )
        result = gate.evaluate()
        assert result["groups"]["E"]["passed"] is False
        assert result["passed"] is False
        assert result["violations"][0]["reason"] == "not_measured"

    def test_strict_required_does_not_affect_auto_discovered_groups(self):
        """required_groups를 생략(자동 탐지)한 경우 strict_required=True여도 None 점수 Gate는
        여전히 통과해야 한다 — 명시적으로 요구하지 않은 Gate까지 강제하면 안 된다."""
        report = _ReportProxy({
            "A": {"score": 0.9, "status": "pass"},
            "E": {"score": None},
        })
        gate = HarnessEvaluationGate(report, strict_required=True)
        result = gate.evaluate()
        assert result["groups"]["E"]["passed"] is True
        assert result["passed"] is True


class TestHarnessEvaluationGateInsufficientDataWarnings:
    def test_warnings_exposed_in_result(self):
        report = _ReportProxy({
            "B": {
                "score": 0.9, "status": "pass",
                "details": {"insufficient_data_warnings": ["loop_detection: 1 samples < min_samples=3"]},
            },
        })
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate()
        assert result["groups"]["B"]["insufficient_data_warnings"] == [
            "loop_detection: 1 samples < min_samples=3"
        ]

    def test_no_warnings_key_when_absent(self):
        """details에 insufficient_data_warnings가 없거나 None이면 결과 dict에 그 키 자체가 없어야 한다."""
        report = _ReportProxy({"A": {"score": 0.9, "status": "pass", "details": {}}})
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate()
        assert "insufficient_data_warnings" not in result["groups"]["A"]


# ---------------------------------------------------------------------------
# REQ-1/REQ-2: CLI cli/gate.py 통합
# ---------------------------------------------------------------------------

class TestCliSaveBaselineIncludesGateScores:
    def test_save_baseline_includes_gate_scores(self, tmp_path):
        data = _with_harness_groups(_make_result_data(), {"A": 0.82, "B": 0.74})
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), save_baseline=True)
        rc = cmd_gate(args)
        assert rc == 0

        baseline = _load_baseline(tmp_path / "baseline.json")
        assert baseline is not None
        assert baseline["gate_scores"] == {
            g: (0.82 if g == "A" else 0.74 if g == "B" else None) for g in "ABCDEFG"
        }

    def test_save_baseline_without_harness_groups_omits_gate_scores_key(self, tmp_path):
        """harness_groups가 아예 없는 결과 파일에서는 gate_scores 키 자체가 저장되지 않아야 한다."""
        data = _make_result_data()  # extra_metrics 없음
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), save_baseline=True)
        cmd_gate(args)
        baseline = _load_baseline(tmp_path / "baseline.json")
        assert baseline is not None
        assert "gate_scores" not in baseline


class TestCliFailOnRegressionIncludesGateScores:
    def test_gate_regression_triggers_exit_code_2(self, tmp_path):
        data = _with_harness_groups(_make_result_data(tcr=0.95), {"A": 0.70})
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"tcr": 90.0, "gate_scores": {"A": 0.90}, "saved_at": "2025-01-01"}),
            encoding="utf-8",
        )
        args = _make_args(result_file=str(f), fail_on_regression=5.0)
        rc = cmd_gate(args)
        assert rc == 2

    def test_gate_regression_absent_when_baseline_has_no_gate_scores(self, tmp_path):
        """REQ-2 하위호환: 구버전 baseline.json(gate_scores 키 없음)을 읽어도 크래시 없이
        동작해야 하고, Gate 회귀는 단순히 감지되지 않아야 한다(기존 5개 평면 지표 회귀는 그대로 동작)."""
        data = _with_harness_groups(_make_result_data(tcr=0.95, accuracy=0.9, p95=1.0, hallucination=0.02), {"A": 0.70})
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        # 구버전 포맷 — gate_scores 키가 아예 없음
        baseline.write_text(
            json.dumps({
                "tcr": 90.0, "accuracy": 85.0, "p95_latency": 1.5,
                "hallucination": 10.0, "llm_judge_overall": None,
                "saved_at": "2025-01-01",
            }),
            encoding="utf-8",
        )
        args = _make_args(result_file=str(f), fail_on_regression=5.0)
        rc = cmd_gate(args)
        # 5개 평면 지표는 전부 개선(baseline 대비 향상)됐으므로 회귀 없음 → 0
        # (Gate A는 baseline에 없으므로 비교 자체가 스킵됨 — 크래시 없이 안전하게 무시)
        assert rc == 0

    def test_no_gate_regression_within_tolerance(self, tmp_path):
        data = _with_harness_groups(_make_result_data(tcr=0.9), {"A": 0.80})
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"tcr": 90.0, "gate_scores": {"A": 0.82}, "saved_at": "2025-01-01"}),
            encoding="utf-8",
        )
        args = _make_args(result_file=str(f), fail_on_regression=5.0)
        rc = cmd_gate(args)
        assert rc == 0

    def test_gate_regression_without_fail_on_regression_flag_ignored(self, tmp_path):
        """--fail-on-regression을 지정하지 않으면 baseline.json에 gate_scores가 있어도
        Gate 회귀 비교 자체가 수행되지 않아야 한다(REQ-4 — 옵트인 기능)."""
        data = _with_harness_groups(_make_result_data(tcr=0.95), {"A": 0.10})
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"tcr": 90.0, "gate_scores": {"A": 0.90}, "saved_at": "2025-01-01"}),
            encoding="utf-8",
        )
        args = _make_args(result_file=str(f))  # fail_on_regression=None (기본)
        rc = cmd_gate(args)
        assert rc == 0
