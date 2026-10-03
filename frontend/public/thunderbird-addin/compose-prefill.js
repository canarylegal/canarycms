/* global globalThis */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const cs = () => globalThis.canaryComposeStore

  /** Automatic reply→matter prefill stays off (wrong-case risk). Canary→mailto uses pending-send. */
  const ENABLE_REPLY_PREFILL = false

  const prefillDoneForTab = new Set()
  const prefillTimersByTab = new Map()
  const lastRelatedByTab = new Map()
  /** Allow pending-send claim retries for a few seconds after compose opens (mailto race). */
  const pendingRetryDeadlineByTab = new Map()

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

  async function fetchCaseSummary(token, origin, caseId) {
    try {
      const res = await fetch(sh().apiRoot(origin) + '/cases/' + encodeURIComponent(String(caseId)), {
        headers: sh().authHeaders(token),
      })
      const body = await res.json().catch(function () {
        return null
      })
      if (!res.ok || !body || typeof body !== 'object') return null
      return body
    } catch (_) {
      return null
    }
  }

  /**
   * When Canary web launches mailto, it PUTs /mail-plugin/pending-send with the matter.
   * Bind that matter to this compose tab and claim (clear) the pending row so a later blank
   * Write is not incorrectly linked.
   */
  async function tryBindPendingSend(ext, tabId, jwt, origin) {
    const pending = await sh().fetchPendingSend(jwt, origin)
    if (!pending || !pending.active || !pending.case_id) return false

    const caseId = String(pending.case_id)
    const caseRow = await fetchCaseSummary(jwt, origin, caseId)
    const matterTitle =
      (caseRow && (caseRow.matter_description || caseRow.title || '').trim()) || ''
    await cs().setTabState(ext, tabId, {
      caseId: caseId,
      parentFileId: pending.source_file_id != null ? String(pending.source_file_id) : null,
      folder: '',
      userOverridden: false,
      prefilledFromPending: true,
      prefilledFromReply: false,
      composeAutoApplied: false,
      prefilledCaseNumber: (caseRow && caseRow.case_number) || '',
      prefilledClientName: (caseRow && caseRow.client_name) || '',
      prefilledMatterTitle: matterTitle,
      prefillStatus: 'pending-send',
    })
    await cs().setActiveComposeTab(ext, tabId)
    // Claim so the next unrelated Write does not inherit this matter.
    await clearPendingSend(jwt, origin)
    return true
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

    if (prefillDoneForTab.has(key)) return false

    const st = await cs().getTabState(ext, tabId)
    if (st.userOverridden) {
      prefillDoneForTab.add(key)
      return false
    }
    // Already bound (e.g. user opened the panel and confirmed) — do not re-claim.
    if (st.caseId && (st.prefilledFromPending || st.composeAutoApplied)) {
      prefillDoneForTab.add(key)
      return false
    }

    if (isDefiniteNonReplyCompose(details)) {
      const { jwt, origin } = await sh().getStoredAuth(ext)
      if (!jwt || !origin) {
        prefillDoneForTab.add(key)
        await setPrefillStatus(ext, tabId, 'not-signed-in')
        return false
      }
      const bound = await tryBindPendingSend(ext, tabId, jwt, origin)
      if (bound) {
        prefillDoneForTab.add(key)
        pendingRetryDeadlineByTab.delete(key)
        return true
      }
      // Mailto can open before Canary's pending-send PUT lands — retry briefly, then stop.
      if (!pendingRetryDeadlineByTab.has(key)) {
        pendingRetryDeadlineByTab.set(key, Date.now() + 6000)
      }
      if (Date.now() > pendingRetryDeadlineByTab.get(key)) {
        prefillDoneForTab.add(key)
        pendingRetryDeadlineByTab.delete(key)
        await setPrefillStatus(ext, tabId, 'not-reply:new')
      }
      return false
    }

    if (!isReplyOrForward(details)) {
      await setPrefillStatus(ext, tabId, 'waiting-type:' + (details.type || ''))
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
    // Include a short delayed retry so Canary's pending-send PUT can win the race with mailto.
    const delays = [0, 400, 1000, 2500, 5000]
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
        schedulePrefillAttempts(ext, tab.id)
      })
    }
    if (ext.tabs && ext.tabs.onCreated) {
      ext.tabs.onCreated.addListener(function (tab) {
        if (!tab || tab.id == null || tab.type !== 'messageCompose') return
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
          if (active != null) {
            prefillDoneForTab.delete(String(active))
            schedulePrefillAttempts(ext, active)
          }
        })()
      })
    }
    if (ext.tabs && ext.tabs.onRemoved) {
      ext.tabs.onRemoved.addListener(function (tabId) {
        const key = String(tabId)
        prefillDoneForTab.delete(key)
        lastRelatedByTab.delete(key)
        pendingRetryDeadlineByTab.delete(key)
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
