"""
Tests for Task 2 (TaskResult validation), Task 1 (exception hierarchy),
and Task 4 (record_task deprecated warnings).
"""
from __future__ import annotations

import warnings
from datetime import datetime

import pytest

from agent_evaluator import (
    AgentEvaluatorError,
    ValidationError,
    FrameworkNotInstalledError,
    MetricComputationError,
    ConfigurationError,
    StorageError,
)
from agent_evaluator.core.trackers.base import TaskResult, TaskType
from agent_evaluator.helpers.taskresult_helpers import create_taskresult_from_execution as create_taskresult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_task(**overrides) -> TaskResult:
    """최소 유효한 TaskResult 생성 헬퍼."""
    kwargs = dict(
        task_id="t1",
        task_type=TaskType.QA,
        success=True,
        completion_score=1.0,
        accuracy_score=0.8,
        execution_time=1.0,
        tokens_used={"total": 100},
        tool_calls=[],
        attempts=1,
        errors=[],
    )
    kwargs.update(overrides)
    return TaskResult(**kwargs)


# ---------------------------------------------------------------------------
# 1. ValidationError — completion_score 범위 초과
# ---------------------------------------------------------------------------

class TestCompletionScoreValidation:
    def test_completion_score_above_1_raises(self):
        with pytest.raises(ValidationError, match="completion_score"):
            _make_valid_task(completion_score=1.5)

    def test_completion_score_negative_raises(self):
        with pytest.raises(ValidationError, match="completion_score"):
            _make_valid_task(completion_score=-0.1)

    def test_completion_score_boundary_0_passes(self):
        task = _make_valid_task(completion_score=0.0)
        assert task is not None

    def test_completion_score_boundary_1_passes(self):
        task = _make_valid_task(completion_score=1.0)
        assert task is not None


# ---------------------------------------------------------------------------
# 2. ValidationError — accuracy_score 음수
# ---------------------------------------------------------------------------

class TestAccuracyScoreValidation:
    def test_accuracy_score_negative_raises(self):
        with pytest.raises(ValidationError):
            _make_valid_task(accuracy_score=-0.1)

    def test_accuracy_score_above_1_raises(self):
        with pytest.raises(ValidationError):
            _make_valid_task(accuracy_score=1.01)

    def test_accuracy_score_boundary_0_passes(self):
        task = _make_valid_task(accuracy_score=0.0)
        assert task is not None

    def test_accuracy_score_boundary_1_passes(self):
        task = _make_valid_task(accuracy_score=1.0)
        assert task is not None


# ---------------------------------------------------------------------------
# 3. ValidationError — execution_time 음수
# ---------------------------------------------------------------------------

class TestExecutionTimeValidation:
    def test_execution_time_negative_raises(self):
        with pytest.raises(ValidationError, match="execution_time"):
            _make_valid_task(execution_time=-0.5)

    def test_execution_time_zero_passes(self):
        task = _make_valid_task(execution_time=0.0)
        assert task is not None


# ---------------------------------------------------------------------------
# 4. ValidationError — attempts < 1
# ---------------------------------------------------------------------------

class TestAttemptsValidation:
    def test_attempts_zero_raises(self):
        with pytest.raises(ValidationError, match="attempts"):
            _make_valid_task(attempts=0)

    def test_attempts_negative_raises(self):
        with pytest.raises(ValidationError, match="attempts"):
            _make_valid_task(attempts=-1)

    def test_attempts_one_passes(self):
        task = _make_valid_task(attempts=1)
        assert task is not None


# ---------------------------------------------------------------------------
# 5. 정상 범위는 통과
# ---------------------------------------------------------------------------

class TestValidTaskCreation:
    def test_min_boundary_values_pass(self):
        task = _make_valid_task(
            completion_score=0.0,
            accuracy_score=0.0,
            execution_time=0.0,
            attempts=1,
        )
        assert task is not None

    def test_max_boundary_values_pass(self):
        task = _make_valid_task(
            completion_score=1.0,
            accuracy_score=1.0,
        )
        assert task is not None


# ---------------------------------------------------------------------------
# 6. timestamp 기본값 자동 설정
# ---------------------------------------------------------------------------

class TestTimestampDefault:
    def test_create_taskresult_timestamp_is_set(self):
        task = create_taskresult(
            task_id="t_ts",
            question="timestamp test",
            response="ok",
            ground_truth="ok",
            execution_time=0.1,
        )
        assert task.timestamp is not None
        assert isinstance(task.timestamp, datetime)

    def test_taskresult_timestamp_default(self):
        task = _make_valid_task()
        assert task.timestamp is not None
        assert isinstance(task.timestamp, datetime)

    def test_taskresult_explicit_timestamp_overrides_default(self):
        ts = datetime(2024, 1, 1, 12, 0, 0)
        task = _make_valid_task(timestamp=ts)
        assert task.timestamp == ts


# ---------------------------------------------------------------------------
# 7. FrameworkNotInstalledError 메시지 포맷
# ---------------------------------------------------------------------------

class TestFrameworkNotInstalledError:
    def test_message_contains_pip_install(self):
        err = FrameworkNotInstalledError("LangChain", "langchain")
        assert "pip install" in str(err)

    def test_message_contains_package_extra(self):
        err = FrameworkNotInstalledError("LangChain", "langchain")
        assert "agent-evaluator[langchain]" in str(err)

    def test_attributes_set(self):
        err = FrameworkNotInstalledError("CrewAI", "crewai")
        assert err.framework == "CrewAI"
        assert err.extra == "crewai"

    def test_is_subclass_of_agent_evaluator_error(self):
        err = FrameworkNotInstalledError("X", "x")
        assert isinstance(err, AgentEvaluatorError)


# ---------------------------------------------------------------------------
# 8. AgentEvaluatorError 계층
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:
    def test_agent_evaluator_error_is_exception(self):
        assert issubclass(AgentEvaluatorError, Exception)

    def test_validation_error_is_agent_evaluator_error(self):
        assert issubclass(ValidationError, AgentEvaluatorError)

    def test_metric_computation_error_is_agent_evaluator_error(self):
        assert issubclass(MetricComputationError, AgentEvaluatorError)

    def test_configuration_error_is_agent_evaluator_error(self):
        assert issubclass(ConfigurationError, AgentEvaluatorError)

    def test_storage_error_is_agent_evaluator_error(self):
        assert issubclass(StorageError, AgentEvaluatorError)

    def test_framework_not_installed_error_is_agent_evaluator_error(self):
        assert issubclass(FrameworkNotInstalledError, AgentEvaluatorError)


# ---------------------------------------------------------------------------
# 9. record_task() deprecated warning 발생 확인
# ---------------------------------------------------------------------------

class TestRecordTaskDeprecationWarning:
    def test_request_param_triggers_deprecation_warning(self):
        from agent_evaluator import PerformanceMonitor

        monitor = PerformanceMonitor(enable_hallucination_detection=False)
        task = _make_valid_task(task_id="dep_test")
        # question is None → deprecated warning should fire
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task, request="test question")
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert any("request" in str(x.message).lower() for x in dep_warnings)

    def test_ground_truth_param_triggers_deprecation_warning(self):
        from agent_evaluator import PerformanceMonitor

        monitor = PerformanceMonitor(enable_hallucination_detection=False)
        task = _make_valid_task(task_id="dep_test_gt")
        # ground_truth is None → deprecated warning should fire
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task, ground_truth="expected answer")
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert any("ground_truth" in str(x.message).lower() for x in dep_warnings)

    def test_warning_fires_even_when_question_already_set(self):
        """task_result.question already populated → DeprecationWarning still fires (warn always, overwrite only when None)."""
        from agent_evaluator import PerformanceMonitor

        monitor = PerformanceMonitor(enable_hallucination_detection=False)
        task = _make_valid_task(task_id="no_dep", question="already set")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            monitor.record_task(task, request="test question")
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            # request= was passed so warning must always fire
            assert len(dep_warnings) >= 1


# ---------------------------------------------------------------------------
# 10. exceptions are accessible from public API
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_import_validation_error_from_public_api(self):
        from agent_evaluator import ValidationError as VE
        assert VE is ValidationError

    def test_import_agent_evaluator_error_from_public_api(self):
        from agent_evaluator import AgentEvaluatorError as AEE
        assert AEE is AgentEvaluatorError

    def test_import_framework_not_installed_error_from_public_api(self):
        from agent_evaluator import FrameworkNotInstalledError as FNIE
        assert FNIE is FrameworkNotInstalledError

    def test_import_metric_computation_error_from_public_api(self):
        from agent_evaluator import MetricComputationError as MCE
        assert MCE is MetricComputationError

    def test_import_configuration_error_from_public_api(self):
        from agent_evaluator import ConfigurationError as CE
        assert CE is ConfigurationError

    def test_import_storage_error_from_public_api(self):
        from agent_evaluator import StorageError as SE
        assert SE is StorageError
