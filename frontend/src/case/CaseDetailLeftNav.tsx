import type { RefObject } from 'react'
import type {
  CaseContactOut,
  CaseEventsOut,
  CasePropertyDetailsOut,
  CasePropertyPayload,
  FinanceOut,
  LedgerOut,
  TaskMenuRow,
} from '../types'
import { CaseLeftMenuIcon } from './caseDetailChrome'
import { ledgerSignedGb } from './caseDetailHelpers'
import { financeCaseTotals, penceGb } from './financeTotals'
import { matterContactTypeLabel } from './matterLabels'
import { propertyTenureLabel } from './propertyLabels'

export type CaseDetailLeftDocPanel =
  | 'documents'
  | 'events'
  | 'finance'
  | 'property'
  | 'tasks'
  | 'contacts'
  | 'edit-details'
  | 'accounts'
  | 'portal-share'
  | 'portal-hub'

export type CaseDetailLeftOpen = {
  contacts: boolean
  accounts: boolean
  tasks: boolean
  property: boolean
  events: boolean
  finance: boolean
}

export type CaseDetailLeftAccordionKey = keyof CaseDetailLeftOpen

type Props = {
  busy: boolean
  caseDocPanel: CaseDetailLeftDocPanel
  leftOpen: CaseDetailLeftOpen
  toggleLeftAccordion: (key: CaseDetailLeftAccordionKey) => void
  goToOverview: () => void
  setCaseDocPanel: (panel: CaseDetailLeftDocPanel) => void
  caseContacts: CaseContactOut[]
  caseContactsMenuOrder: CaseContactOut[]
  matterTypeOptions: { value: string; label: string }[]
  contactRowMenu: null | { cc: CaseContactOut; x: number; y: number }
  setContactRowMenu: (v: null | { cc: CaseContactOut; x: number; y: number }) => void
  contactRowMenuRef: RefObject<HTMLDivElement | null>
  setContactAddOpen: (v: boolean) => void
  setEditSnapshot: (cc: CaseContactOut | null) => void
  setPushToGlobal: (v: boolean) => void
  setMatterContactType: (v: string) => void
  setMatterContactReference: (v: string) => void
  setLawyerLinkClientIds: (v: string[]) => void
  setContactAddErr: (v: string | null) => void
  setSelectedGlobalContactId: (v: string | null) => void
  accountsPreview: LedgerOut | null
  accountsPreviewErr: string | null
  hasTasksMenu: boolean
  sidebarTaskRows: TaskMenuRow[]
  hasPropertyMenu: boolean
  propertyLoading: boolean
  propertyDetails: CasePropertyDetailsOut | null
  setPropertyDraft: (d: CasePropertyPayload) => void
  setPropertyBaseline: (d: CasePropertyPayload) => void
  hasEventsMenu: boolean
  eventsPreview: CaseEventsOut | null
  openCaseEventModal: () => void
  hasFinanceMenu: boolean
  financePreview: FinanceOut | null
}

export function CaseDetailLeftNav({
  busy,
  caseDocPanel,
  leftOpen,
  toggleLeftAccordion,
  goToOverview,
  setCaseDocPanel,
  caseContacts,
  caseContactsMenuOrder,
  matterTypeOptions,
  contactRowMenu,
  setContactRowMenu,
  contactRowMenuRef,
  setContactAddOpen,
  setEditSnapshot,
  setPushToGlobal,
  setMatterContactType,
  setMatterContactReference,
  setLawyerLinkClientIds,
  setContactAddErr,
  setSelectedGlobalContactId,
  accountsPreview,
  accountsPreviewErr,
  hasTasksMenu,
  sidebarTaskRows,
  hasPropertyMenu,
  propertyLoading,
  propertyDetails,
  setPropertyDraft,
  setPropertyBaseline,
  hasEventsMenu,
  eventsPreview,
  openCaseEventModal,
  hasFinanceMenu,
  financePreview,
}: Props) {
  return (
    <>
      <div className="card caseMatterSections">
        <button
          type="button"
          className={`accHead caseLeftNavItem${caseDocPanel === 'documents' ? ' is-active' : ''}`}
          aria-current={caseDocPanel === 'documents' ? 'page' : undefined}
          onClick={goToOverview}
        >
          <CaseLeftMenuIcon name="overview" />
          <span>Overview</span>
        </button>
        <div className="accordion">
          <button
            className={`accHead${caseDocPanel === 'contacts' ? ' is-active' : ''}`}
            aria-expanded={leftOpen.contacts}
            aria-current={caseDocPanel === 'contacts' ? 'page' : undefined}
            onClick={() => toggleLeftAccordion('contacts')}
          >
            <CaseLeftMenuIcon name="contacts" />
            <span>Contacts</span>
            <span className="muted">{leftOpen.contacts ? '▾' : '▸'}</span>
          </button>
          {leftOpen.contacts ? (
            <div className="accBody">
              <>
                <div className="list caseLeftContactsList">
                  {caseContactsMenuOrder.map((cc) => (
                    <div
                      key={cc.id}
                      className="listCard caseLeftContactCard"
                      onDoubleClick={() => {
                        if (busy) return
                        setContactAddOpen(false)
                        setEditSnapshot(cc)
                        setPushToGlobal(false)
                        setCaseDocPanel('contacts')
                      }}
                      onContextMenu={(e) => {
                        e.preventDefault()
                        setContactRowMenu({ cc, x: e.clientX, y: e.clientY })
                      }}
                    >
                      <div className="caseLeftContactMeta">
                        <div className="listTitle">{cc.name}</div>
                        <div className="muted">
                          {matterContactTypeLabel(cc.matter_contact_type, matterTypeOptions)}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn caseLeftCompactBtn"
                        disabled={busy}
                        onClick={() => {
                          setContactAddOpen(false)
                          setEditSnapshot(cc)
                          setPushToGlobal(false)
                          setCaseDocPanel('contacts')
                        }}
                      >
                        Edit
                      </button>
                    </div>
                  ))}
                  {caseContacts.length === 0 ? <div className="muted">No contacts yet.</div> : null}
                </div>
                {contactRowMenu ? (
                  <div
                    ref={contactRowMenuRef}
                    className="docContextMenu"
                    style={{
                      position: 'fixed',
                      left: contactRowMenu.x,
                      top: contactRowMenu.y,
                      zIndex: 40,
                    }}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <div
                      className="docContextItem"
                      role="menuitem"
                      tabIndex={0}
                      onClick={() => {
                        const cc = contactRowMenu.cc
                        setContactRowMenu(null)
                        setContactAddOpen(false)
                        setEditSnapshot(cc)
                        setPushToGlobal(false)
                        setCaseDocPanel('contacts')
                      }}
                    >
                      Open
                    </div>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="btn primary caseLeftCompactBtn"
                  disabled={busy}
                  onClick={() => {
                    setEditSnapshot(null)
                    setMatterContactType('')
                    setMatterContactReference('')
                    setLawyerLinkClientIds([])
                    setContactAddErr(null)
                    setSelectedGlobalContactId(null)
                    setContactAddOpen(true)
                    setCaseDocPanel('contacts')
                  }}
                >
                  Add contact…
                </button>
              </>
            </div>
          ) : null}
        </div>
      </div>

      <div className="card">
        <div className="accordion">
          <button
            className={`accHead${caseDocPanel === 'accounts' ? ' is-active' : ''}`}
            aria-expanded={leftOpen.accounts}
            aria-current={caseDocPanel === 'accounts' ? 'page' : undefined}
            onClick={() => toggleLeftAccordion('accounts')}
          >
            <CaseLeftMenuIcon name="accounts" />
            <span>Accounts</span>
            <span className="muted">{leftOpen.accounts ? '▾' : '▸'}</span>
          </button>
          {leftOpen.accounts ? (
            <div className="accBody">
              {accountsPreviewErr ? (
                <div className="muted">{accountsPreviewErr}</div>
              ) : accountsPreview ? (
                <div className="stack caseLeftRailPreview">
                  <div>
                    Client balance:{' '}
                    <strong>{ledgerSignedGb(accountsPreview.client.balance_pence)}</strong>
                  </div>
                  <div>
                    Office balance:{' '}
                    <strong>{ledgerSignedGb(accountsPreview.office.balance_pence)}</strong>
                  </div>
                </div>
              ) : (
                <div className="muted">Loading…</div>
              )}
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => setCaseDocPanel('accounts')}
              >
                View accounts
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {hasTasksMenu ? (
        <div className="card">
          <div className="accordion">
            <button
              className={`accHead${caseDocPanel === 'tasks' ? ' is-active' : ''}`}
              aria-expanded={leftOpen.tasks}
              aria-current={caseDocPanel === 'tasks' ? 'page' : undefined}
              onClick={() => toggleLeftAccordion('tasks')}
            >
              <CaseLeftMenuIcon name="tasks" />
              <span>Tasks</span>
              <span className="muted">{leftOpen.tasks ? '▾' : '▸'}</span>
            </button>
            {leftOpen.tasks ? (
              <div className="accBody">
                <div className="caseLeftRailPreview">
                  {sidebarTaskRows.length === 0 ? 'No tasks yet.' : `${sidebarTaskRows.length} task(s).`}
                </div>
                <button
                  type="button"
                  className="btn primary"
                  style={{ marginTop: 8, width: '100%', boxSizing: 'border-box' }}
                  disabled={busy}
                  onClick={() => setCaseDocPanel('tasks')}
                >
                  View tasks
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasPropertyMenu ? (
        <div className="card">
          <div className="accordion">
            <button
              className={`accHead${caseDocPanel === 'property' ? ' is-active' : ''}`}
              aria-expanded={leftOpen.property}
              aria-current={caseDocPanel === 'property' ? 'page' : undefined}
              onClick={() => toggleLeftAccordion('property')}
            >
              <CaseLeftMenuIcon name="property" />
              <span>Property</span>
              <span className="muted">{leftOpen.property ? '▾' : '▸'}</span>
            </button>
            {leftOpen.property ? (
              <div className="accBody">
                {propertyLoading ? (
                  <div className="muted">Loading…</div>
                ) : !propertyDetails?.has_details ? (
                  <>
                    <div className="muted">No details added</div>
                    <button
                      type="button"
                      className="btn primary"
                      style={{ marginTop: 8 }}
                      disabled={busy}
                      onClick={() => {
                        const blank: CasePropertyPayload = {
                          is_non_postal: false,
                          uk: {},
                          free_lines: ['', '', '', '', '', ''],
                          title_numbers: [],
                          tenure: null,
                        }
                        setPropertyDraft(blank)
                        setPropertyBaseline(JSON.parse(JSON.stringify(blank)) as CasePropertyPayload)
                        setCaseDocPanel('property')
                      }}
                    >
                      Add
                    </button>
                  </>
                ) : (
                  <>
                    <div className="stack" style={{ gap: 4 }}>
                      {propertyDetails.payload.title_numbers
                        .map((t) => t.trim())
                        .filter(Boolean)
                        .map((t, i) => (
                          <div key={`title-${i}`}>Title number: {t}</div>
                        ))}
                      {propertyTenureLabel(propertyDetails.payload.tenure ?? undefined) ? (
                        <div>{propertyTenureLabel(propertyDetails.payload.tenure ?? undefined)}</div>
                      ) : null}
                      {propertyDetails.payload.existing_lender_case_contact_id ? (
                        <div>
                          Existing lender:{' '}
                          {caseContacts.find((c) => c.id === propertyDetails.payload.existing_lender_case_contact_id)
                            ?.name ?? '—'}
                        </div>
                      ) : null}
                      {propertyDetails.payload.charge_date ? (
                        <div>
                          Charge date:{' '}
                          {(() => {
                            const raw = propertyDetails.payload.charge_date ?? ''
                            const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw)
                            return m ? `${m[3]}/${m[2]}/${m[1]}` : raw
                          })()}
                        </div>
                      ) : null}
                      {(propertyDetails.payload.is_non_postal
                        ? propertyDetails.payload.free_lines
                        : [
                            propertyDetails.payload.uk.line1,
                            propertyDetails.payload.uk.line2,
                            propertyDetails.payload.uk.town,
                            propertyDetails.payload.uk.county,
                            propertyDetails.payload.uk.postcode,
                            propertyDetails.payload.uk.country,
                          ]
                      )
                        .map((ln) => (ln || '').trim())
                        .filter(Boolean)
                        .map((ln, i) => (
                          <div key={`prop-line-${i}`}>{ln}</div>
                        ))}
                    </div>
                    <button
                      type="button"
                      className="btn primary"
                      style={{ marginTop: 8 }}
                      disabled={busy}
                      onClick={() => {
                        const d: CasePropertyPayload = {
                          ...propertyDetails.payload,
                          free_lines: [...propertyDetails.payload.free_lines],
                          title_numbers: [...propertyDetails.payload.title_numbers],
                          tenure: propertyDetails.payload.tenure ?? null,
                        }
                        setPropertyDraft(d)
                        setPropertyBaseline(JSON.parse(JSON.stringify(d)) as CasePropertyPayload)
                        setCaseDocPanel('property')
                      }}
                    >
                      Edit
                    </button>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasEventsMenu ? (
        <div className="card">
          <div className="accordion">
            <button
              className={`accHead${caseDocPanel === 'events' ? ' is-active' : ''}`}
              aria-expanded={leftOpen.events}
              aria-current={caseDocPanel === 'events' ? 'page' : undefined}
              onClick={() => toggleLeftAccordion('events')}
            >
              <CaseLeftMenuIcon name="events" />
              <span>Calendar</span>
              <span className="muted">{leftOpen.events ? '▾' : '▸'}</span>
            </button>
            {leftOpen.events ? (
              <div className="accBody">
                {eventsPreview ? (
                  <div className="stack" style={{ gap: 6 }}>
                    {eventsPreview.events.length === 0 ? (
                      <div className="muted">No event lines yet.</div>
                    ) : (
                      eventsPreview.events.slice(0, 6).map((ev) => (
                        <div key={ev.id} className="muted" style={{ fontSize: 13 }}>
                          {ev.track_in_calendar ? (
                            <span title="Tracked in calendar" aria-hidden style={{ marginRight: 4 }}>
                              🔔
                            </span>
                          ) : null}
                          <strong style={{ color: 'var(--text)' }}>{ev.name}</strong>
                          {ev.event_date
                            ? ` · ${new Date(ev.event_date).toLocaleDateString('en-GB')}`
                            : ' · No date'}
                        </div>
                      ))
                    )}
                    {eventsPreview.events.length > 6 ? (
                      <div className="muted" style={{ fontSize: 12 }}>
                        +{eventsPreview.events.length - 6} more…
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="muted">Loading…</div>
                )}
                <div className="row" style={{ marginTop: 8, gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button type="button" className="btn" disabled={busy} onClick={() => openCaseEventModal()}>
                    New event
                  </button>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={busy}
                    onClick={() => setCaseDocPanel('events')}
                  >
                    View
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasFinanceMenu ? (
        <div className="card">
          <div className="accordion">
            <button
              className={`accHead${caseDocPanel === 'finance' ? ' is-active' : ''}`}
              aria-expanded={leftOpen.finance}
              aria-current={caseDocPanel === 'finance' ? 'page' : undefined}
              onClick={() => toggleLeftAccordion('finance')}
            >
              <CaseLeftMenuIcon name="finance" />
              <span>Finance</span>
              <span className="muted">{leftOpen.finance ? '▾' : '▸'}</span>
            </button>
            {leftOpen.finance ? (
              <div className="accBody">
                {financePreview ? (
                  (() => {
                    const { dr, cr } = financeCaseTotals(financePreview)
                    const net = cr - dr
                    const creditBal = net >= 0
                    return (
                      <div className="stack caseLeftRailPreview">
                        <div>
                          Credits: <strong>{penceGb(cr)}</strong>
                        </div>
                        <div>
                          Debits: <strong>{penceGb(dr)}</strong>
                        </div>
                        <div
                          className={
                            creditBal
                              ? 'caseFinanceBalance caseFinanceBalance--ok'
                              : 'caseFinanceBalance caseFinanceBalance--dr'
                          }
                        >
                          Balance:{' '}
                          <strong>{creditBal ? penceGb(net) : `-${penceGb(-net)}`}</strong>
                        </div>
                      </div>
                    )
                  })()
                ) : (
                  <div className="muted">Loading…</div>
                )}
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy}
                  onClick={() => setCaseDocPanel('finance')}
                >
                  Edit
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  )
}
