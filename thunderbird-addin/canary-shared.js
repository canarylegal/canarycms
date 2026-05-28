/* global messenger, browser, globalThis */
'use strict'
;(function () {
  const ORIGIN_KEY = 'canaryApiOrigin'
  const JWT_KEY = 'canary_jwt'

  function getGecko() {
    return globalThis.messenger || globalThis.browser
  }

  function apiRoot(origin) {
    return String(origin || '')
      .trim()
      .replace(/\/$/, '') + '/api'
  }

  function authHeaders(token) {
    const h = new Headers()
    if (token) h.set('Authorization', 'Bearer ' + token)
    h.set('Accept', 'application/json')
    return h
  }

  function jsonAuthHeaders(token) {
    const h = authHeaders(token)
    h.set('Content-Type', 'application/json')
    return h
  }

  function sanitizeFilename(name) {
    let n = String(name || '').trim()
    if (!n) return 'sent-message'
    n = n.replace(/[^A-Za-z0-9._@-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '')
    return n || 'sent-message'
  }

  function matterLabel(c) {
    const num = c.case_number != null ? String(c.case_number) : ''
    const client = c.client_name ? String(c.client_name) : ''
    const title = c.matter_description != null ? String(c.matter_description) : ''
    const primary = [num, client].filter(Boolean).join(' — ') || String(c.id)
    return title ? primary + ' — ' + title : primary
  }

  function rawToBlob(raw) {
    if (raw instanceof ArrayBuffer) {
      return new Blob([raw], { type: 'message/rfc822' })
    }
    if (typeof raw === 'string') {
      const buf = new Uint8Array(raw.length)
      for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i) & 0xff
      return new Blob([buf], { type: 'message/rfc822' })
    }
    throw new Error('Unexpected raw message format.')
  }

  function base64ToBlob(b64, mime) {
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    return new Blob([bytes], { type: mime || 'application/octet-stream' })
  }

  async function getStoredAuth(ext) {
    const st = await ext.storage.local.get([JWT_KEY, ORIGIN_KEY])
    return {
      jwt: (st && st[JWT_KEY]) || '',
      origin: (st && st[ORIGIN_KEY]) || '',
    }
  }

  async function clearStoredJwt(ext) {
    await ext.storage.local.remove(JWT_KEY)
  }

  /** Backend 401 detail strings that mean the saved JWT must be discarded. */
  function isAuthSessionErrorMessage(msg) {
    const m = String(msg || '').trim().toLowerCase()
    return (
      m === '401 unauthorized' ||
      m === 'invalid token' ||
      m === 'missing bearer token' ||
      m.includes('invalid or expired token')
    )
  }

  function folderRefFromHeader(header) {
    if (!header || header.folder == null) return null
    const f = header.folder
    if (typeof f === 'string' || typeof f === 'number') return f
    if (typeof f === 'object' && f.id != null) return f.id
    return null
  }

  async function resolveImapRefs(ext, header) {
    let mbox = ''
    const uid = header && header.id != null ? String(header.id) : ''
    const fref = header && header.folder
    if (fref && typeof fref === 'object' && !Array.isArray(fref)) {
      if (fref.path) mbox = String(fref.path).trim()
      else if (fref.name) mbox = String(fref.name).trim()
    }
    const folderId = folderRefFromHeader(header)
    if (!mbox && folderId != null && ext.folders && typeof ext.folders.get === 'function') {
      try {
        const folder = await ext.folders.get(folderId)
        if (folder) {
          mbox = String(folder.path || folder.name || '').trim()
        }
      } catch (_) {
        /* optional */
      }
    }
    if (!mbox && folderId != null && typeof folderId === 'string') {
      mbox = folderId
    }
    return { mbox, uid }
  }

  /**
   * @param {object} opts
   * @param {string} opts.caseId
   * @param {Blob} opts.blob
   * @param {string} opts.filename
   * @param {string} [opts.folder]
   * @param {string|null} [opts.parentFileId]
   * @param {string|null} [opts.precedentId]
   * @param {string|null} [opts.caseContactId]
   * @param {string|null} [opts.globalContactId]
   * @param {{ mbox?: string, uid?: string }|null} [opts.imapRefs]
   * @param {string|null} [opts.internetMessageId]
   */
  async function uploadCaseFile(opts) {
    const fd = new FormData()
    fd.append('upload', opts.blob, opts.filename)
    fd.append('folder', opts.folder || '')
    if (opts.parentFileId) fd.append('parent_file_id', opts.parentFileId)
    if (opts.precedentId) fd.append('compose_precedent_id', opts.precedentId)
    if (opts.caseContactId) fd.append('compose_case_contact_id', opts.caseContactId)
    if (opts.globalContactId) fd.append('compose_global_contact_id', opts.globalContactId)
    if (opts.imapRefs && opts.imapRefs.mbox) fd.append('source_imap_mbox', opts.imapRefs.mbox)
    if (opts.imapRefs && opts.imapRefs.uid) fd.append('source_imap_uid', opts.imapRefs.uid)
    if (opts.internetMessageId) fd.append('source_internet_message_id', opts.internetMessageId)
    const res = await fetch(
      apiRoot(opts.origin) + '/cases/' + encodeURIComponent(opts.caseId) + '/files',
      {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + opts.token },
        body: fd,
      },
    )
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      const detail = body && typeof body === 'object' && body.detail
      throw new Error(typeof detail === 'string' ? detail : 'Upload failed (' + res.status + ')')
    }
    if (!body || !body.id) {
      throw new Error('Upload succeeded but no file id returned.')
    }
    return body
  }

  const FILED_MAP_KEY = 'canary_filed_tb_messages'
  const VIEWED_KEY = 'canary_last_viewed_filing_context'
  const COMPOSE_PANEL_TAB_KEY = 'canary_compose_panel_tab_id'

  function internetMessageIdVariants(raw) {
    const t = String(raw || '').trim()
    if (!t) return []
    const out = new Set([t])
    if (t.startsWith('<') && t.endsWith('>')) {
      const inner = t.slice(1, -1).trim()
      if (inner) out.add(inner)
    } else if (t.indexOf('@') >= 0) {
      out.add('<' + t + '>')
    }
    return Array.from(out)
  }

  function normalizeTbMessageId(id) {
    if (id == null) return null
    if (typeof id === 'number' && !Number.isNaN(id)) return id
    const n = parseInt(String(id), 10)
    return Number.isFinite(n) ? n : null
  }

  function messageIdForApi(id) {
    const n = normalizeTbMessageId(id)
    return n != null ? n : id
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms)
    })
  }

  function formatComposeRecipients(recipients) {
    if (!recipients) return ''
    const list = Array.isArray(recipients) ? recipients : [recipients]
    const parts = []
    for (let i = 0; i < list.length; i++) {
      const r = list[i]
      if (typeof r === 'string' && r.trim()) {
        parts.push(r.trim())
      } else if (r && typeof r === 'object') {
        const name = r.displayName || r.name || ''
        const email = r.email || r.address || ''
        if (name && email) parts.push(String(name) + ' <' + String(email) + '>')
        else if (email) parts.push(String(email))
        else if (name) parts.push(String(name))
      }
    }
    return parts.join(', ')
  }

  function buildSyntheticEmlFromComposeDetails(details, headerMessageId) {
    const d = details || {}
    const subject = String(d.subject || 'sent-message').replace(/\r?\n/g, ' ')
    const from = formatComposeRecipients(d.from) || 'unknown@local'
    const to = formatComposeRecipients(d.to)
    const cc = formatComposeRecipients(d.cc)
    const bcc = formatComposeRecipients(d.bcc)
    const midRaw = String(headerMessageId || '').trim()
    const mid =
      midRaw && midRaw.indexOf('@') >= 0
        ? midRaw.startsWith('<')
          ? midRaw
          : '<' + midRaw + '>'
        : '<' + Date.now() + '.' + Math.random().toString(36).slice(2) + '@canary.local>'
    const lines = [
      'From: ' + from,
      'To: ' + (to || 'undisclosed-recipients:;'),
      'Subject: ' + subject,
      'Date: ' + new Date().toUTCString(),
      'Message-ID: ' + mid,
      'MIME-Version: 1.0',
    ]
    if (cc) lines.push('Cc: ' + cc)
    if (bcc) lines.push('Bcc: ' + bcc)
    const plain = String(d.plainTextBody || d.body || '').replace(/\r\n/g, '\n')
    const isPlain = !!d.isPlainText || !String(d.body || '').trim()
    if (!isPlain && String(d.body || '').trim()) {
      lines.push('Content-Type: text/html; charset=utf-8')
      lines.push('Content-Transfer-Encoding: 8bit')
      lines.push('')
      lines.push(String(d.body))
    } else {
      lines.push('Content-Type: text/plain; charset=utf-8')
      lines.push('Content-Transfer-Encoding: 8bit')
      lines.push('')
      lines.push(plain)
    }
    return lines.join('\r\n')
  }

  function extractMessagesFromQueryResult(list) {
    if (!list) return []
    if (Array.isArray(list)) return list
    if (Array.isArray(list.messages)) return list.messages
    return []
  }

  async function queryAllMessagesByHeaderMessageId(ext, headerMessageId) {
    if (!ext || !ext.messages || typeof ext.messages.query !== 'function') return []
    const variants = internetMessageIdVariants(headerMessageId)
    if (!variants.length) return []
    const out = []
    const seen = new Set()
    for (let v = 0; v < variants.length; v++) {
      try {
        let list = await ext.messages.query({ headerMessageId: variants[v] })
        for (let page = 0; page < 20; page++) {
          const msgs = extractMessagesFromQueryResult(list)
          for (let i = 0; i < msgs.length; i++) {
            const h = msgs[i]
            if (!h || h.id == null) continue
            const key = String(h.id)
            if (seen.has(key)) continue
            seen.add(key)
            out.push(h)
          }
          if (!list || !list.id || !ext.messages.continueList) break
          list = await ext.messages.continueList(list.id)
          const more = extractMessagesFromQueryResult(list)
          if (!more.length) break
        }
      } catch (_) {
        /* optional */
      }
    }
    return out
  }

  async function queryMessagesByHeaderMessageId(ext, headerMessageId) {
    if (!ext || !ext.messages || typeof ext.messages.query !== 'function') return []
    const variants = internetMessageIdVariants(headerMessageId)
    if (!variants.length) return []
    for (let attempt = 0; attempt < 6; attempt++) {
      if (attempt > 0) await sleep(250 * attempt)
      const all = await queryAllMessagesByHeaderMessageId(ext, headerMessageId)
      if (all.length) return all
    }
    return []
  }

  function extractMessageIdFromHeaders(headers) {
    if (!headers || typeof headers !== 'object') return ''
    const keys = Object.keys(headers)
    for (let i = 0; i < keys.length; i++) {
      if (String(keys[i]).toLowerCase() === 'message-id') {
        const v = headers[keys[i]]
        const s = Array.isArray(v) ? String(v[0] || '') : String(v || '')
        return s.trim()
      }
    }
    return ''
  }

  /**
   * Thunderbird often omits headerMessageId on messages.get; fall back to getFull headers.
   */
  /**
   * Message currently shown in the mail UI (for reply prefill when relatedMessageId is missing).
   */
  async function resolveDisplayedMessageHeader(ext) {
    if (!ext.mailTabs && !ext.messageDisplay) return null
    let tabId = null
    if (ext.mailTabs && typeof ext.mailTabs.getCurrent === 'function') {
      try {
        const cur = await ext.mailTabs.getCurrent()
        if (cur && cur.id != null) tabId = cur.id
      } catch (_) {
        /* no mail tab focused */
      }
    }
    let messages = []
    if (ext.messageDisplay && typeof ext.messageDisplay.getDisplayedMessages === 'function') {
      try {
        const list =
          tabId != null
            ? await ext.messageDisplay.getDisplayedMessages(tabId)
            : await ext.messageDisplay.getDisplayedMessages()
        messages = list && Array.isArray(list.messages) ? list.messages : []
      } catch (_) {
        messages = []
      }
    }
    if (!messages.length && ext.mailTabs && typeof ext.mailTabs.getSelectedMessages === 'function') {
      try {
        const list =
          tabId != null
            ? await ext.mailTabs.getSelectedMessages(tabId)
            : await ext.mailTabs.getSelectedMessages()
        messages = list && Array.isArray(list.messages) ? list.messages : []
      } catch (_) {
        messages = []
      }
    }
    if (!messages.length) return null
    return messages[0]
  }

  async function resolveMessageHeaderForLookup(ext, messageId) {
    const normId = normalizeTbMessageId(messageId)
    if (normId == null) return null
    let header = null
    if (ext.messages && typeof ext.messages.get === 'function') {
      try {
        header = await ext.messages.get(normId)
      } catch (_) {
        header = null
      }
    }
    const fromGet = header && header.headerMessageId ? String(header.headerMessageId).trim() : ''
    if (fromGet) return header
    if (ext.messages && typeof ext.messages.getFull === 'function') {
      try {
        const full = await ext.messages.getFull(normId, { decodeHeaders: true })
        const mid = extractMessageIdFromHeaders(full && full.headers)
        if (mid) {
          return Object.assign({}, header || { id: normId }, { headerMessageId: mid })
        }
      } catch (_) {
        /* optional */
      }
    }
    return header
  }

  async function recordFiledTbMessage(ext, tbMessageId, caseId, fileId, internetMessageId) {
    const key = String(tbMessageId)
    if (!key || !caseId) return
    const st = await ext.storage.session.get(FILED_MAP_KEY)
    const map = (st && st[FILED_MAP_KEY]) || {}
    if (typeof map !== 'object' || map === null) return
    map[key] = {
      caseId: String(caseId),
      fileId: fileId != null ? String(fileId) : null,
      internetMessageId: internetMessageId ? String(internetMessageId).trim() : null,
      at: Date.now(),
    }
    await ext.storage.session.set({ [FILED_MAP_KEY]: map })
  }

  async function lookupFiledTbMessage(ext, tbMessageId, headerMessageId) {
    const st = await ext.storage.session.get(FILED_MAP_KEY)
    const map = (st && st[FILED_MAP_KEY]) || {}
    if (typeof map !== 'object' || map === null) return null
    const key = String(tbMessageId)
    if (map[key]) return map[key]
    if (!headerMessageId) return null
    const want = new Set(internetMessageIdVariants(headerMessageId))
    const keys = Object.keys(map)
    for (let i = 0; i < keys.length; i++) {
      const entry = map[keys[i]]
      if (!entry || !entry.internetMessageId) continue
      const have = internetMessageIdVariants(entry.internetMessageId)
      for (let j = 0; j < have.length; j++) {
        if (want.has(have[j])) return entry
      }
    }
    return null
  }

  async function getViewedFilingContext(ext, tbMessageId, headerMessageId) {
    const st = await ext.storage.session.get(VIEWED_KEY)
    const row = st && st[VIEWED_KEY]
    if (!row || !row.case_id) return null
    if (tbMessageId != null && row.tbMessageId != null && String(row.tbMessageId) === String(tbMessageId)) {
      return row
    }
    if (headerMessageId && row.internetMessageId) {
      const want = new Set(internetMessageIdVariants(headerMessageId))
      const have = internetMessageIdVariants(row.internetMessageId)
      for (let i = 0; i < have.length; i++) {
        if (want.has(have[i])) return row
      }
    }
    return null
  }

  async function fetchLinkedCase(token, origin, ext, header) {
    const mid = header && header.headerMessageId ? String(header.headerMessageId).trim() : ''
    let imapRefs = { mbox: '', uid: '' }
    if (!mid) {
      imapRefs = await resolveImapRefs(ext, header)
    }
    const res = await fetch(apiRoot(origin) + '/mail-plugin/linked-case', {
      method: 'POST',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify({
        outlook_item_id: null,
        internet_message_id: mid || null,
        source_imap_mbox: imapRefs.mbox || null,
        source_imap_uid: imapRefs.uid || null,
      }),
    })
    const body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || !body.linked_case || !body.linked_case.id) return null
    const lc = body.linked_case
    return {
      found: true,
      case_id: lc.id,
      file_id: null,
      folder_path: '',
      case_number: lc.case_number,
      client_name: lc.client_name,
      matter_description: lc.matter_description,
    }
  }

  async function fetchMessageContext(token, origin, ext, header) {
    const mid = header && header.headerMessageId ? String(header.headerMessageId).trim() : ''
    let imapRefs = { mbox: '', uid: '' }
    if (!mid) {
      imapRefs = await resolveImapRefs(ext, header)
    }
    const res = await fetch(apiRoot(origin) + '/mail-plugin/message-context', {
      method: 'POST',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify({
        outlook_item_id: null,
        internet_message_id: mid || null,
        source_imap_mbox: imapRefs.mbox || null,
        source_imap_uid: imapRefs.uid || null,
      }),
    })
    const body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || !body.found || !body.case_id) return null
    return body
  }

  async function fetchPendingSend(token, origin) {
    const res = await fetch(apiRoot(origin) + '/mail-plugin/pending-send', {
      headers: authHeaders(token),
    })
    const body = await res.json().catch(function () {
      return null
    })
    if (!res.ok || !body || typeof body !== 'object') return { active: false }
    return body
  }

  async function syncPendingSend(token, origin, caseId, sourceFileId) {
    if (!caseId) {
      await fetch(apiRoot(origin) + '/mail-plugin/pending-send', {
        method: 'DELETE',
        headers: authHeaders(token),
      }).catch(() => {})
      return
    }
    const body = { case_id: caseId, ttl_seconds: 86400 }
    if (sourceFileId) body.source_file_id = sourceFileId
    const res = await fetch(apiRoot(origin) + '/mail-plugin/pending-send', {
      method: 'PUT',
      headers: jsonAuthHeaders(token),
      body: JSON.stringify(body),
    })
    const respBody = await res.json().catch(function () {
      return null
    })
    if (!res.ok) {
      const detail = respBody && respBody.detail
      throw new Error(typeof detail === 'string' ? detail : 'Could not set pending send matter.')
    }
  }

  async function setComposePanelTabId(ext, tabId) {
    if (!ext || !ext.storage || !ext.storage.session) return
    if (tabId == null) {
      await ext.storage.session.remove(COMPOSE_PANEL_TAB_KEY)
      return
    }
    await ext.storage.session.set({ [COMPOSE_PANEL_TAB_KEY]: tabId })
  }

  async function getComposePanelTabId(ext) {
    if (!ext || !ext.storage || !ext.storage.session) return null
    const st = await ext.storage.session.get(COMPOSE_PANEL_TAB_KEY)
    const id = st && st[COMPOSE_PANEL_TAB_KEY]
    return id != null ? id : null
  }

  async function resolveRelatedMessageIdForCompose(ext, composeTabId) {
    if (composeTabId == null || !ext.compose || typeof ext.compose.getComposeDetails !== 'function') {
      return null
    }
    try {
      const details = await ext.compose.getComposeDetails(composeTabId)
      if (details && details.relatedMessageId != null) return details.relatedMessageId
    } catch (_) {
      /* optional */
    }
    const displayed = await resolveDisplayedMessageHeader(ext)
    if (displayed && displayed.id != null) return displayed.id
    return null
  }

  async function applyFiledTagForMessage(ext, messageId) {
    if (messageId == null) return { ok: false, detail: 'No message id.' }
    if (typeof globalThis.canaryRunApplyFiledTag === 'function') {
      try {
        return await globalThis.canaryRunApplyFiledTag(messageId)
      } catch (e) {
        return { ok: false, detail: (e && e.message) || String(e) }
      }
    }
    if (!ext || !ext.runtime || !ext.runtime.sendMessage) {
      return { ok: false, detail: 'Tag API not available.' }
    }
    return new Promise(function (resolve) {
      ext.runtime.sendMessage({ type: 'canary-apply-filed-tag', messageId: messageId }, function (resp) {
        if (ext.runtime.lastError) {
          resolve({ ok: false, detail: String(ext.runtime.lastError.message) })
          return
        }
        resolve(resp || { ok: true })
      })
    })
  }

  /**
   * Upload a Thunderbird message (.eml) to a matter, record it, and optionally tag it.
   * @returns {Promise<{ header: object, fileId: string|null }>}
   */
  async function fileTbMessageById(ext, token, origin, caseId, messageId, opts) {
    opts = opts || {}
    if (!ext.messages || typeof ext.messages.getRaw !== 'function') {
      throw new Error('messages.getRaw is not available in this build.')
    }
    const header = await resolveMessageHeaderForLookup(ext, messageId)
    if (!header) throw new Error('Could not load the message to file.')
    if (header.headersOnly) {
      throw new Error('Message body not downloaded; wait for the message to load fully, then try again.')
    }
    const rawId = normalizeTbMessageId(header.id)
    if (rawId == null) throw new Error('Invalid message id for filing.')
    const raw = await ext.messages.getRaw(rawId)
    const blob = rawToBlob(raw)
    const subj = (header.subject && String(header.subject).trim()) || 'email'
    const filename = sanitizeFilename(subj) + '.eml'
    const imapRefs = await resolveImapRefs(ext, header)
    let internetMid = header.headerMessageId ? String(header.headerMessageId).trim() : ''
    if (!internetMid && ext.messages && typeof ext.messages.getFull === 'function') {
      try {
        const full = await ext.messages.getFull(rawId, { decodeHeaders: true })
        internetMid = extractMessageIdFromHeaders(full && full.headers)
      } catch (_) {
        /* optional */
      }
    }
    const uploaded = await uploadCaseFile({
      token,
      origin,
      caseId,
      blob,
      filename,
      folder: opts.folder || '',
      parentFileId: opts.parentFileId || null,
      imapRefs,
      internetMessageId: internetMid || null,
    })
    const fileId = uploaded && uploaded.id != null ? String(uploaded.id) : null
    await recordFiledTbMessage(ext, header.id, caseId, fileId, internetMid)
    if (opts.tag !== false) {
      await applyFiledTagForMessage(ext, header.id)
    }
    return { header: header, fileId: fileId }
  }

  function isPopoutWindow() {
    try {
      const s = String(globalThis.location && globalThis.location.search || '')
      return (
        s.indexOf('autoWindow=1') !== -1 ||
        s.indexOf('contextFiling=1') !== -1 ||
        s.indexOf('companion=1') !== -1
      )
    } catch (_) {
      return false
    }
  }

  async function closeExtensionWindow(ext) {
    try {
      globalThis.close()
    } catch (_) {
      /* ignore */
    }
    const gecko = ext || getGecko()
    if (!gecko || !gecko.windows || typeof gecko.windows.getCurrent !== 'function') return
    try {
      const win = await gecko.windows.getCurrent()
      if (win && win.id != null && typeof gecko.windows.remove === 'function') {
        await gecko.windows.remove(win.id)
      }
    } catch (_) {
      /* ignore */
    }
  }

  function wirePopoutCloseButton(buttonId) {
    const btn =
      typeof buttonId === 'string' ? globalThis.document && globalThis.document.getElementById(buttonId) : buttonId
    if (!btn) return
    if (!isPopoutWindow()) {
      btn.hidden = true
      return
    }
    btn.hidden = false
    btn.addEventListener('click', function () {
      void closeExtensionWindow(getGecko())
    })
  }

  globalThis.canaryShared = {
    ORIGIN_KEY,
    JWT_KEY,
    getGecko,
    apiRoot,
    authHeaders,
    jsonAuthHeaders,
    sanitizeFilename,
    matterLabel,
    rawToBlob,
    base64ToBlob,
    getStoredAuth,
    clearStoredJwt,
    isAuthSessionErrorMessage,
    resolveImapRefs,
    uploadCaseFile,
    fetchPendingSend,
    syncPendingSend,
    setComposePanelTabId,
    getComposePanelTabId,
    resolveRelatedMessageIdForCompose,
    applyFiledTagForMessage,
    fileTbMessageById,
    extractMessageIdFromHeaders,
    recordFiledTbMessage,
    lookupFiledTbMessage,
    getViewedFilingContext,
    fetchLinkedCase,
    resolveDisplayedMessageHeader,
    resolveMessageHeaderForLookup,
    fetchMessageContext,
    internetMessageIdVariants,
    messageIdForApi,
    sleep,
    formatComposeRecipients,
    buildSyntheticEmlFromComposeDetails,
    extractMessagesFromQueryResult,
    queryMessagesByHeaderMessageId,
    queryAllMessagesByHeaderMessageId,
    isPopoutWindow,
    closeExtensionWindow,
    wirePopoutCloseButton,
  }
})()
