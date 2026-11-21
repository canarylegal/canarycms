import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCaseDocumentTransfers } from './useCaseDocumentTransfers'
import { uploadFilesToCaseFolder } from './documentTransferOps'
import { notifyPortalFilesAdded } from './caseDocFileOps'
import { DocumentRequestError } from './documentRequests'
vi.mock('./documentTransferOps', () => ({ uploadFilesToCaseFolder: vi.fn(), downloadCaseExportZipBlob: vi.fn(), downloadCaseFilesSequential: vi.fn(), downloadCaseFolderZipBlob: vi.fn() }))
vi.mock('./caseDocFileOps', () => ({ notifyPortalFilesAdded: vi.fn() }))
vi.mock('./portalFolderAccess', () => ({ isPortalSharedFolder: () => true, portalContactsForFolder: () => [], portalSharedFolderUploadNotifyMessage: () => 'Notify?' }))
function args(): Parameters<typeof useCaseDocumentTransfers>[0] {
  return { caseId: 'case', caseDetail: null, token: '', docFolder: 'folder', portalEnabled: false, portalFolderGrants: [], askConfirm: vi.fn().mockResolvedValue(false), pushNotification: vi.fn(), onRefresh: vi.fn(), setBusy: vi.fn(), setActionErr: vi.fn(), setDocMenu: vi.fn() }
}
beforeEach(() => vi.resetAllMocks())
describe('document transfer state', () => {
  it('ignores a repeated upload while the first is in flight', async () => {
    let finish!: () => void
    vi.mocked(uploadFilesToCaseFolder).mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
    const options = args()
    const { result } = renderHook(() => useCaseDocumentTransfers(options))
    const files = [new File(['x'], 'one.txt')]
    let pending!: Promise<void>
    await act(async () => { pending = result.current.uploadFilesToCurrentFolder(files); await result.current.uploadFilesToCurrentFolder(files) })
    expect(uploadFilesToCaseFolder).toHaveBeenCalledTimes(1)
    await act(async () => { finish(); await pending })
    expect(options.setBusy).toHaveBeenLastCalledWith(false)
  })
  it('refreshes successful uploads even if portal notification fails, without reuploading', async () => {
    vi.mocked(uploadFilesToCaseFolder).mockImplementation(async (_id, _token, _folder, files, progress) => { progress!.uploaded = files.map(f => f.name) })
    vi.mocked(notifyPortalFilesAdded).mockRejectedValue(new Error('notification failed'))
    const options = args(); options.portalEnabled = true; vi.mocked(options.askConfirm).mockResolvedValue(true)
    const { result } = renderHook(() => useCaseDocumentTransfers(options))
    await act(async () => { await result.current.uploadFilesToCurrentFolder([new File(['x'], 'one.txt')]) })
    expect(uploadFilesToCaseFolder).toHaveBeenCalledTimes(1)
    expect(options.onRefresh).toHaveBeenCalledOnce()
    expect(options.setActionErr).toHaveBeenLastCalledWith(expect.stringContaining('files were uploaded'))
  })
  it('does not resume a failed upload in a different folder', async () => {
    vi.mocked(uploadFilesToCaseFolder).mockRejectedValue(new DocumentRequestError('busy', 429, true))
    let choose!: (value: boolean) => void
    const options = args(); vi.mocked(options.askConfirm).mockImplementation(() => new Promise(resolve => { choose = resolve }))
    const { result, rerender } = renderHook((props) => useCaseDocumentTransfers(props), { initialProps: options })
    let pending!: Promise<void>
    await act(async () => { pending = result.current.uploadFilesToCurrentFolder([new File(['x'], 'one.txt')]); await Promise.resolve() })
    rerender({ ...options, docFolder: 'another-folder' })
    await act(async () => { choose(true); await pending })
    expect(uploadFilesToCaseFolder).toHaveBeenCalledTimes(1)
    expect(options.onRefresh).not.toHaveBeenCalled()
  })
  it('does not trigger a reloading refresh when the upload session expires', async () => {
    vi.mocked(uploadFilesToCaseFolder).mockRejectedValue(new DocumentRequestError('Your session has expired.', 401, false))
    const options = args()
    const { result } = renderHook(() => useCaseDocumentTransfers(options))
    await act(async () => { await result.current.uploadFilesToCurrentFolder([new File(['x'], 'one.txt')]) })
    expect(options.onRefresh).not.toHaveBeenCalled()
    expect(options.setActionErr).toHaveBeenLastCalledWith(expect.stringContaining('session has expired'))
    expect(options.setBusy).toHaveBeenLastCalledWith(false)
  })

})

it('retains selected files and progress for explicit retry after session recovery', async () => {
  const files = [new File(['a'], 'one.txt'), new File(['b'], 'two.txt')]
  vi.mocked(uploadFilesToCaseFolder).mockImplementationOnce(async (_id, _token, _folder, _files, progress) => {
    progress!.completed = 1
    throw new DocumentRequestError('Your session has expired.', 401, false)
  }).mockResolvedValueOnce()
  const options = args(); vi.mocked(options.askConfirm).mockResolvedValue(true)
  const { result } = renderHook(() => useCaseDocumentTransfers(options))
  await act(async () => { await result.current.uploadFilesToCurrentFolder(files) })
  expect(uploadFilesToCaseFolder).toHaveBeenCalledTimes(2)
  const retry = vi.mocked(uploadFilesToCaseFolder).mock.calls[1]
  expect(retry[3]).toBe(files)
  expect(retry[4]!.completed).toBe(1)
})
