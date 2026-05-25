/* global globalThis */
'use strict'
;(function () {
  const shared = function () {
    return globalThis.canaryShared
  }
  const store = function () {
    return globalThis.canaryComposeStore
  }

  async function fileSentMessages(ext, token, origin, caseId, tabState, messageHeaders) {
    const sh = shared()
    const st = tabState || store().blankState()
    if (!messageHeaders || !messageHeaders.length) return
    const header = messageHeaders[0]
    if (!ext.messages || typeof ext.messages.getRaw !== 'function') return
    const rawId =
      typeof header.id === 'number'
        ? header.id
        : parseInt(String(header.id), 10)
    if (!Number.isFinite(rawId)) return
    const raw = await ext.messages.getRaw(rawId)
    const blob = sh.rawToBlob(raw)
    const subj = (header.subject && String(header.subject).trim()) || 'sent-message'
    const parentName = sh.sanitizeFilename(subj) + '.eml'
    const imapRefs = await sh.resolveImapRefs(ext, header)
    await sh.uploadCaseFile({
      token,
      origin,
      caseId,
      blob,
      filename: parentName,
      folder: st.folder || '',
      parentFileId: st.parentFileId || null,
      precedentId: st.precedentId || null,
      caseContactId: st.caseContactId || null,
      globalContactId: st.globalContactId || null,
      imapRefs,
    })
  }

  function registerComposeListeners() {
    const ext = shared().getGecko()
    if (!ext || !ext.compose || !ext.compose.onAfterSend) return
    store().registerComposeTabTracking(ext)
    ext.compose.onAfterSend.addListener(function (tab, sendInfo) {
      void (async function () {
        try {
          const sh = shared()
          const cs = store()
          const { jwt, origin } = await sh.getStoredAuth(ext)
          if (!jwt || !origin) return
          const tabId = tab && tab.id
          let tabState = await cs.getTabState(ext, tabId)
          const caseId = tabState.caseId ? String(tabState.caseId) : ''
          if (!caseId) return
          const msgs = (sendInfo && sendInfo.messages) || []
          if (!msgs.length) return
          await fileSentMessages(ext, jwt, origin, caseId, tabState, msgs)
          const header = msgs[0]
          if (header && header.id != null && typeof globalThis.canaryRunApplyFiledTag === 'function') {
            await globalThis.canaryRunApplyFiledTag(header.id)
          }
          await fetch(sh.apiRoot(origin) + '/mail-plugin/pending-send', {
            method: 'DELETE',
            headers: sh.authHeaders(jwt),
          }).catch(() => {})
          if (tabId != null) await cs.clearTabState(ext, tabId)
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
