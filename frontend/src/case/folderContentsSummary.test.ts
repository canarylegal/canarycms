import { describe, expect, it } from 'vitest'
import type { FileSummary } from '../types'
import { folderContentsSummary } from './DocCells'

function file(partial: Partial<FileSummary> & Pick<FileSummary, 'original_filename'>): FileSummary {
  return {
    id: 'f1',
    mime_type: 'text/plain',
    size_bytes: 1,
    created_at: '2024-01-01T00:00:00Z',
    ...partial,
  }
}

describe('folderContentsSummary', () => {
  it('counts root items and subfolders', () => {
    const files = [
      file({ original_filename: 'a.txt', folder_path: 'Shared' }),
      file({ original_filename: 'b.txt', folder_path: 'Shared' }),
      file({ original_filename: 'c.txt', folder_path: 'Shared/Inbox' }),
      file({ original_filename: 'd.txt', folder_path: 'Shared/Sent' }),
      file({ original_filename: 'sys', folder_path: 'Shared', category: 'system' }),
      file({ original_filename: 'att.bin', folder_path: 'Shared', parent_file_id: 'parent' }),
    ]
    expect(folderContentsSummary(files, 'Shared')).toBe('2 items, 2 subfolders')
  })

  it('uses singular labels', () => {
    const files = [file({ original_filename: 'only.txt', folder_path: 'Solo' })]
    expect(folderContentsSummary(files, 'Solo')).toBe('1 item, 0 subfolders')
  })
})
