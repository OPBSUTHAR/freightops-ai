"""Shared run context and trace primitives."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunContext:
    run_id: str
    goal: str
    store: Any
    shipment_ref: str | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    traces: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    cost_usd: float = 0.0
    blocked: bool = False
    requires_approval: bool = False
    seq: int = 0

    def emit(
        self,
        agent: str,
        action: str,
        *,
        tool: str | None = None,
        status: str = "ok",
        detail: str = "",
        latency_ms: int = 0,
        cost_usd: float = 0.0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        event = {
            "seq": self.seq,
            "agent": agent,
            "action": action,
            "tool": tool,
            "status": status,
            "detail": detail[:280],
            "latency_ms": latency_ms,
            "cost_usd": round(cost_usd, 6),
            "at": utc_now(),
        }
        if meta:
            event["meta"] = meta
        self.traces.append(event)
        self.cost_usd += cost_usd
        return event
