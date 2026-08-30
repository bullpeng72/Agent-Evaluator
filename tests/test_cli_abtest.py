"""
tests/test_cli_abtest.py
============================
`agent-eval abtest` CLI — 결과 JSON 파일 2개 이상을 통계적으로 비교.

이 서브커맨드는 QuickEval.ab_test()/ab_test_nway()/ab_test_sequential()을 감싸는
얇은 레이어다 — 새 통계 로직은 없으므로, 여기서는 ① 파일 로딩·모드 자동 선택
(2 파일 vs 3+ 파일)·에러 처리 배선이 올바른지, ② CLI 전용 검증(guardrail 형식,
--sequential+--tau 필수, 옵션 조합 제약)이 맞는지만 확인한다.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.cli.abtest import (
    _parse_guardrail,
    _variant_names,
    cmd_abtest,
)


def _ns(**kwargs) -> argparse.Namespace:
    defaults = dict(
        metric="accuracy_score",
        guardrail=None,
        sequential=False,
        tau=None,
        alpha=0.05,
        fdr_alpha=0.05,
        min_samples=30,
        json=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_result_file(tmp_path, name: str, values: list[float], metric_key: str = "execution_time"):
    monitor = PerformanceMonitor(output_dir=str(tmp_path))
    for i, v in enumerate(values):
        kwargs: dict[str, Any] = dict(
            task_id=f"t{i}", question=f"q{i}", response="r", ground_truth="r",
            execution_time=1.0, task_type="qa",
        )
        if metric_key == "execution_time":
            kwargs["execution_time"] = v
        else:
            kwargs["extra"] = {metric_key: v}
        monitor.record_task(create_taskresult(**kwargs))
    path = tmp_path / name
    monitor.save_to_file(str(path))
    return str(path) + ".json"


class TestGuardrailParsing:
    def test_valid_guardrail(self):
        g = _parse_guardrail("latency_ms:lower_is_better:0.5")
        assert g == {"metric": "latency_ms", "direction": "lower_is_better", "max_regression": 0.5}

    def test_invalid_format_wrong_part_count(self):
        with pytest.raises(ValueError, match="Invalid --guardrail format"):
            _parse_guardrail("latency_ms:0.5")

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            _parse_guardrail("latency_ms:sideways:0.5")


class TestVariantNames:
    def test_unique_stems_used_as_is(self):
        names = _variant_names(["results/v1.json", "results/v2.json"])
        assert names == ["v1", "v2"]

    def test_colliding_stems_fall_back_to_full_path(self):
        names = _variant_names(["a/v1.json", "b/v1.json"])
        assert names == ["a/v1.json", "b/v1.json"]


class TestTwoWayAbTest:
    def test_basic_comparison_succeeds(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9, 1.1, 0.95, 1.05] * 8)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4, 1.6, 1.45, 1.55] * 8)
        code = cmd_abtest(_ns(result_files=[f1, f2], metric="execution_time"))
        assert code == 0
        out = capsys.readouterr().out
        assert "A/B Test" in out
        assert "execution_time" in out

    def test_json_output_is_valid_json_with_expected_keys(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9, 1.1, 0.95, 1.05] * 8)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4, 1.6, 1.45, 1.55] * 8)
        code = cmd_abtest(_ns(result_files=[f1, f2], metric="execution_time", json=True))
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload.keys()) >= {
            "metric", "self_mean", "other_mean", "delta", "better",
            "significant", "sample_sizes",
        }

    def test_custom_extra_metric_fallback(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [0.5] * 10, metric_key="custom_cost")
        f2 = _make_result_file(tmp_path, "v2", [0.8] * 10, metric_key="custom_cost")
        code = cmd_abtest(_ns(result_files=[f1, f2], metric="custom_cost"))
        assert code == 0
        out = capsys.readouterr().out
        assert "custom_cost" in out

    def test_guardrail_applied(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 10)
        f2 = _make_result_file(tmp_path, "v2", [1.0] * 10)
        code = cmd_abtest(_ns(
            result_files=[f1, f2],
            guardrail=["execution_time:lower_is_better:0.5"],
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Guardrail" in out

    def test_invalid_guardrail_format_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 10)
        f2 = _make_result_file(tmp_path, "v2", [1.0] * 10)
        code = cmd_abtest(_ns(result_files=[f1, f2], guardrail=["bogus"]))
        assert code == 1
        assert "Invalid --guardrail format" in capsys.readouterr().err

    def test_mde_line_shown_for_proportion_metric_and_underpower_warning(self, tmp_path, capsys):
        # accuracy_score is proportion-like; tiny near-identical samples -> underpowered
        f1 = _make_result_file(tmp_path, "v1", [0.8, 0.9] * 6, metric_key="accuracy_score")
        f2 = _make_result_file(tmp_path, "v2", [0.85, 0.85] * 6, metric_key="accuracy_score")
        code = cmd_abtest(_ns(result_files=[f1, f2], metric="accuracy_score"))
        assert code == 0
        out = capsys.readouterr().out
        assert "min detectable effect" in out
        assert "underpowered" in out

    def test_mde_line_skipped_for_non_proportion_metric(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 1.2] * 8)
        f2 = _make_result_file(tmp_path, "v2", [3.0, 3.2] * 8)
        code = cmd_abtest(_ns(result_files=[f1, f2], metric="execution_time"))
        assert code == 0
        assert "min detectable effect" not in capsys.readouterr().out


class TestSequentialAbTest:
    def test_missing_tau_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9] * 5)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4] * 5)
        code = cmd_abtest(_ns(result_files=[f1, f2], sequential=True, tau=None))
        assert code == 1
        assert "tau" in capsys.readouterr().err

    def test_sequential_with_tau_succeeds(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9, 1.1, 0.95, 1.05] * 4)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4, 1.6, 1.45, 1.55] * 4)
        code = cmd_abtest(_ns(
            result_files=[f1, f2], metric="execution_time", sequential=True, tau=0.1,
        ))
        assert code == 0
        out = capsys.readouterr().out
        assert "Sequential" in out or "mSPRT" in out

    def test_sequential_with_3_files_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 5)
        f2 = _make_result_file(tmp_path, "v2", [1.0] * 5)
        f3 = _make_result_file(tmp_path, "v3", [1.0] * 5)
        code = cmd_abtest(_ns(result_files=[f1, f2, f3], sequential=True, tau=0.1))
        assert code == 1
        assert "exactly 2 result files" in capsys.readouterr().err


class TestNwayAbTest:
    def test_three_files_uses_nway(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9, 1.1, 0.95, 1.05] * 4)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4, 1.6, 1.45, 1.55] * 4)
        f3 = _make_result_file(tmp_path, "v3", [1.2, 1.1, 1.3, 1.15, 1.25] * 4)
        code = cmd_abtest(_ns(result_files=[f1, f2, f3], metric="execution_time"))
        assert code == 0
        out = capsys.readouterr().out
        assert "N-way" in out
        assert "Pairwise" in out

    def test_nway_json_has_fdr_fields(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0, 0.9, 1.1, 0.95, 1.05] * 4)
        f2 = _make_result_file(tmp_path, "v2", [1.5, 1.4, 1.6, 1.45, 1.55] * 4)
        f3 = _make_result_file(tmp_path, "v3", [1.2, 1.1, 1.3, 1.15, 1.25] * 4)
        code = cmd_abtest(_ns(result_files=[f1, f2, f3], metric="execution_time", json=True))
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fdr_method"] == "benjamini_hochberg"
        assert len(payload["pairwise"]) == 3  # C(3,2)

    def test_guardrail_with_3_files_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 5)
        f2 = _make_result_file(tmp_path, "v2", [1.0] * 5)
        f3 = _make_result_file(tmp_path, "v3", [1.0] * 5)
        code = cmd_abtest(_ns(
            result_files=[f1, f2, f3],
            guardrail=["execution_time:lower_is_better:0.5"],
        ))
        assert code == 1
        assert "exactly 2 result files" in capsys.readouterr().err


class TestFileErrors:
    def test_single_file_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 5)
        code = cmd_abtest(_ns(result_files=[f1]))
        assert code == 1
        assert "At least 2 result files" in capsys.readouterr().err

    def test_nonexistent_file_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 5)
        code = cmd_abtest(_ns(result_files=[f1, str(tmp_path / "nope.json")]))
        assert code == 1
        assert "Could not read result file" in capsys.readouterr().err

    def test_malformed_json_exits_1(self, tmp_path, capsys):
        f1 = _make_result_file(tmp_path, "v1", [1.0] * 5)
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        code = cmd_abtest(_ns(result_files=[f1, str(bad)]))
        assert code == 1
        assert "Could not read result file" in capsys.readouterr().err


class TestSubparserRegistration:
    def test_abtest_importable_from_main(self):
        # cli/main.py imports build_abtest_subparser/cmd_abtest at module load time —
        # a failed import here would break `agent-eval` entirely, so this just
        # confirms the wiring in main.py's import line is intact. getattr(), not a
        # static `from`/attribute reference, since main.py re-exports these from
        # cli/abtest.py rather than declaring them as its own public API (Pylance's
        # reportPrivateImportUsage flags any static reference to a bare re-export).
        from agent_evaluator.cli import main as main_module
        assert getattr(main_module, "build_abtest_subparser", None) is not None
        assert getattr(main_module, "cmd_abtest", None) is not None

    def test_parser_accepts_expected_arguments(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        from agent_evaluator.cli.abtest import build_abtest_subparser
        build_abtest_subparser(sub)
        args = parser.parse_args(["abtest", "a.json", "b.json", "--tau", "0.1"])
        assert args.command == "abtest"
        assert args.result_files == ["a.json", "b.json"]
        assert args.tau == 0.1
