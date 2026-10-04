// Thin API transport. Holds the JWT and shapes requests — it has no React
// knowledge; AuthContext is the source of truth and drives setAuth().
// In dev, API_BASE is '' so requests are relative and hit the Vite proxy
// (/api -> localhost:8000). In production (Vercel), set VITE_API_BASE to the
// deployed backend URL, e.g. https://thriftfind-api.onrender.com
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

// Token persists in localStorage so login survives a tab close / refresh (the
// backend JWT is stateless, so nothing server-side needs to remember the session).
let _token = localStorage.getItem('tf_token') || null;
let _user = JSON.parse(localStorage.getItem('tf_user') || 'null');

// Fired when the server rejects our token (401). AuthContext listens and logs out
// cleanly instead of leaving a half-broken, "logged-in-looking" UI.
export const AUTH_UNAUTHORIZED_EVENT = 'tf:auth:unauthorized';

// Stable session ID for the lifetime of this browser tab.
// Sent with every chat message so the backend can maintain conversation state.
function _getSessionId() {
  let sid = sessionStorage.getItem('tf_chat_session');
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem('tf_chat_session', sid);
  }
  return sid;
}

// Drop the current chat session so the next message starts a fresh conversation.
// Called on logout so a second user on the same tab never inherits the first
// user's session/history. A new id is minted lazily on the next chat call.
export function resetSession() {
  sessionStorage.removeItem('tf_chat_session');
}

export function setAuth(token, user) {
  _token = token; _user = user;
  if (token) {
    localStorage.setItem('tf_token', token);
    localStorage.setItem('tf_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('tf_token');
    localStorage.removeItem('tf_user');
  }
}
export function getToken() { return _token; }
export function getUser() { return _user; }

async function req(path, opts = {}) {
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
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  register: (name, email, password) =>
    req('/api/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) }),
  login: (email, password) =>
    req('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  google: (credential) =>
    req('/api/auth/google', { method: 'POST', body: JSON.stringify({ credential }) }),
  me: () => req('/api/auth/me'),
  stores: (params = {}, opts = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
    return req(`/api/stores?${qs}`, opts);
  },
  areas: () => req('/api/stores/areas'),
  categories: () => req('/api/stores/categories'),
  store: (id) => req(`/api/stores/${id}`),
  nearby: (lat, lng, radius = 5) => req(`/api/stores/nearby?lat=${lat}&lng=${lng}&radius_km=${radius}`),
  addReview: (id, rating, text) =>
    req(`/api/stores/${id}/reviews`, { method: 'POST', body: JSON.stringify({ rating, text }) }),
  saveStore: (id) => req(`/api/stores/${id}/save`, { method: 'POST' }),
  zones: () => req('/api/zones'),
  clusters: () => req('/api/clusters'),
  findCluster: ({ lat, lng, radius_km, min_shops, max_shops }, opts = {}) => {
    const qs = new URLSearchParams({ lat, lng, radius_km, ...(min_shops != null ? { min_shops } : {}), ...(max_shops != null ? { max_shops } : {}) })
    return req(`/api/clusters/find?${qs}`, opts)
  },
  splitCluster: ({ lat, lng, radius_km, max_shops }) => {
    const qs = new URLSearchParams({ lat, lng, radius_km, ...(max_shops != null ? { max_shops } : {}) })
    return req(`/api/clusters/split?${qs}`)
  },
  areaCoords: () => req('/api/stores/areas/coords'),
  metroStations: () => req('/api/metro/stations'),
  metroNearest: (lat, lng) => req(`/api/metro/nearest?lat=${lat}&lng=${lng}`),
  recommendations: () => req('/api/recommendations'),
  chat: (message, origin = null) => req('/api/chat', { method: 'POST', body: JSON.stringify({ message, session_id: _getSessionId(), ...(origin ? { origin } : {}) }) }),
  conversations: () => req('/api/conversations'),
  conversation: (id) => req(`/api/conversations/${id}`),
  deleteConversation: (id) => req(`/api/conversations/${id}`, { method: 'DELETE' }),
  createList: (body) => req('/api/lists', { method: 'POST', body: JSON.stringify(body) }),
  lists: () => req('/api/lists'),
  list: (id) => req(`/api/lists/${id}`),
  updateList: (id, patch) => req(`/api/lists/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteList: (id) => req(`/api/lists/${id}`, { method: 'DELETE' }),
  claimChat: (turns) => req('/api/conversations/claim', {
    method: 'POST',
    body: JSON.stringify({ session_id: _getSessionId(), turns }),
  }),
};
