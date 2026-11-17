import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

const STATUS = [
  { value: 'all', label: 'All' },
  { value: 'visible', label: 'Visible' },
  { value: 'hidden', label: 'Hidden' },
]

export default function StoresTab({ version, onOpen, onChanged }) {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [stores, setStores] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)   // id of the store being hidden/unhidden

  useEffect(() => {
    let cancelled = false
    setError('')
    api.adminStores({ status })
      .then(res => { if (!cancelled) setStores(res.stores) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [status, version])

  // Filter locally: the full list is ~550 rows, so typing never waits on the network.
  const shown = useMemo(() => {
    if (!stores) return []
    const needle = q.trim().toLowerCase()
    if (!needle) return stores
    return stores.filter(s => [s.id, s.name, s.area, s.locality_raw]
      .some(v => (v || '').toLowerCase().includes(needle)))
  }, [stores, q])

  const toggleHidden = async (s) => {
    setBusy(s.id)
    try {
      await api.adminUpdateStore(s.id, { is_active: !s.is_active })
      onChanged(`${s.name} is now ${s.is_active ? 'hidden' : 'visible'}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section>
      <div className="admin-toolbar">
        <input className="input" style={{ maxWidth: 320 }} placeholder="Search name, id or area"
          value={q} onChange={e => setQ(e.target.value)} aria-label="Search stores" />
        <div className="admin-seg" role="group" aria-label="Filter by visibility">
          {STATUS.map(o => (
            <button key={o.value} className={status === o.value ? 'active' : ''}
              onClick={() => setStatus(o.value)}>{o.label}</button>
          ))}
        </div>
        {stores && <span className="muted" style={{ fontSize: 12 }}>{shown.length} of {stores.length}</span>}
      </div>
      {error && <p className="admin-error">{error}</p>}
      {!stores && !error && <p className="muted">Loading stores…</p>}
      {stores && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>ID</th><th>Name</th><th>Area</th><th>Kind</th><th>Pin</th><th>Source</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {shown.map(s => (
                <tr key={s.id} className={s.is_active ? '' : 'is-hidden'}>
                  <td className="mono">{s.id}</td>
                  <td><button className="link-btn" onClick={() => onOpen(s.id)}>{s.name}</button></td>
                  <td>{s.area}</td>
                  <td>{s.store_type}</td>
                  <td>{s.lat == null ? <span className="admin-flag">none</span> : (s.geocode_precision || 'set')}</td>
                  <td>{s.created_via}{s.admin_edited_at ? ' · edited' : ''}</td>
                  <td>
                    {!s.is_active ? <span className="admin-flag">Hidden</span>
                      : s.lat == null ? <span className="muted" title="Stores without a pin are not shown on the site">Not shown</span>
                        : 'Visible'}
                  </td>
                  <td className="admin-row-actions">
                    <button className="pill-btn" onClick={() => onOpen(s.id)}>Edit</button>
                    <button className="pill-btn" disabled={busy === s.id} onClick={() => toggleHidden(s)}>
                      {s.is_active ? 'Hide' : 'Unhide'}
                    </button>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={8} className="muted">No stores match.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
