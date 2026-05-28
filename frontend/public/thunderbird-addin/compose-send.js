/* global globalThis */
'use strict'
;(function () {
  const SEND_SNAPSHOT_KEY = 'canary_compose_send_snapshot'
  /** @type {Map<string, object>} */
  const composeDetailsByTab = new Map()

  const shared = function () {
    return globalThis.canaryShared
  }
  const store = function () {
    return globalThis.canaryComposeStore
  }

  async function readSendSnapshot(ext, tabId) {
    if (!ext || !ext.storage || !ext.storage.session) return null
    const st = await ext.storage.session.get(SEND_SNAPSHOT_KEY)
    const row = st && st[SEND_SNAPSHOT_KEY]
    if (!row || !row.caseId) return null
    if (tabId != null && row.tabId != null && String(row.tabId) !== String(tabId)) return null
    return row
  }

  async function clearSendSnapshot(ext) {
    if (!ext || !ext.storage || !ext.storage.session) return
    await ext.storage.session.remove(SEND_SNAPSHOT_KEY)
  }

  async function resolveSendContext(ext, jwt, origin, tabId) {
    const sh = shared()
    const cs = store()
    let tabState = await cs.getTabState(ext, tabId)
    let caseId = tabState.caseId ? String(tabState.caseId) : ''

    const snapshot = await readSendSnapshot(ext, tabId)
    if (snapshot) {
      if (!caseId && snapshot.caseId) caseId = String(snapshot.caseId)
      tabState = Object.assign({}, tabState, snapshot.tabState || {})
    }

    const pending = await sh.fetchPendingSend(jwt, origin)
    if (pending && pending.active && pending.case_id) {
      if (!caseId) caseId = String(pending.case_id)
    }

    if (!caseId && tabId == null) {
      const activeId = await cs.getActiveComposeTab(ext)
      if (activeId != null) {
        tabState = await cs.getTabState(ext, activeId)
        caseId = tabState.caseId ? String(tabState.caseId) : ''
      }
    }

    return { caseId, tabState, snapshot }
  }

  async function resolveSentMessageHeaders(ext, sendInfo, snapshot) {
    const sh = shared()
    let msgs = (sendInfo && sendInfo.messages) || []
    if (msgs.length) return msgs

    const headerMid =
      (sendInfo && sendInfo.headerMessageId) ||
      (snapshot && snapshot.details && snapshot.details.headerMessageId) ||
      ''
    if (headerMid) {
      msgs = await sh.queryMessagesByHeaderMessageId(ext, headerMid)
      if (msgs.length) return msgs
    }
    return []
  }

  async function fileSentHeader(ext, token, origin, caseId, tabState, header) {
    const sh = shared()
    if (!header) throw new Error('No sent message header to file.')
    const msgId = sh.messageIdForApi(header.id)
    if (msgId == null) throw new Error('Sent message has no id.')
    if (!ext.messages || typeof ext.messages.getRaw !== 'function') {
      throw new Error('messages.getRaw is not available.')
    }
    const raw = await ext.messages.getRaw(msgId)
    const blob = sh.rawToBlob(raw)
    const subj = (header.subject && String(header.subject).trim()) || 'sent-message'
    const filename = sh.sanitizeFilename(subj) + '.eml'
    const imapRefs = await sh.resolveImapRefs(ext, header)
    let internetMid = header.headerMessageId ? String(header.headerMessageId).trim() : ''
    if (!internetMid && ext.messages && typeof ext.messages.getFull === 'function') {
      try {
        const full = await ext.messages.getFull(msgId, { decodeHeaders: true })
        internetMid = sh.extractMessageIdFromHeaders(full && full.headers)
      } catch (_) {
        /* optional */
      }
    }
    const uploaded = await sh.uploadCaseFile({
      token,
      origin,
      caseId,
      blob,
      filename,
      folder: tabState.folder || '',
      parentFileId: null,
      precedentId: tabState.precedentId || null,
      caseContactId: tabState.caseContactId || null,
      globalContactId: tabState.globalContactId || null,
      imapRefs,
      internetMessageId: internetMid || null,
    })
    await sh.recordFiledTbMessage(
      ext,
      header.id,
      caseId,
      uploaded && uploaded.id != null ? String(uploaded.id) : null,
      internetMid,
    )
    return { header: header, uploaded: uploaded, internetMessageId: internetMid || null }
  }

  async function fileSyntheticSentMessage(ext, token, origin, caseId, tabState, details, headerMessageId) {
    const sh = shared()
    const eml = sh.buildSyntheticEmlFromComposeDetails(details, headerMessageId)
    const blob = new Blob([eml], { type: 'message/rfc822' })
    const subj = (details && details.subject && String(details.subject).trim()) || 'sent-message'
    const filename = sh.sanitizeFilename(subj) + '.eml'
    const uploaded = await sh.uploadCaseFile({
      token,
      origin,
      caseId,
      blob,
      filename,
      folder: tabState.folder || '',
      parentFileId: null,
      precedentId: tabState.precedentId || null,
      caseContactId: tabState.caseContactId || null,
      globalContactId: tabState.globalContactId || null,
      imapRefs: null,
      internetMessageId: headerMessageId || null,
    })
    return { header: null, uploaded: uploaded, internetMessageId: headerMessageId || null }
  }

  async function captureSentCompose(ext, jwt, origin, caseId, tabState, sendInfo, snapshot, tabId) {
    const sh = shared()
    if (sendInfo && sendInfo.error) {
      throw new Error(String(sendInfo.error))
    }
    if (sendInfo && sendInfo.mode === 'sendLater') {
      throw new Error('Send later is not supported for automatic filing.')
    }

    let headers = await resolveSentMessageHeaders(ext, sendInfo, snapshot)
    const composeDetails =
      (sendInfo && sendInfo.details) ||
      (tabId != null ? composeDetailsByTab.get(String(tabId)) : null) ||
      (snapshot && snapshot.details) ||
      null
    const headerMessageId =
      (sendInfo && sendInfo.headerMessageId) ||
      (composeDetails && composeDetails.headerMessageId) ||
      null

    if (headers.length) {
      try {
        return await fileSentHeader(ext, jwt, origin, caseId, tabState, headers[0])
      } catch (rawErr) {
        console.warn('Canary: could not read sent message raw source, trying synthetic .eml:', rawErr)
      }
    }

    if (composeDetails) {
      const filed = await fileSyntheticSentMessage(
        ext,
        jwt,
        origin,
        caseId,
        tabState,
        composeDetails,
        headerMessageId,
      )
      if (headerMessageId) {
        headers = await sh.queryMessagesByHeaderMessageId(ext, headerMessageId)
        if (headers.length) {
          filed.header = headers[0]
        }
      }
      if (!filed.internetMessageId && headerMessageId) {
        filed.internetMessageId = headerMessageId
      }
      return filed
    }

    throw new Error('Could not locate the sent message to file.')
  }

  function registerComposeListeners() {
    const ext = shared().getGecko()
    if (!ext || !ext.compose) return
    store().registerComposeTabTracking(ext)

    if (ext.compose.onBeforeSend) {
      ext.compose.onBeforeSend.addListener(function (tab, details) {
        const tabId = tab && tab.id
        if (tabId != null && details) {
          composeDetailsByTab.set(String(tabId), details)
        }
        void (async function () {
          try {
            const sh = shared()
            const tabId = tab && tab.id
            if (tabId == null || !ext.storage || !ext.storage.session) return
            const { jwt, origin } = await sh.getStoredAuth(ext)
            if (!jwt || !origin) return
            const ctx = await resolveSendContext(ext, jwt, origin, tabId)
            if (!ctx.caseId) return
            await ext.storage.session.set({
              [SEND_SNAPSHOT_KEY]: {
                tabId: tabId,
                caseId: ctx.caseId,
                tabState: ctx.tabState,
                details: details || null,
                at: Date.now(),
              },
            })
          } catch (e) {
            console.warn('Canary onBeforeSend snapshot failed:', e)
          }
        })()
      })
    }

    if (!ext.compose.onAfterSend) return

    ext.compose.onAfterSend.addListener(function (tab, sendInfo) {
      void (async function () {
        const sh = shared()
        const cs = store()
        const tabId = tab && tab.id
        try {
          const { jwt, origin } = await sh.getStoredAuth(ext)
          if (!jwt || !origin) {
            console.warn('Canary onAfterSend: not signed in.')
            return
          }
          const ctx = await resolveSendContext(ext, jwt, origin, tabId)
          const caseId = ctx.caseId
          if (!caseId) {
            console.warn('Canary onAfterSend: no matter selected (tab state and pending-send empty).')
            return
          }
          await captureSentCompose(
            ext,
            jwt,
            origin,
            caseId,
            ctx.tabState,
            sendInfo,
            ctx.snapshot,
            tabId,
          )
          await fetch(sh.apiRoot(origin) + '/mail-plugin/pending-send', {
            method: 'DELETE',
            headers: sh.authHeaders(jwt),
          }).catch(() => {})
          await clearSendSnapshot(ext)
          if (tabId != null) {
            composeDetailsByTab.delete(String(tabId))
            await cs.clearTabState(ext, tabId)
          }
        } catch (e) {
          console.warn('Canary onAfterSend capture failed:', e)
        }
      })()
    })
  }

  if (!globalThis.__canaryComposeSendRegistered) {
    globalThis.__canaryComposeSendRegistered = true
    registerComposeListeners()
  }
})()
