import { createPortal } from 'react-dom'
import { SearchInput } from '../SearchInput'
import { CASE_DOCS_TOOLBAR_ICONS, CaseDocsToolbarBtnIcon } from './caseDetailChrome'
import type { CaseDocsBrowserProps } from './caseDocsBrowserTypes'

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
