import { useCallback, useEffect, useState } from 'react'

type ColumnWidthsOptions = {
  /** Persisted pixel widths; omit length or pass undefined to use CSS fr defaults. */
  widths?: number[]
  onChange?: (widths: number[]) => void
  /** Fallback when DOM measure fails on first resize. */
  fallbackWidths?: number[]
  min?: number
}

function measureRowColumnWidths(row: HTMLElement, count: number): number[] {
  const children = Array.from(row.children).slice(0, count) as HTMLElement[]
  if (children.length !== count) return []
  return children.map((el) => Math.round(el.getBoundingClientRect().width))
}

/** Resizable pixel column widths; uses CSS fr layout until the user resizes once. */
export function useColumnWidths(columnCount: number, options?: ColumnWidthsOptions) {
  const min = options?.min ?? 48
  const fallbacks = options?.fallbackWidths ?? Array.from({ length: columnCount }, () => 120)
  const externalWidths = options?.widths
  const customized =
    externalWidths != null && externalWidths.length === columnCount && options?.onChange != null

  const [pixelWidths, setPixelWidths] = useState<number[] | null>(null)

  useEffect(() => {
    if (customized && externalWidths) {
      setPixelWidths(externalWidths.map((w, i) => Math.max(min, Math.min(2000, w || fallbacks[i]!))))
      return
    }
    setPixelWidths(null)
  }, [customized, externalWidths, fallbacks, min])

  const gridTemplateColumns = pixelWidths
    ? pixelWidths.map((w) => `${Math.round(w)}px`).join(' ')
    : undefined

  const startResize = useCallback(
    (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => {
      let base = pixelWidths ?? (customized && externalWidths ? externalWidths : null)
      if (!base) {
        const measured = measureRow ? measureRowColumnWidths(measureRow, columnCount) : []
        base =
          measured.length === columnCount
            ? measured
            : fallbacks.map((w) => Math.max(min, Math.min(2000, w || 120)))
        setPixelWidths(base)
        options?.onChange?.(base)
      }
      const startW = base[colIndex] ?? fallbacks[colIndex] ?? min
      function onMove(ev: MouseEvent) {
        const dx = ev.clientX - startClientX
        setPixelWidths((prev) => {
          const current = prev ?? base!
          const next = [...current]
          next[colIndex] = Math.max(min, startW + dx)
          options?.onChange?.(next)
          return next
        })
      }
      function onUp() {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        window.removeEventListener('blur', onUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
      window.addEventListener('blur', onUp)
    },
    [columnCount, customized, externalWidths, fallbacks, min, options, pixelWidths],
  )

  return { gridTemplateColumns, startResize, customized: customized || pixelWidths != null }
}
