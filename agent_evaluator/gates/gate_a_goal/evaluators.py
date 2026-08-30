"""
agent_evaluator.gates.gate_a_goal.evaluators
===============================================
Gate A(Goal Achievement) 평가 함수 6종.

SPEC-000: agent_evaluator/helpers/taskresult_helpers.py에서 그대로 이관(로직 변경 없음).
taskresult_helpers.py는 이 모듈을 re-export하여 하위호환을 유지한다.

이 모듈이 정의하는 private 헬퍼(_is_subtask_found, _is_subtask_find_pos,
_is_fact_retained_in_text, _kr_strip_particle, _clamp01 등)는 Gate A의 6개 eval 함수
전용으로만 사용됨을 확인했으므로 함께 이관했다(다른 Gate와 공유하지 않음).
"""
from __future__ import annotations

import logging
import re
from typing import Any, cast

logger = logging.getLogger(__name__)


def _clamp01(v: float) -> float:
    """Clamp value to [0.0, 1.0]."""
    return max(0.0, min(1.0, v))


def _is_subtask_found(subtask_lower: str, response_lower: str) -> bool:
    """서브태스크가 응답에서 단어 경계 매칭으로 발견되는지 확인.

    단순 substring(`in`)과 달리 복합어 내부 일치를 차단한다.
    - '데이터' in '메타데이터' → False (앞 문자 '타'가 한글 → 복합어 내부)
    - '데이터' in '데이터를' → True (before 경계 명확 + 뒤 한글은 조사로 허용)
    """
    return _is_subtask_find_pos(subtask_lower, response_lower) >= 0


def _is_subtask_find_pos(subtask_lower: str, response_lower: str) -> int:
    """경계 조건을 만족하는 첫 번째 매칭 위치를 반환한다.

    반환값이 -1이면 매칭 없음, 0 이상이면 해당 위치에서 경계 유효 매칭 발견.
    ordering 검사처럼 위치가 필요한 곳에서 `_is_subtask_found` 대신 사용한다.
    """
    idx = 0
    while True:
        pos = response_lower.find(subtask_lower, idx)
        if pos == -1:
            return -1
        before = response_lower[pos - 1] if pos > 0 else None
        after = response_lower[pos + len(subtask_lower)] if pos + len(subtask_lower) < len(response_lower) else None
        before_ok = before is None or not (before.isalnum() or '가' <= before <= '힣')
        if before_ok:
            after_ok = after is None or not after.isalnum() or '가' <= after <= '힣'
            if after_ok:
                return pos
        idx = pos + 1


# 사실 보존 검사용 1자 조사 허용 목록: 복합어 접미사(군/계/화/적/성/…)와 구분
# '으'는 독립 조사가 아니지만 '-으로/-으며/-으면' 등 복합 조사의 첫 음절로 반드시 등장하므로
# 허용 목록에 포함. 예: "결론으로" → after='으' → 허용 (결론이 사실로서 보존됨)
_KOREAN_PARTICLES_1 = frozenset('이가을를은는에도만와과의로서야아으')

# 숫자 뒤에 바로 붙는 한국어 단위 문자 허용 목록.
# 예: "2024년", "50개", "100명", "1500원", "3월", "25일"
# Python의 한글은 \w (isalnum=True) 이므로 \b 경계가 성립하지 않아
# \b\d{2,}\b 패턴은 한글 단위 접미 숫자를 추출하지 못함 — 이 셋으로 보완.
_KOREAN_UNITS = frozenset('년월일개명원억만천백위층번호')

# goal_coverage / goal_retained 토큰 비교 시 조사 제거용 (긴 조사 우선)
# eval_plan_coherence · eval_context_retention 에서 공유
_KR_PARTICLE_SUFFIXES: tuple = (
    "에서", "에게", "이랑", "으로", "처럼", "보다", "까지", "부터", "마다",  # 2글자
    "은", "는", "이", "가", "을", "를", "에", "의", "로", "도", "만", "과", "와", "랑",  # 1글자
)


def _kr_strip_particle(tok: str) -> str:
    """한국어 조사를 제거한 어근 반환 — 비한국어 토큰은 그대로 통과.

    조사를 제거했을 때 어근이 2글자 미만이 되면 원형을 반환한다.
    예: '서울의' → '서울',  '날씨를' → '날씨',  'weather' → 'weather'
    """
    if not any('가' <= c <= '힣' for c in tok):
        return tok
    for p in _KR_PARTICLE_SUFFIXES:
        if tok.endswith(p) and len(tok) - len(p) >= 2:
            return tok[:-len(p)]
    return tok

# goal_coverage / goal_retained 계산 시 제거할 기능어 목록
# eval_plan_coherence 와 eval_context_retention 에서 공유
_GOAL_STOPWORDS: frozenset = frozenset({
    # 영어 기능어 (조동사·be동사)
    "what", "is", "are", "was", "were", "the", "a", "an",
    "how", "why", "when", "where", "who", "which",
    "do", "does", "did", "can", "could", "will", "would", "should", "be",
    # 영어 전치사·접속사·지시사 — 문장 시작 대문자("In", "At", "Of" 등) auto-extract 오염 방지
    "in", "at", "of", "for", "with", "by", "from", "on", "to",
    "not", "but", "or", "and", "if", "as",
    "this", "that", "these", "those", "it", "its",
    # 한국어 조사·후치사 (독립 토큰)
    "이", "의", "을", "를", "은", "는", "에서", "에게", "에", "으로", "로",
    "도", "만", "과", "와", "이랑", "랑", "처럼", "보다", "까지", "부터", "마다",
    # 한국어 의문문·높임말 어미 (space-split 후 독립 토큰)
    "있나요", "있습니까", "해주세요", "알려주세요", "어떻습니까", "입니까",
    "인가요", "무엇입니까", "무엇인가요", "어떤가요", "어떻게",
})


def _is_fact_retained_in_text(fact_lower: str, text_lower: str) -> bool:
    """사실 보존 검사용 경계 매칭 (`_is_subtask_found`보다 엄격).

    `_is_subtask_found`의 after 조건은 모든 한글을 조사로 허용하므로,
    단어 끝이 한글인 사실(예: '제품')이 복합어('제품군') 앞에 오면 false positive가 발생한다.
    이 헬퍼는 after가 한글일 때 1자 조사 목록에 포함된 것만 허용한다.
    숫자 사실(예: "2024", "50")은 한국어 단위 접미사(_KOREAN_UNITS: 년·개·명·원 등)도 허용한다.
    """
    _is_numeric = fact_lower.isdigit()
    idx = 0
    while True:
        pos = text_lower.find(fact_lower, idx)
        if pos == -1:
            return False
        before = text_lower[pos - 1] if pos > 0 else None
        after = text_lower[pos + len(fact_lower)] if pos + len(fact_lower) < len(text_lower) else None
        before_ok = before is None or not (before.isalnum() or '가' <= before <= '힣')
        if before_ok:
            if after is None or not after.isalnum():
                return True
            if '가' <= after <= '힣':
                if after in _KOREAN_PARTICLES_1:
                    return True
                if _is_numeric and after in _KOREAN_UNITS:
                    return True
        idx = pos + 1


def eval_instruction_adherence(response: str, config: Any) -> dict[str, Any]:
    """응답이 InstructionConfig의 형식·길이·키워드 지시를 준수하는지 평가.

    Args:
        response: 에이전트 응답 텍스트.
        config: InstructionConfig 인스턴스.

    Returns:
        {score, violations, violation_count, checks}
    """
    violations: list[str] = []
    checks: dict[str, bool] = {}

    # 1. 형식 검사
    if config.expected_format:
        fmt = config.expected_format.lower()
        if fmt == "json":
            import json as _json
            try:
                _json.loads(response)
                checks["format"] = True
            except Exception:
                checks["format"] = False
                violations.append("응답이 JSON 형식이 아님")
        elif fmt == "markdown":
            checks["format"] = bool(
                re.search(r"#{1,6}\s", response) or
                re.search(r"\*\*[^*]+\*\*", response) or
                # (?:^|\n) — 응답 첫 줄 불릿(앞에 \n 없음)도 탐지 (r"\n[-*]\s" 는 첫 줄 누락)
                re.search(r"(?:^|\n)[-*][ \t]", response)
            )
            if not checks["format"]:
                violations.append("응답에 마크다운 요소 없음")
        elif fmt == "yaml":
            checks["format"] = bool(re.search(r"^\w[\w\s]*:", response, re.MULTILINE))
            if not checks["format"]:
                violations.append("응답이 YAML 형식이 아님")
        elif fmt == "plain":
            checks["format"] = True  # 평문은 항상 통과
        else:
            checks["format"] = True  # 알 수 없는 형식은 통과

    # 2. 섹션 검사
    if config.required_sections:
        missing = [s for s in config.required_sections if not _is_fact_retained_in_text(s.lower(), response.lower())]
        checks["sections"] = len(missing) == 0
        if missing:
            violations.append(f"필수 섹션 누락: {missing}")

    # 3. 길이 검사 (max/min chars + words)
    length_ok = True
    char_len = len(response)
    word_len = len(response.split())
    if config.max_chars is not None and char_len > config.max_chars:
        violations.append(f"응답 길이 초과: {char_len} > {config.max_chars} chars")
        length_ok = False
    if config.min_chars is not None and char_len < config.min_chars:
        violations.append(f"응답 길이 부족: {char_len} < {config.min_chars} chars")
        length_ok = False
    if config.max_words is not None and word_len > config.max_words:
        violations.append(f"단어 수 초과: {word_len} > {config.max_words}")
        length_ok = False
    if config.min_words is not None and word_len < config.min_words:
        violations.append(f"단어 수 부족: {word_len} < {config.min_words}")
        length_ok = False
    if any(getattr(config, k, None) is not None
           for k in ("max_chars", "min_chars", "max_words", "min_words")):
        checks["length"] = length_ok

    # 4. 금지 문구 검사
    if config.forbidden_phrases:
        found = [p for p in config.forbidden_phrases if _is_fact_retained_in_text(p.lower(), response.lower())]
        checks["forbidden"] = len(found) == 0
        if found:
            violations.append(f"금지 문구 포함: {found}")

    # 5. 필수 키워드 검사 — 경계 인식 매칭으로 서브스트링 false positive 방지
    # "AI" ∈ "training" 같은 오탐 방지 (eval_knowledge_retention과 동일 헬퍼 사용)
    if config.required_keywords:
        missing_kw = [
            k for k in config.required_keywords
            if not _is_fact_retained_in_text(k.lower(), response.lower())
        ]
        checks["keywords"] = len(missing_kw) == 0
        if missing_kw:
            violations.append(f"필수 키워드 누락: {missing_kw}")

    # 6. 언어 검사 (Unicode 범위 분석 — 외부 의존성 없음)
    expected_lang = getattr(config, "expected_language", None)
    if expected_lang and response.strip():
        lang_lower = expected_lang.lower()
        total_chars = max(len([c for c in response if c.strip()]), 1)

        def _ratio(start: int, end: int) -> float:
            return sum(1 for c in response if start <= ord(c) <= end) / total_chars

        korean_ratio = _ratio(0xAC00, 0xD7A3) + _ratio(0x1100, 0x11FF) + _ratio(0x3130, 0x318F)
        latin_ratio = _ratio(0x0041, 0x005A) + _ratio(0x0061, 0x007A)  # A-Z + a-z (0x5B-0x60 비문자 제외)
        cjk_ratio = _ratio(0x4E00, 0x9FFF) + _ratio(0x3040, 0x30FF)  # CJK + Hiragana/Katakana
        arabic_ratio = _ratio(0x0600, 0x06FF)

        if lang_lower in ("ko", "korean", "한국어"):
            lang_ok = korean_ratio > 0.2
        elif lang_lower in ("en", "english", "영어"):
            lang_ok = latin_ratio > 0.3 and korean_ratio < 0.1 and cjk_ratio < 0.1
        elif lang_lower in ("ja", "japanese", "일본어"):
            lang_ok = cjk_ratio > 0.1
        elif lang_lower in ("zh", "chinese", "중국어"):
            lang_ok = _ratio(0x4E00, 0x9FFF) > 0.1
        elif lang_lower in ("ar", "arabic", "아랍어"):
            lang_ok = arabic_ratio > 0.1
        else:
            lang_ok = True  # 알 수 없는 언어 코드는 통과

        checks["language"] = lang_ok
        if not lang_ok:
            violations.append(f"response language is not '{expected_lang}' (ko_ratio={korean_ratio:.2f}, en_ratio={latin_ratio:.2f})")

    # 설정된 검사 항목이 없으면 score=None — Gate A avg_ifr 집계에서 제외
    # (eval_plan_coherence가 components 없을 때 None을 반환하는 것과 동일 패턴)
    if not checks:
        return {
            "score": None,
            "violations": [],
            "violation_count": 0,
            "checks": {},
            "fail_on_violation": config.fail_on_violation,
        }

    violation_count = len(violations)
    violation_weights_map = getattr(config, "violation_weights", {}) or {}
    if violation_weights_map:
        # 위반 유형별 가중치 적용 (checks 키: format/sections/length/forbidden/keywords/language)
        total_penalty = sum(
            violation_weights_map.get(check_type, config.violation_weight)
            for check_type, passed in checks.items()
            if not passed
        )
        score = _clamp01(1.0 - total_penalty)
    else:
        score = _clamp01(1.0 - violation_count * config.violation_weight)

    return {
        "score": score,
        "violations": violations,
        "violation_count": violation_count,
        "checks": checks,
        "fail_on_violation": config.fail_on_violation,
    }


def eval_goal_alignment(
    question: str,
    tool_calls: list[dict[str, Any]],
    config: Any,
) -> dict[str, Any] | None:
    """질문(목표)과 도구 호출(행동)의 정렬 점수를 계산.

    Args:
        question: 사용자 질문.
        tool_calls: 도구 호출 리스트.
        config: GoalAlignmentConfig 인스턴스.

    Returns:
        정렬 결과 dict 또는 None (도구 호출 없고 ignore_no_tool_tasks=True).
    """
    if not tool_calls and config.ignore_no_tool_tasks:
        return None

    # "tool_name" / "tool" / "name" 순서로 키를 확인 — ToolCallAnalyzer와 동일 패턴
    # 데코레이터가 생성하는 내부 포맷은 "tool_name", 사용자 직접 제공 포맷은 "name"이 일반적
    tool_names = [
        n for tc in (tool_calls or [])
        if isinstance(tc, dict)
        for n in [tc.get("tool_name") or tc.get("tool") or tc.get("name", "")]
        if n  # 빈 문자열 제거
    ]
    aligned_tools: list[str] = []
    unaligned_tools: list[str] = []
    method = "none"
    score = 0.0

    if not tool_names:
        return {
            "score": 0.0, "method": "no_tools",
            "misaligned": [], "aligned_tools": [], "unaligned_tools": [],
            "below_threshold": True,
            "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
            "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
        }

    # goal_tool_map 방식
    if config.goal_tool_map:
        method = "goal_tool_map"
        question_lower = question.lower()
        mapped: set = set()
        for goal_kw, expected_tools in config.goal_tool_map.items():
            # 경계 인식 매칭 — "search" in "research" 류 false positive 방지
            if _is_fact_retained_in_text(goal_kw.lower(), question_lower):
                mapped.update(t.lower() for t in expected_tools)
        if mapped:
            for t in tool_names:
                if t.lower() in mapped:
                    aligned_tools.append(t)
                else:
                    unaligned_tools.append(t)
            score = len(aligned_tools) / len(tool_names) if tool_names else 0.0
        else:
            # goal_tool_map에 질문 키워드가 없음 → use_keyword_overlap 여부에 따라 분기
            if not config.use_keyword_overlap:
                # 폴백 금지 + 어떤 키워드도 매칭 안 됨 → 측정 불가 (0.0 반환 오류 방지)
                return {
                    "score": None, "method": "goal_tool_map_no_match",
                    "misaligned": [], "aligned_tools": [], "unaligned_tools": list(tool_names),
                    "below_threshold": None, "goal_tool_map_advisory": True,
                    "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
                    "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
                    "keyword_overlap_advisory": False,
                }
            logger.warning(
                "GoalAlignmentConfig: goal_tool_map keywords do not match the question (%r...). "
                "Falling back to keyword_overlap. Adjust the goal_tool_map keys to fit the question.",
                question[:40],
            )
            method = "keyword_overlap"

    # goal_tool_map 없이 keyword_overlap 폴백: 도구명이 영어 약어이면 False Negative 가능성 있음
    _kw_overlap_advisory = False
    if method in ("none", "keyword_overlap") and config.use_keyword_overlap:
        method = "keyword_overlap"
        if not config.goal_tool_map:
            _kw_overlap_advisory = True
            logger.debug(
                "GoalAlignmentConfig: goal_tool_map is unset — using the keyword_overlap method. "
                "English abbreviated tool names may not overlap question keywords, causing "
                "false negatives. Setting goal_tool_map={<goal keyword>: [<tool name>]} is recommended."
            )
        # 기능어 제거 후 의미 토큰만 비교 — "is_valid"의 "is"가 질문의 "is"와 false align 방지
        _q_raw = set(re.sub(r"[^\w\s]", "", question.lower()).split())
        q_tokens = {tok for tok in _q_raw if tok not in _GOAL_STOPWORDS and len(tok) >= 2}
        # 질문이 stopword만으로 구성된 경우 — 측정 불가, Gate A 오염 방지 (plan_coherence _has_q_tokens와 동일 패턴)
        if not q_tokens:
            return {
                "score": None,
                "method": "keyword_overlap_no_tokens",
                "misaligned": [],
                "aligned_tools": [],
                "unaligned_tools": list(tool_names),
                "below_threshold": None,
                "keyword_overlap_advisory": _kw_overlap_advisory,
                "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
                "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
            }
        for t in tool_names:
            t_tokens = set(re.sub(r"[-_]", " ", t.lower()).split())
            if q_tokens & t_tokens:
                aligned_tools.append(t)
            else:
                unaligned_tools.append(t)
        score = len(aligned_tools) / len(tool_names) if tool_names else 0.0

    # goal_tool_map도 keyword_overlap도 모두 비활성화된 경우 — 측정이 수행되지 않음.
    # score=0.0을 반환하면 Gate A에 거짓 0.0이 포함되어 점수를 왜곡하므로 score=None 반환.
    if method == "none":
        return {
            "score": None, "method": "no_measurement",
            "misaligned": [], "aligned_tools": [], "unaligned_tools": list(tool_names),
            "below_threshold": None,
            "keyword_overlap_advisory": False,
            "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
            "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
        }

    misaligned = unaligned_tools
    threshold = getattr(config, "alignment_threshold", 0.6) or 0.6
    below_threshold = score < threshold
    result: dict[str, Any] = {
        "score": score,
        "method": method,
        "misaligned": misaligned,
        "aligned_tools": aligned_tools,
        "unaligned_tools": unaligned_tools,
        "below_threshold": below_threshold,
        # goal_tool_map 없이 keyword_overlap 사용 중임을 외부에 알림
        "keyword_overlap_advisory": _kw_overlap_advisory,
        # use_llm_scoring 플래그를 저장 — _compute_harness_groups에서 LLM judge relevance와 블렌딩
        "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
        "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
    }
    return result


def eval_plan_coherence(
    response: str,
    question: str,
    config: Any,
) -> dict[str, Any] | None:
    """응답에서 계획(단계 목록)을 추출하고 일관성을 평가.

    Args:
        response: 에이전트 응답 텍스트.
        question: 사용자 질문(목표 커버리지 확인에 사용).
        config: PlanConfig 인스턴스.

    Returns:
        계획 평가 결과 dict 또는 None (계획 없음).
    """
    import json as _json

    steps: list[str] = []
    _from_json = False  # JSON 배열에서 파싱 성공 여부 — 순서가 인덱스에 내재됨

    # 1. JSON 파싱 시도
    try:
        parsed = _json.loads(response)
        if isinstance(parsed, dict):
            # sentinel으로 키 존재 여부와 빈 리스트를 구분:
            # steps_field=[] (빈 계획)와 steps_field 키 부재(→ plan_field 폴백)를 다르게 처리
            _MISSING = object()
            _raw = parsed.get(config.steps_field, _MISSING)
            if _raw is _MISSING:
                _raw = parsed.get(config.plan_field)
            raw_steps = _raw
            if isinstance(raw_steps, list):
                steps = [str(s) for s in raw_steps]
                _from_json = True
        elif isinstance(parsed, list):
            steps = [str(s) for s in parsed]
            _from_json = True
    except Exception:
        pass

    # 2. 번호 매기기 패턴 추출 (1. / 2. / - / *)
    if not steps:
        # JSON 파싱으로 빈 배열이 나왔더라도 여기서 plain text 폴백 사용 시 _from_json을 리셋.
        # 그렇지 않으면 bullet-point 단계가 JSON 배열인 것처럼 ordering_score=1.0을 얻어 오판.
        _from_json = False
        numbered = re.findall(r"^\s*(?:\d+[.)]\s*|[-*]\s+)(.+)", response, re.MULTILINE)
        if numbered:
            steps = [s.strip() for s in numbered]

    if not steps:
        return None

    # 단계 수 검사
    step_count = len(steps)
    if step_count < config.min_steps or step_count > config.max_steps:
        pass  # 기록은 하되 점수에 반영

    # 3. 목표 커버리지 (기능어 제거 후 의미 토큰만 비교)
    goal_coverage = 0.0
    _has_q_tokens = False  # stopword 필터 후 의미 토큰 존재 여부 추적
    if config.check_goal_coverage and question:
        _q_raw = set(re.sub(r"[^\w\s]", "", question.lower()).split())
        q_tokens = {t for t in (_q_raw - _GOAL_STOPWORDS) if len(t) >= 2}
        plan_text = " ".join(steps).lower()
        plan_tokens = set(re.sub(r"[^\w\s]", "", plan_text).split())
        if q_tokens:
            _has_q_tokens = True
            # 한국어 조사 탈락 매칭: '서울의'(질문) ↔ '서울'(계획) 같은 형태 차이 허용
            # plan에 있는 토큰의 어근도 조회 집합에 추가
            _plan_lookup = plan_tokens | {_kr_strip_particle(t) for t in plan_tokens}
            _matched_goal = sum(
                1 for qt in q_tokens
                if qt in _plan_lookup or _kr_strip_particle(qt) in _plan_lookup
            )
            goal_coverage = _matched_goal / len(q_tokens)

    # 4. 단계 순서: 번호 목록이면 1.0, 아니면 순서 접속사 비율로 평가
    if config.check_step_ordering:
        # JSON 배열 파싱 성공 시 인덱스 순서가 이미 확정됨 — 번호 목록과 동등하게 처리.
        # JSON steps의 순서는 데이터 구조 자체가 보장하므로, sequential marker 검사를 건너뜀.
        is_numbered = _from_json or bool(re.search(r"^\s*\d+[.)]\s", response or "", re.MULTILINE))
        # step_count <= 1: 단일 단계 플랜은 정의상 순서 문제가 없음 — marker 검사 의미 없음
        if is_numbered or step_count <= 1:
            ordering_score = 1.0
        else:
            sequential_markers = [
                "then", "next", "after", "finally", "second", "third", "fourth", "fifth",
                "다음", "그 다음", "이후", "마지막으로", "그런 다음",
            ]
            # _is_subtask_found 사용: 한국어 조사 '으로' 등이 마커 뒤에 붙는 경우 허용
            # (_is_fact_retained_in_text는 _KOREAN_PARTICLES_1만 허용해 '다음으로'가 '다음'과 불일치)
            steps_with_markers = sum(
                1 for step in steps if any(_is_subtask_found(m, step.lower()) for m in sequential_markers)
            )
            ordering_score = min(1.0, steps_with_markers / max(step_count * 0.5, 1))
    else:
        ordering_score = 1.0

    # 5. 실행 가능성 (available_tools가 있으면 각 단계에서 도구 언급 비율)
    executability_score = 1.0
    if config.check_executability and not config.available_tools:
        logger.warning(
            "PlanConfig: check_executability=True but available_tools is empty, so the "
            "executability check is skipped. Specify available_tools to enable this check."
        )
    if config.check_executability and config.available_tools:
        executable = 0
        for step in steps:
            if any(_is_fact_retained_in_text(t.lower(), step.lower()) for t in config.available_tools):
                executable += 1
        executability_score = executable / step_count if step_count else 0.0

    # 최종 점수: 활성화된 체크만 평균 (비활성 체크를 0.0으로 포함하면 최대 점수가 제한됨)
    # check_goal_coverage=True라도 question이 빈 문자열이거나 stopword만 있으면 goal_coverage=0.0이 되어
    # 에이전트 잘못 없이 점수를 낮추므로 별도 플래그로 분리 (_has_q_tokens: 의미 토큰 존재 여부)
    _can_goal = config.check_goal_coverage and bool(question) and _has_q_tokens
    components = []
    if _can_goal:
        components.append(goal_coverage)
    if config.check_step_ordering:
        components.append(ordering_score)
    if config.check_executability and config.available_tools:
        components.append(executability_score)
    if not components:
        # 모든 체크가 명시적으로 비활성화된 경우 — 의미 있는 점수를 계산할 수 없음
        return None
    score = sum(components) / len(components)

    # min_steps / max_steps 위반 페널티 (이탈량에 비례, 최대 0.30)
    min_steps_ok = step_count >= config.min_steps
    max_steps_ok = step_count <= config.max_steps
    if not min_steps_ok or not max_steps_ok:
        deviation = max(0, config.min_steps - step_count) + max(0, step_count - config.max_steps)
        steps_penalty = min(0.30, deviation * 0.05)
        score = max(0.0, score - steps_penalty)

    return {
        "score": score,
        # 비활성 체크는 None — 0.0/1.0 초기값이 "측정된 결과"처럼 오해되는 것을 방지
        "goal_coverage": goal_coverage if _can_goal else None,
        "ordering_score": ordering_score if config.check_step_ordering else None,
        "executability_score": (
            executability_score
            if config.check_executability and bool(getattr(config, "available_tools", None))
            else None
        ),
        "step_count": step_count,
        "steps": steps,
        "min_steps_ok": min_steps_ok,
        "max_steps_ok": max_steps_ok,
        # use_llm_scoring 플래그 — _compute_harness_groups에서 LLM judge relevance와 블렌딩
        "use_llm_scoring": bool(getattr(config, "use_llm_scoring", False)),
        "llm_blend_weight": float(getattr(config, "llm_blend_weight", 0.5)),
    }


def eval_context_retention(
    response: str, question: str, context: str, config: Any
) -> dict[str, Any]:
    """에이전트가 핵심 컨텍스트 엔티티 및 원래 목표를 보존하는지 평가한다.

    Args:
        response: 에이전트 응답 문자열.
        question: 원래 질문.
        context: RAG 또는 대화 컨텍스트 문자열.
        config: ContextRetentionConfig 인스턴스.

    Returns:
        {retention_score, entities_retained, entities_lost, entity_retention_rate, goal_retained}
    """
    response_lower = response.lower() if response else ""

    key_entities = list(getattr(config, "key_entities", []) or [])
    check_original_goal = getattr(config, "check_original_goal", True)
    entity_weight = getattr(config, "entity_weight", 0.6)
    goal_weight = getattr(config, "goal_weight", 0.4)

    # key_entities 미지정 + context 제공 시 context에서 엔티티 자동 추출
    if not key_entities and context:
        _auto: list[str] = []
        _auto.extend(re.findall(r'\d{2,}', context))
        _auto.extend(re.findall(r'\b[A-Z][a-z]+', context))
        _auto.extend(re.findall(r'[가-힣]{3,}', context))  # 2글자는 기능어 오염 — knowledge_retention과 동일 기준
        # 문장 시작 기능어("The", "In", "An" 등) 제거는 dedup 단계에서 — eval_knowledge_retention과 동일 패턴
        # [:20] 제한은 필터 후 적용해야 의미 있는 엔티티 20개를 보장 (필터 전 적용 시 기능어가 슬롯 차지)
        _seen_e: dict[str, None] = {}
        for _e in _auto:
            if _e.lower() not in _GOAL_STOPWORDS and len(_e) >= 2:
                _seen_e[_e] = None
        key_entities = list(_seen_e.keys())[:20]

    # Entity retention — 경계 인식 매칭으로 false positive 방지
    # eval_knowledge_retention과 동일한 _is_fact_retained_in_text 사용
    entities_retained: list[str] = []
    entities_lost: list[str] = []
    for entity in key_entities:
        if _is_fact_retained_in_text(entity.lower(), response_lower):
            entities_retained.append(entity)
        else:
            entities_lost.append(entity)

    entity_score = 1.0
    if key_entities:
        entity_score = len(entities_retained) / len(key_entities)

    # Goal retention: 구두점 제거 후 기능어 필터링한 의미 토큰이 응답에 포함되는지 확인
    goal_retained = False
    _can_check_goal = False  # 의미 토큰이 존재해 실제로 goal 검사를 수행했을 때만 True
    if check_original_goal and question:
        _q_raw = set(re.sub(r"[^\w\s]", "", question.lower()).split())
        r_tokens = set(re.sub(r"[^\w\s]", "", response_lower).split())
        # _GOAL_STOPWORDS 공유 (eval_plan_coherence와 동일 기준) + 1글자 토큰 제거
        q_sig = {t for t in (_q_raw - _GOAL_STOPWORDS) if len(t) >= 2}
        if q_sig:
            _can_check_goal = True
            # 한국어 조사 탈락 매칭: '서울의'(질문) ↔ '서울'(응답) 같은 형태 차이 허용
            _r_lookup = r_tokens | {_kr_strip_particle(t) for t in r_tokens}
            _matched_sig = sum(
                1 for qt in q_sig
                if qt in _r_lookup or _kr_strip_particle(qt) in _r_lookup
            )
            overlap = _matched_sig / len(q_sig)
            goal_retained = overlap >= float(getattr(config, "goal_overlap_threshold", 0.3))
        else:
            # q_sig 비어 있으면 측정 불가 — goal_retained=True 유지(compat), 가드에서 걸러짐
            goal_retained = True

    goal_score = 1.0 if goal_retained else 0.0

    # goal도 entity도 측정하지 않은 경우 — Gate A avg_context_r에서 제외 (0.0/1.0 포함 방지)
    # _can_check_goal=False: check_original_goal=False / question="" / q_sig={} 케이스 모두 커버
    if not key_entities and not _can_check_goal:
        return {
            "retention_score": None,
            "entities_retained": [],
            "entities_lost": [],
            "entity_retention_rate": None,
            "goal_retained": None,
            "threshold_met": None,
            "no_checks": True,
        }

    if key_entities:
        if _can_check_goal:
            # 가중치 합으로 나누어 정규화: entity_weight + goal_weight ≠ 1.0 이면 점수가 왜곡됨
            # 예) entity_weight=0.3, goal_weight=0.2 → 최대 0.5로 제한되는 문제 방지
            _w_sum = entity_weight + goal_weight
            retention_score = _clamp01(
                (entity_weight * entity_score + goal_weight * goal_score) / max(_w_sum, 1e-9)
            )
        else:
            # goal 검사 불가 또는 비활성 (_can_check_goal=False): goal_weight를 분모에 포함하면
            # goal_score=0.0이 0.4 페널티로 작용해 최대 retention_score=0.6으로 제한됨 — 버그 방지
            # entity score만으로 전체 점수 산출 (check_original_goal=False / question="" / q_sig={} 공통)
            retention_score = entity_score
    else:
        # key_entities 없음: entity 파트 제외하고 goal만으로 평가
        retention_score = goal_score

    threshold = float(getattr(config, "retention_threshold", 0.7))
    return {
        "retention_score": round(retention_score, 4),
        "entities_retained": entities_retained,
        "entities_lost": entities_lost,
        "entity_retention_rate": round(entity_score, 4),
        "goal_retained": goal_retained,
        "threshold_met": retention_score >= threshold,
    }


def eval_subtask_completion(
    response: str, tool_calls: list[Any], config: Any, question: str = ""
) -> dict[str, Any]:
    """예상 하위 작업의 완료율을 평가한다.

    Args:
        response: 에이전트 응답 문자열.
        tool_calls: 도구 호출 리스트 (현재 미사용, 향후 확장용).
        config: SubtaskConfig 인스턴스.
        question: 원래 질문 텍스트 (auto_extract 시 단계 추출 소스).

    Returns:
        {completion_rate, completed, incomplete, subtask_count, ordering_ok}
    """
    import re as _re

    response_lower = response.lower() if response else ""

    expected_subtasks = list(getattr(config, "expected_subtasks", []) or [])
    completion_markers = getattr(config, "completion_markers", []) or []
    check_ordering = getattr(config, "check_ordering", False)
    auto_extract = getattr(config, "auto_extract", False)

    # Auto-extract numbered/bullet steps from question (NOT response) to avoid self-reference bias.
    # response를 소스로 쓰면 추출된 단계가 response 자체에서 항상 발견되어 completion_rate=1.0 고착
    if auto_extract and not expected_subtasks:
        if not question:
            logger.warning(
                "SubtaskConfig(auto_extract=True): question is empty, so sub-tasks cannot be "
                "extracted. Using response as the source causes self-reference bias, so this "
                "is skipped. Specify expected_subtasks directly, or pass a question."
            )
        else:
            lines = question.split("\n")
            extracted: list[str] = []
            for line in lines:
                line = line.strip()
                if _re.match(r"^(\d+[.)]\s+|\-\s+|\*\s+|•\s+)", line) and len(line) > 3:
                    extracted.append(_re.sub(r"^(\d+[.)]\s+|\-\s+|\*\s+|•\s+)", "", line).strip())
            expected_subtasks = extracted[:20]

    if not expected_subtasks:
        return {
            "completion_rate": 1.0,
            "completed": [],
            "incomplete": [],
            "subtask_count": 0,
            "ordering_ok": True,
        }

    completed: list[str] = []
    incomplete: list[str] = []
    non_empty_lines = [l for l in response_lower.split("\n") if l.strip()]

    for i, subtask in enumerate(expected_subtasks):
        subtask_lower = subtask.lower()
        # 1차: 단어 경계 매칭 (substring 부분 일치 False Positive 방지)
        found = _is_subtask_found(subtask_lower, response_lower)
        if not found and completion_markers:
            # 2차(위치 기반): 이름 매칭 실패 시 N번째 줄 + 마커 + 서브태스크 이름 토큰 동시 검사
            if i < len(non_empty_lines):
                line = non_empty_lines[i]
                has_marker = any(_is_fact_retained_in_text(m.lower(), line) for m in completion_markers)
                subtask_tokens = [t for t in subtask_lower.split() if len(t) >= 2]
                has_name_signal = bool(subtask_tokens) and any(_is_fact_retained_in_text(t, line) for t in subtask_tokens)
                if has_marker and has_name_signal:
                    found = True
        if found:
            completed.append(subtask)
        else:
            incomplete.append(subtask)

    completion_rate = len(completed) / len(expected_subtasks) if expected_subtasks else 1.0

    # Ordering check: verify completed tasks appear in expected order in response
    # 위치 기반 마커로 완료된 태스크(이름이 응답에 없음)는 순서 검사에서 제외
    # _is_subtask_find_pos: 경계 유효한 첫 위치 반환 (_is_subtask_found와 동일 로직)
    ordering_ok = True
    if check_ordering and len(completed) >= 2:
        # pos=-1(마커 완료, 텍스트 위치 미확인) → float('inf')로 처리 (가장 뒤에 있다고 보수적 가정)
        positions: list[float] = []
        for task in completed:
            pos = _is_subtask_find_pos(task.lower(), response_lower)
            positions.append(float(pos) if pos >= 0 else float("inf"))
        ordering_ok = all(positions[i] <= positions[i + 1] for i in range(len(positions) - 1)) if len(positions) >= 2 else True

    min_rate = float(getattr(config, "min_completion_rate", 0.8))
    return {
        "completion_rate": round(completion_rate, 4),
        "completed": completed,
        "incomplete": incomplete,
        "subtask_count": len(expected_subtasks),
        "ordering_ok": ordering_ok,
        "threshold_met": completion_rate >= min_rate,
        "min_completion_rate": min_rate,
    }


def eval_knowledge_retention(
    response: str | None,
    conversation_history: list[dict[str, Any]] | None,
    config: Any,
) -> dict[str, Any] | None:
    """대화 중 사실 보존 평가 (Harness A — Goal Achievement).

    Args:
        response: 평가할 에이전트 응답 텍스트.
        conversation_history: 이전 대화 기록 (turn dict 리스트).
        config: :class:`KnowledgeRetentionConfig` 인스턴스.

    Returns:
        Dict with keys: retention_score, retained_facts, forgotten_facts,
        seed_facts_count, retention_threshold.  사실이 없으면 ``None`` 반환.
    """
    # check_from_turn: 현재 턴이 기준 미만이면 평가 건너뜀
    check_from = int(getattr(config, "check_from_turn", 3))
    current_turn = len(conversation_history) + 1 if conversation_history else 1
    if current_turn < check_from:
        return None

    facts: list[str] = list(config.facts_to_retain or [])

    # auto_extract_seed=True 일 때만 seed 턴에서 사실 자동 추출 (opt-in)
    # 광범위한 정규식(특히 한국어 [가-힣]{3,})은 노이즈를 유발하므로 기본 비활성
    if not facts and conversation_history and bool(getattr(config, "auto_extract_seed", False)):
        seed = list(conversation_history)[:config.seed_turns]
        for turn in seed:
            text = turn.get("user", "") or turn.get("content", "") or ""
            # Numbers (2+ digits)
            facts.extend(re.findall(r'\d{2,}', text))
            # Capitalized words (potential proper nouns) — 2+ chars
            facts.extend(re.findall(r'\b[A-Z][a-z]{1,}', text))
            # Korean nouns: kiwipiepy NNG/NNP 필터 우선, 없으면 3글자 이상 한자어 패턴 폴백
            try:
                from kiwipiepy import Kiwi as _Kiwi
                _kiwi = _Kiwi()
                for token in cast(Any, _kiwi.tokenize(text)):
                    if token.tag in ("NNG", "NNP") and len(token.form) >= 2:
                        facts.append(token.form)
            except ImportError:
                facts.extend(re.findall(r'[가-힣]{3,}', text))
        # Deduplicate + stopword 필터 (eval_context_retention 자동 추출과 동일 패턴)
        # 문장 시작 기능어 "The", "In", "What" 등이 facts에 포함되면 응답에서 항상 발견되어
        # retention_score를 허위 상향시키므로 제거 (Round 20 eval_context_retention 수정과 동일 이슈)
        _seen: dict[str, None] = {}
        for f in facts:
            if f.lower() not in _GOAL_STOPWORDS and len(f) >= 2:
                _seen[f] = None
        facts = list(_seen.keys())[:20]

    if not facts:
        return None

    response_lower = (response or "").lower()
    allow_implicit = bool(getattr(config, "allow_implicit_retention", True))

    def _fact_retained(fact: str) -> bool:
        # 조사 허용 목록 기반 경계 검사: '제품'이 '제품군'에서 false positive 방지
        if _is_fact_retained_in_text(fact.lower(), response_lower):
            return True
        if allow_implicit:
            tokens = fact.lower().split()
            # 분모·분자 모집단 일치: len >= 2 필터를 양쪽에 동일 적용
            long_tokens = [t for t in tokens if len(t) >= 2]
            if long_tokens:
                coverage = sum(1 for t in long_tokens if _is_fact_retained_in_text(t, response_lower)) / len(long_tokens)
                return coverage >= 0.5
        return False

    retained = [f for f in facts if _fact_retained(f)]
    forgotten = [f for f in facts if not _fact_retained(f)]

    retention_rate = len(retained) / len(facts) if facts else 1.0
    threshold = float(getattr(config, "retention_threshold", 0.6))

    return {
        "retention_score": round(retention_rate, 4),
        "retained_facts": retained,
        "forgotten_facts": forgotten,
        "seed_facts_count": len(facts),
        "retention_threshold": threshold,
        "threshold_met": retention_rate >= threshold,
    }
