import React, { useEffect, useRef, useState } from 'react';
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
  money,
  pretty,
  severityTone,
  shortTime,
} from '../ui.jsx';

const KINDS = [
  { id: 'auto', label: 'Auto-detect' },
  { id: 'invoice', label: 'Invoice' },
  { id: 'bol', label: 'Bill of lading' },
  { id: 'packing_list', label: 'Packing list' },
];

const formatValue = (field) => {
  if (field === null || field === undefined) return '—';
  const value = typeof field === 'object' && 'value' in field ? field.value : field;
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  return String(value);
};

const confidenceTone = (value = 0) => (value >= 0.9 ? 'green' : value >= 0.75 ? 'amber' : 'red');

export default function Documents({ initialRef }) {
  const [samples, setSamples] = useState([]);
  const [text, setText] = useState('');
  const [kind, setKind] = useState('auto');
  const [shipmentRef, setShipmentRef] = useState('');
  const [selected, setSelected] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [recent, setRecent] = useState([]);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  const loadRecent = async () => {
    try {
      setRecent(await api('/api/documents'));
    } catch {
      /* keep the console usable */
    }
  };

  useEffect(() => {
    let cancelled = false;
    api('/api/documents/samples')
      .then((data) => {
        if (cancelled) return;
        setSamples(data);
        const invoice = data.find((sample) => sample.id === 'invoice') || data[0];
        if (invoice) {
          setText(invoice.text);
          setSelected(invoice.id);
        }
      })
      .catch((err) => !cancelled && setError(err.message));
    loadRecent();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (initialRef?.ref) setShipmentRef(initialRef.ref);
  }, [initialRef]);

  const chooseSample = (sample) => {
    setSelected(sample.id);
    setText(sample.text);
    setKind('auto');
    setResult(null);
    setError('');
  };

  const runExtraction = async () => {
    if (!text.trim()) {
      setError('Paste a document or load a sample first.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const sample = samples.find((item) => item.id === selected);
      const payload = {
        text,
        kind,
        shipment_ref: shipmentRef.trim() ? shipmentRef.trim().toUpperCase() : undefined,
        filename: sample ? `${sample.id}.pdf` : 'pasted-document.txt',
      };
      const response = await api('/api/documents/extract', { method: 'POST', body: payload });
      setResult(response);
      loadRecent();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      if (shipmentRef.trim()) form.append('shipment_ref', shipmentRef.trim().toUpperCase());
      const response = await api('/api/documents/upload', { method: 'POST', body: form });
      setResult(response);
      setSelected('');
      loadRecent();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setDragging(false);
    }
  };

  const extraction = result?.extraction;
  const document = result?.document;
  const guardrail = result?.guardrail;
  const fields = document?.fields || {};
  const validations = document?.validations || [];
  const findings = guardrail?.findings || [];

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <span className="live-dot" /> Document intelligence
          </div>
          <h1>BOL, invoice &amp; packing list ingestion</h1>
          <p>
            OCR-ready extraction with per-field confidence, PII redaction, prompt-injection quarantine and a three-way match
            gate before anything posts to the ERP.
          </p>
        </div>
        <div className="head-actions">
          <span className="env-pill">
            <Icon name="shield" size={14} />
            Confidence floor 85%
          </span>
        </div>
      </div>

      <ErrorNote error={error} />

      <div className="docs-grid">
        <Card className="doc-source">
          <CardHead
            eyebrow="Source"
            title="Ingest a document"
            sub="Text-layer PDFs, TXT or pasted text. Scanned images route through the OCR adapter."
          />

          <div className="sample-row">
            {samples.map((sample) => (
              <button
                key={sample.id}
                type="button"
                className={`sample-chip ${selected === sample.id ? 'active' : ''}`}
                onClick={() => chooseSample(sample)}
              >
                <Icon name="doc" size={14} />
                {sample.label}
              </button>
            ))}
          </div>

          <textarea
            className="doc-textarea"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSelected('');
            }}
            rows={15}
            spellCheck={false}
            aria-label="Document text"
            placeholder="Paste BOL, invoice or packing list text here…"
          />

          <div className="doc-controls">
            <label className="field compact">
              <span>Document type</span>
              <select value={kind} onChange={(event) => setKind(event.target.value)}>
                {KINDS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field compact">
              <span>Link to shipment</span>
              <input value={shipmentRef} onChange={(event) => setShipmentRef(event.target.value)} placeholder="FO-4821" />
            </label>
          </div>

          <div className="doc-actions">
            <button type="button" className="btn primary" onClick={runExtraction} disabled={busy}>
              {busy ? <span className="spinner small" /> : <Icon name="flask" size={15} />}
              {busy ? 'Extracting…' : 'Extract fields'}
            </button>
            <button type="button" className="btn ghost" onClick={() => fileInput.current?.click()} disabled={busy}>
              <Icon name="upload" size={15} />
              Upload file
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,.csv,.json,.md"
              hidden
              onChange={(event) => upload(event.target.files?.[0])}
            />
          </div>

          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              upload(event.dataTransfer.files?.[0]);
            }}
            onClick={() => fileInput.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => event.key === 'Enter' && fileInput.current?.click()}
          >
            <Icon name="upload" size={18} />
            <span>Drop a PDF or text file, or click to browse</span>
          </div>
        </Card>

        <Card className="doc-result">
          <CardHead
            eyebrow="Extraction"
            title="Structured result"
            sub={document ? document.filename : 'Nothing extracted yet'}
            actions={document ? <Status value={document.status} /> : null}
          />

          {!document && <Empty title="Awaiting a document" hint="Load a sample on the left and run extraction." icon="doc" />}

          {document && (
            <>
              <div className="doc-summary">
                <ScoreRing score={Math.round((document.confidence || 0) * 100)} label="confidence" size={78} />
                <div>
                  <div className="eyebrow">{pretty(document.kind)}</div>
                  <h3>{Object.keys(fields).length} fields extracted</h3>
                  <p className="muted small">
                    {document.pii_redactions ? `${document.pii_redactions} PII values redacted · ` : ''}
                    source {document.source} · {document.requires_review ? 'human review required' : 'auto-validated'}
                  </p>
                  <div className="verdict-tags">
                    {(document.injection_signals || []).length > 0 && (
                      <span className="sev red">prompt injection quarantined</span>
                    )}
                    {validations.filter((validation) => !validation.passed).length > 0 && (
                      <span className="sev violet">{validations.filter((validation) => !validation.passed).length} validation issues</span>
                    )}
                  </div>
                </div>
              </div>

              {(document.injection_signals || []).length > 0 && (
                <div className="alert-banner">
                  <Icon name="alert" size={17} />
                  <div>
                    <strong>Instruction-override text detected</strong>
                    <p>
                      The document asked the agent to skip review. Its content was treated as data only and the posting gate
                      stayed closed.
                    </p>
                  </div>
                </div>
              )}

              <div className="field-table">
                {Object.entries(fields).map(([name, field]) => {
                  const confidence = field?.confidence ?? 0;
                  return (
                    <div className="field-row" key={name}>
                      <div className="field-name">{pretty(name)}</div>
                      <div className="field-value">{formatValue(field)}</div>
                      <div className="field-conf">
                        <span className={`tiny tone-${confidenceTone(confidence)}`}>{Math.round(confidence * 100)}%</span>
                        <Meter value={confidence * 100} tone={confidenceTone(confidence)} height={4} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {validations.length > 0 && (
                <div className="doc-block">
                  <h3>Validations</h3>
                  {validations.map((validation) => (
                    <div className={`validation ${validation.passed ? 'pass' : 'fail'}`} key={validation.code}>
                      <Icon name={validation.passed ? 'check' : 'alert'} size={14} />
                      <div>
                        <strong>{pretty(validation.code)}</strong>
                        <p>{validation.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(document.line_items || []).length > 0 && (
                <div className="doc-block">
                  <h3>Line items</h3>
                  <div className="table-wrap">
                    <table className="data-table compact-table">
                      <thead>
                        <tr>
                          <th>Description</th>
                          <th className="num">Qty</th>
                          <th className="num">Unit</th>
                          <th className="num">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {document.line_items.map((item, index) => (
                          <tr key={`${item.description}-${index}`}>
                            <td>{item.description}</td>
                            <td className="num">{item.qty}</td>
                            <td className="num">{money(item.unit_price, 2)}</td>
                            <td className="num">{money(item.amount, 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {findings.length > 0 && (
                <div className="doc-block">
                  <h3>Guardrail findings</h3>
                  {findings.map((finding, index) => (
                    <div className="validation fail" key={`${finding.code}-${index}`}>
                      <span className={`sev ${severityTone(finding.severity)}`}>{finding.severity}</span>
                      <div>
                        <strong>{pretty(finding.code)}</strong>
                        <p>{finding.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {extraction && (
                <p className="muted tiny">
                  Parsed {extraction.raw_chars} characters · confidence floor 85% · mandatory fields enforced per document type.
                </p>
              )}
            </>
          )}
        </Card>
      </div>

      <Card className="doc-recent">
        <CardHead eyebrow="Document ledger" title="Recent ingestions" sub="Linked to shipments and blocked postings stay visible." />
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th>Shipment</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Ingested</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div>{doc.filename}</div>
                    <div className="muted small">{doc.source}</div>
                  </td>
                  <td>{pretty(doc.kind)}</td>
                  <td>{doc.shipment_ref || '—'}</td>
                  <td>
                    <div className="inline-meter">
                      <Meter value={(doc.confidence || 0) * 100} tone={confidenceTone(doc.confidence)} height={4} />
                      <span className="tiny">{Math.round((doc.confidence || 0) * 100)}%</span>
                    </div>
                  </td>
                  <td>
                    <Status value={doc.status} />
                  </td>
                  <td className="muted small">{shortTime(doc.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!recent.length && <Empty title="No documents yet" hint="Extract a sample to populate the ledger." icon="doc" />}
        </div>
      </Card>
    </>
  );
}
