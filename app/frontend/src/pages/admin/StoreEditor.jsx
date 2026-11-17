// Side drawer to add or edit a store: every field, the pin on a map, hide /
// unhide, delete (with confirmation), its reviews and its change history.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import PinMap from './PinMap'
import ConfirmDialog from './ConfirmDialog'
import ReviewRow from './ReviewRow'

const TEXT_FIELDS = [
  ['name', 'Name', true], ['area', 'Area', true], ['locality_raw', 'Locality'],
  ['address', 'Address'], ['city', 'City'], ['phone', 'Phone'], ['instagram', 'Instagram handle'],
  ['open_time', 'Opens (HH:MM)'], ['close_time', 'Closes (HH:MM)'], ['timing_note', 'Timing note'],
]

const EMPTY = {
  name: '', area: '', locality_raw: '', address: '', city: 'Bengaluru', phone: '', instagram: '',
  open_time: '', close_time: '', timing_note: '', notes: '', description: '',
  lat: null, lng: null, store_type: 'thrift', tags: [], categories: '', closed_days: [],
  price_min: '', price_max: '', price_estimated: false, is_active: true,
}

function toForm(s) {
  const f = { ...EMPTY }
  Object.keys(EMPTY).forEach(k => { if (s[k] !== undefined && s[k] !== null) f[k] = s[k] })
  f.price_min = s.price_min ?? ''
  f.price_max = s.price_max ?? ''
  f.categories = (s.categories || []).join(', ')   // edited as one comma-separated line
  return f
}

// What the API wants for each form value ('' → null, numbers parsed).
function toApi(key, v) {
  if (key === 'categories') return v.split(',').map(c => c.trim()).filter(Boolean)
  if (key === 'price_min' || key === 'price_max') return v === '' || v === null ? null : Number(v)
  if (key === 'lat' || key === 'lng') return v === '' || v === null ? null : Number(v)
  if (typeof v === 'string') return v.trim() === '' ? null : v.trim()
  return v
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

export default function StoreEditor({ storeId, meta, onClose, onSaved, onDeleted }) {
  const isNew = !storeId
  const [store, setStore] = useState(null)
  const [form, setForm] = useState(isNew ? EMPTY : null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [history, setHistory] = useState([])

  const load = useCallback(() => {
    if (isNew) return
    api.adminStore(storeId)
      .then(s => { setStore(s); setForm(toForm(s)) })
      .catch(e => setError(e.message))
    api.adminAudit({ entity: 'store', entity_id: storeId, limit: 20 })
      .then(r => setHistory(r.entries)).catch(() => {})
  }, [isNew, storeId])
  useEffect(load, [load])

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape' && !confirmDelete) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, confirmDelete])

  const original = useMemo(() => (store ? toForm(store) : EMPTY), [store])
  const changes = useMemo(() => {
    if (!form) return {}
    const out = {}
    Object.keys(EMPTY).forEach(k => {
      const next = toApi(k, form[k])
      const include = isNew
        ? ['name', 'area', 'store_type'].includes(k) || (next !== null && !same(next, toApi(k, EMPTY[k])))
        : !same(next, toApi(k, original[k]))
      if (include) out[k] = next
    })
    return out
  }, [form, original, isNew])
  const dirty = Object.keys(changes).length > 0

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const toggleIn = (k, v) => setForm(f => ({ ...f, [k]: f[k].includes(v) ? f[k].filter(x => x !== v) : [...f[k], v] }))

  const save = async (e) => {
    e?.preventDefault()
    if (!dirty) return
    setSaving(true); setError('')
    try {
      const saved = isNew ? await api.adminCreateStore(changes) : await api.adminUpdateStore(storeId, changes)
      onSaved(saved, isNew ? `Added ${saved.name} (${saved.id})` : `Saved ${saved.name}`)
      if (!isNew) load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleHidden = async () => {
    setSaving(true); setError('')
    try {
      const s = await api.adminUpdateStore(storeId, { is_active: !store.is_active })
      onSaved(s, `${s.name} is now ${s.is_active ? 'visible' : 'hidden'}`)
      load()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }

  const doDelete = async () => {
    setDeleting(true)
    try {
      const r = await api.adminDeleteStore(storeId)
      onDeleted(`Deleted ${store.name}${r.reviews_removed ? ` and ${r.reviews_removed} reviews` : ''}`)
    } catch (err) {
      setError(err.message); setConfirmDelete(false)
    } finally { setDeleting(false) }
  }

  return (
    <div className="admin-drawer-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="admin-drawer" aria-label={isNew ? 'Add store' : 'Edit store'}>
        <div className="admin-drawer-head">
          <div>
            <div className="section-eyebrow">{isNew ? 'New store' : storeId}</div>
            <h2 className="admin-drawer-title">{isNew ? 'Add a store' : (store?.name || 'Loading…')}</h2>
            {store && (
              <div className="muted" style={{ fontSize: 12 }}>
                {store.is_active ? 'Visible' : 'Hidden'} · added via {store.created_via}
                {store.google_status ? ` · Google: ${store.google_status.replace('_', ' ')}` : ''}
                {store.is_active && store.lat != null && <> · <Link to={`/store/${store.id}`} target="_blank">public page ↗</Link></>}
              </div>
            )}
          </div>
          <button className="admin-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {error && <p className="admin-error">{error}</p>}
        {!form && !error && <p className="muted" style={{ padding: 20 }}>Loading…</p>}

        {form && (
          <form className="admin-form" onSubmit={save}>
            <div className="admin-grid">
              {TEXT_FIELDS.map(([k, label, required]) => (
                <label key={k}>
                  <span className="field-label">{label}{required ? ' *' : ''}</span>
                  <input className="input" value={form[k] ?? ''} required={required}
                    onChange={e => set(k, e.target.value)} />
                </label>
              ))}
              <label>
                <span className="field-label">Kind</span>
                <select className="select" value={form.store_type} onChange={e => set('store_type', e.target.value)}>
                  {(meta?.store_types || [{ value: form.store_type, label: form.store_type }]).map(o =>
                    <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <div className="admin-price">
                <label>
                  <span className="field-label">Price from (₹)</span>
                  <input className="input" type="number" min="0" value={form.price_min}
                    onChange={e => set('price_min', e.target.value)} />
                </label>
                <label>
                  <span className="field-label">Price to (₹)</span>
                  <input className="input" type="number" min="0" value={form.price_max}
                    onChange={e => set('price_max', e.target.value)} />
                </label>
              </div>
            </div>

            <label className="admin-check">
              <input type="checkbox" checked={!!form.price_estimated}
                onChange={e => set('price_estimated', e.target.checked)} />
              Prices are an estimate, not the store's own figures
            </label>

            <fieldset className="admin-fieldset">
              <legend className="field-label">Tags</legend>
              <div className="admin-chips">
                {(meta?.tags || []).map(t => (
                  <button type="button" key={t.value} aria-pressed={form.tags.includes(t.value)}
                    className={`admin-chip ${form.tags.includes(t.value) ? 'on' : ''}`}
                    onClick={() => toggleIn('tags', t.value)}>{t.label}</button>
                ))}
              </div>
            </fieldset>

            <fieldset className="admin-fieldset">
              <legend className="field-label">Closed on</legend>
              <div className="admin-chips">
                {(meta?.days || []).map(d => (
                  <button type="button" key={d} aria-pressed={form.closed_days.includes(d)}
                    className={`admin-chip ${form.closed_days.includes(d) ? 'on' : ''}`}
                    onClick={() => toggleIn('closed_days', d)}>{d.slice(0, 3)}</button>
                ))}
              </div>
            </fieldset>

            <label>
              <span className="field-label">Categories (comma separated)</span>
              <input className="input" value={form.categories}
                onChange={e => set('categories', e.target.value)} />
            </label>
            <label>
              <span className="field-label">Description</span>
              <textarea className="textarea" rows={3} value={form.description ?? ''}
                onChange={e => set('description', e.target.value)} />
            </label>
            <label>
              <span className="field-label">Notes</span>
              <textarea className="textarea" rows={2} value={form.notes ?? ''}
                onChange={e => set('notes', e.target.value)} />
            </label>

            <fieldset className="admin-fieldset">
              <legend className="field-label">Map pin</legend>
              <p className="muted admin-hint">
                {form.lat == null ? 'No pin yet — click the map to place one.' : 'Drag the pin to move it.'}
              </p>
              <PinMap lat={form.lat == null || form.lat === '' ? null : Number(form.lat)}
                lng={form.lng == null || form.lng === '' ? null : Number(form.lng)}
                onChange={(lat, lng) => setForm(f => ({ ...f, lat, lng }))} />
              <div className="admin-price" style={{ marginTop: 8 }}>
                <label>
                  <span className="field-label">Latitude</span>
                  <input className="input" type="number" step="any" value={form.lat ?? ''}
                    onChange={e => set('lat', e.target.value === '' ? null : e.target.value)} />
                </label>
                <label>
                  <span className="field-label">Longitude</span>
                  <input className="input" type="number" step="any" value={form.lng ?? ''}
                    onChange={e => set('lng', e.target.value === '' ? null : e.target.value)} />
                </label>
              </div>
              {form.lat != null && (
                <button type="button" className="link-btn" style={{ marginTop: 6 }}
                  onClick={() => setForm(f => ({ ...f, lat: null, lng: null }))}>Remove pin</button>
              )}
            </fieldset>

            <div className="admin-form-actions">
              <button type="submit" className="btn btn-primary" disabled={!dirty || saving}>
                {saving ? 'Saving…' : isNew ? 'Add store' : 'Save changes'}
              </button>
              {!isNew && dirty && (
                <button type="button" className="btn" onClick={() => setForm(toForm(store))}>Discard</button>
              )}
              {!isNew && store && (
                <>
                  <span style={{ flex: 1 }} />
                  <button type="button" className="btn" onClick={toggleHidden} disabled={saving || dirty}
                    title={dirty ? 'Save or discard your edits first' : ''}>
                    {store.is_active ? 'Hide store' : 'Unhide store'}
                  </button>
                  <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(true)}>Delete</button>
                </>
              )}
            </div>
          </form>
        )}

        {store && (
          <section className="admin-sub">
            <h3 className="section-eyebrow">Reviews ({store.reviews.length})</h3>
            {store.reviews.length === 0 && <p className="muted admin-hint">No reviews.</p>}
            {store.reviews.map(r => (
              <ReviewRow key={r.id} review={r} showStore={false}
                onChanged={msg => { onSaved(null, msg); load() }} />
            ))}
          </section>
        )}

        {history.length > 0 && (
          <section className="admin-sub">
            <h3 className="section-eyebrow">History</h3>
            <ul className="admin-history">
              {history.map(h => (
                <li key={h.id}>
                  <span className="muted">{new Date(h.created_at + 'Z').toLocaleString()}</span>{' '}
                  <b>{h.action}</b> by {h.user_email}
                  {h.action === 'update' && h.changes && <span className="muted"> — {Object.keys(h.changes).join(', ')}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>

      {confirmDelete && (
        <ConfirmDialog title={`Delete ${store.name}?`} confirmLabel="Delete permanently" busy={deleting}
          onConfirm={doDelete} onCancel={() => setConfirmDelete(false)}>
          <p>This removes the store, its {store.reviews.length} reviews, and it from everyone's saved lists. It can't be undone.</p>
          <p className="muted">To take it off the site but keep everything, use <b>Hide store</b> instead.</p>
        </ConfirmDialog>
      )}
    </div>
  )
}
