import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { useDialogs } from '../DialogProvider'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { FeeScaleScaleRows } from '../FeeScaleThreadTree'
import { openOnlyOfficePrecedentEditor } from '../onlyofficeEditorWindow'
import {
  buildPrecedentTree,
  countFilteredCustomPrecedents,
  countMatterBlockPrecedents,
  countSubTypeBlockPrecedents,
  SYSTEM_PRECEDENT_REFERENCES,
  type PrecedentKindFilter,
  type PrecedentMatterBlock,
} from '../precedentGrouping'
import { SearchInput } from '../SearchInput'
import type { MatterHeadTypeOut, PrecedentCategoryOut, PrecedentOut } from '../types'
import { GLOBAL_PRECEDENT_SCOPE } from '../types'
import { PrecedentNamePencilIcon } from './precedentAdminHelpers'

type Props = {
  token: string
  items: PrecedentOut[]
  matterHeads: MatterHeadTypeOut[]
  busy: boolean
  setBusy: (busy: boolean) => void
  onReload: () => Promise<void>
  onError: (message: string | null) => void
}

export function AdminPrecedentLibraryPanel({
  token,
  items,
  matterHeads,
  busy,
  setBusy,
  onReload,
  onError,
}: Props) {
  const { askConfirm } = useDialogs()
  const systemPrecedentReferences = SYSTEM_PRECEDENT_REFERENCES
  const [nameEditId, setNameEditId] = useState<string | null>(null)
  const [nameDraft, setNameDraft] = useState('')
  const [referenceEditId, setReferenceEditId] = useState<string | null>(null)
  const [referenceDraft, setReferenceDraft] = useState('')
  const [scopeEditId, setScopeEditId] = useState<string | null>(null)
  const [scopeEditHead, setScopeEditHead] = useState('')
  const [scopeEditSub, setScopeEditSub] = useState('')
  const [scopeEditCat, setScopeEditCat] = useState(GLOBAL_PRECEDENT_SCOPE)
  const [scopeEditCats, setScopeEditCats] = useState<PrecedentCategoryOut[]>([])
  const [scopeEditCatsLoading, setScopeEditCatsLoading] = useState(false)
  const precedentNameInputRef = useRef<HTMLInputElement | null>(null)
  const precedentReferenceInputRef = useRef<HTMLInputElement | null>(null)
  const [listSearch, setListSearch] = useState('')
  const [listKindFilter, setListKindFilter] = useState<PrecedentKindFilter>('all')
  const [expandedTreeNodes, setExpandedTreeNodes] = useState<Set<string>>(() => new Set())

  const listFilters = useMemo(
    () => ({ search: listSearch, kind: listKindFilter }),
    [listSearch, listKindFilter],
  )

  const precedentTree = useMemo(
    () => buildPrecedentTree(items, matterHeads, listFilters),
    [items, matterHeads, listFilters],
  )

  const filteredCustomCount = useMemo(
    () => countFilteredCustomPrecedents(items, listFilters),
    [items, listFilters],
  )

  const listFilterActive = listKindFilter !== 'all' || listSearch.trim().length > 0

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )

  const uploadHeadTypeDropdownOptions = useMemo(
    () => [
      { value: '', label: '— select —' },
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all cases)' },
      ...matterTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ],
    [matterTypeOptions],
  )

  const scopeEditHeadIsGlobal = scopeEditHead === GLOBAL_PRECEDENT_SCOPE
  const scopeEditSubOptions = useMemo(() => {
    if (!scopeEditHead || scopeEditHead === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === scopeEditHead)
    return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
  }, [matterHeads, scopeEditHead])

  function isTreeNodeExpanded(key: string): boolean {
    return expandedTreeNodes.has(key)
  }

  function toggleTreeNode(key: string) {
    setExpandedTreeNodes((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function expandAllTreeNodes() {
    const keys = new Set<string>()
    for (const block of precedentTree) {
      if (block.kind === 'system') {
        keys.add('system')
      } else if (block.kind === 'global') {
        keys.add('global')
      } else if (block.kind === 'orphan') {
        keys.add('orphan')
      } else {
        keys.add(`head:${block.headId}`)
        if (block.headPrecedents.length) keys.add(`head:${block.headId}:all-subs`)
        for (const sg of block.subGroups) {
          keys.add(`head:${block.headId}:sub:${sg.subId}`)
          if (sg.uncategorised.length) keys.add(`head:${block.headId}:sub:${sg.subId}:uncat`)
          for (const cg of sg.categoryGroups) {
            keys.add(`head:${block.headId}:sub:${sg.subId}:cat:${cg.categoryId}`)
          }
        }
      }
    }
    setExpandedTreeNodes(keys)
  }

  function collapseAllTreeNodes() {
    setExpandedTreeNodes(new Set())
  }

  function renderTreeSectionToggle(
    key: string,
    title: string,
    count: number,
    opts?: { className?: string },
  ) {
    const expanded = isTreeNodeExpanded(key)
    return (
      <button
        type="button"
        className={`precedentTreeSectionToggle${opts?.className ? ` ${opts.className}` : ''}`}
        aria-expanded={expanded}
        onClick={() => toggleTreeNode(key)}
      >
        <span className="precedentTreeSectionChevron" aria-hidden>
          {expanded ? '▾' : '▸'}
        </span>
        <span className="precedentTreeSectionTitle">{title}</span>
        <span className="precedentTreeSectionCount">{count}</span>
      </button>
    )
  }

  useEffect(() => {
    if (!nameEditId) return
    const id = requestAnimationFrame(() => {
      precedentNameInputRef.current?.focus()
      precedentNameInputRef.current?.select()
    })
    return () => cancelAnimationFrame(id)
  }, [nameEditId])

  useEffect(() => {
    if (!referenceEditId) return
    const id = requestAnimationFrame(() => {
      precedentReferenceInputRef.current?.focus()
      precedentReferenceInputRef.current?.select()
    })
    return () => cancelAnimationFrame(id)
  }, [referenceEditId])

  useEffect(() => {
    if (!scopeEditId || !scopeEditHead || scopeEditHead === GLOBAL_PRECEDENT_SCOPE) {
      setScopeEditCats([])
      return
    }
    if (!scopeEditSub || scopeEditSub === GLOBAL_PRECEDENT_SCOPE) {
      setScopeEditCats([])
      return
    }
    let cancelled = false
    setScopeEditCatsLoading(true)
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${scopeEditSub}/precedent-categories`, { token })
      .then((rows) => {
        if (!cancelled) setScopeEditCats(Array.isArray(rows) ? rows : [])
      })
      .catch(() => {
        if (!cancelled) setScopeEditCats([])
      })
      .finally(() => {
        if (!cancelled) setScopeEditCatsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [scopeEditId, scopeEditHead, scopeEditSub, token])

  function scopeIdToForm(id?: string | null) {
    return id ?? GLOBAL_PRECEDENT_SCOPE
  }

  async function commitPrecedentReferenceEdit(p: PrecedentOut) {
    const v = referenceDraft.trim()
    if (!v) {
      onError('Reference cannot be empty.')
      return
    }
    if (v === p.reference) {
      setReferenceEditId(null)
      return
    }
    setBusy(true)
    onError(null)
    try {
      await apiFetch(`/precedents/${p.id}`, { token, method: 'PATCH', json: { reference: v } })
      setReferenceEditId(null)
      await onReload()
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Failed to update reference')
    } finally {
      setBusy(false)
    }
  }

  function beginScopeEdit(p: PrecedentOut) {
    setScopeEditId(p.id)
    setScopeEditHead(scopeIdToForm(p.matter_head_type_id))
    setScopeEditSub(scopeIdToForm(p.matter_sub_type_id))
    setScopeEditCat(scopeIdToForm(p.category_id))
  }

  async function commitScopeEdit(p: PrecedentOut) {
    setBusy(true)
    onError(null)
    try {
      let mh: string | null = GLOBAL_PRECEDENT_SCOPE
      let ms: string | null = GLOBAL_PRECEDENT_SCOPE
      let cat: string | null = GLOBAL_PRECEDENT_SCOPE
      if (scopeEditHead && scopeEditHead !== GLOBAL_PRECEDENT_SCOPE) {
        mh = scopeEditHead
        if (scopeEditSub && scopeEditSub !== GLOBAL_PRECEDENT_SCOPE) {
          ms = scopeEditSub
          cat = scopeEditCat && scopeEditCat !== GLOBAL_PRECEDENT_SCOPE ? scopeEditCat : null
        } else {
          ms = null
          cat = null
        }
      } else {
        mh = null
        ms = null
        cat = null
      }
      await apiFetch(`/precedents/${p.id}`, {
        token,
        method: 'PATCH',
        json: {
          matter_head_type_id: mh === GLOBAL_PRECEDENT_SCOPE ? null : mh,
          matter_sub_type_id: ms === GLOBAL_PRECEDENT_SCOPE ? null : ms,
          category_id: cat === GLOBAL_PRECEDENT_SCOPE ? null : cat,
        },
      })
      setScopeEditId(null)
      await onReload()
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Failed to update scope')
    } finally {
      setBusy(false)
    }
  }

  async function commitPrecedentNameEdit(p: PrecedentOut) {
    const v = nameDraft.trim()
    if (!v) {
      onError('Name cannot be empty.')
      return
    }
    if (v === p.name) {
      setNameEditId(null)
      return
    }
    setBusy(true)
    onError(null)
    try {
      await apiFetch(`/precedents/${p.id}`, {
        token,
        method: 'PATCH',
        json: { name: v },
      })
      setNameEditId(null)
      await onReload()
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Failed to update name')
    } finally {
      setBusy(false)
    }
  }

  function renderPrecedentCard(p: PrecedentOut) {
    return (
      <div
        className="listCard row precedentListCardRow"
        style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}
      >
        <div style={{ flex: '1 1 200px', minWidth: 0 }}>
          {nameEditId === p.id ? (
            <div className="precedentNameRow precedentNameRow--edit">
              <input
                ref={precedentNameInputRef}
                className="precedentAdminNameInput"
                value={nameDraft}
                disabled={busy}
                maxLength={300}
                aria-label="Precedent name"
                onChange={(e) => setNameDraft(e.target.value)}
                onBlur={() => void commitPrecedentNameEdit(p)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void commitPrecedentNameEdit(p)
                  }
                  if (e.key === 'Escape') {
                    e.preventDefault()
                    setNameEditId(null)
                    onError(null)
                  }
                }}
              />
            </div>
          ) : (
            <div className="precedentNameRow">
              <span className="listTitle precedentNameText">{p.name}</span>
              <button
                type="button"
                className="btn precedentNameEditBtn"
                disabled={busy}
                title="Edit name"
                aria-label="Edit precedent name"
                onClick={() => {
                  setNameEditId(p.id)
                  setNameDraft(p.name)
                }}
              >
                <PrecedentNamePencilIcon />
              </button>
            </div>
          )}
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            {referenceEditId === p.id ? (
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  ref={precedentReferenceInputRef}
                  className="mono precedentAdminNameInput"
                  value={referenceDraft}
                  disabled={busy}
                  maxLength={200}
                  aria-label="Precedent reference"
                  onChange={(e) => setReferenceDraft(e.target.value)}
                  onBlur={() => void commitPrecedentReferenceEdit(p)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      void commitPrecedentReferenceEdit(p)
                    }
                    if (e.key === 'Escape') {
                      e.preventDefault()
                      setReferenceEditId(null)
                      onError(null)
                    }
                  }}
                />
              </div>
            ) : (
              <span className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="mono">{p.reference}</span>
                {!systemPrecedentReferences.has(p.reference) ? (
                  <button
                    type="button"
                    className="btn precedentNameEditBtn"
                    disabled={busy}
                    title="Edit reference"
                    aria-label="Edit precedent reference"
                    onClick={() => {
                      setReferenceEditId(p.id)
                      setReferenceDraft(p.reference)
                    }}
                  >
                    <PrecedentNamePencilIcon />
                  </button>
                ) : null}
              </span>
            )}{' '}
            · {p.kind}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {p.original_filename}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            {scopeEditId === p.id ? (
              <div className="stack" style={{ gap: 8, marginTop: 4 }}>
                <SingleSelectDropdown
                  label="Matter type"
                  options={uploadHeadTypeDropdownOptions}
                  value={scopeEditHead}
                  onChange={(v) => {
                    setScopeEditHead(v)
                    setScopeEditSub('')
                    setScopeEditCat(GLOBAL_PRECEDENT_SCOPE)
                  }}
                  disabled={busy}
                />
                <SingleSelectDropdown
                  label="Sub-type"
                  options={
                    !scopeEditHead
                      ? [{ value: '', label: 'Select a matter type first' }]
                      : scopeEditHeadIsGlobal
                        ? [{ value: GLOBAL_PRECEDENT_SCOPE, label: 'Global' }]
                        : [
                            { value: '', label: '— select —' },
                            { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all sub-types under this matter type)' },
                            ...scopeEditSubOptions.map((o) => ({ value: o.id, label: o.label })),
                          ]
                  }
                  value={scopeEditSub}
                  onChange={(v) => {
                    setScopeEditSub(v)
                    setScopeEditCat(GLOBAL_PRECEDENT_SCOPE)
                  }}
                  disabled={busy || !scopeEditHead || scopeEditHeadIsGlobal}
                />
                {scopeEditHead &&
                !scopeEditHeadIsGlobal &&
                scopeEditSub &&
                scopeEditSub !== GLOBAL_PRECEDENT_SCOPE ? (
                  scopeEditCatsLoading ? (
                    <div className="muted">Loading categories…</div>
                  ) : (
                    <SingleSelectDropdown
                      label="Precedent category"
                      options={[
                        { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all categories under this sub-type)' },
                        ...scopeEditCats.map((c) => ({ value: c.id, label: c.name })),
                      ]}
                      value={scopeEditCat}
                      onChange={setScopeEditCat}
                      disabled={busy}
                    />
                  )
                ) : null}
                <div className="row" style={{ gap: 8 }}>
                  <button type="button" className="btn primary" disabled={busy} onClick={() => void commitScopeEdit(p)}>
                    Save scope
                  </button>
                  <button type="button" className="btn" disabled={busy} onClick={() => setScopeEditId(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <span className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <span>{p.scope_summary || p.category_name || '—'}</span>
                {!systemPrecedentReferences.has(p.reference) ? (
                  <button
                    type="button"
                    className="btn precedentNameEditBtn"
                    disabled={busy}
                    title="Edit scope / category"
                    aria-label="Edit precedent scope"
                    onClick={() => beginScopeEdit(p)}
                  >
                    <PrecedentNamePencilIcon />
                  </button>
                ) : null}
              </span>
            )}
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => openOnlyOfficePrecedentEditor(p.id)}
          >
            Edit in OnlyOffice
          </button>
          {systemPrecedentReferences.has(p.reference) ? null : (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                void (async () => {
                  const ok = await askConfirm({
                    title: 'Delete precedent',
                    message: `Delete precedent "${p.name}"?`,
                    danger: true,
                    confirmLabel: 'Delete',
                  })
                  if (!ok) return
                  setBusy(true)
                  apiFetch(`/precedents/${p.id}`, { token, method: 'DELETE' })
                    .then(() => onReload())
                    .catch((e: any) => onError(e?.message ?? 'Delete failed'))
                    .finally(() => setBusy(false))
                })()
              }}
            >
              Remove
            </button>
          )}
        </div>
      </div>
    )
  }

  function renderPrecedentRows(precedents: PrecedentOut[], depth: 0 | 1 | 2) {
    return (
      <FeeScaleScaleRows
        depth={depth}
        scales={precedents.map((p) => ({
          id: p.id,
          render: () => renderPrecedentCard(p),
        }))}
      />
    )
  }

  function renderMatterBlock(block: PrecedentMatterBlock) {
    const headKey = `head:${block.headId}`
    const headExpanded = isTreeNodeExpanded(headKey)
    const headCount = countMatterBlockPrecedents(block)
    return (
      <section key={block.headId} className="feeScaleTreeBlock feeScaleTreeBlock--matter precedentTreeBlock">
        {renderTreeSectionToggle(headKey, block.headName, headCount, { className: 'precedentTreeSectionToggle--head' })}
        {headExpanded ? (
          <div className="precedentTreeSectionBody">
            {block.headPrecedents.length ? (
              <div className="precedentTreeNestedSection">
                {renderTreeSectionToggle(
                  `${headKey}:all-subs`,
                  'All sub-types',
                  block.headPrecedents.length,
                )}
                {isTreeNodeExpanded(`${headKey}:all-subs`) ? renderPrecedentRows(block.headPrecedents, 1) : null}
              </div>
            ) : null}
            {block.subGroups.map((sg) => {
              const subKey = `${headKey}:sub:${sg.subId}`
              const subCount = countSubTypeBlockPrecedents(sg)
              return (
                <div key={sg.subId} className="precedentTreeNestedSection">
                  {renderTreeSectionToggle(subKey, sg.subName, subCount, { className: 'precedentTreeSectionToggle--sub' })}
                  {isTreeNodeExpanded(subKey) ? (
                    <div className="precedentTreeSectionBody precedentTreeSectionBody--nested">
                      {sg.uncategorised.length ? (
                        <div className="precedentTreeSubGroup">
                          {renderTreeSectionToggle(
                            `${subKey}:uncat`,
                            'Uncategorised',
                            sg.uncategorised.length,
                          )}
                          {isTreeNodeExpanded(`${subKey}:uncat`) ? renderPrecedentRows(sg.uncategorised, 2) : null}
                        </div>
                      ) : null}
                      {sg.categoryGroups.map((cg) => (
                        <div key={cg.categoryId} className="precedentTreeSubGroup">
                          {renderTreeSectionToggle(
                            `${subKey}:cat:${cg.categoryId}`,
                            cg.categoryName,
                            cg.precedents.length,
                          )}
                          {isTreeNodeExpanded(`${subKey}:cat:${cg.categoryId}`)
                            ? renderPrecedentRows(cg.precedents, 2)
                            : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        ) : null}
      </section>
    )
  }

  return (
    <div className="card" style={{ padding: 12, marginTop: 16 }}>
      <h4 style={{ marginTop: 0 }}>Precedent library</h4>
      <div className="precedentLibraryToolbar stack" style={{ gap: 10, marginBottom: 16 }}>
        <SearchInput
          placeholder="Search by name or reference…"
          value={listSearch}
          onChange={(e) => setListSearch(e.target.value)}
          onClear={() => setListSearch('')}
          aria-label="Search precedents"
        />
        <div className="precedentKindTabs row" role="tablist" aria-label="Precedent kind">
          {(
            [
              ['all', 'All'],
              ['letter', 'Letters'],
              ['email', 'E-mails'],
              ['document', 'Documents'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={listKindFilter === value}
              className={`btn precedentKindTab${listKindFilter === value ? ' precedentKindTab--active' : ''}`}
              onClick={() => setListKindFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="row precedentLibraryMeta" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {listFilterActive ? (
            <span className="precedentLibraryFilterStatus">
              Showing {filteredCustomCount} firm precedent{filteredCustomCount === 1 ? '' : 's'}
              {listKindFilter !== 'all' ? ` · ${listKindFilter === 'email' ? 'E-mails' : listKindFilter === 'letter' ? 'Letters' : 'Documents'} only` : ''}
              {listSearch.trim() ? ` · matching “${listSearch.trim()}”` : ''}
            </span>
          ) : (
            <span className="muted">Expand a section to browse — system templates are listed separately below.</span>
          )}
          <button type="button" className="btn" onClick={expandAllTreeNodes}>
            Expand all
          </button>
          <button type="button" className="btn" onClick={collapseAllTreeNodes}>
            Collapse all
          </button>
        </div>
      </div>

      <div className="feeScaleTree precedentTree stack" style={{ gap: 24 }}>
        {precedentTree.map((block) => {
          if (block.kind === 'system') {
            const expanded = isTreeNodeExpanded('system')
            return (
              <section key="system" className="feeScaleTreeBlock precedentTreeBlock precedentTreeBlock--system">
                {renderTreeSectionToggle('system', 'System templates', block.precedents.length, {
                  className: 'precedentTreeSectionToggle--system',
                })}
                <p className="muted precedentTreeBlockHint">
                  Built-in Canary templates — always listed; not affected by search or kind filters.
                </p>
                {expanded ? renderPrecedentRows(block.precedents, 0) : null}
              </section>
            )
          }
          if (block.kind === 'global') {
            const expanded = isTreeNodeExpanded('global')
            return (
              <section key="global" className="feeScaleTreeBlock precedentTreeBlock">
                {renderTreeSectionToggle('global', 'Global — all cases', block.precedents.length)}
                {expanded ? renderPrecedentRows(block.precedents, 0) : null}
              </section>
            )
          }
          if (block.kind === 'orphan') {
            const expanded = isTreeNodeExpanded('orphan')
            return (
              <section key="orphan" className="feeScaleTreeBlock precedentTreeBlock">
                {renderTreeSectionToggle('orphan', 'Other', block.precedents.length)}
                {expanded ? renderPrecedentRows(block.precedents, 1) : null}
              </section>
            )
          }
          return renderMatterBlock(block)
        })}
        {items.length === 0 ? <div className="muted">No precedents yet — upload one above.</div> : null}
        {items.length > 0 &&
        filteredCustomCount === 0 &&
        items.some((p) => !systemPrecedentReferences.has(p.reference)) ? (
          <div className="muted">No firm precedents match your search or kind filter.</div>
        ) : null}
      </div>
    </div>
  )
}
