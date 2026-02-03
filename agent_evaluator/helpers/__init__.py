"""
Agent Evaluator Helper Functions
=================================

Automatic TaskResult generation and utility functions.

Security Functions:
- validate_input_security: 입력 보안 위협 검증
- check_output_leakage: 출력 민감정보 유출 검사
- validate_tool_authorization: 도구 호출 권한 검증
"""

from .taskresult_helpers import (
    # Main function
    create_taskresult_from_execution,

    # Calculation functions
    calculate_completion_score,
    calculate_accuracy_score,
    normalize_text,

    # Token extraction
    extract_tokens_from_openai,
    extract_tokens_from_langchain,
    estimate_tokens,

    # Tool extraction
    extract_tool_calls_from_langchain,
    extract_tool_calls_from_openai_functions,

    # Utility functions
    simulate_agent_response,
    calculate_percentage_score,

    # Security functions
    validate_input_security,
    check_output_leakage,
    validate_tool_authorization,
)

__all__ = [
    # Main
    'create_taskresult_from_execution',

    # Calculation
    'calculate_completion_score',
    'calculate_accuracy_score',
    'normalize_text',

    # Token extraction
    'extract_tokens_from_openai',
    'extract_tokens_from_langchain',
    'estimate_tokens',

    # Tool extraction
    'extract_tool_calls_from_langchain',
    'extract_tool_calls_from_openai_functions',

    # Utilities
    'simulate_agent_response',
    'calculate_percentage_score',

    # Security
    'validate_input_security',
    'check_output_leakage',
    'validate_tool_authorization',
]
