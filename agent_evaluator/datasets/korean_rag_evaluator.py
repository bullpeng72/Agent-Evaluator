"""
Korean RAG Evaluator
====================
Golden Dataset을 활용한 한국어 RAG 시스템 평가

주요 기능:
- Golden Dataset 기반 자동 평가
- Ragas 메트릭: Faithfulness, Context Recall, Context Precision, Answer Relevancy
- 배치 평가 및 상세 리포트 생성
- RAG 시스템 통합 인터페이스
"""

import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import pandas as pd

# Agent Evaluator 통합
from agent_evaluator import TaskResult, TaskType
from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor
from .korean_rag_dataset_generator import (
    GoldenDataset,
    QAPair,
    GoldenDatasetManager
)

# Ragas (선택적)
try:
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_recall,
        context_precision,
        answer_similarity
    )
    from datasets import Dataset
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RAGResponse:
    """RAG 시스템 응답"""
    question: str
    answer: str
    retrieved_contexts: List[str]
    metadata: Dict[str, Any]


@dataclass
class EvaluationResult:
    """개별 QA 쌍의 평가 결과"""
    qa_id: str
    question: str
    expected_answer: str
    generated_answer: str
    contexts: List[str]

    # Ragas 메트릭
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_recall: Optional[float] = None
    context_precision: Optional[float] = None
    answer_similarity: Optional[float] = None

    # 추가 정보
    evaluation_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class RAGEvaluationReport:
    """전체 RAG 평가 리포트"""
    report_id: str
    dataset_id: str
    evaluated_at: str
    total_qa_pairs: int
    successful_evaluations: int
    failed_evaluations: int

    # 평균 메트릭
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_recall: float
    avg_context_precision: float
    avg_answer_similarity: float

    # 상세 결과
    detailed_results: List[EvaluationResult]

    # 통계
    statistics: Dict[str, Any]
    metadata: Dict[str, Any]


# ============================================================================
# RAG System Interface
# ============================================================================

class RAGSystemInterface:
    """RAG 시스템 인터페이스 - 사용자가 구현해야 하는 추상 클래스"""

    def query(self, question: str) -> RAGResponse:
        """
        RAG 시스템에 질문하고 응답 받기

        Args:
            question: 질문

        Returns:
            RAGResponse (답변 + 검색된 컨텍스트)
        """
        raise NotImplementedError("RAG 시스템의 query 메서드를 구현해야 합니다")


# ============================================================================
# Korean RAG Evaluator
# ============================================================================

class KoreanRAGEvaluator:
    """한국어 RAG 시스템 평가기"""

    @staticmethod
    def _detect_data_directory() -> Path:
        """
        Zero Configuration: 자동으로 데이터 저장 위치 감지

        우선순위:
        1. 환경변수 AGENT_EVALUATOR_DATA_DIR
        2. path_helpers로 프로젝트 루트 탐지 → results/
        3. 홈 디렉토리 ~/.agent_evaluator/data/ (fallback)
        """

        # 1. 환경변수
        if 'AGENT_EVALUATOR_DATA_DIR' in os.environ:
            data_dir = Path(os.environ['AGENT_EVALUATOR_DATA_DIR'])
            if data_dir.exists():
                return data_dir

        # 2. path_helpers로 results/ 탐지
        try:
            from ..utils.path_helpers import get_evaluation_results_dir
            return get_evaluation_results_dir(create=True)
        except ImportError:
            pass

        # 3. Fallback: 홈 디렉토리
        return Path.home() / ".agent_evaluator" / "data"

    def __init__(
        self,
        rag_system: Optional[RAGSystemInterface] = None,
        use_ragas: bool = True,
        ragas_model: str = "gpt-4o-mini",
        output_dir: Optional[str] = None,
        golden_datasets_dir: Optional[str] = None
    ):
        """
        Args:
            rag_system: RAG 시스템 인터페이스
            use_ragas: Ragas 메트릭 사용 여부
            ragas_model: Ragas에서 사용할 모델
            output_dir: 결과 저장 디렉토리 (None이면 자동 감지 - Zero Configuration)
            golden_datasets_dir: Golden Dataset 저장 디렉토리 (None이면 자동 감지)
        """
        self.rag_system = rag_system
        self.use_ragas = use_ragas and RAGAS_AVAILABLE
        self.ragas_model = ragas_model

        # Zero Configuration: 자동 경로 감지
        if output_dir is None:
            self.output_dir = self._detect_data_directory()
        else:
            self.output_dir = Path(output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Golden Dataset Manager - results/golden_datasets/ 사용
        if golden_datasets_dir is None:
            golden_datasets_dir = str(self.output_dir / "golden_datasets")
        self.dataset_manager = GoldenDatasetManager(output_dir=golden_datasets_dir)

        # Hybrid Monitor (optional, for advanced tracking)
        self.monitor = None

        if not self.use_ragas:
            print("⚠️  Ragas를 사용할 수 없습니다. 설치: pip install ragas")

    def set_rag_system(self, rag_system: RAGSystemInterface):
        """RAG 시스템 설정"""
        self.rag_system = rag_system

    def evaluate_dataset(
        self,
        dataset: GoldenDataset,
        use_hybrid_monitor: bool = False,
        max_samples: Optional[int] = None
    ) -> RAGEvaluationReport:
        """
        Golden Dataset으로 RAG 시스템 평가

        Args:
            dataset: Golden Dataset
            use_hybrid_monitor: Hybrid Monitor 사용 여부
            max_samples: 최대 샘플 수 (테스트용)

        Returns:
            평가 리포트
        """
        if self.rag_system is None:
            raise ValueError("RAG 시스템이 설정되지 않았습니다. set_rag_system()을 호출하세요")

        print(f"\n{'='*80}")
        print(f"한국어 RAG 시스템 평가 시작")
        print(f"{'='*80}\n")

        print(f"📊 Dataset: {dataset.dataset_id}")
        print(f"   총 QA 쌍: {dataset.total_qa_pairs}개")

        # Hybrid Monitor 초기화 (선택적)
        if use_hybrid_monitor:
            self.monitor = HybridPerformanceMonitor(
                use_deepeval=False,
                use_ragas=True,
                ragas_model=self.ragas_model
            )

        # 평가할 QA 쌍 선택
        qa_pairs = dataset.qa_pairs
        if max_samples:
            qa_pairs = qa_pairs[:max_samples]
            print(f"   ⚠️  테스트 모드: 최대 {max_samples}개만 평가")

        print(f"   평가 대상: {len(qa_pairs)}개\n")

        # 개별 QA 쌍 평가
        print("🔍 RAG 시스템 평가 진행 중...\n")
        detailed_results = []

        for i, qa in enumerate(qa_pairs, 1):
            print(f"   [{i}/{len(qa_pairs)}] 평가 중: {qa.question[:50]}...", end=" ")

            start_time = datetime.now()
            result = self._evaluate_single_qa(qa)
            elapsed = (datetime.now() - start_time).total_seconds()
            result.evaluation_time = elapsed

            detailed_results.append(result)

            if result.error:
                print(f"❌ 실패: {result.error}")
            else:
                # Handle both float and list values from Ragas
                def format_metric(value):
                    import math
                    if value is None:
                        return "N/A"
                    elif isinstance(value, float) and math.isnan(value):
                        return "N/A"
                    elif isinstance(value, list):
                        # If list, take the mean or first value
                        return f"{sum(value)/len(value):.2f}" if value else "N/A"
                    else:
                        return f"{value:.2f}"

                faith_str = format_metric(result.faithfulness)
                rel_str = format_metric(result.answer_relevancy)
                print(f"✓ (Faith: {faith_str}, Rel: {rel_str})")

            # Hybrid Monitor에 기록 (선택적)
            if self.monitor:
                self._record_to_monitor(qa, result)

        print(f"\n   ✓ {len(detailed_results)}개 평가 완료\n")

        # 리포트 생성
        report = self._generate_report(dataset, detailed_results)

        # 리포트 출력
        self._print_report(report)

        # 저장
        saved_path = self._save_report(report)
        print(f"\n💾 평가 리포트 저장: {saved_path}\n")

        return report

    def evaluate_single(
        self,
        question: str,
        expected_answer: str,
        ground_truth_context: Optional[str] = None
    ) -> EvaluationResult:
        """
        단일 질문 평가

        Args:
            question: 질문
            expected_answer: 기대 답변
            ground_truth_context: Ground truth 컨텍스트 (선택적)

        Returns:
            평가 결과
        """
        if self.rag_system is None:
            raise ValueError("RAG 시스템이 설정되지 않았습니다")

        # QAPair 생성
        qa = QAPair(
            qa_id="single_eval",
            question=question,
            answer="",  # 생성될 것임
            context=ground_truth_context or "",
            ground_truth=expected_answer,
            metadata={}
        )

        # 평가
        result = self._evaluate_single_qa(qa)

        return result

    def _evaluate_single_qa(self, qa: QAPair) -> EvaluationResult:
        """개별 QA 쌍 평가"""
        try:
            # 1. RAG 시스템에서 응답 생성
            rag_response = self.rag_system.query(qa.question)

            # 2. Ragas 메트릭 계산
            metrics = {}

            if self.use_ragas:
                metrics = self._calculate_ragas_metrics(
                    question=qa.question,
                    answer=rag_response.answer,
                    contexts=rag_response.retrieved_contexts,
                    ground_truth=qa.ground_truth
                )

            # 3. 결과 생성
            result = EvaluationResult(
                qa_id=qa.qa_id,
                question=qa.question,
                expected_answer=qa.ground_truth,
                generated_answer=rag_response.answer,
                contexts=rag_response.retrieved_contexts,
                faithfulness=metrics.get("faithfulness"),
                answer_relevancy=metrics.get("answer_relevancy"),
                context_recall=metrics.get("context_recall"),
                context_precision=metrics.get("context_precision"),
                answer_similarity=metrics.get("answer_similarity"),
                metadata=rag_response.metadata
            )

            return result

        except Exception as e:
            # 에러 발생 시
            return EvaluationResult(
                qa_id=qa.qa_id,
                question=qa.question,
                expected_answer=qa.ground_truth,
                generated_answer="",
                contexts=[],
                error=str(e),
                metadata={}
            )

    def _calculate_ragas_metrics(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: str
    ) -> Dict[str, float]:
        """Ragas 메트릭 계산"""
        if not self.use_ragas:
            return {}

        try:
            # Configure Ragas to use OpenAI via LangChain
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings

            # Initialize LLM and embeddings for Ragas
            llm = ChatOpenAI(model=self.ragas_model, temperature=0)
            embeddings = OpenAIEmbeddings()

            # Ragas Dataset 생성
            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
                "ground_truth": [ground_truth]
            }

            dataset = Dataset.from_dict(data)

            # 평가 실행 with explicit LLM
            result = evaluate(
                dataset,
                metrics=[
                    faithfulness,
                    answer_relevancy,
                    context_recall,
                    context_precision,
                    answer_similarity
                ],
                llm=llm,
                embeddings=embeddings
            )

            # 결과 추출
            metrics = {
                "faithfulness": result["faithfulness"],
                "answer_relevancy": result["answer_relevancy"],
                "context_recall": result["context_recall"],
                "context_precision": result["context_precision"],
                "answer_similarity": result["answer_similarity"]
            }

            return metrics

        except Exception as e:
            print(f"⚠️  Ragas 메트릭 계산 실패: {e}")
            return {}

    def _generate_report(
        self,
        dataset: GoldenDataset,
        results: List[EvaluationResult]
    ) -> RAGEvaluationReport:
        """평가 리포트 생성"""
        # 성공/실패 카운트
        successful = [r for r in results if r.error is None]
        failed = [r for r in results if r.error is not None]

        # 평균 메트릭 계산
        def safe_mean(values):
            """Calculate mean, handling both float and list values from Ragas"""
            valid = []
            for v in values:
                if v is None:
                    continue
                elif isinstance(v, list):
                    # If list, take the mean of the list
                    if v:
                        valid.append(sum(v) / len(v))
                else:
                    valid.append(v)
            return sum(valid) / len(valid) if valid else 0.0

        avg_metrics = {
            "faithfulness": safe_mean([r.faithfulness for r in successful]),
            "answer_relevancy": safe_mean([r.answer_relevancy for r in successful]),
            "context_recall": safe_mean([r.context_recall for r in successful]),
            "context_precision": safe_mean([r.context_precision for r in successful]),
            "answer_similarity": safe_mean([r.answer_similarity for r in successful])
        }

        # 통계 - 안전하게 min/max 계산, list 값 처리
        def extract_value(v):
            """Extract float value from either float or list"""
            if v is None:
                return None
            elif isinstance(v, list):
                return sum(v) / len(v) if v else None
            else:
                return v

        faithfulness_values = [extract_value(r.faithfulness) for r in successful if extract_value(r.faithfulness) is not None]
        answer_relevancy_values = [extract_value(r.answer_relevancy) for r in successful if extract_value(r.answer_relevancy) is not None]

        statistics = {
            "total_evaluation_time": sum(r.evaluation_time for r in results),
            "avg_evaluation_time": sum(r.evaluation_time for r in results) / len(results) if results else 0,
            "min_faithfulness": min(faithfulness_values) if faithfulness_values else 0,
            "max_faithfulness": max(faithfulness_values) if faithfulness_values else 0,
            "min_answer_relevancy": min(answer_relevancy_values) if answer_relevancy_values else 0,
            "max_answer_relevancy": max(answer_relevancy_values) if answer_relevancy_values else 0
        }

        # 리포트 생성
        report = RAGEvaluationReport(
            report_id=self._generate_report_id(),
            dataset_id=dataset.dataset_id,
            evaluated_at=datetime.now().isoformat(),
            total_qa_pairs=len(results),
            successful_evaluations=len(successful),
            failed_evaluations=len(failed),
            avg_faithfulness=avg_metrics["faithfulness"],
            avg_answer_relevancy=avg_metrics["answer_relevancy"],
            avg_context_recall=avg_metrics["context_recall"],
            avg_context_precision=avg_metrics["context_precision"],
            avg_answer_similarity=avg_metrics["answer_similarity"],
            detailed_results=results,
            statistics=statistics,
            metadata={
                "source_document": dataset.source_document,
                "ragas_model": self.ragas_model if self.use_ragas else None
            }
        )

        return report

    def _print_report(self, report: RAGEvaluationReport):
        """리포트 출력"""
        print(f"{'='*80}")
        print(f"📊 RAG 평가 리포트")
        print(f"{'='*80}\n")

        print(f"리포트 ID: {report.report_id}")
        print(f"평가 시간: {report.evaluated_at}")
        print(f"Dataset: {report.dataset_id}")
        print(f"소스 문서: {report.metadata.get('source_document', 'N/A')}\n")

        print(f"{'='*80}")
        print(f"평가 결과 요약")
        print(f"{'='*80}\n")

        print(f"총 QA 쌍: {report.total_qa_pairs}개")
        print(f"성공: {report.successful_evaluations}개")
        print(f"실패: {report.failed_evaluations}개")
        print(f"성공률: {report.successful_evaluations / report.total_qa_pairs * 100:.1f}%\n")

        if report.successful_evaluations > 0:
            print(f"{'='*80}")
            print(f"Ragas 메트릭 (평균)")
            print(f"{'='*80}\n")

            metrics = [
                ("Faithfulness", report.avg_faithfulness, 0.8),
                ("Answer Relevancy", report.avg_answer_relevancy, 0.8),
                ("Context Recall", report.avg_context_recall, 0.8),
                ("Context Precision", report.avg_context_precision, 0.8),
                ("Answer Similarity", report.avg_answer_similarity, 0.8)
            ]

            for name, value, threshold in metrics:
                if value is not None:
                    status = "✓" if value >= threshold else "✗"
                    print(f"{status} {name:20s}: {value:.3f} (목표: {threshold:.1f})")
                else:
                    print(f"? {name:20s}: N/A (목표: {threshold:.1f})")

            print(f"\n{'='*80}")
            print(f"통계")
            print(f"{'='*80}\n")

            total_time = report.statistics.get('total_evaluation_time', 0)
            avg_time = report.statistics.get('avg_evaluation_time', 0)
            print(f"총 평가 시간: {total_time:.2f}초")
            print(f"평균 평가 시간: {avg_time:.2f}초/개")

            min_faith = report.statistics.get('min_faithfulness')
            max_faith = report.statistics.get('max_faithfulness')
            if min_faith is not None and max_faith is not None:
                print(f"Faithfulness 범위: {min_faith:.3f} ~ {max_faith:.3f}")

            min_rel = report.statistics.get('min_answer_relevancy')
            max_rel = report.statistics.get('max_answer_relevancy')
            if min_rel is not None and max_rel is not None:
                print(f"Answer Relevancy 범위: {min_rel:.3f} ~ {max_rel:.3f}")

        print(f"\n{'='*80}\n")

    def _save_report(self, report: RAGEvaluationReport, format: str = "json") -> str:
        """리포트 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rag_evaluation_{report.report_id}_{timestamp}.{format}"
        filepath = self.output_dir / filename

        if format == "json":
            # 상세 결과는 별도 파일로
            summary_data = {
                "report_id": report.report_id,
                "dataset_id": report.dataset_id,
                "evaluated_at": report.evaluated_at,
                "total_qa_pairs": report.total_qa_pairs,
                "successful_evaluations": report.successful_evaluations,
                "failed_evaluations": report.failed_evaluations,
                "avg_metrics": {
                    "faithfulness": report.avg_faithfulness,
                    "answer_relevancy": report.avg_answer_relevancy,
                    "context_recall": report.avg_context_recall,
                    "context_precision": report.avg_context_precision,
                    "answer_similarity": report.avg_answer_similarity
                },
                "statistics": report.statistics,
                "metadata": report.metadata
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)

            # 상세 결과 저장
            details_filename = f"rag_evaluation_details_{report.report_id}_{timestamp}.json"
            details_filepath = self.output_dir / details_filename

            details_data = [asdict(r) for r in report.detailed_results]

            with open(details_filepath, 'w', encoding='utf-8') as f:
                json.dump(details_data, f, ensure_ascii=False, indent=2)

            print(f"   ✓ 상세 결과: {details_filepath}")

        elif format == "csv":
            # CSV로 저장
            rows = []
            for r in report.detailed_results:
                row = {
                    "qa_id": r.qa_id,
                    "question": r.question,
                    "expected_answer": r.expected_answer,
                    "generated_answer": r.generated_answer,
                    "faithfulness": r.faithfulness,
                    "answer_relevancy": r.answer_relevancy,
                    "context_recall": r.context_recall,
                    "context_precision": r.context_precision,
                    "answer_similarity": r.answer_similarity,
                    "evaluation_time": r.evaluation_time,
                    "error": r.error or ""
                }
                rows.append(row)

            df = pd.DataFrame(rows)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')

        return str(filepath)

    def _record_to_monitor(self, qa: QAPair, result: EvaluationResult):
        """Hybrid Monitor에 기록"""
        if not self.monitor:
            return

        task = TaskResult(
            task_id=result.qa_id,
            task_type=TaskType.QA.value,
            success=result.error is None,
            completion_score=1.0 if result.error is None else 0.0,
            accuracy_score=result.answer_similarity or 0.0,
            execution_time=result.evaluation_time,
            tokens_used={"input": 0, "output": 0, "total": 0},  # TODO: track tokens
            tool_calls=[],
            attempts=1,
            errors=[result.error] if result.error else [],
            timestamp=datetime.now()
        )

        self.monitor.record_task(
            task,
            enable_advanced_metrics=True,
            input_text=result.question,
            output_text=result.generated_answer,
            expected_output=result.expected_answer,
            retrieved_context=result.contexts
        )

    def _generate_report_id(self) -> str:
        """리포트 ID 생성"""
        import hashlib
        timestamp = datetime.now().isoformat()
        return hashlib.md5(timestamp.encode()).hexdigest()[:8]


# ============================================================================
# Example RAG System Implementation
# ============================================================================

class SimpleRAGSystem(RAGSystemInterface):
    """
    간단한 RAG 시스템 예제
    실제 사용 시 OpenAI, LangChain 등을 활용하여 구현
    """

    def __init__(self, knowledge_base: List[str]):
        """
        Args:
            knowledge_base: 검색할 문서 리스트
        """
        self.knowledge_base = knowledge_base

    def query(self, question: str) -> RAGResponse:
        """
        간단한 키워드 매칭 기반 검색 + 더미 답변 생성
        실제로는 벡터 검색 + LLM 생성을 사용해야 함
        """
        # 1. 검색 (간단한 키워드 매칭)
        retrieved_contexts = self._retrieve(question)

        # 2. 답변 생성 (더미 - 실제로는 LLM 사용)
        answer = f"검색된 {len(retrieved_contexts)}개의 문서를 바탕으로 답변합니다..."

        return RAGResponse(
            question=question,
            answer=answer,
            retrieved_contexts=retrieved_contexts,
            metadata={"num_retrieved": len(retrieved_contexts)}
        )

    def _retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """간단한 키워드 매칭 검색"""
        query_words = set(query.lower().split())

        scores = []
        for doc in self.knowledge_base:
            doc_words = set(doc.lower().split())
            overlap = len(query_words & doc_words)
            scores.append((doc, overlap))

        # 상위 k개 반환
        scores.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scores[:top_k]]


# ============================================================================
# Example Usage
# ============================================================================

def example_evaluate_rag():
    """RAG 시스템 평가 예제"""

    # 1. Golden Dataset 로드
    manager = GoldenDatasetManager()
    dataset = manager.load_dataset("golden_datasets/your_dataset.json")

    # 2. RAG 시스템 초기화 (여기서는 간단한 예제 사용)
    knowledge_base = [
        "한국의 수도는 서울입니다.",
        "서울은 한국의 정치, 경제, 문화의 중심지입니다.",
        "한국은 아시아 동쪽에 위치한 국가입니다."
    ]
    rag_system = SimpleRAGSystem(knowledge_base)

    # 3. 평가기 초기화
    evaluator = KoreanRAGEvaluator(
        rag_system=rag_system,
        use_ragas=True,
        ragas_model="gpt-4o-mini"
    )

    # 4. 평가 실행
    report = evaluator.evaluate_dataset(
        dataset,
        use_hybrid_monitor=False,
        max_samples=5  # 테스트용
    )

    return report


if __name__ == "__main__":
    print("""
Korean RAG Evaluator
====================

사용 방법:

1. Golden Dataset 준비:
   - korean_rag_dataset_generator.py로 생성
   - 또는 기존 데이터셋 로드

2. RAG 시스템 구현:
   - RAGSystemInterface를 상속받아 구현
   - query() 메서드 구현

3. 평가 실행:
   evaluator = KoreanRAGEvaluator(rag_system=your_rag_system)
   report = evaluator.evaluate_dataset(dataset)

필수 라이브러리:
   pip install ragas langchain-openai datasets

예제 실행:
   - example_evaluate_rag()
""")
