import { useMemo } from 'react'
import type { FileSummary } from '../types'
import { fileDocOwnerLabel } from './caseDetailHelpers'
import { docListPrimaryDate } from './docFormat'
import { splitFolderPath } from './folderPathCodec'

export function useCaseDocsFolderData({
  files,
  docSearch,
  docFolder,
  docSortKey,
  docSortDir,
}: {
  files: FileSummary[]
  docSearch: string
  docFolder: string
  docSortKey: 'description' | 'size' | 'created' | 'user'
  docSortDir: 'asc' | 'desc'
}) {
  const filteredFiles = useMemo(() => {
    const s = docSearch.trim().toLowerCase()
    if (!s) return files
    const matches = (f: FileSummary) => {
      if ((f.original_filename || '').toLowerCase().includes(s)) return true
      if ((f.source_mail_from_name || '').toLowerCase().includes(s)) return true
      if ((f.source_mail_from_email || '').toLowerCase().includes(s)) return true
      return false
    }
    const expanded = new Set<string>(files.filter(matches).map((f) => f.id))
    let changed = true
    while (changed) {
      changed = false
      for (const f of files) {
        if (expanded.has(f.id)) continue
        if (f.parent_file_id && expanded.has(f.parent_file_id)) {
          expanded.add(f.id)
          changed = true
        }
      }
      for (const f of files) {
        if (!expanded.has(f.id)) continue
        if (f.parent_file_id && !expanded.has(f.parent_file_id)) {
          expanded.add(f.parent_file_id)
          changed = true
        }
      }
    }
    return files.filter((f) => expanded.has(f.id))
  }, [files, docSearch])

  const filesInFolder = useMemo(() => {
    return filteredFiles.filter((f) => (f.folder_path ?? '') === docFolder && f.category !== 'system')
  }, [filteredFiles, docFolder])

  // Group artifacts (e.g. imported emails with attachments) under a parent `.eml` row.
  // Attachments are represented as child files with `parent_file_id` set.
  const topLevelInFolder = useMemo(() => {
    return filesInFolder.filter((f) => !f.parent_file_id)
  }, [filesInFolder])

  const childrenByParentId = useMemo(() => {
    const map = new Map<string, FileSummary[]>()
    for (const f of filesInFolder) {
      if (!f.parent_file_id) continue
      const pid = f.parent_file_id
      const arr = map.get(pid) ?? []
      arr.push(f)
      map.set(pid, arr)
    }
    return map
  }, [filesInFolder])

  const childFolders = useMemo(() => {
    const set = new Set<string>()
    const basePrefix = docFolder ? `${docFolder}/` : ''
    // Use full file list (not search-filtered) so empty folders with only a system marker stay visible.
    for (const f of files) {
      const fp = (f.folder_path ?? '').trim()
      if (!fp) continue
      if (fp === docFolder) continue
      if (docFolder && !fp.startsWith(basePrefix)) continue
      const rest = docFolder ? fp.slice(basePrefix.length) : fp
      const [first] = rest.split('/').filter(Boolean)
      if (first) set.add(first)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [files, docFolder])

  const allFolderPaths = useMemo(() => {
    const set = new Set<string>()
    for (const f of files) {
      const fp = (f.folder_path ?? '').trim()
      if (!fp) continue
      const parts = fp.split('/').filter(Boolean)
      let cur = ''
      for (const p of parts) {
        cur = cur ? `${cur}/${p}` : p
        set.add(cur)
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [files])

  const sortedChildFolders = useMemo(() => {
    const dir = docSortDir === 'asc' ? 1 : -1
    return [...childFolders].sort((a, b) => a.localeCompare(b) * dir)
  }, [childFolders, docSortDir])

  const sortedPinnedInFolder = useMemo(() => {
    const dir = docSortDir === 'asc' ? 1 : -1
    const compare = (a: FileSummary, b: FileSummary) => {
      const av =
        docSortKey === 'description'
          ? a.original_filename
          : docSortKey === 'size'
            ? a.size_bytes
            : docSortKey === 'created'
              ? docListPrimaryDate(a)
              : fileDocOwnerLabel(a)
      const bv =
        docSortKey === 'description'
          ? b.original_filename
          : docSortKey === 'size'
            ? b.size_bytes
            : docSortKey === 'created'
              ? docListPrimaryDate(b)
              : fileDocOwnerLabel(b)
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    }

    const pinnedParents = topLevelInFolder.filter((f) => f.is_pinned)
    const sortedParents = [...pinnedParents].sort(compare)

    const out: FileSummary[] = []
    for (const p of sortedParents) {
      out.push(p)
      const kids = childrenByParentId.get(p.id) ?? []
      out.push(...kids.sort(compare))
    }
    return out
  }, [topLevelInFolder, childrenByParentId, docSortDir, docSortKey])

  const sortedRegularInFolder = useMemo(() => {
    const dir = docSortDir === 'asc' ? 1 : -1
    const compare = (a: FileSummary, b: FileSummary) => {
      const av =
        docSortKey === 'description'
          ? a.original_filename
          : docSortKey === 'size'
            ? a.size_bytes
            : docSortKey === 'created'
              ? docListPrimaryDate(a)
              : fileDocOwnerLabel(a)
      const bv =
        docSortKey === 'description'
          ? b.original_filename
          : docSortKey === 'size'
            ? b.size_bytes
            : docSortKey === 'created'
              ? docListPrimaryDate(b)
              : fileDocOwnerLabel(b)
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    }

    const regularParents = topLevelInFolder.filter((f) => !f.is_pinned)
    const sortedParents = [...regularParents].sort(compare)

    const out: FileSummary[] = []
    for (const p of sortedParents) {
      out.push(p)
      const kids = childrenByParentId.get(p.id) ?? []
      out.push(...kids.sort(compare))
    }
    return out
  }, [topLevelInFolder, childrenByParentId, docSortDir, docSortKey])

  const breadcrumbParts = useMemo(() => {
    if (!docFolder) return []
    return splitFolderPath(docFolder)
  }, [docFolder])

  // Flat ordered key list for shift-range selection.
  // Files use their ID; folders use "folder:<path>".
  const allDocKeys = useMemo(
    () => [
      ...sortedPinnedInFolder.map((f) => f.id),
      ...sortedChildFolders.map((name) => `folder:${docFolder ? `${docFolder}/${name}` : name}`),
      ...sortedRegularInFolder.map((f) => f.id),
    ],
    [sortedPinnedInFolder, sortedChildFolders, sortedRegularInFolder, docFolder],
  )

  return {
    childFolders,
    allFolderPaths,
    sortedChildFolders,
    sortedPinnedInFolder,
    sortedRegularInFolder,
    breadcrumbParts,
    allDocKeys,
  }
}
