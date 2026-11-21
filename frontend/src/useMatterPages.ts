import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import type { CaseOut } from './types'

export type MatterPage = { items: CaseOut[]; next_cursor: string | null }

/** A query generation owns its requests; stale responses can never append to a new list. */
export function useMatterPages(token: string, query: string, revision: number, enabled: boolean) {
  const [rows, setRows] = useState<CaseOut[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const generation = useRef(0)
  const cursorOwner = useRef<{ query: string; token: string; revision: number; retry: number } | null>(null)
  const pending = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const fetchPage = useCallback(async (next: string | null, version: number) => {
    if (pending.current) return
    pending.current = true
    const abort = new AbortController()
    controller.current = abort
    setBusy(true)
    setError(null)
    try {
      const data = await apiFetch<MatterPage>(`/cases/menu?${query}${next ? `&cursor=${encodeURIComponent(next)}` : ''}`, { token, signal: abort.signal })
      if (generation.current !== version || abort.signal.aborted) return
      setRows(previous => {
        if (!next) return data.items
        const ids = new Set(previous.map(row => row.id))
        return [...previous, ...data.items.filter(row => !ids.has(row.id))]
      })
      cursorOwner.current = { query, token, revision, retry }
      setCursor(data.next_cursor)
    } catch (error) {
      if (generation.current === version && !abort.signal.aborted) {
        setError((error as { message?: string }).message ?? 'Failed to load matters. Use Refresh to retry.')
      }
    } finally {
      if (generation.current === version) {
        pending.current = false
        setBusy(false)
      }
    }
  }, [query, token, revision, retry])

  useEffect(() => {
    const version = ++generation.current
    controller.current?.abort()
    pending.current = false
    setRows([])
    cursorOwner.current = null
    setCursor(null)
    setError(null)
    setBusy(enabled)
    if (!enabled) return
    // Debounce changing searches/filters without ever showing rows from the previous query.
    const timer = window.setTimeout(() => void fetchPage(null, version), 200)
    return () => { window.clearTimeout(timer); controller.current?.abort(); generation.current = version + 1 }
  }, [fetchPage, revision, enabled, retry])

  const loadMore = useCallback(() => {
    // Observers can run after render but before the passive reset effect. Never
    // combine a new query/session with a cursor issued for the previous one.
    const owner = cursorOwner.current
    if (enabled && cursor && !pending.current && !error && owner?.query === query &&
        owner.token === token && owner.revision === revision && owner.retry === retry) {
      void fetchPage(cursor, generation.current)
    }
  }, [cursor, error, fetchPage, enabled, query, token, revision, retry])
  const refresh = useCallback(() => setRetry(value => value + 1), [])
  return { rows, busy, error, hasMore: cursor !== null, loadMore, refresh }
}
