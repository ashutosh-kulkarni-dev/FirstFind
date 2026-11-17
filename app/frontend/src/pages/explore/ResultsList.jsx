import { useEffect, useRef, useState } from 'react'
import ScorePill from '../../components/ScorePill'

const PAGE = 40

// The stores matching the current filters, best rated first. Clicking a row
// selects the store (the map pans to it); the arrow opens its page. Hovering a
// row highlights its dot on the map, and hovering a dot highlights its row.
export default function ResultsList({ stores, selectedId, hoveredId, onSelect, onHover, onOpen }) {
  const [shown, setShown] = useState(PAGE)
  // A new result set starts from the top again.
  useEffect(() => { setShown(PAGE) }, [stores])

  // A store picked on the map is brought into view in the list.
  const listRef = useRef(null)
  useEffect(() => {
    if (!selectedId) return
    const at = stores.findIndex(s => s.id === selectedId)
    if (at < 0) return
    setShown(n => Math.max(n, Math.ceil((at + 1) / PAGE) * PAGE))
    requestAnimationFrame(() => {
      listRef.current?.querySelector('.result-row-on')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
    // Only when the selection changes: "Show more" must not jump back to it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  // A dot hovered on the map: show its row if it is already in the list.
  useEffect(() => {
    if (!hoveredId) return
    listRef.current?.querySelector(`[data-store-id="${CSS.escape(hoveredId)}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [hoveredId])

  if (stores.length === 0) {
    return <div className="explore-hint">No stores match these filters. Try removing one.</div>
  }
  return (
    <div className="results-list" ref={listRef}>
      {stores.slice(0, shown).map(s => (
        <div key={s.id} role="button" tabIndex={0} data-store-id={s.id}
          className={['result-row', s.id === selectedId && 'result-row-on', s.id === hoveredId && 'result-row-hover']
            .filter(Boolean).join(' ')}
          onMouseEnter={() => onHover?.(s.id)}
          onMouseLeave={() => onHover?.(null)}
          onFocus={() => onHover?.(s.id)}
          onBlur={() => onHover?.(null)}
          onClick={() => onSelect(s.id)}
          onKeyDown={e => e.key === 'Enter' && onSelect(s.id)}>
          <div className="result-main">
            <div className="result-name">{s.name}</div>
            <div className="result-meta">
              {[s.area, s.kindLabel, ...s.tagLabels.slice(0, 2)].filter(Boolean).join(' · ')}
            </div>
          </div>
          <ScorePill score={s.score} googleRating={s.googleRating} />
          <button className="result-open" title="Open store page" aria-label={`Open ${s.name}`}
            onClick={e => { e.stopPropagation(); onOpen(s.id) }}>→</button>
        </div>
      ))}
      {stores.length > shown && (
        <button className="pill-btn results-more" onClick={() => setShown(n => n + PAGE)}>
          Show more ({stores.length - shown} left)
        </button>
      )}
    </div>
  )
}
