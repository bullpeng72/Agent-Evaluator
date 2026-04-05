"""
agent_evaluator.integrations.llm_judge
=======================================
LLM-as-Judge evaluation engine.

Evaluates agent responses on three dimensions without requiring ground_truth:
  - completeness  (0–5): Is the response complete and thorough?
  - relevance     (0–5): Does the response address the question?
  - factual_consistency (0–5): Is the response internally consistent and plausible?

Supports Claude (Haiku / Sonnet) and OpenAI (gpt-4o-mini / gpt-4o) models.
Cost is controlled via ``sample_rate`` (fraction of tasks to judge) and
``budget_per_day`` (USD hard cap, tracked in-memory per process lifetime).

Usage:
    >>> from agent_evaluator.integrations.llm_judge import LLMJudge
    >>> judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.1)
    >>> result = judge.judge("t1", question="한국의 수도는?", response="서울입니다.")
    >>> print(result["scores"])
    {'completeness': 4, 'relevance': 5, 'factual_consistency': 5, 'overall': 4.67}
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import warnings
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing (USD per 1 000 tokens) — used for budget tracking
# ---------------------------------------------------------------------------
_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.00025, "output": 0.00125},
    "claude-haiku-4-5":          {"input": 0.00025, "output": 0.00125},
    "claude-sonnet-4-6":         {"input": 0.003,   "output": 0.015},
    "claude-opus-4-6":           {"input": 0.015,   "output": 0.075},
    "gpt-4o-mini":               {"input": 0.00015, "output": 0.0006},
    "gpt-4o":                    {"input": 0.005,   "output": 0.015},
}
_DEFAULT_PRICING = {"input": 0.001, "output": 0.004}

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are an impartial evaluator assessing AI agent responses.
Score the response on three dimensions (integer 0–5 each):

1. completeness       — Does the response fully address all aspects of the question?
   0 = completely ignores the question
   5 = thorough and complete

2. relevance          — Does the response stay on-topic and directly answer the question?
   0 = entirely off-topic
   5 = perfectly focused

3. factual_consistency — Is the response internally consistent, plausible, and free of
   obvious contradictions?
   0 = self-contradictory or clearly wrong
   5 = coherent and plausible

Return ONLY valid JSON with this exact structure:
{
  "completeness": <int 0-5>,
  "relevance": <int 0-5>,
  "factual_consistency": <int 0-5>,
  "reasoning": "<one sentence explanation>"
}
"""

def _resolve_default_model() -> str:
    """
    Settings에서 사용 가능한 API 키와 모델명을 읽어 기본 judge 모델을 결정한다.

    우선순위:
      1. OPENAI_API_KEY 설정됨  → OPENAI_MODEL (기본: gpt-4o-mini)
      2. ANTHROPIC_API_KEY 설정됨 → ANTHROPIC_MODEL (기본: claude-haiku-4-5-20251001)
      3. 둘 다 없으면 → "gpt-4o-mini" (사용 시 오류 메시지로 안내)
    """
    try:
        from ..config import get_settings
        s = get_settings()
        if s.has_openai():
            return s.openai_model
        if s.has_anthropic():
            return s.anthropic_model
    except Exception as _e:
        logger.debug("설정에서 모델 이름 조회 실패 (무시): %s", _e)
    return "gpt-4o-mini"


def _build_user_message(question: str, response: str, context: Optional[str] = None) -> str:
    parts = [f"QUESTION:\n{question}", f"\nAGENT RESPONSE:\n{response}"]
    if context:
        parts.insert(1, f"\nCONTEXT:\n{context[:1500]}")  # cap context
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLMJudge
# ---------------------------------------------------------------------------
class LLMJudge:
    """
    LLM-as-Judge scoring engine.

    Args:
        model: LLM model ID.  ``None`` (default) → ``agent-eval init``으로 설정한
               API 키와 모델명(OPENAI_MODEL / ANTHROPIC_MODEL)에서 자동 결정.
               명시적으로 지정할 경우 해당 모델을 사용.
               지원 모델 예시:
               - OpenAI : ``gpt-4o-mini``, ``gpt-4o``
               - Claude : ``claude-haiku-4-5-20251001``, ``claude-sonnet-4-6``
        sample_rate: Fraction of tasks to actually judge (0.0–1.0).
                     1.0 = judge every task, 0.1 = judge ~10 % of tasks.
        budget_per_day: Optional USD hard cap per calendar day.  When the
                        cumulative cost exceeds this limit, judging is skipped
                        and a warning is emitted.
        seed: Random seed for deterministic sampling (tests / reproducibility).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        sample_rate: float = 0.1,
        budget_per_day: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> None:
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError(f"sample_rate must be in [0, 1]; got {sample_rate}")

        # model=None → agent-eval init 설정(OPENAI_MODEL / ANTHROPIC_MODEL)에서 자동 결정
        self.model = model if model is not None else _resolve_default_model()
        self.sample_rate = sample_rate
        self.budget_per_day = budget_per_day

        self._rng = random.Random(seed)
        self._pricing = _MODEL_PRICING.get(self.model, _DEFAULT_PRICING)

        # In-memory daily budget tracking (resets on a new calendar day)
        self._budget_day: Optional[date] = None
        self._budget_spent: float = 0.0

        # Results store: task_id → judge result dict
        self.results: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def judge(
        self,
        task_id: str,
        question: str,
        response: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Judge a single task response.

        Sampling is applied: if ``random() > sample_rate`` the call is skipped
        and ``{"skipped": True}`` is returned.

        Args:
            task_id:  Unique task identifier.
            question: The original user question / prompt.
            response: The agent's response to judge.
            context:  Optional retrieved context (RAG) — improves factual_consistency scoring.

        Returns:
            Dict with keys:
              - ``task_id``
              - ``scores``: {completeness, relevance, factual_consistency, overall}
              - ``reasoning``: one-sentence explanation from the judge
              - ``model``: model used
              - ``cost_usd``: estimated API call cost
              - ``skipped``: True if sampling decided to skip this task
              - ``error``: error message if the API call failed (scores will be None)
        """
        # Sampling gate
        if self._rng.random() > self.sample_rate:
            return {"task_id": task_id, "skipped": True}

        # Budget gate
        if not self._check_budget():
            warnings.warn(
                f"LLMJudge: daily budget of ${self.budget_per_day:.2f} reached. "
                "Skipping judge call.",
                RuntimeWarning,
                stacklevel=2,
            )
            return {"task_id": task_id, "skipped": True, "reason": "budget_exceeded"}

        # Run the judge
        result = self._call_judge(task_id, question, response, context)
        self.results.append(result)
        return result

    def get_summary(self) -> Dict[str, Any]:
        """
        Aggregate summary of all judge results collected so far.

        Returns:
            Dict with avg scores, count, total_cost_usd.
        """
        judged = [r for r in self.results if not r.get("skipped") and not r.get("error") and r.get("scores")]
        if not judged:
            return {"count": 0, "avg_scores": {}, "total_cost_usd": 0.0}

        dims = ["completeness", "relevance", "factual_consistency", "overall", "confidence"]
        avg_scores = {}
        for dim in dims:
            vals = [r["scores"][dim] for r in judged if r.get("scores") and dim in r["scores"]]
            avg_scores[dim] = round(sum(vals) / len(vals), 3) if vals else 0.0

        total_cost = sum(r.get("cost_usd", 0.0) for r in judged)

        return {
            "count": len(judged),
            "avg_scores": avg_scores,
            "total_cost_usd": round(total_cost, 6),
            "results": judged,
        }

    def register_prompt_to_phoenix(
        self,
        prompt_name: str = "agent-eval-judge",
        phoenix_endpoint: str = "http://localhost:6006",
    ) -> Optional[str]:
        """현재 LLMJudge 채점 프롬프트를 Phoenix Prompts에 등록한다.

        Phoenix UI → Prompts 탭에서 버전 이력 확인 및 Playground 연동이 가능해진다.
        프롬프트 변경 시 재호출하면 Phoenix에서 버전 diff를 추적한다.

        Args:
            prompt_name: Phoenix Prompts 탭에 표시될 이름.
            phoenix_endpoint: Phoenix 서버 주소 (기본: http://localhost:6006).

        Returns:
            생성된 prompt_id 문자열. 실패 시 None.

        Example::
            judge = LLMJudge(model="gpt-4o-mini", sample_rate=0.1)
            prompt_id = judge.register_prompt_to_phoenix("qa-judge-v1")
        """
        import urllib.error
        import urllib.request

        # Phoenix v1/prompts API 스키마:
        # prompt: {name, description}
        # version: {model_provider, model_name, template, template_type,
        #           template_format, invocation_parameters, description}
        model_provider = "OPENAI" if self.model.startswith("gpt") else "ANTHROPIC"
        inv_type = "openai" if model_provider == "OPENAI" else "anthropic"
        inv_content: Dict[str, Any] = {"temperature": 0.0, "max_tokens": 512}
        payload = json.dumps({
            "prompt": {
                "name": prompt_name,
                "description": (
                    f"Agent Evaluator LLMJudge — model: {self.model}. "
                    "Scores completeness / relevance / factual_consistency (0–5 each)."
                ),
            },
            "version": {
                "model_provider": model_provider,
                "model_name": self.model,
                "template": {
                    "type": "chat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "QUESTION:\n{{question}}\n\n"
                                "AGENT RESPONSE:\n{{response}}\n\n"
                                "{{#if context}}CONTEXT:\n{{context}}{{/if}}"
                            ),
                        },
                    ],
                },
                "template_type": "CHAT",
                "template_format": "MUSTACHE",
                "invocation_parameters": {
                    "type": inv_type,
                    inv_type: inv_content,
                },
                "description": f"v1 — completeness/relevance/factual_consistency | model={self.model}",
            },
        }).encode()

        url = f"{phoenix_endpoint.rstrip('/')}/v1/prompts"
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
                prompt_id: Optional[str] = (
                    result.get("data", {}).get("id")
                    or result.get("id")
                )
                logger.info(
                    "Phoenix Prompts 등록 완료: %s (id=%s)", prompt_name, prompt_id
                )
                return prompt_id
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception as _e:
                logger.debug("HTTP 오류 body 읽기 실패 (무시): %s", _e)
            logger.warning("Phoenix Prompts API 오류 (HTTP %d): %s", e.code, body)
            return None
        except Exception as exc:
            logger.debug("register_prompt_to_phoenix: 연결 실패: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_budget(self) -> bool:
        """Return True if we are within the daily budget (or no budget set)."""
        if self.budget_per_day is None:
            return True
        today = date.today()
        if self._budget_day != today:
            self._budget_day = today
            self._budget_spent = 0.0
        return self._budget_spent < self.budget_per_day

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost = (
            input_tokens / 1000 * self._pricing["input"]
            + output_tokens / 1000 * self._pricing["output"]
        )
        self._budget_spent += cost
        return round(cost, 8)

    def _call_judge(
        self,
        task_id: str,
        question: str,
        response: str,
        context: Optional[str],
    ) -> Dict[str, Any]:
        """Dispatch to the correct provider."""
        model_lower = self.model.lower()
        if "claude" in model_lower:
            return self._call_claude(task_id, question, response, context)
        elif "gpt" in model_lower or "openai" in model_lower:
            return self._call_openai(task_id, question, response, context)
        else:
            return {
                "task_id": task_id,
                "skipped": False,
                "error": f"Unsupported model: {self.model}",
                "scores": None,
            }

    def _parse_judge_response(self, task_id: str, raw_text: str, cost: float) -> Dict[str, Any]:
        """Parse JSON from the judge's response."""
        try:
            # Strip markdown fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())

            completeness = max(0, min(5, int(data.get("completeness", 0))))
            relevance = max(0, min(5, int(data.get("relevance", 0))))
            factual = max(0, min(5, int(data.get("factual_consistency", 0))))
            overall = round((completeness + relevance + factual) / 3, 3)

            import math as _math
            _scores_3 = [completeness, relevance, factual]
            _variance = sum((_s - overall) ** 2 for _s in _scores_3) / 3.0
            _std = _math.sqrt(_variance)
            confidence = round(max(0.0, min(1.0, 1.0 - _std / 2.5)), 3)

            return {
                "task_id": task_id,
                "skipped": False,
                "scores": {
                    "completeness": completeness,
                    "relevance": relevance,
                    "factual_consistency": factual,
                    "overall": overall,
                    "confidence": confidence,
                },
                "reasoning": data.get("reasoning", ""),
                "model": self.model,
                "cost_usd": cost,
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("LLMJudge: failed to parse response for %s: %s | raw=%r", task_id, e, raw_text[:200])
            return {
                "task_id": task_id,
                "skipped": False,
                "error": f"parse_error: {e}",
                "scores": None,
                "model": self.model,
                "cost_usd": cost,
            }

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _call_claude(
        self,
        task_id: str,
        question: str,
        response: str,
        context: Optional[str],
    ) -> Dict[str, Any]:
        try:
            import anthropic
        except ImportError:
            return {
                "task_id": task_id,
                "skipped": False,
                "error": "anthropic library not installed. Run: pip install anthropic",
                "scores": None,
            }

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "task_id": task_id,
                "skipped": False,
                "error": "ANTHROPIC_API_KEY not set",
                "scores": None,
            }

        try:
            client = anthropic.Anthropic(api_key=api_key)
            user_msg = _build_user_message(question, response, context)

            msg = client.messages.create(
                model=self.model,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw = msg.content[0].text if msg.content else ""
            in_tok = msg.usage.input_tokens if hasattr(msg, "usage") else 500
            out_tok = msg.usage.output_tokens if hasattr(msg, "usage") else 100
            cost = self._estimate_cost(in_tok, out_tok)
            return self._parse_judge_response(task_id, raw, cost)

        except Exception as e:
            logger.warning("LLMJudge Claude call failed for %s: %s", task_id, e)
            return {
                "task_id": task_id,
                "skipped": False,
                "error": str(e),
                "scores": None,
                "model": self.model,
                "cost_usd": 0.0,
            }

    def _call_openai(
        self,
        task_id: str,
        question: str,
        response: str,
        context: Optional[str],
    ) -> Dict[str, Any]:
        try:
            import openai
        except ImportError:
            return {
                "task_id": task_id,
                "skipped": False,
                "error": "openai library not installed. Run: pip install openai",
                "scores": None,
            }

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "task_id": task_id,
                "skipped": False,
                "error": "OPENAI_API_KEY not set",
                "scores": None,
            }

        try:
            client = openai.OpenAI(api_key=api_key)
            user_msg = _build_user_message(question, response, context)

            completion = client.chat.completions.create(
                model=self.model,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )

            raw = completion.choices[0].message.content or ""
            usage = completion.usage
            in_tok = usage.prompt_tokens if usage else 500
            out_tok = usage.completion_tokens if usage else 100
            cost = self._estimate_cost(in_tok, out_tok)
            return self._parse_judge_response(task_id, raw, cost)

        except Exception as e:
            logger.warning("LLMJudge OpenAI call failed for %s: %s", task_id, e)
            return {
                "task_id": task_id,
                "skipped": False,
                "error": str(e),
                "scores": None,
                "model": self.model,
                "cost_usd": 0.0,
            }
