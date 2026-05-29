import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import DOMPurify from 'dompurify'
import type { FileSummary } from '../types'

/**
 * Square dialog size in px from the real window (not CSS vmin alone — avoids cascade / iframe quirks).
 * ~70% of the shorter edge, clamped so the box stays on screen.
 */
function computeEmlPreviewSidePx(): number {
  if (typeof window === 'undefined') return 640
  const w = window.innerWidth
  const h = window.innerHeight
  const short = Math.min(w, h)
  const target = Math.round(short * 0.7)
  const maxAllowed = Math.floor(short * 0.92)
  return Math.max(280, Math.min(target, maxAllowed))
}

export type EmlPreviewData = {
  subject: string
  from: string
  to: string
  cc: string
  date: string
  /** Plain-text fallback (and accessibility when HTML is shown). */
  bodyText: string
  /** Raw HTML from the message when available; sanitized before display. */
  bodyHtml?: string
}

function normalizeNewlines(s: string): string {
  return s.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

/** Parse RFC822 header block into lower-case keys. */
function parseHeaderBlock(block: string): Record<string, string> {
  const lines = block.split('\n')
  const out: Record<string, string> = {}
  let curKey: string | null = null
  for (const line of lines) {
    if (line.startsWith(' ') || line.startsWith('\t')) {
      if (curKey) out[curKey] += ` ${line.trim()}`
      continue
    }
    const m = /^([^:]+):\s*(.*)$/.exec(line)
    if (!m) continue
    curKey = m[1].trim().toLowerCase()
    out[curKey] = m[2].trim()
  }
  return out
}

function decodeQuotedPrintableToBytes(input: string): Uint8Array {
  const t = input.replace(/=\r?\n/g, '')
  const bytes: number[] = []
  for (let i = 0; i < t.length; i++) {
    const ch = t[i]
    if (ch === '=' && i + 2 < t.length) {
      const hex = t.slice(i + 1, i + 3)
      if (/^[0-9A-Fa-f]{2}$/.test(hex)) {
        bytes.push(Number.parseInt(hex, 16))
        i += 2
        continue
      }
    }
    bytes.push(t.charCodeAt(i) & 0xff)
  }
  return new Uint8Array(bytes)
}

function normalizeCharset(charset: string): string {
  const c = charset.trim().toLowerCase()
  if (!c) return 'utf-8'
  if (c === 'utf8' || c === 'utf-8') return 'utf-8'
  if (c === 'us-ascii' || c === 'ascii') return 'utf-8'
  if (c === 'iso-8859-1' || c === 'iso8859-1' || c === 'latin1' || c === 'latin-1' || c === 'iso_8859-1') {
    return 'iso-8859-1'
  }
  if (c === 'windows-1252' || c === 'cp1252' || c === 'x-cp1252') return 'windows-1252'
  return charset.trim()
}

function extractCharset(contentType: string): string {
  const m = /charset\s*=\s*("?)([^";\s]+)\1/i.exec(contentType || '')
  if (!m) return 'utf-8'
  return normalizeCharset(m[2])
}

function decodeBytesWithCharset(bytes: Uint8Array, charset: string): string {
  const normalized = normalizeCharset(charset)
  try {
    return new TextDecoder(normalized, { fatal: false }).decode(bytes)
  } catch {
    try {
      return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
    } catch {
      return new TextDecoder('iso-8859-1', { fatal: false }).decode(bytes)
    }
  }
}

function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/\s+/g, '')
  const bin = atob(clean)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

function latin1Bytes(s: string): Uint8Array {
  const out = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff
  return out
}

function extractBoundary(contentType: string): string | null {
  const m = /boundary\s*=\s*("?)([^";\s]+)\1/i.exec(contentType)
  return m ? m[2].trim() : null
}

function htmlToPlainText(html: string): string {
  if (typeof document === 'undefined') return html.replace(/<[^>]+>/g, ' ')
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return doc.body?.textContent?.replace(/\s+\n/g, '\n').trim() ?? ''
  } catch {
    return html.replace(/<[^>]+>/g, ' ')
  }
}

function decodeBodyPayload(headers: Record<string, string>, body: string): string {
  const enc = (headers['content-transfer-encoding'] || '8bit').toLowerCase()
  const charset = extractCharset(headers['content-type'] || '')

  let bytes: Uint8Array
  if (enc.includes('base64')) {
    try {
      bytes = base64ToBytes(body)
    } catch {
      return body
    }
  } else if (enc.includes('quoted-printable')) {
    bytes = decodeQuotedPrintableToBytes(body)
  } else {
    bytes = latin1Bytes(body)
  }
  return decodeBytesWithCharset(bytes, charset)
}

function decodeRfc2047Q(payload: string): Uint8Array {
  const bytes: number[] = []
  for (let i = 0; i < payload.length; i++) {
    const ch = payload[i]
    if (ch === '_') {
      bytes.push(0x20)
    } else if (ch === '=' && i + 2 < payload.length) {
      const hex = payload.slice(i + 1, i + 3)
      if (/^[0-9A-Fa-f]{2}$/.test(hex)) {
        bytes.push(Number.parseInt(hex, 16))
        i += 2
        continue
      }
      bytes.push(ch.charCodeAt(0) & 0xff)
    } else {
      bytes.push(ch.charCodeAt(0) & 0xff)
    }
  }
  return new Uint8Array(bytes)
}

/** Decode RFC 2047 encoded-words in header values (Subject, From, etc.). */
function decodeMimeHeaderValue(value: string): string {
  if (!value || !/=\?/.test(value)) return value
  const normalized = value.replace(/(\?=)\s+(=\?)/g, '$1$2')
  return normalized.replace(/=\?([^?]+)\?([BbQq])\?([^?]*)\?=/g, (_, charset, enc, text) => {
    const cs = extractCharset(`text/plain; charset=${charset}`)
    try {
      const bytes = enc.toUpperCase() === 'B' ? base64ToBytes(text) : decodeRfc2047Q(text)
      return decodeBytesWithCharset(bytes, cs)
    } catch {
      return text
    }
  })
}

type Collected = { plain: string[]; htmlRaw: string[] }

/** Max raw .eml size for preview parse (avoids freezing the tab on huge MIME trees). */
export const MAX_EML_PREVIEW_CHARS = 2_000_000

/** HTML passed to DOMPurify for preview (sanitization can be superlinear on pathological HTML). */
const MAX_HTML_SANITIZE_CHARS = 400_000

/**
 * Split a multipart body on RFC 2046 boundaries in linear time.
 * The previous RegExp-based split could take effectively forever on large or degenerate bodies.
 */
function splitMultipartSegmentsLinear(norm: string, boundaryRaw: string): string[] {
  const b = boundaryRaw.replace(/^["']|["']$/g, '').trim()
  if (!b) return []
  const marker = `\n--${b}`
  const rawParts = norm.split(marker)
  const out: string[] = []
  for (let i = 1; i < rawParts.length; i++) {
    let p = rawParts[i]
    if (p.startsWith('--')) break
    if (p.startsWith('\n')) p = p.slice(1)
    if (p === '--') break
    if (p.endsWith('--')) p = p.slice(0, -2)
    p = p.replace(/\s+$/, '')
    if (p.length) out.push(p)
  }
  return out
}

function collectParts(headers: Record<string, string>, body: string, depth: number, into: Collected): void {
  if (depth > 12) return
  const ct = (headers['content-type'] || '').toLowerCase()

  if (ct.includes('multipart/')) {
    const boundary = extractBoundary(headers['content-type'] || '')
    if (!boundary) return
    const norm = normalizeNewlines(body)
    const segments = splitMultipartSegmentsLinear(norm, boundary)
    const isAlternative = ct.includes('multipart/alternative')
    const ordered = isAlternative ? [...segments].reverse() : segments
    for (const seg of ordered) {
      const parsed = splitHeadersBody(seg)
      if (!parsed) continue
      collectParts(parsed.headers, parsed.payload, depth + 1, into)
      if (isAlternative && (into.htmlRaw.length > 0 || into.plain.length > 0)) {
        break
      }
    }
    return
  }

  if (!isBodyTextPart(ct, headers)) return

  const decoded = decodeBodyPayload(headers, body)
  if (ct.includes('text/html')) {
    if (isLikelyHtml(decoded)) into.htmlRaw.push(decoded)
  } else if (ct.includes('text/plain')) {
    const trimmed = decoded.trim()
    if (isLikelyReadableText(trimmed)) into.plain.push(trimmed)
  }
}

function splitHeadersBody(segment: string): { headers: Record<string, string>; payload: string } | null {
  const norm = normalizeNewlines(segment.trim())
  if (!norm) return null
  const sep = norm.indexOf('\n\n')
  if (sep === -1) return null
  return {
    headers: parseHeaderBlock(norm.slice(0, sep)),
    payload: norm.slice(sep + 2),
  }
}

function isBodyTextPart(contentType: string, headers: Record<string, string>): boolean {
  const ct = contentType.toLowerCase()
  if (ct.includes('multipart/')) return false
  const disp = (headers['content-disposition'] || '').toLowerCase()
  if (disp.includes('attachment') && !disp.includes('inline')) return false
  return ct.includes('text/html') || ct.includes('text/plain')
}

/** Reject decoded binary blobs mis-labelled or mistaken for plain text (e.g. inline PNG signatures). */
function isLikelyReadableText(s: string): boolean {
  const t = s.trim()
  if (!t) return false
  if (t.startsWith('\x89PNG') || t.startsWith('PNG\r') || t.includes('IHDR')) return false
  if (t.startsWith('\xff\xd8\xff') || t.startsWith('GIF8')) return false
  const sample = t.slice(0, 12_000)
  let bad = 0
  for (let i = 0; i < sample.length; i++) {
    const c = sample.charCodeAt(i)
    if (c === 0) return false
    if (c === 9 || c === 10 || c === 13) continue
    if (c < 32 || c === 127) bad++
  }
  return bad / sample.length < 0.03
}

function isLikelyHtml(s: string): boolean {
  const t = s.trim().slice(0, 4000).toLowerCase()
  return (
    t.includes('<html') ||
    t.includes('<!doctype') ||
    t.includes('<body') ||
    /<\s*(div|p|table|span|br|style)\b/.test(t)
  )
}

function pickBestHtml(parts: string[]): string | undefined {
  const candidates = parts.filter((p) => isLikelyHtml(p))
  if (!candidates.length) return undefined
  return candidates.sort((a, b) => b.length - a.length)[0]
}

function pickBestPlain(parts: string[]): string | undefined {
  const candidates = parts.filter((p) => isLikelyReadableText(p))
  if (!candidates.length) return undefined
  return candidates.sort((a, b) => b.length - a.length)[0]
}

function headerDisplay(headers: Record<string, string>, key: string): string {
  return decodeMimeHeaderValue((headers[key.toLowerCase()] ?? '').trim())
}

let domPurifyLinkHookAdded = false

function sanitizeEmlHtml(html: string): string {
  if (typeof window === 'undefined' || !html.trim()) return ''
  if (html.length > MAX_HTML_SANITIZE_CHARS) {
    return '<p class="muted">HTML body is too large to preview safely. Use <strong>Download</strong> or <strong>Open</strong>.</p>'
  }
  if (!domPurifyLinkHookAdded) {
    DOMPurify.addHook('afterSanitizeAttributes', (node) => {
      if (node.nodeType !== Node.ELEMENT_NODE || node.nodeName !== 'A') return
      const el = node as Element
      if (el.hasAttribute('href')) {
        el.setAttribute('target', '_blank')
        el.setAttribute('rel', 'noopener noreferrer')
      }
    })
    domPurifyLinkHookAdded = true
  }
  /* Default allow-list keeps most mail tags; allow <style> blocks used by HTML e-mail. */
  return DOMPurify.sanitize(html, { ADD_TAGS: ['style'], ADD_ATTR: ['target', 'rel'] })
}

function wrapEmailHtmlDocument(safeBodyHtml: string): string {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><base target="_blank"><style>
body{margin:0;padding:16px 18px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;color:#111827;background:#fff;word-wrap:break-word;overflow-wrap:break-word;}
img{max-width:100%;height:auto;}
table{max-width:100%;border-collapse:collapse;}
a{color:#2563eb;}
blockquote{margin:0.5em 0 0.5em 0;padding-left:12px;border-left:3px solid #d1d5db;color:#374151;}
pre{white-space:pre-wrap;word-wrap:break-word;}
</style></head><body>${safeBodyHtml}</body></html>`
}

/**
 * Best-effort parse of .eml / RFC822 for in-app preview (not a full MIME stack).
 */
export function parseEmlForPreview(raw: string): EmlPreviewData {
  let truncated = false
  let text = normalizeNewlines(raw)
  if (text.length > MAX_EML_PREVIEW_CHARS) {
    truncated = true
    text = text.slice(0, MAX_EML_PREVIEW_CHARS)
  }
  const splitAt = text.indexOf('\n\n')
  if (splitAt === -1) {
    return {
      subject: '',
      from: '',
      to: '',
      cc: '',
      date: '',
      bodyText: text.trim(),
    }
  }
  const topHeaders = parseHeaderBlock(text.slice(0, splitAt))
  const body = text.slice(splitAt + 2)

  const subject = headerDisplay(topHeaders, 'subject')
  const from = headerDisplay(topHeaders, 'from')
  const to = headerDisplay(topHeaders, 'to')
  const cc = headerDisplay(topHeaders, 'cc')
  const date = headerDisplay(topHeaders, 'date')

  const into: Collected = { plain: [], htmlRaw: [] }
  collectParts(topHeaders, body, 0, into)

  let bodyHtml: string | undefined
  let bodyText = ''

  bodyHtml = pickBestHtml(into.htmlRaw)
  if (bodyHtml) {
    bodyText = htmlToPlainText(bodyHtml)
  }
  const bestPlain = pickBestPlain(into.plain)
  if (bestPlain && !bodyHtml) {
    bodyText = bestPlain
  } else if (bestPlain && bodyHtml && !bodyText.trim()) {
    bodyText = bestPlain
  }

  if (!bodyHtml && !bodyText) {
    const dec = decodeBodyPayload(topHeaders, body)
    const ct = (topHeaders['content-type'] || '').toLowerCase()
    if (ct.includes('text/html') && isLikelyHtml(dec)) {
      bodyHtml = dec.trim()
      bodyText = htmlToPlainText(bodyHtml)
    } else if (ct.includes('text/plain') && isLikelyReadableText(dec)) {
      bodyText = dec.trim()
    }
  }

  if (!bodyHtml && !bodyText) {
    const dec = decodeBodyPayload(topHeaders, body).trim()
    if (isLikelyReadableText(dec)) bodyText = dec
    else if (isLikelyHtml(dec)) {
      bodyHtml = dec
      bodyText = htmlToPlainText(dec)
    }
  }

  if (!bodyHtml && !bodyText) {
    bodyText = '(No readable message body in preview. Use Open or Download for the full e-mail.)'
  }

  if (truncated) {
    const note = '[Preview truncated — file is very large. Use Download for the full message.]\n\n'
    bodyText = bodyHtml ? bodyText : note + bodyText
    if (bodyHtml) {
      bodyHtml = `<p class="muted">${note.trim()}</p>${bodyHtml}`
    }
  }

  return {
    subject,
    from,
    to,
    cc,
    date,
    bodyText,
    ...(bodyHtml ? { bodyHtml } : {}),
  }
}

type EmlPreviewModalProps = {
  file: FileSummary
  data: EmlPreviewData | null
  loading: boolean
  error: string | null
  onClose: () => void
  onOpenExternal: () => void
}

export function EmlPreviewModal({ file, data, loading, error, onClose, onOpenExternal }: EmlPreviewModalProps) {
  const [sidePx, setSidePx] = useState(() => computeEmlPreviewSidePx())

  useEffect(() => {
    function onResize() {
      setSidePx(computeEmlPreviewSidePx())
    }
    onResize()
    window.addEventListener('resize', onResize)
    window.visualViewport?.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      window.visualViewport?.removeEventListener('resize', onResize)
    }
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const modalFrameStyle = useMemo(
    () =>
      ({
        width: sidePx,
        height: sidePx,
        maxWidth: 'min(92vw, 92vh)',
        maxHeight: 'min(92vw, 92vh)',
        boxSizing: 'border-box',
      }) as const,
    [sidePx],
  )

  const safeHtml = useMemo(() => {
    if (!data?.bodyHtml?.trim()) return ''
    return sanitizeEmlHtml(data.bodyHtml)
  }, [data?.bodyHtml])

  const iframeDoc = useMemo(() => (safeHtml ? wrapEmailHtmlDocument(safeHtml) : ''), [safeHtml])

  const title = data?.subject?.trim() || file.original_filename || 'E-mail preview'

  const overlay = (
    <div
      className="modalOverlay emlPreviewOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="eml-preview-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="card emlPreviewModal" style={modalFrameStyle} onClick={(e) => e.stopPropagation()}>
        <div className="emlPreviewModalHeader">
          <h2 id="eml-preview-title" className="emlPreviewModalTitle">
            {title}
          </h2>
        </div>

        {loading ? <div className="muted emlPreviewModalPad">Loading preview…</div> : null}
        {error ? (
          <div className="emlPreviewModalPad" style={{ color: 'var(--danger, #b91c1c)' }} role="alert">
            {error}
          </div>
        ) : null}

        {!loading && !error && data ? (
          <div className="emlPreviewModalMain">
            <div className="emlPreviewHeaderStrip">
              {data.from ? (
                <div className="emlPreviewHeaderFrom">
                  <span className="emlPreviewHeaderLabel">From</span>
                  <span className="emlPreviewHeaderValue">{data.from}</span>
                </div>
              ) : null}
              <dl className="emlPreviewMeta">
                {data.to ? (
                  <>
                    <dt>To</dt>
                    <dd>{data.to}</dd>
                  </>
                ) : null}
                {data.cc ? (
                  <>
                    <dt>Cc</dt>
                    <dd>{data.cc}</dd>
                  </>
                ) : null}
                {data.date ? (
                  <>
                    <dt>Date</dt>
                    <dd>{data.date}</dd>
                  </>
                ) : null}
              </dl>
            </div>
            <div className={`emlPreviewBodyWrap${iframeDoc ? ' emlPreviewBodyWrapHtml' : ''}`}>
              {iframeDoc ? (
                <iframe
                  className="emlPreviewHtmlFrame"
                  title="E-mail body"
                  sandbox="allow-popups allow-popups-to-escape-sandbox"
                  srcDoc={iframeDoc}
                />
              ) : (
                <pre className="emlPreviewBody">{data.bodyText || '—'}</pre>
              )}
            </div>
          </div>
        ) : null}

        <div className="emlPreviewModalFooter">
          <button type="button" className="btn primary" onClick={onOpenExternal} disabled={loading}>
            Open
          </button>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )

  /* Portal: avoid .caseShell overflow:hidden and nested layout shrinking a position:fixed overlay. */
  if (typeof document !== 'undefined') {
    return createPortal(overlay, document.body)
  }
  return overlay
}
