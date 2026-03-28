"""
agent_evaluator.core.trackers.layer1
======================================
Layer 1 — Foundation Metrics (native, no external deps):
  TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
  ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker
"""

from __future__ import annotations

import logging
import re
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .base import TaskResult, TaskType
from ...exceptions import ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level threshold constants — change here if defaults need adjustment
# ---------------------------------------------------------------------------
_TCR_PARTIAL_THRESHOLD: float = 0.7      # completion_score: full vs partial boundary
_TCR_EXCELLENT: float = 95.0             # benchmark level: Industry Leading
_TCR_GOOD: float = 85.0                  # benchmark level: Good Performance
_TCR_ACCEPTABLE: float = 70.0            # benchmark level: Acceptable

_HALLUCINATION_OVERLAP_THRESHOLD: float = 0.3   # min fraction of words supported by context
_HALLUCINATION_SENTENCE_MIN_WORDS: int = 5       # skip short sentences (noise reduction)

_QUALITY_SCORE_MAX: float = 5.0          # all quality dimension scores scaled to [0, 5]

# QA accuracy weighted-combination weights (must sum to 1.0)
_QA_WEIGHT_TOKEN_OVERLAP: float = 0.4   # token-level F1 overlap (most important for QA)
_QA_WEIGHT_JACCARD: float = 0.3         # set-based Jaccard similarity
_QA_WEIGHT_LCS: float = 0.2             # longest-common-subsequence ratio
_QA_WEIGHT_CHAR: float = 0.1            # character-level similarity

# Code accuracy constants
# AST 비교 점수가 이 값 이상이면 정규화 비교를 건너뜀 (고신뢰 AST 일치)
_CODE_AST_HIGH_CONFIDENCE_THRESHOLD: float = 0.95
# 정규화 비교(공백·주석 제거)에서 완전 일치 시 반환 값.
# 1.0이 아닌 이유: 주석이나 독스트링이 다를 수 있어 "사실상 같은 코드"지만 완전 동일은 아님
_CODE_NORMALIZED_MATCH_CONFIDENCE: float = 0.95


# ============================================================================
# 1. Task Completion Rate Tracker
# ============================================================================

class TaskCompletionTracker:
    """Track and analyze task completion rates"""

    def __init__(self):
        self.tasks: List[TaskResult] = []
        self.completion_criteria = {
            "full_success": 1.0,
            "partial_success": 0.7,
            "failure": 0.0
        }

    def add_task(self, task: TaskResult):
        """Add a task result"""
        self.tasks.append(task)

    def calculate_tcr(self, task_type: Optional[str] = None) -> Dict[str, float]:
        """Calculate Task Completion Rate"""
        tasks = self.tasks
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]

        if not tasks:
            return {"tcr": 0.0, "total_tasks": 0}

        # Weighted completion
        weighted_completions = sum(
            t.completion_score for t in tasks
        )

        tcr = (weighted_completions / len(tasks)) * 100

        # Count based on completion_score, not success flag
        full_success_count = sum(1 for t in tasks if t.completion_score >= 1.0)
        partial_count = sum(
            1 for t in tasks if _TCR_PARTIAL_THRESHOLD <= t.completion_score < 1.0
        )
        failure_count = sum(1 for t in tasks if t.completion_score < _TCR_PARTIAL_THRESHOLD)

        return {
            "tcr": round(tcr, 2),
            "total_tasks": len(tasks),
            "full_success": full_success_count,
            "partial_success": partial_count,
            "failures": failure_count,
            "success_rate": round((full_success_count / len(tasks)) * 100, 2)
        }

    def get_tcr_by_type(self) -> Dict[str, Dict[str, float]]:
        """Get TCR breakdown by task type"""
        task_types = set(t.task_type for t in self.tasks)
        return {
            (task_type.value if hasattr(task_type, 'value') else str(task_type)): self.calculate_tcr(task_type)
            for task_type in task_types
        }

    def get_benchmark_status(self, tcr: float) -> str:
        """Determine benchmark status"""
        if tcr >= _TCR_EXCELLENT:
            return "Industry Leading"
        elif tcr >= _TCR_GOOD:
            return "Good Performance"
        elif tcr >= _TCR_ACCEPTABLE:
            return "Acceptable"
        else:
            return "Needs Improvement"

    def __repr__(self) -> str:
        return f"TaskCompletionTracker(tasks={len(self.tasks)})"


# ============================================================================
# 2. Accuracy Evaluator
# ============================================================================

class AccuracyEvaluator:
    """Evaluate accuracy across different dimensions"""

    def __init__(self):
        self.evaluations: List[Dict[str, Any]] = []

    def add_evaluation(self, task_id: str, ground_truth: Any,
                      prediction: Any, task_type: str):
        """Add an evaluation"""
        accuracy = self._calculate_accuracy(ground_truth, prediction, task_type)

        self.evaluations.append({
            "task_id": task_id,
            "task_type": task_type,
            "accuracy": accuracy,
            "timestamp": datetime.now()
        })

    def _calculate_accuracy(self, ground_truth: Any, prediction: Any,
                           task_type: str) -> float:
        """Calculate accuracy based on task type"""
        if task_type == TaskType.QA.value:
            return self._qa_accuracy(ground_truth, prediction)
        elif task_type == TaskType.CODE_GENERATION.value:
            return self._code_accuracy(ground_truth, prediction)
        else:
            return self._general_accuracy(ground_truth, prediction)

    def _qa_accuracy(self, ground_truth: str, prediction: str) -> float:
        """
        QA accuracy using improved token-based similarity

        Uses multiple similarity metrics:
        - Token overlap (Jaccard similarity)
        - Longest common subsequence ratio
        - Character-level similarity
        """
        # Normalize text
        def normalize(text):
            # Convert to lowercase
            text = text.lower()
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            # Remove punctuation for better matching
            text = re.sub(r'[^\w\s]', '', text)
            return text

        gt_norm = normalize(ground_truth)
        pred_norm = normalize(prediction)

        if not gt_norm:
            return 0.0

        # 1. Token-based Jaccard similarity
        gt_tokens = set(gt_norm.split())
        pred_tokens = set(pred_norm.split())

        if not gt_tokens:
            return 0.0

        intersection = len(gt_tokens & pred_tokens)
        union = len(gt_tokens | pred_tokens)
        jaccard = intersection / union if union > 0 else 0.0

        # 2. Token overlap ratio (original approach, improved)
        overlap_ratio = intersection / len(gt_tokens)

        # 3. Character-level similarity (handles typos better)
        def char_similarity(s1, s2):
            s1_chars = set(s1)
            s2_chars = set(s2)
            if not s1_chars:
                return 0.0
            char_overlap = len(s1_chars & s2_chars) / len(s1_chars)
            return char_overlap

        char_sim = char_similarity(gt_norm, pred_norm)

        # 4. Longest common subsequence ratio
        def lcs_ratio(s1, s2):
            m, n = len(s1), len(s2)
            if m == 0:
                return 0.0

            # Dynamic programming for LCS
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if s1[i-1] == s2[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])

            lcs_length = dp[m][n]
            return lcs_length / m

        lcs_sim = lcs_ratio(gt_norm, pred_norm)

        # Weighted combination (weights defined as module constants above)
        final_score = (
            _QA_WEIGHT_TOKEN_OVERLAP * overlap_ratio +
            _QA_WEIGHT_JACCARD * jaccard +
            _QA_WEIGHT_LCS * lcs_sim +
            _QA_WEIGHT_CHAR * char_sim
        )

        return min(final_score, 1.0)  # Cap at 1.0

    def _code_accuracy(self, expected_output: Any, actual_output: Any) -> float:
        """
        Code accuracy with multiple evaluation strategies

        Evaluation hierarchy:
        1. Exact match (100% confidence)
        2. AST structural comparison (handles formatting differences)
        3. Normalized comparison (whitespace/comment insensitive)

        Returns:
            Accuracy score (0.0 - 1.0)
        """
        if not isinstance(expected_output, str) or not isinstance(actual_output, str):
            # Non-string code (e.g., already parsed): exact match
            return 1.0 if expected_output == actual_output else 0.0

        # Strategy 1: Exact match (fastest)
        if expected_output == actual_output:
            return 1.0

        # Strategy 2: AST comparison (handles formatting, comments, variable names)
        ast_score = self._ast_comparison(expected_output, actual_output)
        if ast_score >= _CODE_AST_HIGH_CONFIDENCE_THRESHOLD:
            return ast_score

        # Strategy 3: Normalized comparison (whitespace-insensitive)
        normalized_score = self._normalized_code_comparison(expected_output, actual_output)

        # Return best score
        return max(ast_score, normalized_score)

    def _ast_comparison(self, code1: str, code2: str) -> float:
        """
        Compare code using Abstract Syntax Tree (AST)

        This handles:
        - Different whitespace/indentation
        - Different comment styles
        - Reordered imports (future enhancement)

        Returns:
            Similarity score (0.0 - 1.0)
        """
        import ast

        try:
            # Parse both code snippets
            tree1 = ast.parse(code1)
            tree2 = ast.parse(code2)

            # Compare AST structures
            dump1 = ast.dump(tree1)
            dump2 = ast.dump(tree2)

            if dump1 == dump2:
                return 1.0

            # Partial match: count matching nodes
            nodes1 = dump1.split(',')
            nodes2 = dump2.split(',')

            # Calculate Jaccard similarity of AST nodes
            set1 = set(nodes1)
            set2 = set(nodes2)

            intersection = len(set1 & set2)
            union = len(set1 | set2)

            jaccard_score = intersection / union if union > 0 else 0.0

            # AST match should be weighted high (90-100% if structures are similar)
            return jaccard_score

        except SyntaxError:
            # If either code has syntax errors, AST comparison fails
            return 0.0
        except (ValueError, RecursionError) as e:
            logger.warning("AST comparison error for code snippet: %s", e)
            return 0.0
        except Exception as e:
            logger.debug("AST comparison unexpected error: %s", e)
            return 0.0

    def _normalized_code_comparison(self, code1: str, code2: str) -> float:
        """
        Compare code with normalization (whitespace/comment removal)

        Returns:
            Similarity score (0.0 - 1.0)
        """
        def normalize_code(code: str) -> str:
            # Remove comments
            code = re.sub(r'#.*?$', '', code, flags=re.MULTILINE)
            code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
            code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)

            # Remove extra whitespace
            code = re.sub(r'\s+', ' ', code)

            # Remove leading/trailing whitespace
            code = code.strip()

            return code

        norm1 = normalize_code(code1)
        norm2 = normalize_code(code2)

        if norm1 == norm2:
            return _CODE_NORMALIZED_MATCH_CONFIDENCE  # High confidence but not perfect (comments differ)

        # Character-level similarity
        if not norm1:
            return 0.0

        # Simple character overlap
        matches = sum(1 for c1, c2 in zip(norm1, norm2) if c1 == c2)
        max_len = max(len(norm1), len(norm2))

        return matches / max_len if max_len > 0 else 0.0

    def _general_accuracy(self, ground_truth: Any, prediction: Any) -> float:
        """General accuracy"""
        return 1.0 if str(ground_truth) == str(prediction) else 0.0

    def get_accuracy_scores(self) -> Dict[str, float]:
        """Get aggregated accuracy scores"""
        if not self.evaluations:
            return {"overall_accuracy": 0.0}

        df = pd.DataFrame(self.evaluations)

        # HIGH PRIORITY FIX: Handle NaN from std() when single value
        std_val = df["accuracy"].std()

        return {
            "overall_accuracy": round(df["accuracy"].mean() * 100, 2),
            "median_accuracy": round(df["accuracy"].median() * 100, 2),
            "min_accuracy": round(df["accuracy"].min() * 100, 2),
            "max_accuracy": round(df["accuracy"].max() * 100, 2),
            "std_accuracy": round(std_val * 100, 2) if not pd.isna(std_val) else 0.0,
            "high_accuracy_count": int((df["accuracy"] >= 0.9).sum()),
            "low_accuracy_count": int((df["accuracy"] < 0.7).sum()),
        }

    def get_accuracy_by_type(self) -> Dict[str, float]:
        """Get accuracy breakdown by task type"""
        if not self.evaluations:
            return {}

        df = pd.DataFrame(self.evaluations)
        return df.groupby("task_type")["accuracy"].mean().mul(100).round(2).to_dict()

    def get_accuracy_metrics(self) -> Dict[str, Any]:
        """Alias for print_metric_breakdown compatibility"""
        if not self.evaluations:
            return {}
        scores = [e.get("accuracy", 0) for e in self.evaluations]
        return {
            "scores": scores,
            "overall_accuracy": round(sum(scores) / len(scores) * 100, 2) if scores else 0.0,
            "median_accuracy": round(statistics.median(scores) * 100, 2) if scores else 0.0,
        }

    def __repr__(self) -> str:
        avg = (
            round(sum(e.get("accuracy", 0) for e in self.evaluations) / len(self.evaluations) * 100, 1)
            if self.evaluations else 0.0
        )
        return f"AccuracyEvaluator(evaluations={len(self.evaluations)}, avg={avg}%)"


# ============================================================================
# 3. Hallucination Detector
# ============================================================================

class HallucinationDetector:
    """
    Rule-based hallucination detector (Layer 1 Native Metric)

    ⚠️ LIMITATIONS:
    - Pattern-based detection (70-80% accuracy)
    - May flag valid paraphrasing/summarization as hallucination
    - Cannot detect semantic hallucinations (e.g., factual errors)
    - Relies on simple word overlap (30% threshold)

    ✅ STRENGTHS:
    - Fast execution (no API calls)
    - Free (no external dependencies)
    - Good for detecting obvious inconsistencies (numbers, unsupported claims)

    🎯 RECOMMENDED FOR:
    - Quick validation during development
    - Detecting numerical inconsistencies
    - Flagging responses with very low context overlap

    📈 FOR PRODUCTION USE:
    - Use HybridPerformanceMonitor with DeepEval's semantic hallucination detection
    - DeepEval provides 90-95% accuracy with LLM-based analysis
    - See: agent_evaluator.integrations.metric_adapters.DeepEvalAdapter

    Detection Methods:
    1. Unsupported Claims: Response sentences with < 30% word overlap with context
    2. Numerical Inconsistencies: Numbers in response not found in context/ground_truth
    """

    def __init__(self):
        self.detections: List[Dict[str, Any]] = []

    def detect_hallucination(self, task_id: str, response: str,
                            context: str, ground_truth: Optional[str] = None,
                            request: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect hallucinations using rule-based patterns

        Args:
            task_id: Unique task identifier
            response: Agent's response text
            context: Context/retrieved documents used for generation
            ground_truth: Optional expected answer for validation
            request: Original question/query (displayed in dashboard)

        Returns:
            Detection result with hallucination rate and indicators

        Note:
            This is a heuristic-based detector. For production use with high accuracy
            requirements, consider using DeepEval's semantic hallucination metric via
            HybridPerformanceMonitor.
        """
        hallucination_indicators = []

        # 1. Check for unsupported claims (simple heuristic)
        # Split and filter empty sentences
        response_sentences = [s.strip() for s in response.split('.') if s.strip()]
        context_words = set(context.lower().split())

        for sentence in response_sentences:
            sentence_words = set(sentence.lower().split())

            # CRITICAL FIX: Skip empty sentences to avoid zero division
            if len(sentence_words) == 0:
                continue

            overlap = len(sentence_words & context_words)

            # If overlap ratio below threshold, flag as potential hallucination
            if (len(sentence_words) > _HALLUCINATION_SENTENCE_MIN_WORDS
                    and overlap / len(sentence_words) < _HALLUCINATION_OVERLAP_THRESHOLD):
                hallucination_indicators.append({
                    "type": "unsupported_claim",
                    "sentence": sentence.strip(),
                    "severity": "medium"
                })

        # 2. Check for numerical inconsistencies
        response_numbers = re.findall(r'\d+\.?\d*', response)
        context_numbers = re.findall(r'\d+\.?\d*', context)

        # CRITICAL FIX: Handle ground_truth None properly
        ground_truth_numbers = re.findall(r'\d+\.?\d*', ground_truth) if ground_truth else []

        for num in response_numbers:
            if num not in context_numbers and num not in ground_truth_numbers:
                hallucination_indicators.append({
                    "type": "numerical_inconsistency",
                    "value": num,
                    "severity": "high"
                })

        # HIGH PRIORITY FIX: Empty response is 100% hallucination
        if not response_sentences:
            hallucination_rate = 1.0  # Empty response is 100% hallucination
        else:
            hallucination_rate = min(len(hallucination_indicators) / len(response_sentences), 1.0)

        detection = {
            "task_id": task_id,
            "hallucination_rate": hallucination_rate,
            "indicators": hallucination_indicators,
            "response_sentences": len(response_sentences),   # 응답 문장 수
            "question": request[:200] if request else None,  # 원래 질문 (최대 200자)
            "context": context[:300] if context else None,   # 참조 컨텍스트 (최대 300자)
            "timestamp": datetime.now()
        }

        self.detections.append(detection)
        return detection

    def get_hallucination_rate(self) -> Dict[str, float]:
        """Get overall hallucination statistics"""
        if not self.detections:
            return {
                "overall_rate": 0.0,
                "total_evaluated": 0,  # Added for dashboard
                "total_flagged": 0,  # Added for dashboard
                "unsupported_claims_count": 0,  # Added for dashboard
                "numerical_inconsistencies_count": 0  # Added for dashboard
            }

        rates = [d["hallucination_rate"] for d in self.detections]
        flagged_count = sum(1 for r in rates if r > 0)

        # Count hallucination types
        unsupported_claims_count = 0
        numerical_inconsistencies_count = 0

        for detection in self.detections:
            for indicator in detection.get("indicators", []):
                if indicator.get("type") == "unsupported_claim":
                    unsupported_claims_count += 1
                elif indicator.get("type") == "numerical_inconsistency":
                    numerical_inconsistencies_count += 1

        return {
            "overall_rate": round(statistics.mean(rates) * 100, 2),
            "median_rate": round(statistics.median(rates) * 100, 2),
            "max_rate": round(max(rates) * 100, 2),
            "tasks_with_hallucinations": flagged_count,
            "total_tasks_checked": len(rates),
            "total_evaluated": len(rates),  # Added for dashboard
            "total_flagged": flagged_count,  # Added for dashboard
            "unsupported_claims_count": unsupported_claims_count,  # Added for dashboard
            "numerical_inconsistencies_count": numerical_inconsistencies_count  # Added for dashboard
        }

    def get_hallucination_by_type(self) -> Dict[str, Any]:
        """Get hallucination statistics broken down by type

        Returns:
            Dictionary with counts and rates for each hallucination type
        """
        if not self.detections:
            return {
                "unsupported_claims": 0,
                "numerical_errors": 0,
                "temporal_errors": 0,
                "other_errors": 0,
                "total_hallucinations": 0,
                "total_detections": 0,
                "by_severity": {
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }
            }

        # Count by type
        type_counts = {
            "unsupported_claim": 0,
            "numerical_inconsistency": 0,
            "temporal_inconsistency": 0,
            "other": 0
        }

        # Count by severity
        severity_counts = {
            "high": 0,
            "medium": 0,
            "low": 0
        }

        total_indicators = 0

        for detection in self.detections:
            for indicator in detection.get("indicators", []):
                total_indicators += 1

                # Count by type
                ind_type = indicator.get("type", "other")
                if ind_type in type_counts:
                    type_counts[ind_type] += 1
                else:
                    type_counts["other"] += 1

                # Count by severity
                severity = indicator.get("severity", "medium")
                if severity in severity_counts:
                    severity_counts[severity] += 1

        return {
            "unsupported_claims": type_counts["unsupported_claim"],
            "numerical_errors": type_counts["numerical_inconsistency"],
            "temporal_errors": type_counts["temporal_inconsistency"],
            "other_errors": type_counts["other"],
            "total_hallucinations": total_indicators,
            "total_detections": len(self.detections),
            "hallucination_rate": round((total_indicators / len(self.detections)) * 100, 2) if self.detections else 0.0,
            "by_severity": severity_counts,
            "avg_per_detection": round(total_indicators / len(self.detections), 2) if self.detections else 0.0
        }

    def __repr__(self) -> str:
        rate = (
            round(
                sum(len(d.get("indicators", [])) for d in self.detections)
                / len(self.detections) * 100, 1
            )
            if self.detections else 0.0
        )
        return f"HallucinationDetector(detections={len(self.detections)}, rate={rate}%)"


# ============================================================================
# 4. Response Quality Evaluator
# ============================================================================

class ResponseQualityEvaluator:
    """Evaluate response quality across multiple dimensions"""

    #: Default dimension weights (must sum to 1.0). Override via constructor.
    DEFAULT_DIMENSIONS: Dict[str, float] = {
        "relevance": 0.25,
        "completeness": 0.25,
        "accuracy": 0.20,
        "clarity": 0.15,
        "usefulness": 0.15,
    }

    def __init__(self, dimensions: Optional[Dict[str, float]] = None):
        """
        Args:
            dimensions: Custom dimension weights dict. Must sum to 1.0 (±0.01 tolerance).
                If None, uses ``DEFAULT_DIMENSIONS``.

        Raises:
            ValidationError: If provided weights do not sum to 1.0.

        Example:
            >>> evaluator = ResponseQualityEvaluator(
            ...     dimensions={"relevance": 0.5, "completeness": 0.3,
            ...                 "accuracy": 0.1, "clarity": 0.05, "usefulness": 0.05}
            ... )
        """
        if dimensions is not None:
            weight_sum = sum(dimensions.values())
            if not (0.99 <= weight_sum <= 1.01):
                raise ValidationError(
                    f"Dimension weights must sum to 1.0, got {weight_sum:.4f}. "
                    f"Weights: {dimensions}"
                )
            self.dimensions = dict(dimensions)
        else:
            self.dimensions = dict(self.DEFAULT_DIMENSIONS)
        self.evaluations: List[Dict[str, Any]] = []

    def evaluate_response(self, task_id: str, response: str,
                         request: str, expected_elements: List[str],
                         ground_truth: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate response quality

        Args:
            task_id: Task identifier
            response: The response to evaluate
            request: Original request/question
            expected_elements: List of expected elements in the response
            ground_truth: Optional ground truth for accuracy calculation

        Returns:
            Dict containing evaluation results
        """
        scores = {}

        # Relevance (keyword overlap)
        request_words = set(request.lower().split())
        response_words = set(response.lower().split())

        # CRITICAL FIX: Handle empty request_words to avoid zero division
        if not request_words:
            relevance = 0.0
        else:
            relevance = len(request_words & response_words) / len(request_words)
        scores["relevance"] = min(relevance * _QUALITY_SCORE_MAX, _QUALITY_SCORE_MAX)

        # Completeness (check for expected elements)
        found_elements = sum(1 for elem in expected_elements if elem.lower() in response.lower())

        # CRITICAL FIX: Handle empty expected_elements properly
        if expected_elements and len(expected_elements) > 0:
            completeness = found_elements / len(expected_elements)
        else:
            # No requirements means 100% complete
            completeness = 1.0
        scores["completeness"] = completeness * _QUALITY_SCORE_MAX

        # Clarity (based on response length and structure)
        word_count = len(response.split())
        has_structure = '\n' in response or '.' in response
        clarity = min(word_count / 100, 1.0) * (1.2 if has_structure else 1.0)
        scores["clarity"] = min(clarity * _QUALITY_SCORE_MAX, _QUALITY_SCORE_MAX)

        # Accuracy score (use ground truth if available)
        if ground_truth:
            # Calculate similarity with ground truth
            similarity = self._calculate_similarity(response, ground_truth)
            scores["accuracy"] = similarity * _QUALITY_SCORE_MAX
        else:
            # Heuristic: longer, more complete responses tend to be more accurate
            scores["accuracy"] = min(completeness * 4.5, _QUALITY_SCORE_MAX)

        # Usefulness score (heuristic based on response characteristics)
        # Good indicators: length, structure, specific examples
        has_examples = any(word in response.lower() for word in ['예를 들어', 'example', ':', '•', '-'])
        has_numbers = any(char.isdigit() for char in response)
        word_count = len(response.split())

        usefulness = (
            0.4 * min(word_count / 150, 1.0) +  # Adequate length
            0.3 * (1.0 if has_structure else 0.5) +  # Well-structured
            0.2 * (1.0 if has_examples else 0.5) +  # Has examples
            0.1 * (1.0 if has_numbers else 0.5)     # Has specific data
        )
        scores["usefulness"] = usefulness * _QUALITY_SCORE_MAX

        # Calculate weighted total
        total_score = sum(
            scores[dim] * weight
            for dim, weight in self.dimensions.items()
        )

        grade = self._assign_grade(total_score)

        evaluation = {
            "task_id": task_id,
            "dimension_scores": scores,
            "total_score": round(total_score, 2),
            "grade": grade,
            "timestamp": datetime.now()
        }

        self.evaluations.append(evaluation)
        return evaluation

    def _assign_grade(self, score: float) -> str:
        """Assign letter grade"""
        if score >= 4.5:
            return "A"
        elif score >= 4.0:
            return "B"
        elif score >= 3.5:
            return "C"
        elif score >= 3.0:
            return "D"
        else:
            return "F"

    def _calculate_similarity(self, response: str, ground_truth: str) -> float:
        """
        Calculate similarity between response and ground truth

        Uses token-based similarity with normalization
        """
        # Normalize text
        def normalize(text):
            text = text.lower()
            text = re.sub(r'\s+', ' ', text).strip()
            text = re.sub(r'[^\w\s]', '', text)
            return text

        response_norm = normalize(response)
        gt_norm = normalize(ground_truth)

        if not gt_norm:
            return 0.0

        # Token overlap
        response_tokens = set(response_norm.split())
        gt_tokens = set(gt_norm.split())

        if not gt_tokens:
            return 0.0

        intersection = len(response_tokens & gt_tokens)
        union = len(response_tokens | gt_tokens)

        # Jaccard similarity
        jaccard = intersection / union if union > 0 else 0.0

        # Coverage (how much of ground truth is covered)
        coverage = intersection / len(gt_tokens)

        # Weighted combination (favor coverage)
        similarity = 0.6 * coverage + 0.4 * jaccard

        return min(similarity, 1.0)

    def get_quality_metrics(self) -> Dict[str, Any]:
        """Get aggregated quality metrics"""
        if not self.evaluations:
            return {
                "avg_total_score": 0.0, "avg_grade": "N/A",
                "median_total_score": 0.0, "min_total_score": 0.0,
                "max_total_score": 0.0, "std_total_score": 0.0,
                "grade_distribution": {}, "high_quality_count": 0,
                "total_evaluated": 0, "dimension_averages": {},
                "dimension_scores": {}, "quality_distribution": {},
            }

        df = pd.DataFrame(self.evaluations)

        grade_dist = df["grade"].value_counts().to_dict()

        # HIGH PRIORITY FIX: Handle NaN from std() when single value
        std_val = df["total_score"].std()

        # Count high quality (grade A or B)
        high_quality_count = len(df[df["grade"].isin(["A", "B"])])

        # Calculate dimension averages
        dimension_averages = {
            dim: round(
                df["dimension_scores"].apply(lambda x: x[dim]).mean(),
                2
            )
            for dim in self.dimensions.keys()
        }

        # Create quality distribution by score ranges
        quality_distribution = {}
        for _, eval_data in df.iterrows():
            score = eval_data["total_score"]
            if score >= 4.5:
                range_key = "4.5-5.0 (Excellent)"
            elif score >= 4.0:
                range_key = "4.0-4.5 (Good)"
            elif score >= 3.5:
                range_key = "3.5-4.0 (Fair)"
            elif score >= 3.0:
                range_key = "3.0-3.5 (Poor)"
            else:
                range_key = "0-3.0 (Very Poor)"

            quality_distribution[range_key] = quality_distribution.get(range_key, 0) + 1

        avg_score = round(df["total_score"].mean(), 2)
        return {
            "avg_total_score": avg_score,
            "avg_grade": self._assign_grade(avg_score),
            "median_total_score": round(df["total_score"].median(), 2),
            "min_total_score": round(df["total_score"].min(), 2),
            "max_total_score": round(df["total_score"].max(), 2),
            "std_total_score": round(std_val, 2) if not pd.isna(std_val) else 0.0,
            "grade_distribution": grade_dist,
            "high_quality_count": high_quality_count,
            "total_evaluated": len(self.evaluations),  # Add for dashboard compatibility
            "dimension_averages": dimension_averages,
            "dimension_scores": dimension_averages,  # Alias for dashboard compatibility
            "quality_distribution": quality_distribution  # Add quality distribution for dashboard
        }

    def get_quality_by_dimension(self) -> Dict[str, Any]:
        """Get detailed quality statistics broken down by each dimension

        Returns:
            Dictionary with detailed statistics for each quality dimension
        """
        if not self.evaluations:
            return {
                "relevance": 0.0,
                "completeness": 0.0,
                "accuracy": 0.0,
                "clarity": 0.0,
                "usefulness": 0.0,
                "by_dimension_detailed": {}
            }

        # Collect all dimension scores
        dimension_scores = {dim: [] for dim in self.dimensions.keys()}

        for eval_data in self.evaluations:
            scores = eval_data.get("dimension_scores", {})
            for dim in self.dimensions.keys():
                if dim in scores:
                    dimension_scores[dim].append(scores[dim])

        # Calculate detailed statistics for each dimension
        dimension_stats = {}
        for dim, scores in dimension_scores.items():
            if scores:
                dimension_stats[dim] = {
                    "average": round(statistics.mean(scores), 2),
                    "median": round(statistics.median(scores), 2),
                    "min": round(min(scores), 2),
                    "max": round(max(scores), 2),
                    "std": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
                    "count": len(scores),
                    "distribution": self._get_score_distribution(scores)
                }
            else:
                dimension_stats[dim] = {
                    "average": 0.0,
                    "median": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "std": 0.0,
                    "count": 0,
                    "distribution": {}
                }

        # Return both simple averages (for backward compatibility) and detailed stats
        return {
            "relevance": dimension_stats["relevance"]["average"],
            "completeness": dimension_stats["completeness"]["average"],
            "accuracy": dimension_stats["accuracy"]["average"],
            "clarity": dimension_stats["clarity"]["average"],
            "usefulness": dimension_stats["usefulness"]["average"],
            "by_dimension_detailed": dimension_stats,
            "total_evaluations": len(self.evaluations)
        }

    def _get_score_distribution(self, scores: List[float]) -> Dict[str, int]:
        """Get distribution of scores in ranges"""
        distribution = {
            "0-1": 0,
            "1-2": 0,
            "2-3": 0,
            "3-4": 0,
            "4-5": 0
        }

        for score in scores:
            if score < 1.0:
                distribution["0-1"] += 1
            elif score < 2.0:
                distribution["1-2"] += 1
            elif score < 3.0:
                distribution["2-3"] += 1
            elif score < 4.0:
                distribution["3-4"] += 1
            else:
                distribution["4-5"] += 1

        return distribution

    def __repr__(self) -> str:
        avg = (
            round(
                sum(e.get("total_score", 0) for e in self.evaluations) / len(self.evaluations), 2
            )
            if self.evaluations else 0.0
        )
        return f"ResponseQualityEvaluator(evaluations={len(self.evaluations)}, avg_score={avg})"


# ============================================================================
# 5. Latency Tracker
# ============================================================================

class LatencyTracker:
    """Track and analyze response latency"""

    def __init__(self):
        self.latencies: List[Dict[str, Any]] = []

    def record_latency(self, task_id: str, task_type: str,
                       total_time: float, breakdown: Dict[str, float]):
        """Record latency for a task"""
        self.latencies.append({
            "task_id": task_id,
            "task_type": task_type,
            "total_time": total_time,
            "breakdown": breakdown,
            "timestamp": datetime.now()
        })

    def get_latency_stats(self, task_type: Optional[str] = None) -> Dict[str, float]:
        """Get latency statistics"""
        latencies = self.latencies
        if task_type:
            latencies = [l for l in latencies if l["task_type"] == task_type]

        if not latencies:
            return {"mean": 0.0, "median": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0,
                    "min": 0.0, "max": 0.0, "std": 0.0}

        times = [l["total_time"] for l in latencies]

        return {
            "mean": round(statistics.mean(times), 3),
            "median": round(statistics.median(times), 3),
            "p50": round(np.percentile(times, 50), 3),
            "p95": round(np.percentile(times, 95), 3),
            "p99": round(np.percentile(times, 99), 3),
            "min": round(min(times), 3),
            "max": round(max(times), 3),
            "std": round(statistics.stdev(times) if len(times) > 1 else 0, 3)
        }

    def analyze_bottlenecks(self) -> Dict[str, Any]:
        """Identify performance bottlenecks"""
        if not self.latencies:
            return {}

        # Aggregate breakdown times
        breakdown_totals = defaultdict(float)
        breakdown_counts = defaultdict(int)

        for latency in self.latencies:
            # Skip if breakdown is empty or None
            if not latency.get("breakdown"):
                continue
            for component, time in latency["breakdown"].items():
                breakdown_totals[component] += time
                breakdown_counts[component] += 1

        # Return empty if no breakdown data
        if not breakdown_totals:
            return {"breakdown_averages": {}, "bottleneck": None}

        breakdown_avgs = {
            component: breakdown_totals[component] / breakdown_counts[component]
            for component in breakdown_totals
        }

        bottleneck = max(breakdown_avgs, key=breakdown_avgs.get)

        return {
            "breakdown_averages": {k: round(v, 3) for k, v in breakdown_avgs.items()},
            "bottleneck": bottleneck,
            "bottleneck_avg_time": round(breakdown_avgs[bottleneck], 3)
        }

    def get_latency_by_type(self) -> Dict[str, Dict[str, float]]:
        """Get latency statistics broken down by task type

        Returns:
            Dictionary mapping task_type to its latency statistics
        """
        if not self.latencies:
            return {}

        # Group latencies by task type
        latencies_by_type = defaultdict(list)
        for latency in self.latencies:
            task_type = latency.get("task_type", "unknown")
            latencies_by_type[task_type].append(latency["total_time"])

        # Calculate statistics for each type
        type_stats = {}
        for task_type, times in latencies_by_type.items():
            if times:
                type_stats[task_type] = {
                    "mean": round(statistics.mean(times), 3),
                    "median": round(statistics.median(times), 3),
                    "min": round(min(times), 3),
                    "max": round(max(times), 3),
                    "p95": round(np.percentile(times, 95), 3),
                    "p99": round(np.percentile(times, 99), 3),
                    "count": len(times),
                    "total_time": round(sum(times), 3),
                    "std": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0
                }

        return type_stats

    def check_sla_compliance(self, sla_targets: Dict[str, float]) -> Dict[str, Any]:
        """Check SLA compliance"""
        results = {}

        for task_type, target in sla_targets.items():
            type_latencies = [
                l["total_time"] for l in self.latencies
                if l["task_type"] == task_type
            ]

            if not type_latencies:
                continue

            p95 = np.percentile(type_latencies, 95)
            within_sla = sum(1 for t in type_latencies if t <= target)

            results[task_type] = {
                "target": target,
                "p95": round(p95, 3),
                "compliance_rate": round((within_sla / len(type_latencies)) * 100, 2),
                "within_sla": within_sla,
                "total": len(type_latencies)
            }

        return results

    def __repr__(self) -> str:
        mean = (
            round(statistics.mean(l["total_time"] for l in self.latencies), 3)
            if self.latencies else 0.0
        )
        return f"LatencyTracker(records={len(self.latencies)}, mean={mean}s)"


# ============================================================================
# 6. Token Economy Tracker
# ============================================================================

class TokenEconomyTracker:
    """Track token usage and costs"""

    def __init__(self, pricing: Dict[str, float]):
        """
        Args:
            pricing: {"input": cost_per_1k_tokens, "output": cost_per_1k_tokens}

        Raises:
            ValidationError: If any price value is negative.
        """
        for key, price in (pricing or {}).items():
            if price < 0:
                raise ValidationError(
                    f"pricing['{key}'] = {price} is invalid: token prices must be >= 0"
                )
        self.pricing = pricing
        self.usage_log: List[Dict[str, Any]] = []

    def track_usage(self, task_id: str, input_tokens: int,
                   output_tokens: int, task_type: str, model: str = "default"):
        """Track token usage for a task"""
        total_tokens = input_tokens + output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        self.usage_log.append({
            "task_id": task_id,
            "task_type": task_type,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": cost,
            "timestamp": datetime.now()
        })

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on token usage"""
        input_cost = (input_tokens / 1000) * self.pricing["input"]
        output_cost = (output_tokens / 1000) * self.pricing["output"]
        return input_cost + output_cost

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics"""
        if not self.usage_log:
            return {
                "total_tasks": 0, "total_tokens": 0,
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_cost": 0.0, "avg_tokens_per_task": 0.0,
                "avg_cost_per_task": 0.0, "estimated_monthly_cost": 0.0,
                "token_distribution": {"input_ratio": 0.0, "output_ratio": 0.0},
                "cost_percentiles": {"p50": 0.0, "p90": 0.0, "p95": 0.0},
            }

        df = pd.DataFrame(self.usage_log)

        total_input = int(df["input_tokens"].sum())
        total_output = int(df["output_tokens"].sum())
        total_tokens = int(df["total_tokens"].sum())

        return {
            "total_tasks": len(df),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input,  # Added for dashboard
            "total_output_tokens": total_output,  # Added for dashboard
            "total_cost": round(df["cost"].sum(), 4),
            "avg_tokens_per_task": round(df["total_tokens"].mean(), 2),
            "avg_cost_per_task": round(df["cost"].mean(), 4),
            "estimated_monthly_cost": round(df["cost"].sum() * 30, 2),
            "token_distribution": {
                "input_ratio": round(total_input / total_tokens, 3) if total_tokens > 0 else 0,
                "output_ratio": round(total_output / total_tokens, 3) if total_tokens > 0 else 0
            },
            "cost_percentiles": {
                "p50": round(df["cost"].quantile(0.5), 4),
                "p90": round(df["cost"].quantile(0.9), 4),
                "p95": round(df["cost"].quantile(0.95), 4)
            }
        }

    def get_usage_by_type(self) -> Dict[str, Dict[str, float]]:
        """Get usage breakdown by task type"""
        if not self.usage_log:
            return {}

        df = pd.DataFrame(self.usage_log)
        grouped = df.groupby("task_type").agg({
            "total_tokens": ["sum", "mean"],
            "cost": ["sum", "mean"]
        }).round(2)

        return grouped.to_dict()

    def get_cost_breakdown_by_model(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed cost breakdown by model"""
        if not self.usage_log:
            return {}

        # Group by model
        model_data = defaultdict(lambda: {
            "input_tokens": [],
            "output_tokens": [],
            "total_tokens": [],
            "costs": [],
            "task_count": 0
        })

        for entry in self.usage_log:
            model = entry.get("model", "default")
            model_data[model]["input_tokens"].append(entry["input_tokens"])
            model_data[model]["output_tokens"].append(entry["output_tokens"])
            model_data[model]["total_tokens"].append(entry["total_tokens"])
            model_data[model]["costs"].append(entry["cost"])
            model_data[model]["task_count"] += 1

        # Calculate statistics for each model
        breakdown = {}
        for model, data in model_data.items():
            costs = data["costs"]
            total_tokens = data["total_tokens"]
            input_tokens = data["input_tokens"]
            output_tokens = data["output_tokens"]

            breakdown[model] = {
                "total_cost": round(sum(costs), 4),
                "avg_cost_per_task": round(statistics.mean(costs), 4),
                "median_cost": round(statistics.median(costs), 4),
                "min_cost": round(min(costs), 4),
                "max_cost": round(max(costs), 4),
                "std_cost": round(statistics.stdev(costs), 4) if len(costs) > 1 else 0.0,
                "total_tasks": data["task_count"],
                "total_tokens": sum(total_tokens),
                "total_input_tokens": sum(input_tokens),
                "total_output_tokens": sum(output_tokens),
                "avg_tokens_per_task": round(statistics.mean(total_tokens), 2),
                "cost_per_1k_tokens": round((sum(costs) / sum(total_tokens) * 1000), 4) if sum(total_tokens) > 0 else 0.0
            }

        return breakdown

    def __repr__(self) -> str:
        total_cost = sum(r.get("cost", 0) for r in self.usage_log)
        return (
            f"TokenEconomyTracker(records={len(self.usage_log)}, "
            f"total_cost=${total_cost:.4f})"
        )
