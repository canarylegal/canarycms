import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { ApiError } from './api'
import type { MatterSubTypeEventTemplateOut } from './types'

interface Props {
  token: string
  subTypeId: string
  subTypeName: string
}

const SMALL: React.CSSProperties = { padding: '3px 8px', fontSize: '0.82em' }
const INLINE: React.CSSProperties = { flex: 1, width: 'auto', minWidth: 120 }

const NOTIFY_UNIT_OPTIONS = [
  { value: '', label: '—' },
  { value: 'days', label: 'days' },
  { value: 'weeks', label: 'weeks' },
  { value: 'months', label: 'months' },
] as const

function reminderSummary(r: MatterSubTypeEventTemplateOut): string {
  const parts: string[] = []
  if (r.notify_on_day !== false) parts.push('On the day')
  if (r.notify_every_n && r.notify_every_unit) {
    parts.push(`Every ${r.notify_every_n} ${r.notify_every_unit}`)
  }
  return parts.length ? parts.join(' · ') : 'No reminder cadence'
}

type EditRow = {
  id: string
  name: string
  sort_order: string
  notify_on_day: boolean
  notify_every_n: string
  notify_every_unit: '' | 'days' | 'weeks' | 'months'
}

export function AdminEventsTemplate({ token, subTypeId, subTypeName }: Props) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<MatterSubTypeEventTemplateOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [newOrder, setNewOrder] = useState('0')
  const [newNotifyOnDay, setNewNotifyOnDay] = useState(true)
  const [newEveryN, setNewEveryN] = useState('')
  const [newEveryUnit, setNewEveryUnit] = useState<'' | 'days' | 'weeks' | 'months'>('')
  const [edit, setEdit] = useState<EditRow | null>(null)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const data = await apiFetch<MatterSubTypeEventTemplateOut[]>(
        `/admin/sub-menus/events/templates/${subTypeId}`,
        { token },
      )
      setRows(data)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load events template')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    setRows([])
    setNewName('')
    setNewOrder('0')
    setNewNotifyOnDay(true)
    setNewEveryN('')
    setNewEveryUnit('')
    setEdit(null)
    void load()
  }, [subTypeId, token])

  function buildNotifyPayload(notifyOnDay: boolean, everyNRaw: string, everyUnit: '' | 'days' | 'weeks' | 'months') {
    const n = parseInt(everyNRaw.trim(), 10)
    const hasRepeat = everyNRaw.trim().length > 0 && everyUnit !== ''
    return {
      notify_on_day: notifyOnDay,
      notify_every_n: hasRepeat && !Number.isNaN(n) && n >= 1 ? n : null,
      notify_every_unit: hasRepeat && !Number.isNaN(n) && n >= 1 ? everyUnit : null,
    }
  }

  async function addRow() {
    if (!newName.trim()) return
    setBusy(true)
    setErr(null)
    try {
      const extra = buildNotifyPayload(newNotifyOnDay, newEveryN, newEveryUnit)
      await apiFetch('/admin/sub-menus/events/templates', {
        token,
        method: 'POST',
        json: {
          matter_sub_type_id: subTypeId,
          name: newName.trim(),
          sort_order: parseInt(newOrder, 10) || 0,
          ...extra,
        },
      })
      setNewName('')
      setNewOrder('0')
      setNewNotifyOnDay(true)
      setNewEveryN('')
      setNewEveryUnit('')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to add')
    } finally {
      setBusy(false)
    }
  }

  async function saveEdit() {
    if (!edit) return
    setBusy(true)
    setErr(null)
    try {
      const extra = buildNotifyPayload(edit.notify_on_day, edit.notify_every_n, edit.notify_every_unit)
      await apiFetch(`/admin/sub-menus/events/templates/${edit.id}`, {
        token,
        method: 'PATCH',
        json: {
          name: edit.name.trim(),
          sort_order: parseInt(edit.sort_order, 10) || 0,
          ...extra,
        },
      })
      setEdit(null)
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  async function removeRow(id: string) {
    const ok = await askConfirm({
      title: 'Remove template line',
      message: 'Remove this event line from the template?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/admin/sub-menus/events/templates/${id}`, { token, method: 'DELETE' })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to remove')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adminFinanceSection" style={{ marginTop: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ fontWeight: 600 }}>
          Calendar template — <span style={{ fontWeight: 400 }}>{subTypeName}</span>
        </div>
        <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <div className="muted" style={{ marginBottom: 12, fontSize: '0.9em' }}>
        Event names and order shown when a user opens Calendar on a case of this sub-type (after you assign the Calendar menu
        under Matters). Lower numbers appear first. E-mail reminder cadence applies when users opt into alerts for events
        linked to a template line.
      </div>
      {err ? <div className="error" style={{ marginBottom: 8 }}>{err}</div> : null}

      <div className="list">
        {rows.map((r) => (
          <div key={r.id} className="listCard row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
            {edit?.id === r.id ? (
              <div className="stack" style={{ flex: 1, minWidth: 0, gap: 10 }}>
                <input
                  style={INLINE}
                  value={edit.name}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                  disabled={busy}
                />
                <input
                  style={{ width: 72 }}
                  type="number"
                  value={edit.sort_order}
                  onChange={(e) => setEdit({ ...edit, sort_order: e.target.value })}
                  disabled={busy}
                />
                <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={edit.notify_on_day}
                    disabled={busy}
                    onChange={(e) => setEdit({ ...edit, notify_on_day: e.target.checked })}
                  />
                  <span>On the day</span>
                </label>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="muted" style={{ fontSize: '0.9em' }}>Every</span>
                  <input
                    style={{ width: 64 }}
                    type="number"
                    min={1}
                    placeholder="N"
                    value={edit.notify_every_n}
                    onChange={(e) => setEdit({ ...edit, notify_every_n: e.target.value })}
                    disabled={busy}
                  />
                  <div className="adminInlineSelect">
                    <SingleSelectDropdown
                      hideLabel
                      label="Repeat unit"
                      options={[...NOTIFY_UNIT_OPTIONS]}
                      value={edit.notify_every_unit}
                      disabled={busy}
                      onChange={(v) =>
                        setEdit({
                          ...edit,
                          notify_every_unit: v as EditRow['notify_every_unit'],
                        })
                      }
                      placeholder="—"
                    />
                  </div>
                  <span className="muted" style={{ fontSize: '0.85em' }}>before (lead-up)</span>
                </div>
                <div className="row" style={{ gap: 4 }}>
                  <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => void saveEdit()}>
                    Save
                  </button>
                  <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => setEdit(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span className="listTitle">
                    {r.name}{' '}
                    <span className="muted adminFinanceCatOrder" style={{ fontSize: '0.85em' }}>
                      #{r.sort_order}
                    </span>
                  </span>
                  <div className="muted" style={{ fontSize: '0.85em', marginTop: 4 }}>
                    {reminderSummary(r)}
                  </div>
                </div>
                <div className="row" style={{ gap: 4, flexShrink: 0 }}>
                  <button
                    type="button"
                    className="btn"
                    style={SMALL}
                    disabled={busy}
                    onClick={() =>
                      setEdit({
                        id: r.id,
                        name: r.name,
                        sort_order: String(r.sort_order),
                        notify_on_day: r.notify_on_day !== false,
                        notify_every_n: r.notify_every_n != null ? String(r.notify_every_n) : '',
                        notify_every_unit: r.notify_every_unit ?? '',
                      })
                    }
                  >
                    Edit
                  </button>
                  <button type="button" className="btn danger" style={SMALL} disabled={busy} onClick={() => void removeRow(r.id)}>
                    Remove
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {rows.length === 0 ? <div className="muted" style={{ padding: '8px 0' }}>No event lines yet.</div> : null}
      </div>

      <div className="stack" style={{ marginTop: 12, gap: 10 }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            style={{ ...INLINE, maxWidth: 280 }}
            placeholder="New event name…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={busy}
          />
          <input
            style={{ width: 80 }}
            type="number"
            placeholder="Order"
            value={newOrder}
            onChange={(e) => setNewOrder(e.target.value)}
            disabled={busy}
          />
          <button type="button" className="btn primary" disabled={busy || !newName.trim()} onClick={() => void addRow()}>
            Add event
          </button>
        </div>
        <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={newNotifyOnDay}
            disabled={busy}
            onChange={(e) => setNewNotifyOnDay(e.target.checked)}
          />
          <span className="muted" style={{ fontSize: '0.9em' }}>
            On the day (new lines)
          </span>
        </label>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="muted" style={{ fontSize: '0.9em' }}>Every</span>
          <input
            style={{ width: 64 }}
            type="number"
            min={1}
            placeholder="N"
            value={newEveryN}
            onChange={(e) => setNewEveryN(e.target.value)}
            disabled={busy}
          />
          <div className="adminInlineSelect">
            <SingleSelectDropdown
              hideLabel
              label="Repeat unit for new lines"
              options={[...NOTIFY_UNIT_OPTIONS]}
              value={newEveryUnit}
              disabled={busy}
              onChange={(v) => setNewEveryUnit(v as typeof newEveryUnit)}
              placeholder="—"
            />
          </div>
          <span className="muted" style={{ fontSize: '0.85em' }}>before (lead-up)</span>
        </div>
      </div>
    </div>
  )
}
