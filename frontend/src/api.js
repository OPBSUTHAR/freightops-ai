const BASE = import.meta.env.VITE_API_BASE || '';

export async function api(path, { method = 'GET', body, signal } = {}) {
  const isForm = body instanceof FormData;
  const response = await fetch(`${BASE}${path}`, {
    method,
    signal,
    headers: isForm ? undefined : body ? { 'Content-Type': 'application/json' } : undefined,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  const raw = await response.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = { detail: raw };
  }
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}
