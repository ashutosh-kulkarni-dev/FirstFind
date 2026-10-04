import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import MiniMap from './MiniMap'
import StoreCard from './StoreCard'

const WELCOME = {
  role: 'bot',
  text: "Hi — I'm your FIRSTFIND style assistant. Tell me what you're after by area, style, or budget, ask what's open now, or where Bengaluru's thrift zones are.",
  stores: [],
  suggestions: [
    'Best stores in Indiranagar',
    'Vintage under ₹500',
    "What's open now?",
    'Where are the budget thrift zones?',
  ],
}

/** Shared chat logic + thread, used by the full Chat page and the floating widget. */
export default function ChatCore({ compact = false }) {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [conversations, setConversations] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const scrollRef = useRef(null)
  const claimedRef = useRef(false)   // guard: only claim once per session
  const messagesRef = useRef(messages)   // always-current messages for the claim effect
  const originRef = useRef(null)     // cached browser geolocation {lat,lng} or null
  const navigate = useNavigate()
  const { user } = useAuth()

  messagesRef.current = messages

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  // When a guest logs in mid-chat, claim their transcript once (idempotent on server).
  // Reads from a ref so we always send the latest thread, not a render-time snapshot.
  useEffect(() => {
    if (!user || claimedRef.current) return
    const guestTurns = messagesRef.current
      .filter(m => m.role !== 'bot' || m.text !== WELCOME.text)  // skip the static welcome
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', text: m.text, meta: m.meta ?? null }))
    if (guestTurns.length > 0) {
      claimedRef.current = true
      api.claimChat(guestTurns).catch(() => {})
    }
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  function loadHistory() {
    setHistoryLoading(true)
    api.conversations()
      .then(setConversations)
      .catch(() => setConversations([]))
      .finally(() => setHistoryLoading(false))
  }

  function openHistory() {
    setHistoryOpen(true)
    loadHistory()
  }

  async function openConversation(id) {
    setHistoryOpen(false)
    const data = await api.conversation(id).catch(() => null)
    if (!data) return

    const parseMeta = (raw) => {
      if (!raw) return null
      try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return null }
    }
    const parsed = data.messages.map(m => ({
      role: m.role === 'user' ? 'user' : 'bot',
      text: m.text,
      meta: parseMeta(m.meta),
    }))

    // Re-inflate real store cards: the backend persists store_ids per message
    // (not full records), so fetch the current store list once and map by id.
    const ids = new Set()
    parsed.forEach(m => (m.meta?.store_ids || []).forEach(sid => ids.add(sid)))
    let byId = {}
    if (ids.size > 0) {
      const all = await api.stores().then(r => r.stores || []).catch(() => [])
      byId = Object.fromEntries(all.map(s => [s.id, s]))
    }

    const restored = parsed.map(m => ({
      role: m.role,
      text: m.text,
      stores: (m.meta?.store_ids || []).map(sid => byId[sid]).filter(Boolean),
      suggestions: m.meta?.suggestions || [],
      intent: m.meta?.intent || null,
    }))
    setMessages([WELCOME, ...restored])
  }

  async function deleteConversation(id, e) {
    e.stopPropagation()
    await api.deleteConversation(id).catch(() => {})
    setConversations(cs => cs.filter(c => c.id !== id))
  }

  const NEAR_ME_RE = /\b(near me|close to me|around me|nearby|my location|current location|around here|near here)\b/i

  async function send(text) {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput('')
    setMessages(m => [...m, { role: 'user', text: msg }])
    setBusy(true)

    // Request geolocation once if "near me" phrasing detected and not yet cached.
    // Non-blocking: if denied or unavailable, origin stays null and the backend replies honestly.
    let origin = originRef.current
    if (NEAR_ME_RE.test(msg) && origin === null && navigator.geolocation) {
      origin = await new Promise(resolve => {
        navigator.geolocation.getCurrentPosition(
          pos => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
          () => resolve(null),
          { timeout: 5000 }
        )
      })
      originRef.current = origin ?? false  // false = permission denied/unavailable, skip future prompts
    }

    try {
      const res = await api.chat(msg, origin && origin !== false ? origin : null)
      setMessages(m => [...m, {
        role: 'bot', text: res.reply, intent: res.intent,
        stores: res.stores || [], suggestions: res.suggestions || [],
        map: res.map || null, action: res.action || null, trip: res.trip || null,
      }])
    } catch (e) {
      setMessages(m => [...m, {
        role: 'bot', text: `Hmm, I couldn't reach the server (${e.message}). Is the backend running on port 8000?`,
        stores: [], suggestions: [],
      }])
    } finally {
      setBusy(false)
    }
  }

  const lastSuggestions = messages[messages.length - 1]?.suggestions || []

  return (
    <>
      {/* History panel — full chat page only, not the compact widget */}
      {!compact && historyOpen && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 200,
          display: 'flex', justifyContent: 'flex-end',
          background: 'rgba(0,0,0,.35)',
        }} onClick={() => setHistoryOpen(false)}>
          <div style={{
            width: 'min(340px, 92vw)', height: '100%', background: 'var(--surface)',
            boxShadow: '-4px 0 24px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: '18px 18px 12px', borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className="anton" style={{ flex: 1, fontSize: 18, color: 'var(--ink)' }}>CHAT HISTORY</span>
              <button onClick={() => setHistoryOpen(false)}
                style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 18, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
              {historyLoading && (
                <p className="muted" style={{ padding: '14px 18px', fontSize: 13 }}>Loading…</p>
              )}
              {!historyLoading && conversations.length === 0 && (
                <p className="muted" style={{ padding: '14px 18px', fontSize: 13 }}>No saved conversations yet.</p>
              )}
              {conversations.map(c => (
                <div key={c.id} onClick={() => openConversation(c.id)}
                  style={{ padding: '11px 18px', cursor: 'pointer', borderBottom: '1px solid var(--line-2)', display: 'flex', alignItems: 'flex-start', gap: 8 }}
                  onMouseOver={e => e.currentTarget.style.background = 'var(--surface-2)'}
                  onMouseOut={e => e.currentTarget.style.background = 'transparent'}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {c.title || 'Conversation'}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
                      {c.message_count} messages · {new Date(c.updated_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button onClick={(e) => deleteConversation(c.id, e)}
                    title="Delete"
                    style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 14, cursor: 'pointer', flexShrink: 0, padding: '2px 4px' }}>🗑</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="chat-scroll" ref={scrollRef}>
        {/* History button — shown at the top of the thread for logged-in users */}
        {!compact && user && (
          <div style={{ textAlign: 'center', padding: '8px 0 4px' }}>
            <button onClick={openHistory}
              style={{ border: '1px solid var(--line)', borderRadius: 20, padding: '5px 14px', fontSize: 12, fontWeight: 600, color: 'var(--muted)', background: 'var(--surface)', cursor: 'pointer' }}>
              📋 View past conversations
            </button>
          </div>
        )}

        {messages.map((m, i) => {
          const mine = m.role === 'user'
          return (
            <div key={i} className="msg" style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
              <div className={`bubble ${mine ? 'mine' : ''}`}>{m.text}</div>

              {m.stores?.length > 0 && (
                <div className="msg-stores">
                  {m.stores.slice(0, compact ? 2 : 6).map(s => <StoreCard key={s.id} store={s} />)}
                </div>
              )}

              {!compact && m.map && (
                <div style={{ width: '78%' }}>
                  <MiniMap center={m.map.center} radiusKm={m.map.radius_km} stores={m.map.stores || []} metro={m.map.metro} />
                </div>
              )}

              {!compact && m.action?.type === 'open_zones' && (
                <button className="chat-map-btn" onClick={() => {
                  const p = m.action.params
                  navigate(`/explore?lat=${p.lat}&lng=${p.lng}&radius=${p.radius_km}`)
                }}>
                  <span className="chat-map-ic">◉</span> {m.action.label || 'View these on the full map →'}
                </button>
              )}

              {!compact && m.intent && (
                <div className="intent-tag">intent · {m.intent.replaceAll('_', ' ')}</div>
              )}
            </div>
          )
        })}
        {busy && (
          <div className="msg" style={{ alignItems: 'flex-start' }}>
            <div className="bubble typing"><span /><span /><span /></div>
          </div>
        )}
      </div>

      {lastSuggestions.length > 0 && !busy && (
        <div className="chips">
          {lastSuggestions.map(s => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
        </div>
      )}

      <form className="chat-input-row" onSubmit={e => { e.preventDefault(); send() }}>
        <input className="chat-input" placeholder="Ask about stores, areas, budgets…"
          value={input} onChange={e => setInput(e.target.value)} />
        <button type="submit" className="chat-send" disabled={busy}>↑</button>
      </form>
    </>
  )
}
