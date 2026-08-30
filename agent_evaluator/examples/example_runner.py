"""
ExampleRunner - Base class for running agent evaluation examples
Handles common patterns: environment check, file prefix, dashboard instructions
"""
from __future__ import annotations

import os
import traceback
from typing import Callable

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
        required_libs: list[str] | None = None,
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
        print("🔍 Environment check")
        print("=" * 70)

        # Check API key if required
        if self.requires_api_key:
            load_dotenv()
            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                print("\n❌ OPENAI_API_KEY is not set.")
                print("\nHow to set it:")
                print('   Add to a .env file: OPENAI_API_KEY="your-key-here"')
                print('   Or an env var: export OPENAI_API_KEY="your-key-here"')
                return False

            print(f"✅ OPENAI_API_KEY found: {api_key[:10]}...")

        # Check required libraries
        missing_libs = []
        for lib in self.required_libs:
            try:
                __import__(lib)
                print(f"✅ {lib} installed")
            except ImportError:
                missing_libs.append(lib)
                print(f"❌ {lib} not installed")

        if missing_libs:
            print("\n❌ Install the following libraries:")
            print(f"   pip install {' '.join(missing_libs)}")
            return False

        print("\n✅ All dependencies OK!")
        return True

    def print_header(self) -> None:
        """Print example header"""
        print("=" * 70)
        print(f"🎯 Level {self.level} - {self.title}")
        print("=" * 70)

    def save_and_finish(
        self,
        monitor,
        filename_suffix: str,
        dashboard_tabs: list[str] | None = None
    ) -> None:
        """
        Save results and print dashboard instructions

        Args:
            monitor: PerformanceMonitor instance
            filename_suffix: Suffix for filename (e.g., "quickstart_example_result")
            dashboard_tabs: List of dashboard tabs to check
        """
        filename = f"{self.file_prefix}{filename_suffix}.json"

        monitor.save_to_file(filename)

        print(f"\n✅ Saved: {filename}")
        print(f"   Location: {monitor.output_dir / filename}")

        # Dashboard instructions
        print("\n" + "=" * 70)
        print("🎉 Example complete!")
        print("=" * 70)

        print("\n📊 View the results on the dashboard:")
        print("-" * 70)
        print("1. Start the dashboard:")
        print("   agent-eval serve")
        print("")
        print("2. Select the file:")
        print(f"   select {filename}")
        print("")

    def run(self, main_func: Callable) -> None:
        """
        Run example with error handling

        Args:
            main_func: Main example function to execute
        """
        self.print_header()

        if not self.check_environment():
            print("\n⚠️ Set up the environment, then run again.")
            return

        try:
            main_func()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            traceback.print_exc()
