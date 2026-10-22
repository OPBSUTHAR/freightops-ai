"""Deterministic guardrails that wrap every agent decision."""
from __future__ import annotations

import re
from typing import Any

from .config import settings

PII_PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (the )?(system|previous) prompt",
    r"you are now",
    r"reveal (your )?(system prompt|api key|credentials)",
    r"approve (this|the) invoice without",
    r"do not (log|report|escalate)",
]

MANDATORY_FIELDS = {
    "bol": ["bol_number", "shipper", "consignee", "pieces", "weight_lb"],
    "invoice": ["invoice_number", "invoice_date", "subtotal", "total"],
    "packing_list": ["carton_count", "total_weight_lb"],
}


def redact_pii(text: str) -> tuple[str, int]:
    hits = 0
    for pattern in PII_PATTERNS.values():
        text, n = pattern.subn("[REDACTED]", text)
        hits += n
    return text, hits


def scan_injection(text: str) -> list[str]:
    lowered = text.lower()
    return [p for p in INJECTION_PATTERNS if re.search(p, lowered)]


def check_quote(*, buy: float, sell: float, carrier_reliability: float, auto_book: bool = True) -> dict[str, Any]:
    margin = round((sell - buy) / sell * 100, 2) if sell else 0.0
    findings: list[dict[str, str]] = []
    if margin < settings.min_margin_pct:
        findings.append({
            "code": "MARGIN_FLOOR",
            "severity": "blocking",
            "message": f"Margin {margin}% is below the {settings.min_margin_pct}% floor.",
        })
    if carrier_reliability < settings.carrier_reliability_floor:
        findings.append({
            "code": "CARRIER_SCORE",
            "severity": "blocking",
            "message": f"Carrier reliability {carrier_reliability} is below the {settings.carrier_reliability_floor} floor.",
        })
    if auto_book and sell > settings.max_auto_book_usd:
        findings.append({
            "code": "APPROVAL_REQUIRED",
            "severity": "approval",
            "message": f"Sell rate ${sell:,.2f} exceeds the ${settings.max_auto_book_usd:,.0f} auto-book cap.",
        })
    blocking = [f for f in findings if f["severity"] == "blocking"]
    approval = [f for f in findings if f["severity"] == "approval"]
    return {
        "passed": not blocking,
        "requires_approval": bool(approval),
        "margin_pct": margin,
        "findings": findings,
    }


def check_extraction(result: dict[str, Any]) -> dict[str, Any]:
    kind = result.get("kind", "bol")
    fields = result.get("fields", {})
    missing = [f for f in MANDATORY_FIELDS.get(kind, []) if not fields.get(f, {}).get("value")]
    low = [name for name, f in fields.items() if f.get("confidence", 0) < settings.doc_confidence_floor]
    findings: list[dict[str, str]] = []
    if missing:
        findings.append({"code": "MISSING_FIELDS", "severity": "high", "message": f"Missing mandatory fields: {', '.join(missing)}"})
    if low:
        findings.append({"code": "LOW_CONFIDENCE", "severity": "medium", "message": f"Review fields: {', '.join(low)}"})
    for finding in result.get("validations", []):
        if not finding.get("passed", True):
            findings.append({"code": finding["code"], "severity": finding.get("severity", "medium"), "message": finding["message"]})
    if result.get("injection_signals"):
        findings.append({"code": "PROMPT_INJECTION", "severity": "critical", "message": "Document text contains instruction-override patterns; content was not trusted."})
    requires_review = (
        bool(missing)
        or bool(result.get("injection_signals"))
        or result.get("confidence", 0) < settings.doc_confidence_floor
        or any(not v.get("passed", True) for v in result.get("validations", []))
    )
    return {"passed": not findings, "requires_review": requires_review, "findings": findings}


def budget_ok(cost_usd: float) -> bool:
    return cost_usd <= settings.run_budget_usd


def policy_snapshot() -> dict[str, Any]:
    return {
        "min_margin_pct": settings.min_margin_pct,
        "max_auto_book_usd": settings.max_auto_book_usd,
        "doc_confidence_floor": settings.doc_confidence_floor,
        "carrier_reliability_floor": settings.carrier_reliability_floor,
        "run_budget_usd": settings.run_budget_usd,
        "pii_redaction": "email, phone, credit card, SSN",
        "injection_patterns": len(INJECTION_PATTERNS),
    }
