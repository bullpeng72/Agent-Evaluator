"""
Data Editor Manager
===================
Dashboard에서 평가 데이터를 확인하고 편집하는 기능 제공

주요 기능:
- TaskResult 데이터 CRUD
- Golden Dataset 편집
- 메트릭 임계값 조정
- 버전 관리 및 롤백
"""

import json
import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import pandas as pd
import copy

# Import from pip-installed agent_evaluator package
from agent_evaluator import TaskResult, TaskType, PerformanceMonitor
from agent_evaluator.utils.path_helpers import (
    find_project_root,
    get_evaluation_results_dir,
    get_dashboard_dir
)

# Storage paths are now hardcoded to data/ directory
# No longer using DataStorageManager

# Optional import - create stubs if not available
try:
    from agent_evaluator.datasets.korean_rag_dataset_generator import (
        QAPair, GoldenDataset, GoldenDatasetManager
    )
except ImportError:
    # Create stub classes for when the module is not available
    @dataclass
    class QAPair:
        """Stub QAPair class"""
        question: str = ""
        answer: str = ""
        context: str = ""
        metadata: Dict[str, Any] = None

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

    class GoldenDataset:
        """Stub GoldenDataset class"""
        def __init__(self, qa_pairs: List[QAPair] = None, metadata: Dict[str, Any] = None):
            self.qa_pairs = qa_pairs or []
            self.metadata = metadata or {}

    class GoldenDatasetManager:
        """Stub GoldenDatasetManager class"""
        def __init__(self, data_dir: str = None):
            if data_dir is None:
                # Zero Configuration: 자동 경로 탐지
                from agent_evaluator.utils.path_helpers import get_dashboard_dir, find_project_root
                dashboard_dir = get_dashboard_dir(find_project_root())
                data_dir = str(dashboard_dir / "data" / "golden_datasets")
            self.data_dir = Path(data_dir)
            self.data_dir.mkdir(parents=True, exist_ok=True)

        def save_dataset(self, dataset: GoldenDataset, name: str):
            pass

        def load_dataset(self, name: str) -> Optional[GoldenDataset]:
            return None


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DataEdit:
    """데이터 편집 기록"""
    edit_id: str
    timestamp: str
    editor: str  # 편집자 이름
    edit_type: str  # "create", "update", "delete"
    data_type: str  # "task_result", "qa_pair", "threshold"
    data_id: str
    before_value: Optional[Dict[str, Any]]
    after_value: Optional[Dict[str, Any]]
    reason: str  # 편집 이유


@dataclass
class DataVersion:
    """데이터 버전"""
    version_id: str
    timestamp: str
    data_snapshot: Dict[str, Any]
    description: str


# ============================================================================
# Data Editor Manager
# ============================================================================

class DataEditorManager:
    """
    데이터 편집 관리자

    기능:
    - 데이터 로드 및 저장
    - CRUD 작업
    - 변경 이력 추적
    - 버전 관리 및 롤백
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Args:
            data_dir: 데이터 저장 디렉토리 (기본값: Zero Configuration으로 자동 탐지)
        """
        # Zero Configuration: 프로젝트 루트 및 Dashboard 디렉토리 자동 탐지
        project_root = find_project_root()
        dashboard_dir = get_dashboard_dir(project_root)

        # 데이터 디렉토리 설정
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = get_evaluation_results_dir(project_root)

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 히스토리 저장 디렉토리
        self.history_dir = dashboard_dir / "data" / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # 버전 디렉토리
        self.versions_dir = dashboard_dir / "data" / "versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)

        # 경로 정보 저장 (다른 메서드에서 재사용)
        self._dashboard_dir = dashboard_dir
        self._project_root = project_root

        # 현재 세션의 편집 기록
        self.edit_history: List[DataEdit] = []

    # ========================================================================
    # TaskResult 데이터 관리
    # ========================================================================

    def load_task_results(self, filepath: str) -> pd.DataFrame:
        """
        TaskResult 데이터를 DataFrame으로 로드

        Args:
            filepath: performance_data.json 파일 경로

        Returns:
            DataFrame
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tasks = data.get("tasks", [])

        # DataFrame으로 변환
        df = pd.DataFrame(tasks)

        # 중첩된 딕셔너리 평탄화
        if 'tokens_used' in df.columns:
            df['input_tokens'] = df['tokens_used'].apply(lambda x: x.get('input', 0) if isinstance(x, dict) else 0)
            df['output_tokens'] = df['tokens_used'].apply(lambda x: x.get('output', 0) if isinstance(x, dict) else 0)
            df['total_tokens'] = df['tokens_used'].apply(lambda x: x.get('total', 0) if isinstance(x, dict) else 0)

        if 'tool_calls' in df.columns:
            df['num_tool_calls'] = df['tool_calls'].apply(lambda x: len(x) if isinstance(x, list) else 0)

        if 'errors' in df.columns:
            df['num_errors'] = df['errors'].apply(lambda x: len(x) if isinstance(x, list) else 0)

        return df

    def save_task_results(self, df: pd.DataFrame, filepath: str, editor: str, reason: str):
        """
        수정된 TaskResult 데이터를 저장

        Args:
            df: 수정된 DataFrame
            filepath: 저장할 파일 경로
            editor: 편집자 이름
            reason: 편집 이유
        """
        # 버전 백업
        self._create_version(filepath, f"Before edit by {editor}")

        # 원본 데이터 로드
        with open(filepath, 'r', encoding='utf-8') as f:
            original_data = json.load(f)

        # DataFrame을 tasks 리스트로 변환
        tasks = df.to_dict('records')

        # tokens_used 재구성
        for task in tasks:
            if 'input_tokens' in task:
                task['tokens_used'] = {
                    'input': task.pop('input_tokens', 0),
                    'output': task.pop('output_tokens', 0),
                    'total': task.pop('total_tokens', 0)
                }

            # tool_calls, errors는 원본 유지 (복잡한 구조)
            # num_tool_calls, num_errors는 제거
            task.pop('num_tool_calls', None)
            task.pop('num_errors', None)

        # 저장
        original_data['tasks'] = tasks
        original_data['last_modified'] = datetime.now().isoformat()
        original_data['modified_by'] = editor

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(original_data, f, indent=2, default=str)

        # 편집 기록
        self._record_edit(
            edit_type="update",
            data_type="task_results",
            data_id=filepath,
            editor=editor,
            reason=reason,
            before_value=None,  # 전체 파일이므로 None
            after_value=None
        )

        print(f"✅ TaskResult 데이터 저장 완료: {filepath}")

    def add_task_result(
        self,
        task_data: Dict[str, Any],
        filepath: str,
        editor: str,
        reason: str
    ):
        """새 TaskResult 추가"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data['tasks'].append(task_data)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        self._record_edit(
            edit_type="create",
            data_type="task_result",
            data_id=task_data.get('task_id', 'unknown'),
            editor=editor,
            reason=reason,
            before_value=None,
            after_value=task_data
        )

    def delete_task_result(
        self,
        task_id: str,
        filepath: str,
        editor: str,
        reason: str
    ):
        """TaskResult 삭제"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 삭제할 task 찾기
        tasks = data['tasks']
        deleted_task = None

        for i, task in enumerate(tasks):
            if task.get('task_id') == task_id:
                deleted_task = tasks.pop(i)
                break

        if deleted_task:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)

            self._record_edit(
                edit_type="delete",
                data_type="task_result",
                data_id=task_id,
                editor=editor,
                reason=reason,
                before_value=deleted_task,
                after_value=None
            )

            print(f"✅ TaskResult 삭제 완료: {task_id}")
        else:
            print(f"⚠️  TaskResult를 찾을 수 없음: {task_id}")

    # ========================================================================
    # Golden Dataset 관리
    # ========================================================================

    def load_golden_dataset(self, filepath: str) -> pd.DataFrame:
        """Golden Dataset을 DataFrame으로 로드"""
        # Zero Configuration: 저장된 dashboard_dir 사용
        golden_dir = str(self._dashboard_dir / "data" / "golden_datasets")
        manager = GoldenDatasetManager(output_dir=golden_dir)
        dataset = manager.load_dataset(filepath)

        # Handle case where dataset is None
        if dataset is None:
            raise ValueError(
                f"Failed to load dataset from {filepath}. "
                f"The file may be corrupted or in an incorrect format."
            )

        # QA pairs를 DataFrame으로 변환
        qa_data = [asdict(qa) for qa in dataset.qa_pairs]
        df = pd.DataFrame(qa_data)

        # metadata 평탄화
        if 'metadata' in df.columns:
            df['chunk_id'] = df['metadata'].apply(lambda x: x.get('chunk_id', '') if isinstance(x, dict) else '')
            df['page_number'] = df['metadata'].apply(lambda x: x.get('page_number', '') if isinstance(x, dict) else '')

        # Layer 2 필드: 리스트를 쉼표로 구분된 문자열로 변환 (UI 표시용)
        for field in ['expected_tools', 'expected_agents', 'expected_workflow_steps']:
            if field in df.columns:
                df[field] = df[field].apply(
                    lambda x: ','.join(x) if isinstance(x, list) and x else ''
                )

        return df

    def save_golden_dataset(
        self,
        df: pd.DataFrame,
        filepath: str,
        dataset_id: str,
        source_document: str,
        editor: str,
        reason: str
    ):
        """수정된 Golden Dataset 저장"""
        # 버전 백업
        self._create_version(filepath, f"Before edit by {editor}")

        # DataFrame을 QAPair 객체로 변환
        qa_pairs = []
        for idx, row in df.iterrows():
            # 필수 필드 검증 (None 체크)
            required_fields = ['qa_id', 'question', 'answer', 'ground_truth']
            missing_fields = []

            for field in required_fields:
                if pd.isna(row[field]) or row[field] is None or str(row[field]).strip() == '':
                    missing_fields.append(field)

            if missing_fields:
                raise ValueError(
                    f"행 {idx + 1}에 필수 필드가 비어있습니다: {', '.join(missing_fields)}. "
                    f"새로 추가한 행의 경우 모든 필수 필드를 입력한 후 저장해주세요."
                )

            # Layer 2 필드 처리 (쉼표로 구분된 문자열을 리스트로 변환)
            def parse_list_field(field_value):
                """쉼표로 구분된 문자열을 리스트로 변환"""
                if pd.isna(field_value) or field_value == '' or field_value is None:
                    return None
                if isinstance(field_value, list):
                    return field_value
                return [item.strip() for item in str(field_value).split(',') if item.strip()]

            qa = QAPair(
                qa_id=str(row['qa_id']).strip(),
                question=str(row['question']).strip(),
                answer=str(row['answer']).strip(),
                context=str(row['context']).strip() if not pd.isna(row.get('context')) else '',
                ground_truth=str(row['ground_truth']).strip(),
                metadata={
                    'chunk_id': row.get('chunk_id', ''),
                    'page_number': row.get('page_number', ''),
                    'modified_at': datetime.now().isoformat(),
                    'modified_by': editor
                },
                # Layer 2: Agentic AI Metrics 필드
                expected_tools=parse_list_field(row.get('expected_tools')),
                expected_agents=parse_list_field(row.get('expected_agents')),
                expected_workflow_steps=parse_list_field(row.get('expected_workflow_steps'))
            )
            qa_pairs.append(qa)

        # GoldenDataset 생성
        dataset = GoldenDataset(
            dataset_id=dataset_id,
            source_document=source_document,
            created_at=datetime.now().isoformat(),
            total_qa_pairs=len(qa_pairs),
            qa_pairs=qa_pairs,
            metadata={
                'last_modified': datetime.now().isoformat(),
                'modified_by': editor,
                'modification_reason': reason
            }
        )

        # 저장 (Zero Configuration: 저장된 dashboard_dir 사용)
        golden_dir = str(self._dashboard_dir / "data" / "golden_datasets")
        manager = GoldenDatasetManager(output_dir=golden_dir)
        manager.save_dataset(dataset, format="json", filename=Path(filepath).name)

        # 편집 기록
        self._record_edit(
            edit_type="update",
            data_type="golden_dataset",
            data_id=dataset_id,
            editor=editor,
            reason=reason,
            before_value=None,
            after_value=None
        )

        print(f"✅ Golden Dataset 저장 완료: {filepath}")

    def add_qa_pair(
        self,
        qa_data: Dict[str, Any],
        filepath: str,
        editor: str,
        reason: str
    ):
        """Golden Dataset에 새 QA 쌍 추가"""
        # Zero Configuration: 저장된 dashboard_dir 사용
        golden_dir = str(self._dashboard_dir / "data" / "golden_datasets")
        manager = GoldenDatasetManager(output_dir=golden_dir)
        dataset = manager.load_dataset(filepath)

        # 새 QA 쌍 생성
        new_qa = QAPair(**qa_data)
        dataset.qa_pairs.append(new_qa)
        dataset.total_qa_pairs = len(dataset.qa_pairs)

        # 저장
        manager.save_dataset(dataset, format="json", filename=Path(filepath).name)

        self._record_edit(
            edit_type="create",
            data_type="qa_pair",
            data_id=qa_data.get('qa_id', 'unknown'),
            editor=editor,
            reason=reason,
            before_value=None,
            after_value=qa_data
        )

    def delete_qa_pair(
        self,
        qa_id: str,
        filepath: str,
        editor: str,
        reason: str
    ):
        """Golden Dataset에서 QA 쌍 삭제"""
        # Zero Configuration: 저장된 dashboard_dir 사용
        golden_dir = str(self._dashboard_dir / "data" / "golden_datasets")
        manager = GoldenDatasetManager(output_dir=golden_dir)
        dataset = manager.load_dataset(filepath)

        # 삭제할 QA 찾기
        deleted_qa = None
        for i, qa in enumerate(dataset.qa_pairs):
            if qa.qa_id == qa_id:
                deleted_qa = dataset.qa_pairs.pop(i)
                break

        if deleted_qa:
            dataset.total_qa_pairs = len(dataset.qa_pairs)
            manager.save_dataset(dataset, format="json", filename=Path(filepath).name)

            self._record_edit(
                edit_type="delete",
                data_type="qa_pair",
                data_id=qa_id,
                editor=editor,
                reason=reason,
                before_value=asdict(deleted_qa),
                after_value=None
            )

            print(f"✅ QA 쌍 삭제 완료: {qa_id}")

    # ========================================================================
    # 메트릭 임계값 관리
    # ========================================================================

    def load_thresholds(self) -> Dict[str, float]:
        """임계값 설정 로드"""
        threshold_file = self.data_dir / "thresholds.json"

        if threshold_file.exists():
            with open(threshold_file, 'r') as f:
                return json.load(f)

        # 기본값
        return {
            "tcr": 90.0,
            "accuracy": 85.0,
            "hallucination": 5.0,
            "quality": 7.0,
            "latency": 3.0,
            "cost_per_task": 0.05,
            "faithfulness": 0.8,
            "answer_relevancy": 0.8,
            "context_recall": 0.8,
            "context_precision": 0.8
        }

    def save_thresholds(
        self,
        thresholds: Dict[str, float],
        editor: str,
        reason: str
    ):
        """임계값 설정 저장"""
        threshold_file = self.data_dir / "thresholds.json"

        # 버전 백업
        if threshold_file.exists():
            self._create_version(str(threshold_file), f"Before threshold edit by {editor}")

        # 원본 로드
        old_thresholds = self.load_thresholds()

        # 저장
        with open(threshold_file, 'w') as f:
            json.dump(thresholds, f, indent=2)

        # 편집 기록
        self._record_edit(
            edit_type="update",
            data_type="thresholds",
            data_id="system_thresholds",
            editor=editor,
            reason=reason,
            before_value=old_thresholds,
            after_value=thresholds
        )

        print(f"✅ 임계값 저장 완료")

    # ========================================================================
    # 고급 평가 설정 관리
    # ========================================================================

    def load_advanced_eval_config(self) -> Dict[str, Any]:
        """고급 평가 설정 로드 (DeepEval, Ragas, LangSmith)"""
        config_file = self.data_dir / "advanced_eval_config.json"

        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)

        # 기본값
        return {
            "deepeval": {
                "enabled": True,
                "model": "gpt-4o-mini",
                "thresholds": {
                    "g_eval": 0.7,
                    "hallucination": 0.3,
                    "toxicity": 0.3,
                    "bias": 0.3
                }
            },
            "ragas": {
                "enabled": True,
                "model": "gpt-4o-mini",
                "thresholds": {
                    "context_relevancy": 0.7,
                    "answer_similarity": 0.7,
                    "answer_correctness": 0.7,
                    "overall_score": 0.7
                }
            },
            "langsmith": {
                "enabled": False,
                "api_key": ""
            },
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "updated_by": "System"
            }
        }

    def save_advanced_eval_config(
        self,
        config: Dict[str, Any],
        editor: str,
        reason: str
    ):
        """고급 평가 설정 저장"""
        config_file = self.data_dir / "advanced_eval_config.json"

        # 버전 백업
        if config_file.exists():
            self._create_version(str(config_file), f"Before advanced eval config edit by {editor}")

        # 원본 로드
        old_config = self.load_advanced_eval_config()

        # 메타데이터 업데이트
        config["metadata"] = {
            "last_updated": datetime.now().isoformat(),
            "updated_by": editor
        }

        # 저장
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        # 편집 기록
        self._record_edit(
            edit_type="update",
            data_type="advanced_eval_config",
            data_id="system_advanced_eval",
            editor=editor,
            reason=reason,
            before_value=old_config,
            after_value=config
        )

        print(f"✅ 고급 평가 설정 저장 완료")

    # ========================================================================
    # 버전 관리
    # ========================================================================

    def _create_version(self, filepath: str, description: str):
        """데이터 버전 생성"""
        if not os.path.exists(filepath):
            return

        # 원본 데이터 로드
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 버전 ID 생성
        version_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        version = DataVersion(
            version_id=version_id,
            timestamp=datetime.now().isoformat(),
            data_snapshot=data,
            description=description
        )

        # 저장
        version_file = self.versions_dir / f"version_{version_id}_{Path(filepath).stem}.json"
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(version), f, indent=2, default=str)

    def list_versions(self, data_name: str = None) -> List[DataVersion]:
        """버전 목록 조회"""
        versions = []

        for version_file in self.versions_dir.glob("version_*.json"):
            if data_name and data_name not in version_file.stem:
                continue

            with open(version_file, 'r', encoding='utf-8') as f:
                version_data = json.load(f)
                version = DataVersion(**version_data)
                versions.append(version)

        # 최신순 정렬
        versions.sort(key=lambda v: v.timestamp, reverse=True)

        return versions

    def rollback_to_version(self, version_id: str, target_filepath: str, editor: str):
        """특정 버전으로 롤백"""
        # 버전 파일 찾기
        version_files = list(self.versions_dir.glob(f"version_{version_id}_*.json"))

        if not version_files:
            print(f"⚠️  버전을 찾을 수 없음: {version_id}")
            return False

        version_file = version_files[0]

        # 버전 로드
        with open(version_file, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
            version = DataVersion(**version_data)

        # 현재 데이터 백업
        self._create_version(target_filepath, f"Before rollback by {editor}")

        # 버전 데이터로 복원
        with open(target_filepath, 'w', encoding='utf-8') as f:
            json.dump(version.data_snapshot, f, indent=2, default=str)

        # 편집 기록
        self._record_edit(
            edit_type="rollback",
            data_type="version_rollback",
            data_id=version_id,
            editor=editor,
            reason=f"Rollback to version {version_id}",
            before_value=None,
            after_value=None
        )

        print(f"✅ 버전 롤백 완료: {version_id}")
        return True

    # ========================================================================
    # 편집 기록 관리
    # ========================================================================

    def _record_edit(
        self,
        edit_type: str,
        data_type: str,
        data_id: str,
        editor: str,
        reason: str,
        before_value: Optional[Dict],
        after_value: Optional[Dict]
    ):
        """편집 기록 저장"""
        edit_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        edit = DataEdit(
            edit_id=edit_id,
            timestamp=datetime.now().isoformat(),
            editor=editor,
            edit_type=edit_type,
            data_type=data_type,
            data_id=data_id,
            before_value=before_value,
            after_value=after_value,
            reason=reason
        )

        self.edit_history.append(edit)

        # 파일로 저장
        history_file = self.history_dir / f"edit_{edit_id}.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(edit), f, indent=2, default=str)

    def load_edit_history(self, limit: int = 100) -> pd.DataFrame:
        """편집 기록 로드"""
        edits = []

        # 최근 파일들만 로드
        edit_files = sorted(
            self.history_dir.glob("edit_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]

        for edit_file in edit_files:
            with open(edit_file, 'r', encoding='utf-8') as f:
                edit_data = json.load(f)
                edits.append(edit_data)

        if not edits:
            return pd.DataFrame()

        df = pd.DataFrame(edits)

        # before_value, after_value는 간단히 표시
        if 'before_value' in df.columns:
            df['has_before'] = df['before_value'].apply(lambda x: x is not None)
        if 'after_value' in df.columns:
            df['has_after'] = df['after_value'].apply(lambda x: x is not None)

        return df

    def get_edit_details(self, edit_id: str) -> Optional[DataEdit]:
        """특정 편집의 상세 정보 조회"""
        edit_files = list(self.history_dir.glob(f"edit_{edit_id}.json"))

        if not edit_files:
            return None

        with open(edit_files[0], 'r', encoding='utf-8') as f:
            edit_data = json.load(f)
            return DataEdit(**edit_data)

    # ========================================================================
    # Test 환경 설정 (Test 수행 전)
    # ========================================================================

    def prepare_test_environment(self) -> Dict[str, Any]:
        """
        Test 수행 전 환경 설정 로드

        Returns:
            Dict containing:
            - thresholds: 메트릭 임계값
            - golden_datasets: 사용 가능한 Golden Dataset 목록
            - last_results: 이전 Test 결과 (있는 경우)
        """
        env_config = {
            "thresholds": self.load_thresholds(),
            "golden_datasets": [],
            "last_results": None
        }

        # Golden Dataset 목록 조회 (Zero Configuration: 저장된 dashboard_dir 사용)
        golden_dir = self._dashboard_dir / "data" / "golden_datasets"
        if golden_dir.exists():
            env_config["golden_datasets"] = [
                str(f) for f in golden_dir.glob("*.json")
            ]

        # 이전 Test 결과 확인
        results_dir = self.data_dir / "performance_data.json"
        if results_dir.exists():
            with open(results_dir, 'r', encoding='utf-8') as f:
                env_config["last_results"] = json.load(f)

        return env_config

    def validate_test_environment(self) -> Dict[str, Any]:
        """
        Test 환경이 올바르게 설정되었는지 검증

        Returns:
            Dict containing:
            - valid: bool - 환경이 유효한지
            - warnings: List[str] - 경고 메시지
            - errors: List[str] - 오류 메시지
        """
        validation = {
            "valid": True,
            "warnings": [],
            "errors": []
        }

        # 임계값 확인
        thresholds = self.load_thresholds()
        if not thresholds:
            validation["warnings"].append("임계값이 설정되지 않았습니다. 기본값을 사용합니다.")

        # Golden Dataset 확인 (Zero Configuration: 저장된 dashboard_dir 사용)
        golden_dir = self._dashboard_dir / "data" / "golden_datasets"
        if not golden_dir.exists() or not list(golden_dir.glob("*.json")):
            validation["warnings"].append("Golden Dataset이 없습니다. RAG 메트릭을 사용할 수 없습니다.")

        # 결과 저장 디렉토리 확인
        if not self.data_dir.exists():
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                validation["errors"].append(f"결과 저장 디렉토리를 생성할 수 없습니다: {e}")
                validation["valid"] = False

        return validation

    def create_test_configuration(
        self,
        test_name: str,
        golden_dataset_path: Optional[str] = None,
        golden_datasets: Optional[List[str]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        enable_transparency: bool = True,
        editor: str = "Admin",
        author: Optional[str] = None,
        # 🆕 Phase 3: Enhanced Metadata
        environment: str = "development",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_config: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        version: str = "0.5.0",
        expected_duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Test 구성 생성 및 저장 (Phase 3 Enhanced)

        Args:
            test_name: Test 이름
            golden_dataset_path: 사용할 Golden Dataset 경로 (단일, 호환성 유지)
            golden_datasets: 사용할 Golden Dataset 경로 목록 (복수)
            thresholds: 임계값 (None이면 기본값 사용)
            enable_transparency: 투명성 추적 활성화 여부
            editor: 구성 작성자 (호환성 유지)
            author: 구성 작성자 (editor와 동일, 우선순위 높음)

            # 🆕 Phase 3: Enhanced Metadata
            environment: 배포 환경 (development, staging, production). Default: "development"
            description: Test 구성에 대한 설명
            tags: 분류를 위한 태그 리스트 (예: ["regression", "api-test"])
            model_config: LLM 모델 구성 정보
                - model_name: 모델 이름 (예: "gpt-4", "claude-3-opus")
                - temperature: Temperature 설정
                - max_tokens: 최대 토큰 수
                - top_p, frequency_penalty 등 추가 파라미터
            framework: 사용 중인 프레임워크 (langchain, crewai, langgraph, autogen, custom)
            version: Test 구성 버전 (예: "0.5.0", "1.0.0"). Default: "0.5.0"
            expected_duration_seconds: 예상 Test 실행 시간(초)
            metadata: 추가 유연한 메타데이터 (자유 형식 딕셔너리)

        Returns:
            config: 생성된 구성 딕셔너리 (config_id 및 모든 메타데이터 포함)

        Example:
            >>> manager.create_test_configuration(
            ...     test_name="Production_API_Test",
            ...     environment="production",
            ...     description="API 엔드포인트 회귀 테스트",
            ...     tags=["api", "regression", "critical"],
            ...     model_config={
            ...         "model_name": "gpt-4",
            ...         "temperature": 0.7,
            ...         "max_tokens": 2000
            ...     },
            ...     framework="langchain",
            ...     version="0.5.0",
            ...     expected_duration_seconds=300,
            ...     metadata={"team": "qa", "priority": "high"}
            ... )
        """
        config_id = f"test_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # author와 editor 우선순위 처리
        created_by = author if author else editor

        # golden_datasets 우선, 없으면 golden_dataset_path 사용
        datasets = golden_datasets if golden_datasets else ([golden_dataset_path] if golden_dataset_path else [])

        # 기본 구성
        config = {
            # Core fields
            "config_id": config_id,
            "test_name": test_name,
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "golden_dataset": golden_dataset_path,  # 호환성 유지
            "golden_datasets": datasets,  # 복수 지원
            "thresholds": thresholds if thresholds else self.load_thresholds(),
            "enable_transparency": enable_transparency,
            "status": "ready",

            # 🆕 Phase 3: Enhanced Metadata
            "environment": environment,
            "version": version
        }

        # Optional fields - 값이 제공된 경우에만 추가
        if description:
            config["description"] = description

        if tags:
            config["tags"] = tags

        if model_config:
            config["model_config"] = model_config

        if framework:
            config["framework"] = framework

        if expected_duration_seconds is not None:
            config["expected_duration_seconds"] = expected_duration_seconds

        if metadata:
            config["metadata"] = metadata

        # 저장
        config_dir = self.data_dir / "test_configs"
        config_dir.mkdir(exist_ok=True)

        config_file = config_dir / f"{config_id}.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, default=str)

        print(f"✅ Test 구성 생성: {config_id}")
        print(f"   환경: {environment}")
        print(f"   버전: {version}")
        if framework:
            print(f"   프레임워크: {framework}")
        if tags:
            print(f"   태그: {', '.join(tags)}")

        return config

    def load_test_configuration(self, config_id: str) -> Dict[str, Any]:
        """Test 구성 로드"""
        config_file = self.data_dir / "test_configs" / f"{config_id}.json"

        if not config_file.exists():
            raise FileNotFoundError(f"Test 구성을 찾을 수 없습니다: {config_id}")

        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_test_configurations(self) -> List[Dict[str, Any]]:
        """모든 Test 구성 목록 조회"""
        config_dir = self.data_dir / "test_configs"

        if not config_dir.exists():
            return []

        configs = []
        for config_file in config_dir.glob("test_config_*.json"):
            with open(config_file, 'r', encoding='utf-8') as f:
                configs.append(json.load(f))

        # 최신순 정렬
        configs.sort(key=lambda c: c.get('created_at', ''), reverse=True)
        return configs

    # ========================================================================
    # 데이터 검증
    # ========================================================================

    def validate_task_result(self, task_data: Dict[str, Any]) -> List[str]:
        """TaskResult 데이터 검증"""
        errors = []

        required_fields = [
            'task_id', 'task_type', 'success', 'completion_score',
            'accuracy_score', 'execution_time', 'tokens_used'
        ]

        for field in required_fields:
            if field not in task_data:
                errors.append(f"필수 필드 누락: {field}")

        # 범위 검증
        if 'completion_score' in task_data:
            score = task_data['completion_score']
            if not (0 <= score <= 1):
                errors.append(f"completion_score는 0-1 범위여야 함: {score}")

        if 'accuracy_score' in task_data:
            score = task_data['accuracy_score']
            if not (0 <= score <= 1):
                errors.append(f"accuracy_score는 0-1 범위여야 함: {score}")

        if 'execution_time' in task_data:
            time = task_data['execution_time']
            if time < 0:
                errors.append(f"execution_time은 양수여야 함: {time}")

        return errors

    def validate_qa_pair(self, qa_data: Dict[str, Any]) -> List[str]:
        """QA 쌍 데이터 검증"""
        errors = []

        required_fields = ['qa_id', 'question', 'answer', 'ground_truth', 'context']

        for field in required_fields:
            if field not in qa_data:
                errors.append(f"필수 필드 누락: {field}")
            elif not qa_data[field] or not str(qa_data[field]).strip():
                errors.append(f"{field}이(가) 비어있음")

        # 길이 검증
        if 'question' in qa_data and len(qa_data['question']) < 5:
            errors.append("질문이 너무 짧음 (최소 5자)")

        if 'answer' in qa_data and len(qa_data['answer']) < 10:
            errors.append("답변이 너무 짧음 (최소 10자)")

        if 'context' in qa_data and len(qa_data['context']) < 20:
            errors.append("컨텍스트가 너무 짧음 (최소 20자)")

        return errors


# ============================================================================
# Example Usage
# ============================================================================

def example_edit_task_results():
    """TaskResult 편집 예제"""
    manager = DataEditorManager()

    # 1. 데이터 로드
    df = manager.load_task_results("data/evaluation_results/performance_data.json")
    print(f"로드된 TaskResult: {len(df)}개")

    # 2. 데이터 수정 (예: completion_score 조정)
    df.loc[df['task_id'] == 'task_001', 'completion_score'] = 0.98

    # 3. 저장
    manager.save_task_results(
        df,
        "data/evaluation_results/performance_data.json",
        editor="John Doe",
        reason="Manual correction of completion score"
    )

    # 4. 편집 기록 확인
    history = manager.load_edit_history()
    print(f"\n편집 기록: {len(history)}개")
    print(history[['timestamp', 'editor', 'edit_type', 'reason']].head())


def example_edit_golden_dataset():
    """Golden Dataset 편집 예제"""
    manager = DataEditorManager()

    # 1. 데이터 로드
    df = manager.load_golden_dataset("golden_datasets/my_dataset.json")
    print(f"로드된 QA 쌍: {len(df)}개")

    # 2. 데이터 수정 (예: ground_truth 수정)
    df.loc[df['qa_id'] == 'qa_001', 'ground_truth'] = "수정된 정답"

    # 3. 저장
    manager.save_golden_dataset(
        df,
        "golden_datasets/my_dataset.json",
        dataset_id="my_dataset",
        source_document="my_document.pdf",
        editor="Jane Smith",
        reason="Corrected ground truth based on expert review"
    )


def example_version_management():
    """버전 관리 예제"""
    manager = DataEditorManager()

    # 1. 버전 목록 조회
    versions = manager.list_versions(data_name="performance_data")
    print(f"사용 가능한 버전: {len(versions)}개")

    for version in versions[:5]:
        print(f"  - {version.version_id}: {version.description}")

    # 2. 롤백
    if versions:
        manager.rollback_to_version(
            version_id=versions[0].version_id,
            target_filepath="data/evaluation_results/performance_data.json",
            editor="Admin"
        )


if __name__ == "__main__":
    print("""
Data Editor Manager
===================

기능:
1. TaskResult 데이터 CRUD
2. Golden Dataset 편집
3. 메트릭 임계값 조정
4. 버전 관리 및 롤백
5. 편집 기록 추적

예제 실행:
- example_edit_task_results()
- example_edit_golden_dataset()
- example_version_management()
""")
