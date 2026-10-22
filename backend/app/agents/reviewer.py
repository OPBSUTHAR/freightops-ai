"""Reviewer agent: independent, adversarial audit of an executed plan."""
from __future__ import annotations

from typing import Any

from ..config import settings
from ..guardrails import MANDATORY_FIELDS
from ..domain.tracking import SEVERITY_ORDER
from .runtime import RunContext, utc_now


def _check(name: str, passed: bool, weight: int, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "weight": weight, "detail": detail}


async def review(ctx: RunContext) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    quote = ctx.artifacts.get("quote") or {}
    guard = ctx.artifacts.get("guardrail") or quote.get("guardrail") or {}
    shipment = ctx.artifacts.get("shipment") or {}
    document = ctx.artifacts.get("document") or {}
    doc_guard = ctx.artifacts.get("document_guardrail") or {}
    exceptions = ctx.artifacts.get("exceptions") or []

    # 1. Pricing guardrail
    if quote:
        margin_ok = quote.get("margin_pct", 0) >= settings.min_margin_pct
        checks.append(_check("margin_floor", margin_ok, 20, f"margin {quote.get('margin_pct')}% vs floor {settings.min_margin_pct}%"))
        if not margin_ok:
            findings.append({"code": "MARGIN_FLOOR", "severity": "high", "message": f"Margin {quote.get('margin_pct')}% is under the floor."})
        rel_ok = quote.get("carrier_reliability", 1) >= settings.carrier_reliability_floor
        checks.append(_check("carrier_reliability", rel_ok, 15, f"{quote.get('carrier')} reliability {quote.get('carrier_reliability')}"))
        if not rel_ok:
            findings.append({"code": "CARRIER_RELIABILITY", "severity": "high", "message": "Carrier is below the reliability floor."})
    else:
        checks.append(_check("pricing", True, 35, "no quote in this run"))

    # 2. Document integrity
    if document:
        missing = [f for f in MANDATORY_FIELDS.get(document.get("kind", "bol"), []) if not document.get("fields", {}).get(f, {}).get("value")]
        confidence_ok = document.get("confidence", 0) >= settings.doc_confidence_floor
        checks.append(_check("document_confidence", confidence_ok, 15, f"confidence {document.get('confidence', 0):.0%}"))
        checks.append(_check("document_completeness", not missing, 10, f"missing: {', '.join(missing) or 'none'}"))
        if not confidence_ok:
            findings.append({"code": "LOW_CONFIDENCE", "severity": "medium", "message": f"Extraction confidence {document.get('confidence', 0):.0%} below floor."})
        if missing:
            findings.append({"code": "MISSING_FIELDS", "severity": "high", "message": f"Missing {', '.join(missing)}."})
        if document.get("injection_signals"):
            findings.append({"code": "PROMPT_INJECTION", "severity": "critical", "message": "Instruction-override text detected in the document; content was not trusted."})
        for finding in doc_guard.get("findings", []):
            findings.append({"code": finding["code"], "severity": finding.get("severity", "medium"), "message": finding["message"]})
    else:
        checks.append(_check("documents", True, 25, "no documents in this run"))

    # 3. Exception risk
    open_exc = [e for e in exceptions if e.get("status") == "open"]
    worst = max((e.get("severity", "low") for e in open_exc), key=lambda s: SEVERITY_ORDER.get(s, 0), default="none")
    exc_ok = SEVERITY_ORDER.get(worst, 0) < SEVERITY_ORDER["high"]
    checks.append(_check("exception_risk", exc_ok, 15, f"worst open severity: {worst}"))
    if not exc_ok:
        findings.append({"code": "OPEN_EXCEPTION", "severity": worst, "message": f"{len(open_exc)} open exception(s); worst is {worst}."})

    # 4. Execution integrity
    failed = [s for s in ctx.steps if s["status"] in ("failed", "blocked")]
    skipped = [s for s in ctx.steps if s["status"] == "skipped"]
    exec_ok = not failed
    checks.append(_check("execution", exec_ok, 15, f"{len(ctx.steps) - len(failed)}/{len(ctx.steps)} steps succeeded" + (f", {len(skipped)} skipped" if skipped else "")))
    for step in failed:
        findings.append({"code": "STEP_BLOCKED" if step["status"] == "blocked" else "STEP_FAILED", "severity": "high", "message": f"{step['tool']}: {step.get('detail', '')}"})

    # 5. Budget
    budget_ok = ctx.cost_usd <= settings.run_budget_usd
    checks.append(_check("run_budget", budget_ok, 10, f"${ctx.cost_usd:.4f} of ${settings.run_budget_usd:.2f}"))
    if not budget_ok:
        findings.append({"code": "BUDGET_EXCEEDED", "severity": "high", "message": "Run exceeded the model spend cap."})

    score = round(sum(c["weight"] for c in checks if c["passed"]) / max(1, sum(c["weight"] for c in checks)) * 100)

    critical = any(f["severity"] == "critical" for f in findings)
    high = any(f["severity"] == "high" for f in findings)
    if critical or ctx.blocked or high:
        verdict = "escalate"
    elif ctx.requires_approval or any(s["status"] == "skipped" for s in ctx.steps):
        verdict = "needs_approval"
    else:
        verdict = "approve"

    if verdict == "approve":
        summary = f"All {len(checks)} policy checks passed at {score}/100. Run is cleared for straight-through processing."
    elif verdict == "needs_approval":
        summary = f"{score}/100 with a human gate: " + (findings[0]["message"] if findings else "approval required by policy.")
    else:
        summary = f"{score}/100 - escalation required: " + (findings[0]["message"] if findings else "blocking condition detected.")

    return {
        "verdict": verdict,
        "score": score,
        "checks": checks,
        "findings": findings,
        "summary": summary,
        "human_gate": bool(ctx.requires_approval),
        "reviewed_at": utc_now(),
        "reviewer": "reviewer-agent (policy engine)",
    }
