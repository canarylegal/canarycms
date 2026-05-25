/* global globalThis */
'use strict'
;(function () {
  const CONTEXT_FILING_KEY = 'canary_context_filing_message_id'
  const MENU_ID = 'canary-file-to-matter'

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  /** message_list clicks expose selectedMessages, not messageId (TB menus API). */
  async function resolveMessageIdFromClick(ext, info) {
    if (!info) return null
    const sel = info.selectedMessages
    if (sel && Array.isArray(sel.messages) && sel.messages.length) {
      const id = sel.messages[0].id
      if (id != null) return id
    }
    let mid = info.messageId
    if (Array.isArray(mid)) mid = mid.length ? mid[0] : null
    if (mid != null) return mid
    if (ext.mailTabs && typeof ext.mailTabs.getSelectedMessages === 'function') {
      try {
        let tabId = info.tabId
        if (tabId == null && typeof ext.mailTabs.getCurrent === 'function') {
          const cur = await ext.mailTabs.getCurrent()
          tabId = cur && cur.id
        }
        if (tabId != null) {
          const picked = await ext.mailTabs.getSelectedMessages(tabId)
          const m =
            picked && Array.isArray(picked.messages) && picked.messages.length
              ? picked.messages[0]
              : null
          if (m && m.id != null) return m.id
        }
      } catch (_) {
        /* ignore */
      }
    }
    return null
  }

  function registerContextMenus(ext) {
    if (!ext.menus || typeof ext.menus.create !== 'function') return
    ext.menus.create({
      id: MENU_ID,
      title: 'File to Canary matter…',
      contexts: ['message_list'],
    })
    ext.menus.onClicked.addListener(function (info) {
      if (!info || info.menuItemId !== MENU_ID) return
      void (async function () {
        const mid = await resolveMessageIdFromClick(ext, info)
        if (mid == null) {
          console.warn('Canary: no message for filing menu (selectedMessages empty).', info)
          return
        }
        if (typeof globalThis.canaryOpenFilingWindow === 'function') {
          void globalThis.canaryOpenFilingWindow(mid)
        } else {
          console.warn('Canary: canaryOpenFilingWindow not loaded (check script order in manifest).')
        }
      })()
    })
  }

  const ext = getGecko()
  if (ext) registerContextMenus(ext)
  globalThis.canaryContextFilingMessageKey = CONTEXT_FILING_KEY
})()
