/* global globalThis */
'use strict'
;(function () {
  // Hard stop if this script is evaluated more than once in the same background.
  if (globalThis.__canaryFilingMenuInit) return
  globalThis.__canaryFilingMenuInit = true

  const CONTEXT_FILING_KEY = 'canary_context_filing_message_id'
  const MENU_ID = 'canary-file-to-matter-v6'
  const LEGACY_MENU_IDS = [
    'canary-file-to-matter',
    'canary-file-to-matter-v2',
    'canary-file-to-matter-v3',
    'canary-file-to-matter-v4',
    'canary-file-to-matter-v5',
    'canary-file-to-matter-v6',
  ]
  const MENU_TITLE = 'File to Canary matter…'

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
    if (typeof ext.menus.remove === 'function') {
      for (let i = 0; i < LEGACY_MENU_IDS.length; i++) {
        try {
          await ext.menus.remove(LEGACY_MENU_IDS[i])
        } catch (_) {
          /* ignore */
        }
      }
    }
  }

  async function ensureSingleMenu(ext) {
    if (!ext.menus || typeof ext.menus.create !== 'function') return
    await wipeMenus(ext)
    // Let Thunderbird finish removing ghosts before recreating (reload race).
    await new Promise(function (r) {
      setTimeout(r, 50)
    })
    try {
      await ext.menus.create({
        id: MENU_ID,
        title: MENU_TITLE,
        contexts: ['message_list'],
      })
    } catch (_) {
      try {
        if (typeof ext.menus.update === 'function') {
          await ext.menus.update(MENU_ID, {
            title: MENU_TITLE,
            contexts: ['message_list'],
          })
        }
      } catch (e2) {
        console.warn('Canary: menus.create/update failed', e2)
      }
    }
    globalThis.__canaryFilingMenuRegistered = true
  }

  function bindClick(ext) {
    if (globalThis.__canaryFilingMenuClickBound) return
    globalThis.__canaryFilingMenuClickBound = true
    ext.menus.onClicked.addListener(onFilingMenuClicked)
  }

  function bindShownDedupe(ext) {
    if (globalThis.__canaryFilingMenuShownBound) return
    if (!ext.menus.onShown || typeof ext.menus.onShown.addListener !== 'function') return
    globalThis.__canaryFilingMenuShownBound = true
    ext.menus.onShown.addListener(function (info) {
      const ids = (info && info.menuIds) || []
      const ours = []
      for (let i = 0; i < ids.length; i++) {
        const id = String(ids[i] || '')
        if (id.indexOf('canary-file-to-matter') === 0) ours.push(id)
      }
      if (ours.length <= 1) return
      // Ghost duplicates from extension reloads — wipe and recreate one item, then refresh.
      void (async function () {
        try {
          await ensureSingleMenu(ext)
          if (typeof ext.menus.refresh === 'function') await ext.menus.refresh()
        } catch (e) {
          console.warn('Canary: menu dedupe failed', e)
        }
      })()
    })
  }

  const ext = getGecko()
  if (ext && ext.menus) {
    bindClick(ext)
    bindShownDedupe(ext)
    void ensureSingleMenu(ext).catch(function (e) {
      console.warn('Canary: menu register failed', e)
    })
  }
  globalThis.canaryContextFilingMessageKey = CONTEXT_FILING_KEY
})()
