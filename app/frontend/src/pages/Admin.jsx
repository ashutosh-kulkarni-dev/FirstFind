// /admin — store and review management for admin accounts. The server enforces
// access on every /api/admin call; this page only hides itself from everyone else.
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import StoresTab from './admin/StoresTab'
import ReviewsTab from './admin/ReviewsTab'
import AttentionTab from './admin/AttentionTab'
import ChangeLog from './admin/ChangeLog'
import StoreEditor from './admin/StoreEditor'

const TABS = [
  { key: 'stores', label: 'Stores' },
  { key: 'attention', label: 'Needs attention' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'log', label: 'Change log' },
]

export default function Admin() {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user?.is_admin) {
    return (
      <div className="admin-denied">
        <div className="card" style={{ padding: 28, textAlign: 'center', maxWidth: 380 }}>
          <p className="muted" style={{ fontSize: 14, marginBottom: 16 }}>
            {user ? 'This page is for admin accounts.' : 'Log in with an admin account to continue.'}
          </p>
          <Link to={user ? '/explore' : '/auth?next=%2Fadmin'} className="btn btn-primary">
            {user ? 'Back to Explore' : 'Log in'}
          </Link>
        </div>
      </div>
    )
  }
  return <AdminPage />
}

function AdminPage() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.some(t => t.key === params.get('tab')) ? params.get('tab') : 'stores'
  const editing = params.get('store')            // a store id, "new", or null
  const [meta, setMeta] = useState(null)
  const [stats, setStats] = useState(null)
  const [version, setVersion] = useState(0)      // bumped after every change → lists reload
  const [toast, setToast] = useState('')
  const [exporting, setExporting] = useState(false)

  useEffect(() => { api.adminMeta().then(setMeta).catch(() => {}) }, [])
  useEffect(() => { api.adminStats().then(setStats).catch(() => {}) }, [version])
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 3200)
    return () => clearTimeout(t)
  }, [toast])

  const setParam = useCallback((key, value) => {
    setParams(prev => {
      const next = new URLSearchParams(prev)
      if (value) next.set(key, value); else next.delete(key)
      return next
    })
  }, [setParams])

  const changed = useCallback((message) => {
    setVersion(v => v + 1)
    if (message) setToast(message)
  }, [])

  const exportCsv = async () => {
    setExporting(true)
    try {
      const blob = await api.adminExportStores()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `firstfind-stores-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setToast(e.message)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="admin">
      <header className="admin-head">
        <div>
          <div className="section-eyebrow">Admin</div>
          <h1 className="anton admin-title">STORES &amp; REVIEWS</h1>
          {stats && (
            <div className="admin-stats muted">
              {stats.stores} stores · {stats.hidden_stores} hidden · {stats.no_pin} without a pin ·{' '}
              {stats.reviews} reviews · {stats.hidden_reviews} hidden
            </div>
          )}
        </div>
        <div className="admin-actions">
          <button className="btn" onClick={exportCsv} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <button className="btn btn-primary" onClick={() => setParam('store', 'new')}>+ Add store</button>
        </div>
      </header>

      <nav className="admin-tabs" role="tablist">
        {TABS.map(t => (
          <button key={t.key} role="tab" aria-selected={tab === t.key}
            className={tab === t.key ? 'active' : ''} onClick={() => setParam('tab', t.key === 'stores' ? '' : t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="admin-body">
        {tab === 'stores' && <StoresTab version={version} onOpen={id => setParam('store', id)} onChanged={changed} />}
        {tab === 'attention' && <AttentionTab version={version} onOpen={id => setParam('store', id)} />}
        {tab === 'reviews' && <ReviewsTab version={version} onChanged={changed} />}
        {tab === 'log' && <ChangeLog version={version} onOpen={id => setParam('store', id)} />}
      </main>

      {editing && (
        <StoreEditor
          key={editing}
          storeId={editing === 'new' ? null : editing}
          meta={meta}
          onClose={() => setParam('store', '')}
          onSaved={(store, message) => {
            changed(message)
            if (editing === 'new' && store) setParam('store', store.id)
          }}
          onDeleted={(message) => { changed(message); setParam('store', '') }}
        />
      )}

      {toast && <div className="admin-toast" role="status">{toast}</div>}
    </div>
  )
}
