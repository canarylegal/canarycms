import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { MatterSearchPicker } from './MatterSearchPicker'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { MatterSubTypeStandardTaskOut, UserSummary } from './types'
import { CANARY_FOLLOW_UP_STANDARD_TASK_ID } from './standardTasks'
import { useExclusiveDropdownOpen } from './useExclusiveDropdownOpen'

export function TaskCreateModal({
  open,
  token,
  users,
  caseIdFixed,
  preset,
  onClose,
  onCreated,
}: {
  open: boolean
  token: string
  users: UserSummary[]
  caseIdFixed: string | null
  /** Optional seed when opening (e.g. document context Follow up). */
  preset: { standardTaskId?: string; title?: string } | null
  onClose: () => void
  onCreated: () => void
}) {
  const [pickedCaseId, setPickedCaseId] = useState('')
  const effectiveCaseId = caseIdFixed ?? pickedCaseId

  const [standardTaskTemplates, setStandardTaskTemplates] = useState<MatterSubTypeStandardTaskOut[]>([])
  const [standardId, setStandardId] = useState<string>('__custom__')
  const [customTitle, setCustomTitle] = useState('')
  const [titleOverride, setTitleOverride] = useState<string | null>(null)
  const [dueDate, setDueDate] = useState('')
  const [assignUserId, setAssignUserId] = useState('')
  const [priority, setPriority] = useState<'low' | 'normal' | 'high'>('normal')
  const [isPrivate, setIsPrivate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dropdown = useExclusiveDropdownOpen<'task' | 'assign' | 'priority'>()

  const taskOptions = useMemo(
    () => [
      ...standardTaskTemplates.map((t) => ({ value: t.id, label: t.title })),
      { value: '__custom__', label: 'Custom task…' },
    ],
    [standardTaskTemplates],
  )

  const assignOptions = useMemo(
    () =>
      users
        .filter((u) => u.is_active)
        .slice()
        .sort((a, b) => a.display_name.localeCompare(b.display_name))
        .map((u) => ({ value: u.id, label: u.display_name })),
    [users],
  )

  const priorityOptions = useMemo(
    () => [
      { value: 'low', label: 'Low' },
      { value: 'normal', label: 'Normal' },
      { value: 'high', label: 'High' },
    ],
    [],
  )

  useEffect(() => {
    if (!open) return
    setErr(null)
    setBusy(false)
    dropdown.closeAll()
    if (!caseIdFixed) setPickedCaseId('')
    const t = new Date()
    setDueDate(`${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`)
    setAssignUserId('')
    setPriority('normal')
    setIsPrivate(false)
    if (preset?.standardTaskId) {
      setStandardId(preset.standardTaskId)
      setTitleOverride(preset.title ?? null)
      setCustomTitle('')
      if (preset.standardTaskId === '__custom__') {
        setCustomTitle(preset.title ?? '')
      }
    } else {
      setStandardId('__custom__')
      setCustomTitle('')
      setTitleOverride(null)
    }
  }, [open, caseIdFixed, preset, dropdown.closeAll])

  useEffect(() => {
    if (!open || !effectiveCaseId) {
      setStandardTaskTemplates([])
      return
    }
    let cancelled = false
    async function loadStd() {
      try {
        const data = await apiFetch<MatterSubTypeStandardTaskOut[]>(
          `/cases/${effectiveCaseId}/standard-tasks`,
          { token },
        )
        if (cancelled) return
        const list = Array.isArray(data) ? data : []
        setStandardTaskTemplates(list)
        if (preset?.standardTaskId && list.some((x) => x.id === preset.standardTaskId)) {
          setStandardId(preset.standardTaskId)
          return
        }
        setStandardId((prev) => {
          if (prev !== '__custom__' && list.some((x) => x.id === prev)) return prev
          return list.length > 0 ? list[0]!.id : '__custom__'
        })
      } catch {
        if (!cancelled) {
          setStandardTaskTemplates([])
          setStandardId('__custom__')
        }
      }
    }
    void loadStd()
    return () => {
      cancelled = true
    }
  }, [open, effectiveCaseId, token, preset?.standardTaskId])

  useEffect(() => {
    if (!open) setTitleOverride(null)
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onClose])

  if (!open) return null

  const needsCasePick = !caseIdFixed

  return (
    <div
      className="modalOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-create-title"
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
    >
      <div className="modal card" style={{ maxWidth: 480, minWidth: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="paneHead">
          <h2 id="task-create-title" style={{ margin: 0, fontSize: 18 }}>
            New task
          </h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
        <div className="stack" style={{ marginTop: 12, gap: 12, minWidth: 0 }}>
          {err ? <div className="error">{err}</div> : null}
          {needsCasePick ? (
            <div className="field" style={{ minWidth: 0 }}>
              <span>Matter</span>
              <MatterSearchPicker
                token={token}
                value={pickedCaseId}
                onChange={setPickedCaseId}
                disabled={busy}
                autoFocus
                listMaxHeight={180}
              />
            </div>
          ) : null}
          <SingleSelectDropdown
            label="Task"
            options={taskOptions}
            value={standardId}
            onChange={(v) => {
              setStandardId(v)
              if (v === '__custom__' && titleOverride) {
                setCustomTitle(titleOverride)
                setTitleOverride(null)
              } else if (v !== CANARY_FOLLOW_UP_STANDARD_TASK_ID) {
                setTitleOverride(null)
              }
            }}
            open={dropdown.isOpen('task')}
            onOpenChange={(next) => dropdown.setOpen('task', next)}
            disabled={busy}
            placeholder="— select —"
          />
          {titleOverride !== null ? (
            <label className="field">
              <span>Title</span>
              <input value={titleOverride} onChange={(e) => setTitleOverride(e.target.value)} disabled={busy} />
            </label>
          ) : null}
          {standardId === '__custom__' ? (
            <label className="field">
              <span>Custom title</span>
              <input
                value={customTitle}
                onChange={(e) => setCustomTitle(e.target.value)}
                disabled={busy}
                placeholder="Describe the task…"
              />
            </label>
          ) : null}
          <label className="field">
            <span>Date</span>
            <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} disabled={busy} />
          </label>
          <SingleSelectDropdown
            label="Assigned to"
            options={assignOptions}
            value={assignUserId}
            onChange={setAssignUserId}
            open={dropdown.isOpen('assign')}
            onOpenChange={(next) => dropdown.setOpen('assign', next)}
            disabled={busy}
            placeholder="— Unassigned —"
          />
          <SingleSelectDropdown
            label="Priority"
            options={priorityOptions}
            value={priority}
            onChange={(v) => setPriority(v as 'low' | 'normal' | 'high')}
            open={dropdown.isOpen('priority')}
            onOpenChange={(next) => dropdown.setOpen('priority', next)}
            disabled={busy}
            placeholder="— select —"
          />
          <label className="row" style={{ alignItems: 'flex-start', gap: 8 }}>
            <input type="checkbox" checked={isPrivate} disabled={busy} onChange={(e) => setIsPrivate(e.target.checked)} />
            <span className="muted" style={{ lineHeight: 1.4 }}>
              Private — only you and the assignee (if any) can see this task on the matter.
            </span>
          </label>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() =>
                void (async () => {
                  if (!effectiveCaseId) {
                    setErr('Please select a matter.')
                    return
                  }
                  if (!dueDate.trim()) {
                    setErr('Please choose a date.')
                    return
                  }
                  if (standardId === '__custom__' && !customTitle.trim()) {
                    setErr('Please enter a task title or pick a standard task.')
                    return
                  }
                  setBusy(true)
                  setErr(null)
                  try {
                    const due = new Date(`${dueDate}T12:00:00`)
                    const json: Record<string, unknown> = {
                      due_at: due.toISOString(),
                      priority,
                      is_private: isPrivate,
                    }
                    if (assignUserId) json.assigned_to_user_id = assignUserId
                    if (standardId !== '__custom__') {
                      json.standard_task_id = standardId
                      if (titleOverride != null && titleOverride.trim() !== '') {
                        json.title = titleOverride.trim()
                      }
                    } else {
                      json.title = customTitle.trim()
                    }
                    await apiFetch(`/cases/${effectiveCaseId}/tasks`, { token, method: 'POST', json })
                    onCreated()
                    onClose()
                  } catch (e: unknown) {
                    setErr((e as ApiError).message ?? 'Failed to create task')
                  } finally {
                    setBusy(false)
                  }
                })()
              }
            >
              {busy ? 'Creating…' : 'Create task'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
