/** Monotonic request ids so stale async responses can be ignored. */

export type RequestSeq = {
  next: () => number
  invalidate: () => void
  isCurrent: (id: number) => boolean
}

export function createRequestSeq(): RequestSeq {
  let current = 0
  return {
    next() {
      current += 1
      return current
    },
    invalidate() {
      current += 1
    },
    isCurrent(id: number) {
      return id === current
    },
  }
}
