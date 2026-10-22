import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import {
  Card,
  CardHead,
  Empty,
  ErrorNote,
  Icon,
  Meter,
  ScoreRing,
  Spinner,
  Status,
  duration,
  money,
  pct,
  pretty,
  severityTone,
  timeAgo,
} from '../ui.jsx';

const PRESETS = [
  {
    label: 'Full autopilot',
    goal: 'Run full autopilot: quote and book Los Angeles, CA to Denver, CO for 8,200 lbs',
    hint: 'hits the approval cap',
    icon: 'bolt',
  },
  {
    label: 'Quote lane',
    goal: 'Quote Chicago, IL to Dallas, TX for 2,400 lbs LTL',
    hint: 'pricing + RAG citation',
    icon: 'route',
  },
  {
    label: 'Track load',
    goal: 'Track FO-4824, assess ETA risk and list open exceptions',
    hint: 'risk + exception triage',
    icon: 'clock',
  },
  {
    label: 'Invoice intake',
    goal: 'Extract the invoice for FO-4821 and run three-way match',
    hint: 'OCR + validation',
    icon: 'doc',
  },
  {
    label: 'Exception sweep',
    goal: 'Review and resolve safe exceptions for FO-4824',
    hint: 'playbook guardrails',
    icon: 'shield',
  },
];

const TEAM = [
  { name: 'planner-agent', role: 'goal → plan' },
  { name: 'executor-agent', role: 'tool calls + retries' },
  { name: 'reviewer-agent', role: 'policy audit' },
  { name: 'domain agents', role: 'quote · book · track · docs' },
];

function agentTone(agent = '') {
  if (agent.includes('planner')) return 'planner';
  if (agent.includes('executor')) return 'executor';
  if (agent.includes('reviewer')) return 'reviewer';
  if (agent === 'human' || agent.includes('orchestrator')) return 'human';
  return 'domain';
}

function RunView({ run, onRefresh, onNavigate }) {
  const [openStep, setOpenStep] = useState(null);
  const [showTrace, setShowTrace] = useState(false);
  const [note, setNote] = useState('');
  const [deciding, setDeciding] = useState(false);
  const [decisionError, setDecisionError] = useState('');

  const review = run.review || {};
  const artifacts = run.artifacts || {};
  const shipment = artifacts.shipment;
  const quote = artifacts.quote;
  const document = artifacts.document;
  const risk = artifacts.risk || shipment?.risk;
  const options = artifacts.rate?.options || quote?.options || [];
  const steps = run.plan?.steps || [];
  const toolSteps = steps.filter((step) => !step.deferred);
  const executed = toolSteps.filter((step) => ['ok', 'blocked', 'failed'].includes(step.status)).length;
  const paused = toolSteps.some((step) => step.status === 'skipped');
  const failed = toolSteps.some((step) => ['blocked', 'failed'].includes(step.status));
  const heldForApproval = shipment?.status === 'held_for_approval';

  const decide = async (approved) => {
    if (!approved && !window.confirm('Reject this booking? The shipment will be cancelled.')) return;
    setDeciding(true);
    setDecisionError('');
    try {
      const updated = await api(`/api/agents/runs/${run.id}/approve`, {
        method: 'POST',
        body: { approved, note: note || (approved ? 'Approved by operator' : 'Rejected by operator') },
      });
      onRefresh(updated);
    } catch (error) {
      setDecisionError(error.message);
    } finally {
      setDeciding(false);
    }
  };

  return (
    <div className="run-view">
      <Card className="run-head-card">
        <div className="run-head">
          <div className="run-title">
            <div className="eyebrow">
              Run {run.id.replace('run_', '#')} · {run.intent}
            </div>
            <h2>{run.goal}</h2>
            <div className="run-sub">
              <Status value={run.status} />
              <span>{run.planner}</span>
              <span>{duration(run.started_at, run.finished_at)}</span>
              <span>{run.tokens || 0} tokens</span>
              <span>{money(run.cost_usd || 0, 4)} model spend</span>
              <span>{timeAgo(run.started_at)}</span>
            </div>
          </div>
          <ScoreRing score={review.score || 0} label="review" />
        </div>

        <div className="pipeline">
          <div className="pipeline-stage done">
            <span className="stage-num">
              <Icon name="check" size={14} />
            </span>
            <div>
              <strong>Planner</strong>
              <small>{steps.length} steps · {run.planner}</small>
            </div>
          </div>
          <span className="pipeline-link" />
          <div className={`pipeline-stage ${failed ? 'blocked' : paused ? 'paused' : executed === toolSteps.length ? 'done' : ''}`}>
            <span className="stage-num">{failed ? <Icon name="x" size={14} /> : paused ? 'Ⅱ' : <Icon name="check" size={14} />}</span>
            <div>
              <strong>Executor</strong>
              <small>
                {executed}/{toolSteps.length} tools · {paused ? 'paused' : failed ? 'blocked' : 'complete'}
              </small>
            </div>
          </div>
          <span className="pipeline-link" />
          <div className={`pipeline-stage ${review.verdict === 'approve' || review.verdict === 'approved_by_human' ? 'done' : review.verdict === 'escalate' || review.verdict === 'rejected_by_human' ? 'blocked' : 'paused'}`}>
            <span className="stage-num">
              <Icon name={review.verdict === 'escalate' ? 'alert' : 'shield'} size={14} />
            </span>
            <div>
              <strong>Reviewer</strong>
              <small>{pretty(review.verdict || 'pending')} · {review.score ?? '—'}/100</small>
            </div>
          </div>
        </div>
      </Card>

      <Card className={`verdict-card ${severityTone(review.verdict === 'escalate' ? 'critical' : review.verdict === 'approve' ? 'low' : 'medium')}`}>
        <div className="verdict-top">
          <div>
            <div className="eyebrow">Reviewer verdict</div>
            <h3>{review.summary || 'Review pending'}</h3>
            <p className="muted small">Independent policy engine · margin, carrier, documents, exceptions, budget.</p>
          </div>
          <Status value={review.verdict || 'pending'} />
        </div>

        {(review.findings || []).length > 0 && (
          <ul className="finding-list">
            {review.findings.map((finding, index) => (
              <li key={`${finding.code}-${index}`}>
                <span className={`sev ${severityTone(finding.severity)}`}>{finding.severity}</span>
                <div>
                  <strong>{finding.code.replaceAll('_', ' ')}</strong>
                  <p>{finding.message}</p>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="check-grid">
          {(review.checks || []).map((check) => (
            <div className={`check ${check.passed ? 'pass' : 'fail'}`} key={check.name}>
              <Icon name={check.passed ? 'check' : 'x'} size={14} />
              <div>
                <strong>{pretty(check.name)}</strong>
                <small>{check.detail}</small>
              </div>
              <span>{check.weight}pt</span>
            </div>
          ))}
        </div>

        {heldForApproval && (
          <div className="approval-box">
            <div className="approval-copy">
              <Icon name="shield" size={20} />
              <div>
                <strong>Human approval required</strong>
                <p>
                  {shipment.ref} is holding at {money(shipment.sell, 2)} — above the auto-book cap or flagged by the reviewer.
                  Approving tenders the load and closes the gate.
                </p>
              </div>
            </div>
            <div className="approval-actions">
              <input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Decision note (audit trail)"
                aria-label="Approval note"
              />
              <button type="button" className="btn primary" disabled={deciding} onClick={() => decide(true)}>
                <Icon name="check" size={15} />
                {deciding ? 'Recording…' : 'Approve & tender'}
              </button>
              <button type="button" className="btn danger" disabled={deciding} onClick={() => decide(false)}>
                Reject
              </button>
            </div>
            <ErrorNote error={decisionError} />
          </div>
        )}
      </Card>

      <Card className="plan-card">
        <CardHead
          eyebrow="Execution plan"
          title="Agent-by-agent trail"
          sub="Every tool call, latency and guardrail result is persisted."
          actions={
            <button type="button" className="btn bare sm" onClick={() => setShowTrace((value) => !value)}>
              <Icon name="layers" size={14} />
              {showTrace ? 'Hide trace log' : 'Trace log'}
            </button>
          }
        />

        <ol className="steps">
          {steps.map((step, index) => (
            <li className={`step ${step.status || 'pending'}`} key={`${step.id}-${step.tool}`}>
              <span className="step-index">{String(index + 1).padStart(2, '0')}</span>
              <div className="step-body">
                <div className="step-top">
                  <span className={`agent-badge ${agentTone(step.agent)}`}>{step.agent.replace('-agent', '')}</span>
                  <strong>{step.action}</strong>
                  <Status value={step.status || 'pending'} />
                </div>
                <div className="step-meta">
                  {step.tool && <code>{step.tool}</code>}
                  {step.latency_ms != null && <span>{step.latency_ms} ms</span>}
                  {step.deferred && <span>post-execution audit</span>}
                </div>
                <p className="step-why">{step.why}</p>
                {step.detail && <div className="step-detail">{step.detail}</div>}
                {step.result && (
                  <>
                    <button type="button" className="step-expand" onClick={() => setOpenStep(openStep === step.id ? null : step.id)}>
                      {openStep === step.id ? 'Hide result' : 'View tool result'}
                    </button>
                    {openStep === step.id && <pre className="code-block">{JSON.stringify(step.result, null, 2)}</pre>}
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>

        {showTrace && (
          <div className="trace-table">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Agent</th>
                  <th>Action</th>
                  <th>Tool</th>
                  <th>Status</th>
                  <th className="num">Latency</th>
                </tr>
              </thead>
              <tbody>
                {(run.traces || []).map((trace) => (
                  <tr key={trace.seq}>
                    <td className="muted">{trace.seq}</td>
                    <td>{trace.agent}</td>
                    <td>{trace.action}</td>
                    <td>{trace.tool ? <code>{trace.tool}</code> : '—'}</td>
                    <td>
                      <Status value={trace.status} dot={false} />
                    </td>
                    <td className="num">{trace.latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {(quote || shipment || document || risk || options.length > 0) && (
        <div className="artifact-grid">
          {quote && (
            <Card className="artifact">
              <CardHead eyebrow="Artifact" title="Customer quote" actions={<Status value={quote.status} />} />
              <div className="quote-hero">
                <div>
                  <span>Sell rate</span>
                  <strong>{money(quote.sell, 2)}</strong>
                </div>
                <div>
                  <span>Buy rate</span>
                  <strong>{money(quote.buy, 2)}</strong>
                </div>
                <div>
                  <span>Margin</span>
                  <strong className="tone-green">{pct(quote.margin_pct)}</strong>
                </div>
              </div>
              <Meter value={quote.margin_pct * 4} tone="green" />
              <div className="fact-grid">
                <div>
                  <span>Quote</span>
                  <strong>{quote.quote_id}</strong>
                </div>
                <div>
                  <span>Carrier</span>
                  <strong>{quote.carrier}</strong>
                </div>
                <div>
                  <span>Transit</span>
                  <strong>{quote.transit_days} days</strong>
                </div>
                <div>
                  <span>Mode</span>
                  <strong>{quote.mode}</strong>
                </div>
              </div>
            </Card>
          )}

          {shipment && (
            <Card className="artifact">
              <CardHead eyebrow="Artifact" title="Shipment of record" actions={<Status value={shipment.status} />} />
              <div className="shipment-hero">
                <div>
                  <div className="ref">{shipment.ref}</div>
                  <p className="muted small">{shipment.customer}</p>
                </div>
                <strong>{money(shipment.sell)}</strong>
              </div>
              <div className="lane">
                <span>{shipment.origin}</span>
                <Icon name="arrow" size={12} />
                <span>{shipment.destination}</span>
              </div>
              <div className="fact-grid">
                <div>
                  <span>Carrier</span>
                  <strong>{shipment.carrier}</strong>
                </div>
                <div>
                  <span>ETA</span>
                  <strong>{shipment.eta ? new Date(shipment.eta).toLocaleDateString() : '—'}</strong>
                </div>
                <div>
                  <span>Margin</span>
                  <strong>{pct(shipment.margin_pct)}</strong>
                </div>
                <div>
                  <span>Booking</span>
                  <strong>{pretty(shipment.booking_status || (shipment.status === 'held_for_approval' ? 'held' : 'confirmed'))}</strong>
                </div>
              </div>
              {shipment.status === 'booked' && (
                <button type="button" className="btn ghost sm" onClick={() => onNavigate('overview')}>
                  Open in load board <Icon name="arrow" size={14} />
                </button>
              )}
            </Card>
          )}

          {document && (
            <Card className="artifact">
              <CardHead eyebrow="Artifact" title="Extracted document" actions={<Status value={document.status} />} />
              <div className="doc-hero">
                <Icon name="doc" size={26} />
                <div>
                  <strong>{document.filename}</strong>
                  <p className="muted small">
                    {pretty(document.kind)} · {Math.round((document.confidence || 0) * 100)}% confidence · {Object.keys(document.fields || {}).length} fields
                  </p>
                </div>
              </div>
              {(document.validations || []).slice(0, 3).map((validation) => (
                <div className={`validation ${validation.passed ? 'pass' : 'fail'}`} key={validation.code}>
                  <Icon name={validation.passed ? 'check' : 'alert'} size={14} />
                  <span>{validation.message}</span>
                </div>
              ))}
            </Card>
          )}

          {risk && (
            <Card className="artifact">
              <CardHead eyebrow="Artifact" title="ETA risk" actions={<Status value={risk.level} />} />
              <ul className="bullet-list">
                {(risk.reasons || []).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </Card>
          )}

          {options.length > 0 && (
            <Card className="artifact artifact-wide">
              <CardHead eyebrow="Artifact" title="Carrier panel" sub={`Benchmark buy ${money(artifacts.rate?.benchmark_buy, 2)}`} />
              <div className="table-wrap">
                <table className="data-table compact-table">
                  <thead>
                    <tr>
                      <th>Carrier</th>
                      <th className="num">Buy</th>
                      <th className="num">Transit</th>
                      <th className="num">Reliability</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {options.map((option) => (
                      <tr key={option.carrier_code}>
                        <td>
                          <div>{option.carrier}</div>
                          <div className="muted small">{option.scac}</div>
                        </td>
                        <td className="num">{money(option.buy_rate, 2)}</td>
                        <td className="num">{option.transit_days}d</td>
                        <td className="num">{pct(option.reliability * 100, 0)}</td>
                        <td>{option.recommended ? <Status value="recommended" label="Recommended" /> : option.tenderable ? <span className="muted small">Tenderable</span> : <Status value="blocked" label="Below floor" />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentStudio({ pendingGoal, initialRun, initialRef, onNavigate }) {
  const [goal, setGoal] = useState('Quote and book Chicago, IL to Dallas, TX for 2,400 lbs');
  const [shipmentRef, setShipmentRef] = useState('');
  const [run, setRun] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [loadingRun, setLoadingRun] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await api('/api/agents/runs?limit=8'));
    } catch {
      /* history is non-blocking */
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (pendingGoal?.text) {
      setGoal(pendingGoal.text);
      setRun(null);
    }
  }, [pendingGoal]);

  useEffect(() => {
    if (initialRef?.ref) setShipmentRef(initialRef.ref);
  }, [initialRef]);

  useEffect(() => {
    if (!initialRun?.id) return;
    let cancelled = false;
    setLoadingRun(true);
    api(`/api/agents/runs/${initialRun.id}`)
      .then((data) => !cancelled && setRun(data))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoadingRun(false));
    return () => {
      cancelled = true;
    };
  }, [initialRun]);

  const execute = async (event) => {
    event?.preventDefault();
    if (!goal.trim()) {
      setError('Describe the outcome you want the agents to achieve.');
      return;
    }
    setRunning(true);
    setError('');
    try {
      const payload = { goal: goal.trim() };
      if (shipmentRef.trim()) payload.shipment_ref = shipmentRef.trim().toUpperCase();
      const result = await api('/api/agents/run', { method: 'POST', body: payload });
      setRun(result);
      window.history.replaceState(null, '', `#studio/${result.id}`);
      loadHistory();
      requestAnimationFrame(() => document.querySelector('.run-view')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  const refreshRun = (updated) => {
    setRun(updated);
    loadHistory();
  };

  const openHistoryRun = async (runId) => {
    setLoadingRun(true);
    setError('');
    try {
      setRun(await api(`/api/agents/runs/${runId}`));
      window.history.replaceState(null, '', `#studio/${runId}`);
      requestAnimationFrame(() => document.querySelector('.run-view')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingRun(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <span className="live-dot" /> Agent studio
          </div>
          <h1>Run the freight agent team</h1>
          <p>
            State a goal. The planner writes the plan, the executor calls tools, the reviewer audits policy. Nothing ships
            straight through if it breaks a guardrail.
          </p>
        </div>
      </div>

      <div className="studio-grid">
        <div className="studio-main">
          <Card className="composer" as="form" onSubmit={execute}>
            <CardHead
              eyebrow="Composer"
              title="What should the agents do?"
              sub="Goals are interpreted against the tool catalog — not free-form text generation."
            />
            <label className="field">
              <span>Operator goal</span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={3}
                placeholder="e.g. Quote and book Chicago, IL to Dallas, TX for 2,400 lbs"
              />
            </label>
            <div className="composer-row">
              <label className="field compact">
                <span>Shipment reference (optional)</span>
                <input
                  value={shipmentRef}
                  onChange={(event) => setShipmentRef(event.target.value)}
                  placeholder="FO-4821"
                />
              </label>
              <button type="submit" className="btn primary run-btn" disabled={running}>
                {running ? <span className="spinner small" /> : <Icon name="play" size={15} />}
                {running ? 'Agents working…' : 'Run agent team'}
              </button>
            </div>

            <div className="preset-row">
              {PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className={`preset ${goal === preset.goal ? 'active' : ''}`}
                  onClick={() => {
                    setGoal(preset.goal);
                    setError('');
                  }}
                >
                  <Icon name={preset.icon} size={14} />
                  <span>
                    <strong>{preset.label}</strong>
                    <small>{preset.hint}</small>
                  </span>
                </button>
              ))}
            </div>

            <div className="composer-note">
              <Icon name="cpu" size={15} />
              <span>
                Deterministic planner by default — no Claude or OpenAI key required. Set <code>LLM_MODE=openai</code> with any
                OpenAI-compatible endpoint to have the model propose the plan; tool validation and fallback stay in place.
              </span>
            </div>
            <ErrorNote error={error} />
          </Card>

          {loadingRun && <Spinner label="Loading run" />}
          {run && !loadingRun && <RunView run={run} onRefresh={refreshRun} onNavigate={onNavigate} />}
          {!run && !loadingRun && (
            <Card className="empty-card">
              <Empty
                title="No run loaded"
                hint="Pick a preset or describe a goal. Try full autopilot to watch the human approval gate fire."
                icon="bolt"
              />
            </Card>
          )}
        </div>

        <div className="studio-rail">
          <Card className="rail-card">
            <CardHead eyebrow="Agent team" title="Who does what" />
            <div className="team-list">
              {TEAM.map((member) => (
                <div className="team-row" key={member.name}>
                  <span className={`agent-badge ${agentTone(member.name)}`}>{member.name.replace('-agent', '')}</span>
                  <span className="muted small">{member.role}</span>
                </div>
              ))}
            </div>
            <div className="policy-foot">
              <Icon name="shield" size={14} />
              Reviewer can escalate; it cannot approve around a guardrail.
            </div>
          </Card>

          <Card className="rail-card">
            <CardHead
              eyebrow="Run history"
              title="Audit log"
              actions={
                <button type="button" className="btn bare sm" onClick={loadHistory}>
                  <Icon name="refresh" size={14} />
                </button>
              }
            />
            <div className="run-list">
              {history.length ? (
                history.map((item) => (
                  <button key={item.id} type="button" className={`run-row ${run?.id === item.id ? 'selected' : ''}`} onClick={() => openHistoryRun(item.id)}>
                    <div className="run-row-top">
                      <span className="run-id">{item.id.replace('run_', '#')}</span>
                      <Status value={item.status} />
                    </div>
                    <div className="run-goal">{item.goal}</div>
                    <div className="run-meta">
                      <span>{timeAgo(item.started_at)}</span>
                      <span>{item.planner}</span>
                      {item.score != null && <span>{item.score}/100</span>}
                    </div>
                  </button>
                ))
              ) : (
                <Empty title="No runs yet" hint="Your first run will appear here." icon="layers" />
              )}
            </div>
          </Card>

          <Card className="rail-card">
            <CardHead eyebrow="Model routing" title="Cost-aware by default" />
            <ul className="routing-list">
              <li>
                <span>Planning</span>
                <strong>rules / LLM</strong>
                <small>low volume, validated output</small>
              </li>
              <li>
                <span>Extraction</span>
                <strong>regex + heuristics</strong>
                <small>high volume, sLM-ready</small>
              </li>
              <li>
                <span>Review</span>
                <strong>policy engine</strong>
                <small>auditable, never sampled</small>
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
