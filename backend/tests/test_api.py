"""Smoke + behavior tests. Run: pytest -q"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        test_client.post("/api/admin/reseed")
        yield test_client


def test_health_and_meta(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["developer"] == "Omprakash Suthar"
    assert meta["developer_github"] == "OPBSUTHAR"
    assert "@OPBSUTHAR" in meta["credit"]
    assert len(meta["agents"]) >= 5


def test_rate_lane_returns_scored_options(client):
    response = client.post(
        "/api/quotes/rate",
        json={"origin": "Chicago, IL", "destination": "Dallas, TX", "mode": "LTL", "weight_lb": 2400},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["lane"]["miles"] > 500
    assert len(data["options"]) >= 3
    assert any(option["recommended"] for option in data["options"])


def test_document_extraction_flags_invoice_mismatch(client):
    sample = next(s for s in client.get("/api/documents/samples").json() if s["id"] == "invoice")
    response = client.post("/api/documents/extract", json={"text": sample["text"], "kind": "auto"})
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["kind"] == "invoice"
    codes = [v["code"] for v in body["document"]["validations"] if not v["passed"]]
    assert "INVOICE_TOTAL_MISMATCH" in codes
    assert body["guardrail"]["requires_review"] is True


def test_agent_run_quote_to_book(client):
    response = client.post("/api/agents/run", json={"goal": "Quote and book Chicago, IL to Dallas, TX for 1,200 lbs"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert run["review"]["verdict"] == "approve"
    assert run["artifacts"]["shipment"]["status"] == "booked"
    assert len(run["traces"]) >= 5


def test_auto_book_cap_requires_human(client):
    response = client.post("/api/agents/run", json={"goal": "Quote and book Los Angeles, CA to Denver, CO for 8,200 lbs"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "needs_approval"
    shipment = run["artifacts"]["shipment"]
    assert shipment["status"] == "held_for_approval"

    approved = client.post(f"/api/agents/runs/{run['id']}/approve", json={"approved": True, "note": "Reviewed with pricing"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    refreshed = client.get(f"/api/shipments/{shipment['ref']}").json()["shipment"]
    assert refreshed["status"] == "booked"


def test_exception_guard_blocks_critical_without_human(client):
    critical = next(e for e in client.get("/api/exceptions?status=open").json() if e["severity"] == "critical")
    blocked = client.post(f"/api/exceptions/{critical['id']}/resolve", json={"action": "auto_resolve"})
    assert blocked.status_code == 409
    allowed = client.post(f"/api/exceptions/{critical['id']}/resolve", json={"action": "human_approve", "note": "Broker confirmed"})
    assert allowed.status_code == 200
    assert allowed.json()["exception"]["status"] == "resolved"


def test_rag_retrieves_detention_policy(client):
    results = client.get("/api/rag/search", params={"q": "detention after two free hours"}).json()["results"]
    assert results
    assert results[0]["doc_id"] == "detention-sop"


def test_eval_suite_green(client):
    body = client.post("/api/evals/run").json()
    failing = [r["name"] for r in body["results"] if not r["passed"]]
    assert body["summary"]["failed"] == 0, failing
