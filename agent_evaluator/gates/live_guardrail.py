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

import dataclasses
from typing import Any, Dict, List, Optional

from agent_evaluator.core.trackers.security import (
    PrivilegeEscalationDetector,
    ToolAuthorizationTracker,
    ToolChainAttackDetector,
)
from agent_evaluator.gates.gate_b_behavioral import evaluators as gate_b_evaluators
from agent_evaluator.gates.gate_b_behavioral.configs import (
    DeadlockConfig,
    LoopDetectionConfig,
    ScopeConfig,
    ToolParameterSafetyConfig,
)


@dataclasses.dataclass
class LiveVerdict:
    """``LiveGuardrail.check_before_tool_call()``의 반환값 (SPEC-019 Interface)."""

    block: bool
    gate: Optional[str] = None  # "B" | "E" | None
    reason: Optional[str] = None
    detail: Dict[str, Any] = dataclasses.field(default_factory=dict)


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
        loop_detection: Optional[LoopDetectionConfig] = None,
        deadlock: Optional[DeadlockConfig] = None,
        scope: Optional[ScopeConfig] = None,
        tool_parameter_safety: Optional[ToolParameterSafetyConfig] = None,
        tool_authorization: Optional[ToolAuthorizationTracker] = None,
        privilege_escalation: Optional[PrivilegeEscalationDetector] = None,
        tool_chain_attack: Optional[ToolChainAttackDetector] = None,
    ) -> None:
        self._loop_detection = loop_detection
        self._deadlock = deadlock
        self._scope = scope
        self._tool_parameter_safety = tool_parameter_safety
        self._tool_authorization = tool_authorization
        self._privilege_escalation = privilege_escalation
        self._tool_chain_attack = tool_chain_attack
        self._tool_calls: List[Dict[str, Any]] = []
        self._task_id: Optional[str] = None

    def _tool_call_names(self) -> List[str]:
        return [tc.get("name", "") for tc in self._tool_calls]

    def check_before_tool_call(
        self,
        task_id: str,
        tool_name: str,
        parameters: Optional[dict] = None,
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
        _candidate = self._tool_calls + [{"name": tool_name, "arguments": parameters or {}}]

        if self._loop_detection is not None:
            _loop = gate_b_evaluators.eval_loop_detection(_candidate, None, self._loop_detection)
            if self._loop_detection.on_loop_detected == "fail" and _loop.get("detected"):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=(
                        f"loop_detection: {_loop.get('loop_type')} "
                        f"(tool={_loop.get('loop_tool')}, task_id={task_id})"
                    ),
                    detail=_loop,
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
            _sc = gate_b_evaluators.eval_scope(_candidate, self._scope)
            if self._scope.fail_on_violation and not _sc.get("in_scope", True):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=f"scope violation: {_sc.get('violations')} (task_id={task_id})",
                    detail=_sc,
                )

        if self._tool_parameter_safety is not None:
            _tps = gate_b_evaluators.eval_tool_parameter_safety(_candidate, self._tool_parameter_safety)
            if self._tool_parameter_safety.fail_on_dangerous and _tps.get("dangerous_calls"):
                return LiveVerdict(
                    block=True,
                    gate="B",
                    reason=f"dangerous tool parameters: {_tps.get('dangerous_calls')} (task_id={task_id})",
                    detail=_tps,
                )

        if self._tool_authorization is not None:
            _ta = self._tool_authorization.track_tool_call(task_id, tool_name, parameters)
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
            _pe = self._privilege_escalation.analyze_privilege_chain(task_id, _candidate_names)
            self._privilege_escalation.escalation_events = self._privilege_escalation.escalation_events[:-1]
            if _pe.get("escalation_detected"):
                return LiveVerdict(
                    block=True,
                    gate="E",
                    reason=f"privilege_escalation: {_pe.get('initial_privilege')}->{_pe.get('max_privilege')} (task_id={task_id})",
                    detail=_pe,
                )

        if self._tool_chain_attack is not None:
            _tc = self._tool_chain_attack.analyze_tool_chain(task_id, _candidate_names)
            self._tool_chain_attack.detections = self._tool_chain_attack.detections[:-1]
            if _tc.get("is_suspicious_chain"):
                return LiveVerdict(
                    block=True,
                    gate="E",
                    reason=f"tool_chain_attack: {_tc.get('attack_patterns_detected')} (task_id={task_id})",
                    detail=_tc,
                )

        return LiveVerdict(block=False)

    def record_tool_call(
        self,
        task_id: str,
        tool_name: str,
        parameters: Optional[dict] = None,
    ) -> None:
        """실제로 실행된 도구 호출을 확정 반영한다 (SPEC-019 REQ-4).

        ``check_before_tool_call``이 차단(``block=True``)을 반환해 실제로
        실행되지 않은 호출은 여기로 기록하지 않는다.

        ``tool_authorization``이 설정된 경우 ``track_tool_call``을 실제로
        호출해 확정 로그에 반영한다(배치 경로와 동일하게 "확정 호출 1건당
        1회"). ``privilege_escalation``/``tool_chain_attack``은 완결된 전체
        시퀀스가 필요한 태스크당-1회 분석기라 여기서는 갱신하지 않고
        :meth:`snapshot`에서 계산한다.
        """
        self._task_id = task_id
        self._tool_calls.append({"name": tool_name, "arguments": parameters or {}})
        if self._tool_authorization is not None:
            self._tool_authorization.track_tool_call(task_id, tool_name, parameters)

    def _tool_authorization_summary(self) -> Optional[Dict[str, Any]]:
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

    def snapshot(self) -> Dict[str, Any]:
        """확정 누적된 tool_calls에 대한 Gate B/E 평가 결과 (SPEC-019 REQ-5).

        ``TaskResult.extra``와 동일한 키(``loop_detection``/``deadlock``/
        ``scope``/``tool_parameter_safety``/``tool_authorization``/
        ``privilege_escalation``/``tool_chain_attack``)로 반환한다 —
        생성자에서 설정되지 않은 항목, 또는 해당 지표가 배치 경로와 동일하게
        "확정된 tool_calls가 없어 계산 자체를 하지 않는" 경우는 키 자체가
        없다. 몇 번을 호출해도 부작용이 없다(``privilege_escalation``/
        ``tool_chain_attack``은 호출 후 로그 1건을 되돌려 반복 호출 시
        내부 이력이 중복 누적되지 않게 한다).
        """
        _result: Dict[str, Any] = {}
        if self._loop_detection is not None:
            _result["loop_detection"] = gate_b_evaluators.eval_loop_detection(
                self._tool_calls, None, self._loop_detection,
            )
        if self._deadlock is not None:
            _result["deadlock"] = gate_b_evaluators.eval_deadlock(
                self._tool_calls, None, self._deadlock,
            )
        if self._scope is not None:
            _result["scope"] = gate_b_evaluators.eval_scope(self._tool_calls, self._scope)
        if self._tool_parameter_safety is not None:
            _result["tool_parameter_safety"] = gate_b_evaluators.eval_tool_parameter_safety(
                self._tool_calls, self._tool_parameter_safety,
            )

        if self._tool_authorization is not None:
            _ta_summary = self._tool_authorization_summary()
            if _ta_summary is not None:
                _result["tool_authorization"] = _ta_summary

        _names = self._tool_call_names()
        _task_id = self._task_id or "unknown"
        if self._privilege_escalation is not None and _names:
            _pe = self._privilege_escalation.analyze_privilege_chain(_task_id, _names)
            self._privilege_escalation.escalation_events = self._privilege_escalation.escalation_events[:-1]
            _result["privilege_escalation"] = _pe
        if self._tool_chain_attack is not None and _names:
            _tc = self._tool_chain_attack.analyze_tool_chain(_task_id, _names)
            self._tool_chain_attack.detections = self._tool_chain_attack.detections[:-1]
            _result["tool_chain_attack"] = _tc

        return _result

    def to_task_extra(self) -> Dict[str, Any]:
        """``TaskResult(extra=...)``에 그대로 대입 가능한 형태 (SPEC-019 REQ-6).

        :meth:`snapshot`과 내용은 동일하다 — 세션 종료 시 배치 리포트로
        편입하는 용도임을 호출부에서 드러내기 위한 별도 이름.
        """
        return self.snapshot()
