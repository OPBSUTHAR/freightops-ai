"""Seed data so the control tower is useful on first launch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .domain.rates import build_quote, pick_option, rate_lane
from .domain.tracking import assess, build_events, make_exception
from .pipelines.extraction import extract
from .samples import SAMPLES
from .store import Store

NOW = datetime.now(timezone.utc)


def _shipment(
    ref: str,
    customer: str,
    origin: str,
    destination: str,
    *,
    mode: str,
    weight: int,
    pieces: int,
    commodity: str,
    carrier: str,
    carrier_code: str,
    scac: str,
    buy: float,
    sell: float,
    status: str,
    booked_hours_ago: float,
    eta_hours: float | None,
    disruption: str | None = None,
    equipment: str = "Dry Van 53'",
    exception_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    booked_at = NOW - timedelta(hours=booked_hours_ago)
    doc: dict[str, Any] = {
        "id": f"shp_{ref.lower().replace('-', '')}",
        "ref": ref,
        "customer": customer,
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "equipment": equipment,
        "weight_lb": weight,
        "pieces": pieces,
        "commodity": commodity,
        "carrier": carrier,
        "carrier_code": carrier_code,
        "scac": scac,
        "buy": buy,
        "sell": sell,
        "margin_pct": round((sell - buy) / sell * 100, 2),
        "status": status,
        "booking_status": "held_for_approval" if status == "held_for_approval" else "confirmed",
        "booked_at": booked_at.isoformat(),
        "eta": (NOW + timedelta(hours=eta_hours)).isoformat() if eta_hours is not None else None,
        "delivered_at": (NOW - timedelta(hours=8)).isoformat() if status == "delivered" else None,
        "events": build_events(status, origin, destination, carrier, booked_at) if status not in ("held_for_approval", "quoted") else [],
        "documents": document_ids or [],
        "exception_ids": exception_ids or [],
        "disruption": disruption,
        "sla": "Standard",
        "created_at": booked_at.isoformat(),
    }
    doc["risk"] = assess(doc)
    return doc


def _build() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    exception_specs = [
        ("FO-4821", "eta_slip", "Carrier reported a 5 hour ETA slip at the Memphis breakbulk; delivery now 21:40.", "medium", 3.0),
        ("FO-4824", "missed_scan", "No scan event for 7 hours after departure from Miami. Driver unreachable via app ping.", "high", 1.5),
        ("FO-4825", "customs_hold", "CBP hold at Laredo entry; commercial invoice HS codes do not match packing list.", "critical", 0.75),
        ("FO-4827", "document_mismatch", "Invoice total is $200 above subtotal plus tax; ERP posting blocked.", "high", 26.0),
    ]
    exceptions: list[dict[str, Any]] = []
    for ref, kind, summary, severity, hours_ago in exception_specs:
        exc = make_exception(ref, kind, summary, severity=severity)
        exc["detected_at"] = (NOW - timedelta(hours=hours_ago)).isoformat()
        if ref == "FO-4827":
            exc["status"] = "monitoring"
            exc["owner"] = "documents-agent"
        exceptions.append(exc)

    def exc_ids(ref: str) -> list[str]:
        return [e["id"] for e in exceptions if e["shipment_ref"] == ref]

    # Documents parsed through the real extraction pipeline.
    docs: list[dict[str, Any]] = []
    doc_plan = [("bol", "FO-4821", "PCL-8842317.pdf", "validated"), ("invoice", "FO-4821", "INV-2026-0451.pdf", "needs_review"), ("packing_list", "FO-4827", "PL-77120.pdf", "validated")]
    for sample_id, shipment_ref, filename, status in doc_plan:
        sample = next(s for s in SAMPLES if s["id"] == sample_id)
        result = extract(sample["text"], sample["kind"], filename)
        docs.append(
            {
                "id": f"doc_{sample_id}_{shipment_ref.lower().replace('-', '')}",
                "shipment_ref": shipment_ref,
                "kind": result["kind"],
                "filename": filename,
                "status": status,
                "confidence": result["confidence"],
                "fields": result["fields"],
                "line_items": result["line_items"],
                "validations": result["validations"],
                "requires_review": result["requires_review"],
                "pii_redactions": result["pii_redactions"],
                "injection_signals": result["injection_signals"],
                "source": "pdf-text-layer",
                "created_at": (NOW - timedelta(hours=4)).isoformat(),
            }
        )

    def doc_ids(ref: str) -> list[str]:
        return [d["id"] for d in docs if d["shipment_ref"] == ref and d["status"] == "validated"]

    shipments = [
        _shipment("FO-4821", "Northline Foods", "Chicago, IL", "Dallas, TX", mode="LTL", weight=2400, pieces=6, commodity="Packaged foods", carrier="PaceLane Network", carrier_code="PCL", scac="PCLN", buy=3160.24, sell=3807.52, status="in_transit", booked_hours_ago=34, eta_hours=8, disruption="eta_slip", exception_ids=exc_ids("FO-4821"), document_ids=doc_ids("FO-4821")),
        _shipment("FO-4822", "Vertex Medical", "Newark, NJ", "Columbus, OH", mode="FTL", weight=12000, pieces=14, commodity="Medical devices", carrier="BlueRoad Logistics", carrier_code="BRD", scac="BRDL", buy=1687.40, sell=2033.01, status="out_for_delivery", booked_hours_ago=30, eta_hours=3, equipment="53' Air Ride"),
        _shipment("FO-4823", "Cascade Retail", "Seattle, WA", "Phoenix, AZ", mode="Intermodal", weight=34000, pieces=26, commodity="Retail fixtures", carrier="Southgate Intermodal", carrier_code="SGL", scac="SGIL", buy=4230.80, sell=5036.67, status="booked", booked_hours_ago=6, eta_hours=76, equipment="53' Container"),
        _shipment("FO-4824", "Gulf Coast Produce", "Miami, FL", "Atlanta, GA", mode="LTL", weight=3100, pieces=9, commodity="Refrigerated produce", carrier="Horizon Parcel", carrier_code="HRZ", scac="HRZP", buy=2688.10, sell=3238.67, status="exception", booked_hours_ago=22, eta_hours=14, disruption="missed_scan", equipment="Reefer 53'", exception_ids=exc_ids("FO-4824")),
        _shipment("FO-4825", "Ironwood Industrial", "Laredo, TX", "Detroit, MI", mode="FTL", weight=41000, pieces=22, commodity="Auto parts (cross-border)", carrier="Northwind Freight", carrier_code="NWF", scac="NWFD", buy=7420.00, sell=8920.00, status="exception", booked_hours_ago=52, eta_hours=30, disruption="customs_hold", exception_ids=exc_ids("FO-4825")),
        _shipment("FO-4826", "Aster Home", "Los Angeles, CA", "Denver, CO", mode="LTL", weight=8200, pieces=18, commodity="Furniture", carrier="PaceLane Network", carrier_code="PCL", scac="PCLN", buy=7240.15, sell=8711.02, status="held_for_approval", booked_hours_ago=1.5, eta_hours=None),
        _shipment("FO-4827", "Prairie Ag", "Kansas City, MO", "Memphis, TN", mode="LTL", weight=1500, pieces=4, commodity="Dry goods", carrier="PaceLane Network", carrier_code="PCL", scac="PCLN", buy=1204.30, sell=1450.96, status="delivered", booked_hours_ago=60, eta_hours=-8, exception_ids=exc_ids("FO-4827"), document_ids=doc_ids("FO-4827")),
        _shipment("FO-4828", "Beacon Electronics", "Charlotte, NC", "Miami, FL", mode="LTL", weight=900, pieces=3, commodity="Consumer electronics", carrier="Horizon Parcel", carrier_code="HRZ", scac="HRZP", buy=1980.42, sell=2386.05, status="booked", booked_hours_ago=2, eta_hours=40),
    ]

    quotes: list[dict[str, Any]] = []
    for req, carrier, margin, status in [
        ({"origin": "Chicago, IL", "destination": "Dallas, TX", "mode": "LTL", "weight_lb": 2400, "commodity": "Packaged foods", "customer": "Northline Foods"}, "PCL", 17.0, "won"),
        ({"origin": "Los Angeles, CA", "destination": "Denver, CO", "mode": "LTL", "weight_lb": 8200, "commodity": "Furniture", "customer": "Aster Home"}, "PCL", 16.9, "pending_approval"),
        ({"origin": "Atlanta, GA", "destination": "Miami, FL", "mode": "FTL", "weight_lb": 26000, "commodity": "Beverages", "customer": "Peachtree Beverage"}, "BRD", 18.0, "sent"),
    ]:
        rate = rate_lane(req)
        option = pick_option(rate, carrier) or rate["options"][0]
        quote = build_quote(req, rate, option, margin)
        quote["status"] = status
        quotes.append(quote)

    return shipments, quotes, docs, exceptions


def seed_all(store: Store) -> list[Any]:
    shipments, quotes, docs, exceptions = _build()
    return [shipments, quotes, docs, exceptions]


async def ensure_seed(store: Store) -> None:
    shipments, quotes, docs, exceptions = _build()
    for collection, rows in (
        ("shipments", shipments),
        ("quotes", quotes),
        ("documents", docs),
        ("exceptions", exceptions),
    ):
        if await store.count(collection) == 0:
            for row in rows:
                await store.insert(collection, row)
