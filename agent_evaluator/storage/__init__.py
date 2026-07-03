"""
agent_evaluator.storage
========================
SPEC-016: 영속성 저장소 옵션 — SQLite 백엔드 (JSON 파일 전용의 동시쓰기/규모 한계).

기본 JSON 파일 저장(``PerformanceMonitor(storage_backend="json")``, 기본값)에 대한
옵트인 대안. stdlib ``sqlite3``만 사용해 추가 의존성 없이(Layer independence 원칙 준수)
다중 writer 동시쓰기와 증분(upsert) 쓰기를 지원한다.
"""
from .sqlite_backend import SCHEMA_VERSION, load_tasks_from_db, save_tasks_to_db

__all__ = ["save_tasks_to_db", "load_tasks_from_db", "SCHEMA_VERSION"]
