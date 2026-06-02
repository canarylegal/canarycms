import type { FeeScaleOut } from './types'

type Props = {
  scale: FeeScaleOut
  busy: boolean
  onEdit: () => void
  onClone: () => void
  onRemove: () => void
  onToggleFavorite: () => void
}

export function FeeScaleListCard({ scale, busy, onEdit, onClone, onRemove, onToggleFavorite }: Props) {
  const favorited = Boolean(scale.is_favorited)
  return (
    <div className="listCard row feeScaleListCard" style={{ justifyContent: 'space-between', gap: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: 'center', flex: 1, minWidth: 0 }}>
        <button
          type="button"
          className={`feeScaleFavoriteBtn${favorited ? ' feeScaleFavoriteBtn--on' : ''}`}
          disabled={busy}
          title={favorited ? 'Remove from favourites' : 'Add to favourites'}
          aria-label={favorited ? 'Remove from favourites' : 'Add to favourites'}
          aria-pressed={favorited}
          onClick={onToggleFavorite}
        >
          {favorited ? '★' : '☆'}
        </button>
        <div style={{ minWidth: 0 }}>
          <div className="listTitle">{scale.name}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {scale.reference}
            {scale.scope_summary ? ` · ${scale.scope_summary}` : ''}
          </div>
        </div>
      </div>
      <div className="row" style={{ gap: 6, flexShrink: 0 }}>
        <button type="button" className="btn" disabled={busy} onClick={onClone}>
          Clone
        </button>
        <button type="button" className="btn primary" disabled={busy} onClick={onEdit}>
          Edit
        </button>
        <button type="button" className="btn danger" disabled={busy} onClick={onRemove}>
          Remove
        </button>
      </div>
    </div>
  )
}
