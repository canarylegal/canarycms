'use strict'
;(function () {
  const params = new URLSearchParams(window.location.search)
  const connect = params.get('connect')
  const statusEl = document.getElementById('status')

  if (!connect) {
    if (statusEl) statusEl.textContent = 'Missing connect URL.'
    return
  }

  // Navigate this popup to Canary (not an iframe). WebAuthn/passkeys are blocked inside iframes.
  window.location.replace(connect)
})()
