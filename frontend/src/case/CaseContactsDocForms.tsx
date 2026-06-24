import type { Dispatch, SetStateAction } from 'react'
import { useMemo, useState } from 'react'
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
import { ContactSearchPicker } from '../ContactSearchPicker'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { defaultLetterSalutationForContact, LetterSalutationFields } from '../LetterSalutationFields'
import { coerceLetterSalutation, type LetterSalutation } from '../letterSalutation'
import type { CaseContactOut, ContactOut } from '../types'
import { applyCaseContactFieldPatch } from './caseContactPatch'
import { CaseContactPortalSection } from './CaseContactPortalSection'
import { matterContactTypeLabel } from './matterLabels'

const CONTACT_TYPE_REQUIRED_MSG = 'Please select a contact type for this matter.'
const LAWYERS_TYPE_SLUG = 'lawyers'

/** Shown when Lawyers contact type is chosen but no client matter contacts are linked. */
export const LAWYER_CLIENTS_REQUIRED_MSG =
  'Lawyer contacts must be linked to at least one other matter contact. Select one or more contacts below.'

function lawyerClientsValidationError(matterContactType: string, lawyerClientIds: string[]): string | null {
  if (matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG && lawyerClientIds.length < 1) {
    return LAWYER_CLIENTS_REQUIRED_MSG
  }
  return null
}

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
  selectedGlobalContactId,
  setSelectedGlobalContactId,
  matterTypeOptions,
  lawyerLinkableContacts,
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
  /** After PATCH /contacts/{id}, parent may refresh search results. */
  onGlobalContactsUpdated: () => void
  matterContactType: string
  setMatterContactType: (v: string) => void
  matterContactReference: string
  setMatterContactReference: (v: string) => void
  lawyerLinkClientIds: string[]
  setLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  selectedGlobalContactId: string | null
  setSelectedGlobalContactId: (v: string | null) => void
  matterTypeOptions: MatterOpt[]
  lawyerLinkableContacts: CaseContactOut[]
  contactAddErr: string | null
  setContactAddErr: (v: string | null) => void
  setActionErr: (v: string | null) => void
}) {
  const [globalEditContact, setGlobalEditContact] = useState<ContactOut | null>(null)
  const [globalEditFields, setGlobalEditFields] = useState<ContactFormFieldsModel>(() => emptyContactFormFields())
  const [globalEditErr, setGlobalEditErr] = useState<string | null>(null)
  const [lawyerClientsErr, setLawyerClientsErr] = useState<string | null>(null)
  const [matterTypeOpen, setMatterTypeOpen] = useState(false)
  const [addContactType, setAddContactType] = useState<'person' | 'organisation'>('person')
  const [letterSalutation, setLetterSalutation] = useState<LetterSalutation | null>(null)
  const [letterSalutationCustom, setLetterSalutationCustom] = useState<string | null>(null)

  const addSalutationContactType =
    matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? 'organisation' : addContactType

  function resetSalutationForAdd(matterType: string, contactType: 'person' | 'organisation') {
    const defaults = defaultLetterSalutationForContact(matterType, contactType)
    setLetterSalutation(defaults.letterSalutation)
    setLetterSalutationCustom(defaults.letterSalutationCustom)
  }

  const matterTypeDropdownOptions = useMemo(
    () => matterTypeOptions.map((o) => ({ value: o.value, label: o.label })),
    [matterTypeOptions],
  )

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
        <SingleSelectDropdown
          label="Contact type (required)"
          options={matterTypeDropdownOptions}
          value={matterContactType}
          onChange={(v) => {
            setMatterContactType(v)
            setContactAddErr(null)
            setLawyerClientsErr(null)
            const contactType = v.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? 'organisation' : addContactType
            resetSalutationForAdd(v, contactType)
            if (v.trim().toLowerCase() !== LAWYERS_TYPE_SLUG) {
              setLawyerLinkClientIds([])
            } else if (selectedGlobalContactId) {
              setSelectedGlobalContactId(null)
            }
          }}
          open={matterTypeOpen}
          onOpenChange={setMatterTypeOpen}
          disabled={busy}
          placeholder="Select contact type"
          emptyMessage={matterTypeDropdownOptions.length === 0 ? 'No contact types configured.' : undefined}
        />
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
            <span>Linked contacts (required)</span>
            <div className="stack" style={{ gap: 6, maxHeight: 160, overflow: 'auto' }}>
              {lawyerLinkableContacts.length === 0 ? (
                <div className="muted">Add at least one other matter contact on this case first.</div>
              ) : (
                lawyerLinkableContacts.map((c) => (
                  <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'flex-start' }}>
                    <input
                      type="checkbox"
                      checked={lawyerLinkClientIds.includes(c.id)}
                      disabled={busy}
                      style={{ marginTop: 3 }}
                      onChange={(e) => {
                        setLawyerLinkClientIds((prev) => {
                          let next: string[]
                          if (e.target.checked) {
                            if (prev.includes(c.id) || prev.length >= 4) return prev
                            next = [...prev, c.id]
                          } else {
                            next = prev.filter((x) => x !== c.id)
                          }
                          if (next.length > 0) setLawyerClientsErr(null)
                          return next
                        })
                      }}
                    />
                    <span>
                      {c.name}
                      <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                        {matterContactTypeLabel(c.matter_contact_type, matterTypeOptions)}
                      </span>
                    </span>
                  </label>
                ))
              )}
            </div>
            {lawyerClientsErr ? <div className="error" style={{ marginTop: 8 }}>{lawyerClientsErr}</div> : null}
          </div>
        ) : null}
        {matterContactType.trim() ? (
          <LetterSalutationFields
            matterContactType={matterContactType}
            contactType={addSalutationContactType}
            value={letterSalutation}
            customValue={letterSalutationCustom}
            busy={busy}
            onChange={({ letterSalutation: nextSalutation, letterSalutationCustom: nextCustom }) => {
              setLetterSalutation(nextSalutation)
              setLetterSalutationCustom(nextCustom)
            }}
          />
        ) : null}
      </div>
      {contactAddErr ? <div className="error">{contactAddErr}</div> : null}
      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Existing contacts
        </div>
        <ContactSearchPicker
          token={token}
          value={selectedGlobalContactId}
          onChange={(id, contact) => {
            setSelectedGlobalContactId(id)
            if (contact) {
              setAddContactType(contact.type)
              if (matterContactType.trim()) {
                resetSalutationForAdd(matterContactType, contact.type)
              }
            }
          }}
          disabled={busy}
          organisationOnly={matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG}
          listMaxHeight={140}
          renderActions={(c) => (
            <button type="button" className="btn" disabled={busy} onClick={() => openGlobalEdit(c)}>
              Edit
            </button>
          )}
        />
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
                if (globalEditFields.type === 'organisation' && !globalEditFields.tradingName.trim()) {
                  setGlobalEditErr('Trading name is required for organisations.')
                  return
                }
                const payload = contactFieldsModelToPayload(globalEditFields, {
                  fallbackName: globalEditContact.name,
                })
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
          const lawyerErr = lawyerClientsValidationError(matterContactType, lawyerLinkClientIds)
          if (lawyerErr) {
            setLawyerClientsErr(lawyerErr)
            setContactAddErr(lawyerErr)
            return
          }
          if (!selectedGlobalContactId) return
          setBusy(true)
          try {
            const linkBody: Record<string, unknown> = {
              contact_id: selectedGlobalContactId,
              matter_contact_type: matterContactType.trim(),
              matter_contact_reference: matterContactReference.trim() || null,
              letter_salutation: coerceLetterSalutation(
                letterSalutation,
                matterContactType,
                addSalutationContactType,
              ),
              letter_salutation_custom:
                coerceLetterSalutation(letterSalutation, matterContactType, addSalutationContactType) === 'custom'
                  ? (letterSalutationCustom ?? '').trim() || null
                  : null,
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
          onFieldsChange={(fields) => {
            setAddContactType(fields.type)
            if (matterContactType.trim()) {
              const contactType =
                matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? 'organisation' : fields.type
              const nextSalutation = coerceLetterSalutation(
                letterSalutation,
                matterContactType,
                contactType,
              )
              if (nextSalutation !== letterSalutation) {
                resetSalutationForAdd(matterContactType, contactType)
              }
            }
          }}
          onSubmit={async (payload) => {
            setContactAddErr(null)
            setActionErr(null)
            if (!matterContactType.trim()) {
              setContactAddErr(CONTACT_TYPE_REQUIRED_MSG)
              throw new Error(CONTACT_TYPE_REQUIRED_MSG)
            }
            const lawyerErr = lawyerClientsValidationError(matterContactType, lawyerLinkClientIds)
            if (lawyerErr) {
              setLawyerClientsErr(lawyerErr)
              setContactAddErr(lawyerErr)
              throw new Error(lawyerErr)
            }
            setBusy(true)
            try {
              const created = await apiFetch<ContactOut>('/contacts', {
                token,
                method: 'POST',
                json: payload,
              })
              const createContactType =
                matterContactType.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? 'organisation' : payload.type
              const createLinkBody: Record<string, unknown> = {
                contact_id: created.id,
                matter_contact_type: matterContactType.trim(),
                matter_contact_reference: matterContactReference.trim() || null,
                letter_salutation: coerceLetterSalutation(
                  letterSalutation,
                  matterContactType,
                  createContactType,
                ),
                letter_salutation_custom:
                  coerceLetterSalutation(letterSalutation, matterContactType, createContactType) === 'custom'
                    ? (letterSalutationCustom ?? '').trim() || null
                    : null,
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
  lawyerLinkableContacts,
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
  lawyerLinkableContacts: CaseContactOut[]
  onDone: () => void
  setActionErr: (v: string | null) => void
}) {
  const { askConfirm } = useDialogs()
  const [editMatterTypeOpen, setEditMatterTypeOpen] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const [lawyerClientsErr, setLawyerClientsErr] = useState<string | null>(null)

  const editMatterTypeOptions = useMemo(() => {
    const base = matterTypeOptions.map((o) => ({ value: o.value, label: o.label }))
    const current = editSnapshot.matter_contact_type
    if (current && !matterTypeOptions.some((o) => o.value === current)) {
      base.push({ value: current, label: current })
    }
    return base
  }, [matterTypeOptions, editSnapshot.matter_contact_type])

  return (
    <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
      <SingleSelectDropdown
        label="Contact type (required)"
        options={editMatterTypeOptions}
        value={editSnapshot.matter_contact_type ?? ''}
        onChange={(v) => {
          const val = v ? v : null
          const isLawyers = (val || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG
          const contactType = isLawyers ? ('organisation' as const) : editSnapshot.type
          const nextSalutation = coerceLetterSalutation(
            editSnapshot.letter_salutation,
            val || '',
            contactType,
          )
          setEditSnapshot({
            ...editSnapshot,
            matter_contact_type: val,
            ...(isLawyers ? { type: 'organisation' as const } : {}),
            letter_salutation: nextSalutation,
            letter_salutation_custom: nextSalutation === 'custom' ? editSnapshot.letter_salutation_custom : null,
          })
          if (!isLawyers) {
            setEditLawyerLinkClientIds([])
            setLawyerClientsErr(null)
          }
        }}
        open={editMatterTypeOpen}
        onOpenChange={setEditMatterTypeOpen}
        disabled={busy}
        placeholder="Select contact type"
      />
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
          <span>Linked contacts (required)</span>
          <div className="stack" style={{ gap: 6, maxHeight: 160, overflow: 'auto' }}>
            {lawyerLinkableContacts.length === 0 ? (
              <div className="muted">Add at least one other matter contact on this case first.</div>
            ) : (
              lawyerLinkableContacts.map((c) => (
                <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={editLawyerLinkClientIds.includes(c.id)}
                    disabled={busy}
                    style={{ marginTop: 3 }}
                    onChange={(e) => {
                      setEditLawyerLinkClientIds((prev) => {
                        let next: string[]
                        if (e.target.checked) {
                          if (prev.includes(c.id) || prev.length >= 4) return prev
                          next = [...prev, c.id]
                        } else {
                          next = prev.filter((x) => x !== c.id)
                        }
                        if (next.length > 0) setLawyerClientsErr(null)
                        return next
                      })
                    }}
                  />
                  <span>
                    {c.name}
                    <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                      {matterContactTypeLabel(c.matter_contact_type, matterTypeOptions)}
                    </span>
                  </span>
                </label>
              ))
            )}
          </div>
          {lawyerClientsErr ? <div className="error" style={{ marginTop: 8 }}>{lawyerClientsErr}</div> : null}
        </div>
      ) : null}
      {(editSnapshot.matter_contact_type || '').trim() ? (
        <LetterSalutationFields
          matterContactType={editSnapshot.matter_contact_type ?? ''}
          contactType={
            (editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG
              ? 'organisation'
              : editSnapshot.type
          }
          value={editSnapshot.letter_salutation}
          customValue={editSnapshot.letter_salutation_custom}
          busy={busy}
          onChange={({ letterSalutation, letterSalutationCustom }) =>
            setEditSnapshot({
              ...editSnapshot,
              letter_salutation: letterSalutation,
              letter_salutation_custom: letterSalutationCustom,
            })
          }
        />
      ) : null}
      <div className="muted" style={{ fontSize: 12 }}>
        Name and email below are the case snapshot; they can be pushed to the global card only when linked.
      </div>
      <ContactPersonOrgAddressFields
        busy={busy}
        organisationOnly={(editSnapshot.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG}
        value={contactOutToFormFields(editSnapshot as unknown as ContactOut)}
        onChange={(patch) =>
          setEditSnapshot((prev) => {
            if (!prev) return prev
            const next = applyCaseContactFieldPatch(prev, patch)
            if (patch.type !== undefined) {
              const contactType =
                (prev.matter_contact_type || '').trim().toLowerCase() === LAWYERS_TYPE_SLUG
                  ? 'organisation'
                  : patch.type
              const salutation = coerceLetterSalutation(
                prev.letter_salutation,
                prev.matter_contact_type || '',
                contactType,
              )
              return {
                ...next,
                letter_salutation: salutation,
                letter_salutation_custom: salutation === 'custom' ? prev.letter_salutation_custom : null,
              }
            }
            return next
          })
        }
      />
      {editSnapshot.contact_id ? (
        <label className="row" style={{ alignItems: 'center' }}>
          <input type="checkbox" checked={pushToGlobal} onChange={(e) => setPushToGlobal(e.target.checked)} disabled={busy} />
          <span className="muted">Also update global contact</span>
        </label>
      ) : null}
      <CaseContactPortalSection
        token={token}
        globalContactId={editSnapshot.contact_id}
        contactName={resolvedEditSnapshotName}
        contactEmail={editSnapshot.email}
      />
      {saveErr ? <div className="error">{saveErr}</div> : null}
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
            (editSnapshot.type === 'organisation' && !(editSnapshot.trading_name ?? '').trim()) ||
            !(editSnapshot.matter_contact_type && editSnapshot.matter_contact_type.trim())
          }
          onClick={async () => {
            setBusy(true)
            setSaveErr(null)
            setLawyerClientsErr(null)
            setActionErr(null)
            try {
              const lawyerErr = lawyerClientsValidationError(
                editSnapshot.matter_contact_type ?? '',
                editLawyerLinkClientIds,
              )
              if (lawyerErr) {
                setLawyerClientsErr(lawyerErr)
                setSaveErr(lawyerErr)
                setActionErr(lawyerErr)
                return
              }
              const payload = contactFieldsModelToPayload(
                contactOutToFormFields(editSnapshot as unknown as ContactOut),
                { fallbackName: editSnapshot.name },
              )
              if (!payload) {
                const msg = 'Enter a name (person or organisation fields).'
                setSaveErr(msg)
                setActionErr(msg)
                return
              }
              if (editSnapshot.type === 'organisation' && !(editSnapshot.trading_name ?? '').trim()) {
                const msg = 'Trading name is required for organisations.'
                setSaveErr(msg)
                setActionErr(msg)
                return
              }
              const resolvedSalutation = coerceLetterSalutation(
                editSnapshot.letter_salutation,
                editSnapshot.matter_contact_type ?? '',
                editSnapshot.type,
              )
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
                letter_salutation: resolvedSalutation,
                letter_salutation_custom:
                  resolvedSalutation === 'custom'
                    ? (editSnapshot.letter_salutation_custom ?? '').trim() || null
                    : null,
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
              const msg = (e as { message?: string })?.message ?? 'Failed to update snapshot'
              setSaveErr(msg)
              setActionErr(msg)
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
