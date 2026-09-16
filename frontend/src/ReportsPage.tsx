import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch, type ApiError } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { userCanAccessAdminConsole, type UserPublic } from './types'
import { AccountantPackBody, AccountantPackFilters, useAccountantPackSection } from './reports/AccountantPackSection'
import { AgedDebtReportBody, AgedDebtReportFilters, useAgedDebtReport } from './reports/AgedDebtReport'
import { BalancesReportBody, useBalancesReport } from './reports/BalancesReport'
import { BillingReportBody, BillingReportFilters, useBillingReport } from './reports/BillingReport'
import { CasesOpenedReportBody, CasesOpenedReportFilters, useCasesOpenedReport } from './reports/CasesOpenedReport'
import { CasesReportBody, CasesReportFilters, useCasesReport } from './reports/CasesReport'
import { ClientAccountReconcileSection } from './reports/ClientAccountReconcileSection'
import { EventsReportBody, EventsReportFilters, useEventsReport } from './reports/EventsReport'
import { ExceptionsReportBody, ExceptionsReportFilters, useExceptionsReport } from './reports/ExceptionsReport'
import { FeeEarnerFilter } from './reports/FeeEarnerFilter'
import { LedgerActivityReportBody, LedgerActivityReportFilters, useLedgerActivityReport } from './reports/LedgerActivityReport'
import type { ReportSectionShared } from './reports/sectionTypes'
import { TimeRecordedReportBody, TimeRecordedReportFilters, useTimeRecordedReport } from './reports/TimeRecordedReport'
import { REPORT_OPTIONS, type FeeEarnerPick, type ReportTab } from './reports/types'
import { WipReportBody, WipReportFilters, useWipReport } from './reports/WipReport'

export function ReportsPage({
  token,
  me,
  initialTab,
  onInitialTabConsumed,
}: {
  token: string
  me: UserPublic | null
  initialTab?: ReportTab
  onInitialTabConsumed?: () => void
}) {
  const [tab, setTab] = useState<ReportTab>(initialTab ?? 'client_office_balances')
  useEffect(() => {
    if (!initialTab) return
    setTab(initialTab)
    onInitialTabConsumed?.()
  }, [initialTab, onInitialTabConsumed])

  const [openFilterId, setOpenFilterId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [feeEarners, setFeeEarners] = useState<FeeEarnerPick[]>([])
  const [feeEarnerSelected, setFeeEarnerSelected] = useState<Set<string>>(new Set())

  const isAdmin = userCanAccessAdminConsole(me)
  const feeEarnerLocked = !isAdmin

  const feeEarnerPayload = useMemo(() => {
    const ids = Array.from(feeEarnerSelected)
    return { fee_earner_user_ids: ids }
  }, [feeEarnerSelected])

  const loadFeeEarners = useCallback(async () => {
    setErr(null)
    try {
      const rows = await apiFetch<FeeEarnerPick[]>('/reports/fee-earners', { token })
      setFeeEarners(rows)
      if (!isAdmin && me?.id) {
        setFeeEarnerSelected(new Set([me.id]))
      } else if (isAdmin && rows.length) {
        setFeeEarnerSelected(new Set(rows.map((r) => r.id)))
      }
    } catch (e) {
      setFeeEarners([])
      setErr((e as ApiError)?.message ?? 'Could not load fee earners')
    }
  }, [token, isAdmin, me?.id])

  useEffect(() => {
    void loadFeeEarners()
  }, [loadFeeEarners])

  function requireFeeEarners(): boolean {
    if (feeEarnerSelected.size === 0) {
      setErr('Select at least one fee earner.')
      return false
    }
    return true
  }

  const filterChrome = { openFilterId, setOpenFilterId }

  const shared: ReportSectionShared = {
    token,
    busy,
    setBusy,
    setErr,
    setOpenFilterId,
    requireFeeEarners,
    feeEarnerPayload,
  }

  const balances = useBalancesReport(tab === 'client_office_balances')
  const billing = useBillingReport(tab === 'billing')
  const timeRecorded = useTimeRecordedReport(tab === 'time_recorded')
  const wip = useWipReport(tab === 'wip')
  const agedDebt = useAgedDebtReport(tab === 'aged_debt')
  const exceptions = useExceptionsReport(tab === 'exceptions')
  const ledgerActivity = useLedgerActivityReport(tab === 'ledger_activity')
  const cases = useCasesReport(tab === 'cases')
  const casesOpened = useCasesOpenedReport(tab === 'cases_opened')
  const events = useEventsReport(tab === 'events', token)
  const accountantPack = useAccountantPackSection(tab === 'accountant_pack')

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="card casesTableCard reportsPageShell">
        <div className="reportsPageHeader">
          <h1 className="reportsPageTitle">Reports</h1>
          <p className="muted reportsPageLead" style={{ marginBottom: 16 }}>
            Run firm reports by fee earner. Exports use the same Excel format as merge-code downloads.
            {!isAdmin ? ' You can only include matters where you are the fee earner.' : null}
          </p>

          {err ? <div className="error">{err}</div> : null}

          <div className="reportsToolbar">
            <div className="reportsReportSelect">
              <SingleSelectDropdown
                label="Report"
                options={REPORT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                value={tab}
                onChange={(v) => {
                  setTab(v as ReportTab)
                  setOpenFilterId(null)
                }}
                disabled={busy}
              />
            </div>

            <div className="reportsFilterRow">
              {tab !== 'client_account_reconcile' ? (
                <FeeEarnerFilter
                  feeEarners={feeEarners}
                  feeEarnerSelected={feeEarnerSelected}
                  setFeeEarnerSelected={setFeeEarnerSelected}
                  isAdmin={isAdmin}
                  feeEarnerLocked={feeEarnerLocked}
                  openFilterId={openFilterId}
                  setOpenFilterId={setOpenFilterId}
                />
              ) : null}

              {tab === 'billing' ? <BillingReportFilters state={billing} chrome={filterChrome} /> : null}
              {tab === 'time_recorded' ? <TimeRecordedReportFilters state={timeRecorded} chrome={filterChrome} /> : null}
              {tab === 'wip' ? <WipReportFilters state={wip} chrome={filterChrome} /> : null}
              {tab === 'aged_debt' ? <AgedDebtReportFilters state={agedDebt} chrome={filterChrome} /> : null}
              {tab === 'exceptions' ? <ExceptionsReportFilters state={exceptions} chrome={filterChrome} /> : null}
              {tab === 'ledger_activity' ? (
                <LedgerActivityReportFilters state={ledgerActivity} chrome={filterChrome} />
              ) : null}
              {tab === 'accountant_pack' ? <AccountantPackFilters state={accountantPack} chrome={filterChrome} /> : null}
              {tab === 'cases' ? <CasesReportFilters state={cases} chrome={filterChrome} /> : null}
              {tab === 'cases_opened' ? <CasesOpenedReportFilters state={casesOpened} chrome={filterChrome} /> : null}
              {tab === 'events' ? <EventsReportFilters state={events} chrome={filterChrome} /> : null}
            </div>
          </div>
        </div>

        <div className="reportsPageBody">
          {tab === 'client_office_balances' ? (
            <BalancesReportBody shared={shared} preview={balances.preview} setPreview={balances.setPreview} />
          ) : null}
          {tab === 'billing' ? <BillingReportBody shared={shared} state={billing} /> : null}
          {tab === 'time_recorded' ? <TimeRecordedReportBody shared={shared} state={timeRecorded} /> : null}
          {tab === 'wip' ? <WipReportBody shared={shared} state={wip} /> : null}
          {tab === 'aged_debt' ? <AgedDebtReportBody shared={shared} state={agedDebt} /> : null}
          {tab === 'exceptions' ? <ExceptionsReportBody shared={shared} state={exceptions} /> : null}
          {tab === 'ledger_activity' ? <LedgerActivityReportBody shared={shared} state={ledgerActivity} /> : null}
          {tab === 'cases' ? <CasesReportBody shared={shared} state={cases} /> : null}
          {tab === 'cases_opened' ? <CasesOpenedReportBody shared={shared} state={casesOpened} /> : null}
          {tab === 'events' ? <EventsReportBody shared={shared} state={events} /> : null}
          {tab === 'accountant_pack' ? <AccountantPackBody shared={shared} state={accountantPack} /> : null}
          {tab === 'client_account_reconcile' ? (
            <ClientAccountReconcileSection
              token={token}
              busy={busy}
              setBusy={setBusy}
              setErr={setErr}
              active={tab === 'client_account_reconcile'}
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}
