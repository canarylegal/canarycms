import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { applyAuthHeaders } from './api'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

export type CanarySignOverlayField = {
  id: string
  page: number
  x_pct: number
  y_pct: number
  w_pct: number
  h_pct: number
  label: string
  color?: string
  fill?: string
  selected?: boolean
  /** plain = printed name/date; script = unused when image present */
  textStyle?: 'plain' | 'script'
  previewText?: string | null
  previewImageB64?: string | null
}

export type SignatureStyle = {
  id: string
  label: string
  /** CSS / canvas font-family primary name */
  family: string
  /** Backend TTF filename under app/fonts */
  file: string
}

export const SIGNATURE_STYLES: SignatureStyle[] = [
  { id: 'great-vibes', label: 'Great Vibes', family: 'Great Vibes', file: 'GreatVibes-Regular.ttf' },
  { id: 'allura', label: 'Allura', family: 'Allura', file: 'Allura-Regular.ttf' },
  { id: 'sacramento', label: 'Sacramento', family: 'Sacramento', file: 'Sacramento-Regular.ttf' },
  { id: 'homemade-apple', label: 'Homemade Apple', family: 'Homemade Apple', file: 'HomemadeApple-Regular.ttf' },
  { id: 'satisfy', label: 'Satisfy', family: 'Satisfy', file: 'Satisfy-Regular.ttf' },
]

/** DocuSign-like distinct signer colours (border + translucent fill). */
export const CANARY_SIGN_SIGNER_PALETTE = [
  { border: '#2563eb', fill: 'rgba(37, 99, 235, 0.22)' },
  { border: '#ea580c', fill: 'rgba(234, 88, 12, 0.22)' },
  { border: '#7c3aed', fill: 'rgba(124, 58, 237, 0.22)' },
  { border: '#059669', fill: 'rgba(5, 150, 105, 0.22)' },
  { border: '#db2777', fill: 'rgba(219, 39, 119, 0.22)' },
  { border: '#0891b2', fill: 'rgba(8, 145, 178, 0.22)' },
]

export const CANARY_SIGN_SIGNER_COLORS = CANARY_SIGN_SIGNER_PALETTE.map((p) => p.border)

type PageView = {
  page: number
  width: number
  height: number
  dataUrl: string
}

type Props = {
  pdfUrl: string
  authToken: string
  overlays?: CanarySignOverlayField[]
  placing?: boolean
  resizable?: boolean
  onPageClick?: (info: { page: number; x_pct: number; y_pct: number }) => void
  onOverlayClick?: (id: string) => void
  onOverlayMove?: (id: string, info: { page: number; x_pct: number; y_pct: number }) => void
  onOverlayResize?: (
    id: string,
    info: { page: number; x_pct: number; y_pct: number; w_pct: number; h_pct: number },
  ) => void
  /** Fired when the document fails to load or render (friendly message). */
  onError?: (message: string) => void
  className?: string
}

type DragState = {
  mode: 'move' | 'resize'
  id: string
  page: number
  grabOffsetXPct: number
  grabOffsetYPct: number
  startX: number
  startY: number
  startW: number
  startH: number
  moved: boolean
}

const MIN_W = 6
const MIN_H = 3

function pctFromEvent(el: HTMLElement, clientX: number, clientY: number) {
  const rect = el.getBoundingClientRect()
  const x_pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
  const y_pct = Math.max(0, Math.min(100, ((clientY - rect.top) / rect.height) * 100))
  return { x_pct, y_pct }
}

function hexToFill(color: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(color.trim())
  if (!m) return 'rgba(8, 145, 178, 0.22)'
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, 0.22)`
}

export function CanarySignPdfDocument({
  pdfUrl,
  authToken,
  overlays = [],
  placing = false,
  resizable = false,
  onPageClick,
  onOverlayClick,
  onOverlayMove,
  onOverlayResize,
  onError,
  className,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<DragState | null>(null)
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError
  const [pages, setPages] = useState<PageView[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const [visiblePage, setVisiblePage] = useState(1)

  function reportError(message: string) {
    setErr(message)
    onErrorRef.current?.(message)
  }

  useEffect(() => {
    let cancelled = false
    setPages([])
    setErr(null)
    setLoading(true)
    setVisiblePage(1)

    void (async () => {
      try {
        const headers = new Headers()
        applyAuthHeaders(headers, authToken)
        const res = await fetch(pdfUrl, { headers })
        if (!res.ok) {
          if (!cancelled) {
            reportError(
              res.status === 503
                ? 'Could not convert this document for signing. Try a PDF, or check ONLYOFFICE is available.'
                : 'Could not load the document for preview. Check the file and try again.',
            )
          }
          return
        }
        const buf = await res.arrayBuffer()
        if (cancelled) return
        const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(buf) }).promise
        if (cancelled) return

        const hostWidth = hostRef.current?.clientWidth || 720
        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        const next: PageView[] = []
        for (let p = 1; p <= pdf.numPages; p += 1) {
          const page = await pdf.getPage(p)
          const base = page.getViewport({ scale: 1 })
          const screenScale = Math.min(1.15, (hostWidth - 8) / base.width)
          const cssScale = Math.max(0.5, screenScale)
          const viewport = page.getViewport({ scale: cssScale * dpr })
          const canvas = document.createElement('canvas')
          canvas.width = viewport.width
          canvas.height = viewport.height
          const ctx = canvas.getContext('2d')
          if (!ctx) {
            if (!cancelled) reportError('This browser cannot display the PDF preview.')
            return
          }
          await page.render({ canvasContext: ctx, viewport }).promise
          if (cancelled) return
          next.push({
            page: p,
            width: viewport.width / dpr,
            height: viewport.height / dpr,
            dataUrl: canvas.toDataURL('image/png'),
          })
        }
        if (!cancelled) {
          if (!next.length) {
            reportError('This document has no pages to display.')
          } else {
            setPages(next)
          }
        }
      } catch {
        if (!cancelled) reportError('Could not display this document. Try again, or use a PDF.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- retryKey forces reload
  }, [pdfUrl, authToken, retryKey])

  useEffect(() => {
    if (pages.length <= 1) return
    const root = hostRef.current
    if (!root) return
    const ratios = new Map<number, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.page || 0)
          if (!page) continue
          ratios.set(page, entry.isIntersecting ? entry.intersectionRatio : 0)
        }
        let best = 1
        let bestRatio = -1
        for (const [page, ratio] of ratios) {
          if (ratio > bestRatio) {
            bestRatio = ratio
            best = page
          }
        }
        if (bestRatio >= 0) setVisiblePage(best)
      },
      { root: null, threshold: [0.15, 0.35, 0.55, 0.75] },
    )
    for (const el of root.querySelectorAll('.canarySignPdfPage')) {
      observer.observe(el)
    }
    return () => observer.disconnect()
  }, [pages])

  useEffect(() => {
    if (!onOverlayMove && !onOverlayResize) return

    function onPointerMove(e: PointerEvent) {
      const drag = dragRef.current
      if (!drag) return
      const pageEl = document.querySelector(`.canarySignPdfPage[data-page="${drag.page}"]`) as HTMLElement | null
      if (!pageEl) return
      const { x_pct, y_pct } = pctFromEvent(pageEl, e.clientX, e.clientY)
      drag.moved = true

      if (drag.mode === 'resize' && onOverlayResize) {
        const w = Math.max(MIN_W, Math.min(100 - drag.startX, x_pct - drag.startX))
        const h = Math.max(MIN_H, Math.min(100 - drag.startY, y_pct - drag.startY))
        onOverlayResize(drag.id, {
          page: drag.page,
          x_pct: drag.startX,
          y_pct: drag.startY,
          w_pct: w,
          h_pct: h,
        })
        return
      }

      if (drag.mode === 'move' && onOverlayMove) {
        const nextX = Math.max(0, Math.min(100 - drag.startW, x_pct - drag.grabOffsetXPct))
        const nextY = Math.max(0, Math.min(100 - drag.startH, y_pct - drag.grabOffsetYPct))
        onOverlayMove(drag.id, { page: drag.page, x_pct: nextX, y_pct: nextY })
      }
    }

    function onPointerUp() {
      const drag = dragRef.current
      dragRef.current = null
      setDraggingId(null)
      if (drag && !drag.moved) onOverlayClick?.(drag.id)
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
    }
  }, [onOverlayMove, onOverlayResize, onOverlayClick])

  function handlePageClick(e: React.MouseEvent<HTMLDivElement>, page: number) {
    if (!onPageClick) return
    if (dragRef.current?.moved) return
    if ((e.target as HTMLElement).closest('.canarySignFieldOverlay')) return
    const { x_pct, y_pct } = pctFromEvent(e.currentTarget, e.clientX, e.clientY)
    onPageClick({ page, x_pct, y_pct })
  }

  function startMove(e: React.PointerEvent<HTMLButtonElement>, o: CanarySignOverlayField) {
    if (!onOverlayMove) {
      e.stopPropagation()
      onOverlayClick?.(o.id)
      return
    }
    e.preventDefault()
    e.stopPropagation()
    const pageEl = e.currentTarget.closest('.canarySignPdfPage') as HTMLElement | null
    if (!pageEl) return
    const { x_pct, y_pct } = pctFromEvent(pageEl, e.clientX, e.clientY)
    dragRef.current = {
      mode: 'move',
      id: o.id,
      page: o.page,
      grabOffsetXPct: x_pct - o.x_pct,
      grabOffsetYPct: y_pct - o.y_pct,
      startX: o.x_pct,
      startY: o.y_pct,
      startW: o.w_pct,
      startH: o.h_pct,
      moved: false,
    }
    setDraggingId(o.id)
    onOverlayClick?.(o.id)
  }

  function startResize(e: React.PointerEvent<HTMLSpanElement>, o: CanarySignOverlayField) {
    if (!onOverlayResize) return
    e.preventDefault()
    e.stopPropagation()
    dragRef.current = {
      mode: 'resize',
      id: o.id,
      page: o.page,
      grabOffsetXPct: 0,
      grabOffsetYPct: 0,
      startX: o.x_pct,
      startY: o.y_pct,
      startW: o.w_pct,
      startH: o.h_pct,
      moved: false,
    }
    setDraggingId(o.id)
    onOverlayClick?.(o.id)
  }

  const numPages = pages.length

  return (
    <div
      ref={hostRef}
      className={className}
      style={{ cursor: placing ? 'crosshair' : undefined, minHeight: 120, position: 'relative' }}
    >
      {numPages > 1 ? (
        <div
          className="muted"
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 2,
            alignSelf: 'flex-start',
            display: 'inline-block',
            marginBottom: 8,
            padding: '4px 10px',
            fontSize: 12,
            background: 'rgba(255, 255, 255, 0.92)',
            border: '1px solid #e2e8f0',
            borderRadius: 6,
            boxShadow: '0 1px 2px rgba(15, 23, 42, 0.06)',
          }}
          aria-live="polite"
        >
          Page {visiblePage} of {numPages}
        </div>
      ) : null}
      {loading ? <div className="muted">Loading document preview…</div> : null}
      {err ? (
        <div className="stack" style={{ gap: 8 }}>
          <div className="error">{err}</div>
          <div>
            <button type="button" className="btn" onClick={() => setRetryKey((k) => k + 1)}>
              Retry
            </button>
          </div>
        </div>
      ) : null}
      {!loading && !err && numPages === 0 ? (
        <div className="muted">No pages to show for this document.</div>
      ) : null}
      {pages.map((p) => (
        <div
          key={p.page}
          className="canarySignPdfPage"
          data-page={String(p.page)}
          onClick={(e) => handlePageClick(e, p.page)}
          style={{
            position: 'relative',
            margin: '0 auto 12px',
            width: p.width,
            height: p.height,
          }}
        >
          <img
            src={p.dataUrl}
            alt={`Page ${p.page}`}
            draggable={false}
            style={{
              display: 'block',
              width: p.width,
              height: p.height,
              boxShadow: '0 1px 4px rgba(15, 23, 42, 0.12)',
              borderRadius: 4,
              pointerEvents: 'none',
              userSelect: 'none',
            }}
          />
          {overlays
            .filter((o) => o.page === p.page)
            .map((o) => {
              const border = o.color || '#2563eb'
              const fill = o.fill || hexToFill(border)
              const hasContent = Boolean(o.previewImageB64 || o.previewText)
              return (
                <button
                  key={o.id}
                  type="button"
                  className={`canarySignFieldOverlay${o.selected ? ' canarySignFieldOverlay--selected' : ''}${
                    draggingId === o.id ? ' canarySignFieldOverlay--dragging' : ''
                  }`}
                  style={{
                    left: `${o.x_pct}%`,
                    top: `${o.y_pct}%`,
                    width: `${o.w_pct}%`,
                    height: `${o.h_pct}%`,
                    borderColor: border,
                    background: hasContent ? 'rgba(255,255,255,0.96)' : fill,
                    boxShadow: o.selected ? `0 0 0 2px ${border}` : undefined,
                    cursor: onOverlayMove ? 'grab' : 'pointer',
                  }}
                  title={onOverlayMove ? `${o.label} — drag to move${resizable ? ', corner to resize' : ''}` : o.label}
                  onPointerDown={(e) => startMove(e, o)}
                  onClick={(e) => e.stopPropagation()}
                >
                  {o.previewImageB64 ? (
                    <img
                      key={`${o.id}-${o.previewImageB64.slice(0, 48)}`}
                      src={`data:image/png;base64,${o.previewImageB64}`}
                      alt=""
                      style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }}
                    />
                  ) : o.previewText ? (
                    <span
                      className={`canarySignFieldOverlay__value${
                        o.textStyle === 'script' ? ' canarySignFieldOverlay__value--script' : ' canarySignFieldOverlay__value--plain'
                      }`}
                    >
                      {o.previewText}
                    </span>
                  ) : (
                    <span className="canarySignFieldOverlay__label">{o.label}</span>
                  )}
                  {resizable && o.selected && onOverlayResize ? (
                    <span
                      className="canarySignFieldOverlay__resize"
                      onPointerDown={(e) => startResize(e, o)}
                      title="Resize"
                    />
                  ) : null}
                </button>
              )
            })}
        </div>
      ))}
    </div>
  )
}

export function defaultFieldSize(fieldType: string): { w_pct: number; h_pct: number } {
  switch (fieldType) {
    case 'signature':
      return { w_pct: 32, h_pct: 9 }
    case 'initials':
      return { w_pct: 12, h_pct: 6 }
    case 'printed_name':
      return { w_pct: 30, h_pct: 6 }
    case 'date':
      return { w_pct: 24, h_pct: 6 }
    case 'checkbox':
      return { w_pct: 5, h_pct: 5 }
    default:
      return { w_pct: 25, h_pct: 5 }
  }
}

export function fieldTypeLabel(fieldType: string): string {
  switch (fieldType) {
    case 'signature':
      return 'Signature'
    case 'initials':
      return 'Initials'
    case 'printed_name':
      return 'Printed name'
    case 'date':
      return 'Date'
    case 'checkbox':
      return 'Checkbox'
    default:
      return fieldType
  }
}

export function formatUkDate(d = new Date()): string {
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

/** Render a typed signature in the chosen script style to PNG base64 (no data: prefix). */
export async function renderTypedSignaturePng(
  name: string,
  opts?: { width?: number; height?: number; styleIndex?: number },
): Promise<string> {
  const text = name.trim()
  if (!text) throw new Error('Name is required')
  const width = opts?.width ?? 900
  const height = opts?.height ?? 220
  const style = SIGNATURE_STYLES[(opts?.styleIndex ?? 0) % SIGNATURE_STYLES.length]
  const fontUrl = `/canary-fonts/${style.file}`
  try {
    // Explicit FontFace load — CSS @font-face alone is unreliable for canvas measure/draw.
    const face = new FontFace(style.family, `url(${fontUrl})`)
    await face.load()
    document.fonts.add(face)
    await document.fonts.load(`96px "${style.family}"`)
    await document.fonts.ready
  } catch {
    // Fall through; canvas may still use a loaded CSS face or generic cursive
  }
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas unavailable')
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0f172a'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  let size = Math.min(110, Math.floor(height * 0.72))
  // Do not fall back across signature families — that made every style look identical.
  ctx.font = `${size}px "${style.family}", cursive`
  while (size > 22 && ctx.measureText(text).width > width - 36) {
    size -= 3
    ctx.font = `${size}px "${style.family}", cursive`
  }
  ctx.fillText(text, width / 2, height / 2)
  return canvas.toDataURL('image/png').replace(/^data:image\/png;base64,/, '')
}
