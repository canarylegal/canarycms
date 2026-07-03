/* global Office */
/**
 * Event-based activation: OnMessageSend — save a synthetic .eml to Canary when a matter is known
 * (pending send from Canary web, or thread match via conversation id / linked metadata).
 * Does not use Microsoft Graph. Keep upload/MIME helpers aligned with taskpane.js.
 *
 * Classic Outlook on Windows loads this file in a JS-only runtime (not a browser). That engine
 * does not support async/await — use Promise chains and callbacks only.
 */
;(function () {
  'use strict'

  /* Initialize Office; handler registration must not rely only on this callback (classic Outlook + JS runtime). */
  Office.onReady()

  var LS_KEY = 'canary_outlook_addin_jwt'
  var LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  var RS_KEY = 'canary_jwt'
  var RS_API_ORIGIN_KEY = 'canary_api_origin'
  var RS_PENDING_CASE_KEY = 'canary_pending_send_case_id'
  var RS_PENDING_EXPIRES_KEY = 'canary_pending_send_expires_ms'

  function globalRef() {
    if (typeof globalThis !== 'undefined') return globalThis
    if (typeof self !== 'undefined') return self
    if (typeof window !== 'undefined') return window
    return {}
  }

  function pageOrigin() {
    try {
      if (typeof window !== 'undefined' && window.location && window.location.href) {
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
      if (typeof localStorage !== 'undefined') {
        var fromLs = localStorage.getItem(LS_API_ORIGIN_KEY)
        if (fromLs) origin = String(fromLs).trim().replace(/\/$/, '')
      }
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
      if (typeof localStorage !== 'undefined') {
        var fromLs = localStorage.getItem(LS_KEY)
        if (fromLs) return String(fromLs)
      }
    } catch (_) {}
    try {
      return Office.context.roamingSettings.get(RS_KEY) || ''
    } catch (_) {
      return ''
    }
  }

  /** OnMessageSend uses the JS-only runtime (not the task pane WebView) — read OfficeRuntime.storage first. */
  function getTokenAsync() {
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

  function readPendingSendCaseIdSync() {
    try {
      var expRaw = Office.context.roamingSettings.get(RS_PENDING_EXPIRES_KEY)
      var exp = parseInt(String(expRaw || '0'), 10)
      if (exp && Date.now() > exp) return ''
      return String(Office.context.roamingSettings.get(RS_PENDING_CASE_KEY) || '').trim()
    } catch (_) {
      return ''
    }
  }

  function persistPendingSendRoamingAsync(caseId, ttlSeconds) {
    var ttl = ttlSeconds == null ? 86400 : Number(ttlSeconds)
    var exp = Date.now() + Math.max(60, ttl) * 1000
    var v = caseId ? String(caseId) : ''
    return new Promise(function (resolve, reject) {
      try {
        if (v) {
          Office.context.roamingSettings.set(RS_PENDING_CASE_KEY, v)
          Office.context.roamingSettings.set(RS_PENDING_EXPIRES_KEY, String(exp))
        } else {
          Office.context.roamingSettings.remove(RS_PENDING_CASE_KEY)
          Office.context.roamingSettings.remove(RS_PENDING_EXPIRES_KEY)
        }
        Office.context.roamingSettings.saveAsync(function (r) {
          if (r.status === Office.AsyncResultStatus.Succeeded || v) resolve()
          else reject(new Error(r.error ? r.error.message : 'Could not save pending send.'))
        })
      } catch (e) {
        if (v) resolve()
        else reject(e)
      }
    }).then(function () {
      if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.setItem) {
        return
      }
      if (v) {
        return OfficeRuntime.storage.setItem(RS_PENDING_CASE_KEY, v).catch(function () {})
      }
      return OfficeRuntime.storage.removeItem(RS_PENDING_CASE_KEY).catch(function () {})
    })
  }

  function mirrorAuthToEventRuntimeAsync(token) {
    if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.setItem) {
      return Promise.resolve()
    }
    var origin = apiRoot().replace(/\/api$/, '')
    if (!token) {
      return Promise.all([
        OfficeRuntime.storage.removeItem(LS_KEY).catch(function () {}),
        OfficeRuntime.storage.removeItem(LS_API_ORIGIN_KEY).catch(function () {}),
      ])
    }
    return Promise.all([
      OfficeRuntime.storage.setItem(LS_KEY, String(token)),
      OfficeRuntime.storage.setItem(LS_API_ORIGIN_KEY, origin),
    ]).catch(function () {})
  }

  function clearPendingSendAsync(token) {
    return fetch(apiRoot() + '/mail-plugin/pending-send', {
      method: 'DELETE',
      headers: authHeaders(token),
    })
      .catch(function () {})
      .then(function () {
        return persistPendingSendRoamingAsync(null)
      })
  }

  function syncServerPendingToRoamingAsync(token) {
    if (!token) return Promise.resolve()
    return fetchPending(token).then(function (pending) {
      if (!pending || !pending.active || !pending.case_id) return
      var ttl = 86400
      if (pending.expires_at) {
        try {
          var ms = new Date(pending.expires_at).getTime() - Date.now()
          if (ms > 60000) ttl = Math.ceil(ms / 1000)
        } catch (_) {}
      }
      return persistPendingSendRoamingAsync(String(pending.case_id), ttl).then(function () {
        return mirrorAuthToEventRuntimeAsync(token)
      })
    })
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

  function officeMail() {
    return globalRef().canaryOutlookShared || {}
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
        : '(no subject)'
    var toDisp = formatRecipients(item.to || [])
    var ccDisp = formatRecipients(item.cc || [])
    var when = new Date().toISOString()
    var om = officeMail()
    var mid =
      om.wrapMessageId && om.safeInternetMessageId
        ? om.wrapMessageId(om.safeInternetMessageId(item))
        : '<sent@canary-outlook-addin>'
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

  function uploadMultipart(token, caseId, payload) {
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

    return fetch(apiRoot() + '/cases/' + encodeURIComponent(caseId) + '/files', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
      body: fd,
    }).then(function (res) {
      return res.json().catch(function () {
        return null
      }).then(function (body) {
        if (!res.ok) {
          var detail = body && typeof body === 'object' && body.detail
          var msg = typeof detail === 'string' ? detail : 'Upload failed (' + res.status + ')'
          throw new Error(msg)
        }
        if (!body || typeof body !== 'object' || !body.id) {
          throw new Error('Upload succeeded but no file id returned.')
        }
        return body
      })
    })
  }

  function fetchPending(token) {
    return fetch(apiRoot() + '/mail-plugin/pending-send', { headers: authHeaders(token) })
      .then(function (res) {
        return res.json().catch(function () {
          return null
        }).then(function (body) {
          if (!res.ok || !body || typeof body !== 'object') return { active: false }
          return body
        })
      })
  }

  function resolveLinkedCase(token, outlookItemId, internetMessageId, conversationId) {
    return fetch(apiRoot() + '/mail-plugin/linked-case', {
      method: 'POST',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify({
        outlook_item_id: outlookItemId || null,
        internet_message_id: internetMessageId || null,
        conversation_id: conversationId || null,
      }),
    }).then(function (res) {
      return res.json().catch(function () {
        return null
      }).then(function (body) {
        if (!res.ok || !body || !body.linked_case || !body.linked_case.id) return ''
        return String(body.linked_case.id)
      })
    })
  }

  function getSubjectForItem(item) {
    var om = officeMail()
    if (om.getSubjectAsync) {
      return om.getSubjectAsync(item).then(function (subj) {
        return String(subj || '').trim()
      })
    }
    return Promise.resolve('')
  }

  function resolveBodyText(item) {
    return getBodyAsync(item, Office.CoercionType.Text)
      .catch(function () {
        return ''
      })
      .then(function (bodyText) {
        if (bodyText && String(bodyText).trim()) return String(bodyText)
        return getBodyAsync(item, Office.CoercionType.Html)
          .catch(function () {
            return ''
          })
          .then(function (html) {
            return String(html || '')
              .replace(/<br\s*\/?>/gi, '\n')
              .replace(/<[^>]+>/g, '')
          })
      })
  }

  function uploadAttachmentsSequential(item, token, caseId, parentId) {
    var atts = item.attachments || []
    var idx = 0

    function next() {
      if (idx >= atts.length) return Promise.resolve()
      var a = atts[idx++]
      if (shouldSkipAttachment(a)) return next()
      var name = sanitizeFilename(a.name || 'attachment')
      var mime = (a.contentType || 'application/octet-stream').split(';')[0].trim()
      return getAttachmentContentAsync(item, a.id)
        .then(function (content) {
          var b64 = content && content.content
          if (!b64) return
          var blob = base64ToBlob(b64, mime)
          return uploadMultipart(token, caseId, {
            blob: blob,
            filename: name,
            mime: mime,
            parentFileId: parentId,
          })
        })
        .catch(function () {})
        .then(next)
    }

    return next()
  }

  function captureSendToCanary(event) {
    function finishOk() {
      event.completed({ allowEvent: true })
    }

    getTokenAsync()
      .then(function (token) {
        if (!token || !apiRoot()) return null

        var item = Office.context.mailbox.item
        var Msg = Office.MailboxEnums && Office.MailboxEnums.ItemType && Office.MailboxEnums.ItemType.Message
        if (!item || (Msg != null && item.itemType !== Msg)) return null

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

        return syncServerPendingToRoamingAsync(token).then(function () {
          var roamingCaseId = readPendingSendCaseIdSync()
          return fetchPending(token).then(function (pending) {
            return resolveLinkedCase(token, oid || '', imid || '', conv || '').then(function (linkedCaseId) {
              var caseId = ''
              var usedPending = false
              if (roamingCaseId) {
                caseId = roamingCaseId
                usedPending = true
              } else if (pending && pending.active && pending.case_id) {
                caseId = String(pending.case_id)
                usedPending = true
              } else if (linkedCaseId) {
                caseId = linkedCaseId
              }
              if (!caseId) return null

              return resolveBodyText(item).then(function (bodyText) {
                return getSubjectForItem(item).then(function (subj) {
                  var displayBase = String(subj || '').trim() || 'sent-message'
                  var fromLine = composeFromLine(item)
                  var parentBlob = buildSyntheticEmlCompose(item, bodyText, displayBase, fromLine)
                  var parentName = sanitizeFilename(displayBase) + '.eml'

                  return uploadMultipart(token, caseId, {
                    blob: parentBlob,
                    filename: parentName,
                    mime: 'message/rfc822',
                    parentFileId: null,
                    outlookItemId: undefined,
                    outlookConversationId: conv || undefined,
                    internetMessageId: imid || undefined,
                  }).then(function (parent) {
                    return uploadAttachmentsSequential(item, token, caseId, parent.id).then(function () {
                      var chain = Promise.resolve()
                      if (usedPending) {
                        chain = clearPendingSendAsync(token)
                      }
                      return chain
                        .then(function () {
                          return applyCanaryCategoryToItem(item)
                        })
                        .catch(function () {})
                        .then(function () {
                          return applyGraphCategoryTag(token, item)
                        })
                        .catch(function () {})
                    })
                  })
                })
              })
            })
          })
        })
      })
      .catch(function () {
        /* Never block send — capture is best-effort. */
      })
      .then(function () {
        finishOk()
      })
  }

  function applyGraphCategoryTag(token, item) {
    return new Promise(function (resolve) {
      var mailbox = ''
      try {
        var prof = Office.context.mailbox && Office.context.mailbox.userProfile
        if (prof && prof.emailAddress) mailbox = String(prof.emailAddress).trim()
      } catch (_) {}
      var restId = graphRestItemIdFromItem(item)
      var internetMid = ''
      try {
        if (item && item.internetMessageId) internetMid = String(item.internetMessageId).trim()
      } catch (_) {}
      if (!mailbox || !restId) {
        resolve()
        return
      }
      fetch(apiRoot() + '/outlook-plugin/graph-tag-category', {
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
    captureSendToCanary(event)
  }

  function showFileTaskpane(event) {
    var done = function () {
      try {
        event.completed()
      } catch (_) {}
    }
    try {
      if (Office.addin && typeof Office.addin.showAsTaskpane === 'function') {
        Office.addin
          .showAsTaskpane()
          .then(done)
          .catch(function () {
            done()
          })
        return
      }
    } catch (_) {}
    done()
  }

  function registerSendHandler() {
    try {
      Office.actions.associate('onMessageSendHandler', onMessageSendHandler)
      Office.actions.associate('showFileTaskpane', showFileTaskpane)
    } catch (_) {
      /* Event-based activation not supported on this host. */
    }
  }

  registerSendHandler()
  Office.onReady(function () {
    registerSendHandler()
    getTokenAsync().then(function (token) {
      if (token) syncServerPendingToRoamingAsync(token)
    })
  })
})()
