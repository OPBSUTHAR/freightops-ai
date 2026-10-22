import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Card, CardHead, Empty, ErrorNote, Icon, ScoreRing, Spinner, Status, duration } from '../ui.jsx';

const FOCUS_TONE = {
  Pricing: 'blue',
  Guardrails: 'amber',
  'Human-in-the-loop': 'violet',
  Documents: 'green',
  Security: 'red',
  Retrieval: 'blue',
  'Agent orchestration': 'violet',
};

export default function Evals() {
  const [data, setData] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setRunning(true);
    setError('');
    try {
      setData(await api('/api/evals/run', { method: 'POST' }));
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summary = data?.summary;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <span className="live-dot" /> Evaluation harness
          </div>
          <h1>Prove the agents still behave</h1>
          <p>
            A CI-ready suite that exercises pricing, guardrails, extraction, retrieval, security and a full quote-to-book run.
            Every case runs against an isolated store.
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn primary" onClick={run} disabled={running}>
            {running ? <span className="spinner small" /> : <Icon name="flask" size={15} />}
            {running ? 'Running suite…' : 'Run eval suite'}
          </button>
        </div>
      </div>

      <ErrorNote error={error} onRetry={run} />

      {running && !data ? (
        <Spinner label="Running nine behavioral evals" />
      ) : (
        data && (
          <>
            <Card className="eval-summary">
              <div className="eval-score">
                <ScoreRing score={summary.score} size={104} label="pass rate" />
                <div>
                  <div className="eyebrow">Suite result</div>
                  <h2>{summary.score}% behavioral coverage</h2>
                  <p className="muted">
                    {summary.passed} of {summary.total} cases passed in {summary.duration_ms} ms. A failing case blocks release.
                  </p>
                </div>
              </div>
              <div className="eval-stats">
                <div>
                  <span>Passed</span>
                  <strong className="tone-green">{summary.passed}</strong>
                </div>
                <div>
                  <span>Failed</span>
                  <strong className={summary.failed ? 'tone-danger' : ''}>{summary.failed}</strong>
                </div>
                <div>
                  <span>Duration</span>
                  <strong>{summary.duration_ms} ms</strong>
                </div>
                <div>
                  <span>Last run</span>
                  <strong>{new Date(data.ran_at).toLocaleTimeString()}</strong>
                </div>
              </div>
            </Card>

            <div className="eval-grid">
              <Card className="eval-list">
                <CardHead eyebrow="Cases" title="Behavioral checklist" sub="Each assertion maps to a production failure mode." />
                {data.results.map((result) => (
                  <div className={`eval-row ${result.passed ? 'pass' : 'fail'}`} key={result.id}>
                    <span className={`eval-icon ${result.passed ? 'pass' : 'fail'}`}>
                      <Icon name={result.passed ? 'check' : 'x'} size={15} />
                    </span>
                    <div className="eval-copy">
                      <div className="eval-top">
                        <strong>{result.name}</strong>
                        <span className={`focus ${FOCUS_TONE[result.focus] || 'gray'}`}>{result.focus}</span>
                      </div>
                      <p>{result.detail}</p>
                    </div>
                    <span className="eval-ms">{result.ms} ms</span>
                  </div>
                ))}
                {!data.results.length && <Empty title="No cases ran" icon="flask" />}
              </Card>

              <div className="eval-rail">
                <Card className="rail-card">
                  <CardHead eyebrow="Why it matters" title="Release gate, not a demo" />
                  <ul className="bullet-list">
                    <li>Catches pricing regressions before a quote reaches a customer.</li>
                    <li>Proves guardrails hold when the prompt or model changes.</li>
                    <li>Keeps the human approval gate wired to the booking tool.</li>
                    <li>Exercises real document parsing, not fixture snapshots.</li>
                  </ul>
                  <div className="policy-foot">
                    <Icon name="shield" size={14} />
                    Run this in CI on every prompt, tool or model change.
                  </div>
                </Card>

                <Card className="rail-card">
                  <CardHead eyebrow="Coverage" title="Failure modes" />
                  <div className="coverage-list">
                    {['Pricing', 'Guardrails', 'Human-in-the-loop', 'Documents', 'Security', 'Retrieval', 'Agent orchestration'].map((item) => (
                      <div key={item} className="coverage-row">
                        <span className={`focus ${FOCUS_TONE[item] || 'gray'}`}>{item}</span>
                        <Icon name="check" size={14} />
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="rail-card">
                  <CardHead eyebrow="Telemetry" title="What is recorded" />
                  <ul className="bullet-list">
                    <li>Trace per agent action with latency and spend.</li>
                    <li>Tool inputs, outputs and retry counts.</li>
                    <li>Reviewer checks, weights and final score.</li>
                    <li>Human decisions with actor and note.</li>
                  </ul>
                </Card>
              </div>
            </div>
          </>
        )
      )}
    </>
  );
}
