import { it, expect } from 'vitest'
import { performance } from 'node:perf_hooks'
import { buildCaseTableRows } from './mainMenuCaseData'
import type { CaseOut, UserSummary } from './types'
it('measures large-list fee-earner lookup work', () => {
  let reads = 0
  const users = Array.from({length:200},(_,i) => ({get id(){reads++;return `u${i}`},display_name:`Fee Earner ${String(i).padStart(3,'0')}`} as UserSummary))
  const cases = Array.from({length:5000},(_,i)=>({id:`c${i}`,case_number:`PERF-${i}`,matter_description:'Synthetic transaction',status:'open',fee_earner_user_id:`u${(i*97)%200}`,created_at:'2026-01-01'} as CaseOut))
  const start=performance.now()
  const rows=buildCaseTableRows(cases,users,'Fee Earner',{matterTypes:[],feeEarnerUserIds:[],caseStatuses:[]},'feeEarner','asc')
  expect(rows).toHaveLength(5000)
  expect(reads).toBeLessThanOrEqual(400)
  expect(rows[0].fee_earner_user_id).toBe('u0')
  expect(rows.at(-1)?.fee_earner_user_id).toBe('u199')
  console.log(JSON.stringify({case_rows:rows.length,staff_id_reads:reads,elapsed_ms:performance.now()-start}))
})

it('retains duplicate-ID, missing-staff, search and stable ordering semantics', () => {
  const users=[{id:'u1',display_name:'First'},{id:'u1',display_name:'Second'}] as UserSummary[]
  const cases=[{id:'a',case_number:'1',status:'open',fee_earner_user_id:'u1'},
    {id:'b',case_number:'2',status:'open',fee_earner_user_id:'u1'},
    {id:'c',case_number:'3',status:'closed',fee_earner_user_id:'missing'}] as CaseOut[]
  const filters={matterTypes:[],feeEarnerUserIds:[],caseStatuses:[]}
  expect(buildCaseTableRows(cases,users,' FIRST ',filters,'feeEarner','desc').map(c=>c.id)).toEqual(['a','b'])
  expect(buildCaseTableRows(cases,users,'Second',filters,'feeEarner','asc')).toEqual([])
  expect(buildCaseTableRows(cases,users,'—',filters,'feeEarner','asc').map(c=>c.id)).toEqual(['c'])
  expect(cases.map(c=>c.id)).toEqual(['a','b','c'])
})
