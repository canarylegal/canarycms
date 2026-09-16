import type { Dispatch, RefObject, SetStateAction } from 'react'
import { apiFetch } from '../api'
import { CANARY_FOLLOW_UP_STANDARD_TASK_ID } from '../standardTasks'
import { isQuotePortalSendCandidate } from '../quotePortalFile'
import type {
  CasePortalFolderAccessGrantOut,
  FileSummary,
} from '../types'
import {
  decodeFolderPathForDisplay,
  decodeFolderPathSegment,
  joinFolderPath,
  splitFolderPath,
} from './folderPathCodec'
import { isEmlLikeFileSummary } from './officeFiles'
import {
  portalContactsForFolder,
  portalSharedFolderDeleteConfirmMessage,
  portalSharedFolderMoveConfirmMessage,
} from './portalFolderAccess'
import type { CaseDetailLeftDocPanel } from './CaseDetailLeftNav'

export type CaseDocMenuState =
  | { kind: 'file'; fileId: string; x: number; y: number }
  | { kind: 'folder'; folderPath: string; x: number; y: number }
  | { kind: 'surface'; x: number; y: number }

export type CaseDocMoveMenu =
  | { kind: 'file'; fileId: string }
  | { kind: 'folder'; folderPath: string }
  | null

export type CaseDocTextPrompt = {
  title: string
  hint?: string
  initial: string
  confirmLabel: string
  onConfirm: (value: string) => void
}

export type CaseDocsContextMenuProps = {
  docMenu: CaseDocMenuState
  docMenuRef: RefObject<HTMLDivElement | null>
  docMenuStyle: { left: number; top: number; maxHeight?: number } | null
  moveMenu: CaseDocMoveMenu
  setMoveMenu: Dispatch<SetStateAction<CaseDocMoveMenu>>
  portalMenu: { folderPath: string } | null
  setPortalMenu: Dispatch<SetStateAction<{ folderPath: string } | null>>
  setDocMenu: Dispatch<SetStateAction<CaseDocMenuState | null>>
  createFolderAtCurrentPath: () => void
  setDocFolder: Dispatch<SetStateAction<string>>
  downloadCaseFolderZip: (folderPath: string) => void | Promise<void>
  docFolder: string
  setTextPrompt: Dispatch<SetStateAction<CaseDocTextPrompt | null>>
  caseId: string | undefined
  token: string
  onRefresh: () => void
  setBusy: Dispatch<SetStateAction<boolean>>
  setActionErr: Dispatch<SetStateAction<string | null>>
  allFolderPaths: string[]
  portalEnabled: boolean
  setCaseDocPanel: Dispatch<SetStateAction<CaseDetailLeftDocPanel>>
  openPortalSharePanel: (folderPath: string) => void
  portalFolderGrants: CasePortalFolderAccessGrantOut[]
  askConfirm: (opts: {
    title: string
    message: string
    danger?: boolean
    confirmLabel?: string
  }) => Promise<boolean>
  files: FileSummary[]
  selectedDocSet: Set<string>
  setSelectedDocSet: Dispatch<SetStateAction<Set<string>>>
  previewEmlFile: (f: FileSummary) => void | Promise<void>
  openCaseFile: (f: FileSummary) => void | Promise<void>
  downloadCaseFiles: (targets: FileSummary[]) => void | Promise<void>
  setPortalQuoteSend: Dispatch<
    SetStateAction<{ fileId: string; fileName: string; folderPath: string } | null>
  >
  docusignEnabled: boolean
  pushNotification: (msg: string) => void
  setDocusignSend: Dispatch<
    SetStateAction<{ fileId: string; fileName: string; amendFromId?: string | null } | null>
  >
  canarySignEnabled: boolean
  setCanarySignSend: Dispatch<
    SetStateAction<{ fileId: string; fileName: string; amendFromId?: string | null } | null>
  >
  setTaskCreatePreset: Dispatch<
    SetStateAction<{ standardTaskId?: string; title?: string } | null>
  >
  setTaskCreateOpen: Dispatch<SetStateAction<boolean>>
  isCommentFile: (f: FileSummary) => boolean
}

export function CaseDocsContextMenu({
  docMenu,
  docMenuRef,
  docMenuStyle,
  moveMenu,
  setMoveMenu,
  portalMenu,
  setPortalMenu,
  setDocMenu,
  createFolderAtCurrentPath,
  setDocFolder,
  downloadCaseFolderZip,
  docFolder,
  setTextPrompt,
  caseId,
  token,
  onRefresh,
  setBusy,
  setActionErr,
  allFolderPaths,
  portalEnabled,
  setCaseDocPanel,
  openPortalSharePanel,
  portalFolderGrants,
  askConfirm,
  files,
  selectedDocSet,
  setSelectedDocSet,
  previewEmlFile,
  openCaseFile,
  downloadCaseFiles,
  setPortalQuoteSend,
  docusignEnabled,
  pushNotification,
  setDocusignSend,
  canarySignEnabled,
  setCanarySignSend,
  setTaskCreatePreset,
  setTaskCreateOpen,
  isCommentFile,
}: CaseDocsContextMenuProps) {
  return (
      <div
        ref={docMenuRef}
        className="docContextMenu"
        style={{
          left: docMenuStyle?.left ?? docMenu.x,
          top: docMenuStyle?.top ?? docMenu.y,
          ...(docMenuStyle?.maxHeight != null
            ? { maxHeight: docMenuStyle.maxHeight, overflowY: 'auto' as const }
            : {}),
        }}
        onMouseDown={(e) => e.stopPropagation()}
        onMouseLeave={() => {
          setMoveMenu(null)
          setPortalMenu(null)
        }}
      >
        {docMenu.kind === 'surface' ? (
          <div
            className="docContextItem"
            onClick={() => {
              setDocMenu(null)
              createFolderAtCurrentPath()
            }}
          >
            New folder
          </div>
        ) : null}

        {docMenu.kind === 'folder' ? (
          <div
            className="docContextItem"
            onClick={() => {
              setDocFolder(docMenu.folderPath)
              setDocMenu(null)
            }}
          >
            Open
          </div>
        ) : null}

        {docMenu.kind === 'folder' ? (
          <div
            className="docContextItem"
            onClick={() => {
              void downloadCaseFolderZip(docMenu.folderPath)
            }}
          >
            Download
          </div>
        ) : null}

        {docMenu.kind === 'folder' ? (
          <>
            <div
              className="docContextItem"
              onClick={() => {
                const current = docMenu.folderPath
                const parts = splitFolderPath(current)
                const parent = parts.length > 1 ? parts.slice(0, -1).join('/') : ''
                const leafEnc = parts[parts.length - 1] || ''
                const leaf = decodeFolderPathSegment(leafEnc)
                setDocMenu(null)
                setTextPrompt({
                  title: 'Rename folder',
                  hint: 'Name only (not the full path).',
                  initial: leaf,
                  confirmLabel: 'Rename',
                  onConfirm: (newName) => {
                    const trimmed = newName.trim()
                    setTextPrompt(null)
                    if (!trimmed) return
                    const newFolderPath = joinFolderPath(parent, trimmed)
                    if (docFolder === current) setDocFolder(newFolderPath)
                    setBusy(true)
                    setActionErr(null)
                    apiFetch(`/cases/${caseId}/files/folders/rename`, {
                      token,
                      method: 'POST',
                      json: { old_folder_path: current, new_folder_path: newFolderPath },
                    })
                      .then(() => {
                        onRefresh()
                      })
                      .catch((e: any) => {
                        setActionErr(e?.message ?? 'Failed to rename folder')
                      })
                      .finally(() => {
                        setBusy(false)
                      })
                  },
                })
              }}
            >
              Rename
            </div>

            <div
              className="docContextSubWrap"
              onMouseEnter={() => setMoveMenu({ kind: 'folder', folderPath: docMenu.folderPath })}
              onMouseLeave={() => setMoveMenu(null)}
            >
              <div className="docContextItem docContextItemRow">
                <span>Move</span>
                <span className="docMenuChevron" aria-hidden>
                  ▸
                </span>
              </div>
              {moveMenu?.kind === 'folder' && moveMenu.folderPath === docMenu.folderPath ? (
                <div className="docSubMenu" role="menu">
                  {(() => {
                    const current = docMenu.folderPath
                    const currentParts = splitFolderPath(current)
                    const leaf = currentParts[currentParts.length - 1] ?? ''
                    const forbiddenPrefix = `${current}/`
                    const currentParent = currentParts.length > 1 ? currentParts.slice(0, -1).join('/') : ''
                    const options = [
                      { label: 'Home', parent: '' },
                      ...allFolderPaths
                        .filter(
                          (p) => p !== current && !p.startsWith(forbiddenPrefix),
                        )
                        .map((p) => ({ label: decodeFolderPathForDisplay(p), parent: p })),
                    ]
                    return options.map((opt) => {
                      const isCurrentParent = opt.parent === currentParent
                      return (
                      <div
                        key={`folder-move-${opt.parent || 'home'}`}
                        className={`docContextItem${isCurrentParent ? ' docContextItemDisabled' : ''}`}
                        role="menuitem"
                        aria-disabled={isCurrentParent}
                        onClick={() => {
                          if (isCurrentParent) return
                          const newFullPath = opt.parent ? `${opt.parent}/${leaf}` : leaf
                          if (docFolder === current) setDocFolder(newFullPath)
                          else if (docFolder.startsWith(`${current}/`)) {
                            setDocFolder(`${newFullPath}/${docFolder.slice(current.length + 1)}`)
                          }
                          setBusy(true)
                          setActionErr(null)
                          apiFetch(`/cases/${caseId}/files/folders/move`, {
                            token,
                            method: 'POST',
                            json: { old_folder_path: current, new_parent_path: opt.parent },
                          })
                            .then(() => onRefresh())
                            .catch((e: any) => setActionErr(e?.message ?? 'Failed to move folder'))
                            .finally(() => setBusy(false))
                          setMoveMenu(null)
                          setDocMenu(null)
                        }}
                      >
                        {opt.label}
                      </div>
                      )
                    })
                  })()}
                </div>
              ) : null}
            </div>

            {portalEnabled ? (
            <div
              className="docContextSubWrap"
              onMouseEnter={() => setPortalMenu({ folderPath: docMenu.folderPath })}
              onMouseLeave={() => setPortalMenu(null)}
            >
              <div className="docContextItem docContextItemRow">
                <span>Portal</span>
                <span className="docMenuChevron" aria-hidden>
                  ▸
                </span>
              </div>
              {portalMenu?.folderPath === docMenu.folderPath ? (
                <div className="docSubMenu" role="menu">
                  <div
                    className="docContextItem"
                    role="menuitem"
                    onClick={() => {
                      setDocMenu(null)
                      setPortalMenu(null)
                      setCaseDocPanel('portal-hub')
                    }}
                  >
                    Activity & settings
                  </div>
                  <div
                    className="docContextItem"
                    role="menuitem"
                    onClick={() => openPortalSharePanel(docMenu.folderPath)}
                  >
                    Share
                  </div>
                </div>
              ) : null}
            </div>
            ) : null}

            <div
              className="docContextItem"
              onClick={() => {
                void (async () => {
                  const current = docMenu.folderPath
                  const sharedContacts = portalEnabled ? portalContactsForFolder(current, portalFolderGrants) : []
                  const ok = await askConfirm({
                    title: 'Delete folder',
                    message: portalSharedFolderDeleteConfirmMessage(
                      decodeFolderPathForDisplay(current),
                      sharedContacts,
                    ),
                    danger: true,
                    confirmLabel: 'Delete',
                  })
                  if (!ok) return
                  setDocMenu(null)
                  setBusy(true)
                  setActionErr(null)
                  apiFetch(`/cases/${caseId}/files/folders/delete`, {
                    token,
                    method: 'POST',
                    json: { folder_path: current },
                  })
                    .then(() => {
                      if (docFolder === current) setDocFolder('')
                      onRefresh()
                    })
                    .catch((e: any) => {
                      setActionErr(e?.message ?? 'Failed to delete folder')
                    })
                    .finally(() => {
                      setBusy(false)
                    })
                  setMoveMenu(null)
                })()
              }}
            >
              Delete
            </div>
          </>
        ) : null}

        {docMenu.kind === 'file' ? (
          <>
            {(() => {
              const f = files.find((x) => x.id === docMenu.fileId)
              if (!f) return null
              const canOpenDownload = f.category !== 'system' && f.mime_type !== 'application/x-directory'
              if (!canOpenDownload) return null
              return (
                <>
                  {isEmlLikeFileSummary(f) ? (
                    <div
                      className="docContextItem"
                      onClick={() => {
                        setDocMenu(null)
                        void previewEmlFile(f)
                      }}
                    >
                      Preview
                    </div>
                  ) : null}
                  <div
                    className="docContextItem"
                    onClick={() => {
                      setDocMenu(null)
                      void openCaseFile(f)
                    }}
                  >
                    Open
                  </div>
                  <div
                    className="docContextItem"
                    onClick={() => {
                      const isMultiSelected = selectedDocSet.has(f.id) && selectedDocSet.size > 1
                      const ids = isMultiSelected
                        ? [...selectedDocSet].filter((k) => !k.startsWith('folder:'))
                        : [f.id]
                      const targets = ids
                        .map((id) => files.find((x) => x.id === id))
                        .filter((x): x is FileSummary => Boolean(x))
                      setDocMenu(null)
                      void downloadCaseFiles(targets)
                    }}
                  >
                    {selectedDocSet.has(f.id) && selectedDocSet.size > 1
                      ? `Download ${[...selectedDocSet].filter((k) => !k.startsWith('folder:')).length} files`
                      : 'Download'}
                  </div>
                  {portalEnabled && isQuotePortalSendCandidate(f) ? (
                    <div
                      className="docContextItem"
                      onClick={() => {
                        setDocMenu(null)
                        setPortalQuoteSend({
                          fileId: f.id,
                          fileName: f.original_filename,
                          folderPath: f.folder_path ?? '',
                        })
                      }}
                    >
                      Send quote via portal
                    </div>
                  ) : null}
                  {docusignEnabled && f.category !== 'system' ? (
                    <>
                      {f.docusign_signing?.status === 'pending' ? (
                        <>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              void (async () => {
                                if (!caseId) return
                                setBusy(true)
                                try {
                                  await apiFetch(`/cases/${caseId}/docusign/requests/${f.docusign_signing!.id}/resend`, {
                                    token,
                                    method: 'POST',
                                  })
                                  pushNotification('Signing reminders sent.')
                                } catch (e: any) {
                                  setActionErr(e?.message ?? 'Resend failed')
                                } finally {
                                  setBusy(false)
                                }
                              })()
                            }}
                          >
                            Resend DocuSign link
                          </div>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              setDocusignSend({
                                fileId: f.id,
                                fileName: f.original_filename,
                                amendFromId: f.docusign_signing!.id,
                              })
                            }}
                          >
                            Amend & re-send
                          </div>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              void (async () => {
                                if (!caseId) return
                                const ok = await askConfirm({
                                  title: 'Void DocuSign envelope',
                                  message: 'Void this envelope? Recipients will no longer be able to sign.',
                                })
                                if (!ok) return
                                setBusy(true)
                                try {
                                  await apiFetch(`/cases/${caseId}/docusign/requests/${f.docusign_signing!.id}/void`, {
                                    token,
                                    method: 'POST',
                                    json: { reason: 'Voided from Canary' },
                                  })
                                  onRefresh()
                                } catch (e: any) {
                                  setActionErr(e?.message ?? 'Void failed')
                                } finally {
                                  setBusy(false)
                                }
                              })()
                            }}
                          >
                            Void DocuSign envelope
                          </div>
                        </>
                      ) : (
                        <div
                          className="docContextItem"
                          onClick={() => {
                            setDocMenu(null)
                            setDocusignSend({ fileId: f.id, fileName: f.original_filename })
                          }}
                        >
                          Send for signature (DocuSign)
                        </div>
                      )}
                    </>
                  ) : null}
                  {canarySignEnabled && portalEnabled && f.category !== 'system' ? (
                    <>
                      {f.canary_signing?.status === 'pending' ? (
                        <>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              void (async () => {
                                if (!caseId || !f.canary_signing) return
                                setBusy(true)
                                try {
                                  await apiFetch(`/cases/${caseId}/canary-sign/requests/${f.canary_signing.id}/remind`, {
                                    token,
                                    method: 'POST',
                                  })
                                  pushNotification('Signing reminders sent.')
                                } catch (e: any) {
                                  setActionErr(e?.message ?? 'Remind failed')
                                } finally {
                                  setBusy(false)
                                }
                              })()
                            }}
                          >
                            Remind Canary Sign
                          </div>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              setCanarySignSend({
                                fileId: f.id,
                                fileName: f.original_filename,
                                amendFromId: f.canary_signing!.id,
                              })
                            }}
                          >
                            Amend & re-send (Canary Sign)
                          </div>
                          <div
                            className="docContextItem"
                            onClick={() => {
                              setDocMenu(null)
                              void (async () => {
                                if (!caseId || !f.canary_signing) return
                                const ok = await askConfirm({
                                  title: 'Void Canary Sign request',
                                  message: 'Void this signing request? Recipients will no longer be able to sign.',
                                })
                                if (!ok) return
                                setBusy(true)
                                try {
                                  await apiFetch(`/cases/${caseId}/canary-sign/requests/${f.canary_signing.id}/void`, {
                                    token,
                                    method: 'POST',
                                    json: { reason: 'Voided from Canary' },
                                  })
                                  pushNotification('Canary Sign request voided.')
                                  onRefresh()
                                } catch (e: any) {
                                  setActionErr(e?.message ?? 'Void failed')
                                } finally {
                                  setBusy(false)
                                }
                              })()
                            }}
                          >
                            Void Canary Sign
                          </div>
                        </>
                      ) : (
                        <div
                          className="docContextItem"
                          onClick={() => {
                            setDocMenu(null)
                            setCanarySignSend({ fileId: f.id, fileName: f.original_filename })
                          }}
                        >
                          Send for signature (Canary Sign)
                        </div>
                      )}
                    </>
                  ) : null}
                </>
              )
            })()}

            {(() => {
              const f = files.find((x) => x.id === docMenu.fileId)
              if (!f || f.mime_type === 'application/x-directory') return null
              return (
                <div
                  className="docContextItem"
                  onClick={() => {
                    setDocMenu(null)
                    const name = f.original_filename.trim() || 'Document'
                    setTaskCreatePreset({
                      standardTaskId: CANARY_FOLLOW_UP_STANDARD_TASK_ID,
                      title: `Follow up: ${name}`,
                    })
                    setTaskCreateOpen(true)
                  }}
                >
                  Follow up
                </div>
              )
            })()}

            {(() => {
              const f = files.find((x) => x.id === docMenu.fileId)
              if (!f) return null
              if (isCommentFile(f)) {
                return (
                  <div
                    className="docContextItem"
                    onClick={() => {
                      setDocMenu(null)
                      void downloadCaseFiles([f])
                    }}
                  >
                    Export
                  </div>
                )
              }
              return (
                <div
                  className="docContextItem"
                  onClick={() => {
                    setDocMenu(null)
                    const originalName = f.original_filename.trim()
                    const extIdx = originalName.lastIndexOf('.')
                    const hasEditableExt = extIdx > 0 && extIdx < originalName.length - 1
                    const lockedExt = hasEditableExt ? originalName.slice(extIdx) : ''
                    const initialBase = hasEditableExt ? originalName.slice(0, extIdx) : originalName
                    setTextPrompt({
                      title: lockedExt ? `Rename file (extension ${lockedExt} is fixed)` : 'Rename file',
                      initial: initialBase,
                      confirmLabel: 'Rename',
                      onConfirm: (newName) => {
                        const trimmedBase = newName.trim()
                        setTextPrompt(null)
                        if (!trimmedBase) return
                        const finalName = `${trimmedBase}${lockedExt}`
                        if (finalName === f.original_filename) return
                        setBusy(true)
                        setActionErr(null)
                        apiFetch(`/cases/${caseId}/files/${f.id}/rename`, {
                          token,
                          method: 'PATCH',
                          json: { original_filename: finalName },
                        })
                          .then(() => onRefresh())
                          .catch((e: any) => setActionErr(e?.message ?? 'Failed to rename file'))
                          .finally(() => setBusy(false))
                      },
                    })
                  }}
                >
                  Rename
                </div>
              )
            })()}

            <div
              className="docContextItem"
              onClick={async () => {
                const f = files.find((x) => x.id === docMenu.fileId)
                if (!f) return
                setBusy(true)
                setActionErr(null)
                try {
                  await apiFetch(`/cases/${caseId}/files/${f.id}/pin`, {
                    token,
                    method: 'PATCH',
                    json: { is_pinned: !f.is_pinned },
                  })
                  onRefresh()
                  setDocMenu(null)
                  setMoveMenu(null)
                } catch (e: any) {
                  setActionErr(e?.message ?? 'Failed to update pin')
                } finally {
                  setBusy(false)
                }
              }}
            >
              {files.find((x) => x.id === docMenu.fileId)?.is_pinned ? 'Unpin' : 'Pin'}
            </div>

            <div
              className="docContextSubWrap"
              onMouseEnter={() => setMoveMenu({ kind: 'file', fileId: docMenu.fileId })}
              onMouseLeave={() => setMoveMenu(null)}
            >
              <div className="docContextItem docContextItemRow">
                <span>Move</span>
                <span className="docMenuChevron" aria-hidden>
                  ▸
                </span>
              </div>
              {moveMenu?.kind === 'file' && moveMenu.fileId === docMenu.fileId ? (
                <div className="docSubMenu" role="menu">
                  {(() => {
                    const f = files.find((x) => x.id === docMenu.fileId)
                    if (!f) return null
                    const here = (f.folder_path ?? '').trim()
                    return [
                      { label: 'Home', path: '' },
                      ...allFolderPaths.map((p) => ({ label: decodeFolderPathForDisplay(p), path: p })),
                    ].map((opt) => {
                        const isHere = here === (opt.path ?? '').trim()
                        return (
                      <div
                        key={`file-move-${opt.path || 'home'}`}
                        className={`docContextItem${isHere ? ' docContextItemDisabled' : ''}`}
                        role="menuitem"
                        aria-disabled={isHere}
                        onClick={() => {
                          if (isHere) return
                          void (async () => {
                            const file = files.find((x) => x.id === moveMenu.fileId)
                            if (!file) return
                            const targetContacts = portalContactsForFolder(opt.path, portalFolderGrants)
                            if (targetContacts.length) {
                              const ok = await askConfirm({
                                title: 'Move to shared folder',
                                message: portalSharedFolderMoveConfirmMessage(targetContacts),
                              })
                              if (!ok) return
                            }
                            const isMultiSelected =
                              selectedDocSet.has(file.id) && selectedDocSet.size > 1
                            const idsToMove = isMultiSelected
                              ? [...selectedDocSet].filter((k) => !k.startsWith('folder:'))
                              : [file.id]
                            setBusy(true)
                            setActionErr(null)
                            try {
                              for (const id of idsToMove) {
                                await apiFetch(`/cases/${caseId}/files/${id}/move`, {
                                  token,
                                  method: 'POST',
                                  json: { folder_path: opt.path },
                                })
                              }
                              setSelectedDocSet(new Set())
                              onRefresh()
                            } catch (e: any) {
                              setActionErr(e?.message ?? 'Failed to move file(s)')
                            } finally {
                              setBusy(false)
                            }
                            setMoveMenu(null)
                            setDocMenu(null)
                          })()
                        }}
                      >
                        {opt.label}
                      </div>
                        )
                      },
                    )
                  })()}
                </div>
              ) : null}
            </div>

            <div
              className="docContextItem"
              onClick={async () => {
                const f = files.find((x) => x.id === docMenu.fileId)
                if (!f) return
                // If this file is in a multi-selection, delete all selected files
                const isMultiSelected = selectedDocSet.has(f.id) && selectedDocSet.size > 1
                const idsToDelete = isMultiSelected
                  ? [...selectedDocSet].filter((k) => !k.startsWith('folder:'))
                  : [f.id]
                const label = isMultiSelected
                  ? `${idsToDelete.length} selected files`
                  : `"${f.original_filename}"`
                const ok = await askConfirm({
                  title: 'Delete file',
                  message: `Delete ${label}?`,
                  danger: true,
                  confirmLabel: 'Delete',
                })
                if (!ok) return
                setDocMenu(null)
                setMoveMenu(null)
                setBusy(true)
                setActionErr(null)
                try {
                  await Promise.all(
                    idsToDelete.map((id) =>
                      apiFetch(`/cases/${caseId}/files/${id}`, { token, method: 'DELETE' }),
                    ),
                  )
                  setSelectedDocSet(new Set())
                  onRefresh()
                } catch (e: any) {
                  setActionErr(e?.message ?? 'Failed to delete file(s)')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Delete
            </div>
          </>
        ) : null}
      </div>
  )
}
