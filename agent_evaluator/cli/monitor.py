"""
agent-eval monitor — 운영 실시간 모니터링 (Phoenix + OTEL)

Phoenix 13.x 기준:
  - UI + OTLP HTTP 수신: 동일 포트 (기본 6006)
  - OTLP gRPC 수신: 기본 4317
  - 포트 설정: PHOENIX_PORT 환경변수 (--port CLI 인수 없음)

사용법:
    agent-eval monitor                      # Phoenix 기동 + 브라우저 오픈
    agent-eval monitor --port 6006          # 포트 지정
    agent-eval monitor --no-open            # 브라우저 자동 오픈 비활성화
    agent-eval monitor --attach <url>       # 기존 Phoenix 서버에 연결
    agent-eval monitor --check              # 설치 상태 및 포트 점유 확인
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import sys
import time
import webbrowser
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 도움말 포맷터 — RawDescriptionHelpFormatter + 한국어 "사용법:" 접두사
# ---------------------------------------------------------------------------


class _MonitorHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """monitor 서브파서용 HelpFormatter.

    RawDescriptionHelpFormatter를 상속해 description/epilog 줄바꿈을 보존하면서
    사용법 접두사를 한국어로 출력한다.
    """

    def _format_usage(self, usage, actions, groups, prefix):  # type: ignore[override]
        if prefix is None:
            prefix = "사용법: "
        return super()._format_usage(usage, actions, groups, prefix)


# ---------------------------------------------------------------------------
# 의존성 / 포트 유틸리티
# ---------------------------------------------------------------------------


def _pkg_installed(import_name: str) -> bool:
    """패키지가 import 가능한지 확인 (실제 import 없이)."""
    return importlib.util.find_spec(import_name) is not None


def _phoenix_version() -> Optional[str]:
    """설치된 arize-phoenix 버전 반환. 미설치 시 None."""
    try:
        from importlib.metadata import version

        return version("arize-phoenix")
    except Exception:
        return None


def _check_deps() -> Dict[str, bool]:
    """필수 패키지 설치 여부 반환."""
    return {
        "arize-phoenix": _pkg_installed("phoenix"),
        "opentelemetry-sdk": _pkg_installed("opentelemetry.sdk"),
        "opentelemetry-exporter-otlp-proto-http": _pkg_installed(
            "opentelemetry.exporter.otlp.proto.http"
        ),
    }


def _port_in_use(port: int, host: str = "localhost") -> bool:
    """포트가 이미 사용 중이면 True."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _phoenix_cmd() -> List[str]:
    """Phoenix 기동 명령 반환.

    `phoenix` CLI 바이너리가 있으면 우선 사용,
    없으면 python -m phoenix.server.main serve 로 fallback.
    """
    if shutil.which("phoenix"):
        return ["phoenix", "serve"]
    return [sys.executable, "-m", "phoenix.server.main", "serve"]


# ---------------------------------------------------------------------------
# --check 모드
# ---------------------------------------------------------------------------


def cmd_check_monitor() -> int:
    """--check: 설치 상태 및 포트 점유 확인."""
    deps = _check_deps()
    all_ok = True

    print()
    print("  패키지 상태")
    print("  " + "─" * 54)
    for pkg, installed in deps.items():
        if installed:
            suffix = f"  ({_phoenix_version()})" if pkg == "arize-phoenix" else ""
            print(f"  ✅  {pkg:<50} 설치됨{suffix}")
        else:
            print(f"  ❌  {pkg:<50} 미설치")
            all_ok = False

    print()
    print("  포트 상태  (Phoenix 13.x: UI + OTLP HTTP 동일 포트)")
    print("  " + "─" * 54)
    for port, label in [(6006, "Phoenix UI / OTLP HTTP"), (4317, "OTLP gRPC")]:
        in_use = _port_in_use(port)
        if in_use:
            print(f"  ⚠️   포트 {port:<6} ({label}) — 사용 중 (다른 프로세스)")
        else:
            print(f"  ✅  포트 {port:<6} ({label}) — 사용 가능")

    if not all_ok:
        print()
        print("  설치 명령어:")
        print('  pip install "agent-evaluator[otel]"')
        print()
        return 1

    print()
    return 0


# ---------------------------------------------------------------------------
# 연결 정보 출력
# ---------------------------------------------------------------------------


def _print_connect_info(ui_url: str, otlp_url: str) -> None:
    import unicodedata

    INNER = 57  # ─ 개수 = 박스 내부 표시 너비 (열 단위)

    def _dw(text: str) -> int:
        """터미널 표시 폭 계산 (한글·전각문자 = 2열)."""
        return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)

    def _row(content: str) -> str:
        pad = INNER - _dw(content)
        return f"  │{content}{' ' * max(pad, 0)}│"

    top = f"  ┌{'─' * INNER}┐"
    sep = f"  ├{'─' * INNER}┤"
    bot = f"  └{'─' * INNER}┘"

    print()
    print(top)
    print(_row("  Agent Evaluator — 운영 모니터링"))
    print(sep)
    print(_row(f"  Phoenix UI      {ui_url}"))
    print(_row(f"  OTLP HTTP       {otlp_url}"))
    print(sep)
    print(_row("  에이전트 코드에 아래를 추가하세요:"))
    print(_row(""))
    print(_row("  from agent_evaluator import setup_otel"))
    print(_row(f'  setup_otel(endpoint="{otlp_url}")'))
    print(bot)
    print()

    # Phoenix UI는 새 프로젝트를 자동 감지하지 않음 (Relay 클라이언트 한계).
    # 브라우저 콘솔에 아래 스크립트를 붙여넣으면 5초마다 자동 새로고침.
    print("  ── Phoenix Tracing 자동 새로고침 ──────────────────────────")
    print("  새 프로젝트는 Phoenix UI에서 수동 새로고침 필요 (UI 한계).")
    print("  브라우저 콘솔(F12 → Console)에 아래를 붙여넣으면 자동 적용:")
    print()
    print("  (()=>{let p='';setInterval(async()=>{const d=await")
    print(f"  fetch('{ui_url}/v1/projects').then(r=>r.json());")
    print("  const c=JSON.stringify((d.data??[]).map(x=>x.name).sort());")
    print("  if(c!==p&&p!=='')location.reload();p=c;},5000);})();")
    print("  ────────────────────────────────────────────────────────────")
    print()


# ---------------------------------------------------------------------------
# monitor 메인 핸들러
# ---------------------------------------------------------------------------


def cmd_sync_datasets(args: argparse.Namespace) -> int:
    """--sync-datasets: 골든셋 JSON 파일을 Phoenix Datasets API로 업로드."""
    import glob as _glob

    from agent_evaluator.datasets.builder import GoldenSetBuilder

    pattern = args.sync_datasets
    files = _glob.glob(pattern)
    if not files:
        print(f"\n  ❌  파일을 찾을 수 없습니다: {pattern}\n")
        return 1

    phoenix_endpoint = f"http://{args.host}:{args.port}"
    builder = GoldenSetBuilder(source_dir=".", output_dir=".")
    success_count = 0

    print(f"\n  Phoenix Datasets 업로드 — {phoenix_endpoint}\n")
    for filepath in sorted(files):
        import pathlib
        name = pathlib.Path(filepath).stem
        try:
            dataset_id = builder.upload_to_phoenix(
                dataset_path=filepath,
                dataset_name=name,
                phoenix_endpoint=phoenix_endpoint,
            )
            if dataset_id:
                print(f"  ✅  {filepath}  →  dataset_id: {dataset_id}")
            else:
                print(f"  ⚠️   {filepath}  →  업로드 완료 (id 미반환)")
            success_count += 1
        except Exception as exc:
            print(f"  ❌  {filepath}  →  실패: {exc}")

    print(f"\n  완료: {success_count}/{len(files)}개 업로드\n")
    return 0 if success_count > 0 else 1


def cmd_reset_db(args: argparse.Namespace) -> int:
    """Phoenix DB 초기화 — 모든 트레이스·프로젝트·데이터셋 삭제."""
    import pathlib

    # 1. DB 경로 결정
    # PHOENIX_SQL_DATABASE_URL이 설정된 경우 PostgreSQL → 파일 삭제 불가
    pg_url = os.environ.get("PHOENIX_SQL_DATABASE_URL", "")
    if pg_url and not pg_url.startswith("sqlite"):
        print()
        print("  ❌  PostgreSQL 데이터베이스는 파일 삭제로 초기화할 수 없습니다.")
        print(f"     PHOENIX_SQL_DATABASE_URL={pg_url}")
        print("     DB 관리자에게 직접 테이블을 truncate 하도록 요청하세요.")
        print()
        return 1

    # working_dir: CLI 인수(명시) → 환경변수 → Phoenix 기본값 순서
    cli_dir = getattr(args, "working_dir", None)  # None = 미지정
    env_dir = os.environ.get("PHOENIX_WORKING_DIR", "")
    if cli_dir:
        working_dir = pathlib.Path(cli_dir)
    elif env_dir:
        working_dir = pathlib.Path(env_dir)
    else:
        try:
            from phoenix.config import get_working_dir
            working_dir = pathlib.Path(get_working_dir())
        except Exception:
            working_dir = pathlib.Path(os.path.expanduser("~/.phoenix"))

    db_file = working_dir / "phoenix.db"

    # 2. DB 파일 존재 확인
    if not db_file.exists():
        print()
        print(f"  ℹ️   Phoenix DB 파일이 없습니다: {db_file}")
        print("     (아직 Phoenix를 실행한 적이 없거나 이미 초기화된 상태)")
        print()
        return 0

    # 3. Phoenix 실행 중 여부 확인
    port = getattr(args, "port", 6006)
    host = getattr(args, "host", "localhost")
    if _port_in_use(port, host):
        print()
        print(f"  ❌  Phoenix가 포트 {port}에서 실행 중입니다.")
        print("     DB를 초기화하려면 먼저 Phoenix를 종료하세요.")
        print(f"     (Ctrl+C 또는 kill $(lsof -ti :{port}))")
        print()
        return 1

    # 4. 삭제 대상 목록 (DB 파일 + WAL 파일 + trace_datasets)
    targets: list[pathlib.Path] = []
    for name in ("phoenix.db", "phoenix.db-shm", "phoenix.db-wal"):
        p = working_dir / name
        if p.exists():
            targets.append(p)

    trace_dir = working_dir / "trace_datasets"
    if trace_dir.exists() and any(trace_dir.iterdir()):
        targets.append(trace_dir)

    inferences_dir = working_dir / "inferences"
    if inferences_dir.exists() and any(inferences_dir.iterdir()):
        targets.append(inferences_dir)

    # 5. 확인 프롬프트 (--yes 없을 때)
    print()
    print(f"  Phoenix DB 초기화 — {working_dir}")
    print()
    for t in targets:
        size = t.stat().st_size if t.is_file() else sum(f.stat().st_size for f in t.rglob("*") if f.is_file())
        print(f"  🗑  {t.name:<24s} ({size/1024:.1f} KB)")
    print()
    print("  ⚠️  모든 트레이스·프로젝트·어노테이션·데이터셋이 삭제됩니다.")
    print()

    if not getattr(args, "yes", False):
        try:
            ans = input("  계속하시겠습니까? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans not in ("y", "yes"):
            print("  취소됨.")
            print()
            return 0

    # 6. 삭제 실행
    for t in targets:
        try:
            if t.is_file():
                t.unlink()
                print(f"  ✅  삭제: {t}")
            elif t.is_dir():
                shutil.rmtree(t)
                t.mkdir(exist_ok=True)   # 빈 디렉토리 재생성 (Phoenix 재시작 시 필요)
                print(f"  ✅  초기화: {t}/")
        except Exception as exc:
            print(f"  ❌  실패: {t}  →  {exc}")
            return 1

    print()
    print("  Phoenix DB 초기화 완료. 다음 실행 시 새 DB가 자동 생성됩니다.")
    print(f"  agent-eval monitor --port {port}")
    print()
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Phoenix 서버 기동 후 OTEL 연결 정보 출력."""
    if args.check:
        return cmd_check_monitor()

    if getattr(args, "reset", False):
        return cmd_reset_db(args)

    if args.sync_datasets:
        return cmd_sync_datasets(args)

    # 의존성 확인
    deps = _check_deps()
    missing = [pkg for pkg, ok in deps.items() if not ok]
    if missing:
        print()
        print("  ❌  필수 패키지가 설치되지 않았습니다.")
        print(f"     미설치: {', '.join(missing)}")
        print()
        print('  pip install "agent-evaluator[otel]"')
        print()
        return 1

    port: int = args.port
    host: str = args.host
    ui_url = f"http://{host}:{port}"
    # Phoenix 13.x: OTLP HTTP는 UI와 동일 포트
    otlp_url = ui_url

    # --attach 모드: 자체 기동 없이 기존 서버에 연결
    if args.attach:
        ui_url = args.attach.rstrip("/")
        otlp_url = ui_url
        _print_connect_info(ui_url, otlp_url)
        if not args.no_open:
            webbrowser.open(ui_url)
        return 0

    # Phoenix 포트 충돌 확인
    if _port_in_use(port, host):
        print()
        print(f"  ⚠️   포트 {port}가 이미 사용 중입니다.")
        print(f"     기존 서버에 연결하려면: agent-eval monitor --attach {ui_url}")
        print()
        return 1

    # Phoenix 서버 기동
    # Phoenix 13.x: 포트는 PHOENIX_PORT 환경변수로 지정
    print(f"\n  Agent Evaluator — 운영 모니터링 기동 중...\n")
    try:
        import subprocess

        env = os.environ.copy()
        env["PHOENIX_PORT"] = str(port)

        cmd = _phoenix_cmd()
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"  ❌  Phoenix 서버 기동 실패: {exc}")
        return 1

    # 서버 준비 대기 (최대 30초 — Phoenix 13.x는 DB 초기화로 시간이 걸릴 수 있음)
    for _ in range(60):
        if _port_in_use(port, host):
            break
        time.sleep(0.5)
    else:
        print("  ❌  Phoenix 서버 기동 시간 초과 (30초).")
        print(f"     직접 실행해보세요: PHOENIX_PORT={port} phoenix serve")
        proc.terminate()
        return 1

    _print_connect_info(ui_url, otlp_url)

    if not args.no_open:
        webbrowser.open(ui_url)

    # 새 프로젝트 감지 — 백그라운드 폴링 스레드
    # Phoenix UI가 자동 갱신을 지원하지 않으므로 터미널에서 알림 출력
    import threading

    def _watch_projects(base_url: str) -> None:
        import urllib.request
        import json as _json

        known: set = set()
        initialized = False
        while True:
            time.sleep(5)
            try:
                with urllib.request.urlopen(f"{base_url}/v1/projects", timeout=3) as resp:
                    data = _json.loads(resp.read())
                names = {p["name"] for p in (data.get("data") or [])}
                if not initialized:
                    known = names
                    initialized = True
                    continue
                new = names - known
                if new:
                    for n in sorted(new):
                        print(f"\n  🆕  새 프로젝트 감지: [{n}]  → 브라우저에서 새로고침(F5) 또는 콘솔 스크립트 실행")
                    known = names
            except Exception:
                pass  # Phoenix 재시작 중이면 조용히 무시

    watcher = threading.Thread(target=_watch_projects, args=(ui_url,), daemon=True)
    watcher.start()

    print("  Ctrl+C 로 종료\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  모니터링 서버 종료됨.")

    return 0


# ---------------------------------------------------------------------------
# 서브파서 등록 (main.py 에서 호출)
# ---------------------------------------------------------------------------


def build_monitor_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """main.py에서 호출 — monitor 서브파서 등록."""
    p = sub.add_parser(
        "monitor",
        help="Arize Phoenix 기동 + OTLP 스팬 수신 — 실시간 운영 모니터링",
        description=(
            "Arize Phoenix 서버를 기동하고 OpenTelemetry 스팬 수신을 설정합니다.\n"
            "프로덕션 환경의 실시간 트레이싱·스팬 분석·오류 감지에 활용합니다.\n"
            "\n"
            "Phoenix 13.x: UI + OTLP HTTP가 동일 포트(기본 6006) 사용.\n"
            "예제(01~07) 실행 시 자동으로 OTLP 스팬을 전송하며,\n"
            "Phoenix UI의 Tracing 탭에서 예제별 독립 프로젝트로 확인할 수 있습니다.\n"
            "\n"
            "필요 패키지:\n"
            '  pip install "agent-evaluator[otel]"\n'
            "\n"
            "예시:\n"
            "  agent-eval monitor\n"
            "  agent-eval monitor --port 6007\n"
            "  agent-eval monitor --attach http://localhost:6006\n"
            "  agent-eval monitor --check\n"
            "  agent-eval monitor --sync-datasets 'data/golden_datasets/*.json'"
        ),
        formatter_class=_MonitorHelpFormatter,
    )
    p.add_argument(
        "--port",
        type=int,
        default=6006,
        help="Phoenix UI 포트 (기본: 6006) — OTLP HTTP도 동일 포트 수신",
    )
    p.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="바인딩 호스트 (기본: localhost)",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        dest="no_open",
        help="브라우저 자동 오픈 비활성화",
    )
    p.add_argument(
        "--attach",
        type=str,
        metavar="URL",
        default=None,
        help="자체 기동 없이 기존 Phoenix 서버 URL에 연결",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="설치 상태 및 포트 점유 확인",
    )
    p.add_argument(
        "--working-dir",
        type=str,
        default=None,
        dest="working_dir",
        metavar="DIR",
        help="Phoenix DB 저장 디렉토리 (기본: Phoenix 자동 결정 — 보통 ~/.phoenix)",
    )
    p.add_argument(
        "--sync-datasets",
        type=str,
        metavar="GLOB",
        default=None,
        dest="sync_datasets",
        help=(
            "골든셋 JSON 파일을 Phoenix Datasets로 업로드 (glob 패턴 지원).\n"
            "예: --sync-datasets 'data/golden_datasets/*.json'"
        ),
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Phoenix DB 초기화 — 모든 트레이스·프로젝트·데이터셋 삭제 (Phoenix 종료 후 실행)",
    )
    p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="초기화 확인 프롬프트 없이 바로 실행",
    )
    p.set_defaults(func=cmd_monitor)
