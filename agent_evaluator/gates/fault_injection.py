"""
SPEC-043 REQ-5 — thin fault-injection harness (Gate C scoring enrichment).

Gate C (``FaultToleranceConfig`` / ``GracefulDegradationConfig``) *scores*
fault situations when the data contains them; nothing *creates* those
situations. Full sandboxes (E2B / Firecracker) and contract testing (Pact) are
the boundary the book draws — out of scope. This module is the thin layer
inside that boundary: a decorator-level, seeded-RNG wrapper that probabilistically

  (a) raises an exception before a tool call runs, or
  (b) sleeps for ``added_latency_ms`` ± jitter,

and otherwise does nothing. It **never touches the blocking path**
(``check_before_tool_call``): a blocked call is still blocked, injection only
affects calls that were going to run anyway. The injected failures / latencies
flow through the normal result path into Gate C / Gate D scoring, and the config
is echoed into ``lineage.fault_injection`` for reproducibility.

Usage — per tool (``tool_guard``)::

    @tool_guard(fault_injection=FaultInjectionConfig(tool_failure_rate=0.3, seed=1))
    def call_api(payload): ...

Usage — for a whole agent run (``@agent_eval`` sets this context)::

    with fault_injection_session(FaultInjectionConfig(added_latency_ms=200, seed=7)):
        run_agent()          # every @tool_guard tool inside inherits it
"""
from __future__ import annotations

import contextlib
import contextvars
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any


class FaultInjectionError(RuntimeError):
    """Raised by the injector in place of a real tool exception.

    A subclass of :class:`RuntimeError` so existing ``except RuntimeError`` /
    retry logic treats it exactly like a genuine tool failure.
    """


@dataclass
class FaultInjectionConfig:
    """Probabilistic fault / latency injection for tool calls.

    Attributes:
        tool_failure_rate: P(raise :class:`FaultInjectionError`) per guarded call,
            0.0–1.0. Applied *after* ``fail_tools`` (which is unconditional).
        added_latency_ms: base latency added before each guarded call runs.
        latency_jitter_ms: uniform ± jitter on ``added_latency_ms`` (never sleeps
            for a negative duration).
        fail_tools: tool names that always raise (case-insensitive). ``None`` /
            empty → only the random rate applies.
        seed: RNG seed. Same seed → identical failure / latency sequence across
            runs (the whole point — a reproducible chaos run).
    """

    tool_failure_rate: float = 0.0
    added_latency_ms: int = 0
    latency_jitter_ms: int = 0
    fail_tools: list[str] | None = None
    seed: int | None = None

    def is_noop(self) -> bool:
        return (
            self.tool_failure_rate <= 0.0
            and self.added_latency_ms <= 0
            and not self.fail_tools
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _FaultInjector:
    """Stateful runtime companion to a :class:`FaultInjectionConfig` — owns the
    seeded RNG so a single decorator instance produces one deterministic
    sequence across every call."""

    config: FaultInjectionConfig
    _rng: random.Random = field(init=False)
    _fail_set: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.seed)
        self._fail_set = frozenset(
            (t or "").strip().lower() for t in (self.config.fail_tools or [])
        )

    def before_call(self, tool_name: str) -> None:
        """Apply latency then (maybe) raise, for a call about to run.

        Raises:
            FaultInjectionError: when ``tool_name`` is in ``fail_tools`` or the
                RNG draw falls under ``tool_failure_rate``.
        """
        cfg = self.config
        if cfg.added_latency_ms > 0 or cfg.latency_jitter_ms > 0:
            jitter = (
                self._rng.uniform(-cfg.latency_jitter_ms, cfg.latency_jitter_ms)
                if cfg.latency_jitter_ms > 0 else 0.0
            )
            delay_s = max(0.0, (cfg.added_latency_ms + jitter) / 1000.0)
            if delay_s > 0:
                time.sleep(delay_s)
        name = (tool_name or "").strip().lower()
        if name in self._fail_set:
            raise FaultInjectionError(
                f"fault_injection: '{tool_name}' is in fail_tools"
            )
        if cfg.tool_failure_rate > 0.0 and self._rng.random() < cfg.tool_failure_rate:
            raise FaultInjectionError(
                f"fault_injection: random failure on '{tool_name}' "
                f"(rate={cfg.tool_failure_rate})"
            )


_fault_injection_ctx_var: contextvars.ContextVar[_FaultInjector | None] = (
    contextvars.ContextVar("_fault_injection_ctx", default=None)
)


@contextlib.contextmanager
def fault_injection_session(config: FaultInjectionConfig | None):
    """Activate ``config`` for every ``@tool_guard`` call in this block that does
    not pass its own ``fault_injection=``. ``None`` / a no-op config is a
    transparent pass-through (context still entered, injector is ``None``)."""
    injector = (
        _FaultInjector(config) if (config is not None and not config.is_noop()) else None
    )
    token = _fault_injection_ctx_var.set(injector)
    try:
        yield injector
    finally:
        _fault_injection_ctx_var.reset(token)


def active_injector() -> _FaultInjector | None:
    """The injector installed by the nearest :func:`fault_injection_session`, or
    ``None``."""
    return _fault_injection_ctx_var.get()


def enter_fault_injection(config: FaultInjectionConfig | None) -> Any:
    """Token-based equivalent of :func:`fault_injection_session` for callers that
    set up / tear down in separate ``try``/``finally`` arms (``@agent_eval``).

    Returns an opaque token to pass to :func:`exit_fault_injection`. A ``None`` /
    no-op config installs ``None`` (transparent)."""
    injector = (
        _FaultInjector(config) if (config is not None and not config.is_noop()) else None
    )
    return _fault_injection_ctx_var.set(injector)


def exit_fault_injection(token: Any) -> None:
    """Undo :func:`enter_fault_injection`. Never raises."""
    try:
        _fault_injection_ctx_var.reset(token)
    except Exception:  # pragma: no cover - defensive
        pass
