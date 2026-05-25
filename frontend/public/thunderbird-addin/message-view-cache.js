/* global globalThis */
'use strict'
;(function () {
  const sh = () => globalThis.canaryShared
  const VIEWED_KEY = 'canary_last_viewed_filing_context'

  async function cacheContextForMessage(ext, message) {
    if (!message || message.id == null) return
    const shared = sh()
    if (!shared) return
    const { jwt, origin } = await shared.getStoredAuth(ext)
    if (!jwt || !origin) return
    const header = await shared.resolveMessageHeaderForLookup(ext, message.id)
    const ctx = await shared.fetchMessageContext(jwt, origin, ext, header || message)
    if (!ctx || !ctx.found || !ctx.case_id) return
    const mid =
      header && header.headerMessageId ? String(header.headerMessageId).trim() : ''
    await ext.storage.session.set({
      [VIEWED_KEY]: {
        tbMessageId: message.id,
        internetMessageId: mid || null,
        case_id: String(ctx.case_id),
        file_id: ctx.file_id != null ? String(ctx.file_id) : null,
        folder_path: ctx.folder_path || '',
        case_number: ctx.case_number || '',
        client_name: ctx.client_name || '',
        matter_description: ctx.matter_description || '',
        at: Date.now(),
      },
    })
  }

  function registerMessageViewCache(ext) {
    if (!ext.messageDisplay || !ext.messageDisplay.onMessageDisplayed) return
    ext.messageDisplay.onMessageDisplayed.addListener(function (_tab, message) {
      void cacheContextForMessage(ext, message)
    })
  }

  globalThis.canaryViewedMessageKey = VIEWED_KEY

  const ext = sh() && sh().getGecko()
  if (ext) registerMessageViewCache(ext)
})()
