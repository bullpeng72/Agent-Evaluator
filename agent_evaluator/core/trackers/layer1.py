"""
agent_evaluator.core.trackers.layer1
======================================
Layer 1 — Foundation Metrics (native, no external deps):
  TaskCompletionTracker, AccuracyEvaluator, HallucinationDetector,
  ResponseQualityEvaluator, LatencyTracker, TokenEconomyTracker
"""

from __future__ import annotations

import ast
import logging
import re
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

from .base import BaseTracker, TaskResult, TaskType
from ...exceptions import ValidationError
from ...utils.text_similarity import lcs_ratio as _lcs_ratio

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

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns — avoids per-call recompilation overhead
# ---------------------------------------------------------------------------
# QA accuracy text normalization
_RE_QA_WHITESPACE = re.compile(r'\s+')
_RE_QA_PUNCTUATION = re.compile(r'[^\w\s]')

# Code normalization (for _normalized_code_comparison)
_RE_CODE_SINGLE_COMMENT = re.compile(r'#.*?$', re.MULTILINE)
_RE_CODE_DOUBLE_DOCSTRING = re.compile(r'""".*?"""', re.DOTALL)
_RE_CODE_SINGLE_DOCSTRING = re.compile(r"'''.*?'''", re.DOTALL)
_RE_CODE_WHITESPACE = re.compile(r'\s+')

# Hallucination number extraction
_RE_NUMBER = re.compile(r'\d+\.?\d*')


def _try_load_kiwi():
    """kiwipiepy.Kiwi 인스턴스를 반환. 미설치 시 None 반환하고 경고 로그 출력."""
    try:
        from kiwipiepy import Kiwi  # type: ignore[import]
        return Kiwi()
    except ImportError:
        logger.warning(
            "use_korean_tokenizer=True but kiwipiepy is not installed. "
            "Falling back to whitespace tokenization. "
            "Install: pip install \"agent-evaluator[korean]\""
        )
        return None


def _try_load_encoder():
    """sentence-transformers SentenceTransformer 인스턴스를 반환. 미설치 시 None."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        logger.warning(
            "use_semantic_similarity=True but sentence-transformers is not installed. "
            "Falling back to word-overlap method. "
            "Install: pip install \"agent-evaluator[semantic]\""
        )
        return None


def _normalize_qa_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation — shared by QA accuracy helpers."""
    text = text.lower()
    text = _RE_QA_WHITESPACE.sub(' ', text).strip()
    text = _RE_QA_PUNCTUATION.sub('', text)
    return text


def _qa_char_similarity(s1: str, s2: str) -> float:
    """Character-level similarity using Levenshtein distance (order-aware)."""
    if s1 == s2:
        return 1.0
    m, n = len(s1), len(s2)
    if m == 0 or n == 0:
        return 0.0
    if m > n:
        s1, s2, m, n = s2, s1, n, m
    prev_row = list(range(n + 1))
    for i in range(1, m + 1):
        curr_row = [i]
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr_row.append(min(prev_row[j] + 1, curr_row[j - 1] + 1, prev_row[j - 1] + cost))
        prev_row = curr_row
    return max(0.0, 1.0 - prev_row[n] / max(m, n))


def _normalize_code(code: str) -> str:
    """Remove comments, docstrings, and collapse whitespace for normalized code comparison."""
    code = _RE_CODE_SINGLE_COMMENT.sub('', code)
    code = _RE_CODE_DOUBLE_DOCSTRING.sub('', code)
    code = _RE_CODE_SINGLE_DOCSTRING.sub('', code)
    code = _RE_CODE_WHITESPACE.sub(' ', code).strip()
    return code


def _assign_grade(score: float) -> str:
    """Convert a 0–5 quality score to a letter grade.

    Used by :class:`ResponseQualityEvaluator` for both individual evaluations
    and the aggregate ``avg_grade`` in :meth:`get_quality_metrics`.

    Args:
        score: Numeric quality score in the range [0, 5].

    Returns:
        Letter grade string: ``"A"`` (≥4.5), ``"B"`` (≥4.0), ``"C"`` (≥3.5),
        ``"D"`` (≥3.0), or ``"F"`` (<3.0).
    """
    if score >= 4.5:
        return "A"
    elif score >= 4.0:
        return "B"
    elif score >= 3.5:
        return "C"
    elif score >= 3.0:
        return "D"
    return "F"


# TaskType alias mapping: canonical form used for bucketing in get_tcr_by_type().
# TaskType.CODING ("coding") is a legacy alias for CODE_GENERATION ("code_generation").
_TASK_TYPE_ALIASES: Dict[str, str] = {
    "coding": "code_generation",
}


# ============================================================================
# 1. Task Completion Rate Tracker
# ============================================================================

class TaskCompletionTracker(BaseTracker):
    """Track and analyze task completion rates"""

    def __init__(self):
        self._tasks: List[TaskResult] = []
        self.completion_criteria = {
            "full_success": 1.0,
            "partial_success": 0.7,
            "failure": 0.0
        }

    @property
    def tasks(self) -> List[TaskResult]:
        """Shallow copy of accumulated tasks — prevents external mutation of internal state."""
        return list(self._tasks)

    @tasks.setter
    def tasks(self, value: List[TaskResult]) -> None:
        """Restore internal state (used by load_from_file)."""
        self._tasks = list(value)

    def add_task(self, task: TaskResult):
        """Add a task result"""
        self._tasks.append(task)

    def reset(self) -> None:
        """Clear all accumulated tasks.  Useful for reusing the tracker across sessions."""
        self._tasks.clear()

    def calculate_tcr(self, task_type: Optional[str] = None) -> Dict[str, float]:
        """Calculate Task Completion Rate"""
        tasks = self._tasks
        if task_type:
            _canonical = _TASK_TYPE_ALIASES.get(task_type, task_type)
            tasks = [t for t in tasks if _TASK_TYPE_ALIASES.get(t.task_type, t.task_type) == _canonical]

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

    # Alias for naming consistency with other trackers' get_*_metrics() pattern
    get_completion_metrics = calculate_tcr

    def get_tcr_by_type(self) -> Dict[str, Dict[str, float]]:
        """Get TCR breakdown by task type.

        ``TaskType.CODING`` ("coding") is merged into the
        ``"code_generation"`` bucket to avoid split reporting.
        """
        canonical_types = set(
            _TASK_TYPE_ALIASES.get(t.task_type, t.task_type) for t in self._tasks
        )
        return {ct: self.calculate_tcr(ct) for ct in canonical_types}

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
        return f"TaskCompletionTracker(tasks={len(self._tasks)})"


# ============================================================================
# 2. Accuracy Evaluator
# ============================================================================

class AccuracyEvaluator(BaseTracker):
    """Evaluate accuracy across different dimensions"""

    def __init__(self, use_korean_tokenizer: bool = False):
        self._evaluations: List[Dict[str, Any]] = []
        self._cached_avg: Optional[float] = None  # invalidated on each add_evaluation()
        self._task_ids: Set[str] = set()
        self._kiwi = _try_load_kiwi() if use_korean_tokenizer else None

    def _tokenize_words(self, text: str) -> set:
        """형태소 분석(kiwipiepy) 또는 공백 분리 폴백으로 단어 토큰 집합 반환."""
        normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
        if self._kiwi is not None:
            tokens = [t.form for t in self._kiwi.tokenize(normalized)
                      if t.tag in ("NNG", "NNP", "VV", "VA", "SL", "SN", "XR")]
            return set(tokens) if tokens else set(normalized.split())
        return set(normalized.split())

    @property
    def evaluations(self) -> List[Dict[str, Any]]:
        """Shallow copy of accumulated evaluations.

        Returns a new list each time so callers cannot accidentally mutate
        the internal state or bypass ``_cached_avg`` invalidation.  Use
        :meth:`add_evaluation` or :meth:`record_score` to add records.
        """
        return list(self._evaluations)

    @evaluations.setter
    def evaluations(self, value: List[Dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file).  Invalidates repr cache."""
        self._cached_avg = None
        self._evaluations = list(value)
        self._task_ids = {e.get("task_id") for e in value if e.get("task_id") is not None}

    def reset(self) -> None:
        """Clear all evaluations and invalidate the repr cache."""
        self._cached_avg = None  # invalidate before clearing so __repr__ never sees stale avg
        self._evaluations.clear()
        self._task_ids.clear()

    def record_score(
        self, task_id: str, task_type: str, accuracy: Optional[float]
    ) -> None:
        """Record a pre-computed accuracy score (cache-safe).

        Use this when the caller has already computed the accuracy value and
        wants to store it without re-running the similarity pipeline.
        Unlike appending to ``evaluations`` directly, this method invalidates
        ``_cached_avg`` so ``__repr__`` and ``get_accuracy_scores()`` remain
        consistent.

        Args:
            task_id: Unique task identifier.
            task_type: Normalised task type string (e.g. ``"qa"``).
            accuracy: Pre-computed score in [0.0, 1.0], or ``None`` when
                the score was not measured for this task.
        """
        self._cached_avg = None  # invalidate repr cache
        self._evaluations.append({
            "task_id": task_id,
            "task_type": task_type,
            "accuracy": accuracy,
            "timestamp": datetime.now(),
        })
        self._task_ids.add(task_id)

    def add_evaluation(self, task_id: str, ground_truth: Any,
                      prediction: Any, task_type: str):
        """Add an evaluation"""
        self._cached_avg = None  # invalidate repr cache
        accuracy = self._calculate_accuracy(ground_truth, prediction, task_type)

        self._evaluations.append({
            "task_id": task_id,
            "task_type": task_type,
            "accuracy": accuracy,
            "timestamp": datetime.now()
        })
        self._task_ids.add(task_id)

    def _calculate_accuracy(self, ground_truth: Any, prediction: Any,
                           task_type: str) -> float:
        """Calculate accuracy based on task type"""
        _canonical = _TASK_TYPE_ALIASES.get(task_type, task_type)
        if _canonical == TaskType.QA.value:
            return self._qa_accuracy(ground_truth, prediction)
        elif _canonical == TaskType.CODE_GENERATION.value:
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
        gt_norm = _normalize_qa_text(ground_truth)
        pred_norm = _normalize_qa_text(prediction)

        if not gt_norm:
            return 0.0

        # 1. Token-based Jaccard similarity
        gt_tokens = self._tokenize_words(gt_norm)
        pred_tokens = self._tokenize_words(pred_norm)

        if not gt_tokens:
            return 0.0

        intersection = len(gt_tokens & pred_tokens)
        union = len(gt_tokens | pred_tokens)
        # Jaccard: coverage relative to *union* (penalises extra tokens in prediction)
        jaccard = intersection / union if union > 0 else 0.0

        # Token overlap F1: harmonic mean of precision and recall.
        # Balances coverage of ground-truth (recall) and avoiding hallucinated tokens (precision).
        precision = intersection / len(pred_tokens) if pred_tokens else 0.0
        recall = intersection / len(gt_tokens) if gt_tokens else 0.0
        overlap_ratio = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        # 3. Character-level similarity (handles typos better)
        char_sim = _qa_char_similarity(gt_norm, pred_norm)

        # 4. Longest common subsequence ratio — rolling 2-row DP: O(n) space
        lcs_sim = _lcs_ratio(gt_norm, pred_norm)

        # Weighted combination (weights defined as module constants above)
        final_score = (
            _QA_WEIGHT_TOKEN_OVERLAP * overlap_ratio +
            _QA_WEIGHT_JACCARD * jaccard +
            _QA_WEIGHT_LCS * lcs_sim +
            _QA_WEIGHT_CHAR * char_sim
        )

        if final_score > 1.0:
            logger.debug(
                "_qa_accuracy: weighted score %.4f exceeded 1.0 (clamped). "
                "This is normal when all similarity signals are high.",
                final_score,
            )
        return min(final_score, 1.0)

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
        try:
            tree1 = ast.parse(code1)
            tree2 = ast.parse(code2)

            if ast.dump(tree1) == ast.dump(tree2):
                return 1.0

            # Node-type multiset Jaccard: counts each AST node type occurrence.
            # Avoids false splits caused by commas inside string literals in ast.dump().
            from collections import Counter as _Counter
            counter1: _Counter = _Counter(type(node).__name__ for node in ast.walk(tree1))
            counter2: _Counter = _Counter(type(node).__name__ for node in ast.walk(tree2))

            intersection = sum((counter1 & counter2).values())
            union = sum((counter1 | counter2).values())

            return intersection / union if union > 0 else 0.0

        except SyntaxError:
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
        norm1 = _normalize_code(code1)
        norm2 = _normalize_code(code2)

        if norm1 == norm2:
            return _CODE_NORMALIZED_MATCH_CONFIDENCE  # High confidence but not perfect (comments differ)

        # Character-level similarity
        if not norm1:
            return 0.0

        return _qa_char_similarity(norm1, norm2)

    def _general_accuracy(self, ground_truth: Any, prediction: Any) -> float:
        """General accuracy"""
        return 1.0 if str(ground_truth) == str(prediction) else 0.0

    def get_accuracy_scores(self) -> Dict[str, float]:
        """Get aggregated accuracy scores"""
        if not self._evaluations:
            return {
                "overall_accuracy": 0.0,
                "median_accuracy": 0.0,
                "min_accuracy": 0.0,
                "max_accuracy": 0.0,
                "std_accuracy": 0.0,
                "high_accuracy_count": 0,
                "low_accuracy_count": 0,
            }

        df = pd.DataFrame(self._evaluations)
        measured = df["accuracy"].dropna()

        if measured.empty:
            return {
                "overall_accuracy": 0.0,
                "median_accuracy": 0.0,
                "min_accuracy": 0.0,
                "max_accuracy": 0.0,
                "std_accuracy": 0.0,
                "high_accuracy_count": 0,
                "low_accuracy_count": 0,
            }

        std_val = measured.std()

        return {
            "overall_accuracy": round(measured.mean() * 100, 2),
            "median_accuracy": round(measured.median() * 100, 2),
            "min_accuracy": round(measured.min() * 100, 2),
            "max_accuracy": round(measured.max() * 100, 2),
            "std_accuracy": round(std_val * 100, 2) if not pd.isna(std_val) else 0.0,
            "high_accuracy_count": int((measured >= 0.9).sum()),
            "low_accuracy_count": int((measured < 0.7).sum()),
        }

    def get_accuracy_by_type(self) -> Dict[str, float]:
        """Get accuracy breakdown by task type"""
        if not self._evaluations:
            return {}

        df = pd.DataFrame(self._evaluations)
        return (
            df.groupby("task_type")["accuracy"]
            .apply(lambda s: s.dropna().mean())
            .mul(100)
            .round(2)
            .to_dict()
        )

    def get_accuracy_metrics(self) -> Dict[str, Any]:
        """Get aggregated accuracy metrics — consistent superset of get_accuracy_scores().

        Returns the same keys as :meth:`get_accuracy_scores` so callers can use either
        method interchangeably.  Returns structured zeros (not ``{}``) when no
        evaluations have been recorded, allowing safe key access without guards.

        Returns:
            Dict with keys: total_evaluated, overall_accuracy, median_accuracy,
            min_accuracy, max_accuracy, std_accuracy,
            high_accuracy_count, low_accuracy_count  (all float/int).
        """
        if not self._evaluations:
            return {
                "total_evaluated": 0,
                "overall_accuracy": 0.0,
                "median_accuracy": 0.0,
                "min_accuracy": 0.0,
                "max_accuracy": 0.0,
                "std_accuracy": 0.0,
                "high_accuracy_count": 0,
                "low_accuracy_count": 0,
            }
        scores = self.get_accuracy_scores()
        return {
            "total_evaluated": len(self._evaluations),
            **scores,
        }

    def __repr__(self) -> str:
        # _cached_avg is None when invalidated.  We only write a numeric value when
        # at least one accuracy measurement exists; otherwise leave it None so that
        # callers see "<no-data>" instead of a misleading "0.0%".
        if self._cached_avg is None:
            measured = [e.get("accuracy") for e in self._evaluations if e.get("accuracy") is not None]
            if measured:
                self._cached_avg = round(sum(measured) / len(measured) * 100, 1)
        n = len(self._evaluations)
        avg_str = f"{self._cached_avg}%" if self._cached_avg is not None else "<no-data>"
        return f"AccuracyEvaluator(evaluations={n}, avg={avg_str})"


# ============================================================================
# 3. Hallucination Detector
# ============================================================================

class HallucinationDetector(BaseTracker):
    """
    Rule-based hallucination detector (Layer 1 Native Metric)

    Detection Methods:
    1. Unsupported Claims: Response sentences with support score < 30% threshold
       - Word overlap mode (default): simple token-level overlap ratio
       - Semantic mode (use_semantic_similarity=True): blends word overlap with
         sentence-transformers cosine similarity via semantic_weight
    2. Numerical Inconsistencies: Numbers in response not found in context/ground_truth

    ⚠️ LIMITATIONS (word-overlap mode):
    - Pattern-based detection (70-80% accuracy)
    - May flag valid paraphrasing/summarization as hallucination

    ✅ SEMANTIC MODE:
    - Requires: pip install "agent-evaluator[semantic]"
    - Model: paraphrase-multilingual-MiniLM-L12-v2 (50 languages, Korean included)
    - Accuracy improvement: 80-90% vs 70-80% word-overlap baseline
    - Falls back silently to word-overlap if sentence-transformers is not installed

    📈 FOR HIGHEST ACCURACY:
    - Use HybridPerformanceMonitor with DeepEval's LLM-based hallucination detection
    - See: agent_evaluator.integrations.metric_adapters.DeepEvalAdapter
    """

    def __init__(
        self,
        use_korean_tokenizer: bool = False,
        use_semantic_similarity: bool = False,
        semantic_weight: float = 0.5,
    ):
        self._detections: List[Dict[str, Any]] = []
        self._rag_metrics: List[Dict[str, Any]] = []
        self._kiwi = _try_load_kiwi() if use_korean_tokenizer else None
        self._encoder = _try_load_encoder() if use_semantic_similarity else None
        # semantic_weight: 0.0 = 단어 중복만, 1.0 = 의미 유사도만, 0.5 = 균등 혼합
        self._semantic_weight = max(0.0, min(1.0, semantic_weight))

    def _tokenize_words(self, text: str) -> set:
        """형태소 분석(kiwipiepy) 또는 공백 분리 폴백으로 단어 토큰 집합 반환."""
        normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
        if self._kiwi is not None:
            tokens = [t.form for t in self._kiwi.tokenize(normalized)
                      if t.tag in ("NNG", "NNP", "VV", "VA", "SL", "SN", "XR")]
            return set(tokens) if tokens else set(normalized.split())
        return set(normalized.split())

    def _semantic_support_score(self, sentence: str, support_texts: List[str]) -> float:
        """sentence-transformers 코사인 유사도로 sentence의 지지도 반환.

        Args:
            sentence: 검증할 응답 문장.
            support_texts: 근거 문서(컨텍스트/정답) 목록.

        Returns:
            0.0–1.0 사이 최대 코사인 유사도. 인코더 미설치 시 0.0 반환.
        """
        if self._encoder is None or not support_texts:
            return 0.0
        try:
            import numpy as np  # already imported at module level but guard for type checker
            all_texts = [sentence] + support_texts
            embeddings = self._encoder.encode(all_texts, convert_to_numpy=True)
            sent_emb = embeddings[0]
            support_embs = embeddings[1:]
            # Cosine similarity: dot / (norm * norm)
            sent_norm = np.linalg.norm(sent_emb)
            if sent_norm == 0:
                return 0.0
            sims = []
            for emb in support_embs:
                norm = np.linalg.norm(emb)
                if norm == 0:
                    continue
                sims.append(float(np.dot(sent_emb, emb) / (sent_norm * norm)))
            return max(sims) if sims else 0.0
        except Exception as exc:
            logger.debug("semantic_support_score calculation failed (ignored): %s", exc)
            return 0.0

    @property
    def detections(self) -> List[Dict[str, Any]]:
        """Read-only snapshot of accumulated detection records.

        Returns a shallow copy so callers cannot mutate internal state.
        Use :meth:`detect_hallucination` to add records.
        """
        return list(self._detections)

    @detections.setter
    def detections(self, value: List[Dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        self._detections = list(value)

    def reset(self) -> None:
        """Clear all hallucination detections."""
        self._detections.clear()
        self._rag_metrics.clear()

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
        context_words = self._tokenize_words(context)
        # ground_truth words are also valid support — if a claim appears in the
        # expected answer it should not be flagged as hallucination
        gt_words = self._tokenize_words(ground_truth) if ground_truth else set()
        supported_words = context_words | gt_words

        # Build support texts for semantic similarity (used when encoder available)
        support_texts = [context]
        if ground_truth:
            support_texts.append(ground_truth)

        for sentence in response_sentences:
            sentence_words = self._tokenize_words(sentence)

            # CRITICAL FIX: Skip empty sentences to avoid zero division
            if len(sentence_words) == 0:
                continue

            if len(sentence_words) <= _HALLUCINATION_SENTENCE_MIN_WORDS:
                continue

            overlap = len(sentence_words & supported_words)
            word_support = overlap / len(sentence_words)

            if self._encoder is not None:
                # 의미 유사도와 단어 중복을 semantic_weight로 혼합
                semantic_support = self._semantic_support_score(sentence, support_texts)
                support_score = (
                    (1.0 - self._semantic_weight) * word_support
                    + self._semantic_weight * semantic_support
                )
            else:
                support_score = word_support

            # If support score below threshold, flag as potential hallucination
            if support_score < _HALLUCINATION_OVERLAP_THRESHOLD:
                hallucination_indicators.append({
                    "type": "unsupported_claim",
                    "sentence": sentence.strip(),
                    "severity": "medium"
                })

        # 2. Check for numerical inconsistencies (pre-compiled pattern for performance)
        response_numbers = _RE_NUMBER.findall(response)
        context_numbers = _RE_NUMBER.findall(context)
        ground_truth_numbers = _RE_NUMBER.findall(ground_truth) if ground_truth else []

        for num in response_numbers:
            if num not in context_numbers and num not in ground_truth_numbers:
                hallucination_indicators.append({
                    "type": "numerical_inconsistency",
                    "value": num,
                    "severity": "high"
                })

        # HIGH PRIORITY FIX: Empty response is 100% hallucination
        if not response_sentences:
            hallucination_rate = 1.0
        else:
            # Separate by unit type to avoid inflating rate:
            # unsupported_claim is per sentence; numerical_inconsistency is per number found.
            sentence_indicators = [i for i in hallucination_indicators if i["type"] == "unsupported_claim"]
            number_indicators = [i for i in hallucination_indicators if i["type"] == "numerical_inconsistency"]
            sentence_rate = len(sentence_indicators) / len(response_sentences)
            number_rate = len(number_indicators) / len(response_numbers) if response_numbers else 0.0
            # Weighted combination: sentence-level (0.6) + number-level (0.4)
            hallucination_rate = min(1.0, sentence_rate * 0.6 + number_rate * 0.4)

        detection = {
            "task_id": task_id,
            "hallucination_rate": hallucination_rate,
            "semantic_enabled": self._encoder is not None,
            "indicators": hallucination_indicators,
            "response_sentences": len(response_sentences),   # 응답 문장 수
            "question": request[:200] if request else None,  # 원래 질문 (최대 200자)
            "context": context[:300] if context else None,   # 참조 컨텍스트 (최대 300자)
            "timestamp": datetime.now()
        }

        self._detections.append(detection)
        return detection

    # ------------------------------------------------------------------
    # RAG metrics (Context Recall / Context Precision approximation)
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> set:
        """소문자 단어 토큰 집합 (구두점 제거). 한국어 토크나이저 활성 시 형태소 분석 사용."""
        return self._tokenize_words(text)

    def compute_context_recall(self, ground_truth: str, context: str) -> float:
        """Context Recall 근사: GT 키워드 중 context 에 포함된 비율.

        Ragas Context Recall (LLM 기반) 의 경량 토큰 오버랩 근사값이다.
        ground_truth 의 핵심 정보가 retrieved context 에 얼마나 담겼는지를 나타낸다.
        값이 낮으면 retriever 가 정답에 필요한 문서를 놓쳤을 가능성이 높다.

        Returns:
            0.0 – 1.0 (1.0 = GT 의 모든 토큰이 context 에 존재)
        """
        gt_tokens = self._tokenize(ground_truth)
        if not gt_tokens:
            return 0.0
        ctx_tokens = self._tokenize(context)
        return round(len(gt_tokens & ctx_tokens) / len(gt_tokens), 4)

    def compute_context_precision(self, response: str, context: str) -> float:
        """Context Precision 근사: context 토큰 중 response 에 실제 인용된 비율.

        Ragas Context Precision (LLM 기반) 의 경량 근사값이다.
        retrieved context 가 응답 생성에 얼마나 활용됐는지(노이즈 대비 유용성)를 나타낸다.
        값이 낮으면 retriever 가 불필요한 문서를 과도하게 가져왔을 가능성이 높다.

        Returns:
            0.0 – 1.0 (1.0 = context 의 모든 토큰이 response 에 등장)
        """
        ctx_tokens = self._tokenize(context)
        if not ctx_tokens:
            return 0.0
        resp_tokens = self._tokenize(response)
        return round(len(ctx_tokens & resp_tokens) / len(ctx_tokens), 4)

    def track_rag_task(
        self,
        task_id: str,
        response: str,
        context: str,
        ground_truth: Optional[str] = None,
    ) -> Dict[str, float]:
        """Context Recall / Precision 을 계산하고 내부 목록에 저장한다.

        ``PerformanceMonitor.record_task()`` 에서 ``enable_hallucination_detection=True``
        이고 ``context`` 와 ``ground_truth`` 가 모두 존재할 때 자동으로 호출된다.
        ``@agent_eval(rag_mode=True)`` 데코레이터를 사용하면 추가 코드 없이 동작한다.

        Args:
            task_id: 태스크 고유 ID.
            response: 에이전트 응답 텍스트.
            context: Retriever 가 가져온 문서 텍스트.
            ground_truth: 정답 텍스트 (Context Recall 계산에 사용).

        Returns:
            Dict with context_recall and context_precision (0.0–1.0).
        """
        recall = self.compute_context_recall(ground_truth or "", context) if ground_truth else None
        precision = self.compute_context_precision(response, context)
        record: Dict[str, Any] = {
            "task_id": task_id,
            "context_precision": precision,
            "context_recall": recall,
        }
        self._rag_metrics.append(record)
        return {k: v for k, v in record.items() if k != "task_id" and v is not None}

    def get_rag_metrics(self) -> Dict[str, Any]:
        """Context Recall / Precision 집계 통계를 반환한다.

        Returns:
            Dict with keys: tasks_evaluated, avg_context_precision,
            avg_context_recall (None 이면 ground_truth 미제공), per_task list.
        """
        if not self._rag_metrics:
            return {
                "tasks_evaluated": 0,
                "avg_context_precision": 0.0,
                "avg_context_recall": None,
                "per_task": [],
            }

        precisions = [r["context_precision"] for r in self._rag_metrics]
        recalls = [r["context_recall"] for r in self._rag_metrics if r["context_recall"] is not None]

        return {
            "tasks_evaluated": len(self._rag_metrics),
            "avg_context_precision": round(sum(precisions) / len(precisions), 4),
            "avg_context_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "per_task": list(self._rag_metrics),
        }

    def get_hallucination_rate(self) -> Dict[str, float]:
        """Get overall hallucination statistics"""
        if not self._detections:
            return {
                "overall_rate": 0.0,
                "median_rate": 0.0,
                "max_rate": 0.0,
                "tasks_with_hallucinations": 0,
                "total_tasks_checked": 0,
                "total_evaluated": 0,
                "total_flagged": 0,
                "unsupported_claims_count": 0,
                "numerical_inconsistencies_count": 0,
            }

        rates = [d["hallucination_rate"] for d in self._detections]
        flagged_count = sum(1 for r in rates if r > 0)

        # Count hallucination types
        unsupported_claims_count = 0
        numerical_inconsistencies_count = 0

        for detection in self._detections:
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
        if not self._detections:
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

        for detection in self._detections:
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
            "total_detections": len(self._detections),
            "hallucination_rate": round((total_indicators / len(self._detections)) * 100, 2) if self._detections else 0.0,
            "by_severity": severity_counts,
            "avg_per_detection": round(total_indicators / len(self._detections), 2) if self._detections else 0.0
        }

    def __repr__(self) -> str:
        rate = (
            round(
                sum(d.get("hallucination_rate", 0.0) for d in self._detections)
                / len(self._detections) * 100, 1
            )
            if self._detections else 0.0
        )
        return f"HallucinationDetector(detections={len(self._detections)}, rate={rate}%)"


# ============================================================================
# 4. Response Quality Evaluator
# ============================================================================

class ResponseQualityEvaluator(BaseTracker):
    """Evaluate response quality across multiple dimensions"""

    #: Default dimension weights (must sum to 1.0). Override via constructor.
    DEFAULT_DIMENSIONS: Dict[str, float] = {
        "relevance": 0.25,
        "completeness": 0.25,
        "accuracy": 0.20,
        "clarity": 0.15,
        "usefulness": 0.15,
    }

    def __init__(
        self,
        dimensions: Optional[Dict[str, float]] = None,
        format_bonus: bool = False,
    ):
        """
        Args:
            dimensions: Custom dimension weights dict. Must sum to 1.0 (±0.01 tolerance).
                If None, uses ``DEFAULT_DIMENSIONS``.
            format_bonus: When True, the clarity score applies a 1.2× boost for
                responses that contain newlines (structured formatting). Default False
                to avoid rewarding verbosity or markdown decoration over content quality.
                Set True only if formatting quality is an explicit evaluation criterion.

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
        self.format_bonus = format_bonus
        self._evaluations: List[Dict[str, Any]] = []
        self._task_ids: Set[str] = set()

    @property
    def evaluations(self) -> List[Dict[str, Any]]:
        """Shallow copy of accumulated quality evaluations."""
        return list(self._evaluations)

    @evaluations.setter
    def evaluations(self, value: List[Dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        self._evaluations = list(value)
        self._task_ids = {e.get("task_id") for e in value if e.get("task_id") is not None}

    def reset(self) -> None:
        """Clear all quality evaluations."""
        self._evaluations.clear()
        self._task_ids.clear()

    def evaluate_response(self, task_id: str, response: str,
                         request: str, expected_elements: Optional[List[str]] = None,
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
            Dict[str, Any]: 평가 결과 딕셔너리.  각 차원 점수는 **[0, 5]** 범위.

            키 목록: ``task_id``, ``relevance``, ``completeness``, ``clarity``,
            ``accuracy``, ``usefulness``, ``total_score`` (5개 차원 가중 평균, [0, 5]),
            ``grade`` (A–F).
        """
        # H1: expected_elements=None guard — None passed at runtime bypasses List[str] hint
        if expected_elements is None:
            expected_elements = []

        scores = {}

        # Pre-compute word_count once — reused for completeness, clarity, usefulness
        word_count = len(response.split())

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

        if expected_elements:
            completeness = found_elements / len(expected_elements)
        else:
            # 검증할 요소가 없으면 응답 길이 기반 휴리스틱 (clarity와 동일 방식)
            completeness = min(word_count / 150, 1.0)
        scores["completeness"] = completeness * _QUALITY_SCORE_MAX

        # Clarity (length-normalized + optional structure bonus)
        # has_structure requires actual line breaks — a single period does not indicate
        # structured output (every sentence ends with one), so we intentionally exclude it.
        has_structure = '\n' in response
        boost = (1.2 if has_structure else 1.0) if self.format_bonus else 1.0
        clarity = min(word_count / 100, 1.0) * boost
        scores["clarity"] = min(clarity * _QUALITY_SCORE_MAX, _QUALITY_SCORE_MAX)

        # Accuracy score (use ground truth if available)
        if ground_truth:
            # Calculate similarity with ground truth
            similarity = self._calculate_similarity(response, ground_truth)
            scores["accuracy"] = similarity * _QUALITY_SCORE_MAX
        else:
            # Heuristic: longer, more complete responses tend to be more accurate
            scores["accuracy"] = min(completeness * _QUALITY_SCORE_MAX, _QUALITY_SCORE_MAX)

        # Usefulness score — length + content indicators (structure reuses has_structure above)
        has_examples = any(word in response.lower() for word in ['예를 들어', 'example', ':', '•', '-'])
        has_numbers = any(char.isdigit() for char in response)

        usefulness = (
            0.4 * min(word_count / 150, 1.0) +              # Adequate length
            0.3 * (1.0 if has_structure else 0.5) +          # Well-structured (newlines only)
            0.2 * (1.0 if has_examples else 0.5) +           # Has examples
            0.1 * (1.0 if has_numbers else 0.5)              # Has specific data
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

        self._evaluations.append(evaluation)
        self._task_ids.add(task_id)
        return evaluation

    def _assign_grade(self, score: float) -> str:
        """Assign letter grade.  Delegates to module-level :func:`_assign_grade`."""
        return _assign_grade(score)

    def _calculate_similarity(self, response: str, ground_truth: str) -> float:
        """
        Calculate similarity between response and ground truth

        Uses token-based similarity with normalization
        """
        response_norm = _normalize_qa_text(response)
        gt_norm = _normalize_qa_text(ground_truth)

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
        if not self._evaluations:
            return {
                "avg_total_score": 0.0, "avg_grade": "N/A",
                "median_total_score": 0.0, "min_total_score": 0.0,
                "max_total_score": 0.0, "std_total_score": 0.0,
                "grade_distribution": {}, "high_quality_count": 0,
                "total_evaluated": 0, "dimension_averages": {},
                "dimension_scores": {}, "quality_distribution": {},
            }

        df = pd.DataFrame(self._evaluations)

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

        _mean_val = df["total_score"].dropna().mean()
        avg_score = round(_mean_val, 2) if not pd.isna(_mean_val) else 0.0
        return {
            "avg_total_score": avg_score,
            "avg_grade": self._assign_grade(avg_score),
            "median_total_score": round(df["total_score"].median(), 2),
            "min_total_score": round(df["total_score"].min(), 2),
            "max_total_score": round(df["total_score"].max(), 2),
            "std_total_score": round(std_val, 2) if not pd.isna(std_val) else 0.0,
            "grade_distribution": grade_dist,
            "high_quality_count": high_quality_count,
            "total_evaluated": len(self._evaluations),  # Add for dashboard compatibility
            "dimension_averages": dimension_averages,
            "dimension_scores": dimension_averages,  # Alias for dashboard compatibility
            "quality_distribution": quality_distribution  # Add quality distribution for dashboard
        }

    def get_quality_by_dimension(self) -> Dict[str, Any]:
        """Get detailed quality statistics broken down by each dimension

        Returns:
            Dictionary with detailed statistics for each quality dimension
        """
        if not self._evaluations:
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

        for eval_data in self._evaluations:
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
            "total_evaluations": len(self._evaluations)
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
                sum(e.get("total_score", 0) for e in self._evaluations) / len(self._evaluations), 2
            )
            if self._evaluations else 0.0
        )
        return f"ResponseQualityEvaluator(evaluations={len(self._evaluations)}, avg_score={avg})"


# ============================================================================
# 5. Latency Tracker
# ============================================================================

class LatencyTracker(BaseTracker):
    """Track and analyze response latency"""

    def __init__(self):
        self._latencies: List[Dict[str, Any]] = []
        self._cached_stats: Optional[Dict[str, float]] = None  # invalidated on each record
        self._ttft_records: List[Dict[str, Any]] = []  # C1: TTFT records

    @property
    def latencies(self) -> List[Dict[str, Any]]:
        """Shallow copy of accumulated latency records."""
        return list(self._latencies)

    @latencies.setter
    def latencies(self, value: List[Dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        self._latencies = list(value)
        self._cached_stats = None

    def reset(self) -> None:
        """Clear all latency records."""
        self._latencies.clear()
        self._cached_stats = None
        self._ttft_records.clear()  # C1

    def record_latency(self, task_id: str, task_type: str,
                       total_time: float, breakdown: Dict[str, float]):
        """Record latency for a task"""
        self._cached_stats = None  # invalidate cache on new record
        self._latencies.append({
            "task_id": task_id,
            "task_type": task_type,
            "total_time": total_time,
            "breakdown": breakdown,
            "timestamp": datetime.now()
        })

    def get_latency_stats(self, task_type: Optional[str] = None) -> Dict[str, float]:
        """Get latency statistics.

        Results for the full dataset (``task_type=None``) are cached and
        reused until the next :meth:`record_latency` / :meth:`reset` call.
        Per-type queries bypass the cache (uncommon, low-volume path).
        """
        if task_type:
            # Per-type query: filter then compute without touching the cache
            filtered = [lat for lat in self._latencies if lat["task_type"] == task_type]
            return self._compute_stats(filtered)

        # Full-dataset query: use cache
        if self._cached_stats is not None:
            return self._cached_stats

        self._cached_stats = self._compute_stats(self._latencies)
        return self._cached_stats

    def _compute_stats(self, latencies: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute latency statistics from a list of latency records."""
        if not latencies:
            return {"mean": 0.0, "median": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0,
                    "min": 0.0, "max": 0.0, "std": 0.0}

        times = [lat["total_time"] for lat in latencies]

        return {
            "mean": round(statistics.mean(times), 4),
            "median": round(statistics.median(times), 4),
            "p50": round(np.percentile(times, 50), 4),
            "p90": round(np.percentile(times, 90), 4),
            "p95": round(np.percentile(times, 95), 4),
            "p99": round(np.percentile(times, 99), 4),
            "min": round(min(times), 4),
            "max": round(max(times), 4),
            "std": round(statistics.stdev(times) if len(times) > 1 else 0, 4),
        }

    def analyze_bottlenecks(self) -> Dict[str, Any]:
        """Identify performance bottlenecks"""
        if not self._latencies:
            return {}

        # Aggregate breakdown times
        breakdown_totals = defaultdict(float)
        breakdown_counts = defaultdict(int)

        for latency in self._latencies:
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
        if not self._latencies:
            return {}

        # Group latencies by task type
        latencies_by_type = defaultdict(list)
        for latency in self._latencies:
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

    @property
    def ttft_records(self) -> List[Dict[str, Any]]:
        """Shallow copy of TTFT records."""
        return list(self._ttft_records)

    def track_ttft(self, task_id: str, ttft_seconds: float, task_type: str = "unknown") -> None:
        """스트리밍 응답의 첫 번째 토큰까지의 시간(TTFT)을 기록한다 (C1).

        Args:
            task_id: 태스크 ID.
            ttft_seconds: 첫 번째 토큰까지 걸린 시간(초).
            task_type: 태스크 유형.

        Example::

            tracker.track_ttft("task_001", 0.35, task_type="qa")
            stats = tracker.get_ttft_stats()
            # {"mean": 0.35, "p95": 0.35, ...}
        """
        self._ttft_records.append({
            "task_id": task_id,
            "ttft": ttft_seconds,
            "task_type": task_type,
            "timestamp": datetime.now(),
        })

    def get_ttft_stats(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """TTFT(Time-To-First-Token) 통계를 반환한다 (C1).

        Args:
            task_type: 특정 task_type 필터. ``None`` 이면 전체.

        Returns:
            mean, p50, p95, p99, min, max, count 통계 dict.
            기록이 없으면 모두 0.0 반환.
        """
        records = self._ttft_records
        if task_type:
            records = [r for r in records if r["task_type"] == task_type]
        if not records:
            return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0,
                    "min": 0.0, "max": 0.0, "count": 0}
        times = [r["ttft"] for r in records]
        return {
            "mean": round(statistics.mean(times), 3),
            "p50": round(float(np.percentile(times, 50)), 3),
            "p95": round(float(np.percentile(times, 95)), 3),
            "p99": round(float(np.percentile(times, 99)), 3),
            "min": round(min(times), 3),
            "max": round(max(times), 3),
            "count": len(times),
        }

    def check_sla_compliance(self, sla_targets: Dict[str, float]) -> Dict[str, Any]:
        """Check SLA compliance"""
        results = {}

        for task_type, target in sla_targets.items():
            type_latencies = [
                l["total_time"] for l in self._latencies
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
            round(statistics.mean(l["total_time"] for l in self._latencies), 3)
            if self._latencies else 0.0
        )
        return f"LatencyTracker(records={len(self._latencies)}, mean={mean}s)"


# ============================================================================
# 6. Token Economy Tracker
# ============================================================================

class TokenEconomyTracker(BaseTracker):
    """Track token usage and costs"""

    def __init__(self, pricing: Dict[str, float]):
        """
        Args:
            pricing: {"input": cost_per_1k_tokens, "output": cost_per_1k_tokens}

        Raises:
            ValidationError: If required keys are missing or any price value is negative.
        """
        # L1/H2: validate required keys before iterating values
        for required_key in ("input", "output"):
            if required_key not in (pricing or {}):
                raise ValidationError(
                    f"pricing must contain '{required_key}' key. "
                    f"Expected: {{\"input\": float, \"output\": float}}, got: {list((pricing or {}).keys())}"
                )
        for key, price in (pricing or {}).items():
            if not isinstance(price, (int, float)):
                raise ValidationError(
                    f"pricing['{key}'] = {price!r} is invalid: expected a numeric value (int or float)"
                )
            if price < 0:
                raise ValidationError(
                    f"pricing['{key}'] = {price} is invalid: token prices must be >= 0"
                )
        self.pricing = pricing
        self._usage_log: List[Dict[str, Any]] = []

    @property
    def usage_log(self) -> List[Dict[str, Any]]:
        """Shallow copy of accumulated usage records."""
        return list(self._usage_log)

    @usage_log.setter
    def usage_log(self, value: List[Dict[str, Any]]) -> None:
        """Restore internal state (used by load_from_file)."""
        self._usage_log = list(value)

    def reset(self) -> None:
        """Clear all token usage records."""
        self._usage_log.clear()

    def update_pricing(self, pricing: Dict[str, float]) -> None:
        """Update token pricing after construction.

        Useful when switching models during a long evaluation session without
        creating a new ``PerformanceMonitor`` instance.  Applies the same
        validation as ``__init__``.

        Args:
            pricing: ``{"input": cost_per_1k_tokens, "output": cost_per_1k_tokens}``

        Raises:
            ValidationError: If required keys are missing or any price is invalid.

        Example::

            monitor.token_tracker.update_pricing({"input": 0.003, "output": 0.015})
        """
        for required_key in ("input", "output"):
            if required_key not in (pricing or {}):
                raise ValidationError(
                    f"pricing must contain '{required_key}' key. "
                    f"Expected: {{\"input\": float, \"output\": float}}, "
                    f"got: {list((pricing or {}).keys())}"
                )
        for key, price in (pricing or {}).items():
            if not isinstance(price, (int, float)):
                raise ValidationError(
                    f"pricing['{key}'] = {price!r} is invalid: expected a numeric value (int or float)"
                )
            if price < 0:
                raise ValidationError(
                    f"pricing['{key}'] = {price} is invalid: token prices must be >= 0"
                )
        self.pricing = pricing

    def track_usage(self, task_id: str, input_tokens: int,
                   output_tokens: int, task_type: str, model: str = "default",
                   framework: str = "native"):
        """Track token usage for a task"""
        total_tokens = input_tokens + output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        self._usage_log.append({
            "task_id": task_id,
            "task_type": task_type,
            "model": model,
            "framework": framework,
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
        if not self._usage_log:
            return {
                "total_tasks": 0, "total_tokens": 0,
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_cost": 0.0, "avg_tokens_per_task": 0.0,
                "avg_cost_per_task": 0.0, "estimated_monthly_cost": 0.0,
                "token_distribution": {"input_ratio": 0.0, "output_ratio": 0.0},
                "cost_percentiles": {"p50": 0.0, "p90": 0.0, "p95": 0.0},
            }

        df = pd.DataFrame(self._usage_log)

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
            "cost_percentiles": self._compute_cost_percentiles(df)
        }

    def _compute_cost_percentiles(self, df: "pd.DataFrame") -> Dict[str, float]:
        """p50/p90/p95 비용 백분위 계산.

        소표본(n<5)에서는 선형 보간 결과가 불안정할 수 있으므로 경고를 발생시킨다.
        """
        n = len(df)
        if n < 5:
            logger.debug(
                "Cost percentile calculation may be unreliable with only %d sample(s). "
                "Collect more tasks for stable percentile estimates (recommended: ≥20).",
                n,
            )
        return {
            "p50": round(df["cost"].quantile(0.5), 4),
            "p90": round(df["cost"].quantile(0.9), 4),
            "p95": round(df["cost"].quantile(0.95), 4),
        }

    def get_usage_by_type(self) -> Dict[str, Dict[str, float]]:
        """Get usage breakdown by task type"""
        if not self._usage_log:
            return {}

        df = pd.DataFrame(self._usage_log)
        grouped = df.groupby("task_type").agg({
            "total_tokens": ["sum", "mean"],
            "cost": ["sum", "mean"]
        }).round(2)

        # Flatten multi-level columns to strings (e.g. ("total_tokens", "sum") → "total_tokens_sum")
        # then return {task_type: {stat_name: value}} via orient='index'.
        grouped.columns = ["_".join(col) for col in grouped.columns]
        return grouped.to_dict("index")

    def get_cost_breakdown_by_model(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed cost breakdown by model"""
        if not self._usage_log:
            return {}

        # Group by model
        model_data = defaultdict(lambda: {
            "input_tokens": [],
            "output_tokens": [],
            "total_tokens": [],
            "costs": [],
            "task_count": 0
        })

        for entry in self._usage_log:
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

    def get_cost_breakdown_by_framework(self) -> Dict[str, Dict[str, Any]]:
        """프레임워크별 비용 분류를 반환한다 (C2).

        ``_usage_log`` 의 ``framework`` 필드 기준으로 집계한다.
        framework 정보가 없으면 ``"unknown"`` 으로 분류한다.

        Returns:
            Dict mapping framework → {total_cost, avg_cost_per_task, task_count,
            total_tokens, avg_tokens_per_task}.

        Example::

            breakdown = tracker.get_cost_breakdown_by_framework()
            # {"anthropic": {"total_cost": 0.05, "task_count": 10, ...},
            #  "openai":    {"total_cost": 0.03, "task_count": 5,  ...}}
        """
        if not self._usage_log:
            return {}

        framework_data: Dict[str, Dict[str, Any]] = {}
        for entry in self._usage_log:
            fw = str(entry.get("framework", "unknown") or "unknown")
            if fw not in framework_data:
                framework_data[fw] = {"costs": [], "tokens": [], "task_count": 0}
            framework_data[fw]["costs"].append(float(entry.get("cost", 0.0)))
            framework_data[fw]["tokens"].append(int(entry.get("total_tokens", 0)))
            framework_data[fw]["task_count"] += 1

        result: Dict[str, Dict[str, Any]] = {}
        for fw, data in framework_data.items():
            costs = data["costs"]
            tokens = data["tokens"]
            result[fw] = {
                "total_cost": round(sum(costs), 4),
                "avg_cost_per_task": round(statistics.mean(costs), 4) if costs else 0.0,
                "task_count": data["task_count"],
                "total_tokens": sum(tokens),
                "avg_tokens_per_task": round(statistics.mean(tokens), 2) if tokens else 0.0,
            }
        return result

    def __repr__(self) -> str:
        total_cost = sum(r.get("cost", 0) for r in self._usage_log)
        return (
            f"TokenEconomyTracker(records={len(self._usage_log)}, "
            f"total_cost=${total_cost:.4f})"
        )


class MultimodalMetricsTracker(BaseTracker):
    """멀티모달 입출력 지표 추적기 (F3).

    태스크의 ``extra`` 딕셔너리에서 이미지/오디오/비디오 메타데이터를 추출해
    모달리티별 사용 현황을 집계한다.

    Example::
        tracker = MultimodalMetricsTracker()
        tracker.track_multimodal(task_result)
        summary = tracker.get_multimodal_summary()
    """

    def __init__(self) -> None:
        self._image_count: int = 0
        self._audio_seconds: float = 0.0
        self._video_frames: int = 0
        self._modality_mix: dict = {}
        self._tracked: int = 0

    def reset(self) -> None:
        self.__init__()

    def track_multimodal(self, task: TaskResult) -> None:
        """태스크에서 멀티모달 지표를 추출해 누적한다.

        Args:
            task: 분석할 TaskResult 인스턴스.
                  ``extra["image_count"]``, ``extra["audio_duration_seconds"]``,
                  ``extra["video_frames"]`` 키를 읽는다.
        """
        extra = getattr(task, "extra", {}) or {}
        imgs = int(extra.get("image_count", 0) or 0)
        audio = float(extra.get("audio_duration_seconds", 0) or 0)
        frames = int(extra.get("video_frames", 0) or 0)

        self._image_count += imgs
        self._audio_seconds += audio
        self._video_frames += frames
        self._tracked += 1

        modalities = []
        if imgs > 0:
            modalities.append("image")
        if audio > 0:
            modalities.append("audio")
        if frames > 0:
            modalities.append("video")
        if not modalities:
            modalities.append("text")

        for m in modalities:
            self._modality_mix[m] = self._modality_mix.get(m, 0) + 1

    def get_multimodal_summary(self) -> dict:
        """누적된 멀티모달 지표 요약을 반환한다.

        Returns:
            ``{"total_tracked", "image_count", "audio_duration_seconds",
               "video_frames", "modality_mix"}`` 딕셔너리.
        """
        return {
            "total_tracked": self._tracked,
            "image_count": self._image_count,
            "audio_duration_seconds": round(self._audio_seconds, 3),
            "video_frames": self._video_frames,
            "modality_mix": dict(self._modality_mix),
        }
