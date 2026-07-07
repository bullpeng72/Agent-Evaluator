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
                                             # (SPEC-028 REQ-1: "tool_calls" 키가 있으면
                                             #  꺼내서 TaskResult.tool_calls로 옮기고
                                             #  나머지만 TaskResult.extra에 남긴다 —
                                             #  Gate G(ToolCallAnalyzer)가 실제 도구
                                             #  사용 데이터를 읽을 수 있게 하기 위함)
      "output_dir": str,                    # 기본값 "results/opencode_live_guardrail"
      "storage_backend": "sqlite"|"json",   # 기본값 "sqlite"
      "save_filename": str,                 # 기본값 "opencode_sessions" (확장자는 백엔드가 자동 결정)
      "question": str,                      # 기본값 "<opencode session>"
      "response": str,                       # 기본값 "<opencode session>"
      "execution_time": float,              # 기본값 0.0
      "success": bool | null,               # SPEC-028 REQ-3, 선택 — 실제 완료 판정
                                             # (예: 자동화된 검증 스크립트 결과). 지정
                                             # 시 completion_score/accuracy_score를
                                             # 1.0/0.0으로 명시 반영. 미지정 시
                                             # completion_score=0.5(신호 없음 — 중립,
                                             # placeholder 텍스트 기반 오도 방지).
      "agent_version": str,                 # SPEC-028 REQ-5, 선택. 기본값 "auto"
                                             # (SPEC-027 — git 커밋 SHA + 미커밋 변경
                                             #  해시로 자동 태깅). 다른 태깅 전략을
                                             #  쓰려면 원하는 문자열로 오버라이드.
      "iteration_note": str | null,         # SPEC-029, 선택. 기본값 None. agent_version=
                                             # "auto"가 만드는 dirty-hash 태그에 사람이
                                             # 읽을 수 있는 한 줄 메모를 붙인다(예: "플랜
                                             # 단계를 먼저 세우게 지시문 추가") — 대시보드
                                             # File Compare 탭에서 group_by=agent_version
                                             # 그룹핑 시 함께 렌더링된다.
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
    # SPEC-028 REQ-1: LiveGuardrail.snapshot()이 담아 보낸 "tool_calls"는 다른 Gate B/E
    # 파생 지표(loop_detection 등)와 달리 TaskResult.extra가 아니라 최상위
    # TaskResult.tool_calls로 옮겨야 ToolCallAnalyzer(Gate G tool_coverage)가 읽는다.
    # dict(...)로 복사해 pop이 호출자의 원본 payload를 변형하지 않게 한다.
    extra = dict(payload["extra"])
    tool_calls = extra.pop("tool_calls", [])
    output_dir = payload.get("output_dir", "results/opencode_live_guardrail")
    storage_backend = payload.get("storage_backend", "sqlite")
    # SPEC-028 REQ-5: 기본값 "auto"(SPEC-027) — 커밋 SHA + 미커밋 변경 해시로 자동
    # 태깅해, 커밋 없이 반복 실행되는 로컬 세션도 SPEC-025의 group_by/pairwise 비교
    # 파이프라인에서 자동으로 구분되게 한다. 다른 태깅 전략이 필요하면 오버라이드.
    agent_version = payload.get("agent_version", "auto")
    # SPEC-029: 순수 표시용 메타데이터 — 지정하지 않으면 기존과 동일하게 None.
    iteration_note = payload.get("iteration_note")

    # SPEC-028 REQ-3: success가 주어지면 실제 완료 판정을 반영한다. 주어지지 않으면
    # (기존 호출부 전부 포함) completion_score를 0.5(신호 없음 — 중립값)로 명시
    # override한다. *설계안 대비 수정*: 원 설계는 이 경우 completion_score=None을
    # 계획했으나, TaskResult.__post_init__이 0.0<=completion_score<=1.0을 강제해
    # None을 주면 TypeError로 즉시 크래시한다(직접 실행해 확인). completion_score는
    # Gate A TCR 컴포넌트(`_a_vals[0]`)에 무조건 반영되므로 "not tested"로 만들 방법
    # 자체가 없다 — `response="<opencode session>"` 고정 placeholder가 항상 1.0(완벽)을
    # 만들어내던 것을 0.5(불명 — 성공도 실패도 아님)로 바꿔, 최소한 모든 세션이
    # 획일적으로 "완벽히 성공"으로 보이는 오도는 없앤다.
    success = payload.get("success")
    # success 미지정 시 accuracy_score는 기존처럼 자연 계산값(ground_truth 없음 → 0.0)을
    # 그대로 둔다 — 이미 "측정 불가"를 정직하게 반영하고 있어 별도 override가 필요
    # 없다. success가 주어지면 완료 판정과 일관되게 맞춘다.
    extra_score_fields: Dict[str, Any] = {"completion_score": 0.5}
    if success is not None:
        extra_score_fields = {
            "completion_score": 1.0 if success else 0.0,
            "accuracy_score": 1.0 if success else 0.0,
            "success": bool(success),
        }

    monitor = PerformanceMonitor(
        output_dir=output_dir, storage_backend=storage_backend, agent_version=agent_version,
        iteration_note=iteration_note,
    )
    task = create_taskresult(
        task_id=task_id,
        question=payload.get("question", "<opencode session>"),
        response=payload.get("response", "<opencode session>"),
        execution_time=float(payload.get("execution_time", 0.0)),
        extra=extra,
        tool_calls=tool_calls,
        **extra_score_fields,
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
