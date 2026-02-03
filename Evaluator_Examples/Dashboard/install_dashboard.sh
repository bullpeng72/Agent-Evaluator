#!/bin/bash
# Agent Evaluator Dashboard - 설치 스크립트
# Python 3.11+

set -e  # 오류 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 헤더 출력
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}  📊 Agent Evaluator Dashboard - 설치${NC}"
echo -e "${CYAN}================================================${NC}"
echo ""

# 현재 디렉토리 확인 (Zero Configuration: 자동 경로 탐지)
CURRENT_DIR=$(pwd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR"

if [ "$CURRENT_DIR" != "$DASHBOARD_DIR" ]; then
    echo -e "${YELLOW}⚠️  Dashboard 디렉토리로 이동합니다...${NC}"
    cd "$DASHBOARD_DIR" || exit 1
    echo -e "${GREEN}✓ 디렉토리 변경 완료: $DASHBOARD_DIR${NC}"
    echo ""
fi

# Python 버전 확인
echo -e "${YELLOW}[1/6] Python 버전 확인 중...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}❌ Python 3.11 이상이 필요합니다. 현재 버전: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION 감지됨${NC}"
echo ""

# 가상환경 확인
echo -e "${YELLOW}[2/6] 가상환경 확인 중...${NC}"
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  가상환경이 활성화되지 않았습니다.${NC}"
    echo -e "${YELLOW}   가상환경을 사용하시겠습니까? (y/n)${NC}"
    read -r USE_VENV

    if [ "$USE_VENV" = "y" ] || [ "$USE_VENV" = "Y" ]; then
        # 프로젝트 루트에 가상환경이 있는지 확인
        if [ -d "../venv" ]; then
            echo -e "${BLUE}기존 가상환경 활성화 중...${NC}"
            source ../venv/bin/activate
            echo -e "${GREEN}✓ 가상환경 활성화됨${NC}"
        else
            echo -e "${YELLOW}가상환경이 없습니다. 프로젝트 루트에서 생성하세요:${NC}"
            echo -e "${YELLOW}  cd .. && python3 -m venv venv && source venv/bin/activate${NC}"
            exit 1
        fi
    fi
else
    echo -e "${GREEN}✓ 가상환경 활성화됨: $VIRTUAL_ENV${NC}"
fi
echo ""

# pip 업그레이드
echo -e "${YELLOW}[3/6] pip 업그레이드 중...${NC}"
pip install --upgrade pip setuptools wheel -q
echo -e "${GREEN}✓ pip 업그레이드 완료${NC}"
echo ""

# agent_evaluator 패키지 확인
echo -e "${YELLOW}[4/6] agent_evaluator 패키지 확인 중...${NC}"
if python -c "import agent_evaluator" 2>/dev/null; then
    EVALUATOR_VERSION=$(python -c "import agent_evaluator; print(getattr(agent_evaluator, '__version__', 'unknown'))" 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✓ agent_evaluator 패키지 감지됨 (버전: $EVALUATOR_VERSION)${NC}"
else
    echo -e "${RED}❌ agent_evaluator 패키지가 설치되지 않았습니다!${NC}"
    echo ""
    echo -e "${YELLOW}Dashboard는 agent_evaluator 패키지가 필요합니다.${NC}"
    echo -e "${YELLOW}지금 설치하시겠습니까? (y/n)${NC}"
    read -r INSTALL_EVALUATOR

    if [ "$INSTALL_EVALUATOR" = "y" ] || [ "$INSTALL_EVALUATOR" = "Y" ]; then
        echo -e "${BLUE}agent_evaluator 패키지 설치 중...${NC}"
        cd ..
        pip install -e . -q
        cd Dashboard
        echo -e "${GREEN}✓ agent_evaluator 패키지 설치 완료${NC}"
    else
        echo -e "${RED}설치를 중단합니다. agent_evaluator를 먼저 설치하세요:${NC}"
        echo -e "${RED}  cd .. && pip install -e .${NC}"
        exit 1
    fi
fi
echo ""

# Dashboard 의존성 설치
echo -e "${YELLOW}[5/6] Dashboard 의존성 설치 중...${NC}"
echo -e "${BLUE}필수 패키지: streamlit, plotly, pandas, numpy, python-dotenv${NC}"
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Dashboard 의존성 설치 완료${NC}"
echo ""

# 선택적 프레임워크 설치
echo -e "${YELLOW}[6/6] 선택적 프레임워크 설치${NC}"
echo -e "${YELLOW}추가 프레임워크를 설치하시겠습니까?${NC}"
echo "  1) 설치 안 함 (Dashboard만)"
echo "  2) AutoGen만 (Multi-agent conversations)"
echo "  3) 전체 프레임워크 (AutoGen, LangChain, LangGraph, CrewAI)"
echo "  4) 전체 + 고급 메트릭 (DeepEval, Ragas)"
echo ""
read -p "선택 (1-4): " FRAMEWORK_CHOICE

case $FRAMEWORK_CHOICE in
    1)
        echo -e "${GREEN}✓ Dashboard 기본 설치 완료${NC}"
        ;;
    2)
        echo -e "${BLUE}AutoGen 설치 중...${NC}"
        pip install "pyautogen>=0.2.0,<0.3.0" -q
        echo -e "${GREEN}✓ AutoGen 설치 완료${NC}"
        ;;
    3)
        echo -e "${BLUE}전체 프레임워크 설치 중...${NC}"
        pip install "pyautogen>=0.2.0,<0.3.0" langchain langchain-core langchain-community langgraph crewai -q
        echo -e "${GREEN}✓ 전체 프레임워크 설치 완료${NC}"
        ;;
    4)
        echo -e "${BLUE}전체 프레임워크 + 고급 메트릭 설치 중...${NC}"
        pip install "pyautogen>=0.2.0,<0.3.0" langchain langchain-core langchain-community langgraph crewai deepeval ragas -q
        echo -e "${GREEN}✓ 전체 프레임워크 + 고급 메트릭 설치 완료${NC}"
        ;;
    *)
        echo -e "${YELLOW}⚠️  기본 설치만 진행합니다${NC}"
        ;;
esac
echo ""

# 설치 확인
echo -e "${YELLOW}설치 확인 중...${NC}"
echo -e "${BLUE}설치된 주요 패키지:${NC}"

PACKAGES=("streamlit" "plotly" "pandas" "numpy" "python-dotenv")

for PACKAGE in "${PACKAGES[@]}"; do
    if pip show "$PACKAGE" &> /dev/null; then
        VERSION=$(pip show "$PACKAGE" | grep Version | awk '{print $2}')
        echo -e "  ${GREEN}✓${NC} $PACKAGE ($VERSION)"
    else
        echo -e "  ${RED}✗${NC} $PACKAGE (미설치)"
    fi
done
echo ""

# 데이터 디렉토리 확인
echo -e "${YELLOW}데이터 디렉토리 확인 중...${NC}"
if [ ! -d "data" ]; then
    echo -e "${YELLOW}⚠️  data/ 디렉토리가 없습니다. 생성합니다...${NC}"
    mkdir -p data
    echo -e "${GREEN}✓ data/ 디렉토리 생성 완료${NC}"
else
    DATA_COUNT=$(find data -name "*.json" -type f 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ data/ 디렉토리 존재 (JSON 파일: $DATA_COUNT개)${NC}"
fi
echo ""

# 완료 메시지
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  ✅ Dashboard 설치가 완료되었습니다!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# 다음 단계 안내
echo -e "${CYAN}🚀 Dashboard 실행 방법:${NC}"
echo ""
echo -e "${YELLOW}1. 평가 결과 생성 (아직 없는 경우):${NC}"
echo "   cd ../level_1_foundation"
echo "   python 01_quickstart.py"
echo ""
echo -e "${YELLOW}2. Dashboard 실행:${NC}"
echo "   cd $DASHBOARD_DIR"
echo "   streamlit run app.py"
echo ""
echo -e "${YELLOW}3. 브라우저에서 확인:${NC}"
echo "   http://localhost:8501"
echo ""

# 데이터 파일이 없는 경우 경고
if [ ! -d "data" ] || [ $(find data -name "*.json" -type f 2>/dev/null | wc -l) -eq 0 ]; then
    echo -e "${YELLOW}⚠️  현재 평가 결과 파일이 없습니다.${NC}"
    echo -e "${YELLOW}   Level 1 예제를 먼저 실행하여 데이터를 생성하세요:${NC}"
    echo -e "${YELLOW}     cd ../level_1_foundation && python 01_quickstart.py${NC}"
    echo ""
fi

# 선택적 실행
echo -e "${YELLOW}지금 Dashboard를 실행하시겠습니까? (y/n)${NC}"
read -r RUN_NOW

if [ "$RUN_NOW" = "y" ] || [ "$RUN_NOW" = "Y" ]; then
    echo -e "${BLUE}Dashboard 실행 중...${NC}"
    streamlit run app.py
else
    echo -e "${GREEN}설치가 완료되었습니다. 언제든지 실행하세요:${NC}"
    echo -e "${GREEN}  streamlit run app.py${NC}"
    echo ""
fi

echo -e "${CYAN}📖 자세한 사용법: cat DASHBOARD_SETUP.md${NC}"
echo ""
echo -e "${GREEN}Happy Visualizing! 📊${NC}"
