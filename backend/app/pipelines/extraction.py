"""Document ingestion + field extraction.

Text documents are parsed directly. PDFs use pypdf when installed. Scanned
images route through an OCR adapter; when no OCR engine is configured the
pipeline returns a clear `ocr_unavailable` signal instead of hallucinating.
"""
from __future__ import annotations

import io
import re
from typing import Any

from ..guardrails import MANDATORY_FIELDS, redact_pii, scan_injection
from ..config import settings

MONEY = r"\$?\s*([0-9][0-9,]*\.?[0-9]{0,2})"
KIND_SIGNALS = {
    "invoice": ["invoice", "amount due", "subtotal", "bill to", "remit to", "terms"],
    "bol": ["bill of lading", "bol", "scac", "consignee", "shipper", "freight bill"],
    "packing_list": ["packing list", "carton", "pallet", "dimensions", "gross weight"],
}


def _num(raw: str) -> float:
    return float(re.sub(r"[^0-9.]", "", raw) or 0)


def _field(value: Any, confidence: float, evidence: str = "") -> dict[str, Any]:
    return {"value": value, "confidence": round(confidence, 2), "evidence": evidence.strip()}


def _labeled(text: str, labels: list[str], *, max_len: int = 42) -> tuple[str, str] | None:
    alternation = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"(?<![A-Za-z])(?:{alternation})\s*(?:#|no\.?|number|id)?\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 .,'&/\-]{{1,{max_len}}})", re.I)
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip().strip(".,;")
    value = re.split(r"\s{2,}|\n", value)[0].strip()
    return value, match.group(0).strip()


def _money_field(text: str, labels: list[str]) -> dict[str, Any] | None:
    alternation = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"(?<![A-Za-z])(?:{alternation})\s*[:\-]\s*{MONEY}", re.I)
    match = pattern.search(text)
    if not match:
        return None
    return _field(round(_num(match.group(1)), 2), 0.96, match.group(0).strip())


def _date_field(text: str, labels: list[str]) -> dict[str, Any] | None:
    alternation = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf"(?<![A-Za-z])(?:{alternation})\s*[:\-]\s*(\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}[/\-]\d{{1,2}}[/\-]\d{{2,4}}|[A-Z][a-z]{{2,8}} \d{{1,2}},? \d{{4}})",
        re.I,
    )
    match = pattern.search(text)
    if not match:
        return None
    return _field(match.group(1).strip(), 0.93, match.group(0).strip())


def classify(text: str) -> str:
    lowered = text.lower()
    scores = {kind: sum(lowered.count(sig) for sig in sigs) for kind, sigs in KIND_SIGNALS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "bol"


def _parse_line_items(text: str) -> list[dict[str, Any]]:
    items = []
    pattern = re.compile(
        r"^\s*(?P<desc>[A-Za-z][A-Za-z0-9 .,'/&-]{2,60}?)\s+"
        r"(?P<qty>\d+(?:\.\d+)?)\s+"
        r"\$?(?P<unit>[\d,]+\.\d{2})\s+"
        r"\$?(?P<amount>[\d,]+\.\d{2})\s*$"
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            items.append(
                {
                    "description": match.group("desc").strip(),
                    "qty": _num(match.group("qty")),
                    "unit_price": _num(match.group("unit")),
                    "amount": _num(match.group("amount")),
                }
            )
    return items


def _bol_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    found = _labeled(text, ["BOL No", "BOL Number", "Bill of Lading No", "BOL", "Pro Number", "PRO"])
    if found:
        fields["bol_number"] = _field(found[0], 0.95, found[1])
    for key, labels in {
        "shipper": ["Shipper", "From"],
        "consignee": ["Consignee", "Ship To", "To"],
        "carrier": ["Carrier"],
    }.items():
        found = _labeled(text, labels)
        if found:
            fields[key] = _field(found[0], 0.88, found[1])
    scac = re.search(r"\bSCAC\s*[:\-]?\s*([A-Z]{2,4})\b", text)
    if scac:
        fields["scac"] = _field(scac.group(1), 0.97, scac.group(0))
    pieces = re.search(r"\b(\d{1,5})\s*(?:pcs|pieces|cartons|pallets|plt|skids)\b", text, re.I)
    if pieces:
        fields["pieces"] = _field(int(pieces.group(1)), 0.9, pieces.group(0))
    weight = re.search(r"\b([\d,]+(?:\.\d+)?)\s*(lbs?|pounds|kg)\b", text, re.I)
    if weight:
        value = _num(weight.group(1))
        if weight.group(2).lower() == "kg":
            value = round(value * 2.20462, 2)
        fields["weight_lb"] = _field(value, 0.91, weight.group(0))
    for key, labels in {
        "pickup_date": ["Pickup Date", "Pickup"],
        "delivery_date": ["Delivery Date", "Deliver By", "Due"],
    }.items():
        found = _date_field(text, labels)
        if found:
            fields[key] = found
    po = re.search(r"\bP\.?O\.?\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,})", text, re.I)
    if po:
        fields["po_number"] = _field(po.group(1), 0.9, po.group(0))
    return fields


def _invoice_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    found = _labeled(text, ["Invoice No", "Invoice Number", "Invoice #", "Invoice"])
    if found:
        fields["invoice_number"] = _field(found[0], 0.95, found[1])
    for key, labels in {
        "invoice_date": ["Invoice Date", "Date"],
        "due_date": ["Due Date", "Payment Due", "Net"],
    }.items():
        found = _date_field(text, labels)
        if found:
            fields[key] = found
    for key, labels in {
        "subtotal": ["Subtotal", "Sub Total", "Linehaul"],
        "tax": ["Tax", "Sales Tax"],
        "total": ["Total Due", "Amount Due", "Invoice Total", "Total"],
    }.items():
        found = _money_field(text, labels)
        if found:
            fields[key] = found
    po = re.search(r"\bP\.?O\.?\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9\-]{4,})", text, re.I)
    if po:
        fields["po_number"] = _field(po.group(1), 0.91, po.group(0))
    terms = re.search(r"\bNet\s*(\d{1,3})\b", text, re.I)
    if terms:
        fields["payment_terms"] = _field(f"Net {terms.group(1)}", 0.9, terms.group(0))
    return fields


def _packing_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    found = _labeled(text, ["Packing List No", "Packing List", "PL No", "PL"])
    if found:
        fields["packing_list_number"] = _field(found[0], 0.94, found[1])
    cartons = re.search(r"\b(\d{1,5})\s*(?:cartons|ctns|boxes)\b", text, re.I)
    if cartons:
        fields["carton_count"] = _field(int(cartons.group(1)), 0.92, cartons.group(0))
    pallets = re.search(r"\b(\d{1,4})\s*(?:pallets|plt|skids)\b", text, re.I)
    if pallets:
        fields["pallet_count"] = _field(int(pallets.group(1)), 0.9, pallets.group(0))
    weight = re.search(r"\b(?:gross weight|total weight)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(lbs?|kg)\b", text, re.I)
    if weight:
        value = _num(weight.group(1))
        if weight.group(2).lower() == "kg":
            value = round(value * 2.20462, 2)
        fields["total_weight_lb"] = _field(value, 0.92, weight.group(0))
    dims = re.search(r"\b(\d{1,3})\s*[xX]\s*(\d{1,3})\s*[xX]\s*(\d{1,3})\s*(in|cm)\b", text)
    if dims:
        fields["dimensions"] = _field(f"{dims.group(1)}x{dims.group(2)}x{dims.group(3)} {dims.group(4)}", 0.88, dims.group(0))
    return fields


def extract(text: str, kind: str = "auto", filename: str | None = None) -> dict[str, Any]:
    redacted, pii_hits = redact_pii(text)
    resolved = classify(text) if kind == "auto" else kind
    fields = {"bol": _bol_fields, "invoice": _invoice_fields, "packing_list": _packing_fields}[resolved](redacted)
    line_items = _parse_line_items(redacted) if resolved == "invoice" else []
    validations: list[dict[str, Any]] = []

    if resolved == "invoice" and line_items:
        summed = round(sum(item["amount"] for item in line_items), 2)
        stated = fields.get("total", {}).get("value")
        if stated is not None:
            delta = round(abs(summed - stated), 2)
            validations.append(
                {
                    "code": "INVOICE_TOTAL_MISMATCH",
                    "passed": delta <= 0.02,
                    "severity": "high" if delta > 0.02 else "info",
                    "message": f"Line items sum to ${summed:,.2f}; invoice states ${stated:,.2f} (delta ${delta:,.2f}).",
                }
            )
    if resolved == "invoice":
        subtotal = fields.get("subtotal", {}).get("value")
        tax = fields.get("tax", {}).get("value") or 0.0
        total = fields.get("total", {}).get("value")
        if subtotal is not None and total is not None:
            expected = round(subtotal + tax, 2)
            validations.append(
                {
                    "code": "INVOICE_MATH",
                    "passed": abs(expected - total) <= 0.02,
                    "severity": "medium",
                    "message": f"Subtotal + tax = ${expected:,.2f}; stated total ${total:,.2f}.",
                }
            )

    missing = [f for f in MANDATORY_FIELDS.get(resolved, []) if f not in fields]
    if missing:
        validations.append(
            {
                "code": "MISSING_FIELDS",
                "passed": False,
                "severity": "high",
                "message": f"Could not locate: {', '.join(missing)}.",
            }
        )

    confidences = [f["confidence"] for f in fields.values()]
    confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    if len(fields) < 3:
        confidence = min(confidence, 0.55)
    injection = scan_injection(text)

    return {
        "kind": resolved,
        "filename": filename,
        "confidence": confidence,
        "fields": fields,
        "line_items": line_items,
        "validations": validations,
        "injection_signals": injection,
        "pii_redactions": pii_hits,
        "requires_review": confidence < settings.doc_confidence_floor or bool(missing) or bool(injection) or any(not v.get("passed", True) for v in validations),
        "raw_chars": len(text),
    }


def text_from_bytes(filename: str, data: bytes) -> tuple[str, str]:
    """Return (text, source). Raises ValueError when OCR is required."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise ValueError("PDF support requires pypdf. Install backend requirements.") from exc
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise ValueError("PDF has no text layer (scanned). Configure an OCR engine for image PDFs.")
        return text, "pdf-text-layer"
    if lower.endswith((".png", ".jpg", ".jpeg", ".tiff")):
        raise ValueError("Image OCR engine not configured. Set OCR_ENGINE=tesseract and install pytesseract.")
    try:
        return data.decode("utf-8"), "plain-text"
    except UnicodeDecodeError as exc:
        raise ValueError("Unsupported binary document. Upload PDF, TXT, CSV or JSON.") from exc
