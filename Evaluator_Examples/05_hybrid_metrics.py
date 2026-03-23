"""
하이브리드 지표 예제 — DeepEval + Ragas 실제 API 동작
=====================================================

커버 지표 (Layer 3):
  DeepEval  │ G-Eval               (커스텀 기준 품질 평가 — GPT 기반)
            │ Hallucination        (문맥 기반 환각 탐지 — GPT 기반, RAG 태스크)
            │ Toxicity             (독성 콘텐츠 탐지 — GPT 기반)
            │ Bias                 (편향 탐지 — GPT 기반)
            │ Answer Relevancy     (질문-답변 관련성 — GPT 기반, QA 태스크)
  Ragas     │ Faithfulness         (컨텍스트 충실도 — 실제 Ragas, RAG 태스크)
            │ Answer Relevancy     (답변 관련성 — 실제 Ragas, RAG 태스크)
            │ Context Precision    (컨텍스트 정밀도 — 실제 Ragas, RAG 태스크)
            │ Context Recall       (컨텍스트 재현율 — 실제 Ragas, RAG 태스크)

사전 요구사항:
    pip install agent-evaluator[eval]
    pip install langchain-openai datasets

실행:
    cd Evaluator_Examples
    python 05_hybrid_metrics.py

주의: 이 예제는 OpenAI API를 호출합니다. Evaluator_Examples/.env 에
      OPENAI_API_KEY 가 설정되어 있어야 합니다.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 자동 감지
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ─────────────────────────────────────────────────────────────────────────────
# .env 로드 (Evaluator_Examples/.env)
# ─────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ .env 로드: {env_path}")
else:
    print("⚠️  .env 파일 없음 — OPENAI_API_KEY 환경변수를 직접 설정하세요")

if not os.getenv("OPENAI_API_KEY"):
    print("❌ OPENAI_API_KEY 가 설정되지 않았습니다.")
    print("   Evaluator_Examples/.env 파일에 OPENAI_API_KEY 를 설정한 후 재실행하세요.")
    sys.exit(1)

# LangSmith 트레이싱 비활성화 — .env 의 LANGCHAIN_TRACING_V2=true 덮어쓰기
# Ragas 가 LangChain 내부적으로 LangSmith 에 연결 시도하므로 명시적으로 끔
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

# 패키지 가용성 확인
_missing = []
try:
    import deepeval  # noqa: F401
except ImportError:
    _missing.append("deepeval")
try:
    import ragas  # noqa: F401
except ImportError:
    _missing.append("ragas")
try:
    import langchain_openai  # noqa: F401
except ImportError:
    _missing.append("langchain-openai")
try:
    import datasets  # noqa: F401
except ImportError:
    _missing.append("datasets")

if _missing:
    print(f"❌ 필수 패키지 미설치: {', '.join(_missing)}")
    print("   다음 명령으로 설치하세요:")
    print("   pip install agent-evaluator[eval] langchain-openai datasets")
    sys.exit(1)

from agent_evaluator import TaskResult
from agent_evaluator import HybridPerformanceMonitor
from agent_evaluator.reporting import generate_comprehensive_html_report

# ─────────────────────────────────────────────────────────────────────────────
# 테스트 데이터셋
# ─────────────────────────────────────────────────────────────────────────────
# 주의: 각 태스크는 여러 GPT API 호출을 발생시킵니다.
# 비용 절감을 위해 케이스를 소규모로 유지합니다 (6 tasks 총).

# [A] DeepEval 단독 케이스 — 컨텍스트 없음 (G-Eval, Toxicity, Bias, Answer Relevancy)
DEEPEVAL_ONLY_CASES = [
    {
        "task_id": "de_qa_001",
        "question": "대한민국의 수도는 어디인가요?",
        "answer": "대한민국의 수도는 서울입니다. 서울은 약 천만 명이 거주하는 대도시로 경제·문화·정치의 중심지입니다.",
        "expected": "서울",
        "task_type": "qa",
        "quality_criteria": (
            "답변이 질문에 직접적으로 답하고, 정확한 정보를 포함하며, "
            "간결하고 명확한지 1~10 척도로 평가하세요."
        ),
        "success": True,
        "accuracy_score": 0.95,
    },
    {
        "task_id": "de_qa_002",
        "question": "Python 리스트와 튜플의 주요 차이점은 무엇인가요?",
        "answer": (
            "리스트는 변경 가능(mutable)하고 [] 로 선언합니다. "
            "튜플은 변경 불가능(immutable)하며 () 로 선언합니다. "
            "메모리 효율은 튜플이 더 좋습니다."
        ),
        "expected": "리스트는 mutable, 튜플은 immutable",
        "task_type": "qa",
        "quality_criteria": (
            "기술적 정확성, 핵심 차이점 포함 여부, 예시 포함 여부를 평가하세요."
        ),
        "success": True,
        "accuracy_score": 0.90,
    },
    {
        "task_id": "de_reasoning_003",
        "question": "AI 기술이 사회에 미치는 영향을 설명하세요.",
        "answer": (
            "AI는 의료 진단 정확도 향상, 교육 개인화, 업무 자동화 등 긍정적 영향을 줍니다. "
            "반면 일자리 대체, 알고리즘 편향, 프라이버시 침해 위험도 존재합니다. "
            "균형 잡힌 규제와 윤리 가이드라인이 필요합니다."
        ),
        "expected": "긍정적 영향과 위험 요소 균형 있는 분석",
        "task_type": "reasoning",
        "quality_criteria": (
            "균형 잡힌 시각을 제시하는지, 구체적인 사례를 포함하는지, "
            "특정 집단에 대한 편향이 없는지 평가하세요."
        ),
        "success": True,
        "accuracy_score": 0.85,
    },
]

# [B] DeepEval + Ragas 통합 케이스 — 컨텍스트 있음 (RAG 태스크)
RAG_CASES = [
    {
        "task_id": "rag_001_good",
        "question": "Agent Evaluator SDK의 세 가지 평가 레이어는 무엇인가요?",
        "answer": (
            "Agent Evaluator SDK는 세 개의 평가 레이어로 구성됩니다. "
            "Layer 1(Foundation)은 태스크 완료율·정확도·할루시네이션·응답 품질·지연 시간·토큰 비용을 외부 의존성 없이 측정합니다. "
            "Layer 2(Agentic)는 도구 호출 패턴, 재시도, 멀티에이전트 협조, 워크플로우, 보안을 측정합니다. "
            "Layer 3(Hybrid)는 DeepEval·Ragas·LangSmith 등 외부 라이브러리와 통합합니다."
        ),
        "expected": "Layer 1(Foundation), Layer 2(Agentic), Layer 3(Hybrid)의 세 레이어",
        "contexts": [
            "Agent Evaluator SDK는 25개의 성능 지표를 세 개의 레이어로 측정합니다.",
            "Layer 1(Foundation Metrics)은 외부 의존성 없이 알고리즘 기반으로 태스크 완료율, 정확도, 할루시네이션, 응답 품질, 지연 시간, 토큰 비용을 측정합니다.",
            "Layer 2(Agentic Metrics)는 도구 호출 분석, 재시도 추적, 도구 선택 정확도, 멀티에이전트 협조, 워크플로우 실행, 보안 메트릭을 포함합니다.",
            "Layer 3(Hybrid Evaluation)는 HybridPerformanceMonitor를 통해 DeepEval, Ragas, LangSmith 등 외부 라이브러리와 통합하여 GPT 기반 평가를 제공합니다.",
        ],
        "task_type": "qa",
        "quality_criteria": (
            "제공된 컨텍스트에 근거하여 세 레이어를 정확하게 설명했는지, "
            "각 레이어의 특징을 올바르게 구분했는지 평가하세요."
        ),
        "success": True,
        "accuracy_score": 0.93,
        "is_hallucination_test": False,
    },
    {
        "task_id": "rag_002_good",
        "question": "Python GIL이 멀티스레딩에 미치는 영향은?",
        "answer": (
            "GIL(Global Interpreter Lock)은 CPython에서 한 번에 하나의 스레드만 "
            "Python 바이트코드를 실행하도록 합니다. "
            "CPU 바운드 작업에서는 멀티스레딩의 병렬 효과가 제한됩니다. "
            "I/O 바운드 작업에서는 GIL이 일시 해제되어 스레드 전환이 가능합니다. "
            "CPU 병렬 처리가 필요하면 multiprocessing 모듈을 사용하세요."
        ),
        "expected": "GIL은 한 번에 하나의 스레드만 실행, CPU 바운드 작업에서 병렬 제한, I/O 바운드에서는 유효",
        "contexts": [
            "GIL(Global Interpreter Lock)은 CPython 인터프리터에서 여러 스레드가 동시에 Python 객체에 접근하지 못하도록 하는 뮤텍스입니다.",
            "CPU 바운드 작업에서 멀티스레딩을 사용해도 GIL 때문에 실제 병렬 실행이 제한됩니다.",
            "I/O 바운드 작업(파일 읽기, 네트워크 요청 등)에서는 GIL이 해제되어 스레드 간 전환이 발생합니다.",
            "CPU 병렬 처리가 필요한 경우 multiprocessing 모듈을 사용하는 것이 권장됩니다.",
        ],
        "task_type": "qa",
        "quality_criteria": (
            "GIL의 정의와 CPU/I/O 바운드 작업에 대한 영향 차이를 정확하게 설명했는지 평가하세요."
        ),
        "success": True,
        "accuracy_score": 0.91,
        "is_hallucination_test": False,
    },
    {
        "task_id": "rag_003_hallucination",
        "question": "Docker 컨테이너와 가상머신(VM)의 차이점은?",
        # 의도적으로 사실과 다른 답변 — 환각 탐지 검증용
        "answer": (
            "Docker 컨테이너와 가상머신은 동일한 기술입니다. "
            "둘 다 하드웨어를 완전히 에뮬레이션하며 성능 차이가 없습니다. "
            "Docker는 2005년 Microsoft가 개발했으며 Windows 전용입니다."
        ),
        "expected": "컨테이너는 OS 커널 공유, VM은 전체 OS 포함 — 컨테이너가 더 경량",
        "contexts": [
            "Docker 컨테이너는 호스트 OS의 커널을 공유하며 가볍고 시작이 빠릅니다.",
            "가상머신(VM)은 전체 운영체제를 포함하여 더 많은 리소스를 사용합니다.",
            "Docker는 2013년 dotCloud(현 Docker Inc.)가 오픈소스로 공개한 컨테이너 플랫폼입니다.",
            "컨테이너는 격리 수준이 VM보다 낮지만 오버헤드가 적어 배포 속도가 빠릅니다.",
        ],
        "task_type": "qa",
        "quality_criteria": (
            "컨텍스트에 기반하여 정확한 차이점을 설명했는지 평가하세요. "
            "잘못된 날짜(2005년, Microsoft 등)나 사실에 주의하세요."
        ),
        "success": False,  # 의도적 오류
        "accuracy_score": 0.15,
        "is_hallucination_test": True,
    },
]


def load_hybrid_golden_dataset() -> tuple:
    """
    results/golden_datasets/hybrid_rag_evaluation.json 에서
    DEEPEVAL_ONLY_CASES 와 RAG_CASES 를 동적으로 로드합니다.

    JSON 파일이 없으면 모듈 상단의 인라인 데이터로 폴백합니다.

    Returns:
        (deepeval_cases, rag_cases) 튜플
    """
    import json

    golden_path = project_root / "results" / "golden_datasets" / "hybrid_rag_evaluation.json"
    if not golden_path.exists():
        return DEEPEVAL_ONLY_CASES, RAG_CASES

    try:
        with open(golden_path, encoding="utf-8") as f:
            items = json.load(f)

        deepeval_cases = []
        rag_cases = []
        for item in items:
            if item.get("layer") == "deepeval_only":
                deepeval_cases.append({
                    "task_id":         item["qa_id"],
                    "question":        item["question"],
                    "answer":          item.get("answer", ""),   # 파일에 없으면 빈 문자열 — 실제 에이전트 응답으로 교체
                    "expected":        item["ground_truth"],
                    "task_type":       item.get("task_type", "qa"),
                    "quality_criteria": item.get("quality_criteria", ""),
                    "success":         not item.get("is_hallucination_test", False),
                    "accuracy_score":  item.get("expected_accuracy", 0.85),
                })
            elif item.get("layer") == "deepeval_ragas":
                rag_cases.append({
                    "task_id":              item["qa_id"],
                    "question":             item["question"],
                    "answer":               item.get("answer", ""),
                    "expected":             item["ground_truth"],
                    "contexts":             item.get("contexts", []),
                    "task_type":            item.get("task_type", "qa"),
                    "quality_criteria":     item.get("quality_criteria", ""),
                    "success":              not item.get("is_hallucination_test", False),
                    "accuracy_score":       item.get("expected_accuracy", 0.85),
                    "is_hallucination_test": item.get("is_hallucination_test", False),
                })

        # 파일에 answer 필드가 없으면 인라인 케이스로 보완
        if not deepeval_cases:
            deepeval_cases = DEEPEVAL_ONLY_CASES
        if not rag_cases:
            rag_cases = RAG_CASES

        # answer 필드 보완: 인라인 데이터에서 매칭
        _inline_de = {c["task_id"]: c for c in DEEPEVAL_ONLY_CASES}
        _inline_rag = {c["task_id"]: c for c in RAG_CASES}
        for c in deepeval_cases:
            if not c.get("answer") and c["task_id"] in _inline_de:
                c["answer"] = _inline_de[c["task_id"]]["answer"]
        for c in rag_cases:
            if not c.get("answer") and c["task_id"] in _inline_rag:
                c["answer"] = _inline_rag[c["task_id"]]["answer"]

        print(f"✅ Golden Dataset 로드: deepeval={len(deepeval_cases)}건, rag={len(rag_cases)}건")
        print(f"   경로: {golden_path}")
        return deepeval_cases, rag_cases

    except Exception as e:
        print(f"⚠️  Golden Dataset 로드 실패 ({e}) — 인라인 데이터 사용")
        return DEEPEVAL_ONLY_CASES, RAG_CASES


def _print_metric_row(label: str, values: list, width: int = 24) -> None:
    if values:
        avg = sum(values) / len(values)
        print(f"    {label:<{width}}: {avg:.3f}  (n={len(values)})")
    else:
        print(f"    {label:<{width}}: —  (해당 태스크 없음)")


def run_hybrid_evaluation():
    print("\n" + "=" * 70)
    print("  하이브리드 지표 평가 — DeepEval + Ragas (실제 API 호출)")
    print("  Coverage: G-Eval · Hallucination · Toxicity · Bias · Answer Relevancy")
    print("            Faithfulness · Context Precision · Context Recall")
    print("=" * 70)
    print("\n⚠️  이 예제는 OpenAI API 를 호출합니다 (모델: gpt-4o-mini).")
    print("   6개 태스크 기준 예상 비용: $0.01~0.05 수준\n")

    # Golden Dataset 파일 로드 (없으면 인라인 케이스 폴백)
    deepeval_cases, rag_cases = load_hybrid_golden_dataset()

    monitor = HybridPerformanceMonitor(
        use_deepeval=True,
        use_ragas=True,
        use_langsmith=False,
        deepeval_model="gpt-4o-mini",
        ragas_model="gpt-4o-mini",
        enable_hallucination_detection=True,
        enable_transparency=True,
        output_dir=str(project_root / "results"),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # [Part 1] DeepEval 단독 케이스
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print(f"  [Part 1] DeepEval 단독 ({len(deepeval_cases)}건)")
    print("           적용 지표: G-Eval · Toxicity · Bias · Answer Relevancy (QA)")
    print("─" * 70)

    for i, case in enumerate(deepeval_cases, 1):
        print(f"\n  [{i}/{len(deepeval_cases)}] {case['task_id']}  {case['question'][:45]}...")

        _q_len = len(case["question"])
        _a_len = len(case["answer"])
        _exec_time = round(0.4 + _q_len / 600 + _a_len / 900, 2)
        _tokens = {
            "input":  max(50, _q_len // 4),
            "output": max(40, _a_len // 4),
            "total":  max(50, _q_len // 4) + max(40, _a_len // 4),
        }

        task = TaskResult(
            task_id=case["task_id"],
            task_type=case["task_type"],
            success=case["success"],
            completion_score=case["accuracy_score"],
            accuracy_score=case["accuracy_score"],
            execution_time=_exec_time,
            tokens_used=_tokens,
            tool_calls=[],
            attempts=1,
            errors=[],
            timestamp=datetime.now(),
            framework="langchain",
        )

        monitor.record_task(
            task,
            input_text=case["question"],
            output_text=case["answer"],
            expected_output=case["expected"],
            retrieved_context=None,
            quality_criteria=case["quality_criteria"],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # [Part 2] DeepEval + Ragas 통합 (RAG)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print(f"  [Part 2] DeepEval + Ragas 통합 ({len(rag_cases)}건, RAG 컨텍스트 포함)")
    print("           적용 지표: 위 5개 + Faithfulness · Context Precision · Context Recall")
    print("─" * 70)

    for i, case in enumerate(rag_cases, 1):
        label = "⚠️  환각 유발 케이스" if case["is_hallucination_test"] else "✅ 정상 케이스"
        print(f"\n  [{i}/{len(rag_cases)}] {case['task_id']}  {label}")
        print(f"       질문: {case['question'][:50]}...")

        _q_len   = len(case["question"])
        _a_len   = len(case["answer"])
        _ctx_len = sum(len(c) for c in case.get("contexts", []))
        _exec_time = round(0.6 + (_q_len + _ctx_len) / 900 + _a_len / 700, 2)
        _tokens = {
            "input":  max(100, (_q_len + _ctx_len) // 4),
            "output": max(80,  _a_len // 4),
            "total":  max(100, (_q_len + _ctx_len) // 4) + max(80, _a_len // 4),
        }

        task = TaskResult(
            task_id=case["task_id"],
            task_type=case["task_type"],
            success=case["success"],
            completion_score=case["accuracy_score"],
            accuracy_score=case["accuracy_score"],
            execution_time=_exec_time,
            tokens_used=_tokens,
            tool_calls=[],
            attempts=1,
            errors=["hallucination_detected"] if case["is_hallucination_test"] else [],
            timestamp=datetime.now(),
            framework="langchain",
        )

        monitor.record_task(
            task,
            input_text=case["question"],
            output_text=case["answer"],
            expected_output=case["expected"],
            retrieved_context=case["contexts"],
            quality_criteria=case["quality_criteria"],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 결과 저장
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  리포트 저장 중...")
    filename = f"[H]_hybrid_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    monitor.save_to_file(filename)
    saved_path = project_root / "results" / filename
    html_path = saved_path.with_suffix('.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"📄 HTML 리포트 저장: {html_path}")

    # ─────────────────────────────────────────────────────────────────────────
    # 결과 출력
    # ─────────────────────────────────────────────────────────────────────────
    # 태스크별 고급 메트릭 수집
    metrics_by_key: dict = {}
    for ext_task in monitor.extended_tasks:
        for k, v in ext_task.advanced_metrics.items():
            if (
                isinstance(v, float)
                and not k.endswith("_passed")
                and not k.endswith("_detected")
                and not k.endswith("_error")
            ):
                metrics_by_key.setdefault(k, []).append(v)

    print(f"\n{'─'*70}")
    print(f"  저장 위치: {saved_path}")
    print(f"  총 평가 태스크: {len(monitor.extended_tasks)}건")

    print(f"\n  [DeepEval 메트릭 — 전체 평균]")
    _print_metric_row("G-Eval Score",        metrics_by_key.get("g_eval_score", []))
    _print_metric_row("Answer Relevancy",    metrics_by_key.get("answer_relevancy_score", []))
    _print_metric_row("Hallucination Score", metrics_by_key.get("hallucination_score", []))
    _print_metric_row("Toxicity Score",      metrics_by_key.get("toxicity_score", []))
    _print_metric_row("Bias Score",          metrics_by_key.get("bias_score", []))

    print(f"\n  [Ragas 메트릭 — RAG 태스크 평균 (n={len(RAG_CASES)})]")
    _print_metric_row("Faithfulness",        metrics_by_key.get("ragas_faithfulness", []))
    _print_metric_row("Answer Relevancy",    metrics_by_key.get("ragas_answer_relevancy", []))
    _print_metric_row("Context Precision",   metrics_by_key.get("ragas_context_precision", []))
    _print_metric_row("Context Recall",      metrics_by_key.get("ragas_context_recall", []))

    # G-Eval 이유 첫 번째 태스크 출력
    first_reason = None
    for ext_task in monitor.extended_tasks:
        reason = ext_task.advanced_metrics.get("g_eval_reason")
        if reason:
            first_reason = reason
            break
    if first_reason:
        print(f"\n  [G-Eval 평가 이유 — 첫 번째 태스크]")
        print(f"    {first_reason[:250]}")

    # 환각 유발 케이스 집중 분석
    print(f"\n  [환각 유발 케이스 분석 — rag_003_hallucination]")
    for ext_task in monitor.extended_tasks:
        if ext_task.task_id == "rag_003_hallucination":
            h_score   = ext_task.advanced_metrics.get("hallucination_score", "N/A")
            h_detect  = ext_task.advanced_metrics.get("hallucination_detected", "N/A")
            r_faith   = ext_task.advanced_metrics.get("ragas_faithfulness", "N/A")
            r_overall = ext_task.advanced_metrics.get("ragas_overall_score", "N/A")
            g_score   = ext_task.advanced_metrics.get("g_eval_score", "N/A")

            def _fmt(v):
                return f"{v:.3f}" if isinstance(v, float) else str(v)

            print(f"    hallucination_score   : {_fmt(h_score)}  (1.0=정상, 0.0=환각)")
            print(f"    hallucination_detected: {h_detect}")
            print(f"    ragas_faithfulness    : {_fmt(r_faith)}  (낮을수록 컨텍스트 불일치)")
            print(f"    ragas_overall_score   : {_fmt(r_overall)}")
            print(f"    g_eval_score          : {_fmt(g_score)}")
            break

    print(f"{'─'*70}\n")
    return saved_path


if __name__ == "__main__":
    run_hybrid_evaluation()
