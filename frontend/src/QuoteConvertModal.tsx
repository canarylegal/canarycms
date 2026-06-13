import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import {
  CASE_SOURCE_CUSTOM,
  CaseSourceField,
  resolveCaseSourcePayload,
  useCaseSources,
} from './CaseSourceField'
import { useDialogs } from './DialogProvider'
import {
  matterHeadDropdownOptions,
  matterHeadIdForSubType,
  matterSubDropdownOptions,
} from './matterTypeOptions'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseOut, CasePortalShareStatusOut, MatterHeadTypeOut, UserSummary } from './types'
import { useExclusiveDropdownOpen } from './useExclusiveDropdownOpen'

type Props = {
  token: string
  quoteCase: CaseOut
  users: UserSummary[]
  onClose: () => void
  onConverted: (result: { caseId: string; openAfter: boolean }) => void
}

export function QuoteConvertModal({ token, quoteCase, users, onClose, onConverted }: Props) {
  const { askConfirm } = useDialogs()
  const caseSources = useCaseSources(token)
  const [matterHeadTypes, setMatterHeadTypes] = useState<MatterHeadTypeOut[]>([])
  const [matterHeadTypeId, setMatterHeadTypeId] = useState('')
  const [feeEarner, setFeeEarner] = useState('')
  const [practiceArea, setPracticeArea] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [sourceCustomName, setSourceCustomName] = useState('')
  const [portalEnabled, setPortalEnabled] = useState(false)
  const [openAfter, setOpenAfter] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dropdown = useExclusiveDropdownOpen<'feeEarner' | 'head' | 'sub' | 'source'>()

  useEffect(() => {
    let cancelled = false
    void apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
      .then((data) => {
        if (!cancelled) setMatterHeadTypes(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setMatterHeadTypes([])
      })
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    setFeeEarner(quoteCase.fee_earner_user_id)
    const subId = quoteCase.matter_sub_type_id ?? ''
    setPracticeArea(subId)
    setMatterHeadTypeId(
      quoteCase.matter_head_type_id ?? matterHeadIdForSubType(matterHeadTypes, subId),
    )
    if (quoteCase.source_id) {
      setSourceId(quoteCase.source_id)
      setSourceCustomName('')
    } else if (quoteCase.source_name?.trim()) {
      setSourceId(CASE_SOURCE_CUSTOM)
      setSourceCustomName(quoteCase.source_name.trim())
    } else {
      setSourceId('')
      setSourceCustomName('')
    }
    setPortalEnabled(Boolean(quoteCase.portal_enabled))
    setOpenAfter(true)
    setErr(null)
  }, [quoteCase, matterHeadTypes])

  async function onPortalEnabledChange(checked: boolean) {
    if (checked) {
      setPortalEnabled(true)
      return
    }
    if (!quoteCase.portal_enabled) {
      setPortalEnabled(false)
      return
    }
    try {
      const status = await apiFetch<CasePortalShareStatusOut>(`/cases/${quoteCase.id}/portal/share-status`, {
        token,
      })
      if (status.active_grant_count > 0) {
        const shareNoun =
          status.active_grant_count === 1 ? '1 active folder share' : `${status.active_grant_count} active folder shares`
        const contactNoun = status.contact_count === 1 ? '1 contact' : `${status.contact_count} contacts`
        const ok = await askConfirm({
          title: 'Disable portal for this matter?',
          message: [
            `This matter has ${shareNoun} for ${contactNoun}.`,
            '',
            'Clients will immediately lose access to shared documents through the portal.',
            'Folder sharing settings are kept but inactive until portal is re-enabled.',
            '',
            'Disable portal for this matter?',
          ].join('\n'),
          danger: true,
          confirmLabel: 'Disable portal',
          cancelLabel: 'Keep portal enabled',
        })
        if (!ok) return
      }
    } catch {
      /* proceed — server will enforce on save if needed */
    }
    setPortalEnabled(false)
  }

  const feeEarnerOptions = useMemo(
    () =>
      users
        .filter(
          (u) =>
            u.is_active &&
            (u.can_be_fee_earner !== false || u.id === quoteCase.fee_earner_user_id),
        )
        .map((u) => ({ value: u.id, label: `${u.display_name} (${u.email})` })),
    [users, quoteCase.fee_earner_user_id],
  )

  const matterHeadOptions = useMemo(() => matterHeadDropdownOptions(matterHeadTypes), [matterHeadTypes])
  const matterSubOptions = useMemo(
    () => matterSubDropdownOptions(matterHeadTypes, matterHeadTypeId),
    [matterHeadTypes, matterHeadTypeId],
  )

  async function submit() {
    if (!feeEarner) {
      setErr('Select a fee earner.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const sourcePayload = resolveCaseSourcePayload(caseSources, sourceId, sourceCustomName)
      const json: Record<string, unknown> = {
        status: 'open',
        fee_earner_user_id: feeEarner,
        matter_sub_type_id: practiceArea || null,
        portal_enabled: portalEnabled,
      }
      if (sourcePayload.source_id) json.source_id = sourcePayload.source_id
      if (sourcePayload.source_name) json.source_name = sourcePayload.source_name
      await apiFetch(`/cases/${quoteCase.id}`, { method: 'PATCH', token, json })
      onConverted({ caseId: quoteCase.id, openAfter })
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not convert quote')
      setBusy(false)
    }
  }

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div className="modal card modal--scrollBody">
        <div className="paneHead">
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>Convert quote to Active matter</h2>
            <div className="muted">Confirm details before instructing this quote.</div>
          </div>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          <div className="card" style={{ padding: 12 }}>
            <div className="listTitle">{quoteCase.case_number}</div>
            <div className="muted">
              {[quoteCase.client_name, quoteCase.matter_description].filter(Boolean).join(' · ')}
            </div>
          </div>
          <SingleSelectDropdown
            label="Fee earner"
            options={feeEarnerOptions}
            value={feeEarner}
            onChange={setFeeEarner}
            open={dropdown.isOpen('feeEarner')}
            onOpenChange={(next) => dropdown.setOpen('feeEarner', next)}
            disabled={busy}
            placeholder="Select fee earner"
            emptyMessage={feeEarnerOptions.length === 0 ? 'No fee earners available.' : undefined}
          />
          <SingleSelectDropdown
            label="Matter type"
            options={matterHeadOptions}
            value={matterHeadTypeId}
            onChange={(v) => {
              setMatterHeadTypeId(v)
              setPracticeArea('')
            }}
            open={dropdown.isOpen('head')}
            onOpenChange={(next) => dropdown.setOpen('head', next)}
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
              open={dropdown.isOpen('sub')}
              onOpenChange={(next) => dropdown.setOpen('sub', next)}
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
            open={dropdown.isOpen('source')}
            onOpenChange={(next) => dropdown.setOpen('source', next)}
          />
          <label className="row field" style={{ gap: 10, alignItems: 'flex-start', cursor: busy ? 'default' : 'pointer' }}>
            <input
              type="checkbox"
              checked={portalEnabled}
              disabled={busy}
              onChange={(e) => void onPortalEnabledChange(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Enable portal
              <span className="muted" style={{ display: 'block', fontSize: 13, marginTop: 2 }}>
                Allow client folder sharing and portal notifications for this matter.
              </span>
            </span>
          </label>
          <label className="row taskEditCheckboxRow" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={openAfter}
              disabled={busy}
              onChange={(e) => setOpenAfter(e.target.checked)}
            />
            <span>Open matter after converting</span>
          </label>
          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
              Convert to Active
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
