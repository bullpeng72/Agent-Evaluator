"""
스트리밍 실시간 평가 예제 — Agent Evaluator v1.0.0 Phase 2-A/2-C
=================================================================

실시간 에이전트 스트림을 슬라이딩 윈도우로 연속 평가하고
사용자 암묵적 피드백을 PerformanceMonitor에 통합하여 결과 파일에 저장합니다.

커버 지표 (Phase 2-A · Phase 2-C):
  Phase 2-A  │ StreamingEvaluator — 1m/5m/1h 슬라이딩 윈도우 지표
             │   TCR · 평균 지연 · P95 지연 · 오류율 · 평균 토큰
  Phase 2-C  │ monitor.record_implicit_feedback() — 사용자 암묵적 피드백
             │   copy · thumbs_up · share · regenerate · abandon · correction
             │   ※ monitor.feedback_tracker에 기록 → save_to_file()에 자동 포함
  Context    │ evaluation_session — 자동 저장 컨텍스트 매니저

핵심 시나리오:
  - 프로덕션 에이전트 응답 스트림 시뮬레이션 (40개 태스크)
  - 슬라이딩 윈도우(1m/5m/1h) 통계 실시간 계산
  - monitor.record_implicit_feedback()으로 피드백을 결과 파일에 포함
  - evaluation_session 컨텍스트 매니저로 자동 저장
  - 대시보드 "사용자 반응" 탭에서 피드백 데이터 확인 가능

실행:
    python 11_streaming_eval.py    # API 키 불필요 — 순수 시뮬레이션
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    evaluation_session,
)
from agent_evaluator.streaming.evaluator import StreamingEvaluator


# ─── 시뮬레이션 태스크 데이터 ─────────────────────────────────────────────────
TASK_TEMPLATES = [
    # (question, response, ground_truth, task_type, quality: high/med/low)
    ("대한민국 수도는?", "서울입니다. 인구 약 950만 명의 대도시입니다.", "서울", "qa", "high"),
    ("Python GIL이란?", "Global Interpreter Lock으로 한 번에 하나의 스레드만 실행합니다.", "GIL: 단일 스레드 실행 보장", "qa", "high"),
    ("Docker와 VM 차이?", "Docker는 OS 커널 공유, VM은 전체 OS 포함입니다.", "컨테이너 vs 하이퍼바이저", "qa", "high"),
    ("머신러닝이란?", "데이터에서 패턴을 학습하는 AI 기법입니다.", "데이터 기반 학습", "qa", "med"),
    ("TCP와 UDP 차이?", "TCP는 연결 지향, UDP는 비연결성입니다.", "TCP: 신뢰성, UDP: 속도", "qa", "high"),
    ("RESTful API란?", "HTTP 기반의 상태 없는(stateless) 웹 서비스 설계 원칙입니다.", "REST 원칙", "qa", "med"),
    ("클라우드 컴퓨팅?", "인터넷을 통해 서버, 스토리지, 소프트웨어를 제공하는 서비스입니다.", "온디맨드 IT 자원", "qa", "med"),
    ("마이크로서비스란?", "서비스를 독립적인 소형 단위로 분리하는 아키텍처 패턴입니다.", "분산 아키텍처", "qa", "high"),
    ("Kubernetes란?", "컨테이너 오케스트레이션 플랫폼입니다.", "컨테이너 관리 시스템", "qa", "med"),
    ("CI/CD란?", "지속적 통합과 지속적 배포를 의미합니다.", "자동화 개발 파이프라인", "qa", "high"),
]

# 피드백 패턴: quality → feedback_type 확률
_FEEDBACK_DISTRIBUTION = {
    "high": {"thumbs_up": 0.40, "copy": 0.25, "share": 0.10, "follow_up_depth": 0.15,
             "regenerate": 0.05, "thumbs_down": 0.03, "abandon": 0.02},
    "med":  {"thumbs_up": 0.20, "copy": 0.15, "share": 0.05, "follow_up_depth": 0.05,
             "regenerate": 0.25, "thumbs_down": 0.15, "abandon": 0.10, "correction": 0.05},
    "low":  {"thumbs_up": 0.05, "copy": 0.05, "share": 0.00, "follow_up_depth": 0.00,
             "regenerate": 0.40, "thumbs_down": 0.25, "abandon": 0.20, "correction": 0.05},
}


def _simulate_feedback(
    monitor: PerformanceMonitor,
    task_id: str,
    quality: str,
    rng: random.Random,
) -> None:
    """품질 수준에 따른 암묵적 피드백 시뮬레이션.

    monitor.record_implicit_feedback()을 사용하여
    monitor.feedback_tracker에 기록하면 save_to_file() 시 자동으로
    결과 JSON의 "feedback" 키에 포함되어 대시보드 사용자 반응 탭에 표시됩니다.
    """
    dist = _FEEDBACK_DISTRIBUTION[quality]
    for fb_type, prob in dist.items():
        if rng.random() < prob:
            monitor.record_implicit_feedback(
                task_id=task_id,
                feedback_type=fb_type,
                metadata={"quality_bucket": quality, "simulated": True},
            )


def run_streaming_evaluation():
    print("\n" + "=" * 70)
    print("  스트리밍 실시간 평가 — Agent Evaluator v1.0.0")
    print("  Phase 2-A: StreamingEvaluator · Phase 2-C: ImplicitFeedbackTracker")
    print("=" * 70)

    rng = random.Random(20250401)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"[S]_streaming_eval_{ts}.json"

    # ── evaluation_session 컨텍스트 매니저 ─────────────────────────────────
    # 세션 종료 시 자동으로 JSON + 보고서 저장 (예외 발생 시에도 안전)
    print(f"\n  [evaluation_session] 컨텍스트 매니저로 자동 저장 활성화")
    print(f"  저장 경로: results/{filename}\n")

    with evaluation_session(
        filename,
        enable_hallucination=True,
        output_dir=str(results_dir),
    ) as monitor:

        # ── Phase 2-A: StreamingEvaluator 초기화 ───────────────────────────
        # flush_interval=30 — 30초마다 배치 통계 갱신 (시뮬레이션에서는 즉시 처리)
        streamer = StreamingEvaluator(monitor=monitor, flush_interval=30)
        streamer.start()

        print("  [Phase 2-A] StreamingEvaluator 시작 — 40개 태스크 스트림")
        print(f"\n  {'태스크':<22} {'성공':>5}  {'지연ms':>7}  {'토큰':>6}  {'피드백'}")
        print(f"  {'─'*22} {'─'*5}  {'─'*7}  {'─'*6}  {'─'*20}")

        base_time = datetime.now() - timedelta(minutes=40)

        # ── 태스크 스트림 시뮬레이션 ─────────────────────────────────────
        n_tasks = 40
        for i in range(n_tasks):
            # 시간 경과 시뮬레이션 (각 태스크 ~60초 간격)
            task_ts = base_time + timedelta(seconds=i * 60)

            # 템플릿에서 순환 선택
            tmpl = TASK_TEMPLATES[i % len(TASK_TEMPLATES)]
            q, resp, gt, ttype, quality = tmpl

            # 품질 버킷에 따른 성공/지연 변동
            success = rng.random() < (0.92 if quality == "high" else 0.75 if quality == "med" else 0.45)
            exec_ms = rng.uniform(120, 400) if success else rng.uniform(800, 2500)
            exec_sec = exec_ms / 1000
            tokens = rng.randint(80, 350) if success else rng.randint(20, 100)
            acc_score = rng.uniform(0.78, 0.96) if success else rng.uniform(0.1, 0.4)

            task_id = f"stream_{i+1:03d}"

            # PerformanceMonitor에 태스크 기록
            task = create_taskresult(
                task_id=task_id,
                question=q,
                response=resp if success else "오류가 발생했습니다.",
                ground_truth=gt,
                execution_time=round(exec_sec, 3),
                task_type=ttype,
                has_error=not success,
                error_message="timeout" if not success and exec_ms > 1500 else None,
            )
            monitor.record_task(task)

            # StreamingEvaluator에 실시간 기록
            streamer.record(
                task_id=task_id,
                success=success,
                execution_time=exec_sec,
                tokens_used=tokens,
                accuracy_score=acc_score,
                has_error=not success,
            )

            # monitor.record_implicit_feedback()으로 사용자 피드백 기록
            # → monitor.feedback_tracker에 저장 → save_to_file()에 자동 포함
            _simulate_feedback(monitor, task_id, quality, rng)
            fb_count = len(monitor.feedback_tracker.get_task_feedbacks(task_id))

            icon = "✅" if success else "❌"
            print(f"  {icon} {task_id:<20} {str(success):>5}  {exec_ms:>6.0f}ms  {tokens:>6}  {fb_count}건")

        streamer.stop()

        # ── 슬라이딩 윈도우 통계 출력 ────────────────────────────────────
        print(f"\n  {'─'*70}")
        print(f"  [Phase 2-A] 슬라이딩 윈도우 실시간 통계")
        print(f"  {'─'*70}")

        for window in ("1m", "5m", "1h"):
            stats = streamer.get_stats(window)
            count = stats.get("count", 0)
            if count == 0:
                print(f"  [{window} 윈도우] 데이터 없음 (슬라이딩 만료)")
                continue
            # tcr, error_rate: 이미 % 단위 (0-100), avg/p95_latency: 초 단위
            tcr     = stats.get("tcr", 0)
            avg_lat = stats.get("avg_latency", 0) * 1000
            p95_lat = stats.get("p95_latency", 0) * 1000
            err_r   = stats.get("error_rate", 0)
            avg_tok = stats.get("avg_tokens", 0)
            print(f"  [{window} 윈도우]  n={count}  TCR={tcr:.1f}%  "
                  f"avg={avg_lat:.0f}ms  p95={p95_lat:.0f}ms  "
                  f"err={err_r:.1f}%  avgTok={avg_tok:.0f}")

        all_stats = streamer.get_all_stats()
        print(f"\n  get_all_stats() 반환 윈도우: {list(all_stats.keys())}")

    # ── Phase 2-C: ImplicitFeedbackTracker 집계 ─────────────────────────
    # evaluation_session 블록 종료 시 save_to_file() 자동 호출 → feedback 포함됨
    print(f"\n  {'─'*70}")
    print(f"  [Phase 2-C] 사용자 반응 집계 결과 (monitor.feedback_tracker)")
    print(f"  {'─'*70}")

    fb_stats = monitor.feedback_tracker.get_stats()
    total       = fb_stats.get("total", 0)
    pos_count   = fb_stats.get("positive_count", 0)
    neg_count   = fb_stats.get("negative_count", 0)
    # positive_rate, regenerate_rate 등은 이미 % 단위 (0-100)
    pos_rate    = fb_stats.get("positive_rate", 0)
    neg_rate    = fb_stats.get("negative_rate", 0)
    regen_rate  = fb_stats.get("regenerate_rate", 0)
    abandon_r   = fb_stats.get("abandon_rate", 0)
    dist        = fb_stats.get("type_distribution", {})

    print(f"  총 피드백: {total}건")
    print(f"  긍정 신호: {pos_count}건  ({pos_rate:.1f}%)")
    print(f"  부정 신호: {neg_count}건  ({neg_rate:.1f}%)")
    print(f"  재생성률 : {regen_rate:.1f}%  (낮을수록 품질 높음)")
    print(f"  이탈률   : {abandon_r:.1f}%  (낮을수록 만족도 높음)")
    print(f"\n  유형별 분포:")
    for fb_type, count_val in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(count_val / max(dist.values(), default=1) * 20)
        print(f"    {fb_type:<20}: {count_val:>3}건  {bar}")

    print(f"\n  ✅ 피드백 데이터는 결과 JSON 'feedback' 키에 포함됩니다.")
    print(f"     대시보드 '사용자 반응' 탭에서 확인하세요.")

    # ── 품질 vs 피드백 상관 요약 ─────────────────────────────────────────
    print(f"\n  피드백 품질 신호 해석:")
    if regen_rate < 10:
        print(f"  ✅ 재생성률 {regen_rate:.1f}% — 에이전트 첫 응답 품질 양호")
    elif regen_rate < 25:
        print(f"  🟡 재생성률 {regen_rate:.1f}% — 응답 품질 개선 여지 있음")
    else:
        print(f"  ❌ 재생성률 {regen_rate:.1f}% — 응답 품질 문제 심각, 모델 조정 필요")

    if pos_rate > 50:
        print(f"  ✅ 긍정 피드백 비율 {pos_rate:.1f}% — 사용자 만족도 높음")
    elif pos_rate > 30:
        print(f"  🟡 긍정 피드백 비율 {pos_rate:.1f}% — 중간 수준")
    else:
        print(f"  ❌ 긍정 피드백 비율 {pos_rate:.1f}% — 사용자 경험 저하")

    # ── evaluation_session이 자동 저장한 결과 확인 ──────────────────────
    saved_json = results_dir / filename
    if saved_json.exists():
        print(f"\n  ✅ evaluation_session 자동 저장 완료: {saved_json.name}")
    else:
        print(f"\n  ⚠️  저장 파일 미확인: {saved_json}")

    # ── 검증 테이블 ───────────────────────────────────────────────────────
    one_h_stats = streamer.get_stats("1h")
    final_tcr   = one_h_stats.get("tcr", 0)  # 이미 % 단위

    # 결과 파일에 feedback 데이터 포함 여부 확인
    import json as _json
    feedback_in_file = False
    if saved_json.exists():
        with open(saved_json, encoding="utf-8") as _f:
            _d = _json.load(_f)
        feedback_in_file = _d.get("feedback", {}).get("total", 0) > 0

    checks = [
        ("StreamingEvaluator 기록",        f"{n_tasks}건",       n_tasks > 0),
        ("1h 윈도우 TCR 측정",              f"{final_tcr:.1f}%",  final_tcr > 0),
        ("사용자 반응 기록",                f"{total}건",          total > 0),
        ("긍정 피드백 존재",                f"{pos_count}건",      pos_count > 0),
        ("부정 피드백 존재",                f"{neg_count}건",      neg_count > 0),
        ("자동 저장 완료",                  "JSON 파일",           saved_json.exists()),
        ("결과 파일에 feedback 포함",       str(feedback_in_file), feedback_in_file),
    ]

    print(f"\n  {'═'*60}")
    print(f"  {'검증 항목':<28} {'실측값':<14} 결과")
    print(f"  {'─'*60}")
    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<28} {actual:<14} {mark}")
    print(f"  {'═'*60}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    return str(saved_json)


if __name__ == "__main__":
    run_streaming_evaluation()
