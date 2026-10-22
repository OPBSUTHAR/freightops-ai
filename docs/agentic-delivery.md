# Agentic delivery workflow

This repository is built to be driven by a coding agent — and reviewed like production software. It deliberately does
not depend on a specific assistant or subscription: the workflow, contracts and eval gate are the durable part.

## The loop

1. **Specify the behavior, not the file.**
   Write the operating requirement as an assertion: "a booking over $5,000 must return `needs_approval` and hold the
   shipment." Add it to `backend/app/agents/evals.py` first.
2. **Constrain the tool surface.**
   Any new capability becomes a tool with an explicit input shape and a `summary`/flag contract. Agents cannot reach
   around tools into domain code.
3. **Implement in small vertical slices.**
   Domain service → tool → planner step → API → UI. Each slice keeps the suite green.
4. **Run the gate.**
   ```powershell
   cd backend
   ..\.venv\Scripts\python -m pytest -q
   curl.exe -X POST http://localhost:8000/api/evals/run
   ```
   A red eval blocks the change; a passing demo does not replace it.
5. **Review the diff adversarially.**
   The reviewer's checklist mirrors the code review: can a guardrail be bypassed? Is a failure surfaced or swallowed?
   Is the trace sufficient to reconstruct the decision? Is spend bounded?

## What makes agent output reviewable

- **Bounded authority.** The planner chooses among registered tools; it cannot invent a shipment or a rate.
- **Deterministic baseline.** With `LLM_MODE=rules`, behavior is reproducible, so diffs and evals mean something.
- **Structured traces.** Every action records agent, tool, status, latency and cost. Review is reading a ledger, not a
  transcript.
- **Explicit stop conditions.** `blocking`, `pause_run`, `stop_run` and `needs_approval` are data, not prose.
- **Isolated evals.** Cases construct their own store, so the suite is order-independent and safe in CI.

## Prompt change checklist

- [ ] Bump or note the prompt version in `agents/prompts.py`.
- [ ] Validate the model's plan against the tool registry; keep the deterministic fallback.
- [ ] Re-run the 9-case suite and `pytest`.
- [ ] Check token/spend telemetry on a representative run.
- [ ] Confirm the reviewer still sees the same artifacts (no prompt-only policy).

## Using a different coding assistant

The repo is plain Python/React with no assistant-specific files. Any agentic coding tool can:

- read `README.md` and `docs/architecture.md` for the contract,
- run the test and eval commands above,
- use the tool registry and eval suite as the definition of done.

The build itself demonstrates the operating model requested in the role: orchestrate agents, review their output,
harden the system, and keep a human accountable for the decisions that matter.
