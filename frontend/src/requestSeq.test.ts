import { describe, expect, it } from 'vitest'
import { createRequestSeq } from './requestSeq'

describe('createRequestSeq', () => {
  it('ignores stale ids after a newer next() or invalidate()', () => {
    const seq = createRequestSeq()
    const first = seq.next()
    const second = seq.next()
    expect(seq.isCurrent(first)).toBe(false)
    expect(seq.isCurrent(second)).toBe(true)

    seq.invalidate()
    expect(seq.isCurrent(second)).toBe(false)
    const third = seq.next()
    expect(seq.isCurrent(third)).toBe(true)
  })
})
