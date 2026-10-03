/* global globalThis */
'use strict'
;(function () {
  // Hard stop if this script is evaluated more than once in the same background.
  if (globalThis.__canaryFilingMenuInit) return
  globalThis.__canaryFilingMenuInit = true

  const CONTEXT_FILING_KEY = 'canary_context_filing_message_id'
  const MENU_ID = 'canary-file-to-matter'
  const LEGACY_MENU_IDS = ['canary-file-to-matter', 'canary-file-to-matter-v2', 'canary-file-to-matter-v3']

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

  function onFilingMenuClicked(info) {
    if (!info || info.menuItemId !== MENU_ID) return
    const ext = getGecko()
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
  }

  async function wipeMenus(ext) {
    if (typeof ext.menus.removeAll === 'function') {
      try {
        await ext.menus.removeAll()
      } catch (_) {
        /* ignore */
      }
    }
    if (typeof ext.menus.remove !== 'function') return
    for (let i = 0; i < LEGACY_MENU_IDS.length; i++) {
      try {
        await ext.menus.remove(LEGACY_MENU_IDS[i])
      } catch (_) {
        /* ignore */
      }
    }
  }

  async function registerContextMenus(ext) {
    if (!ext.menus || typeof ext.menus.create !== 'function') return
    await wipeMenus(ext)
    // Promise-only create (no callback) — avoids TB dual callback/promise edge cases.
    try {
      await ext.menus.create({
        id: MENU_ID,
        title: 'File to Canary matter…',
        contexts: ['message_list'],
      })
    } catch (e) {
      // Item already present — refresh in place rather than creating a second entry.
      if (typeof ext.menus.update === 'function') {
        try {
          await ext.menus.update(MENU_ID, {
            title: 'File to Canary matter…',
            contexts: ['message_list'],
          })
        } catch (e2) {
          console.warn('Canary: menus.update failed', e2 || e)
        }
      } else {
        console.warn('Canary: menus.create failed', e)
      }
    }
    if (!globalThis.__canaryFilingMenuClickBound) {
      globalThis.__canaryFilingMenuClickBound = true
      ext.menus.onClicked.addListener(onFilingMenuClicked)
    }
  }

  const ext = getGecko()
  if (ext) {
    // Single registration path only (do NOT also register on onInstalled — that races and doubles).
    void registerContextMenus(ext).catch(function (e) {
      console.warn('Canary: menu register failed', e)
    })
  }
  globalThis.canaryContextFilingMessageKey = CONTEXT_FILING_KEY
})()
