"""
agent_evaluator.utils.pii_redaction
======================================
SPEC-020: 저장 계층 PII redaction (옵트인).

Gate E의 기존 PII 탐지 패턴(``gates/gate_e_security/evaluators.py::_PII_PATTERNS``)을
그대로 재사용해, ``TaskResult``의 원문 텍스트 필드(``question``/``response``/
``ground_truth``/``context``)를 **저장 시점에만** 마스킹한다. Gate E의 PII 탐지(스코어링)
자체는 원문이 있어야 의미가 있으므로, 이 모듈의 함수는 ``PerformanceMonitor.save_to_file()``
이 만드는 저장용 스냅숏 사본에만 적용해야 한다 — 인메모리 ``self.tasks``에는 절대 적용하지
않는다(SPEC-020 REQ-7).

``_PII_PATTERNS["name"]``(아무 한글 3-4글자 연속 매칭)과 ``["address"]``는 매칭 범위가
넓어 일반 텍스트 상당 부분을 지워버릴 수 있어 :data:`DEFAULT_REDACTION_CATEGORIES`에서
제외한다 — 필요한 사용자만 명시적으로 opt-in할 것.
"""
from __future__ import annotations

import dataclasses
import re

from agent_evaluator.core.trackers.base import TaskResult
from agent_evaluator.gates.gate_e_security.evaluators import _PII_PATTERNS

#: name/address는 매칭 범위가 넓어(일반 텍스트 과잉 매칭 위험) 기본에서 제외한다.
DEFAULT_REDACTION_CATEGORIES: list[str] = [
    category for category in _PII_PATTERNS if category not in ("name", "address")
]

_REDACTED_TEXT_FIELDS = ("question", "response", "ground_truth", "context")


def redact_pii_text(text: str | None, categories: list[str]) -> str | None:
    """``categories``에 해당하는 ``_PII_PATTERNS`` 정규식을 ``text``에서 찾아
    ``[REDACTED:<category>]``로 치환한다.

    Args:
        text: 원문. ``None``/빈 문자열이면 그대로 반환.
        categories: 적용할 PII 카테고리 이름 목록(``_PII_PATTERNS``의 키).

    Returns:
        치환된 텍스트(또는 ``text``가 falsy면 그대로).
    """
    if not text:
        return text
    for category in categories:
        pattern = _PII_PATTERNS.get(category)
        if not pattern:
            continue
        text = re.sub(pattern, f"[REDACTED:{category}]", text)
    return text


def redact_task_pii(task: TaskResult, categories: list[str] | None = None) -> TaskResult:
    """``task``의 원문 텍스트 필드를 redact한 **새** ``TaskResult``를 반환한다.

    ``TaskResult``는 frozen dataclass이므로 ``dataclasses.replace()``로 사본을 만든다 —
    원본 ``task``는 변경되지 않는다. 호출자는 반환값만 저장용으로 사용해야 하며,
    인메모리 태스크 리스트를 이 반환값으로 교체해서는 안 된다(SPEC-020 REQ-7).

    Args:
        task: redact할 원본 ``TaskResult``.
        categories: 적용할 PII 카테고리. ``None``이면 :data:`DEFAULT_REDACTION_CATEGORIES`.

    Returns:
        ``question``/``response``/``ground_truth``/``context``만 redact되고
        나머지 필드는 동일한 새 ``TaskResult``.
    """
    _categories = categories if categories is not None else DEFAULT_REDACTION_CATEGORIES
    _updates = {
        field: redact_pii_text(getattr(task, field), _categories)
        for field in _REDACTED_TEXT_FIELDS
    }
    return dataclasses.replace(task, **_updates)
