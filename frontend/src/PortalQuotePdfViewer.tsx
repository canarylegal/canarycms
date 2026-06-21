import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { applyAuthHeaders } from './api'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

type Props = {
  fetchUrl: string
  portalToken: string
  title?: string
}

export function PortalQuotePdfViewer({ fetchUrl, portalToken, title = 'Quote preview' }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    let cancelled = false
    host.replaceChildren()
    setErr(null)
    setLoading(true)

    void (async () => {
      try {
        const headers = new Headers()
        applyAuthHeaders(headers, portalToken)
        const res = await fetch(fetchUrl, { headers })
        if (!res.ok) {
          if (!cancelled) setErr('Could not load quote preview.')
          return
        }
        const buf = await res.arrayBuffer()
        if (cancelled) return

        const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(buf) }).promise
        if (cancelled) return

        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        for (let p = 1; p <= pdf.numPages; p += 1) {
          const page = await pdf.getPage(p)
          const base = page.getViewport({ scale: 1 })
          const screenScale = Math.min(1.15, (host.clientWidth - 8) / base.width)
          const viewport = page.getViewport({ scale: Math.max(0.5, screenScale) * dpr })

          const canvas = document.createElement('canvas')
          canvas.className = 'portalQuotePdfPage'
          canvas.style.display = 'block'
          canvas.style.margin = '0 auto 12px'
          canvas.style.width = `${viewport.width / dpr}px`
          canvas.style.height = `${viewport.height / dpr}px`
          canvas.style.boxShadow = '0 1px 4px rgba(15, 23, 42, 0.12)'
          canvas.style.borderRadius = '4px'

          const ctx = canvas.getContext('2d')
          if (!ctx) {
            if (!cancelled) setErr('Canvas is unavailable in this browser.')
            return
          }
          canvas.width = viewport.width
          canvas.height = viewport.height

          await page.render({ canvasContext: ctx, viewport }).promise
          if (cancelled) return
          host.appendChild(canvas)
        }
      } catch {
        if (!cancelled) setErr('Could not render quote preview.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [fetchUrl, portalToken])

  return (
    <div className="portalQuotePdfViewer" aria-label={title}>
      {loading ? <div className="muted portalQuotePdfStatus">Loading preview…</div> : null}
      {err ? <div className="error portalQuotePdfStatus">{err}</div> : null}
      <div ref={hostRef} className="portalQuotePdfPages" />
    </div>
  )
}
