import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { CASE_MENU_OPTIONS } from './caseMenuOptions'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  MatterHeadTypeOut,
  MatterSubTypeOut,
  PrecedentCategoryOut,
} from './types'

export function AdminMatters({ token }: { token: string }) {
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
