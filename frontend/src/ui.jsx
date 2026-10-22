import React from 'react';

const ICONS = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  bolt: <path d="M13 2 4 13.5h6.5L10 22l9-11.5h-6.5L13 2Z" />,
  doc: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>,
  flask: <><path d="M9 3h6M10 3v6l-5.5 9.2A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.8L14 9V3" /><path d="M7.5 15h9" /></>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" /><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 21c.7-4 3.2-6 7-6s6.3 2 7 6" /></>,
  play: <path d="M8 5.5v13l11-6.5-11-6.5Z" />,
  check: <path d="m5 12.5 4.5 4.5L19 7" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  alert: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5M12 17.2v.3" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  shield: <><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  route: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M8.5 6H14a3 3 0 0 1 0 6h-4a3 3 0 0 0 0 6h5.5" /></>,
  database: <><ellipse cx="12" cy="5.5" rx="7.5" ry="3" /><path d="M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13" /><path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" /></>,
  cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9.5 9.5h5v5h-5zM12 2v4M12 18v4M2 12h4M18 12h4M5 5l-2-2M21 21l-2-2" /></>,
  external: <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />,
  refresh: <><path d="M20 11a8 8 0 1 0-.7 4" /><path d="M20 5v6h-6" /></>,
  filter: <path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z" />,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5M3 17l9 5 9-5" /></>,
};

export function Icon({ name, size = 18, className = '' }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name] || ICONS.grid}
    </svg>
  );
}

const TONES = {
  green: ['approve', 'approved_by_human', 'completed', 'delivered', 'ok', 'passed', 'validated', 'posted', 'resolved', 'done', 'confirmed', 'recommended', 'tenderable'],
  amber: ['needs_approval', 'held_for_approval', 'pending_approval', 'medium', 'monitoring', 'warn', 'quoted', 'sent'],
  red: ['escalate', 'escalated', 'exception', 'failed', 'critical', 'rejected', 'rejected_by_human', 'blocked', 'cancelled'],
  blue: ['in_transit', 'running', 'low', 'booked', 'new'],
  violet: ['out_for_delivery', 'high'],
  gray: ['skipped', 'pending', 'draft', 'none', 'all'],
};

export function toneFor(value) {
  const key = String(value ?? '').toLowerCase();
  for (const [tone, values] of Object.entries(TONES)) {
    if (values.includes(key)) return tone;
  }
  return 'gray';
}

export function pretty(value) {
  return String(value ?? '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function Status({ value, label, dot = true }) {
  return (
    <span className={`pill ${toneFor(value)}`}>
      {dot && <i className="dot" />}
      {label || pretty(value)}
    </span>
  );
}

export function Card({ children, className = '', as: Tag = 'section', ...rest }) {
  return (
    <Tag className={`card ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHead({ eyebrow, title, sub, actions }) {
  return (
    <div className="card-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        {title && <h2>{title}</h2>}
        {sub && <p className="sub">{sub}</p>}
      </div>
      {actions && <div className="card-actions">{actions}</div>}
    </div>
  );
}

export function ScoreRing({ score = 0, size = 84, label = 'score' }) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  const tone = score >= 85 ? 'green' : score >= 65 ? 'amber' : 'red';
  return (
    <div className={`score-ring ${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} />
        <circle
          className="ring-value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-label">
        <strong>{Math.round(score)}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

export function Meter({ value = 0, tone = 'green', height = 6 }) {
  const width = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className={`meter ${tone}`} style={{ height }}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="loading">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  );
}

export function Empty({ title, hint, icon = 'layers' }) {
  return (
    <div className="empty">
      <Icon name={icon} size={26} />
      <strong>{title}</strong>
      {hint && <span>{hint}</span>}
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-note">
      <Icon name="alert" size={16} />
      <span>{error}</span>
      {onRetry && (
        <button type="button" className="btn bare sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export const money = (value, digits = 0) =>
  value === null || value === undefined
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);

export const pct = (value, digits = 1) =>
  value === null || value === undefined ? '—' : `${Number(value).toFixed(digits)}%`;

export const compact = (value) =>
  value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

export function timeAgo(iso) {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function shortTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function duration(start, end) {
  if (!start) return '—';
  const a = new Date(start).getTime();
  const b = end ? new Date(end).getTime() : Date.now();
  const ms = b - a;
  if (ms < 1000) return `${Math.max(ms, 0)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}m`;
}

export const severityTone = (severity) => (severity === 'critical' ? 'red' : severity === 'high' ? 'violet' : severity === 'medium' ? 'amber' : 'blue');
