# Chapter 26. 완성: CI/CD와 주간 루틴으로 닫기

> **이 챕터에서 배우는 것**
> - 측정이 자동화되지 않으면 지속되지 않는 이유와 자동화 설계 원칙
> - 골든 데이터셋이 자동으로 쌓이는 패턴과 CI에서 매번 평가하는 방법
> - 단발성 이상이 아닌 **추세**를 감지하는 주간 리뷰 루틴
> - Part VI 전체를 관통하는 **재현 가능한 이식 체크리스트**
> - Lecture_forge에서 발견된 Gate D 비용 추세 이슈 사례

> **독자별 읽기 가이드**
> - **👨‍💻 개발자**: §26.2(CI/CD 통합)와 §26.3(골든 데이터셋)를 중심으로 읽으면 당장 GitHub Actions에 적용할 수 있습니다.
> - **📋 QA 관리자**: §26.4(주간 리뷰)와 §26.6(이식 체크리스트)를 읽으면 팀 운영 루틴의 뼈대를 만들 수 있습니다.
> - **이 챕터는 Part VI의 결론입니다.** Ch22–25까지의 모든 작업이 이 챕터에서 자동화 루틴으로 완성됩니다.

---

## 26.1 측정은 자동화되지 않으면 지속되지 않는다

Ch24–25에서 측정 코드를 삽입했다. 이제 `lf create`를 실행할 때마다 Gate 리포트가 나온다.

하지만 이것만으로는 충분하지 않다. 개발자가 직접 실행할 때만 측정된다. 다음 상황에서는 측정이 이루어지지 않는다.

- 다른 팀원이 기존 방식으로 실행하는 경우
- 코드가 변경되어 배포되기 직전
- 의존성이 업그레이드되어 프롬프트 동작이 달라진 경우
- 한 달이 지나 품질이 조금씩 하락하고 있는 경우

이 네 가지 상황을 모두 커버하려면 측정이 **사람의 행동과 독립적으로** 실행되어야 한다. 코드가 변경될 때 자동으로, 일정 주기로 자동으로, 품질이 떨어질 때 자동으로 알려줘야 한다.

CI/CD 통합과 주간 루틴이 그 역할을 한다.

---

## 26.2 CI/CD 통합: PR마다 품질을 확인한다

> **용어: PR(Pull Request)**  
> PR은 개발자가 자신의 브랜치에서 작업한 코드 변경 사항을 메인 브랜치에 합치기 전에 팀에게 검토를 요청하는 절차다. GitHub에서는 "Pull Request", GitLab에서는 "Merge Request(MR)"라고 부른다. CI/CD 파이프라인은 PR이 열릴 때마다 자동으로 실행되어, 변경 코드가 품질 기준을 통과하는지 확인한다. 기준을 통과하지 못하면 머지(merge, 코드 합치기)가 차단된다.

### 설계 원칙

CI에서 평가를 실행하는 방법은 두 가지다.

**방법 A: 실제 LLM 호출로 평가**: 매 PR마다 실제로 강의를 생성해서 Gate 판정을 한다. 정확하지만 시간이 오래 걸리고 비용이 발생한다.

**방법 B: 골든 데이터셋 재실행**: 미리 준비된 입출력 쌍을 `QuickEval.replay()`로 재실행해 Gate 판정을 한다. 빠르고 비용이 없지만, 골든셋이 최신이어야 한다.

두 방법을 병행한다. PR마다 방법 B로 빠른 판정을 하고, 주 1회 방법 A로 실제 생성 품질을 확인한다.

### GitHub Actions 설정

```yaml
# .github/workflows/quality-gate.yml

name: Agent Quality Gate

on:
  push:
    branches: [main]
  pull_request:
    paths:
      - "src/**"           # 소스 변경 시만
      - "templates/**"     # 프롬프트 템플릿 변경 시만
  schedule:
    - cron: "0 2 * * 1"   # 매주 월요일 02:00 — 실제 생성 품질 검증

jobs:
  # ── PR마다 실행: 골든 데이터셋 재실행 (빠름, 비용 없음) ─────────────
  gate-check:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' || github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4

      - name: Python 환경 설정
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: 의존성 설치
        run: |
          pip install -e ".[dev]"
          pip install agent-evaluator

      - name: 골든 데이터셋 Gate 판정
        run: |
          python scripts/run_golden_eval.py \
            --dataset golden_cases/qa_dataset.json \
            --output results/ci_eval.json

          agent-eval gate results/ci_eval.json \
            --tcr 85 \
            --accuracy 70 \
            --min-gate-score 0.75 \
            --group-weights A:2.0,E:3.0,F:1.5,D:1.2

      - name: 추세 회귀 감지
        run: |
          agent-eval trend results/ \
            --window 8 \
            --fail-on-regression \
            --output-json results/trend_report.json

      - name: 리포트 아티팩트 저장
        uses: actions/upload-artifact@v4
        if: always()   # 실패해도 리포트는 저장
        with:
          name: gate-report-${{ github.sha }}
          path: |
            results/ci_eval.html
            results/trend_report.json
          retention-days: 30

  # ── 주 1회: 실제 LLM 호출로 생성 품질 검증 (느림, 비용 발생) ──────
  weekly-full-eval:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v4

      - name: 의존성 설치
        run: |
          pip install -e ".[dev]"
          pip install agent-evaluator

      - name: 실제 강의 생성 평가 (골든 케이스 3건)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python scripts/run_weekly_eval.py \
            --cases golden_cases/weekly_topics.json \
            --output results/weekly_eval.json

      - name: Gate 판정 및 골든 데이터셋 갱신
        run: |
          agent-eval gate results/weekly_eval.json \
            --min-gate-score 0.75 \
            --group-weights A:2.0,E:3.0,F:1.5,D:1.2

          agent-eval dataset build results/ \
            --min-score 0.80 \
            --output golden_cases/qa_dataset.json
```

### 골든 데이터셋 재실행 스크립트

```python
# scripts/run_golden_eval.py

import json
import argparse
from pathlib import Path
from agent_evaluator import PerformanceMonitor, create_taskresult


def run_golden_eval(dataset_path: str, output_path: str):
    """
    골든 데이터셋의 입출력 쌍을 재현해 Gate 판정용 결과 파일을 생성한다.

    실제 LLM 호출 없이 기존 결과를 재현하므로 비용이 발생하지 않는다.

    PerformanceMonitor는 평가 결과를 모아서 Gate 리포트를 생성하는
    중앙 저장소다. create_taskresult()로 만든 TaskResult를 record_task()로
    전달하면 Gate 집계에 포함된다.
    """
    output_dir = str(Path(output_path).parent)
    monitor = PerformanceMonitor(output_dir=output_dir, use_korean_tokenizer=True)

    # build_golden_dataset.py가 저장한 JSON 배열을 그대로 읽는다
    items = json.loads(Path(dataset_path).read_text())

    for item in items:
        # ① 각 골든 케이스를 TaskResult로 변환 — 점수 자동 계산
        result = create_taskresult(
            task_id=item["task_id"],
            question=item["question"],
            response=item["response"],
            ground_truth=item.get("ground_truth", ""),
            execution_time=item.get("execution_time", 1.0),
            task_type=item.get("task_type", "qa"),
        )
        # ② 모니터에 기록 (나중에 save_to_file()로 Gate 리포트 생성)
        monitor.record_task(result)

    stem = Path(output_path).stem
    monitor.save_to_file(stem)   # {stem}.json + {stem}.html 자동 생성
    print(f"골든 데이터셋 재실행 완료: {len(items)}건 → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output",  required=True)
    args = parser.parse_args()
    run_golden_eval(args.dataset, args.output)
```

> 👨‍💻 **개발자 TIP**: GitHub Actions 워크플로에서 `agent-eval gate` 커맨드가 `exit code 1`을 반환하면 PR이 블로킹됩니다. 처음 CI 통합 시에는 해당 스텝에 `continue-on-error: true`를 추가해 블로킹 없이 결과를 로그로만 출력하고, 팀이 Gate 기준치에 익숙해진 뒤 옵션을 제거해 블로킹 모드로 전환하세요.

> 📋 **QA 관리자 TIP**: 골든 데이터셋 재실행 스크립트는 기능 변경 없는 리팩터링 PR에서 특히 유용합니다. "코드만 정리했는데 Gate A 점수가 0.03 내려갔다"는 발견이 리팩터링 중 의도치 않게 바뀐 로직을 드러냅니다. 모든 PR에서 골든 데이터셋을 돌리도록 CI에 넣으면, 기능 PR과 리팩터링 PR 모두를 동일한 품질 기준으로 검증할 수 있습니다.

---

## 26.3 골든 데이터셋: 자동으로 쌓이는 테스트 케이스

### 골든 데이터셋이란

골든 데이터셋은 **알려진 좋은 입출력 쌍의 모음**이다. "이 질문에 이 답변이 나오면 좋은 것"을 정의한 테스트 케이스다.

수동으로 만들 필요가 없다. 프로덕션에서 실제로 생성된 결과 중 품질 기준을 통과한 것들이 자동으로 골든셋이 된다. 처음에는 케이스가 적지만, 운영할수록 골든셋이 풍부해진다.

### 자동 구축 스크립트

> **💡 `GoldenSetBuilder` 란?**
>
> 평가 결과 파일 디렉토리에서 "알려진 좋은 케이스"를 자동으로 골라 골든 데이터셋을 구축하는 클래스다.
>
> 지원 전략: `high_value`(accuracy ≥ 0.9), `failure_cases`(실패한 케이스), `edge_cases`(극단값), `coverage_gap`(적게 수집된 태스크 유형).

```python
from agent_evaluator import GoldenSetBuilder

builder = GoldenSetBuilder(
    source_dir="results/",        # 결과 JSON 파일이 있는 디렉토리
    output_dir="golden_cases/",   # 골든 데이터셋 저장 위치
)
candidates = builder.extract(
    strategies=["high_value", "failure_cases"],  # 추출 전략
    max_cases=50,
)
builder.save_candidates(candidates, filename="qa_dataset.json")
```

```python
# scripts/build_golden_dataset.py

from pathlib import Path
from agent_evaluator import GoldenSetBuilder


def build_golden_dataset(
    results_dir: str,
    output_path: str,
    min_score: float = 0.80,
    max_size: int = 100,
):
    """
    결과 파일에서 품질 기준을 통과한 케이스를 골든 데이터셋으로 자동 추출한다.

    GoldenSetBuilder는 source_dir의 모든 JSON 결과 파일을 읽어
    strategy별로 케이스를 추출한다. min_score 이상인 케이스만 저장한다.
    """
    output_dir = str(Path(output_path).parent)

    builder = GoldenSetBuilder(
        source_dir=results_dir,   # 평가 결과 JSON 파일 디렉토리
        output_dir=output_dir,    # 골든 데이터셋 저장 위치
    )

    # 고품질·실패·엣지 케이스를 함께 추출 (max_size 2배 풀에서 필터)
    candidates = builder.extract(
        strategies=["high_value", "failure_cases", "edge_cases"],
        max_cases=max_size * 2,
    )

    # accuracy 기준으로 min_score 이상인 케이스만 선택
    filtered = [
        c for c in candidates
        if c.get("accuracy_score", 0) >= min_score
    ][:max_size]

    output_filename = Path(output_path).name
    builder.save_candidates(filtered, filename=output_filename)

    count = len(filtered)
    print(f"골든 데이터셋 갱신 완료: {count}건 → {output_path}")
    return count


if __name__ == "__main__":
    count = build_golden_dataset(
        results_dir="lecture_eval_results/",
        output_path="golden_cases/qa_dataset.json",
        min_score=0.80,
        max_size=100,
    )
    if count < 10:
        print("⚠  골든 케이스가 10건 미만입니다. 더 많은 실행이 필요합니다.")
```

### 골든 데이터셋 성장 전략

처음 1개월은 골든셋이 거의 비어 있다. CI가 "데이터 없음"으로 Gate 판정을 건너뛰는 상황이 발생한다. 이것은 정상이다.

골든셋을 빠르게 채우는 방법은 두 가지다.

**방법 1**: 팀의 실제 사용 케이스를 수동으로 3–5개 추가한다. 완벽한 `ground_truth`가 없어도 된다. 빈 문자열로 두면 TCR만 평가하고 나머지는 나중에 채운다.

**방법 2**: 개발 환경에서 주제 목록으로 배치 실행해 초기 케이스를 만든다.

```python
# scripts/seed_golden_dataset.py — 초기 시드 생성

SEED_TOPICS = [
    ("FastAPI 기초", "intermediate", 60),
    ("LangChain 에이전트", "advanced", 60),
    ("Docker 컨테이너화", "beginner", 45),
    ("Python 비동기 프로그래밍", "intermediate", 60),
    ("RAG 시스템 설계", "advanced", 90),
]

for topic, level, duration in SEED_TOPICS:
    # 실제 강의를 생성하고 골든셋에 추가
    result = run_lecture_pipeline(topic, level, duration)
    if result.quality_score >= 80:
        golden_builder.add(result)
```

> 👨‍💻 **개발자 TIP**: `quality_score >= 80` 기준은 골든 데이터셋의 품질 하한선입니다. 이 기준을 너무 낮게 잡으면(예: `>= 60`) 경계선 케이스가 많이 포함돼 Gate 임계값이 실제보다 낮게 형성됩니다. 초기에는 `>= 85`로 시작해 골든셋이 50건 이상 쌓인 뒤 실제 점수 분포를 보고 기준을 조정하세요.

> 📋 **QA 관리자 TIP**: 골든 데이터셋은 "모범 답안 모음"입니다. 신규 입사자나 외부 개발자가 에이전트의 기대 품질 수준을 파악할 때, 코드 문서보다 골든 데이터셋 예시가 더 직관적입니다. 분기별로 골든셋 샘플 10건을 팀 전체와 공유하는 것을 루틴으로 만들면, Gate 기준치 설정에 대한 팀 공감대가 자연스럽게 형성됩니다.

---

## 26.4 주간 추세 리뷰: 하락을 일찍 발견한다

### 단발성 이상 vs 추세

Gate 판정은 "지금 이 실행이 기준을 통과했는가"를 본다. 이것만으로는 부족하다.

어떤 문제는 단발성이 아니라 추세로 나타난다. 매주 Accuracy가 0.5%씩 하락하는 것, 8주에 걸쳐 평균 비용이 10% 증가하는 것, 서서히 P95 레이턴시가 올라가는 것. 이런 변화는 어느 시점의 단면만 보면 "정상"처럼 보이다가 어느 날 갑자기 임계값을 넘는다.

주간 추세 리뷰는 이런 변화를 조기에 발견하기 위한 루틴이다.

### 주간 추세 분석 스크립트

> **💡 `RunTrendAnalyzer` 란?**
>
> 여러 회의 평가 결과 파일(`.json`)을 시간순으로 읽어 TCR·Accuracy·Latency·Cost의 변화 기울기(slope)를 계산하는 클래스다. CLI에서는 `agent-eval trend results/ --fail-on-regression`으로 동일 기능을 사용할 수 있다.

```python
from agent_evaluator.cli.trend import RunTrendAnalyzer

analyzer = RunTrendAnalyzer(
    results_dir="results/",    # 결과 파일이 있는 디렉토리
    pattern="eval_*.json",     # 파일 패턴
    window=8,                  # 최근 N개 파일만 분석
    slope_threshold=0.3,       # 이 기울기 이상이면 회귀로 간주
)
report = analyzer.analyze()
report.tcr_trend.slope          # TCR 기울기 (음수 = 하락 추세)
report.any_regression           # True/False — CI fail-on-regression 기준
```

```python
# scripts/weekly_review.py

from agent_evaluator.cli.trend import RunTrendAnalyzer
from agent_evaluator import QuickEval
from datetime import datetime
from pathlib import Path


def run_weekly_review(
    results_dir: str = "lecture_eval_results/",
    pattern: str = "lecture_*.json",
    window: int = 8,
) -> dict:
    """
    최근 N주의 결과 파일에서 지표 추세를 분석한다.
    회귀가 감지되면 상세 내용을 출력하고 딕셔너리로 반환한다.
    """
    analyzer = RunTrendAnalyzer(
        results_dir=results_dir,
        pattern=pattern,
        window=window,
        slope_threshold=0.3,
    )
    report = analyzer.analyze()

    print(f"\n{'='*60}")
    print(f"  주간 품질 추세 리뷰 — {datetime.today().strftime('%Y-%m-%d')}")
    print(f"  분석 기간: 최근 {window}주 ({len(report.runs)}개 결과 파일)")
    print(f"{'='*60}")

    trend_items = {
        "TCR":           report.tcr_trend,
        "Accuracy":      report.accuracy_trend,
        "Avg Latency":   report.latency_trend,
        "Cost":          report.cost_trend,
        "Hallucination": report.hallucination_trend,
    }

    regressions = []
    for name, trend in trend_items.items():
        if trend is None:
            continue
        direction  = "↑" if trend.slope > 0 else "↓" if trend.slope < 0 else "→"
        status_str = "REGRESS ⚠️ " if trend.any_regression else "stable  ✅"
        print(f"  {name:<16} slope={trend.slope:+.3f}/run  {direction}  {status_str}")
        if trend.any_regression:
            regressions.append(name)

    print(f"\n  전체 회귀 감지: {'있음 ⚠️' if report.any_regression else '없음 ✅'}")

    if regressions:
        print(f"\n  ⚠  회귀 지표: {', '.join(regressions)}")
        print(f"  → 권고: 해당 지표의 최근 커밋 이력 확인")
        print(f"  → CI/CD: agent-eval trend results/ --fail-on-regression")

    # 전주 대비 비교
    eval_last = QuickEval(results_dir)
    eval_this = QuickEval(results_dir)

    result_files = sorted(Path(results_dir).glob(pattern))
    if len(result_files) >= 2:
        eval_last.replay(str(result_files[-2]))
        eval_this.replay(str(result_files[-1]))
        comparison = eval_this.compare(eval_last)
        delta = comparison.get("delta", {})
        # compare()의 delta에는 tcr·accuracy·avg_latency가 포함된다.
        # total_cost_usd는 delta에 없으므로 summary()에서 직접 계산한다.
        cost_delta = (
            comparison.get("self", {}).get("total_cost_usd", 0.0)
            - comparison.get("other", {}).get("total_cost_usd", 0.0)
        )

        print(f"\n  [ 전주 대비 변화 ]")
        print(f"    Accuracy:    {delta.get('accuracy', 0):+.1f}pp")
        print(f"    TCR:         {delta.get('tcr', 0):+.1f}pp")
        print(f"    Avg Latency: {delta.get('avg_latency', 0):+.2f}초")
        print(f"    비용:        {cost_delta:+.4f}$")

    print(f"{'='*60}\n")
    return {"regressions": regressions, "report": report}


if __name__ == "__main__":
    run_weekly_review()
```

### cron 설정

```bash
# crontab -e 에 추가

# 매주 월요일 09:00 — 주간 추세 리뷰
0 9 * * 1 cd /path/to/lecture-forge && \
    python scripts/weekly_review.py >> logs/weekly_review.log 2>&1

# 매주 월요일 09:10 — 골든 데이터셋 갱신
10 9 * * 1 cd /path/to/lecture-forge && \
    python scripts/build_golden_dataset.py >> logs/golden_build.log 2>&1

# 매월 1일 09:00 — 8주 추세 분석 및 CI 회귀 차단
0 9 1 * * cd /path/to/lecture-forge && \
    agent-eval trend lecture_eval_results/ \
      --window 8 \
      --fail-on-regression \
      --output-json reports/monthly_trend_$(date +%Y%m).json
```

---

## 26.5 Lecture_forge 실제 사례: Gate D 비용 추세 발견

주간 리뷰를 8주 운영한 후 다음 리포트가 생성됐다.

```
  비용 추세 분석 (8주)

  TCR          slope=+0.012/run  ↑  stable  ✅
  Accuracy     slope=+0.008/run  ↑  stable  ✅
  Avg Latency  slope=+0.042/run  ↑  stable  ✅
  Cost         slope=+0.004/run  ↑  REGRESS ⚠️  ← 비용 추세 회귀
  Hallucination slope=+0.001/run →  stable  ✅

  전체 회귀 감지: 있음 ⚠️

  ⚠  회귀 지표: Cost
  → 권고: 해당 지표의 최근 커밋 이력 확인
```

비용이 8주에 걸쳐 실행당 평균 0.4%씩 증가하고 있었다. 단발성 이상이 아니라 구조적 증가다.

Git log를 확인하니 6주 전 커밋에서 RAG 컨텍스트 크기(`RAG_MAX_CONTEXT_TOKENS`)를 6,000에서 8,000으로 늘린 것이 발견됐다. RAG 품질이 좋아지는 대신, ContentWriter 프롬프트가 길어지면서 completion token 수가 증가하고 있었다.

```python
# config.py — 6주 전 변경사항
RAG_MAX_CONTEXT_TOKENS = 8000  # 기존 6000 → 품질 개선 목적으로 증가

# 영향: 섹션당 평균 비용 $0.035 → $0.038 (+8.6%)
# 8주 누적으로 Gate D 추세 회귀 감지됨
```

추세 리뷰가 없었다면 이 변화를 알아채지 못했을 것이다. 각 실행의 비용은 여전히 Gate D 상한($0.10)보다 낮아서 단발성 판정에서는 PASS가 나왔다. 하지만 추세로 보면 $0.035 목표에서 멀어지고 있었다.

---

## 26.6 파트 VI 재현 가능한 이식 체크리스트

파트 VI 전체를 관통하는 방법론을 마지막으로 체크리스트로 정리한다. 이 목록은 어떤 프로젝트에도 그대로 적용할 수 있다.

@@HTML_START@@
<style>
.checklist-container{margin:20px 0;}
.checklist-phase{margin-bottom:20px;}
.phase-header{padding:10px 16px;border-radius:10px 10px 0 0;font-weight:700;font-size:14px;display:flex;align-items:center;gap:8px;}
.phase-body{border-radius:0 0 10px 10px;padding:12px 16px;}
.check-item{display:flex;align-items:flex-start;gap:10px;padding:6px 0;border-bottom:1px solid rgba(0,0,0,0.05);font-size:13px;line-height:1.5;}
.check-item:last-child{border-bottom:none;}
.check-box{width:18px;height:18px;border:2px solid #bdbdbd;border-radius:4px;flex-shrink:0;margin-top:2px;}
.check-ref{font-size:11px;opacity:.7;margin-left:auto;white-space:nowrap;padding-left:8px;}
</style>

<div class="checklist-container">

  <div class="checklist-phase">
    <div class="phase-header" style="background:#1565c0;color:#fff;">
      📐 분석 단계 (Ch22) — 1–2시간
    </div>
    <div class="phase-body" style="background:#e3f2fd;border:1px solid #90caf9;">
      <div class="check-item"><div class="check-box"></div><div>에이전트 실행 순서를 그림(또는 텍스트)으로 표현했다</div><span class="check-ref">§22.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>파이프라인 패턴을 식별했다 (순차 / 루프 포함 / 병렬+집계)</div><span class="check-ref">§22.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>LLM 호출 지점 전체를 목록으로 만들었다</div><span class="check-ref">§22.4</span></div>
      <div class="check-item"><div class="check-box"></div><div>성공 기준이 없는 호출 지점(= 1순위 후보)을 식별했다</div><span class="check-ref">§22.4</span></div>
      <div class="check-item"><div class="check-box"></div><div>이미 측정되는 지표와 측정 안 되는 공백을 목록으로 만들었다</div><span class="check-ref">§22.5</span></div>
      <div class="check-item"><div class="check-box"></div><div>외부 입력 경로, 루프, 비용 폭발 가능 지점을 우선순위화했다</div><span class="check-ref">§22.6</span></div>
    </div>
  </div>

  <div class="checklist-phase">
    <div class="phase-header" style="background:#2e7d32;color:#fff;">
      🗺 매핑 단계 (Ch23) — 1–3시간
    </div>
    <div class="phase-body" style="background:#e8f5e9;border:1px solid #a5d6a7;">
      <div class="check-item"><div class="check-box"></div><div>"이 시스템이 망했다는 것을 어떻게 아는가" 실패 모드를 나열했다</div><span class="check-ref">§23.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>"잘못된 방향" 실패 모드를 나열했다</div><span class="check-ref">§23.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>"겉으로는 돌아가는" 숨겨진 실패 모드를 나열했다</div><span class="check-ref">§23.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>각 실패 모드를 Gate Config로 번역했다 (범용 템플릿 활용)</div><span class="check-ref">§23.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>코드의 기존 상수(max_retry 등)를 Config 파라미터와 1:1 연결했다</div><span class="check-ref">§23.4</span></div>
      <div class="check-item"><div class="check-box"></div><div>Gate 가중치를 비즈니스 영향도 기준으로 설정했다</div><span class="check-ref">§23.5</span></div>
    </div>
  </div>

  <div class="checklist-phase">
    <div class="phase-header" style="background:#e65100;color:#fff;">
      🔌 1단계 이식 (Ch24) — 30분
    </div>
    <div class="phase-body" style="background:#fff3e0;border:1px solid #ffcc80;">
      <div class="check-item"><div class="check-box"></div><div>첫 측정점 1–2개를 선택했다 (명확한 입출력 + 기존 성공 기준 + 독립 호출)</div><span class="check-ref">§24.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>레벨 0 또는 레벨 1 방식으로 이식했다 (기존 반환값 변경 없음)</div><span class="check-ref">§24.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>eval_results/ 디렉토리에 JSON 파일이 생성됐다</div><span class="check-ref">§24.7</span></div>
      <div class="check-item"><div class="check-box"></div><div>dashboard에서 TCR, Accuracy, P95가 보인다</div><span class="check-ref">§24.7</span></div>
      <div class="check-item"><div class="check-box"></div><div>기존 테스트가 모두 통과한다 (이식이 기존 동작을 깨지 않았음 확인)</div><span class="check-ref">§24.10</span></div>
    </div>
  </div>

  <div class="checklist-phase">
    <div class="phase-header" style="background:#6a1b9a;color:#fff;">
      🏗 2단계 이식 (Ch25) — 1–3일
    </div>
    <div class="phase-body" style="background:#f3e5f5;border:1px solid #ce93d8;">
      <div class="check-item"><div class="check-box"></div><div>중앙 모니터 빌더 함수를 별도 파일에 작성했다</div><span class="check-ref">§25.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>기존 추적기(비용, 품질 점수) → TaskResult 어댑터를 작성했다</div><span class="check-ref">§25.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>외부 입력 경로에 InputSanitizationTracker를 삽입했다</div><span class="check-ref">§25.5</span></div>
      <div class="check-item"><div class="check-box"></div><div>파이프라인 진입점에서 monitor를 주입해 모든 에이전트가 공유한다</div><span class="check-ref">§25.5</span></div>
      <div class="check-item"><div class="check-box"></div><div>Gate 리포트를 생성하고 WARN/FAIL 항목을 확인했다</div><span class="check-ref">§25.6</span></div>
      <div class="check-item"><div class="check-box"></div><div>Gate가 발견한 버그를 수정하고 Gate 점수가 올라갔음을 확인했다</div><span class="check-ref">§25.7</span></div>
    </div>
  </div>

  <div class="checklist-phase">
    <div class="phase-header" style="background:#37474f;color:#fff;">
      🚀 완성 단계 (Ch26) — 1일
    </div>
    <div class="phase-body" style="background:#eceff1;border:1px solid #b0bec5;">
      <div class="check-item"><div class="check-box"></div><div>CI/CD에 Gate 판정 스텝을 추가했다 (PR마다 자동 실행)</div><span class="check-ref">§26.2</span></div>
      <div class="check-item"><div class="check-box"></div><div>골든 데이터셋 자동 구축 스크립트를 설정했다</div><span class="check-ref">§26.3</span></div>
      <div class="check-item"><div class="check-box"></div><div>주간 추세 리뷰 cron을 설정했다 (매주 월요일)</div><span class="check-ref">§26.4</span></div>
      <div class="check-item"><div class="check-box"></div><div>첫 주간 리뷰 리포트를 생성하고 추세 데이터를 확인했다</div><span class="check-ref">§26.4</span></div>
    </div>
  </div>

</div>
@@HTML_END@@

---

## 26.7 도입 로드맵: 팀 규모에 따른 현실적인 일정

단계별 작업의 실제 소요 시간은 팀 규모와 프로젝트 복잡도에 따라 다르다.

@@HTML_START@@
<style>
.roadmap-table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;}
.roadmap-table th{background:#37474f;color:#fff;padding:10px 14px;}
.roadmap-table td{padding:9px 14px;border-bottom:1px solid #eceff1;vertical-align:top;}
.timeline-badge{display:inline-block;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:700;}
</style>

<table class="roadmap-table">
<thead>
<tr>
  <th>단계</th>
  <th>1인 개발자</th>
  <th>5인 팀</th>
  <th>20인+ 팀</th>
</tr>
</thead>
<tbody>
<tr>
  <td><strong>분석 (Ch22)</strong></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">1–2시간</span><br>본인이 코드를 잘 알기 때문에 빠름</td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">반나절</span><br>팀원 인터뷰 포함</td>
  <td><span class="timeline-badge" style="background:#ffcdd2;color:#c62828;">1–2일</span><br>담당자 파악 + 미팅</td>
</tr>
<tr>
  <td><strong>매핑 (Ch23)</strong></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">1–3시간</span></td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">반나절</span><br>팀 리뷰 포함</td>
  <td><span class="timeline-badge" style="background:#ffcdd2;color:#c62828;">2–3일</span><br>Gate 가중치 합의 필요</td>
</tr>
<tr>
  <td><strong>1단계 이식 (Ch24)</strong></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">30분</span></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">1–2시간</span></td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">반나절</span><br>코드 리뷰 포함</td>
</tr>
<tr>
  <td><strong>2단계 이식 (Ch25)</strong></td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">1–2일</span></td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">2–3일</span></td>
  <td><span class="timeline-badge" style="background:#ffcdd2;color:#c62828;">1주</span><br>여러 서비스에 배포</td>
</tr>
<tr>
  <td><strong>CI/CD 완성 (Ch26)</strong></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">반나절</span></td>
  <td><span class="timeline-badge" style="background:#c8e6c9;color:#1b5e20;">1일</span></td>
  <td><span class="timeline-badge" style="background:#fff9c4;color:#f57f17;">2–3일</span><br>DevOps 협력 필요</td>
</tr>
<tr style="background:#f5f5f5;">
  <td><strong>총 소요</strong></td>
  <td><strong>2–4일</strong></td>
  <td><strong>1주</strong></td>
  <td><strong>2–3주</strong></td>
</tr>
</tbody>
</table>
@@HTML_END@@

---

## 26.8 파트 VI를 마치며: 이 방법론이 의미하는 것

Part I–V에서 agent-evaluator를 처음부터 설계에 포함한 시스템을 만드는 방법을 다뤘다. 새 프로젝트를 올바르게 시작하는 방법이었다.

Part VI는 다른 상황을 위한 것이었다. 이미 6개월을 개발한 프로젝트, 이미 프로덕션에서 돌아가는 시스템, "잘 돌아가고 있는데 얼마나 잘 돌아가는지 모르는" 상태.

이 파트에서 배운 방법론의 핵심은 하나다.

> **기존 프로젝트를 깨지 않으면서, 단계적으로, 측정 가능한 상태로 만들 수 있다.**

분석 4단계로 프로젝트를 해부하고, 실패 모드에서 출발해 Gate를 역매핑하고, 레벨 0 침습으로 첫 숫자를 얻고, 중앙 모니터로 전체를 연결하고, CI/CD와 주간 루틴으로 자동화한다.

Lecture_forge를 통해 이 과정을 실증했다. Gate F가 `audience_level` 전파 버그를 찾아냈고, 8주 추세 리뷰가 비용 증가 패턴을 발견했다. 이 두 가지 발견은 단발성 테스트로는 절대 포착되지 않았을 것이다.

Gate 리포트가 "어딘가 이상한 것 같은데"를 "Gate F PropagationConfig: curriculum_designer → content_writer 구간, audience_level None"으로 바꾸는 것이 이 방법론의 실질적 가치다. 진단의 수준이 달라지면, 수정의 속도가 달라진다.

---

> **Part VI에서 배운 것**
>
> 기존 프로젝트에 agent-evaluator를 이식하는 작업은 새 프로젝트와 다르다. 코드를 건드리지 않는 것, 단계적으로 진행하는 것, 기존 지표를 재활용하는 것이 핵심이다.
>
> 분석 → 매핑 → 1단계 이식 → 2단계 이식 → 완성. 이 다섯 단계는 어떤 프로젝트에도 적용된다. Lecture_forge는 그 방법론을 실증한 재료였다.
>
> 이 파트를 끝낸 독자는 자신의 프로젝트를 들고 Ch22의 체크리스트부터 시작하면 된다.

```
# 출처: Evaluator_Examples/ch26_cicd_weekly.py
```
