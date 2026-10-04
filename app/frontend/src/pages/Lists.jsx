import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { RequireAuth } from '../auth/RequireAuth'
import StoreCard from '../components/StoreCard'

export default function Lists() {
  return (
    <RequireAuth message="Log in to view and manage your saved lists.">
      <ListsContent />
    </RequireAuth>
  )
}

function ListsContent() {
  const [lists, setLists] = useState(null)      // null = loading
  const [openId, setOpenId] = useState(null)    // expanded list id
  const [detail, setDetail] = useState(null)    // full list with stores
  const [editId, setEditId] = useState(null)
  const [editName, setEditName] = useState('')
  const [editError, setEditError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.lists().then(setLists).catch(() => setLists([]))
  }, [])

  async function expand(id) {
    if (openId === id) { setOpenId(null); setDetail(null); return }
    setOpenId(id); setDetail(null)
    const d = await api.list(id).catch(() => null)
    setDetail(d)
  }

  async function deleteList(id, e) {
    e.stopPropagation()
    await api.deleteList(id).catch(() => {})
    setLists(ls => ls.filter(l => l.id !== id))
    if (openId === id) { setOpenId(null); setDetail(null) }
  }

  async function saveRename(id) {
    const name = editName.trim()
    if (!name) { setEditError('Name cannot be empty.'); return }
    try {
      const updated = await api.updateList(id, { name })
      setLists(ls => ls.map(l => l.id === id ? { ...l, name: updated.name } : l))
      setEditId(null)
    } catch (e) { setEditError(e.message) }
  }

  function openOnMap(lst) {
    if (lst.center_lat != null && lst.center_lng != null) {
      navigate(`/explore?lat=${lst.center_lat}&lng=${lst.center_lng}&radius=${lst.radius_km ?? 2}`)
    }
  }

  if (lists === null) {
    return <div style={{ display: 'grid', placeItems: 'center', minHeight: 300 }}><span className="muted">Loading…</span></div>
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '28px 20px 60px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 6 }}>
        <div className="anton" style={{ fontSize: 34, color: 'var(--ink)', lineHeight: 1 }}>MY LISTS</div>
        <Link to="/explore" style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-blue-2)' }}>+ New list from Explore →</Link>
      </div>
      <p className="muted" style={{ fontSize: 13, marginBottom: 24 }}>
        Named collections of thrift stores you saved from the Explore map.
      </p>

      {lists.length === 0 && (
        <div style={{ padding: '28px 24px', border: '1.5px dashed var(--line)', borderRadius: 14, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
          No lists yet. Go to <Link to="/explore" style={{ fontWeight: 700 }}>Explore</Link>, start a cluster, and hit "Save list".
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {lists.map(lst => (
          <div key={lst.id} className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', cursor: 'pointer' }}
              onClick={() => expand(lst.id)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                {editId === lst.id ? (
                  <div onClick={e => e.stopPropagation()} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input className="input" value={editName} autoFocus
                      onChange={e => setEditName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') saveRename(lst.id); if (e.key === 'Escape') setEditId(null) }}
                      style={{ flex: 1, fontSize: 14 }} />
                    <button className="btn btn-primary" style={{ padding: '6px 12px', fontSize: 12 }} onClick={() => saveRename(lst.id)}>Save</button>
                    <button className="btn btn-light" style={{ padding: '6px 10px', fontSize: 12 }} onClick={() => setEditId(null)}>✕</button>
                  </div>
                ) : (
                  <div className="anton" style={{ fontSize: 17, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {lst.name.toUpperCase()}
                  </div>
                )}
                {editError && editId === lst.id && (
                  <p style={{ fontSize: 11, color: 'var(--sent-neg)', marginTop: 4 }}>{editError}</p>
                )}
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
                  {lst.store_count} store{lst.store_count !== 1 ? 's' : ''}
                  {lst.source_label ? ` · from "${lst.source_label}"` : ''}
                  {' · '}{new Date(lst.created_at).toLocaleDateString()}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <button title="Rename" onClick={e => { e.stopPropagation(); setEditId(lst.id); setEditName(lst.name); setEditError('') }}
                  style={{ border: '1px solid var(--line)', borderRadius: 8, padding: '4px 9px', fontSize: 12, background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>✏</button>
                {detail?.center_lat != null && openId === lst.id && (
                  <button title="Open on map" onClick={e => { e.stopPropagation(); openOnMap(detail) }}
                    style={{ border: '1px solid var(--line)', borderRadius: 8, padding: '4px 9px', fontSize: 12, background: 'transparent', color: 'var(--brand-blue-2)', cursor: 'pointer' }}>◉ Map</button>
                )}
                <button title="Delete list" onClick={e => deleteList(lst.id, e)}
                  style={{ border: '1px solid var(--line)', borderRadius: 8, padding: '4px 9px', fontSize: 12, background: 'transparent', color: 'var(--sent-neg)', cursor: 'pointer' }}>🗑</button>
                <span style={{ fontSize: 16, color: 'var(--muted)', alignSelf: 'center' }}>{openId === lst.id ? '▲' : '▼'}</span>
              </div>
            </div>

            {/* Expanded store grid */}
            {openId === lst.id && (
              <div style={{ borderTop: '1px solid var(--line-2)', padding: '14px 18px 18px' }}>
                {!detail && <p className="muted" style={{ fontSize: 13 }}>Loading stores…</p>}
                {detail && detail.stores.length === 0 && (
                  <p className="muted" style={{ fontSize: 13 }}>No stores found (they may have been removed).</p>
                )}
                {detail && detail.stores.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
                    {detail.stores.map(s => <StoreCard key={s.id} store={s} />)}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
