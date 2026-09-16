import type { CSSProperties } from 'react'
import { useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { useDialogs } from '../DialogProvider'
import type { CalendarCategoryOut, UserCalendarListItem } from '../types'

export function CalendarCategoriesPanel({
  token,
  calendar,
  rows,
  isOwner,
  busy,
  setBusy,
  setErr,
  onRefresh,
  embedded = false,
}: {
  token: string
  calendar: UserCalendarListItem
  rows: CalendarCategoryOut[]
  isOwner: boolean
  busy: boolean
  setBusy: (v: boolean) => void
  setErr: (v: string | null) => void
  onRefresh: () => void
  /** Hide calendar name row when nested under calendar Edit screen */
  embedded?: boolean
}) {
  const { askConfirm } = useDialogs()
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('')

  async function add() {
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories`, {
        method: 'POST',
        token,
        json: { name, color: newColor.trim() || null },
      })
      setNewName('')
      setNewColor('')
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Add failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeCategory(catId: string) {
    const ok = await askConfirm({
      title: 'Delete category',
      message: 'Delete this category? Events keep their times but lose this colour in Canary.',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories/${catId}`, { method: 'DELETE', token })
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function patchColor(catId: string, raw: string) {
    const c = raw.trim()
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories/${catId}`, {
        method: 'PATCH',
        token,
        json: { color: c || null },
      })
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const colorInputStyle: CSSProperties = {
    width: 40,
    height: 32,
    padding: 0,
    border: '1px solid var(--border)',
    borderRadius: 6,
    cursor: busy ? 'not-allowed' : 'pointer',
    background: 'transparent',
    verticalAlign: 'middle',
  }

  return (
    <div style={{ marginBottom: embedded ? 0 : 16, padding: embedded ? 0 : 12, border: embedded ? 'none' : '1px solid var(--border)', borderRadius: embedded ? 0 : 8 }}>
      {embedded ? null : (
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
          <strong>{calendar.name}</strong>
          <span className="muted" style={{ fontSize: 12 }}>
            {calendar.source !== 'owned' ? `${calendar.owner.display_name} · ` : ''}
            {isOwner ? 'owner' : calendar.access === 'read' ? 'read-only' : 'can edit events'}
          </span>
        </div>
      )}
      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>No categories yet.</div>
      ) : (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18 }}>
          {rows.map((cat) => (
            <li key={cat.id} style={{ marginBottom: 8 }}>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span
                  title={cat.color ?? 'No colour'}
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 4,
                    background: cat.color || 'var(--border)',
                    border: '1px solid var(--border)',
                    flexShrink: 0,
                  }}
                />
                <span>{cat.name}</span>
                {isOwner ? (
                  <>
                    <input
                      type="color"
                      aria-label={`Colour for ${cat.name}`}
                      title="Choose colour"
                      value={cat.color ?? '#888888'}
                      disabled={busy}
                      style={colorInputStyle}
                      onChange={(e) => void patchColor(cat.id, e.target.value)}
                    />
                    {cat.color ? (
                      <button
                        type="button"
                        className="btn"
                        style={{ fontSize: 12, padding: '2px 8px' }}
                        disabled={busy}
                        onClick={() => void patchColor(cat.id, '')}
                      >
                        Clear colour
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn"
                      style={{ fontSize: 12, padding: '2px 8px' }}
                      disabled={busy}
                      onClick={() => void removeCategory(cat.id)}
                    >
                      Delete
                    </button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {isOwner ? (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 12, alignItems: 'center' }}>
          <input
            placeholder="New category name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ flex: '1 1 160px', minWidth: 140 }}
            disabled={busy}
          />
          <label className="row" style={{ gap: 6, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 13 }}>
              Colour
            </span>
            <input
              type="color"
              aria-label="Pick colour for new category"
              title="Choose colour (optional)"
              value={newColor || '#888888'}
              disabled={busy}
              style={colorInputStyle}
              onChange={(e) => setNewColor(e.target.value)}
            />
          </label>
          {newColor ? (
            <button type="button" className="btn" style={{ fontSize: 12, padding: '2px 8px' }} disabled={busy} onClick={() => setNewColor('')}>
              Clear colour
            </button>
          ) : null}
          <button type="button" className="btn primary" disabled={busy || !newName.trim()} onClick={() => void add()}>
            Add category
          </button>
        </div>
      ) : null}
    </div>
  )
}
