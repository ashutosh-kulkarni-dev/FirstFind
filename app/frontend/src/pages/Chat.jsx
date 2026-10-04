import ChatCore from '../components/ChatCore'

export default function Chat() {
  return (
    <div className="chat-page">
      <div className="chat-head chat-head-banner">
        <div className="anton" style={{ fontSize: 26, color: '#fff' }}>STYLE ASSISTANT</div>
        <p style={{ fontSize: 13, marginTop: 2, color: 'rgba(255,255,255,.82)' }}>
          One assistant, three brains — search, recommend, and map, in plain language.
        </p>
      </div>
      <ChatCore />
    </div>
  )
}
