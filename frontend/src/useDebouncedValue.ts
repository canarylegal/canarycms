import { useEffect, useState } from 'react'

/** Debounce a value for server-side search inputs. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const tid = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(tid)
  }, [value, delayMs])
  return debounced
}
