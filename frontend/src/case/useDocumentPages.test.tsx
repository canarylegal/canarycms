import {act, cleanup, renderHook} from '@testing-library/react'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import {apiFetch} from '../api'
import {useDocumentPages, type DocumentPage, type DocumentRow} from './useDocumentPages'
vi.mock('../api',()=>({apiFetch:vi.fn()}))
const fetch=vi.mocked(apiFetch)
const pages=vi.fn()
const page=(ids:string[],cursor:string|null=null):DocumentPage=>({items:ids.map(id=>({id,group_pinned:false} as DocumentRow)),next_cursor:cursor})
const tick=async()=>{await act(async()=>{await vi.advanceTimersByTimeAsync(250)})}
beforeEach(()=>{
 vi.useFakeTimers();fetch.mockReset();pages.mockReset()
 fetch.mockImplementation((path)=>path.includes('folder-metadata')?Promise.resolve({paths:['Empty'],summaries:{Empty:'0 items, 0 subfolders'}}):pages(path))
})
afterEach(()=>{cleanup();vi.useRealTimers()})
it('loads folder metadata independently of a bounded document page',async()=>{
 pages.mockResolvedValue(page(['a'],'next'))
 const {result}=renderHook(()=>useDocumentPages('token','case','folder=',0))
 await tick()
 expect(result.current.folders.paths).toEqual(['Empty'])
 expect(result.current.rows.map(row=>row.id)).toEqual(['a'])
 expect(pages).toHaveBeenCalledTimes(1)
})
it('ignores obsolete folder searches and appends each continuation once',async()=>{
 let late!:(value:DocumentPage)=>void
 pages.mockImplementationOnce(()=>new Promise(resolve=>{late=resolve}))
 const {result,rerender}=renderHook(({q})=>useDocumentPages('token','case',q,0),{initialProps:{q:'folder=old'}})
 await tick()
 pages.mockResolvedValueOnce(page(['b'],'next')).mockResolvedValueOnce(page(['b','c']))
 rerender({q:'folder=new'});await tick()
 await act(async()=>late(page(['obsolete'])))
 await act(async()=>{result.current.loadMore();result.current.loadMore()})
 expect(result.current.rows.map(row=>row.id)).toEqual(['b','c'])
 expect(pages).toHaveBeenCalledTimes(3)
})
it('retains loaded documents after page failure and does not loop retries',async()=>{
 pages.mockResolvedValueOnce(page(['parent'],'next')).mockRejectedValueOnce({message:'Unavailable'})
 const {result,rerender}=renderHook(({revision})=>useDocumentPages('token','case','',revision),{initialProps:{revision:0}})
 await tick();await act(async()=>result.current.loadMore())
 expect(result.current.rows[0].id).toBe('parent')
 expect(result.current.error).toBe('Unavailable')
 await act(async()=>result.current.loadMore());expect(pages).toHaveBeenCalledTimes(2)
 pages.mockResolvedValueOnce(page(['parent','child']))
 rerender({revision:1});await tick()
 expect(result.current.error).toBeNull();expect(result.current.rows).toHaveLength(2)
})
it('clears previous matter metadata immediately when changing matter scope',async()=>{
 pages.mockResolvedValue(page(['a']))
 const {result,rerender}=renderHook(({id})=>useDocumentPages('token',id,'',0),{initialProps:{id:'one'}})
 await tick()
 fetch.mockImplementation(()=>new Promise(()=>{}))
 rerender({id:'two'})
 expect(result.current.folders.paths).toEqual([])
 expect(result.current.rows).toEqual([])
})
it('session expiry stops requests until explicit refresh after sign-in',async()=>{
 pages.mockRejectedValueOnce({status:401,message:'Sign in required'}).mockResolvedValueOnce(page(['a']))
 const {result,rerender}=renderHook(({revision})=>useDocumentPages('token','case','',revision),{initialProps:{revision:0}})
 await tick();expect(result.current.error).toBe('Sign in required')
 await act(async()=>result.current.loadMore());expect(pages).toHaveBeenCalledTimes(1)
 rerender({revision:1});await tick();expect(result.current.rows[0].id).toBe('a')
})
