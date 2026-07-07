"""
tests/test_spec025_version_aware_comparison.py
================================================
SPEC-025 REQ-1: ResultFile.prompt_version/agent_version 노출 + list_results 버전 필터.
SPEC-025 REQ-2: compare_results(group_by=...) — 버전 태그별 최신 파일 자동 그룹 비교.
SPEC-025 REQ-3: cli/gate.py --baseline-version — 버전별 독립 기준선.
SPEC-025 REQ-4: LLMJudge.judge_pairwise() — pairwise(A/B) 비교 + swap-check.
"""
from __future__ import annotations

import json
import os
import time
import warnings
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.integrations.llm_judge import LLMJudge
from agent_evaluator.serve.loader import load_results


def _save_run(tmp_path, filename: str, *, prompt_version=None, agent_version=None):
    monitor = PerformanceMonitor(
        output_dir=str(tmp_path),
        prompt_version=prompt_version,
        agent_version=agent_version,
    )
    monitor.record_task(
        create_taskresult(task_id="t1", question="q", response="r", execution_time=1.0)
    )
    monitor.save_to_file(filename)


def _save_run_with_tasks(tmp_path, filename: str, tasks: list):
    """SPEC-025 REQ-5: task_id별 question/response를 직접 지정해 저장 — 두 파일이
    같은 task_id를 공유해야 compare_results(detailed=True)의 공통 task 비교가 된다.

    Args:
        tasks: ``[{"task_id": ..., "question": ..., "response": ...}, ...]``
    """
    monitor = PerformanceMonitor(output_dir=str(tmp_path))
    for t in tasks:
        monitor.record_task(create_taskresult(
            task_id=t["task_id"], question=t["question"], response=t["response"],
            execution_time=1.0,
        ))
    monitor.save_to_file(filename)


def _call_compare(tmp_path, **query):
    from agent_evaluator.serve.routers.data import compare_results

    result_set = load_results(tmp_path)
    app_state = SimpleNamespace(result_set=result_set)
    app = SimpleNamespace(state=app_state)
    request = SimpleNamespace(app=app)
    defaults = dict(ids=None, detailed=False, group_by=None, pairwise=False)
    defaults.update(query)
    return compare_results(request, **defaults)


class TestResultFileVersionProperties:
    def test_prompt_and_agent_version_exposed(self, tmp_path):
        _save_run(tmp_path, "run_v2", prompt_version="v2-cot", agent_version="agent-2026-07")
        result_set = load_results(tmp_path)
        assert len(result_set.files) == 1
        rf = result_set.files[0]
        assert rf.prompt_version == "v2-cot"
        assert rf.agent_version == "agent-2026-07"

    def test_none_when_absent_not_error(self, tmp_path):
        """구버전 결과 파일(prompt_version/agent_version 미지정)에서는 None — 에러 아님."""
        _save_run(tmp_path, "run_legacy")
        result_set = load_results(tmp_path)
        rf = result_set.files[0]
        assert rf.prompt_version is None
        assert rf.agent_version is None

    def test_missing_extra_metrics_key_entirely(self):
        """extra_metrics 자체가 없는(더 오래된) raw dict에서도 에러 없이 None."""
        from agent_evaluator.serve.loader import ResultFile

        rf = ResultFile(
            path=None, file_id="f1", name="f1", timestamp="", total_tasks=0, tasks=[],
            accuracy_metrics={}, efficiency_metrics={},
            security_l1=SimpleNamespace(), security_l2=SimpleNamespace(),
            agentic=SimpleNamespace(), quality_detail=SimpleNamespace(),
            hallucination_detail=SimpleNamespace(), advanced=SimpleNamespace(),
            insights=SimpleNamespace(),
            rag_metrics={}, pricing={}, raw={},
        )
        assert rf.prompt_version is None
        assert rf.agent_version is None


class TestListResultsVersionFilter:
    def _call_list_results(self, tmp_path, **query):
        from agent_evaluator.serve.routers.data import list_results

        result_set = load_results(tmp_path)
        app_state = SimpleNamespace(result_set=result_set)
        app = SimpleNamespace(state=app_state)
        request = SimpleNamespace(app=app)
        defaults = dict(
            page=1, limit=50, sort_by="timestamp", sort_desc=True,
            tcr_min=None, tcr_max=None, accuracy_min=None, age_hours=None,
            prompt_version=None, agent_version=None, include_sample=False,
        )
        defaults.update(query)
        return list_results(request, **defaults)

    def test_filters_by_exact_prompt_version(self, tmp_path):
        _save_run(tmp_path, "run_v1", prompt_version="v1-few-shot")
        _save_run(tmp_path, "run_v2", prompt_version="v2-cot")

        result = self._call_list_results(tmp_path, prompt_version="v2-cot")
        names = [f["name"] for f in result["files"]]
        assert len(result["files"]) == 1
        assert "run_v2" in names

    def test_filters_by_exact_agent_version(self, tmp_path):
        _save_run(tmp_path, "run_a", agent_version="0.9.7")
        _save_run(tmp_path, "run_b", agent_version="0.9.8")

        result = self._call_list_results(tmp_path, agent_version="0.9.8")
        assert len(result["files"]) == 1
        assert result["files"][0]["name"] == "run_b"

    def test_no_filter_returns_all(self, tmp_path):
        _save_run(tmp_path, "run_a", prompt_version="v1")
        _save_run(tmp_path, "run_b", prompt_version="v2")

        result = self._call_list_results(tmp_path)
        assert len(result["files"]) == 2

    def test_meta_exposes_version_fields(self, tmp_path):
        _save_run(tmp_path, "run_v2", prompt_version="v2-cot", agent_version="agent-2026-07")
        result = self._call_list_results(tmp_path)
        entry = result["files"][0]
        assert entry["prompt_version"] == "v2-cot"
        assert entry["agent_version"] == "agent-2026-07"

    def test_meta_none_for_legacy_file(self, tmp_path):
        _save_run(tmp_path, "run_legacy")
        result = self._call_list_results(tmp_path)
        entry = result["files"][0]
        assert entry["prompt_version"] is None
        assert entry["agent_version"] is None


def _touch_mtime(tmp_path, filename: str, seconds_ago: float) -> None:
    """파일의 mtime을 명시적으로 과거로 되돌려, `max(..., key=mtime)` 선택 순서를
    파일시스템 mtime 해상도(1초 등)에 의존하지 않고 테스트에서 결정적으로 만든다."""
    path = tmp_path / f"{filename}.json"
    now = time.time()
    os.utime(path, (now - seconds_ago, now - seconds_ago))


class TestCompareResultsGroupBy:
    def _call_compare_results(self, tmp_path, **query):
        from agent_evaluator.serve.routers.data import compare_results

        result_set = load_results(tmp_path)
        app_state = SimpleNamespace(result_set=result_set)
        app = SimpleNamespace(state=app_state)
        request = SimpleNamespace(app=app)
        defaults = dict(ids=None, detailed=False, group_by=None, pairwise=False)
        defaults.update(query)
        return compare_results(request, **defaults)

    def test_group_by_picks_latest_per_version(self, tmp_path):
        _save_run(tmp_path, "v1_old", prompt_version="v1-few-shot")
        _save_run(tmp_path, "v1_new", prompt_version="v1-few-shot")
        _save_run(tmp_path, "v2_only", prompt_version="v2-cot")
        _touch_mtime(tmp_path, "v1_old", seconds_ago=100)
        _touch_mtime(tmp_path, "v1_new", seconds_ago=1)
        _touch_mtime(tmp_path, "v2_only", seconds_ago=1)

        result = self._call_compare_results(tmp_path, group_by="prompt_version")
        names = {f["name"] for f in result["files"]}
        assert result["file_count"] == 2
        # v1-few-shot 그룹에서는 최신 파일(v1_new)만 선택되어야 한다.
        assert names == {"v1_new", "v2_only"}

    def test_group_by_excludes_files_without_tag(self, tmp_path):
        _save_run(tmp_path, "tagged", prompt_version="v1")
        _save_run(tmp_path, "untagged")

        result = self._call_compare_results(tmp_path, group_by="prompt_version")
        assert result["file_count"] == 1
        assert result["files"][0]["name"] == "tagged"

    def test_group_by_computes_delta(self, tmp_path):
        _save_run(tmp_path, "v1", prompt_version="v1")
        _save_run(tmp_path, "v2", prompt_version="v2")

        result = self._call_compare_results(tmp_path, group_by="prompt_version")
        assert len(result["delta"]) == 1
        assert "tcr_delta" in result["delta"][0]

    def test_invalid_group_by_field_raises_400(self, tmp_path):
        _save_run(tmp_path, "v1", prompt_version="v1")
        with pytest.raises(HTTPException) as exc_info:
            self._call_compare_results(tmp_path, group_by="not_a_real_field")
        assert exc_info.value.status_code == 400

    def test_ids_takes_precedence_over_group_by(self, tmp_path):
        _save_run(tmp_path, "v1", prompt_version="v1")
        _save_run(tmp_path, "v2", prompt_version="v2")
        result_set = load_results(tmp_path)
        v1_id = next(f.file_id for f in result_set.files if f.name == "v1")

        result = self._call_compare_results(
            tmp_path, ids=v1_id, group_by="prompt_version",
        )
        assert result["file_count"] == 1
        assert result["files"][0]["name"] == "v1"

    def test_neither_ids_nor_group_by_raises_400(self, tmp_path):
        _save_run(tmp_path, "v1", prompt_version="v1")
        with pytest.raises(HTTPException) as exc_info:
            self._call_compare_results(tmp_path)
        assert exc_info.value.status_code == 400

    def test_group_by_agent_version(self, tmp_path):
        _save_run(tmp_path, "a", agent_version="0.9.7")
        _save_run(tmp_path, "b", agent_version="0.9.8")

        result = self._call_compare_results(tmp_path, group_by="agent_version")
        assert result["file_count"] == 2


class TestComparePairwise:
    """SPEC-025 REQ-5: compare_results(detailed=True, pairwise=True) — win_rate 요약."""

    def _two_files_with_common_tasks(self, tmp_path, n=3):
        tasks = [
            {"task_id": f"t{i}", "question": f"q{i}", "response": f"r{i}"} for i in range(n)
        ]
        _save_run_with_tasks(tmp_path, "file_a", tasks)
        _save_run_with_tasks(tmp_path, "file_b", tasks)
        result_set = load_results(tmp_path)
        ids = ",".join(f.file_id for f in sorted(result_set.files, key=lambda f: f.name))
        return ids

    def test_pairwise_false_omits_key(self, tmp_path):
        ids = self._two_files_with_common_tasks(tmp_path)
        result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=False)
        assert "pairwise" not in result

    def test_pairwise_without_detailed_omits_key(self, tmp_path):
        """detailed=False면 pairwise=True를 줘도 무시된다 — REQ-5는 detailed 블록 안에서만 동작."""
        ids = self._two_files_with_common_tasks(tmp_path)
        result = _call_compare(tmp_path, ids=ids, detailed=False, pairwise=True)
        assert "pairwise" not in result

    def test_pairwise_all_wins_a(self, tmp_path):
        ids = self._two_files_with_common_tasks(tmp_path, n=3)
        with patch.object(
            LLMJudge, "judge_pairwise",
            lambda self, *a, **kw: {"skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.0},
        ):
            result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=True)
        pw = result["pairwise"]
        assert pw["wins_a"] == 3
        assert pw["wins_b"] == 0
        assert pw["ties"] == 0
        assert pw["judged_count"] == 3
        assert pw["win_rate"] == 1.0

    def test_pairwise_tie_counts_as_half_win(self, tmp_path):
        ids = self._two_files_with_common_tasks(tmp_path, n=2)
        with patch.object(
            LLMJudge, "judge_pairwise",
            lambda self, *a, **kw: {"skipped": False, "winner": "tie", "reasoning": "r", "cost_usd": 0.0},
        ):
            result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=True)
        pw = result["pairwise"]
        assert pw["ties"] == 2
        assert pw["win_rate"] == 0.5

    def test_pairwise_skips_errored_tasks(self, tmp_path):
        ids = self._two_files_with_common_tasks(tmp_path, n=2)
        calls = []

        def fake_judge_pairwise(self, question, response_a, response_b, *a, **kw):
            calls.append(question)
            if len(calls) == 1:
                return {"skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.0}
            return {"skipped": False, "error": "boom", "winner": None, "cost_usd": 0.0}

        with patch.object(LLMJudge, "judge_pairwise", fake_judge_pairwise):
            result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=True)
        pw = result["pairwise"]
        assert pw["judged_count"] == 1
        assert pw["wins_a"] == 1
        assert len(pw["per_task"]) == 1

    def test_pairwise_no_common_tasks_win_rate_none(self, tmp_path):
        _save_run_with_tasks(tmp_path, "only_a", [{"task_id": "x1", "question": "q", "response": "r"}])
        _save_run_with_tasks(tmp_path, "only_b", [{"task_id": "y1", "question": "q", "response": "r"}])
        result_set = load_results(tmp_path)
        ids = ",".join(f.file_id for f in sorted(result_set.files, key=lambda f: f.name))

        result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=True)
        pw = result["pairwise"]
        assert pw["judged_count"] == 0
        assert pw["win_rate"] is None

    def test_regression_improvement_lists_unaffected_by_pairwise(self, tmp_path):
        """REQ-5는 기존 accuracy_delta 기반 regression_tasks/improvement_tasks를
        대체하지 않고 병행 제공해야 한다."""
        ids = self._two_files_with_common_tasks(tmp_path, n=2)
        with patch.object(
            LLMJudge, "judge_pairwise",
            lambda self, *a, **kw: {"skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.0},
        ):
            result = _call_compare(tmp_path, ids=ids, detailed=True, pairwise=True)
        assert "regression_tasks" in result
        assert "improvement_tasks" in result
        assert "pairwise" in result


class TestGateBaselineVersion:
    """SPEC-025 REQ-3: agent-eval gate --baseline-version — 버전별 독립 기준선."""

    def test_baseline_version_path_helper(self, tmp_path):
        from agent_evaluator.cli.gate import _baseline_version_path

        result_file = tmp_path / "run.json"
        path = _baseline_version_path(result_file, "v2-cot")
        assert path == tmp_path / "baselines" / "v2-cot.json"

    def test_save_baseline_version_writes_to_baselines_subdir(self, tmp_path):
        from agent_evaluator.cli.gate import _load_baseline, cmd_gate
        from tests.test_coverage_cli_gate import _make_args, _make_result_data

        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.9)), encoding="utf-8")
        args = _make_args(result_file=str(f), save_baseline=True, baseline_version="v2-cot")
        rc = cmd_gate(args)
        assert rc == 0

        # 버전별 기준선 파일은 baselines/<tag>.json에 저장되고, 기본 baseline.json은 생성되지 않는다.
        assert (tmp_path / "baselines" / "v2-cot.json").is_file()
        assert not (tmp_path / "baseline.json").exists()
        baseline = _load_baseline(tmp_path / "baselines" / "v2-cot.json")
        assert baseline["tcr"] == pytest.approx(90.0)

    def test_two_versions_stay_independent(self, tmp_path):
        from agent_evaluator.cli.gate import _load_baseline, cmd_gate
        from tests.test_coverage_cli_gate import _make_args, _make_result_data

        f1 = tmp_path / "run_v1.json"
        f1.write_text(json.dumps(_make_result_data(tcr=0.80)), encoding="utf-8")
        f2 = tmp_path / "run_v2.json"
        f2.write_text(json.dumps(_make_result_data(tcr=0.95)), encoding="utf-8")

        cmd_gate(_make_args(result_file=str(f1), save_baseline=True, baseline_version="v1"))
        cmd_gate(_make_args(result_file=str(f2), save_baseline=True, baseline_version="v2"))

        baseline_v1 = _load_baseline(tmp_path / "baselines" / "v1.json")
        baseline_v2 = _load_baseline(tmp_path / "baselines" / "v2.json")
        assert baseline_v1["tcr"] == pytest.approx(80.0)
        assert baseline_v2["tcr"] == pytest.approx(95.0)

    def test_regression_check_uses_versioned_baseline(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args, _make_result_data

        baseline_f = tmp_path / "baseline_run.json"
        baseline_f.write_text(json.dumps(_make_result_data(tcr=0.95)), encoding="utf-8")
        cmd_gate(_make_args(result_file=str(baseline_f), save_baseline=True, baseline_version="v2-cot"))

        # 같은 버전의 후속 실행에서 TCR이 크게 떨어짐 — 회귀로 잡혀야 한다.
        later_f = tmp_path / "later_run.json"
        later_f.write_text(json.dumps(_make_result_data(tcr=0.70)), encoding="utf-8")
        rc = cmd_gate(_make_args(
            result_file=str(later_f), baseline_version="v2-cot", fail_on_regression=5.0,
        ))
        assert rc == 2

    def test_explicit_baseline_takes_precedence_over_version(self, tmp_path):
        """--baseline(명시적 경로)이 지정되면 --baseline-version은 무시된다."""
        from agent_evaluator.cli.gate import _load_baseline, cmd_gate
        from tests.test_coverage_cli_gate import _make_args, _make_result_data

        explicit_path = tmp_path / "custom_baseline.json"
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.9)), encoding="utf-8")
        args = _make_args(
            result_file=str(f), save_baseline=True,
            baseline=str(explicit_path), baseline_version="v2-cot",
        )
        cmd_gate(args)

        assert explicit_path.is_file()
        assert not (tmp_path / "baselines" / "v2-cot.json").exists()
        assert _load_baseline(explicit_path) is not None

    def test_no_baseline_version_falls_back_to_default_path(self, tmp_path):
        """--baseline-version 미지정 시 기존 baseline.json 단일 경로 — 하위호환."""
        from agent_evaluator.cli.gate import _load_baseline, cmd_gate
        from tests.test_coverage_cli_gate import _make_args, _make_result_data

        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.9)), encoding="utf-8")
        cmd_gate(_make_args(result_file=str(f), save_baseline=True))

        assert (tmp_path / "baseline.json").is_file()
        assert not (tmp_path / "baselines").exists()
        assert _load_baseline(tmp_path / "baseline.json") is not None


class TestCheckGoldenRegressions:
    """SPEC-025 REQ-6: cli/gate.py._check_golden_regressions — 순수 매칭 로직."""

    def test_matched_and_successful_is_not_a_regression(self):
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"task_id": "t1", "question": "q1", "ground_truth": "a1"}]
        tasks = [{"task_id": "t1", "question": "q1", "success": True}]
        assert _check_golden_regressions(golden, tasks) == []

    def test_missing_task_id_flagged_as_missing(self):
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"task_id": "t1", "question": "q1"}]
        tasks = [{"task_id": "t2", "question": "other", "success": True}]
        result = _check_golden_regressions(golden, tasks)
        assert len(result) == 1
        assert result[0]["reason"] == "missing"
        assert result[0]["task_id"] == "t1"

    def test_matched_but_failed_flagged_as_failed(self):
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"task_id": "t1", "question": "q1"}]
        tasks = [{"task_id": "t1", "question": "q1", "success": False}]
        result = _check_golden_regressions(golden, tasks)
        assert len(result) == 1
        assert result[0]["reason"] == "failed"

    def test_question_fallback_when_no_task_id(self):
        """골든셋 케이스에 task_id가 없으면 question 텍스트 완전 일치로 매칭한다."""
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"question": "한국의 수도는?"}]
        tasks = [{"task_id": "t9", "question": "한국의 수도는?", "success": True}]
        assert _check_golden_regressions(golden, tasks) == []

    def test_missing_success_key_treated_as_failure(self):
        """success 키 자체가 없으면(비정상 데이터) 안전하게 회귀로 처리한다."""
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"task_id": "t1", "question": "q1"}]
        tasks = [{"task_id": "t1", "question": "q1"}]
        result = _check_golden_regressions(golden, tasks)
        assert len(result) == 1
        assert result[0]["reason"] == "failed"

    def test_empty_golden_set_no_regressions(self):
        from agent_evaluator.cli.gate import _check_golden_regressions

        assert _check_golden_regressions([], [{"task_id": "t1", "success": True}]) == []

    def test_non_dict_case_and_task_ignored(self):
        """리스트 안에 dict가 아닌 원소가 섞여도 크래시하지 않아야 한다."""
        from agent_evaluator.cli.gate import _check_golden_regressions

        golden = [{"task_id": "t1", "question": "q1"}, "not-a-dict"]
        tasks = [{"task_id": "t1", "question": "q1", "success": True}, "also-not-a-dict"]
        assert _check_golden_regressions(golden, tasks) == []


class TestLoadGoldenSet:
    """SPEC-025 REQ-6: cli/gate.py._load_golden_set."""

    def test_loads_list_json(self, tmp_path):
        from agent_evaluator.cli.gate import _load_golden_set

        p = tmp_path / "golden.json"
        p.write_text(json.dumps([{"task_id": "t1", "question": "q"}]), encoding="utf-8")
        result = _load_golden_set(p)
        assert result == [{"task_id": "t1", "question": "q"}]

    def test_non_list_json_returns_empty(self, tmp_path):
        from agent_evaluator.cli.gate import _load_golden_set

        p = tmp_path / "golden.json"
        p.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        assert _load_golden_set(p) == []

    def test_missing_file_raises(self, tmp_path):
        from agent_evaluator.cli.gate import _load_golden_set

        with pytest.raises(OSError):
            _load_golden_set(tmp_path / "nonexistent.json")

    def test_malformed_json_raises(self, tmp_path):
        from agent_evaluator.cli.gate import _load_golden_set

        p = tmp_path / "golden.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            _load_golden_set(p)


class TestCmdGateGoldenSet:
    """SPEC-025 REQ-6: agent-eval gate --golden-set / --fail-on-golden-regression 통합."""

    def _write_result(self, tmp_path, name, tasks):
        from tests.test_coverage_cli_gate import _make_result_data

        data = _make_result_data(tcr=0.9)
        data["tasks"] = tasks
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def _write_golden(self, tmp_path, name, cases):
        p = tmp_path / name
        p.write_text(json.dumps(cases), encoding="utf-8")
        return p

    def test_nonexistent_golden_set_file_returns_1(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [])
        rc = cmd_gate(_make_args(result_file=str(f), golden_set=str(tmp_path / "nope.json")))
        assert rc == 1

    def test_malformed_golden_set_returns_1(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [])
        g = tmp_path / "golden.json"
        g.write_text("{bad json", encoding="utf-8")
        rc = cmd_gate(_make_args(result_file=str(f), golden_set=str(g)))
        assert rc == 1

    def test_all_cases_pass_without_fail_flag_exits_0(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [
            {"task_id": "t1", "question": "q1", "success": True},
        ])
        g = self._write_golden(tmp_path, "golden.json", [{"task_id": "t1", "question": "q1"}])
        rc = cmd_gate(_make_args(result_file=str(f), golden_set=str(g)))
        assert rc == 0

    def test_regression_without_fail_flag_does_not_change_exit_code(self, tmp_path):
        """--fail-on-golden-regression 없이 --golden-set만 주면 보고만 하고 게이팅엔 영향 없다."""
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [
            {"task_id": "t1", "question": "q1", "success": False},
        ])
        g = self._write_golden(tmp_path, "golden.json", [{"task_id": "t1", "question": "q1"}])
        rc = cmd_gate(_make_args(result_file=str(f), golden_set=str(g)))
        assert rc == 0

    def test_regression_with_fail_flag_returns_3(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [
            {"task_id": "t1", "question": "q1", "success": False},
        ])
        g = self._write_golden(tmp_path, "golden.json", [{"task_id": "t1", "question": "q1"}])
        rc = cmd_gate(_make_args(
            result_file=str(f), golden_set=str(g), fail_on_golden_regression=True,
        ))
        assert rc == 3

    def test_missing_case_with_fail_flag_returns_3(self, tmp_path):
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [])
        g = self._write_golden(tmp_path, "golden.json", [{"task_id": "t1", "question": "q1"}])
        rc = cmd_gate(_make_args(
            result_file=str(f), golden_set=str(g), fail_on_golden_regression=True,
        ))
        assert rc == 3

    def test_no_golden_set_flag_is_a_noop(self, tmp_path):
        """--golden-set 미지정 시 기존 동작과 100% 동일 — 하위호환."""
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [
            {"task_id": "t1", "question": "q1", "success": False},
        ])
        rc = cmd_gate(_make_args(result_file=str(f), fail_on_golden_regression=True))
        assert rc == 0

    def test_regular_metric_gate_still_takes_effect_alongside_golden_set(self, tmp_path):
        """골든셋 게이트가 기존 --tcr 등 지표 게이팅과 독립적으로 병행 동작해야 한다."""
        from agent_evaluator.cli.gate import cmd_gate
        from tests.test_coverage_cli_gate import _make_args

        f = self._write_result(tmp_path, "result.json", [
            {"task_id": "t1", "question": "q1", "success": True},
        ])
        g = self._write_golden(tmp_path, "golden.json", [{"task_id": "t1", "question": "q1"}])
        # tcr=0.9(90%)인데 --tcr 95 지정 → 골든셋과 무관하게 지표 미달로 1
        rc = cmd_gate(_make_args(result_file=str(f), golden_set=str(g), tcr=95.0))
        assert rc == 1


class TestPairwiseJudgeDispatch:
    """SPEC-025 REQ-4: LLMJudge._call_pairwise_judge — provider 분기."""

    def test_claude_dispatch(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        called = []
        judge._call_claude_pairwise = (
            lambda *a, **kw: called.append("claude") or {"winner": "a", "skipped": False, "cost_usd": 0.0}
        )
        judge._call_pairwise_judge("Q", "resp a", "resp b", None)
        assert "claude" in called

    def test_openai_dispatch(self):
        judge = LLMJudge(model="gpt-4o-mini")
        called = []
        judge._call_openai_pairwise = (
            lambda *a, **kw: called.append("openai") or {"winner": "a", "skipped": False, "cost_usd": 0.0}
        )
        judge._call_pairwise_judge("Q", "resp a", "resp b", None)
        assert "openai" in called

    def test_unsupported_model_error(self):
        judge = LLMJudge(model="some-unknown-model")
        result = judge._call_pairwise_judge("Q", "a", "b", None)
        assert result.get("error") is not None
        assert "Unsupported model" in result["error"]


class TestParsePairwiseResponse:
    """SPEC-025 REQ-4: LLMJudge._parse_pairwise_response."""

    def test_basic_parse(self):
        judge = LLMJudge(model="gpt-4o-mini")
        raw = json.dumps({"winner": "a", "reasoning": "A is more complete."})
        result = judge._parse_pairwise_response(raw, cost=0.001)
        assert result["winner"] == "a"
        assert result["reasoning"] == "A is more complete."
        assert result["cost_usd"] == 0.001

    def test_winner_case_insensitive(self):
        judge = LLMJudge(model="gpt-4o-mini")
        raw = json.dumps({"winner": "B", "reasoning": "..."})
        result = judge._parse_pairwise_response(raw, cost=0.0)
        assert result["winner"] == "b"

    def test_invalid_winner_value_becomes_tie(self):
        """알 수 없는 winner 값은 임의로 승자를 선언하지 않고 tie로 처리한다."""
        judge = LLMJudge(model="gpt-4o-mini")
        raw = json.dumps({"winner": "c", "reasoning": "..."})
        result = judge._parse_pairwise_response(raw, cost=0.0)
        assert result["winner"] == "tie"

    def test_markdown_fence_stripped(self):
        judge = LLMJudge(model="gpt-4o-mini")
        raw = "```json\n" + json.dumps({"winner": "tie", "reasoning": "equal"}) + "\n```"
        result = judge._parse_pairwise_response(raw, cost=0.0)
        assert result["winner"] == "tie"

    def test_parse_error_returns_error_key(self):
        judge = LLMJudge(model="gpt-4o-mini")
        result = judge._parse_pairwise_response("not json", cost=0.0)
        assert result.get("error") is not None
        assert result["winner"] is None


class TestCallPairwiseNoKey:
    """SPEC-025 REQ-4: _call_claude_pairwise/_call_openai_pairwise — API 키 없을 때."""

    def test_claude_no_api_key_returns_error(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = judge._call_claude_pairwise("Q", "a", "b", None)
        assert result.get("winner") is None
        assert "ANTHROPIC_API_KEY" in (result.get("error") or "")

    def test_openai_no_api_key_returns_error(self):
        judge = LLMJudge(model="gpt-4o-mini")
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            result = judge._call_openai_pairwise("Q", "a", "b", None)
        assert result.get("winner") is None
        assert "OPENAI_API_KEY" in (result.get("error") or "")


class TestJudgePairwise:
    """SPEC-025 REQ-4: LLMJudge.judge_pairwise() — swap-check 결합 로직 + 안전장치."""

    def test_swap_check_agrees_returns_winner(self):
        judge = LLMJudge(model="gpt-4o-mini")
        calls = []

        def fake_call(question, resp_x, resp_y, context, **kw):
            calls.append((resp_x, resp_y))
            # 1차: (A, B) 순서 그대로 → "a" 승리
            # 2차: (B, A)로 뒤집힘 → 원래 A 내용이 이제 슬롯 b에 있으므로 "b" 응답이면 합의
            winner = "a" if len(calls) == 1 else "b"
            return {"skipped": False, "winner": winner, "reasoning": "r", "cost_usd": 0.001, "model": "gpt-4o-mini"}

        judge._call_pairwise_judge = fake_call
        result = judge.judge_pairwise("Q", "resp A text", "resp B text")
        assert result["winner"] == "a"
        assert result["swap_check"] is True
        assert len(calls) == 2
        assert calls[1] == ("resp B text", "resp A text")

    def test_swap_check_disagrees_returns_tie(self):
        """두 번 다 같은 슬롯(a)이 이겼다고 답하면(포지션 편향 신호) tie로 수렴한다."""
        judge = LLMJudge(model="gpt-4o-mini")

        judge._call_pairwise_judge = lambda *a, **kw: {
            "skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.0, "model": "gpt-4o-mini",
        }
        result = judge.judge_pairwise("Q", "A text", "B text")
        assert result["winner"] == "tie"
        assert result["swap_check"] is True

    def test_swap_check_false_skips_second_call(self):
        judge = LLMJudge(model="gpt-4o-mini")
        calls = []

        def fake_call(question, resp_x, resp_y, context, **kw):
            calls.append((resp_x, resp_y))
            return {"skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.001, "model": "gpt-4o-mini"}

        judge._call_pairwise_judge = fake_call
        result = judge.judge_pairwise("Q", "A text", "B text", swap_check=False)
        assert result["winner"] == "a"
        assert result["swap_check"] is False
        assert len(calls) == 1

    def test_second_call_error_falls_back_to_first(self):
        judge = LLMJudge(model="gpt-4o-mini")
        calls = []

        def fake_call(question, resp_x, resp_y, context, **kw):
            calls.append((resp_x, resp_y))
            if len(calls) == 1:
                return {"skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.001, "model": "gpt-4o-mini"}
            return {"skipped": False, "error": "network blip", "winner": None, "cost_usd": 0.0, "model": "gpt-4o-mini"}

        judge._call_pairwise_judge = fake_call
        result = judge.judge_pairwise("Q", "A text", "B text")
        assert result["winner"] == "a"
        assert result["swap_check"] is False
        assert result["swap_check_error"] == "network blip"
        assert not result.get("error")
        assert judge._consecutive_errors == 0

    def test_first_call_error_returned_directly(self):
        judge = LLMJudge(model="gpt-4o-mini")
        calls = []

        def fake_call(question, resp_x, resp_y, context, **kw):
            calls.append((resp_x, resp_y))
            return {"skipped": False, "error": "boom", "winner": None, "cost_usd": 0.0, "model": "gpt-4o-mini"}

        judge._call_pairwise_judge = fake_call
        result = judge.judge_pairwise("Q", "A text", "B text")
        assert result.get("error") == "boom"
        assert result["swap_check"] is False
        assert len(calls) == 1  # 2차(swap) 호출은 시도되지 않는다

    def test_budget_exceeded_skips(self):
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=0.001)
        judge._budget_spent = 999.0
        judge._budget_day = date.today()
        with warnings.catch_warnings(record=True):
            result = judge.judge_pairwise("Q", "A", "B")
        assert result.get("skipped") is True
        assert result.get("reason") == "budget_exceeded"

    def test_disabled_reason_skips_immediately(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge._disabled_reason = "auto_disabled_after_3_errors"
        result = judge.judge_pairwise("Q", "A", "B")
        assert result.get("skipped") is True
        assert result.get("reason") == "auto_disabled_after_3_errors"

    def test_pairwise_results_separate_from_absolute_results(self):
        """pairwise 이력은 judge()의 절대 스코어 이력(self.results)과 분리되어야 하고,
        get_summary()의 절대 스코어 집계를 오염시키지 않아야 한다."""
        judge = LLMJudge(model="gpt-4o-mini")
        judge._call_pairwise_judge = lambda *a, **kw: {
            "skipped": False, "winner": "a", "reasoning": "r", "cost_usd": 0.001, "model": "gpt-4o-mini",
        }
        judge.judge_pairwise("Q", "A", "B", swap_check=False)
        assert len(judge.pairwise_results) == 1
        assert judge.results == []
        assert judge.get_summary()["count"] == 0

    def test_consecutive_pairwise_errors_disable_judge(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge._call_pairwise_judge = lambda *a, **kw: {
            "skipped": False, "error": "boom", "winner": None, "cost_usd": 0.0, "model": "gpt-4o-mini",
        }
        with warnings.catch_warnings(record=True):
            for _ in range(3):
                judge.judge_pairwise("Q", "A", "B", swap_check=False)
        assert judge._disabled_reason is not None

        result = judge.judge_pairwise("Q", "A", "B")
        assert result.get("skipped") is True
