"""
agent_evaluator.gates.shared_metrics
=======================================
SPEC-018: Gate 러닝 집계 공유 인프라.

SPEC-004의 ``_RunningTCRView``/``_running_tcr_agg``(``core/trackers/monitor.py``)를
일반화한다 — ``retention_mode="windowed"``에서 ``record_task()`` 시점에 갱신되고,
``tasks`` 리스트를 전체 이력 기준으로 재계산했을 때와 수학적으로 동일한 결과를
O(1)/task로 제공하는 누적기(accumulator) 프리미티브 모음이다.

``retention_mode="full"``(기본값)에서는 이 모듈의 어떤 클래스도 인스턴스화되지
않는다 — 모든 사용처는 ``if self._retention_mode == "windowed":`` 가드 안에 있어야 한다.

각 Gate의 ``GateXSharedAgg.update()``는 해당 ``gates/gate_x/aggregate.py``의 현재
per-task 필터·변환 로직을 있는 그대로 옮겨 적은 것이어야 한다(재해석 금지) — 그래야
windowed 모드의 스냅숏이 "전체 이력을 tasks로 재계산했을 때"와 항등이 된다.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, Optional


class RunningAverage:
    """스칼라 스트림의 O(1) 평균 — 대부분의 "avg_*" 지표에 재사용."""

    __slots__ = ("_sum", "_count")

    def __init__(self) -> None:
        self._sum: float = 0.0
        self._count: int = 0

    def add(self, value: float) -> None:
        self._sum += value
        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    def average(self) -> Optional[float]:
        if self._count == 0:
            return None
        return self._sum / self._count


class RunningSum:
    """순수 누적합 — 세션 전체 비용/토큰 등 "합산" 의미의 지표."""

    __slots__ = ("_total",)

    def __init__(self) -> None:
        self._total: float = 0.0

    def add(self, value: float) -> None:
        self._total += value

    @property
    def total(self) -> float:
        return self._total


class RunningLastValue:
    """매번 덮어쓰기만 하는 "가장 최근 관측값" 저장소 — 예: SLA breach_window 같은
    설정값 자체(설정은 태스크마다 달라질 수 있어 매번 최신값을 반영해야 함).
    O(1) 저장이며 이력 누적이 아니므로 windowed/full 모드와 무관하게 증식하지 않는다.
    """

    __slots__ = ("_value",)

    def __init__(self) -> None:
        self._value: Any = None

    def set(self, value: Any) -> None:
        self._value = value

    def get(self) -> Any:
        return self._value


class RunningWindow:
    """순서를 보존하는 최근 N개 값의 링버퍼.

    ``retention_mode``의 ``window_size``와는 완전히 독립적인, Config 자체가 정의하는
    별도 윈도우(예: ``SLAConfig.breach_window``, 기본 10)에 사용한다 — ``self.tasks``가
    ``window_size``로 축출되어도 이 링버퍼는 자신만의 ``maxlen``을 유지한다.
    """

    __slots__ = ("_maxlen", "_buf")

    def __init__(self, maxlen: int) -> None:
        self._maxlen = maxlen
        self._buf: Deque[Any] = deque(maxlen=maxlen)

    def resize(self, new_maxlen: int) -> None:
        if new_maxlen == self._maxlen:
            return
        self._maxlen = new_maxlen
        self._buf = deque(self._buf, maxlen=new_maxlen)

    def add(self, value: Any) -> None:
        self._buf.append(value)

    def values(self) -> list:
        return list(self._buf)


class MonotonicFlag:
    """한 번 True가 되면 영구히 True로 유지되는 플래그 — "이 종류의 데이터가 전체
    이력에 한 번이라도 존재했는가" 같은 all-or-nothing 게이팅에 사용(예: Gate E의
    ``_native_e_scores`` 포함 여부). windowed 모드에서 해당 데이터를 가진 태스크가
    전부 윈도우 밖으로 밀려나도 값이 사라지면 안 되므로 단조 증가만 허용한다.
    """

    __slots__ = ("_value",)

    def __init__(self) -> None:
        self._value: bool = False

    def mark(self) -> None:
        self._value = True

    def is_set(self) -> bool:
        return self._value


class RunningCategoryCounter:
    """dict[str, int] 러닝 카운트 — 예: Gate B의 ``deadlock_by_type``. 카테고리
    (문자열 키) 수가 실무상 유한(수 개~수십 개)한 지표에만 사용할 것 — 카테고리 값
    자체가 사실상 무한 카디널리티(사용자 자유 입력 문자열 등)라면 이 프리미티브를
    그 용도로 재사용하지 말 것(Gate C의 retry_consistency 프리픽스 그룹과 동일한 함정).
    """

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def add(self, key: str) -> None:
        self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> Dict[str, int]:
        return dict(self._counts)


class RunningCount:
    """단순 발생 횟수 카운터 — 공유 분모(예: Gate E의 ``n = max(len(tasks), 1)``)나
    이진 이벤트 발생 횟수(예: ``privilege_escalation_rate``의 분자)에 재사용."""

    __slots__ = ("_count",)

    def __init__(self) -> None:
        self._count: int = 0

    def add(self, n: int = 1) -> None:
        self._count += n

    @property
    def count(self) -> int:
        return self._count


class GateESharedAgg:
    """SPEC-018 Phase 1 — Gate E(Security Boundary)의 러닝 집계.

    ``gates/gate_e_security/aggregate.py::compute()``의 ``shared_running is None``
    분기(원본 태스크 재계산 로직)를 한 태스크 단위로 그대로 옮겨 적은 것 — 필터 조건·
    분모(``n``)·프리즌스 카운트(``*_n``)를 재해석 없이 동일하게 유지해야 windowed 모드의
    스냅숏이 전체 이력 재계산과 항등이 된다.
    """

    def __init__(self) -> None:
        self.n = RunningCount()
        self.sec_threats = RunningCount()
        self.cvss = RunningAverage()
        self.compliance = RunningAverage()
        self.priv_esc_count = RunningCount()
        self.priv_esc_n = RunningCount()
        self.chain_attack_count = RunningCount()
        self.chain_attack_n = RunningCount()
        self.leakage_count = RunningCount()
        self.leakage_n = RunningCount()
        self.injection_count = RunningCount()
        self.injection_n = RunningCount()
        self.unauth_count = RunningSum()
        self.tool_auth_n = RunningCount()
        self.threat_response = RunningAverage()

    def update(self, t: Any) -> None:
        self.n.add()
        extra = t.extra or {}

        _has_threat = (
            extra.get("input_sanitization", {}).get("sanitization_needed")
            or int(extra.get("output_leakage", {}).get("leakage_count", 0) or 0) > 0
            or extra.get("privilege_escalation", {}).get("escalation_detected")
            or extra.get("tool_chain_attack", {}).get("is_suspicious_chain")
            or int(
                extra.get("tool_authorization", {}).get("total_violations")
                or extra.get("tool_authorization", {}).get("unauthorized_calls")
                or 0
            ) > 0
        )
        if _has_threat:
            self.sec_threats.add()

        _sev = extra.get("threat_severity")
        if _sev is not None and _sev.get("weighted_score") is not None:
            self.cvss.add(min(float(_sev["weighted_score"]), 10.0))

        _comp = extra.get("compliance")
        if _comp is not None and _comp.get("compliance_score") is not None:
            self.compliance.add(float(_comp["compliance_score"]))

        if extra.get("privilege_escalation", {}).get("escalation_detected"):
            self.priv_esc_count.add()
        if "privilege_escalation" in extra:
            self.priv_esc_n.add()

        if extra.get("tool_chain_attack", {}).get("is_suspicious_chain"):
            self.chain_attack_count.add()
        if "tool_chain_attack" in extra:
            self.chain_attack_n.add()

        if int(extra.get("output_leakage", {}).get("leakage_count", 0) or 0) > 0:
            self.leakage_count.add()
        if "output_leakage" in extra:
            self.leakage_n.add()

        if int(extra.get("input_sanitization", {}).get("threat_count", 0) or 0) > 0:
            self.injection_count.add()
        if "input_sanitization" in extra:
            self.injection_n.add()

        if "tool_authorization" in extra:
            self.unauth_count.add(int(
                extra.get("tool_authorization", {}).get("total_violations")
                or extra.get("tool_authorization", {}).get("unauthorized_calls")
                or 0
            ))
            self.tool_auth_n.add()

        _tr = extra.get("threat_response")
        if _tr and _tr.get("response_score") is not None:
            self.threat_response.add(float(_tr["response_score"]))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "n": max(self.n.count, 1),
            "sec_threats": self.sec_threats.count,
            "cvss_count": self.cvss.count,
            "cvss_avg": self.cvss.average(),
            "compliance_count": self.compliance.count,
            "compliance_avg": self.compliance.average(),
            "priv_esc_count": self.priv_esc_count.count,
            "priv_esc_n": self.priv_esc_n.count,
            "chain_attack_count": self.chain_attack_count.count,
            "chain_attack_n": self.chain_attack_n.count,
            "leakage_count": self.leakage_count.count,
            "leakage_n": self.leakage_n.count,
            "injection_count": self.injection_count.count,
            "injection_n": self.injection_n.count,
            "unauth_count": int(self.unauth_count.total),
            "tool_auth_n": self.tool_auth_n.count,
            "tr_count": self.threat_response.count,
            "tr_avg": self.threat_response.average(),
        }


class GateFSharedAgg:
    """SPEC-018 Phase 2 — Gate F(Multi-Agent Coordination)의 러닝 집계.

    ``gates/gate_f_multiagent/aggregate.py::compute()``의 태스크 기반 4개 지표
    (consensus/propagation/agent_role/conflict_resolution)만 다룬다.
    ``agent_coordination_tracker``/``tool_selection_tracker``(트래커 자체 상태 기반,
    ``tasks``를 순회하지 않음)는 이 스펙 범위 밖 — 여전히 별도로 무제한 증식한다.
    """

    def __init__(self) -> None:
        self.consensus = RunningAverage()
        self.propagation = RunningAverage()
        self.role = RunningAverage()
        self.conflict = RunningAverage()

    def update(self, t: Any) -> None:
        extra = t.extra or {}

        _consensus = extra.get("consensus")
        if _consensus is not None:
            _cs = _consensus.get("consensus_score")
            if _cs is not None and _consensus.get("method") != "single":
                self.consensus.add(float(_cs))

        _prop = extra.get("propagation")
        if _prop is not None:
            _fs = _prop.get("fidelity_score")
            if _fs is not None:
                self.propagation.add(float(_fs))

        _role = extra.get("agent_role")
        if _role is not None:
            _rc = _role.get("role_compliance_score")
            if _rc is not None:
                self.role.add(float(_rc))

        _conflict = extra.get("conflict_resolution")
        if _conflict is not None:
            _rs = _conflict.get("resolution_score")
            if _rs is not None:
                self.conflict.add(float(_rs))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "consensus_avg": self.consensus.average(),
            "consensus_count": self.consensus.count,
            "propagation_avg": self.propagation.average(),
            "propagation_count": self.propagation.count,
            "role_avg": self.role.average(),
            "role_count": self.role.count,
            "conflict_avg": self.conflict.average(),
            "conflict_count": self.conflict.count,
        }


class GateGSharedAgg:
    """SPEC-018 Phase 3 — Gate G(Observability)의 러닝 집계.

    ``gates/gate_g_observability/aggregate.py::compute()``의 태스크 기반 4개 지표
    (observability/explainability/error_diagnosis/latency_attribution)만 다룬다.
    ``tool_call_analyzer``(트래커 기반, ``tasks``를 순회하지 않음)와 ``hall_rate``/
    ``avg_llm_faithfulness``(Gate C passthrough, Phase 6까지 windowed-only)는 이
    스펙 범위 밖.
    """

    def __init__(self) -> None:
        self.observability = RunningAverage()
        self.explainability = RunningAverage()
        self.error_diagnosis = RunningAverage()
        self.latency_attribution = RunningAverage()

    def update(self, t: Any) -> None:
        extra = t.extra or {}

        _obs = extra.get("observability")
        if _obs is not None:
            _s = _obs.get("observability_score")
            if _s is not None:
                self.observability.add(_s)

        _expl = extra.get("explainability")
        if _expl is not None:
            _s = _expl.get("score")
            if _s is not None:
                self.explainability.add(_s)

        _ed = extra.get("error_diagnosis")
        if _ed is not None:
            _s = _ed.get("diagnosis_score")
            if _s is not None:
                self.error_diagnosis.add(_s)

        _la = extra.get("latency_attribution")
        if _la:
            _s = _la.get("attribution_score")
            if _s is not None:
                self.latency_attribution.add(_s)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "observability_avg": self.observability.average(),
            "observability_count": self.observability.count,
            "explainability_avg": self.explainability.average(),
            "explainability_count": self.explainability.count,
            "error_diagnosis_avg": self.error_diagnosis.average(),
            "error_diagnosis_count": self.error_diagnosis.count,
            "latency_attribution_avg": self.latency_attribution.average(),
            "latency_attribution_count": self.latency_attribution.count,
        }


class GateBSharedAgg:
    """SPEC-018 Phase 4 — Gate B(Behavioral Integrity)의 러닝 집계.

    ``gates/gate_b_behavioral/aggregate.py::compute()``의 6개 지표 전부를 다룬다 —
    트래커 의존성이 없는 100% task-derived Gate. ``loop_detection_rate``/``deadlock``은
    공유 분모(해당 Config가 설정된 태스크 수)로 나뉘므로 hit/presence 카운트 쌍으로
    추적한다. ``avg_goal_alignment_ref``/``avg_plan_coherence_ref``(Gate A 참조값)는
    Gate B 자체 상태가 아니므로 여기서 다루지 않는다.
    """

    def __init__(self) -> None:
        self.loop_count = RunningCount()
        self.loop_n = RunningCount()
        self.state_consistency = RunningAverage()
        self.deadlock_count = RunningCount()
        self.deadlock_n = RunningCount()
        self.deadlock_by_type = RunningCategoryCounter()
        self.scope = RunningAverage()
        self.tool_parameter_safety = RunningAverage()
        self.context_window = RunningAverage()

    def update(self, t: Any) -> None:
        extra = t.extra or {}

        _loop = extra.get("loop_detection")
        if _loop is not None:
            self.loop_n.add()
            if _loop.get("detected", False):
                self.loop_count.add()

        _sc = extra.get("state_consistency")
        if _sc is not None and _sc.get("consistency_score") is not None:
            self.state_consistency.add(_sc["consistency_score"])

        _dl = extra.get("deadlock")
        if _dl is not None:
            self.deadlock_n.add()
            if _dl.get("deadlock_detected"):
                self.deadlock_count.add()
                if _dl.get("deadlock_type"):
                    self.deadlock_by_type.add(str(_dl["deadlock_type"]))

        _scope = extra.get("scope")
        if _scope is not None and _scope.get("scope_score") is not None:
            self.scope.add(float(_scope["scope_score"]))

        _tps = extra.get("tool_parameter_safety")
        if _tps is not None and _tps.get("safety_score") is not None:
            self.tool_parameter_safety.add(float(_tps["safety_score"]))

        _cw = extra.get("context_window")
        if _cw and _cw.get("context_window_score") is not None:
            self.context_window.add(float(_cw["context_window_score"]))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "loop_count": self.loop_count.count,
            "loop_n": self.loop_n.count,
            "sc_avg": self.state_consistency.average(),
            "sc_count": self.state_consistency.count,
            "deadlock_count": self.deadlock_count.count,
            "deadlock_n": self.deadlock_n.count,
            "deadlock_by_type": self.deadlock_by_type.snapshot(),
            "scope_avg": self.scope.average(),
            "scope_count": self.scope.count,
            "tps_avg": self.tool_parameter_safety.average(),
            "tps_count": self.tool_parameter_safety.count,
            "cw_avg": self.context_window.average(),
            "cw_count": self.context_window.count,
        }


class GateASharedAgg:
    """SPEC-018 Phase 5 — Gate A(Goal Achievement)의 러닝 집계.

    ``gates/gate_a_goal/aggregate.py::compute()``의 6개 Config 기반 지표만 다룬다
    (instruction_adherence/goal_alignment/plan_coherence/subtask_completion/
    context_retention/knowledge_retention). goal_alignment/plan_coherence는 원본이
    LLM-judge relevance 점수와 가중 블렌딩한 **최종 스칼라**를 평균하므로, 여기서도
    블렌딩을 먼저 적용한 뒤 ``RunningAverage``에 누적한다(원점수를 누적하면 안 됨).
    TCR 컴포넌트(``tcr_tracker``)와 accuracy_evaluator/quality_evaluator 기반 부분은
    이 스펙 범위 밖 — 기존 ``_RunningTCRView`` 및 별도 무제한 트래커 그대로 유지된다.

    **알려진 한계**: ``update()``는 ``record_task()`` 호출 시점의 ``task_result.llm_judge``
    스냅숏으로 블렌딩한다. SPEC-006의 비동기 judge 경로(``ajudge()``/
    ``_process_async_judge_targets()``)는 ``record_task()``가 이미 반환한 뒤 별도
    코루틴에서 ``llm_judge``를 patch하므로, 그 패치가 러닝 집계에는 반영되지 않는다
    ("full" 모드는 매번 `tasks`를 재스캔하므로 patch 이후 값을 항상 반영 — 이 지점만
    windowed 모드와 다를 수 있음). 동기 judge 경로(`record_task()` 내부, lock 진입
    이전에 `dataclasses.replace()`로 이미 반영됨)는 영향받지 않는다. 이 격차를 메우려면
    SPEC-014의 `invalidate_report_cache()`와 유사하게 비동기 patch 지점에서 러닝
    집계도 재갱신해야 하며, 이는 Phase 5 승인 범위 밖의 별도 작업으로 남긴다.
    """

    def __init__(self) -> None:
        self.instruction_adherence = RunningAverage()
        self.goal_alignment = RunningAverage()
        self.plan_coherence = RunningAverage()
        self.subtask_completion = RunningAverage()
        self.context_retention = RunningAverage()
        self.knowledge_retention = RunningAverage()

    def update(self, t: Any) -> None:
        extra = t.extra or {}

        _ifr = extra.get("instruction_adherence")
        if _ifr is not None and _ifr.get("score") is not None:
            self.instruction_adherence.add(float(_ifr["score"]))

        _ga = extra.get("goal_alignment") or {}
        if _ga:
            _ga_score_raw = _ga.get("score")
            if _ga_score_raw is not None:
                _ga_score = float(_ga_score_raw)
                if _ga.get("use_llm_scoring"):
                    _lj = extra.get("llm_judge") or {}
                    _rel = (_lj.get("scores") or {}).get("relevance")
                    if _rel is not None:
                        try:
                            _rel_norm = min(1.0, max(0.0, float(_rel) / 5.0))
                            _w = max(0.0, min(1.0, float(_ga.get("llm_blend_weight", 0.5))))
                            _ga_score = _ga_score * (1 - _w) + _rel_norm * _w
                        except (TypeError, ValueError):
                            pass
                self.goal_alignment.add(_ga_score)

        _pc = extra.get("plan_coherence") or {}
        if _pc:
            _pc_score_raw = _pc.get("score")
            if _pc_score_raw is not None:
                _pc_score = float(_pc_score_raw)
                if _pc.get("use_llm_scoring"):
                    _lj_pc = extra.get("llm_judge") or {}
                    _rel_pc = (_lj_pc.get("scores") or {}).get("relevance")
                    if _rel_pc is not None:
                        try:
                            _w_pc = max(0.0, min(1.0, float(_pc.get("llm_blend_weight", 0.5))))
                            _rel_norm_pc = min(1.0, max(0.0, float(_rel_pc) / 5.0))
                            _pc_score = _pc_score * (1 - _w_pc) + _rel_norm_pc * _w_pc
                        except (TypeError, ValueError):
                            pass
                self.plan_coherence.add(_pc_score)

        _st = extra.get("subtask_completion")
        if (
            _st is not None
            and _st.get("completion_rate") is not None
            and int(_st.get("subtask_count", 0)) > 0
        ):
            self.subtask_completion.add(float(_st["completion_rate"]))

        _cr = extra.get("context_retention")
        if _cr is not None and _cr.get("retention_score") is not None:
            self.context_retention.add(float(_cr["retention_score"]))

        _kr = extra.get("knowledge_retention")
        if _kr is not None and _kr.get("retention_score") is not None:
            self.knowledge_retention.add(float(_kr["retention_score"]))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ifr_avg": self.instruction_adherence.average(),
            "ifr_count": self.instruction_adherence.count,
            "goal_avg": self.goal_alignment.average(),
            "goal_count": self.goal_alignment.count,
            "plan_avg": self.plan_coherence.average(),
            "plan_count": self.plan_coherence.count,
            "subtask_avg": self.subtask_completion.average(),
            "subtask_count": self.subtask_completion.count,
            "context_retention_avg": self.context_retention.average(),
            "context_retention_count": self.context_retention.count,
            "knowledge_retention_avg": self.knowledge_retention.average(),
            "knowledge_retention_count": self.knowledge_retention.count,
        }


class GateCSharedAgg:
    """SPEC-018 Phase 6 — Gate C(Reliability)의 러닝 집계.

    ``gates/gate_c_reliability/aggregate.py``의 reproducibility/fault_tolerance/
    graceful_degradation/idempotency/llm_faithfulness(단순 평균) + SLA
    breach_rate/window_penalty/budget_penalty를 다룬다. **`retry_consistency`는
    의도적으로 제외** — task_id 프리픽스별 무한 증식 위험이 있어 이 클래스에서
    다루지 않는다(별도 승인 대상, SPEC-018 Risks 참조).

    SLA window_penalty는 ``retention_mode``의 ``window_size``와 완전히 독립적인
    별도 링버퍼(``RunningWindow``, 기본 maxlen=10 — 실제 값은 최근 관측된
    ``SLAConfig.breach_window``로 매번 갱신)로 "최근 breach_window개 결과"를 순서
    보존하며 추적한다. budget_penalty는 세션 전체 누적 비용(``RunningSum``) 대비
    가장 최근 관측된 ``budget_usd`` 설정값(``RunningLastValue``)으로 계산한다 —
    원본 코드가 ``reversed(sla_results)``에서 첫 `_config` 존재 항목을 찾는 것과
    동일하게, 매 update()마다 `_config`가 있으면 최신값으로 덮어써 동일한 "가장
    최근 설정" 의미를 재현한다.
    """

    def __init__(self) -> None:
        self.reproducibility = RunningAverage()
        self.fault_tolerance = RunningAverage()
        self.graceful_degradation = RunningAverage()
        self.idempotency = RunningAverage()
        self.llm_faithfulness = RunningAverage()
        self.sla_breach = RunningCount()
        self.sla_n = RunningCount()
        self.sla_cost = RunningSum()
        self.sla_config = RunningLastValue()
        self.sla_window = RunningWindow(maxlen=10)

    def update(self, t: Any) -> None:
        extra = t.extra or {}

        _repro = extra.get("reproducibility")
        if (
            _repro is not None
            and _repro.get("score") is not None
            and int(_repro.get("run_count", 2)) >= 2
        ):
            self.reproducibility.add(float(_repro["score"]))

        _ft = extra.get("fault_tolerance")
        if _ft is not None and _ft.get("grade") not in ("none", "untracked"):
            _ft_sc = (
                _ft["recovery_quality_score"]
                if "recovery_quality_score" in _ft
                else _ft.get("recovery_rate", 1.0)
            )
            self.fault_tolerance.add(float(_ft_sc))

        _deg = extra.get("graceful_degradation")
        if _deg is not None and _deg.get("degradation_score") is not None:
            self.graceful_degradation.add(float(_deg["degradation_score"]))

        _idem = extra.get("idempotency")
        if _idem and _idem.get("idempotency_score") is not None:
            self.idempotency.add(float(_idem["idempotency_score"]))

        _lj = getattr(t, "llm_judge", None)
        if _lj and not (_lj or {}).get("skipped"):
            _faith = (_lj or {}).get("scores", {}).get("faithfulness")
            if isinstance(_faith, (int, float)):
                self.llm_faithfulness.add(float(_faith))

        _sla = extra.get("sla")
        if _sla is not None:
            self.sla_n.add()
            if not _sla.get("sla_met", True):
                self.sla_breach.add()
            self.sla_cost.add(float(_sla.get("cost_usd") or 0.0))
            _cfg = _sla.get("_config")
            if _cfg:
                self.sla_config.set(_cfg)
                self.sla_window.resize(int(_cfg.get("breach_window", 10)))
            self.sla_window.add(bool(_sla.get("sla_met", True)))

    def snapshot(self) -> Dict[str, Any]:
        _cfg = self.sla_config.get() or {}
        _sla_n = self.sla_n.count

        _sla_window_penalty = 0.0
        if _sla_n > 0:
            _warn_thr = int(_cfg.get("warn_threshold", 2))
            _fail_thr = int(_cfg.get("fail_threshold", 5))
            _recent = self.sla_window.values()
            _recent_breach = sum(1 for m in _recent if not m)
            if _recent_breach >= _fail_thr:
                _sla_window_penalty = 0.3
            elif _recent_breach >= _warn_thr:
                _sla_window_penalty = 0.1

        _sla_budget_penalty = 0.0
        if _sla_n > 0:
            _budget_usd = _cfg.get("budget_usd")
            if _budget_usd is not None:
                _total_cost = self.sla_cost.total
                if _total_cost > float(_budget_usd):
                    _overage = _total_cost / max(float(_budget_usd), 1e-9) - 1.0
                    _sla_budget_penalty = min(0.3, _overage * 0.1)

        return {
            "repro_avg": self.reproducibility.average(),
            "repro_count": self.reproducibility.count,
            "ft_avg": self.fault_tolerance.average(),
            "ft_count": self.fault_tolerance.count,
            "deg_avg": self.graceful_degradation.average(),
            "deg_count": self.graceful_degradation.count,
            "idem_avg": self.idempotency.average(),
            "idem_count": self.idempotency.count,
            "faith_avg": self.llm_faithfulness.average(),
            "faith_count": self.llm_faithfulness.count,
            "sla_breach_count": self.sla_breach.count,
            "sla_n": _sla_n,
            "sla_window_penalty": _sla_window_penalty,
            "sla_budget_penalty": _sla_budget_penalty,
        }
