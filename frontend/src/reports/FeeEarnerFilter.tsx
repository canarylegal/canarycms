import type { FeeEarnerPick } from './types'
import { FilterDropdown } from './FilterDropdown'
import { scrollPanelClassName } from '../dropdownSizing'
import { feeEarnerSummary } from './utils'

export function FeeEarnerFilter({
  feeEarners,
  feeEarnerSelected,
  setFeeEarnerSelected,
  isAdmin,
  feeEarnerLocked,
  openFilterId,
  setOpenFilterId,
}: {
  feeEarners: FeeEarnerPick[]
  feeEarnerSelected: Set<string>
  setFeeEarnerSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  isAdmin: boolean
  feeEarnerLocked: boolean
  openFilterId: string | null
  setOpenFilterId: (v: string | null) => void
}) {
  const allFeeIds = feeEarners.map((u) => u.id)
  const feSummary = feeEarnerSummary(feeEarnerSelected, feeEarners, feeEarnerLocked)

  return (
    <FilterDropdown
      id="fe"
      label="Fee earners"
      summary={feSummary}
      openId={openFilterId}
      setOpenId={setOpenFilterId}
      fitContentItemCount={feeEarners.length}
      footer={
        isAdmin ? (
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn--small" onClick={() => setFeeEarnerSelected(new Set(allFeeIds))}>
              All
            </button>
            <button type="button" className="btn btn--small" onClick={() => setFeeEarnerSelected(new Set())}>
              Clear
            </button>
          </div>
        ) : undefined
      }
    >
      <div className={scrollPanelClassName('reportsDdCheckList', feeEarners.length)}>
        {feeEarners.map((u) => (
          <label key={u.id} className="reportsCheckbox">
            <input
              type="checkbox"
              checked={feeEarnerSelected.has(u.id)}
              onChange={() => {
                if (feeEarnerLocked) return
                setFeeEarnerSelected((prev) => {
                  const next = new Set(prev)
                  if (next.has(u.id)) next.delete(u.id)
                  else next.add(u.id)
                  return next
                })
              }}
              disabled={feeEarnerLocked}
            />
            <span>
              {u.display_name}
              <span className="muted" style={{ fontSize: 12 }}>
                {' '}
                ({u.email})
              </span>
            </span>
          </label>
        ))}
      </div>
    </FilterDropdown>
  )
}
