/* global Office */
/**
 * Event-based activation: OnMessageSend — save a synthetic .eml to Canary when a matter is known
 * (pending send from Canary web, or thread match via conversation id / linked metadata).
 * Does not use Microsoft Graph. Keep upload/MIME helpers aligned with taskpane.js.
 */
;(function () {
  'use strict'

  /* Initialize Office; handler registration must not rely only on this callback (classic Outlook + JS runtime). */
  Office.onReady()

  const LS_KEY = 'canary_outlook_addin_jwt'
  const LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  const RS_KEY = 'canary_jwt'
  const RS_API_ORIGIN_KEY = 'canary_api_origin'

  function pageOrigin() {
    try {
      if (window.location && window.location.href) {
        var u = new URL(window.location.href)
        return u.origin
      }
    } catch (_) {}
    return ''
  }

  /** Classic Outlook JS-only runtime: relative fetch URLs fail — prefer origin saved at task-pane sign-in. */
  function apiRoot() {
    var origin = ''
    try {
      var fromLs = localStorage.getItem(LS_API_ORIGIN_KEY)
      if (fromLs) origin = String(fromLs).trim().replace(/\/$/, '')
    } catch (_) {}
    if (!origin) {
      try {
        var fromRo = Office.context.roamingSettings.get(RS_API_ORIGIN_KEY)
        if (fromRo) origin = String(fromRo).trim().replace(/\/$/, '')
      } catch (_) {}
    }
    if (!origin) origin = pageOrigin()
    if (!origin) return ''
    return origin + '/api'
  }

  function getToken() {
    try {
      var fromLs = localStorage.getItem(LS_KEY)
      if (fromLs) return String(fromLs)
    } catch (_) {}
    try {
      return Office.context.roamingSettings.get(RS_KEY) || ''
    } catch (_) {
      return ''
    }
  }

  function authHeaders(token) {
    var h = new Headers()
    if (token) h.set('Authorization', 'Bearer ' + token)
    h.set('Accept', 'application/json')
    return h
  }

  function jsonAuthHeaders(token) {
    var h = authHeaders(token)
    h.set('Content-Type', 'application/json')
    return h
  }

  function sanitizeFilename(name) {
    var n = String(name || '').trim()
    if (!n) return 'sent-message'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'sent-message'
  }

  function randomMessageId() {
    var id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0
            var v = c === 'x' ? r : (r & 0x3) | 0x8
            return v.toString(16)
          })
    return '<' + id + '@canary-outlook-addin>'
  }

  function wrapMessageId(id) {
    var s = String(id || '').trim()
    if (!s) return randomMessageId()
    if (s.charAt(0) === '<') return s
    return '<' + s + '>'
  }

  function formatRecipients(list) {
    if (!list || !list.length) return ''
    return list
      .map(function (r) {
        if (!r) return ''
        var em = String(r.emailAddress || '').trim()
        var name = String(r.displayName || '').trim().replace(/"/g, '')
        if (name) return '"' + name + '" <' + em + '>'
        return em
      })
      .filter(Boolean)
      .join(', ')
  }

  function rfc2822(d) {
    try {
      return new Date(d).toUTCString()
    } catch (_) {
      return new Date().toUTCString()
    }
  }

  function composeFromLine(item) {
    try {
      if (item.from && item.from.emailAddress) {
        return formatRecipients([item.from])
      }
    } catch (_) {}
    try {
      var p = Office.context.mailbox.userProfile
      var em = p && p.emailAddress ? String(p.emailAddress).trim() : ''
      var dn = p && p.displayName ? String(p.displayName).trim().replace(/"/g, '') : ''
      if (em && dn) return '"' + dn + '" <' + em + '>'
      return em
    } catch (_) {}
    return ''
  }

  function buildSyntheticEmlCompose(item, bodyText, displaySubject, fromLine) {
    var subj =
      displaySubject != null && String(displaySubject).trim() !== ''
        ? String(displaySubject).trim()
        : String(item.subject || '(no subject)')
    var toDisp = formatRecipients(item.to || [])
    var ccDisp = formatRecipients(item.cc || [])
    var when = new Date().toISOString()
    var mid = wrapMessageId(item.internetMessageId)
    var hdr = ''
    hdr += 'From: ' + (fromLine || '') + '\r\n'
    if (toDisp) hdr += 'To: ' + toDisp + '\r\n'
    if (ccDisp) hdr += 'Cc: ' + ccDisp + '\r\n'
    hdr += 'Subject: ' + subj.replace(/\r|\n/g, ' ') + '\r\n'
    hdr += 'Date: ' + rfc2822(when) + '\r\n'
    hdr += 'Message-ID: ' + mid + '\r\n'
    hdr += 'MIME-Version: 1.0\r\n'
    hdr += 'Content-Type: text/plain; charset="utf-8"\r\n'
    hdr += '\r\n'
    hdr += (bodyText || '').replace(/\r\n/g, '\n').replace(/\n/g, '\r\n')
    return new Blob([hdr], { type: 'message/rfc822' })
  }

  function graphRestItemIdFromItem(item) {
    if (!item || !item.itemId) return ''
    var raw = String(item.itemId).trim()
    try {
      var mb = Office.context.mailbox
      if (mb && typeof mb.convertToRestId === 'function') {
        var RV = Office.MailboxEnums && Office.MailboxEnums.RestVersion
        var ver = RV && RV.v2_0 != null ? RV.v2_0 : 'v2.0'
        var converted = mb.convertToRestId(raw, ver)
        if (converted) return String(converted).trim()
      }
    } catch (_) {}
    return raw
  }

  function primaryOutlookItemIdForApi(item) {
    var rest = graphRestItemIdFromItem(item)
    if (rest) return rest
    try {
      if (item && item.itemId) return String(item.itemId).trim()
    } catch (_) {}
    return ''
  }

  function getBodyAsync(item, coercionType) {
    return new Promise(function (resolve, reject) {
      try {
        item.body.getAsync(coercionType, function (r) {
          if (r.status !== Office.AsyncResultStatus.Succeeded) {
            reject(new Error(r.error ? r.error.message : 'getAsync failed'))
            return
          }
          resolve(String(r.value || ''))
        })
      } catch (e) {
        reject(e)
      }
    })
  }

  function base64ToBlob(base64, mime) {
    var bin = atob(base64)
    var bytes = new Uint8Array(bin.length)
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    return new Blob([bytes], { type: mime || 'application/octet-stream' })
  }

  function getAttachmentTypeEnum() {
    return Office.MailboxEnums && Office.MailboxEnums.AttachmentType ? Office.MailboxEnums.AttachmentType : null
  }

  function shouldSkipAttachment(att) {
    if (!att || !att.id) return true
    var T = getAttachmentTypeEnum()
    if (T && att.attachmentType === T.Reference) return true
    return false
  }

  function getAttachmentContentAsync(item, id) {
    return new Promise(function (resolve, reject) {
      try {
        item.getAttachmentContentAsync(id, function (r) {
          if (r.status !== Office.AsyncResultStatus.Succeeded) {
            reject(new Error(r.error ? r.error.message : 'getAttachmentContentAsync failed'))
            return
          }
          resolve(r.value)
        })
      } catch (e) {
        reject(e)
      }
    })
  }

  async function uploadMultipart(token, caseId, payload) {
    var fd = new FormData()
    fd.append('upload', payload.blob, payload.filename)
    fd.append('folder', '')
    if (payload.parentFileId) fd.append('parent_file_id', payload.parentFileId)
    else {
      if (payload.outlookItemId) fd.append('outlook_item_id', payload.outlookItemId)
      if (payload.outlookConversationId) fd.append('outlook_conversation_id', payload.outlookConversationId)
    }

    var res = await fetch(apiRoot() + '/cases/' + encodeURIComponent(caseId) + '/files', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
      body: fd,
    })
    var body = await res.json().catch(function () {
      return null
    })
    if (!res.ok) {
      var detail = body && typeof body === 'object' && body.detail
      var msg = typeof detail === 'string' ? detail : 'Upload failed (' + res.status + ')'
      throw new Error(msg)
    }
    if (!body || typeof body !== 'object' || !body.id) {
      throw new Error('Upload succeeded but no file id returned.')
    }
    return body
  }

  async function fetchPending(token) {
    var res = await fetch(apiRoot() + '/outlook-plugin/pending-send', { headers: authHeaders(token) })
    var body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || typeof body !== 'object') return { active: false }
    return body
  }

  async function clearPending(token) {
    await fetch(apiRoot() + '/outlook-plugin/pending-send', {
      method: 'DELETE',
      headers: authHeaders(token),
    }).catch(function () {})
  }

  async function resolveLinkedCase(token, outlookItemId, internetMessageId, conversationId) {
    var res = await fetch(apiRoot() + '/outlook-plugin/linked-case', {
      method: 'POST',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify({
        outlook_item_id: outlookItemId || null,
        internet_message_id: internetMessageId || null,
        conversation_id: conversationId || null,
      }),
    })
    var body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || !body.linked_case || !body.linked_case.id) return ''
    return String(body.linked_case.id)
  }

  async function captureSendToCanary(event) {
    var finishOk = function () {
      event.completed({ allowEvent: true })
    }

    try {
      var token = getToken()
      if (!token) {
        finishOk()
        return
      }
      if (!apiRoot()) {
        finishOk()
        return
      }

      var item = Office.context.mailbox.item
      var Msg = Office.MailboxEnums && Office.MailboxEnums.ItemType && Office.MailboxEnums.ItemType.Message
      if (!item || (Msg != null && item.itemType !== Msg)) {
        finishOk()
        return
      }

      var oid = ''
      var imid = ''
      var conv = ''
      try {
        oid = primaryOutlookItemIdForApi(item)
      } catch (_) {}
      try {
        if (item.internetMessageId) imid = String(item.internetMessageId).trim()
      } catch (_) {}
      try {
        if (item.conversationId) conv = String(item.conversationId).trim()
      } catch (_) {}

      var pending = await fetchPending(token)
      var linkedCaseId = await resolveLinkedCase(token, oid || '', imid || '', conv || '')
      var caseId = linkedCaseId || ''
      var usedPending = false
      if (caseId) {
        if (pending && pending.active) await clearPending(token)
      } else if (pending && pending.active && pending.case_id) {
        caseId = String(pending.case_id)
        usedPending = true
      }

      if (!caseId) {
        finishOk()
        return
      }

      var bodyText = ''
      try {
        bodyText = await getBodyAsync(item, Office.CoercionType.Text)
      } catch (_) {
        bodyText = ''
      }
      if (!bodyText || !bodyText.trim()) {
        try {
          var html = await getBodyAsync(item, Office.CoercionType.Html)
          bodyText = String(html || '')
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<[^>]+>/g, '')
        } catch (_) {
          bodyText = ''
        }
      }

      var subj = ''
      try {
        subj = item.subject ? String(item.subject) : ''
      } catch (_) {}
      var displayBase = subj.trim() || 'sent-message'
      var fromLine = composeFromLine(item)
      var parentBlob = buildSyntheticEmlCompose(item, bodyText, displayBase, fromLine)
      var parentName = sanitizeFilename(displayBase) + '.eml'

      var parent = await uploadMultipart(token, caseId, {
        blob: parentBlob,
        filename: parentName,
        mime: 'message/rfc822',
        parentFileId: null,
        outlookItemId: oid || undefined,
        outlookConversationId: conv || undefined,
      })
      var parentId = parent.id

      var atts = item.attachments || []
      for (var i = 0; i < atts.length; i++) {
        var a = atts[i]
        if (shouldSkipAttachment(a)) continue
        try {
          var name = sanitizeFilename(a.name || 'attachment')
          var mime = (a.contentType || 'application/octet-stream').split(';')[0].trim()
          var content = await getAttachmentContentAsync(item, a.id)
          var b64 = content && content.content
          if (!b64) continue
          var blob = base64ToBlob(b64, mime)
          await uploadMultipart(token, caseId, {
            blob: blob,
            filename: name,
            mime: mime,
            parentFileId: parentId,
          })
        } catch (_) {
          /* best-effort attachments */
        }
      }

      if (usedPending) await clearPending(token)
    } catch (_) {
      /* Never block send — capture is best-effort. */
    }
    finishOk()
  }

  function onMessageSendHandler(event) {
    void captureSendToCanary(event)
  }

  Office.actions.associate('onMessageSendHandler', onMessageSendHandler)
})()
