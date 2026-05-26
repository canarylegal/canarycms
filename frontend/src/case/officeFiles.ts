import type { FileSummary } from '../types'

/** Local file picked or dropped in the browser (before upload). */
export function isEmlLikeUploadFile(file: File): boolean {
  const name = (file.name || '').toLowerCase()
  const type = (file.type || '').toLowerCase()
  return name.endsWith('.eml') || type.includes('message/rfc822') || type.includes('rfc822')
}

/** E-mail stored as .eml / RFC822 — must match backend ``_row_is_eml_like``. */
export function isEmlLikeFileSummary(f: FileSummary): boolean {
  if ((f.outlook_graph_message_id || '').trim() || (f.outlook_web_link || '').trim()) return true
  const name = (f.original_filename || '').toLowerCase()
  const m = (f.mime_type || '').toLowerCase()
  return name.endsWith('.eml') || m.includes('message/rfc822') || m.includes('rfc822')
}

function openPdfInOnlyOffice(): boolean {
  const v = (import.meta.env.VITE_CANARY_OPEN_PDF_IN_ONLYOFFICE as string | undefined)?.trim().toLowerCase()
  return v === '1' || v === 'true' || v === 'yes' || v === 'on'
}

/**
 * Word / Excel / PowerPoint / ODF / RTF: open in ONLYOFFICE.
 * PDFs too when ``VITE_CANARY_OPEN_PDF_IN_ONLYOFFICE`` is set (deployment opt-in).
 */
export function isOfficeLikeFile(f: FileSummary): boolean {
  const name = f.original_filename.toLowerCase()
  const dot = name.lastIndexOf('.')
  const ext = dot >= 0 ? name.slice(dot + 1) : ''
  const m = (f.mime_type || '').toLowerCase()
  if (openPdfInOnlyOffice() && (ext === 'pdf' || m === 'application/pdf' || m.endsWith('/pdf'))) {
    return true
  }
  const officeExt = new Set([
    'doc',
    'docx',
    'dot',
    'dotx',
    'xls',
    'xlsx',
    'xlsm',
    'xlsb',
    'ppt',
    'pptx',
    'pps',
    'ppsx',
    'odt',
    'ods',
    'odp',
    'rtf',
  ])
  if (officeExt.has(ext)) return true
  return (
    m.includes('wordprocessing') ||
    m.includes('spreadsheetml') ||
    m.includes('presentationml') ||
    m.includes('msword') ||
    m.includes('ms-powerpoint') ||
    m.includes('ms-excel') ||
    m === 'application/vnd.ms-excel' ||
    m === 'application/vnd.ms-powerpoint'
  )
}
