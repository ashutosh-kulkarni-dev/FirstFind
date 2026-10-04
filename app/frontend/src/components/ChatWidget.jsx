import { useState } from 'react'
import ChatCore from './ChatCore'

// Floating assistant. FAB toggles a compact docked ChatCore.
export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  return (
    <>
      {open && (
        <div className="chat-dock">
          <div className="chat-dock-head">
            <span className="anton" style={{ fontSize: 16 }}>ASSISTANT</span>
            <button className="chat-dock-x" onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="chat-dock-body">
            <ChatCore compact />
          </div>
        </div>
      )}
      <button className="chat-fab" onClick={() => setOpen(o => !o)} title="Style assistant"
        aria-label={open ? 'Close style assistant' : 'Open style assistant'} aria-expanded={open}>
        {open ? '✕' : '💬'}
      </button>
    </>
  )
}
