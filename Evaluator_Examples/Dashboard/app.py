#!/usr/bin/env python3
"""
Agent Evaluator Dashboard - Entry Point
========================================

QA Dashboard with agent_evaluator package integration

사용법:
    어떤 위치에서든 실행 가능 (Zero Configuration):
    streamlit run Examples/Dashboard/app.py
    또는
    cd Examples && streamlit run Dashboard/app.py
    또는
    cd Examples/Dashboard && streamlit run app.py

요구사항:
    - agent_evaluator 패키지가 프로젝트 루트에 있어야 함
"""
import sys
import os
from pathlib import Path

# ========================================
# CRITICAL: 경로 설정 (import 전에 실행)
# ========================================
# agent_evaluator 패키지를 import하기 전에 프로젝트 루트를 sys.path에 추가해야 함

def find_project_root_bootstrap() -> Path:
    """
    agent_evaluator를 import하기 전에 프로젝트 루트를 찾는 부트스트랩 함수

    Zero Configuration: 자동 경로 탐지
    탐지 순서:
    1. 환경 변수 AGENT_EVALUATOR_ROOT
    2. Examples 디렉토리가 있는 상위 디렉토리 (이름 무관)
    3. .git이 있는 상위 디렉토리
    4. 현재 파일 위치에서 상위로 탐색 (app.py 기준)
    """
    # 1. 환경 변수 확인
    if 'AGENT_EVALUATOR_ROOT' in os.environ:
        root = Path(os.environ['AGENT_EVALUATOR_ROOT'])
        if root.exists():
            return root.resolve()

    # 2. 현재 파일 위치에서 상위로 탐색 (app.py -> Dashboard -> Examples -> 프로젝트 루트)
    current = Path(__file__).resolve().parent  # Dashboard 디렉토리

    # Dashboard -> Examples 디렉토리 (directory name agnostic)
    if current.name == "Dashboard":
        project_root = current.parent.parent  # 프로젝트 루트
        return project_root

    # 3. Examples 디렉토리 찾기 (현재 작업 디렉토리 기준)
    # Zero Configuration: Search for any directory containing Dashboard/app.py
    current = Path.cwd()
    for _ in range(5):  # 최대 5단계 상위까지 탐색
        # Look for any subdirectory containing Dashboard/app.py
        for subdir in current.iterdir():
            if subdir.is_dir():
                dashboard = subdir / "Dashboard"
                if dashboard.exists() and (dashboard / "app.py").exists():
                    return current.resolve()

        if current == current.parent:
            break
        current = current.parent

    # 4. Git 저장소 루트 찾기
    current = Path.cwd()
    for _ in range(5):
        if (current / ".git").exists():
            return current.resolve()

        if current == current.parent:
            break
        current = current.parent

    # 5. 폴백: 현재 작업 디렉토리
    return Path.cwd().resolve()

# 프로젝트 루트를 sys.path에 추가 (agent_evaluator import를 위해)
project_root_bootstrap = find_project_root_bootstrap()
if str(project_root_bootstrap) not in sys.path:
    sys.path.insert(0, str(project_root_bootstrap))

# ========================================
# 이제 agent_evaluator를 안전하게 import 가능
# ========================================
try:
    from agent_evaluator.utils.path_helpers import (
        find_project_root,
        get_evaluation_results_dir,
        get_dashboard_dir
    )
except ImportError as e:
    print("❌ Error: agent_evaluator 패키지를 찾을 수 없습니다!")
    print(f"   {e}")
    print()
    print(f"🔍 Debug Information:")
    print(f"   현재 작업 디렉토리: {Path.cwd()}")
    print(f"   프로젝트 루트 (추정): {project_root_bootstrap}")
    print(f"   agent_evaluator 경로: {project_root_bootstrap / 'agent_evaluator'}")
    print(f"   agent_evaluator 존재 여부: {(project_root_bootstrap / 'agent_evaluator').exists()}")
    print()
    print("해결 방법:")
    print("  1. 프로젝트 루트에 agent_evaluator 디렉토리가 있는지 확인")
    print("  2. 또는 pip install agent-evaluator로 패키지 설치")
    sys.exit(1)

# Dashboard 디렉토리는 app.py 위치에서 직접 얻기 (Zero Configuration)
# app.py는 항상 Dashboard 폴더 안에 있으므로 이것이 가장 정확함
dashboard_dir = Path(__file__).resolve().parent

# Project root는 agent_evaluator 패키지가 있는 위치
# Dashboard의 상위 디렉토리들을 탐색하여 agent_evaluator가 있는 곳을 찾음
project_root = dashboard_dir.parent  # 먼저 상위 디렉토리 시도
if not (project_root / "agent_evaluator").exists():
    # agent_evaluator가 없으면 한 단계 더 올라감
    project_root = project_root.parent

dashboard_str = str(dashboard_dir)

# CRITICAL FIX: Remove Dashboard directory from sys.path[0]
# When running "streamlit run app.py", the current directory is automatically added to sys.path[0]
# This causes Python to search Dashboard BEFORE site-packages, leading to import errors
while dashboard_str in sys.path:
    sys.path.remove(dashboard_str)

# Add it back at the END (for Dashboard-specific modules only)
sys.path.append(dashboard_str)

# Verify agent_evaluator can be imported from package
try:
    from agent_evaluator import PerformanceMonitor, HybridPerformanceMonitor
except ImportError as e:
    print("❌ Error: agent_evaluator 패키지의 일부 모듈을 import할 수 없습니다!")
    print(f"   {e}")
    print()
    print("해결 방법:")
    print("  1. agent_evaluator 패키지가 올바르게 설치되었는지 확인")
    print("  2. 또는 pip install agent-evaluator로 패키지 설치")
    sys.exit(1)

# 메인 대시보드 실행
# streamlit_dashboard.py는 항상 app.py와 같은 Dashboard 폴더에 있음
dashboard_path = dashboard_dir / "streamlit_dashboard.py"

# Debug: Print paths
print(f"🔍 Debug Information:")
print(f"   Dashboard Dir (from __file__): {dashboard_dir}")
print(f"   Project Root (detected): {project_root}")
print(f"   Main Dashboard Script: {dashboard_path}")
print(f"   Dashboard Script Exists: {dashboard_path.exists()}")

# Verify the dashboard file exists
if not dashboard_path.exists():
    print(f"\n❌ Error: Dashboard file not found at {dashboard_path}")
    print(f"   Expected: streamlit_dashboard.py in same directory as app.py")
    print(f"   Please verify the Dashboard folder structure.")
    sys.exit(1)

# Execute the dashboard script
with open(dashboard_path, 'r', encoding='utf-8') as f:
    exec(f.read(), {'__file__': str(dashboard_path), '__name__': '__main__'})
