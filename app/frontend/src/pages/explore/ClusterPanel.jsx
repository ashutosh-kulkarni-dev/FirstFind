import ClusterResult from '../../components/zones/ClusterResult'

// What the dropped pin caught: the stores inside the circle, with save / clear.
export default function ClusterPanel({ stores, radiusKm, onOpenStore, onSave, onClear }) {
  return (
    <>
      <ClusterResult stores={stores} radiusKm={radiusKm} onFocusStore={onOpenStore} />
      <div className="explore-cluster-actions">
        {stores.length > 0 && (
          <button className="pill-btn pill-btn-accent" onClick={onSave}>+ Save list</button>
        )}
        <button className="pill-btn" onClick={onClear}>Clear</button>
      </div>
    </>
  )
}
