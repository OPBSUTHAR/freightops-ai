"""Evaluation suite.

Each case runs against an isolated store so evals never pollute the operator
console. This is the seed of a CI gate: fail the build when agent behavior drifts.
"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Awaitable, Callable

from ..domain.rates import rate_lane
from ..domain.tracking import make_exception
from ..guardrails import check_quote
from ..pipelines.extraction import extract
from ..rag import index
from ..samples import SAMPLES
from ..seed import ensure_seed
from ..store import Store
from .orchestrator import Orchestrator
from .runtime import RunContext
from .tools import build_registry

Case = tuple[str, str, str, Callable[[], Awaitable[tuple[bool, str]]]]


def _sample(sample_id: str) -> dict[str, str]:
    return next(s for s in SAMPLES if s["id"] == sample_id)


async def _fresh() -> Store:
    store = Store()
    await ensure_seed(store)
    return store


async def _quote_options() -> tuple[bool, str]:
    rate = rate_lane({"origin": "Chicago, IL", "destination": "Dallas, TX", "mode": "LTL", "weight_lb": 2400})
    ok = len(rate["options"]) >= 3 and rate["benchmark_buy"] > 0 and any(o["recommended"] for o in rate["options"])
    return ok, f"{len(rate['options'])} options, benchmark ${rate['benchmark_buy']:,.2f}"


async def _margin_guardrail() -> tuple[bool, str]:
    low = check_quote(buy=1000, sell=1087, carrier_reliability=0.95)
    healthy = check_quote(buy=1000, sell=1220, carrier_reliability=0.95)
    ok = (not low["passed"]) and healthy["passed"] and healthy["margin_pct"] >= 12
    return ok, f"8% margin blocked={not low['passed']}; 18% margin passes={healthy['passed']}"


async def _approval_cap() -> tuple[bool, str]:
    store = await _fresh()
    run = await Orchestrator(store).run("Quote and book Los Angeles, CA to Denver, CO for 8,200 lbs")
    shipment = (run.get("artifacts") or {}).get("shipment") or {}
    ok = run["status"] == "needs_approval" and shipment.get("status") == "held_for_approval"
    return ok, f"run={run['status']} shipment={shipment.get('status')} sell=${shipment.get('sell', 0):,.2f}"


async def _bol_extraction() -> tuple[bool, str]:
    result = extract(_sample("bol")["text"], "auto")
    number = result["fields"].get("bol_number", {}).get("value")
    ok = result["kind"] == "bol" and number == "PCL-8842317" and result["confidence"] >= 0.85 and not result["requires_review"]
    return ok, f"kind={result['kind']} bol={number} confidence={result['confidence']}"


async def _invoice_mismatch() -> tuple[bool, str]:
    result = extract(_sample("invoice")["text"], "auto")
    codes = {v["code"]: v for v in result["validations"]}
    mismatch = codes.get("INVOICE_TOTAL_MISMATCH")
    ok = result["kind"] == "invoice" and mismatch is not None and not mismatch["passed"] and result["requires_review"]
    return ok, f"total={result['fields'].get('total', {}).get('value')} validations={list(codes)}"


async def _injection_guard() -> tuple[bool, str]:
    result = extract(_sample("suspicious")["text"], "auto")
    ok = bool(result["injection_signals"]) and result["requires_review"]
    return ok, f"signals={len(result['injection_signals'])} review={result['requires_review']}"


async def _rag_detention() -> tuple[bool, str]:
    hits = index.search("how much detention after two free hours at a shipper", k=3)
    ok = bool(hits) and hits[0]["doc_id"] == "detention-sop" and "95" in hits[0]["text"]
    return ok, f"top={hits[0]['doc_id'] if hits else 'none'} score={hits[0]['score'] if hits else 0}"


async def _critical_exception_guard() -> tuple[bool, str]:
    store = Store()
    exc = make_exception("FO-9900", "customs_hold", "CBP hold", severity="critical")
    await store.insert("exceptions", exc)
    ctx = RunContext(run_id="eval", goal="resolve exception", store=store)
    result = await build_registry(store).call("resolve_exception", ctx, ref=exc["ref"])
    ok = result.get("ok") is False and result.get("blocked") is True
    return ok, f"blocked={result.get('blocked')} reason={(result.get('error') or '')[:60]}"


async def _end_to_end() -> tuple[bool, str]:
    store = await _fresh()
    run = await Orchestrator(store).run("Quote and book Chicago, IL to Dallas, TX for 1,200 lbs")
    shipment = (run.get("artifacts") or {}).get("shipment") or {}
    review = run.get("review") or {}
    ok = run["status"] == "completed" and shipment.get("status") == "booked" and review.get("verdict") == "approve"
    return ok, f"run={run['status']} shipment={shipment.get('status')} verdict={review.get('verdict')} score={review.get('score')}"


CASES: list[Case] = [
    ("pricing", "Carrier panel returns scored options", "Pricing", _quote_options),
    ("margin", "Margin floor blocks unprofitable quote", "Guardrails", _margin_guardrail),
    ("approval", "Auto-book cap forces human approval", "Human-in-the-loop", _approval_cap),
    ("bol", "BOL extraction hits mandatory fields", "Documents", _bol_extraction),
    ("invoice", "Invoice total mismatch is detected", "Documents", _invoice_mismatch),
    ("injection", "Prompt injection in document is quarantined", "Security", _injection_guard),
    ("rag", "RAG retrieves the detention SOP", "Retrieval", _rag_detention),
    ("exceptions", "Critical exception cannot be auto-closed", "Guardrails", _critical_exception_guard),
    ("e2e", "Quote to booked shipment, straight through", "Agent orchestration", _end_to_end),
]


async def run_evals() -> dict[str, Any]:
    started = perf_counter()
    results = []
    for case_id, name, focus, fn in CASES:
        t0 = perf_counter()
        try:
            passed, detail = await fn()
        except Exception as exc:  # an eval failure must not kill the suite
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "id": case_id,
                "name": name,
                "focus": focus,
                "passed": bool(passed),
                "detail": detail,
                "ms": int((perf_counter() - t0) * 1000),
            }
        )
    passed = sum(1 for r in results if r["passed"])
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "score": round(passed / len(results) * 100, 1),
            "duration_ms": int((perf_counter() - started) * 1000),
        },
        "results": results,
        "ran_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
