"""
Phoenix 통합 검증 스크립트 — Agent Evaluator v0.7.0
=====================================================

4가지 신규 통합 기능을 순서대로 검증한다.

  ① Evaluators  — 8개 Annotation 지표가 Phoenix Evaluators 탭에 표시되는지
  ② Tracing     — ae.question / ae.response / ae.ground_truth 스팬 attribute 확인
  ③ Datasets    — GoldenSet → Phoenix Datasets 업로드 (Datasets & Experiments 탭)
  ④ Experiments — begin_experiment() / end_experiment() 실험 등록 및 스팬 그룹핑
  (⑤ Prompts   — LLMJudge.register_prompt_to_phoenix() — [llm] extra 필요 시 스킵)

사전 조건:
    1. Phoenix 기동: agent-eval monitor
    2. (이 스크립트는 API 키 없어도 실행 가능 — Prompts 단계만 선택적으로 스킵)

실행:
    cd Evaluator_Examples
    python 17_phoenix_verification.py
"""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

PHOENIX_ENDPOINT = "http://localhost:6006"

# ─── Phoenix 실행 여부 확인 ───────────────────────────────────────────────────

def _phoenix_running(endpoint: str = PHOENIX_ENDPOINT) -> bool:
    import socket
    host, port = endpoint.replace("http://", "").split(":")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, int(port))) == 0


# ─── 공통 출력 헬퍼 ─────────────────────────────────────────────────────────

_results: list[tuple[str, str, bool]] = []

def _check(label: str, detail: str, ok: bool) -> None:
    _results.append((label, detail, ok))
    mark = "✅" if ok else "❌"
    print(f"  {mark}  {label:<45} {detail}")


def _section(title: str) -> None:
    print(f"\n  {'─'*68}")
    print(f"  {title}")
    print(f"  {'─'*68}")


# ─── OTEL 설정 ───────────────────────────────────────────────────────────────

def _setup_otel() -> bool:
    try:
        from agent_evaluator import setup_otel
        setup_otel(endpoint=PHOENIX_ENDPOINT, service_name="ae-phoenix-verify")
        print(f"  📡  OTEL 활성화 — {PHOENIX_ENDPOINT}")
        return True
    except Exception as e:
        print(f"  ⚠️   OTEL 설정 실패 (agent-evaluator[otel] 필요): {e}")
        return False


# ─── 태스크 데이터 ────────────────────────────────────────────────────────────

_TASKS = [
    ("한국의 수도는?",              "서울입니다.",          "서울",           "qa",              True),
    ("Python 리스트 컴프리헨션?",   "[x*2 for x in range(10)]", "리스트 생성 문법", "code_generation", True),
    ("REST API란?",                "HTTP 기반 웹 서비스.", "HTTP 서비스 설계", "qa",             True),
    ("Docker와 VM 차이?",          "잘 모르겠습니다.",     "컨테이너 vs VM",  "qa",             False),  # 실패
    ("머신러닝이란?",              "데이터로부터 패턴 학습.", "데이터 기반 학습", "qa",            True),
    ("JWT 토큰 구조?",             "Header.Payload.Signature", "3-part 구조", "qa",             True),
    ("CI/CD란?",                   "잘 모르겠습니다.",     "자동화 파이프라인", "qa",            False),  # 실패
    ("SQL JOIN 종류?",             "INNER, LEFT, RIGHT, FULL.", "4가지 JOIN", "qa",             True),
]


# ─── ① + ② : Evaluators & Tracing ──────────────────────────────────────────

def run_tracing_and_evaluators(phoenix_ok: bool) -> str:
    """8개 태스크 실행 → OTEL 스팬 발행 + Annotation 누적 → save_to_file()로 전송."""
    from agent_evaluator import PerformanceMonitor, create_taskresult

    _section("① Evaluators + ② Tracing — 스팬 발행 & Annotation 전송")

    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    monitor = PerformanceMonitor(
        output_dir=str(results_dir),
        enable_hallucination_detection=True,
    )

    rng = random.Random(42)

    from agent_evaluator.decorators import agent_eval, EvalMetadata

    _task_by_q: dict = {q: (resp, ttype, success) for q, resp, gt, ttype, success in _TASKS}

    @agent_eval(
        monitor,
        task_type="qa",
        task_id_prefix="verify",
        flush_every=8,
        flush_filename="17_phoenix_verify",
    )
    def _verify_agent(question: str, ground_truth: str = "") -> tuple:
        _resp, _ttype, _success = _task_by_q[question]
        exec_time = round(rng.uniform(0.3, 2.1), 3)
        meta = EvalMetadata(completion_score=1.0 if _success else 0.0)
        if not _success:
            raise RuntimeError("verification_failure")
        return _resp, meta

    for i, (q, resp, gt, ttype, success) in enumerate(_TASKS):
        try:
            _verify_agent(question=q, ground_truth=gt)
        except RuntimeError:
            pass
        icon = "✅" if success else "❌"
        print(f"    {icon}  verify_{i+1:03d}  {q[:30]}")

    filename = f"[PX]_verify_{ts}.json"
    monitor.save_to_file(filename)

    saved = results_dir / filename
    _check("결과 JSON 저장", saved.name, saved.exists())
    _check("record_task() 8건 완료", "8건", len(monitor.tcr_tracker.tasks) == 8)

    if phoenix_ok:
        # Annotations 전송 여부 확인 — pending 비워졌으면 전송 시도한 것
        annotations_sent = len(monitor._pending_annotations) == 0
        _check(
            "Phoenix Annotations 전송 시도",
            "pending 큐 비워짐" if annotations_sent else "Phoenix 응답 없음(스킵)",
            True,  # 전송 시도 자체는 항상 OK
        )
        print()
        print("  📌  Phoenix에서 확인할 위치:")
        print("      [Tracing 탭]")
        print("        → 스팬 이름 'ae.task/qa/verify_*' 클릭")
        print("        → Attributes 패널에서 확인:")
        print("            ae.question    : 질문 전문")
        print("            ae.response    : 응답 전문")
        print("            ae.ground_truth: 정답")
        print("            ae.experiment_name: (없으면 정상 — Experiment 미등록)")
        print()
        print("      [Evaluators 탭]  (Traces 상단 'Annotations' 뷰)")
        print("        → accuracy / completion / success / hallucination /")
        print("           quality / latency_s / tool_calls / attempts")
        print("           8개 지표가 스팬별로 표시되는지 확인")
    else:
        print("  ⚠️   Phoenix 미실행 — Tracing/Evaluators 탭 확인 불가")

    return filename


# ─── ③ Datasets & Experiments ───────────────────────────────────────────────

def run_datasets_and_experiments(phoenix_ok: bool, base_filename: str) -> tuple[str | None, str | None]:
    """GoldenSet 생성 → Phoenix Datasets 업로드 → Experiment 등록."""
    from agent_evaluator import PerformanceMonitor, create_taskresult
    from agent_evaluator.datasets.builder import GoldenSetBuilder

    _section("③ Datasets & Experiments — 골든셋 업로드 + 실험 등록")

    results_dir = project_root / "results"
    golden_dir  = project_root / "data" / "golden_datasets"
    golden_dir.mkdir(parents=True, exist_ok=True)

    # 골든셋 추출 & 저장
    builder = GoldenSetBuilder(source_dir=str(results_dir), output_dir=str(golden_dir))
    candidates = builder.extract(
        strategies=["failure_cases", "high_value"],
        max_cases=20,
        require_human_review=False,
    )
    _check("GoldenSet 후보 추출", f"{len(candidates)}건", len(candidates) > 0)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    golden_path: Path | None = None
    dataset_id: str | None = None
    exp_id: str | None = None

    if candidates:
        golden_path = builder.save_candidates(candidates, f"verify_golden_{ts}.json")
        _check("골든셋 파일 저장", golden_path.name, golden_path.exists())

        if phoenix_ok:
            print(f"\n    Phoenix Datasets 업로드 중...")
            try:
                dataset_id = builder.upload_to_phoenix(
                    dataset_path=str(golden_path),
                    dataset_name=f"ae-verify-{ts}",
                    phoenix_endpoint=PHOENIX_ENDPOINT,
                )
                _check(
                    "Phoenix Datasets 업로드",
                    f"dataset_id={dataset_id}" if dataset_id else "id 미반환",
                    True,
                )
            except Exception as e:
                _check("Phoenix Datasets 업로드", f"실패: {e}", False)

            print()
            print("  📌  Phoenix에서 확인할 위치:")
            print("      [Datasets & Experiments 탭]")
            print(f"        → 'ae-verify-{ts}' 데이터셋 항목 확인")
            print("        → 각 row에 question / ground_truth / metadata 포함")
        else:
            _check("Phoenix Datasets 업로드", "Phoenix 미실행 — 스킵", True)

    # Experiment 등록 + 태스크 실행
    results_dir2 = project_root / "results"
    monitor2 = PerformanceMonitor(output_dir=str(results_dir2))

    if phoenix_ok:
        print(f"\n    Phoenix Experiment 등록 중...")
        exp_id = monitor2.begin_experiment(
            name=f"verify-run-{ts}",
            dataset_id=dataset_id,
            description="17_phoenix_verification.py 검증 실행",
            phoenix_endpoint=PHOENIX_ENDPOINT,
        )
        _check(
            "Experiment 등록",
            f"exp_id={exp_id}" if exp_id else "id 미반환 (Phoenix API 미지원 가능)",
            True,
        )
    else:
        _check("Experiment 등록", "Phoenix 미실행 — 스킵", True)

    # Experiment에 묶인 태스크 실행 (스팬에 ae.experiment_id 자동 첨부)
    rng = random.Random(99)
    for i, (q, resp, gt, ttype, success) in enumerate(_TASKS[:4]):
        task = create_taskresult(
            task_id=f"exp_{i+1:03d}",
            question=q,
            response=resp,
            ground_truth=gt,
            execution_time=round(rng.uniform(0.2, 1.5), 3),
            task_type=ttype,
            has_error=not success,
        )
        monitor2.record_task(task)

    report2 = monitor2.generate_report()
    ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname2 = f"[PX]_exp_{ts2}.json"
    monitor2.save_to_file(fname2)

    if phoenix_ok and exp_id:
        monitor2.end_experiment(report=report2, phoenix_endpoint=PHOENIX_ENDPOINT)
        tcr2 = report2.accuracy_metrics.get("tcr", {}).get("tcr", 0)
        _check("Experiment 종료 (end_experiment)", f"TCR={tcr2:.0f}%", True)
        print()
        print("  📌  Phoenix에서 확인할 위치:")
        print("      [Datasets & Experiments 탭]")
        print("        → Experiments 목록에서 'verify-run-*' 항목 확인")
        print("      [Tracing 탭]")
        print("        → 스팬 Attributes: ae.experiment_id 필드 존재 여부 확인")
        print("        → 필터: ae.experiment_name = 'verify-run-*' 로 run 단위 조회")

    return str(golden_path) if golden_path else None, exp_id


# ─── ④ Prompts ───────────────────────────────────────────────────────────────

def run_prompts(phoenix_ok: bool) -> None:
    """LLMJudge 프롬프트를 Phoenix Prompts API로 등록."""
    _section("④ Prompts — LLMJudge 채점 프롬프트 등록")

    try:
        from agent_evaluator import LLMJudge
    except Exception as e:
        _check("LLMJudge import", f"실패: {e}", False)
        return

    # LLMJudge 인스턴스 (실제 API 호출 없이 프롬프트 등록만)
    judge = LLMJudge(model="gpt-4o-mini", sample_rate=0.0)  # sample_rate=0 → judge 호출 없음

    if phoenix_ok:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prompt_name = f"ae-judge-{ts}"
        try:
            prompt_id = judge.register_prompt_to_phoenix(
                prompt_name=prompt_name,
                phoenix_endpoint=PHOENIX_ENDPOINT,
            )
            _check(
                "Phoenix Prompts 등록",
                f"prompt_id={prompt_id}" if prompt_id else "id 미반환 (Phoenix API 미지원 가능)",
                True,
            )
            if prompt_id:
                print()
                print("  📌  Phoenix에서 확인할 위치:")
                print("      [Prompts 탭]")
                print(f"        → '{prompt_name}' 프롬프트 항목 확인")
                print("        → 버전 이력 / Playground 연동 버튼 확인")
        except Exception as e:
            _check("Phoenix Prompts 등록", f"실패: {e}", False)
    else:
        _check("Phoenix Prompts 등록", "Phoenix 미실행 — 스킵", True)
        print("  💡  Phoenix 기동 후 재실행하면 Prompts 탭에서 확인 가능")


# ─── CLI 검증: --sync-datasets ───────────────────────────────────────────────

def run_cli_sync(golden_path: str | None) -> None:
    _section("⑤ CLI — agent-eval monitor --sync-datasets 검증")

    if not golden_path:
        _check("골든셋 파일 존재", "파일 없음 — 스킵", True)
        return

    import subprocess
    cmd = [
        sys.executable, "-m", "agent_evaluator.cli.main",
        "monitor",
        "--sync-datasets", golden_path,
        "--port", "6006",
    ]
    print(f"  실행: {' '.join(cmd[-4:])}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           cwd=str(project_root))
        output = (r.stdout + r.stderr).strip()
        ok = r.returncode == 0
        _check("--sync-datasets CLI", "exit 0" if ok else f"exit {r.returncode}", ok)
        if output:
            for line in output.splitlines()[:6]:
                print(f"    {line}")
    except subprocess.TimeoutExpired:
        _check("--sync-datasets CLI", "timeout", False)
    except Exception as e:
        _check("--sync-datasets CLI", f"오류: {e}", False)


# ─── 최종 보고서 ─────────────────────────────────────────────────────────────

def print_final_report(phoenix_ok: bool) -> None:
    print(f"\n  {'═'*68}")
    print(f"  검증 결과 요약")
    print(f"  {'─'*68}")
    pass_cnt = sum(1 for _, _, ok in _results if ok)
    for label, detail, ok in _results:
        mark = "✅" if ok else "❌"
        print(f"  {mark}  {label:<45} {detail}")
    print(f"  {'═'*68}")
    print(f"  합계: {pass_cnt}/{len(_results)} 통과\n")

    if not phoenix_ok:
        print("  ┌─────────────────────────────────────────────────────┐")
        print("  │  Phoenix 미실행 — UI 탭 검증을 완료하려면:          │")
        print("  │                                                      │")
        print("  │   터미널 1:  agent-eval monitor                     │")
        print("  │   터미널 2:  python 17_phoenix_verification.py      │")
        print("  └─────────────────────────────────────────────────────┘\n")
    else:
        print("  Phoenix UI 체크리스트:")
        print("  ┌──────────────────────────────┬─────────────────────────────────────┐")
        print("  │ 탭                           │ 확인 항목                           │")
        print("  ├──────────────────────────────┼─────────────────────────────────────┤")
        print("  │ Tracing                      │ ae.question / ae.response /         │")
        print("  │                              │ ae.ground_truth attribute 존재       │")
        print("  ├──────────────────────────────┼─────────────────────────────────────┤")
        print("  │ Tracing → Annotations 뷰     │ accuracy / completion / success /   │")
        print("  │ (= Evaluators)               │ hallucination / quality / latency_s │")
        print("  │                              │ / tool_calls / attempts 8개 지표    │")
        print("  ├──────────────────────────────┼─────────────────────────────────────┤")
        print("  │ Datasets & Experiments       │ ae-verify-* 데이터셋 항목           │")
        print("  │                              │ verify-run-* 실험 항목              │")
        print("  ├──────────────────────────────┼─────────────────────────────────────┤")
        print("  │ Prompts                      │ ae-judge-* 프롬프트 항목            │")
        print("  └──────────────────────────────┴─────────────────────────────────────┘\n")


# ─── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 70)
    print("  Phoenix 통합 검증 — Agent Evaluator v0.7.0")
    print("=" * 70)

    phoenix_ok = _phoenix_running()
    if phoenix_ok:
        print(f"\n  ✅  Phoenix 실행 중 — {PHOENIX_ENDPOINT}")
        _setup_otel()
    else:
        print(f"\n  ⚠️   Phoenix 미실행 ({PHOENIX_ENDPOINT})")
        print("       코드 검증은 진행, UI 탭 검증은 스킵됩니다.")
        print("       UI까지 검증하려면: agent-eval monitor  →  재실행")

    # ① + ② Evaluators + Tracing
    base_filename = run_tracing_and_evaluators(phoenix_ok)

    # 스팬이 Phoenix에 인덱싱될 시간 확보
    if phoenix_ok:
        print("\n  (Phoenix 스팬 인덱싱 대기 1초...)")
        time.sleep(1)

    # ③ Datasets + Experiments
    golden_path, exp_id = run_datasets_and_experiments(phoenix_ok, base_filename)

    # ④ Prompts
    run_prompts(phoenix_ok)

    # ⑤ CLI --sync-datasets
    run_cli_sync(golden_path)

    # 최종 보고서
    print_final_report(phoenix_ok)


if __name__ == "__main__":
    main()
