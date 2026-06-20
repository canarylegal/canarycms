import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import {
  GLOBAL_PRECEDENT_SCOPE,
  type MatterHeadTypeOut,
  type PortalFormFieldType,
  type PortalFormTemplateDetailOut,
  type PortalFormTemplateFieldIn,
  type PortalFormTemplateOut,
} from './types'

const FIELD_TYPE_OPTIONS: { value: PortalFormFieldType; label: string }[] = [
  { value: 'section', label: 'Section heading' },
  { value: 'text', label: 'Short text' },
  { value: 'textarea', label: 'Long text' },
  { value: 'date', label: 'Date' },
  { value: 'select', label: 'Dropdown' },
  { value: 'file', label: 'File upload' },
]

function randomHexRef(): string {
  const bytes = new Uint8Array(3)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function slugFieldKey(label: string): string {
  let s = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  if (!s || !/^[a-z]/.test(s)) s = `field_${s || 'x'}`
  return s.slice(0, 80)
}

type FieldDraft = PortalFormTemplateFieldIn & { id?: string }

function emptyField(sortOrder: number): FieldDraft {
  return {
    field_key: '',
    label: '',
    field_type: 'text',
    help_text: '',
    required: false,
    sort_order: sortOrder,
    select_options: [],
  }
}

function scopeToApi(headId: string, subId: string) {
  if (!headId || headId === GLOBAL_PRECEDENT_SCOPE) {
    return { matter_head_type_id: null, matter_sub_type_id: null }
  }
  if (!subId || subId === GLOBAL_PRECEDENT_SCOPE) {
    return { matter_head_type_id: headId, matter_sub_type_id: null }
  }
  return { matter_head_type_id: headId, matter_sub_type_id: subId }
}

function scopeFromTemplate(t: PortalFormTemplateOut): { headId: string; subId: string } {
  if (!t.matter_head_type_id) return { headId: GLOBAL_PRECEDENT_SCOPE, subId: GLOBAL_PRECEDENT_SCOPE }
  if (!t.matter_sub_type_id) return { headId: t.matter_head_type_id, subId: GLOBAL_PRECEDENT_SCOPE }
  return { headId: t.matter_head_type_id, subId: t.matter_sub_type_id }
}

function fieldsFromDetail(detail: PortalFormTemplateDetailOut): FieldDraft[] {
  return detail.fields.map((f, i) => ({
    id: f.id,
    field_key: f.field_key,
    label: f.label,
    field_type: f.field_type === ('yes_no' as PortalFormFieldType) ? 'select' : f.field_type,
    help_text: f.help_text ?? '',
    required: f.required ?? false,
    sort_order: f.sort_order ?? i,
    select_options:
      f.field_type === 'select' || (f.field_type as string) === 'yes_no'
        ? f.select_options?.length
          ? [...f.select_options]
          : ['Yes', 'No']
        : [],
  }))
}

export function AdminPortalForms({ token }: { token: string }) {
  const [items, setItems] = useState<PortalFormTemplateOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reference, setReference] = useState(() => randomHexRef())
  const [description, setDescription] = useState('')
  const [headId, setHeadId] = useState('')
  const [subId, setSubId] = useState('')
  const [fields, setFields] = useState<FieldDraft[]>([emptyField(0)])
  const [headOpen, setHeadOpen] = useState(false)
  const [subOpen, setSubOpen] = useState(false)
  const [saveOk, setSaveOk] = useState(false)

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ value: h.id, label: h.name })),
    [matterHeads],
  )

  const subTypeOptions = useMemo(() => {
    if (!headId || headId === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === headId)
    return (h?.sub_types ?? []).map((s) => ({ value: s.id, label: s.name }))
  }, [matterHeads, headId])

  const headDropdownOptions = useMemo(
    () => [{ value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all cases)' }, ...matterTypeOptions],
    [matterTypeOptions],
  )

  const subDropdownOptions = useMemo(
    () => [
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'All sub-types under this matter type' },
      ...subTypeOptions,
    ],
    [subTypeOptions],
  )

  const load = useCallback(async () => {
    setErr(null)
    try {
      const [rows, heads] = await Promise.all([
        apiFetch<PortalFormTemplateOut[]>('/admin/portal-forms', { token }),
        apiFetch<MatterHeadTypeOut[]>('/matter-types', { token }),
      ])
      setItems(Array.isArray(rows) ? rows : [])
      setMatterHeads(Array.isArray(heads) ? heads : [])
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load portal form templates')
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  function resetEditor() {
    setEditId(null)
    setName('')
    setReference(randomHexRef())
    setDescription('')
    setHeadId('')
    setSubId('')
    setFields([emptyField(0)])
    setSaveOk(false)
    setErr(null)
  }

  function openCreate() {
    resetEditor()
    setEditorOpen(true)
  }

  async function openEdit(id: string) {
    setBusy(true)
    setErr(null)
    try {
      const detail = await apiFetch<PortalFormTemplateDetailOut>(`/admin/portal-forms/${id}`, { token })
      const scope = scopeFromTemplate(detail)
      setEditId(id)
      setName(detail.name)
      setReference(detail.reference)
      setDescription(detail.description ?? '')
      setHeadId(scope.headId)
      setSubId(scope.subId)
      setFields(fieldsFromDetail(detail).length > 0 ? fieldsFromDetail(detail) : [emptyField(0)])
      setEditorOpen(true)
      setSaveOk(false)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not load template')
    } finally {
      setBusy(false)
    }
  }

  function closeEditor() {
    if (busy) return
    setEditorOpen(false)
    resetEditor()
  }

  function updateField(index: number, patch: Partial<FieldDraft>) {
    setFields((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row
        const next = { ...row, ...patch }
        if (patch.label !== undefined && !row.field_key.trim()) {
          next.field_key = slugFieldKey(patch.label)
        }
        return next
      }),
    )
  }

  function moveField(index: number, dir: -1 | 1) {
    const target = index + dir
    if (target < 0 || target >= fields.length) return
    setFields((prev) => {
      const copy = [...prev]
      const tmp = copy[index]
      copy[index] = copy[target]
      copy[target] = tmp
      return copy.map((f, i) => ({ ...f, sort_order: i }))
    })
  }

  function removeField(index: number) {
    setFields((prev) => {
      const next = prev.filter((_, i) => i !== index)
      return next.length > 0 ? next.map((f, i) => ({ ...f, sort_order: i })) : [emptyField(0)]
    })
  }

  function validate(): string | null {
    if (!name.trim()) return 'Enter a form name.'
    if (!reference.trim()) return 'Enter a reference.'
    if (!headId) return 'Select a matter type scope.'
    if (headId !== GLOBAL_PRECEDENT_SCOPE && !subId) return 'Select a sub-type scope.'
    const dataFields = fields.filter((f) => f.field_type !== 'section')
    if (dataFields.length === 0) return 'Add at least one input field (not only section headings).'
    for (const f of fields) {
      if (!f.label.trim()) return 'Every field needs a label.'
      if (f.field_type !== 'section' && !f.field_key.trim()) return `Field "${f.label}" needs a key.`
      if (f.field_type === 'select') {
        const opts = (f.select_options ?? []).map((o) => o.trim()).filter(Boolean)
        if (opts.length === 0) return `Dropdown "${f.label}" needs at least one option.`
      }
    }
    const keys = fields.filter((f) => f.field_type !== 'section').map((f) => f.field_key.trim())
    if (new Set(keys).size !== keys.length) return 'Field keys must be unique.'
    return null
  }

  async function save() {
    const validationErr = validate()
    if (validationErr) {
      setErr(validationErr)
      return
    }
    setBusy(true)
    setErr(null)
    setSaveOk(false)
    const payloadFields: PortalFormTemplateFieldIn[] = fields.map((f, i) => ({
      field_key: f.field_type === 'section' ? slugFieldKey(f.label || `section_${i}`) : f.field_key.trim(),
      label: f.label.trim(),
      field_type: f.field_type,
      help_text: f.help_text?.trim() || null,
      required: f.field_type !== 'section' && f.required,
      sort_order: i,
      select_options:
        f.field_type === 'select'
          ? (f.select_options ?? []).map((o) => o.trim()).filter(Boolean)
          : [],
    }))
    const scope = scopeToApi(headId, subId)
    const body = {
      name: name.trim(),
      reference: reference.trim(),
      description: description.trim() || null,
      ...scope,
      fields: payloadFields,
    }
    try {
      if (editId) {
        await apiFetch<PortalFormTemplateDetailOut>(`/admin/portal-forms/${editId}`, {
          token,
          method: 'PUT',
          json: body,
        })
      } else {
        await apiFetch<PortalFormTemplateDetailOut>('/admin/portal-forms', {
          token,
          method: 'POST',
          json: body,
        })
      }
      setSaveOk(true)
      await load()
      closeEditor()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save template')
    } finally {
      setBusy(false)
    }
  }

  async function removeTemplate(id: string) {
    if (!window.confirm('Delete this form template? Existing submissions are kept but no new sends will use it.')) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch<void>(`/admin/portal-forms/${id}`, { token, method: 'DELETE' })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not delete template')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 960 }}>
      <div>
        <p className="muted" style={{ margin: '0 0 12px' }}>
          Precedent-based forms sent manually to portal contacts. Responses are stored on the matter when the client
          submits.
        </p>
        <button type="button" className="btn primary" disabled={busy} onClick={openCreate}>
          New form template
        </button>
      </div>

      {err && !editorOpen ? <div className="error">{err}</div> : null}

      {items.length === 0 ? (
        <div className="muted">No portal form templates yet.</div>
      ) : (
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: '1fr 120px 1fr 100px 140px' }}>
            <div className="thCell">Name</div>
            <div className="thCell">Reference</div>
            <div className="thCell">Scope</div>
            <div className="thCell">Fields</div>
            <div className="thCell">Actions</div>
          </div>
          {items.map((row) => (
            <div key={row.id} className="tr" style={{ gridTemplateColumns: '1fr 120px 1fr 100px 140px' }}>
              <div className="td">{row.name}</div>
              <div className="td muted">{row.reference}</div>
              <div className="td muted">{row.scope_summary}</div>
              <div className="td muted">{row.field_count}</div>
              <div className="td row" style={{ gap: 6 }}>
                <button type="button" className="btn" disabled={busy} onClick={() => void openEdit(row.id)}>
                  Edit
                </button>
                <button type="button" className="btn" disabled={busy} onClick={() => void removeTemplate(row.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editorOpen ? (
        <div className="modalOverlay" role="dialog" aria-modal="true" onClick={() => closeEditor()}>
          <div
            className="modal card modal--scrollBody"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 720, width: '95vw' }}
          >
            <div className="paneHead">
              <h2 style={{ margin: 0, fontSize: 18 }}>{editId ? 'Edit form template' : 'New form template'}</h2>
              <button type="button" className="btn" disabled={busy} onClick={closeEditor}>
                Close
              </button>
            </div>
            <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
              {err ? <div className="error">{err}</div> : null}
              {saveOk ? <div className="notice">Saved.</div> : null}
              <label className="field">
                <span>Name</span>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
              </label>
              <label className="field">
                <span>Reference</span>
                <input className="input" value={reference} onChange={(e) => setReference(e.target.value)} disabled={busy} />
              </label>
              <label className="field">
                <span>Description (shown to client)</span>
                <textarea
                  className="input"
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={busy}
                />
              </label>
              <SingleSelectDropdown
                label="Matter type"
                options={headDropdownOptions}
                value={headId}
                onChange={(v) => {
                  setHeadId(v)
                  setSubId('')
                }}
                open={headOpen}
                onOpenChange={setHeadOpen}
                disabled={busy}
                placeholder="Choose scope…"
              />
              {headId && headId !== GLOBAL_PRECEDENT_SCOPE ? (
                <SingleSelectDropdown
                  label="Sub-type"
                  options={subDropdownOptions}
                  value={subId}
                  onChange={setSubId}
                  open={subOpen}
                  onOpenChange={setSubOpen}
                  disabled={busy}
                  placeholder="Choose sub-type…"
                />
              ) : null}

              <div>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 16 }}>Fields</h3>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => setFields((prev) => [...prev, emptyField(prev.length)])}
                  >
                    Add field
                  </button>
                </div>
                <div className="stack" style={{ gap: 10 }}>
                  {fields.map((f, index) => (
                    <div key={`${f.id ?? 'new'}-${index}`} className="card" style={{ padding: 12 }}>
                      <div className="stack" style={{ gap: 8 }}>
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                          <label className="field" style={{ flex: '2 1 160px' }}>
                            <span>Label</span>
                            <input
                              className="input"
                              value={f.label}
                              onChange={(e) => updateField(index, { label: e.target.value })}
                              disabled={busy}
                            />
                          </label>
                          <label className="field" style={{ flex: '1 1 140px' }}>
                            <span>Type</span>
                            <select
                              className="input"
                              value={f.field_type}
                              onChange={(e) => {
                                const nextType = e.target.value as PortalFormFieldType
                                updateField(index, {
                                  field_type: nextType,
                                  select_options:
                                    nextType === 'select'
                                      ? f.select_options?.length
                                        ? f.select_options
                                        : ['']
                                      : [],
                                })
                              }}
                              disabled={busy}
                            >
                              {FIELD_TYPE_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                        {f.field_type !== 'section' ? (
                          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                            <label className="field" style={{ flex: '1 1 160px' }}>
                              <span>Field key</span>
                              <input
                                className="input"
                                value={f.field_key}
                                onChange={(e) => updateField(index, { field_key: e.target.value })}
                                disabled={busy}
                              />
                            </label>
                            <label className="field row" style={{ gap: 6, alignItems: 'center', paddingBottom: 8 }}>
                              <input
                                type="checkbox"
                                checked={f.required}
                                onChange={(e) => updateField(index, { required: e.target.checked })}
                                disabled={busy}
                              />
                              <span>Required</span>
                            </label>
                          </div>
                        ) : null}
                        <label className="field">
                          <span>Help text (optional)</span>
                          <input
                            className="input"
                            value={f.help_text ?? ''}
                            onChange={(e) => updateField(index, { help_text: e.target.value })}
                            disabled={busy}
                          />
                        </label>
                        {f.field_type === 'select' ? (
                          <div className="stack" style={{ gap: 6 }}>
                            <span style={{ fontSize: 13, fontWeight: 500 }}>Dropdown options</span>
                            {(f.select_options ?? ['']).map((opt, optIndex) => (
                              <div key={optIndex} className="row" style={{ gap: 6 }}>
                                <input
                                  className="input"
                                  style={{ flex: 1 }}
                                  value={opt}
                                  placeholder={`Option ${optIndex + 1}`}
                                  onChange={(e) => {
                                    const next = [...(f.select_options ?? [''])]
                                    next[optIndex] = e.target.value
                                    updateField(index, { select_options: next })
                                  }}
                                  disabled={busy}
                                />
                                <button
                                  type="button"
                                  className="btn"
                                  disabled={busy || (f.select_options ?? []).length <= 1}
                                  onClick={() => {
                                    const next = [...(f.select_options ?? [''])]
                                    next.splice(optIndex, 1)
                                    updateField(index, { select_options: next.length ? next : [''] })
                                  }}
                                >
                                  Remove
                                </button>
                              </div>
                            ))}
                            <button
                              type="button"
                              className="btn"
                              disabled={busy}
                              onClick={() =>
                                updateField(index, { select_options: [...(f.select_options ?? ['']), ''] })
                              }
                            >
                              Add option
                            </button>
                          </div>
                        ) : null}
                        <div className="row" style={{ gap: 6 }}>
                          <button type="button" className="btn" disabled={busy || index === 0} onClick={() => moveField(index, -1)}>
                            ↑
                          </button>
                          <button
                            type="button"
                            className="btn"
                            disabled={busy || index === fields.length - 1}
                            onClick={() => moveField(index, 1)}
                          >
                            ↓
                          </button>
                          <button type="button" className="btn" disabled={busy} onClick={() => removeField(index)}>
                            Remove
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" className="btn" disabled={busy} onClick={closeEditor}>
                  Cancel
                </button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
                  {busy ? 'Saving…' : 'Save template'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
