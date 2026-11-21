import {cleanup,fireEvent,render,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {WindowedDocumentRows} from './WindowedDocumentRows'

const observed=new Set<Element>()
beforeEach(()=>{
 observed.clear()
 vi.stubGlobal('ResizeObserver',class {
  observe(el:Element){observed.add(el)}
  unobserve(el:Element){observed.delete(el)}
  disconnect(){observed.clear()}
 })
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  const host=this.closest('.caseDocsScroll') as HTMLElement|null
  const height=this.classList.contains('caseDocsScroll')?500:52
  return {x:0,y:0,left:0,right:800,width:800,top:this.hasAttribute('data-loaded-rows')?88-(host?.scrollTop??0):0,bottom:height,height,toJSON(){}} as DOMRect
 })
 vi.spyOn(HTMLElement.prototype,'offsetHeight','get').mockReturnValue(500)
 vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockReturnValue(500)
})
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()})

it('mounts an off-screen keyboard target and releases observations for removed rows',async()=>{
 const keys=Array.from({length:1000},(_,i)=>String(i))
 const content=(focusKey:string)=> <div className="caseDocsScroll"><WindowedDocumentRows keys={keys} focusKey={focusKey}
  renderRow={i=><div key={keys[i]} data-doc-key={keys[i]} style={{minHeight:52}}>Document {i}</div>} /></div>
 const {container,rerender,unmount}=render(content('0'))
 const host=container.firstElementChild as HTMLElement
 await waitFor(()=>expect(container.querySelectorAll('[data-doc-key]').length).toBeLessThan(40))
 rerender(content('900'))
 expect(host.scrollTop).toBeGreaterThan(40000)
 fireEvent.scroll(host)
 await waitFor(()=>expect(container.querySelector('[data-doc-key="900"]')).not.toBeNull())
 expect(container.querySelector('[data-doc-key="0"]')).toBeNull()
 await waitFor(()=>expect([...observed].every(el=>el.isConnected)).toBe(true))
 expect(observed.size).toBeLessThan(40)
 unmount();expect(observed.size).toBe(0)
})
