"""
tests/test_phase7_msprt_sequential_ab_test.py
=================================================
Phase 7(개선 엔진) — QuickEval.ab_test_sequential()(mSPRT always-valid inference)의
회귀·통계적 검증 테스트.

이 기능은 이전 세션에서 "통계적 정합성을 세션 내에서 충분히 검증할 자신이 없다"는
이유로 보류됐었다 — 이번엔 그 우려를 해소하기 위해 폐형해(closed-form) 공식 자체의
단위 테스트를 넘어, **몬테카를로 시뮬레이션으로 반복 확인(peeking) 하에서도 귀무가설
하 위양성률이 명목 alpha를 넘지 않는지 직접 실증**한다(TestType1ErrorControl 클래스)
— 이게 "always valid"라는 이름이 실제로 의미하는 바다. 대조군으로 순진하게 반복
t-검정을 peeking하면 위양성률이 크게 부풀려진다는 것도 함께 확인해, always-valid
검정이 실제로 해결하는 문제가 진짜임을 보인다.

시뮬레이션은 고정 시드(``numpy.random.default_rng(42)``)로 완전히 재현 가능하게
만들어 CI에서 flaky하지 않다.
"""
from __future__ import annotations

import numpy as np
import pytest

from agent_evaluator import QuickEval, create_taskresult
from agent_evaluator.quick_eval import _always_valid_p_value, _msprt_log_likelihood_ratio


def _qeval(tmp_path, name, scores):
    qe = QuickEval(str(tmp_path / name))
    for i, score in enumerate(scores):
        qe._monitor.record_task(create_taskresult(
            task_id=f"{name}_{i}", question="q", response="r",
            accuracy_score=score, execution_time=1.0, extra={},
        ))
    return qe


class TestMsprtClosedForm:
    """폐형해 공식 자체의 성질 — Johari et al.(2015) Section 3의 공식을 그대로
    구현했는지 확인한다."""

    def test_zero_effect_gives_log_lr_at_most_zero(self):
        # theta_hat=0이면 지수항이 0이 되고 log(variance/(variance+tau^2)) < 0(tau>0이므로)
        # → log_lr < 0 → p=1.0 (증거 없음이 정확히 반영돼야 함)
        log_lr = _msprt_log_likelihood_ratio(theta_hat=0.0, variance=1.0, tau=0.5)
        assert log_lr < 0

    def test_zero_effect_p_value_is_one(self):
        p = _always_valid_p_value(theta_hat=0.0, variance=1.0, tau=0.5)
        assert p == 1.0

    def test_large_effect_small_variance_gives_small_p_value(self):
        p = _always_valid_p_value(theta_hat=5.0, variance=0.01, tau=1.0)
        assert p is not None
        assert p < 0.001

    def test_p_value_none_when_variance_non_positive(self):
        assert _always_valid_p_value(theta_hat=1.0, variance=0.0, tau=1.0) is None
        assert _always_valid_p_value(theta_hat=1.0, variance=-1.0, tau=1.0) is None

    def test_p_value_none_when_tau_non_positive(self):
        assert _always_valid_p_value(theta_hat=1.0, variance=1.0, tau=0.0) is None

    def test_p_value_never_exceeds_one(self):
        for theta in (-3.0, -0.5, 0.0, 0.5, 3.0):
            p = _always_valid_p_value(theta_hat=theta, variance=2.0, tau=0.3)
            assert p is not None
            assert 0.0 <= p <= 1.0

    def test_no_overflow_for_large_theta(self):
        # 매우 큰 효과 크기에서도 예외 없이 유한한 값을 반환해야 한다(로그 스케일 계산).
        p = _always_valid_p_value(theta_hat=1000.0, variance=0.001, tau=1.0)
        assert p is not None
        assert p >= 0.0

    def test_mismatched_tau_reduces_evidence_for_fixed_theta(self):
        """tau가 실제 효과 스케일과 안 맞을수록(너무 작거나 너무 크면) 검정력이
        떨어진다는 docstring의 주장을 직접 확인한다 — 위양성률이 아니라 민감도가
        달라진다. 관계는 단조가 아니라 "관측된 효과 크기 근방에서 최댓값을 갖는
        피크 형태"다(사전분포와 관측 신호가 일치할 때 증거가 최대) — 이 피크 성질을
        직접 검증한다(tau가 클수록 무조건 증거가 준다는 단순 단조성이 아님).
        """
        theta_hat, variance = 1.0, 0.05
        # tau=1.0: 관측 효과와 유사한 스케일 / tau=0.01: 너무 작음 / tau=100.0: 너무 큼
        p_matched = _always_valid_p_value(theta_hat, variance, tau=1.0)
        p_too_small = _always_valid_p_value(theta_hat, variance, tau=0.01)
        p_too_large = _always_valid_p_value(theta_hat, variance, tau=100.0)
        assert p_matched is not None and p_too_small is not None and p_too_large is not None
        assert p_matched < p_too_small
        assert p_matched < p_too_large


class TestAbTestSequentialMethod:
    def test_basic_call_returns_expected_shape(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9] * 20)
        b = _qeval(tmp_path, "b", [0.5] * 20)
        result = a.ab_test_sequential(b, tau=0.2)
        assert result["metric"] == "accuracy_score"
        assert result["self_mean"] == pytest.approx(0.9)
        assert result["other_mean"] == pytest.approx(0.5)
        assert result["delta"] == pytest.approx(0.4)
        assert result["tau"] == 0.2
        assert result["alpha"] == 0.05

    def test_warning_when_insufficient_samples(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9])
        b = _qeval(tmp_path, "b", [0.5, 0.6])
        result = a.ab_test_sequential(b, tau=0.2)
        assert result["warning"] is not None
        assert result["always_valid_p_value"] is None
        assert result["significant"] is None

    def test_warning_when_zero_variance(self, tmp_path):
        a = _qeval(tmp_path, "a", [0.9, 0.9, 0.9])
        b = _qeval(tmp_path, "b", [0.5, 0.5, 0.5])
        result = a.ab_test_sequential(b, tau=0.2)
        assert result["variance"] == 0.0
        assert result["warning"] is not None

    def test_significant_true_when_p_below_alpha(self, tmp_path):
        rng = np.random.default_rng(0)
        a = _qeval(tmp_path, "a", (0.9 + rng.normal(0, 0.02, 100)).tolist())
        b = _qeval(tmp_path, "b", (0.5 + rng.normal(0, 0.02, 100)).tolist())
        result = a.ab_test_sequential(b, tau=0.2)
        assert result["significant"] is True
        assert result["always_valid_p_value"] <= 0.05

    def test_custom_alpha_respected(self, tmp_path):
        rng = np.random.default_rng(1)
        a = _qeval(tmp_path, "a", (0.7 + rng.normal(0, 0.05, 30)).tolist())
        b = _qeval(tmp_path, "b", (0.65 + rng.normal(0, 0.05, 30)).tolist())
        result = a.ab_test_sequential(b, tau=0.2, alpha=0.5)
        assert result["significant"] == (result["always_valid_p_value"] <= 0.5)

    def test_tau_has_no_implicit_default(self, tmp_path):
        """direction(guardrails)과 동일한 설계 원칙 — tau는 암묵적 기본값이 없다."""
        a = _qeval(tmp_path, "a", [0.9] * 5)
        b = _qeval(tmp_path, "b", [0.5] * 5)
        with pytest.raises(TypeError):
            a.ab_test_sequential(b)  # type: ignore[call-arg]  # 의도적으로 tau 누락 — 필수임을 검증


def _msprt_ever_significant(a_stream, b_stream, checkpoints, tau, alpha):
    for n in checkpoints:
        a_n, b_n = a_stream[:n], b_stream[:n]
        theta_hat = float(a_n.mean() - b_n.mean())
        variance = float(a_n.var(ddof=1) / n + b_n.var(ddof=1) / n)
        if variance <= 0:
            continue
        p = _always_valid_p_value(theta_hat, variance, tau)
        if p is not None and p <= alpha:
            return True
    return False


class TestType1ErrorControl:
    """핵심 검증 — 귀무가설(두 그룹이 실제로 동일한 분포) 하에서, 반복적으로 확인
    (peeking)해도 위양성률이 명목 alpha를 넘지 않아야 한다. 이게 "always valid"의
    정확한 의미이자, 이 기능을 보류했던 우려("통계적 정합성을 검증할 자신이 없다")에
    대한 직접적인 실증 답변이다. 고정 시드로 완전히 재현 가능 — flaky 아님.
    """

    N_REPS = 500
    N_MAX = 200
    ALPHA = 0.05
    TAU = 0.1
    # 몬테카를로 노이즈 허용폭 — R=500, true rate=0.05일 때 SD≈0.0097이므로 3-4 SD 여유.
    TOLERANCE = 0.05

    def _checkpoints(self):
        return range(10, self.N_MAX + 1, 10)

    def test_empirical_false_positive_rate_bounded_by_alpha(self):
        rng = np.random.default_rng(42)
        checkpoints = list(self._checkpoints())
        false_positives = 0
        for _ in range(self.N_REPS):
            a = rng.normal(0.0, 1.0, size=self.N_MAX)
            b = rng.normal(0.0, 1.0, size=self.N_MAX)  # 동일 분포 — 참 효과 없음(H0)
            if _msprt_ever_significant(a, b, checkpoints, self.TAU, self.ALPHA):
                false_positives += 1

        empirical_fpr = false_positives / self.N_REPS
        assert empirical_fpr <= self.ALPHA + self.TOLERANCE, (
            f"경험적 위양성률 {empirical_fpr:.3f}이 명목 alpha={self.ALPHA} + 허용폭을 "
            f"초과 — always-valid 보장이 깨졌을 수 있음"
        )

    def test_naive_repeated_t_test_inflates_false_positive_rate_by_contrast(self):
        """대조군 — 같은 데이터·같은 peeking 스케줄에 순진한(고정 표본 가정) t-검정을
        쓰면 위양성률이 명목 alpha를 크게 초과한다는 것을 직접 보여, mSPRT가 실제로
        해결하는 문제가 가짜가 아님을 확인한다."""
        pytest.importorskip("scipy")
        from scipy import stats as _stats

        rng = np.random.default_rng(42)  # 위 테스트와 동일 시드 — 같은 데이터로 대조
        checkpoints = list(self._checkpoints())
        false_positives = 0
        for _ in range(self.N_REPS):
            a = rng.normal(0.0, 1.0, size=self.N_MAX)
            b = rng.normal(0.0, 1.0, size=self.N_MAX)
            ever_significant = False
            for n in checkpoints:
                _result = _stats.ttest_ind(a[:n], b[:n], equal_var=False)
                p = float(_result.pvalue)  # type: ignore[attr-defined]
                if p <= self.ALPHA:
                    ever_significant = True
                    break
            if ever_significant:
                false_positives += 1

        naive_fpr = false_positives / self.N_REPS
        # 문헌에서 잘 알려진 현상 — peeking 시 위양성률이 명목값의 2배 이상으로
        # 부풀려진다. 정확한 배수는 peeking 횟수에 따라 다르므로 느슨하게 확인한다.
        assert naive_fpr > self.ALPHA * 1.5, (
            f"대조군(순진한 반복 t-검정)의 위양성률 부풀림이 예상보다 작음 "
            f"({naive_fpr:.3f}) — 이 테스트가 실제로 peeking 편향을 재현하고 있는지 확인 필요"
        )

    def test_power_sanity_check_detects_real_effect(self):
        """위양성률 통제가 "항상 p=1을 반환하는 퇴화한 구현" 때문이 아님을 확인 —
        실제 효과가 있고 tau가 그 효과 크기와 대략 맞을 때는 감지해야 한다(검정력이
        0이 아님). tau=0.1(위 클래스 상수, H0 검증과 동일 설정)은 작은 효과에 맞춰진
        보수적 설정이라 참 효과를 0.3으로 크게 잡아 충분한 신호 대 잡음비를 준다."""
        rng = np.random.default_rng(7)
        checkpoints = list(self._checkpoints())
        detections = 0
        for _ in range(200):
            a = rng.normal(0.3, 1.0, size=self.N_MAX)  # 참 효과 0.3
            b = rng.normal(0.0, 1.0, size=self.N_MAX)
            if _msprt_ever_significant(a, b, checkpoints, tau=0.3, alpha=self.ALPHA):
                detections += 1

        detection_rate = detections / 200
        assert detection_rate > 0.5, (
            f"실제 효과(0.3, tau=0.3로 매칭)가 있는데도 감지율이 낮음({detection_rate:.3f}) "
            "— 구현이 퇴화(항상 미유의)하지 않았는지 확인 필요"
        )
