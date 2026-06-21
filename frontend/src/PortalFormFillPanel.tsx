import { useEffect, useMemo, useState } from 'react'
import { applyAuthHeaders, apiUrl, formatApiErrorDetail } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { PortalFormDetailOut, PortalFormFieldOut } from './types'

type Props = {
  submissionId: string
  portalToken: string
  onBack: () => void
  onSubmitted: () => void
  previewMode?: boolean
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
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (!o.file_id) return null
  return { file_id: String(o.file_id), filename: String(o.filename || 'upload') }
}

export function PortalFormFillPanel({ submissionId, portalToken, onBack, onSubmitted, previewMode = false }: Props) {
  const [form, setForm] = useState<PortalFormDetailOut | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [busy, setBusy] = useState(false)
  const [uploadBusyKey, setUploadBusyKey] = useState<string | null>(null)
  const [openSelectKey, setOpenSelectKey] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const sortedFields = useMemo(() => {
    if (!form) return []
    return [...form.fields].sort((a, b) => a.sort_order - b.sort_order)
  }, [form])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setBusy(true)
      setErr(null)
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

  async function uploadFile(field: PortalFormFieldOut, file: File) {
    if (previewMode) return
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
      const out = parsed as FileValue
      setFieldValue(field.field_key, { file_id: out.file_id, filename: out.filename })
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Upload failed')
    } finally {
      setUploadBusyKey(null)
    }
  }

  async function submit() {
    if (!form) return
    setBusy(true)
    setErr(null)
    try {
      const payload: Record<string, unknown> = {}
      for (const f of form.fields) {
        if (f.field_type === 'section' || f.field_type === 'file') continue
        const v = values[f.field_key]
        if (v !== undefined && v !== '') payload[f.field_key] = v
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

  function renderField(field: PortalFormFieldOut) {
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

    if (field.field_type === 'textarea') {
      return (
        <label key={field.field_key} className="field portalFormField">
          <span>{label}</span>
          {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
          <textarea
            className="input"
            rows={4}
            value={typeof val === 'string' ? val : ''}
            onChange={(e) => setFieldValue(field.field_key, e.target.value)}
            disabled={busy}
          />
        </label>
      )
    }

    if (field.field_type === 'date') {
      return (
        <label key={field.field_key} className="field portalFormField">
          <span>{label}</span>
          {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
          <input
            type="date"
            className="input"
            value={typeof val === 'string' ? val : ''}
            onChange={(e) => setFieldValue(field.field_key, e.target.value)}
            disabled={busy}
          />
        </label>
      )
    }

    if (field.field_type === 'select' || (field.field_type as string) === 'yes_no') {
      const options = dropdownOptions(field)
      const selected = displaySelectValue(val)
      return (
        <div key={field.field_key} className="field portalFormField">
          {help ? <span className="muted" style={{ fontSize: 13, marginBottom: 6, display: 'block' }}>{help}</span> : null}
          <SingleSelectDropdown
            label={label}
            options={options.map((opt) => ({ value: opt, label: opt }))}
            value={selected}
            onChange={(next) => setFieldValue(field.field_key, next)}
            open={openSelectKey === field.field_key}
            onOpenChange={(open) => setOpenSelectKey(open ? field.field_key : null)}
            disabled={busy || options.length === 0}
            placeholder={options.length === 0 ? 'No choices configured' : field.required ? 'Choose…' : '— None —'}
            emptyMessage="No choices configured"
          />
          {options.length === 0 ? (
            <div className="error" style={{ marginTop: 6, fontSize: 13 }}>
              This question has no answer choices yet. Please contact your firm.
            </div>
          ) : null}
        </div>
      )
    }

    if (field.field_type === 'file') {
      const uploaded = fileFromResponse(val) ?? fileFromResponse(responseValue(form?.responses ?? {}, field.field_key))
      const uploading = uploadBusyKey === field.field_key
      return (
        <div key={field.field_key} className="field portalFormField">
          <span>{label}</span>
          {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
          {uploaded ? <div className="muted" style={{ fontSize: 13 }}>Uploaded: {uploaded.filename}</div> : null}
          <label className="btn" style={{ cursor: uploading || busy || previewMode ? 'not-allowed' : 'pointer', alignSelf: 'flex-start', opacity: previewMode ? 0.6 : 1 }}>
            {uploading ? 'Uploading…' : uploaded ? 'Replace file' : 'Choose file'}
            <input
              type="file"
              hidden
              disabled={busy || uploading || previewMode}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void uploadFile(field, file)
                e.target.value = ''
              }}
            />
          </label>
        </div>
      )
    }

    return (
      <label key={field.field_key} className="field portalFormField">
        <span>{label}</span>
        {help ? <span className="muted" style={{ fontSize: 13 }}>{help}</span> : null}
        <input
          className="input"
          value={typeof val === 'string' ? val : ''}
          onChange={(e) => setFieldValue(field.field_key, e.target.value)}
          disabled={busy}
        />
      </label>
    )
  }

  return (
    <div className="portalFormFill card" style={{ marginTop: 16, padding: 16 }}>
      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <button type="button" className="btn" disabled={busy} onClick={onBack}>
          ← Back
        </button>
        <h2 style={{ margin: 0, flex: 1, fontSize: 18 }}>{form?.template_name ?? 'Form'}</h2>
      </div>
      {form?.description?.trim() ? <p className="muted">{form.description.trim()}</p> : null}
      {err ? <div className="error">{err}</div> : null}
      {busy && !form ? <div className="muted">Loading form…</div> : null}
      {form ? (
        <div className="stack portalFormFields" style={{ gap: 10 }}>
          {sortedFields.map((f) => renderField(f))}
          {previewMode ? (
            <p className="muted" style={{ margin: '8px 0 0' }}>
              Form submission is disabled in preview mode.
            </p>
          ) : (
            <div className="row" style={{ gap: 8, marginTop: 8 }}>
              <button type="button" className="btn primary" disabled={busy || uploadBusyKey !== null} onClick={() => void submit()}>
                {busy ? 'Submitting…' : 'Submit form'}
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
