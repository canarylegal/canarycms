import { useCallback, useState } from 'react'

/** Track which dropdown in a form is open; opening one closes the others. */
export function useExclusiveDropdownOpen<T extends string>() {
  const [openKey, setOpenKey] = useState<T | null>(null)

  const isOpen = useCallback((key: T) => openKey === key, [openKey])

  const setOpen = useCallback((key: T, next: boolean) => {
    setOpenKey(next ? key : null)
  }, [])

  const closeAll = useCallback(() => setOpenKey(null), [])

  return { isOpen, setOpen, closeAll }
}
