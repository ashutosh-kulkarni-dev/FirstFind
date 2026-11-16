// "Name this list" dialog shown when saving a cluster of stores.
export default function SaveListModal({ name, onName, error, saving, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <div className="anton modal-title">NAME THIS LIST</div>
        <input className="input" autoFocus
          placeholder="My thrift run"
          value={name} onChange={e => onName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onConfirm()} />
        {error && <p className="form-error">{error}</p>}
        <div className="modal-actions">
          <button className="btn btn-primary modal-confirm" onClick={onConfirm} disabled={saving}>
            {saving ? 'Saving…' : 'Save list'}
          </button>
          <button className="btn btn-light" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  )
}
