/* global globalThis */
'use strict'
;(function () {
  const openedForTab = new Set()
  const pendingOpen = new Map()

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  function tryOpenComposePanel(ext, tabId, force) {
    const key = String(tabId)
    if (!force && openedForTab.has(key)) return
    const openFn = globalThis.canaryOpenComposePanelWindow
    if (typeof openFn !== 'function') return
    if (!force) openedForTab.add(key)
    void openFn(tabId, { force: !!force }).then(function (r) {
      if (!r || !r.ok) openedForTab.delete(key)
      else if (!force) openedForTab.add(key)
    }).catch(function () {
      openedForTab.delete(key)
    })
  }

  globalThis.canaryClearComposeAutoOpened = function (tabId) {
    if (tabId == null) return
    openedForTab.delete(String(tabId))
    const prev = pendingOpen.get(String(tabId))
    if (prev != null) {
      clearTimeout(prev)
      pendingOpen.delete(String(tabId))
    }
  }

  function scheduleOpen(ext, tabId) {
    const key = String(tabId)
    if (openedForTab.has(key) || pendingOpen.has(key)) return
    const t = setTimeout(function () {
      pendingOpen.delete(key)
      tryOpenComposePanel(ext, tabId)
    }, 400)
    pendingOpen.set(key, t)
  }

  function registerComposeAutoOpen(ext) {
    if (!ext.compose) return

    if (ext.compose.onComposeStateChanged) {
      ext.compose.onComposeStateChanged.addListener(function (tab) {
        if (!tab || tab.id == null) return
        if (globalThis.canaryComposeStore && typeof globalThis.canaryComposeStore.setActiveComposeTab === 'function') {
          void globalThis.canaryComposeStore.setActiveComposeTab(ext, tab.id)
        }
        scheduleOpen(ext, tab.id)
      })
    }

    if (ext.tabs && ext.tabs.onCreated) {
      ext.tabs.onCreated.addListener(function (tab) {
        if (!tab || tab.id == null) return
        if (tab.type === 'messageCompose') {
          scheduleOpen(ext, tab.id)
        }
      })
    }

    if (ext.tabs && ext.tabs.onUpdated) {
      ext.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
        if (changeInfo && changeInfo.status === 'complete' && tab && tab.type === 'messageCompose') {
          scheduleOpen(ext, tabId)
        }
      })
    }

    if (ext.tabs && ext.tabs.onRemoved) {
      ext.tabs.onRemoved.addListener(function (tabId) {
        if (globalThis.canaryClearComposeAutoOpened) {
          globalThis.canaryClearComposeAutoOpened(tabId)
        }
      })
    }
  }

  const ext = getGecko()
  if (ext) registerComposeAutoOpen(ext)
})()
