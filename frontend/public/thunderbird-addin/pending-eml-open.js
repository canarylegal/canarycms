/* global globalThis */
'use strict'
/**
 * Poll Canary for queued "open this filed .eml" requests from the web UI.
 * Opens via messenger.messageDisplay.open({ file }) — no browser download.
 */
;(function () {
  const POLL_MS = 2000
  let timer = null
  let inFlight = false
  let lastAuthWarnAt = 0

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  function notify(title, message) {
    const ext = getGecko()
    if (!ext || !ext.notifications || typeof ext.notifications.create !== 'function') return
    try {
      void ext.notifications.create({
        type: 'basic',
        iconUrl: ext.runtime.getURL('icons/icon32.png'),
        title: title || 'Canary',
        message: message || '',
      })
    } catch (_) {
      /* optional */
    }
  }

  async function openClaimedEml(ext, claim, origin) {
    const sh = globalThis.canaryShared
    if (!sh || !claim || !claim.active || !claim.open_token || !claim.case_id || !claim.file_id) {
      return false
    }
    if (!ext.messageDisplay || typeof ext.messageDisplay.open !== 'function') {
      console.warn('Canary: messageDisplay.open unavailable')
      notify('Canary', 'This Thunderbird build cannot open message files.')
      return false
    }
    const url =
      sh.apiRoot(origin) +
      '/cases/' +
      encodeURIComponent(String(claim.case_id)) +
      '/files/' +
      encodeURIComponent(String(claim.file_id)) +
      '/eml-open?token=' +
      encodeURIComponent(String(claim.open_token))
    const res = await fetch(url)
    if (!res.ok) {
      console.warn('Canary: pending eml-open fetch failed', res.status)
      notify('Canary', 'Could not download the e-mail to open (' + res.status + ').')
      return false
    }
    const buf = await res.arrayBuffer()
    let name = (claim.filename && String(claim.filename).trim()) || 'message.eml'
    if (!/\.eml$/i.test(name)) name = name.replace(/\.[^.]+$/, '') + '.eml'
    const file = new File([buf], name, { type: 'message/rfc822' })
    // Thunderbird API uses `location`, not `where`.
    try {
      await ext.messageDisplay.open({ file: file, location: 'window' })
    } catch (e1) {
      try {
        await ext.messageDisplay.open({ file: file, location: 'tab' })
      } catch (e2) {
        try {
          await ext.messageDisplay.open({ file: file })
        } catch (e3) {
          console.warn('Canary: messageDisplay.open failed', e3 || e2 || e1)
          notify('Canary', 'Thunderbird refused to open the e-mail. Try Download .eml from Canary.')
          return false
        }
      }
    }
    notify('Canary', 'Opened e-mail in Thunderbird.')
    return true
  }

  async function pollOnce() {
    if (inFlight) return
    const ext = getGecko()
    const sh = globalThis.canaryShared
    if (!ext || !sh) return
    inFlight = true
    try {
      const auth = await sh.getStoredAuth(ext)
      if (!auth || !auth.jwt || !auth.origin) {
        const now = Date.now()
        if (now - lastAuthWarnAt > 60000) {
          lastAuthWarnAt = now
          console.warn('Canary: sign in via the Canary toolbar button to open e-mails from the web app.')
        }
        return
      }
      const res = await fetch(sh.apiRoot(auth.origin) + '/mail-plugin/pending-eml-open/claim', {
        method: 'POST',
        headers: sh.authHeaders(auth.jwt),
      })
      const body = await res.json().catch(function () {
        return null
      })
      if (res.status === 401 || res.status === 403) {
        console.warn('Canary: pending eml-open claim auth failed', res.status)
        return
      }
      if (!res.ok || !body || !body.active) return
      console.info('Canary: claimed pending eml-open', body.file_id)
      await openClaimedEml(ext, body, auth.origin)
    } catch (e) {
      console.warn('Canary: pending eml-open poll failed', e)
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer != null) return
    void pollOnce()
    timer = setInterval(function () {
      void pollOnce()
    }, POLL_MS)
  }

  const ext = getGecko()
  if (ext) {
    start()
    if (ext.runtime && ext.runtime.onStartup) {
      ext.runtime.onStartup.addListener(start)
    }
    // Force a poll when the user opens the Canary popup / panel messaging wakes the background.
    if (ext.runtime && ext.runtime.onMessage) {
      ext.runtime.onMessage.addListener(function (message) {
        if (message && message.type === 'canary-poll-pending-eml-open') {
          void pollOnce()
        }
      })
    }
  }

  globalThis.canaryPollPendingEmlOpen = pollOnce
})()
