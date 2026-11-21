import {useLayoutEffect, useMemo, useRef, useState, type ReactNode} from 'react'
import {documentOffsets, documentWindow} from './documentWindow'

const WINDOW_THRESHOLD = 250

/** Preserve natural row markup/heights; only long lists omit off-screen DOM nodes. */
export function WindowedDocumentRows({keys, focusKey, renderRow}: {
  keys: string[]; focusKey: string | null; renderRow: (index: number) => ReactNode
}) {
  const body = useRef<HTMLDivElement>(null)
  const [heights, setHeights] = useState<ReadonlyMap<string, number>>(new Map())
  const [estimate, setEstimate] = useState(52)
  const [viewport, setViewport] = useState({top: 0, height: 600, offset: 0, header: 0})
  const offsets = useMemo(() => documentOffsets(keys, heights, estimate), [keys, heights, estimate])
  const enabled = keys.length > WINDOW_THRESHOLD
  const window = enabled ? documentWindow(offsets, viewport.top - viewport.offset, viewport.height) :
    {start: 0, end: keys.length, before: 0, after: 0}
  const layout = useRef({keys, offsets, enabled})
  useLayoutEffect(() => { layout.current = {keys, offsets, enabled} }, [keys, offsets, enabled])

  useLayoutEffect(() => {
    const container = body.current
    const host = container?.closest<HTMLElement>('.caseDocsScroll')
    if (!container || !host) return
    let frame = 0
    let previousWidth = container.clientWidth
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        // DOM rectangles include the app's CSS zoom; scrollTop/offsetHeight do not.
        const scale = host.getBoundingClientRect().height / host.offsetHeight || 1
        const offset = (container.getBoundingClientRect().top - host.getBoundingClientRect().top) / scale + host.scrollTop - host.clientTop
        const widthChanged = previousWidth !== container.clientWidth
        previousWidth = container.clientWidth
        const rows = Array.from(container.querySelectorAll<HTMLElement>(':scope > [data-doc-key]'))
        const minimum = rows[0] ? parseFloat(getComputedStyle(rows[0]).minHeight) : NaN
        if (minimum > 0) setEstimate(minimum)
        const measured = rows.map(row => [row.dataset.docKey!, Math.round(row.getBoundingClientRect().height / scale * 1000) / 1000] as const)
        setHeights(current => {
          const valid = new Set(layout.current.keys)
          const next = new Map(widthChanged ? [] : [...current].filter(([key]) => valid.has(key)))
          for (const [key, value] of measured) if (value > 0) next.set(key, value)
          if (next.size === current.size && [...next].every(([key, value]) => current.get(key) === value)) return current
          return next
        })
        const next = {top: host.scrollTop, height: host.clientHeight, offset,
          header: host.querySelector<HTMLElement>('.caseDocsListHead')?.offsetHeight ?? 0}
        setViewport(current => Object.keys(next).every(key => next[key as keyof typeof next] === current[key as keyof typeof next]) ? current : next)
      })
    }
    const observer = new ResizeObserver(update)
    observer.observe(host)
    observer.observe(container)
    // Newly mounted rows (including status badges) also need height observations.
    let observed = new Set<Element>()
    const observeRows = () => {
      const current = new Set(container.querySelectorAll<HTMLElement>(':scope > [data-doc-key]'))
      for (const row of observed) if (!current.has(row as HTMLElement)) observer.unobserve(row)
      for (const row of current) if (!observed.has(row)) observer.observe(row)
      observed = current
      update()
    }
    const mutations = new MutationObserver(observeRows)
    mutations.observe(container, {childList: true})
    observeRows()
    host.addEventListener('scroll', update, {passive: true})
    return () => { cancelAnimationFrame(frame); observer.disconnect(); mutations.disconnect(); host.removeEventListener('scroll', update) }
  }, [])

  const lastFocus = useRef<string | null>(null)
  useLayoutEffect(() => {
    if (lastFocus.current === focusKey) return
    lastFocus.current = focusKey
    if (!enabled || !focusKey) return
    const index = keys.indexOf(focusKey)
    const host = body.current?.closest<HTMLElement>('.caseDocsScroll')
    if (!host || index < 0) return
    const top = viewport.offset + offsets[index], bottom = viewport.offset + offsets[index + 1]
    if (top < host.scrollTop + viewport.header) host.scrollTop = Math.max(0, top - viewport.header)
    else if (bottom > host.scrollTop + host.clientHeight) host.scrollTop = bottom - host.clientHeight
  }, [focusKey, enabled, keys, offsets, viewport.offset, viewport.header])

  return <div ref={body} data-windowed={enabled ? 'true' : 'false'} data-loaded-rows={keys.length}>
    {window.before > 0 ? <div aria-hidden style={{height: window.before}} /> : null}
    {keys.slice(window.start, window.end).map((_, index) => renderRow(window.start + index))}
    {window.after > 0 ? <div aria-hidden style={{height: window.after}} /> : null}
  </div>
}
