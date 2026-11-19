import { act, cleanup, fireEvent, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useColumnWidths } from './useColumnWidths'
import { MENU_COLUMN_RESET_EVENT } from './userUiPreferences'

afterEach(cleanup)
function row(widths: number[]) {
  const element = document.createElement('div')
  widths.forEach(width => {
    const child = document.createElement('div')
    child.getBoundingClientRect = () => ({ width }) as DOMRect
    element.append(child)
  })
  return element
}

describe('proportional column preferences', () => {
  it('uses saved pixels as weights without rewriting them on resize or rerender', () => {
    const onChange = vi.fn()
    const { result, rerender } = renderHook(() => useColumnWidths(3, {
      widths: [100, 300, 200], minimumWidths: [80, 120, 90], onChange,
      fallbackWidths: [100, 200, 100],
    }))
    expect(result.current.gridTemplateColumns).toBe('minmax(80px, 100fr) minmax(120px, 300fr) minmax(90px, 200fr)')
    fireEvent(window, new Event('resize'))
    rerender()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('measures the current row, redistributes adjacent columns and saves once on release', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useColumnWidths(3, { widths: [100, 300, 200], minimumWidths: [80, 120, 90], onChange }))
    act(() => result.current.startResize(0, 400, row([200, 600, 400])))
    fireEvent.mouseMove(document, { clientX: 450 })
    expect(result.current.gridTemplateColumns).toContain('250fr')
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.mouseUp(document)
    expect(onChange).toHaveBeenCalledExactlyOnceWith([250, 550, 400])
  })

  it('clamps both sides to minimum widths and preserves the total', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useColumnWidths(3, { minimumWidths: [80, 120, 90], onChange }))
    act(() => result.current.startResize(0, 0, row([200, 300, 200])))
    fireEvent.mouseMove(document, { clientX: 1000 })
    fireEvent.mouseUp(document)
    expect(onChange).toHaveBeenLastCalledWith([380, 120, 200])
    act(() => result.current.startResize(0, 0, row([380, 120, 200])))
    fireEvent.mouseMove(document, { clientX: -1000 })
    fireEvent(window, new Event('blur'))
    expect(onChange).toHaveBeenLastCalledWith([80, 420, 200])
  })

  it('does not save a click or a drag that returns to its start', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useColumnWidths(2, { onChange }))
    act(() => result.current.startResize(0, 0, row([200, 300])))
    fireEvent.mouseUp(document)
    act(() => result.current.startResize(0, 0, row([200, 300])))
    fireEvent.mouseMove(document, { clientX: 30 })
    fireEvent.mouseMove(document, { clientX: 0 })
    fireEvent.mouseUp(document)
    expect(onChange).not.toHaveBeenCalled()
    expect(result.current.customized).toBe(false)
  })

  it('accepts external preferences and cleans up a drag on reset or unmount without saving', () => {
    const onChange = vi.fn()
    const { result, rerender, unmount } = renderHook(({ widths }) => useColumnWidths(2, { widths, onChange }), { initialProps: { widths: [100, 200] } })
    rerender({ widths: [200, 100] })
    expect(result.current.gridTemplateColumns).toContain('200fr')
    act(() => result.current.startResize(0, 0, row([200, 300])))
    fireEvent.mouseMove(document, { clientX: 30 })
    fireEvent(window, new Event(MENU_COLUMN_RESET_EVENT))
    fireEvent.mouseUp(document)
    expect(onChange).not.toHaveBeenCalled()
    act(() => result.current.startResize(0, 0, row([200, 300])))
    unmount()
    fireEvent.mouseMove(document, { clientX: 100 })
    fireEvent.mouseUp(document)
    expect(onChange).not.toHaveBeenCalled()
    expect(document.body.style.cursor).toBe('')
  })
})
