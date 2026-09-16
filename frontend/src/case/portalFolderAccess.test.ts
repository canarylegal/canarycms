import { describe, expect, it } from 'vitest'
import type { CasePortalFolderAccessGrantOut } from '../types'
import {
  folderMatchesPortalGrant,
  isPortalSharedFolder,
  normalizeFolderPathForPortal,
  portalContactsForFolder,
  portalSharedFolderConfirmMessage,
  portalSharedFolderDeleteConfirmMessage,
  portalSharedFolderUploadNotifyMessage,
} from './portalFolderAccess'

function grant(
  partial: Pick<CasePortalFolderAccessGrantOut, 'contact_id' | 'contact_name' | 'folder_path'>,
): CasePortalFolderAccessGrantOut {
  return partial
}

describe('normalizeFolderPathForPortal', () => {
  it('strips dots and empty segments', () => {
    expect(normalizeFolderPathForPortal('/a/../b/./c/')).toBe('a/b/c')
    expect(normalizeFolderPathForPortal('')).toBe('')
  })
})

describe('folderMatchesPortalGrant', () => {
  it('matches exact and descendant folders', () => {
    expect(folderMatchesPortalGrant('Shared', 'Shared')).toBe(true)
    expect(folderMatchesPortalGrant('Shared/Inbox', 'Shared')).toBe(true)
    expect(folderMatchesPortalGrant('Other', 'Shared')).toBe(false)
    expect(folderMatchesPortalGrant('SharedX', 'Shared')).toBe(false)
  })
})

describe('portalContactsForFolder', () => {
  it('dedupes contacts and sorts by name', () => {
    const grants = [
      grant({ contact_id: '2', contact_name: 'Zoe', folder_path: 'Shared' }),
      grant({ contact_id: '1', contact_name: 'Ada', folder_path: 'Shared' }),
      grant({ contact_id: '1', contact_name: 'Ada', folder_path: 'Shared/Inbox' }),
      grant({ contact_id: '3', contact_name: 'Bob', folder_path: 'Other' }),
    ]
    const out = portalContactsForFolder('Shared/Inbox', grants)
    expect(out.map((g) => g.contact_name)).toEqual(['Ada', 'Zoe'])
    expect(isPortalSharedFolder('Shared/Inbox', grants)).toBe(true)
    expect(isPortalSharedFolder('Private', grants)).toBe(false)
  })
})

describe('shared folder messages', () => {
  const contacts = [grant({ contact_id: '1', contact_name: 'Ada', folder_path: 'Shared' })]

  it('lists contacts on confirm', () => {
    const msg = portalSharedFolderConfirmMessage(contacts, 'Heads up')
    expect(msg).toContain('Heads up')
    expect(msg).toContain('externally shared')
    expect(msg).toContain('• Ada')
  })

  it('builds upload notify and delete copy', () => {
    expect(portalSharedFolderUploadNotifyMessage(contacts, 1)).toContain('1 file was added')
    expect(portalSharedFolderUploadNotifyMessage(contacts, 3)).toContain('3 files were added')
    expect(portalSharedFolderDeleteConfirmMessage('Shared', [])).toBe(
      'Delete folder "Shared" (including its contents)?',
    )
    expect(portalSharedFolderDeleteConfirmMessage('Shared', contacts)).toContain('externally shared')
  })
})
