"""
Korean RAG Dataset Generator
=============================
한국어 PDF 문서에서 RAG 평가를 위한 Ground Truth (Golden Data) 생성

주요 기능:
- PDF 파일에서 한국어 텍스트 추출
- AI를 활용한 QA 쌍 자동 생성
- Faithfulness, Context Recall, Context Precision, Answer Relevancy 평가를 위한 데이터셋 구축
- Golden data 저장/로드 (JSON, CSV)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Pre-compiled patterns for clean_text() and _parse_qa_pairs()
_RE_MULTI_SPACE = re.compile(r'\s+')
_RE_MULTI_NEWLINE = re.compile(r'\n{3,}')
_RE_QA_QUESTION = re.compile(r'질문:\s*(.+?)(?=\n|답변:|$)', re.DOTALL)
_RE_QA_ANSWER = re.compile(r'답변:\s*(.+?)(?=\n|ground_truth:|$)', re.DOTALL)
_RE_QA_GT = re.compile(r'ground_truth:\s*(.+?)(?=\n|---|\Z)', re.DOTALL)

# PDF 처리
try:
    import pdfplumber
    PDF_LIBRARY = "pdfplumber"
except ImportError:
    PDF_LIBRARY = None

# OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]
    OPENAI_AVAILABLE = False

# 기타 의존성
import pandas as pd
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DocumentChunk:
    """문서 청크 정보"""
    chunk_id: str
    content: str
    page_number: int
    chunk_index: int
    metadata: dict[str, Any]


@dataclass
class QAPair:
    """질문-답변 쌍"""
    qa_id: str
    question: str
    answer: str
    context: str
    ground_truth: str  # 기대되는 정답
    metadata: dict[str, Any]

    # Layer 2: Agentic AI Metrics 필드 (Optional)
    expected_tools: list[str] | None = None  # Tool Selection 평가용
    expected_agents: list[str] | None = None  # Agent Coordination 평가용
    expected_workflow_steps: list[str] | None = None  # Workflow Execution 평가용


@dataclass
class GoldenDataset:
    """Golden Dataset - RAG 평가용"""
    dataset_id: str
    source_document: str
    created_at: str
    total_qa_pairs: int
    qa_pairs: list[QAPair]
    metadata: dict[str, Any]


# ============================================================================
# PDF Text Extractor
# ============================================================================

class KoreanPDFExtractor:
    """한국어 PDF 텍스트 추출기"""

    def __init__(self):
        if PDF_LIBRARY is None:
            raise ImportError(
                "PDF 처리 라이브러리가 필요합니다:\n"
                "pip install pdfplumber  또는  pip install 'agent-evaluator[all]'"
            )
        self.library = PDF_LIBRARY

    def extract_text(self, pdf_path: str) -> list[tuple[int, str]]:
        """
        PDF에서 텍스트 추출

        Args:
            pdf_path: PDF 파일 경로

        Returns:
            List of (page_number, text) tuples
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        return self._extract_with_pdfplumber(pdf_path)

    def _extract_with_pdfplumber(self, pdf_path: str) -> list[tuple[int, str]]:
        """pdfplumber를 사용한 텍스트 추출 (더 정확함)"""
        import logging
        import warnings

        import pdfplumber

        # Suppress FontBBox warnings from pdfminer
        logging.getLogger('pdfminer').setLevel(logging.ERROR)

        # Suppress all warnings during PDF processing
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            pages_text = []

            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text and text.strip():
                        pages_text.append((page_num, text))

        return pages_text

    def clean_text(self, text: str) -> str:
        """텍스트 정제"""
        # 여러 개의 연속된 공백을 하나로
        text = _RE_MULTI_SPACE.sub(' ', text)

        # 여러 개의 연속된 줄바꿈을 최대 2개로
        text = _RE_MULTI_NEWLINE.sub('\n\n', text)

        # 앞뒤 공백 제거
        text = text.strip()

        return text


# ============================================================================
# Text Chunker
# ============================================================================

class TextChunker:
    """텍스트 청킹 - 의미 단위로 분할"""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Args:
            chunk_size: 청크 크기 (문자 수)
            chunk_overlap: 청크 간 겹침 (문자 수)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_documents(self, pages_text: list[tuple[int, str]]) -> list[DocumentChunk]:
        """문서를 청크로 분할"""
        chunks = []
        chunk_index = 0

        for page_num, text in pages_text:
            page_chunks = self._chunk_text(text, page_num)

            for chunk_text in page_chunks:
                chunk_id = self._generate_chunk_id(page_num, chunk_index, chunk_text)

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    content=chunk_text,
                    page_number=page_num,
                    chunk_index=chunk_index,
                    metadata={
                        "char_count": len(chunk_text),
                        "word_count": len(chunk_text.split())
                    }
                )

                chunks.append(chunk)
                chunk_index += 1

        return chunks

    def _chunk_text(self, text: str, page_num: int) -> list[str]:
        """텍스트를 청크로 분할"""
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + self.chunk_size

            # 청크 경계를 문장 끝으로 조정
            if end < text_length:
                # 마침표, 느낌표, 물음표 등을 찾아서 조정
                for punct in ['. ', '.\n', '! ', '!\n', '? ', '?\n', '。', '！', '？']:
                    punct_pos = text.rfind(punct, start, end)
                    if punct_pos != -1:
                        end = punct_pos + len(punct)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # 다음 청크 시작 위치 (오버랩 고려)
            start = end - self.chunk_overlap

        return chunks

    def _generate_chunk_id(self, page_num: int, chunk_index: int, text: str) -> str:
        """청크 ID 생성"""
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"chunk_p{page_num}_i{chunk_index}_{text_hash}"


# ============================================================================
# QA Pair Generator
# ============================================================================

class KoreanQAGenerator:
    """한국어 QA 쌍 생성기 (OpenAI GPT 사용)"""

    def __init__(self, api_key: str | None = None, model: str = "gpt-5-nano"):
        """
        Args:
            api_key: OpenAI API 키 (없으면 환경 변수에서 가져옴)
            model: 사용할 모델 (gpt-5-nano, gpt-4o, gpt-3.5-turbo 등)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library required: pip install openai")
        assert OpenAI is not None  # OPENAI_AVAILABLE=True면 위 import가 이미 성공한 상태

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set")

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def generate_qa_pairs(
        self,
        chunk: DocumentChunk,
        num_questions: int = 3,
        question_types: list[str] | None = None
    ) -> list[QAPair]:
        """
        청크에서 QA 쌍 생성

        Args:
            chunk: 문서 청크
            num_questions: 생성할 질문 수
            question_types: 질문 유형 (factual, reasoning, summary 등)

        Returns:
            생성된 QA 쌍 리스트
        """
        if question_types is None:
            question_types = ["factual", "reasoning", "summary"]

        prompt = self._build_prompt(chunk.content, num_questions, question_types)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "당신은 한국어 교육 자료를 만드는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            qa_pairs_text = response.choices[0].message.content or ""
            qa_pairs = self._parse_qa_pairs(qa_pairs_text, chunk)

            return qa_pairs

        except Exception as e:
            print(f"⚠️  QA generation failed (chunk_id: {chunk.chunk_id}): {str(e)}")
            return []

    def _build_prompt(self, context: str, num_questions: int, question_types: list[str]) -> str:
        """프롬프트 생성"""
        types_desc = {
            "factual": "사실 확인 질문 (문서에 명시된 정보)",
            "reasoning": "추론 질문 (문서 내용을 바탕으로 한 논리적 추론)",
            "summary": "요약 질문 (문서의 주요 내용 요약)"
        }

        types_str = "\n".join([f"- {types_desc.get(t, t)}" for t in question_types])

        prompt = f"""
다음 한국어 문서 내용을 읽고, RAG 시스템 평가를 위한 고품질 질문-답변 쌍을 {num_questions}개 생성해주세요.

[문서 내용]
{context}

[요구사항]
1. 질문 유형:
{types_str}

2. 각 QA 쌍은 다음 형식으로 작성:
---
질문: [명확하고 구체적인 질문]
답변: [문서 내용을 바탕으로 한 완전한 답변 (2-3문장)]
ground_truth: [평가를 위한 핵심 정답 (1-2문장, 간결하게)]
---

3. 답변은 반드시 주어진 문서 내용만을 기반으로 작성하세요.

4. 질문은 자연스럽고 실제 사용자가 물어볼 법한 형태로 작성하세요.

5. Ground truth는 RAG 시스템 평가를 위한 기준 답변입니다.

6. **중요: 다음과 같은 질문은 절대 생성하지 마세요:**
   ❌ 메타 정보 질문: "몇 페이지인가요?", "문서의 구조는?", "총 섹션은 몇 개인가요?"
   ❌ 문서 외부 질문: "다른 도구와 비교하면?", "앞으로 어떻게 발전할까요?"
   ❌ 추상적 질문: "이 기술의 미래는?", "왜 중요한가요?" (문서에 답이 없는 경우)
   ✅ 문서 내용 질문: 구체적인 기능, 사용법, 개념, 절차, 예시 등

7. **좋은 질문 예시:**
   - "CrewAI에서 에이전트를 생성하는 방법은 무엇인가요?"
   - "Task의 필수 파라미터에는 어떤 것들이 있나요?"
   - "Sequential Process와 Hierarchical Process의 차이점은 무엇인가요?"

생성해주세요:
"""
        return prompt

    def _parse_qa_pairs(self, response_text: str, chunk: DocumentChunk) -> list[QAPair]:
        """AI 응답에서 QA 쌍 파싱"""
        qa_pairs = []

        # "---"로 구분된 블록들을 찾기
        blocks = response_text.split("---")

        for i, block in enumerate(blocks):
            if not block.strip():
                continue

            # 질문, 답변, ground_truth 추출
            question_match = _RE_QA_QUESTION.search(block)
            answer_match = _RE_QA_ANSWER.search(block)
            gt_match = _RE_QA_GT.search(block)

            if question_match and answer_match and gt_match:
                question = question_match.group(1).strip()
                answer = answer_match.group(1).strip()
                ground_truth = gt_match.group(1).strip()

                qa_id = f"{chunk.chunk_id}_qa{i}"

                qa_pair = QAPair(
                    qa_id=qa_id,
                    question=question,
                    answer=answer,
                    context=chunk.content,
                    ground_truth=ground_truth,
                    metadata={
                        "chunk_id": chunk.chunk_id,
                        "page_number": chunk.page_number,
                        "generated_at": datetime.now().isoformat()
                    }
                )

                qa_pairs.append(qa_pair)

        return qa_pairs


# ============================================================================
# Golden Dataset Manager
# ============================================================================

class GoldenDatasetManager:
    """Golden Dataset 관리자 - 저장/로드/검증"""

    def __init__(self, output_dir: str = "results/golden_datasets"):
        """
        Args:
            output_dir: 저장 디렉토리 (기본: results/golden_datasets)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_dataset(
        self,
        qa_pairs: list[QAPair],
        source_document: str,
        metadata: dict[str, Any] | None = None
    ) -> GoldenDataset:
        """Golden Dataset 생성"""
        dataset_id = self._generate_dataset_id(source_document)

        if metadata is None:
            metadata = {}

        dataset = GoldenDataset(
            dataset_id=dataset_id,
            source_document=source_document,
            created_at=datetime.now().isoformat(),
            total_qa_pairs=len(qa_pairs),
            qa_pairs=qa_pairs,
            metadata=metadata
        )

        return dataset

    def save_dataset(
        self,
        dataset: GoldenDataset,
        format: str = "json",
        filename: str | None = None
    ) -> str:
        """
        Dataset 저장

        Args:
            dataset: Golden Dataset
            format: 저장 형식 ("json" 또는 "csv")
            filename: 파일명 (None이면 자동 생성)

        Returns:
            저장된 파일 경로
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"golden_dataset_{dataset.dataset_id}_{timestamp}.{format}"

        filepath = self.output_dir / filename

        if format == "json":
            self._save_as_json(dataset, filepath)
        elif format == "csv":
            self._save_as_csv(dataset, filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(filepath)

    def _save_as_json(self, dataset: GoldenDataset, filepath: Path):
        """JSON 형식으로 저장"""
        data = asdict(dataset)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ Saved as JSON: {filepath}")

    def _save_as_csv(self, dataset: GoldenDataset, filepath: Path):
        """CSV 형식으로 저장"""
        rows = []

        for qa in dataset.qa_pairs:
            row = {
                "qa_id": qa.qa_id,
                "question": qa.question,
                "answer": qa.answer,
                "ground_truth": qa.ground_truth,
                "context": qa.context,
                "chunk_id": qa.metadata.get("chunk_id", ""),
                "page_number": qa.metadata.get("page_number", ""),
                "generated_at": qa.metadata.get("generated_at", "")
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')  # utf-8-sig for Excel

        print(f"✅ Saved as CSV: {filepath}")

    def load_dataset(self, filepath: str) -> GoldenDataset:
        """Dataset 로드"""
        filepath_p = Path(filepath)

        if not filepath_p.exists():
            raise FileNotFoundError(f"File not found: {filepath_p}")

        if filepath_p.suffix == ".json":
            return self._load_from_json(filepath_p)
        elif filepath_p.suffix == ".csv":
            return self._load_from_csv(filepath_p)
        else:
            raise ValueError(f"Unsupported format: {filepath_p.suffix}")

    def _load_from_json(self, filepath: Path) -> GoldenDataset:
        """JSON에서 로드"""
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)

        # QAPair 객체로 변환
        qa_pairs = [QAPair(**qa) for qa in data["qa_pairs"]]

        dataset = GoldenDataset(
            dataset_id=data["dataset_id"],
            source_document=data["source_document"],
            created_at=data["created_at"],
            total_qa_pairs=data["total_qa_pairs"],
            qa_pairs=qa_pairs,
            metadata=data.get("metadata", {})
        )

        print(f"✅ Loaded from JSON: {filepath} ({len(qa_pairs)} QA pairs)")
        return dataset

    def _load_from_csv(self, filepath: Path) -> GoldenDataset:
        """CSV에서 로드"""
        df = pd.read_csv(filepath, encoding='utf-8-sig')

        qa_pairs = []
        for _, row in df.iterrows():
            qa_pair = QAPair(
                qa_id=row["qa_id"],
                question=row["question"],
                answer=row["answer"],
                ground_truth=row["ground_truth"],
                context=row["context"],
                metadata={
                    "chunk_id": row.get("chunk_id", ""),
                    "page_number": row.get("page_number", ""),
                    "generated_at": row.get("generated_at", "")
                }
            )
            qa_pairs.append(qa_pair)

        # 메타데이터 추출 (첫 번째 행에서)
        source_doc = filepath.stem
        dataset_id = self._generate_dataset_id(source_doc)

        dataset = GoldenDataset(
            dataset_id=dataset_id,
            source_document=source_doc,
            created_at=datetime.now().isoformat(),
            total_qa_pairs=len(qa_pairs),
            qa_pairs=qa_pairs,
            metadata={}
        )

        print(f"✅ Loaded from CSV: {filepath} ({len(qa_pairs)} QA pairs)")
        return dataset

    def validate_dataset(self, dataset: GoldenDataset) -> dict[str, Any]:
        """Dataset 검증"""
        validation_results = {
            "is_valid": True,
            "total_qa_pairs": len(dataset.qa_pairs),
            "issues": []
        }

        for qa in dataset.qa_pairs:
            # 필수 필드 체크
            if not qa.question or not qa.question.strip():
                validation_results["issues"].append(f"{qa.qa_id}: 질문이 비어있음")
                validation_results["is_valid"] = False

            if not qa.answer or not qa.answer.strip():
                validation_results["issues"].append(f"{qa.qa_id}: 답변이 비어있음")
                validation_results["is_valid"] = False

            if not qa.ground_truth or not qa.ground_truth.strip():
                validation_results["issues"].append(f"{qa.qa_id}: Ground truth가 비어있음")
                validation_results["is_valid"] = False

            if not qa.context or not qa.context.strip():
                validation_results["issues"].append(f"{qa.qa_id}: Context가 비어있음")
                validation_results["is_valid"] = False

            # 길이 체크
            if len(qa.question) < 10:
                validation_results["issues"].append(f"{qa.qa_id}: 질문이 너무 짧음")

            if len(qa.answer) < 20:
                validation_results["issues"].append(f"{qa.qa_id}: 답변이 너무 짧음")

        return validation_results

    def _generate_dataset_id(self, source_document: str) -> str:
        """Dataset ID 생성"""
        doc_hash = hashlib.md5(source_document.encode()).hexdigest()[:8]
        return f"dataset_{doc_hash}"


# ============================================================================
# Main Pipeline
# ============================================================================

class KoreanRAGDatasetGenerator:
    """한국어 RAG Dataset 생성 파이프라인"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-5-nano",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        output_dir: str = "golden_datasets"
    ):
        """
        Args:
            api_key: OpenAI API 키
            model: 사용할 모델
            chunk_size: 청크 크기
            chunk_overlap: 청크 겹침
            output_dir: 출력 디렉토리
        """
        self.pdf_extractor = KoreanPDFExtractor()
        self.text_chunker = TextChunker(chunk_size, chunk_overlap)
        self.qa_generator = KoreanQAGenerator(api_key, model)
        self.dataset_manager = GoldenDatasetManager(output_dir)

    def generate_from_pdf(
        self,
        pdf_path: str,
        num_questions_per_chunk: int = 3,
        question_types: list[str] | None = None,
        save_format: str = "json",
        max_chunks: int | None = None
    ) -> GoldenDataset:
        """
        PDF에서 Golden Dataset 생성 (전체 파이프라인)

        Args:
            pdf_path: PDF 파일 경로
            num_questions_per_chunk: 청크당 질문 수
            question_types: 질문 유형
            save_format: 저장 형식 ("json" 또는 "csv")
            max_chunks: 최대 청크 수 (테스트용, None이면 전체)

        Returns:
            생성된 Golden Dataset
        """
        print(f"\n{'='*80}")
        print("Korean RAG Golden Dataset generation started")
        print(f"{'='*80}\n")

        # 1. PDF 텍스트 추출
        print(f"📄 Reading PDF file: {pdf_path}")
        pages_text = self.pdf_extractor.extract_text(pdf_path)
        print(f"   ✓ {len(pages_text)} pages extracted\n")

        # 텍스트 정제
        cleaned_pages = []
        for page_num, text in pages_text:
            cleaned_text = self.pdf_extractor.clean_text(text)
            cleaned_pages.append((page_num, cleaned_text))

        # 메모리 최적화: max_chunks 설정 시 페이지 수 제한
        if max_chunks:
            # 청크당 평균 1-2페이지로 가정, 여유있게 계산
            estimated_pages_needed = max(3, max_chunks * 2)
            if len(cleaned_pages) > estimated_pages_needed:
                print(f"🛡️  Memory optimization: processing only first {estimated_pages_needed} of {len(cleaned_pages)} pages (for {max_chunks} chunks)")
                cleaned_pages = cleaned_pages[:estimated_pages_needed]

        # 2. 텍스트 청킹
        print(f"📦 Text chunking (chunk_size: {self.text_chunker.chunk_size}, overlap: {self.text_chunker.chunk_overlap})")
        chunks = self.text_chunker.chunk_documents(cleaned_pages)

        if max_chunks and len(chunks) > max_chunks:
            chunks = chunks[:max_chunks]
            print(f"   ⚠️  Chunk limit applied: using only {max_chunks} chunks")

        print(f"   ✓ {len(chunks)} chunks created\n")

        # 3. QA 쌍 생성
        print(f"🤖 AI-based QA pair generation ({num_questions_per_chunk} questions per chunk)")
        print(f"   Model: {self.qa_generator.model}")
        print(f"   Expected count: {len(chunks) * num_questions_per_chunk}\n")

        all_qa_pairs = []

        for i, chunk in enumerate(chunks, 1):
            print(f"   [{i}/{len(chunks)}] Processing chunk (Page {chunk.page_number})...", end=" ")

            qa_pairs = self.qa_generator.generate_qa_pairs(
                chunk,
                num_questions=num_questions_per_chunk,
                question_types=question_types
            )

            all_qa_pairs.extend(qa_pairs)
            print(f"✓ {len(qa_pairs)} generated")

        print(f"\n   ✓ Total {len(all_qa_pairs)} QA pairs generated\n")

        # 4. Golden Dataset 생성
        print("💾 Building and saving Golden Dataset")
        dataset = self.dataset_manager.create_dataset(
            qa_pairs=all_qa_pairs,
            source_document=pdf_path,
            metadata={
                "total_pages": len(pages_text),
                "total_chunks": len(chunks),
                "chunk_size": self.text_chunker.chunk_size,
                "chunk_overlap": self.text_chunker.chunk_overlap,
                "num_questions_per_chunk": num_questions_per_chunk,
                "question_types": question_types,
                "model": self.qa_generator.model
            }
        )

        # 5. 검증
        validation = self.dataset_manager.validate_dataset(dataset)
        if validation["is_valid"]:
            print("   ✓ Dataset validation passed")
        else:
            print("   ⚠️  Dataset validation failed:")
            for issue in validation["issues"][:5]:  # 처음 5개만 표시
                print(f"      - {issue}")

        # 6. 저장
        saved_path = self.dataset_manager.save_dataset(dataset, format=save_format)
        print(f"   ✓ Saved: {saved_path}\n")

        # 7. 요약 출력
        self._print_summary(dataset)

        return dataset

    def _print_summary(self, dataset: GoldenDataset):
        """생성 결과 요약 출력"""
        print(f"{'='*80}")
        print("📊 Generation summary")
        print(f"{'='*80}\n")

        print(f"Dataset ID: {dataset.dataset_id}")
        print(f"Source document: {dataset.source_document}")
        print(f"Created at: {dataset.created_at}")
        print(f"Total QA pairs: {dataset.total_qa_pairs}\n")

        # 샘플 QA 쌍 출력
        if dataset.qa_pairs:
            print("📝 Sample QA pair (first):")
            print("-" * 80)
            sample = dataset.qa_pairs[0]
            print(f"Question: {sample.question}")
            print(f"Answer: {sample.answer}")
            print(f"Ground Truth: {sample.ground_truth}")
            print(f"Context (first 100 chars): {sample.context[:100]}...")
            print("-" * 80 + "\n")

        print("✅ Golden Dataset generation complete!\n")


# ============================================================================
# Example Usage
# ============================================================================

def example_generate_from_pdf():
    """PDF에서 Golden Dataset 생성 예제"""

    # 1. 생성기 초기화
    generator = KoreanRAGDatasetGenerator(
        model="gpt-5-nano",  # 또는 "gpt-4o" (더 비싸지만 품질 좋음)
        chunk_size=800,
        chunk_overlap=150,
        output_dir="golden_datasets"
    )

    # 2. PDF에서 데이터셋 생성
    dataset = generator.generate_from_pdf(
        pdf_path="your_document.pdf",  # 실제 PDF 경로로 변경
        num_questions_per_chunk=3,
        question_types=["factual", "reasoning", "summary"],
        save_format="json",  # "json" 또는 "csv"
        max_chunks=5  # 테스트용, 실제 사용 시 None으로 설정
    )

    return dataset


def example_load_and_use():
    """저장된 Golden Dataset 로드 및 사용 예제"""

    manager = GoldenDatasetManager()

    # 1. 로드
    dataset = manager.load_dataset("golden_datasets/golden_dataset_xxx.json")

    # 2. 검증
    validation = manager.validate_dataset(dataset)
    print(f"Validation result: {'passed' if validation['is_valid'] else 'failed'}")

    # 3. RAG 평가에 사용
    for qa in dataset.qa_pairs[:3]:  # 처음 3개만
        print(f"\nQuestion: {qa.question}")
        print(f"Expected: {qa.ground_truth}")
        print(f"Context: {qa.context[:100]}...")


if __name__ == "__main__":
    print("""
Korean RAG Dataset Generator
=============================

사용 방법:

1. PDF에서 Golden Dataset 생성:
   python korean_rag_dataset_generator.py

2. 저장된 데이터셋 로드:
   manager = GoldenDatasetManager()
   dataset = manager.load_dataset("path/to/dataset.json")

필수 환경 변수:
   OPENAI_API_KEY=your-api-key

필수 라이브러리:
   pip install pdfplumber openai pandas python-dotenv

예제 실행:
   - example_generate_from_pdf()
   - example_load_and_use()
""")

    # 예제 실행 (주석 해제하여 사용)
    # example_generate_from_pdf()
