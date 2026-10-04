/* global globalThis */
'use strict'
/**
 * Poll Canary for queued "open this filed .eml" requests from the web UI.
 * Opens via messenger.messageDisplay.open({ file }) — no browser download.
 */
;(function () {
  if (globalThis.__canaryPendingEmlInit) return
  globalThis.__canaryPendingEmlInit = true

  const POLL_MS = 1200
  /** Bridge vs poller race only — must not block a later intentional re-open. */
  const RACE_MS = 2500
  const OPEN_TIMEOUT_MS = 4500
  let timer = null
  /** Claim lock only (never held across messageDisplay.open). */
  let claimInFlight = false
  let lastAuthWarnAt = 0
  /** @type {Map<string, number>} */
  const recentOpens = new Map()
  /** @type {Set<string>} */
  const openingNow = new Set()
  /** Serialize messageDisplay.open; always advance even if an open hangs. */
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

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms)
    })
  }

  function withTimeout(promise, ms, label) {
    let timer = null
    return Promise.race([
      Promise.resolve(promise).finally(function () {
        if (timer != null) clearTimeout(timer)
      }),
      new Promise(function (_, reject) {
        timer = setTimeout(function () {
          reject(new Error(label || 'timeout'))
        }, ms)
      }),
    ])
  }

  /** Reserve a short race window / in-progress slot. Returns false if skip. */
  function beginOpen(fileId) {
    const key = String(fileId || '').toLowerCase()
    if (!key) return true
    if (openingNow.has(key)) return false
    const now = Date.now()
    const prev = recentOpens.get(key)
    if (prev != null && now - prev < RACE_MS) return false
    openingNow.add(key)
    if (recentOpens.size > 40) {
      for (const [k, t] of recentOpens) {
        if (now - t > RACE_MS) recentOpens.delete(k)
      }
    }
    return true
  }

  function endOpen(fileId, ok) {
    const key = String(fileId || '').toLowerCase()
    if (!key) return
    openingNow.delete(key)
    if (ok) recentOpens.set(key, Date.now())
  }

  /** Legacy helpers used by background.js bridge. */
  function markOpened(fileId) {
    return beginOpen(fileId)
  }

  function clearOpened(fileId) {
    const key = String(fileId || '').toLowerCase()
    if (!key) return
    openingNow.delete(key)
    recentOpens.delete(key)
  }

  async function openEmlFile(ext, file) {
    if (!ext.messageDisplay || typeof ext.messageDisplay.open !== 'function') {
      console.warn('Canary: messageDisplay.open unavailable')
      notify('Canary', 'This Thunderbird build cannot open message files.')
      return false
    }
    // Thunderbird sometimes hangs on open (esp. after a message window is already up).
    // Timeout each attempt so the open chain and poller never wedge permanently.
    let lastErr = null
    const strategies = [
      function (f) {
        return { file: f, location: 'window' }
      },
      function (f) {
        return { file: f, location: 'tab' }
      },
      function (f) {
        return { file: f }
      },
    ]
    for (let attempt = 0; attempt < 3; attempt++) {
      if (attempt > 0) await sleep(250 * attempt)
      let bytes
      try {
        bytes = await file.arrayBuffer()
      } catch (e) {
        lastErr = e
        continue
      }
      const fresh = new File([bytes], file.name, { type: file.type || 'message/rfc822' })
      for (let s = 0; s < strategies.length; s++) {
        try {
          await withTimeout(
            ext.messageDisplay.open(strategies[s](fresh)),
            OPEN_TIMEOUT_MS,
            'messageDisplay.open timeout',
          )
          return true
        } catch (e) {
          lastErr = e
        }
      }
    }
    console.warn('Canary: messageDisplay.open failed', lastErr)
    notify('Canary', 'Thunderbird refused to open the e-mail. Try Download .eml from Canary.')
    return false
  }

  function openEmlFileSerialized(ext, file) {
    const run = openChain.then(function () {
      return openEmlFile(ext, file)
    })
    // Always advance the chain — even on hang/timeout/reject — so later opens are not blocked.
    openChain = run.then(
      function () {
        return sleep(80)
      },
      function () {
        return sleep(80)
      },
    )
    return run
  }

  async function requeuePendingEml(sh, auth, claim) {
    if (!auth || !auth.jwt || !auth.origin || !claim || !claim.case_id || !claim.file_id) return
    try {
      await fetch(sh.apiRoot(auth.origin) + '/mail-plugin/pending-eml-open', {
        method: 'PUT',
        headers: sh.jsonAuthHeaders(auth.jwt),
        body: JSON.stringify({
          case_id: String(claim.case_id),
          file_id: String(claim.file_id),
          ttl_seconds: 120,
        }),
      })
    } catch (e) {
      console.warn('Canary: could not re-queue failed eml-open', e)
    }
  }

  async function openClaimedEml(ext, claim, origin, auth) {
    const sh = globalThis.canaryShared
    if (!sh || !claim || !claim.active || !claim.open_token || !claim.case_id || !claim.file_id) {
      return false
    }
    if (!beginOpen(claim.file_id)) {
      console.info('Canary: skip race-duplicate eml-open for', claim.file_id)
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
    let res
    try {
      res = await fetch(url)
    } catch (e) {
      endOpen(claim.file_id, false)
      console.warn('Canary: pending eml-open fetch error', e)
      await requeuePendingEml(sh, auth, claim)
      return false
    }
    if (!res.ok) {
      endOpen(claim.file_id, false)
      console.warn('Canary: pending eml-open fetch failed', res.status)
      notify('Canary', 'Could not download the e-mail to open (' + res.status + ').')
      await requeuePendingEml(sh, auth, claim)
      return false
    }
    const buf = await res.arrayBuffer()
    let name = (claim.filename && String(claim.filename).trim()) || 'message.eml'
    if (!/\.eml$/i.test(name)) name = name.replace(/\.[^.]+$/, '') + '.eml'
    const file = new File([buf], name, { type: 'message/rfc822' })
    const ok = await openEmlFileSerialized(ext, file)
    endOpen(claim.file_id, ok)
    if (ok) return true
    await requeuePendingEml(sh, auth, claim)
    return false
  }

  async function pollOnce() {
    if (claimInFlight) return
    const ext = getGecko()
    const sh = globalThis.canaryShared
    if (!ext || !sh) return
    claimInFlight = true
    let claim = null
    let auth = null
    try {
      auth = await sh.getStoredAuth(ext)
      if (!auth || !auth.jwt || !auth.origin) {
        const now = Date.now()
        if (now - lastAuthWarnAt > 45000) {
          lastAuthWarnAt = now
          console.warn('Canary: sign in via the Canary toolbar button to open e-mails from the web app.')
          notify(
            'Canary',
            'Sign in via the Canary toolbar button to open e-mails from the web app.',
          )
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
        const now = Date.now()
        if (now - lastAuthWarnAt > 45000) {
          lastAuthWarnAt = now
          notify(
            'Canary',
            'Canary sign-in expired. Open the Canary toolbar button and sign in again.',
          )
        }
        return
      }
      if (!res.ok || !body || !body.active) return
      claim = body
      console.info('Canary: claimed pending eml-open', body.file_id)
    } catch (e) {
      console.warn('Canary: pending eml-open poll failed', e)
    } finally {
      // Release before open so a hung messageDisplay.open cannot block all future claims.
      claimInFlight = false
    }
    if (claim && auth) {
      try {
        await openClaimedEml(ext, claim, auth.origin, auth)
      } catch (e) {
        console.warn('Canary: openClaimedEml failed', e)
      }
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
  globalThis.canaryClearEmlOpened = clearOpened
  globalThis.canaryEndEmlOpen = endOpen
  globalThis.canaryOpenEmlFile = openEmlFileSerialized
})()
