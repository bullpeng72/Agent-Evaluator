"""
TaskResult 동적 데이터 생성 헬퍼 함수 라이브러리
================================================
하드코딩 없이 실제 값을 동적으로 계산하여 TaskResult를 생성합니다.

주요 함수:
- calculate_completion_score(): 작업 완료도 점수 계산
- calculate_accuracy_score(): 정확도 점수 계산 (4가지 유사도 메트릭 조합)
- extract_tokens_from_openai(): OpenAI API 응답에서 토큰 추출
- extract_tokens_from_langchain(): LangChain 결과에서 토큰 추출
- estimate_tokens(): 텍스트 길이로 토큰 추정
- create_taskresult_from_execution(): 모든 필드 동적 계산하여 TaskResult 생성

🔒 보안 함수:
- validate_input_security(): 입력 보안 위협 검증
- check_output_leakage(): 출력 민감정보 유출 검사
- validate_tool_authorization(): 도구 호출 권한 검증
"""
from __future__ import annotations

import ast
import dataclasses
import logging
import re
from datetime import datetime
from typing import Any, cast

from agent_evaluator.utils.text_similarity import lcs_ratio as _lcs_ratio_util

# Pre-compiled patterns for estimate_tokens() heuristic fallback
_RE_KOREAN_CHARS = re.compile(r'[가-힣]')
_RE_ENGLISH_CHARS = re.compile(r'[a-zA-Z]')

# Pre-compiled patterns for normalize_text()
_RE_NORM_SPECIAL = re.compile(r'[^\w\s]')   # 특수문자 제거 (\w covers Korean in Python 3)
_RE_NORM_WHITESPACE = re.compile(r'\s+')

# SPEC-000: _clamp01은 Gate A 전용 헬퍼 — gates/gate_a_goal/evaluators.py로 이관됨.

# SPEC-041: common developer synonyms for the canonical TaskType values. Without
# this, create_taskresult(task_type="rag") silently became "qa" (via
# getattr(TaskType, "RAG", TaskType.QA)) — losing the RAG cohort from per-slice /
# eval-set-quality reporting even though the SDK is RAG-centric.
_TASK_TYPE_ALIASES: dict[str, str] = {
    "rag": "information_retrieval",
    "retrieval": "information_retrieval",
    "search": "information_retrieval",
    "kb": "information_retrieval",
    "summarization": "document_creation",
    "summary": "document_creation",
    "writing": "document_creation",
    "report": "document_creation",
    "chat": "qa",
    "conversation": "qa",
    "conversational": "qa",
    "plan": "planning",
    "analysis": "data_analysis",
    "data": "data_analysis",
    "multiagent": "multi_agent",
    "multi-agent": "multi_agent",
    "coordination": "multi_agent",
}


def _resolve_task_type(task_type: str | None) -> str:
    """Map a task_type string to a canonical ``TaskType`` value.

    Accepts the canonical lowercase values, the ``TaskType`` enum names, and the
    developer synonyms in ``_TASK_TYPE_ALIASES``. An unrecognised value is kept
    as-is (lowercased) rather than silently forced to ``"qa"`` — ``TaskResult``
    accepts any string — but a warning is emitted so the typo/synonym surfaces.
    """
    from agent_evaluator import TaskType

    if not task_type:
        return TaskType.QA.value
    raw = str(task_type).strip().lower()
    if not raw:
        return TaskType.QA.value
    valid = {t.value for t in TaskType}
    if raw in valid:
        return raw
    if raw in _TASK_TYPE_ALIASES:
        return _TASK_TYPE_ALIASES[raw]
    enum_member = getattr(TaskType, raw.upper(), None)
    if enum_member is not None:
        return enum_member.value
    import warnings as _w
    _w.warn(
        f"create_taskresult: unrecognised task_type {task_type!r}; keeping it as-is. "
        f"Canonical values: {sorted(valid)}. Common aliases (e.g. 'rag' -> "
        f"'information_retrieval') are accepted.",
        UserWarning,
        stacklevel=3,
    )
    return raw


# ---------------------------------------------------------------------------
# Pre-compiled patterns for validate_input_security()
# ---------------------------------------------------------------------------
_SEC_SQL_PATTERNS = [
    re.compile(r"(?i)(OR\s+['\"]?1['\"]?\s*=\s*['\"]?1)"),
    re.compile(r"(?i)(DROP\s+TABLE)"),
    re.compile(r"(?i)(UNION\s+SELECT)"),
    re.compile(r"(?i)(--\s*$)"),
    re.compile(r"(?i)(;\s*DROP)"),
]
_SEC_CMD_PATTERNS = [
    re.compile(r'rm\s+-rf'),
    re.compile(r'\|\s*bash'),
    re.compile(r';\s*rm'),
    re.compile(r'`[^`]+`'),
    re.compile(r'\$\([^)]+\)'),
]
_SEC_PATH_PATTERNS = [
    re.compile(r'\.\./\.\.', re.IGNORECASE),
    re.compile(r'\.\.\\', re.IGNORECASE),
    re.compile(r'/etc/passwd', re.IGNORECASE),
    re.compile(r'\\windows\\system32', re.IGNORECASE),
]
_SEC_XSS_PATTERNS = [
    re.compile(r'<script[^>]*>', re.IGNORECASE),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'onerror\s*=', re.IGNORECASE),
    re.compile(r'onclick\s*=', re.IGNORECASE),
]
_SEC_PROMPT_PATTERNS = [
    re.compile(r'(?i)ignore\s+(all\s+)?previous\s+instructions'),
    re.compile(r'(?i)disregard\s+(all\s+)?above'),
    re.compile(r'(?i)forget\s+everything'),
    re.compile(r'(?i)you\s+are\s+now'),
]

# ---------------------------------------------------------------------------
# Pre-compiled patterns for check_output_leakage()
# ---------------------------------------------------------------------------
_LEAK_API_PATTERNS = {
    'openai_api_key': re.compile(r'sk-[A-Za-z0-9]{48}', re.IGNORECASE),
    'aws_access_key': re.compile(r'AKIA[0-9A-Z]{16}', re.IGNORECASE),
    'google_api_key': re.compile(r'AIza[0-9A-Za-z_-]{35}', re.IGNORECASE),
    'generic_api_key': re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_-]{20,}', re.IGNORECASE),
}
_LEAK_PASSWORD_PATTERNS = [
    re.compile(r'password["\']?\s*[:=]\s*["\']?[^\s"\']{8,}', re.IGNORECASE),
    re.compile(r'passwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}', re.IGNORECASE),
    re.compile(r'pwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}', re.IGNORECASE),
]
_LEAK_CC_PATTERN = re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b')
_LEAK_EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
_LEAK_PRIVATE_IP_PATTERNS = [
    re.compile(r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'\b192\.168\.\d{1,3}\.\d{1,3}\b'),
    re.compile(r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b'),
]
_LEAK_FILE_PATH_PATTERNS = [
    re.compile(r'[A-Z]:\\[^\s]+'),  # Windows paths
    re.compile(r'/home/[^\s]+'),    # Unix home paths
    re.compile(r'/root/[^\s]+'),    # Root paths
]

logger = logging.getLogger(__name__)


# SPEC-000: Gate A 전용 헬퍼(_is_subtask_found·_is_subtask_find_pos·_is_fact_retained_in_text·
# _kr_strip_particle·_GOAL_STOPWORDS 등)는 gates/gate_a_goal/evaluators.py로 이관됨 —
# Gate A의 6개 eval 함수 전용으로만 사용됨을 확인(다른 Gate와 비공유).
# 기존 테스트(tests/test_decorators_harness.py)가 일부를 직접 import하므로 재노출한다.
from agent_evaluator.gates.gate_a_goal.evaluators import (  # noqa: F401,E402
    _KOREAN_PARTICLES_1 as _KOREAN_PARTICLES_1,
    _KOREAN_UNITS as _KOREAN_UNITS,
    _is_fact_retained_in_text as _is_fact_retained_in_text,
    _kr_strip_particle as _kr_strip_particle,
)

# ============================================================================
# 1. Completion Score 계산
# ============================================================================

def calculate_completion_score(
    response: str,
    expected_min_length: int = 10,
    has_error: bool = False,
    ground_truth: str | None = None,
    task_type: str | None = None,
    tool_calls: list[Any] | None = None,
) -> float:
    """
    작업 완료도 점수 계산 (0.0 ~ 1.0)

    Args:
        response: 에이전트의 응답
        expected_min_length: 최소 기대 길이
        has_error: 에러 발생 여부
        ground_truth: 정답 (선택사항, 있으면 유사도 기반 점수 계산)
        task_type: 태스크 유형 (선택사항, 유형별 완료 기준 적용)
        tool_calls: 도구 호출 목록 (tool_use 태스크 완료 판정에 사용)

    Returns:
        float: 0.0 ~ 1.0 사이의 완료도 점수

    Examples:
        >>> calculate_completion_score("서울입니다", expected_min_length=5)
        1.0

        >>> calculate_completion_score("", has_error=True)
        0.0

        >>> calculate_completion_score("짧음", expected_min_length=100)
        0.3
    """
    # 1. 에러가 있으면 0
    if has_error:
        return 0.0

    # 2. 응답이 없으면 0
    if not response or not response.strip():
        return 0.0

    # 3. 태스크 유형별 완료 기준 (ground_truth 없이도 구조적으로 완료 판정)
    if task_type and not ground_truth:
        task_type_lower = task_type.lower()

        # code_generation / coding: 파싱 가능한 Python 코드인지 확인
        if task_type_lower in ("code_generation", "coding"):
            stripped = response.strip()
            # 코드 블록 제거 후 파싱 시도
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            else:
                inner = stripped
            try:
                ast.parse(inner)
                return 1.0  # 구문 유효한 코드 → 완전 완료
            except SyntaxError:
                pass
            # 파싱 실패 → 길이 기반으로 fallthrough

        # tool_use: 도구를 실제로 호출했는지 확인
        elif task_type_lower == "tool_use":
            if tool_calls:
                return 1.0
            # 도구 호출 없이 텍스트만 반환 → 부분 완료
            response_length = len(response.strip())
            if response_length < expected_min_length:
                ratio = response_length / expected_min_length
                return max(0.3, min(0.5, ratio))
            return 0.6  # 응답은 있으나 도구 미사용

    # 4. 길이 기반 평가
    response_length = len(response.strip())
    if response_length < expected_min_length:
        # 최소 길이에 미달하면 부분 점수 (0.3 ~ 0.7)
        ratio = response_length / expected_min_length
        return max(0.3, min(0.7, ratio))

    # 5. ground_truth가 있으면 유사도 기반 평가
    if ground_truth:
        similarity = _calculate_simple_similarity(response, ground_truth)
        if similarity >= 0.8:
            return 1.0
        elif similarity >= 0.5:
            return 0.7
        else:
            return 0.5

    # 6. 기본 완료 점수
    return 1.0


# ============================================================================
# 2. Accuracy Score 계산 (4가지 유사도 메트릭 조합)
# ============================================================================

def calculate_accuracy_score(
    response: str,
    ground_truth: str | None,
    method: str = "combined"
) -> float:
    """
    정확도 점수 계산 - 4가지 유사도 메트릭 조합

    4가지 유사도 메트릭 조합:
    - Token Overlap Ratio (40%)
    - Jaccard Similarity (30%)
    - Longest Common Subsequence (20%)
    - Character-level Similarity (10%)

    Args:
        response: 에이전트의 응답
        ground_truth: 정답
        method: "combined" (4가지 조합) 또는 개별 메트릭명

    Returns:
        float: 0.0 ~ 1.0 사이의 정확도 점수.
              *response* 또는 *ground_truth* 가 빈 문자열이거나 None인 경우 0.0을 반환한다
              (ground_truth가 없으면 정확도를 측정할 수 없음).

    Examples:
        >>> calculate_accuracy_score("서울", "서울", method="combined")
        1.0

        >>> calculate_accuracy_score("대한민국의 수도는 서울입니다", "서울")
        0.85

        >>> calculate_accuracy_score("서울", "")  # empty ground_truth → 0.0
        0.0
    """
    if not response or not ground_truth:
        return 0.0

    # 정규화
    resp_norm = normalize_text(response)
    truth_norm = normalize_text(ground_truth)

    if method == "combined":
        # 4가지 메트릭 가중 조합
        token_score = _token_overlap_ratio(resp_norm, truth_norm)
        jaccard_score = _jaccard_similarity(resp_norm, truth_norm)
        lcs_score = _lcs_ratio_util(resp_norm, truth_norm)
        char_score = _char_similarity(resp_norm, truth_norm)

        # 가중 평균
        combined_score = (
            token_score * 0.4 +      # Token Overlap: 40%
            jaccard_score * 0.3 +    # Jaccard: 30%
            lcs_score * 0.2 +        # LCS: 20%
            char_score * 0.1         # Char: 10%
        )

        return round(combined_score, 3)

    elif method == "token_overlap":
        return _token_overlap_ratio(resp_norm, truth_norm)
    elif method == "jaccard":
        return _jaccard_similarity(resp_norm, truth_norm)
    elif method == "lcs":
        return _lcs_ratio_util(resp_norm, truth_norm)
    elif method == "char":
        return _char_similarity(resp_norm, truth_norm)
    else:
        raise ValueError(f"Unknown method: {method}")


def normalize_text(text: str) -> str:
    """텍스트 정규화 (소문자, 공백 정리, 특수문자 제거)"""
    text = text.lower().strip()
    text = _RE_NORM_SPECIAL.sub('', text)       # 특수문자 제거 (\w covers Korean)
    text = _RE_NORM_WHITESPACE.sub(' ', text)   # 다중 공백 → 단일 공백
    return text


# Internal similarity functions
def _token_overlap_ratio(text1: str, text2: str) -> float:
    """Token Overlap F1 — harmonic mean of precision and recall."""
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 or not tokens2:
        return 0.0

    overlap = len(tokens1 & tokens2)
    precision = overlap / len(tokens1)
    recall = overlap / len(tokens2)

    return (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Jaccard Similarity"""
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 and not tokens2:
        return 1.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    return intersection / union if union > 0 else 0.0



def _char_similarity(text1: str, text2: str) -> float:
    """Character-level Similarity (Levenshtein distance 기반)"""
    if text1 == text2:
        return 1.0

    m, n = len(text1), len(text2)

    if m == 0 or n == 0:
        return 0.0

    # Simplified Levenshtein distance
    if m > n:
        text1, text2 = text2, text1
        m, n = n, m

    prev_row = list(range(n + 1))

    for i in range(1, m + 1):
        curr_row = [i]
        for j in range(1, n + 1):
            insert = prev_row[j] + 1
            delete = curr_row[j-1] + 1
            substitute = prev_row[j-1] + (0 if text1[i-1] == text2[j-1] else 1)
            curr_row.append(min(insert, delete, substitute))
        prev_row = curr_row

    distance = prev_row[n]
    max_length = max(m, n)

    similarity = 1 - (distance / max_length)
    return max(0.0, similarity)


def _calculate_simple_similarity(text1: str, text2: str) -> float:
    """간단한 유사도 계산 (completion_score용)"""
    return _jaccard_similarity(normalize_text(text1), normalize_text(text2))


# ============================================================================
# 3. Token 추출 및 추정
# ============================================================================

def extract_tokens_from_openai(openai_response: Any) -> dict[str, int]:
    """
    OpenAI API 응답에서 토큰 사용량 추출

    Args:
        openai_response: OpenAI API 응답 객체

    Returns:
        dict: {"input": int, "output": int, "total": int}

    Examples:
        >>> response = openai.chat.completions.create(...)
        >>> tokens = extract_tokens_from_openai(response)
        >>> print(tokens)
        {"input": 100, "output": 50, "total": 150}
    """
    try:
        return {
            "input": openai_response.usage.prompt_tokens,
            "output": openai_response.usage.completion_tokens,
            "total": openai_response.usage.total_tokens
        }
    except AttributeError:
        return {"input": 0, "output": 0, "total": 0}


def extract_tokens_from_langchain(langchain_result: Any) -> dict[str, int]:
    """
    LangChain 실행 결과에서 토큰 사용량 추출

    Args:
        langchain_result: LangChain Agent 실행 결과 (dict)

    Returns:
        dict: {"input": int, "output": int, "total": int}

    Examples:
        >>> result = agent.run("질문")
        >>> tokens = extract_tokens_from_langchain(result)
    """
    try:
        if isinstance(langchain_result, dict):
            llm_output = langchain_result.get("llm_output", {})
            token_usage = llm_output.get("token_usage", {})

            return {
                "input": token_usage.get("prompt_tokens", 0),
                "output": token_usage.get("completion_tokens", 0),
                "total": token_usage.get("total_tokens", 0)
            }
    except Exception as e:
        logger.warning("LangChain token extraction failed (recording tokens_used=0): %s", e)

    return {"input": 0, "output": 0, "total": 0}


def estimate_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    텍스트의 토큰 수 추정. tiktoken 설치 시 정확한 값, 아니면 언어별 휴리스틱 사용.

    Args:
        text: 추정할 텍스트
        model: tiktoken 모델명 (기본: gpt-3.5-turbo)

    Returns:
        int: 추정 토큰 수
    """
    if not text:
        return 0

    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        pass

    # Fallback: 언어별 휴리스틱 (영문 4자 ≈ 1토큰, 한글 1.5자 ≈ 1토큰)
    # Use pre-compiled patterns (avoid per-call recompilation)
    korean_chars = len(_RE_KOREAN_CHARS.findall(text))
    english_chars = len(_RE_ENGLISH_CHARS.findall(text))
    other_chars = len(text) - korean_chars - english_chars
    estimated = (korean_chars / 1.5) + (english_chars / 4) + (other_chars / 3)
    return max(1, int(estimated))


# ============================================================================
# 4. Tool Calls 추출
# ============================================================================

def extract_tool_calls_from_langchain(langchain_result) -> list[dict[str, Any]]:
    """
    LangChain intermediate_steps에서 tool calls 추출

    Args:
        langchain_result: LangChain Agent 실행 결과

    Returns:
        list: [{"tool": "tool_name", "input": {...}, "output": "..."}]
    """
    tool_calls = []

    try:
        if isinstance(langchain_result, dict):
            intermediate_steps = langchain_result.get("intermediate_steps", [])

            for step in intermediate_steps:
                if isinstance(step, tuple) and len(step) >= 2:
                    action, output = step[0], step[1]

                    tool_calls.append({
                        "tool": getattr(action, 'tool', 'unknown'),
                        "input": getattr(action, 'tool_input', {}),
                        "output": str(output)
                    })
    except Exception as e:
        logger.warning("LangChain tool calls extraction failed (recording tool_calls=[]): %s", e)

    return tool_calls


def extract_tool_calls_from_openai_functions(openai_response) -> list[dict[str, Any]]:
    """
    OpenAI Function Calling 응답에서 tool calls 추출

    Args:
        openai_response: OpenAI API 응답 객체

    Returns:
        list: [{"tool": "function_name", "arguments": {...}}]
    """
    tool_calls = []

    try:
        message = openai_response.choices[0].message

        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append({
                    "tool": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                })
    except Exception as e:
        logger.warning("OpenAI function calling tool calls extraction failed (recording tool_calls=[]): %s", e)

    return tool_calls


# ============================================================================
# 5. 통합 TaskResult 생성 함수
# ============================================================================

def create_taskresult_from_execution(
    task_id: str,
    question: str,
    response: str,
    ground_truth: str = "",
    execution_time: float = 0.0,
    openai_response: Any | None = None,
    langchain_result: Any | None = None,
    has_error: bool = False,
    error_message: str | None = None,
    task_type: str = "qa",
    partial_reason: str | None = None,
    context: str | None = None,
    model_name: str = "",
    metadata: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    use_korean_tokenizer: bool = False,
    **extra_fields: Any,
):
    """
    Agent 실행 결과로부터 TaskResult 생성 (모든 필드 동적 계산)

    Args:
        task_id: Task 고유 ID
        question: 질문
        response: 에이전트의 응답
        ground_truth: 정답
        execution_time: 실행 시간 (초)
        openai_response: OpenAI API 응답 객체 (선택). 토큰 사용량 자동 추출에 사용.
        langchain_result: LangChain 실행 결과 딕셔너리 (선택). 토큰 사용량 자동 추출에 사용.
        has_error: 에러 발생 여부
        error_message: 에러 메시지
        task_type: Task 유형 (기본: ``"qa"``). 허용값:
            ``"qa"``, ``"coding"``, ``"code_generation"``, ``"data_analysis"``,
            ``"document_creation"``, ``"information_retrieval"``, ``"reasoning"``,
            ``"creative"``, ``"planning"``, ``"tool_use"``.
            :class:`~agent_evaluator.TaskType` enum의 소문자 값과 동일.
        context: RAG 시스템에서 검색된 컨텍스트 (할루시네이션 감지에 사용).
            제공하면 HallucinationDetector가 응답의 사실 일관성을 검증한다.
        model_name: 이 태스크에서 사용한 LLM 모델명 (예: "claude-sonnet-4-6").
            지정하면 tokens dict에 "model" 키로 추가되어 Phoenix "Top models" 차트에서
            태스크별 모델 구분이 가능하다 (멀티 모델 평가 시 유용).
            미지정 시 PerformanceMonitor.model_name (전역 설정)이 사용된다.
        metadata: 추가 메타데이터 dict (D6). ``TaskResult.extra`` 필드에 병합된다.
            ``extra`` 와 동시에 지정 시 ``metadata`` 가 ``extra`` 를 덮어쓴다.
        extra: ``TaskResult.extra`` 기본값. ``metadata`` 보다 낮은 우선순위.
        **extra_fields: ``TaskResult`` 의 선택적 필드를 직접 주입한다 (Item T).
            예: ``framework="langchain"``, ``tokens_used={"input": 10, "output": 20, "total": 30}``,
            ``errors=["some error"]``, ``tool_calls=[...]``.
            ``TaskResult`` 필드로 등록되지 않은 키는 무시된다. 기존 자동 계산값보다 우선 적용된다.

    Returns:
        TaskResult: 동적 계산된 TaskResult 객체

    Examples:
        >>> from agent_evaluator import TaskResult, TaskType
        >>>
        >>> # Public alias: ``from agent_evaluator import create_taskresult``
        >>>
        >>> # OpenAI 사용 시
        >>> task = create_taskresult_from_execution(
        ...     task_id="task_001",
        ...     question="수도는?",
        ...     response="서울입니다",
        ...     ground_truth="서울",
        ...     execution_time=1.2,
        ...     openai_response=response
        ... )
        >>>
        >>> # LangChain 사용 시
        >>> task = create_taskresult_from_execution(
        ...     task_id="task_002",
        ...     question="수도는?",
        ...     response="서울입니다",
        ...     ground_truth="서울",
        ...     execution_time=1.5,
        ...     langchain_result=result
        ... )
    """
    from agent_evaluator import TaskResult

    # 1. tokens_used 동적 추출
    if openai_response:
        tokens = extract_tokens_from_openai(openai_response)
    elif langchain_result:
        tokens = extract_tokens_from_langchain(langchain_result)
    else:
        # 추정 — 로컬 변수로 캐시해 estimate_tokens(question) 중복 호출 방지
        _input_tokens = estimate_tokens(question)
        _output_tokens = estimate_tokens(response)
        tokens = {
            "input": _input_tokens,
            "output": _output_tokens,
            "total": _input_tokens + _output_tokens,
        }
    # model_name 지정 시 tokens dict에 포함 — Phoenix Top models 차트에서 태스크별 모델 구분.
    # tokens는 위 세 분기 모두 dict[str, int]를 반환하지만, TaskResult.tokens_used는
    # "model" 문자열 키가 섞여도 되는 관례(base.py/monitor.py와 동일)라 여기서만 캐스팅.
    if model_name:
        cast(dict, tokens)["model"] = model_name

    # 2. tool_calls 동적 추출 (completion_score 계산 전에 추출해야 task_type 인식 가능)
    tool_calls = []
    if openai_response:
        tool_calls = extract_tool_calls_from_openai_functions(openai_response)
    elif langchain_result:
        tool_calls = extract_tool_calls_from_langchain(langchain_result)
    # extra_fields로 직접 지정된 tool_calls가 있으면 우선 사용
    if "tool_calls" in extra_fields:
        tool_calls = extra_fields["tool_calls"]

    # 3. completion_score 동적 계산 (task_type + tool_calls 정보 활용)
    completion = calculate_completion_score(
        response=response,
        expected_min_length=10,
        has_error=has_error,
        ground_truth=ground_truth,
        task_type=task_type,
        tool_calls=tool_calls,
    )

    # 4. accuracy_score 동적 계산 (4가지 유사도 메트릭 조합)
    if use_korean_tokenizer:
        from agent_evaluator.core.trackers.layer1 import AccuracyEvaluator
        _ae = AccuracyEvaluator(use_korean_tokenizer=True)
        accuracy = _ae._calculate_accuracy(ground_truth, response, task_type) if ground_truth else 0.0
    else:
        accuracy = calculate_accuracy_score(
            response=response,
            ground_truth=ground_truth,
            method="combined"
        )

    # 5. partial_reason 자동 추론 (사용자가 직접 지정하지 않은 경우)
    if partial_reason is None and completion < 1.0:
        if has_error and error_message:
            partial_reason = f"error: {error_message}"
        elif not response or not response.strip():
            partial_reason = "no response"
        elif ground_truth:
            sim = _calculate_simple_similarity(response, ground_truth)
            if completion == 0.0:
                partial_reason = f"ground_truth mismatch (similarity {sim:.0%} — below threshold)"
            elif sim >= 0.5:
                partial_reason = f"partial ground_truth match (similarity {sim:.0%}, not exact)"
            else:
                partial_reason = f"low ground_truth similarity (similarity {sim:.0%})"
        elif len((response or "").strip()) < 10:
            partial_reason = f"response too short ({len((response or '').strip())} chars)"
        # completion_score를 사용자가 직접 지정한 경우 — 추론 불가
        # partial_reason은 None으로 유지

    # 6. D6: metadata → extra 병합
    # metadata가 있으면 extra에 병합 (metadata가 우선)
    if metadata:
        if extra:
            merged_extra: dict[str, Any] | None = {**extra, **metadata}
        else:
            merged_extra = dict(metadata)
        extra = merged_extra

    # 7. TaskResult 생성 (기본값 dict 먼저 구성)
    _base_kwargs: dict[str, Any] = dict(
        task_id=task_id,
        task_type=_resolve_task_type(task_type),
        success=not has_error,
        completion_score=completion,      # ✅ 동적 계산
        accuracy_score=accuracy,          # ✅ 동적 계산 (4가지 메트릭 조합)
        execution_time=execution_time,
        tokens_used=tokens,               # ✅ 동적 추출
        tool_calls=tool_calls,            # ✅ 동적 추출
        attempts=1,
        errors=[error_message] if error_message else [],
        timestamp=datetime.now(),
        partial_reason=partial_reason,    # ✅ 자동 추론 또는 사용자 지정
        question=question,                # ✅ raw content — 대시보드 표시용
        response=response,               # ✅ raw content — 대시보드 표시용
        ground_truth=str(ground_truth) if ground_truth is not None else None,  # ✅ raw content
        context=context,                  # ✅ RAG 컨텍스트 — 할루시네이션 감지용
        extra=extra,                      # ✅ D6: metadata 포함 사용자 정의 메타데이터
    )

    # Item T: extra_fields — TaskResult 필드로 등록된 키만 허용, 기존 값 override
    if extra_fields:
        _valid_keys = {f.name for f in dataclasses.fields(TaskResult)}
        _filtered = {k: v for k, v in extra_fields.items() if k in _valid_keys}
        _base_kwargs.update(_filtered)

    return TaskResult(**_base_kwargs)


# ============================================================================
# 6. 간편 헬퍼 함수들
# ============================================================================

def simulate_agent_response(question: str, responses_map: dict[str, str]) -> dict[str, Any]:
    """
    간단한 에이전트 응답 시뮬레이션 (테스트/예제용)

    Args:
        question: 질문
        responses_map: 키워드별 응답 매핑

    Returns:
        dict: {"answer": str, "latency": float}
    """
    for keyword, answer in responses_map.items():
        if keyword in question:
            return {
                "answer": answer,
                "latency": 1.0 + len(answer) / 100  # 길이 기반 가짜 latency
            }

    return {"answer": "Answer not found.", "latency": 0.5}


def calculate_percentage_score(score: float) -> float:
    """
    0.0~1.0 점수를 0~100 백분율로 변환

    Args:
        score: 0.0 ~ 1.0 사이 점수

    Returns:
        float: 0 ~ 100 사이 백분율
    """
    return round(score * 100, 2)


# ============================================================================
# 예제 사용법
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TaskResult Helpers - Usage Examples")
    print("=" * 70)

    # 예제 1: Completion Score 계산
    print("\n1️⃣ Completion Score calculation")
    score1 = calculate_completion_score("대한민국의 수도는 서울입니다", expected_min_length=5)
    print(f"   Score: {score1:.2f}")

    # 예제 2: Accuracy Score 계산
    print("\n2️⃣ Accuracy Score calculation (4-metric blend)")
    score2 = calculate_accuracy_score("대한민국의 수도는 서울입니다", "서울")
    print(f"   Score: {score2:.3f}")

    # 예제 3: Token 추정
    print("\n3️⃣ Token estimation")
    text = "한국어와 영어가 섞인 텍스트입니다. This is mixed text."
    tokens = estimate_tokens(text)
    print(f"   Text: {text}")
    print(f"   Estimated Tokens: {tokens}")

    # 예제 4: 통합 TaskResult 생성 (시뮬레이션)
    print("\n4️⃣ TaskResult creation (simulation)")
    print("   All fields are dynamically calculated:")
    print("   ✅ completion_score: dynamically calculated")
    print("   ✅ accuracy_score: 4 metrics combined")
    print("   ✅ tokens_used: dynamically extracted/estimated")
    print("   ✅ tool_calls: dynamically extracted")

    print("\n✅ taskresult_helpers.py ready!")
    print("   Import from the examples/ directory to use.")


# ============================================================================
# 7. 보안 검증 함수
# ============================================================================

def validate_input_security(input_text: str) -> dict[str, Any]:
    """
    입력 텍스트의 보안 위협 검증

    Args:
        input_text: 검사할 입력 텍스트

    Returns:
        보안 검증 결과 딕셔너리:
        {
            'is_safe': bool,
            'risk_level': 'safe' | 'low' | 'medium' | 'high' | 'critical',
            'threats_detected': List[str],
            'threat_details': List[Dict]
        }

    Examples:
        >>> result = validate_input_security("SELECT * FROM users")
        >>> result['is_safe']
        False
        >>> 'sql_injection' in result['threats_detected']
        True
    """
    threats_detected = []
    threat_details = []
    risk_level = 'safe'

    # SQL Injection patterns
    for pat in _SEC_SQL_PATTERNS:
        if pat.search(input_text):
            threats_detected.append('sql_injection')
            threat_details.append({
                'type': 'sql_injection',
                'pattern': pat.pattern,
                'severity': 'high'
            })
            risk_level = 'high'
            break

    # Command Injection patterns
    for pat in _SEC_CMD_PATTERNS:
        if pat.search(input_text):
            threats_detected.append('command_injection')
            threat_details.append({
                'type': 'command_injection',
                'pattern': pat.pattern,
                'severity': 'critical'
            })
            risk_level = 'critical'
            break

    # Path Traversal patterns
    for pat in _SEC_PATH_PATTERNS:
        if pat.search(input_text):
            threats_detected.append('path_traversal')
            threat_details.append({
                'type': 'path_traversal',
                'pattern': pat.pattern,
                'severity': 'high'
            })
            if risk_level not in ['critical', 'high']:
                risk_level = 'high'
            break

    # XSS patterns
    for pat in _SEC_XSS_PATTERNS:
        if pat.search(input_text):
            threats_detected.append('xss')
            threat_details.append({
                'type': 'xss',
                'pattern': pat.pattern,
                'severity': 'medium'
            })
            if risk_level not in ['critical', 'high']:
                risk_level = 'medium'
            break

    # Prompt Injection patterns
    for pat in _SEC_PROMPT_PATTERNS:
        if pat.search(input_text):
            threats_detected.append('prompt_injection')
            threat_details.append({
                'type': 'prompt_injection',
                'pattern': pat.pattern,
                'severity': 'medium'
            })
            if risk_level == 'safe':
                risk_level = 'low'
            break

    is_safe = len(threats_detected) == 0

    return {
        'is_safe': is_safe,
        'risk_level': risk_level,
        'threats_detected': list(set(threats_detected)),
        'threat_details': threat_details,
        'input_length': len(input_text)
    }


def check_output_leakage(output_text: str) -> dict[str, Any]:
    """
    출력 텍스트에서 민감정보 유출 검사

    Args:
        output_text: 검사할 출력 텍스트

    Returns:
        유출 검사 결과:
        {
            'has_leakage': bool,
            'severity': 'none' | 'low' | 'medium' | 'high' | 'critical',
            'leakage_types': List[str],
            'leakage_count': int,
            'details': List[Dict]
        }

    Examples:
        >>> result = check_output_leakage("API key: sk-1234567890")
        >>> result['has_leakage']
        True
        >>> 'api_key' in result['leakage_types']
        True
    """
    leakage_found = []
    details = []
    severity = 'none'

    # API Keys patterns
    for key_type, pat in _LEAK_API_PATTERNS.items():
        matches = pat.findall(output_text)
        if matches:
            leakage_found.append('api_key')
            details.append({
                'type': 'api_key',
                'subtype': key_type,
                'count': len(matches),
                'severity': 'critical'
            })
            severity = 'critical'

    # Password patterns
    for pat in _LEAK_PASSWORD_PATTERNS:
        matches = pat.findall(output_text)
        if matches:
            leakage_found.append('password')
            details.append({
                'type': 'password',
                'count': len(matches),
                'severity': 'critical'
            })
            severity = 'critical'
            break

    # Credit card numbers
    cc_matches = _LEAK_CC_PATTERN.findall(output_text)
    if cc_matches:
        leakage_found.append('credit_card')
        details.append({
            'type': 'credit_card',
            'count': len(cc_matches),
            'severity': 'critical'
        })
        severity = 'critical'

    # Email addresses (lower severity)
    email_matches = _LEAK_EMAIL_PATTERN.findall(output_text)
    if email_matches:
        leakage_found.append('email')
        details.append({
            'type': 'email',
            'count': len(email_matches),
            'severity': 'low'
        })
        if severity == 'none':
            severity = 'low'

    # IP addresses (internal networks)
    for pat in _LEAK_PRIVATE_IP_PATTERNS:
        ip_matches = pat.findall(output_text)
        if ip_matches:
            leakage_found.append('private_ip')
            details.append({
                'type': 'private_ip',
                'count': len(ip_matches),
                'severity': 'medium'
            })
            if severity not in ['critical', 'high']:
                severity = 'medium'
            break

    # File paths (potential info leak)
    for pat in _LEAK_FILE_PATH_PATTERNS:
        path_matches = pat.findall(output_text)
        if path_matches:
            leakage_found.append('file_path')
            details.append({
                'type': 'file_path',
                'count': len(path_matches),
                'severity': 'low'
            })
            break

    has_leakage = len(leakage_found) > 0

    return {
        'has_leakage': has_leakage,
        'severity': severity,
        'leakage_types': list(set(leakage_found)),
        'leakage_count': len(details),
        'details': details,
        'output_length': len(output_text)
    }


def validate_tool_authorization(
    tool_name: str,
    tool_params: dict[str, Any],
    allowed_tools: list[str] | None = None,
    restricted_tools: list[str] | None = None
) -> dict[str, Any]:
    """
    도구 호출 권한 검증

    Args:
        tool_name: 호출하려는 도구 이름
        tool_params: 도구 파라미터
        allowed_tools: 허용된 도구 목록 (None이면 모두 허용)
        restricted_tools: 제한된 도구 목록

    Returns:
        권한 검증 결과:
        {
            'is_authorized': bool,
            'violation_type': str | None,
            'risk_level': 'safe' | 'low' | 'medium' | 'high',
            'reason': str,
            'dangerous_params': List[str]
        }

    Examples:
        >>> result = validate_tool_authorization(
        ...     'execute_command',
        ...     {'command': 'rm -rf /'},
        ...     restricted_tools=['execute_command']
        ... )
        >>> result['is_authorized']
        False
    """
    is_authorized = True
    violation_type = None
    risk_level = 'safe'
    reason = 'Tool call authorized'
    dangerous_params = []

    # Check whitelist
    if allowed_tools is not None:
        if tool_name not in allowed_tools:
            is_authorized = False
            violation_type = 'not_in_whitelist'
            risk_level = 'medium'
            reason = f"Tool '{tool_name}' not in allowed list"
            return {
                'is_authorized': is_authorized,
                'violation_type': violation_type,
                'risk_level': risk_level,
                'reason': reason,
                'dangerous_params': dangerous_params
            }

    # Check blacklist
    if restricted_tools is not None:
        if tool_name in restricted_tools:
            is_authorized = False
            violation_type = 'restricted_tool'
            risk_level = 'high'
            reason = f"Tool '{tool_name}' is restricted"
            return {
                'is_authorized': is_authorized,
                'violation_type': violation_type,
                'risk_level': risk_level,
                'reason': reason,
                'dangerous_params': dangerous_params
            }

    # Check for dangerous parameters
    dangerous_patterns = {
        'rm -rf': 'high',
        'DROP TABLE': 'critical',
        'sudo': 'high',
        '--force': 'medium',
        'DELETE FROM': 'high',
        '/etc/passwd': 'critical',
        'eval(': 'high',
        'exec(': 'high',
    }

    param_str = str(tool_params)
    for pattern, severity in dangerous_patterns.items():
        if pattern in param_str:
            dangerous_params.append(pattern)
            if severity == 'critical':
                risk_level = 'high'
            elif severity == 'high' and risk_level not in ['high']:
                risk_level = 'high'
            elif severity == 'medium' and risk_level == 'safe':
                risk_level = 'medium'

    if dangerous_params:
        reason = f"Dangerous parameters detected: {', '.join(dangerous_params)}"

    return {
        'is_authorized': is_authorized,
        'violation_type': violation_type,
        'risk_level': risk_level,
        'reason': reason,
        'dangerous_params': dangerous_params
    }


# ---------------------------------------------------------------------------
# v0.9.0: Phase 1 Harness Config 헬퍼 함수 6개 (A/B/C/G 그룹 보조)
# ---------------------------------------------------------------------------


# SPEC-000: Gate A 패키지로 이관됨 — 원본 구현은 gates/gate_a_goal/evaluators.py 참조
from agent_evaluator.gates.gate_a_goal.evaluators import (  # noqa: F401,E402
    eval_context_retention as eval_context_retention,
    eval_goal_alignment as eval_goal_alignment,
    eval_instruction_adherence as eval_instruction_adherence,
    eval_knowledge_retention as eval_knowledge_retention,
    eval_plan_coherence as eval_plan_coherence,
    eval_subtask_completion as eval_subtask_completion,
)

# ---------------------------------------------------------------------------
# v0.9.2: Phase 3 Harness Config 헬퍼 함수 5개
# ---------------------------------------------------------------------------
# Phase 5 Harness Helpers (v0.9.4+)
# ---------------------------------------------------------------------------
# SPEC-000: Gate B 패키지로 이관됨 — 원본 구현은 gates/gate_b_behavioral/evaluators.py 참조
from agent_evaluator.gates.gate_b_behavioral.evaluators import (  # noqa: F401,E402
    _normalize_agent_interactions as _normalize_agent_interactions,
    eval_context_window as eval_context_window,
    eval_deadlock as eval_deadlock,
    eval_loop_detection as eval_loop_detection,
    eval_scope as eval_scope,
    eval_state_consistency as eval_state_consistency,
    eval_tool_parameter_safety as eval_tool_parameter_safety,
)

# ── Phase 6 Harness helpers ──────────────────────────────────────────────────
# SPEC-000: Gate C 패키지로 이관됨 — 원본 구현은 gates/gate_c_reliability/evaluators.py 참조
from agent_evaluator.gates.gate_c_reliability.evaluators import (  # noqa: F401,E402
    compute_reproducibility_score as compute_reproducibility_score,
    eval_fault_tolerance as eval_fault_tolerance,
    eval_graceful_degradation as eval_graceful_degradation,
    eval_idempotency as eval_idempotency,
    eval_retry_consistency as eval_retry_consistency,
)

# ---------------------------------------------------------------------------
# v0.9.1: 신규 Harness Config 헬퍼 함수 7개
# ---------------------------------------------------------------------------
# SPEC-000: Gate D 패키지로 이관됨 — 원본 구현은 gates/gate_d_performance/evaluators.py 참조
from agent_evaluator.gates.gate_d_performance.evaluators import (  # noqa: F401,E402
    eval_efficiency as eval_efficiency,
    eval_resource_budget as eval_resource_budget,
    eval_sla as eval_sla,
)

# SPEC-000: Gate E 패키지로 이관됨 — 원본 구현(및 _PII_PATTERNS)은 gates/gate_e_security/evaluators.py 참조
from agent_evaluator.gates.gate_e_security.evaluators import (  # noqa: F401,E402
    eval_compliance as eval_compliance,
    eval_threat_response as eval_threat_response,
    eval_threat_severity as eval_threat_severity,
)

# ── Phase 4 Harness helpers ──────────────────────────────────────────────────
# SPEC-000 Commit 1: Gate F 패키지로 이관됨 — 원본 구현은 gates/gate_f_multiagent/evaluators.py 참조
from agent_evaluator.gates.gate_f_multiagent.evaluators import (  # noqa: F401,E402
    eval_conflict_resolution as eval_conflict_resolution,
    eval_consensus as eval_consensus,
    eval_propagation as eval_propagation,
    eval_role_adherence as eval_role_adherence,
)

# SPEC-000: Gate G 패키지로 이관됨 — 원본 구현은 gates/gate_g_observability/evaluators.py 참조
from agent_evaluator.gates.gate_g_observability.evaluators import (  # noqa: F401,E402
    eval_error_diagnosis as eval_error_diagnosis,
    eval_explainability as eval_explainability,
    eval_latency_attribution as eval_latency_attribution,
    eval_observability as eval_observability,
)
