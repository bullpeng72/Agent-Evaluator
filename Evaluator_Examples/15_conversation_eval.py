"""
멀티턴 대화 평가 예제 — Agent Evaluator v0.7.3
=================================================

@conversation_eval 데코레이터로 ConversationSession API를 대체합니다.
함수에 decorator를 붙이면 session_id 기반으로 턴이 자동 누적되고,
max_turns 도달 또는 flush_conversation() 호출 시 지표가 자동 계산됩니다.

【변경 이력】
  v0.7.3: ConversationSession + monitor.conversation() 수동 패턴
          → @conversation_eval 데코레이터로 전면 교체
  v0.6.7: Phase 1-C 초기 구현

커버 지표:
  context_retention   — 맥락 유지율
  topic_coherence     — 주제 일관성
  progressive_depth   — 점진적 심화
  session_completion  — 세션 완결성
  overall_score       — 종합 점수
  avg_turn_latency    — 평균 응답 지연

핵심 시나리오:
  1. Python 학습 세션 — 기초 → 심화 (맥락 유지 우수, 4턴)
  2. 여행 계획 세션  — 일관된 주제 유지 (6턴)
  3. 요리 레시피 세션 — 단계별 질문 (5턴)
  4. 기술 지원 세션  — 문제 해결 흐름 (3턴)
  5. 맥락 단절 세션  — 갑작스러운 주제 전환 (낮은 맥락 유지율, 4턴)
  6. ML/DL 비교 세션 — 기술 심층 질문 (3턴)

실행:
    python 15_conversation_eval.py    # API 키 불필요 — 순수 시뮬레이션

대시보드 확인:
    agent-eval dashboard
    → "💬 멀티턴 대화" 탭 → 세션 목록 → 세션 클릭 → 턴별 상세
"""

from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import PerformanceMonitor, conversation_eval, flush_conversation


def _try_setup_otel(service_name: str) -> None:
    """Phoenix가 실행 중이면 OTEL 활성화 (선택적). 미실행 시 무시."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.settimeout(1)
        if _s.connect_ex(("localhost", 6006)) != 0:
            return
    try:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name=service_name)
        print(f"  📡  Phoenix 모니터링 활성화 — http://localhost:6006  (service: {service_name})")
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).debug("setup_otel 실패: %s", _e)

_try_setup_otel("15-conversation-eval")


# ─── 시뮬레이션 세션 데이터 ───────────────────────────────────────────────────
# (user_message, agent_response, latency_factor)

SESSION_PYTHON = [
    ("Python 리스트와 튜플의 차이가 뭔가요?",
     "리스트는 변경 가능(mutable)하고 튜플은 불변(immutable)입니다. "
     "리스트는 []로, 튜플은 ()로 생성하며, 튜플은 딕셔너리 키로 사용할 수 있습니다.",
     0.65),
    ("그럼 튜플을 언제 쓰는 게 좋을까요?",
     "좌표나 RGB 색상처럼 변경되면 안 되는 데이터, 또는 딕셔너리 키로 쓸 때 "
     "튜플을 사용합니다. 성능도 리스트보다 약간 빠릅니다.",
     0.72),
    ("방금 설명한 불변성을 활용한 실제 코드 예시 보여주세요.",
     "point = (3, 4)  # 좌표 — 변경 불필요\n"
     "color_map = {(255, 0, 0): 'red', (0, 255, 0): 'green'}  # 튜플을 키로 사용\n"
     "x, y = point  # 언패킹도 가능합니다.",
     0.58),
    ("언패킹을 더 활용하면 어떤 패턴이 있나요?",
     "a, *b = [1, 2, 3, 4]  # a=1, b=[2,3,4] — 별표 언패킹\n"
     "first, *middle, last = range(5)  # 앞뒤 분리\n"
     "for i, v in enumerate(items):  # 인덱스+값 동시 언패킹",
     0.61),
]

SESSION_TRAVEL = [
    ("서울 여행 3박 4일 일정을 짜주세요.",
     "1일차: 경복궁·북촌한옥마을 / 2일차: 홍대·신촌 문화 체험 / "
     "3일차: 인사동·광장시장 / 4일차: 남산타워·이태원 쇼핑 일정을 추천합니다.",
     0.55),
    ("경복궁 관람 팁이 있나요?",
     "수문장 교대식은 매일 10시와 14시에 진행됩니다. 한복 착용 시 무료 입장이며 "
     "궁중문화축전 기간에는 야간 개장도 운영합니다.",
     0.70),
    ("한복 대여는 경복궁 근처에서 할 수 있나요?",
     "네, 경복궁 동문(건춘문) 주변에 한복 대여점이 밀집해 있습니다. "
     "2~3만원 수준이며 하루 종일 착용 가능합니다. 북촌까지 걸어서 이동도 좋습니다.",
     0.68),
    ("북촌한옥마을에서 주의할 점은?",
     "주거 지역이므로 소음 자제가 필요합니다. 사진 촬영 시 창문·마당 촬영은 삼가고 "
     "주민 생활에 방해되지 않도록 주의하세요. 오전 10시 이후 방문을 권장합니다.",
     0.62),
    ("서울 여행에서 교통카드가 필요한가요?",
     "T-money나 외국인용 WOWPASS 카드를 추천합니다. 지하철·버스 모두 사용 가능하며 "
     "공항철도도 이용할 수 있습니다. 인천공항 1층 편의점에서 바로 구매 가능합니다.",
     0.50),
    ("첫째 날 경복궁 방문 후 저녁 식사 추천해주세요.",
     "경복궁 인근 통인시장에서 엽전 도시락 체험이 인기입니다. "
     "저녁은 서촌의 한정식 레스토랑이나 광화문 근처 청진동 해장국 거리도 좋습니다.",
     0.65),
]

SESSION_COOKING = [
    ("된장찌개 만드는 법 알려주세요.",
     "기본 재료: 된장 2큰술, 두부, 애호박, 양파, 버섯, 다시마 육수 3컵. "
     "육수를 끓인 후 된장을 풀고 채소를 넣어 10분 끓이면 완성입니다.",
     0.60),
    ("다시마 육수 만드는 방법도 알려주세요.",
     "물 4컵에 다시마 10g을 넣고 약불로 15분 우려냅니다. "
     "끓이지 않고 우려야 깔끔한 맛이 납니다. 멸치를 함께 넣으면 더 깊은 맛이 납니다.",
     0.72),
    ("아까 된장 2큰술이라고 하셨는데 너무 짜지 않나요?",
     "개인 취향에 따라 1.5큰술부터 시작해서 간을 맞추는 것이 좋습니다. "
     "된장마다 염도가 다르므로, 끓이면서 맛을 보며 조절하세요.",
     0.78),
    ("두부는 어떤 종류를 쓰는 게 좋나요?",
     "찌개용 두부(단단한 두부)를 사용하면 으깨지지 않습니다. "
     "부드러운 순두부를 쓰면 더 고소하지만 젓가락으로 집기 어려울 수 있습니다.",
     0.65),
    ("처음 만들기 좋은 된장찌개 레시피 핵심만 정리해주세요.",
     "핵심 3단계: ① 멸치·다시마 육수 끓이기 → ② 된장 1.5큰술 풀기 → "
     "③ 두부·애호박·양파 넣고 10분. 처음엔 재료 2~3가지로 심플하게 시작하세요.",
     0.70),
]

SESSION_SUPPORT = [
    ("파이썬 패키지 설치가 안 됩니다. pip install 하면 오류가 나요.",
     "어떤 오류 메시지가 나오나요? 주요 원인은 ① 네트워크 문제 ② 권한 문제 "
     "③ Python 버전 불일치입니다. 오류 메시지를 공유해주시면 더 정확히 도움드릴게요.",
     0.58),
    ("'Permission denied' 오류가 납니다.",
     "pip install --user 패키지명 으로 설치하거나, "
     "가상환경(venv)을 사용하세요: python -m venv venv → source venv/bin/activate (Mac/Linux) "
     "또는 venv\\Scripts\\activate (Windows) 후 pip install 하시면 됩니다.",
     0.75),
    ("가상환경으로 해결됐습니다. 감사합니다!",
     "잘 해결되셨군요! 앞으로는 프로젝트마다 가상환경을 만들어 사용하면 "
     "패키지 충돌을 방지할 수 있습니다. requirements.txt로 환경을 공유하는 것도 유용합니다.",
     0.82),
]

SESSION_CONTEXT_BREAK = [
    ("오늘 날씨 어때요?",
     "죄송합니다만 저는 실시간 날씨 정보에 접근할 수 없습니다. "
     "기상청 앱이나 네이버 날씨를 확인해주세요.",
     0.55),
    ("양자컴퓨터의 원리를 설명해주세요.",
     "양자컴퓨터는 큐비트(qubit)를 사용합니다. 고전 비트가 0 또는 1인 반면 "
     "큐비트는 중첩(superposition) 상태로 0과 1을 동시에 표현합니다. "
     "얽힘(entanglement)과 간섭(interference)을 활용해 특정 문제를 지수적으로 빠르게 풉니다.",
     0.48),
    ("아이돌 그룹 추천해주세요.",
     "K-pop에서는 BTS, BLACKPINK, aespa 등이 글로벌 인기를 얻고 있습니다. "
     "장르 취향에 따라 댄스 중심이면 에스파, 보컬 중심이면 아이유를 추천합니다.",
     0.40),
    ("고려시대 무신정변에 대해 알려주세요.",
     "1170년(의종 24년) 정중부·이의방이 주도한 무신 쿠데타입니다. "
     "문신 중심 정치에 불만을 품은 무신들이 반란을 일으켜 의종을 폐위하고 "
     "이후 100년간 무신 집권기가 시작되었습니다.",
     0.42),
]

SESSION_ML_DL = [
    ("머신러닝과 딥러닝의 차이점이 뭔가요?",
     "머신러닝은 데이터에서 패턴을 학습하는 포괄적 방법론이며, "
     "딥러닝은 머신러닝의 하위 분야로 다층 신경망을 사용합니다.",
     0.42),
    ("딥러닝이 더 좋은 건가요?",
     "딥러닝은 이미지·음성 등 비정형 데이터에서 강점을 보이지만 "
     "대량의 데이터와 연산이 필요합니다. 전통 머신러닝은 소규모 데이터나 "
     "해석 가능성이 중요한 경우에 여전히 유효합니다.",
     0.55),
    ("어떤 경우에 어떤 걸 선택해야 하나요?",
     "이미지 분류·자연어 처리 → 딥러닝, "
     "의료 진단·금융 모델(해석 필요) → 전통 ML(랜덤포레스트, XGBoost), "
     "데이터 1000건 이하 → 전통 ML이 대체로 더 좋은 성능을 냅니다.",
     0.61),
]


# ─── 세션 응답 테이블 ─────────────────────────────────────────────────────────
# session_id → {질문: (응답, latency_factor)} 매핑
_SESSION_RESPONSES: dict[str, dict[str, tuple]] = {}
_rng = random.Random(20250405)

def _build_response_table() -> None:
    """세션별 응답 조회 테이블 구성."""
    mapping = {
        "python_tutorial_001":  SESSION_PYTHON,
        "travel_seoul_002":     SESSION_TRAVEL,
        "cooking_doenjang_003": SESSION_COOKING,
        "tech_support_004":     SESSION_SUPPORT,
        "context_break_005":    SESSION_CONTEXT_BREAK,
        "ml_dl_compare_006":    SESSION_ML_DL,
    }
    for sid, turns in mapping.items():
        _SESSION_RESPONSES[sid] = {
            user_msg: (agent_msg, lat) for user_msg, agent_msg, lat in turns
        }

_build_response_table()


# ─── 모니터 및 결과 경로 설정 ─────────────────────────────────────────────────
results_dir = project_root / "results"
results_dir.mkdir(exist_ok=True)

monitor = PerformanceMonitor(output_dir=str(results_dir))

# 세션 완료 통계 수집용
_session_summaries: list[tuple] = []   # (session_id, label, expected, metrics)


# ─── @conversation_eval 데코레이터 적용 ───────────────────────────────────────
#
# 【Before — 수동 패턴】
#   with monitor.conversation(session_id) as conv:
#       for user, agent, lat in turns:
#           conv.turn(user=user, agent=agent, metadata={"latency": lat})
#
# 【After — 데코레이터 패턴】
#   @conversation_eval(monitor, session_id_arg="session_id", max_turns=8, ...)
#   def chat(question, session_id="default"): return response
#   → 동일 session_id로 반복 호출하면 턴이 자동 누적됨
#   → max_turns 도달 또는 flush_conversation() 호출 시 지표 자동 계산·기록

def _on_flush(metrics, sid: str) -> None:
    """세션 완료 시 콜백: 통계 수집 + 콘솔 출력."""
    label_map = {
        "python_tutorial_001":  ("Python 학습",    "medium"),
        "travel_seoul_002":     ("서울 여행 계획",  "high"),
        "cooking_doenjang_003": ("된장찌개 레시피", "high"),
        "tech_support_004":     ("기술 지원",       "high"),
        "context_break_005":    ("맥락 단절 패턴",  "low"),
        "ml_dl_compare_006":    ("ML vs DL 비교",   "high"),
    }
    label, expected = label_map.get(sid, (sid, "unknown"))
    _session_summaries.append((sid, label, expected, metrics))
    print(f"  📝 [{label}]  session_id={sid}")
    print(f"     turns={metrics.turn_count}  "
          f"overall={metrics.overall_score:.3f}  "
          f"context={metrics.context_retention:.3f}  "
          f"coherence={metrics.topic_coherence:.3f}  "
          f"progression={metrics.progressive_depth:.3f}  "
          f"completion={metrics.session_completion:.3f}")
    if metrics.avg_turn_latency and metrics.avg_turn_latency > 0:
        print(f"     avg_latency={metrics.avg_turn_latency:.3f}s")
    print()


def _on_turn(sid: str, user: str, response: str, metadata: dict) -> None:
    """매 턴 직후 콜백: 실시간 진행 확인용."""
    turn_n = metadata.get("turn_index", "?")
    # 필요 시 실시간 알림·로깅에 활용
    _ = (sid, user[:20], turn_n)


@conversation_eval(
    monitor,
    session_id_arg="session_id",
    max_turns=8,                     # 최대 턴 수 초과 시 자동 flush
    flush_every=6,                   # 6세션마다 save_to_file() 자동 실행
    flush_filename="15_conversation_eval",
    on_flush=_on_flush,              # 세션 종료 시 지표 출력 콜백
    on_turn=_on_turn,                # 매 턴 직후 콜백
)
def chat_agent(question: str, session_id: str = "default") -> str:
    """시뮬레이션 챗봇 에이전트.

    실제 프로젝트에서는 이 함수 안에 LLM 호출 코드를 작성합니다.
    이 예제는 미리 정의된 응답 테이블에서 값을 반환합니다.
    """
    session_data = _SESSION_RESPONSES.get(session_id, {})
    if question in session_data:
        agent_msg, lat_factor = session_data[question]
        return agent_msg
    return f"[{session_id}] '{question[:30]}...' 에 대한 답변입니다."


# ─── 메인 평가 실행 ───────────────────────────────────────────────────────────

def run_conversation_evaluation() -> str:
    print("\n" + "=" * 70)
    print("  멀티턴 대화 평가 — Agent Evaluator v0.7.3")
    print("  @conversation_eval 데코레이터 패턴")
    print("=" * 70)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"[CV]_conversation_eval_{ts}"
    print(f"\n  저장 경로: results/{filename}.json")
    print(f"  대시보드 '💬 멀티턴 대화' 탭에서 결과를 확인하세요.\n")

    # ── 세션 정의: (session_id, turns_data) ──────────────────────────────────
    sessions = [
        ("python_tutorial_001",  SESSION_PYTHON),
        ("travel_seoul_002",     SESSION_TRAVEL),
        ("cooking_doenjang_003", SESSION_COOKING),
        ("tech_support_004",     SESSION_SUPPORT),
        ("context_break_005",    SESSION_CONTEXT_BREAK),
        ("ml_dl_compare_006",    SESSION_ML_DL),
    ]

    # ── 세션별 턴 호출 ────────────────────────────────────────────────────────
    # @conversation_eval 이 session_id 별로 턴을 자동 누적한다.
    # max_turns 도달 전에는 flush_conversation(session_id) 로 수동 종료한다.
    for session_id, turns_data in sessions:
        for user_msg, _agent_msg, _lat in turns_data:
            chat_agent(user_msg, session_id=session_id)
        # max_turns 미도달 세션 → 수동 종료 (metrics 자동 계산 + _on_flush 호출)
        flush_conversation(session_id)

    # ── 최종 저장 ─────────────────────────────────────────────────────────────
    saved_path = monitor.save_to_file(filename)
    saved_json = Path(saved_path)

    # ── 종합 분석 출력 ────────────────────────────────────────────────────────
    print(f"\n  {'═'*70}")
    print(f"  📊 세션 종합 분석")
    print(f"  {'═'*70}")
    print(f"  {'세션':<28} {'품질':<8} {'종합':>6} {'맥락':>6} {'일관':>6} {'심화':>6} {'완결':>6}")
    print(f"  {'─'*70}")

    avg_overall = 0.0
    for sid, label, expected, metrics in _session_summaries:
        o  = metrics.overall_score
        c  = metrics.context_retention
        co = metrics.topic_coherence
        p  = metrics.progressive_depth
        cp = metrics.session_completion
        grade = "✅" if o >= 0.65 else ("🟡" if o >= 0.45 else "❌")
        print(f"  {grade} {label:<26} {expected:<8} {o:>5.3f} {c:>6.3f} {co:>6.3f} {p:>6.3f} {cp:>6.3f}")
        avg_overall += o

    if _session_summaries:
        avg_overall /= len(_session_summaries)
    print(f"  {'─'*70}")
    print(f"  {'평균':>36} {avg_overall:>6.3f}")

    python_data = next((m for s, _, _, m in _session_summaries if "python" in s), None)
    break_data  = next((m for s, _, _, m in _session_summaries if "break" in s), None)
    if python_data and break_data and python_data.context_retention > break_data.context_retention:
        diff = python_data.context_retention - break_data.context_retention
        print(f"\n  💡 맥락 유지율: 학습 세션({python_data.context_retention:.3f}) > "
              f"단절 세션({break_data.context_retention:.3f}) 차이: +{diff:.3f} ✅")

    # ── 결과 파일 확인 ────────────────────────────────────────────────────────
    import json as _json
    n_conv = 0
    if saved_json.exists():
        with open(saved_json, encoding="utf-8") as _f:
            _d = _json.load(_f)
        n_conv = len(_d.get("conversation_sessions", []))

    checks = [
        ("전체 세션 수",                    f"{len(_session_summaries)}개",  len(_session_summaries) >= 6),
        ("overall_score 계산",              f"{avg_overall:.3f}",           avg_overall > 0),
        ("맥락 단절 세션 점수 낮음",         str(break_data.overall_score < 0.55 if break_data else False),
         break_data is not None and break_data.overall_score < 0.55),
        ("자동 저장 완료",                  "JSON 파일",                    saved_json.exists()),
        ("결과 파일 conversation_sessions", f"{n_conv}개",                  n_conv >= 5),
    ]

    print(f"\n  {'═'*60}")
    print(f"  {'검증 항목':<30} {'실측값':<14} 결과")
    print(f"  {'─'*60}")
    pass_cnt = 0
    for chk, actual, ok in checks:
        mark = "PASS ✅" if ok else "FAIL ❌"
        if ok:
            pass_cnt += 1
        print(f"  {chk:<30} {actual:<14} {mark}")
    print(f"  {'═'*60}")
    print(f"  합계: {pass_cnt}/{len(checks)} 통과")
    print(f"\n  📄 결과 파일: {saved_json.name}")
    print(f"  → 대시보드 '💬 멀티턴 대화' 탭에서 {n_conv}개 세션을 확인하세요.\n")
    return str(saved_json)


if __name__ == "__main__":
    run_conversation_evaluation()
