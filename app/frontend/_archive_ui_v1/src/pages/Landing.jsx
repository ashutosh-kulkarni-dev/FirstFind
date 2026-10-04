import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Hero3D from '../components/Hero3D'
import StoreCard from '../components/StoreCard'
import { api } from '../api'

const FEATURES = [
  { icon: '💬', title: 'Conversational discovery', to: '/chat' },
  { icon: '🗺️', title: 'Live thrift map', text: 'Stores in the city on one map', to: '/explore' },
  { icon: '🧠', title: 'AI-scored reviews', text: 'Sentiment analysis reads every review and blends it with star ratings into one experience score you can actually trust.', to: '/explore' },
  { icon: '📍', title: 'Thrift zones', text: 'Clustering groups the city into Budget, Premium, Mixed and Hidden Gem zones — plan a whole haul day, not one stop.', to: '/zones' },
]

export default function Landing() {
  const [featured, setFeatured] = useState([])
  const [stats, setStats] = useState({ stores: '48', zones: '4', areas: '—' })

  useEffect(() => {
    api.recommendations().then(r => setFeatured(r.stores.slice(0, 6))).catch(() => { })
    Promise.all([api.stores(), api.areas(), api.zones()])
      .then(([s, a, z]) => setStats({ stores: s.count, areas: a.length, zones: z.length }))
      .catch(() => { })
  }, [])

  return (
    <>
      <section className="hero">
        <Hero3D />
        <div className="hero-content">
          <span className="hero-eyebrow">● Bengaluru · AI-powered thrift discovery</span>
          <h1>Thrift smarter.<br /><span className="grad">Find the good stuff first.</span></h1>
          <p className="sub">
            Every thrift store in the city — mapped, scored by real community sentiment,
            and searchable by simply asking. Sustainable fashion without the treasure-hunt friction.
          </p>
          <div className="hero-cta">
            <Link to="/chat" className="btn btn-primary">Ask the assistant →</Link>
            <Link to="/explore" className="btn">Explore the map</Link>
          </div>
          <div className="hero-stats">
            <div className="hero-stat"><div className="num">{stats.stores}</div><div className="lbl">verified stores</div></div>
            <div className="hero-stat"><div className="num">{stats.areas}</div><div className="lbl">neighbourhoods</div></div>
            <div className="hero-stat"><div className="num">{stats.zones}</div><div className="lbl">AI thrift zones</div></div>
            <div className="hero-stat"><div className="num">3</div><div className="lbl">ML modules</div></div>
          </div>
        </div>
      </section>

      <section className="section container">
        <h2 className="section-title">One assistant, two  brains</h2>
        <p className="section-sub">Everything on ThriftFind exists to make one conversation smarter.</p>
        <div className="grid grid-3">
          {FEATURES.map(f => (
            <Link key={f.title} to={f.to} className="card" style={{ display: 'block' }}>
              <div className="feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p style={{ color: 'var(--text-dim)', fontSize: 14, marginTop: 8, lineHeight: 1.6 }}>{f.text}</p>
            </Link>
          ))}
        </div>
      </section>

      {featured.length > 0 && (
        <section className="section container">
          <h2 className="section-title">Top-rated right now</h2>
          <p className="section-sub">Ranked by AI experience score — star ratings blended with review sentiment.</p>
          <div className="grid grid-3">
            {featured.map(s => <StoreCard key={s.id} store={s} />)}
          </div>
        </section>
      )}

      <footer className="footer">
        <div className="container">
          ThriftFind MVP · real store data from field research ·
        </div>
      </footer>
    </>
  )
}
