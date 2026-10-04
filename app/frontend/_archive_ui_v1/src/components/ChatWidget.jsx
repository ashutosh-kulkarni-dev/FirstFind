import { useState } from 'react'
import ChatCore from './ChatCore'

/** Floating chat widget available on all pages (SRS FR-1.1). */
export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  return (
    <>
      {open && (
        <div className="chat-dock">
          <div className="chat-dock-head">
            <span>ThriftFind Assistant</span>
            <button className="chip" onClick={() => setOpen(false)}>✕</button>
          </div>
          <ChatCore compact />
        </div>
      )}
      <button className="chat-fab" onClick={() => setOpen(o => !o)} title="Ask the assistant">
        {open ? '✕' : '💬'}
      </button>
    </>
  )
}
