# Zero Configuration 가이드

별도 설정 없이 자동으로 올바른 위치에 데이터를 저장하는 방법 — Agent Evaluator v0.7.3

## 목차

1. [개요](#개요)
2. [프로젝트 구조](#프로젝트-구조)
3. [자동 경로 감지 원리](#자동-경로-감지-원리)
4. [기본 사용법](#기본-사용법)
5. [Path Helpers 모듈](#path-helpers-모듈)
6. [환경 변수 설정](#환경-변수-설정)
7. [Dashboard 통합](#dashboard-통합)
8. [실전 예시](#실전-예시)
9. [고급 설정](#고급-설정)
10. [문제 해결](#문제-해결)
11. [베스트 프랙티스](#베스트-프랙티스)

---

## 개요

agent-evaluator는 **Zero Configuration** 철학을 따릅니다. 별도의 설정 파일이나 환경 변수 없이도 자동으로 올바른 위치에 데이터를 저장합니다.

v0.7.3 기준 모든 핵심 클래스가 Zero Configuration을 완벽하게 지원합니다:

- `PerformanceMonitor` / `HybridPerformanceMonitor`
- `KoreanRAGEvaluator`
- `TestTransparencyManager`
- `QuickEval`

---

## 프로젝트 구조

agent-evaluator는 다음과 같은 표준 프로젝트 구조를 권장합니다:

```
MyProject/                    # 프로젝트 루트
├── .git/                     # Git 저장소 (선택사항)
├── results/                  # 자동 저장 위치 (기본값)
│   ├── *_evaluation.json     # 평가 결과
│   ├── *_report.html         # HTML 리포트
│   └── golden_datasets/      # Golden Datasets
├── data/
│   └── golden_datasets/      # GoldenSetBuilder 기본 경로
├── my_agent.py
└── requirements.txt
```

---

## 자동 경로 감지 원리

agent-evaluator는 다음 우선순위로 결과 저장 위치를 결정합니다:

1. **환경 변수** `AGENT_EVALUATOR_OUTPUT_DIR` (명시적 지정, 최우선)
2. **환경 변수** `AGENT_EVALUATOR_ROOT` (프로젝트 루트 지정)
3. **Git 저장소 루트** 아래 `results/` 디렉토리
4. **현재 작업 디렉토리** 아래 `results/` (폴백)

감지된 위치에 자동으로 `results/` 디렉토리를 생성하고 저장합니다.

### 탐지 로직 (내부 구현)

```python
from pathlib import Path
import os

def find_project_root() -> Path:
    # 1. 환경 변수 확인
    if 'AGENT_EVALUATOR_ROOT' in os.environ:
        root = Path(os.environ['AGENT_EVALUATOR_ROOT'])
        if root.exists():
            return root.resolve()

    # 2. Git 저장소 루트 찾기 (상위 디렉토리 순회)
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current.resolve()
        current = current.parent

    # 3. 폴백: 현재 작업 디렉토리
    return Path.cwd().resolve()
```

---

## 기본 사용법

### 권장 방식: QuickEval 데코레이터

```python
from agent_evaluator import QuickEval

# output_dir 생략 → 자동 경로 감지
eval = QuickEval()

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

@eval.rag
def rag_agent(question: str, context: str = "", ground_truth: str = "") -> str:
    return retriever.query(question, context)

# 평가 실행
my_agent("한국의 수도는?", ground_truth="서울")

# 저장 (자동으로 {프로젝트_루트}/results/ 에 저장)
eval.save()
```

### 저장 위치 확인

```python
from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir

print("프로젝트 루트:", find_project_root())
# → /home/user/Projects/MyProject

print("결과 저장 경로:", get_evaluation_results_dir())
# → /home/user/Projects/MyProject/results
```

### PerformanceMonitor 직접 사용

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

# output_dir 생략 → 자동 경로 감지
monitor = PerformanceMonitor()

result = create_taskresult(
    task_id="task_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=1.2,
    task_type="qa",
)

monitor.record_task(result)

# 저장 — 자동으로 {프로젝트_루트}/results/ 에 저장
monitor.save_to_file("my_evaluation")
# → MyProject/results/my_evaluation_evaluation.json
# → MyProject/results/my_evaluation_report.html
```

### KoreanRAGEvaluator

```python
from agent_evaluator.datasets.korean_rag_evaluator import KoreanRAGEvaluator

# output_dir 생략 → 자동으로 results/에 저장
evaluator = KoreanRAGEvaluator()

results = evaluator.evaluate_dataset(dataset)
# → {프로젝트_루트}/results/에 자동 저장
```

### TestTransparencyManager

```python
from agent_evaluator.utils.transparency_manager import TestTransparencyManager

# 경로 지정 없이 사용
transparency_mgr = TestTransparencyManager()

trace_id = transparency_mgr.start_metric_calculation("accuracy", "quality")
transparency_mgr.complete_metric_calculation(trace_id, 0.95)
# → {프로젝트_루트}/results/traces/에 자동 저장
```

---

## Path Helpers 모듈

모든 Zero Configuration 로직은 `agent_evaluator.utils.path_helpers` 모듈로 통합되어 있습니다.

### 주요 함수

```python
from agent_evaluator.utils.path_helpers import (
    find_project_root,           # 프로젝트 루트 자동 탐지
    get_evaluation_results_dir,  # 평가 결과 디렉토리 경로 (자동 생성)
    get_dashboard_dir,           # Dashboard 디렉토리 경로
    is_valid_dashboard           # Dashboard 유효성 검증
)

# 프로젝트 루트 탐지
project_root = find_project_root()
print(f"프로젝트 루트: {project_root}")

# 평가 결과 디렉토리 (없으면 자동 생성됨)
results_dir = get_evaluation_results_dir()
print(f"결과 저장 경로: {results_dir}")
```

### 커스텀 프로젝트 루트 지정

```python
from pathlib import Path
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir

custom_root = Path("/path/to/custom/project")
results_dir = get_evaluation_results_dir(project_root=custom_root)
# → /path/to/custom/project/results
```

### 여러 프로젝트 동시 관리

```python
from pathlib import Path
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir

project_a = Path("/projects/ProjectA")
project_b = Path("/projects/ProjectB")

results_a = get_evaluation_results_dir(project_a)
results_b = get_evaluation_results_dir(project_b)

print(f"Project A: {results_a}")
print(f"Project B: {results_b}")
```

### 마이그레이션 가이드

하드코딩된 경로를 Zero Configuration으로 전환하는 방법:

**Before (하드코딩)**
```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent  # 잘못된 위치에 저장될 수 있음
EVALUATION_RESULTS_DIR = PROJECT_ROOT / "results"

with open(EVALUATION_RESULTS_DIR / "results.json", 'w') as f:
    json.dump(data, f)
```

**After (Zero Configuration)**
```python
from agent_evaluator.utils.path_helpers import get_evaluation_results_dir

results_dir = get_evaluation_results_dir()  # 자동으로 올바른 위치 탐지

with open(results_dir / "results.json", 'w') as f:
    json.dump(data, f)
```

> `PerformanceMonitor._find_project_root()` 클래스 메서드는 제거되었습니다.
> `from agent_evaluator.utils.path_helpers import find_project_root`를 직접 사용하세요.

---

## 환경 변수 설정

명시적으로 경로를 지정하고 싶은 경우 환경 변수를 사용합니다:

```bash
# 결과 저장 디렉토리 직접 지정 (최우선)
export AGENT_EVALUATOR_OUTPUT_DIR=/path/to/results

# 프로젝트 루트 지정
export AGENT_EVALUATOR_ROOT=/path/to/my/project
```

```python
# Python 코드에서 설정
import os
os.environ['AGENT_EVALUATOR_ROOT'] = '/path/to/my/project'

# 이후 모든 save_to_file() 호출은 지정된 루트 사용
monitor.save_to_file("my_evaluation")
# → /path/to/my/project/results/my_evaluation_evaluation.json
```

### 특정 위치에 직접 저장

```python
# 절대 경로 사용 시 자동 경로 감지를 우회
monitor.save_to_file("/custom/path/results/results.json")

evaluator = KoreanRAGEvaluator(
    output_dir="/custom/evaluation_results",
    golden_datasets_dir="/custom/golden_datasets"
)
```

---

## Dashboard 통합

### FastAPI 대시보드 시작

```bash
# 기본 실행 (포트 8765)
agent-eval dashboard

# results/ 디렉토리 지정
agent-eval dashboard results/

# 포트 및 파일 감시 옵션
agent-eval dashboard --port 8080 --watch
```

대시보드는 `results/` 디렉토리의 평가 결과를 자동으로 인식합니다.
품질 / 성능 / 에이전틱 / 보안 관점의 UI로 데이터를 시각화합니다.

### 자동 레지스트리 등록

`save_to_file()` 호출 시 결과 파일이 `~/.agent_evaluator/registry.json`에 자동 등록됩니다:

```json
{
  "version": "0.7.3",
  "created_at": "2026-04-07T10:00:00",
  "data_files": {
    "/path/to/results/my_evaluation.json": {
      "filepath": "/path/to/results/my_evaluation.json",
      "project_name": "MyProject",
      "registered_at": "2026-04-07T10:00:00",
      "last_modified": "2026-04-07T10:00:00",
      "file_size": 1234,
      "metadata": {
        "total_tasks": 10,
        "framework": "langchain"
      }
    }
  }
}
```

---

## 실전 예시

### 예시 1: Git 프로젝트

```
MyProject/
├── .git/                    # Git 루트 자동 감지
├── results/                 # 여기에 자동 저장
│   ├── my_eval_evaluation.json
│   └── my_eval_report.html
├── my_agent.py
└── run_evaluation.py
```

```python
# run_evaluation.py
from agent_evaluator import QuickEval

eval = QuickEval()  # Git 루트 자동 감지

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

my_agent("테스트 질문", ground_truth="예상 답변")
eval.save()  # → MyProject/results/quickeval.json
```

### 예시 2: 일반 프로젝트 (.git 없음)

```
AgentApp/
├── results/                 # 자동 생성/저장
└── src/
    └── agent.py
```

```python
# src/agent.py
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor()
monitor.save_to_file("agent_results")
# → AgentApp/results/agent_results_evaluation.json
```

### 예시 3: 환경 변수로 루트 명시

```bash
export AGENT_EVALUATOR_ROOT=/home/user/projects/MyAgent

# 어느 디렉토리에서 실행해도 동일한 위치에 저장
cd /tmp
python /home/user/projects/MyAgent/src/agent.py
# → /home/user/projects/MyAgent/results/ 에 저장
```

### 예시 4: CI/CD 품질 게이트

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    return llm.invoke(question)

# 평가 실행
for q, gt in test_cases:
    my_agent(q, ground_truth=gt)

eval.save()

# CI/CD 게이트 — 실패 시 sys.exit(1)
eval.gate(tcr=85, accuracy=70)
```

---

## 고급 설정

### 멀티 프로젝트 환경

```
Projects/
├── ProjectA/
│   └── results/    # ProjectA 전용 데이터
├── ProjectB/
│   └── results/    # ProjectB 전용 데이터
```

각 프로젝트 디렉토리에서 실행하면 해당 프로젝트의 `results/`에 자동 저장됩니다.

### 자동 저장 (auto_save)

```python
monitor = PerformanceMonitor(
    output_dir="results/",
    auto_save=True,
    auto_save_interval=10,      # 10건마다 자동 저장
    auto_save_filename="auto_checkpoint",
)
```

### QuickEval 자동 저장

```python
eval = QuickEval("results/", auto_save=True, auto_save_interval=10)
```

---

## 문제 해결

### Q1: 데이터가 잘못된 위치에 저장됩니다

현재 감지된 경로를 확인하세요:

```python
from agent_evaluator.utils.path_helpers import find_project_root, get_evaluation_results_dir

print("감지된 프로젝트 루트:", find_project_root())
print("결과 저장 경로:", get_evaluation_results_dir())
```

올바르지 않다면 환경 변수로 명시 지정:

```python
import os
os.environ['AGENT_EVALUATOR_ROOT'] = '/correct/path'
```

### Q2: Dashboard에서 데이터가 보이지 않습니다

1. `results/` 폴더에 JSON 파일 존재 확인: `ls -la results/`
2. Dashboard를 프로젝트 루트에서 실행했는지 확인
3. 파일 권한 확인

```bash
cd /path/to/MyProject
agent-eval dashboard
```

### Q3: 레지스트리에 등록되지 않습니다

```bash
# 레지스트리 파일 확인
cat ~/.agent_evaluator/registry.json

# 레지스트리 디렉토리 재생성
mkdir -p ~/.agent_evaluator
chmod 755 ~/.agent_evaluator
```

---

## 베스트 프랙티스

**권장 사항:**

- **Git 프로젝트 사용** — Git 저장소로 관리하면 자동 감지가 가장 정확합니다
- **상대 경로 사용** — `save_to_file("results.json")` 형태로 자동 경로 감지 활용
- **QuickEval 사용** — 데코레이터 방식이 가장 간결하고 권장됩니다
- **일관된 구조 유지** — 표준 `results/` 폴더 구조 유지

**피해야 할 사항:**

- 소스 코드에 절대 경로 하드코딩
- 프로젝트 루트 외부에서 스크립트 실행
- `AGENT_EVALUATOR_ROOT` 환경 변수를 불필요하게 남용 (Zero Configuration의 장점 활용)

---

## 요약

| 항목 | 설명 |
|------|------|
| **Zero Configuration** | 별도 설정 없이 자동으로 올바른 위치에 저장 |
| **통합 모듈** | `agent_evaluator.utils.path_helpers` |
| **핵심 함수** | `find_project_root()`, `get_evaluation_results_dir()` |
| **경로 감지 순서** | 환경변수 → Git 루트 → 현재 디렉토리 |
| **자동 저장 경로** | `{프로젝트_루트}/results/` |
| **Golden Datasets** | `{프로젝트_루트}/data/golden_datasets/` |
| **환경 변수** | `AGENT_EVALUATOR_OUTPUT_DIR` (직접), `AGENT_EVALUATOR_ROOT` (루트) |
| **레지스트리** | `~/.agent_evaluator/registry.json`에 자동 등록 |

---

**문서 버전**: v0.7.3  
**최종 업데이트**: 2026-04-07
