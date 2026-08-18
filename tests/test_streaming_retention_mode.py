"""
tests/test_streaming_retention_mode.py
========================================
SPEC-004: 옵트인 스트리밍 모니터 모드(retention_mode) 검증.

REQ-1: PerformanceMonitor(retention_mode="full"|"windowed", window_size=int) 추가.
       기본값 "full"은 기존 동작(무제한 리스트)과 100% 동일해야 한다.
REQ-2: "windowed"에서 self.tasks는 deque(maxlen=window_size)처럼 동작한다.
       Gate A/C의 TCR 컴포넌트는 record_task() 시점에 갱신되는 러닝 집계로 전체
       이력을 반영한다(축소 범위 — 다른 Gate 지표는 windowed 태스크 목록만으로 재계산됨,
       자세한 내용은 SPEC-004 문서의 구현 노트 참고).
REQ-3: "windowed"에서 get_report_by_type/get_report_by_framework/export_by_framework/
       register_aggregator 호출 시 UserWarning이 매번 발생해야 한다.
REQ-4: window_size는 양의 정수만 허용 — 0 이하이면 ValueError.
"""
import warnings

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult


def _task(task_id: str, completion_score: float, **kwargs):
    return create_taskresult(
        task_id=task_id,
        question="q",
        response="r",
        execution_time=0.1,
        task_type="qa",
        completion_score=completion_score,
        **kwargs,
    )


def _hg(monitor: PerformanceMonitor):
    """모니터 현재 태스크 목록으로 harness groups를 계산한다 (private API — 기존
    tests/test_min_sample_guard.py의 헬퍼와 동일한 패턴)."""
    return monitor._compute_harness_groups(
        tasks=list(monitor.tcr_tracker.tasks),
        security_metrics=monitor._collect_security_metrics(),
        layer1=monitor._collect_layer1_metrics(),
        layer2=monitor._collect_layer2_metrics(),
        ttft_variability_config=monitor._ttft_variability_config,
        cost_predictability_config=monitor._cost_predictability_config,
    )


class TestRetentionModeDefaultIsFull:
    """REQ-1: retention_mode 미지정 시 기존 동작과 100% 동일."""

    def test_default_retention_mode_is_full(self):
        m = PerformanceMonitor()
        assert m._retention_mode == "full"
        assert m._window_size == 10000

    def test_full_mode_tasks_grow_unbounded(self):
        m = PerformanceMonitor()
        for i in range(50):
            m.record_task(_task(f"t{i}", 1.0))
        assert len(m.tasks) == 50

    def test_full_mode_no_windowed_warning_on_apis(self):
        m = PerformanceMonitor()
        m.record_task(_task("t0", 1.0))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            m.get_report_by_type("qa")
            m.get_report_by_framework("native")
            m.register_aggregator("noop", lambda tasks: len(tasks))
            _retention_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning) and "retention_mode" in str(x.message)
            ]
            assert _retention_warnings == []


class TestWindowSizeValidation:
    """REQ-4: window_size는 양의 정수만 허용."""

    @pytest.mark.parametrize("bad_size", [0, -1, -100])
    def test_non_positive_window_size_raises(self, bad_size):
        with pytest.raises(ValueError):
            PerformanceMonitor(window_size=bad_size)

    @pytest.mark.parametrize("bad_size", [0, -5])
    def test_non_positive_window_size_raises_even_in_full_mode(self, bad_size):
        # window_size는 retention_mode와 무관하게 항상 검증되어야 한다.
        with pytest.raises(ValueError):
            PerformanceMonitor(retention_mode="full", window_size=bad_size)

    def test_invalid_retention_mode_raises(self):
        with pytest.raises(ValueError):
            PerformanceMonitor(retention_mode="bogus")  # type: ignore[arg-type] — intentionally invalid, testing the runtime guard

    def test_positive_window_size_accepted(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=1)
        assert m._window_size == 1


class TestWindowedTaskCap:
    """REQ-2: windowed 모드에서 self.tasks가 deque(maxlen=window_size)처럼 동작."""

    def test_tasks_capped_at_window_size(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        assert len(m.tasks) == 5

    def test_tasks_keep_most_recent_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        kept_ids = [t.task_id for t in m.tasks]
        assert kept_ids == [f"t{i}" for i in range(15, 20)]

    def test_task_count_property_reflects_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            m.record_task(_task(f"t{i}", 1.0))
        assert m.task_count == 5


class TestWindowedRunningTCRAggregate:
    """REQ-2: Gate A/C의 TCR 컴포넌트는 windowed 상태에서도 전체 이력을 반영해야 한다
    (러닝 집계로 유지되는 유일한 지표 — 축소 범위)."""

    def test_running_agg_reflects_full_history_beyond_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        # 20개 태스크 중 정확히 절반(10개)만 완전 성공(completion_score=1.0)
        for i in range(20):
            cs = 1.0 if i % 2 == 0 else 0.0
            m.record_task(_task(f"t{i}", cs))

        # 윈도우에는 마지막 5개(t15..t19)만 남음: i=16,18 → cs=1.0(2개), i=15,17,19 → cs=0.0(3개)
        # windowed-only TCR이라면 2/5 = 40.0%가 되어야 하지만, 러닝 집계는 전체 20개 기준
        # 10/20 = 50.0%를 반영해야 한다.
        assert len(m.tasks) == 5
        agg = m._running_tcr_agg
        assert agg["total_count"] == 20
        assert agg["full_success"] == 10
        assert agg["failures"] == 10
        assert agg["weighted_sum"] == pytest.approx(10.0)

    def test_gate_a_tcr_pct_uses_full_history_not_window(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(20):
            cs = 1.0 if i % 2 == 0 else 0.0
            m.record_task(_task(f"t{i}", cs))

        hg = _hg(m)
        # 전체 이력 기준 TCR = 50.0% (windowed-only라면 40.0%가 나와야 함 — 다른 값)
        assert hg["A"]["details"]["tcr_pct"] == pytest.approx(50.0)
        assert hg["C"]["details"]["tcr_pct"] == pytest.approx(50.0)

    def test_gate_a_tcr_pct_matches_full_mode_equivalent(self):
        # windowed 모드의 러닝 집계 기반 tcr_pct가, 동일한 태스크를 "full" 모드로
        # 기록했을 때의 tcr_pct와 정확히 일치하는지 교차 검증한다.
        tasks_scores = [1.0 if i % 3 == 0 else 0.0 for i in range(30)]

        m_full = PerformanceMonitor(retention_mode="full")
        for i, cs in enumerate(tasks_scores):
            m_full.record_task(_task(f"t{i}", cs))
        full_tcr = _hg(m_full)["A"]["details"]["tcr_pct"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=7)
        for i, cs in enumerate(tasks_scores):
            m_win.record_task(_task(f"t{i}", cs))
        windowed_tcr = _hg(m_win)["A"]["details"]["tcr_pct"]

        assert windowed_tcr == pytest.approx(full_tcr)


class TestWindowedGateERunningMetrics:
    """SPEC-018 Phase 1: Gate E(Security Boundary)의 러닝 집계가 windowed 모드에서도
    전체 이력을 반영해야 한다(파일럿 Gate — 트래커 의존성 0, 다른 Gate 참조 0)."""

    def _make_security_task(self, task_id: str, kind: str):
        """kind별로 Gate E가 추적하는 각 extra 필드를 하나씩 채운 태스크를 만든다."""
        extra_by_kind = {
            "priv_esc": {"privilege_escalation": {"escalation_detected": True}},
            "chain_attack": {"tool_chain_attack": {"is_suspicious_chain": True}},
            "leakage": {"output_leakage": {"leakage_count": 2}},
            "injection": {"input_sanitization": {"threat_count": 1}},
            "tool_auth": {"tool_authorization": {"total_violations": 3}},
            "cvss": {"threat_severity": {"weighted_score": 7.5}},
            "compliance": {"compliance": {"compliance_score": 0.6}},
            "threat_response": {"threat_response": {"response_score": 0.9}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 20):
        kinds = [
            "priv_esc", "chain_attack", "leakage", "injection", "tool_auth",
            "cvss", "compliance", "threat_response", "clean",
        ]
        return [self._make_security_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        """윈도우보다 많은 태스크를 기록하면, 스냅숏이 밀려난 태스크의 기여분도 반영해야 한다."""
        m = PerformanceMonitor(enable_security_metrics=True, retention_mode="windowed", window_size=5)
        for t in self._build_sequence(20):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_e_agg.snapshot()
        # 20개 태스크 중 priv_esc/chain_attack/leakage/injection/tool_auth kind는
        # 각각 20/9 ≈ 2~3회씩 등장(윈도우에 남은 5개보다 훨씬 많음).
        assert snap["priv_esc_n"] >= 2
        assert snap["chain_attack_n"] >= 2
        assert snap["leakage_n"] >= 2
        assert snap["injection_n"] >= 2
        assert snap["tool_auth_n"] >= 2
        assert snap["cvss_count"] >= 2
        assert snap["compliance_count"] >= 2
        assert snap["tr_count"] >= 2
        assert snap["n"] == 20

    def test_gate_e_details_match_full_history_expectation(self):
        """세부 지표 단위 일치 — 최상위 score뿐 아니라 details의 각 키가 전체 이력
        기대값과 일치해야 한다."""
        m_full = PerformanceMonitor(enable_security_metrics=True)
        for t in self._build_sequence(18):
            m_full.record_task(t)
        expected = _hg(m_full)["E"]["details"]

        m_win = PerformanceMonitor(enable_security_metrics=True, retention_mode="windowed", window_size=4)
        for t in self._build_sequence(18):
            m_win.record_task(t)
        actual = _hg(m_win)["E"]["details"]

        assert actual == expected

    def test_full_vs_windowed_cross_check(self):
        """가장 강력한 회귀 방지 — 동일 태스크 시퀀스를 full/windowed로 각각 실행해
        Gate E details 전체가 일치하는지 확인."""
        tasks = self._build_sequence(27)

        m_full = PerformanceMonitor(enable_security_metrics=True, retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(enable_security_metrics=True, retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        e_full = _hg(m_full)["E"]
        e_win = _hg(m_win)["E"]
        assert e_win["details"] == e_full["details"]
        assert e_win["score"] == pytest.approx(e_full["score"])

    def test_full_mode_never_constructs_gate_e_agg(self):
        """불변식: retention_mode="full"에서는 _running_gate_e_agg 속성 자체가
        생성되지 않아야 한다."""
        m = PerformanceMonitor(enable_security_metrics=True)
        m.record_task(self._make_security_task("t0", "priv_esc"))
        assert not hasattr(m, "_running_gate_e_agg")

    def test_no_security_data_produces_none_score(self):
        """extra에 보안 데이터가 전혀 없고 enable_security_metrics=False이면
        Gate E 점수는 None이어야 한다(기존 동작 불변)."""
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for i in range(10):
            m.record_task(_task(f"t{i}", 1.0))
        hg = _hg(m)
        assert hg["E"]["score"] is None


class TestWindowedGateFRunningMetrics:
    """SPEC-018 Phase 2: Gate F(Multi-Agent Coordination)의 태스크 기반 4개 지표
    (consensus/propagation/agent_role/conflict_resolution)가 windowed 모드에서도
    전체 이력을 반영해야 한다. 트래커 기반 coordination/tool_selection은 이 스펙
    범위 밖(별도로 무제한 증식, 변경 없음)."""

    def _make_coord_task(self, task_id: str, kind: str):
        extra_by_kind = {
            "consensus": {"consensus": {"consensus_score": 0.9, "method": "majority"}},
            "consensus_single": {"consensus": {"consensus_score": 0.9, "method": "single"}},
            "propagation": {"propagation": {"fidelity_score": 0.8}},
            "agent_role": {"agent_role": {"role_compliance_score": 0.7}},
            "conflict_resolution": {"conflict_resolution": {"resolution_score": 0.6}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 20):
        kinds = ["consensus", "propagation", "agent_role", "conflict_resolution", "clean"]
        return [self._make_coord_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(20):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_f_agg.snapshot()
        assert snap["consensus_count"] >= 2
        assert snap["propagation_count"] >= 2
        assert snap["role_count"] >= 2
        assert snap["conflict_count"] >= 2

    def test_consensus_single_method_excluded_from_running_agg(self):
        """method="single"인 태스크는 러닝 집계에서도 제외되어야 한다(기존 필터 유지)."""
        m = PerformanceMonitor(retention_mode="windowed", window_size=10)
        for i in range(5):
            m.record_task(self._make_coord_task(f"s{i}", "consensus_single"))
        snap = m._running_gate_f_agg.snapshot()
        assert snap["consensus_count"] == 0
        assert snap["consensus_avg"] is None

    def test_gate_f_details_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(18):
            m_full.record_task(t)
        expected = _hg(m_full)["F"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(18):
            m_win.record_task(t)
        actual = _hg(m_win)["F"]["details"]

        assert actual == expected

    def test_full_vs_windowed_cross_check(self):
        tasks = self._build_sequence(27)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        f_full = _hg(m_full)["F"]
        f_win = _hg(m_win)["F"]
        assert f_win["details"] == f_full["details"]
        assert f_win["score"] == pytest.approx(f_full["score"])

    def test_full_mode_never_constructs_gate_f_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_coord_task("t0", "consensus"))
        assert not hasattr(m, "_running_gate_f_agg")


class TestWindowedGateGRunningMetrics:
    """SPEC-018 Phase 3: Gate G(Observability)의 태스크 기반 4개 지표
    (observability/explainability/error_diagnosis/latency_attribution)가 windowed
    모드에서도 전체 이력을 반영해야 한다. hall_rate/avg_llm_faithfulness는 Gate C가
    Phase 6에서 마이그레이션되기 전까지 여전히 windowed-only(별도 회귀 아님)."""

    def _make_obs_task(self, task_id: str, kind: str):
        extra_by_kind = {
            "observability": {"observability": {"observability_score": 0.9}},
            "explainability": {"explainability": {"score": 0.8}},
            "error_diagnosis": {"error_diagnosis": {"diagnosis_score": 0.7}},
            "latency_attribution": {"latency_attribution": {"attribution_score": 0.6}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 20):
        kinds = ["observability", "explainability", "error_diagnosis", "latency_attribution", "clean"]
        return [self._make_obs_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(20):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_g_agg.snapshot()
        assert snap["observability_count"] >= 2
        assert snap["explainability_count"] >= 2
        assert snap["error_diagnosis_count"] >= 2
        assert snap["latency_attribution_count"] >= 2

    def test_gate_g_migrated_details_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(18):
            m_full.record_task(t)
        expected = _hg(m_full)["G"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(18):
            m_win.record_task(t)
        actual = _hg(m_win)["G"]["details"]

        # 4개 마이그레이션된 키만 비교 — hallucination_rate는 Gate C의 hallucination_detector
        # (별도의, retention_mode와 무관하게 항상 무제한 증식하는 트래커)에서 오므로 Gate G/C의
        # task 기반 지표 마이그레이션과 무관하게 애초부터 전체 이력을 반영해 왔다(별도 검증 불필요).
        for key in (
            "avg_observability_score", "avg_explainability",
            "avg_error_diagnosis", "avg_latency_attribution",
        ):
            assert actual[key] == expected[key], key

    def test_full_vs_windowed_cross_check_migrated_keys(self):
        tasks = self._build_sequence(27)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        g_full = _hg(m_full)["G"]["details"]
        g_win = _hg(m_win)["G"]["details"]
        for key in (
            "avg_observability_score", "avg_explainability",
            "avg_error_diagnosis", "avg_latency_attribution",
        ):
            assert g_win[key] == pytest.approx(g_full[key]), key

    def test_full_mode_never_constructs_gate_g_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_obs_task("t0", "observability"))
        assert not hasattr(m, "_running_gate_g_agg")


class TestWindowedGateBRunningMetrics:
    """SPEC-018 Phase 4: Gate B(Behavioral Integrity)의 6개 지표
    (loop_detection/state_consistency/deadlock/scope/tool_parameter_safety/
    context_window)가 windowed 모드에서도 전체 이력을 반영해야 한다. 트래커 의존성
    없는 100% task-derived Gate — 공유 분모(loop/deadlock) + 카테고리 카운터
    (deadlock_by_type) 패턴을 처음 검증."""

    def _make_behavioral_task(self, task_id: str, kind: str):
        extra_by_kind = {
            "loop_detected": {"loop_detection": {"detected": True}},
            "loop_clean": {"loop_detection": {"detected": False}},
            "state_consistency": {"state_consistency": {"consistency_score": 0.8}},
            "deadlock_resource": {"deadlock": {"deadlock_detected": True, "deadlock_type": "resource"}},
            "deadlock_comm": {"deadlock": {"deadlock_detected": True, "deadlock_type": "communication"}},
            "deadlock_clean": {"deadlock": {"deadlock_detected": False}},
            "scope": {"scope": {"scope_score": 0.7}},
            "tool_param_safety": {"tool_parameter_safety": {"safety_score": 0.6}},
            "context_window": {"context_window": {"context_window_score": 0.5}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 30):
        kinds = [
            "loop_detected", "loop_clean", "state_consistency", "deadlock_resource",
            "deadlock_comm", "deadlock_clean", "scope", "tool_param_safety",
            "context_window", "clean",
        ]
        return [self._make_behavioral_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(30):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_b_agg.snapshot()
        assert snap["loop_n"] >= 2
        assert snap["sc_count"] >= 2
        assert snap["deadlock_n"] >= 2
        assert snap["scope_count"] >= 2
        assert snap["tps_count"] >= 2
        assert snap["cw_count"] >= 2
        assert snap["deadlock_by_type"] == {"resource": 3, "communication": 3}

    def test_gate_b_details_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(20):
            m_full.record_task(t)
        expected = _hg(m_full)["B"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(20):
            m_win.record_task(t)
        actual = _hg(m_win)["B"]["details"]

        assert actual == expected

    def test_full_vs_windowed_cross_check(self):
        tasks = self._build_sequence(40)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        b_full = _hg(m_full)["B"]
        b_win = _hg(m_win)["B"]
        assert b_win["details"] == b_full["details"]
        assert b_win["score"] == pytest.approx(b_full["score"])

    def test_full_mode_never_constructs_gate_b_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_behavioral_task("t0", "loop_detected"))
        assert not hasattr(m, "_running_gate_b_agg")


class TestWindowedGateARunningMetrics:
    """SPEC-018 Phase 5: Gate A(Goal Achievement)의 6개 Config 지표
    (instruction_adherence/goal_alignment/plan_coherence/subtask_completion/
    context_retention/knowledge_retention)가 windowed 모드에서도 전체 이력을
    반영해야 한다. goal_alignment/plan_coherence는 LLM-judge 블렌딩 후 최종
    스칼라를 누적하는지가 핵심 검증 대상."""

    def _make_goal_task(self, task_id: str, kind: str):
        extra_by_kind = {
            "instruction_adherence": {"instruction_adherence": {"score": 0.9}},
            "goal_alignment": {"goal_alignment": {"score": 0.8, "use_llm_scoring": False}},
            "goal_alignment_blended": {
                "goal_alignment": {"score": 0.6, "use_llm_scoring": True, "llm_blend_weight": 0.5},
                "llm_judge": {"scores": {"relevance": 4.0}},  # 4.0/5.0=0.8 정규화 → (0.6+0.8)/2=0.7
            },
            "plan_coherence": {"plan_coherence": {"score": 0.7, "use_llm_scoring": False}},
            "subtask_completion": {
                "subtask_completion": {"completion_rate": 0.6, "subtask_count": 3}
            },
            "context_retention": {"context_retention": {"retention_score": 0.5}},
            "knowledge_retention": {"knowledge_retention": {"retention_score": 0.4}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 21):
        kinds = [
            "instruction_adherence", "goal_alignment_blended", "plan_coherence",
            "subtask_completion", "context_retention", "knowledge_retention", "clean",
        ]
        return [self._make_goal_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(21):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_a_agg.snapshot()
        assert snap["ifr_count"] >= 2
        assert snap["goal_count"] >= 2
        assert snap["plan_count"] >= 2
        assert snap["subtask_count"] >= 2
        assert snap["context_retention_count"] >= 2
        assert snap["knowledge_retention_count"] >= 2

    def test_goal_alignment_llm_blend_matches_manual_computation(self):
        """LLM-judge 블렌딩 후 최종 스칼라(0.7)가 누적되어야 한다(원점수 0.6이 아님)."""
        m = PerformanceMonitor(retention_mode="windowed", window_size=10)
        for i in range(3):
            m.record_task(self._make_goal_task(f"g{i}", "goal_alignment_blended"))
        snap = m._running_gate_a_agg.snapshot()
        assert snap["goal_avg"] == pytest.approx(0.7)

    def test_gate_a_migrated_details_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(21):
            m_full.record_task(t)
        expected = _hg(m_full)["A"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(21):
            m_win.record_task(t)
        actual = _hg(m_win)["A"]["details"]

        for key in (
            "avg_instruction_adherence", "avg_goal_alignment", "avg_plan_coherence",
            "avg_subtask_completion", "avg_context_retention", "avg_knowledge_retention",
        ):
            assert actual[key] == expected[key], key

    def test_full_vs_windowed_cross_check_migrated_keys(self):
        tasks = self._build_sequence(35)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        a_full = _hg(m_full)["A"]["details"]
        a_win = _hg(m_win)["A"]["details"]
        for key in (
            "avg_instruction_adherence", "avg_goal_alignment", "avg_plan_coherence",
            "avg_subtask_completion", "avg_context_retention", "avg_knowledge_retention",
        ):
            assert a_win[key] == pytest.approx(a_full[key]), key

    def test_full_mode_never_constructs_gate_a_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_goal_task("t0", "instruction_adherence"))
        assert not hasattr(m, "_running_gate_a_agg")


class TestWindowedGateCRunningMetrics:
    """SPEC-018 Phase 6: Gate C(Reliability)의 reproducibility/fault_tolerance/
    graceful_degradation/idempotency/llm_faithfulness + SLA breach_rate/
    window_penalty/budget_penalty가 windowed 모드에서도 전체 이력을 반영해야
    한다. `retry_consistency`는 의도적으로 제외 — windowed 부분집합 기준으로만
    계산되는지 별도 검증."""

    def _make_reliability_task(self, task_id: str, kind: str, **extra_overrides):
        extra_by_kind = {
            "reproducibility": {"reproducibility": {"score": 0.9, "run_count": 3}},
            "fault_tolerance": {"fault_tolerance": {"grade": "full_recovery", "recovery_rate": 0.8}},
            "graceful_degradation": {"graceful_degradation": {"degradation_score": 0.7}},
            "idempotency": {"idempotency": {"idempotency_score": 0.6}},
            "clean": {},
        }
        extra = dict(extra_by_kind[kind])
        extra.update(extra_overrides)
        return _task(task_id, 1.0, extra=extra)

    def _build_sequence(self, n: int = 20):
        kinds = ["reproducibility", "fault_tolerance", "graceful_degradation", "idempotency", "clean"]
        return [self._make_reliability_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(20):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_c_agg.snapshot()
        assert snap["repro_count"] >= 2
        assert snap["ft_count"] >= 2
        assert snap["deg_count"] >= 2
        assert snap["idem_count"] >= 2

    def test_gate_c_migrated_details_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(18):
            m_full.record_task(t)
        expected = _hg(m_full)["C"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(18):
            m_win.record_task(t)
        actual = _hg(m_win)["C"]["details"]

        for key in (
            "avg_reproducibility", "avg_fault_tolerance", "avg_degradation", "avg_idempotency",
        ):
            assert actual[key] == expected[key], key

    def test_full_vs_windowed_cross_check_migrated_keys(self):
        tasks = self._build_sequence(35)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        c_full = _hg(m_full)["C"]["details"]
        c_win = _hg(m_win)["C"]["details"]
        for key in (
            "avg_reproducibility", "avg_fault_tolerance", "avg_degradation", "avg_idempotency",
        ):
            assert c_win[key] == pytest.approx(c_full[key]), key

    def test_full_mode_never_constructs_gate_c_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_reliability_task("t0", "reproducibility"))
        assert not hasattr(m, "_running_gate_c_agg")

    def test_retry_consistency_now_reflects_full_history_under_lru_cap(self):
        """SPEC-018 Phase 7: retry_consistency가 GateCRetryConsistencyAgg(LRU 캡 적용)로
        마이그레이션됐다 — 프리픽스 카디널리티가 캡(기본 5,000) 이내인 일반적인 경우,
        windowed 모드도 이제 전체 이력 기준(개선 보너스 포함)과 일치해야 한다."""
        # task_id를 0-패딩(retry_00..retry_19)해 문자열 정렬이 수치 순서와 일치하게 한다
        # (rsplit("_", 1) 그룹핑 로직이 문자열 정렬에 의존하므로, 패딩 없으면
        # "retry_10" < "retry_2" 처럼 의도와 다른 순서로 그룹 내 first/last가 뒤바뀐다).
        tasks = []
        for i in range(20):
            t = create_taskresult(
                task_id=f"retry_{i:02d}", question="q", response="r", execution_time=0.1,
                task_type="qa", completion_score=1.0,
                accuracy_score=0.3 if i < 15 else 0.9,
                extra={"retry_consistency": {"consistency_score": 0.5, "_config": {"group_by_task_prefix": True}}},
            )
            tasks.append(t)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_rc = _hg(m_full)["C"]["details"]["avg_retry_consistency"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in tasks:
            m_win.record_task(t)
        win_rc = _hg(m_win)["C"]["details"]["avg_retry_consistency"]

        # 전체 이력(첫 task accuracy=0.3, 마지막 accuracy=0.9로 delta=+0.6 → 개선 보너스 적용)이
        # windowed 부분집합(마지막 5개만 보면 delta=0)과 이제는 일치해야 한다 — LRU 캡(5,000)을
        # 전혀 건드리지 않는 이 픽스처(단일 프리픽스, 20개 태스크)에서는 근사가 발동하지 않는다.
        assert win_rc == pytest.approx(full_rc)
        assert full_rc == pytest.approx(0.6)  # 0.5 + 0.1 개선 보너스

    def test_retry_consistency_lru_cap_evicts_oldest_prefix_when_exceeded(self):
        """프리픽스 카디널리티가 LRU 캡을 초과하면 가장 오래전에 갱신된 프리픽스가
        제거되고 그 기여분이 최종 평균에서 빠진다 — 의도적으로 승인된 근사(SPEC-018
        Phase 7 REQ-C1)가 실제로 발동하는지 확인한다."""
        m = PerformanceMonitor(retention_mode="windowed", window_size=10)
        agg = m._running_gate_c_retry_agg
        agg._MAX_PREFIXES = 3  # 테스트용으로 캡을 작게 조정

        def _rc_task(task_id: str):
            return create_taskresult(
                task_id=task_id, question="q", response="r", execution_time=0.1,
                task_type="qa", completion_score=1.0,
                extra={"retry_consistency": {"consistency_score": 0.5, "_config": {"group_by_task_prefix": True}}},
            )

        for prefix_i in range(5):  # 5개의 distinct 프리픽스 — 캡(3)을 초과
            m.record_task(_rc_task(f"prefix{prefix_i}_00"))

        snap = agg.snapshot()
        assert snap["evicted_count"] == 2  # 5개 중 캡(3) 초과분 2개 제거됨
        assert len(agg._prefixes) == 3

    def test_full_mode_never_constructs_gate_c_retry_agg(self):
        m = PerformanceMonitor()
        m.record_task(create_taskresult(
            task_id="t0", question="q", response="r", execution_time=0.1,
            task_type="qa", completion_score=1.0,
            extra={"retry_consistency": {"consistency_score": 0.5}},
        ))
        assert not hasattr(m, "_running_gate_c_retry_agg")

    def test_sla_window_penalty_ring_buffer_independent_of_window_size(self):
        """SLA breach_window(예: 3)는 retention_mode의 window_size(예: 5)와 독립적인
        별도 링버퍼로 추적되어야 한다 — 윈도우 밖으로 밀려난 태스크의 SLA 결과도
        breach_window 범위 안에 있다면 페널티 계산에 반영되어야 한다."""
        tasks = []
        for i in range(10):
            # 마지막 3개(breach_window)만 breach, 나머지는 정상
            is_breach = i >= 7
            t = create_taskresult(
                task_id=f"sla_{i}", question="q", response="r", execution_time=0.1,
                task_type="qa", completion_score=1.0,
                extra={"sla": {
                    "sla_met": not is_breach, "cost_usd": 0.01,
                    "_config": {"breach_window": 3, "warn_threshold": 2, "fail_threshold": 3},
                }},
            )
            tasks.append(t)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_penalty = _hg(m_full)["C"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in tasks:
            m_win.record_task(t)
        win_penalty = _hg(m_win)["C"]

        # 두 모드 모두 마지막 3개(breach_window)가 전부 breach → fail_threshold(3) 도달
        # → sla_breach_rate가 동일해야 한다(전체 이력 기준 breach_count/n 비교).
        assert win_penalty["details"]["sla_breach_rate"] == pytest.approx(
            full_penalty["details"]["sla_breach_rate"]
        )

    def test_sla_breach_count_reflects_full_history_even_when_window_evicts_all_sla_tasks(self):
        """회귀 방지: sla_breach_count의 표시 여부가 windowed 부분집합의 존재 여부가
        아니라 전체 이력 기준으로 결정되어야 한다(원본 코드의 `if _sla_results:` 게이팅이
        windowed 모드에서 잘못된 None을 낼 수 있었던 버그의 수정 확인)."""
        tasks = []
        for i in range(5):
            tasks.append(create_taskresult(
                task_id=f"sla_old_{i}", question="q", response="r", execution_time=0.1,
                task_type="qa", completion_score=1.0,
                extra={"sla": {"sla_met": False, "cost_usd": 0.01}},
            ))
        # 이후 SLA 데이터가 전혀 없는 태스크만 추가 — 윈도우가 전부 밀어냄
        for i in range(5):
            tasks.append(create_taskresult(
                task_id=f"clean_{i}", question="q", response="r", execution_time=0.1,
                task_type="qa", completion_score=1.0,
            ))

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        details = _hg(m_win)["C"]["details"]
        # 윈도우에는 SLA 데이터가 있는 태스크가 하나도 남아있지 않지만(전부 clean_*),
        # 전체 이력에는 5건의 SLA breach가 있었으므로 None이 아니라 5가 나와야 한다.
        assert details["sla_breach_count"] == 5


class TestWindowedGateDRunningMetrics:
    """SPEC-018 Phase 7: Gate D(Performance Contract)의 러닝 집계.

    efficiency/resource_budget는 정확한 재현(단순 평균·누적합·최근값 덮어쓰기)이므로
    다른 Gate와 동일한 4종 패턴으로 검증한다. ttft_variability/cost_predictability는
    GateDSharedAgg._RESERVOIR_SIZE(2,000)개 슬라이딩 샘플 기반 **의도적으로 승인된
    근사**이므로, 이력이 reservoir 크기 이내일 때만 exact match를 요구하고, reservoir를
    초과하는 시나리오는 근사가 실제로 발동함(다르게 나옴)을 확인한다. p95 latency는
    latency_tracker가 애초부터 무제한이라 별도 검증(이미 전체 이력)만 한다.
    """

    def _make_perf_task(self, task_id: str, kind: str):
        extra_by_kind = {
            "eff_calibrated": {"efficiency": {"calibrated_score": 0.8}},
            "eff_ratio": {"efficiency": {"efficiency_ratio": 0.05, "cost_unit": "tokens"}},
            "resource_budget": {"resource_budget": {"budget_score": 0.7, "_config": {"rollover": False}}},
            "clean": {},
        }
        return _task(task_id, 1.0, extra=extra_by_kind[kind])

    def _build_sequence(self, n: int = 20):
        kinds = ["eff_calibrated", "eff_ratio", "resource_budget", "clean"]
        return [self._make_perf_task(f"t{i}", kinds[i % len(kinds)]) for i in range(n)]

    def test_running_agg_reflects_evicted_history(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in self._build_sequence(20):
            m.record_task(t)

        assert len(m.tasks) == 5
        snap = m._running_gate_d_agg.snapshot()
        assert snap["eff_calibrated_count"] >= 2
        assert snap["eff_ratio_count"] >= 2
        assert snap["rb_budget_score_count"] >= 2
        assert snap["total_n"] == 20

    def test_exact_metrics_match_full_history_expectation(self):
        m_full = PerformanceMonitor()
        for t in self._build_sequence(18):
            m_full.record_task(t)
        expected = _hg(m_full)["D"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in self._build_sequence(18):
            m_win.record_task(t)
        actual = _hg(m_win)["D"]["details"]

        for key in (
            "avg_efficiency_calibrated_score", "avg_efficiency_ratio", "avg_budget_score",
        ):
            assert actual[key] == expected[key], key

    def test_exact_metrics_full_vs_windowed_cross_check(self):
        tasks = self._build_sequence(35)

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)

        d_full = _hg(m_full)["D"]["details"]
        d_win = _hg(m_win)["D"]["details"]
        for key in (
            "avg_efficiency_calibrated_score", "avg_efficiency_ratio", "avg_budget_score",
        ):
            assert d_win[key] == pytest.approx(d_full[key]), key

    def test_full_mode_never_constructs_gate_d_agg(self):
        m = PerformanceMonitor()
        m.record_task(self._make_perf_task("t0", "eff_calibrated"))
        assert not hasattr(m, "_running_gate_d_agg")

    def test_resource_budget_rollover_mode_exact_via_running_sums(self):
        """rollover=True 모드(세션 누적 소비 대 전체 한도 비교)도 정확히 재현되는지 확인."""
        tasks = []
        for i in range(10):
            tasks.append(_task(f"rb{i}", 1.0, extra={"resource_budget": {
                "_config": {"rollover": True, "max_tokens": 1000},
                "_consumed": {"tokens": 80},
            }}))

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_budget = _hg(m_full)["D"]["details"]["avg_budget_score"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=4)
        for t in tasks:
            m_win.record_task(t)
        win_budget = _hg(m_win)["D"]["details"]["avg_budget_score"]

        # 10개 태스크 × 80 tokens = 800 소비, 한도 10 × 1000 = 10000 → utilization=0.08 → score=0.92
        assert win_budget == pytest.approx(full_budget)
        assert win_budget == pytest.approx(0.92)

    def test_ttft_variability_exact_within_reservoir_size(self):
        """이력이 reservoir 크기(2,000) 이내면 ttft_variability도 전체 이력과 일치해야 한다."""
        tasks = [
            _task(f"ttft{i}", 1.0, extra={"ttft_ms": 100.0 + (i % 7) * 15.0})
            for i in range(30)
        ]

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_d = _hg(m_full)["D"]["details"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in tasks:
            m_win.record_task(t)
        win_d = _hg(m_win)["D"]["details"]

        assert win_d["ttft_variability_score"] == pytest.approx(full_d["ttft_variability_score"])
        assert win_d["ttft_stddev_ms"] == pytest.approx(full_d["ttft_stddev_ms"])
        assert win_d["ttft_p50_ms"] == pytest.approx(full_d["ttft_p50_ms"])
        assert win_d["ttft_p95_ms"] == pytest.approx(full_d["ttft_p95_ms"])

    def test_ttft_reservoir_approximation_activates_beyond_reservoir_size(self):
        """이력이 reservoir 크기를 초과하면 근사가 실제로 발동(값이 달라짐)해야 한다 —
        승인된 트레이드오프가 실제로 존재함을 증명하는 회귀 방지 테스트."""
        m = PerformanceMonitor(retention_mode="windowed", window_size=10)
        agg = m._running_gate_d_agg
        agg._RESERVOIR_SIZE = 5
        agg.ttft_reservoir.resize(5)

        # 초반 100ms 값들(reservoir에서 밀려남) 다음 500ms 값들(reservoir에 남음)
        for i in range(20):
            ttft = 100.0 if i < 15 else 500.0
            m.record_task(_task(f"ttft{i}", 1.0, extra={"ttft_ms": ttft}))

        snap = agg.snapshot()
        # reservoir(마지막 5개)는 전부 500.0 → stddev=0, 실제 전체 이력(100/500 혼재)의
        # stddev와는 다르다 — 근사가 발동했다는 증거.
        assert snap["ttft_values"] == [500.0] * 5

    def test_cost_predictability_exact_within_reservoir_size(self):
        """이력이 reservoir 크기 이내면 cost_predictability도 전체 이력과 일치해야 한다."""
        tasks = [
            _task(f"cost{i}", 1.0, tokens_used={"total": 100 + (i % 5) * 20})
            for i in range(30)
        ]

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_cv = _hg(m_full)["D"]["details"]["avg_cost_predictability"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=5)
        for t in tasks:
            m_win.record_task(t)
        win_cv = _hg(m_win)["D"]["details"]["avg_cost_predictability"]

        assert win_cv == pytest.approx(full_cv)

    def test_p95_latency_already_full_history_via_uncapped_latency_tracker(self):
        """p95_latency_s는 latency_tracker(retention_mode와 무관하게 이미 무제한 증식)에서
        오므로 GateDSharedAgg와 무관하게 windowed 모드에서도 애초부터 전체 이력을 반영한다."""
        tasks = [
            create_taskresult(
                task_id=f"lat{i}", question="q", response="r",
                execution_time=float(i) / 10.0, task_type="qa", completion_score=1.0,
            )
            for i in range(1, 21)
        ]

        m_full = PerformanceMonitor(retention_mode="full")
        for t in tasks:
            m_full.record_task(t)
        full_p95 = _hg(m_full)["D"]["details"]["p95_latency_s"]

        m_win = PerformanceMonitor(retention_mode="windowed", window_size=3)
        for t in tasks:
            m_win.record_task(t)
        win_p95 = _hg(m_win)["D"]["details"]["p95_latency_s"]

        assert win_p95 == pytest.approx(full_p95)


class TestWindowedRetentionWarnings:
    """REQ-3: windowed 모드에서 get_report_by_type/get_report_by_framework/
    export_by_framework/register_aggregator 호출 시 UserWarning이 매번 발생."""

    def _monitor(self):
        m = PerformanceMonitor(retention_mode="windowed", window_size=5)
        m.record_task(_task("t0", 1.0))
        return m

    def test_get_report_by_type_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.get_report_by_type("qa")

    def test_get_report_by_framework_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.get_report_by_framework("native")

    def test_register_aggregator_warns(self):
        m = self._monitor()
        with pytest.warns(UserWarning, match="retention_mode"):
            m.register_aggregator("noop", lambda tasks: len(tasks))

    def test_export_by_framework_warns(self, tmp_path):
        m = self._monitor()
        m.output_dir = tmp_path
        with pytest.warns(UserWarning, match="retention_mode"):
            m.export_by_framework("native", "out")

    def test_warning_fires_every_call_not_just_once(self):
        m = self._monitor()
        for _ in range(3):
            with pytest.warns(UserWarning, match="retention_mode"):
                m.get_report_by_type("qa")
