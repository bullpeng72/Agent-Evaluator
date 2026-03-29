#!/usr/bin/env python3
"""
LangChain Integration - Full 3-Layer Metrics Support
=====================================================

LangChain 1.2.x (LCEL Runnable 기반) 에이전트에 대한 완전한 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics — TCR, Accuracy, Latency, Token Economy, ResponseQuality
- Layer 2: Agentic AI Metrics — Tool Selection, Workflow Execution, RetryCorrection 자동 추적
- Layer 2 (RAG): on_retriever_end → HallucinationDetector 자동 연결
- Security (opt-in): enable_security=True 로 InputSanitization / OutputLeakage / ToolAuthorization 활성화
- BaseCallbackHandler 기반 실시간 추적 (OpenAI / Anthropic / 기타 모두 지원)

사용 방법:
    from agent_evaluator.integrations import LangChainEvaluator

    evaluator = LangChainEvaluator(agent, monitor, enable_layer2=True)

    result = evaluator.run(
        query="What is AI?",
        ground_truth="Expected answer...",
        expected_tools=["search", "calculator"]
    )

    report = evaluator.generate_report()

요구 사항:
    pip install "agent-evaluator[langchain]"
    langchain >= 1.0.0, langchain-core >= 1.0.0
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType
from .framework_integrations import (
    ensure_security_trackers as _ensure_security_trackers,
    extract_tools_from_framework_object as _extract_tools_from_agent,
    infer_privilege_level as _infer_privilege_level,
)

try:
    from ..helpers.taskresult_helpers import (
        create_taskresult_from_execution,
        calculate_accuracy_score,
    )
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    create_taskresult_from_execution = None
    calculate_accuracy_score = None  # type: ignore[assignment]

# LangChain 1.x — langchain-core 기반 import
try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.agents import AgentAction, AgentFinish
    from langchain_core.outputs import LLMResult
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BaseCallbackHandler = object


def _parse_tool_input(tool_input: Any) -> Dict[str, Any]:
    """
    tool_input을 dict로 정규화합니다.
    JSON 문자열이면 파싱, 이미 dict면 그대로, 기타 타입은 {"input": str()} 로 감쌉니다.
    """
    if isinstance(tool_input, dict):
        return tool_input
    try:
        parsed = json.loads(str(tool_input))
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.debug("tool_input JSON 파싱 실패: %s", e)
    return {"input": str(tool_input)}


def _auto_extract_elements(text: str) -> List[str]:
    """
    입력 텍스트에서 ResponseQuality expected_elements를 다단계 휴리스틱으로 추출합니다.
    영문/한국어 동사 패턴, 목적어 패턴, 콤마 분리 fallback 을 차례로 적용합니다.
    """
    elements: List[str] = []
    seen: set = set()

    def _add(elem: str) -> bool:
        e = elem.strip().rstrip(".,;!? ")
        if e and 2 < len(e) < 120 and e.lower() not in seen:
            seen.add(e.lower())
            elements.append(e)
            return True
        return False

    # 영문 동사 패턴
    en_patterns = [
        r'(?:include|mention|describe|explain|provide|list|cover|address|discuss|analyze|evaluate|review|assess|check)\s+([^,\.\n]{3,100})',
        r'(?:the\s+)?(?:importance|significance|details|aspects|reasons|benefits|drawbacks|pros|cons)\s+of\s+([^,\.\n]{3,80})',
    ]
    for pat in en_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            _add(m.group(1))
            if len(elements) >= 5:
                return elements

    # 한국어 패턴 — 용언 기반
    ko_patterns = [
        r'(?:포함|언급|설명|제공|나열|기술|작성|다루|분석|검토|평가|살펴|알아|논의|기재)(?:해|하|하여|하고|할|하는|되어야|되어|줘|주세요|바랍니다)\s*([^,\.\n]{2,80})',
        r'([^,\.\n]{2,40})(?:의|에\s*대한|에\s*관한)\s+(?:장단점|중요성|의의|상세|이유|효과|문제점|영향)',
        r'다음(?:과|을|의)\s+(?:같은|같이)?\s*([^,\.\n]{2,60})',
    ]
    for pat in ko_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            _add(m.group(1))
            if len(elements) >= 5:
                return elements

    # Fallback: 짧은 쿼리를 콤마/세미콜론으로 분리
    if not elements and len(text) < 300:
        parts = re.split(r'[,;]', text)
        if 1 < len(parts) <= 6:
            for p in parts:
                _add(p)
                if len(elements) >= 5:
                    break

    return elements[:5]


def _resolve_privilege_level(tool_name: str, monitor: Optional[PerformanceMonitor] = None) -> str:
    """
    도구 권한 수준 결정:
    1순위: monitor.privilege_registry[tool_name] (실제 설정)
    2순위: _infer_privilege_level() 휴리스틱 (키워드 기반)
    """
    registry: Dict[str, str] = getattr(monitor, "privilege_registry", {}) or {}
    if tool_name in registry:
        return registry[tool_name]
    return _infer_privilege_level(tool_name)


if LANGCHAIN_AVAILABLE:
    class AdvancedLangChainCallback(BaseCallbackHandler):
        """
        LangChain 1.x용 평가 콜백 핸들러

        on_chat_model_start / on_llm_end 를 통해 OpenAI·Anthropic·로컬 모델
        모두의 토큰 사용량을 추출합니다.
        on_retriever_end 를 통해 RAG 컨텍스트를 수집해 HallucinationDetector에 연결합니다.
        """

        def __init__(
            self,
            monitor: PerformanceMonitor,
            task_type: str = TaskType.QA.value,
            expected_tools: Optional[List[str]] = None,
            expected_elements: Optional[List[str]] = None,
            ground_truth: Optional[str] = None,
            enable_layer2: bool = True,
            enable_security: bool = False,
            verbose: bool = True,
            task_id: Optional[str] = None,
        ):
            super().__init__()
            self.monitor = monitor
            self.task_type = task_type
            self.expected_tools = expected_tools
            self.expected_elements = expected_elements or []
            self.ground_truth = ground_truth
            self.enable_layer2 = enable_layer2
            self.enable_security = enable_security
            self.verbose = verbose

            self.current_task_id: Optional[str] = task_id  # 사용자 지정 시 on_chain_start 재생성 방지
            self.start_time: Optional[float] = None
            self.tokens_used: Dict[str, int] = {"input": 0, "output": 0}
            self.tool_calls: List[Dict[str, Any]] = []
            self.workflow_steps: List[List[Any]] = []  # [name, success, duration]
            self.errors: List[str] = []
            self.task_input: str = ""
            self.task_output: str = ""
            self.tool_start_times: Dict[str, float] = {}
            self.retry_count: int = 0
            self.last_error: str = ""  # on_chain_error 에서 수집 → retry_reason 개선
            self.retrieved_contexts: List[str] = []  # on_retriever_end 수집
            self.model_name: str = ""  # on_chat_model_start 에서 추출
            self._agent_name: str = ""  # on_chain_start 에서 추출 → AgentCoord from_agent
            self._retry_times: List[float] = []  # on_retry 타임스탬프 → duration 실측
            self._llm_start_time: float = 0.0  # on_chat_model_start/on_llm_start 타임스탬프
            self._has_actual_tokens: bool = False  # 실측 토큰 도착 여부 (중복 추정 방지)
            self._tool_outputs: List[str] = []  # on_tool_end 도구 실행 결과 (OutputLeakage용)
            self._is_top_chain: bool = False  # 최상위 체인 여부 (연속 실행 간 상태 격리)

        # ── 체인 생명주기 ────────────────────────────────────────────────────

        def on_chain_start(
            self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs
        ):
            # 새 실행 시작 시에만 run 상태 전체 리셋
            if not self.current_task_id or not self._is_top_chain:
                # UI-022: 4개 어댑터 공통 ms 타임스탬프 포맷
                self.current_task_id = f"langchain_{int(time.time() * 1000)}"
                self.start_time = time.time()
                self.tokens_used = {"input": 0, "output": 0}
                self.tool_calls = []
                self.workflow_steps = []
                self.errors = []
                self.task_output = ""
                self.tool_start_times = {}
                self.retry_count = 0
                self.last_error = ""
                self.retrieved_contexts = []
                self.model_name = ""
                self._agent_name = ""  # 연속 실행 간 에이전트 이름 누수 방지
                self._retry_times = []
                self._has_actual_tokens = False
                self._tool_outputs = []
                self._is_top_chain = True
            # 최상위 체인에서만 에이전트 이름 추출
            if not self._agent_name:
                chain_id = serialized.get("id", [])
                self._agent_name = (
                    chain_id[-1] if chain_id else serialized.get("name", "langchain_agent")
                ) or "langchain_agent"
            # inputs 는 dict 또는 str 모두 가능
            if isinstance(inputs, dict):
                # "messages" 키 처리: LangGraph-style 입력이나 chat model 체인 호환
                _msgs_val = inputs.get("messages")
                if _msgs_val and isinstance(_msgs_val, (list, tuple)) and _msgs_val:
                    _first_msg = _msgs_val[0]
                    self.task_input = str(getattr(_first_msg, "content", _first_msg))
                else:
                    self.task_input = inputs.get("input", inputs.get("query", str(inputs)))
            else:
                self.task_input = str(inputs)
            # expected_elements 자동 추출 (명시 전달 없을 때)
            if not self.expected_elements and self.task_input:
                self.expected_elements = _auto_extract_elements(self.task_input)
            if self.verbose:
                print(f"\n{'='*70}")
                print(f"🚀 LangChain 실행 시작 (Task ID: {self.current_task_id})")
                print(f"{'='*70}")

        def on_chain_end(self, outputs: Dict[str, Any], **kwargs):
            if not (self.current_task_id and self.start_time):
                return
            execution_time = time.time() - self.start_time
            success = len(self.errors) == 0

            # LCEL invoke 결과에서 출력 텍스트 추출
            if isinstance(outputs, dict):
                self.task_output = (
                    outputs.get("output")
                    or outputs.get("result")
                    or outputs.get("answer")
                    or str(outputs)
                )
            elif isinstance(outputs, str):
                self.task_output = outputs

            if self.verbose:
                print(f"\n✅ LangChain 실행 완료 ({execution_time:.2f}s)")

            self._record_layer1(execution_time, success)
            if self.enable_layer2:
                self._record_layer2()
            if self.enable_security:
                self._record_security()
            self._is_top_chain = False

        def on_chain_error(self, error: Exception, **kwargs):
            self.last_error = f"{type(error).__name__}: {str(error)[:80]}"
            self.errors.append(str(error))
            # 실패 태스크도 반드시 기록 — 에러가 있어도 수집된 메트릭은 보존
            if self.current_task_id and self.start_time:
                execution_time = time.time() - self.start_time
                self._record_layer1(execution_time, success=False)
                if self.enable_layer2:
                    self._record_layer2()
                if self.enable_security:
                    self._record_security()
            self._is_top_chain = False

        # ── LLM 토큰 추적 ────────────────────────────────────────────────────

        def on_chat_model_start(
            self,
            serialized: Dict[str, Any],
            messages: List[List[Any]],
            **kwargs,
        ):
            """Chat 모델 시작 — 모델명 추출 + 입력 길이 기반 토큰 추정 (실측 on_llm_end에서 덮어씀)"""
            self._llm_start_time = time.time()
            # 모델명 추출 (TokenEconomy model_name 연결용)
            if not self.model_name:
                kwargs_dict = kwargs.get("invocation_params", {})
                self.model_name = (
                    serialized.get("kwargs", {}).get("model_name", "")
                    or serialized.get("kwargs", {}).get("model", "")
                    or kwargs_dict.get("model_name", "")
                    or kwargs_dict.get("model", "")
                )
            # 실측값이 아직 없을 때만 입력 길이 추정으로 사전 채움
            if not self._has_actual_tokens:
                for message_list in messages:
                    for msg in message_list:
                        content = (
                            msg.get("content", "") if isinstance(msg, dict)
                            else str(getattr(msg, "content", ""))
                        )
                        self.tokens_used["input"] += max(1, len(content) // 4)

        def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs
        ):
            """Completion 모델 시작 — 입력 길이 기반 추정"""
            self._llm_start_time = time.time()
            if not self._has_actual_tokens:
                for prompt in prompts:
                    self.tokens_used["input"] += max(1, len(prompt) // 4)

        def on_llm_end(self, response: LLMResult, **kwargs):
            """LLM 완료 — OpenAI / Anthropic / 기타 토큰 포맷 통합 처리"""
            prompt_t = None
            completion_t = None

            if response.llm_output:
                # OpenAI: token_usage.prompt_tokens / completion_tokens
                # Anthropic: usage.input_tokens / output_tokens
                usage = (
                    response.llm_output.get("token_usage")
                    or response.llm_output.get("usage")
                    or {}
                )
                prompt_t = usage.get("prompt_tokens", usage.get("input_tokens"))
                completion_t = usage.get("completion_tokens", usage.get("output_tokens"))

            # Chat model: generation.message.usage_metadata 로도 확인
            if response.generations:
                for gen in response.generations[0]:
                    msg = getattr(gen, "message", None)
                    if msg:
                        meta = getattr(msg, "usage_metadata", None)
                        if meta:
                            meta_in = meta.get("input_tokens", 0)
                            meta_out = meta.get("output_tokens", 0)
                            if meta_in is not None or meta_out is not None:
                                if prompt_t is None:
                                    prompt_t = meta_in or 0
                                if completion_t is None:
                                    completion_t = meta_out or 0
                    # 응답 텍스트 수집
                    if not self.task_output:
                        self.task_output += getattr(gen, "text", "")

            # 실측값 처리: 추정값을 교체 or 누적 (0값도 API가 반환한 실측값으로 처리)
            if prompt_t is not None or completion_t is not None:
                prompt_t = prompt_t or 0
                completion_t = completion_t or 0
                if not self._has_actual_tokens:
                    # 최초 실측: 추정값 버리고 실측값으로 교체
                    self.tokens_used["input"] = prompt_t
                    self.tokens_used["output"] = completion_t
                    self._has_actual_tokens = True
                else:
                    # 이후 LLM 호출: 누적 (멀티-LLM 체인)
                    self.tokens_used["input"] += prompt_t
                    self.tokens_used["output"] += completion_t

            # LLM generation 스텝 기록 (WorkflowTracker success_rate 정확도 향상)
            if self.enable_layer2 and self.current_task_id:
                llm_dur = (
                    time.time() - self._llm_start_time
                    if getattr(self, "_llm_start_time", 0.0) > 0.0
                    else 0.0
                )
                self.workflow_steps.append(["llm_generation", True, llm_dur])

        # ── RAG Retriever 추적 ───────────────────────────────────────────────

        def on_retriever_end(self, documents: Any, **kwargs):
            """Retriever 완료 — RAG 컨텍스트 수집 → HallucinationDetector + WorkflowExecution"""
            _retriever_start = getattr(self, "_retriever_start_time", None)
            _elapsed = time.time() - _retriever_start if _retriever_start else 0.0
            try:
                for doc in documents:
                    content = (
                        doc.page_content if hasattr(doc, "page_content")
                        else str(getattr(doc, "content", doc))
                    )
                    # DQ-001: 20자 미만 단편 컨텍스트 필터 — 노이즈·조사·단어 하나 제거
                    if content and len(content) >= 20 and content not in self.retrieved_contexts:
                        self.retrieved_contexts.append(content)
            except Exception as e:
                logger.debug("retriever 문서 파싱 실패: %s", e)
            if self.enable_layer2:
                self.workflow_steps.append(["retrieval", True, _elapsed])

        def on_retriever_start(self, serialized: Any, query: str, **kwargs):
            """Retriever 시작 — 검색 소요 시간 측정용 타임스탬프 저장"""
            self._retriever_start_time = time.time()

        # ── 도구 추적 ────────────────────────────────────────────────────────

        def on_agent_action(self, action: AgentAction, **kwargs):
            run_id = str(kwargs.get("run_id", ""))
            self.tool_start_times[run_id] = time.time()
            self.tool_calls.append({
                "tool_name": action.tool,
                "parameters": _parse_tool_input(action.tool_input),
                "success": True,
                "duration": 0.0,
                "privilege_level": _resolve_privilege_level(action.tool, self.monitor),
                "execution_result": "",  # on_tool_end에서 채워짐; 불발 시 빈 문자열 유지
            })
            if self.enable_layer2:
                self.workflow_steps.append([action.tool, True, 0.0])

        def on_tool_end(self, output: str, **kwargs):
            run_id = str(kwargs.get("run_id", ""))
            _out_str = output if isinstance(output, str) else str(output) if output is not None else ""
            if run_id in self.tool_start_times:
                elapsed = time.time() - self.tool_start_times.pop(run_id)
                if self.tool_calls:
                    self.tool_calls[-1]["duration"] = elapsed
                    # ToolCallAnalyzer + OutputLeakage 양쪽에 활용할 실행 결과 기록
                    if _out_str:
                        self.tool_calls[-1]["execution_result"] = _out_str[:2000]
                if self.enable_layer2 and self.workflow_steps:
                    self.workflow_steps[-1][2] = elapsed
            # 도구 실행 결과 수집 → OutputLeakageDetector 통합 스캔용
            if _out_str and len(_out_str.strip()) > 0:
                self._tool_outputs.append(_out_str)

        def on_tool_error(self, error: Exception, **kwargs):
            run_id = str(kwargs.get("run_id", ""))
            elapsed = 0.0
            if run_id in self.tool_start_times:
                elapsed = time.time() - self.tool_start_times.pop(run_id)
            if self.tool_calls:
                self.tool_calls[-1]["success"] = False
                self.tool_calls[-1]["duration"] = elapsed
                self.tool_calls[-1]["error"] = str(error)
            if self.enable_layer2 and self.workflow_steps:
                self.workflow_steps[-1][1] = False
                self.workflow_steps[-1][2] = elapsed
            self.errors.append(f"Tool error: {error}")

        def on_retry(self, retry_state: Any, **kwargs):
            self.retry_count += 1
            self._retry_times.append(time.time())

        # ── 내부 기록 메서드 ─────────────────────────────────────────────────

        def _record_layer1(self, execution_time: float, success: bool):
            execution_time = max(0.001, execution_time)  # D3-1: zero-latency guard
            if self.verbose:
                print(f"\n📈 Layer 1: Native Metrics 기록 중...")

            if create_taskresult_from_execution and _HELPERS_AVAILABLE:
                task = create_taskresult_from_execution(
                    task_id=self.current_task_id,
                    task_type=self.task_type,
                    question=self.task_input,
                    response=self.task_output,
                    ground_truth=self.ground_truth,
                    execution_time=execution_time,
                    has_error=not success,
                    error_message=self.errors[0] if self.errors else None,
                )
                # I-C-001: create_taskresult_from_execution은 tool_calls를 빈 리스트로 반환
                # (openai_response/langchain_result 미전달 시) → 실제 수집 데이터로 덮어씀
                # 이렇게 해야 monitor.record_task()가 tool_analyzer.analyze_execution()을 호출함
                # DQ-035: on_tool_end/on_tool_error 미실행 시 duration=0.0 그대로 — 소급 플래그
                for _tc in self.tool_calls:
                    if _tc.get("duration", -1.0) == 0.0 and "duration_estimated" not in _tc:
                        _tc["duration_estimated"] = True
                task.tool_calls = self.tool_calls
                task.attempts = 1 + self.retry_count
                # Override with actual measured tokens (estimated tokens from helper may be inaccurate)
                if self.tokens_used.get("input", 0) > 0 or self.tokens_used.get("output", 0) > 0:
                    task.tokens_used = self.tokens_used
            else:
                # DQ-017: 공백 전용 ground_truth(" ") 는 truthy지만 의미 없는 계산 → strip() 추가
                _acc = (
                    calculate_accuracy_score(self.task_output, self.ground_truth)
                    if calculate_accuracy_score and self.task_output and self.ground_truth
                    and self.ground_truth.strip()
                    else 0.0
                )
                task = TaskResult(
                    task_id=self.current_task_id,
                    task_type=self.task_type,
                    success=success,
                    completion_score=1.0 if (success and bool(self.task_output)) else 0.0,
                    accuracy_score=_acc,
                    execution_time=execution_time,
                    tokens_used=self.tokens_used,
                    tool_calls=self.tool_calls,
                    attempts=1 + self.retry_count,
                    errors=self.errors,
                    timestamp=datetime.now(),
                )

            # DQ-168: record_task() 전에 model 설정 → tokens_used.get("model") 경로 활성화
            _effective_model = (self.model_name or "unknown_model").lower()  # DQ-183
            task.tokens_used["model"] = _effective_model
            self.monitor.record_task(task)
            # 소급 설정 (defense-in-depth: record_task 내부 직접 접근 경로 보완)
            if self.monitor.token_tracker.usage_log:
                self.monitor.token_tracker.usage_log[-1]["model"] = _effective_model


            # ResponseQualityEvaluator — request/response 기반 품질 평가
            if self.task_input and self.task_output:
                try:
                    self.monitor.quality_evaluator.evaluate_response(
                        task_id=self.current_task_id,
                        response=self.task_output,
                        request=self.task_input,
                        expected_elements=self.expected_elements,
                        ground_truth=self.ground_truth,
                    )
                    if self.verbose:
                        n_elem = len(self.expected_elements)
                        print(f"   ✅ ResponseQuality 평가 완료"
                              + (f" (expected_elements: {n_elem})" if n_elem else ""))
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

            # HallucinationDetector — RAG 컨텍스트가 수집된 경우
            if self.retrieved_contexts and self.task_output:
                try:
                    # DQ-047: 대용량 RAG 결과 → 무제한 join 방지 (HallucinationDetector OOM 위험)
                    # DQ-141: 공백 전용 컨텍스트 배제
                    combined_context = "\n".join(
                        c for c in self.retrieved_contexts if c.strip()
                    )[:50_000]
                    if not combined_context.strip():
                        raise ValueError("retrieved_contexts are all whitespace")
                    self.monitor.hallucination_detector.detect_hallucination(
                        task_id=self.current_task_id,
                        response=self.task_output,
                        context=combined_context,
                        ground_truth=self.ground_truth,
                    )
                    if self.verbose:
                        print(f"   ✅ HallucinationDetector: {len(self.retrieved_contexts)} 컨텍스트 분석")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

            if self.verbose:
                print(f"   ✅ TCR: {(task.completion_score or 0.0) * 100:.1f}%  "
                      f"Latency: {execution_time:.2f}s  "
                      f"Tokens: {self.tokens_used}")

        def _record_layer2(self):
            if self.verbose:
                print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

            # ToolSelectionTracker — expected_tools 가 명시적으로 제공된 경우에만 기록
            # expected_tools 없이 호출하면 100% 만점이 기록되어 지표가 오염됨
            actual_tools = [t["tool_name"] for t in self.tool_calls]
            if self.expected_tools:
                try:
                    self.monitor.tool_selection_tracker.evaluate_selection(
                        task_id=self.current_task_id,
                        expected_tools=self.expected_tools or [],
                        actual_tools=actual_tools,
                    )
                    if self.verbose:
                        if self.expected_tools:
                            print(f"   ✅ Tool Selection: expected={len(self.expected_tools)} "
                                  f"actual={len(actual_tools)}")
                        else:
                            print(f"   ✅ Tool Selection: actual={len(actual_tools)} (no expected)")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

            _lc_agent = self._agent_name or "langchain_agent"
            for step_name, success, duration in self.workflow_steps:
                if step_name == "llm_generation":
                    step_type = "llm_generation"
                    _meta: Dict[str, Any] = {"agent": _lc_agent}
                elif step_name == "retrieval":
                    step_type = "retrieval"
                    _meta = {"agent": _lc_agent}
                else:
                    step_type = "tool_call"
                    _meta = {"agent": _lc_agent, "tool": step_name}
                self.monitor.workflow_tracker.track_step(
                    task_id=self.current_task_id,
                    step_name=step_name,
                    step_type=step_type,
                    success=success,
                    execution_time=duration,
                    framework="langchain",
                    metadata=_meta,
                )
            if self.verbose and self.workflow_steps:
                print(f"   ✅ Workflow: {len(self.workflow_steps)} steps tracked")


            # M1: 단일 에이전트 LangChain에서는 도구 전환을 AgentCoordination으로 기록하지 않음
            # 도구는 에이전트가 아니므로 tool-to-tool 전환은 의미론적으로 오류 (WorkflowExecution에 이미 기록됨)
            # Multi-agent LangChain (agent routing) 사용 시 직접 monitor.agent_coordination_tracker 사용 권장
            if self.verbose and len(self.tool_calls) > 1:
                print(f"   ℹ️ Agent Coordination: 단일 에이전트 — 도구 전환은 WorkflowExecution에서 추적됨")

            # RetryCorrectionTracker — 항상 기록 (성공만 해도 first_attempt_success_rate 계산에 필요)
            final_success = len(self.errors) == 0
            if self.retry_count > 0:
                from agent_evaluator.core.trackers.security import categorize_retry_error
                _raw_reason = self.last_error if self.last_error else "chain_retry"
                reason = categorize_retry_error(_raw_reason) if self.last_error else "chain_retry"
                # 실측 타이밍: [start → retry1 → retry2 → ... → now]
                _now = time.time()
                _times = [self.start_time or _now] + self._retry_times + [_now]
                _durs = [max(0.0, _times[i + 1] - _times[i]) for i in range(len(_times) - 1)]
                # DQ-156: on_retry 콜백이 retry_count보다 적게 실행됐으면 duration 0.0 fallback 경고
                if len(self._retry_times) < self.retry_count and self.verbose:
                    import warnings as _w
                    _w.warn(
                        f"RetryCorrectionTracker: {self.retry_count} retries counted but only "
                        f"{len(self._retry_times)} on_retry timestamps captured — "
                        "some attempt durations will be 0.0 (estimated).",
                        UserWarning,
                        stacklevel=2,
                    )
                attempts_log = [
                    {"success": False, "retry_reason": reason,
                     "duration": _durs[i] if i < len(_durs) else 0.0,
                     "duration_estimated": i >= len(_durs)}
                    for i in range(self.retry_count)
                ]
                attempts_log.append({
                    "success": final_success, "retry_reason": "",
                    "duration": _durs[-1] if _durs else 0.0,
                })
            else:
                # 재시도 없음 — 단일 시도 성공/실패 기록 (실제 실행 시간 사용)
                single_dur = max(0.0, time.time() - self.start_time) if self.start_time else 0.0
                attempts_log = [{"success": final_success, "retry_reason": "", "duration": single_dur}]
            try:
                self.monitor.retry_tracker.track_attempts(
                    task_id=self.current_task_id,
                    attempts_log=attempts_log,
                    task_type=self.task_type,
                )
                if self.verbose:
                    if self.retry_count > 0:
                        print(f"   ✅ RetryCorrection: {self.retry_count} retries")
                    else:
                        print(f"   ✅ RetryCorrection: first attempt {'success' if final_success else 'failed'}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        def _record_security(self):
            if self.verbose:
                print(f"\n🔒 Security Metrics 기록 중...")

            sanitizer = getattr(self.monitor, "input_sanitizer", None)
            leakage_det = getattr(self.monitor, "output_leakage_detector", None)
            authorizer = getattr(self.monitor, "tool_authorizer", None)

            # D8-3: enable_security=True 인데 트래커 미초기화 시 경고
            if self.enable_security and sanitizer is None:
                import warnings as _w
                _w.warn(
                    "LangChain: enable_security=True 이지만 보안 트래커가 초기화되지 않았습니다. "
                    "_ensure_security_trackers()가 호출되지 않은 것 같습니다.",
                    UserWarning,
                    stacklevel=3,
                )

            # InputSanitizationTracker
            if self.task_input and sanitizer:
                try:
                    # DQ-007: 4000자 초과 입력 truncation — evaluate_input 정규식 성능 보호
                    _safe_input = self.task_input[:4000]
                    result = sanitizer.evaluate_input(
                        task_id=self.current_task_id,
                        input_text=_safe_input,
                    )
                    if self.verbose:
                        print(f"   ✅ InputSanitization: risk={result.get('risk_level', 'low')}")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

            # OutputLeakageDetector — 최종 응답 + 도구 실행 결과 통합 스캔
            if leakage_det:
                _full_output = self.task_output
                if self._tool_outputs:
                    _full_output = self.task_output + "\n" + "\n".join(self._tool_outputs)
                if _full_output:
                    try:
                        result = leakage_det.detect_leakage(
                            task_id=self.current_task_id,
                            output_text=_full_output,
                        )
                        leaked = result.get("leakage_count", 0) > 0
                        if self.verbose:
                            extra = f" (+{len(self._tool_outputs)} tool outputs)" if self._tool_outputs else ""
                            print(f"   ✅ OutputLeakage: detected={leaked}{extra}")
                    except Exception as _e:
                        if self.verbose:
                            print(f"   ⚠️ {_e}")

            # ToolAuthorizationTracker — 각 도구 호출 검사
            if authorizer:
                for tc in self.tool_calls:
                    try:
                        authorizer.track_tool_call(
                            task_id=self.current_task_id,
                            tool_name=tc["tool_name"],
                            parameters=tc.get("parameters"),
                        )
                    except Exception as e:
                        if self.verbose:
                            print(f"   ⚠️  ToolAuthorization error: {e}")
                if self.verbose and self.tool_calls:
                    print(f"   ✅ ToolAuthorization: {len(self.tool_calls)} calls checked")

            # PrivilegeEscalationDetector
            priv_det = getattr(self.monitor, "privilege_escalation_detector", None)
            if priv_det and self.tool_calls:
                try:
                    # DQ-124: privilege_level 없는 tool_calls에 휴리스틱으로 보강
                    # privilege_level 이미 있으면 그대로 사용, 없으면 도구명 기반 추론
                    from .framework_integrations import infer_privilege_level as _infer_priv
                    _enriched_calls = [
                        {**tc, "privilege_level": tc.get("privilege_level") or _infer_priv(tc.get("tool_name", ""))}
                        for tc in self.tool_calls
                    ]
                    priv_det.analyze_privilege_chain(
                        task_id=self.current_task_id,
                        tool_calls=_enriched_calls,
                    )
                    if self.verbose:
                        print(f"   ✅ PrivilegeEscalation: analyzed")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

            # ToolChainAttackDetector
            chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
            if chain_det and self.tool_calls:
                tool_names = [tc["tool_name"] for tc in self.tool_calls]
                try:
                    chain_det.analyze_tool_chain(
                        task_id=self.current_task_id,
                        tool_sequence=tool_names,
                    )
                    if self.verbose:
                        print(f"   ✅ ToolChainAttack: analyzed")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")


class LangChainEvaluator:
    """
    LangChain 1.x Runnable 에이전트 평가 클래스 (Layer 1/2 지원)

    LCEL invoke() 인터페이스와 BaseCallbackHandler를 통해
    실행 중 메트릭을 실시간으로 수집합니다.
    """

    def __init__(
        self,
        agent,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_security: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True,
        privilege_registry: Optional[Dict[str, str]] = None,
        authorized_tools: Optional[List[str]] = None,
    ):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is not installed. "
                "Install with: pip install 'agent-evaluator[langchain]'"
            )
        self.agent = agent
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_security = enable_security
        self.task_type = task_type
        self.verbose = verbose
        self.execution_history: List[Dict[str, Any]] = []
        self._tasks_with_ground_truth: int = 0  # ground_truth 제공 횟수 추적 (Accuracy N/A 판단용)

        # authorized_tools 자동 추출: 미제공 시 agent 객체에서 자동 탐색
        if not authorized_tools:
            authorized_tools = _extract_tools_from_agent(agent)
            if authorized_tools and self.verbose:
                print(f"   ℹ️  authorized_tools 자동 추출: {authorized_tools}")
        self.authorized_tools: List[str] = list(authorized_tools or [])
        self.monitor._authorized_tools = self.authorized_tools
        if enable_security:
            _ensure_security_trackers(self.monitor, privilege_registry=privilege_registry)
        elif privilege_registry:
            self.monitor.privilege_registry = privilege_registry

        if self.verbose:
            print(f"✅ LangChainEvaluator 초기화 완료 "
                  f"(Layer2: {enable_layer2}, Security: {enable_security})")

    def run(
        self,
        query: str,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # FA7: EvaluatorProtocol 통일 인터페이스
        task_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        에이전트를 실행하고 평가 메트릭을 수집합니다.

        Args:
            query: 사용자 질문
            ground_truth: 정답 (Accuracy 계산용)
            expected_tools: 기대 도구 목록 (Layer 2 Tool Selection 평가)
            expected_elements: ResponseQuality completeness 평가용 기대 요소 목록
            expected_agents: 기대 에이전트 목록 (단일 에이전트 LangChain에서는 미사용 — 인터페이스 통일용)
            **kwargs: agent.invoke() 에 전달할 추가 인자

        Returns:
            에이전트 응답 문자열
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 LangChain 실행 시작{f' (Task ID: {task_id})' if task_id else ''}")
            print(f"{'='*70}")

        callback = AdvancedLangChainCallback(
            monitor=self.monitor,
            task_type=self.task_type,
            expected_tools=expected_tools,
            expected_elements=expected_elements,
            ground_truth=ground_truth,
            enable_layer2=self.enable_layer2,
            enable_security=self.enable_security,
            verbose=self.verbose,
            task_id=task_id,
        )

        config = kwargs.pop("config", {})
        existing_cbs = config.get("callbacks", [])
        config["callbacks"] = existing_cbs + [callback]

        # LangChain 1.x: invoke() via LCEL Runnable interface
        # I-H-002: 예외 억제 — on_chain_error()가 이미 메트릭 수집 후 호출됨
        # 다른 프레임워크(LangGraph/CrewAI/AutoGen)와 동일하게 예외 억제 + 오류 결과 반환
        _t0 = time.time()
        _invoke_error: Optional[Exception] = None
        raw = None
        try:
            raw = self.agent.invoke({"input": query}, config=config, **kwargs)
        except Exception as _e:
            _invoke_error = _e
        _execution_time = time.time() - _t0

        # 응답 추출 — dict / str / 오류 / 기타 객체 모두 처리
        if _invoke_error is not None:
            result = f"[Error: {type(_invoke_error).__name__}: {str(_invoke_error)[:200]}]"
        elif isinstance(raw, dict):
            result = (
                raw.get("output")
                or raw.get("result")
                or raw.get("answer")
                or str(raw)
            )
        else:
            result = str(raw) if raw is not None else ""

        # DQ-002: 빈 문자열 ground_truth는 유의미한 accuracy 측정 불가 — strip() 후 확인
        if ground_truth is not None and ground_truth.strip():
            self._tasks_with_ground_truth += 1
        # FA3: 표준 실행 히스토리 스키마 (UI-023: input/output 키 통일)
        self.execution_history.append({
            "task_id": callback.current_task_id or f"lc_{len(self.execution_history) + 1}",
            "timestamp": datetime.now(),
            "success": _invoke_error is None and callback.last_error is None,
            "execution_time": _execution_time,
            "framework": "langchain",
            "input": query,
            "output": result,
        })
        return result

    def run_sync(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # Protocol 통일 (LangChain에서는 미사용)
        **kwargs,
    ) -> Any:
        """run()의 동기 별칭 — EvaluatorProtocol.run_sync() 인터페이스 충족.

        ``user_input`` 은 문자열 또는 dict 모두 허용합니다.
        dict인 경우 ``to_task_string()`` 으로 문자열 추출 후 전달합니다.
        """
        from .framework_integrations import to_task_string
        return self.run(
            to_task_string(user_input),
            ground_truth=ground_truth,
            expected_tools=expected_tools,
            expected_elements=expected_elements,
            expected_agents=expected_agents,
            **kwargs,
        )

    def generate_report(self, output_path: Optional[str] = None) -> Any:
        """평가 보고서 생성"""
        if self.verbose:
            print(f"\n{'='*70}\n📊 평가 보고서 생성\n{'='*70}")

        report = self.monitor.generate_report()

        if self.verbose:
            print(f"\n🔹 Layer 1: Native Metrics")
            tcr = report.accuracy_metrics.get("tcr", {})
            acc = report.accuracy_metrics.get("accuracy_scores", {})
            lat = report.efficiency_metrics.get("latency", {})
            tok = report.efficiency_metrics.get("tokens", {})
            _acc_str = (
                f"{acc.get('overall_accuracy', 0):.1f}%"
                if self._tasks_with_ground_truth > 0
                else "N/A (no ground truth provided)"
            )
            print(f"   TCR: {tcr.get('tcr', 0):.1f}%")
            print(f"   Accuracy: {_acc_str}")
            print(f"   Avg Latency: {lat.get('avg', 0):.2f}s")
            print(f"   Total Tokens: {tok.get('total_tokens', 0)}")
            # DQ-197/198: ResponseQuality + Hallucination 결과 출력 (수집된 경우에만)
            _q = self.monitor.quality_evaluator.get_quality_metrics()
            if _q:
                print(f"   Response Quality: {_q.get('avg_total_score', 0):.2f}/5.0"
                      f"  (grade: {_q.get('avg_grade', 'N/A')})")
            _h = self.monitor.hallucination_detector.get_hallucination_rate()
            if _h and "overall_rate" in _h:
                print(f"   Hallucination Rate: {_h.get('overall_rate', 0):.1f}%")

            if self.enable_layer2:
                print(f"\n🔹 Layer 2: Agentic AI Metrics")
                tool = self.monitor.tool_selection_tracker.get_accuracy_stats()
                wf = self.monitor.workflow_tracker.calculate_execution_success_rate()
                retry = self.monitor.retry_tracker.get_retry_metrics()
                tool_eff = self.monitor.tool_analyzer.get_efficiency_stats()
                _tool_acc_str = (
                    f"{tool.get('accuracy', 0):.1f}%"
                    if tool
                    else "N/A (no expected_tools provided)"
                )
                coord = self.monitor.agent_coordination_tracker.calculate_coordination_score()
                print(f"   Tool Selection Accuracy: {_tool_acc_str}")
                print(f"   Workflow Execution Score: {wf.get('success_rate', 0):.1f}%")
                if coord:
                    print(f"   Agent Coordination Rate: {coord.get('overall_score', 0):.1f}%")
                if tool_eff:
                    print(f"   Tool Call Success Rate: {tool_eff.get('success_rate', 0):.1f}%")
                if retry:
                    print(f"   Retry Rate: {retry.get('retry_rate', 0):.1f}%  "
                          f"First-attempt Success: {retry.get('first_attempt_success_rate', 0):.1f}%")

            if self.enable_security:
                print(f"\n🔹 Security Metrics")
                sanitizer = getattr(self.monitor, "input_sanitizer", None)
                leakage_det = getattr(self.monitor, "output_leakage_detector", None)
                authorizer = getattr(self.monitor, "tool_authorizer", None)
                priv_det = getattr(self.monitor, "privilege_escalation_detector", None)
                chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
                if sanitizer:
                    sec = sanitizer.get_security_stats()
                    print(f"   Input Threat Rate: {sec.get('threat_rate', 0):.1f}%")
                if leakage_det:
                    leak = leakage_det.get_leakage_stats()
                    print(f"   Output Leakage Rate: {leak.get('leakage_rate', 0):.1f}%")
                if authorizer:
                    auth = authorizer.get_compliance_stats()
                    print(f"   Tool Compliance Rate: {auth.get('compliance_rate', 100):.1f}%")
                if priv_det:
                    priv = priv_det.get_escalation_stats()
                    print(f"   Privilege Escalation Rate: {priv.get('escalation_rate', 0):.1f}%")
                if chain_det:
                    chain = chain_det.get_attack_stats()
                    print(f"   Tool Chain Attack Rate: {chain.get('attack_rate', 0):.1f}%")

        if output_path:
            self.monitor.save_to_file(output_path)
            if self.verbose:
                print(f"\n💾 보고서 저장: {output_path}")

        return report

    def reset(self) -> None:
        """실행 이력과 내부 카운터를 초기화합니다. 같은 인스턴스로 새 평가 세션을 시작할 때 사용하세요."""
        self.execution_history = []
        self._tasks_with_ground_truth = 0

    def track_workflow_step(
        self,
        step_name: str,
        success: bool = True,
        duration: float = 0.0,
        agent_name: str = "",
    ) -> None:
        """워크플로우 단계를 수동으로 추적합니다. LangChain 콜백 외부에서 커스텀 스텝을 기록할 때 사용하세요."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step_name,
            step_type="task_completion",
            success=success,
            execution_time=duration,
            framework="langchain",
            metadata={"agent": agent_name} if agent_name else {},
        )

    def track_agent_interaction(
        self,
        from_agent: str,
        to_agent: str,
        interaction_type: str = "delegation",
        success: bool = True,
    ) -> None:
        """에이전트 간 상호작용을 수동으로 추적합니다."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            interaction_type=interaction_type,
            success=success,
        )

    def track_tool_usage(
        self,
        tool_name: str,
        success: bool = True,
        duration: float = 0.0,
        parameters: Optional[Dict[str, Any]] = None,
        execution_result: str = "",
    ) -> None:
        """도구 사용을 수동으로 추적합니다."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.tool_analyzer.analyze_execution(
            task_id=task_id,
            tool_calls=[{
                "tool_name": tool_name,
                "success": success,
                "duration": duration,
                "parameters": parameters or {},
                "execution_result": execution_result,
            }],
        )

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_executions": len(self.execution_history),
            "successful_executions": sum(1 for h in self.execution_history if h["success"]),
            "average_duration": (
                sum(h.get("execution_time", 0.0) for h in self.execution_history) / len(self.execution_history)
                if self.execution_history else 0.0
            ),
            "layer2_enabled": self.enable_layer2,
            "security_enabled": self.enable_security,
        }


def create_evaluated_langchain_agent(
    agent,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> LangChainEvaluator:
    """LangChain 에이전트를 평가 래퍼로 감싸는 편의 함수"""
    return LangChainEvaluator(
        agent=agent,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )
