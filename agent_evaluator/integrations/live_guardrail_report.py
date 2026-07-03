"""
agent_evaluator.integrations.live_guardrail_report
======================================================
SPEC-019 REQ-6 배치 편입 — ``LiveGuardrail.to_task_extra()``가 만든 ``extra``를 실제
``PerformanceMonitor.record_task()``/``save_to_file()``로 기록하는 1회성 CLI 브리지.

``live_guardrail_stdio.py``(세션 내내 살아있는 요청-응답 루프)와 달리, 이 모듈은
세션 종료 시 **정확히 1회** 실행되는 단발성 프로세스다 — stdin에서 JSON 객체 하나를
읽고, ``record_task()`` + ``save_to_file()``을 실행한 뒤 stdout에 결과(JSON 한 줄)를
쓰고 종료한다.

실행::

    echo '{"task_id": "session-42", "extra": {...}, "output_dir": "results/opencode"}' \\
      | python -m agent_evaluator.integrations.live_guardrail_report

여러 OpenCode 세션(각각 독립 프로세스)이 같은 리포트에 누적돼야 하므로
``storage_backend="sqlite"``(SPEC-016, ``task_id`` 기준 upsert + WAL 동시쓰기)를
기본값으로 쓴다. JSON 백엔드는 매 프로세스가 자신의 메모리에 있는 태스크 1건만으로
파일 전체를 덮어쓰므로(``core/trackers/monitor.py:4810-4816``의 ``_tasks_snapshot``이
그 프로세스의 ``self.tasks``뿐), 서로 다른 프로세스가 같은 파일에 반복 저장하면 이전
세션 기록을 잃는다 — 이 다중 프로세스 유스케이스에는 sqlite 백엔드(업서트)만 안전하다.
``storage_backend="json"``으로 오버라이드할 수는 있지만, 그 경우 파일당 세션 1개로
한정해서 쓸 것(Risks 참조).

입력 스키마(stdin, JSON 한 덩어리)::

    {
      "task_id": str,                       # 필수 — OpenCode 세션 id
      "extra": {...},                       # 필수 — LiveGuardrail.to_task_extra() 결과
      "output_dir": str,                    # 기본값 "results/opencode_live_guardrail"
      "storage_backend": "sqlite"|"json",   # 기본값 "sqlite"
      "save_filename": str,                 # 기본값 "opencode_sessions" (확장자는 백엔드가 자동 결정)
      "question": str,                      # 기본값 "<opencode session>"
      "response": str,                       # 기본값 "<opencode session>"
      "execution_time": float,              # 기본값 0.0
    }

출력(stdout, JSON 한 줄)::

    {"ok": true, "saved_to": "...", "gate_b_score": float|null, "gate_e_score": float|null}
    {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, TextIO

from agent_evaluator import PerformanceMonitor, create_taskresult


def record_and_save(payload: Dict[str, Any]) -> Dict[str, Any]:
    """단일 세션의 ``extra``를 배치 리포트에 편입한다 (SPEC-019 REQ-6).

    Args:
        payload: 위 모듈 docstring의 입력 스키마를 따르는 dict.

    Returns:
        ``{"ok": True, "saved_to": str, "gate_b_score": Optional[float],
        "gate_e_score": Optional[float]}``.

    Raises:
        KeyError: ``task_id``/``extra``가 없을 때.
    """
    task_id = payload["task_id"]
    extra = payload["extra"]
    output_dir = payload.get("output_dir", "results/opencode_live_guardrail")
    storage_backend = payload.get("storage_backend", "sqlite")

    monitor = PerformanceMonitor(output_dir=output_dir, storage_backend=storage_backend)
    task = create_taskresult(
        task_id=task_id,
        question=payload.get("question", "<opencode session>"),
        response=payload.get("response", "<opencode session>"),
        execution_time=float(payload.get("execution_time", 0.0)),
        extra=extra,
    )
    monitor.record_task(task)
    saved_to = monitor.save_to_file(payload.get("save_filename", "opencode_sessions"))

    report = monitor.generate_report()
    harness_groups = report.to_dict().get("extra_metrics", {}).get("harness_groups", {}) or {}
    return {
        "ok": True,
        "saved_to": saved_to,
        "gate_b_score": (harness_groups.get("B") or {}).get("score"),
        "gate_e_score": (harness_groups.get("E") or {}).get("score"),
    }


def run(instream: TextIO = sys.stdin, outstream: TextIO = sys.stdout) -> None:
    """stdin에서 요청 하나를 읽고 stdout에 결과 하나를 쓴 뒤 반환한다.

    호출자(예: OpenCode 플러그인의 one-shot ``opencode run`` 프로세스)가 응답을
    기다리지 않고 먼저 종료해 stdout 파이프가 닫힐 수 있다 — 실제로 확인된 사례
    (2026-07-03, 실 OpenCode 세션 라이브 테스트). 이 시점에는 ``record_and_save()``가
    이미 완료돼 배치 리포트 저장 자체는 끝난 뒤이므로, 응답을 못 전달하는 것 자체는
    데이터 유실이 아니다 — ``BrokenPipeError``를 조용히 무시한다(트레이스백 노이즈 방지).
    """
    raw = instream.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
        if "task_id" not in payload or "extra" not in payload:
            raise ValueError('payload must include both "task_id" and "extra"')
        result = record_and_save(payload)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    try:
        outstream.write(json.dumps(result) + "\n")
        outstream.flush()
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    run()
