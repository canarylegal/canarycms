import { describe, expect, it } from 'vitest'
import type { CaseOut, UserSummary } from './types'
import {
  caseMatchesMainMenuSearch,
  feeEarnerLabel,
  filterMainMenuCases,
  matterTypeLabel,
} from './mainMenuCases'

const users: UserSummary[] = [
  { id: 'u1', display_name: 'Ada Lovelace', email: 'ada@example.com', role: 'user', is_active: true },
]

function matter(partial: Partial<CaseOut> = {}): CaseOut {
  return {
    id: 'c1',
    case_number: '000100',
    client_name: 'Sam Thomas',
    matter_description: 'Purchase of 1 High Street',
    fee_earner_user_id: 'u1',
    status: 'open',
    created_by: 'u1',
    is_locked: false,
    lock_mode: 'none',
    created_at: '',
    updated_at: '',
    matter_head_type_name: 'Conveyancing',
    matter_sub_type_name: 'Purchase',
    source_name: 'Website',
    ...partial,
  }
}

describe('mainMenuCases helpers', () => {
  it('builds matter type and fee earner labels', () => {
    expect(matterTypeLabel(matter())).toBe('Conveyancing · Purchase')
    expect(matterTypeLabel(matter({ matter_head_type_name: null, matter_sub_type_name: null }))).toBe('—')
    expect(feeEarnerLabel(matter(), users)).toBe('Ada Lovelace')
    expect(feeEarnerLabel(matter({ fee_earner_user_id: 'missing' }), users)).toBe('—')
  })

  it('matches search across case fields', () => {
    const c = matter()
    expect(caseMatchesMainMenuSearch(c, users, '')).toBe(true)
    expect(caseMatchesMainMenuSearch(c, users, 'high street')).toBe(true)
    expect(caseMatchesMainMenuSearch(c, users, 'ada')).toBe(true)
    expect(caseMatchesMainMenuSearch(c, users, 'zzznomatch')).toBe(false)
  })

  it('filters by matter type, fee earner, and status', () => {
    const cases = [
      matter({ id: '1', status: 'open' }),
      matter({
        id: '2',
        status: 'closed',
        fee_earner_user_id: 'u2',
        matter_head_type_name: 'Litigation',
        matter_sub_type_name: 'Claim',
      }),
    ]
    expect(filterMainMenuCases(cases, ['Conveyancing · Purchase'], [], []).map((c) => c.id)).toEqual(['1'])
    expect(filterMainMenuCases(cases, [], ['u2'], []).map((c) => c.id)).toEqual(['2'])
    expect(filterMainMenuCases(cases, [], [], ['closed']).map((c) => c.id)).toEqual(['2'])
  })
})
