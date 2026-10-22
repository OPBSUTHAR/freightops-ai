"""Planner agent.

Builds an explicit, auditable plan. Deterministic by default; when a model is
configured the plan is proposed by the model and then validated against the tool
catalog, with automatic fallback to the deterministic plan.
"""
from __future__ import annotations

import re
from typing import Any

from ..domain.rates import CITIES
from .llm import llm_client

CITY_STATE = {
    "chicago": "IL", "dallas": "TX", "atlanta": "GA", "los angeles": "CA", "newark": "NJ",
    "memphis": "TN", "columbus": "OH", "denver": "CO", "seattle": "WA", "miami": "FL",
    "houston": "TX", "phoenix": "AZ", "kansas city": "MO", "charlotte": "NC",
    "indianapolis": "IN", "laredo": "TX", "detroit": "MI", "savannah": "GA",
}

LANE_RE = re.compile(
    r"(" + "|".join(re.escape(city.title()) for city in sorted(CITIES, key=len, reverse=True)) + r")\s*,\s*([A-Z]{2})\s*(?:to|->|→)\s*("
    + "|".join(re.escape(city.title()) for city in sorted(CITIES, key=len, reverse=True))
    + r")\s*,\s*([A-Z]{2})",
    re.I,
)
WEIGHT_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:lb|lbs|pounds)", re.I)
MODE_WORDS = {"ftl": "FTL", "truckload": "FTL", "ltl": "LTL", "parcel": "Parcel", "intermodal": "Intermodal"}


def _entities(goal: str, shipment: dict[str, Any] | None) -> dict[str, Any]:
    entities: dict[str, Any] = {
        "origin": "Chicago, IL",
        "destination": "Dallas, TX",
        "mode": "LTL",
        "weight_lb": 1200,
        "commodity": "General freight",
        "customer": "Acme Distribution",
    }
    lane = LANE_RE.search(goal)
    if lane:
        entities.update(
            {
                "origin": f"{lane.group(1).title()}, {lane.group(2).upper()}",
                "destination": f"{lane.group(3).title()}, {lane.group(4).upper()}",
            }
        )
    else:
        hits = [(m.start(), key) for key in CITIES for m in re.finditer(rf"\b{re.escape(key)}\b", goal, re.I)]
        hits.sort()
        if len(hits) >= 2:
            entities["origin"] = f"{hits[0][1].title()}, {CITY_STATE.get(hits[0][1], '')}".strip(", ")
            entities["destination"] = f"{hits[1][1].title()}, {CITY_STATE.get(hits[1][1], '')}".strip(", ")

    lowered = goal.lower()
    for word, mode in MODE_WORDS.items():
        if word in lowered:
            entities["mode"] = mode
            break
    weight = WEIGHT_RE.search(goal)
    if weight:
        entities["weight_lb"] = float(weight.group(1).replace(",", ""))

    if shipment:
        entities.update(
            {
                "origin": shipment["origin"],
                "destination": shipment["destination"],
                "mode": shipment["mode"],
                "weight_lb": shipment["weight_lb"],
                "commodity": shipment["commodity"],
                "customer": shipment["customer"],
                "carrier_code": shipment["carrier_code"],
            }
        )
    return entities


def _intent(goal: str, shipment: dict[str, Any] | None) -> str:
    lowered = goal.lower()
    if any(word in lowered for word in ("track", "where is", "eta", "status update", "trace")):
        return "track"
    if any(word in lowered for word in ("invoice", "packing list", "bill of lading", "extract", "document", "ocr")):
        return "documents"
    if "exception" in lowered:
        return "exceptions"
    if any(word in lowered for word in ("book", "tender", "ship it", "autopilot", "full run", "end to end")):
        return "full" if any(w in lowered for w in ("autopilot", "full", "end to end")) else "book"
    if any(word in lowered for word in ("quote", "rate", "price")):
        return "quote"
    return "track" if shipment else "quote"


def _step(agent: str, action: str, tool: str | None, args: dict[str, Any], why: str, *, deferred: bool = False) -> dict[str, Any]:
    return {"agent": agent, "action": action, "tool": tool, "args": args, "why": why, "deferred": deferred, "status": "pending"}


def _reviewer_step() -> dict[str, Any]:
    return _step(
        "reviewer-agent",
        "Audit plan against policy and risk",
        None,
        {},
        "Independent review is mandatory before a run can be marked complete.",
        deferred=True,
    )


def deterministic_plan(intent: str, goal: str, entities: dict[str, Any], shipment_ref: str | None) -> list[dict[str, Any]]:
    lane_args = {k: entities[k] for k in ("origin", "destination", "mode", "weight_lb", "commodity", "customer") if k in entities}
    ref = shipment_ref or "FO-4821"
    steps: list[dict[str, Any]] = []

    if intent in ("quote", "book", "full"):
        steps += [
            _step("quoting-agent", "Resolve lane and pull carrier rates", "rate_lane", lane_args, "Pricing must come from the carrier panel, never from the model."),
            _step("quoting-agent", "Retrieve accessorial and margin policy", "search_policy", {"query": "accessorial charges, margin floor and auto-book approval cap"}, "Cite the tariff before quoting."),
            _step("quoting-agent", "Draft quote from recommended carrier", "draft_quote", {"margin_pct": 18.0}, "Target margin is 18% with a 12% hard floor."),
            _step("reviewer-agent", "Run pricing guardrails", "check_guardrails", {}, "Margin, carrier reliability and auto-book cap are hard gates."),
        ]
    if intent in ("book", "full"):
        steps.append(_step("booking-agent", "Tender load and create shipment", "book_shipment", {}, "Booking writes the shipment of record and audit trail."))
    if intent in ("track", "book", "full"):
        if intent == "track":
            steps.append(_step("tracking-agent", "Load shipment of record", "get_shipment", {"ref": ref}, "Tracking needs the booked record and SLA."))
        track_ref = "$shipment" if intent in ("book", "full") else ref
        steps.append(_step("tracking-agent", "Sync latest scan and score ETA risk", "sync_tracking", {"shipment_ref": track_ref}, "Every active load is tracked at least every 2 hours."))
        steps.append(_step("exceptions-agent", "Review open exceptions", "list_exceptions", {"shipment_ref": track_ref}, "Unresolved high/critical exceptions block completion."))
    if intent == "documents":
        steps += [
            _step("documents-agent", "Extract invoice fields", "extract_document", {"sample": "invoice", "shipment_ref": ref}, "Structured extraction with per-field confidence."),
            _step("documents-agent", "Three-way match and post to ERP", "post_invoice", {}, "Posting is blocked unless documents reconcile."),
            _step("exceptions-agent", "Review document exceptions", "list_exceptions", {"shipment_ref": ref}, "Mismatches must be visible to the ops desk."),
        ]
    if intent == "exceptions":
        steps += [
            _step("exceptions-agent", "Load open exceptions", "list_exceptions", {"shipment_ref": ref}, "Triage starts from the open queue."),
            _step("exceptions-agent", "Run auto-resolve playbook", "resolve_exception", {}, "Only low/medium exceptions may auto-resolve."),
        ]
    steps.append(_reviewer_step())
    return steps


def _validate_llm_steps(raw: Any, allowed: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    steps = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if tool not in allowed:
            continue
        steps.append(
            _step(
                str(item.get("agent") or "executor-agent")[:40],
                str(item.get("action") or "Run tool")[:80],
                tool,
                item.get("args") if isinstance(item.get("args"), dict) else {},
                str(item.get("why") or "")[:160],
            )
        )
    return steps


async def build_plan(
    goal: str,
    shipment: dict[str, Any] | None,
    shipment_ref: str | None,
    tools: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    intent = _intent(goal, shipment)
    entities = _entities(goal, shipment)
    steps = deterministic_plan(intent, goal, entities, shipment_ref)
    plan: dict[str, Any] = {
        "intent": intent,
        "entities": entities,
        "steps": steps,
        "notes": ["Deterministic planner (rules baseline): no model call, zero token cost."],
        "planner": "rules-v1",
    }
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

    if llm_client.enabled:
        proposed = await llm_client.plan(goal, {"entities": entities, "shipment": shipment}, tools)
        if proposed and "error" not in proposed:
            allowed = {t["name"] for t in tools}
            llm_steps = _validate_llm_steps(proposed.get("steps"), allowed)
            if llm_steps:
                llm_steps.append(_reviewer_step())
                plan["steps"] = llm_steps
                plan["planner"] = proposed.get("planner", "llm")
                plan["intent"] = proposed.get("intent", intent)
                for key, value in (proposed.get("entities") or {}).items():
                    if value not in (None, "", 0):
                        entities[key] = value
                plan["entities"] = entities
                plan["notes"] = (proposed.get("notes") or [])[:4]
                usage = proposed.get("usage", usage)
        elif proposed and "error" in proposed:
            plan["notes"].append(f"Model plan unavailable ({proposed['error']}); used deterministic fallback.")

    for i, step in enumerate(plan["steps"], start=1):
        step["id"] = i
    return plan, usage
