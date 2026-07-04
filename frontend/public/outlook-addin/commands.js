/* global Office, OfficeRuntime */
/**
 * Event-based activation: OnMessageSend — save a synthetic .eml to Canary when a matter is known
 * (pending send from Canary web, or thread match via conversation id / linked metadata).
 * Loaded from commands.html (WebView runtime). Keep upload/MIME helpers aligned with taskpane.js.
 */
;(function () {
  'use strict'

  Office.onReady()

  const LS_KEY = 'canary_outlook_addin_jwt'
  const LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  const RS_KEY = 'canary_jwt'
  const RS_API_ORIGIN_KEY = 'canary_api_origin'
  const RS_PENDING_CASE_KEY = 'canary_pending_send_case_id'
  const RS_PENDING_EXPIRES_KEY = 'canary_pending_send_expires_ms'
  const ADDIN_SEND_VERSION = '1.0.28.0'
  const SEND_ALLOW_MS = 28000

  function pageOrigin() {
    try {
      if (window.location && window.location.href) {
        var u = new URL(window.location.href)
        return u.origin
      }
    } catch (_) {}
    return ''
  }

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

  function getTokenAsync() {
    var shared = globalThis.canaryOutlookShared
    if (shared && shared.getTokenAsync) {
      return shared.getTokenAsync()
    }
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      return OfficeRuntime.storage.getItem(LS_KEY)
        .then(function (fromRt) {
          if (fromRt) return String(fromRt)
          return getToken()
        })
        .catch(function () {
          return getToken()
        })
    }
    return Promise.resolve(getToken())
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

  function xhrRequest(url, options) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest()
      xhr.open(options.method || 'GET', url, true)
      var headers = options.headers || {}
      if (headers.forEach) {
        headers.forEach(function (value, key) {
          xhr.setRequestHeader(key, value)
        })
      } else if (typeof headers === 'object') {
        Object.keys(headers).forEach(function (key) {
          xhr.setRequestHeader(key, headers[key])
        })
      }
      xhr.onload = function () {
        resolve({
          ok: xhr.status >= 200 && xhr.status < 300,
          status: xhr.status,
          text: function () {
            return Promise.resolve(xhr.responseText || '')
          },
          json: function () {
            try {
              return Promise.resolve(JSON.parse(xhr.responseText || 'null'))
            } catch (e) {
              return Promise.reject(e)
            }
          },
        })
      }
      xhr.onerror = function () {
        reject(new Error('Network request failed'))
      }
      xhr.send(options.body == null ? null : options.body)
    })
  }

  function httpFetch(url, options) {
    options = options || {}
    if (typeof fetch === 'function') {
      return fetch(url, options).catch(function (err) {
        return xhrRequest(url, options).catch(function () {
          throw err
        })
      })
    }
    return xhrRequest(url, options)
  }

  function logCapture(token, step, detail, caseId) {
    var msg = '[Canary send ' + ADDIN_SEND_VERSION + '] ' + step + (detail ? ': ' + detail : '')
    try {
      console.warn(msg)
    } catch (_) {}
    if (!token) return
    var root = apiRoot()
    if (!root) return
    httpFetch(root + '/outlook-plugin/send-capture-log', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        step: String(step || '').slice(0, 64),
        detail: detail ? String(detail).slice(0, 2000) : null,
        case_id: caseId ? String(caseId).slice(0, 64) : null,
      }),
    }).catch(function () {})
  }

  function sanitizeFilename(name) {
    var n = String(name || '').trim()
    if (!n) return 'sent-message'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'sent-message'
  }

  function officeMail() {
    return globalThis.canaryOutlookShared || {}
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

  function safeInternetMessageId(item) {
    try {
      var v = item && item.internetMessageId
      if (typeof v === 'string') {
        var s = v.trim()
        if (s && s.indexOf('[object') < 0) return s
      }
    } catch (_) {}
    return ''
  }

  function wrapMessageId(id) {
    var s = String(id || '').trim()
    if (!s || s.indexOf('[object') >= 0) return '<sent@canary-outlook-addin>'
    if (s.charAt(0) === '<') return s
    return '<' + s + '>'
  }

  function getSubjectAsync(item) {
    var om = officeMail()
    if (om.getSubjectAsync) return om.getSubjectAsync(item)
    return new Promise(function (resolve) {
      if (!item || !item.subject) {
        resolve('')
        return
      }
      try {
        if (typeof item.subject === 'string') {
          resolve(String(item.subject).trim())
          return
        }
        if (typeof item.subject.getAsync === 'function') {
          item.subject.getAsync(function (r) {
            if (r.status === Office.AsyncResultStatus.Succeeded) {
              resolve(String(r.value || '').trim())
              return
            }
            resolve('')
          })
          return
        }
      } catch (_) {}
      resolve('')
    })
  }

  function buildSyntheticEmlCompose(item, bodyText, displaySubject, fromLine) {
    var subj =
      displaySubject != null && String(displaySubject).trim() !== ''
        ? String(displaySubject).trim()
        : '(no subject)'
    var toDisp = formatRecipients(item.to || [])
    var ccDisp = formatRecipients(item.cc || [])
    var when = new Date().toISOString()
    var om = officeMail()
    var mid =
      om.wrapMessageId && om.safeInternetMessageId
        ? om.wrapMessageId(om.safeInternetMessageId(item))
        : wrapMessageId(safeInternetMessageId(item))
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
      var imid = (payload.internetMessageId || '').trim()
      if (imid) fd.append('source_internet_message_id', imid)
    }

    var res = await httpFetch(apiRoot() + '/cases/' + encodeURIComponent(caseId) + '/files', {
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
    var res = await httpFetch(apiRoot() + '/mail-plugin/pending-send', { headers: authHeaders(token) })
    var body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || typeof body !== 'object') return { active: false }
    return body
  }

  async function clearPending(token) {
    await httpFetch(apiRoot() + '/mail-plugin/pending-send', {
      method: 'DELETE',
      headers: authHeaders(token),
    }).catch(function () {})
  }

  async function resolveLinkedCase(token, outlookItemId, internetMessageId, conversationId) {
    var res = await httpFetch(apiRoot() + '/mail-plugin/linked-case', {
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

  function readPendingCaseIdFromRoaming() {
    try {
      var expRaw = Office.context.roamingSettings.get(RS_PENDING_EXPIRES_KEY)
      var exp = parseInt(String(expRaw || '0'), 10)
      if (exp && Date.now() > exp) return ''
      return String(Office.context.roamingSettings.get(RS_PENDING_CASE_KEY) || '').trim()
    } catch (_) {
      return ''
    }
  }

  async function readPendingCaseIdAsync() {
    var shared = globalThis.canaryOutlookShared
    if (shared && shared.readPendingSendCaseIdAsync) {
      return shared.readPendingSendCaseIdAsync()
    }
    var fromRoaming = readPendingCaseIdFromRoaming()
    if (fromRoaming) return fromRoaming
    if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.getItem) {
      return ''
    }
    try {
      var arr = await Promise.all([
        OfficeRuntime.storage.getItem(RS_PENDING_CASE_KEY).catch(function () {
          return ''
        }),
        OfficeRuntime.storage.getItem(RS_PENDING_EXPIRES_KEY).catch(function () {
          return ''
        }),
      ])
      var id = arr[0] ? String(arr[0]).trim() : ''
      var exp = parseInt(String(arr[1] || '0'), 10)
      if (id && exp && Date.now() > exp) return ''
      return id
    } catch (_) {
      return ''
    }
  }

  function sh() {
    return globalThis.canaryOutlookShared || {}
  }

  function snapshotAttachments(item) {
    var atts = item.attachments || []
    var chain = Promise.resolve([])
    for (var i = 0; i < atts.length; i++) {
      ;(function (a) {
        if (shouldSkipAttachment(a)) return
        chain = chain.then(function (list) {
          return getAttachmentContentAsync(item, a.id)
            .then(function (content) {
              var b64 = content && content.content
              if (!b64) return list
              list.push({
                name: sanitizeFilename(a.name || 'attachment'),
                mime: (a.contentType || 'application/octet-stream').split(';')[0].trim(),
                b64: b64,
              })
              return list
            })
            .catch(function () {
              return list
            })
        })
      })(atts[i])
    }
    return chain
  }

  function snapshotMessage(item) {
    var imid = safeInternetMessageId(item)
    var conv = ''
    try {
      if (item.conversationId) conv = String(item.conversationId).trim()
    } catch (_) {}
    return getBodyAsync(item, Office.CoercionType.Text)
      .catch(function () {
        return ''
      })
      .then(function (bodyText) {
        if (bodyText && String(bodyText).trim()) return bodyText
        return getBodyAsync(item, Office.CoercionType.Html)
          .then(function (html) {
            return String(html || '')
              .replace(/<br\s*\/?>/gi, '\n')
              .replace(/<[^>]+>/g, '')
          })
          .catch(function () {
            return ''
          })
      })
      .then(function (bodyText) {
        return getSubjectAsync(item).then(function (subj) {
          return snapshotAttachments(item).then(function (attachments) {
            return {
              bodyText: bodyText,
              subject: subj,
              fromLine: composeFromLine(item),
              imid: imid,
              conv: conv,
              to: item.to || [],
              cc: item.cc || [],
              attachments: attachments,
            }
          })
        })
      })
  }

  function uploadSnapshot(token, caseId, snap, caseSource, usedPending) {
    var displayBase = (snap.subject || '').trim() || 'sent-message'
    var parentBlob = buildSyntheticEmlCompose(
      { to: snap.to || [], cc: snap.cc || [] },
      snap.bodyText,
      displayBase,
      snap.fromLine,
    )
    var parentName = sanitizeFilename(displayBase) + '.eml'
    return uploadMultipart(token, caseId, {
      blob: parentBlob,
      filename: parentName,
      mime: 'message/rfc822',
      parentFileId: null,
      outlookItemId: undefined,
      outlookConversationId: snap.conv || undefined,
      internetMessageId: snap.imid || undefined,
    })
      .then(function (parent) {
        var parentId = parent.id
        var chain = Promise.resolve(parentId)
        for (var i = 0; i < snap.attachments.length; i++) {
          ;(function (att) {
            chain = chain.then(function (pid) {
              return uploadMultipart(token, caseId, {
                blob: base64ToBlob(att.b64, att.mime),
                filename: att.name,
                mime: att.mime,
                parentFileId: pid,
              }).then(function () {
                return pid
              })
            })
          })(snap.attachments[i])
        }
        return chain.then(function (pid) {
          if (usedPending) {
            var shared = sh()
            if (shared.clearPendingSendAsync) return shared.clearPendingSendAsync(token).then(function () { return pid })
            return clearPending(token).then(function () { return pid })
          }
          return pid
        })
      })
      .then(function (parentId) {
        logCapture(token, 'filed_ok', 'source=' + caseSource + ' parent=' + String(parentId), caseId)
      })
      .catch(function (err) {
        logCapture(
          token,
          'capture_error',
          err && err.message ? String(err.message) : String(err),
          caseId,
        )
      })
  }

  async function captureSendToCanary(event) {
    var completed = false
    var safetyTimer = null

    function finishOk() {
      if (completed) return
      completed = true
      if (safetyTimer != null) clearTimeout(safetyTimer)
      try {
        event.completed({ allowEvent: true })
      } catch (_) {}
    }

    safetyTimer = setTimeout(function () {
      logCapture('', 'capture_timeout', 'Allowing send after ' + SEND_ALLOW_MS + 'ms safety timeout.', null)
      finishOk()
    }, SEND_ALLOW_MS)

    var token = ''
    try {
      token = await getTokenAsync()
      if (!token) {
        logCapture('', 'skip_no_token', 'Sign in via File to Case before sending.', null)
        finishOk()
        return
      }
      if (!apiRoot()) {
        logCapture(token, 'skip_no_api_root', 'Could not resolve Canary API origin.', null)
        finishOk()
        return
      }

      var item = Office.context.mailbox.item
      var Msg = Office.MailboxEnums && Office.MailboxEnums.ItemType && Office.MailboxEnums.ItemType.Message
      if (!item || (Msg != null && item.itemType !== Msg)) {
        logCapture(token, 'skip_not_message', 'Item is not a mail message.', null)
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
        imid = safeInternetMessageId(item)
      } catch (_) {}
      try {
        if (item.conversationId) conv = String(item.conversationId).trim()
      } catch (_) {}

      var subjectToken = { caseId: '', cleanSubject: '' }
      var applyCompose = globalThis.canaryOutlookApplyCompose
      if (applyCompose && applyCompose.parseSubjectCaseToken) {
        var rawSubj = await getSubjectAsync(item)
        subjectToken = applyCompose.parseSubjectCaseToken(rawSubj)
        if (subjectToken.caseId && subjectToken.cleanSubject !== rawSubj && item.subject && item.subject.setAsync) {
          await new Promise(function (resolve) {
            item.subject.setAsync(subjectToken.cleanSubject, function () {
              resolve()
            })
          })
        }
      }

      var itemCaseId = ''
      if (sh().readCaseIdFromItemAsync) {
        itemCaseId = await sh().readCaseIdFromItemAsync(item)
      }

      var pending = await fetchPending(token)
      var roamingCaseId = await readPendingCaseIdAsync()
      var linkedCaseId = await resolveLinkedCase(token, oid || '', imid || '', conv || '')
      var caseId = ''
      var usedPending = false
      var caseSource = ''
      if (itemCaseId) {
        caseId = itemCaseId
        usedPending = true
        caseSource = 'item_custom'
      } else if (subjectToken && subjectToken.caseId) {
        caseId = subjectToken.caseId
        usedPending = true
        caseSource = 'subject_token'
      } else if (pending && pending.active && pending.case_id) {
        caseId = String(pending.case_id)
        usedPending = true
        caseSource = 'server_pending'
      } else if (roamingCaseId) {
        caseId = roamingCaseId
        usedPending = true
        caseSource = 'roaming_pending'
      } else if (linkedCaseId) {
        caseId = linkedCaseId
        caseSource = 'linked_thread'
      }

      if (!caseId) {
        logCapture(
          token,
          'skip_no_case',
          'No item matter, subject token, pending send, or linked thread (conv=' + (conv || 'none') + ').',
          null,
        )
        finishOk()
        return
      }

      logCapture(token, 'capture_start', 'source=' + caseSource + ' v=' + ADDIN_SEND_VERSION, caseId)
      await applyCanaryCategoryToItem(item)
      var snap = await snapshotMessage(item)
      try {
        await uploadSnapshot(token, caseId, snap, caseSource, usedPending)
      } catch (uploadErr) {
        logCapture(
          token,
          'capture_error',
          uploadErr && uploadErr.message ? String(uploadErr.message) : String(uploadErr),
          caseId,
        )
      }
      finishOk()
    } catch (err) {
      logCapture(
        token,
        'capture_error',
        err && err.message ? String(err.message) : String(err),
        null,
      )
      finishOk()
    }
  }

  function applyGraphCategoryTag(token, item) {
    return new Promise(function (resolve) {
      var mailbox = ''
      try {
        var prof = Office.context.mailbox && Office.context.mailbox.userProfile
        if (prof && prof.emailAddress) mailbox = String(prof.emailAddress).trim()
      } catch (_) {}
      var restId = graphRestItemIdFromItem(item)
      var internetMid = safeInternetMessageId(item)
      if (!mailbox || !restId) {
        resolve()
        return
      }
      httpFetch(apiRoot() + '/outlook-plugin/graph-tag-category', {
        method: 'POST',
        headers: jsonAuthHeaders(token),
        body: JSON.stringify({
          mailbox: mailbox,
          rest_item_id: restId,
          internet_message_id: internetMid || null,
        }),
      })
        .then(function () {
          resolve()
        })
        .catch(function () {
          resolve()
        })
    })
  }

  function applyCanaryCategoryToItem(item) {
    return new Promise(function (resolve) {
      if (!item || !item.categories || typeof item.categories.addAsync !== 'function') {
        resolve()
        return
      }
      item.categories.addAsync(['Canary'], function (r) {
        if (r.status === Office.AsyncResultStatus.Succeeded) {
          resolve()
          return
        }
        var msg = (r.error && r.error.message) || ''
        if (/already|duplicate|same category|in the list/i.test(msg)) {
          resolve()
          return
        }
        resolve()
      })
    })
  }

  function onMessageSendHandler(event) {
    void captureSendToCanary(event)
  }

  function registerSendHandler() {
    try {
      Office.actions.associate('onMessageSendHandler', onMessageSendHandler)
    } catch (_) {}
  }

  registerSendHandler()
  Office.onReady(function () {
    registerSendHandler()
  })
})()
