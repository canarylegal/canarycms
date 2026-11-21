import { useLayoutEffect } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
import { useMatterPages, type MatterPage } from './useMatterPages'
import type { CaseOut } from './types'
vi.mock('./api', () => ({apiFetch: vi.fn()}))
const fetch = vi.mocked(apiFetch)
const page = (ids: string[], cursor: string | null = null): MatterPage => ({items: ids.map(id => ({id} as CaseOut)), next_cursor: cursor})
const tick = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(250) }) }
beforeEach(() => { vi.useFakeTimers(); fetch.mockReset() })
afterEach(() => { cleanup(); vi.useRealTimers() })

it('debounces queries, discards late responses and aborts obsolete requests', async () => {
  let late!: (data: MatterPage) => void
  fetch.mockImplementationOnce(() => new Promise(resolve => { late = resolve }))
  const {result, rerender} = renderHook(({q}) => useMatterPages('session', q, 0, true), {initialProps:{q:'q=old'}})
  await tick()
  const signal = fetch.mock.calls[0][1]?.signal
  fetch.mockResolvedValueOnce(page(['new']))
  rerender({q:'q=n'}); rerender({q:'q=new'})
  await tick()
  await act(async () => late(page(['old'], 'stale')))
  expect(signal?.aborted).toBe(true)
  expect(result.current.rows.map(r=>r.id)).toEqual(['new'])
  expect(result.current.hasMore).toBe(false)
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('serializes continuation requests and deduplicates concurrent edits', async () => {
  fetch.mockResolvedValueOnce(page(['a'], 'next')).mockResolvedValueOnce(page(['a','b']))
  const {result} = renderHook(() => useMatterPages('session', 'q=', 0, true))
  await tick()
  await act(async () => { result.current.loadMore(); result.current.loadMore() })
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[1][0]).toContain('cursor=next')
  expect(result.current.rows.map(r=>r.id)).toEqual(['a','b'])
})

it('retains loaded rows on continuation failure, stops retry loops and refreshes explicitly', async () => {
  fetch.mockResolvedValueOnce(page(['a'], 'next')).mockRejectedValueOnce({message:'Unavailable'})
  const {result} = renderHook(() => useMatterPages('session', 'q=', 0, true))
  await tick()
  await act(async () => result.current.loadMore())
  expect(result.current.rows.map(r=>r.id)).toEqual(['a'])
  expect(result.current.error).toBe('Unavailable')
  await act(async () => result.current.loadMore())
  expect(fetch).toHaveBeenCalledTimes(2)
  fetch.mockResolvedValueOnce(page(['a','b']))
  act(() => result.current.refresh())
  await tick()
  expect(result.current.error).toBeNull()
  expect(result.current.rows).toHaveLength(2)
})

it('does not request a hidden, never-opened menu and clears old rows on session change', async () => {
  const {result, rerender} = renderHook(({enabled, token}) => useMatterPages(token, 'q=', 0, enabled), {initialProps:{enabled:false,token:'one'}})
  await tick(); expect(fetch).not.toHaveBeenCalled()
  fetch.mockResolvedValueOnce(page(['one']))
  rerender({enabled:true,token:'one'}); await tick()
  expect(result.current.rows).toHaveLength(1)
  fetch.mockResolvedValueOnce(page(['two']))
  rerender({enabled:true,token:'two'})
  expect(result.current.rows).toEqual([])
  await tick(); expect(result.current.rows.map(r=>r.id)).toEqual(['two'])
})


it.each(['query', 'token', 'revision', 'disabled'])('rejects a stale continuation before reset effects run: %s', async changed => {
  fetch.mockResolvedValueOnce(page(['old'], 'old-cursor')).mockResolvedValue(page(['new']))
  const initial = { q: 'sort=created', token: 'one', revision: 0, enabled: true, trigger: false }
  const { rerender } = renderHook(props => {
    const pages = useMatterPages(props.token, props.q, props.revision, props.enabled)
    const { loadMore } = pages
    // A child observer/layout effect can run before the hook's passive reset effect.
    useLayoutEffect(() => {
      if (props.trigger) loadMore()
    }, [props.trigger, loadMore])
    return pages
  }, { initialProps: initial })
  await tick()
  rerender({ ...initial, trigger: true,
    ...(changed === 'query' ? { q: 'sort=feeEarner' } : {}),
    ...(changed === 'token' ? { token: 'two' } : {}),
    ...(changed === 'revision' ? { revision: 1 } : {}),
    ...(changed === 'disabled' ? { enabled: false } : {}),
  })
  expect(fetch).toHaveBeenCalledTimes(1)
  await tick()
  expect(fetch).toHaveBeenCalledTimes(changed === 'disabled' ? 1 : 2)
  expect(fetch.mock.calls.every(([path]) => !String(path).includes('cursor='))).toBe(true)
})
