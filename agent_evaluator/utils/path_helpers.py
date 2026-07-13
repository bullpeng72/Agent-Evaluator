"""
Path Helper Utilities for Zero Configuration
=============================================

이 모듈은 agent_evaluator 패키지 전체에서 사용되는 경로 관련 유틸리티를 제공합니다.
Zero Configuration 원칙에 따라 프로젝트 루트를 자동으로 탐지합니다.
"""
from __future__ import annotations

import os
from pathlib import Path


def find_project_root() -> Path:
    """
    프로젝트 루트 디렉토리 자동 탐지 (Zero Configuration)

    탐지 우선순위:
        1. 환경 변수 AGENT_EVALUATOR_ROOT — 명시적 지정
        2. Git 저장소 루트 — .git 디렉토리 탐색
        3. 현재 작업 디렉토리 — 폴백

    Returns:
        Path: 프로젝트 루트 절대 경로

    Examples:
        >>> from agent_evaluator.utils.path_helpers import find_project_root
        >>> root = find_project_root()
        >>> print(f"Project root: {root}")
        Project root: /home/user/Projects/MyProject
    """

    # 1. 환경 변수 확인
    if 'AGENT_EVALUATOR_ROOT' in os.environ:
        root = Path(os.environ['AGENT_EVALUATOR_ROOT'])
        if root.exists():
            return root.resolve()

    # 2. Git 저장소 루트 찾기
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current.resolve()
        current = current.parent

    # 3. pyproject.toml / setup.py 기준 프로젝트 루트 찾기
    current = Path.cwd()
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / "setup.py").exists():
            return current.resolve()
        current = current.parent

    # 4. 폴백: 현재 작업 디렉토리
    return Path.cwd().resolve()


def get_evaluation_results_dir(project_root: Path | None = None, create: bool = False) -> Path:
    """
    평가 결과 저장 디렉토리 경로 반환

    우선순위:
        1. 환경 변수 AGENT_EVALUATOR_OUTPUT_DIR
        2. <project_root>/results (기본값)

    Args:
        project_root: 프로젝트 루트 경로 (None이면 자동 탐지)
        create: True이면 디렉토리를 즉시 생성, False이면 경로만 반환

    Returns:
        Path: 평가 결과 디렉토리 절대 경로

    Examples:
        >>> from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
        >>> results_dir = get_evaluation_results_dir()
        >>> print(results_dir)
        /home/user/Projects/MyProject/results
    """
    # 1. 환경 변수 우선
    output_dir_env = os.environ.get('AGENT_EVALUATOR_OUTPUT_DIR', '').strip()
    if output_dir_env:
        results_dir = Path(output_dir_env)
        if not results_dir.is_absolute():
            if project_root is None:
                project_root = find_project_root()
            results_dir = project_root / results_dir
        results_dir = results_dir.resolve()
    else:
        # 2. 기본값: <project_root>/results
        if project_root is None:
            project_root = find_project_root()
        results_dir = project_root / "results"

    if create:
        results_dir.mkdir(parents=True, exist_ok=True)

    return results_dir


def get_dashboard_dir(project_root: Path | None = None) -> Path:
    """
    Dashboard 디렉토리 경로 반환 (하위 호환성 유지)

    Args:
        project_root: 프로젝트 루트 경로 (None이면 자동 탐지)

    Returns:
        Path: <project_root>/Dashboard 경로

    Note:
        v0.5.1+: FastAPI 대시보드는 `agent-eval serve`로 실행합니다.
        이 함수는 하위 호환성을 위해 유지됩니다.
    """
    if project_root is None:
        project_root = find_project_root()
    return project_root / "Dashboard"


def is_valid_dashboard(dashboard_path: Path) -> bool:
    """
    주어진 경로가 유효한 디렉토리인지 검증 (하위 호환성 유지)

    Args:
        dashboard_path: 검증할 경로

    Returns:
        bool: 디렉토리가 존재하면 True
    """
    return dashboard_path.exists() and dashboard_path.is_dir()
