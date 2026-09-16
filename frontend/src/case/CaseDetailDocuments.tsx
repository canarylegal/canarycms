import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  type SetStateAction,
} from 'react'
import type { CaseOut, CasePortalFolderAccessGrantOut, FileSummary } from '../types'
import type { PrecedentPickerState } from '../quoteEmailPrecedent'
import type { CaseDetailLeftDocPanel } from './CaseDetailLeftNav'
import { CaseDocsList, CaseDocsToolbar } from './CaseDocsBrowser'
import { dndEventHasFiles } from './docFormat'
import { isEmlLikeUploadFile } from './officeFiles'

export type CaseDetailDocumentsProps = {
  busy: boolean
  portalEnabled: boolean
  caseDetail: CaseOut | null
  createFolderAtCurrentPath: () => void
  openTaskCreateModal: () => void
  openCaseEventModal: () => void
  setQuoteWizardOpen: Dispatch<SetStateAction<boolean>>
  setFormSendOpen: Dispatch<SetStateAction<boolean>>
  setPrecedentPicker: Dispatch<SetStateAction<PrecedentPickerState | null>>
  setCommentText: Dispatch<SetStateAction<string>>
  setCommentErr: Dispatch<SetStateAction<string | null>>
  setCommentOpen: Dispatch<SetStateAction<boolean>>
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
  setSelectedDocSet: Dispatch<SetStateAction<Set<string>>>
  docFocusKey: string | null
  handleDocItemClick: (key: string, e: MouseEvent) => void
  handleDocsKeyDown: (e: ReactKeyboardEvent) => void
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
  uploadFilesToCurrentFolder: (incomingFiles: File[]) => void | Promise<void>
  setActionErr: Dispatch<SetStateAction<string | null>>
}

export function CaseDetailDocuments({
  busy,
  portalEnabled,
  caseDetail,
  createFolderAtCurrentPath,
  openTaskCreateModal,
  openCaseEventModal,
  setQuoteWizardOpen,
  setFormSendOpen,
  setPrecedentPicker,
  setCommentText,
  setCommentErr,
  setCommentOpen,
  downloadCaseExportZip,
  setCaseDocPanel,
  onRefresh,
  docSearch,
  setDocSearch,
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
  setSelectedDocSet,
  docFocusKey,
  handleDocItemClick,
  handleDocsKeyDown,
  previewEmlFile,
  openCaseFile,
  setDocMenu,
  portalFolderGrants,
  files,
  uploadFilesToCurrentFolder,
  setActionErr,
}: CaseDetailDocumentsProps) {
  const [docsDragOver, setDocsDragOver] = useState(false)
  const importInputRef = useRef<HTMLInputElement | null>(null)
  const newMenuRef = useRef<HTMLDivElement | null>(null)
  const newMenuBtnRef = useRef<HTMLButtonElement | null>(null)
  const newMenuPortalRef = useRef<HTMLDivElement | null>(null)
  const [newMenuOpen, setNewMenuOpen] = useState(false)
  const [newMenuPos, setNewMenuPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!newMenuOpen) {
      setNewMenuPos(null)
      return
    }
    function updatePos() {
      const btn = newMenuBtnRef.current
      if (!btn) return
      const rect = btn.getBoundingClientRect()
      setNewMenuPos({ top: rect.bottom + 4, left: rect.left })
    }
    updatePos()
    window.addEventListener('resize', updatePos)
    window.addEventListener('scroll', updatePos, true)
    return () => {
      window.removeEventListener('resize', updatePos)
      window.removeEventListener('scroll', updatePos, true)
    }
  }, [newMenuOpen])

  useEffect(() => {
    if (!newMenuOpen) return
    function onDocMouseDown(e: globalThis.MouseEvent) {
      const t = e.target as Node
      if (newMenuRef.current?.contains(t) || newMenuPortalRef.current?.contains(t)) return
      setNewMenuOpen(false)
    }
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') setNewMenuOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [newMenuOpen])

  return (
    <>
      <CaseDocsToolbar
        busy={busy}
        portalEnabled={portalEnabled}
        caseDetail={caseDetail}
        newMenuRef={newMenuRef}
        newMenuBtnRef={newMenuBtnRef}
        newMenuPortalRef={newMenuPortalRef}
        newMenuOpen={newMenuOpen}
        setNewMenuOpen={setNewMenuOpen}
        newMenuPos={newMenuPos}
        createFolderAtCurrentPath={createFolderAtCurrentPath}
        openTaskCreateModal={openTaskCreateModal}
        openCaseEventModal={openCaseEventModal}
        setQuoteWizardOpen={setQuoteWizardOpen}
        setFormSendOpen={setFormSendOpen}
        setPrecedentPicker={setPrecedentPicker}
        setCommentText={setCommentText}
        setCommentErr={setCommentErr}
        setCommentOpen={setCommentOpen}
        importInputRef={importInputRef}
        downloadCaseExportZip={downloadCaseExportZip}
        setCaseDocPanel={setCaseDocPanel}
        onRefresh={onRefresh}
        docSearch={docSearch}
        setDocSearch={setDocSearch}
      />
      <div
        className={`card caseDocsCard${docsDragOver ? ' caseDocsCard--dragOver' : ''}`}
        onDragEnter={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (!dndEventHasFiles(e)) return
          setDocsDragOver(true)
        }}
        onDragLeave={(e) => {
          const cur = e.currentTarget as HTMLElement
          const rel = e.relatedTarget as Node | null
          if (rel && cur.contains(rel)) return
          setDocsDragOver(false)
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (dndEventHasFiles(e)) {
            e.dataTransfer.dropEffect = 'copy'
          } else {
            e.dataTransfer.dropEffect = 'none'
          }
        }}
        onClick={() => setSelectedDocSet(new Set())}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setDocMenu({ kind: 'surface', x: e.clientX, y: e.clientY })
        }}
        onDrop={async (e) => {
          e.preventDefault()
          e.stopPropagation()
          setDocsDragOver(false)
          if (!dndEventHasFiles(e)) return
          const droppedFiles = [...e.dataTransfer.files]
          if (droppedFiles.some(isEmlLikeUploadFile)) {
            setActionErr(
              'To file an e-mail in Canary, please use the add-in appropriate to your e-mail client.',
            )
            return
          }
          await uploadFilesToCurrentFolder(droppedFiles)
        }}
      >
        <div className="caseDocsScroll" tabIndex={0} onKeyDown={handleDocsKeyDown}>
          <CaseDocsList
            docSortKey={docSortKey}
            setDocSortKey={setDocSortKey}
            docSortDir={docSortDir}
            setDocSortDir={setDocSortDir}
            breadcrumbParts={breadcrumbParts}
            setDocFolder={setDocFolder}
            sortedPinnedInFolder={sortedPinnedInFolder}
            sortedChildFolders={sortedChildFolders}
            sortedRegularInFolder={sortedRegularInFolder}
            childFolders={childFolders}
            docFolder={docFolder}
            selectedDocSet={selectedDocSet}
            docFocusKey={docFocusKey}
            handleDocItemClick={handleDocItemClick}
            previewEmlFile={previewEmlFile}
            openCaseFile={openCaseFile}
            setDocMenu={setDocMenu}
            portalEnabled={portalEnabled}
            portalFolderGrants={portalFolderGrants}
            files={files}
          />
        </div>
      </div>

      <input
        ref={importInputRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={(e) => {
          const selectedFiles = Array.from(e.target.files ?? [])
          void uploadFilesToCurrentFolder(selectedFiles)
          e.target.value = ''
        }}
      />
    </>
  )
}
