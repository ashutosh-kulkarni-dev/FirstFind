import ClusterResult from '../../components/zones/ClusterResult'

// What the dropped pin caught: the stores inside the circle, with save / clear.
export default function ClusterPanel({ active, stores, radiusKm, onOpenStore, onSave, onClear }) {
  if (!active) {
    return (
      <div className="explore-cluster">
        <div className="explore-hint">
          Double-click anywhere on the map to cluster stores within this diameter.
        </div>
      </div>
    )
  }
  return (
    <div className="explore-cluster">
      <ClusterResult stores={stores} radiusKm={radiusKm} onFocusStore={onOpenStore} />
      <div className="explore-cluster-actions">
        {stores.length > 0 && (
          <button className="pill-btn pill-btn-accent" onClick={onSave}>+ Save list</button>
        )}
        <button className="pill-btn" onClick={onClear}>Clear</button>
      </div>
    </div>
  )
}
