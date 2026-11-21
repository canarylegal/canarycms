import {act,cleanup,renderHook} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {useCaseDocsSelection} from './useCaseDocsSelection'
import type {KeyboardEvent,MouseEvent} from 'react'
afterEach(cleanup)
const keyEvent=(key:string)=>({key,target:document.createElement('div'),preventDefault:vi.fn()} as unknown as KeyboardEvent)
const click=(modifiers:Partial<MouseEvent>={})=>({stopPropagation:vi.fn(),...modifiers} as unknown as MouseEvent)
const defaults={caseDocPanel:'documents',docMenu:null,commentOpen:false,precedentPicker:null,contactPickModal:null,files:[],setDocFolder:vi.fn(),previewEmlFile:vi.fn(),openCaseFile:vi.fn()}
it('keeps multi-selection and shift anchor as new pages arrive',()=>{
 const {result,rerender}=renderHook(({keys})=>useCaseDocsSelection({...defaults,allDocKeys:keys}),{initialProps:{keys:['a','b']}})
 act(()=>result.current.handleDocItemClick('a',click()))
 act(()=>result.current.handleDocItemClick('b',click({ctrlKey:true})))
 rerender({keys:['a','b','c','d']})
 expect([...result.current.selectedDocSet]).toEqual(['a','b'])
 act(()=>result.current.handleDocItemClick('d',click({shiftKey:true,ctrlKey:true})))
 expect([...result.current.selectedDocSet]).toEqual(['a','b','c','d'])
})
it('continues keyboard focus into the next page',()=>{
 const load=vi.fn()
 const {result,rerender}=renderHook(({keys,loading})=>useCaseDocsSelection({...defaults,allDocKeys:keys,hasMore:true,loading,onLoadMore:load}),{initialProps:{keys:['a'],loading:false}})
 act(()=>result.current.handleDocItemClick('a',click()))
 act(()=>result.current.handleDocsKeyDown(keyEvent('ArrowDown')))
 expect(load).toHaveBeenCalledOnce()
 rerender({keys:['a'],loading:true})
 rerender({keys:['a','b'],loading:false})
 expect(result.current.docFocusKey).toBe('b')
 expect([...result.current.selectedDocSet]).toEqual(['b'])
})
it('waits for the first document page before choosing initial keyboard focus',()=>{
 const {result,rerender}=renderHook(({keys,loading})=>useCaseDocsSelection({...defaults,allDocKeys:keys,loading}),{initialProps:{keys:['folder:Empty'],loading:true}})
 expect(result.current.docFocusKey).toBeNull()
 rerender({keys:['pinned','folder:Empty'],loading:false})
 expect(result.current.docFocusKey).toBe('pinned')
})
