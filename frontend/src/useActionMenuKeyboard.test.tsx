import {useRef} from 'react'
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {useActionMenuKeyboard} from './useActionMenuKeyboard'

afterEach(cleanup)

it('prepares menu items inserted by a document refresh without stealing focus', async () => {
  const close = vi.fn()
  const download = vi.fn()
  function Menu({loaded}: {loaded: boolean}) {
    const ref = useRef<HTMLDivElement>(null)
    useActionMenuKeyboard(ref, true, close)
    return <div ref={ref}>
      {loaded && <div className="docContextItem" onClick={download}>Download</div>}
      <div className="docContextItem">Pin</div>
    </div>
  }
  const {rerender} = render(<Menu loaded={false} />)
  const pin = screen.getByRole('menuitem', {name: 'Pin'})
  pin.focus()
  rerender(<Menu loaded />)
  await waitFor(() => expect(screen.getByRole('menuitem', {name: 'Download'}).tabIndex).toBe(-1))
  expect(document.activeElement).toBe(pin)
  const item = screen.getByRole('menuitem', {name: 'Download'})
  vi.spyOn(item, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  item.focus()
  fireEvent.keyDown(item, {key: 'Enter'})
  expect(download).toHaveBeenCalledOnce()
})
