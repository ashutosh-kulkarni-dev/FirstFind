import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme'
import { savedCount, onSavedChange } from '../lib/saved'
import StoreCard from '../components/StoreCard'

const WORD = 'FIRSTFIND'.split('')
const TICKER = ['VINTAGE', 'STREET', 'DESIGNER', 'RETRO']

export default function Landing() {
  const { dark, toggle } = useTheme()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [saved, setSaved] = useState(savedCount())
  const [featured, setFeatured] = useState([])
  const [personalized, setPersonalized] = useState(false)
  const [stats, setStats] = useState(null)
  const savedRef = useRef(null)

  // Triggers the exit animation on <main class="lp"> then navigates — only fires from this page.
  const exitTo = (dest) => (e) => {
    e.preventDefault()
    document.querySelector('.lp').classList.add('lp-exit')
    setTimeout(() => navigate(dest), 260)
  }

  // Re-fetch recommendations whenever auth changes so a fresh login immediately
  // shows personalised picks (and a logout reverts to top-rated).
  useEffect(() => {
    api.recommendations()
      .then(r => { setFeatured((r.stores || []).slice(0, 6)); setPersonalized(!!r.personalized) })
      .catch(() => { })
  }, [user])

  useEffect(() => {
    const off = onSavedChange(list => setSaved(list.length))
    Promise.all([api.stores(), api.areas(), api.zones()])
      .then(([s, a, z]) => setStats({ stores: s.count ?? null, areas: a.length ?? null, zones: z.length ?? null }))
      .catch(() => { })
    return off
  }, [])

  // SAVED-chip pulse (mockup micro-interaction) then exits with animation.
  const pulseSaved = (e) => {
    const el = savedRef.current
    if (el) { el.style.animation = 'none'; void el.offsetWidth; el.style.animation = 'ffPulse .6s ease' }
    exitTo('/lists')(e)
  }

  return (
    <main className="lp">
      {/* ===== HERO ===== */}
      <section className="lp-hero">
        <nav className="lp-nav">
          <Link to="/" className="lp-logo">FIRSTFIND</Link>
          <div className="lp-nav-links">
            <Link to="/">HOME</Link>
            <a href="/explore" onClick={exitTo('/explore')}>EXPLORE</a>
            <a href="/chat" onClick={exitTo('/chat')}>ASSISTANT</a>
          </div>
          <div className="lp-nav-right">
            <a href="/lists" ref={savedRef} className="lp-chip" onClick={pulseSaved}>♥ SAVED ({saved})</a>
            <button className="lp-icon" onClick={toggle} title="Toggle dark mode"
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>{dark ? '☀' : '☾'}</button>
            {user
              ? <button className="lp-cta-sm" onClick={logout}>LOG OUT</button>
              : <a href="/auth" className="lp-cta-sm" onClick={exitTo('/auth')}>LOG IN</a>}
            <a href="/explore" className="lp-cta-sm lp-open" onClick={exitTo('/explore')}>OPEN APP</a>
          </div>
        </nav>

        <div className="lp-hero-grid">
          <div className="lp-hero-left">
            <h1 className="lp-word">
              {WORD.map((ch, i) => (
                <span key={i} style={{ animationDelay: `${1 + i * 0.06}s` }}>{ch}</span>
              ))}
            </h1>

            <div className="lp-hero-row">
              <div className="lp-hero-copy">
                <p className="lp-tag">
                  Discover Bengaluru's best thrift and second-hand stores, guided by an AI assistant
                  that learns your style. Real stores, real reviews, real finds.
                </p>
                <a href="/explore" className="lp-explore-btn" onClick={exitTo('/explore')}>
                  EXPLORE STORES <span className="lp-explore-arrow">↗</span>
                </a>
              </div>
            </div>
          </div>

          <aside className="lp-hero-right">
            {TICKER.map((w, i) => (
              <div key={w} className={`lp-ticker-row${w === 'STREET' ? ' on' : ''}`}
                style={{ animationDelay: `${1.4 + i * 0.1}s` }}>{w}</div>
            ))}
            <img className="lp-ticker-img" alt="Streetwear fashion"
              src="https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=500&q=85" />
          </aside>
        </div>
      </section>

      {/* ===== DISCOVER ===== */}
      <section className="lp-discover container">
        <div className="lp-watermark anton">START EXPLORING</div>
        <h2 className="anton lp-h2">DISCOVER THRIFT STORES THAT DEFINE YOUR STYLE</h2>
      </section>

      {/* ===== OUR FEATURES ===== */}
      <section className="lp-trust">
        <div className="container">
          <h2 className="anton" style={{ color: '#fff', fontSize: 'clamp(26px,3.4vw,36px)' }}>OUR FEATURES</h2>
          <div className="lp-stats">

            <a href="/explore" onClick={exitTo('/explore')} style={{ textDecoration: 'none', display: 'block' }}>
              <article className="lp-stat-img" style={{ cursor: 'pointer' }}>
                <img alt="Bengaluru thrifter" src="https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=400&q=85" />
                <div className="lp-stat-cap">
                  <span style={{ display: 'block', fontWeight: 700, color: '#fff', fontSize: 13, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.5px' }}>Explore</span>
                  Explore stores around you on our live map
                </div>
              </article>
            </a>

            <article className="lp-stat-num">
              <small>Stores in<br />Bengaluru</small>
              <div className="anton" style={{ fontSize: 46, lineHeight: 1, marginTop: 10, color: 'var(--ink)' }}>
                {stats?.stores ?? '—'}
              </div>
              <div style={{ marginTop: 6, color: 'var(--ink)', fontSize: 11.5, lineHeight: 1.35 }}>
                verified thrift stores, updated as new ones join.
              </div>
            </article>

            <a href="/chat" onClick={exitTo('/chat')} style={{ textDecoration: 'none', display: 'block' }}>
              <article className="lp-stat-img" style={{ cursor: 'pointer' }}>
                <img alt="Thrift shopper" src="https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=400&q=85" />
                <div className="lp-stat-cap">
                  <span style={{ display: 'block', fontWeight: 700, color: '#fff', fontSize: 13, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.5px' }}>Assistant</span>
                  Chat with our AI assistant — let us plan your perfect thrift trip
                </div>
              </article>
            </a>

          </div>
        </div>
      </section>

      {/* ===== TOP RATED / PICKED FOR YOU (real data) ===== */}
      {featured.length > 0 && (
        <section className="container" style={{ padding: '40px 24px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <h2 className="anton lp-h2" style={{ textAlign: 'left', margin: 0 }}>
              {personalized ? 'PICKED FOR YOU' : 'TOP-RATED RIGHT NOW'}
            </h2>
            {personalized && (
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--brand-blue-2)', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                ✦ Personalised
              </span>
            )}
          </div>
          <p className="muted" style={{ marginTop: 4, marginBottom: 18, fontSize: 13 }}>
            {personalized
              ? `Based on your saves and browsing, ${user?.name?.split(' ')[0] || 'here'} — stores matched to your taste.`
              : 'Ranked by AI experience score — star ratings blended with review sentiment. Log in for picks tailored to you.'}
          </p>
          <div className="lp-grid">
            {featured.map(s => <StoreCard key={s.id} store={s} />)}
          </div>
        </section>
      )}

      <footer className="lp-footer">
        <div className="container">
          FIRSTFIND · real store data from field research ·
        </div>
      </footer>
    </main>
  )
}
