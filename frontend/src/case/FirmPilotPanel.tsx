import { useCallback, useEffect, useState } from 'react'
import { apiFetch, type ApiError } from '../api'

type AttrField = { key: string; label: string; type?: string }
type ChecklistItem = { key: string; label: string; done: boolean }

type Manifest = {
  enabled: boolean
  module_id?: string | null
  label?: string | null
  panel_label?: string | null
  stages?: string[]
  attr_fields?: AttrField[]
}

type CaseState = {
  module_id: string
  case_id: string
  stage: string
  stages: string[]
  checklist: ChecklistItem[]
  attrs: Record<string, string>
  integration: { stub?: string; last_event?: unknown }
}

export function FirmPilotPanel({
  caseId,
  token,
  onBack,
}: {
  caseId: string
  token: string
  onBack: () => void
}) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [state, setState] = useState<CaseState | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    setErr(null)
    try {
      const m = await apiFetch<Manifest>('/firm-modules/active', { token })
      setManifest(m)
      if (!m.enabled) {
        setState(null)
        return
      }
      const s = await apiFetch<CaseState>(`/firm-modules/active/matters/${caseId}`, { token })
      setState(s)
    } catch (e) {
      setState(null)
      setErr((e as ApiError).message ?? 'Could not load firm module')
    }
  }, [caseId, token])

  useEffect(() => {
    void load()
  }, [load])

  async function save() {
    if (!state) return
    setBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const out = await apiFetch<CaseState>(`/firm-modules/active/matters/${caseId}`, {
        token,
        method: 'PUT',
        json: {
          stage: state.stage,
          checklist: state.checklist,
          attrs: state.attrs,
        },
      })
      setState(out)
      setSaved(true)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const title = manifest?.panel_label || manifest?.label || 'Firm module'

  return (
    <div className="stack" style={{ padding: 12, gap: 12 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <button type="button" className="btn" onClick={onBack}>
          Back
        </button>
      </div>
      <div className="muted" style={{ fontSize: 13 }}>
        Phase 3 stand-in firm module (config from firm package). Not Rhodes &amp; Walker production content.
      </div>
      {err ? <div className="error">{err}</div> : null}
      {saved ? <div className="muted">Saved.</div> : null}
      {!manifest?.enabled ? (
        <div className="muted">No firm module attached (set FIRM_MODULE_DIR / firm package).</div>
      ) : !state ? (
        <div className="muted">Loading… or this matter type is outside the module scope.</div>
      ) : (
        <>
          <label className="field">
            <span>Stage</span>
            <select
              value={state.stage}
              disabled={busy}
              onChange={(e) => setState({ ...state, stage: e.target.value })}
            >
              {(state.stages.length ? state.stages : ['']).map((s) => (
                <option key={s || '_'} value={s}>
                  {s || '—'}
                </option>
              ))}
            </select>
          </label>
          <div style={{ fontWeight: 600 }}>Checklist</div>
          <div className="stack" style={{ gap: 6 }}>
            {state.checklist.map((item, idx) => (
              <label key={item.key || idx} className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="checkbox"
                  checked={Boolean(item.done)}
                  disabled={busy}
                  onChange={(e) => {
                    const checklist = state.checklist.map((c, i) =>
                      i === idx ? { ...c, done: e.target.checked } : c,
                    )
                    setState({ ...state, checklist })
                  }}
                />
                <span>{item.label}</span>
              </label>
            ))}
          </div>
          <div style={{ fontWeight: 600 }}>Extra fields</div>
          {(manifest.attr_fields || []).map((f) => (
            <label key={f.key} className="field">
              <span>{f.label || f.key}</span>
              <input
                value={state.attrs[f.key] ?? ''}
                disabled={busy}
                onChange={(e) =>
                  setState({ ...state, attrs: { ...state.attrs, [f.key]: e.target.value } })
                }
              />
            </label>
          ))}
          <div className="muted" style={{ fontSize: 12 }}>
            Integration stub: {state.integration?.stub || 'log_only'}
            {state.integration?.last_event ? ' · matter.created handled' : ''}
          </div>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
            Save
          </button>
        </>
      )}
    </div>
  )
}
