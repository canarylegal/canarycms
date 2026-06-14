import { useEffect, useMemo, useRef, useState } from 'react'
import { TASKS_MENU_TABLE_GRID } from './columnGridDefaults'
import { useDialogs } from './DialogProvider'
import { apiFetch } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseTaskOut, MatterSubTypeStandardTaskOut, TaskMenuRow, UserSummary } from './types'
import { useExclusiveDropdownOpen } from './useExclusiveDropdownOpen'

export { TASKS_MENU_TABLE_GRID }

/**
 * Tasks menu: Date · Priority · Assigned · Task · Description · Client · Reference.
 * Description is 30% of row width (30fr of 100fr); other columns scale with prior proportions on the remaining 70%.
 */

const TASK_PRI_ORDER: Record<string, number> = { high: 2, normal: 1, low: 0 }

function formatTaskMenuDate(iso: string) {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString()
}

function priorityLabel(p: string): string {
  if (p === 'high') return 'High'
  if (p === 'low') return 'Low'
  return 'Normal'
}

export function TasksTable({
  token,
  currentUserId,
  users,
  rows,
  layoutMode = 'list',
  search,
  filterMatterType,
  onSelectCase,
  sortKey,
  sortDir,
  onSort,
  onInvalidate,
  embedded,
  suppressCaseOpen,
  gridTemplateColumns,
  startColumnResize,
}: {
  token: string
  currentUserId: string
  users: UserSummary[]
  rows: TaskMenuRow[]
  layoutMode?: 'list' | 'kanban'
  search: string
  filterMatterType: string
  onSelectCase: (caseId: string) => void
  sortKey: 'reference' | 'client' | 'matter' | 'task' | 'date' | 'assigned' | 'priority'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'task' | 'date' | 'assigned' | 'priority') => void
  onInvalidate: () => void
  /** When set, omit outer card chrome (nested inside case documents panel). */
  embedded?: boolean
  /** Hide “Open matter” actions when tasks are already shown in case context. */
  suppressCaseOpen?: boolean
  gridTemplateColumns?: string
  startColumnResize?: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
}) {
  const { askConfirm } = useDialogs()
  const [ctx, setCtx] = useState<null | { x: number; y: number; row: TaskMenuRow }>(null)
  const listGrid = gridTemplateColumns ?? TASKS_MENU_TABLE_GRID
  const resizeCol = startColumnResize
  const taskCtxRef = useRef<HTMLDivElement | null>(null)
  const [editRow, setEditRow] = useState<TaskMenuRow | null>(null)
  const [editStandardId, setEditStandardId] = useState('__custom__')
  const [editStandardTasks, setEditStandardTasks] = useState<MatterSubTypeStandardTaskOut[]>([])
  const [editTitle, setEditTitle] = useState('')
  const [editDue, setEditDue] = useState('')
  const [editAssign, setEditAssign] = useState('')
  const [editPriority, setEditPriority] = useState<'low' | 'normal' | 'high'>('normal')
  const [editCompleted, setEditCompleted] = useState(false)
  const [editPrivate, setEditPrivate] = useState(false)
  const [editCreatedBy, setEditCreatedBy] = useState('')
  const [editBaseline, setEditBaseline] = useState<{
    title: string
    due: string
    assign: string
    priority: 'low' | 'normal' | 'high'
    completed: boolean
    isPrivate: boolean
    standardId: string
  } | null>(null)
  const [editBusy, setEditBusy] = useState(false)
  const [editErr, setEditErr] = useState<string | null>(null)
  const editDropdown = useExclusiveDropdownOpen<'category' | 'priority' | 'assign'>()
  const [taskRowFocusId, setTaskRowFocusId] = useState<string | null>(null)
  const [kanbanTitles, setKanbanTitles] = useState<string[]>([])

  useEffect(() => {
    if (layoutMode !== 'kanban') return
    let cancel = false
    void apiFetch<string[]>(`/tasks/kanban-column-titles`, { token })
      .then((data) => {
        if (!cancel && Array.isArray(data)) setKanbanTitles(data)
      })
      .catch(() => {
        if (!cancel) setKanbanTitles([])
      })
    return () => {
      cancel = true
    }
  }, [layoutMode, token])

  const editAssignOptions = useMemo(
    () =>
      users
        .filter((u) => u.is_active)
        .slice()
        .sort((a, b) => a.display_name.localeCompare(b.display_name))
        .map((u) => ({ value: u.id, label: u.display_name })),
    [users],
  )

  const editPriorityOptions = useMemo(
    () => [
      { value: 'low', label: 'Low' },
      { value: 'normal', label: 'Normal' },
      { value: 'high', label: 'High' },
    ],
    [],
  )

  const editCategoryOptions = useMemo(
    () => [
      ...editStandardTasks.map((t) => ({ value: t.id, label: t.title })),
      { value: '__custom__', label: 'Custom (no category)' },
    ],
    [editStandardTasks],
  )

  const visible = useMemo(() => {
    const s = search.trim().toLowerCase()
    let filtered = rows
    if (s) {
      filtered = filtered.filter((r) => {
        const parts = [
          r.case_number,
          r.client_name ?? '',
          r.matter_description ?? '',
          r.task_title,
          r.date,
          formatTaskMenuDate(r.date),
          r.assigned_display_name ?? '',
          r.priority,
          r.status,
          r.is_private ? 'private' : '',
        ]
        return parts.join(' ').toLowerCase().includes(s)
      })
    }
    if (filterMatterType) {
      filtered = filtered.filter((r) => r.matter_type_label === filterMatterType)
    }
    const dir = sortDir === 'asc' ? 1 : -1
    const sorted = [...filtered].sort((a, b) => {
      const key = sortKey
      if (key === 'priority') {
        const pa = TASK_PRI_ORDER[a.priority] ?? 1
        const pb = TASK_PRI_ORDER[b.priority] ?? 1
        if (pa !== pb) return (pa - pb) * -dir
        return (new Date(a.date).getTime() - new Date(b.date).getTime()) * dir
      }
      const av =
        key === 'reference'
          ? a.case_number
          : key === 'client'
            ? a.client_name ?? ''
            : key === 'matter'
              ? a.matter_description ?? ''
              : key === 'task'
                ? a.task_title
                : key === 'date'
                  ? a.date
                  : a.assigned_display_name ?? ''
      const bv =
        key === 'reference'
          ? b.case_number
          : key === 'client'
            ? b.client_name ?? ''
            : key === 'matter'
              ? b.matter_description ?? ''
              : key === 'task'
                ? b.task_title
                : key === 'date'
                  ? b.date
                  : b.assigned_display_name ?? ''
      const c = String(av).localeCompare(String(bv)) * dir
      if (c !== 0) return c
      const pa = TASK_PRI_ORDER[a.priority] ?? 1
      const pb = TASK_PRI_ORDER[b.priority] ?? 1
      if (pa !== pb) return pb - pa
      return new Date(a.date).getTime() - new Date(b.date).getTime()
    })
    return sorted
  }, [rows, search, filterMatterType, sortKey, sortDir])

  const kanbanBuckets = useMemo(() => {
    const m = new Map<string, TaskMenuRow[]>()
    for (const r of visible) {
      const t = r.standard_task_category_title?.trim()
      const col = t && kanbanTitles.includes(t) ? t : 'Custom'
      const arr = m.get(col)
      if (arr) arr.push(r)
      else m.set(col, [r])
    }
    return m
  }, [visible, kanbanTitles])

  const kanbanColumns = useMemo(() => {
    const cols: string[] = []
    for (const title of kanbanTitles) {
      if ((kanbanBuckets.get(title)?.length ?? 0) > 0) cols.push(title)
    }
    if ((kanbanBuckets.get('Custom')?.length ?? 0) > 0) cols.push('Custom')
    return cols
  }, [kanbanTitles, kanbanBuckets])

  useEffect(() => {
    if (!ctx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (taskCtxRef.current?.contains(t)) return
      setCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [ctx])

  async function openEdit(r: TaskMenuRow) {
    setEditErr(null)
    editDropdown.closeAll()
    setEditRow(r)
    setEditBusy(true)
    try {
      const [list, standardTasks] = await Promise.all([
        apiFetch<CaseTaskOut[]>(`/cases/${r.case_id}/tasks`, { token }),
        apiFetch<MatterSubTypeStandardTaskOut[]>(`/cases/${r.case_id}/standard-tasks`, { token }),
      ])
      const templates = Array.isArray(standardTasks) ? standardTasks : []
      setEditStandardTasks(templates)
      const t = list.find((x) => x.id === r.id)
      const title = (t?.title ?? r.task_title).trim()
      const dueRaw = t?.due_at ?? r.date
      const due = dueRaw.slice(0, 10)
      const assign = t?.assigned_to_user_id ?? ''
      const pri = (t?.priority ?? r.priority ?? 'normal') as 'low' | 'normal' | 'high'
      const completed = (t?.status ?? r.status) === 'done'
      const priv = Boolean(t?.is_private)
      const createdBy = t?.created_by_user_id ?? ''
      const stdIdRaw = t?.standard_task_id ?? r.standard_task_id ?? null
      const stdId =
        stdIdRaw && templates.some((x) => x.id === stdIdRaw) ? stdIdRaw : '__custom__'
      setEditTitle(title)
      setEditDue(due)
      setEditAssign(assign)
      setEditPriority(pri)
      setEditCompleted(completed)
      setEditPrivate(priv)
      setEditCreatedBy(createdBy)
      setEditStandardId(stdId)
      setEditBaseline({ title, due, assign, priority: pri, completed, isPrivate: priv, standardId: stdId })
    } catch {
      const due = r.date.slice(0, 10)
      const pri = (r.priority ?? 'normal') as 'low' | 'normal' | 'high'
      const completed = r.status === 'done'
      const priv = Boolean(r.is_private)
      const stdId = r.standard_task_id ?? '__custom__'
      setEditStandardTasks([])
      setEditTitle(r.task_title)
      setEditDue(due)
      setEditAssign('')
      setEditPriority(pri)
      setEditCompleted(completed)
      setEditPrivate(priv)
      setEditCreatedBy('')
      setEditStandardId(stdId)
      setEditBaseline({
        title: r.task_title,
        due,
        assign: '',
        priority: pri,
        completed,
        isPrivate: priv,
        standardId: stdId,
      })
    } finally {
      setEditBusy(false)
    }
  }

  function discardTaskEdit() {
    if (editBaseline) {
      setEditTitle(editBaseline.title)
      setEditDue(editBaseline.due)
      setEditAssign(editBaseline.assign)
      setEditPriority(editBaseline.priority)
      setEditCompleted(editBaseline.completed)
      setEditPrivate(editBaseline.isPrivate)
      setEditStandardId(editBaseline.standardId)
    }
    setEditRow(null)
    setEditErr(null)
  }

  async function saveEdit() {
    if (!editRow) return
    setEditBusy(true)
    setEditErr(null)
    try {
      const due = new Date(`${editDue}T12:00:00`)
      const patch: Record<string, unknown> = {
        title: editTitle.trim(),
        due_at: due.toISOString(),
        priority: editPriority,
        assigned_to_user_id: editAssign || null,
        status: editCompleted ? 'done' : 'open',
        standard_task_id: editStandardId === '__custom__' ? null : editStandardId,
      }
      if (currentUserId && editCreatedBy === currentUserId) {
        patch.is_private = editPrivate
      }
      await apiFetch(`/cases/${editRow.case_id}/tasks/${editRow.id}`, {
        token,
        method: 'PATCH',
        json: patch,
      })
      setEditRow(null)
      setEditBaseline(null)
      onInvalidate()
    } catch (e: unknown) {
      setEditErr((e as { message?: string })?.message ?? 'Failed to update task')
    } finally {
      setEditBusy(false)
    }
  }

  async function markComplete(r: TaskMenuRow) {
    try {
      await apiFetch(`/cases/${r.case_id}/tasks/${r.id}`, {
        token,
        method: 'PATCH',
        json: { status: 'done' },
      })
      onInvalidate()
    } catch {
      // ignore
    }
  }

  async function removeTask(r: TaskMenuRow, mode: 'delete' | 'clear') {
    const isClear = mode === 'clear'
    const ok = await askConfirm({
      title: isClear ? 'Clear task' : 'Delete task',
      message: isClear
        ? 'Remove this completed task from the list?'
        : 'Delete this task permanently?',
      danger: true,
      confirmLabel: isClear ? 'Clear' : 'Delete',
    })
    if (!ok) return
    try {
      await apiFetch(`/cases/${r.case_id}/tasks/${r.id}`, { token, method: 'DELETE' })
      onInvalidate()
    } catch {
      // ignore
    }
  }

  const outerCls = embedded ? 'tasksTableEmbed' : 'card casesTableCard'

  return (
    <div className={outerCls} style={{ padding: 0, overflow: 'hidden' }}>
      {layoutMode === 'kanban' ? (
        <div className="casesTableScroll tasksTableScroll" style={{ padding: 8 }}>
          <div className="row" style={{ alignItems: 'flex-start', gap: 12, flexWrap: 'nowrap', overflowX: 'auto' }}>
            {kanbanColumns.map((col) => (
              <div
                key={col}
                className="card"
                style={{ flex: '0 0 260px', minWidth: 220, padding: 10, background: 'var(--surface)' }}
              >
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>{col}</div>
                <div className="stack" style={{ gap: 8 }}>
                  {(kanbanBuckets.get(col) ?? []).map((r) => {
                    const rowCls =
                      r.status === 'done'
                        ? 'taskMenuRow--done'
                        : (r.priority ?? 'normal') === 'high'
                          ? 'taskMenuRow--high'
                          : ''
                    return (
                      <button
                        key={r.id}
                        type="button"
                        className={`btn taskKanbanCard ${rowCls}`}
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          whiteSpace: 'normal',
                          padding: 10,
                        }}
                        onClick={() => setTaskRowFocusId(r.id)}
                        onDoubleClick={() => {
                          if (suppressCaseOpen) return
                          onSelectCase(r.case_id)
                        }}
                        onContextMenu={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          setCtx({ x: e.clientX, y: e.clientY, row: r })
                        }}
                      >
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.task_title}</div>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {formatTaskMenuDate(r.date)} · {priorityLabel(r.priority ?? 'normal')}
                          {r.assigned_display_name ? ` · ${r.assigned_display_name}` : ''}
                        </div>
                        {!suppressCaseOpen ? (
                          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                            {r.case_number}
                            {r.matter_description ? ` · ${r.matter_description}` : ''}
                          </div>
                        ) : null}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
          {visible.length === 0 ? (
            <div className="muted" style={{ padding: 12 }}>
              No tasks to show yet.
            </div>
          ) : null}
        </div>
      ) : (
      <div className="casesTableScroll tasksTableScroll">
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: listGrid }}>
            {(
              [
                ['date', 'Date'],
                ['priority', 'Priority'],
                ['assigned', 'Assigned'],
                ['task', 'Task'],
                ['matter', 'Description'],
                ['client', 'Client name'],
                ['reference', 'Reference'],
              ] as const
            ).map(([k, label], colIndex) => (
              <div key={k} className="thCell">
                <button type="button" className="thbtn" onClick={() => onSort(k)}>
                  {label}
                </button>
                {resizeCol && colIndex < 6 ? (
                  <div
                    className="colResizeHandle"
                    role="separator"
                    aria-orientation="vertical"
                    aria-label={`Resize ${label} column`}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      resizeCol(colIndex, e.clientX, e.currentTarget.closest('.tr.th') as HTMLElement | null)
                    }}
                  />
                ) : null}
              </div>
            ))}
          </div>
          {visible.map((r) => {
            const rowCls =
              r.status === 'done'
                ? 'taskMenuRow--done'
                : (r.priority ?? 'normal') === 'high'
                  ? 'taskMenuRow--high'
                  : ''
            const rowActive = taskRowFocusId === r.id
            return (
              <button
                key={r.id}
                type="button"
                className={`tr rowbtn taskMenuRow ${rowCls} ${rowActive ? 'active' : ''}`}
                style={{ gridTemplateColumns: listGrid }}
                onClick={() => setTaskRowFocusId(r.id)}
                onDoubleClick={() => {
                  if (suppressCaseOpen) return
                  onSelectCase(r.case_id)
                }}
                onContextMenu={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  setCtx({ x: e.clientX, y: e.clientY, row: r })
                }}
              >
                <div className="td">{formatTaskMenuDate(r.date)}</div>
                <div className="td">{priorityLabel(r.priority ?? 'normal')}</div>
                <div className="td">{r.assigned_display_name ?? '—'}</div>
                <div className="td">
                  {r.task_title}
                  {r.is_private ? <span className="muted"> (private)</span> : null}
                </div>
                <div className="td">{r.matter_description ?? '—'}</div>
                <div className="td">{r.client_name ?? '—'}</div>
                <div className="td mono">{r.case_number}</div>
              </button>
            )
          })}
          {visible.length === 0 ? (
            <div className="muted" style={{ padding: 12 }}>
              No tasks to show yet.
            </div>
          ) : null}
        </div>
      </div>
      )}
      {ctx ? (
        <div
          ref={taskCtxRef}
          className="docContextMenu"
          style={{ left: ctx.x, top: ctx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {!suppressCaseOpen ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => {
                const r = ctx.row
                setCtx(null)
                onSelectCase(r.case_id)
              }}
            >
              Open
            </div>
          ) : null}
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              const r = ctx.row
              setCtx(null)
              void openEdit(r)
            }}
          >
            Edit…
          </div>
          {ctx.row.status !== 'done' ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => {
                const r = ctx.row
                setCtx(null)
                void markComplete(r)
              }}
            >
              Mark as complete
            </div>
          ) : null}
          {ctx.row.status === 'done' ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => {
                const r = ctx.row
                setCtx(null)
                void removeTask(r, 'clear')
              }}
            >
              Clear task
            </div>
          ) : (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => {
                const r = ctx.row
                setCtx(null)
                void removeTask(r, 'delete')
              }}
            >
              Delete
            </div>
          )}
        </div>
      ) : null}
      {editRow ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="task-edit-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !editBusy) discardTaskEdit()
          }}
        >
          <div className="modal card" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <div className="paneHead">
              <h2 id="task-edit-title" style={{ margin: 0, fontSize: 18 }}>
                Edit task
              </h2>
              <div className="row" style={{ gap: 8 }}>
                <button type="button" className="btn" disabled={editBusy} onClick={discardTaskEdit}>
                  Discard changes
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
                  disabled={editBusy}
                  onClick={() => void saveEdit()}
                >
                  {editBusy ? 'Saving…' : 'Save and close'}
                </button>
              </div>
            </div>
            <div className="stack" style={{ marginTop: 12, gap: 12 }}>
              {editErr ? <div className="error">{editErr}</div> : null}
              <SingleSelectDropdown
                label="Category"
                options={editCategoryOptions}
                value={editStandardId}
                onChange={setEditStandardId}
                open={editDropdown.isOpen('category')}
                onOpenChange={(next) => editDropdown.setOpen('category', next)}
                disabled={editBusy}
                placeholder="— select —"
              />
              <label className="field">
                <span>Title</span>
                <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} disabled={editBusy} />
              </label>
              <label className="field">
                <span>Due date</span>
                <input type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)} disabled={editBusy} />
              </label>
              <SingleSelectDropdown
                label="Priority"
                options={editPriorityOptions}
                value={editPriority}
                onChange={(v) => setEditPriority(v as 'low' | 'normal' | 'high')}
                open={editDropdown.isOpen('priority')}
                onOpenChange={(next) => editDropdown.setOpen('priority', next)}
                disabled={editBusy}
                placeholder="— select —"
              />
              <SingleSelectDropdown
                label="Assigned to"
                options={editAssignOptions}
                value={editAssign}
                onChange={setEditAssign}
                open={editDropdown.isOpen('assign')}
                onOpenChange={(next) => editDropdown.setOpen('assign', next)}
                disabled={editBusy}
                placeholder="— Unassigned —"
              />
              <label className="row taskEditCheckboxRow" style={{ gap: 8 }}>
                <input
                  type="checkbox"
                  checked={editCompleted}
                  disabled={editBusy}
                  onChange={(e) => setEditCompleted(e.target.checked)}
                />
                <span>Completed</span>
              </label>
              {currentUserId && editCreatedBy === currentUserId ? (
                <label className="row taskEditCheckboxRow" style={{ gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={editPrivate}
                    disabled={editBusy}
                    onChange={(e) => setEditPrivate(e.target.checked)}
                  />
                  <span>
                    Private — only you and the assignee (if any) can see this task on the matter.
                  </span>
                </label>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
