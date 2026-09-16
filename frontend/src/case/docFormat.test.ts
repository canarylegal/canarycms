import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CaseOut, FileSummary } from '../types'
import {
  dndEventHasFiles,
  docListPrimaryDate,
  formatDocFileSize,
  formatDocModified,
  matterTypeDisplayLine,
} from './docFormat'

function file(partial: Partial<FileSummary> & Pick<FileSummary, 'original_filename' | 'created_at'>): FileSummary {
  return {
    id: 'f1',
    mime_type: 'application/octet-stream',
    size_bytes: 1,
    ...partial,
  }
}

describe('formatDocFileSize', () => {
  it('uses KB under 1 MiB with a 1 KB floor', () => {
    expect(formatDocFileSize(0)).toBe('0 KB')
    expect(formatDocFileSize(1)).toBe('1 KB')
    expect(formatDocFileSize(1024)).toBe('1 KB')
    expect(formatDocFileSize(1536)).toBe('2 KB')
  })

  it('switches to MB and GB at 1024-based boundaries', () => {
    expect(formatDocFileSize(1024 * 1024)).toBe('1 MB')
    expect(formatDocFileSize(2.5 * 1024 * 1024)).toBe('2.5 MB')
    expect(formatDocFileSize(1024 * 1024 * 1024)).toBe('1 GB')
  })

  it('clamps negative sizes to zero', () => {
    expect(formatDocFileSize(-10)).toBe('0 KB')
  })
})

describe('formatDocModified', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-06-15T12:00:00'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns time for same-day timestamps and date otherwise', () => {
    const sameDay = formatDocModified('2024-06-15T09:30:00')
    expect(sameDay).toMatch(/\d/)
    expect(sameDay).not.toMatch(/2024/)

    const otherDay = formatDocModified('2024-01-02T09:30:00')
    expect(otherDay.length).toBeGreaterThan(0)
  })

  it('returns the raw string when invalid', () => {
    expect(formatDocModified('not-a-date')).toBe('not-a-date')
  })
})

describe('docListPrimaryDate', () => {
  it('prefers source_mail_date for root eml-like files', () => {
    const f = file({
      original_filename: 'mail.eml',
      created_at: '2024-01-01T00:00:00Z',
      source_mail_date: '2023-12-25T10:00:00Z',
    })
    expect(docListPrimaryDate(f)).toBe('2023-12-25T10:00:00Z')
  })

  it('uses created_at for attachments and non-mail', () => {
    expect(
      docListPrimaryDate(
        file({
          original_filename: 'mail.eml',
          created_at: '2024-01-01T00:00:00Z',
          source_mail_date: '2023-12-25T10:00:00Z',
          parent_file_id: 'parent',
        }),
      ),
    ).toBe('2024-01-01T00:00:00Z')
    expect(
      docListPrimaryDate(
        file({
          original_filename: 'note.txt',
          created_at: '2024-01-01T00:00:00Z',
          source_mail_date: '2023-12-25T10:00:00Z',
        }),
      ),
    ).toBe('2024-01-01T00:00:00Z')
  })
})

describe('dndEventHasFiles', () => {
  it('detects Files in dataTransfer types', () => {
    expect(dndEventHasFiles({ dataTransfer: null })).toBe(false)
    expect(dndEventHasFiles({ dataTransfer: { types: [] } as unknown as DataTransfer })).toBe(false)
    expect(
      dndEventHasFiles({ dataTransfer: { types: ['text/plain', 'Files'] } as unknown as DataTransfer }),
    ).toBe(true)
  })
})

describe('matterTypeDisplayLine', () => {
  const base = {
    id: 'c1',
    case_number: '0001',
    matter_description: 'x',
    fee_earner_user_id: 'u1',
    status: 'open' as const,
    created_by: 'u1',
    is_locked: false,
    lock_mode: 'none' as const,
    created_at: '',
    updated_at: '',
  } satisfies CaseOut

  it('joins head and sub with an em dash', () => {
    expect(
      matterTypeDisplayLine({
        ...base,
        matter_head_type_name: 'Conveyancing',
        matter_sub_type_name: 'Purchase',
      }),
    ).toBe('Conveyancing — Purchase')
  })

  it('dedupes identical head/sub and ignores placeholder dashes', () => {
    expect(
      matterTypeDisplayLine({
        ...base,
        matter_head_type_name: 'Litigation',
        matter_sub_type_name: 'litigation',
      }),
    ).toBe('Litigation')
    expect(
      matterTypeDisplayLine({
        ...base,
        matter_head_type_name: '—',
        matter_sub_type_name: '-',
      }),
    ).toBe('—')
  })

  it('avoids duplicating an already-joined head label', () => {
    expect(
      matterTypeDisplayLine({
        ...base,
        matter_head_type_name: 'Conveyancing — Purchase',
        matter_sub_type_name: 'Purchase',
      }),
    ).toBe('Conveyancing — Purchase')
  })
})
