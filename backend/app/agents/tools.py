"""Tool catalog used by the executor agent.

Every tool is an async function with a narrow contract. Results are JSON-safe
dicts annotated with `summary`, plus optional `blocking` / `requires_approval`
flags that the executor and reviewer understand.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from ..config import settings
from ..domain import rates, tracking
from ..guardrails import check_extraction, check_quote
from ..pipelines.extraction import extract
from ..rag import index
from ..samples import SAMPLES
from ..store import new_id

Handler = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._specs: dict[str, dict[str, Any]] = {}

    def register(self, name: str, description: str, handler: Handler, args: dict[str, str] | None = None) -> None:
        self._handlers[name] = handler
        self._specs[name] = {"name": name, "description": description, "args": args or {}}

    def specs(self) -> list[dict[str, Any]]:
        return list(self._specs.values())

    async def call(self, name: str, ctx: Any, **kwargs: Any) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown tool {name}"}
        return await handler(ctx, **kwargs)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _shipment_by_ref(ctx: Any, ref: str) -> dict[str, Any] | None:
    rows = await ctx.store.find("shipments", where={"ref": ref})
    return rows[0] if rows else None


def _lane_payload(ctx: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    entities = ctx.entities or {}
    payload = {
        "origin": kwargs.get("origin") or entities.get("origin") or "Chicago, IL",
        "destination": kwargs.get("destination") or entities.get("destination") or "Dallas, TX",
        "mode": kwargs.get("mode") or entities.get("mode") or "LTL",
        "weight_lb": kwargs.get("weight_lb") or entities.get("weight_lb") or 1200,
        "equipment": kwargs.get("equipment") or entities.get("equipment") or "Dry Van 53'",
        "commodity": kwargs.get("commodity") or entities.get("commodity") or "General freight",
        "customer": kwargs.get("customer") or entities.get("customer") or "Acme Distribution",
    }
    return payload


async def get_shipment(ctx: Any, ref: str | None = None, **_: Any) -> dict[str, Any]:
    ref = ref or ctx.shipment_ref
    if not ref:
        return {"ok": False, "error": "shipment reference required"}
    shipment = await _shipment_by_ref(ctx, ref)
    if not shipment:
        return {"ok": False, "error": f"shipment {ref} not found"}
    ctx.artifacts["shipment"] = shipment
    return {
        "ok": True,
        "shipment": shipment,
        "summary": f"{shipment['ref']} {shipment['origin']} to {shipment['destination']} is {shipment['status']}",
    }


async def rate_lane(ctx: Any, **kwargs: Any) -> dict[str, Any]:
    payload = _lane_payload(ctx, kwargs)
    result = rates.rate_lane(payload)
    ctx.artifacts["rate"] = result
    options = result["options"]
    best = next((o for o in options if o["recommended"]), options[0] if options else None)
    detail = (
        f"{len(options)} carrier options for {result['lane']['miles']} mi; benchmark ${result['benchmark_buy']:,.2f}"
        if options
        else "No tenderable carrier options"
    )
    return {"ok": bool(options), "rate": result, "options": options, "best": best, "summary": detail}


async def search_policy(ctx: Any, query: str = "margin floor and accessorial charges", k: int = 3, **_: Any) -> dict[str, Any]:
    hits = index.search(query, k=k)
    ctx.artifacts["policy_hits"] = hits
    top = hits[0]["title"] if hits else "no match"
    return {"ok": bool(hits), "hits": hits, "summary": f"Retrieved {len(hits)} policy chunks; top: {top}"}


async def draft_quote(ctx: Any, **kwargs: Any) -> dict[str, Any]:
    payload = _lane_payload(ctx, kwargs)
    rate = rates.rate_lane(payload)
    carrier_code = kwargs.get("carrier_code") or (ctx.entities or {}).get("carrier_code")
    option = rates.pick_option(rate, carrier_code) if carrier_code else None
    if option is None:
        option = next((o for o in rate["options"] if o["recommended"]), rate["options"][0] if rate["options"] else None)
    if option is None:
        return {"ok": False, "error": "no carrier can serve this lane/mode"}
    margin = kwargs.get("margin_pct")
    quote = rates.build_quote(payload, rate, option, margin)
    await ctx.store.insert("quotes", quote)
    ctx.artifacts["quote"] = quote
    return {
        "ok": True,
        "quote": quote,
        "options": rate["options"],
        "benchmark": rate["benchmark_buy"],
        "summary": f"{quote['quote_id']} {quote['carrier']} buy ${quote['buy']:,.2f} sell ${quote['sell']:,.2f} ({quote['margin_pct']}% margin)",
    }


async def check_guardrails(ctx: Any, **_: Any) -> dict[str, Any]:
    quote = ctx.artifacts.get("quote")
    if not quote:
        return {"ok": False, "error": "no quote in context"}
    result = check_quote(
        buy=quote["buy"],
        sell=quote["sell"],
        carrier_reliability=quote.get("carrier_reliability", 0.9),
    )
    quote["guardrail"] = result
    await ctx.store.update("quotes", quote["id"], {"guardrail": result})
    ctx.artifacts["guardrail"] = result
    if result["requires_approval"]:
        ctx.requires_approval = True
    status = "blocked" if not result["passed"] else "needs approval" if result["requires_approval"] else "passed"
    return {
        **result,
        "ok": result["passed"],
        "blocking": not result["passed"],
        "stop_run": not result["passed"],
        "summary": f"Guardrails {status} at {result['margin_pct']}% margin" + (f" ({len(result['findings'])} findings)" if result["findings"] else ""),
    }


async def _unique_ref(ctx: Any) -> str:
    for _ in range(6):
        ref = f"FO-{uuid.uuid4().int % 9000 + 1000}"
        if not await ctx.store.find("shipments", where={"ref": ref}):
            return ref
    return f"FO-{uuid.uuid4().hex[:6].upper()}"


async def book_shipment(ctx: Any, quote_id: str | None = None, **_: Any) -> dict[str, Any]:
    quote = ctx.artifacts.get("quote")
    if quote_id and not quote:
        quote = await ctx.store.get("quotes", quote_id)
    if not quote:
        return {"ok": False, "error": "no quote ready to book"}

    guard = quote.get("guardrail") or check_quote(
        buy=quote["buy"], sell=quote["sell"], carrier_reliability=quote.get("carrier_reliability", 0.9)
    )
    if not guard["passed"]:
        return {
            "ok": False,
            "blocking": True,
            "findings": guard["findings"],
            "summary": "Booking blocked by pricing guardrail",
        }

    now = _now()
    ref = await _unique_ref(ctx)
    held = bool(guard.get("requires_approval"))
    shipment = {
        "id": new_id("shp"),
        "ref": ref,
        "quote_id": quote["quote_id"],
        "customer": quote.get("customer", "Acme Distribution"),
        "origin": quote["origin"],
        "destination": quote["destination"],
        "mode": quote["mode"],
        "equipment": quote.get("equipment", "Dry Van 53'"),
        "weight_lb": quote["weight_lb"],
        "pieces": max(1, round(quote["weight_lb"] / 400)),
        "commodity": quote.get("commodity", "General freight"),
        "carrier": quote["carrier"],
        "carrier_code": quote["carrier_code"],
        "scac": quote["scac"],
        "buy": quote["buy"],
        "sell": quote["sell"],
        "margin_pct": quote["margin_pct"],
        "status": "held_for_approval" if held else "booked",
        "booking_status": "held_for_approval" if held else "confirmed",
        "booked_at": _iso(now),
        "eta": _iso(now + timedelta(days=quote.get("transit_days", 2))),
        "delivered_at": None,
        "events": [
            {
                "at": _iso(now),
                "code": "tender_sent",
                "label": f"Load tendered to {quote['carrier']}",
                "location": quote["origin"],
                "source": "agent",
            }
        ],
        "documents": [],
        "exception_ids": [],
        "sla": "Standard",
        "created_at": _iso(now),
    }
    shipment["risk"] = tracking.assess(shipment)
    await ctx.store.insert("shipments", shipment)
    await ctx.store.update("quotes", quote["id"], {"status": "pending_approval" if held else "booked", "shipment_ref": ref})
    ctx.artifacts["shipment"] = shipment
    if held:
        ctx.requires_approval = True
    return {
        "ok": True,
        "shipment": shipment,
        "requires_approval": held,
        "pause_run": held,
        "summary": f"{'Held' if held else 'Booked'} {ref} with {shipment['carrier']} at ${shipment['sell']:,.2f}"
        + (" - human approval required" if held else ""),
    }


async def sync_tracking(ctx: Any, shipment_ref: str | None = None, **_: Any) -> dict[str, Any]:
    ref = shipment_ref or ctx.shipment_ref or (ctx.artifacts.get("shipment") or {}).get("ref")
    if not ref:
        return {"ok": False, "error": "shipment reference required"}
    shipment = await _shipment_by_ref(ctx, ref)
    if not shipment:
        return {"ok": False, "error": f"shipment {ref} not found"}

    patch = tracking.apply_scan(shipment, shipment.get("destination"))
    risk = patch["risk"]
    created = None
    open_types = {e["type"] for e in await ctx.store.find("exceptions", where={"shipment_ref": ref}) if e["status"] == "open"}
    kind = shipment.get("disruption", "missed_scan")
    if risk["level"] in ("high", "critical") and kind not in open_types:
        exc = tracking.make_exception(ref, kind, risk["reasons"][0], severity=risk["level"] if risk["level"] != "medium" else "medium")
        await ctx.store.insert("exceptions", exc)
        shipment.setdefault("exception_ids", []).append(exc["id"])
        created = exc
    await ctx.store.update(
        "shipments",
        shipment["id"],
        {"events": patch["events"], "risk": risk, "last_sync": patch["last_sync"], "exception_ids": shipment.get("exception_ids", [])},
    )
    ctx.artifacts["risk"] = risk
    ctx.artifacts["shipment"] = shipment
    return {
        "ok": True,
        "risk": risk,
        "exception": created,
        "summary": f"Tracking synced; risk {risk['level'].upper()} ({', '.join(risk['reasons'])})"
        + (f"; opened {created['ref']}" if created else ""),
    }


async def extract_document(
    ctx: Any,
    text: str | None = None,
    kind: str = "auto",
    shipment_ref: str | None = None,
    sample: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    source = "inline_text"
    filename = "pasted-document.txt"
    if not text:
        chosen = next((s for s in SAMPLES if s["id"] == sample), None)
        if chosen is None and kind != "auto":
            chosen = next((s for s in SAMPLES if s["kind"] == kind), None)
        chosen = chosen or SAMPLES[1]
        text, kind, filename, source = chosen["text"], chosen["kind"], f"{chosen['id']}.pdf", "sample"

    result = extract(text, kind, filename)
    doc = {
        "id": new_id("doc"),
        "shipment_ref": shipment_ref or ctx.shipment_ref,
        "kind": result["kind"],
        "filename": filename,
        "status": "needs_review" if result["requires_review"] else "validated",
        "confidence": result["confidence"],
        "fields": result["fields"],
        "line_items": result["line_items"],
        "validations": result["validations"],
        "requires_review": result["requires_review"],
        "pii_redactions": result["pii_redactions"],
        "injection_signals": result["injection_signals"],
        "source": source,
        "created_at": _iso(_now()),
    }
    await ctx.store.insert("documents", doc)
    if doc["shipment_ref"]:
        shipment = await _shipment_by_ref(ctx, doc["shipment_ref"])
        if shipment:
            ids = list(shipment.get("documents", [])) + [doc["id"]]
            await ctx.store.update("shipments", shipment["id"], {"documents": ids})

    guard = check_extraction(result)
    ctx.artifacts["document"] = doc
    ctx.artifacts["document_guardrail"] = guard
    if guard.get("requires_review"):
        ctx.requires_approval = True
    return {
        "ok": True,
        "document_id": doc["id"],
        "document": doc,
        "confidence": doc["confidence"],
        "fields": doc["fields"],
        "validations": doc["validations"],
        "guardrail": guard,
        "summary": f"Extracted {len(doc['fields'])} fields from {doc['kind']} at {doc['confidence']:.0%} confidence"
        + (" - human review required" if guard["requires_review"] else ""),
    }


async def post_invoice(ctx: Any, document_id: str | None = None, **_: Any) -> dict[str, Any]:
    doc = ctx.artifacts.get("document")
    if document_id and (not doc or doc["id"] != document_id):
        doc = await ctx.store.get("documents", document_id)
    if not doc or doc["kind"] != "invoice":
        return {"ok": False, "error": "an invoice document is required"}

    failures = [v for v in doc.get("validations", []) if not v.get("passed", True)]
    if not doc.get("fields", {}).get("po_number", {}).get("value"):
        failures.append({"code": "MISSING_PO", "message": "No PO number found; ERP posting blocked.", "severity": "high"})
    if doc.get("injection_signals"):
        failures.append({"code": "PROMPT_INJECTION", "message": "Instruction-override text detected in document.", "severity": "critical"})

    if failures:
        updated = await ctx.store.update("documents", doc["id"], {"status": "blocked"})
        ctx.artifacts["document"] = updated or doc
        exc = None
        if doc.get("shipment_ref"):
            existing = [e for e in await ctx.store.find("exceptions", where={"shipment_ref": doc["shipment_ref"]}) if e["type"] == "document_mismatch" and e["status"] == "open"]
            if not existing:
                exc = tracking.make_exception(
                    doc["shipment_ref"],
                    "document_mismatch",
                    "; ".join(f["message"] for f in failures[:2]),
                    severity="high",
                )
                await ctx.store.insert("exceptions", exc)
        return {
            "ok": False,
            "blocking": True,
            "failures": failures,
            "exception": exc,
            "summary": f"Posting blocked: {failures[0]['message']}",
        }

    updated = await ctx.store.update("documents", doc["id"], {"status": "posted", "posted_at": _iso(_now())})
    ctx.artifacts["document"] = updated or doc
    return {"ok": True, "summary": f"{doc['filename']} posted to ERP after three-way match"}


async def list_exceptions(ctx: Any, shipment_ref: str | None = None, status: str | None = "open", **_: Any) -> dict[str, Any]:
    ref = shipment_ref or ctx.shipment_ref or (ctx.artifacts.get("shipment") or {}).get("ref")
    rows = await ctx.store.find("exceptions", where={"shipment_ref": ref} if ref else None)
    if status:
        rows = [r for r in rows if r["status"] == status]
    worst = tracking.worst_severity(rows)
    ctx.artifacts["exceptions"] = rows
    return {
        "ok": True,
        "exceptions": rows,
        "worst_severity": worst,
        "summary": f"{len(rows)} {status or 'all'} exception(s)" + (f"; worst {worst}" if rows else ""),
    }


async def resolve_exception(ctx: Any, ref: str | None = None, action: str = "auto_resolve", note: str | None = None, **_: Any) -> dict[str, Any]:
    rows = await ctx.store.find("exceptions")
    target = None
    if ref:
        target = next((e for e in rows if e["ref"] == ref or e["id"] == ref), None)
    else:
        target = next(
            (e for e in rows if e["status"] == "open" and e.get("auto_resolvable") and e["severity"] in ("low", "medium")),
            None,
        )
    if not target:
        return {"ok": True, "exception": None, "summary": "No auto-resolvable exceptions in the queue"}
    if target["severity"] in ("high", "critical") and action != "human_approve":
        return {
            "ok": False,
            "blocked": True,
            "error": f"{target['ref']} is {target['severity']} severity and needs a human operator",
            "summary": f"Refused to auto-close {target['ref']} ({target['severity']})",
        }
    updated = await ctx.store.update(
        "exceptions",
        target["id"],
        {
            "status": "resolved",
            "resolved_at": _iso(_now()),
            "resolution": note or "Closed by agent playbook",
            "owner": "exceptions-agent",
        },
    )
    ctx.artifacts.setdefault("resolved", []).append(updated)
    return {"ok": True, "exception": updated, "summary": f"Resolved {target['ref']} ({target['type']})"}


def build_registry(store: Any) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("get_shipment", "Load a shipment by reference (FO-xxxx).", get_shipment, {"ref": "string"})
    registry.register("rate_lane", "Price a lane across the carrier panel with benchmark scoring.", rate_lane)
    registry.register("search_policy", "Vector search over tariffs, SOPs and approval policy.", search_policy, {"query": "string"})
    registry.register("draft_quote", "Create a customer quote from the best tenderable carrier option.", draft_quote)
    registry.register("check_guardrails", "Check margin floor, carrier reliability and auto-book cap.", check_guardrails)
    registry.register("book_shipment", "Tender the load and create the shipment record.", book_shipment)
    registry.register("sync_tracking", "Pull the latest scan, recompute risk and open exceptions.", sync_tracking)
    registry.register("extract_document", "Extract fields from a BOL, invoice or packing list.", extract_document)
    registry.register("post_invoice", "Three-way match and post an invoice to the ERP.", post_invoice)
    registry.register("list_exceptions", "List exceptions for a shipment.", list_exceptions)
    registry.register("resolve_exception", "Resolve an exception through its playbook (never high/critical).", resolve_exception)
    return registry
