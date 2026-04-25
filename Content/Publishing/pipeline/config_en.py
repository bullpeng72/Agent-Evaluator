"""영문판 출판 파이프라인 설정 — Amazon KDP (English edition).

한국어 config.py를 기반으로 영문판에 필요한 항목만 재정의한다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent.parent / ".env")

PIPELINE_DIR = Path(__file__).parent
PUBLISHING_DIR = PIPELINE_DIR.parent
PROJECT_ROOT = PUBLISHING_DIR.parent.parent

# 영문판 소스는 Book_EN/
BOOK_DIR = PROJECT_ROOT / "Book_EN"
OUTPUT_DIR = PUBLISHING_DIR / "output_en"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── 책 기본 정보 (영문판) ─────────────────────────────────────────────────────
BOOK_TITLE = "AI Agent Harness Engineering"
BOOK_SUBTITLE = "A Practitioner's Guide to Production-Ready Evaluation"
AUTHOR_NAME = "Sungwoo Kim"
AUTHOR_NAME_KO = "김성우"
AUTHOR_EMAIL = "sungwoo.kim@gmail.com"
PUBLISHER = "Self-Published"
LANGUAGE = "English"

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

# ── Amazon KDP 가격 설정 (USD) ───────────────────────────────────────────────
EBOOK_PRICE_USD = 9.99
PRINT_PRICE_USD = 34.99  # 영문 시장 기준 약간 높게

# Amazon 카테고리 (BISAC)
BISAC_PRIMARY = "COM051000"   # COMPUTERS / Software Development & Engineering / General
BISAC_SECONDARY = "COM004000" # COMPUTERS / Artificial Intelligence / General

# ── 챕터 파일 순서 (EPUB 빌드용) ─────────────────────────────────────────────
# Book_EN/ 은 Book/ 와 동일한 하위 경로 구조를 유지한다
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
