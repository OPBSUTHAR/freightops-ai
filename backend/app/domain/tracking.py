"""Tracking, ETA risk scoring and exception playbooks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..store import new_id

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "eta_slip": {
        "label": "ETA slip",
        "severity": "medium",
        "auto_resolvable": True,
        "steps": [
            "Confirm latest GPS or scan event with the carrier",
            "Recalculate ETA and notify the customer if slip exceeds 2 hours",
            "Offer recovery options (team driver, partial transload)",
            "Log customer acknowledgement in the shipment timeline",
        ],
    },
    "missed_scan": {
        "label": "Missed scan window",
        "severity": "medium",
        "auto_resolvable": True,
        "steps": [
            "Ping carrier API and driver mobile app for a location",
            "Request a manual checkpoint from dispatch",
            "Escalate to high if no scan within 6 hours",
        ],
    },
    "customs_hold": {
        "label": "Customs hold",
        "severity": "critical",
        "auto_resolvable": False,
        "steps": [
            "Pull broker entry number and hold reason",
            "Validate commercial invoice, packing list and HS codes",
            "Notify importer of record and account manager",
            "Update customer within 30 minutes",
        ],
    },
    "damage": {
        "label": "Cargo damage / OS&D",
        "severity": "critical",
        "auto_resolvable": False,
        "steps": [
            "Request photos of seal, pallet and damaged cartons",
            "Note exception on the delivery receipt",
            "Open claim and notify cargo claims desk",
            "Hold invoice posting until inspection report",
        ],
    },
    "detention": {
        "label": "Detention exposure",
        "severity": "low",
        "auto_resolvable": False,
        "steps": [
            "Verify driver check-in timestamp",
            "Bill 95 USD per hour after 2 free hours, 15 minute increments",
            "Cap at 8 hours per stop",
        ],
    },
    "document_mismatch": {
        "label": "Document mismatch",
        "severity": "high",
        "auto_resolvable": False,
        "steps": [
            "Run three-way match across BOL, invoice and packing list",
            "Request corrected document from shipper",
            "Block ERP posting until values reconcile",
        ],
    },
}

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def build_events(status: str, origin: str, destination: str, carrier: str, booked_at: datetime) -> list[dict[str, Any]]:
    """Deterministic scan history for seeded shipments."""
    plan = [
        (0.0, "tender_accepted", f"Tender accepted by {carrier}", origin),
        (2.0, "picked_up", "Loaded and departed shipper", origin),
        (6.0, "in_transit", "Linehaul scan", "Joliet, IL" if origin.lower().startswith("chicago") else origin),
        (26.0, "in_transit", "Arrived breakbulk", "Memphis, TN"),
        (40.0, "out_for_delivery", "Out for delivery", destination),
        (46.0, "delivered", "Delivered, POD captured", destination),
    ]
    cutoff = {"booked": 1, "in_transit": 4, "out_for_delivery": 5, "delivered": 6, "exception": 4}.get(status, 1)
    events = []
    for hours, code, label, location in plan[:cutoff]:
        events.append(
            {
                "at": _iso(booked_at + timedelta(hours=hours)),
                "code": code,
                "label": label,
                "location": location,
                "source": "carrier_api",
            }
        )
    return events


def assess(shipment: dict[str, Any]) -> dict[str, Any]:
    status = shipment.get("status", "booked")
    if status == "delivered":
        return {"level": "none", "score": 0, "reasons": ["Delivered"]}
    reasons: list[str] = []
    score = 0
    if shipment.get("disruption") == "eta_slip":
        score += 55
        reasons.append("Carrier reported a 5 hour ETA slip at the Memphis breakbulk")
    if status == "exception":
        score += 30
        reasons.append("Shipment is in exception status")
    if shipment.get("disruption") == "missed_scan":
        score += 35
        reasons.append("No scan event in the last 7 hours")
    if shipment.get("disruption") == "customs_hold":
        score += 80
        reasons.append("Customs hold on cross-border entry")
    if not reasons:
        reasons.append("Tracking on plan")
    level = "critical" if score >= 75 else "high" if score >= 55 else "medium" if score >= 25 else "low"
    return {"level": level, "score": min(score, 100), "reasons": reasons, "assessed_at": _iso(_now())}


def apply_scan(shipment: dict[str, Any], location: str | None = None) -> dict[str, Any]:
    """Append a fresh in-transit scan and recompute risk."""
    now = _now()
    events = list(shipment.get("events", []))
    events.append(
        {
            "at": _iso(now),
            "code": "in_transit",
            "label": "Automated tracking sync",
            "location": location or shipment.get("destination", "In transit"),
            "source": "agent_sync",
        }
    )
    risk = assess(shipment)
    return {"events": events, "risk": risk, "last_sync": _iso(now)}


def make_exception(
    shipment_ref: str,
    kind: str,
    summary: str,
    *,
    severity: str | None = None,
    auto_resolvable: bool | None = None,
) -> dict[str, Any]:
    playbook = PLAYBOOKS.get(kind, PLAYBOOKS["missed_scan"])
    return {
        "id": new_id("exc"),
        "ref": f"EX-{new_id('x').split('_')[1][:4].upper()}",
        "shipment_ref": shipment_ref,
        "type": kind,
        "label": playbook["label"],
        "severity": severity or playbook["severity"],
        "status": "open",
        "summary": summary,
        "playbook": playbook["steps"],
        "auto_resolvable": playbook["auto_resolvable"] if auto_resolvable is None else auto_resolvable,
        "detected_at": _iso(_now()),
        "resolved_at": None,
        "resolution": None,
        "owner": "unassigned",
    }


def worst_severity(exceptions: list[dict[str, Any]]) -> str:
    if not exceptions:
        return "none"
    return max((e.get("severity", "low") for e in exceptions), key=lambda s: SEVERITY_ORDER.get(s, 0))
