import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { GlobalContactCreateForm } from './GlobalContactCreateForm'
import { ContactSearchPicker } from './ContactSearchPicker'
import { CaseSourceField, resolveCaseSourcePayload, useCaseSources } from './CaseSourceField'
import { PropertyDetailsForm } from './case/PropertyDetailsForm'
import {
  blankPropertyPayload,
  buildNewMatterDescription,
  subTypeHasPropertyMenu,
} from './case/propertyMatterHelpers'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { matterContactTypeLabel } from './case/matterLabels'
import type { CaseOut, CasePropertyPayload, ContactOut, MatterHeadTypeOut, UserSummary } from './types'

type NewMatterPendingClient = {
  contact_id: string
  name: string
  email?: string | null
  phone?: string | null
}

export function NewMatterModal({
  token,
  currentUserId,
  onClose,
  onCreated,
  defaultStatus = 'open',
}: {
  token: string
  currentUserId: string
  onClose: () => void
  onCreated: (created?: CaseOut) => void
  defaultStatus?: 'open' | 'quote'
}) {
  const { askConfirm } = useDialogs()
  const caseSources = useCaseSources(token)
  const [matterDescription, setMatterDescription] = useState('')
  const [matterHeadTypeId, setMatterHeadTypeId] = useState('')
  const [practiceArea, setPracticeArea] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [sourceCustomName, setSourceCustomName] = useState('')
  const [feeEarner, setFeeEarner] = useState<string>(currentUserId)
  /** Active = open; Quote = quote (only these may be set on create). */
  const [newMatterStatus, setNewMatterStatus] = useState<'open' | 'quote'>(defaultStatus)
  const [portalEnabled, setPortalEnabled] = useState(false)
  const [step, setStep] = useState<'details' | 'property' | 'description' | 'contacts'>('details')
  const [propertyDraft, setPropertyDraft] = useState<CasePropertyPayload | null>(null)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [matterHeadTypes, setMatterHeadTypes] = useState<MatterHeadTypeOut[]>([])
  const [matterHeadOpen, setMatterHeadOpen] = useState(false)
  const [matterSubOpen, setMatterSubOpen] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [feeEarnerOpen, setFeeEarnerOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [selectedGlobalContact, setSelectedGlobalContact] = useState<ContactOut | null>(null)
  const [contactErr, setContactErr] = useState<string | null>(null)
  /** Client contacts to link after the matter is created (Finish). */
  const [pendingClientLinks, setPendingClientLinks] = useState<NewMatterPendingClient[]>([])
  const [newContactFormKey, setNewContactFormKey] = useState(0)

  const hasClientOnMatter = pendingClientLinks.length > 0

  const selectedSubType = useMemo(() => {
    if (!practiceArea) return null
    return matterHeadTypes.flatMap((h) => h.sub_types).find((s) => s.id === practiceArea) ?? null
  }, [practiceArea, matterHeadTypes])

  const matterHeadOptions = useMemo(
    () => matterHeadTypes.map((head) => ({ value: head.id, label: head.name })),
    [matterHeadTypes],
  )

  const matterSubOptions = useMemo(() => {
    const head = matterHeadTypes.find((h) => h.id === matterHeadTypeId)
    return (head?.sub_types ?? []).map((sub) => ({ value: sub.id, label: sub.name }))
  }, [matterHeadTypes, matterHeadTypeId])

  const feeEarnerOptions = useMemo(
    () => users.map((u) => ({ value: u.id, label: `${u.display_name} (${u.email})` })),
    [users],
  )

  const closeDetailsDropdowns = useCallback((except?: 'head' | 'sub' | 'source' | 'feeEarner') => {
    if (except !== 'head') setMatterHeadOpen(false)
    if (except !== 'sub') setMatterSubOpen(false)
    if (except !== 'source') setSourceOpen(false)
    if (except !== 'feeEarner') setFeeEarnerOpen(false)
  }, [])

  useEffect(() => {
    setNewMatterStatus(defaultStatus)
  }, [defaultStatus])

  useEffect(() => {
    setPropertyDraft(null)
  }, [practiceArea])

  useEffect(() => {
    setPracticeArea('')
    setMatterSubOpen(false)
  }, [matterHeadTypeId])

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) {
          const active = (Array.isArray(data) ? data : []).filter((u) => u.is_active && u.can_be_fee_earner !== false)
          setUsers(active)
          setFeeEarner((prev) => {
            if (prev && active.some((u) => u.id === prev)) return prev
            if (currentUserId && active.some((u) => u.id === currentUserId)) return currentUserId
            return active[0]?.id ?? ''
          })
        }
      } catch {
        // ignore; keep dropdown empty
      }
    }
    void loadUsers()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    let cancelled = false
    async function loadMatterTypes() {
      try {
        const data = await apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
        if (!cancelled) setMatterHeadTypes(data)
      } catch {
        // ignore; keep dropdown empty
      }
    }
    void loadMatterTypes()
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div className="modal card modal--scrollBody">
        <div className="paneHead">
          <div>
            <h2>New matter</h2>
            <div className="muted">Reference is generated automatically.</div>
          </div>
          <button className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <div className="modalBodyScroll">
        {step === 'details' ? (
        <div className="stack" style={{ marginTop: 12 }}>
          <SingleSelectDropdown
            label="Matter type"
            options={matterHeadOptions}
            value={matterHeadTypeId}
            onChange={setMatterHeadTypeId}
            open={matterHeadOpen}
            onOpenChange={(next) => {
              setMatterHeadOpen(next)
              if (next) closeDetailsDropdowns('head')
            }}
            disabled={busy}
            placeholder="— select —"
            emptyMessage={
              matterHeadOptions.length === 0
                ? 'No matter types available — add them under Admin → Matters.'
                : undefined
            }
          />
          {matterHeadTypeId ? (
            <SingleSelectDropdown
              label="Sub-type"
              options={matterSubOptions}
              value={practiceArea}
              onChange={setPracticeArea}
              open={matterSubOpen}
              onOpenChange={(next) => {
                setMatterSubOpen(next)
                if (next) closeDetailsDropdowns('sub')
              }}
              disabled={busy}
              placeholder="— select —"
              emptyMessage={
                matterSubOptions.length === 0
                  ? 'No sub-types for this matter type — add them under Admin → Matters.'
                  : undefined
              }
            />
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Choose a matter type, then pick a sub-type.
            </p>
          )}
          <CaseSourceField
            sources={caseSources}
            sourceId={sourceId}
            customName={sourceCustomName}
            onSourceIdChange={setSourceId}
            onCustomNameChange={setSourceCustomName}
            disabled={busy}
            open={sourceOpen}
            onOpenChange={(next) => {
              setSourceOpen(next)
              if (next) closeDetailsDropdowns('source')
            }}
          />
          <SingleSelectDropdown
            label="Fee earner"
            options={feeEarnerOptions}
            value={feeEarner}
            onChange={setFeeEarner}
            open={feeEarnerOpen}
            onOpenChange={(next) => {
              setFeeEarnerOpen(next)
              if (next) closeDetailsDropdowns('feeEarner')
            }}
            disabled={busy}
            placeholder="Select fee earner"
            emptyMessage={feeEarnerOptions.length === 0 ? 'No fee earners available.' : undefined}
          />
          <div className="field">
            <span>Status</span>
            <div className="row" style={{ gap: 20, marginTop: 6, flexWrap: 'wrap' }}>
              <label className="row" style={{ gap: 8, cursor: busy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="new-matter-status"
                  checked={newMatterStatus === 'open'}
                  onChange={() => setNewMatterStatus('open')}
                  disabled={busy}
                />
                <span>Active</span>
              </label>
              <label className="row" style={{ gap: 8, cursor: busy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="new-matter-status"
                  checked={newMatterStatus === 'quote'}
                  onChange={() => setNewMatterStatus('quote')}
                  disabled={busy}
                />
                <span>Quote</span>
              </label>
            </div>
          </div>
          <label className="row field" style={{ gap: 10, alignItems: 'flex-start', cursor: busy ? 'default' : 'pointer' }}>
            <input
              type="checkbox"
              checked={portalEnabled}
              disabled={busy}
              onChange={(e) => setPortalEnabled(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Enable portal
              <span className="muted" style={{ display: 'block', fontSize: 13, marginTop: 2 }}>
                Allow client folder sharing and portal notifications for this matter.
              </span>
            </span>
          </label>
          {err ? <div className="error">{err}</div> : null}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => {
                setErr(null)
                setContactErr(null)
                if (!matterHeadTypeId) {
                  setErr('Select a matter type.')
                  return
                }
                if (!practiceArea) {
                  setErr('Select a sub-type.')
                  return
                }
                const sub = selectedSubType
                if (subTypeHasPropertyMenu(sub)) {
                  setPropertyDraft((d) => d ?? blankPropertyPayload())
                  setStep('property')
                } else {
                  setPropertyDraft(null)
                  setMatterDescription(buildNewMatterDescription(sub?.prefix ?? null, null))
                  setStep('description')
                }
              }}
            >
              Continue
            </button>
          </div>
        </div>
        ) : null}

        {step === 'property' && propertyDraft ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 8 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Property details</h2>
                <div className="muted">Same fields as the Property sub-menu on the matter.</div>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setErr(null)
                  setStep('details')
                }}
                disabled={busy}
              >
                Back
              </button>
            </div>
            <div className="card" style={{ padding: 12 }}>
              <PropertyDetailsForm draft={propertyDraft} onChange={setPropertyDraft} disabled={busy} />
            </div>
            {err ? <div className="error">{err}</div> : null}
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  setErr(null)
                  setMatterDescription(
                    buildNewMatterDescription(selectedSubType?.prefix ?? null, propertyDraft),
                  )
                  setStep('description')
                }}
              >
                Continue
              </button>
            </div>
          </div>
        ) : null}

        {step === 'description' ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 8 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Description</h2>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setErr(null)
                  if (selectedSubType && subTypeHasPropertyMenu(selectedSubType)) {
                    setPropertyDraft((d) => d ?? blankPropertyPayload())
                    setStep('property')
                  } else {
                    setStep('details')
                  }
                }}
                disabled={busy}
              >
                Back
              </button>
            </div>
            <label className="field">
              <span>Description</span>
              <input
                value={matterDescription}
                onChange={(e) => setMatterDescription(e.target.value)}
                disabled={busy}
              />
            </label>
            {err ? <div className="error">{err}</div> : null}
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy || !matterDescription.trim()}
                onClick={() => {
                  setErr(null)
                  setContactErr(null)
                  setStep('contacts')
                }}
              >
                Continue
              </button>
            </div>
          </div>
        ) : null}

        {step === 'contacts' ? (
          <div className="card" style={{ marginTop: 12, padding: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Contacts</h2>
                <div className="muted">Link at least one client contact, then finish to create the matter.</div>
              </div>
              <button className="btn" onClick={() => setStep('description')} disabled={busy}>
                Back
              </button>
            </div>

            <div className="stack">
              <div className="muted">Clients for this matter (you can add more than one):</div>
              <div className="list scrollPanel--compact" style={{ marginTop: 12 }}>
                {pendingClientLinks.map((cc) => (
                  <div key={cc.contact_id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                    <div>
                      <div className="listTitle">
                        {cc.name} <span className="muted">· {matterContactTypeLabel('client')}</span>
                      </div>
                      <div className="muted">{cc.email ?? cc.phone ?? '—'}</div>
                    </div>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await askConfirm({
                          title: 'Remove contact',
                          message: 'Remove this contact from the list?',
                          danger: true,
                          confirmLabel: 'Remove',
                        })
                        if (!ok) return
                        setContactErr(null)
                        setPendingClientLinks((prev) => prev.filter((p) => p.contact_id !== cc.contact_id))
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {pendingClientLinks.length === 0 ? <div className="muted">None added yet.</div> : null}
              </div>

              <label className="field">
                <span>Search existing global contacts</span>
                <ContactSearchPicker
                  token={token}
                  value={selectedGlobalContact?.id ?? null}
                  onChange={(_id, contact) => setSelectedGlobalContact(contact ?? null)}
                  disabled={busy}
                  filterContact={(c) => !pendingClientLinks.some((p) => p.contact_id === c.id)}
                  listMaxHeight={160}
                />
              </label>

              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="btn primary"
                  disabled={
                    busy ||
                    !selectedGlobalContact ||
                    pendingClientLinks.some((p) => p.contact_id === selectedGlobalContact.id)
                  }
                  onClick={() => {
                    if (!selectedGlobalContact) return
                    const c = selectedGlobalContact
                    setContactErr(null)
                    setErr(null)
                    setPendingClientLinks((prev) => [
                      ...prev,
                      {
                        contact_id: c.id,
                        name: c.name,
                        email: c.email,
                        phone: c.phone,
                      },
                    ])
                    setSelectedGlobalContact(null)
                  }}
                >
                  Link as client
                </button>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <GlobalContactCreateForm
                  key={newContactFormKey}
                  busy={busy}
                  submitLabel="Create & add as client"
                  intro={
                    <div className="muted" style={{ marginBottom: 8 }}>
                      Create new contact and add as client for this matter
                    </div>
                  }
                  onSubmit={async (payload) => {
                    setBusy(true)
                    setContactErr(null)
                    setErr(null)
                    try {
                      const created = await apiFetch<ContactOut>('/contacts', {
                        token,
                        method: 'POST',
                        json: payload,
                      })
                      setPendingClientLinks((prev) => [
                        ...prev,
                        {
                          contact_id: created.id,
                          name: created.name,
                          email: created.email,
                          phone: created.phone,
                        },
                      ])
                      setNewContactFormKey((k) => k + 1)
                    } catch (e: any) {
                      setContactErr(e?.message ?? 'Failed to create contact')
                      throw e
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              </div>

              {err ? <div className="error">{err}</div> : null}
              {contactErr ? <div className="error">{contactErr}</div> : null}
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
                <button
                  className="btn primary"
                  disabled={busy || !hasClientOnMatter}
                  onClick={async () => {
                    if (!hasClientOnMatter) return
                    if (!feeEarner) {
                      setErr('Select a fee earner.')
                      return
                    }
                    setBusy(true)
                    setErr(null)
                    setContactErr(null)
                    try {
                      const created = await apiFetch<CaseOut>('/cases', {
                        token,
                        json: {
                          matter_description: matterDescription.trim(),
                          status: newMatterStatus,
                          matter_sub_type_id: practiceArea || null,
                          fee_earner_user_id: feeEarner,
                          portal_enabled: portalEnabled,
                          ...resolveCaseSourcePayload(caseSources, sourceId, sourceCustomName),
                        },
                      })
                      for (const p of pendingClientLinks) {
                        await apiFetch(`/cases/${created.id}/contacts`, {
                          token,
                          json: {
                            contact_id: p.contact_id,
                            matter_contact_type: 'client',
                            matter_contact_reference: null,
                          },
                        })
                      }
                      if (selectedSubType && subTypeHasPropertyMenu(selectedSubType) && propertyDraft) {
                        const lines = [...propertyDraft.free_lines]
                        while (lines.length < 6) lines.push('')
                        await apiFetch(`/cases/${created.id}/property-details`, {
                          token,
                          method: 'PUT',
                          json: { ...propertyDraft, free_lines: lines.slice(0, 6) },
                        })
                      }
                      onCreated(created)
                    } catch (e: any) {
                      setErr(e?.message ?? 'Could not create matter')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Finish
                </button>
              </div>
            </div>
          </div>
        ) : null}
        </div>
      </div>
    </div>
  )
}


