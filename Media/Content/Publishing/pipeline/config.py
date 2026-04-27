"""출판 파이프라인 설정 — Amazon KDP · 리디북스 · 부크크."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent.parent / ".env")

PIPELINE_DIR = Path(__file__).parent
PUBLISHING_DIR = PIPELINE_DIR.parent
PROJECT_ROOT = PUBLISHING_DIR.parent.parent.parent
BOOK_DIR = PROJECT_ROOT / "Media" / "Book"
OUTPUT_DIR = PUBLISHING_DIR / "output"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# 책 기본 정보
BOOK_TITLE = "AI 에이전트 Harness Engineering 실무 가이드"
BOOK_SUBTITLE = "Agent-Evaluator로 구현하는 프로덕션 AI 품질 시스템"
AUTHOR_NAME = "Sungwoo Kim"
AUTHOR_NAME_KO = "김성우"
AUTHOR_EMAIL = "sungwoo.kim@gmail.com"
PUBLISHER = "Self-Published"
LANGUAGE = "Korean"  # KDP 언어 코드
ISBN = ""  # KDP는 ISBN 없어도 출판 가능 (자동 ASIN 부여)

# ── 저자 소개 (플랫폼별) ──────────────────────────────────────────────────────
# LinkedIn: https://www.linkedin.com/in/성우-김-58448045/
# 현직: KT DS AI혁신지원센터장 / 상무 (2026.04~)

# KDP용 (영문, ~250 words)
AUTHOR_BIO_KDP = """\
Sungwoo Kim is the Head of AI Innovation Center (Executive Director) at KT DS, \
where he leads the company's enterprise-wide AI transformation strategy and \
AI-driven work environment initiatives. Over more than nine years at KT DS, he \
has served as Head of Technology Innovation and Head of Digico Development Center, \
spearheading 5G/AI new business development, MSA migration consulting, and Agile \
culture adoption across the organization. Prior to KT DS, he spent four years at \
Samsung SDS as a Principal Engineer, leading the PMO for Samsung Electronics' \
Big Data platform enhancement and delivering global retail solution consulting in \
Germany (Kaufland), the United Kingdom (Countrywide), and China (Mercedes-Benz). \
He holds a Master's degree in Artificial Intelligence from Sogang University \
(GPA 4.14/4.3, 2023), where his thesis focused on stock price prediction using \
Many-to-Many sequence modeling, and a Bachelor's degree in Electronic Engineering \
from Dankook University. A prolific internal educator, he has delivered technical \
lectures on deep learning, CNN, RNN/LSTM, and CrewAI, and has authored practical \
AI e-books used company-wide. He is the creator and maintainer of agent-evaluator, \
an open-source SDK on PyPI for evaluating AI agents in production using a 7-Gate \
Harness Engineering framework covering 58 metrics.\
"""

# 리디북스용 (~350자)
AUTHOR_BIO_RIDI = """\
김성우는 KT DS AI혁신지원센터장(상무)으로 전사 AI 혁신을 총괄하고 있다. \
KT DS에서 기술혁신단장·Digico개발센터장을 역임하며 5G·AI 신사업 개발과 \
MSA 전환을 이끌었고, 삼성SDS에서는 삼성전자 빅데이터 플랫폼 PMO 및 \
독일·영국·중국 글로벌 리테일 솔루션 컨설팅을 수행했다. \
서강대학교 정보통신대학원에서 인공지능 석사를 취득(GPA 4.14/4.3)했으며, \
딥러닝·CrewAI 사내 강의와 AI 실무 e-Book을 저술했다. \
현재 프로덕션 AI 에이전트를 7개 Gate·58개 지표로 평가하는 오픈소스 \
agent-evaluator(PyPI)를 개발·운영하고 있다.\
"""

# 부크크·교보·예스24 공용 (~230자)
AUTHOR_BIO_BOOKK = """\
김성우는 KT DS AI혁신지원센터장(상무)으로 전사 AI 혁신을 이끌고 있다. \
삼성SDS와 KT DS에서 13년간 빅데이터 플랫폼 PMO, 5G·AI 신사업 개발, \
글로벌 솔루션 컨설팅을 수행했으며, 서강대 AI 석사(GPA 4.14/4.3) 학위를 보유하고 있다. \
딥러닝·CrewAI 사내 강의와 AI 실무 e-Book을 저술했으며, \
현재 AI 에이전트 평가 오픈소스 agent-evaluator를 개발·운영 중이다.\
"""

# ── Amazon KDP 가격 설정 (USD) ───────────────────────────────────────────────
EBOOK_PRICE_USD = 9.99
PRINT_PRICE_USD = 29.99

# Amazon 카테고리 (BISAC + Amazon Browse Node)
BISAC_PRIMARY = "COM051000"   # COMPUTERS / Software Development & Engineering / General
BISAC_SECONDARY = "COM004000" # COMPUTERS / Artificial Intelligence / General

# ── 리디북스 설정 ─────────────────────────────────────────────────────────────
# 카테고리: 컴퓨터/IT > 프로그래밍 > 개발 방법론
RIDI_CATEGORY_ID = "550"       # 리디북스 카테고리 ID (프로그래밍)
RIDI_EBOOK_PRICE_KRW = 15_000  # 정가 (원)
RIDI_EBOOK_PRICE_SALE_KRW = 13_500  # 할인가 (원, 정가의 90%)
# 리디북스 로열티: 판매가의 50% (단, 리디 정산 기준)

# ── 부크크 설정 ───────────────────────────────────────────────────────────────
# 카테고리: IT/컴퓨터 > 프로그래밍/개발
BOOKK_EBOOK_PRICE_KRW = 13_000   # 전자책 정가 (원)
BOOKK_PRINT_PRICE_KRW = 22_000   # 종이책 정가 (원)
# 종이책 판형: A5 (148×210mm), 예상 쪽수 350~400p
# 부크크 로열티: 판매가의 30~40% (플랫폼별 상이)
# 부크크 유통: 교보문고 · 예스24 · 알라딘 자동 유통
BOOKK_PAPER_SIZE = "a5"         # a5 | b5 | a4
BOOKK_FONT_SIZE_PT = 10         # 본문 폰트 크기 (pt)

# 챕터 파일 순서 (EPUB 빌드용)
CHAPTER_ORDER = [
    "00_서문.md",
    "Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md",
    "Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md",
    "Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md",
    "Part_II_지표시스템/Chapter_04_GroupA_목표달성.md",
    "Part_II_지표시스템/Chapter_05_GroupB_행동무결성.md",
    "Part_II_지표시스템/Chapter_06_GroupC_신뢰성.md",
    "Part_II_지표시스템/Chapter_07_GroupD_성능계약.md",
    "Part_II_지표시스템/Chapter_08_GroupE_보안경계.md",
    "Part_II_지표시스템/Chapter_09_GroupF_다중에이전트.md",
    "Part_II_지표시스템/Chapter_10_GroupG_운영관측성.md",
    "Part_III_개발자가이드/Chapter_11_평가데이터_설계.md",
    "Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md",
    "Part_III_개발자가이드/Chapter_13_프레임워크_통합.md",
    "Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md",
    "Part_IV_QA관리자가이드/Chapter_15_대시보드_시각화.md",
    "Part_IV_QA관리자가이드/Chapter_16_알림시스템_운영.md",
    "Part_IV_QA관리자가이드/Chapter_17_주간월간_품질리뷰.md",
    "Part_V_프로덕션운영/Chapter_18_CICD_품질게이팅.md",
    "Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md",
    "Part_V_프로덕션운영/Chapter_20_프로덕션_배포전략.md",
    "Part_V_프로덕션운영/Chapter_21_종합_실무파이프라인.md",
    "Part_VI_실전이식가이드/Chapter_22_기존_프로젝트_해부.md",
    "Part_VI_실전이식가이드/Chapter_23_Gate_매핑_전략.md",
    "Part_VI_실전이식가이드/Chapter_24_첫번째_이식.md",
    "Part_VI_실전이식가이드/Chapter_25_전체_통합.md",
    "Part_VI_실전이식가이드/Chapter_26_CICD_완성.md",
    "Appendix/A_58개지표_레퍼런스.md",
    "Appendix/B_CLI_명령어_레퍼런스.md",
    "Appendix/G_AI평가_이론적기초.md",
    "Appendix/H_알고리즘_수학적_레퍼런스.md",
    "Appendix/I_지표_비교분석_선택가이드.md",
    "Appendix/J_프로덕션_실패패턴_카탈로그.md",
    "Appendix/K_적대적_강건성과_레드팀_평가.md",
    "Appendix/L_예산최적화_평가설계.md",
    "Appendix/M_프로덕션_운영_체크리스트.md",
]
