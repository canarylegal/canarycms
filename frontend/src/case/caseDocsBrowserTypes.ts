import type { Dispatch, MouseEvent, RefObject, SetStateAction } from 'react'
import type { CasePortalFolderAccessGrantOut, FileSummary } from '../types'
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
