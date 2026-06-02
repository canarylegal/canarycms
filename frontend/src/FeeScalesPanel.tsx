import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { FeeScaleEditor } from './FeeScaleEditor'
import { FeeScaleListCard } from './FeeScaleListCard'
import { FeeScaleScaleRows, FeeScaleThreadGroup } from './FeeScaleThreadTree'
import { buildFeeScaleTree } from './feeScaleGrouping'
import { scopeSummaryForCreate, buildClonedDraftDetail, type FeeScaleDraftCreate } from './feeScaleDraft'
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

function scopeIdsFromScale(scale: FeeScaleOut): { headId: string; subId: string } {
  if (!scale.matter_head_type_id) {
    return { headId: GLOBAL_PRECEDENT_SCOPE, subId: GLOBAL_PRECEDENT_SCOPE }
  }
  if (!scale.matter_sub_type_id) {
    return { headId: scale.matter_head_type_id, subId: GLOBAL_PRECEDENT_SCOPE }
  }
  return { headId: scale.matter_head_type_id, subId: scale.matter_sub_type_id }
}

export function FeeScalesPanel({ token, onBack }: { token: string; onBack: () => void }) {
  const { askConfirm } = useDialogs()
  const [items, setItems] = useState<FeeScaleOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [matterTypesReady, setMatterTypesReady] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [draftCreate, setDraftCreate] = useState<FeeScaleDraftCreate | null>(null)
  const [draftInitialDetail, setDraftInitialDetail] = useState<FeeScaleDetailOut | null>(null)
  const [cloneSourceDetail, setCloneSourceDetail] = useState<FeeScaleDetailOut | null>(null)
  const [cloneSourceName, setCloneSourceName] = useState<string | null>(null)
  const createFormRef = useRef<HTMLDivElement>(null)
  const [createName, setCreateName] = useState('')
  const [createRef, setCreateRef] = useState(() => randomHexRef())
  const [createHeadId, setCreateHeadId] = useState('')
  const [createSubId, setCreateSubId] = useState('')
  const [createErr, setCreateErr] = useState<string | null>(null)

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )
  const createSubOptions = useMemo(
    () => subTypeOptionsForHead(matterHeads, createHeadId),
    [matterHeads, createHeadId],
  )
  const createHeadIsGlobal = createHeadId === GLOBAL_PRECEDENT_SCOPE

  function validateCreateForm(): string | null {
    if (!createName.trim()) return 'Enter a name for the fee scale.'
    if (!createHeadId) return 'Select a matter type or Global (all cases).'
    if (!createHeadIsGlobal && !createSubId) {
      return 'Select a sub-type or “All sub-types under this matter type”.'
    }
    return null
  }

  const feeScaleTree = useMemo(() => buildFeeScaleTree(items, matterHeads), [items, matterHeads])

  async function toggleFavorite(scale: FeeScaleOut) {
    const favorited = !scale.is_favorited
    setBusy(true)
    try {
      await apiFetch<FeeScaleOut>(`/fee-scales/${scale.id}/favorite`, {
        token,
        method: 'PUT',
        json: { favorited },
      })
      setItems((prev) => prev.map((row) => (row.id === scale.id ? { ...row, is_favorited: favorited } : row)))
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not update favourite')
    } finally {
      setBusy(false)
    }
  }

  async function startCloneSetup(scale: FeeScaleOut) {
    setBusy(true)
    setErr(null)
    try {
      const detail = await apiFetch<FeeScaleDetailOut>(`/fee-scales/${scale.id}`, { token })
      const { headId, subId } = scopeIdsFromScale(scale)
      setCloneSourceDetail(detail)
      setCloneSourceName(scale.name)
      setCreateName(`${scale.name} (copy)`)
      setCreateRef(randomHexRef())
      setCreateHeadId(headId)
      setCreateSubId(subId)
      setCreateErr(null)
      createFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not load fee scale to clone')
    } finally {
      setBusy(false)
    }
  }

  function clearCloneSetup() {
    setCloneSourceDetail(null)
    setCloneSourceName(null)
  }

  function renderScaleActions(p: FeeScaleOut) {
    return (
      <FeeScaleListCard
        scale={p}
        busy={busy}
        onToggleFavorite={() => void toggleFavorite(p)}
        onClone={() => void startCloneSetup(p)}
        onEdit={() => {
          setDraftCreate(null)
          setDraftInitialDetail(null)
          clearCloneSetup()
          setEditId(p.id)
        }}
        onRemove={() => {
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
      />
    )
  }

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

  function startCreateSetup() {
    const validationErr = validateCreateForm()
    if (validationErr) {
      setCreateErr(validationErr)
      return
    }
    const scope = scopeToApiPayload(createHeadId, createSubId)
    const draft: FeeScaleDraftCreate = {
      name: createName.trim(),
      reference: createRef.trim() || randomHexRef(),
      matter_head_type_id: scope.matter_head_type_id,
      matter_sub_type_id: scope.matter_sub_type_id,
      scope_summary: scopeSummaryForCreate(createHeadId, createSubId, matterHeads),
    }
    setCreateErr(null)
    setDraftCreate(draft)
    setDraftInitialDetail(cloneSourceDetail ? buildClonedDraftDetail(cloneSourceDetail, draft) : null)
    clearCloneSetup()
    setEditId(null)
  }

  function exitEditor() {
    setEditId(null)
    setDraftCreate(null)
    setDraftInitialDetail(null)
    clearCloneSetup()
    setCreateName('')
    setCreateRef(randomHexRef())
    setCreateHeadId('')
    setCreateSubId('')
    setCreateErr(null)
    void load()
  }

  if (editId || draftCreate) {
    return (
      <div className="mainMenuShell mainMenuShell--mainMenu">
        <FeeScaleEditor
          token={token}
          scaleId={editId ?? undefined}
          draftCreate={draftCreate ?? undefined}
          draftInitialDetail={draftInitialDetail}
          setupMode={Boolean(draftCreate)}
          onBack={() => exitEditor()}
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
          Configure quote fee tables in Canary — categories, line items, value bands, VAT and totals. Star a scale to
          show it first when creating quotes. Quotes are generated as Word documents on your quote letterhead.
        </p>
      </div>
      {err ? <div className="error">{err}</div> : null}

      <div ref={createFormRef} className="card stack" style={{ marginBottom: 16, padding: 12 }}>
        <h4 style={{ margin: 0 }}>New fee scale</h4>
        {cloneSourceName ? (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Cloning from “{cloneSourceName}”. Set the name, reference and matter type below, then click Create to edit
            the copy.
            {' '}
            <button
              type="button"
              className="btn"
              style={{ padding: 0, border: 'none', background: 'none', color: 'var(--link, #2563eb)', font: 'inherit' }}
              disabled={busy}
              onClick={() => clearCloneSetup()}
            >
              Cancel clone
            </button>
          </p>
        ) : null}
        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={createName}
            onChange={(e) => {
              setCreateName(e.target.value)
              setCreateErr(null)
            }}
          />
        </label>
        <label className="field">
          <span>Reference</span>
          <input
            className="input"
            value={createRef}
            onChange={(e) => {
              setCreateRef(e.target.value)
              setCreateErr(null)
            }}
          />
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
            setCreateErr(null)
          }}
          onSubChange={(v) => {
            setCreateSubId(v)
            setCreateErr(null)
          }}
        />
        {createErr ? <div className="error">{createErr}</div> : null}
        <button type="button" className="btn primary" disabled={busy} onClick={() => startCreateSetup()}>
          Create
        </button>
      </div>

      <div className="feeScaleTree stack" style={{ gap: 24 }}>
        {feeScaleTree.map((block) => {
          if (block.kind === 'global') {
            return (
              <section key="global" className="feeScaleTreeBlock">
                <h4 className="feeScaleTreeBlockTitle">Global — all cases</h4>
                <FeeScaleScaleRows
                  depth={0}
                  scales={block.scales.map((p) => ({
                    id: p.id,
                    render: () => renderScaleActions(p),
                  }))}
                />
              </section>
            )
          }

          if (block.kind === 'orphan') {
            return (
              <section key="orphan" className="feeScaleTreeBlock">
                <h4 className="feeScaleTreeBlockTitle">Other</h4>
                <FeeScaleScaleRows
                  depth={1}
                  scales={block.scales.map((p) => ({
                    id: p.id,
                    render: () => renderScaleActions(p),
                  }))}
                />
              </section>
            )
          }

          return (
            <section key={block.headId} className="feeScaleTreeBlock feeScaleTreeBlock--matter">
              <h4 className="feeScaleTreeBlockTitle">{block.headName}</h4>
              {block.headScales.length ? (
                <FeeScaleThreadGroup depth={1} label="All sub-types">
                  <FeeScaleScaleRows
                    depth={1}
                    scales={block.headScales.map((p) => ({
                      id: p.id,
                      render: () => renderScaleActions(p),
                    }))}
                  />
                </FeeScaleThreadGroup>
              ) : null}
              {block.subGroups.map((sg) => (
                <FeeScaleThreadGroup key={sg.subId} depth={2} label={sg.subName}>
                  <FeeScaleScaleRows
                    depth={2}
                    scales={sg.scales.map((p) => ({
                      id: p.id,
                      render: () => renderScaleActions(p),
                    }))}
                  />
                </FeeScaleThreadGroup>
              ))}
            </section>
          )
        })}
        {items.length === 0 ? <div className="muted">No fee scales yet — create one above.</div> : null}
      </div>
    </div>
  )
}
