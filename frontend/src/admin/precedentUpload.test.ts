import { beforeEach, expect, it, vi } from 'vitest'
import { apiFetch } from '../api'
import { createPrecedentUploader } from './precedentUpload'
vi.mock('../api', () => ({ apiFetch: vi.fn() }))
beforeEach(() => { vi.mocked(apiFetch).mockReset() })
const fields = { name: 'Synthetic', reference: 'REF', kind: 'document' }
const key = (index: number) => new Headers(vi.mocked(apiFetch).mock.calls[index][1]?.headers).get('Idempotency-Key')

it('retains identity after an uncertain response and clears it after confirmation', async () => {
  vi.mocked(apiFetch).mockRejectedValueOnce(new Error('lost response')).mockResolvedValue({ id: 'saved' })
  const upload = createPrecedentUploader(), file = new File(['synthetic'], 'sample.txt')
  await expect(upload('token', file, fields)).rejects.toThrow('lost response')
  await upload('token', file, fields)
  expect(key(0)).toBeTruthy()
  expect(key(1)).toBe(key(0))
  expect((vi.mocked(apiFetch).mock.calls[1][1]?.body as FormData).get('upload')).toBe(file)
  await upload('token', file, fields)
  expect(key(2)).not.toBe(key(1))
})

it('uses a new identity when the file or metadata changes', async () => {
  vi.mocked(apiFetch).mockRejectedValue(new Error('uncertain'))
  const upload = createPrecedentUploader(), file = new File(['original'], 'sample.txt')
  await upload('token', file, fields).catch(() => {})
  await upload('token', file, { ...fields, reference: 'CHANGED' }).catch(() => {})
  await upload('token', new File(['replacement'], 'sample.txt'), fields).catch(() => {})
  expect(new Set([key(0), key(1), key(2)]).size).toBe(3)
})
