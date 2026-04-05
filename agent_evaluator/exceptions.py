"""Agent Evaluator SDK 전용 예외 계층."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AgentEvaluatorError(Exception):
    """Agent Evaluator SDK의 기본 예외 클래스."""


class ValidationError(AgentEvaluatorError):
    """입력값 또는 설정값이 유효하지 않을 때 발생.

    Args:
        message: 오류 메시지.
        context: 추가 컨텍스트 정보 (선택). H2: task_id, task_type 등 진단 정보.
    """

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.context = context or {}


class FrameworkNotInstalledError(AgentEvaluatorError):
    """필요한 프레임워크 패키지가 설치되지 않았을 때 발생.

    Attributes:
        framework (str): 설치되지 않은 패키지 이름 (예: ``"crewai"``).
        extra (str): 설치에 필요한 extras 이름 (예: ``"crewai"``).
            ``pip install 'agent-evaluator[{extra}]'`` 로 해결한다.
    """

    def __init__(self, framework: str, extra: str) -> None:
        super().__init__(
            f"{framework} is not installed. "
            f"Install it with: pip install 'agent-evaluator[{extra}]'"
        )
        self.framework = framework
        self.extra = extra


class MetricComputationError(AgentEvaluatorError):
    """지표 계산 중 오류가 발생했을 때."""


class ConfigurationError(AgentEvaluatorError):
    """설정이 잘못되었거나 필수 API 키가 없을 때."""


class StorageError(AgentEvaluatorError):
    """파일 저장/로드 중 오류가 발생했을 때."""


class InvalidOperationError(AgentEvaluatorError):
    """현재 상태에서 허용되지 않는 연산을 시도했을 때.

    예: 태스크가 기록되지 않은 상태에서 ``generate_report()`` 호출,
    이미 닫힌 세션에 ``turn()`` 추가 시도 등.

    Args:
        message: 오류 메시지.
        context: 추가 컨텍스트 정보 (선택). H2: task_id, task_type 등 진단 정보.
    """

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.context = context or {}


def format_error_context(
    task_id: str,
    task_type: str,
    error: Exception,
    additional: Optional[Dict[str, Any]] = None,
) -> str:
    """H2: 오류 메시지에 컨텍스트 정보를 포함시킨다.

    Args:
        task_id: task_id 문자열.
        task_type: task_type 문자열.
        error: 발생한 예외.
        additional: 추가 정보 딕셔너리 (선택).

    Returns:
        ``"[{task_type}] {ErrorType}: {message} (task_id={task_id})"`` 형식 문자열.

    Example::
        msg = format_error_context("task_001", "qa", ValueError("invalid input"))
        # "[qa] ValueError: invalid input (task_id=task_001)"
    """
    _extra = ""
    if additional:
        _extra = " " + " ".join(f"{k}={v}" for k, v in additional.items())
    return f"[{task_type}] {type(error).__name__}: {str(error)[:200]} (task_id={task_id}){_extra}"
