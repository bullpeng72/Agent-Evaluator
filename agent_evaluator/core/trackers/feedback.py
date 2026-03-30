"""
ImplicitFeedbackTracker — Phase 2-C 운영 피드백 수집

사용자 암묵적 행동 신호를 품질 지표로 변환한다.
긍정: copy, thumbs_up, share, save, follow_up_depth
부정: regenerate, thumbs_down, abandon, correction
"""
from __future__ import annotations
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from .base import BaseTracker
from ...exceptions import ValidationError

POSITIVE_TYPES = frozenset({"copy", "thumbs_up", "share", "save", "follow_up_depth"})
NEGATIVE_TYPES = frozenset({"regenerate", "thumbs_down", "abandon", "correction"})
ALL_FEEDBACK_TYPES = POSITIVE_TYPES | NEGATIVE_TYPES

class ImplicitFeedbackTracker(BaseTracker):
    """사용자 암묵적 행동 신호 기반 피드백 수집 트래커."""

    def __init__(self) -> None:
        self._feedbacks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def feedbacks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._feedbacks)

    def record(self, task_id: str, feedback_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """피드백 기록.

        Args:
            task_id: 피드백 대상 태스크 ID.
            feedback_type: 피드백 유형 (예: "regenerate", "thumbs_up").
            metadata: 추가 메타데이터 (선택).

        Raises:
            ValidationError: task_id가 비어 있거나 feedback_type이 미지원 유형인 경우.
        """
        if not task_id or not task_id.strip():
            raise ValidationError(f"task_id must be a non-empty string, got {task_id!r}")
        if feedback_type not in ALL_FEEDBACK_TYPES:
            raise ValidationError(
                f"feedback_type {feedback_type!r} is not supported. "
                f"Use one of: {sorted(ALL_FEEDBACK_TYPES)}"
            )
        entry = {
            "task_id": task_id,
            "feedback_type": feedback_type,
            "is_positive": feedback_type in POSITIVE_TYPES,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        with self._lock:
            self._feedbacks.append(entry)

    def get_stats(self) -> Dict[str, Any]:
        """피드백 통계 반환.

        Returns:
            Dict with keys: total, positive_count, negative_count,
            positive_rate, negative_rate, regenerate_rate, abandon_rate,
            type_distribution (각 유형별 카운트).
        """
        with self._lock:
            fb = list(self._feedbacks)

        total = len(fb)
        if total == 0:
            return {
                "total": 0,
                "positive_count": 0,
                "negative_count": 0,
                "positive_rate": 0.0,
                "negative_rate": 0.0,
                "regenerate_rate": 0.0,
                "abandon_rate": 0.0,
                "type_distribution": {},
            }

        positive = sum(1 for f in fb if f["is_positive"])
        negative = total - positive
        type_dist: Dict[str, int] = {}
        for f in fb:
            t = f["feedback_type"]
            type_dist[t] = type_dist.get(t, 0) + 1

        return {
            "total": total,
            "positive_count": positive,
            "negative_count": negative,
            "positive_rate": round(positive / total * 100, 1),
            "negative_rate": round(negative / total * 100, 1),
            "regenerate_rate": round(type_dist.get("regenerate", 0) / total * 100, 1),
            "abandon_rate": round(type_dist.get("abandon", 0) / total * 100, 1),
            "type_distribution": type_dist,
        }

    def get_task_feedbacks(self, task_id: str) -> List[Dict[str, Any]]:
        """특정 태스크의 피드백 목록 반환."""
        with self._lock:
            return [f for f in self._feedbacks if f["task_id"] == task_id]

    def reset(self) -> None:
        with self._lock:
            self._feedbacks.clear()
