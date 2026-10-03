/* global messenger, browser */
'use strict'
;(function () {
  const ext = typeof messenger !== 'undefined' ? messenger : typeof browser !== 'undefined' ? browser : null
  if (!ext || !ext.runtime || !ext.runtime.sendMessage) return

  function closeThisTab() {
    try {
      window.close()
    } catch (_) {
      /* ignore */
    }
    if (!ext.tabs || typeof ext.tabs.getCurrent !== 'function' || typeof ext.tabs.remove !== 'function') {
      return Promise.resolve()
    }
    return ext.tabs
      .getCurrent()
      .then(function (tab) {
        if (tab && tab.id != null) return ext.tabs.remove(tab.id)
      })
      .catch(function () {})
  }

  void ext.runtime
    .sendMessage({ type: 'canary-poll-pending-eml-open' })
    .catch(function () {})
    .then(function () {
      return new Promise(function (r) {
        setTimeout(r, 400)
      })
    })
    .then(function () {
      return closeThisTab()
    })
    .then(function () {
      // Retry close — some TB builds ignore the first remove while the tab is still loading.
      return new Promise(function (r) {
        setTimeout(r, 600)
      }).then(closeThisTab)
    })
    .catch(function () {})
})()
