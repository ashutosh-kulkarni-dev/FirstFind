import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme'
import { savedCount, onSavedChange } from '../lib/saved'

const LINKS = [
  { to: '/', label: 'Home' },
  { to: '/explore', label: 'Explore' },
  { to: '/chat', label: 'Assistant' },
]

export default function Navbar() {
  const nav = useNavigate()
  const { dark, toggle } = useTheme()
  const { user, logout: doLogout } = useAuth()
  const [saved, setSaved] = useState(savedCount())

  useEffect(() => onSavedChange(list => setSaved(list.length)), [])

  const logout = () => { doLogout(); nav('/') }

  return (
    <nav className="nav">
      <Link to="/" className="nav-logo">FIRSTFIND</Link>
      <div className="nav-links">
        {LINKS.map(l => (
          <NavLink key={l.to} to={l.to} end={l.end}
            className={({ isActive }) => (isActive ? 'active' : '')}>{l.label}</NavLink>
        ))}
        {user && (
          <NavLink to="/lists" className={({ isActive }) => (isActive ? 'active' : '')}>My Lists</NavLink>
        )}
      </div>
      <div className="nav-right">
        <Link to="/lists" className="nav-chip" title="Your saved lists">♥ SAVED ({saved})</Link>
        <button className="nav-icon-btn" title="Toggle dark mode"
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={toggle}>
          {dark ? '☀' : '☾'}
        </button>
        {user ? (
          <>
            <span className="nav-greet">Hi, {user.name || user.email}</span>
            <button className="btn btn-light btn-pill" style={{ padding: '8px 15px', fontSize: 12 }} onClick={logout}>Log out</button>
          </>
        ) : (
          <Link to="/auth" className="btn btn-light btn-pill" style={{ padding: '8px 15px', fontSize: 12 }}>Log in</Link>
        )}
      </div>
    </nav>
  )
}
