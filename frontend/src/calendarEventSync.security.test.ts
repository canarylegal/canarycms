import { expect, it, vi } from 'vitest'
import { syncCaseEventToCalDav } from './calendarEventSync'
import { apiFetch } from './api'
import type { CaseEventOut } from './types'
vi.mock('./api', () => ({ apiFetch: vi.fn() }))
it('never updates, deletes or duplicates an unverified historical appointment', async () => {
  await syncCaseEventToCalDav('cookie', 'matter', {
    id: 'event', name: 'Matter event', track_in_calendar: true, event_date: '2026-11-23',
    calendar_event_uid: null, calendar_link_needs_review: true,
  } as CaseEventOut, { caseLabel: 'Matter' })
  expect(apiFetch).not.toHaveBeenCalled()
})
