// Lightweight client-side "saved stores" tracker. The backend has POST /save
// (fire-and-forget, auth-gated) but no list endpoint, so we mirror saved ids
// locally to drive the navbar counter and the store Save button state.
const KEY = 'ff_saved'
const listeners = new Set()

export function getSaved() {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] }
}
export function isSaved(id) { return getSaved().includes(id) }
export function savedCount() { return getSaved().length }

export function toggleSaved(id) {
  const cur = getSaved()
  const next = cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id]
  localStorage.setItem(KEY, JSON.stringify(next))
  listeners.forEach(fn => fn(next))
  return next.includes(id)
}

export function onSavedChange(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
