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

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  async function openClaimedEml(ext, claim, origin) {
    const sh = globalThis.canaryShared
    if (!sh || !claim || !claim.active || !claim.open_token || !claim.case_id || !claim.file_id) {
      return false
    }
    if (!ext.messageDisplay || typeof ext.messageDisplay.open !== 'function') {
      console.warn('Canary: messageDisplay.open unavailable')
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
      return false
    }
    const buf = await res.arrayBuffer()
    let name = (claim.filename && String(claim.filename).trim()) || 'message.eml'
    if (!/\.eml$/i.test(name)) name = name.replace(/\.[^.]+$/, '') + '.eml'
    const file = new File([buf], name, { type: 'message/rfc822' })
    await ext.messageDisplay.open({ file: file, where: 'window' })
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
      if (!auth || !auth.jwt || !auth.origin) return
      const res = await fetch(sh.apiRoot(auth.origin) + '/mail-plugin/pending-eml-open/claim', {
        method: 'POST',
        headers: sh.authHeaders(auth.jwt),
      })
      const body = await res.json().catch(function () {
        return null
      })
      if (!res.ok || !body || !body.active) return
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
  }
})()
