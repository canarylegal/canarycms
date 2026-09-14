import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { fetchContactSearch } from './apiSearch'
import {
  GlobalContactCreateForm,
  ContactPersonOrgAddressFields,
  contactOutToFormFields,
  contactFieldsModelToPayload,
  resolveContactNameWithFallback,
} from './GlobalContactCreateForm'
import { ContactPortalPanel } from './ContactPortalPanel'
import { ContactMergePanel } from './ContactMergePanel'
import { SearchInput } from './SearchInput'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { useDialogs } from './DialogProvider'
import {
  choosePortalActionOnIdentityChange,
  contactHasActivePortalAccess,
  contactIdentityFieldsChanged,
  revokeContactPortalAccess,
} from './portalIdentityGuard'
import { useDebouncedValue } from './useDebouncedValue'
import { useColumnWidths } from './useColumnWidths'
import { useUserUiPreferences } from './useUserUiPreferences'
import {
  CONTACTS_COLUMN_COUNT,
  CONTACTS_COLUMN_WIDTHS_DEFAULT,
} from './userUiPreferences'
import { effectiveColumnWidths, LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS } from './columnGridDefaults'
import { createRequestSeq } from './requestSeq'
import type { ContactOut, UserPublic } from './types'

function contactTypeLabel(t: ContactOut['type']) {
  return t === 'person' ? 'Person' : 'Organisation'
}

export function Contacts({ token, me }: { token: string; me?: UserPublic | null }) {
  const { askConfirm } = useDialogs()
  const { prefs: uiPrefs, setPreference: setUiPreference, setPreferenceDebounced: setUiPreferenceDebounced } =
    useUserUiPreferences(me, token)
  const [contactsSearch, setContactsSearch] = useState('')
  const debouncedContactsSearch = useDebouncedValue(contactsSearch.trim(), 300)
  const [contactsFilterOpen, setContactsFilterOpen] = useState(false)
  const [contactsFilterType, setContactsFilterType] = useState<'' | ContactOut['type']>('')
  const [contactsFilterEmail, setContactsFilterEmail] = useState<'' | 'has' | 'missing'>('')
  const [contactsFilterPhone, setContactsFilterPhone] = useState<'' | 'has' | 'missing'>('')
  const { gridTemplateColumns: contactsGridColumns, startResize: contactsStartResize } = useColumnWidths(
    CONTACTS_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.contacts_column_widths,
        CONTACTS_COLUMN_COUNT,
        LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...CONTACTS_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('contacts_column_widths', widths, 300),
    },
  )
  const [contacts, setContacts] = useState<ContactOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [contactRowFocusId, setContactRowFocusId] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createErr, setCreateErr] = useState<string | null>(null)

  const [editing, setEditing] = useState<ContactOut | null>(null)
  const [contactCtx, setContactCtx] = useState<null | { x: number; y: number; c: ContactOut }>(null)
  const contactCtxRef = useRef<HTMLDivElement | null>(null)

  const contactsSearchSeqRef = useRef(createRequestSeq())

  async function load() {
    const seq = contactsSearchSeqRef.current
    const reqId = seq.next()
    setBusy(true)
    setErr(null)
    try {
      const data = await fetchContactSearch(token, {
        q: debouncedContactsSearch || undefined,
        type: contactsFilterType || undefined,
        hasEmail:
          contactsFilterEmail === 'has' ? true : contactsFilterEmail === 'missing' ? false : undefined,
        hasPhone:
          contactsFilterPhone === 'has' ? true : contactsFilterPhone === 'missing' ? false : undefined,
      })
      if (!seq.isCurrent(reqId)) return
      setContacts(data)
    } catch (e: unknown) {
      if (!seq.isCurrent(reqId)) return
      setErr((e as { message?: string })?.message ?? 'Failed to load contacts')
    } finally {
      if (seq.isCurrent(reqId)) setBusy(false)
    }
  }

  useEffect(() => {
    void load()
    return () => {
      contactsSearchSeqRef.current.invalidate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load closes over latest filter/search values
  }, [token, debouncedContactsSearch, contactsFilterType, contactsFilterEmail, contactsFilterPhone])

  useEffect(() => {
    if (!contactCtx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (contactCtxRef.current?.contains(t)) return
      setContactCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [contactCtx])

  const contactsActiveFilterCount = useMemo(
    () =>
      (contactsFilterType ? 1 : 0) +
      (contactsFilterEmail ? 1 : 0) +
      (contactsFilterPhone ? 1 : 0),
    [contactsFilterType, contactsFilterEmail, contactsFilterPhone],
  )

  const rows = useMemo(() => {
    const dir = uiPrefs.contacts_sort_dir === 'asc' ? 1 : -1
    const key = uiPrefs.contacts_sort_key
    return [...contacts].sort((a, b) => {
      const av =
        key === 'name'
          ? a.name
          : key === 'type'
            ? a.type
            : key === 'email'
              ? a.email ?? ''
              : a.phone ?? ''
      const bv =
        key === 'name'
          ? b.name
          : key === 'type'
            ? b.type
            : key === 'email'
              ? b.email ?? ''
              : b.phone ?? ''
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [contacts, uiPrefs.contacts_sort_key, uiPrefs.contacts_sort_dir])

  function toggleContactsSort(key: 'name' | 'type' | 'email' | 'phone') {
    if (uiPrefs.contacts_sort_key === key) {
      setUiPreference('contacts_sort_dir', uiPrefs.contacts_sort_dir === 'asc' ? 'desc' : 'asc')
    } else {
      setUiPreference('contacts_sort_key', key)
      setUiPreference('contacts_sort_dir', 'asc')
    }
  }

  function closeCreateModal() {
    if (busy) return
    setCreateOpen(false)
    setCreateErr(null)
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {err ? <div className="error">{err}</div> : null}
      <div className={`mainMenuFilterBar${contactsFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button
              type="button"
              className="btn primary toolbarLeadBtn"
              onClick={() => {
                setCreateErr(null)
                setCreateOpen(true)
              }}
            >
              New contact
            </button>
            <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
            <div className="caseToolbarDropdownWrap">
              <button
                type="button"
                className="btn mainMenuFilterBtn"
                aria-expanded={contactsFilterOpen}
                aria-haspopup="true"
                aria-controls="contacts-menu-filter-menu"
                id="contacts-menu-filter-button"
                onClick={(e) => {
                  e.stopPropagation()
                  setContactsFilterOpen((o) => !o)
                }}
              >
                <span className="mainMenuFilterBtnInner">
                  <svg
                    className="mainMenuFilterBtnIcon"
                    width={16}
                    height={16}
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden
                  >
                    <polygon
                      points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                  <span>Filter</span>
                  <span className="mainMenuFilterBtnCount">({contactsActiveFilterCount})</span>
                </span>
              </button>
              {contactsFilterOpen ? (
                <div
                  id="contacts-menu-filter-menu"
                  className="caseToolbarDropdown mainMenuFilterDropdown"
                  role="group"
                  aria-labelledby="contacts-menu-filter-button"
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  <div className="stack mainMenuFilterDropdownBody">
                    <SingleSelectDropdown
                      label="Type"
                      options={[
                        { value: '', label: 'All' },
                        { value: 'person', label: 'Person' },
                        { value: 'organisation', label: 'Organisation' },
                      ]}
                      value={contactsFilterType}
                      onChange={(v) => setContactsFilterType(v as '' | ContactOut['type'])}
                      placeholder="All"
                    />
                    <SingleSelectDropdown
                      label="Email"
                      options={[
                        { value: '', label: 'Any' },
                        { value: 'has', label: 'Has email' },
                        { value: 'missing', label: 'Missing email' },
                      ]}
                      value={contactsFilterEmail}
                      onChange={(v) => setContactsFilterEmail(v as '' | 'has' | 'missing')}
                      placeholder="Any"
                    />
                    <SingleSelectDropdown
                      label="Phone"
                      options={[
                        { value: '', label: 'Any' },
                        { value: 'has', label: 'Has phone' },
                        { value: 'missing', label: 'Missing phone' },
                      ]}
                      value={contactsFilterPhone}
                      onChange={(v) => setContactsFilterPhone(v as '' | 'has' | 'missing')}
                      placeholder="Any"
                    />
                  </div>
                </div>
              ) : null}
            </div>
            <SearchInput
              placeholder="Search"
              value={contactsSearch}
              onChange={(e) => setContactsSearch(e.target.value)}
              onClear={() => setContactsSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search contacts"
            />
          </div>
        </div>
      </div>

      <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="casesTableScroll contactsTableScroll">
          <div className="table">
            <div className="tr th" style={contactsGridColumns ? { gridTemplateColumns: contactsGridColumns } : undefined}>
              {(
                [
                  ['name', 'Name'],
                  ['type', 'Type'],
                  ['email', 'Email'],
                  ['phone', 'Phone'],
                ] as const
              ).map(([k, label], colIndex) => (
                <div key={k} className="thCell">
                  <button type="button" className="thbtn" onClick={() => toggleContactsSort(k)}>
                    {label}
                  </button>
                  {colIndex < 3 ? (
                    <div
                      className="colResizeHandle"
                      role="separator"
                      aria-orientation="vertical"
                      aria-label={`Resize ${label} column`}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        contactsStartResize(colIndex, e.clientX, e.currentTarget.closest('.tr.th') as HTMLElement | null)
                      }}
                    />
                  ) : null}
                </div>
              ))}
            </div>
            {rows.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`tr rowbtn${contactRowFocusId === c.id ? ' active' : ''}`}
                style={contactsGridColumns ? { gridTemplateColumns: contactsGridColumns } : undefined}
                onClick={() => setContactRowFocusId(c.id)}
                onDoubleClick={() => setEditing(c)}
                onContextMenu={(e) => {
                  e.preventDefault()
                  setContactCtx({ x: e.clientX, y: e.clientY, c })
                }}
              >
                <div className="td">{c.name}</div>
                <div className="td">{contactTypeLabel(c.type)}</div>
                <div className="td">{c.email ?? '—'}</div>
                <div className="td">{c.phone ?? '—'}</div>
              </button>
            ))}
            {rows.length === 0 ? (
              <div className="muted" style={{ padding: 12 }}>
                {contacts.length === 0 ? 'No contacts yet.' : 'No contacts match your search.'}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {contactCtx ? (
        <div
          ref={contactCtxRef}
          className="docContextMenu"
          style={{ left: contactCtx.x, top: contactCtx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              const c = contactCtx.c
              setContactCtx(null)
              setEditing(c)
            }}
          >
            Open
          </div>
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              void (async () => {
                const c = contactCtx.c
                setContactCtx(null)
                const ok = await askConfirm({
                  title: 'Delete contact',
                  message: `Delete “${c.name}” from the global directory?`,
                  danger: true,
                  confirmLabel: 'Delete',
                })
                if (!ok) return
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch(`/contacts/${c.id}`, { token, method: 'DELETE' })
                  if (editing?.id === c.id) setEditing(null)
                  await load()
                } catch (e: any) {
                  setErr(e?.message ?? 'Delete failed')
                } finally {
                  setBusy(false)
                }
              })()
            }}
          >
            Delete
          </div>
        </div>
      ) : null}

      {createOpen ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="new-contact-title"
          onClick={() => closeCreateModal()}
        >
          <div
            className="modal modal--scrollBody card"
            style={{ maxWidth: 720, width: 'min(720px, 100%)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="paneHead">
              <div>
                <h2 id="new-contact-title">New contact</h2>
                <div className="muted">Add a person or organisation to the global directory (same details as when creating from a matter).</div>
              </div>
              <button type="button" className="btn" onClick={() => closeCreateModal()} disabled={busy}>
                Close
              </button>
            </div>
            <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
              <GlobalContactCreateForm
                busy={busy}
                formError={createErr}
                submitLabel="Create"
                showCancelButton
                cancelLabel="Cancel"
                onCancel={() => closeCreateModal()}
                onSubmit={async (payload) => {
                  setBusy(true)
                  setCreateErr(null)
                  try {
                    await apiFetch('/contacts', { token, json: payload })
                    setCreateOpen(false)
                    setCreateErr(null)
                    await load()
                  } catch (e: any) {
                    setCreateErr(e?.message ?? 'Create failed')
                    throw e
                  } finally {
                    setBusy(false)
                  }
                }}
              />
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-contact-title"
          onClick={() => {
            setEditing(null)
          }}
        >
          <div
            className="modal modal--scrollBody card"
            style={{ maxWidth: 640, width: 'min(640px, 100%)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <ContactEditor
              token={token}
              contact={editing}
              onSaved={async () => {
                setEditing(null)
                await load()
              }}
              onMerged={async (survivorId) => {
                await load()
                try {
                  const refreshed = await apiFetch<ContactOut>(`/contacts/${survivorId}`, { token })
                  setEditing(refreshed)
                } catch {
                  setEditing(null)
                }
              }}
              onDeleted={async () => {
                setEditing(null)
                await load()
              }}
              onCancel={() => setEditing(null)}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ContactEditor({
  token,
  contact,
  onSaved,
  onMerged,
  onDeleted,
  onCancel,
}: {
  token: string
  contact: ContactOut
  onSaved: () => void
  onMerged?: (survivorId: string) => void
  onDeleted?: () => void
  onCancel: () => void
}) {
  const { askConfirm, askConfirmChoice } = useDialogs()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [fields, setFields] = useState(() => contactOutToFormFields(contact))

  useEffect(() => {
    setFields(contactOutToFormFields(contact))
  }, [contact.id])

  const resolvedName = useMemo(
    () =>
      resolveContactNameWithFallback(
        fields.type,
        {
          title: fields.title,
          first_name: fields.firstName,
          middle_name: fields.middleName,
          last_name: fields.lastName,
        },
        { company_name: fields.companyName, trading_name: fields.tradingName },
        contact.name,
      ),
    [fields, contact.name],
  )

  return (
    <>
      <div className="paneHead">
        <div>
          <h2 id="edit-contact-title">Edit contact</h2>
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          <button className="btn" onClick={onCancel} disabled={busy}>
            Close
          </button>
          {onDeleted ? (
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                const ok = await askConfirm({
                  title: 'Delete contact',
                  message: 'Permanently delete this contact from the global directory?',
                  danger: true,
                  confirmLabel: 'Delete',
                })
                if (!ok) return
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch<unknown>(`/contacts/${contact.id}`, { token, method: 'DELETE' })
                  onDeleted()
                } catch (e: any) {
                  setErr(e?.message ?? 'Delete failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Delete globally
            </button>
          ) : null}
          <button
            className="btn primary"
            disabled={busy || !resolvedName.trim()}
            onClick={async () => {
              if (fields.type === 'organisation' && !fields.tradingName.trim()) {
                setErr('Trading name is required for organisations.')
                return
              }
              const payload = contactFieldsModelToPayload(fields, { fallbackName: contact.name })
              if (!payload) {
                setErr('Name is required.')
                return
              }
              const identityChanged = contactIdentityFieldsChanged(
                {
                  type: contact.type,
                  first_name: contact.first_name,
                  middle_name: contact.middle_name,
                  last_name: contact.last_name,
                },
                {
                  type: payload.type,
                  first_name: payload.first_name,
                  middle_name: payload.middle_name,
                  last_name: payload.last_name,
                },
              )
              let revokePortal = false
              if (identityChanged) {
                const portalActive = await contactHasActivePortalAccess(token, contact.id)
                const choice = await choosePortalActionOnIdentityChange(askConfirmChoice, {
                  identityChanged: true,
                  portalAccessActive: portalActive,
                })
                if (choice === 'cancel') return
                revokePortal = choice === 'save_revoke'
              }
              setBusy(true)
              setErr(null)
              try {
                await apiFetch(`/contacts/${contact.id}`, {
                  token,
                  method: 'PATCH',
                  json: payload,
                })
                if (revokePortal) {
                  await revokeContactPortalAccess(token, contact.id)
                }
                onSaved()
              } catch (e: any) {
                setErr(e?.message ?? 'Save failed')
              } finally {
                setBusy(false)
              }
            }}
          >
            Save
          </button>
        </div>
      </div>
      {err ? <div className="error">{err}</div> : null}
      <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
        <ContactPersonOrgAddressFields
          value={fields}
          onChange={(patch) => setFields((prev) => ({ ...prev, ...patch }))}
          busy={busy}
        />
        <ContactPortalPanel token={token} contactId={contact.id} contactName={contact.name} contactEmail={contact.email} />
        <ContactMergePanel
          token={token}
          survivor={contact}
          onMerged={(survivorId) => {
            onMerged?.(survivorId)
          }}
        />
      </div>
    </>
  )
}


