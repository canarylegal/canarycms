/* global globalThis */
'use strict'
;(function () {
  const shared = function () {
    return globalThis.canaryShared
  }

  async function applyBundleToTab(ext, tabId, bundle, options) {
    const sh = shared()
    if (!ext.compose || tabId == null) {
      throw new Error('Compose API not available.')
    }
    const skipTo = options && options.skipTo
    const details = {
      subject: bundle.subject || '',
      plainTextBody: bundle.body || '',
    }
    if (!skipTo) {
      details.to = bundle.to || undefined
      if (details.to === '') delete details.to
    }
    await ext.compose.setComposeDetails(tabId, details)
    const atts = (bundle && bundle.attachments) || []
    for (let i = 0; i < atts.length; i++) {
      const a = atts[i]
      if (!a || !a.content_base64) continue
      try {
        const blob = sh.base64ToBlob(a.content_base64, a.mime_type || 'application/octet-stream')
        const file = new File([blob], a.filename || 'attachment', {
          type: a.mime_type || 'application/octet-stream',
        })
        await ext.compose.addAttachment(tabId, { file: file, name: a.filename || 'attachment' })
      } catch (_) {
        /* best-effort per attachment */
      }
    }
  }

  async function applyAttachmentsOnly(ext, tabId, bundle) {
    if (!ext.compose || tabId == null) {
      throw new Error('Compose API not available.')
    }
    const atts = (bundle && bundle.attachments) || []
    const sh = shared()
    let added = 0
    for (let i = 0; i < atts.length; i++) {
      const a = atts[i]
      if (!a || !a.content_base64) continue
      try {
        const blob = sh.base64ToBlob(a.content_base64, a.mime_type || 'application/octet-stream')
        const file = new File([blob], a.filename || 'attachment', {
          type: a.mime_type || 'application/octet-stream',
        })
        await ext.compose.addAttachment(tabId, { file: file, name: a.filename || 'attachment' })
        added += 1
      } catch (_) {
        /* best-effort per attachment */
      }
    }
    if (!added && atts.length) {
      throw new Error('Could not add attachments to the message.')
    }
  }

  globalThis.canaryApplyComposeBundle = applyBundleToTab
  globalThis.canaryApplyComposeAttachments = applyAttachmentsOnly
})()
