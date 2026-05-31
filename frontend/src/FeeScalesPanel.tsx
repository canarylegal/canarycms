import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { FeeScaleEditor } from './FeeScaleEditor'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { GLOBAL_PRECEDENT_SCOPE, type FeeScaleDetailOut, type FeeScaleOut, type MatterHeadTypeOut } from './types'

function randomHexRef(): string {
  const bytes = new Uint8Array(3)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function scopeToApiPayload(headId: string, subId: string): {
  matter_head_type_id: string | null
  matter_sub_type_id: string | null
} {
  if (!headId || headId === GLOBAL_PRECEDENT_SCOPE) {
    return { matter_head_type_id: null, matter_sub_type_id: null }
  }
  if (!subId || subId === GLOBAL_PRECEDENT_SCOPE) {
    return { matter_head_type_id: headId, matter_sub_type_id: null }
  }
  return { matter_head_type_id: headId, matter_sub_type_id: subId }
}

function subTypeOptionsForHead(matterHeads: MatterHeadTypeOut[], headTypeId: string) {
  if (!headTypeId || headTypeId === GLOBAL_PRECEDENT_SCOPE) return []
  const h = matterHeads.find((x) => x.id === headTypeId)
  return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
}

function MatterScopeFields({
  headTypeId,
  subTypeId,
  headIsGlobal,
  matterTypeOptions,
  subTypeOptions,
  matterTypesReady,
  disabled,
  onHeadChange,
  onSubChange,
}: {
  headTypeId: string
  subTypeId: string
  headIsGlobal: boolean
  matterTypeOptions: { id: string; label: string }[]
  subTypeOptions: { id: string; label: string }[]
  matterTypesReady: boolean
  disabled?: boolean
  onHeadChange: (v: string) => void
  onSubChange: (v: string) => void
}) {
  const [headOpen, setHeadOpen] = useState(false)
  const [subOpen, setSubOpen] = useState(false)

  const headDropdownOptions = useMemo(
    () => [
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all cases)' },
      ...matterTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ],
    [matterTypeOptions],
  )

  const subDropdownOptions = useMemo(
    () => [
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'All sub-types under this matter type' },
      ...subTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ],
    [subTypeOptions],
  )

  return (
    <>
      <SingleSelectDropdown
        label="Matter type"
        options={headDropdownOptions}
        value={headTypeId}
        onChange={(v) => {
          onHeadChange(v)
          setSubOpen(false)
        }}
        open={headOpen}
        onOpenChange={setHeadOpen}
        disabled={disabled || !matterTypesReady}
        placeholder="Choose…"
        emptyMessage={
          matterTypesReady && matterTypeOptions.length === 0
            ? 'No matter types available — add them under Admin → Matters.'
            : undefined
        }
      />
      {headTypeId && !headIsGlobal ? (
        <SingleSelectDropdown
          label="Sub-type"
          options={subDropdownOptions}
          value={subTypeId}
          onChange={onSubChange}
          open={subOpen}
          onOpenChange={setSubOpen}
          disabled={disabled || !matterTypesReady}
          placeholder="Choose…"
          emptyMessage={
            subTypeOptions.length === 0
              ? 'No sub-types for this matter type — add them under Admin → Matters.'
              : undefined
          }
        />
      ) : headTypeId && headIsGlobal ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          This fee scale applies to all matter types.
        </p>
      ) : (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Choose a matter type, then pick a sub-type (or “All sub-types”).
        </p>
      )}
    </>
  )
}

export function FeeScalesPanel({ token, onBack }: { token: string; onBack: () => void }) {
  const { askConfirm } = useDialogs()
  const [items, setItems] = useState<FeeScaleOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [matterTypesReady, setMatterTypesReady] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [editSetupMode, setEditSetupMode] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createRef, setCreateRef] = useState(() => randomHexRef())
  const [createHeadId, setCreateHeadId] = useState('')
  const [createSubId, setCreateSubId] = useState('')

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )
  const createSubOptions = useMemo(
    () => subTypeOptionsForHead(matterHeads, createHeadId),
    [matterHeads, createHeadId],
  )
  const createHeadIsGlobal = createHeadId === GLOBAL_PRECEDENT_SCOPE
  const createScopeComplete = useMemo(() => {
    if (!createHeadId) return false
    if (createHeadIsGlobal) return true
    return Boolean(createSubId)
  }, [createHeadId, createHeadIsGlobal, createSubId])

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<FeeScaleOut[]>('/fee-scales', { token })
      setItems(Array.isArray(data) ? data : [])
      setErr(null)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not load fee scales')
    }
  }, [token])

  useEffect(() => {
    void load()
    setMatterTypesReady(false)
    void apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
      .then((d) => {
        setMatterHeads(Array.isArray(d) ? d : [])
        setErr(null)
      })
      .catch((e: unknown) => {
        setMatterHeads([])
        setErr((e as { message?: string }).message ?? 'Could not load matter types')
      })
      .finally(() => setMatterTypesReady(true))
  }, [load, token])

  useEffect(() => {
    if (createHeadId === GLOBAL_PRECEDENT_SCOPE) setCreateSubId(GLOBAL_PRECEDENT_SCOPE)
  }, [createHeadId])

  async function createScale() {
    if (!createName.trim() || !createScopeComplete) {
      setErr('Enter a name and choose scope before creating.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const created = await apiFetch<FeeScaleDetailOut>('/fee-scales', {
        token,
        method: 'POST',
        json: {
          name: createName.trim(),
          reference: createRef.trim() || randomHexRef(),
          ...scopeToApiPayload(createHeadId, createSubId),
        },
      })
      setCreateName('')
      setCreateRef(randomHexRef())
      setCreateHeadId('')
      setCreateSubId('')
      setEditId(created.id)
      setEditSetupMode(true)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not create fee scale')
    } finally {
      setBusy(false)
    }
  }

  if (editId) {
    return (
      <div className="mainMenuShell mainMenuShell--mainMenu">
        <FeeScaleEditor
          token={token}
          scaleId={editId}
          setupMode={editSetupMode}
          onBack={() => {
            setEditId(null)
            setEditSetupMode(false)
            void load()
          }}
        />
      </div>
    )
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="paneHead" style={{ marginBottom: 12 }}>
        <button type="button" className="btn" onClick={onBack}>
          ← Quotes
        </button>
        <h2 style={{ margin: '8px 0 0', fontSize: 18 }}>Fee scales</h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>
          Configure quote fee tables in Canary — categories, line items, value bands, VAT and totals. Quotes are
          generated as Word documents on your quote letterhead.
        </p>
      </div>
      {err ? <div className="error">{err}</div> : null}

      <div className="card stack" style={{ marginBottom: 16, padding: 12 }}>
        <h4 style={{ margin: 0 }}>New fee scale</h4>
        <label className="field">
          <span>Name</span>
          <input className="input" value={createName} onChange={(e) => setCreateName(e.target.value)} />
        </label>
        <label className="field">
          <span>Reference</span>
          <input className="input" value={createRef} onChange={(e) => setCreateRef(e.target.value)} />
        </label>
        <MatterScopeFields
          headTypeId={createHeadId}
          subTypeId={createSubId}
          headIsGlobal={createHeadIsGlobal}
          matterTypeOptions={matterTypeOptions}
          subTypeOptions={createSubOptions}
          matterTypesReady={matterTypesReady}
          disabled={busy}
          onHeadChange={(v) => {
            setCreateHeadId(v)
            setCreateSubId('')
          }}
          onSubChange={setCreateSubId}
        />
        <button type="button" className="btn primary" disabled={busy || !createScopeComplete} onClick={() => void createScale()}>
          Create &amp; set up…
        </button>
        {createHeadId && !createHeadIsGlobal && !createSubId ? (
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            Select a sub-type (or “All sub-types under this matter type”) to enable Create.
          </p>
        ) : null}
      </div>

      <div className="list">
        {items.map((p) => (
          <div key={p.id} className="listCard row" style={{ justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div className="listTitle">{p.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                {p.reference}
                {p.scope_summary ? ` · ${p.scope_summary}` : ''}
              </div>
            </div>
            <div className="row" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  setEditSetupMode(false)
                  setEditId(p.id)
                }}
              >
                Edit
              </button>
              <button
                type="button"
                className="btn danger"
                disabled={busy}
                onClick={() => {
                  void askConfirm({
                    title: 'Delete fee scale',
                    message: `Delete “${p.name}”?`,
                    confirmLabel: 'Delete',
                    danger: true,
                  }).then((ok) => {
                    if (!ok) return
                    setBusy(true)
                    apiFetch(`/fee-scales/${p.id}`, { token, method: 'DELETE' })
                      .then(() => load())
                      .catch((e: unknown) => setErr((e as { message?: string }).message ?? 'Delete failed'))
                      .finally(() => setBusy(false))
                  })
                }}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 ? <div className="muted">No fee scales yet — create one above.</div> : null}
      </div>
    </div>
  )
}
