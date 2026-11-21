import { useEffect, useRef, useState } from 'react'
import type { FileSummary } from '../types'
import { isEmlLikeFileSummary } from './officeFiles'

type UseCaseDocsSelectionArgs = {
  hasMore?: boolean
  loading?: boolean
  onLoadMore?: () => void
  allDocKeys: string[]
  caseDocPanel: string
  docMenu: unknown
  commentOpen: boolean
  precedentPicker: unknown
  contactPickModal: unknown
  files: FileSummary[]
  setDocFolder: (path: string) => void
  previewEmlFile: (f: FileSummary) => void
  openCaseFile: (f: FileSummary) => void
}

export function useCaseDocsSelection({
  hasMore = false, loading = false, onLoadMore,
  allDocKeys,
  caseDocPanel,
  docMenu,
  commentOpen,
  precedentPicker,
  contactPickModal,
  files,
  setDocFolder,
  previewEmlFile,
  openCaseFile,
}: UseCaseDocsSelectionArgs) {
  const [selectedDocSet, setSelectedDocSet] = useState<Set<string>>(new Set())
  const [docFocusKey, setDocFocusKey] = useState<string | null>(null)
  const docAnchorRef = useRef<string | null>(null)

  useEffect(() => {
    if (loading) return
    if (docAnchorRef.current && !allDocKeys.includes(docAnchorRef.current)) docAnchorRef.current = null
    setDocFocusKey((prev) => {
      if (prev && allDocKeys.includes(prev)) return prev
      return allDocKeys[0] ?? null
    })
  }, [allDocKeys, loading])

  const awaitingNext = useRef<string | null>(null)
  useEffect(() => {
    const key = awaitingNext.current
    if (!key) return
    const index = allDocKeys.indexOf(key)
    if (index >= 0 && allDocKeys[index + 1]) {
      const next = allDocKeys[index + 1]
      awaitingNext.current = null
      setDocFocusKey(next)
      setSelectedDocSet(new Set([next]))
      docAnchorRef.current = next
    } else if (!loading) awaitingNext.current = null
  }, [allDocKeys, loading])

  useEffect(() => {
    if (!docFocusKey) return
    const row = Array.from(document.querySelectorAll<HTMLElement>('[data-doc-key]')).find(el => el.dataset.docKey === docFocusKey)
    row?.scrollIntoView?.({block: 'nearest'})
  }, [docFocusKey])

  function activateDocFocusKey(key: string) {
    if (key.startsWith('folder:')) {
      setDocFolder(key.slice('folder:'.length))
      return
    }
    const f = files.find((x) => x.id === key)
    if (!f) return
    if (isEmlLikeFileSummary(f)) void previewEmlFile(f)
    else void openCaseFile(f)
  }

  function handleDocsKeyDown(e: React.KeyboardEvent) {
    if (caseDocPanel !== 'documents' || (loading && files.length === 0)) return
    if (docMenu || commentOpen || precedentPicker || contactPickModal) return
    const target = e.target as HTMLElement
    if (target.closest('input, textarea, select, button')) return
    if (allDocKeys.length === 0) return

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const currentIdx = docFocusKey ? allDocKeys.indexOf(docFocusKey) : -1
      if (e.key === 'ArrowDown' && currentIdx === allDocKeys.length - 1 && hasMore) {
        awaitingNext.current = docFocusKey
        onLoadMore?.()
        return
      }
      const delta = e.key === 'ArrowDown' ? 1 : -1
      let nextIdx = currentIdx + delta
      if (nextIdx < 0) nextIdx = 0
      if (nextIdx >= allDocKeys.length) nextIdx = allDocKeys.length - 1
      const nextKey = allDocKeys[nextIdx]!
      setDocFocusKey(nextKey)
      setSelectedDocSet(new Set([nextKey]))
      docAnchorRef.current = nextKey
      return
    }

    if (e.key === 'Enter' && docFocusKey) {
      e.preventDefault()
      activateDocFocusKey(docFocusKey)
    }
  }

  function handleDocItemClick(key: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (e.shiftKey && docAnchorRef.current) {
      const anchorIdx = allDocKeys.indexOf(docAnchorRef.current)
      const currentIdx = allDocKeys.indexOf(key)
      if (anchorIdx !== -1 && currentIdx !== -1) {
        const [lo, hi] = anchorIdx <= currentIdx ? [anchorIdx, currentIdx] : [currentIdx, anchorIdx]
        const range = new Set(allDocKeys.slice(lo, hi + 1))
        setSelectedDocSet(e.ctrlKey || e.metaKey ? (prev) => new Set([...prev, ...range]) : range)
      }
    } else if (e.ctrlKey || e.metaKey) {
      setSelectedDocSet((prev) => {
        const next = new Set(prev)
        if (next.has(key)) {
          next.delete(key)
        } else {
          next.add(key)
        }
        return next
      })
      docAnchorRef.current = key
    } else {
      setSelectedDocSet(new Set([key]))
      docAnchorRef.current = key
      setDocFocusKey(key)
    }
  }

  return {
    selectedDocSet,
    setSelectedDocSet,
    docFocusKey,
    setDocFocusKey,
    handleDocsKeyDown,
    handleDocItemClick,
  }
}
