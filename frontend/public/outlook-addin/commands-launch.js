/* global Office, OfficeRuntime */
/**
 * Classic Outlook (Windows) OnMessageSend handler — single self-contained file.
 * No async/await; no localStorage; snapshot message then allow send, upload after.
 */
;(function () {
  'use strict'

  var LS_KEY = 'canary_outlook_addin_jwt'
  var LS_API_ORIGIN_KEY = 'canary_outlook_addin_api_origin'
  var RS_KEY = 'canary_jwt'
  var RS_API_ORIGIN_KEY = 'canary_api_origin'
  var RS_PENDING_CASE_KEY = 'canary_pending_send_case_id'
  var RS_PENDING_EXPIRES_KEY = 'canary_pending_send_expires_ms'
  var ADDIN_SEND_VERSION = '1.0.28.0'
  var ITEM_CASE_KEY = 'canary_case_id'
  var SUBJECT_CASE_TOKEN_RE = /^\[CANARY:([0-9a-f-]{36})\]\s*/i
  var SEND_ALLOW_MS = 28000
  var INLINE_UPLOAD_MS = 18000
  var QUEUE_WAKE_KEY = 'canary_send_queue_wake_v1'
  var SNAPSHOT_TIMEOUT_MS = 8000
  var UPLOAD_QUEUE_KEY = 'canary_send_upload_queue_v1'

  function apiOriginFromRoaming() {
    try {
      var fromRo = Office.context.roamingSettings.get(RS_API_ORIGIN_KEY)
      if (fromRo) return String(fromRo).trim().replace(/\/$/, '')
    } catch (_) {}
    return ''
  }

  function apiRootSync() {
    var origin = apiOriginFromRoaming()
    return origin ? origin + '/api' : ''
  }

  function apiRoot() {
    var origin = apiOriginFromRoaming()
    if (origin) return Promise.resolve(origin + '/api')
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      return OfficeRuntime.storage.getItem(LS_API_ORIGIN_KEY)
        .then(function (fromRt) {
          origin = fromRt ? String(fromRt).trim().replace(/\/$/, '') : ''
          return origin ? origin + '/api' : ''
        })
        .catch(function () {
          return apiRootSync()
        })
    }
    return Promise.resolve(apiRootSync())
  }

  function getTokenSync() {
    try {
      return Office.context.roamingSettings.get(RS_KEY) || ''
    } catch (_) {
      return ''
    }
  }

  function getTokenAsync() {
    var sync = getTokenSync()
    if (sync) return Promise.resolve(sync)
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      return OfficeRuntime.storage.getItem(LS_KEY)
        .then(function (fromRt) {
          if (fromRt) return String(fromRt)
          return getTokenSync()
        })
        .catch(function () {
          return getTokenSync()
        })
    }
    return Promise.resolve(getTokenSync())
  }

  function xhrRequest(url, method, headerObj, body) {
    return new Promise(function (resolve, reject) {
      try {
        var xhr = new XMLHttpRequest()
        xhr.open(method || 'GET', url, true)
        if (headerObj) {
          for (var k in headerObj) {
            if (Object.prototype.hasOwnProperty.call(headerObj, k)) {
              xhr.setRequestHeader(k, headerObj[k])
            }
          }
        }
        xhr.onload = function () {
          resolve({
            ok: xhr.status >= 200 && xhr.status < 300,
            status: xhr.status,
            text: xhr.responseText || '',
          })
        }
        xhr.onerror = function () {
          reject(new Error('Network request failed'))
        }
        xhr.send(body == null ? null : body)
      } catch (e) {
        reject(e)
      }
    })
  }

  function xhrFetch(url, options) {
    options = options || {}
    return new Promise(function (resolve, reject) {
      try {
        var xhr = new XMLHttpRequest()
        xhr.open(options.method || 'GET', url, true)
        var headers = options.headers || {}
        Object.keys(headers).forEach(function (key) {
          xhr.setRequestHeader(key, headers[key])
        })
        xhr.onload = function () {
          resolve({
            ok: xhr.status >= 200 && xhr.status < 300,
            status: xhr.status,
            text: xhr.responseText || '',
          })
        }
        xhr.onerror = function () {
          reject(new Error('Network request failed'))
        }
        xhr.send(options.body == null ? null : options.body)
      } catch (e) {
        reject(e)
      }
    })
  }

  function httpFetch(url, options) {
    options = options || {}
    if (typeof fetch === 'function') {
      return fetch(url, options)
        .then(function (res) {
          return res.text().then(function (text) {
            return { ok: res.ok, status: res.status, text: text }
          })
        })
        .catch(function () {
          return xhrFetch(url, options)
        })
    }
    return xhrFetch(url, options)
  }

  function withTimeout(promise, ms, fallbackValue) {
    return new Promise(function (resolve) {
      var settled = false
      var timer = setTimeout(function () {
        if (settled) return
        settled = true
        resolve(typeof fallbackValue === 'function' ? fallbackValue() : fallbackValue)
      }, ms)
      promise.then(
        function (value) {
          if (settled) return
          settled = true
          clearTimeout(timer)
          resolve(value)
        },
        function () {
          if (settled) return
          settled = true
          clearTimeout(timer)
          resolve(typeof fallbackValue === 'function' ? fallbackValue() : fallbackValue)
        },
      )
    })
  }

  function uploadErrorMessage(res, body) {
    if (body && typeof body.detail === 'string') return body.detail
    if (body && body.detail) {
      try {
        return JSON.stringify(body.detail).slice(0, 500)
      } catch (_) {}
    }
    return 'Upload failed (' + res.status + '): ' + String(res.text || '').slice(0, 300)
  }

  function parseJson(text) {
    try {
      return JSON.parse(text || 'null')
    } catch (_) {
      return null
    }
  }

  function logCapture(token, step, detail, caseId) {
    if (!token) return
    apiRoot().then(function (root) {
      if (!root) return
      xhrRequest(
        root + '/outlook-plugin/send-capture-log',
        'POST',
        {
          Authorization: 'Bearer ' + token,
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        JSON.stringify({
          step: String(step || '').slice(0, 64),
          detail: detail ? String(detail).slice(0, 2000) : null,
          case_id: caseId ? String(caseId).slice(0, 64) : null,
        }),
      ).catch(function () {})
    })
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

  function readPendingCaseIdAsync() {
    var fromRoaming = readPendingCaseIdFromRoaming()
    if (fromRoaming) return Promise.resolve(fromRoaming)
    if (typeof OfficeRuntime === 'undefined' || !OfficeRuntime.storage || !OfficeRuntime.storage.getItem) {
      return Promise.resolve('')
    }
    return Promise.all([
      OfficeRuntime.storage.getItem(RS_PENDING_CASE_KEY).catch(function () {
        return ''
      }),
      OfficeRuntime.storage.getItem(RS_PENDING_EXPIRES_KEY).catch(function () {
        return ''
      }),
    ]).then(function (arr) {
      var id = arr[0] ? String(arr[0]).trim() : ''
      var exp = parseInt(String(arr[1] || '0'), 10)
      if (id && exp && Date.now() > exp) return ''
      return id
    })
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

  function parseSubjectCaseToken(subject) {
    var s = String(subject || '')
    var m = SUBJECT_CASE_TOKEN_RE.exec(s)
    if (!m) return { caseId: '', cleanSubject: s }
    return { caseId: String(m[1]), cleanSubject: s.replace(SUBJECT_CASE_TOKEN_RE, '') }
  }

  function stripSubjectCaseTokenAsync(item) {
    return getSubjectAsync(item).then(function (subj) {
      var parsed = parseSubjectCaseToken(subj)
      if (!parsed.caseId || parsed.cleanSubject === subj) return parsed
      return new Promise(function (resolve) {
        if (!item.subject || typeof item.subject.setAsync !== 'function') {
          resolve(parsed)
          return
        }
        item.subject.setAsync(parsed.cleanSubject, function () {
          resolve(parsed)
        })
      })
    })
  }

  function readCaseIdFromItemAsync(item) {
    return new Promise(function (resolve) {
      if (!item || typeof item.loadCustomPropertiesAsync !== 'function') {
        resolve('')
        return
      }
      item.loadCustomPropertiesAsync(function (r) {
        if (r.status !== Office.AsyncResultStatus.Succeeded || !r.value) {
          resolve('')
          return
        }
        try {
          var v = r.value.get(ITEM_CASE_KEY)
          resolve(v ? String(v).trim() : '')
        } catch (_) {
          resolve('')
        }
      })
    })
  }

  function fetchPending(token, root) {
    return httpFetch(root + '/mail-plugin/pending-send', {
      method: 'GET',
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json' },
    }).then(function (res) {
      var body = parseJson(res.text)
      if (!res.ok || !body || typeof body !== 'object') return { active: false }
      return body
    })
  }

  function resolveLinkedCase(token, root, outlookItemId, internetMessageId, conversationId) {
    return httpFetch(root + '/mail-plugin/linked-case', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        outlook_item_id: outlookItemId || null,
        internet_message_id: internetMessageId || null,
        conversation_id: conversationId || null,
      }),
    }).then(function (res) {
      var body = parseJson(res.text)
      if (!res.ok || !body || !body.linked_case || !body.linked_case.id) return ''
      return String(body.linked_case.id)
    })
  }

  function clearPending(token, root) {
    return httpFetch(root + '/mail-plugin/pending-send', {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json' },
    }).catch(function () {})
  }

  function clearPendingLocal() {
    try {
      Office.context.roamingSettings.remove(RS_PENDING_CASE_KEY)
      Office.context.roamingSettings.remove(RS_PENDING_EXPIRES_KEY)
      Office.context.roamingSettings.saveAsync(function () {})
    } catch (_) {}
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage) {
      try {
        OfficeRuntime.storage.removeItem(RS_PENDING_CASE_KEY).catch(function () {})
        OfficeRuntime.storage.removeItem(RS_PENDING_EXPIRES_KEY).catch(function () {})
      } catch (_) {}
    }
  }

  function formatRecipients(list) {
    if (!list || !list.length) return ''
    var out = []
    for (var i = 0; i < list.length; i++) {
      var r = list[i]
      if (!r) continue
      var em = String(r.emailAddress || '').trim()
      var name = String(r.displayName || '').trim().replace(/"/g, '')
      if (name) out.push('"' + name + '" <' + em + '>')
      else if (em) out.push(em)
    }
    return out.join(', ')
  }

  function rfc2822(d) {
    try {
      return new Date(d).toUTCString()
    } catch (_) {
      return new Date().toUTCString()
    }
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

  function composeFromLine(item) {
    try {
      if (item.from && item.from.emailAddress) return formatRecipients([item.from])
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

  function getSubjectAsync(item) {
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
            if (r.status === Office.AsyncResultStatus.Succeeded) resolve(String(r.value || '').trim())
            else resolve('')
          })
          return
        }
      } catch (_) {}
      resolve('')
    })
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

  function sanitizeFilename(name) {
    var n = String(name || '').trim()
    if (!n) return 'sent-message'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'sent-message'
  }

  function base64ToBlob(base64, mime) {
    var bin = atob(base64)
    var bytes = new Uint8Array(bin.length)
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    return new Blob([bytes], { type: mime || 'application/octet-stream' })
  }

  function buildSyntheticEml(item, bodyText, displaySubject, fromLine, imid) {
    var subj =
      displaySubject != null && String(displaySubject).trim() !== ''
        ? String(displaySubject).trim()
        : '(no subject)'
    var toDisp = formatRecipients(item.to || [])
    var ccDisp = formatRecipients(item.cc || [])
    var when = new Date().toISOString()
    var mid = wrapMessageId(imid)
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
    var oid = primaryOutlookItemIdForApi(item)
    try {
      if (item.conversationId) conv = String(item.conversationId).trim()
    } catch (_) {}
    var bodyChain = getBodyAsync(item, Office.CoercionType.Text).catch(function () {
      return ''
    })
    var snapPromise = bodyChain
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
          return {
            bodyText: bodyText,
            subject: subj,
            fromLine: composeFromLine(item),
            imid: imid,
            conv: conv,
            outlookItemId: oid,
            to: item.to || [],
            cc: item.cc || [],
            attachments: [],
          }
        })
      })
    return withTimeout(snapPromise, SNAPSHOT_TIMEOUT_MS, function () {
      return {
        bodyText: '',
        subject: '',
        fromLine: composeFromLine(item),
        imid: imid,
        conv: conv,
        outlookItemId: oid,
        to: [],
        cc: [],
        attachments: [],
      }
    })
  }

  function utf8Bytes(str) {
    if (typeof TextEncoder !== 'undefined') {
      return new TextEncoder().encode(String(str))
    }
    var s = unescape(encodeURIComponent(String(str)))
    var out = new Uint8Array(s.length)
    for (var i = 0; i < s.length; i++) out[i] = s.charCodeAt(i)
    return out
  }

  function concatBytes(chunks) {
    var total = 0
    for (var i = 0; i < chunks.length; i++) total += chunks[i].length
    var out = new Uint8Array(total)
    var offset = 0
    for (var j = 0; j < chunks.length; j++) {
      out.set(chunks[j], offset)
      offset += chunks[j].length
    }
    return out
  }

  function blobToArrayBuffer(blob) {
    return new Promise(function (resolve, reject) {
      try {
        var reader = new FileReader()
        reader.onload = function () {
          resolve(reader.result)
        }
        reader.onerror = function () {
          reject(new Error('Could not read upload blob'))
        }
        reader.readAsArrayBuffer(blob)
      } catch (e) {
        reject(e)
      }
    })
  }

  /** Classic OnMessageSend sandbox often rejects FormData — build multipart manually for XHR. */
  function uploadMultipartRawXhr(token, root, caseId, payload) {
    var boundary = '----CanaryBoundary' + String(Date.now()) + Math.random().toString(36).slice(2)
    var filename = String(payload.filename || 'upload').replace(/"/g, '')
    var mime = payload.mime || 'application/octet-stream'
    var fields = { folder: '' }
    if (payload.parentFileId) {
      fields.parent_file_id = String(payload.parentFileId)
    } else {
      if (payload.outlookItemId) fields.outlook_item_id = String(payload.outlookItemId)
      if (payload.outlookConversationId) fields.outlook_conversation_id = String(payload.outlookConversationId)
      if (payload.internetMessageId) fields.source_internet_message_id = String(payload.internetMessageId)
    }

    return blobToArrayBuffer(payload.blob).then(function (fileBuf) {
      var fileBytes = new Uint8Array(fileBuf)
      var crlf = '\r\n'
      var parts = []
      var keys = Object.keys(fields)
      for (var i = 0; i < keys.length; i++) {
        var name = keys[i]
        parts.push(utf8Bytes('--' + boundary + crlf))
        parts.push(utf8Bytes('Content-Disposition: form-data; name="' + name + '"' + crlf + crlf))
        parts.push(utf8Bytes(String(fields[name]) + crlf))
      }
      parts.push(utf8Bytes('--' + boundary + crlf))
      parts.push(
        utf8Bytes(
          'Content-Disposition: form-data; name="upload"; filename="' +
            filename +
            '"' +
            crlf +
            'Content-Type: ' +
            mime +
            crlf +
            crlf,
        ),
      )
      parts.push(fileBytes)
      parts.push(utf8Bytes(crlf + '--' + boundary + '--' + crlf))
      var body = concatBytes(parts)

      return new Promise(function (resolve, reject) {
        try {
          var xhr = new XMLHttpRequest()
          xhr.open('POST', root + '/cases/' + encodeURIComponent(caseId) + '/files', true)
          xhr.setRequestHeader('Authorization', 'Bearer ' + token)
          xhr.setRequestHeader('Content-Type', 'multipart/form-data; boundary=' + boundary)
          xhr.setRequestHeader('Accept', 'application/json')
          xhr.onload = function () {
            var parsed = parseJson(xhr.responseText || '')
            if (xhr.status >= 200 && xhr.status < 300) {
              if (!parsed || !(parsed.id || parsed.file_id)) {
                reject(new Error('Upload succeeded but no file id returned.'))
                return
              }
              if (!parsed.id && parsed.file_id) parsed.id = parsed.file_id
              resolve(parsed)
              return
            }
            reject(new Error(uploadErrorMessage({ status: xhr.status, text: xhr.responseText || '' }, parsed)))
          }
          xhr.onerror = function () {
            reject(new Error('Network request failed'))
          }
          xhr.send(body)
        } catch (e) {
          reject(e)
        }
      })
    })
  }

  function uploadMultipartFormData(token, root, caseId, payload) {
    var fd = new FormData()
    var uploadBody = payload.blob
    try {
      if (typeof File === 'function' && uploadBody instanceof Blob && !(uploadBody instanceof File)) {
        uploadBody = new File([uploadBody], payload.filename, {
          type: payload.mime || 'application/octet-stream',
        })
      }
    } catch (_) {}
    fd.append('upload', uploadBody, payload.filename)
    fd.append('folder', '')
    if (payload.parentFileId) {
      fd.append('parent_file_id', payload.parentFileId)
    } else {
      if (payload.outlookItemId) fd.append('outlook_item_id', payload.outlookItemId)
      if (payload.outlookConversationId) fd.append('outlook_conversation_id', payload.outlookConversationId)
      if (payload.internetMessageId) fd.append('source_internet_message_id', payload.internetMessageId)
    }
    return httpFetch(root + '/cases/' + encodeURIComponent(caseId) + '/files', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
      body: fd,
    }).then(function (res) {
      var body = parseJson(res.text)
      if (!res.ok) {
        throw new Error(uploadErrorMessage(res, body))
      }
      if (!body || !(body.id || body.file_id)) throw new Error('Upload succeeded but no file id returned.')
      if (!body.id && body.file_id) body.id = body.file_id
      return body
    })
  }

  function uploadMultipart(token, root, caseId, payload) {
    return uploadMultipartRawXhr(token, root, caseId, payload).catch(function () {
      return uploadMultipartFormData(token, root, caseId, payload)
    })
  }

  function snapForQueue(snap) {
    return {
      bodyText: String((snap && snap.bodyText) || '').slice(0, 12000),
      subject: String((snap && snap.subject) || '').slice(0, 500),
      fromLine: String((snap && snap.fromLine) || '').slice(0, 500),
      imid: String((snap && snap.imid) || '').slice(0, 500),
      conv: String((snap && snap.conv) || '').slice(0, 500),
      outlookItemId: String((snap && snap.outlookItemId) || '').slice(0, 500),
      to: [],
      cc: [],
    }
  }

  function saveRoamingQueue(payloadStr) {
    return new Promise(function (resolve) {
      try {
        Office.context.roamingSettings.set(UPLOAD_QUEUE_KEY, payloadStr)
        Office.context.roamingSettings.saveAsync(function () {
          resolve()
        })
      } catch (_) {
        resolve()
      }
    })
  }

  function clearQueuedSend() {
    try {
      Office.context.roamingSettings.remove(UPLOAD_QUEUE_KEY)
      Office.context.roamingSettings.saveAsync(function () {})
    } catch (_) {}
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.removeItem) {
      OfficeRuntime.storage.removeItem(UPLOAD_QUEUE_KEY).catch(function () {})
    }
  }

  function uploadWithTimeout(token, root, caseId, snap, caseSource, usedPending, ms) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        reject(new Error('inline_upload_timeout'))
      }, ms)
      uploadSnapshot(token, root, caseId, snap, caseSource, usedPending).then(
        function (id) {
          clearTimeout(timer)
          resolve(id)
        },
        function (err) {
          clearTimeout(timer)
          reject(err)
        },
      )
    })
  }

  function signalQueueWakeAsync() {
    var stamp = String(Date.now())
    var tasks = []
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.setItem) {
      tasks.push(OfficeRuntime.storage.setItem(QUEUE_WAKE_KEY, stamp).catch(function () {}))
    }
    try {
      Office.context.roamingSettings.set(QUEUE_WAKE_KEY, stamp)
      tasks.push(
        new Promise(function (resolve) {
          Office.context.roamingSettings.saveAsync(function () {
            resolve()
          })
        }),
      )
    } catch (_) {}
    return Promise.all(tasks)
  }

  function fileOnSend(token, root, caseId, snap, caseSource, usedPending) {
    function tryInline(ms) {
      return uploadWithTimeout(token, root, caseId, snap, caseSource, usedPending, ms)
    }
    return tryInline(INLINE_UPLOAD_MS)
      .catch(function (firstErr) {
        logCapture(
          token,
          'filed_inline_miss',
          firstErr && firstErr.message ? String(firstErr.message) : String(firstErr),
          caseId,
        )
        return tryInline(10000)
      })
      .then(function () {
        clearQueuedSend()
        logCapture(token, 'filed_inline', 'ok v=' + ADDIN_SEND_VERSION, caseId)
      })
      .catch(function (secondErr) {
        logCapture(
          token,
          'filed_inline_miss2',
          secondErr && secondErr.message ? String(secondErr.message) : String(secondErr),
          caseId,
        )
        return queueSendUpload(token, root, caseId, snap, caseSource, usedPending)
      })
  }

  function queueSendUpload(token, root, caseId, snap, caseSource, usedPending) {
    var payload
    try {
      payload = JSON.stringify({
        v: ADDIN_SEND_VERSION,
        caseId: caseId,
        caseSource: caseSource,
        usedPending: !!usedPending,
        token: String(token || ''),
        snap: snapForQueue(snap),
        queuedAt: Date.now(),
      })
    } catch (e) {
      return Promise.reject(new Error('Could not serialize send queue: ' + (e && e.message ? e.message : String(e))))
    }
    return saveRoamingQueue(payload).then(function () {
      var rt = typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.setItem
      if (rt) {
        return OfficeRuntime.storage.setItem(UPLOAD_QUEUE_KEY, payload).catch(function () {})
      }
    })
      .then(function () {
        return signalQueueWakeAsync()
      })
      .then(function () {
        logCapture(token, 'capture_queued', 'roaming bytes=' + payload.length, caseId)
      })
  }

  function uploadSnapshot(token, root, caseId, snap, caseSource, usedPending) {
    var displayBase = (snap.subject || '').trim() || 'sent-message'
    var parentBlob = buildSyntheticEml(
      { to: snap.to || [], cc: snap.cc || [] },
      snap.bodyText,
      displayBase,
      snap.fromLine,
      snap.imid,
    )
    var parentName = sanitizeFilename(displayBase) + '.eml'
    return uploadMultipart(token, root, caseId, {
      blob: parentBlob,
      filename: parentName,
      mime: 'message/rfc822',
      parentFileId: null,
      outlookItemId: snap.outlookItemId || undefined,
      outlookConversationId: snap.conv || undefined,
      internetMessageId: snap.imid || undefined,
    })
      .then(function (parent) {
        var chain = Promise.resolve(parent.id)
        for (var i = 0; i < snap.attachments.length; i++) {
          ;(function (att) {
            chain = chain.then(function (parentId) {
              return uploadMultipart(token, root, caseId, {
                blob: base64ToBlob(att.b64, att.mime),
                filename: att.name,
                mime: att.mime,
                parentFileId: parentId,
              }).then(function () {
                return parentId
              })
            })
          })(snap.attachments[i])
        }
        return chain.then(function (parentId) {
          if (usedPending) {
            return clearPending(token, root).then(function () {
              clearPendingLocal()
              return parentId
            })
          }
          return parentId
        })
      })
      .then(function (parentId) {
        logCapture(token, 'filed_ok', 'source=' + caseSource + ' parent=' + String(parentId), caseId)
        return parentId
      })
      .catch(function (err) {
        var msg = err && err.message ? String(err.message) : String(err)
        logCapture(token, 'capture_error', msg, caseId)
        throw err
      })
  }

  function applyCanaryCategory(item) {
    return new Promise(function (resolve) {
      if (!item || !item.categories || typeof item.categories.addAsync !== 'function') {
        resolve()
        return
      }
      item.categories.addAsync(['Canary'], function () {
        resolve()
      })
    })
  }

  function captureSendToCanary(event) {
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

    getTokenAsync()
      .then(function (token) {
        if (!token) {
          logCapture('', 'skip_no_token', 'Sign in via task pane before sending.', null)
          finishOk()
          return
        }
        return apiRoot().then(function (root) {
          if (!root) {
            logCapture(token, 'skip_no_api_root', 'Could not resolve Canary API origin.', null)
            finishOk()
            return
          }

          var item = Office.context.mailbox.item
          var Msg =
            Office.MailboxEnums && Office.MailboxEnums.ItemType && Office.MailboxEnums.ItemType.Message
          if (!item || (Msg != null && item.itemType !== Msg)) {
            logCapture(token, 'skip_not_message', 'Item is not a mail message.', null)
            finishOk()
            return
          }

          var oid = primaryOutlookItemIdForApi(item)
          var imid = safeInternetMessageId(item)
          var conv = ''
          try {
            if (item.conversationId) conv = String(item.conversationId).trim()
          } catch (_) {}

          return stripSubjectCaseTokenAsync(item).then(function (subjectToken) {
            return readCaseIdFromItemAsync(item).then(function (itemCaseId) {
              return Promise.all([
                fetchPending(token, root),
                readPendingCaseIdAsync(),
                resolveLinkedCase(token, root, oid, imid, conv),
              ]).then(function (arr) {
                var pending = arr[0]
                var roamingCaseId = arr[1]
                var linkedCaseId = arr[2]
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
                    'No item matter, subject token, pending send, or linked thread (conv=' +
                      (conv || 'none') +
                      ').',
                    null,
                  )
                  finishOk()
                  return
                }

                logCapture(token, 'capture_start', 'source=' + caseSource + ' v=' + ADDIN_SEND_VERSION, caseId)

                return applyCanaryCategory(item).then(function () {
                  return snapshotMessage(item).then(function (snap) {
                    return fileOnSend(token, root, caseId, snap, caseSource, usedPending).then(
                      function () {
                        finishOk()
                      },
                      function (err) {
                        logCapture(
                          token,
                          'capture_error',
                          err && err.message ? String(err.message) : String(err),
                          caseId,
                        )
                        finishOk()
                      },
                    )
                  })
                })
              })
            })
          })
        })
      })
      .catch(function (err) {
        logCapture('', 'capture_error', err && err.message ? String(err.message) : String(err), null)
        finishOk()
      })
  }

  function onMessageSendHandler(event) {
    captureSendToCanary(event)
  }

  function registerSendHandler() {
    try {
      Office.actions.associate('onMessageSendHandler', onMessageSendHandler)
    } catch (_) {}
  }

  registerSendHandler()
  if (typeof Office !== 'undefined' && Office.onReady) {
    Office.onReady(function () {
      registerSendHandler()
    })
  }
})()
