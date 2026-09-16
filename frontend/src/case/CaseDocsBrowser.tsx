import type { Dispatch, MouseEvent, RefObject, SetStateAction } from 'react'
import { createPortal } from 'react-dom'
import { SearchInput } from '../SearchInput'
import type { CasePortalFolderAccessGrantOut, FileSummary } from '../types'
import {
  CASE_DOCS_TOOLBAR_ICONS,
  CaseDocsToolbarBtnIcon,
} from './caseDetailChrome'
import { fileDocOwnerLabel } from './caseDetailHelpers'
import { docListPrimaryDate, formatDocFileSize, formatDocModified } from './docFormat'
import { DocsFileDescCell, DocsFolderDescCell, folderContentsSummary } from './DocCells'
import { decodeFolderPathSegment } from './folderPathCodec'
import { isEmlLikeFileSummary } from './officeFiles'
import { isPortalSharedFolder } from './portalFolderAccess'
import type { PrecedentPickerState } from '../quoteEmailPrecedent'
import type { CaseDetailLeftDocPanel } from './CaseDetailLeftNav'

export type CaseDocsBrowserProps = {
  busy: boolean
  portalEnabled: boolean
  caseDetail: { id: string } | null
  newMenuRef: RefObject<HTMLDivElement | null>
  newMenuBtnRef: RefObject<HTMLButtonElement | null>
  newMenuPortalRef: RefObject<HTMLDivElement | null>
  newMenuOpen: boolean
  setNewMenuOpen: Dispatch<SetStateAction<boolean>>
  newMenuPos: { top: number; left: number } | null
  createFolderAtCurrentPath: () => void
  openTaskCreateModal: () => void
  openCaseEventModal: () => void
  setQuoteWizardOpen: Dispatch<SetStateAction<boolean>>
  setFormSendOpen: Dispatch<SetStateAction<boolean>>
  setPrecedentPicker: Dispatch<SetStateAction<PrecedentPickerState | null>>
  setCommentText: Dispatch<SetStateAction<string>>
  setCommentErr: Dispatch<SetStateAction<string | null>>
  setCommentOpen: Dispatch<SetStateAction<boolean>>
  importInputRef: RefObject<HTMLInputElement | null>
  downloadCaseExportZip: () => void | Promise<void>
  setCaseDocPanel: Dispatch<SetStateAction<CaseDetailLeftDocPanel>>
  onRefresh: () => void
  docSearch: string
  setDocSearch: Dispatch<SetStateAction<string>>
  docSortKey: 'description' | 'size' | 'created' | 'user'
  setDocSortKey: Dispatch<SetStateAction<'description' | 'size' | 'created' | 'user'>>
  docSortDir: 'asc' | 'desc'
  setDocSortDir: Dispatch<SetStateAction<'asc' | 'desc'>>
  breadcrumbParts: string[]
  setDocFolder: Dispatch<SetStateAction<string>>
  sortedPinnedInFolder: FileSummary[]
  sortedChildFolders: string[]
  sortedRegularInFolder: FileSummary[]
  childFolders: string[]
  docFolder: string
  selectedDocSet: Set<string>
  docFocusKey: string | null
  handleDocItemClick: (key: string, e: MouseEvent) => void
  previewEmlFile: (f: FileSummary) => void | Promise<void>
  openCaseFile: (f: FileSummary) => void | Promise<void>
  setDocMenu: Dispatch<
    SetStateAction<
      | null
      | { kind: 'file'; fileId: string; x: number; y: number }
      | { kind: 'folder'; folderPath: string; x: number; y: number }
      | { kind: 'surface'; x: number; y: number }
    >
  >
  portalFolderGrants: CasePortalFolderAccessGrantOut[]
  files: FileSummary[]
}

export function CaseDocsToolbar({
  busy,
  portalEnabled,
  caseDetail,
  newMenuRef,
  newMenuBtnRef,
  newMenuPortalRef,
  newMenuOpen,
  setNewMenuOpen,
  newMenuPos,
  createFolderAtCurrentPath,
  openTaskCreateModal,
  openCaseEventModal,
  setQuoteWizardOpen,
  setFormSendOpen,
  setPrecedentPicker,
  setCommentText,
  setCommentErr,
  setCommentOpen,
  importInputRef,
  downloadCaseExportZip,
  setCaseDocPanel,
  onRefresh,
  docSearch,
  setDocSearch,
}: Pick<
  CaseDocsBrowserProps,
  | 'busy'
  | 'portalEnabled'
  | 'caseDetail'
  | 'newMenuRef'
  | 'newMenuBtnRef'
  | 'newMenuPortalRef'
  | 'newMenuOpen'
  | 'setNewMenuOpen'
  | 'newMenuPos'
  | 'createFolderAtCurrentPath'
  | 'openTaskCreateModal'
  | 'openCaseEventModal'
  | 'setQuoteWizardOpen'
  | 'setFormSendOpen'
  | 'setPrecedentPicker'
  | 'setCommentText'
  | 'setCommentErr'
  | 'setCommentOpen'
  | 'importInputRef'
  | 'downloadCaseExportZip'
  | 'setCaseDocPanel'
  | 'onRefresh'
  | 'docSearch'
  | 'setDocSearch'
>) {
  return (
    <div
      className="caseDocsToolbarBar"
      role="toolbar"
      aria-label="Documents actions"
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.stopPropagation()}
    >
      <div className="caseDocsToolbar">
        <div className="caseDocsToolbarMain">
          <div className="caseToolbarDropdownWrap" ref={newMenuRef}>
            <button
              ref={newMenuBtnRef}
              type="button"
              className="btn btnCaseChrome caseDocsNewMenuBtn"
              disabled={busy}
              aria-haspopup="menu"
              aria-expanded={newMenuOpen}
              onClick={() => setNewMenuOpen((o) => !o)}
            >
              New <span className="caseDocsNewMenuChevron" aria-hidden>▾</span>
            </button>
            {newMenuOpen && newMenuPos
              ? createPortal(
                  <div
                    ref={newMenuPortalRef}
                    className="caseToolbarDropdown caseToolbarDropdown--portal"
                    role="menu"
                    style={{ top: newMenuPos.top, left: newMenuPos.left }}
                  >
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        createFolderAtCurrentPath()
                      }}
                    >
                      Folder
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        openTaskCreateModal()
                      }}
                    >
                      Task
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        openCaseEventModal()
                      }}
                    >
                      Event
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        setQuoteWizardOpen(true)
                      }}
                    >
                      Quote
                    </button>
                    {portalEnabled ? (
                      <button
                        type="button"
                        className="caseToolbarDropdownItem"
                        role="menuitem"
                        onClick={() => {
                          setNewMenuOpen(false)
                          setFormSendOpen(true)
                        }}
                      >
                        Portal form
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        setPrecedentPicker({ kind: 'letter' })
                      }}
                    >
                      Letter
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        setPrecedentPicker({ kind: 'document' })
                      }}
                    >
                      Document
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        setPrecedentPicker({ kind: 'email' })
                      }}
                    >
                      E-mail
                    </button>
                    <button
                      type="button"
                      className="caseToolbarDropdownItem"
                      role="menuitem"
                      onClick={() => {
                        setNewMenuOpen(false)
                        setCommentText('')
                        setCommentErr(null)
                        setCommentOpen(true)
                      }}
                    >
                      Comment
                    </button>
                  </div>,
                  document.body,
                )
              : null}
          </div>
          <button
            type="button"
            className="btn btnCaseChrome caseDocsToolbarActionBtn"
            disabled={busy}
            onClick={() => importInputRef.current?.click()}
          >
            <CaseDocsToolbarBtnIcon d={CASE_DOCS_TOOLBAR_ICONS.import} />
            Import
          </button>
          <button
            type="button"
            className="btn btnCaseChrome caseDocsToolbarActionBtn"
            disabled={busy || !caseDetail}
            onClick={() => void downloadCaseExportZip()}
          >
            <CaseDocsToolbarBtnIcon d={CASE_DOCS_TOOLBAR_ICONS.export} />
            Export
          </button>
          {portalEnabled ? (
            <button
              type="button"
              className="btn btnCaseChrome caseDocsToolbarActionBtn"
              disabled={busy}
              onClick={() => setCaseDocPanel('portal-hub')}
            >
              <CaseDocsToolbarBtnIcon d={CASE_DOCS_TOOLBAR_ICONS.portal} />
              Portal
            </button>
          ) : null}
          <button
            type="button"
            className="btn btnCaseChrome caseDocsToolbarActionBtn"
            disabled={busy}
            onClick={() => onRefresh()}
          >
            <CaseDocsToolbarBtnIcon d={CASE_DOCS_TOOLBAR_ICONS.refresh} />
            Refresh
          </button>
        </div>
        <SearchInput
          className="caseDocsToolbarSearch"
          placeholder="Search documents…"
          value={docSearch}
          onChange={(e) => setDocSearch(e.target.value)}
          onClear={() => setDocSearch('')}
          aria-label="Search documents"
        />
      </div>
    </div>
  )
}

export function CaseDocsList({
  docSortKey,
  setDocSortKey,
  docSortDir,
  setDocSortDir,
  breadcrumbParts,
  setDocFolder,
  sortedPinnedInFolder,
  sortedChildFolders,
  sortedRegularInFolder,
  childFolders,
  docFolder,
  selectedDocSet,
  docFocusKey,
  handleDocItemClick,
  previewEmlFile,
  openCaseFile,
  setDocMenu,
  portalEnabled,
  portalFolderGrants,
  files,
}: Pick<
  CaseDocsBrowserProps,
  | 'docSortKey'
  | 'setDocSortKey'
  | 'docSortDir'
  | 'setDocSortDir'
  | 'breadcrumbParts'
  | 'setDocFolder'
  | 'sortedPinnedInFolder'
  | 'sortedChildFolders'
  | 'sortedRegularInFolder'
  | 'childFolders'
  | 'docFolder'
  | 'selectedDocSet'
  | 'docFocusKey'
  | 'handleDocItemClick'
  | 'previewEmlFile'
  | 'openCaseFile'
  | 'setDocMenu'
  | 'portalEnabled'
  | 'portalFolderGrants'
  | 'files'
>) {
  return (
    <>
    <div className="caseDocsListHead">
    <div className="docsTr docsTh">
      <button
        type="button"
        className="thbtn"
        onClick={() => {
          if (docSortKey === 'description') setDocSortDir(docSortDir === 'asc' ? 'desc' : 'asc')
          else {
            setDocSortKey('description')
            setDocSortDir('asc')
          }
        }}
      >
        Description
      </button>
      <button
        type="button"
        className="thbtn docsCenter"
        onClick={() => {
          if (docSortKey === 'size') setDocSortDir(docSortDir === 'asc' ? 'desc' : 'asc')
          else {
            setDocSortKey('size')
            setDocSortDir('asc')
          }
        }}
      >
        Size
      </button>
      <button
        type="button"
        className="thbtn docsCenter"
        onClick={() => {
          if (docSortKey === 'created') setDocSortDir(docSortDir === 'asc' ? 'desc' : 'asc')
          else {
            setDocSortKey('created')
            setDocSortDir('desc')
          }
        }}
      >
        Created
      </button>
      <button
        type="button"
        className="thbtn docsCenter"
        onClick={() => {
          if (docSortKey === 'user') setDocSortDir(docSortDir === 'asc' ? 'desc' : 'asc')
          else {
            setDocSortKey('user')
            setDocSortDir('asc')
          }
        }}
      >
        User
      </button>
    </div>
    </div>
    <div
      className="muted"
      style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
      onContextMenu={(e) => e.stopPropagation()}
    >
      <span
        style={{ cursor: 'pointer', textDecoration: 'underline' }}
        onClick={() => setDocFolder('')}
        title="Home"
      >
        Home
      </span>
      {breadcrumbParts.map((p, idx) => {
        const path = breadcrumbParts.slice(0, idx + 1).join('/')
        return (
          <span key={path} style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <span aria-hidden> / </span>
            <span style={{ cursor: 'pointer', textDecoration: 'underline' }} onClick={() => setDocFolder(path)}>
              {decodeFolderPathSegment(p)}
            </span>
          </span>
        )
      })}
    </div>

    {sortedPinnedInFolder.map((f) => (
      <div
        key={f.id}
        className={`docsTr rowbtn ${f.parent_file_id ? 'attachmentChild' : ''} ${selectedDocSet.has(f.id) ? 'active' : ''} ${docFocusKey === f.id ? 'docsTr--focused' : ''}`}
        onMouseDown={(e) => { if (e.shiftKey) e.preventDefault() }}
        onClick={(e) => handleDocItemClick(f.id, e)}
        onDoubleClick={(e) => {
          e.stopPropagation()
          if (isEmlLikeFileSummary(f)) void previewEmlFile(f)
          else void openCaseFile(f)
        }}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setDocMenu({ kind: 'file', fileId: f.id, x: e.clientX, y: e.clientY })
        }}
      >
        <DocsFileDescCell f={f} showPin={!f.parent_file_id} />
        <div className="td docsCenter">{formatDocFileSize(f.size_bytes)}</div>
        <div className="td docsCenter">{formatDocModified(docListPrimaryDate(f))}</div>
        <div className="td docsCenter">{fileDocOwnerLabel(f)}</div>
      </div>
    ))}

    {sortedChildFolders.map((folderName) => {
      const next = docFolder ? `${docFolder}/${folderName}` : folderName
      const folderKey = `folder:${next}`
      return (
        <div
          key={next}
          className={`docsTr rowbtn ${selectedDocSet.has(folderKey) ? 'active' : ''} ${docFocusKey === folderKey ? 'docsTr--focused' : ''}`}
          onMouseDown={(e) => { if (e.shiftKey) e.preventDefault() }}
          onClick={(e) => handleDocItemClick(folderKey, e)}
          onDoubleClick={() => setDocFolder(next)}
          onContextMenu={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDocMenu({ kind: 'folder', folderPath: next, x: e.clientX, y: e.clientY })
          }}
        >
          <DocsFolderDescCell
            name={decodeFolderPathSegment(folderName)}
            shared={portalEnabled && isPortalSharedFolder(next, portalFolderGrants)}
            contentsSummary={folderContentsSummary(files, next)}
          />
          <div className="td muted docsCenter">—</div>
          <div className="td muted docsCenter">—</div>
          <div className="td muted docsCenter">—</div>
        </div>
      )
    })}

    {sortedRegularInFolder.map((f) => (
      <div
        key={f.id}
        className={`docsTr rowbtn ${f.parent_file_id ? 'attachmentChild' : ''} ${selectedDocSet.has(f.id) ? 'active' : ''} ${docFocusKey === f.id ? 'docsTr--focused' : ''}`}
        onMouseDown={(e) => { if (e.shiftKey) e.preventDefault() }}
        onClick={(e) => handleDocItemClick(f.id, e)}
        onDoubleClick={(e) => {
          e.stopPropagation()
          if (isEmlLikeFileSummary(f)) void previewEmlFile(f)
          else void openCaseFile(f)
        }}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setDocMenu({ kind: 'file', fileId: f.id, x: e.clientX, y: e.clientY })
        }}
      >
        <DocsFileDescCell f={f} showPin={false} />
        <div className="td docsCenter">{formatDocFileSize(f.size_bytes)}</div>
        <div className="td docsCenter">{formatDocModified(docListPrimaryDate(f))}</div>
        <div className="td docsCenter">{fileDocOwnerLabel(f)}</div>
      </div>
    ))}

    {sortedPinnedInFolder.length === 0 && sortedRegularInFolder.length === 0 && childFolders.length === 0 ? (
      <div className="muted" style={{ padding: 12 }}>
        No documents in this folder.
      </div>
    ) : null}
    </>
  )
}
