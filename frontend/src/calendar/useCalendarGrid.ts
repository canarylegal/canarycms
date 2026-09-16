import type { EventInput, EventMountArg } from '@fullcalendar/core'
import type FullCalendar from '@fullcalendar/react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import {
  calendarEventCacheKey,
  invalidateCalendarEventCache,
  readCalendarEventCache,
  writeCalendarEventCache,
} from '../calendarEventCache'
import {
  addOneCalendarDayYmd,
  eventInputToYmd,
  mapCalendarEventsToFullCalendar,
} from '../calendarEventMapping'
import { calendarNoEventsContent } from '../calendarListView'
import type { CalendarEventOut, UserCalendarListItem, UserPublic } from '../types'
import { useUserUiPreferences } from '../useUserUiPreferences'

export function useCalendarGrid({
  token,
  me,
}: {
  token: string
  me?: UserPublic | null
}) {
  const calRef = useRef<FullCalendar>(null)
  const calWrapRef = useRef<HTMLDivElement | null>(null)
  const calendarSelectionHydratedRef = useRef(false)
  const calendarsRef = useRef<UserCalendarListItem[]>([])
  const selectedCalIdsRef = useRef<string[]>([])
  const selectionKeyRef = useRef('')
  const prevSelectionKeyRef = useRef<string | null>(null)
  const fetchGenRef = useRef(0)
  const { prefs, setPreference } = useUserUiPreferences(me, token)
  const [calendarPixelHeight, setCalendarPixelHeight] = useState(480)
  const [needCaldav, setNeedCaldav] = useState(false)
  const [calendarsLoaded, setCalendarsLoaded] = useState(false)
  const [selectionReady, setSelectionReady] = useState(false)
  const [eventsLoading, setEventsLoading] = useState(true)
  const [caldavSyncing, setCaldavSyncing] = useState(false)
  const [banner, setBanner] = useState<string | null>(null)

  const [calendars, setCalendars] = useState<UserCalendarListItem[]>([])
  const [selectedCalIds, setSelectedCalIds] = useState<string[]>([])

  const refresh = useCallback(() => {
    invalidateCalendarEventCache()
    calRef.current?.getApi().refetchEvents()
  }, [])

  const loadCalendars = useCallback(async () => {
    try {
      const rows = await apiFetch<UserCalendarListItem[]>('/users/me/calendars', { token })
      setCalendars(rows)
    } catch (e: unknown) {
      const err = e as ApiError
      if (err.status === 403) setNeedCaldav(true)
    } finally {
      setCalendarsLoaded(true)
    }
  }, [token])

  useEffect(() => {
    if (needCaldav) return
    void loadCalendars()
  }, [needCaldav, loadCalendars])

  useEffect(() => {
    if (!calendarsLoaded) {
      setSelectionReady(false)
      return
    }
    if (calendars.length === 0) {
      setSelectionReady(true)
      return
    }
    const valid = new Set(calendars.map((c) => c.id))
    const saved = prefs.calendar_selected_calendar_ids.filter((id) => valid.has(id))
    if (prefs.calendar_selected_calendar_ids.length > 0 && saved.length > 0) {
      setSelectedCalIds(saved)
    } else {
      setSelectedCalIds(calendars.map((c) => c.id))
    }
    calendarSelectionHydratedRef.current = true
    setSelectionReady(true)
  }, [calendars, prefs.calendar_selected_calendar_ids, calendarsLoaded])

  useEffect(() => {
    const api = calRef.current?.getApi()
    if (api && api.view.type !== prefs.calendar_view) {
      api.changeView(prefs.calendar_view)
    }
  }, [prefs.calendar_view])

  useLayoutEffect(() => {
    const el = calWrapRef.current
    if (!el) return
    const apply = () => {
      const h = el.getBoundingClientRect().height
      if (h > 0) setCalendarPixelHeight(Math.floor(h))
    }
    apply()
    const ro = new ResizeObserver(() => apply())
    ro.observe(el)
    return () => ro.disconnect()
  }, [needCaldav])

  const selectionKey = selectedCalIds.join(',')
  calendarsRef.current = calendars
  selectedCalIdsRef.current = selectedCalIds
  selectionKeyRef.current = selectionKey

  useEffect(() => {
    if (!selectionReady || needCaldav) return
    if (prevSelectionKeyRef.current === null) {
      prevSelectionKeyRef.current = selectionKey
      return
    }
    if (prevSelectionKeyRef.current === selectionKey) return
    prevSelectionKeyRef.current = selectionKey
    calRef.current?.getApi().refetchEvents()
  }, [selectionReady, needCaldav, selectionKey])

  const transformEventFromApi = useCallback((event: EventInput): EventInput => {
    const ep = event.extendedProps as { api_all_day?: boolean } | undefined
    if (ep?.api_all_day !== true) return event
    const startY = eventInputToYmd(event.start)
    let endY = eventInputToYmd(event.end ?? event.start)
    if (!startY) return { ...event, allDay: true }
    if (!endY || endY <= startY) {
      endY = addOneCalendarDayYmd(startY)
    }
    return {
      ...event,
      allDay: true,
      start: startY,
      end: endY,
    }
  }, [])

  const onEventDidMount = useCallback((info: EventMountArg) => {
    const apiAll = info.event.extendedProps?.api_all_day === true
    const row = info.el.closest('tr.fc-list-event') as HTMLElement | null

    if (apiAll) {
      info.el.setAttribute('data-canary-allday', '1')
      info.el.querySelectorAll('.fc-event-time').forEach((node) => {
        ;(node as HTMLElement).style.setProperty('display', 'none', 'important')
      })
      if (row) {
        row.setAttribute('data-canary-allday', '1')
        row.querySelectorAll('td.fc-list-event-time').forEach((td) => {
          ;(td as HTMLElement).style.setProperty('display', 'none', 'important')
        })
      }
    }

    if (!row) return
    const bg = info.event.backgroundColor
    if (!bg) return
    const fg = info.event.textColor
    const chip = row.querySelector(
      'td.fc-list-event-title a, td.fc-list-event-title .canary-list-event-title',
    ) as HTMLElement | null
    if (chip) {
      chip.style.backgroundColor = bg
      if (fg) chip.style.color = fg
    }
  }, [])

  const noEventsContent = useMemo(() => calendarNoEventsContent(eventsLoading), [eventsLoading])

  const fetchEvents = useCallback(
    async (
      info: { startStr: string; endStr: string },
      successCallback: (events: EventInput[]) => void,
      failureCallback: (error: Error) => void,
    ) => {
      const gen = ++fetchGenRef.current
      setBanner(null)
      setNeedCaldav(false)

      const params = new URLSearchParams({ start: info.startStr, end: info.endStr })
      const cals = calendarsRef.current
      const sel = selectedCalIdsRef.current
      const selectionKey = selectionKeyRef.current
      if (cals.length > 0 && sel.length > 0 && sel.length < cals.length) {
        params.set('calendar_ids', sel.join(','))
      }

      const cacheKey = calendarEventCacheKey(info.startStr, info.endStr, selectionKey)
      const cached = readCalendarEventCache(cacheKey)
      let painted = false

      if (cached) {
        successCallback(mapCalendarEventsToFullCalendar(cached))
        painted = true
        setCaldavSyncing(true)
      }

      if (!cached) {
        try {
          const localParams = new URLSearchParams(params)
          localParams.set('include_caldav', 'false')
          const localRows = await apiFetch<CalendarEventOut[]>(`/users/me/calendar/events?${localParams}`, {
            token,
          })
          if (gen !== fetchGenRef.current) return
          if (localRows.length > 0) {
            successCallback(mapCalendarEventsToFullCalendar(localRows))
            painted = true
            setCaldavSyncing(true)
          }
        } catch {
          /* local-only feed is best-effort */
        }
      }

      try {
        const rows = await apiFetch<CalendarEventOut[]>(`/users/me/calendar/events?${params}`, { token })
        if (gen !== fetchGenRef.current) return
        writeCalendarEventCache(cacheKey, rows)
        successCallback(mapCalendarEventsToFullCalendar(rows))
        setCaldavSyncing(false)
      } catch (e: unknown) {
        if (gen !== fetchGenRef.current) return
        const err = e as ApiError
        if (err.status === 403) {
          setNeedCaldav(true)
          setCaldavSyncing(false)
          successCallback([])
          return
        }
        setCaldavSyncing(false)
        if (painted) {
          setBanner(err.message ?? 'Could not refresh personal calendar events from CalDAV')
          return
        }
        setBanner(err.message ?? 'Could not load events')
        failureCallback(err instanceof Error ? err : new Error(String(e)))
      }
    },
    [token],
  )

  function toggleCal(id: string) {
    setSelectedCalIds((prev) => {
      let next: string[]
      if (prev.includes(id)) {
        if (prev.length <= 1) return prev
        next = prev.filter((x) => x !== id)
      } else {
        next = [...prev, id]
      }
      if (calendarSelectionHydratedRef.current) {
        setPreference('calendar_selected_calendar_ids', next)
      }
      return next
    })
  }

  return {
    calRef,
    calWrapRef,
    prefs,
    setPreference,
    calendarPixelHeight,
    needCaldav,
    calendarsLoaded,
    selectionReady,
    setEventsLoading,
    caldavSyncing,
    banner,
    setBanner,
    calendars,
    selectedCalIds,
    refresh,
    loadCalendars,
    transformEventFromApi,
    onEventDidMount,
    noEventsContent,
    fetchEvents,
    toggleCal,
  }
}
