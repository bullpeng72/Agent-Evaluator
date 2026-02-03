"""
데이터 편집 & Test 환경 설정
================================
Golden Dataset 편집, 임계값 설정, Test 구성 관리

📋 사용 시나리오:
- Test 수행 전: Golden Dataset 생성/편집, 임계값 설정
- Test 환경 검증 및 구성 저장
- 버전 관리 및 편집 기록 확인
"""

import streamlit as st
from dashboard_data_editor import render_data_editor_tab

# 페이지 설정
st.set_page_config(
    page_title="데이터 편집 - Agent Evaluator",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 메인 콘텐츠
st.title("📝 데이터 편집 & Test 환경 관리")

# 데이터 편집 UI 렌더링
render_data_editor_tab()
