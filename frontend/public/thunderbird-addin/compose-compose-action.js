/* global globalThis */
'use strict'
;(function () {
  const cs = () => globalThis.canaryComposeStore

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  async function isComposeTab(ext, tabId) {
    if (tabId == null || !ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      return false
    }
    try {
      await ext.compose.getComposeDetails(tabId)
      return true
    } catch (_) {
      return false
    }
  }

  async function listComposeTabIds(ext) {
    if (!ext.tabs || typeof ext.tabs.query !== 'function') return []
    try {
      const rows = await ext.tabs.query({ type: 'messageCompose' })
      return (rows || []).filter((t) => t && t.id != null).map((t) => t.id)
    } catch (_) {
      return []
    }
  }

  async function resolveComposeTabId(ext, tabFromEvent) {
    if (tabFromEvent && tabFromEvent.id != null && (await isComposeTab(ext, tabFromEvent.id))) {
      return tabFromEvent.id
    }

    if (cs && typeof cs().getActiveComposeTab === 'function') {
      const active = await cs().getActiveComposeTab(ext)
      if (active != null && (await isComposeTab(ext, active))) return active
    }

    if (ext.tabs && typeof ext.tabs.query === 'function') {
      try {
        let windowId = tabFromEvent && tabFromEvent.windowId != null ? tabFromEvent.windowId : null
        if (windowId == null && ext.windows && ext.windows.getLastFocused) {
          const win = await ext.windows.getLastFocused()
          if (win && win.id != null) windowId = win.id
        }
        const query = windowId != null ? { windowId: windowId, type: 'messageCompose' } : { type: 'messageCompose' }
        const rows = await ext.tabs.query(query)
        if (rows && rows.length) {
          for (let i = 0; i < rows.length; i++) {
            if (rows[i].active && rows[i].id != null) return rows[i].id
          }
          const last = rows[rows.length - 1]
          if (last && last.id != null) return last.id
        }
      } catch (_) {
        /* optional */
      }
    }

    const ids = await listComposeTabIds(ext)
    if (ids.length === 1) return ids[0]
    return null
  }

  async function openComposePanelFromToolbar(ext, tabFromEvent) {
    const tabId = await resolveComposeTabId(ext, tabFromEvent)
    if (tabId == null) {
      console.warn('Canary compose: no compose tab found for toolbar click')
      return { ok: false, detail: 'No compose tab found. Click in the message body, then try again.' }
    }

    if (globalThis.canaryClearComposeAutoOpened) {
      globalThis.canaryClearComposeAutoOpened(tabId)
    }
    if (cs && typeof cs().setActiveComposeTab === 'function') {
      await cs().setActiveComposeTab(ext, tabId)
    }

    const action = ext.composeAction
    if (action && typeof action.openPopup === 'function') {
      try {
        await action.openPopup()
        return { ok: true, popup: true }
      } catch (_) {
        /* fall through to pop-out window */
      }
    }

    const open = globalThis.canaryOpenComposePanelWindow
    if (typeof open !== 'function') {
      return { ok: false, detail: 'Compose panel opener not available.' }
    }
    return open(tabId, { force: true })
  }

  globalThis.canaryOpenComposePanelFromToolbar = openComposePanelFromToolbar

  function registerComposeActionClick(ext) {
    const action = ext.composeAction
    if (!action || typeof action.onClicked !== 'function') {
      return
    }
    action.onClicked.addListener(function (tab) {
      void openComposePanelFromToolbar(ext, tab)
    })
  }

  const ext = getGecko()
  if (ext) registerComposeActionClick(ext)
})()
