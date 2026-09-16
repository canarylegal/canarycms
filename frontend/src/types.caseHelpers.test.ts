import { describe, expect, it } from 'vitest'
import {
  caseHasRevokedUserAccess,
  displayCaseNumber,
  formatCaseStatusLabel,
  isQuoteWorkflowStatus,
  stripCaseNumberPrefix,
} from './types'

describe('case status / number helpers', () => {
  it('maps workflow statuses to UI labels', () => {
    expect(formatCaseStatusLabel('open')).toBe('Active')
    expect(formatCaseStatusLabel('closed')).toBe('Closed')
    expect(formatCaseStatusLabel('quote')).toBe('Quote')
    expect(formatCaseStatusLabel('post_completion')).toBe('Post-completion')
    expect(formatCaseStatusLabel('mystery')).toBe('mystery')
  })

  it('detects quote workflow statuses', () => {
    expect(isQuoteWorkflowStatus('quote')).toBe(true)
    expect(isQuoteWorkflowStatus('quote_closed')).toBe(true)
    expect(isQuoteWorkflowStatus('open')).toBe(false)
  })

  it('strips and applies Q display prefixes', () => {
    expect(stripCaseNumberPrefix('Q0001')).toBe('0001')
    expect(stripCaseNumberPrefix('0001')).toBe('0001')
    expect(displayCaseNumber('0001', 'quote')).toBe('Q0001')
    expect(displayCaseNumber('Q0001', 'quote')).toBe('Q0001')
    expect(displayCaseNumber('0001', 'open')).toBe('0001')
  })

  it('detects revoked / locked matter access', () => {
    expect(caseHasRevokedUserAccess({ is_locked: false, lock_mode: 'allow_list' })).toBe(true)
    expect(caseHasRevokedUserAccess({ is_locked: true, lock_mode: 'open_by_default' })).toBe(true)
    expect(caseHasRevokedUserAccess({ is_locked: false, lock_mode: 'open_by_default' })).toBe(false)
    expect(caseHasRevokedUserAccess({ is_locked: true, lock_mode: 'none' })).toBe(false)
  })
})
