/* global Office, OfficeRuntime */
'use strict'
;(function () {
  var QUEUE_KEY = 'canary_send_upload_queue_v1'
  var QUEUE_WAKE_KEY = 'canary_send_queue_wake_v1'
  var POLL_MS = 250
  var ADDIN_QUEUE_VERSION = '1.0.28.0'

  function sh() {
    return globalThis.canaryOutlookShared
  }

  var busy = false
  var timer = null

  function notifyStatus(ok, msg) {
    if (typeof globalThis.canarySendUploadStatus === 'function') {
      globalThis.canarySendUploadStatus(ok, msg)
    }
  }

  function sanitizeFilename(name) {
    var n = String(name || '').trim()
    if (!n) return 'sent-message'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'sent-message'
  }

  function buildSyntheticEml(snap) {
    var subj =
      snap.subject != null && String(snap.subject).trim() !== ''
        ? String(snap.subject).trim()
        : '(no subject)'
    var mid = String(snap.imid || '').trim()
    if (!mid || mid.indexOf('[object') >= 0) mid = '<sent@canary-outlook-addin>'
    else if (mid.charAt(0) !== '<') mid = '<' + mid + '>'
    var hdr = ''
    hdr += 'From: ' + (snap.fromLine || '') + '\r\n'
    hdr += 'Subject: ' + subj.replace(/\r|\n/g, ' ') + '\r\n'
    hdr += 'Date: ' + new Date().toUTCString() + '\r\n'
    hdr += 'Message-ID: ' + mid + '\r\n'
    hdr += 'MIME-Version: 1.0\r\n'
    hdr += 'Content-Type: text/plain; charset="utf-8"\r\n'
    hdr += '\r\n'
    hdr += (snap.bodyText || '').replace(/\r\n/g, '\n').replace(/\n/g, '\r\n')
    return new Blob([hdr], { type: 'message/rfc822' })
  }

  function readQueueFromRoaming() {
    try {
      var raw = Office.context.roamingSettings.get(QUEUE_KEY)
      return raw ? String(raw) : ''
    } catch (_) {
      return ''
    }
  }

  function clearQueueStorage() {
    try {
      Office.context.roamingSettings.remove(QUEUE_KEY)
      Office.context.roamingSettings.saveAsync(function () {})
    } catch (_) {}
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.removeItem) {
      OfficeRuntime.storage.removeItem(QUEUE_KEY).catch(function () {})
    }
  }

  async function readQueueRaw() {
    var fromRoaming = readQueueFromRoaming()
    if (fromRoaming) return fromRoaming
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      return OfficeRuntime.storage.getItem(QUEUE_KEY).catch(function () {
        return ''
      })
    }
    return ''
  }

  async function resolveToken(item) {
    var shared = sh()
    if (!shared) return ''
    if (item && item.token) return String(item.token)
    var sync = shared.getToken ? shared.getToken() : ''
    if (sync) return String(sync)
    if (shared.getTokenAsync) return shared.getTokenAsync()
    return ''
  }

  async function uploadMultipart(token, caseId, payload) {
    var shared = sh()
    if (!shared || !shared.apiRoot) throw new Error('Canary API not configured.')
    var fd = new FormData()
    fd.append('upload', payload.blob, payload.filename)
    fd.append('folder', '')
    if (payload.parentFileId) {
      fd.append('parent_file_id', payload.parentFileId)
    } else {
      if (payload.outlookItemId) fd.append('outlook_item_id', payload.outlookItemId)
      if (payload.outlookConversationId) fd.append('outlook_conversation_id', payload.outlookConversationId)
      if (payload.internetMessageId) fd.append('source_internet_message_id', payload.internetMessageId)
    }
    var res = await fetch(shared.apiRoot() + '/cases/' + encodeURIComponent(caseId) + '/files', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
      body: fd,
    })
    var text = await res.text()
    var body = null
    try {
      body = JSON.parse(text)
    } catch (_) {}
    if (!res.ok) {
      var detail = body && body.detail
      var msg = typeof detail === 'string' ? detail : 'Upload failed (' + res.status + '): ' + text.slice(0, 200)
      throw new Error(msg)
    }
    if (!body || !(body.id || body.file_id)) {
      throw new Error('Upload succeeded but no file id returned.')
    }
    return body
  }

  async function processQueueItem(item) {
    var shared = sh()
    if (!shared) throw new Error('Canary shared helpers not loaded.')
    var token = await resolveToken(item)
    if (!token) throw new Error('Not signed in to Canary add-in.')

    var caseId = String(item.caseId || '')
    if (!caseId) throw new Error('Missing case id in upload queue.')

    var snap = item.snap || {}
    var displayBase = (snap.subject || '').trim() || 'sent-message'
    var parentName = sanitizeFilename(displayBase) + '.eml'
    var parentBlob = buildSyntheticEml(snap)

    var parent = await uploadMultipart(token, caseId, {
      blob: parentBlob,
      filename: parentName,
      mime: 'message/rfc822',
      parentFileId: null,
      outlookItemId: snap.outlookItemId || undefined,
      outlookConversationId: snap.conv || undefined,
      internetMessageId: snap.imid || undefined,
    })

    if (item.usedPending) {
      await fetch(shared.apiRoot() + '/mail-plugin/pending-send', {
        method: 'DELETE',
        headers: shared.authHeaders(token),
      }).catch(function () {})
      await shared.persistPendingSendAsync(null)
    }

    return parent
  }

  var lastWakeStamp = ''

  async function readQueueWakeStamp() {
    if (typeof OfficeRuntime !== 'undefined' && OfficeRuntime.storage && OfficeRuntime.storage.getItem) {
      var fromRt = await OfficeRuntime.storage.getItem(QUEUE_WAKE_KEY).catch(function () {
        return ''
      })
      if (fromRt) return String(fromRt)
    }
    try {
      return String(Office.context.roamingSettings.get(QUEUE_WAKE_KEY) || '')
    } catch (_) {
      return ''
    }
  }

  async function tryProcessSendUploadQueue() {
    if (busy) return
    busy = true
    var parsedCaseId = ''
    var item = null
    try {
      var raw = await readQueueRaw()
      if (!raw) return

      item = JSON.parse(raw)
      parsedCaseId = item && item.caseId ? String(item.caseId) : ''
      if (!item || !parsedCaseId) return

      var parent = await processQueueItem(item)
      clearQueueStorage()
      notifyStatus(
        true,
        'Previous sent message' +
          (item.snap && item.snap.subject ? ' “' + String(item.snap.subject).slice(0, 60) + '”' : '') +
          ' filed to Canary.',
      )
    } catch (e) {
      var msg = e && e.message ? String(e.message) : String(e)
      if (item && parsedCaseId) {
        notifyStatus(false, 'Send filing failed: ' + msg)
        clearQueueStorage()
      }
    } finally {
      busy = false
    }
  }

  function startPolling() {
    if (timer != null) return
    timer = setInterval(function () {
      void readQueueWakeStamp().then(function (wake) {
        if (wake && wake !== lastWakeStamp) {
          lastWakeStamp = wake
          void tryProcessSendUploadQueue()
          return
        }
        void tryProcessSendUploadQueue()
      })
    }, POLL_MS)
    void tryProcessSendUploadQueue()
  }

  globalThis.canaryProcessSendUploadQueue = tryProcessSendUploadQueue

  Office.onReady(function () {
    startPolling()
  })
})()
