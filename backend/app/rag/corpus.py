"""Knowledge base: tariffs, SOPs and operating policy used by RAG."""
from __future__ import annotations

DOCS: list[dict] = [
    {
        "id": "tariff-101",
        "title": "Tariff 101 - LTL and FTL base rates",
        "tags": ["pricing", "tariff", "fuel"],
        "text": (
            "Base linehaul for LTL is distance multiplied by 1.55 USD per mile, adjusted by the "
            "shipment weight factor. FTL dry van base is 2.35 USD per mile with a 350 USD minimum. "
            "Parcel is 0.90 USD per mile equivalent and intermodal is 1.15 USD per mile. "
            "A fuel surcharge of 18 percent applies to all linehaul charges and is recalculated weekly. "
            "Minimum charge for any LTL shipment is 185 USD. Quotes expire after 7 days. "
            "Spot rates may deviate 8 percent from tariff without director approval."
        ),
    },
    {
        "id": "accessorials",
        "title": "Accessorial charge schedule",
        "tags": ["pricing", "accessorials"],
        "text": (
            "Liftgate service is 185 USD per stop. Residential delivery is 145 USD. "
            "Inside delivery is 210 USD. Appointment or timed delivery is 55 USD. "
            "Detention is 95 USD per hour after 2 free hours at pickup or delivery. "
            "Hazmat handling is 325 USD per shipment and requires a signed DG declaration. "
            "Redelivery after a failed appointment is 175 USD. Storage is 45 USD per pallet per day "
            "after 48 hours. Driver assist loading or unloading is 120 USD."
        ),
    },
    {
        "id": "detention-sop",
        "title": "Detention and demurrage SOP",
        "tags": ["operations", "detention", "exceptions"],
        "text": (
            "Detention accrues after 2 free hours at a shipper or consignee. Charge 95 USD per hour, "
            "billed in 15 minute increments, capped at 8 hours per stop. Drivers must check in through "
            "the mobile app to start the clock; without a check-in the claim is not billable. "
            "Any detention over 4 hours must open a service exception and notify the account manager. "
            "Demurrage at rail ramps is 150 USD per container per day after 3 free days."
        ),
    },
    {
        "id": "carrier-scorecard",
        "title": "Carrier scorecard and tender rules",
        "tags": ["carriers", "procurement"],
        "text": (
            "Tender only to carriers with a reliability score of 0.85 or higher. Preferred carriers "
            "receive first tender and have 30 minutes to accept before the load cascades. "
            "On-time pickup below 92 percent or on-time delivery below 90 percent triggers a "
            "performance review. Any carrier with an active safety alert is blocked from tender. "
            "Double brokering is grounds for immediate removal from the network."
        ),
    },
    {
        "id": "hazmat-sop",
        "title": "Dangerous goods and hazmat handling",
        "tags": ["compliance", "hazmat"],
        "text": (
            "Hazmat shipments require a signed dangerous goods declaration, UN number, proper "
            "shipping name, hazard class and packing group. Drivers must hold a hazmat endorsement. "
            "Placards are required for quantities above 1,001 pounds aggregate gross weight. "
            "Hazmat cannot be tendered to carriers without a current DG certification on file. "
            "Never consolidate hazmat with food-grade freight."
        ),
    },
    {
        "id": "customs-sop",
        "title": "Cross-border customs documentation",
        "tags": ["compliance", "customs", "documents"],
        "text": (
            "Cross-border loads require a commercial invoice, packing list, bill of lading and a "
            "customs broker authorization. The commercial invoice must state country of origin, "
            "HS code, declared value and Incoterms. Missing or mismatched values hold the shipment "
            "at the border and must be escalated as a high severity exception within 30 minutes."
        ),
    },
    {
        "id": "claims-osd",
        "title": "Claims, OS&D and cargo loss",
        "tags": ["claims", "exceptions"],
        "text": (
            "Over, short and damaged freight must be noted on the delivery receipt at the time of "
            "delivery. Photograph the seal, pallet and damaged cartons. File a claim within 9 months "
            "under NMFC rules; target first notice of loss within 24 hours. Concealed damage claims "
            "require a signed delivery receipt without exception notation and a inspection report."
        ),
    },
    {
        "id": "doc-standards",
        "title": "Document extraction standards - BOL, invoice, packing list",
        "tags": ["documents", "ocr", "extraction"],
        "text": (
            "Every bill of lading must yield BOL number, shipper, consignee, SCAC, piece count, "
            "weight, pickup date and delivery date. Invoices require invoice number, invoice date, "
            "due date, PO number, subtotal, tax and total; line item amounts must sum to the total "
            "within two cents. Packing lists require carton count, pallet count, total weight and "
            "dimensions. Extraction confidence below 0.85 requires human review before posting to "
            "the ERP. Never auto-post an invoice whose purchase order does not match an open PO."
        ),
    },
    {
        "id": "booking-policy",
        "title": "Quote and booking approval policy",
        "tags": ["policy", "approval", "margin"],
        "text": (
            "Target margin is 18 percent with a hard floor of 12 percent. Quotes below the floor "
            "require pricing manager approval. Bookings with a sell rate above 5,000 USD require "
            "human approval before tender. Bookings above 15,000 USD require director approval. "
            "All approvals are recorded with actor, timestamp and rationale for audit."
        ),
    },
    {
        "id": "tracking-sop",
        "title": "Tracking cadence and exception severity matrix",
        "tags": ["operations", "tracking", "exceptions"],
        "text": (
            "Track every active load at least every 2 hours. A missed scan window over 6 hours is a "
            "medium severity exception. ETA slip over 2 hours is medium; over 8 hours is high. "
            "Temperature excursion, hazmat incident, customs hold and cargo damage are always "
            "critical. Critical exceptions page the on-call coordinator immediately and require a "
            "customer update within 30 minutes. Auto-resolve only low severity scan delays with a "
            "documented playbook."
        ),
    },
    {
        "id": "edi-standards",
        "title": "EDI and integration standards",
        "tags": ["integration", "edi"],
        "text": (
            "Support EDI 204 load tender, 990 tender response, 214 shipment status, 210 invoice and "
            "997 functional acknowledgement. Duplicate 214 events must be de-duplicated on shipment "
            "reference plus event timestamp. Rejected 990s cascade to the next carrier within 30 "
            "minutes. Retry failed transmissions with exponential backoff up to five attempts."
        ),
    },
]
