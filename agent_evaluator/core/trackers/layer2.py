"""
agent_evaluator.core.trackers.layer2
======================================
Layer 2 — Agentic Metrics (native, no external deps):
  ToolCallAnalyzer, RetryCorrectionTracker, ToolSelectionTracker,
  AgentCoordinationTracker, WorkflowExecutionTracker
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import TaskResult


# ============================================================================
# 7. Tool Call Efficiency Analyzer (Agentic AI - Layer 2)
# ============================================================================

class ToolCallAnalyzer:
    """
    Analyze tool call efficiency for Agentic AI systems

    Layer 2 Metric: Tracks efficiency, redundancy, and failure rates of tool calls.
    This is specific to agent systems that use tools/functions.
    """

    def __init__(self):
        self.executions: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"ToolCallAnalyzer(executions={len(self.executions)})"

    def analyze_execution(self, task_id: str, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze tool calls for a task"""
        if not tool_calls:
            return {
                "task_id": task_id,
                "total_calls": 0,
                "efficiency_score": 100.0
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
            "avg_call_duration": statistics.mean(durations) if durations else 0
        }

        # CRITICAL FIX: Calculate efficiency score with zero division check
        if metrics["total_calls"] > 0:
            waste_rate = (metrics["redundant_calls"] + metrics["failed_calls"]) / metrics["total_calls"]
            metrics["efficiency_score"] = round(max(0, 100 - (waste_rate * 100)), 2)
        else:
            metrics["efficiency_score"] = 100.0

        self.executions.append(metrics)
        return metrics

    def _count_redundant_calls(self, tool_calls: List) -> int:
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

    def get_efficiency_stats(self) -> Dict[str, Any]:
        """Get tool call efficiency statistics"""
        if not self.executions:
            return {
                "total_calls": 0, "success_rate": 0.0,
                "avg_duration": 0.0, "avg_calls_per_task": 0.0,
                "avg_efficiency_score": 100.0, "total_redundant_calls": 0,
                "total_failed_calls": 0, "redundancy_rate": 0.0, "failure_rate": 0.0,
            }

        df = pd.DataFrame(self.executions)

        total_calls = int(df["total_calls"].sum())

        return {
            "total_calls": total_calls,  # Added for dashboard
            "success_rate": round((1 - df["failed_calls"].sum() / total_calls) * 100, 2) if total_calls > 0 else 0,  # Added
            "avg_duration": round(df["avg_call_duration"].mean(), 3) if "avg_call_duration" in df.columns else 0,  # Added
            "avg_calls_per_task": round(df["total_calls"].mean(), 2),
            "avg_efficiency_score": round(df["efficiency_score"].mean(), 2),
            "total_redundant_calls": int(df["redundant_calls"].sum()),
            "total_failed_calls": int(df["failed_calls"].sum()),
            "redundancy_rate": round(
                (df["redundant_calls"].sum() / total_calls) * 100, 2
            ) if total_calls > 0 else 0,
            "failure_rate": round(
                (df["failed_calls"].sum() / total_calls) * 100, 2
            ) if total_calls > 0 else 0
        }

    def get_tool_usage_patterns(self) -> Dict[str, Any]:
        """Get detailed tool usage patterns and statistics"""
        if not self.executions:
            return {
                "total_tasks": 0,
                "tool_frequency": {},
                "pattern_analysis": {}
            }

        # Collect all tool usage data
        all_tools = []
        tool_call_counts = []
        efficiency_scores = []

        for exec_data in self.executions:
            tool_call_counts.append(exec_data.get("total_calls", 0))
            efficiency_scores.append(exec_data.get("efficiency_score", 0))

        # Calculate pattern analysis
        pattern_analysis = {
            "avg_tools_per_task": round(statistics.mean(tool_call_counts), 2) if tool_call_counts else 0,
            "median_tools_per_task": round(statistics.median(tool_call_counts), 2) if tool_call_counts else 0,
            "max_tools_in_single_task": max(tool_call_counts) if tool_call_counts else 0,
            "min_tools_in_single_task": min(tool_call_counts) if tool_call_counts else 0,
            "avg_efficiency": round(statistics.mean(efficiency_scores), 2) if efficiency_scores else 0,
            "tasks_with_redundancy": sum(1 for e in self.executions if e.get("redundant_calls", 0) > 0),
            "tasks_with_failures": sum(1 for e in self.executions if e.get("failed_calls", 0) > 0)
        }

        # Calculate usage distribution
        usage_distribution = {
            "1-2_calls": sum(1 for c in tool_call_counts if 1 <= c <= 2),
            "3-5_calls": sum(1 for c in tool_call_counts if 3 <= c <= 5),
            "6-10_calls": sum(1 for c in tool_call_counts if 6 <= c <= 10),
            "11+_calls": sum(1 for c in tool_call_counts if c > 10)
        }

        # Calculate efficiency distribution
        efficiency_distribution = {
            "excellent_90-100": sum(1 for e in efficiency_scores if e >= 90),
            "good_75-89": sum(1 for e in efficiency_scores if 75 <= e < 90),
            "fair_50-74": sum(1 for e in efficiency_scores if 50 <= e < 75),
            "poor_0-49": sum(1 for e in efficiency_scores if e < 50)
        }

        return {
            "total_tasks": len(self.executions),
            "total_tool_calls": sum(tool_call_counts),
            "pattern_analysis": pattern_analysis,
            "usage_distribution": usage_distribution,
            "efficiency_distribution": efficiency_distribution,
            "redundancy_impact": {
                "total_redundant": sum(e.get("redundant_calls", 0) for e in self.executions),
                "avg_redundant_per_task": round(statistics.mean([e.get("redundant_calls", 0) for e in self.executions]), 2)
            },
            "failure_impact": {
                "total_failed": sum(e.get("failed_calls", 0) for e in self.executions),
                "avg_failed_per_task": round(statistics.mean([e.get("failed_calls", 0) for e in self.executions]), 2)
            }
        }


# ============================================================================
# 8. Retry/Correction Tracker
# ============================================================================

class RetryCorrectionTracker:
    """Track retry and correction attempts"""

    def __init__(self):
        self.attempts: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"RetryCorrectionTracker(attempts={len(self.attempts)})"

    def track_attempts(
        self,
        task_id: str,
        attempts_log: List[Dict[str, Any]],
        task_type: str = "unknown",
    ):
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

        self.attempts.append(analysis)

    def get_retry_metrics(self) -> Dict[str, Any]:
        """Get retry statistics"""
        if not self.attempts:
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

        df = pd.DataFrame(self.attempts)

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
            "avg_retry_time": round(
                df[df["total_attempts"] > 1]["total_retry_time"].mean(), 2
            ) if tasks_with_retries > 0 else 0.0,
            # overall_retry_rate: 재시도 횟수 / 총 시도 횟수 × 100
            "overall_retry_rate": round(
                (df["total_attempts"].sum() - len(df)) / df["total_attempts"].sum() * 100, 2
            ) if df["total_attempts"].sum() > 0 else 0.0,
            "avg_retries_per_task": round(df["total_attempts"].mean() - 1, 2)
        }

    def analyze_failure_patterns(self) -> Dict[str, Any]:
        """Analyze common failure patterns"""
        all_reasons = []
        for attempt in self.attempts:
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
            "most_common": max(reason_counts, key=reason_counts.get) if reason_counts else None
        }


# ============================================================================
# 9. Tool Selection Tracker (Agentic AI)
# ============================================================================

# 도구명 정규화 별칭 맵 — 프레임워크별 명명 차이로 인한 F1 왜곡 방지
# 형식: canonical_name → [alias_list]
_TOOL_ALIASES: Dict[str, List[str]] = {
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
_TOOL_ALIAS_REVERSE: Dict[str, str] = {
    alias: canonical
    for canonical, aliases in _TOOL_ALIASES.items()
    for alias in aliases
}


def _normalize_tool_name(name: str) -> str:
    """도구 이름을 정규화합니다. 알려진 별칭은 canonical 이름으로 변환합니다."""
    n = (name or "").lower().strip()
    return _TOOL_ALIAS_REVERSE.get(n, n)


class ToolSelectionTracker:
    """Track tool selection accuracy for Agentic AI"""

    def __init__(self):
        self.selections: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"ToolSelectionTracker(selections={len(self.selections)})"

    def evaluate_selection(
        self,
        task_id: str,
        expected_tools: List[str],
        actual_tools: List[str]
    ) -> Dict[str, Any]:
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
            return {
                "task_id": task_id,
                "accuracy": 100.0,
                "note": "No expected tools defined"
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
            "accuracy": round(f1_score * 100, 2)  # Use F1 as overall accuracy
        }

        self.selections.append(result)
        return result

    def get_accuracy_stats(self) -> Dict[str, Any]:
        """Get tool selection accuracy statistics"""
        if not self.selections:
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

        df = pd.DataFrame(self.selections)

        return {
            "total_evaluations": len(self.selections),
            "avg_accuracy": round(df["accuracy"].mean(), 2),
            "avg_precision": round(df["precision"].mean(), 2),
            "avg_recall": round(df["recall"].mean(), 2),
            "avg_f1_score": round(df["f1_score"].mean(), 2),
            "total_true_positives": int(df["true_positives"].sum()),
            "total_false_positives": int(df["false_positives"].sum()),
            "total_false_negatives": int(df["false_negatives"].sum())
        }


# ============================================================================
# 10. Agent Coordination Tracker (CrewAI)
# ============================================================================

class AgentCoordinationTracker:
    """Track multi-agent coordination quality for CrewAI"""

    def __init__(self):
        self.interactions: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"AgentCoordinationTracker(interactions={len(self.interactions)})"

    def track_interaction(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        interaction_type: str,  # delegation, communication, collaboration
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
        # DQ-167: allowed interaction_type 외 값은 "delegation"으로 정규화
        _ALLOWED_TYPES = {"delegation", "communication", "collaboration"}
        if interaction_type not in _ALLOWED_TYPES:
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

        self.interactions.append(interaction)
        return interaction

    def calculate_coordination_score(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculate agent coordination quality score"""
        interactions = self.interactions
        if task_id:
            interactions = [i for i in interactions if i["task_id"] == task_id]

        if not interactions:
            return {
                "score": 0.0,
                "success_rate": 0.0,
                "total_interactions": 0,
                "unique_agents": 0,
                "interaction_types": {},
            }

        # Success rate
        success_rate = sum(1 for i in interactions if i["success"]) / len(interactions) * 100

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
        # 50% success rate, 30% diversity, 20% balance
        diversity_score = min(len(agents) / 5, 1.0) * 10  # Assume 5+ agents is ideal
        balance_score = (len(type_counts) / 3) * 10  # Assume 3 types is ideal

        coordination_score = (
            success_rate * 0.5 / 10 +
            diversity_score * 0.3 +
            balance_score * 0.2
        )

        return {
            "score": round(coordination_score, 2),
            "success_rate": round(success_rate, 2),
            "total_interactions": len(interactions),
            "unique_agents": len(agents),
            "interaction_types": dict(type_counts)
        }

    def get_delegation_success_rate(self) -> float:
        """Calculate task delegation success rate"""
        delegations = [i for i in self.interactions if i["interaction_type"] == "delegation"]
        if not delegations:
            return 0.0
        return sum(1 for d in delegations if d["success"]) / len(delegations) * 100

    def get_interaction_patterns(self) -> Dict[str, Any]:
        """Analyze agent interaction patterns (Hub, Chain, Mesh)"""
        if not self.interactions:
            return {
                "total_interactions": 0,
                "pattern_type": "none",
                "pattern_analysis": {}
            }

        # Count interactions per agent
        agent_send_counts = defaultdict(int)  # How many messages each agent sends
        agent_receive_counts = defaultdict(int)  # How many messages each agent receives
        agent_pairs = defaultdict(int)  # Count interactions between specific pairs

        for interaction in self.interactions:
            from_agent = interaction["from_agent"]
            to_agent = interaction["to_agent"]
            agent_send_counts[from_agent] += 1
            agent_receive_counts[to_agent] += 1
            agent_pairs[f"{from_agent}->{to_agent}"] += 1

        all_agents = set(list(agent_send_counts.keys()) + list(agent_receive_counts.keys()))
        total_agents = len(all_agents)

        # Detect pattern type
        pattern_type = "unknown"
        pattern_confidence = 0.0

        # Hub Pattern: One agent has significantly more interactions than others
        if agent_send_counts or agent_receive_counts:
            max_sends = max(agent_send_counts.values()) if agent_send_counts else 0
            max_receives = max(agent_receive_counts.values()) if agent_receive_counts else 0
            total_interactions = len(self.interactions)

            # Hub: Central agent handles > 50% of interactions
            hub_threshold = total_interactions * 0.5
            if max_sends >= hub_threshold or max_receives >= hub_threshold:
                pattern_type = "hub"
                pattern_confidence = min((max(max_sends, max_receives) / total_interactions) * 100, 100)

            # Chain Pattern: Sequential passing (each agent mostly talks to 1-2 others)
            elif total_agents >= 3:
                # Check if agents form a chain (each agent has ~1 sender and ~1 receiver)
                chain_like = sum(1 for agent in all_agents
                               if agent_send_counts.get(agent, 0) <= 2
                               and agent_receive_counts.get(agent, 0) <= 2)

                if chain_like / total_agents >= 0.7:  # 70% of agents fit chain pattern
                    pattern_type = "chain"
                    pattern_confidence = (chain_like / total_agents) * 100

            # Mesh Pattern: Many-to-many connections
            # Check connection density
            unique_pairs = len(agent_pairs)
            max_possible_pairs = total_agents * (total_agents - 1)  # Directed graph

            if max_possible_pairs > 0:
                connection_density = unique_pairs / max_possible_pairs
                if connection_density >= 0.5:  # 50% of possible connections exist
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
        for interaction in self.interactions:
            interaction_types[interaction["interaction_type"]] += 1

        # Calculate success rate by pattern
        successful_interactions = sum(1 for i in self.interactions if i["success"])
        success_rate = (successful_interactions / len(self.interactions)) * 100

        # Analyze agent roles
        agent_roles = {}
        for agent in all_agents:
            sends = agent_send_counts.get(agent, 0)
            receives = agent_receive_counts.get(agent, 0)
            total = sends + receives

            if total > 0:
                send_ratio = sends / total
                if send_ratio > 0.7:
                    role = "producer"
                elif send_ratio < 0.3:
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
            "total_interactions": len(self.interactions),
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

    def _describe_pattern(self, pattern_type: str, total_agents: int, agent_roles: Dict) -> Dict[str, Any]:
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


# ============================================================================
# 11. Workflow Execution Tracker (LangChain/LangGraph)
# ============================================================================

class WorkflowExecutionTracker:
    """Track workflow/chain execution for LangChain and LangGraph"""

    def __init__(self):
        self.executions: List[Dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"WorkflowExecutionTracker(steps={len(self.executions)})"

    def track_step(
        self,
        task_id: str,
        step_name: str,
        step_type: str,  # chain_step, node, edge, branch
        success: bool,
        execution_time: float,
        framework: str = "langchain",  # langchain or langgraph
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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

        self.executions.append(step)
        return step

    def calculate_execution_success_rate(
        self,
        task_id: Optional[str] = None,
        framework: Optional[str] = None
    ) -> Dict[str, Any]:
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
        executions = self.executions

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

    def get_graph_traversal_efficiency(self, task_id: str) -> Dict[str, Any]:
        """Calculate graph traversal efficiency (LangGraph specific)"""
        steps = [e for e in self.executions if e["task_id"] == task_id and e["framework"] == "langgraph"]

        if not steps:
            return {"efficiency": 0, "note": "No LangGraph data"}

        # Count node transitions and branches
        nodes = [s for s in steps if s["step_type"] == "node"]
        branches = [s for s in steps if s["step_type"] == "branch"]

        # Efficiency = successful nodes / total steps * 100
        successful_nodes = sum(1 for n in nodes if n["success"])
        efficiency = (successful_nodes / len(steps)) * 100 if steps else 0

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

    def get_critical_path_analysis(self) -> Dict[str, Any]:
        """Analyze critical path and bottlenecks in workflow execution"""
        if not self.executions:
            return {
                "total_workflows": 0,
                "critical_path": [],
                "bottlenecks": []
            }

        # Group executions by task
        task_groups = defaultdict(list)
        for execution in self.executions:
            task_groups[execution["task_id"]].append(execution)

        # Analyze step performance across all tasks
        step_stats = defaultdict(lambda: {
            "execution_times": [],
            "success_count": 0,
            "failure_count": 0,
            "total_count": 0
        })

        for task_id, steps in task_groups.items():
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
        for task_id, steps in task_groups.items():
            total_time = sum(s["execution_time"] for s in steps)
            total_execution_times.append(total_time)
            success_rate = (sum(1 for s in steps if s["success"]) / len(steps)) * 100
            workflow_success_rates.append(success_rate)

        # Identify parallelization opportunities
        # Steps that appear in the same position across multiple workflows
        parallel_opportunities = []
        step_types = defaultdict(int)
        for execution in self.executions:
            step_types[execution["step_type"]] += 1

        if step_types.get("branch", 0) > 0:
            parallel_opportunities.append({
                "type": "branch_points",
                "count": step_types["branch"],
                "description": "Branch points detected - potential for parallel execution"
            })

        return {
            "total_workflows": len(task_groups),
            "total_steps": len(self.executions),
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

    def _generate_optimization_recommendations(self, step_analysis: List[Dict], bottlenecks: List[Dict]) -> List[str]:
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
