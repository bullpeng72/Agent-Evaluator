"""
AI Agent Technical Performance Evaluation System
================================================
Comprehensive evaluation framework for AI Agent performance metrics
"""

import json
import logging
import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TaskResult:
    """Individual task execution result with Agentic AI support"""
    task_id: str
    task_type: str
    success: bool
    completion_score: float
    accuracy_score: float
    execution_time: float
    tokens_used: Dict[str, int]
    tool_calls: List[Dict[str, Any]]
    attempts: int
    errors: List[str]
    timestamp: datetime

    # Agentic AI specific fields
    agent_interactions: Optional[List[Dict[str, Any]]] = None      # Multi-agent interactions (CrewAI)
    chain_steps: Optional[List[Dict[str, Any]]] = None             # Chain execution steps (LangChain)
    graph_traversal: Optional[Dict[str, Any]] = None               # Graph traversal path (LangGraph)
    conversation_turns: Optional[List[Dict[str, Any]]] = None      # Conversation turns (AutoGen)
    expected_tools: Optional[List[str]] = None                     # Expected tools from golden dataset
    state_transitions: Optional[List[Dict[str, Any]]] = None       # State transitions (LangGraph)
    framework: Optional[str] = None                                 # Framework used (crewai, langchain, langgraph, autogen)


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report"""
    period: str
    total_tasks: int
    accuracy_metrics: Dict[str, float]
    efficiency_metrics: Dict[str, Any]
    quality_metrics: Dict[str, float]
    security_metrics: Dict[str, Any] = None  # Optional security metrics (Layer 1 & 2)
    alerts: List[Dict[str, str]] = None
    recommendations: List[Dict[str, str]] = None
    timestamp: datetime = None


class TaskType(Enum):
    """Task type enumeration"""
    QA = "qa"
    DATA_ANALYSIS = "data_analysis"
    CODE_GENERATION = "code_generation"
    DOCUMENT_CREATION = "document_creation"
    INFORMATION_RETRIEVAL = "information_retrieval"
    REASONING = "reasoning"
    CREATIVE = "creative"
    CODING = "coding"
    PLANNING = "planning"
    TOOL_USE = "tool_use"


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
        partial_count = sum(1 for t in tasks if 0.7 <= t.completion_score < 1.0)
        failure_count = sum(1 for t in tasks if t.completion_score < 0.7)
        
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
        if tcr >= 95:
            return "Industry Leading"
        elif tcr >= 85:
            return "Good Performance"
        elif tcr >= 70:
            return "Acceptable"
        else:
            return "Needs Improvement"


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

        # Weighted combination (emphasize token overlap and LCS)
        final_score = (
            0.4 * overlap_ratio +  # Token overlap (most important for QA)
            0.3 * jaccard +         # Jaccard similarity
            0.2 * lcs_sim +         # Sequence similarity
            0.1 * char_sim          # Character-level similarity
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
        if ast_score >= 0.95:
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
        except Exception as e:
            logger.debug("taskresult calculation error: %s", e)
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
            return 0.95  # High confidence but not perfect (comments differ)

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
                            context: str, ground_truth: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect hallucinations using rule-based patterns

        Args:
            task_id: Unique task identifier
            response: Agent's response text
            context: Context/retrieved documents used for generation
            ground_truth: Optional expected answer for validation

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

            # If less than 30% overlap with context, flag as potential hallucination
            if len(sentence_words) > 5 and overlap / len(sentence_words) < 0.3:
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


# ============================================================================
# 4. Response Quality Evaluator
# ============================================================================

class ResponseQualityEvaluator:
    """Evaluate response quality across multiple dimensions"""
    
    def __init__(self):
        self.evaluations: List[Dict[str, Any]] = []
        self.dimensions = {
            "relevance": 0.25,
            "completeness": 0.25,
            "accuracy": 0.20,
            "clarity": 0.15,
            "usefulness": 0.15
        }
    
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
        scores["relevance"] = min(relevance * 5, 5.0)

        # Completeness (check for expected elements)
        found_elements = sum(1 for elem in expected_elements if elem.lower() in response.lower())

        # CRITICAL FIX: Handle empty expected_elements properly
        if expected_elements and len(expected_elements) > 0:
            completeness = found_elements / len(expected_elements)
        else:
            # No requirements means 100% complete
            completeness = 1.0
        scores["completeness"] = completeness * 5
        
        # Clarity (based on response length and structure)
        word_count = len(response.split())
        has_structure = '\n' in response or '.' in response
        clarity = min(word_count / 100, 1.0) * (1.2 if has_structure else 1.0)
        scores["clarity"] = min(clarity * 5, 5.0)
        
        # Accuracy score (use ground truth if available)
        if ground_truth:
            # Calculate similarity with ground truth
            similarity = self._calculate_similarity(response, ground_truth)
            scores["accuracy"] = similarity * 5  # Scale to 5-point
        else:
            # Heuristic: longer, more complete responses tend to be more accurate
            scores["accuracy"] = min(completeness * 4.5, 5.0)

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
        scores["usefulness"] = usefulness * 5  # Scale to 5-point
        
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
            return {}

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
            return {}
        
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


# ============================================================================
# 6. Token Economy Tracker
# ============================================================================

class TokenEconomyTracker:
    """Track token usage and costs"""
    
    def __init__(self, pricing: Dict[str, float]):
        """
        Args:
            pricing: {"input": cost_per_1k_tokens, "output": cost_per_1k_tokens}
        """
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
            return {}

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
            return {}

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
    
    def track_attempts(self, task_id: str, attempts_log: List[Dict[str, Any]]):
        """Track retry attempts for a task"""
        # DQ-135: 빈 attempts_log는 IndexError 발생 — 단일 성공 시도로 기록하고 조기 반환
        if not attempts_log:
            return
        analysis = {
            "task_id": task_id,
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
            return {}

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
            "avg_retry_time": round(df["total_retry_time"].mean(), 2),
            # Legacy keys for backward compatibility
            "overall_retry_rate": round(retry_rate, 2),
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

class ToolSelectionTracker:
    """Track tool selection accuracy for Agentic AI"""

    def __init__(self):
        self.selections: List[Dict[str, Any]] = []

    def evaluate_selection(
        self,
        task_id: str,
        expected_tools: List[str],
        actual_tools: List[str]
    ) -> Dict[str, Any]:
        """Evaluate if correct tools were selected"""
        if not expected_tools:
            return {
                "task_id": task_id,
                "accuracy": 100.0,
                "note": "No expected tools defined"
            }

        expected_set = set(t.lower() for t in expected_tools)
        actual_set = set(t.lower() for t in actual_tools)

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
            return {}

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

    def track_interaction(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        interaction_type: str,  # delegation, communication, collaboration
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Track agent-to-agent interaction"""
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
            return {"score": 0, "total_interactions": 0}

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
        """Track individual workflow step execution"""
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
        """Calculate workflow execution success rate"""
        executions = self.executions

        if task_id:
            executions = [e for e in executions if e["task_id"] == task_id]
        if framework:
            executions = [e for e in executions if e["framework"] == framework]

        if not executions:
            return {"success_rate": 0, "total_steps": 0}

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


# ============================================================================
# 11. Security Metrics - Layer 1 (Native Security)
# ============================================================================

class SecurityTrackerMixin:
    """Shared utilities for security tracker classes."""

    def _check_patterns(self, text: str, patterns: List[str], flags: int = 0) -> bool:
        """Check if text matches any of the given regex patterns."""
        for pattern in patterns:
            if re.search(pattern, text, flags):
                return True
        return False


class InputSanitizationTracker(SecurityTrackerMixin):
    """
    Track input sanitization and detect injection attacks

    Layer 1 Security Metric: Detects dangerous patterns in user inputs
    including SQL injection, command injection, prompt injection, XSS, etc.
    """

    def __init__(self):
        self.evaluations: List[Dict[str, Any]] = []

        # Dangerous patterns
        self.sql_injection_patterns = [
            r"('\s*OR\s*'1'\s*=\s*'1)", r"(--)", r"(;\s*DROP\s+TABLE)",
            r"(UNION\s+SELECT)", r"(INSERT\s+INTO)", r"(DELETE\s+FROM)",
            r"(UPDATE\s+\w+\s+SET)", r"(/\*.*?\*/)", r"(xp_cmdshell)"
        ]

        self.command_injection_patterns = [
            r"(;\s*rm\s+-rf)", r"(\|\s*curl)", r"(\$\(.*?\))", r"(`.*?`)",
            r"(&&\s*\w+)", r"(\|\|\s*\w+)", r"(>\s*/dev/)", r"(<\s*\()",
            r"(eval\s*\()", r"(exec\s*\()"
        ]

        self.path_traversal_patterns = [
            r"(\.\./)", r"(\.\.\\)", r"(/etc/passwd)", r"(/etc/shadow)",
            r"(C:\\Windows)", r"(/root/)", r"(/var/www)"
        ]

        self.xss_patterns = [
            r"(<script)", r"(javascript:)", r"(onerror\s*=)", r"(onclick\s*=)",
            r"(onload\s*=)", r"(<iframe)", r"(<object)", r"(document\.cookie)"
        ]

        self.prompt_injection_patterns = [
            r"(ignore\s+previous\s+instructions)", r"(system:\s*you\s+are\s+now)",
            r"(admin\s+mode)", r"(developer\s+mode)", r"(jailbreak)",
            r"(DAN\s+mode)", r"(disregard\s+all\s+rules)"
        ]

    def evaluate_input(self, task_id: str, input_text: str) -> Dict[str, Any]:
        """Evaluate input for security threats"""
        result = {
            "task_id": task_id,
            "has_sql_injection": self._check_patterns(input_text, self.sql_injection_patterns),
            "has_command_injection": self._check_patterns(input_text, self.command_injection_patterns),
            "has_path_traversal": self._check_patterns(input_text, self.path_traversal_patterns),
            "has_xss": self._check_patterns(input_text, self.xss_patterns),
            "has_prompt_injection": self._check_patterns(input_text, self.prompt_injection_patterns, re.IGNORECASE)
        }

        # Calculate risk level
        threat_count = sum([result[k] for k in result if k.startswith("has_")])
        if threat_count >= 3:
            result["risk_level"] = "critical"
        elif threat_count == 2:
            result["risk_level"] = "high"
        elif threat_count == 1:
            result["risk_level"] = "medium"
        else:
            result["risk_level"] = "low"

        result["sanitization_needed"] = threat_count > 0
        result["threat_count"] = threat_count

        self.evaluations.append(result)
        return result

    def get_security_stats(self) -> Dict[str, Any]:
        """Get input security statistics"""
        if not self.evaluations:
            return {}

        df = pd.DataFrame(self.evaluations)

        total = len(self.evaluations)

        return {
            "total_inputs_evaluated": total,
            "inputs_with_threats": int(df["sanitization_needed"].sum()),
            "threat_rate": round((df["sanitization_needed"].sum() / total) * 100, 2),
            "sql_injection_attempts": int(df["has_sql_injection"].sum()),
            "command_injection_attempts": int(df["has_command_injection"].sum()),
            "path_traversal_attempts": int(df["has_path_traversal"].sum()),
            "xss_attempts": int(df["has_xss"].sum()),
            "prompt_injection_attempts": int(df["has_prompt_injection"].sum()),
            "critical_risk_inputs": int((df["risk_level"] == "critical").sum()),
            "high_risk_inputs": int((df["risk_level"] == "high").sum())
        }


class OutputLeakageDetector(SecurityTrackerMixin):
    """
    Detect sensitive information leakage in outputs

    Layer 1 Security Metric: Detects API keys, passwords, PII,
    and other sensitive data in agent outputs.
    """

    def __init__(self):
        self.detections: List[Dict[str, Any]] = []

        # Sensitive patterns
        self.api_key_patterns = [
            r"(AIza[0-9A-Za-z\-_]{35})",  # Google API Key
            r"(sk-[a-zA-Z0-9]{32,})",     # OpenAI API Key
            r"(AKIA[0-9A-Z]{16})",        # AWS Access Key
            r"([a-zA-Z0-9]{32,})",        # Generic long strings (potential keys)
        ]

        self.password_patterns = [
            r"(password\s*[:=]\s*['\"]?[\w!@#$%^&*]{8,}['\"]?)",
            r"(pwd\s*[:=]\s*['\"]?[\w!@#$%^&*]{8,}['\"]?)",
            r"(passwd\s*[:=]\s*['\"]?[\w!@#$%^&*]{8,}['\"]?)"
        ]

        self.credit_card_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"

        self.email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        self.phone_pattern = r"\b(\d{3}[-.]?\d{3,4}[-.]?\d{4}|\d{2,3}-\d{3,4}-\d{4})\b"

        self.ssn_pattern = r"\b\d{6}-\d{7}\b"  # Korean SSN pattern

        self.private_ip_patterns = [
            r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
            r"\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b"
        ]

        self.file_path_patterns = [
            r"([A-Z]:\\[\w\\]+)",  # Windows path
            r"(/[a-z]+/[\w/]+)",   # Unix path
        ]

    def detect_leakage(self, task_id: str, output_text: str) -> Dict[str, Any]:
        """Detect sensitive information in output"""
        result = {
            "task_id": task_id,
            "contains_api_key": self._check_patterns(output_text, self.api_key_patterns),
            "contains_password": self._check_patterns(output_text, self.password_patterns, re.IGNORECASE),
            "contains_credit_card": bool(re.search(self.credit_card_pattern, output_text)),
            "contains_email": bool(re.search(self.email_pattern, output_text)),
            "contains_phone": bool(re.search(self.phone_pattern, output_text)),
            "contains_ssn": bool(re.search(self.ssn_pattern, output_text)),
            "contains_private_ip": self._check_patterns(output_text, self.private_ip_patterns),
            "contains_file_path": self._check_patterns(output_text, self.file_path_patterns)
        }

        # Calculate leakage count and severity
        leakage_count = sum([result[k] for k in result if k.startswith("contains_")])
        result["leakage_count"] = leakage_count

        # Severity based on type of data leaked
        if result["contains_api_key"] or result["contains_password"] or result["contains_credit_card"]:
            result["severity"] = "critical"
        elif result["contains_ssn"] or result["contains_email"]:
            result["severity"] = "high"
        elif result["contains_phone"] or result["contains_private_ip"]:
            result["severity"] = "medium"
        elif result["contains_file_path"]:
            result["severity"] = "low"
        else:
            result["severity"] = "none"

        self.detections.append(result)
        return result

    def get_leakage_stats(self) -> Dict[str, Any]:
        """Get output leakage statistics"""
        if not self.detections:
            return {}

        df = pd.DataFrame(self.detections)

        total = len(self.detections)
        outputs_with_leakage = int((df["leakage_count"] > 0).sum())

        return {
            "total_outputs_evaluated": total,
            "outputs_with_leakage": outputs_with_leakage,
            "leakage_rate": round((outputs_with_leakage / total) * 100, 2) if total > 0 else 0,
            "api_key_leaks": int(df["contains_api_key"].sum()),
            "password_leaks": int(df["contains_password"].sum()),
            "credit_card_leaks": int(df["contains_credit_card"].sum()),
            "email_leaks": int(df["contains_email"].sum()),
            "ssn_leaks": int(df["contains_ssn"].sum()),
            "phone_leaks": int(df["contains_phone"].sum()) if "contains_phone" in df.columns else 0,
            "private_ip_leaks": int(df["contains_private_ip"].sum()) if "contains_private_ip" in df.columns else 0,
            "critical_severity_count": int((df["severity"] == "critical").sum()),
            "high_severity_count": int((df["severity"] == "high").sum())
        }


class ToolAuthorizationTracker:
    """
    Track tool authorization compliance

    Layer 1 Security Metric: Monitors tool usage against allowed/restricted lists
    and detects dangerous parameters.
    """

    def __init__(self, allowed_tools: Optional[List[str]] = None,
                 restricted_tools: Optional[List[str]] = None):
        self.allowed_tools = set(allowed_tools) if allowed_tools else None
        self.restricted_tools = set(restricted_tools) if restricted_tools else set()
        self.tool_calls: List[Dict[str, Any]] = []

        # Dangerous parameter patterns
        self.dangerous_patterns = [
            r"(rm\s+-rf)", r"(DROP\s+TABLE)", r"(DELETE\s+FROM)",
            r"(chmod\s+777)", r"(sudo)", r"(eval\s*\()",
            r"(exec\s*\()", r"(__import__)", r"(system\s*\()"
        ]

    def track_tool_call(self, task_id: str, tool_name: str,
                       parameters: Optional[Dict] = None) -> Dict[str, Any]:
        """Track and evaluate tool call authorization"""
        result = {
            "task_id": task_id,
            "tool_name": tool_name,
            "is_authorized": True,
            "is_restricted": False,
            "has_dangerous_params": False,
            "violation_type": None
        }

        # Check if tool is in allowed list (whitelist)
        if self.allowed_tools and tool_name not in self.allowed_tools:
            result["is_authorized"] = False
            result["violation_type"] = "unauthorized_tool"

        # Check if tool is in restricted list (blacklist)
        if tool_name in self.restricted_tools:
            result["is_restricted"] = True
            result["violation_type"] = "restricted_tool"

        # Check for dangerous parameters
        if parameters:
            params_str = json.dumps(parameters)
            for pattern in self.dangerous_patterns:
                if re.search(pattern, params_str, re.IGNORECASE):
                    result["has_dangerous_params"] = True
                    result["violation_type"] = "dangerous_params"
                    break

        # Determine privilege level
        if tool_name in ['delete', 'drop', 'remove', 'execute', 'system']:
            result["privilege_level"] = "admin"
        elif tool_name in ['write', 'update', 'create', 'modify']:
            result["privilege_level"] = "write"
        elif tool_name in ['execute_command', 'run_script', 'eval']:
            result["privilege_level"] = "execute"
        else:
            result["privilege_level"] = "read"

        self.tool_calls.append(result)
        return result

    def get_compliance_stats(self) -> Dict[str, Any]:
        """Get tool authorization compliance statistics"""
        if not self.tool_calls:
            return {}

        df = pd.DataFrame(self.tool_calls)

        total = len(self.tool_calls)
        authorized = int(df["is_authorized"].sum())

        return {
            "total_tool_calls": total,
            "authorized_calls": authorized,
            "unauthorized_calls": total - authorized,
            "restricted_tool_attempts": int(df["is_restricted"].sum()),
            "dangerous_param_attempts": int(df["has_dangerous_params"].sum()),
            "compliance_rate": round((authorized / total) * 100, 2) if total > 0 else 100,
            "violation_rate": round(((total - authorized) / total) * 100, 2) if total > 0 else 0,
            "admin_privilege_calls": int((df["privilege_level"] == "admin").sum()),
            "execute_privilege_calls": int((df["privilege_level"] == "execute").sum())
        }


# ============================================================================
# 12. Security Metrics - Layer 2 (Agentic Security)
# ============================================================================

class PrivilegeEscalationDetector:
    """
    Detect privilege escalation attempts

    Layer 2 Security Metric: Analyzes tool call sequences to detect
    privilege escalation patterns in agent behavior.
    """

    def __init__(self):
        self.escalation_events: List[Dict[str, Any]] = []

        # Privilege levels (0 = lowest, 4 = highest)
        # write and execute are separated: read→write is normal, read→execute is suspicious
        self.privilege_levels = {
            "guest": 0,
            "read": 1,
            "write": 2,
            "execute": 3,
            "admin": 4
        }

        # Suspicious tool sequences
        self.suspicious_sequences = [
            ["read_user_file", "execute_command", "read_admin_file"],
            ["get_token", "modify_permissions", "access_database"],
            ["list_files", "read_credentials", "ssh_connect"],
            ["query_database", "modify_schema", "drop_table"]
        ]

    def analyze_privilege_chain(self, task_id: str, tool_calls: List) -> Dict[str, Any]:
        """Analyze tool call chain for privilege escalation (supports both dict and string formats)"""
        if not tool_calls:
            return {"escalation_detected": False}

        # Extract tool names and privilege levels (handle both dict and string)
        tools = []
        privileges = []
        for call in tool_calls:
            if isinstance(call, str):
                tools.append(call)
                privileges.append("read")  # Default privilege for string tool calls
            elif isinstance(call, dict):
                tools.append(call.get("tool_name", call.get("tool", "unknown")))
                privileges.append(call.get("privilege_level", "read"))
            else:
                tools.append("unknown")
                privileges.append("read")

        # Map to numeric privilege levels
        privilege_values = [self.privilege_levels.get(p, 1) for p in privileges]

        # Detect escalation
        initial_privilege = privilege_values[0] if privilege_values else 1
        final_privilege = privilege_values[-1] if privilege_values else 1
        max_privilege = max(privilege_values) if privilege_values else 1

        # Escalation: reaching execute(3)/admin(4) from lower level, OR jumping ≥2 levels
        # read→write (1→2) is normal and NOT flagged; read→execute (1→3) IS flagged
        escalation_detected = (final_privilege >= 3 and initial_privilege < 3) or max_privilege - initial_privilege >= 2

        # Check for suspicious sequences
        suspicious = self._check_suspicious_sequences(tools)

        # Calculate risk score (0-10)
        risk_score = 0
        if escalation_detected:
            risk_score += 3
        if suspicious:
            risk_score += 4
        if max_privilege >= 3:  # Execute or admin privilege reached
            risk_score += 3
        risk_score = min(risk_score, 10)

        result = {
            "task_id": task_id,
            "initial_privilege": {v: k for k, v in self.privilege_levels.items()}.get(initial_privilege, "unknown"),
            "final_privilege": {v: k for k, v in self.privilege_levels.items()}.get(final_privilege, "unknown"),
            "max_privilege": {v: k for k, v in self.privilege_levels.items()}.get(max_privilege, "unknown"),
            "escalation_detected": escalation_detected,
            "suspicious_sequences": suspicious,
            "escalation_path": tools if escalation_detected else [],
            "risk_score": risk_score
        }

        self.escalation_events.append(result)
        return result

    def _check_suspicious_sequences(self, tools: List[str]) -> List[str]:
        """Check if tools match suspicious sequences"""
        found = []
        for seq in self.suspicious_sequences:
            if self._is_exact_subsequence(seq, tools):
                found.append(" -> ".join(seq))
        return found

    def _is_exact_subsequence(self, subseq: List[str], seq: List[str]) -> bool:
        """Check if subseq is a subsequence of seq"""
        it = iter(seq)
        return all(item in it for item in subseq)

    def get_escalation_stats(self) -> Dict[str, Any]:
        """Get privilege escalation statistics"""
        if not self.escalation_events:
            return {}

        df = pd.DataFrame(self.escalation_events)

        return {
            "total_evaluations": len(self.escalation_events),
            "escalations_detected": int(df["escalation_detected"].sum()),
            "escalation_rate": round((df["escalation_detected"].sum() / len(self.escalation_events)) * 100, 2),
            "avg_risk_score": round(df["risk_score"].mean(), 2),
            "high_risk_events": int((df["risk_score"] >= 7).sum()),
            "suspicious_sequence_count": sum(len(s) for s in df["suspicious_sequences"])
        }


class ToolChainAttackDetector:
    """
    Detect tool chain attack patterns

    Layer 2 Security Metric: Identifies malicious tool usage patterns
    like data exfiltration, lateral movement, etc.
    """

    def __init__(self):
        self.detections: List[Dict[str, Any]] = []

        # Attack patterns — 짧은 키워드 조각으로 정의하여 실제 도구 이름과 매칭 가능
        # _is_fuzzy_subsequence() 가 substring 매칭이므로 "database" 는 "query_database" 에 매칭됨
        self.attack_patterns = {
            "data_exfiltration": [
                ["database", "encode", "post"],        # DB읽기 → 인코딩 → HTTP POST 전송
                ["file", "read", "send"],              # 파일읽기 → 전송
                ["query", "export", "upload"],         # 쿼리 → 내보내기 → 업로드
                ["search", "extract", "transmit"],     # 검색 → 추출 → 전송
                ["read", "compress", "transfer"],      # 읽기 → 압축 → 전송
            ],
            "lateral_movement": [
                ["credential", "connect", "execute"],  # 자격증명 → 접속 → 실행
                ["server", "connect", "escalate"],     # 서버목록 → 접속 → 권한상승
                ["login", "access", "deploy"],         # 로그인 → 접근 → 배포
                ["token", "authenticate", "run"],      # 토큰 → 인증 → 실행
            ],
            "persistence": [
                ["cron", "service", "restart"],        # 크론/서비스 등록
                ["startup", "install", "run"],         # 시작프로그램 등록
                ["schedule", "create", "execute"],     # 스케줄 생성 → 실행
                ["write", "register", "enable"],       # 설정파일 쓰기 → 등록 → 활성화
            ],
            "defense_evasion": [
                ["log", "clear", "delete"],            # 로그 삭제
                ["monitor", "disable", "bypass"],      # 모니터링 우회
                ["audit", "disable", "hide"],          # 감사 비활성화
                ["history", "clear", "wipe"],          # 히스토리 삭제
            ]
        }

    def register_pattern(self, attack_type: str, pattern: List[str]) -> None:
        """사용자 정의 공격 패턴 등록.

        Args:
            attack_type: 공격 유형 이름 (기존 키 또는 새 키 모두 허용)
            pattern: 도구 이름 키워드 조각 리스트 (순서 중요).
                     각 조각은 실제 도구 이름에 substring 매칭됨.
                     예: ["database", "encode", "post"]

        Example:
            >>> detector = ToolChainAttackDetector()
            >>> detector.register_pattern("custom_exfil", ["s3_get", "zip", "ftp_send"])
        """
        if attack_type not in self.attack_patterns:
            self.attack_patterns[attack_type] = []
        self.attack_patterns[attack_type].append(pattern)

    def analyze_tool_chain(self, task_id: str, tool_sequence: List[str]) -> Dict[str, Any]:
        """Analyze tool sequence for attack patterns"""
        if not tool_sequence:
            return {"is_suspicious_chain": False}

        attack_types_detected = {}
        patterns_detected = []

        # Check each attack pattern category
        for attack_type, patterns in self.attack_patterns.items():
            for pattern in patterns:
                if self._is_fuzzy_subsequence(pattern, tool_sequence):
                    attack_types_detected[attack_type] = True
                    patterns_detected.append(f"{attack_type}: {' -> '.join(pattern)}")
                    break
            if attack_type not in attack_types_detected:
                attack_types_detected[attack_type] = False

        is_suspicious = len(patterns_detected) > 0
        confidence = min(len(patterns_detected) * 0.3, 1.0)  # 0-1 scale

        result = {
            "task_id": task_id,
            "chain_length": len(tool_sequence),
            "is_suspicious_chain": is_suspicious,
            "attack_patterns_detected": patterns_detected,
            "confidence": round(confidence, 2),
            "attack_types": attack_types_detected
        }

        self.detections.append(result)
        return result

    def _is_fuzzy_subsequence(self, subseq: List[str], seq: List[str]) -> bool:
        """Check if subseq is a subsequence of seq (with fuzzy matching)"""
        it = iter(seq)
        return all(any(sub_item.lower() in item.lower() for item in it) for sub_item in subseq)

    def get_attack_stats(self) -> Dict[str, Any]:
        """Get tool chain attack statistics"""
        if not self.detections:
            return {}

        df = pd.DataFrame(self.detections)

        return {
            "total_chains_analyzed": len(self.detections),
            "suspicious_chains": int(df["is_suspicious_chain"].sum()),
            "detection_rate": round((df["is_suspicious_chain"].sum() / len(self.detections)) * 100, 2),
            "avg_confidence": round(df["confidence"].mean(), 2),
            "data_exfiltration_detected": sum(d["attack_types"].get("data_exfiltration", False) for d in self.detections),
            "lateral_movement_detected": sum(d["attack_types"].get("lateral_movement", False) for d in self.detections),
            "persistence_detected": sum(d["attack_types"].get("persistence", False) for d in self.detections),
            "defense_evasion_detected": sum(d["attack_types"].get("defense_evasion", False) for d in self.detections)
        }


# ============================================================================
# 13. Main Performance Monitor
# ============================================================================

class PerformanceMonitor:
    """Main performance monitoring and reporting system"""

    def __init__(
        self,
        pricing: Dict[str, float] = None,
        enable_transparency: bool = False,
        enable_hallucination_detection: bool = False,
        enable_security_metrics: bool = False,
        security_config: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None
    ):
        """
        Initialize Performance Monitor

        Args:
            pricing: Token pricing (default: GPT-4 pricing)
            enable_transparency: Enable transparency logging (traces, annotations)
            enable_hallucination_detection: Enable Layer1 hallucination detection (opt-in)
                - False (default): No hallucination detection, best performance
                - True: Automatic hallucination detection when context/response provided
            enable_security_metrics: Enable security metrics tracking (opt-in)
                - False (default): No security tracking, best performance
                - True: Track input/output security and authorization compliance
            security_config: Security configuration (allowed_tools, restricted_tools)
            output_dir: Output directory for results
        """
        if pricing is None:
            pricing = {"input": 0.003, "output": 0.015}  # Default pricing

        # Configuration
        self.enable_hallucination_detection = enable_hallucination_detection
        self.enable_security_metrics = enable_security_metrics
        self.security_config = security_config or {}

        # Zero Configuration: 자동 경로 감지
        from pathlib import Path
        if output_dir is None:
            from ..utils.path_helpers import get_evaluation_results_dir
            output_dir = get_evaluation_results_dir(create=False)
        self.output_dir = Path(output_dir) if isinstance(output_dir, str) else output_dir
        # ⚡ Lazy initialization: 디렉토리는 실제 저장 시점에 생성
        # self.output_dir.mkdir(parents=True, exist_ok=True)

        # Layer 1: Basic trackers (Native Metrics)
        self.tcr_tracker = TaskCompletionTracker()
        self.accuracy_evaluator = AccuracyEvaluator()
        self.hallucination_detector = HallucinationDetector()
        self.quality_evaluator = ResponseQualityEvaluator()
        self.latency_tracker = LatencyTracker()
        self.token_tracker = TokenEconomyTracker(pricing)
        self.retry_tracker = RetryCorrectionTracker()

        # Layer 1: Security trackers (optional)
        self.input_sanitizer = None
        self.output_leakage_detector = None
        self.tool_authorizer = None

        if enable_security_metrics:
            self.input_sanitizer = InputSanitizationTracker()
            self.output_leakage_detector = OutputLeakageDetector()
            self.tool_authorizer = ToolAuthorizationTracker(
                allowed_tools=self.security_config.get('allowed_tools'),
                restricted_tools=self.security_config.get('restricted_tools')
            )
            print("✅ Security metrics (Layer 1) 활성화됨")

        # Layer 2: Agentic AI trackers
        self.tool_analyzer = ToolCallAnalyzer()  # Tool call efficiency
        self.tool_selection_tracker = ToolSelectionTracker()  # Tool selection accuracy
        self.agent_coordination_tracker = AgentCoordinationTracker()
        self.workflow_tracker = WorkflowExecutionTracker()

        # Layer 2: Agentic Security trackers (optional)
        self.privilege_escalation_detector = None
        self.tool_chain_attack_detector = None

        if enable_security_metrics:
            self.privilege_escalation_detector = PrivilegeEscalationDetector()
            self.tool_chain_attack_detector = ToolChainAttackDetector()
            print("✅ Security metrics (Layer 2) 활성화됨")

        # RAG metrics tracker
        self.rag_metrics = {
            'faithfulness': [],
            'answer_relevancy': [],
            'context_recall': [],
            'context_precision': []
        }

        # Test 투명성 추적 (선택적)
        self.enable_transparency = enable_transparency
        self.transparency_manager = None

        if enable_transparency:
            try:
                # CRITICAL FIX: Use correct relative import path
                from ..utils.transparency_manager import TestTransparencyManager
                self.transparency_manager = TestTransparencyManager(output_dir=str(self.output_dir))
                print("✅ Test 투명성 추적 활성화됨")
                # Auto audit: evaluation session started
                self.transparency_manager.log_event(
                    event_type="lifecycle",
                    user="system",
                    action="evaluation_started",
                    target_type="monitor",
                    target_id="performance_monitor",
                    details={
                        "enable_hallucination_detection": enable_hallucination_detection,
                        "enable_security_metrics": enable_security_metrics,
                        "output_dir": str(self.output_dir),
                    },
                    success=True,
                )
            except ImportError as e:
                print(f"⚠️  transparency_manager를 찾을 수 없습니다: {e}")
                print("   투명성 추적 비활성화됨")
                self.enable_transparency = False

        # 임계값 설정 (DataEditorManager에서 로드 가능)
        self.thresholds = None
        self.golden_dataset_path = None
        self.golden_datasets = []

    def load_golden_dataset(self, dataset_path: Optional[str] = None):
        """
        Golden Dataset 로드

        Args:
            dataset_path: Golden Dataset 파일 경로 (None이면 config에서 로드)

        Returns:
            List[Dict]: Golden Dataset 항목 리스트
        """
        import json
        import os

        if dataset_path is None and self.golden_dataset_path:
            dataset_path = self.golden_dataset_path

        if dataset_path is None:
            print("⚠️  Golden Dataset 경로가 지정되지 않았습니다")
            return []

        # golden_datasets 디렉토리에서 찾기
        if not os.path.isabs(dataset_path):
            golden_dir = 'golden_datasets'
            full_path = os.path.join(golden_dir, dataset_path)
            if os.path.exists(full_path):
                dataset_path = full_path

        if not os.path.exists(dataset_path):
            print(f"⚠️  Golden Dataset 파일을 찾을 수 없습니다: {dataset_path}")
            return []

        try:
            with open(dataset_path, encoding='utf-8') as f:
                data = json.load(f)

            # Handle both formats: direct array or object with qa_pairs key
            if isinstance(data, list):
                self.golden_datasets = data
            elif isinstance(data, dict) and 'qa_pairs' in data:
                self.golden_datasets = data['qa_pairs']
            else:
                print("⚠️  Unexpected Golden Dataset format")
                self.golden_datasets = []
                return []

            print(f"✅ Golden Dataset 로드: {len(self.golden_datasets)}개 항목")
            return self.golden_datasets
        except Exception as e:
            logger.error("Golden Dataset 로드 실패: %s", e)
            print(f"❌ Golden Dataset 로드 실패: {str(e)}")
            return []

    def evaluate_with_golden_dataset(
        self,
        agent_fn,
        dataset_path: Optional[str] = None,
        enable_layer2_metrics: bool = True,
        enable_advanced_metrics: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Golden Dataset 기반 자동 평가 파이프라인

        Args:
            agent_fn: 평가할 에이전트 함수 (question을 입력받아 결과 반환)
                      반환값: Dict with keys: answer, tools_used (optional)
            dataset_path: Golden Dataset 파일 경로
            enable_layer2_metrics: Layer 2 메트릭 자동 평가 (Tool Selection 등)
            enable_advanced_metrics: Layer 3 고급 메트릭 (DeepEval, Ragas)
            verbose: 진행 상황 출력

        Returns:
            Dict: 평가 결과 요약
            {
                "total_evaluated": int,
                "layer1_metrics": {...},
                "layer2_metrics": {...},
                "layer3_metrics": {...},
                "pass_fail": {...}
            }

        Example:
            # 간단한 에이전트 함수
            def my_agent(question):
                return {
                    "answer": llm.predict(question),
                    "tools_used": ["search", "calculator"]
                }

            # 자동 평가
            results = monitor.evaluate_with_golden_dataset(
                agent_fn=my_agent,
                dataset_path="sample_dataset.json",
                enable_layer2_metrics=True
            )
        """
        # Golden Dataset 로드
        if not self.golden_datasets or dataset_path:
            self.load_golden_dataset(dataset_path)

        if not self.golden_datasets:
            return {"error": "Golden Dataset을 로드할 수 없습니다"}

        total = len(self.golden_datasets)
        if verbose:
            print(f"🚀 Golden Dataset 기반 자동 평가 시작 ({total}개 항목)")

        # 각 QA 쌍 평가
        for idx, qa_pair in enumerate(self.golden_datasets, 1):
            if verbose:
                print(f"\n[{idx}/{total}] 평가 중: {qa_pair.get('question', '')[:50]}...")

            try:
                # 에이전트 실행
                result = agent_fn(qa_pair['question'])

                # 결과 추출
                if isinstance(result, dict):
                    agent_answer = result.get('answer', str(result))
                    tools_used = result.get('tools_used', [])
                else:
                    agent_answer = str(result)
                    tools_used = []

                # Accuracy 자동 계산 (ground_truth가 있는 경우)
                ground_truth = qa_pair.get('ground_truth', '')
                accuracy_score = 0.0
                if ground_truth:
                    # AccuracyEvaluator를 사용하여 계산
                    accuracy_score = self.accuracy_evaluator._calculate_accuracy(
                        ground_truth,
                        agent_answer,
                        TaskType.QA.value
                    )
                    # 평가 추가
                    self.accuracy_evaluator.add_evaluation(
                        task_id=qa_pair.get('qa_id', f'qa_{idx}'),
                        ground_truth=ground_truth,
                        prediction=agent_answer,
                        task_type=TaskType.QA.value
                    )

                # Layer 1: TaskResult 생성
                task = TaskResult(
                    task_id=qa_pair.get('qa_id', f'qa_{idx}'),
                    task_type=TaskType.QA.value,
                    timestamp=datetime.now(),
                    success=True,
                    completion_score=1.0 if agent_answer else 0.0,
                    accuracy_score=accuracy_score,
                    execution_time=result.get('latency', 0) if isinstance(result, dict) else 0,
                    tokens_used=result.get('token_usage', {"input": 0, "output": 0}) if isinstance(result, dict) else {"input": 0, "output": 0},
                    tool_calls=result.get('tool_calls', []) if isinstance(result, dict) else [],
                    attempts=result.get('retry_count', 0) if isinstance(result, dict) else 0,
                    errors=[],
                    expected_tools=qa_pair.get('expected_tools', []) if enable_layer2_metrics else None
                )

                # 메트릭 자동 계산
                self.record_task(task)

                # Layer 2: Tool Selection 자동 평가
                if enable_layer2_metrics and qa_pair.get('expected_tools'):
                    self.tool_selection_tracker.evaluate_selection(
                        task_id=task.task_id,
                        expected_tools=qa_pair['expected_tools'],
                        actual_tools=tools_used
                    )

                if verbose:
                    print("   ✅ 평가 완료")

            except Exception as e:
                logger.warning("Golden Dataset 평가 항목 오류 (continue): %s", e)
                if verbose:
                    print(f"   ❌ 오류: {str(e)}")
                continue

        # 결과 요약
        if verbose:
            print(f"\n✅ Golden Dataset 평가 완료 ({total}개 항목)")

        # Layer 1 메트릭
        tcr_data = self.tcr_tracker.calculate_tcr()
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        hallucination_data = self.hallucination_detector.get_hallucination_rate()

        # Layer 2 메트릭
        tool_selection_stats = self.tool_selection_tracker.get_accuracy_stats() if enable_layer2_metrics else {}

        # 임계값 비교
        comparison = self.compare_with_thresholds() if self.thresholds else {}

        results = {
            "total_evaluated": total,
            "layer1_metrics": {
                "tcr": tcr_data.get('tcr', 0),
                "accuracy": accuracy_data.get('overall_accuracy', 0) if accuracy_data else 0,
                "hallucination_rate": hallucination_data.get('overall_rate', 0),
            },
            "layer2_metrics": {
                "tool_selection_accuracy": tool_selection_stats.get('avg_accuracy', 0) if tool_selection_stats else 0,
                "tool_selection_f1": tool_selection_stats.get('avg_f1_score', 0) if tool_selection_stats else 0,
            } if enable_layer2_metrics else {},
            "pass_fail": comparison
        }

        if verbose:
            print("\n📊 평가 결과 요약:")
            print(f"   TCR: {results['layer1_metrics']['tcr']:.1f}%")
            print(f"   Accuracy: {results['layer1_metrics']['accuracy']:.1f}%")
            if enable_layer2_metrics and results['layer2_metrics']:
                print(f"   Tool Selection Accuracy: {results['layer2_metrics']['tool_selection_accuracy']:.1f}%")

        return results

    def compare_with_thresholds(self) -> Dict[str, Any]:
        """
        현재 메트릭 값을 임계값과 비교

        Returns:
            Dict: 각 메트릭별 비교 결과
            {
                'metric_name': {
                    'value': 실제 값,
                    'threshold': 임계값,
                    'status': 'pass' | 'fail',
                    'direction': 'higher' | 'lower'  # 높을수록 좋은지, 낮을수록 좋은지
                }
            }
        """
        if not self.thresholds:
            return {}

        comparison = {}

        # TCR
        tcr_data = self.tcr_tracker.calculate_tcr()
        if 'tcr' in self.thresholds:
            comparison['tcr'] = {
                'name': '작업 완료율 (TCR)',
                'value': tcr_data.get('tcr', 0),
                'threshold': self.thresholds['tcr'],
                'status': 'pass' if tcr_data.get('tcr', 0) >= self.thresholds['tcr'] else 'fail',
                'direction': 'higher',
                'unit': '%'
            }

        # Accuracy
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data and 'accuracy' in self.thresholds:
            comparison['accuracy'] = {
                'name': '정확도 (Accuracy)',
                'value': accuracy_data.get('overall_accuracy', 0),
                'threshold': self.thresholds['accuracy'],
                'status': 'pass' if accuracy_data.get('overall_accuracy', 0) >= self.thresholds['accuracy'] else 'fail',
                'direction': 'higher',
                'unit': '%'
            }

        # Hallucination
        hall_data = self.hallucination_detector.get_hallucination_rate()
        if 'hallucination' in self.thresholds:
            comparison['hallucination'] = {
                'name': '환각 발생률 (Hallucination)',
                'value': hall_data.get('overall_rate', 0),
                'threshold': self.thresholds['hallucination'],
                'status': 'pass' if hall_data.get('overall_rate', 0) <= self.thresholds['hallucination'] else 'fail',
                'direction': 'lower',
                'unit': '%'
            }

        # Quality
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and 'quality' in self.thresholds:
            avg_quality = quality_data.get('avg_total_score', 0) * 2  # Convert to 10-point scale
            comparison['quality'] = {
                'name': '응답 품질 (Quality)',
                'value': avg_quality,
                'threshold': self.thresholds['quality'],
                'status': 'pass' if avg_quality >= self.thresholds['quality'] else 'fail',
                'direction': 'higher',
                'unit': '/10'
            }

        # Latency
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data and 'latency' in self.thresholds:
            comparison['latency'] = {
                'name': '응답 시간 (Latency)',
                'value': latency_data.get('p95', 0),
                'threshold': self.thresholds['latency'],
                'status': 'pass' if latency_data.get('p95', 0) <= self.thresholds['latency'] else 'fail',
                'direction': 'lower',
                'unit': 's'
            }

        # Cost per Task
        token_data = self.token_tracker.get_usage_stats()
        if 'cost_per_task' in self.thresholds:
            comparison['cost_per_task'] = {
                'name': '작업당 비용 (Cost per Task)',
                'value': token_data.get('avg_cost_per_task', 0),
                'threshold': self.thresholds['cost_per_task'],
                'status': 'pass' if token_data.get('avg_cost_per_task', 0) <= self.thresholds['cost_per_task'] else 'fail',
                'direction': 'lower',
                'unit': '$'
            }

        # RAG Metrics
        # Faithfulness
        if 'faithfulness' in self.thresholds:
            faithfulness_values = self.rag_metrics.get('faithfulness', [])
            avg_faithfulness = statistics.mean(faithfulness_values) if faithfulness_values else 0.0
            comparison['faithfulness'] = {
                'name': 'Faithfulness',
                'value': avg_faithfulness,
                'threshold': self.thresholds['faithfulness'],
                'status': 'pass' if avg_faithfulness >= self.thresholds['faithfulness'] else 'fail' if faithfulness_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Answer Relevancy
        if 'answer_relevancy' in self.thresholds:
            relevancy_values = self.rag_metrics.get('answer_relevancy', [])
            avg_relevancy = statistics.mean(relevancy_values) if relevancy_values else 0.0
            comparison['answer_relevancy'] = {
                'name': 'Answer Relevancy',
                'value': avg_relevancy,
                'threshold': self.thresholds['answer_relevancy'],
                'status': 'pass' if avg_relevancy >= self.thresholds['answer_relevancy'] else 'fail' if relevancy_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Context Recall
        if 'context_recall' in self.thresholds:
            recall_values = self.rag_metrics.get('context_recall', [])
            avg_recall = statistics.mean(recall_values) if recall_values else 0.0
            comparison['context_recall'] = {
                'name': 'Context Recall',
                'value': avg_recall,
                'threshold': self.thresholds['context_recall'],
                'status': 'pass' if avg_recall >= self.thresholds['context_recall'] else 'fail' if recall_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Context Precision
        if 'context_precision' in self.thresholds:
            precision_values = self.rag_metrics.get('context_precision', [])
            avg_precision = statistics.mean(precision_values) if precision_values else 0.0
            comparison['context_precision'] = {
                'name': 'Context Precision',
                'value': avg_precision,
                'threshold': self.thresholds['context_precision'],
                'status': 'pass' if avg_precision >= self.thresholds['context_precision'] else 'fail' if precision_values else 'pending',
                'direction': 'higher',
                'unit': ''
            }

        # Layer 2: Agentic AI Metrics
        # Tool Selection Accuracy
        tool_stats = self.tool_selection_tracker.get_accuracy_stats()
        if tool_stats and 'tool_selection_accuracy' in self.thresholds:
            comparison['tool_selection_accuracy'] = {
                'name': '도구 선택 정확도 (Tool Selection Accuracy)',
                'value': tool_stats.get('avg_accuracy', 0),
                'threshold': self.thresholds['tool_selection_accuracy'],
                'status': 'pass' if tool_stats.get('avg_accuracy', 0) >= self.thresholds['tool_selection_accuracy'] else 'fail',
                'direction': 'higher',
                'unit': '%',
                'layer': 'Layer 2'
            }

        # Agent Coordination Score
        coord_data = self.agent_coordination_tracker.calculate_coordination_score()
        if coord_data and 'agent_coordination' in self.thresholds:
            # coordination_score는 0-10 척도, threshold도 0-10으로 설정
            comparison['agent_coordination'] = {
                'name': '에이전트 협업 점수 (Agent Coordination)',
                'value': coord_data.get('score', 0),
                'threshold': self.thresholds['agent_coordination'],
                'status': 'pass' if coord_data.get('score', 0) >= self.thresholds['agent_coordination'] else 'fail',
                'direction': 'higher',
                'unit': '/10',
                'layer': 'Layer 2',
                'details': {
                    'success_rate': coord_data.get('success_rate', 0),
                    'total_interactions': coord_data.get('total_interactions', 0),
                    'unique_agents': coord_data.get('unique_agents', 0)
                }
            }

        # Workflow Execution Success Rate
        workflow_stats = self.workflow_tracker.calculate_execution_success_rate()
        if workflow_stats and 'workflow_execution' in self.thresholds:
            comparison['workflow_execution'] = {
                'name': '워크플로우 실행 성공률 (Workflow Execution)',
                'value': workflow_stats.get('step_success_rate', 0),
                'threshold': self.thresholds['workflow_execution'],
                'status': 'pass' if workflow_stats.get('step_success_rate', 0) >= self.thresholds['workflow_execution'] else 'fail',
                'direction': 'higher',
                'unit': '%',
                'layer': 'Layer 2',
                'details': {
                    'total_steps': workflow_stats.get('total_steps', 0),
                    'successful_steps': workflow_stats.get('successful_steps', 0),
                    'task_success_rate': workflow_stats.get('task_success_rate', 0)
                }
            }

        return comparison

    def record_task(self, task_result: TaskResult,
                   ground_truth: Optional[Any] = None,
                   context: Optional[str] = None,
                   request: Optional[str] = None,
                   response: Optional[str] = None,
                   expected_elements: Optional[List[str]] = None):
        """
        Record a complete task execution

        Args:
            task_result: TaskResult from agent execution
            ground_truth: Expected/correct output
            context: Context or retrieved documents for hallucination detection
            request: User request/query
            response: Agent's response/output for hallucination detection
            expected_elements: Expected elements in response
        """
        # Task completion
        self.tcr_tracker.add_task(task_result)
        
        # Accuracy - use TaskResult's accuracy_score
        # Normalize to 0-1 scale: users may pass 0-100 scale values
        _accuracy = task_result.accuracy_score
        if _accuracy is not None and _accuracy > 1.0:
            _accuracy = _accuracy / 100.0
        self.accuracy_evaluator.evaluations.append({
            "task_id": task_result.task_id,
            "task_type": task_result.task_type,
            "accuracy": _accuracy,
            "timestamp": datetime.now()
        })
        
        # Latency
        self.latency_tracker.record_latency(
            task_result.task_id,
            task_result.task_type,
            task_result.execution_time,
            {"total": task_result.execution_time}  # Simplified breakdown
        )
        
        # Token usage
        if task_result.tokens_used:
            self.token_tracker.track_usage(
                task_result.task_id,
                task_result.tokens_used.get("input", 0),
                task_result.tokens_used.get("output", 0),
                task_result.task_type,
                model=task_result.tokens_used.get("model", "default"),  # DQ-150
            )
        
        # Tool calls
        if task_result.tool_calls:
            self.tool_analyzer.analyze_execution(
                task_result.task_id,
                task_result.tool_calls
            )
        
        # Retries — integration(_record_layer2)이 이미 기록했으면 합성 데이터로 중복 기록하지 않음
        if task_result.attempts > 1:
            existing_retry_ids = {a.get('task_id') for a in self.retry_tracker.attempts}
            if task_result.task_id not in existing_retry_ids:
                attempts_log = [
                    {"success": i == task_result.attempts - 1, "duration": 1.0}
                    for i in range(task_result.attempts)
                ]
                self.retry_tracker.track_attempts(task_result.task_id, attempts_log)

        # Agentic AI: Tool Selection Accuracy
        # integration(_record_layer2)이 이미 기록했으면 중복 기록하지 않음
        if task_result.expected_tools and task_result.tool_calls:
            existing_selection_ids = {s.get('task_id') for s in self.tool_selection_tracker.selections}
            if task_result.task_id not in existing_selection_ids:
                actual_tools = []
                for call in task_result.tool_calls:
                    if isinstance(call, str):
                        actual_tools.append(call)
                    elif isinstance(call, dict):
                        tool_name = call.get("tool_name") or call.get("tool") or call.get("name", "unknown")
                        actual_tools.append(tool_name)
                    else:
                        actual_tools.append("unknown")
                self.tool_selection_tracker.evaluate_selection(
                    task_result.task_id,
                    task_result.expected_tools,
                    actual_tools
                )

        # Agentic AI: Agent Coordination (CrewAI)
        if task_result.agent_interactions:
            for interaction in task_result.agent_interactions:
                self.agent_coordination_tracker.track_interaction(
                    task_result.task_id,
                    interaction.get("from_agent", "unknown"),
                    interaction.get("to_agent", "unknown"),
                    interaction.get("type", "communication"),
                    interaction.get("success", True),
                    interaction.get("context")
                )

        # Agentic AI: Workflow Execution (LangChain/LangGraph)
        if task_result.chain_steps:
            for step in task_result.chain_steps:
                self.workflow_tracker.track_step(
                    task_result.task_id,
                    step.get("name", "unknown"),
                    step.get("type", "chain_step"),
                    step.get("success", True),
                    step.get("execution_time", 0.0),
                    task_result.framework or "langchain",
                    step.get("metadata")
                )

        # Layer1: Hallucination Detection (opt-in, rule-based, free)
        if self.enable_hallucination_detection and context and response:
            try:
                # Convert ground_truth to string if needed
                ground_truth_str = None
                if ground_truth is not None:
                    if isinstance(ground_truth, str):
                        ground_truth_str = ground_truth
                    else:
                        ground_truth_str = str(ground_truth)

                self.hallucination_detector.detect_hallucination(
                    task_id=task_result.task_id,
                    response=response,
                    context=context,
                    ground_truth=ground_truth_str
                )
            except Exception as e:
                # Silent fail - don't break the entire evaluation
                import warnings
                warnings.warn(f"Hallucination detection failed for {task_result.task_id}: {e}")

    def record_rag_metrics(
        self,
        faithfulness: Optional[float] = None,
        answer_relevancy: Optional[float] = None,
        context_recall: Optional[float] = None,
        context_precision: Optional[float] = None
    ):
        """
        Record RAG evaluation metrics

        Args:
            faithfulness: Faithfulness score (0-1)
            answer_relevancy: Answer relevancy score (0-1)
            context_recall: Context recall score (0-1)
            context_precision: Context precision score (0-1)
        """
        if faithfulness is not None:
            self.rag_metrics['faithfulness'].append(faithfulness)
        if answer_relevancy is not None:
            self.rag_metrics['answer_relevancy'].append(answer_relevancy)
        if context_recall is not None:
            self.rag_metrics['context_recall'].append(context_recall)
        if context_precision is not None:
            self.rag_metrics['context_precision'].append(context_precision)

    def get_rag_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of RAG metrics

        Returns:
            Dict containing average and statistics for each RAG metric
        """
        summary = {}

        for metric_name, values in self.rag_metrics.items():
            if values:
                mean_val = statistics.mean(values)
                summary[metric_name] = {
                    'mean': mean_val,  # Use 'mean' for consistency with dashboard
                    'average': mean_val,  # Alias for compatibility
                    'min': min(values),
                    'max': max(values),
                    'std': statistics.stdev(values) if len(values) > 1 else 0.0,
                    'count': len(values)
                }
            else:
                summary[metric_name] = {
                    'mean': 0.0,
                    'average': 0.0,
                    'min': 0.0,
                    'max': 0.0,
                    'std': 0.0,
                    'count': 0
                }

        return summary

    def generate_report(self) -> EvaluationReport:
        """Generate comprehensive evaluation report"""

        # Collect security metrics if enabled
        security_metrics = {}
        if self.enable_security_metrics:
            security_metrics = {
                "layer1_security": {
                    "input_security": self.input_sanitizer.get_security_stats() if self.input_sanitizer else {},
                    "output_leakage": self.output_leakage_detector.get_leakage_stats() if self.output_leakage_detector else {},
                    "authorization": self.tool_authorizer.get_compliance_stats() if self.tool_authorizer else {}
                },
                "layer2_security": {
                    "privilege_escalation": self.privilege_escalation_detector.get_escalation_stats() if self.privilege_escalation_detector else {},
                    "attack_detection": self.tool_chain_attack_detector.get_attack_stats() if self.tool_chain_attack_detector else {}
                }
            }

        report = EvaluationReport(
            period="current_session",
            total_tasks=len(self.tcr_tracker.tasks),
            accuracy_metrics={
                "tcr": self.tcr_tracker.calculate_tcr(),
                "accuracy_scores": self.accuracy_evaluator.get_accuracy_scores(),
                "hallucination": self.hallucination_detector.get_hallucination_rate(),
                "quality": self.quality_evaluator.get_quality_metrics()
            },
            efficiency_metrics={
                "latency": self.latency_tracker.get_latency_stats(),
                "tokens": self.token_tracker.get_usage_stats(),
                "tool_efficiency": self.tool_analyzer.get_efficiency_stats(),
                "retries": self.retry_tracker.get_retry_metrics()
            },
            quality_metrics={},
            security_metrics=security_metrics,  # Add security metrics
            alerts=self._generate_alerts(),
            recommendations=self._generate_recommendations(),
            timestamp=datetime.now()
        )

        return report
    
    def _generate_alerts(self) -> List[Dict[str, str]]:
        """Generate alerts for metric violations"""
        alerts = []

        # 임계값 설정 (로드된 임계값 또는 기본값)
        thresholds = self.thresholds if self.thresholds else {
            'tcr': 80.0,
            'accuracy': 70.0,
            'hallucination': 10.0,
            'quality': 6.0,
            'latency': 10.0,
            'cost_per_task': 0.05,
        }

        # Check TCR
        tcr_data = self.tcr_tracker.calculate_tcr()
        tcr_threshold = thresholds.get('tcr', 80.0)
        if tcr_data.get("tcr", 0) < tcr_threshold:
            alerts.append({
                "severity": "high",
                "metric": "작업 완료율 (TCR)",
                "message": f"TCR이 {tcr_data.get('tcr', 0):.1f}%입니다 ({tcr_threshold:.1f}% 기준 미달)",
                "action": "프롬프트와 도구 설정을 검토하세요"
            })
        elif tcr_data.get("tcr", 0) < 90:
            alerts.append({
                "severity": "medium",
                "metric": "작업 완료율 (TCR)",
                "message": f"TCR이 {tcr_data.get('tcr', 0):.1f}%입니다 (90% 기준 미달)",
                "action": "작업 완료율 개선을 고려하세요"
            })

        # Check accuracy
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data:
            overall_acc = accuracy_data.get("overall_accuracy", 100)
            accuracy_threshold = thresholds.get('accuracy', 70.0)
            if overall_acc < accuracy_threshold:
                alerts.append({
                    "severity": "critical",
                    "metric": "정확도 (Accuracy)",
                    "message": f"정확도가 {overall_acc:.1f}%입니다 ({accuracy_threshold:.1f}% 기준 미달)",
                    "action": "즉시 검증 로직을 강화하고 프롬프트를 개선하세요"
                })
            elif overall_acc < 80:
                alerts.append({
                    "severity": "high",
                    "metric": "정확도 (Accuracy)",
                    "message": f"정확도가 {overall_acc:.1f}%입니다 (80% 기준 미달)",
                    "action": "프롬프트 개선과 예시 추가를 고려하세요"
                })

        # Check hallucination rate
        hall_data = self.hallucination_detector.get_hallucination_rate()
        hallucination_threshold = thresholds.get('hallucination', 10.0)
        if hall_data.get("overall_rate", 0) > hallucination_threshold:
            alerts.append({
                "severity": "critical",
                "metric": "환각 발생률 (Hallucination)",
                "message": f"환각 발생률이 {hall_data.get('overall_rate', 0):.1f}%입니다 ({hallucination_threshold:.1f}% 기준 초과)",
                "action": "검증 프로세스와 사실 확인 절차를 즉시 강화하세요"
            })
        elif hall_data.get("overall_rate", 0) > 5:
            alerts.append({
                "severity": "high",
                "metric": "환각 발생률 (Hallucination)",
                "message": f"환각 발생률이 {hall_data.get('overall_rate', 0):.1f}%입니다 (5% 기준 초과)",
                "action": "검증 및 사실 확인 프로세스를 강화하세요"
            })

        # Check quality
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and "avg_total_score" in quality_data:
            # MEDIUM PRIORITY FIX: Only generate alerts when data actually exists
            avg_quality = quality_data["avg_total_score"] * 2  # Convert to 10-point scale
            quality_threshold = thresholds.get('quality', 6.0)
            if avg_quality < quality_threshold:
                alerts.append({
                    "severity": "high",
                    "metric": "응답 품질 (Quality)",
                    "message": f"평균 품질이 {avg_quality:.1f}/10입니다 ({quality_threshold:.1f} 기준 미달)",
                    "action": "응답 완성도, 관련성, 명확성을 개선하세요"
                })
            elif avg_quality < 7.0:
                alerts.append({
                    "severity": "medium",
                    "metric": "응답 품질 (Quality)",
                    "message": f"평균 품질이 {avg_quality:.1f}/10입니다 (7.0 기준 미달)",
                    "action": "응답 품질 개선을 고려하세요"
                })

        # Check latency
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data:
            p95_latency = latency_data.get("p95", 0)
            latency_threshold = thresholds.get('latency', 10.0)
            if p95_latency > latency_threshold:
                alerts.append({
                    "severity": "high",
                    "metric": "응답 시간 (Latency)",
                    "message": f"P95 응답 시간이 {p95_latency:.2f}초입니다 ({latency_threshold:.2f}초 기준 초과)",
                    "action": "성능 최적화와 병렬 처리를 고려하세요"
                })
            elif p95_latency > 5:
                alerts.append({
                    "severity": "medium",
                    "metric": "응답 시간 (Latency)",
                    "message": f"P95 응답 시간이 {p95_latency:.2f}초입니다 (5초 기준 초과)",
                    "action": "응답 시간 최적화를 고려하세요"
                })

        # Check cost
        token_data = self.token_tracker.get_usage_stats()
        cost_per_task = token_data.get("avg_cost_per_task", 0)
        cost_threshold = thresholds.get('cost_per_task', 0.05)
        if cost_per_task > cost_threshold:
            alerts.append({
                "severity": "high",
                "metric": "토큰 비용 (Cost per Task)",
                "message": f"작업당 평균 비용: ${cost_per_task:.4f} (${cost_threshold:.4f} 기준 초과)",
                "action": "토큰 사용 패턴을 검토하고 최적화 기회를 찾으세요"
            })
        elif cost_per_task > 0.03:
            alerts.append({
                "severity": "medium",
                "metric": "토큰 비용 (Cost per Task)",
                "message": f"작업당 평균 비용: ${cost_per_task:.4f} ($0.03 기준 초과)",
                "action": "비용 최적화를 고려하세요"
            })

        # Check tool efficiency
        tool_data = self.tool_analyzer.get_efficiency_stats()
        if tool_data and tool_data.get("total_calls", 0) > 0:
            efficiency = tool_data.get("avg_efficiency_score", 100)
            if efficiency < 60:
                alerts.append({
                    "severity": "high",
                    "metric": "도구 효율성 (Tool Efficiency)",
                    "message": f"도구 효율성이 {efficiency:.1f}%입니다 (60% 기준 미달)",
                    "action": "도구 호출 패턴을 분석하고 중복을 제거하세요"
                })
            elif efficiency < 70:
                alerts.append({
                    "severity": "medium",
                    "metric": "도구 효율성 (Tool Efficiency)",
                    "message": f"도구 효율성이 {efficiency:.1f}%입니다 (70% 기준 미달)",
                    "action": "도구 사용 최적화를 고려하세요"
                })

        # === Security Alerts (Layer 1 & 2) ===
        if self.enable_security_metrics:
            # Input sanitization threats
            if self.input_sanitizer:
                security_data = self.input_sanitizer.get_security_stats()
                if security_data:
                    threat_rate = security_data.get("threat_rate", 0)
                    if threat_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "입력 보안 위협 (Input Security)",
                            "message": f"입력의 {threat_rate:.1f}%에서 보안 위협 탐지 (SQL injection, prompt injection 등)",
                            "action": "즉시 입력 검증 및 살균 프로세스를 강화하세요"
                        })
                    elif threat_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "입력 보안 위협 (Input Security)",
                            "message": f"입력의 {threat_rate:.1f}%에서 보안 위협 탐지",
                            "action": "입력 검증 로직을 검토하고 강화하세요"
                        })

            # Output leakage
            if self.output_leakage_detector:
                leakage_data = self.output_leakage_detector.get_leakage_stats()
                if leakage_data:
                    leakage_rate = leakage_data.get("leakage_rate", 0)
                    critical_leaks = leakage_data.get("critical_severity_count", 0)
                    if critical_leaks > 0:
                        alerts.append({
                            "severity": "critical",
                            "metric": "민감 정보 유출 (Data Leakage)",
                            "message": f"{critical_leaks}개의 출력에서 API 키, 비밀번호 등 중요 정보 유출 탐지",
                            "action": "즉시 출력 필터링을 강화하고 유출된 정보를 회전시키세요"
                        })
                    elif leakage_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "민감 정보 유출 (Data Leakage)",
                            "message": f"출력의 {leakage_rate:.1f}%에서 민감 정보 유출 탐지",
                            "action": "출력 검증 및 마스킹 프로세스를 강화하세요"
                        })

            # Tool authorization violations
            if self.tool_authorizer:
                auth_data = self.tool_authorizer.get_compliance_stats()
                if auth_data:
                    violation_rate = auth_data.get("violation_rate", 0)
                    if violation_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "도구 권한 위반 (Authorization)",
                            "message": f"도구 호출의 {violation_rate:.1f}%가 권한 정책 위반",
                            "action": "즉시 권한 정책을 검토하고 무단 도구 사용을 차단하세요"
                        })
                    elif violation_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "도구 권한 위반 (Authorization)",
                            "message": f"도구 호출의 {violation_rate:.1f}%가 권한 정책 위반",
                            "action": "권한 정책 및 허용 도구 목록을 검토하세요"
                        })

            # Privilege escalation
            if self.privilege_escalation_detector:
                escalation_data = self.privilege_escalation_detector.get_escalation_stats()
                if escalation_data:
                    escalation_rate = escalation_data.get("escalation_rate", 0)
                    high_risk = escalation_data.get("high_risk_events", 0)
                    if high_risk > 0:
                        alerts.append({
                            "severity": "critical",
                            "metric": "권한 상승 탐지 (Privilege Escalation)",
                            "message": f"{high_risk}개의 고위험 권한 상승 패턴 탐지",
                            "action": "즉시 도구 체인을 검토하고 권한 상승 경로를 차단하세요"
                        })
                    elif escalation_rate > 20:
                        alerts.append({
                            "severity": "high",
                            "metric": "권한 상승 탐지 (Privilege Escalation)",
                            "message": f"작업의 {escalation_rate:.1f}%에서 권한 상승 패턴 탐지",
                            "action": "권한 상승 패턴을 분석하고 제한하세요"
                        })

            # Tool chain attacks
            if self.tool_chain_attack_detector:
                attack_data = self.tool_chain_attack_detector.get_attack_stats()
                if attack_data:
                    detection_rate = attack_data.get("detection_rate", 0)
                    if detection_rate > 10:
                        alerts.append({
                            "severity": "critical",
                            "metric": "공격 패턴 탐지 (Attack Detection)",
                            "message": f"도구 체인의 {detection_rate:.1f}%에서 공격 패턴 탐지 (데이터 유출, 측면 이동 등)",
                            "action": "즉시 의심스러운 도구 체인을 검토하고 차단하세요"
                        })
                    elif detection_rate > 5:
                        alerts.append({
                            "severity": "high",
                            "metric": "공격 패턴 탐지 (Attack Detection)",
                            "message": f"도구 체인의 {detection_rate:.1f}%에서 공격 패턴 탐지",
                            "action": "도구 체인 패턴을 분석하고 모니터링을 강화하세요"
                        })

        return alerts
    
    def _generate_recommendations(self) -> List[Dict[str, str]]:
        """Generate improvement recommendations"""
        recommendations = []

        # TCR improvement
        tcr_data = self.tcr_tracker.calculate_tcr()
        if tcr_data.get("tcr", 100) < 90:
            tcr_value = tcr_data.get('tcr', 0)
            gap = 90 - tcr_value
            full_success = tcr_data.get('full_success', 0)
            partial_success = tcr_data.get('partial_success', 0)
            failures = tcr_data.get('failures', 0)

            recommendations.append({
                "area": "작업 완료율 개선",
                "title": f"작업 완료율(TCR)이 목표치 대비 {gap:.1f}%p 낮음",
                "priority": "high" if tcr_value < 80 else "medium",
                "issue": f"현재 TCR {tcr_value:.1f}% (목표: 90% 이상). 전체 성공 {full_success}건, 부분 성공 {partial_success}건, 실패 {failures}건으로 실패 작업의 원인 분석이 필요합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **실패 작업 패턴 분석**: 실패한 {failures}개 작업의 공통 오류 패턴 파악 (타임아웃, API 오류, 입력 검증 실패 등)
2. **프롬프트 명확화**: 작업 지시사항에 구체적인 성공 기준과 출력 형식 명시
3. **작업 분할 전략**: 복잡한 작업을 3-5개의 하위 작업으로 분할하여 단계별 검증 수행
4. **재시도 메커니즘**: 일시적 오류(네트워크, API 제한)에 대한 지수 백오프 재시도 구현
5. **입력 검증 강화**: 작업 실행 전 필수 파라미터와 컨텍스트 검증 로직 추가""",
                "impact": f"""**예상 개선 효과:**
• TCR 목표 달성 시 연간 {failures * 52}건 실패 작업 감소 (주간 {failures}건 기준)
• 사용자 만족도 15-25% 향상 (90% TCR 달성 시)
• 재작업 비용 절감: 실패 작업당 평균 5분 소요 시 주당 {failures * 5}분 절약
• 시스템 신뢰도 향상으로 프로덕션 배포 리스크 감소"""
            })

        # Accuracy improvement
        accuracy_data = self.accuracy_evaluator.get_accuracy_scores()
        if accuracy_data:
            overall_acc = accuracy_data.get("overall_accuracy", 100)
            if overall_acc < 85:
                gap = 85 - overall_acc
                recommendations.append({
                    "area": "정확도 개선",
                    "title": f"정답 정확도가 기준치 대비 {gap:.1f}%p 부족",
                    "priority": "high" if overall_acc < 75 else "medium",
                    "issue": f"현재 정확도 {overall_acc:.1f}% (목표: 85% 이상). 응답의 사실 정확성이 부족하여 사용자에게 잘못된 정보를 제공할 위험이 있습니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **검증 단계 추가**:
   - RAG 기반 작업: 검색된 컨텍스트와 응답의 일치성을 자동 검증하는 후처리 단계 추가
   - 계산/추론 작업: 중간 단계 결과를 명시적으로 출력하고 검증
2. **Few-shot 예시 제공**: 작업 유형별로 3-5개의 고품질 예시를 프롬프트에 포함
3. **프롬프트 구조화**:
   - 단계별 사고 과정(Chain-of-Thought) 유도
   - 최종 답변 전 자기 검증(Self-verification) 단계 추가
4. **Golden Dataset 활용**: 현재 평가 데이터셋을 기반으로 오답 패턴 분석 및 학습 데이터 보강
5. **모델 파라미터 조정**: Temperature 낮추기(0.3-0.5), Top-P 조정으로 일관성 향상""",
                    "impact": f"""**예상 개선 효과:**
• 정확도 85% 달성 시 오답률 {100-overall_acc:.1f}% → 15%로 {(100-overall_acc)-15:.1f}%p 감소
• 사용자 신뢰도 20-30% 향상
• 잘못된 정보로 인한 비즈니스 리스크 {((100-overall_acc)/100)*100:.0f}% 감소
• 사실 확인 및 수정 작업 시간 주당 10-15시간 절감"""
                })

        # Quality improvement
        quality_data = self.quality_evaluator.get_quality_metrics()
        if quality_data and "avg_total_score" in quality_data:
            # MEDIUM PRIORITY FIX: Only generate recommendations when data actually exists
            avg_quality = quality_data["avg_total_score"] * 2
            if avg_quality < 8.0:
                gap = 8.0 - avg_quality
                recommendations.append({
                    "area": "응답 품질 개선",
                    "title": f"응답 품질 점수가 목표치 대비 {gap:.1f}점 낮음 (10점 만점)",
                    "priority": "medium",
                    "issue": f"현재 품질 점수 {avg_quality:.1f}/10 (목표: 8.0 이상). 응답의 완성도, 관련성, 가독성이 사용자 기대 수준에 미치지 못하고 있습니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **응답 구조화 템플릿 적용**:
   - 질문형 작업: 직접적 답변 → 근거 제시 → 추가 정보 순으로 구조화
   - 분석형 작업: 요약 → 상세 분석 → 결론 및 권장사항 순으로 구성
2. **완성도 체크리스트 도입**:
   - 질문의 모든 부분에 답변했는가?
   - 근거나 예시가 충분히 제공되었는가?
   - 결론이 명확하게 제시되었는가?
3. **관련성 강화**:
   - 제공된 컨텍스트나 질문에서 벗어난 내용 제거
   - 핵심 키워드를 응답에 자연스럽게 포함
4. **가독성 개선**:
   - 긴 문장(50자 이상) 분할
   - 불릿 포인트나 번호 매기기 활용
   - 전문 용어 사용 시 간단한 설명 추가
5. **사용자 맞춤화**: 응답 톤과 디테일 수준을 사용자 컨텍스트에 맞게 조정""",
                    "impact": f"""**예상 개선 효과:**
• 품질 점수 8.0 달성 시 사용자 재질문률 30-40% 감소
• 응답 이해도 향상으로 고객 지원 문의 주당 20-30건 감소
• 사용자 세션 시간 15-20% 증가 (만족도 향상)
• 응답 재작성 필요성 {((8.0-avg_quality)/8.0)*100:.0f}% 감소로 운영 효율 증대"""
                })

        # Token optimization
        token_data = self.token_tracker.get_usage_stats()
        if token_data.get("token_distribution", {}).get("input_ratio", 0) > 0.7:
            input_ratio = token_data.get("token_distribution", {}).get("input_ratio", 0) * 100
            total_tokens = token_data.get("total_tokens", 0)
            total_cost = token_data.get("total_cost", 0)

            recommendations.append({
                "area": "토큰 효율성",
                "title": f"입력 토큰 비율이 {input_ratio:.0f}%로 과도하게 높음",
                "priority": "medium",
                "issue": f"전체 토큰 사용량의 {input_ratio:.0f}%가 입력 토큰 (총 {total_tokens:,} 토큰, 비용 ${total_cost:.2f}). 불필요하게 긴 컨텍스트나 반복적인 프롬프트가 비용 증가의 주요 원인입니다.",
                "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **컨텍스트 요약 기법**:
   - 긴 문서는 임베딩 기반 검색 후 상위 3-5개 청크만 사용
   - 대화 히스토리는 최근 5턴으로 제한하고 이전 내용은 요약본 사용
2. **슬라이딩 윈도우 구현**:
   - 장문 처리 시 4096 토큰 윈도우로 분할 처리
   - 중복 컨텍스트 제거 (이전 윈도우에서 이미 처리된 정보)
3. **프롬프트 최적화**:
   - 시스템 프롬프트에서 불필요한 예시나 설명 제거
   - 동적 프롬프트: 작업 복잡도에 따라 프롬프트 길이 조절
4. **캐싱 활용**:
   - 반복되는 시스템 프롬프트나 자주 사용하는 컨텍스트는 API 캐싱 기능 활용 (Claude/OpenAI)
5. **토큰 모니터링**: 작업별 입력 토큰 추적 및 500토큰 이상 작업 우선 최적화""",
                "impact": f"""**예상 개선 효과:**
• 입력 토큰 30% 감소 시 월간 비용 ${total_cost * 0.3 * 30:.2f} 절감 (현재 일간 ${total_cost:.2f} 기준)
• 연간 ${total_cost * 0.3 * 365:.2f} 비용 절감 가능
• 응답 속도 10-15% 향상 (입력 처리 시간 감소)
• 토큰 한도 도달 빈도 감소로 서비스 안정성 향상"""
            })

        # Latency optimization
        latency_data = self.latency_tracker.get_latency_stats()
        if latency_data:
            mean_latency = latency_data.get("mean", 0)
            if mean_latency > 3:
                p95 = latency_data.get("p95", 0)
                recommendations.append({
                    "area": "응답 시간 최적화",
                    "title": f"평균 응답 시간이 {mean_latency:.1f}초로 사용자 기대치 초과",
                    "priority": "high" if mean_latency > 5 else "medium",
                    "issue": f"평균 {mean_latency:.2f}초, P95 {p95:.2f}초 (목표: 3초 이내). 긴 대기 시간은 사용자 이탈률 증가와 직결됩니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **병렬 처리 구현**:
   - 독립적인 도구 호출은 asyncio로 병렬 실행 (2-3배 속도 향상)
   - RAG 검색과 LLM 추론을 파이프라인으로 중첩 처리
2. **캐싱 전략 적용**:
   - 빈번한 질문(FAQ)에 대한 응답 캐싱 (Redis/Memcached)
   - 검색 결과 캐싱: 동일 쿼리 24시간 캐시
   - 임베딩 캐싱: 동일 텍스트 재계산 방지
3. **모델 최적화**:
   - 간단한 작업(분류, 간단한 QA)은 경량 모델 사용 (GPT-3.5, Claude Haiku)
   - 복잡한 작업만 고성능 모델 사용
   - Streaming 응답 활성화로 체감 속도 개선
4. **인프라 최적화**:
   - API 엔드포인트를 지리적으로 가까운 리전 사용
   - 연결 풀링 및 Keep-Alive 설정
5. **타임아웃 설정**: 5초 초과 작업은 중단 후 간소화된 응답 제공""",
                    "impact": f"""**예상 개선 효과:**
• 평균 응답 시간 3초 달성 시 사용자 이탈률 25-35% 감소
• P95를 5초 이하로 개선하면 상위 5% 불만족 사용자 경험 대폭 개선
• 처리량 {(mean_latency/3.0):.1f}배 증가 (동일 리소스로 더 많은 요청 처리)
• 사용자 만족도 조사 점수 0.5-1.0점 향상 (5점 만점)"""
                })

        # Tool efficiency
        tool_data = self.tool_analyzer.get_efficiency_stats()
        if tool_data and tool_data.get("total_calls", 0) > 0:
            redundancy_rate = tool_data.get("redundancy_rate", 0)
            if redundancy_rate > 10:
                total_calls = tool_data.get("total_calls", 0)
                redundant_calls = int(total_calls * redundancy_rate / 100)

                recommendations.append({
                    "area": "도구 호출 최적화",
                    "title": f"중복 도구 호출로 인한 비효율 발생 ({redundancy_rate:.0f}%)",
                    "priority": "medium",
                    "issue": f"총 {total_calls}회 도구 호출 중 약 {redundant_calls}회가 중복 호출 (중복률 {redundancy_rate:.1f}%). 동일한 파라미터로 같은 도구를 반복 호출하여 불필요한 지연과 비용이 발생합니다.",
                    "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **결과 캐싱 메커니즘**:
   - 도구 호출 결과를 메모리 캐시에 저장 (작업 세션 동안 유지)
   - 캐시 키: (도구명, 파라미터 해시) 조합
   - 최대 100개 결과 저장, LRU 정책으로 관리
2. **중복 검사 로직**:
   - 도구 호출 전 최근 5회 호출 이력 확인
   - 동일 파라미터 발견 시 캐시된 결과 재사용
3. **에이전트 로직 개선**:
   - 도구 호출 이력을 프롬프트에 포함하여 LLM이 중복 인지하도록 유도
   - "이전에 이미 검색한 내용입니다" 같은 피드백 제공
4. **배치 처리**:
   - 여러 개의 유사한 도구 호출을 하나로 통합 (예: 10개 문서 검색 → 1회 배치 검색)
5. **도구 호출 분석**: 상위 5개 중복 도구 파악 후 우선 최적화""",
                    "impact": f"""**예상 개선 효과:**
• 중복 호출 {redundancy_rate:.0f}% 제거 시 도구 호출 시간 {redundancy_rate:.0f}% 단축
• API 비용 절감: 외부 API 도구의 경우 월간 수백 달러 절감 가능
• 평균 작업 완료 시간 15-20% 개선
• 시스템 부하 감소로 동시 처리 가능 작업 수 {(100/(100-redundancy_rate)):.1f}배 증가"""
                })

        # Retry optimization
        retry_data = self.retry_tracker.get_retry_metrics()
        if retry_data.get("overall_retry_rate", 0) > 20:
            retry_rate = retry_data.get('overall_retry_rate', 0)
            recommendations.append({
                "area": "에러 처리 개선",
                "title": f"재시도율이 {retry_rate:.0f}%로 과도하게 높음",
                "priority": "high" if retry_rate > 30 else "medium",
                "issue": f"전체 작업의 {retry_rate:.1f}%가 재시도 필요. 높은 재시도율은 근본 원인 해결 없이 임시방편으로 대응하고 있음을 의미하며, 사용자 경험과 시스템 효율을 저하시킵니다.",
                "suggestion": """**즉시 실행 가능한 개선 방안:**
1. **실패 패턴 분석 대시보드 구축**:
   - 재시도 원인별 통계 (API 타임아웃, 파싱 오류, 검증 실패 등)
   - 시간대별, 작업 유형별 실패율 추적
   - 주간 리포트 자동 생성
2. **첫 시도 성공률 개선**:
   - **API 타임아웃**: 타임아웃 설정 10초 → 15초로 증가, 중요 작업 우선순위 부여
   - **파싱 오류**: 응답 형식을 JSON Schema로 명시, Pydantic 검증 추가
   - **검증 실패**: 입력 전처리 단계에서 필수 필드 검증 강화
3. **지능형 재시도 전략**:
   - 일시적 오류(네트워크): 지수 백오프 (1초 → 2초 → 4초)
   - 영구적 오류(잘못된 입력): 재시도 없이 즉시 실패 처리
   - 최대 재시도 횟수 3회로 제한 (무한 루프 방지)
4. **대체 전략 구현**:
   - Primary API 실패 시 Fallback API로 자동 전환
   - 복잡한 작업 실패 시 단순화된 버전으로 재시도
5. **알림 시스템**: 재시도율 30% 초과 시 개발팀에 자동 알림""",
                "impact": f"""**예상 개선 효과:**
• 재시도율 10% 이하로 감소 시 평균 작업 시간 {retry_rate/2:.0f}% 단축
• 사용자 체감 속도 30-40% 향상
• 시스템 리소스 효율 {retry_rate:.0f}% 개선 (중복 처리 감소)
• 안정성 향상으로 프로덕션 신뢰도 증가
• 장애 대응 시간 50% 단축 (명확한 실패 패턴 파악)"""
                })

        return recommendations
    
    def print_report(self, report: EvaluationReport = None):
        """Print formatted report"""
        if report is None:
            report = self.generate_report()
        
        print("\n" + "="*80)
        print("AI AGENT PERFORMANCE EVALUATION REPORT")
        print(f"Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Tasks Evaluated: {report.total_tasks}")
        print("="*80 + "\n")
        
        # Accuracy & Quality Metrics
        print("📊 ACCURACY & QUALITY METRICS")
        print("-" * 80)
        
        tcr = report.accuracy_metrics.get("tcr", {})
        print(f"Task Completion Rate: {tcr.get('tcr', 0):.1f}%")
        print(f"  - Full Success: {tcr.get('full_success', 0)} tasks")
        print(f"  - Partial Success: {tcr.get('partial_success', 0)} tasks")
        print(f"  - Failures: {tcr.get('failures', 0)} tasks")
        print(f"  - Status: {self.tcr_tracker.get_benchmark_status(tcr.get('tcr', 0))}")
        
        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print("\nAccuracy Scores:")
            print(f"  - Overall: {accuracy.get('overall_accuracy', 0):.1f}%")
            print(f"  - Median: {accuracy.get('median_accuracy', 0):.1f}%")
        
        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"\nHallucination Rate: {hall.get('overall_rate', 0):.1f}%")
        
        quality = report.accuracy_metrics.get("quality", {})
        if quality:
            print(f"\nQuality Score: {quality.get('avg_total_score', 0):.1f}/5.0")
        
        # Efficiency Metrics
        print("\n⚡ EFFICIENCY METRICS")
        print("-" * 80)
        
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print("Response Time:")
            print(f"  - Mean: {latency.get('mean', 0):.3f}s")
            print(f"  - Median: {latency.get('median', 0):.3f}s")
            print(f"  - P95: {latency.get('p95', 0):.3f}s")
            print(f"  - P99: {latency.get('p99', 0):.3f}s")
        
        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            print("\nToken Usage:")
            print(f"  - Total Tokens: {tokens.get('total_tokens', 0):,}")
            print(f"  - Avg per Task: {tokens.get('avg_tokens_per_task', 0):.0f}")
            print(f"  - Total Cost: ${tokens.get('total_cost', 0):.4f}")
            print(f"  - Estimated Monthly: ${tokens.get('estimated_monthly_cost', 0):.2f}")
        
        tool_eff = report.efficiency_metrics.get("tool_efficiency", {})
        if tool_eff:
            print("\nTool Call Efficiency:")
            print(f"  - Avg Calls per Task: {tool_eff.get('avg_calls_per_task', 0):.1f}")
            print(f"  - Efficiency Score: {tool_eff.get('avg_efficiency_score', 0):.1f}%")
            print(f"  - Redundancy Rate: {tool_eff.get('redundancy_rate', 0):.1f}%")
        
        retries = report.efficiency_metrics.get("retries", {})
        if retries:
            print("\nRetry Statistics:")
            print(f"  - Retry Rate: {retries.get('overall_retry_rate', 0):.1f}%")
            print(f"  - First Attempt Success: {retries.get('first_attempt_success_rate', 0):.1f}%")
        
        # Alerts
        if report.alerts:
            print("\n🚨 ALERTS")
            print("-" * 80)
            for alert in report.alerts:
                severity_icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "high" else "🟢"
                print(f"{severity_icon} [{alert['severity'].upper()}] {alert['metric']}")
                print(f"   {alert['message']}")
                print(f"   → {alert['action']}\n")
        
        # Recommendations
        if report.recommendations:
            print("💡 RECOMMENDATIONS")
            print("-" * 80)
            for i, rec in enumerate(report.recommendations, 1):
                print(f"{i}. {rec['area']}")
                print(f"   Issue: {rec['issue']}")
                print(f"   Suggestion: {rec['suggestion']}")
                print(f"   Impact: {rec['impact']}\n")

        print("="*80 + "\n")

    def print_summary(self, report: EvaluationReport = None):
        """
        Print quick summary report (documented in user guides)

        Provides a concise overview of key metrics for rapid assessment.
        Ideal for quick checks during development or CI/CD pipelines.

        Args:
            report: Pre-generated report (optional). If None, generates new report.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_summary()  # Quick overview
        """
        if report is None:
            report = self.generate_report()

        print("=" * 80)
        print("         성능 요약 보고서")
        print("=" * 80)
        print()

        # Overall statistics
        print("📊 전체 작업 통계:")
        print(f"  - 총 작업 수: {report.total_tasks}")

        # Calculate success/failure from TCR
        tcr_data = report.accuracy_metrics.get("tcr", {})
        success_count = tcr_data.get("full_success", 0) + tcr_data.get("partial_success", 0)
        failure_count = tcr_data.get("failures", 0)
        success_rate = (success_count / report.total_tasks * 100) if report.total_tasks > 0 else 0

        print(f"  - 성공: {success_count} ({success_rate:.1f}%)")
        print(f"  - 실패: {failure_count} ({100 - success_rate:.1f}%)")
        print()

        # Accuracy metrics
        print("✅ 정확도 메트릭:")
        print(f"  - TCR (Task Completion Rate): {tcr_data.get('tcr', 0):.1f}%")

        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print(f"  - 평균 Accuracy: {accuracy.get('overall_accuracy', 0):.1f}%")

        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"  - Hallucination Rate: {hall.get('overall_rate', 0):.1f}%")
        print()

        # Efficiency metrics
        print("⚡ 효율성 메트릭:")
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print(f"  - 평균 Latency: {latency.get('mean', 0):.2f}초")
            print(f"  - P95 Latency: {latency.get('p95', 0):.2f}초")

        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            avg_tokens = tokens.get('avg_tokens_per_task', 0)
            print(f"  - 평균 Token 사용량: {avg_tokens:.0f} tokens")
            print(f"  - 총 비용: ${tokens.get('total_cost', 0):.4f}")

        print()
        print("=" * 80)
        print()

    def print_detailed_report(self, report: EvaluationReport = None):
        """
        Print comprehensive detailed report (documented in user guides)

        Provides in-depth analysis across all three metric layers:
        - Layer 1: Native Metrics (TCR, Accuracy, Latency, Cost)
        - Layer 2: Agentic AI Metrics (Tool Usage, Agent Coordination, Workflow)
        - Layer 3: Advanced Metrics (DeepEval, Ragas, etc.)

        Args:
            report: Pre-generated report (optional). If None, generates new report.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_detailed_report()  # Full analysis
        """
        if report is None:
            report = self.generate_report()

        print()
        print("=" * 80)
        print("                    상세 성능 분석 보고서")
        print("=" * 80)
        print()

        # ========== Task Statistics ==========
        print("📊 작업 통계")
        print("─" * 80)

        tcr_data = report.accuracy_metrics.get("tcr", {})
        success_count = tcr_data.get("full_success", 0) + tcr_data.get("partial_success", 0)
        failure_count = tcr_data.get("failures", 0)

        print(f"  총 작업 수              : {report.total_tasks}")
        print(f"  성공                    : {success_count} ({success_count/report.total_tasks*100:.1f}%)" if report.total_tasks > 0 else "  성공                    : 0 (0.0%)")
        print(f"  실패                    : {failure_count} ({failure_count/report.total_tasks*100:.1f}%)" if report.total_tasks > 0 else "  실패                    : 0 (0.0%)")

        # Retry statistics
        retries = report.efficiency_metrics.get("retries", {})
        if retries:
            print(f"  평균 재시도 횟수        : {retries.get('avg_attempts_per_task', 0):.1f}")
        print()

        # ========== Layer 1: Native Metrics ==========
        print("✅ Layer 1: Native Metrics (기본 성능 지표)")
        print("─" * 80)

        # Accuracy
        print("  [정확도]")
        print(f"    - TCR                 : {tcr_data.get('tcr', 0):.1f}%")

        accuracy = report.accuracy_metrics.get("accuracy_scores", {})
        if accuracy:
            print(f"    - Accuracy (평균)     : {accuracy.get('overall_accuracy', 0):.1f}%")
            print(f"    - Accuracy (중앙값)   : {accuracy.get('median_accuracy', 0):.1f}%")

        hall = report.accuracy_metrics.get("hallucination", {})
        if hall:
            print(f"    - Hallucination Rate  : {hall.get('overall_rate', 0):.1f}%")
        print()

        # Latency
        latency = report.efficiency_metrics.get("latency", {})
        if latency:
            print("  [지연시간]")
            print(f"    - 평균               : {latency.get('mean', 0):.2f}초")
            print(f"    - 중앙값             : {latency.get('median', 0):.2f}초")
            print(f"    - P95                : {latency.get('p95', 0):.2f}초")
            print(f"    - P99                : {latency.get('p99', 0):.2f}초")
            if 'min' in latency:
                print(f"    - 최소               : {latency.get('min', 0):.2f}초")
            if 'max' in latency:
                print(f"    - 최대               : {latency.get('max', 0):.2f}초")
            print()

        # Tokens
        tokens = report.efficiency_metrics.get("tokens", {})
        if tokens:
            print("  [토큰 사용량]")
            print(f"    - 총 Input Tokens    : {tokens.get('total_input_tokens', 0):,}")
            print(f"    - 총 Output Tokens   : {tokens.get('total_output_tokens', 0):,}")
            print(f"    - 총 Tokens          : {tokens.get('total_tokens', 0):,}")
            print(f"    - 평균 (작업당)      : {tokens.get('avg_tokens_per_task', 0):.0f} tokens")
            print()

        # Cost
        if tokens:
            print("  [비용]")
            print(f"    - 총 비용            : ${tokens.get('total_cost', 0):.4f}")
            print(f"    - 평균 (작업당)      : ${tokens.get('avg_cost_per_task', 0):.4f}")
            if 'estimated_monthly_cost' in tokens:
                print(f"    - 예상 월간 비용     : ${tokens.get('estimated_monthly_cost', 0):.2f}")
            print()

        # ========== Layer 2: Agentic AI Metrics ==========
        print("⚙️  Layer 2: Agentic AI Metrics (에이전트 시스템 지표)")
        print("─" * 80)

        # Tool usage
        tool_eff = report.efficiency_metrics.get("tool_efficiency", {})
        if tool_eff and tool_eff.get("total_calls", 0) > 0:
            print("  [도구 사용]")

            # Tool selection accuracy (if available)
            tool_selection = self.tool_selection_tracker.get_accuracy_stats()
            if tool_selection and tool_selection.get('total_evaluations', 0) > 0:
                print(f"    - Tool Selection Accuracy    : {tool_selection.get('avg_accuracy', 0):.1f}%")

            print(f"    - Tool Efficiency            : {tool_eff.get('avg_efficiency_score', 0):.1f}%")
            print(f"    - 평균 도구 호출 수          : {tool_eff.get('avg_calls_per_task', 0):.1f}")

            if 'redundancy_rate' in tool_eff:
                print(f"    - 중복 호출 비율             : {tool_eff.get('redundancy_rate', 0):.1f}%")
            print()

        # Agent coordination
        coord_stats = self.agent_coordination_tracker.calculate_coordination_score()
        if coord_stats and coord_stats.get('total_interactions', 0) > 0:
            print("  [에이전트 협업]")
            print(f"    - Agent Coordination Score   : {coord_stats.get('score', 0):.2f}")
            print(f"    - 협업 성공률                : {coord_stats.get('success_rate', 0):.1f}%")
            print(f"    - 고유 에이전트 수           : {coord_stats.get('unique_agents', 0)}")
            print(f"    - 총 상호작용 수             : {coord_stats.get('total_interactions', 0)}")
            print()

        # Workflow execution
        workflow_stats = self.workflow_tracker.calculate_execution_success_rate()
        if workflow_stats and workflow_stats.get('total_tasks', 0) > 0:
            print("  [워크플로우 실행]")
            print(f"    - Workflow Success Rate      : {workflow_stats.get('task_success_rate', 0):.1f}%")
            print(f"    - Step Success Rate          : {workflow_stats.get('step_success_rate', 0):.1f}%")
            print(f"    - 평균 단계 수               : {workflow_stats.get('avg_steps_per_task', 0):.1f}")
            print(f"    - 총 실행 태스크 수          : {workflow_stats.get('total_tasks', 0)}")
            print()

        # If no Layer 2 metrics
        if (not tool_eff or tool_eff.get("total_calls", 0) == 0) and \
           (not coord_stats or coord_stats.get('total_interactions', 0) == 0) and \
           (not workflow_stats or workflow_stats.get('total_tasks', 0) == 0):
            print("  (Layer 2 메트릭 데이터 없음)")
            print()

        # ========== Layer 3: Advanced Metrics (if HybridMonitor) ==========
        # Note: This section is a placeholder for advanced metrics
        # Full implementation would require checking if this is a HybridMonitor instance
        has_advanced_metrics = False

        if hasattr(self, 'metric_adapters') and len(getattr(self, 'metric_adapters', {})) > 0:
            print("🎯 Layer 3: Advanced Metrics (고급 평가 지표)")
            print("─" * 80)
            print("  (HybridPerformanceMonitor 사용 시 DeepEval, Ragas 메트릭 표시)")
            print()
            has_advanced_metrics = True

        # ========== Alerts ==========
        if report.alerts:
            print("🚨 경고 및 알림")
            print("─" * 80)
            for alert in report.alerts:
                severity_icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "high" else "🟢"
                print(f"{severity_icon} [{alert['severity'].upper()}] {alert['metric']}")
                print(f"   {alert['message']}")
                print(f"   → {alert['action']}")
                print()

        # ========== Recommendations ==========
        if report.recommendations:
            print("💡 개선 권장사항")
            print("─" * 80)
            for i, rec in enumerate(report.recommendations, 1):
                print(f"{i}. {rec['area']}")
                print(f"   문제: {rec['issue']}")
                print(f"   제안: {rec['suggestion']}")
                print(f"   영향: {rec['impact']}")
                print()

        print("=" * 80)
        print()

    def print_metric_breakdown(self, task_id: str = None, verbose: bool = True):
        """
        Print detailed calculation breakdown for transparency (NEW)

        Shows how each metric is calculated with intermediate values,
        providing full transparency into the evaluation process.

        Args:
            task_id: Specific task ID to analyze. If None, shows aggregate breakdown.
            verbose: If True, shows step-by-step calculations.

        Example:
            >>> monitor = PerformanceMonitor()
            >>> # ... record tasks ...
            >>> monitor.print_metric_breakdown("task_001", verbose=True)
        """
        print()
        print("=" * 80)
        print("        평가 지표 계산 과정 (Metric Calculation Breakdown)")
        print("=" * 80)
        print()

        if task_id:
            # Find specific task
            task = next((t for t in self.tcr_tracker.tasks if t.task_id == task_id), None)
            if not task:
                print(f"❌ Task ID '{task_id}'를 찾을 수 없습니다.")
                return

            print(f"🔍 Task ID: {task_id}")
            print(f"   Task Type: {task.task_type}")
            print(f"   Timestamp: {task.timestamp}")
            print()

            # ========== TCR Calculation ==========
            print("📊 1. Task Completion Rate (TCR) 계산")
            print("─" * 80)
            print(f"   Completion Score: {task.completion_score:.3f}")
            print()
            if verbose:
                print("   📝 계산 방법:")
                print("      - success=True이고 completion_score >= 0.7  → Full Success")
                print("      - success=True이고 completion_score < 0.7   → Partial Success")
                print("      - success=False                              → Failure")
                print()
                if task.success and task.completion_score >= 0.7:
                    print("   ✅ 이 작업: Full Success (completion_score >= 0.7)")
                elif task.success:
                    print("   ⚠️  이 작업: Partial Success (0 < completion_score < 0.7)")
                else:
                    print("   ❌ 이 작업: Failure (success=False)")
                print()

            # ========== Accuracy Calculation ==========
            print("📊 2. Accuracy Score 계산")
            print("─" * 80)
            print(f"   Accuracy Score: {task.accuracy_score:.3f}")
            print()
            if verbose:
                print("   📝 계산 방법 (4가지 유사도 메트릭 조합):")
                print("      1. Token Overlap Ratio (40% 가중치)")
                print("      2. Jaccard Similarity   (30% 가중치)")
                print("      3. LCS Similarity       (20% 가중치)")
                print("      4. Character Similarity (10% 가중치)")
                print()
                print("   ℹ️  이 점수는 응답과 정답(ground truth) 간 유사도를 측정합니다.")
                print()

            # ========== Latency ==========
            print("📊 3. Latency (응답 시간)")
            print("─" * 80)
            print(f"   Execution Time: {task.execution_time:.3f}초")
            print()

            # ========== Token Usage ==========
            print("📊 4. Token Usage & Cost")
            print("─" * 80)
            print(f"   Input Tokens:  {task.tokens_used.get('input', 0):,}")
            print(f"   Output Tokens: {task.tokens_used.get('output', 0):,}")
            print(f"   Total Tokens:  {task.tokens_used.get('total', 0):,}")
            print()
            if verbose:
                input_cost = task.tokens_used.get('input', 0) / 1_000_000 * self.token_tracker.pricing['input']
                output_cost = task.tokens_used.get('output', 0) / 1_000_000 * self.token_tracker.pricing['output']
                total_cost = input_cost + output_cost
                print("   📝 비용 계산:")
                print(f"      Input Cost  = {task.tokens_used.get('input', 0):,} tokens × ${self.token_tracker.pricing['input']}/1M = ${input_cost:.6f}")
                print(f"      Output Cost = {task.tokens_used.get('output', 0):,} tokens × ${self.token_tracker.pricing['output']}/1M = ${output_cost:.6f}")
                print(f"      Total Cost  = ${total_cost:.6f}")
                print()

            # ========== Tool Calls ==========
            if task.tool_calls:
                print("📊 5. Tool Calls")
                print("─" * 80)
                print(f"   Total Tool Calls: {len(task.tool_calls)}")
                for i, tool_call in enumerate(task.tool_calls, 1):
                    if isinstance(tool_call, str):
                        tool_name = tool_call
                    elif isinstance(tool_call, dict):
                        tool_name = tool_call.get('tool', 'unknown')
                    else:
                        tool_name = 'unknown'
                    print(f"   {i}. {tool_name}")
                print()

            # ========== Retry/Attempts ==========
            if task.attempts > 1:
                print("📊 6. Retry/Correction")
                print("─" * 80)
                print(f"   Attempts: {task.attempts}")
                print(f"   Retries:  {task.attempts - 1}")
                if verbose:
                    print()
                    print("   📝 Retry 효율성 계산:")
                    print(f"      최종 성공 여부: {'✅ 성공' if task.success else '❌ 실패'}")
                    print("      Retry Efficiency = 최종 성공 / 총 시도 횟수")
                print()

        else:
            # Aggregate breakdown
            print("📊 전체 작업 통합 분석")
            print()

            # TCR Breakdown
            print("1️⃣ Task Completion Rate (TCR)")
            print("─" * 80)
            tcr_result = self.tcr_tracker.calculate_tcr()
            total = tcr_result['total_tasks']
            full_success = sum(1 for t in self.tcr_tracker.tasks if t.success and t.completion_score >= 0.7)
            partial_success = sum(1 for t in self.tcr_tracker.tasks if t.success and t.completion_score < 0.7)
            failures = sum(1 for t in self.tcr_tracker.tasks if not t.success)

            print(f"   Total Tasks: {total}")
            print(f"   Full Success: {full_success} ({full_success/total*100:.1f}%)" if total > 0 else "   Full Success: 0 (0.0%)")
            print(f"   Partial Success: {partial_success} ({partial_success/total*100:.1f}%)" if total > 0 else "   Partial Success: 0 (0.0%)")
            print(f"   Failures: {failures} ({failures/total*100:.1f}%)" if total > 0 else "   Failures: 0 (0.0%)")
            print()
            if verbose:
                print("   📝 TCR 계산식:")
                print("      TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100")
                weighted_success = (full_success * 1.0 + partial_success * 0.5)
                tcr_calculated = (weighted_success / total * 100) if total > 0 else 0
                print(f"      TCR = ({full_success} × 1.0 + {partial_success} × 0.5) / {total} × 100")
                print(f"      TCR = {tcr_calculated:.2f}%")
                print()

            # Accuracy Breakdown
            print("2️⃣ Accuracy Score")
            print("─" * 80)
            accuracy_stats = self.accuracy_evaluator.get_accuracy_metrics()
            if accuracy_stats and 'scores' in accuracy_stats:
                scores = accuracy_stats['scores']
                print(f"   Total Evaluations: {len(scores)}")
                print(f"   Overall Accuracy: {accuracy_stats.get('overall_accuracy', 0):.1f}%")
                print(f"   Median Accuracy: {accuracy_stats.get('median_accuracy', 0):.1f}%")
                print()
                if verbose:
                    print("   📝 계산 방법:")
                    print("      - 각 작업의 accuracy_score를 수집")
                    print("      - Overall = 평균값")
                    print("      - Median = 중앙값")
                    print()

            # Latency Breakdown
            print("3️⃣ Latency Statistics")
            print("─" * 80)
            latency_stats = self.latency_tracker.get_latency_stats()
            if latency_stats:
                print(f"   Mean: {latency_stats.get('mean', 0):.3f}초")
                print(f"   Median: {latency_stats.get('median', 0):.3f}초")
                print(f"   P95: {latency_stats.get('p95', 0):.3f}초")
                print(f"   P99: {latency_stats.get('p99', 0):.3f}초")
                print()
                if verbose:
                    print("   📝 백분위수(Percentile) 계산:")
                    print("      - P95: 전체 작업 중 95%가 이 시간 이내에 완료")
                    print("      - P99: 전체 작업 중 99%가 이 시간 이내에 완료")
                    print()

            # Token & Cost Breakdown
            print("4️⃣ Token Usage & Cost")
            print("─" * 80)
            token_stats = self.token_tracker.get_usage_stats()
            if token_stats:
                print(f"   Total Input Tokens: {token_stats.get('total_input_tokens', 0):,}")
                print(f"   Total Output Tokens: {token_stats.get('total_output_tokens', 0):,}")
                print(f"   Total Tokens: {token_stats.get('total_tokens', 0):,}")
                print(f"   Total Cost: ${token_stats.get('total_cost', 0):.4f}")
                print()
                if verbose:
                    print("   📝 비용 계산식:")
                    print(f"      Input Cost  = {token_stats.get('total_input_tokens', 0):,} × ${self.token_tracker.pricing['input']}/1M")
                    print(f"      Output Cost = {token_stats.get('total_output_tokens', 0):,} × ${self.token_tracker.pricing['output']}/1M")
                    print("      Total Cost  = Input Cost + Output Cost")
                    print()

        print("=" * 80)
        print()
        print("ℹ️  투명성 노트: 이 분석은 평가 과정의 완전한 투명성을 제공합니다.")
        print("   모든 계산 로직은 오픈소스로 공개되어 있으며, 필요 시 수정 가능합니다.")
        print()

    def explain_metric(self, metric_name: str):
        """
        Explain how a specific metric is calculated (NEW)

        Provides detailed explanation of metric calculation methodology,
        formulas, and interpretation guidelines.

        Args:
            metric_name: Metric to explain (tcr, accuracy, latency, cost, etc.)

        Example:
            >>> monitor = PerformanceMonitor()
            >>> monitor.explain_metric("tcr")
            >>> monitor.explain_metric("accuracy")
        """
        explanations = {
            "tcr": {
                "name": "Task Completion Rate (TCR)",
                "purpose": "작업의 완료 여부와 완료 품질을 측정합니다.",
                "calculation": """
    1. 각 작업을 3가지 범주로 분류:
       - Full Success: success=True and completion_score >= 0.7
       - Partial Success: success=True and completion_score < 0.7
       - Failure: success=False

    2. 가중 평균 계산:
       TCR = (Full Success × 1.0 + Partial Success × 0.5) / Total Tasks × 100
                """,
                "interpretation": """
    - 95% 이상: 우수 (Industry Benchmark)
    - 90-95%: 양호
    - 80-90%: 개선 필요
    - 80% 미만: 긴급 개선 필요
                """,
                "transparency_notes": """
    - completion_score는 응답 길이, 에러 여부, ground truth 유사도 기반
    - 기준값(0.7)은 조정 가능
    - 전체 계산 로직은 TaskCompletionTracker.calculate_tcr()에 공개
                """
            },
            "accuracy": {
                "name": "Accuracy Score",
                "purpose": "Agent 응답이 정답(ground truth)과 얼마나 유사한지 측정합니다.",
                "calculation": """
    4가지 유사도 메트릭 조합:

    1. Token Overlap Ratio (40% 가중치)
       - 공통 단어 수 / 최대 단어 수

    2. Jaccard Similarity (30% 가중치)
       - 교집합 크기 / 합집합 크기

    3. Longest Common Subsequence (20% 가중치)
       - 최장 공통 부분 수열 길이 / 최대 길이

    4. Character-level Similarity (10% 가중치)
       - Levenshtein distance 기반

    최종 점수 = Σ(각 메트릭 × 가중치)
                """,
                "interpretation": """
    - 90% 이상: 매우 정확
    - 80-90%: 정확
    - 70-80%: 보통
    - 70% 미만: 부정확
                """,
                "transparency_notes": """
    - 각 유사도 알고리즘은 taskresult_helpers.py에 구현
    - 가중치는 연구 기반 최적화된 값
    - 도메인별로 가중치 조정 가능
                """
            },
            "latency": {
                "name": "Latency (응답 시간)",
                "purpose": "Agent가 작업을 완료하는 데 걸린 시간을 측정합니다.",
                "calculation": """
    1. 각 작업의 execution_time 수집
    2. 통계 계산:
       - Mean (평균): Σ(시간) / 개수
       - Median (중앙값): 정렬 후 중간 값
       - P95: 하위 95% 지점의 값
       - P99: 하위 99% 지점의 값
                """,
                "interpretation": """
    P95 Latency 기준:
    - 1초 미만: 매우 빠름
    - 1-3초: 빠름 (대부분의 QA 작업)
    - 3-5초: 보통
    - 5-10초: 느림 (개선 권장)
    - 10초 이상: 매우 느림 (즉시 개선)
                """,
                "transparency_notes": """
    - P95/P99는 이상치(outlier)를 고려한 안정적인 지표
    - 평균만으로는 실제 사용자 경험을 대표하기 어려움
    - 계산 로직: LatencyTracker.get_latency_stats()
                """
            },
            "cost": {
                "name": "Token Cost (비용)",
                "purpose": "LLM API 사용 비용을 계산합니다.",
                "calculation": """
    1. Input Cost:
       Input Cost = (Total Input Tokens / 1,000,000) × Input Price

    2. Output Cost:
       Output Cost = (Total Output Tokens / 1,000,000) × Output Price

    3. Total Cost:
       Total Cost = Input Cost + Output Cost
                """,
                "interpretation": """
    작업당 평균 비용 기준:
    - $0.001 미만: 매우 효율적
    - $0.001-$0.01: 효율적
    - $0.01-$0.05: 보통
    - $0.05 이상: 비효율적 (최적화 필요)
                """,
                "transparency_notes": """
    - 가격은 초기화 시 설정 (기본: GPT-4 Turbo 가격)
    - 실제 가격은 OpenAI pricing 페이지 참조
    - 계산 로직: TokenEconomyTracker.get_usage_stats()
                """
            },
            "hallucination": {
                "name": "Hallucination Rate (환각 발생률)",
                "purpose": "Agent가 사실이 아닌 정보를 생성하는 비율을 측정합니다.",
                "calculation": """
    1. 각 응답을 분석하여 환각 여부 판정:
       - Context와 충돌하는 주장
       - Ground truth와 완전히 다른 정보
       - 사실이 아닌 추가 정보

    2. Hallucination Rate 계산:
       Rate = (환각 발생 작업 수 / 총 작업 수) × 100
                """,
                "interpretation": """
    - 0-2%: 우수
    - 2-5%: 양호
    - 5-10%: 개선 필요
    - 10% 이상: 심각 (즉시 개선)
                """,
                "transparency_notes": """
    - 환각 탐지 로직: HallucinationDetector.detect_hallucination()
    - Context 기반 검증
    - 필요시 사용자 정의 탐지 로직 추가 가능
                """
            }
        }

        metric_name = metric_name.lower()

        if metric_name not in explanations:
            print(f"❌ 알 수 없는 메트릭: '{metric_name}'")
            print()
            print("사용 가능한 메트릭:")
            for key in explanations.keys():
                print(f"  - {key}")
            return

        info = explanations[metric_name]

        print()
        print("=" * 80)
        print(f"   📖 {info['name']} - 상세 설명")
        print("=" * 80)
        print()

        print("🎯 목적")
        print("─" * 80)
        print(info['purpose'])
        print()

        print("🧮 계산 방법")
        print("─" * 80)
        print(info['calculation'])
        print()

        print("📊 해석 가이드")
        print("─" * 80)
        print(info['interpretation'])
        print()

        print("🔍 투명성 노트")
        print("─" * 80)
        print(info['transparency_notes'])
        print()

        print("=" * 80)
        print()

    def export_report(self, filename: str, format: str = "json"):
        """Export report to file"""
        report = self.generate_report()
        
        if format == "json":
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(asdict(report), f, indent=2, default=str)
        elif format == "csv":
            # Export comprehensive metrics to CSV
            data = {
                "Metric": [],
                "Value": [],
                "Unit": []
            }

            # Layer 1 Metrics
            # TCR
            tcr = report.accuracy_metrics.get("tcr", {})
            data["Metric"].append("Task Completion Rate (TCR)")
            data["Value"].append(f"{tcr.get('tcr', 0):.2f}")
            data["Unit"].append("%")

            # Accuracy
            accuracy_scores = report.accuracy_metrics.get("accuracy_scores", {})
            data["Metric"].append("Overall Accuracy")
            data["Value"].append(f"{accuracy_scores.get('overall_accuracy', 0):.2f}")
            data["Unit"].append("%")

            # Hallucination Rate
            hall_data = self.hallucination_detector.get_hallucination_rate()
            data["Metric"].append("Hallucination Rate")
            data["Value"].append(f"{hall_data.get('overall_rate', 0):.2f}")
            data["Unit"].append("%")

            # Quality Score
            quality_data = self.quality_evaluator.get_quality_metrics()
            if quality_data:
                avg_quality = quality_data.get('avg_total_score', 0) * 2  # Convert to 10-point scale
                data["Metric"].append("Response Quality")
                data["Value"].append(f"{avg_quality:.2f}")
                data["Unit"].append("/10")

            # Latency
            latency_stats = report.efficiency_metrics.get("latency", {})
            data["Metric"].append("Average Latency")
            data["Value"].append(f"{latency_stats.get('mean', 0):.3f}")
            data["Unit"].append("s")

            data["Metric"].append("P95 Latency")
            data["Value"].append(f"{latency_stats.get('p95', 0):.3f}")
            data["Unit"].append("s")

            # Token Usage & Cost
            token_stats = report.efficiency_metrics.get("tokens", {})
            data["Metric"].append("Total Input Tokens")
            data["Value"].append(f"{token_stats.get('total_input_tokens', 0)}")
            data["Unit"].append("tokens")

            data["Metric"].append("Total Output Tokens")
            data["Value"].append(f"{token_stats.get('total_output_tokens', 0)}")
            data["Unit"].append("tokens")

            data["Metric"].append("Total Cost")
            data["Value"].append(f"{token_stats.get('total_cost', 0):.4f}")
            data["Unit"].append("$")

            data["Metric"].append("Avg Cost per Task")
            data["Value"].append(f"{token_stats.get('avg_cost_per_task', 0):.4f}")
            data["Unit"].append("$")

            # Layer 2 Metrics (if available)
            tool_stats = self.tool_selection_tracker.get_accuracy_stats()
            if tool_stats:
                data["Metric"].append("Tool Selection Accuracy")
                data["Value"].append(f"{tool_stats.get('avg_accuracy', 0):.2f}")
                data["Unit"].append("%")

                data["Metric"].append("Tool Selection F1 Score")
                data["Value"].append(f"{tool_stats.get('avg_f1_score', 0):.2f}")
                data["Unit"].append("%")

            # RAG Metrics (Layer 3)
            rag_summary = self.get_rag_metrics_summary()
            for metric_name, metric_data in rag_summary.items():
                if metric_data['count'] > 0:
                    display_name = metric_name.replace('_', ' ').title()
                    data["Metric"].append(display_name)
                    data["Value"].append(f"{metric_data['mean']:.3f}")
                    data["Unit"].append("score")

            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
        
        print(f"Report exported to {filename}")

    def save_to_file(self, filename: str = "performance_data.json"):
        """
        Save all performance data to a JSON file

        Automatically includes:
        - Task data
        - Full report data (accuracy, efficiency, quality, security metrics)
        - All evaluator data (quality, hallucination, security, etc.)
        - RAG metrics
        - Completion tracker data

        Args:
            filename: Output filename (relative paths are automatically resolved to Dashboard data directory)

        Note:
            Always includes full report data for Dashboard compatibility.
        """
        import os

        # ⚡ Lazy initialization: 디렉토리를 실제 저장 시점에 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Zero Configuration: 자동으로 올바른 위치에 저장
        if not os.path.isabs(filename):
            filename = str(self.output_dir / filename)

        data = {
            "tasks": [asdict(task) for task in self.tcr_tracker.tasks],
            "pricing": self.token_tracker.pricing,
            "timestamp": datetime.now().isoformat(),
            # Save evaluator data
            "evaluators": {
                "quality": {
                    "evaluations": self.quality_evaluator.evaluations
                },
                "hallucination": {
                    "detections": self.hallucination_detector.detections
                },
                "retry": {
                    "attempts": self.retry_tracker.attempts
                },
                "tool_calls": {
                    "executions": self.tool_analyzer.executions
                },
                "tool_selection": {
                    "selections": self.tool_selection_tracker.selections
                },
                "agent_coordination": {
                    "interactions": self.agent_coordination_tracker.interactions
                },
                "workflow": {
                    "executions": self.workflow_tracker.executions
                }
            },
            # Save RAG metrics
            "rag_metrics": self.rag_metrics,
            # Save advanced metrics summary (DeepEval, Ragas 등)
            "advanced_metrics_summary": getattr(self, '_advanced_metrics_summary', {})
        }

        # Auto-add security evaluators if enabled
        if hasattr(self, 'input_sanitizer') and self.input_sanitizer is not None:
            security_data = self._get_security_evaluator_data()
            if security_data:  # Only add if there's actually security data
                data["evaluators"]["security"] = security_data

        # Always add full report data (for Dashboard compatibility)
        self._append_report_data(data)

        # Convert datetime objects and enum values to strings
        for task in data["tasks"]:
            if isinstance(task.get("timestamp"), datetime):
                task["timestamp"] = task["timestamp"].isoformat()
            tt = task.get("task_type")
            if hasattr(tt, "value"):
                task["task_type"] = tt.value

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        print(f"✅ Performance data saved to {filename}")

        # Auto transparency: generate metric traces + audit logs
        if self.transparency_manager:
            try:
                self._auto_transparency_on_save(filename)
            except Exception as e:
                logger.warning("투명성 데이터 생성 실패 (평가 결과는 정상 저장됨): %s", e)

        # 레지스트리에 자동 등록
        try:
            from ..utils.data_registry import DataRegistry

            abs_path = os.path.abspath(filename)

            # 메타데이터 수집
            metadata = {
                "total_tasks": len(self.tcr_tracker.tasks),
                "framework": None,
                "task_types": []
            }

            # Framework 정보 (첫 번째 task에서)
            if self.tcr_tracker.tasks:
                first_task = self.tcr_tracker.tasks[0]
                metadata["framework"] = getattr(first_task, "framework", None)

                # Task types 수집 (JSON 직렬화를 위해 문자열로 변환)
                task_types = set(task.task_type for task in self.tcr_tracker.tasks)
                metadata["task_types"] = [str(tt.value) if hasattr(tt, 'value') else str(tt) for tt in task_types]

            # 레지스트리 등록
            success = DataRegistry.register_data_file(
                filepath=abs_path,
                metadata=metadata
            )

            if success:
                print("📋 Dashboard 레지스트리에 자동 등록됨 (~/.agent_evaluator/registry.json)")

        except Exception as e:
            # 레지스트리 등록 실패해도 데이터 저장은 성공한 것으로 처리
            logger.warning("레지스트리 등록 실패 (데이터는 정상 저장됨): %s", e)
            print(f"⚠️  레지스트리 등록 실패 (데이터는 정상 저장됨): {e}")

        return filename

    def _auto_transparency_on_save(self, filename: str):
        """
        Auto-generate transparency data on save_to_file().
        Produces:
          - 5 metric traces (TCR, Accuracy, Latency, Token Economy, Quality)
          - 2 audit log entries (report_generated, file_saved)
        Called only when enable_transparency=True.
        """
        from ..utils.transparency_manager import TestStepStatus

        tm = self.transparency_manager
        tasks = self.tcr_tracker.tasks
        n = len(tasks)
        if n == 0:
            return

        # ── 1. TCR trace ────────────────────────────────────────────────────
        tcr_data = self.tcr_tracker.calculate_tcr()
        success_count = sum(1 for t in tasks if t.success)
        tcr_val = round(tcr_data.get("tcr", 0), 2)

        tid = tm.start_metric_calculation("tcr", "basic")
        tm.add_calculation_step(
            tid, "collect_tasks", f"{n}개 태스크 수집",
            {"total_tasks": n},
            {"tasks_collected": n},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid, "count_successes", f"성공 {success_count} / 전체 {n}",
            {"total": n, "success": success_count},
            {"success_count": success_count, "fail_count": n - success_count},
            TestStepStatus.SUCCESS,
        )
        weighted = round(sum(t.completion_score for t in tasks), 2)
        tm.add_calculation_step(
            tid, "calculate_tcr", f"TCR = Σ(completion_score)/{n} × 100 = {weighted}/{n} × 100 = {tcr_val}%",
            {"weighted_completions": weighted, "total": n},
            {"tcr": tcr_val},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid, final_value=tcr_val,
            metadata={"formula": "Σ(completion_score) / total_tasks × 100", "task_count": n},
        )

        # ── 2. Accuracy trace ───────────────────────────────────────────────
        acc_data = self.accuracy_evaluator.get_accuracy_scores()
        overall_acc = round(acc_data.get("overall_accuracy", 0), 4)
        scores = [e.get("accuracy", 0) for e in self.accuracy_evaluator.evaluations]

        tid2 = tm.start_metric_calculation("accuracy", "quality")
        tm.add_calculation_step(
            tid2, "collect_scores", f"{len(scores)}개 태스크 정확도 점수 수집",
            {"evaluations": len(scores)},
            {"score_min": round(min(scores), 3) if scores else 0,
             "score_max": round(max(scores), 3) if scores else 0},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid2, "weighted_aggregate",
            "Token Overlap 40% + Jaccard 30% + LCS 20% + Char 10% 가중 평균",
            {"weights": {"token_overlap": 0.4, "jaccard": 0.3, "lcs": 0.2, "char": 0.1}},
            {"overall_accuracy": overall_acc},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid2, final_value=overall_acc,
            metadata={"method": "weighted_average", "task_count": len(scores)},
        )

        # ── 3. Latency trace ────────────────────────────────────────────────
        lat_data = self.latency_tracker.get_latency_stats()
        mean_lat = round(lat_data.get("mean", 0), 3)
        p95_lat = round(lat_data.get("p95", 0), 3)
        times = [t.execution_time for t in tasks]

        tid3 = tm.start_metric_calculation("latency", "performance")
        tm.add_calculation_step(
            tid3, "collect_times", f"{len(times)}개 실행 시간 수집",
            {"task_count": len(times)},
            {"min_s": round(min(times), 3) if times else 0,
             "max_s": round(max(times), 3) if times else 0},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid3, "percentiles", "평균·p50·p95·p99 백분위수 계산",
            {"values_count": len(times)},
            {"mean_s": mean_lat, "p95_s": p95_lat},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid3, final_value=mean_lat,
            metadata={"unit": "seconds", "p95": p95_lat},
        )

        # ── 4. Token Economy trace ──────────────────────────────────────────
        tok_data = self.token_tracker.get_usage_stats()
        total_tokens = tok_data.get("total_tokens", 0)
        total_cost = round(tok_data.get("total_cost", 0.0), 6)

        tid4 = tm.start_metric_calculation("token_economy", "performance")
        tm.add_calculation_step(
            tid4, "sum_tokens", "태스크별 input/output 토큰 합산",
            {"task_count": n},
            {"total_input": tok_data.get("total_input_tokens", 0),
             "total_output": tok_data.get("total_output_tokens", 0),
             "total_tokens": total_tokens},
            TestStepStatus.SUCCESS,
        )
        tm.add_calculation_step(
            tid4, "calculate_cost", "총 비용 = Σ(토큰 × 단가)",
            {"total_tokens": total_tokens},
            {"total_cost_usd": total_cost,
             "avg_cost_per_task": round(total_cost / n, 6) if n else 0},
            TestStepStatus.SUCCESS,
        )
        tm.complete_metric_calculation(
            tid4, final_value=total_tokens,
            metadata={"total_cost_usd": total_cost},
        )

        # ── 5. Quality trace (only when quality evaluations exist) ──────────
        q_evals = self.quality_evaluator.evaluations
        if q_evals:
            q_data = self.quality_evaluator.get_quality_metrics()
            avg_q = round(q_data.get("avg_total_score", 0), 4)
            dim_scores = q_data.get("dimension_averages", {})

            tid5 = tm.start_metric_calculation("response_quality", "quality")
            tm.add_calculation_step(
                tid5, "collect_evaluations", f"{len(q_evals)}개 응답 품질 평가 수집",
                {"evaluations": len(q_evals)},
                {"dimension_count": len(dim_scores)},
                TestStepStatus.SUCCESS,
            )
            tm.add_calculation_step(
                tid5, "dimension_scoring",
                "5개 차원 채점 (relevance · completeness · accuracy · clarity · usefulness)",
                {"dimensions": list(dim_scores.keys())},
                {"avg_dimension_scores": {k: round(v, 3) for k, v in dim_scores.items()}},
                TestStepStatus.SUCCESS,
            )
            tm.add_calculation_step(
                tid5, "aggregate_quality", f"종합 품질 점수 = {avg_q}",
                {"method": "weighted_dimension_average"},
                {"avg_quality_score": avg_q},
                TestStepStatus.SUCCESS,
            )
            tm.complete_metric_calculation(
                tid5, final_value=avg_q,
                metadata={"scale": "0-5", "grade_distribution": q_data.get("grade_distribution", {})},
            )

        # ── Audit: report_generated ─────────────────────────────────────────
        tm.log_event(
            event_type="lifecycle",
            user="system",
            action="report_generated",
            target_type="report",
            target_id="evaluation_report",
            details={
                "total_tasks": n,
                "tcr": tcr_val,
                "overall_accuracy": overall_acc,
                "mean_latency_s": mean_lat,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
            },
            success=True,
        )

        # ── Audit: file_saved ───────────────────────────────────────────────
        import os as _os
        tm.log_event(
            event_type="lifecycle",
            user="system",
            action="file_saved",
            target_type="file",
            target_id=_os.path.basename(filename),
            details={
                "filepath": filename,
                "total_tasks": n,
                "file_size_bytes": _os.path.getsize(filename) if _os.path.exists(filename) else 0,
            },
            success=True,
        )

    def _get_security_evaluator_data(self) -> dict:
        """
        Extract security evaluator data for JSON export

        Returns:
            Dictionary containing all security evaluator data
        """
        security_data = {}

        # Input Sanitizer
        if hasattr(self, 'input_sanitizer') and self.input_sanitizer is not None:
            security_data['input_sanitizer'] = {
                'evaluations': self.input_sanitizer.evaluations
            }

        # Output Leakage Detector
        if hasattr(self, 'output_leakage_detector') and self.output_leakage_detector is not None:
            security_data['output_leakage_detector'] = {
                'detections': self.output_leakage_detector.detections
            }

        # Tool Authorizer
        if hasattr(self, 'tool_authorizer') and self.tool_authorizer is not None:
            security_data['tool_authorizer'] = {
                'tool_calls': self.tool_authorizer.tool_calls
            }

        # Privilege Escalation Detector
        if hasattr(self, 'privilege_escalation_detector') and self.privilege_escalation_detector is not None:
            security_data['privilege_escalation_detector'] = {
                'escalation_events': self.privilege_escalation_detector.escalation_events
            }

        # Tool Chain Attack Detector
        if hasattr(self, 'tool_chain_attack_detector') and self.tool_chain_attack_detector is not None:
            security_data['tool_chain_attack_detector'] = {
                'detections': self.tool_chain_attack_detector.detections
            }

        return security_data

    def _append_report_data(self, data: dict):
        """
        Append full report data to existing data dictionary
        Required for Dashboard compatibility

        Args:
            data: Existing data dictionary to append to
        """
        # Generate report
        report = self.generate_report()

        # Add report fields
        data['total_tasks'] = report.total_tasks
        data['accuracy_metrics'] = report.accuracy_metrics if isinstance(report.accuracy_metrics, dict) else {}
        data['efficiency_metrics'] = report.efficiency_metrics if isinstance(report.efficiency_metrics, dict) else {}
        data['quality_metrics'] = report.quality_metrics if isinstance(report.quality_metrics, dict) else {}
        data['security_metrics'] = report.security_metrics if isinstance(report.security_metrics, dict) else {}
        data['recommendations'] = report.recommendations if isinstance(report.recommendations, list) else []
        data['alerts'] = report.alerts if isinstance(report.alerts, list) else []

        # Add completion_tracker data
        data['completion_tracker'] = {
            'tcr': self.tcr_tracker.calculate_tcr(),
            'completion_by_type': self.tcr_tracker.get_tcr_by_type(),
            'accuracy_stats': self.accuracy_evaluator.get_accuracy_scores()
        }

    @classmethod
    def load_from_file(cls, filename: str = "performance_data.json"):
        """Load performance data from a JSON file including evaluator data"""
        import os

        # Dashboard/data/evaluation_results 디렉토리에서 찾기 (절대 경로가 아닌 경우)
        if not os.path.isabs(filename) and not os.path.exists(filename):
            from ..utils.path_helpers import get_evaluation_results_dir
            results_dir = get_evaluation_results_dir(create=False)
            alt_path = os.path.join(results_dir, filename)
            if os.path.exists(alt_path):
                filename = alt_path

        with open(filename, encoding='utf-8') as f:
            data = json.load(f)

        # Create new monitor instance — enable security if JSON contains security evaluator data
        has_security = "security" in data.get("evaluators", {})
        monitor = cls(
            pricing=data.get("pricing", {"input": 0.003, "output": 0.015}),
            enable_security_metrics=has_security,
        )

        # Restore tasks
        for task_dict in data.get("tasks", []):
            # Convert timestamp string back to datetime
            if isinstance(task_dict.get("timestamp"), str):
                task_dict["timestamp"] = datetime.fromisoformat(task_dict["timestamp"])

            # Ensure numeric fields are proper types
            if "attempts" in task_dict:
                task_dict["attempts"] = int(task_dict["attempts"])
            if "completion_score" in task_dict:
                task_dict["completion_score"] = float(task_dict["completion_score"])
            if "accuracy_score" in task_dict:
                task_dict["accuracy_score"] = float(task_dict["accuracy_score"])
            if "execution_time" in task_dict:
                task_dict["execution_time"] = float(task_dict["execution_time"])

            # Create TaskResult object — filter extra keys for cross-monitor compatibility
            import dataclasses as _dc
            _tr_fields = {f.name for f in _dc.fields(TaskResult)}
            task = TaskResult(**{k: v for k, v in task_dict.items() if k in _tr_fields})
            monitor.record_task(task)

        # Restore evaluator data (if available)
        evaluators = data.get("evaluators", {})

        if evaluators:
            # Quality evaluations
            if "quality" in evaluators:
                monitor.quality_evaluator.evaluations = evaluators["quality"].get("evaluations", [])

            # Hallucination detections
            if "hallucination" in evaluators:
                monitor.hallucination_detector.detections = evaluators["hallucination"].get("detections", [])

            # Retry attempts
            if "retry" in evaluators:
                monitor.retry_tracker.attempts = evaluators["retry"].get("attempts", [])

            # Tool selections
            if "tool_selection" in evaluators:
                monitor.tool_selection_tracker.selections = evaluators["tool_selection"].get("selections", [])

            # Agent interactions
            if "agent_coordination" in evaluators:
                monitor.agent_coordination_tracker.interactions = evaluators["agent_coordination"].get("interactions", [])

            # Workflow executions
            if "workflow" in evaluators:
                monitor.workflow_tracker.executions = evaluators["workflow"].get("executions", [])

            # Tool call executions
            if "tool_calls" in evaluators:
                monitor.tool_analyzer.executions = evaluators["tool_calls"].get("executions", [])

            # Security evaluators (Layer 1 & 2)
            if "security" in evaluators:
                security_data = evaluators["security"]

                # Input Sanitizer
                if "input_sanitizer" in security_data:
                    monitor.input_sanitizer.evaluations = security_data["input_sanitizer"].get("evaluations", [])

                # Output Leakage Detector
                if "output_leakage_detector" in security_data:
                    monitor.output_leakage_detector.detections = security_data["output_leakage_detector"].get("detections", [])

                # Tool Authorizer
                if "tool_authorizer" in security_data:
                    monitor.tool_authorizer.tool_calls = security_data["tool_authorizer"].get("tool_calls", [])

                # Privilege Escalation Detector
                if "privilege_escalation_detector" in security_data:
                    monitor.privilege_escalation_detector.escalation_events = security_data["privilege_escalation_detector"].get("escalation_events", [])

                # Tool Chain Attack Detector
                if "tool_chain_attack_detector" in security_data:
                    monitor.tool_chain_attack_detector.detections = security_data["tool_chain_attack_detector"].get("detections", [])

            print("   Restored evaluator data:")
            print(f"     - Quality: {len(monitor.quality_evaluator.evaluations)} evaluations")
            print(f"     - Hallucination: {len(monitor.hallucination_detector.detections)} detections")
            print(f"     - Tool Calls: {len(monitor.tool_analyzer.executions)} executions")
            print(f"     - Tool Selection: {len(monitor.tool_selection_tracker.selections)} selections")
            print(f"     - Agent Coordination: {len(monitor.agent_coordination_tracker.interactions)} interactions")
            print(f"     - Workflow: {len(monitor.workflow_tracker.executions)} executions")
            if "security" in evaluators:
                print(f"     - Security: {len(monitor.input_sanitizer.evaluations)} input evals, {len(monitor.output_leakage_detector.detections)} output detections, {len(monitor.tool_authorizer.tool_calls)} tool calls")

        # Restore advanced_metrics_summary (DeepEval, Ragas 등) — check both top-level and report.*
        _ams = data.get("advanced_metrics_summary") or data.get("report", {}).get("advanced_metrics_summary")
        if _ams:
            monitor._advanced_metrics_summary = _ams
            print(f"   Restored advanced metrics summary with {len(_ams)} metrics")

        # Restore RAG metrics
        if "rag_metrics" in data:
            monitor.rag_metrics = data["rag_metrics"]
            total_rag_values = sum(len(v) for v in monitor.rag_metrics.values() if v)
            if total_rag_values > 0:
                print(f"   Restored RAG metrics with {total_rag_values} total values")

        # Store evaluators data for Dashboard compatibility
        if "evaluators" in data:
            monitor.evaluators = data["evaluators"]

        print(f"✅ Performance data loaded from {filename}")
        print(f"   Loaded {len(data.get('tasks', []))} tasks")
        return monitor


# ============================================================================
# Example Usage & Demo
# ============================================================================

def create_demo_data():
    """
    Create comprehensive demo task results for testing

    Generates realistic test data covering:
    - All 10 TaskTypes
    - Various success/failure scenarios
    - Different tool usage patterns
    - Realistic error cases
    - Time-distributed tasks
    - Varied token usage patterns
    """
    demo_tasks = []

    # All available TaskTypes
    all_task_types = [
        TaskType.QA,
        TaskType.DATA_ANALYSIS,
        TaskType.CODE_GENERATION,
        TaskType.DOCUMENT_CREATION,
        TaskType.INFORMATION_RETRIEVAL,
        TaskType.REASONING,
        TaskType.CREATIVE,
        TaskType.CODING,
        TaskType.PLANNING,
        TaskType.TOOL_USE
    ]

    # Realistic error messages by category
    error_messages = {
        "timeout": ["Execution timeout after 30s", "Request timeout", "Connection timeout"],
        "validation": ["Invalid input format", "Schema validation failed", "Missing required field"],
        "api": ["API rate limit exceeded", "Service unavailable", "Authentication failed"],
        "resource": ["Out of memory", "Disk space full", "Resource quota exceeded"],
        "logic": ["Division by zero", "Index out of range", "Null pointer exception"]
    }

    # Tool categories by task type
    tool_mapping = {
        TaskType.QA: ["search", "knowledge_base", "fact_checker"],
        TaskType.DATA_ANALYSIS: ["pandas", "matplotlib", "sql_query", "data_processor"],
        TaskType.CODE_GENERATION: ["code_analyzer", "syntax_checker", "linter", "formatter"],
        TaskType.DOCUMENT_CREATION: ["template_engine", "markdown_parser", "pdf_generator"],
        TaskType.INFORMATION_RETRIEVAL: ["vector_search", "web_scraper", "database_query"],
        TaskType.REASONING: ["logic_engine", "math_solver", "proof_checker"],
        TaskType.CREATIVE: ["image_gen", "style_analyzer", "content_filter"],
        TaskType.CODING: ["compiler", "debugger", "test_runner", "code_review"],
        TaskType.PLANNING: ["task_scheduler", "resource_allocator", "dependency_resolver"],
        TaskType.TOOL_USE: ["api_caller", "file_handler", "system_command"]
    }

    # Generate 100 diverse tasks
    for i in range(100):
        task_type = np.random.choice(all_task_types)

        # Realistic success rate: 88% overall, varies by task type
        base_success_rate = {
            TaskType.QA: 0.92,
            TaskType.DATA_ANALYSIS: 0.85,
            TaskType.CODE_GENERATION: 0.83,
            TaskType.DOCUMENT_CREATION: 0.90,
            TaskType.INFORMATION_RETRIEVAL: 0.88,
            TaskType.REASONING: 0.80,
            TaskType.CREATIVE: 0.95,
            TaskType.CODING: 0.82,
            TaskType.PLANNING: 0.87,
            TaskType.TOOL_USE: 0.89
        }

        success = np.random.random() < base_success_rate[task_type]

        # Realistic score distributions
        if success:
            completion_score = np.random.beta(8, 2)  # Skewed towards high scores
            accuracy_score = np.random.beta(9, 1.5)
        else:
            completion_score = np.random.beta(2, 5)  # Skewed towards low scores
            accuracy_score = np.random.beta(2, 6)

        # Realistic execution time by task type
        time_ranges = {
            TaskType.QA: (0.5, 3.0),
            TaskType.DATA_ANALYSIS: (2.0, 15.0),
            TaskType.CODE_GENERATION: (3.0, 20.0),
            TaskType.DOCUMENT_CREATION: (1.0, 8.0),
            TaskType.INFORMATION_RETRIEVAL: (1.5, 10.0),
            TaskType.REASONING: (2.0, 12.0),
            TaskType.CREATIVE: (5.0, 30.0),
            TaskType.CODING: (3.0, 25.0),
            TaskType.PLANNING: (2.0, 15.0),
            TaskType.TOOL_USE: (0.5, 5.0)
        }

        time_range = time_ranges[task_type]
        execution_time = np.random.uniform(*time_range)

        # Realistic token usage by task type
        token_ranges = {
            TaskType.QA: (100, 500, 50, 300),  # input_min, input_max, output_min, output_max
            TaskType.DATA_ANALYSIS: (500, 2000, 300, 1500),
            TaskType.CODE_GENERATION: (200, 800, 400, 2000),
            TaskType.DOCUMENT_CREATION: (300, 1500, 500, 3000),
            TaskType.INFORMATION_RETRIEVAL: (100, 600, 200, 1000),
            TaskType.REASONING: (200, 1000, 300, 1200),
            TaskType.CREATIVE: (150, 600, 400, 2500),
            TaskType.CODING: (300, 1200, 500, 2500),
            TaskType.PLANNING: (400, 1500, 600, 2000),
            TaskType.TOOL_USE: (100, 400, 100, 500)
        }

        token_range = token_ranges[task_type]
        input_tokens = int(np.random.uniform(token_range[0], token_range[1]))
        output_tokens = int(np.random.uniform(token_range[2], token_range[3]))

        # Realistic tool calls
        available_tools = tool_mapping.get(task_type, ["generic_tool"])
        num_tools = np.random.poisson(2) + 1  # Average 3 tool calls
        num_tools = min(num_tools, 6)  # Cap at 6

        tool_calls = []
        for _ in range(num_tools):
            tool_success = np.random.random() < 0.95  # 95% tool success rate
            tool_calls.append({
                "tool": np.random.choice(available_tools),
                "duration": np.random.exponential(0.5),
                "success": tool_success,
                "parameters": {"task_id": f"task_{i:03d}"}
            })

        # Realistic attempt patterns
        if success:
            attempts = 1
        else:
            # Failed tasks might have retries
            attempts = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2])

        # Generate realistic errors for failed tasks
        errors = []
        if not success:
            error_category = np.random.choice(list(error_messages.keys()))
            error_msg = np.random.choice(error_messages[error_category])
            errors.append(error_msg)

            # Some tasks have multiple errors
            if np.random.random() < 0.3:
                other_category = np.random.choice(list(error_messages.keys()))
                errors.append(np.random.choice(error_messages[other_category]))

        # Time distribution: more tasks during business hours
        # Probabilities sum to 1.0
        hour_probs = np.array([
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02,  # 0-5 AM (0.07)
            0.03, 0.05, 0.07, 0.08, 0.09, 0.09,  # 6-11 AM (0.41)
            0.08, 0.08, 0.09, 0.09, 0.08, 0.07,  # 12-5 PM (0.49)
            0.05, 0.03, 0.02, 0.02, 0.01, 0.01   # 6-11 PM (0.14)
        ])
        # Normalize to ensure sum is exactly 1.0
        hour_probs = hour_probs / hour_probs.sum()

        hour_bias = np.random.choice(range(24), p=hour_probs)

        timestamp = datetime.now() - timedelta(
            hours=np.random.randint(0, 72),
            minutes=np.random.randint(0, 60)
        )

        task = TaskResult(
            task_id=f"task_{i:03d}",
            task_type=task_type.value,
            success=success,
            completion_score=float(completion_score),
            accuracy_score=float(accuracy_score),
            execution_time=float(execution_time),
            tokens_used={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            },
            tool_calls=tool_calls,
            attempts=attempts,
            errors=errors,
            timestamp=timestamp
        )

        demo_tasks.append(task)

    return demo_tasks


def run_demo():
    """
    Run a comprehensive demonstration of the evaluation system

    Generates 100 diverse tasks across all TaskTypes and demonstrates:
    - Task Completion Rate (TCR) tracking
    - Token usage and cost analysis
    - Latency monitoring
    - Error pattern analysis
    - Retry behavior tracking
    """
    print("\n" + "="*80)
    print("AI AGENT EVALUATION SYSTEM - COMPREHENSIVE DEMO")
    print("="*80 + "\n")

    # Initialize monitor with realistic pricing (OpenAI GPT-4 Turbo rates)
    monitor = PerformanceMonitor(pricing={
        "input": 0.01,   # $10 per 1M tokens
        "output": 0.03   # $30 per 1M tokens
    })

    # Generate and record demo data
    print("📊 Generating comprehensive demo task data...")
    print("   • 100 tasks across 10 TaskTypes")
    print("   • Realistic success/failure patterns")
    print("   • Varied tool usage and token consumption")
    print("   • Time-distributed over 72 hours\n")

    demo_tasks = create_demo_data()

    print(f"📝 Recording {len(demo_tasks)} tasks...\n")

    # Show task type distribution
    from collections import Counter
    task_type_counts = Counter(task.task_type for task in demo_tasks)
    print("Task Type Distribution:")
    for task_type, count in sorted(task_type_counts.items()):
        print(f"   • {task_type}: {count} tasks")
    print()

    # Record all tasks
    for i, task in enumerate(demo_tasks, 1):
        monitor.record_task(task)
        if i % 20 == 0:
            print(f"   ✓ Recorded {i}/{len(demo_tasks)} tasks...")

    print(f"   ✓ All {len(demo_tasks)} tasks recorded!\n")

    # Generate and print comprehensive report
    print("="*80)
    print("EVALUATION REPORT")
    print("="*80 + "\n")

    monitor.print_report()

    # Additional detailed analysis
    print("\n" + "="*80)
    print("DETAILED ANALYSIS")
    print("="*80 + "\n")

    print("📈 Task Completion Rate by Type:")
    tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()
    for task_type, tcr_data in sorted(tcr_by_type.items()):
        print(f"   • {task_type}: {tcr_data.get('tcr', 0):.1f}%")

    print("\n⏱️  Latency Analysis:")
    bottlenecks = monitor.latency_tracker.analyze_bottlenecks()
    if bottlenecks and bottlenecks.get("bottleneck"):
        print(f"   Bottleneck: {bottlenecks['bottleneck']} (avg {bottlenecks.get('bottleneck_avg_time', 0):.3f}s)")
        for comp, avg_time in bottlenecks.get("breakdown_averages", {}).items():
            print(f"   • {comp}: {avg_time:.3f}s")
    else:
        print("   No significant bottlenecks detected")

    print("\n🔄 Failure Pattern Analysis:")
    failure_patterns = monitor.retry_tracker.analyze_failure_patterns()
    if failure_patterns and failure_patterns.get("patterns"):
        for reason, count in list(failure_patterns["patterns"].items())[:5]:
            print(f"   • {reason}: {count} occurrences")
    else:
        print("   No significant failure patterns")

    print("\n💰 Cost Analysis:")
    report = monitor.generate_report()
    tokens = report.efficiency_metrics.get('tokens', {})
    if tokens:
        print(f"   • Total cost: ${tokens.get('total_cost', 0):.4f}")
        print(f"   • Avg cost per task: ${tokens.get('avg_cost_per_task', 0):.4f}")
        print(f"   • Tokens per task (avg): {tokens.get('avg_tokens_per_task', 0):.0f}")

    # Export comprehensive report
    print("\n📁 Exporting results...")
    monitor.export_report("evaluation_report.json", format="json")
    print("   ✓ Saved to: evaluation_report.json")

    monitor.export_report("evaluation_report.csv", format="csv")
    print("   ✓ Saved to: evaluation_report.csv")

    print("\n" + "="*80)
    print("DEMO COMPLETED SUCCESSFULLY!")
    print("="*80 + "\n")

    print("💡 Next steps:")
    print("   1. Review evaluation_report.json for detailed metrics")
    print("   2. Open evaluation_report.csv in spreadsheet software")
    print("   3. Use the monitor object for custom analysis")
    print("   4. Integrate with your own agent workflow\n")

    return monitor


if __name__ == "__main__":
    """
    Demo Mode: Run comprehensive evaluation system demonstration

    This generates 100 realistic test tasks and demonstrates all evaluation features.
    Perfect for:
    - Understanding system capabilities
    - Testing integration
    - Benchmarking performance
    - Learning the API
    """
    # Run comprehensive demo
    monitor = run_demo()

    # Show how to access individual components for custom analysis
    print("="*80)
    print("ADVANCED USAGE EXAMPLES")
    print("="*80 + "\n")

    print("# Access individual tracker components:")
    print("monitor.tcr_tracker        # Task Completion Rate tracking")
    print("monitor.token_tracker      # Token usage and cost analysis")
    print("monitor.latency_tracker    # Execution time monitoring")
    print("monitor.retry_tracker      # Retry and failure analysis")
    print()

    print("# Get specific metrics:")
    print("tcr_by_type = monitor.tcr_tracker.get_tcr_by_type()")
    print("bottlenecks = monitor.latency_tracker.analyze_bottlenecks()")
    print("patterns = monitor.retry_tracker.analyze_failure_patterns()")
    print()

    print("# Generate custom reports:")
    print("report = monitor.generate_report()")
    print("monitor.export_report('custom_report.json', format='json')")
    print()

    print("# Integration example:")
    print("""
from agent_evaluator import PerformanceMonitor, TaskResult, TaskType

# Initialize
monitor = PerformanceMonitor(pricing={'input': 0.01, 'output': 0.03})

# Record your agent's task
task = TaskResult(
    task_id='my_task_001',
    task_type=TaskType.QA.value,
    success=True,
    completion_score=0.95,
    accuracy_score=0.92,
    execution_time=2.3,
    tokens_used={'input': 500, 'output': 300, 'total': 800},
    tool_calls=[],
    attempts=1,
    errors=[],
    timestamp=datetime.now()
)

monitor.record_task(task)
monitor.print_report()
""")
