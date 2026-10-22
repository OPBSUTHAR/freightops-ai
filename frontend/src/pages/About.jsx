import React from 'react';
import { Card, CardHead, Icon } from '../ui.jsx';

const CAPABILITIES = [
  {
    n: '01',
    title: 'Multi-agent freight workflows',
    body: 'Planner, executor, reviewer and domain agents run quoting, booking, track-and-trace, document processing and exception handling as one auditable pipeline.',
    proof: 'backend/app/agents · orchestrator.py',
  },
  {
    n: '02',
    title: 'Agentic delivery, reviewed',
    body: 'The build is organized for an agentic coding loop: explicit tool contracts, deterministic fixtures, a behavioral eval suite and a reviewer gate on every change.',
    proof: 'backend/app/agents/evals.py · 9 passing cases',
  },
  {
    n: '03',
    title: 'Python services, React console, clean APIs',
    body: 'FastAPI endpoints with Mongo-shaped documents, a repository abstraction that runs on MongoDB or in-memory, and a responsive operator UI with dense, legible state.',
    proof: 'backend/app/api.py · frontend/src',
  },
  {
    n: '04',
    title: 'Prompts, tools, memory and retrieval',
    body: 'Versioned prompts, a validated tool catalog, per-run artifacts and vector retrieval over tariffs and SOPs — with explicit model routing for reliability and cost.',
    proof: 'agents/prompts.py · app/rag · MODEL_ROUTING',
  },
  {
    n: '05',
    title: 'Production hardening',
    body: 'Guardrails live in code: margin floor, carrier reliability, auto-book cap, document confidence, prompt-injection quarantine, spend budget and a refusal to auto-close critical exceptions.',
    proof: 'app/guardrails.py · traces · eval gate',
  },
  {
    n: '06',
    title: 'Integrations and document pipelines',
    body: 'Carrier rate panel and tender flow, EDI-ready event vocabulary, PDF text extraction, OCR adapter boundary, BOL/invoice/packing-list fields and three-way match.',
    proof: 'app/domain/rates.py · pipelines/extraction.py',
  },
];

const STACK = ['Python 3', 'FastAPI', 'Pydantic', 'MongoDB', 'React 18', 'Vite', 'RAG', 'OCR', 'pytest'];

export default function About({ meta }) {
  const developer = meta?.developer || 'Omprakash Suthar';
  const role = meta?.developer_role || 'AI / Platform Engineer — freight operations';

  return (
    <>
      <div className="about-hero">
        <div className="about-id">
          <span className="monogram">OS</span>
          <div>
            <div className="eyebrow">Designed &amp; built by</div>
            <h1>{developer}</h1>
            <p className="about-role">{role}</p>
          </div>
        </div>
        <p className="about-lede">
          This control tower is a working answer to a simple question: what does it take for AI agents to run freight
          operations responsibly? Typed tools, explicit policy, human gates, retrieval with citations, and telemetry that
          makes every decision explainable.
        </p>
        <div className="about-stats">
          <div>
            <strong>8</strong>
            <span>agents in the roster</span>
          </div>
          <div>
            <strong>11</strong>
            <span>guarded tools</span>
          </div>
          <div>
            <strong>9</strong>
            <span>behavioral evals</span>
          </div>
          <div>
            <strong>0</strong>
            <span>API keys required</span>
          </div>
        </div>
      </div>

      <Card className="about-section">
        <CardHead
          eyebrow="Capability map"
          title="The work, end to end"
          sub="Each capability is implemented here — not listed on a slide."
        />
        <div className="cap-grid">
          {CAPABILITIES.map((capability) => (
            <article className="cap-card" key={capability.n}>
              <span className="cap-num">{capability.n}</span>
              <h3>{capability.title}</h3>
              <p>{capability.body}</p>
              <code>{capability.proof}</code>
            </article>
          ))}
        </div>
      </Card>

      <Card className="about-section">
        <CardHead
          eyebrow="Architecture"
          title="How the pieces fit"
          sub="A clean split between experience, orchestration, domain logic and storage."
        />
        <div className="arch">
          <div className="arch-node">
            <span className="arch-label">Experience</span>
            <strong>React console</strong>
            <small>load board · studio · documents · evals</small>
          </div>
          <span className="arch-arrow">
            <Icon name="arrow" size={16} />
          </span>
          <div className="arch-node">
            <span className="arch-label">Interface</span>
            <strong>FastAPI</strong>
            <small>clean REST · typed schemas · CORS</small>
          </div>
          <span className="arch-arrow">
            <Icon name="arrow" size={16} />
          </span>
          <div className="arch-node accent">
            <span className="arch-label">Intelligence</span>
            <strong>Agent runtime</strong>
            <small>planner · executor · reviewer · domain agents</small>
          </div>
          <span className="arch-arrow">
            <Icon name="arrow" size={16} />
          </span>
          <div className="arch-node">
            <span className="arch-label">Domain</span>
            <strong>Freight services</strong>
            <small>rates · tracking · extraction · exceptions</small>
          </div>
          <span className="arch-arrow">
            <Icon name="arrow" size={16} />
          </span>
          <div className="arch-node">
            <span className="arch-label">Storage</span>
            <strong>Repository</strong>
            <small>MongoDB or in-memory, same contract</small>
          </div>
        </div>

        <div className="arch-side">
          <div>
            <Icon name="book" size={16} />
            <div>
              <strong>RAG index</strong>
              <span>Tariffs and SOPs retrieved before pricing or triage.</span>
            </div>
          </div>
          <div>
            <Icon name="shield" size={16} />
            <div>
              <strong>Guardrails</strong>
              <span>Policy enforced outside the prompt, around every tool.</span>
            </div>
          </div>
          <div>
            <Icon name="flask" size={16} />
            <div>
              <strong>Evals + traces</strong>
              <span>Behavioral regression gate and a persisted audit trail.</span>
            </div>
          </div>
        </div>
      </Card>

      <div className="about-two-col">
        <Card className="about-section">
          <CardHead eyebrow="Delivery" title="How this was built" />
          <ol className="delivery-list">
            <li>
              <strong>Plan against the role, not a tutorial.</strong>
              <span>Turn each operating requirement into a testable behavior with an owning module.</span>
            </li>
            <li>
              <strong>Contract first.</strong>
              <span>Tools and API schemas before UI. Agents can only act through validated tools.</span>
            </li>
            <li>
              <strong>Fail closed.</strong>
              <span>Every risky path — booking, posting, closing an exception — has an explicit gate.</span>
            </li>
            <li>
              <strong>Prove it with evals.</strong>
              <span>The suite is the release gate; a passing demo is not the same as a passing system.</span>
            </li>
          </ol>
        </Card>

        <Card className="about-section">
          <CardHead eyebrow="Models" title="No vendor lock-in" />
          <p className="about-copy">
            The agent runtime ships with a deterministic policy baseline, so the whole tour runs offline with no Claude,
            OpenAI or other subscription. Set <code>LLM_MODE=openai</code> with any OpenAI-compatible endpoint — GPT, Llama,
            Qwen, Groq, OpenRouter or a local Ollama model — and the planner proposes plans while validation, fallback and
            review stay in code.
          </p>
          <ul className="bullet-list">
            <li>Planning: model-proposed, tool-validated, rules fallback.</li>
            <li>Extraction: deterministic parsing now, small-model ready.</li>
            <li>Review: always the policy engine, never sampled.</li>
            <li>Spend: per-run budget recorded in the trace.</li>
          </ul>
          <div className="stack-row">
            {STACK.map((item) => (
              <span className="tag" key={item}>
                {item}
              </span>
            ))}
          </div>
        </Card>
      </div>

      <div className="credit-banner">
        <div>
          <div className="eyebrow">Built by</div>
          <strong>{developer}</strong>
          <span>{role}</span>
        </div>
        <p>
          FreightOps AI · v{meta?.version || '1.0.0'} · planner, executor and reviewer agents with a human gate on every
          decision that matters.
        </p>
      </div>
    </>
  );
}
