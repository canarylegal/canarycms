import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { UploadScanningPanel } from './UploadScanningPanel'
import { apiFetch } from './api'
vi.mock('./api', () => ({ apiFetch: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('reports disabled worker and retries quarantined files without offering release', async () => {
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path.endsWith('/quarantine')) return [{ id: 'file', filename: 'synthetic.pdf', state: 'error', reason: 'scan_incomplete' }] as never
    return { mode: 'required', worker_enabled: false, scanner: 'unavailable_or_stale', version: null, counts: { error: 1 } } as never
  })
  render(<UploadScanningPanel token="synthetic" />)
  expect(await screen.findByText(/worker is disabled/)).toBeTruthy()
  expect(screen.getByText(/Unavailable or signatures out of date/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Retry scan' }))
  await waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/admin/storage/upload-scanning/file/retry', { token: 'synthetic', method: 'POST' }))
  expect(screen.queryByRole('button', { name: /release|bypass/i })).toBeNull()
})
it('does not offer retries when scanning is disabled', async () => {
  vi.mocked(apiFetch).mockImplementation(async (path) => path.endsWith('/quarantine')
    ? [{ id: 'file', filename: 'synthetic.pdf', state: 'blocked', reason: null }] as never
    : { mode: 'disabled', worker_enabled: false, scanner: 'disabled', version: null, counts: { blocked: 1 } } as never)
  render(<UploadScanningPanel token="synthetic" />)
  await screen.findByText(/Upload scanning: Disabled/)
  expect(screen.queryByRole('button', { name: 'Retry scan' })).toBeNull()
})
