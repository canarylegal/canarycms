import type { CasePortalFolderAccessGrantOut } from '../types'

/** Match backend ``file_folder_in_grant`` / ``sanitize_folder_path`` (posix, no ``..``). */
export function normalizeFolderPathForPortal(folderPath: string): string {
  const parts: string[] = []
  for (const part of (folderPath || '').split('/')) {
    const t = part.trim()
    if (!t || t === '.' || t === '..') continue
    parts.push(t)
  }
  return parts.join('/')
}

/** True when folder ``target`` is the grant root or a descendant (portal-visible). */
export function folderMatchesPortalGrant(targetFolder: string, grantFolder: string): boolean {
  const target = normalizeFolderPathForPortal(targetFolder)
  const grant = normalizeFolderPathForPortal(grantFolder)
  if (target === grant) return true
  if (grant && target.startsWith(`${grant}/`)) return true
  return false
}

export function portalContactsForFolder(
  folderPath: string,
  grants: CasePortalFolderAccessGrantOut[],
): CasePortalFolderAccessGrantOut[] {
  const seen = new Set<string>()
  const out: CasePortalFolderAccessGrantOut[] = []
  for (const g of grants) {
    if (!folderMatchesPortalGrant(folderPath, g.folder_path)) continue
    if (seen.has(g.contact_id)) continue
    seen.add(g.contact_id)
    out.push(g)
  }
  out.sort((a, b) => a.contact_name.localeCompare(b.contact_name))
  return out
}

export function isPortalSharedFolder(folderPath: string, grants: CasePortalFolderAccessGrantOut[]): boolean {
  return portalContactsForFolder(folderPath, grants).length > 0
}

const PORTAL_SHARED_WARN = 'This folder is externally shared, are you sure?'

export function portalSharedFolderConfirmMessage(
  contacts: CasePortalFolderAccessGrantOut[],
  preamble?: string,
): string {
  const parts: string[] = []
  if (preamble?.trim()) parts.push(preamble.trim())
  parts.push(PORTAL_SHARED_WARN)
  if (contacts.length) {
    parts.push('')
    parts.push('Contacts with access:')
    for (const c of contacts) {
      parts.push(`• ${c.contact_name}`)
    }
  }
  return parts.join('\n')
}

export function portalSharedFolderMoveConfirmMessage(contacts: CasePortalFolderAccessGrantOut[]): string {
  return portalSharedFolderConfirmMessage(contacts)
}

export function portalSharedFolderUploadNotifyMessage(
  contacts: CasePortalFolderAccessGrantOut[],
  fileCount: number,
): string {
  const noun = fileCount === 1 ? '1 file' : `${fileCount} files`
  const parts = [
    `Notify portal contacts by e-mail that ${noun} ${fileCount === 1 ? 'was' : 'were'} added to this shared folder?`,
  ]
  if (contacts.length) {
    parts.push('')
    parts.push('Contacts with access:')
    for (const c of contacts) {
      parts.push(`• ${c.contact_name}`)
    }
  }
  parts.push('')
  parts.push('Choose Send to e-mail them, or Skip to upload without notifying.')
  return parts.join('\n')
}

export function portalSharedFolderDeleteConfirmMessage(
  folderLabel: string,
  contacts: CasePortalFolderAccessGrantOut[],
): string {
  const preamble = `Delete folder "${folderLabel}" (including its contents)?`
  if (!contacts.length) return preamble
  return portalSharedFolderConfirmMessage(contacts, preamble)
}
