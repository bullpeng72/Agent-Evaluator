"""
tests/test_harness_groups_schema.py
=====================================
Phase 1 (계약 굳히기) — extra_metrics.harness_groups의 출력 계약(schemas/
harness_groups.schema.json) contract test.

실제 PerformanceMonitor가 낸 리포트를 스키마로 검증한다 — 필드 rename·삭제·타입
변경이 CI에서 바로 잡히게 하는 게 목적이다(과거 tool_coverage 명명 혼동 같은 사고를
구조적으로 막는다). 스키마 자체가 바뀌어야 하는 의도된 변경이면 schemas/
harness_groups.schema.json을 함께 고친다 — 이 테스트가 실패하는 게 "버그"가 아니라
"계약 변경을 스키마에 반영하라"는 신호일 수 있다.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import jsonschema.validators  # noqa: F401 — submodule attr access needs an explicit import for stubs
import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "agent_evaluator" / "schemas" / "harness_groups.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    result: dict = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return result


def _basic_monitor() -> PerformanceMonitor:
    m = PerformanceMonitor()
    for i in range(5):
        m.record_task(create_taskresult(
            task_id=f"task_{i}", question="What is the capital of Korea?",
            response="Seoul", ground_truth="Seoul", execution_time=1.0 + i * 0.5,
        ))
    return m


class TestSchemaFileItself:
    def test_schema_file_exists_and_is_valid_json(self, schema):
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert "A" in schema["properties"]
        assert "overall" in schema["properties"]

    def test_schema_is_self_consistent(self, schema):
        """스키마 자체가 유효한 JSON Schema(draft 2020-12)인지 — $ref 등이 다 풀리는지."""
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)


class TestHarnessGroupsConformsToSchema:
    def test_basic_monitor_report_conforms(self, schema):
        """도구 호출 없는 QA 에이전트 — Gate A/C만 실질적으로 채점되는 최소 케이스."""
        m = _basic_monitor()
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        jsonschema.validate(instance=hg, schema=schema)

    def test_security_metrics_enabled_report_conforms(self, schema):
        """enable_security_metrics=True — Gate E details도 채워진 케이스."""
        m = PerformanceMonitor(enable_security_metrics=True)
        m.record_task(create_taskresult(
            task_id="t0", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0,
        ))
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        jsonschema.validate(instance=hg, schema=schema)

    def test_no_tasks_yields_empty_dict_which_the_schema_does_not_have_to_cover(self):
        """tasks가 비어있으면 harness_groups 자체가 {}(SPEC 상 사실) — 스키마는
        "존재하는 harness_groups"의 계약만 정의하므로 이 케이스는 스키마 검증 대상이 아니다."""
        m = PerformanceMonitor()
        report = m.generate_report()
        assert report.extra_metrics is not None
        assert report.extra_metrics.get("harness_groups", {}) == {}

    def test_gate_b_rich_data_report_conforms(self, schema):
        """Gate B의 non-null details 경로(loop/state_consistency/deadlock/scope/
        tool_parameter_safety/context_window 전부 채워진 케이스)도 스키마를 지키는지."""
        from tests.test_gates_gate_b_migration import _build_monitor_with_fixtures

        m = _build_monitor_with_fixtures()
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        jsonschema.validate(instance=hg, schema=schema)

    def test_report_with_registered_custom_gate_still_conforms(self, schema):
        """Phase 2 — register_gate()로 추가한 8번째 Gate가 있어도 스키마 검증이 깨지면
        안 된다(최상위 additionalProperties:true). 커스텀 Gate 내부 구조는 계약 밖이지만
        A-G+overall은 여전히 v1.0을 지켜야 한다."""
        from agent_evaluator.gates.base import _g

        def _custom(tasks, min_samples_default):
            return _g(0.5, "Custom", {"note": "out of contract"})

        m = _basic_monitor()
        m.register_gate("COST", _custom)
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        assert "COST" in hg
        jsonschema.validate(instance=hg, schema=schema)

    def test_overall_scored_group_ids_present_and_consistent(self, schema):
        """이번 Phase 0에서 추가한 scored_group_ids도 계약에 포함돼 있는지 확인."""
        m = _basic_monitor()
        report = m.generate_report()
        assert report.extra_metrics is not None
        hg = report.extra_metrics["harness_groups"]
        jsonschema.validate(instance=hg, schema=schema)
        overall = hg["overall"]
        assert len(overall["scored_group_ids"]) == overall["scored_groups"]
