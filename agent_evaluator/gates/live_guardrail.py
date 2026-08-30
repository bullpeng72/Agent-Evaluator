"""
agent_evaluator.gates.live_guardrail
=======================================
SPEC-019: 실시간 가드레일 API — tool-call 단위 동기 Gate B/E 판정.

Rollout 1-3단계(Gate B 4종 + Gate E 3종) 구현. Gate B 판정 로직은
``gates/gate_b_behavioral/evaluators.py``의 기존 순수 함수(``eval_loop_detection``/
``eval_deadlock``/``eval_scope``/``eval_tool_parameter_safety``)를, Gate E
판정 로직은 ``core/trackers/security.py``의 기존 트래커(``ToolAuthorizationTracker``/
``PrivilegeEscalationDetector``/``ToolChainAttackDetector``)를 그대로 재사용한다 —
새 탐지 로직을 만들지 않는다(SPEC-019 Non-Goals, SPEC-018과 동일한 "재해석 금지" 원칙).

Gate E 트래커는 (Gate B 순수 함수와 달리) 호출마다 내부 상태를 누적하는
스테이트풀 객체다. ``core/trackers/monitor.py:1877-1947``의 배치 경로를 직접
대조한 결과, 이 트래커들의 호출 카디널리티는 둘로 나뉜다:

- ``ToolAuthorizationTracker.track_tool_call``: 도구 호출 1건당 1회
  (``monitor.py:1892``, ``task_result.tool_calls`` 순회).
- ``PrivilegeEscalationDetector.analyze_privilege_chain`` /
  ``ToolChainAttackDetector.analyze_tool_chain``: 태스크(세션)당 정확히 1회,
  **완결된 전체** tool 시퀀스를 인자로(``monitor.py:1926,1943``).

이 카디널리티를 실시간 경로에서도 그대로 지키기 위해:

- :meth:`record_tool_call`(확정)은 ``track_tool_call``을 실제로 호출해
  ``ToolAuthorizationTracker`` 내부 로그에 반영한다(배치와 동일하게 "확정된
  호출 1건당 1회").
- :meth:`check_before_tool_call`(순수 조회)과 :meth:`snapshot`은 두 체인
  분석기를 호출한 뒤 그 호출이 남긴 로그 1건을 즉시 되돌린다(pop) — 그래야
  "아직 실행 안 된 후보"를 미리 엿보거나 ``snapshot()``을 여러 번 호출해도
  체인 분석기 내부 이력이 중복 누적되지 않는다(둘 다 태스크당 1회라는
  배치 카디널리티를 실시간에서도 어기지 않기 위함).
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import dataclasses
import functools
import hashlib
import inspect
import json
import re
import warnings
from typing import Any, Callable

from agent_evaluator.core.trackers.security import (
    PrivilegeEscalationDetector,
    ToolAuthorizationTracker,
    ToolChainAttackDetector,
)
from agent_evaluator.gates.branch_guard import (
    BranchGuardConfig,
    get_current_branch,
    is_branch_protected,
    matches_git_mutation,
)
from agent_evaluator.gates.gate_b_behavioral import evaluators as gate_b_evaluators
from agent_evaluator.gates.gate_b_behavioral.configs import (
    DeadlockConfig,
    LoopDetectionConfig,
    ScopeConfig,
    ToolParameterSafetyConfig,
)
from agent_evaluator.gates.team_concurrency import (
    TeamConcurrencyConfig,
    _load_shared_files,
    _scopes_overlap,
    extract_path_param,
    load_active_claims,
    resolve_owner,
)

_REMEDIATION_KIND_MAP: tuple[tuple[str, str], ...] = (
    # reason 접두어(부분 일치) → COMPONENT_GUIDANCE 키
    ("loop_detection", "loop_detection"),
    ("deadlock", "deadlock"),
    ("scope violation", "scope_score"),
    ("dangerous tool parameters", "tool_parameter_safety"),
    ("tool_authorization", "scope_score"),
    ("privilege_escalation", "threat_severity"),
    ("tool_chain_attack", "threat_severity"),
    ("protected write path", "threat_severity"),
    ("branch", "scope_score"),
    ("team scope", "scope_score"),
)

_REMEDIATION_TAIL = (
    " Do not repeat the identical call — change your approach. Use the recommend_fix / "
    "search_violations MCP tools to check past blocks and fixes for this kind of issue."
)


def _derive_remediation(gate: str | None, reason: str | None) -> str | None:
    """차단 사유에서 에이전트가 바로 실행할 수 있는 조치 문구를 만든다.

    ``ontology.metric_registry.COMPONENT_GUIDANCE``(개발자용 조치 지식)를 재사용하되,
    끝에 "반복하지 말고 접근을 바꿔라 + MCP 도구를 써라"를 붙여 에이전트가 다음 행동을
    고를 수 있게 한다. 새 판정/지식이 아니라 기존 지식의 재포장이다.
    """
    if not reason:
        return None
    r = reason.lower()
    key = next((k for pre, k in _REMEDIATION_KIND_MAP if pre in r), None)
    base = ""
    if key:
        try:
            from agent_evaluator.ontology.metric_registry import component_guidance_for

            base = component_guidance_for(key) or ""
        except Exception:
            base = ""
    if not base:
        base = f"This tool call was blocked by a Gate {gate or '?'} rule violation."
    return base + _REMEDIATION_TAIL


@dataclasses.dataclass
class LiveVerdict:
    """``LiveGuardrail.check_before_tool_call()``의 반환값 (SPEC-019 Interface).

    ``remediation``(SPEC-041): ``block=True``이고 미지정이면 ``__post_init__``이
    ``reason``에서 자동 도출한다 — 차단 메시지가 "무엇이 막혔나"에 더해 "그래서 뭘
    하라"까지 담게 하려는 것. 명시적으로 넘기면 그 값을 그대로 쓴다. ``block=False``면
    항상 ``None``. ``dataclasses.asdict``로 stdio 브리지·훅에 그대로 실려 나간다.
    """

    block: bool
    gate: str | None = None  # "B" | "E" | None
    reason: str | None = None
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)
    remediation: str | None = None

    def __post_init__(self) -> None:
        if self.block and not self.remediation:
            self.remediation = _derive_remediation(self.gate, self.reason)
        elif not self.block:
            self.remediation = None


class LiveGuardrail:
    """세션 단위 실시간 가드레일 (SPEC-019).

    ``PerformanceMonitor.record_task()``/``generate_report()`` 배치 사이클과
    무관하게, 개별 도구 호출 단위로 Gate B 규칙 기반 평가를 동기 실행한다.

    세션(에이전트 루프 1회 실행)마다 별도 인스턴스를 사용할 것 — 내부
    상태(``_tool_calls``)에 락을 두지 않으므로 여러 세션이 하나의 인스턴스를
    공유하면 안 된다(SPEC-019 REQ-7. ``PerformanceMonitor.self._lock``과는
    다른 동시성 모델).
    """

    def __init__(
        self,
        loop_detection: LoopDetectionConfig | None = None,
        deadlock: DeadlockConfig | None = None,
        scope: ScopeConfig | None = None,
        tool_parameter_safety: ToolParameterSafetyConfig | None = None,
        tool_authorization: ToolAuthorizationTracker | None = None,
        privilege_escalation: PrivilegeEscalationDetector | None = None,
        tool_chain_attack: ToolChainAttackDetector | None = None,
        # SPEC-031 REQ-1: record_tool_call(output=...)로 넘어온 stdout/stderr를
        # 이 길이로 truncate한다 — judge_max_context_chars와 동일한 길이 제한 원칙.
        max_tool_output_chars: int = 2000,
        # SPEC-032 REQ-3: 다중 세션 스코프 충돌 감지(축소 범위) — 설정되면 생성자
        # 시점에 claims_path/shared_files_path를 1회만 읽어 캐싱한다(매 호출 재조회
        # 없음 — check_before_tool_call()의 순수 조회 계약 유지).
        team_concurrency: TeamConcurrencyConfig | None = None,
        # SPEC-035: 보호 브랜치(main/master) git commit/push 차단 — 설정되면 생성자
        # 시점에 현재 브랜치를 1회만 조회해 캐싱한다(team_concurrency와 동일 원칙).
        branch_guard: BranchGuardConfig | None = None,
        # SPEC-041: 실시간 루프 판정(check_before_tool_call)에만 적용되는 두 knob.
        # snapshot()/배치 경로는 전혀 건드리지 않는다.
        #
        # live_loop_window — check_before_tool_call()이 루프를 판정할 때 볼 최근 호출
        #   개수(트레일링 윈도우). None이면 세션 전체 이력을 본다(구 동작). 기본값 15는
        #   "직전 15호출 안에서만 루프를 따진다"는 뜻 — 세션 초반의 일시적 반복 하나가
        #   세션 끝까지 모든 도구 호출을 막아버리는 latch(래치) 현상을 없앤다. 배치
        #   snapshot()은 여전히 전체 이력을 본다(리포트 정확도 유지).
        # live_loop_blocking_types — on_loop_detected="fail"일 때 실제로 *차단*할 루프
        #   타입. 기본값은 "consecutive_repeat"(진짜 타이트 무한 루프)뿐 —
        #   "window_duplicate"(최근 N호출 중 같은 도구 M회)는 정상적인 반복 편집·테스트
        #   에서도 흔히 발생하는 소프트 신호라, fail 설정이어도 차단하지 않고 snapshot
        #   리포트에만 남긴다. 옛 동작(모든 타입 차단)이 필요하면
        #   ("consecutive_repeat", "window_duplicate", "response_similarity")로 넘긴다.
        live_loop_window: int | None = 15,
        live_loop_blocking_types: tuple[str, ...] = ("consecutive_repeat",),
        # SPEC-041: tool_authorization의 하드코딩 백스톱(ToolAuthorizationTracker —
        # rm -rf/sudo/eval(/DROP TABLE 등, 커스터마이즈 불가)은 도구 이름과 무관하게
        # 모든 파라미터의 JSON 직렬화 문자열을 스캔한다. 그래서 Write/Edit/NotebookEdit로
        # "파일 내용"을 쓸 때 그 내용에 위 문자열이 들어 있으면(예: `sudo apt install`을
        # 문서화한 README, `rm -rf ./build`가 든 배포 스크립트, `DROP TABLE`이 든 SQL
        # 마이그레이션, `eval(`이 든 파이썬 파일) 정상적인 파일 생성이 통째로 차단된다.
        # 아래 키에 담긴 값은 이 백스톱 스캔에서 제외한다 — 파일에 위험 명령을 *쓰는*
        # 것 자체는 무해하고(실행돼야 위험하다), 실행은 Bash 도구에서 별도로 잡힌다.
        # ()를 넘기면 옛 동작(파일 내용까지 스캔)으로 되돌아간다.
        #
        # 커버하는 파일-내용/패치 키 (실제 도구 스키마에서 확인):
        #   Claude Code  — Write.content, Edit.old_string/new_string, NotebookEdit.new_source
        #   OpenCode     — write.content, edit.oldString/newString, patch.patchText
        #   흔한 MCP 에디터 — file_text/fileText/contents/diff/patch
        #   TodoWrite.todos — 할 일 텍스트에 "rm -rf 정리" 같은 문구가 들어가면 오탐되던 것 방지
        auth_scan_skip_keys: tuple[str, ...] = (
            "content", "contents",
            "old_string", "new_string", "old_str", "new_str",
            "oldString", "newString", "oldText", "newText",
            "new_source", "file_text", "fileText",
            "patch", "patchText", "diff",
            "edits", "replacement", "todos",
        ),
        # SPEC-041: 셸 명령이 "순수한 파일 쓰기"(cat/tee/echo/printf로 리다이렉트,
        # 셸 연산자·명령치환·파이프 없음)면 그 안의 dangerous_patterns/백스톱 매치를
        # *차단하지 않는다* — `cat > deploy.sh <<'EOF' ... rm -rf ./dist ... EOF`처럼
        # 파일 *내용*에 위험 문자열이 있을 뿐 실행되는 게 아니기 때문이다. Write/Edit로
        # 같은 파일을 만드는 것과 동일하게 취급한다. 파이프(`| sh`)·`;`·`&&`·`$(...)`·
        # 백틱이 하나라도 있으면 이 완화는 적용되지 않아 여전히 스캔·차단된다.
        # ()나 False로 끄면 옛 동작(heredoc 본문까지 스캔해 차단).
        lenient_shell_file_write: bool = True,
        # SPEC-041: 파일 *내용*이 아니라 *위치*가 민감한 쓰기를 차단한다 — Write/Edit/
        # NotebookEdit/MCP-write, 그리고 순수 셸 쓰기(`> TARGET`/`tee TARGET`)의 대상
        # 경로가 아래 정규식 중 하나에 매치되면 Gate E로 block. 에이전트가 조용히
        # 셸 rc·SSH 키·크론·systemd·/etc 등에 파일을 심는 것을 막는다(내용 스캔과 무관).
        # None/()이면 이 검사를 끈다. dangerous_patterns처럼 커스터마이즈 가능.
        protected_write_paths: tuple[str, ...] | None = (
            r"(^|/)\.ssh/", r"(^|/)authorized_keys$",
            r"(^|/)\.aws/(credentials|config)$", r"(^|/)\.gnupg/",
            r"(^|/)\.(bash|zsh)rc$", r"(^|/)\.(bash_profile|bash_login|zprofile|profile)$",
            r"(^|/)\.zshenv$", r"(^|/)\.config/fish/",
            r"^/etc/", r"^/usr/", r"^/bin/", r"^/sbin/", r"^/boot/",
            r"(^|/)cron\.(d|daily|hourly|weekly|monthly)/", r"(^|/)var/spool/cron/",
            r"(^|/)Library/Launch(Daemons|Agents)/",
        ),
    ) -> None:
        self._loop_detection = loop_detection
        # <=0은 "제한 없음"(None)으로 정규화 — lst[-0:]가 전체를 반환하는 함정 방지.
        self._live_loop_window = (
            live_loop_window if (live_loop_window is None or live_loop_window > 0) else None
        )
        self._live_loop_blocking_types = tuple(live_loop_blocking_types or ())
        self._auth_scan_skip_keys = frozenset(auth_scan_skip_keys or ())
        self._lenient_shell_file_write = bool(lenient_shell_file_write)
        self._protected_write_re: re.Pattern | None = None
        if protected_write_paths:
            _valid = [p for p in protected_write_paths if isinstance(p, str) and p.strip()]
            if _valid:
                try:
                    self._protected_write_re = re.compile("|".join(f"(?:{p})" for p in _valid))
                except re.error:
                    self._protected_write_re = None
        self._deadlock = deadlock
        self._scope = scope
        self._tool_parameter_safety = tool_parameter_safety
        self._tool_authorization = tool_authorization
        self._privilege_escalation = privilege_escalation
        self._tool_chain_attack = tool_chain_attack
        # 음수면 value[:-n]이 뒤에서 잘리는 함정 — 0으로 클램프(0이면 stdout/stderr 미기록).
        try:
            self._max_tool_output_chars = max(0, int(max_tool_output_chars))
        except (TypeError, ValueError):
            self._max_tool_output_chars = 2000
        self._team_concurrency = team_concurrency
        self._team_claims: list[dict[str, Any]] = []
        self._shared_files: list[str] = []
        # SPEC-037: owner="auto" 센티널은 생성자 시점에 git config user.name을
        # 1회 조회해 해석한다(team_claims 로딩과 동일한 "1회만" 원칙). 원본
        # TeamConcurrencyConfig 객체는 변경하지 않는다 — 호출자가 같은 config를
        # 재사용하거나 다른 LiveGuardrail 인스턴스에 공유해도 원본 owner="auto"가
        # 그대로 보존된다.
        self._team_concurrency_owner: str | None = None
        if self._team_concurrency is not None:
            self._team_claims = load_active_claims(self._team_concurrency.claims_path)
            self._shared_files = _load_shared_files(self._team_concurrency.shared_files_path)
            self._team_concurrency_owner = resolve_owner(self._team_concurrency.owner)
        self._branch_guard = branch_guard
        self._current_branch: str | None = None
        # SPEC-041: recheck_branch=True(기본)면 git 변경이 임박한 check 시점에 브랜치를
        # 다시 조회한다 — 상주 프로세스(OpenCode stdio)에서 세션 중 `git checkout main`
        # 후 `git commit`이 (세션 시작 시 캐시된 feature 브랜치 기준으로) 통과되던
        # 구멍을 막는다. git 서브프로세스는 커밋/푸시 직전에만 1회 도는 저비용이다.
        # False면 생성자 시점 1회 조회값을 계속 쓴다(구 동작).
        self._recheck_branch = getattr(branch_guard, "recheck_branch", True) if branch_guard else False
        if self._branch_guard is not None:
            self._current_branch = get_current_branch()
        self._tool_calls: list[dict[str, Any]] = []
        # SPEC-030: 완전 차단된 시도의 감사 이력 — Gate B/E 점수 계산(self._tool_calls
        # 기반)과 완전히 분리된 별도 목록. check_before_tool_call()은 이 목록을
        # 건드리지 않는다(순수 조회 계약 유지) — record_blocked_attempt()를 호출자가
        # 명시적으로 호출해야만 채워진다.
        self._blocked_attempts: list[dict[str, Any]] = []
        self._task_id: str | None = None

    # SPEC-041: "순수한 파일 쓰기"로 인정하는 셸 명령 감지 (아래 _is_benign_shell_file_write).
    _PRODUCER_RE = re.compile(r"^\s*(?:cat|printf|echo)\b")          # 파일 내용 생성기
    _WRITE_TOOL_RE = re.compile(r"^\s*(?:cat|tee|printf|echo)\b")    # 리다이렉트로 쓰는 도구
    _TEE_SINK_RE = re.compile(r"^\s*(?:sudo\s+)?tee\b")             # `| tee [-a] FILE`
    _HEREDOC_START_RE = re.compile(r"<<[-~]?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
    _FD_REDIR_RE = re.compile(r"\d*>&\d*|&>>?|>&")
    # 껍데기(heredoc 본문·따옴표·fd리다이렉트·`>/dev/null` 제거, `|` 로 분리 후) 세그먼트에
    # 남으면 "실행 가능"으로 보는 토큰: 백틱 · $( · ; · && · || · 프로세스치환 <( >( · 백그라운드 &
    _SHELL_EXEC_TOKEN_RE = re.compile(r"[`;]|\$\(|&&|\|\||[<>]\(|(?<!\d)&(?!\d)")
    _BASH_TOOL_NAMES = frozenset(
        {"bash", "shell", "shell_exec", "sh", "run_shell", "run_command", "command"}
    )

    def _is_benign_shell_file_write(self, tool_name: str, parameters: dict | None) -> bool:
        """이 호출이 "위험 문자열이 들었더라도 파일 *내용*일 뿐"인 순수 파일 쓰기인가?

        heredoc(``cat > f <<'EOF' ... EOF``)·리다이렉트(``echo '...' > f``)·
        ``echo '...' | tee f`` / ``... | sudo tee /etc/f`` 로 파일을 만드는 정상 작업이
        본문 속 ``rm -rf``/``sudo``/``DROP TABLE`` 등 때문에 차단되던 오탐을 막는다.

        판정(모두 만족해야 True):
          - cat/tee/printf/echo 로 시작
          - ``>``/``>>``/``<<`` 리다이렉트 또는 ``| tee`` 싱크가 있음
          - heredoc 본문·따옴표·fd 리다이렉트·``>/dev/null`` 을 들어낸 파이프라인
            세그먼트에 실행 유발 토큰(`` ` `` ``$(`` ``;`` ``&&`` ``||`` ``<(`` ``>(``
            백그라운드 ``&``)이 없음. 파이프는 정확히 ``producer | tee FILE`` 한 단계만 허용.
          - 따옴표 없는 ``<<EOF`` 본문에 ``$()``·백틱이 있으면(실행됨) False.

        따라서 ``cat <<EOF | sh``, ``echo x > f; rm -rf /``, ``echo $(rm -rf /) > f``,
        ``echo x | tee f | sh`` 는 여전히 스캔·차단되지만, SQL/JS/셸 스크립트처럼 본문에
        ``;``·``|`` 가 든 파일을 heredoc/redirect/``| tee`` 로 쓰는 것은 통과한다."""
        if not self._lenient_shell_file_write:
            return False
        if tool_name.lower() not in self._BASH_TOOL_NAMES:
            return False
        if not isinstance(parameters, dict):
            return False
        _cmd = parameters.get("command") or parameters.get("cmd") or parameters.get("script")
        if not isinstance(_cmd, str) or not self._WRITE_TOOL_RE.match(_cmd):
            return False

        # 1) heredoc 본문(리터럴)을 들어낸다. 따옴표 없는 <<EOF 본문의 $()·백틱은 실행됨.
        shell = _cmd
        for _m in self._HEREDOC_START_RE.finditer(_cmd):
            _quoted = bool(_m.group(1))
            _delim = _m.group(2)
            _after = _cmd[_m.end():]
            _nl = _after.find("\n")
            if _nl == -1:
                continue
            _end = re.search(rf"\n[ \t]*{re.escape(_delim)}[ \t]*(?:\n|$)", _after)
            _body = _after[_nl + 1: _end.start() + 1] if _end else _after[_nl + 1:]
            if _body:
                if not _quoted and re.search(r"\$\(|`", _body):
                    return False
                shell = shell.replace(_body, " ", 1)
        # 2) 따옴표 span(리터럴) 제거.
        shell = re.sub(r"'[^']*'", " ", shell)
        shell = re.sub(r'"(?:[^"\\]|\\.)*"', " ", shell)
        # 3) 무해한 fd 리다이렉트(2>&1, >&2, &>)와 `>/dev/null` 제거.
        shell = self._FD_REDIR_RE.sub(" ", shell)
        shell = re.sub(r">>?\s*/dev/null", " ", shell)

        _segs = shell.split("|")
        if len(_segs) == 1:
            _s = _segs[0]
            if ">" not in _s and "<<" not in _s:
                return False  # 어디에도 안 쓴다
            return not self._SHELL_EXEC_TOKEN_RE.search(_s)
        if len(_segs) == 2:
            # producer | tee [-a] FILE  (echo/printf/cat → tee, 그 뒤에 아무것도 없음)
            _prod, _sink = _segs
            if not self._PRODUCER_RE.match(_prod) or not self._TEE_SINK_RE.match(_sink):
                return False
            return not self._SHELL_EXEC_TOKEN_RE.search(_prod + " " + _sink)
        return False  # 파이프가 2단계 이상 — 순수 쓰기가 아니다

    # Write류 도구가 대상 경로를 담는 파라미터 키.
    _WRITE_TARGET_KEYS = ("file_path", "filePath", "path", "notebook_path", "notebookPath")
    # 순수 셸 쓰기에서 대상 경로를 뽑는 패턴: `> PATH`, `>> PATH`, `tee [-옵션] PATH`.
    # 대상은 따옴표로 감쌀 수 있으므로("공백 있는 경로") 3-way 대안으로 잡는다.
    # bare 토큰에서 `(`·백틱은 제외하지만 `$`는 허용 — `> $HOME/.ssh/x`(변수 확장
    # 대상)를 놓치지 않기 위해. `$(...)`는 `(`에서 잘려 무해한 `$`만 남고, 명령치환
    # 자체는 _SHELL_EXEC_TOKEN_RE/dangerous_patterns가 따로 잡는다.
    _QUOTED_OR_BARE = r"""(?:"([^"]+)"|'([^']+)'|([^\s|;&<>()`]+))"""
    _TOKEN_RE = re.compile(_QUOTED_OR_BARE)
    _SHELL_REDIR_TARGET_RE = re.compile(r">>?\s*" + _QUOTED_OR_BARE)
    _TEE_TARGET_RE = re.compile(r"\btee\b(?:\s+-[a-zA-Z]+)*\s+" + _QUOTED_OR_BARE)
    # 리다이렉트가 아니라 *인자*로 목적지를 받는 파일-쓰기/이동 명령들.
    # 대상 경로만 protected_write_paths 매칭에 쓴다(내용 스캔 아님) — `> FILE` 대신
    # `sed -i FILE`/`cp x FILE`로 우회해 민감 경로에 심는 걸 막는다.
    _INPLACE_EDIT_RE = re.compile(r"\b(?:sed|perl|ruby)\b.*?\s-\S*i\S*\s(.*)$", re.DOTALL)
    _DEST_ARG_CMD_RE = re.compile(
        r"^\s*(?:(?:sudo|command|nohup|time|env)\s+(?:\w+=\S+\s+)*)*"
        r"(cp|mv|install|rsync|ln|truncate)\b(.*)$",
        re.DOTALL,
    )
    _DD_OF_RE = re.compile(r"\bof=" + _QUOTED_OR_BARE)

    def _extract_write_targets(self, tool_name: str, parameters: dict | None) -> list[str]:
        """이 호출이 파일을 쓴다면 그 대상 경로들을 반환한다(아니면 빈 리스트).

        Write/Edit/NotebookEdit/MCP-write는 파라미터 키에서, 순수 셸 쓰기
        (``> PATH`` / ``>> PATH`` / ``tee PATH``)는 명령 문자열에서 파싱한다."""
        if not isinstance(parameters, dict):
            return []
        _targets: list[str] = []
        for _k in self._WRITE_TARGET_KEYS:
            _v = parameters.get(_k)
            if isinstance(_v, str) and _v:
                _targets.append(_v)
        _cmd = parameters.get("command") or parameters.get("cmd") or parameters.get("script")
        if isinstance(_cmd, str) and tool_name.lower() in self._BASH_TOOL_NAMES:
            # heredoc 본문을 걷어낸 뒤(본문 안 `>`는 리다이렉트가 아님) 대상만 뽑는다.
            _c = _cmd
            for _m in self._HEREDOC_START_RE.finditer(_cmd):
                _aft = _cmd[_m.end():]
                _nl = _aft.find("\n")
                if _nl == -1:
                    continue
                _e = re.search(rf"\n[ \t]*{re.escape(_m.group(2))}[ \t]*(?:\n|$)", _aft)
                _body = _aft[_nl + 1: _e.start() + 1] if _e else _aft[_nl + 1:]
                if _body:
                    _c = _c.replace(_body, " ", 1)
            _c = re.sub(r">>?\s*/dev/null", " ", _c)
            _c = self._FD_REDIR_RE.sub(" ", _c)
            # `> "/etc/x"` 처럼 따옴표로 감싼 대상도 잡는다(B26에서 따옴표를 통째로
            # 지웠더니 `echo x > "/etc/passwd"`의 실제 대상을 놓치는 회귀가 있었다).
            for _rx in (self._SHELL_REDIR_TARGET_RE, self._TEE_TARGET_RE):
                for _grp in _rx.findall(_c):
                    _t = next((g for g in _grp if g), "").strip()
                    if _t and _t != "/dev/null":
                        _targets.append(_t)
            _targets.extend(self._extract_nonredir_write_targets(_c))
        return _targets

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        """따옴표/bare 토큰만 뽑는다(옵션 플래그 `-x`·`=` 포함 토큰 제외)."""
        _out: list[str] = []
        for _grp in cls._TOKEN_RE.findall(text):
            _t = next((g for g in _grp if g), "").strip()
            if _t and not _t.startswith("-") and "=" not in _t[:4]:
                _out.append(_t)
        return _out

    @classmethod
    def _extract_nonredir_write_targets(cls, cmd: str) -> list[str]:
        """리다이렉트(`>`)가 아니라 *인자*로 목적지를 받는 파일-쓰기/이동 명령의
        대상 경로를 뽑는다 — `> FILE` 대신 `sed -i FILE`/`cp x FILE`/`dd of=FILE`로
        민감 경로에 쓰는 우회를 protected_write_paths가 잡을 수 있게 한다.
        경로만 쓰고(내용 스캔 아님), 과다 추출은 무해하다(protected 정규식이 안 맞으면 그만).
        `a && b ; c | d` 는 세그먼트별로 각각 검사한다."""
        _out: list[str] = []
        # dd of=DEST 는 명령 어디에 있든 잡는다.
        for _grp in cls._DD_OF_RE.findall(cmd):
            _t = next((g for g in _grp if g), "").strip()
            if _t and _t != "/dev/null":
                _out.append(_t)
        for _seg in re.split(r"[;&|\n]+", cmd):
            _seg = _seg.strip()
            if not _seg:
                continue
            # in-place 편집(sed/perl/ruby -i): `-i` 뒤 non-option 토큰 전부가 대상.
            _m = cls._INPLACE_EDIT_RE.search(_seg)
            if _m:
                _out.extend(cls._tokens(_m.group(1)))
            # cp/mv/install/rsync/ln → 목적지는 마지막 인자.  truncate → non-option 전부.
            _m2 = cls._DEST_ARG_CMD_RE.match(_seg)
            if _m2:
                _toks = cls._tokens(_m2.group(2))
                if _m2.group(1) == "truncate":
                    _out.extend(_toks)
                elif _toks:
                    _out.append(_toks[-1])
        return _out

    def _protected_write_hit(self, tool_name: str, parameters: dict | None) -> str | None:
        """대상 경로가 ``protected_write_paths`` 중 하나에 매치되면 그 경로를 반환."""
        if self._protected_write_re is None:
            return None
        for _t in self._extract_write_targets(tool_name, parameters):
            _norm = _t[2:] if _t.startswith("~/") else _t
            if self._protected_write_re.search(_norm):
                return _t
        return None

    def _auth_scan_params(self, parameters: dict | None) -> dict | None:
        """``tool_authorization`` 백스톱 스캔에 넘길 파라미터에서 파일 본문 성격의
        키(``auth_scan_skip_keys``)를 제거한 얕은 복사본을 반환한다 (SPEC-041).

        ``parameters``가 dict가 아니거나 제거할 키가 없으면 원본을 그대로 돌려준다
        (불필요한 복사 방지)."""
        if not isinstance(parameters, dict) or not self._auth_scan_skip_keys:
            return parameters
        if not any(k in parameters for k in self._auth_scan_skip_keys):
            return parameters
        return {k: v for k, v in parameters.items() if k not in self._auth_scan_skip_keys}

    @staticmethod
    def _clean_loop_result(loop: dict[str, Any]) -> dict[str, Any]:
        """``eval_loop_detection`` 결과에서 합성 식별자(``"<name>\\x00<hash>"``)를
        사람이 읽을 도구 이름으로 되돌린 얕은 복사본을 반환한다 (SPEC-041).
        ``check_before_tool_call``의 ``verdict.detail``과 ``snapshot()``이 공유한다."""
        _c = lambda _t: str(_t or "").split("\x00", 1)[0]  # noqa: E731
        _out = dict(loop)
        if _out.get("loop_tool"):
            _out["loop_tool"] = _c(_out["loop_tool"])
        if _out.get("detected_loops"):
            _out["detected_loops"] = [
                {**_dl, "loop_tool": _c(_dl.get("loop_tool"))} for _dl in _out["detected_loops"]
            ]
        return _out

    @staticmethod
    def _loop_call_identity(entry: dict[str, Any]) -> str:
        """실시간 루프 판정용 합성 식별자: ``"<name>\\x00<정렬된 인자 JSON>"``.

        같은 도구를 서로 다른 인자로 이어 호출하는 정상 작업이
        ``consecutive_repeat``로 오탐되지 않도록, 도구 이름만이 아니라 인자까지
        포함해 "완전히 동일한 호출"의 반복만 루프로 보게 한다. 인자 직렬화가
        실패하면(순환 참조 등) 이름만 쓴다(회귀 없이 안전하게 폴백)."""
        _name = str(entry.get("name", "") or "")
        _args = entry.get("arguments")
        if _args in (None, {}):
            return _name
        try:
            _blob = json.dumps(_args, sort_keys=True, default=str)
        except Exception:
            return _name
        # 큰 파일 본문 등으로 식별자가 무한정 커지지 않게, 길면 전체 내용의 해시를
        # 쓴다 — 앞 N자만 자르면 "앞부분은 같고 총 길이도 같은데 뒷부분만 다른"
        # 연속 편집이 오탐될 수 있으므로 전체를 정확히 비교한다.
        if len(_blob) > 2048:
            _blob = "sha1:" + hashlib.sha1(_blob.encode("utf-8", "replace")).hexdigest()
        return _name + "\x00" + _blob

    def _tool_call_names(self) -> list[str]:
        return [tc.get("name", "") for tc in self._tool_calls]

    @staticmethod
    def _tool_in(tool_name: str, names: Any) -> bool:
        """대소문자 무시 도구 이름 멤버십 — OpenCode "bash" / Claude Code "Bash"처럼
        같은 도구를 스택마다 다르게 부르는 걸 흡수한다 (SPEC-041)."""
        if not names:
            return False
        _t = (tool_name or "").lower()
        return any(_t == str(n).lower() for n in names)

    def check_before_tool_call(
        self,
        task_id: str,
        tool_name: str,
        parameters: dict | None = None,
    ) -> LiveVerdict:
        """도구 호출 직전 Gate B 위반 여부를 조회한다 (SPEC-019 REQ-3).

        순수 조회 — 이 메서드 호출로 ``_tool_calls``는 변경되지 않는다.
        실제 실행 여부는 호출자가 결정하므로, 실행이 확정되면 별도로
        :meth:`record_tool_call`을 호출해야 한다.

        Args:
            task_id: 세션/태스크 식별자 (평가 로직 자체는 사용하지 않음 —
                호출자 로깅·detail 상관관계 확인용).
            tool_name: 호출하려는 도구 이름.
            parameters: 도구 호출 인자.

        Returns:
            LiveVerdict: ``block=True``면 이 도구 호출을 막아야 한다.
        """
        self._task_id = task_id
        # SPEC-041: tool_name이 None/비-str이어도 죽지 않게 정규화(helper들이 .lower() 호출).
        tool_name = tool_name if isinstance(tool_name, str) else str(tool_name or "")
        _candidate = self._tool_calls + [{"name": tool_name, "arguments": parameters or {}}]
        # SPEC-041: heredoc/리다이렉트로 파일을 만드는 순수 셸 쓰기면, 명령 문자열 안의
        # 위험 문자열은 파일 *내용*일 뿐이므로 dangerous_patterns/백스톱 검사를 건너뛴다.
        _benign_write = self._is_benign_shell_file_write(tool_name, parameters)

        # SPEC-041: 파일 *위치*가 민감한 쓰기(SSH 키·셸 rc·크론·/etc·systemd 등)는
        # 내용과 무관하게 차단한다 — _benign_write여도 적용된다(내용이 아니라 위치가 문제).
        _protected = self._protected_write_hit(tool_name, parameters)
        if _protected is not None:
            return LiveVerdict(
                block=True,
                gate="E",
                reason=(
                    f"protected write path: {_protected!r} "
                    f"(tool={tool_name}, task_id={task_id})"
                ),
                detail={"target": _protected, "tool_name": tool_name},
            )

        if self._loop_detection is not None:
            # SPEC-041: 트레일링 윈도우로만 루프를 본다(latch 방지). 배치 snapshot()은
            # 여전히 self._tool_calls 전체를 본다 — 이 축소는 실시간 판정 전용이다.
            _loop_window = (
                _candidate
                if self._live_loop_window is None
                else _candidate[-self._live_loop_window :]
            )
            # SPEC-041: eval_loop_detection은 도구 *이름*만 비교하므로, Claude Code의
            # "Bash"·"Edit"나 OpenCode의 "bash"처럼 도구가 굵으면 서로 다른 명령
            # (npm test → git status → ls)을 8번 이어 호출한 정상 작업까지
            # "consecutive_repeat"로 오탐한다(연속 8회 편집도 마찬가지). 실시간 판정에서는
            # 이름 대신 (이름 + 정렬된 인자 JSON)을 합성 "이름"으로 넘겨, *완전히 동일한*
            # 호출이 반복될 때만 루프로 본다 — 진짜 무한 루프는 같은 인자를 반복한다.
            # 배치 snapshot()/리포트는 기존대로 이름 기준(과도 계수 가능하나 점수만 영향).
            _loop_source = [
                {"name": self._loop_call_identity(_e)} for _e in _loop_window
            ]
            _loop = gate_b_evaluators.eval_loop_detection(
                _loop_source, None, self._loop_detection
            )
            # SPEC-041: on_loop_detected="fail"이어도 live_loop_blocking_types에 든 루프
            # 타입만 차단한다(기본: consecutive_repeat만). detected_loops 안 어느 하나라도
            # 차단 대상 타입이면 막는다.
            _detected_types = {
                dl.get("loop_type")
                for dl in _loop.get("detected_loops", [])
            } or {_loop.get("loop_type")}
            _blocking_hit = _detected_types & set(self._live_loop_blocking_types)
            if (
                self._loop_detection.on_loop_detected == "fail"
                and _loop.get("detected")
                and _blocking_hit
            ):
                _detail = self._clean_loop_result(_loop)
                _loop_tool = _detail.get("loop_tool") or ""
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=(
                        f"loop_detection: {sorted(t for t in _blocking_hit if t)} "
                        f"(tool={_loop_tool!r} repeated with identical arguments, "
                        f"task_id={task_id})"
                    ),
                    detail=_detail,
                )

        if self._deadlock is not None:
            _dl = gate_b_evaluators.eval_deadlock(_candidate, None, self._deadlock)
            if self._deadlock.fail_on_deadlock and _dl.get("deadlock_detected"):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=f"deadlock: {_dl.get('deadlock_type')} (task_id={task_id})",
                    detail=_dl,
                )

        if self._scope is not None:
            # SPEC-041: 누적 상한(max_tool_calls/max_unique_tools)이 설정된 경우에만
            # 전체 이력을 봐야 한다(상한은 본래 누적 개념). 그 외
            # (forbidden_tools/allowed_tools만) 이번 호출만 검사한다 — 과거에 금지
            # 도구가 이력에 있다는 이유로 이후 모든 호출을 막는 latch를 방지
            # (예: 서킷 브레이커로 통과됐던 WebFetch 한 건).
            _has_cumulative_cap = (
                getattr(self._scope, "max_tool_calls", None) is not None
                or getattr(self._scope, "max_unique_tools", None) is not None
            )
            _scope_source = _candidate if _has_cumulative_cap else [
                {"name": tool_name, "arguments": parameters or {}}
            ]
            _sc = gate_b_evaluators.eval_scope(_scope_source, self._scope)
            if self._scope.fail_on_violation and not _sc.get("in_scope", True):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=f"scope violation: {_sc.get('violations')} (task_id={task_id})",
                    detail=_sc,
                )

        _tc_cfg = self._team_concurrency
        if _tc_cfg is not None and self._tool_in(tool_name, _tc_cfg.scoped_tool_names):
            _path = extract_path_param(parameters, _tc_cfg.path_param_candidates)
            if _path is not None:
                # SPEC-036/037: owner가 설정되면(또는 "auto"가 해석되면) 자기
                # 자신(developer == owner)의 클레임은 충돌 후보에서 제외한다 —
                # owner 미설정(None, "auto" 해석 실패 포함)이면 이 필터를
                # 적용하지 않아 기존 동작(자기 클레임도 충돌로 잡힘) 그대로 유지된다.
                _resolved_owner = self._team_concurrency_owner
                _conflicts = [
                    c for c in self._team_claims
                    if (_resolved_owner is None or c.get("developer") != _resolved_owner)
                    and _scopes_overlap(_path, c.get("scope", []))
                ]
                if _conflicts and _tc_cfg.fail_on_conflict:
                    _c = _conflicts[0]
                    return LiveVerdict(
                        block=True,
                        gate="B",
                        reason=(
                            f"team_concurrency: scope claimed by {_c.get('developer')} "
                            f"(claim_id={_c.get('claim_id')}, task_id={task_id})"
                        ),
                        detail={"conflicts": _conflicts, "path": _path},
                    )
                if self._shared_files and any(
                    _scopes_overlap(_path, [sf]) for sf in self._shared_files
                ):
                    return LiveVerdict(
                        block=True,
                        gate="B",
                        reason=(
                            f"team_concurrency: shared file requires coordination: "
                            f"{_path} (task_id={task_id})"
                        ),
                        detail={"path": _path},
                    )

        _bg_cfg = self._branch_guard
        if _bg_cfg is not None and self._tool_in(tool_name, _bg_cfg.scoped_tool_names):
            try:
                _args_str = (
                    json.dumps(parameters, default=str)
                    if isinstance(parameters, dict) else str(parameters or "")
                )
            except (TypeError, ValueError):
                _args_str = str(parameters or "")
            if matches_git_mutation(_args_str, _bg_cfg) and _bg_cfg.fail_on_violation:
                # 커밋/푸시가 임박했을 때만 브랜치를 다시 조회한다(저비용, recheck_branch=True).
                _branch = self._current_branch
                if self._recheck_branch:
                    _branch = get_current_branch()
                    self._current_branch = _branch
                if is_branch_protected(_branch, _bg_cfg):
                    return LiveVerdict(
                        block=True,
                        gate="B",
                        reason=(
                            f"branch_guard: git mutation blocked on branch "
                            f"'{_branch}' (task_id={task_id})"
                        ),
                        detail={"branch": _branch, "tool_name": tool_name},
                    )

        if self._tool_parameter_safety is not None and not _benign_write:
            # SPEC-041: 실행 전 파라미터 안전성은 *이번* 호출만 검사한다 — 과거
            # 호출의 인자는 이미 확정됐고 바뀌지 않으므로 재검사할 이유가 없다.
            # _candidate 전체를 넘기면 (1) 세션이 길어질수록 매 호출 O(n) 정규식
            # 스캔이 쌓여 O(n²)가 되고, (2) 서킷 브레이커로 통과됐거나 세션 중
            # dangerous_patterns가 바뀌어 과거 호출 하나가 위험으로 잡히면 그 뒤
            # 모든 호출이 차단되는 latch가 생긴다. 배치 snapshot()은 여전히 전체를 본다.
            # _benign_write(순수 파일 쓰기)면 명령 안의 위험 문자열이 파일 내용일 뿐이라 건너뛴다.
            _tps = gate_b_evaluators.eval_tool_parameter_safety(
                [{"name": tool_name, "arguments": parameters or {}}], self._tool_parameter_safety
            )
            if self._tool_parameter_safety.fail_on_dangerous and _tps.get("dangerous_calls"):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=f"dangerous tool parameters: {_tps.get('dangerous_calls')} (task_id={task_id})",
                    detail=_tps,
                )

        if self._tool_authorization is not None and not _benign_write:
            _ta = self._tool_authorization.track_tool_call(
                task_id, tool_name, self._auth_scan_params(parameters)
            )
            # track_tool_call은 무조건 로그에 append하므로(빈 케이스 없음), peek 직후 되돌린다.
            self._tool_authorization.tool_calls = self._tool_authorization.tool_calls[:-1]
            if _ta.get("is_authorized") is False or _ta.get("is_restricted") or _ta.get("has_dangerous_params"):
                return LiveVerdict(
                    block=True,
                    gate="E",
                    reason=f"tool_authorization: {_ta.get('violation_type')} (task_id={task_id})",
                    detail=_ta,
                )

        _candidate_names = self._tool_call_names() + [tool_name]

        if self._privilege_escalation is not None:
            _n0 = len(self._privilege_escalation.escalation_events)
            _pe = self._privilege_escalation.analyze_privilege_chain(task_id, _candidate_names)
            # SPEC-041: analyze_*는 조기 반환(safe-workflow whitelist·빈 입력) 시 append하지
            # 않을 수 있다 — 무조건 [:-1]하면 이전 항목을 지우므로, 호출 전 길이로 복원한다.
            self._privilege_escalation.escalation_events = (
                self._privilege_escalation.escalation_events[:_n0]
            )
            if _pe.get("escalation_detected"):
                return LiveVerdict(
                    block=True,
                    gate="E",
                    reason=f"privilege_escalation: {_pe.get('initial_privilege')}->{_pe.get('max_privilege')} (task_id={task_id})",
                    detail=_pe,
                )

        if self._tool_chain_attack is not None:
            _n0 = len(self._tool_chain_attack.detections)
            _tc = self._tool_chain_attack.analyze_tool_chain(task_id, _candidate_names)
            self._tool_chain_attack.detections = self._tool_chain_attack.detections[:_n0]
            if _tc.get("is_suspicious_chain"):
                return LiveVerdict(
                    block=True,
                    gate="E",
                    reason=f"tool_chain_attack: {_tc.get('attack_patterns_detected')} (task_id={task_id})",
                    detail=_tc,
                )

        return LiveVerdict(block=False)

    # SPEC-031 REQ-1: record_tool_call(output=...)이 병합할 수 있는 키 화이트리스트 —
    # 호출자가 실수로(또는 악의적으로) "name"/"arguments"를 output에 넣어도 무시된다.
    _ALLOWED_OUTPUT_KEYS = ("success", "exit_code", "stdout", "stderr")

    def record_tool_call(
        self,
        task_id: str,
        tool_name: str,
        parameters: dict | None = None,
        output: dict[str, Any] | None = None,
    ) -> None:
        """실제로 실행된 도구 호출을 확정 반영한다 (SPEC-019 REQ-4).

        ``check_before_tool_call``이 차단(``block=True``)을 반환해 실제로
        실행되지 않은 호출은 여기로 기록하지 않는다.

        ``tool_authorization``이 설정된 경우 ``track_tool_call``을 실제로
        호출해 확정 로그에 반영한다(배치 경로와 동일하게 "확정 호출 1건당
        1회"). ``privilege_escalation``/``tool_chain_attack``은 완결된 전체
        시퀀스가 필요한 태스크당-1회 분석기라 여기서는 갱신하지 않고
        :meth:`snapshot`에서 계산한다.

        Args:
            task_id: 세션/태스크 식별자.
            tool_name: 실행된 도구 이름.
            parameters: 도구 호출 인자.
            output: (SPEC-031) 실행 결과 — ``"success"``(bool)/``"exit_code"``(int)/
                ``"stdout"``/``"stderr"``(str) 중 있는 키만 반영한다. ``"success"``가
                채워지면 ``ToolCallAnalyzer``(Gate G)가 이미 읽는 신호이므로 새 계산
                로직 없이 그대로 성공/실패 판정에 반영된다. 생략하면(기본값 ``None``)
                이전과 완전히 동일하게 동작한다(회귀 없음). ``stdout``/``stderr``는
                ``max_tool_output_chars``로 truncate된다.
        """
        self._task_id = task_id
        tool_name = tool_name if isinstance(tool_name, str) else str(tool_name or "")
        entry: dict[str, Any] = {"name": tool_name, "arguments": parameters or {}}
        # SPEC-041: output이 dict가 아니면(문자열/None 등) 조용히 무시한다 — 과거엔
        # `"stdout" in output`가 문자열에서 substring 검사로 참이 된 뒤 output["stdout"]가
        # TypeError(string indices must be integers)로 터졌다.
        if isinstance(output, dict):
            for key in self._ALLOWED_OUTPUT_KEYS:
                if key not in output:
                    continue
                value = output[key]
                if key in ("stdout", "stderr") and isinstance(value, str):
                    value = value[: self._max_tool_output_chars]
                entry[key] = value
        # SPEC-041: 순수 파일 쓰기임을 표시해 둔다 — snapshot()의 tool_parameter_safety
        # 스캔이 이 항목의 명령(=파일 내용)을 건너뛰어, 실시간 판정(allow)과 배치
        # 리포트 점수가 어긋나지 않게 한다. loop 식별자는 여전히 원본 arguments를 쓴다.
        if self._is_benign_shell_file_write(tool_name, parameters):
            entry["_benign_write"] = True
        self._tool_calls.append(entry)
        if self._tool_authorization is not None:
            # 순수 파일 쓰기는 명령 안의 위험 문자열이 파일 내용일 뿐이므로, 실시간
            # 판정과 마찬가지로 백스톱 집계에서도 command를 비운 채 기록한다(리포트 일관성).
            _params = self._auth_scan_params(parameters)
            if self._is_benign_shell_file_write(tool_name, parameters) and isinstance(_params, dict):
                _params = {k: v for k, v in _params.items() if k not in ("command", "cmd", "script")}
            self._tool_authorization.track_tool_call(task_id, tool_name, _params)

    def record_blocked_attempt(
        self,
        task_id: str,
        tool_name: str,
        verdict: LiveVerdict,
    ) -> None:
        """완전히 차단된 시도를 감사(audit) 이력에 기록한다 (SPEC-030 REQ-1).

        ``check_before_tool_call()``이 ``block=True``를 반환했고, 호출자가 실제로
        그 판정을 따라 도구를 실행하지 않기로 했을 때만 명시적으로 호출한다 —
        ``check_before_tool_call()``은 이 메서드를 내부적으로 호출하지 않는다
        (순수 조회 계약 유지, 후보를 미리 여러 개 찔러보는 호출까지 감사 이력에
        섞이는 것을 방지).

        여기 기록되는 목록(``self._blocked_attempts``)은 Gate B/E 점수를 만드는
        ``self._tool_calls``와 완전히 분리돼 있다 — 실행되지 않은 시도이므로
        점수 계산에는 전혀 관여하지 않는다.

        Args:
            task_id: 세션/태스크 식별자.
            tool_name: 차단된 도구 이름.
            verdict: ``check_before_tool_call()``이 반환한 판정(``block=True``이어야 함).

        Raises:
            ValueError: ``verdict.block``이 ``False``일 때 — 차단되지 않은 시도를
                차단 이력에 넣는 호출자 오류를 조용히 넘기지 않는다.
        """
        if not verdict.block:
            raise ValueError(
                "record_blocked_attempt() requires a verdict with block=True "
                f"(got block=False for tool_name={tool_name!r})"
            )
        self._task_id = task_id
        self._blocked_attempts.append({
            "tool_name": tool_name,
            "gate": verdict.gate,
            "reason": verdict.reason,
        })

    def refresh_team_claims(self) -> None:
        """``team_concurrency``의 클레임/공유파일 캐시를 다시 읽는다 (SPEC-032 REQ-6).

        생성자 시점 1회 로드가 기본 계약이므로(``check_before_tool_call()``의
        순수 조회 원칙 유지), 자동으로 호출되지 않는다 — 장시간 세션에서 다른
        개발자의 새 클레임을 반영하고 싶을 때 호출자가 명시적으로 사용한다.
        ``team_concurrency``가 설정되지 않았으면 아무 일도 하지 않는다.
        """
        if self._team_concurrency is None:
            return
        self._team_claims = load_active_claims(self._team_concurrency.claims_path)
        self._shared_files = _load_shared_files(self._team_concurrency.shared_files_path)

    def _tool_authorization_summary(self) -> dict[str, Any] | None:
        """``monitor.py:1877-1921``의 tool_authorization 집계 로직을 그대로
        재현한다 — ``ToolAuthorizationTracker.tool_calls``(확정된 호출 로그,
        :meth:`record_tool_call`이 매번 append)에서 재집계할 뿐, 새 호출을
        하지 않는다(순수 조회)."""
        assert self._tool_authorization is not None
        _records = self._tool_authorization.tool_calls
        _total = len(_records)
        if _total == 0:
            return None
        _violations = sum(1 for r in _records if r.get("violation_type") is not None)
        _restricted = sum(1 for r in _records if r.get("is_restricted"))
        _dangerous = sum(1 for r in _records if r.get("has_dangerous_params"))
        _unauthorized_only = sum(1 for r in _records if r.get("violation_type") == "unauthorized_tool")
        return {
            "unauthorized_calls": _unauthorized_only,
            "restricted_calls": _restricted,
            "dangerous_param_calls": _dangerous,
            "total_violations": _violations,
            "total_calls": _total,
            "compliance_rate": round((_total - _violations) / _total, 4),
        }

    def snapshot(self) -> dict[str, Any]:
        """확정 누적된 tool_calls에 대한 Gate B/E 평가 결과 (SPEC-019 REQ-5).

        ``TaskResult.extra``와 동일한 키(``loop_detection``/``deadlock``/
        ``scope``/``tool_parameter_safety``/``tool_authorization``/
        ``privilege_escalation``/``tool_chain_attack``)로 반환한다 —
        생성자에서 설정되지 않은 항목, 또는 해당 지표가 배치 경로와 동일하게
        "확정된 tool_calls가 없어 계산 자체를 하지 않는" 경우는 키 자체가
        없다. 몇 번을 호출해도 부작용이 없다(``privilege_escalation``/
        ``tool_chain_attack``은 호출 후 로그 1건을 되돌려 반복 호출 시
        내부 이력이 중복 누적되지 않게 한다).

        **SPEC-041 — SPEC-019 REQ-5/6 byte-identity에서의 의도적 이탈**:
        원래 REQ-5/6은 snapshot 결과가 ``eval_*(self._tool_calls, config)``를 그대로
        돌린 것과 byte-diff 동일할 것을 요구했다("라이브 근사치 vs 배치 정답" 이중
        소스 방지). 그러나 두 지표는 그 원본 함수가 opencode/claude처럼 도구가 굵은
        환경에서 오탐하는 것이 드러나, 실시간(check)과 배치(snapshot) *양쪽*을 함께
        보정한다 — 이탈이 아니라 "실시간·배치가 여전히 서로 일치"라는 REQ-5/6의
        본래 취지는 유지된다. 달라지는 건 ``@agent_eval`` 순수 배치 경로와의 교차
        비교뿐이며, 그쪽은 도구 이름이 세분화돼 있어 원본 동작이 맞다:
          - ``loop_detection``: 도구 *이름*이 아니라 (이름 + 인자 해시)로 동일성 판정
            (``_loop_call_identity``) — "Bash"를 서로 다른 명령으로 8번 이어 부른 정상
            세션이 loop로 잡혀 Gate B/CI를 오탈락시키던 것 방지.
          - ``tool_parameter_safety``: ``_benign_write`` 표식이 붙은 순수 파일 쓰기
            항목을 스캔 대상에서 제외(실시간에서 통과시킨 것과 점수 일치).

        SPEC-028 REQ-1: ``tool_calls`` 키에 확정 호출 원본 로그(얕은 복사)를
        항상 포함한다(설정된 Config와 무관 — 실제 관측 데이터라 조건부가
        아니다). 이 키는 다른 Gate B/E 파생 지표와 달리 ``TaskResult.extra``가
        아니라 최상위 ``TaskResult.tool_calls``로 옮겨 담기 위한 것이다 —
        호출부(``live_guardrail_report.py``)가 이 키를 꺼내 쓰고 나머지만
        ``extra``에 남긴다.

        SPEC-030 REQ-2: ``blocked_attempts`` 키도 ``tool_calls``와 동일하게
        항상 포함한다(비어 있어도 빈 리스트로). ``tool_calls``와 달리 이 키는
        그대로 ``TaskResult.extra``에 남아(최상위로 승격되지 않음) —
        ``storage/sqlite_backend.py``의 ``save_tasks_to_db()``가 ``extra``에서
        직접 읽어 ``blocked_violations`` 테이블에 반영한다(SPEC-030 REQ-3).
        """
        _result: dict[str, Any] = {
            "tool_calls": list(self._tool_calls),
            "blocked_attempts": list(self._blocked_attempts),
        }
        if self._loop_detection is not None:
            # SPEC-041: 실시간 판정(check_before_tool_call)과 동일하게 (이름 + 인자)
            # 식별자로 루프를 본다 — 서로 다른 명령을 8번 이어 부른 정상 작업이
            # 배치 리포트에서 loop_detection.detected=True로 잡혀 Gate B 점수를
            # 떨어뜨리던 것(CI `agent-eval gate` 오탈락)을 없앤다. 출력의 loop_tool은
            # 합성 식별자에서 사람이 읽을 이름만 남긴다.
            _lp_src = [{"name": self._loop_call_identity(_e)} for _e in self._tool_calls]
            _lp = gate_b_evaluators.eval_loop_detection(_lp_src, None, self._loop_detection)
            _result["loop_detection"] = self._clean_loop_result(_lp)
        if self._deadlock is not None:
            _result["deadlock"] = gate_b_evaluators.eval_deadlock(
                self._tool_calls, None, self._deadlock,
            )
        if self._scope is not None:
            _result["scope"] = gate_b_evaluators.eval_scope(self._tool_calls, self._scope)
        if self._tool_parameter_safety is not None:
            # SPEC-041: 순수 파일 쓰기(_benign_write)는 실시간에서 통과시킨 것이므로
            # 배치 스캔에서도 제외 — 리포트 점수가 실시간 판정과 일치하도록.
            _tps_calls = [tc for tc in self._tool_calls if not tc.get("_benign_write")]
            _result["tool_parameter_safety"] = gate_b_evaluators.eval_tool_parameter_safety(
                _tps_calls, self._tool_parameter_safety,
            )

        if self._tool_authorization is not None:
            _ta_summary = self._tool_authorization_summary()
            if _ta_summary is not None:
                _result["tool_authorization"] = _ta_summary

        _names = self._tool_call_names()
        _task_id = self._task_id or "unknown"
        if self._privilege_escalation is not None and _names:
            _n0 = len(self._privilege_escalation.escalation_events)
            _pe = self._privilege_escalation.analyze_privilege_chain(_task_id, _names)
            self._privilege_escalation.escalation_events = (
                self._privilege_escalation.escalation_events[:_n0]
            )
            _result["privilege_escalation"] = _pe
        if self._tool_chain_attack is not None and _names:
            _n0 = len(self._tool_chain_attack.detections)
            _tc = self._tool_chain_attack.analyze_tool_chain(_task_id, _names)
            self._tool_chain_attack.detections = self._tool_chain_attack.detections[:_n0]
            _result["tool_chain_attack"] = _tc

        return _result

    def to_task_extra(self) -> dict[str, Any]:
        """``TaskResult(extra=...)``에 그대로 대입 가능한 형태 (SPEC-019 REQ-6).

        :meth:`snapshot`과 내용은 동일하다 — 세션 종료 시 배치 리포트로
        편입하는 용도임을 호출부에서 드러내기 위한 별도 이름.
        """
        return self.snapshot()


# ---------------------------------------------------------------------------
# SPEC-039 REQ-6: contextvars 기반 세션 + tool_guard 데코레이터
#
# 지금까지 자체 Python 에이전트 루프에서 LiveGuardrail을 쓰려면 도구 호출
# 지점마다 `check_before_tool_call()` → (통과 시) 실제 실행 → `record_tool_call()`을
# 손으로 반복해야 했다(Ch27 `run_agent_step()` 헬퍼가 이 패턴을 감싸지만, 그래도
# 호출 스타일 자체를 그 헬퍼로 바꿔야 하는 침습적 변경이었다). `agent_eval`은 이미
# `contextvars.ContextVar`(`decorators.py`의 `_eval_ctx_var`) + `_push_ctx()`/`_pop_ctx()`로
# "현재 실행 컨텍스트"를 암묵 전달하는 인프라를 갖고 있다 — 여기서는 정확히 같은
# 패턴을 LiveGuardrail 전용으로 재현한다(별도의 새 ContextVar, `_eval_ctx_var`와는
# 무관 — 의미가 다른 두 컨텍스트를 하나로 합치지 않는다).
#
# 사용 패턴::
#
#     from agent_evaluator.gates.live_guardrail import (
#         LiveGuardrail, live_guardrail_session, tool_guard, GuardrailBlockedError,
#     )
#
#     guardrail = LiveGuardrail(tool_parameter_safety=ToolParameterSafetyConfig(...))
#
#     @tool_guard()
#     def bash(command: str) -> str:
#         ...  # 실제 구현 — guardrail을 전혀 모른다
#         return result
#
#     with live_guardrail_session(guardrail, task_id="session-1"):
#         bash("ls -la")       # 자동으로 check_before_tool_call → 실행 → record_tool_call
#         bash("rm -rf /")     # GuardrailBlockedError 발생
# ---------------------------------------------------------------------------

_guardrail_ctx_var: contextvars.ContextVar[tuple[LiveGuardrail, str] | None] = (
    contextvars.ContextVar("_live_guardrail_ctx", default=None)
)


class GuardrailBlockedError(Exception):
    """:meth:`tool_guard`로 감싼 함수 호출이 차단됐을 때 발생 (SPEC-039 REQ-6).

    Attributes:
        verdict: 차단을 유발한 :class:`LiveVerdict` (``.gate``/``.reason``/``.detail`` 포함).
    """

    verdict: LiveVerdict  # 타입 체커가 exc.value.verdict를 인식하도록 클래스 레벨 선언

    def __init__(self, verdict: LiveVerdict) -> None:
        self.verdict = verdict
        super().__init__(verdict.reason or "blocked by LiveGuardrail")


@contextlib.contextmanager
def live_guardrail_session(guardrail: LiveGuardrail, task_id: str):
    """이 ``with`` 블록 안에서 실행되는 :func:`tool_guard` 함수 호출이 자동으로 이
    ``guardrail``/``task_id``를 쓰게 한다 (SPEC-039 REQ-6).

    ``decorators.py``의 ``_push_ctx()``/``_pop_ctx()``와 동일한 토큰 기반
    contextvars 패턴 — 세션(에이전트 루프 1회 실행)마다 새로 진입해야 한다.
    ``asyncio.create_task()``로 만든 동시 태스크 사이에서도 서로 다른 세션이
    섞이지 않는다(``contextvars.ContextVar``의 표준 보장).

    Args:
        guardrail: 이 세션에 쓸 :class:`LiveGuardrail` 인스턴스.
        task_id: 이 세션의 태스크/세션 식별자.

    Example::

        with live_guardrail_session(guardrail, task_id="session-1"):
            bash("ls -la")
    """
    token = _guardrail_ctx_var.set((guardrail, task_id))
    try:
        yield guardrail
    finally:
        _guardrail_ctx_var.reset(token)


def _bind_call_params(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    """``func(*args, **kwargs)`` 호출의 실제 인자를 이름 기반 dict로 변환한다.

    ``check_before_tool_call()``/``record_tool_call()``이 기대하는
    ``parameters: dict`` 형태로 맞추기 위함 — 바인딩 실패 시(가변 인자 등
    드문 시그니처) 빈 dict로 안전하게 폴백한다.
    """
    try:
        bound = inspect.signature(func).bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        # SPEC-041: 가변 인자(*args/**kwargs) 등으로 이름 바인딩이 안 되면 빈 dict 대신
        # 원본 인자 값을 그대로 담아 넘긴다 — {}면 dangerous_patterns/protected_write_paths/
        # tool_authorization이 스캔할 게 없어 가드레일이 조용히 무력화되기 때문.
        try:
            return {"_args": [_a for _a in args], "_kwargs": dict(kwargs)}
        except Exception:
            return {}


def tool_guard(
    tool_name: str | None = None,
    *,
    audit_blocked: bool = False,
    fail_closed: bool = False,
    capture_output: Callable[[Any], dict[str, Any]] | None = None,
) -> Callable:
    """도구 함수를 :class:`LiveGuardrail`로 비침습적으로 감싸는 데코레이터 (SPEC-039 REQ-6).

    ``live_guardrail_session()`` 블록 안에서 이 데코레이터가 붙은 함수가 호출되면,
    실제 실행 전에 자동으로 ``check_before_tool_call()``을 거치고 차단되지 않으면
    실행 후 ``record_tool_call()``까지 자동 호출한다 — 호출자는 도구 함수를
    평소처럼 그냥 호출하면 된다(``run_agent_step()`` 같은 별도 헬퍼로 호출 스타일을
    바꿀 필요가 없다).

    새로운 위험 탐지 로직은 없다 — :class:`LiveGuardrail`의 기존 메서드를
    호출 지점마다 반복해서 쓰지 않도록 감싸는 순수 적용 계층이다.

    Args:
        tool_name: ``check_before_tool_call()``/``record_tool_call()``에 넘길 도구
            이름. 생략하면 데코레이트된 함수의 ``__name__``을 쓴다.
        audit_blocked: ``True``면 차단된 시도를 ``record_blocked_attempt()``로
            감사 이력에도 남긴다(기본 ``False`` — SPEC-030과 동일하게 옵트인).
        fail_closed: 활성 ``live_guardrail_session()``이 없는 상태에서 호출되면
            ``True``일 때 :class:`RuntimeError`를 발생시킨다. ``False``(기본)면
            ``RuntimeWarning``만 내고 가드 없이 원본 함수를 그대로 실행한다
            (다른 ``fail_on_*`` 옵션들과 달리 여기서는 기본값을 fail-open으로 둔다 —
            세션 밖에서의 우발적 호출까지 막으면 테스트·REPL 사용성이 크게 떨어지기
            때문이다. "단 하나의 누락도 허용하지 않아야" 하는 운영 환경이라면
            반드시 ``fail_closed=True``로 명시할 것).
        capture_output: 함수의 반환값을 받아 ``record_tool_call(output=...)``에 넘길
            ``{"success": ..., "exit_code": ..., "stdout": ..., "stderr": ...}``
            형태의 dict로 변환하는 콜백(선택). 지정하지 않으면 ``output``은
            생략되고(기존과 동일한 낙관적 기본값), 예외가 발생하지 않고 정상
            반환됐다는 사실만으로 ``success``를 추론하지 않는다 — 반환값 형태가
            도구마다 제각각이라 매직 추론은 하지 않는다(SPEC-039 설계 결정).

    Raises:
        GuardrailBlockedError: 호출이 차단됐을 때. ``.verdict``에 판정 상세가 담긴다.

    Example::

        @tool_guard(audit_blocked=True, fail_closed=True)
        def bash(command: str) -> str:
            ...
            return result

        with live_guardrail_session(guardrail, task_id="s1"):
            bash("ls -la")
    """

    def decorator(func: Callable) -> Callable:
        _name = tool_name or func.__name__
        _is_async = asyncio.iscoroutinefunction(func)

        def _resolve_ctx() -> tuple[LiveGuardrail, str] | None:
            ctx = _guardrail_ctx_var.get()
            if ctx is not None:
                return ctx
            _msg = (
                f"tool_guard({_name!r}): no active live_guardrail_session() — running the "
                "wrapped function unguarded. If this call must be checked, use "
                "tool_guard(fail_closed=True)."
            )
            if fail_closed:
                raise RuntimeError(_msg)
            warnings.warn(_msg, RuntimeWarning, stacklevel=3)
            return None

        def _check(
            guardrail: LiveGuardrail, task_id: str, params: dict[str, Any]
        ) -> LiveVerdict:
            verdict = guardrail.check_before_tool_call(task_id, _name, params)
            if verdict.block:
                if audit_blocked:
                    guardrail.record_blocked_attempt(task_id, _name, verdict)
                raise GuardrailBlockedError(verdict)
            return verdict

        def _record(
            guardrail: LiveGuardrail, task_id: str, params: dict[str, Any], result: Any
        ) -> None:
            output = capture_output(result) if capture_output is not None else None
            guardrail.record_tool_call(task_id, _name, params, output)

        def _record_failure(
            guardrail: LiveGuardrail, task_id: str, params: dict[str, Any]
        ) -> None:
            # SPEC-041: 도구가 예외를 던져도 "실행은 됐다" — 이력에 실패로 남겨야
            # 루프 감지(같은 실패 명령 반복)와 Gate G 성공률이 정확해진다.
            try:
                guardrail.record_tool_call(task_id, _name, params, {"success": False})
            except Exception:
                pass

        if _is_async:
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx = _resolve_ctx()
                if ctx is None:
                    return await func(*args, **kwargs)
                guardrail, task_id = ctx
                params = _bind_call_params(func, args, kwargs)
                _check(guardrail, task_id, params)
                try:
                    result = await func(*args, **kwargs)
                except BaseException:
                    _record_failure(guardrail, task_id, params)
                    raise
                _record(guardrail, task_id, params, result)
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _resolve_ctx()
            if ctx is None:
                return func(*args, **kwargs)
            guardrail, task_id = ctx
            params = _bind_call_params(func, args, kwargs)
            _check(guardrail, task_id, params)
            try:
                result = func(*args, **kwargs)
            except BaseException:
                _record_failure(guardrail, task_id, params)
                raise
            _record(guardrail, task_id, params, result)
            return result

        return sync_wrapper

    return decorator
