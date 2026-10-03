/* global globalThis */
'use strict'
/**
 * Poll Canary for queued "open this filed .eml" requests from the web UI.
 * Opens via messenger.messageDisplay.open({ file }) — no browser download.
 */
;(function () {
  if (globalThis.__canaryPendingEmlInit) return
  globalThis.__canaryPendingEmlInit = true

  const POLL_MS = 1500
  const DEDUPE_MS = 30000
  let timer = null
  let inFlight = false
  let lastAuthWarnAt = 0
  /** @type {Map<string, number>} */
  const recentOpens = new Map()
  /** Serialize all messageDisplay.open calls (bridge + poller). */
  let openChain = Promise.resolve()

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

  function markOpened(fileId) {
    const key = String(fileId || '').toLowerCase()
    if (!key) return true
    const now = Date.now()
    const prev = recentOpens.get(key)
    if (prev != null && now - prev < DEDUPE_MS) return false
    recentOpens.set(key, now)
    if (recentOpens.size > 40) {
      for (const [k, t] of recentOpens) {
        if (now - t > DEDUPE_MS) recentOpens.delete(k)
      }
    }
    return true
  }

  async function openEmlFile(ext, file) {
    if (!ext.messageDisplay || typeof ext.messageDisplay.open !== 'function') {
      console.warn('Canary: messageDisplay.open unavailable')
      notify('Canary', 'This Thunderbird build cannot open message files.')
      return false
    }
    // One call only — prefer window (common solicitor preference). No tab fallback
    // that could surface as a second view of the same message.
    try {
      await ext.messageDisplay.open({ file: file, location: 'window' })
      return true
    } catch (e1) {
      try {
        // Last resort: omit location (uses Thunderbird's open-message pref).
        await ext.messageDisplay.open({ file: file })
        return true
      } catch (e2) {
        console.warn('Canary: messageDisplay.open failed', e2 || e1)
        notify('Canary', 'Thunderbird refused to open the e-mail. Try Download .eml from Canary.')
        return false
      }
    }
  }

  function openEmlFileSerialized(ext, file) {
    const run = openChain.then(function () {
      return openEmlFile(ext, file)
    })
    openChain = run.then(
      function () {},
      function () {},
    )
    return run
  }

  async function openClaimedEml(ext, claim, origin) {
    const sh = globalThis.canaryShared
    if (!sh || !claim || !claim.active || !claim.open_token || !claim.case_id || !claim.file_id) {
      return false
    }
    if (!markOpened(claim.file_id)) {
      console.info('Canary: skip duplicate eml-open for', claim.file_id)
      return true
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
    const ok = await openEmlFileSerialized(ext, file)
    if (ok) notify('Canary', 'Opened e-mail in Thunderbird.')
    return ok
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
    if (ext.runtime && ext.runtime.onMessage) {
      ext.runtime.onMessage.addListener(function (message) {
        if (message && message.type === 'canary-poll-pending-eml-open') {
          void pollOnce()
        }
      })
    }
  }

  globalThis.canaryPollPendingEmlOpen = pollOnce
  globalThis.canaryMarkEmlOpened = markOpened
  globalThis.canaryOpenEmlFile = openEmlFileSerialized
})()
