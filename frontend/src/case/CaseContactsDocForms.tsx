import type { Dispatch, SetStateAction } from 'react'
import { useState } from 'react'
import {
  GlobalContactCreateForm,
  ContactPersonOrgAddressFields,
  emptyContactFormFields,
  contactOutToFormFields,
  contactFieldsModelToPayload,
  resolveContactNameWithFallback,
  type ContactFormFieldsModel,
} from '../GlobalContactCreateForm'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { useDialogs } from '../DialogProvider'
import { SearchInput } from '../SearchInput'
import type { CaseContactOut, ContactOut } from '../types'
import { applyCaseContactFieldPatch } from './caseContactPatch'

const CONTACT_TYPE_REQUIRED_MSG = 'Please select a contact type for this matter.'
const LAWYERS_TYPE_SLUG = 'lawyers'

type MatterOpt = { value: string; label: string }

export function CaseContactsAddDocForm({
  token,
  caseId,
  busy,
  setBusy,
  onDone,
  matterContactType,
  setMatterContactType,
  matterContactReference,
  setMatterContactReference,
  lawyerLinkClientIds,
  setLawyerLinkClientIds,
  contacts,
  contactAddSearch,
  setContactAddSearch,
  selectedGlobalContactId,
  setSelectedGlobalContactId,
  matterTypeOptions,
  clientMatterContacts,
  contactAddErr,
  setContactAddErr,
  setActionErr,
  onGlobalContactsUpdated,
}: {
  token: string
  caseId: string
  busy: boolean
  setBusy: (v: boolean) => void
  onDone: () => void
  /** After PATCH /contacts/{id}, reload global contacts in the parent. */
  onGlobalContactsUpdated: () => Promise<void>
  matterContactType: string
  setMatterContactType: (v: string) => void
  matterContactReference: string
  setMatterContactReference: (v: string) => void
  lawyerLinkClientIds: string[]
  setLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  contacts: ContactOut[]
  contactAddSearch: string
  setContactAddSearch: (v: string) => void
  selectedGlobalContactId: string | null
  setSelectedGlobalContactId: (v: string | null) => void
  matterTypeOptions: MatterOpt[]
  clientMatterContacts: CaseContactOut[]
  contactAddErr: string | null
  setContactAddErr: (v: string | null) => void
  setActionErr: (v: string | null) => void
}) {
  const [globalEditContact, setGlobalEditContact] = useState<ContactOut | null>(null)
  const [globalEditFields, setGlobalEditFields] = useState<ContactFormFieldsModel>(() => emptyContactFormFields())
  const [globalEditErr, setGlobalEditErr] = useState<string | null>(null)

  function openGlobalEdit(c: ContactOut) {
    setGlobalEditContact(c)
    setGlobalEditFields(contactOutToFormFields(c))
    setGlobalEditErr(null)
    setContactAddErr(null)
  }

  return (
    <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Matter-specific
        </div>
        <label className="field">
          <span>Contact type (required)</span>
          <select
            required
            value={matterContactType}
            onChange={(e) => {
              const v = e.target.value
              setMatterContactType(v)
              setContactAddErr(null)
              if (v.trim().toLowerCase() !== LAWYERS_TYPE_SLUG) {
                setLawyerLinkClientIds([])
              } else if (selectedGlobalContactId) {
                const sel = contacts.find((x) => x.id === selectedGlobalContactId)
                if (sel && sel.type === 'person') setSelectedGlobalContactId(null)
              }
            }}
            disabled={busy}
          >
            <option value="" disabled>
              Select contact type
            </option>
            {matterTypeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Contact reference</span>
          <input
            value={matterContactReference}
            onChange={(e) => setMatterContactReference(e.target.value)}
            placeholder="Reference for this matter only"
            disabled={busy}
          />
        </label>
        {matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? (
          <div className="field">
            <span>Linked clients (required)</span>
            <div className="stack" style={{ gap: 6, maxHeight: 160, overflow: 'auto' }}>
              {clientMatterContacts.length === 0 ? (
                <div className="muted">Add at least one Client matter contact on this case first.</div>
              ) : (
                clientMatterContacts.map((c) => (
                  <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={lawyerLinkClientIds.includes(c.id)}
                      disabled={busy}
                      onChange={(e) => {
                        setLawyerLinkClientIds((prev) => {
                          if (e.target.checked) {
                            if (prev.includes(c.id) || prev.length >= 4) return prev
                            return [...prev, c.id]
                          }
                          return prev.filter((x) => x !== c.id)
                        })
                      }}
                    />
                    <span>{c.name}</span>
                  </label>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>
      {contactAddErr ? <div className="error">{contactAddErr}</div> : null}
      <div className="row">
        <SearchInput
          placeholder="Search global contacts…"
          value={contactAddSearch}
          onChange={(e) => setContactAddSearch(e.target.value)}
          onClear={() => setContactAddSearch('')}
          style={{ flex: 1 }}
          aria-label="Search global contacts to add"
        />
      </div>

      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Existing contacts
        </div>
        <div className="list" style={{ maxHeight: 140, overflow: 'auto' }}>
          {contacts
            .filter((c) => {
              if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG && c.type !== 'organisation') {
                return false
              }
              const s = contactAddSearch.trim().toLowerCase()
              if (!s) return true
              return (
                c.name.toLowerCase().includes(s) ||
                (c.email ?? '').toLowerCase().includes(s) ||
                (c.phone ?? '').toLowerCase().includes(s)
              )
            })
            .slice(0, 25)
            .map((c) => (
              <div key={c.id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <div className="listTitle">
                    {c.name} <span className="muted">· {c.type}</span>
                  </div>
                  <div className="muted">{c.email ?? c.phone ?? '—'}</div>
                </div>
                <div className="row" style={{ gap: 6, alignItems: 'center', flexShrink: 0 }}>
                  <button type="button" className="btn" disabled={busy} onClick={() => openGlobalEdit(c)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className={`btn ${selectedGlobalContactId === c.id ? 'primary' : ''}`}
                    disabled={busy}
                    onClick={() => setSelectedGlobalContactId(c.id)}
                  >
                    {selectedGlobalContactId === c.id ? 'Selected' : 'Select'}
                  </button>
                </div>
              </div>
            ))}
          {contacts.length === 0 ? <div className="muted">No contacts yet.</div> : null}
        </div>
      </div>

      {globalEditContact ? (
        <div className="card" style={{ padding: 12, marginTop: 12 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div className="muted" style={{ marginBottom: 0 }}>
              Edit global contact <strong>{globalEditContact.name}</strong>
            </div>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setGlobalEditContact(null)
                setGlobalEditErr(null)
              }}
            >
              Close editor
            </button>
          </div>
          <ContactPersonOrgAddressFields
            value={globalEditFields}
            onChange={(patch) => setGlobalEditFields((prev) => ({ ...prev, ...patch }))}
            busy={busy}
            organisationOnly={matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG}
          />
          {globalEditErr ? <div className="error">{globalEditErr}</div> : null}
          <div className="row" style={{ gap: 8, justifyContent: 'flex-end', marginTop: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setGlobalEditContact(null)
                setGlobalEditErr(null)
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={async () => {
                if (!globalEditContact) return
                const resolvedName = resolveContactNameWithFallback(
                  globalEditFields.type,
                  {
                    title: globalEditFields.title,
                    first_name: globalEditFields.firstName,
                    middle_name: globalEditFields.middleName,
                    last_name: globalEditFields.lastName,
                  },
                  { company_name: globalEditFields.companyName, trading_name: globalEditFields.tradingName },
                  globalEditContact.name,
                )
                if (!resolvedName.trim()) {
                  setGlobalEditErr('Name is required.')
                  return
                }
                const payload = contactFieldsModelToPayload(globalEditFields)
                if (!payload) {
                  setGlobalEditErr('Name is required.')
                  return
                }
                setBusy(true)
                setGlobalEditErr(null)
                try {
                  await apiFetch(`/contacts/${globalEditContact.id}`, {
                    token,
                    method: 'PATCH',
                    json: payload,
                  })
                  await onGlobalContactsUpdated()
                  setGlobalEditContact(null)
                } catch (e: unknown) {
                  setGlobalEditErr((e as ApiError).message?.trim() || 'Save failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Save to directory
            </button>
          </div>
        </div>
      ) : null}

      <button
        type="button"
        className="btn primary"
        disabled={busy || !selectedGlobalContactId}
        onClick={async () => {
          setContactAddErr(null)
          setActionErr(null)
          if (!matterContactType.trim()) {
            setContactAddErr(CONTACT_TYPE_REQUIRED_MSG)
            return
          }
          if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG && lawyerLinkClientIds.length < 1) {
            setContactAddErr('Select one or more clients that this lawyer represents on this matter.')
            return
          }
          if (!selectedGlobalContactId) return
          setBusy(true)
          try {
            const linkBody: Record<string, unknown> = {
              contact_id: selectedGlobalContactId,
              matter_contact_type: matterContactType.trim(),
              matter_contact_reference: matterContactReference.trim() || null,
            }
            if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG) {
              linkBody.lawyer_client_ids = lawyerLinkClientIds
            }
            await apiFetch(`/cases/${caseId}/contacts`, {
              token,
              json: linkBody,
            })
            onDone()
          } catch (e: unknown) {
            setContactAddErr((e as { message?: string })?.message ?? 'Failed to link contact')
          } finally {
            setBusy(false)
          }
        }}
      >
        Link selected
      </button>

      <div className="card" style={{ padding: 12, marginTop: 12 }}>
        <GlobalContactCreateForm
          key={matterContactType || 'mc'}
          organisationOnly={matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG}
          busy={busy}
          formError={contactAddErr}
          submitLabel="Create & link"
          intro={<div className="muted" style={{ marginBottom: 8 }}>Create new contact</div>}
          onSubmit={async (payload) => {
            setContactAddErr(null)
            setActionErr(null)
            if (!matterContactType.trim()) {
              setContactAddErr(CONTACT_TYPE_REQUIRED_MSG)
              throw new Error(CONTACT_TYPE_REQUIRED_MSG)
            }
            if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG && lawyerLinkClientIds.length < 1) {
              const msg = 'Select one or more clients that this lawyer represents on this matter.'
              setContactAddErr(msg)
              throw new Error(msg)
            }
            setBusy(true)
            try {
              const created = await apiFetch<ContactOut>('/contacts', {
                token,
                method: 'POST',
                json: payload,
              })
              const createLinkBody: Record<string, unknown> = {
                contact_id: created.id,
                matter_contact_type: matterContactType.trim(),
                matter_contact_reference: matterContactReference.trim() || null,
              }
              if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG) {
                createLinkBody.lawyer_client_ids = lawyerLinkClientIds
              }
              await apiFetch(`/cases/${caseId}/contacts`, {
                token,
                json: createLinkBody,
              })
              onDone()
            } catch (e: unknown) {
              if ((e as Error)?.message !== CONTACT_TYPE_REQUIRED_MSG) {
                setContactAddErr((e as { message?: string })?.message ?? 'Failed to create/link contact')
              }
              throw e
            } finally {
              setBusy(false)
            }
          }}
        />
      </div>
    </div>
  )
}

export function CaseContactsEditDocForm({
  token,
  caseId,
  busy,
  setBusy,
  editSnapshot,
  setEditSnapshot,
  editLawyerLinkClientIds,
  setEditLawyerLinkClientIds,
  pushToGlobal,
  setPushToGlobal,
  resolvedEditSnapshotName,
  matterTypeOptions,
  clientMatterContacts,
  onDone,
  setActionErr,
}: {
  token: string
  caseId: string
  busy: boolean
  setBusy: (v: boolean) => void
  editSnapshot: CaseContactOut
  setEditSnapshot: Dispatch<SetStateAction<CaseContactOut | null>>
  editLawyerLinkClientIds: string[]
  setEditLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  pushToGlobal: boolean
  setPushToGlobal: (v: boolean) => void
  resolvedEditSnapshotName: string
  matterTypeOptions: MatterOpt[]
  clientMatterContacts: CaseContactOut[]
  onDone: () => void
  setActionErr: (v: string | null) => void
}) {
  const { askConfirm } = useDialogs()

  return (
    <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
      <label className="field">
        <span>Contact type (required)</span>
        <select
          required
          value={editSnapshot.matter_contact_type ?? ''}
          onChange={(e) => {
            const v = e.target.value ? e.target.value : null
            const isLawyers = (v || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG
            setEditSnapshot({
              ...editSnapshot,
              matter_contact_type: v,
              ...(isLawyers ? { type: 'organisation' as const } : {}),
            })
            if (!isLawyers) {
              setEditLawyerLinkClientIds([])
            }
          }}
          disabled={busy}
        >
          <option value="" disabled>
            Select contact type
          </option>
          {matterTypeOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
          {editSnapshot.matter_contact_type &&
          !matterTypeOptions.some((o) => o.value === editSnapshot.matter_contact_type) ? (
            <option value={editSnapshot.matter_contact_type}>{editSnapshot.matter_contact_type}</option>
          ) : null}
        </select>
      </label>
      <label className="field">
        <span>Contact reference</span>
        <input
          placeholder="Matter-specific reference"
          value={editSnapshot.matter_contact_reference ?? ''}
          onChange={(e) => setEditSnapshot({ ...editSnapshot, matter_contact_reference: e.target.value || null })}
          disabled={busy}
        />
      </label>
      {(editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG ? (
        <div className="field">
          <span>Linked clients (required)</span>
          <div className="stack" style={{ gap: 6, maxHeight: 160, overflow: 'auto' }}>
            {clientMatterContacts.length === 0 ? (
              <div className="muted">Add at least one Client matter contact on this case first.</div>
            ) : (
              clientMatterContacts.map((c) => (
                <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={editLawyerLinkClientIds.includes(c.id)}
                    disabled={busy}
                    onChange={(e) => {
                      setEditLawyerLinkClientIds((prev) => {
                        if (e.target.checked) {
                          if (prev.includes(c.id) || prev.length >= 4) return prev
                          return [...prev, c.id]
                        }
                        return prev.filter((x) => x !== c.id)
                      })
                    }}
                  />
                  <span>{c.name}</span>
                </label>
              ))
            )}
          </div>
        </div>
      ) : null}
      <div className="muted" style={{ fontSize: 12 }}>
        Name and email below are the case snapshot; they can be pushed to the global card only when linked.
      </div>
      <ContactPersonOrgAddressFields
        busy={busy}
        organisationOnly={(editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG}
        value={contactOutToFormFields(editSnapshot as unknown as ContactOut)}
        onChange={(patch) => setEditSnapshot((prev) => (prev ? applyCaseContactFieldPatch(prev, patch) : prev))}
      />
      {editSnapshot.contact_id ? (
        <label className="row" style={{ alignItems: 'center' }}>
          <input type="checkbox" checked={pushToGlobal} onChange={(e) => setPushToGlobal(e.target.checked)} disabled={busy} />
          <span className="muted">Also update global contact</span>
        </label>
      ) : null}
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 8 }}>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={async () => {
            if (!caseId) return
            const ok = await askConfirm({
              title: 'Remove contact',
              message: 'Remove this contact from the matter only? The global contact will not be deleted.',
              danger: true,
              confirmLabel: 'Remove',
            })
            if (!ok) return
            setBusy(true)
            setActionErr(null)
            try {
              await apiFetch(`/cases/${caseId}/contacts/${editSnapshot.id}`, {
                token,
                method: 'DELETE',
              })
              onDone()
            } catch (e: unknown) {
              setActionErr((e as { message?: string })?.message ?? 'Failed to remove contact')
            } finally {
              setBusy(false)
            }
          }}
        >
          Remove from matter
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={
            busy ||
            !resolvedEditSnapshotName.trim() ||
            !(editSnapshot.matter_contact_type && editSnapshot.matter_contact_type.trim()) ||
            ((editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG &&
              editLawyerLinkClientIds.length < 1)
          }
          onClick={async () => {
            setBusy(true)
            setActionErr(null)
            try {
              const payload = contactFieldsModelToPayload(contactOutToFormFields(editSnapshot as unknown as ContactOut))
              if (!payload) {
                setActionErr('Enter a name (person or organisation fields).')
                return
              }
              const patchBody: Record<string, unknown> = {
                type: payload.type,
                name: payload.name,
                email: payload.email,
                phone: payload.phone,
                title: payload.title,
                first_name: payload.first_name,
                middle_name: payload.middle_name,
                last_name: payload.last_name,
                company_name: payload.company_name,
                trading_name: payload.trading_name,
                address_line1: payload.address_line1,
                address_line2: payload.address_line2,
                city: payload.city,
                county: payload.county,
                postcode: payload.postcode,
                country: payload.country,
                matter_contact_type: editSnapshot.matter_contact_type!.trim(),
                matter_contact_reference: (editSnapshot.matter_contact_reference ?? '').trim() || null,
                push_to_global: pushToGlobal,
              }
              if ((editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG) {
                patchBody.lawyer_client_ids = editLawyerLinkClientIds
              }
              await apiFetch(`/cases/${caseId}/contacts/${editSnapshot.id}`, {
                token,
                method: 'PATCH',
                json: patchBody,
              })
              onDone()
            } catch (e: unknown) {
              setActionErr((e as { message?: string })?.message ?? 'Failed to update snapshot')
            } finally {
              setBusy(false)
            }
          }}
        >
          Save
        </button>
      </div>
    </div>
  )
}
