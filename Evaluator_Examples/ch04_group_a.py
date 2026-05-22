# 기반 코드 — PerformanceMonitor + create_taskresult TCR 패턴 (ch04_group_a.py 기반)
from agent_evaluator import PerformanceMonitor, create_taskresult

monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)

# tool_use: 도구를 사용한 경우만 완전 완료
r1 = create_taskresult(
    task_id="t1",
    question="날씨 검색",
    response="서울 맑음",
    execution_time=1.0,
    task_type="tool_use",
    tool_calls=[{"name": "search", "args": {"query": "서울 날씨"}}],

    use_korean_tokenizer=True,
)
# → completion_score = 1.0 (도구 사용 확인)

r2 = create_taskresult(
    task_id="t2",
    question="날씨 검색",
    response="서울은 보통 맑습니다",
    execution_time=0.5,
    task_type="tool_use",
    tool_calls=[],  # 도구 미사용
    use_korean_tokenizer=True,
)
# → completion_score = 0.6 (실패 — 부분 임계값 0.7 미만)

monitor.record_task(r1)
monitor.record_task(r2)

# 개념 코드 — PerformanceMonitor TCR 결과 접근 패턴
report = monitor.generate_report()
d = report.to_dict()
tcr_data = d.get("accuracy_metrics", {}).get("tcr", {})
total = tcr_data.get("total_tasks", 1) or 1
tcr   = tcr_data.get("tcr", 0.0)
full  = tcr_data.get("full_success", 0)
fail  = tcr_data.get("failures", 0)
print(f"TCR: {tcr:.1f}%")                            # TCR: 80.0%  ← (1.0 + 0.6) / 2 × 100
print(f"완전 성공: {full}/{total} ({full/total*100:.1f}%)")  # 1/2 (50.0%)
print(f"실패: {fail}/{total} ({fail/total*100:.1f}%)")       # 1/2 (50.0%)