import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RowActions } from './RowActions'

describe('explicit row actions', () => {
  it('opens exactly once with Enter without triggering row keyboard navigation', async () => {
    const open = vi.fn()
    const rowKey = vi.fn()
    const rowClick = vi.fn()
    render(<div onKeyDown={rowKey} onClick={rowClick}><RowActions label="matter 900001" onOpen={open} onActions={vi.fn()} /></div>)
    const user = userEvent.setup()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Open matter 900001' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(open).toHaveBeenCalledTimes(1)
    expect(rowKey).not.toHaveBeenCalled()
    expect(rowClick).not.toHaveBeenCalled()
  })

  it('opens Actions without opening or selecting the row', async () => {
    const open = vi.fn()
    const actions = vi.fn()
    const rowClick = vi.fn()
    render(<div onClick={rowClick}><RowActions label="document.docx" onOpen={open} onActions={actions} /></div>)
    await userEvent.click(screen.getByRole('button', { name: 'Actions for document.docx' }))
    expect(actions).toHaveBeenCalledTimes(1)
    expect(open).not.toHaveBeenCalled()
    expect(rowClick).not.toHaveBeenCalled()
  })
})
