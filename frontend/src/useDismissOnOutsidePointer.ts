import { useEffect, useRef } from 'react'

/**
 * Call `onDismiss` on the next pointer down outside nodes matched by `contains`.
 * Registration is deferred one frame so the same gesture that opened a menu does not close it.
 */
export function useDismissOnOutsidePointer(
  open: boolean,
  contains: (target: Node) => boolean,
  onDismiss: () => void,
) {
  const containsRef = useRef(contains)
  containsRef.current = contains
  const onDismissRef = useRef(onDismiss)
  onDismissRef.current = onDismiss

  useEffect(() => {
    if (!open) return

    function handlePointerDown(e: MouseEvent) {
      if (containsRef.current(e.target as Node)) return
      onDismissRef.current()
    }

    let attached = false
    const frame = window.requestAnimationFrame(() => {
      attached = true
      document.addEventListener('mousedown', handlePointerDown)
    })

    return () => {
      window.cancelAnimationFrame(frame)
      if (attached) document.removeEventListener('mousedown', handlePointerDown)
    }
  }, [open])
}
