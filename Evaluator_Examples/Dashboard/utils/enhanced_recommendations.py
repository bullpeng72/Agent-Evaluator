"""
Enhanced Recommendations Generator for Advanced Metrics
상세하고 실무적인 개선 권장사항 생성
"""

from typing import Dict, Any, List


def generate_detailed_advanced_recommendations(advanced_summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Generate detailed, actionable recommendations based on advanced metrics

    Each recommendation includes:
    - area: 개선 영역
    - title: 구체적인 문제 제목
    - priority: high/medium/low
    - issue: 상세한 현재 문제점 (🔍)
    - suggestion: 5가지 구체적 개선 방안 (💡)
    - impact: 정량적 예상 효과 (📈)
    """
    recommendations = []

    if not advanced_summary:
        return recommendations

    # ============================================================================
    # DeepEval G-Eval Score (전반적 품질)
    # ============================================================================
    if 'g_eval_score' in advanced_summary and isinstance(advanced_summary['g_eval_score'], dict):
        g_eval = advanced_summary['g_eval_score']['mean']
        if g_eval < 0.7:
            gap = 0.7 - g_eval
            recommendations.append({
                "area": "G-Eval 품질 개선",
                "title": f"전반적 응답 품질이 기준치 대비 {gap:.2f}점 부족 (G-Eval)",
                "priority": "high" if g_eval < 0.5 else "medium",
                "issue": f"현재 G-Eval 점수 {g_eval:.2f} (권장: 0.7 이상). G-Eval은 응답의 일관성(Coherence), 관련성(Relevance), 유창성(Fluency), 일관성(Consistency)을 종합 평가하는 지표로, 낮은 점수는 응답이 사용자 기대에 미치지 못함을 의미합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **평가 기준 명확화 및 정렬**:
   - G-Eval의 4가지 평가 차원(일관성, 관련성, 유창성, 일관성)을 프롬프트에 명시
   - 각 차원별 체크리스트를 응답 생성 전에 제시
   - 예: "응답은 논리적으로 일관되어야 하며, 질문과 직접 관련되어야 하고..."
2. **구조화된 응답 템플릿 적용**:
   - 서론(질문 재진술) → 본론(핵심 답변) → 결론(요약) 구조 강제
   - 각 섹션별 목적을 프롬프트에 명시
   - Markdown 헤더나 번호 매기기로 구조 시각화
3. **프롬프트 체인 구현**:
   - 1단계: 질문 분석 및 핵심 포인트 추출
   - 2단계: 각 포인트에 대한 답변 생성
   - 3단계: 전체 일관성 검증 및 재작성
4. **Few-shot 예시 강화**:
   - 높은 G-Eval 점수를 받은 응답 3-5개를 프롬프트에 포함
   - "좋은 예시"와 "나쁜 예시"를 대조하여 제시
5. **자기 평가 단계 추가**:
   - LLM이 응답 생성 후 4가지 차원으로 자기 평가
   - 7점 미만 차원에 대해 재작성 수행""",
                "impact": f"""**예상 개선 효과:**
• G-Eval 0.7 달성 시 응답 품질 전반적으로 {(0.7-g_eval)/g_eval*100:.0f}% 향상
• 사용자 만족도 조사 점수 0.5-1.0점 상승 (5점 만점)
• 재질문 및 명확화 요청 30-40% 감소
• 응답당 평균 편집/재작성 시간 {(0.7-g_eval)*10:.0f}분 절약
• 고품질 응답 비율 50% → 70%+ 증가"""
            })

    # ============================================================================
    # Hallucination Score (환각 감소 - 컨텍스트 충실도)
    # ============================================================================
    if 'hallucination_score' in advanced_summary and isinstance(advanced_summary['hallucination_score'], dict):
        hall_score = advanced_summary['hallucination_score']['mean']
        if hall_score < 0.7:
            gap = 0.7 - hall_score
            recommendations.append({
                "area": "환각 감소 (컨텍스트 충실도 향상)",
                "title": f"컨텍스트 충실도가 기준치 대비 {gap:.2f}점 부족",
                "priority": "high",  # Hallucination은 항상 high priority
                "issue": f"현재 환각 없음 점수 {hall_score:.2f} (권장: 0.7 이상). 낮은 점수는 모델이 제공된 컨텍스트를 벗어나 사실이 아닌 정보를 생성하고 있음을 의미합니다. 이는 사용자 신뢰도를 심각하게 저하시키고 잘못된 의사결정으로 이어질 수 있습니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **Temperature 및 Sampling 최적화**:
   - Temperature 0.7 → 0.3으로 낮춰 창의성보다 정확성 우선
   - Top-P를 0.95 → 0.8로 낮춰 확률 높은 토큰만 선택
   - Frequency Penalty 0.2 적용하여 반복 패턴 억제
2. **컨텍스트 강화 및 명시**:
   - 시스템 프롬프트에 "제공된 컨텍스트에만 기반하여 답변하세요" 명시
   - 컨텍스트를 XML 태그나 구분선으로 명확히 표시
   - 컨텍스트에 없는 정보는 "제공된 정보에 없습니다"라고 답변하도록 지시
3. **사실 확인(Fact-Checking) 단계 추가**:
   - 응답 생성 후 각 주장을 컨텍스트와 대조 검증
   - 인용 구절 추가: "문서에 따르면 '[인용]'..."
   - 불일치 발견 시 해당 부분 제거 또는 재작성
4. **RAG 검색 품질 개선** (RAG 시스템인 경우):
   - 검색 Top-K를 5 → 10으로 증가하여 더 많은 컨텍스트 제공
   - Hybrid 검색: 키워드 검색 + 의미 검색 결합
   - Re-ranking 모델 추가로 가장 관련 높은 컨텍스트 우선 배치
5. **응답 검증 모델 도입**:
   - 별도의 경량 모델로 "응답이 컨텍스트에 근거하는가?" 검증
   - 검증 실패 시 재생성 또는 경고 표시
   - NLI(Natural Language Inference) 모델 활용""",
                "impact": f"""**예상 개선 효과:**
• 환각 없음 점수 0.7 달성 시 사실 오류 {(0.7-hall_score)/hall_score*100:.0f}% 감소
• 사용자 신뢰도 회복: 현재 {hall_score*100:.0f}% → 목표 70%+ 신뢰 수준
• 법적/비즈니스 리스크 크게 감소 (잘못된 정보로 인한 손실 방지)
• 사실 확인 및 수정에 소요되는 인력 주당 15-20시간 절감
• 고객 불만 및 환불 요청 {(0.7-hall_score)*50:.0f}% 감소"""
            })

    # ============================================================================
    # Toxicity Score (독성 콘텐츠 감소)
    # ============================================================================
    if 'toxicity_score' in advanced_summary and isinstance(advanced_summary['toxicity_score'], dict):
        tox_score = advanced_summary['toxicity_score']['mean']
        if tox_score > 0.3:
            excess = tox_score - 0.3
            recommendations.append({
                "area": "독성 콘텐츠 감소",
                "title": f"독성 콘텐츠 비율이 기준치 대비 {excess:.2f}점 초과",
                "priority": "high",  # Toxicity는 항상 high priority (안전 문제)
                "issue": f"현재 평균 독성 점수 {tox_score:.2f} (권장: 0.3 이하). 응답에 공격적, 모욕적, 혐오적 표현이 포함되어 있어 사용자 경험을 해치고 브랜드 이미지에 부정적 영향을 미칠 수 있습니다. 특히 공개 서비스의 경우 법적 문제로 이어질 위험도 있습니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **Safety System Message 강화**:
   - 시스템 프롬프트에 안전 가이드라인 명시
   - "항상 존중하고 중립적인 톤을 유지하세요. 공격적이거나 모욕적인 표현을 절대 사용하지 마세요."
   - 민감한 주제(정치, 종교, 인종 등)에 대한 특별 지침 추가
2. **출력 필터링 시스템 구축**:
   - OpenAI Moderation API 또는 Perspective API 통합
   - 응답 생성 후 독성 점수 체크 (임계값: 0.3)
   - 임계값 초과 시 자동 차단 및 대체 응답 생성
3. **콘텐츠 검수 프로세스 도입**:
   - 높은 위험도 응답(민감 주제)은 인간 검수 거치기
   - 주간 단위로 독성 점수 높은 응답 샘플링 검토
   - 문제 패턴 발견 시 프롬프트 업데이트
4. **부정적 Few-shot 예시 제거**:
   - 프롬프트에 포함된 예시 중 공격적 표현 검토 및 제거
   - 긍정적이고 건설적인 대안 표현 예시로 교체
5. **사용자 피드백 루프 구축**:
   - "이 응답이 부적절했나요?" 버튼 추가
   - 신고된 응답은 즉시 분석 및 프롬프트 개선에 활용
   - 반복 문제 발생 시 자동 알림""",
                "impact": f"""**예상 개선 효과:**
• 독성 점수 0.3 달성 시 부적절한 응답 {(tox_score-0.3)/tox_score*100:.0f}% 감소
• 사용자 불만 및 서비스 중단 요청 70-80% 감소
• 브랜드 평판 및 신뢰도 회복 (부정적 리뷰 감소)
• 법적 리스크 및 규제 위반 가능성 대폭 감소
• 안전한 서비스로 인한 사용자 유지율 10-15% 향상"""
            })

    # ============================================================================
    # Bias Score (편향 감소)
    # ============================================================================
    if 'bias_score' in advanced_summary and isinstance(advanced_summary['bias_score'], dict):
        bias_score = advanced_summary['bias_score']['mean']
        if bias_score > 0.3:
            excess = bias_score - 0.3
            recommendations.append({
                "area": "편향 감소",
                "title": f"응답 편향이 기준치 대비 {excess:.2f}점 초과",
                "priority": "high" if bias_score > 0.5 else "medium",
                "issue": f"현재 평균 편향 점수 {bias_score:.2f} (권장: 0.3 이하). 응답에 성별, 인종, 연령, 종교 등에 대한 편향이 감지되어 특정 그룹에 대한 불공정한 대우나 고정관념을 강화할 수 있습니다. 이는 다양한 사용자층에게 부정적 경험을 제공하고 사회적 책임을 저버리는 것입니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **공정성 가이드라인 적용**:
   - 시스템 프롬프트에 "모든 답변은 성별, 인종, 연령, 종교, 장애 여부 등에 관계없이 공정해야 합니다" 명시
   - 편향된 가정을 피하고 중립적 언어 사용 지시
   - 예: "그 사람은..." (성별 중립) vs "그는..." (남성 가정)
2. **다양한 예제 데이터 사용**:
   - Few-shot 예시에 다양한 배경의 인물 포함
   - 직업, 역할 설명 시 성별 고정관념 탈피 (간호사=여성 X)
   - 다양한 문화권과 관점을 반영한 예시 선택
3. **편향 제거 프롬프트 기법**:
   - "다양한 관점을 고려하여 균형 잡힌 답변을 제공하세요"
   - 민감한 주제의 경우 여러 시각을 제시하고 판단은 사용자에게 맡기기
   - 단정적 표현 대신 "~할 수 있습니다", "~경향이 있습니다" 등 완화 표현 사용
4. **편향 탐지 도구 통합**:
   - IBM AI Fairness 360, Microsoft Fairlearn 등 편향 탐지 라이브러리 활용
   - 정기적으로 응답 샘플을 편향 분석 도구로 검사
   - 패턴 발견 시 프롬프트 및 훈련 데이터 보완
5. **다양성 팀 리뷰**:
   - 다양한 배경의 팀원이 응답 품질 리뷰
   - 월간 편향 리포트 생성 및 개선 방향 논의
   - 사용자 피드백 중 편향 관련 의견 우선 처리""",
                "impact": f"""**예상 개선 효과:**
• 편향 점수 0.3 달성 시 불공정한 응답 {(bias_score-0.3)/bias_score*100:.0f}% 감소
• 다양한 사용자층의 만족도 균등화 (특정 그룹의 낮은 만족도 개선)
• 사회적 책임 이행으로 기업 이미지 향상
• 차별 관련 법적 리스크 및 소송 가능성 감소
• 포용적 서비스로 인한 사용자 기반 10-20% 확대"""
            })

    # ============================================================================
    # Answer Relevancy (답변 관련성)
    # ============================================================================
    if 'answer_relevancy_score' in advanced_summary and isinstance(advanced_summary['answer_relevancy_score'], dict):
        relevancy = advanced_summary['answer_relevancy_score']['mean']
        if relevancy < 0.7:
            gap = 0.7 - relevancy
            recommendations.append({
                "area": "답변 관련성 개선",
                "title": f"답변 관련성이 기준치 대비 {gap:.2f}점 부족",
                "priority": "high" if relevancy < 0.5 else "medium",
                "issue": f"현재 평균 답변 관련성 {relevancy:.2f} (권장: 0.7 이상). 응답이 질문과 직접적으로 관련되지 않거나 불필요한 정보가 많이 포함되어 사용자가 원하는 답을 찾기 어렵습니다. 이는 사용자 시간 낭비와 불만족으로 이어집니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **질문 분석 강화**:
   - 질문에서 핵심 키워드 추출 (명사, 동사, 의문사)
   - 질문 유형 분류 (사실 질문, 방법 질문, 이유 질문 등)
   - 프롬프트에 "질문은 '[키워드]'에 대해 묻고 있습니다" 명시
2. **불필요한 정보 제거**:
   - 응답 후 "이 내용이 질문에 직접 답변하는가?" 자기 검증
   - 배경 설명은 최소화하고 핵심 답변 우선
   - 응답 길이를 질문 복잡도에 비례하도록 조절 (간단한 질문 → 짧은 답변)
3. **답변 포커스 개선**:
   - 첫 문장에서 질문에 직접 답변 (예: "네, 가능합니다" / "그 이유는...")
   - 질문의 모든 부분에 답변했는지 체크리스트 확인
   - 다단계 질문의 경우 각 부분을 명시적으로 구분하여 답변
4. **프롬프트 구조화**:
   - "질문: [사용자 질문]" 섹션을 명확히 표시
   - "답변은 질문에 직접 관련된 정보만 포함해야 합니다" 지시
   - 예시: "질문이 '어떻게'를 묻는다면 단계별 방법을 제시하세요"
5. **관련성 점수 모니터링**:
   - 응답 생성 후 BERTScore 또는 의미 유사도로 질문-응답 관련성 측정
   - 점수 0.7 미만 시 재생성 또는 경고 표시
   - 관련성 낮은 응답 패턴 분석 및 프롬프트 개선""",
                "impact": f"""**예상 개선 효과:**
• 답변 관련성 0.7 달성 시 재질문 및 명확화 요청 40-50% 감소
• 사용자가 원하는 정보 찾는 시간 평균 30초 → 10초로 단축
• 세션당 상호작용 횟수 감소 (효율성 향상)
• 사용자 만족도 {(0.7-relevancy)*100:.0f}% 향상
• 고객 지원 문의 "답변이 도움이 안 되었어요" 유형 60% 감소"""
            })

    # ============================================================================
    # RAGAS Faithfulness (RAG 충실도)
    # ============================================================================
    if 'ragas_faithfulness' in advanced_summary and isinstance(advanced_summary['ragas_faithfulness'], dict):
        faithfulness = advanced_summary['ragas_faithfulness']['mean']
        if faithfulness < 0.7:
            gap = 0.7 - faithfulness
            recommendations.append({
                "area": "RAG 충실도 개선",
                "title": f"RAG 시스템의 컨텍스트 충실도가 기준치 대비 {gap:.2f}점 부족",
                "priority": "high",
                "issue": f"현재 평균 충실도 {faithfulness:.2f} (권장: 0.7 이상). RAG 시스템에서 검색된 문서(컨텍스트)에 충실하지 않고 모델이 자체적으로 정보를 생성하고 있습니다. 이는 RAG의 핵심 목적인 '신뢰할 수 있는 소스 기반 답변'을 훼손합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **컨텍스트 사용 강제**:
   - 프롬프트에 "반드시 아래 제공된 문서에서만 정보를 추출하여 답변하세요" 명시
   - "문서에 없는 정보는 '제공된 문서에서 해당 정보를 찾을 수 없습니다'라고 답변하세요"
   - XML 태그로 컨텍스트 명확히 구분: `<context>...</context>`
2. **인용(Citation) 추가**:
   - 각 주장마다 인용 구절 추가: "문서에 따르면, '[정확한 인용]'..."
   - 인용 번호 시스템 도입: "첫 번째 문서[1]에서..."
   - 인용 없는 주장 발견 시 자동 제거
3. **주장 검증 단계 추가**:
   - 응답 생성 후 각 문장을 컨텍스트와 대조
   - NLI 모델로 "문장이 컨텍스트에 의해 뒷받침되는가?" 검증
   - 뒷받침되지 않는 문장은 삭제 또는 재작성
4. **RAG 검색 품질 개선**:
   - 검색된 청크가 질문에 실제로 답변하는지 Relevance Score 확인
   - 낮은 relevance 청크 제거 (노이즈 감소)
   - Top-K를 동적으로 조정 (간단한 질문: 3개, 복잡한 질문: 10개)
5. **응답 형식 제한**:
   - "컨텍스트에서 추출한 정보만 사용" 반복 강조
   - Temperature 0.3 이하로 낮춰 창의성 억제
   - Extractive QA 모델 병행 사용하여 직접 추출된 답변과 비교""",
                "impact": f"""**예상 개선 효과:**
• 충실도 0.7 달성 시 컨텍스트 기반 정확도 {(0.7-faithfulness)/faithfulness*100:.0f}% 향상
• RAG 시스템의 신뢰성 회복 (사용자가 소스 문서 확인 가능)
• 환각으로 인한 사실 오류 70-80% 감소
• 법적 문서, 의료 정보 등 중요 도메인에서 안전성 대폭 향상
• 정보 검증에 소요되는 시간 주당 10-15시간 절감"""
            })

    # ============================================================================
    # RAGAS Context Precision (컨텍스트 정밀도)
    # ============================================================================
    if 'ragas_context_precision' in advanced_summary and isinstance(advanced_summary['ragas_context_precision'], dict):
        precision = advanced_summary['ragas_context_precision']['mean']
        if precision < 0.7:
            gap = 0.7 - precision
            recommendations.append({
                "area": "RAG 컨텍스트 정밀도 개선",
                "title": f"검색된 컨텍스트의 정밀도가 기준치 대비 {gap:.2f}점 부족",
                "priority": "medium",
                "issue": f"현재 평균 컨텍스트 정밀도 {precision:.2f} (권장: 0.7 이상). 검색된 문서에 불필요한 정보(노이즈)가 많이 포함되어 있어 LLM이 핵심 정보를 찾기 어렵고, 처리 시간과 토큰 비용이 증가합니다. 높은 노이즈는 응답 품질도 저하시킵니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **검색 쿼리 최적화**:
   - 질문에서 핵심 키워드만 추출하여 검색 (불용어 제거)
   - HyDE(Hypothetical Document Embeddings): 이상적 답변을 먼저 생성하고 그것으로 검색
   - 쿼리 확장: 동의어, 관련 용어 추가하여 더 정확한 매칭
2. **Re-ranking 모델 추가**:
   - Cohere Rerank, bge-reranker 등 re-ranking 모델 도입
   - 1차 검색(Top-20) → Re-ranking → 최종 Top-5 선택
   - 질문과 청크 간 Cross-Encoder로 정확한 관련성 계산
3. **메타데이터 필터링**:
   - 문서 메타데이터(날짜, 카테고리, 태그)로 검색 범위 사전 필터링
   - 예: "2023년 이후 재무 문서"만 검색
   - 사용자 컨텍스트 활용 (권한, 부서, 선호도)
4. **하이브리드 검색 구현**:
   - 키워드 검색(BM25) + 의미 검색(임베딩) 결합
   - 가중 평균: 키워드 30% + 의미 70%
   - 정확한 용어 매칭이 중요한 도메인(법률, 기술)에 효과적
5. **청킹 전략 개선**:
   - 고정 크기(512 토큰) → 의미 단위(문단, 섹션) 청킹
   - Overlap 100 토큰 추가하여 경계 정보 손실 방지
   - 계층적 청킹: 문서 요약 + 상세 청크""",
                "impact": f"""**예상 개선 효과:**
• 정밀도 0.7 달성 시 불필요한 컨텍스트 {(0.7-precision)/precision*100:.0f}% 제거
• 입력 토큰 20-30% 감소로 월간 비용 수백 달러 절감
• LLM 처리 시간 15-25% 단축 (컨텍스트 길이 감소)
• 응답 정확도 향상 (노이즈로 인한 혼란 감소)
• RAG 파이프라인 전체 효율 30% 향상"""
            })

    # ============================================================================
    # RAGAS Context Recall (컨텍스트 재현율)
    # ============================================================================
    if 'ragas_context_recall' in advanced_summary and isinstance(advanced_summary['ragas_context_recall'], dict):
        recall = advanced_summary['ragas_context_recall']['mean']
        if recall < 0.7:
            gap = 0.7 - recall
            recommendations.append({
                "area": "RAG 컨텍스트 재현율 개선",
                "title": f"검색된 컨텍스트의 재현율이 기준치 대비 {gap:.2f}점 부족",
                "priority": "high" if recall < 0.5 else "medium",
                "issue": f"현재 평균 컨텍스트 재현율 {recall:.2f} (권장: 0.7 이상). 질문에 답변하는 데 필요한 정보를 충분히 검색하지 못하고 있습니다. 이는 불완전한 답변으로 이어지며, RAG 시스템이 지식 베이스의 정보를 제대로 활용하지 못함을 의미합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **Top-K 증가**:
   - 검색 결과 Top-5 → Top-10으로 증가
   - 복잡한 질문의 경우 Top-15까지 검색
   - 동적 Top-K: 질문 복잡도에 따라 자동 조정
2. **하이브리드 검색(키워드 + 의미 검색) 구현**:
   - BM25(키워드) + Dense Retrieval(임베딩) 결합
   - 키워드 검색으로 정확한 용어 매칭, 의미 검색으로 문맥 이해
   - 가중 평균으로 최종 점수 계산
3. **쿼리 확장(Query Expansion)**:
   - 원본 질문 + 동의어 + 관련 용어로 검색
   - LLM을 사용하여 "이 질문에 답하기 위해 찾아야 할 정보는?" 생성 후 검색
   - Multi-query: 하나의 질문을 3-5개의 다른 표현으로 변환하여 각각 검색
4. **임베딩 모델 업그레이드**:
   - OpenAI text-embedding-ada-002 → text-embedding-3-large
   - Cohere embed-v3, Voyage AI 등 최신 모델 고려
   - 도메인 특화 임베딩 모델 파인튜닝
5. **멀티 인덱스 검색**:
   - 전체 문서 인덱스 + 요약 인덱스 병행 검색
   - 다양한 청크 크기의 인덱스 생성 (256, 512, 1024 토큰)
   - 모든 인덱스에서 검색 후 중복 제거 및 병합""",
                "impact": f"""**예상 개선 효과:**
• 재현율 0.7 달성 시 필요 정보 검색 완전성 {(0.7-recall)/recall*100:.0f}% 향상
• 불완전한 답변으로 인한 재질문 50-60% 감소
• 답변 완성도 및 세부성 대폭 향상
• 지식 베이스 활용률 현재 {recall*100:.0f}% → 70%+ 증가
• 복잡한 질문에 대한 답변 성공률 30-40% 향상"""
            })

    # ============================================================================
    # RAGAS Answer Relevancy (RAG 답변 관련성)
    # ============================================================================
    if 'ragas_answer_relevancy' in advanced_summary and isinstance(advanced_summary['ragas_answer_relevancy'], dict):
        ragas_relevancy = advanced_summary['ragas_answer_relevancy']['mean']
        if ragas_relevancy < 0.7:
            gap = 0.7 - ragas_relevancy
            recommendations.append({
                "area": "RAG 답변 관련성 개선",
                "title": f"RAG 시스템의 답변 관련성이 기준치 대비 {gap:.2f}점 부족",
                "priority": "high" if ragas_relevancy < 0.5 else "medium",
                "issue": f"현재 평균 RAGAS 답변 관련성 {ragas_relevancy:.2f} (권장: 0.7 이상). RAG 시스템에서 검색된 컨텍스트가 있음에도 불구하고 답변이 질문과 직접 관련되지 않습니다. 검색과 생성 단계 간의 정렬이 부족하여 컨텍스트를 제대로 활용하지 못하고 있습니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **질문 이해 개선**:
   - 질문 분해: 복잡한 질문을 여러 하위 질문으로 분할
   - 질문 유형 분류: 사실, 비교, 절차, 이유 등
   - 프롬프트에 "이 질문은 [유형]이므로 [형식]으로 답변하세요" 명시
2. **검색-생성 정렬 강화**:
   - 검색된 각 문서에 대해 "이 문서가 질문에 어떻게 도움이 되는가?" 메타 정보 추가
   - 프롬프트: "제공된 문서를 사용하여 '[질문]'에 직접 답변하세요"
   - 검색 결과와 질문의 키워드 매칭 강조
3. **프롬프트에 질문 재강조**:
   - 프롬프트 구조: 질문 → 컨텍스트 → 다시 질문 반복
   - "질문에 직접 관련된 정보만 사용하고, 관련 없는 정보는 무시하세요"
   - 답변 첫 문장에서 질문을 직접 언급하도록 지시
4. **답변 형식 가이드**:
   - 질문 유형별 답변 템플릿 제공
   - 예: "비교 질문 → 표 형식 또는 항목별 비교"
   - 예: "절차 질문 → 단계별 번호 매기기"
5. **관련성 검증 단계 추가**:
   - 답변 생성 후 "이 답변이 '[질문]'에 직접 답변하는가?" 자기 평가
   - BERTScore로 질문-답변 의미 유사도 측정
   - 낮은 유사도 시 재생성""",
                "impact": f"""**예상 개선 효과:**
• RAGAS 답변 관련성 0.7 달성 시 질문-답변 일치도 {(0.7-ragas_relevancy)/ragas_relevancy*100:.0f}% 향상
• RAG 시스템의 실용성 대폭 개선 (컨텍스트를 제대로 활용)
• 사용자 재질문 "답변이 질문과 맞지 않아요" 유형 60% 감소
• RAG 투자 대비 효과(ROI) 향상 (검색 비용을 답변 품질로 전환)
• 복잡한 질문에 대한 사용자 만족도 40% 향상"""
            })

    # ============================================================================
    # RAGAS Overall Score (RAG 종합 점수)
    # ============================================================================
    if 'ragas_overall_score' in advanced_summary and isinstance(advanced_summary['ragas_overall_score'], dict):
        overall = advanced_summary['ragas_overall_score']['mean']
        if overall < 0.6:
            gap = 0.6 - overall
            recommendations.append({
                "area": "RAG 시스템 전반 개선",
                "title": f"RAG 종합 성능이 기준치 대비 {gap:.2f}점 부족",
                "priority": "high",
                "issue": f"현재 RAGAS 종합 점수 {overall:.2f} (권장: 0.6 이상). RAG 파이프라인의 전반적인 성능이 낮아 검색-생성-평가의 전 단계에서 개선이 필요합니다. 이는 RAG 시스템의 근본적인 설계나 구성에 문제가 있을 수 있음을 시사합니다.",
                "suggestion": f"""**즉시 실행 가능한 개선 방안:**
1. **RAG 파이프라인 전체 재검토**:
   - 데이터 수집 → 전처리 → 청킹 → 임베딩 → 검색 → 생성 → 평가의 각 단계 점검
   - 병목 구간 식별: RAGAS의 하위 메트릭(Faithfulness, Precision, Recall, Relevancy) 중 가장 낮은 점수 우선 개선
   - End-to-end 테스트 케이스 구축 및 정기 평가
2. **임베딩 모델 업그레이드**:
   - 현재 모델 (예: text-embedding-ada-002) → 최신 모델 (text-embedding-3-large, Cohere embed-v3)
   - 도메인 특화 모델 고려: 의료 → BioBERT, 법률 → Legal-BERT
   - 임베딩 차원 증가 (768 → 1024 or 1536)
3. **청킹 전략 최적화**:
   - 고정 크기 청킹 → 의미 기반 청킹 (문단, 섹션 단위)
   - 청크 크기 실험: 256 vs 512 vs 1024 토큰 (도메인별 최적값 찾기)
   - Overlap 설정: 100-200 토큰으로 문맥 연속성 보장
   - 계층적 청킹: 문서 요약(작은 청크) + 상세 내용(큰 청크)
4. **벡터 DB 및 인덱싱 개선**:
   - HNSW, IVF 등 고성능 인덱스 알고리즘 사용
   - 메타데이터 인덱싱으로 사전 필터링 성능 향상
   - 주기적인 인덱스 재구축 및 최적화
5. **프롬프트 엔지니어링 전략**:
   - RAG 전용 프롬프트 템플릿 설계
   - 컨텍스트 사용 방법, 인용 규칙, 답변 형식 명시
   - Few-shot 예시: 좋은 RAG 응답 3-5개 포함""",
                "impact": f"""**예상 개선 효과:**
• RAGAS 종합 점수 0.6 달성 시 RAG 시스템 전반 성능 {(0.6-overall)/overall*100:.0f}% 향상
• 검색 정확도, 답변 품질, 신뢰성이 모두 균형 있게 개선
• RAG 시스템 ROI 대폭 증가 (투자 비용 대비 가치 향상)
• 지식 기반 서비스의 경쟁력 확보
• 연간 수만 건의 질의에 대한 자동화된 고품질 답변 제공"""
            })

    return recommendations
