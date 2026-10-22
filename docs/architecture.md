# Architecture notes

## Request flow

```
POST /api/agents/run { goal, shipment_ref? }
  │
  ├─ orchestrator creates run_id, loads shipment if referenced
  ├─ planner  → plan { intent, entities, steps[], planner }
  ├─ run doc persisted (status=running) before any tool executes
  ├─ executor → for each step: resolve args → tool call → trace → step status
  │              retries transient errors once
  │              stops on stop_run, pauses on pause_run
  ├─ reviewer → weighted checks → verdict + findings + score
  └─ run doc updated (status, plan, steps, traces, artifacts, review, cost)
```

Run status maps from reviewer verdict:

| Verdict | Run status | Meaning |
| --- | --- | --- |
| `approve` | `completed` | Straight-through processing allowed. |
| `needs_approval` | `needs_approval` | A human gate is open (booking cap, doc review). |
| `escalate` | `escalated` | Blocking guardrail, failed tool, or critical exception. |
| human approves | `completed` | Shipment flips `held_for_approval` → `booked`. |
| human rejects | `rejected` | Shipment is cancelled. |

## Tool contract

Every tool is `async (ctx, **kwargs) -> dict`. Required conventions:

- `ok: bool` — did the action succeed.
- `summary: str` — one line shown in the trace and UI.
- `blocking: bool` — policy failure that must stop dependent steps.
- `requires_approval: bool` — a human gate exists.
- `pause_run: bool` — stop executing the remaining plan (held booking).
- `stop_run: bool` — stop because a guardrail rejected the action.

`ctx.artifacts` carries the working set: `quote`, `rate`, `shipment`, `document`, `risk`, `exceptions`,
`policy_hits`, `guardrail`. The executor trims large records before persisting step results.

## State and memory

- **Run memory** is the artifacts dict plus the persisted run document. It is not a chat transcript; agents operate on
  records.
- **Shipment memory** is the shipment document: events, documents, exception ids, risk, approval decision.
- **Knowledge** is the RAG index. Retrieval is cited in `ctx.artifacts.policy_hits` so a reviewer can see what the
  quoting agent read.
- **Provider memory** is intentionally absent. Every run starts from explicit records, which keeps behavior
  reproducible and evals meaningful.

## Data model (Mongo-shaped)

```
quotes       { id, quote_id, customer, lane fields, carrier, buy, sell, margin_pct, status, guardrail }
shipments    { id, ref, quote_id, lane, carrier, buy, sell, status, booking_status,
               events[], documents[], exception_ids[], risk, approval, eta }
documents    { id, shipment_ref, kind, filename, status, confidence, fields{}, line_items[],
               validations[], injection_signals[], pii_redactions }
exceptions   { id, ref, shipment_ref, type, severity, status, summary, playbook[], resolution }
agent_runs   { id, goal, intent, planner, plan, steps[], traces[], artifacts, review, status,
               tokens, cost_usd, started_at, finished_at }
```

Indexes to add in MongoDB: `shipments.ref` (unique), `quotes.quote_id` (unique), `agent_runs.started_at`,
`documents.shipment_ref`, `exceptions.shipment_ref`, `exceptions.status`.

## Failure handling

| Failure | Behavior |
| --- | --- |
| Tool raises | Caught by executor, retried once, then step marked `failed`; reviewer escalates. |
| LLM plan invalid / unreachable | Planner falls back to the deterministic plan and records a note. |
| Booking above cap | Shipment created `held_for_approval`; executor pauses; reviewer returns `needs_approval`. |
| Guardrail blocks quote | `stop_run`; dependent booking steps marked `skipped`; reviewer escalates. |
| Invoice mismatch | `post_invoice` returns blocking, document status `blocked`, exception opened. |
| Critical exception close | Tool refuses; API returns `409` unless `action=human_approve`. |
| Mongo unavailable | Application logs a warning and uses the in-memory repository. |

## Extending

- **New tool**: add an async handler in `agents/tools.py`, register it in `build_registry`, add an eval, then let the
  planner use it. The LLM planner validates against the registry automatically.
- **New domain agent**: it is a naming/ownership convention over tools (`documents-agent` owns extraction tools). Add it
  to `AGENT_ROSTER` in `api.py` and use the agent name in plans.
- **Real rate provider**: replace `domain/rates.rate_lane` internals with carrier API calls; keep the option shape so
  the quote and guardrail layers do not change.
- **Real OCR**: implement `text_from_bytes` for images with Tesseract/Textract/Document AI; extraction regexes and
  confidence scoring stay.
- **Different embedding model**: replace `rag.index.embed`; `search` and its result contract stay identical.
- **Persistence**: set `STORAGE=mongo` and install `pymongo`; the repository interface is already async.
