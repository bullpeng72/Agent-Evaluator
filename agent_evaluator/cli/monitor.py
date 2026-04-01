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


def cmd_monitor(args: argparse.Namespace) -> int:
    """Phoenix 서버 기동 후 OTEL 연결 정보 출력."""
    if args.check:
        return cmd_check_monitor()

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
        help="운영 실시간 모니터링 (Phoenix + OTEL) — pip install agent-evaluator[otel]",
        description=(
            "Arize Phoenix 서버를 기동하고 OpenTelemetry 스팬 수신을 설정합니다.\n"
            "프로덕션 환경의 실시간 트레이싱·스팬 분석·오류 감지에 활용합니다.\n"
            "\n"
            "Phoenix 13.x: UI + OTLP HTTP가 동일 포트(기본 6006) 사용.\n"
            "예제(01~17) 실행 시 자동으로 OTLP 스팬을 전송하며,\n"
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        default="./",
        dest="working_dir",
        help="Phoenix DB 저장 디렉토리 (기본: ./)",
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
    p.set_defaults(func=cmd_monitor)
