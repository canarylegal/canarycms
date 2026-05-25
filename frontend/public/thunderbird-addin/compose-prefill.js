/* global globalThis */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const cs = () => globalThis.canaryComposeStore

  /** Automatic reply prefill disabled — manual matter selection only (avoids wrong-case filing). */
  const ENABLE_REPLY_PREFILL = false

  const prefillDoneForTab = new Set()
  const prefillTimersByTab = new Map()
  const lastRelatedByTab = new Map()

  function isReplyOrForward(details) {
    if (!details || !details.type) return false
    const t = String(details.type).toLowerCase()
    if (t === 'new' || t === 'draft') return false
    return t === 'reply' || t === 'forward' || t.indexOf('reply') >= 0 || t.indexOf('forward') >= 0
  }

  function isDefiniteNonReplyCompose(details) {
    if (!details || !details.type) return false
    const t = String(details.type).toLowerCase()
    return t === 'new' || t === 'draft'
  }

  async function clearPendingSend(token, origin) {
    await sh().syncPendingSend(token, origin, null, null)
  }

  async function setPrefillStatus(ext, tabId, status) {
    if (tabId == null) return
    await cs().setTabState(ext, tabId, { prefillStatus: status || '' })
  }

  async function resetComposeTabForManualMatter(ext, tabId, jwt, origin, status) {
    await cs().clearTabState(ext, tabId)
    if (jwt && origin) await clearPendingSend(jwt, origin)
    await setPrefillStatus(ext, tabId, status)
  }

  async function tryPrefillComposeTab(ext, tabId) {
    if (tabId == null) return false
    const key = String(tabId)

    if (!ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      await setPrefillStatus(ext, tabId, 'compose-api-unavailable')
      return false
    }

    let details = null
    try {
      details = await ext.compose.getComposeDetails(tabId)
    } catch (_) {
      await setPrefillStatus(ext, tabId, 'getComposeDetails-failed')
      return false
    }

    const relatedKey =
      details.relatedMessageId != null ? String(details.relatedMessageId) : ''
    if (lastRelatedByTab.get(key) !== relatedKey) {
      lastRelatedByTab.set(key, relatedKey)
      prefillDoneForTab.delete(key)
    }

    if (isDefiniteNonReplyCompose(details)) {
      if (!prefillDoneForTab.has(key)) {
        prefillDoneForTab.add(key)
        const { jwt, origin } = await sh().getStoredAuth(ext)
        if (jwt && origin) await resetComposeTabForManualMatter(ext, tabId, jwt, origin, 'not-reply:new')
        else await cs().clearTabState(ext, tabId)
      }
      return false
    }

    if (!isReplyOrForward(details)) {
      await setPrefillStatus(ext, tabId, 'waiting-type:' + (details.type || ''))
      return false
    }

    if (prefillDoneForTab.has(key)) return false

    const st = await cs().getTabState(ext, tabId)
    if (st.userOverridden) {
      prefillDoneForTab.add(key)
      return false
    }

    prefillDoneForTab.add(key)

    if (!ENABLE_REPLY_PREFILL) {
      const { jwt, origin } = await sh().getStoredAuth(ext)
      if (jwt && origin) {
        await resetComposeTabForManualMatter(ext, tabId, jwt, origin, 'reply-manual')
      } else {
        await cs().clearTabState(ext, tabId)
        await setPrefillStatus(ext, tabId, 'reply-manual')
      }
      return false
    }

    return false
  }

  function schedulePrefillAttempts(ext, tabId) {
    const key = String(tabId)
    const prev = prefillTimersByTab.get(key)
    if (prev) {
      for (let i = 0; i < prev.length; i++) clearTimeout(prev[i])
    }
    const delays = [0, 400, 1000, 2500]
    const timers = delays.map(function (ms) {
      return setTimeout(function () {
        void tryPrefillComposeTab(ext, tabId)
      }, ms)
    })
    prefillTimersByTab.set(key, timers)
  }

  function registerComposePrefill(ext) {
    if (!ext.compose) return
    if (ext.compose.onComposeStateChanged) {
      ext.compose.onComposeStateChanged.addListener(function (tab) {
        if (!tab || tab.id == null) return
        const key = String(tab.id)
        if (prefillDoneForTab.has(key)) {
          void (async function () {
            try {
              const details = await ext.compose.getComposeDetails(tab.id)
              if (isDefiniteNonReplyCompose(details)) return
            } catch (_) {
              return
            }
            schedulePrefillAttempts(ext, tab.id)
          })()
          return
        }
        schedulePrefillAttempts(ext, tab.id)
      })
    }
    if (ext.storage && ext.storage.onChanged) {
      ext.storage.onChanged.addListener(function (changes, area) {
        if (area !== 'local') return
        if (!changes || !changes.canary_jwt) return
        const jwt = changes.canary_jwt.newValue
        if (!jwt) return
        void (async function () {
          const active = await cs().getActiveComposeTab(ext)
          if (active != null) schedulePrefillAttempts(ext, active)
        })()
      })
    }
    if (ext.tabs && ext.tabs.onRemoved) {
      ext.tabs.onRemoved.addListener(function (tabId) {
        const key = String(tabId)
        prefillDoneForTab.delete(key)
        lastRelatedByTab.delete(key)
        const prev = prefillTimersByTab.get(key)
        if (prev) {
          for (let i = 0; i < prev.length; i++) clearTimeout(prev[i])
          prefillTimersByTab.delete(key)
        }
      })
    }
  }

  const ext = sh().getGecko()
  if (ext) registerComposePrefill(ext)
})()
