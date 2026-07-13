"""
Dashboard Integration Utilities
================================

Helper functions for integrating with Dashboard storage settings.
Allows examples and external code to save results directly to Dashboard's
configured storage location.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def get_dashboard_storage_path(data_type: str = "results") -> Path | None:
    """
    Get storage path from Dashboard configuration

    Args:
        data_type: Type of data ('results', 'golden_datasets', 'edit_history', 'versions')

    Returns:
        Path object pointing to Dashboard storage location, or None if unavailable

    Example:
        >>> results_path = get_dashboard_storage_path("results")
        >>> if results_path:
        >>>     monitor.save_to_file(str(results_path / "my_eval.json"))
    """
    try:
        from .path_helpers import find_project_root, get_dashboard_dir

        project_root = find_project_root()
        dashboard_dir = get_dashboard_dir(project_root)

        if not dashboard_dir.exists():
            return None

        # Load data_storage_manager without changing CWD — use importlib directly
        module_path = dashboard_dir / "data_storage_manager.py"
        if not module_path.exists():
            return None

        spec = importlib.util.spec_from_file_location(
            "data_storage_manager", module_path
        )
        if spec is None or spec.loader is None:
            return None

        mod = importlib.util.module_from_spec(spec)
        # Make the module resolve relative paths from its own directory
        sys.modules.setdefault("data_storage_manager", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        storage_mgr = mod.get_default_storage_manager()

        path_map = {
            "results":        storage_mgr.get_results_path,
            "golden_datasets": storage_mgr.get_golden_dataset_path,
            "edit_history":   storage_mgr.get_edit_history_path,
            "versions":       storage_mgr.get_versions_path,
        }
        get_path = path_map.get(data_type, storage_mgr.get_results_path)
        path = get_path()
        return path.resolve() if path else None

    except Exception:
        return None


def get_save_path(filename: str, prefer_dashboard: bool = True) -> Path:
    """
    Get optimal save path for evaluation results

    Args:
        filename: Name of the file to save
        prefer_dashboard: If True, prefer Dashboard storage; else use local

    Returns:
        Complete file path where to save the result

    Example:
        >>> save_path = get_save_path("my_eval.json")
        >>> monitor.save_to_file(str(save_path))
    """
    if prefer_dashboard:
        dashboard_path = get_dashboard_storage_path("results")

        if dashboard_path and dashboard_path.exists():
            return dashboard_path / filename

    # Fallback to results/ directory
    from .path_helpers import get_evaluation_results_dir
    local_results = get_evaluation_results_dir(create=True)
    return local_results / filename


def is_dashboard_available() -> bool:
    """
    Check if Dashboard storage integration is available

    Returns:
        True if Dashboard configuration can be accessed

    Example:
        >>> if is_dashboard_available():
        >>>     print("Will save to Dashboard storage")
        >>> else:
        >>>     print("Will save to local storage")
    """
    return get_dashboard_storage_path("results") is not None


def print_save_location_info(filepath: Path):
    """
    Print information about where the file was saved

    Args:
        filepath: Path where the file was saved

    Example:
        >>> save_path = get_save_path("eval.json")
        >>> monitor.save_to_file(str(save_path))
        >>> print_save_location_info(save_path)
    """
    abs_path = filepath.resolve()

    # Check if it's in Dashboard storage
    if "Dashboard" in str(abs_path) and "data" in str(abs_path):
        print("📁 Saved to Dashboard storage")
        print(f"   Path: {abs_path}")
        print("   💡 Viewable directly in the Dashboard!")
    else:
        print("📁 Saved to local directory")
        print(f"   Path: {abs_path}")
        print("   💡 Accessible from Dashboard via registry")


# Convenience function for examples
def save_to_dashboard(
    monitor,
    filename: str,
    prefer_dashboard: bool = True,
    verbose: bool = True
) -> str:
    """
    Save evaluation results with Dashboard integration

    Args:
        monitor: PerformanceMonitor or HybridPerformanceMonitor instance
        filename: Name of the file to save
        prefer_dashboard: If True, try to save to Dashboard storage first
        verbose: If True, print save location information

    Returns:
        Absolute path to the saved file

    Example:
        >>> from agent_evaluator import PerformanceMonitor
        >>> from agent_evaluator.utils.dashboard_integration import save_to_dashboard
        >>>
        >>> monitor = PerformanceMonitor()
        >>> # ... record tasks ...
        >>>
        >>> result_path = save_to_dashboard(
        >>>     monitor,
        >>>     "my_evaluation.json",
        >>>     prefer_dashboard=True
        >>> )
    """
    save_path = get_save_path(filename, prefer_dashboard=prefer_dashboard)

    # Ensure parent directory exists
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # Save using monitor's method
    result_file = monitor.save_to_file(str(save_path))

    if verbose:
        print_save_location_info(Path(result_file))

    return result_file


if __name__ == "__main__":
    # Test the integration
    print("=" * 70)
    print("Dashboard Integration Test")
    print("=" * 70)

    print("\n1. Dashboard 사용 가능 여부:")
    available = is_dashboard_available()
    print(f"   {'✅ Available' if available else '❌ Unavailable'}")

    if available:
        print("\n2. Dashboard 저장소 경로:")
        results_path = get_dashboard_storage_path("results")
        print(f"   Results: {results_path}")

        golden_path = get_dashboard_storage_path("golden_datasets")
        print(f"   Golden Datasets: {golden_path}")

    print("\n3. 저장 경로 테스트:")
    test_path = get_save_path("test_file.json", prefer_dashboard=True)
    print(f"   Dashboard-first: {test_path}")

    test_path_local = get_save_path("test_file.json", prefer_dashboard=False)
    print(f"   Local-first: {test_path_local}")

    print("\n" + "=" * 70)
