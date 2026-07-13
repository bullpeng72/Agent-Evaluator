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
import subprocess
import sys
import time
import webbrowser

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
            prefix = "Usage: "
        return super()._format_usage(usage, actions, groups, prefix)


# ---------------------------------------------------------------------------
# 의존성 / 포트 유틸리티
# ---------------------------------------------------------------------------


def _pkg_installed(import_name: str) -> bool:
    """패키지가 import 가능한지 확인 (실제 import 없이)."""
    return importlib.util.find_spec(import_name) is not None


def _phoenix_version() -> str | None:
    """설치된 arize-phoenix 버전 반환. 미설치 시 None."""
    try:
        from importlib.metadata import version

        return version("arize-phoenix")
    except Exception:
        return None


def _check_deps() -> dict[str, bool]:
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


def _get_pids_on_port(port: int) -> list[int]:
    """포트를 점유 중인 PID 목록 반환 (lsof 사용, 없으면 빈 리스트)."""
    try:
        import subprocess as _sp
        out = _sp.check_output(
            ["lsof", "-ti", f":{port}"],
            stderr=_sp.DEVNULL,
            text=True,
        )
        return [int(p) for p in out.split() if p.isdigit()]
    except Exception:
        return []


def _report_startup_failure(
    proc: subprocess.Popen[bytes],
    output_lines: list[str],
    ui_port: int,
    grpc_port: int,
    host: str,
) -> None:
    """Phoenix 기동 실패 원인을 분석해 사용자 친화적 메시지를 출력한다."""
    returncode = proc.poll()

    # gRPC 포트 충돌 여부 (타임아웃 후 재확인)
    if _port_in_use(grpc_port, host):
        pids = _get_pids_on_port(grpc_port)
        pid_hint = f" (PID {pids[0]})" if pids else ""
        print(f"  ❌  Phoenix startup failed — gRPC port {grpc_port} conflict{pid_hint}")
        print(f"     Another Phoenix instance is occupying port {grpc_port}.")
        print(f"     Fix:  kill $(lsof -ti :{grpc_port})  then retry")
        print("     Or:   PHOENIX_GRPC_PORT=4318 agent-eval monitor")
    elif returncode is not None:
        print(f"  ❌  Phoenix process exited immediately (exitcode={returncode}).")
        error_lines = [
            ln.rstrip() for ln in output_lines
            if any(kw in ln for kw in ("Error", "ERROR", "Exception", "FAILED", "Failed"))
        ]
        if error_lines:
            print("     Error output:")
            for ln in error_lines[:5]:
                print(f"       {ln.strip()}")
        else:
            print("     Run directly to see the error:")
            print(f"       PHOENIX_PORT={ui_port} phoenix serve")
    else:
        print("  ❌  Phoenix server startup timed out (30s).")
        print("     Run directly to see the error:")
        print(f"       PHOENIX_PORT={ui_port} phoenix serve")
        if _port_in_use(grpc_port, host):
            pids = _get_pids_on_port(grpc_port)
            pid_hint = f" (PID {pids[0]})" if pids else ""
            print(f"     Hint: gRPC port {grpc_port} is in use{pid_hint}")
    print()


def _phoenix_cmd() -> list[str]:
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
    print("  Package Status")
    print("  " + "─" * 54)
    for pkg, installed in deps.items():
        if installed:
            suffix = f"  ({_phoenix_version()})" if pkg == "arize-phoenix" else ""
            print(f"  ✅  {pkg:<50} installed{suffix}")
        else:
            print(f"  ❌  {pkg:<50} not installed")
            all_ok = False

    print()
    print("  Port Status  (Phoenix 13.x: UI + OTLP HTTP share the same port)")
    print("  " + "─" * 54)
    for port, label in [(6006, "Phoenix UI / OTLP HTTP"), (4317, "OTLP gRPC")]:
        in_use = _port_in_use(port)
        if in_use:
            print(f"  ⚠️   Port {port:<6} ({label}) — in use (another process)")
        else:
            print(f"  ✅  Port {port:<6} ({label}) — available")

    if not all_ok:
        print()
        print("  Install command:")
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
    print(_row("  Agent Evaluator — Operations Monitoring"))
    print(sep)
    print(_row(f"  Phoenix UI      {ui_url}"))
    print(_row(f"  OTLP HTTP       {otlp_url}"))
    print(sep)
    print(_row("  Add the following to your agent code:"))
    print(_row(""))
    print(_row("  from agent_evaluator import setup_otel"))
    print(_row(f'  setup_otel(endpoint="{otlp_url}")'))
    print(bot)
    print()

    # Phoenix UI does not auto-detect new projects (Relay client limitation).
    # Paste the script below in the browser console for 5-second auto-refresh.
    print("  ── Phoenix Tracing Auto-Refresh ──────────────────────────")
    print("  New projects require a manual refresh in Phoenix UI (UI limitation).")
    print("  Paste the following into the browser console (F12 → Console):")
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
        print(f"\n  ❌  No files found: {pattern}\n")
        return 1

    phoenix_endpoint = f"http://{args.host}:{args.port}"
    builder = GoldenSetBuilder(source_dir=".", output_dir=".")
    success_count = 0

    print(f"\n  Phoenix Datasets upload — {phoenix_endpoint}\n")
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
                print(f"  ⚠️   {filepath}  →  upload complete (no id returned)")
            success_count += 1
        except Exception as exc:
            print(f"  ❌  {filepath}  →  failed: {exc}")

    print(f"\n  Done: {success_count}/{len(files)} uploaded\n")
    return 0 if success_count > 0 else 1


def cmd_reset_db(args: argparse.Namespace) -> int:
    """Phoenix DB 초기화 — 모든 트레이스·프로젝트·데이터셋 삭제."""
    import pathlib

    # 1. DB 경로 결정
    # PHOENIX_SQL_DATABASE_URL이 설정된 경우 PostgreSQL → 파일 삭제 불가
    pg_url = os.environ.get("PHOENIX_SQL_DATABASE_URL", "")
    if pg_url and not pg_url.startswith("sqlite"):
        print()
        print("  ❌  PostgreSQL databases cannot be reset by deleting files.")
        print(f"     PHOENIX_SQL_DATABASE_URL={pg_url}")
        print("     Ask your DB admin to truncate the tables directly.")
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
        print(f"  ℹ️   Phoenix DB file not found: {db_file}")
        print("     (Phoenix has not been run yet, or the DB is already clean)")
        print()
        return 0

    # 3. Phoenix 실행 중 여부 확인
    port = getattr(args, "port", 6006)
    host = getattr(args, "host", "localhost")
    if _port_in_use(port, host):
        print()
        print(f"  ❌  Phoenix is running on port {port}.")
        print("     Stop Phoenix before resetting the DB.")
        print(f"     (Ctrl+C or kill $(lsof -ti :{port}))")
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
    print(f"  Phoenix DB Reset — {working_dir}")
    print()
    for t in targets:
        size = t.stat().st_size if t.is_file() else sum(f.stat().st_size for f in t.rglob("*") if f.is_file())
        print(f"  🗑  {t.name:<24s} ({size/1024:.1f} KB)")
    print()
    print("  ⚠️  All traces, projects, annotations, and datasets will be deleted.")
    print()

    if not getattr(args, "yes", False):
        try:
            ans = input("  Continue? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans not in ("y", "yes"):
            print("  Cancelled.")
            print()
            return 0

    # 6. perform deletion
    for t in targets:
        try:
            if t.is_file():
                t.unlink()
                print(f"  ✅  Deleted: {t}")
            elif t.is_dir():
                shutil.rmtree(t)
                t.mkdir(exist_ok=True)   # recreate empty dir (needed on Phoenix restart)
                print(f"  ✅  Reset: {t}/")
        except Exception as exc:
            print(f"  ❌  Failed: {t}  →  {exc}")
            return 1

    print()
    print("  Phoenix DB reset complete. A new DB will be created on next startup.")
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
        print("  ❌  Required packages are not installed.")
        print(f"     Missing: {', '.join(missing)}")
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

    # Phoenix UI 포트 충돌 확인
    if _port_in_use(port, host):
        print()
        print(f"  ⚠️   Port {port} is already in use.")
        print(f"     To connect to the existing server: agent-eval monitor --attach {ui_url}")
        print()
        return 1

    # gRPC 포트(4317) 사전 충돌 확인
    _GRPC_PORT = int(os.environ.get("PHOENIX_GRPC_PORT", "4317"))
    if _port_in_use(_GRPC_PORT, host):
        pids = _get_pids_on_port(_GRPC_PORT)
        pid_hint = f" (PID {pids[0]} — kill {pids[0]} to stop)" if pids else ""
        print()
        print(f"  ❌  gRPC port {_GRPC_PORT} is already in use.{pid_hint}")
        print(f"     Phoenix uses both UI port ({port}) and gRPC port ({_GRPC_PORT}).")
        print("     Fix:")
        print(f"       1. Stop existing process:  kill $(lsof -ti :{_GRPC_PORT})")
        print("       2. Change gRPC port:        PHOENIX_GRPC_PORT=4318 agent-eval monitor")
        print()
        return 1

    # Phoenix 서버 기동
    print("\n  Agent Evaluator — Starting operations monitoring...\n")
    try:
        env = os.environ.copy()
        env["PHOENIX_PORT"] = str(port)

        cmd = _phoenix_cmd()
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        print(f"  ❌  Phoenix server startup failed: {exc}")
        return 1

    # 서버 준비 대기 (최대 30초)
    # — Phoenix 14.x는 DB 마이그레이션으로 첫 실행 시 수 초 소요
    _startup_output: list = []

    import threading as _threading

    def _drain_output() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            _startup_output.append(line.decode(errors="replace"))

    _drain_thread = _threading.Thread(target=_drain_output, daemon=True)
    _drain_thread.start()

    for _ in range(60):
        # 프로세스가 조기에 종료된 경우 즉시 진단
        if proc.poll() is not None:
            _drain_thread.join(timeout=2)
            _report_startup_failure(proc, _startup_output, port, _GRPC_PORT, host)
            return 1
        if _port_in_use(port, host):
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        _drain_thread.join(timeout=2)
        _report_startup_failure(proc, _startup_output, port, _GRPC_PORT, host)
        return 1

    _print_connect_info(ui_url, otlp_url)

    if not args.no_open:
        webbrowser.open(ui_url)

    # 새 프로젝트 감지 — 백그라운드 폴링 스레드
    # Phoenix UI가 자동 갱신을 지원하지 않으므로 터미널에서 알림 출력
    import threading

    def _watch_projects(base_url: str) -> None:
        import json as _json
        import urllib.request

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
                        print(f"\n  🆕  New project detected: [{n}]  → Refresh browser (F5) or run the console script")
                    known = names
            except Exception:
                pass  # Phoenix 재시작 중이면 조용히 무시

    watcher = threading.Thread(target=_watch_projects, args=(ui_url,), daemon=True)
    watcher.start()

    print("  Press Ctrl+C to stop\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  Monitoring server stopped.")

    return 0


# ---------------------------------------------------------------------------
# 서브파서 등록 (main.py 에서 호출)
# ---------------------------------------------------------------------------


def build_monitor_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """main.py에서 호출 — monitor 서브파서 등록."""
    p = sub.add_parser(
        "monitor",
        help="Start Arize Phoenix + OTLP span receiver — real-time operations monitoring",
        description=(
            "Start an Arize Phoenix server and configure OpenTelemetry span reception.\n"
            "Use for real-time tracing, span analysis, and error detection in production.\n"
            "\n"
            "Phoenix 13.x: UI + OTLP HTTP share the same port (default 6006).\n"
            "Examples (01~07) automatically send OTLP spans;\n"
            "each example appears as an independent project in the Phoenix UI Tracing tab.\n"
            "\n"
            "Required packages:\n"
            '  pip install "agent-evaluator[otel]"\n'
            "\n"
            "Examples:\n"
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
        help="Phoenix UI port (default: 6006) — OTLP HTTP also listens on this port",
    )
    p.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Bind host (default: localhost)",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        dest="no_open",
        help="Disable automatic browser launch",
    )
    p.add_argument(
        "--attach",
        type=str,
        metavar="URL",
        default=None,
        help="Connect to an existing Phoenix server URL without starting one",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Check installation status and port availability",
    )
    p.add_argument(
        "--working-dir",
        type=str,
        default=None,
        dest="working_dir",
        metavar="DIR",
        help="Phoenix DB directory (default: auto-determined by Phoenix — usually ~/.phoenix)",
    )
    p.add_argument(
        "--sync-datasets",
        type=str,
        metavar="GLOB",
        default=None,
        dest="sync_datasets",
        help=(
            "Upload golden-set JSON files to Phoenix Datasets (glob patterns supported).\n"
            "Example: --sync-datasets 'data/golden_datasets/*.json'"
        ),
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Reset Phoenix DB — delete all traces, projects, and datasets (stop Phoenix first)",
    )
    p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the reset confirmation prompt",
    )
    p.set_defaults(func=cmd_monitor)
