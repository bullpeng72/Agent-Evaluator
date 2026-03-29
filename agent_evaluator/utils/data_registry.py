"""
Data Registry Module
====================
중앙 레지스트리를 통한 평가 데이터 위치 관리

개발자가 agent_evaluator 라이브러리로 생성한 평가 데이터의 위치를
자동으로 등록하고, Dashboard에서 검색할 수 있도록 지원합니다.

레지스트리 위치: ~/.agent_evaluator/registry.json

동시성 안전:
- 파일 락(fcntl/msvcrt)을 사용하여 멀티프로세스 환경에서 안전하게 동작
- CI/CD 파이프라인, 병렬 테스트 환경에서도 데이터 무결성 보장
"""

import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Platform-specific file locking
if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl


class DataRegistry:
    """
    데이터 위치 레지스트리

    개발자가 생성한 평가 데이터의 위치를 중앙에 등록하고 관리합니다.
    Dashboard는 이 레지스트리를 읽어 모든 프로젝트의 데이터를 검색할 수 있습니다.
    """

    REGISTRY_DIR = Path.home() / ".agent_evaluator"
    REGISTRY_FILE = REGISTRY_DIR / "registry.json"

    @classmethod
    def register_data_file(
        cls,
        filepath: str,
        project_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        데이터 파일을 레지스트리에 등록

        Args:
            filepath: 저장된 데이터 파일의 절대 경로
            project_name: 프로젝트 이름 (None이면 자동 감지)
            metadata: 추가 메타데이터 (예: task 개수, framework 등)

        Returns:
            등록 성공 여부

        Examples:
            >>> DataRegistry.register_data_file(
            ...     "/path/to/evaluation_results/data.json",
            ...     metadata={"total_tasks": 10, "framework": "langchain"}
            ... )
            True
        """
        try:
            cls.REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

            # 기존 레지스트리 로드
            registry = cls._load_registry()

            # 프로젝트 이름 자동 감지
            if project_name is None:
                project_name = cls._detect_project_name(filepath)

            # 파일 존재 여부 확인
            file_path = Path(filepath)
            if not file_path.exists():
                return False

            # 엔트리 생성
            entry = {
                "filepath": str(file_path.resolve()),
                "project_name": project_name,
                "registered_at": datetime.now().isoformat(),
                "last_modified": datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).isoformat(),
                "file_size": file_path.stat().st_size,
                "metadata": metadata or {}
            }

            # 레지스트리에 추가 (중복 제거)
            file_id = str(file_path.resolve())
            registry["data_files"][file_id] = entry

            # 저장
            cls._save_registry(registry)

            return True

        except Exception as e:
            logger.warning("레지스트리 등록 실패: %s", e, exc_info=True)
            return False

    @classmethod
    def _detect_project_name(cls, filepath: str) -> str:
        """
        파일 경로에서 프로젝트 이름 자동 추출

        우선순위:
        1. Git 저장소 루트 디렉토리 이름
        2. evaluation_results의 부모 디렉토리 이름
        3. "unknown_project"

        Args:
            filepath: 파일 경로

        Returns:
            프로젝트 이름
        """
        path = Path(filepath).resolve()

        # 1. Git 저장소 루트 찾기
        current = path.parent
        while current != current.parent:
            if (current / ".git").exists():
                return current.name
            current = current.parent

        # 2. evaluation_results의 부모 디렉토리 이름
        for parent in path.parents:
            if parent.name == "evaluation_results":
                return parent.parent.name

        # 3. 기본값
        return "unknown_project"

    @classmethod
    def _acquire_lock(cls, file_handle, timeout: float = 5.0) -> bool:
        """
        파일 락 획득 (플랫폼 독립적)

        Args:
            file_handle: 파일 핸들
            timeout: 락 획득 대기 시간 (초)

        Returns:
            락 획득 성공 여부
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                if sys.platform == 'win32':
                    # Windows: msvcrt.locking
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix/Linux/Mac: fcntl.flock
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                # Lock is held by another process, wait and retry
                time.sleep(0.1)

        return False

    @classmethod
    def _release_lock(cls, file_handle) -> None:
        """
        파일 락 해제 (플랫폼 독립적)

        Args:
            file_handle: 파일 핸들
        """
        try:
            if sys.platform == 'win32':
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass  # Best effort unlock

    @classmethod
    def _load_registry(cls) -> Dict[str, Any]:
        """
        레지스트리 파일 로드 (동시성 안전)

        Returns:
            레지스트리 딕셔너리
        """
        if not cls.REGISTRY_FILE.exists():
            return {
                "version": "0.5.0",
                "created_at": datetime.now().isoformat(),
                "data_files": {}
            }

        try:
            # Open with shared lock for reading
            with open(cls.REGISTRY_FILE, encoding='utf-8') as f:
                # Acquire shared lock (non-blocking for reads)
                if sys.platform != 'win32':
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)

                try:
                    data = json.load(f)
                finally:
                    # Release lock
                    if sys.platform != 'win32':
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

                return data

        except Exception as e:
            logger.warning("레지스트리 로드 실패, 빈 레지스트리로 시작: %s", e, exc_info=True)
            return {
                "version": "0.5.0",
                "created_at": datetime.now().isoformat(),
                "data_files": {}
            }

    @classmethod
    def _save_registry(cls, registry: Dict[str, Any]) -> bool:
        """
        레지스트리 파일 저장 (동시성 안전)

        Args:
            registry: 저장할 레지스트리 딕셔너리

        Returns:
            저장 성공 여부
        """
        try:
            cls.REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

            # Use exclusive lock for writing
            with open(cls.REGISTRY_FILE, 'w', encoding='utf-8') as f:
                # Acquire exclusive lock with timeout
                if not cls._acquire_lock(f, timeout=5.0):
                    logger.warning("레지스트리 락 획득 실패 (다른 프로세스가 사용 중)")
                    return False

                try:
                    json.dump(registry, f, indent=2, ensure_ascii=False)
                finally:
                    # Always release lock
                    cls._release_lock(f)

            return True

        except Exception as e:
            logger.warning("레지스트리 저장 실패: %s", e, exc_info=True)
            return False

    @classmethod
    def get_all_data_files(
        cls,
        project_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        등록된 모든 데이터 파일 가져오기

        Args:
            project_name: 특정 프로젝트만 필터링 (None이면 전체)

        Returns:
            데이터 파일 정보 리스트 (최신순 정렬)

        Examples:
            >>> # 모든 프로젝트의 데이터
            >>> all_files = DataRegistry.get_all_data_files()
            >>>
            >>> # 특정 프로젝트만
            >>> project_files = DataRegistry.get_all_data_files("my_agent_project")
        """
        registry = cls._load_registry()
        data_files = list(registry["data_files"].values())

        if project_name:
            data_files = [
                f for f in data_files
                if f["project_name"] == project_name
            ]

        # 최신순 정렬
        data_files.sort(key=lambda x: x["registered_at"], reverse=True)

        return data_files

    @classmethod
    def get_projects(cls) -> List[Dict[str, Any]]:
        """
        등록된 모든 프로젝트 정보 가져오기

        Returns:
            프로젝트 정보 리스트 (파일 개수, 최신 업데이트 시간 포함)

        Examples:
            >>> projects = DataRegistry.get_projects()
            >>> for project in projects:
            ...     print(f"{project['name']}: {project['file_count']} files")
        """
        registry = cls._load_registry()
        data_files = registry["data_files"].values()

        # 프로젝트별로 그룹화
        projects_dict: Dict[str, Dict[str, Any]] = {}

        for entry in data_files:
            project = entry.get("project_name", "unknown")

            if project not in projects_dict:
                projects_dict[project] = {
                    "name": project,
                    "file_count": 0,
                    "total_size": 0,
                    "latest_update": None,
                    "files": []
                }

            projects_dict[project]["file_count"] += 1
            projects_dict[project]["total_size"] += entry.get("file_size", 0)
            projects_dict[project]["files"].append(entry)

            # 최신 업데이트 시간 추적
            registered_at = entry.get("registered_at")
            if registered_at is not None and (
                projects_dict[project]["latest_update"] is None
                or registered_at > projects_dict[project]["latest_update"]
            ):
                projects_dict[project]["latest_update"] = registered_at

        # 리스트로 변환 및 정렬
        projects = list(projects_dict.values())
        projects.sort(key=lambda x: x["latest_update"] or "", reverse=True)

        return projects

    @classmethod
    def cleanup_missing_files(cls) -> int:
        """
        존재하지 않는 파일을 레지스트리에서 제거

        Returns:
            제거된 파일 개수

        Examples:
            >>> removed = DataRegistry.cleanup_missing_files()
            >>> print(f"{removed} files removed from registry")
        """
        registry = cls._load_registry()

        initial_count = len(registry["data_files"])

        # 존재하는 파일만 유지
        valid_files = {
            file_id: entry
            for file_id, entry in registry["data_files"].items()
            if Path(entry["filepath"]).exists()
        }

        registry["data_files"] = valid_files
        cls._save_registry(registry)

        removed_count = initial_count - len(valid_files)

        return removed_count

    @classmethod
    def get_registry_info(cls) -> Dict[str, Any]:
        """
        레지스트리 전체 정보 가져오기

        Returns:
            레지스트리 통계 정보
        """
        registry = cls._load_registry()

        total_files = len(registry["data_files"])
        total_size = sum(
            entry.get("file_size", 0)
            for entry in registry["data_files"].values()
        )

        projects = cls.get_projects()

        return {
            "registry_path": str(cls.REGISTRY_FILE),
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "project_count": len(projects),
            "created_at": registry.get("created_at"),
            "version": registry.get("version")
        }

    @classmethod
    def remove_file(cls, filepath: str) -> bool:
        """
        레지스트리에서 특정 파일 제거

        Args:
            filepath: 제거할 파일 경로

        Returns:
            제거 성공 여부
        """
        try:
            registry = cls._load_registry()
            file_id = str(Path(filepath).resolve())

            if file_id in registry["data_files"]:
                del registry["data_files"][file_id]
                cls._save_registry(registry)
                return True

            return False

        except Exception as e:
            logger.warning("파일 제거 실패: %s", e, exc_info=True)
            return False

    @classmethod
    def clear_registry(cls) -> bool:
        """
        레지스트리 전체 초기화

        Returns:
            초기화 성공 여부
        """
        try:
            registry = {
                "version": "0.5.0",
                "created_at": datetime.now().isoformat(),
                "data_files": {}
            }

            return cls._save_registry(registry)

        except Exception as e:
            logger.warning("레지스트리 초기화 실패: %s", e, exc_info=True)
            return False
