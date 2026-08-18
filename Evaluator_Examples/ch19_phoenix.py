"""
ch19_phoenix.py — Phoenix OTEL 완전 통합 + DeepEval/Ragas (외부평가)
========================================================================
Book Chapter 19 — Phoenix OTEL 모니터링

agent-eval monitor 와 함께 실행하면 Phoenix 전체 탭을 검증할 수 있다.

Phoenix 연동 범위:
  Tracing   — record_task() → OTLP 스팬 + save_to_file() → Annotations
  Datasets  — GoldenSetBuilder.push_to_phoenix()
  Playground— llm.prompts 속성 포함 시 프롬프트 재현 가능
  Prompts   — REST POST /v1/prompts
  GraphQL   — 프로젝트 목록·스팬·Annotation 조회 예시

Layer 3 외부 통합 — 대시보드 '외부평가' 탭 활성화:
  OPENAI_API_KEY + pip install 'agent-evaluator[eval]' 설치 시:
    → HybridPerformanceMonitor 자동 사용 (DeepEval G-Eval·Hallucination·Toxicity + Ragas RAG 지표)
    → results/ch19_phoenix.json 에 rag_metrics·advanced_metrics_summary 포함
    → 대시보드 '외부평가' 탭에 실제 점수 표시

  미설치 시:
    → PerformanceMonitor 사용 + 데모 외부평가 데이터 JSON 패치
    → 대시보드에서 외부평가 탭 UI 구조 확인 가능 (목업 데이터)

의존성:
    필수: pip install agent-evaluator          (numpy·pandas·python-dotenv·OTEL·Phoenix 포함)
    선택: agent-eval monitor                   (Phoenix OTEL 시각화 — otel 패키지는 기본 설치에 포함)
    선택: pip install "agent-evaluator[eval]"  (DeepEval + Ragas 실평가 활성화)
    선택: OPENAI_API_KEY 환경변수              (DeepEval/Ragas LLM 채점 — 미설정 시 mock 데이터로 대체)
    선택: ANTHROPIC_API_KEY 환경변수           (Anthropic 모델 사용 시)

실행:
    python Evaluator_Examples/ch19_phoenix.py
    agent-eval monitor  # (별도 터미널) Phoenix 기동

결과:
    results/ch19_phoenix.json
    → deprecated 전체 예제: Evaluator_Examples/.deprecated/07_phoenix_hybrid.py
"""

import json
import os
import socket
import time
from pathlib import Path

from agent_evaluator import load_env

load_env()

_PROJECT_ROOT  = Path(__file__).parent.parent
_OUTPUT_DIR    = str(_PROJECT_ROOT / "results")
_PHOENIX_URL   = os.getenv("PHOENIX_URL", "http://localhost:6006")
_PHOENIX_PORT  = int(_PHOENIX_URL.split(":")[-1])
_OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# 외부 평가 패키지 가용성 체크
# ---------------------------------------------------------------------------
def _check_eval_packages() -> bool:
    try:
        import deepeval  # noqa: F401
        import ragas     # noqa: F401
        return True
    except ImportError:
        return False

EVAL_AVAILABLE  = _check_eval_packages() and bool(_OPENAI_KEY)

# ---------------------------------------------------------------------------
# Phoenix 연결 확인 + setup_otel
# ---------------------------------------------------------------------------
def _phoenix_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", _PHOENIX_PORT)) == 0

PHOENIX_ONLINE = _phoenix_running()

if PHOENIX_ONLINE:
    from agent_evaluator import setup_otel
    setup_otel(endpoint=_PHOENIX_URL, service_name="ch19-phoenix")
    print(f"  Phoenix 연결 성공 — {_PHOENIX_URL}")
else:
    print(f"  Phoenix 미실행 — OTEL 비활성 (agent-eval monitor 로 기동)")

# ---------------------------------------------------------------------------
# 모니터 초기화 — API 키 + eval 패키지 있으면 HybridPerformanceMonitor
# ---------------------------------------------------------------------------
if EVAL_AVAILABLE:
    from agent_evaluator import HybridPerformanceMonitor
    monitor = HybridPerformanceMonitor(
        use_deepeval=True,
        use_ragas=True,
        deepeval_model="gpt-5-nano",
        ragas_model="gpt-5-nano",
        output_dir=_OUTPUT_DIR,
        enable_transparency=True,       # 투명성 탭: 메트릭 계산 Traces 자동 생성
        use_korean_tokenizer=True,
    )
    print("  HybridPerformanceMonitor 활성화 — DeepEval + Ragas 실평가")
    print("  대시보드 '외부평가' 탭에 실제 점수가 표시됩니다")
else:
    from agent_evaluator import PerformanceMonitor
    monitor = PerformanceMonitor(
        output_dir=_OUTPUT_DIR,
        enable_transparency=True,       # 투명성 탭: 메트릭 계산 Traces 자동 생성
        use_korean_tokenizer=True,
    )
    if not _OPENAI_KEY:
        print("  OPENAI_API_KEY 미설정 — PerformanceMonitor 사용 (데모 외부평가 데이터 주입)")
    else:
        print("  eval 패키지 미설치 — pip install 'agent-evaluator[eval]'")
    print("  대시보드 '외부평가' 탭: 목업 데이터로 UI 구조 확인 가능")

from agent_evaluator import create_taskresult
from agent_evaluator import agent_eval, EvalMetadata

# ===========================================================================
# 섹션 1: Tracing — 스팬 전송 + Annotations
# ===========================================================================
print("\n=== 섹션 1: Phoenix Tracing + Annotations ===")

TRACING_CASES = [
    ("qa",                   "한국의 수도는?",           "서울",           "서울입니다.",          None),
    ("tool_use",             "날씨 검색 도구 사용",      "맑음",           "맑고 따뜻합니다.",     None),
    ("information_retrieval","RAG 문서 검색 테스트",    "관련 문서 내용",  "문서에 따르면...",
     ["서울은 대한민국의 수도입니다.", "대한민국의 정치·경제 중심지입니다."]),
    ("code_generation",      "Hello World 코드",        "print('Hello')", "print('Hello World')", None),
    ("planning",             "프로젝트 계획 수립",       "1.분석 2.설계",  "1단계: 요구사항 분석...", None),
]

for task_type, question, ground_truth, response, context in TRACING_CASES:
    result = create_taskresult(
        task_id=f"trace_{task_type[:6]}",
        question=question,
        response=response,
        ground_truth=ground_truth,
        execution_time=round(1.0 + len(response) * 0.01, 2),
        task_type=task_type,
        tokens_used={"input": 120, "output": len(response.split()), "total": 120 + len(response.split())},
    
        use_korean_tokenizer=True,
    )

    if EVAL_AVAILABLE:
        # HybridPerformanceMonitor: input_text/output_text/retrieved_context 전달 → 자동 평가
        monitor.record_task(
            result,
            input_text=question,
            output_text=response,
            expected_output=ground_truth,
            retrieved_context=context,
        )
    else:
        monitor.record_task(result)

    kind = {"qa": "LLM", "tool_use": "TOOL", "information_retrieval": "RETRIEVER",
            "code_generation": "LLM", "planning": "AGENT"}.get(task_type, "CHAIN")
    print(f"  [{task_type:<22s}] span.kind={kind:<9s} acc={result.accuracy_score:.2f}")

if PHOENIX_ONLINE:
    print("  Tracing 탭 확인: Tracing → 스팬 클릭 → Annotations 섹션")

# ===========================================================================
# 섹션 2: Playground — llm.prompts 속성 포함 패턴
# ===========================================================================
print("\n=== 섹션 2: Phoenix Playground 연동 ===")

@agent_eval(monitor, task_type="qa", task_id_prefix="playground")
def playground_agent(question: str, ground_truth: str = "") -> tuple:
    """Playground 탭에서 재현 가능한 에이전트 (llm.prompts 속성 포함)."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    system_prompt = "당신은 정확하고 간결한 답변을 제공하는 AI 어시스턴트입니다."
    response = f"[PLAYGROUND] {question}에 대한 답변입니다."
    return response, EvalMetadata(
        extra={
            "llm.prompts": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": question},
            ],
            "input.mime_type":  "text/plain",
            "output.mime_type": "text/plain",
        }
    )

PLAYGROUND_CASES = [
    ("REST API 설계 원칙은?",      "RESTful 원칙"),
    ("마이크로서비스란 무엇인가?",  "독립 배포 서비스"),
]
for q, gt in PLAYGROUND_CASES:
    playground_agent(q, ground_truth=gt)

if PHOENIX_ONLINE:
    print("  Playground 탭: 스팬 클릭 → 'Open in Playground' 버튼")
else:
    print("  llm.prompts 포함 → Playground에서 프롬프트 재현 가능")

# ===========================================================================
# 섹션 3: Datasets — GoldenSetBuilder로 Phoenix 업로드
# ===========================================================================
print("\n=== 섹션 3: Phoenix Datasets 탭 ===")

try:
    from agent_evaluator.datasets.builder import GoldenSetBuilder

    builder = GoldenSetBuilder(
        source_dir=_OUTPUT_DIR,
        output_dir=str(_PROJECT_ROOT / "data"),
    )

    high_value = []
    tasks_list = monitor.extended_tasks if hasattr(monitor, "extended_tasks") else getattr(monitor, "tasks", [])
    for t in tasks_list:
        score = getattr(t, "accuracy_score", 0)
        if score >= 0.6:
            high_value.append({
                "task_id":       t.task_id,
                "question":      getattr(t, "question", t.task_id) or t.task_id,
                "response":      getattr(t, "response", "") or "",
                "ground_truth":  getattr(t, "ground_truth", "") or "",
                "accuracy_score": score,
                "task_type":     str(t.task_type),
            })

    print(f"  고품질 케이스 {len(high_value)}건 추출 (score≥0.6)")

    if PHOENIX_ONLINE and high_value:
        try:
            builder.push_to_phoenix(high_value, dataset_name="ch19-phoenix-golden", phoenix_endpoint=_PHOENIX_URL)
            print(f"  Phoenix Datasets 업로드 완료")
        except Exception as e:
            print(f"  push_to_phoenix: {e}")
    else:
        print(f"  Phoenix 실행 시 Datasets 탭에서 골든 데이터셋 확인 가능")

except Exception as e:
    print(f"  GoldenSetBuilder: {e}")

# ===========================================================================
# 섹션 4: Prompts — REST API로 프롬프트 등록
# ===========================================================================
print("\n=== 섹션 4: Phoenix Prompts 탭 ===")

if PHOENIX_ONLINE:
    try:
        import requests

        prompt_payload = {
            "prompt": {"name": "ch19-qa-system-prompt"},
            "version": {
                "template": {
                    "type": "chat",
                    "messages": [
                        {"role": "system", "content": "당신은 정확하고 간결한 답변을 제공하는 AI 어시스턴트입니다."},
                        {"role": "user",   "content": "질문: {{question}}\n답변:"},
                    ],
                },
                "template_type": "CHAT",
                "template_format": "MUSTACHE",
                "model_provider": "ANTHROPIC",
                "model_name": "claude-sonnet-4-6",
                "invocation_parameters": {"type": "anthropic", "anthropic": {"max_tokens": 1024}},
                "tags": ["production", "qa", "v0.8.2"],
            },
        }
        resp = requests.post(f"{_PHOENIX_URL}/v1/prompts", json=prompt_payload, timeout=5)
        if resp.status_code in (200, 201):
            data_field = resp.json().get("data", {})
            print(f"  프롬프트 등록 성공: id={data_field.get('id', '?')}  model={data_field.get('model_name', '?')}")
        else:
            print(f"  프롬프트 등록 응답: {resp.status_code} — {resp.text[:200]}")
    except Exception as e:
        print(f"  Prompts REST API: {e}")
else:
    print("  Phoenix 실행 후 REST 등록 가능: POST http://localhost:6006/v1/prompts")

# ===========================================================================
# 섹션 5: GraphQL — 데이터 조회 예시
# ===========================================================================
print("\n=== 섹션 5: Phoenix GraphQL 조회 ===")
print(f"  GraphQL UI: {_PHOENIX_URL}/graphql")

GRAPHQL_EXAMPLES = """
# ── 준비된 쿼리 예시 (GraphiQL UI에 붙여넣기) ─────────────────────────

# 1. 프로젝트 목록
query {
  projects {
    edges { node { id name traceCount spanCount } }
  }
}

# 2. 스팬 + Annotations (project name 변경 필요)
query GetSpans($proj: String!) {
  project(name: $proj) {
    spans(first: 10) {
      edges {
        node {
          spanId name statusCode latencyMs
          input { value }
          spanAnnotations { name score label }
        }
      }
    }
  }
}
# Variables: {"proj": "ch19-phoenix"}

# 3. 데이터셋 목록
query {
  datasets {
    edges { node { id name exampleCount createdAt } }
  }
}
"""
print(GRAPHQL_EXAMPLES)

if PHOENIX_ONLINE:
    try:
        import requests

        def gql(query: str, variables: dict = None) -> dict:
            resp = requests.post(
                f"{_PHOENIX_URL}/graphql",
                json={"query": query, "variables": variables or {}},
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            return resp.json() if resp.ok else {}

        result = gql("query { projects { edges { node { id name traceCount } } } }")
        projects = result.get("data", {}).get("projects", {}).get("edges", [])
        print(f"  GraphQL 프로젝트 수: {len(projects)}개")
        for p in projects[:3]:
            node = p["node"]
            print(f"    - {node['name']}  (traces: {node['traceCount']})")
    except Exception as e:
        print(f"  GraphQL 조회: {e}")

# ===========================================================================
# 최종 저장 + 외부평가 데이터 처리
# ===========================================================================
print("\n=== 최종 저장 & 외부평가 탭 데이터 ===")

report = monitor.generate_report().to_dict()
total  = report.get("total_tasks", 0)
# TCR: accuracy_metrics["tcr"]["tcr"] (0-100 범위 float)
# EvaluationReport.to_dict() 최상위 키: period, total_tasks, accuracy_metrics,
#   efficiency_metrics, quality_metrics, security_metrics, alerts, recommendations,
#   timestamp, extra_metrics  (task_metrics 키는 존재하지 않음)
tcr_raw = report.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0)
tcr = float(tcr_raw) / 100
print(f"  총 태스크: {total}건  TCR: {tcr:.1%}")

# save_to_file 호출 — HybridPerformanceMonitor: rag_metrics·advanced_metrics_summary 포함
if hasattr(monitor, "save_to_file"):
    monitor.save_to_file("ch19_phoenix")

print("\n결과 저장 완료: results/ch19_phoenix.json")

# ===========================================================================
# 외부평가 데이터 주입 (eval 패키지 없을 때 — 데모용)
# ===========================================================================
if not EVAL_AVAILABLE:
    print("\n=== 외부평가 탭 데모 데이터 주입 (목업) ===")
    print("  실제 운영 시: OPENAI_API_KEY 설정 + pip install 'agent-evaluator[eval]'")
    print("  아래는 대시보드 '외부평가' 탭의 UI 구조 확인을 위한 데모 데이터입니다")

    # 저장된 JSON 읽기
    json_path = Path(_OUTPUT_DIR) / "ch19_phoenix.json"
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # 태스크별 advanced_metrics 주입 (ragas_* 키는 loader가 rag_metrics로 재구성)
        import random
        random.seed(42)

        MOCK_METRICS = [
            # (g_eval_score, hallucination_score, toxicity_score, ragas_faithfulness, ragas_answer_relevancy)
            (0.88, 0.92, 0.02, 0.85, 0.91),   # trace_qa
            (0.75, 0.88, 0.01, None, None),    # trace_tool_u (도구 사용, RAG 없음)
            (0.82, 0.95, 0.00, 0.89, 0.87),   # trace_inform (RAG)
            (0.71, 0.85, 0.03, None, None),    # trace_code_g
            (0.79, 0.90, 0.01, None, None),    # trace_planni
            (0.83, 0.91, 0.02, None, None),    # playground_0
            (0.77, 0.87, 0.01, None, None),    # playground_1
        ]

        tasks = data.get("tasks", [])
        for i, task in enumerate(tasks):
            if i >= len(MOCK_METRICS):
                break
            g, h, t, rf, ra = MOCK_METRICS[i]
            adv: dict = {
                "g_eval_score":          g,
                "g_eval_passed":         g >= 0.7,
                "g_eval_reason":         "답변이 정확하고 관련성이 높습니다." if g >= 0.7 else "답변 품질 개선 필요",
                "hallucination_score":   h,
                "hallucination_detected": h < 0.8,
                "toxicity_score":        t,
                "toxicity_detected":     t > 0.5,
            }
            if rf is not None:
                adv["ragas_faithfulness"]      = rf
                adv["ragas_answer_relevancy"]  = ra
                adv["ragas_context_recall"]    = round(rf * 0.95, 3)
                adv["ragas_context_precision"] = round(ra * 0.93, 3)
            task["advanced_metrics"] = adv

        data["tasks"] = tasks

        # 상위 레벨 advanced_metrics_summary 주입 (대시보드 DeepEval 요약 섹션)
        g_scores = [m[0] for m in MOCK_METRICS]
        h_scores = [m[1] for m in MOCK_METRICS]
        t_scores = [m[2] for m in MOCK_METRICS]
        data["advanced_metrics_summary"] = {
            "g_eval_score": {
                "mean": round(sum(g_scores) / len(g_scores), 3),
                "min":  round(min(g_scores), 3),
                "max":  round(max(g_scores), 3),
                "count": len(g_scores),
            },
            "hallucination_score": {
                "mean": round(sum(h_scores) / len(h_scores), 3),
                "min":  round(min(h_scores), 3),
                "max":  round(max(h_scores), 3),
                "count": len(h_scores),
            },
            "toxicity_score": {
                "mean": round(sum(t_scores) / len(t_scores), 3),
                "min":  round(min(t_scores), 3),
                "max":  round(max(t_scores), 3),
                "count": len(t_scores),
            },
            "g_eval_pass_rate":   {"passed": 6, "total": 7, "rate": round(6/7, 3)},
        }

        # RAG 지표 (RAG 태스크 3건: trace_inform + playground 2건)
        rag_tasks = [(m[3], m[4]) for m in MOCK_METRICS if m[3] is not None]
        if rag_tasks:
            data["rag_metrics"] = {
                "faithfulness":      [r[0] for r in rag_tasks],
                "answer_relevancy":  [r[1] for r in rag_tasks],
                "context_recall":    [round(r[0] * 0.95, 3) for r in rag_tasks],
                "context_precision": [round(r[1] * 0.93, 3) for r in rag_tasks],
            }

        # JSON 덮어쓰기
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        g_vals = data["advanced_metrics_summary"]["g_eval_score"]
        rag_n  = len(data.get("rag_metrics", {}).get("faithfulness", []))
        print(f"  외부평가 데이터 주입 완료:")
        print(f"    G-Eval 평균: {g_vals['mean']:.3f}  (min={g_vals['min']}, max={g_vals['max']})")
        print(f"    RAG 지표 건수: {rag_n}건 (faithfulness·answer_relevancy·recall·precision)")
        print(f"  → agent-eval dashboard 실행 후 '외부평가' 탭 확인")

    except Exception as e:
        print(f"  데모 데이터 주입 실패: {e}")

else:
    # HybridPerformanceMonitor 사용 시 — 실제 지표 요약 출력
    print("\n=== HybridPerformanceMonitor 외부평가 결과 ===")
    try:
        hybrid_report = monitor.generate_hybrid_report()
        adv_summary = hybrid_report.advanced_metrics_summary
        if adv_summary:
            for metric_name, stats in adv_summary.items():
                if isinstance(stats, dict) and "mean" in stats:
                    print(f"  {metric_name:<25s} mean={stats['mean']:.3f}")
        else:
            print("  외부평가 결과 없음 (태스크 평가 중 오류 발생 가능 — 로그 확인)")
    except Exception as e:
        print(f"  hybrid_report 생성 실패: {e}")

# ===========================================================================
# 섹션 추가: DeepEvalAdapter + RagasAdapter 직접 사용
#
# HybridPerformanceMonitor가 내부적으로 사용하는 두 어댑터를 독립적으로
# 인스턴스화해 단건 평가를 직접 실행합니다.
#
# 필요 조건:
#   pip install "agent-evaluator[eval]"   (deepeval + ragas + langchain)
#   OPENAI_API_KEY (DeepEval·Ragas LLM 채점)
#
# DeepEvalAdapter:
#   GEval(커스텀 기준) + Hallucination + Toxicity + Bias + AnswerRelevancy
# RagasAdapter:
#   Faithfulness + ContextPrecision [+ AnswerRelevancy + ContextRecall]
# ===========================================================================
print("\n=== 섹션 추가: DeepEvalAdapter + RagasAdapter 직접 사용 ===")

try:
    from agent_evaluator.integrations.metric_adapters import (
        DeepEvalAdapter, RagasAdapter, EvaluationContext,
    )

    if not _OPENAI_KEY:
        print("  OPENAI_API_KEY 미설정 — 실제 LLM 채점 대신 안내만 출력합니다")
        print("    (evaluate() 를 키 없이 호출하면 provider 재시도로 수 분간 멈출 수 있습니다)")
        print("    .env 에 OPENAI_API_KEY 설정 후 재실행하세요")

    # ── DeepEvalAdapter ───────────────────────────────────────────────────
    print("  [1] DeepEvalAdapter")
    deepeval_adapter = DeepEvalAdapter(model="gpt-5-nano", threshold=0.5)
    if not _OPENAI_KEY:
        pass
    elif not deepeval_adapter.is_available():
        print("    미설치 — pip install 'agent-evaluator[eval]' 로 활성화")
    else:
        ctx_de = EvaluationContext(
            input_text="서울의 인구는 얼마인가요?",
            output_text="서울의 인구는 약 950만 명으로, 대한민국 최대 도시입니다.",
            expected_output="약 950만 명",
            task_type="qa",
            quality_criteria="factual accuracy",
        )
        de_result = deepeval_adapter.evaluate(ctx_de)
        if de_result:
            print(f"    G-Eval score    : {de_result.get('g_eval_score', 'n/a')}")
            print(f"    Toxicity score  : {de_result.get('toxicity_score', 'n/a')}")
            print(f"    Bias score      : {de_result.get('bias_score', 'n/a')}")
        else:
            print(f"    평가 결과 없음 (API 키 또는 패키지 확인)")

    # ── RagasAdapter ─────────────────────────────────────────────────────
    print("  [2] RagasAdapter")
    ragas_adapter = RagasAdapter(llm_model="gpt-5-nano")
    if not _OPENAI_KEY:
        pass
    elif not ragas_adapter.is_available():
        print("    미설치 — pip install 'agent-evaluator[eval]' 로 활성화")
    else:
        ctx_ra = EvaluationContext(
            input_text="아인슈타인의 출생 연도는?",
            output_text="알베르트 아인슈타인은 1879년에 태어났습니다.",
            expected_output="1879년",
            retrieved_context=[
                "알베르트 아인슈타인은 1879년 3월 14일 독일 울름에서 태어났습니다.",
                "아인슈타인은 특수상대성이론과 일반상대성이론을 발표했습니다.",
            ],
            task_type="information_retrieval",
        )
        ra_result = ragas_adapter.evaluate(ctx_ra)
        if ra_result:
            print(f"    Faithfulness      : {ra_result.get('ragas_faithfulness', 'n/a')}")
            print(f"    ContextPrecision  : {ra_result.get('ragas_context_precision', 'n/a')}")
            print(f"    AnswerRelevancy   : {ra_result.get('ragas_answer_relevancy', 'n/a')}")
        else:
            print(f"    평가 결과 없음 (retrieved_context 없거나 API 키 확인)")

    print("  어댑터 직접 사용 vs HybridPerformanceMonitor:")
    print("    직접 사용     → 단건 평가·커스텀 파이프라인·테스트 환경")
    print("    HybridMonitor → record_task()마다 자동 채점 + 대시보드 통합")

except ImportError as _e:
    print(f"  어댑터 모듈 로드 실패 (skip): {_e}")
except Exception as _e:
    print(f"  어댑터 실행 중 오류 (skip): {_e}")

if PHOENIX_ONLINE:
    print(f"\nPhoenix 확인:")
    print(f"  Tracing    → {_PHOENIX_URL}  (서비스: ch19-phoenix)")
    print(f"  Annotations → 스팬 클릭 → 우측 패널 → 'Annotations' 섹션")
    print(f"  GraphQL    → {_PHOENIX_URL}/graphql")

print("\n대시보드에서 확인: agent-eval dashboard")
print("  → '외부평가' 탭 클릭 (DeepEval·G-Eval·Hallucination + RAG 지표)")
