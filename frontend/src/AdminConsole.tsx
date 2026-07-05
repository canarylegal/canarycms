import { useEffect, useMemo, useRef, useState } from 'react'
import { AdminAudit } from './AdminAudit'
import { AdminBilling } from './AdminBilling'
import { AdminDeploy } from './AdminDeploy'
import { AdminEmail } from './AdminEmail'
import { AdminDocuSign } from './AdminDocuSign'
import { AdminPortalForms } from './AdminPortalForms'
import { AdminFirmDetails } from './AdminFirmDetails'
import { AdminSubMenus } from './AdminSubMenus'
import { AdminTasks } from './AdminTasks'
import { apiFetch, apiUrl, applyAuthHeaders } from './api'
import type { ApiError } from './api'
import { CASE_MENU_OPTIONS } from './caseMenuOptions'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { FeeScaleScaleRows } from './FeeScaleThreadTree'
import { openOnlyOfficeFirmLetterheadEditor, openOnlyOfficePrecedentEditor } from './onlyofficeEditorWindow'
import {
  buildPrecedentTree,
  countFilteredCustomPrecedents,
  countMatterBlockPrecedents,
  countSubTypeBlockPrecedents,
  SYSTEM_PRECEDENT_REFERENCES,
  type PrecedentKindFilter,
  type PrecedentMatterBlock,
} from './precedentGrouping'
import { SearchInput } from './SearchInput'
import type {
  AdminSendPasswordResetResponse,
  AdminUserPublic,
  FirmSettingsOut,
  LetterheadStyle,
  MatterContactTypeOut,
  MatterHeadTypeOut,
  MatterSubTypeOut,
  MergeCodeCatalogImportResult,
  MergeCodeCatalogOut,
  PrecedentCategoryOut,
  PrecedentOut,
  UserPermissionCategoryOut,
} from './types'
import { GLOBAL_PRECEDENT_SCOPE } from './types'

function AdminMatters({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [heads, setHeads] = useState<MatterHeadTypeOut[]>([])
  const [selectedHeadId, setSelectedHeadId] = useState<string | null>(null)
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [subPrecCats, setSubPrecCats] = useState<PrecedentCategoryOut[]>([])
  const [newPrecCatName, setNewPrecCatName] = useState('')
  const [editingPrecCatId, setEditingPrecCatId] = useState<string | null>(null)
  const [editingPrecCatName, setEditingPrecCatName] = useState('')

  // Sub type form state
  const [newSubName, setNewSubName] = useState('')
  const [editingSubId, setEditingSubId] = useState<string | null>(null)
  const [editingSubName, setEditingSubName] = useState('')

  // Sub type config state (prefix + menus)
  const [prefixInput, setPrefixInput] = useState('')
  const [newMenuName, setNewMenuName] = useState('')
  const [editingMenuId, setEditingMenuId] = useState<string | null>(null)
  const [editingMenuName, setEditingMenuName] = useState('')

  async function loadHeads() {
    try {
      const data = await apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
      setHeads(data)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load matter types')
    }
  }

  useEffect(() => { void loadHeads() }, [token])

  useEffect(() => {
    if (!selectedSubId) {
      setSubPrecCats([])
      return
    }
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, { token })
      .then(setSubPrecCats)
      .catch(() => setSubPrecCats([]))
  }, [selectedSubId, token])

  const selectedHead = heads.find((h) => h.id === selectedHeadId) ?? null
  const selectedSub: MatterSubTypeOut | null =
    selectedHead?.sub_types.find((s) => s.id === selectedSubId) ?? null

  // Sync prefix input when selected sub changes
  useEffect(() => {
    setPrefixInput(selectedSub?.prefix ?? '')
    setNewPrecCatName('')
    setNewMenuName('')
    setEditingMenuId(null)
    setEditingPrecCatId(null)
  }, [selectedSubId, selectedHead])

  // Clear sub selection when head changes
  useEffect(() => {
    setSelectedSubId(null)
  }, [selectedHeadId])

  const smallBtn = { padding: '3px 8px', fontSize: '0.82em' } as const
  const inlineInput = { flex: 1, width: 'auto' } as const

  const addMenuOptions = useMemo(
    () =>
      CASE_MENU_OPTIONS.filter((opt) => !selectedSub?.menus.some((m) => m.name === opt)).map((opt) => ({
        value: opt,
        label: opt,
      })),
    [selectedSub],
  )

  // ── Head type visibility (canonical list from Canary; no add/rename/delete) ──

  async function setHeadHidden(id: string, is_hidden: boolean) {
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/heads/${id}`, { token, method: 'PATCH', json: { is_hidden } })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Sub type actions ─────────────────────────────────────────────────────

  async function addSub() {
    if (!newSubName.trim() || !selectedHeadId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/heads/${selectedHeadId}/sub-types`, { token, json: { name: newSubName.trim() } })
      setNewSubName('')
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function savePrecCatRename(categoryId: string) {
    const name = editingPrecCatName.trim()
    if (!name || !selectedSubId) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories/${categoryId}`, {
        token,
        method: 'PATCH',
        json: { name },
      })
      const next = await apiFetch<PrecedentCategoryOut[]>(
        `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
        { token },
      )
      setSubPrecCats(next)
      setEditingPrecCatId(null)
      setEditingPrecCatName('')
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to rename category')
    } finally {
      setBusy(false)
    }
  }

  async function saveSubRename(id: string) {
    if (!editingSubName.trim()) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${id}`, { token, method: 'PATCH', json: { name: editingSubName.trim() } })
      setEditingSubId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function deleteSub(id: string) {
    const ok = await askConfirm({
      title: 'Delete sub type',
      message:
        'Delete this sub type? You must remove its sub-menus, precedent categories, and precedents scoped to it first; hiding the head matter type does not delete sub-types or menus.',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${id}`, { token, method: 'DELETE' })
      if (selectedSubId === id) setSelectedSubId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Prefix action ────────────────────────────────────────────────────────

  async function savePrefix() {
    if (!selectedSubId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${selectedSubId}`, {
        token, method: 'PATCH', json: { prefix: prefixInput.trim() || null },
      })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Menu actions ─────────────────────────────────────────────────────────

  async function addMenu() {
    if (!newMenuName.trim() || !selectedSubId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${selectedSubId}/menus`, { token, json: { name: newMenuName.trim() } })
      setNewMenuName('')
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function saveMenuRename(id: string) {
    if (!editingMenuName.trim()) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/menus/${id}`, { token, method: 'PATCH', json: { name: editingMenuName.trim() } })
      setEditingMenuId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function deleteMenu(id: string) {
    const ok = await askConfirm({
      title: 'Remove menu',
      message: 'Remove this menu?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/menus/${id}`, { token, method: 'DELETE' })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      {err ? <div className="error">{err}</div> : null}

      {/* ── Row 1: head types + sub types ─────────────────────────── */}
      <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>

        {/* Head matter types */}
        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>Head matter types</h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Head types are defined by Canary and sync from the product seed. Hide a head here if your firm does not use that area of law (it disappears from fee-earner matter pickers but stays in the database for existing matters).
          </p>
          <div className="list">
            {heads.map((h) => (
              <div
                key={h.id}
                className="listCard row"
                style={{
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  background: selectedHeadId === h.id ? 'rgba(37,99,235,0.1)' : undefined,
                  opacity: h.is_hidden ? 0.72 : undefined,
                }}
                onClick={() => setSelectedHeadId(h.id)}
              >
                <span className="listTitle">
                  {h.name}
                  {h.is_hidden ? <span className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>(hidden)</span> : null}
                </span>
                <label
                  className="row"
                  style={{ gap: 6, alignItems: 'center', fontSize: 13 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={Boolean(h.is_hidden)}
                    disabled={busy}
                    onChange={(e) => void setHeadHidden(h.id, e.target.checked)}
                  />
                  <span>Hidden</span>
                </label>
              </div>
            ))}
            {heads.length === 0 && <div className="muted" style={{ padding: '6px 0' }}>No head types yet.</div>}
          </div>
        </div>

        {/* Sub matter types */}
        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>
            Sub matter types{selectedHead ? ` — ${selectedHead.name}` : ''}
          </h3>
          {!selectedHead ? (
            <div className="muted">Select a head type on the left to manage its sub types.</div>
          ) : (
            <>
              <div className="list">
                {selectedHead.sub_types.map((s) => (
                  <div
                    key={s.id}
                    className="listCard row"
                    style={{
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      background: selectedSubId === s.id ? 'rgba(37,99,235,0.1)' : undefined,
                    }}
                    onClick={() => setSelectedSubId(s.id)}
                  >
                    {editingSubId === s.id ? (
                      <input
                        style={inlineInput}
                        value={editingSubName}
                        onChange={(e) => setEditingSubName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void saveSubRename(s.id); if (e.key === 'Escape') setEditingSubId(null) }}
                        autoFocus
                        disabled={busy}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <span className="listTitle">{s.name}</span>
                    )}
                    <div className="row" style={{ gap: 4 }} onClick={(e) => e.stopPropagation()}>
                      {editingSubId === s.id ? (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => void saveSubRename(s.id)}>Save</button>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => setEditingSubId(null)}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => { setEditingSubId(s.id); setEditingSubName(s.name) }}>Rename</button>
                          <button className="btn danger" style={smallBtn} disabled={busy} onClick={() => void deleteSub(s.id)}>Delete</button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
                {selectedHead.sub_types.length === 0 && (
                  <div className="muted" style={{ padding: '6px 0' }}>No sub types yet.</div>
                )}
              </div>
              <div className="row" style={{ marginTop: 10, gap: 6 }}>
                <input
                  style={inlineInput}
                  placeholder="New sub type name…"
                  value={newSubName}
                  onChange={(e) => setNewSubName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void addSub() }}
                  disabled={busy}
                />
                <button className="btn primary" disabled={busy || !newSubName.trim()} onClick={() => void addSub()}>Add</button>
              </div>
            </>
          )}
        </div>

      </div>

      {/* ── Row 2: sub type config (shown when a sub type is selected) ── */}
      {selectedSub && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>
            Sub type config — <span style={{ fontWeight: 400 }}>{selectedSub.name}</span>
          </h3>
          <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>

            {/* Pre-fix */}
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Pre-fix</div>
              <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
                Pre-filled into the Description field when a user creates a new matter of this type.
              </div>
              <div className="row" style={{ gap: 6 }}>
                <input
                  style={inlineInput}
                  placeholder="Pre-fix text…"
                  value={prefixInput}
                  onChange={(e) => setPrefixInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void savePrefix() }}
                  disabled={busy}
                />
                <button
                  className="btn primary"
                  disabled={busy || prefixInput === (selectedSub.prefix ?? '')}
                  onClick={() => void savePrefix()}
                >
                  Save
                </button>
              </div>
              {selectedSub.prefix && (
                <div className="muted" style={{ marginTop: 6, fontSize: '0.85em' }}>
                  Current: <em>{selectedSub.prefix}</em>
                </div>
              )}
            </div>

            {/* Default menus */}
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Default menus</div>
              <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
                Additional menus shown on the case page (alongside Contacts).
              </div>
              <div className="list">
                {selectedSub.menus.map((m) => (
                  <div key={m.id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                    {editingMenuId === m.id ? (
                      <input
                        style={inlineInput}
                        value={editingMenuName}
                        onChange={(e) => setEditingMenuName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void saveMenuRename(m.id); if (e.key === 'Escape') setEditingMenuId(null) }}
                        autoFocus
                        disabled={busy}
                      />
                    ) : (
                      <span className="listTitle">{m.name}</span>
                    )}
                    <div className="row" style={{ gap: 4 }}>
                      {editingMenuId === m.id ? (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => void saveMenuRename(m.id)}>Save</button>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => setEditingMenuId(null)}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => { setEditingMenuId(m.id); setEditingMenuName(m.name) }}>Rename</button>
                          <button className="btn danger" style={smallBtn} disabled={busy} onClick={() => void deleteMenu(m.id)}>Remove</button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
                {selectedSub.menus.length === 0 && (
                  <div className="muted" style={{ padding: '6px 0' }}>No additional menus configured.</div>
                )}
              </div>
              <div className="row" style={{ marginTop: 10, gap: 6, alignItems: 'center' }}>
                <div style={inlineInput}>
                  <SingleSelectDropdown
                    hideLabel
                    label="Additional case menu"
                    options={addMenuOptions}
                    value={newMenuName}
                    onChange={setNewMenuName}
                    disabled={busy}
                    placeholder="— select menu —"
                    emptyMessage="All menus already added."
                  />
                </div>
                <button className="btn primary" disabled={busy || !newMenuName} onClick={() => void addMenu()}>Add</button>
              </div>
            </div>

          </div>

          <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Precedent categories</div>
            <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
              Letter, document, and e-mail precedents for cases of this sub-type are grouped under these categories. The precedent picker defaults to All.
            </div>
            <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input
                style={{ minWidth: 160, ...inlineInput }}
                placeholder="New category name…"
                value={newPrecCatName}
                onChange={(e) => setNewPrecCatName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void (async () => {
                      if (!newPrecCatName.trim() || !selectedSubId || busy) return
                      setBusy(true)
                      setErr(null)
                      try {
                        await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, {
                          token,
                          json: { name: newPrecCatName.trim(), sort_order: subPrecCats.length },
                        })
                        setNewPrecCatName('')
                        const next = await apiFetch<PrecedentCategoryOut[]>(
                          `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                          { token },
                        )
                        setSubPrecCats(next)
                      } catch (e: any) {
                        setErr(e?.message ?? 'Failed to add category')
                      } finally {
                        setBusy(false)
                      }
                    })()
                  }
                }}
                disabled={busy}
              />
              <button
                type="button"
                className="btn primary"
                disabled={busy || !newPrecCatName.trim() || !selectedSubId}
                onClick={async () => {
                  if (!newPrecCatName.trim() || !selectedSubId) return
                  setBusy(true)
                  setErr(null)
                  try {
                    await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, {
                      token,
                      json: { name: newPrecCatName.trim(), sort_order: subPrecCats.length },
                    })
                    setNewPrecCatName('')
                    const next = await apiFetch<PrecedentCategoryOut[]>(
                      `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                      { token },
                    )
                    setSubPrecCats(next)
                  } catch (e: any) {
                    setErr(e?.message ?? 'Failed to add category')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Add category
              </button>
            </div>
            <div className="list" style={{ maxHeight: 200, overflow: 'auto' }}>
              {subPrecCats.map((c) => (
                <div key={c.id} className="listCard row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  {editingPrecCatId === c.id ? (
                    <input
                      style={inlineInput}
                      value={editingPrecCatName}
                      onChange={(e) => setEditingPrecCatName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void savePrecCatRename(c.id)
                        if (e.key === 'Escape') setEditingPrecCatId(null)
                      }}
                      autoFocus
                      disabled={busy}
                    />
                  ) : (
                    <span className="listTitle">{c.name}</span>
                  )}
                  <div className="row" style={{ gap: 4 }}>
                    {editingPrecCatId === c.id ? (
                      <>
                        <button
                          type="button"
                          className="btn"
                          style={smallBtn}
                          disabled={busy}
                          onClick={() => void savePrecCatRename(c.id)}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="btn"
                          style={smallBtn}
                          disabled={busy}
                          onClick={() => setEditingPrecCatId(null)}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="btn"
                          style={smallBtn}
                          disabled={busy}
                          onClick={() => {
                            setEditingPrecCatId(c.id)
                            setEditingPrecCatName(c.name)
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="btn danger"
                          style={smallBtn}
                          disabled={busy}
                          onClick={async () => {
                            const ok = await askConfirm({
                              title: 'Remove category',
                              message: `Remove category “${c.name}”? You cannot remove a category that still has precedents.`,
                              danger: true,
                              confirmLabel: 'Remove',
                            })
                            if (!ok) return
                            setBusy(true)
                            setErr(null)
                            try {
                              await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories/${c.id}`, {
                                token,
                                method: 'DELETE',
                              })
                              const next = await apiFetch<PrecedentCategoryOut[]>(
                                `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                                { token },
                              )
                              setSubPrecCats(next)
                            } catch (e: any) {
                              setErr(e?.message ?? 'Failed to remove category')
                            } finally {
                              setBusy(false)
                            }
                          }}
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {subPrecCats.length === 0 ? (
                <div className="muted" style={{ padding: 8 }}>No categories yet — add one before uploading precedents for this sub-type.</div>
              ) : null}
            </div>
          </div>

        </div>
      )}

    </div>
  )
}

/** Random 6-character lowercase hex for a new custom precedent reference (uniqueness enforced server-side). */
function suggestedPrecedentReferenceHex(): string {
  try {
    const a = new Uint8Array(3)
    crypto.getRandomValues(a)
    return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return Array.from({ length: 6 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
  }
}

function PrecedentNamePencilIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  )
}

function precedentDisplayNameFromFile(file: File): string {
  const stem = file.name.replace(/\.docx$/i, '').trim()
  return stem || file.name
}

function AdminPrecedents({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  /** Reserved references — edit in OnlyOffice; do not delete from Admin. */
  const systemPrecedentReferences = SYSTEM_PRECEDENT_REFERENCES
  const [items, setItems] = useState<PrecedentOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [uploadHeadTypeId, setUploadHeadTypeId] = useState('')
  const [uploadSubTypeId, setUploadSubTypeId] = useState('')
  const [uploadCats, setUploadCats] = useState<PrecedentCategoryOut[]>([])
  const [uploadCatsLoading, setUploadCatsLoading] = useState(false)
  const [uploadCatsFetchErr, setUploadCatsFetchErr] = useState<string | null>(null)
  /** Specific category id, or GLOBAL_PRECEDENT_SCOPE for “all categories under sub-type”. */
  const [uploadCategoryId, setUploadCategoryId] = useState(GLOBAL_PRECEDENT_SCOPE)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reference, setReference] = useState(() => suggestedPrecedentReferenceHex())
  const [kind, setKind] = useState<'letter' | 'email' | 'document'>('letter')
  const [file, setFile] = useState<File | null>(null)
  const [mergePanelOpen, setMergePanelOpen] = useState(false)
  const [mergeRows, setMergeRows] = useState<MergeCodeCatalogOut[]>([])
  const [mergeLoading, setMergeLoading] = useState(false)
  const [mergeSaving, setMergeSaving] = useState(false)
  const [mergeFilter, setMergeFilter] = useState('')
  const [mergeImportKey, setMergeImportKey] = useState(0)
  const [mergeMsg, setMergeMsg] = useState<string | null>(null)
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
  const [firmSettings, setFirmSettings] = useState<FirmSettingsOut | null>(null)
  const [lhBusy, setLhBusy] = useState(false)
  const [lhFileKey, setLhFileKey] = useState(0)
  const [qlhBusy, setQlhBusy] = useState(false)
  const [qlhFileKey, setQlhFileKey] = useState(0)
  const [sigBusy, setSigBusy] = useState(false)
  const [sigFileKey, setSigFileKey] = useState(0)
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

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )

  const uploadSubTypeOptions = useMemo(() => {
    if (!uploadHeadTypeId || uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === uploadHeadTypeId)
    return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
  }, [matterHeads, uploadHeadTypeId])

  const headIsGlobal = uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE

  const uploadHeadTypeDropdownOptions = useMemo(
    () => [
      { value: '', label: '— select —' },
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all cases)' },
      ...matterTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ],
    [matterTypeOptions],
  )

  const uploadSubTypeDropdownOptions = useMemo(() => {
    if (!uploadHeadTypeId) return [{ value: '', label: 'Select a matter type first' }]
    if (headIsGlobal) return [{ value: GLOBAL_PRECEDENT_SCOPE, label: 'Global' }]
    if (uploadSubTypeOptions.length === 0) return [{ value: '', label: 'No sub-types for this matter type' }]
    return [
      { value: '', label: '— select —' },
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all sub-types under this matter type)' },
      ...uploadSubTypeOptions.map((o) => ({ value: o.id, label: o.label })),
    ]
  }, [uploadHeadTypeId, headIsGlobal, uploadSubTypeOptions])

  const uploadCategoryDropdownOptions = useMemo(
    () => [
      { value: GLOBAL_PRECEDENT_SCOPE, label: 'Global (all categories under this sub-type)' },
      ...uploadCats.map((c) => ({ value: c.id, label: c.name })),
    ],
    [uploadCats],
  )
  const uploadBlockers = useMemo(() => {
    const blockers: string[] = []
    if (uploadCatsLoading) blockers.push('Wait for precedent categories to finish loading')
    if (!name.trim()) blockers.push('Enter a precedent name')
    if (!reference.trim()) blockers.push('Enter a reference')
    if (!file) blockers.push('Choose a .docx file to upload')
    if (!uploadHeadTypeId) blockers.push('Select a matter type (or Global)')
    else if (!headIsGlobal && !uploadSubTypeId) blockers.push('Select a sub-type (or Global)')
    else if (
      !headIsGlobal &&
      uploadSubTypeId &&
      uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
      !uploadCategoryId
    ) {
      blockers.push('Select a precedent category (or Global)')
    }
    return blockers
  }, [
    uploadCatsLoading,
    name,
    reference,
    file,
    uploadHeadTypeId,
    headIsGlobal,
    uploadSubTypeId,
    uploadCategoryId,
  ])

  const uploadReady = uploadBlockers.length === 0

  const mergeFiltered = useMemo(() => {
    const q = mergeFilter.trim().toLowerCase()
    if (!q) return mergeRows
    return mergeRows.filter(
      (r) => r.code.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    )
  }, [mergeRows, mergeFilter])

  useEffect(() => {
    if (
      !uploadSubTypeId ||
      uploadSubTypeId === GLOBAL_PRECEDENT_SCOPE ||
      uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE
    ) {
      setUploadCats([])
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCatsFetchErr(null)
      return
    }
    setUploadCatsLoading(true)
    setUploadCatsFetchErr(null)
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${uploadSubTypeId}/precedent-categories`, { token })
      .then((list) => {
        setUploadCats(list)
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      })
      .catch((e: unknown) => {
        setUploadCats([])
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
        setUploadCatsFetchErr((e as ApiError)?.message ?? 'Could not load precedent categories for this sub-type')
      })
      .finally(() => setUploadCatsLoading(false))
  }, [uploadSubTypeId, uploadHeadTypeId, token])

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const [data, heads, firm] = await Promise.all([
        apiFetch<PrecedentOut[]>('/precedents', { token }),
        apiFetch<MatterHeadTypeOut[]>('/matter-types', { token }),
        apiFetch<FirmSettingsOut>('/admin/firm-settings', { token }),
      ])
      setItems(data)
      setMatterHeads(heads)
      setFirmSettings(firm)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load precedents')
    } finally {
      setBusy(false)
    }
  }

  async function loadMergeCatalog() {
    setMergeLoading(true)
    setMergeMsg(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', { token })
      setMergeRows(rows)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not load merge codes')
    } finally {
      setMergeLoading(false)
    }
  }

  async function saveMergeCatalog() {
    setMergeSaving(true)
    setMergeMsg(null)
    setErr(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', {
        token,
        method: 'PATCH',
        json: { items: mergeRows.map((r) => ({ code: r.code, description: r.description })) },
      })
      setMergeRows(rows)
      setMergeMsg(`Saved ${rows.length} codes.`)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Save merge codes failed')
    } finally {
      setMergeSaving(false)
    }
  }

  async function exportMergeCatalog() {
    setMergeMsg(null)
    try {
      const auth = String(token ?? '').trim()
      if (!auth) throw new Error('You are not signed in. Refresh the page and log in again.')
      const xh = new Headers()
      applyAuthHeaders(xh, auth)
      const res = await fetch(apiUrl('/admin/merge-codes/export.xlsx'), { headers: xh })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const msg = typeof body?.detail === 'string' ? body.detail : `Export failed (${res.status})`
        throw new Error(msg)
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'canary-merge-codes.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
      setMergeMsg('Download started.')
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Export failed')
    }
  }

  async function importMergeCatalogFile(f: File) {
    setMergeSaving(true)
    setMergeMsg(null)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<MergeCodeCatalogImportResult>('/admin/merge-codes/import', {
        token,
        method: 'POST',
        body: fd,
      })
      setMergeMsg(
        `Import: updated ${body.updated ?? 0} row(s); ${body.skipped_unknown ?? 0} unknown code(s) skipped.`,
      )
      await loadMergeCatalog()
      setMergeImportKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Import failed')
    } finally {
      setMergeSaving(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  useEffect(() => {
    if (mergePanelOpen) void loadMergeCatalog()
  }, [mergePanelOpen, token])

  async function patchLetterheadStyle(next: LetterheadStyle) {
    setLhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { letterhead_style: next },
      })
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not update letterhead mode')
    } finally {
      setLhBusy(false)
    }
  }

  async function uploadLetterheadFile(f: File) {
    setLhBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', {
        token,
        method: 'POST',
        body: fd,
      })
      setFirmSettings(body)
      await load()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Letterhead upload failed')
    } finally {
      setLhBusy(false)
    }
  }

  async function clearLetterheadFile() {
    setLhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', { token, method: 'DELETE' })
      await load()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not remove letterhead file')
    } finally {
      setLhBusy(false)
    }
  }

  async function patchQuoteLetterheadStyle(next: LetterheadStyle) {
    setQlhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { quote_letterhead_style: next },
      })
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not update quote letterhead mode')
    } finally {
      setQlhBusy(false)
    }
  }

  async function uploadQuoteLetterheadFile(f: File) {
    setQlhBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/quote-letterhead', {
        token,
        method: 'POST',
        body: fd,
      })
      setFirmSettings(body)
      await load()
      setQlhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Quote letterhead upload failed')
    } finally {
      setQlhBusy(false)
    }
  }

  async function clearQuoteLetterheadFile() {
    setQlhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/quote-letterhead', { token, method: 'DELETE' })
      await load()
      setQlhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not remove quote letterhead file')
    } finally {
      setQlhBusy(false)
    }
  }

  async function patchDefaultSignatureScale(scale: number) {
    if (!firmSettings) return
    setSigBusy(true)
    setErr(null)
    try {
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { default_signature_scale: scale },
      })
      setFirmSettings(body)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not save signature scale')
    } finally {
      setSigBusy(false)
    }
  }

  async function uploadDefaultSignatureFile(f: File) {
    setSigBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/default-signature', {
        token,
        method: 'POST',
        body: fd,
      })
      setFirmSettings(body)
      await load()
      setSigFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Signature upload failed')
    } finally {
      setSigBusy(false)
    }
  }

  async function clearDefaultSignatureFile() {
    setSigBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/default-signature', { token, method: 'DELETE' })
      await load()
      setSigFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not remove signature image')
    } finally {
      setSigBusy(false)
    }
  }

  useEffect(() => {
    if (uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) {
      setUploadSubTypeId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
    }
  }, [uploadHeadTypeId])

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
      setErr('Reference cannot be empty.')
      return
    }
    if (v === p.reference) {
      setReferenceEditId(null)
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/precedents/${p.id}`, { token, method: 'PATCH', json: { reference: v } })
      setReferenceEditId(null)
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Failed to update reference')
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
    setErr(null)
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
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Failed to update scope')
    } finally {
      setBusy(false)
    }
  }

  const scopeEditHeadIsGlobal = scopeEditHead === GLOBAL_PRECEDENT_SCOPE
  const scopeEditSubOptions = useMemo(() => {
    if (!scopeEditHead || scopeEditHead === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === scopeEditHead)
    return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
  }, [matterHeads, scopeEditHead])

  async function commitPrecedentNameEdit(p: PrecedentOut) {
    const v = nameDraft.trim()
    if (!v) {
      setErr('Name cannot be empty.')
      return
    }
    if (v === p.name) {
      setNameEditId(null)
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/precedents/${p.id}`, {
        token,
        method: 'PATCH',
        json: { name: v },
      })
      setNameEditId(null)
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Failed to update name')
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
                    setErr(null)
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
                    .then(() => load())
                    .catch((e: any) => setErr(e?.message ?? 'Delete failed'))
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

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Precedents</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Letterhead (Letter precedents only)</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          <strong>Digital</strong> copies the uploaded .docx <strong>headers and footers</strong> into each{' '}
          <strong>Letter</strong> precedent before merge codes run. Keep logos and firm blocks in the header/footer so the
          letter body can sit on page 1 underneath. <strong>Pre-printed</strong> skips any overlay (headed stationery).
          Embedded logos in the uploaded .docx are copied into each composed letter automatically.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'preprinted'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('preprinted')}
                />
                Pre-printed
              </label>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'digital'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('digital')}
                />
                Digital
              </label>
            </div>
            {firmSettings.letterhead_style === 'digital' ? (
              <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <label className="btn" style={{ cursor: lhBusy ? 'not-allowed' : 'pointer' }}>
                  Browse…
                  <input
                    key={lhFileKey}
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={lhBusy}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void uploadLetterheadFile(f)
                    }}
                  />
                </label>
                <span className="muted">
                  {firmSettings.letterhead_original_filename
                    ? `Current file: ${firmSettings.letterhead_original_filename}`
                    : 'No .docx uploaded yet.'}
                </span>
                {firmSettings.letterhead_original_filename ? (
                  <>
                    <button
                      type="button"
                      className="btn"
                      disabled={lhBusy}
                      onClick={() => openOnlyOfficeFirmLetterheadEditor('letterhead')}
                    >
                      Edit in OnlyOffice
                    </button>
                    <button type="button" className="btn danger" disabled={lhBusy} onClick={() => void clearLetterheadFile()}>
                      Remove letterhead file
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="muted">Loading letterhead settings…</div>
        )}
      </div>

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Quote letterhead</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          The <strong>quote body layout</strong> (text, fee-table merge codes) is edited under <strong>Precedents</strong>{' '}
          as <strong>Quote template</strong> (<code>QUOTE_TEMPLATE</code>). When <strong>Digital</strong> is selected,
          upload a .docx whose <strong>header and footer</strong> contain your logo and firm details — Canary copies those
          onto every new quote document. The letterhead file should not need the fee table; keep that in the quote template
          precedent. Covering letters sent after creating a quote use your normal letter precedents and firm letterhead.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: qlhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="quote-letterhead-style"
                  checked={(firmSettings.quote_letterhead_style ?? 'preprinted') === 'preprinted'}
                  disabled={qlhBusy}
                  onChange={() => void patchQuoteLetterheadStyle('preprinted')}
                />
                Pre-printed
              </label>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: qlhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="quote-letterhead-style"
                  checked={(firmSettings.quote_letterhead_style ?? 'preprinted') === 'digital'}
                  disabled={qlhBusy}
                  onChange={() => void patchQuoteLetterheadStyle('digital')}
                />
                Digital
              </label>
            </div>
            {(firmSettings.quote_letterhead_style ?? 'preprinted') === 'digital' ? (
              <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <label className="btn" style={{ cursor: qlhBusy ? 'not-allowed' : 'pointer' }}>
                  Browse…
                  <input
                    key={qlhFileKey}
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={qlhBusy}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void uploadQuoteLetterheadFile(f)
                    }}
                  />
                </label>
                <span className="muted">
                  {firmSettings.quote_letterhead_original_filename
                    ? `Current file: ${firmSettings.quote_letterhead_original_filename}`
                    : 'No .docx uploaded yet.'}
                </span>
                {firmSettings.quote_letterhead_original_filename ? (
                  <>
                    <button
                      type="button"
                      className="btn"
                      disabled={qlhBusy}
                      onClick={() => openOnlyOfficeFirmLetterheadEditor('quote_letterhead')}
                    >
                      Edit in OnlyOffice
                    </button>
                    <button type="button" className="btn danger" disabled={qlhBusy} onClick={() => void clearQuoteLetterheadFile()}>
                      Remove letterhead file
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="muted">Loading quote letterhead settings…</div>
        )}
      </div>

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Default signature</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          Upload a firm-wide default e-signature for merge code{' '}
          <code>[FEE_EARNER_SIGNATURE]</code>. Used when the fee earner has not uploaded their own signature in user
          settings. Individual users can override this with their own signature image.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <label className="muted" style={{ minWidth: 120 }}>
                Size in letters
              </label>
              <input
                type="range"
                min={1}
                max={10}
                value={firmSettings.default_signature_scale ?? 7}
                disabled={sigBusy}
                onChange={(ev) => void patchDefaultSignatureScale(Number(ev.target.value))}
              />
              <span style={{ minWidth: 88, textAlign: 'right' }}>
                {firmSettings.default_signature_scale ?? 7} / 10
              </span>
            </div>
            <div className="muted">
              About{' '}
              {(((2 * (firmSettings.default_signature_scale ?? 7)) / 7).toFixed(2))} inches wide in composed documents
            </div>
            <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <label className="btn" style={{ cursor: sigBusy ? 'not-allowed' : 'pointer' }}>
                Upload signature…
                <input
                  key={sigFileKey}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
                  disabled={sigBusy}
                  style={{ display: 'none' }}
                  onChange={(ev) => {
                    const f = ev.target.files?.[0]
                    ev.target.value = ''
                    if (f) void uploadDefaultSignatureFile(f)
                  }}
                />
              </label>
              <span className="muted">
                {firmSettings.default_signature_configured
                  ? `Current file: ${firmSettings.default_signature_original_filename ?? 'signature image'}`
                  : 'No default signature uploaded yet.'}
              </span>
              {firmSettings.default_signature_configured ? (
                <button
                  type="button"
                  className="btn danger"
                  disabled={sigBusy}
                  onClick={() => void clearDefaultSignatureFile()}
                >
                  Remove signature
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="muted">Loading default signature settings…</div>
        )}
      </div>

      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Universal templates (e.g. <strong>Blank (no precedent)</strong> for letters,{' '}
          <strong>Blank e-mail (no precedent)</strong> for e-mails, <strong>Invoice template</strong>,{' '}
          <strong>Completion statement template</strong>) ship with Canary and are always shown at the top of the
          precedent library below. Edit them in OnlyOffice like any other precedent. Firm-specific letterheads are
          configured in the cards above.
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>
          Upload a template. Choose <strong>Global</strong> at any level to widen availability: <strong>Matter type</strong>{' '}
          Global = all cases; <strong>Sub-type</strong> Global = all sub-types under the chosen matter type;{' '}
          <strong>Precedent category</strong> Global = all categories under the chosen sub-type. Otherwise pick a specific
          value. Add named categories under <strong>Admin → Matters</strong> if you need a specific category.
        </div>
        {uploadCatsFetchErr ? <div className="error" style={{ marginBottom: 8 }}>{uploadCatsFetchErr}</div> : null}
        <div className="stack">
          <label className="field">
            <span>Name (required)</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              aria-required
              placeholder="e.g. Purchase exchange letter"
            />
          </label>
          <label className="field">
            <span>Reference</span>
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="mono"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={200}
                required
                aria-required
                autoComplete="off"
                spellCheck={false}
                placeholder="e.g. a1f9c2"
                title="Required. Must be unique among precedents."
              />
              <button
                type="button"
                className="btn"
                disabled={busy}
                title="Replace with another random 6-character hex"
                onClick={() => setReference(suggestedPrecedentReferenceHex())}
              >
                New suggestion
              </button>
            </div>
            <span className="muted" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              Required for every custom precedent. A random 6-character hex is suggested; change it if you prefer. Must be
              unique.
            </span>
          </label>
          <SingleSelectDropdown
            label="Type"
            options={[
              { value: 'letter', label: 'Letter' },
              { value: 'email', label: 'E-mail' },
              { value: 'document', label: 'Document' },
            ]}
            value={kind}
            onChange={(v) => setKind(v as typeof kind)}
          />
          <SingleSelectDropdown
            label="Matter type"
            options={uploadHeadTypeDropdownOptions}
            value={uploadHeadTypeId}
            onChange={(v) => {
              setUploadHeadTypeId(v)
              setUploadSubTypeId('')
              setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
            }}
            disabled={busy}
            placeholder="— select —"
          />
          <SingleSelectDropdown
            label="Sub-type"
            options={uploadSubTypeDropdownOptions}
            value={uploadSubTypeId}
            onChange={(v) => {
              setUploadSubTypeId(v)
              setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
            }}
            disabled={busy || !uploadHeadTypeId || headIsGlobal}
            placeholder="— select —"
          />
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          uploadCatsLoading ? (
            <div className="muted" style={{ fontSize: 13 }}>
              Loading precedent categories…
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading &&
          !uploadCatsFetchErr &&
          uploadCats.length === 0 ? (
            <div
              className="muted"
              style={{
                fontSize: 13,
                padding: '8px 10px',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'var(--panel)',
              }}
            >
              No named precedent categories exist for this sub-type. You can still choose{' '}
              <strong>Global</strong> above to apply to all categories, or add categories under{' '}
              <strong>Admin → Matters</strong>.
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading ? (
            <SingleSelectDropdown
              label="Precedent category"
              options={uploadCategoryDropdownOptions}
              value={uploadCategoryId}
              onChange={setUploadCategoryId}
              disabled={busy}
            />
          ) : null}
          <label className="field">
            <span>File</span>
            <input
              key={fileInputKey}
              type="file"
              accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f && !name.trim()) {
                  setName(precedentDisplayNameFromFile(f))
                }
              }}
            />
          </label>
          {uploadBlockers.length > 0 ? (
            <div className="muted" style={{ fontSize: 13 }}>
              Before uploading: {uploadBlockers.join(' · ')}
            </div>
          ) : null}
          <button
            type="button"
            className="btn primary"
            disabled={busy || !uploadReady}
            onClick={async () => {
              if (!uploadReady || !file) {
                setErr(uploadBlockers[0] ?? 'Complete the form before uploading')
                return
              }
              setBusy(true)
              setErr(null)
              try {
                let mh: string = GLOBAL_PRECEDENT_SCOPE
                let ms: string = GLOBAL_PRECEDENT_SCOPE
                let mc: string = GLOBAL_PRECEDENT_SCOPE
                if (uploadHeadTypeId && uploadHeadTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                  mh = uploadHeadTypeId
                  if (uploadSubTypeId && uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                    ms = uploadSubTypeId
                    mc = uploadCategoryId || GLOBAL_PRECEDENT_SCOPE
                  } else {
                    ms = GLOBAL_PRECEDENT_SCOPE
                    mc = GLOBAL_PRECEDENT_SCOPE
                  }
                }
                const fd = new FormData()
                fd.set('name', name.trim())
                fd.set('reference', reference.trim())
                fd.set('kind', kind)
                fd.set('matter_head_type_id', mh)
                fd.set('matter_sub_type_id', ms)
                fd.set('category_id', mc)
                fd.set('upload', file)
                if (!String(token ?? '').trim()) {
                  throw new Error('You are not signed in or your session token is empty. Refresh the page and log in again.')
                }
                await apiFetch<PrecedentOut>('/precedents', { token, method: 'POST', body: fd })
                setName('')
                setReference(suggestedPrecedentReferenceHex())
                setFile(null)
                setFileInputKey((k) => k + 1)
                await load()
              } catch (e: unknown) {
                setErr((e as { message?: string }).message ?? 'Upload failed')
              } finally {
                setBusy(false)
              }
            }}
          >
            Upload
          </button>
        </div>
      </div>
      <div className="card" style={{ padding: 12 }}>
        <div
          className="row"
          style={{
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: mergePanelOpen ? 8 : 0,
            gap: 12,
          }}
        >
          <div className="stack" style={{ gap: 10, flex: 1, minWidth: 0 }}>
            <span className="muted" style={{ fontSize: 13 }}>
              Merge codes — stored in the database; edit descriptions here or round-trip via Excel. Codes themselves
              come from Canary releases (sync on startup).
            </span>
            <div
              style={{
                fontSize: 13,
                padding: '10px 12px',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'var(--panel)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Formatting modifiers</div>
              <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
                Optional prefix before a code in Word templates. Plain <code>[CODE]</code> merges without extra
                formatting.
              </p>
              <table
                className="allow-select"
                style={{ width: '100%', maxWidth: 420, borderCollapse: 'collapse', fontSize: 12 }}
              >
                <thead>
                  <tr>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '4px 8px 4px 0',
                        borderBottom: '1px solid var(--border)',
                        fontWeight: 600,
                        width: '28%',
                      }}
                    >
                      Modifier
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '4px 0',
                        borderBottom: '1px solid var(--border)',
                        fontWeight: 600,
                      }}
                    >
                      Effect on merged value
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>b:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Bold</td>
                  </tr>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>i:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Italic</td>
                  </tr>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>u:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Underline</td>
                  </tr>
                </tbody>
              </table>
              <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
                Combine modifiers in any order, e.g. <code>[bi:LAST_NAME]</code> (bold + italic) or{' '}
                <code>[biu:MATTER_DESCRIPTION]</code> (all three). Example:{' '}
                <code>Re: [b:MATTER_DESCRIPTION]</code>
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn"
            style={{ fontSize: 12, flexShrink: 0 }}
            onClick={() => {
              setMergePanelOpen((v) => !v)
              if (mergePanelOpen) setMergeMsg(null)
            }}
          >
            {mergePanelOpen ? 'Hide' : 'View/Edit'}
          </button>
        </div>
        {mergePanelOpen ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="mergeCatalogToolbar">
              <span className="mergeCatalogToolbarLabel muted">Filter</span>
              <div className="mergeCatalogToolbarControls">
                <input
                  className="mergeCatalogToolbarInput"
                  value={mergeFilter}
                  onChange={(e) => setMergeFilter(e.target.value)}
                  placeholder="Code or description…"
                  disabled={mergeLoading || mergeSaving}
                />
                <div className="mergeCatalogToolbarActions">
                  <button
                    type="button"
                    className="btn primary"
                    disabled={mergeLoading || mergeSaving || mergeRows.length === 0}
                    onClick={() => void saveMergeCatalog()}
                  >
                    Save descriptions
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={mergeLoading || mergeSaving}
                    onClick={() => void exportMergeCatalog()}
                  >
                    Export Excel
                  </button>
                  <label className="btn" style={{ cursor: mergeSaving ? 'not-allowed' : 'pointer' }}>
                    Import Excel…
                    <input
                      key={mergeImportKey}
                      type="file"
                      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                      disabled={mergeSaving}
                      style={{ display: 'none' }}
                      onChange={(ev) => {
                        const f = ev.target.files?.[0]
                        ev.target.value = ''
                        if (f) void importMergeCatalogFile(f)
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn"
                    disabled={mergeLoading}
                    onClick={() => void loadMergeCatalog()}
                  >
                    Reload
                  </button>
                </div>
              </div>
            </div>
            {mergeMsg ? <div className="muted" style={{ fontSize: 13 }}>{mergeMsg}</div> : null}
            {mergeLoading ? (
              <div className="muted">Loading merge codes…</div>
            ) : (
              <div
                style={{
                  maxHeight: 420,
                  overflow: 'auto',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  background: 'var(--panel)',
                }}
              >
                <table
                  className="allow-select"
                  style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}
                >
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--panel2)', zIndex: 1 }}>
                    <tr>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '8px',
                          borderBottom: '1px solid var(--border)',
                          width: '22%',
                          color: 'var(--text)',
                          fontWeight: 600,
                        }}
                      >
                        Code
                      </th>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '8px',
                          borderBottom: '1px solid var(--border)',
                          color: 'var(--text)',
                          fontWeight: 600,
                        }}
                      >
                        Description (editable)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mergeFiltered.map((r) => (
                      <tr key={r.code}>
                        <td
                          style={{
                            padding: '6px 8px',
                            fontFamily: 'monospace',
                            color: 'var(--text)',
                            verticalAlign: 'top',
                            borderBottom: '1px solid var(--border)',
                          }}
                        >
                          {r.code}
                        </td>
                        <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                          <textarea
                            value={r.description}
                            rows={2}
                            disabled={mergeSaving}
                            style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                            onChange={(e) => {
                              const v = e.target.value
                              setMergeRows((prev) => prev.map((x) => (x.code === r.code ? { ...x, description: v } : x)))
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {mergeFiltered.length === 0 && mergeRows.length > 0 ? (
                  <div className="muted" style={{ padding: 12 }}>
                    No rows match the filter.
                  </div>
                ) : null}
                {!mergeLoading && mergeRows.length === 0 ? (
                  <div className="muted" style={{ padding: 12 }}>
                    No catalog rows yet — ensure the backend has run a migration and restarted so merge codes sync from the
                    server defaults.
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </div>
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
    </div>
  )
}
function AdminMatterContacts({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<MatterContactTypeOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newSort, setNewSort] = useState(90)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const r = await apiFetch<MatterContactTypeOut[]>('/admin/matter-contact-types', { token })
      setRows(r)
    } catch (e: unknown) {
      setErr((e as ApiError)?.message ?? 'Failed to load contact types')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Contacts</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}
      <p className="muted" style={{ marginTop: 0 }}>
        These labels populate the matter contact type dropdown. The four system types (Client, Lawyers, New lender,
        Existing lender) cannot be deleted or renamed.
      </p>
      <div className="card stack" style={{ gap: 10, maxWidth: 720 }}>
        <div className="muted" style={{ fontWeight: 600 }}>
          Add type
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: '1 1 140px', marginBottom: 0 }}>
            <span>Slug</span>
            <input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              placeholder="e.g. surveyor"
              disabled={busy}
            />
          </label>
          <label className="field" style={{ flex: '1 1 160px', marginBottom: 0 }}>
            <span>Label</span>
            <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} disabled={busy} />
          </label>
          <label className="field" style={{ flex: '0 0 80px', marginBottom: 0 }}>
            <span>Sort</span>
            <input type="number" value={newSort} onChange={(e) => setNewSort(Number(e.target.value))} disabled={busy} />
          </label>
          <button
            type="button"
            className="btn primary"
            disabled={busy || !newSlug.trim() || !newLabel.trim()}
            onClick={async () => {
              setBusy(true)
              setErr(null)
              try {
                await apiFetch('/admin/matter-contact-types', {
                  token,
                  method: 'POST',
                  json: { slug: newSlug.trim(), label: newLabel.trim(), sort_order: newSort },
                })
                setNewSlug('')
                setNewLabel('')
                await load()
              } catch (e: unknown) {
                setErr((e as ApiError)?.message ?? 'Could not add contact type')
              } finally {
                setBusy(false)
              }
            }}
          >
            Add
          </button>
        </div>
      </div>
      <div className="list" style={{ marginTop: 12 }}>
        {rows.map((r) => (
          <div
            key={r.id}
            className="listCard row"
            style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12 }}
          >
            <div style={{ minWidth: 0 }}>
              <div className="listTitle">
                {r.label}{' '}
                {r.is_system ? (
                  <span className="muted" style={{ fontSize: 12 }}>
                    (system)
                  </span>
                ) : null}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                slug: <span className="mono">{r.slug}</span> · sort {r.sort_order}
              </div>
            </div>
            {!r.is_system ? (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={async () => {
                  const ok = await askConfirm({
                    title: 'Delete contact type',
                    message: `Remove “${r.label}”? Existing matter contacts keep this slug until edited.`,
                    danger: true,
                    confirmLabel: 'Delete',
                  })
                  if (!ok) return
                  setBusy(true)
                  setErr(null)
                  try {
                    await apiFetch(`/admin/matter-contact-types/${r.id}`, { token, method: 'DELETE' })
                    await load()
                  } catch (e: unknown) {
                    setErr((e as ApiError)?.message ?? 'Delete failed')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Delete
              </button>
            ) : (
              <span className="muted" style={{ fontSize: 13 }}>
                Cannot delete
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function AdminConsole({ token, refreshMe }: { token: string; refreshMe: () => Promise<void> }) {
  const [tab, setTab] = useState<
    | 'firm'
    | 'users'
    | 'matters'
    | 'billing'
    | 'email'
    | 'docusign'
    | 'portalForms'
    | 'deploy'
    | 'submenus'
    | 'tasks'
    | 'contacts'
    | 'precedents'
    | 'audit'
  >('firm')
  const adminSubtitle =
    tab === 'firm'
      ? 'Trading name, registered name, and firm address for precedent merge codes.'
      : tab === 'email'
      ? 'Org-wide e-mail integration (mailto vs Microsoft 365).'
      : tab === 'docusign'
        ? 'DocuSign integration credentials and send options.'
        : tab === 'portalForms'
          ? 'Portal form templates sent manually to clients.'
          : tab === 'deploy'
        ? 'Deploy, updates, and file storage usage.'
        : tab === 'audit'
        ? 'Activity and audit trail.'
        : tab === 'users'
          ? 'User accounts and permission categories.'
          : tab === 'matters'
            ? 'Matter types and defaults.'
            : tab === 'billing'
              ? 'Billing configuration.'
              : tab === 'submenus'
                ? 'Case sub-menu configuration.'
                : tab === 'tasks'
                  ? 'Task templates and defaults.'
                  : tab === 'contacts'
                    ? 'Matter contact types.'
                    : tab === 'precedents'
                      ? 'Precedent library.'
                      : ''
  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Admin Settings</h2>
          <div className="muted" style={{ marginTop: 4 }}>{adminSubtitle}</div>
        </div>
        <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
          <button type="button" className={`navBtn ${tab === 'firm' ? 'active' : ''}`} onClick={() => setTab('firm')}>
            Firm details
          </button>
          <button type="button" className={`navBtn ${tab === 'users' ? 'active' : ''}`} onClick={() => setTab('users')}>
            Users
          </button>
          <button type="button" className={`navBtn ${tab === 'matters' ? 'active' : ''}`} onClick={() => setTab('matters')}>
            Matters
          </button>
          <button type="button" className={`navBtn ${tab === 'billing' ? 'active' : ''}`} onClick={() => setTab('billing')}>
            Billing
          </button>
          <button type="button" className={`navBtn ${tab === 'email' ? 'active' : ''}`} onClick={() => setTab('email')}>
            E-mail
          </button>
          <button type="button" className={`navBtn ${tab === 'docusign' ? 'active' : ''}`} onClick={() => setTab('docusign')}>
            DocuSign
          </button>
          <button type="button" className={`navBtn ${tab === 'portalForms' ? 'active' : ''}`} onClick={() => setTab('portalForms')}>
            Portal forms
          </button>
          <button type="button" className={`navBtn ${tab === 'deploy' ? 'active' : ''}`} onClick={() => setTab('deploy')}>
            Deploy
          </button>
          <button type="button" className={`navBtn ${tab === 'submenus' ? 'active' : ''}`} onClick={() => setTab('submenus')}>
            Sub-Menus
          </button>
          <button type="button" className={`navBtn ${tab === 'tasks' ? 'active' : ''}`} onClick={() => setTab('tasks')}>
            Tasks
          </button>
          <button type="button" className={`navBtn ${tab === 'contacts' ? 'active' : ''}`} onClick={() => setTab('contacts')}>
            Contacts
          </button>
          <button type="button" className={`navBtn ${tab === 'precedents' ? 'active' : ''}`} onClick={() => setTab('precedents')}>
            Precedents
          </button>
          <button type="button" className={`navBtn ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
            Audit
          </button>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        {tab === 'firm' ? (
          <AdminFirmDetails token={token} />
        ) : tab === 'users' ? (
          <AdminUsers token={token} embedded />
        ) : tab === 'matters' ? (
          <AdminMatters token={token} />
        ) : tab === 'billing' ? (
          <AdminBilling token={token} />
        ) : tab === 'email' ? (
          <AdminEmail token={token} onSaved={() => void refreshMe()} />
        ) : tab === 'docusign' ? (
          <AdminDocuSign token={token} />
        ) : tab === 'portalForms' ? (
          <AdminPortalForms token={token} />
        ) : tab === 'deploy' ? (
          <AdminDeploy token={token} />
        ) : tab === 'submenus' ? (
          <AdminSubMenus token={token} />
        ) : tab === 'tasks' ? (
          <AdminTasks token={token} />
        ) : tab === 'contacts' ? (
          <AdminMatterContacts token={token} />
        ) : tab === 'precedents' ? (
          <AdminPrecedents token={token} />
        ) : (
          <AdminAudit token={token} embedded />
        )}
      </div>
    </div>
  )
}

export function AdminUsers({ token, embedded }: { token: string; embedded?: boolean; recoveryMode?: boolean }) {
  const { askConfirm, alert: showAlert } = useDialogs()
  const [users, setUsers] = useState<AdminUserPublic[]>([])
  const [categories, setCategories] = useState<UserPermissionCategoryOut[]>([])
  const [firmSettings, setFirmSettings] = useState<FirmSettingsOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [newInitials, setNewInitials] = useState('')
  const [newJobTitle, setNewJobTitle] = useState('')
  const [newUserCategoryId, setNewUserCategoryId] = useState('')
  const [creatingUser, setCreatingUser] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUserPublic | null>(null)
  const [editEmail, setEditEmail] = useState('')
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editInitials, setEditInitials] = useState('')
  const [editJobTitle, setEditJobTitle] = useState('')
  const [editChargeRateStr, setEditChargeRateStr] = useState('')
  const [editRole, setEditRole] = useState<'admin' | 'user'>('user')
  const [editActive, setEditActive] = useState(true)
  const [editCategoryId, setEditCategoryId] = useState('')
  const [editPw, setEditPw] = useState('')
  const [editPw2, setEditPw2] = useState('')
  const [newCatName, setNewCatName] = useState('')
  const [newCat, setNewCat] = useState({
    perm_fee_earner: false,
    perm_post_client: false,
    perm_post_office: false,
    perm_post_anticipated: false,
    perm_approve_payments: false,
    perm_approve_invoices: false,
    perm_admin: false,
  })
  const [editCatId, setEditCatId] = useState<string | null>(null)
  const [editCatName, setEditCatName] = useState('')
  const [editCat, setEditCat] = useState({
    perm_fee_earner: false,
    perm_post_client: false,
    perm_post_office: false,
    perm_post_anticipated: false,
    perm_approve_payments: false,
    perm_approve_invoices: false,
    perm_admin: false,
  })

  const permissionCategoryOptions = useMemo(
    () => categories.map((c) => ({ value: c.id, label: c.name })),
    [categories],
  )

  const editPermissionCategoryOptions = useMemo(
    () => [
      {
        value: '',
        label: editRole === 'admin' ? '— None —' : '— Select category —',
      },
      ...permissionCategoryOptions,
    ],
    [editRole, permissionCategoryOptions],
  )

  const passwordRotationOptions = useMemo(
    () => [
      { value: '30', label: '30 days' },
      { value: '60', label: '60 days' },
      { value: '90', label: '90 days' },
      { value: '180', label: '180 days' },
      { value: '365', label: '365 days' },
    ],
    [],
  )

  async function load(): Promise<AdminUserPublic[] | null> {
    setBusy(true)
    setErr(null)
    try {
      const [u, c, f] = await Promise.all([
        apiFetch<AdminUserPublic[]>('/admin/users', { token }),
        apiFetch<UserPermissionCategoryOut[]>('/admin/permission-categories', { token }),
        apiFetch<FirmSettingsOut>('/admin/firm-settings', { token }),
      ])
      setUsers(u)
      setCategories(c)
      setFirmSettings(f)
      const feeEarnerDefault = c.find((cat) => cat.is_builtin_template && cat.name === 'Fee earner')
      if (feeEarnerDefault) {
        setNewUserCategoryId((prev) => prev || feeEarnerDefault.id)
      }
      return u
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load users')
      return null
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  function openUserEditor(u: AdminUserPublic) {
    setErr(null)
    setEditingUser(u)
    setEditEmail(u.email)
    setEditDisplayName(u.display_name)
    setEditInitials(u.initials ?? '')
    setEditJobTitle(u.job_title ?? '')
    setEditChargeRateStr(
      u.charge_rate_pence_per_hour != null ? (u.charge_rate_pence_per_hour / 100).toFixed(2) : '',
    )
    setEditRole(u.role)
    setEditActive(u.is_active)
    setEditCategoryId(u.permission_category_id ?? '')
    setEditPw('')
    setEditPw2('')
  }

  return (
    <div className="stack">
      <div className="paneHead">
        {embedded ? <h3 style={{ margin: 0 }}>Users</h3> : <h2>Admin · Users</h2>}
        <button type="button" className="btn" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {err && !editingUser ? <div className="error">{err}</div> : null}
      <div className="card">
        <h3>User categories</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Assign each user to a category to control fee-earner status, ledger posting, and approvals.{' '}
          <strong>Fee earner</strong> and <strong>Cashier</strong> are default templates on every deployment — you
          may edit their permissions or delete them (reassign users first).
        </p>
        <div className="stack" style={{ gap: 10, maxWidth: 720 }}>
          <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
            <label className="field" style={{ flex: '1 1 200px', marginBottom: 0 }}>
              <span>New category name</span>
              <input value={newCatName} onChange={(e) => setNewCatName(e.target.value)} disabled={busy} />
            </label>
            <button
              type="button"
              className="btn primary"
              disabled={busy || !newCatName.trim()}
              onClick={async () => {
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch('/admin/permission-categories', {
                    token,
                    method: 'POST',
                    json: { name: newCatName.trim(), ...newCat },
                  })
                  setNewCatName('')
                  await load()
                } catch (e: any) {
                  setErr(e?.message ?? 'Could not create category')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Add category
            </button>
          </div>
          <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
            {(
              [
                ['perm_fee_earner', 'Fee-earner files'],
                ['perm_post_client', 'Post client'],
                ['perm_post_office', 'Post office'],
                ['perm_post_anticipated', 'Post anticipated'],
                ['perm_approve_payments', 'Approve payments'],
                ['perm_approve_invoices', 'Approve invoices'],
                ['perm_admin', 'Admin'],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="row" style={{ gap: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={newCat[k]}
                  disabled={busy}
                  onChange={(e) => setNewCat((p) => ({ ...p, [k]: e.target.checked }))}
                />
                <span style={{ fontSize: 13 }}>{label}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="list" style={{ marginTop: 12 }}>
          {categories.map((c) => (
            <div key={c.id} className="listCard stack" style={{ gap: 10 }}>
              {editCatId === c.id ? (
                <div className="stack" style={{ gap: 10 }}>
                  <label className="field" style={{ marginBottom: 0 }}>
                    <span>Category name</span>
                    <input value={editCatName} onChange={(e) => setEditCatName(e.target.value)} disabled={busy} />
                  </label>
                  <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
                    {(
                      [
                        ['perm_fee_earner', 'Fee-earner files'],
                        ['perm_post_client', 'Post client'],
                        ['perm_post_office', 'Post office'],
                        ['perm_post_anticipated', 'Post anticipated'],
                        ['perm_approve_payments', 'Approve payments'],
                        ['perm_approve_invoices', 'Approve invoices'],
                        ['perm_admin', 'Admin'],
                      ] as const
                    ).map(([k, label]) => (
                      <label key={k} className="row" style={{ gap: 6, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={editCat[k]}
                          disabled={busy}
                          onChange={(e) => setEditCat((p) => ({ ...p, [k]: e.target.checked }))}
                        />
                        <span style={{ fontSize: 13 }}>{label}</span>
                      </label>
                    ))}
                  </div>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={busy || !editCatName.trim()}
                      onClick={async () => {
                        setBusy(true)
                        setErr(null)
                        try {
                          await apiFetch(`/admin/permission-categories/${c.id}`, {
                            token,
                            method: 'PATCH',
                            json: {
                              name: editCatName.trim(),
                              perm_fee_earner: editCat.perm_fee_earner,
                              perm_post_client: editCat.perm_post_client,
                              perm_post_office: editCat.perm_post_office,
                              perm_post_anticipated: editCat.perm_post_anticipated,
                              perm_approve_payments: editCat.perm_approve_payments,
                              perm_approve_invoices: editCat.perm_approve_invoices,
                              perm_admin: editCat.perm_admin,
                            },
                          })
                          setEditCatId(null)
                          await load()
                        } catch (e: any) {
                          setErr(e?.message ?? 'Could not update category')
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Save changes
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => setEditCatId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <div>
                    <div className="listTitle">
                      {c.name}
                      {c.is_builtin_template ? (
                        <span className="muted" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
                          Default template
                        </span>
                      ) : null}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {[
                        c.perm_fee_earner ? 'Fee-earner' : null,
                        c.perm_post_client ? 'Client post' : null,
                        c.perm_post_office ? 'Office post' : null,
                        c.perm_post_anticipated ? 'Post anticipated' : null,
                        c.perm_approve_payments ? 'Approve payments' : null,
                        c.perm_approve_invoices ? 'Approve invoices' : null,
                        c.perm_admin ? 'Admin' : null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || 'No permissions'}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => {
                        setEditCatId(c.id)
                        setEditCatName(c.name)
                        setEditCat({
                          perm_fee_earner: c.perm_fee_earner,
                          perm_post_client: c.perm_post_client,
                          perm_post_office: c.perm_post_office,
                          perm_post_anticipated: c.perm_post_anticipated,
                          perm_approve_payments: c.perm_approve_payments,
                          perm_approve_invoices: c.perm_approve_invoices,
                          perm_admin: c.perm_admin ?? false,
                        })
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn danger"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await askConfirm({
                          title: 'Delete category',
                          message: `Delete category “${c.name}”?`,
                          danger: true,
                          confirmLabel: 'Delete',
                        })
                        if (!ok) return
                        setBusy(true)
                        setErr(null)
                        try {
                          await apiFetch(`/admin/permission-categories/${c.id}`, { token, method: 'DELETE' })
                          await load()
                        } catch (e: any) {
                          setErr(e?.message ?? 'Delete failed (is it still assigned to users?)')
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {categories.length === 0 ? <div className="muted">No categories yet.</div> : null}
        </div>
      </div>
      <div className="card">
        <h3>Security</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Organisation-wide sign-in policy. When enabled, users must enable an authenticator app (2FA) or
          register at least one passkey before using matters, tasks, and other areas of the app — including
          firm administrators.
        </p>
        <label className="row" style={{ gap: 10, alignItems: 'center', cursor: firmSettings ? 'pointer' : 'default' }}>
          <input
            type="checkbox"
            checked={Boolean(firmSettings?.mandate_two_factor)}
            disabled={busy || !firmSettings}
            onChange={async (e) => {
              if (!firmSettings) return
              const next = e.target.checked
              setBusy(true)
              setErr(null)
              try {
                const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                  token,
                  method: 'PATCH',
                  json: { mandate_two_factor: next },
                })
                setFirmSettings(updated)
              } catch (err: unknown) {
                setErr((err as ApiError).message ?? 'Could not update security settings')
              } finally {
                setBusy(false)
              }
            }}
          />
          <span>Mandate two-factor authentication</span>
        </label>
        <label className="row" style={{ gap: 10, alignItems: 'center', cursor: firmSettings ? 'pointer' : 'default', marginTop: 12 }}>
          <input
            type="checkbox"
            checked={Boolean(firmSettings?.mandate_password_rotation)}
            disabled={busy || !firmSettings}
            onChange={async (e) => {
              if (!firmSettings) return
              const next = e.target.checked
              setBusy(true)
              setErr(null)
              try {
                const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                  token,
                  method: 'PATCH',
                  json: next
                    ? {
                        mandate_password_rotation: true,
                        password_rotation_days: firmSettings.password_rotation_days ?? 90,
                      }
                    : { mandate_password_rotation: false, password_rotation_days: null },
                })
                setFirmSettings(updated)
              } catch (err: unknown) {
                setErr((err as ApiError).message ?? 'Could not update security settings')
              } finally {
                setBusy(false)
              }
            }}
          />
          <span>Require periodic password updates</span>
        </label>
        {firmSettings?.mandate_password_rotation ? (
          <div style={{ marginTop: 12, maxWidth: 280 }}>
            <SingleSelectDropdown
              label="Update every"
            options={passwordRotationOptions}
            value={String(firmSettings.password_rotation_days ?? 90)}
            disabled={busy}
            onChange={(v) => {
              void (async () => {
                const days = Number(v)
                setBusy(true)
                setErr(null)
                try {
                  const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                    token,
                    method: 'PATCH',
                    json: { mandate_password_rotation: true, password_rotation_days: days },
                  })
                  setFirmSettings(updated)
                } catch (err: unknown) {
                  setErr((err as ApiError).message ?? 'Could not update password rotation interval')
                } finally {
                  setBusy(false)
                }
              })()
            }}
            />
          </div>
        ) : null}
        <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>
          When enabled, all staff users must choose a new password after the interval since their last change. Password
          reset e-mails require alert notifications under Admin → E-mail.
        </p>
      </div>
      <div className="card">
        <h3>Create user</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Every new user must be assigned a permission category (create one above if needed).
        </p>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input placeholder="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <input
            placeholder="Initials (unique)"
            value={newInitials ?? ''}
            onChange={(e) => setNewInitials(e.target.value)}
            style={{ maxWidth: 120 }}
            title="Letters, digits, dot, underscore, hyphen; 1–12 characters"
          />
          <input
            placeholder="Job title (optional)"
            value={newJobTitle}
            onChange={(e) => setNewJobTitle(e.target.value)}
            style={{ minWidth: 160 }}
          />
          <input placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <SingleSelectDropdown
            label="Category"
            options={permissionCategoryOptions}
            value={newUserCategoryId}
            onChange={setNewUserCategoryId}
            disabled={busy}
            placeholder="— Select category —"
          />
          <button
            className="btn primary"
            style={creatingUser ? { cursor: 'wait' } : undefined}
            disabled={
              busy ||
              creatingUser ||
              !email ||
              !displayName ||
              !(newInitials ?? '').trim() ||
              password.length < 12 ||
              !newUserCategoryId
            }
            onClick={async () => {
              setCreatingUser(true)
              setBusy(true)
              setErr(null)
              const prevBodyCursor = document.body.style.cursor
              document.body.style.cursor = 'wait'
              try {
                await apiFetch('/admin/users', {
                  token,
                  json: {
                    email,
                    display_name: displayName,
                    initials: (newInitials ?? '').trim(),
                    job_title: newJobTitle.trim() || null,
                    password,
                    permission_category_id: newUserCategoryId,
                  },
                })
                setEmail('')
                setDisplayName('')
                setNewInitials('')
                setNewJobTitle('')
                setPassword('')
                setNewUserCategoryId('')
                await load()
              } catch (e: unknown) {
                const msg = ((e as ApiError).message ?? '').trim()
                setErr(msg || 'Create failed')
              } finally {
                document.body.style.cursor = prevBodyCursor
                setBusy(false)
                setCreatingUser(false)
              }
            }}
          >
            {creatingUser ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
      <div className="card">
        <h3>Users</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Edit a user to change e-mail, display name, job title, role, category, active state, or set a new password (optional).
        </p>
        <div className="list">
          {users.map((u) => (
            <div key={u.id} className="listCard row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ flex: '1 1 220px' }}>
                <div className="listTitle">
                  {u.email} <span className="muted">· {u.role}</span>
                </div>
                <div className="muted">
                  {u.display_name} ({u.initials ?? '—'}) · {u.is_active ? 'active' : 'disabled'} · 2FA{' '}
                  {u.is_2fa_enabled ? 'on' : 'off'}
                </div>
              </div>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <button type="button" className="btn" disabled={busy} onClick={() => openUserEditor(u)}>
                  Edit
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    setErr(null)
                    try {
                      await apiFetch(`/admin/users/${u.id}`, { token, method: 'PATCH', json: { is_active: !u.is_active } })
                      await load()
                    } catch (e: any) {
                      setErr(e?.message ?? 'Update failed')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {u.is_active ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {editingUser ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-edit-user-title"
          onClick={() => !busy && setEditingUser(null)}
        >
          <div
            className="modal card modal--scrollBody"
            style={{ maxWidth: 520, width: 'min(520px, 94vw)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="paneHead">
              <div>
                <h2 id="admin-edit-user-title">Edit user</h2>
                <div className="muted" style={{ fontSize: 13 }}>
                  Same fields as create user. Under Sign-in security you can reset authenticator 2FA or set a new password (min 12 characters). Setting a new password clears their authenticator enrolment.
                </div>
              </div>
              <button type="button" className="btn" disabled={busy} onClick={() => setEditingUser(null)}>
                Close
              </button>
            </div>
            <div className="stack modalBodyScroll" style={{ gap: 12, marginTop: 12 }}>
              {err ? (
                <div className="error" role="alert">
                  {err}
                </div>
              ) : null}
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Email</span>
                <input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} disabled={busy} autoComplete="off" />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Display name</span>
                <input value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} disabled={busy} />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Initials (unique)</span>
                <input
                  value={editInitials ?? ''}
                  onChange={(e) => setEditInitials(e.target.value)}
                  disabled={busy}
                  title="Letters, digits, dot, underscore, hyphen; 1–12 characters"
                />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Job title (optional)</span>
                <input value={editJobTitle} onChange={(e) => setEditJobTitle(e.target.value)} disabled={busy} placeholder="Optional" />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Charge rate (£/hour, optional — for time / WIP)</span>
                <input
                  className="input inputNoSpinner"
                  inputMode="decimal"
                  value={editChargeRateStr}
                  onChange={(e) => setEditChargeRateStr(e.target.value.replace(/[^\d.]/g, ''))}
                  disabled={busy}
                  placeholder="e.g. 250.00"
                />
              </label>
              <SingleSelectDropdown
                label="Role"
                options={[
                  { value: 'user', label: 'User' },
                  { value: 'admin', label: 'Admin' },
                ]}
                value={editRole}
                onChange={(v) => setEditRole(v as 'admin' | 'user')}
                disabled={busy}
              />
              <SingleSelectDropdown
                label={`Permission category${editRole === 'user' ? '' : ' (optional for admins)'}`}
                options={editPermissionCategoryOptions}
                value={editCategoryId}
                onChange={setEditCategoryId}
                disabled={busy}
                placeholder={editRole === 'admin' ? '— None —' : '— Select category —'}
              />
              <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={editActive} onChange={(e) => setEditActive(e.target.checked)} disabled={busy} />
                <span>Account active</span>
              </label>

              <h4 style={{ margin: '16px 0 8px', fontSize: '1rem', fontWeight: 600 }}>Sign-in security</h4>
              <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                Authenticator status:{' '}
                <strong>{editingUser.is_2fa_enabled ? 'Enabled' : 'Not enabled'}</strong>. Reset removes their app enrolment so
                they must set up 2FA again in User settings (existing passkeys are unchanged).
              </p>
              <button
                type="button"
                className="btn danger"
                disabled={busy}
                onClick={() =>
                  void (async () => {
                    if (!editingUser) return
                    const ok = await askConfirm({
                      title: 'Reset authenticator (2FA)',
                      message:
                        `Clear authenticator enrolment for ${editingUser.email}? They will need to set up 2FA again under User settings before it applies at sign-in.`,
                      danger: true,
                      confirmLabel: 'Reset 2FA',
                    })
                    if (!ok) return
                    setBusy(true)
                    setErr(null)
                    try {
                      await apiFetch<null>(`/admin/users/${editingUser.id}/disable-2fa`, { method: 'POST', token })
                      const list = await load()
                      const nu = list?.find((x) => x.id === editingUser.id)
                      if (nu) setEditingUser(nu)
                    } catch (e: unknown) {
                      setErr((e as ApiError).message ?? 'Could not reset 2FA')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }
              >
                Reset authenticator (2FA)
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  void (async () => {
                    if (!editingUser) return
                    setBusy(true)
                    setErr(null)
                    try {
                      const res = await apiFetch<AdminSendPasswordResetResponse>(
                        `/admin/users/${editingUser.id}/send-password-reset-email`,
                        { method: 'POST', token },
                      )
                      await showAlert(res.message ?? 'Password reset e-mail sent.', 'E-mail sent')
                    } catch (e: unknown) {
                      setErr((e as ApiError).message ?? 'Could not send password reset e-mail')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }
              >
                Send password reset e-mail
              </button>

              <label className="field" style={{ marginBottom: 0, marginTop: 14 }}>
                <span>New password (optional, min 12 characters)</span>
                <input
                  type="password"
                  value={editPw}
                  onChange={(e) => setEditPw(e.target.value)}
                  disabled={busy}
                  autoComplete="new-password"
                  placeholder="Leave blank to keep current password"
                />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Confirm new password</span>
                <input
                  type="password"
                  value={editPw2}
                  onChange={(e) => setEditPw2(e.target.value)}
                  disabled={busy}
                  autoComplete="new-password"
                />
              </label>
              <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                When you set a new password here, this user’s authenticator 2FA and passkeys are cleared — they sign in with the
                new password until they enrol again.
              </p>
              <div className="row" style={{ gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                <button type="button" className="btn" disabled={busy} onClick={() => setEditingUser(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={
                    busy ||
                    !editEmail.trim() ||
                    !editDisplayName.trim() ||
                    !(editInitials ?? '').trim() ||
                    (editRole === 'user' && !editCategoryId) ||
                    (editPw.length > 0 && (editPw.length < 12 || editPw !== editPw2))
                  }
                  onClick={async () => {
                    if (!editingUser) return
                    if (editPw.length > 0 && editPw !== editPw2) {
                      setErr('Passwords do not match')
                      return
                    }
                    if (editPw.length > 0 && editPw.length < 12) {
                      setErr('Password must be at least 12 characters')
                      return
                    }
                    setBusy(true)
                    setErr(null)
                    try {
                      let chargeRatePence: number | null = null
                      const rateTrim = editChargeRateStr.trim()
                      if (rateTrim) {
                        const parsed = Math.round(parseFloat(rateTrim) * 100)
                        if (Number.isNaN(parsed) || parsed < 0) {
                          setErr('Charge rate must be a valid amount.')
                          setBusy(false)
                          return
                        }
                        chargeRatePence = parsed
                      }
                      const updatedUser = await apiFetch<AdminUserPublic>(`/admin/users/${editingUser.id}`, {
                        token,
                        method: 'PATCH',
                        json: {
                          email: editEmail.trim(),
                          display_name: editDisplayName.trim(),
                          initials: (editInitials ?? '').trim(),
                          job_title: (editJobTitle ?? '').trim() || null,
                          role: editRole,
                          is_active: editActive,
                          permission_category_id: editCategoryId || null,
                          charge_rate_pence_per_hour: chargeRatePence,
                        },
                      })
                      if (editPw.length >= 12) {
                        await apiFetch(`/admin/users/${editingUser.id}/set-password`, {
                          token,
                          method: 'POST',
                          json: { password: editPw },
                        })
                      }
                      setEditingUser(null)
                      setEditPw('')
                      setEditPw2('')
                      await load()
                      // Fill in fields from PATCH (not a full spread: set-password may run after PATCH
                      // and load() is the source of truth for 2FA state).
                      setUsers((prev) =>
                        prev.map((u) => {
                          if (u.id !== updatedUser.id) return u
                          return {
                            ...u,
                            email: updatedUser.email,
                            display_name: updatedUser.display_name,
                            initials: updatedUser.initials ?? u.initials,
                            job_title: updatedUser.job_title,
                            role: updatedUser.role,
                            is_active: updatedUser.is_active,
                            permission_category_id: updatedUser.permission_category_id,
                          }
                        }),
                      )
                    } catch (e: unknown) {
                      const msg = ((e as ApiError).message ?? '').trim()
                      setErr(msg || 'Update failed')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Save changes
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function RecoveryConsole({ token }: { token: string }) {
  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Recovery console</h2>
          <div className="muted" style={{ marginTop: 4 }}>
            User accounts, permission categories, and organisation security policy. No access to cases or firm data.
          </div>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        <AdminUsers token={token} embedded recoveryMode />
      </div>
    </div>
  )
}

