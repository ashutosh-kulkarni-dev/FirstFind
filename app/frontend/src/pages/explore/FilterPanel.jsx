// Search box, area / store kind / tag pickers and the "open now" toggle, plus
// the result count. `kinds` and `tags` come from the server with counts, so an
// option only appears when at least one store has it.
export default function FilterPanel({
  q, onQ, area, onArea, areas,
  storeType, onStoreType, kinds,
  tag, onTag, tags,
  openOnly, onOpenOnly, count, onReset,
}) {
  return (
    <>
      <div className="explore-filters">
        <label>
          <span className="field-label">Search</span>
          <input className="input" placeholder="Store name or location…" value={q} onChange={e => onQ(e.target.value)} />
        </label>
        <label>
          <span className="field-label">Area</span>
          <select className="select" value={area} onChange={e => onArea(e.target.value)}>
            <option value="">All areas</option>
            {areas.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <div className="explore-filter-pair">
          <label>
            <span className="field-label">Store kind</span>
            <select className="select" value={storeType} onChange={e => onStoreType(e.target.value)}>
              <option value="">All kinds</option>
              {kinds.map(k => <option key={k.value} value={k.value}>{k.label} ({k.count})</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">Sells</span>
            <select className="select" value={tag} onChange={e => onTag(e.target.value)}>
              <option value="">Anything</option>
              {tags.map(t => <option key={t.value} value={t.value}>{t.label} ({t.count})</option>)}
            </select>
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={openOnly} onChange={e => onOpenOnly(e.target.checked)} />
          <span>Open now only</span>
        </label>
      </div>

      <div className="explore-count">
        <span className="anton">{count} RESULTS</span>
        <button className="btn explore-reset" onClick={onReset}>Reset</button>
      </div>
    </>
  )
}
