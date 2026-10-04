import { useNavigate } from 'react-router-dom'

export default function ChatFab() {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/chat')}
      style={{
        position: 'absolute',
        left: 16,
        bottom: 16,
        zIndex: 600,
        width: 44,
        height: 44,
        border: 0,
        borderRadius: '50%',
        background: 'var(--nav)',
        color: '#fff',
        fontSize: 20,
        boxShadow: 'var(--shadow-md)',
        cursor: 'pointer',
      }}
    >
      💬
    </button>
  )
}
