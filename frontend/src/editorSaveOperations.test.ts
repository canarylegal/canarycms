import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { documentRequest, DocumentRequestError } from './case/documentRequests'
import { pollOnlyofficeSaveConfirmed } from './editorSaveOperations'
vi.mock('./case/documentRequests', async (original) => ({ ...await original<typeof import('./case/documentRequests')>(), documentRequest: vi.fn() }))
beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())
it('waits for a newer persisted version after a transient status failure', async () => {
  vi.mocked(documentRequest).mockRejectedValueOnce(new DocumentRequestError('unavailable', 503, true)).mockResolvedValueOnce({ saved: true, version: 4 }).mockResolvedValueOnce({ saved: true, version: 5 })
  const result = pollOnlyofficeSaveConfirmed('/save-status', 4, '', 1000)
  await vi.advanceTimersByTimeAsync(600)
  await expect(result).resolves.toBeUndefined()
  expect(documentRequest).toHaveBeenCalledTimes(3)
})
it('stops immediately on access denial', async () => {
  vi.mocked(documentRequest).mockRejectedValue(new DocumentRequestError('denied', 403, false))
  await expect(pollOnlyofficeSaveConfirmed('/save-status', 1, '', 1000)).rejects.toMatchObject({ status: 403 })
  expect(documentRequest).toHaveBeenCalledTimes(1)
})
it('reports an unconfirmed save within its deadline', async () => {
  vi.mocked(documentRequest).mockResolvedValue({ saved: false, version: 1 })
  const result = expect(pollOnlyofficeSaveConfirmed('/save-status', 1, '', 500)).rejects.toThrow('did not confirm')
  await vi.advanceTimersByTimeAsync(500)
  await result
  expect(documentRequest).toHaveBeenCalledTimes(2)
})
