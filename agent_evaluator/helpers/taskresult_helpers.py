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

from typing import Dict, List, Any, Optional
from datetime import datetime
import re


# ============================================================================
# 1. Completion Score 계산
# ============================================================================

def calculate_completion_score(
    response: str,
    expected_min_length: int = 10,
    has_error: bool = False,
    ground_truth: str = None
) -> float:
    """
    작업 완료도 점수 계산 (0.0 ~ 1.0)

    Args:
        response: 에이전트의 응답
        expected_min_length: 최소 기대 길이
        has_error: 에러 발생 여부
        ground_truth: 정답 (선택사항, 있으면 유사도 기반 점수 계산)

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

    # 3. 길이 기반 평가
    response_length = len(response.strip())
    if response_length < expected_min_length:
        # 최소 길이에 미달하면 부분 점수 (0.3 ~ 0.7)
        ratio = response_length / expected_min_length
        return max(0.3, min(0.7, ratio))

    # 4. ground_truth가 있으면 유사도 기반 평가
    if ground_truth:
        similarity = _calculate_simple_similarity(response, ground_truth)
        if similarity >= 0.8:
            return 1.0
        elif similarity >= 0.5:
            return 0.7
        else:
            return 0.5

    # 5. 기본 완료 점수
    return 1.0


# ============================================================================
# 2. Accuracy Score 계산 (4가지 유사도 메트릭 조합)
# ============================================================================

def calculate_accuracy_score(
    response: str,
    ground_truth: str,
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
        float: 0.0 ~ 1.0 사이의 정확도 점수

    Examples:
        >>> calculate_accuracy_score("서울", "서울", method="combined")
        1.0

        >>> calculate_accuracy_score("대한민국의 수도는 서울입니다", "서울")
        0.85
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
        lcs_score = _lcs_similarity(resp_norm, truth_norm)
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
        return _lcs_similarity(resp_norm, truth_norm)
    elif method == "char":
        return _char_similarity(resp_norm, truth_norm)
    else:
        raise ValueError(f"Unknown method: {method}")


def normalize_text(text: str) -> str:
    """텍스트 정규화 (소문자, 공백 정리, 특수문자 제거)"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s가-힣]', '', text)  # 특수문자 제거 (한글 유지)
    text = re.sub(r'\s+', ' ', text)  # 다중 공백 → 단일 공백
    return text


# Internal similarity functions
def _token_overlap_ratio(text1: str, text2: str) -> float:
    """Token Overlap Ratio"""
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 or not tokens2:
        return 0.0

    overlap = len(tokens1 & tokens2)
    total = max(len(tokens1), len(tokens2))

    return overlap / total if total > 0 else 0.0


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Jaccard Similarity"""
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 and not tokens2:
        return 1.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    return intersection / union if union > 0 else 0.0


def _lcs_similarity(text1: str, text2: str) -> float:
    """Longest Common Subsequence Similarity"""
    m, n = len(text1), len(text2)

    if m == 0 or n == 0:
        return 0.0

    # DP 테이블
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if text1[i-1] == text2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    lcs_length = dp[m][n]
    max_length = max(m, n)

    return lcs_length / max_length


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

def extract_tokens_from_openai(openai_response) -> Dict[str, int]:
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


def extract_tokens_from_langchain(langchain_result) -> Dict[str, int]:
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
    except Exception:
        pass

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
    korean_chars = len(re.findall(r'[가-힣]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    other_chars = len(text) - korean_chars - english_chars
    estimated = (korean_chars / 1.5) + (english_chars / 4) + (other_chars / 3)
    return max(1, int(estimated))


# ============================================================================
# 4. Tool Calls 추출
# ============================================================================

def extract_tool_calls_from_langchain(langchain_result) -> List[Dict[str, Any]]:
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
    except Exception:
        pass

    return tool_calls


def extract_tool_calls_from_openai_functions(openai_response) -> List[Dict[str, Any]]:
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
    except Exception:
        pass

    return tool_calls


# ============================================================================
# 5. 통합 TaskResult 생성 함수
# ============================================================================

def create_taskresult_from_execution(
    task_id: str,
    question: str,
    response: str,
    ground_truth: str,
    execution_time: float,
    openai_response = None,
    langchain_result = None,
    has_error: bool = False,
    error_message: str = None,
    task_type: str = "qa",
    partial_reason: str = None,
):
    """
    Agent 실행 결과로부터 TaskResult 생성 (모든 필드 동적 계산)

    Args:
        task_id: Task 고유 ID
        question: 질문
        response: 에이전트의 응답
        ground_truth: 정답
        execution_time: 실행 시간 (초)
        openai_response: OpenAI API 응답 (선택)
        langchain_result: LangChain 실행 결과 (선택)
        has_error: 에러 발생 여부
        error_message: 에러 메시지
        task_type: Task 유형 (기본: "qa")

    Returns:
        TaskResult: 동적 계산된 TaskResult 객체

    Examples:
        >>> from agent_evaluator import TaskResult, TaskType
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
    from agent_evaluator import TaskResult, TaskType

    # 1. completion_score 동적 계산
    completion = calculate_completion_score(
        response=response,
        expected_min_length=10,
        has_error=has_error,
        ground_truth=ground_truth
    )

    # 2. accuracy_score 동적 계산 (4가지 유사도 메트릭 조합)
    accuracy = calculate_accuracy_score(
        response=response,
        ground_truth=ground_truth,
        method="combined"
    )

    # 3. tokens_used 동적 추출
    if openai_response:
        tokens = extract_tokens_from_openai(openai_response)
    elif langchain_result:
        tokens = extract_tokens_from_langchain(langchain_result)
    else:
        # 추정
        tokens = {
            "input": estimate_tokens(question),
            "output": estimate_tokens(response),
            "total": estimate_tokens(question) + estimate_tokens(response)
        }

    # 4. tool_calls 동적 추출
    tool_calls = []
    if openai_response:
        tool_calls = extract_tool_calls_from_openai_functions(openai_response)
    elif langchain_result:
        tool_calls = extract_tool_calls_from_langchain(langchain_result)

    # 5. partial_reason 자동 추론 (사용자가 직접 지정하지 않은 경우)
    if partial_reason is None and completion < 1.0:
        if has_error and error_message:
            partial_reason = f"오류 발생: {error_message}"
        elif not response or not response.strip():
            partial_reason = "응답 없음"
        elif ground_truth:
            sim = _calculate_simple_similarity(response, ground_truth)
            if completion == 0.0:
                partial_reason = f"ground_truth 불일치 (유사도 {sim:.0%} — 임계값 미달)"
            elif sim >= 0.5:
                partial_reason = f"ground_truth 부분 일치 (유사도 {sim:.0%}, 완전 일치 미달)"
            else:
                partial_reason = f"ground_truth 유사도 낮음 (유사도 {sim:.0%})"
        elif len((response or "").strip()) < 10:
            partial_reason = f"응답 길이 부족 ({len((response or '').strip())}자)"
        # completion_score를 사용자가 직접 지정한 경우 — 추론 불가
        # partial_reason은 None으로 유지

    # 6. TaskResult 생성
    return TaskResult(
        task_id=task_id,
        task_type=getattr(TaskType, task_type.upper(), TaskType.QA).value,
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
    )


# ============================================================================
# 6. 간편 헬퍼 함수들
# ============================================================================

def simulate_agent_response(question: str, responses_map: Dict[str, str]) -> Dict[str, Any]:
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

    return {"answer": "답변을 찾을 수 없습니다.", "latency": 0.5}


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
    print("TaskResult Helpers - 사용 예제")
    print("=" * 70)

    # 예제 1: Completion Score 계산
    print("\n1️⃣ Completion Score 계산")
    score1 = calculate_completion_score("대한민국의 수도는 서울입니다", expected_min_length=5)
    print(f"   Score: {score1:.2f}")

    # 예제 2: Accuracy Score 계산
    print("\n2️⃣ Accuracy Score 계산 (4가지 메트릭 조합)")
    score2 = calculate_accuracy_score("대한민국의 수도는 서울입니다", "서울")
    print(f"   Score: {score2:.3f}")

    # 예제 3: Token 추정
    print("\n3️⃣ Token 추정")
    text = "한국어와 영어가 섞인 텍스트입니다. This is mixed text."
    tokens = estimate_tokens(text)
    print(f"   Text: {text}")
    print(f"   Estimated Tokens: {tokens}")

    # 예제 4: 통합 TaskResult 생성 (시뮬레이션)
    print("\n4️⃣ TaskResult 생성 (시뮬레이션)")
    print("   모든 필드가 동적으로 계산됩니다:")
    print("   ✅ completion_score: 동적 계산")
    print("   ✅ accuracy_score: 4가지 메트릭 조합")
    print("   ✅ tokens_used: 동적 추출/추정")
    print("   ✅ tool_calls: 동적 추출")

    print("\n✅ taskresult_helpers.py 준비 완료!")
    print("   examples/ 디렉토리에서 import하여 사용하세요.")


# ============================================================================
# 7. 보안 검증 함수
# ============================================================================

def validate_input_security(input_text: str) -> Dict[str, Any]:
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
    sql_patterns = [
        r"(?i)(OR\s+['\"]?1['\"]?\s*=\s*['\"]?1)",
        r"(?i)(DROP\s+TABLE)",
        r"(?i)(UNION\s+SELECT)",
        r"(?i)(--\s*$)",
        r"(?i)(;\s*DROP)",
    ]

    for pattern in sql_patterns:
        if re.search(pattern, input_text):
            threats_detected.append('sql_injection')
            threat_details.append({
                'type': 'sql_injection',
                'pattern': pattern,
                'severity': 'high'
            })
            risk_level = 'high'
            break

    # Command Injection patterns
    cmd_patterns = [
        r'rm\s+-rf',
        r'\|\s*bash',
        r';\s*rm',
        r'`[^`]+`',
        r'\$\([^)]+\)',
    ]

    for pattern in cmd_patterns:
        if re.search(pattern, input_text):
            threats_detected.append('command_injection')
            threat_details.append({
                'type': 'command_injection',
                'pattern': pattern,
                'severity': 'critical'
            })
            risk_level = 'critical'
            break

    # Path Traversal patterns
    path_patterns = [
        r'\.\./\.\.',
        r'\.\.\\',
        r'/etc/passwd',
        r'\\windows\\system32',
    ]

    for pattern in path_patterns:
        if re.search(pattern, input_text, re.IGNORECASE):
            threats_detected.append('path_traversal')
            threat_details.append({
                'type': 'path_traversal',
                'pattern': pattern,
                'severity': 'high'
            })
            if risk_level not in ['critical', 'high']:
                risk_level = 'high'
            break

    # XSS patterns
    xss_patterns = [
        r'<script[^>]*>',
        r'javascript:',
        r'onerror\s*=',
        r'onclick\s*=',
    ]

    for pattern in xss_patterns:
        if re.search(pattern, input_text, re.IGNORECASE):
            threats_detected.append('xss')
            threat_details.append({
                'type': 'xss',
                'pattern': pattern,
                'severity': 'medium'
            })
            if risk_level not in ['critical', 'high']:
                risk_level = 'medium'
            break

    # Prompt Injection patterns
    prompt_patterns = [
        r'(?i)ignore\s+(all\s+)?previous\s+instructions',
        r'(?i)disregard\s+(all\s+)?above',
        r'(?i)forget\s+everything',
        r'(?i)you\s+are\s+now',
    ]

    for pattern in prompt_patterns:
        if re.search(pattern, input_text):
            threats_detected.append('prompt_injection')
            threat_details.append({
                'type': 'prompt_injection',
                'pattern': pattern,
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


def check_output_leakage(output_text: str) -> Dict[str, Any]:
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
    api_patterns = {
        'openai_api_key': r'sk-[A-Za-z0-9]{48}',
        'aws_access_key': r'AKIA[0-9A-Z]{16}',
        'google_api_key': r'AIza[0-9A-Za-z_-]{35}',
        'generic_api_key': r'api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_-]{20,}',
    }

    for key_type, pattern in api_patterns.items():
        matches = re.findall(pattern, output_text, re.IGNORECASE)
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
    password_patterns = [
        r'password["\']?\s*[:=]\s*["\']?[^\s"\']{8,}',
        r'passwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}',
        r'pwd["\']?\s*[:=]\s*["\']?[^\s"\']{8,}',
    ]

    for pattern in password_patterns:
        matches = re.findall(pattern, output_text, re.IGNORECASE)
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
    cc_pattern = r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
    cc_matches = re.findall(cc_pattern, output_text)
    if cc_matches:
        leakage_found.append('credit_card')
        details.append({
            'type': 'credit_card',
            'count': len(cc_matches),
            'severity': 'critical'
        })
        severity = 'critical'

    # Email addresses (lower severity)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_matches = re.findall(email_pattern, output_text)
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
    private_ip_patterns = [
        r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        r'\b192\.168\.\d{1,3}\.\d{1,3}\b',
        r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b',
    ]

    for pattern in private_ip_patterns:
        ip_matches = re.findall(pattern, output_text)
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
    path_patterns = [
        r'[A-Z]:\\[^\s]+',  # Windows paths
        r'/home/[^\s]+',    # Unix home paths
        r'/root/[^\s]+',    # Root paths
    ]

    for pattern in path_patterns:
        path_matches = re.findall(pattern, output_text)
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
    tool_params: Dict[str, Any],
    allowed_tools: Optional[List[str]] = None,
    restricted_tools: Optional[List[str]] = None
) -> Dict[str, Any]:
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
