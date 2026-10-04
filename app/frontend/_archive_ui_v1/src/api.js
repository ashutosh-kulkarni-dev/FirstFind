// Thin API client. Token is kept in memory + sessionStorage for dev convenience.
// In dev, API_BASE is '' so requests are relative and hit the Vite proxy
// (/api -> localhost:8000). In production (Vercel), set VITE_API_BASE to the
// deployed backend URL, e.g. https://thriftfind-api.up.railway.app
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

let _token = sessionStorage.getItem('tf_token') || null;
let _user = JSON.parse(sessionStorage.getItem('tf_user') || 'null');

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

export function setAuth(token, user) {
  _token = token; _user = user;
  if (token) {
    sessionStorage.setItem('tf_token', token);
    sessionStorage.setItem('tf_user', JSON.stringify(user));
  } else {
    sessionStorage.removeItem('tf_token');
    sessionStorage.removeItem('tf_user');
  }
}
export function getUser() { return _user; }

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
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
  stores: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
    return req(`/api/stores?${qs}`);
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
  findCluster: ({ lat, lng, radius_km, min_shops, max_shops }) => {
    const qs = new URLSearchParams({ lat, lng, radius_km, ...(min_shops != null ? { min_shops } : {}), ...(max_shops != null ? { max_shops } : {}) })
    return req(`/api/clusters/find?${qs}`)
  },
  splitCluster: ({ lat, lng, radius_km, max_shops }) => {
    const qs = new URLSearchParams({ lat, lng, radius_km, ...(max_shops != null ? { max_shops } : {}) })
    return req(`/api/clusters/split?${qs}`)
  },
  areaCoords: () => req('/api/stores/areas/coords'),
  metroStations: () => req('/api/metro/stations'),
  metroNearest: (lat, lng) => req(`/api/metro/nearest?lat=${lat}&lng=${lng}`),
  recommendations: () => req('/api/recommendations'),
  chat: (message) => req('/api/chat', { method: 'POST', body: JSON.stringify({ message, session_id: _getSessionId() }) }),
};
