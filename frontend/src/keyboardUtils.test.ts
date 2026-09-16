import { afterEach, describe, expect, it } from 'vitest'
import {
  isCaseContextMenuOpen,
  isEditableKeyboardTarget,
  isModalBlockingKeyboard,
} from './keyboardUtils'

describe('keyboardUtils', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('detects editable targets', () => {
    const input = document.createElement('input')
    const div = document.createElement('div')
    expect(isEditableKeyboardTarget(input)).toBe(true)
    expect(isEditableKeyboardTarget(div)).toBe(false)
    expect(isEditableKeyboardTarget(null)).toBe(false)

    div.setAttribute('contenteditable', 'true')
    expect(isEditableKeyboardTarget(div)).toBe(true)

    const nested = document.createElement('span')
    const host = document.createElement('div')
    host.setAttribute('contenteditable', 'true')
    host.appendChild(nested)
    document.body.appendChild(host)
    expect(isEditableKeyboardTarget(nested)).toBe(true)
  })

  it('detects modal and context-menu overlays in the DOM', () => {
    expect(isModalBlockingKeyboard()).toBe(false)
    expect(isCaseContextMenuOpen()).toBe(false)

    const overlay = document.createElement('div')
    overlay.className = 'modalOverlay'
    document.body.appendChild(overlay)
    expect(isModalBlockingKeyboard()).toBe(true)

    const menu = document.createElement('div')
    menu.className = 'docContextMenu'
    document.body.appendChild(menu)
    expect(isCaseContextMenuOpen()).toBe(true)
  })
})
