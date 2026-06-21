import type { FileSummary, QuotePortalDeliverySummary, DocusignSigningRequestOut } from '../types'
import { portalFormStatusLabel } from '../portalFormFile'

/** Vimix-doder (regular / non-dark theme) icons in `public/icons/vimix/`. */
export function DocMimeIcon({ mime, filename }: { mime: string; filename?: string }) {
  const m = (mime || '').toLowerCase()
  const ext = (filename || '').toLowerCase().split('.').pop() ?? ''
  let src = '/icons/vimix/file-generic.svg'

  const excelExts = new Set(['xls', 'xlsx', 'xlsm', 'xlsb'])
  const wordExts = new Set(['doc', 'docx', 'dot', 'dotx', 'odt', 'rtf'])

  if (m.includes('pdf')) src = '/icons/vimix/file-pdf.svg'
  else if (m.startsWith('image/')) src = '/icons/vimix/file-image.svg'
  else if (excelExts.has(ext) || m.includes('spreadsheet') || m === 'application/vnd.ms-excel') {
    src = '/icons/vimix/file-office-green.svg'
  } else if (ext === 'xml' || (m.includes('xml') && !m.includes('wordprocessing'))) {
    src = '/icons/vimix/file-office-green.svg'
  } else if (m.startsWith('text/')) src = '/icons/vimix/file-text.svg'
  else if (wordExts.has(ext) || m.includes('wordprocessing') || m.includes('msword')) {
    src = '/icons/vimix/file-office.svg'
  } else if (m.includes('ms-powerpoint') || m.includes('presentation')) src = '/icons/vimix/file-office.svg'
  else if (m.includes('zip') || m.includes('archive')) src = '/icons/vimix/file-archive.svg'

  return <img className="docsVimixIcon" src={src} alt="" aria-hidden />
}

/** Parent .eml row: envelope icon, coloured by sent vs received (distinct from office blue / image green). */
function DocMailIcon({ outbound }: { outbound: boolean }) {
  return (
    <svg
      className={`docsMailGlyph${outbound ? ' docsMailGlyph--out' : ' docsMailGlyph--in'}`}
      viewBox="0 0 24 24"
      width="24"
      height="24"
      aria-hidden
    >
      <path
        fill="currentColor"
        d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"
      />
    </svg>
  )
}

function isCaseMailRootFile(f: FileSummary): boolean {
  if (f.parent_file_id) return false
  const m = (f.mime_type || '').toLowerCase()
  const name = (f.original_filename || '').toLowerCase()
  return m.includes('message/rfc822') || m.includes('rfc822') || name.endsWith('.eml')
}

function caseMailIconOutbound(f: FileSummary): boolean {
  if (f.source_mail_is_outbound === true) return true
  if (f.source_mail_is_outbound === false) return false
  const mbox = (f.source_imap_mbox || '').toLowerCase()
  if (mbox.includes('sent') || mbox.includes('outbox')) {
    if (mbox.includes('unsent')) return false
    return true
  }
  return false
}

export function DocFolderIcon({ shared = false }: { shared?: boolean }) {
  if (shared) {
    return (
      <span className="docsFolderIconWrap docsFolderIconWrap--shared" aria-hidden title="Externally shared via Canary Portal">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" className="docsFolderIconSvg docsSharedFolderIconSvg">
          <path fill="#f0b429" d="M3 7.5V19a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-7.2L9.6 5H5a2 2 0 0 0-2 2v.5z" />
          <path fill="#e07b1a" d="M3 7.5h6.4L9.6 5H5a2 2 0 0 0-2 2v.5z" />
          {/* Badge — bottom-right corner of folder */}
          <circle cx="18.4" cy="18.4" r="5.35" fill="#fff" />
          {/* Conventional share glyph (opens to the right), centred in badge */}
          <g transform="translate(18.4 18.4)">
            <circle cx="-2.15" cy="0" r="1.45" fill="#5b9fd4" />
            <circle cx="2.05" cy="-2.05" r="1.45" fill="#5b9fd4" />
            <circle cx="2.05" cy="2.05" r="1.45" fill="#5b9fd4" />
            <path
              d="M-0.85 -0.65 L1.05 -1.75 M-0.85 0.65 L1.05 1.75"
              stroke="#5b9fd4"
              strokeWidth="1.35"
              strokeLinecap="round"
              fill="none"
            />
          </g>
        </svg>
      </span>
    )
  }
  return (
    <span className="docsFolderIconWrap" aria-hidden>
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" className="docsFolderIconSvg">
        <path
          fill="currentColor"
          d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8c0-1.1-.9-1.99-2-1.99h-8l-2-2z"
        />
      </svg>
    </span>
  )
}

function DocPinIcon() {
  return <img className="docsVimixIcon" src="/icons/vimix/pin.svg" alt="" title="Pinned" aria-hidden />
}

/** Second line in the documents Description column for filed parent .eml (parsed on upload). */
function fileMailFromSubline(f: FileSummary): string | null {
  const n = f.source_mail_from_name?.trim()
  const e = f.source_mail_from_email?.trim()
  if (n && e) return `${n} · ${e}`
  if (e) return e
  if (n) return n
  return null
}

/** Same idea as case comment files: plain text or ``.txt`` name (opens in comment editor). */
function isCaseCommentStyleFile(f: FileSummary): boolean {
  const m = (f.mime_type || '').toLowerCase()
  const n = (f.original_filename || '').toLowerCase()
  return m.startsWith('text/plain') || n.endsWith('.txt')
}

/** List label: comment bodies are stored as ``… .txt``; hide the extension in the description column. */
function docsListDisplayFilename(f: FileSummary): string {
  const raw = f.original_filename || ''
  if (!isCaseCommentStyleFile(f)) return raw
  if (raw.length > 4 && raw.toLowerCase().endsWith('.txt')) return raw.slice(0, -4)
  return raw
}

function quotePortalStatusLabel(d: QuotePortalDeliverySummary): string {
  switch (d.status) {
    case 'pending':
      return `Awaiting ${d.contact_name}`
    case 'accepted':
      return `Accepted — ${d.contact_name}`
    case 'declined':
      return d.decline_reason ? `Declined — ${d.contact_name}` : `Declined — ${d.contact_name}`
    case 'superseded':
      return 'Superseded — re-send if needed'
    default:
      return d.status
  }
}

function docusignStatusLabel(d: DocusignSigningRequestOut): string {
  switch (d.status) {
    case 'pending':
      return 'DocuSign — awaiting signature'
    case 'completed':
      return 'DocuSign — signed'
    case 'declined':
      return 'DocuSign — declined'
    case 'voided':
      return 'DocuSign — voided'
    case 'expired':
      return 'DocuSign — expired'
    case 'error':
      return d.status_detail ? `DocuSign — error: ${d.status_detail}` : 'DocuSign — error'
    default:
      return `DocuSign — ${d.status}`
  }
}

export function DocsFileDescCell({ f, showPin }: { f: FileSummary; showPin: boolean }) {
  const sub = fileMailFromSubline(f)
  const quoteSub = f.quote_portal_delivery ? quotePortalStatusLabel(f.quote_portal_delivery) : null
  const formSub = f.portal_form_submission ? portalFormStatusLabel(f.portal_form_submission) : null
  const docusignSub = f.docusign_signing ? docusignStatusLabel(f.docusign_signing) : null
  const statusSub = quoteSub || formSub || docusignSub
  const mailRoot = isCaseMailRootFile(f)
  const displayName = f.parent_file_id ? `↳ ${docsListDisplayFilename(f)}` : docsListDisplayFilename(f)
  return (
    <div className={sub || statusSub ? 'docsDescWrapper docsDescWrapper--hasSub' : 'docsDescWrapper'}>
      <div className="docsDescCell">
        <div className={sub || statusSub ? 'docsDescRow docsDescRow--hasSub' : 'docsDescRow'}>
          {showPin ? (
            <span className="docsPinIcon">
              <DocPinIcon />
            </span>
          ) : null}
          <span className="docsTypeIcon" aria-hidden>
            {mailRoot ? (
              <DocMailIcon outbound={caseMailIconOutbound(f)} />
            ) : (
              <DocMimeIcon mime={f.mime_type} filename={f.original_filename} />
            )}
          </span>
          <div className="docsDescTextBlock">
            <span className="docsDescName">{displayName}</span>
            {sub ? <div className="docsDescSub muted">{sub}</div> : null}
            {quoteSub ? <div className="docsDescSub muted portalQuoteFileStatus">{quoteSub}</div> : null}
            {formSub && !quoteSub ? <div className="docsDescSub muted portalQuoteFileStatus">{formSub}</div> : null}
            {docusignSub && !quoteSub && !formSub ? (
              <div className="docsDescSub muted portalQuoteFileStatus">{docusignSub}</div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

export function DocsFolderDescCell({ name, shared = false }: { name: string; shared?: boolean }) {
  return (
    <div className="docsDescWrapper">
      <div className="docsDescCell">
        <div className="docsDescRow">
          <span className="docsTypeIcon" aria-hidden>
            <DocFolderIcon shared={shared} />
          </span>
          <div className="docsDescTextBlock">
            <span className="docsDescName">{name}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
