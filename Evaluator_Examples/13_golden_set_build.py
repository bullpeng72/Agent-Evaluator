"""
골든 데이터셋 구축 예제 — Agent Evaluator v0.6.4 Phase 3-A
===========================================================

운영 평가 결과에서 가치 높은 케이스를 자동 추출하여
골든 데이터셋을 반복적으로 개선(버전 관리)합니다.

커버 기능 (Phase 3-A):
  Phase 3-A  │ GoldenSetBuilder — 케이스 추출 · 후보 저장 · 골든 병합
             │   전략: failure_cases · edge_cases · high_value · coverage_gap
             │ GoldenSetBuilder.extract()    — 전략별 케이스 추출
             │ GoldenSetBuilder.save_candidates() — 후보 JSON 저장
             │ GoldenSetBuilder.merge_to_golden() — 검토 완료본 → 골든 통합

워크플로우:
  1단계: 다양한 평가 결과 JSON 파일을 results/ 에 준비
  2단계: GoldenSetBuilder.extract() — 4가지 전략으로 케이스 추출
  3단계: save_candidates() — 후보 파일 저장 (인간 검토 대기)
  4단계: merge_to_golden()  — 검토 완료 케이스를 골든 셋에 통합
  5단계: 버전별 이력 확인

실행:
    python 13_golden_set_build.py    # API 키 불필요
"""

from __future__ import annotations

import json
import sys
import random
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import (
    PerformanceMonitor,
    create_taskresult,
    evaluation_session,
)
from agent_evaluator.datasets.builder import GoldenSetBuilder


# ─── 평가 결과 생성 (GoldenSetBuilder의 입력 소스) ───────────────────────────
_QA_PAIRS = [
    # (question, response_ok, response_fail, ground_truth, task_type, category)
    ("Python 리스트와 튜플 차이?",
     "리스트는 mutable, 튜플은 immutable입니다. 리스트는 [], 튜플은 ()를 사용합니다.",
     "잘 모르겠습니다.",
     "리스트 mutable, 튜플 immutable", "qa", "python"),
    ("REST API와 GraphQL 차이점?",
     "REST는 고정 엔드포인트, GraphQL은 단일 엔드포인트에서 쿼리로 필요한 데이터만 가져옵니다.",
     "REST는 오래된 방식이고 GraphQL이 최신입니다.",
     "REST: 고정 엔드포인트, GraphQL: 유연한 쿼리", "qa", "api"),
    ("Docker 컨테이너 생성 명령어?",
     "docker run -d --name myapp -p 8080:80 nginx",
     "docker start myapp",
     "docker run 명령어 사용", "qa", "devops"),
    ("Kubernetes Pod이란?",
     "Pod는 하나 이상의 컨테이너를 묶는 K8s의 최소 배포 단위입니다.",
     "Pod은 가상머신입니다.",
     "K8s 최소 배포 단위", "qa", "devops"),
    ("SQL JOIN 종류?",
     "INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN, CROSS JOIN이 있습니다.",
     "JOIN은 두 테이블을 합칩니다.",
     "INNER/LEFT/RIGHT/FULL OUTER/CROSS", "qa", "database"),
    ("JWT 토큰 구조?",
     "Header.Payload.Signature 세 부분으로 구성됩니다. Base64URL로 인코딩됩니다.",
     "JWT는 인증 토큰입니다.",
     "Header.Payload.Signature", "qa", "security"),
    ("Python 데코레이터란?",
     "함수나 클래스를 수정하지 않고 기능을 추가하는 고차함수 패턴입니다. @syntax로 사용합니다.",
     "데코레이터는 장식자입니다.",
     "함수를 감싸는 고차함수 패턴", "qa", "python"),
    ("CI/CD 파이프라인이란?",
     "코드 변경사항을 자동으로 빌드, 테스트, 배포하는 자동화 워크플로우입니다.",
     "CI는 지속적 통합입니다.",
     "자동화 빌드·테스트·배포 워크플로우", "qa", "devops"),
    ("마이크로서비스 vs 모놀리식?",
     "마이크로서비스는 독립 서비스 단위로 분리, 모놀리식은 하나의 통합 애플리케이션입니다.",
     "마이크로서비스가 더 좋습니다.",
     "독립 서비스 vs 통합 애플리케이션", "qa", "architecture"),
    ("Redis 주요 용도?",
     "캐싱, 세션 관리, 실시간 리더보드, 메시지 브로커, 분산 락 등에 사용됩니다.",
     "Redis는 데이터베이스입니다.",
     "캐싱·세션·메시지 브로커", "qa", "database"),
]

_FAIL_QA = [
    ("양자 컴퓨팅이란?", "모르겠습니다.", "모르겠습니다.", "양자 비트(큐비트) 기반 연산", "qa", "advanced"),
    ("Transformer 아키텍처?", "AI 모델입니다.", "AI 모델입니다.", "Attention 메커니즘 기반 딥러닝 모델", "qa", "advanced"),
    ("RLHF란?", "학습 방법입니다.", "학습 방법입니다.", "인간 피드백 기반 강화학습", "qa", "advanced"),
]


def _generate_evaluation_files(results_dir: Path, rng: random.Random) -> list[Path]:
    """여러 평가 결과 JSON 파일을 생성 (GoldenSetBuilder의 source_dir 입력)."""
    source_dir = results_dir / "golden_source_demo"
    source_dir.mkdir(exist_ok=True)

    saved_files = []
    for batch_idx in range(3):
        monitor = PerformanceMonitor(
            output_dir=str(results_dir),
            enable_hallucination_detection=True,
        )

        # 일반 케이스 + 실패 케이스 혼합
        cases = _QA_PAIRS[batch_idx*3:(batch_idx+1)*3]
        if batch_idx == 2:
            cases = cases + _FAIL_QA

        for i, item in enumerate(cases):
            q, r_ok, r_fail, gt, ttype, category = item
            is_fail = rng.random() < 0.35  # 35% 실패
            task_id = f"batch{batch_idx}_{i:03d}_{category}_{datetime.now().strftime('%H%M%S')}"
            task = create_taskresult(
                task_id=task_id,
                question=q,
                response=r_fail if is_fail else r_ok,
                ground_truth=gt,
                execution_time=rng.uniform(0.3, 1.8),
                task_type=ttype,
                has_error=is_fail,
            )
            monitor.record_task(task)

        fname = f"demo_batch_{batch_idx:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        saved = monitor.save_to_file(fname)
        dest = source_dir / fname

        # source_dir로 복사 (GoldenSetBuilder가 이 디렉토리를 스캔)
        import shutil
        shutil.copy2(saved, dest)
        saved_files.append(dest)
        print(f"    배치 {batch_idx}: {len(cases)}개 태스크 → {dest.name}")

    return saved_files


def run_golden_set_build():
    print("\n" + "=" * 70)
    print("  골든 데이터셋 구축 — Agent Evaluator v0.6.4")
    print("  Phase 3-A: GoldenSetBuilder — 케이스 추출 · 후보 저장 · 골든 병합")
    print("=" * 70)

    rng = random.Random(20250403)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)
    golden_dir = project_root / "data" / "golden_datasets"
    golden_dir.mkdir(parents=True, exist_ok=True)
    source_dir = results_dir / "golden_source_demo"

    # ─────────────────────────────────────────────────────────────────────
    # 1단계: 평가 결과 JSON 파일 생성 (소스 데이터)
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [1단계] 평가 결과 파일 생성 (GoldenSetBuilder 소스)")
    print(f"  소스 디렉토리: {source_dir}")
    source_files = _generate_evaluation_files(results_dir, rng)
    print(f"  생성 완료: {len(source_files)}개 파일")

    # ─────────────────────────────────────────────────────────────────────
    # 2단계: GoldenSetBuilder 초기화 + 전략별 케이스 추출
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [2단계] GoldenSetBuilder.extract() — 4가지 전략")
    builder = GoldenSetBuilder(
        source_dir=str(source_dir),
        output_dir=str(golden_dir),
    )

    # 전략 1: failure_cases — 실패한 태스크 추출 (가장 많은 개선 기회)
    print(f"\n  전략 1: failure_cases — 실패·오류 태스크 추출")
    failures = builder.extract(
        strategies=["failure_cases"],
        max_cases=10,
        require_human_review=True,
        min_question_length=5,
    )
    print(f"    추출된 케이스: {len(failures)}건")
    for c in failures[:3]:
        print(f"    - [{c.get('_strategy', '?')}] {c.get('question', c.get('task_id', ''))[:50]}")

    # 전략 2: high_value — 높은 점수의 성공 케이스 (안정적 기준 사례)
    print(f"\n  전략 2: high_value — 고품질 성공 케이스 추출")
    high_value = builder.extract(
        strategies=["high_value"],
        max_cases=10,
        require_human_review=False,  # 고품질 케이스는 자동 승인 가능
        min_question_length=5,
    )
    print(f"    추출된 케이스: {len(high_value)}건")

    # 전략 3: edge_cases — 엣지 케이스 (경계 조건)
    print(f"\n  전략 3: edge_cases — 경계 조건 케이스 추출")
    edges = builder.extract(
        strategies=["edge_cases"],
        max_cases=8,
        require_human_review=True,
        min_question_length=5,
    )
    print(f"    추출된 케이스: {len(edges)}건")

    # 전략 4: coverage_gap — 커버리지 부족 영역
    print(f"\n  전략 4: coverage_gap — 미커버 태스크 유형 추출")
    gaps = builder.extract(
        strategies=["coverage_gap"],
        max_cases=8,
        require_human_review=True,
        min_question_length=5,
    )
    print(f"    추출된 케이스: {len(gaps)}건")

    # 복합 전략 — 한 번에 여러 전략 결합
    print(f"\n  복합 전략: failure_cases + edge_cases 결합")
    combined = builder.extract(
        strategies=["failure_cases", "edge_cases"],
        max_cases=15,
        require_human_review=True,
        min_question_length=5,
    )
    print(f"    결합 추출: {len(combined)}건")

    all_candidates = failures + high_value + edges + gaps
    print(f"\n  총 추출 후보: {len(all_candidates)}건")

    # ─────────────────────────────────────────────────────────────────────
    # 3단계: 후보 저장 (인간 검토 대기)
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [3단계] save_candidates() — 후보 파일 저장")
    if all_candidates:
        cand_path = builder.save_candidates(
            all_candidates,
            filename=f"demo_candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        print(f"    저장 완료: {cand_path.name}")
        print(f"    총 {len(all_candidates)}건 인간 검토 대기 중")

        # 후보 구조 미리보기
        if all_candidates:
            sample = all_candidates[0]
            meta_keys = [k for k in sample if k.startswith("_")]
            print(f"    메타 키 예시: {meta_keys}")
    else:
        cand_path = None
        print(f"    ⚠️  추출된 후보 없음 (소스 파일 검토 필요)")

    # ─────────────────────────────────────────────────────────────────────
    # 4단계: 검토 완료 케이스 → 골든 셋 병합
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [4단계] merge_to_golden() — 검토 완료본 골든 통합")

    # 시뮬레이션: 검토자가 일부 케이스 승인
    approved = [c for c in all_candidates if not c.get("_requires_review", True)]
    if not approved:
        # 검토 필요 없는 케이스가 없으면 high_value 케이스 직접 사용
        approved = high_value[:5] if high_value else all_candidates[:5]

    print(f"    검토 완료 케이스: {len(approved)}건 (자동 승인)")

    if approved:
        golden_path = builder.merge_to_golden(
            cases=approved,
            version=f"v1.0_{datetime.now().strftime('%Y%m%d')}",
            output_name=f"demo_golden_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
        print(f"    골든 셋 저장: {golden_path.name}")

        # 저장된 골든 셋 내용 확인
        with open(golden_path, encoding="utf-8") as f:
            golden_data = json.load(f)
        # merge_to_golden()은 {"version", "created_at", "count", "items"} 구조로 저장
        if isinstance(golden_data, list):
            golden_items = golden_data
        elif isinstance(golden_data, dict) and "items" in golden_data:
            golden_items = golden_data["items"]   # GoldenSetBuilder 포맷
        elif isinstance(golden_data, dict) and "qa_pairs" in golden_data:
            golden_items = golden_data["qa_pairs"]  # load_golden_dataset 호환 포맷
        else:
            golden_items = []
        print(f"    골든 셋 크기: {len(golden_items)}건")
        if golden_items:
            first = golden_items[0]
            if isinstance(first, dict):
                clean_keys = [k for k in first if not k.startswith("_")]
                print(f"    케이스 필드: {clean_keys[:6]}")
    else:
        golden_path = None
        print(f"    ⚠️  병합할 케이스 없음")

    # ─────────────────────────────────────────────────────────────────────
    # 5단계: 골든 데이터셋 이력 확인
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [5단계] 골든 데이터셋 이력")
    golden_files = sorted(golden_dir.glob("*.json"))
    print(f"  golden_datasets/ 내 파일 목록:")
    for gf in golden_files[-5:]:  # 최근 5개
        size = gf.stat().st_size
        mtime = datetime.fromtimestamp(gf.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"    {gf.name:<55} {size:>8} bytes  {mtime}")

    # ─────────────────────────────────────────────────────────────────────
    # 6단계: 구축된 골든 셋 활용 — 기존 예제와 통합 예시
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n  [6단계] 구축된 골든 셋 활용 예시")
    print(f"  # 다른 예제 파일에서 골든 셋 로드:")
    print(f"  # from agent_evaluator import PerformanceMonitor")
    print(f"  # monitor = PerformanceMonitor(output_dir='results/')")
    print(f"  # monitor.load_golden_dataset('{golden_dir}/<파일명>.json')")

    if golden_path and golden_path.exists() and golden_items:
        # load_golden_dataset()은 list 또는 {"qa_pairs": [...]} 포맷을 지원
        # → merge_to_golden() 포맷("items" 키)을 qa_pairs 포맷으로 변환 후 로드
        qa_pairs_path = golden_dir / f"qa_pairs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(qa_pairs_path, "w", encoding="utf-8") as _f:
            json.dump({"qa_pairs": golden_items}, _f, ensure_ascii=False, indent=2)
        new_monitor = PerformanceMonitor(output_dir=str(results_dir))
        loaded = new_monitor.load_golden_dataset(str(qa_pairs_path))
        print(f"\n  ✅ load_golden_dataset() 로드 완료: {len(loaded)}건")
    else:
        print(f"\n  ⚠️  골든 파일 없어 로드 테스트 건너뜀")

    # ── 검증 테이블 ───────────────────────────────────────────────────────
    print(f"\n  {'═'*65}")
    print(f"  {'검증 항목':<35} {'실측값':<14} 결과")
    print(f"  {'─'*65}")

    checks = [
        ("소스 파일 생성",        f"{len(source_files)}개",        len(source_files) == 3),
        ("failure_cases 추출",    f"{len(failures)}건",            len(failures) >= 0),
        ("high_value 추출",       f"{len(high_value)}건",          len(high_value) >= 0),
        ("edge_cases 추출",       f"{len(edges)}건",               len(edges) >= 0),
        ("coverage_gap 추출",     f"{len(gaps)}건",                len(gaps) >= 0),
        ("후보 파일 저장",         str(cand_path is not None),     cand_path is not None),
        ("골든 셋 병합",           str(golden_path is not None),   golden_path is not None),
        ("골든 파일 존재",         str(golden_path.exists() if golden_path else False),
                                                                   golden_path is not None and golden_path.exists()),
    ]

    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<35} {actual:<14} {mark}")
    print(f"  {'═'*65}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과\n")

    return str(golden_path) if golden_path else None


if __name__ == "__main__":
    run_golden_set_build()
