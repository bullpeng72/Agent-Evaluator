"""
agent_evaluator.ontology
==========================
Phase 2(확장성 인프라) — 여러 코드 위치에 흩어져 있던 진단/추천 지식을 모으는 패키지.

지식 자체(어떤 Gate·지표가 나쁠 때 뭘 제안할지)는 순수 Python 데이터 구조로 관리한다.
YAML이 아니라 Python을 쓰는 이유: PyYAML은 core dependency가 아니고(dev/선택 의존만),
Harness Config가 이미 지키는 "Layer 1/2는 외부 의존성 없이 동작한다" 원칙을
이 레지스트리에도 그대로 적용하기 위해서다.
"""
from __future__ import annotations
