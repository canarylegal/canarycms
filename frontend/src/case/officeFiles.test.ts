import { describe, expect, it } from 'vitest'
import type { FileSummary } from '../types'
import { isEmlLikeFileSummary, isEmlLikeUploadFile, isOfficeLikeFile } from './officeFiles'

function file(partial: Partial<FileSummary> & Pick<FileSummary, 'original_filename'>): FileSummary {
  return {
    id: 'f1',
    mime_type: 'application/octet-stream',
    size_bytes: 1,
    created_at: '2024-01-01T00:00:00Z',
    ...partial,
  }
}

describe('isEmlLikeUploadFile', () => {
  it('detects by extension and mime', () => {
    expect(isEmlLikeUploadFile(new File([], 'a.eml'))).toBe(true)
    expect(isEmlLikeUploadFile(new File([], 'a.MSG'))).toBe(true)
    expect(isEmlLikeUploadFile(new File([], 'a.bin', { type: 'message/rfc822' }))).toBe(true)
    expect(isEmlLikeUploadFile(new File([], 'a.pdf'))).toBe(false)
  })
})

describe('isEmlLikeFileSummary', () => {
  it('treats Outlook Graph-linked rows as e-mail', () => {
    expect(isEmlLikeFileSummary(file({ original_filename: 'x.bin', outlook_graph_message_id: 'mid' }))).toBe(true)
    expect(isEmlLikeFileSummary(file({ original_filename: 'x.bin', outlook_web_link: 'https://owa' }))).toBe(true)
  })

  it('detects .eml and rfc822 mime', () => {
    expect(isEmlLikeFileSummary(file({ original_filename: 'mail.eml' }))).toBe(true)
    expect(isEmlLikeFileSummary(file({ original_filename: 'x.bin', mime_type: 'message/rfc822' }))).toBe(true)
    expect(isEmlLikeFileSummary(file({ original_filename: 'letter.docx' }))).toBe(false)
  })
})

describe('isOfficeLikeFile', () => {
  it('recognises common Office / ODF / RTF extensions', () => {
    for (const name of ['a.docx', 'b.xlsx', 'c.pptx', 'd.odt', 'e.rtf', 'f.DOC']) {
      expect(isOfficeLikeFile(file({ original_filename: name })), name).toBe(true)
    }
  })

  it('recognises Office mime types without extension', () => {
    expect(
      isOfficeLikeFile(
        file({
          original_filename: 'blob',
          mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }),
      ),
    ).toBe(true)
  })

  it('treats PDF as office-like by default (OnlyOffice)', () => {
    expect(isOfficeLikeFile(file({ original_filename: 'a.pdf', mime_type: 'application/pdf' }))).toBe(true)
  })

  it('rejects plain images and text', () => {
    expect(isOfficeLikeFile(file({ original_filename: 'a.png', mime_type: 'image/png' }))).toBe(false)
    expect(isOfficeLikeFile(file({ original_filename: 'a.txt', mime_type: 'text/plain' }))).toBe(false)
  })
})
