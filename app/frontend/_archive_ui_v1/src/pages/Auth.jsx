import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setAuth } from '../api'

export default function Auth() {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const res = mode === 'login'
        ? await api.login(form.email, form.password)
        : await api.register(form.name, form.email, form.password)
      setAuth(res.token, { name: res.name, email: res.email })
      nav('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h2>{mode === 'login' ? 'Welcome back' : 'Join ThriftFind'}</h2>
        <p className="sub">
          {mode === 'login'
            ? 'Log in for personalized recommendations.'
            : 'Create an account — save stores, post reviews, get picks tailored to you.'}
        </p>
        {error && <p className="err">{error}</p>}
        {mode === 'register' && (
          <div className="field">
            <label>Name</label>
            <input value={form.name} onChange={set('name')} required />
          </div>
        )}
        <div className="field">
          <label>Email</label>
          <input type="email" value={form.email} onChange={set('email')} required />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={form.password} onChange={set('password')} minLength={6} required />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={busy}>
          {busy ? <span className="spin" /> : mode === 'login' ? 'Log in' : 'Create account'}
        </button>
        <p style={{ marginTop: 18, fontSize: 14, color: 'var(--text-dim)', textAlign: 'center' }}>
          {mode === 'login' ? "No account? " : 'Already have an account? '}
          <a style={{ color: 'var(--accent)', cursor: 'pointer' }}
             onClick={() => setMode(m => (m === 'login' ? 'register' : 'login'))}>
            {mode === 'login' ? 'Register' : 'Log in'}
          </a>
        </p>
        <p className="synthetic-note">
          Demo login: <b>priya@demo.thriftfind</b> / <b>demo1234</b> (synthetic user with interaction history)
        </p>
      </form>
    </div>
  )
}
