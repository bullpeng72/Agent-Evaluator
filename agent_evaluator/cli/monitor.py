"""
agent-eval monitor — 운영 실시간 모니터링 (Phoenix + OTEL)

사용법:
    agent-eval monitor                      # Phoenix 기동 + 브라우저 오픈
    agent-eval monitor --port 6006          # 포트 지정
    agent-eval monitor --otlp-port 4318     # OTLP receiver 포트 지정
    agent-eval monitor --no-open            # 브라우저 자동 오픈 비활성화
    agent-eval monitor --attach <url>       # 기존 Phoenix 서버에 연결
    agent-eval monitor --check              # 설치 상태 및 포트 점유 확인
"""

from __future__ import annotations

import argparse
import importlib.util
import socket
import sys
import time
import webbrowser
from typing import Dict


# ---------------------------------------------------------------------------
# 의존성 / 포트 유틸리티
# ---------------------------------------------------------------------------


def _pkg_installed(import_name: str) -> bool:
    """패키지가 import 가능한지 확인 (실제 import 없이)."""
    return importlib.util.find_spec(import_name) is not None


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


# ---------------------------------------------------------------------------
# --check 모드
# ---------------------------------------------------------------------------


def cmd_check_monitor() -> int:
    """--check: 설치 상태 및 포트 점유 확인."""
    deps = _check_deps()
    all_ok = True

    print()
    print("  패키지 상태")
    print("  " + "─" * 50)
    for pkg, installed in deps.items():
        if installed:
            print(f"  ✅  {pkg:<50} 설치됨")
        else:
            print(f"  ❌  {pkg:<50} 미설치")
            all_ok = False

    print()
    print("  포트 상태")
    print("  " + "─" * 50)
    for port, label in [(6006, "Phoenix UI"), (4318, "OTLP Receiver")]:
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
    print(f"""
  ┌─────────────────────────────────────────────────────────┐
  │  Agent Evaluator — 운영 모니터링                        │
  ├─────────────────────────────────────────────────────────┤
  │  Phoenix UI      {ui_url:<40} │
  │  OTLP Receiver   {otlp_url:<40} │
  ├─────────────────────────────────────────────────────────┤
  │  에이전트 코드에 아래를 추가하세요:                      │
  │                                                         │
  │  from agent_evaluator import setup_otel                 │
  │  setup_otel(endpoint="{otlp_url}")        │
  └─────────────────────────────────────────────────────────┘
""")


# ---------------------------------------------------------------------------
# monitor 메인 핸들러
# ---------------------------------------------------------------------------


def cmd_monitor(args: argparse.Namespace) -> int:
    """Phoenix 서버 기동 후 OTEL 연결 정보 출력."""
    if args.check:
        return cmd_check_monitor()

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
    otlp_port: int = args.otlp_port
    host: str = args.host
    ui_url = f"http://{host}:{port}"
    otlp_url = f"http://{host}:{otlp_port}"

    # --attach 모드: 자체 기동 없이 기존 서버에 연결
    if args.attach:
        ui_url = args.attach.rstrip("/")
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
    print(f"\n  Agent Evaluator — 운영 모니터링 기동 중...\n")
    try:
        import subprocess

        proc = subprocess.Popen(
            [sys.executable, "-m", "phoenix.server.main", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"  ❌  Phoenix 서버 기동 실패: {exc}")
        return 1

    # 서버 준비 대기 (최대 10초)
    for _ in range(20):
        if _port_in_use(port, host):
            break
        time.sleep(0.5)
    else:
        print("  ❌  Phoenix 서버 기동 시간 초과.")
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
            "필요 패키지:\n"
            '  pip install "agent-evaluator[otel]"\n'
            "\n"
            "예시:\n"
            "  agent-eval monitor\n"
            "  agent-eval monitor --port 6006 --otlp-port 4318\n"
            "  agent-eval monitor --attach http://localhost:6006\n"
            "  agent-eval monitor --check"
        ),
    )
    p.add_argument(
        "--port",
        type=int,
        default=6006,
        help="Phoenix 웹 UI 포트 (기본: 6006)",
    )
    p.add_argument(
        "--otlp-port",
        type=int,
        default=4318,
        dest="otlp_port",
        help="OTLP HTTP receiver 포트 (기본: 4318)",
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
    p.set_defaults(func=cmd_monitor)
