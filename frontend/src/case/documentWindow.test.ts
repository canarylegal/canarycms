import {expect,it} from 'vitest'
import {documentOffsets,documentWindow} from './documentWindow'

it('includes partially visible variable-height rows and both overscan edges',()=>{
 const offsets=documentOffsets(['a','b','c','d','e'],new Map([['b',80],['d',110]]),50)
 expect(offsets).toEqual([0,50,130,180,290,340])
 expect(documentWindow(offsets,110,100,0)).toEqual({start:1,end:4,before:50,after:50})
 expect(documentWindow(offsets,110,100,1)).toEqual({start:0,end:5,before:0,after:0})
})
it('clamps empty lists and positions beyond their ends',()=>{
 expect(documentWindow([0],1000,600)).toEqual({start:0,end:0,before:0,after:0})
 expect(documentWindow([0,50,100],-30,20,0)).toEqual({start:0,end:1,before:0,after:50})
 expect(documentWindow([0,50,100],1000,600,0)).toEqual({start:2,end:2,before:100,after:0})
})
it('bounds mounted rows after ten thousand documents have loaded',()=>{
 const keys=Array.from({length:10000},(_,i)=>String(i))
 const offsets=documentOffsets(keys,new Map(),52)
 const window=documentWindow(offsets,260000,900)
 expect(window.end-window.start).toBeLessThan(40)
 expect(window.before+offsets[window.end]-offsets[window.start]+window.after).toBe(offsets[10000])
})
