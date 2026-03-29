"""ConversationSession, ConversationMetrics, ConversationTurn 테스트."""
import pytest
from agent_evaluator import ConversationSession, ConversationMetrics, ConversationTurn
from agent_evaluator.exceptions import InvalidOperationError


class TestConversationSessionCreation:
    """ConversationSession 생성 테스트."""

    def test_create_session(self):
        session = ConversationSession("sess_001")
        assert session.session_id == "sess_001"

    def test_initial_turns_empty(self):
        session = ConversationSession("sess_002")
        assert session.turns == []

    def test_initial_metrics_none(self):
        session = ConversationSession("sess_003")
        assert session.metrics is None


class TestConversationSessionAddTurn:
    """add_turn() / turn() 테스트."""

    def test_add_turn(self):
        session = ConversationSession("s1")
        session.add_turn(user="안녕하세요", agent="반갑습니다")
        assert len(session.turns) == 1

    def test_add_turn_content(self):
        session = ConversationSession("s2")
        session.add_turn(user="질문", agent="응답")
        turn = session.turns[0]
        assert turn.user == "질문"
        assert turn.agent == "응답"

    def test_add_turn_index(self):
        session = ConversationSession("s3")
        session.add_turn(user="u1", agent="a1")
        session.add_turn(user="u2", agent="a2")
        assert session.turns[0].turn_index == 0
        assert session.turns[1].turn_index == 1

    def test_turn_alias(self):
        """turn()은 add_turn()의 별칭이어야 함."""
        session = ConversationSession("s4")
        session.turn(user="hello", agent="world")
        assert len(session.turns) == 1

    def test_method_chaining(self):
        """add_turn()은 self를 반환하여 체이닝 가능."""
        session = ConversationSession("s5")
        result = session.add_turn(user="u", agent="a")
        assert result is session

    def test_turn_metadata(self):
        session = ConversationSession("s6")
        session.add_turn(user="q", agent="a", metadata={"latency": 1.5})
        assert session.turns[0].metadata["latency"] == 1.5

    def test_turn_timestamp_set(self):
        from datetime import datetime
        session = ConversationSession("s7")
        session.add_turn(user="q", agent="a")
        assert isinstance(session.turns[0].timestamp, datetime)


class TestConversationMetricsComputation:
    """compute_metrics() 테스트."""

    def test_compute_metrics_raises_on_empty(self):
        """턴이 없으면 InvalidOperationError 발생."""
        session = ConversationSession("empty")
        with pytest.raises(InvalidOperationError):
            session.compute_metrics()

    def test_compute_metrics_returns_conversation_metrics(self):
        session = ConversationSession("m1")
        session.add_turn(user="What is Python?", agent="Python is a programming language.")
        metrics = session.compute_metrics()
        assert isinstance(metrics, ConversationMetrics)

    def test_compute_metrics_stores_in_session(self):
        session = ConversationSession("m2")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        assert session.metrics is metrics

    def test_turn_count_single(self):
        session = ConversationSession("m3")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        assert metrics.turn_count == 1

    def test_turn_count_multiple(self):
        session = ConversationSession("m4")
        for i in range(5):
            session.add_turn(user=f"Q{i}", agent=f"A{i}")
        metrics = session.compute_metrics()
        assert metrics.turn_count == 5

    def test_session_id_in_metrics(self):
        session = ConversationSession("my_session")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        assert metrics.session_id == "my_session"

    def test_metrics_scores_in_range(self):
        """모든 점수가 0.0~1.0 범위 내."""
        session = ConversationSession("m5")
        session.add_turn(user="What is AI?", agent="AI stands for artificial intelligence.")
        session.add_turn(user="Tell me more.", agent="AI involves machine learning and neural networks.")
        metrics = session.compute_metrics()
        for score in [
            metrics.context_retention,
            metrics.topic_coherence,
            metrics.progressive_depth,
            metrics.session_completion,
            metrics.overall_score,
        ]:
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    def test_overall_score_is_average(self):
        """overall_score는 4개 지표의 평균."""
        session = ConversationSession("m6")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        expected = (
            metrics.context_retention
            + metrics.topic_coherence
            + metrics.progressive_depth
            + metrics.session_completion
        ) / 4.0
        assert abs(metrics.overall_score - expected) < 1e-5

    def test_avg_turn_latency_none_when_no_metadata(self):
        """latency metadata 없으면 avg_turn_latency=None."""
        session = ConversationSession("m7")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        assert metrics.avg_turn_latency is None

    def test_avg_turn_latency_computed(self):
        """latency metadata 있으면 평균 계산."""
        session = ConversationSession("m8")
        session.add_turn(user="Q1", agent="A1", metadata={"latency": 1.0})
        session.add_turn(user="Q2", agent="A2", metadata={"latency": 3.0})
        metrics = session.compute_metrics()
        assert metrics.avg_turn_latency == pytest.approx(2.0)

    def test_computed_at_is_string(self):
        session = ConversationSession("m9")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        assert isinstance(metrics.computed_at, str)


class TestConversationMetricsToDict:
    """ConversationMetrics.to_dict() 테스트."""

    def test_to_dict_returns_dict(self):
        session = ConversationSession("d1")
        session.add_turn(user="Q", agent="A")
        metrics = session.compute_metrics()
        d = metrics.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_session_id(self):
        session = ConversationSession("d2")
        session.add_turn(user="Q", agent="A")
        d = session.compute_metrics().to_dict()
        assert d["session_id"] == "d2"

    def test_to_dict_has_turn_count(self):
        session = ConversationSession("d3")
        session.add_turn(user="Q", agent="A")
        d = session.compute_metrics().to_dict()
        assert d["turn_count"] == 1


class TestConversationSessionContextManager:
    """with ConversationSession() as conv 테스트."""

    def test_context_manager_computes_metrics(self):
        session = ConversationSession("cm1")
        with session as conv:
            conv.add_turn(user="Q", agent="A")
        assert session.metrics is not None

    def test_context_manager_no_turns_no_metrics(self):
        """턴이 없으면 metrics는 None 유지 (ValueError 발생 안 함)."""
        session = ConversationSession("cm2")
        with session:
            pass  # 턴 없음
        assert session.metrics is None

    def test_context_manager_with_monitor(self):
        """monitor 연결 시 conversation_sessions에 추가됨."""
        from agent_evaluator import PerformanceMonitor
        monitor = PerformanceMonitor()
        session = ConversationSession("cm3", monitor=monitor)
        with session as conv:
            conv.add_turn(user="Q", agent="A")
        assert any(s.session_id == "cm3" for s in monitor.conversation_sessions)


class TestConversationSessionToDict:
    """ConversationSession.to_dict() 테스트."""

    def test_to_dict_returns_dict(self):
        session = ConversationSession("td1")
        session.add_turn(user="Q", agent="A")
        d = session.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_session_id(self):
        session = ConversationSession("td2")
        d = session.to_dict()
        assert d["session_id"] == "td2"

    def test_to_dict_turns_present(self):
        session = ConversationSession("td3")
        session.add_turn(user="Q", agent="A")
        d = session.to_dict()
        assert len(d["turns"]) == 1

    def test_to_dict_metrics_none_before_compute(self):
        session = ConversationSession("td4")
        session.add_turn(user="Q", agent="A")
        d = session.to_dict()
        assert d["metrics"] is None

    def test_to_dict_metrics_present_after_compute(self):
        session = ConversationSession("td5")
        session.add_turn(user="Q", agent="A")
        session.compute_metrics()
        d = session.to_dict()
        assert d["metrics"] is not None
