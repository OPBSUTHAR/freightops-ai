"""Orchestrator: planner -> executor -> reviewer, with persisted audit trail."""
from __future__ import annotations

import re
from typing import Any

from ..config import settings
from ..store import new_id
from .executor import Executor
from .planner import build_plan
from .reviewer import review
from .runtime import RunContext, utc_now
from .tools import build_registry


def _shipment_snapshot(shipment: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "ref", "customer", "origin", "destination", "mode", "carrier", "carrier_code", "buy", "sell", "margin_pct", "status", "eta", "risk", "documents", "exception_ids")
    return {k: shipment.get(k) for k in keep if k in shipment}


def _rate_snapshot(rate: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": rate.get("lane"),
        "benchmark_buy": rate.get("benchmark_buy"),
        "options": rate.get("options", [])[:6],
        "fuel_surcharge_pct": rate.get("fuel_surcharge_pct"),
        "accessorials": rate.get("accessorials", []),
    }


def _artifacts(ctx: RunContext) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if ctx.artifacts.get("quote"):
        out["quote"] = ctx.artifacts["quote"]
    if ctx.artifacts.get("rate"):
        out["rate"] = _rate_snapshot(ctx.artifacts["rate"])
    if ctx.artifacts.get("shipment"):
        out["shipment"] = _shipment_snapshot(ctx.artifacts["shipment"])
    if ctx.artifacts.get("document"):
        doc = ctx.artifacts["document"]
        out["document"] = {
            "id": doc.get("id"),
            "kind": doc.get("kind"),
            "filename": doc.get("filename"),
            "status": doc.get("status"),
            "confidence": doc.get("confidence"),
            "fields": doc.get("fields"),
            "validations": doc.get("validations"),
        }
    if ctx.artifacts.get("risk"):
        out["risk"] = ctx.artifacts["risk"]
    if ctx.artifacts.get("exceptions") is not None:
        out["exceptions"] = ctx.artifacts["exceptions"]
    if ctx.artifacts.get("policy_hits"):
        out["policy_hits"] = ctx.artifacts["policy_hits"]
    return out


class Orchestrator:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.registry = build_registry(store)
        self.executor = Executor(self.registry)

    async def run(self, goal: str, shipment_ref: str | None = None) -> dict[str, Any]:
        if not shipment_ref:
            match = re.search(r"\bFO-\d{4,6}\b", goal, re.I)
            shipment_ref = match.group(0).upper() if match else None

        shipment = None
        if shipment_ref:
            rows = await self.store.find("shipments", where={"ref": shipment_ref})
            shipment = rows[0] if rows else None

        run_id = new_id("run")
        started = utc_now()
        ctx = RunContext(run_id=run_id, goal=goal, store=self.store, shipment_ref=shipment_ref)
        ctx.emit("planner-agent", "Planning run", detail=goal)

        plan, usage = await build_plan(goal, shipment, shipment_ref, self.registry.specs())
        ctx.entities = plan["entities"]
        tokens = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
        ctx.tokens += tokens
        ctx.emit(
            "planner-agent",
            "Plan ready",
            status="ok",
            detail=f"{len(plan['steps'])} steps via {plan['planner']} for intent '{plan['intent']}'",
            cost_usd=float(usage.get("cost_usd", 0.0)),
            meta={"tokens": tokens},
        )

        run: dict[str, Any] = {
            "id": run_id,
            "goal": goal,
            "intent": plan["intent"],
            "shipment_ref": shipment_ref,
            "planner": plan["planner"],
            "plan": plan,
            "steps": [],
            "traces": ctx.traces,
            "artifacts": {},
            "review": None,
            "status": "running",
            "tokens": ctx.tokens,
            "cost_usd": 0.0,
            "started_at": started,
            "finished_at": None,
        }
        await self.store.insert("agent_runs", run)

        await self.executor.execute(ctx, plan)

        review_result = await review(ctx)
        for step in plan["steps"]:
            if step.get("deferred"):
                step["status"] = "done"
                step["detail"] = review_result["summary"]
        ctx.emit("reviewer-agent", "Policy audit complete", status=review_result["verdict"], detail=review_result["summary"])

        status = {"approve": "completed", "needs_approval": "needs_approval", "escalate": "escalated"}[review_result["verdict"]]
        artifacts = _artifacts(ctx)
        final_ref = (artifacts.get("shipment") or {}).get("ref") or shipment_ref

        run.update(
            {
                "plan": plan,
                "steps": ctx.steps,
                "traces": ctx.traces,
                "artifacts": artifacts,
                "review": review_result,
                "status": status,
                "shipment_ref": final_ref,
                "tokens": ctx.tokens,
                "cost_usd": round(ctx.cost_usd, 6),
                "finished_at": utc_now(),
            }
        )
        await self.store.update("agent_runs", run_id, run)
        return run

    async def decide(self, run_id: str, approved: bool, note: str | None = None, actor: str = "operator") -> dict[str, Any]:
        run = await self.store.get("agent_runs", run_id)
        if not run:
            return {"error": "run not found"}
        if run["status"] not in ("needs_approval", "escalated"):
            return {"error": f"run is {run['status']}, not awaiting approval"}
        shipment_ref = (run.get("artifacts", {}).get("shipment") or {}).get("ref") or run.get("shipment_ref")
        rows = await self.store.find("shipments", where={"ref": shipment_ref}) if shipment_ref else []
        shipment = rows[0] if rows else None

        now = utc_now()
        decision = {"approved": approved, "actor": actor, "note": note or "", "at": now}
        if shipment:
            await self.store.update(
                "shipments",
                shipment["id"],
                {
                    "status": "booked" if approved else "cancelled",
                    "booking_status": "confirmed" if approved else "rejected",
                    "approval": decision,
                },
            )
            if shipment.get("quote_id"):
                quote = await self.store.find("quotes", where={"quote_id": shipment["quote_id"]})
                if quote:
                    await self.store.update("quotes", quote[0]["id"], {"status": "booked" if approved else "rejected", "approval": decision})

        review = run.get("review") or {}
        review["human_decision"] = decision
        review["verdict"] = "approved_by_human" if approved else "rejected_by_human"
        run["status"] = "completed" if approved else "rejected"
        run["review"] = review
        snapshot = (run.get("artifacts") or {}).get("shipment")
        if snapshot:
            snapshot["status"] = "booked" if approved else "cancelled"
            snapshot["booking_status"] = "confirmed" if approved else "rejected"
        run["finished_at"] = now
        run.setdefault("traces", []).append(
            {
                "seq": len(run.get("traces", [])) + 1,
                "agent": "human",
                "action": "Approval granted" if approved else "Approval rejected",
                "tool": None,
                "status": "ok" if approved else "rejected",
                "detail": (note or ("Auto-book cap approved" if approved else "Rejected by operator"))[:280],
                "latency_ms": 0,
                "cost_usd": 0.0,
                "at": now,
            }
        )
        if approved:
            plan = run.get("plan") or {}
            for step in plan.get("steps", []):
                if step.get("status") == "skipped" and "approval" in (step.get("detail") or "").lower():
                    step["status"] = "deferred_to_human"
        await self.store.update("agent_runs", run_id, run)
        return run


def orchestrator_for(store: Any) -> Orchestrator:
    return Orchestrator(store)


__all__ = ["Orchestrator", "orchestrator_for", "settings"]
