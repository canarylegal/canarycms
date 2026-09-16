import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { useDialogs } from '../DialogProvider'
import { SearchInput } from '../SearchInput'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import type {
  CalendarCategoryOut,
  CalendarDirectoryRow,
  CalendarShareOut,
  UserCalendarListItem,
  UserSummary,
} from '../types'
import { CalendarCategoriesPanel } from './CalendarCategoriesPanel'

export function CalendarManageModal({
  token,
  calendars,
  onClose,
  onChanged,
}: {
  token: string
  calendars: UserCalendarListItem[]
  onClose: () => void
  onChanged: () => void
}) {
  const { askConfirm } = useDialogs()
  const [newName, setNewName] = useState('')
  const [dirQ, setDirQ] = useState('')
  const [dirRows, setDirRows] = useState<CalendarDirectoryRow[] | null>(null)
  const [dirBusy, setDirBusy] = useState(false)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [shares, setShares] = useState<CalendarShareOut[]>([])
  const [pickGrantee, setPickGrantee] = useState('')
  const [pickCanWrite, setPickCanWrite] = useState(false)
  const [granteeDropdownOpen, setGranteeDropdownOpen] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editCalId, setEditCalId] = useState<string | null>(null)
  const [editCategoryRows, setEditCategoryRows] = useState<CalendarCategoryOut[]>([])

  const owned = useMemo(() => calendars.filter((c) => c.access === 'owner'), [calendars])

  const granteeOptions = useMemo(
    () =>
      users.map((u) => ({
        value: u.id,
        label: `${u.display_name} (${u.email})`,
      })),
    [users],
  )

  const editingCal = useMemo(
    () => (editCalId ? calendars.find((c) => c.id === editCalId) : undefined),
    [calendars, editCalId],
  )

  const loadEditCategories = useCallback(async () => {
    if (!editCalId) {
      setEditCategoryRows([])
      return
    }
    try {
      const rows = await apiFetch<CalendarCategoryOut[]>(`/users/me/calendars/${editCalId}/categories`, { token })
      setEditCategoryRows(rows)
    } catch {
      setEditCategoryRows([])
    }
  }, [editCalId, token])

  useEffect(() => {
    void loadEditCategories()
  }, [loadEditCategories])

  useEffect(() => {
    if (editCalId && !calendars.some((c) => c.id === editCalId)) {
      setEditCalId(null)
    }
  }, [calendars, editCalId])

  useEffect(() => {
    void apiFetch<UserSummary[]>('/users', { token })
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [token])

  async function searchDir() {
    const q = dirQ.trim()
    if (q.length < 1) return
    setDirBusy(true)
    setErr(null)
    try {
      const rows = await apiFetch<CalendarDirectoryRow[]>(
        `/users/me/calendars/directory?q=${encodeURIComponent(q)}`,
        { token },
      )
      setDirRows(rows)
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Search failed')
    } finally {
      setDirBusy(false)
    }
  }

  async function createCal() {
    const name = newName.trim()
    if (name.length < 1) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/users/me/calendars', { method: 'POST', token, json: { name } })
      setNewName('')
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  async function loadSharesForEdit(calId: string) {
    try {
      const rows = await apiFetch<CalendarShareOut[]>(`/users/me/calendars/${calId}/shares`, { token })
      setShares(rows)
    } catch {
      setShares([])
    }
  }

  function openCalendarEdit(calId: string) {
    setErr(null)
    setEditCalId(calId)
    void loadSharesForEdit(calId)
  }

  async function togglePublic(calId: string, cur: boolean) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}`, { method: 'PATCH', token, json: { is_public: !cur } })
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  async function addShare(calId: string) {
    const id = pickGrantee
    if (!id) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/shares`, {
        method: 'POST',
        token,
        json: { grantee_user_id: id, can_write: pickCanWrite },
      })
      setPickGrantee('')
      setPickCanWrite(false)
      await loadSharesForEdit(calId)
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Share failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeShare(calId: string, granteeId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/shares/${granteeId}`, { method: 'DELETE', token })
      await loadSharesForEdit(calId)
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Remove share failed')
    } finally {
      setBusy(false)
    }
  }

  async function subscribe(calId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/users/me/calendars/subscribe', { method: 'POST', token, json: { calendar_id: calId } })
      onChanged()
      setDirRows(null)
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Subscribe failed')
    } finally {
      setBusy(false)
    }
  }

  async function unsubscribe(calId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/subscription`, { method: 'DELETE', token })
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Unsubscribe failed')
    } finally {
      setBusy(false)
    }
  }

  async function deleteOwnedCalendar(calId: string, name: string) {
    const ok = await askConfirm({
      title: 'Delete calendar',
      message: `Delete calendar “${name}”? All events in this calendar will be removed from the server. Shares and Canary categories for it will be removed. This cannot be undone.`,
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}`, { method: 'DELETE', token })
      setEditCalId((prev) => (prev === calId ? null : prev))
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.35)',
        zIndex: 30,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && (editCalId ? setEditCalId(null) : onClose())}
      role="presentation"
    >
      <div
        className="card"
        style={{ maxWidth: 560, width: '100%', maxHeight: '90vh', overflow: 'auto', padding: 20 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="presentation"
      >
        {err ? <div className="error" style={{ marginBottom: 12 }}>{err}</div> : null}

        {editCalId && editingCal && editingCal.access === 'owner' ? (
          <>
            <div className="row" style={{ marginBottom: 16, gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button type="button" className="btn" disabled={busy} onClick={() => setEditCalId(null)}>
                ← Back
              </button>
            </div>
            <h3 style={{ marginTop: 0 }}>{editingCal.name}</h3>
            <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
              Change who can see this calendar, whether it appears in the public directory, and Canary-only event
              categories (not synced to external CalDAV).
            </p>

            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Public directory
              </span>
              <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="checkbox"
                  checked={editingCal.is_public}
                  disabled={busy}
                  onChange={() => void togglePublic(editingCal.id, editingCal.is_public)}
                />
              </label>
            </div>

            <h4 style={{ margin: '0 0 8px' }}>Access</h4>
            <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
              Other Canary users you add here see this calendar in the app (merged by the server). It does not appear in
              their external CalDAV client — only calendars on their own account sync there.
            </div>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
              <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                <SingleSelectDropdown
                  label="User"
                  placeholder="Select user…"
                  options={granteeOptions}
                  value={pickGrantee}
                  disabled={busy}
                  open={granteeDropdownOpen}
                  onOpenChange={setGranteeDropdownOpen}
                  onChange={setPickGrantee}
                />
              </div>
              <label className="row" style={{ gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={pickCanWrite} onChange={(e) => setPickCanWrite(e.target.checked)} />
                <span className="muted" style={{ fontSize: 13 }}>Can edit</span>
              </label>
              <button
                type="button"
                className="btn primary"
                disabled={busy || !pickGrantee}
                onClick={() => void addShare(editingCal.id)}
              >
                Add
              </button>
            </div>
            <ul style={{ margin: '0 0 20px', paddingLeft: 18 }}>
              {shares.map((s) => (
                <li key={s.grantee_user_id} style={{ marginBottom: 4 }}>
                  {s.grantee_display_name} ({s.grantee_email}) — {s.can_write ? 'edit' : 'view'}
                  <button
                    type="button"
                    className="btn"
                    style={{ marginLeft: 8, padding: '2px 8px', fontSize: 12 }}
                    disabled={busy}
                    onClick={() => void removeShare(editingCal.id, s.grantee_user_id)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>

            <h4 style={{ margin: '0 0 8px' }}>Event categories (Canary only)</h4>
            <p className="muted" style={{ marginTop: 0, fontSize: 13, marginBottom: 8 }}>
              Labels and colours for the in-app calendar. Everyone who can see this calendar can view its categories.
            </p>
            <CalendarCategoriesPanel
              token={token}
              calendar={editingCal}
              rows={editCategoryRows}
              isOwner
              busy={busy}
              setBusy={setBusy}
              setErr={setErr}
              onRefresh={() => void loadEditCategories()}
              embedded
            />

            <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="btn" onClick={() => setEditCalId(null)}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
        <h3 style={{ marginTop: 0 }}>Calendars</h3>
        <section style={{ marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>New calendar</h4>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input
              placeholder="Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: '1 1 200px' }}
            />
            <button type="button" className="btn primary" disabled={busy} onClick={() => void createCal()}>
              Create
            </button>
          </div>
        </section>

        <section style={{ marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>Find calendar by name</h4>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Lists public calendars and calendars already shared with you. Subscribe to add a public calendar to your list.
          </p>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <SearchInput
              placeholder="Search…"
              value={dirQ}
              onChange={(e) => setDirQ(e.target.value)}
              onClear={() => setDirQ('')}
              style={{ flex: '1 1 200px' }}
              aria-label="Search calendars"
            />
            <button type="button" className="btn" disabled={dirBusy} onClick={() => void searchDir()}>
              Search
            </button>
          </div>
          {dirRows ? (
            <div className="stack" style={{ marginTop: 12, gap: 8 }}>
              {dirRows.length === 0 ? (
                <div className="muted">No matches.</div>
              ) : (
                dirRows.map((r) => (
                  <div
                    key={r.id}
                    className="row"
                    style={{
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 10px',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <div>
                      <strong>{r.name}</strong>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {r.owner.display_name} — {r.is_public ? 'public' : 'shared with you'}
                        {r.shared_directly ? ' — already shared' : ''}
                      </div>
                    </div>
                    {r.can_subscribe ? (
                      <button type="button" className="btn primary" disabled={busy} onClick={() => void subscribe(r.id)}>
                        Subscribe
                      </button>
                    ) : (
                      <span className="muted" style={{ fontSize: 13 }}>
                        {r.already_in_my_list ? 'In your list' : '—'}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          ) : null}
        </section>

        <section>
          <h4 style={{ margin: '0 0 8px' }}>Your calendars</h4>
          {owned.map((c) => (
            <div key={c.id} style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border)', borderRadius: 8 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <strong>{c.name}</strong>
              </div>
              <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn primary" disabled={busy} onClick={() => openCalendarEdit(c.id)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => void deleteOwnedCalendar(c.id, c.name)}
                  style={{ color: 'var(--danger)' }}
                >
                  Delete calendar…
                </button>
              </div>
            </div>
          ))}
        </section>

        <section style={{ marginTop: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>Subscriptions</h4>
          {calendars.filter((c) => c.source === 'subscription').map((c) => (
            <div key={c.id} className="row" style={{ justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
              <span>
                {c.name} <span className="muted">— {c.owner.display_name}</span>
              </span>
              <button type="button" className="btn" disabled={busy} onClick={() => void unsubscribe(c.id)}>
                Unsubscribe
              </button>
            </div>
          ))}
          {calendars.every((c) => c.source !== 'subscription') ? (
            <div className="muted" style={{ fontSize: 13 }}>No subscriptions yet.</div>
          ) : null}
        </section>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>
            Done
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  )
}
