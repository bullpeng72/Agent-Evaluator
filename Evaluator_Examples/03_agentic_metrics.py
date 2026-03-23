from __future__ import annotations

"""
에이전트 지표 검증 예제 — Agent Evaluator
==========================================

커버 지표 (에이전트 카테고리):
  Layer 2  │ Tool Call Analysis     (효율성 점수 · 중복 호출 · 실패율)
           │ Retry & Correction     (재시도 패턴 · 자기수정 능력 · 첫시도 성공률)
           │ Tool Selection         (F1 기반 Precision · Recall · 선택 정확도)
           │ Agent Coordination     (협업 점수(0-10) · Hub/Chain/Mesh 패턴)
           │ Workflow Execution     (단계별 성공률 · 병목 탐지 · 병렬화 기회)

실행:
    python 03_agentic_metrics.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent_evaluator import (
    PerformanceMonitor,
    TaskResult,
    TestTransparencyManager,
    AnnotationType,
    TestStepStatus,
)
from agent_evaluator.reporting import generate_comprehensive_html_report

# ────────────────────────────────────────────────────────────────────────────────
# 에이전트 역할 정의
# ────────────────────────────────────────────────────────────────────────────────
AGENTS = {
    "orchestrator": "오케스트레이터",
    "researcher":   "리서처",
    "analyst":      "분석가",
    "writer":       "작성자",
    "reviewer":     "검토자",
}

# 도구 카탈로그
ALL_TOOLS = [
    "web_search", "doc_reader", "data_query", "code_executor",
    "summarizer", "classifier", "translator", "image_analyzer",
    "chart_generator", "report_writer", "email_sender", "db_lookup",
]

# 워크플로우 단계 정의
WORKFLOW_STEPS = [
    {"name": "input_validation",   "type": "validation"},
    {"name": "data_retrieval",     "type": "retrieval"},
    {"name": "data_preprocessing", "type": "transform"},
    {"name": "analysis",           "type": "analysis"},
    {"name": "synthesis",          "type": "synthesis"},
    {"name": "quality_check",      "type": "validation"},
    {"name": "output_generation",  "type": "output"},
]


def _make_tool_calls(tools: list[str], rng: random.Random, redundancy: float = 0.0) -> list[dict]:
    """도구 호출 목록 생성. redundancy = 중복 비율(0~1)"""
    calls = []
    for tool in tools:
        success = rng.random() > 0.1  # 90% 성공률
        calls.append({
            "name": tool,
            "tool_name": tool,
            "success": success,
            "execution_time": round(rng.uniform(0.05, 0.8), 3),
            "args": {"query": f"task_query_{tool}"},
        })
    # 중복 호출 추가
    if redundancy > 0 and calls:
        n_redundant = max(1, int(len(calls) * redundancy))
        for _ in range(n_redundant):
            dup = rng.choice(calls).copy()
            dup["redundant"] = True
            calls.append(dup)
    return calls


def _make_agent_interactions(agents: list[str], rng: random.Random, n: int = 3) -> list[dict]:
    """에이전트 간 상호작용 생성"""
    interactions = []
    for _ in range(n):
        from_a, to_a = rng.sample(agents, 2)
        interactions.append({
            "from_agent": from_a,
            "to_agent":   to_a,
            "type": rng.choice(["task_delegation", "result_sharing", "feedback", "coordination"]),
            "success": rng.random() > 0.08,
            "context": f"{from_a} → {to_a} 협업",
        })
    return interactions


def _make_chain_steps(steps: list[dict], rng: random.Random, fail_step: str | None = None) -> list[dict]:
    """워크플로우 단계 생성"""
    result = []
    for s in steps:
        is_bottleneck = s["name"] in ("data_retrieval", "analysis")
        success = False if s["name"] == fail_step else rng.random() > 0.12
        result.append({
            "name": s["name"],
            "type": s["type"],
            "success": success,
            "execution_time": round(rng.uniform(0.5, 3.0) * (3 if is_bottleneck else 1), 3),
            "metadata": {"bottleneck": is_bottleneck},
        })
    return result


# ────────────────────────────────────────────────────────────────────────────────
# 시나리오 정의
# ────────────────────────────────────────────────────────────────────────────────

# (scenario_name, tools_expected, tools_actual_pool, agents, has_workflow, retry, redundancy)
SCENARIOS = [
    # ─── 단일 에이전트 — 도구 선택 완벽 ───────────────────────────────────────
    ("simple_search",      ["web_search"],                      ["web_search"],                       ["researcher"],             False, 1, 0.0),
    ("data_lookup",        ["db_lookup", "data_query"],         ["db_lookup", "data_query"],          ["analyst"],                False, 1, 0.0),
    ("code_run",           ["code_executor"],                   ["code_executor"],                    ["analyst"],                False, 1, 0.0),
    ("classify_task",      ["classifier"],                      ["classifier"],                       ["analyst"],                False, 1, 0.0),
    # ─── 단일 에이전트 — 도구 선택 부정확 (낮은 F1) ────────────────────────────
    ("wrong_tool_1",       ["web_search"],                      ["doc_reader"],                       ["researcher"],             False, 1, 0.0),
    ("wrong_tool_2",       ["data_query", "chart_generator"],   ["db_lookup"],                        ["analyst"],                False, 2, 0.0),
    ("partial_match",      ["web_search", "summarizer"],        ["web_search", "doc_reader"],         ["researcher"],             False, 1, 0.0),
    # ─── 멀티 에이전트 — Hub 패턴 ──────────────────────────────────────────────
    ("research_hub",       ["web_search", "summarizer"],        ["web_search", "summarizer"],         ["orchestrator", "researcher", "writer"],       True, 1, 0.0),
    ("analysis_hub",       ["data_query", "chart_generator"],   ["data_query", "chart_generator"],    ["orchestrator", "analyst", "writer", "reviewer"], True, 1, 0.0),
    ("document_hub",       ["doc_reader", "summarizer", "report_writer"], ["doc_reader", "summarizer", "report_writer"], ["orchestrator", "researcher", "writer"], True, 1, 0.0),
    # ─── 멀티 에이전트 — Chain 패턴 ────────────────────────────────────────────
    ("chain_research",     ["web_search", "summarizer", "report_writer"], ["web_search", "summarizer", "report_writer"], ["researcher", "analyst", "writer"], True, 1, 0.0),
    ("chain_analysis",     ["data_query", "classifier", "chart_generator"], ["data_query", "classifier", "chart_generator"], ["analyst", "writer", "reviewer"], True, 1, 0.1),
    # ─── 재시도 시나리오 ───────────────────────────────────────────────────────
    ("retry_on_fail_1",    ["web_search"],                      ["web_search"],                       ["researcher"],             False, 2, 0.0),
    ("retry_on_fail_2",    ["code_executor", "data_query"],     ["code_executor", "data_query"],      ["analyst"],                False, 3, 0.0),
    ("retry_success",      ["db_lookup"],                       ["db_lookup"],                        ["analyst"],                True,  2, 0.0),
    # ─── 중복 호출 시나리오 ────────────────────────────────────────────────────
    ("redundant_calls_1",  ["web_search", "doc_reader"],        ["web_search", "doc_reader"],         ["researcher"],             False, 1, 0.5),
    ("redundant_calls_2",  ["data_query"],                      ["data_query"],                       ["analyst"],                False, 1, 1.0),
    # ─── 복잡한 멀티 에이전트 워크플로우 ──────────────────────────────────────
    ("complex_pipeline",   ["web_search", "data_query", "chart_generator", "report_writer"],
                           ["web_search", "data_query", "chart_generator", "report_writer"],
                           ["orchestrator", "researcher", "analyst", "writer", "reviewer"], True, 1, 0.0),
    ("ml_pipeline",        ["data_query", "code_executor", "classifier", "chart_generator"],
                           ["data_query", "code_executor", "classifier", "chart_generator"],
                           ["orchestrator", "analyst", "writer"],                          True, 1, 0.1),
    ("translation_chain",  ["doc_reader", "translator", "summarizer"],
                           ["doc_reader", "translator", "summarizer"],
                           ["researcher", "writer"],                                        True, 1, 0.0),
    # ─── 실패 포함 워크플로우 ──────────────────────────────────────────────────
    ("workflow_fail_1",    ["data_query", "analysis"],          ["data_query"],                       ["analyst"],                True, 1, 0.0),
    ("workflow_fail_2",    ["web_search", "summarizer"],        ["web_search"],                       ["researcher"],             True, 2, 0.0),
    # ─── 이메일/알림 에이전트 ─────────────────────────────────────────────────
    ("notification_flow",  ["db_lookup", "email_sender"],       ["db_lookup", "email_sender"],        ["orchestrator", "analyst"], True, 1, 0.0),
    ("image_analysis",     ["image_analyzer", "classifier"],    ["image_analyzer", "classifier"],     ["analyst"],                False, 1, 0.0),
    ("full_report",        ["web_search", "data_query", "summarizer", "chart_generator", "report_writer"],
                           ["web_search", "data_query", "summarizer", "chart_generator", "report_writer"],
                           ["orchestrator", "researcher", "analyst", "writer", "reviewer"], True, 1, 0.0),
]


# ── 시나리오별 대표 콘텐츠 ────────────────────────────────────────────────────────
# (request, response_ok, response_fail, ground_truth, expected_elements)
_SCENARIO_CONTENT = {
    "simple_search": (
        "최신 AI 에이전트 프레임워크 동향을 웹에서 검색해 요약하세요.",
        "web_search 실행 결과: LangGraph·CrewAI·AutoGen이 주요 트렌드. 멀티에이전트 협업, 툴 통합, 평가 파이프라인 지원이 공통 특징입니다.",
        "검색 결과를 가져오지 못했습니다.",
        "LangGraph, CrewAI, AutoGen 동향 — 멀티에이전트·툴 통합·평가 파이프라인",
        ["LangGraph", "CrewAI", "AutoGen", "멀티에이전트"],
    ),
    "data_lookup": (
        "데이터베이스에서 사용자 ID 12345의 최근 주문 내역을 조회하세요.",
        "db_lookup 결과: 사용자 12345 / 최근 주문 3건 — 2024-01-15 노트북 ₩1,200,000 / 2024-01-22 마우스 ₩45,000 / 2024-02-03 SSD ₩180,000.",
        "데이터베이스 조회 실패.",
        "사용자 12345 최근 주문 3건, 날짜·상품·금액 포함",
        ["12345", "주문", "조회"],
    ),
    "code_run": (
        "Python 코드를 실행하고 결과를 반환하세요: sorted([3,1,4,1,5], reverse=True)",
        "code_executor 실행 완료. 결과: [5, 4, 3, 1, 1]. sorted() 내장 함수 내림차순 정렬 성공.",
        "코드 실행 실패.",
        "[5, 4, 3, 1, 1] — 내림차순 정렬 결과",
        ["[5, 4, 3, 1, 1]", "정렬", "code_executor"],
    ),
    "classify_task": (
        "텍스트 감성을 분류하세요: '이 제품은 정말 만족스럽고 다시 구매하고 싶습니다.'",
        "classifier 실행 결과: 긍정(Positive) 분류 — 신뢰도 0.97. 감성 키워드: '만족스럽고', '다시 구매하고 싶습니다'.",
        "분류 모델 오류.",
        "긍정(Positive), 신뢰도 0.97 이상",
        ["긍정", "Positive", "신뢰도"],
    ),
    "wrong_tool_1": (
        "최신 AI 뉴스를 검색해 주세요.",
        "doc_reader로 로컬 문서 검색 시도 — 최신 뉴스 없음. web_search 도구가 필요합니다.",
        "관련 정보를 찾지 못했습니다.",
        "web_search로 최신 AI 뉴스 검색 필요",
        ["web_search", "뉴스"],
    ),
    "wrong_tool_2": (
        "제품별 월간 판매량 데이터를 분석하고 차트를 생성하세요.",
        "db_lookup으로 데이터 일부 조회 완료. data_query·chart_generator 없이 완전한 분석·시각화 불가.",
        "데이터 분석 실패.",
        "data_query로 데이터 조회 후 chart_generator로 시각화 필요",
        ["data_query", "chart_generator"],
    ),
    "partial_match": (
        "경쟁사 제품 리뷰를 수집하고 요약하세요.",
        "web_search로 리뷰 수집 완료. doc_reader 대신 summarizer 필요. 수집 리뷰 요약: 경쟁사 A 제품은 배터리 성능에서 높은 평가.",
        "요약 실패.",
        "web_search + summarizer 조합으로 리뷰 수집 및 요약",
        ["web_search", "summarizer", "요약"],
    ),
    "research_hub": (
        "AI 에이전트 시장 동향 보고서를 작성하세요.",
        "오케스트레이터→리서처(web_search)→작성자(report_writer) 허브 실행 완료. 2024 AI 에이전트 시장 규모 $5.2B, 연간 43% 성장 전망. 주요 플레이어: OpenAI, Anthropic, Google.",
        "보고서 작성 실패.",
        "시장 규모 $5.2B, 연간 성장률 43%, 주요 플레이어 포함",
        ["시장 규모", "성장", "$5.2B"],
    ),
    "analysis_hub": (
        "Q4 판매 데이터를 분석하고 시각화 보고서를 작성하세요.",
        "오케스트레이터→분석가(data_query)→작성자(chart_generator)→검토자 허브 완료. Q4 매출 2.1억, 전분기 대비 17% 성장. 차트 3종 생성.",
        "분석 파이프라인 실패.",
        "Q4 매출 2.1억, 전분기 17% 성장, 시각화 차트 포함",
        ["Q4", "매출", "성장", "chart_generator"],
    ),
    "document_hub": (
        "기술 문서를 요약하고 보고서를 생성하세요.",
        "리서처(doc_reader)→summarizer→작성자(report_writer) 허브 완료. 총 47페이지 보고서 생성.",
        "문서 처리 실패.",
        "doc_reader→summarizer→report_writer 파이프라인 성공, 47페이지",
        ["doc_reader", "summarizer", "report_writer"],
    ),
    "chain_research": (
        "신기술 트렌드를 조사하고 분석 보고서를 작성하세요.",
        "researcher(web_search)→analyst(summarizer)→writer(report_writer) 체인 완료. 2024 3대 기술 트렌드: 생성형 AI, 엣지 컴퓨팅, 양자 컴퓨팅.",
        "체인 실패.",
        "web_search→summarizer→report_writer 체인, 3대 기술 트렌드 보고서",
        ["생성형 AI", "엣지 컴퓨팅", "양자 컴퓨팅"],
    ),
    "chain_analysis": (
        "고객 행동 데이터를 분석하고 세그먼트별 차트를 생성하세요.",
        "analyst(data_query)→writer(classifier)→reviewer(chart_generator) 체인 완료. 고객 3개 세그먼트: 충성(32%), 이탈 위험(28%), 신규(40%). 차트 생성.",
        "분석 체인 부분 실패.",
        "data_query→classifier→chart_generator, 3개 세그먼트 분류 차트",
        ["세그먼트", "분류", "차트", "data_query"],
    ),
    "retry_on_fail_1": (
        "날씨 API에서 서울 현재 날씨를 검색하세요.",
        "첫 번째 web_search 실패(API 타임아웃) → 재시도 성공. 서울 현재 날씨: 맑음 12°C, 습도 45%, 바람 북서풍 3m/s.",
        "날씨 검색 최종 실패.",
        "서울 날씨 맑음 12°C, 재시도 후 성공",
        ["서울", "날씨", "맑음", "재시도"],
    ),
    "retry_on_fail_2": (
        "복잡한 데이터 쿼리를 실행하고 결과를 반환하세요.",
        "1차 code_executor 실패(메모리) → 2차 data_query 실패(타임아웃) → 3차 성공. 쿼리 결과: 총 12,847건 반환.",
        "3회 시도 모두 실패.",
        "3회 재시도 후 최종 성공, 12,847건 반환",
        ["재시도", "성공", "12,847"],
    ),
    "retry_success": (
        "데이터베이스에서 부서별 인원 현황을 조회하세요.",
        "첫 번째 db_lookup 실패(연결 오류) → 재시도 성공. 부서별 인원: 개발팀 45명, 마케팅 23명, 인사 12명, 재무 18명. 총 98명.",
        "DB 조회 실패.",
        "부서별 인원 조회, 총 98명 — 개발팀 최다",
        ["개발팀", "마케팅", "총 98명", "db_lookup"],
    ),
    "redundant_calls_1": (
        "AI 최신 논문을 검색하고 주요 내용을 정리하세요.",
        "web_search 1회 + doc_reader 1회 + web_search 중복 1회(불필요). 논문 요약: GPT-4 기술 보고서, Llama 3 아키텍처, Gemini 멀티모달 연구.",
        "검색 중 오류.",
        "web_search + doc_reader로 논문 수집 (중복 호출 최소화 필요)",
        ["web_search", "doc_reader", "논문", "GPT-4"],
    ),
    "redundant_calls_2": (
        "현재 시스템 상태를 점검하세요.",
        "data_query 2회 중복 실행(최적화 필요). 시스템 상태: CPU 45%, 메모리 62%, 디스크 23%. 전체 정상.",
        "시스템 점검 실패.",
        "단일 data_query로 시스템 상태 조회 (CPU·메모리·디스크)",
        ["CPU", "메모리", "디스크", "data_query"],
    ),
    "complex_pipeline": (
        "경쟁사 비교 분석 종합 보고서를 작성하세요.",
        "5에이전트 파이프라인 완료: 오케스트레이터→리서처(web_search)→분석가(data_query)→작성자(chart_generator + report_writer)→검토자. 경쟁사 A·B·C 시장점유율·가격·기능 비교표 포함.",
        "복잡 파이프라인 실패.",
        "5에이전트 파이프라인, 경쟁사 3사 비교 분석 보고서",
        ["경쟁사", "비교", "파이프라인", "report_writer"],
    ),
    "ml_pipeline": (
        "고객 이탈 예측 모델을 학습하고 결과를 시각화하세요.",
        "data_query→code_executor(모델 학습)→classifier(예측)→chart_generator(ROC 곡선) 완료. 이탈 예측 AUC 0.87, 정밀도 0.83, 재현율 0.79.",
        "ML 파이프라인 오류.",
        "AUC 0.87, 정밀도 0.83, 재현율 0.79, ROC 곡선 포함",
        ["AUC", "정밀도", "재현율", "ROC"],
    ),
    "translation_chain": (
        "영문 기술 문서를 한국어로 번역하고 요약하세요.",
        "doc_reader(문서 로드)→translator(영→한)→summarizer(핵심 요약) 체인 완료. 번역 15페이지 / 핵심 요약: 마이크로서비스 아키텍처 7가지 모범 사례.",
        "번역 체인 실패.",
        "doc_reader→translator→summarizer 체인, 15페이지 번역 완료",
        ["번역", "요약", "마이크로서비스", "summarizer"],
    ),
    "workflow_fail_1": (
        "매출 데이터를 분석하고 핵심 인사이트를 도출하세요.",
        "data_query 부분 완료 후 analyzer 도구 미사용으로 분석 중단. 조회 데이터: 이번 달 총 매출 ₩850M.",
        "데이터 분석 중단.",
        "data_query + analyzer로 완전한 인사이트 도출 필요",
        ["data_query", "분석", "매출"],
    ),
    "workflow_fail_2": (
        "최신 기사를 검색하고 인사이트를 요약하세요.",
        "web_search 완료, summarizer 없어 원문 반환. 원문: OpenAI GPT-5 개발 중, 멀티모달 강화 예정...",
        "요약 실패.",
        "web_search + summarizer 조합 필요, 요약 미완성",
        ["web_search", "summarizer", "요약"],
    ),
    "notification_flow": (
        "VIP 고객 목록을 조회하고 이메일 알림을 발송하세요.",
        "db_lookup으로 VIP 고객 127명 조회 → email_sender로 맞춤형 알림 발송 완료. 발송 성공률 99.2%.",
        "알림 발송 실패.",
        "db_lookup + email_sender, VIP 127명 발송 성공률 99.2%",
        ["db_lookup", "email_sender", "VIP", "127명"],
    ),
    "image_analysis": (
        "업로드된 제품 이미지를 분석하고 카테고리를 분류하세요.",
        "image_analyzer로 이미지 특징 추출 → classifier로 카테고리 분류. 결과: 전자제품 > 노트북 (신뢰도 0.94).",
        "이미지 분석 오류.",
        "image_analyzer + classifier, 전자제품>노트북 신뢰도 0.94",
        ["image_analyzer", "classifier", "전자제품", "신뢰도"],
    ),
    "full_report": (
        "시장 조사부터 최종 보고서까지 전체 파이프라인을 실행하세요.",
        "5에이전트 풀 파이프라인 완료: 오케스트레이터→리서처(web_search)→분석가(data_query + summarizer)→작성자(chart_generator + report_writer)→검토자. 최종 보고서 52페이지 생성.",
        "풀 파이프라인 실패.",
        "5에이전트 풀 파이프라인, 52페이지 최종 보고서",
        ["풀 파이프라인", "보고서", "52페이지"],
    ),
}


def run_agentic_evaluation():
    print("\n" + "=" * 70)
    print("  에이전트 지표 평가 — Agent Evaluator")
    print("  Coverage: Tool Call · Retry · Tool Selection · Coordination · Workflow")
    print("=" * 70)

    rng = random.Random(2025)

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        enable_transparency=True,
        output_dir=str(project_root / "results"),
    )

    base_time = datetime.now() - timedelta(hours=3)

    for idx, (name, expected_tools, actual_tools, agents, has_wf, attempts, redundancy) in enumerate(SCENARIOS):
        task_id = f"agent_{idx+1:03d}_{name}"

        # 도구 호출 생성
        tool_calls = _make_tool_calls(actual_tools, rng, redundancy)

        # 성공 여부 — 도구 미스매치가 있으면 확률적 실패
        tool_match = set(expected_tools) == set(actual_tools)
        success_prob = 0.92 if tool_match else (0.65 if set(expected_tools) & set(actual_tools) else 0.30)
        success = rng.random() < success_prob
        completion = round(rng.uniform(0.8, 1.0) if success else rng.uniform(0.3, 0.6), 3)
        accuracy = round(rng.uniform(0.75, 0.95) if success else rng.uniform(0.25, 0.55), 3)

        # 에이전트 상호작용 (멀티 에이전트)
        agent_interactions = None
        if len(agents) > 1:
            n_interactions = rng.randint(len(agents) - 1, len(agents) * 2)
            agent_interactions = _make_agent_interactions(agents, rng, n_interactions)

        # 워크플로우 단계
        chain_steps = None
        if has_wf:
            # 실패 워크플로우는 한 단계 실패
            fail_step = None if success else rng.choice([s["name"] for s in WORKFLOW_STEPS[1:]])
            steps_subset = WORKFLOW_STEPS[:rng.randint(4, len(WORKFLOW_STEPS))]
            chain_steps = _make_chain_steps(steps_subset, rng, fail_step)

        exec_time = round(rng.uniform(0.5, 8.0) * (1.5 if len(agents) > 2 else 1.0), 3)
        input_tokens = rng.randint(200, 2000)
        output_tokens = rng.randint(100, 1500)

        task = TaskResult(
            task_id=task_id,
            task_type="tool_use" if not has_wf else "planning",
            success=success,
            completion_score=completion,
            accuracy_score=accuracy,
            execution_time=exec_time,
            tokens_used={"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens},
            tool_calls=tool_calls,
            attempts=attempts,
            errors=[] if success else ["tool_mismatch" if not tool_match else "execution_error"],
            timestamp=base_time + timedelta(minutes=idx * 4),
            agent_interactions=agent_interactions,
            chain_steps=chain_steps,
            expected_tools=expected_tools,
            framework="crewai" if len(agents) > 1 else "langchain",
        )

        _content = _SCENARIO_CONTENT.get(name, _SCENARIO_CONTENT["simple_search"])
        request_text, resp_ok, resp_fail, ground_truth_text, expected_elems = _content
        response_text = resp_ok if success else resp_fail

        monitor.record_task(
            task,
            ground_truth=ground_truth_text,
            context=ground_truth_text,
            request=request_text,
            response=response_text,
        )

        # Response Quality — 5차원 품질 평가 (성공 시 expected_elements 기반)
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=response_text,
            request=request_text,
            expected_elements=expected_elems if success else [],
            ground_truth=ground_truth_text,
        )

        # Accuracy — ground_truth 대비 정확도 명시적 평가
        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=ground_truth_text,
            prediction=response_text,
            task_type=task.task_type,
        )

        if has_wf:
            monitor.record_rag_metrics(
                faithfulness=round(min(accuracy * rng.uniform(0.80, 1.05), 1.0), 3),
                answer_relevancy=round(min(accuracy * rng.uniform(0.85, 1.10), 1.0), 3),
                context_precision=round(min(completion * rng.uniform(0.75, 1.00), 1.0), 3),
                context_recall=round(min(completion * rng.uniform(0.70, 1.05), 1.0), 3),
            )

    # ─── 추가: 직접 retry tracker 에 시나리오 등록 ───────────────────────────
    # record_task는 attempts>1이면 retry_tracker에 등록
    # 더 다양한 패턴을 위해 직접 등록도 추가
    extra_retry_cases = [
        ("retry_ext_001", [{"success": False, "duration": 1.2}, {"success": False, "duration": 1.5}, {"success": True, "duration": 0.9}], "qa"),
        ("retry_ext_002", [{"success": False, "duration": 2.0}, {"success": True, "duration": 1.1}], "reasoning"),
        ("retry_ext_003", [{"success": True, "duration": 0.7}], "qa"),
        ("retry_ext_004", [{"success": False, "duration": 3.0}, {"success": False, "duration": 2.5}, {"success": False, "duration": 2.0}], "tool_use"),
        ("retry_ext_005", [{"success": False, "duration": 1.0}, {"success": True, "duration": 0.8}], "reasoning"),
    ]
    for tid, log, ttype in extra_retry_cases:
        monitor.retry_tracker.track_attempts(tid, log, task_type=ttype)

    # ─── 추가: ToolCallAnalyzer 직접 호출 — 효율성 점수 케이스별 검증 ──────────
    # record_task는 tool_calls 필드가 있으면 analyze_execution()을 자동 호출하지만
    # 아래처럼 직접 호출하면 반환된 dict에서 케이스별 점수를 직접 확인할 수 있다.
    direct_tool_cases = [
        # (task_id, tool_calls, 설명)
        # 정상 단일 호출 — 효율성 100에 가까워야 함
        ("tool_direct_001",
         [{"name": "web_search", "tool_name": "web_search", "success": True,  "duration": 0.3}],
         "단일 성공 호출 (효율성 최고)"),
        # 중복 없는 3-도구 체인
        ("tool_direct_002",
         [{"name": "data_query",  "tool_name": "data_query",  "success": True,  "duration": 0.5},
          {"name": "classifier",  "tool_name": "classifier",  "success": True,  "duration": 0.4},
          {"name": "chart_gen",   "tool_name": "chart_generator","success": True,"duration": 0.6}],
         "3-도구 체인, 중복 없음"),
        # 중복 호출 포함 — 효율성 낮아야 함
        ("tool_direct_003",
         [{"name": "web_search", "tool_name": "web_search", "success": True,  "duration": 0.3},
          {"name": "web_search", "tool_name": "web_search", "success": True,  "duration": 0.3},  # 중복
          {"name": "summarizer", "tool_name": "summarizer", "success": True,  "duration": 0.4}],
         "web_search 중복 호출"),
        # 실패 포함 — 효율성 낮아야 함
        ("tool_direct_004",
         [{"name": "code_executor", "tool_name": "code_executor", "success": False, "duration": 2.0},
          {"name": "code_executor", "tool_name": "code_executor", "success": False, "duration": 2.5},
          {"name": "code_executor", "tool_name": "code_executor", "success": True,  "duration": 1.2}],
         "2회 실패 후 성공"),
        # 완전 실패 체인
        ("tool_direct_005",
         [{"name": "db_lookup",   "tool_name": "db_lookup",   "success": False, "duration": 1.0},
          {"name": "data_query",  "tool_name": "data_query",  "success": False, "duration": 1.5}],
         "전체 실패 체인"),
        # 빈 호출 — 효율성 100 반환해야 함
        ("tool_direct_006",
         [],
         "도구 호출 없음 (효율성 100)"),
    ]

    print(f"\n  [직접 ToolCallAnalyzer 호출 — 케이스별 효율성 점수]")
    for tid, calls, desc in direct_tool_cases:
        result = monitor.tool_analyzer.analyze_execution(tid, calls)
        score       = result.get("efficiency_score", 0)
        total_calls = result.get("total_calls", 0)
        redundant   = result.get("redundant_calls", 0)
        failed      = result.get("failed_calls", 0)
        flag = "🟢" if score >= 80 else ("🟡" if score >= 50 else "🔴")
        print(f"    {flag} {tid}: score={score:.1f}/100  calls={total_calls}  "
              f"dup={redundant}  fail={failed}  ({desc})")

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[A]_agentic_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)
    html_path = Path(saved_path).with_suffix('.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"📄 HTML 리포트 저장: {html_path}")

    # ─── 결과 출력 ────────────────────────────────────────────────────────────
    eff_data    = report.efficiency_metrics.get("tool_efficiency", {})
    retry_data  = report.efficiency_metrics.get("retries", {})

    tool_sel    = monitor.tool_selection_tracker.get_accuracy_stats()
    coord       = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow    = monitor.workflow_tracker.calculate_execution_success_rate()

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개  (+{len(extra_retry_cases)} retry 직접 등록)")
    print(f"  저장 위치: {saved_path}")

    print(f"\n  [Tool Call Analysis]")
    if eff_data:
        print(f"    효율성 점수:   {eff_data.get('avg_efficiency_score', 0):.1f}/100")
        print(f"    중복 호출률:   {eff_data.get('redundancy_rate', 0):.1f}%")
        print(f"    실패율:        {eff_data.get('failure_rate', 0):.1f}%")
        print(f"    총 호출:       {eff_data.get('total_calls', 0)}회")

    print(f"\n  [Tool Selection Accuracy — F1]")
    if tool_sel:
        print(f"    Precision:     {tool_sel.get('avg_precision', 0):.1f}%")
        print(f"    Recall:        {tool_sel.get('avg_recall', 0):.1f}%")
        print(f"    F1 Score:      {tool_sel.get('avg_f1_score', tool_sel.get('avg_accuracy', 0)):.1f}%")
        print(f"    평가 태스크:   {tool_sel.get('total_evaluations', 0)}개")

    print(f"\n  [Agent Coordination]")
    if coord:
        patterns = monitor.agent_coordination_tracker.get_interaction_patterns()
        print(f"    협업 점수:     {coord.get('score', 0):.2f}/10")
        print(f"    성공률:        {coord.get('success_rate', 0):.1f}%")
        print(f"    총 상호작용:   {coord.get('total_interactions', 0)}회")
        print(f"    에이전트 수:   {coord.get('unique_agents', 0)}개")
        print(f"    패턴:          {patterns.get('pattern_type', 'N/A')}")

    print(f"\n  [Workflow Execution]")
    if workflow:
        print(f"    단계 성공률:   {workflow.get('step_success_rate', 0):.1f}%")
        print(f"    태스크 성공률: {workflow.get('task_success_rate', 0):.1f}%")
        print(f"    총 단계:       {workflow.get('total_steps', 0)}개")
        print(f"    성공 단계:     {workflow.get('successful_steps', 0)}개")

    print(f"\n  [Retry & Correction]")
    if retry_data:
        print(f"    재시도율:      {retry_data.get('retry_rate', 0):.1f}%")
        print(f"    첫시도 성공률: {retry_data.get('first_attempt_success_rate', 0):.1f}%")
        print(f"    수정 성공률:   {retry_data.get('correction_success_rate', 0):.1f}%")

    if report.alerts:
        print(f"\n  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:3]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")

    # ─── 검증 테이블 ─────────────────────────────────────────────────────────
    eff_score    = eff_data.get("avg_efficiency_score", 0) if eff_data else 0
    redundancy   = eff_data.get("redundancy_rate", 0) if eff_data else 0
    tool_f1      = tool_sel.get("avg_f1_score", tool_sel.get("avg_accuracy", 0)) if tool_sel else 0
    coord_score  = coord.get("score", 0) if coord else 0
    coord_suc    = coord.get("success_rate", 0) if coord else 0
    wf_step_suc  = workflow.get("step_success_rate", 0) if workflow else 0
    wf_task_suc  = workflow.get("task_success_rate", 0) if workflow else 0
    retry_m      = monitor.retry_tracker.get_retry_metrics()
    first_suc    = retry_m.get("first_attempt_success_rate", 0)

    # direct_tool_cases 검증: 중복 호출 케이스(003)의 효율성이 정상 케이스(001)보다 낮아야 함
    res_normal   = monitor.tool_analyzer.analyze_execution("val_normal",
        [{"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3}])
    res_dup      = monitor.tool_analyzer.analyze_execution("val_dup",
        [{"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3},
         {"name": "web_search", "tool_name": "web_search", "success": True, "duration": 0.3}])
    dup_separation = res_normal.get("efficiency_score", 0) > res_dup.get("efficiency_score", 0)

    checks = [
        #  항목                               기준           실제값                     통과
        ("Tool Call 효율성 점수",             "> 50/100",  f"{eff_score:.1f}",          eff_score > 50),
        ("중복 호출률",                        "< 30%",     f"{redundancy:.1f}%",        redundancy < 30.0),
        ("Tool Selection F1",                 "> 50%",     f"{tool_f1:.1f}%",           tool_f1 > 50.0),
        ("Agent Coordination 점수",           "> 5/10",    f"{coord_score:.2f}",        coord_score > 5.0),
        ("Agent Coordination 성공률",         "> 70%",     f"{coord_suc:.1f}%",         coord_suc > 70.0),
        ("Workflow 단계 성공률",              "> 70%",     f"{wf_step_suc:.1f}%",       wf_step_suc > 70.0),
        ("Workflow 태스크 성공률",            "> 50%",     f"{wf_task_suc:.1f}%",       wf_task_suc > 50.0),
        ("첫시도 성공률 (직접 retry 포함)",   "> 5%",      f"{first_suc:.1f}%",         first_suc > 5.0),
        ("중복 호출 효율성 점수 분리",         "정상>중복", str(dup_separation),         dup_separation),
    ]

    print(f"\n  {'═'*66}")
    print(f"  {'검증 항목':<32} {'기준':<12} {'실측값':<12} {'결과'}")
    print(f"  {'─'*66}")
    pass_cnt = 0
    for name, threshold, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok: pass_cnt += 1
        print(f"  {name:<32} {threshold:<12} {actual:<12} {mark}")
    print(f"  {'═'*66}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    print(f"{'─'*70}\n")
    return saved_path


def run_tool_selection_golden_demo():
    """
    Golden Dataset 파일 기반 Tool Selection 정확도 평가 데모
    ─────────────────────────────────────────────────────────
    results/golden_datasets/agentic_tool_selection.json 을 로드하고
    ToolSelectionTracker 로 F1 기반 정확도를 측정합니다.

    각 항목의 expected_tools 와 시뮬레이션 agent 가 반환하는
    actual_tools 를 비교합니다.
    """
    import json

    print("\n" + "=" * 70)
    print("  Tool Selection Golden Dataset 평가 데모")
    print("  파일: results/golden_datasets/agentic_tool_selection.json")
    print("=" * 70)

    golden_path = project_root / "results" / "golden_datasets" / "agentic_tool_selection.json"
    if not golden_path.exists():
        print(f"\n⚠️  Golden Dataset 파일이 없습니다: {golden_path}")
        return

    with open(golden_path, encoding="utf-8") as f:
        golden_items = json.load(f)

    rng = random.Random(7777)
    monitor = PerformanceMonitor(output_dir=str(project_root / "results"))

    print(f"\n  총 {len(golden_items)}개 시나리오 평가 중...\n")

    for item in golden_items:
        task_id = f"golden_{item['qa_id']}"
        expected = item["expected_tools"]

        # 시뮬레이션: 난이도에 따라 도구 선택 정확도 조절
        difficulty = item.get("difficulty", "medium")
        if difficulty == "easy":
            match_prob = 0.95
        elif difficulty == "medium":
            match_prob = 0.80
        else:  # hard
            match_prob = 0.65

        # 실제 도구 = expected를 기반으로 일부 추가/제거 (시뮬레이션)
        actual = list(expected)
        if rng.random() > match_prob:
            # 일부 도구를 잘못 선택
            all_available = list(ALL_TOOLS)
            wrong = rng.choice([t for t in all_available if t not in expected])
            if actual:
                actual[-1] = wrong  # 마지막 도구를 잘못된 도구로 교체

        success = set(actual) == set(expected)
        completion = 1.0 if success else rng.uniform(0.4, 0.8)

        tool_calls = [
            {"name": t, "tool_name": t, "success": True, "execution_time": rng.uniform(0.1, 0.5)}
            for t in actual
        ]

        task = TaskResult(
            task_id=task_id,
            task_type=item.get("task_type", "tool_use"),
            success=success,
            completion_score=round(completion, 3),
            accuracy_score=round(completion, 3),
            execution_time=round(rng.uniform(0.5, 5.0), 3),
            tokens_used={"input": rng.randint(100, 500), "output": rng.randint(50, 300), "total": 0},
            tool_calls=tool_calls,
            attempts=1,
            errors=[] if success else ["wrong_tool_selected"],
            timestamp=datetime.now(),
            expected_tools=expected,
            framework="crewai",
        )
        task.tokens_used["total"] = task.tokens_used["input"] + task.tokens_used["output"]

        monitor.record_task(
            task,
            ground_truth=item["ground_truth"],
            request=item["question"],
            response="작업 완료" if success else "도구 선택 오류",
        )

        # Tool Selection Tracker 에 직접 등록
        monitor.tool_selection_tracker.evaluate_selection(
            task_id=task_id,
            expected_tools=expected,
            actual_tools=actual,
        )

        match_icon = "✅" if success else "⚠️ "
        print(f"  {match_icon} {item['qa_id']:<20} expected={expected}  actual={actual}")

    # 결과 출력
    tool_sel = monitor.tool_selection_tracker.get_accuracy_stats()
    print(f"\n{'─'*70}")
    print(f"  [Tool Selection 골든 데이터셋 평가 결과]")
    if tool_sel:
        print(f"    Precision : {tool_sel.get('avg_precision', 0):.1f}%")
        print(f"    Recall    : {tool_sel.get('avg_recall', 0):.1f}%")
        print(f"    F1 Score  : {tool_sel.get('avg_f1_score', tool_sel.get('avg_accuracy', 0)):.1f}%")
        print(f"    평가 건수 : {tool_sel.get('total_evaluations', 0)}건")
    print(f"{'─'*70}\n")


def run_transparency_demo(monitor: PerformanceMonitor, saved_path: str):
    """
    투명성 데모 — Traces / Annotations / Audit Log 생성
    ────────────────────────────────────────────────────
    TestTransparencyManager를 사용해 평가 계산 과정을 추적하고
    어노테이션·감사 로그를 남깁니다.

    생성 파일:
      results/traces/          → 지표 계산 단계별 트레이스 JSON
      results/annotations/     → 검토 메모·경고 JSON
      results/audit_logs/      → 이벤트 감사 로그 JSON
    """
    print("\n" + "=" * 70)
    print("  투명성 데모 — Traces · Annotations · Audit Log")
    print("=" * 70)

    results_dir = str(project_root / "results")
    tm = TestTransparencyManager(output_dir=results_dir)

    report = monitor.generate_report()
    tool_sel = monitor.tool_selection_tracker.get_accuracy_stats()
    coord    = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow = monitor.workflow_tracker.calculate_execution_success_rate()

    # ── 1. Traces: 주요 지표 계산 과정 기록 ──────────────────────────────────

    # (1a) Tool Selection F1 트레이스
    f1_score = tool_sel.get("avg_f1_score", tool_sel.get("avg_accuracy", 0))
    trace_id = tm.start_metric_calculation(
        metric_name="tool_selection_f1",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="collect_selections",
        description="전체 태스크의 expected/actual tool 목록 수집",
        input_data={"total_tasks": report.total_tasks},
        output_data={"evaluations": tool_sel.get("total_evaluations", 0)},
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="compute_precision_recall",
        description="각 태스크별 Precision·Recall 계산 후 평균",
        input_data={"method": "set_intersection / union"},
        output_data={
            "avg_precision": tool_sel.get("avg_precision", 0),
            "avg_recall":    tool_sel.get("avg_recall", 0),
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id,
        step_name="compute_f1",
        description="F1 = 2 × (Precision × Recall) / (Precision + Recall)",
        input_data={
            "precision": tool_sel.get("avg_precision", 0),
            "recall":    tool_sel.get("avg_recall", 0),
        },
        output_data={"f1_score": round(f1_score, 2)},
        status=TestStepStatus.SUCCESS,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id,
        final_value=round(f1_score, 2),
        metadata={"unit": "%", "threshold": 70.0},
    )

    # (1b) Agent Coordination 트레이스
    coord_score = coord.get("score", 0) if coord else 0
    trace_id2 = tm.start_metric_calculation(
        metric_name="agent_coordination_score",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id2,
        step_name="collect_interactions",
        description="멀티 에이전트 상호작용 목록 수집",
        input_data={"agents": list(AGENTS.keys())},
        output_data={
            "total_interactions": coord.get("total_interactions", 0) if coord else 0,
            "unique_agents":      coord.get("unique_agents", 0) if coord else 0,
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id2,
        step_name="score_coordination",
        description="성공률·다양성·패턴 기반 0-10 점수 산출",
        input_data={"success_rate": coord.get("success_rate", 0) if coord else 0},
        output_data={"score": round(coord_score, 2)},
        status=TestStepStatus.SUCCESS,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id2,
        final_value=round(coord_score, 2),
        metadata={"unit": "/10", "threshold": 7.0},
    )

    # (1c) Workflow Execution 트레이스
    step_success = workflow.get("step_success_rate", 0) if workflow else 0
    trace_id3 = tm.start_metric_calculation(
        metric_name="workflow_step_success_rate",
        metric_type="agentic",
    )
    tm.add_calculation_step(
        trace_id=trace_id3,
        step_name="collect_steps",
        description="워크플로우 전체 단계 수집",
        input_data={"workflows": len(WORKFLOW_STEPS)},
        output_data={
            "total_steps":      workflow.get("total_steps", 0) if workflow else 0,
            "successful_steps": workflow.get("successful_steps", 0) if workflow else 0,
        },
        status=TestStepStatus.SUCCESS,
    )
    tm.add_calculation_step(
        trace_id=trace_id3,
        step_name="identify_bottlenecks",
        description="실행 시간 상위 단계 병목 탐지",
        input_data={"bottleneck_steps": ["data_retrieval", "analysis"]},
        output_data={"step_success_rate": round(step_success, 2)},
        status=TestStepStatus.SUCCESS if step_success >= 80 else TestStepStatus.FAILED,
    )
    tm.complete_metric_calculation(
        trace_id=trace_id3,
        final_value=round(step_success, 2),
        metadata={"unit": "%", "threshold": 85.0},
    )

    # ── 2. Annotations: 주목할 점 기록 ───────────────────────────────────────

    # 낮은 F1 경고
    if f1_score < 70:
        ann_id = tm.add_annotation(
            target_type="metric",
            target_id="tool_selection_f1",
            annotation_type=AnnotationType.WARNING,
            priority="high",
            title=f"Tool Selection F1 낮음 ({f1_score:.1f}%)",
            content=(
                f"Tool Selection F1이 {f1_score:.1f}%로 임계값(70%) 미달입니다. "
                "wrong_tool_* 시나리오에서 도구 미스매치가 빈번하게 발생했습니다. "
                "에이전트 도구 선택 로직 개선이 필요합니다."
            ),
            author="evaluator",
            metadata={"threshold": 70.0, "actual": round(f1_score, 2)},
        )
        tm.add_reply_to_annotation(
            annotation_id=ann_id,
            author="reviewer",
            content="wrong_tool_1, wrong_tool_2 시나리오 우선 검토 권장.",
        )

    # 워크플로우 병목 노트
    tm.add_annotation(
        target_type="metric",
        target_id="workflow_execution",
        annotation_type=AnnotationType.NOTE,
        priority="medium",
        title="data_retrieval · analysis 단계 병목 확인됨",
        content=(
            "워크플로우에서 data_retrieval·analysis 단계의 실행 시간이 "
            "다른 단계 대비 최대 3배 높습니다. "
            "병렬 실행 또는 캐싱 전략 도입을 검토하세요."
        ),
        author="evaluator",
    )

    # 전체 개선 제안
    tm.add_annotation(
        target_type="evaluation",
        target_id="agentic_metrics_run",
        annotation_type=AnnotationType.IMPROVEMENT,
        priority="low",
        title="redundant_calls 시나리오 — 중복 호출 제거 가능",
        content=(
            "redundant_calls_1·2 시나리오에서 동일 도구를 2회 이상 호출합니다. "
            "Tool Call Analyzer의 중복 탐지 결과를 에이전트 피드백 루프에 반영하면 "
            "토큰 비용과 실행 시간을 줄일 수 있습니다."
        ),
        author="evaluator",
    )

    # ── 3. Audit Log: 에이전틱 전용 세부 지표 (자동 생성 lifecycle 이벤트와 별개) ──

    tm.log_event(
        event_type="evaluation_started",
        user="evaluator",
        action="에이전틱 지표 평가 세션 시작",
        target_type="monitor",
        target_id="agentic_metrics_run",
        details={"scenarios": len(SCENARIOS), "trackers": ["tool_call", "tool_selection", "coordination", "workflow", "retry"]},
        success=True,
    )
    tm.log_event(
        event_type="report_generated",
        user="evaluator",
        action="평가 리포트 생성",
        target_type="report",
        target_id="agentic_metrics_run",
        details={
            "total_tasks":      report.total_tasks,
            "tool_selection_f1": round(f1_score, 2),
            "coord_score":       round(coord_score, 2),
            "step_success_rate": round(step_success, 2),
        },
        success=True,
    )
    tm.log_event(
        event_type="file_saved",
        user="evaluator",
        action="결과 파일 저장",
        target_type="file",
        target_id=str(saved_path),
        details={"format": "json", "path": str(saved_path)},
        success=bool(saved_path),
    )

    # ── 결과 요약 출력 ────────────────────────────────────────────────────────
    summary = tm.get_transparency_summary()
    print(f"\n  [Transparency 생성 결과]")
    print(f"    Traces     : {summary.get('total_traces', 0)}개  → {results_dir}/traces/")
    print(f"    Annotations: {summary.get('total_annotations', 0)}개  → {results_dir}/annotations/")
    print(f"    Audit Logs : {summary.get('total_audit_logs', 0)}개  → {results_dir}/audit_logs/")
    print(f"\n  대시보드 '투명성' 탭에서 Traces · Annotations · Audit Log를 확인하세요.")
    print(f"{'─'*70}\n")


if __name__ == "__main__":
    # enable_transparency=True → save_to_file() 시 Traces·Audit Log 자동 생성
    saved_path = run_agentic_evaluation()
    run_tool_selection_golden_demo()
    # Annotations 데모 (수동 입력 예시 — dashboard UI로도 작성 가능)
    _demo_monitor = PerformanceMonitor(output_dir=str(project_root / "results"))
    run_transparency_demo(_demo_monitor, saved_path)
