import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'

// Client ID is baked in at Vercel build time. Empty string = button hidden.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

export default function Auth() {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const [params] = useSearchParams()
  const { login } = useAuth()
  const gBtnRef = useRef(null)

  // Where to land after auth — set by the gating helper (?next=/lists etc.).
  const next = params.get('next') || '/'

  // Load Google Identity Services and render their button when a client id is
  // configured. Runs only once; the ref keeps the DOM node stable across re-renders.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !gBtnRef.current) return
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async ({ credential }) => {
          setError(''); setBusy(true)
          try {
            const res = await api.google(credential)
            login(res.token, res)
            nav(next)
          } catch (err) {
            setError(err.message)
          } finally {
            setBusy(false)
          }
        },
      })
      window.google?.accounts.id.renderButton(gBtnRef.current, {
        theme: 'outline', size: 'large', width: 360, text: 'continue_with',
      })
    }
    document.head.appendChild(script)
    return () => { document.head.removeChild(script) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const res = mode === 'login'
        ? await api.login(form.email, form.password)
        : await api.register(form.name, form.email, form.password)
      login(res.token, res)   // updates auth state + replays any pending action
      nav(next)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--bg)' }}>
      <form className="card fade-up" style={{ width: 'min(420px, 100%)', padding: 30 }} onSubmit={submit}>
        <div className="anton" style={{ fontSize: 30, color: 'var(--ink)', lineHeight: 1 }}>
          {mode === 'login' ? 'WELCOME BACK' : 'JOIN FIRSTFIND'}
        </div>
        <p className="muted" style={{ fontSize: 13, marginTop: 8, lineHeight: 1.5 }}>
          {mode === 'login'
            ? 'Log in for personalized recommendations, saved stores and reviews.'
            : 'Create an account — save stores, post reviews, get picks tailored to you.'}
        </p>

        {error && (
          <p style={{ marginTop: 14, padding: '9px 12px', borderRadius: 9, background: '#ffe4e6', color: 'var(--sent-neg)', fontSize: 12.5, fontWeight: 600 }}>{error}</p>
        )}

        {/* Google button — only rendered when VITE_GOOGLE_CLIENT_ID is set */}
        {GOOGLE_CLIENT_ID && (
          <>
            <div ref={gBtnRef} style={{ marginTop: 20, display: 'flex', justifyContent: 'center' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '16px 0 4px' }}>
              <span style={{ flex: 1, height: 1, background: 'var(--line)' }} />
              <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>OR</span>
              <span style={{ flex: 1, height: 1, background: 'var(--line)' }} />
            </div>
          </>
        )}

        {mode === 'register' && (
          <label style={{ display: 'block', marginTop: 16 }}>
            <span className="field-label">Name</span>
            <input className="input" value={form.name} onChange={set('name')} required />
          </label>
        )}
        <label style={{ display: 'block', marginTop: 14 }}>
          <span className="field-label">Email</span>
          <input className="input" type="email" value={form.email} onChange={set('email')} required />
        </label>
        <label style={{ display: 'block', marginTop: 14 }}>
          <span className="field-label">Password</span>
          <input className="input" type="password" value={form.password} onChange={set('password')} minLength={6} required />
        </label>

        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 20 }} disabled={busy}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
        </button>

        <p style={{ marginTop: 18, fontSize: 13, color: 'var(--muted)', textAlign: 'center' }}>
          {mode === 'login' ? 'No account? ' : 'Already have an account? '}
          <button type="button"
             style={{ border: 0, background: 'none', padding: 0, color: 'var(--brand-blue)', cursor: 'pointer', fontWeight: 700 }}
             onClick={() => { setError(''); setMode(m => (m === 'login' ? 'register' : 'login')) }}>
            {mode === 'login' ? 'Register' : 'Log in'}
          </button>
        </p>
      </form>
    </div>
  )
}
