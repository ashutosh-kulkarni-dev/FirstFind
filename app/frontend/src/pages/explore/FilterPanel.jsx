// Search box, area picker and "open now" toggle, plus the result count.
export default function FilterPanel({ q, onQ, area, onArea, areas, openOnly, onOpenOnly, count, onReset }) {
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
