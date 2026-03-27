"""
agent_evaluator.core.trackers.conversation
==========================================
멀티턴 대화 평가 — ConversationSession

외부 LLM 의존성 없이 순수 Python으로 4개 지표를 계산합니다:
  - context_retention  : 이전 턴 참조 비율
  - topic_coherence    : 주제 일관성 (Jaccard)
  - progressive_depth  : 대화 심화 정도
  - session_completion : 마지막 응답 완결성 추정
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopword sets
# ---------------------------------------------------------------------------

_KO_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과",
    "도", "만", "라", "이다", "있다", "하다", "것", "수", "그", "저",
    "이런", "저런",
}

_EN_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "on",
    "at", "for", "with", "and", "or", "but", "not", "this", "that",
    "it", "its",
}

_STOPWORDS = _KO_STOPWORDS | _EN_STOPWORDS

# 한국어 어절 말미에 붙는 조사/어미 패턴 (접미 제거용)
# 긴 패턴을 먼저 나열해서 최장 일치로 제거
_KO_SUFFIX_PATTERN = re.compile(
    r"(에서|으로|이라|이고|이며|하고|하며|에게|한테|부터|까지|처럼|만큼|보다"
    r"|이다|있다|하다|합니다|입니다|습니다|됩니다|않다|못하다|않다는|못합니다"
    r"|에서|으로|이고|이며|에도|에만|으로는|으로도"
    r"|에서는|에서도|에서만"
    r"|이란|이나|이며"
    r"|을|를|은|는|이|가|의|에|로|와|과|도|만|라)$"
)


def _strip_ko_suffix(token: str) -> str:
    """한국어 토큰에서 조사/어미를 최대 2회 제거. 어근이 2자 미만이 되면 중단."""
    for _ in range(2):
        m = _KO_SUFFIX_PATTERN.search(token)
        if m:
            root = token[: m.start()]
            if len(root) >= 2:
                token = root
            else:
                break
        else:
            break
    return token


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """단어 단위 토큰화, stopword 제거, 소문자화. 2글자 이상만 반환.

    한국어 어절에서 조사/어미를 제거하여 어근 기반 비교가 가능하도록 정규화합니다.
    영어 토큰은 소문자화만 수행합니다.
    """
    raw_tokens = re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())
    result = []
    for tok in raw_tokens:
        # 한국어 포함 어절은 조사 제거 시도
        if re.search(r"[가-힣]", tok):
            tok = _strip_ko_suffix(tok)
        if len(tok) >= 2 and tok not in _STOPWORDS:
            result.append(tok)
    return result


def _top_tokens(text: str, n: int = 10) -> set:
    """빈도 기준 상위 N개 토큰 집합."""
    tokens = _tokenize(text)
    if not tokens:
        return set()
    counter = Counter(tokens)
    return {tok for tok, _ in counter.most_common(n)}


def _jaccard(a: set, b: set) -> float:
    """Jaccard 유사도 — 분모 0 guard 포함."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ConversationTurn:
    """단일 대화 턴."""

    turn_index: int
    user: str
    agent: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationMetrics:
    """ConversationSession.compute_metrics()가 반환하는 평가 결과."""

    session_id: str
    turn_count: int
    context_retention: float
    topic_coherence: float
    progressive_depth: float
    session_completion: float
    avg_turn_latency: Optional[float]
    overall_score: float
    computed_at: str  # ISO-8601 datetime string

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화용 dict 반환."""
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "context_retention": self.context_retention,
            "topic_coherence": self.topic_coherence,
            "progressive_depth": self.progressive_depth,
            "session_completion": self.session_completion,
            "avg_turn_latency": self.avg_turn_latency,
            "overall_score": self.overall_score,
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ConversationSession:
    """멀티턴 대화 평가 세션.

    사용 패턴 1 — 직접 생성::

        session = ConversationSession("s_001")
        session.add_turn(user="질문1", agent="응답1")
        session.add_turn(user="질문2", agent="응답2", metadata={"latency": 1.2})
        metrics = session.compute_metrics()

    사용 패턴 2 — PerformanceMonitor 컨텍스트 매니저::

        with monitor.conversation("session_001") as conv:
            conv.turn(user="질문", agent="응답")
        # 세션 종료 시 자동으로 지표 계산 및 monitor에 기록

    Attributes:
        session_id: 세션 고유 ID.
        turns: 누적된 ConversationTurn 목록.
        metrics: compute_metrics() 호출 후 채워지는 ConversationMetrics 인스턴스.
    """

    def __init__(
        self,
        session_id: str,
        monitor: Optional[Any] = None,
    ) -> None:
        self.session_id = session_id
        self._monitor = monitor
        self.turns: List[ConversationTurn] = []
        self.metrics: Optional[ConversationMetrics] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_turn(
        self,
        user: str,
        agent: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ConversationSession":
        """대화 턴 추가.

        Args:
            user: 사용자 발화 텍스트.
            agent: 에이전트 응답 텍스트.
            metadata: 추가 정보 (예: ``{"latency": 1.2, "tool_calls": [...]}``)

        Returns:
            self — 메서드 체이닝 지원.
        """
        turn = ConversationTurn(
            turn_index=len(self.turns),
            user=user,
            agent=agent,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )
        self.turns.append(turn)
        return self

    # alias for context-manager style: conv.turn(...)
    def turn(
        self,
        user: str,
        agent: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ConversationSession":
        """add_turn()의 짧은 별칭. 컨텍스트 매니저 패턴에서 편의 사용."""
        return self.add_turn(user=user, agent=agent, metadata=metadata)

    def compute_metrics(self) -> ConversationMetrics:
        """대화 지표를 계산하고 ConversationMetrics를 반환.

        Returns:
            ConversationMetrics — 계산된 지표.

        Raises:
            ValueError: 턴이 하나도 없을 경우.
        """
        if not self.turns:
            raise ValueError("compute_metrics()를 호출하려면 최소 1턴이 필요합니다.")

        n = len(self.turns)

        context_retention = self._compute_context_retention()
        topic_coherence = self._compute_topic_coherence()
        progressive_depth = self._compute_progressive_depth()
        session_completion = self._compute_session_completion()
        avg_turn_latency = self._compute_avg_turn_latency()

        # overall_score: 4개 지표의 단순 평균
        overall_score = (
            context_retention + topic_coherence + progressive_depth + session_completion
        ) / 4.0

        self.metrics = ConversationMetrics(
            session_id=self.session_id,
            turn_count=n,
            context_retention=round(context_retention, 6),
            topic_coherence=round(topic_coherence, 6),
            progressive_depth=round(progressive_depth, 6),
            session_completion=round(session_completion, 6),
            avg_turn_latency=avg_turn_latency,
            overall_score=round(overall_score, 6),
            computed_at=datetime.utcnow().isoformat(),
        )
        return self.metrics

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화용 dict 반환."""
        return {
            "session_id": self.session_id,
            "turns": [
                {
                    "turn_index": t.turn_index,
                    "user": t.user,
                    "agent": t.agent,
                    "timestamp": t.timestamp.isoformat(),
                    "metadata": t.metadata,
                }
                for t in self.turns
            ],
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
        }

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ConversationSession":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """세션 종료 시 자동으로 compute_metrics() 호출 및 monitor에 기록."""
        if self.turns:
            try:
                self.compute_metrics()
            except Exception as e:
                logger.warning("compute_metrics() 실패 (세션=%s): %s", self.session_id, e)

        if self._monitor is not None and self.metrics is not None:
            try:
                self._monitor.conversation_sessions.append(self)
            except AttributeError as e:
                logger.warning("monitor.conversation_sessions 접근 실패: %s", e)

    # ------------------------------------------------------------------
    # Internal metric computations
    # ------------------------------------------------------------------

    def _compute_context_retention(self) -> float:
        """이전 응답의 top-N 단어가 현재 응답에 등장하는 비율 평균.

        1턴이면 비교 불가하므로 1.0 반환.
        """
        n = len(self.turns)
        if n <= 1:
            return 1.0

        scores: List[float] = []
        for i in range(1, n):
            prev_top = _top_tokens(self.turns[i - 1].agent, n=10)
            curr_tokens = set(_tokenize(self.turns[i].agent))
            if not prev_top:
                scores.append(1.0)
                continue
            overlap = len(prev_top & curr_tokens) / len(prev_top)
            scores.append(overlap)

        return sum(scores) / len(scores) if scores else 1.0

    def _compute_topic_coherence(self) -> float:
        """인접 턴 간 질문+응답 단어 집합의 Jaccard 유사도 평균.

        1턴이면 1.0 반환.
        """
        n = len(self.turns)
        if n <= 1:
            return 1.0

        scores: List[float] = []
        for i in range(1, n):
            prev_set = set(_tokenize(self.turns[i - 1].user + " " + self.turns[i - 1].agent))
            curr_set = set(_tokenize(self.turns[i].user + " " + self.turns[i].agent))
            scores.append(_jaccard(prev_set, curr_set))

        return sum(scores) / len(scores) if scores else 1.0

    def _compute_progressive_depth(self) -> float:
        """사용자 질문이 직전 에이전트 응답의 핵심 단어를 포함하는 비율.

        첫 턴은 제외. 2턴 미만이면 0.0 반환.
        """
        n = len(self.turns)
        if n <= 1:
            return 0.0

        scores: List[float] = []
        for i in range(1, n):
            prev_top = _top_tokens(self.turns[i - 1].agent, n=10)
            user_tokens = set(_tokenize(self.turns[i].user))
            if not prev_top:
                scores.append(0.0)
                continue
            overlap = len(prev_top & user_tokens) / len(prev_top)
            scores.append(overlap)

        return sum(scores) / len(scores) if scores else 0.0

    def _compute_session_completion(self) -> float:
        """마지막 응답 길이 / 평균 응답 길이 비율 (최대 1.0).

        단독으로는 약하지만 overall_score 구성 요소로 사용.
        응답이 없으면 0.0 반환.
        """
        if not self.turns:
            return 0.0

        lengths = [len(t.agent) for t in self.turns]
        avg_len = sum(lengths) / len(lengths)
        if avg_len == 0:
            return 0.0

        last_len = lengths[-1]
        return min(1.0, last_len / avg_len)

    def _compute_avg_turn_latency(self) -> Optional[float]:
        """metadata의 'latency' 값 평균. 없으면 None."""
        latencies = [
            t.metadata["latency"]
            for t in self.turns
            if "latency" in t.metadata and isinstance(t.metadata["latency"], (int, float))
        ]
        if not latencies:
            return None
        return sum(latencies) / len(latencies)
