"""
GoldenSetBuilder — Phase 3-A 운영 데이터 기반 골든셋 자동 확장.

운영 결과 파일에서 케이스를 자동 추출하여 골든 데이터셋으로 확장한다.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SUPPORTED_STRATEGIES = frozenset({
    "failure_cases", "edge_cases", "high_value", "coverage_gap"
})


class GoldenSetBuilder:
    """운영 데이터 기반 골든셋 자동 확장기.

    Args:
        source_dir: 결과 JSON 파일 디렉토리.
        output_dir: 골든셋 출력 디렉토리.

    Example::
        builder = GoldenSetBuilder(
            source_dir="results/daily/",
            output_dir="data/golden_datasets/",
        )
        candidates = builder.extract(
            strategies=["failure_cases", "edge_cases"],
            max_cases=50,
        )
        builder.save_candidates(candidates)
    """

    def __init__(self, source_dir: str, output_dir: str) -> None:
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)

    def _load_tasks(self) -> List[Dict[str, Any]]:
        """source_dir의 모든 JSON 파일에서 태스크 목록 로드."""
        tasks = []
        for p in sorted(self.source_dir.glob("*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                for task in data.get("tasks", []):
                    task["_source_file"] = p.name
                    tasks.append(task)
            except Exception:
                continue
        return tasks

    def _load_existing_golden(self) -> List[Dict[str, Any]]:
        """기존 골든셋의 task_id 목록 수집 (중복 방지)."""
        existing = []
        for p in self.output_dir.glob("*.json"):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    existing.extend(data)
                elif isinstance(data, dict):
                    existing.extend(data.get("items", []))
            except Exception:
                continue
        return existing

    def extract(
        self,
        strategies: List[str],
        max_cases: int = 50,
        require_human_review: bool = True,
        min_question_length: int = 10,
    ) -> List[Dict[str, Any]]:
        """전략에 따라 골든셋 후보 케이스를 추출한다.

        Args:
            strategies: 추출 전략 목록. 지원: failure_cases, edge_cases, high_value, coverage_gap.
            max_cases: 최대 추출 케이스 수. Default 50.
            require_human_review: 사람 검토 필요 여부 플래그. Default True.
            min_question_length: 질문 최소 길이. Default 10.

        Returns:
            추출된 후보 케이스 딕셔너리 목록.

        Raises:
            ValueError: 지원하지 않는 전략이 포함된 경우.
        """
        unsupported = set(strategies) - _SUPPORTED_STRATEGIES
        if unsupported:
            raise ValueError(f"Unsupported strategies: {unsupported}. Use: {_SUPPORTED_STRATEGIES}")

        tasks = self._load_tasks()
        existing_ids = {t.get("task_id") for t in self._load_existing_golden()}

        # 기존 골든셋에 없는 태스크만 필터
        tasks = [t for t in tasks if t.get("task_id") not in existing_ids]

        candidates: List[Dict[str, Any]] = []

        for strategy in strategies:
            extracted = self._apply_strategy(strategy, tasks, min_question_length)
            for e in extracted:
                e["_strategy"] = strategy
                e["_requires_review"] = require_human_review
                e["_extracted_at"] = datetime.now().isoformat()
                candidates.append(e)

        # 중복 task_id 제거
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for c in candidates:
            tid = c.get("task_id")
            if tid not in seen:
                seen.add(tid)
                unique.append(c)

        # max_cases 제한
        return unique[:max_cases]

    def _apply_strategy(self, strategy: str, tasks: List[Dict[str, Any]], min_q_len: int) -> List[Dict[str, Any]]:
        if strategy == "failure_cases":
            return [t for t in tasks if not t.get("success", True)
                    and len(str(t.get("question", t.get("task_id", "")))) >= min_q_len]

        if strategy == "edge_cases":
            # 이상치: completion_score == 0 or == 1, 응답 길이 극단값
            result = []
            for t in tasks:
                score = t.get("completion_score", -1)
                if score == 0.0 or score == 1.0:
                    result.append(t)
            return result

        if strategy == "high_value":
            # 긍정 피드백 또는 높은 accuracy_score
            return [t for t in tasks
                    if t.get("accuracy_score", 0) >= 0.9 or t.get("completion_score", 0) >= 0.95]

        if strategy == "coverage_gap":
            # 태스크 유형 분포 중 적은 유형 우선
            type_counts: Counter = Counter(t.get("task_type", "unknown") for t in tasks)
            min_count = min(type_counts.values()) if type_counts else 0
            rare_types = {k for k, v in type_counts.items() if v <= min_count + 2}
            return [t for t in tasks if t.get("task_type") in rare_types]

        return []

    def save_candidates(self, candidates: List[Dict[str, Any]], filename: str = "candidates.json") -> Path:
        """후보 케이스를 파일에 저장."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2, default=str)
        return path

    def merge_to_golden(
        self,
        cases: List[Dict[str, Any]],
        version: str = "latest",
        output_name: Optional[str] = None,
    ) -> Path:
        """후보 케이스를 골든셋으로 병합 저장.

        Args:
            cases: 골든셋에 추가할 케이스 목록.
            version: 버전 태그 (예: "v2.1").
            output_name: 출력 파일명. None이면 자동 생성.

        Returns:
            저장된 골든셋 파일 경로.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if output_name is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"golden_{version}_{ts}.json"

        path = self.output_dir / output_name
        dataset = {
            "version": version,
            "created_at": datetime.now().isoformat(),
            "count": len(cases),
            "items": cases,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2, default=str)
        return path
