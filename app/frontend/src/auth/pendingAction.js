// Continuity: when a guest triggers a privileged action, we stash a serialisable
// descriptor here, send them to log in, then replay it afterwards so the task they
// started isn't lost. Storage-only + a tiny handler registry — no React, no
// feature knowledge. Each feature (save-list, post-review, …) registers its own
// handler in its own phase, keeping this module a stable, decoupled hub.
const KEY = 'tf_pending_action';
const handlers = new Map(); // type -> async (payload) => void

// action: { type: string, payload: object }
export function setPendingAction(action) {
  try { sessionStorage.setItem(KEY, JSON.stringify(action)); } catch { /* quota/serialisation */ }
}

export function peekPendingAction() {
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch { return null; }
}

export function clearPendingAction() {
  sessionStorage.removeItem(KEY);
}

// Feature modules call this once (e.g. in a top-level effect) to register how their
// action type is replayed after login.
export function registerActionHandler(type, handler) {
  handlers.set(type, handler);
  return () => handlers.delete(type);
}

// Run and clear the pending action, if any and if a handler is registered.
// Returns true if something was run. Safe to call on every successful login.
export async function resumePendingAction() {
  const action = peekPendingAction();
  if (!action) return false;
  const handler = handlers.get(action.type);
  if (!handler) return false;           // handler not registered yet — leave it queued
  clearPendingAction();
  try { await handler(action.payload); } catch { /* surfaced by the handler itself */ }
  return true;
}
