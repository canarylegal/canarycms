import { useEffect, type RefObject } from 'react'

/** Keyboard access for the existing context menus, including their nested items. */
export function useActionMenuKeyboard(ref: RefObject<HTMLDivElement | null>, open: boolean, close: () => void) {
  useEffect(() => {
    const menu = ref.current
    if (!open || !menu) return
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    menu.setAttribute('role', 'menu')
    const items = () => Array.from(menu.querySelectorAll<HTMLElement>('.docContextItem'))
      .filter((el) => !el.classList.contains('docContextItemDisabled') && el.getAttribute('aria-disabled') !== 'true' && el.getClientRects().length > 0)
    for (const el of menu.querySelectorAll<HTMLElement>('.docContextItem')) {
      el.setAttribute('role', 'menuitem')
      el.tabIndex = -1
    }
    items()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      const list = items()
      const index = list.indexOf(document.activeElement as HTMLElement)
      if (event.key === 'Escape' || event.key === 'Tab') {
        event.preventDefault()
        event.stopPropagation()
        close()
        trigger?.focus()
      } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault()
        event.stopPropagation()
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? list.length - 1 :
          (index + (event.key === 'ArrowUp' ? -1 : 1) + list.length) % list.length
        list[next]?.focus()
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        event.stopPropagation()
        list[index]?.click()
      }
    }
    menu.addEventListener('keydown', onKey)
    return () => menu.removeEventListener('keydown', onKey)
  }, [ref, open, close])
}
