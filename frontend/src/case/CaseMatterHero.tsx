import type { CaseOut, UserSummary } from '../types'
import { caseHasRevokedUserAccess, formatCaseStatusLabel } from '../types'
import { matterTypeDisplayLine } from './docFormat'

export type CaseMatterHeroProps = {
  caseDetail: CaseOut
  users: UserSummary[]
  busy: boolean
  backNavLabel: string
  onBackToMainMenu?: () => void
  onEditMatterDetails: () => void
}

export function CaseMatterHero({
  caseDetail,
  users,
  busy,
  backNavLabel,
  onBackToMainMenu,
  onEditMatterDetails,
}: CaseMatterHeroProps) {
  return (
    <div className="caseMatterHero">
      <div className="caseMatterHeroTop">
        <span className="caseMatterHeroRef mono">{caseDetail.case_number}</span>
        {onBackToMainMenu ? (
          <button
            type="button"
            className="btn caseMatterHeroBack"
            onClick={onBackToMainMenu}
            aria-label={backNavLabel}
            title={backNavLabel}
          >
            <svg
              className="caseMatterHeroBackIcon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M19 12H5"
                stroke="currentColor"
                strokeWidth="2.25"
                strokeLinecap="round"
              />
              <path
                d="M12 5 5 12l7 7"
                stroke="currentColor"
                strokeWidth="2.25"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : null}
      </div>
      <h2 className="caseMatterHeroClient">{caseDetail.matter_description || 'No description'}</h2>
      <p className="caseMatterHeroType">{matterTypeDisplayLine(caseDetail)}</p>
      <dl className="caseDetailsList caseMatterHeroDetails">
        <div className="caseDetailRow">
          <dt>Client</dt>
          <dd>{caseDetail.client_name ?? '—'}</dd>
        </div>
        <div className="caseDetailRow">
          <dt>Fee earner</dt>
          <dd>{users.find((u) => u.id === caseDetail.fee_earner_user_id)?.display_name ?? '—'}</dd>
        </div>
        {caseDetail.source_name ? (
          <div className="caseDetailRow">
            <dt>Source</dt>
            <dd>{caseDetail.source_name}</dd>
          </div>
        ) : null}
        <div className="caseDetailRow">
          <dt>Status</dt>
          <dd className={`caseMatterHeroStatusText caseMatterHeroStatusText--${caseDetail.status}`}>
            {formatCaseStatusLabel(caseDetail.status)}
          </dd>
        </div>
        <div className="caseDetailRow">
          <dt>Lock</dt>
          <dd>{caseHasRevokedUserAccess(caseDetail) ? 'Locked' : 'Unlocked'}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="btn primary caseMatterHeroEdit"
        disabled={busy}
        onClick={onEditMatterDetails}
      >
        Matter details
      </button>
    </div>
  )
}
