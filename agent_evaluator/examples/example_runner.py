"""
ExampleRunner - Base class for running agent evaluation examples
Handles common patterns: environment check, file prefix, dashboard instructions
"""

from typing import Optional, List, Callable
import os
from dotenv import load_dotenv


class ExampleRunner:
    """
    Base class for running agent evaluation examples
    Handles common patterns to reduce boilerplate code

    Example:
        ```python
        from agent_evaluator.examples import ExampleRunner

        def main(runner: ExampleRunner):
            monitor = PerformanceMonitor()
            # ... your evaluation code ...
            runner.save_and_finish(monitor, "results")

        if __name__ == "__main__":
            runner = ExampleRunner(
                example_id="01",
                level=1,
                title="Quick Start",
                required_libs=[],
                requires_api_key=False
            )
            runner.run(lambda: main(runner))
        ```
    """

    def __init__(
        self,
        example_id: str,
        level: int,
        title: str,
        required_libs: Optional[List[str]] = None,
        requires_api_key: bool = False
    ):
        """
        Initialize ExampleRunner

        Args:
            example_id: Example ID (e.g., "01", "03")
            level: Level number (1, 2, or 3)
            title: Example title
            required_libs: List of required library names
            requires_api_key: Whether OpenAI API key is required
        """
        self.example_id = example_id
        self.level = level
        self.title = title
        self.required_libs = required_libs or []
        self.requires_api_key = requires_api_key

        # Auto-generate file prefix
        self.file_prefix = f"[L{level}-{example_id}]_"

    def check_environment(self) -> bool:
        """
        Check environment prerequisites

        Returns:
            True if all prerequisites are met, False otherwise
        """
        print("=" * 70)
        print("🔍 환경 확인")
        print("=" * 70)

        # Check API key if required
        if self.requires_api_key:
            load_dotenv()
            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                print("\n❌ OpenAI API 키가 설정되지 않았습니다.")
                print("\n설정 방법:")
                print('   .env 파일에 추가: OPENAI_API_KEY="your-key-here"')
                print('   또는 환경 변수: export OPENAI_API_KEY="your-key-here"')
                return False

            print(f"✅ OpenAI API 키 확인됨: {api_key[:10]}...")

        # Check required libraries
        missing_libs = []
        for lib in self.required_libs:
            try:
                __import__(lib)
                print(f"✅ {lib} 설치됨")
            except ImportError:
                missing_libs.append(lib)
                print(f"❌ {lib} 설치 필요")

        if missing_libs:
            print(f"\n❌ 다음 라이브러리를 설치하세요:")
            print(f"   pip install {' '.join(missing_libs)}")
            return False

        print("\n✅ 모든 종속성 확인 완료!")
        return True

    def print_header(self):
        """Print example header"""
        print("=" * 70)
        print(f"🎯 Level {self.level} - {self.title}")
        print("=" * 70)

    def save_and_finish(
        self,
        monitor,
        filename_suffix: str,
        dashboard_tabs: Optional[List[str]] = None
    ):
        """
        Save results and print dashboard instructions

        Args:
            monitor: PerformanceMonitor instance
            filename_suffix: Suffix for filename (e.g., "quickstart_example_result")
            dashboard_tabs: List of dashboard tabs to check
        """
        filename = f"{self.file_prefix}{filename_suffix}.json"

        monitor.save_to_file(filename)

        print(f"\n✅ 저장 완료: {filename}")
        print(f"   위치: {monitor.output_dir / filename}")

        # Dashboard instructions
        print("\n" + "=" * 70)
        print("🎉 예제 완료!")
        print("=" * 70)

        print("\n📊 대시보드에서 결과 확인하기:")
        print("-" * 70)
        print("1. 대시보드 실행:")
        print("   agent-eval serve")
        print("")
        print("2. 파일 선택:")
        print(f"   {filename} 선택")
        print("")

    def run(self, main_func: Callable):
        """
        Run example with error handling

        Args:
            main_func: Main example function to execute
        """
        self.print_header()

        if not self.check_environment():
            print("\n⚠️ 환경 설정 후 다시 실행하세요.")
            return

        try:
            main_func()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
