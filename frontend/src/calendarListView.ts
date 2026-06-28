import type { EventContentArg } from '@fullcalendar/core'

/** Shared list-year view config (main ribbon + matter events). */
export const CALENDAR_LIST_YEAR_VIEW = {
  type: 'list' as const,
  duration: { years: 1 },
  buttonText: 'list',
  listDaySideFormat: false as const,
  listDayFormat: {
    weekday: 'long' as const,
    month: 'long' as const,
    day: 'numeric' as const,
    year: 'numeric' as const,
  },
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** List rows: title only in the title column (time stays in the time column). */
export function calendarListEventContent(arg: EventContentArg): boolean | { html: string } {
  if (!arg.view.type.startsWith('list')) return true
  const title = arg.event.title || '(no title)'
  return { html: `<span class="canary-list-event-title">${escapeHtml(title)}</span>` }
}

/** List empty state: show loading text while the event feed is fetching. */
export function calendarNoEventsContent(isLoading: boolean): (renderProps: { text: string }) => string {
  return (renderProps) => (isLoading ? 'Loading…' : renderProps.text)
}
