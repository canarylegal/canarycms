import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { useDialogs } from './DialogProvider'
import type { MatterContactTypeOut } from './types'

export function AdminMatterContacts({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<MatterContactTypeOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newSort, setNewSort] = useState(90)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const r = await apiFetch<MatterContactTypeOut[]>('/admin/matter-contact-types', { token })
      setRows(r)
    } catch (e: unknown) {
      setErr((e as ApiError)?.message ?? 'Failed to load contact types')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Contacts</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}
      <p className="muted" style={{ marginTop: 0 }}>
        These labels populate the matter contact type dropdown. The four system types (Client, Lawyers, New lender,
        Existing lender) cannot be deleted or renamed.
      </p>
      <div className="card stack" style={{ gap: 10, maxWidth: 720 }}>
        <div className="muted" style={{ fontWeight: 600 }}>
          Add type
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: '1 1 140px', marginBottom: 0 }}>
            <span>Slug</span>
            <input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              placeholder="e.g. surveyor"
              disabled={busy}
            />
          </label>
          <label className="field" style={{ flex: '1 1 160px', marginBottom: 0 }}>
            <span>Label</span>
            <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} disabled={busy} />
          </label>
          <label className="field" style={{ flex: '0 0 80px', marginBottom: 0 }}>
            <span>Sort</span>
            <input type="number" value={newSort} onChange={(e) => setNewSort(Number(e.target.value))} disabled={busy} />
          </label>
          <button
            type="button"
            className="btn primary"
            disabled={busy || !newSlug.trim() || !newLabel.trim()}
            onClick={async () => {
              setBusy(true)
              setErr(null)
              try {
                await apiFetch('/admin/matter-contact-types', {
                  token,
                  method: 'POST',
                  json: { slug: newSlug.trim(), label: newLabel.trim(), sort_order: newSort },
                })
                setNewSlug('')
                setNewLabel('')
                await load()
              } catch (e: unknown) {
                setErr((e as ApiError)?.message ?? 'Could not add contact type')
              } finally {
                setBusy(false)
              }
            }}
          >
            Add
          </button>
        </div>
      </div>
      <div className="list" style={{ marginTop: 12 }}>
        {rows.map((r) => (
          <div
            key={r.id}
            className="listCard row"
            style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12 }}
          >
            <div style={{ minWidth: 0 }}>
              <div className="listTitle">
                {r.label}{' '}
                {r.is_system ? (
                  <span className="muted" style={{ fontSize: 12 }}>
                    (system)
                  </span>
                ) : null}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                slug: <span className="mono">{r.slug}</span> · sort {r.sort_order}
              </div>
            </div>
            {!r.is_system ? (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={async () => {
                  const ok = await askConfirm({
                    title: 'Delete contact type',
                    message: `Remove “${r.label}”? Existing matter contacts keep this slug until edited.`,
                    danger: true,
                    confirmLabel: 'Delete',
                  })
                  if (!ok) return
                  setBusy(true)
                  setErr(null)
                  try {
                    await apiFetch(`/admin/matter-contact-types/${r.id}`, { token, method: 'DELETE' })
                    await load()
                  } catch (e: unknown) {
                    setErr((e as ApiError)?.message ?? 'Delete failed')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Delete
              </button>
            ) : (
              <span className="muted" style={{ fontSize: 13 }}>
                Cannot delete
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
