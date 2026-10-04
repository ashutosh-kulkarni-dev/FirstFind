import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import MiniMap from './MiniMap'
import StoreCard from './StoreCard'

const WELCOME = {
  role: 'bot',
  text: "Hey! I'm the ThriftFind assistant — ask me about stores by area, style, or budget, what's open now, or where Bengaluru's thrift zones are.",
  stores: [],
  suggestions: [
    'Show me thrift stores in Koramangala',
    'Vintage stores under ₹500',
    'Which stores are open right now?',
    'Where are the budget thrift zones?',
  ],
}

/** Shared chat logic + message list, used by the full Chat page and the floating widget. */
export default function ChatCore({ compact = false }) {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  async function send(text) {
    const msg = (text ?? input).trim()
    if (!msg || busy) return
    setInput('')
    setMessages(m => [...m, { role: 'user', text: msg }])
    setBusy(true)
    try {
      const res = await api.chat(msg)
      setMessages(m => [...m, {
        role: 'bot', text: res.reply, intent: res.intent,
        stores: res.stores || [], suggestions: res.suggestions || [],
        map: res.map || null, action: res.action || null,
        trip: res.trip || null,
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
      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.text}</div>
            {m.role === 'bot' && m.intent && !compact && (
              <div className="intent-tag">intent · {m.intent.replaceAll('_', ' ')}</div>
            )}
            {m.stores?.length > 0 && (
              <div className="msg-stores">
                {m.stores.slice(0, compact ? 2 : 6).map(s => (
                  <StoreCard key={s.id} store={s} compact />
                ))}
              </div>
            )}
            {m.role === 'bot' && m.map && !compact && (
              <MiniMap
                center={m.map.center}
                radiusKm={m.map.radius_km}
                stores={m.map.stores || []}
                metro={m.map.metro}
              />
            )}
            {m.role === 'bot' && m.action?.type === 'open_zones' && !compact && (
              <button
                className="btn btn-secondary map-action-btn"
                onClick={() => {
                  const p = m.action.params
                  navigate(`/zones?lat=${p.lat}&lng=${p.lng}&radius=${p.radius_km}`)
                }}
              >
                {m.action.label || 'View on full map →'}
              </button>
            )}
          </div>
        ))}
        {busy && (
          <div className="msg bot">
            <div className="bubble typing"><span /><span /><span /></div>
          </div>
        )}
      </div>
      {lastSuggestions.length > 0 && !busy && (
        <div className="chips">
          {lastSuggestions.map(s => (
            <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}
      <div className="chat-input-row">
        <input
          className="chat-input"
          placeholder="Ask about stores, areas, budgets…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
        />
        <button className="btn btn-primary" onClick={() => send()} disabled={busy}>
          {busy ? <span className="spin" /> : 'Send'}
        </button>
      </div>
    </>
  )
}
