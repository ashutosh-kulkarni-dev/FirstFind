import { Link } from 'react-router-dom'
import ScorePill from '../../components/ScorePill'

// Summary of the store whose marker was clicked.
export default function SelectedStoreCard({ store }) {
  return (
    <div className="explore-selected fade-up">
      <div className="section-eyebrow explore-selected-eyebrow">Selected store</div>
      <div className="anton explore-selected-name">{store.name}</div>
      <div className="muted explore-selected-meta">{[store.area, store.cat].filter(Boolean).join(' · ')}</div>
      <div className="explore-selected-row">
        <ScorePill score={store.score} googleRating={store.googleRating} />
        {store.open != null && (
          <span className={store.open ? 'open-flag open-flag-on' : 'open-flag'}>
            {store.open ? 'Open now' : 'Closed'}
          </span>
        )}
      </div>
      <Link to={`/store/${store.id}`} className="explore-selected-link">View store →</Link>
    </div>
  )
}
