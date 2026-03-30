"""
AgentEvalMiddleware — FastAPI/ASGI 미들웨어

각 요청마다 실행 시간을 자동 측정하고 StreamingEvaluator에 기록한다.
기존 코드 변경 없이 app.add_middleware() 한 줄로 삽입 가능.
"""
from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from agent_evaluator.streaming.evaluator import StreamingEvaluator

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    _STARLETTE_AVAILABLE = True
except ImportError:
    _STARLETTE_AVAILABLE = False
    BaseHTTPMiddleware = object  # type: ignore[assignment,misc]


class AgentEvalMiddleware(BaseHTTPMiddleware if _STARLETTE_AVAILABLE else object):  # type: ignore[misc]
    """FastAPI/Starlette ASGI 미들웨어.

    Args:
        app: FastAPI/Starlette 앱.
        evaluator: StreamingEvaluator 인스턴스.
        sample_rate: 측정 샘플링률 (0.0~1.0). Default 1.0.
        skip_paths: 측정 제외 경로 목록. Default ["/health", "/docs", "/static"].

    Example::
        from agent_evaluator.streaming import StreamingEvaluator, AgentEvalMiddleware

        evaluator = StreamingEvaluator(monitor=monitor)
        app.add_middleware(AgentEvalMiddleware, evaluator=evaluator, sample_rate=1.0)
    """

    def __init__(self, app: object, evaluator: "StreamingEvaluator", sample_rate: float = 1.0,
                 skip_paths: Optional[List[str]] = None) -> None:
        if not _STARLETTE_AVAILABLE:
            raise ImportError(
                "starlette is required for AgentEvalMiddleware. "
                "Install it with: pip install 'agent-evaluator[serve]'"
            )
        super().__init__(app)
        self.evaluator = evaluator
        self.sample_rate = sample_rate
        self.skip_paths = set(skip_paths or ["/health", "/docs", "/redoc", "/openapi.json", "/static"])

    async def dispatch(self, request: "Request", call_next: Callable) -> "Response":
        path = request.url.path
        if path in self.skip_paths or random.random() > self.sample_rate:
            return await call_next(request)

        start = time.time()
        has_error = False
        try:
            response = await call_next(request)
            has_error = response.status_code >= 500
            return response
        except Exception:
            has_error = True
            raise
        finally:
            execution_time = time.time() - start
            task_id = f"{request.method}:{path}"
            self.evaluator.record(
                task_id=task_id,
                success=not has_error,
                execution_time=execution_time,
                has_error=has_error,
            )
