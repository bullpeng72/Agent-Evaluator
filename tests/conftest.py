"""
tests/conftest.py — 공통 pytest 픽스처
"""
from __future__ import annotations

import asyncio
import pytest


@pytest.fixture(autouse=True)
def _restore_event_loop():
    """asyncio.run() 호출 후 event loop가 닫혀 후속 테스트가 실패하는 문제를 방지한다.

    test_spec014_generate_report_cache.py/test_spec039_decorator_architecture.py 등이
    asyncio.run()으로 event loop를 닫으면 이후 asyncio.get_event_loop()를 사용하는
    테스트에서 RuntimeError가 발생한다.
    각 테스트 실행 전에 usable event loop가 있는지 보장한다.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        # No current event loop in this thread
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield
