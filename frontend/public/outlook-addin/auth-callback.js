/* global Office */
'use strict'
;(function () {
  const statusEl = document.getElementById('status')

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text
  }

  function messageParent(payload) {
    if (Office && Office.context && Office.context.ui && typeof Office.context.ui.messageParent === 'function') {
      Office.context.ui.messageParent(JSON.stringify(payload))
    }
  }

  Office.onReady(function () {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code') || ''
    const state = params.get('state') || ''
    const error = params.get('error') || ''
    const payload = { code: code, state: state, error: error }
    messageParent(payload)
    setStatus(error ? 'Authorization failed. You can close this window.' : 'Connected. You can close this window.')
  })
})()
