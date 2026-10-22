"""REST API for the FreightOps AI control tower."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from .agents.evals import run_evals
from .agents.orchestrator import Orchestrator
from .agents.tools import build_registry
from .config import CAPABILITIES, MODEL_ROUTING, settings
from .domain import rates, tracking
from .guardrails import check_extraction, check_quote, policy_snapshot
from .models import ApprovalRequest, ExtractRequest, QuoteRequest, RateRequest, ResolveRequest, RunRequest
from .pipelines.extraction import extract, text_from_bytes
from .rag import index
from .samples import SAMPLES
from .seed import ensure_seed
from .store import build_store, new_id

router = APIRouter(prefix="/api")
store = build_store()
orchestrator = Orchestrator(store)

AGENT_ROSTER = [
    {"name": "planner-agent", "role": "Turns an operator goal into a minimal, auditable plan and selects tools.", "tools": ["search_policy"], "mode": "llm-or-rules"},
    {"name": "executor-agent", "role": "Runs each step, retries transient failures, emits a trace per action.", "tools": ["*"], "mode": "deterministic"},
    {"name": "reviewer-agent", "role": "Adversarial policy audit: margin, carrier, documents, exceptions, budget.", "tools": ["check_guardrails"], "mode": "policy-engine"},
    {"name": "quoting-agent", "role": "Prices lanes, benchmarks carriers, retrieves tariff policy and drafts quotes.", "tools": ["rate_lane", "search_policy", "draft_quote"], "mode": "rules+rag"},
    {"name": "booking-agent", "role": "Tenders the load and writes the shipment of record after guardrails pass.", "tools": ["book_shipment"], "mode": "deterministic"},
    {"name": "tracking-agent", "role": "Syncs scans, scores ETA risk and opens exceptions.", "tools": ["get_shipment", "sync_tracking"], "mode": "deterministic"},
    {"name": "documents-agent", "role": "Extracts BOL, invoice and packing list fields, then runs three-way match.", "tools": ["extract_document", "post_invoice"], "mode": "ocr+extraction"},
    {"name": "exceptions-agent", "role": "Triages exceptions, runs playbooks, refuses to auto-close high/critical.", "tools": ["list_exceptions", "resolve_exception"], "mode": "playbooks"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _link_document(doc_id: str, shipment_ref: str | None) -> None:
    if not shipment_ref:
        return
    rows = await store.find("shipments", where={"ref": shipment_ref})
    if rows:
        ids = list(rows[0].get("documents", [])) + [doc_id]
        await store.update("shipments", rows[0]["id"], {"documents": ids})


# ---------------------------------------------------------------- meta / health
@router.get("/health")
async def health() -> dict[str, Any]:
    try:
        backend = await store.ping()
    except Exception:
        backend = "unavailable"
    return {
        "status": "ok",
        "storage": backend,
        "llm_mode": settings.llm_mode,
        "version": settings.version,
        "developer": settings.developer,
        "time": _now(),
    }


@router.get("/meta")
async def meta() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "developer": settings.developer,
        "developer_github": settings.developer_github,
        "developer_role": settings.developer_role,
        "credit": f"Designed and built by {settings.developer} (@{settings.developer_github})",
        "github_url": f"https://github.com/{settings.developer_github}",
        "capabilities": CAPABILITIES,
        "stack": ["Python 3", "FastAPI", "MongoDB / in-memory repository", "React 18", "Vite", "RAG vector search", "OCR-ready extraction"],
        "llm_mode": settings.llm_mode,
        "model_routing": MODEL_ROUTING,
        "agents": AGENT_ROSTER,
        "policy": policy_snapshot(),
        "storage": await store.ping(),
    }


@router.get("/policy")
async def policy() -> dict[str, Any]:
    return {"policy": policy_snapshot(), "rag": index.stats()}


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
async def dashboard() -> dict[str, Any]:
    shipments = await store.find("shipments")
    exceptions = await store.find("exceptions")
    runs = await store.find("agent_runs", sort="started_at", limit=6)

    active_statuses = {"booked", "in_transit", "out_for_delivery", "exception", "held_for_approval"}
    open_exc = [e for e in exceptions if e["status"] == "open"]
    at_risk = [s for s in shipments if (s.get("risk") or {}).get("level") in ("high", "critical")]
    margins = [s.get("margin_pct", 0) for s in shipments if s.get("margin_pct")]
    auto = [s for s in shipments if s.get("booking_status") == "confirmed"]

    return {
        "kpis": {
            "active_loads": len([s for s in shipments if s["status"] in active_statuses]),
            "in_exception": len([s for s in shipments if s["status"] == "exception"]),
            "at_risk": len(at_risk),
            "open_exceptions": len(open_exc),
            "critical_exceptions": len([e for e in open_exc if e["severity"] == "critical"]),
            "avg_margin_pct": round(sum(margins) / len(margins), 1) if margins else 0,
            "auto_booked_pct": round(len(auto) / max(1, len(shipments)) * 100),
            "active_runs": len([r for r in runs if r["status"] == "running"]),
        },
        "shipments": shipments,
        "exceptions": open_exc,
        "runs": [{k: r.get(k) for k in ("id", "goal", "status", "intent", "shipment_ref", "started_at", "planner")} | {"verdict": (r.get("review") or {}).get("verdict"), "score": (r.get("review") or {}).get("score")} for r in runs],
        "policy": policy_snapshot(),
        "generated_at": _now(),
    }


# ---------------------------------------------------------------- shipments
@router.get("/shipments")
async def list_shipments(status: str | None = None, q: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    rows = await store.find("shipments", sort="created_at", limit=200)
    if status and status != "all":
        rows = [r for r in rows if r["status"] == status]
    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if any(needle in str(r.get(field, "")).lower() for field in ("ref", "customer", "origin", "destination", "carrier", "commodity"))
        ]
    return rows[:limit]


@router.get("/shipments/{ref}")
async def get_shipment(ref: str) -> dict[str, Any]:
    rows = await store.find("shipments", where={"ref": ref.upper()})
    if not rows:
        raise HTTPException(status_code=404, detail=f"Shipment {ref} not found")
    shipment = rows[0]
    exceptions = await store.find("exceptions", where={"shipment_ref": shipment["ref"]})
    documents = await store.find("documents", where={"shipment_ref": shipment["ref"]})
    runs = [r for r in await store.find("agent_runs", sort="started_at", limit=50) if r.get("shipment_ref") == shipment["ref"]]
    return {
        "shipment": shipment,
        "exceptions": exceptions,
        "documents": documents,
        "runs": [{k: r.get(k) for k in ("id", "goal", "status", "started_at")} | {"verdict": (r.get("review") or {}).get("verdict")} for r in runs],
    }


# ---------------------------------------------------------------- quotes
@router.get("/quotes")
async def list_quotes() -> list[dict[str, Any]]:
    return await store.find("quotes", sort="created_at", limit=50)


@router.post("/quotes/rate")
async def price_lane(body: RateRequest) -> dict[str, Any]:
    return rates.rate_lane(body.model_dump())


@router.post("/quotes")
async def create_quote(body: QuoteRequest) -> dict[str, Any]:
    payload = body.model_dump()
    rate = rates.rate_lane(payload)
    option = rates.pick_option(rate, body.carrier_code)
    if not option:
        raise HTTPException(status_code=422, detail=f"Carrier {body.carrier_code} cannot serve this lane/mode")
    quote = rates.build_quote(payload, rate, option, body.margin_pct)
    guard = check_quote(buy=quote["buy"], sell=quote["sell"], carrier_reliability=quote["carrier_reliability"])
    quote["guardrail"] = guard
    await store.insert("quotes", quote)
    return {"quote": quote, "guardrail": guard, "options": rate["options"], "benchmark": rate["benchmark_buy"]}


# ---------------------------------------------------------------- documents
@router.get("/documents")
async def list_documents(shipment_ref: str | None = None) -> list[dict[str, Any]]:
    rows = await store.find("documents", sort="created_at", limit=100)
    return [r for r in rows if not shipment_ref or r.get("shipment_ref") == shipment_ref.upper()]


@router.get("/documents/samples")
async def document_samples() -> list[dict[str, str]]:
    return SAMPLES


@router.post("/documents/extract")
async def extract_document(body: ExtractRequest) -> dict[str, Any]:
    result = extract(body.text, body.kind, body.filename)
    doc = {
        "id": new_id("doc"),
        "shipment_ref": body.shipment_ref,
        "kind": result["kind"],
        "filename": body.filename or "pasted-document.txt",
        "status": "needs_review" if result["requires_review"] else "validated",
        "confidence": result["confidence"],
        "fields": result["fields"],
        "line_items": result["line_items"],
        "validations": result["validations"],
        "requires_review": result["requires_review"],
        "pii_redactions": result["pii_redactions"],
        "injection_signals": result["injection_signals"],
        "source": "inline_text",
        "created_at": _now(),
    }
    await store.insert("documents", doc)
    await _link_document(doc["id"], body.shipment_ref)
    return {"document": doc, "guardrail": check_extraction(result), "extraction": result}


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), shipment_ref: str | None = Form(default=None)) -> dict[str, Any]:
    data = await file.read()
    try:
        text, source = text_from_bytes(file.filename or "upload.txt", data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = extract(text, "auto", file.filename)
    doc = {
        "id": new_id("doc"),
        "shipment_ref": (shipment_ref or "").upper() or None,
        "kind": result["kind"],
        "filename": file.filename or "upload.txt",
        "status": "needs_review" if result["requires_review"] else "validated",
        "confidence": result["confidence"],
        "fields": result["fields"],
        "line_items": result["line_items"],
        "validations": result["validations"],
        "requires_review": result["requires_review"],
        "pii_redactions": result["pii_redactions"],
        "injection_signals": result["injection_signals"],
        "source": source,
        "created_at": _now(),
    }
    await store.insert("documents", doc)
    await _link_document(doc["id"], doc["shipment_ref"])
    return {"document": doc, "guardrail": check_extraction(result)}


# ---------------------------------------------------------------- exceptions
@router.get("/exceptions")
async def list_exceptions(status: str | None = None, shipment_ref: str | None = None) -> list[dict[str, Any]]:
    rows = await store.find("exceptions", sort="detected_at", limit=100)
    if status and status != "all":
        rows = [r for r in rows if r["status"] == status]
    if shipment_ref:
        rows = [r for r in rows if r["shipment_ref"] == shipment_ref.upper()]
    return rows


@router.post("/exceptions/{exc_id}/resolve")
async def resolve_exception(exc_id: str, body: ResolveRequest) -> dict[str, Any]:
    row = await store.get("exceptions", exc_id)
    if not row:
        rows = [e for e in await store.find("exceptions") if e["ref"] == exc_id]
        row = rows[0] if rows else None
    if not row:
        raise HTTPException(status_code=404, detail="Exception not found")
    if row["severity"] in ("high", "critical") and body.action != "human_approve":
        raise HTTPException(status_code=409, detail=f"{row['ref']} is {row['severity']} severity; requires human_approve")
    updated = await store.update(
        "exceptions",
        row["id"],
        {
            "status": "resolved",
            "resolved_at": _now(),
            "resolution": body.note or f"Resolved via {body.action}",
            "owner": "operator",
        },
    )
    return {"exception": updated}


# ---------------------------------------------------------------- agents
@router.get("/agents/tools")
async def agent_tools() -> dict[str, Any]:
    registry = build_registry(store)
    return {"tools": registry.specs(), "agents": AGENT_ROSTER}


@router.post("/agents/run")
async def run_agents(body: RunRequest) -> dict[str, Any]:
    try:
        return await orchestrator.run(body.goal, body.shipment_ref)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent run failed: {type(exc).__name__}: {exc}") from exc


@router.get("/agents/runs")
async def list_runs(limit: int = Query(default=20, le=100)) -> list[dict[str, Any]]:
    runs = await store.find("agent_runs", sort="started_at", limit=limit)
    return [
        {
            "id": r["id"],
            "goal": r["goal"],
            "intent": r.get("intent"),
            "status": r["status"],
            "planner": r.get("planner"),
            "shipment_ref": r.get("shipment_ref"),
            "verdict": (r.get("review") or {}).get("verdict"),
            "score": (r.get("review") or {}).get("score"),
            "cost_usd": r.get("cost_usd", 0),
            "tokens": r.get("tokens", 0),
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
            "step_count": len(r.get("steps", [])),
        }
        for r in runs
    ]


@router.get("/agents/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = await store.get("agent_runs", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/agents/runs/{run_id}/approve")
async def approve_run(run_id: str, body: ApprovalRequest) -> dict[str, Any]:
    result = await orchestrator.decide(run_id, body.approved, body.note)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------- rag / evals
@router.get("/rag/search")
async def rag_search(q: str, k: int = Query(default=4, le=10), tag: str | None = None) -> dict[str, Any]:
    return {"query": q, "results": index.search(q, k=k, tag=tag), "stats": index.stats()}


@router.get("/rag/stats")
async def rag_stats() -> dict[str, Any]:
    from .rag.corpus import DOCS

    return {
        "stats": index.stats(),
        "documents": [{"id": d["id"], "title": d["title"], "tags": d["tags"], "chars": len(d["text"])} for d in DOCS],
    }


@router.post("/evals/run")
async def evals() -> dict[str, Any]:
    return await run_evals()


# ---------------------------------------------------------------- boot
@router.post("/admin/reseed")
async def reseed() -> dict[str, Any]:
    for collection in ("shipments", "quotes", "documents", "exceptions", "agent_runs"):
        await store.clear(collection)
    await ensure_seed(store)
    return {"ok": True, "shipments": await store.count("shipments"), "at": _now()}
