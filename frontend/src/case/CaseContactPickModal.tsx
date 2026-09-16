import type { Dispatch, SetStateAction } from 'react'
import { ContactSearchPicker } from '../ContactSearchPicker'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { shouldUseGraphDraftForMatterEmail } from '../emailLauncher'
import type { CaseContactOut, ContactOut, UserPublic } from '../types'
import { LAWYERS_TYPE_SLUG } from './caseDetailHelpers'
import { matterContactTypeLabel } from './matterLabels'

export type CaseContactPickModalProps = {
  contactPickModal: {
    composeKind?: 'email' | 'letter' | string
    attachmentFileIds?: string[]
  }
  currentUser?: UserPublic | null
  contactPickErr: string | null
  contactPickMatterOptions: { value: string; label: string }[]
  pickMatterCcId: string
  setPickMatterCcId: (v: string) => void
  contactPickMatterOpen: boolean
  setContactPickMatterOpen: (v: boolean) => void
  token: string
  pickSelectedContact: ContactOut | null
  setPickSelectedContact: (c: ContactOut | null) => void
  busy: boolean
  pickLinkType: string
  pickLinkGlobal: boolean
  setPickLinkGlobal: (v: boolean) => void
  contactPickTypeOptions: { value: string; label: string }[]
  setPickLinkType: (v: string) => void
  setContactPickErr: (v: string | null) => void
  pickLawyerClientIds: string[]
  setPickLawyerClientIds: Dispatch<SetStateAction<string[]>>
  contactPickTypeOpen: boolean
  setContactPickTypeOpen: (v: boolean) => void
  lawyerLinkableMatterContacts: CaseContactOut[]
  matterTypeOptions: { value: string; label: string }[]
  onClose: () => void
  onContinue: () => void
}

export function CaseContactPickModal({
  contactPickModal,
  currentUser,
  contactPickErr,
  contactPickMatterOptions,
  pickMatterCcId,
  setPickMatterCcId,
  contactPickMatterOpen,
  setContactPickMatterOpen,
  setContactPickTypeOpen,
  token,
  pickSelectedContact,
  setPickSelectedContact,
  busy,
  pickLinkType,
  pickLinkGlobal,
  setPickLinkGlobal,
  contactPickTypeOptions,
  setPickLinkType,
  setContactPickErr,
  pickLawyerClientIds,
  setPickLawyerClientIds,
  contactPickTypeOpen,
  lawyerLinkableMatterContacts,
  matterTypeOptions,
  onClose,
  onContinue,
}: CaseContactPickModalProps) {
  return (
      <div
        className="modalOverlay"
        role="dialog"
        aria-modal="true"
      >
        <div className="modal card modal--scrollBody" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
          <div className="paneHead">
            <div>
              <h2 style={{ margin: 0, fontSize: 18 }}>
                {contactPickModal.composeKind === 'email' ? 'E-mail recipient' : 'Letter recipient'}
              </h2>
              <div className="muted">
                {contactPickModal.composeKind === 'email' ? (
                  <>
                    Optional: pick a recipient to pre-fill <strong>To</strong>.
                    {(contactPickModal.attachmentFileIds?.length ?? 0) > 0 &&
                    shouldUseGraphDraftForMatterEmail(
                      currentUser,
                      contactPickModal.attachmentFileIds ?? [],
                    ) ? (
                      <>
                        {' '}
                        Canary creates an Outlook draft via Microsoft Graph with the quote attached.
                        {currentUser?.email_launch_preference === 'outlook_web' ? (
                          <> Outlook on the web opens for review.</>
                        ) : (
                          <>
                            {' '}
                            With <strong>Outlook</strong> selected under desktop e-mail settings, the Canary Outlook
                            add-in opens compose; the draft is also in Drafts as a fallback.
                          </>
                        )}
                      </>
                    ) : (contactPickModal.attachmentFileIds?.length ?? 0) > 0 ? (
                      <>
                        {' '}
                        Compose opens in your mail program with merged subject and body. Attach the quote using{' '}
                        <strong>Compose from matter</strong> in the Canary Thunderbird or Outlook add-in.
                      </>
                    ) : (
                      <>
                        {' '}
                        Compose opens in your mail program (or Outlook on the web) with merged subject and body.
                        Attach case files with <strong>Compose from matter</strong> in the Canary Outlook or
                        Thunderbird add-in.
                      </>
                    )}
                  </>
                ) : (
                  <>
                    Matter contact (choose &quot;All clients&quot; to fill every client merge slot), none, or search for a
                    global contact below.
                  </>
                )}
              </div>
            </div>
            <button
              type="button"
              className="btn"
              onClick={onClose}
            >
              Close
            </button>
          </div>
          <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
            {contactPickErr ? <div className="error">{contactPickErr}</div> : null}
            <SingleSelectDropdown
              label="Matter contact"
              options={contactPickMatterOptions}
              value={pickMatterCcId}
              onChange={(v) => {
                setPickMatterCcId(v)
                setPickSelectedContact(null)
              }}
              open={contactPickMatterOpen}
              onOpenChange={(next) => {
                setContactPickMatterOpen(next)
                if (next) setContactPickTypeOpen(false)
              }}
              emptyMessage="No matter contacts on this case yet."
            />
            <div className="muted" style={{ fontSize: 12 }}>
              Or search for a global contact (results appear when your search matches):
            </div>
            <ContactSearchPicker
              token={token}
              value={pickSelectedContact?.id ?? null}
              onChange={(id, contact) => {
                setPickSelectedContact(contact ?? null)
                if (id) setPickMatterCcId('none')
              }}
              disabled={busy}
              organisationOnly={pickLinkType.trim().toLowerCase() === LAWYERS_TYPE_SLUG}
              listMaxHeight={120}
              searchPlaceholder="Search global…"
            />
            {pickSelectedContact ? (
              <label className="row" style={{ alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={pickLinkGlobal}
                  onChange={(e) => setPickLinkGlobal(e.target.checked)}
                />
                <span className="muted">Link this contact to the current matter</span>
              </label>
            ) : null}
            {pickLinkGlobal ? (
              <SingleSelectDropdown
                label="Contact type (required to link)"
                options={contactPickTypeOptions}
                value={pickLinkType}
                onChange={(v) => {
                  setPickLinkType(v)
                  setContactPickErr(null)
                  if (v.trim().toLowerCase() !== LAWYERS_TYPE_SLUG) {
                    setPickLawyerClientIds([])
                  } else if (pickSelectedContact?.type === 'person') {
                    setPickSelectedContact(null)
                  }
                }}
                open={contactPickTypeOpen}
                onOpenChange={(next) => {
                  setContactPickTypeOpen(next)
                  if (next) setContactPickMatterOpen(false)
                }}
                placeholder="— select —"
              />
            ) : null}
            {pickLinkGlobal && pickLinkType.trim().toLowerCase() === LAWYERS_TYPE_SLUG ? (
              <div className="field">
                <span>Linked contacts (required)</span>
                <div className="stack" style={{ gap: 6, maxHeight: 120, overflow: 'auto' }}>
                  {lawyerLinkableMatterContacts.length === 0 ? (
                    <div className="muted">Add at least one other matter contact on this case first.</div>
                  ) : (
                    lawyerLinkableMatterContacts.map((c) => (
                      <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'flex-start' }}>
                        <input
                          type="checkbox"
                          checked={pickLawyerClientIds.includes(c.id)}
                          style={{ marginTop: 3 }}
                          onChange={(e) => {
                            setPickLawyerClientIds((prev) => {
                              let next: string[]
                              if (e.target.checked) {
                                if (prev.includes(c.id) || prev.length >= 4) return prev
                                next = [...prev, c.id]
                              } else {
                                next = prev.filter((x) => x !== c.id)
                              }
                              if (next.length > 0) setContactPickErr(null)
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
              </div>
            ) : null}
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
              <button
                type="button"
                className="btn"
                onClick={onClose}
              >
                Cancel
              </button>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void onContinue()}>
                Continue
              </button>
            </div>
          </div>
        </div>
      </div>
  )
}
