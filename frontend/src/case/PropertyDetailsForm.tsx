import { useMemo, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import { GlobalContactCreateForm } from '../GlobalContactCreateForm'
import { ContactSearchPicker } from '../ContactSearchPicker'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import type { CaseContactOut, CasePropertyPayload, CasePropertyTenure, ContactOut } from '../types'

const TENURE_OPTIONS: { value: CasePropertyTenure; label: string }[] = [
  { value: 'freehold', label: 'Freehold' },
  { value: 'leasehold', label: 'Leasehold' },
  { value: 'commonhold', label: 'Commonhold' },
]

const EXISTING_LENDER_SLUG = 'existing-lender'

type Props = {
  draft: CasePropertyPayload
  onChange: (next: CasePropertyPayload) => void
  disabled?: boolean
  /** When omitted (new-matter wizard), existing-lender linking is hidden until the matter exists. */
  token?: string
  caseId?: string
  caseContacts?: CaseContactOut[]
  onCaseContactsChange?: () => void | Promise<void>
}

/** Same field layout as the Property sub-menu editor in CaseDetail. */
export function PropertyDetailsForm({
  draft,
  onChange,
  disabled,
  token,
  caseId,
  caseContacts = [],
  onCaseContactsChange,
}: Props) {
  const [tenureOpen, setTenureOpen] = useState(false)
  const [lenderMode, setLenderMode] = useState<'none' | 'matter' | 'directory' | 'create'>('none')
  const [selectedGlobalContactId, setSelectedGlobalContactId] = useState<string | null>(null)
  const [lenderBusy, setLenderBusy] = useState(false)
  const [lenderErr, setLenderErr] = useState<string | null>(null)

  const tenureOptions = useMemo(
    () => TENURE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    [],
  )

  const existingLenderContacts = useMemo(
    () =>
      caseContacts.filter(
        (c) => (c.matter_contact_type || '').trim().toLowerCase() === EXISTING_LENDER_SLUG,
      ),
    [caseContacts],
  )

  const lenderDropdownOptions = useMemo(
    () => [
      { value: '', label: '— none —' },
      ...existingLenderContacts.map((c) => ({ value: c.id, label: c.name || 'Contact' })),
    ],
    [existingLenderContacts],
  )

  async function linkGlobalAsExistingLender(contactId: string) {
    if (!token || !caseId || !onCaseContactsChange) return
    setLenderBusy(true)
    setLenderErr(null)
    try {
      const linked = await apiFetch<CaseContactOut>(`/cases/${caseId}/contacts`, {
        token,
        method: 'POST',
        json: {
          contact_id: contactId,
          matter_contact_type: EXISTING_LENDER_SLUG,
          matter_contact_reference: null,
          letter_salutation: null,
          letter_salutation_custom: null,
        },
      })
      await onCaseContactsChange()
      onChange({ ...draft, existing_lender_case_contact_id: linked.id })
      setLenderMode('matter')
      setSelectedGlobalContactId(null)
    } catch (e: unknown) {
      setLenderErr((e as ApiError).message ?? 'Could not link existing lender')
    } finally {
      setLenderBusy(false)
    }
  }

  return (
    <div className="stack" style={{ marginTop: 12 }}>
      <div className="muted" style={{ fontWeight: 600 }}>
        Title number(s)
      </div>
      {draft.title_numbers.map((t, i) => (
        <div key={i} className="row" style={{ gap: 8 }}>
          <input
            style={{ flex: 1 }}
            value={t}
            disabled={disabled}
            onChange={(e) => {
              const next = [...draft.title_numbers]
              next[i] = e.target.value
              onChange({ ...draft, title_numbers: next })
            }}
          />
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => {
              const next = draft.title_numbers.filter((_, j) => j !== i)
              onChange({ ...draft, title_numbers: next })
            }}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn"
        disabled={disabled}
        onClick={() =>
          onChange({
            ...draft,
            title_numbers: [...draft.title_numbers, ''],
          })
        }
      >
        Add title number
      </button>
      <SingleSelectDropdown
        label="Tenure"
        options={tenureOptions}
        value={draft.tenure ?? ''}
        onChange={(v) =>
          onChange({
            ...draft,
            tenure: v === '' ? null : (v as CasePropertyTenure),
          })
        }
        open={tenureOpen}
        onOpenChange={setTenureOpen}
        disabled={disabled}
        placeholder="—"
      />

      <div style={{ fontWeight: 600, marginTop: 8 }}>Existing lender</div>
      {!caseId || !token ? (
        <div className="muted" style={{ fontSize: 13 }}>
          Save the matter first, then open Property to link an existing lender contact.
        </div>
      ) : (
        <>
      <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
        Link an existing lender contact on this matter, pick one from the global directory, or create a new contact
        (added to Contacts as Existing lender).
      </div>
      {lenderErr ? <div className="error">{lenderErr}</div> : null}
      <SingleSelectDropdown
        label="Existing lender on this matter"
        options={lenderDropdownOptions}
        value={draft.existing_lender_case_contact_id ?? ''}
        onChange={(v) => {
          onChange({
            ...draft,
            existing_lender_case_contact_id: v || null,
          })
          if (v) setLenderMode('matter')
        }}
        disabled={disabled || lenderBusy}
        placeholder="— none —"
      />
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn"
          disabled={disabled || lenderBusy}
          onClick={() => setLenderMode(lenderMode === 'directory' ? 'none' : 'directory')}
        >
          {lenderMode === 'directory' ? 'Hide directory search' : 'Choose from directory…'}
        </button>
        <button
          type="button"
          className="btn"
          disabled={disabled || lenderBusy}
          onClick={() => setLenderMode(lenderMode === 'create' ? 'none' : 'create')}
        >
          {lenderMode === 'create' ? 'Hide create form' : 'Create new lender…'}
        </button>
      </div>
      {lenderMode === 'directory' ? (
        <div className="card" style={{ padding: 12 }}>
          <ContactSearchPicker
            token={token}
            value={selectedGlobalContactId}
            onChange={(id) => setSelectedGlobalContactId(id)}
            disabled={disabled || lenderBusy}
            organisationOnly
          />
          <button
            type="button"
            className="btn primary"
            style={{ marginTop: 8 }}
            disabled={disabled || lenderBusy || !selectedGlobalContactId}
            onClick={() => {
              if (selectedGlobalContactId) void linkGlobalAsExistingLender(selectedGlobalContactId)
            }}
          >
            Add as existing lender
          </button>
        </div>
      ) : null}
      {lenderMode === 'create' ? (
        <div className="card" style={{ padding: 12 }}>
          <GlobalContactCreateForm
            organisationOnly
            busy={lenderBusy}
            formError={lenderErr}
            submitLabel="Create & link as existing lender"
            intro={<div className="muted" style={{ marginBottom: 8 }}>New existing lender contact</div>}
            onSubmit={async (payload) => {
              setLenderErr(null)
              setLenderBusy(true)
              try {
                const created = await apiFetch<ContactOut>('/contacts', {
                  token,
                  method: 'POST',
                  json: payload,
                })
                await linkGlobalAsExistingLender(created.id)
              } catch (e: unknown) {
                setLenderErr((e as ApiError).message ?? 'Could not create lender')
                throw e
              } finally {
                setLenderBusy(false)
              }
            }}
          />
        </div>
      ) : null}
        </>
      )}

      <label className="field">
        <span>Charge date</span>
        <input
          type="date"
          value={draft.charge_date ?? ''}
          disabled={disabled}
          onChange={(e) =>
            onChange({
              ...draft,
              charge_date: e.target.value.trim() || null,
            })
          }
        />
      </label>

      <label className="row" style={{ alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          checked={draft.is_non_postal}
          disabled={disabled}
          onChange={(e) => onChange({ ...draft, is_non_postal: e.target.checked })}
        />
        <span>Non-postal address (free lines)</span>
      </label>
      {!draft.is_non_postal ? (
        <>
          <label className="field">
            <span>Address line 1</span>
            <input
              value={draft.uk.line1 ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, line1: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Address line 2</span>
            <input
              value={draft.uk.line2 ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, line2: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Town / city</span>
            <input
              value={draft.uk.town ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, town: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>County</span>
            <input
              value={draft.uk.county ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, county: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Postcode</span>
            <input
              value={draft.uk.postcode ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, postcode: e.target.value },
                })
              }
            />
          </label>
          <label className="field">
            <span>Country</span>
            <input
              value={draft.uk.country ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...draft,
                  uk: { ...draft.uk, country: e.target.value },
                })
              }
            />
          </label>
        </>
      ) : (
        [0, 1, 2, 3, 4, 5].map((i) => (
          <label key={i} className="field">
            <span>Address line {i + 1}</span>
            <input
              value={draft.free_lines[i] ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const next = [...draft.free_lines]
                next[i] = e.target.value
                onChange({ ...draft, free_lines: next })
              }}
            />
          </label>
        ))
      )}
    </div>
  )
}
