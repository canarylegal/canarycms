import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { useDialogs } from './DialogProvider'
import { TextPromptModal } from './TextPromptModal'
import type { CaseSourceOut, UserPublic } from './types'
import { userCanAccessAdminConsole } from './types'

type Props = {
  token: string
  me: UserPublic | null | undefined
  onBack: () => void
}

type PromptState =
  | { mode: 'add' }
  | { mode: 'edit'; row: CaseSourceOut }
  | null

export function QuoteSourcesPanel({ token, me, onBack }: Props) {
  const { askConfirm } = useDialogs()
  const canAdmin = userCanAccessAdminConsole(me)
  const [rows, setRows] = useState<CaseSourceOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<PromptState>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const data = await apiFetch<CaseSourceOut[]>('/case-sources', { token })
      setRows(data)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load sources')
    } finally {
      setBusy(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  async function savePrompt(name: string) {
    if (!prompt) return
    const trimmed = name.trim()
    if (!trimmed) return
    setBusy(true)
    setErr(null)
    try {
      if (prompt.mode === 'add') {
        await apiFetch<CaseSourceOut>('/case-sources', { token, method: 'POST', json: { name: trimmed } })
      } else {
        await apiFetch<CaseSourceOut>(`/case-sources/${prompt.row.id}`, {
          token,
          method: 'PATCH',
          json: { name: trimmed },
        })
      }
      setPrompt(null)
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save source')
      setBusy(false)
    }
  }

  async function removeSource(row: CaseSourceOut) {
    if (!canAdmin || row.is_system) return
    const ok = await askConfirm({
      title: 'Remove source',
      message: `Remove “${row.name}”? Cases using this source will show no source until updated.`,
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/case-sources/${row.id}`, { token, method: 'DELETE' })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not remove source')
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ padding: 16, maxWidth: 720, margin: '0 auto' }}>
      <div className="row" style={{ alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn" onClick={onBack} disabled={busy}>
          ← Quotes
        </button>
        <h2 style={{ margin: 0, flex: 1 }}>Sources</h2>
        <button type="button" className="btn primary" disabled={busy} onClick={() => setPrompt({ mode: 'add' })}>
          Add source
        </button>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Track where work came from. Anyone can add a source; only administrators can rename or remove custom sources.
        Built-in sources cannot be changed.
      </p>
      {err ? <div className="error">{err}</div> : null}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: '1fr 140px' }}>
            <div className="thCell">Name</div>
            <div className="thCell">Actions</div>
          </div>
          {rows.map((row) => (
            <div key={row.id} className="tr" style={{ gridTemplateColumns: '1fr 140px' }}>
              <div className="td">{row.name}</div>
              <div className="td row" style={{ gap: 6, flexWrap: 'wrap' }}>
                {canAdmin && !row.is_system ? (
                  <>
                    <button type="button" className="btn" disabled={busy} onClick={() => setPrompt({ mode: 'edit', row })}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => void removeSource(row)}
                    >
                      Remove
                    </button>
                  </>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </div>
          ))}
          {rows.length === 0 && !busy ? <div className="muted" style={{ padding: 12 }}>No sources yet.</div> : null}
        </div>
      </div>
      {prompt ? (
        <TextPromptModal
          title={prompt.mode === 'add' ? 'Add source' : 'Rename source'}
          fieldLabel="Source name"
          initial={prompt.mode === 'edit' ? prompt.row.name : ''}
          confirmLabel={prompt.mode === 'add' ? 'Add' : 'Save'}
          busy={busy}
          onCancel={() => setPrompt(null)}
          onConfirm={(value) => void savePrompt(value)}
        />
      ) : null}
    </div>
  )
}
