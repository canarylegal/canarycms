import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import { BusyIcon } from './BusyIcon'
import { CASE_FILES_STORAGE_KEY, signalCaseFilesChanged } from './caseFilesCrossTab'
import { CaseDetail, type CaseOpenDocPanel } from './case/CaseDetail'
import type { PendingCaseCompose } from './quoteEmailPrecedent'
import type {
  CaseContactOut,
  CaseNoteOut,
  CaseOut,
  CaseTaskOut,
  FileSummary,
  UserPublic,
} from './types'

type Props = {
  token: string
  caseId: string
  currentUser: UserPublic | null
  openDocPanel: CaseOpenDocPanel | null
  onOpenDocPanelConsumed: () => void
  pendingComposeKind: PendingCaseCompose | null
  onPendingComposeConsumed: () => void
  onCaseListInvalidate: () => void
  onTaskMenuInvalidate: () => void
  onCaseDetailChange: (detail: CaseOut | null) => void
}

/** Loads and renders an open matter — isolated from App so other menus do not pay case state costs. */
export function CaseViewRoute({
  token,
  caseId,
  currentUser,
  openDocPanel,
  onOpenDocPanelConsumed,
  pendingComposeKind,
  onPendingComposeConsumed,
  onCaseListInvalidate,
  onTaskMenuInvalidate,
  onCaseDetailChange,
}: Props) {
  const [caseDetail, setCaseDetail] = useState<CaseOut | null>(null)
  const [notes, setNotes] = useState<CaseNoteOut[]>([])
  const [tasks, setTasks] = useState<CaseTaskOut[]>([])
  const [files, setFiles] = useState<FileSummary[]>([])
  const [caseContacts, setCaseContacts] = useState<CaseContactOut[]>([])
  const [detailErr, setDetailErr] = useState<string | null>(null)
  const [opening, setOpening] = useState(true)
  const caseIdRef = useRef(caseId)
  caseIdRef.current = caseId

  const refreshCaseFiles = useCallback(
    async (id: string) => {
      try {
        const f = await apiFetch<FileSummary[]>(`/cases/${id}/files`, { token })
        if (String(id) !== String(caseIdRef.current)) return
        setFiles(Array.isArray(f) ? f : [])
      } catch {
        /* keep existing file list */
      }
    },
    [token],
  )

  const refreshCaseDetail = useCallback(
    async (id: string) => {
      setDetailErr(null)
      try {
        const [c, n, t, f, cc] = await Promise.all([
          apiFetch<CaseOut>(`/cases/${id}`, { token }),
          apiFetch<CaseNoteOut[]>(`/cases/${id}/notes`, { token }),
          apiFetch<CaseTaskOut[]>(`/cases/${id}/tasks`, { token }),
          apiFetch<FileSummary[]>(`/cases/${id}/files`, { token }),
          apiFetch<CaseContactOut[]>(`/cases/${id}/contacts`, { token }),
        ])
        if (String(id) !== String(caseIdRef.current)) return
        setCaseDetail(c)
        onCaseDetailChange(c)
        setNotes(Array.isArray(n) ? n : [])
        setTasks(Array.isArray(t) ? t : [])
        setFiles(Array.isArray(f) ? f : [])
        setCaseContacts(Array.isArray(cc) ? cc : [])
      } catch (e: unknown) {
        if (String(id) !== String(caseIdRef.current)) return
        setCaseDetail(null)
        onCaseDetailChange(null)
        setDetailErr((e as { message?: string }).message ?? 'Failed to load case')
      }
    },
    [onCaseDetailChange, token],
  )

  useEffect(() => {
    let cancelled = false
    setOpening(true)
    setCaseDetail(null)
    onCaseDetailChange(null)
    setDetailErr(null)
    void (async () => {
      await refreshCaseDetail(caseId)
      if (!cancelled) setOpening(false)
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, onCaseDetailChange, refreshCaseDetail])

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.origin !== window.location.origin) return
      const d = e.data as { type?: string; caseId?: string } | null
      if (d?.type === 'canary-files-changed' && d.caseId === caseId) {
        void refreshCaseFiles(caseId)
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [caseId, refreshCaseFiles])

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key !== CASE_FILES_STORAGE_KEY || !e.newValue) return
      let parsed: { caseId?: string } = {}
      try {
        parsed = JSON.parse(e.newValue) as { caseId?: string }
      } catch {
        return
      }
      if (parsed.caseId === caseId) void refreshCaseFiles(caseId)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [caseId, refreshCaseFiles])

  const refreshCaseDetailWithCrossTabSignal = useCallback(() => {
    void refreshCaseDetail(caseId)
    signalCaseFilesChanged(caseId)
  }, [caseId, refreshCaseDetail])

  if (opening) {
    return (
      <div className="caseViewBusy">
        <BusyIcon label="Opening case" />
      </div>
    )
  }

  return (
    <CaseDetail
      token={token}
      caseDetail={caseDetail}
      notes={notes}
      tasks={tasks}
      files={files}
      caseContacts={caseContacts}
      error={detailErr}
      selectedCaseId={caseId}
      currentUser={currentUser}
      openDocPanel={openDocPanel}
      onOpenDocPanelConsumed={onOpenDocPanelConsumed}
      pendingComposeKind={pendingComposeKind}
      onPendingComposeConsumed={onPendingComposeConsumed}
      onRefresh={refreshCaseDetailWithCrossTabSignal}
      onCaseListInvalidate={onCaseListInvalidate}
      onTaskMenuInvalidate={onTaskMenuInvalidate}
    />
  )
}
