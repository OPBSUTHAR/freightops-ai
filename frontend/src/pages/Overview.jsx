import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { Card, CardHead, Empty, ErrorNote, Icon, Meter, Spinner, Status, duration, money, pct, pretty, severityTone, shortTime, timeAgo } from '../ui.jsx';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'in_transit', label: 'In transit' },
  { id: 'exception', label: 'Exceptions' },
  { id: 'held_for_approval', label: 'Approvals' },
  { id: 'delivered', label: 'Delivered' },
];

function RiskBadge({ risk }) {
  if (!risk) return <span className="muted small">—</span>;
  const level = risk.level || 'none';
  if (level === 'none') return <span className="risk-chip none">on plan</span>;
  return (
    <span className={`risk-chip ${level}`} title={(risk.reasons || []).join(' · ')}>
      <i />
      {level}
    </span>
  );
}

export default function Overview({ meta, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const payload = await api('/api/dashboard');
      setData(payload);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(() => load(false), 45000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!detail) return undefined;
    const onKey = (event) => event.key === 'Escape' && setDetail(null);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [detail]);

  const openShipment = async (ref) => {
    setDetailLoading(true);
    setDetailError('');
    setDetail({ ref, loading: true });
    try {
      const payload = await api(`/api/shipments/${ref}`);
      setDetail(payload);
    } catch (err) {
      setDetailError(err.message);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const shipments = data?.shipments || [];
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return shipments.filter((shipment) => {
      if (filter !== 'all' && shipment.status !== filter) return false;
      if (!needle) return true;
      return ['ref', 'customer', 'origin', 'destination', 'carrier', 'commodity'].some((key) =>
        String(shipment[key] || '').toLowerCase().includes(needle),
      );
    });
  }, [shipments, filter, query]);

  const kpis = data?.kpis;
  const policy = data?.policy || meta?.policy || {};
  const runs = data?.runs || [];
  const exceptions = data?.exceptions || [];

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <span className="live-dot" /> Live operations
          </div>
          <h1>Freight operations control tower</h1>
          <p>
            Quote, book, track and reconcile freight with planner, executor and reviewer agents. Every booking above{' '}
            <strong>{money(policy.max_auto_book_usd)}</strong> stops for a human.
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn ghost" onClick={() => load()}>
            <Icon name="refresh" size={16} />
            Refresh
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => onNavigate('studio', { goal: 'Run full autopilot: quote and book Los Angeles, CA to Denver, CO for 8,200 lbs' })}
          >
            <Icon name="bolt" size={16} />
            Run autopilot
          </button>
        </div>
      </div>

      <ErrorNote error={error} onRetry={() => load()} />

      {loading && !data ? (
        <Spinner label="Pulling live shipment data" />
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-top">
                <span>Active loads</span>
                <Icon name="route" size={17} />
              </div>
              <strong className="kpi-value">{kpis?.active_loads ?? '—'}</strong>
              <div className="kpi-foot">
                <span className="tone-blue">{kpis?.in_exception ?? 0} in exception</span>
                <span>across {shipments.length} records</span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-top">
                <span>At risk</span>
                <Icon name="alert" size={17} />
              </div>
              <strong className="kpi-value">{kpis?.at_risk ?? '—'}</strong>
              <div className="kpi-foot">
                <span className="tone-violet">ETA slip, missed scan, customs</span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-top">
                <span>Open exceptions</span>
                <Icon name="shield" size={17} />
              </div>
              <strong className="kpi-value">{kpis?.open_exceptions ?? '—'}</strong>
              <div className="kpi-foot">
                <span className={(kpis?.critical_exceptions || 0) > 0 ? 'tone-danger' : 'muted'}>
                  {kpis?.critical_exceptions ?? 0} critical
                </span>
                <span>human-only closure</span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-top">
                <span>Avg margin</span>
                <Icon name="bolt" size={17} />
              </div>
              <strong className="kpi-value">{pct(kpis?.avg_margin_pct)}</strong>
              <div className="kpi-foot">
                <span className="tone-green">floor {pct(policy.min_margin_pct, 0)}</span>
                <span>on booked loads</span>
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-top">
                <span>Auto-booked</span>
                <Icon name="cpu" size={17} />
              </div>
              <strong className="kpi-value">{pct(kpis?.auto_booked_pct, 0)}</strong>
              <div className="kpi-foot">
                <span className="tone-blue">straight-through</span>
                <span>rest held by policy</span>
              </div>
            </div>
          </div>

          <div className="grid-main">
            <Card className="board">
              <CardHead
                eyebrow="Load board"
                title="Active shipments"
                sub={`${filtered.length} of ${shipments.length} loads shown`}
                actions={
                  <div className="chips">
                    {FILTERS.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`chip ${filter === item.id ? 'active' : ''}`}
                        onClick={() => setFilter(item.id)}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                }
              />

              <div className="board-tools">
                <label className="search">
                  <Icon name="search" size={15} />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search ref, customer, lane or carrier"
                    aria-label="Search shipments"
                  />
                </label>
                <span className="muted small">Click a row for the full trail</span>
              </div>

              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Shipment</th>
                      <th>Lane</th>
                      <th>Carrier</th>
                      <th>Status</th>
                      <th className="num">Revenue</th>
                      <th>ETA / risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((shipment) => (
                      <tr key={shipment.id} onClick={() => openShipment(shipment.ref)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && openShipment(shipment.ref)}>
                        <td>
                          <div className="ref">{shipment.ref}</div>
                          <div className="muted small">{shipment.customer}</div>
                        </td>
                        <td>
                          <div className="lane">
                            <span>{shipment.origin}</span>
                            <Icon name="arrow" size={12} />
                            <span>{shipment.destination}</span>
                          </div>
                          <div className="muted small">
                            {shipment.mode} · {shipment.weight_lb?.toLocaleString()} lb
                          </div>
                        </td>
                        <td>
                          <div>{shipment.carrier}</div>
                          <div className="muted small">{shipment.scac}</div>
                        </td>
                        <td>
                          <Status value={shipment.status} />
                        </td>
                        <td className="num">
                          <div className="money">{money(shipment.sell)}</div>
                          <div className="muted small">{pct(shipment.margin_pct)} margin</div>
                        </td>
                        <td>
                          <div className="small">{shipment.status === 'delivered' ? 'Delivered' : shortTime(shipment.eta)}</div>
                          <RiskBadge risk={shipment.risk} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!filtered.length && <Empty title="No loads match this view" hint="Clear the search or switch filters." icon="filter" />}
              </div>
            </Card>

            <div className="rail">
              <Card className="rail-card">
                <CardHead
                  eyebrow="Agent activity"
                  title="Recent runs"
                  actions={
                    <button type="button" className="btn bare sm" onClick={() => onNavigate('studio')}>
                      Open studio <Icon name="arrow" size={14} />
                    </button>
                  }
                />
                <div className="run-list">
                  {runs.length ? (
                    runs.map((run) => (
                      <button key={run.id} type="button" className="run-row" onClick={() => onNavigate('studio', { runId: run.id })}>
                        <div className="run-row-top">
                          <span className={`run-id`}>{run.id.replace('run_', '#')}</span>
                          <Status value={run.status} />
                        </div>
                        <div className="run-goal">{run.goal}</div>
                        <div className="run-meta">
                          <span>{timeAgo(run.started_at)}</span>
                          <span>{run.planner}</span>
                          {run.score != null && <span className="tone-green">{run.score}/100</span>}
                        </div>
                      </button>
                    ))
                  ) : (
                    <Empty title="No agent runs yet" hint="Start in the agent studio." icon="bolt" />
                  )}
                </div>
              </Card>

              <Card className="rail-card">
                <CardHead eyebrow="Exception queue" title={`${exceptions.length} open`} sub="High and critical need a human." />
                <div className="exc-list">
                  {exceptions.slice(0, 5).map((exception) => (
                    <button
                      key={exception.id}
                      type="button"
                      className="exc-row"
                      onClick={() => exception.shipment_ref && openShipment(exception.shipment_ref)}
                    >
                      <div className="exc-top">
                        <span className={`sev ${severityTone(exception.severity)}`}>{exception.severity}</span>
                        <span className="muted small">{exception.shipment_ref}</span>
                        <span className="muted small push">{timeAgo(exception.detected_at)}</span>
                      </div>
                      <strong>{exception.label || pretty(exception.type)}</strong>
                      <p>{exception.summary}</p>
                    </button>
                  ))}
                  {!exceptions.length && <Empty title="Queue is clear" hint="No open exceptions." icon="shield" />}
                </div>
              </Card>

              <Card className="rail-card policy-card">
                <CardHead eyebrow="Operating policy" title="Hard guardrails" />
                <ul className="policy-list">
                  <li>
                    <span>Margin floor</span>
                    <strong>{pct(policy.min_margin_pct, 0)}</strong>
                  </li>
                  <li>
                    <span>Auto-book cap</span>
                    <strong>{money(policy.max_auto_book_usd)}</strong>
                  </li>
                  <li>
                    <span>Carrier reliability</span>
                    <strong>{pct(policy.carrier_reliability_floor * 100, 0)}</strong>
                  </li>
                  <li>
                    <span>Document confidence</span>
                    <strong>{pct(policy.doc_confidence_floor * 100, 0)}</strong>
                  </li>
                  <li>
                    <span>Run spend cap</span>
                    <strong>{money(policy.run_budget_usd, 2)}</strong>
                  </li>
                </ul>
                <div className="policy-foot">
                  <Icon name="shield" size={14} />
                  Enforced in code, not in the prompt.
                </div>
              </Card>
            </div>
          </div>
        </>
      )}

      {detail && (
        <div className="drawer-backdrop" onClick={() => setDetail(null)} role="presentation">
          <aside className="drawer" onClick={(event) => event.stopPropagation()} aria-label="Shipment detail">
            {detail.loading || detailLoading ? (
              <Spinner label="Loading shipment trail" />
            ) : detail.shipment ? (
              <>
                <div className="drawer-head">
                  <div>
                    <div className="eyebrow">Shipment</div>
                    <h2>{detail.shipment.ref}</h2>
                    <p className="muted">{detail.shipment.customer}</p>
                  </div>
                  <button type="button" className="icon-btn" onClick={() => setDetail(null)} aria-label="Close">
                    <Icon name="x" size={18} />
                  </button>
                </div>

                <div className="drawer-status">
                  <Status value={detail.shipment.status} />
                  <RiskBadge risk={detail.shipment.risk} />
                  <span className="muted small">
                    booked {timeAgo(detail.shipment.booked_at)} · ETA {shortTime(detail.shipment.eta)}
                  </span>
                </div>

                <div className="route-card">
                  <div className="route-points">
                    <div>
                      <span className="route-kicker">Origin</span>
                      <strong>{detail.shipment.origin}</strong>
                    </div>
                    <div className="route-line">
                      <span />
                      <em>{detail.shipment.mode}</em>
                    </div>
                    <div>
                      <span className="route-kicker">Destination</span>
                      <strong>{detail.shipment.destination}</strong>
                    </div>
                  </div>
                  <div className="route-meta">
                    <span>{detail.shipment.carrier}</span>
                    <span>{detail.shipment.scac}</span>
                    <span>{detail.shipment.weight_lb?.toLocaleString()} lb</span>
                    <span>{detail.shipment.equipment}</span>
                  </div>
                </div>

                <div className="drawer-stats">
                  <div>
                    <span>Buy</span>
                    <strong>{money(detail.shipment.buy, 2)}</strong>
                  </div>
                  <div>
                    <span>Sell</span>
                    <strong>{money(detail.shipment.sell, 2)}</strong>
                  </div>
                  <div>
                    <span>Margin</span>
                    <strong className="tone-green">{pct(detail.shipment.margin_pct)}</strong>
                  </div>
                </div>
                <Meter value={detail.shipment.margin_pct * 4} tone="green" />

                {(detail.shipment.risk?.reasons || []).length > 0 && (
                  <div className="drawer-block">
                    <h3>Risk signals</h3>
                    <ul className="bullet-list">
                      {detail.shipment.risk.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="drawer-block">
                  <h3>Tracking trail</h3>
                  <div className="timeline">
                    {[...(detail.shipment.events || [])].reverse().map((event, index) => (
                      <div className="timeline-row" key={`${event.at}-${index}`}>
                        <span className="timeline-dot" />
                        <div>
                          <strong>{event.label}</strong>
                          <div className="muted small">
                            {event.location} · {shortTime(event.at)} · {event.source}
                          </div>
                        </div>
                      </div>
                    ))}
                    {!(detail.shipment.events || []).length && <p className="muted small">No scans yet.</p>}
                  </div>
                </div>

                <div className="drawer-block">
                  <h3>Exceptions</h3>
                  {(detail.exceptions || []).length ? (
                    detail.exceptions.map((exception) => (
                      <div className="mini-row" key={exception.id}>
                        <span className={`sev ${severityTone(exception.severity)}`}>{exception.severity}</span>
                        <div>
                          <strong>{exception.label}</strong>
                          <p className="muted small">{exception.summary}</p>
                        </div>
                        <Status value={exception.status} />
                      </div>
                    ))
                  ) : (
                    <p className="muted small">No exceptions on this shipment.</p>
                  )}
                </div>

                <div className="drawer-block">
                  <h3>Documents</h3>
                  {(detail.documents || []).length ? (
                    detail.documents.map((document) => (
                      <div className="mini-row" key={document.id}>
                        <Icon name="doc" size={18} />
                        <div>
                          <strong>{document.filename}</strong>
                          <p className="muted small">
                            {pretty(document.kind)} · {Math.round((document.confidence || 0) * 100)}% confidence
                          </p>
                        </div>
                        <Status value={document.status} />
                      </div>
                    ))
                  ) : (
                    <p className="muted small">No documents ingested.</p>
                  )}
                </div>

                <div className="drawer-actions">
                  <button
                    type="button"
                    className="btn primary"
                    onClick={() => onNavigate('studio', { goal: `Track ${detail.shipment.ref}, assess ETA risk and list open exceptions` })}
                  >
                    <Icon name="bolt" size={15} />
                    Track with agents
                  </button>
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => onNavigate('studio', { goal: `Extract the invoice for ${detail.shipment.ref} and run three-way match` })}
                  >
                    <Icon name="doc" size={15} />
                    Document match
                  </button>
                </div>
              </>
            ) : (
              <p className="muted">{detailError || 'Shipment not found.'}</p>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
