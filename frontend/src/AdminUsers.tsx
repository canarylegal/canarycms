import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  AdminSendPasswordResetResponse,
  AdminUserPublic,
  FirmSettingsOut,
  UserPermissionCategoryOut,
} from './types'

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
