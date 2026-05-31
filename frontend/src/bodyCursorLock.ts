/** Ref-counted ``wait`` cursor on ``document.body`` — always pair lock/unlock or call ``releaseAllBodyCursorLocks``. */

let lockCount = 0
let savedCursor = ''

export function lockBodyWaitCursor(): void {
  if (typeof document === 'undefined') return
  if (lockCount === 0) {
    savedCursor = document.body.style.cursor
    document.body.style.cursor = 'wait'
  }
  lockCount += 1
}

export function unlockBodyWaitCursor(): void {
  if (typeof document === 'undefined') return
  if (lockCount <= 0) return
  lockCount -= 1
  if (lockCount === 0) {
    document.body.style.cursor = savedCursor
    savedCursor = ''
  }
}

/** Reset after logout, stuck navigation, or abnormal unmount. */
export function releaseAllBodyCursorLocks(): void {
  if (typeof document === 'undefined') return
  lockCount = 0
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  savedCursor = ''
}

/**
 * Run async work under a wait cursor; always releases, including on throw/unmount via ``signal``.
 */
export function withBodyWaitCursor<T>(
  work: () => Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  lockBodyWaitCursor()
  const onAbort = () => unlockBodyWaitCursor()
  signal?.addEventListener('abort', onAbort, { once: true })
  return work()
    .finally(() => {
      signal?.removeEventListener('abort', onAbort)
      unlockBodyWaitCursor()
    })
}
