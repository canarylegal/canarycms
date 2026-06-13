import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseAccessRuleOut, UserSummary } from './types'

type CaseLockMode = 'none' | 'open_by_default' | 'allow_list'

type Props = {
  token: string
  caseId: string
  users: UserSummary[]
  feeEarnerUserId: string | null
  lockMode: CaseLockMode
  canSetLockMode: boolean
  onClose: () => void
  onSaved: () => void
}

function isRoleAdmin(u: UserSummary) {
  return u.role === 'admin'
}

export function ManageCaseAccessModal({
  token,
  caseId,
  users,
  feeEarnerUserId,
  lockMode,
  canSetLockMode,
  onClose,
  onSaved,
}: Props) {
  const listsActive = lockMode === 'allow_list' || lockMode === 'open_by_default'
  const openByDefault = lockMode === 'open_by_default'
  const selectValue: 'open_by_default' | 'allow_list' =
    lockMode === 'allow_list' ? 'allow_list' : 'open_by_default'

  const [rules, setRules] = useState<CaseAccessRuleOut[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [leftSel, setLeftSel] = useState<Set<string>>(new Set())
  const [rightSel, setRightSel] = useState<Set<string>>(new Set())
  const [anchorLeft, setAnchorLeft] = useState<string | null>(null)
  const [anchorRight, setAnchorRight] = useState<string | null>(null)
  const [accessModeOpen, setAccessModeOpen] = useState(false)

  const accessModeOptions = useMemo(
    () => [
      { value: 'open_by_default', label: 'Blacklist' },
      { value: 'allow_list', label: 'Whitelist' },
    ],
    [],
  )

  const allUsersSorted = useMemo(
    () => [...users].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [users],
  )

  const denyUserIds = useMemo(() => {
    const s = new Set<string>()
    for (const r of rules) {
      if (r.mode === 'deny') s.add(r.user_id)
    }
    return s
  }, [rules])

  const allowUserIds = useMemo(() => {
    const s = new Set<string>()
    for (const r of rules) {
      if (r.mode === 'allow') s.add(r.user_id)
    }
    return s
  }, [rules])

  const { granted, revoked } = useMemo(() => {
    if (openByDefault) {
      const g: UserSummary[] = []
      const r: UserSummary[] = []
      for (const u of allUsersSorted) {
        if (isRoleAdmin(u)) {
          g.push(u)
          continue
        }
        if (feeEarnerUserId && u.id === feeEarnerUserId) {
          g.push(u)
          continue
        }
        if (denyUserIds.has(u.id)) r.push(u)
        else g.push(u)
      }
      return { granted: g, revoked: r }
    }
    const g: UserSummary[] = []
    const r: UserSummary[] = []
    for (const u of allUsersSorted) {
      if (isRoleAdmin(u) || (feeEarnerUserId && u.id === feeEarnerUserId) || allowUserIds.has(u.id)) {
        g.push(u)
      } else {
        r.push(u)
      }
    }
    return { granted: g, revoked: r }
  }, [allUsersSorted, denyUserIds, allowUserIds, feeEarnerUserId, openByDefault])

  const canRevokeSelected = useMemo(() => {
    return [...leftSel].some((id) => {
      const u = allUsersSorted.find((x) => x.id === id)
      if (!u || isRoleAdmin(u)) return false
      if (feeEarnerUserId && u.id === feeEarnerUserId) return false
      return true
    })
  }, [leftSel, allUsersSorted, feeEarnerUserId])

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const list = await apiFetch<CaseAccessRuleOut[]>(`/cases/${caseId}/access`, { token })
      setRules(list)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load access rules'
      setErr(msg)
    } finally {
      setLoading(false)
    }
  }, [caseId, token])

  useEffect(() => {
    void load()
  }, [load])

  async function patchLockMode(next: 'allow_list' | 'open_by_default') {
    if (next === lockMode) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/cases/${caseId}`, {
        token,
        method: 'PATCH',
        json: { lock_mode: next },
      })
      await load()
      onSaved()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed to update access mode')
    } finally {
      setBusy(false)
    }
  }

  function clickLeft(u: UserSummary, e: React.MouseEvent) {
    if (!listsActive) return
    if (isRoleAdmin(u)) return
    if (feeEarnerUserId && u.id === feeEarnerUserId) return
    const ordered = granted
    if (e.shiftKey && anchorLeft) {
      const ia = ordered.findIndex((x) => x.id === anchorLeft)
      const ib = ordered.findIndex((x) => x.id === u.id)
      if (ia < 0 || ib < 0) return
      const lo = Math.min(ia, ib)
      const hi = Math.max(ia, ib)
      setLeftSel((prev) => {
        const next = new Set(prev)
        for (let i = lo; i <= hi; i++) {
          const x = ordered[i]
          if (!isRoleAdmin(x) && !(feeEarnerUserId && x.id === feeEarnerUserId)) next.add(x.id)
        }
        return next
      })
      return
    }
    if (e.metaKey || e.ctrlKey) {
      setLeftSel((prev) => {
        const next = new Set(prev)
        if (next.has(u.id)) next.delete(u.id)
        else next.add(u.id)
        return next
      })
      setAnchorLeft(u.id)
      return
    }
    setLeftSel(new Set([u.id]))
    setAnchorLeft(u.id)
  }

  function clickRight(u: UserSummary, e: React.MouseEvent) {
    if (!listsActive) return
    const ordered = revoked
    if (e.shiftKey && anchorRight) {
      const ia = ordered.findIndex((x) => x.id === anchorRight)
      const ib = ordered.findIndex((x) => x.id === u.id)
      if (ia < 0 || ib < 0) return
      const lo = Math.min(ia, ib)
      const hi = Math.max(ia, ib)
      setRightSel((prev) => {
        const next = new Set(prev)
        for (let i = lo; i <= hi; i++) next.add(ordered[i].id)
        return next
      })
      return
    }
    if (e.metaKey || e.ctrlKey) {
      setRightSel((prev) => {
        const next = new Set(prev)
        if (next.has(u.id)) next.delete(u.id)
        else next.add(u.id)
        return next
      })
      setAnchorRight(u.id)
      return
    }
    setRightSel(new Set([u.id]))
    setAnchorRight(u.id)
  }

  async function moveRevoke() {
    if (!listsActive) return
    const ids = [...leftSel].filter((id) => {
      const u = allUsersSorted.find((x) => x.id === id)
      return u && !isRoleAdmin(u) && !(feeEarnerUserId && u.id === feeEarnerUserId)
    })
    if (ids.length === 0) return
    setBusy(true)
    setErr(null)
    try {
      if (openByDefault) {
        for (const userId of ids) {
          await apiFetch<CaseAccessRuleOut>(`/cases/${caseId}/access`, {
            token,
            method: 'PUT',
            json: { user_id: userId, mode: 'deny' },
          })
        }
      } else {
        await Promise.all(
          ids.map((userId) => apiFetch(`/cases/${caseId}/access/${userId}`, { token, method: 'DELETE' })),
        )
      }
      setLeftSel(new Set())
      await load()
      onSaved()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed to update access')
    } finally {
      setBusy(false)
    }
  }

  async function moveGrant() {
    if (!listsActive) return
    const ids = [...rightSel]
    if (ids.length === 0) return
    setBusy(true)
    setErr(null)
    try {
      if (openByDefault) {
        await Promise.all(
          ids.map((userId) => apiFetch(`/cases/${caseId}/access/${userId}`, { token, method: 'DELETE' })),
        )
      } else {
        for (const userId of ids) {
          await apiFetch<CaseAccessRuleOut>(`/cases/${caseId}/access`, {
            token,
            method: 'PUT',
            json: { user_id: userId, mode: 'allow' },
          })
        }
      }
      setRightSel(new Set())
      await load()
      onSaved()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed to update access')
    } finally {
      setBusy(false)
    }
  }

  const hint =
    lockMode === 'open_by_default'
      ? 'Blacklist: everyone can access unless moved to “No access”.'
      : lockMode === 'allow_list'
        ? 'Whitelist: only admins, the fee earner, and people under “Can access”; grant others with ← .'
        : 'Choose Blacklist or Whitelist above.'

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" aria-labelledby="manage-access-title">
      <div className="modal card modal--scrollBody" style={{ maxWidth: 720, width: 'min(720px, 94vw)' }}>
        <div className="paneHead">
          <div>
            <h2 id="manage-access-title">Manage access</h2>
            <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
              {hint}
            </div>
          </div>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <div className="modalBodyScroll">
          <div className="row" style={{ marginTop: 12, alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <SingleSelectDropdown
              label="Access mode"
              options={accessModeOptions}
              value={selectValue}
              onChange={(v) => void patchLockMode(v as 'allow_list' | 'open_by_default')}
              open={accessModeOpen}
              onOpenChange={setAccessModeOpen}
              disabled={busy || loading || !canSetLockMode}
              placeholder="— select —"
            />
            {!canSetLockMode ? (
              <span className="muted" style={{ fontSize: 13 }}>
                Only the fee earner or an administrator can change the mode.
              </span>
            ) : null}
          </div>
          {loading ? (
            <div className="muted" style={{ marginTop: 16 }}>
              Loading…
            </div>
          ) : (
            <div className="stack" style={{ marginTop: 12 }}>
              {!listsActive ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  Set access mode above to edit who can open this matter.
                </div>
              ) : null}
              <div className="row" style={{ alignItems: 'stretch', gap: 12, flexWrap: 'wrap' }}>
                <div className="card" style={{ flex: '1 1 220px', padding: 10, minHeight: 220 }}>
                  <div className="muted" style={{ marginBottom: 8, fontWeight: 600 }}>
                    Can access
                  </div>
                  <div
                    className="list"
                    style={{
                      maxHeight: 280,
                      overflow: 'auto',
                      border: '1px solid var(--border, #ddd)',
                      borderRadius: 6,
                    }}
                    role="listbox"
                    aria-multiselectable
                  >
                    {granted.map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        role="option"
                        aria-selected={leftSel.has(u.id)}
                        className="rowbtn"
                        style={{
                          display: 'block',
                          width: '100%',
                          textAlign: 'left',
                          padding: '8px 10px',
                          border: 'none',
                          borderBottom: '1px solid var(--border, #eee)',
                          background: leftSel.has(u.id) ? 'var(--accent-soft, rgba(100,149,237,0.2))' : undefined,
                          cursor: isRoleAdmin(u) || (feeEarnerUserId && u.id === feeEarnerUserId) ? 'default' : 'pointer',
                          opacity: isRoleAdmin(u) || (feeEarnerUserId && u.id === feeEarnerUserId) ? 0.65 : 1,
                        }}
                        disabled={
                          !listsActive || isRoleAdmin(u) || (feeEarnerUserId && u.id === feeEarnerUserId) || busy
                        }
                        onClick={(e) => clickLeft(u, e)}
                      >
                        <div className="listTitle">{u.display_name}</div>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {u.email}
                          {isRoleAdmin(u) ? ' · admin' : ''}
                          {feeEarnerUserId && u.id === feeEarnerUserId ? ' · fee earner' : ''}
                          {!u.is_active ? ' · inactive' : ''}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="row" style={{ flexDirection: 'column', justifyContent: 'center', gap: 8, minWidth: 44 }}>
                  <button
                    type="button"
                    className="btn"
                    title={openByDefault ? 'Remove access for selected users' : 'Remove from allowed list'}
                    disabled={busy || !listsActive || !canRevokeSelected}
                    onClick={() => void moveRevoke()}
                  >
                    →
                  </button>
                  <button
                    type="button"
                    className="btn"
                    title={openByDefault ? 'Restore access for selected users' : 'Grant access to selected users'}
                    disabled={busy || !listsActive || rightSel.size === 0}
                    onClick={() => void moveGrant()}
                  >
                    ←
                  </button>
                </div>
                <div className="card" style={{ flex: '1 1 220px', padding: 10, minHeight: 220 }}>
                  <div className="muted" style={{ marginBottom: 8, fontWeight: 600 }}>
                    No access
                  </div>
                  <div
                    className="list"
                    style={{
                      maxHeight: 280,
                      overflow: 'auto',
                      border: '1px solid var(--border, #ddd)',
                      borderRadius: 6,
                    }}
                    role="listbox"
                    aria-multiselectable
                  >
                    {revoked.length === 0 ? (
                      <div className="muted" style={{ padding: 12 }}>
                        None
                      </div>
                    ) : (
                      revoked.map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          role="option"
                          aria-selected={rightSel.has(u.id)}
                          className="rowbtn"
                          style={{
                            display: 'block',
                            width: '100%',
                            textAlign: 'left',
                            padding: '8px 10px',
                            border: 'none',
                            borderBottom: '1px solid var(--border, #eee)',
                            background: rightSel.has(u.id) ? 'var(--accent-soft, rgba(100,149,237,0.2))' : undefined,
                            cursor: 'pointer',
                          }}
                          disabled={busy || !listsActive}
                          onClick={(e) => clickRight(u, e)}
                        >
                          <div className="listTitle">{u.display_name}</div>
                          <div className="muted" style={{ fontSize: 12 }}>
                            {u.email}
                            {!u.is_active ? ' · inactive' : ''}
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                Tip: Ctrl or ⌘ click to toggle selection; Shift click extends the selection.
              </div>
              {err ? <div className="error">{err}</div> : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
