import { del, post, req } from './client'

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

export const chatApi = {
  chat: (message, origin = null) =>
    post('/api/chat', { message, session_id: _getSessionId(), ...(origin ? { origin } : {}) }),
  conversations: () => req('/api/conversations'),
  conversation: (id) => req(`/api/conversations/${id}`),
  deleteConversation: (id) => del(`/api/conversations/${id}`),
  claimChat: (turns) => post('/api/conversations/claim', { session_id: _getSessionId(), turns }),
}
