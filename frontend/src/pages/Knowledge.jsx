import React, { useEffect, useState } from 'react';
import { api } from '../api.js';
import { Card, CardHead, Empty, ErrorNote, Icon, Meter, Spinner, pretty } from '../ui.jsx';

const TAGS = ['all', 'pricing', 'operations', 'compliance', 'documents', 'policy', 'integration', 'carriers'];

export default function Knowledge() {
  const [query, setQuery] = useState('detention after two free hours at a shipper');
  const [tag, setTag] = useState('all');
  const [results, setResults] = useState([]);
  const [stats, setStats] = useState(null);
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const search = async (nextQuery = query, nextTag = tag) => {
    if (!nextQuery.trim()) return;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ q: nextQuery, k: '5' });
      if (nextTag !== 'all') params.set('tag', nextTag);
      const payload = await api(`/api/rag/search?${params.toString()}`);
      setResults(payload.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api('/api/rag/stats')
      .then((payload) => {
        setStats(payload.stats);
        setDocs(payload.documents || []);
      })
      .catch((err) => setError(err.message));
    search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (event) => {
    event.preventDefault();
    search();
  };

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">
            <span className="live-dot" /> Retrieval
          </div>
          <h1>Tariffs, SOPs and policy, retrievable</h1>
          <p>
            The quoting and exception agents cite the operating corpus before they act. Embeddings are pluggable; the offline
            baseline is signed hashing so the tour works without a model key.
          </p>
        </div>
      </div>

      <ErrorNote error={error} />

      <div className="kb-grid">
        <Card className="kb-search">
          <CardHead eyebrow="Vector search" title="Ask the operating corpus" sub="Hybrid-ready retrieval over tariffs, SOPs and approval policy." />
          <form className="kb-form" onSubmit={submit}>
            <label className="search grow">
              <Icon name="search" size={15} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. liftgate fee, margin floor, customs hold" />
            </label>
            <button type="submit" className="btn primary" disabled={loading}>
              {loading ? <span className="spinner small" /> : <Icon name="search" size={15} />}
              Search
            </button>
          </form>

          <div className="chips tag-row">
            {TAGS.map((item) => (
              <button
                key={item}
                type="button"
                className={`chip ${tag === item ? 'active' : ''}`}
                onClick={() => {
                  setTag(item);
                  search(query, item);
                }}
              >
                {item === 'all' ? 'All tags' : item}
              </button>
            ))}
          </div>

          <div className="kb-results">
            {loading && !results.length && <Spinner label="Searching the index" />}
            {results.map((result) => (
              <article className="kb-hit" key={result.id}>
                <div className="kb-hit-top">
                  <div>
                    <div className="eyebrow">{result.doc_id.replaceAll('-', ' ')}</div>
                    <h3>{result.title}</h3>
                  </div>
                  <div className="kb-score">
                    <strong>{result.score.toFixed(3)}</strong>
                    <Meter value={result.score * 100} tone={result.score > 0.35 ? 'green' : 'amber'} height={4} />
                  </div>
                </div>
                <p>{result.text}</p>
                <div className="tags">
                  {result.tags.map((item) => (
                    <span className="tag" key={item}>
                      {item}
                    </span>
                  ))}
                  <span className="tag ghost">{result.id}</span>
                </div>
              </article>
            ))}
            {!loading && !results.length && <Empty title="No matches" hint="Try a different phrase or clear the tag filter." icon="book" />}
          </div>
        </Card>

        <div className="kb-rail">
          <Card className="rail-card">
            <CardHead eyebrow="Index" title="Retrieval health" />
            <div className="index-stats">
              <div>
                <span>Documents</span>
                <strong>{stats?.documents ?? '—'}</strong>
              </div>
              <div>
                <span>Chunks</span>
                <strong>{stats?.chunks ?? '—'}</strong>
              </div>
              <div>
                <span>Dimensions</span>
                <strong>{stats?.dimensions ?? '—'}</strong>
              </div>
            </div>
            <p className="muted small">Embedding: {stats?.embedding || '—'}</p>
            <div className="policy-foot">
              <Icon name="database" size={14} />
              Swap in OpenAI, Cohere or a local embedding model behind the same interface.
            </div>
          </Card>

          <Card className="rail-card">
            <CardHead eyebrow="Corpus" title={`${docs.length} source documents`} />
            <div className="corpus-list">
              {docs.map((doc) => (
                <div className="corpus-row" key={doc.id}>
                  <div>
                    <strong>{doc.title}</strong>
                    <div className="tags">
                      {doc.tags.map((item) => (
                        <span className="tag" key={item}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="muted tiny">{doc.chars.toLocaleString()} chars</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
