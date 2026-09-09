"""
agent_evaluator.cli._integration_health
=======================================
``agent-eval {claude,opencode} doctor / upgrade / uninstall``이 공유하는 헬퍼.

두 installer(``cli/claude.py`` · ``cli/opencode.py``)는 의도적으로 각자 ANSI 헬퍼를
경량 재정의하지만(``main.py``에서 직접 import 불가), doctor/upgrade/uninstall의 실질
로직(설정 deep-merge, 훅 커맨드에서 인터프리터 추출, 서브프로세스 import 프로브, MCP
stdio 핸드셰이크, 체크리스트 렌더링)은 비자명해서 여기 한 곳에 모은다. 새 판정 로직은
없다 — 전부 "이미 설치된 것이 실제로 도는지" 확인·정리하는 순수 운영 계층이다.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 체크리스트 모델
# ---------------------------------------------------------------------------
_STATUS_ICON = {"ok": "✅", "warn": "⚠️", "error": "❌", "info": "•"}


@dataclass
class Check:
    """doctor 체크 한 줄."""

    tier: str  # "static" | "live" | "mcp"
    status: str  # "ok" | "warn" | "error" | "info"
    label: str
    detail: str = ""


@dataclass
class DoctorReport:
    """doctor 체크 결과 누적기 + 렌더러."""

    title: str
    checks: list[Check] = field(default_factory=list)

    def add(self, tier: str, status: str, label: str, detail: str = "") -> None:
        self.checks.append(Check(tier, status, label, detail))

    def ok(self, tier: str, label: str, detail: str = "") -> None:
        self.add(tier, "ok", label, detail)

    def warn(self, tier: str, label: str, detail: str = "") -> None:
        self.add(tier, "warn", label, detail)

    def error(self, tier: str, label: str, detail: str = "") -> None:
        self.add(tier, "error", label, detail)

    def info(self, tier: str, label: str, detail: str = "") -> None:
        self.add(tier, "info", label, detail)

    @property
    def n_errors(self) -> int:
        return sum(1 for c in self.checks if c.status == "error")

    @property
    def n_warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    def exit_code(self, *, strict: bool = False) -> int:
        if self.n_errors:
            return 1
        if strict and self.n_warnings:
            return 1
        return 0

    def render_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "checks": [
                    {"tier": c.tier, "status": c.status, "label": c.label, "detail": c.detail}
                    for c in self.checks
                ],
                "summary": {
                    "errors": self.n_errors,
                    "warnings": self.n_warnings,
                    "passed": sum(1 for c in self.checks if c.status == "ok"),
                },
            },
            indent=2,
        )

    def render_text(self, *, color: bool = True) -> str:
        b = "\033[1m" if color else ""
        d = "\033[2m" if color else ""
        g = "\033[32m" if color else ""
        y = "\033[33m" if color else ""
        rd = "\033[31m" if color else ""
        r = "\033[0m" if color else ""
        tone = {"ok": g, "warn": y, "error": rd, "info": d}

        lines = [f"{b}{self.title}{r}"]
        tier_names = {"static": "Static", "live": "Live", "mcp": "MCP handshake"}
        for tier in ("static", "live", "mcp"):
            tier_checks = [c for c in self.checks if c.tier == tier]
            if not tier_checks:
                continue
            lines.append("")
            lines.append(f"{d}{tier_names[tier]}{r}")
            for c in tier_checks:
                icon = _STATUS_ICON[c.status]
                line = f"  {tone[c.status]}{icon} {c.label}{r}"
                if c.detail:
                    line += f"  {d}{c.detail}{r}"
                lines.append(line)

        lines.append("")
        if self.n_errors:
            summary = f"{rd}{self.n_errors} error(s), {self.n_warnings} warning(s){r}"
        elif self.n_warnings:
            summary = f"{y}{self.n_warnings} warning(s), 0 errors{r}"
        else:
            summary = f"{g}all checks passed{r}"
        lines.append(summary)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 설정 deep-merge (upgrade용 — 사용자 편집 보존)
# ---------------------------------------------------------------------------
def deep_merge_defaults(user: dict, defaults: dict) -> tuple[dict, list[str]]:
    """``defaults``에는 있는데 ``user``에는 없는 키만 재귀적으로 채운다.

    사용자가 이미 넣은 값은 절대 덮어쓰지 않는다(``install --force``와의 핵심 차이).
    리스트는 leaf로 취급한다(요소 단위 병합 안 함).

    Returns:
        ``(병합된 dict, 새로 추가된 키 경로 리스트)``. 원본 ``user``는 변경하지 않는다.
    """
    added: list[str] = []
    merged = json.loads(json.dumps(user))  # deep copy (JSON-safe 설정만 다룸)

    def _merge(dst: dict, src: dict, prefix: str) -> None:
        for k, sv in src.items():
            path = f"{prefix}{k}"
            if k not in dst:
                dst[k] = json.loads(json.dumps(sv))
                added.append(path)
            elif isinstance(dst[k], dict) and isinstance(sv, dict):
                _merge(dst[k], sv, path + ".")

    _merge(merged, defaults, "")
    return merged, added


# ---------------------------------------------------------------------------
# 훅 커맨드 → 인터프리터 경로
# ---------------------------------------------------------------------------
_CMD_PREFIXES = {"nice", "env", "time", "sudo", "exec", "command", "stdbuf"}


def interpreter_from_command(cmd: str) -> str | None:
    """훅 커맨드 문자열에서 파이썬 인터프리터 경로(첫 실행 토큰)를 뽑는다.

    ``nice /x/python -m mod`` / ``env A=b /x/python ...`` 같은 접두 래핑을 건너뛴다.
    파싱 불가면 ``None``.
    """
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    for p in parts:
        if p in _CMD_PREFIXES:
            continue
        if "=" in p and not p.startswith(("/", ".", "~")):
            continue  # `env` 스타일 VAR=VALUE 접두
        return p
    return None


# ---------------------------------------------------------------------------
# 서브프로세스 import 프로브
# ---------------------------------------------------------------------------
def probe_import(python_bin: str, module: str, *, timeout: float = 20.0) -> tuple[bool, str]:
    """``python_bin``으로 ``import module``이 되는지 확인한다.

    Returns:
        ``(성공 여부, 실패 시 마지막 에러 줄)``.
    """
    try:
        proc = subprocess.run(
            [python_bin, "-c", f"import {module}"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"interpreter not found: {python_bin}"
    except subprocess.TimeoutExpired:
        return False, "import timed out"
    except OSError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    last = err.splitlines()[-1] if err else f"exit {proc.returncode}"
    return False, last[:300]


# ---------------------------------------------------------------------------
# MCP stdio 핸드셰이크 프로브
# ---------------------------------------------------------------------------
def mcp_initialize_probe(
    python_bin: str, module: str, expect_tool: str, *, timeout: float = 12.0,
) -> tuple[str, str]:
    """MCP stdio 서버를 띄우고 ``initialize`` → ``initialized`` → ``tools/list`` 핸드셰이크를 한다.

    세 메시지를 한 번에 써 보내고 stdin을 닫은 뒤 ``communicate(timeout=...)``로 모든
    출력을 한꺼번에 읽어 파싱한다 — 버퍼링된 파이프에서 ``select``로 한 줄씩 읽는 것보다
    훨씬 견고하다(MCP stdio 서버는 stdin을 순서대로 처리하고 EOF에서 깔끔히 종료한다).

    MCP는 opt-in이므로 실패는 항상 ``"warn"``이지 ``"error"``가 아니다.

    Returns:
        ``(status, detail)`` — status는 ``"ok"`` 또는 ``"warn"``.
    """
    reqs = "\n".join(
        json.dumps(m) for m in (
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "agent-eval-doctor", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
    ) + "\n"

    try:
        proc = subprocess.Popen(
            [python_bin, "-m", module],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except (FileNotFoundError, OSError) as exc:
        return "warn", f"could not start server: {exc}"

    try:
        out, err = proc.communicate(input=reqs, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()

    if "agent-evaluator[mcp]" in (err or "") or "No module named 'mcp'" in (err or ""):
        return "warn", "the 'mcp' extra is not installed — pip install \"agent-evaluator[mcp]\""

    saw_init = False
    tools: list[str] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or line[0] != "{":
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = msg.get("result") if isinstance(msg, dict) else None
        if not isinstance(result, dict):
            continue
        if "protocolVersion" in result or "serverInfo" in result:
            saw_init = True
        for t in result.get("tools", []):
            if isinstance(t, dict) and t.get("name"):
                tools.append(t["name"])

    if expect_tool in tools:
        return "ok", f"tools: {', '.join(dict.fromkeys(tools))}"
    if tools:
        return "warn", f"'{expect_tool}' not advertised (got: {', '.join(dict.fromkeys(tools))})"
    if saw_init:
        return "warn", "initialize OK but tools/list returned nothing"
    tail = (err or "").strip().splitlines()
    return "warn", "no valid response" + (f" ({tail[-1][:120]})" if tail else "")


# ---------------------------------------------------------------------------
# build_guardrail() 검증 (stderr 경고 캡처)
# ---------------------------------------------------------------------------
def validate_guardrail_config(config: dict) -> tuple[bool, list[str]]:
    """해석된 guardrail 설정을 ``build_guardrail()``에 넣어 실제로 만들어지는지 본다.

    Returns:
        ``(성공 여부, build_guardrail이 stderr로 낸 "SKIPPED" 경고 줄들)``.
    """
    from agent_evaluator.integrations.live_guardrail_stdio import build_guardrail

    cfg = dict(config)
    for bridge_only in ("output_dir", "circuit_breaker_after", "circuit_breaker_recover_after"):
        cfg.pop(bridge_only, None)
    err_buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(err_buf):
            build_guardrail(cfg)
    except Exception as exc:  # noqa: BLE001 — doctor는 모든 실패를 리포트로 흡수
        return False, [f"build_guardrail raised: {exc}"]
    warnings = [
        ln.strip()
        for ln in err_buf.getvalue().splitlines()
        if "SKIPPED" in ln or "invalid" in ln
    ]
    return True, warnings


# ---------------------------------------------------------------------------
# SPEC-041: blocked-attempt capture live round-trip (claude + opencode doctor)
# ---------------------------------------------------------------------------
def probe_blocked_capture(config: dict) -> tuple[str, str]:
    """실제 차단 1건을 흘려 ``arg_excerpt``(PII 마스킹된 명령 발췌)가 잡히는지 본다.

    ``blocked_attempt_capture``가 명시적으로 꺼져 있으면 ``"info"``(정상적인 선택),
    켜져 있는데 발췌가 안 나오거나 마스킹이 안 되면 ``"warn"``.

    Returns:
        ``(status, detail)`` — status는 ``"ok" | "warn" | "info"``.
    """
    from agent_evaluator.gates.live_guardrail import LiveVerdict
    from agent_evaluator.integrations.live_guardrail_stdio import build_guardrail

    cfg = dict(config)
    for bridge_only in ("output_dir", "circuit_breaker_after", "circuit_breaker_recover_after"):
        cfg.pop(bridge_only, None)
    cap = cfg.get("blocked_attempt_capture")
    if isinstance(cap, dict) and not cap.get("enabled", True):
        return "info", "blocked_attempt_capture disabled — blocked-detail falls back to transcripts"
    try:
        guardrail = build_guardrail(cfg)
        entry = guardrail.record_blocked_attempt(
            "doctor-probe", "Bash",
            LiveVerdict(block=True, gate="B", reason="dangerous tool parameters"),
            tool_input={"command": "rm -rf /tmp/x  # reach doctor@example.com"},
        )
    except Exception as exc:  # noqa: BLE001 — doctor absorbs every failure into the report
        return "warn", f"record_blocked_attempt round-trip failed: {exc}"
    excerpt = entry.get("arg_excerpt")
    if not excerpt:
        return "warn", "no arg_excerpt produced (blocked-detail will need host transcripts)"
    if "doctor@example.com" in excerpt:
        return "warn", "arg_excerpt is not PII-redacted"
    return "ok", f"captures a redacted command excerpt ({len(excerpt)} chars)"


# ---------------------------------------------------------------------------
# SPEC-043 REQ-6a: guardrail_config 케이스 기반 검증
#
# `{claude,opencode} doctor`는 고정 시나리오(무해→allow, `rm -rf`→deny 등)만 태운다.
# 이 헬퍼는 프로젝트가 자기 금지/정상 명령 목록을 케이스 파일로 적어 두고, 해석된
# 자기 config가 실제로 그 판정을 내는지 assert하게 한다 (가드레일의 red-green TDD).
# 새 채점 로직 없음 — 이미 있는 `LiveGuardrail.check_before_tool_call`을 그대로 태운다.
# ---------------------------------------------------------------------------
def load_config_cases(path: str) -> list[dict[str, Any]]:
    """test-config 케이스 파일(YAML 또는 JSON)을 파싱해 정규화한다.

    형태: ``{"cases": [{tool, args?, expect: "allow"|"deny", gate?, name?}]}``
    또는 최상위 리스트. 빈 파일 / 빈 ``cases`` → ``[]``.

    Raises:
        ValueError: 파일이 없거나 형식이 잘못된 경우 (사람이 읽을 메시지).
    """
    if not os.path.exists(path):
        raise ValueError(f"case file not found: {path}")
    with open(path, encoding="utf-8") as f:
        text = f.read()

    data: Any = None
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml as _yaml  # type: ignore

            data = _yaml.safe_load(text)
        except ImportError:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "the case file has a .yaml/.yml extension but PyYAML is not "
                    "installed and it is not valid JSON either — run "
                    "`pip install pyyaml` or use a .json case file "
                    f"({exc})"
                ) from exc
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"the case file is not valid JSON: {exc}") from exc

    cases = data.get("cases") if isinstance(data, dict) else data
    if cases is None:
        return []
    if not isinstance(cases, list):
        raise ValueError("expected a `cases` list (or a bare top-level list)")

    out: list[dict[str, Any]] = []
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            raise ValueError(f"case #{i + 1} is not a mapping")
        tool = c.get("tool")
        expect = str(c.get("expect", "")).strip().lower()
        if not tool or expect not in ("allow", "deny"):
            raise ValueError(
                f"case #{i + 1} needs a non-empty `tool` and `expect: allow|deny`"
            )
        args = c.get("args")
        out.append(
            {
                "name": str(c.get("name") or tool),
                "tool": str(tool),
                "args": args if isinstance(args, dict) else {},
                "expect": expect,
                "gate": (str(c["gate"]).strip().upper() if c.get("gate") else None),
            }
        )
    return out


def run_config_tests(
    resolved_cfg: dict[str, Any], cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    """각 케이스를 해석된 config로 만든 LiveGuardrail에 태워 기대 vs 실제를 대조한다.

    ``check_before_tool_call``은 순수 조회(``_tool_calls`` 불변)라 guardrail 하나를
    재사용해도 케이스 간 상태가 새지 않는다.

    Returns:
        ``(rows, all_passed, skipped_config_blocks)`` — 각 row는 ``{name, tool,
        expect, actual, gate_expect, gate_actual, ok, reason}``.
        ``skipped_config_blocks``는 ``build_guardrail``이 오타/잘못된 값 때문에
        건너뛴 config 블록의 경고 줄들 — 이게 비어 있지 않으면 케이스는 *부분*
        config로 돌았다는 뜻이라 호출자가 눈에 띄게 알려야 한다.

    Raises:
        ValueError: config로 guardrail 자체가 만들어지지 않는 경우.
    """
    from agent_evaluator.integrations.live_guardrail_stdio import build_guardrail

    cfg = dict(resolved_cfg)
    for bridge_only in (
        "output_dir", "circuit_breaker_after", "circuit_breaker_recover_after",
    ):
        cfg.pop(bridge_only, None)

    err_buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(err_buf):
            guardrail = build_guardrail(cfg)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not build a guardrail from this config: {exc}") from exc
    skipped = [
        ln.strip() for ln in err_buf.getvalue().splitlines()
        if "SKIPPED" in ln
    ]

    rows: list[dict[str, Any]] = []
    all_ok = True
    for c in cases:
        try:
            verdict = guardrail.check_before_tool_call("test-config", c["tool"], c["args"])
            actual = "deny" if verdict.block else "allow"
            gate_actual = verdict.gate if verdict.block else None
            reason = verdict.reason if verdict.block else ""
        except Exception as exc:  # noqa: BLE001 — a failed row, never a raise
            actual, gate_actual, reason = "error", None, str(exc)
        expect_ok = actual == c["expect"]
        gate_ok = c["gate"] is None or gate_actual == c["gate"]
        ok = expect_ok and gate_ok
        all_ok = all_ok and ok
        rows.append(
            {
                "name": c["name"], "tool": c["tool"],
                "expect": c["expect"], "actual": actual,
                "gate_expect": c["gate"], "gate_actual": gate_actual,
                "ok": ok, "reason": reason,
            }
        )
    return rows, all_ok, skipped


def render_config_test_table(
    rows: list[dict[str, Any]], *, color: bool = True,
) -> str:
    """run_config_tests의 rows를 사람이 읽을 표로 렌더한다."""
    b = "\033[1m" if color else ""
    d = "\033[2m" if color else ""
    g = "\033[32m" if color else ""
    rd = "\033[31m" if color else ""
    r = "\033[0m" if color else ""

    if not rows:
        return f"{d}no cases — nothing to check{r}"

    lines = [f"{b}{'':2} {'case':<28} {'tool':<10} {'expect':<7} {'actual':<7} gate{r}"]
    for row in rows:
        icon = f"{g}PASS{r}" if row["ok"] else f"{rd}FAIL{r}"
        gate = ""
        if row["gate_expect"] or row["gate_actual"]:
            gate = f"{row['gate_expect'] or '-'}→{row['gate_actual'] or '-'}"
        lines.append(
            f"{icon} {row['name'][:28]:<28} {row['tool'][:10]:<10} "
            f"{row['expect']:<7} {row['actual']:<7} {gate}"
        )
        if not row["ok"] and row["reason"]:
            lines.append(f"      {d}{row['reason'][:120]}{r}")

    n_fail = sum(1 for x in rows if not x["ok"])
    lines.append("")
    lines.append(
        f"{g}all {len(rows)} case(s) passed{r}" if not n_fail
        else f"{rd}{n_fail} of {len(rows)} case(s) failed{r}"
    )
    return "\n".join(lines)


def cmd_test_config_common(
    cases_path: str, resolved_cfg: dict[str, Any], *, as_json: bool, color: bool,
) -> int:
    """`{claude,opencode} test-config`의 공유 본체. exit 1 on any mismatch / bad file."""
    try:
        cases = load_config_cases(cases_path)
    except ValueError as exc:
        print(f"\033[31merror:\033[0m {exc}" if color else f"error: {exc}")
        return 1
    try:
        rows, all_ok, skipped = run_config_tests(resolved_cfg, cases)
    except ValueError as exc:
        print(f"\033[31merror:\033[0m {exc}" if color else f"error: {exc}")
        return 1

    if as_json:
        print(json.dumps(
            {"cases": rows, "passed": all_ok, "n_cases": len(rows),
             "n_failed": sum(1 for x in rows if not x["ok"]),
             "skipped_config_blocks": skipped},
            indent=2,
        ))
    else:
        y = "\033[33m" if color else ""
        r = "\033[0m" if color else ""
        for ln in skipped:
            print(f"{y}⚠  {ln}{r}")
        if skipped:
            print(
                f"{y}   → cases below ran against a PARTIAL config "
                f"(fix the block(s) above){r}"
            )
        print(render_config_test_table(rows, color=color))
    return 0 if all_ok else 1
