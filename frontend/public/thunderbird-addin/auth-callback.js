/* global messenger, browser */
'use strict'
;(function () {
  const ext = messenger || browser
  const sh = globalThis.canaryShared
  const statusEl = document.getElementById('status')

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text
  }

  function closeConnectWindow() {
    try {
      if (window.top && window.top !== window && typeof window.top.close === 'function') {
        window.top.close()
        return
      }
    } catch (_) {}
    window.close()
  }

  async function finish() {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    const error = params.get('error')
    if (!ext || !ext.storage || !ext.storage.local) {
      setStatus('Storage unavailable.')
      return
    }
    const pending = {
      code: code || '',
      state: state || '',
      error: error || '',
      at: Date.now(),
    }
    await ext.storage.local.set({ [sh.PLUGIN_AUTH_PENDING_KEY]: pending })
    setStatus(error ? 'Authorization failed. You can close this tab.' : 'Connected. Return to Thunderbird — you can close this tab.')
    window.setTimeout(closeConnectWindow, 600)
  }

  finish().catch(function (e) {
    setStatus(e && e.message ? String(e.message) : 'Could not complete authorization.')
  })
})()
