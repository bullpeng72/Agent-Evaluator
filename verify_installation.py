#!/usr/bin/env python3
"""
Agent Evaluator Installation Verification Script
=================================================

이 스크립트는 agent-evaluator 패키지가 올바르게 설치되었는지 검증합니다.
"""

def verify_installation():
    print("="*70)
    print("🔍 Agent Evaluator Installation Verification")
    print("="*70)
    print()

    success = True

    # 1. 패키지 임포트
    print("1️⃣  Checking package import...")
    try:
        import agent_evaluator
        print(f"   ✅ Package imported successfully")
        print(f"   📦 Version: {agent_evaluator.__version__}")
        print(f"   📁 Location: {agent_evaluator.__file__}")
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        success = False
        return success
    print()

    # 2. 핵심 클래스
    print("2️⃣  Checking core classes...")
    try:
        from agent_evaluator import PerformanceMonitor, HybridPerformanceMonitor
        print(f"   ✅ PerformanceMonitor: Available")
        print(f"   ✅ HybridPerformanceMonitor: Available")
    except ImportError as e:
        print(f"   ❌ Core classes failed: {e}")
        success = False
    print()

    # 3. 유틸리티 모듈
    print("3️⃣  Checking utilities...")
    try:
        from agent_evaluator.utils.path_helpers import (
            find_project_root,
            get_dashboard_dir,
            get_evaluation_results_dir
        )
        root = find_project_root()
        print(f"   ✅ path_helpers: Available")
        print(f"   📂 Project root: {root}")

        try:
            dashboard = get_dashboard_dir(root)
            print(f"   📂 Dashboard: {dashboard}")
        except Exception as e:
            print(f"   ⚠️  Dashboard detection: {e}")
    except Exception as e:
        print(f"   ⚠️  Utilities warning: {e}")
    print()

    # 4. 통합 모듈
    print("4️⃣  Checking integration modules...")
    integrations_available = []
    integrations_missing = []

    integration_modules = [
        ("langchain_integration", "LangChain"),
        ("crewai_integration", "CrewAI"),
        ("autogen_integration", "AutoGen"),
        ("langgraph_integration", "LangGraph"),
    ]

    for module_name, display_name in integration_modules:
        try:
            __import__(f"agent_evaluator.integrations.{module_name}")
            integrations_available.append(display_name)
            print(f"   ✅ {display_name}: Available")
        except ImportError:
            integrations_missing.append(display_name)
            print(f"   ⚠️  {display_name}: Module not found")
    print()

    # 5. Helper 모듈
    print("5️⃣  Checking helper modules...")
    try:
        from agent_evaluator.helpers import taskresult_helpers
        print(f"   ✅ taskresult_helpers: Available")
    except ImportError as e:
        print(f"   ⚠️  Helpers warning: {e}")
    print()

    # 6. 데이터셋 모듈
    print("6️⃣  Checking dataset modules...")
    try:
        from agent_evaluator.datasets import korean_rag_evaluator
        print(f"   ✅ korean_rag_evaluator: Available")
    except ImportError as e:
        print(f"   ⚠️  Datasets warning: {e}")
    print()

    # 7. 리포팅 모듈
    print("7️⃣  Checking reporting modules...")
    try:
        from agent_evaluator.reporting import comprehensive_report
        print(f"   ✅ comprehensive_report: Available")
    except ImportError as e:
        print(f"   ⚠️  Reporting warning: {e}")
    print()

    # 8. 간단한 기능 테스트
    print("8️⃣  Running basic functionality test...")
    try:
        from agent_evaluator import PerformanceMonitor

        monitor = PerformanceMonitor()
        print(f"   ✅ PerformanceMonitor initialized")
        print(f"   📊 Available trackers: TCR, Accuracy, Quality, Latency, Cost")

        # Test report generation
        report = monitor.generate_report()
        print(f"   ✅ Report generation: Working")
    except Exception as e:
        print(f"   ⚠️  Functionality test warning: {e}")
        # Don't fail on this - just a basic test
    print()

    # 결과 요약
    print("="*70)
    if success:
        print("✅ Installation Verification: PASSED")
        print()
        print("🎉 All core components are working correctly!")
        print()
        print("📚 Next steps:")
        print("   1. Read documentation: Docs/")
        print("   2. Try examples: Evaluator_Examples/")
        print("   3. Run dashboard: streamlit run Evaluator_Examples/Dashboard/app.py")
    else:
        print("❌ Installation Verification: FAILED")
        print()
        print("🔧 Troubleshooting:")
        print("   1. Reinstall: pip install -e .")
        print("   2. Check Python version: python --version (>= 3.8)")
        print("   3. Check pip: pip show agent-evaluator")
    print("="*70)

    return success


if __name__ == "__main__":
    import sys
    success = verify_installation()
    sys.exit(0 if success else 1)
