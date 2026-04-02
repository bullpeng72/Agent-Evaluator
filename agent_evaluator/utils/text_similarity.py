"""
agent_evaluator.utils.text_similarity
======================================
공통 텍스트 유사도 헬퍼 — LCS, Jaccard, 문자 유사도.

layer1.py / taskresult_helpers.py 양쪽에서 중복 구현되던
LCS 알고리즘을 단일 위치로 통합한다.
"""
from __future__ import annotations


def lcs_ratio(s1: str, s2: str) -> float:
    """LCS 길이 / max(len(s1), len(s2)) — 롤링 2행 DP, O(n) 공간.

    Args:
        s1: 비교 대상 문자열 1.
        s2: 비교 대상 문자열 2.

    Returns:
        0.0–1.0 사이의 LCS 기반 유사도. 둘 다 빈 문자열이면 0.0.

    Example::
        >>> lcs_ratio("서울입니다", "서울")
        0.4
    """
    m, n = len(s1), len(s2)
    if m == 0:
        return 0.0
    # 짧은 쪽을 열(n)로 배치해 메모리 최소화
    if m < n:
        s1, s2 = s2, s1
        m, n = n, m
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n] / m  # m == max(original_m, original_n) after swap
