"""
멀티턴 대화 평가 예제 — Agent Evaluator v0.6.7 Phase 1-C
==========================================================

ConversationSession API를 사용하여 챗봇·대화형 에이전트의 품질을 측정합니다.
결과 파일에 conversation_sessions 키가 포함되어
대시보드 "멀티턴 대화" 탭에서 세션별 지표를 확인할 수 있습니다.

커버 기능 (Phase 1-C):
  ConversationSession    │ session.add_turn(user, agent, metadata)
                         │ session.compute_metrics() → ConversationMetrics
  monitor.conversation() │ 컨텍스트 매니저 — 세션 종료 시 자동 저장
  지표                   │ context_retention   — 맥락 유지율
                         │ topic_coherence     — 주제 일관성
                         │ progressive_depth   — 점진적 심화
                         │ session_completion  — 세션 완결성
                         │ overall_score       — 종합 점수
                         │ avg_turn_latency    — 평균 응답 지연

핵심 시나리오:
  1. Python 학습 세션 — 기초 → 심화 (맥락 유지 우수, 4턴)
  2. 여행 계획 세션  — 일관된 주제 유지 (6턴)
  3. 요리 레시피 세션 — 단계별 질문 (5턴)
  4. 기술 지원 세션  — 문제 해결 흐름 (3턴)
  5. 맥락 단절 세션  — 갑작스러운 주제 전환 (낮은 맥락 유지율, 4턴)

실행:
    python 15_conversation_eval.py    # API 키 불필요 — 순수 시뮬레이션

대시보드 확인:
    agent-eval dashboard
    → "💬 멀티턴 대화" 탭 → 세션 목록 → 세션 클릭 → 턴별 상세
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import (
    PerformanceMonitor,
    ConversationSession,
    ConversationMetrics,
    evaluation_session,
)


# ─── 시뮬레이션 세션 데이터 ───────────────────────────────────────────────────

# 세션 1: Python 학습 — 기초에서 심화로 자연스럽게 진행 (맥락 유지 우수)
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

# 세션 2: 여행 계획 — 주제 일관성 높음 (서울 여행)
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

# 세션 3: 요리 레시피 — 단계별 심화 (된장찌개)
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

# 세션 4: 기술 지원 — 문제 해결 (짧지만 완결성 높음)
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

# 세션 5: 맥락 단절 — 갑자기 주제가 바뀌는 패턴 (낮은 점수 예상)
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


def run_conversation_evaluation() -> str:
    print("\n" + "=" * 70)
    print("  멀티턴 대화 평가 — Agent Evaluator v0.6.7")
    print("  Phase 1-C: ConversationSession · monitor.conversation()")
    print("=" * 70)

    rng = random.Random(20250405)
    results_dir = project_root / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"[CV]_conversation_eval_{ts}.json"

    print(f"\n  저장 경로: results/{filename}")
    print(f"  대시보드 '💬 멀티턴 대화' 탭에서 결과를 확인하세요.\n")

    all_sessions_data = []

    with evaluation_session(filename, output_dir=str(results_dir)) as monitor:

        # ──────────────────────────────────────────────────────────────────
        # 방법 1: monitor.conversation() 컨텍스트 매니저 (권장)
        #         세션 종료 시 자동으로 monitor.conversation_sessions에 저장
        # ──────────────────────────────────────────────────────────────────
        print("  [방법 1] monitor.conversation() 컨텍스트 매니저")
        print(f"  {'─'*68}\n")

        sessions_config = [
            ("python_tutorial_001",  "Python 학습",  SESSION_PYTHON,        "medium"),
            ("travel_seoul_002",     "서울 여행 계획", SESSION_TRAVEL,        "high"),
            ("cooking_doenjang_003", "된장찌개 레시피", SESSION_COOKING,      "high"),
            ("tech_support_004",     "기술 지원",     SESSION_SUPPORT,       "high"),
            ("context_break_005",    "맥락 단절 패턴", SESSION_CONTEXT_BREAK, "low"),
        ]

        for session_id, label, turns_data, expected_quality in sessions_config:
            with monitor.conversation(session_id) as conv:
                for user_msg, agent_msg, latency_factor in turns_data:
                    latency = rng.uniform(0.3, 0.8) * latency_factor + 0.1
                    conv.turn(
                        user=user_msg,
                        agent=agent_msg,
                        metadata={
                            "latency": round(latency, 3),
                            "simulated": True,
                            "topic": label,
                        },
                    )

            # 세션 종료 → monitor.conversation_sessions에 자동 추가됨
            # 마지막으로 추가된 세션의 metrics 출력
            if monitor.conversation_sessions:
                last = monitor.conversation_sessions[-1]
                if hasattr(last, "compute_metrics"):
                    metrics = last.compute_metrics()
                    all_sessions_data.append((session_id, label, expected_quality, metrics))
                    _print_session_summary(session_id, label, metrics)

        # ──────────────────────────────────────────────────────────────────
        # 방법 2: ConversationSession 직접 사용 후 수동 추가
        # ──────────────────────────────────────────────────────────────────
        print(f"\n  [방법 2] ConversationSession 직접 생성 (고급 제어)")
        print(f"  {'─'*68}\n")

        direct_session = ConversationSession(session_id="direct_session_006")
        direct_session.add_turn(
            user="머신러닝과 딥러닝의 차이점이 뭔가요?",
            agent="머신러닝은 데이터에서 패턴을 학습하는 포괄적 방법론이며, "
                  "딥러닝은 머신러닝의 하위 분야로 다층 신경망을 사용합니다.",
            metadata={"latency": 0.42},
        )
        direct_session.add_turn(
            user="딥러닝이 더 좋은 건가요?",
            agent="딥러닝은 이미지·음성 등 비정형 데이터에서 강점을 보이지만 "
                  "대량의 데이터와 연산이 필요합니다. 전통 머신러닝은 소규모 데이터나 "
                  "해석 가능성이 중요한 경우에 여전히 유효합니다.",
            metadata={"latency": 0.55},
        )
        direct_session.add_turn(
            user="어떤 경우에 어떤 걸 선택해야 하나요?",
            agent="이미지 분류·자연어 처리 → 딥러닝, "
                  "의료 진단·금융 모델 (해석 필요) → 전통 ML (랜덤포레스트, XGBoost), "
                  "데이터 1000건 이하 → 전통 ML이 대체로 더 좋은 성능을 냅니다.",
            metadata={"latency": 0.61},
        )

        direct_metrics = direct_session.compute_metrics()
        all_sessions_data.append(("direct_session_006", "ML vs DL 비교", "high", direct_metrics))
        _print_session_summary("direct_session_006", "ML vs DL 비교", direct_metrics)

        # ConversationSession을 monitor에 수동 추가
        monitor.conversation_sessions.append(direct_session)

    # ── evaluation_session 블록 종료 → save_to_file() 자동 호출 ──────────
    # conversation_sessions가 결과 JSON에 포함됨

    # ── 종합 분석 출력 ────────────────────────────────────────────────────
    print(f"\n  {'═'*70}")
    print(f"  📊 세션 종합 분석")
    print(f"  {'═'*70}")
    print(f"  {'세션':<28} {'품질':<8} {'종합':>6} {'맥락':>6} {'일관':>6} {'심화':>6} {'완결':>6}")
    print(f"  {'─'*70}")

    for sid, label, expected, metrics in all_sessions_data:
        o = metrics.overall_score
        c = metrics.context_retention
        co = metrics.topic_coherence
        p = metrics.progressive_depth
        cp = metrics.session_completion
        grade = "✅" if o >= 0.65 else ("🟡" if o >= 0.45 else "❌")
        print(f"  {grade} {label:<26} {expected:<8} {o:>5.3f} {c:>6.3f} {co:>6.3f} {p:>6.3f} {cp:>6.3f}")

    print(f"  {'─'*70}")
    avg_overall = sum(m.overall_score for _, _, _, m in all_sessions_data) / len(all_sessions_data)
    print(f"  {'평균':>36} {avg_overall:>6.3f}")

    # ── 품질 해석 ─────────────────────────────────────────────────────────
    print(f"\n  💡 분석 결과:")
    python_data = next((m for s, _, _, m in all_sessions_data if "python" in s), None)
    break_data  = next((m for s, _, _, m in all_sessions_data if "break" in s), None)

    if python_data and break_data:
        if python_data.context_retention > break_data.context_retention:
            diff = python_data.context_retention - break_data.context_retention
            print(f"  맥락 유지율: 학습 세션({python_data.context_retention:.3f}) > "
                  f"단절 세션({break_data.context_retention:.3f}) "
                  f"차이: +{diff:.3f} ✅")

    # ── 결과 파일 확인 ────────────────────────────────────────────────────
    saved_json = results_dir / filename
    import json as _json
    n_conv = 0
    if saved_json.exists():
        with open(saved_json, encoding="utf-8") as _f:
            _d = _json.load(_f)
        n_conv = len(_d.get("conversation_sessions", []))

    checks = [
        ("전체 세션 수",                     f"{len(all_sessions_data)}개",  len(all_sessions_data) >= 6),
        ("overall_score 계산",               f"{avg_overall:.3f}",           avg_overall > 0),
        ("맥락 단절 세션 점수 낮음",          str(break_data.overall_score < 0.55 if break_data else False),
         break_data is not None and break_data.overall_score < 0.55),
        ("자동 저장 완료",                   "JSON 파일",                    saved_json.exists()),
        ("결과 파일 conversation_sessions",  f"{n_conv}개",                  n_conv >= 5),
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


def _print_session_summary(session_id: str, label: str, metrics: "ConversationMetrics") -> None:
    """세션 지표를 콘솔에 출력."""
    print(f"  📝 [{label}]  session_id={session_id}")
    print(f"     turns={metrics.turn_count}  "
          f"overall={metrics.overall_score:.3f}  "
          f"context={metrics.context_retention:.3f}  "
          f"coherence={metrics.topic_coherence:.3f}  "
          f"progression={metrics.progressive_depth:.3f}  "
          f"completion={metrics.session_completion:.3f}")
    if metrics.avg_turn_latency and metrics.avg_turn_latency > 0:
        print(f"     avg_latency={metrics.avg_turn_latency:.3f}s")
    print()


if __name__ == "__main__":
    run_conversation_evaluation()
