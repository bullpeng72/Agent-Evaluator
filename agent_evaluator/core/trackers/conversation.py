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

import dataclasses
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...exceptions import InvalidOperationError

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
_RE_TOKENIZE = re.compile(r"[가-힣a-zA-Z0-9]+")
_RE_KO_CHAR = re.compile(r"[가-힣]")

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
    raw_tokens = _RE_TOKENIZE.findall(text.lower())
    result = []
    for tok in raw_tokens:
        # 한국어 포함 어절은 조사 제거 시도
        if _RE_KO_CHAR.search(tok):
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

    def __repr__(self) -> str:
        user_preview = self.user[:40] + "…" if len(self.user) > 40 else self.user
        agent_preview = self.agent[:40] + "…" if len(self.agent) > 40 else self.agent
        return (
            f"ConversationTurn(index={self.turn_index}, "
            f"user={user_preview!r}, agent={agent_preview!r})"
        )


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
    score_stddev: float  # 4개 구성 점수의 표준편차. **낮을수록 균형 잡힌 대화**를 의미.
    #   0.0 = 모든 차원 점수 동일(완벽한 균형), 0.5 = 보통, ≥0.3 = 특정 차원 편중 주의.
    computed_at: str  # ISO-8601 datetime string
    # F1: 턴별 품질 점수 (선택 항목 — turn_score_fn 지정 시 채워짐)
    turn_scores: Optional[Dict[int, float]] = None

    def __repr__(self) -> str:
        return (
            f"ConversationMetrics(session_id={self.session_id!r}, "
            f"turns={self.turn_count}, "
            f"overall={self.overall_score:.3f}, "
            f"context={self.context_retention:.3f}, "
            f"coherence={self.topic_coherence:.3f})"
        )

    def __str__(self) -> str:
        lines = [
            f"ConversationMetrics — {self.session_id}",
            f"  Turns             : {self.turn_count}",
            f"  Overall Score     : {self.overall_score:.3f}",
            f"  Context Retention : {self.context_retention:.3f}",
            f"  Topic Coherence   : {self.topic_coherence:.3f}",
            f"  Progressive Depth : {self.progressive_depth:.3f}",
            f"  Session Completion: {self.session_completion:.3f}",
            f"  Score Stddev      : {self.score_stddev:.3f}",
        ]
        if self.avg_turn_latency is not None:
            lines.append(f"  Avg Turn Latency  : {self.avg_turn_latency:.3f}s")
        lines.append(f"  Computed At       : {self.computed_at}")
        return "\n".join(lines)

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
            "score_stddev": self.score_stddev,
            "computed_at": self.computed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMetrics":
        """Reconstruct ConversationMetrics from a dict (e.g. loaded from JSON).

        Extra keys in *data* are silently ignored so that saved JSON files
        with additional fields round-trip correctly.

        Args:
            data: Mapping produced by :meth:`to_dict`.

        Returns:
            A new ``ConversationMetrics`` instance.

        Example::

            import json
            metrics = session.compute_metrics()
            restored = ConversationMetrics.from_dict(metrics.to_dict())
            assert restored.session_id == metrics.session_id
        """
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


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
        task_type: str = "qa",
    ) -> None:
        self.session_id = session_id
        self.task_type = task_type
        self._monitor = monitor
        self._turns: List[ConversationTurn] = []
        self.metrics: Optional[ConversationMetrics] = None

    @property
    def turns(self) -> "List[ConversationTurn]":
        """Shallow copy of accumulated conversation turns."""
        return list(self._turns)

    @turns.setter
    def turns(self, value: "List[ConversationTurn]") -> None:
        """Restore internal state."""
        self._turns = list(value)

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
            turn_index=len(self._turns),
            user=user,
            agent=agent,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self._turns.append(turn)
        return self

    def __repr__(self) -> str:
        return (
            f"ConversationSession(session_id={self.session_id!r}, "
            f"turns={len(self._turns)})"
        )

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
            InvalidOperationError: 턴이 하나도 없을 경우.
        """
        if not self._turns:
            raise InvalidOperationError("compute_metrics()를 호출하려면 최소 1턴이 필요합니다.")

        n = len(self._turns)

        context_retention = self._compute_context_retention()
        topic_coherence = self._compute_topic_coherence()
        progressive_depth = self._compute_progressive_depth()
        session_completion = self._compute_session_completion()
        avg_turn_latency = self._compute_avg_turn_latency()

        # overall_score: 구성 지표의 단순 평균
        component_scores = [context_retention, topic_coherence, progressive_depth, session_completion]
        _n = len(component_scores)
        overall_score = sum(component_scores) / _n
        # score_stddev: 구성 지표 간 분산을 나타내는 표준편차 (0에 가까울수록 균형 잡힌 성능)
        mean_sq_diff = sum((s - overall_score) ** 2 for s in component_scores) / _n
        score_stddev = math.sqrt(mean_sq_diff)

        self.metrics = ConversationMetrics(
            session_id=self.session_id,
            turn_count=n,
            context_retention=round(context_retention, 6),
            topic_coherence=round(topic_coherence, 6),
            progressive_depth=round(progressive_depth, 6),
            session_completion=round(session_completion, 6),
            avg_turn_latency=avg_turn_latency,
            overall_score=round(overall_score, 6),
            score_stddev=round(score_stddev, 6),
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
        return self.metrics

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화용 dict 반환."""
        return {
            "session_id": self.session_id,
            "turn_count": len(self._turns),
            "turns": [
                {
                    "turn_index": t.turn_index,
                    "user": t.user,
                    "agent": t.agent,
                    "timestamp": t.timestamp.isoformat(),
                    "metadata": t.metadata,
                }
                for t in self._turns
            ],
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
        }

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ConversationSession":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """세션 종료 시 자동으로 compute_metrics() 호출 및 monitor에 기록."""
        if exc_type is None and self._turns:
            try:
                self.compute_metrics()
            except Exception as e:
                logger.warning("compute_metrics() 실패 (세션=%s): %s", self.session_id, e)

        if self._monitor is not None and self.metrics is not None:
            try:
                _lock = getattr(self._monitor, "_lock", None)
                if _lock is not None:
                    with _lock:
                        self._monitor.conversation_sessions.append(self)
                else:
                    self._monitor.conversation_sessions.append(self)
            except AttributeError as e:
                logger.warning("monitor.conversation_sessions 접근 실패: %s", e)
        return False  # 예외 전파 (suppress하지 않음)

    # ------------------------------------------------------------------
    # Internal metric computations
    # ------------------------------------------------------------------

    def _compute_context_retention(self) -> float:
        """이전 응답의 top-N 단어가 현재 응답에 등장하는 비율 평균.

        1턴이면 비교 불가하므로 0.5(중립) 반환.
        이전 응답이 불용어만 포함해 top-N 단어 추출 불가한 턴은 평균에서 제외한다
        (측정 불가 ≠ 완벽한 유지).
        """
        n = len(self._turns)
        if n <= 1:
            return 0.5  # M4: 1-turn → neutral 0.5 (not 1.0) to align with progressive_depth=0.0

        scores: List[float] = []
        for i in range(1, n):
            prev_top = _top_tokens(self._turns[i - 1].agent, n=10)
            curr_tokens = set(_tokenize(self._turns[i].agent))
            if not prev_top:
                # 비교 기준이 없으므로 이 턴은 측정에서 제외
                continue
            overlap = len(prev_top & curr_tokens) / len(prev_top)
            scores.append(overlap)

        # 측정 가능한 턴이 하나도 없으면 0.5(중립)를 반환 — 1.0(완벽)으로 오해 방지
        return sum(scores) / len(scores) if scores else 0.5

    def _compute_topic_coherence(self) -> float:
        """인접 턴 간 질문+응답 단어 집합의 Jaccard 유사도 평균.

        1턴이면 1.0 반환.
        """
        n = len(self._turns)
        if n <= 1:
            return 1.0

        scores: List[float] = []
        for i in range(1, n):
            prev_set = set(_tokenize(self._turns[i - 1].user + " " + self._turns[i - 1].agent))
            curr_set = set(_tokenize(self._turns[i].user + " " + self._turns[i].agent))
            scores.append(_jaccard(prev_set, curr_set))

        return sum(scores) / len(scores) if scores else 1.0

    def _compute_progressive_depth(self) -> float:
        """사용자 질문이 직전 에이전트 응답의 핵심 단어를 포함하는 비율.

        첫 턴은 제외. 2턴 미만이면 0.0 반환.
        """
        n = len(self._turns)
        if n <= 1:
            return 0.0

        scores: List[float] = []
        for i in range(1, n):
            prev_top = _top_tokens(self._turns[i - 1].agent, n=10)
            user_tokens = set(_tokenize(self._turns[i].user))
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
        if not self._turns:
            return 0.0

        lengths = [len(t.agent) for t in self._turns]
        avg_len = sum(lengths) / len(lengths)
        if avg_len == 0:
            return 0.0

        last_len = lengths[-1]
        return min(1.0, last_len / avg_len)

    def _compute_avg_turn_latency(self) -> Optional[float]:
        """metadata의 'latency' 값 평균. 없으면 None."""
        latencies = [
            t.metadata["latency"]
            for t in self._turns
            if "latency" in t.metadata and isinstance(t.metadata["latency"], (int, float))
        ]
        if not latencies:
            return None
        return sum(latencies) / len(latencies)
