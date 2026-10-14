import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react'
import { applyAuthHeaders, apiUrl, formatApiErrorDetail } from './api'
import { triggerBlobDownload } from './case/caseDocFileOps'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { PortalFormDetailOut, PortalFormFieldOut } from './types'

type Props = {
  submissionId: string
  portalToken: string
  onBack: () => void
  onSubmitted: () => void
  previewMode?: boolean
}

/** Local / admin interactive preview — no network fetch. */
export type PortalFormLocalPreviewProps = {
  title: string
  description?: string | null
  fields: PortalFormFieldOut[]
  className?: string
}

type FileValue = { file_id: string; filename: string }

function responseValue(responses: Record<string, unknown>, key: string): unknown {
  return responses[key]
}

function dropdownOptions(field: PortalFormFieldOut): string[] {
  if (field.field_type === 'select') {
    return (field.select_options ?? []).filter((o) => o.trim())
  }
  if ((field.field_type as string) === 'yes_no') {
    return ['Yes', 'No']
  }
  return []
}

function displaySelectValue(raw: unknown): string {
  if (raw === true) return 'Yes'
  if (raw === false) return 'No'
  return typeof raw === 'string' ? raw : ''
}

function fileFromResponse(raw: unknown): FileValue | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>
  if (!o.file_id) return null
  return { file_id: String(o.file_id), filename: String(o.filename || 'upload') }
}

function filesFromResponse(raw: unknown): FileValue[] {
  if (Array.isArray(raw)) {
    return raw.map(fileFromResponse).filter((x): x is FileValue => x != null)
  }
  const single = fileFromResponse(raw)
  return single ? [single] : []
}

function formatCompletedWhen(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fieldIsEmpty(field: PortalFormFieldOut, values: Record<string, unknown>): boolean {
  const v = values[field.field_key]
  if (field.field_type === 'checkbox') {
    return !(v === true || v === 'true' || v === 1)
  }
  if (field.field_type === 'file') {
    return !fileFromResponse(v)
  }
  if (field.field_type === 'files') {
    return filesFromResponse(v).length === 0
  }
  if (typeof v === 'string') return !v.trim()
  return v === undefined || v === null || v === ''
}

/** Collect required-field errors; keys are field_key. */
export function collectPortalFormFieldErrors(
  fields: PortalFormFieldOut[],
  values: Record<string, unknown>,
): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const f of fields) {
    if (f.field_type === 'section' || !f.required) continue
    if (fieldIsEmpty(f, values)) {
      errors[f.field_key] =
        f.field_type === 'checkbox' ? 'Please confirm this required item.' : 'This field is required.'
    }
  }
  return errors
}

type FieldsViewProps = {
  fields: PortalFormFieldOut[]
  values: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  fieldErrors: Record<string, string>
  disabled: boolean
  readOnly: boolean
  openSelectKey: string | null
  onOpenSelectChange: (key: string | null) => void
  uploadBusyKey?: string | null
  onUploadFile?: (field: PortalFormFieldOut, file: File) => void
  onRemoveFile?: (field: PortalFormFieldOut, fileId: string) => void
  responsesFallback?: Record<string, unknown>
  fieldRefs?: MutableRefObject<Record<string, HTMLElement | null>>
}

function PortalFormFieldsView({
  fields,
  values,
  onChange,
  fieldErrors,
  disabled,
  readOnly,
  openSelectKey,
  onOpenSelectChange,
  uploadBusyKey = null,
  onUploadFile,
  onRemoveFile,
  responsesFallback = {},
  fieldRefs,
}: FieldsViewProps) {
  const sorted = useMemo(() => [...fields].sort((a, b) => a.sort_order - b.sort_order), [fields])
  const controlsDisabled = disabled || readOnly

  function setRef(key: string, el: HTMLElement | null) {
    if (fieldRefs) fieldRefs.current[key] = el
  }

  function wrapError(fieldKey: string, node: ReactNode) {
    const msg = fieldErrors[fieldKey]
    return (
      <div
        key={fieldKey}
        ref={(el) => setRef(fieldKey, el)}
        className={msg ? 'portalFormFieldWrap portalFormFieldWrap--error' : 'portalFormFieldWrap'}
      >
        {node}
        {msg ? (
          <div className="error portalFormFieldError" role="alert">
            {msg}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <>
      {sorted.map((field) => {
        if (field.field_type === 'section') {
          return (
            <h3 key={field.field_key} style={{ margin: '16px 0 4px', fontSize: 16 }}>
              {field.label}
            </h3>
          )
        }

        const val = values[field.field_key]
        const help = field.help_text?.trim()
        const label = `${field.label}${field.required ? ' *' : ''}`
        const invalid = Boolean(fieldErrors[field.field_key])

        if (field.field_type === 'textarea') {
          return wrapError(
            field.field_key,
            <label className="field portalFormField">
              <span>{label}</span>
              {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
              <textarea
                className="input"
                rows={4}
                value={typeof val === 'string' ? val : ''}
                onChange={(e) => onChange(field.field_key, e.target.value)}
                disabled={controlsDisabled}
                readOnly={readOnly}
                aria-invalid={invalid}
              />
            </label>,
          )
        }

        if (field.field_type === 'date') {
          return wrapError(
            field.field_key,
            <label className="field portalFormField">
              <span>{label}</span>
              {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
              <input
                type="date"
                className="input"
                value={typeof val === 'string' ? val : ''}
                onChange={(e) => onChange(field.field_key, e.target.value)}
                disabled={controlsDisabled}
                readOnly={readOnly}
                aria-invalid={invalid}
              />
            </label>,
          )
        }

        if (field.field_type === 'select' || (field.field_type as string) === 'yes_no') {
          const options = dropdownOptions(field)
          const selected = displaySelectValue(val)
          return wrapError(
            field.field_key,
            <div className="field portalFormField">
              {help ? (
                <span className="muted" style={{ fontSize: 13, marginBottom: 6, display: 'block' }}>
                  {help}
                </span>
              ) : null}
              <SingleSelectDropdown
                label={label}
                options={options.map((opt) => ({ value: opt, label: opt }))}
                value={selected}
                onChange={(next) => onChange(field.field_key, next)}
                open={!readOnly && openSelectKey === field.field_key}
                onOpenChange={(open) => onOpenSelectChange(open ? field.field_key : null)}
                disabled={controlsDisabled || options.length === 0}
                placeholder={options.length === 0 ? 'No choices configured' : field.required ? 'Choose…' : '— None —'}
                emptyMessage="No choices configured"
              />
              {options.length === 0 ? (
                <div className="error" style={{ marginTop: 6, fontSize: 13 }}>
                  This question has no answer choices yet. Please contact your firm.
                </div>
              ) : null}
            </div>,
          )
        }

        if (field.field_type === 'checkbox') {
          const checked = val === true || val === 'true' || val === 1
          return wrapError(
            field.field_key,
            <label className="portalFormCheckboxField">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(field.field_key, e.target.checked)}
                disabled={controlsDisabled}
                aria-invalid={invalid}
              />
              <span className="portalFormCheckboxField__text">
                <span className="portalFormCheckboxField__label">{label}</span>
                {help ? <span className="muted portalFormCheckboxField__help">{help}</span> : null}
              </span>
            </label>,
          )
        }

        if (field.field_type === 'file') {
          const uploaded =
            fileFromResponse(val) ?? fileFromResponse(responseValue(responsesFallback, field.field_key))
          const uploading = uploadBusyKey === field.field_key
          return wrapError(
            field.field_key,
            <div className="field portalFormField">
              <span>{label}</span>
              {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
              {uploaded ? <div className="muted" style={{ fontSize: 13 }}>Uploaded: {uploaded.filename}</div> : null}
              {!readOnly ? (
                <label
                  className="btn"
                  style={{
                    cursor: uploading || disabled || !onUploadFile ? 'not-allowed' : 'pointer',
                    alignSelf: 'flex-start',
                    opacity: !onUploadFile ? 0.6 : 1,
                  }}
                >
                  {uploading ? 'Uploading…' : uploaded ? 'Replace file' : 'Choose file'}
                  <input
                    type="file"
                    hidden
                    disabled={disabled || uploading || !onUploadFile}
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file && onUploadFile) onUploadFile(field, file)
                      e.target.value = ''
                    }}
                  />
                </label>
              ) : null}
            </div>,
          )
        }

        if (field.field_type === 'files') {
          const uploaded =
            filesFromResponse(val).length > 0
              ? filesFromResponse(val)
              : filesFromResponse(responseValue(responsesFallback, field.field_key))
          const uploading = uploadBusyKey === field.field_key
          return wrapError(
            field.field_key,
            <div className="field portalFormField">
              <span>{label}</span>
              {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
              {uploaded.length ? (
                <ul style={{ margin: '6px 0', paddingLeft: 18, fontSize: 13 }}>
                  {uploaded.map((f) => (
                    <li key={f.file_id} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                      <span className="muted">{f.filename}</span>
                      {!readOnly && onRemoveFile ? (
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: '2px 8px', fontSize: 12 }}
                          disabled={disabled || uploading}
                          onClick={() => onRemoveFile(field, f.file_id)}
                        >
                          Remove
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {!readOnly ? (
                <label
                  className="btn"
                  style={{
                    cursor: uploading || disabled || !onUploadFile ? 'not-allowed' : 'pointer',
                    alignSelf: 'flex-start',
                    opacity: !onUploadFile ? 0.6 : 1,
                  }}
                >
                  {uploading ? 'Uploading…' : 'Add file'}
                  <input
                    type="file"
                    hidden
                    disabled={disabled || uploading || !onUploadFile}
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file && onUploadFile) onUploadFile(field, file)
                      e.target.value = ''
                    }}
                  />
                </label>
              ) : null}
            </div>,
          )
        }

        return wrapError(
          field.field_key,
          <label className="field portalFormField">
            <span>{label}</span>
            {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
            <input
              className="input"
              value={typeof val === 'string' ? val : ''}
              onChange={(e) => onChange(field.field_key, e.target.value)}
              disabled={controlsDisabled}
              readOnly={readOnly}
              aria-invalid={invalid}
            />
          </label>,
        )
      })}
    </>
  )
}

/** Interactive client-style preview for the admin form builder (native controls). */
export function PortalFormLocalPreview({ title, description, fields, className }: PortalFormLocalPreviewProps) {
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [summary, setSummary] = useState<string | null>(null)
  const [validationActive, setValidationActive] = useState(false)
  const sorted = useMemo(() => [...fields].sort((a, b) => a.sort_order - b.sort_order), [fields])

  useEffect(() => {
    if (!validationActive) return
    const remaining = collectPortalFormFieldErrors(fields, values)
    setFieldErrors(remaining)
    const n = Object.keys(remaining).length
    setSummary(
      n > 0
        ? `Please complete ${n} required field${n === 1 ? '' : 's'}.`
        : 'All required fields look complete.',
    )
  }, [validationActive, fields, values])

  function setFieldValue(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  function checkRequired() {
    setValidationActive(true)
    const errors = collectPortalFormFieldErrors(fields, values)
    setFieldErrors(errors)
    const n = Object.keys(errors).length
    setSummary(n > 0 ? `Please complete ${n} required field${n === 1 ? '' : 's'}.` : 'All required fields look complete.')
  }

  return (
    <div
      className={`portalFormBuilderPreview ${className ?? 'card'}`}
      style={{ padding: 14, background: 'var(--panel2, rgba(15,23,42,0.03))', border: '1px solid var(--border, #e2e8f0)' }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Live client preview</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        Working controls — change answers, open dropdowns, and run the required-field check below.
      </div>
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>{title || 'Untitled form'}</h3>
      {description?.trim() ? <p style={{ margin: '0 0 10px' }}>{description.trim()}</p> : null}
      {summary ? (
        <div className={summary.startsWith('All required') ? 'notice' : 'error'} style={{ marginBottom: 10 }}>
          {summary}
        </div>
      ) : null}
      <div className="stack portalFormFields" style={{ gap: 10 }}>
        {sorted.map((field) => {
          if (field.field_type === 'section') {
            return (
              <h4 key={field.field_key} style={{ margin: '8px 0 0', fontSize: 15 }}>
                {field.label || 'Section'}
              </h4>
            )
          }
          const label = `${field.label || 'Untitled field'}${field.required ? ' *' : ''}`
          const help = field.help_text?.trim()
          const val = values[field.field_key]
          const err = fieldErrors[field.field_key]
          const wrapClass = err ? 'portalFormFieldWrap portalFormFieldWrap--error' : 'portalFormFieldWrap'

          if (field.field_type === 'checkbox') {
            const checked = val === true || val === 'true' || val === 1
            return (
              <div key={field.field_key} className={wrapClass}>
                <label className="portalFormCheckboxField">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => setFieldValue(field.field_key, e.target.checked)}
                  />
                  <span className="portalFormCheckboxField__text">
                    <span className="portalFormCheckboxField__label">{label}</span>
                    {help ? <span className="muted portalFormCheckboxField__help">{help}</span> : null}
                  </span>
                </label>
                {err ? <div className="error portalFormFieldError">{err}</div> : null}
              </div>
            )
          }

          if (field.field_type === 'select' || (field.field_type as string) === 'yes_no') {
            const options = dropdownOptions(field)
            return (
              <div key={field.field_key} className={wrapClass}>
                <label className="field portalFormField">
                  <span>{label}</span>
                  {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
                  <select
                    className="input"
                    value={displaySelectValue(val)}
                    onChange={(e) => setFieldValue(field.field_key, e.target.value)}
                  >
                    <option value="">{options.length ? 'Choose…' : 'No choices configured'}</option>
                    {options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </label>
                {err ? <div className="error portalFormFieldError">{err}</div> : null}
              </div>
            )
          }

          if (field.field_type === 'textarea') {
            return (
              <div key={field.field_key} className={wrapClass}>
                <label className="field portalFormField">
                  <span>{label}</span>
                  {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
                  <textarea
                    className="input"
                    rows={3}
                    value={typeof val === 'string' ? val : ''}
                    onChange={(e) => setFieldValue(field.field_key, e.target.value)}
                  />
                </label>
                {err ? <div className="error portalFormFieldError">{err}</div> : null}
              </div>
            )
          }

          if (field.field_type === 'date') {
            return (
              <div key={field.field_key} className={wrapClass}>
                <label className="field portalFormField">
                  <span>{label}</span>
                  {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
                  <input
                    type="date"
                    className="input"
                    value={typeof val === 'string' ? val : ''}
                    onChange={(e) => setFieldValue(field.field_key, e.target.value)}
                  />
                </label>
                {err ? <div className="error portalFormFieldError">{err}</div> : null}
              </div>
            )
          }

          if (field.field_type === 'file' || field.field_type === 'files') {
            return (
              <div key={field.field_key} className={wrapClass}>
                <label className="field portalFormField">
                  <span>{label}</span>
                  {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
                  <input type="file" className="input" disabled multiple={field.field_type === 'files'} />
                  <span className="muted" style={{ fontSize: 12 }}>
                    File upload is available when clients complete the form (disabled in builder preview).
                  </span>
                </label>
              </div>
            )
          }

          return (
            <div key={field.field_key} className={wrapClass}>
              <label className="field portalFormField">
                <span>{label}</span>
                {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
                <input
                  className="input"
                  value={typeof val === 'string' ? val : ''}
                  onChange={(e) => setFieldValue(field.field_key, e.target.value)}
                />
              </label>
              {err ? <div className="error portalFormFieldError">{err}</div> : null}
            </div>
          )
        })}
        <button type="button" className="btn" style={{ alignSelf: 'flex-start' }} onClick={checkRequired}>
          Check required fields
        </button>
      </div>
    </div>
  )
}

async function portalDownloadFile(path: string, portalToken: string, fallbackName: string) {
  const headers = new Headers()
  applyAuthHeaders(headers, portalToken)
  const res = await fetch(apiUrl(path), { headers })
  if (!res.ok) {
    const body = await res.text()
    let parsed: unknown = body
    try {
      parsed = JSON.parse(body)
    } catch {
      /* keep text */
    }
    throw new Error(formatApiErrorDetail(parsed, res.statusText, apiUrl(path)))
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd)
  const name = match ? decodeURIComponent(match[1].replace(/"/g, '')) : fallbackName
  triggerBlobDownload(blob, name || fallbackName)
}

export function PortalFormFillPanel({ submissionId, portalToken, onBack, onSubmitted, previewMode = false }: Props) {
  const [form, setForm] = useState<PortalFormDetailOut | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [busy, setBusy] = useState(false)
  const [uploadBusyKey, setUploadBusyKey] = useState<string | null>(null)
  const [openSelectKey, setOpenSelectKey] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [validationActive, setValidationActive] = useState(false)
  const fieldRefs = useRef<Record<string, HTMLElement | null>>({})

  const status = (form?.status || '').toLowerCase()
  const isCompleted = status === 'completed'
  const isReadOnly = isCompleted || status === 'voided' || status === 'superseded' || previewMode
  const canSubmit = Boolean(form) && status === 'pending' && !previewMode

  useEffect(() => {
    if (!validationActive || !form) return
    const remaining = collectPortalFormFieldErrors(form.fields, values)
    setFieldErrors(remaining)
    const n = Object.keys(remaining).length
    setErr(n > 0 ? `Please complete ${n} required field${n === 1 ? '' : 's'}.` : null)
  }, [validationActive, form, values])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setBusy(true)
      setErr(null)
      setFieldErrors({})
      setValidationActive(false)
      try {
        const headers = new Headers()
        applyAuthHeaders(headers, portalToken)
        const res = await fetch(apiUrl(`/portal/forms/${submissionId}`), { headers })
        const text = await res.text()
        let parsed: unknown = text
        try {
          parsed = JSON.parse(text)
        } catch {
          /* keep text */
        }
        if (!res.ok) throw new Error(formatApiErrorDetail(parsed, res.statusText))
        const detail = parsed as PortalFormDetailOut
        if (cancelled) return
        setForm(detail)
        const initial: Record<string, unknown> = {}
        for (const f of detail.fields) {
          if (f.field_type === 'section') continue
          const existing = detail.responses?.[f.field_key]
          if (existing !== undefined) initial[f.field_key] = existing
        }
        setValues(initial)
      } catch (e: unknown) {
        if (!cancelled) setErr((e as { message?: string }).message ?? 'Could not load form')
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [submissionId, portalToken])

  function setFieldValue(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  function focusFirstError(errors: Record<string, string>) {
    const firstKey = Object.keys(errors)[0]
    if (!firstKey) return
    const el = fieldRefs.current[firstKey]
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const focusable = el.querySelector<HTMLElement>('input, textarea, button, select, [tabindex]')
    focusable?.focus()
  }

  async function uploadFile(field: PortalFormFieldOut, file: File) {
    if (previewMode || isReadOnly) return
    setUploadBusyKey(field.field_key)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', file)
      const headers = new Headers()
      applyAuthHeaders(headers, portalToken)
      const url = apiUrl(`/portal/forms/${submissionId}/upload?field_key=${encodeURIComponent(field.field_key)}`)
      const res = await fetch(url, { method: 'POST', headers, body: fd })
      const text = await res.text()
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        /* keep text */
      }
      if (!res.ok) throw new Error(formatApiErrorDetail(parsed, res.statusText))
      const out = parsed as FileValue & { files?: FileValue[] }
      if (field.field_type === 'files' && Array.isArray(out.files)) {
        setFieldValue(field.field_key, out.files)
      } else {
        setFieldValue(field.field_key, { file_id: out.file_id, filename: out.filename })
      }
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Upload failed')
    } finally {
      setUploadBusyKey(null)
    }
  }

  async function removeUploadedFile(field: PortalFormFieldOut, fileId: string) {
    if (previewMode || isReadOnly || field.field_type !== 'files') return
    setUploadBusyKey(field.field_key)
    setErr(null)
    try {
      const headers = new Headers()
      applyAuthHeaders(headers, portalToken)
      const url = apiUrl(
        `/portal/forms/${submissionId}/upload?field_key=${encodeURIComponent(field.field_key)}&file_id=${encodeURIComponent(fileId)}`,
      )
      const res = await fetch(url, { method: 'DELETE', headers })
      const text = await res.text()
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        /* keep text */
      }
      if (!res.ok) throw new Error(formatApiErrorDetail(parsed, res.statusText))
      const out = parsed as { files?: FileValue[] }
      setFieldValue(field.field_key, Array.isArray(out.files) ? out.files : [])
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not remove file')
    } finally {
      setUploadBusyKey(null)
    }
  }

  async function downloadSnapshot() {
    setBusy(true)
    setErr(null)
    try {
      await portalDownloadFile(
        `/portal/forms/${submissionId}/snapshot`,
        portalToken,
        form?.snapshot_filename || 'completed-form.docx',
      )
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not download completed form')
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (!form || !canSubmit) return
    const errors = collectPortalFormFieldErrors(form.fields, values)
    if (Object.keys(errors).length > 0) {
      setValidationActive(true)
      setFieldErrors(errors)
      setErr(`Please complete ${Object.keys(errors).length} required field${Object.keys(errors).length === 1 ? '' : 's'}.`)
      focusFirstError(errors)
      return
    }
    setBusy(true)
    setErr(null)
    setFieldErrors({})
    setValidationActive(false)
    try {
      const payload: Record<string, unknown> = {}
      for (const f of form.fields) {
        if (f.field_type === 'section' || f.field_type === 'file' || f.field_type === 'files') continue
        if (f.field_type === 'checkbox') {
          payload[f.field_key] = Boolean(values[f.field_key])
          continue
        }
        const v = values[f.field_key]
        // Always send date/text when present (including date) so values persist reliably.
        if (v !== undefined && v !== null && v !== '') payload[f.field_key] = v
      }
      const headers = new Headers({ 'Content-Type': 'application/json' })
      applyAuthHeaders(headers, portalToken)
      const res = await fetch(apiUrl(`/portal/forms/${submissionId}/submit`), {
        method: 'POST',
        headers,
        body: JSON.stringify({ responses: payload }),
      })
      const text = await res.text()
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        /* keep text */
      }
      if (!res.ok) throw new Error(formatApiErrorDetail(parsed, res.statusText))
      onSubmitted()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not submit form')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="portalFormFill card" style={{ marginTop: 16, padding: 16 }}>
      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <button type="button" className="btn" disabled={busy} onClick={onBack}>
          ← Back
        </button>
        <h2 style={{ margin: 0, flex: 1, fontSize: 18 }}>{form?.template_name ?? 'Form'}</h2>
        {isCompleted ? (
          <span className="portalActionBadge portalActionBadge--complete">Completed</span>
        ) : null}
        {status === 'voided' ? (
          <span className="portalActionBadge portalActionBadge--cancelled">Voided</span>
        ) : null}
        {status === 'superseded' ? (
          <span className="portalActionBadge portalActionBadge--expired">Superseded</span>
        ) : null}
      </div>
      {form?.description?.trim() ? <p className="muted">{form.description.trim()}</p> : null}

      {isCompleted ? (
        <div className="notice" style={{ marginBottom: 12 }}>
          <div>
            Submitted
            {form?.completed_at ? ` on ${formatCompletedWhen(form.completed_at)}` : ''}. Your answers below are
            read-only.
          </div>
          {form?.snapshot_file_id ? (
            <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void downloadSnapshot()}>
                Download completed form
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {status === 'voided' || status === 'superseded' ? (
        <div className="muted" style={{ marginBottom: 12, fontSize: 14 }}>
          This form is no longer active. Answers are shown for your records where available.
        </div>
      ) : null}

      {err ? <div className="error">{err}</div> : null}
      {busy && !form ? <div className="muted">Loading form…</div> : null}
      {form ? (
        <div className="stack portalFormFields" style={{ gap: 10 }}>
          <PortalFormFieldsView
            fields={form.fields}
            values={values}
            onChange={setFieldValue}
            fieldErrors={fieldErrors}
            disabled={busy}
            readOnly={isReadOnly}
            openSelectKey={openSelectKey}
            onOpenSelectChange={setOpenSelectKey}
            uploadBusyKey={uploadBusyKey}
            onUploadFile={canSubmit ? (f, file) => void uploadFile(f, file) : undefined}
            onRemoveFile={canSubmit ? (f, id) => void removeUploadedFile(f, id) : undefined}
            responsesFallback={form.responses || {}}
            fieldRefs={fieldRefs}
          />
          {previewMode ? (
            <p className="muted" style={{ margin: '8px 0 0' }}>
              Form submission is disabled in preview mode.
            </p>
          ) : canSubmit ? (
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy || uploadBusyKey !== null}
                onClick={() => void submit()}
              >
                {busy ? 'Submitting…' : 'Submit form'}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
