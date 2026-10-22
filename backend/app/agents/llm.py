"""Optional LLM adapter (OpenAI-compatible: OpenAI, Groq, OpenRouter, Ollama, vLLM).

The control tower never requires a model. When `LLM_MODE` is not `rules` and a
key is configured, the planner asks the model for a plan and validates it against
the tool catalog. Any failure falls back to the deterministic planner.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import settings
from .prompts import PLANNER_SYSTEM, PLANNER_USER

PRICES_PER_MTOK = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "llama3.1": (0.0, 0.0),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = PRICES_PER_MTOK.get(model, (0.50, 1.50))
    return round(prompt_tokens / 1_000_000 * inp + completion_tokens / 1_000_000 * out, 6)


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no json object in response")
    return json.loads(content[start : end + 1])


class LLMClient:
    def __init__(self) -> None:
        self.enabled = settings.llm_enabled
        self.mode = settings.llm_mode

    async def plan(self, goal: str, context: dict[str, Any], tools: list[dict[str, str]]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        tool_lines = "\n".join(f"- {t['name']}: {t['description']}" for t in tools)
        user = PLANNER_USER.format(goal=goal, context=json.dumps(context, default=str), tools=tool_lines)
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": PLANNER_SYSTEM},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                response.raise_for_status()
                payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            plan = _parse_json(content)
            plan["planner"] = f"llm:{payload.get('model', settings.llm_model)}"
            plan["usage"] = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "cost_usd": estimate_cost(settings.llm_model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            }
            return plan
        except Exception as exc:  # network, auth, bad json - never break a run
            return {"error": f"{type(exc).__name__}: {exc}"[:200]}


llm_client = LLMClient()
