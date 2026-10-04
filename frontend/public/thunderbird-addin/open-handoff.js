/* global messenger, browser */
'use strict'
;(function () {
  const ext = typeof messenger !== 'undefined' ? messenger : typeof browser !== 'undefined' ? browser : null
  if (!ext || !ext.runtime || !ext.runtime.sendMessage) return

  const statusEl = document.getElementById('status')

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || ''
  }

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

  function pollPending() {
    return ext.runtime.sendMessage({ type: 'canary-poll-pending-eml-open' }).catch(function () {})
  }

  function checkAuth() {
    return ext.runtime
      .sendMessage({ type: 'canary-handoff-auth-status' })
      .catch(function () {
        return null
      })
  }

  setStatus('Opening from Canary…')
  void pollPending()
    .then(function () {
      return new Promise(function (r) {
        setTimeout(r, 500)
      })
    })
    .then(function () {
      return checkAuth()
    })
    .then(function (auth) {
      if (auth && auth.signedIn === false) {
        setStatus('Sign in via the Canary toolbar button, then try Open in Thunderbird again.')
        // Keep the tab briefly so the message is readable; user may also get a desktop notify.
        return new Promise(function (r) {
          setTimeout(r, 4500)
        }).then(closeThisTab)
      }
      return new Promise(function (r) {
        setTimeout(r, 350)
      })
        .then(function () {
          // Second nudge — startup races can miss the first poll.
          return pollPending()
        })
        .then(function () {
          return new Promise(function (r) {
            setTimeout(r, 400)
          })
        })
        .then(closeThisTab)
    })
    .then(function () {
      return new Promise(function (r) {
        setTimeout(r, 600)
      }).then(closeThisTab)
    })
    .catch(function () {})
})()
