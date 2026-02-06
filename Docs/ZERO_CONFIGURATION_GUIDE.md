# ⚙️ Zero Configuration 가이드

별도 설정 없이 자동으로 올바른 위치에 데이터 저장하기

# Zero Configuration 가이드

Agent Evaluator의 Zero Configuration 기능을 활용하여 별도 설정 없이 자동으로 올바른 위치에 데이터를 저장하는 방법을 안내합니다.

## 목차

  1. [개요](<#개요>)
  2. [핵심 개념](<#핵심-개념>)
  3. [사용 방법](<#사용-방법>)
  4. [작동 원리](<#작동-원리>)
  5. [Dashboard 통합](<#dashboard-통합>)
  6. [실전 예시](<#실전-예시>)
  7. [Dashboard 설치](<#dashboard-설치>)
  8. [Path Helpers 모듈 직접 사용](<#path-helpers-사용>)
  9. [고급 설정](<#고급-설정>)
  10. [문제 해결](<#문제-해결>)
  11. [베스트 프랙티스](<#베스트-프랙티스>)
  12. [요약](<#요약>)
  13. [추가 정보](<#추가-정보>)

* * *

## 개요

agent-evaluator는 **Zero Configuration** 철학을 따릅니다. 별도의 설정 파일이나 환경 변수 없이도 자동으로 올바른 위치에 데이터를 저장합니다.

* * *

## 핵심 개념

### 프로젝트 구조

agent-evaluator는 다음과 같은 표준 프로젝트 구조를 권장합니다:
[code] 
    MyProject/                    # 프로젝트 루트
    ├── .git/                     # Git 저장소 (선택사항)
    ├── Dashboard/                # Dashboard 앱
    │   ├── app.py
    │   └── data/                 # ✓ 자동 저장 위치
    │       ├── evaluation_results/    # 평가 결과
    │       └── golden_datasets/       # Golden Datasets
    ├── my_agent.py               # Agent 코드
    └── requirements.txt
[/code]

### 자동 경로 감지

agent-evaluator는 다음 우선순위로 프로젝트 루트를 자동 감지합니다:

  1. **환경 변수** `AGENT_EVALUATOR_ROOT` (명시적 지정)
  2. **Git 저장소 루트** (`.git` 폴더 위치)
  3. **Dashboard 디렉토리** 가 있는 상위 디렉토리 (검증 포함)
  4. **현재 작업 디렉토리** (폴백)

감지된 프로젝트 루트 기준으로 자동으로 `Dashboard/data/evaluation_results/`에 저장합니다.

* * *

## 사용 방법

### 1\. 기본 사용 (Zero Configuration)
[code] 
    from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
    from datetime import datetime
    
    # 1. PerformanceMonitor 생성 (설정 불필요)
    monitor = PerformanceMonitor()
    
    # 2. Task 기록
    task = TaskResult(
        task_id="task_001",
        task_type=TaskType.QA.value,
        success=True,
        completion_score=1.0,
        accuracy_score=0.95,
        execution_time=1.2,
        tokens_used={"input": 100, "output": 50, "total": 150},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now()
    )
    
    monitor.record_task(task)
    
    # 3. 저장 (자동으로 올바른 위치에 저장)
    monitor.save_to_file("my_evaluation.json")
    # → {프로젝트_루트}/Dashboard/data/evaluation_results/my_evaluation.json
[/code]

#### 💡 저장되는 위치

  * Git 프로젝트인 경우: `{Git_Root}/Dashboard/data/evaluation_results/`
  * Dashboard 폴더가 있는 경우: `{Dashboard_Parent}/Dashboard/data/evaluation_results/`
  * 그 외: `{Current_Dir}/Dashboard/data/evaluation_results/`

### 2\. KoreanRAGEvaluator (Zero Configuration)
[code] 
    from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator
    
    # Zero Configuration - 경로 지정 안 함!
    evaluator = KoreanRAGEvaluator()
    # → 자동으로 Dashboard/data/evaluation_results/에 저장
    # → 자동으로 Dashboard/data/golden_datasets/ 사용
    
    # 평가 수행
    results = evaluator.evaluate_dataset(dataset)
    # → {프로젝트_루트}/Dashboard/data/evaluation_results/에 자동 저장
[/code]

### 3\. TestTransparencyManager (Zero Configuration)
[code] 
    from agent_evaluator.utils.test_transparency_manager import TestTransparencyManager
    
    # Zero Configuration - 경로 지정 안 함!
    transparency_mgr = TestTransparencyManager()
    # → 자동으로 Dashboard/data/evaluation_results/에 저장
    # → traces/, annotations/, audit_logs/ 서브디렉토리 자동 생성
    
    # Trace 기록
    trace_id = transparency_mgr.start_metric_calculation("accuracy", "quality")
    transparency_mgr.complete_metric_calculation(trace_id, 0.95)
    # → {프로젝트_루트}/Dashboard/data/evaluation_results/traces/에 자동 저장
[/code]

### 4\. 환경 변수로 명시적 지정

프로젝트 루트를 명시적으로 지정하고 싶은 경우:
[code] 
    # Linux/Mac
    export AGENT_EVALUATOR_ROOT=/path/to/my/project
    
    # Windows
    set AGENT_EVALUATOR_ROOT=C:\path\to\my\project
    
    # Python 코드에서
    import os
    os.environ['AGENT_EVALUATOR_ROOT'] = '/path/to/my/project'
[/code]

### 5\. 절대 경로 사용 (옵션)

특정 위치에 저장하고 싶은 경우:
[code] 
    # 절대 경로 사용 시 자동 경로 감지를 우회
    monitor.save_to_file("/custom/path/my_evaluation.json")
    
    # KoreanRAGEvaluator에서 커스텀 경로 지정
    evaluator = KoreanRAGEvaluator(
        output_dir="/custom/evaluation_results",
        golden_datasets_dir="/custom/golden_datasets"
    )
    
    # TestTransparencyManager에서 커스텀 경로 지정
    transparency_mgr = TestTransparencyManager(output_dir="/custom/evaluation_results")
[/code]

* * *

## 작동 원리

### 통합 경로 헬퍼 모듈

모든 Zero Configuration 로직이 `agent_evaluator.utils.path_helpers` 모듈로 통합되었습니다.

#### ✨ 주요 개선사항

  * **코드 통합** : 113줄의 중복 코드를 단일 모듈로 통합
  * **타입 일관성** : 모든 함수가 `Path` 객체 반환 (하위 호환성 유지)
  * **Dashboard 검증 강화** : `app.py` 또는 `streamlit_dashboard.py` 존재 확인
  * **자동 디렉토리 생성** : 필요한 경로 자동 생성

#### 핵심 함수들
[code] 
    from agent_evaluator.utils.path_helpers import (
        find_project_root,           # 프로젝트 루트 자동 탐지
        get_evaluation_results_dir,  # 평가 결과 디렉토리 경로
        get_dashboard_dir,           # Dashboard 디렉토리 경로
        is_valid_dashboard           # Dashboard 유효성 검증
    )
    
    # 1. 프로젝트 루트 자동 탐지
    project_root = find_project_root()
    print(f"프로젝트 루트: {project_root}")
    # → /home/user/Projects/MyProject
    
    # 2. 평가 결과 디렉토리 (자동 생성)
    results_dir = get_evaluation_results_dir()
    print(f"결과 저장 경로: {results_dir}")
    # → /home/user/Projects/MyProject/Dashboard/data/evaluation_results
    
    # 3. Dashboard 디렉토리
    dashboard_dir = get_dashboard_dir()
    print(f"Dashboard 경로: {dashboard_dir}")
    # → /home/user/Projects/MyProject/Dashboard
    
    # 4. Dashboard 유효성 검증
    is_valid = is_valid_dashboard(dashboard_dir)
    print(f"유효한 Dashboard: {is_valid}")
    # → True (app.py 또는 streamlit_dashboard.py 존재 시)
[/code]

### 프로젝트 루트 감지 과정
[code] 
    from pathlib import Path
    import os
    
    def find_project_root() -> Path:
        """프로젝트 루트 디렉토리 자동 탐지 (Zero Configuration)
    
        탐지 우선순위:
            1. 환경 변수 AGENT_EVALUATOR_ROOT
            2. Git 저장소 루트 (.git)
            3. Dashboard 디렉토리 (app.py/streamlit_dashboard.py 검증)
            4. 현재 작업 디렉토리 (폴백)
    
        Returns:
            Path: 프로젝트 루트 절대 경로
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
        current = Path.cwd()
        while current != current.parent:
            dashboard = current / "Dashboard"
            if dashboard.exists() and dashboard.is_dir():
                # ✓ 실제 agent_evaluator Dashboard인지 확인
                if (dashboard / "app.py").exists() or \
                   (dashboard / "streamlit_dashboard.py").exists():
                    return current.resolve()
            current = current.parent
    
        # 4. 폴백: 현재 작업 디렉토리
        return Path.cwd().resolve()
[/code]

#### 💡 Dashboard 검증 로직

v0.5.0부터 Dashboard 디렉토리를 찾을 때 **실제 agent_evaluator Dashboard인지 검증** 합니다:

  * `app.py` 존재 확인 (Streamlit 앱)
  * `streamlit_dashboard.py` 존재 확인 (대체 이름)
  * 둘 중 하나라도 존재하면 유효한 Dashboard로 인정
  * 이를 통해 우연히 같은 이름을 가진 다른 폴더와 구분

### 자동 저장 로직
[code] 
    def save_to_file(self, filename: str = "performance_data.json"):
        """자동으로 올바른 위치에 저장"""
    
        # 상대 경로인 경우 자동 경로 해석
        if not os.path.isabs(filename):
            project_root = self._find_project_root()
            results_dir = os.path.join(project_root, 'Dashboard', 'data', 'evaluation_results')
            os.makedirs(results_dir, exist_ok=True)  # 디렉토리 자동 생성
            filename = os.path.join(results_dir, filename)
    
        # 파일 저장
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
[/code]

* * *

## Dashboard 통합

### 자동 레지스트리 등록

저장된 파일은 자동으로 `~/.agent_evaluator/registry.json`에 등록됩니다:
[code] 
    {
      "version": "0.5.0",
      "created_at": "2025-12-08T10:00:00",
      "data_files": {
        "/path/to/Dashboard/data/evaluation_results/my_evaluation.json": {
          "filepath": "/path/to/Dashboard/data/evaluation_results/my_evaluation.json",
          "project_name": "MyProject",
          "registered_at": "2025-12-08T10:00:00",
          "last_modified": "2025-12-08T10:00:00",
          "file_size": 1234,
          "metadata": {
            "total_tasks": 10,
            "framework": "langchain"
          }
        }
      }
    }
[/code]

### Dashboard에서 자동 인식

Dashboard는 다음 방법으로 데이터를 자동 인식합니다:

  1. **로컬 데이터** : `Dashboard/data/evaluation_results/` 폴더 스캔
  2. **레지스트리** : `~/.agent_evaluator/registry.json` 읽기
  3. **외부 프로젝트** : "🔗 외부 데이터 소스" 탭에서 확인

* * *

## 실전 예시

### 예시 1: Git 프로젝트
[code] 
    MyProject/
    ├── .git/                    # ← Git 루트 감지
    ├── Dashboard/
    │   └── data/
    │       └── evaluation_results/  # ← 여기에 저장됨
    ├── my_agent.py
    └── run_evaluation.py
[/code]
[code] 
    # run_evaluation.py
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    # ... task 기록 ...
    monitor.save_to_file("results.json")
    # → MyProject/Dashboard/data/evaluation_results/results.json
[/code]

### 예시 2: Dashboard 프로젝트
[code] 
    AgentApp/
    ├── Dashboard/               # ← Dashboard 감지
    │   └── data/
    │       └── evaluation_results/  # ← 여기에 저장됨
    └── src/
        └── agent.py
[/code]
[code] 
    # src/agent.py
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.save_to_file("agent_results.json")
    # → AgentApp/Dashboard/data/evaluation_results/agent_results.json
[/code]

### 예시 3: 환경 변수 사용
[code] 
    # 프로젝트 루트 명시적 지정
    export AGENT_EVALUATOR_ROOT=/home/user/projects/MyAgent
    
    # 어디서든 실행 가능
    cd /tmp
    python /home/user/projects/MyAgent/src/agent.py
    # → /home/user/projects/MyAgent/Dashboard/data/evaluation_results/에 저장
[/code]

* * *

## Dashboard 설치

### 1\. 표준 설치 (권장)

프로젝트 루트에 Dashboard 폴더 생성:
[code] 
    cd /path/to/MyProject
    mkdir -p Dashboard/data/{evaluation_results,golden_datasets}
    
    # Dashboard 파일 다운로드 또는 복사
    # 방법 1: GitHub에서 Dashboard 폴더 다운로드
    # 방법 2: pip 설치 위치에서 Dashboard 템플릿 복사
    # pip show agent-evaluator로 설치 위치 확인 후 복사
[/code]

### 2\. Dashboard 실행
[code] 
    cd /path/to/MyProject
    streamlit run Dashboard/app.py
[/code]

Dashboard가 자동으로 `Dashboard/data/` 하위 데이터를 인식합니다.

* * *

## Path Helpers 모듈 직접 사용

### 기본 사용법

기존 클래스 메서드 대신 `path_helpers` 모듈을 직접 사용할 수 있습니다:
[code] 
    from agent_evaluator.utils.path_helpers import (
        find_project_root,
        get_evaluation_results_dir,
        get_dashboard_dir,
        is_valid_dashboard
    )
    
    # 프로젝트 루트 탐지
    project_root = find_project_root()
    print(f"📁 프로젝트 루트: {project_root}")
    
    # 평가 결과 디렉토리 (자동 생성됨)
    results_dir = get_evaluation_results_dir()
    print(f"💾 결과 저장 경로: {results_dir}")
    
    # Dashboard 디렉토리
    dashboard_dir = get_dashboard_dir()
    print(f"📊 Dashboard 경로: {dashboard_dir}")
    
    # Dashboard 유효성 검증
    if is_valid_dashboard(dashboard_dir):
        print("✅ 유효한 Dashboard입니다!")
    else:
        print("⚠️ Dashboard가 존재하지 않거나 유효하지 않습니다.")
[/code]

### 마이그레이션 가이드

기존 코드를 새로운 `path_helpers` 모듈로 마이그레이션하는 방법:

#### Before (하드코딩된 경로)
[code] 
    from pathlib import Path
    
    # ❌ 문제: 상위 디렉토리를 하드코딩하면 잘못된 위치에 저장될 수 있음
    PROJECT_ROOT = Path(__file__).parent.parent
    EVALUATION_RESULTS_DIR = PROJECT_ROOT / "Dashboard" / "data" / "evaluation_results"
    
    # 결과 저장
    with open(EVALUATION_RESULTS_DIR / "results.json", 'w') as f:
        json.dump(data, f)
[/code]

#### After (Zero Configuration)
[code] 
    from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
    
    # ✅ 해결: 자동으로 올바른 위치 탐지
    results_dir = get_evaluation_results_dir()
    
    # 결과 저장 (디렉토리 자동 생성됨)
    with open(results_dir / "results.json", 'w') as f:
        json.dump(data, f)
[/code]

#### Before (클래스 메서드 사용)
[code] 
    from agent_evaluator import PerformanceMonitor
    
    # ✓ 동작하지만 권장하지 않음
    project_root = PerformanceMonitor._find_project_root()
    results_dir = project_root / "Dashboard" / "data" / "evaluation_results"
[/code]

#### After (직접 import)
[code] 
    from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir
    
    # ✅ 권장: 직접 path_helpers 모듈 사용
    project_root = find_project_root()
    results_dir = get_evaluation_results_dir()
[/code]

#### 💡 하위 호환성 보장

기존 클래스 메서드(`PerformanceMonitor._find_project_root()` 등)는 **계속 지원** 됩니다. 내부적으로 `path_helpers` 모듈을 호출하므로 동작은 동일합니다.

  * ✅ 기존 코드: 수정 없이 계속 사용 가능
  * ✅ 새 코드: `path_helpers` 직접 사용 권장

### 고급 사용 예시

#### 커스텀 프로젝트 루트 지정
[code] 
    from pathlib import Path
    from agent_evaluator.utils.path_helpers import get_evaluation_results_dir
    
    # 특정 프로젝트 루트 지정
    custom_root = Path("/path/to/custom/project")
    results_dir = get_evaluation_results_dir(project_root=custom_root)
    # → /path/to/custom/project/Dashboard/data/evaluation_results
    
    # 환경 변수로 전역 설정
    import os
    os.environ['AGENT_EVALUATOR_ROOT'] = '/path/to/custom/project'
    
    # 이후 모든 호출은 지정된 루트 사용
    results_dir = get_evaluation_results_dir()
    # → /path/to/custom/project/Dashboard/data/evaluation_results
[/code]

#### 여러 프로젝트 동시 관리
[code] 
    from pathlib import Path
    from agent_evaluator.utils.path_helpers import get_evaluation_results_dir, is_valid_dashboard
    
    # 프로젝트 A
    project_a = Path("/projects/ProjectA")
    results_a = get_evaluation_results_dir(project_a)
    print(f"Project A 결과: {results_a}")
    
    # 프로젝트 B
    project_b = Path("/projects/ProjectB")
    results_b = get_evaluation_results_dir(project_b)
    print(f"Project B 결과: {results_b}")
    
    # Dashboard 유효성 개별 검증
    for project in [project_a, project_b]:
        dashboard = project / "Dashboard"
        status = "✅ 유효" if is_valid_dashboard(dashboard) else "❌ 무효"
        print(f"{project.name}: {status}")
[/code]

### path_helpers 모듈 사용의 이점

이점 | 설명  
---|---  
**코드 중복 제거** | 113줄의 중복 코드를 단일 모듈로 통합  
**타입 안전성** | 일관된 `Path` 객체 반환으로 타입 에러 방지  
**Dashboard 검증** | 실제 agent_evaluator Dashboard인지 자동 확인  
**자동 생성** | 필요한 디렉토리를 자동으로 생성  
**명시적 API** | 용도에 맞는 전용 함수 제공 (`get_evaluation_results_dir` 등)  
**하위 호환성** | 기존 코드를 수정하지 않아도 됨  
**테스트 용이성** | 경로 로직을 독립적으로 테스트 가능  
  
* * *

## 고급 설정

### 커스텀 데이터 경로

특정 경로를 사용하고 싶은 경우:
[code] 
    # 방법 1: 환경 변수
    import os
    os.environ['AGENT_EVALUATOR_ROOT'] = '/custom/path'
    
    # 방법 2: 절대 경로
    monitor.save_to_file("/custom/path/Dashboard/data/evaluation_results/results.json")
[/code]

### 멀티 프로젝트 환경

여러 프로젝트를 운영하는 경우:
[code] 
    Projects/
    ├── ProjectA/
    │   └── Dashboard/data/evaluation_results/  # ProjectA 데이터
    ├── ProjectB/
    │   └── Dashboard/data/evaluation_results/  # ProjectB 데이터
    └── Shared_Dashboard/
        └── data/
            └── evaluation_results/              # 통합 대시보드용 (레지스트리에서 가져오기)
[/code]

* * *

## 문제 해결

### Q1: 데이터가 잘못된 위치에 저장됩니다

#### ⚠️ 확인사항

  1. 현재 작업 디렉토리 확인: `pwd` (Linux/Mac) 또는 `cd` (Windows)
  2. Git 저장소 확인: `.git` 폴더 위치
  3. Dashboard 폴더 확인: `Dashboard/` 디렉토리 존재 여부

**해결방법:**
[code] 
    # 프로젝트 루트 확인
    from agent_evaluator import PerformanceMonitor
    monitor = PerformanceMonitor()
    print("감지된 프로젝트 루트:", monitor._find_project_root())
    
    # 명시적 지정
    import os
    os.environ['AGENT_EVALUATOR_ROOT'] = '/correct/path'
[/code]

### Q2: Dashboard에서 데이터가 보이지 않습니다

**확인사항:**

  1. Dashboard 실행 위치가 올바른지 확인
  2. `Dashboard/data/evaluation_results/` 폴더에 JSON 파일 존재 확인
  3. 파일 권한 확인

**해결방법:**
[code] 
    # 데이터 파일 확인
    ls -la Dashboard/data/evaluation_results/
    
    # Dashboard 실행 (올바른 위치에서)
    cd /path/to/MyProject
    streamlit run Dashboard/app.py
[/code]

### Q3: 레지스트리에 등록되지 않습니다

**확인사항:**

  * `~/.agent_evaluator/registry.json` 파일 존재 및 권한 확인

**해결방법:**
[code] 
    # 레지스트리 파일 확인
    cat ~/.agent_evaluator/registry.json
    
    # 레지스트리 디렉토리 재생성
    mkdir -p ~/.agent_evaluator
    chmod 755 ~/.agent_evaluator
[/code]

* * *

## 베스트 프랙티스

### ✅ 권장 사항

  1. **Git 프로젝트 사용** : Git 저장소로 관리하면 자동 감지가 더 정확합니다
  2. **Dashboard 폴더 생성** : 프로젝트 루트에 `Dashboard/` 폴더를 미리 생성
  3. **상대 경로 사용** : `save_to_file("results.json")` \- 자동 경로 감지 활용
  4. **일관된 구조 유지** : 표준 프로젝트 구조 유지

### ❌ 피해야 할 사항

  1. **절대 경로 남용** : 가능한 상대 경로 사용
  2. **임의 위치에서 실행** : 프로젝트 루트 또는 하위 디렉토리에서 실행
  3. **Dashboard 폴더 이름 변경** : `Dashboard` 이름 유지
  4. **환경 변수 불필요한 설정** : Zero Configuration의 장점 활용

* * *

## 요약

항목 | 설명  
---|---  
**Zero Configuration** | 별도 설정 없이 자동으로 올바른 위치에 저장  
**통합 모듈** | `agent_evaluator.utils.path_helpers`  
**핵심 함수들** | `find_project_root()`, `get_evaluation_results_dir()`, `get_dashboard_dir()`, `is_valid_dashboard()`  
**지원 클래스** | `PerformanceMonitor`, `HybridPerformanceMonitor`, `KoreanRAGEvaluator`, `TestTransparencyManager`  
**프로젝트 루트 감지** | 환경변수 → Git 루트 → Dashboard 폴더 (검증) → 현재 디렉토리  
**Dashboard 검증** | `app.py` 또는 `streamlit_dashboard.py` 존재 확인  
**자동 저장 경로** | `{프로젝트_루트}/Dashboard/data/evaluation_results/`  
**Golden Datasets** | `{프로젝트_루트}/Dashboard/data/golden_datasets/`  
**Transparency 데이터** | `{프로젝트_루트}/Dashboard/data/evaluation_results/traces/`  
**자동 레지스트리 등록** | `~/.agent_evaluator/registry.json`에 자동 등록  
**Dashboard 통합** | Dashboard가 자동으로 데이터 인식  
**환경 변수** | `AGENT_EVALUATOR_ROOT`로 명시적 지정 가능  
**하위 호환성** | 기존 클래스 메서드 계속 지원 (내부적으로 통합 모듈 사용)  
**100% 준수율** | 모든 핵심 클래스가 Zero Configuration 지원 ✅  
  
* * *

## 추가 정보

  * **Dashboard 가이드** : [DASHBOARD.html](<DASHBOARD.html>)
  * **시작 가이드** : [GETTING_STARTED.html](<GETTING_STARTED.html>)
  * **배포 가이드** : [DEPLOYMENT_GUIDE.html](<DEPLOYMENT_GUIDE.html>)
  * **API 참조** : [API_REFERENCE.html](<API_REFERENCE.html>)

* * *

#### 🎉 100% Zero Configuration 달성!

agent-evaluator v0.5.0 버전부터 모든 핵심 클래스가 Zero Configuration을 완벽하게 지원합니다!

  * ✅ `PerformanceMonitor` \- 자동 경로 감지
  * ✅ `HybridPerformanceMonitor` \- 상속으로 자동 적용
  * ✅ `KoreanRAGEvaluator` \- 스크립트 위치 기반 자동 감지
  * ✅ `TestTransparencyManager` \- 자동 경로 감지

#### 주요 특징

  * **통합 경로 헬퍼 모듈** : `agent_evaluator.utils.path_helpers` 제공
  * **코드 중복 제거** : 중복 경로 탐지 로직을 단일 모듈로 통합
  * **Dashboard 검증 강화** : `app.py` 또는 `streamlit_dashboard.py` 자동 검증
  * **타입 일관성** : 모든 함수가 `Path` 객체 반환
  * **자동 디렉토리 생성** : `get_evaluation_results_dir()`가 필요한 경로 자동 생성
  * **클래스 메서드 제거** : `_find_project_root()` 메서드 제거, `path_helpers` 직접 사용 권장

* * *

**문서 버전** : 0.5.0  
**최종 업데이트** : 2025-12-15  
**변경사항** :  
\- Evaluator_Examples 경로 탐지 로직 제거  
\- 클래스 메서드 _find_project_root() 제거, path_helpers 직접 사용 권장  
\- 통합 경로 헬퍼 모듈(`path_helpers`) 추가  
\- Dashboard 검증 로직 강화  
\- 마이그레이션 가이드 추가  
\- 고급 사용 예시 추가
