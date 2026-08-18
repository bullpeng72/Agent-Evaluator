"""
agent_evaluator.core.trackers.layer2
======================================
Layer 2 — Agentic Metrics (native, no external deps):
  ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
  AgentCoordinationTracker, WorkflowExecutionTracker
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Sequence, Union

import pandas as pd

from ...exceptions import ValidationError
from .base import BaseTracker

logger = logging.getLogger(__name__)


def _safe_mean(series: pd.Series) -> float:
    """Return the mean of a pandas Series, or 0.0 if empty / all-NaN."""
    if len(series) == 0:
        return 0.0
    val = series.mean()
    return float(val) if not pd.isna(val) else 0.0


# ---------------------------------------------------------------------------
# AgentCoordinationTracker 스코어링 상수
# ---------------------------------------------------------------------------

# 협업 점수 가중치 (success 50% + diversity 30% + balance 20% = 1.0)
_COORD_WEIGHT_SUCCESS: float = 0.5
_COORD_WEIGHT_DIVERSITY: float = 0.3
_COORD_WEIGHT_BALANCE: float = 0.2

# 다양성 정규화 기준: 5개 이상 에이전트를 "이상적" 다양성으로 정의
_COORD_IDEAL_AGENT_COUNT: int = 5
# 균형 정규화 기준: 3가지 인터랙션 유형(delegation/communication/collaboration)이 이상적
_COORD_IDEAL_INTERACTION_TYPES: int = 3
# 점수 척도: 협업 점수는 0-10 범위
_COORD_SCORE_SCALE: float = 10.0

# 패턴 탐지 임계값
# Hub: 단일 에이전트가 전체 인터랙션의 50% 이상 처리
_COORD_HUB_THRESHOLD: float = 0.5
# Chain: 에이전트의 70% 이상이 송수신 ≤2 조건 충족
_COORD_CHAIN_RATIO: float = 0.7
# Mesh: 가능한 연결 쌍의 50% 이상이 실제로 연결됨
_COORD_MESH_DENSITY_THRESHOLD: float = 0.5

# 에이전트 역할 분류 경계값
# 전체 인터랙션 중 70% 이상 송신 → producer
_COORD_PRODUCER_RATIO: float = 0.7
# 전체 인터랙션 중 30% 이하 송신 → consumer (그 외는 coordinator)
_COORD_CONSUMER_RATIO: float = 0.3

# track_interaction()에서 허용되는 인터랙션 유형 집합
_COORD_ALLOWED_INTERACTION_TYPES: frozenset = frozenset({"delegation", "communication", "collaboration"})

# 흔히 사용되는 별칭 → canonical 유형 매핑 (경고 없이 자동 정규화)
_COORD_INTERACTION_TYPE_ALIASES: dict = {
    # 일반 별칭
    "task_delegation": "delegation",
    "result_sharing":  "communication",
    "feedback":        "communication",
    "coordination":    "collaboration",
    "handoff":         "delegation",
    "broadcast":       "communication",
    # 프레임워크 어댑터 생성 타입 (CrewAI / LangGraph / AutoGen)
    "task_completion": "communication",   # CrewAI: 태스크 완료 후 coordinator에 통보
    "output_format":   "communication",   # CrewAI: 출력 포맷 공유
    "pydantic_output": "communication",   # CrewAI: Pydantic 모델 출력 전달
    "result":          "communication",   # LangGraph: 노드 결과 반환
    "tool_result":     "communication",   # LangGraph: 도구 결과 반환
    "ai_message":      "communication",   # LangGraph: AI 메시지 전달
    "message":         "communication",   # AutoGen: 에이전트 간 메시지
    "tool_call":       "delegation",      # 범용: 도구 호출 위임
    "tool_return":     "communication",   # 범용: 도구 반환값 전달
}


# ===========================================================================
# 7. Tool Call Efficiency Analyzer (Agentic AI - Layer 2)
# ============================================================================

class ToolCallAnalyzer(BaseTracker):
    """
    Analyze tool call efficiency for Agentic AI systems

    Layer 2 Metric: Tracks efficiency, redundancy, and failure rates of tool calls.
    This is specific to agent systems that use tools/functions.
    """

    def __init__(self):
        self._executions: list[dict[str, Any]] = []
        self._all_tool_names: set = set()  # 전체 누적 고유 도구명 집합
        self._lock = threading.Lock()  # M4: thread-safe append

    @property
    def executions(self) -> list[dict[str, Any]]:
        """Shallow copy of accumulated execution records."""
        with self._lock:
            return list(self._executions)

    @executions.setter
    def executions(self, value: list[dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        with self._lock:
            self._executions = list(value)

    def __repr__(self) -> str:
        with self._lock:
            return f"ToolCallAnalyzer(executions={len(self._executions)})"

    def reset(self) -> None:
        """Clear all execution records."""
        with self._lock:
            self._executions.clear()
            self._all_tool_names.clear()

    def analyze_execution(
        self,
        task_id: str,
        tool_calls: Sequence[Union[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Analyze tool call efficiency for a single task.

        Args:
            task_id: Unique task identifier.
            tool_calls: List of tool call records. Each element can be:

                - ``str`` — simple tool name (e.g., ``"web_search"``).
                - ``dict`` — structured call record with optional keys:

                  * ``tool_name`` / ``tool`` / ``name`` (str): Tool identifier
                    (checked in this order; defaults to ``"unknown"``).
                  * ``duration`` (float, opt): Execution time in seconds.
                    Values ``<= 0`` are excluded from ``avg_call_duration``.
                  * ``success`` (bool, opt): Whether the call succeeded.
                    Defaults to ``True`` when absent.
                  * ``parameters`` (dict, opt): Tool arguments used for
                    redundancy detection (same tool + same parameters = redundant).

        Returns:
            Dict with keys: task_id, total_calls, unique_tools,
            redundant_calls, failed_calls (int), avg_call_duration (float),
            efficiency_score (float 0–100, or None when no calls were made).

            ``efficiency_score`` is ``None`` — not 100 — when *tool_calls* is
            empty, because "no tool calls" is an unmeasured state, not a
            perfect result.  Callers and aggregators must handle ``None``.
        """
        if not tool_calls:
            return {
                "task_id": task_id,
                "total_calls": 0,
                "unique_tools": 0,
                "redundant_calls": 0,
                "failed_calls": 0,
                "avg_call_duration": 0.0,
                "efficiency_score": None,  # unmeasured — not 100%
                "note": "No tool calls recorded for this task",
            }

        # Extract tool names (support both "tool" and "tool_name" keys, as well as plain strings)
        tool_names = []
        for call in tool_calls:
            if isinstance(call, str):
                # Handle simple string tool names (for compatibility)
                tool_name = call
            elif isinstance(call, dict):
                tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown")
            else:
                tool_name = "unknown"
            tool_names.append(tool_name)

        # DQ-126: duration=0.0은 측정 불가 값이므로 평균에서 제외
        # "duration" 키 존재 + 값이 0보다 클 때만 포함 (0은 콜백 미작동으로 수집 안 된 케이스)
        durations = [
            call["duration"] for call in tool_calls
            if isinstance(call, dict) and call.get("duration", 0) > 0
        ]

        metrics = {
            "task_id": task_id,
            "total_calls": len(tool_calls),
            "unique_tools": len(set(tool_names)),
            "redundant_calls": self._count_redundant_calls(tool_calls),
            "failed_calls": sum(1 for call in tool_calls if isinstance(call, dict) and not call.get("success", True)),
            "avg_call_duration": round(statistics.mean(durations), 2) if durations else 0.0
        }

        # Calculate efficiency score (only reachable when total_calls > 0;
        # empty tool_calls returns early above with efficiency_score=None).
        # Cap at 1.0: a call can be both redundant and failed, so naive sum can exceed total_calls
        waste_rate = min(1.0, (metrics["redundant_calls"] + metrics["failed_calls"]) / metrics["total_calls"])
        metrics["efficiency_score"] = round(max(0, 100 - (waste_rate * 100)), 2)

        with self._lock:
            self._executions.append(metrics)
            self._all_tool_names.update(tool_names)
        return metrics

    def _count_redundant_calls(self, tool_calls: Sequence[Union[str, dict[str, Any]]]) -> int:
        """Count redundant tool calls (supports both dict and string formats)"""
        seen = set()
        redundant = 0

        for call in tool_calls:
            if isinstance(call, str):
                # For string tool calls, just check tool name
                key = (call, "{}")
            elif isinstance(call, dict):
                # Support multiple key names for tool
                tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown")
                key = (tool_name, json.dumps(call.get("parameters", {}), sort_keys=True))
            else:
                continue

            if key in seen:
                redundant += 1
            seen.add(key)

        return redundant

    def get_efficiency_stats(self) -> dict[str, Any]:
        """Get tool call efficiency statistics"""
        if not self._executions:
            return {
                "total_calls": 0, "unique_tools": 0, "success_rate": 0.0,
                "avg_duration": 0.0, "avg_calls_per_task": 0.0,
                "avg_efficiency_score": 0.0,  # 0 = no data, not 100 (unmeasured ≠ perfect)
                "total_redundant_calls": 0,
                "total_failed_calls": 0, "redundancy_rate": 0.0, "failure_rate": 0.0,
            }

        df = pd.DataFrame(self._executions)

        total_calls = int(df["total_calls"].sum())

        return {
            "total_calls": total_calls,  # Added for dashboard
            "unique_tools": len(self._all_tool_names),
            "success_rate": round((1 - df["failed_calls"].sum() / total_calls) * 100, 2) if total_calls > 0 else 0,  # Added
            "avg_duration": round(df["avg_call_duration"].dropna().mean(), 3)
            if "avg_call_duration" in df.columns and df["avg_call_duration"].notna().any() else 0.0,
            "avg_calls_per_task": round(df["total_calls"].mean(), 2),
            "avg_efficiency_score": round(df["efficiency_score"].dropna().mean(), 2)
            if df["efficiency_score"].notna().any() else 0.0,
            "total_redundant_calls": int(df["redundant_calls"].sum()),
            "total_failed_calls": int(df["failed_calls"].sum()),
            "redundancy_rate": round(
                (df["redundant_calls"].sum() / total_calls) * 100, 2
            ) if total_calls > 0 else 0,
            "failure_rate": round(
                (df["failed_calls"].sum() / total_calls) * 100, 2
            ) if total_calls > 0 else 0
        }

    def get_tool_usage_patterns(self) -> dict[str, Any]:
        """Get detailed tool usage patterns and statistics"""
        if not self._executions:
            return {
                "total_tasks": 0,
                "tool_frequency": {},
                "pattern_analysis": {}
            }

        # Single-pass: collect all per-task values to avoid O(N) × num_metrics overhead
        tool_call_counts = []
        efficiency_scores = []
        redundant_counts = []
        failed_counts = []
        tasks_with_redundancy = 0
        tasks_with_failures = 0

        ud_1_2 = ud_3_5 = ud_6_10 = ud_11p = 0
        ed_exc = ed_good = ed_fair = ed_poor = 0

        for exec_data in self._executions:
            tc = exec_data.get("total_calls", 0)
            tool_call_counts.append(tc)
            rc = exec_data.get("redundant_calls", 0)
            fc = exec_data.get("failed_calls", 0)
            redundant_counts.append(rc)
            failed_counts.append(fc)
            if rc > 0:
                tasks_with_redundancy += 1
            if fc > 0:
                tasks_with_failures += 1

            # efficiency_score is None when no tool calls were made — exclude from average
            es = exec_data.get("efficiency_score")
            if es is not None:
                efficiency_scores.append(es)
                if es >= 90:
                    ed_exc += 1
                elif es >= 75:
                    ed_good += 1
                elif es >= 50:
                    ed_fair += 1
                else:
                    ed_poor += 1

            # usage distribution buckets
            if 1 <= tc <= 2:
                ud_1_2 += 1
            elif 3 <= tc <= 5:
                ud_3_5 += 1
            elif 6 <= tc <= 10:
                ud_6_10 += 1
            elif tc > 10:
                ud_11p += 1

        total_redundant = sum(redundant_counts)
        total_failed = sum(failed_counts)
        n = len(self._executions)

        pattern_analysis = {
            "avg_tools_per_task": round(statistics.mean(tool_call_counts), 2) if tool_call_counts else 0,
            "median_tools_per_task": round(statistics.median(tool_call_counts), 2) if tool_call_counts else 0,
            "max_tools_in_single_task": max(tool_call_counts) if tool_call_counts else 0,
            "min_tools_in_single_task": min(tool_call_counts) if tool_call_counts else 0,
            "avg_efficiency": round(statistics.mean(efficiency_scores), 2) if efficiency_scores else 0,
            "tasks_with_redundancy": tasks_with_redundancy,
            "tasks_with_failures": tasks_with_failures,
        }

        return {
            "total_tasks": n,
            "total_tool_calls": sum(tool_call_counts),
            "pattern_analysis": pattern_analysis,
            "usage_distribution": {
                "1-2_calls": ud_1_2,
                "3-5_calls": ud_3_5,
                "6-10_calls": ud_6_10,
                "11+_calls": ud_11p,
            },
            "efficiency_distribution": {
                "excellent_90-100": ed_exc,
                "good_75-89": ed_good,
                "fair_50-74": ed_fair,
                "poor_0-49": ed_poor,
            },
            "redundancy_impact": {
                "total_redundant": total_redundant,
                "avg_redundant_per_task": round(total_redundant / n, 2) if n > 0 else 0,
            },
            "failure_impact": {
                "total_failed": total_failed,
                "avg_failed_per_task": round(total_failed / n, 2) if n > 0 else 0,
            },
        }


# ============================================================================
# 8. Retry/Correction Tracker
# ============================================================================

class RetryCorrectionTracker(BaseTracker):
    """Track retry and correction attempts"""

    def __init__(self):
        self._attempts: list[dict[str, Any]] = []
        self._task_ids: set[str] = set()
        self._lock = threading.Lock()  # M4: thread-safe append

    @property
    def attempts(self) -> list[dict[str, Any]]:
        """Shallow copy of accumulated retry attempt records."""
        with self._lock:
            return list(self._attempts)

    @attempts.setter
    def attempts(self, value: list[dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        with self._lock:
            self._attempts = list(value)
            self._task_ids = {tid for a in value if (tid := a.get("task_id")) is not None}

    def __repr__(self) -> str:
        with self._lock:
            return f"RetryCorrectionTracker(attempts={len(self._attempts)})"

    def reset(self) -> None:
        """Clear all retry attempt records."""
        with self._lock:
            self._attempts.clear()
            self._task_ids.clear()

    def track_attempts(
        self,
        task_id: str,
        attempts_log: list[dict[str, Any]],
        task_type: str = "unknown",
    ) -> None:
        """태스크의 재시도 이력을 기록한다.

        Args:
            task_id: 태스크 고유 ID.
            attempts_log: 각 시도를 나타내는 dict 목록. 각 dict는 다음 키를 포함할 수 있다:
                - success (bool): 해당 시도 성공 여부
                - retry_reason (str, 선택): 재시도 사유
                - duration (float, 선택): 해당 시도 소요 시간(초)
            task_type: 태스크 유형 (기본값: "unknown"). 유형별 집계에 사용.

        Note:
            빈 attempts_log는 무시된다.

        Example:
            >>> tracker.track_attempts(
            ...     task_id="t1",
            ...     attempts_log=[
            ...         {"success": False, "retry_reason": "timeout", "duration": 1.2},
            ...         {"success": True, "duration": 0.8},
            ...     ],
            ... )
        """
        # DQ-135: 빈 attempts_log는 IndexError 발생 — 단일 성공 시도로 기록하고 조기 반환
        if not attempts_log:
            return
        analysis = {
            "task_id": task_id,
            "task_type": task_type,
            "total_attempts": len(attempts_log),
            "first_attempt_success": attempts_log[0].get("success", False),
            "final_success": attempts_log[-1].get("success", False),
            "retry_reasons": [a.get("retry_reason", "unknown") for a in attempts_log if not a.get("success")],
            "total_retry_time": sum(a.get("duration", 0) for a in attempts_log[1:])
        }

        with self._lock:
            self._attempts.append(analysis)
            self._task_ids.add(task_id)

    def get_retry_metrics(self) -> dict[str, Any]:
        """Get retry statistics"""
        if not self._attempts:
            return {
                "total_tasks_with_retries": 0,
                "retry_rate": 0.0,
                "first_attempt_success_rate": 0.0,
                "eventual_success_rate": 0.0,
                "retry_success_count": 0,
                "correction_success_rate": 0.0,
                "avg_attempts_per_task": 0.0,
                "total_retry_time": 0.0,
                "avg_retry_time": 0.0,
                "overall_retry_rate": 0.0,
                "avg_retries_per_task": 0.0,
            }

        df = pd.DataFrame(self._attempts)

        # Calculate metrics
        tasks_with_retries = (df["total_attempts"] > 1).sum()
        retry_rate = (df["total_attempts"] > 1).mean() * 100
        first_attempt_success_rate = df["first_attempt_success"].mean() * 100
        eventual_success_rate = df["final_success"].mean() * 100

        # Retry success count: tasks that failed first but eventually succeeded
        retry_success_count = ((~df["first_attempt_success"]) & df["final_success"]).sum()

        # Correction success rate: of tasks that needed retries, how many succeeded
        tasks_needing_retry = (~df["first_attempt_success"]).sum()
        correction_success_rate = (retry_success_count / tasks_needing_retry * 100) if tasks_needing_retry > 0 else 0

        return {
            # Dashboard keys
            "total_tasks_with_retries": int(tasks_with_retries),
            "retry_rate": round(retry_rate, 2),
            "first_attempt_success_rate": round(first_attempt_success_rate, 2),
            "eventual_success_rate": round(eventual_success_rate, 2),
            "retry_success_count": int(retry_success_count),
            "correction_success_rate": round(correction_success_rate, 2),
            "avg_attempts_per_task": round(df["total_attempts"].mean(), 2),
            "total_retry_time": round(df["total_retry_time"].sum(), 2),
            "avg_retry_time": (
                round(
                    _safe_mean(df[df["total_attempts"] > 1]["total_retry_time"]), 2
                ) if tasks_with_retries > 0 else 0.0
            ),
            # overall_retry_rate: 재시도 횟수 / 총 시도 횟수 × 100
            # Guard: track_attempts() always stores total_attempts>=1, but
            # defend against any external direct-list mutation here.
            "overall_retry_rate": round(
                (df["total_attempts"].sum() - len(df)) / df["total_attempts"].sum() * 100, 2
            ) if df["total_attempts"].sum() > 0 else 0.0,
            "avg_retries_per_task": round(df["total_attempts"].mean() - 1, 2)
        }

    def analyze_failure_patterns(self) -> dict[str, Any]:
        """Analyze common failure patterns"""
        all_reasons = []
        for attempt in self._attempts:
            all_reasons.extend(attempt["retry_reasons"])

        if not all_reasons:
            return {"patterns": {}}

        reason_counts = defaultdict(int)
        for reason in all_reasons:
            reason_counts[reason] += 1

        return {
            "patterns": dict(sorted(
                reason_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )),
            "most_common": max(reason_counts, key=lambda r: reason_counts[r]) if reason_counts else None
        }


# ============================================================================
# 9. Tool Selection Tracker (Agentic AI)
# ============================================================================

# 도구명 정규화 별칭 맵 — 프레임워크별 명명 차이로 인한 F1 왜곡 방지
# 형식: canonical_name → [alias_list]
_TOOL_ALIASES: dict[str, list[str]] = {
    "web_search": ["search_web", "internet_search", "google_search", "search", "web_search_tool"],
    "python_repl": ["python_executor", "code_runner", "execute_python", "python_tool", "repl"],
    "calculator": ["compute", "math_tool", "calculate", "arithmetic", "math"],
    "file_read": ["read_file", "open_file", "load_file", "file_loader"],
    "file_write": ["write_file", "save_file", "create_file", "file_writer"],
    "sql_query": ["run_sql", "execute_sql", "db_query", "query_database"],
    "http_request": ["call_api", "api_request", "fetch_url", "requests"],
    "retriever": ["retrieve", "vector_search", "semantic_search", "rag_retrieve", "similarity_search"],
}

# 역방향 맵: alias → canonical
_TOOL_ALIAS_REVERSE: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _TOOL_ALIASES.items()
    for alias in aliases
}


def _normalize_tool_name(name: str) -> str:
    """도구 이름을 정규화합니다. 알려진 별칭은 canonical 이름으로 변환합니다."""
    n = (name or "").lower().strip()
    return _TOOL_ALIAS_REVERSE.get(n, n)


class ToolSelectionTracker(BaseTracker):
    """Track tool selection accuracy for Agentic AI"""

    def __init__(self):
        self._selections: list[dict[str, Any]] = []
        self._task_ids: set[str] = set()
        self._lock = threading.Lock()  # M4: thread-safe append

    @property
    def selections(self) -> list[dict[str, Any]]:
        """Shallow copy of accumulated tool selection records."""
        with self._lock:
            return list(self._selections)

    @selections.setter
    def selections(self, value: list[dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        with self._lock:
            self._selections = list(value)
            self._task_ids = {tid for s in value if (tid := s.get("task_id")) is not None}

    def __repr__(self) -> str:
        with self._lock:
            return f"ToolSelectionTracker(selections={len(self._selections)})"

    def reset(self) -> None:
        """Clear all selection records."""
        with self._lock:
            self._selections.clear()
            self._task_ids.clear()

    def evaluate_selection(
        self,
        task_id: str,
        expected_tools: list[str],
        actual_tools: list[str]
    ) -> dict[str, Any]:
        """에이전트가 올바른 도구를 선택했는지 평가한다 (Precision/Recall/F1 기반).

        도구 이름은 시맨틱 별칭 정규화(`_normalize_tool_name`)를 거쳐 비교하므로
        ``web_search``와 ``search_web`` 같은 동의어는 동일하게 처리된다.

        Args:
            task_id: 태스크 고유 ID.
            expected_tools: 기대되는 도구 이름 목록.
            actual_tools: 에이전트가 실제로 사용한 도구 이름 목록.

        Returns:
            Dict containing:
                - task_id (str)
                - expected_tools, actual_tools (List[str])
                - true_positives, false_positives, false_negatives (int)
                - precision, recall, f1_score (float, 0-100 scale)
                - accuracy (float): f1_score와 동일 (전체 정확도 대표값)

        Example:
            >>> result = tracker.evaluate_selection(
            ...     task_id="t1",
            ...     expected_tools=["search", "calculator"],
            ...     actual_tools=["web_search", "calculator"],
            ... )
            >>> result["f1_score"]  # search ↔ web_search 시맨틱 매칭으로 100.0 반환
            100.0
        """
        if not expected_tools:
            # No ground truth to compare against — return None for numeric scores
            # so callers can distinguish "evaluation skipped" from "actual score=0".
            # Aggregation callers that use dropna() will exclude None automatically.
            return {
                "task_id": task_id,
                "expected_tools": expected_tools,
                "actual_tools": actual_tools,
                "true_positives": 0,
                "false_positives": len(actual_tools),
                "false_negatives": 0,
                "precision": None,
                "recall": None,
                "f1_score": None,
                "accuracy": None,
                "note": "No expected tools defined — evaluation skipped",
            }

        expected_set = set(_normalize_tool_name(t) for t in expected_tools)
        actual_set = set(_normalize_tool_name(t) for t in actual_tools)

        # Calculate precision, recall, F1
        true_positives = len(expected_set & actual_set)
        false_positives = len(actual_set - expected_set)
        false_negatives = len(expected_set - actual_set)

        precision = true_positives / len(actual_set) if actual_set else 0
        recall = true_positives / len(expected_set) if expected_set else 0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        result = {
            "task_id": task_id,
            "expected_tools": expected_tools,
            "actual_tools": actual_tools,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": round(precision * 100, 2),
            "recall": round(recall * 100, 2),
            "f1_score": round(f1_score * 100, 2),
            # "accuracy" is an alias for f1_score kept for backward compatibility.
            # Callers needing the true F1 score should use the "f1_score" key.
            "accuracy": round(f1_score * 100, 2)
        }

        with self._lock:
            self._selections.append(result)
            self._task_ids.add(task_id)
        return result

    def get_accuracy_stats(self) -> dict[str, Any]:
        """Get tool selection accuracy statistics"""
        if not self._selections:
            return {
                "total_evaluations": 0,
                "avg_accuracy": 0.0,
                "avg_precision": 0.0,
                "avg_recall": 0.0,
                "avg_f1_score": 0.0,
                "total_true_positives": 0,
                "total_false_positives": 0,
                "total_false_negatives": 0,
            }

        df = pd.DataFrame(self._selections)

        # H1/M1: evaluate_selection() may return None for skipped entries (no expected_tools).
        # Use dropna() before mean() so skipped evaluations don't distort averages.
        def _safe_mean(col: str) -> float:
            valid = df[col].dropna()
            return round(valid.mean(), 2) if not valid.empty else 0.0

        return {
            "total_evaluations": len(self._selections),
            "avg_accuracy": _safe_mean("accuracy"),
            "avg_precision": _safe_mean("precision"),
            "avg_recall": _safe_mean("recall"),
            "avg_f1_score": _safe_mean("f1_score"),
            "total_true_positives": int(df["true_positives"].sum()),
            "total_false_positives": int(df["false_positives"].sum()),
            "total_false_negatives": int(df["false_negatives"].sum())
        }

    def get_f1_by_tool(self) -> dict[str, dict[str, float]]:
        """도구별 F1/Precision/Recall 세부 분류를 반환한다 (C3).

        각 expected_tool에 대해 실제 선택 여부를 기준으로 per-tool 지표를 계산한다.

        Returns:
            Dict mapping tool_name → {precision, recall, f1, tp, fp, fn, appearances}.

        Example::

            stats = tracker.get_f1_by_tool()
            # {"search": {"f1": 85.0, "precision": 90.0, "recall": 80.0, ...},
            #  "calculator": {"f1": 100.0, "appearances": 3, ...}}
        """
        if not self._selections:
            return {}

        tool_stats: dict[str, dict[str, int]] = {}
        for sel in self._selections:
            expected = set(_normalize_tool_name(t) for t in sel.get("expected_tools", []))
            actual = set(_normalize_tool_name(t) for t in sel.get("actual_tools", []))
            for tool in expected | actual:
                if tool not in tool_stats:
                    tool_stats[tool] = {"tp": 0, "fp": 0, "fn": 0, "appearances": 0}
                if tool in expected:
                    tool_stats[tool]["appearances"] += 1
                if tool in expected and tool in actual:
                    tool_stats[tool]["tp"] += 1
                elif tool in actual and tool not in expected:
                    tool_stats[tool]["fp"] += 1
                elif tool in expected and tool not in actual:
                    tool_stats[tool]["fn"] += 1

        result: dict[str, dict[str, float]] = {}
        for tool, s in tool_stats.items():
            tp, fp, fn = s["tp"], s["fp"], s["fn"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            result[tool] = {
                "precision": round(precision * 100, 2),
                "recall": round(recall * 100, 2),
                "f1": round(f1 * 100, 2),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "appearances": s["appearances"],
            }
        return result


# ============================================================================
# 10. Agent Coordination Tracker (CrewAI)
# ============================================================================

class AgentCoordinationTracker(BaseTracker):
    """Track multi-agent coordination quality for CrewAI.

    Args:
        hub_threshold: Fraction of total interactions handled by a single agent
            to classify the topology as ``"hub"`` pattern. Default: data-driven
            (mean + 1·std of per-agent interaction shares). Pass an explicit float
            (0.0–1.0) to override — useful for known fixed architectures.
        chain_ratio: Minimum fraction of agents that each send/receive ≤ 2
            messages to classify the topology as ``"chain"`` pattern.
        mesh_density_threshold: Minimum undirected connection density to classify
            the topology as ``"mesh"`` pattern.
        ideal_agent_count: Reference agent count for the diversity score (agents /
            ideal_agent_count, capped at 1.0). Defaults to ``_COORD_IDEAL_AGENT_COUNT``.
    """

    def __init__(
        self,
        hub_threshold: float | None = None,
        chain_ratio: float = _COORD_CHAIN_RATIO,
        mesh_density_threshold: float = _COORD_MESH_DENSITY_THRESHOLD,
        ideal_agent_count: int = _COORD_IDEAL_AGENT_COUNT,
    ):
        self._interactions: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # M4: thread-safe append
        # None → compute dynamically from interaction data (mean + 1·std)
        self._hub_threshold_override: float | None = hub_threshold
        self._chain_ratio = chain_ratio
        self._mesh_density_threshold = mesh_density_threshold
        self._ideal_agent_count = ideal_agent_count

    @property
    def interactions(self) -> list[dict[str, Any]]:
        """Shallow copy of accumulated agent interaction records."""
        with self._lock:
            return list(self._interactions)

    @interactions.setter
    def interactions(self, value: list[dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        with self._lock:
            self._interactions = list(value)

    def __repr__(self) -> str:
        with self._lock:
            return f"AgentCoordinationTracker(interactions={len(self._interactions)})"

    def reset(self) -> None:
        """Clear all interaction records."""
        with self._lock:
            self._interactions.clear()

    def track_interaction(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        interaction_type: str,  # delegation, communication, collaboration
        success: bool,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """에이전트 간 인터랙션(위임·통신·협업)을 기록한다.

        Args:
            task_id: 인터랙션이 발생한 태스크 ID.
            from_agent: 인터랙션을 시작한 에이전트 이름. 빈 문자열은 ``"unknown_agent"``로 정규화.
            to_agent: 인터랙션을 받은 에이전트 이름. 빈 문자열은 ``"unknown_agent"``로 정규화.
            interaction_type: 인터랙션 종류. 허용값: ``"delegation"``, ``"communication"``,
                ``"collaboration"``. 허용값 외 입력은 ``"delegation"``으로 정규화.
            success: 인터랙션 성공 여부.
            context: 추가 메타데이터 dict (선택).

        Returns:
            기록된 인터랙션 dict (task_id, from_agent, to_agent, interaction_type, success,
            timestamp, context).

        Example:
            >>> tracker.track_interaction(
            ...     task_id="t1",
            ...     from_agent="orchestrator",
            ...     to_agent="retriever",
            ...     interaction_type="delegation",
            ...     success=True,
            ... )
        """
        # DQ-166: 빈 에이전트 이름은 집계를 오염시킴 — placeholder로 대체
        from_agent = from_agent or "unknown_agent"
        to_agent = to_agent or "unknown_agent"
        # DQ-167: allowed interaction_type 외 값은 별칭 매핑 후 canonical 유형으로 정규화
        if interaction_type not in _COORD_ALLOWED_INTERACTION_TYPES:
            canonical = _COORD_INTERACTION_TYPE_ALIASES.get(interaction_type)
            if canonical is not None:
                interaction_type = canonical
            else:
                logger.warning(
                    "track_interaction() received unknown interaction_type=%r for task %r. "
                    "Expected one of %s. Normalising to 'delegation'. "
                    "This may indicate a bug in the caller.",
                    interaction_type, task_id, sorted(_COORD_ALLOWED_INTERACTION_TYPES),
                )
                interaction_type = "delegation"
        interaction = {
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "interaction_type": interaction_type,
            "success": success,
            "timestamp": datetime.now(),
            "context": context or {}
        }

        with self._lock:
            self._interactions.append(interaction)
        return interaction

    def calculate_coordination_score(self, task_id: str | None = None) -> dict[str, Any]:
        """Calculate agent coordination quality score"""
        interactions = self._interactions
        if task_id:
            interactions = [i for i in interactions if i["task_id"] == task_id]

        if not interactions:
            return {
                "overall_score": 0.0,
                "success_rate": 0.0,
                "total_interactions": 0,
                "unique_agents": 0,
                "interaction_types": {},
            }

        # Success rate — len(interactions) > 0 is guaranteed by the early-return guard above
        n_interactions = len(interactions)
        success_rate = sum(1 for i in interactions if i["success"]) / n_interactions * 100

        # Interaction diversity (more agents = better collaboration)
        agents = set()
        for i in interactions:
            agents.add(i["from_agent"])
            agents.add(i["to_agent"])

        # Interaction type balance
        type_counts = defaultdict(int)
        for i in interactions:
            type_counts[i["interaction_type"]] += 1

        # Score calculation (0-10 scale)
        # success_rate(0-100) → /10 → (0-10), then weight by _COORD_WEIGHT_SUCCESS
        diversity_score = min(len(agents) / self._ideal_agent_count, 1.0) * _COORD_SCORE_SCALE
        balance_score = min(len(type_counts) / _COORD_IDEAL_INTERACTION_TYPES, 1.0) * _COORD_SCORE_SCALE

        coordination_score = (
            success_rate * _COORD_WEIGHT_SUCCESS / _COORD_SCORE_SCALE +
            diversity_score * _COORD_WEIGHT_DIVERSITY +
            balance_score * _COORD_WEIGHT_BALANCE
        )

        return {
            "overall_score": round(coordination_score, 2),
            "success_rate": round(success_rate, 2),
            "total_interactions": len(interactions),
            "unique_agents": len(agents),
            "interaction_types": dict(type_counts)
        }

    def get_delegation_success_rate(self) -> float:
        """Calculate task delegation success rate"""
        delegations = [i for i in self._interactions if i["interaction_type"] == "delegation"]
        if not delegations:
            return 0.0
        return sum(1 for d in delegations if d.get("success", False)) / len(delegations) * 100

    def get_interaction_patterns(self) -> dict[str, Any]:
        """Analyze agent interaction patterns (Hub, Chain, Mesh)"""
        if not self._interactions:
            return {
                "total_interactions": 0,
                "pattern_type": "none",
                "pattern_analysis": {}
            }

        # Count interactions per agent
        agent_send_counts = defaultdict(int)  # How many messages each agent sends
        agent_receive_counts = defaultdict(int)  # How many messages each agent receives
        agent_pairs = defaultdict(int)  # Count interactions between specific pairs

        for interaction in self._interactions:
            from_agent = interaction["from_agent"]
            to_agent = interaction["to_agent"]
            agent_send_counts[from_agent] += 1
            agent_receive_counts[to_agent] += 1
            agent_pairs[f"{from_agent}->{to_agent}"] += 1

        all_agents = set(agent_send_counts) | set(agent_receive_counts)
        total_agents = len(all_agents)

        # Detect pattern type
        pattern_type = "unknown"
        pattern_confidence = 0.0

        # Hub Pattern: One agent has significantly more interactions than others
        if agent_send_counts or agent_receive_counts:
            max_sends = max(agent_send_counts.values()) if agent_send_counts else 0
            max_receives = max(agent_receive_counts.values()) if agent_receive_counts else 0
            total_interactions = len(self._interactions)

            # Dynamic hub threshold: if not overridden, use mean + 1·std of per-agent
            # interaction shares so the threshold adapts to actual data distribution.
            if self._hub_threshold_override is not None:
                _hub_frac = self._hub_threshold_override
            elif total_agents >= 3:
                shares = [
                    (agent_send_counts.get(a, 0) + agent_receive_counts.get(a, 0))
                    / (total_interactions * 2)
                    for a in all_agents
                ]
                mean_share = sum(shares) / len(shares)
                variance = sum((s - mean_share) ** 2 for s in shares) / len(shares)
                std_share = variance ** 0.5
                # A hub agent must exceed mean + 1·std — adapts to team size
                _hub_frac = min(0.9, mean_share + std_share)
            else:
                _hub_frac = _COORD_HUB_THRESHOLD

            hub_threshold = total_interactions * _hub_frac
            if max_sends >= hub_threshold or max_receives >= hub_threshold:
                pattern_type = "hub"
                pattern_confidence = min((max(max_sends, max_receives) / total_interactions) * 100, 100)

            # Chain Pattern: Sequential passing (each agent mostly talks to 1-2 others)
            elif total_agents >= 3:
                chain_like = sum(1 for agent in all_agents
                               if agent_send_counts.get(agent, 0) <= 2
                               and agent_receive_counts.get(agent, 0) <= 2)

                if chain_like / total_agents >= self._chain_ratio:
                    pattern_type = "chain"
                    pattern_confidence = (chain_like / total_agents) * 100

            # Mesh Pattern: Many-to-many connections
            # F-H: 독립 if → Hub/Chain이 감지된 경우에도 Mesh가 항상 덮어쓰는 버그 수정.
            # Hub → Chain → Mesh 우선순위 순서로 fallback되어야 하므로 elif로 변경.
            # connection_density 계산은 패턴 확인에 관계없이 분석 목적으로 유지.
            unique_pairs = len({
                tuple(sorted(k.split("->"))) for k in agent_pairs
            })
            max_possible_pairs = total_agents * (total_agents - 1) // 2  # Undirected

            if pattern_type == "unknown" and max_possible_pairs > 0:
                connection_density = unique_pairs / max_possible_pairs
                if connection_density >= self._mesh_density_threshold:
                    pattern_type = "mesh"
                    pattern_confidence = connection_density * 100

        # Identify hub agent if hub pattern
        hub_agent = None
        if pattern_type == "hub":
            # Find agent with most total interactions
            agent_totals = {
                agent: agent_send_counts.get(agent, 0) + agent_receive_counts.get(agent, 0)
                for agent in all_agents
            }
            hub_agent = max(agent_totals.items(), key=lambda x: x[1])[0] if agent_totals else None

        # Calculate interaction type distribution
        interaction_types = defaultdict(int)
        for interaction in self._interactions:
            interaction_types[interaction["interaction_type"]] += 1

        # Calculate success rate by pattern
        successful_interactions = sum(1 for i in self._interactions if i["success"])
        success_rate = (successful_interactions / len(self._interactions)) * 100

        # Analyze agent roles
        agent_roles = {}
        for agent in all_agents:
            sends = agent_send_counts.get(agent, 0)
            receives = agent_receive_counts.get(agent, 0)
            total = sends + receives

            if total > 0:
                send_ratio = sends / total
                if send_ratio > _COORD_PRODUCER_RATIO:
                    role = "producer"
                elif send_ratio < _COORD_CONSUMER_RATIO:
                    role = "consumer"
                else:
                    role = "coordinator"
            else:
                role = "inactive"

            agent_roles[agent] = {
                "role": role,
                "sends": sends,
                "receives": receives,
                "total_interactions": total
            }

        return {
            "total_interactions": len(self._interactions),
            "total_agents": total_agents,
            "pattern_type": pattern_type,
            "pattern_confidence": round(pattern_confidence, 2),
            "hub_agent": hub_agent,
            "agent_roles": agent_roles,
            "interaction_type_distribution": dict(interaction_types),
            "success_rate": round(success_rate, 2),
            "top_agent_pairs": sorted(
                [{"pair": k, "count": v} for k, v in agent_pairs.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:5],  # Top 5 most frequent agent pairs
            "pattern_characteristics": self._describe_pattern(pattern_type, total_agents, agent_roles)
        }

    def _describe_pattern(self, pattern_type: str, total_agents: int, agent_roles: dict) -> dict[str, Any]:
        """Generate pattern characteristics description"""
        if pattern_type == "hub":
            return {
                "description": "Hub Pattern - Centralized coordination through a central agent",
                "strengths": ["Clear command structure", "Efficient for task distribution"],
                "weaknesses": ["Single point of failure", "Potential bottleneck at hub"],
                "recommendation": "Monitor hub agent performance to avoid bottlenecks"
            }
        elif pattern_type == "chain":
            return {
                "description": "Chain Pattern - Sequential agent-to-agent processing",
                "strengths": ["Simple workflow", "Clear dependencies", "Easy to debug"],
                "weaknesses": ["Sequential bottlenecks", "No parallelization"],
                "recommendation": "Consider parallelizing independent steps"
            }
        elif pattern_type == "mesh":
            return {
                "description": "Mesh Pattern - Fully connected multi-agent collaboration",
                "strengths": ["High redundancy", "Flexible routing", "No single point of failure"],
                "weaknesses": ["Complex coordination", "Potential for conflicts"],
                "recommendation": "Implement conflict resolution and consensus mechanisms"
            }
        else:
            return {
                "description": "Unknown Pattern - Interaction pattern unclear or mixed",
                "strengths": ["Flexible structure"],
                "weaknesses": ["May indicate inefficient coordination"],
                "recommendation": "Analyze agent interactions to establish clearer patterns"
            }

    def get_network_topology(self) -> dict[str, Any]:
        """에이전트 네트워크 토폴로지 요약을 반환한다 (C4).

        ``analyze_interaction_patterns()`` 를 호출해 패턴을 감지하고
        핵심 지표만 추출한 compact 뷰를 반환한다.

        Returns:
            Dict with keys:
                - ``pattern``: ``"hub"`` | ``"chain"`` | ``"mesh"`` | ``"unknown"`` | ``"none"``
                - ``density``: 연결 밀도 (0.0–1.0)
                - ``hub_node``: hub 패턴일 때 중심 에이전트 이름, 아니면 ``None``
                - ``agent_count``: 고유 에이전트 수
                - ``total_interactions``: 총 상호작용 수

        Example::

            topo = tracker.get_network_topology()
            # {"pattern": "hub", "density": 0.4, "hub_node": "orchestrator",
            #  "agent_count": 4, "total_interactions": 10}
        """
        if not self._interactions:
            return {
                "pattern": "none",
                "density": 0.0,
                "hub_node": None,
                "agent_count": 0,
                "total_interactions": 0,
            }

        patterns = self.get_interaction_patterns()

        all_agents: set = set()
        for itx in self._interactions:
            if itx.get("from_agent"):
                all_agents.add(itx["from_agent"])
            if itx.get("to_agent"):
                all_agents.add(itx["to_agent"])
        n = len(all_agents)
        # Undirected unique pairs: n*(n-1)/2 maximum — matches sorted-tuple dedup in unique_pairs
        max_pairs = n * (n - 1) // 2 if n > 1 else 1
        unique_pairs = len({
            tuple(sorted([str(itx.get("from_agent", "")), str(itx.get("to_agent", ""))]))
            for itx in self._interactions
        })
        density = round(unique_pairs / max_pairs, 3) if max_pairs > 0 else 0.0

        return {
            "pattern": patterns.get("pattern_type", "unknown"),
            "density": density,
            "hub_node": patterns.get("hub_agent"),
            "agent_count": n,
            "total_interactions": len(self._interactions),
        }


# ============================================================================
# 11. Workflow Execution Tracker (LangChain/LangGraph)
# ============================================================================

class WorkflowExecutionTracker(BaseTracker):
    """Track workflow/chain execution for LangChain and LangGraph"""

    def __init__(self):
        self._executions: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # M4: thread-safe append

    @property
    def executions(self) -> list[dict[str, Any]]:
        """Shallow copy of accumulated workflow execution records."""
        with self._lock:
            return list(self._executions)

    @executions.setter
    def executions(self, value: list[dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        with self._lock:
            self._executions = list(value)

    def __repr__(self) -> str:
        with self._lock:
            return f"WorkflowExecutionTracker(steps={len(self._executions)})"

    def reset(self) -> None:
        """Clear all workflow execution records."""
        with self._lock:
            self._executions.clear()

    def track_step(
        self,
        task_id: str,
        step_name: str,
        step_type: str,  # chain_step, node, edge, branch
        success: bool,
        execution_time: float,
        framework: str = "langchain",  # langchain or langgraph
        metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """워크플로우의 개별 단계(체인 스텝·노드·엣지·분기) 실행을 기록한다.

        Args:
            task_id: 이 단계가 속한 태스크 ID.
            step_name: 단계 이름 (예: ``"retrieval"``, ``"llm_call"``).
            step_type: 단계 유형. 권장값: ``"chain_step"``, ``"node"``, ``"edge"``, ``"branch"``.
            success: 단계 성공 여부.
            execution_time: 단계 소요 시간(초).
            framework: 프레임워크 식별자 (기본값: ``"langchain"``). ``"langgraph"``도 지원.
            metadata: 추가 메타데이터 dict (선택).

        Returns:
            기록된 단계 dict (task_id, step_name, step_type, success, execution_time,
            framework, timestamp, metadata).

        Example:
            >>> tracker.track_step(
            ...     task_id="t1",
            ...     step_name="retrieval",
            ...     step_type="node",
            ...     success=True,
            ...     execution_time=0.45,
            ...     framework="langgraph",
            ... )
        """
        if execution_time < 0.0:
            raise ValidationError(
                f"execution_time must be >= 0.0, got {execution_time} "
                f"(task_id={task_id!r}, step={step_name!r})"
            )
        step = {
            "task_id": task_id,
            "step_name": step_name,
            "step_type": step_type,
            "success": success,
            "execution_time": execution_time,
            "framework": framework,
            "timestamp": datetime.now(),
            "metadata": metadata or {}
        }

        with self._lock:
            self._executions.append(step)
        return step

    def calculate_execution_success_rate(
        self,
        task_id: str | None = None,
        framework: str | None = None
    ) -> dict[str, Any]:
        """워크플로우 단계별·태스크별 실행 성공률을 계산한다.

        Args:
            task_id: 특정 태스크만 집계할 경우 지정. ``None``이면 전체 집계.
            framework: 특정 프레임워크만 집계할 경우 지정 (예: ``"langgraph"``).
                ``None``이면 전체 집계.

        Returns:
            Dict containing:
                - step_success_rate (float): 개별 단계 성공률 (0-100, %)
                - total_steps (int)
                - successful_steps, failed_steps (int)
                - total_tasks (int): 고유 태스크 수
                - fully_successful_tasks (int): 모든 단계가 성공한 태스크 수

        Example:
            >>> stats = tracker.calculate_execution_success_rate(framework="langgraph")
            >>> stats["step_success_rate"]
            95.0
        """
        executions = self._executions

        if task_id:
            executions = [e for e in executions if e["task_id"] == task_id]
        if framework:
            executions = [e for e in executions if e["framework"] == framework]

        if not executions:
            return {
                "step_success_rate": 0.0,
                "total_steps": 0,
                "successful_steps": 0,
                "failed_steps": 0,
                "total_tasks": 0,
                "fully_successful_tasks": 0,
                "task_success_rate": 0.0,
                "avg_steps_per_task": 0.0,
            }

        success_count = sum(1 for e in executions if e["success"])
        success_rate = (success_count / len(executions)) * 100

        # Group by task to get per-task success
        task_groups = defaultdict(list)
        for e in executions:
            task_groups[e["task_id"]].append(e)

        fully_successful_tasks = sum(
            1 for steps in task_groups.values()
            if all(s["success"] for s in steps)
        )

        return {
            "step_success_rate": round(success_rate, 2),
            "total_steps": len(executions),
            "successful_steps": success_count,
            "failed_steps": len(executions) - success_count,
            "total_tasks": len(task_groups),
            "fully_successful_tasks": fully_successful_tasks,
            "task_success_rate": round((fully_successful_tasks / len(task_groups)) * 100, 2) if task_groups else 0,
            "avg_steps_per_task": round(len(executions) / len(task_groups), 2) if task_groups else 0
        }

    def get_graph_traversal_efficiency(self, task_id: str) -> dict[str, Any]:
        """Calculate graph traversal efficiency (LangGraph specific)"""
        steps = [e for e in self._executions if e["task_id"] == task_id and e["framework"] == "langgraph"]

        if not steps:
            return {"efficiency": 0, "note": "No LangGraph data"}

        # Count node transitions and branches
        nodes = [s for s in steps if s["step_type"] == "node"]
        branches = [s for s in steps if s["step_type"] == "branch"]

        # Efficiency = successful nodes / total nodes (not total steps which includes branches/edges)
        successful_nodes = sum(1 for n in nodes if n["success"])
        efficiency = (successful_nodes / len(nodes)) * 100 if nodes else 0

        return {
            "efficiency": round(efficiency, 2),
            "total_steps": len(steps),
            "nodes_executed": len(nodes),
            "branches_taken": len(branches),
            "successful_nodes": successful_nodes,
            # DQ-164: 0.0 durations are unmeasured — exclude from mean
            "avg_node_time": round(statistics.mean(
                [n["execution_time"] for n in nodes if n["execution_time"] > 0]
            ), 3) if any(n["execution_time"] > 0 for n in nodes) else 0
        }

    def get_critical_path_analysis(self) -> dict[str, Any]:
        """Analyze critical path and bottlenecks in workflow execution"""
        if not self._executions:
            return {
                "total_workflows": 0,
                "critical_path": [],
                "bottlenecks": []
            }

        # Group executions by task
        task_groups = defaultdict(list)
        for execution in self._executions:
            task_groups[execution["task_id"]].append(execution)

        # Analyze step performance across all tasks
        step_stats = defaultdict(lambda: {
            "execution_times": [],
            "success_count": 0,
            "failure_count": 0,
            "total_count": 0
        })

        for _task_id, steps in task_groups.items():
            for step in steps:
                step_name = step["step_name"]
                # DQ-164: exclude 0.0 durations (unmeasured) from critical path analysis
                if step["execution_time"] > 0:
                    step_stats[step_name]["execution_times"].append(step["execution_time"])
                step_stats[step_name]["total_count"] += 1
                if step["success"]:
                    step_stats[step_name]["success_count"] += 1
                else:
                    step_stats[step_name]["failure_count"] += 1

        # Calculate statistics for each step
        step_analysis = []
        for step_name, stats in step_stats.items():
            times = stats["execution_times"]  # already filtered (>0) when appended
            step_analysis.append({
                "step_name": step_name,
                "avg_time": round(statistics.mean(times), 3) if times else 0.0,
                "median_time": round(statistics.median(times), 3) if times else 0.0,
                "max_time": round(max(times), 3) if times else 0.0,
                "min_time": round(min(times), 3) if times else 0.0,
                "std_time": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0,
                "success_rate": round((stats["success_count"] / stats["total_count"]) * 100, 2),
                "execution_count": stats["total_count"]
            })

        # Sort by average time to identify critical path
        step_analysis.sort(key=lambda x: x["avg_time"], reverse=True)

        # Identify bottlenecks (top 3 slowest steps)
        bottlenecks = step_analysis[:3] if len(step_analysis) >= 3 else step_analysis

        # Calculate total workflow statistics
        total_execution_times = []
        workflow_success_rates = []
        for _task_id, steps in task_groups.items():
            total_time = sum(s["execution_time"] for s in steps)
            total_execution_times.append(total_time)
            success_rate = (sum(1 for s in steps if s["success"]) / len(steps)) * 100
            workflow_success_rates.append(success_rate)

        # Identify parallelization opportunities
        # Steps that appear in the same position across multiple workflows
        parallel_opportunities = []
        step_types = defaultdict(int)
        for execution in self._executions:
            step_types[execution["step_type"]] += 1

        if step_types.get("branch", 0) > 0:
            parallel_opportunities.append({
                "type": "branch_points",
                "count": step_types["branch"],
                "description": "Branch points detected - potential for parallel execution"
            })

        return {
            "total_workflows": len(task_groups),
            "total_steps": len(self._executions),
            "critical_path": step_analysis,
            "bottlenecks": bottlenecks,
            "workflow_statistics": {
                "avg_total_time": round(statistics.mean(total_execution_times), 3) if total_execution_times else 0,
                "median_total_time": round(statistics.median(total_execution_times), 3) if total_execution_times else 0,
                "max_total_time": round(max(total_execution_times), 3) if total_execution_times else 0,
                "min_total_time": round(min(total_execution_times), 3) if total_execution_times else 0,
                "avg_success_rate": round(statistics.mean(workflow_success_rates), 2) if workflow_success_rates else 0
            },
            "parallelization_opportunities": parallel_opportunities,
            "optimization_recommendations": self._generate_optimization_recommendations(step_analysis, bottlenecks)
        }

    def _generate_optimization_recommendations(self, step_analysis: list[dict], bottlenecks: list[dict]) -> list[str]:
        """Generate optimization recommendations based on critical path analysis"""
        recommendations = []

        if not bottlenecks:
            return ["No significant bottlenecks detected"]

        # Check for slow steps
        for bottleneck in bottlenecks:
            if bottleneck["avg_time"] > 1.0:
                recommendations.append(
                    f"Optimize '{bottleneck['step_name']}' - average time {bottleneck['avg_time']}s is high"
                )

        # Check for high variance (inconsistent performance)
        for step in step_analysis:
            if step["std_time"] > step["avg_time"] * 0.5:
                recommendations.append(
                    f"Investigate '{step['step_name']}' - high variance (std: {step['std_time']}s) indicates inconsistent performance"
                )

        # Check for low success rates
        for step in step_analysis:
            if step["success_rate"] < 90:
                recommendations.append(
                    f"Improve reliability of '{step['step_name']}' - success rate {step['success_rate']}% is below target"
                )

        if not recommendations:
            recommendations.append("All steps performing within acceptable parameters")

        return recommendations[:5]  # Return top 5 recommendations
