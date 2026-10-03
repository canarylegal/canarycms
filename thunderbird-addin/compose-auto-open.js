/* global globalThis */
'use strict'
;(function () {
  /**
   * Track the active compose tab only. Do **not** auto-open the Canary panel when the user
   * starts Write / Reply / Forward — open only via the compose toolbar button (or explicit UI).
   */
  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  globalThis.canaryClearComposeAutoOpened = function (_tabId) {
    /* retained for callers; auto-open disabled */
  }

  function registerComposeTabTracking(ext) {
    if (!ext.compose) return

    if (ext.compose.onComposeStateChanged) {
      ext.compose.onComposeStateChanged.addListener(function (tab) {
        if (!tab || tab.id == null) return
        if (globalThis.canaryComposeStore && typeof globalThis.canaryComposeStore.setActiveComposeTab === 'function') {
          void globalThis.canaryComposeStore.setActiveComposeTab(ext, tab.id)
        }
      })
    }

    if (ext.tabs && ext.tabs.onCreated) {
      ext.tabs.onCreated.addListener(function (tab) {
        if (!tab || tab.id == null || tab.type !== 'messageCompose') return
        if (globalThis.canaryComposeStore && typeof globalThis.canaryComposeStore.setActiveComposeTab === 'function') {
          void globalThis.canaryComposeStore.setActiveComposeTab(ext, tab.id)
        }
      })
    }
  }

  const ext = getGecko()
  if (ext) registerComposeTabTracking(ext)
})()
