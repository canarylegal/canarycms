import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import type { FileSummary } from '../types'

export type DocumentRow = FileSummary & {group_pinned: boolean}
export type DocumentPage = { items: DocumentRow[]; next_cursor: string | null }

type FolderMetadata = {paths: string[]; summaries: Record<string, string>}
const EMPTY_FOLDERS: FolderMetadata = {paths: [], summaries: {}}

/** A query generation owns its requests; stale responses can never append to a new list. */
export function useDocumentPages(token: string, caseId: string | null, query: string, revision: number) {
  const folderScope = `${token}:${caseId}`
  const [folderState, setFolderState] = useState<{scope: string; data: FolderMetadata; error: string | null}>({scope: '', data: EMPTY_FOLDERS, error: null})
  useEffect(() => {
    if (!caseId) return
    const abort = new AbortController()
    apiFetch<FolderMetadata>(`/cases/${caseId}/files/folder-metadata`, {token, signal: abort.signal})
      .then(data => {if (!abort.signal.aborted) setFolderState({scope: folderScope, data, error: null})})
      .catch(() => {if (!abort.signal.aborted) setFolderState({scope: folderScope, data: EMPTY_FOLDERS, error: 'Failed to load folders. Use Refresh to retry.'})})
    return () => abort.abort()
  }, [caseId, token, revision, folderScope])
  const folders = folderState.scope === folderScope ? folderState.data : EMPTY_FOLDERS
  const folderError = folderState.scope === folderScope ? folderState.error : null
  const [rows, setRows] = useState<DocumentRow[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const generation = useRef(0)
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
      const data = await apiFetch<DocumentPage>(`/cases/${caseId}/files/browse?${query}${next ? `&cursor=${encodeURIComponent(next)}` : ''}`, { token, signal: abort.signal })
      if (generation.current !== version || abort.signal.aborted) return
      setRows(previous => {
        if (!next) return data.items
        const ids = new Set(previous.map(row => row.id))
        return [...previous, ...data.items.filter(row => !ids.has(row.id))]
      })
      setCursor(data.next_cursor)
    } catch (error) {
      if (generation.current === version && !abort.signal.aborted) {
        setError((error as { message?: string }).message ?? 'Failed to load documents. Use Refresh to retry.')
      }
    } finally {
      if (generation.current === version) {
        pending.current = false
        setBusy(false)
      }
    }
  }, [query, token, caseId])

  useEffect(() => {
    const version = ++generation.current
    controller.current?.abort()
    pending.current = false
    setRows([])
    setCursor(null)
    setError(null)
    setBusy(Boolean(caseId))
    if (!caseId) return
    // Debounce changing searches/filters without ever showing rows from the previous query.
    const timer = window.setTimeout(() => void fetchPage(null, version), 200)
    return () => { window.clearTimeout(timer); controller.current?.abort(); generation.current = version + 1 }
  }, [fetchPage, revision, caseId, retry])

  const loadMore = useCallback(() => {
    if (cursor && !pending.current && !error) void fetchPage(cursor, generation.current)
  }, [cursor, error, fetchPage])
  const refresh = useCallback(() => setRetry(value => value + 1), [])
  return { rows, folders, busy, error: error ?? folderError, hasMore: cursor !== null, loadMore, refresh }
}
