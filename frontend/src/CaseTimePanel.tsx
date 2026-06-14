import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseTimeEntryOut, UserSummary } from './types'

const TIME_UNIT_MINUTES = 6
const MAX_TENTHS = 80 // 8 hours per entry cap

interface Props {
  caseId: string
  token: string
  isAdmin: boolean
  currentUserId: string
}

function formatHours(tenths: number): string {
  const hrs = tenths / 10
  return hrs === Math.floor(hrs) ? String(hrs) : hrs.toFixed(1)
}

function formatMoneyPence(p: number | null | undefined): string {
  if (p == null) return '—'
  return `£${(p / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatEntryValue(e: CaseTimeEntryOut): string {
  if (e.non_billable) return 'Nil rate'
  return formatMoneyPence(e.value_pence)
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

function resolveTargetUserId(isAdmin: boolean, feeEarnerId: string, currentUserId: string): string {
  if (isAdmin && feeEarnerId) return feeEarnerId
  return currentUserId
}

function userHasChargeRate(users: UserSummary[], userId: string): boolean {
  return Boolean(users.find((u) => u.id === userId)?.has_charge_rate)
}

export function CaseTimePanel({ caseId, token, isAdmin, currentUserId }: Props) {
  const { askConfirm } = useDialogs()
  const [entries, setEntries] = useState<CaseTimeEntryOut[]>([])
  const [users, setUsers] = useState<UserSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [workDate, setWorkDate] = useState(todayIsoDate())
  const [tenths, setTenths] = useState(1)
  const [description, setDescription] = useState('')
  const [feeEarnerId, setFeeEarnerId] = useState('')
  const [nonBillable, setNonBillable] = useState(false)

  const [editId, setEditId] = useState<string | null>(null)
  const [editWorkDate, setEditWorkDate] = useState('')
  const [editTenths, setEditTenths] = useState(1)
  const [editDescription, setEditDescription] = useState('')
  const [editFeeEarnerId, setEditFeeEarnerId] = useState('')
  const [editNonBillable, setEditNonBillable] = useState(false)

  const addTargetUserId = useMemo(
    () => resolveTargetUserId(isAdmin, feeEarnerId, currentUserId),
    [isAdmin, feeEarnerId, currentUserId],
  )
  const addTargetHasRate = useMemo(
    () => userHasChargeRate(users, addTargetUserId),
    [users, addTargetUserId],
  )
  const editTargetUserId = editId ? resolveTargetUserId(isAdmin, editFeeEarnerId, currentUserId) : ''
  const editTargetHasRate = useMemo(
    () => (editTargetUserId ? userHasChargeRate(users, editTargetUserId) : true),
    [users, editTargetUserId],
  )

  useEffect(() => {
    if (!addTargetHasRate) setNonBillable(true)
  }, [addTargetHasRate])

  useEffect(() => {
    if (editId && !editTargetHasRate) setEditNonBillable(true)
  }, [editId, editTargetHasRate])

  const tenthsOptions = useMemo(
    () =>
      Array.from({ length: MAX_TENTHS }, (_, i) => {
        const n = i + 1
        return { value: String(n), label: `${formatHours(n)} hr (${n * TIME_UNIT_MINUTES} min)` }
      }),
    [],
  )

  const userOptions = useMemo(
    () => users.map((u) => ({ value: u.id, label: u.display_name || u.email })),
    [users],
  )

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const [list, userList] = await Promise.all([
        apiFetch<CaseTimeEntryOut[]>(`/cases/${caseId}/time`, { token }),
        apiFetch<UserSummary[]>('/users', { token }),
      ])
      setEntries(list)
      setUsers(userList.filter((u) => u.is_active))
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to load time entries')
    } finally {
      setBusy(false)
    }
  }, [caseId, token])

  useEffect(() => {
    void load()
  }, [load])

  const unbilledSummary = useMemo(() => {
    let billableMinutes = 0
    let nilMinutes = 0
    let value = 0
    for (const e of entries) {
      if (e.status !== 'unbilled') continue
      if (e.non_billable) {
        nilMinutes += e.duration_minutes
        continue
      }
      billableMinutes += e.duration_minutes
      if (e.value_pence != null) value += e.value_pence
    }
    return { billableMinutes, nilMinutes, value: billableMinutes > 0 ? value : null }
  }, [entries])

  async function addEntry() {
    const desc = description.trim()
    if (!desc) {
      setError('Enter a description.')
      return
    }
    if (!addTargetHasRate && !nonBillable) {
      setError('This fee earner has no charge rate. Record as non-billable or ask an admin to set a rate.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await apiFetch<CaseTimeEntryOut>(`/cases/${caseId}/time`, {
        token,
        method: 'POST',
        json: {
          work_date: workDate,
          duration_minutes: tenths * TIME_UNIT_MINUTES,
          description: desc,
          non_billable: nonBillable,
          ...(isAdmin && feeEarnerId ? { user_id: feeEarnerId } : {}),
        },
      })
      setDescription('')
      setTenths(1)
      setNonBillable(!addTargetHasRate)
      await load()
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to add time')
    } finally {
      setBusy(false)
    }
  }

  function startEdit(e: CaseTimeEntryOut) {
    setEditId(e.id)
    setEditWorkDate(e.work_date)
    setEditTenths(e.duration_tenths)
    setEditDescription(e.description)
    setEditFeeEarnerId(e.user_id)
    setEditNonBillable(Boolean(e.non_billable))
  }

  async function saveEdit() {
    if (!editId) return
    const desc = editDescription.trim()
    if (!desc) {
      setError('Enter a description.')
      return
    }
    if (!editTargetHasRate && !editNonBillable) {
      setError('This fee earner has no charge rate. Record as non-billable or ask an admin to set a rate.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await apiFetch<CaseTimeEntryOut>(`/cases/${caseId}/time/${editId}`, {
        token,
        method: 'PATCH',
        json: {
          work_date: editWorkDate,
          duration_minutes: editTenths * TIME_UNIT_MINUTES,
          description: desc,
          non_billable: editNonBillable,
          ...(isAdmin ? { user_id: editFeeEarnerId } : {}),
        },
      })
      setEditId(null)
      await load()
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  async function removeEntry(id: string) {
    const ok = await askConfirm({
      title: 'Delete time entry',
      message: 'Remove this time entry?',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await apiFetch(`/cases/${caseId}/time/${id}`, { token, method: 'DELETE' })
      if (editId === id) setEditId(null)
      await load()
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to delete')
    } finally {
      setBusy(false)
    }
  }

  async function writeOffEntry(id: string) {
    const ok = await askConfirm({
      title: 'Write off time',
      message: 'Mark this time as written off? It will no longer appear as billable WIP.',
      danger: true,
      confirmLabel: 'Write off',
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await apiFetch(`/cases/${caseId}/time/${id}/write-off`, { token, method: 'POST' })
      if (editId === id) setEditId(null)
      await load()
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to write off')
    } finally {
      setBusy(false)
    }
  }

  function statusLabel(e: CaseTimeEntryOut): string {
    if (e.status === 'written_off') return 'Written off'
    if (e.status === 'billed') return 'Billed'
    if (e.non_billable) return 'Unbilled (nil rate)'
    return 'Unbilled'
  }

  function nonBillableCheckbox(
    checked: boolean,
    onChange: (v: boolean) => void,
    hasRate: boolean,
    disabled: boolean,
  ) {
    return (
      <label className="field" style={{ marginBottom: 0, flex: '1 1 100%' }}>
        <span className="row" style={{ gap: 8, alignItems: 'center', fontSize: '0.92em' }}>
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled || !hasRate}
            onChange={(ev) => onChange(ev.target.checked)}
          />
          Non-billable (nil rate)
        </span>
        {!hasRate ? (
          <span className="muted" style={{ display: 'block', fontSize: '0.85em', marginTop: 4 }}>
            No charge rate on this fee earner — time can only be recorded as non-billable.
          </span>
        ) : null}
      </label>
    )
  }

  return (
    <div className="caseTimePanel stack" style={{ gap: 12 }}>
      <p className="muted" style={{ margin: 0, fontSize: '0.92em' }}>
        Log fee-earner time in 0.1 hour (6 minute) units. Billable unbilled time can be added to an invoice from the
        case ledger.
      </p>
      {error ? <div className="error">{error}</div> : null}

      <div className="card" style={{ padding: 12 }}>
        <h4 style={{ margin: '0 0 10px', fontSize: '0.95rem' }}>Add time</h4>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field" style={{ marginBottom: 0 }}>
            <span>Date</span>
            <input
              type="date"
              className="input"
              value={workDate}
              onChange={(e) => setWorkDate(e.target.value)}
              disabled={busy}
            />
          </label>
          <div className="field" style={{ marginBottom: 0, minWidth: 160 }}>
            <SingleSelectDropdown
              label="Duration"
              options={tenthsOptions}
              value={String(tenths)}
              onChange={(v) => setTenths(parseInt(v, 10) || 1)}
              disabled={busy}
            />
          </div>
          {isAdmin ? (
            <div className="field" style={{ marginBottom: 0, minWidth: 180 }}>
              <SingleSelectDropdown
                label="Fee earner"
                options={userOptions}
                value={feeEarnerId}
                onChange={setFeeEarnerId}
                disabled={busy}
                placeholder="— You —"
              />
            </div>
          ) : null}
          <label className="field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
            <span>Description</span>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={busy}
              placeholder="What was done…"
            />
          </label>
          {nonBillableCheckbox(nonBillable, setNonBillable, addTargetHasRate, busy)}
          <button
            type="button"
            className="btn primary"
            disabled={busy || (!addTargetHasRate && !nonBillable)}
            onClick={() => void addEntry()}
          >
            Add
          </button>
        </div>
      </div>

      {unbilledSummary.billableMinutes > 0 || unbilledSummary.nilMinutes > 0 ? (
        <div className="muted" style={{ fontSize: '0.92em' }}>
          {unbilledSummary.billableMinutes > 0 ? (
            <>
              Billable unbilled:{' '}
              <strong>{formatHours(unbilledSummary.billableMinutes / TIME_UNIT_MINUTES)} hr</strong>
              {unbilledSummary.value != null ? <> ({formatMoneyPence(unbilledSummary.value)})</> : null}
            </>
          ) : null}
          {unbilledSummary.nilMinutes > 0 ? (
            <>
              {unbilledSummary.billableMinutes > 0 ? ' · ' : null}
              Nil-rate unbilled:{' '}
              <strong>{formatHours(unbilledSummary.nilMinutes / TIME_UNIT_MINUTES)} hr</strong>
            </>
          ) : null}
          {unbilledSummary.billableMinutes > 0 ? (
            <> — invoice from the <strong>Ledger</strong> tab → New invoice.</>
          ) : null}
        </div>
      ) : null}

      {entries.length === 0 && !busy ? (
        <p className="muted">No time recorded yet.</p>
      ) : (
        <table className="reportsTable">
          <thead>
            <tr>
              <th>Date</th>
              <th>Fee earner</th>
              <th>Duration</th>
              <th>Description</th>
              <th className="finAmtCell">Value</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {entries.map((e) =>
              editId === e.id ? (
                <tr key={e.id}>
                  <td>
                    <input
                      type="date"
                      className="input"
                      value={editWorkDate}
                      onChange={(ev) => setEditWorkDate(ev.target.value)}
                      disabled={busy}
                    />
                  </td>
                  <td>
                    {isAdmin ? (
                      <SingleSelectDropdown
                        hideLabel
                        label="Fee earner"
                        options={userOptions}
                        value={editFeeEarnerId}
                        onChange={setEditFeeEarnerId}
                        disabled={busy}
                      />
                    ) : (
                      e.user_display_name
                    )}
                  </td>
                  <td style={{ minWidth: 140 }}>
                    <SingleSelectDropdown
                      hideLabel
                      label="Duration"
                      options={tenthsOptions}
                      value={String(editTenths)}
                      onChange={(v) => setEditTenths(parseInt(v, 10) || 1)}
                      disabled={busy}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      style={{ width: '100%' }}
                      value={editDescription}
                      onChange={(ev) => setEditDescription(ev.target.value)}
                      disabled={busy}
                    />
                  </td>
                  <td className="finAmtCell">{formatEntryValue(e)}</td>
                  <td className="muted">{statusLabel(e)}</td>
                  <td colSpan={1}>
                    <div className="stack" style={{ gap: 6 }}>
                      {nonBillableCheckbox(editNonBillable, setEditNonBillable, editTargetHasRate, busy)}
                      <div className="row" style={{ gap: 6 }}>
                        <button type="button" className="btn btn--small primary" disabled={busy} onClick={() => void saveEdit()}>
                          Save
                        </button>
                        <button type="button" className="btn btn--small" disabled={busy} onClick={() => setEditId(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={e.id}>
                  <td>{e.work_date}</td>
                  <td>{e.user_display_name}</td>
                  <td>{formatHours(e.duration_tenths)} hr</td>
                  <td>{e.description}</td>
                  <td className="finAmtCell">{formatEntryValue(e)}</td>
                  <td className="muted">{statusLabel(e)}</td>
                  <td>
                    {e.status === 'unbilled' ? (
                      <>
                        <button type="button" className="btn btn--small" disabled={busy} onClick={() => startEdit(e)}>
                          Edit
                        </button>
                        {!e.non_billable ? (
                          <button type="button" className="btn btn--small" disabled={busy} onClick={() => void writeOffEntry(e.id)}>
                            Write off
                          </button>
                        ) : null}
                        <button type="button" className="btn btn--small danger" disabled={busy} onClick={() => void removeEntry(e.id)}>
                          Delete
                        </button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
