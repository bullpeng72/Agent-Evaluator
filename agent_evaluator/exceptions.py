"""Agent Evaluator SDK 전용 예외 계층."""

from __future__ import annotations


class AgentEvaluatorError(Exception):
    """Agent Evaluator SDK의 기본 예외 클래스."""


class ValidationError(AgentEvaluatorError):
    """입력값 또는 설정값이 유효하지 않을 때 발생."""


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
    """
