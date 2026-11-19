import { useCallback, useEffect, useRef, useState } from 'react'
import { MENU_COLUMN_RESET_EVENT } from './userUiPreferences'

type ColumnWidthsOptions = {
  /** Existing pixel preferences are used as relative weights, without rewriting them. */
  widths?: number[]
  onChange?: (widths: number[]) => void
  fallbackWidths?: number[]
  min?: number
  minimumWidths?: number[]
}

export function columnGrid(weights: number[], minimums: number[]): string {
  return weights.map((weight, i) => `minmax(${minimums[i]}px, ${weight}fr)`).join(' ')
}

/** CSS fits the weights to the container. Only completed user drags persist preferences. */
export function useColumnWidths(columnCount: number, options?: ColumnWidthsOptions) {
  const [local, setLocal] = useState<{ source: string; widths: number[] } | null>(null)
  const source = JSON.stringify(options?.widths ?? [])
  const widths = local?.source === source ? local.widths : options?.widths
  const minimums = Array.from({ length: columnCount }, (_, i) => options?.minimumWidths?.[i] ?? options?.min ?? 48)
  const latest = useRef(options)
  useEffect(() => { latest.current = options }, [options])
  const cancelDrag = useRef<(() => void) | null>(null)

  useEffect(() => {
    function reset() {
      cancelDrag.current?.()
      setLocal(null)
    }
    window.addEventListener(MENU_COLUMN_RESET_EVENT, reset)
    return () => {
      cancelDrag.current?.()
      window.removeEventListener(MENU_COLUMN_RESET_EVENT, reset)
    }
  }, [])

  const startResize = useCallback((index: number, startX: number, row?: HTMLElement | null) => {
    if (index < 0 || index >= columnCount - 1) return
    cancelDrag.current?.()
    const opts = latest.current
    const mins = Array.from({ length: columnCount }, (_, i) => opts?.minimumWidths?.[i] ?? opts?.min ?? 48)
    // Always measure the current layout, including any intervening sidebar/window resize.
    const measured = row ? Array.from(row.children).slice(0, columnCount).map(el => el.getBoundingClientRect().width) : []
    const base = measured.length === columnCount && measured.every(w => w > 0)
      ? measured : Array.from({ length: columnCount }, (_, i) => Math.max(mins[i], opts?.fallbackWidths?.[i] ?? 120))
    let next: number[] | null = null
    const cursor = document.body.style.cursor
    const userSelect = document.body.style.userSelect
    function move(event: MouseEvent) {
      const delta = Math.max(mins[index] - base[index], Math.min(base[index + 1] - mins[index + 1], event.clientX - startX))
      if (delta === 0 && !next) return
      next = [...base]
      next[index] += delta
      next[index + 1] -= delta
      setLocal({ source, widths: next })
    }
    function cleanup() {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', finish)
      window.removeEventListener('blur', finish)
      document.body.style.cursor = cursor
      document.body.style.userSelect = userSelect
      cancelDrag.current = null
    }
    function finish() {
      cleanup()
      if (next && next.some((w, i) => Math.abs(w - base[i]) >= 1)) {
        // Keep the existing integer preference format and its 2000 upper bound.
        const scale = Math.min(1, 2000 / Math.max(...next))
        const saved = next.map(w => Math.max(48, Math.round(w * scale)))
        setLocal({ source, widths: saved })
        latest.current?.onChange?.(saved)
      } else if (next) setLocal(local)
    }
    cancelDrag.current = cleanup
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', finish)
    window.addEventListener('blur', finish)
  }, [columnCount, source, local])

  const customized = widths?.length === columnCount
  return {
    gridTemplateColumns: customized ? columnGrid(widths, minimums) : undefined,
    startResize,
    customized,
  }
}
