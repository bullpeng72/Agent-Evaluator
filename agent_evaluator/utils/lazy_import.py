"""
agent_evaluator.utils.lazy_import
===================================
``LazyModule`` — 실제 모듈 import를 첫 속성 접근 시점까지 미룬다.

SPEC-041: ``LiveGuardrail`` 실시간 가드레일이 Claude Code 훅으로 쓰일 때, 매 도구
호출마다 별도 파이썬 프로세스가 뜨고 ``import agent_evaluator`` 체인이 실행된다. 그
체인의 ~60%가 ``core/trackers/layer1·layer2·monitor``가 모듈 최상단에서 하는
``import pandas``(~135ms)인데, 이 세 모듈의 pandas/numpy 사용은 전부 배치 리포트
전용 메서드(``get_*_stats()`` 등) 안에 있고 실시간 판정 경로는 절대 건드리지 않는다.
``pd``/``np``를 ``LazyModule``로 바꾸면 훅 콜드스타트가 ~225ms → ~90ms로 줄고, 배치
리포트는 첫 DataFrame 생성 시점에 pandas를 정상적으로 로드한다(동작 변화 없음).

``from __future__ import annotations``가 있는 모듈에서는 ``-> pd.DataFrame`` 같은
어노테이션이 문자열이라 프록시를 건드리지 않는다.
"""
from __future__ import annotations

import importlib
from typing import Any


class LazyModule:
    """지연 로딩 모듈 프록시. ``pd = LazyModule("pandas")`` 후 ``pd.DataFrame(...)``
    첫 호출에서 실제 pandas를 import한다. ``import`` 자체는 무료다."""

    def __init__(self, name: str) -> None:
        self.__dict__["_lazy_name"] = name
        self.__dict__["_lazy_mod"] = None

    def _resolve(self) -> Any:  # noqa: ANN401 - 임의 모듈
        mod = self.__dict__["_lazy_mod"]
        if mod is None:
            mod = importlib.import_module(self.__dict__["_lazy_name"])
            self.__dict__["_lazy_mod"] = mod
        return mod

    def __getattr__(self, attr: str) -> Any:  # noqa: ANN401
        # __getattr__은 일반 조회 실패 시에만 호출된다 — _lazy_name/_lazy_mod(__dict__)와
        # _resolve(클래스 메서드)는 정상 조회로 찾히므로 여기서 재귀하지 않는다.
        return getattr(self._resolve(), attr)

    def __dir__(self) -> list[str]:
        return dir(self._resolve())

    def __repr__(self) -> str:
        _m = self.__dict__["_lazy_mod"]
        _state = "loaded" if _m is not None else "deferred"
        return f"<LazyModule {self.__dict__['_lazy_name']!r} ({_state})>"
