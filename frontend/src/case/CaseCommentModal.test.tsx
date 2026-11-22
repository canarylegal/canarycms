import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from '../api'
import { CaseCommentModal } from './CaseCommentModal'
vi.mock('../api', () => ({ apiFetch: vi.fn(), apiUrl: (path: string) => path }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('retains a stale draft, shows the latest text and retries against its version', async () => {
  const saved = vi.fn()
  const close = vi.fn()
  function Editor() {
    const [text, setText] = useState('my unsaved draft')
    const [version, setVersion] = useState<number | null>(1)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    return <CaseCommentModal caseId="case" token="token" docFolder="" commentEditFileId="file"
      commentVersion={version} setCommentVersion={setVersion} commentText={text} setCommentText={setText}
      commentBusy={busy} setCommentBusy={setBusy} commentErr={error} setCommentErr={setError}
      onSaved={saved} onClose={close} />
  }
  const fetch = vi.mocked(apiFetch)
  fetch.mockRejectedValueOnce({ status: 409, message: 'changed' })
  render(<Editor />)
  fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Your comment draft')).toHaveValue('my unsaved draft')
  expect(screen.getByRole('button', { name: 'Save comment' })).toBeDisabled()
  expect(saved).not.toHaveBeenCalled(); expect(close).not.toHaveBeenCalled()
  fetch.mockResolvedValueOnce({ text: 'colleague edit', version: 2 })
  fireEvent.click(screen.getByRole('button', { name: 'Load latest comment' }))
  await screen.findByLabelText('Latest saved comment')
  expect(screen.getByLabelText('Latest saved comment')).toHaveValue('colleague edit')
  expect(screen.getByLabelText('Your comment draft')).toHaveValue('my unsaved draft')
  fireEvent.change(screen.getByLabelText('Your comment draft'), { target: { value: 'colleague edit and my draft' } })
  fetch.mockRejectedValueOnce({status:409})
  fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
  await screen.findByRole('alert')
  expect(fetch).toHaveBeenLastCalledWith('/cases/case/files/file/comment', expect.objectContaining({json:{text:'colleague edit and my draft', expected_version:2}}))
  expect(screen.getByRole('button', { name: 'Save comment' })).toBeDisabled()
  fetch.mockResolvedValueOnce({text:'newer colleague edit',version:3})
  fireEvent.click(screen.getByRole('button', { name: 'Load latest comment' }))
  await screen.findByLabelText('Latest saved comment')
  fetch.mockResolvedValueOnce({id:'file'})
  fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenLastCalledWith('/cases/case/files/file/comment', expect.objectContaining({json:{text:'colleague edit and my draft',expected_version:3}}))
})
