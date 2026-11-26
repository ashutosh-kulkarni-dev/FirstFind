// Thin API transport (shared by every file in this folder). Holds the JWT and shapes requests — it has no React
// knowledge; AuthContext is the source of truth and drives setAuth().
// In dev, API_BASE is '' so requests are relative and hit the Vite proxy
// (/api -> localhost:8000). In production (Vercel), set VITE_API_BASE to the
// deployed backend URL, e.g. https://thriftfind-api.onrender.com
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

// Token persists in localStorage so login survives a tab close / refresh (the
// backend JWT is stateless, so nothing server-side needs to remember the session).
// Storage can be unavailable (privacy modes) or hold a corrupted value; either
// used to throw here, at import time, and leave the whole app blank.
function readStored(key) {
  try { return localStorage.getItem(key) } catch { return null }
}
function readStoredUser() {
  try { return JSON.parse(readStored('tf_user') || 'null') } catch { return null }
}
let _token = readStored('tf_token') || null;
let _user = _token ? readStoredUser() : null;

// Fired when the server rejects our token (401). AuthContext listens and logs out
// cleanly instead of leaving a half-broken, "logged-in-looking" UI.
export const AUTH_UNAUTHORIZED_EVENT = 'tf:auth:unauthorized';

export function setAuth(token, user) {
  _token = token; _user = user;
  try {
    if (token) {
      localStorage.setItem('tf_token', token);
      localStorage.setItem('tf_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('tf_token');
      localStorage.removeItem('tf_user');
    }
  } catch { /* storage unavailable: the session just won't survive a reload */ }
}
export function getToken() { return _token; }
export function getUser() { return _user; }

// The server sends `detail` as a string, or (for a rejected form field) as a
// list of {msg} objects — which used to reach the page as "[object Object]".
function errorText(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => {
      // The email validator's wording ("value is not a valid email address: The
      // part after the @-sign is a special-use or reserved name…") is too technical.
      if (d?.loc?.at(-1) === 'email') return 'Please enter a valid email address.'
      return (d?.msg || '').replace(/^Value error, /, '')
    }).filter(Boolean).join(' ')
  }
  return ''
}

export async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    // An expired/invalid token on an authenticated request → tell the app to log
    // out. Skip /me: it is the validation probe itself, handled by the caller.
    if (res.status === 401 && _token && !path.endsWith('/api/auth/me')) {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    const body = await res.json().catch(() => ({}));
    throw new Error(errorText(body.detail) || `Request failed (${res.status})`);
  }
  // 204 No Content (e.g. DELETE /api/lists/{id}) has no body to parse.
  if (res.status === 204) return null;
  return res.json();
}

const json = (method, body) => ({ method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
export const post = (path, body) => req(path, json('POST', body))
export const patch = (path, body) => req(path, json('PATCH', body))
export const del = (path) => req(path, json('DELETE'))
