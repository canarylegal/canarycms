/** True when the event target is an input the user is typing into. */
export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return Boolean(target.closest('[contenteditable="true"]'))
}

/** True when a modal overlay is blocking app-level shortcuts. */
export function isModalBlockingKeyboard(): boolean {
  return Boolean(document.querySelector('.modalOverlay'))
}

/** True when a case row context menu is open. */
export function isCaseContextMenuOpen(): boolean {
  return Boolean(document.querySelector('.docContextMenu'))
}
