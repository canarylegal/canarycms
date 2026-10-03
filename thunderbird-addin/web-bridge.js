/* global browser, messenger */
'use strict'
/**
 * Bridge Canary web UI → Thunderbird background (open filed .eml in a message window).
 * The web app postMessages; we forward to the background script.
 */
;(function () {
  const ext = typeof messenger !== 'undefined' ? messenger : typeof browser !== 'undefined' ? browser : null
  if (!ext || !ext.runtime || !ext.runtime.sendMessage) return

  const HOST = String(location.hostname || '')
  const allowed =
    /(^|\.)canarylegalsoftware\.co\.uk$/i.test(HOST) ||
    HOST === 'localhost' ||
    HOST === '127.0.0.1' ||
    /^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(HOST)
  if (!allowed) return

  function reply(requestId, payload) {
    window.postMessage(
      Object.assign({ type: 'canary-tb-open-eml-result', requestId: requestId }, payload || {}),
      '*',
    )
  }

  window.addEventListener('message', function (ev) {
    if (ev.source !== window) return
    const data = ev.data
    if (!data || typeof data !== 'object') return
    if (data.type === 'canary-tb-bridge-ping') {
      window.postMessage({ type: 'canary-tb-bridge-ready', version: 1 }, '*')
      return
    }
    if (data.type !== 'canary-tb-open-eml') return
    const requestId = data.requestId
    const url = data.url
    if (!requestId || !url || typeof url !== 'string') {
      reply(requestId, { ok: false, detail: 'Missing url.' })
      return
    }
    // Only allow Canary API open-token URLs (avoid turning the bridge into an open fetch proxy).
    if (!/\/files\/[^/]+\/eml-open\?/i.test(url) || !/[?&]token=/.test(url)) {
      reply(requestId, { ok: false, detail: 'Unsupported open URL.' })
      return
    }
    try {
      const u = new URL(url, location.href)
      if (u.protocol !== 'https:' && u.protocol !== 'http:') {
        reply(requestId, { ok: false, detail: 'Unsupported URL scheme.' })
        return
      }
    } catch (_) {
      reply(requestId, { ok: false, detail: 'Invalid URL.' })
      return
    }
    void ext.runtime
      .sendMessage({
        type: 'canary-open-eml-url',
        url: url,
        filename: typeof data.filename === 'string' ? data.filename : 'message.eml',
      })
      .then(function (resp) {
        reply(requestId, resp && typeof resp === 'object' ? resp : { ok: false, detail: 'No response' })
      })
      .catch(function (e) {
        reply(requestId, { ok: false, detail: (e && e.message) || String(e) })
      })
  })

  window.postMessage({ type: 'canary-tb-bridge-ready', version: 1 }, '*')
})()
