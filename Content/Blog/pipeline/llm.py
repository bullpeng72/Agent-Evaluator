"""Shared LLM caller for the YouTube pipeline.

Priority:
  1. Anthropic SDK  — ANTHROPIC_API_KEY 환경변수가 설정되어 있을 때
  2. claude CLI     — Claude Code 내장 인증 사용 (API Key 불필요)
"""
import subprocess
import sys


def _is_valid_api_key(key: str) -> bool:
    """sk-ant- 로 시작하는 실제 키인지 확인한다."""
    return bool(key) and key.startswith("sk-ant-") and len(key) > 20


def call_claude(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    """Claude를 호출하여 텍스트를 반환한다.

    Args:
        system: 시스템 프롬프트
        user: 사용자 프롬프트 (stdin으로 전달)
        model: 모델명 (예: claude-sonnet-4-6)
        max_tokens: 최대 토큰 수 (SDK 전용, CLI는 무시)

    Returns:
        Claude 응답 텍스트
    """
    from config import ANTHROPIC_API_KEY

    if _is_valid_api_key(ANTHROPIC_API_KEY):
        print("  모드: Anthropic SDK")
        return _call_via_sdk(system, user, model, max_tokens)

    print("  모드: claude CLI (Claude Code 인증)")
    return _call_via_cli(system, user, model)


def _call_via_sdk(system: str, user: str, model: str, max_tokens: int) -> str:
    import anthropic
    from config import ANTHROPIC_API_KEY

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return msg.content[0].text


def _call_via_cli(system: str, user: str, model: str) -> str:
    """claude CLI를 subprocess로 호출한다. 프롬프트는 stdin으로 전달.

    ANTHROPIC_API_KEY와 CLAUDECODE 계열 변수를 제거해 Claude Code 내장 인증을
    독립 프로세스로 호출한다. CLAUDECODE=1이 남으면 부모 세션에 연결을 시도해
    응답이 수 분 이상 지연된다.
    """
    import os

    _remove = {"ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH"}
    env = {k: v for k, v in os.environ.items() if k not in _remove}

    result = subprocess.run(
        [
            "claude", "--print",
            "--system-prompt", system,
            "--model", model,
            "--tools", "",   # 도구 비활성화 — 순수 텍스트 응답만
        ],
        input=user,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if result.returncode != 0:
        sys.stderr.write(f"[ERROR] claude CLI 실패 (exit {result.returncode}):\n")
        if result.stderr:
            sys.stderr.write(result.stderr[:500] + "\n")
        elif result.stdout:
            sys.stderr.write(result.stdout[:300] + "\n")
        sys.exit(1)
    return result.stdout.strip()
