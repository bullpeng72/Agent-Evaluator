"""
Test.py — ch01 결과물 4단계 검증 스크립트
===========================================
(1) save_to_file → JSON + HTML 생성 확인
(2) JSON ↔ HTML 주요 수치 일치 확인
(3) 대시보드 API ↔ JSON 일치 확인
(4) export HTML/JSON/CSV ↔ save_to_file 동일 값 확인

실행: python Evaluator_Examples/Test.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

RESULTS_DIR = ROOT / "results"
TARGET_FILES = [
    "ch01_first_eval",
    "ch01_hallucination_eval",
    "ch01_sla_eval",
    "ch01_harness_eval",
]

PASS = "\033[32m✅ PASS\033[0m"
FAIL = "\033[31m❌ FAIL\033[0m"
WARN = "\033[33m⚠️  WARN\033[0m"

_errors: list[str] = []
_warns: list[str] = []


def ok(label: str) -> None:
    print(f"  {PASS}  {label}")


def fail(label: str) -> None:
    print(f"  {FAIL}  {label}")
    _errors.append(label)


def warn(label: str) -> None:
    print(f"  {WARN}  {label}")
    _warns.append(label)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(name: str) -> dict:
    p = RESULTS_DIR / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_html(name: str) -> str:
    p = RESULTS_DIR / f"{name}.html"
    return p.read_text(encoding="utf-8")


def _extract_number(pattern: str, text: str, group: int = 1) -> float | None:
    m = re.search(pattern, text)
    if m:
        try:
            return float(m.group(group).replace(",", "").replace("%", ""))
        except ValueError:
            return None
    return None


def _approx_eq(a: float | None, b: float | None, tol: float = 0.5) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


# ─────────────────────────────────────────────────────────────────────────────
# (1) JSON + HTML 파일 존재 확인
# ─────────────────────────────────────────────────────────────────────────────

def check_files_exist() -> None:
    print("\n" + "─" * 60)
    print("(1) save_to_file → JSON + HTML 생성 확인")
    print("─" * 60)
    for name in TARGET_FILES:
        j = RESULTS_DIR / f"{name}.json"
        h = RESULTS_DIR / f"{name}.html"
        j_ok = j.exists() and j.stat().st_size > 100
        h_ok = h.exists() and h.stat().st_size > 1000
        if j_ok and h_ok:
            ok(f"{name}.json ({j.stat().st_size:,}B)  +  .html ({h.stat().st_size:,}B)")
        elif not j_ok:
            fail(f"{name}.json 없거나 비어있음")
        else:
            fail(f"{name}.html 없거나 비어있음")


# ─────────────────────────────────────────────────────────────────────────────
# (2) JSON ↔ HTML(save_to_file) 수치 일치 확인
# ─────────────────────────────────────────────────────────────────────────────

def _json_tcr(raw: dict) -> float | None:
    try:
        return float(raw["accuracy_metrics"]["tcr"]["tcr"])
    except (KeyError, TypeError, ValueError):
        return None

def _json_acc(raw: dict) -> float | None:
    try:
        return float(raw["accuracy_metrics"]["accuracy_scores"]["overall_accuracy"] * 100)
    except (KeyError, TypeError, ValueError):
        return None

def _html_tcr(html: str) -> float | None:
    # TCR 수치를 HTML에서 추출 — "TCR" 레이블 근처의 숫자
    for pat in [
        r'TCR[^0-9]{0,30}?(\d+\.?\d*)\s*%',
        r'(\d+\.?\d*)\s*%[^<]{0,30}TCR',
    ]:
        v = _extract_number(pat, html)
        if v is not None:
            return v
    return None

def _html_acc(html: str) -> float | None:
    for pat in [
        r'[Aa]ccuracy[^0-9]{0,30}?(\d+\.?\d*)\s*%',
        r'overall.accuracy[^0-9]{0,30}?(\d+\.?\d*)',
    ]:
        v = _extract_number(pat, html)
        if v is not None:
            return v
    return None


def check_json_html_consistency() -> None:
    print("\n" + "─" * 60)
    print("(2) JSON ↔ save_to_file HTML 수치 일치 확인")
    print("─" * 60)

    for name in TARGET_FILES:
        raw = _parse_json(name)
        html = _parse_html(name)

        # HTML이 최소 구조를 갖추는지 확인
        has_gate_a = "gate-a" in html
        has_gate_d = "gate-d" in html
        if has_gate_a and has_gate_d:
            ok(f"{name}: HTML Gate A·D 섹션 존재")
        else:
            fail(f"{name}: HTML Gate 섹션 누락 (gate-a={has_gate_a}, gate-d={has_gate_d})")

        # TCR 비교
        j_tcr = _json_tcr(raw)
        h_tcr = _html_tcr(html)
        if j_tcr is None:
            warn(f"{name}: JSON TCR 없음 (태스크 수 부족 또는 타입 미지원)")
        elif h_tcr is None:
            warn(f"{name}: HTML에서 TCR 파싱 실패 (레이아웃 확인 필요)")
        elif _approx_eq(j_tcr, h_tcr):
            ok(f"{name}: TCR {j_tcr:.1f}% (JSON) ≈ {h_tcr:.1f}% (HTML)")
        else:
            fail(f"{name}: TCR 불일치 — JSON={j_tcr:.1f}%, HTML={h_tcr:.1f}%")

        # 태스크 수 비교
        j_tasks = len(raw.get("tasks", []))
        h_tasks_m = re.search(r'(\d+)\s*(?:tasks?|태스크)', html, re.IGNORECASE)
        h_tasks = int(h_tasks_m.group(1)) if h_tasks_m else None
        if h_tasks is not None and j_tasks == h_tasks:
            ok(f"{name}: 태스크 수 일치 ({j_tasks}건)")
        elif h_tasks is None:
            warn(f"{name}: HTML에서 태스크 수 파싱 실패")
        else:
            fail(f"{name}: 태스크 수 불일치 — JSON={j_tasks}, HTML={h_tasks}")


# ─────────────────────────────────────────────────────────────────────────────
# (3) 대시보드 API ↔ JSON 일치 확인
# ─────────────────────────────────────────────────────────────────────────────

def check_dashboard_api() -> None:
    print("\n" + "─" * 60)
    print("(3) 대시보드 API ↔ JSON 일치 확인")
    print("─" * 60)

    try:
        from starlette.testclient import TestClient
        from agent_evaluator.serve.server import create_app
    except ImportError as e:
        warn(f"대시보드 의존성 없음 — {e}")
        return

    app = create_app(results_dir=RESULTS_DIR)
    client = TestClient(app, raise_server_exceptions=True)

    # /api/results 목록 확인
    resp = client.get("/api/results")
    assert resp.status_code == 200, f"/api/results 응답 오류: {resp.status_code}"
    api_resp = resp.json()
    results_list = api_resp.get("files", api_resp) if isinstance(api_resp, dict) else api_resp
    ok(f"/api/results — {len(results_list)}개 파일 인식")

    # 각 파일별로 JSON과 API 수치 비교
    for item in results_list:
        file_id = item["id"]
        name = item["name"]
        if name not in TARGET_FILES:
            continue

        raw = _parse_json(name)
        j_tcr = _json_tcr(raw)
        j_tasks = len(raw.get("tasks", []))

        # /api/results/{id} 상세
        r2 = client.get(f"/api/results/{file_id}")
        if r2.status_code != 200:
            fail(f"{name}: /api/results/{file_id} → {r2.status_code}")
            continue
        api_data = r2.json()
        # /api/results/{id} 는 accuracy_metrics.tcr.tcr 구조로 반환
        api_tcr = (api_data.get("accuracy_metrics") or {}).get("tcr", {}).get("tcr")
        api_tasks = api_data.get("total_tasks")

        # TCR 비교
        if j_tcr is None:
            warn(f"{name}: JSON TCR 없음")
        elif api_tcr is None:
            warn(f"{name}: API TCR 없음")
        elif _approx_eq(j_tcr, float(api_tcr)):
            ok(f"{name}: TCR {j_tcr:.1f}% (JSON) ≈ {float(api_tcr):.1f}% (API)")
        else:
            fail(f"{name}: TCR 불일치 — JSON={j_tcr:.1f}%, API={api_tcr}")

        # 태스크 수 비교
        if api_tasks is not None and j_tasks == int(api_tasks):
            ok(f"{name}: 태스크 수 일치 ({j_tasks}건)")
        else:
            fail(f"{name}: 태스크 수 불일치 — JSON={j_tasks}, API={api_tasks}")


# ─────────────────────────────────────────────────────────────────────────────
# (4) export HTML/JSON/CSV ↔ save_to_file 일치 확인
# ─────────────────────────────────────────────────────────────────────────────

def check_export_consistency() -> None:
    print("\n" + "─" * 60)
    print("(4) export HTML/JSON/CSV ↔ save_to_file 값 비교")
    print("─" * 60)

    try:
        from starlette.testclient import TestClient
        from agent_evaluator.serve.server import create_app
    except ImportError as e:
        warn(f"대시보드 의존성 없음 — {e}")
        return

    app = create_app(results_dir=RESULTS_DIR)
    client = TestClient(app, raise_server_exceptions=True)

    api_resp = client.get("/api/results").json()
    results_list = api_resp.get("files", api_resp) if isinstance(api_resp, dict) else api_resp
    file_map = {item["name"]: item["id"] for item in results_list}

    for name in TARGET_FILES:
        if name not in file_map:
            warn(f"{name}: 대시보드가 인식하지 못함")
            continue
        file_id = file_map[name]
        raw = _parse_json(name)
        html_local = _parse_html(name)

        print(f"\n  [{name}]")

        # ── export JSON ──────────────────────────────────────────────────────
        r_json = client.get(f"/api/export/json/{file_id}")
        if r_json.status_code == 200:
            exp_raw = r_json.json()
            # 태스크 수 비교
            local_tasks = len(raw.get("tasks", []))
            export_tasks = len(exp_raw.get("tasks", []))
            if local_tasks == export_tasks:
                ok(f"export JSON — 태스크 수 일치 ({local_tasks}건)")
            else:
                fail(f"export JSON — 태스크 수 불일치: local={local_tasks}, export={export_tasks}")

            # TCR 비교
            j_tcr = _json_tcr(raw)
            e_tcr = _json_tcr(exp_raw)
            if j_tcr is None and e_tcr is None:
                warn(f"export JSON — TCR 없음 (양쪽 모두)")
            elif _approx_eq(j_tcr, e_tcr):
                ok(f"export JSON — TCR 일치 ({j_tcr:.1f}%)")
            else:
                fail(f"export JSON — TCR 불일치: local={j_tcr}, export={e_tcr}")
        else:
            fail(f"export JSON → HTTP {r_json.status_code}")

        # ── export CSV ───────────────────────────────────────────────────────
        r_csv = client.get(f"/api/export/csv/{file_id}")
        if r_csv.status_code == 200:
            lines = r_csv.text.strip().splitlines()
            # 헤더 제외한 행 수 = 태스크 수
            csv_tasks = len(lines) - 1
            local_tasks = len(raw.get("tasks", []))
            if csv_tasks == local_tasks:
                ok(f"export CSV — 태스크 수 일치 ({csv_tasks}건)")
            else:
                fail(f"export CSV — 태스크 수 불일치: local={local_tasks}, csv={csv_tasks}")

            # 헤더 컬럼 확인
            headers = lines[0].split(",")
            expected_cols = {"task_id", "success", "accuracy_score", "execution_time"}
            missing = expected_cols - set(headers)
            if not missing:
                ok(f"export CSV — 필수 컬럼 존재 ({len(headers)}개 컬럼)")
            else:
                fail(f"export CSV — 컬럼 누락: {missing}")
        else:
            fail(f"export CSV → HTTP {r_csv.status_code}")

        # ── export HTML ──────────────────────────────────────────────────────
        r_html = client.get(f"/api/export/html/{file_id}")
        if r_html.status_code == 200:
            html_exp = r_html.text

            # 양쪽 모두 gate 섹션 존재 여부
            for gate in ["gate-a", "gate-d", "gate-e"]:
                local_has = gate in html_local
                export_has = gate in html_exp
                if local_has == export_has:
                    ok(f"export HTML — {gate} 섹션 일치 (both={local_has})")
                else:
                    fail(f"export HTML — {gate} 섹션 불일치: save_to_file={local_has}, export={export_has}")

            # TCR 수치 비교
            tcr_local = _html_tcr(html_local)
            tcr_export = _html_tcr(html_exp)
            if tcr_local is None and tcr_export is None:
                warn(f"export HTML — 양쪽 모두 TCR 파싱 실패")
            elif _approx_eq(tcr_local, tcr_export):
                ok(f"export HTML — TCR 수치 일치 ({tcr_local:.1f}% ≈ {tcr_export:.1f}%)")
            else:
                fail(f"export HTML — TCR 수치 불일치: save_to_file={tcr_local}, export={tcr_export}")

            # 태스크 수 비교
            local_tasks = len(raw.get("tasks", []))
            m_local = re.search(r'(\d+)\s*tasks?', html_local, re.IGNORECASE)
            m_exp   = re.search(r'(\d+)\s*tasks?', html_exp, re.IGNORECASE)
            n_local = int(m_local.group(1)) if m_local else None
            n_exp   = int(m_exp.group(1)) if m_exp else None
            if n_local is not None and n_exp is not None and n_local == n_exp:
                ok(f"export HTML — 태스크 수 일치 ({n_local}건)")
            elif n_local is None or n_exp is None:
                warn(f"export HTML — 태스크 수 파싱 실패 (local={n_local}, export={n_exp})")
            else:
                fail(f"export HTML — 태스크 수 불일치: save_to_file={n_local}, export={n_exp}")

            # 보안 섹션 동일 여부 (Security Metrics)
            sec_local = "Security Metrics" in html_local
            sec_exp   = "Security Metrics" in html_exp
            if sec_local == sec_exp:
                ok(f"export HTML — Security Metrics 섹션 일치 (both={sec_local})")
            else:
                fail(f"export HTML — Security Metrics 불일치: save_to_file={sec_local}, export={sec_exp}")

        else:
            fail(f"export HTML → HTTP {r_html.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Agent-Evaluator 출력 정합성 검증 (4단계)")
    print("=" * 60)

    check_files_exist()
    check_json_html_consistency()
    check_dashboard_api()
    check_export_consistency()

    print("\n" + "=" * 60)
    total_errors = len(_errors)
    total_warns  = len(_warns)
    if total_errors == 0:
        print(f"\033[32m✅ 전체 통과\033[0m  (경고 {total_warns}건)")
    else:
        print(f"\033[31m❌ 실패 {total_errors}건\033[0m  (경고 {total_warns}건)")
        for e in _errors:
            print(f"   • {e}")
    print("=" * 60)
    sys.exit(0 if total_errors == 0 else 1)
