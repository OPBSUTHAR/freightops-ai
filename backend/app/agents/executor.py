"""Executor agent: runs plan steps, retries transient failures, emits traces."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from .runtime import RunContext
from .tools import ToolRegistry

MAX_ATTEMPTS = 2


def _resolve(value: Any, ctx: RunContext) -> Any:
    shipment = ctx.artifacts.get("shipment") or {}
    quote = ctx.artifacts.get("quote") or {}
    document = ctx.artifacts.get("document") or {}
    tokens = {
        "$shipment": shipment.get("ref") or ctx.shipment_ref,
        "$shipment_ref": shipment.get("ref") or ctx.shipment_ref,
        "$quote_id": quote.get("quote_id"),
        "$quote": quote.get("id"),
        "$document_id": document.get("id"),
    }
    if isinstance(value, str):
        return tokens.get(value, value)
    if isinstance(value, list):
        return [_resolve(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, ctx) for k, v in value.items()}
    return value


def _trim(result: dict[str, Any]) -> dict[str, Any]:
    """Keep run documents small: replace embedded records with references."""
    out: dict[str, Any] = {}
    for key, value in result.items():
        if key in ("shipment", "document") and isinstance(value, dict):
            out[key] = {k: value.get(k) for k in ("id", "ref", "kind", "status", "confidence", "filename") if value.get(k) is not None}
        elif key == "rate" and isinstance(value, dict):
            out[key] = {
                "lane": value.get("lane"),
                "benchmark_buy": value.get("benchmark_buy"),
                "options": value.get("options"),
            }
        else:
            out[key] = value
    return out


class Executor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, ctx: RunContext, plan: dict[str, Any]) -> None:
        paused = False

        for step in plan["steps"]:
            if step.get("deferred"):
                continue
            if paused:
                step["status"] = "skipped"
                step["detail"] = "Paused for human approval"
                continue

            args = _resolve(step.get("args") or {}, ctx)
            result: dict[str, Any] = {}
            latency = 0
            for attempt in range(MAX_ATTEMPTS):
                started = perf_counter()
                try:
                    result = await self.registry.call(step["tool"], ctx, **args)
                except Exception as exc:  # tool crashes must not kill the run
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                latency = int((perf_counter() - started) * 1000)
                if result.get("ok") or result.get("blocking") or result.get("blocked") or attempt + 1 >= MAX_ATTEMPTS:
                    break
                ctx.emit(
                    step["agent"],
                    "Retrying after transient tool error",
                    tool=step["tool"],
                    status="retry",
                    detail=str(result.get("error", "")),
                    latency_ms=latency,
                )

            ok = bool(result.get("ok"))
            blocked = bool(result.get("blocking") or result.get("blocked"))
            status = "ok" if ok else "blocked" if blocked else "failed"
            summary = str(result.get("summary") or result.get("error") or "completed")

            step.update(
                {
                    "status": status,
                    "detail": summary[:280],
                    "latency_ms": latency,
                    "result": _trim(result),
                }
            )
            ctx.steps.append(step)
            ctx.emit(
                step["agent"],
                step["action"],
                tool=step["tool"],
                status=status,
                detail=summary,
                latency_ms=latency,
            )

            if result.get("requires_approval"):
                ctx.requires_approval = True
            if result.get("stop_run") or blocked and step["tool"] == "check_guardrails":
                ctx.blocked = True
                self._skip_remaining(plan, step["id"], "Skipped: guardrail blocked the run")
                break
            if result.get("pause_run"):
                paused = True
                self._skip_remaining(plan, step["id"], "Skipped: waiting for human approval")
                ctx.emit(
                    "orchestrator",
                    "Run paused for human-in-the-loop approval",
                    status="paused",
                    detail="Booking exceeds the auto-book cap. A human must approve before tendering.",
                )
                break

    @staticmethod
    def _skip_remaining(plan: dict[str, Any], after_id: int, reason: str) -> None:
        for later in plan["steps"]:
            if later["id"] > after_id and not later.get("deferred") and later.get("status") == "pending":
                later["status"] = "skipped"
                later["detail"] = reason
