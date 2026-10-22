import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import { Icon, Status } from './ui.jsx';
import Overview from './pages/Overview.jsx';
import AgentStudio from './pages/AgentStudio.jsx';
import Documents from './pages/Documents.jsx';
import Evals from './pages/Evals.jsx';
import Knowledge from './pages/Knowledge.jsx';
import About from './pages/About.jsx';

const NAV = [
  { id: 'overview', label: 'Control tower', short: 'Tower', icon: 'grid' },
  { id: 'studio', label: 'Agent studio', short: 'Agents', icon: 'bolt' },
  { id: 'documents', label: 'Documents', short: 'Docs', icon: 'doc' },
  { id: 'evals', label: 'Evals', short: 'Evals', icon: 'flask' },
  { id: 'knowledge', label: 'Knowledge', short: 'RAG', icon: 'book' },
  { id: 'about', label: 'About', short: 'About', icon: 'user' },
];

const TITLES = Object.fromEntries(NAV.map((item) => [item.id, item.label]));

function parseHash() {
  const raw = window.location.hash.replace(/^#/, '');
  const [candidate, runId] = raw.split('/');
  const page = NAV.some((item) => item.id === candidate) ? candidate : 'overview';
  return { page, runId: runId || null };
}

export default function App() {
  const initialRoute = parseHash();
  const [page, setPage] = useState(initialRoute.page);
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState('');
  const [pendingGoal, setPendingGoal] = useState(null);
  const [initialRun, setInitialRun] = useState(initialRoute.runId ? { id: initialRoute.runId, nonce: 0 } : null);
  const [initialRef, setInitialRef] = useState(null);

  useEffect(() => {
    const onHashChange = () => {
      const route = parseHash();
      setPage(route.page);
      if (route.runId) setInitialRun({ id: route.runId, nonce: Date.now() });
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api('/api/meta')
      .then((data) => !cancelled && setMeta(data))
      .catch((error) => !cancelled && setMetaError(error.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const navigate = useCallback((next, payload = {}) => {
    if (payload.goal) setPendingGoal({ text: payload.goal, nonce: Date.now() });
    if (payload.runId) setInitialRun({ id: payload.runId, nonce: Date.now() });
    if (payload.shipmentRef) setInitialRef({ ref: payload.shipmentRef, nonce: Date.now() });
    const hash = `#${next}${payload.runId ? `/${payload.runId}` : ''}`;
    if (window.location.hash !== hash) window.location.hash = hash;
    setPage(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const developer = meta?.developer || 'Omprakash Suthar';
  const github = meta?.developer_github || 'OPBSUTHAR';
  const githubUrl = meta?.github_url || `https://github.com/${github}`;
  const llmMode = meta?.llm_mode === 'rules' || !meta ? 'Rules baseline' : 'Model routed';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button type="button" className="brand" onClick={() => navigate('overview')} aria-label="FreightOps AI home">
          <span className="brand-mark">
            <span>FO</span>
          </span>
          <span className="brand-text">
            <strong>
              FreightOps<span>AI</span>
            </strong>
            <small>Agent control tower</small>
          </span>
        </button>

        <nav className="nav" aria-label="Sections">
          <div className="nav-label">Workspace</div>
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => navigate(item.id)}
              aria-current={page === item.id ? 'page' : undefined}
            >
              <Icon name={item.icon} size={18} />
              <span className="nav-full">{item.label}</span>
              <span className="nav-short">{item.short}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="credit-card">
            <span className="avatar">OS</span>
            <div className="credit-copy">
              <span>Designed &amp; built by</span>
              <strong>{developer}</strong>
              <a className="credit-github" href={githubUrl} target="_blank" rel="noreferrer">
                @{github}
              </a>
              <small>{meta?.developer_role || 'AI / Platform Engineer'}</small>
            </div>
          </div>
          <div className="env-row">
            <span className="live-dot" />
            <span>{llmMode}</span>
            <span className="env-sep">·</span>
            <span>{meta?.storage || 'memory'}</span>
          </div>
          <div className="version-row">
            <span>v{meta?.version || '1.0.0'}</span>
            <span>agentic ops demo</span>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumbs">
            <span className="crumb-root">Control tower</span>
            <Icon name="arrow" size={14} className="crumb-arrow" />
            <strong>{TITLES[page]}</strong>
          </div>
          <div className="topbar-actions">
            {metaError && <span className="text-danger tiny">API offline</span>}
            <span className="env-pill" title={metaError || 'Runtime status'}>
              <i className="dot" />
              {metaError ? 'Backend unreachable' : meta ? `${llmMode} · ${meta.storage}` : 'Connecting'}
            </span>
            {page !== 'studio' && (
              <button type="button" className="btn primary sm" onClick={() => navigate('studio')}>
                <Icon name="bolt" size={15} />
                New agent run
              </button>
            )}
          </div>
        </header>

        <main className="content">
          <div className="page" key={page}>
            {page === 'overview' && <Overview meta={meta} onNavigate={navigate} />}
            {page === 'studio' && (
              <AgentStudio pendingGoal={pendingGoal} initialRun={initialRun} initialRef={initialRef} onNavigate={navigate} />
            )}
            {page === 'documents' && <Documents initialRef={initialRef} />}
            {page === 'evals' && <Evals />}
            {page === 'knowledge' && <Knowledge />}
            {page === 'about' && <About meta={meta} />}
          </div>

          <footer className="foot">
            <span>
              FreightOps AI · designed and built by <strong>{developer}</strong> · GitHub{' '}
              <a href={githubUrl} target="_blank" rel="noreferrer">
                @{github}
              </a>
            </span>
            <span className="foot-right">
              <span className="dot-sep" /> Python · FastAPI · MongoDB-shaped APIs · React
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
