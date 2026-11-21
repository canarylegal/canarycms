import { fileDocOwnerLabel } from './caseDetailHelpers'
import { docListPrimaryDate, formatDocFileSize, formatDocModified } from './docFormat'
import { DocsFileDescCell, DocsFolderDescCell, folderContentsSummary } from './DocCells'
import { decodeFolderPathSegment } from './folderPathCodec'
import { isEmlLikeFileSummary } from './officeFiles'
import { isPortalSharedFolder } from './portalFolderAccess'
import type { CaseDocsBrowserProps } from './caseDocsBrowserTypes'

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
  folderSummaries,
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
  | 'folderSummaries'
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
        data-doc-key={f.id}
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
          data-doc-key={folderKey}
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
            contentsSummary={folderSummaries?.[next] ?? folderContentsSummary(files, next)}
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
        data-doc-key={f.id}
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
