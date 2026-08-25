"""
tests/test_phase6_structural_change3_unification.py
=======================================================
구조변경③ — 3경로(HarnessEvaluationGate.evaluate()/QuickEval.gate()/cli/gate.py
--gate-thresholds) Harness Gate A-G 판정 완전 통합의 회귀 테스트.

gates/base.py의 evaluate_gate_scores()가 세 경로가 공유하는 단일 정본이다.
직접 단위 테스트 + 세 경로가 같은 입력에 대해 같은 판정을 내는지 확인하는
일관성 테스트로 구성한다.
"""
from __future__ import annotations

import argparse
import json

from agent_evaluator import QuickEval, create_taskresult
from agent_evaluator.cli.gate import cmd_gate
from agent_evaluator.gates.base import evaluate_gate_scores
from agent_evaluator.quick_eval import HarnessEvaluationGate


def _hg(**scores):
    """{"A": 0.9, "B": None, ...} → harness_groups 형식 dict."""
    return {
        gate_id: (
            {"score": s, "status": "pass" if s is not None and s >= 0.7 else "warn"}
            if s is not None else {"score": None, "status": "n/a"}
        )
        for gate_id, s in scores.items()
    }


class TestEvaluateGateScoresUnit:
    def test_passes_when_above_threshold(self):
        hg = _hg(A=0.9)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.7})
        assert result["A"]["passed"] is True
        assert result["A"]["score"] == 0.9

    def test_fails_when_below_threshold(self):
        hg = _hg(A=0.5)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.7})
        assert result["A"]["passed"] is False

    def test_falls_back_to_default_threshold(self):
        hg = _hg(A=0.75, B=0.6)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.5}, default_threshold=0.7)
        assert result["A"]["passed"] is True   # A는 개별 임계값(0.5) 사용
        assert result["B"]["passed"] is False  # B는 default_threshold(0.7) 사용

    def test_gate_excluded_when_no_threshold_available(self):
        hg = _hg(A=0.9, B=0.5)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.7})  # B는 threshold 없음
        assert "A" in result
        assert "B" not in result

    def test_none_score_passes_by_default(self):
        hg = _hg(A=None)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.7})
        assert result["A"]["passed"] is True
        assert result["A"]["not_measured"] is True

    def test_strict_required_fails_explicit_none_score(self):
        hg = _hg(A=None)
        result = evaluate_gate_scores(
            hg, gate_ids=["A"], thresholds={"A": 0.7}, strict_required=True,
        )
        assert result["A"]["passed"] is False

    def test_strict_required_does_not_affect_auto_discovered_gates(self):
        hg = _hg(A=None)
        result = evaluate_gate_scores(hg, thresholds={"A": 0.7}, strict_required=True)
        # gate_ids=None(자동 감지)이므로 strict_required가 적용되지 않아야 함
        assert result["A"]["passed"] is True

    def test_fail_on_warn_escalates_warn_status(self):
        hg = {"A": {"score": 0.3, "status": "warn"}}  # threshold를 낮춰도 warn이면 실패
        result = evaluate_gate_scores(
            hg, thresholds={"A": 0.1}, fail_on_warn=True,
        )
        assert result["A"]["passed"] is False

    def test_auto_detects_custom_registered_gate(self):
        """register_gate()로 추가된 커스텀 Gate("COST" 등)도 자동 감지 대상이다 —
        이전엔 QuickEval.gate()/cli/gate.py가 "ABCDEFG"로 고정돼 있어 불가능했다."""
        hg = {"COST": {"score": 0.4, "status": "warn"}}
        result = evaluate_gate_scores(hg, default_threshold=0.5)
        assert "COST" in result
        assert result["COST"]["passed"] is False

    def test_overall_key_excluded_from_auto_detection(self):
        hg = {"A": {"score": 0.9, "status": "pass"}, "overall": {"score": 0.9}}
        result = evaluate_gate_scores(hg, default_threshold=0.5)
        assert "overall" not in result

    def test_order_preserved_for_explicit_gate_ids(self):
        hg = _hg(A=0.9, B=0.9, C=0.9)
        result = evaluate_gate_scores(hg, gate_ids=["C", "A", "B"], default_threshold=0.5)
        assert list(result.keys()) == ["C", "A", "B"]


class TestThreePathConsistency:
    """같은 harness_groups + 같은 임계값 설정을 세 경로 모두에 줘서, 판정이 일치하는지
    확인한다 — evaluate_gate_scores() 통합 전에는 세 경로가 독립 구현이라 이런
    일관성이 알고리즘적으로 보장되지 않았다(각자 버그가 있으면 서로 다른 결과가 나올 수 있었음)."""

    def _report_dict(self, hg):
        return {"extra_metrics": {"harness_groups": hg}}

    def test_harness_gate_and_quickeval_agree(self, tmp_path):
        hg = _hg(A=0.9, B=0.5, C=0.75)
        report_data = self._report_dict(hg)

        # 경로 1: HarnessEvaluationGate
        class _ReportProxy:
            def __init__(self, d):
                self.extra_metrics = d["extra_metrics"]

        hg_gate = HarnessEvaluationGate(
            _ReportProxy(report_data), group_thresholds={"A": 0.7, "B": 0.7, "C": 0.7},
        )
        hg_result = hg_gate.evaluate()

        # 경로 2: QuickEval.gate() (dry_run)
        qe = QuickEval(str(tmp_path))
        qe._monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="r", execution_time=1.0,
        ))
        _orig_generate = qe._monitor.generate_report
        qe._monitor.generate_report = lambda: type(  # type: ignore[method-assign]
            "R", (), {"to_dict": lambda self=None: report_data}
        )()
        try:
            qe_result = qe.gate(
                gate_thresholds={"A": 0.7, "B": 0.7, "C": 0.7}, dry_run=True,
            )
        finally:
            qe._monitor.generate_report = _orig_generate

        assert isinstance(qe_result, dict)  # dry_run=True always returns a dict
        for gate_id in ("A", "B", "C"):
            hg_passed = hg_result["groups"][gate_id]["passed"]
            qe_passed = qe_result["gate_results"][gate_id]["passed"]
            assert hg_passed == qe_passed, f"Gate {gate_id} verdict mismatch"

    def test_cli_gate_agrees_with_harness_gate(self, tmp_path):
        hg = _hg(A=0.9, B=0.5)
        report_data = {
            "accuracy_metrics": {
                "tcr": {"tcr": 90.0}, "accuracy_scores": {"overall_accuracy": 85.0},
            },
            "efficiency_metrics": {"latency": {"p95": 1.0}},
            "tasks": [],
            "extra_metrics": {"harness_groups": hg},
        }
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(report_data), encoding="utf-8")

        class _ReportProxy:
            def __init__(self, d):
                self.extra_metrics = d["extra_metrics"]

        hg_gate = HarnessEvaluationGate(
            _ReportProxy(report_data), group_thresholds={"A": 0.7, "B": 0.7},
        )
        hg_result = hg_gate.evaluate()

        args = argparse.Namespace(
            result_file=str(result_file), tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, fail_on_regression=None, baseline=None,
            baseline_version=None, save_baseline=False, junit_xml=None, golden_set=None,
            fail_on_golden_regression=False, gate_thresholds="A:0.7,B:0.7",
            required_gates=None, fail_on_gate_warn=False, min_gate_score=None,
            group_weights=None,
        )
        rc = cmd_gate(args)

        # B(0.5 < 0.7)가 실패이므로 HarnessEvaluationGate·CLI 둘 다 전체 실패로 판정해야 한다.
        assert hg_result["passed"] is False
        assert rc == 1


class TestCliGateThresholdsPath:
    """cli/gate.py --gate-thresholds 경로 자체의 직접 테스트 — 통합 전에는 이 경로에
    대한 전용 테스트가 없었다(간접적으로만 커버됨)."""

    def _write_result(self, tmp_path, hg):
        data = {
            "accuracy_metrics": {
                "tcr": {"tcr": 90.0}, "accuracy_scores": {"overall_accuracy": 85.0},
            },
            "efficiency_metrics": {"latency": {"p95": 1.0}},
            "tasks": [],
            "extra_metrics": {"harness_groups": hg},
        }
        path = tmp_path / "result.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _args(self, result_file, **overrides):
        base = dict(
            result_file=str(result_file), tcr=None, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None, fail_on_regression=None, baseline=None,
            baseline_version=None, save_baseline=False, junit_xml=None, golden_set=None,
            fail_on_golden_regression=False, gate_thresholds=None, required_gates=None,
            fail_on_gate_warn=False, min_gate_score=None, group_weights=None,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_exit_zero_when_all_gates_pass(self, tmp_path):
        result_file = self._write_result(tmp_path, _hg(A=0.9, B=0.8))
        args = self._args(result_file, gate_thresholds="A:0.7,B:0.7")
        assert cmd_gate(args) == 0

    def test_exit_one_when_a_gate_fails(self, tmp_path):
        result_file = self._write_result(tmp_path, _hg(A=0.9, B=0.4))
        args = self._args(result_file, gate_thresholds="A:0.7,B:0.7")
        assert cmd_gate(args) == 1

    def test_required_gates_restricts_scope(self, tmp_path):
        result_file = self._write_result(tmp_path, _hg(A=0.9, B=0.4))
        args = self._args(
            result_file, gate_thresholds="A:0.7,B:0.7", required_gates="A",
        )
        assert cmd_gate(args) == 0  # B는 검사 대상에서 제외됨

    def test_min_gate_score_used_as_fallback(self, tmp_path):
        # A는 gate_thresholds에 없으므로 min_gate_score(0.5)로 폴백 — 0.6 >= 0.5로 통과.
        # (min_gate_score는 별도로 복합 점수 체크도 함께 트리거하므로, 그 체크도 통과하도록
        # 같은 값을 쓴다 — 이 테스트가 검증하려는 건 gate_thresholds 폴백 하나뿐이다.)
        result_file = self._write_result(tmp_path, _hg(A=0.6))
        args = self._args(result_file, gate_thresholds="B:0.9", min_gate_score=0.5)
        assert cmd_gate(args) == 0

    def test_not_measured_gate_does_not_fail(self, tmp_path):
        result_file = self._write_result(tmp_path, _hg(A=None, B=0.9))
        args = self._args(result_file, gate_thresholds="A:0.7,B:0.7")
        assert cmd_gate(args) == 0
