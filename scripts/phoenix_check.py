"""
Phoenix 통합 점검 스크립트 — Agent Evaluator v0.7.0
====================================================

Phoenix 메뉴 4개의 연동 상태를 자동으로 점검한다.

  [1] Tracing     — ae.question / ae.response / ae.ground_truth 스팬 attribute
  [2] Evaluators  — 8개 Annotation 지표 (Tracing → Annotations 뷰)
  [3] Datasets    — 골든셋 → Phoenix Datasets 업로드
  [4] Prompts     — LLMJudge 채점 프롬프트 등록

실행:
    # Phoenix 먼저 기동
    agent-eval monitor

    # 다른 터미널에서
    cd Evaluator_Examples
    python 17_phoenix_check.py
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

PHOENIX = "http://localhost:6006"
TS = datetime.now().strftime("%H%M%S")

# ─── 출력 헬퍼 ───────────────────────────────────────────────────────────────

_results: List[Tuple[str, str, bool]] = []

def _ok(label: str, detail: str = "") -> None:
    _results.append((label, detail, True))
    print(f"  ✅  {label:<52} {detail}")

def _fail(label: str, detail: str = "") -> None:
    _results.append((label, detail, False))
    print(f"  ❌  {label:<52} {detail}")

def _skip(label: str, reason: str = "") -> None:
    print(f"  ⏭️   {label:<52} {reason}")

def _section(n: int, title: str) -> None:
    print(f"\n  ┌─[{n}] {title}")
    print(f"  │")

def _end_section() -> None:
    print(f"  └{'─'*68}")

# ─── Phoenix REST / GraphQL 헬퍼 ─────────────────────────────────────────────

def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{PHOENIX}{path}", timeout=5) as r:
        return json.loads(r.read())

def _post(path: str, body: Dict[str, Any]) -> Tuple[int, Any]:
    req = urllib.request.Request(
        f"{PHOENIX}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")[:300]
        return e.code, {"error": body_txt}

def _graphql(query: str) -> Any:
    _, resp = _post("/graphql", {"query": query})
    return resp

def _phoenix_running() -> bool:
    import socket
    h, p = PHOENIX.replace("http://", "").split(":")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((h, int(p))) == 0

# ─── 테스트 태스크 데이터 ─────────────────────────────────────────────────────


# (question, response, ground_truth, task_type, success, context_or_None)
_TASKS = [
    (
        "한국의 수도는?",
        "서울입니다.",
        "서울",
        "qa",
        True,
        "한국은 동아시아에 위치한 나라로, 수도는 서울이며 최대 도시이다.",  # context → hallucination 탐지
    ),
    (
        "REST API란?",
        "HTTP 기반 웹 서비스 원칙.",
        "HTTP 서비스 설계",
        "qa",
        True,
        "REST(Representational State Transfer)는 HTTP를 기반으로 하는 클라이언트-서버 아키텍처 스타일이다.",
    ),
    (
        "Docker와 VM 차이?",
        "잘 모르겠습니다.",
        "컨테이너 vs VM",
        "qa",
        False,
        None,  # context 없음
    ),
    (
        "Python 리스트 컴프리헨션?",
        "[x*2 for x in range(10)]",
        "리스트 생성 문법",
        "code_generation",
        True,
        None,
    ),
]

# ─── [1] + [2]: 스팬 생성 후 Tracing & Evaluators 점검 ───────────────────────

def check_tracing_and_evaluators() -> Optional[str]:
    """
    테스트 스팬 4개를 발행하고, Phoenix GraphQL로 역조회하여
    ae.question / ae.response / ae.ground_truth 존재와
    8개 Annotation 지표를 검증한다.
    """
    _section(1, "Tracing  +  [2] Evaluators (Annotations)")

    from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel

    setup_otel(endpoint=PHOENIX, service_name=f"ae-check-{TS}")

    monitor = PerformanceMonitor(
        output_dir=str(project_root / "results"),
        enable_hallucination_detection=True,   # hallucination annotation 생성용
        enable_security_metrics=False,
    )

    rng = random.Random(7)
    task_ids = []
    for i, (q, resp, gt, ttype, success, ctx) in enumerate(_TASKS):
        tid = f"chk_{TS}_{i+1:02d}"
        task_ids.append(tid)
        kwargs: Dict[str, Any] = dict(
            task_id=tid,
            question=q,
            response=resp,
            ground_truth=gt,
            execution_time=round(rng.uniform(0.3, 2.0), 3),
            task_type=ttype,
            has_error=not success,
        )
        if ctx is not None:
            kwargs["context"] = ctx
        t = create_taskresult(**kwargs)
        monitor.record_task(t)

    monitor.save_to_file(f"[CHK]_check_{TS}")
    print(f"  │  스팬 {len(task_ids)}개 발행 + save_to_file() 완료")

    # Phoenix GraphQL로 스팬 역조회 — 인덱싱 대기 (최대 15초 재시도)
    # setup_otel(service_name=...) 이 Phoenix 프로젝트 이름이 되므로 이름으로 매칭.
    # OTLP BatchSpanProcessor가 비동기로 전송하므로 프로젝트 생성 자체도 지연될 수 있음.
    # → 프로젝트 조회도 retry 루프 안에서 수행.
    service_name = f"ae-check-{TS}"
    project_id: Optional[str] = None

    spans_found: Dict[str, Any] = {}
    for attempt in range(5):  # 최대 15초 대기 (3s × 5회)
        print(f"  │  Phoenix 인덱싱 대기 중... (시도 {attempt+1}/5, {3*(attempt+1)}초 경과)\r", end="")
        time.sleep(3)

        # 프로젝트 목록 갱신 — 아직 생성 전일 수 있으므로 매 시도마다 재조회
        if project_id is None:
            resp_proj = _graphql("{ projects { edges { node { id name } } } }")
            proj_edges = resp_proj.get("data", {}).get("projects", {}).get("edges", [])
            project_id = next(
                (e["node"]["id"] for e in proj_edges if e["node"]["name"] == service_name),
                None,
            )
            if project_id:
                print(f"  │  Phoenix 프로젝트 확인: '{service_name}' (id={project_id})" + " " * 20)

        if not project_id:
            continue  # 아직 프로젝트 미생성 — 다음 시도

        q_span = f"""{{
          node(id: "{project_id}") {{
            ... on Project {{
              spans(first: 500, sort: {{col: startTime, dir: desc}}) {{
                edges {{
                  node {{
                    spanId name attributes
                    spanAnnotations {{ name score label }}
                  }}
                }}
              }}
            }}
          }}
        }}"""
        r_spans = _graphql(q_span)
        edges = (
            r_spans.get("data", {})
            .get("node", {})
            .get("spans", {})
            .get("edges", [])
        )
        for edge in edges:
            node = edge["node"]
            name: str = node.get("name", "")
            for tid in task_ids:
                if tid in name and tid not in spans_found:
                    spans_found[tid] = node
        if len(spans_found) == len(task_ids):
            break  # 모두 발견

    print(f"  │  GraphQL 역조회: {len(spans_found)}/{len(task_ids)}개 발견" + " " * 40)

    # ── [1] Tracing — ae.* attribute 점검
    # Phoenix는 OTLP dot-notation을 중첩 dict으로 저장
    # ae.question → attrs["ae"]["question"]
    print(f"  │")
    print(f"  │  [1] Tracing — ae.question / ae.response / ae.ground_truth")
    ae_attr_ok = True
    for tid, node in spans_found.items():
        raw = node.get("attributes") or "{}"
        attrs = json.loads(raw) if isinstance(raw, str) else (raw or {})
        ae = attrs.get("ae", {})  # Phoenix 중첩 구조
        has_q  = bool(ae.get("question"))
        has_r  = bool(ae.get("response"))
        has_gt = bool(ae.get("ground_truth"))
        if has_q and has_r and has_gt:
            print(f"  │    ✅  {tid}  ae.question={ae['question'][:20]!r}")
        else:
            ae_attr_ok = False
            missing = [k for k, v in [("ae.question", has_q), ("ae.response", has_r), ("ae.ground_truth", has_gt)] if not v]
            print(f"  │    ❌  {tid}  누락: {missing}")

    if spans_found:
        if ae_attr_ok:
            _ok("ae.question/response/ground_truth 모든 스팬에 존재")
        else:
            _fail("ae.question/response/ground_truth 일부 누락")
    else:
        _fail("스팬 GraphQL 역조회 실패 — Phoenix에 스팬 없음")

    # ── [2] Evaluators — Annotation 8개 점검
    EXPECTED_ANNOTATIONS = {
        "accuracy", "completion", "success",
        "hallucination", "quality",
        "latency_s", "tool_calls", "attempts",
    }
    print(f"  │")
    print(f"  │  [2] Evaluators — Annotation 8개 지표")

    ann_coverage: Dict[str, set] = {}  # tid → set of annotation names
    for tid, node in spans_found.items():
        anns = node.get("spanAnnotations") or []
        ann_coverage[tid] = {a["name"] for a in anns}

    if ann_coverage:
        # 대표 스팬 하나 상세 출력
        sample_tid = next(iter(ann_coverage))
        sample_anns = ann_coverage[sample_tid]
        present   = EXPECTED_ANNOTATIONS & sample_anns
        missing_a = EXPECTED_ANNOTATIONS - sample_anns
        for ann_name in sorted(present):
            node = spans_found[sample_tid]
            anns = node.get("spanAnnotations") or []
            score = next((a["score"] for a in anns if a["name"] == ann_name), None)
            print(f"  │    ✅  {ann_name:<16} score={score}")
        for ann_name in sorted(missing_a):
            print(f"  │    ❌  {ann_name:<16} 미전송")

        all_present = len(missing_a) == 0
        if all_present:
            _ok(f"Annotation 8개 전송 완료", f"({len(present)}/8)")
        else:
            _fail(f"Annotation 일부 누락", f"누락={sorted(missing_a)}")
    else:
        _fail("Annotation 없음 — save_to_file() 후 전송 실패 가능")

    _end_section()
    return spans_found.get(task_ids[0], {}).get("spanId") if spans_found else None


# ─── [3] Datasets ─────────────────────────────────────────────────────────────

def check_datasets() -> Optional[str]:
    """
    골든셋 JSON을 인라인으로 생성 후 /v1/datasets 로 업로드,
    GET /v1/datasets 역조회로 존재 확인.
    """
    _section(3, "Datasets & Experiments")
    from agent_evaluator.datasets.builder import GoldenSetBuilder

    golden_dir = project_root / "data" / "golden_datasets"
    golden_dir.mkdir(parents=True, exist_ok=True)

    # 임시 골든셋 파일 생성
    candidates = [
        {"task_id": f"g_{TS}_01", "question": "한국의 수도는?",  "ground_truth": "서울",
         "accuracy_score": 1.0, "completion_score": 1.0, "_strategy": "high_value"},
        {"task_id": f"g_{TS}_02", "question": "REST API란?",     "ground_truth": "HTTP 서비스",
         "accuracy_score": 0.9, "completion_score": 0.9, "_strategy": "high_value"},
    ]
    golden_path = golden_dir / f"check_{TS}.json"
    golden_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2))
    _ok("골든셋 임시 파일 생성", golden_path.name)

    # upload_to_phoenix()
    builder = GoldenSetBuilder(source_dir=str(golden_dir), output_dir=str(golden_dir))
    dataset_name = f"ae-check-{TS}"
    dataset_id: Optional[str] = None
    try:
        dataset_id = builder.upload_to_phoenix(
            dataset_path=str(golden_path),
            dataset_name=dataset_name,
            phoenix_endpoint=PHOENIX,
        )
        if dataset_id:
            _ok("POST /v1/datasets 업로드", f"id={dataset_id}")
        else:
            _fail("POST /v1/datasets 업로드", "id 미반환")
    except Exception as e:
        _fail("POST /v1/datasets 업로드", str(e)[:80])

    # GraphQL datasets query로 역조회
    try:
        r = _graphql("{ datasets { edges { node { id name exampleCount } } } }")
        ds_nodes = [e["node"] for e in r.get("data", {}).get("datasets", {}).get("edges", [])]
        names = [d["name"] for d in ds_nodes]
        match = next((d for d in ds_nodes if d["name"] == dataset_name), None)
        if match:
            _ok("GraphQL datasets 역조회 — 업로드 확인",
                f"'{dataset_name}' exampleCount={match.get('exampleCount', '?')}")
        else:
            _fail("GraphQL datasets 역조회", f"'{dataset_name}' 없음 (현재: {names[:3]})")
    except Exception as e:
        _fail("GraphQL datasets 역조회", str(e)[:80])

    print(f"  │")
    print(f"  │  📌 Phoenix UI 확인 위치:")
    print(f"  │     Datasets & Experiments 탭 → '{dataset_name}' 항목")

    _end_section()
    return dataset_id


# ─── [4] Prompts ─────────────────────────────────────────────────────────────

def check_prompts() -> None:
    """
    LLMJudge.register_prompt_to_phoenix() 호출 후
    GET /v1/prompts 역조회로 존재 확인.
    """
    _section(4, "Prompts")
    from agent_evaluator import LLMJudge

    judge = LLMJudge(model="gpt-5-nano", sample_rate=0.0)
    prompt_name = f"ae-judge-{TS}"

    prompt_id: Optional[str] = None
    try:
        prompt_id = judge.register_prompt_to_phoenix(
            prompt_name=prompt_name,
            phoenix_endpoint=PHOENIX,
        )
        if prompt_id:
            _ok("POST /v1/prompts 등록", f"id={prompt_id}")
        else:
            _fail("POST /v1/prompts 등록", "id 미반환")
    except Exception as e:
        _fail("POST /v1/prompts 등록", str(e)[:80])

    # GET /v1/prompts 역조회
    try:
        body = _get("/v1/prompts")
        names = [p.get("name", "") for p in body.get("data", [])]
        if prompt_name in names:
            _ok("GET /v1/prompts 역조회 — 등록 확인", f"'{prompt_name}' 목록에 존재")
        else:
            _fail("GET /v1/prompts 역조회", f"'{prompt_name}' 없음 (현재: {names[:3]})")
    except Exception as e:
        _fail("GET /v1/prompts 역조회", str(e)[:80])

    print(f"  │")
    print(f"  │  📌 Phoenix UI 확인 위치:")
    print(f"  │     Prompts 탭 → '{prompt_name}' 항목")
    print(f"  │     → 'Open in Playground' 버튼으로 Playground 연동 확인")

    _end_section()


# ─── 최종 보고서 ─────────────────────────────────────────────────────────────

def print_summary() -> int:
    passed = sum(1 for *_, ok in _results if ok)
    total  = len(_results)
    failed = total - passed

    print(f"\n  {'═'*70}")
    print(f"  점검 결과: {passed}/{total} 통과  {'✅ 전체 통과' if failed == 0 else f'❌ {failed}개 실패'}")
    print(f"  {'─'*70}")
    for label, detail, ok in _results:
        mark = "✅" if ok else "❌"
        print(f"  {mark}  {label:<52} {detail}")
    print(f"  {'═'*70}")

    if failed:
        print(f"\n  실패 항목 해결 방법:")
        for label, detail, ok in _results:
            if not ok:
                print(f"    • {label}")
                if "역조회 실패" in label or "스팬" in label:
                    print(f"      → agent-eval monitor 실행 중인지 확인")
                    print(f"      → setup_otel() 후 save_to_file() 필요")
                elif "Annotation" in label:
                    print(f"      → save_to_file() 호출 후 3초 이상 대기 필요")
                    print(f"      → enable_hallucination_detection=True 설정 확인")
    print()
    return 0 if failed == 0 else 1


# ─── 메인 ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n" + "=" * 72)
    print("  Phoenix 통합 점검 — Agent Evaluator v0.7.0")
    print(f"  Phoenix: {PHOENIX}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # Phoenix 실행 여부 확인
    if not _phoenix_running():
        print(f"\n  ❌  Phoenix 미실행 ({PHOENIX})")
        print(f"     먼저 실행하세요:  agent-eval monitor\n")
        return 1
    print(f"\n  ✅  Phoenix 실행 중\n")

    # [1] Tracing + [2] Evaluators
    check_tracing_and_evaluators()

    # [3] Datasets
    check_datasets()

    # [4] Prompts
    check_prompts()

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
