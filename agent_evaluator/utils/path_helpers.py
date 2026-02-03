"""
Path Helper Utilities for Zero Configuration
=============================================

이 모듈은 agent_evaluator 패키지 전체에서 사용되는 경로 관련 유틸리티를 제공합니다.
Zero Configuration 원칙에 따라 프로젝트 루트를 자동으로 탐지합니다.
"""

import os
from pathlib import Path
from typing import Optional


def find_project_root() -> Path:
    """
    프로젝트 루트 디렉토리 자동 탐지 (Zero Configuration)

    이 함수는 agent_evaluator 패키지의 모든 클래스에서 사용되는
    통합된 프로젝트 루트 탐지 로직입니다.

    탐지 우선순위:
        1. 환경 변수 AGENT_EVALUATOR_ROOT
           - 명시적으로 프로젝트 루트를 지정
           - 다중 프로젝트 환경에서 유용

        2. Git 저장소 루트
           - .git 디렉토리를 찾아 저장소 루트 확인
           - 개발 환경에서 가장 일반적

        3. Dashboard 디렉토리가 있는 상위 디렉토리
           - app.py 또는 streamlit_dashboard.py 존재 검증
           - agent_evaluator의 실제 Dashboard인지 확인
           - 프로덕션 환경에서 안정적

        4. 현재 작업 디렉토리
           - 위의 모든 방법이 실패한 경우 폴백

    Returns:
        Path: 프로젝트 루트 절대 경로

    Examples:
        >>> from agent_evaluator.utils.path_helpers import find_project_root
        >>> root = find_project_root()
        >>> print(f"Project root: {root}")
        Project root: /home/user/Projects/MyProject

        >>> # 환경 변수로 명시적 지정
        >>> import os
        >>> os.environ['AGENT_EVALUATOR_ROOT'] = '/custom/path'
        >>> root = find_project_root()
        >>> print(root)
        /custom/path

    Note:
        - 반환값은 항상 Path 객체입니다 (str이 아님)
        - Dashboard 검증을 통해 실제 agent_evaluator Dashboard인지 확인
        - 모든 agent_evaluator 클래스에서 이 함수를 사용해야 합니다
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

    # 3. Dashboard 디렉토리 찾기 (실제 agent_evaluator Dashboard 검증)
    # Dashboard가 중첩된 위치(예: Examples/Dashboard)에 있을 수 있음
    current = Path.cwd()
    while current != current.parent:
        # 직접 자식으로 Dashboard가 있는지 확인
        dashboard = current / "Dashboard"
        if dashboard.exists() and dashboard.is_dir():
            # 실제 agent_evaluator Dashboard인지 확인
            if (dashboard / "app.py").exists() or (dashboard / "streamlit_dashboard.py").exists():
                return current.resolve()

        # 하위 디렉토리 안에 Dashboard가 있는지 확인 (1단계만)
        # 예: current/Examples/Dashboard
        try:
            for subdir in current.iterdir():
                if subdir.is_dir() and subdir.name != ".git":
                    nested_dashboard = subdir / "Dashboard"
                    if nested_dashboard.exists() and nested_dashboard.is_dir():
                        if (nested_dashboard / "app.py").exists() or \
                           (nested_dashboard / "streamlit_dashboard.py").exists():
                            return current.resolve()
        except (PermissionError, OSError):
            pass  # 접근 권한 없는 디렉토리는 건너뛰기

        current = current.parent

    # 4. 폴백: 현재 작업 디렉토리
    return Path.cwd().resolve()


def get_evaluation_results_dir(project_root: Optional[Path] = None, create: bool = False) -> Path:
    """
    평가 결과 저장 디렉토리 경로 반환

    Args:
        project_root: 프로젝트 루트 경로 (None이면 자동 탐지)
        create: True이면 디렉토리를 즉시 생성, False이면 경로만 반환

    Returns:
        Path: Dashboard/data/evaluation_results 절대 경로
              (Dashboard 위치는 자동 탐지)

    Examples:
        >>> from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
        >>> # 경로만 반환 (디렉토리 생성 안 함)
        >>> results_dir = get_evaluation_results_dir()
        >>> print(results_dir)
        /home/user/Projects/MyProject/Examples/Dashboard/data/evaluation_results

        >>> # 디렉토리 즉시 생성
        >>> results_dir = get_evaluation_results_dir(create=True)

    Note:
        기본적으로 디렉토리를 생성하지 않습니다 (lazy initialization).
        실제로 디렉토리가 필요한 경우 create=True를 사용하세요.
        Dashboard 위치는 get_dashboard_dir()를 통해 자동으로 탐지됩니다.
    """
    if project_root is None:
        project_root = find_project_root()

    # Dashboard 위치를 동적으로 탐지 (중첩 구조 지원)
    dashboard_dir = get_dashboard_dir(project_root)
    results_dir = dashboard_dir / "data" / "evaluation_results"

    # ⚡ Lazy initialization: create=True일 때만 디렉토리 생성
    if create:
        results_dir.mkdir(parents=True, exist_ok=True)

    return results_dir


def get_dashboard_dir(project_root: Optional[Path] = None) -> Path:
    """
    Dashboard 디렉토리 경로 반환

    Args:
        project_root: 프로젝트 루트 경로 (None이면 자동 탐지)

    Returns:
        Path: Dashboard 절대 경로 (직접 자식 또는 중첩 위치)

    Examples:
        >>> from agent_evaluator.utils.path_helpers import get_dashboard_dir
        >>> dashboard = get_dashboard_dir()
        >>> print(dashboard)
        /home/user/Projects/MyProject/Dashboard
        # 또는
        /home/user/Projects/MyProject/Examples/Dashboard

    Note:
        Dashboard가 project_root/Dashboard에 없으면
        project_root/*/Dashboard 패턴으로 1단계 하위를 검색합니다.
    """
    if project_root is None:
        project_root = find_project_root()

    # 1. 직접 자식으로 Dashboard 확인
    dashboard = project_root / "Dashboard"
    if dashboard.exists() and dashboard.is_dir():
        if (dashboard / "app.py").exists() or (dashboard / "streamlit_dashboard.py").exists():
            return dashboard

    # 2. 중첩된 위치 확인 (1단계 하위)
    try:
        for subdir in project_root.iterdir():
            if subdir.is_dir() and subdir.name != ".git":
                nested_dashboard = subdir / "Dashboard"
                if nested_dashboard.exists() and nested_dashboard.is_dir():
                    if (nested_dashboard / "app.py").exists() or \
                       (nested_dashboard / "streamlit_dashboard.py").exists():
                        return nested_dashboard
    except (PermissionError, OSError):
        pass

    # 3. 폴백: project_root/Dashboard 반환
    # 하지만 생성은 하지 않음 (caller가 create=True일 때만 생성)
    # 이렇게 하면 Dashboard가 실제로 없을 때 불필요한 폴더가 생성되지 않음
    return project_root / "Dashboard"


def is_valid_dashboard(dashboard_path: Path) -> bool:
    """
    주어진 경로가 유효한 agent_evaluator Dashboard인지 검증

    Args:
        dashboard_path: 검증할 Dashboard 경로

    Returns:
        bool: 유효한 Dashboard이면 True

    Examples:
        >>> from agent_evaluator.utils.path_helpers import is_valid_dashboard
        >>> from pathlib import Path
        >>> is_valid_dashboard(Path("/path/to/Dashboard"))
        True
    """
    if not dashboard_path.exists() or not dashboard_path.is_dir():
        return False

    # app.py 또는 streamlit_dashboard.py 중 하나라도 존재하면 유효
    return (dashboard_path / "app.py").exists() or \
           (dashboard_path / "streamlit_dashboard.py").exists()
