/* global globalThis */
'use strict'
;(function () {
  const COMPOSE_BODY_READY_MS = 350

  const shared = function () {
    return globalThis.canaryShared
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms)
    })
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  function plainTextToHtml(text) {
    return String(text || '')
      .split(/\r?\n/)
      .map(function (line) {
        return '<div>' + (line ? escapeHtml(line) : '<br>') + '</div>'
      })
      .join('')
  }

  function mergeBodyText(bundle) {
    const raw = String((bundle && bundle.body) || '')
    if (!raw.trim()) return ''
    return raw.replace(/\r\n/g, '\n')
  }

  function isTrivialHtml(html) {
    const s = String(html || '')
      .replace(/\s/g, '')
      .toLowerCase()
    return !s || s === '<br>' || s === '<br/>' || s === '<div><br></div>' || s === '<div><br/></div>'
  }

  function bodyHasEmbeddedImages(text) {
    const s = String(text || '')
    return /<img[\s>]/i.test(s) || /cid:/i.test(s) || /data:image\//i.test(s)
  }

  /** Insert merge HTML before the moz-signature block or after <body> when present. */
  function prependToComposeHtml(mergeHtml, existingHtml) {
    const existing = String(existingHtml || '')
    const merge = String(mergeHtml || '')
    if (!merge) return existing
    if (!existing.trim() || isTrivialHtml(existing)) return merge
    const sigStart = existing.search(/<div[^>]*class="[^"]*moz-signature/i)
    if (sigStart >= 0) {
      const before = existing.slice(0, sigStart)
      const signatureBlock = existing.slice(sigStart)
      if (isTrivialHtml(before)) {
        return merge + '<div><br></div>' + signatureBlock
      }
      return before + merge + '<div><br></div>' + signatureBlock
    }
    const bodyOpen = existing.match(/<body[^>]*>/i)
    if (bodyOpen && bodyOpen.index != null) {
      const idx = bodyOpen.index + bodyOpen[0].length
      return existing.slice(0, idx) + merge + '<div><br></div>' + existing.slice(idx)
    }
    return merge + '<div><br></div>' + existing
  }

  async function getComposeDetailsForApply(ext, tabId) {
    if (!ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      return { isPlainText: false, body: '', plainTextBody: '' }
    }
    try {
      const details = await ext.compose.getComposeDetails(tabId)
      return {
        isPlainText: !!(details && details.isPlainText),
        body: String((details && details.body) || ''),
        plainTextBody: String((details && details.plainTextBody) || ''),
      }
    } catch (_) {
      return { isPlainText: false, body: '', plainTextBody: '' }
    }
  }

  async function captureComposeDetailsForApply(ext, tabId) {
    let details = await getComposeDetailsForApply(ext, tabId)
    if (details.isPlainText || isTrivialHtml(details.body)) return details
    await sleep(COMPOSE_BODY_READY_MS)
    return getComposeDetailsForApply(ext, tabId)
  }

  function bodyContainsMerge(composeDetails, merge, isPlainText) {
    if (!merge) return true
    const probe = merge.slice(0, Math.min(40, merge.length))
    if (!probe) return true
    if (isPlainText) {
      return String(composeDetails.plainTextBody || composeDetails.body || '').indexOf(probe) >= 0
    }
    const html = String(composeDetails.body || '')
    const firstLine = merge.split('\n').map(function (l) {
      return l.trim()
    }).filter(Boolean)[0]
    if (firstLine && html.indexOf(escapeHtml(firstLine)) >= 0) return true
    return html.indexOf(probe) >= 0 || html.indexOf(plainTextToHtml(merge).slice(0, 80)) >= 0
  }

  function mergeOnlyFields(merge, isPlainText) {
    if (isPlainText) {
      return { plainTextBody: merge }
    }
    return { body: plainTextToHtml(merge) }
  }

  function prependBodyFields(merge, existingHtml, isPlainText) {
    if (isPlainText) {
      const existing = String(existingHtml || '').trim()
      if (!existing) return mergeOnlyFields(merge, true)
      return { plainTextBody: merge + '\n\n' + existing }
    }
    if (isTrivialHtml(existingHtml)) {
      return mergeOnlyFields(merge, false)
    }
    return { body: prependToComposeHtml(plainTextToHtml(merge), existingHtml) }
  }

  async function applyBodyWithSignaturePreserve(ext, tabId, bundle, composeDetails, headerDetails) {
    const merge = mergeBodyText(bundle)
    if (!merge) return

    const isPlainText = composeDetails.isPlainText
    const mergeOnly = mergeOnlyFields(merge, isPlainText)
    const savedExisting = isPlainText
      ? String(composeDetails.plainTextBody || composeDetails.body || '').trim()
      : String(composeDetails.body || '')
    const hasExisting = isPlainText ? !!savedExisting : !isTrivialHtml(savedExisting)

    if (!hasExisting) {
      await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, mergeOnly))
      return
    }

    const combined = prependBodyFields(merge, savedExisting, isPlainText)
    await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, combined))
    let after = await getComposeDetailsForApply(ext, tabId)
    if (bodyContainsMerge(after, merge, isPlainText)) return

    if (!isPlainText && bodyHasEmbeddedImages(savedExisting)) {
      await sleep(200)
      const retry = prependBodyFields(merge, savedExisting, isPlainText)
      await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, retry))
      after = await getComposeDetailsForApply(ext, tabId)
      if (bodyContainsMerge(after, merge, isPlainText)) return
    }

    /* One-shot prepend often fails when a signature is present — apply precedent, then restore signature. */
    await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, mergeOnly))
    after = await getComposeDetailsForApply(ext, tabId)
    if (!bodyContainsMerge(after, merge, isPlainText)) return

    const restore = prependBodyFields(merge, savedExisting, isPlainText)
    await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, restore))
    after = await getComposeDetailsForApply(ext, tabId)
    if (!bodyContainsMerge(after, merge, isPlainText)) {
      await ext.compose.setComposeDetails(tabId, Object.assign({}, headerDetails, mergeOnly))
    }
  }

  async function applyBundleToTab(ext, tabId, bundle, options) {
    const sh = shared()
    if (!ext.compose || tabId == null) {
      throw new Error('Compose API not available.')
    }
    const skipTo = options && options.skipTo
    const composeDetails = await captureComposeDetailsForApply(ext, tabId)

    const headerDetails = {
      subject: bundle.subject || '',
    }
    if (!skipTo) {
      headerDetails.to = bundle.to || undefined
      if (headerDetails.to === '') delete headerDetails.to
    }

    await applyBodyWithSignaturePreserve(ext, tabId, bundle, composeDetails, headerDetails)

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
