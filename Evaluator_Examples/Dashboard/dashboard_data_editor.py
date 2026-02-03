"""
Dashboard Data Editor UI
=========================
Streamlit 기반 데이터 편집 및 투명성 UI 컴포넌트

주요 기능:
- 인터랙티브 데이터 테이블
- 인라인 편집
- Test 과정 시각화
- 주석(Annotation) UI
- Audit Log 뷰어
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

from data_editor_manager import DataEditorManager
from agent_evaluator.utils.test_transparency_manager import (
    TestTransparencyManager,
    AnnotationType,
    TestStepStatus
)
from agent_evaluator.utils.path_helpers import (
    find_project_root,
    get_evaluation_results_dir,
    get_dashboard_dir
)


# ============================================================================
# Helper Functions
# ============================================================================

def get_data_dir():
    """Get the data directory using zero configuration"""
    project_root = find_project_root()
    dashboard_dir = get_dashboard_dir(project_root)
    return dashboard_dir / "data"

def get_dashboard_directory():
    """Get the dashboard directory using zero configuration"""
    project_root = find_project_root()
    return get_dashboard_dir(project_root)

def get_test_readiness(manager: DataEditorManager) -> Dict[str, Any]:
    """
    Test 준비 상태 체크

    Returns:
        Dict with readiness status for each component
    """
    # Golden Datasets 확인
    golden_dataset_dir = get_data_dir() / "golden_datasets"
    if golden_dataset_dir.exists():
        golden_datasets = [f.name for f in golden_dataset_dir.glob("*.json")]
    else:
        golden_datasets = []
    dataset_count = len(golden_datasets)

    # 임계값 확인
    thresholds = manager.load_thresholds()
    threshold_exists = bool(thresholds)

    # 고급 평가 설정 확인
    advanced_config = manager.load_advanced_eval_config()
    advanced_configured = advanced_config.get("metadata", {}).get("updated_by") != "System"
    deepeval_enabled = advanced_config.get("deepeval", {}).get("enabled", False)
    ragas_enabled = advanced_config.get("ragas", {}).get("enabled", False)
    langsmith_enabled = advanced_config.get("langsmith", {}).get("enabled", False)

    # Test 구성 확인
    test_configs = manager.list_test_configurations()
    has_saved_config = len(test_configs) > 0

    # 전체 상태 판단
    all_ready = dataset_count > 0 and threshold_exists
    overall_status = "ready" if all_ready else "not_ready"
    if all_ready and not has_saved_config:
        overall_status = "warning"

    return {
        "golden_datasets": {
            "status": "complete" if dataset_count > 0 else "incomplete",
            "count": dataset_count,
            "files": golden_datasets,
            "message": f"{dataset_count}개 준비됨" if dataset_count > 0 else "Dataset 추가 필요"
        },
        "thresholds": {
            "status": "complete" if threshold_exists else "incomplete",
            "preset": thresholds.get("metadata", {}).get("preset", "커스텀") if threshold_exists else "미설정",
            "data": thresholds,
            "message": "설정 완료" if threshold_exists else "임계값 설정 필요"
        },
        "advanced_eval": {
            "status": "complete" if advanced_configured else "warning",
            "deepeval_enabled": deepeval_enabled,
            "ragas_enabled": ragas_enabled,
            "langsmith_enabled": langsmith_enabled,
            "deepeval_model": advanced_config.get("deepeval", {}).get("model", "gpt-4o-mini"),
            "ragas_model": advanced_config.get("ragas", {}).get("model", "gpt-4o-mini"),
            "message": "설정 완료" if advanced_configured else "기본 설정 사용 중"
        },
        "test_config": {
            "status": "complete" if has_saved_config else "warning",
            "count": len(test_configs),
            "last_config": test_configs[0] if test_configs else None,
            "message": "저장됨" if has_saved_config else "저장 권장"
        },
        "overall": overall_status
    }


def get_status_icon(status: str) -> str:
    """상태별 아이콘 반환"""
    icons = {
        "complete": "✅",
        "incomplete": "⚠️",
        "warning": "💡",
        "ready": "🚀",
        "not_ready": "⏸️"
    }
    return icons.get(status, "")


# ============================================================================
# 데이터 편집 UI
# ============================================================================

def render_data_editor_tab():
    """데이터 편집 탭 렌더링 - Test 관리자 워크플로우 최적화"""

    # 준비 상태 확인
    manager = DataEditorManager()
    readiness = get_test_readiness(manager)

    # 탭 제목에 상태 아이콘 추가 (임계값을 첫 번째로, Golden Dataset을 두 번째로 재배치)
    tab_titles = [
        f"⚙️ 임계값 설정 {get_status_icon(readiness['thresholds']['status'])}",
        f"📄 Golden Dataset {get_status_icon(readiness['golden_datasets']['status'])}",
        "📋 Test 준비",
        "🔗 레지스트리 (모든 프로젝트)",
        "📊 이력 관리"
    ]

    sub_tab = st.tabs(tab_titles)

    with sub_tab[0]:
        render_threshold_editor()

    with sub_tab[1]:
        render_golden_dataset_editor()

    with sub_tab[2]:
        render_test_overview_tab(manager, readiness)

    with sub_tab[3]:
        render_external_data_sources_tab()

    with sub_tab[4]:
        render_history_tab()


def render_test_overview_tab(manager: DataEditorManager, readiness: Dict[str, Any]):
    """Test 준비 개요 탭 - 업무 프로세스 기반 워크플로우"""

    # 전체 상태 확인
    overall_status = readiness['overall']
    gd_ready = readiness['golden_datasets']['status'] == "complete"
    th_ready = readiness['thresholds']['status'] == "complete"

    # 상태 요약 배너
    if overall_status == "ready":
        st.success("✅ **Test 실행 준비 완료!** 모든 필수 설정이 완료되었습니다.")

        # 빠른 실행 버튼
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.metric("Golden Datasets", f"{readiness['golden_datasets']['count']}개")
        with col2:
            st.metric("Threshold 설정", readiness['thresholds']['preset'])
        with col3:
            if st.button("🚀 Test 실행", type="primary", width="stretch"):
                st.info("💡 Python 코드에서 `PerformanceMonitor.from_test_config(config_id)`로 실행하세요")
    else:
        st.warning("⚠️ **Test 준비가 완료되지 않았습니다.** 아래 단계를 완료해주세요.")

    st.markdown("---")

    # 단계별 프로세스
    st.markdown("### 📋 Test 준비 프로세스")

    # Step 1: Golden Dataset
    with st.expander("**Step 1: Golden Dataset 준비** " + ("✅ 완료" if gd_ready else "⏸️ 필요"),
                     expanded=not gd_ready):
        if gd_ready:
            st.success(f"✅ {readiness['golden_datasets']['count']}개의 Dataset이 준비되어 있습니다.")

            # Dataset 목록 표시
            st.markdown("**준비된 Datasets:**")
            for ds_file in readiness['golden_datasets']['files'][:5]:
                st.markdown(f"• `{ds_file}`")
            if readiness['golden_datasets']['count'] > 5:
                st.markdown(f"*...외 {readiness['golden_datasets']['count'] - 5}개*")

            st.info("💡 추가 Dataset이 필요하면 '📄 Golden Dataset' 탭에서 생성하세요")
        else:
            st.warning("⚠️ Golden Dataset이 필요합니다")
            st.markdown("""
            **Golden Dataset 생성 방법:**
            1. 상단의 **'📄 Golden Dataset'** 탭으로 이동
            2. **'PDF에서 생성'** 또는 **'수동 생성'** 선택
            3. QAPair 작성 및 저장
            """)

    # Step 2: Threshold 설정
    with st.expander("**Step 2: Threshold 설정** " + ("✅ 완료" if th_ready else "⏸️ 필요"),
                     expanded=not th_ready):
        if th_ready:
            st.success(f"✅ Threshold가 설정되어 있습니다 (Preset: {readiness['thresholds']['preset']})")

            # 주요 임계값 표시
            thresholds = readiness['thresholds']['data']
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Layer 1 Metrics**")
                st.markdown(f"• TCR ≥ {thresholds.get('tcr', 90)}%")
                st.markdown(f"• Accuracy ≥ {thresholds.get('accuracy', 85)}%")
                st.markdown(f"• Hallucination ≤ {thresholds.get('hallucination', 5)}%")

            with col2:
                st.markdown("**Layer 2 Metrics**")
                st.markdown(f"• Tool Selection ≥ {thresholds.get('tool_selection_accuracy', 80)}%")
                st.markdown(f"• Agent Coord ≥ {thresholds.get('agent_coordination', 7)}/10")
                st.markdown(f"• Workflow ≥ {thresholds.get('workflow_execution', 90)}%")

            with col3:
                st.markdown("**Layer 3 Metrics**")
                st.markdown(f"• Faithfulness ≥ {thresholds.get('faithfulness', 0.8)}")
                st.markdown(f"• Context Recall ≥ {thresholds.get('context_recall', 0.8)}")
                st.markdown(f"• Answer Relevancy ≥ {thresholds.get('answer_relevancy', 0.8)}")

            st.info("💡 Threshold 수정이 필요하면 '⚙️ 임계값 설정' 탭에서 변경하세요")
        else:
            st.warning("⚠️ Threshold 설정이 필요합니다")
            st.markdown("""
            **Threshold 설정 방법:**
            1. 상단의 **'⚙️ 임계값 설정'** 탭으로 이동
            2. **Preset 선택** 또는 **커스텀 설정**
            3. 저장
            """)

    # Step 3: 고급 평가 설정 (선택)
    adv_eval = readiness['advanced_eval']
    adv_configured = adv_eval['status'] == "complete"

    with st.expander("**Step 3: 고급 평가 설정** (선택사항) " + ("✅ 설정됨" if adv_configured else "💡 기본값"),
                     expanded=False):
        if any([adv_eval['deepeval_enabled'], adv_eval['ragas_enabled'], adv_eval['langsmith_enabled']]):
            st.success("✅ 고급 평가 도구가 활성화되어 있습니다")

            providers = []
            if adv_eval['deepeval_enabled']:
                providers.append(f"DeepEval ({adv_eval['deepeval_model']})")
            if adv_eval['ragas_enabled']:
                providers.append(f"Ragas ({adv_eval['ragas_model']})")
            if adv_eval['langsmith_enabled']:
                providers.append("LangSmith")

            for provider in providers:
                st.markdown(f"• {provider}")
        else:
            st.info("💡 고급 평가 도구를 사용하지 않습니다 (Layer 1 + 2만 사용)")
            st.markdown("""
            **고급 평가 도구 활성화 (선택):**
            - **DeepEval**: G-Eval, Hallucination, Toxicity, Bias 등
            - **Ragas**: RAG 시스템 전용 메트릭
            - **LangSmith**: LangChain 통합 추적

            활성화하려면 '⚙️ 임계값 설정' → '🔬 고급 평가' 탭으로 이동하세요
            """)

    st.markdown("---")

    # Test 구성 저장 및 관리
    st.markdown("### 💾 Test 구성 관리")

    tc_status = readiness['test_config']['status']
    has_saved_config = tc_status == "complete"

    if gd_ready and th_ready:
        col1, col2 = st.columns([3, 1])

        with col1:
            if has_saved_config:
                st.success(f"✅ {readiness['test_config']['message']}")
                st.info("💡 새 구성을 저장하거나 기존 구성을 불러올 수 있습니다")
            else:
                st.info("💡 현재 설정을 저장하여 나중에 재사용할 수 있습니다")

        with col2:
            if st.button("💾 구성 저장", type="primary", width="stretch"):
                st.session_state.show_save_config = True

        # 구성 저장 폼
        if st.session_state.get('show_save_config', False):
            with st.form("save_test_config_form"):
                st.markdown("#### 📝 Test 구성 저장")

                col1, col2 = st.columns(2)

                with col1:
                    config_name = st.text_input(
                        "구성 이름",
                        value=f"test_config_{datetime.now().strftime('%Y%m%d_%H%M')}",
                        help="이 Test 구성을 식별할 이름"
                    )

                    environment = st.selectbox(
                        "환경",
                        options=["development", "staging", "production"],
                        help="배포 환경 선택"
                    )

                with col2:
                    author = st.text_input(
                        "작성자",
                        value="test_manager",
                        help="구성 작성자"
                    )

                    description = st.text_input(
                        "설명 (선택)",
                        placeholder="예: 프로덕션 배포 전 회귀 테스트",
                        help="이 구성에 대한 간단한 설명"
                    )

                # Dataset 선택
                available_datasets = readiness['golden_datasets']['files']
                selected_datasets = st.multiselect(
                    "Golden Datasets 선택",
                    options=available_datasets,
                    default=available_datasets,
                    help="이 구성에 포함할 Golden Datasets"
                )

                col1, col2 = st.columns(2)

                with col1:
                    submitted = st.form_submit_button("💾 저장", type="primary", width="stretch")

                with col2:
                    cancelled = st.form_submit_button("취소", width="stretch")

                if submitted and selected_datasets:
                    try:
                        config = manager.create_test_configuration(
                            test_name=config_name,
                            golden_datasets=selected_datasets,
                            thresholds=readiness['thresholds']['data'],
                            enable_transparency=True,
                            author=author,
                            environment=environment,
                            description=description if description else None
                        )

                        st.success(f"✅ Test 구성이 저장되었습니다!")
                        st.code(f"config_id = '{config['config_id']}'", language="python")
                        st.info("💡 Python 코드에서 이 config_id로 Test를 실행할 수 있습니다")
                        st.balloons()

                        st.session_state.show_save_config = False
                        import time
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Test 환경 적용 실패: {str(e)}")


def render_history_tab():
    """통합 이력 관리 탭 - 버전 관리 + 편집 기록"""

    st.markdown("### 📊 이력 관리")

    sub_tab = st.tabs(["📚 버전 관리", "📜 편집 기록"])

    with sub_tab[0]:
        st.info("💡 이전 설정으로 돌아가고 싶으신가요?")
        render_version_manager()

    with sub_tab[1]:
        st.info("💡 누가 언제 무엇을 변경했는지 추적합니다")
        render_edit_history()


def render_test_environment_setup():
    """Test 환경 설정 UI (구버전 - 호환성 유지)"""
    st.subheader("🎯 Test 환경 설정 및 검증")

    manager = DataEditorManager()

    # 환경 검증
    st.markdown("### 📋 Test 환경 검증")

    if st.button("🔍 환경 검증 실행", type="primary"):
        validation = manager.validate_test_environment()

        if validation["valid"]:
            st.success("✅ Test 환경이 올바르게 설정되었습니다!")
        else:
            st.error("❌ Test 환경에 문제가 있습니다!")

        # 경고 표시
        if validation["warnings"]:
            st.warning("⚠️ **경고**")
            for warning in validation["warnings"]:
                st.markdown(f"- {warning}")

        # 오류 표시
        if validation["errors"]:
            st.error("🚨 **오류**")
            for error in validation["errors"]:
                st.markdown(f"- {error}")

    # 현재 환경 설정 표시
    st.markdown("---")
    st.markdown("### 📊 현재 Test 환경")

    env_config = manager.prepare_test_environment()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Golden Datasets",
            len(env_config["golden_datasets"]),
            help="사용 가능한 Golden Dataset 파일 수"
        )

    with col2:
        thresholds_set = len(env_config["thresholds"]) > 0
        st.metric(
            "임계값 설정",
            "✅ 완료" if thresholds_set else "❌ 미설정",
            help="메트릭 임계값 설정 상태"
        )

    with col3:
        last_test = env_config["last_results"] is not None
        st.metric(
            "이전 Test 결과",
            "✅ 있음" if last_test else "⚪ 없음",
            help="이전 Test 실행 결과 존재 여부"
        )

    # Golden Dataset 목록
    with st.expander("📄 Golden Dataset 목록"):
        if env_config["golden_datasets"]:
            for dataset_path in env_config["golden_datasets"]:
                st.markdown(f"- `{dataset_path}`")
        else:
            st.info("Golden Dataset이 없습니다. '📄 Golden Dataset 생성 & 편집' 탭에서 생성하세요.")

    # 임계값 표시
    with st.expander("⚙️ 현재 임계값 설정"):
        if env_config["thresholds"]:
            st.json(env_config["thresholds"])
        else:
            st.info("임계값이 설정되지 않았습니다. '⚙️ 임계값 설정' 탭에서 설정하세요.")

    # Test 구성 생성
    st.markdown("---")
    st.markdown("### 💾 Test 구성 저장")

    with st.form("test_config_form"):
        st.markdown("Test 환경을 구성으로 저장하여 나중에 재사용할 수 있습니다.")

        test_name = st.text_input(
            "Test 이름",
            value=f"Test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            help="이 Test 구성의 이름"
        )

        # Golden Dataset 선택
        golden_dataset = None
        if env_config["golden_datasets"]:
            golden_dataset = st.selectbox(
                "Golden Dataset 선택",
                ["(없음)"] + env_config["golden_datasets"]
            )
            if golden_dataset == "(없음)":
                golden_dataset = None

        enable_transparency = st.checkbox(
            "Test 투명성 추적 활성화",
            value=True,
            help="Test 수행 중 메트릭 계산 과정을 추적합니다"
        )

        editor_name = st.text_input("작성자", value="Admin")

        submitted = st.form_submit_button("💾 Test 구성 저장", type="primary")

        if submitted:
            try:
                config_id = manager.create_test_configuration(
                    test_name=test_name,
                    golden_dataset_path=golden_dataset,
                    thresholds=env_config["thresholds"],
                    enable_transparency=enable_transparency,
                    editor=editor_name
                )

                st.success(f"""
                ✅ **Test 구성 저장 완료!**
                - 구성 ID: `{config_id}`
                - Test 이름: {test_name}
                - Golden Dataset: {golden_dataset if golden_dataset else '없음'}
                - 투명성 추적: {'활성화' if enable_transparency else '비활성화'}
                """)

                st.info("""
                💡 **다음 단계**
                1. 터미널에서 Test 수행:
                   ```bash
                   python agent_evaluator.py
                   # 또는
                   python examples/hybrid_evaluation_example.py
                   ```
                2. Test 완료 후 대시보드에서 결과 확인
                """)

            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")

    # 저장된 Test 구성 목록
    st.markdown("---")
    st.markdown("### 📚 저장된 Test 구성")

    configs = manager.list_test_configurations()

    if configs:
        st.info(f"총 {len(configs)}개의 Test 구성이 저장되어 있습니다.")

        for i, config in enumerate(configs[:10]):  # 최근 10개만 표시
            with st.expander(f"📋 {config['test_name']} - {config['config_id']}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**생성일**: {config['created_at']}")
                    st.markdown(f"**작성자**: {config['created_by']}")
                    st.markdown(f"**상태**: {config['status']}")

                with col2:
                    st.markdown(f"**Golden Dataset**: {config.get('golden_dataset', '없음')}")
                    st.markdown(f"**투명성 추적**: {'✅' if config.get('enable_transparency') else '❌'}")

                if st.button(f"🔄 이 구성으로 복원", key=f"restore_config_{i}"):
                    st.info("💡 구성 복원 기능은 추후 구현 예정입니다.")
    else:
        st.info("저장된 Test 구성이 없습니다. 위에서 Test 구성을 생성하세요.")


# 기존 함수들은 그대로 유지하되, 서브탭 구조 변경
def render_data_editor_tab_old():
    """데이터 편집 탭 렌더링 (구버전 - 호환성 유지)"""
    st.header("📝 데이터 편집 & 관리")

    st.info("""
    📋 **데이터 편집 가이드**
    - **Golden Dataset**: RAG 평가용 QA 데이터셋 생성 및 편집
    - **임계값 설정**: 각 메트릭의 기준값 조정
    - **버전 관리**: 데이터 변경 이력 및 롤백

    ⚠️ **주의**: Test 결과 데이터는 평가의 신뢰성을 위해 편집이 제한됩니다.
    """)

    # 서브탭 (TaskResult 편집 제거)
    sub_tab = st.tabs([
        "Golden Dataset 생성 & 편집",
        "임계값 설정",
        "버전 관리",
        "편집 기록"
    ])

    with sub_tab[0]:
        render_golden_dataset_editor()

    with sub_tab[1]:
        render_threshold_editor()

    with sub_tab[2]:
        render_version_manager()

    with sub_tab[3]:
        render_edit_history()


# TaskResult 편집 기능 제거됨
# 사유: Test 결과 조작은 평가의 신뢰성을 해치므로 불허


def render_golden_dataset_editor():
    """Golden Dataset 생성 & 편집 UI"""
    st.subheader("🇰🇷 Golden Dataset 생성 & 편집")

    # 사용처 안내
    st.info("""
    📊 **Golden Dataset 사용 지표**

    **Layer 3: Advanced Metrics - Ragas (RAG 평가)**
    - 🎯 **Faithfulness**: 답변이 컨텍스트에 충실한지 평가 | 지표: Faithfulness (0-1)
    - 🎯 **Context Recall**: 컨텍스트가 정답을 포함하는지 평가 | 지표: Context Recall (0-1)
    - 🎯 **Context Precision**: 컨텍스트의 정확도 평가 | 지표: Context Precision (0-1)
    - 🎯 **Answer Relevancy**: 답변의 질문 관련성 평가 | 지표: Answer Relevancy (0-1)

    **Layer 2: Agentic AI Metrics (옵션)**
    - 🤖 **Tool Selection Accuracy**: expected_tools 필드 정의 시 측정 가능

    💡 Golden Dataset은 RAG 시스템과 멀티 에이전트 시스템의 품질을 객관적으로 측정하기 위한 기준 데이터입니다.
    """)

    with st.expander("📖 Golden Dataset과 지표 체계의 관계"):
        st.markdown("""
        ### Golden Dataset이 필요한 지표

        **Layer 3: Advanced Metrics - Ragas (필수)**
        - Golden Dataset의 `question`, `answer`, `context`, `ground_truth` 필드 사용
        - RAG 시스템 평가에 필수적

        **Layer 2: Agentic AI Metrics (선택)**
        - `expected_tools` 필드를 추가하면 Tool Selection Accuracy 측정 가능
        - 멀티 에이전트 시스템에서 유용

        **Layer 1: Native Metrics**
        - Golden Dataset 불필요 (TaskResult만으로 측정)

        ---

        ### Golden Dataset 구조 예시

        ```json
        {
          "qa_id": "qa_001",
          "question": "회사의 휴가 정책은?",
          "answer": "1년 근무 시 15일의 연차 휴가",
          "context": "당사의 연차 휴가 정책...",
          "ground_truth": "15일",
          "expected_tools": ["policy_search", "document_reader"]  // 옵션
        }
        ```
        """)

    # 탭으로 생성과 편집 분리
    sub_sub_tab = st.tabs(["📄 PDF에서 생성", "✏️ 기존 데이터셋 편집"])

    # ========================================================================
    # Tab 1: PDF에서 Golden Dataset 생성
    # ========================================================================
    with sub_sub_tab[0]:
        st.markdown("### 📄 PDF 문서에서 QA 쌍 자동 생성")

        st.error("""
        🚨 **메모리 부족 방지 - 필독!**

        **33페이지 PDF = 메모리 부족 발생 가능!**
        - ⚠️ 30페이지 이상 PDF는 시스템이 강제 종료될 수 있습니다
        - ✅ **안전한 시작**: 최대 청크 수 **3-5개**로 시작
        - ✅ 문제없으면 **점진적으로** 늘리기 (5 → 10 → 15)
        - ❌ **0(전체)은 작은 PDF(10페이지 이하)만!**

        💡 **권장 설정 (페이지 수별)**
        - 10페이지 이하: 최대 10-15 청크
        - 10-30페이지: 최대 5-8 청크
        - 30페이지 이상: 최대 3-5 청크 (필수!)
        """)

        st.markdown("""
        **절차:**
        1. 고객사 PDF 문서 업로드
        2. OpenAI API Key 확인 (.env에서 자동 로드 ✅)
        3. 생성 옵션 설정 (⚠️ **최대 청크 수를 작게 시작!**)
        4. QA 쌍 자동 생성
        5. 생성된 데이터 검토 및 편집
        """)

        # PDF 업로드
        uploaded_file = st.file_uploader(
            "📎 PDF 파일 업로드",
            type=['pdf'],
            help="고객사의 정책 문서, 매뉴얼, 기술 문서 등을 업로드하세요",
            key="pdf_upload"
        )

        if uploaded_file:
            st.success(f"✅ 파일 업로드: {uploaded_file.name} ({uploaded_file.size} bytes)")

            col1, col2, col3 = st.columns(3)

            with col1:
                # .env에서 API 키 로드
                env_api_key = os.getenv('OPENAI_API_KEY', '')

                if env_api_key:
                    # .env에 키가 있으면 마스킹하여 표시
                    masked_key = env_api_key[:7] + '*' * 20 + env_api_key[-4:]
                    st.text_input(
                        "🔑 OpenAI API Key",
                        value=masked_key,
                        disabled=True,
                        help="✅ .env 파일에서 자동 로드됨",
                        key="openai_api_key_display"
                    )
                    st.caption("✅ .env 파일에서 자동 로드")

                    # 다른 키 사용 옵션
                    use_custom_key = st.checkbox(
                        "다른 API 키 사용",
                        key="use_custom_api_key",
                        help="체크하면 .env 대신 다른 API 키를 입력할 수 있습니다"
                    )

                    if use_custom_key:
                        api_key = st.text_input(
                            "🔑 커스텀 API Key",
                            type="password",
                            help="QA 생성에 사용할 OpenAI API Key",
                            key="openai_api_key_custom"
                        )
                    else:
                        api_key = env_api_key
                else:
                    # .env에 키가 없으면 직접 입력
                    st.warning("⚠️ .env 파일에 OPENAI_API_KEY가 설정되지 않았습니다")
                    api_key = st.text_input(
                        "🔑 OpenAI API Key",
                        type="password",
                        help="QA 생성에 사용할 OpenAI API Key",
                        key="openai_api_key"
                    )

            with col2:
                num_questions = st.number_input(
                    "📝 청크당 질문 수",
                    min_value=1,
                    max_value=5,
                    value=2,
                    help="각 텍스트 청크에서 생성할 QA 쌍 수",
                    key="num_questions"
                )

            with col3:
                chunk_size = st.number_input(
                    "📏 청크 크기 (문자)",
                    min_value=500,
                    max_value=3000,
                    value=1000,
                    step=100,
                    help="텍스트를 나눌 청크의 크기",
                    key="chunk_size"
                )

            # 최대 청크 수 제한 (메모리 효율성)
            col4, col5 = st.columns(2)

            with col4:
                # 파일 크기 기반 권장값 계산
                file_size_mb = uploaded_file.size / (1024 * 1024)
                if file_size_mb < 1:
                    recommended_chunks = 10
                    safety_level = "안전"
                elif file_size_mb < 3:
                    recommended_chunks = 5
                    safety_level = "주의"
                else:
                    recommended_chunks = 3
                    safety_level = "위험"

                max_chunks = st.number_input(
                    f"🎯 최대 청크 수 (권장: {recommended_chunks}개)",
                    min_value=0,
                    max_value=50,
                    value=recommended_chunks,
                    help=f"파일 크기 {file_size_mb:.1f}MB - {safety_level} 수준. 작게 시작하세요!",
                    key="max_chunks"
                )

            with col5:
                # 경고 레벨에 따라 색상 변경
                if max_chunks == 0:
                    st.error(f"""
                    🚨 **위험: 전체 처리**
                    - 메모리 부족 위험 높음!
                    - 파일: {file_size_mb:.1f}MB
                    - 권장: {recommended_chunks}개로 변경
                    """)
                elif max_chunks > recommended_chunks * 2:
                    st.warning(f"""
                    ⚠️ **주의**
                    - 최대 청크 수: {max_chunks}개
                    - 예상 QA 수: ~{max_chunks * num_questions}개
                    - 권장: {recommended_chunks}개 이하
                    """)
                else:
                    st.success(f"""
                    ✅ **안전**
                    - 최대 청크 수: {max_chunks}개
                    - 예상 QA 수: ~{max_chunks * num_questions}개
                    - 메모리 최적화됨
                    """)


            dataset_id = st.text_input(
                "🏷️ Dataset ID",
                value=f"dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                help="생성될 데이터셋의 고유 ID",
                key="dataset_id"
            )

            # 최종 확인 메시지
            st.divider()
            if max_chunks == 0 or max_chunks > 10:
                st.error("""
                🚨 **최종 확인**
                - 최대 청크 수가 너무 많습니다!
                - 메모리 부족으로 시스템이 강제 종료될 수 있습니다
                - 권장: 5개 이하로 시작하세요
                """)
            else:
                st.info(f"""
                ✅ **설정 확인**
                - 파일: {uploaded_file.name} ({file_size_mb:.1f}MB)
                - 최대 청크 수: {max_chunks}개
                - 예상 QA 수: ~{max_chunks * num_questions}개
                - 안전 수준: {"✅ 안전" if max_chunks <= recommended_chunks else "⚠️ 주의"}
                """)

            if st.button("🚀 QA 쌍 생성 시작", type="primary", key="generate_qa"):
                if not api_key:
                    st.error("❌ OpenAI API Key를 입력해주세요.")
                else:
                    try:
                        from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
                        import tempfile
                        from pathlib import Path

                        # 임시 파일로 저장
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                            tmp_file.write(uploaded_file.getvalue())
                            tmp_path = tmp_file.name

                        with st.spinner("📖 PDF 읽는 중..."):
                            # chunk_size는 generator 생성 시 전달
                            # Dashboard 기준 경로 사용
                            golden_dir = str(get_data_dir() / "golden_datasets")
                            generator = KoreanRAGDatasetGenerator(
                                api_key=api_key,
                                chunk_size=chunk_size,
                                output_dir=golden_dir
                            )

                        # 최대 청크 수 설정 (0이면 None으로)
                        max_chunks_value = max_chunks if max_chunks > 0 else None

                        expected_qa = max_chunks * num_questions if max_chunks_value else "모든 청크"

                        with st.spinner(f"🤖 AI가 QA 쌍을 생성 중... (최대 ~{expected_qa}개)"):
                            # max_chunks 옵션 전달
                            dataset = generator.generate_from_pdf(
                                pdf_path=tmp_path,
                                num_questions_per_chunk=num_questions,
                                max_chunks=max_chunks_value
                            )

                        # generate_from_pdf가 자동으로 저장한 파일의 원래 dataset_id 저장
                        original_dataset_id = dataset.dataset_id

                        # Dataset ID와 source_document 업데이트
                        dataset.dataset_id = dataset_id
                        dataset.source_document = uploaded_file.name

                        # golden_datasets 디렉토리에 원하는 이름으로 저장
                        (get_data_dir() / "golden_datasets").mkdir(parents=True, exist_ok=True)
                        saved_path = generator.dataset_manager.save_dataset(
                            dataset,
                            format="json",
                            filename=f"{dataset_id}.json"
                        )

                        # generate_from_pdf가 자동 생성한 원본 파일 삭제
                        # (원래 dataset_id로 생성된 파일 찾기)
                        golden_dir = get_data_dir() / "golden_datasets"
                        for auto_file in golden_dir.glob("golden_dataset_*.json"):
                            # 파일 이름에 원래 dataset_id가 포함되어 있으면 삭제
                            if original_dataset_id in auto_file.name and auto_file.name != Path(saved_path).name:
                                try:
                                    auto_file.unlink()
                                    st.info(f"🗑️  자동 생성 파일 삭제: {auto_file.name}")
                                except Exception as e:
                                    st.warning(f"⚠️  파일 삭제 실패: {auto_file.name} - {e}")

                        # 임시 파일 삭제
                        os.unlink(tmp_path)

                        st.success(f"""
                        ✅ **Golden Dataset 생성 완료!**
                        - 📁 파일: {saved_path}
                        - 📊 QA 쌍 수: {dataset.total_qa_pairs}개
                        - 📄 원본 문서: {uploaded_file.name}

                        👉 "기존 데이터셋 편집" 탭에서 생성된 데이터를 검토하고 편집할 수 있습니다.
                        """)

                        st.balloons()

                        # 생성된 QA 미리보기
                        with st.expander("🔍 생성된 QA 쌍 미리보기"):
                            for i, qa in enumerate(dataset.qa_pairs[:5], 1):
                                st.markdown(f"""
                                **QA {i}:**
                                - **질문**: {qa.question}
                                - **답변**: {qa.answer}
                                - **Ground Truth**: {qa.ground_truth}
                                ---
                                """)

                            if len(dataset.qa_pairs) > 5:
                                st.info(f"... 외 {len(dataset.qa_pairs) - 5}개 QA 쌍")

                    except Exception as e:
                        st.error(f"❌ 생성 실패: {str(e)}")
                        import traceback
                        with st.expander("🔍 오류 상세"):
                            st.code(traceback.format_exc())

    # ========================================================================
    # Tab 2: 기존 데이터셋 편집
    # ========================================================================
    with sub_sub_tab[1]:
        st.markdown("### ✏️ 기존 Golden Dataset 편집")

        manager = DataEditorManager()
        from pathlib import Path

        golden_dir = get_data_dir() / "golden_datasets"
        if not golden_dir.exists():
            golden_dir.mkdir(parents=True, exist_ok=True)

        json_files = list(golden_dir.glob("*.json"))

        if not json_files:
            st.warning("⚠️ Golden Dataset 파일이 없습니다.")
            st.info("💡 먼저 'PDF에서 생성' 탭에서 QA 쌍을 생성하세요.")
            return

        col1, col2 = st.columns([3, 1])

        with col1:
            selected_file = st.selectbox(
                "Golden Dataset 선택",
                [str(f) for f in json_files],
                key="golden_dataset_file"
            )

        with col2:
            if st.button("🔄 새로고침", key="refresh_golden_dataset"):
                st.rerun()

        try:
            # 데이터 로드
            df = manager.load_golden_dataset(selected_file)

            st.success(f"📦 로드된 QA 쌍: {len(df)}개")

            # 검색 기능
            with st.expander("🔍 검색"):
                search_query = st.text_input("질문 또는 답변 검색", key="golden_search")

                if search_query:
                    mask = (
                        df['question'].str.contains(search_query, case=False, na=False) |
                        df['answer'].str.contains(search_query, case=False, na=False)
                    )
                    df = df[mask]
                    st.info(f"🔍 {len(df)}개 결과 발견")

            # 편집 가능한 컬럼 (Layer 2 필드 포함)
            editable_columns = [
                'qa_id', 'question', 'answer', 'ground_truth',
                'context', 'expected_tools', 'expected_agents', 'expected_workflow_steps'
            ]

            # 필요한 컬럼만 선택
            available_columns = [col for col in editable_columns if col in df.columns]
            display_df = df[available_columns].copy()

            st.markdown("---")
            st.markdown("### 📋 QA 쌍 편집")
            st.info("""
            📝 **편집 가이드**
            - ✏️ 셀을 더블클릭하여 편집할 수 있습니다
            - ➕ 하단의 "+" 버튼으로 새 행을 추가할 수 있습니다
            - ⚠️ **새 행 추가 시**: 모든 필수 필드(qa_id, question, answer, ground_truth)를 입력한 후 저장하세요
            - 💡 질문이 명확한지, 답변이 정확한지, Ground Truth가 올바른지 검토하세요
            """)

            # 데이터 편집기
            edited_df = st.data_editor(
                display_df,
                width="stretch",
                num_rows="dynamic",
                column_config={
                    "qa_id": st.column_config.TextColumn(
                        "QA ID",
                        width="small",
                        disabled=True
                    ),
                    "question": st.column_config.TextColumn(
                        "질문 (Faithfulness, Answer Relevancy에 사용)",
                        width="medium",
                        max_chars=500,
                        help="RAG 시스템에 입력될 질문"
                    ),
                    "answer": st.column_config.TextColumn(
                        "답변 (Faithfulness에 사용)",
                        width="large",
                        max_chars=1000,
                        help="기대되는 정확한 답변"
                    ),
                    "ground_truth": st.column_config.TextColumn(
                        "Ground Truth (Context Recall에 사용)",
                        width="medium",
                        max_chars=500,
                        help="질문에 대한 정답 (평가 기준)"
                    ),
                    "context": st.column_config.TextColumn(
                        "컨텍스트 (Context Precision, Faithfulness에 사용)",
                        width="large",
                        max_chars=2000,
                        help="RAG 시스템이 검색할 관련 문맥"
                    ),
                    # Layer 2: Agentic AI Metrics 필드
                    "expected_tools": st.column_config.TextColumn(
                        "Expected Tools (Layer 2 - Tool Selection)",
                        width="medium",
                        max_chars=500,
                        help="예상 도구 목록 (쉼표로 구분, 예: search,calculator,python_repl) - Tool Selection Accuracy 평가용"
                    ),
                    "expected_agents": st.column_config.TextColumn(
                        "Expected Agents (Layer 2 - Agent Coordination)",
                        width="medium",
                        max_chars=500,
                        help="예상 에이전트 목록 (쉼표로 구분, 예: researcher,writer,reviewer) - Agent Coordination 평가용"
                    ),
                    "expected_workflow_steps": st.column_config.TextColumn(
                        "Expected Workflow Steps (Layer 2 - Workflow Execution)",
                        width="medium",
                        max_chars=500,
                        help="예상 워크플로우 단계 (쉼표로 구분, 예: retrieval,generation,validation) - Workflow Execution 평가용"
                    )
                },
                hide_index=False,
                key="golden_dataset_editor"
            )

            # 저장 옵션
            st.markdown("---")
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                editor_name = st.text_input("편집자 이름", value="Admin", key="golden_editor_name")

            with col2:
                edit_reason = st.text_input("편집 이유", value="QA 품질 개선", key="golden_edit_reason")

            with col3:
                st.write("")
                st.write("")

                if st.button("💾 저장", type="primary", key="save_golden_dataset"):
                    try:
                        # Dataset ID 추출 (파일명에서)
                        dataset_id = Path(selected_file).stem

                        manager.save_golden_dataset(
                            df=edited_df,
                            filepath=selected_file,
                            dataset_id=dataset_id,
                            source_document=selected_file,
                            editor=editor_name,
                            reason=edit_reason
                        )

                        st.success("✅ Golden Dataset이 성공적으로 저장되었습니다!")
                        st.balloons()

                    except Exception as e:
                        st.error(f"❌ 저장 실패: {str(e)}")

            # 상세 보기
            with st.expander("📝 QA 쌍 상세 보기"):
                if len(edited_df) > 0:
                    def format_qa_option(i):
                        """QA 옵션 포맷 (None 안전)"""
                        qa_id = edited_df.iloc[i]['qa_id']
                        question = edited_df.iloc[i]['question']

                        # None 체크
                        qa_id_str = str(qa_id) if qa_id is not None else "(새 항목)"
                        question_str = str(question)[:50] if question is not None else "(질문 없음)"

                        return f"{qa_id_str}: {question_str}..."

                    selected_idx = st.selectbox(
                        "QA 쌍 선택",
                        range(len(edited_df)),
                        format_func=format_qa_option,
                        key="qa_detail_select"
                    )

                    qa = edited_df.iloc[selected_idx]

                    st.markdown(f"""
                    **QA ID:** `{qa['qa_id'] if qa['qa_id'] is not None else '(미설정)'}`

                    **📝 질문 (Question):**
                    > {qa['question'] if qa['question'] is not None else '(질문을 입력하세요)'}

                    **💬 답변 (Answer):**
                    > {qa['answer'] if qa['answer'] is not None else '(답변을 입력하세요)'}

                    **✅ Ground Truth:**
                    > {qa['ground_truth'] if qa['ground_truth'] is not None else '(Ground Truth를 입력하세요)'}

                    **📄 컨텍스트 (Context):**
                    ```
                    {qa['context'] if qa['context'] is not None else '(컨텍스트를 입력하세요)'}
                    ```

                    ---
                    **🎯 이 QA가 사용되는 메트릭:**
                    - Faithfulness: 답변이 컨텍스트에 충실한지
                    - Context Recall: 컨텍스트가 Ground Truth를 포함하는지
                    - Context Precision: 컨텍스트의 정확도
                    - Answer Relevancy: 답변이 질문과 관련있는지
                    """)

        except Exception as e:
            st.error(f"❌ 데이터 로드 실패: {str(e)}")
            import traceback
            with st.expander("🔍 오류 상세"):
                st.code(traceback.format_exc())


def render_threshold_editor():
    """임계값 설정 UI - 3계층 지표 체계 기반"""
    st.subheader("⚙️ 메트릭 임계값 설정")

    st.info("""
    📊 **3계층 지표 체계**

    - **Layer 1: Native Metrics** - 기본 메트릭 (8개) | API 키 불필요, 무료
    - **Layer 2: Agentic AI Metrics** - 에이전틱 AI 메트릭 (3개) | API 키 불필요, 무료
    - **Layer 3: Advanced Metrics** - 고급 메트릭 (DeepEval + Ragas) | OpenAI API 필요

    💡 각 계층은 AI Agent 성능의 다른 측면을 측정합니다.
    """)

    manager = DataEditorManager()

    # 서브탭 생성 (3계층 구조)
    sub_tab = st.tabs([
        "📊 Layer 1: Native Metrics",
        "🤖 Layer 2: Agentic AI",
        "🚀 Layer 3: Advanced Metrics"
    ])

    # ========================================================================
    # Layer 1: Native Metrics (기본 메트릭)
    # ========================================================================
    with sub_tab[0]:
        render_native_metrics_tab(manager)

    # ========================================================================
    # Layer 2: Agentic AI Metrics
    # ========================================================================
    with sub_tab[1]:
        render_agentic_metrics_tab(manager)

    # ========================================================================
    # Layer 3: Advanced Metrics (DeepEval + Ragas)
    # ========================================================================
    with sub_tab[2]:
        render_advanced_eval_tab_v2(manager)


def render_native_metrics_tab(manager: DataEditorManager):
    """Layer 1: Native Metrics (기본 메트릭 8개)"""
    st.markdown("### 📊 Layer 1: Native Metrics (기본 메트릭)")
    st.caption("💡 API 키 불필요 | 무료 | 모든 평가에서 기본 측정")

    # 임계값 로드
    thresholds = manager.load_thresholds()

    st.info("""
    **Native Metrics (8개)**
    - 🎯 **정확도 & 품질**: TCR, Accuracy, Quality, Hallucination
    - ⚡ **효율성**: Latency, Cost
    - 🔧 **도구 & 재시도**: Tool Efficiency, Retry Success Rate

    💡 이 메트릭들은 API 키 없이도 자동으로 측정됩니다.
    """)

    # ========================================================================
    # 🎯 정확도 & 품질 (4개)
    # ========================================================================
    st.markdown("## 🎯 정확도 & 품질")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📍 TCR (Task Completion Rate)")
        thresholds['tcr'] = st.slider(
            "작업 완료율 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('tcr', 90.0)),
            step=1.0,
            help="📊 **지표**: TCR (Task Completion Rate)\n완료된 작업 / 전체 작업 × 100",
            key="native_tcr"
        )

        st.markdown("### 📍 Quality Score")
        thresholds['quality'] = st.slider(
            "응답 품질 최소 목표 (1-10)",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('quality', 7.0)),
            step=0.1,
            help="📊 **지표**: Quality Score\n관련성(25%) + 완전성(25%) + 정확성(20%) + 명확성(15%) + 유용성(15%)",
            key="native_quality"
        )

    with col2:
        st.markdown("### 📍 Accuracy")
        thresholds['accuracy'] = st.slider(
            "정확도 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('accuracy', 85.0)),
            step=1.0,
            help="📊 **지표**: Accuracy\n정답과의 일치도 (사실적 정확성)",
            key="native_accuracy"
        )

        st.markdown("### 📍 Hallucination Rate")
        thresholds['hallucination'] = st.slider(
            "환각률 최대 허용치 (%)",
            min_value=0.0,
            max_value=20.0,
            value=float(thresholds.get('hallucination', 5.0)),
            step=0.5,
            help="📊 **지표**: Hallucination Rate\n환각 탐지 건수 / 검사된 응답 수 × 100 (낮을수록 좋음)",
            key="native_hallucination"
        )

    st.markdown("---")

    # ========================================================================
    # ⚡ 효율성 (2개)
    # ========================================================================
    st.markdown("## ⚡ 효율성")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📍 Latency (응답 지연시간)")
        thresholds['latency'] = st.slider(
            "응답 시간 최대 허용치 (초)",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('latency', 3.0)),
            step=0.1,
            help="📊 **지표**: Latency\n요청 → 응답 완료까지 시간 (평균)",
            key="native_latency"
        )

    with col2:
        st.markdown("### 📍 Cost per Task")
        thresholds['cost_per_task'] = st.slider(
            "작업당 비용 최대 허용치 ($)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('cost_per_task', 0.1)),
            step=0.01,
            help="📊 **지표**: Cost per Task\n(입력 토큰 비용 + 출력 토큰 비용) / 작업 수",
            key="native_cost"
        )

    st.markdown("---")

    # ========================================================================
    # 🔧 도구 & 재시도 (2개)
    # ========================================================================
    st.markdown("## 🔧 도구 & 재시도")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📍 Tool Efficiency")
        thresholds['tool_efficiency'] = st.slider(
            "도구 효율성 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('tool_efficiency', 80.0)),
            step=1.0,
            help="📊 **지표**: Tool Efficiency\n성공한 도구 호출 / 전체 도구 호출 × 100",
            key="native_tool_eff"
        )

    with col2:
        st.markdown("### 📍 Retry Success Rate")
        thresholds['retry_success_rate'] = st.slider(
            "재시도 성공률 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('retry_success_rate', 70.0)),
            step=1.0,
            help="📊 **지표**: Retry Success Rate\n재시도 후 성공한 작업 / 재시도한 작업 × 100",
            key="native_retry"
        )

    st.markdown("---")

    # 저장 버튼
    if st.button("💾 Native Metrics 임계값 저장", key="save_native_metrics", width="stretch"):
        try:
            manager.save_thresholds(
                thresholds,
                editor="dashboard_user",
                reason="Layer 1: Native Metrics 임계값 업데이트"
            )
            st.success("✅ Native Metrics 임계값이 저장되었습니다!")
            st.balloons()
        except Exception as e:
            st.error(f"❌ 저장 실패: {e}")


def render_agentic_metrics_tab(manager: DataEditorManager):
    """Layer 2: Agentic AI Metrics (에이전틱 AI 메트릭 3개)"""
    st.markdown("### 🤖 Layer 2: Agentic AI Metrics")
    st.caption("💡 API 키 불필요 | 무료 | 멀티 에이전트 시스템 전용")

    # 임계값 로드
    thresholds = manager.load_thresholds()

    st.info("""
    **Agentic AI Metrics (3개)**
    - 🎯 **Tool Selection Accuracy**: 적절한 도구 선택 정확도
    - 🤝 **Agent Coordination**: 멀티 에이전트 협업 효율성
    - 📊 **Workflow Execution**: 워크플로우 실행 성공률

    💡 이 메트릭들은 CrewAI, LangGraph 등 멀티 에이전트 시스템에서 측정됩니다.
    """)

    # ========================================================================
    # 🤖 Agentic AI Metrics
    # ========================================================================

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📍 Tool Selection Accuracy")
        thresholds['tool_selection_accuracy'] = st.slider(
            "도구 선택 정확도 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('tool_selection_accuracy', 85.0)),
            step=1.0,
            help="📊 **지표**: Tool Selection Accuracy\n올바른 도구 선택 / 전체 도구 선택 × 100\n\n**측정 방법**: Golden Dataset에 expected_tools 정의 필요",
            key="agentic_tool_selection"
        )

    with col2:
        st.markdown("### 📍 Agent Coordination Score")
        thresholds['agent_coordination'] = st.slider(
            "에이전트 협업 점수 최소 목표 (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('agent_coordination', 0.8)),
            step=0.05,
            help="📊 **지표**: Agent Coordination\n성공적인 에이전트 간 상호작용 / 전체 상호작용\n\n**포함**: 작업 위임, 정보 공유, 충돌 해결",
            key="agentic_coordination"
        )

    with col3:
        st.markdown("### 📍 Workflow Execution Rate")
        thresholds['workflow_execution'] = st.slider(
            "워크플로우 실행 성공률 최소 목표 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('workflow_execution', 90.0)),
            step=1.0,
            help="📊 **지표**: Workflow Execution Success Rate\n성공한 워크플로우 / 전체 워크플로우 × 100\n\n**적용**: LangChain, LangGraph, CrewAI 워크플로우",
            key="agentic_workflow"
        )

    st.markdown("---")

    # 추가 설명
    with st.expander("📖 Agentic AI Metrics 상세 설명"):
        st.markdown("""
        ### 🎯 Tool Selection Accuracy
        에이전트가 작업에 적합한 도구를 선택하는 능력을 측정합니다.

        **계산 방법**:
        - Golden Dataset에 `expected_tools` 필드 정의
        - 실제 사용된 도구와 비교
        - 일치율 계산

        ---

        ### 🤝 Agent Coordination Score
        멀티 에이전트 시스템에서 에이전트 간 협업 효율성을 측정합니다.

        **측정 항목**:
        - 작업 위임 성공률
        - 정보 공유 효율성
        - 충돌 해결 능력
        - 병렬 실행 효율성

        ---

        ### 📊 Workflow Execution Rate
        체인/그래프 기반 워크플로우가 완전히 실행되는 비율을 측정합니다.

        **실패 원인**:
        - 노드 실행 실패
        - 조건 분기 오류
        - 타임아웃
        - 의존성 문제
        """)

    st.markdown("---")

    # 저장 버튼
    if st.button("💾 Agentic AI Metrics 임계값 저장", key="save_agentic_metrics", width="stretch"):
        try:
            manager.save_thresholds(
                thresholds,
                editor="dashboard_user",
                reason="Layer 2: Agentic AI Metrics 임계값 업데이트"
            )
            st.success("✅ Agentic AI Metrics 임계값이 저장되었습니다!")
            st.balloons()
        except Exception as e:
            st.error(f"❌ 저장 실패: {e}")


def render_basic_metrics_tab(manager: DataEditorManager):
    """기본 메트릭 임계값 설정 (구 버전, 호환성 유지)"""
    st.markdown("### 📊 기본 메트릭 임계값")
    st.caption("💡 데이터 소스: TaskResult (평가 실행 결과)")

    # 임계값 로드
    thresholds = manager.load_thresholds()

    st.info("""
    🎯 **기본 메트릭 안내**
    - TaskResult 기반 메트릭 (TCR, Accuracy, Quality 등)
    - 실제 평가 실행 결과에서 측정
    - 알림 및 통과/실패 판정에 사용
    """)

    # 카테고리별 구분
    col1, col2 = st.columns(2)

    with col1:
        thresholds['tcr'] = st.slider(
            "TCR (Task Completion Rate) (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('tcr', 90.0)),
            step=1.0,
            help="📊 작업 완료율 최소 목표 | 데이터: TaskResult.completion_score",
            key="basic_tcr"
        )

        thresholds['accuracy'] = st.slider(
            "Accuracy (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('accuracy', 85.0)),
            step=1.0,
            help="📊 정확도 최소 목표 | 데이터: TaskResult.accuracy_score",
            key="basic_accuracy"
        )

        thresholds['hallucination'] = st.slider(
            "Hallucination Rate (%) - 최대",
            min_value=0.0,
            max_value=20.0,
            value=float(thresholds.get('hallucination', 5.0)),
            step=0.5,
            help="📊 환각 발생률 최대 허용치 | 데이터: TaskResult (오류 분석)",
            key="basic_hallucination"
        )

    with col2:
        thresholds['quality'] = st.slider(
            "Quality Score (1-10)",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('quality', 7.0)),
            step=0.1,
            help="📊 응답 품질 최소 목표 | 데이터: TaskResult.quality_score",
            key="basic_quality"
        )

        thresholds['latency'] = st.slider(
            "Latency (초) - 최대",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('latency', 3.0)),
            step=0.1,
            help="📊 응답 시간 최대 허용치 | 데이터: TaskResult.execution_time",
            key="basic_latency"
        )

        thresholds['cost_per_task'] = st.slider(
            "Cost per Task ($) - 최대",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('cost_per_task', 0.05)),
            step=0.01,
            help="📊 작업당 비용 최대 허용치 | 데이터: TaskResult.tokens_used",
            key="basic_cost"
        )

    # 저장
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        editor_name = st.text_input("편집자 이름", value="Admin", key="basic_editor_name")

    with col2:
        edit_reason = st.text_input("변경 이유", value="Basic threshold adjustment", key="basic_edit_reason")

    with col3:
        st.write("")
        st.write("")

        if st.button("💾 저장", type="primary", key="save_basic_thresholds"):
            try:
                manager.save_thresholds(
                    thresholds=thresholds,
                    editor=editor_name,
                    reason=edit_reason
                )

                st.success("✅ 기본 메트릭 임계값이 저장되었습니다!")

            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")


def render_rag_metrics_tab(manager: DataEditorManager):
    """RAG 메트릭 임계값 설정"""
    st.markdown("### 🇰🇷 RAG 메트릭 임계값")
    st.caption("💡 데이터 소스: Golden Dataset (QA 쌍)")

    # 임계값 로드
    thresholds = manager.load_thresholds()

    st.info("""
    🎯 **RAG 메트릭 안내**
    - Golden Dataset 기반 메트릭 (Faithfulness, Answer Relevancy 등)
    - QA 쌍 데이터로 측정
    - RAG 시스템 품질 평가에 사용
    """)

    # 카테고리별 구분
    col1, col2 = st.columns(2)

    with col1:
        thresholds['faithfulness'] = st.slider(
            "Faithfulness",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('faithfulness', 0.8)),
            step=0.05,
            help="🎯 답변이 컨텍스트에 충실한지 평가 | 데이터: Golden Dataset (answer, context)",
            key="rag_faithfulness"
        )

        thresholds['answer_relevancy'] = st.slider(
            "Answer Relevancy",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('answer_relevancy', 0.8)),
            step=0.05,
            help="🎯 답변이 질문과 관련있는지 평가 | 데이터: Golden Dataset (question, answer)",
            key="rag_answer_relevancy"
        )

    with col2:
        thresholds['context_recall'] = st.slider(
            "Context Recall",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('context_recall', 0.8)),
            step=0.05,
            help="🎯 컨텍스트가 정답을 포함하는지 평가 | 데이터: Golden Dataset (context, ground_truth)",
            key="rag_context_recall"
        )

        thresholds['context_precision'] = st.slider(
            "Context Precision",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('context_precision', 0.8)),
            step=0.05,
            help="🎯 검색된 컨텍스트의 정확도 평가 | 데이터: Golden Dataset (context, ground_truth)",
            key="rag_context_precision"
        )

    # 저장
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        editor_name = st.text_input("편집자 이름", value="Admin", key="rag_editor_name")

    with col2:
        edit_reason = st.text_input("변경 이유", value="RAG threshold adjustment", key="rag_edit_reason")

    with col3:
        st.write("")
        st.write("")

        if st.button("💾 저장", type="primary", key="save_rag_thresholds"):
            try:
                manager.save_thresholds(
                    thresholds=thresholds,
                    editor=editor_name,
                    reason=edit_reason
                )

                st.success("✅ RAG 메트릭 임계값이 저장되었습니다!")

            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")

    # 프리셋
    with st.expander("🎨 프리셋 (전체 임계값)"):
        st.caption("⚠️ 프리셋 적용 시 기본 메트릭과 RAG 메트릭이 모두 변경됩니다")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📘 엄격 (Strict)", key="preset_strict"):
                thresholds.update({
                    'tcr': 95.0,
                    'accuracy': 90.0,
                    'hallucination': 2.0,
                    'quality': 8.0,
                    'latency': 2.0,
                    'cost_per_task': 0.03,
                    'faithfulness': 0.9,
                    'answer_relevancy': 0.9,
                    'context_recall': 0.85,
                    'context_precision': 0.85
                })
                manager.save_thresholds(thresholds, "Admin", "Preset: Strict")
                st.rerun()

        with col2:
            if st.button("📗 표준 (Standard)", key="preset_standard"):
                thresholds.update({
                    'tcr': 90.0,
                    'accuracy': 85.0,
                    'hallucination': 5.0,
                    'quality': 7.0,
                    'latency': 3.0,
                    'cost_per_task': 0.05,
                    'faithfulness': 0.8,
                    'answer_relevancy': 0.8,
                    'context_recall': 0.8,
                    'context_precision': 0.8
                })
                manager.save_thresholds(thresholds, "Admin", "Preset: Standard")
                st.rerun()

        with col3:
            if st.button("📙 관대 (Lenient)", key="preset_lenient"):
                thresholds.update({
                    'tcr': 80.0,
                    'accuracy': 75.0,
                    'hallucination': 10.0,
                    'quality': 6.0,
                    'latency': 5.0,
                    'cost_per_task': 0.10,
                    'faithfulness': 0.7,
                    'answer_relevancy': 0.7,
                    'context_recall': 0.7,
                    'context_precision': 0.7
                })
                manager.save_thresholds(thresholds, "Admin", "Preset: Lenient")
                st.rerun()



# ============================================================================
# 새로운 임계값 설정 UI (v2) - 기본 지표 + 고급 평가 분리
# ============================================================================

def render_basic_metrics_tab_v2(manager: DataEditorManager):
    """기본 지표 임계값 설정 - 정확도 & 품질 + 효율성"""
    st.markdown("### 📊 기본 지표 임계값")
    st.caption("💡 모든 평가에서 기본적으로 측정되는 핵심 지표")

    # 임계값 로드
    thresholds = manager.load_thresholds()

    st.info("""
    📊 **기본 지표 (8개)**
    - 🎯 **정확도 & 품질 (7개)**: 작업 수행 정확도, 응답 품질, RAG 정확도
    - ⚡ **효율성 (2개)**: 응답 시간, 비용

    💡 각 지표는 시스템 품질의 다른 측면을 측정합니다.
    """)

    # ========================================================================
    # 🎯 정확도 & 품질 (7개)
    # ========================================================================
    st.markdown("## 🎯 정확도 & 품질")
    st.caption("시스템의 정확성과 응답 품질을 측정하는 지표")

    # ------------------------------------------------------------------------
    # 1. 작업 수행 정확도
    # ------------------------------------------------------------------------
    st.markdown("### 📍 작업 수행 정확도")
    st.caption("작업이 얼마나 정확하게 완료되는지 측정")

    col1, col2 = st.columns(2)

    with col1:
        thresholds['tcr'] = st.slider(
            "TCR (Task Completion Rate) (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('tcr', 90.0)),
            step=1.0,
            help="📊 작업 완료율 최소 목표 | 완료된 작업 / 전체 작업",
            key="v2_tcr"
        )

    with col2:
        thresholds['accuracy'] = st.slider(
            "Accuracy (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(thresholds.get('accuracy', 85.0)),
            step=1.0,
            help="📊 응답의 사실적 정확도 | 정답과의 일치도",
            key="v2_accuracy"
        )

    st.markdown("---")

    # ------------------------------------------------------------------------
    # 2. 응답 품질
    # ------------------------------------------------------------------------
    st.markdown("### 📍 응답 품질")
    st.caption("응답의 전반적인 품질과 관련성 측정")

    col1, col2 = st.columns(2)

    with col1:
        thresholds['quality'] = st.slider(
            "Quality Score (1-10)",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('quality', 7.0)),
            step=0.1,
            help="📊 응답 품질 최소 목표 | 가독성, 완성도, 유용성 종합",
            key="v2_quality"
        )

    with col2:
        thresholds['answer_relevancy'] = st.slider(
            "Answer Relevancy (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('answer_relevancy', 0.8)),
            step=0.05,
            help="🎯 답변이 질문과 관련있는 정도 | 질문-답변 관련성",
            key="v2_answer_relevancy"
        )

    st.markdown("---")

    # ------------------------------------------------------------------------
    # 3. RAG 정확도
    # ------------------------------------------------------------------------
    st.markdown("### 📍 RAG 정확도")
    st.caption("검색-생성 시스템의 정확도 측정 (컨텍스트 충실도 및 검색 성능)")

    col1, col2, col3 = st.columns(3)

    with col1:
        thresholds['faithfulness'] = st.slider(
            "Faithfulness (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('faithfulness', 0.8)),
            step=0.05,
            help="🎯 답변이 컨텍스트에 충실한 정도 | 환각 방지",
            key="v2_faithfulness"
        )

    with col2:
        thresholds['context_recall'] = st.slider(
            "Context Recall (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('context_recall', 0.8)),
            step=0.05,
            help="🎯 정답을 포함하는 정도 | 검색 재현율 (높을수록 좋음)",
            key="v2_context_recall"
        )

    with col3:
        thresholds['context_precision'] = st.slider(
            "Context Precision (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('context_precision', 0.8)),
            step=0.05,
            help="🎯 검색된 내용의 정확도 | 검색 정밀도 (불필요한 정보 제거)",
            key="v2_context_precision"
        )

    st.markdown("---")

    # ========================================================================
    # ⚡ 효율성 (2개)
    # ========================================================================
    st.markdown("## ⚡ 효율성")
    st.caption("시스템의 응답 속도와 비용 효율성 측정")

    col1, col2 = st.columns(2)

    with col1:
        thresholds['latency'] = st.slider(
            "Latency (초) - 최대",
            min_value=0.0,
            max_value=10.0,
            value=float(thresholds.get('latency', 3.0)),
            step=0.1,
            help="⚡ 응답 시간 최대 허용치 | 사용자 경험에 직접 영향",
            key="v2_latency"
        )

    with col2:
        thresholds['cost_per_task'] = st.slider(
            "Cost per Task ($) - 최대",
            min_value=0.0,
            max_value=1.0,
            value=float(thresholds.get('cost_per_task', 0.05)),
            step=0.01,
            help="⚡ 작업당 비용 최대 허용치 | 비즈니스 지속가능성",
            key="v2_cost"
        )

    st.markdown("---")

    # ========================================================================
    # ➕ 선택적 지표
    # ========================================================================
    st.markdown("## ➕ 선택적 지표")

    with st.expander("🔍 추가 품질 지표 (선택사항)", expanded=False):
        st.caption("필요시 추가로 모니터링할 수 있는 지표")

        col1, col2 = st.columns(2)

        with col1:
            thresholds['hallucination'] = st.slider(
                "Hallucination Rate (%) - 최대",
                min_value=0.0,
                max_value=20.0,
                value=float(thresholds.get('hallucination', 5.0)),
                step=0.5,
                help="⚠️ 환각 발생률 최대 허용치 | Faithfulness와 반대 개념 (낮을수록 좋음)",
                key="v2_hallucination"
            )
            st.caption("💡 Faithfulness와 반대 관계")

        with col2:
            st.info("""
            **Hallucination이란?**
            - 모델이 사실이 아닌 정보를 생성하는 현상
            - Faithfulness ↑ = Hallucination ↓
            - Strict: 2% / Standard: 5% / Lenient: 10%
            """)

    # ========================================================================
    # 🎨 프리셋
    # ========================================================================
    st.markdown("---")
    st.markdown("## 🎨 프리셋")

    with st.expander("📋 프리셋으로 빠르게 설정하기", expanded=False):
        st.info("""
        🎯 **프리셋별 전략**
        - **📘 Strict (엄격)**: 프로덕션 환경 | 정확도 & 품질 최우선
        - **📗 Standard (표준)**: 일반 사용 | 균형잡힌 설정
        - **📙 Lenient (관대)**: 개발/테스트 | 빠른 반복, 비용 절감

        ⚠️ 프리셋 적용 시 모든 기본 지표 (8개)가 변경됩니다.
        """)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**📘 Strict (엄격)**")
            st.caption("프로덕션 환경")
            with st.container():
                st.markdown("""
                - 정확도 & 품질: ⬆️⬆️⬆️
                - 효율성: 엄격
                """)
                if st.button("적용", key="v2_preset_strict", type="primary", width="stretch"):
                    thresholds.update({
                        'tcr': 95.0,
                        'accuracy': 90.0,
                        'quality': 8.0,
                        'latency': 2.0,
                        'faithfulness': 0.9,
                        'answer_relevancy': 0.9,
                        'context_recall': 0.85,
                        'context_precision': 0.85,
                        'hallucination': 2.0,
                        'cost_per_task': 0.03
                    })
                    manager.save_thresholds(thresholds, "Admin", "Preset: Strict")
                    st.success("✅ Strict 프리셋 적용!")
                    st.rerun()

        with col2:
            st.markdown("**📗 Standard (표준)**")
            st.caption("일반 사용 (권장)")
            with st.container():
                st.markdown("""
                - 정확도 & 품질: ⬆️⬆️
                - 효율성: 균형
                """)
                if st.button("적용", key="v2_preset_standard", type="secondary", width="stretch"):
                    thresholds.update({
                        'tcr': 90.0,
                        'accuracy': 85.0,
                        'quality': 7.0,
                        'latency': 3.0,
                        'faithfulness': 0.8,
                        'answer_relevancy': 0.8,
                        'context_recall': 0.8,
                        'context_precision': 0.8,
                        'hallucination': 5.0,
                        'cost_per_task': 0.05
                    })
                    manager.save_thresholds(thresholds, "Admin", "Preset: Standard")
                    st.success("✅ Standard 프리셋 적용!")
                    st.rerun()

        with col3:
            st.markdown("**📙 Lenient (관대)**")
            st.caption("개발/테스트")
            with st.container():
                st.markdown("""
                - 정확도 & 품질: ⬆️
                - 효율성: 여유있게
                """)
                if st.button("적용", key="v2_preset_lenient", width="stretch"):
                    thresholds.update({
                        'tcr': 80.0,
                        'accuracy': 75.0,
                        'quality': 6.0,
                        'latency': 5.0,
                        'faithfulness': 0.7,
                        'answer_relevancy': 0.7,
                        'context_recall': 0.7,
                        'context_precision': 0.7,
                        'hallucination': 10.0,
                        'cost_per_task': 0.10
                    })
                    manager.save_thresholds(thresholds, "Admin", "Preset: Lenient")
                    st.success("✅ Lenient 프리셋 적용!")
                    st.rerun()

    # ========================================================================
    # 💾 저장
    # ========================================================================
    st.markdown("---")
    st.markdown("## 💾 변경사항 저장")

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        editor_name = st.text_input("편집자 이름", value="Admin", key="v2_editor_name", help="변경사항을 기록할 편집자 이름")

    with col2:
        edit_reason = st.text_input("변경 이유", value="기본 지표 임계값 조정", key="v2_edit_reason", help="변경 이유를 입력하세요")

    with col3:
        st.write("")
        st.write("")

        if st.button("💾 저장", type="primary", key="v2_save_thresholds", width="stretch"):
            try:
                manager.save_thresholds(
                    thresholds=thresholds,
                    editor=editor_name,
                    reason=edit_reason
                )

                st.success("✅ 기본 지표 임계값이 저장되었습니다!")
                st.info("📊 편집 기록이 자동으로 추적됩니다. '📊 이력 관리' 탭에서 확인하세요.")
                st.balloons()

            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")
                import traceback
                with st.expander("🔍 오류 상세"):
                    st.code(traceback.format_exc())


def render_advanced_eval_tab_v2(manager: DataEditorManager):
    """고급 평가 설정 UI (DeepEval, Ragas만)"""
    st.markdown("### 🔬 고급 평가 설정")
    st.caption("💡 외부 라이브러리 통합 (DeepEval, Ragas)")

    # 설정 로드
    config = manager.load_advanced_eval_config()

    st.info("""
    🎯 **고급 평가 안내**
    - **DeepEval (4개)**: G-Eval, Hallucination Detection, Toxicity, Bias
    - **Ragas (4개)**: Context Relevancy, Answer Similarity, Answer Correctness, Overall Score

    💡 기본 지표 외에 추가적인 심층 평가가 필요한 경우 활성화하세요.
    ⚠️ 고급 평가는 추가 API 비용이 발생합니다.
    """)

    # ========================================================================
    # DeepEval 설정
    # ========================================================================
    st.markdown("---")
    st.markdown("### 🔍 DeepEval")

    col1, col2 = st.columns([1, 3])

    with col1:
        deepeval_enabled = st.checkbox(
            "DeepEval 활성화",
            value=config['deepeval']['enabled'],
            key="v2_deepeval_enabled",
            help="G-Eval, Hallucination, Toxicity, Bias 메트릭 활성화"
        )

    with col2:
        deepeval_model = st.selectbox(
            "DeepEval 모델",
            options=["gpt-4o-mini", "gpt-4o"],
            index=0 if config['deepeval']['model'] == "gpt-4o-mini" else 1,
            key="v2_deepeval_model",
            help="gpt-4o-mini: 비용 최적화 (권장) | gpt-4o: 고품질 (10배 비용)",
            disabled=not deepeval_enabled
        )

    if deepeval_enabled:
        st.markdown("#### DeepEval 메트릭 임계값")

        col1, col2 = st.columns(2)

        with col1:
            g_eval_threshold = st.slider(
                "G-Eval (최소)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['deepeval']['thresholds'].get('g_eval', 0.7)),
                step=0.05,
                help="일반 응답 품질 평가 점수 최소값",
                key="v2_deepeval_g_eval"
            )

            hallucination_threshold = st.slider(
                "Hallucination (최대)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['deepeval']['thresholds'].get('hallucination', 0.3)),
                step=0.05,
                help="환각 발생 점수 최대 허용치 (낮을수록 좋음)",
                key="v2_deepeval_hallucination"
            )

        with col2:
            toxicity_threshold = st.slider(
                "Toxicity (최대)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['deepeval']['thresholds'].get('toxicity', 0.3)),
                step=0.05,
                help="독성 점수 최대 허용치 (낮을수록 좋음)",
                key="v2_deepeval_toxicity"
            )

            bias_threshold = st.slider(
                "Bias (최대)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['deepeval']['thresholds'].get('bias', 0.3)),
                step=0.05,
                help="편향 점수 최대 허용치 (낮을수록 좋음)",
                key="v2_deepeval_bias"
            )

    # ========================================================================
    # Ragas 설정
    # ========================================================================
    st.markdown("---")
    st.markdown("### 📊 Ragas")

    col1, col2 = st.columns([1, 3])

    with col1:
        ragas_enabled = st.checkbox(
            "Ragas 활성화",
            value=config['ragas']['enabled'],
            key="v2_ragas_enabled",
            help="Context Relevancy, Answer Similarity, Answer Correctness, Overall Score 메트릭 활성화"
        )

    with col2:
        ragas_model = st.selectbox(
            "Ragas 모델",
            options=["gpt-4o-mini", "gpt-4o"],
            index=0 if config['ragas']['model'] == "gpt-4o-mini" else 1,
            key="v2_ragas_model",
            help="gpt-4o-mini: 비용 최적화 (권장) | gpt-4o: 고품질 (10배 비용)",
            disabled=not ragas_enabled
        )

    if ragas_enabled:
        st.markdown("#### Ragas 메트릭 임계값")

        col1, col2, col3 = st.columns(3)

        with col1:
            context_relevancy_threshold = st.slider(
                "Context Relevancy (최소)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['ragas']['thresholds'].get('context_relevancy', 0.7)),
                step=0.05,
                help="검색된 컨텍스트의 관련성 최소값",
                key="v2_ragas_context_relevancy"
            )

        with col2:
            answer_similarity_threshold = st.slider(
                "Answer Similarity (최소)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['ragas']['thresholds'].get('answer_similarity', 0.7)),
                step=0.05,
                help="답변과 Ground Truth의 유사도 최소값",
                key="v2_ragas_answer_similarity"
            )

        with col3:
            answer_correctness_threshold = st.slider(
                "Answer Correctness (최소)",
                min_value=0.0,
                max_value=1.0,
                value=float(config['ragas']['thresholds'].get('answer_correctness', 0.7)),
                step=0.05,
                help="답변의 정확도 최소값",
                key="v2_ragas_answer_correctness"
            )

        # RAGAS Overall Score (선택적)
        with st.expander("➕ RAGAS Overall Score (선택사항)", expanded=False):
            st.caption("모든 Ragas 메트릭을 종합한 전체 점수")

            col1, col2 = st.columns([2, 3])

            with col1:
                overall_score_threshold = st.slider(
                    "Overall Score (최소)",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(config['ragas']['thresholds'].get('overall_score', 0.7)),
                    step=0.05,
                    help="RAG 시스템 전체 품질 점수 최소값",
                    key="v2_ragas_overall_score"
                )

            with col2:
                st.info("""
                **RAGAS Overall Score란?**
                - 모든 Ragas 메트릭의 종합 점수
                - RAG 시스템의 전반적인 품질을 단일 지표로 표현
                - 벤치마킹과 비교에 유용

                **계산 방식:**
                여러 메트릭의 조화 평균 또는 가중 평균
                """)

    # ========================================================================
    # LangSmith 설정
    # ========================================================================
    st.markdown("---")
    st.markdown("### 🔗 LangSmith 연동 (선택사항)")

    col1, col2 = st.columns([1, 3])

    with col1:
        langsmith_enabled = st.checkbox(
            "LangSmith 활성화",
            value=config['langsmith']['enabled'],
            key="v2_langsmith_enabled",
            help="LangSmith 추적 및 분석 기능 활성화 (API 키 필요)"
        )

    with col2:
        langsmith_api_key = st.text_input(
            "LangSmith API Key",
            value=config['langsmith']['api_key'],
            type="password",
            key="v2_langsmith_api_key",
            help="LangSmith API 키 (https://smith.langchain.com/)",
            disabled=not langsmith_enabled
        )

    # ========================================================================
    # 저장
    # ========================================================================
    st.markdown("---")

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        editor_name = st.text_input("편집자 이름", value="Admin", key="v2_advanced_editor_name")

    with col2:
        edit_reason = st.text_input("변경 이유", value="Advanced eval configuration", key="v2_advanced_edit_reason")

    with col3:
        st.write("")
        st.write("")

        if st.button("💾 저장", type="primary", key="v2_save_advanced_eval"):
            try:
                # 설정 업데이트
                new_config = {
                    "deepeval": {
                        "enabled": deepeval_enabled,
                        "model": deepeval_model,
                        "thresholds": {
                            "g_eval": g_eval_threshold if deepeval_enabled else config['deepeval']['thresholds'].get('g_eval', 0.7),
                            "hallucination": hallucination_threshold if deepeval_enabled else config['deepeval']['thresholds'].get('hallucination', 0.3),
                            "toxicity": toxicity_threshold if deepeval_enabled else config['deepeval']['thresholds'].get('toxicity', 0.3),
                            "bias": bias_threshold if deepeval_enabled else config['deepeval']['thresholds'].get('bias', 0.3)
                        }
                    },
                    "ragas": {
                        "enabled": ragas_enabled,
                        "model": ragas_model,
                        "thresholds": {
                            "context_relevancy": context_relevancy_threshold if ragas_enabled else config['ragas']['thresholds'].get('context_relevancy', 0.7),
                            "answer_similarity": answer_similarity_threshold if ragas_enabled else config['ragas']['thresholds'].get('answer_similarity', 0.7),
                            "answer_correctness": answer_correctness_threshold if ragas_enabled else config['ragas']['thresholds'].get('answer_correctness', 0.7),
                            "overall_score": overall_score_threshold if ragas_enabled else config['ragas']['thresholds'].get('overall_score', 0.7)
                        }
                    },
                    "langsmith": {
                        "enabled": langsmith_enabled,
                        "api_key": langsmith_api_key
                    }
                }

                manager.save_advanced_eval_config(
                    config=new_config,
                    editor=editor_name,
                    reason=edit_reason
                )

                st.success("✅ 고급 평가 설정이 저장되었습니다!")
                st.balloons()

                # 비용 경고
                if (deepeval_enabled and deepeval_model == "gpt-4o") or (ragas_enabled and ragas_model == "gpt-4o"):
                    st.warning("""
                    ⚠️ **비용 주의**
                    - gpt-4o 모델 선택: gpt-4o-mini 대비 약 10배 비용
                    - 대량 평가 시 비용이 급증할 수 있습니다
                    - 테스트 환경에서는 gpt-4o-mini 사용을 권장합니다
                    """)

            except Exception as e:
                st.error(f"❌ 저장 실패: {str(e)}")
                import traceback
                with st.expander("🔍 오류 상세"):
                    st.code(traceback.format_exc())

    # ========================================================================
    # 현재 설정 요약
    # ========================================================================
    with st.expander("📋 현재 설정 요약"):
        st.json(config)


def render_version_manager():
    """버전 관리 UI"""
    st.subheader("📚 버전 관리")

    manager = DataEditorManager()

    # 버전 목록 조회
    col1, col2 = st.columns([3, 1])

    with col1:
        data_name = st.text_input(
            "데이터 이름 필터 (선택사항)",
            placeholder="예: performance_data",
            key="version_filter"
        )

    with col2:
        if st.button("🔄 새로고침", key="refresh_versions"):
            st.rerun()

    versions = manager.list_versions(data_name=data_name if data_name else None)

    if not versions:
        st.info("📁 저장된 버전이 없습니다.")
        return

    st.info(f"📦 총 {len(versions)}개의 버전이 있습니다.")

    # 버전 목록 표시
    for i, version in enumerate(versions[:20]):  # 최근 20개만
        with st.expander(f"🔖 버전 {version.version_id} - {version.description}"):
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown(f"**버전 ID:** {version.version_id}")
                st.markdown(f"**생성 시간:** {version.timestamp}")

            with col2:
                st.markdown(f"**설명:** {version.description}")

            with col3:
                target_file = st.text_input(
                    "복원할 파일 경로",
                    value="data/evaluation_results/performance_data.json",
                    key=f"rollback_target_{i}"
                )

                if st.button("⏮️ 롤백", key=f"rollback_{i}"):
                    editor = st.text_input("롤백 실행자", value="Admin", key=f"rollback_editor_{i}")

                    if manager.rollback_to_version(
                        version_id=version.version_id,
                        target_filepath=target_file,
                        editor=editor
                    ):
                        st.success(f"✅ 버전 {version.version_id}로 롤백 완료!")
                        st.rerun()


def render_edit_history():
    """편집 기록 UI"""
    st.subheader("📜 편집 기록")

    manager = DataEditorManager()

    # 편집 기록 로드
    history_df = manager.load_edit_history(limit=100)

    if history_df.empty:
        st.info("📁 편집 기록이 없습니다.")
        return

    st.info(f"📦 총 {len(history_df)}개의 편집 기록")

    # 필터
    with st.expander("🔍 필터"):
        col1, col2, col3 = st.columns(3)

        with col1:
            data_types = ["전체"] + list(history_df['data_type'].unique())
            selected_data_type = st.selectbox("데이터 유형", data_types)

        with col2:
            edit_types = ["전체"] + list(history_df['edit_type'].unique())
            selected_edit_type = st.selectbox("편집 유형", edit_types)

        with col3:
            editors = ["전체"] + list(history_df['editor'].unique())
            selected_editor = st.selectbox("편집자", editors)

        # 필터 적용
        filtered_df = history_df.copy()

        if selected_data_type != "전체":
            filtered_df = filtered_df[filtered_df['data_type'] == selected_data_type]

        if selected_edit_type != "전체":
            filtered_df = filtered_df[filtered_df['edit_type'] == selected_edit_type]

        if selected_editor != "전체":
            filtered_df = filtered_df[filtered_df['editor'] == selected_editor]

    # 테이블 표시
    display_columns = ['timestamp', 'editor', 'edit_type', 'data_type', 'data_id', 'reason']

    st.dataframe(
        filtered_df[display_columns],
        width="stretch",
        height=400
    )

    # 상세 보기
    with st.expander("🔍 편집 상세 보기"):
        if len(filtered_df) > 0:
            selected_idx = st.selectbox(
                "편집 선택",
                range(len(filtered_df)),
                format_func=lambda i: f"{filtered_df.iloc[i]['edit_id']}: {filtered_df.iloc[i]['reason']}"
            )

            edit_row = filtered_df.iloc[selected_idx]
            edit_details = manager.get_edit_details(edit_row['edit_id'])

            if edit_details:
                st.markdown(f"**편집 ID:** {edit_details.edit_id}")
                st.markdown(f"**시간:** {edit_details.timestamp}")
                st.markdown(f"**편집자:** {edit_details.editor}")
                st.markdown(f"**유형:** {edit_details.edit_type}")
                st.markdown(f"**데이터 유형:** {edit_details.data_type}")
                st.markdown(f"**대상 ID:** {edit_details.data_id}")
                st.markdown(f"**이유:** {edit_details.reason}")

                if edit_details.before_value:
                    st.markdown("**변경 전:**")
                    st.json(edit_details.before_value)

                if edit_details.after_value:
                    st.markdown("**변경 후:**")
                    st.json(edit_details.after_value)


# ============================================================================
# Test 투명성 UI
# ============================================================================

def render_transparency_tab():
    """Test 투명성 탭 렌더링"""
    st.header("🔬 Test 투명성 & 주석")

    sub_tab = st.tabs([
        "메트릭 계산 과정",
        "주석 관리",
        "Audit Log",
        "상세 리포트"
    ])

    with sub_tab[0]:
        render_metric_calculation_traces()

    with sub_tab[1]:
        render_annotation_manager()

    with sub_tab[2]:
        render_audit_log_viewer()

    with sub_tab[3]:
        render_detailed_report()


def render_metric_calculation_traces():
    """메트릭 계산 과정 시각화"""
    st.subheader("📊 메트릭 계산 과정")

    manager = TestTransparencyManager()

    # Trace 파일 목록
    from pathlib import Path

    traces_dir = get_evaluation_results_dir() / "traces"

    if not traces_dir.exists():
        st.info("📁 추적 데이터가 없습니다. 평가를 먼저 실행하세요.")
        return

    trace_files = list(traces_dir.glob("trace_*.json"))

    if not trace_files:
        st.info("📁 추적 데이터가 없습니다.")
        return

    # 파일 선택
    selected_trace_file = st.selectbox(
        "Trace 선택",
        [f.name for f in trace_files],
        format_func=lambda name: name.replace("trace_", "").replace(".json", "")
    )

    # Trace 로드
    trace_path = traces_dir / selected_trace_file

    with open(trace_path, 'r', encoding='utf-8') as f:
        trace_data = json.load(f)

    # 메트릭 정보
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("메트릭", trace_data['metric_name'])

    with col2:
        st.metric("타입", trace_data['metric_type'])

    with col3:
        final_value = trace_data.get('final_value')
        if final_value is not None:
            st.metric("최종 값", f"{final_value:.3f}")

    # 계산 단계
    st.markdown("---")
    st.markdown("### 📝 계산 단계")

    steps = trace_data.get('steps', [])

    if not steps:
        st.info("📁 계산 단계 정보가 없습니다.")
    else:
        # 타임라인 시각화
        fig = go.Figure()

        for i, step in enumerate(steps):
            status = step.get('status', 'unknown')
            color = {
                'success': 'green',
                'failed': 'red',
                'running': 'yellow',
                'pending': 'gray'
            }.get(status, 'blue')

            fig.add_trace(go.Scatter(
                x=[i],
                y=[1],
                mode='markers+text',
                marker=dict(size=30, color=color),
                text=step['step_name'],
                textposition='bottom center',
                showlegend=False,
                hovertemplate=f"<b>{step['step_name']}</b><br>{step['description']}<br>상태: {status}<extra></extra>"
            ))

        fig.update_layout(
            title="계산 단계 타임라인",
            xaxis_title="단계",
            yaxis=dict(visible=False),
            height=200
        )

        st.plotly_chart(fig, width="stretch")

        # 각 단계 상세
        for i, step in enumerate(steps, 1):
            with st.expander(f"📌 단계 {i}: {step['step_name']} - {step['status'].upper()}"):
                st.markdown(f"**설명:** {step['description']}")

                if step.get('input_data'):
                    st.markdown("**입력 데이터:**")
                    st.json(step['input_data'])

                if step.get('output_data'):
                    st.markdown("**출력 데이터:**")
                    st.json(step['output_data'])

                if step.get('error_message'):
                    st.error(f"⚠️ 에러: {step['error_message']}")

                if step.get('intermediate_results'):
                    st.markdown("**중간 결과:**")
                    for result in step['intermediate_results']:
                        st.json(result)

    # 설명
    st.markdown("---")
    st.markdown("### 💡 설명")

    # explanation은 최상위 레벨 또는 metadata에 있을 수 있음
    explanation = trace_data.get('explanation') or trace_data.get('metadata', {}).get('explanation', '설명 없음')
    st.markdown(explanation)

    # 메타데이터 표시
    metadata = trace_data.get('metadata', {})
    if metadata:
        st.markdown("### 📋 메타데이터")
        st.json(metadata)

    # 영향 요인
    factors = trace_data.get('factors') or trace_data.get('metadata', {}).get('factors')
    if factors:
        st.markdown("### 📈 영향 요인")
        st.json(factors)


def render_annotation_manager():
    """주석 관리 UI"""
    st.subheader("📝 주석 관리")

    manager = TestTransparencyManager()

    # 탭: 주석 목록 | 주석 추가
    tab1, tab2 = st.tabs(["📋 주석 목록", "➕ 주석 추가"])

    with tab1:
        # 필터
        col1, col2, col3 = st.columns(3)

        with col1:
            annotation_type_filter = st.selectbox(
                "주석 유형",
                ["전체", "comment", "issue", "improvement", "confirmation", "question"]
            )

        with col2:
            status_filter = st.selectbox(
                "상태",
                ["전체", "open", "in_progress", "resolved", "closed"]
            )

        with col3:
            priority_filter = st.selectbox(
                "우선순위",
                ["전체", "low", "normal", "high", "critical"]
            )

        # 주석 로드
        annotations = manager.load_annotations(
            annotation_type=annotation_type_filter if annotation_type_filter != "전체" else None,
            status=status_filter if status_filter != "전체" else None
        )

        if priority_filter != "전체":
            annotations = [a for a in annotations if a.priority == priority_filter]

        if not annotations:
            st.info("📁 주석이 없습니다.")
        else:
            st.info(f"📦 {len(annotations)}개의 주석")

            # 주석 카드
            for annotation in annotations:
                with st.container():
                    st.markdown("---")

                    # 헤더
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        priority_emoji = {
                            "low": "🟢",
                            "normal": "🟡",
                            "high": "🟠",
                            "critical": "🔴"
                        }.get(annotation.get('priority'), "⚪")

                        st.markdown(f"### {priority_emoji} {annotation.get('title', 'Untitled')}")

                    with col2:
                        st.badge(annotation.get('annotation_type', 'unknown').upper())

                    with col3:
                        status_color = {
                            "open": "blue",
                            "in_progress": "orange",
                            "resolved": "green",
                            "closed": "gray"
                        }.get(annotation.get('status'), "blue")

                        st.markdown(f":{status_color}[{annotation.get('status', 'unknown')}]")

                    # 내용
                    st.markdown(f"**작성자:** {annotation.get('author', 'Unknown')}")
                    st.markdown(f"**작성일:** {annotation.get('created_at', 'N/A')}")

                    if annotation.get('related_metric'):
                        st.markdown(f"**관련 메트릭:** {annotation.get('related_metric')} = {annotation.get('related_value', 'N/A')}")

                    st.markdown(f"**내용:**\n{annotation.get('content', '')}")

                    # 태그
                    if annotation.get('tags'):
                        st.markdown(f"**태그:** {', '.join(annotation.get('tags', []))}")

                    # 답변
                    if annotation.get('replies'):
                        with st.expander(f"💬 답변 ({len(annotation.get('replies', []))}개)"):
                            for reply in annotation.get('replies', []):
                                st.markdown(f"**{reply.get('author', 'Unknown')}** ({reply.get('created_at', 'N/A')})")
                                st.markdown(reply.get('content', ''))
                                st.markdown("---")

                    # 액션
                    col1, col2, col3 = st.columns([1, 1, 3])

                    annotation_id = annotation.get('annotation_id', '')

                    with col1:
                        if st.button("💬 답변", key=f"reply_{annotation_id}"):
                            st.session_state[f"show_reply_{annotation_id}"] = True

                    with col2:
                        new_status = st.selectbox(
                            "상태 변경",
                            ["", "open", "in_progress", "resolved", "closed"],
                            key=f"status_{annotation_id}"
                        )

                        if new_status and new_status != annotation.get('status'):
                            if hasattr(manager, 'update_annotation_status'):
                                manager.update_annotation_status(
                                    annotation_id=annotation_id,
                                    new_status=new_status,
                                    user="Admin"
                                )
                                st.rerun()

                    # 답변 입력
                    if st.session_state.get(f"show_reply_{annotation_id}"):
                        reply_content = st.text_area(
                            "답변 내용",
                            key=f"reply_content_{annotation_id}"
                        )

                        if st.button("📤 답변 제출", key=f"submit_reply_{annotation_id}"):
                            if hasattr(manager, 'add_reply_to_annotation'):
                                manager.add_reply_to_annotation(
                                    annotation_id=annotation_id,
                                    author="Admin",
                                content=reply_content
                            )
                            st.success("✅ 답변이 추가되었습니다!")
                            st.rerun()

    with tab2:
        st.markdown("### ➕ 새 주석 추가")

        with st.form("annotation_form"):
            col1, col2 = st.columns(2)

            with col1:
                target_type = st.selectbox(
                    "대상 유형",
                    ["task", "metric", "dataset"]
                )

                annotation_type = st.selectbox(
                    "주석 유형",
                    [t.value for t in AnnotationType]
                )

            with col2:
                target_id = st.text_input("대상 ID")

                priority = st.selectbox(
                    "우선순위",
                    ["low", "normal", "high", "critical"]
                )

            title = st.text_input("제목")

            content = st.text_area("내용", height=150)

            col1, col2 = st.columns(2)

            with col1:
                related_metric = st.text_input("관련 메트릭 (선택)")

            with col2:
                related_value = st.number_input("관련 값 (선택)", value=0.0, step=0.01)

            tags = st.text_input("태그 (쉼표로 구분)")

            author = st.text_input("작성자", value="Admin")

            submitted = st.form_submit_button("📤 주석 추가")

            if submitted:
                if not title or not content or not target_id:
                    st.error("⚠️ 필수 항목을 모두 입력하세요.")
                else:
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

                    annotation_id = manager.add_annotation(
                        target_type=target_type,
                        target_id=target_id,
                        annotation_type=AnnotationType(annotation_type),
                        title=title,
                        content=content,
                        author=author,
                        related_metric=related_metric if related_metric else None,
                        related_value=related_value if related_value > 0 else None,
                        priority=priority,
                        tags=tag_list
                    )

                    st.success(f"✅ 주석이 추가되었습니다! (ID: {annotation_id})")
                    st.rerun()


def render_audit_log_viewer():
    """Audit Log 뷰어"""
    st.subheader("📜 Audit Log")

    manager = TestTransparencyManager()

    # 필터
    col1, col2, col3 = st.columns(3)

    with col1:
        event_type_filter = st.selectbox(
            "이벤트 유형",
            ["전체", "evaluation", "annotation", "edit", "view"]
        )

    with col2:
        user_filter = st.text_input("사용자 필터")

    with col3:
        limit = st.number_input("로그 수", min_value=10, max_value=1000, value=100, step=10)

    # 로드
    logs = manager.load_audit_logs(
        event_type=event_type_filter if event_type_filter != "전체" else None,
        user=user_filter if user_filter else None,
        limit=int(limit)
    )

    if not logs:
        st.info("📁 Audit Log가 없습니다.")
        return

    st.info(f"📦 {len(logs)}개의 로그")

    # 데이터프레임 변환
    log_data = []
    for log in logs:
        log_data.append({
            "시간": log.get('timestamp', 'N/A'),
            "이벤트": log.get('event_type', 'unknown'),
            "사용자": log.get('user', 'Unknown'),
            "액션": log.get('action', 'unknown'),
            "대상": f"{log.get('target_type', 'N/A')}/{log.get('target_id', 'N/A')}",
            "성공": "✅" if log.get('success', False) else "❌"
        })

    df = pd.DataFrame(log_data)

    st.dataframe(df, width="stretch", height=400)

    # 상세 보기
    with st.expander("🔍 로그 상세 보기"):
        if len(logs) > 0:
            selected_idx = st.selectbox(
                "로그 선택",
                range(len(logs)),
                format_func=lambda i: f"{logs[i].get('timestamp', 'N/A')}: {logs[i].get('action', 'unknown')}"
            )

            log = logs[selected_idx]

            st.markdown(f"**로그 ID:** {log.get('log_id', 'N/A')}")
            st.markdown(f"**시간:** {log.get('timestamp', 'N/A')}")
            st.markdown(f"**이벤트 유형:** {log.get('event_type', 'unknown')}")
            st.markdown(f"**사용자:** {log.get('user', 'Unknown')}")
            st.markdown(f"**액션:** {log.get('action', 'unknown')}")
            st.markdown(f"**대상 유형:** {log.get('target_type', 'N/A')}")
            st.markdown(f"**대상 ID:** {log.get('target_id', 'N/A')}")
            st.markdown(f"**성공 여부:** {'✅ 성공' if log.get('success', False) else '❌ 실패'}")

            if log.get('error_message'):
                st.error(f"에러: {log.get('error_message')}")

            if log.get('details'):
                st.markdown("**상세 정보:**")
                st.json(log.get('details'))


def render_detailed_report():
    """투명성 종합리포트 뷰어 (Phase 1-5 완전 구현)"""
    st.subheader("📋 투명성 종합리포트")

    # Transparent Report 파일 목록
    from pathlib import Path

    reports_dir = get_evaluation_results_dir() / "transparent_reports"

    if not reports_dir.exists():
        st.info("📁 투명한 평가 리포트가 없습니다.")
        return

    report_files = list(reports_dir.glob("*.json"))

    if not report_files:
        st.info("📁 투명한 평가 리포트가 없습니다.")
        return

    # 파일 선택 및 내보내기 버튼
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        selected_report = st.selectbox(
            "리포트 선택",
            [f.name for f in report_files]
        )

    report_path = reports_dir / selected_report
    report_id = selected_report.replace('.json', '')

    with col2:
        # Excel 내보내기
        if st.button("📊 Excel로 내보내기", width="stretch"):
            from agent_evaluator.utils.test_transparency_manager import TestTransparencyManager

            manager = TestTransparencyManager()
            excel_path = manager.export_report_to_excel(report_id)

            if excel_path:
                st.success(f"✅ Excel로 내보내기 완료!")
                st.info(f"📂 파일 위치: {excel_path}")

                # 다운로드 버튼 제공
                with open(excel_path, 'rb') as f:
                    st.download_button(
                        label="⬇️ Excel 다운로드",
                        data=f,
                        file_name=f"{report_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.error("❌ Excel 내보내기 실패. pandas와 openpyxl이 설치되어 있는지 확인하세요.")

    with col3:
        # Markdown 내보내기
        if st.button("📄 Markdown으로 내보내기", width="stretch"):
            from agent_evaluator.utils.test_transparency_manager import TestTransparencyManager

            manager = TestTransparencyManager()
            md_path = manager.export_report_to_markdown(report_id)

            if md_path:
                st.success(f"✅ Markdown으로 내보내기 완료!")
                st.info(f"📂 파일 위치: {md_path}")

                # 다운로드 버튼 제공
                with open(md_path, 'r', encoding='utf-8') as f:
                    st.download_button(
                        label="⬇️ Markdown 다운로드",
                        data=f.read(),
                        file_name=f"{report_id}.md",
                        mime="text/markdown"
                    )
            else:
                st.error("❌ Markdown 내보내기 실패.")

    with open(report_path, 'r', encoding='utf-8') as f:
        report_data = json.load(f)

    # =========================================================================
    # Phase 1: 평가 메타데이터
    # =========================================================================
    st.markdown("### 📋 평가 메타데이터")

    col1, col2, col3, col4 = st.columns(4)

    report_metadata = report_data.get('metadata', {})
    test_config = report_metadata.get('test_configuration', {})

    with col1:
        st.markdown("**평가 ID**")
        st.code(report_data.get('report_id', 'N/A'))
        st.markdown("**Task ID**")
        st.code(report_data.get('task_id', 'N/A'))

    with col2:
        st.markdown("**평가 시간**")
        st.text(report_data.get('generated_at', 'N/A')[:19])
        st.markdown("**평가자**")
        st.text(test_config.get('evaluator', 'System'))

    with col3:
        st.markdown("**환경**")
        st.text(test_config.get('environment', 'N/A'))
        st.markdown("**프레임워크**")
        st.text(test_config.get('framework', 'N/A'))

    with col4:
        st.markdown("**모델**")
        st.text(test_config.get('model_name', 'N/A'))
        st.markdown("**데이터셋**")
        dataset_path = test_config.get('dataset_path', 'N/A')
        st.text(dataset_path if len(dataset_path) < 20 else f"...{dataset_path[-17:]}")

    # 임계값 설정 표시
    if test_config.get('thresholds'):
        with st.expander("🎯 임계값 설정"):
            thresholds_df = pd.DataFrame([
                {
                    "메트릭": k,
                    "임계값": v,
                    "타입": "≥" if k in ['tcr', 'accuracy', 'tool_selection_accuracy', 'agent_coordination', 'workflow_execution'] else "≤"
                }
                for k, v in test_config['thresholds'].items()
            ])
            st.dataframe(thresholds_df, width="stretch")

    # =========================================================================
    # 요약 메트릭
    # =========================================================================
    st.markdown("---")
    st.markdown("### 📈 요약 메트릭")

    col1, col2, col3, col4 = st.columns(4)

    summary = report_data.get('summary', {})

    with col1:
        st.metric("총 태스크", summary.get('total_tasks', 0))

    with col2:
        st.metric("이상 감지", summary.get('anomalies_detected', 0))

    with col3:
        st.metric("경고", summary.get('warnings', 0))

    with col4:
        quality_score = summary.get('data_quality_score', 0)
        st.metric("데이터 품질", f"{quality_score:.0f}/100")

    # =========================================================================
    # Phase 2: 메트릭 계산 투명성
    # =========================================================================
    traces = report_data.get('traces', [])
    if traces:
        st.markdown("---")
        st.markdown("### 📊 메트릭 계산 투명성")

        st.info(f"📦 {len(traces)}개의 메트릭 계산 추적 기록")

        # 메트릭별 그룹화
        metric_groups = {}
        for trace in traces:
            metric_name = trace.get('metric_name', 'unknown')
            if metric_name not in metric_groups:
                metric_groups[metric_name] = []
            metric_groups[metric_name].append(trace)

        # 탭으로 메트릭별 표시
        if metric_groups:
            metric_tabs = st.tabs(list(metric_groups.keys()))

            for idx, (metric_name, metric_traces) in enumerate(metric_groups.items()):
                with metric_tabs[idx]:
                    for trace in metric_traces:
                        status_emoji = "✅" if trace.get('status') == 'completed' else "⚠️"
                        with st.expander(f"{status_emoji} {trace.get('trace_id', 'N/A')} - {trace.get('status', 'N/A')}"):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown(f"**계산 방법:** {trace.get('calculation_method', 'N/A')}")
                                st.markdown(f"**메트릭 타입:** {trace.get('metric_type', 'N/A')}")

                            with col2:
                                st.markdown(f"**최종 값:** {trace.get('final_value', 'N/A')}")
                                st.markdown(f"**시작 시간:** {trace.get('started_at', 'N/A')[:19]}")

                            # 계산 단계
                            steps = trace.get('steps', [])
                            if steps:
                                st.markdown("**계산 단계:**")
                                for step_idx, step in enumerate(steps, 1):
                                    step_status = "✅" if step.get('status') == 'success' else "❌"
                                    st.markdown(f"{step_idx}. {step_status} **{step.get('step_name', 'Step')}** - {step.get('description', '')}")

                            # 입력/출력 데이터
                            if trace.get('input_data') or trace.get('output_data'):
                                col1, col2 = st.columns(2)
                                with col1:
                                    if trace.get('input_data'):
                                        st.markdown("**입력 데이터:**")
                                        st.json(trace['input_data'])
                                with col2:
                                    if trace.get('output_data'):
                                        st.markdown("**출력 데이터:**")
                                        st.json(trace['output_data'])

                            # 메타데이터
                            if trace.get('metadata'):
                                with st.expander("📋 메타데이터"):
                                    st.json(trace['metadata'])

    # =========================================================================
    # Phase 3: 평가 신뢰도 분석
    # =========================================================================
    reliability = report_data.get('reliability_analysis', {})
    if reliability:
        st.markdown("---")
        st.markdown("### 📈 평가 신뢰도 분석")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            sample_size = reliability.get('sample_size', 0)
            min_required = reliability.get('min_required_samples', 30)
            sufficient = reliability.get('sufficient', False)
            st.metric(
                "샘플 크기",
                sample_size,
                delta=f"최소 {min_required}개 필요" if not sufficient else "충분함",
                delta_color="normal" if sufficient else "inverse"
            )

        with col2:
            confidence = reliability.get('confidence_level', 0)
            st.metric("신뢰 수준", f"{confidence:.0f}%")

        with col3:
            variance = reliability.get('variance', 0)
            st.metric("분산", f"{variance:.4f}")

        with col4:
            std_error = reliability.get('standard_error', 0)
            st.metric("표준 오차", f"{std_error:.4f}")

        # 경고 및 권장사항
        warnings_list = reliability.get('warnings', [])
        if warnings_list:
            st.warning("⚠️ **주의사항**\n\n" + "\n- ".join(warnings_list))

        recommendations = reliability.get('recommendations', [])
        if recommendations:
            with st.expander("💡 신뢰도 개선 권장사항"):
                for rec in recommendations:
                    st.markdown(f"- {rec}")

    # =========================================================================
    # 실행 가능한 인사이트
    # =========================================================================
    actionable = report_data.get('actionable_insights', [])
    if actionable:
        st.markdown("---")
        st.markdown("### 💡 실행 가능한 인사이트")

        for item in actionable:
            priority_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }.get(item.get('priority', 'medium'), "🟡")

            with st.expander(f"{priority_emoji} {item.get('title', 'Insight')} ({item.get('priority', 'medium')})"):
                st.markdown(f"**카테고리:** {item.get('category', 'N/A')}")
                st.markdown(f"**현재 상태:** {item.get('current_state', 'N/A')}")
                st.markdown(f"**권장 액션:** {item.get('action', 'N/A')}")
                st.markdown(f"**예상 효과:** {item.get('expected_impact', 'N/A')}")

                if item.get('implementation'):
                    st.markdown("**구현 단계:**")
                    for step in item.get('implementation', []):
                        st.markdown(f"- {step}")

    # =========================================================================
    # 이상 현상 & 긍정적 인사이트
    # =========================================================================
    anomalies_data = report_data.get('anomalies', {})

    # 이상 현상
    anomalies = anomalies_data.get('anomalies', [])
    if anomalies:
        st.markdown("---")
        st.markdown("### ⚠️ 이상 현상")

        for anomaly in anomalies:
            st.warning(f"**{anomaly.get('title', 'Anomaly')}**: {anomaly.get('description', 'N/A')}")

    # 긍정적 인사이트
    insights_data = anomalies_data.get('insights', [])
    if insights_data:
        st.markdown("---")
        st.markdown("### ✨ 긍정적 인사이트")

        for insight in insights_data:
            with st.expander(f"💡 {insight.get('title', 'Insight')}"):
                st.markdown(f"**설명:** {insight.get('description', 'N/A')}")
                st.markdown(f"**권장사항:** {insight.get('action', 'N/A')}")

    # =========================================================================
    # 데이터 품질 분석
    # =========================================================================
    quality = report_data.get('quality_report', {})
    if quality:
        st.markdown("---")
        st.markdown("### 📊 데이터 품질 분석")

        col1, col2, col3 = st.columns(3)

        overall_score = quality.get('overall_score', 0)
        completeness = quality.get('data_completeness', {})

        with col1:
            st.metric("종합 품질 점수", f"{overall_score:.0f}/100")

        with col2:
            st.metric("전체 태스크", completeness.get('total_tasks', 0))

        with col3:
            st.metric("스코어가 있는 태스크", completeness.get('tasks_with_scores', 0))

        # 품질 이슈
        issues = quality.get('quality_issues', [])
        if issues:
            st.markdown("**품질 이슈:**")
            for issue in issues:
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🔵"
                }.get(issue.get('severity', 'medium'), "⚪")

                st.warning(f"{severity_emoji} **{issue.get('type', 'Issue')}** ({issue.get('severity', 'medium')}): {issue.get('description', '')}\n\n💡 {issue.get('recommendation', '')}")

        # 통과한 검사
        passed = quality.get('passed_checks', [])
        if passed:
            with st.expander(f"✅ 통과한 검사 ({len(passed)}개)"):
                for check in passed:
                    st.success(f"**{check.get('check', 'Check')}**: {check.get('result', '')}")

    # =========================================================================
    # Phase 4: 변경 이력 타임라인
    # =========================================================================
    st.markdown("---")
    st.markdown("### 📅 변경 이력 타임라인")

    # Annotations과 Audit Logs를 시간순으로 통합
    timeline_events = []

    # Annotations 추가
    for annotation in report_data.get('annotations', []):
        timeline_events.append({
            'timestamp': annotation.get('timestamp', ''),
            'type': 'annotation',
            'icon': '💬',
            'title': annotation.get('title', 'Annotation'),
            'content': annotation.get('content', ''),
            'author': annotation.get('author', 'Unknown'),
            'priority': annotation.get('priority', 'medium')
        })

    # Audit Logs 추가
    for log in report_data.get('audit_logs', []):
        timeline_events.append({
            'timestamp': log.get('timestamp', ''),
            'type': 'audit',
            'icon': '📝',
            'title': f"{log.get('event_type', 'Event')}: {log.get('action', 'Action')}",
            'content': str(log.get('details', {}).get('message', '')),
            'author': log.get('user', 'System'),
            'success': log.get('success', True)
        })

    # 시간순 정렬
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)

    if timeline_events:
        st.info(f"📦 {len(timeline_events)}개의 이벤트 (최근 20개 표시)")

        # 타임라인 표시
        for event in timeline_events[:20]:  # 최근 20개만
            col1, col2 = st.columns([1, 5])

            with col1:
                st.markdown(f"**{event['icon']} {event['type'].upper()}**")
                st.caption(event['timestamp'][:19] if len(event['timestamp']) >= 19 else event['timestamp'])

            with col2:
                if event['type'] == 'annotation':
                    priority_color = {
                        'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'
                    }.get(event['priority'], '⚪')
                    st.markdown(f"{priority_color} **{event['title']}** by {event['author']}")
                else:
                    status = "✅" if event.get('success') else "❌"
                    st.markdown(f"{status} **{event['title']}** by {event['author']}")

                if event['content']:
                    st.caption(event['content'])

            st.markdown("---")
    else:
        st.info("📁 변경 이력이 없습니다.")

    # =========================================================================
    # Phase 5: 이전 평가와 비교
    # =========================================================================
    comparison = report_data.get('comparison', {})
    if comparison and comparison.get('metric_changes'):
        st.markdown("---")
        st.markdown("### 📊 이전 평가와 비교")

        previous_report_id = comparison.get('previous_report_id')
        previous_date = comparison.get('previous_generated_at', 'N/A')[:19]
        st.info(f"📋 기준 리포트: {previous_report_id} ({previous_date})")

        # 메트릭 변화 데이터 준비
        metric_changes = comparison.get('metric_changes', {})

        if metric_changes:
            # 테이블 데이터
            changes_data = []
            for metric, data in metric_changes.items():
                changes_data.append({
                    "메트릭": metric,
                    "이전": f"{data['previous']:.2f}" if isinstance(data['previous'], (int, float)) else data['previous'],
                    "현재": f"{data['current']:.2f}" if isinstance(data['current'], (int, float)) else data['current'],
                    "변화": f"{data['change']:+.2f}",
                    "변화율": f"{data['change_percent']:+.1f}%",
                    "상태": "📈" if data['change'] > 0 else "📉" if data['change'] < 0 else "➡️"
                })

            changes_df = pd.DataFrame(changes_data)

            # 🆕 차트 추가
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 📊 메트릭 값 비교")
                # 이전 vs 현재 바 차트
                chart_data = pd.DataFrame({
                    '이전': [data['previous'] for data in metric_changes.values()],
                    '현재': [data['current'] for data in metric_changes.values()]
                }, index=list(metric_changes.keys()))

                st.bar_chart(chart_data)

            with col2:
                st.markdown("#### 📈 변화율 분석")
                # 변화율 차트
                change_percent_data = pd.DataFrame({
                    '변화율 (%)': [data['change_percent'] for data in metric_changes.values()]
                }, index=list(metric_changes.keys()))

                # 색상을 위한 포지티브/네거티브 분리
                positive_changes = {}
                negative_changes = {}
                for metric, data in metric_changes.items():
                    if data['change_percent'] >= 0:
                        positive_changes[metric] = data['change_percent']
                    else:
                        negative_changes[metric] = abs(data['change_percent'])

                if positive_changes:
                    st.markdown("**🟢 개선**")
                    pos_df = pd.DataFrame({
                        '개선 (%)': list(positive_changes.values())
                    }, index=list(positive_changes.keys()))
                    st.bar_chart(pos_df, color="#00FF00")

                if negative_changes:
                    st.markdown("**🔴 저하**")
                    neg_df = pd.DataFrame({
                        '저하 (%)': list(negative_changes.values())
                    }, index=list(negative_changes.keys()))
                    st.bar_chart(neg_df, color="#FF0000")

            # 테이블
            st.markdown("#### 📋 상세 비교 테이블")
            st.dataframe(changes_df, width="stretch")

            # 🆕 추세 분석
            st.markdown("#### 📈 추세 분석")

            # 개선/저하 통계
            improved = sum(1 for data in metric_changes.values() if data['change'] > 0)
            degraded = sum(1 for data in metric_changes.values() if data['change'] < 0)
            unchanged = sum(1 for data in metric_changes.values() if data['change'] == 0)

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("개선된 메트릭", improved, delta=f"{(improved/len(metric_changes)*100):.0f}%", delta_color="normal")

            with col2:
                st.metric("저하된 메트릭", degraded, delta=f"{(degraded/len(metric_changes)*100):.0f}%", delta_color="inverse")

            with col3:
                st.metric("변화 없음", unchanged)

            # 가장 큰 변화
            if metric_changes:
                max_improvement = max(metric_changes.items(), key=lambda x: x[1]['change_percent'])
                max_degradation = min(metric_changes.items(), key=lambda x: x[1]['change_percent'])

                col1, col2 = st.columns(2)

                with col1:
                    if max_improvement[1]['change_percent'] > 0:
                        st.success(f"🏆 **최대 개선**: {max_improvement[0]}\n\n{max_improvement[1]['change_percent']:+.1f}% ({max_improvement[1]['previous']:.2f} → {max_improvement[1]['current']:.2f})")

                with col2:
                    if max_degradation[1]['change_percent'] < 0:
                        st.error(f"⚠️ **최대 저하**: {max_degradation[0]}\n\n{max_degradation[1]['change_percent']:+.1f}% ({max_degradation[1]['previous']:.2f} → {max_degradation[1]['current']:.2f})")

        # 주요 변화 요약
        summary_text = comparison.get('summary', '')
        if summary_text:
            st.success(f"✨ **종합 평가**: {summary_text}")
    else:
        st.markdown("---")
        st.markdown("### 📊 이전 평가와 비교")
        st.info("📁 비교할 이전 평가가 없습니다. 동일한 task_id로 평가를 반복하면 자동으로 비교 분석이 제공됩니다.")


def render_external_data_sources_tab():
    """외부 데이터 소스 관리 탭 - 개발자 라이브러리 데이터 자동 검색"""
    from pathlib import Path
    from agent_evaluator.utils.data_registry import DataRegistry
    import shutil

    st.header("🔗 레지스트리 (모든 프로젝트)")

    # 기능 설명 - Zero Config와의 차이 명확히
    st.markdown("""
    모든 프로젝트의 평가 데이터를 중앙 레지스트리로 관리합니다.

    **💡 Zero Configuration vs 레지스트리:**
    - **Zero Configuration**: 현재 프로젝트 데이터는 메인 Dashboard에서 **자동 로드**됩니다
    - **레지스트리**: 모든 프로젝트 데이터를 확인하고, 다른 프로젝트 데이터를 **가져올 수 있습니다**

    **작동 방식:**
    - `PerformanceMonitor.save_to_file()` 호출 시 자동으로 `~/.agent_evaluator/registry.json`에 등록
    - 현재 프로젝트와 다른 프로젝트의 데이터를 모두 확인 가능
    - 필요한 경우 다른 프로젝트 데이터를 가져오기
    """)

    # 레지스트리 상태 확인
    registry_file = Path.home() / ".agent_evaluator" / "registry.json"
    if not registry_file.exists():
        st.warning("⚠️ 레지스트리가 아직 생성되지 않았습니다")
        st.info("""
        **레지스트리 생성 방법:**
        1. 개발자 프로젝트에서 `agent_evaluator` 라이브러리 사용
        2. `PerformanceMonitor.save_to_file()` 호출하여 평가 데이터 저장
        3. 자동으로 `~/.agent_evaluator/registry.json`에 등록됨

        **예제 코드:**
        ```python
        from agent_evaluator import PerformanceMonitor, TaskResult, TaskType
        from datetime import datetime

        monitor = PerformanceMonitor()

        # Task 기록
        task = TaskResult(
            task_id="task_001",
            task_type=TaskType.QA.value,
            success=True,
            completion_score=1.0,
            accuracy_score=0.95,
            execution_time=1.2,
            tokens_used={"input": 100, "output": 50, "total": 150},
            tool_calls=[],
            attempts=1,
            errors=[],
            timestamp=datetime.now()
        )
        monitor.record_task(task)

        # 저장 (자동으로 레지스트리에 등록됨)
        monitor.save_to_file("my_evaluation.json")
        ```
        """)
        return

    # 레지스트리 정보
    registry_info = DataRegistry.get_registry_info()

    # Handle case where registry_info is None
    if registry_info is None:
        st.warning("⚠️ 레지스트리 정보를 불러올 수 없습니다.")
        registry_info = {
            'total_files': 0,
            'project_count': 0,
            'total_size_mb': 0,
            'registry_path': '~/.agent_evaluator/registry.json'
        }

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 데이터 파일", f"{registry_info['total_files']}개")
    with col2:
        st.metric("프로젝트 수", f"{registry_info['project_count']}개")
    with col3:
        st.metric("총 용량", f"{registry_info['total_size_mb']} MB")

    st.caption(f"📂 레지스트리 위치: `{registry_info['registry_path']}`")

    st.markdown("---")

    # 프로젝트 검색 및 가져오기
    st.subheader("📦 프로젝트별 데이터")

    # 새로고침 버튼
    if st.button("🔄 프로젝트 목록 새로고침", type="secondary"):
        st.rerun()

    projects = DataRegistry.get_projects()

    if not projects:
        st.info("등록된 프로젝트가 없습니다")
        return

    # 현재 프로젝트 감지 (Dashboard 위치 기반)
    current_dashboard_path = Path(__file__).resolve().parent
    current_project_name = None

    # Dashboard 폴더의 부모가 프로젝트 루트
    # 예: /path/to/MyProject/Dashboard → MyProject
    for parent in current_dashboard_path.parents:
        if (parent / "Dashboard").exists() or (parent / ".git").exists():
            current_project_name = parent.name
            break

    if not current_project_name:
        # 폴더 구조에서 추출 (fallback)
        current_project_name = current_dashboard_path.parent.name

    # 프로젝트별 표시
    for idx, project in enumerate(projects):
        project_name = project["name"]
        project_files = project["files"]
        is_current_project = (project_name == current_project_name)

        # 유효성 상태 계산 (파일 존재 여부)
        valid_files = sum(1 for f in project_files if Path(f["filepath"]).exists())
        total_files = len(project_files)
        validity_pct = (valid_files / total_files * 100) if total_files > 0 else 0

        # 프로젝트 카드 - 현재 프로젝트 표시
        title_parts = [
            '🟢' if validity_pct == 100 else '🟡' if validity_pct > 0 else '🔴',
            f"**{project_name}**"
        ]

        if is_current_project:
            title_parts.append("**[현재 프로젝트]**")

        title_parts.append(f"({valid_files}/{total_files} 파일)")

        with st.expander(
            " ".join(title_parts),
            expanded=(idx == 0)  # 첫 번째만 펼쳐짐
        ):
            # 현재 프로젝트 안내
            if is_current_project:
                st.info("""
                💡 **현재 프로젝트의 데이터입니다**

                이 데이터는 메인 Dashboard에서 **자동으로 로드**됩니다 (Zero Configuration).
                가져오기 없이 바로 사용 가능합니다.

                ```bash
                # 메인 Dashboard 실행
                streamlit run Dashboard/streamlit_dashboard.py
                ```
                """)

            # 프로젝트 정보
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("유효 파일", f"{valid_files}/{total_files}")
            with col2:
                st.metric("총 용량", f"{round(project['total_size'] / (1024*1024), 2)} MB")
            with col3:
                latest = project.get("latest_update")
                if latest:
                    from datetime import datetime
                    dt = datetime.fromisoformat(latest)
                    st.metric("최근 업데이트", dt.strftime("%Y-%m-%d"))
                else:
                    st.metric("최근 업데이트", "N/A")

            # 파일 목록
            st.markdown("**파일 목록:**")

            files_to_show = project_files[:10]  # 최대 10개만 표시

            for file_info in files_to_show:
                file_path = Path(file_info["filepath"])
                exists = file_path.exists()

                icon = "✅" if exists else "❌"
                status = "존재" if exists else "없음"

                # 메타데이터 표시
                metadata = file_info.get("metadata", {})
                meta_str = ""
                if metadata:
                    total_tasks = metadata.get("total_tasks", "?")
                    framework = metadata.get("framework", "N/A")
                    meta_str = f" - {total_tasks} tasks, {framework}"

                st.text(f"{icon} {file_path.name} ({status}){meta_str}")

            if total_files > 10:
                st.caption(f"... 외 {total_files - 10}개 파일")

            st.markdown("---")

            # 가져오기 옵션
            st.markdown("**데이터 가져오기:**")

            col1, col2 = st.columns(2)

            with col1:
                copy_mode = st.radio(
                    "가져오기 방식:",
                    ["복사 (권장)", "참조만"],
                    key=f"copy_mode_{project_name}",
                    help="복사: Dashboard 폴더로 파일 복사\n참조만: 원본 위치 그대로 사용"
                )

                overwrite = st.checkbox(
                    "기존 파일 덮어쓰기",
                    key=f"overwrite_{project_name}",
                    help="같은 이름의 파일이 있을 경우 덮어씁니다"
                )

            with col2:
                if st.button(
                    f"📥 {project_name} 데이터 가져오기",
                    type="primary",
                    key=f"import_{project_name}",
                    width="stretch"
                ):
                    with st.spinner(f"{project_name} 데이터 가져오는 중..."):
                        # 대상 디렉토리
                        target_dir = get_evaluation_results_dir()
                        target_dir.mkdir(parents=True, exist_ok=True)

                        imported = 0
                        skipped = 0
                        failed = 0
                        imported_files = []
                        failed_files = []

                        # 파일 복사
                        for file_info in project_files:
                            source_path = Path(file_info["filepath"])

                            if not source_path.exists():
                                failed += 1
                                failed_files.append({"source": str(source_path), "reason": "파일이 존재하지 않음"})
                                continue

                            target_path = target_dir / source_path.name

                            # 덮어쓰기 확인
                            if target_path.exists() and not overwrite:
                                skipped += 1
                                continue

                            try:
                                if copy_mode == "복사 (권장)":
                                    shutil.copy2(source_path, target_path)
                                imported += 1
                                imported_files.append({"source": str(source_path), "destination": str(target_path)})
                            except Exception as e:
                                failed += 1
                                failed_files.append({"source": str(source_path), "reason": str(e)})

                        # 결과 표시
                        st.success(
                            f"✅ 가져오기 완료!\n"
                            f"- 가져온 파일: {imported}개\n"
                            f"- 건너뛴 파일: {skipped}개\n"
                            f"- 실패한 파일: {failed}개"
                        )

                        # 상세 정보
                        if imported_files:
                            with st.expander("가져온 파일 상세"):
                                for file in imported_files:
                                    st.text(f"✓ {Path(file['source']).name}")
                                    st.caption(f"   → {file['destination']}")

                        if failed_files:
                            with st.expander("실패한 파일", expanded=True):
                                for file in failed_files:
                                    st.error(f"✗ {Path(file['source']).name}\n  이유: {file['reason']}")

    st.markdown("---")

    # 레지스트리 관리
    st.subheader("🛠️ 레지스트리 관리")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🧹 존재하지 않는 파일 정리", width="stretch"):
            with st.spinner("레지스트리 정리 중..."):
                removed_count = DataRegistry.cleanup_missing_files()
                st.success(
                    f"✅ 정리 완료!\n"
                    f"- 제거된 항목: {removed_count}개"
                )
                st.rerun()

    with col2:
        st.info(
            "**정리 기능:**\n"
            "삭제된 파일이나 이동된 파일을 레지스트리에서 제거합니다."
        )

    # 도움말
    with st.expander("❓ 도움말 - Zero Configuration vs 레지스트리"):
        st.markdown("""
        ### 🎯 두 기능의 차이점

        #### 1️⃣ Zero Configuration (자동 로드)
        **언제 사용하나요?**
        - 같은 프로젝트 내에서 평가 → Dashboard 확인

        **작동 방식:**
        ```python
        # 프로젝트 내에서 평가 실행
        monitor.save_to_file("my_eval.json")
        # → Dashboard/data/evaluation_results/my_eval.json 저장
        ```

        ```bash
        # 메인 Dashboard 실행
        streamlit run Dashboard/streamlit_dashboard.py
        # → my_eval.json 자동 로드 ✨ (설정 불필요)
        ```

        **특징:**
        - ✅ 같은 프로젝트 데이터 자동 로드
        - ✅ 설정 불필요
        - ✅ 실시간 동기화

        ---

        #### 2️⃣ 레지스트리 (크로스 프로젝트)
        **언제 사용하나요?**
        - 여러 프로젝트의 데이터를 한 곳에서 관리
        - 다른 프로젝트의 평가 결과를 비교/분석

        **작동 방식:**
        ```
        [프로젝트 A] → save_to_file() → ~/.agent_evaluator/registry.json 등록
        [프로젝트 B] → save_to_file() → ~/.agent_evaluator/registry.json 등록

        [중앙 Dashboard] → 레지스트리 탭 → 모든 프로젝트 데이터 확인
                        → "가져오기" → 분석/비교
        ```

        **특징:**
        - ✅ 모든 프로젝트 데이터 조회
        - ✅ 크로스 프로젝트 비교
        - ✅ 중앙 집중식 품질 관리

        ---

        ### 💡 사용 시나리오

        **시나리오 1: 단일 프로젝트 개발**
        ```
        MyAgent/ 프로젝트에서 작업 중
        → Zero Configuration만 사용
        → 메인 Dashboard에서 자동 로드
        → 레지스트리 탭은 참고용
        ```

        **시나리오 2: 멀티 프로젝트 품질 관리**
        ```
        TeamA, TeamB, TeamC가 각자 Agent 개발
        → 중앙 품질 관리자가 모든 프로젝트 모니터링
        → 레지스트리 탭에서 모든 데이터 확인
        → 필요한 데이터 가져와서 비교 분석
        ```

        ---

        ### 📋 레지스트리 관리

        **자동 등록:**
        ```python
        monitor.save_to_file("results.json")
        # 출력: 📋 Dashboard 레지스트리에 자동 등록됨
        ```

        **레지스트리 위치:**
        - `~/.agent_evaluator/registry.json`
        - 모든 프로젝트의 데이터 위치 중앙 관리

        **가져오기 방식:**
        - **복사 (권장)**: Dashboard 폴더로 복사 (원본 삭제되어도 안전)
        - **참조만**: 원본 위치 그대로 사용 (디스크 공간 절약)

        **정리 기능:**
        - "🧹 존재하지 않는 파일 정리" 버튼
        - 삭제/이동된 파일을 레지스트리에서 자동 제거
        """)


if __name__ == "__main__":
    st.set_page_config(
        page_title="Agent Evaluator - Data Editor",
        page_icon="📝",
        layout="wide"
    )

    st.title("📝 Agent Evaluator - 데이터 편집")

    render_data_editor_tab()
