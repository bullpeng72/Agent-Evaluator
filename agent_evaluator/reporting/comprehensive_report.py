"""
Comprehensive HTML Report Generator for Agent Evaluator
Designed for AI Agent Developers and Quality Managers
"""
from datetime import datetime
import re


def markdown_to_html(text: str) -> str:
    """Convert simple markdown formatting to HTML with support for nested lists"""
    if not text:
        return ""

    # Escape HTML special characters first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Remove colon immediately after </strong> tag for better readability
    text = re.sub(r'</strong>:', '</strong>', text)

    # Process line by line
    lines = text.split('\n')
    in_numbered_list = False
    in_bullet_list = False
    result_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check for numbered list item (1. 2. 3.)
        if re.match(r'^\d+\.\s+', stripped):
            # Close any open bullet list before starting new numbered item
            if in_bullet_list:
                result_lines.append('</ul>')
                in_bullet_list = False

            # Close previous numbered list item if exists
            if in_numbered_list:
                result_lines.append('</li>')

            # Start numbered list if not already started
            if not in_numbered_list:
                result_lines.append('<ol style="margin: 10px 0 10px 20px; line-height: 2.0;">')
                in_numbered_list = True

            # Start new list item - remove trailing colon for better readability
            content = re.sub(r'^\d+\.\s+', '', stripped)
            # Remove trailing colon if present
            content = re.sub(r':$', '', content)
            # Content already has <strong> tags from markdown conversion, don't add more
            result_lines.append(f'<li>{content}')

        # Check for bullet list item (starts with -)
        elif re.match(r'^\s*-\s+', line):
            # We're inside a numbered list item, add nested bullet list
            if in_numbered_list:
                if not in_bullet_list:
                    # Start nested bullet list without extra line break
                    result_lines.append('<ul style="margin: 5px 0 5px 20px; line-height: 1.8;">')
                    in_bullet_list = True

                content = re.sub(r'^\s*-\s+', '', line.strip())
                result_lines.append(f'<li>{content}</li>')

        # Regular text line
        else:
            if stripped:
                # If we're inside a numbered list item, add to current item
                if in_numbered_list and not in_bullet_list:
                    # Check if this might be a continuation line (indented)
                    if line.startswith('   ') or line.startswith('\t'):
                        result_lines.append(f'<br>{stripped}')
                    else:
                        # Not indented - might be header or regular text
                        # Close any open lists and add as paragraph
                        if in_bullet_list:
                            result_lines.append('</ul>')
                            in_bullet_list = False
                        if in_numbered_list:
                            result_lines.append('</li>')
                            result_lines.append('</ol>')
                            in_numbered_list = False
                        result_lines.append(f'<p style="margin: 10px 0; line-height: 1.8;">{stripped}</p>')
                else:
                    # Regular paragraph
                    if in_bullet_list:
                        result_lines.append('</ul>')
                        in_bullet_list = False
                    if in_numbered_list:
                        result_lines.append('</li>')
                        result_lines.append('</ol>')
                        in_numbered_list = False
                    result_lines.append(f'<p style="margin: 10px 0; line-height: 1.8;">{stripped}</p>')
            else:
                # Empty line - keep as spacing unless inside list
                if not in_numbered_list and not in_bullet_list:
                    result_lines.append('<br>')

    # Close any remaining open lists
    if in_bullet_list:
        result_lines.append('</ul>')
    if in_numbered_list:
        result_lines.append('</li>')
        result_lines.append('</ol>')

    return '\n'.join(result_lines)


def _build_css_and_head() -> str:
    """Build the CSS stylesheet and HTML DOCTYPE/head section."""
    parts = []
    parts.append('''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Evaluator - 종합 평가 리포트</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; background: #f5f5f5; color: #333; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 40px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; border-radius: 10px; margin-bottom: 40px; }
        .header h1 { font-size: 36px; margin-bottom: 10px; }
        .header .subtitle { font-size: 14px; opacity: 0.9; margin-top: 10px; }

        .section { margin-bottom: 40px; padding: 30px; background: #f8f9fa; border-radius: 10px; border-left: 5px solid #667eea; }
        .section h2 { color: #2c3e50; margin-bottom: 20px; font-size: 24px; display: flex; align-items: center; }
        .section h2 .icon { margin-right: 10px; }
        .section h3 { color: #34495e; margin: 25px 0 15px 0; font-size: 18px; padding-bottom: 10px; border-bottom: 2px solid #ecf0f1; }
        .section h4 { color: #555; margin: 20px 0 10px 0; font-size: 16px; }

        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }
        .metric-card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #3498db; transition: transform 0.2s; }
        .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
        .metric-card h3 { margin: 0 0 10px 0; color: #7f8c8d; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
        .metric-card .value { font-size: 32px; font-weight: bold; color: #2c3e50; }
        .metric-card .subtitle { font-size: 12px; color: #95a5a6; margin-top: 5px; }

        .status-good { border-left-color: #27ae60; }
        .status-warning { border-left-color: #f39c12; }
        .status-critical { border-left-color: #e74c3c; }

        table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
        th, td { padding: 15px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #667eea; color: white; font-weight: 600; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #e9ecef; }

        .insight-box { background: white; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #3498db; }
        .insight-box.warning { border-left-color: #f39c12; background: #fffbf0; }
        .insight-box.critical { border-left-color: #e74c3c; background: #fff5f5; }
        .insight-box.success { border-left-color: #27ae60; background: #f0fff4; }
        .insight-box h4 { margin: 0 0 10px 0; color: #2c3e50; }
        .insight-box p { margin: 5px 0; line-height: 1.8; }
        .insight-box ul { margin: 10px 0 10px 20px; }
        .insight-box li { margin: 5px 0; }

        .recommendation { background: white; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #3498db; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .recommendation strong { color: #2980b9; display: block; margin-bottom: 8px; font-size: 16px; }
        .recommendation p { line-height: 1.8; color: #555; }

        .priority-high { border-left-color: #e74c3c; }
        .priority-medium { border-left-color: #f39c12; }
        .priority-low { border-left-color: #3498db; }

        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-danger { background: #f8d7da; color: #721c24; }

        .footer { margin-top: 60px; padding-top: 30px; border-top: 2px solid #ecf0f1; text-align: center; color: #95a5a6; font-size: 12px; }
        .footer p { margin: 5px 0; }

        .toc { background: white; padding: 20px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .toc h3 { color: #2c3e50; margin-bottom: 15px; }
        .toc ul { list-style: none; }
        .toc li { padding: 8px 0; border-bottom: 1px solid #ecf0f1; }
        .toc a { color: #3498db; text-decoration: none; }
        .toc a:hover { text-decoration: underline; }

        @media print {
            .container { padding: 20px; }
            .metric-card, .section { break-inside: avoid; }
        }
    </style>
</head>
<body>
    <div class="container">''')
    return ''.join(parts)


def _build_header_toc(total_tasks, success_rate, tcr, acc, latency) -> str:
    """Build the header div and table of contents."""
    parts = []
    parts.append(f'''
        <div class="header">
            <h1>📊 Agent Evaluator 종합 평가 리포트</h1>
            <div class="subtitle">AI Agent 개발자 및 품질 관리자를 위한 상세 성능 분석 보고서</div>
            <div style="margin-top: 15px;"><p><strong>생성일시:</strong> {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}</p>
                <p><strong>평가 대상:</strong> {total_tasks}개 Task</p>
                <p><strong>평가 버전:</strong> Agent Evaluator v0.5.0</p>
            </div>
        </div>

        <!-- Table of Contents -->
        <div class="toc">
            <h3>📑 목차</h3>
            <ul>
                <li><a href="#summary">1. 핵심 요약 (Executive Summary)</a></li>
                <li><a href="#core">2. 🎯 Core Metrics - 작업 완료도 및 정확성</a></li>
                <li><a href="#performance">3. ⚡ Performance - 실행 효율성 및 리소스</a></li>
                <li><a href="#agentic">4. 🤖 Agentic AI - 도구 사용 및 협업</a></li>
                <li><a href="#advanced">5. 🔬 Advanced Metrics - 외부 라이브러리 평가</a></li>
                <li><a href="#security">6. 🔒 Security - 보안 지표 (Layer 1 & 2)</a></li>
                <li><a href="#insights">7. 💡 Insights - 주요 인사이트 및 알림</a></li>
                <li><a href="#transparency">8. 🔍 Test 투명성 - 평가 프로세스 투명성</a></li>
                <li><a href="#recommendations">9. 개선 권장사항 (Recommendations)</a></li>
                <li><a href="#conclusion">10. 결론 및 다음 단계 (Conclusion)</a></li>
            </ul>
        </div>

        <!-- Executive Summary -->
        <div class="section" id="summary">
            <h2><span class="icon">📋</span>핵심 요약 (Executive Summary)</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                본 리포트는 총 <strong>{total_tasks}개</strong>의 Task를 평가한 결과입니다.
                전체 성공률은 <strong>{success_rate:.1f}%</strong>이며, 작업 완료율(TCR)은 <strong>{tcr:.1f}%</strong>를 기록했습니다.
            </p>
            <div class="metrics-grid">''')

    # Status badges for KPIs
    success_badge = 'badge-success' if success_rate >= 90 else 'badge-warning' if success_rate >= 75 else 'badge-danger'
    tcr_badge = 'badge-success' if tcr >= 90 else 'badge-warning' if tcr >= 75 else 'badge-danger'
    acc_badge = 'badge-success' if acc >= 85 else 'badge-warning' if acc >= 70 else 'badge-danger'
    latency_badge = 'badge-success' if latency <= 3.0 else 'badge-warning' if latency <= 5.0 else 'badge-danger'

    parts.append(f'''
                <div class="metric-card">
                    <h3>성공률</h3>
                    <div class="value">{success_rate:.1f}%</div>
                    <div class="subtitle"><span class="{success_badge}">{'우수' if success_rate >= 90 else '양호' if success_rate >= 75 else '개선 필요'}</span></div>
                </div>
                <div class="metric-card">
                    <h3>작업 완료율 (TCR)</h3>
                    <div class="value">{tcr:.1f}%</div>
                    <div class="subtitle"><span class="{tcr_badge}">{'우수' if tcr >= 90 else '양호' if tcr >= 75 else '개선 필요'}</span></div>
                </div>
                <div class="metric-card">
                    <h3>정확도</h3>
                    <div class="value">{acc:.1f}%</div>
                    <div class="subtitle"><span class="{acc_badge}">{'우수' if acc >= 85 else '양호' if acc >= 70 else '개선 필요'}</span></div>
                </div>
                <div class="metric-card">
                    <h3>평균 응답 시간</h3>
                    <div class="value">{latency:.2f}s</div>
                    <div class="subtitle"><span class="{latency_badge}">{'빠름' if latency <= 3.0 else '보통' if latency <= 5.0 else '느림'}</span></div>
                </div>
            </div>
        </div>''')

    return ''.join(parts)


def _build_core_section(tcr, success_rate, acc, accuracy_metrics, quality_metrics, hallucination_data) -> str:
    """Build the Core Metrics section (TCR, accuracy, quality, hallucination)."""
    parts = []

    parts.append(f'''
        <!-- Core Metrics Section -->
        <div class="section" id="core">
            <h2><span class="icon">🎯</span>Core Metrics - 작업 완료도 및 정확성</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                Core Metrics는 <strong>"What was achieved"</strong> (무엇을 달성했는가)를 측정합니다.
                작업 완료율, 정확도, 품질, 환각 탐지 등 AI Agent의 기본적인 성능을 평가합니다.
            </p>

            <h3>작업 완료율 (Task Completion Rate - TCR)</h3>''')

    parts.append(f'''
            <div class="insight-box {'success' if tcr >= 90 else 'warning' if tcr >= 75 else 'critical'}">
                <h4>TCR 요약</h4>
                <p><strong>작업 완료율:</strong> {tcr:.1f}%</p>
                <p><strong>성공률:</strong> {success_rate:.1f}%</p>
                <p><strong>벤치마크 등급:</strong> {'S등급 (Outstanding)' if tcr >= 95 else 'A등급 (Excellent)' if tcr >= 90 else 'B등급 (Good)' if tcr >= 80 else 'C등급 (Fair)' if tcr >= 70 else 'D등급 (Poor)'}</p>
            </div>

            <h3>정확도 (Accuracy)</h3>''')

    parts.append(f'''
            <div class="insight-box {'success' if acc >= 85 else 'warning' if acc >= 70 else 'critical'}">
                <h4>정확도 요약</h4>
                <p><strong>전체 정확도:</strong> {acc:.1f}%</p>
                <p><strong>높은 정확도 (≥90%):</strong> {accuracy_metrics.get('high_accuracy_count', 0)}개</p>
                <p><strong>낮은 정확도 (<70%):</strong> {accuracy_metrics.get('low_accuracy_count', 0)}개</p>
                <p><strong>평균 정확도:</strong> {accuracy_metrics.get('overall_accuracy', 0):.1f}%</p>
            </div>

            <h3>응답 품질 분석 (Quality Analysis)</h3>''')

    # Detailed Quality metrics
    if quality_metrics.get('total_evaluated', 0) > 0:
        avg_score = quality_metrics.get('avg_total_score', 0)
        quality_status = '우수' if avg_score >= 4.5 else '양호' if avg_score >= 4.0 else '개선 필요'
        quality_class = 'success' if avg_score >= 4.5 else 'warning' if avg_score >= 4.0 else 'critical'

        parts.append(f'''
            <div class="insight-box {quality_class}">
                <h4>품질 평가 요약</h4>
                <p><strong>평가 상태:</strong> {quality_status}</p>
                <p><strong>평가된 응답:</strong> {quality_metrics.get('total_evaluated', 0)}개</p>
                <p><strong>평균 품질 점수:</strong> {avg_score:.2f}/5.0</p>
                <p><strong>고품질 응답 (A/B등급):</strong> {quality_metrics.get('high_quality_count', 0)}개 ({quality_metrics.get('high_quality_count', 0) / quality_metrics.get('total_evaluated', 1) * 100:.1f}%)</p>
            </div>

            <h4>차원별 점수 상세</h4>
            <table>
                <thead>
                    <tr>
                        <th>평가 차원</th>
                        <th>평균 점수</th>
                        <th>가중치</th>
                        <th>설명</th>
                        <th>개발자 가이드</th>
                    </tr>
                </thead>
                <tbody>''')

        dimensions = [
            ('relevance', 'Relevance (관련성)', '25%', '질문과 답변의 연관성', '프롬프트 엔지니어링으로 질문 의도 파악 강화'),
            ('completeness', 'Completeness (완전성)', '25%', '필요한 정보의 포함 여부', '필수 요소 체크리스트 추가 및 검증 로직 구현'),
            ('accuracy', 'Accuracy (정확성)', '20%', '사실적 정확도', 'RAG 컨텍스트 품질 개선 및 환각 탐지 강화'),
            ('clarity', 'Clarity (명확성)', '15%', '이해하기 쉬운 정도', '구조화된 응답 포맷 사용 및 단계별 설명 추가'),
            ('usefulness', 'Usefulness (유용성)', '15%', '실용적 가치', '사용자 피드백 반영 및 실행 가능한 답변 생성')
        ]

        dim_scores = quality_metrics.get('dimension_scores', {})
        for dim_key, dim_name, weight, desc, guide in dimensions:
            score = dim_scores.get(dim_key, 0)
            score_badge = 'badge-success' if score >= 4.5 else 'badge-warning' if score >= 4.0 else 'badge-danger'
            parts.append(f'''
                    <tr>
                        <td><strong>{dim_name}</strong></td>
                        <td><span class="{score_badge}">{score:.2f}/5.0</span></td>
                        <td>{weight}</td>
                        <td>{desc}</td>
                        <td style="font-size: 12px; color: #555;">{guide}</td>
                    </tr>''')

        parts.append('''
                </tbody>
            </table>

            <h4>등급 분포</h4>
            <table>
                <thead>
                    <tr>
                        <th>등급</th>
                        <th>응답 수</th>
                        <th>비율</th>
                        <th>평가</th>
                    </tr>
                </thead>
                <tbody>''')

        grade_dist = quality_metrics.get('grade_distribution', {})
        grade_order = ['A', 'B', 'C', 'D', 'F']
        for grade in grade_order:
            count = grade_dist.get(grade, 0)
            if count > 0:
                percentage = count / quality_metrics.get('total_evaluated', 1) * 100
                grade_eval = '우수' if grade in ['A', 'B'] else '보통' if grade == 'C' else '개선 필요'
                parts.append(f'''
                    <tr>
                        <td><strong>{grade}</strong></td>
                        <td>{count}개</td>
                        <td>{percentage:.1f}%</td>
                        <td>{grade_eval}</td>
                    </tr>''')

        parts.append('</tbody></table>')

    # Hallucination Detection
    parts.append('<h3>환각 탐지 (Hallucination Detection)</h3>')
    hall_rate = hallucination_data.get('overall_rate', 0)  # Define with default value
    if hallucination_data.get('total_evaluated', 0) > 0:
        hall_rate = hallucination_data.get('overall_rate', 0)
        hall_status = '안전' if hall_rate < 5 else '주의' if hall_rate < 10 else '위험'
        hall_class = 'success' if hall_rate < 5 else 'warning' if hall_rate < 10 else 'critical'

        parts.append(f'''
            <div class="insight-box {hall_class}">
                <h4>환각 탐지 요약</h4>
                <p><strong>탐지 상태:</strong> {hall_status}</p>
                <p><strong>전체 환각률:</strong> {hall_rate:.1f}%</p>
                <p><strong>검사된 응답:</strong> {hallucination_data.get('total_evaluated', 0)}개</p>
                <p><strong>환각 탐지:</strong> {hallucination_data.get('total_flagged', 0)}개</p>
                <p><strong>정상 응답:</strong> {hallucination_data.get('total_evaluated', 0) - hallucination_data.get('total_flagged', 0)}개</p>
            </div>

            <h4>환각 유형별 분석</h4>
            <table>
                <thead>
                    <tr>
                        <th>환각 유형</th>
                        <th>발생 횟수</th>
                        <th>심각도</th>
                        <th>설명</th>
                        <th>개발자 조치사항</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>지원되지 않는 주장</strong></td>
                        <td>{hallucination_data.get('unsupported_claims_count', 0)}개</td>
                        <td><span class="badge-warning">중간</span></td>
                        <td>제공된 컨텍스트에서 지원되지 않는 정보</td>
                        <td style="font-size: 12px;">RAG 검색 품질 개선, 컨텍스트 윈도우 확장</td>
                    </tr>
                    <tr>
                        <td><strong>숫자 불일치</strong></td>
                        <td>{hallucination_data.get('numerical_inconsistencies_count', 0)}개</td>
                        <td><span class="badge-danger">높음</span></td>
                        <td>컨텍스트와 다른 숫자 정보</td>
                        <td style="font-size: 12px;">숫자 추출 후 컨텍스트 대조 검증, 계산 로직 추가</td>
                    </tr>
                </tbody>
            </table>''')

    parts.append('</div>')
    return ''.join(parts)


def _build_performance_section(latency, latency_stats, token_stats, retry_metrics) -> str:
    """Build the Performance section (latency, tokens, retry)."""
    parts = []

    parts.append(f'''
        <div class="section" id="performance">
            <h2><span class="icon">⚡</span>Performance - 실행 효율성 및 리소스</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                Performance Metrics는 <strong>"How efficiently"</strong> (얼마나 효율적으로)를 측정합니다.
                응답 시간, 비용, 재시도 효율성 등 실행 효율성과 리소스 사용을 평가합니다.
            </p>

            <h3>응답 시간 분석 (Latency)</h3>''')

    if latency_stats:
        p95 = latency_stats.get('p95', 0)
        median = latency_stats.get('median', 0)
        max_latency = latency_stats.get('max', 0)

        latency_insight_class = 'success' if latency <= 3.0 else 'warning' if latency <= 5.0 else 'critical'

        parts.append(f'''
            <div class="insight-box {latency_insight_class}">
                <h4>응답 시간 요약</h4>
                <p><strong>평균:</strong> {latency:.2f}초</p>
                <p><strong>중앙값:</strong> {median:.2f}초</p>
                <p><strong>P95:</strong> {p95:.2f}초 (95%의 요청이 이 시간 내에 완료)</p>
                <p><strong>최대:</strong> {max_latency:.2f}초</p>
            </div>

            <h4>개발자 최적화 가이드</h4>
            <ul style="margin: 15px 0 15px 20px; line-height: 2.0;">''')

        if latency > 5.0:
            parts.append('''
                <li><strong>프롬프트 최적화:</strong> 불필요한 지시사항 제거, 간결한 프롬프트 작성</li>
                <li><strong>모델 선택:</strong> 더 빠른 모델 (예: GPT-3.5-turbo) 사용 고려</li>
                <li><strong>병렬 처리:</strong> 독립적인 작업은 병렬로 실행</li>
                <li><strong>캐싱:</strong> 반복적인 질의에 대한 응답 캐싱 구현</li>''')
        elif latency > 3.0:
            parts.append('''
                <li><strong>프롬프트 간소화:</strong> 예시 수 줄이기, 핵심 지시사항만 포함</li>
                <li><strong>토큰 최적화:</strong> 출력 토큰 수 제한 (max_tokens 설정)</li>''')
        else:
            parts.append('''
                <li>✅ 응답 시간이 우수합니다. 현재 최적화 수준을 유지하세요.</li>''')

        parts.append('</ul>')

    # Token and Cost Analysis
    total_cost = token_stats.get('total_cost', 0)
    avg_cost_per_task = token_stats.get('avg_cost_per_task', 0)
    cost_insight_class = 'success' if avg_cost_per_task <= 0.01 else 'warning' if avg_cost_per_task <= 0.05 else 'critical'

    parts.append(f'''
            <h3>토큰 & 비용 분석 (Token & Cost)</h3>
            <div class="insight-box {cost_insight_class}">
                <h4>비용 요약</h4>
                <p><strong>총 비용:</strong> ${total_cost:.4f}</p>
                <p><strong>Task당 평균 비용:</strong> ${avg_cost_per_task:.4f}</p>
                <p><strong>총 토큰 사용량:</strong> {token_stats.get('total_tokens', 0):,} tokens</p>
                <p><strong>Task당 평균 토큰:</strong> {token_stats.get('avg_tokens_per_task', 0):,.0f} tokens</p>
            </div>

            <h4>토큰 사용 내역</h4>
            <table>
                <thead>
                    <tr>
                        <th>구분</th>
                        <th>토큰 수</th>
                        <th>비율</th>
                        <th>최적화 포인트</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>입력 토큰</strong></td>
                        <td>{token_stats.get('total_input_tokens', 0):,}</td>
                        <td>{token_stats.get('total_input_tokens', 0) / max(token_stats.get('total_tokens', 0), 1) * 100:.1f}%</td>
                        <td>프롬프트 간소화, 컨텍스트 최적화</td>
                    </tr>
                    <tr>
                        <td><strong>출력 토큰</strong></td>
                        <td>{token_stats.get('total_output_tokens', 0):,}</td>
                        <td>{token_stats.get('total_output_tokens', 0) / max(token_stats.get('total_tokens', 0), 1) * 100:.1f}%</td>
                        <td>max_tokens 설정, 응답 길이 제한</td>
                    </tr>
                    <tr>
                        <td><strong>총계</strong></td>
                        <td><strong>{token_stats.get('total_tokens', 0):,}</strong></td>
                        <td><strong>100.0%</strong></td>
                        <td>전반적인 효율성 모니터링</td>
                    </tr>
                </tbody>
            </table>

            <h3>재시도 성공률 (Retry Success Rate)</h3>''')

    # Add Retry Success details
    if retry_metrics and retry_metrics.get('total_tasks_with_retries', 0) > 0:
        retry_rate = retry_metrics.get('retry_rate', 0)
        eventual_success = retry_metrics.get('eventual_success_rate', 0)
        first_attempt_success = retry_metrics.get('first_attempt_success_rate', 0)
        avg_attempts = retry_metrics.get('avg_attempts_per_task', 0)
        retry_success_count = retry_metrics.get('retry_success_count', 0)

        retry_class = 'success' if eventual_success >= 80 and retry_rate < 30 else 'warning'

        parts.append(f'''
            <div class="insight-box {retry_class}">
                <h4>재시도 요약</h4>
                <p><strong>재시도율:</strong> {retry_rate:.1f}%</p>
                <p><strong>1차 시도 성공률:</strong> {first_attempt_success:.1f}%</p>
                <p><strong>최종 성공률:</strong> {eventual_success:.1f}%</p>
                <p><strong>개선도:</strong> +{eventual_success - first_attempt_success:.1f}%p (재시도로 구제한 Task: {retry_success_count}개)</p>
                <p><strong>평균 시도 횟수:</strong> {avg_attempts:.2f}회</p>
            </div>

            <h4>재시도 효과 분석</h4>
            <table>
                <thead>
                    <tr>
                        <th>지표</th>
                        <th>값</th>
                        <th>목표</th>
                        <th>상태</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>재시도율</strong></td>
                        <td>{retry_rate:.1f}%</td>
                        <td>&lt; 30%</td>
                        <td><span class="{'badge-success' if retry_rate < 30 else 'badge-warning'}">{'적정' if retry_rate < 30 else '높음'}</span></td>
                    </tr>
                    <tr>
                        <td><strong>최종 성공률</strong></td>
                        <td>{eventual_success:.1f}%</td>
                        <td>≥ 80%</td>
                        <td><span class="{'badge-success' if eventual_success >= 80 else 'badge-danger'}">{'우수' if eventual_success >= 80 else '개선 필요'}</span></td>
                    </tr>
                    <tr>
                        <td><strong>평균 시도 횟수</strong></td>
                        <td>{avg_attempts:.2f}회</td>
                        <td>&lt; 3회</td>
                        <td><span class="{'badge-success' if avg_attempts < 3 else 'badge-warning'}">{'적정' if avg_attempts < 3 else '많음'}</span></td>
                    </tr>
                </tbody>
            </table>

            <h4>재시도 최적화 가이드</h4>
            <ul style="margin: 15px 0 15px 20px; line-height: 2.0;">''')

        if retry_rate > 30:
            parts.append('''
                <li><strong>재시도율 감소:</strong> 1차 시도 성공률을 높이기 위해 입력 검증 강화 및 프롬프트 품질 개선</li>''')

        if eventual_success < 80:
            parts.append('''
                <li><strong>재시도 로직 개선:</strong> 실패 원인을 분석하여 타겟 개선, 더 나은 에러 복구 전략 필요</li>''')

        if avg_attempts > 3:
            parts.append('''
                <li><strong>재시도 한계 조정:</strong> 평균 시도 횟수가 많음, 재시도 한계 설정 검토 및 빠른 실패 전략 고려</li>''')

        if eventual_success >= 80 and retry_rate < 30:
            parts.append('''
                <li>✅ 재시도 메커니즘이 효과적으로 작동하고 있습니다. 현재 수준을 유지하세요.</li>''')

        parts.append('</ul>')
    else:
        parts.append('''
            <p>재시도 데이터가 없습니다. Task 실패 시 재시도 메커니즘이 활성화되면 여기에서 재시도 효율성 지표를 확인할 수 있습니다.</p>''')

    parts.append('''
        </div>''')

    return ''.join(parts)


def _build_agentic_section(monitor, tool_selection_stats, coordination_stats, workflow_stats, retry_metrics) -> str:
    """Build the Agentic section (tool selection, efficiency, coordination, workflow, retry patterns, security-in-agentic)."""
    parts = []

    parts.append('''
        <!-- Agentic AI Section -->
        <div class="section" id="agentic">
            <h2><span class="icon">🤖</span>Agentic AI - 도구 사용 및 협업</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                Agentic AI Metrics는 AI Agent의 <strong>도구 사용 능력 및 협업 품질</strong>을 측정합니다.
                도구 선택 정확도, 도구 실행 효율성, 다중 에이전트 협업, 워크플로우 실행을 평가합니다.
            </p>

            <h3>도구 선택 정확도 (Tool Selection Accuracy)</h3>''')

    if tool_selection_stats and tool_selection_stats.get('total_tasks', 0) > 0:
        tool_acc = tool_selection_stats.get('overall_accuracy', 0) * 100
        tool_class = 'success' if tool_acc >= 85 else 'warning' if tool_acc >= 70 else 'critical'

        parts.append(f'''
            <div class="insight-box {tool_class}">
                <h4>도구 선택 요약</h4>
                <p><strong>전체 정확도:</strong> {tool_acc:.1f}%</p>
                <p><strong>평가된 Task:</strong> {tool_selection_stats.get('total_tasks', 0)}개</p>
                <p><strong>올바른 도구 선택:</strong> {tool_selection_stats.get('correct_selections', 0)}개</p>
            </div>''')

    # Tool Efficiency
    parts.append('<h3>도구 실행 효율성 (Tool Efficiency)</h3>')
    tool_efficiency_stats = monitor.tool_analyzer.get_efficiency_stats()

    if tool_efficiency_stats and tool_efficiency_stats.get('total_calls', 0) > 0:
        efficiency_score = tool_efficiency_stats.get('avg_efficiency_score', 0)
        success_rate = tool_efficiency_stats.get('success_rate', 0)
        redundancy_rate = tool_efficiency_stats.get('redundancy_rate', 0)

        efficiency_class = 'success' if efficiency_score >= 80 else 'warning' if efficiency_score >= 60 else 'critical'

        parts.append(f'''
            <div class="insight-box {efficiency_class}">
                <h4>도구 효율성 요약</h4>
                <p><strong>전체 효율성 점수:</strong> {efficiency_score:.1f}%</p>
                <p><strong>도구 호출 성공률:</strong> {success_rate:.1f}%</p>
                <p><strong>중복 호출률:</strong> {redundancy_rate:.1f}%</p>
                <p><strong>총 도구 호출:</strong> {tool_efficiency_stats.get('total_calls', 0)}회</p>
                <p><strong>성공한 호출:</strong> {tool_efficiency_stats.get('total_calls', 0) - tool_efficiency_stats.get('total_failed_calls', 0)}회</p>
            </div>

            <h4>도구별 실행 통계</h4>''')

        # Get per-tool breakdown if available
        if hasattr(monitor.tool_analyzer, 'executions') and monitor.tool_analyzer.executions:
            tool_breakdown = {}
            for execution in monitor.tool_analyzer.executions:
                for call in execution.get('tool_calls', []):
                    tool_name = call.get('tool_name', 'Unknown')
                    if tool_name not in tool_breakdown:
                        tool_breakdown[tool_name] = {'success': 0, 'failure': 0, 'total': 0, 'total_duration': 0}

                    tool_breakdown[tool_name]['total'] += 1
                    if call.get('success', False):
                        tool_breakdown[tool_name]['success'] += 1
                    else:
                        tool_breakdown[tool_name]['failure'] += 1

                    if 'duration' in call:
                        tool_breakdown[tool_name]['total_duration'] += call['duration']

            if tool_breakdown:
                parts.append('''
            <table>
                <thead>
                    <tr>
                        <th>도구명</th>
                        <th>총 호출</th>
                        <th>성공</th>
                        <th>실패</th>
                        <th>성공률</th>
                        <th>평균 실행 시간</th>
                    </tr>
                </thead>
                <tbody>''')

                for tool_name, stats in sorted(tool_breakdown.items(), key=lambda x: x[1]['total'], reverse=True):
                    tool_success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
                    avg_duration = (stats['total_duration'] / stats['total']) if stats['total'] > 0 else 0
                    success_badge = 'badge-success' if tool_success_rate >= 90 else 'badge-warning' if tool_success_rate >= 70 else 'badge-danger'

                    parts.append(f'''
                    <tr>
                        <td><strong>{tool_name}</strong></td>
                        <td>{stats['total']}회</td>
                        <td>{stats['success']}회</td>
                        <td>{stats['failure']}회</td>
                        <td><span class="{success_badge}">{tool_success_rate:.1f}%</span></td>
                        <td>{avg_duration:.3f}초</td>
                    </tr>''')

                parts.append('</tbody></table>')

        # Add optimization guide
        parts.append('''
            <h4>도구 효율성 최적화 가이드</h4>
            <ul style="margin: 15px 0 15px 20px; line-height: 2.0;">''')

        if success_rate < 90:
            parts.append('''
                <li><strong>성공률 개선:</strong> 실패한 도구 호출의 원인 분석, 입력 검증 강화, 에러 핸들링 개선</li>''')

        if redundancy_rate > 20:
            parts.append('''
                <li><strong>중복 제거:</strong> 불필요한 중복 호출 감소, 캐싱 메커니즘 도입, 도구 선택 로직 최적화</li>''')

        if efficiency_score >= 80:
            parts.append('''
                <li>✅ 도구 실행 효율성이 우수합니다. 현재 수준을 유지하세요.</li>''')

        parts.append('</ul>')
    else:
        parts.append('''
            <p>도구 효율성 데이터가 없습니다. AI Agent가 도구를 사용하면 여기에서 실행 효율성 지표를 확인할 수 있습니다.</p>''')

    # Multi-Agent Coordination
    parts.append('<h3>다중 에이전트 협업 (Multi-Agent Coordination)</h3>')
    if coordination_stats and coordination_stats.get('total_interactions', 0) > 0:
        # CRITICAL FIX: Use 'score' not 'overall_score', and score is 0-10 scale (multiply by 10 for percentage, not 100)
        coord_score = coordination_stats.get('score', 0) * 10
        coord_class = 'success' if coord_score >= 85 else 'warning' if coord_score >= 70 else 'critical'

        parts.append(f'''
            <div class="insight-box {coord_class}">
                <h4>협업 요약</h4>
                <p><strong>협업 점수:</strong> {coord_score:.1f}%</p>
                <p><strong>총 상호작용:</strong> {coordination_stats.get('total_interactions', 0)}개</p>
                <p><strong>성공적인 상호작용:</strong> {coordination_stats.get('successful_interactions', 0)}개</p>
            </div>''')

    # Workflow Execution
    parts.append('<h3>워크플로우 실행 (Workflow Execution)</h3>')
    if workflow_stats and workflow_stats.get('total_workflows', 0) > 0:
        # CRITICAL FIX: Use 'step_success_rate' not 'success_rate', and it's already a percentage (don't multiply by 100)
        workflow_rate = workflow_stats.get('step_success_rate', 0)
        workflow_class = 'success' if workflow_rate >= 85 else 'warning' if workflow_rate >= 70 else 'critical'

        parts.append(f'''
            <div class="insight-box {workflow_class}">
                <h4>워크플로우 요약</h4>
                <p><strong>성공률:</strong> {workflow_rate:.1f}%</p>
                <p><strong>총 워크플로우:</strong> {workflow_stats.get('total_workflows', 0)}개</p>
                <p><strong>성공:</strong> {workflow_stats.get('successful_workflows', 0)}개</p>
            </div>''')

    # Retry Patterns
    parts.append('<h3>재시도 패턴 (Retry Patterns)</h3>')
    if retry_metrics and retry_metrics.get('total_tasks_with_retries', 0) > 0:
        retry_rate = retry_metrics.get('retry_rate', 0)
        # CRITICAL FIX: Use 'eventual_success_rate' not 'final_success_rate'
        final_success = retry_metrics.get('eventual_success_rate', 0)

        parts.append(f'''
            <div class="insight-box">
                <h4>재시도 요약</h4>
                <p><strong>재시도율:</strong> {retry_rate:.1f}%</p>
                <p><strong>재시도 후 최종 성공률:</strong> {final_success:.1f}%</p>
                <p><strong>재시도 발생 Task:</strong> {retry_metrics.get('total_tasks_with_retries', 0)}개</p>
                <p><strong>평균 재시도 횟수:</strong> {retry_metrics.get('avg_attempts_per_task', 0):.2f}회</p>
            </div>

            <h4>개발자 가이드</h4>
            <ul style="margin: 15px 0 15px 20px; line-height: 2.0;">
                <li><strong>재시도 로직 최적화:</strong> 실패 원인 분석 후 타겟 개선</li>
                <li><strong>에러 핸들링:</strong> 명확한 에러 메시지와 복구 전략</li>
                <li><strong>Fallback 전략:</strong> 재시도 실패 시 대안 제공</li>
            </ul>''')

    # 🔒 Security Metrics Section
    parts.append('''
        <h3 style="color: #e74c3c; margin-top: 30px;">🔒 보안 메트릭 (Security Metrics)</h3>
        <p style="color: #555; margin-bottom: 20px;">
            AI Agent의 보안 위험을 실시간으로 모니터링합니다.
            <code>enable_security_metrics=True</code>로 활성화하면 입력 위협, 출력 유출, 권한 관리를 자동 검사합니다.
        </p>''')

    # Check if security metrics are available
    has_security_metrics = (
        hasattr(monitor, 'input_sanitizer') and
        hasattr(monitor, 'output_leakage_detector') and
        hasattr(monitor, 'tool_authorizer')
    )

    if has_security_metrics:
        # Input Sanitization Stats
        try:
            input_stats = monitor.input_sanitizer.get_sanitization_stats()
            if input_stats.get('total_inputs_evaluated', 0) > 0:
                threat_rate = input_stats.get('threat_rate', 0)
                critical_count = input_stats.get('critical_risk_inputs', 0)
                high_count = input_stats.get('high_risk_inputs', 0)

                threat_class = 'critical' if threat_rate > 10 else 'warning' if threat_rate > 5 else 'success'

                parts.append(f'''
            <div class="insight-box {threat_class}">
                <h4>🛡️ 입력 살균 (Input Sanitization)</h4>
                <p><strong>위협 탐지율:</strong> {threat_rate:.1f}%</p>
                <p><strong>검사한 입력:</strong> {input_stats.get('total_inputs_evaluated', 0)}개</p>
                <p><strong>위협 유형:</strong></p>
                <ul style="margin: 5px 0 0 20px;">
                    <li>SQL Injection: {input_stats.get('sql_injection_attempts', 0)}건</li>
                    <li>Command Injection: {input_stats.get('command_injection_attempts', 0)}건</li>
                    <li>XSS: {input_stats.get('xss_attempts', 0)}건</li>
                    <li>Path Traversal: {input_stats.get('path_traversal_attempts', 0)}건</li>
                    <li>Prompt Injection: {input_stats.get('prompt_injection_attempts', 0)}건</li>
                </ul>
                <p style="margin-top: 10px;"><strong>위험 수준:</strong></p>
                <ul style="margin: 5px 0 0 20px;">
                    <li>🔴 Critical: {critical_count}건</li>
                    <li>🟠 High: {high_count}건</li>
                </ul>
            </div>''')
        except Exception:
            pass

        # Output Leakage Stats
        try:
            leakage_stats = monitor.output_leakage_detector.get_leakage_stats()
            if leakage_stats.get('total_outputs_evaluated', 0) > 0:
                leakage_rate = leakage_stats.get('leakage_rate', 0)
                critical_leaks = leakage_stats.get('critical_severity_count', 0)

                leakage_class = 'critical' if leakage_rate > 5 else 'warning' if leakage_rate > 1 else 'success'

                parts.append(f'''
            <div class="insight-box {leakage_class}">
                <h4>🔐 출력 유출 탐지 (Output Leakage Detection)</h4>
                <p><strong>유출률:</strong> {leakage_rate:.1f}%</p>
                <p><strong>검사한 출력:</strong> {leakage_stats.get('total_outputs_evaluated', 0)}개</p>
                <p><strong>유출 유형:</strong></p>
                <ul style="margin: 5px 0 0 20px;">
                    <li>🔑 API Keys: {leakage_stats.get('api_key_leaks', 0)}건</li>
                    <li>🔒 Passwords: {leakage_stats.get('password_leaks', 0)}건</li>
                    <li>💳 Credit Cards: {leakage_stats.get('credit_card_leaks', 0)}건</li>
                    <li>📧 Emails: {leakage_stats.get('email_leaks', 0)}건</li>
                    <li>🆔 SSN: {leakage_stats.get('ssn_leaks', 0)}건</li>
                </ul>
                <p style="margin-top: 10px;"><strong>심각도:</strong> Critical {critical_leaks}건, High {leakage_stats.get('high_severity_count', 0)}건</p>
            </div>''')
        except Exception:
            pass

        # Tool Authorization Stats
        try:
            auth_stats = monitor.tool_authorizer.get_authorization_stats()
            if auth_stats.get('total_tool_calls', 0) > 0:
                compliance_rate = auth_stats.get('compliance_rate', 0)
                violation_rate = auth_stats.get('violation_rate', 0)

                auth_class = 'critical' if violation_rate > 10 else 'warning' if violation_rate > 5 else 'success'

                parts.append(f'''
            <div class="insight-box {auth_class}">
                <h4>✅ 도구 권한 관리 (Tool Authorization)</h4>
                <p><strong>권한 준수율:</strong> {compliance_rate:.1f}%</p>
                <p><strong>총 도구 호출:</strong> {auth_stats.get('total_tool_calls', 0)}회</p>
                <p><strong>권한 통계:</strong></p>
                <ul style="margin: 5px 0 0 20px;">
                    <li>✅ 인가됨: {auth_stats.get('authorized_calls', 0)}회</li>
                    <li>❌ 미인가: {auth_stats.get('unauthorized_calls', 0)}회</li>
                    <li>🚫 제한된 도구 시도: {auth_stats.get('restricted_tool_attempts', 0)}회</li>
                    <li>⚠️ 위험 파라미터: {auth_stats.get('dangerous_param_attempts', 0)}회</li>
                </ul>
                <p style="margin-top: 10px;"><strong>권한 수준:</strong></p>
                <ul style="margin: 5px 0 0 20px;">
                    <li>Admin: {auth_stats.get('admin_privilege_calls', 0)}회</li>
                    <li>Execute: {auth_stats.get('execute_privilege_calls', 0)}회</li>
                </ul>
            </div>''')
        except Exception:
            pass

        # Security Recommendations
        parts.append('''
            <h4 style="margin-top: 20px;">🛡️ 보안 권장사항</h4>
            <div class="recommendation priority-high">
                <strong>1. 입력 검증 강화</strong>
                <p>모든 사용자 입력에 대해 화이트리스트 기반 검증을 적용하고,
                특수문자 및 SQL 키워드를 필터링하세요.</p>
            </div>
            <div class="recommendation priority-high">
                <strong>2. 민감정보 마스킹</strong>
                <p>API 키, 비밀번호 등 민감정보가 로그나 응답에 포함되지 않도록
                자동 마스킹 정책을 적용하세요.</p>
            </div>
            <div class="recommendation priority-medium">
                <strong>3. 도구 권한 최소화</strong>
                <p>각 Agent에 필요한 최소한의 도구만 허용하고,
                위험한 도구(파일 삭제, 명령 실행 등)는 명시적으로 제한하세요.</p>
            </div>''')
    else:
        # Security metrics disabled message
        parts.append('''
            <div class="insight-box warning">
                <h4>⚠️ 보안 메트릭 비활성화됨</h4>
                <p>보안 메트릭이 활성화되지 않았습니다. 다음과 같이 활성화할 수 있습니다:</p>
                <pre style="background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 10px 0; overflow-x: auto;">
<code># PerformanceMonitor에서 활성화
monitor = PerformanceMonitor(
    enable_security_metrics=True,
    security_config={
        'allowed_tools': ['search', 'read', 'query'],
        'restricted_tools': ['delete', 'execute_command']
    }
)

# HybridPerformanceMonitor에서 활성화
from agent_evaluator.core.hybrid_monitor import create_monitor
monitor = create_monitor(
    profile='balanced',
    enable_security_metrics=True
)</code></pre>
                <p><strong>보안 메트릭 기능:</strong></p>
                <ul style="margin: 10px 0 0 20px; line-height: 2.0;">
                    <li>🛡️ <strong>입력 살균</strong>: SQL Injection, XSS, Command Injection 자동 탐지</li>
                    <li>🔐 <strong>출력 유출 탐지</strong>: API 키, 비밀번호, 신용카드 정보 감지</li>
                    <li>✅ <strong>도구 권한 관리</strong>: 화이트리스트/블랙리스트 기반 권한 검증</li>
                    <li>🚨 <strong>권한 상승 탐지</strong>: 의심스러운 권한 상승 패턴 감지</li>
                    <li>⛓️ <strong>도구 체인 공격</strong>: 악의적 도구 호출 시퀀스 탐지</li>
                </ul>
                <p style="margin-top: 15px;">
                    <a href="https://github.com/your-repo/agent-evaluator/blob/main/Docs/SECURITY_METRICS_GUIDE.html"
                       target="_blank" style="color: #3498db; text-decoration: none;">
                        📚 보안 메트릭 가이드 보기 →
                    </a>
                </p>
            </div>''')

    parts.append('</div>')
    return ''.join(parts)


def _build_advanced_section(adv_metrics) -> str:
    """Build the Advanced Metrics section (DeepEval, Ragas)."""
    parts = []

    parts.append('''
        <div class="section" id="advanced">
            <h2><span class="icon">🔬</span>Advanced Metrics - 외부 라이브러리 평가</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                Advanced Metrics는 <strong>외부 평가 라이브러리</strong>를 활용하여 AI Agent의 성능을 다각도로 분석합니다.
                DeepEval과 Ragas 라이브러리를 통해 더 깊이 있는 품질 평가를 제공합니다.
            </p>

            <h3>DeepEval 평가 결과</h3>''')

    # Check for DeepEval metrics in advanced_metrics_summary
    has_deepeval = any(key in adv_metrics for key in [
        'g_eval_score', 'hallucination_score', 'toxicity_score', 'bias_score', 'answer_relevancy_score'
    ])

    if has_deepeval:
        # G-Eval Score
        g_eval_data = adv_metrics.get('g_eval_score', {})
        if g_eval_data:
            g_eval_score = g_eval_data.get('mean', 0) * 100
            g_eval_class = 'success' if g_eval_score >= 70 else 'warning' if g_eval_score >= 50 else 'critical'

            parts.append(f'''
            <h4>G-Eval (전반적 품질)</h4>
            <div class="insight-box {g_eval_class}">
                <p><strong>평균 점수:</strong> {g_eval_score:.1f}%</p>
                <p><strong>평가 횟수:</strong> {g_eval_data.get('count', 0)}회</p>
                <p><strong>평가:</strong> {'우수' if g_eval_score >= 70 else '양호' if g_eval_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> LLM을 평가자로 사용한 전반적인 응답 품질 점수입니다.</p>
            </div>''')

        # Hallucination Score (높을수록 좋음 - 환각이 없음)
        hall_data = adv_metrics.get('hallucination_score', {})
        if hall_data:
            hall_score = hall_data.get('mean', 0) * 100
            hall_class = 'success' if hall_score >= 70 else 'warning' if hall_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Hallucination Score (환각 없음 점수)</h4>
            <div class="insight-box {hall_class}">
                <p><strong>평균 점수:</strong> {hall_score:.1f}%</p>
                <p><strong>평가 횟수:</strong> {hall_data.get('count', 0)}회</p>
                <p><strong>평가:</strong> {'우수' if hall_score >= 70 else '양호' if hall_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 컨텍스트에 충실한 정도 (높을수록 환각이 적음)</p>
            </div>''')

        # Toxicity Score (낮을수록 좋음)
        tox_data = adv_metrics.get('toxicity_score', {})
        if tox_data:
            tox_score = tox_data.get('mean', 0) * 100
            tox_class = 'success' if tox_score <= 30 else 'warning' if tox_score <= 50 else 'critical'

            parts.append(f'''
            <h4>Toxicity Score (독성 점수)</h4>
            <div class="insight-box {tox_class}">
                <p><strong>평균 점수:</strong> {tox_score:.1f}%</p>
                <p><strong>평가 횟수:</strong> {tox_data.get('count', 0)}회</p>
                <p><strong>평가:</strong> {'우수 (낮음)' if tox_score <= 30 else '양호' if tox_score <= 50 else '높음 (개선 필요)'}</p>
                <p><strong>설명:</strong> 유해하거나 부적절한 콘텐츠 점수 (낮을수록 좋음)</p>
            </div>''')

        # Bias Score (낮을수록 좋음)
        bias_data = adv_metrics.get('bias_score', {})
        if bias_data:
            bias_score = bias_data.get('mean', 0) * 100
            bias_class = 'success' if bias_score <= 30 else 'warning' if bias_score <= 50 else 'critical'

            parts.append(f'''
            <h4>Bias Score (편향 점수)</h4>
            <div class="insight-box {bias_class}">
                <p><strong>평균 점수:</strong> {bias_score:.1f}%</p>
                <p><strong>평가 횟수:</strong> {bias_data.get('count', 0)}회</p>
                <p><strong>평가:</strong> {'우수 (낮음)' if bias_score <= 30 else '양호' if bias_score <= 50 else '높음 (개선 필요)'}</p>
                <p><strong>설명:</strong> 편향된 응답 점수 (낮을수록 공정함)</p>
            </div>''')

        # Answer Relevancy Score (높을수록 좋음)
        ans_rel_data = adv_metrics.get('answer_relevancy_score', {})
        if ans_rel_data:
            ans_rel_score = ans_rel_data.get('mean', 0) * 100
            ans_rel_class = 'success' if ans_rel_score >= 70 else 'warning' if ans_rel_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Answer Relevancy (답변 관련성)</h4>
            <div class="insight-box {ans_rel_class}">
                <p><strong>평균 점수:</strong> {ans_rel_score:.1f}%</p>
                <p><strong>평가 횟수:</strong> {ans_rel_data.get('count', 0)}회</p>
                <p><strong>평가:</strong> {'우수' if ans_rel_score >= 70 else '양호' if ans_rel_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 질문과 답변의 관련성 점수</p>
            </div>''')
    else:
        parts.append('''
            <p>DeepEval 평가 데이터가 없습니다. external_library_mode="all" 또는 "deepeval"로 설정하여 DeepEval 메트릭을 활성화할 수 있습니다.</p>''')

    # Ragas Metrics
    parts.append('<h3>Ragas 평가 결과</h3>')

    # Check for Ragas metrics in advanced_metrics_summary
    has_ragas = any(key in adv_metrics for key in [
        'ragas_faithfulness', 'ragas_context_precision', 'ragas_context_recall', 'ragas_answer_relevancy'
    ])

    if has_ragas:
        # Faithfulness (Ragas)
        faithfulness_data = adv_metrics.get('ragas_faithfulness', {})
        if faithfulness_data:
            faith_score = faithfulness_data.get('mean', 0) * 100
            faith_class = 'success' if faith_score >= 70 else 'warning' if faith_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Faithfulness (컨텍스트 충실도)</h4>
            <div class="insight-box {faith_class}">
                <p><strong>평균 점수:</strong> {faith_score:.1f}%</p>
                <p><strong>최대:</strong> {faithfulness_data.get('max', 0):.3f}</p>
                <p><strong>최소:</strong> {faithfulness_data.get('min', 0):.3f}</p>
                <p><strong>평가:</strong> {'우수' if faith_score >= 70 else '양호' if faith_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정 (환각 방지)</p>
            </div>''')

        # Context Precision (Ragas)
        ctx_precision_data = adv_metrics.get('ragas_context_precision', {})
        if ctx_precision_data:
            prec_score = ctx_precision_data.get('mean', 0) * 100
            prec_class = 'success' if prec_score >= 70 else 'warning' if prec_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Context Precision (검색 정밀도)</h4>
            <div class="insight-box {prec_class}">
                <p><strong>평균 점수:</strong> {prec_score:.1f}%</p>
                <p><strong>최대:</strong> {ctx_precision_data.get('max', 0):.3f}</p>
                <p><strong>최소:</strong> {ctx_precision_data.get('min', 0):.3f}</p>
                <p><strong>평가:</strong> {'우수' if prec_score >= 70 else '양호' if prec_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 검색된 컨텍스트 중 관련 있는 정보의 비율 (노이즈 최소화)</p>
            </div>''')

        # Context Recall (Ragas)
        ctx_recall_data = adv_metrics.get('ragas_context_recall', {})
        if ctx_recall_data:
            recall_score = ctx_recall_data.get('mean', 0) * 100
            recall_class = 'success' if recall_score >= 70 else 'warning' if recall_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Context Recall (검색 재현율)</h4>
            <div class="insight-box {recall_class}">
                <p><strong>평균 점수:</strong> {recall_score:.1f}%</p>
                <p><strong>최대:</strong> {ctx_recall_data.get('max', 0):.3f}</p>
                <p><strong>최소:</strong> {ctx_recall_data.get('min', 0):.3f}</p>
                <p><strong>평가:</strong> {'우수' if recall_score >= 70 else '양호' if recall_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 필요한 정보를 모두 검색했는지 측정 (완전성)</p>
            </div>''')

        # Answer Relevancy (Ragas)
        ans_rel_data = adv_metrics.get('ragas_answer_relevancy', {})
        if ans_rel_data:
            ans_rel_score = ans_rel_data.get('mean', 0) * 100
            ans_rel_class = 'success' if ans_rel_score >= 70 else 'warning' if ans_rel_score >= 50 else 'critical'

            parts.append(f'''
            <h4>Answer Relevancy (답변 관련성)</h4>
            <div class="insight-box {ans_rel_class}">
                <p><strong>평균 점수:</strong> {ans_rel_score:.1f}%</p>
                <p><strong>최대:</strong> {ans_rel_data.get('max', 0):.3f}</p>
                <p><strong>최소:</strong> {ans_rel_data.get('min', 0):.3f}</p>
                <p><strong>평가:</strong> {'우수' if ans_rel_score >= 70 else '양호' if ans_rel_score >= 50 else '개선 필요'}</p>
                <p><strong>설명:</strong> 답변이 질문과 얼마나 관련 있는지 측정</p>
            </div>''')
    else:
        parts.append('''
            <p>Ragas 평가 데이터가 없습니다. external_library_mode="all" 또는 "ragas"로 설정하여 Ragas 메트릭을 활성화할 수 있습니다.</p>''')

    # Advanced Metrics Summary
    parts.append('''
            <h3>Advanced Metrics 활용 가이드</h3>
            <div class="insight-box">
                <h4>외부 라이브러리 메트릭의 장점</h4>
                <ul style="margin: 10px 0 10px 20px; line-height: 2.0;">
                    <li><strong>다각적 평가:</strong> 여러 관점에서 AI Agent 성능을 평가하여 숨겨진 문제 발견</li>
                    <li><strong>업계 표준:</strong> DeepEval과 Ragas는 널리 사용되는 평가 프레임워크로 벤치마킹 용이</li>
                    <li><strong>RAG 최적화:</strong> 특히 RAG(Retrieval-Augmented Generation) 시스템의 검색 품질 개선에 유용</li>
                    <li><strong>컨텍스트 품질:</strong> 검색된 컨텍스트의 정밀도와 재현율을 정량적으로 측정</li>
                </ul>
                <p style="margin-top: 15px;"><strong>활성화 방법:</strong> HybridPerformanceMonitor 초기화 시 <code>external_library_mode="all"</code> 파라미터를 설정하세요.</p>
            </div>
        </div>''')

    return ''.join(parts)


def _build_transparency_section() -> str:
    """Build the Test Transparency section."""
    parts = []

    parts.append('''
        <div class="section" id="transparency">
            <h2><span class="icon">🔍</span>Test 투명성 - 평가 프로세스 투명성</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                Test 투명성은 <strong>평가 프로세스의 투명성과 추적 가능성</strong>을 보장합니다.
                각 메트릭의 계산 과정, 주석, 감사 로그를 제공하여 평가 결과의 신뢰성을 높입니다.
            </p>''')

    # Get transparency data from file system
    from ..utils.path_helpers import get_evaluation_results_dir
    transparency_stats = {}

    _results = get_evaluation_results_dir()
    traces_dir = _results / "traces"
    annotations_dir = _results / "annotations"
    audit_logs_dir = _results / "audit_logs"
    reports_dir = _results / "transparent_reports"

    has_traces = traces_dir.exists() and list(traces_dir.glob("trace_*.json"))
    has_annotations = annotations_dir.exists() and list(annotations_dir.glob("annotation_*.json"))
    has_audit_logs = audit_logs_dir.exists() and list(audit_logs_dir.glob("audit_*.json"))
    has_reports = reports_dir.exists() and list(reports_dir.glob("report_*.json"))

    if has_traces or has_annotations or has_audit_logs or has_reports:
        transparency_stats = {
            'total_reports': len(list(reports_dir.glob("report_*.json"))) if has_reports else 0,
            'traced_metrics': len(list(traces_dir.glob("trace_*.json"))) if has_traces else 0,
            'annotated_items': len(list(annotations_dir.glob("annotation_*.json"))) if has_annotations else 0,
            'audit_events': len(list(audit_logs_dir.glob("audit_*.json"))) if has_audit_logs else 0
        }

    if transparency_stats and (transparency_stats.get('total_reports', 0) > 0 or
                                transparency_stats.get('traced_metrics', 0) > 0 or
                                transparency_stats.get('annotated_items', 0) > 0 or
                                transparency_stats.get('audit_events', 0) > 0):
        parts.append(f'''
            <h3>투명성 요약</h3>
            <div class="insight-box success">
                <h4>평가 투명성 현황</h4>
                <p><strong>생성된 상세 리포트:</strong> {transparency_stats.get('total_reports', 0)}개</p>
                <p><strong>추적 가능한 메트릭:</strong> {transparency_stats.get('traced_metrics', 0)}개</p>
                <p><strong>주석 처리된 항목:</strong> {transparency_stats.get('annotated_items', 0)}개</p>
                <p><strong>감사 로그 이벤트:</strong> {transparency_stats.get('audit_events', 0)}개</p>
            </div>

            <h3>투명성 구성 요소</h3>
            <table>
                <thead>
                    <tr>
                        <th>구성 요소</th>
                        <th>설명</th>
                        <th>활용 사례</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>📋 상세 리포트</strong></td>
                        <td>각 Task별 평가 결과의 상세 내역</td>
                        <td>개별 Task 성능 분석, 문제 원인 추적</td>
                    </tr>
                    <tr>
                        <td><strong>🔍 메트릭 추적</strong></td>
                        <td>각 메트릭의 계산 과정 및 중간 값</td>
                        <td>메트릭 검증, 계산 로직 이해</td>
                    </tr>
                    <tr>
                        <td><strong>📝 주석 (Annotations)</strong></td>
                        <td>평가자의 코멘트 및 특이사항 기록</td>
                        <td>정성적 분석, 추가 컨텍스트 제공</td>
                    </tr>
                    <tr>
                        <td><strong>📜 감사 로그</strong></td>
                        <td>평가 과정의 모든 이벤트 기록</td>
                        <td>평가 과정 재현, 변경 이력 추적</td>
                    </tr>
                </tbody>
            </table>''')

        parts.append('''
            <h3>투명성 활용 가이드</h3>
            <div class="insight-box">
                <h4>투명성 데이터 활용 방법</h4>
                <ul style="margin: 10px 0 10px 20px; line-height: 2.0;">
                    <li><strong>디버깅:</strong> 실패한 Task의 상세 리포트를 통해 정확한 실패 원인 파악</li>
                    <li><strong>검증:</strong> 메트릭 추적 데이터로 계산 과정의 정확성 검증</li>
                    <li><strong>개선:</strong> 주석과 감사 로그를 분석하여 반복적인 문제 패턴 발견</li>
                    <li><strong>규정 준수:</strong> 감사 로그를 통해 평가 과정의 투명성 입증 (Compliance)</li>
                    <li><strong>지식 공유:</strong> 상세 리포트를 팀과 공유하여 개선 방안 논의</li>
                </ul>
                <p style="margin-top: 15px;"><strong>접근 방법:</strong> <code>agent-eval serve</code> 대시보드의 투명성 섹션에서 각 리포트를 확인할 수 있습니다.</p>
            </div>''')
    else:
        parts.append('''
            <p>투명성 데이터가 없습니다. TransparentEvaluationReport를 생성하여 평가 프로세스의 투명성을 확보할 수 있습니다.</p>
            <div class="insight-box">
                <h4>투명성 리포트 생성 방법</h4>
                <p>다음 코드를 사용하여 각 Task별 상세 리포트를 생성할 수 있습니다:</p>
                <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; margin-top: 10px;">
report = transparency.generate_transparent_report(
    task_id="task_001",
    task_type="qa",
    success=True
)</pre>
            </div>''')

    parts.append('</div>')
    return ''.join(parts)


def _build_security_section(monitor) -> str:
    """Build the standalone Security section. Returns empty string if security metrics unavailable."""
    # Check if security metrics are available
    has_security = hasattr(monitor, 'input_sanitizer') and hasattr(monitor, 'output_leakage_detector')

    if not has_security:
        return ""

    parts = []

    parts.append('''
        <div class="section" id="security">
            <h2><span class="icon">🔒</span>Security - 보안 지표</h2>
            <p style="margin-bottom: 20px; line-height: 1.8;">
                보안 메트릭은 AI Agent의 안전성과 신뢰성을 평가합니다. Layer 1 (Native Security)과 Layer 2 (Agentic Security)로 구분됩니다.
            </p>''')

    # Get security metrics
    try:
        # Layer 1 Security
        input_sec_stats = monitor.input_sanitizer.get_security_stats()
        output_leak_stats = monitor.output_leakage_detector.get_leakage_stats()
        auth_stats = monitor.tool_authorizer.get_compliance_stats() if hasattr(monitor, 'tool_authorizer') else {}

        threat_rate = input_sec_stats.get('threat_rate', 0)
        leakage_rate = output_leak_stats.get('leakage_rate', 0)
        compliance_rate = auth_stats.get('compliance_rate', 100)

        # Layer 2 Security
        esc_stats = monitor.privilege_escalation_detector.get_escalation_stats() if hasattr(monitor, 'privilege_escalation_detector') else {}
        attack_stats = monitor.tool_chain_attack_detector.get_attack_stats() if hasattr(monitor, 'tool_chain_attack_detector') else {}

        esc_rate = esc_stats.get('escalation_rate', 0)
        attack_rate = attack_stats.get('detection_rate', 0)

        # Security Summary Cards
        parts.append('<div class="metrics-grid">')

        # Input Threat
        threat_badge = 'status-good' if threat_rate < 10 else 'status-warning' if threat_rate < 20 else 'status-critical'
        threat_status = 'badge-success' if threat_rate < 10 else 'badge-warning' if threat_rate < 20 else 'badge-danger'
        parts.append(f'''
                <div class="metric-card {threat_badge}">
                    <h3>입력 위협 탐지율</h3>
                    <div class="value">{threat_rate:.1f}%</div>
                    <div class="subtitle"><span class="{threat_status}">Layer 1</span></div>
                </div>''')

        # Output Leakage
        leak_badge = 'status-good' if leakage_rate < 5 else 'status-warning' if leakage_rate < 10 else 'status-critical'
        leak_status = 'badge-success' if leakage_rate < 5 else 'badge-warning' if leakage_rate < 10 else 'badge-danger'
        parts.append(f'''
                <div class="metric-card {leak_badge}">
                    <h3>출력 유출 탐지율</h3>
                    <div class="value">{leakage_rate:.1f}%</div>
                    <div class="subtitle"><span class="{leak_status}">Layer 1</span></div>
                </div>''')

        # Authorization Compliance
        auth_badge = 'status-good' if compliance_rate >= 95 else 'status-warning' if compliance_rate >= 85 else 'status-critical'
        auth_status = 'badge-success' if compliance_rate >= 95 else 'badge-warning' if compliance_rate >= 85 else 'badge-danger'
        parts.append(f'''
                <div class="metric-card {auth_badge}">
                    <h3>권한 준수율</h3>
                    <div class="value">{compliance_rate:.1f}%</div>
                    <div class="subtitle"><span class="{auth_status}">Layer 1</span></div>
                </div>''')

        # Privilege Escalation
        if esc_stats:
            esc_badge = 'status-good' if esc_rate < 10 else 'status-warning' if esc_rate < 20 else 'status-critical'
            esc_status = 'badge-success' if esc_rate < 10 else 'badge-warning' if esc_rate < 20 else 'badge-danger'
            parts.append(f'''
                <div class="metric-card {esc_badge}">
                    <h3>권한 상승 탐지율</h3>
                    <div class="value">{esc_rate:.1f}%</div>
                    <div class="subtitle"><span class="{esc_status}">Layer 2</span></div>
                </div>''')

        parts.append('</div>')

        # Detailed Layer 1 Security
        parts.append('''
            <h3>🔒 Layer 1 Security (Native Security)</h3>
            <p style="margin-bottom: 15px; line-height: 1.8;">
                Layer 1 보안은 입력 검증, 출력 유출 방지, 도구 권한 관리 등 기본적인 보안 메커니즘을 평가합니다.
            </p>''')

        # Input Security
        input_class = 'success' if threat_rate < 10 else 'warning' if threat_rate < 20 else 'critical'
        parts.append(f'''
            <div class="insight-box {input_class}">
                <h4>입력 보안 (Input Sanitization)</h4>
                <p><strong>위협 탐지율:</strong> {threat_rate:.1f}%</p>
                <p><strong>평가된 입력:</strong> {input_sec_stats.get('total_inputs_evaluated', 0)}개</p>
                <p><strong>위협 탐지:</strong> {input_sec_stats.get('inputs_with_threats', 0)}개</p>
                <p><strong>SQL Injection:</strong> {input_sec_stats.get('sql_injection_attempts', 0)}건</p>
                <p><strong>Prompt Injection:</strong> {input_sec_stats.get('prompt_injection_attempts', 0)}건</p>
                <p><strong>XSS 시도:</strong> {input_sec_stats.get('xss_attempts', 0)}건</p>
                <p><strong>Path Traversal:</strong> {input_sec_stats.get('path_traversal_attempts', 0)}건</p>
            </div>''')

        # Output Leakage
        leak_class = 'success' if leakage_rate < 5 else 'warning' if leakage_rate < 10 else 'critical'
        parts.append(f'''
            <div class="insight-box {leak_class}">
                <h4>출력 유출 방지 (Output Leakage Detection)</h4>
                <p><strong>유출 탐지율:</strong> {leakage_rate:.1f}%</p>
                <p><strong>평가된 출력:</strong> {output_leak_stats.get('total_outputs_evaluated', 0)}개</p>
                <p><strong>유출 탐지:</strong> {output_leak_stats.get('outputs_with_leakage', 0)}개</p>
                <p><strong>API Key 유출:</strong> {output_leak_stats.get('api_key_leaks', 0)}건</p>
                <p><strong>Password 유출:</strong> {output_leak_stats.get('password_leaks', 0)}건</p>
                <p><strong>Email 노출:</strong> {output_leak_stats.get('email_leaks', 0)}건</p>
                <p><strong>고위험 유출:</strong> {output_leak_stats.get('critical_severity_count', 0)}건</p>
            </div>''')

        # Authorization
        if auth_stats:
            auth_class = 'success' if compliance_rate >= 95 else 'warning' if compliance_rate >= 85 else 'critical'
            parts.append(f'''
            <div class="insight-box {auth_class}">
                <h4>도구 권한 관리 (Tool Authorization)</h4>
                <p><strong>준수율:</strong> {compliance_rate:.1f}%</p>
                <p><strong>총 도구 호출:</strong> {auth_stats.get('total_tool_calls', 0)}개</p>
                <p><strong>위반율:</strong> {auth_stats.get('violation_rate', 0):.1f}%</p>
                <p><strong>제한된 도구 시도:</strong> {auth_stats.get('restricted_tool_attempts', 0)}건</p>
                <p><strong>위험한 파라미터:</strong> {auth_stats.get('dangerous_param_attempts', 0)}건</p>
            </div>''')

        # Detailed Layer 2 Security
        if esc_stats or attack_stats:
            parts.append('''
            <h3>🛡️ Layer 2 Security (Agentic Security)</h3>
            <p style="margin-bottom: 15px; line-height: 1.8;">
                Layer 2 보안은 권한 상승, 공격 패턴 탐지 등 에이전트 특화 보안 위협을 평가합니다.
            </p>''')

        # Privilege Escalation
        if esc_stats:
            esc_class = 'success' if esc_rate < 10 else 'warning' if esc_rate < 20 else 'critical'
            parts.append(f'''
            <div class="insight-box {esc_class}">
                <h4>권한 상승 탐지 (Privilege Escalation Detection)</h4>
                <p><strong>상승 탐지율:</strong> {esc_rate:.1f}%</p>
                <p><strong>평가된 체인:</strong> {esc_stats.get('total_evaluations', 0)}개</p>
                <p><strong>상승 탐지:</strong> {esc_stats.get('escalations_detected', 0)}건</p>
                <p><strong>고위험 이벤트:</strong> {esc_stats.get('high_risk_events', 0)}건</p>
            </div>''')

        # Attack Detection
        if attack_stats:
            attack_class = 'success' if attack_rate < 10 else 'warning' if attack_rate < 20 else 'critical'
            parts.append(f'''
            <div class="insight-box {attack_class}">
                <h4>공격 패턴 탐지 (Tool Chain Attack Detection)</h4>
                <p><strong>공격 탐지율:</strong> {attack_rate:.1f}%</p>
                <p><strong>분석된 체인:</strong> {attack_stats.get('total_chains_analyzed', 0)}개</p>
                <p><strong>의심스러운 체인:</strong> {attack_stats.get('suspicious_chains', 0)}개</p>
                <p><strong>데이터 유출:</strong> {attack_stats.get('data_exfiltration_detected', 0)}건</p>
                <p><strong>횡적 이동:</strong> {attack_stats.get('lateral_movement_detected', 0)}건</p>
                <p><strong>방어 회피:</strong> {attack_stats.get('defense_evasion_detected', 0)}건</p>
                <p><strong>지속성 확보:</strong> {attack_stats.get('persistence_detected', 0)}건</p>
            </div>''')

    except Exception as e:
        parts.append(f'<p>보안 메트릭을 가져오는 중 오류 발생: {str(e)}</p>')

    parts.append('</div>')
    return ''.join(parts)


def _build_insights_section(tcr, acc, hall_rate, latency, quality_metrics, avg_cost_per_task) -> str:
    """Build the Key Insights section."""
    parts = []

    parts.append('''
        <div class="section" id="insights">
            <h2><span class="icon">💡</span>주요 인사이트 (Key Insights)</h2>
            <h3>강점 (Strengths)</h3>''')

    strengths = []
    if tcr >= 90:
        strengths.append('높은 작업 완료율 (TCR ≥ 90%)')
    if acc >= 85:
        strengths.append('우수한 정확도 (≥ 85%)')
    if quality_metrics.get('avg_total_score', 0) >= 4.5:
        strengths.append('뛰어난 응답 품질 (≥ 4.5/5.0)')
    if hall_rate < 5:
        strengths.append('낮은 환각률 (< 5%)')
    if latency <= 3.0:
        strengths.append('빠른 응답 시간 (≤ 3초)')

    if strengths:
        parts.append('<ul style="margin: 15px 0 15px 20px; line-height: 2.0;">')
        for strength in strengths:
            parts.append(f'<li>✅ {strength}</li>')
        parts.append('</ul>')
    else:
        parts.append('<p>현재 명확한 강점 영역이 식별되지 않았습니다. 전반적인 개선이 필요합니다.</p>')

    parts.append('<h3>개선 영역 (Areas for Improvement)</h3>')

    improvements = []
    if tcr < 75:
        improvements.append(('작업 완료율 향상', '에러 핸들링 강화 및 안정성 개선', 'high'))
    if acc < 70:
        improvements.append(('정확도 개선', '검증 로직 추가 및 품질 관리 강화', 'high'))
    if hall_rate >= 10:
        improvements.append(('환각 감소', 'RAG 컨텍스트 품질 향상 및 사실 검증', 'high'))
    if latency > 5.0:
        improvements.append(('응답 시간 최적화', '프롬프트 및 모델 최적화', 'medium'))
    if quality_metrics.get('avg_total_score', 0) < 4.0:
        improvements.append(('응답 품질 향상', '프롬프트 엔지니어링 및 출력 구조화', 'medium'))
    if avg_cost_per_task > 0.05:
        improvements.append(('비용 최적화', '토큰 사용량 감소 및 효율성 개선', 'low'))

    if improvements:
        parts.append('<table><thead><tr><th>개선 영역</th><th>조치사항</th><th>우선순위</th></tr></thead><tbody>')
        for area, action, priority in improvements:
            priority_badge = 'badge-danger' if priority == 'high' else 'badge-warning' if priority == 'medium' else 'badge-success'
            priority_text = '높음' if priority == 'high' else '중간' if priority == 'medium' else '낮음'
            parts.append(f'<tr><td><strong>{area}</strong></td><td>{action}</td><td><span class="{priority_badge}">{priority_text}</span></td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p style="color: #27ae60;">✅ 모든 지표가 우수한 수준입니다. 현재 품질을 유지하세요.</p>')

    parts.append('</div>')
    return ''.join(parts)


def _build_recommendations_section(report, hall_rate, latency, quality_metrics) -> str:
    """Build the Recommendations section."""
    parts = []

    # Recompute strengths (same logic as _build_insights_section)
    # Note: tcr, acc, hall_rate, latency, quality_metrics are needed; tcr/acc not passed here
    # so we rely on report.recommendations branching; strengths only used for fallback condition
    strengths = []  # placeholder — populated below if we have the metrics from report
    # We approximate strengths from report data when available
    tcr_data = report.accuracy_metrics.get('tcr', {}) if hasattr(report, 'accuracy_metrics') else {}
    tcr = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
    accuracy_metrics = {}
    acc = 0
    if hasattr(report, 'accuracy_metrics'):
        acc_data = report.accuracy_metrics.get('overall_accuracy', 0)
        acc = acc_data if isinstance(acc_data, (int, float)) else 0

    if tcr >= 90:
        strengths.append('높은 작업 완료율 (TCR ≥ 90%)')
    if acc >= 85:
        strengths.append('우수한 정확도 (≥ 85%)')
    if quality_metrics.get('avg_total_score', 0) >= 4.5:
        strengths.append('뛰어난 응답 품질 (≥ 4.5/5.0)')
    if hall_rate < 5:
        strengths.append('낮은 환각률 (< 5%)')
    if latency <= 3.0:
        strengths.append('빠른 응답 시간 (≤ 3초)')

    parts.append('''
        <div class="section" id="recommendations">
            <h2><span class="icon">🎯</span>개선 권장사항 (Recommendations)</h2>''')

    if report.recommendations:
        for i, rec in enumerate(report.recommendations, 1):
            priority_class = 'priority-high' if i <= 3 else 'priority-medium' if i <= 6 else 'priority-low'

            # Handle different recommendation data structures
            # Structure 1: {"title": "...", "suggestion": "..."}
            # Structure 2: {"area": "...", "issue": "...", "suggestion": "...", "impact": "..."}

            title = rec.get('title', '')
            if not title:
                # Use 'area' or 'issue' as title if 'title' is not present
                title = rec.get('area', rec.get('issue', ''))

            # Build detailed content
            content_parts = []

            if 'issue' in rec and rec.get('area') != rec.get('issue'):
                content_parts.append(f"<p style=\"margin: 10px 0; line-height: 1.8;\"><strong>🔍 현재 문제점</strong><br/>{rec['issue']}</p>")

            if 'suggestion' in rec and rec['suggestion']:
                content_parts.append(f"<p style=\"margin: 10px 0; line-height: 1.8;\"><strong>💡 개선 제안</strong><br/>{rec['suggestion']}</p>")

            if 'impact' in rec and rec['impact']:
                content_parts.append(f"<p style=\"margin: 10px 0; line-height: 1.8;\"><strong>📈 예상 효과</strong><br/>{rec['impact']}</p>")

            # If no structured fields, use suggestion as plain HTML
            if not content_parts and 'suggestion' in rec:
                content_parts.append(markdown_to_html(rec['suggestion']))

            content_html = '\n'.join(content_parts)

            parts.append(f'''
            <div class="recommendation {priority_class}">
                <strong>{i}. {title}</strong>
                {content_html}
            </div>''')
    else:
        # Generate default recommendations based on metrics
        if hall_rate >= 10:
            parts.append('''
            <div class="recommendation priority-high">
                <strong>1. 환각 탐지 및 완화 강화</strong>
                <p>환각률이 높습니다 (≥ 10%). RAG 시스템의 검색 품질을 개선하고, 컨텍스트 윈도우를 확장하며,
                출력 검증 단계를 추가하세요. 특히 숫자 정보는 반드시 소스와 대조 검증하세요.</p>
            </div>''')

        if latency > 5.0:
            parts.append('''
            <div class="recommendation priority-high">
                <strong>2. 응답 시간 최적화</strong>
                <p>평균 응답 시간이 5초를 초과합니다. 프롬프트를 간소화하고, 필요시 더 빠른 모델로 전환하며,
                병렬 처리 및 캐싱을 구현하세요.</p>
            </div>''')

        if quality_metrics.get('avg_total_score', 0) < 4.0:
            parts.append('''
            <div class="recommendation priority-medium">
                <strong>3. 응답 품질 개선</strong>
                <p>품질 점수가 4.0 미만입니다. 프롬프트에 구체적인 출력 포맷을 명시하고,
                Few-shot 예시를 추가하며, 구조화된 응답 생성을 유도하세요.</p>
            </div>''')

        if not strengths or len(strengths) < 2:
            parts.append('''
            <div class="recommendation priority-medium">
                <strong>전반적인 품질 관리 체계 수립</strong>
                <p>체계적인 테스트 및 모니터링 프로세스를 구축하세요.
                자동화된 평가 파이프라인, 지속적인 성능 추적, 정기적인 품질 리뷰를 실시하세요.</p>
            </div>''')

    parts.append('</div>')
    return ''.join(parts)


def _build_conclusion_section(total_tasks, tcr, acc, hall_rate) -> str:
    """Build the Conclusion section and footer."""
    parts = []

    overall_status = '우수' if (tcr >= 90 and acc >= 85 and hall_rate < 5) else '양호' if (tcr >= 75 and acc >= 70 and hall_rate < 10) else '개선 필요'
    conclusion_class = 'success' if overall_status == '우수' else 'warning' if overall_status == '양호' else 'critical'

    parts.append(f'''
        <div class="section" id="conclusion">
            <h2><span class="icon">📝</span>결론 및 다음 단계 (Conclusion)</h2>

            <div class="insight-box {conclusion_class}">
                <h4>전체 평가</h4>
                <p><strong>종합 평가:</strong> {overall_status}</p>
                <p>본 AI Agent는 {total_tasks}개의 Task를 평가한 결과, 전반적으로 <strong>{overall_status}</strong> 수준의 성능을 보였습니다.</p>
            </div>

            <h3>다음 단계 (Next Steps)</h3>
            <ol style="margin: 15px 0 15px 20px; line-height: 2.0;">
                <li><strong>우선순위 개선 작업 착수:</strong> 위에 식별된 개선 영역 중 우선순위가 높은 항목부터 개선</li>
                <li><strong>지속적인 모니터링:</strong> Agent Evaluator를 CI/CD 파이프라인에 통합하여 자동 평가</li>
                <li><strong>A/B 테스팅:</strong> 변경사항의 영향을 측정하기 위한 비교 평가 실시</li>
                <li><strong>정기 리뷰:</strong> 주간/월간 성능 리뷰 미팅으로 지속적인 품질 개선</li>
            </ol>

            <h3>문의 및 지원</h3>
            <p>본 리포트에 대한 질문이나 Agent Evaluator 사용에 관한 지원이 필요하시면 개발팀에 문의하세요.</p>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p><strong>Agent Evaluator</strong> - AI 에이전트 성능 평가 시스템</p>
            <p>Designed for AI Agent Developers and Quality Managers</p>
            <p>Generated at {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}</p>
            <p>© 2025 Agent Evaluator. All rights reserved.</p>
        </div>
    </div>
</body>
</html>''')

    return ''.join(parts)


def generate_comprehensive_html_report(monitor) -> str:
    """Generate detailed comprehensive HTML report with all metrics and actionable insights"""

    # Get all metrics
    report = monitor.generate_hybrid_report()
    quality_metrics = monitor.quality_evaluator.get_quality_metrics()
    hallucination_data = monitor.hallucination_detector.get_hallucination_rate()
    token_stats = monitor.token_tracker.get_usage_stats()
    tool_selection_stats = monitor.tool_selection_tracker.get_accuracy_stats()
    coordination_stats = monitor.agent_coordination_tracker.calculate_coordination_score()
    workflow_stats = monitor.workflow_tracker.calculate_execution_success_rate()
    retry_metrics = monitor.retry_tracker.get_retry_metrics()
    latency_stats = monitor.latency_tracker.get_latency_stats()

    # Get advanced metrics from report (same as dashboard)
    adv_metrics = report.advanced_metrics_summary if hasattr(report, 'advanced_metrics_summary') else {}

    # Extract values
    tcr_data = report.accuracy_metrics.get('tcr', {})
    tcr = tcr_data.get('tcr', 0) if isinstance(tcr_data, dict) else 0
    success_rate = tcr_data.get('success_rate', 0) if isinstance(tcr_data, dict) else 0

    accuracy_metrics = monitor.accuracy_evaluator.get_accuracy_scores()
    acc = accuracy_metrics.get('overall_accuracy', 0)

    latency_data = report.efficiency_metrics.get('latency', {})
    latency = latency_data.get('mean', 0) if isinstance(latency_data, dict) else 0

    total_tasks = len(monitor.tcr_tracker.tasks)
    avg_cost_per_task = token_stats.get('avg_cost_per_task', 0)
    hall_rate = hallucination_data.get('overall_rate', 0)

    # Build from sections
    parts = [
        _build_css_and_head(),
        _build_header_toc(total_tasks, success_rate, tcr, acc, latency),
        _build_core_section(tcr, success_rate, acc, accuracy_metrics, quality_metrics, hallucination_data),
        _build_performance_section(latency, latency_stats, token_stats, retry_metrics),
        _build_agentic_section(monitor, tool_selection_stats, coordination_stats, workflow_stats, retry_metrics),
        _build_advanced_section(adv_metrics),
        _build_transparency_section(),
        _build_security_section(monitor),
        _build_insights_section(tcr, acc, hall_rate, latency, quality_metrics, avg_cost_per_task),
        _build_recommendations_section(report, hall_rate, latency, quality_metrics),
        _build_conclusion_section(total_tasks, tcr, acc, hall_rate),
    ]
    return ''.join(parts)
