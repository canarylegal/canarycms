import type { FeeEarnerPayload } from './types'
import type { ReportRunControls } from './reportRunner'

export type FilterChrome = {
  openFilterId: string | null
  setOpenFilterId: (v: string | null) => void
}

export type ReportSectionShared = ReportRunControls & {
  feeEarnerPayload: FeeEarnerPayload
}
