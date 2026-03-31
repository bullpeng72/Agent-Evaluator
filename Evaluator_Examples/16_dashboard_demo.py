"""
대시보드 3개 탭 통합 데모 — Agent Evaluator v0.6.5
===========================================================

이 예제 하나를 실행하면 대시보드의 세 가지 탭 데이터가 모두 채워집니다:

  📡 실시간 모니터링  — StreamingEvaluator 슬라이딩 윈도우 스냅샷
  👍 사용자 반응      — ImplicitFeedbackTracker 암묵적 피드백 50건
  🗂️ 케이스 검토      — GoldenSetBuilder 후보 추출 → 병합 워크플로우

실행:
    python 16_dashboard_demo.py        # API 키 불필요
    agent-eval dashboard --port 8765   # 대시보드 확인
"""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

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
from agent_evaluator.datasets.builder import GoldenSetBuilder


# ─── 시뮬레이션 데이터 ────────────────────────────────────────────────────────

_TASKS = [
    # (question, response_ok, response_fail, ground_truth, task_type, quality)
    ("한국의 수도는?",           "서울입니다.",                  "잘 모르겠습니다.",               "서울",             "qa",            "high"),
    ("Python 리스트 컴프리헨션?", "[x*2 for x in range(10)]",  "모르겠습니다.",                  "리스트 생성 문법",  "code_generation","high"),
    ("REST API란?",             "HTTP 기반 웹 서비스 원칙.",     "어려운 개념입니다.",              "HTTP 서비스 설계", "qa",            "high"),
    ("Docker와 VM 차이?",        "커널 공유 vs 전체 OS.",        "비슷한 것입니다.",               "컨테이너 vs 하이퍼바이저","qa",       "high"),
    ("머신러닝이란?",            "데이터로부터 패턴 학습.",        "인공지능의 한 종류입니다.",       "데이터 기반 학습", "qa",            "med"),
    ("CI/CD란?",                "지속적 통합·배포 자동화.",       "개발 방법론입니다.",              "자동화 파이프라인","qa",           "high"),
    ("JWT 토큰 구조?",           "Header.Payload.Signature",    "암호화 방식입니다.",              "3-part 구조",      "qa",            "high"),
    ("SQL JOIN 종류?",           "INNER, LEFT, RIGHT, FULL.",  "테이블 결합 방법.",               "4가지 JOIN",      "qa",            "high"),
    ("캐싱 전략이란?",           "LRU, LFU, TTL 기반 전략.",    "성능 최적화 방법.",               "캐시 교체 정책",   "qa",            "med"),
    ("마이크로서비스 장단점?",   "독립 배포·확장성 / 복잡성.",   "서비스 분리 방식입니다.",         "아키텍처 장단점",  "qa",            "med"),
    ("비동기 프로그래밍이란?",   "논블로킹 I/O 처리 방식.",     "await/async 사용.",              "논블로킹 처리",    "code_generation","high"),
    ("데이터베이스 인덱스란?",   "검색 속도 향상을 위한 자료구조.","빠른 검색 도구.",               "인덱스 원리",      "qa",            "high"),
    ("OAuth 2.0이란?",          "위임 권한 부여 프레임워크.",    "인증 방식입니다.",               "권한 위임 표준",   "qa",            "med"),
    ("쿠버네티스란?",            "컨테이너 오케스트레이션 플랫폼.","도커 관리 도구.",               "컨테이너 관리",    "qa",            "high"),
    ("CDN이란?",                "콘텐츠 전송 네트워크.",         "빠른 파일 배포.",                "지리 분산 캐시",   "qa",            "med"),
]

# 피드백 분포 (quality 수준별)
_FB_DIST = {
    "high": {"thumbs_up": 0.42, "copy": 0.22, "share": 0.10, "follow_up_depth": 0.12,
             "regenerate": 0.06, "thumbs_down": 0.04, "abandon": 0.02, "correction": 0.02},
    "med":  {"thumbs_up": 0.20, "copy": 0.12, "share": 0.05, "follow_up_depth": 0.05,
             "regenerate": 0.28, "thumbs_down": 0.15, "abandon": 0.10, "correction": 0.05},
    "low":  {"thumbs_up": 0.05, "copy": 0.03, "share": 0.00, "follow_up_depth": 0.00,
             "regenerate": 0.42, "thumbs_down": 0.28, "abandon": 0.15, "correction": 0.07},
}


def _feedback(monitor: PerformanceMonitor, task_id: str, quality: str, rng: random.Random) -> int:
    dist = _FB_DIST[quality]
    count = 0
    for fb_type, prob in dist.items():
        if rng.random() < prob:
            monitor.record_implicit_feedback(
                task_id=task_id,
                feedback_type=fb_type,
                metadata={"quality": quality, "demo": True},
            )
            count += 1
    return count


def run_dashboard_demo():
    print("\n" + "=" * 70)
    print("  대시보드 3개 탭 통합 데모 — Agent Evaluator v0.6.5")
    print("  📡 실시간  ·  👍 사용자 반응  ·  🗂️ 케이스 검토")
    print("=" * 70)

    rng = random.Random(20260331)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"[DB]_dashboard_demo_{ts}.json"

    # ── 1단계: evaluation_session + StreamingEvaluator ─────────────────────
    print(f"\n  [1단계] 📡 실시간 모니터링 — 50개 태스크 스트림")
    print(f"  {'─'*68}")

    with evaluation_session(
        filename,
        enable_hallucination=True,
        output_dir=str(results_dir),
    ) as monitor:

        streamer = StreamingEvaluator(monitor=monitor, flush_interval=30)
        streamer.start()

        base_time = datetime.now() - timedelta(minutes=50)
        n_tasks = 50
        fb_total = 0

        print(f"  {'태스크':<22} {'성공':>5}  {'지연ms':>7}  {'피드백':>6}")
        print(f"  {'─'*22} {'─'*5}  {'─'*7}  {'─'*6}")

        for i in range(n_tasks):
            tmpl = _TASKS[i % len(_TASKS)]
            q, resp_ok, resp_fail, gt, ttype, quality = tmpl

            # 다양한 성공률: high=90%, med=72%, low=45%
            success_rate = {"high": 0.90, "med": 0.72, "low": 0.45}[quality]
            success = rng.random() < success_rate
            exec_ms = rng.uniform(100, 350) if success else rng.uniform(700, 2200)
            tokens = rng.randint(60, 300) if success else rng.randint(15, 80)
            acc_score = rng.uniform(0.75, 0.97) if success else rng.uniform(0.08, 0.38)

            task_id = f"demo_{i+1:03d}"
            task = create_taskresult(
                task_id=task_id,
                question=q,
                response=resp_ok if success else resp_fail,
                ground_truth=gt,
                execution_time=round(exec_ms / 1000, 3),
                task_type=ttype,
                has_error=not success,
            )
            monitor.record_task(task)

            # StreamingEvaluator 실시간 기록
            streamer.record(
                task_id=task_id,
                success=success,
                execution_time=exec_ms / 1000,
                tokens_used=tokens,
                accuracy_score=acc_score,
                has_error=not success,
            )

            # 2단계: 사용자 피드백 기록 (품질 기반)
            fb_count = _feedback(monitor, task_id, quality, rng)
            fb_total += fb_count

            icon = "✅" if success else "❌"
            print(f"  {icon} {task_id:<20} {str(success):>5}  {exec_ms:>6.0f}ms  {fb_count:>6}건")

        streamer.stop()

        # 슬라이딩 윈도우 스냅샷 → JSON에 저장 (대시보드 '📡 실시간' 탭 히스토리)
        monitor._streaming_snapshot = streamer.get_all_stats()

    # ── 슬라이딩 윈도우 요약 출력 ──────────────────────────────────────────
    print(f"\n  [📡 실시간 스냅샷 저장 완료]")
    for window in ("1m", "5m", "1h"):
        stats = streamer.get_stats(window)
        count = stats.get("count", 0)
        if count == 0:
            print(f"  [{window}] 데이터 없음")
            continue
        print(
            f"  [{window}]  n={count}  TCR={stats.get('tcr', 0):.1f}%  "
            f"avg={stats.get('avg_latency', 0)*1000:.0f}ms  "
            f"p95={stats.get('p95_latency', 0)*1000:.0f}ms  "
            f"err={stats.get('error_rate', 0):.1f}%"
        )

    # ── 사용자 반응 요약 ───────────────────────────────────────────────────
    print(f"\n  [👍 사용자 반응 요약]")
    fb_stats = monitor.feedback_tracker.get_stats()
    print(f"  총 피드백: {fb_stats.get('total', 0)}건  "
          f"긍정: {fb_stats.get('positive_rate', 0):.1f}%  "
          f"부정: {fb_stats.get('negative_rate', 0):.1f}%  "
          f"재생성률: {fb_stats.get('regenerate_rate', 0):.1f}%")
    dist = fb_stats.get("type_distribution", {})
    for fb_type, cnt in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(cnt / max(dist.values(), default=1) * 20)
        print(f"    {fb_type:<20}: {cnt:>3}건  {bar}")

    # ── 3단계: 케이스 검토 (GoldenSetBuilder) ─────────────────────────────
    print(f"\n  [3단계] 🗂️ 케이스 검토 — GoldenSetBuilder")
    print(f"  {'─'*68}")
    saved_json = results_dir / filename

    golden_dir = project_root / "data" / "golden_datasets"
    golden_dir.mkdir(parents=True, exist_ok=True)

    builder = GoldenSetBuilder(
        source_dir=str(results_dir),
        output_dir=str(golden_dir),
    )

    candidates = builder.extract(
        strategies=["failure_cases", "edge_cases", "coverage_gap"],
        max_cases=30,
        require_human_review=True,
    )
    print(f"  추출된 후보 케이스: {len(candidates)}건  "
          f"(failure + edge + coverage_gap)")

    cand_path = None
    golden_path = None
    if candidates:
        cand_path = builder.save_candidates(
            candidates,
            f"dashboard_demo_candidates_{ts}.json",
        )
        print(f"  후보 저장: {Path(cand_path).name}")

        # 후보 중 절반을 자동 승인하여 골든 셋에 병합
        approved = candidates[: max(1, len(candidates) // 2)]
        golden_path = builder.merge_to_golden(
            approved,
            version=f"v_demo_{ts}",
            output_name=f"dashboard_demo_golden_{ts}.json",
        )
        print(f"  골든 병합: {Path(golden_path).name}  ({len(approved)}건 승인)")

    # ── 검증 테이블 ───────────────────────────────────────────────────────
    import json as _json
    _d = {}
    if saved_json.exists():
        with open(saved_json, encoding="utf-8") as _f:
            _d = _json.load(_f)

    feedback_ok  = _d.get("feedback", {}).get("total", 0) > 0
    streaming_ok = bool(_d.get("streaming_data"))
    golden_ok    = golden_path is not None and Path(golden_path).exists()

    checks = [
        ("50개 태스크 평가 완료",          f"{n_tasks}건",                  n_tasks == 50),
        ("📡 streaming_data 파일 저장",    str(streaming_ok),               streaming_ok),
        ("📡 1h 윈도우 데이터 존재",       f"{streamer.get_stats('1h').get('count',0)}건", streamer.get_stats("1h").get("count", 0) > 0),
        ("👍 피드백 기록",                 f"{fb_stats.get('total',0)}건",   fb_stats.get("total", 0) > 0),
        ("👍 긍정/부정 피드백 모두 존재",  f"{fb_stats.get('positive_count',0)}/{fb_stats.get('negative_count',0)}", fb_stats.get("positive_count", 0) > 0 and fb_stats.get("negative_count", 0) > 0),
        ("👍 feedback_data 파일 저장",     str(feedback_ok),                feedback_ok),
        ("🗂️ 후보 케이스 추출",            f"{len(candidates)}건",           len(candidates) > 0),
        ("🗂️ 후보 파일 저장",              str(cand_path is not None),       cand_path is not None),
        ("🗂️ 골든 셋 병합",               str(golden_ok),                   golden_ok),
        ("결과 JSON 자동 저장",            saved_json.name,                  saved_json.exists()),
    ]

    print(f"\n  {'═'*68}")
    print(f"  {'검증 항목':<35} {'실측값':<20} 결과")
    print(f"  {'─'*68}")
    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<35} {actual:<20} {mark}")
    print(f"  {'═'*68}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    # ── 대시보드 실행 안내 ─────────────────────────────────────────────────
    print(f"  {'─'*68}")
    print(f"  ✅ 대시보드 실행 방법:")
    print(f"       agent-eval dashboard --port 8765")
    print(f"  → http://localhost:8765")
    print(f"")
    print(f"  각 탭 확인 위치:")
    print(f"    📡 실시간 모니터링  : 좌측 메뉴 → '📡 실시간' 탭")
    print(f"       · 라이브 모드: 서버 실행 중 StreamingEvaluator 연결 시")
    print(f"       · 히스토리 모드: GET /api/stream/snapshot/{{file_id}}")
    print(f"    👍 사용자 반응      : 좌측 메뉴 → '👍 사용자 반응' 탭")
    print(f"       · 파일 선택 후 피드백 분포 차트 확인")
    print(f"       · API: GET /api/feedback/{{file_id}}")
    print(f"    🗂️ 케이스 검토      : 좌측 메뉴 → '🗂️ 케이스 검토' 탭")
    print(f"       · 후보 파일 로드 → 승인/거부 → 골든 셋 병합")
    print(f"       · API: POST /api/golden/candidates/{{name}}/approve/{{idx}}")
    print(f"  {'─'*68}")
    print(f"  📄 결과 파일: {saved_json.name}")
    if cand_path:
        print(f"  📋 후보 파일: {Path(cand_path).name}")
    if golden_path:
        print(f"  🏅 골든 파일: {Path(golden_path).name}")
    print()

    return str(saved_json)


if __name__ == "__main__":
    run_dashboard_demo()
